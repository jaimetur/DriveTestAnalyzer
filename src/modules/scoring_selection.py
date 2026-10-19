"""Workspace-wide persistence for the Scoring calculation controls."""

from __future__ import annotations

import json
from typing import Any

from src.branding import canonical_format
from src.modules.column_names import campaign_sort_key, column_identity
from src.modules.cdr_auto_selection import (
    CAMPAIGN_PRESETS, CDR_KIND_LABELS, LATEST_CAMPAIGN, NO_PREVIOUS_CAMPAIGN, campaign_groups, campaign_identity, campaign_presets,
    candidate_cdrs, cdr_campaigns, campaign_values, complete_campaign_cdrs, preset_campaign_groups,
)
from src.modules.cdr_facets import cascading_options
from src.modules.cdr_stage import combined_dataset_ids
from src.modules.nr_mode import NSA_VS_SA, normalize_nr_mode, normalize_scoring_nr_mode, nr_modes_of
from src.modules.repository import Repository
from src.modules.scoring_vendors import scoring_vendor_name, scoring_vendor_operators
from src.modules.scoring_config import load_aggregation_hierarchy


SCORING_SELECTION_STATE_KEY = 'scoring_calculation_selection_v1'
SCORING_SELECTION_FORMAT = 'drivetest-analyzer-scoring-selection'
SCORING_SELECTION_VERSION = 1
SCORING_CONTEXT_FILTER_FIELDS = ('Region', 'Cluster', 'City', 'Operator', 'Operator_Vendor', 'Vendor', 'Campaign')
# Filters that are not aggregation levels: saved selections only list them when used.
SCORING_OPTIONAL_CONTEXT_FILTERS = frozenset({'Cluster', 'Operator_Vendor'})
MAX_TRACKED_CLIENTS = 64


def _profile_context(repository: Repository) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        profile_state = repository.get_scoring_profiles()
    except ValueError:
        return {}, ''
    profiles = {
        str(profile['id']): profile
        for profile in profile_state['profiles']
        if isinstance(profile, dict) and str(profile.get('id') or '').strip()
    }
    active_id = str(profile_state.get('active_profile_id') or '')
    return profiles, active_id


def _operator_options(repository: Repository) -> list[str]:
    options: list[str] = []
    seen: set[str] = set()
    for group in repository.list_operator_mapping_groups():
        canonical = str(group.get('canonical') or '').strip()
        identity = canonical.casefold()
        if canonical and identity not in seen:
            options.append(canonical)
            seen.add(identity)
    return options or ['EE']


def _available_cdr_rows(repository: Repository) -> list[dict[str, Any]]:
    # The CDRs of the combined tables: Final CDRs, and Weekly and Daily CDRs until a Final CDR replaces them.
    included = combined_dataset_ids(repository)
    available: list[dict[str, Any]] = []
    for raw_row in repository.list_datasets():
        row = dict(raw_row)
        kind = str(row.get('dataset_kind') or '').strip().casefold()
        if str(row.get('status') or '').strip().casefold() != 'ready' or kind not in {'data', 'voice', 'speech'}:
            continue
        if int(row['id']) not in included:
            continue
        mode = normalize_nr_mode(row.get('nr_mode'))
        if mode not in {'NSA', 'SA'}:
            continue
        available.append({**row, 'id': int(row['id']), 'dataset_kind': kind, 'nr_mode': mode})
    return available


def _available_cdr_ids(
    repository: Repository,
    rows: list[dict[str, Any]],
    selected_ids: list[int] | None = None,
) -> set[int]:
    selected = set(selected_ids) if selected_ids is not None else None
    return {
        int(row['id']) for row in rows
        if (selected is None or int(row['id']) in selected)
        and repository.dataset_rows_table_exists(int(row['id']))
    }


def _default_nr_mode(rows: list[dict[str, Any]]) -> str:
    modes = {str(row['nr_mode']) for row in rows}
    return 'NSA' if 'NSA' in modes else ('SA' if 'SA' in modes else 'NSA')


def _scoring_nr_modes(rows: list[dict[str, Any]]) -> list[str]:
    """The NR Modes a calculation can choose: those of the CDRs, and NSA vs SA when there are both."""
    modes = sorted({str(row['nr_mode']) for row in rows})
    return [*modes, NSA_VS_SA] if len(modes) > 1 else modes


def _default_selection(repository: Repository) -> dict[str, Any]:
    rows = _available_cdr_rows(repository)
    nr_mode = _default_nr_mode(rows)
    defaults = _fallback_selection(repository, rows=rows, nr_mode=nr_mode)
    # Latest campaign: the newest campaign with Data, Voice and Speech CDRs, also when newer ones arrive.
    defaults['context_filters']['Campaign'] = [LATEST_CAMPAIGN]
    defaults['dataset_ids'] = auto_scoring_cdr_ids(repository, nr_mode, defaults['context_filters']['Campaign'])
    return defaults


def _complete_campaign_groups(repository: Repository, nr_mode: str) -> list[list[str]]:
    """The campaigns of the NR Mode with Data, Voice and Speech CDRs, newest first (each with its spellings).

    With NSA vs SA a group is a quarter with its NSA and SA campaigns, so Latest campaign compares the NSA and SA
    campaigns of the newest quarter."""
    _ids, incomplete = complete_campaign_cdrs(repository, nr_mode, [])
    left_out = {campaign_identity(value) for value in incomplete}
    groups = [values for values in campaign_groups(campaign_values(repository, nr_mode)) if campaign_identity(values[0]) not in left_out]
    if normalize_scoring_nr_mode(nr_mode) != NSA_VS_SA:
        return groups
    quarters: dict[str, list[str]] = {}
    for values in groups:
        year, quarter, *_rest = campaign_sort_key(values[0])
        quarters.setdefault(f'{year}-Q{quarter}' if year > 0 and quarter > 0 else campaign_identity(values[0]), []).extend(values)
    return list(quarters.values())


def _flatten_groups(groups: list[list[str]]) -> list[str]:
    return sorted((value for values in groups for value in values), key=lambda value: (value.casefold(), value))


def _preset_scoring_campaigns(groups: list[list[str]], presets: list[str]) -> list[str]:
    """The complete campaigns (groups newest first) that automatic choices stand for, or what stands for none."""
    return _flatten_groups(preset_campaign_groups(groups, presets)) or ([NO_PREVIOUS_CAMPAIGN] if groups else [])


def expand_scoring_campaigns(repository: Repository, nr_mode: str, values: object) -> list[str]:
    """A Campaign filter with its automatic choice (Latest campaign, Previous campaign…) as the complete campaigns it
    stands for now."""
    campaigns = [str(value).strip() for value in (values if isinstance(values, (list, tuple, set)) else [values] if values else [])
                 if str(value or '').strip()]
    presets = campaign_presets(campaigns)
    return _preset_scoring_campaigns(_complete_campaign_groups(repository, nr_mode), presets[:1]) if presets else campaigns


def expand_scoring_context_filters(repository: Repository, nr_mode: str, filters: object) -> dict[str, Any]:
    """Context filters whose Campaign holds a Latest choice, with the campaigns it stands for now."""
    expanded = dict(filters) if isinstance(filters, dict) else {}
    for key in list(expanded):
        if column_identity(key) == column_identity('Campaign') and campaign_presets(
                expanded[key] if isinstance(expanded[key], (list, tuple, set)) else [expanded[key]]):
            expanded[key] = expand_scoring_campaigns(repository, nr_mode, expanded[key])
    return expanded


def auto_scoring_cdr_ids(repository: Repository, nr_mode: str, campaigns: list[str]) -> list[int]:
    """The CDRs a calculation uses: those of the combined tables of its NR Mode and campaigns, each campaign complete."""
    dataset_ids, _incomplete = complete_campaign_cdrs(repository, nr_mode, expand_scoring_campaigns(repository, nr_mode, campaigns))
    return [dataset_id for dataset_id in dataset_ids if repository.dataset_rows_table_exists(dataset_id)]


def scoring_auto_cdrs(repository: Repository, nr_mode: object, context_filters: dict[str, Any] | None,
                      fields: list[str] | None = None, *, default_campaign: bool = False) -> dict[str, Any]:
    """The CDRs chosen for an NR Mode and Campaign filter, and the cascading values of every context filter.

    The filters list the values of every CDR of the NR Mode that the combined tables include, each one
    only those the other filters leave.
    """
    rows = _available_cdr_rows(repository)
    modes = _scoring_nr_modes(rows)
    mode = normalize_scoring_nr_mode(nr_mode)
    if mode is None or (mode == NSA_VS_SA and mode not in modes):
        mode = _default_nr_mode(rows)
    filters = dict(context_filters) if isinstance(context_filters, dict) else {}
    if default_campaign:
        # Another NR Mode starts on Latest campaign.
        filters['Campaign'] = [LATEST_CAMPAIGN]
    # The automatic choices (Latest campaign, Previous campaign…) stand for the complete campaigns now.
    complete_groups = _complete_campaign_groups(repository, mode)
    chosen = [str(value).strip() for value in (filters.get('Campaign') or []) if str(value or '').strip()]
    presets = campaign_presets(chosen)
    filters['Campaign'] = _preset_scoring_campaigns(complete_groups, presets[:1]) if presets else chosen
    campaigns = filters['Campaign']
    dataset_ids, incomplete = complete_campaign_cdrs(repository, mode, campaigns)
    dataset_ids = [dataset_id for dataset_id in dataset_ids if repository.dataset_rows_table_exists(dataset_id)]
    candidates = candidate_cdrs(repository, mode)
    by_id = {row['id']: row for row in candidates}
    campaigns_by_id = cdr_campaigns(repository, dataset_ids)
    fields = fields or ['Campaign', 'Operator', 'Operator_Vendor', 'Vendor_Operator', 'Vendor', 'Region', 'Cluster', 'City']
    return {
        'nr_mode': mode,
        'nr_modes': modes,
        'dataset_ids': dataset_ids,
        'cdrs': [{
            'id': dataset_id, 'name': by_id[dataset_id]['file_name'], 'kind': by_id[dataset_id]['kind'],
            'kind_label': CDR_KIND_LABELS.get(by_id[dataset_id]['kind'], by_id[dataset_id]['kind']),
            'stage': by_id[dataset_id]['stage'], 'campaigns': campaigns_by_id.get(dataset_id, []),
        } for dataset_id in dataset_ids if dataset_id in by_id],
        'incomplete_campaigns': incomplete,
        # The Campaign choice as made (Latest campaign…), for the Campaign filter.
        'campaign_selection': presets[:1] if presets else campaigns,
        # The campaigns each Latest choice stands for now (a calculation uses them).
        'campaign_presets': {preset: _preset_scoring_campaigns(complete_groups, [preset]) for preset in CAMPAIGN_PRESETS},
        'options': cascading_options(repository, [row['id'] for row in candidates], filters, fields),
    }


def _fallback_selection(
    repository: Repository,
    *,
    rows: list[dict[str, Any]] | None = None,
    nr_mode: str | None = None,
) -> dict[str, Any]:
    rows = rows if rows is not None else _available_cdr_rows(repository)
    selected_mode = nr_mode or _default_nr_mode(rows)
    profiles, active_profile_id = _profile_context(repository)
    operator_options = _operator_options(repository)
    baseline = next((value for value in operator_options if value.casefold() == 'ee'), operator_options[0])
    return {
        'dataset_ids': [],
        'auto_cdrs': True,
        # Split by Operator and Campaign, in the order of the aggregation hierarchy.
        'aggregation_levels': [level for level in load_aggregation_hierarchy(repository)
                               if column_identity(level) in {column_identity('Operator'), column_identity('Campaign')}]
                              or ['Operator'],
        'nr_mode': selected_mode,
        'baseline_operator': baseline,
        # Each campaign with the methodology that applies to it (the default one when none does).
        'scoring_profile_id': 'by-campaign' if profiles else '',
        'context_filters': {field: [] for field in SCORING_CONTEXT_FILTER_FIELDS if field not in SCORING_OPTIONAL_CONTEXT_FILTERS},
        'area_summary': _normalize_area_summary(None),
    }


def _normalize_area_summary(raw: object) -> dict[str, Any]:
    """The Geographical Areas & Scoring Trends of the calculation, always included: the Breakdown and Separate cities of
    its Geographical Areas and trends, the time split and the campaigns of its trends."""
    from src.modules.scoring_reports import DEFAULT_AREA_SUMMARY, _normalize_area_summary as normalize
    summary = normalize(raw if isinstance(raw, dict) else DEFAULT_AREA_SUMMARY)
    # (Main Cities stay as such: the Main Cities of the workspace when the scoring is calculated.)
    return summary


def _normalize_context_filters(
    raw_filters: object,
    hierarchy: list[str],
    warnings: list[str],
) -> dict[str, list[str]]:
    normalized = {field: [] for field in SCORING_CONTEXT_FILTER_FIELDS if field not in SCORING_OPTIONAL_CONTEXT_FILTERS}
    if raw_filters is None:
        return normalized
    if not isinstance(raw_filters, dict):
        warnings.append('Saved context filters were invalid and have been cleared.')
        return normalized
    supported = {column_identity(field): field for field in SCORING_CONTEXT_FILTER_FIELDS}
    # Cluster and Operator_Vendor filter the samples without being aggregation levels.
    allowed_fields = {column_identity(field) for field in hierarchy} | {'cluster', 'operatorvendor'}
    values_by_field: dict[str, dict[str, str]] = {field: {} for field in SCORING_CONTEXT_FILTER_FIELDS}
    stale_fields = False
    for raw_field, raw_values in raw_filters.items():
        canonical = supported.get(column_identity(raw_field))
        if canonical is None or column_identity(canonical) not in allowed_fields:
            stale_fields = True
            continue
        if raw_values is None:
            continue
        values = [raw_values] if isinstance(raw_values, str) else raw_values
        if not isinstance(values, (list, tuple, set)):
            stale_fields = True
            continue
        for raw_value in values:
            value = str(raw_value).strip() if raw_value is not None else ''
            if value:
                values_by_field[canonical].setdefault(value.casefold(), value)
    for field, values in values_by_field.items():
        if values or field not in SCORING_OPTIONAL_CONTEXT_FILTERS:
            normalized[field] = sorted(values.values(), key=lambda value: (value.casefold(), value))
    if stale_fields:
        warnings.append('Context filters from the previous selection were no longer supported and have been cleared.')
    return normalized


def _normalize_selection(
    repository: Repository,
    raw_selection: object,
    defaults: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if not isinstance(raw_selection, dict):
        return defaults, ['Saved scoring selection was invalid and has been reset.']

    profiles, active_profile_id = _profile_context(repository)
    selected_profile_id = str(raw_selection.get('scoring_profile_id') or '').strip()
    if profiles and selected_profile_id == 'by-campaign':
        pass  # Each campaign with the methodology that applies to it.
    elif profiles and selected_profile_id not in profiles:
        if selected_profile_id:
            warnings.append('The saved scoring methodology is no longer available; the active methodology was selected.')
        selected_profile_id = active_profile_id
    elif not profiles:
        if selected_profile_id:
            warnings.append('The saved scoring methodology is unavailable; import a scoring configuration before calculating.')
        selected_profile_id = ''
    elif not selected_profile_id:
        selected_profile_id = 'by-campaign'
    hierarchy = load_aggregation_hierarchy(repository)
    hierarchy_by_identity = {column_identity(level): level for level in hierarchy}

    raw_mode = normalize_scoring_nr_mode(raw_selection.get('nr_mode'))
    rows = _available_cdr_rows(repository)
    if raw_mode is None:
        raw_mode = defaults['nr_mode']
        warnings.append('The saved NR Mode was invalid; the default mode was selected.')
    if ((raw_mode == NSA_VS_SA and raw_mode not in _scoring_nr_modes(rows))
            or not any(row['nr_mode'] in nr_modes_of(raw_mode) for row in rows)):
        available_mode = _default_nr_mode(rows)
        if available_mode != raw_mode:
            raw_mode = available_mode
            warnings.append('The saved NR Mode is no longer available; the available mode was selected.')

    raw_ids = raw_selection.get('dataset_ids', [])
    if not isinstance(raw_ids, (list, tuple, set)):
        raw_ids = []
        warnings.append('The saved CDR selection was invalid and has been cleared.')
    parsed_ids: list[int] = []
    invalid_ids = False
    for value in raw_ids:
        if isinstance(value, bool):
            invalid_ids = True
            continue
        try:
            dataset_id = int(value)
        except (TypeError, ValueError, OverflowError):
            invalid_ids = True
            continue
        if dataset_id <= 0:
            invalid_ids = True
            continue
        if dataset_id not in parsed_ids:
            parsed_ids.append(dataset_id)
    rows_by_id = {int(row['id']): row for row in rows}
    context_filters = _normalize_context_filters(raw_selection.get('context_filters'), hierarchy, warnings)
    # The CDRs follow the NR Mode and the Campaign filter (auto_cdrs); a Saved Filter opened in the
    # panel keeps its own CDRs until the NR Mode or a filter changes.
    auto_cdrs = raw_selection.get('auto_cdrs')
    if auto_cdrs is None:
        auto_cdrs = True
        if parsed_ids and not context_filters.get('Campaign'):
            # A selection saved when CDRs were chosen by hand: its campaigns choose the same CDRs.
            kept = [dataset_id for dataset_id in parsed_ids
                    if dataset_id in rows_by_id and rows_by_id[dataset_id]['nr_mode'] in nr_modes_of(raw_mode)]
            campaigns = sorted({value for values in cdr_campaigns(repository, kept).values() for value in values},
                               key=lambda value: (value.casefold(), value))
            if campaigns:
                context_filters['Campaign'] = campaigns
    if auto_cdrs:
        dataset_ids = auto_scoring_cdr_ids(repository, raw_mode, context_filters.get('Campaign') or [])
    else:
        table_ids = _available_cdr_ids(repository, rows, parsed_ids) if parsed_ids else set()
        dataset_ids = [
            dataset_id for dataset_id in parsed_ids
            if dataset_id in rows_by_id
            and rows_by_id[dataset_id]['nr_mode'] in nr_modes_of(raw_mode)
            and dataset_id in table_ids
        ]
        if invalid_ids or len(dataset_ids) != len(parsed_ids):
            warnings.append('One or more saved CDR datasets are no longer available and were removed.')

    raw_levels = raw_selection.get('aggregation_levels', defaults['aggregation_levels'])
    if not isinstance(raw_levels, (list, tuple, set)):
        raw_levels = []
        warnings.append('Saved Split by levels were invalid and have been reset.')
    selected_level_ids = {column_identity(value) for value in raw_levels if str(value).strip()}
    aggregation_levels = [
        level for level in hierarchy
        if column_identity(level) == column_identity('Operator') or column_identity(level) in selected_level_ids
    ]
    if any(identity not in hierarchy_by_identity for identity in selected_level_ids):
        warnings.append('Split by levels from the previous methodology were removed.')
    if not aggregation_levels:
        aggregation_levels = ['Operator']
    if raw_mode == NSA_VS_SA:
        # NSA vs SA compares the campaigns of each NR Mode: it is always split by Campaign.
        aggregation_levels = [level for level in hierarchy if column_identity(level) in {
            column_identity(value) for value in [*aggregation_levels, 'Campaign']}] or aggregation_levels

    operator_options = _operator_options(repository)
    raw_baseline = str(raw_selection.get('baseline_operator') or '').strip()
    baseline = next((value for value in operator_options if value.casefold() == raw_baseline.casefold()), None)
    if baseline is None:
        baseline = next((value for value in operator_options if value.casefold() == 'ee'), operator_options[0])
        if raw_baseline and raw_baseline.casefold() != baseline.casefold():
            warnings.append('The saved GAP reference operator is no longer available; a default operator was selected.')

    vendor_operators = scoring_vendor_operators(
        repository.cdr_catalogues_by_dataset(dataset_ids), repository.list_operator_mapping_groups(),
    )
    context_filters['Vendor'] = sorted({
        scoring_vendor_name(value, vendor_operators) for value in context_filters['Vendor']
    }, key=str.casefold)
    return {
        'dataset_ids': dataset_ids,
        'auto_cdrs': bool(auto_cdrs),
        'aggregation_levels': aggregation_levels,
        'nr_mode': raw_mode,
        'baseline_operator': baseline,
        'scoring_profile_id': selected_profile_id,
        'context_filters': context_filters,
        'area_summary': _normalize_area_summary(raw_selection.get('area_summary')),
    }, list(dict.fromkeys(warnings))


def load_scoring_selection(repository: Repository) -> tuple[dict[str, Any], list[str]]:
    """Return the normalized workspace selection without reading CDR rows."""
    raw = repository.get_workspace_state(SCORING_SELECTION_STATE_KEY)
    if raw is None:
        return _default_selection(repository), []
    try:
        document = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return _default_selection(repository), ['Saved scoring selection could not be read and has been reset.']
    if not isinstance(document, dict):
        return _default_selection(repository), ['Saved scoring selection could not be read and has been reset.']
    if canonical_format(document.get('format')) == SCORING_SELECTION_FORMAT and document.get('version') == SCORING_SELECTION_VERSION:
        selection = document.get('selection')
    else:
        # Accept a flat selection document to ease recovery from early versions.
        selection = document
    defaults = _fallback_selection(repository)
    return normalize_scoring_selection(repository, selection, defaults=defaults)


def normalize_scoring_selection(
    repository: Repository,
    selection: object,
    *,
    defaults: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Validate a client selection against current workspace metadata."""
    return _normalize_selection(repository, selection, defaults or _fallback_selection(repository))


def save_scoring_selection(
    repository: Repository,
    selection: dict[str, Any],
    *,
    client_id: str | None = None,
    client_revision: int | None = None,
) -> bool:
    """Atomically store a selection and reject delayed writes from the same tab."""
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute(
            'SELECT value FROM workspace_state WHERE key = ?', (SCORING_SELECTION_STATE_KEY,),
        ).fetchone()
        try:
            existing = json.loads(str(row['value'])) if row else {}
        except (TypeError, json.JSONDecodeError):
            existing = {}
        revisions: dict[str, int] = {}
        if isinstance(existing, dict) and canonical_format(existing.get('format')) == SCORING_SELECTION_FORMAT:
            raw_revisions = existing.get('client_revisions')
            if isinstance(raw_revisions, dict):
                for existing_client, existing_revision in raw_revisions.items():
                    try:
                        normalized_revision = int(existing_revision)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if str(existing_client).strip() and normalized_revision > 0:
                        revisions[str(existing_client)] = normalized_revision

        if client_id and client_revision is not None:
            if client_revision <= revisions.get(client_id, 0):
                return False
            revisions[client_id] = client_revision
            while len(revisions) > MAX_TRACKED_CLIENTS:
                revisions.pop(next(iter(revisions)))

        document = serialize_scoring_selection(selection, revisions)
        connection.execute(
            'INSERT INTO workspace_state (key, value) VALUES (?, ?) '
            'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (SCORING_SELECTION_STATE_KEY, document),
        )
    return True


def serialize_scoring_selection(
    selection: dict[str, Any],
    client_revisions: dict[str, int] | None = None,
) -> str:
    """Serialize the stable versioned workspace selection document."""
    return json.dumps({
        'format': SCORING_SELECTION_FORMAT,
        'version': SCORING_SELECTION_VERSION,
        'selection': selection,
        'client_revisions': client_revisions or {},
    }, ensure_ascii=False, separators=(',', ':'))
