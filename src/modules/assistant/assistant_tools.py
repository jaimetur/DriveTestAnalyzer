"""The tools of the AI Assistant: what it can read from the workspace to answer a question.

Every tool only reads, through the functions the modules of the tool already use (the Scoring of a selection is
calculated as a Saved Filter calculates it), and returns aggregated figures: never rows of the CDRs, coordinates or
call identifiers. The names in their results are the real ones; ``assistant.py`` masks them (see assistant_privacy)
before they are sent to the engine, and puts the real names back in the arguments the engine sends.
"""
from __future__ import annotations

import ast
import json
import math
import operator as operator_module
import re
import sqlite3
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HELP_DIR = Path(__file__).resolve().parents[3] / 'help'
SPLIT_LEVELS = ('Operator', 'Campaign', 'Vendor', 'Region', 'Cluster', 'City', 'Dataset Type')
FILTER_FIELDS = ('Operator', 'Vendor', 'Region', 'Cluster', 'City')
SCORING_DETAILS = ('environments', 'categories', 'kpis', 'gap')
CAMPAIGN_CHOICES = {
    'latest': '@latest-campaign', 'previous': '@previous-campaign', 'latest 2': '@latest-2-campaigns',
    'latest 3': '@latest-3-campaigns', 'latest 4': '@latest-4-campaigns', 'all': '@all-campaigns',
}
NQ_FIELDS = {
    # field -> column of nq_call_latest (l), nq_call_tracking (t) or nq_dta_rca_results (r)
    'campaign': 'l.campaign', 'operator': 'l.operator', 'vendor': 'l.vendor', 'region': 'l.region', 'cluster': 'l.cluster',
    'city': 'l.city', 'service': 'l.service', 'nr_mode': 'l.nr_mode', 'technology': 'l.technology',
    'environment': 'l.environment', 'failure_category': 'l.failure_category',
    'failure_classification': 'l.failure_classification', 'failure_phase': 'l.failure_phase',
    'failure_technology': 'l.failure_technology', 'host_network': 'l.host_network',
    'status': 't.status', 'root_domain': 't.root_domain', 'root_category': 't.root_category', 'root_cause': 't.root_cause',
    'dta_rca_domain': 'r.domain', 'dta_rca_category': 'r.category', 'dta_rca_cause': 'r.cause',
}
MAX_LIST_VALUES = 400
MAX_KPI_ROWS = 240
KPIS_PER_GROUP = 8
MAX_GROUPS = 60

TOOLS: list[dict[str, str]] = [
    {'name': 'workspace_overview', 'arguments': '{}',
     'description': 'The campaigns of each NR Mode (newest first, with their quarter, CDR types and methodology), the '
                    'operators with their role (focus, exclude), the vendors, regions and clusters, the number of '
                    'cities, the scoring methodologies with their environments and points, and the Saved Filters. '
                    'It is already given with the first question; call it again only if it may have changed.'},
    {'name': 'list_values', 'arguments': '{"field": "City|Region|Cluster|Vendor|Operator|Campaign", "nr_mode": "NSA|SA (optional)"}',
     'description': 'Every value (code) of a field in the CDRs of the workspace, with the number of CDRs that hold it.'},
    {'name': 'scoring', 'arguments': '{"campaigns": ["CP1"] or ["latest"|"previous"|"latest 2"|"latest 3"|"latest 4"|"all"], '
                                     '"nr_mode": "NSA|SA|NSA vs SA", "split_by": ["Operator", "Campaign", "Vendor", "Region", '
                                     '"Cluster", "City", "Dataset Type"], "filters": {"Operator": ["OP1"], "Vendor": [], '
                                     '"Region": [], "Cluster": [], "City": []}, "only": {"Operator": ["OP1"]}, "detail": '
                                     '["environments", "categories", "kpis", "gap"], "reference_operator": "OP3 (optional, the '
                                     'GAP reference)"}',
     'description': 'The Scoring & GAP Analysis points of the operators, calculated exactly as the module calculates a '
                    'Saved Filter: each campaign with the methodology that applies to it, the operators the Operator '
                    'Maps exclude left out. Operator is always part of the split. Returns per group the total points, '
                    'the maximum and available points, whether the coverage is complete and the samples; with detail '
                    'the points per environment and per category, the KPIs that lose most points (value, points, points '
                    'lost) and the GAP to the reference operator. filters change what is calculated: an Operator filter '
                    'changes the points, because some KPIs are scored against the best operator of the calculation, so '
                    'to answer about some operators use "only", which lists only their groups and keeps the points the '
                    'module shows. Vendor is the RAN vendor of the cells that served the test; '
                    '"VNx (Mixed)" means the test started or ended on a VNx cell and on another vendor, "Mixed '
                    '(non-VNx)" two other vendors.'},
    {'name': 'saved_filters', 'arguments': '{"saved_filter_id": 12 (optional)}',
     'description': 'Without an id: the Saved Filters of Scoring & GAP Analysis (name, NR Mode, split, status). With an '
                    'id: the totals of its saved result (as the module shows them), without calculating anything.'},
    {'name': 'nq_calls', 'arguments': '{"group_by": ["operator", "failure_category"], "filters": {"campaign": ["CP1"], '
                                      '"service": ["data"]}, "limit": 50}',
     'description': 'Counts of Non-Qualified Calls (the failed or not qualified tests of Data and Voice) grouped by '
                    'fields: ' + ', '.join(NQ_FIELDS) + '. status, root_* are the tracking of the analysts; dta_rca_* '
                    'the DT Analyzer RCA. Values of filters are matched whatever their case.'},
    {'name': 'help_search', 'arguments': '{"query": "how to create a Saved Filter"}',
     'description': 'The passages of the Help of DriveTest Analyzer that best match a question about how the tool works.'},
    {'name': 'calculate', 'arguments': '{"expressions": ["921.81 - 863.11", "292182 / 382472 * 100"]}',
     'description': 'Arithmetic (+ - * / and parentheses) on figures of the results, for differences, shares and '
                    'ratios: every figure of an answer must come from a tool result, this one included.'},
]


class ToolError(ValueError):
    """A tool could not run with these arguments: the engine is told why."""


@dataclass
class ToolContext:
    repository: Any
    workspace_name: str
    username: str
    progress: Callable[[str], None] = lambda _message: None
    cancelled: Callable[[], bool] = lambda: False
    cache: dict[str, Any] = field(default_factory=dict)


def catalog_text() -> str:
    """The tools as the system prompt describes them."""
    return '\n'.join(f'- {tool["name"]} {tool["arguments"]}: {tool["description"]}' for tool in TOOLS)


def run_tool(context: ToolContext, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    handlers = {'workspace_overview': workspace_overview, 'list_values': list_values, 'scoring': scoring,
                'saved_filters': saved_filters, 'nq_calls': nq_calls, 'help_search': help_search, 'calculate': calculate}
    handler = handlers.get(str(name))
    if handler is None:
        raise ToolError(f'Unknown tool {name}: use one of {", ".join(handlers)}.')
    if not isinstance(arguments, dict):
        raise ToolError('The arguments of a tool are a JSON object.')
    return handler(context, arguments)


# -- helpers ----------------------------------------------------------------------------------------------------------

def _round(value: Any, digits: int = 2) -> Any:
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else round(value, digits)
    return value


def _strings(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return [str(item).strip() for item in values if str(item or '').strip()]


def _ready_cdrs(repository: Any) -> list[dict[str, Any]]:
    from src.modules.cdr.nr_mode import dataset_nr_mode
    rows = []
    for row in repository.list_datasets():
        item = dict(row)
        if item.get('status') != 'ready' or item.get('dataset_kind') not in {'data', 'voice', 'speech'}:
            continue
        item['nr_mode'] = dataset_nr_mode(item['dataset_kind'], item.get('nr_mode'), item.get('file_name'))
        rows.append(item)
    return rows


def _catalogues(context: ToolContext) -> dict[int, dict[str, list[str]]]:
    if 'catalogues' not in context.cache:
        ids = [int(row['id']) for row in _ready_cdrs(context.repository)]
        context.cache['catalogues'] = context.repository.cdr_catalogues_by_dataset(ids) if ids else {}
    return context.cache['catalogues']


def _operator_groups(context: ToolContext) -> list[dict[str, Any]]:
    if 'operator_groups' not in context.cache:
        try:
            groups = context.repository.list_operator_mapping_groups()
        except Exception:  # noqa: BLE001 - a workspace without Operator Maps
            groups = []
        context.cache['operator_groups'] = [group for group in groups or [] if isinstance(group, dict)]
    return context.cache['operator_groups']


def _canonical_operator(context: ToolContext, value: str) -> str:
    text = str(value or '').strip()
    for group in _operator_groups(context):
        names = [str(group.get('canonical') or ''), *(str(alias) for alias in group.get('aliases') or [])]
        if any(name.strip().casefold() == text.casefold() for name in names if name.strip()):
            return str(group.get('canonical') or text).strip()
    return text


def _excluded_operators(context: ToolContext) -> set[str]:
    from src.modules.mapping.operator_roles import EXCLUDE, normalize_mapping_role
    return {str(group.get('canonical') or '').strip().casefold() for group in _operator_groups(context)
            if normalize_mapping_role(group.get('role')) == EXCLUDE}


def _campaign_period(value: str) -> str:
    from src.modules.cdr.column_names import campaign_parts
    year, quarter, _mode = campaign_parts(str(value))
    return f'{year}-{quarter}' if year and quarter else ''


# -- workspace_overview -----------------------------------------------------------------------------------------------

def workspace_overview(context: ToolContext, _arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    from src.modules.cdr.cdr_auto_selection import cdr_campaigns, is_flex_campaign
    from src.modules.mapping.operator_roles import normalize_mapping_role
    from src.modules.scoring.scoring_selection import _complete_campaign_groups
    from src.modules.scoring.scoring_vendors import scoring_vendor_names, scoring_vendor_operators
    from src.modules.assistant.assistant_privacy import vendor_base_name

    repository = context.repository
    cdrs = _ready_cdrs(repository)
    campaigns_of = cdr_campaigns(repository, [int(row['id']) for row in cdrs]) if cdrs else {}
    kinds: dict[tuple[str, str], set[str]] = {}
    for row in cdrs:
        for campaign in campaigns_of.get(int(row['id']), []):
            kinds.setdefault((row['nr_mode'], str(campaign).casefold()), set()).add(row['dataset_kind'])
    methodology_of = _campaign_methodologies(context)
    campaigns: dict[str, list[dict[str, Any]]] = {}
    for mode in sorted({row['nr_mode'] for row in cdrs}):
        listed, rank = [], 0
        for group in _complete_campaign_groups(repository, mode):
            name = group[0]
            flex = is_flex_campaign(name)
            rank += 0 if flex else 1
            item = {'campaign': name, 'quarter': _campaign_period(name),
                    'cdr_types': sorted(kinds.get((mode, name.casefold()), set())),
                    'methodology': methodology_of.get(name.casefold(), methodology_of.get('', ''))}
            # A Flex campaign (one area) is left out of latest, previous… and is only scored when named.
            item.update({'flex': True} if flex else {'newest_rank': rank})
            listed.append(item)
        complete = {item['campaign'].casefold() for item in listed}
        incomplete = sorted({str(campaign) for row in cdrs if row['nr_mode'] == mode
                             for campaign in campaigns_of.get(int(row['id']), []) if str(campaign).casefold() not in complete})
        campaigns[mode] = listed + [{'campaign': name, 'quarter': _campaign_period(name), 'complete': False,
                                     'cdr_types': sorted(kinds.get((mode, name.casefold()), set()))} for name in incomplete]
    operators = []
    excluded = _excluded_operators(context)
    for group in _operator_groups(context):
        canonical = str(group.get('canonical') or '').strip()
        # The operators the Operator Maps exclude are left out of every result: they are not even listed.
        if canonical and canonical.casefold() not in excluded:
            role = normalize_mapping_role(group.get('role')) or ''
            operators.append({'operator': canonical, 'role': role or 'normal',
                              'nr_modes': list(group.get('nr_modes') or []) if isinstance(group.get('nr_modes'), list) else []})
    catalogues = _catalogues(context)
    vendor_operators = scoring_vendor_operators(catalogues, _operator_groups(context))
    vendors = sorted({vendor_base_name(name) for name in scoring_vendor_names(
        [value for catalogue in catalogues.values() for value in catalogue.get('vendors_only') or []], vendor_operators)},
        key=str.casefold)
    values = {field: sorted({value for catalogue in catalogues.values() for value in catalogue.get(field) or []}, key=str.casefold)
              for field in ('regions', 'clusters', 'cities')}
    from src.modules.scoring.saved_filters import list_saved_filters
    try:
        filters = list_saved_filters(repository)[:30]
    except Exception:  # noqa: BLE001 - no Saved Filter table yet
        filters = []
    return {
        'workspace': context.workspace_name,
        'campaigns_by_nr_mode': campaigns,
        'operators': operators,
        'default_gap_reference': _default_reference(context),
        'vendors': vendors,
        'regions': values['regions'], 'clusters': values['clusters'][:MAX_LIST_VALUES], 'city_count': len(values['cities']),
        'methodologies': _methodologies(context),
        'saved_filters': [{'id': item['id'], 'name': item.get('name') or '', 'nr_mode': item.get('nr_mode'),
                           'split_by': item.get('levels'), 'status': item.get('status'), 'starred': bool(item.get('pinned')),
                           'campaigns': item.get('resolved_campaigns') or (item.get('context_filters') or {}).get('Campaign') or []}
                          for item in filters],
    }


def _default_reference(context: ToolContext) -> str:
    names = [str(group.get('canonical') or '').strip() for group in _operator_groups(context)]
    excluded = _excluded_operators(context)
    names = [name for name in names if name and name.casefold() not in excluded]
    return next((name for name in names if name.casefold() == 'ee'), names[0] if names else 'EE')


def _methodologies(context: ToolContext) -> list[dict[str, Any]]:
    try:
        profiles = context.repository.get_scoring_profiles()['profiles']
    except (ValueError, KeyError, TypeError):
        return []
    listed = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        configuration = profile.get('configuration') or {}
        environments = (configuration.get('scope') or {}).get('environments') or {}
        metrics = configuration.get('metrics') or []
        listed.append({
            'methodology': str(profile.get('name') or ''),
            'campaigns': [str(value) for value in profile.get('campaigns') or []],
            'total_points': (configuration.get('scope') or {}).get('total_max_points'),
            'environments': [{'environment': name, 'points': (value or {}).get('total_points')}
                             for name, value in environments.items()],
            'categories': sorted({str(metric.get('category') or '') for metric in metrics if isinstance(metric, dict)}),
            'kpis': len(metrics),
        })
    return listed


def _campaign_methodologies(context: ToolContext) -> dict[str, str]:
    """The methodology of each campaign named by a methodology ('' for the default one)."""
    try:
        state = context.repository.get_scoring_profiles()
    except (ValueError, KeyError, TypeError):
        return {}
    found: dict[str, str] = {}
    active = str(state.get('active_profile_id') or '')
    for profile in state.get('profiles') or []:
        if not isinstance(profile, dict):
            continue
        for campaign in profile.get('campaigns') or []:
            found[str(campaign).casefold()] = str(profile.get('name') or '')
        if str(profile.get('id') or '') == active:
            found[''] = str(profile.get('name') or '')
    return found


# -- list_values ------------------------------------------------------------------------------------------------------

def list_values(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    fields = {'city': 'cities', 'region': 'regions', 'cluster': 'clusters', 'vendor': 'vendors_only',
              'operator': 'operators', 'campaign': 'campaigns'}
    wanted = str(arguments.get('field') or '').strip().casefold()
    if wanted not in fields:
        raise ToolError('field is one of City, Region, Cluster, Vendor, Operator or Campaign.')
    mode = str(arguments.get('nr_mode') or '').strip().upper()
    ids = {int(row['id']) for row in _ready_cdrs(context.repository) if not mode or row['nr_mode'] == mode}
    counts: Counter[str] = Counter()
    for dataset_id, catalogue in _catalogues(context).items():
        if dataset_id in ids:
            for value in catalogue.get(fields[wanted]) or []:
                counts[_canonical_operator(context, value) if wanted == 'operator' else value] += 1
    if wanted == 'operator':
        for name in _excluded_operators(context):
            counts.pop(next((value for value in counts if value.casefold() == name), ''), None)
    values = sorted(counts.items(), key=lambda item: item[0].casefold())
    return {'field': wanted, 'values': [{'value': value, 'cdrs': count} for value, count in values[:MAX_LIST_VALUES]],
            'count': len(values), 'truncated': len(values) > MAX_LIST_VALUES}


# -- scoring ----------------------------------------------------------------------------------------------------------

def scoring(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    from src.modules.scoring.saved_filters import calculate_selection

    campaigns = []
    for value in _strings(arguments.get('campaigns')) or ['latest']:
        campaigns.append(CAMPAIGN_CHOICES.get(value.casefold(), value))
    presets = [value for value in campaigns if value.startswith('@')]
    if presets and len(campaigns) > 1:
        raise ToolError('Give either campaign codes or one automatic choice (latest, previous, latest 2…), not both.')
    nr_mode = str(arguments.get('nr_mode') or 'NSA').strip()
    if nr_mode.casefold() not in {'nsa', 'sa', 'nsa vs sa'}:
        raise ToolError('nr_mode is NSA, SA or NSA vs SA.')
    nr_mode = {'nsa': 'NSA', 'sa': 'SA', 'nsa vs sa': 'NSA vs SA'}[nr_mode.casefold()]
    levels = []
    for value in _strings(arguments.get('split_by')) or ['Operator']:
        level = next((name for name in SPLIT_LEVELS if name.casefold() == value.casefold()), None)
        if level is None:
            raise ToolError(f'split_by takes {", ".join(SPLIT_LEVELS)}.')
        levels.append(level)
    if 'Operator' not in levels:
        levels.insert(0, 'Operator')
    if len(campaigns) > 1 or presets and presets[0] not in {'@latest-campaign', '@previous-campaign'} or nr_mode == 'NSA vs SA':
        if 'Campaign' not in levels:
            levels.append('Campaign')
    filters: dict[str, list[str]] = {}
    for key, values in (arguments.get('filters') or {}).items():
        name = next((field_name for field_name in FILTER_FIELDS if field_name.casefold() == str(key).casefold()), None)
        if name is None:
            raise ToolError(f'filters take {", ".join(FILTER_FIELDS)}.')
        if _strings(values):
            filters[name] = _strings(values)
    details = {value.casefold() for value in _strings(arguments.get('detail'))}
    unknown = details - set(SCORING_DETAILS)
    if unknown:
        raise ToolError(f'detail takes {", ".join(SCORING_DETAILS)}.')
    only = {}
    for key, values in (arguments.get('only') or {}).items():
        name = next((level for level in SPLIT_LEVELS if level.casefold() == str(key).casefold()), None)
        if name is None:
            raise ToolError(f'only takes {", ".join(SPLIT_LEVELS)}.')
        if _strings(values):
            only[name] = _strings(values)
    reference = str(arguments.get('reference_operator') or '').strip() or _default_reference(context)
    context.progress('Calculating the scoring')
    try:
        result, selection = calculate_selection(
            context.repository, campaigns, levels, nr_mode, context_filters=filters, baseline_operator=reference,
            progress=lambda _value, message: context.progress(message))
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return summarize_scoring(result, selection, details, only)


_KEYS = ('campaign', 'operator', 'vendor', 'region', 'cluster', 'city', 'dataset_type')


def _shown(row: dict[str, Any], only: dict[str, list[str]] | None) -> bool:
    """Whether a row of the result is one of the groups ``only`` lists (every row without it)."""
    for level, values in (only or {}).items():
        key = level.casefold().replace(' ', '_')
        if str(row.get(key) or '').casefold() not in {value.casefold() for value in values}:
            return False
    return True


def summarize_scoring(result: dict[str, Any], selection: dict[str, Any], details: set[str],
                      only: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """The figures of a scoring result an answer needs: per group its total points, and with ``details`` its points per
    environment and category, its KPIs and its GAP to the reference (``only``: the groups to list)."""
    keys = [key for key in _KEYS if any(row.get(key) is not None for row in result.get('totals') or [])]
    groups: dict[tuple, dict[str, Any]] = {}
    for row in result.get('totals') or []:
        if not _shown(row, only):
            continue
        group_key = tuple(row.get(key) for key in keys)
        group = groups.setdefault(group_key, {**{key: row.get(key) for key in keys}})
        environment, category = row.get('environment'), row.get('category')
        points = {'points': _round(row.get('total_points', row.get('weighted_points'))), 'max_points': _round(row.get('max_points')),
                  'available_points': _round(row.get('available_points')), 'complete': bool(row.get('complete_coverage')),
                  'samples': row.get('sample_count')}
        if environment == 'Combined' and category == 'Overall':
            group.update(points)
        elif category == 'Overall' and 'environments' in details:
            group.setdefault('by_environment', {})[environment] = {key: points[key] for key in ('points', 'max_points', 'complete')}
        elif environment == 'Combined' and 'categories' in details:
            group.setdefault('by_category', {})[category] = {key: points[key] for key in ('points', 'max_points', 'complete')}
    ordered = [_compact(group) for group in sorted(groups.values(), key=lambda item: -(item.get('points') or 0))]
    summary: dict[str, Any] = {
        'campaigns': selection['campaigns'], 'nr_mode': selection['nr_mode'], 'split_by': selection['levels'],
        'filters': {key: values for key, values in (selection.get('context_filters') or {}).items() if values and key != 'Campaign'},
        'methodology': selection.get('methodology') or '',
        'methodologies_by_campaign': selection.get('methodology_groups') or [],
        'cdrs': len(selection.get('dataset_ids') or []),
        'calculated_from': 'the rows of the CDRs' if selection.get('history_gap') else 'the Scoring History',
        'groups': ordered[:MAX_GROUPS], 'group_count': len(ordered),
        'warnings': [str(warning) for warning in result.get('warnings') or []][:8],
    }
    if len(ordered) > MAX_GROUPS:
        summary['note'] = f'Only the {MAX_GROUPS} groups with most points are listed: filter or split less to see the others.'
    if 'gap' in details:
        summary['gap_reference'] = selection.get('baseline_operator')
        summary['gap'] = [_compact({**{key: row.get(key) for key in keys},
                           'gap_points': _round(row.get('gap_points')), 'operator_points': _round(row.get('operator_points')),
                           'reference_points': _round(row.get('baseline_points')), 'complete': bool(row.get('complete_coverage'))})
                          for row in result.get('gap_totals') or [] if row.get('category') == 'Overall'
                          and row.get('environment', 'Combined') == 'Combined' and _shown(row, only)][:MAX_GROUPS]
    if 'kpis' in details:
        summary['kpis'] = _kpi_rows(result, keys, only)
        summary['kpis_note'] = (f'The {KPIS_PER_GROUP} KPIs that lose most points in each group; points and points lost '
                                'add up the environments.')
    return summary


def _kpi_rows(result: dict[str, Any], keys: list[str], only: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """The KPIs that lose most points in each group: their points and points lost over the environments, and their
    value in each one."""
    kpis: dict[tuple, dict[str, Any]] = {}
    for row in result.get('scoring') or []:
        if not _shown(row, only):
            continue
        group_key = tuple(row.get(key) for key in keys) + (row.get('kpi_code'),)
        entry = kpis.setdefault(group_key, {**{key: row.get(key) for key in keys}, 'kpi': row.get('kpi'),
                                            'code': row.get('kpi_code'), 'category': row.get('category'),
                                            'unit': row.get('unit'), 'points': 0.0, 'max_points': 0.0, 'values': {}})
        entry['max_points'] += float(row.get('max_points') or 0)
        entry['points'] += float(row.get('weighted_points') or 0)
        entry['values'][str(row.get('environment'))] = _round(row.get('value'), 3)
    by_group: dict[tuple, list[dict[str, Any]]] = {}
    for group_key, entry in kpis.items():
        entry['points_lost'] = _round(entry['max_points'] - entry['points'])
        entry['points'], entry['max_points'] = _round(entry['points']), _round(entry['max_points'])
        by_group.setdefault(group_key[:-1], []).append(entry)
    rows = []
    for entries in by_group.values():
        entries.sort(key=lambda item: -(item['points_lost'] or 0))
        rows.extend(_compact(entry) for entry in entries[:KPIS_PER_GROUP])
    return rows[:MAX_KPI_ROWS]


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    """A row without the group fields it does not have (Campaign when the split has none)."""
    return {key: value for key, value in row.items() if not (key in _KEYS and value is None)}


# -- saved_filters ----------------------------------------------------------------------------------------------------

def saved_filters(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    from src.modules.scoring.saved_filters import get_saved_filter, list_saved_filters

    filter_id = arguments.get('saved_filter_id')
    if filter_id in (None, ''):
        return {'saved_filters': [{'id': item['id'], 'name': item.get('name') or '', 'nr_mode': item.get('nr_mode'),
                                   'split_by': item.get('levels'), 'status': item.get('status'), 'starred': bool(item.get('pinned')),
                                   'last_used': item.get('last_used_at')} for item in list_saved_filters(context.repository)[:60]]}
    try:
        saved = get_saved_filter(context.repository, int(filter_id), include_result=True)
    except (TypeError, ValueError) as exc:
        raise ToolError('saved_filter_id is the number of a Saved Filter.') from exc
    if saved is None:
        raise ToolError(f'There is no Saved Filter {filter_id}.')
    if saved.get('status') != 'completed' or not isinstance(saved.get('result'), dict):
        return {'id': saved['id'], 'name': saved.get('name') or '', 'status': saved.get('status'),
                'note': 'This Saved Filter has no calculated result yet.'}
    selection = {'campaigns': saved.get('resolved_campaigns') or [], 'nr_mode': saved.get('nr_mode'),
                 'levels': saved.get('levels'), 'context_filters': saved.get('context_filters') or {},
                 'methodology': saved.get('scoring_profile_name') or '', 'dataset_ids': saved.get('dataset_ids') or [],
                 'baseline_operator': saved.get('baseline_operator')}
    summary = summarize_scoring(saved['result'], selection, {'environments', 'categories', 'gap'})
    summary['calculated_from'] = 'the saved result of the Saved Filter'
    return {'id': saved['id'], 'name': saved.get('name') or '', 'finished_at': saved.get('finished_at'), **summary}


# -- nq_calls ---------------------------------------------------------------------------------------------------------

def nq_calls(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    group_by = [value.casefold() for value in _strings(arguments.get('group_by'))]
    unknown = [value for value in group_by if value not in NQ_FIELDS]
    filters = {str(key).casefold(): _strings(values) for key, values in (arguments.get('filters') or {}).items()}
    unknown += [key for key in filters if key not in NQ_FIELDS]
    if unknown:
        raise ToolError(f'Unknown fields {", ".join(unknown)}: use {", ".join(NQ_FIELDS)}.')
    try:
        limit = max(1, min(200, int(arguments.get('limit') or 50)))
    except (TypeError, ValueError) as exc:
        raise ToolError('limit is a number.') from exc
    selected = ['l.operator AS operator', *(f'{NQ_FIELDS[name]} AS "{name}"' for name in group_by if name != 'operator')]
    where, parameters = [], []
    for name, values in filters.items():
        if not values or name == 'operator':
            continue
        where.append(f'LOWER(COALESCE({NQ_FIELDS[name]}, \'\')) IN ({", ".join("?" for _ in values)})')
        parameters.extend(value.casefold() for value in values)
    joins = ''
    if any(name.startswith(('status', 'root_')) for name in [*group_by, *filters]):
        joins += ' LEFT JOIN nq_call_tracking t ON t.call_key = l.call_key'
    if any(name.startswith('dta_rca_') for name in [*group_by, *filters]):
        joins += ' LEFT JOIN nq_dta_rca_results r ON r.dataset_id = l.dataset_id AND r.source_row_id = l.source_row_id'
    sql = (f'SELECT {", ".join(selected)}, COUNT(*) AS calls FROM nq_call_latest l{joins}'
           f'{" WHERE " + " AND ".join(where) if where else ""} GROUP BY {", ".join(str(index + 1) for index in range(len(selected)))}')
    try:
        with context.repository.connection() as connection:
            rows = [dict(row) for row in connection.execute(sql, parameters).fetchall()]
    except sqlite3.OperationalError as exc:
        if 'no such table' in str(exc):
            return {'calls': 0, 'note': 'The Non-Qualified Calls of this workspace have not been prepared yet.'}
        raise
    excluded = _excluded_operators(context)
    wanted_operators = {_canonical_operator(context, value).casefold() for value in filters.get('operator') or []}
    counts: Counter[tuple] = Counter()
    for row in rows:
        canonical = _canonical_operator(context, row.get('operator') or '')
        if canonical.casefold() in excluded or (wanted_operators and canonical.casefold() not in wanted_operators):
            continue
        key = tuple(canonical if name == 'operator' else (row.get(name) or '') for name in group_by)
        counts[key] += int(row['calls'])
    total = sum(counts.values())
    ordered = counts.most_common()
    return {'group_by': group_by, 'filters': filters, 'total_calls': total, 'groups': len(ordered),
            'rows': [{**dict(zip(group_by, key)), 'calls': count, 'share_percent': _round(count * 100 / total if total else 0, 1)}
                     for key, count in ordered[:limit]],
            **({'note': f'Only the {limit} largest groups are listed.'} if len(ordered) > limit else {})}


# -- help_search ------------------------------------------------------------------------------------------------------

_WORD = re.compile(r'[\w-]{3,}', re.UNICODE)


def help_search(_context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get('query') or '').strip()
    words = {word.casefold() for word in _WORD.findall(query)}
    if not words:
        raise ToolError('query holds the words to look for.')
    passages = []
    for path in sorted(HELP_DIR.glob('*.md')):
        heading = path.stem
        for block in re.split(r'\n(?=#{1,4} )', path.read_text(encoding='utf-8')):
            lines = block.strip().splitlines()
            if not lines:
                continue
            if lines[0].startswith('#'):
                heading = lines[0].lstrip('#').strip()
            text = '\n'.join(lines)
            found = Counter(word.casefold() for word in _WORD.findall(text))
            score = sum(1 + math.log(found[word]) for word in words if found[word])
            if score:
                passages.append((score, path.name, heading, text[:1500]))
    passages.sort(key=lambda item: -item[0])
    return {'passages': [{'chapter': name, 'section': heading, 'text': text} for _score, name, heading, text in passages[:5]]}


# -- calculate --------------------------------------------------------------------------------------------------------

_OPERATORS = {ast.Add: operator_module.add, ast.Sub: operator_module.sub, ast.Mult: operator_module.mul,
              ast.Div: operator_module.truediv}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _evaluate(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    raise ToolError('Only numbers, + - * / and parentheses are calculated.')


def calculate(_context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    results = []
    for expression in _strings(arguments.get('expressions'))[:30]:
        if len(expression) > 200:
            raise ToolError('An expression has at most 200 characters.')
        try:
            value = _evaluate(ast.parse(expression.replace(',', ''), mode='eval'))
        except ZeroDivisionError:
            results.append({'expression': expression, 'error': 'division by zero'})
            continue
        except SyntaxError as exc:
            raise ToolError(f'{expression} is not an arithmetic expression.') from exc
        results.append({'expression': expression, 'result': _round(value, 4)})
    if not results:
        raise ToolError('expressions lists the operations to calculate.')
    return {'results': results}


def result_size(document: Any) -> int:
    return len(json.dumps(document, ensure_ascii=False, default=str))
