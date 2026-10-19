"""Saved Filters of Scoring & GAP Analysis: every selection used (CDRs, filters, Split by, GAP reference,
methodology and National & area summary), reusable, with its result calculated in the background and saved until
its CDRs, methodology or Operator Maps change."""

from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import math
import threading
import time
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from src.modules.column_names import campaign_sort_key, column_identity, resolve_column_name
from src.modules.scoring_area_summary import (
    WARNING_PREFIXES, area_summary_levels, calculate_area_summary, calculate_area_summary_from_history,
    calculate_geographical, calculate_geographical_from_history, geographical_levels, has_area_filters,
    whole_country_filters,
    detach_area_summary, normalize_area_summary_request,
)
from src.modules.scoring_vendors import scoring_vendor_name, scoring_vendor_operators
from src.modules.cdr_auto_selection import CAMPAIGN_PRESET_LABELS, campaign_presets
from src.modules.cdr_stage import combined_dataset_ids
from src.modules.nr_mode import NR_MODES, normalize_nr_mode
from src.modules.repository import Repository, local_now_iso
from src.modules.scoring_config import (
    DEFAULT_AGGREGATION_HIERARCHY,
    complete_aggregation_hierarchy,
    configuration_hash,
    load_aggregation_hierarchy,
    _is_legacy_two_environment_configuration,
    validate_scoring_configuration,
)


CDR_DATASET_KINDS = frozenset({'data', 'voice', 'speech'})
DEFAULT_BASELINE_OPERATOR = 'EE'
DEFAULT_LEVELS = ('Operator',)
SAVED_FILTERS_TABLE = 'saved_filters'
INTERRUPTED_CALCULATION_MESSAGE = 'Interrupted because the application restarted. Calculate it again.'
AGGREGATION_CONTRACT_VERSION = 2
# The Geographical Areas of a result: those of the Breakdown and Separate cities of its Geographical Areas & Scoring
# Trends, on the whole country.
GEOGRAPHICAL_AREAS_VERSION = 2
SCORING_CONTEXT_FILTER_FIELDS = ('Region', 'Cluster', 'City', 'Operator', 'Operator_Vendor', 'Vendor_Operator', 'Vendor', 'Campaign')
SCORING_CONTEXT_FILTER_COLUMNS = {
    'Region': ('Region', 'g_level_2'),
    'Cluster': ('Cluster',),
    'City': ('City', 'g_level_4'),
    'Operator': ('Operator',),
    'Operator_Vendor': ('Operator_Vendor',),
    # Vendor_Operator selections are translated to Operator_Vendor values (_expand_vendor_context_filters).
    'Vendor_Operator': ('Operator_Vendor',),
    'Vendor': ('Vendor',),
    'Campaign': ('Campaign',),
}
# Filters added after saved results existed only take part in their identity when used.
SCORING_OPTIONAL_CONTEXT_FILTERS = frozenset({'Cluster', 'Operator_Vendor', 'Vendor_Operator'})


def _scoring_engine():
    """Load the calculation engine only when a calculation needs it."""
    return importlib.import_module('src.modules.scoring')


def _method_version(configuration: dict[str, Any]) -> str:
    engine = _scoring_engine()
    if configuration is None:
        raise ValueError('A scoring configuration is required. Import the Scoring & GAP Analysis Methodologies before calculating scoring.')
    configured_version = getattr(engine, 'method_version_for_configuration', None)
    if callable(configured_version):
        return str(configured_version(configuration))
    snapshot = validate_scoring_configuration(configuration)
    base_version = str(getattr(engine, 'METHOD_VERSION', '1'))
    return f'{base_version}-config-{configuration_hash(snapshot)[:16]}'


def _workspace_scoring_configuration(repository: Repository) -> dict[str, Any]:
    getter = getattr(repository, 'get_scoring_configuration', None)
    if not callable(getter):
        raise ValueError('Scoring configuration storage is unavailable. Initialize the workspace database before calculating scoring.')
    payload = getter()
    if payload is None:
        raise ValueError('Import the Scoring & GAP Analysis Methodologies before calculating scoring.')
    return validate_scoring_configuration(payload)


def _baseline_aliases(repository: Repository, baseline_operator: str) -> list[str]:
    aliases = [baseline_operator]
    getter = getattr(repository, 'list_operator_mapping_groups', None)
    groups = getter() if callable(getter) else []
    requested = baseline_operator.strip().casefold()
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        canonical = str(group.get('canonical') or '').strip()
        group_aliases = [str(value).strip() for value in group.get('aliases', []) if str(value).strip()]
        labels = [canonical, *group_aliases]
        if requested in {label.casefold() for label in labels if label}:
            aliases = [*labels, baseline_operator]
            break
    return list(dict.fromkeys(value for value in aliases if value))


def _decode_json(value: Any, default: Any) -> Any:
    try:
        decoded = json.loads(str(value or ''))
    except (TypeError, ValueError):
        return default
    return decoded


def _empty_context_filters() -> dict[str, list[str]]:
    return {field: [] for field in SCORING_CONTEXT_FILTER_FIELDS if field not in SCORING_OPTIONAL_CONTEXT_FILTERS}


def _normalize_context_filters(context_filters: dict[str, list[str]] | None) -> dict[str, list[str]]:
    """Normalize supported scoring filters while treating absent values as All."""
    normalized = _empty_context_filters()
    if context_filters is None:
        return normalized
    if not isinstance(context_filters, dict):
        raise ValueError('Scoring context filters must be an object keyed by Region, Cluster, City, Operator, Operator_Vendor, Vendor or Campaign.')

    fields_by_identity = {column_identity(field): field for field in SCORING_CONTEXT_FILTER_FIELDS}
    values_by_field: dict[str, dict[str, str]] = {field: {} for field in SCORING_CONTEXT_FILTER_FIELDS}
    for raw_field, raw_values in context_filters.items():
        field = fields_by_identity.get(column_identity(raw_field))
        if field is None:
            raise ValueError(f"Unsupported scoring context filter '{raw_field}'.")
        if raw_values is None:
            continue
        if isinstance(raw_values, str):
            values = [raw_values]
        elif isinstance(raw_values, (list, tuple, set)):
            values = list(raw_values)
        else:
            raise ValueError(f"Scoring context filter '{field}' must contain a list of values.")
        for raw_value in values:
            if raw_value is None:
                continue
            value = str(raw_value).strip()
            if value:
                values_by_field[field].setdefault(value.casefold(), value)

    for field, values in values_by_field.items():
        if values or field not in SCORING_OPTIONAL_CONTEXT_FILTERS:
            normalized[field] = sorted(values.values(), key=lambda value: (value.casefold(), value))
    return normalized


def _expand_operator_context_filter(
    repository: Repository, context_filters: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Include mapped Operator aliases so canonical selections match raw CDR rows."""
    expanded = {field: list(values) for field, values in context_filters.items()}
    selected = {value.casefold() for value in expanded.get('Operator', [])}
    getter = getattr(repository, 'list_operator_mapping_groups', None)
    groups = getter() if callable(getter) else []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        canonical = str(group.get('canonical') or '').strip()
        raw_aliases = group.get('aliases', [])
        aliases = [str(value).strip() for value in raw_aliases if str(value).strip()] if isinstance(raw_aliases, (list, tuple, set)) else []
        labels = [value for value in [canonical, *aliases] if value]
        if selected.intersection(value.casefold() for value in labels):
            for value in labels:
                selected.add(value.casefold())
                if not any(existing.casefold() == value.casefold() for existing in expanded['Operator']):
                    expanded['Operator'].append(value)
    expanded['Operator'].sort(key=lambda value: (value.casefold(), value))
    return expanded


def _expand_vendor_context_filters(
    repository: Repository, context_filters: dict[str, list[str]], catalogues: dict[int, dict[str, list[str]]],
) -> dict[str, list[str]]:
    """Include the source spellings of mapped Vendor and Operator_Vendor selections, as for Operators."""
    from src.modules.value_maps import ValueMapper

    settings_getter = getattr(repository, 'chart_mapping_settings', None)
    if not callable(settings_getter) or not any(context_filters.get(field) for field in ('Vendor', 'Operator_Vendor', 'Vendor_Operator')):
        return context_filters
    mapper = ValueMapper.from_settings(settings_getter())
    expanded = {field: list(values) for field, values in context_filters.items()}
    # Vendor_Operator is Operator_Vendor the other way round: it selects those values (both: their intersection).
    if expanded.get('Vendor_Operator'):
        wanted = mapper.operator_vendors(expanded['Vendor_Operator'])
        if expanded.get('Operator_Vendor'):
            chosen = {value.casefold() for value in expanded['Operator_Vendor']}
            wanted = [value for value in wanted if value.casefold() in chosen] or ['\u0000']
        expanded['Operator_Vendor'] = wanted
        expanded['Vendor_Operator'] = []
    for field, kind, key in (('Vendor', 'vendor', 'vendors_only'), ('Operator_Vendor', 'operator_vendor', 'vendors')):
        if expanded.get(field):
            sources = [value for catalogue in catalogues.values() for value in catalogue.get(key) or []]
            expanded[field] = sorted(mapper.expand(kind, expanded[field], sources), key=lambda value: (value.casefold(), value))
    return expanded


def _context_filter_cache_values(context_filters: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return the case-insensitive SQL semantics used to identify filter scopes."""
    values = {
        field: sorted({str(value).strip().casefold() for value in context_filters.get(field, []) if str(value).strip()})
        for field in SCORING_CONTEXT_FILTER_FIELDS
    }
    return {field: items for field, items in values.items() if items or field not in SCORING_OPTIONAL_CONTEXT_FILTERS}


def _serialize_result_value(value: Any) -> Any:
    """Convert pandas and NumPy scalars into strict JSON values."""
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _serialize_result_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_result_value(child) for child in value]
    item = getattr(value, 'item', None)
    if callable(item):
        try:
            return _serialize_result_value(item())
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _read_campaigns(repository: Repository, dataset_ids: list[int]) -> dict[int, list[str]]:
    if not dataset_ids:
        return {}
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT dataset_id, campaigns_json FROM cdr_catalogues "
            f"WHERE dataset_id IN ({','.join('?' for _ in dataset_ids)})",
            dataset_ids,
        ).fetchall()
    campaigns: dict[int, list[str]] = {}
    for row in rows:
        values = _decode_json(row['campaigns_json'], [])
        if isinstance(values, list):
            campaigns[int(row['dataset_id'])] = [str(item).strip() for item in values if str(item).strip()]
    for dataset_id in dataset_ids:
        if not campaigns.get(int(dataset_id)):
            campaigns[int(dataset_id)] = repository.list_distinct_dataset_row_values(
                int(dataset_id), 'Campaign', limit=1000,
            )
    return campaigns


DERIVED_ROW_COLUMNS = {'Map_Area', 'Map_Area_Country'}


def _source_snapshot(
    repository: Repository,
    dataset_ids: list[int],
    *,
    expected_nr_mode: str | None = None,
) -> tuple[list[dict[str, Any]], dict[int, list[str]], str]:
    requested_ids = list(dict.fromkeys(int(dataset_id) for dataset_id in dataset_ids))
    if not requested_ids:
        raise ValueError('Select at least one processed CDR dataset.')
    requested_id_set = set(requested_ids)
    datasets_by_id = {
        int(row['id']): row for row in repository.list_datasets()
        if int(row['id']) in requested_id_set
    }
    missing = [dataset_id for dataset_id in requested_ids if dataset_id not in datasets_by_id]
    if missing:
        raise ValueError(f"Selected CDR dataset(s) no longer exist: {', '.join(map(str, missing))}.")

    expected_mode = normalize_nr_mode(expected_nr_mode) if expected_nr_mode else None
    if expected_nr_mode and expected_mode is None:
        raise ValueError('NR Mode must be NSA or SA.')
    campaigns_by_id = _read_campaigns(repository, requested_ids)
    sources: list[dict[str, Any]] = []
    for dataset_id in sorted(requested_ids):
        row = datasets_by_id[dataset_id]
        kind = str(row['dataset_kind'] or '').strip().casefold()
        if kind not in CDR_DATASET_KINDS:
            raise ValueError(f"Dataset '{row['file_name']}' is not a CDR Data, Voice or Speech dataset.")
        if str(row['status'] or '').casefold() != 'ready':
            raise ValueError(f"Dataset '{row['file_name']}' must finish processing before scoring.")
        nr_mode = normalize_nr_mode(row['nr_mode'])
        if nr_mode is None:
            raise ValueError(f"Dataset '{row['file_name']}' has no valid NR Mode.")
        if expected_mode and nr_mode != expected_mode:
            raise ValueError(f"Dataset '{row['file_name']}' does not match the selected {expected_mode} NR Mode.")
        table_name = repository.dataset_rows_table_name(dataset_id)
        if not repository.dataset_rows_table_exists(dataset_id):
            raise ValueError(f"Dataset '{row['file_name']}' has no processed row table.")
        columns = repository.list_dataset_row_columns(dataset_id)
        row_count = repository.profile_row_count(row)
        if row_count < 1:
            raise ValueError(f"Dataset '{row['file_name']}' has no processed rows to score.")
        campaigns = campaigns_by_id.get(dataset_id, [])
        metadata = {
            'dataset_id': dataset_id,
            'name': str(row['file_name'] or ''),
            'kind': kind,
            'nr_mode': nr_mode,
            'campaigns': campaigns,
            'row_count': row_count,
        }
        # Scores are based on the persisted materialization. Keep the cache
        # stable when a workspace is copied or restored and its file paths or
        # dataset IDs change, while profile timestamps capture supported row
        # replacements and Database Management edits.
        signature = {
            'name': metadata['name'],
            'kind': kind,
            'nr_mode': nr_mode,
            'processed_at': str(row['processed_at'] or ''),
            'profile_updated_at': str(row['updated_at'] or ''),
            'normalization_version': int(row['normalization_version'] or 1),
            'vendor_mapping_applied': int(row['vendor_mapping_applied'] or 0),
            'region_mapping_applied': int(row['region_mapping_applied'] or 0),
            'row_count': row_count,
            # The map areas of the tests, kept in the rows in the background, do not change the scores.
            'columns': [column for column in columns if column not in DERIVED_ROW_COLUMNS],
            'campaigns': campaigns,
        }
        sources.append({'metadata': metadata, 'signature': signature, 'columns': columns, 'table_name': table_name})

    modes = {str(source['metadata']['nr_mode']) for source in sources}
    if len(modes) != 1:
        raise ValueError('Select CDR datasets with the same NR Mode.')
    if expected_mode and modes != {expected_mode}:
        raise ValueError(f'Selected CDR datasets do not all match {expected_mode}.')
    source_fingerprint_payload = sorted(
        (source['signature'] for source in sources),
        key=lambda signature: json.dumps(signature, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
    )
    source_fingerprint = hashlib.sha256(
        json.dumps(source_fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()
    return sources, campaigns_by_id, source_fingerprint


def validate_complete_scoring_cdr_selection(
    repository: Repository,
    dataset_ids: list[int],
    nr_mode: str | None,
    context_filters: dict[str, list[str]] | None = None,
) -> list[int]:
    """Validate that a requested run has complete Data, Voice and Speech coverage."""
    normalized_ids = list(dict.fromkeys(int(dataset_id) for dataset_id in dataset_ids))
    normalized_filters = _normalize_context_filters(context_filters)
    sources, _campaigns, _fingerprint = _source_snapshot(
        repository, normalized_ids, expected_nr_mode=nr_mode,
    )
    kinds = {str(source['metadata']['kind']) for source in sources}
    missing_kinds = [kind for kind in ('data', 'voice', 'speech') if kind not in kinds]
    if missing_kinds:
        labels = {'data': 'Data', 'voice': 'Voice', 'speech': 'Speech'}
        missing_label = ', '.join(labels[kind] for kind in missing_kinds)
        raise ValueError(
            'Scoring requires at least one processed Data, Voice and Speech CDR dataset. '
            f'Missing: {missing_label}.'
        )

    campaigns_by_kind: dict[str, set[str]] = {kind: set() for kind in CDR_DATASET_KINDS}
    labels = {'data': 'Data', 'voice': 'Voice', 'speech': 'Speech'}
    for source in sources:
        metadata = source['metadata']
        campaigns_by_kind[str(metadata['kind'])].update(
            str(campaign).strip() for campaign in metadata.get('campaigns', []) if str(campaign).strip()
        )
    selected_campaigns = normalized_filters['Campaign']
    if selected_campaigns:
        campaigns_to_check = selected_campaigns
    else:
        campaigns_to_check = sorted(
            set().union(*campaigns_by_kind.values()), key=lambda value: (value.casefold(), value),
        )
    kind_order = ('data', 'voice', 'speech')
    uncovered = []
    for campaign in campaigns_to_check:
        campaign_key = campaign.casefold()
        missing = [
            labels[kind] for kind in kind_order
            if not any(value.casefold() == campaign_key for value in campaigns_by_kind[kind])
        ]
        if missing:
            uncovered.append(f"{campaign} ({', '.join(missing)})")
    if uncovered:
        raise ValueError(
            'Selected CDR datasets must cover each campaign with Data, Voice and Speech. '
            f'Missing campaign coverage: {"; ".join(uncovered)}.'
        )
    return normalized_ids


def select_all_complete_cdrs(repository: Repository, nr_mode: str) -> list[int]:
    """Every ready CDR of the NR Mode whose campaigns all have Data, Voice and Speech CDRs."""
    mode = normalize_nr_mode(nr_mode)
    included = combined_dataset_ids(repository)
    candidates = [
        row for row in repository.list_datasets()
        if str(row['status'] or '').casefold() == 'ready'
        and str(row['dataset_kind'] or '').strip().casefold() in CDR_DATASET_KINDS
        and int(row['id']) in included
        and normalize_nr_mode(row['nr_mode']) == mode
        and repository.dataset_has_rows(int(row['id']))
    ]
    campaign_index = _read_campaigns(repository, [int(row['id']) for row in candidates])
    # CDRs without a Campaign form their own set, complete when every type has one.
    campaigns_of = {
        int(row['id']): {str(campaign).strip().casefold() for campaign in campaign_index.get(int(row['id']), [])
                         if str(campaign).strip()} or {''}
        for row in candidates
    }
    by_kind: dict[str, set[str]] = {kind: set() for kind in ('data', 'voice', 'speech')}
    for row in candidates:
        by_kind[str(row['dataset_kind']).strip().casefold()].update(campaigns_of[int(row['id'])])
    complete = by_kind['data'] & by_kind['voice'] & by_kind['speech']
    selected = sorted(int(row['id']) for row in candidates if campaigns_of[int(row['id'])] <= complete)
    if not selected:
        raise ValueError(f'There is no complete set of Data, Voice and Speech CDRs in {mode} NR Mode.')
    return validate_complete_scoring_cdr_selection(repository, selected, mode)


def select_latest_companion_cdrs(repository: Repository, dataset_id: int) -> list[int]:
    """Pair a newly processed CDR with the newest compatible CDRs for every type."""
    anchor_id = int(dataset_id)
    anchor_sources, _anchor_campaigns, _fingerprint = _source_snapshot(repository, [anchor_id])
    anchor = anchor_sources[0]['metadata']
    anchor_kind = str(anchor['kind'])
    anchor_mode = str(anchor['nr_mode'])
    target_campaigns = {
        str(campaign).strip() for campaign in anchor.get('campaigns', []) if str(campaign).strip()
    }

    included = combined_dataset_ids(repository) | {anchor_id}
    candidates = [
        row for row in repository.list_datasets()
        if str(row['status'] or '').casefold() == 'ready'
        and str(row['dataset_kind'] or '').strip().casefold() in CDR_DATASET_KINDS
        and int(row['id']) in included
        and normalize_nr_mode(row['nr_mode']) == anchor_mode
        and repository.dataset_has_rows(int(row['id']))
    ]
    campaign_index = _read_campaigns(repository, [int(row['id']) for row in candidates])
    candidates.sort(key=lambda row: (str(row['uploaded_at'] or ''), int(row['id'])), reverse=True)
    selected_ids = [anchor_id]

    labels = {'data': 'Data', 'voice': 'Voice', 'speech': 'Speech'}
    for kind in ('data', 'voice', 'speech'):
        if kind == anchor_kind:
            continue
        compatible: list[Any] = []
        for row in candidates:
            if str(row['dataset_kind'] or '').strip().casefold() != kind:
                continue
            campaigns = set(campaign_index.get(int(row['id']), []))
            if (target_campaigns and campaigns <= target_campaigns) or (not target_campaigns and not campaigns):
                compatible.append(row)

        if target_campaigns:
            for campaign in sorted(target_campaigns, key=str.casefold):
                match = next((
                    row for row in compatible
                    if campaign in campaign_index.get(int(row['id']), [])
                ), None)
                if match is None:
                    raise ValueError(
                        f"No processed {labels[kind]} CDR in {anchor_mode} NR Mode covers campaign '{campaign}'."
                    )
                selected_id = int(match['id'])
                if selected_id not in selected_ids:
                    selected_ids.append(selected_id)
        elif compatible:
            selected_ids.append(int(compatible[0]['id']))
        else:
            raise ValueError(
                f'No processed {labels[kind]} CDR in {anchor_mode} NR Mode has matching campaign coverage.'
            )

    return validate_complete_scoring_cdr_selection(repository, selected_ids, anchor_mode)


def _normalize_levels(
    levels: Iterable[object], sources: list[dict[str, Any]],
    aggregation_hierarchy: Iterable[object] = DEFAULT_AGGREGATION_HIERARCHY,
) -> list[str]:
    raw_levels = [str(level).strip() for level in levels if str(level).strip()]
    if not any(column_identity(level) == 'operator' for level in raw_levels):
        raw_levels.append('Operator')
    available_columns = list(dict.fromkeys(
        str(column) for source in sources for column in source['columns']
    ))
    resolved_levels: list[str] = []
    seen: set[str] = set()
    for requested in raw_levels:
        requested_identity = column_identity(requested)
        if requested_identity == 'operator':
            resolved = 'Operator'
        elif requested_identity in {'datasettype', 'datasetkind'}:
            resolved = 'Dataset Type' if resolve_column_name(available_columns, 'Dataset_Kind') else None
        elif requested_identity in {'ranvendor', 'vendor'}:
            resolved = 'Vendor' if resolve_column_name(available_columns, 'Vendor') else None
        elif requested_identity in {'region', 'city'}:
            canonical = 'Region' if requested_identity == 'region' else 'City'
            aliases = ('Region', 'g_level_2') if canonical == 'Region' else ('City', 'g_level_4')
            resolved = canonical if any(resolve_column_name(available_columns, alias) for alias in aliases) else None
        elif requested_identity == 'cluster':
            resolved = 'Cluster' if resolve_column_name(available_columns, 'Cluster') else None
        elif requested_identity == 'campaign':
            resolved = resolve_column_name(available_columns, 'Campaign')
        else:
            resolved = None
        if not resolved:
            raise ValueError(f"Split by level '{requested}' is not available in the selected CDR datasets.")
        resolved_identity = column_identity(resolved)
        if resolved_identity not in seen:
            resolved_levels.append(resolved)
            seen.add(resolved_identity)
    hierarchy_order = {
        column_identity(field): index
        for index, field in enumerate(complete_aggregation_hierarchy(list(aggregation_hierarchy)))
    }
    resolved_levels.sort(key=lambda value: (
        hierarchy_order.get(column_identity(value), len(hierarchy_order)), value.casefold(),
    ))
    operator_sources = [source for source in sources if resolve_column_name(source['columns'], 'Operator') is None]
    if operator_sources:
        names = ', '.join(str(source['metadata']['name']) for source in operator_sources)
        raise ValueError(f'Operator is required for scoring and is missing from: {names}.')
    return resolved_levels


def saved_filter_key(
    dataset_ids: Iterable[int], levels: Iterable[str], nr_mode: str, baseline_operator: str,
    context_filters: dict[str, list[str]] | None, scoring_profile_id: str, area_summary: dict[str, Any] | None,
) -> str:
    """The identity of a selection: its CDRs, Split by, NR Mode, GAP reference, filters, methodology and National &
    area summary. The same selection is one Saved Filter, whatever its CDRs or methodology hold today."""
    payload = {
        'dataset_ids': sorted({int(value) for value in dataset_ids}),
        'levels': [str(level) for level in levels],
        'nr_mode': str(nr_mode or ''),
        'baseline_operator': str(baseline_operator or '').strip(),
        'context_filters': _context_filter_cache_values(_normalize_context_filters(context_filters)),
        'scoring_profile_id': str(scoring_profile_id or ''),
        'area_summary': area_summary or None,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _result_key(
    levels: list[str], nr_mode: str, baseline_operator: str,
    method_version: str, source_fingerprint: str, config_hash: str = '',
    baseline_aliases: list[str] | None = None,
    context_filters: dict[str, list[str]] | None = None,
    resolved_context_filters: dict[str, list[str]] | None = None,
    operator_mappings: dict[str, str] | None = None,
    scoring_profile_id: str = '',
    scoring_profile_name: str = '',
    area_summary: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """The identity of a result: the selection with what its CDRs, methodology and Operator Maps hold today. A saved
    result whose key differs is calculated again."""
    key_payload = {
        'method_version': method_version,
        'configuration_hash': config_hash,
        'baseline_aliases': sorted(set(baseline_aliases or [baseline_operator]), key=str.casefold),
        'source_fingerprint': source_fingerprint,
        'levels': levels,
        'nr_mode': nr_mode,
        'baseline_operator': baseline_operator,
        'aggregation_contract_version': AGGREGATION_CONTRACT_VERSION,
        'operator_mappings': {
            str(alias).strip().casefold(): str(canonical).strip()
            for alias, canonical in sorted((operator_mappings or {}).items(), key=lambda item: str(item[0]).casefold())
            if str(alias).strip() and str(canonical).strip()
        },
    }
    if scoring_profile_id:
        key_payload['scoring_profile_id'] = scoring_profile_id
    if scoring_profile_name:
        key_payload['scoring_profile_name'] = scoring_profile_name
    if area_summary:
        key_payload['area_summary'] = area_summary
    normalized_filters = _normalize_context_filters(context_filters)
    resolved_filters = _normalize_context_filters(resolved_context_filters or context_filters)
    if any(normalized_filters.values()):
        key_payload['context_filters'] = _context_filter_cache_values(normalized_filters)
        key_payload['resolved_context_filters'] = _context_filter_cache_values(resolved_filters)
    canonical = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest(), canonical


def _row_to_saved_filter(
    row: Any, *, include_result: bool = False, include_snapshot: bool = True,
    include_internal_snapshot: bool = False,
) -> dict[str, Any]:
    if row is None:
        raise ValueError('The Saved Filter was not found.')
    source_metadata_payload = _decode_json(row['source_metadata_json'], {})
    dataset_ids = _decode_json(row['dataset_ids_json'], [])
    levels = _decode_json(row['levels_json'], [])
    cdr_refs = _decode_json(row['cdr_refs_json'], [])
    result = _decode_json(row['result_json'], None) if include_result else None
    if not isinstance(source_metadata_payload, dict):
        source_metadata_payload = {}
    metadata_list = source_metadata_payload.get('sources', [])
    configuration_payload = source_metadata_payload.get('configuration')
    scoring_profile_id = str(source_metadata_payload.get('scoring_profile_id') or '')
    scoring_profile_name = str(source_metadata_payload.get('scoring_profile_name') or '')
    baseline_aliases = source_metadata_payload.get('baseline_aliases', [])
    context_filters = source_metadata_payload.get('context_filters', {})
    resolved_context_filters = source_metadata_payload.get('resolved_context_filters', context_filters)
    aggregation_hierarchy = source_metadata_payload.get('aggregation_hierarchy', [])
    aggregation_contract_version = source_metadata_payload.get('aggregation_contract_version', 1)
    operator_mappings = source_metadata_payload.get('operator_mappings', {})
    area_summary = source_metadata_payload.get('area_summary')
    if not isinstance(context_filters, dict):
        context_filters = {}
    if not isinstance(resolved_context_filters, dict):
        resolved_context_filters = context_filters
    if not isinstance(aggregation_hierarchy, list):
        aggregation_hierarchy = []
    if not isinstance(operator_mappings, dict):
        operator_mappings = {}
    if not isinstance(cdr_refs, list):
        cdr_refs = []
    try:
        aggregation_contract_version = max(1, int(aggregation_contract_version))
    except (TypeError, ValueError):
        aggregation_contract_version = 1
    if not isinstance(metadata_list, list):
        metadata_list = []
    if include_snapshot:
        if configuration_payload is None and isinstance(result, dict):
            configuration_payload = result.get('configuration')
        if _is_legacy_two_environment_configuration(configuration_payload):
            configuration = configuration_payload
        else:
            configuration = validate_scoring_configuration(configuration_payload) if configuration_payload is not None else None
    else:
        configuration = None
    if isinstance(result, dict):
        if configuration is not None:
            result.setdefault('configuration', configuration)
    baseline = str(row['baseline_operator'] or DEFAULT_BASELINE_OPERATOR)
    baseline_aliases = list(dict.fromkeys(
        [baseline, *(str(alias).strip() for alias in baseline_aliases if str(alias).strip())]
    )) if include_snapshot else []
    saved_filter = {
        'id': int(row['id']),
        'selection_key': str(row['selection_key'] or ''),
        'name': str(row['name'] or ''),
        'pinned': bool(row['pinned']),
        # The place of a starred Saved Filter in its list (moved by dragging it), None for the others.
        'position': row['position'] if 'position' in row.keys() else None,
        'use_count': max(1, int(row['use_count'] or 1)),
        'calculation_count': max(0, int(row['calculation_count'] or 0)),
        'last_used_at': str(row['last_used_at'] or ''),
        'result_key': str(row['result_key'] or ''),
        'method_version': str(row['method_version'] or ''),
        'source_fingerprint': str(row['source_fingerprint'] or ''),
        'dataset_ids': [int(value) for value in dataset_ids if str(value).strip().lstrip('-').isdigit()],
        # The CDRs of a Saved Filter imported from another workspace until they are found here (by file).
        'missing_cdrs': [str(item.get('name') or '') for item in cdr_refs if isinstance(item, dict)]
        if not dataset_ids else [],
        'source_metadata': metadata_list,
        'context_filters': {
            str(field): [str(value) for value in values if str(value).strip()]
            for field, values in context_filters.items()
            if isinstance(values, (list, tuple, set))
        },
        'aggregation_hierarchy': [str(value) for value in aggregation_hierarchy if str(value).strip()],
        'aggregation_contract_version': aggregation_contract_version,
        'area_summary': area_summary if isinstance(area_summary, dict) else None,
        'dataset_names': [str(item.get('name') or '') for item in metadata_list if isinstance(item, dict)],
        'campaigns': sorted({
            str(campaign).strip()
            for item in metadata_list if isinstance(item, dict)
            for campaign in item.get('campaigns', []) if str(campaign).strip()
        }, key=campaign_sort_key),
        'nr_mode': str(row['nr_mode'] or ''),
        'levels': [str(value) for value in levels if str(value).strip()],
        'aggregation_levels': [str(value) for value in levels if str(value).strip()],
        'baseline_operator': str(row['baseline_operator'] or DEFAULT_BASELINE_OPERATOR),
        'scoring_profile_id': scoring_profile_id,
        'scoring_profile_name': scoring_profile_name,
        'status': str(row['status'] or 'saved'),
        'progress': max(0, min(100, int(row['progress'] or 0))),
        'message': str(row['message'] or ''),
        'error': str(row['last_error'] or ''),
        'created_by': str(row['created_by'] or 'system'),
        'created_at': str(row['created_at'] or ''),
        'started_at': str(row['started_at'] or ''),
        'updated_at': str(row['updated_at'] or ''),
        'finished_at': str(row['finished_at'] or ''),
        'result': result,
        # The campaigns its Campaign filter stood for when it was last prepared (an automatic choice such as Latest
        # campaign is resolved each time).
        'resolved_campaigns': [str(value) for value in resolved_context_filters.get('Campaign') or [] if str(value).strip()],
        # The campaigns of its National & Geographical Areas Trends when they have campaigns of their own, as last prepared.
        'trend_campaigns': [str(value) for value in (source_metadata_payload.get('area_trends') or {}).get('campaigns') or []
                            if str(value).strip()] if isinstance(source_metadata_payload.get('area_trends'), dict) else [],
    }
    if include_snapshot:
        saved_filter['configuration'] = configuration
        saved_filter['baseline_aliases'] = baseline_aliases
    if include_internal_snapshot:
        saved_filter['resolved_context_filters'] = {
            str(field): [str(value) for value in values if str(value).strip()]
            for field, values in resolved_context_filters.items()
            if isinstance(values, (list, tuple, set))
        }
        saved_filter['operator_mappings'] = {
            str(alias).strip().casefold(): str(canonical).strip()
            for alias, canonical in operator_mappings.items()
            if str(alias).strip() and str(canonical).strip()
        }
        groups = source_metadata_payload.get('methodology_groups')
        saved_filter['methodology_groups'] = groups if isinstance(groups, list) else []
        trends = source_metadata_payload.get('area_trends')
        saved_filter['area_trends'] = trends if isinstance(trends, dict) else None
    return saved_filter


def _prepare_saved_filter(
    repository: Repository,
    dataset_ids: list[int],
    levels: list[str],
    nr_mode: str | None,
    *,
    baseline_operator: str = DEFAULT_BASELINE_OPERATOR,
    context_filters: dict[str, list[str]] | None = None,
    scoring_profile_id: str | None = None,
    area_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The identity of a selection and of its result today, with the snapshot its calculation uses.

    A Campaign filter with an automatic choice (Latest campaign, Previous campaign, Latest 2 campaigns or All available
    campaigns) is kept as such: the selection is that choice, and its campaigns and CDRs are those it stands for now,
    so the Saved Filter follows the campaigns and CDRs that arrive later.
    """
    normalized_context_filters = _normalize_context_filters(context_filters)
    campaign_choice = (campaign_presets(normalized_context_filters['Campaign']) or [''])[0]
    calculation_filters = dict(normalized_context_filters)
    if campaign_choice:
        from src.modules.scoring_selection import auto_scoring_cdr_ids, expand_scoring_campaigns
        mode = normalize_nr_mode(nr_mode) or 'NSA'
        normalized_context_filters['Campaign'] = [campaign_choice]
        calculation_filters['Campaign'] = expand_scoring_campaigns(repository, mode, [campaign_choice])
        dataset_ids = auto_scoring_cdr_ids(repository, mode, [campaign_choice])
        if not dataset_ids:
            raise ValueError(f'{CAMPAIGN_PRESET_LABELS[campaign_choice]} stands for no campaign with Data, Voice and Speech '
                             f'CDRs of {mode} now.')
    normalized_ids = list(dict.fromkeys(int(dataset_id) for dataset_id in dataset_ids))
    normalized_area_summary = normalize_area_summary_request(area_summary, normalized_context_filters)
    vendor_catalogues = repository.cdr_catalogues_by_dataset(normalized_ids)
    vendor_operators = scoring_vendor_operators(vendor_catalogues, repository.list_operator_mapping_groups())
    normalized_context_filters['Vendor'] = calculation_filters['Vendor'] = sorted({
        scoring_vendor_name(value, vendor_operators) for value in normalized_context_filters['Vendor']
    }, key=str.casefold)
    resolved_context_filters = _expand_operator_context_filter(repository, calculation_filters)
    resolved_context_filters = _expand_vendor_context_filters(repository, resolved_context_filters, vendor_catalogues)
    from src.modules.scoring_methodologies import (
        BY_CAMPAIGN, display_configuration, methodology_groups, methodology_label,
    )
    sources, _campaigns, source_fingerprint = _source_snapshot(
        repository, normalized_ids, expected_nr_mode=nr_mode,
    )
    aggregation_hierarchy = load_aggregation_hierarchy(repository)
    normalized_levels = _normalize_levels(levels, sources, aggregation_hierarchy)
    groups: list[dict[str, Any]] = []
    profile_getter = getattr(repository, 'get_scoring_profile', None)
    if scoring_profile_id == BY_CAMPAIGN:
        # Each campaign with the methodology that applies to it (the default one when none does).
        wanted = {value.casefold() for value in calculation_filters.get('Campaign') or []}
        campaigns = [campaign for source in sources for campaign in source['metadata'].get('campaigns') or []
                     if not wanted or campaign.casefold() in wanted]
        groups = methodology_groups(repository.get_scoring_profiles(), campaigns or [''])
        if len(groups) > 1 and 'Campaign' not in normalized_levels:
            raise ValueError('Scoring By campaign with campaigns of different methodologies needs Campaign in the Split by.')
        configuration = validate_scoring_configuration(
            groups[0]['configuration'] if len(groups) == 1 else display_configuration(groups))
        scoring_profile = {'id': BY_CAMPAIGN, 'name': methodology_label(groups)}
    elif callable(profile_getter):
        if scoring_profile_id is None or (
            isinstance(scoring_profile_id, str) and not scoring_profile_id.strip()
        ):
            scoring_profile = profile_getter()
        else:
            if not isinstance(scoring_profile_id, str):
                raise ValueError('Scoring methodology ID must be a non-empty identifier.')
            scoring_profile = profile_getter(scoring_profile_id.strip())
        configuration = validate_scoring_configuration(scoring_profile['configuration'])
    else:
        if scoring_profile_id is not None:
            raise ValueError('This workspace does not support selecting scoring methodologies.')
        configuration = _workspace_scoring_configuration(repository)
        scoring_profile = {'id': '', 'name': ''}
    selected_mode = normalize_nr_mode(nr_mode) if nr_mode else str(sources[0]['metadata']['nr_mode'])
    if selected_mode not in NR_MODES:
        raise ValueError('NR Mode must be NSA or SA.')
    baseline = str(baseline_operator or '').strip()
    if not baseline:
        raise ValueError('Select a comparison baseline operator.')
    baseline_aliases = _baseline_aliases(repository, baseline)
    mapping_getter = getattr(repository, 'list_operator_mappings', None)
    raw_operator_mappings = mapping_getter() if callable(mapping_getter) else {}
    operator_mappings = {
        str(alias).strip().casefold(): str(canonical).strip()
        for alias, canonical in raw_operator_mappings.items()
        if str(alias).strip() and str(canonical).strip()
    } if isinstance(raw_operator_mappings, dict) else {}
    config_hash = configuration_hash(configuration)
    if len(groups) > 1:
        # The result changes with the methodology of any of its campaigns.
        config_hash = hashlib.sha256(json.dumps(
            [[group['profile_id'], configuration_hash(group['configuration']), group['campaigns']] for group in groups],
            sort_keys=True).encode('utf-8')).hexdigest()
    version = _method_version(configuration)
    profile_id = str(scoring_profile.get('id') or '')
    profile_name = str(scoring_profile.get('name') or '')
    area_trends = _area_trends(repository, selected_mode, normalized_area_summary, scoring_profile_id)
    # The result changes with the CDRs and methodologies of the campaigns of the trends too.
    key_area_summary = normalized_area_summary if area_trends is None else {**normalized_area_summary, 'trends': {
        'campaigns': area_trends['campaigns'], 'source_fingerprint': area_trends['source_fingerprint'],
        'methodologies': area_trends.get('configuration_hash', '')}}
    # Results calculated before the Geographical Areas followed the Breakdown and Separate cities on the whole country
    # are calculated again.
    key_area_summary = {**key_area_summary, 'geographical_version': GEOGRAPHICAL_AREAS_VERSION}
    result_key, _canonical = _result_key(
        normalized_levels, selected_mode, baseline, version, source_fingerprint, config_hash, baseline_aliases,
        normalized_context_filters, resolved_context_filters, operator_mappings, profile_id, profile_name,
        key_area_summary,
    )
    snapshot = {
        'sources': [source['metadata'] for source in sources],
        'configuration': configuration,
        'scoring_profile_id': profile_id,
        'scoring_profile_name': profile_name,
        'baseline_aliases': baseline_aliases,
        'context_filters': normalized_context_filters,
        'resolved_context_filters': resolved_context_filters,
        'aggregation_hierarchy': list(aggregation_hierarchy),
        'aggregation_contract_version': AGGREGATION_CONTRACT_VERSION,
        'operator_mappings': operator_mappings,
    }
    if normalized_area_summary:
        snapshot['area_summary'] = normalized_area_summary
    if area_trends is not None:
        snapshot['area_trends'] = area_trends
    if len(groups) > 1:
        snapshot['methodology_groups'] = groups
    return {
        # With an automatic Campaign choice the selection is that choice, whatever CDRs it stands for today.
        'selection_key': saved_filter_key([] if campaign_choice else normalized_ids, normalized_levels, selected_mode, baseline,
                                          normalized_context_filters, profile_id, normalized_area_summary),
        'result_key': result_key, 'method_version': version, 'source_fingerprint': source_fingerprint,
        'dataset_ids': normalized_ids, 'snapshot': snapshot, 'nr_mode': selected_mode, 'levels': normalized_levels,
        'baseline_operator': baseline,
    }


def _area_trends(repository: Repository, nr_mode: str, area_summary: dict[str, Any] | None,
                 scoring_profile_id: str | None) -> dict[str, Any] | None:
    """The campaigns, CDRs and methodologies of National & Geographical Areas Trends with campaigns of their own (an automatic
    choice such as Latest 2 campaigns stands for its campaigns now), or None when they score the job's campaigns."""
    if not area_summary or not area_summary.get('campaigns'):
        return None
    from src.modules.scoring_methodologies import BY_CAMPAIGN, display_configuration, methodology_groups
    from src.modules.scoring_selection import auto_scoring_cdr_ids, expand_scoring_campaigns
    campaigns = expand_scoring_campaigns(repository, nr_mode, area_summary['campaigns'])
    dataset_ids = auto_scoring_cdr_ids(repository, nr_mode, area_summary['campaigns'])
    if not dataset_ids:
        raise ValueError(f'National & Geographical Areas Trends: the chosen campaigns have no Data, Voice and Speech CDRs of {nr_mode} now.')
    sources, _campaigns, fingerprint = _source_snapshot(repository, dataset_ids, expected_nr_mode=nr_mode)
    trends: dict[str, Any] = {'campaigns': list(campaigns), 'dataset_ids': list(dataset_ids), 'source_fingerprint': fingerprint}
    if scoring_profile_id == BY_CAMPAIGN:
        # Each campaign of the trends with the methodology that applies to it, as the job's own campaigns.
        wanted = {value.casefold() for value in campaigns}
        found = [campaign for source in sources for campaign in source['metadata'].get('campaigns') or []
                 if not wanted or campaign.casefold() in wanted]
        groups = methodology_groups(repository.get_scoring_profiles(), found or [''])
        if len(groups) > 1 and area_summary.get('time_split') == 'All':
            raise ValueError('National & Geographical Areas Trends of campaigns with different methodologies cannot aggregate every '
                             'selected CDR: choose another time split.')
        trends['configuration'] = validate_scoring_configuration(
            groups[0]['configuration'] if len(groups) == 1 else display_configuration(groups))
        if len(groups) > 1:
            trends['methodology_groups'] = groups
        trends['configuration_hash'] = hashlib.sha256(json.dumps(
            [[group['profile_id'], configuration_hash(group['configuration']), group['campaigns']] for group in groups],
            sort_keys=True).encode('utf-8')).hexdigest()
    return trends


def _prepare_saved_selection(repository: Repository, saved_filter: dict[str, Any]) -> dict[str, Any]:
    """The identity of the result of a saved Saved Filter with today's CDRs, methodology and Operator Maps."""
    return _prepare_saved_filter(
        repository, saved_filter['dataset_ids'], saved_filter['levels'], saved_filter['nr_mode'],
        baseline_operator=saved_filter['baseline_operator'], context_filters=saved_filter['context_filters'],
        scoring_profile_id=saved_filter['scoring_profile_id'] or None, area_summary=saved_filter['area_summary'],
    )


def _queue_calculation(connection: Any, filter_id: int, prepared: dict[str, Any], username: str, now: str) -> None:
    """Queue the calculation of a Saved Filter with today's CDRs and methodology."""
    connection.execute(
        f"""UPDATE {SAVED_FILTERS_TABLE} SET status = 'queued', progress = 0,
           message = 'Waiting to calculate scoring', result_json = NULL, last_error = NULL, started_at = NULL,
           finished_at = NULL, updated_at = ?, created_by = ?, source_metadata_json = ?, result_key = ?,
           method_version = ?, source_fingerprint = ?, dataset_ids_json = ?, levels_json = ?, nr_mode = ?,
           baseline_operator = ?, cdr_refs_json = '[]'
           WHERE id = ?""",
        (now, str(username or 'system'), json.dumps(prepared['snapshot'], ensure_ascii=False, separators=(',', ':')),
         prepared['result_key'], prepared['method_version'], prepared['source_fingerprint'],
         json.dumps(prepared['dataset_ids']), json.dumps(prepared['levels'], ensure_ascii=False), prepared['nr_mode'],
         prepared['baseline_operator'], int(filter_id)),
    )


def _is_up_to_date(row: Any, result_key: str) -> bool:
    return row['status'] == 'completed' and row['result_key'] == result_key and bool(row['result_json'])


def find_saved_filter(
    repository: Repository, dataset_ids: list[int], levels: list[str], nr_mode: str | None,
    *, baseline_operator: str = DEFAULT_BASELINE_OPERATOR,
    context_filters: dict[str, list[str]] | None = None,
    scoring_profile_id: str | None = None,
    area_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The Saved Filter of a selection, without changing it, and whether its saved result is up to date."""
    prepared = _prepare_saved_filter(
        repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator,
        context_filters=context_filters, scoring_profile_id=scoring_profile_id, area_summary=area_summary,
    )
    with repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE selection_key = ?',
                                 (prepared['selection_key'],)).fetchone()
    if row is None:
        return None
    saved_filter = _row_to_saved_filter(row, include_snapshot=False)
    saved_filter['up_to_date'] = _is_up_to_date(row, prepared['result_key'])
    return saved_filter


def save_saved_filter(
    repository: Repository,
    dataset_ids: list[int],
    levels: list[str],
    nr_mode: str | None,
    *,
    baseline_operator: str = DEFAULT_BASELINE_OPERATOR,
    force: bool = False,
    username: str = 'system',
    context_filters: dict[str, list[str]] | None = None,
    scoring_profile_id: str | None = None,
    area_summary: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Use a selection: its Saved Filter (saved the first time it is used) with its result.

    Returns the Saved Filter and whether its result is ready or already being calculated (``True``), or must be
    calculated (``False``): the first time, when its CDRs, methodology or Operator Maps changed since its result was
    saved, after a failure, or with ``force``. ``area_summary`` (a breakdown level, chosen cities and a time split)
    adds the National & Geographical Areas Trends (and, with campaigns, the Scoring Trends of those campaigns) to a selection.
    """
    prepared = _prepare_saved_filter(
        repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator,
        context_filters=context_filters, scoring_profile_id=scoring_profile_id, area_summary=area_summary,
    )
    now = local_now_iso()
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE selection_key = ?',
                                 (prepared['selection_key'],)).fetchone()
        if row is not None:
            connection.execute(
                f'UPDATE {SAVED_FILTERS_TABLE} SET use_count = use_count + 1, last_used_at = ? WHERE id = ?',
                (now, row['id']),
            )
            if row['status'] in ('queued', 'processing'):
                row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (row['id'],)).fetchone()
                return _row_to_saved_filter(row), True
            if not force and _is_up_to_date(row, prepared['result_key']):
                row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (row['id'],)).fetchone()
                return _row_to_saved_filter(row, include_result=True), True
            _queue_calculation(connection, int(row['id']), prepared, username, now)
            row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (row['id'],)).fetchone()
            return _row_to_saved_filter(row), False
        cursor = connection.execute(
            f"""
            INSERT INTO {SAVED_FILTERS_TABLE} (
                selection_key, last_used_at, result_key, method_version, source_fingerprint, dataset_ids_json,
                source_metadata_json, nr_mode, levels_json, baseline_operator,
                status, progress, message, created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, 'Waiting to calculate scoring', ?, ?, ?)
            """,
            (
                prepared['selection_key'], now, prepared['result_key'], prepared['method_version'],
                prepared['source_fingerprint'], json.dumps(prepared['dataset_ids']),
                json.dumps(prepared['snapshot'], ensure_ascii=False, separators=(',', ':')), prepared['nr_mode'],
                json.dumps(prepared['levels'], ensure_ascii=False), prepared['baseline_operator'],
                str(username or 'system'), now, now,
            ),
        )
        row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE id = ?',
                                 (int(cursor.lastrowid),)).fetchone()
    return _row_to_saved_filter(row), False


def refresh_saved_filter(repository: Repository, filter_id: int, username: str = 'system') -> tuple[bool, str]:
    """Queue the calculation of an opened Saved Filter whose saved result no longer matches its CDRs, methodology
    or Operator Maps (or that has none yet).

    Returns whether it was queued, and why it cannot be calculated (its CDRs or methodology are gone) otherwise.
    """
    _resolve_imported_filters(repository)
    saved_filter = get_saved_filter(repository, filter_id)
    if saved_filter is None or saved_filter['status'] in ('queued', 'processing'):
        return False, ''
    if not saved_filter['dataset_ids']:
        names = ', '.join(saved_filter['missing_cdrs']) or 'its CDRs'
        return False, f'The CDRs of this Saved Filter are not in this workspace: {names}.'
    try:
        prepared = _prepare_saved_selection(repository, saved_filter)
    except ValueError as exc:
        return False, str(exc)
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
        if row is None or row['status'] in ('queued', 'processing') or _is_up_to_date(row, prepared['result_key']):
            return False, ''
        # A failed calculation is not repeated on its own until something it uses changes.
        if row['status'] == 'failed' and row['result_key'] == prepared['result_key']:
            return False, ''
        _queue_calculation(connection, int(filter_id), prepared, username, local_now_iso())
    return True, ''


def list_saved_filters(repository: Repository) -> list[dict[str, Any]]:
    """Every Saved Filter, the starred ones first in their place and then the latest used, without their results.

    Each one lists its CDRs that have been replaced by newer ones (``newer_cdrs``): a Final CDR of the same
    campaign, or a newer cumulative Weekly or Daily CDR.
    """
    _resolve_imported_filters(repository)
    with repository.connection() as connection:
        rows = connection.execute(
            'SELECT id, selection_key, name, pinned, position, use_count, calculation_count, last_used_at, cdr_refs_json, result_key, '
            'method_version, '
            'source_fingerprint, dataset_ids_json, source_metadata_json, nr_mode, levels_json, baseline_operator, '
            'status, progress, message, NULL AS result_json, last_error, created_by, created_at, started_at, '
            f'updated_at, finished_at FROM {SAVED_FILTERS_TABLE} '
            'ORDER BY pinned DESC, position IS NULL, position, julianday(last_used_at) DESC, id DESC'
        ).fetchall()
    saved_filters = [_row_to_saved_filter(row, include_snapshot=False) for row in rows]
    replacements = _replaced_cdrs(repository) if saved_filters else {}
    for saved_filter in saved_filters:
        # One with an automatic Campaign choice takes the newer CDRs on its own the next time it is opened.
        follows = bool(campaign_presets(saved_filter['context_filters'].get('Campaign') or []))
        saved_filter['newer_cdrs'] = [] if follows else [replacements[dataset_id] for dataset_id in saved_filter['dataset_ids']
                                                         if dataset_id in replacements]
    return saved_filters


def _replaced_cdrs(repository: Repository) -> dict[int, dict[str, Any]]:
    """The CDRs replaced by newer ones in the combined tables, with the newest CDR that replaces each one."""
    from src.modules.cdr_stage import combined_inclusion
    try:
        inclusion = combined_inclusion(repository)
    except Exception:  # The notice is optional: without it the Saved Filters are still listed.
        return {}
    names = {int(row['id']): str(row['file_name'] or '') for row in repository.list_datasets()}
    replacements = {}
    for dataset_id, item in inclusion.items():
        newer, seen = item.get('replaced_by'), {dataset_id}
        while newer is not None and inclusion.get(newer, {}).get('replaced_by') is not None and newer not in seen:
            seen.add(newer)
            newer = inclusion[newer]['replaced_by']
        if newer is not None and not item.get('included'):
            replacements[int(dataset_id)] = {'id': int(dataset_id), 'name': names.get(int(dataset_id), ''),
                                             'replaced_by': int(newer), 'replaced_by_name': names.get(int(newer), '')}
    return replacements


def use_newer_cdrs(repository: Repository, filter_id: int, username: str = 'system') -> dict[str, Any] | None:
    """Replace the CDRs of a Saved Filter that newer ones replace and calculate it again, keeping its name, star and
    place. A Saved Filter that already had that selection is merged into it (its name and star are kept when this one
    has none).

    Returns ``None`` when the Saved Filter does not exist; otherwise the Saved Filter, the CDRs replaced
    (``replaced``) and the merged Saved Filter (``merged_filter_id``).
    """
    saved_filter = get_saved_filter(repository, filter_id)
    if saved_filter is None:
        return None
    if saved_filter['status'] in ('queued', 'processing'):
        raise ValueError('Wait until this Saved Filter is calculated to use its newer CDRs.')
    replacements = _replaced_cdrs(repository)
    replaced = [replacements[dataset_id] for dataset_id in saved_filter['dataset_ids'] if dataset_id in replacements]
    if not replaced:
        raise ValueError('This Saved Filter already uses the newest CDRs.')
    dataset_ids = list(dict.fromkeys(
        replacements[dataset_id]['replaced_by'] if dataset_id in replacements else dataset_id
        for dataset_id in saved_filter['dataset_ids']))
    prepared = _prepare_saved_selection(repository, {**saved_filter, 'dataset_ids': dataset_ids})
    updated, merged_filter_id = _replace_selection(repository, filter_id, prepared, username)
    if updated is None:
        return None
    return {'saved_filter': updated, 'replaced': replaced, 'merged_filter_id': merged_filter_id}


def edit_saved_filter(
    repository: Repository,
    filter_id: int,
    dataset_ids: list[int],
    levels: list[str],
    nr_mode: str | None,
    *,
    baseline_operator: str = DEFAULT_BASELINE_OPERATOR,
    username: str = 'system',
    context_filters: dict[str, list[str]] | None = None,
    scoring_profile_id: str | None = None,
    area_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Give a Saved Filter another selection (its NR Mode, CDRs, filters, Split by, GAP reference, methodology or
    National & area summary) and calculate it again, keeping its name, star and place. A Saved Filter that already had
    that selection is merged into it, as with its newer CDRs.

    Returns ``None`` when the Saved Filter does not exist; otherwise the Saved Filter, whether its selection changed
    (``changed``; an unchanged one keeps its result), its selection before (``previous``) and the merged Saved Filter
    (``merged_filter_id``).
    """
    saved_filter = get_saved_filter(repository, filter_id)
    if saved_filter is None:
        return None
    if saved_filter['status'] in ('queued', 'processing'):
        raise ValueError('Wait until this Saved Filter is calculated to edit it.')
    prepared = _prepare_saved_filter(
        repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator,
        context_filters=context_filters, scoring_profile_id=scoring_profile_id, area_summary=area_summary,
    )
    previous = {key: saved_filter[key] for key in (
        'nr_mode', 'dataset_ids', 'levels', 'baseline_operator', 'context_filters', 'scoring_profile_id', 'area_summary')}
    if prepared['selection_key'] == saved_filter['selection_key']:
        return {'saved_filter': saved_filter, 'changed': False,
                'previous': previous, 'merged_filter_id': None}
    updated, merged_filter_id = _replace_selection(repository, filter_id, prepared, username)
    if updated is None:
        return None
    return {'saved_filter': updated, 'changed': True, 'previous': previous, 'merged_filter_id': merged_filter_id}


def _replace_selection(repository: Repository, filter_id: int, prepared: dict[str, Any],
                       username: str) -> tuple[dict[str, Any] | None, int | None]:
    """Give a Saved Filter the prepared selection and queue its calculation, keeping its name, star and place.

    A Saved Filter that already had that selection is merged into it (its name and star are kept when this one has
    none). Returns the Saved Filter (``None`` when it does not exist) and the id of the merged one.
    """
    now = local_now_iso()
    merged_filter_id = None
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
        if row is None:
            return None, None
        duplicate = connection.execute(
            f'SELECT id, name, pinned, position FROM {SAVED_FILTERS_TABLE} WHERE selection_key = ? AND id != ?',
            (prepared['selection_key'], int(filter_id))).fetchone()
        name, pinned, position = row['name'], row['pinned'], row['position']
        if duplicate is not None:
            merged_filter_id = int(duplicate['id'])
            name = name or duplicate['name']
            if not pinned and duplicate['pinned']:
                pinned, position = duplicate['pinned'], duplicate['position']
            connection.execute(f'DELETE FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (merged_filter_id,))
        connection.execute(
            f'UPDATE {SAVED_FILTERS_TABLE} SET selection_key = ?, name = ?, pinned = ?, position = ?, '
            'use_count = use_count + 1, last_used_at = ? WHERE id = ?',
            (prepared['selection_key'], name, pinned, position, now, int(filter_id)))
        _queue_calculation(connection, int(filter_id), prepared, username, now)
        row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
    return _row_to_saved_filter(row), merged_filter_id


def mark_saved_filter_used(repository: Repository, filter_id: int) -> dict[str, Any] | None:
    """Count the opening of a Saved Filter from its card as a use, which also moves it up the list."""
    with repository.connection() as connection:
        connection.execute(f'UPDATE {SAVED_FILTERS_TABLE} SET use_count = use_count + 1, last_used_at = ? WHERE id = ?',
                           (local_now_iso(), int(filter_id)))
    return get_saved_filter(repository, filter_id)


def update_saved_filter(repository: Repository, filter_id: int, *, name: str | None = None,
                           pinned: bool | None = None) -> dict[str, Any] | None:
    """Rename a Saved Filter (an empty name shows its filters) or star it, which keeps it at the top of the list of starred
    ones (unstarring it takes it out of the list)."""
    updates: dict[str, Any] = {}
    if name is not None:
        text = ' '.join(str(name).split())
        if len(text) > 120:
            raise ValueError('The name of a Saved Filter can have up to 120 characters.')
        updates['name'] = text
    if pinned is not None:
        updates['pinned'] = 1 if pinned else 0
    if updates:
        with repository.connection() as connection:
            if pinned is not None:
                row = connection.execute(f'SELECT pinned, position FROM {SAVED_FILTERS_TABLE} WHERE id = ?',
                                         (int(filter_id),)).fetchone()
                if pinned and row is not None and not (row['pinned'] and row['position'] is not None):
                    # A newly starred Saved Filter goes first; the others keep their order.
                    first = connection.execute(
                        f'SELECT MIN(position) FROM {SAVED_FILTERS_TABLE} WHERE pinned = 1 AND position IS NOT NULL').fetchone()[0]
                    updates['position'] = (int(first) - 1) if first is not None else 1
                elif not pinned:
                    updates['position'] = None
            assignments = ', '.join(f'{column} = ?' for column in updates)
            connection.execute(f'UPDATE {SAVED_FILTERS_TABLE} SET {assignments} WHERE id = ?',
                               (*updates.values(), int(filter_id)))
    return get_saved_filter(repository, filter_id)


def reorder_saved_filters(repository: Repository, filter_ids: list[int]) -> list[int]:
    """Put the starred Saved Filters in the order given (dragged in their list); starred ones left out follow it in their
    order. Returns the new order."""
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        starred = [int(row['id']) for row in connection.execute(
            f'SELECT id FROM {SAVED_FILTERS_TABLE} WHERE pinned = 1 '
            'ORDER BY position IS NULL, position, julianday(last_used_at) DESC, id DESC').fetchall()]
        chosen = [int(filter_id) for filter_id in dict.fromkeys(filter_ids) if int(filter_id) in starred]
        order = [*chosen, *(filter_id for filter_id in starred if filter_id not in chosen)]
        connection.executemany(f'UPDATE {SAVED_FILTERS_TABLE} SET position = ? WHERE id = ?',
                               [(index, filter_id) for index, filter_id in enumerate(order, start=1)])
    return order


def recover_interrupted_saved_filters(repository: Repository) -> list[int]:
    """Fail the calculations left running when the application stopped, when the workspace is first opened."""
    now = local_now_iso()
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT id FROM {SAVED_FILTERS_TABLE} WHERE status IN ('queued', 'processing') ORDER BY id",
        ).fetchall()
        filter_ids = [int(row['id']) for row in rows]
        if filter_ids:
            placeholders = ','.join('?' for _ in filter_ids)
            connection.execute(
                f"UPDATE {SAVED_FILTERS_TABLE} SET status = 'failed', last_error = ?, message = ?, updated_at = ?, "
                f"finished_at = ? WHERE id IN ({placeholders}) AND status IN ('queued', 'processing')",
                (INTERRUPTED_CALCULATION_MESSAGE, INTERRUPTED_CALCULATION_MESSAGE, now, now, *filter_ids),
            )
    return filter_ids


def get_saved_filter(
    repository: Repository, filter_id: int, include_result: bool = False,
    include_internal_snapshot: bool = False,
) -> dict[str, Any] | None:
    """A Saved Filter and, optionally, its saved result."""
    with repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
    if row is None:
        return None
    saved_filter = _row_to_saved_filter(
        row, include_result=include_result, include_internal_snapshot=include_internal_snapshot,
    )
    if include_result and not include_internal_snapshot:
        _apply_current_environment_labels(repository, saved_filter)
        # Results saved before environment scaling existed are scaled when they are opened.
        from src.modules.scoring import apply_environment_scaling
        apply_environment_scaling(saved_filter.get('result'), str(saved_filter.get('baseline_operator') or 'EE'))
    return saved_filter


def _apply_current_environment_labels(repository: Repository, saved_filter: dict[str, Any]) -> None:
    """Project current profile labels without changing stored rules or environment keys."""
    try:
        profile = repository.get_scoring_profile(saved_filter.get('scoring_profile_id') or None)
    except ValueError:
        return
    current = profile['configuration'].get('scope', {}).get('environments', {})

    def source_identity(scope: dict[str, Any]) -> tuple[str, str]:
        filters = scope.get('source_filters') or {}
        first = str(filters.get('G_Level_1') or scope.get('g_level_1') or '').strip().casefold()
        second = str(filters.get('G_Level_2') or scope.get('g_level_2') or '').strip().casefold()
        if second in {'connectionroad', 'connectingroads', 'connecting roads'}:
            second = 'connecting roads'
        return first, second

    labels = {source_identity(scope): str(scope.get('display_name') or name)
              for name, scope in current.items()}
    for configuration in (saved_filter.get('configuration'), (saved_filter.get('result') or {}).get('configuration')):
        if not isinstance(configuration, dict):
            continue
        for name, scope in configuration.get('scope', {}).get('environments', {}).items():
            identity = source_identity(scope)
            label = labels.get(identity) if identity[0] else None
            if label and label != str(scope.get('display_name') or name):
                scope['display_name'] = label


def delete_saved_filter(repository: Repository, filter_id: int) -> bool:
    """Remove a Saved Filter and its saved result; its CDRs and the Scoring History stay."""
    with repository.connection() as connection:
        cursor = connection.execute(f'DELETE FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (int(filter_id),))
        return cursor.rowcount > 0


def prune_unpinned_saved_filters(repository: Repository, keep_id: int, username: str) -> list[int]:
    """Only the Saved Filters marked with the star are kept: remove the other unstarred ones of a user when they use
    another one (``keep_id``), except those still calculating or drawing their Points Lost Map."""
    workspace = str(Path(repository.db_path).resolve())
    with _points_loss_guard:
        drawing = {filter_id for path, filter_id in _points_loss_jobs if path == workspace}
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT id FROM {SAVED_FILTERS_TABLE} WHERE pinned = 0 AND id != ? AND created_by = ? "
            "AND status NOT IN ('queued', 'processing')", (int(keep_id), str(username or 'system'))).fetchall()
        removed = [int(row['id']) for row in rows if int(row['id']) not in drawing]
        connection.executemany(f'DELETE FROM {SAVED_FILTERS_TABLE} WHERE id = ?', [(filter_id,) for filter_id in removed])
    return removed


class _SavedFilterDeleted(Exception):
    """Stop a calculation at a checkpoint once its Saved Filter is removed."""


def _update_saved_filter(repository: Repository, filter_id: int, **fields: Any) -> None:
    allowed_fields = {
        'status', 'progress', 'message', 'result_json', 'last_error', 'started_at', 'finished_at',
    }
    updates = {key: value for key, value in fields.items() if key in allowed_fields}
    if not updates:
        return
    updates['updated_at'] = local_now_iso()
    assignments = ', '.join(f'"{column}" = ?' for column in updates)
    values = [updates[column] for column in updates]
    with repository.connection() as connection:
        connection.execute(
            f'UPDATE {SAVED_FILTERS_TABLE} SET {assignments} WHERE id = ?',
            (*values, int(filter_id)),
        )


# -- Export, import, transfers and backups -----------------------------------------------------------------------
# A Favourites Filter travels as the Scoring & GAP Favourites Filters element, without its result: its CDRs are named by the SHA-256 of
# their files, so the workspace that receives it finds them whatever their name or id there.

SAVED_FILTERS_FORMAT = 'drivetest-analyzer-saved-filters'
SAVED_FILTERS_VERSION = 1


def _cdr_hashes(repository: Repository) -> dict[int, dict[str, str]]:
    """The SHA-256 of the file, the name and the type of every CDR of the workspace, and of the deleted CDRs whose
    Scoring History is kept."""
    from src.modules.scoring_history import HISTORY_SOURCES_TABLE, ensure_history_tables, file_sha256
    ensure_history_tables(repository)
    hashes: dict[int, dict[str, str]] = {}
    with repository.connection() as connection:
        for row in connection.execute(
                f'SELECT dataset_id, file_sha256, name, kind FROM {HISTORY_SOURCES_TABLE} ORDER BY indexed_at').fetchall():
            if row['file_sha256']:
                hashes[int(row['dataset_id'])] = {'sha256': str(row['file_sha256']), 'name': str(row['name'] or ''),
                                                  'kind': str(row['kind'] or '')}
    for row in repository.list_datasets():
        if str(row['dataset_kind'] or '').strip().casefold() not in CDR_DATASET_KINDS:
            continue
        sha = file_sha256(repository, row)
        if sha:
            hashes[int(row['id'])] = {'sha256': sha, 'name': str(row['file_name'] or ''),
                                      'kind': str(row['dataset_kind'] or '').casefold()}
    return hashes


def saved_filters_document(repository: Repository, *, favourites_only: bool = False) -> dict[str, Any]:
    """Every Saved Filter of the workspace (``favourites_only``: the Favourites Filters, the Scoring & GAP Favourites Filters
    element of Import / Export / Transfer, workspace transfers and backups), without its result, with its CDRs named
    by their file."""
    hashes: dict[int, dict[str, str]] | None = None
    entries = []
    with repository.connection() as connection:
        rows = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE}{" WHERE pinned = 1" if favourites_only else ""} '
                                  'ORDER BY id').fetchall()
    for row in rows:
        saved_filter = _row_to_saved_filter(row, include_snapshot=False)
        refs = _decode_json(row['cdr_refs_json'], [])
        if saved_filter['dataset_ids']:
            hashes = hashes if hashes is not None else _cdr_hashes(repository)
            refs = [hashes.get(dataset_id) for dataset_id in saved_filter['dataset_ids']]
            if not all(refs):
                # Without the file of one of its CDRs, the selection could not be found again elsewhere.
                continue
        if not refs:
            continue
        entries.append({
            'name': saved_filter['name'], 'pinned': saved_filter['pinned'], 'position': saved_filter['position'],
            'use_count': saved_filter['use_count'], 'last_used_at': saved_filter['last_used_at'],
            'cdrs': refs, 'nr_mode': saved_filter['nr_mode'], 'levels': saved_filter['levels'],
            'baseline_operator': saved_filter['baseline_operator'],
            'context_filters': saved_filter['context_filters'],
            'scoring_profile_id': saved_filter['scoring_profile_id'],
            'area_summary': saved_filter['area_summary'],
        })
    return {'format': SAVED_FILTERS_FORMAT, 'version': SAVED_FILTERS_VERSION, 'saved_filters': entries}


def import_saved_filters(repository: Repository, document: Any) -> int:
    """Add the Saved Filters of a document to the workspace (those it already has keep their name, favourite and
    use). Their CDRs are found by file; until they are processed here, they wait for them. Returns how many were
    added."""
    if (not isinstance(document, dict) or document.get('format') != SAVED_FILTERS_FORMAT
            or document.get('version') != SAVED_FILTERS_VERSION or not isinstance(document.get('saved_filters'), list)):
        raise ValueError('The Saved Filters are invalid.')
    added = 0
    now = local_now_iso()
    # The starred ones follow those of the workspace, in the order of the document.
    with repository.connection() as connection:
        last = connection.execute(f'SELECT MAX(position) FROM {SAVED_FILTERS_TABLE} WHERE pinned = 1').fetchone()[0]
    next_position = int(last or 0) + 1
    entries = sorted(enumerate(document['saved_filters']), key=lambda item: (
        not (isinstance(item[1], dict) and item[1].get('pinned')),
        item[1].get('position') is None if isinstance(item[1], dict) else True,
        (item[1].get('position') or 0) if isinstance(item[1], dict) and isinstance(item[1].get('position'), int) else 0,
        item[0]))
    for _index, entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('The Saved Filters are invalid.')
        refs = [
            {'sha256': str(item.get('sha256') or ''), 'name': str(item.get('name') or ''), 'kind': str(item.get('kind') or '')}
            for item in entry.get('cdrs') or [] if isinstance(item, dict) and item.get('sha256')
        ]
        levels = [str(level) for level in entry.get('levels') or [] if str(level).strip()]
        nr_mode = normalize_nr_mode(entry.get('nr_mode'))
        if not refs or not levels or nr_mode is None:
            raise ValueError('The Saved Filters are invalid.')
        context_filters = _normalize_context_filters(entry.get('context_filters') or {})
        area_summary = entry.get('area_summary') if isinstance(entry.get('area_summary'), dict) else None
        selection = {'levels': levels, 'nr_mode': nr_mode, 'baseline_operator': str(entry.get('baseline_operator') or DEFAULT_BASELINE_OPERATOR),
                     'context_filters': context_filters, 'scoring_profile_id': str(entry.get('scoring_profile_id') or ''),
                     'area_summary': area_summary}
        pending_key = 'pending:' + hashlib.sha256(json.dumps(
            {**selection, 'cdrs': sorted(ref['sha256'] for ref in refs)}, ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode('utf-8')).hexdigest()
        snapshot = {'sources': [{'name': ref['name'], 'kind': ref['kind']} for ref in refs],
                    'scoring_profile_id': selection['scoring_profile_id'], 'context_filters': context_filters,
                    'resolved_context_filters': context_filters}
        if area_summary:
            snapshot['area_summary'] = area_summary
        with repository.connection() as connection:
            if connection.execute(f'SELECT 1 FROM {SAVED_FILTERS_TABLE} WHERE selection_key = ?', (pending_key,)).fetchone():
                continue
            connection.execute(
                f"""INSERT INTO {SAVED_FILTERS_TABLE} (
                    selection_key, name, pinned, position, use_count, last_used_at, cdr_refs_json, dataset_ids_json,
                    source_metadata_json, nr_mode, levels_json, baseline_operator, status, message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, 'saved', 'Imported; calculated when it is opened', ?, ?)""",
                (pending_key, ' '.join(str(entry.get('name') or '').split())[:120], 1 if entry.get('pinned') else 0,
                 next_position if entry.get('pinned') else None,
                 max(1, int(entry.get('use_count') or 1)), str(entry.get('last_used_at') or now),
                 json.dumps(refs, ensure_ascii=False), json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')),
                 nr_mode, json.dumps(levels, ensure_ascii=False), selection['baseline_operator'], now, now),
            )
        added += 1
        if entry.get('pinned'):
            next_position += 1
    _resolve_imported_filters(repository)
    return added


def _resolve_imported_filters(repository: Repository) -> None:
    """Give the imported Saved Filters their CDRs once every one of them is in the workspace (found by file). One
    that matches a Saved Filter of the workspace joins it."""
    with repository.connection() as connection:
        pending = connection.execute(
            f"SELECT * FROM {SAVED_FILTERS_TABLE} WHERE dataset_ids_json = '[]' AND cdr_refs_json <> '[]'"
        ).fetchall()
    if not pending:
        return
    by_hash: dict[str, int] = {}
    for row in repository.list_datasets():
        if str(row['status'] or '').casefold() != 'ready' or str(row['dataset_kind'] or '').casefold() not in CDR_DATASET_KINDS:
            continue
        from src.modules.scoring_history import ensure_history_tables, file_sha256
        ensure_history_tables(repository)
        sha = file_sha256(repository, row)
        if sha:
            by_hash.setdefault(sha, int(row['id']))
    for row in pending:
        refs = _decode_json(row['cdr_refs_json'], [])
        dataset_ids = [by_hash.get(str(ref.get('sha256') or '')) for ref in refs if isinstance(ref, dict)]
        if not dataset_ids or not all(dataset_ids):
            continue
        saved_filter = _row_to_saved_filter(row, include_snapshot=False)
        try:
            prepared = _prepare_saved_filter(
                repository, dataset_ids, saved_filter['levels'], saved_filter['nr_mode'],
                baseline_operator=saved_filter['baseline_operator'], context_filters=saved_filter['context_filters'],
                scoring_profile_id=saved_filter['scoring_profile_id'] or None, area_summary=saved_filter['area_summary'],
            )
        except ValueError:
            continue
        with repository.connection() as connection:
            existing = connection.execute(f'SELECT * FROM {SAVED_FILTERS_TABLE} WHERE selection_key = ?',
                                          (prepared['selection_key'],)).fetchone()
            if existing is not None:
                connection.execute(
                    f"UPDATE {SAVED_FILTERS_TABLE} SET name = CASE WHEN name = '' THEN ? ELSE name END, "
                    'pinned = MAX(pinned, ?), use_count = MAX(use_count, ?), '
                    # A Saved Filter of the workspace starred by the import takes the place the import gave it.
                    'position = CASE WHEN pinned = 1 AND position IS NOT NULL THEN position ELSE ? END WHERE id = ?',
                    (row['name'], row['pinned'], row['use_count'], row['position'] if row['pinned'] else None,
                     existing['id']),
                )
                connection.execute(f'DELETE FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (row['id'],))
                continue
            connection.execute(
                f"""UPDATE {SAVED_FILTERS_TABLE} SET selection_key = ?, result_key = ?, method_version = ?,
                   source_fingerprint = ?, dataset_ids_json = ?, levels_json = ?, nr_mode = ?, baseline_operator = ?,
                   source_metadata_json = ?, cdr_refs_json = '[]', message = 'Calculated when it is opened'
                   WHERE id = ?""",
                (prepared['selection_key'], prepared['result_key'], prepared['method_version'],
                 prepared['source_fingerprint'], json.dumps(prepared['dataset_ids']),
                 json.dumps(prepared['levels'], ensure_ascii=False), prepared['nr_mode'], prepared['baseline_operator'],
                 json.dumps(prepared['snapshot'], ensure_ascii=False, separators=(',', ':')), row['id']),
            )


def convert_scoring_jobs(connection: Any) -> None:
    """Turn the Scoring Jobs of a workspace saved by earlier versions into Saved Filters, once: the jobs of the same
    selection become one, with the latest result and how many times it was calculated."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'scoring_jobs'").fetchone():
        return
    rows = connection.execute('SELECT * FROM scoring_jobs ORDER BY julianday(created_at), id').fetchall()
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        snapshot = _decode_json(row['source_metadata_json'], {})
        if not isinstance(snapshot, dict):
            snapshot = {'sources': snapshot if isinstance(snapshot, list) else []}
        dataset_ids = _decode_json(row['dataset_ids_json'], [])
        levels = _decode_json(row['levels_json'], [])
        try:
            key = saved_filter_key(dataset_ids, levels, row['nr_mode'], row['baseline_operator'],
                                   snapshot.get('context_filters') or {}, snapshot.get('scoring_profile_id') or '',
                                   snapshot.get('area_summary'))
        except (TypeError, ValueError):
            continue
        status = {'ready': 'completed', 'stopped': 'failed', 'queued': 'failed', 'processing': 'failed'}.get(
            str(row['status']), str(row['status']))
        entry = merged.setdefault(key, {'use_count': 0, 'calculation_count': 0})
        entry['use_count'] += 1
        # Each completed job was a calculation of the selection.
        entry['calculation_count'] += int(status == 'completed')
        entry['last_used_at'] = row['created_at']
        # The latest calculation with a result, else the latest one.
        if row['result_json'] or not entry.get('row') or not entry['row']['result_json']:
            entry.update(row=row, status=status, snapshot=snapshot)
    for key, entry in merged.items():
        row = entry['row']
        connection.execute(
            f"""INSERT OR IGNORE INTO {SAVED_FILTERS_TABLE} (
                selection_key, use_count, calculation_count, last_used_at, result_key, method_version, source_fingerprint,
                dataset_ids_json, source_metadata_json, nr_mode, levels_json, baseline_operator, status, progress, message,
                result_json, last_error, created_by, created_at, started_at, updated_at, finished_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (key, entry['use_count'], entry['calculation_count'], entry['last_used_at'], row['cache_key'], row['method_version'],
             row['source_fingerprint'], row['dataset_ids_json'],
             json.dumps(entry['snapshot'], ensure_ascii=False, separators=(',', ':')), row['nr_mode'], row['levels_json'],
             row['baseline_operator'], entry['status'], row['progress'], row['message'], row['result_json'],
             row['last_error'], row['created_by'], row['created_at'], row['started_at'], row['updated_at'],
             row['finished_at']),
        )
    connection.execute('DROP TABLE scoring_jobs')


def _load_source_frames(
    repository: Repository, sources: list[dict[str, Any]], progress_callback, required_columns,
    context_filters: dict[str, list[str]] | None = None,
) -> dict[str, pd.DataFrame]:
    frames_by_kind: dict[str, list[pd.DataFrame]] = {}
    normalized_filters = _normalize_context_filters(context_filters)
    active_filters = {field: values for field, values in normalized_filters.items() if values}
    catalogues = repository.cdr_catalogues_by_dataset([int(source['metadata']['dataset_id']) for source in sources])
    vendor_operators = scoring_vendor_operators(catalogues, repository.list_operator_mapping_groups())
    from src.modules.map_area_columns import MAP_AREA_COLUMN, MAP_AREA_COUNTRY_COLUMN, current_datasets
    # The CDRs whose tests are placed in the current Map Areas give the map their areas.
    placed = current_datasets(repository, [int(source['metadata']['dataset_id']) for source in sources])
    total = max(1, len(sources))
    for index, source in enumerate(sources, start=1):
        dataset_id = int(source['metadata']['dataset_id'])
        if active_filters.get('Vendor'):
            repository.ensure_vendor_column(dataset_id)
        columns = repository.list_dataset_row_columns(dataset_id)
        requested = required_columns(str(source['metadata']['kind']), source['levels'])
        if dataset_id in placed:
            requested = [*requested, MAP_AREA_COLUMN, MAP_AREA_COUNTRY_COLUMN]
        if any(column_identity(level) == 'datasettype' for level in source['levels']):
            requested = [*requested, 'Dataset_Kind']
        requested = [
            'Dataset_Kind' if column_identity(name) == 'datasettype' else name
            for name in requested
        ]
        selected_columns = [
            resolved for name in requested
            if (resolved := resolve_column_name(columns, name)) is not None
        ]
        dataset_filters: dict[str, list[str]] = {}
        missing_filter_fields = []
        for field, values in active_filters.items():
            resolved_filter_column = next((
                resolved for candidate in SCORING_CONTEXT_FILTER_COLUMNS[field]
                if (resolved := resolve_column_name(columns, candidate)) is not None
            ), None)
            if resolved_filter_column is None:
                missing_filter_fields.append(field)
            else:
                if field == 'Vendor':
                    values = [scoring_vendor_name(value, vendor_operators) for value in values]
                dataset_filters[resolved_filter_column] = values
        if missing_filter_fields:
            frame = pd.DataFrame()
        else:
            frame = repository.load_dataset_rows(
                dataset_id, list(dict.fromkeys(selected_columns)), dataset_filters,
            )
        if frame.empty:
            if not active_filters:
                raise ValueError(f"Dataset '{source['metadata']['name']}' has no rows available for scoring.")
            progress_callback(10 + round(index * 45 / total), f"Skipped {source['metadata']['name']} with no matching rows")
            continue
        kind = str(source['metadata']['kind'])
        frames_by_kind.setdefault(kind, []).append(frame)
        progress_callback(10 + round(index * 45 / total), f"Loaded {source['metadata']['name']}")

    if active_filters:
        labels = {'data': 'Data', 'voice': 'Voice', 'speech': 'Speech'}
        missing_kinds = [kind for kind in ('data', 'voice', 'speech') if not frames_by_kind.get(kind)]
        if missing_kinds:
            missing_labels = ', '.join(labels[kind] for kind in missing_kinds)
            raise ValueError(
                'Scoring context filters leave no matching processed rows for every required CDR type. '
                f'Missing: {missing_labels}.'
            )
    return {
        kind: pd.concat(frames, ignore_index=True, sort=False)
        for kind, frames in frames_by_kind.items()
    }


def _attach_mapping_boundaries(repository: Repository, dataset_ids: list[int], result: dict[str, Any]) -> None:
    """Save the Clusters and Region Mapping polygons applied to the CDRs for the points-lost maps."""
    document = result.get('points_loss')
    if not isinstance(document, dict):
        return
    from src.modules.scoring_points_loss import mapping_boundaries

    rows = {int(row['id']): row for row in repository.list_datasets()}
    boundaries = {}
    for field, applied, mapping in (('Cluster', 'cluster_mapping_applied', 'cluster_mapping_dataset_id'),
                                    ('Region', 'region_mapping_applied', 'region_mapping_dataset_id')):
        mapping_ids = [rows[dataset_id][mapping] for dataset_id in dataset_ids
                       if dataset_id in rows and rows[dataset_id][applied] and rows[dataset_id][mapping]]
        mapping_row = rows.get(int(mapping_ids[-1])) if mapping_ids else None
        if mapping_row is None or not mapping_row['stored_path']:
            continue
        try:
            polygons = mapping_boundaries(Path(str(mapping_row['stored_path'])), field)
        except Exception:  # The map is optional; a missing or unreadable mapping file only drops its polygons.
            continue
        if polygons:
            boundaries[field] = polygons
    if boundaries:
        document['boundaries'] = boundaries


def calculate_saved_filter(repository: Repository, filter_id: int,
                           submit_points_loss: Callable[[Callable[[], None]], Any] | None = None) -> dict[str, Any] | None:
    """Calculate the queued result of a Saved Filter, save it, and keep a failure with its reason.

    A result from the Scoring History gets its Points Lost Map from the rows of the tests afterwards: with
    ``submit_points_loss`` as a job of its own (so the calculations waiting do not wait for it), else at once.
    """
    saved_filter = get_saved_filter(repository, filter_id, include_internal_snapshot=True)
    if saved_filter is None:
        return None
    if saved_filter['status'] == 'completed':
        return get_saved_filter(repository, filter_id, include_result=True)
    if saved_filter['status'] == 'processing':
        return saved_filter
    now = local_now_iso()
    _update_saved_filter(
        repository, filter_id, status='processing', progress=2,
        message='Checking selected CDR datasets', last_error='', started_at=now,
    )

    def update_progress(progress: int, message: str) -> None:
        if get_saved_filter(repository, filter_id) is None:
            raise _SavedFilterDeleted()
        _update_saved_filter(
            repository, filter_id, progress=max(2, min(95, int(progress))), message=message,
        )

    try:
        configuration = saved_filter.get('configuration')
        if configuration is None:
            raise ValueError(
                'This Saved Filter has no saved methodology. Import the Scoring & GAP Analysis Methodologies and calculate it again.'
            )
        current_version = _method_version(configuration)
        if current_version != saved_filter['method_version']:
            raise ValueError(
                'The scoring methodology changed after this calculation was queued. Calculate it again.')
        configuration = validate_scoring_configuration(configuration)
        dataset_ids = [int(value) for value in saved_filter['dataset_ids']]
        sources, _campaigns, current_fingerprint = _source_snapshot(
            repository, dataset_ids, expected_nr_mode=saved_filter['nr_mode'],
        )
        if current_fingerprint != saved_filter['source_fingerprint']:
            raise ValueError('A selected CDR changed after this calculation was queued. Calculate it again.')
        engine = _scoring_engine()
        context_filters = saved_filter.get('resolved_context_filters', saved_filter.get('context_filters', {}))
        groups = saved_filter.get('methodology_groups') or []
        trends = saved_filter.get('area_trends') if saved_filter.get('area_summary') else None
        # National & Geographical Areas Trends with campaigns of their own are scored apart, from the CDRs of those
        # campaigns; the Geographical Areas of the job keep their Breakdown and Separate cities.
        job_filter = ({**saved_filter, 'area_summary': None, 'geographical_areas': saved_filter.get('area_summary')}
                      if trends else saved_filter)
        if len(groups) > 1:
            # By campaign: the campaigns of each methodology are scored with it, then put together.
            from src.modules.scoring_methodologies import merge_results
            parts, map_pending = [], False
            share = 90 / len(groups)
            for index, group in enumerate(groups):
                group_configuration = validate_scoring_configuration(group['configuration'])
                group_filter = {**job_filter, 'configuration': group_configuration}

                def group_progress(progress: int, message: str, index: int = index, name: str = group['profile_name']) -> None:
                    update_progress(round(index * share + progress * share / 100), f'{name}: {message}')
                group_result, from_history = _scoring_result(
                    repository, group_filter, group_configuration, dataset_ids, [dict(source) for source in sources],
                    {**context_filters, 'Campaign': list(group['campaigns'])}, engine, group_progress)
                map_pending = map_pending or from_history
                parts.append((group, group_result))
            result = merge_results(parts)
            if map_pending:
                result['points_loss'] = {'version': 2, 'pending': True}
        else:
            result, map_pending = _scoring_result(repository, job_filter, configuration, dataset_ids, sources,
                                                  context_filters, engine, update_progress)
        if trends:
            summary = _trend_area_summary(repository, saved_filter, trends, configuration, context_filters, engine,
                                          update_progress)
            result['warnings'] = [*(result.get('warnings') or []), *summary.pop('warnings', [])]
            result['area_summary'] = summary
        _save_scoring_result(repository, saved_filter, filter_id, dataset_ids, configuration, result,
                             points_loss_pending=map_pending)
        if map_pending:
            # The Points Lost Map needs the rows of the tests: it is added once they are read.
            if submit_points_loss is None:
                complete_saved_filter_points_loss(repository, filter_id)
            else:
                queue_points_loss(repository, filter_id, submit_points_loss)
    except _SavedFilterDeleted:
        return None
    except Exception as exc:
        _fail_calculation(repository, saved_filter, filter_id, exc)
    return get_saved_filter(repository, filter_id, include_result=True)


def _trend_area_summary(repository: Repository, saved_filter: dict[str, Any], trends: dict[str, Any],
                        configuration: dict[str, Any], context_filters: dict[str, list[str]], engine: Any,
                        update_progress: Callable[[int, str], None]) -> dict[str, Any]:
    """National & Geographical Areas Trends with campaigns of their own: the CDRs of those campaigns scored with the job's filters
    (its campaigns aside) and methodology (each campaign with its own By campaign), split by Operator and Campaign."""
    area_summary = saved_filter['area_summary']
    dataset_ids = [int(value) for value in trends.get('dataset_ids') or []]
    sources, _campaigns, fingerprint = _source_snapshot(repository, dataset_ids, expected_nr_mode=saved_filter['nr_mode'])
    if fingerprint != trends.get('source_fingerprint'):
        raise ValueError('A CDR of the National & Geographical Areas Trends changed after this calculation was queued. Calculate it again.')
    # Split as the National calculation of the summary, which then reuses this one.
    levels = ['Operator'] if area_summary.get('time_split') == 'All' else ['Operator', 'Campaign']
    # Scored on the whole country, whatever the job's area filters; the Geographical views are the job's own.
    filters = {**whole_country_filters(context_filters), 'Campaign': list(trends.get('campaigns') or [])}
    trend_filter = {**saved_filter, 'dataset_ids': dataset_ids, 'levels': levels, 'source_fingerprint': fingerprint,
                    'geographical': False}

    def progress(value: int, message: str) -> None:
        update_progress(88 + round(value * 7 / 100), f'National & Geographical Areas Trends: {message}')
    groups = trends.get('methodology_groups') or []
    if len(groups) > 1:
        from src.modules.scoring_methodologies import merge_results
        parts = []
        for group in groups:
            group_configuration = validate_scoring_configuration(group['configuration'])
            part, _from_history = _scoring_result(
                repository, {**trend_filter, 'configuration': group_configuration}, group_configuration, dataset_ids,
                [dict(source) for source in sources], {**filters, 'Campaign': list(group['campaigns'])}, engine, progress)
            parts.append((group, detach_area_summary(part)))
        result = merge_results(parts)
        summary = result.get('area_summary') or {}
        summary['methodology_groups'] = result.get('methodology_groups')
    else:
        trend_configuration = (validate_scoring_configuration(trends['configuration']) if trends.get('configuration')
                               else configuration)
        result, _from_history = _scoring_result(repository, trend_filter, trend_configuration, dataset_ids, sources,
                                                filters, engine, progress)
        summary = detach_area_summary(result).get('area_summary') or {}
    summary = {'breakdown': area_summary.get('breakdown'), 'cities': list(area_summary.get('cities') or []),
               'time_split': area_summary.get('time_split') or 'Campaign', 'passes': [], **summary}
    # The warnings of the summary join those of the job (its other warnings repeat the job's).
    summary['warnings'] = [warning for warning in result.get('warnings') or []
                           if any(prefix in str(warning) for prefix in WARNING_PREFIXES)]
    # Its campaigns and methodology, which the views of its calculations use instead of the job's.
    summary['campaigns'] = list(trends.get('campaigns') or [])
    if trends.get('configuration'):
        summary['configuration'] = trends['configuration']
    return summary


def _scoring_result(repository: Repository, saved_filter: dict[str, Any], configuration: dict[str, Any],
                    dataset_ids: list[int], sources: list[dict[str, Any]], context_filters: dict[str, list[str]],
                    engine: Any, update_progress: Callable[[int, str], None]) -> tuple[dict[str, Any], bool]:
    """The scoring (and area summary) of a Saved Filter with one methodology, and whether it came from the Scoring
    History (its Points Lost Map then follows from the rows of the tests)."""
    result = _history_result(repository, saved_filter, configuration, dataset_ids, context_filters, engine,
                             update_progress)
    if result is not None:
        return result, True
    if saved_filter.get('history_gap'):
        # Every step says why the rows of the CDRs are read (and the Scoring History not used).
        reason = saved_filter['history_gap']
        report = update_progress
        update_progress = lambda progress, message: report(progress, f'{message} (from the CDR rows: {reason})')
    update_progress(6, 'Reading processed CDR rows')
    # The points-lost map also reads the area and coordinate columns.
    required_columns = getattr(engine, 'load_input_columns', None) or getattr(engine, 'required_input_columns')
    # The area summary also reads its breakdown and City columns, and the test start time for its time split; the
    # Geographical views read those of their Breakdown and Separate cities.
    extra = area_summary_levels(saved_filter['levels'], saved_filter.get('area_summary'))
    if saved_filter.get('geographical', True):
        extra = [*extra, *(level for level in geographical_levels(saved_filter['levels'], _geographical_areas(saved_filter))
                           if level not in extra)]
    for source in sources:
        source['levels'] = [*saved_filter['levels'], *extra]
    frames = _load_source_frames(repository, sources, update_progress, required_columns, context_filters)
    _current_sources, _campaigns, post_load_fingerprint = _source_snapshot(
        repository, dataset_ids, expected_nr_mode=saved_filter['nr_mode'],
    )
    if post_load_fingerprint != saved_filter['source_fingerprint']:
        raise ValueError('A selected CDR changed while its scoring rows were being loaded.')
    update_progress(62, 'Calculating KPIs and interpolated scores')
    calculate = engine.calculate_scoring
    call_kwargs = _engine_kwargs(repository, saved_filter, configuration, calculate)
    result = calculate(frames, saved_filter['levels'], **call_kwargs)
    if not isinstance(result, dict):
        raise TypeError('The scoring engine must return a result object.')
    job_filtered = has_area_filters(context_filters)
    # The Geographical Areas & Scoring Trends are scored on the whole country: a job with area filters reads its rows apart.
    country_frames = frames
    if job_filtered and (saved_filter.get('area_summary') or saved_filter.get('geographical', True)):
        update_progress(87, 'Reading the CDR rows of the whole country for the Geographical Areas & Scoring Trends')
        country_frames = _load_source_frames(repository, [dict(source) for source in sources], lambda *_args: None,
                                             required_columns, whole_country_filters(context_filters))
    if saved_filter.get('area_summary'):
        summary = calculate_area_summary(calculate, country_frames, saved_filter['levels'],
                                         saved_filter['area_summary'], call_kwargs, update_progress, job_filtered=job_filtered)
        result['warnings'] = [*(result.get('warnings') or []), *summary.pop('warnings')]
        result['area_summary'] = summary
    if saved_filter.get('geographical', True):
        # Its Breakdown and Separate cities on the whole country: those equal to the job's own calculation or to one of
        # the summary (the same rows) are read from them.
        geographical = calculate_geographical(calculate, country_frames, saved_filter['levels'], call_kwargs, update_progress,
                                              result.get('area_summary'), _geographical_areas(saved_filter),
                                              reuse_job=not job_filtered)
        if geographical:
            result['geographical'] = geographical
    return result, False


def _geographical_areas(saved_filter: dict[str, Any]) -> dict[str, Any] | None:
    """The Breakdown and Separate cities of the Geographical Areas & Scoring Trends of a Saved Filter (those of the job
    when its trends, with campaigns of their own, are scored apart)."""
    areas = saved_filter.get('geographical_areas') or saved_filter.get('area_summary')
    return areas if isinstance(areas, dict) else None


def _engine_kwargs(repository: Repository, saved_filter: dict[str, Any], configuration: dict[str, Any],
                   calculate: Callable[..., Any]) -> dict[str, Any]:
    """The options of the engine's calculation: reference, methodology, operator names and Map Areas."""
    parameters = inspect.signature(calculate).parameters
    call_kwargs = {
        'baseline_operator': saved_filter['baseline_operator'],
        'configuration': configuration,
    }
    accepts_keywords = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    if 'operator_mappings' in parameters or accepts_keywords:
        call_kwargs['operator_mappings'] = saved_filter.get('operator_mappings', {})
    if 'baseline_aliases' in parameters or accepts_keywords:
        call_kwargs['baseline_aliases'] = saved_filter.get('baseline_aliases', [])
    if 'map_areas' in parameters:
        # The tests are placed in the workspace's Map Areas of their country (the ITL3 areas in the UK).
        from src.modules.map_areas import area_index
        call_kwargs['map_areas'] = area_index(repository)
    return call_kwargs


def _history_result(repository: Repository, saved_filter: dict[str, Any], configuration: dict[str, Any], dataset_ids: list[int],
                    context_filters: dict[str, list[str]], engine: Any, update_progress) -> dict[str, Any] | None:
    """The scoring (and area summary) of the saved_filter from the Scoring History when it holds every selected CDR at its
    current revision with every KPI of the methodology, and the split and filters are its dimensions; else None."""
    from src.modules import scoring as scoring_engine
    from src.modules.scoring_history import HistoryUnavailable, calculate_scoring_from_history, history_gap

    if engine is not scoring_engine:
        return None
    update_progress(4, f'Checking the Scoring History of the {len(dataset_ids)} CDRs')
    # Why the rows of the CDRs are read instead, told while they are read.
    saved_filter['history_gap'] = history_gap(repository, dataset_ids, saved_filter['levels'], configuration,
                                              context_filters)
    if saved_filter['history_gap']:
        return None
    update_progress(20, 'Calculating from the Scoring History')
    catalogues = repository.cdr_catalogues_by_dataset(dataset_ids)
    options = {
        'baseline_operator': saved_filter['baseline_operator'], 'configuration': configuration,
        'baseline_aliases': saved_filter.get('baseline_aliases', []), 'operator_mappings': saved_filter.get('operator_mappings', {}),
        'context_filters': context_filters,
        'vendor_operators': scoring_vendor_operators(catalogues, repository.list_operator_mapping_groups()),
    }
    try:
        result = calculate_scoring_from_history(repository, dataset_ids, saved_filter['levels'], **options)
        job_filtered = has_area_filters(context_filters)
        if saved_filter.get('area_summary'):
            # The summary is scored on the whole country, whatever the job's area filters.
            summary_options = {**options, 'context_filters': whole_country_filters(context_filters)}

            def calculate(levels: list[str], *, time_split: str | None = None, cities=None) -> dict[str, Any]:
                return calculate_scoring_from_history(repository, dataset_ids, levels, time_split=time_split,
                                                      cities=cities, **summary_options)
            summary = calculate_area_summary_from_history(calculate, saved_filter['levels'], saved_filter['area_summary'],
                                                          update_progress, job_filtered=job_filtered)
            result['warnings'] = [*(result.get('warnings') or []), *summary.pop('warnings')]
            result['area_summary'] = summary
        if saved_filter.get('geographical', True):
            # Its Breakdown and Separate cities on the whole country: those equal to the job's own calculation or to one
            # of the summary are read from them.
            country_options = {**options, 'context_filters': whole_country_filters(context_filters)}
            geographical = calculate_geographical_from_history(
                lambda levels, *, cities=None: calculate_scoring_from_history(repository, dataset_ids, levels, cities=cities,
                                                                              **country_options),
                saved_filter['levels'], update_progress, result.get('area_summary'), _geographical_areas(saved_filter),
                reuse_job=not job_filtered)
            if geographical:
                result['geographical'] = geographical
    except HistoryUnavailable:
        return None
    result['points_loss'] = {'version': 2, 'pending': True}
    return result


# The Points Lost Maps waiting or being drawn, per workspace database and Saved Filter, for the background tasks card.
_points_loss_jobs: dict[tuple[str, int], dict[str, Any]] = {}
_points_loss_guard = threading.Lock()


def _points_loss_key(database_path: Any, filter_id: int) -> tuple[str, int]:
    return str(Path(database_path).resolve()), int(filter_id)


def queue_points_loss(repository: Repository, filter_id: int, submit: Callable[[Callable[[], None]], Any]) -> None:
    """Queue the Points Lost Map of a result calculated from the Scoring History as a job of its own."""
    with _points_loss_guard:
        _points_loss_jobs[_points_loss_key(repository.db_path, filter_id)] = {
            'status': 'queued', 'queued_at': time.time(), 'started_at': None}
    submit(partial(complete_saved_filter_points_loss, repository, int(filter_id)))


def complete_saved_filter_points_loss(repository: Repository, filter_id: int) -> None:
    """Read the rows of the tests of a Saved Filter and add its Points Lost Map to its saved result."""
    key = _points_loss_key(repository.db_path, filter_id)
    with _points_loss_guard:
        if key in _points_loss_jobs:
            _points_loss_jobs[key].update(status='processing', started_at=time.time(), progress=0,
                                          detail='Reading the rows of the tests')

    def report(progress: float, detail: str) -> None:
        with _points_loss_guard:
            if key in _points_loss_jobs:
                _points_loss_jobs[key].update(progress=max(0.0, min(99.0, float(progress))), detail=detail)
    try:
        saved_filter = get_saved_filter(repository, filter_id, include_internal_snapshot=True)
        if saved_filter is None or not saved_filter.get('configuration'):
            return
        configuration = validate_scoring_configuration(saved_filter['configuration'])
        dataset_ids = [int(value) for value in saved_filter['dataset_ids']]
        context_filters = saved_filter.get('resolved_context_filters', saved_filter.get('context_filters', {}))
        try:
            sources, _campaigns, _fingerprint = _source_snapshot(repository, dataset_ids,
                                                                 expected_nr_mode=saved_filter['nr_mode'])
        except ValueError:
            sources = []
        _complete_points_loss(repository, saved_filter, filter_id, sources, dataset_ids, configuration, context_filters,
                              _scoring_engine(), saved_filter.get('methodology_groups') or [], report)
    finally:
        with _points_loss_guard:
            _points_loss_jobs.pop(key, None)


def points_loss_tasks(database_path: Any) -> list[dict[str, Any]]:
    """The Points Lost Maps of a workspace waiting or being drawn, as background task cards."""
    workspace = str(Path(database_path).resolve())
    with _points_loss_guard:
        jobs = [(filter_id, dict(job)) for (path, filter_id), job in _points_loss_jobs.items() if path == workspace]
    return [{
        'id': f'saved-filter-map:{filter_id}', 'label': f'Points Lost Map #{filter_id}',
        'detail': (_points_loss_detail(job) if job['status'] == 'processing'
                   else 'Waiting for the calculations before it'),
        'status': job['status'], 'progress': job.get('progress') if job['status'] == 'processing' else None,
        'queued_at': job['queued_at'], 'started_at': job['started_at'], 'completed_at': None,
    } for filter_id, job in sorted(jobs)]


def _points_loss_detail(job: dict[str, Any]) -> str:
    """The step of a Points Lost Map being drawn and, once it has advanced enough to tell, about how long it has left."""
    detail = str(job.get('detail') or 'Reading the rows of the tests')
    progress = float(job.get('progress') or 0)
    started = job.get('started_at')
    if progress < 5 or not started:
        return detail
    remaining = (time.time() - float(started)) * (100 - progress) / progress
    left = 'less than a minute left' if remaining < 60 else f'about {round(remaining / 60)} min left'
    return f'{detail} · {left}'


def is_saved_filter_work(task_callback: Any, task_args: tuple[Any, ...], filter_id: int) -> bool:
    """Whether a queued job calculates the given Saved Filter or draws its Points Lost Map."""
    if task_callback is calculate_saved_filter:
        return len(task_args) > 1 and int(task_args[1]) == int(filter_id)
    return (isinstance(task_callback, partial) and task_callback.func is complete_saved_filter_points_loss
            and int(task_callback.args[1]) == int(filter_id))


def _points_loss_of(repository: Repository, saved_filter: dict[str, Any], sources: list[dict[str, Any]],
                    configuration: dict[str, Any], context_filters: dict[str, list[str]], engine: Any,
                    progress: Callable[[float, str], None] = lambda *_args: None) -> Any:
    """The Points Lost Map of a Saved Filter with one methodology, from the rows of its tests.

    ``progress`` (0-100 and the step) follows the CDRs read (the first 45%) and the groups of tests mapped.
    """
    for source in sources:
        source['levels'] = list(saved_filter['levels'])
    required_columns = getattr(engine, 'load_input_columns', None) or getattr(engine, 'required_input_columns')
    total = max(1, len(sources))
    read = 0

    def cdr_read(*_args: Any) -> None:
        nonlocal read
        read += 1
        progress(read * 45 / total, f'Reading the rows of the tests: CDR {min(read + 1, total)} of {total}'
                 if read < total else 'Mapping the tests')

    progress(0, f'Reading the rows of the tests: CDR 1 of {total}')
    frames = _load_source_frames(repository, sources, cdr_read, required_columns, context_filters)
    calculate = engine.calculate_scoring
    options = _engine_kwargs(repository, saved_filter, configuration, calculate)
    if hasattr(engine, 'calculate_points_loss'):
        # Only the map: the scores are already saved.
        extra = ({'progress_callback': lambda share, step: progress(45 + share * 55, step)}
                 if 'progress_callback' in inspect.signature(engine.calculate_points_loss).parameters else {})
        return engine.calculate_points_loss(
            frames, saved_filter['levels'], configuration=configuration,
            operator_mappings=options.get('operator_mappings'), map_areas=options.get('map_areas'), **extra)
    return calculate(frames, saved_filter['levels'], **options)['points_loss']


def _complete_points_loss(repository: Repository, saved_filter: dict[str, Any], filter_id: int, sources: list[dict[str, Any]],
                          dataset_ids: list[int], configuration: dict[str, Any],
                          context_filters: dict[str, list[str]], engine: Any,
                          groups: list[dict[str, Any]] | None = None,
                          progress: Callable[[float, str], None] = lambda *_args: None) -> None:
    """Read the rows of the tests and add the Points Lost Map to a result calculated from the Scoring History (By
    campaign, the map of the campaigns of each methodology with it, each in its share of ``progress``)."""
    try:
        if groups and len(groups) > 1:
            from src.modules.scoring_methodologies import _merge_points_loss
            maps = []
            for index, group in enumerate(groups):
                name = group.get('profile_name') or 'Methodology'

                def group_progress(value: float, step: str, index: int = index, name: str = name) -> None:
                    progress((index + value / 100) * 97 / len(groups),
                             f'Methodology {index + 1} of {len(groups)} ({name}): {step}')
                maps.append(_points_loss_of(repository, saved_filter, [dict(source) for source in sources],
                                            validate_scoring_configuration(group['configuration']),
                                            {**context_filters, 'Campaign': list(group['campaigns'])}, engine,
                                            group_progress))
            points_loss = _merge_points_loss(maps)
        else:
            points_loss = _points_loss_of(repository, saved_filter, sources, configuration, context_filters, engine,
                                          lambda value, step: progress(value * 0.97, step))
        progress(97, 'Adding the area boundaries')
        document = {'points_loss': points_loss}
        _attach_mapping_boundaries(repository, dataset_ids, document)
        progress(99, 'Saving the map')
    except Exception as exc:  # The scores stay; only the map is missing.
        document = {'points_loss': {'version': 2, 'error': str(exc)}}
    with repository.connection() as connection:
        row = connection.execute(f'SELECT status, result_json FROM {SAVED_FILTERS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
    if row is None or row['status'] != 'completed' or not row['result_json']:
        return
    result = json.loads(row['result_json'])
    if not (isinstance(result.get('points_loss'), dict) and result['points_loss'].get('pending')):
        return
    result['points_loss'] = _serialize_result_value(document['points_loss'])
    _update_saved_filter(repository, filter_id, result_json=json.dumps(result, ensure_ascii=False, separators=(',', ':'),
                                                                   allow_nan=False),
                        message='Scoring tables, GAP analysis and Points Lost Map are ready')


def _save_scoring_result(repository: Repository, saved_filter: dict[str, Any], filter_id: int, dataset_ids: list[int],
                         configuration: dict[str, Any], result: dict[str, Any], *, points_loss_pending: bool = False) -> None:
    """Store the result of a calculation once the selected CDRs are checked unchanged."""
    if not isinstance(result, dict):
        raise TypeError('The scoring engine must return a result object.')
    _attach_mapping_boundaries(repository, dataset_ids, result)
    result.setdefault('configuration', configuration)
    result.setdefault('configuration_hash', configuration_hash(configuration))
    result.setdefault('gap_direction', 'operator_minus_reference')
    result.setdefault('baseline_aliases', saved_filter.get('baseline_aliases', []))
    result.setdefault('aggregation_levels', saved_filter['levels'])
    result.setdefault('aggregation_contract_version', saved_filter['aggregation_contract_version'])
    result.setdefault('campaigns', saved_filter['campaigns'])
    _latest_sources, _latest_campaigns, final_fingerprint = _source_snapshot(
        repository, dataset_ids, expected_nr_mode=saved_filter['nr_mode'],
    )
    if final_fingerprint != saved_filter['source_fingerprint']:
        raise ValueError('A selected CDR changed while its scoring calculation was running.')
    result_payload = {
        'scoring': result.get('scoring', []),
        'gap': result.get('gap', []),
        'charts': result.get('charts', []),
        'warnings': result.get('warnings', []),
        **{key: value for key, value in result.items() if key not in {'scoring', 'gap', 'charts', 'warnings'}},
    }
    encoded_result = json.dumps(
        _serialize_result_value(result_payload), ensure_ascii=False, separators=(',', ':'), allow_nan=False,
    )
    _update_saved_filter(
        repository, filter_id, status='completed', progress=100,
        message=('Scoring tables and GAP analysis are ready; preparing the Points Lost Map' if points_loss_pending
                 else 'Scoring tables and GAP analysis are ready'),
        result_json=encoded_result, last_error='', finished_at=local_now_iso(),
    )
    # How many times its result has been calculated, beside how many times it has been used.
    with repository.connection() as connection:
        connection.execute(f'UPDATE {SAVED_FILTERS_TABLE} SET calculation_count = calculation_count + 1 WHERE id = ?',
                           (int(filter_id),))


def _fail_calculation(repository: Repository, saved_filter: dict[str, Any], filter_id: int, exc: Exception) -> None:
    """Keep a failed calculation with its reason, for review."""
    _update_saved_filter(
        repository, filter_id, status='failed', progress=100,
        message='Scoring calculation failed', last_error=str(exc), finished_at=local_now_iso(),
    )
    # App Logs show why a calculation failed, with where it happened.
    if hasattr(repository, 'try_add_log'):
        import traceback
        repository.try_add_log(str(saved_filter.get('created_by') or 'system'), 'scoring_calculation_failed', json.dumps({
            'filter_id': filter_id, 'error': f'{type(exc).__name__}: {exc}',
            'location': ''.join(traceback.format_exception(exc)[-3:]).strip()[-1500:],
        }, ensure_ascii=False))
