"""Saved Scorings of Scoring & GAP Analysis: every selection used (CDRs, filters, Split by, GAP reference,
methodology and National & area summary), reusable, with its result calculated in the background and saved until
its CDRs, methodology or Operator Maps change."""

from __future__ import annotations

import copy
import hashlib
import importlib
import inspect
import itertools
import json
import math
import os
import threading
import time
from datetime import date, datetime
from functools import partial
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

from src.modules.network import postal_areas
from src.modules.cdr.column_names import campaign_sort_key, column_identity, resolve_column_name
from src.modules.scoring.scoring_area_summary import (
    WARNING_PREFIXES, area_summary_levels, area_summary_part_enabled, country_area_summary, trend_area_summary, calculate_area_summary, calculate_area_summary_from_history,
    calculate_geographical, calculate_geographical_from_history, geographical_levels, has_area_filters,
    whole_country_filters,
    detach_area_summary, normalize_area_summary_request, resolve_main_cities, with_breakdown_cities,
)
from src.modules.scoring.scoring_vendors import scoring_vendor_name, scoring_vendor_operators
from src.modules.scoring.scoring_nns_breakdown import KEY as NNS_KEY, VERSION as NNS_VERSION, requested as requested_nns_breakdown
from src.modules.cdr.cdr_auto_selection import CAMPAIGN_PRESET_LABELS, campaign_identity, campaign_presets
from src.modules.cdr.value_patterns import ValueSet
from src.modules.mapping.operator_roles import EXCLUDE, normalize_mapping_role, out_of_scope_operators
from src.modules.cdr.cdr_stage import combined_dataset_ids, remembered_inclusion
from src.modules.cdr.nr_mode import (
    NR_MODE_COLUMN, NSA_VS_SA, SAME_OPERATOR_NSA, SAME_OPERATOR_NSA_LABEL, SCORING_NR_MODES, campaign_with_nr_mode,
    normalize_nr_mode, normalize_scoring_nr_mode, nr_mode_label, nr_modes_of,
)
from src.modules.core.repository import Repository, local_now_iso
from src.modules.scoring.scoring_config import (
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
SAVED_SCORINGS_TABLE = 'saved_scorings'
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
    return importlib.import_module('src.modules.scoring.scoring')


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
    """Include mapped Operator aliases so canonical selections match raw CDR rows; a pattern (VF*) takes the aliases of
    the operators it matches too, an exclusion (-Lebara) leaves out their aliases too, and both stay to match the raw
    values of no Operator Map. The operators the Operator Maps exclude are left out whatever the selection."""
    expanded = {field: list(values) for field, values in context_filters.items()}
    expanded.setdefault('Operator', [])
    selected = ValueSet(expanded.get('Operator', []))
    getter = getattr(repository, 'list_operator_mapping_groups', None)
    groups = getter() if callable(getter) else []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        canonical = str(group.get('canonical') or '').strip()
        raw_aliases = group.get('aliases', [])
        aliases = [str(value).strip() for value in raw_aliases if str(value).strip()] if isinstance(raw_aliases, (list, tuple, set)) else []
        labels = [value for value in [canonical, *aliases] if value]
        if selected.excludes(labels) or normalize_mapping_role(group.get('role')) == EXCLUDE:
            for value in labels:
                if not any(existing.casefold() == f'-{value}'.casefold() for existing in expanded['Operator']):
                    expanded['Operator'].append(f'-{value}')
            continue
        if selected.includes and selected.accepts(labels):
            for value in labels:
                if not any(existing.casefold() == value.casefold() for existing in expanded['Operator']):
                    expanded['Operator'].append(value)
    expanded['Operator'].sort(key=lambda value: (value.casefold(), value))
    return expanded


def _expand_vendor_context_filters(
    repository: Repository, context_filters: dict[str, list[str]], catalogues: dict[int, dict[str, list[str]]],
) -> dict[str, list[str]]:
    """Include the source spellings of mapped Vendor and Operator_Vendor selections, as for Operators."""
    from src.modules.mapping.value_maps import ValueMapper

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
    all_datasets = repository.list_datasets()
    datasets_by_id = {
        int(row['id']): row for row in all_datasets
        if int(row['id']) in requested_id_set
    }
    from src.modules.scoring.scoring_exclusions import load_scope
    exclusions = load_scope(repository, all_datasets)
    missing = [dataset_id for dataset_id in requested_ids if dataset_id not in datasets_by_id]
    if missing:
        raise ValueError(f"Selected CDR dataset(s) no longer exist: {', '.join(map(str, missing))}.")

    expected_mode = normalize_scoring_nr_mode(expected_nr_mode) if expected_nr_mode else None
    if expected_nr_mode and expected_mode is None:
        raise ValueError('NR Mode must be NSA, SA or NSA vs SA.')
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
        if expected_mode and nr_mode not in nr_modes_of(expected_mode):
            raise ValueError(f"Dataset '{row['file_name']}' does not match the selected {nr_mode_label(expected_mode)} NR Mode.")
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
        # The Excluded Calls lists that leave calls of it out (a CDR they do not touch keeps its scorings).
        if excluded_calls := exclusions.signature(dataset_id):
            signature['excluded_calls'] = excluded_calls
        # The operators out of scope in its NR Mode (a CDR whose NR Mode has none keeps its scorings).
        if out_of_scope := sorted(name.casefold() for name in out_of_scope_operators(repository, nr_mode)):
            signature['out_of_scope'] = out_of_scope
        sources.append({'metadata': metadata, 'signature': signature, 'columns': columns, 'table_name': table_name})

    modes = {str(source['metadata']['nr_mode']) for source in sources}
    # NSA vs SA scores the CDRs of both NR Modes, each campaign with its NR Mode.
    if len(modes) != 1 and expected_mode != NSA_VS_SA:
        raise ValueError('Select CDR datasets with the same NR Mode.')
    if expected_mode and not modes <= set(nr_modes_of(expected_mode)):
        raise ValueError(f'Selected CDR datasets do not all match {nr_mode_label(expected_mode)}.')
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
    # NSA vs SA: each campaign of each NR Mode needs the three types.
    both_modes = normalize_scoring_nr_mode(nr_mode) == NSA_VS_SA
    scored: dict[str, set[str]] = {}
    for source in sources:
        metadata = source['metadata']
        for campaign in metadata.get('campaigns', []):
            text = str(campaign).strip()
            if text:
                key = str(campaign_with_nr_mode(text, metadata['nr_mode'])) if both_modes else text
                campaigns_by_kind[str(metadata['kind'])].add(key)
                scored.setdefault(text.casefold(), set()).add(key)
    selected_campaigns = normalized_filters['Campaign']
    if selected_campaigns and both_modes:
        campaigns_to_check = list(dict.fromkeys(
            key for value in selected_campaigns for key in sorted(scored.get(value.casefold()) or {value})))
    elif selected_campaigns:
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
            raise ValueError(f"Break down by level '{requested}' is not available in the selected CDR datasets.")
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


def saved_scoring_key(
    dataset_ids: Iterable[int], levels: Iterable[str], nr_mode: str, baseline_operator: str,
    context_filters: dict[str, list[str]] | None, scoring_profile_id: str, area_summary: dict[str, Any] | None,
) -> str:
    """The identity of a selection: its CDRs, Split by, NR Mode, GAP reference, filters, methodology and National &
    area summary. The same selection is one Saved Scoring, whatever its CDRs or methodology hold today, and whatever map of
    its Postal Codes it uses: another one replaces its result."""
    area_summary = {key: value for key, value in (area_summary or {}).items() if key != 'postal_map'}
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
    # Without filters, the operators the Operator Maps exclude still change what is scored.
    if any(normalized_filters.values()) or any(resolved_filters.values()):
        key_payload['context_filters'] = _context_filter_cache_values(normalized_filters)
        key_payload['resolved_context_filters'] = _context_filter_cache_values(resolved_filters)
    canonical = json.dumps(key_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest(), canonical


def _row_to_saved_scoring(
    row: Any, *, include_result: bool = False, include_snapshot: bool = True,
    include_internal_snapshot: bool = False,
) -> dict[str, Any]:
    if row is None:
        raise ValueError('The Saved Scoring was not found.')
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
    saved_scoring = {
        'id': int(row['id']),
        'selection_key': str(row['selection_key'] or ''),
        'name': str(row['name'] or ''),
        'pinned': bool(row['pinned']),
        # The place of a starred Saved Scoring in its list (moved by dragging it), None for the others.
        'position': row['position'] if 'position' in row.keys() else None,
        'use_count': max(1, int(row['use_count'] or 1)),
        'calculation_count': max(0, int(row['calculation_count'] or 0)),
        'last_used_at': str(row['last_used_at'] or ''),
        'result_key': str(row['result_key'] or ''),
        'method_version': str(row['method_version'] or ''),
        'source_fingerprint': str(row['source_fingerprint'] or ''),
        'dataset_ids': [int(value) for value in dataset_ids if str(value).strip().lstrip('-').isdigit()],
        # The CDRs of a Saved Scoring imported from another workspace until they are found here (by file).
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
        saved_scoring['configuration'] = configuration
        saved_scoring['baseline_aliases'] = baseline_aliases
    if include_internal_snapshot:
        saved_scoring['resolved_context_filters'] = {
            str(field): [str(value) for value in values if str(value).strip()]
            for field, values in resolved_context_filters.items()
            if isinstance(values, (list, tuple, set))
        }
        saved_scoring['operator_mappings'] = {
            str(alias).strip().casefold(): str(canonical).strip()
            for alias, canonical in operator_mappings.items()
            if str(alias).strip() and str(canonical).strip()
        }
        groups = source_metadata_payload.get('methodology_groups')
        saved_scoring['methodology_groups'] = groups if isinstance(groups, list) else []
        trends = source_metadata_payload.get('area_trends')
        saved_scoring['area_trends'] = trends if isinstance(trends, dict) else None
        nns = source_metadata_payload.get('nns_sources')
        saved_scoring['nns_sources'] = nns if isinstance(nns, dict) else None
        saved_scoring['complete_from'] = source_metadata_payload.get('complete_from')
    return saved_scoring


def _shared(cache: dict[Any, Any] | None, key: Any, compute: Callable[[], Any]) -> Any:
    """``compute()``, done once for all the Saved Scorings prepared together (``cache``: those of one import or listing),
    each one with its own copy of the result."""
    if cache is None:
        return compute()
    if key not in cache:
        cache[key] = compute()
    return copy.deepcopy(cache[key])


def _prepare_saved_scoring(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """_prepare_saved_scoring_once with the inclusion of the CDRs in the combined tables worked out once: its campaign
    choices, trends and sources each asked for it, a dozen times on every check of a Favourite Scoring (ticket #168)."""
    with remembered_inclusion():
        return _prepare_saved_scoring_once(*args, **kwargs)


def _prepare_saved_scoring_once(
    repository: Repository,
    dataset_ids: list[int],
    levels: list[str],
    nr_mode: str | None,
    *,
    baseline_operator: str = DEFAULT_BASELINE_OPERATOR,
    context_filters: dict[str, list[str]] | None = None,
    scoring_profile_id: str | None = None,
    area_summary: dict[str, Any] | None = None,
    cache: dict[Any, Any] | None = None,
) -> dict[str, Any]:
    """The identity of a selection and of its result today, with the snapshot its calculation uses.

    A Campaign filter with an automatic choice (Latest campaign, Previous campaign, Latest 2 campaigns or All available
    campaigns) is kept as such: the selection is that choice, and its campaigns and CDRs are those it stands for now,
    so the Saved Scoring follows the campaigns and CDRs that arrive later. Saved Scorings prepared together share
    ``cache``, where what they read alike (methodologies, CDRs, catalogues, campaigns, Operator Maps) is read once.
    """
    normalized_context_filters = _normalize_context_filters(context_filters)
    campaign_choice = (campaign_presets(normalized_context_filters['Campaign']) or [''])[0]
    calculation_filters = dict(normalized_context_filters)
    if campaign_choice:
        from src.modules.scoring.scoring_selection import auto_scoring_cdr_ids, expand_scoring_campaigns
        mode = normalize_scoring_nr_mode(nr_mode) or 'NSA'
        normalized_context_filters['Campaign'] = [campaign_choice]
        calculation_filters['Campaign'], dataset_ids = _shared(cache, ('campaign choice', mode, campaign_choice), lambda: (
            expand_scoring_campaigns(repository, mode, [campaign_choice]), auto_scoring_cdr_ids(repository, mode, [campaign_choice])))
        if not dataset_ids:
            raise ValueError(f'{CAMPAIGN_PRESET_LABELS[campaign_choice]} stands for no campaign with Data, Voice and Speech '
                             f'CDRs of {nr_mode_label(mode)} now.')
    normalized_ids = list(dict.fromkeys(int(dataset_id) for dataset_id in dataset_ids))
    normalized_area_summary = normalize_area_summary_request(area_summary, normalized_context_filters)
    vendor_catalogues = _shared(cache, ('catalogues', tuple(normalized_ids)),
                                lambda: repository.cdr_catalogues_by_dataset(normalized_ids))
    vendor_operators = scoring_vendor_operators(vendor_catalogues, _shared(
        cache, ('operator mapping groups',), repository.list_operator_mapping_groups))
    normalized_context_filters['Vendor'] = calculation_filters['Vendor'] = sorted({
        scoring_vendor_name(value, vendor_operators) for value in normalized_context_filters['Vendor']
    }, key=str.casefold)
    resolved_context_filters = _expand_operator_context_filter(repository, calculation_filters)
    resolved_context_filters = _expand_vendor_context_filters(repository, resolved_context_filters, vendor_catalogues)
    from src.modules.scoring.scoring_methodologies import (
        BY_CAMPAIGN, display_configuration, methodology_groups, methodology_label,
    )
    sources, _campaigns, source_fingerprint = _shared(cache, ('sources', tuple(normalized_ids), nr_mode), lambda: _source_snapshot(
        repository, normalized_ids, expected_nr_mode=nr_mode,
    ))
    aggregation_hierarchy = _shared(cache, ('aggregation hierarchy',), lambda: load_aggregation_hierarchy(repository))
    both_modes = normalize_scoring_nr_mode(nr_mode) == NSA_VS_SA
    if both_modes:
        # NSA vs SA compares the campaigns of each NR Mode: it is always split by Campaign.
        levels = [*levels, *([] if any(column_identity(level) == 'campaign' for level in levels) else ['Campaign'])]
        _check_nsa_vs_sa(sources, normalized_area_summary)
    normalized_levels = _normalize_levels(levels, sources, aggregation_hierarchy)
    groups: list[dict[str, Any]] = []
    profile_getter = getattr(repository, 'get_scoring_profile', None)
    if scoring_profile_id == BY_CAMPAIGN:
        # Each campaign with the methodology that applies to it (the default one when none does).
        wanted = {value.casefold() for value in calculation_filters.get('Campaign') or []}
        campaigns = [campaign for source in sources for campaign in source['metadata'].get('campaigns') or []
                     if not wanted or campaign.casefold() in wanted]
        groups = methodology_groups(_shared(cache, ('profiles',), repository.get_scoring_profiles), campaigns or [''])
        if len(groups) > 1 and 'Campaign' not in normalized_levels:
            raise ValueError('Scoring By campaign with campaigns of different methodologies needs Campaign in the Break down by.')
        configuration_key = ('by campaign', tuple((group['profile_id'], tuple(group['campaigns'])) for group in groups))
        configuration = _shared(cache, configuration_key, lambda: validate_scoring_configuration(
            groups[0]['configuration'] if len(groups) == 1 else display_configuration(groups)))
        scoring_profile = {'id': BY_CAMPAIGN, 'name': methodology_label(groups)}
    elif callable(profile_getter):
        if scoring_profile_id is None or (
            isinstance(scoring_profile_id, str) and not scoring_profile_id.strip()
        ):
            scoring_profile = _shared(cache, ('profile', ''), profile_getter)
        else:
            if not isinstance(scoring_profile_id, str):
                raise ValueError('Scoring methodology ID must be a non-empty identifier.')
            scoring_profile = _shared(cache, ('profile', scoring_profile_id.strip()), lambda: profile_getter(scoring_profile_id.strip()))
        configuration_key = ('configuration', str(scoring_profile.get('id') or ''))
        configuration = _shared(cache, configuration_key, lambda: validate_scoring_configuration(scoring_profile['configuration']))
    else:
        if scoring_profile_id is not None:
            raise ValueError('This workspace does not support selecting scoring methodologies.')
        configuration_key = ('workspace configuration',)
        configuration = _shared(cache, configuration_key, lambda: _workspace_scoring_configuration(repository))
        scoring_profile = {'id': '', 'name': ''}
    selected_mode = normalize_scoring_nr_mode(nr_mode) if nr_mode else str(sources[0]['metadata']['nr_mode'])
    if selected_mode not in SCORING_NR_MODES:
        raise ValueError('NR Mode must be NSA, SA or NSA vs SA.')
    baseline = str(baseline_operator or '').strip()
    if not baseline:
        raise ValueError('Select a comparison baseline operator.')
    if baseline == SAME_OPERATOR_NSA and not both_modes:
        raise ValueError(f'The GAP reference {SAME_OPERATOR_NSA_LABEL} compares NSA vs SA: choose NSA vs SA in NR Mode.')
    baseline_aliases = _shared(cache, ('baseline aliases', baseline), lambda: _baseline_aliases(repository, baseline))
    mapping_getter = getattr(repository, 'list_operator_mappings', None)
    raw_operator_mappings = _shared(cache, ('operator mappings',), mapping_getter) if callable(mapping_getter) else {}
    operator_mappings = {
        str(alias).strip().casefold(): str(canonical).strip()
        for alias, canonical in raw_operator_mappings.items()
        if str(alias).strip() and str(canonical).strip()
    } if isinstance(raw_operator_mappings, dict) else {}
    config_hash = _shared(cache, ('hash', configuration_key), lambda: configuration_hash(configuration))
    if len(groups) > 1:
        # The result changes with the methodology of any of its campaigns.
        config_hash = hashlib.sha256(json.dumps(
            [[group['profile_id'], configuration_hash(group['configuration']), group['campaigns']] for group in groups],
            sort_keys=True).encode('utf-8')).hexdigest()
    version = _shared(cache, ('version', configuration_key), lambda: _method_version(configuration))
    profile_id = str(scoring_profile.get('id') or '')
    profile_name = str(scoring_profile.get('name') or '')
    # (Scoring Trends switched off need no campaigns of their own.)
    area_trends = None if not area_summary_part_enabled(normalized_area_summary, 'trends') else _shared(
        cache, ('trends', selected_mode, json.dumps(normalized_area_summary, sort_keys=True, default=str), scoring_profile_id),
        lambda: _area_trends(repository, selected_mode, normalized_area_summary, scoring_profile_id))
    # The result changes with the CDRs and methodologies of the campaigns of the trends too.
    key_area_summary = normalized_area_summary if area_trends is None else {**normalized_area_summary, 'trends': {
        'campaigns': area_trends['campaigns'], 'source_fingerprint': area_trends['source_fingerprint'],
        'methodologies': area_trends.get('configuration_hash', '')}}
    # Results calculated before the Geographical Areas followed the Breakdown and Separate cities on the whole country
    # are calculated again; with Main Cities, the result changes with the Main Cities of the workspace.
    key_area_summary = {**key_area_summary, 'geographical_version': GEOGRAPHICAL_AREAS_VERSION}
    # The NNS Break-down (when switched on) changes with the CDRs and methodologies of its campaigns and the Master Grid.
    nns_request = requested_nns_breakdown(normalized_area_summary)
    nns_sources = None if nns_request is None else _shared(
        cache, ('nns', selected_mode, json.dumps(nns_request, sort_keys=True), scoring_profile_id),
        lambda: _nns_sources(repository, selected_mode, nns_request, scoring_profile_id))
    if nns_sources is not None:
        key_area_summary[NNS_KEY] = {**nns_request, 'version': NNS_VERSION, 'master_grid': nns_sources['master_grid'],
                                     'modes': [[entry['nr_mode'], entry['campaigns'], entry['source_fingerprint'],
                                                entry.get('configuration_hash', '')] for entry in nns_sources['modes']]}
    if normalized_area_summary.get('main_cities'):
        key_area_summary['main_cities'] = _shared(cache, ('main cities',), lambda: _workspace_main_cities(repository))
    # A City breakdown with a City filter scores those cities and the Separate cities only.
    breakdown_cities = (with_breakdown_cities(normalized_area_summary, normalized_context_filters) or {}).get('breakdown_cities')
    if breakdown_cities:
        key_area_summary['breakdown_cities'] = breakdown_cities
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
    if nns_sources is not None:
        snapshot['nns_sources'] = nns_sources
    if len(groups) > 1:
        snapshot['methodology_groups'] = groups
    return {
        # With an automatic Campaign choice the selection is that choice, whatever CDRs it stands for today.
        'selection_key': saved_scoring_key([] if campaign_choice else normalized_ids, normalized_levels, selected_mode, baseline,
                                          normalized_context_filters, profile_id, normalized_area_summary),
        'result_key': result_key, 'method_version': version, 'source_fingerprint': source_fingerprint,
        'dataset_ids': normalized_ids, 'snapshot': snapshot, 'nr_mode': selected_mode, 'levels': normalized_levels,
        'baseline_operator': baseline,
    }


def _check_nsa_vs_sa(sources: list[dict[str, Any]], area_summary: dict[str, Any] | None) -> None:
    """An NSA vs SA calculation keeps the NSA and SA campaigns apart: the Campaign Maps must show them apart, and its
    Scoring Trends cannot aggregate every campaign (time split All)."""
    from src.modules.cdr.cdr_auto_selection import campaign_identity
    modes_of: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for source in sources:
        mode = str(source['metadata']['nr_mode'])
        for campaign in source['metadata'].get('campaigns') or []:
            scored = campaign_with_nr_mode(campaign, mode)
            identity = campaign_identity(scored)
            modes_of.setdefault(identity, set()).add(mode)
            labels.setdefault(identity, str(campaign))
    shared = [labels[identity] for identity, modes in modes_of.items() if len(modes) > 1]
    if shared:
        raise ValueError(f'NSA vs SA: the Campaign Map shows the NSA and SA campaigns alike ({", ".join(sorted(shared))}). '
                         'Show SA in the campaign labels (Workspace Config → Campaign Maps) to compare them.')
    if (area_summary or {}).get('time_split') == 'All':
        raise ValueError('NSA vs SA compares the campaigns of each NR Mode: choose a Scoring Trends time split other than All.')


def _workspace_main_cities(repository: Repository) -> list[str]:
    """The Main Cities of the workspace now (none in a repository without them)."""
    getter = getattr(repository, 'list_main_cities', None)
    return list(getter()) if callable(getter) else []


def _area_trends(repository: Repository, nr_mode: str, area_summary: dict[str, Any] | None,
                 scoring_profile_id: str | None) -> dict[str, Any] | None:
    """The campaigns, CDRs and methodologies of National & Geographical Areas Trends with campaigns of their own (an automatic
    choice such as Latest 2 campaigns stands for its campaigns now), or None when they score the job's campaigns."""
    if not area_summary or not area_summary.get('campaigns'):
        return None
    from src.modules.scoring.scoring_methodologies import BY_CAMPAIGN, display_configuration, methodology_groups
    from src.modules.scoring.scoring_selection import auto_scoring_cdr_ids, expand_scoring_campaigns
    campaigns = expand_scoring_campaigns(repository, nr_mode, area_summary['campaigns'])
    dataset_ids = auto_scoring_cdr_ids(repository, nr_mode, area_summary['campaigns'])
    if not dataset_ids:
        raise ValueError('National & Country Areas Trends: the chosen campaigns have no Data, Voice and Speech CDRs of '
                         f'{nr_mode_label(nr_mode)} now.')
    sources, _campaigns, fingerprint = _source_snapshot(repository, dataset_ids, expected_nr_mode=nr_mode)
    trends: dict[str, Any] = {'campaigns': list(campaigns), 'dataset_ids': list(dataset_ids), 'source_fingerprint': fingerprint}
    if scoring_profile_id == BY_CAMPAIGN:
        # Each campaign of the trends with the methodology that applies to it, as the job's own campaigns.
        wanted = {value.casefold() for value in campaigns}
        found = [campaign for source in sources for campaign in source['metadata'].get('campaigns') or []
                 if not wanted or campaign.casefold() in wanted]
        groups = methodology_groups(repository.get_scoring_profiles(), found or [''])
        if len(groups) > 1 and area_summary.get('time_split') == 'All':
            raise ValueError('National & Country Areas Trends of campaigns with different methodologies cannot aggregate every '
                             'selected CDR: choose another time split.')
        trends['configuration'] = validate_scoring_configuration(
            groups[0]['configuration'] if len(groups) == 1 else display_configuration(groups))
        if len(groups) > 1:
            trends['methodology_groups'] = groups
        trends['configuration_hash'] = hashlib.sha256(json.dumps(
            [[group['profile_id'], configuration_hash(group['configuration']), group['campaigns']] for group in groups],
            sort_keys=True).encode('utf-8')).hexdigest()
    return trends


def _prepare_saved_selection(repository: Repository, saved_scoring: dict[str, Any]) -> dict[str, Any]:
    """The identity of the result of a saved Saved Scoring with today's CDRs, methodology and Operator Maps."""
    return _prepare_saved_scoring(
        repository, saved_scoring['dataset_ids'], saved_scoring['levels'], saved_scoring['nr_mode'],
        baseline_operator=saved_scoring['baseline_operator'], context_filters=saved_scoring['context_filters'],
        scoring_profile_id=saved_scoring['scoring_profile_id'] or None, area_summary=saved_scoring['area_summary'],
    )


def _queue_calculation(connection: Any, filter_id: int, prepared: dict[str, Any], username: str, now: str) -> None:
    """Queue the calculation of a Saved Scoring with today's CDRs and methodology. A starred one keeps the user who
    starred it; the others belong to the user who calculates them (the application, ``system``, keeps their owner)."""
    snapshot = prepared['snapshot']
    connection.execute(
        f"""UPDATE {SAVED_SCORINGS_TABLE} SET status = 'queued', progress = 0,
           message = 'Waiting to calculate scoring', result_json = NULL, last_error = NULL, started_at = NULL,
           finished_at = NULL, updated_at = ?, created_by = CASE WHEN pinned = 1 OR ? = 'system' THEN created_by ELSE ? END,
           source_metadata_json = ?, result_key = ?,
           method_version = ?, source_fingerprint = ?, dataset_ids_json = ?, levels_json = ?, nr_mode = ?,
           baseline_operator = ?, cdr_refs_json = '[]'
           WHERE id = ?""",
        (now, str(username or 'system'), str(username or 'system'), json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')),
         prepared['result_key'], prepared['method_version'], prepared['source_fingerprint'],
         json.dumps(prepared['dataset_ids']), json.dumps(prepared['levels'], ensure_ascii=False), prepared['nr_mode'],
         prepared['baseline_operator'], int(filter_id)),
    )


def _is_up_to_date(row: Any, result_key: str) -> bool:
    return row['status'] == 'completed' and row['result_key'] == result_key and bool(row['result_json'])


def find_saved_scoring(
    repository: Repository, dataset_ids: list[int], levels: list[str], nr_mode: str | None,
    *, baseline_operator: str = DEFAULT_BASELINE_OPERATOR,
    context_filters: dict[str, list[str]] | None = None,
    scoring_profile_id: str | None = None,
    area_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The Saved Scoring of a selection, without changing it, and whether its saved result is up to date."""
    prepared = _prepare_saved_scoring(
        repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator,
        context_filters=context_filters, scoring_profile_id=scoring_profile_id, area_summary=area_summary,
    )
    with repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?',
                                 (prepared['selection_key'],)).fetchone()
    if row is None:
        return None
    saved_scoring = _row_to_saved_scoring(row, include_snapshot=False)
    saved_scoring['up_to_date'] = _is_up_to_date(row, prepared['result_key'])
    return saved_scoring


# What each part of the Geographical Areas & Scoring Trends adds to a result: the rest of a result is the same whether
# they are switched on or off (ticket #189).
_PART_RESULTS = {'country_areas': 'geographical', 'trends': 'area_summary'}


def _variant_selection_key(prepared: dict[str, Any], area_summary: dict[str, Any] | None) -> str | None:
    """The key of the same selection with another area summary (its parts on or off), without preparing it; None when it
    cannot be told so (its own key is not found again)."""
    snapshot = prepared['snapshot']
    filters = snapshot.get('context_filters') or {}
    ids = [] if campaign_presets(filters.get('Campaign') or []) else prepared['dataset_ids']

    def key(summary: Any) -> str:
        return saved_scoring_key(ids, prepared['levels'], prepared['nr_mode'], prepared['baseline_operator'], filters,
                                 str(snapshot.get('scoring_profile_id') or ''), normalize_area_summary_request(summary, filters))
    return key(area_summary) if key(snapshot.get('area_summary')) == prepared['selection_key'] else None


def _calculated_selection(repository: Repository, prepared: dict[str, Any], area_summary: dict[str, Any]) -> bool:
    """Whether a Saved Scoring of the same selection with ``area_summary`` may have a result (else it is not prepared)."""
    key = _variant_selection_key(prepared, area_summary)
    if key is None:
        return True
    with repository.connection() as connection:
        row = connection.execute(f"SELECT 1 FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ? AND status = 'completed'",
                                 (key,)).fetchone()
    return row is not None


def _result_of_fuller_selection(repository: Repository, prepared: dict[str, Any], dataset_ids: list[int], levels: list[str],
                                nr_mode: str | None, *, baseline_operator: str, context_filters: dict[str, list[str]] | None,
                                scoring_profile_id: str | None, area_summary: dict[str, Any] | None) -> tuple[str, int] | None:
    """The result of a selection with Country Areas or Scoring Trends switched off, taken from the Saved Scoring of the
    same selection with them on when its result is up to date (the same CDRs, methodology and Operator Maps): the same
    result without the parts switched off, so it is not calculated again. Its JSON and the Saved Scoring it comes from."""
    summary = prepared['snapshot'].get('area_summary')
    off = [part for part in _PART_RESULTS if not area_summary_part_enabled(summary, part)]
    if not off or not isinstance(area_summary, dict):
        return None
    cache: dict[Any, Any] = {}
    # (Both parts on first: the Favourite Scorings are usually saved so.)
    for count in range(len(off), 0, -1):
        for turned_on in itertools.combinations(off, count):
            if not _calculated_selection(repository, prepared, {key: value for key, value in area_summary.items() if key not in turned_on}):
                continue
            fuller = _prepare_saved_scoring(
                repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator, context_filters=context_filters,
                scoring_profile_id=scoring_profile_id, cache=cache,
                area_summary={key: value for key, value in area_summary.items() if key not in turned_on})
            with repository.connection() as connection:
                row = connection.execute(f'SELECT id, status, result_key, result_json FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?',
                                         (fuller['selection_key'],)).fetchone()
            if row is None or not _is_up_to_date(row, fuller['result_key']):
                continue
            result = _decode_json(row['result_json'], None)
            # (A Points Lost Map still to be drawn is drawn for its own Saved Scoring only.)
            if not isinstance(result, dict) or (isinstance(result.get('points_loss'), dict) and result['points_loss'].get('pending')):
                continue
            for part in off:
                result.pop(_PART_RESULTS[part], None)
            if 'trends' in off:
                # (With the warnings of the trends.)
                result['warnings'] = [warning for warning in result.get('warnings') or [] if not _is_trend_warning(warning)]
            return json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False), int(row['id'])
    return None


def _is_trend_warning(warning: Any) -> bool:
    return any(str(warning).startswith(prefix) for prefix in WARNING_PREFIXES)


def _parts_of_lesser_selection(repository: Repository, prepared: dict[str, Any], dataset_ids: list[int], levels: list[str],
                               nr_mode: str | None, *, baseline_operator: str, context_filters: dict[str, list[str]] | None,
                               scoring_profile_id: str | None, area_summary: dict[str, Any] | None) -> dict[str, Any] | None:
    """Where a calculation with Country Areas and Scoring Trends on takes one of them already calculated: the Saved
    Scoring of the same selection with the other one switched off, when its result is up to date (ticket #189). The
    calculation then scores only what that result lacks (see calculate_saved_scoring), checking again that it is the same."""
    summary = prepared['snapshot'].get('area_summary')
    on = [part for part in _PART_RESULTS if area_summary_part_enabled(summary, part)]
    if len(on) < 2 or not isinstance(area_summary, dict):
        return None
    cache: dict[Any, Any] = {}
    # (The costlier part first: the Scoring Trends.)
    for kept in sorted(on, key=lambda part: part != 'trends'):
        if not _calculated_selection(repository, prepared, {**area_summary, **{part: False for part in on if part != kept}}):
            continue
        lesser = _prepare_saved_scoring(
            repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator, context_filters=context_filters,
            scoring_profile_id=scoring_profile_id, cache=cache,
            area_summary={**area_summary, **{part: False for part in on if part != kept}})
        with repository.connection() as connection:
            row = connection.execute(f'SELECT id, status, result_key, result_json FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?',
                                     (lesser['selection_key'],)).fetchone()
        if row is None or not _is_up_to_date(row, lesser['result_key']):
            continue
        result = _decode_json(row['result_json'], None)
        if isinstance(result, dict) and _PART_RESULTS[kept] in result and not (
                isinstance(result.get('points_loss'), dict) and result['points_loss'].get('pending')):
            return {'saved_scoring_id': int(row['id']), 'result_key': row['result_key'], 'parts': [kept]}
    return None


def _given_parts(repository: Repository, saved_scoring: dict[str, Any]) -> tuple[list[str], dict[str, Any]] | None:
    """The parts a calculation takes from the result of another Saved Scoring (see _parts_of_lesser_selection), when that
    result is still the one it was queued with."""
    given = saved_scoring.get('complete_from')
    if not isinstance(given, dict) or not isinstance(saved_scoring.get('area_summary'), dict):
        return None
    parts = [part for part in given.get('parts') or [] if part in _PART_RESULTS]
    try:
        source = get_saved_scoring(repository, int(given['saved_scoring_id']), include_result=True)
    except (KeyError, TypeError, ValueError):
        return None
    result = (source or {}).get('result')
    if (not parts or not source or source.get('status') != 'completed' or source.get('result_key') != given.get('result_key')
            or not isinstance(result, dict) or any(_PART_RESULTS[part] not in result for part in parts)):
        return None
    return parts, result


def _with_given_parts(prepared: dict[str, Any], given: dict[str, Any] | None) -> dict[str, Any]:
    """A prepared selection whose calculation takes some parts from another Saved Scoring (``complete_from``)."""
    return {**prepared, 'snapshot': {**prepared['snapshot'], 'complete_from': given}} if given else prepared


def _keep_result_of_fuller_selection(connection: Any, filter_id: int, prepared: dict[str, Any], reused: tuple[str, int],
                                     username: str, now: str) -> None:
    """Give a Saved Scoring the result taken from the same selection with more parts on, as if it had been calculated."""
    _queue_calculation(connection, filter_id, prepared, username, now)
    connection.execute(
        f"""UPDATE {SAVED_SCORINGS_TABLE} SET status = 'completed', progress = 100,
           message = 'Scoring tables and GAP analysis are ready', result_json = ?, started_at = ?, finished_at = ?, updated_at = ?
           WHERE id = ?""", (reused[0], now, now, now, int(filter_id)))


def save_saved_scoring(
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
    """Use a selection: its Saved Scoring (saved the first time it is used) with its result.

    Returns the Saved Scoring and whether its result is ready or already being calculated (``True``), or must be
    calculated (``False``): the first time, when its CDRs, methodology or Operator Maps changed since its result was
    saved, after a failure, or with ``force``. ``area_summary`` (a breakdown level, chosen cities and a time split)
    adds the National & Geographical Areas Trends (and, with campaigns, the Scoring Trends of those campaigns) to a selection.
    """
    prepared = _prepare_saved_scoring(
        repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator,
        context_filters=context_filters, scoring_profile_id=scoring_profile_id, area_summary=area_summary,
    )
    # With Country Areas or Scoring Trends switched off, the result of the same selection with them on serves when it is
    # up to date: switching them off calculates nothing (ticket #189).
    reused = None
    if not force:
        with repository.connection() as connection:
            known = connection.execute(f'SELECT status, result_key, result_json FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?',
                                       (prepared['selection_key'],)).fetchone()
        if known is None or (known['status'] not in ('queued', 'processing') and not _is_up_to_date(known, prepared['result_key'])):
            selection = dict(baseline_operator=baseline_operator, context_filters=context_filters,
                             scoring_profile_id=scoring_profile_id, area_summary=area_summary)
            reused = _result_of_fuller_selection(repository, prepared, dataset_ids, levels, nr_mode, **selection)
            if reused is None:
                # With both parts on, one of them may be calculated already: only the other one is calculated.
                prepared = _with_given_parts(prepared, _parts_of_lesser_selection(
                    repository, prepared, dataset_ids, levels, nr_mode, **selection))
    now = local_now_iso()
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?',
                                 (prepared['selection_key'],)).fetchone()
        if row is not None:
            connection.execute(
                f'UPDATE {SAVED_SCORINGS_TABLE} SET use_count = use_count + 1, last_used_at = ? WHERE id = ?',
                (now, row['id']),
            )
            if row['status'] in ('queued', 'processing'):
                row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (row['id'],)).fetchone()
                return _row_to_saved_scoring(row), True
            if not force and _is_up_to_date(row, prepared['result_key']):
                row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (row['id'],)).fetchone()
                return _row_to_saved_scoring(row, include_result=True), True
            if reused is not None:
                _keep_result_of_fuller_selection(connection, int(row['id']), prepared, reused, username, now)
                row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (row['id'],)).fetchone()
                _log_result_reused(repository, username, row, reused)
                return _row_to_saved_scoring(row, include_result=True), True
            _queue_calculation(connection, int(row['id']), prepared, username, now)
            row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (row['id'],)).fetchone()
            return _row_to_saved_scoring(row), False
        cursor = connection.execute(
            f"""
            INSERT INTO {SAVED_SCORINGS_TABLE} (
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
        row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?',
                                 (int(cursor.lastrowid),)).fetchone()
        if reused is not None:
            _keep_result_of_fuller_selection(connection, int(row['id']), prepared, reused, username, now)
            row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (row['id'],)).fetchone()
    if reused is not None:
        _log_result_reused(repository, username, row, reused)
        return _row_to_saved_scoring(row, include_result=True), True
    return _row_to_saved_scoring(row), False


def _log_result_reused(repository: Repository, username: str, row: Any, reused: tuple[str, int]) -> None:
    summary = (_decode_json(row['source_metadata_json'], {}) or {}).get('area_summary') or {}
    repository.try_add_log(str(username or 'system'), 'scoring_result_reused', json.dumps({
        'saved_scoring_id': int(row['id']), 'name': row['name'] or '', 'from_saved_scoring_id': reused[1],
        'switched_off': [part for part in _PART_RESULTS if not area_summary_part_enabled(summary, part)]}, ensure_ascii=False))


def refresh_saved_scoring(repository: Repository, filter_id: int, username: str = 'system') -> tuple[bool, str]:
    """Queue the calculation of an opened Saved Scoring whose saved result no longer matches its CDRs, methodology
    or Operator Maps (or that has none yet).

    Returns whether it was queued, and why it cannot be calculated (its CDRs or methodology are gone) otherwise.
    """
    _resolve_imported_filters(repository)
    # Its many reads (the CDRs and campaigns of its selection) share one connection, and the write lock is taken only
    # when the saved result no longer matches: opening a Saved Scoring never waits for another one being saved.
    with repository.shared_connection():
        saved_scoring = get_saved_scoring(repository, filter_id)
        if saved_scoring is None or saved_scoring['status'] in ('queued', 'processing'):
            return False, ''
        if not saved_scoring['dataset_ids']:
            names = ', '.join(saved_scoring['missing_cdrs']) or 'its CDRs'
            return False, f'The CDRs of this Saved Scoring are not in this workspace: {names}.'
        try:
            prepared = _prepare_saved_selection(repository, saved_scoring)
        except ValueError as exc:
            return False, str(exc)
        with repository.connection() as connection:
            row = connection.execute(f'SELECT status, result_key, result_json IS NOT NULL AND result_json <> \'\' AS has_result '
                                     f'FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
        if row is None or row['status'] in ('queued', 'processing') or (
                row['status'] == 'completed' and row['result_key'] == prepared['result_key'] and row['has_result']):
            return False, ''
        # (Its Country Areas or Scoring Trends switched off: the result of the same selection with them on serves; with
        # both on, one of them may be calculated already.)
        selection = dict(baseline_operator=saved_scoring['baseline_operator'], context_filters=saved_scoring['context_filters'],
                         scoring_profile_id=saved_scoring['scoring_profile_id'] or None, area_summary=saved_scoring['area_summary'])
        selected = (saved_scoring['dataset_ids'], saved_scoring['levels'], saved_scoring['nr_mode'])
        reused = _result_of_fuller_selection(repository, prepared, *selected, **selection)
        if reused is None:
            prepared = _with_given_parts(prepared, _parts_of_lesser_selection(repository, prepared, *selected, **selection))
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
        if row is None or row['status'] in ('queued', 'processing') or _is_up_to_date(row, prepared['result_key']):
            return False, ''
        # A failed calculation is not repeated on its own until something it uses changes.
        if row['status'] == 'failed' and row['result_key'] == prepared['result_key'] and reused is None:
            return False, ''
        if reused is not None:
            _keep_result_of_fuller_selection(connection, int(filter_id), prepared, reused, username, local_now_iso())
            row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
        else:
            _queue_calculation(connection, int(filter_id), prepared, username, local_now_iso())
    if reused is not None:
        _log_result_reused(repository, username, row, reused)
        return False, ''
    return True, ''


def list_saved_scorings(repository: Repository) -> list[dict[str, Any]]:
    """Every Saved Scoring, the starred ones first in their place and then the latest used, without their results.

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
            f'updated_at, finished_at FROM {SAVED_SCORINGS_TABLE} '
            'ORDER BY pinned DESC, position IS NULL, position, julianday(last_used_at) DESC, id DESC'
        ).fetchall()
    saved_scorings = [_row_to_saved_scoring(row, include_snapshot=False) for row in rows]
    replacements = _replaced_cdrs(repository) if saved_scorings else {}
    for saved_scoring in saved_scorings:
        # One with an automatic Campaign choice takes the newer CDRs on its own the next time it is opened.
        follows = bool(campaign_presets(saved_scoring['context_filters'].get('Campaign') or []))
        saved_scoring['newer_cdrs'] = [] if follows else [replacements[dataset_id] for dataset_id in saved_scoring['dataset_ids']
                                                         if dataset_id in replacements]
    return saved_scorings


def _replaced_cdrs(repository: Repository) -> dict[int, dict[str, Any]]:
    """The CDRs replaced by newer ones in the combined tables, with the newest CDR that replaces each one."""
    from src.modules.cdr.cdr_stage import combined_inclusion
    try:
        inclusion = combined_inclusion(repository)
    except Exception:  # The notice is optional: without it the Saved Scorings are still listed.
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
    """Replace the CDRs of a Saved Scoring that newer ones replace and calculate it again, keeping its name, star and
    place. A Saved Scoring that already had that selection is merged into it (its name and star are kept when this one
    has none).

    Returns ``None`` when the Saved Scoring does not exist; otherwise the Saved Scoring, the CDRs replaced
    (``replaced``) and the merged Saved Scoring (``merged_filter_id``).
    """
    saved_scoring = get_saved_scoring(repository, filter_id)
    if saved_scoring is None:
        return None
    if saved_scoring['status'] in ('queued', 'processing'):
        raise ValueError('Wait until this Saved Scoring is calculated to use its newer CDRs.')
    replacements = _replaced_cdrs(repository)
    replaced = [replacements[dataset_id] for dataset_id in saved_scoring['dataset_ids'] if dataset_id in replacements]
    if not replaced:
        raise ValueError('This Saved Scoring already uses the newest CDRs.')
    dataset_ids = list(dict.fromkeys(
        replacements[dataset_id]['replaced_by'] if dataset_id in replacements else dataset_id
        for dataset_id in saved_scoring['dataset_ids']))
    prepared = _prepare_saved_selection(repository, {**saved_scoring, 'dataset_ids': dataset_ids})
    updated, merged_filter_id = _replace_selection(repository, filter_id, prepared, username)
    if updated is None:
        return None
    return {'saved_scoring': updated, 'replaced': replaced, 'merged_filter_id': merged_filter_id}


def edit_saved_scoring(
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
    """Give a Saved Scoring another selection (its NR Mode, CDRs, filters, Split by, GAP reference, methodology or
    National & area summary) and calculate it again, keeping its name, star and place. A Saved Scoring that already had
    that selection is merged into it, as with its newer CDRs.

    Returns ``None`` when the Saved Scoring does not exist; otherwise the Saved Scoring, whether its selection changed
    (``changed``; an unchanged one keeps its result), its selection before (``previous``) and the merged Saved Scoring
    (``merged_filter_id``).
    """
    saved_scoring = get_saved_scoring(repository, filter_id)
    if saved_scoring is None:
        return None
    if saved_scoring['status'] in ('queued', 'processing'):
        raise ValueError('Wait until this Saved Scoring is calculated to edit it.')
    prepared = _prepare_saved_scoring(
        repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator,
        context_filters=context_filters, scoring_profile_id=scoring_profile_id, area_summary=area_summary,
    )
    previous = {key: saved_scoring[key] for key in (
        'nr_mode', 'dataset_ids', 'levels', 'baseline_operator', 'context_filters', 'scoring_profile_id', 'area_summary')}
    # (Another map of its Postal Codes is the same selection, with another result.)
    if prepared['selection_key'] == saved_scoring['selection_key'] and postal_areas.chosen_map(prepared['snapshot']) == postal_areas.chosen_map(saved_scoring):
        return {'saved_scoring': saved_scoring, 'changed': False,
                'previous': previous, 'merged_filter_id': None}
    updated, merged_filter_id = _replace_selection(repository, filter_id, prepared, username)
    if updated is None:
        return None
    return {'saved_scoring': updated, 'changed': True, 'previous': previous, 'merged_filter_id': merged_filter_id}


def duplicate_saved_scoring(
    repository: Repository,
    filter_id: int,
    dataset_ids: list[int],
    levels: list[str],
    nr_mode: str | None,
    *,
    name: str = '',
    baseline_operator: str = DEFAULT_BASELINE_OPERATOR,
    username: str = 'system',
    context_filters: dict[str, list[str]] | None = None,
    scoring_profile_id: str | None = None,
    area_summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Save a copy of a Saved Scoring, with the selection it was given, as a new starred Saved Scoring queued to be
    calculated; the copied one stays as it was, and the copy goes right after it among the Favourite Scorings (first
    when the copied one is not starred).

    Returns ``None`` when the copied Saved Scoring does not exist. A selection that is already a Saved Scoring (the copied
    one included) is not saved again.
    """
    source = get_saved_scoring(repository, filter_id)
    if source is None:
        return None
    text = ' '.join(str(name or '').split())
    if len(text) > 120:
        raise ValueError('The name of a Saved Scoring can have up to 120 characters.')
    prepared = _prepare_saved_scoring(
        repository, dataset_ids, levels, nr_mode, baseline_operator=baseline_operator,
        context_filters=context_filters, scoring_profile_id=scoring_profile_id, area_summary=area_summary,
    )
    now = local_now_iso()
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        existing = connection.execute(f'SELECT id FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?',
                                      (prepared['selection_key'],)).fetchone()
        if existing is not None and int(existing['id']) == int(filter_id):
            raise ValueError('The copy still has the filters of the Saved Scoring: change them to save it as a new one.')
        if existing is not None:
            raise ValueError(f'Saved Scoring {existing["id"]} already has these filters: change them to save the copy.')
        row = connection.execute(f'SELECT pinned, position FROM {SAVED_SCORINGS_TABLE} WHERE id = ?',
                                 (int(filter_id),)).fetchone()
        if row is not None and row['pinned'] and row['position'] is not None:
            position = int(row['position']) + 1
            connection.execute(f'UPDATE {SAVED_SCORINGS_TABLE} SET position = position + 1 '
                               'WHERE pinned = 1 AND position >= ?', (position,))
        else:
            first = connection.execute(
                f'SELECT MIN(position) FROM {SAVED_SCORINGS_TABLE} WHERE pinned = 1 AND position IS NOT NULL').fetchone()[0]
            position = (int(first) - 1) if first is not None else 1
        cursor = connection.execute(
            f"""
            INSERT INTO {SAVED_SCORINGS_TABLE} (
                selection_key, name, pinned, position, last_used_at, result_key, method_version, source_fingerprint,
                dataset_ids_json, source_metadata_json, nr_mode, levels_json, baseline_operator,
                status, progress, message, created_by, created_at, updated_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, 'Waiting to calculate scoring', ?, ?, ?)
            """,
            (
                prepared['selection_key'], text, position, now, prepared['result_key'], prepared['method_version'],
                prepared['source_fingerprint'], json.dumps(prepared['dataset_ids']),
                json.dumps(prepared['snapshot'], ensure_ascii=False, separators=(',', ':')), prepared['nr_mode'],
                json.dumps(prepared['levels'], ensure_ascii=False), prepared['baseline_operator'],
                str(username or 'system'), now, now,
            ),
        )
        row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?',
                                 (int(cursor.lastrowid),)).fetchone()
    return _row_to_saved_scoring(row)


def _replace_selection(repository: Repository, filter_id: int, prepared: dict[str, Any],
                       username: str) -> tuple[dict[str, Any] | None, int | None]:
    """Give a Saved Scoring the prepared selection and queue its calculation, keeping its name, star and place.

    A Saved Scoring that already had that selection is merged into it (its name and star are kept when this one has
    none). Returns the Saved Scoring (``None`` when it does not exist) and the id of the merged one.
    """
    now = local_now_iso()
    merged_filter_id = None
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
        if row is None:
            return None, None
        duplicate = connection.execute(
            f'SELECT id, name, pinned, position FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ? AND id != ?',
            (prepared['selection_key'], int(filter_id))).fetchone()
        name, pinned, position = row['name'], row['pinned'], row['position']
        if duplicate is not None:
            merged_filter_id = int(duplicate['id'])
            name = name or duplicate['name']
            if not pinned and duplicate['pinned']:
                pinned, position = duplicate['pinned'], duplicate['position']
            connection.execute(f'DELETE FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (merged_filter_id,))
        connection.execute(
            f'UPDATE {SAVED_SCORINGS_TABLE} SET selection_key = ?, name = ?, pinned = ?, position = ?, '
            'use_count = use_count + 1, last_used_at = ? WHERE id = ?',
            (prepared['selection_key'], name, pinned, position, now, int(filter_id)))
        _queue_calculation(connection, int(filter_id), prepared, username, now)
        row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
    return _row_to_saved_scoring(row), merged_filter_id


def mark_saved_scoring_used(repository: Repository, filter_id: int) -> dict[str, Any] | None:
    """Count the opening of a Saved Scoring from its card as a use, which also moves it up the list."""
    with repository.connection() as connection:
        connection.execute(f'UPDATE {SAVED_SCORINGS_TABLE} SET use_count = use_count + 1, last_used_at = ? WHERE id = ?',
                           (local_now_iso(), int(filter_id)))
    return get_saved_scoring(repository, filter_id)


def update_saved_scoring(repository: Repository, filter_id: int, *, name: str | None = None,
                           pinned: bool | None = None, username: str | None = None) -> dict[str, Any] | None:
    """Rename a Saved Scoring (an empty name shows its filters) or star it, which keeps it at the top of the list of starred
    ones (unstarring it takes it out of the list); the user who stars it (``username``) is its creator."""
    updates: dict[str, Any] = {}
    if name is not None:
        text = ' '.join(str(name).split())
        if len(text) > 120:
            raise ValueError('The name of a Saved Scoring can have up to 120 characters.')
        updates['name'] = text
    if pinned is not None:
        updates['pinned'] = 1 if pinned else 0
    if updates:
        with repository.connection() as connection:
            if pinned is not None:
                row = connection.execute(f'SELECT pinned, position FROM {SAVED_SCORINGS_TABLE} WHERE id = ?',
                                         (int(filter_id),)).fetchone()
                if pinned and row is not None and not (row['pinned'] and row['position'] is not None):
                    # A newly starred Saved Scoring goes first; the others keep their order.
                    first = connection.execute(
                        f'SELECT MIN(position) FROM {SAVED_SCORINGS_TABLE} WHERE pinned = 1 AND position IS NOT NULL').fetchone()[0]
                    updates['position'] = (int(first) - 1) if first is not None else 1
                elif not pinned:
                    updates['position'] = None
                if pinned and row is not None and not row['pinned'] and str(username or '').strip():
                    updates['created_by'] = str(username).strip()
            assignments = ', '.join(f'{column} = ?' for column in updates)
            connection.execute(f'UPDATE {SAVED_SCORINGS_TABLE} SET {assignments} WHERE id = ?',
                               (*updates.values(), int(filter_id)))
    return get_saved_scoring(repository, filter_id)


def reorder_saved_scorings(repository: Repository, filter_ids: list[int]) -> list[int]:
    """Put the starred Saved Scorings in the order given (dragged in their list); starred ones left out follow it in their
    order. Returns the new order."""
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        starred = [int(row['id']) for row in connection.execute(
            f'SELECT id FROM {SAVED_SCORINGS_TABLE} WHERE pinned = 1 '
            'ORDER BY position IS NULL, position, julianday(last_used_at) DESC, id DESC').fetchall()]
        chosen = [int(filter_id) for filter_id in dict.fromkeys(filter_ids) if int(filter_id) in starred]
        order = [*chosen, *(filter_id for filter_id in starred if filter_id not in chosen)]
        connection.executemany(f'UPDATE {SAVED_SCORINGS_TABLE} SET position = ? WHERE id = ?',
                               [(index, filter_id) for index, filter_id in enumerate(order, start=1)])
    return order


def recover_interrupted_saved_scorings(repository: Repository) -> list[int]:
    """Fail the calculations left running when the application stopped, when the workspace is first opened."""
    now = local_now_iso()
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT id FROM {SAVED_SCORINGS_TABLE} WHERE status IN ('queued', 'processing') ORDER BY id",
        ).fetchall()
        filter_ids = [int(row['id']) for row in rows]
        if filter_ids:
            placeholders = ','.join('?' for _ in filter_ids)
            connection.execute(
                f"UPDATE {SAVED_SCORINGS_TABLE} SET status = 'failed', last_error = ?, message = ?, updated_at = ?, "
                f"finished_at = ? WHERE id IN ({placeholders}) AND status IN ('queued', 'processing')",
                (INTERRUPTED_CALCULATION_MESSAGE, INTERRUPTED_CALCULATION_MESSAGE, now, now, *filter_ids),
            )
    return filter_ids


def get_saved_scoring(
    repository: Repository, filter_id: int, include_result: bool = False,
    include_internal_snapshot: bool = False,
) -> dict[str, Any] | None:
    """A Saved Scoring and, optionally, its saved result."""
    with repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
    if row is None:
        return None
    saved_scoring = _row_to_saved_scoring(
        row, include_result=include_result, include_internal_snapshot=include_internal_snapshot,
    )
    if include_result and not include_internal_snapshot:
        _apply_current_environment_labels(repository, saved_scoring)
        # Results saved before environment scaling existed are scaled when they are opened.
        from src.modules.scoring.scoring import apply_environment_scaling
        apply_environment_scaling(saved_scoring.get('result'), str(saved_scoring.get('baseline_operator') or 'EE'))
    return saved_scoring


def _apply_current_environment_labels(repository: Repository, saved_scoring: dict[str, Any]) -> None:
    """Project current profile labels without changing stored rules or environment keys."""
    try:
        profile = repository.get_scoring_profile(saved_scoring.get('scoring_profile_id') or None)
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
    for configuration in (saved_scoring.get('configuration'), (saved_scoring.get('result') or {}).get('configuration')):
        if not isinstance(configuration, dict):
            continue
        for name, scope in configuration.get('scope', {}).get('environments', {}).items():
            identity = source_identity(scope)
            label = labels.get(identity) if identity[0] else None
            if label and label != str(scope.get('display_name') or name):
                scope['display_name'] = label


def delete_saved_scoring(repository: Repository, filter_id: int) -> bool:
    """Remove a Saved Scoring and its saved result; its CDRs and the Scoring History stay."""
    with repository.connection() as connection:
        cursor = connection.execute(f'DELETE FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),))
        return cursor.rowcount > 0


def prune_unpinned_saved_scorings(repository: Repository, keep_id: int, username: str) -> list[int]:
    """Only the Saved Scorings marked with the star are kept: remove the other unstarred ones of a user when they use
    another one (``keep_id``), except those still calculating or drawing their Points Lost Map."""
    workspace = str(Path(repository.db_path).resolve())
    with _points_loss_guard:
        drawing = {filter_id for path, filter_id in _points_loss_jobs if path == workspace}
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT id FROM {SAVED_SCORINGS_TABLE} WHERE pinned = 0 AND id != ? AND created_by = ? "
            "AND status NOT IN ('queued', 'processing')", (int(keep_id), str(username or 'system'))).fetchall()
        removed = [int(row['id']) for row in rows if int(row['id']) not in drawing]
        connection.executemany(f'DELETE FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', [(filter_id,) for filter_id in removed])
    return removed


class _SavedScoringDeleted(Exception):
    """Stop a calculation at a checkpoint once its Saved Scoring is removed."""


def _update_saved_scoring(repository: Repository, filter_id: int, **fields: Any) -> None:
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
            f'UPDATE {SAVED_SCORINGS_TABLE} SET {assignments} WHERE id = ?',
            (*values, int(filter_id)),
        )


# -- Export, import, transfers and backups -----------------------------------------------------------------------
# A Favourite Scoring travels as the Scoring & GAP Favourite Scorings element, without its result: its CDRs are named by the SHA-256 of
# their files, so the workspace that receives it finds them whatever their name or id there.

SAVED_SCORINGS_FORMAT = 'drivetest-analyzer-saved-scorings'
SAVED_SCORINGS_VERSION = 1
# Exported until v0.12.7, when they were called Saved Filters: still imported, transferred and restored.
LEGACY_SAVED_SCORINGS_FORMAT = 'drivetest-analyzer-saved-filters'


def current_saved_scorings_document(document: Any) -> Any:
    """A Saved Scorings document in the format of this version (one of the Saved Filters of earlier versions converted)."""
    if isinstance(document, dict) and document.get('format') == LEGACY_SAVED_SCORINGS_FORMAT and 'saved_scorings' not in document:
        return {**{key: value for key, value in document.items() if key != 'saved_filters'},
                'format': SAVED_SCORINGS_FORMAT, 'saved_scorings': document.get('saved_filters')}
    return document


def _cdr_hashes(repository: Repository) -> dict[int, dict[str, str]]:
    """The SHA-256 of the file, the name and the type of every CDR of the workspace, and of the deleted CDRs whose
    Scoring History is kept."""
    from src.modules.scoring.scoring_history import HISTORY_SOURCES_TABLE, ensure_history_tables, file_sha256
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


def saved_scorings_document(repository: Repository, *, favourites_only: bool = False) -> dict[str, Any]:
    """Every Saved Scoring of the workspace (``favourites_only``: the Favourite Scorings, the Scoring & GAP Favourite Scorings
    element of Import / Export / Transfer, workspace transfers and backups), without its result, with its CDRs named
    by their file."""
    hashes: dict[int, dict[str, str]] | None = None
    entries = []
    with repository.connection() as connection:
        rows = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE}{" WHERE pinned = 1" if favourites_only else ""} '
                                  'ORDER BY id').fetchall()
    for row in rows:
        saved_scoring = _row_to_saved_scoring(row, include_snapshot=False)
        refs = _decode_json(row['cdr_refs_json'], [])
        if saved_scoring['dataset_ids']:
            hashes = hashes if hashes is not None else _cdr_hashes(repository)
            refs = [hashes.get(dataset_id) for dataset_id in saved_scoring['dataset_ids']]
            if not all(refs):
                # Without the file of one of its CDRs, the selection could not be found again elsewhere.
                continue
        if not refs:
            continue
        entries.append({
            'name': saved_scoring['name'], 'pinned': saved_scoring['pinned'], 'position': saved_scoring['position'],
            'use_count': saved_scoring['use_count'], 'last_used_at': saved_scoring['last_used_at'],
            'cdrs': refs, 'nr_mode': saved_scoring['nr_mode'], 'levels': saved_scoring['levels'],
            'baseline_operator': saved_scoring['baseline_operator'],
            'context_filters': saved_scoring['context_filters'],
            'scoring_profile_id': saved_scoring['scoring_profile_id'],
            # Its Geographical Areas & Scoring Trends (Main Cities kept as such).
            'area_summary': saved_scoring['area_summary'],
            # Who it belongs to (who starred it, or who calculates it), for Import / Export and Transfer.
            'created_by': saved_scoring['created_by'],
        })
    return {'format': SAVED_SCORINGS_FORMAT, 'version': SAVED_SCORINGS_VERSION, 'saved_scorings': entries}


def import_saved_scorings(repository: Repository, document: Any,
                         creator: Callable[[Any, str], str] | None = None,
                         progress: Callable[[str, float], None] | None = None, takes_order: bool = True) -> int:
    """Add the Saved Scorings of a document to the workspace. Their CDRs are found by file, except for those with a
    Campaign choice (Latest campaign…), which take the CDRs it stands for here and need none in the document; until
    they are processed here, they wait for them. One the workspace already has (the same selection) takes the name and
    the creator of the document, and its star if the document has it, without losing its own star (see
    _resolve_imported_filters). ``creator(creator in the document, '')`` decides who each one belongs to (without it,
    the application), and ``progress(phase, share done)`` follows the Saved Scorings of the document, the only ones it
    prepares. The starred ones go in the order of the document, ahead of those only the workspace has; without an order
    in the document (or ``takes_order``, the starter ones), those the workspace lacks follow its own and the others stay
    where they are. Returns how many were added."""
    document = current_saved_scorings_document(document)
    if (not isinstance(document, dict) or document.get('format') != SAVED_SCORINGS_FORMAT
            or document.get('version') != SAVED_SCORINGS_VERSION or not isinstance(document.get('saved_scorings'), list)):
        raise ValueError('The Saved Scorings are invalid.')
    added = 0
    package_keys: list[str] = []
    now = local_now_iso()
    entries = sorted(enumerate(document['saved_scorings']), key=lambda item: (
        not (isinstance(item[1], dict) and item[1].get('pinned')),
        item[1].get('position') is None if isinstance(item[1], dict) else True,
        (item[1].get('position') or 0) if isinstance(item[1], dict) and isinstance(item[1].get('position'), int) else 0,
        item[0]))
    starred = [entry for _index, entry in entries if isinstance(entry, dict) and entry.get('pinned')]
    ordered = takes_order and any(isinstance(entry.get('position'), int) for entry in starred)
    with repository.connection() as connection:
        first, last = connection.execute(
            f'SELECT MIN(position), MAX(position) FROM {SAVED_SCORINGS_TABLE} WHERE pinned = 1').fetchone()
    next_position = int(first) - len(starred) if ordered and first is not None else int(last or 0) + 1
    for _index, entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('The Saved Scorings are invalid.')
        refs = [
            {'sha256': str(item.get('sha256') or ''), 'name': str(item.get('name') or ''), 'kind': str(item.get('kind') or '')}
            for item in entry.get('cdrs') or [] if isinstance(item, dict) and item.get('sha256')
        ]
        levels = [str(level) for level in entry.get('levels') or [] if str(level).strip()]
        nr_mode = normalize_scoring_nr_mode(entry.get('nr_mode'))
        context_filters = _normalize_context_filters(entry.get('context_filters') or {})
        campaign_choice = (campaign_presets(context_filters['Campaign']) or [''])[0]
        if not refs and campaign_choice:
            # Without CDRs (the starter Favourite Scorings), those its Campaign choice stands for in the workspace.
            refs = [{'sha256': '', 'name': f'{CAMPAIGN_PRESET_LABELS[campaign_choice]} CDRs', 'kind': ''}]
        if not refs or not levels or nr_mode is None:
            raise ValueError('The Saved Scorings are invalid.')
        area_summary = entry.get('area_summary') if isinstance(entry.get('area_summary'), dict) else None
        selection = {'levels': levels, 'nr_mode': nr_mode, 'baseline_operator': str(entry.get('baseline_operator') or DEFAULT_BASELINE_OPERATOR),
                     'context_filters': context_filters, 'scoring_profile_id': str(entry.get('scoring_profile_id') or ''),
                     'area_summary': area_summary}
        pending_key = 'pending:' + hashlib.sha256(json.dumps(
            {**selection, 'cdrs': sorted(ref['sha256'] for ref in refs)}, ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode('utf-8')).hexdigest()
        package_keys.append(pending_key)
        snapshot = {'sources': [{'name': ref['name'], 'kind': ref['kind']} for ref in refs],
                    'scoring_profile_id': selection['scoring_profile_id'], 'context_filters': context_filters,
                    'resolved_context_filters': context_filters}
        if area_summary:
            snapshot['area_summary'] = area_summary
        # Whether the document says who it belongs to (documents of earlier versions do not): only then does a Saved
        # Filter the workspace has take that creator.
        snapshot['creator_from_document'] = str(entry.get('created_by') or '').strip().casefold() not in {'', 'system'}
        # Whether the place it is given here is the one the document says: the Saved Scoring it joins takes it too.
        snapshot['position_from_document'] = ordered and bool(entry.get('pinned'))
        created_by = creator(entry.get('created_by'), '') if creator else 'system'
        position = next_position if entry.get('pinned') else None
        if entry.get('pinned'):
            next_position += 1
        with repository.connection() as connection:
            if connection.execute(f'SELECT 1 FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?', (pending_key,)).fetchone():
                if snapshot['position_from_document']:
                    connection.execute(f'UPDATE {SAVED_SCORINGS_TABLE} SET position = ? WHERE selection_key = ?',
                                       (position, pending_key))
                continue
            connection.execute(
                f"""INSERT INTO {SAVED_SCORINGS_TABLE} (
                    selection_key, name, pinned, position, use_count, last_used_at, cdr_refs_json, dataset_ids_json,
                    source_metadata_json, nr_mode, levels_json, baseline_operator, status, message, created_by, created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '[]', ?, ?, ?, ?, 'saved', 'Imported; calculated when it is opened', ?, ?, ?)""",
                (pending_key, ' '.join(str(entry.get('name') or '').split())[:120], 1 if entry.get('pinned') else 0, position,
                 max(1, int(entry.get('use_count') or 1)), str(entry.get('last_used_at') or now),
                 json.dumps(refs, ensure_ascii=False), json.dumps(snapshot, ensure_ascii=False, separators=(',', ':')),
                 nr_mode, json.dumps(levels, ensure_ascii=False), selection['baseline_operator'], created_by or 'system', now, now),
            )
        added += 1
    _resolve_imported_filters(repository, package_keys, progress)
    return added


def _ready_cdr_hashes(repository: Repository, progress: Callable[[int, int], None] | None = None) -> dict[str, int]:
    """The processed CDRs of the workspace by the SHA-256 of their file (read once and kept, see file_sha256);
    ``progress(done, count)`` follows them."""
    from src.modules.scoring.scoring_history import ensure_history_tables, file_sha256
    by_hash: dict[str, int] = {}
    rows = [row for row in repository.list_datasets()
            if str(row['status'] or '').casefold() == 'ready' and str(row['dataset_kind'] or '').casefold() in CDR_DATASET_KINDS]
    if rows:
        ensure_history_tables(repository)
    for index, row in enumerate(rows):
        if progress:
            progress(index, len(rows))
        sha = file_sha256(repository, row)
        if sha:
            by_hash.setdefault(sha, int(row['id']))
    return by_hash


def _postal_twin_key(prepared: dict[str, Any]) -> str:
    """The key of a prepared selection with Postal Codes if it has none, or without them if it has them."""
    snapshot = prepared['snapshot']
    summary = dict(snapshot.get('area_summary') or {})
    if not summary.pop('postal_codes', False):
        summary['postal_codes'] = True
    filters = snapshot['context_filters']
    return saved_scoring_key([] if campaign_presets(filters.get('Campaign') or []) else prepared['dataset_ids'], prepared['levels'],
                            prepared['nr_mode'], prepared['baseline_operator'], filters, snapshot['scoring_profile_id'], summary)


def _resolve_imported_filters(repository: Repository, selection_keys: Iterable[str] | None = None,
                              progress: Callable[[str, float], None] | None = None) -> None:
    """Give the imported Saved Scorings their CDRs once every one of them is in the workspace (found by file); those
    with a Campaign choice (Latest campaign…) take the CDRs it stands for here once the workspace has them. One that
    matches a Saved Scoring of the workspace joins it. ``selection_keys`` keeps to some of them (those of an import),
    and ``progress(phase, share done)`` follows them; what they read alike is read once."""
    query = f"SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE dataset_ids_json = '[]' AND cdr_refs_json <> '[]'"
    keys = list(dict.fromkeys(selection_keys)) if selection_keys is not None else None
    if keys is not None and not keys:
        return
    with repository.connection() as connection:
        pending = connection.execute(query, ()).fetchall()
    if keys is not None:
        wanted = set(keys)
        pending = [row for row in pending if row['selection_key'] in wanted]
    if not pending:
        return
    items = [(row, _row_to_saved_scoring(row, include_snapshot=False)) for row in pending]
    by_file = [not campaign_presets(saved_scoring['context_filters'].get('Campaign') or []) for _row, saved_scoring in items]
    # The CDRs are found by the hash of their files first (most of the time when they are read for the first time).
    share = 0.5 if any(by_file) else 0.0
    by_hash: dict[str, int] = _ready_cdr_hashes(repository, (lambda done, count: progress(
        f'identifying CDR {done + 1} of {count} by its file', share * done / count)) if progress else None) if any(by_file) else {}
    cache: dict[Any, Any] = {}
    for index, ((row, saved_scoring), needs_files) in enumerate(zip(items, by_file)):
        if progress:
            progress(f'preparing Saved Scoring {index + 1} of {len(items)}', share + (1 - share) * index / len(items))
        if not needs_files:
            # Chosen when it is prepared, from the CDRs of this workspace.
            dataset_ids = []
        else:
            refs = _decode_json(row['cdr_refs_json'], [])
            dataset_ids = [by_hash.get(str(ref.get('sha256') or '')) for ref in refs if isinstance(ref, dict)]
            if not dataset_ids or not all(dataset_ids):
                continue
        try:
            prepared = _prepare_saved_scoring(
                repository, dataset_ids, saved_scoring['levels'], saved_scoring['nr_mode'],
                baseline_operator=saved_scoring['baseline_operator'], context_filters=saved_scoring['context_filters'],
                scoring_profile_id=saved_scoring['scoring_profile_id'] or None, area_summary=saved_scoring['area_summary'],
                cache=cache,
            )
        except ValueError:
            continue
        with repository.connection() as connection:
            existing = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?',
                                          (prepared['selection_key'],)).fetchone()
            # Another map of its Postal Codes is the same Saved Scoring too: it takes the one the import brings.
            brings_postal_codes = (existing is not None and postal_areas.wanted(prepared['snapshot']) and postal_areas.chosen_map(prepared['snapshot'])
                                   != postal_areas.chosen_map(_decode_json(existing['source_metadata_json'], {})))
            if existing is None:
                # With or without Postal Codes it is the same Saved Scoring: the option the import brings is added, to be
                # drawn when it is calculated again, and, as a star, the one of the workspace stays.
                existing = connection.execute(f'SELECT * FROM {SAVED_SCORINGS_TABLE} WHERE selection_key = ?',
                                              (_postal_twin_key(prepared),)).fetchone()
                brings_postal_codes = existing is not None and postal_areas.wanted(prepared['snapshot'])
            if existing is not None:
                if brings_postal_codes:
                    connection.execute(
                        f'UPDATE {SAVED_SCORINGS_TABLE} SET selection_key = ?, source_metadata_json = ? WHERE id = ?',
                        (prepared['selection_key'], json.dumps(prepared['snapshot'], ensure_ascii=False, separators=(',', ':')),
                         existing['id']))
                # The same selection: the Saved Scoring of the workspace takes the name of the import and its creator
                # (with the star it brings; a star of the workspace stays with whoever starred it).
                incoming_creator = str(row['created_by'] or '').strip()
                incoming_creator = '' if incoming_creator.casefold() in {'', 'system'} else incoming_creator
                metadata = _decode_json(row['source_metadata_json'], {})
                from_document = isinstance(metadata, dict) and bool(metadata.get('creator_from_document'))
                take_creator = bool(incoming_creator) and (bool(row['pinned']) or (from_document and not existing['pinned']))
                take_position = isinstance(metadata, dict) and bool(metadata.get('position_from_document'))
                connection.execute(
                    f"UPDATE {SAVED_SCORINGS_TABLE} SET name = CASE WHEN ? <> '' THEN ? ELSE name END, "
                    'created_by = CASE WHEN ? = 1 THEN ? ELSE created_by END, '
                    'pinned = MAX(pinned, ?), use_count = MAX(use_count, ?), '
                    # A Saved Scoring of the workspace takes the place the import gave it when the document says one or
                    # stars it here; else, a starred one stays where it is.
                    'position = CASE WHEN ? = 1 OR pinned = 0 OR position IS NULL THEN ? ELSE position END WHERE id = ?',
                    (row['name'] or '', row['name'] or '', int(take_creator), incoming_creator, row['pinned'],
                     row['use_count'], int(take_position), row['position'] if row['pinned'] else None, existing['id']),
                )
                connection.execute(f'DELETE FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (row['id'],))
                continue
            connection.execute(
                f"""UPDATE {SAVED_SCORINGS_TABLE} SET selection_key = ?, result_key = ?, method_version = ?,
                   source_fingerprint = ?, dataset_ids_json = ?, levels_json = ?, nr_mode = ?, baseline_operator = ?,
                   source_metadata_json = ?, cdr_refs_json = '[]', message = 'Calculated when it is opened'
                   WHERE id = ?""",
                (prepared['selection_key'], prepared['result_key'], prepared['method_version'],
                 prepared['source_fingerprint'], json.dumps(prepared['dataset_ids']),
                 json.dumps(prepared['levels'], ensure_ascii=False), prepared['nr_mode'], prepared['baseline_operator'],
                 json.dumps(prepared['snapshot'], ensure_ascii=False, separators=(',', ':')), row['id']),
            )


def convert_scoring_jobs(connection: Any) -> None:
    """Turn the Scoring Jobs of a workspace saved by earlier versions into Saved Scorings, once: the jobs of the same
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
            key = saved_scoring_key(dataset_ids, levels, row['nr_mode'], row['baseline_operator'],
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
            f"""INSERT OR IGNORE INTO {SAVED_SCORINGS_TABLE} (
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


def _campaign_sources(sources: list[dict[str, Any]], context_filters: dict[str, list[str]]) -> list[dict[str, Any]]:
    """The CDRs with tests of the campaigns of a Campaign filter (every CDR without one): the rows of the others are not
    read (By campaign, each methodology reads only the CDRs of its campaigns)."""
    chosen = {campaign_identity(value) for value in context_filters.get('Campaign') or [] if str(value).strip()}
    if not chosen:
        return list(sources)
    return [source for source in sources
            if not (campaigns := {campaign_identity(value) for value in source['metadata'].get('campaigns') or []})
            or campaigns & chosen]


def _filters_key(context_filters: dict[str, list[str]] | None) -> dict[str, list[str]]:
    """Context filters as a cache key: their values whatever their order and case."""
    return {field: sorted({str(value).strip().casefold() for value in values})
            for field, values in _normalize_context_filters(context_filters).items() if values}


def _load_source_frames(
    repository: Repository, sources: list[dict[str, Any]], progress_callback, required_columns,
    context_filters: dict[str, list[str]] | None = None, *, nr_mode_campaigns: bool = False, columnar: bool = False,
    kinds: Any = None, first_rows: dict[str, int] | None = None,
) -> dict[str, pd.DataFrame]:
    """The rows of the CDRs by type, with the context filters. With ``nr_mode_campaigns`` (NSA vs SA) each campaign
    names the NR Mode of its CDR and each row keeps it (``NR_MODE_COLUMN``), so the NSA and SA tests stay apart.

    With ``columnar``, when the columnar copies of the CDRs hold them, the rows are read from the copies of each CDR
    type at once (cdr_store.read_kind_frame): the same rows and values, the text columns as Categoricals.

    With ``kinds``, only the rows of those CDR types (the map of each type is worked out apart, see
    _draw_points_loss_apart): every CDR type is not required then, and ``first_rows`` (when given) tells the place in
    ``sources`` of the first CDR of each type with rows (the order of the types of the rows of every CDR type)."""
    from src.modules.cdr import cdr_store
    if columnar:
        if all(cdr_store.fresh_kind(repository.db_path, int(source['metadata']['dataset_id'])) for source in sources):
            try:
                return _load_source_frames(repository, sources, progress_callback, required_columns, context_filters,
                                           nr_mode_campaigns=nr_mode_campaigns, columnar=None, kinds=kinds,
                                           first_rows=first_rows)
            except _NotColumnar:
                if first_rows is not None:
                    first_rows.clear()
        columnar = False
    parts_by_kind: dict[str, list[dict[str, Any]]] = {}
    frames_by_kind: dict[str, list[pd.DataFrame]] = {}
    normalized_filters = _normalize_context_filters(context_filters)
    active_filters = {field: values for field, values in normalized_filters.items() if values}
    catalogues = repository.cdr_catalogues_by_dataset([int(source['metadata']['dataset_id']) for source in sources])
    vendor_operators = scoring_vendor_operators(catalogues, repository.list_operator_mapping_groups())
    from src.modules.network.map_area_columns import MAP_AREA_COLUMN, MAP_AREA_COUNTRY_COLUMN, current_datasets
    # The CDRs whose tests are placed in the current Map Areas give the map their areas.
    placed = current_datasets(repository, [int(source['metadata']['dataset_id']) for source in sources])
    total = max(1, len(sources))
    with_rows = {id(source) for source in _campaign_sources(sources, normalized_filters)}
    from src.modules.scoring.scoring_exclusions import load_scope
    exclusions = load_scope(repository)
    for index, source in enumerate(sources, start=1):
        dataset_id = int(source['metadata']['dataset_id'])
        if kinds is not None and str(source['metadata']['kind']) not in kinds:
            continue
        if id(source) not in with_rows:
            progress_callback(10 + round(index * 45 / total), f"Skipped {source['metadata']['name']} of other campaigns")
            continue
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
                if ValueSet(values).includes:
                    missing_filter_fields.append(field)
                # A filter that only leaves values out (every operator but Lebara) keeps a CDR without its column.
            else:
                if field == 'Vendor':
                    values = [scoring_vendor_name(value, vendor_operators) for value in values]
                dataset_filters[resolved_filter_column] = values
        # The calls of the Excluded Calls lists switched on for the CDR are left out.
        excluded_call_lists = exclusions.list_ids_for(dataset_id)
        if columnar is None:
            # Only the rows to read (cdr_store.read_kind_frame reads them for every CDR of the type at once).
            plan = None if missing_filter_fields else repository.dataset_rows_plan(
                dataset_id, list(dict.fromkeys(selected_columns)), dataset_filters,
                **({'excluded_call_lists': excluded_call_lists} if excluded_call_lists else {}), in_scope_only=True,
            )
            kind = str(source['metadata']['kind'])
            rowids = [] if plan is None else cdr_store.plan_rows(
                repository.db_path, cdr_store.fresh_kind(repository.db_path, dataset_id), dataset_id, plan[0],
                ' AND '.join(plan[1]), plan[2], plan[3])
            if rowids is None:
                raise _NotColumnar()
            if not rowids:
                if not active_filters and not excluded_call_lists:
                    raise _source_error(f"Dataset '{source['metadata']['name']}' has no rows available for scoring.", index)
                progress_callback(10 + round(index * 45 / total), f"Skipped {source['metadata']['name']} with no matching rows")
                continue
            part = {'dataset_id': dataset_id, 'selected': plan[0], 'rowids': rowids}
            if nr_mode_campaigns:
                mode = str(source['metadata']['nr_mode'])
                campaign_column = resolve_column_name([requested for requested, _column in plan[0]], 'Campaign')
                if campaign_column is not None:
                    part['transforms'] = {campaign_column: partial(campaign_with_nr_mode, nr_mode=mode)}
                part['constants'] = {NR_MODE_COLUMN: mode}
            parts_by_kind.setdefault(kind, []).append(part)
            if first_rows is not None:
                first_rows.setdefault(kind, index)
            progress_callback(10 + round(index * 45 / total), f"Loaded {source['metadata']['name']}")
            continue
        if missing_filter_fields:
            frame = pd.DataFrame()
        else:
            # The operators out of scope in the NR Mode of the CDR (the NR Modes of the Operator Maps) are left out.
            frame = repository.load_dataset_rows(
                dataset_id, list(dict.fromkeys(selected_columns)), dataset_filters,
                **({'excluded_call_lists': excluded_call_lists} if excluded_call_lists else {}), in_scope_only=True,
            )
        if frame.empty:
            if not active_filters and not excluded_call_lists:
                raise _source_error(f"Dataset '{source['metadata']['name']}' has no rows available for scoring.", index)
            progress_callback(10 + round(index * 45 / total), f"Skipped {source['metadata']['name']} with no matching rows")
            continue
        kind = str(source['metadata']['kind'])
        if nr_mode_campaigns:
            mode = str(source['metadata']['nr_mode'])
            campaign_column = resolve_column_name(frame.columns, 'Campaign')
            if campaign_column is not None:
                frame[campaign_column] = frame[campaign_column].map(
                    {value: campaign_with_nr_mode(value, mode) for value in frame[campaign_column].dropna().unique()}
                ).where(frame[campaign_column].notna(), frame[campaign_column])
            frame[NR_MODE_COLUMN] = mode
        frames_by_kind.setdefault(kind, []).append(frame)
        if first_rows is not None:
            first_rows.setdefault(kind, index)
        progress_callback(10 + round(index * 45 / total), f"Loaded {source['metadata']['name']}")

    if columnar is None:
        frames = {kind: cdr_store.read_kind_frame(repository.db_path, kind, parts)[0] for kind, parts in parts_by_kind.items()}
        frames_by_kind = {kind: [frame] for kind, frame in frames.items()}
    missing = _missing_kinds(context_filters, frames_by_kind) if kinds is None else None
    if missing:
        raise ValueError(missing)
    return {
        kind: frames[0] if columnar is None else pd.concat(frames, ignore_index=True, sort=False)
        for kind, frames in frames_by_kind.items()
    }


class _NotColumnar(Exception):
    """The columnar copy cannot give the rows of a CDR (see _load_source_frames)."""


def _source_error(message: str, index: int) -> ValueError:
    """The error of the CDR at ``index`` (from 1) of the sources read: of several CDR types read apart, the error of the
    first CDR is the one reading them all at once would give."""
    error = ValueError(message)
    error.source_index = index
    return error


def _missing_kinds(context_filters: dict[str, list[str]] | None, frames_by_kind: Any) -> str | None:
    """Why the context filters leave no rows: every CDR type is required when a filter chooses values (filters that only
    leave values out, such as the operators the Operator Maps exclude, choose no CDR type); None when nothing is missing."""
    if not any(ValueSet(values).includes for values in _normalize_context_filters(context_filters).values() if values):
        return None
    labels = {'data': 'Data', 'voice': 'Voice', 'speech': 'Speech'}
    missing_kinds = [kind for kind in ('data', 'voice', 'speech') if not frames_by_kind.get(kind)]
    if not missing_kinds:
        return None
    return ('Scoring context filters leave no matching processed rows for every required CDR type. '
            f"Missing: {', '.join(labels[kind] for kind in missing_kinds)}.")


def _attach_mapping_boundaries(repository: Repository, dataset_ids: list[int], result: dict[str, Any]) -> None:
    """Save the Clusters and Region Mapping polygons applied to the CDRs for the points-lost maps."""
    document = result.get('points_loss')
    if not isinstance(document, dict):
        return
    from src.modules.scoring.scoring_points_loss import mapping_boundaries

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
        document.setdefault('boundaries', {}).update(boundaries)


def calculate_saved_scoring(repository: Repository, filter_id: int,
                           submit_points_loss: Callable[[Callable[[], None]], Any] | None = None,
                           work_waiting: Callable[[], bool] | None = None) -> dict[str, Any] | None:
    """Calculate the queued result of a Saved Scoring, save it, and keep a failure with its reason.

    A result from the Scoring History gets its Points Lost Map from the rows of the tests afterwards: with
    ``submit_points_loss`` as a job of its own (so the calculations waiting do not wait for it, and with
    ``work_waiting`` it gives way to those queued while it is drawn; see queue_points_loss), else at once.
    """
    saved_scoring = get_saved_scoring(repository, filter_id, include_internal_snapshot=True)
    if saved_scoring is None:
        return None
    if saved_scoring['status'] == 'completed':
        return get_saved_scoring(repository, filter_id, include_result=True)
    if saved_scoring['status'] == 'processing':
        return saved_scoring
    now = local_now_iso()
    _update_saved_scoring(
        repository, filter_id, status='processing', progress=2,
        message='Checking selected CDR datasets', last_error='', started_at=now,
    )

    def update_progress(progress: int, message: str) -> None:
        if get_saved_scoring(repository, filter_id) is None:
            raise _SavedScoringDeleted()
        _update_saved_scoring(
            repository, filter_id, progress=max(2, min(95, int(progress))), message=message,
        )

    try:
        # Its Main Cities are those of the workspace when it is calculated; a City breakdown scores the cities of its City
        # filter and its Separate cities only.
        # The National & Country Areas Trends score their own Areas and Cities on their own when they have some; the
        # Country Areas tab those of Country Areas.
        requested = saved_scoring.get('area_summary')
        main_cities = _workspace_main_cities(repository)
        saved_scoring['area_summary'] = with_breakdown_cities(
            resolve_main_cities(trend_area_summary(requested), main_cities), saved_scoring.get('context_filters'))
        if isinstance(requested, dict) and 'trend_cities' in requested:
            saved_scoring['geographical_areas'] = with_breakdown_cities(
                resolve_main_cities(country_area_summary(requested), main_cities), saved_scoring.get('context_filters'))
        configuration = saved_scoring.get('configuration')
        if configuration is None:
            raise ValueError(
                'This Saved Scoring has no saved methodology. Import the Scoring & GAP Analysis Methodologies and calculate it again.'
            )
        current_version = _method_version(configuration)
        if current_version != saved_scoring['method_version']:
            raise ValueError(
                'The scoring methodology changed after this calculation was queued. Calculate it again.')
        configuration = validate_scoring_configuration(configuration)
        dataset_ids = [int(value) for value in saved_scoring['dataset_ids']]
        sources, _campaigns, current_fingerprint = _source_snapshot(
            repository, dataset_ids, expected_nr_mode=saved_scoring['nr_mode'],
        )
        if current_fingerprint != saved_scoring['source_fingerprint']:
            raise ValueError('A selected CDR changed after this calculation was queued. Calculate it again.')
        engine = _scoring_engine()
        context_filters = saved_scoring.get('resolved_context_filters', saved_scoring.get('context_filters', {}))
        groups = saved_scoring.get('methodology_groups') or []
        # A part already calculated for the same selection is taken from that result: only the rest is calculated.
        given = _given_parts(repository, saved_scoring)
        if given:
            saved_scoring['area_summary'] = {**saved_scoring['area_summary'], **{part: False for part in given[0]}}
        # Country Areas and Scoring Trends switched off are not calculated (nor the rows of the whole country read for them).
        areas_on = area_summary_part_enabled(saved_scoring.get('area_summary'), 'country_areas')
        trends_on = area_summary_part_enabled(saved_scoring.get('area_summary'), 'trends')
        trends = saved_scoring.get('area_trends') if saved_scoring.get('area_summary') and trends_on else None
        # National & Geographical Areas Trends with campaigns of their own are scored apart, from the CDRs of those
        # campaigns; the Geographical Areas of the job keep their Breakdown and Separate cities.
        job_filter = ({**saved_scoring, 'area_summary': None,
                       'geographical_areas': saved_scoring.get('geographical_areas') or saved_scoring.get('area_summary')}
                      if trends or not trends_on else saved_scoring)
        if not areas_on:
            job_filter = {**job_filter, 'geographical': False}
        if len(groups) > 1:
            # By campaign: the campaigns of each methodology are scored with it, then put together.
            from src.modules.scoring.scoring_methodologies import merge_results
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
            summary = _trend_area_summary(repository, saved_scoring, trends, configuration, context_filters, engine,
                                          update_progress)
            result['warnings'] = [*(result.get('warnings') or []), *summary.pop('warnings', [])]
            result['area_summary'] = summary
        nns_request = requested_nns_breakdown(saved_scoring.get('area_summary'))
        if nns_request and saved_scoring.get('nns_sources'):
            breakdown = _nns_breakdown(repository, saved_scoring, nns_request, saved_scoring['nns_sources'], configuration,
                                       context_filters, engine, update_progress)
            result['warnings'] = [*(result.get('warnings') or []), *breakdown.get('warnings', [])]
            result[NNS_KEY] = breakdown
        if given:
            parts, source = given
            for part in parts:
                result[_PART_RESULTS[part]] = source[_PART_RESULTS[part]]
            if 'trends' in parts:
                result['warnings'] = [*(result.get('warnings') or []), *(warning for warning in source.get('warnings') or []
                                                                         if _is_trend_warning(warning))]
            # (Its own area summary again: the one it is shown and exported with.)
            saved_scoring['area_summary'] = {key: value for key, value in saved_scoring['area_summary'].items() if key not in parts}
        if warning := _campaigns_without_tests_warning(saved_scoring, context_filters, result):
            result['warnings'] = [*(result.get('warnings') or []), warning]
        # The calls the Excluded Calls lists leave out of its CDRs.
        from src.modules.scoring.scoring_exclusions import load_scope, summary_warning
        excluded_calls = load_scope(repository).summary(dataset_ids)
        if excluded_calls:
            result['excluded_calls'] = excluded_calls
            if warning := summary_warning(excluded_calls):
                result['warnings'] = [*(result.get('warnings') or []), warning]
        if postal_areas.wanted(saved_scoring) and not map_pending:
            # Postal Codes are only placed while the map is drawn apart (the scores never need them).
            result['points_loss'] = {'version': 2, 'pending': True}
            map_pending = True
        _save_scoring_result(repository, saved_scoring, filter_id, dataset_ids, configuration, result,
                             points_loss_pending=map_pending)
        if map_pending and _complete_points_loss(
                repository, saved_scoring, filter_id, [dict(source) for source in sources], dataset_ids, configuration,
                context_filters, engine, groups, cached_only=True):
            # The maps of its CDRs and methodologies were drawn before: it is complete at once.
            map_pending = False
        if map_pending:
            # The Points Lost Map needs the rows of the tests: it is added once they are read.
            if submit_points_loss is None:
                complete_saved_scoring_points_loss(repository, filter_id)
            else:
                queue_points_loss(repository, filter_id, submit_points_loss, work_waiting)
    except _SavedScoringDeleted:
        return None
    except Exception as exc:
        _fail_calculation(repository, saved_scoring, filter_id, exc)
    return get_saved_scoring(repository, filter_id, include_result=True)


def _campaigns_without_tests_warning(saved_scoring: dict[str, Any], context_filters: dict[str, list[str]],
                                     result: dict[str, Any]) -> str | None:
    """The warning of the chosen campaigns the other filters leave no test of (26-Q4 without tests in the City
    chosen): the Campaign filter lists every campaign, so it tells why they add nothing to the results."""
    from src.modules.cdr.column_names import format_campaign

    chosen = [str(value) for value in context_filters.get('Campaign') or [] if str(value or '').strip()
              and not str(value).startswith('@')]
    if not chosen or _compares_nr_modes(saved_scoring) or not isinstance(result.get('campaigns'), list):
        return None
    measured = {campaign_identity(value) for value in result['campaigns']}
    missing = list(dict.fromkeys(format_campaign(value) or value for value in chosen if campaign_identity(value) not in measured))
    if not missing:
        return None
    fields = [field for field, values in context_filters.items() if field != 'Campaign' and values]
    which = f"the {', '.join(fields)} filter{'s' if len(fields) > 1 else ''}" if fields else 'the filters'
    return (f"{', '.join(missing)}: no tests with {which} of this calculation; "
            f"{'they add' if len(missing) > 1 else 'it adds'} nothing to the results.")


def _trend_area_summary(repository: Repository, saved_scoring: dict[str, Any], trends: dict[str, Any],
                        configuration: dict[str, Any], context_filters: dict[str, list[str]], engine: Any,
                        update_progress: Callable[[int, str], None]) -> dict[str, Any]:
    """National & Geographical Areas Trends with campaigns of their own: the CDRs of those campaigns scored with the job's filters
    (its campaigns aside) and methodology (each campaign with its own By campaign), split by Operator and Campaign. The
    trends of the same CDRs, methodology and options calculated before (by this Saved Scoring or another one) are reused."""
    area_summary = saved_scoring['area_summary']
    dataset_ids = [int(value) for value in trends.get('dataset_ids') or []]
    sources, _campaigns, fingerprint = _source_snapshot(repository, dataset_ids, expected_nr_mode=saved_scoring['nr_mode'])
    if fingerprint != trends.get('source_fingerprint'):
        raise ValueError('A CDR of the National & Country Areas Trends changed after this calculation was queued. Calculate it again.')
    # Split as the National calculation of the summary, which then reuses this one.
    levels = ['Operator'] if area_summary.get('time_split') == 'All' else ['Operator', 'Campaign']
    # Scored on the whole country, whatever the job's area filters; the Geographical views are the job's own.
    filters = {**whole_country_filters(context_filters), 'Campaign': list(trends.get('campaigns') or [])}
    from src.modules.scoring import scoring as scoring_engine
    from src.modules.scoring import scoring_cache
    key = None
    if engine is scoring_engine:
        key = scoring_cache.key_of({
            'kind': 'trends', 'method_version': scoring_engine.METHOD_VERSION,
            'geographical_version': GEOGRAPHICAL_AREAS_VERSION, 'sources': fingerprint, 'levels': levels,
            'filters': _filters_key(filters), 'area_summary': area_summary,
            'methodology': [trends.get('configuration_hash'), configuration_hash(trends.get('configuration') or configuration)],
            'baseline_operator': saved_scoring['baseline_operator'], 'baseline_aliases': saved_scoring.get('baseline_aliases', []),
            'operator_mappings': saved_scoring.get('operator_mappings', {}),
            'operator_groups': repository.list_operator_mapping_groups(),
            **({'nr_mode_campaigns': True} if _compares_nr_modes(saved_scoring) else {}),
        })
        cached = scoring_cache.read(repository, 'trends', key)
        if cached is not None:
            update_progress(95, 'National & Country Areas Trends: reused from a calculation of the same CDRs and methodology')
            return cached
    trend_filter = {**saved_scoring, 'dataset_ids': dataset_ids, 'levels': levels, 'source_fingerprint': fingerprint,
                    'geographical': False}

    def progress(value: int, message: str) -> None:
        update_progress(88 + round(value * 7 / 100), f'National & Country Areas Trends: {message}')
    groups = trends.get('methodology_groups') or []
    if len(groups) > 1:
        from src.modules.scoring.scoring_methodologies import merge_results
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
    if key is not None:
        summary = _serialize_result_value(summary)
        scoring_cache.write(repository, 'trends', key, summary)
    return summary


def _nns_sources(repository: Repository, nr_mode: str, request: dict[str, Any],
                 scoring_profile_id: str | None) -> dict[str, Any]:
    """The campaigns, CDRs and methodologies of each NR Mode of an NNS Break-down (an automatic choice such as Latest 4
    campaigns stands for its campaigns now), and the Master Grid it reads."""
    from src.modules.network import master_grid
    from src.modules.scoring.scoring_methodologies import BY_CAMPAIGN, methodology_groups
    from src.modules.scoring.scoring_nns_breakdown import job_modes
    from src.modules.scoring.scoring_selection import auto_scoring_cdr_ids, expand_scoring_campaigns
    modes = []
    for mode in job_modes(nr_mode):
        campaigns = expand_scoring_campaigns(repository, mode, request['campaigns'])
        dataset_ids = auto_scoring_cdr_ids(repository, mode, request['campaigns'])
        entry: dict[str, Any] = {'nr_mode': mode, 'campaigns': list(campaigns), 'dataset_ids': list(dataset_ids),
                                 'source_fingerprint': ''}
        if dataset_ids:
            sources, _campaigns, entry['source_fingerprint'] = _source_snapshot(repository, dataset_ids, expected_nr_mode=mode)
            if scoring_profile_id == BY_CAMPAIGN:
                # Each campaign with the methodology that applies to it, as the job's own campaigns.
                wanted = {value.casefold() for value in campaigns}
                found = [campaign for source in sources for campaign in source['metadata'].get('campaigns') or []
                         if not wanted or campaign.casefold() in wanted]
                groups = methodology_groups(repository.get_scoring_profiles(), found or [''])
                entry['methodology_groups'] = groups
                entry['configuration_hash'] = hashlib.sha256(json.dumps(
                    [[group['profile_id'], configuration_hash(group['configuration']), group['campaigns']] for group in groups],
                    sort_keys=True).encode('utf-8')).hexdigest()
        modes.append(entry)
    if not any(entry['dataset_ids'] for entry in modes):
        raise ValueError(f'NNS Break-down: the chosen campaigns have no Data, Voice and Speech CDRs of {nr_mode_label(nr_mode)} now.')
    return {'modes': modes, 'master_grid': master_grid.latest_dataset(repository), 'version': NNS_VERSION}


def _nns_breakdown(repository: Repository, saved_scoring: dict[str, Any], request: dict[str, Any], nns: dict[str, Any],
                   configuration: dict[str, Any], context_filters: dict[str, list[str]], engine: Any,
                   update_progress: Callable[[int, str], None]) -> dict[str, Any]:
    """The NNS Break-down of a job (see scoring_nns_breakdown): for each NR Mode, the CDRs of its campaigns scored with
    the job's filters (its areas and campaigns aside) and methodology, split by Region and area (a city, or the
    connecting roads) and, for the latest campaign, by city size and scenario; with the serving sites of each area. The
    same CDRs, methodology, Master Grid and options calculated before are reused."""
    from src.modules.network import master_grid
    from src.modules.scoring import scoring as scoring_engine
    from src.modules.scoring import scoring_cache
    from src.modules.scoring import scoring_nns_breakdown as nb

    grid = nns.get('master_grid')
    current = master_grid.latest_dataset(repository)
    if (current or {}).get('id') != (grid or {}).get('id') or (current or {}).get('processed_at') != (grid or {}).get('processed_at'):
        raise ValueError('The Master Grid changed after this calculation was queued. Calculate it again.')
    filters = whole_country_filters(context_filters)
    filters.pop('Campaign', None)
    key = None
    if engine is scoring_engine:
        key = scoring_cache.key_of({
            'kind': 'nns', 'version': NNS_VERSION, 'method_version': scoring_engine.METHOD_VERSION, 'request': request,
            'sources': [[entry['nr_mode'], entry['source_fingerprint'], entry.get('configuration_hash', '')]
                        for entry in nns['modes']],
            'methodology': configuration_hash(configuration), 'master_grid': grid, 'filters': _filters_key(filters),
            'baseline_operator': saved_scoring['baseline_operator'], 'baseline_aliases': saved_scoring.get('baseline_aliases', []),
            'operator_mappings': saved_scoring.get('operator_mappings', {}),
            'operator_groups': repository.list_operator_mapping_groups(),
        })
        cached = scoring_cache.read(repository, 'nns', key)
        if cached is not None:
            update_progress(96, 'NNS Break-down: reused from a calculation of the same CDRs, methodology and Master Grid')
            return cached
    lookup = master_grid.site_lookup(master_grid.load_sites(repository, grid['id'])) if grid else {}
    breakdown: dict[str, Any] = {'version': NNS_VERSION, 'request': request, 'master_grid': grid, 'modes': [],
                                 'areas': [], 'sites': [], 'scenarios': [], 'warnings': []}
    if not grid:
        breakdown['warnings'].append(f'{nb.WARNING_PREFIX} no Master Grid in the workspace: the NNS sites have no capacity '
                                     'and no NNS site is planned.')
    calculate = engine.calculate_scoring
    required_columns = getattr(engine, 'load_input_columns', None) or getattr(engine, 'required_input_columns')
    parameters = inspect.signature(calculate).parameters
    total = max(1, len(nns['modes']))
    for index, entry in enumerate(nns['modes']):
        mode = entry['nr_mode']

        def progress(value: int, message: str, index: int = index, mode: str = mode) -> None:
            update_progress(95 + round((index + value / 100) * 4 / total), f'NNS Break-down ({mode}): {message}')
        if not entry['dataset_ids']:
            breakdown['warnings'].append(f'{nb.WARNING_PREFIX} the chosen campaigns have no {mode} Data, Voice and Speech CDRs.')
            continue
        sources, _campaigns, fingerprint = _source_snapshot(repository, entry['dataset_ids'], expected_nr_mode=mode)
        if fingerprint != entry['source_fingerprint']:
            raise ValueError('A CDR of the NNS Break-down changed after this calculation was queued. Calculate it again.')
        for source in sources:
            source['levels'] = ['Operator', 'Campaign', 'Region', *nb.FIELDS]
        frames = _load_source_frames(repository, sources, progress, required_columns,
                                     {**filters, 'Campaign': list(entry['campaigns'])})
        classified = {kind: nb.classify(frame, lookup, request) for kind, frame in frames.items()}
        classified = {kind: frame for kind, frame in classified.items() if len(frame)}
        if not classified:
            breakdown['warnings'].append(f'{nb.WARNING_PREFIX} the {mode} CDRs have no tests in the chosen Regions.')
            continue
        campaign_of = {kind: frame[resolve_column_name(frame.columns, 'Campaign')].astype(object).astype(str).str.strip()
                       for kind, frame in classified.items() if resolve_column_name(frame.columns, 'Campaign') is not None}
        found = nb.sort_campaigns(value for values in campaign_of.values() for value in values.unique() if value and value != 'nan')
        latest = found[-1] if found else ''
        groups = entry.get('methodology_groups') or [{'campaigns': found, 'configuration': configuration}]
        areas: dict[tuple, dict[str, Any]] = {}
        scenarios: dict[tuple, dict[str, Any]] = {}
        details = nb.area_details(classified)

        def of_campaigns(campaigns: list[str]) -> dict[str, pd.DataFrame]:
            wanted = {str(value).strip().casefold() for value in campaigns}
            chosen = {}
            for kind, frame in classified.items():
                if kind in campaign_of:
                    mask = campaign_of[kind].str.casefold().isin(wanted).to_numpy(dtype=bool)
                    if mask.any():
                        chosen[kind] = frame[mask]
            return chosen
        for group_index, group in enumerate(groups):
            group_configuration = validate_scoring_configuration(group['configuration'])
            kwargs = _engine_kwargs(repository, saved_scoring, group_configuration, calculate)
            if 'with_points_loss' in parameters:
                kwargs['with_points_loss'] = False
            if 'with_global_kpis' in parameters:
                # Only the totals and the tests of each area are shown, not the KPIs of all its environments.
                kwargs['with_global_kpis'] = False
            group_frames = of_campaigns(group['campaigns'])
            if not group_frames:
                continue
            latest_frames = of_campaigns([latest]) if latest in group['campaigns'] or len(groups) == 1 else {}
            # The cities and the connecting roads are scored apart: each area, measured in one environment, is scaled to
            # the full points (as the areas of Country Areas).
            for kind in (nb.CITY_KIND, nb.ROAD_KIND):
                kind_frames = nb.of_kind(group_frames, kind)
                if not kind_frames:
                    continue
                progress(60 + round(group_index * 30 / len(groups)),
                         'Scoring each city' if kind == nb.CITY_KIND else 'Scoring the connecting roads')
                result = calculate(nb.scoring_frames(kind_frames, '__nns_area'), ['Operator', 'Campaign', 'Region', 'City'], **kwargs)
                reliable = scoring_engine.most_reliable_result(result, saved_scoring['baseline_operator'], group_configuration)
                for (campaign, operator, region, area), values in nb.scores(
                        result, reliable, ('campaign', 'operator', 'region', 'city')).items():
                    area_kind, size = details.get((region, area), ('', ''))
                    row = areas.setdefault((region, area, operator), {
                        'nr_mode': mode, 'region': region, 'area': area, 'kind': area_kind, 'size': size,
                        'operator': operator, 'campaigns': {}})
                    row['campaigns'][campaign] = values
                kind_latest = nb.of_kind(latest_frames, kind)
                if kind_latest:
                    progress(80, 'Scoring the latest campaign by city size and scenario')
                    result = calculate(nb.scoring_frames(kind_latest, '__nns_size'), ['Operator', 'City', 'Cluster'], **kwargs)
                    reliable = scoring_engine.most_reliable_result(result, saved_scoring['baseline_operator'], group_configuration)
                    for (operator, size, scenario), values in nb.scores(result, reliable, ('operator', 'city', 'cluster')).items():
                        scenarios[(size, scenario, operator)] = {'nr_mode': mode, 'campaign': latest, 'size': size,
                                                                 'scenario': scenario, 'operator': operator, **values}
        counts = nb.site_counts(of_campaigns([latest]), lookup) if latest else {}
        breakdown['modes'].append({'nr_mode': mode, 'campaigns': found, 'latest_campaign': latest})
        breakdown['areas'].extend(areas.values())
        breakdown['scenarios'].extend(scenarios.values())
        breakdown['sites'].extend({'nr_mode': mode, 'region': region, 'area': area, **counts_of}
                                  for (region, area), counts_of in counts.items())
    breakdown['scenario_order'] = nb.scenario_order(row['scenario'] for row in breakdown['scenarios'])
    if key is not None:
        breakdown = _serialize_result_value(breakdown)
        scoring_cache.write(repository, 'nns', key, breakdown)
    return breakdown


def _scoring_result(repository: Repository, saved_scoring: dict[str, Any], configuration: dict[str, Any],
                    dataset_ids: list[int], sources: list[dict[str, Any]], context_filters: dict[str, list[str]],
                    engine: Any, update_progress: Callable[[int, str], None]) -> tuple[dict[str, Any], bool]:
    """The scoring (and area summary) of a Saved Scoring with one methodology, and whether it came from the Scoring
    History (its Points Lost Map then follows from the rows of the tests)."""
    result = _history_result(repository, saved_scoring, configuration, dataset_ids, context_filters, engine,
                             update_progress)
    if result is not None:
        return result, True
    if saved_scoring.get('history_gap'):
        # Every step says why the rows of the CDRs are read (and the Scoring History not used).
        reason = saved_scoring['history_gap']
        report = update_progress
        update_progress = lambda progress, message: report(progress, f'{message} (from the CDR rows: {reason})')
    update_progress(6, 'Reading processed CDR rows')
    # The points-lost map also reads the area and coordinate columns.
    required_columns = getattr(engine, 'load_input_columns', None) or getattr(engine, 'required_input_columns')
    # The area summary also reads its breakdown and City columns, and the test start time for its time split; the
    # Geographical views read those of their Breakdown and Separate cities.
    extra = area_summary_levels(saved_scoring['levels'], saved_scoring.get('area_summary'))
    if saved_scoring.get('geographical', True):
        extra = [*extra, *(level for level in geographical_levels(saved_scoring['levels'], _geographical_areas(saved_scoring))
                           if level not in extra)]
    for source in sources:
        source['levels'] = [*saved_scoring['levels'], *extra]
    nr_mode_campaigns = _compares_nr_modes(saved_scoring)
    frames = _load_source_frames(repository, sources, update_progress, required_columns, context_filters,
                                 nr_mode_campaigns=nr_mode_campaigns)
    _current_sources, _campaigns, post_load_fingerprint = _source_snapshot(
        repository, dataset_ids, expected_nr_mode=saved_scoring['nr_mode'],
    )
    if post_load_fingerprint != saved_scoring['source_fingerprint']:
        raise ValueError('A selected CDR changed while its scoring rows were being loaded.')
    update_progress(62, 'Calculating KPIs and interpolated scores')
    calculate = engine.calculate_scoring
    call_kwargs = _engine_kwargs(repository, saved_scoring, configuration, calculate)
    result = calculate(frames, saved_scoring['levels'], **call_kwargs)
    if not isinstance(result, dict):
        raise TypeError('The scoring engine must return a result object.')
    job_filtered = has_area_filters(context_filters)
    # The Geographical Areas & Scoring Trends are scored on the whole country: a job with area filters reads its rows apart.
    country_frames = frames
    if job_filtered and (saved_scoring.get('area_summary') or saved_scoring.get('geographical', True)):
        update_progress(87, 'Reading the CDR rows of the whole country for the Country Areas & Scoring Trends')
        country_frames = _load_source_frames(repository, [dict(source) for source in sources], lambda *_args: None,
                                             required_columns, whole_country_filters(context_filters),
                                             nr_mode_campaigns=nr_mode_campaigns)
    if saved_scoring.get('area_summary'):
        summary = calculate_area_summary(calculate, country_frames, saved_scoring['levels'],
                                         saved_scoring['area_summary'], call_kwargs, update_progress, job_filtered=job_filtered)
        result['warnings'] = [*(result.get('warnings') or []), *summary.pop('warnings')]
        result['area_summary'] = summary
    if saved_scoring.get('geographical', True):
        # Its Breakdown and Separate cities on the whole country: those equal to the job's own calculation or to one of
        # the summary (the same rows) are read from them.
        geographical = calculate_geographical(calculate, country_frames, saved_scoring['levels'], call_kwargs, update_progress,
                                              result.get('area_summary'), _geographical_areas(saved_scoring),
                                              reuse_job=not job_filtered)
        if geographical:
            result['geographical'] = geographical
    return result, False


def calculate_selection(repository: Repository, campaigns: list[str], levels: list[str], nr_mode: str, *,
                        context_filters: dict[str, list[str]] | None = None, baseline_operator: str = DEFAULT_BASELINE_OPERATOR,
                        scoring_profile_id: str | None = 'by-campaign',
                        progress: Callable[[int, str], None] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The scoring of a selection calculated at once, as a Saved Scoring of the same selection calculates it (the
    AI Assistant), without saving one: the complete campaigns of the NR Mode choose the CDRs, each campaign is scored
    with the methodology that applies to it, and the Scoring History is used when it covers the selection (else the
    rows of the CDRs are read). Neither the Geographical Areas nor the trends of a Saved Scoring are calculated.

    Returns the result and the selection it was calculated for (its CDRs, campaigns, methodology and filters)."""
    from src.modules.scoring.scoring_selection import scoring_auto_cdrs

    report = progress or (lambda _value, _message: None)
    filters = {key: list(values) for key, values in (context_filters or {}).items() if values}
    chosen = scoring_auto_cdrs(repository, nr_mode, {'Campaign': list(campaigns)}, fields=['Campaign'])
    dataset_ids = list(chosen['dataset_ids'])
    if not dataset_ids:
        raise ValueError('No campaign with Data, Voice and Speech CDRs matches this selection.')
    filters['Campaign'] = list(chosen['campaign_selection'] or campaigns)
    prepared = _prepare_saved_scoring(repository, dataset_ids, levels, chosen['nr_mode'], baseline_operator=baseline_operator,
                                     context_filters=filters, scoring_profile_id=scoring_profile_id)
    snapshot = prepared['snapshot']
    job = {'levels': prepared['levels'], 'nr_mode': prepared['nr_mode'], 'baseline_operator': prepared['baseline_operator'],
           'baseline_aliases': snapshot.get('baseline_aliases', []), 'operator_mappings': snapshot.get('operator_mappings', {}),
           'source_fingerprint': prepared['source_fingerprint'], 'geographical': False}
    sources, _campaigns, _fingerprint = _source_snapshot(repository, prepared['dataset_ids'], expected_nr_mode=prepared['nr_mode'])
    context = snapshot['resolved_context_filters']
    engine = _scoring_engine()
    groups = snapshot.get('methodology_groups') or []
    if len(groups) > 1:
        from src.modules.scoring.scoring_methodologies import merge_results
        parts = []
        for group in groups:
            configuration = validate_scoring_configuration(group['configuration'])
            calculation = {**job, 'configuration': configuration}
            part, _from_history = _scoring_result(repository, calculation, configuration, prepared['dataset_ids'],
                                                  [dict(source) for source in sources],
                                                  {**context, 'Campaign': list(group['campaigns'])}, engine, report)
            job['history_gap'] = job.get('history_gap') or calculation.get('history_gap', '')
            parts.append((group, part))
        result = merge_results(parts)
    else:
        configuration = validate_scoring_configuration(snapshot['configuration'])
        calculation = {**job, 'configuration': configuration}
        result, _from_history = _scoring_result(repository, calculation, configuration, prepared['dataset_ids'], sources,
                                                context, engine, report)
        job['history_gap'] = calculation.get('history_gap', '')
    # The campaigns calculated (those an automatic choice such as Latest campaign stands for now).
    resolved_campaigns = [str(value) for value in context.get('Campaign') or [] if not str(value).startswith('@')]
    selection = {
        'dataset_ids': prepared['dataset_ids'], 'campaigns': resolved_campaigns or list(chosen['campaign_selection'] or campaigns),
        'nr_mode': prepared['nr_mode'], 'levels': prepared['levels'], 'baseline_operator': prepared['baseline_operator'],
        'context_filters': snapshot['context_filters'], 'methodology': snapshot.get('scoring_profile_name') or '',
        'methodology_groups': [{'methodology': group.get('profile_name') or '', 'campaigns': list(group.get('campaigns') or [])}
                               for group in groups],
        'history_gap': job.get('history_gap', ''),
    }
    return result, selection


def _compares_nr_modes(saved_scoring: dict[str, Any]) -> bool:
    """Whether a Saved Scoring scores NSA vs SA (each campaign with the NR Mode of its CDRs)."""
    return normalize_scoring_nr_mode(saved_scoring.get('nr_mode')) == NSA_VS_SA


def _geographical_areas(saved_scoring: dict[str, Any]) -> dict[str, Any] | None:
    """The Breakdown and Separate cities of the Geographical Areas & Scoring Trends of a Saved Scoring (those of the job
    when its trends, with campaigns of their own, are scored apart)."""
    areas = saved_scoring.get('geographical_areas') or saved_scoring.get('area_summary')
    return areas if isinstance(areas, dict) else None


def _engine_kwargs(repository: Repository, saved_scoring: dict[str, Any], configuration: dict[str, Any],
                   calculate: Callable[..., Any]) -> dict[str, Any]:
    """The options of the engine's calculation: reference, methodology, operator names and Map Areas."""
    parameters = inspect.signature(calculate).parameters
    call_kwargs = {
        'baseline_operator': saved_scoring['baseline_operator'],
        'configuration': configuration,
    }
    accepts_keywords = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
    if 'operator_mappings' in parameters or accepts_keywords:
        call_kwargs['operator_mappings'] = saved_scoring.get('operator_mappings', {})
    if 'baseline_aliases' in parameters or accepts_keywords:
        call_kwargs['baseline_aliases'] = saved_scoring.get('baseline_aliases', [])
    if 'map_areas' in parameters:
        # The tests are placed in the workspace's Map Areas of their country (the ITL3 areas in the UK).
        from src.modules.network.map_areas import area_index
        call_kwargs['map_areas'] = area_index(repository)
    return call_kwargs


def _history_result(repository: Repository, saved_scoring: dict[str, Any], configuration: dict[str, Any], dataset_ids: list[int],
                    context_filters: dict[str, list[str]], engine: Any, update_progress) -> dict[str, Any] | None:
    """The scoring (and area summary) of the saved_scoring from the Scoring History when it holds every selected CDR at its
    current revision with every KPI of the methodology, and the split and filters are its dimensions; else None."""
    from src.modules.scoring import scoring as scoring_engine
    from src.modules.scoring.scoring_history import HistoryUnavailable, calculate_scoring_from_history, history_gap

    if engine is not scoring_engine:
        return None
    update_progress(4, f'Checking the Scoring History of the {len(dataset_ids)} CDRs')
    # Why the rows of the CDRs are read instead, told while they are read.
    saved_scoring['history_gap'] = history_gap(repository, dataset_ids, saved_scoring['levels'], configuration,
                                              context_filters)
    if saved_scoring['history_gap']:
        return None
    update_progress(20, 'Calculating from the Scoring History')
    catalogues = repository.cdr_catalogues_by_dataset(dataset_ids)
    options = {
        'baseline_operator': saved_scoring['baseline_operator'], 'configuration': configuration,
        'baseline_aliases': saved_scoring.get('baseline_aliases', []), 'operator_mappings': saved_scoring.get('operator_mappings', {}),
        'context_filters': context_filters,
        'vendor_operators': scoring_vendor_operators(catalogues, repository.list_operator_mapping_groups()),
        **({'nr_mode_campaigns': True} if _compares_nr_modes(saved_scoring) else {}),
    }
    try:
        result = calculate_scoring_from_history(repository, dataset_ids, saved_scoring['levels'], **options)
        job_filtered = has_area_filters(context_filters)
        if saved_scoring.get('area_summary'):
            # The summary is scored on the whole country, whatever the job's area filters.
            summary_options = {**options, 'context_filters': whole_country_filters(context_filters)}

            def calculate(levels: list[str], *, time_split: str | None = None, cities=None) -> dict[str, Any]:
                return calculate_scoring_from_history(repository, dataset_ids, levels, time_split=time_split,
                                                      cities=cities, **summary_options)
            summary = calculate_area_summary_from_history(calculate, saved_scoring['levels'], saved_scoring['area_summary'],
                                                          update_progress, job_filtered=job_filtered)
            result['warnings'] = [*(result.get('warnings') or []), *summary.pop('warnings')]
            result['area_summary'] = summary
        if saved_scoring.get('geographical', True):
            # Its Breakdown and Separate cities on the whole country: those equal to the job's own calculation or to one
            # of the summary are read from them.
            country_options = {**options, 'context_filters': whole_country_filters(context_filters)}
            geographical = calculate_geographical_from_history(
                lambda levels, *, cities=None: calculate_scoring_from_history(repository, dataset_ids, levels, cities=cities,
                                                                              **country_options),
                saved_scoring['levels'], update_progress, result.get('area_summary'), _geographical_areas(saved_scoring),
                reuse_job=not job_filtered)
            if geographical:
                result['geographical'] = geographical
    except HistoryUnavailable:
        return None
    result['points_loss'] = {'version': 2, 'pending': True}
    return result


# The Points Lost Maps waiting or being drawn, per workspace database and Saved Scoring, for the background tasks card.
_points_loss_jobs: dict[tuple[str, int], dict[str, Any]] = {}
_points_loss_guard = threading.Lock()


def _points_loss_key(database_path: Any, filter_id: int) -> tuple[str, int]:
    return str(Path(database_path).resolve()), int(filter_id)


class _MapGivesWay(Exception):
    """A Points Lost Map gives way to work of its workspace waiting before it (see queue_points_loss)."""


class _MapStopped(Exception):
    """A user stopped a Points Lost Map (see request_points_loss_stop)."""


POINTS_LOSS_STOPPED = 'Stopped by a user before it was drawn'
# The message of a Saved Scoring whose Points Lost Map a user stopped: it is drawn again once the application is idle.
POINTS_LOSS_STOPPED_MESSAGE = 'Scoring tables and GAP analysis are ready; the Points Lost Map was stopped'


def request_points_loss_stop(database_path: Any, filter_id: int) -> bool:
    """Stop the Points Lost Map of a Saved Scoring: one waiting does not start, one being drawn stops at once (its process
    is ended); its result keeps its scores, without the map. Returns whether it was waiting or drawn."""
    with _points_loss_guard:
        job = _points_loss_jobs.get(_points_loss_key(database_path, filter_id))
        if job is None:
            return False
        job.update(stop=True, detail='Stopping')
        return True


def _points_loss_stopped(repository: Repository, filter_id: int) -> None:
    """The result of a Saved Scoring whose Points Lost Map a user stopped: its scores, and the map stopped."""
    with repository.connection() as connection:
        row = connection.execute(f'SELECT status, result_json FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
    if row is None or row['status'] != 'completed' or not row['result_json']:
        return
    result = json.loads(row['result_json'])
    if not (isinstance(result.get('points_loss'), dict) and result['points_loss'].get('pending')):
        return
    result['points_loss'] = {'version': 2, 'error': POINTS_LOSS_STOPPED}
    _update_saved_scoring(repository, filter_id, result_json=json.dumps(result, ensure_ascii=False, separators=(',', ':'),
                                                                   allow_nan=False),
                        message=POINTS_LOSS_STOPPED_MESSAGE)


def stopped_points_loss_ids(repository: Repository) -> list[int]:
    """The Saved Scorings whose Points Lost Map a user stopped, the oldest first."""
    with repository.connection() as connection:
        return [int(row['id']) for row in connection.execute(
            f"SELECT id FROM {SAVED_SCORINGS_TABLE} WHERE status = 'completed' AND message = ? ORDER BY updated_at, id",
            (POINTS_LOSS_STOPPED_MESSAGE,)).fetchall()]


def resume_stopped_points_loss(repository: Repository, filter_id: int) -> bool:
    """Make the Points Lost Map a user stopped pending again, to be drawn (see queue_points_loss); whether it was."""
    with repository.connection() as connection:
        row = connection.execute(f'SELECT status, message, result_json FROM {SAVED_SCORINGS_TABLE} WHERE id = ?',
                                 (int(filter_id),)).fetchone()
    if row is None or row['status'] != 'completed' or row['message'] != POINTS_LOSS_STOPPED_MESSAGE or not row['result_json']:
        return False
    result = json.loads(row['result_json'])
    if not (isinstance(result.get('points_loss'), dict) and result['points_loss'].get('error') == POINTS_LOSS_STOPPED):
        return False
    result['points_loss'] = {'version': 2, 'pending': True}
    _update_saved_scoring(repository, filter_id, result_json=json.dumps(result, ensure_ascii=False, separators=(',', ':'),
                                                                   allow_nan=False),
                        message='Scoring tables and GAP analysis are ready; preparing the Points Lost Map')
    return True


def queue_points_loss(repository: Repository, filter_id: int, submit: Callable[[Callable[[], None]], Any],
                      work_waiting: Callable[[], bool] | None = None) -> None:
    """Queue the Points Lost Map of a result calculated from the Scoring History as a job of its own.

    With ``work_waiting`` (whether work of the workspace waits before the job, such as the calculation of another Saved
    Filter), the map gives way to it after the CDR or group of tests it is on and is queued again: it goes on with the
    maps of the methodologies it finished (see _points_loss_of)."""
    with _points_loss_guard:
        _points_loss_jobs[_points_loss_key(repository.db_path, filter_id)] = {
            'status': 'queued', 'queued_at': time.time(), 'started_at': None}
    submit(partial(complete_saved_scoring_points_loss, repository, int(filter_id), submit, work_waiting))


def complete_saved_scoring_points_loss(repository: Repository, filter_id: int,
                                      requeue: Callable[[Callable[[], None]], Any] | None = None,
                                      work_waiting: Callable[[], bool] | None = None) -> None:
    """Read the rows of the tests of a Saved Scoring and add its Points Lost Map to its saved result."""
    key = _points_loss_key(repository.db_path, filter_id)
    with _points_loss_guard:
        if key in _points_loss_jobs:
            _points_loss_jobs[key].update(status='processing', started_at=time.time(), progress=0,
                                          detail='Stopping' if _points_loss_jobs[key].get('stop') else 'Reading the rows of the tests')

    def report(progress: float, detail: str) -> None:
        with _points_loss_guard:
            stopped = bool(_points_loss_jobs.get(key, {}).get('stop'))
        if stopped:
            raise _MapStopped()
        if requeue is not None and work_waiting is not None and progress < 97 and work_waiting():
            raise _MapGivesWay()
        with _points_loss_guard:
            if key in _points_loss_jobs:
                _points_loss_jobs[key].update(progress=max(0.0, min(99.0, float(progress))), detail=detail)
    gave_way = False
    try:
        report(0, 'Reading the rows of the tests')
        saved_scoring = get_saved_scoring(repository, filter_id, include_internal_snapshot=True)
        if saved_scoring is None or not saved_scoring.get('configuration'):
            return
        configuration = validate_scoring_configuration(saved_scoring['configuration'])
        dataset_ids = [int(value) for value in saved_scoring['dataset_ids']]
        context_filters = saved_scoring.get('resolved_context_filters', saved_scoring.get('context_filters', {}))
        try:
            sources, _campaigns, _fingerprint = _source_snapshot(repository, dataset_ids,
                                                                 expected_nr_mode=saved_scoring['nr_mode'])
        except ValueError:
            sources = []
        _complete_points_loss(repository, saved_scoring, filter_id, sources, dataset_ids, configuration, context_filters,
                              _scoring_engine(), saved_scoring.get('methodology_groups') or [], report)
    except _MapGivesWay:
        gave_way = True
    except _MapStopped:
        _points_loss_stopped(repository, filter_id)
        repository.try_add_log('system', 'points_loss_map_stopped', json.dumps({'saved_scoring_id': int(filter_id)}))
    finally:
        if not gave_way:
            with _points_loss_guard:
                _points_loss_jobs.pop(key, None)
    if gave_way:
        queue_points_loss(repository, filter_id, requeue, work_waiting)


def points_loss_tasks(database_path: Any) -> list[dict[str, Any]]:
    """The Points Lost Maps of a workspace waiting or being drawn, as background task cards."""
    workspace = str(Path(database_path).resolve())
    with _points_loss_guard:
        jobs = [(filter_id, dict(job)) for (path, filter_id), job in _points_loss_jobs.items() if path == workspace]
    return [{
        'id': f'saved-scoring-map:{filter_id}', 'label': f'Points Lost Map #{filter_id}',
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


def is_saved_scoring_work(task_callback: Any, task_args: tuple[Any, ...], filter_id: int) -> bool:
    """Whether a queued job calculates the given Saved Scoring or draws its Points Lost Map."""
    if task_callback is calculate_saved_scoring:
        return len(task_args) > 1 and int(task_args[1]) == int(filter_id)
    return (isinstance(task_callback, partial) and task_callback.func is complete_saved_scoring_points_loss
            and int(task_callback.args[1]) == int(filter_id))


def _points_loss_of(repository: Repository, saved_scoring: dict[str, Any], sources: list[dict[str, Any]],
                    configuration: dict[str, Any], context_filters: dict[str, list[str]], engine: Any,
                    progress: Callable[[float, str], None] = lambda *_args: None, *, cached_only: bool = False) -> Any:
    """The Points Lost Map of a Saved Scoring with one methodology, from the rows of its tests.

    ``progress`` (0-100 and the step) follows the CDRs read (the first 45%) and the groups of tests mapped. The map of
    the same CDRs, methodology and options drawn before (by this Saved Scoring or another one) is reused; with
    ``cached_only``, only that one (None without it).
    """
    from src.modules.scoring import scoring as scoring_engine
    from src.modules.scoring import scoring_cache
    key = (scoring_cache.key_of(_points_loss_inputs(repository, saved_scoring, sources, configuration, context_filters))
           if engine is scoring_engine else None)
    cached = scoring_cache.read(repository, 'points-loss', key) if key is not None else None
    if cached is not None:
        progress(100, 'Reused the map of the same CDRs and methodology')
        return cached
    if cached_only:
        return None
    postal_missing = []
    if postal_areas.wanted(saved_scoring):
        # The postal codes of the countries that lack them, before the map reads them (its key follows them).
        postal_missing = postal_areas.ensure_postal_layers(
            repository, _campaign_sources(sources, _normalize_context_filters(context_filters)),
            progress=lambda step: progress(0, step), map_key=postal_areas.chosen_map(saved_scoring))
        if engine is scoring_engine:
            key = scoring_cache.key_of(_points_loss_inputs(repository, saved_scoring, sources, configuration, context_filters))
    if engine is scoring_engine and POINTS_LOSS_APART:
        points_loss = _draw_points_loss_apart(repository, saved_scoring, sources, configuration, context_filters, progress)
    else:
        points_loss = draw_points_loss(repository, saved_scoring, sources, configuration, context_filters, engine, progress)
    if postal_missing and isinstance(points_loss, dict):
        points_loss['postal_missing'] = postal_missing
    if key is not None:
        points_loss = _serialize_result_value(points_loss)
        scoring_cache.write(repository, 'points-loss', key, points_loss)
    return points_loss


# The Points Lost Map is drawn in processes of their own (points_loss_worker), unless this is switched off (the tests
# draw it in theirs).
POINTS_LOSS_APART = os.environ.get('DTA_POINTS_LOSS_IN_PROCESS') != '1'
# The processes drawing Points Lost Maps at the same time, at most (each methodology of a Saved Scoring draws its Data
# tests in one and its other tests in another).
POINTS_LOSS_PROCESSES = max(1, int(os.environ.get('DTA_POINTS_LOSS_PROCESSES') or 4))


class _ProcessRoom:
    """Room for the processes drawing Points Lost Maps: at most POINTS_LOSS_PROCESSES at the same time, a free place
    going to the waiting process with the most tests (so the longest ones start first)."""

    def __init__(self, size: int) -> None:
        self._free = size
        self._waiting: dict[int, tuple[int, int]] = {}
        self._count = 0
        self._lock = threading.Lock()

    def ticket(self, rows: int) -> int:
        """A place in the queue for a process drawing ``rows`` tests."""
        with self._lock:
            self._count += 1
            self._waiting[self._count] = (-int(rows), self._count)
            return self._count

    def take(self, ticket: int) -> bool:
        """Whether the process of ``ticket`` can start now (it then holds a place until give_back)."""
        with self._lock:
            if not self._free or ticket not in self._waiting or min(self._waiting.values()) != self._waiting[ticket]:
                return False
            del self._waiting[ticket]
            self._free -= 1
            return True

    def give_back(self) -> None:
        with self._lock:
            self._free += 1

    def drop(self, tickets: Iterable[int]) -> None:
        """Leave the queue (a process that will not start)."""
        with self._lock:
            for ticket in tickets:
                self._waiting.pop(ticket, None)


_points_loss_room = _ProcessRoom(POINTS_LOSS_PROCESSES)
# The places in the queue of the groups of CDR types of the methodology a thread draws (see _complete_points_loss).
_points_loss_tickets = threading.local()


def _points_loss_rows(sources: list[dict[str, Any]], context_filters: dict[str, list[str]], kinds: Iterable[str]) -> int:
    """The tests of the CDRs of ``kinds`` a methodology reads (its campaigns), roughly: the rows of those CDRs."""
    read = _campaign_sources(sources, _normalize_context_filters(context_filters))
    return sum(int(source['metadata'].get('row_count') or 0) for source in read if str(source['metadata']['kind']) in kinds)


def _points_loss_kind_groups(sources: list[dict[str, Any]]) -> list[list[str]]:
    """The CDR types of a methodology drawn together in a process: Data (most of the tests) apart from the others."""
    kinds = list(dict.fromkeys(str(source['metadata']['kind']) for source in sources))
    if 'data' in kinds and len(kinds) > 1:
        return [['data'], [kind for kind in kinds if kind != 'data']]
    return [kinds] if kinds else []


def _draw_points_loss_apart(repository: Repository, saved_scoring: dict[str, Any], sources: list[dict[str, Any]],
                            configuration: dict[str, Any], context_filters: dict[str, list[str]],
                            progress: Callable[[float, str], None]) -> Any:
    """draw_points_loss in processes of their own (draw_points_loss_parts: Data in one, the other CDR types in another,
    see _points_loss_kind_groups), put together in the order of the CDR types: the same map. ``progress`` follows their
    steps (and is called every half second, so a stop or the work waiting is noticed at once: the processes are ended
    when it raises)."""
    import pickle
    import queue
    import subprocess
    import sys
    import tempfile
    from src.config import PROJECT_ROOT
    from src.modules.scoring import scoring as scoring_engine
    from src.modules.scoring.points_loss_worker import MESSAGE

    with tempfile.TemporaryDirectory(prefix='points-loss-') as folder:
        registry = repository.workspace_registry_db_path
        payload = {'db_path': str(Path(repository.db_path).resolve()),
                   'global_db_path': str(Path(repository.global_db_path).resolve()),
                   'registry_db_path': str(Path(registry).resolve()) if registry else '',
                   'saved_scoring': saved_scoring, 'sources': sources, 'configuration': configuration,
                   'context_filters': context_filters}
        planned = getattr(_points_loss_tickets, 'tickets', None) or {}
        tasks = [{'kinds': kinds, 'result': Path(folder) / f'part-{index}.pickle', 'errors': Path(folder) / f'errors-{index}.txt',
                  'process': None, 'reader': None, 'slot': False, 'done': False, 'progress': 0.0,
                  'step': 'Reading the rows of the tests', 'error': None, 'at': None,
                  'ticket': planned.get(tuple(kinds)) or _points_loss_room.ticket(_points_loss_rows(sources, context_filters, kinds))}
                 for index, kinds in enumerate(_points_loss_kind_groups(sources))]
        messages: queue.Queue = queue.Queue()

        def start(index: int) -> None:
            task = tasks[index]
            with open(task['errors'], 'wb') as errors:
                process = subprocess.Popen([sys.executable, '-m', 'src.modules.scoring.points_loss_worker'], cwd=str(PROJECT_ROOT),
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
            task['process'] = process

            def read_messages() -> None:
                for line in process.stdout:
                    text = line.decode('utf-8', 'replace')
                    if text.startswith(MESSAGE):
                        messages.put((index, json.loads(text[len(MESSAGE):])))
                # Its output closed: the process ended.
                messages.put((index, None))

            task['reader'] = threading.Thread(target=read_messages, name='points-loss-progress', daemon=True)
            task['reader'].start()
            process.stdin.write(pickle.dumps({**payload, 'kinds': task['kinds'], 'result_path': str(task['result'])},
                                             protocol=pickle.HIGHEST_PROTOCOL))
            process.stdin.close()

        def start_waiting() -> None:
            # The processes start as the other maps being drawn leave room.
            for index, task in enumerate(tasks):
                if task['process'] is None and _points_loss_room.take(task['ticket']):
                    task['slot'] = True
                    start(index)

        options = None
        try:
            start_waiting()
            # (Read while the processes draw: the map areas the parts are put together with.)
            options = _engine_kwargs(repository, saved_scoring, configuration, scoring_engine.calculate_scoring)
            while not all(task['done'] for task in tasks):
                start_waiting()
                try:
                    index, message = messages.get(timeout=.05 if any(task['process'] is None for task in tasks) else .5)
                except queue.Empty:
                    index, message = None, None
                if index is not None:
                    task = tasks[index]
                    if message is None:
                        task['process'].wait()
                        task['done'] = True
                        if task['slot']:
                            task['slot'] = False
                            _points_loss_room.give_back()
                    elif 'error' in message:
                        task['error'], task['at'] = message['error'], message.get('at')
                    else:
                        task.update(progress=message['progress'], step=message['step'])
                running = [task for task in tasks if not task['done']]
                progress(sum(task['progress'] for task in tasks) / max(1, len(tasks)),
                         min(running, key=lambda task: task['progress'])['step'] if running else 'Putting the map together')
        except BaseException:
            for task in tasks:
                if task['process'] is not None and task['process'].poll() is None:
                    task['process'].kill()
            raise
        finally:
            for task in tasks:
                if task['process'] is not None:
                    task['process'].wait()
                    task['reader'].join(timeout=5)
                if task['slot']:
                    task['slot'] = False
                    _points_loss_room.give_back()
            _points_loss_room.drop(task['ticket'] for task in tasks if task['process'] is None)
        failed = [task for task in tasks if task['process'].returncode != 0 or not task['result'].exists()]
        if failed:
            # The error of the first CDR read, as reading every CDR type at once gives it.
            task = min(failed, key=lambda task: task['at'] if task['at'] is not None else float('inf'))
            detail = task['error'] or task['errors'].read_text(encoding='utf-8', errors='replace').strip()[-500:]
            raise RuntimeError(detail or f"The Points Lost Map process ended with code {task['process'].returncode}")
        parts, first_rows = [], {}
        for task in tasks:
            with open(task['result'], 'rb') as handle:
                drawn = pickle.load(handle)
            parts.extend(drawn['parts'])
            first_rows.update(drawn['first_rows'])
    missing = _missing_kinds(context_filters, first_rows)
    if missing:
        raise RuntimeError(missing)
    parts.sort(key=lambda part: first_rows[part['kind']])
    return scoring_engine.points_loss_document(parts, options.get('map_areas'), apart=True,
                                               postal_areas=_postal_index(repository, saved_scoring))


def draw_points_loss_parts(repository: Repository, saved_scoring: dict[str, Any], sources: list[dict[str, Any]],
                           configuration: dict[str, Any], context_filters: dict[str, list[str]], kinds: list[str],
                           progress: Callable[[float, str], None] = lambda *_args: None) -> dict[str, Any]:
    """The Points Lost Map of the CDR types ``kinds`` of a Saved Scoring with one methodology, before the parts of every CDR
    type are put together (scoring.points_loss_document): the part of each type and the place in ``sources`` of the first
    CDR of each type with rows (the order of the types)."""
    from src.modules.scoring import scoring as scoring_engine
    from src.modules.scoring.scoring_points_loss import compact_contribution

    for source in sources:
        source['levels'] = list(saved_scoring['levels'])
    total = max(1, sum(str(source['metadata']['kind']) in kinds for source in sources))
    read = 0

    def cdr_read(*_args: Any) -> None:
        nonlocal read
        read += 1
        progress(read * 45 / total, f'Reading the rows of the tests: CDR {min(read + 1, total)} of {total}'
                 if read < total else 'Mapping the tests')

    progress(0, f'Reading the rows of the tests: CDR 1 of {total}')
    first_rows: dict[str, int] = {}
    frames = _load_source_frames(repository, sources, cdr_read, scoring_engine.load_input_columns, context_filters,
                                 nr_mode_campaigns=_compares_nr_modes(saved_scoring), columnar=True, kinds=set(kinds),
                                 first_rows=first_rows)
    options = _engine_kwargs(repository, saved_scoring, configuration, scoring_engine.calculate_scoring)
    parts = scoring_engine.points_loss_parts(
        frames, saved_scoring['levels'], configuration=configuration, operator_mappings=options.get('operator_mappings'),
        map_areas=options.get('map_areas'), progress_callback=lambda share, step: progress(45 + share * 55, step),
        postal_areas=_postal_index(repository, saved_scoring))
    for part in parts:
        compact_contribution(part['places'])
    return {'parts': parts, 'first_rows': first_rows}


def draw_points_loss(repository: Repository, saved_scoring: dict[str, Any], sources: list[dict[str, Any]],
                     configuration: dict[str, Any], context_filters: dict[str, list[str]], engine: Any,
                     progress: Callable[[float, str], None] = lambda *_args: None) -> Any:
    """The Points Lost Map of a Saved Scoring with one methodology, from the rows of its tests (see _points_loss_of)."""
    for source in sources:
        source['levels'] = list(saved_scoring['levels'])
    required_columns = getattr(engine, 'load_input_columns', None) or getattr(engine, 'required_input_columns')
    total = max(1, len(sources))
    read = 0

    def cdr_read(*_args: Any) -> None:
        nonlocal read
        read += 1
        progress(read * 45 / total, f'Reading the rows of the tests: CDR {min(read + 1, total)} of {total}'
                 if read < total else 'Mapping the tests')

    progress(0, f'Reading the rows of the tests: CDR 1 of {total}')
    # The map only needs the rows: read from the columnar copies of each CDR type at once.
    frames = _load_source_frames(repository, sources, cdr_read, required_columns, context_filters,
                                 nr_mode_campaigns=_compares_nr_modes(saved_scoring), columnar=True)
    calculate = engine.calculate_scoring
    options = _engine_kwargs(repository, saved_scoring, configuration, calculate)
    if hasattr(engine, 'calculate_points_loss'):
        # Only the map: the scores are already saved.
        extra = ({'progress_callback': lambda share, step: progress(45 + share * 55, step)}
                 if 'progress_callback' in inspect.signature(engine.calculate_points_loss).parameters else {})
        if 'postal_areas' in inspect.signature(engine.calculate_points_loss).parameters:
            extra['postal_areas'] = _postal_index(repository, saved_scoring)
        points_loss = engine.calculate_points_loss(
            frames, saved_scoring['levels'], configuration=configuration,
            operator_mappings=options.get('operator_mappings'), map_areas=options.get('map_areas'), **extra)
    else:
        points_loss = calculate(frames, saved_scoring['levels'], **options)['points_loss']
    return points_loss


def _postal_index(repository: Repository, saved_scoring: dict[str, Any]) -> Any:
    """The postal code areas that place the tests of a Saved Scoring that asks for Postal Codes."""
    return postal_areas.postal_index(repository, postal_areas.chosen_map(saved_scoring)) if postal_areas.wanted(saved_scoring) else None


def _points_loss_inputs(repository: Repository, saved_scoring: dict[str, Any], sources: list[dict[str, Any]],
                        configuration: dict[str, Any], context_filters: dict[str, list[str]]) -> dict[str, Any]:
    """What the Points Lost Map of one methodology depends on: the revision of the CDRs it reads (and whether their tests
    are placed in the Map Areas), the split, the methodology, the filters, the Operator Maps, the Map Areas and, for a
    Saved Scoring that asks for them, the postal code areas."""
    from src.modules.scoring import scoring as scoring_engine
    from src.modules.network.map_area_columns import areas_version, current_datasets
    read = _campaign_sources(sources, _normalize_context_filters(context_filters))
    placed = current_datasets(repository, [int(source['metadata']['dataset_id']) for source in read])
    return {
        'kind': 'points-loss', 'method_version': scoring_engine.METHOD_VERSION,
        'sources': sorted((json.dumps({**source['signature'], 'placed': int(source['metadata']['dataset_id']) in placed},
                                      sort_keys=True, default=str) for source in read)),
        'levels': list(saved_scoring['levels']), 'configuration': configuration_hash(configuration),
        'filters': _filters_key(context_filters), 'operator_mappings': saved_scoring.get('operator_mappings', {}),
        'map_areas': areas_version(repository),
        **({'nr_mode_campaigns': True} if _compares_nr_modes(saved_scoring) else {}),
        **({'postal_codes': postal_areas.postal_version(repository, postal_areas.chosen_map(saved_scoring))} if postal_areas.wanted(saved_scoring) else {}),
    }


def _complete_points_loss(repository: Repository, saved_scoring: dict[str, Any], filter_id: int, sources: list[dict[str, Any]],
                          dataset_ids: list[int], configuration: dict[str, Any],
                          context_filters: dict[str, list[str]], engine: Any,
                          groups: list[dict[str, Any]] | None = None,
                          progress: Callable[[float, str], None] = lambda *_args: None, *,
                          cached_only: bool = False) -> bool:
    """Read the rows of the tests and add the Points Lost Map to a result calculated from the Scoring History (By
    campaign, the map of the campaigns of each methodology with it, drawn side by side, ``progress`` their mean). With
    ``cached_only``, it is added only when every map was drawn before (see _points_loss_of); returns whether it was."""
    try:
        if groups and len(groups) > 1:
            from concurrent.futures import ThreadPoolExecutor
            from src.modules.scoring.scoring_methodologies import _merge_points_loss
            # The maps of the methodologies are drawn side by side (each in a process of its own, see _points_loss_of):
            # the progress is their mean, with the step of the last one that moved.
            shares = [0.0] * len(groups)
            shares_guard = threading.Lock()

            # Every group of CDR types of every methodology waits in the queue of the processes from the start, so the
            # ones with the most tests start first (see _draw_points_loss_apart).
            planned = [{tuple(kinds): _points_loss_room.ticket(_points_loss_rows(
                sources, {**context_filters, 'Campaign': list(group['campaigns'])}, kinds))
                for kinds in _points_loss_kind_groups(sources)} for group in groups]

            def draw(index: int, group: dict[str, Any]) -> Any:
                name = group.get('profile_name') or 'Methodology'

                def group_progress(value: float, step: str) -> None:
                    with shares_guard:
                        shares[index] = max(shares[index], float(value))
                        overall = sum(shares) / len(groups) * 0.97
                    progress(overall, f'Methodology {index + 1} of {len(groups)} ({name}): {step}')
                _points_loss_tickets.tickets = planned[index]
                try:
                    return _points_loss_of(repository, saved_scoring, [dict(source) for source in sources],
                                           validate_scoring_configuration(group['configuration']),
                                           {**context_filters, 'Campaign': list(group['campaigns'])}, engine,
                                           group_progress, cached_only=cached_only)
                finally:
                    _points_loss_tickets.tickets = None
                    _points_loss_room.drop(planned[index].values())
            try:
                # (A thread per methodology, waiting for its processes: every place in the queue has its thread.)
                with ThreadPoolExecutor(max_workers=len(groups), thread_name_prefix='points-loss-methodology') as pool:
                    futures = [pool.submit(draw, index, group) for index, group in enumerate(groups)]
                    maps = [future.result() for future in futures]
            finally:
                _points_loss_room.drop(ticket for tickets in planned for ticket in tickets.values())
            if any(item is None for item in maps):
                return False
            points_loss = _merge_points_loss(maps)
        else:
            points_loss = _points_loss_of(repository, saved_scoring, sources, configuration, context_filters, engine,
                                          lambda value, step: progress(value * 0.97, step), cached_only=cached_only)
            if points_loss is None and cached_only:
                return False
        progress(97, 'Adding the area boundaries')
        document = {'points_loss': points_loss}
        _attach_mapping_boundaries(repository, dataset_ids, document)
        progress(99, 'Saving the map')
    except (_MapGivesWay, _MapStopped):
        raise
    except Exception as exc:  # The scores stay; only the map is missing.
        if cached_only:
            return False
        document = {'points_loss': {'version': 2, 'error': str(exc)}}
    with repository.connection() as connection:
        row = connection.execute(f'SELECT status, result_json FROM {SAVED_SCORINGS_TABLE} WHERE id = ?', (int(filter_id),)).fetchone()
    if row is None or row['status'] != 'completed' or not row['result_json']:
        return False
    result = json.loads(row['result_json'])
    if not (isinstance(result.get('points_loss'), dict) and result['points_loss'].get('pending')):
        return True
    result['points_loss'] = _serialize_result_value(document['points_loss'])
    _update_saved_scoring(repository, filter_id, result_json=json.dumps(result, ensure_ascii=False, separators=(',', ':'),
                                                                   allow_nan=False),
                        message='Scoring tables, GAP analysis and Points Lost Map are ready')
    return True


def _save_scoring_result(repository: Repository, saved_scoring: dict[str, Any], filter_id: int, dataset_ids: list[int],
                         configuration: dict[str, Any], result: dict[str, Any], *, points_loss_pending: bool = False) -> None:
    """Store the result of a calculation once the selected CDRs are checked unchanged."""
    if not isinstance(result, dict):
        raise TypeError('The scoring engine must return a result object.')
    _attach_mapping_boundaries(repository, dataset_ids, result)
    result.setdefault('configuration', configuration)
    result.setdefault('configuration_hash', configuration_hash(configuration))
    result.setdefault('gap_direction', 'operator_minus_reference')
    result.setdefault('baseline_aliases', saved_scoring.get('baseline_aliases', []))
    result.setdefault('aggregation_levels', saved_scoring['levels'])
    result.setdefault('aggregation_contract_version', saved_scoring['aggregation_contract_version'])
    result.setdefault('campaigns', saved_scoring['campaigns'])
    _latest_sources, _latest_campaigns, final_fingerprint = _source_snapshot(
        repository, dataset_ids, expected_nr_mode=saved_scoring['nr_mode'],
    )
    if final_fingerprint != saved_scoring['source_fingerprint']:
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
    _update_saved_scoring(
        repository, filter_id, status='completed', progress=100,
        message=('Scoring tables and GAP analysis are ready; preparing the Points Lost Map' if points_loss_pending
                 else 'Scoring tables and GAP analysis are ready'),
        result_json=encoded_result, last_error='', finished_at=local_now_iso(),
    )
    # How many times its result has been calculated, beside how many times it has been used.
    with repository.connection() as connection:
        connection.execute(f'UPDATE {SAVED_SCORINGS_TABLE} SET calculation_count = calculation_count + 1 WHERE id = ?',
                           (int(filter_id),))


def _fail_calculation(repository: Repository, saved_scoring: dict[str, Any], filter_id: int, exc: Exception) -> None:
    """Keep a failed calculation with its reason, for review."""
    _update_saved_scoring(
        repository, filter_id, status='failed', progress=100,
        message='Scoring calculation failed', last_error=str(exc), finished_at=local_now_iso(),
    )
    # App Logs show why a calculation failed, with where it happened.
    if hasattr(repository, 'try_add_log'):
        import traceback
        repository.try_add_log(str(saved_scoring.get('created_by') or 'system'), 'scoring_calculation_failed', json.dumps({
            'filter_id': filter_id, 'error': f'{type(exc).__name__}: {exc}',
            'location': ''.join(traceback.format_exception(exc)[-3:]).strip()[-1500:],
        }, ensure_ascii=False))
