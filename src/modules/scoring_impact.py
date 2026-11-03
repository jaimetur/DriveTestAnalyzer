"""Methodology Impact of Scoring & GAP Analysis: what a change of methodology does to the results.

The tests of one campaign are scored with two methodologies, with the scope of the open Saved Filter (NR Mode, filters and
GAP reference), so every difference comes from the methodology alone, never from the network: its operators, environments,
categories, KPIs, geographical areas, GAPs and points lost, with the analysis of scoring_impact_analysis and the maps of
scoring_impact_maps. Between two campaigns, the campaigns only choose the methodologies (those that apply to each one): the
tests are those of the later campaign.

Nothing is saved but the calculation, kept in the cache of the workspace (see scoring_cache) with a key that holds all it
depends on: the CDRs, methodologies, filters, Operator Maps and this code.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from pathlib import Path
from typing import Any, Callable, Iterable

from src.modules import scoring as engine
from src.modules import scoring_cache
from src.modules.cdr_auto_selection import campaign_identity, is_flex_campaign
from src.modules.column_names import campaign_sort_key, compact_campaign_value
from src.modules.nr_mode import NSA_VS_SA, SAME_OPERATOR_NSA, normalize_scoring_nr_mode, nr_mode_label
from src.modules import postal_areas
from src.modules.saved_filters import (
    AGGREGATION_CONTRACT_VERSION, DEFAULT_BASELINE_OPERATOR, _attach_mapping_boundaries, _load_source_frames, _points_loss_of,
    _prepare_saved_filter, _read_campaigns, _source_snapshot,
)
from src.modules.scoring_area_summary import has_area_filters, whole_country_filters
from src.modules.scoring_impact_analysis import competition_part, conclusions, drivers_part, exposure_part, stability_part
from src.modules.scoring_impact_maps import build_maps, impact_map
from src.modules.scoring_config import BEST_NETWORK_SCORING, MOST_RELIABLE_SCORING
from src.modules.scoring_history import HistoryUnavailable, calculate_scoring_from_history, history_gap
from src.modules.scoring_insights import _kpi_rows, _losses, _service, loss_kinds
from src.modules.scoring_methodologies import methodology_for
from src.modules.scoring_selection import _complete_campaign_groups, auto_scoring_cdr_ids
from src.modules.scoring_vendors import scoring_vendor_operators
from src.modules.scoring_views import build_scoring_views, refresh_baseline_warning

CACHE_KIND = 'methodology-impact'
MAPS_CACHE_KIND = 'methodology-impact-maps'
# The other campaigns the same change is tried on, the newest first.
OTHER_CAMPAIGNS = 6
MODES = ('campaigns', 'methodologies')
AREA_LEVELS = ('Region', 'Cluster', 'City')
COMBINED = 'Combined'
COMBINED_LABEL = 'All Environments'
KEPT_JOBS = 24
# Values that differ by less than this are the same.
_SAME = 1e-6
_DIGITS = 4

CHANGE_LABELS = {'added': 'New KPI', 'removed': 'Removed KPI', 'points': 'Points', 'thresholds': 'Thresholds',
                 'calculation': 'Formula or filters', 'scoring': 'Score mapping', 'definition': 'Definition'}
_THRESHOLD_NAMES = {'low': 'Low', 'medium': 'Medium', 'high': 'High', 'ultra': 'Ultra'}
_MAPPING_NAMES = {'low_score': 'Low score', 'medium_score': 'Medium score', 'high_score': 'High score', 'ultra_score': 'Ultra score'}
_DEFINITION_FIELDS = {'kpi': 'Name', 'category': 'Category', 'kpi_type': 'Type', 'source_kind': 'CDR type', 'unit': 'Unit',
                      'direction': 'Direction', 'mapping_method': 'Mapping method'}

_jobs: dict[tuple[str, str], dict[str, Any]] = {}
_guard = threading.Lock()
_code_hash: str | None = None


def _code_version() -> str:
    """The code of what the impact is built from: a change calculates it again (with the modules of the scoring)."""
    global _code_hash
    if _code_hash is None:
        digest = hashlib.sha256()
        for name in ('scoring_impact', 'scoring_impact_analysis', 'scoring_impact_maps', 'scoring_views', 'scoring_insights'):
            try:
                digest.update((Path(__file__).parent / f'{name}.py').read_bytes())
            except OSError:
                digest.update(name.encode('utf-8'))
        _code_hash = digest.hexdigest()
    return _code_hash


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _rounded(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else round(number, _DIGITS) + 0.0


def _differ(before: Any, after: Any) -> bool:
    first, second = _number(before), _number(after)
    if first is None or second is None:
        return before != after
    return abs(first - second) > _SAME


def _shift(before: Any, after: Any, *, absent_is_zero: bool = False) -> dict[str, Any]:
    """Before, after and after minus before; a KPI one methodology does not have counts zero there (``absent_is_zero``)."""
    first, second = _number(before), _number(after)
    if absent_is_zero:
        delta = (second or 0.0) - (first or 0.0) if first is not None or second is not None else None
    else:
        delta = second - first if first is not None and second is not None else None
    return {'before': _rounded(first), 'after': _rounded(second), 'delta': _rounded(delta)}


def _peak(cells: Iterable[dict[str, Any]]) -> float:
    return max((abs(cell['delta']) for cell in cells if cell.get('delta') is not None), default=0.0)


def _ranks(values: dict[str, float | None]) -> dict[str, int]:
    """The position of each operator (1 for the most points; equal points share it), those without points left out."""
    measured = [value for value in values.values() if value is not None]
    return {name: 1 + sum(other > value + _SAME for other in measured) for name, value in values.items() if value is not None}


# ---------------------------------------------------------------------------------------------------------------------
# What the tab offers
# ---------------------------------------------------------------------------------------------------------------------

def _campaign_entries(repository: Any, nr_mode: str, profiles: dict[str, Any]) -> list[dict[str, Any]]:
    """The campaigns of an NR Mode with Data, Voice and Speech CDRs, newest first, each with its methodology."""
    entries = []
    for group in _complete_campaign_groups(repository, nr_mode):
        profile = methodology_for(profiles, group[0])
        entries.append({'value': group[0], 'spellings': list(group), 'label': compact_campaign_value(group[0]) or group[0],
                        'flex': is_flex_campaign(group[0]), 'methodology_id': profile['id'], 'methodology_name': profile['name']})
    return entries


def _own_campaigns(saved_filter: dict[str, Any]) -> set[str]:
    filters = saved_filter.get('resolved_context_filters') or {}
    return {campaign_identity(value) for value in filters.get('Campaign') or []}


def impact_options(repository: Any, saved_filter: dict[str, Any]) -> dict[str, Any]:
    """The methodologies and campaigns the comparison can choose, and what it compares at first: the latest campaign of the
    Saved Filter and the nearest earlier one with another methodology (the methodologies of those two)."""
    profiles = repository.get_scoring_profiles()
    selected = normalize_scoring_nr_mode(saved_filter.get('nr_mode')) or 'NSA'
    modes = ['NSA', 'SA'] if selected == NSA_VS_SA else [selected]
    campaigns = {mode: _campaign_entries(repository, mode, profiles) for mode in modes}
    modes = [mode for mode in modes if campaigns[mode]] or modes
    methodologies = [{'id': profile['id'], 'name': profile['name'], 'campaigns': profile.get('campaigns') or {}}
                     for profile in profiles['profiles']]
    own = _own_campaigns(saved_filter)

    def defaults_of(entries: list[dict[str, Any]]) -> dict[str, str]:
        usable = [entry for entry in entries if not entry['flex']] or entries
        latest = next((entry for entry in usable if campaign_identity(entry['value']) in own), usable[0] if usable else None)
        older = usable[usable.index(latest) + 1:] if latest else []
        earlier = next((entry for entry in older if entry['methodology_id'] != latest['methodology_id']), older[0] if older else None)
        latest_method = latest['methodology_id'] if latest else profiles['active_profile_id']
        other_method = (earlier['methodology_id'] if earlier and earlier['methodology_id'] != latest_method else
                        next((item['id'] for item in methodologies if item['id'] != latest_method), latest_method))
        return {'campaign_a': earlier['value'] if earlier else '', 'campaign_b': latest['value'] if latest else '',
                'methodology_a': other_method, 'methodology_b': latest_method, 'campaign': latest['value'] if latest else ''}

    by_nr_mode = {mode: defaults_of(campaigns[mode]) for mode in modes}
    return {'nr_modes': modes, 'campaigns': campaigns, 'methodologies': methodologies, 'by_nr_mode': by_nr_mode,
            'defaults': {'mode': 'campaigns', 'nr_mode': modes[0], **by_nr_mode[modes[0]]}}


def normalize_selection(raw: Any, options: dict[str, Any]) -> dict[str, str]:
    """The comparison asked for: what is not given takes its default, and what cannot be compared is refused."""
    raw = raw if isinstance(raw, dict) else {}
    nr_mode = str(raw.get('nr_mode') or '').strip()
    nr_mode = nr_mode if nr_mode in options['nr_modes'] else options['defaults']['nr_mode']
    # (What is not given, as those of its own NR Mode.)
    defaults = {**options['defaults'], **options['by_nr_mode'][nr_mode], 'nr_mode': nr_mode}
    selection = {key: str(raw.get(key) or default).strip() for key, default in defaults.items()}
    selection['nr_mode'] = nr_mode
    if selection['mode'] not in MODES:
        raise ValueError('The Methodology Impact compares two campaigns or two methodologies.')
    values = {entry['value'] for entry in options['campaigns'].get(selection['nr_mode'], [])}
    if selection['mode'] == 'campaigns':
        for key in ('campaign_a', 'campaign_b'):
            if selection[key] not in values:
                raise ValueError(f"Choose two campaigns of {nr_mode_label(selection['nr_mode'])} with Data, Voice and Speech CDRs.")
        if selection['campaign_a'] == selection['campaign_b']:
            raise ValueError('Choose two different campaigns to compare.')
        # The earlier campaign first, whichever was chosen first.
        if campaign_sort_key(selection['campaign_a']) > campaign_sort_key(selection['campaign_b']):
            selection['campaign_a'], selection['campaign_b'] = selection['campaign_b'], selection['campaign_a']
    else:
        identifiers = {item['id'] for item in options['methodologies']}
        if selection['methodology_a'] not in identifiers or selection['methodology_b'] not in identifiers:
            raise ValueError('Choose two methodologies of this workspace.')
        if selection['methodology_a'] == selection['methodology_b']:
            raise ValueError('Choose two different methodologies to compare.')
        if selection['campaign'] not in values:
            raise ValueError(f"Choose a campaign of {nr_mode_label(selection['nr_mode'])} with Data, Voice and Speech CDRs.")
    return selection


# ---------------------------------------------------------------------------------------------------------------------
# What changed between two methodologies
# ---------------------------------------------------------------------------------------------------------------------

def _active_environments(*configurations: dict[str, Any]) -> list[str]:
    """The environments with points in any of the methodologies, in their order."""
    names: dict[str, None] = {}
    for configuration in configurations:
        for name, scope in ((configuration.get('scope') or {}).get('environments') or {}).items():
            if (_number(scope.get('total_points')) or 0) > 0:
                names.setdefault(name)
    return list(names)


def _environment_labels(*configurations: dict[str, Any]) -> dict[str, str]:
    labels = {COMBINED: COMBINED_LABEL}
    for configuration in configurations:
        for name, scope in ((configuration.get('scope') or {}).get('environments') or {}).items():
            labels.setdefault(name, str(scope.get('display_name') or name))
    return labels


def _metric_points(metric: dict[str, Any] | None, environment: str) -> float:
    context = ((metric or {}).get('contexts') or {}).get(environment) or {}
    return _number(context.get('max_points')) or 0.0


def _kpi_pairs(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[tuple[dict | None, dict | None]]:
    """Each KPI in both methodologies: by code and name, then by name (another code) and by code (another name)."""
    def name(metric: dict[str, Any]) -> tuple[str, str]:
        return str(metric.get('kpi') or '').strip().casefold(), str(metric.get('source_kind') or '').casefold()

    left, right = list(before), list(after)
    pairs: list[tuple[dict | None, dict | None]] = []
    for matches in (lambda first, second: first['code'] == second['code'] and name(first) == name(second),
                    lambda first, second: name(first) == name(second),
                    lambda first, second: first['code'] == second['code']):
        for metric in list(right):
            other = next((item for item in left if matches(item, metric)), None)
            if other is not None:
                pairs.append((other, metric))
                left.remove(other)
                right.remove(metric)
    pairs.extend((None, metric) for metric in right)
    pairs.extend((metric, None) for metric in left)
    order = {metric['code']: index for index, metric in enumerate(after)}
    earlier = {metric['code']: index for index, metric in enumerate(before)}
    pairs.sort(key=lambda pair: (order.get(pair[1]['code'], len(order)) if pair[1] else len(order),
                                 earlier.get(pair[0]['code'], 0) if pair[0] else 0))
    return pairs


def _text(value: Any) -> str:
    if value is None or value == '':
        return '—'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    number = _number(value)
    if number is not None:
        return f'{number:.2f}'.rstrip('0').rstrip('.')
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _threshold_text(value: Any) -> str:
    # An Ultra threshold can be a rule (the best of the operators in the calculation).
    return str(value.get('rule')).replace('_', ' ') if isinstance(value, dict) and value.get('rule') else _text(value)


def _pair_changes(first: dict[str, Any], second: dict[str, Any], environments: list[str],
                  labels: dict[str, str]) -> tuple[list[str], list[dict[str, str]]]:
    """The kinds of change of a KPI in both methodologies, and each change (before and after, in its environment)."""
    kinds: list[str] = []
    details: list[dict[str, str]] = []

    def add(kind: str, label: str, before: str, after: str, environment: str = '') -> None:
        if kind not in kinds:
            kinds.append(kind)
        details.append({'kind': kind, 'label': label, 'environment': environment, 'before': before, 'after': after})

    for field, label in _DEFINITION_FIELDS.items():
        was, now = first.get(field), second.get(field)
        if (was or '') != (now or '') and not (field == 'mapping_method' and {was or 'piecewise_linear', now or 'piecewise_linear'} == {'piecewise_linear'}):
            add('definition', label, _text(was), _text(now))
    calculation, other = first.get('calculation') or {}, second.get('calculation') or {}
    if calculation.get('formula') != other.get('formula'):
        add('calculation', 'Formula', _text(calculation.get('formula')), _text(other.get('formula')))
    if (calculation.get('filters') or {}) != (other.get('filters') or {}):
        add('calculation', 'Filters', _text(calculation.get('filters') or ''), _text(other.get('filters') or ''))
    for environment in environments:
        was, now = (first.get('contexts') or {}).get(environment), (second.get('contexts') or {}).get(environment)
        if not isinstance(was, dict) or not isinstance(now, dict):
            continue
        name = labels.get(environment, environment)
        if _differ(_number(was.get('max_points')) or 0.0, _number(now.get('max_points')) or 0.0):
            add('points', 'Points', _text(was.get('max_points')), _text(now.get('max_points')), name)
        thresholds, others = was.get('thresholds') or {}, now.get('thresholds') or {}
        for key, label in _THRESHOLD_NAMES.items():
            if thresholds.get(key) != others.get(key) and _differ(thresholds.get(key), others.get(key)):
                add('thresholds', label, _threshold_text(thresholds.get(key)), _threshold_text(others.get(key)), name)
        mapping, other_mapping = was.get('score_mapping') or {}, now.get('score_mapping') or {}
        for key, label in _MAPPING_NAMES.items():
            if _differ(mapping.get(key), other_mapping.get(key)):
                add('scoring', label, _text(mapping.get(key)), _text(other_mapping.get(key)), name)
    return kinds, details


def methodology_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """What changed from one methodology to the other: its KPIs (added, removed, with other points, thresholds, formula…),
    the points of each environment and category, and its general settings."""
    environments = _active_environments(after, before)
    labels = _environment_labels(after, before)
    kpis = []
    counts = dict.fromkeys(('added', 'removed', 'points', 'thresholds', 'calculation', 'scoring', 'definition', 'unchanged'), 0)
    pairs = _kpi_pairs(before.get('metrics') or [], after.get('metrics') or [])
    for first, second in pairs:
        metric = second or first
        total_before = sum(_metric_points(first, name) for name in environments)
        total_after = sum(_metric_points(second, name) for name in environments)
        if first is None or second is None:
            kinds = ['added' if first is None else 'removed']
            details = [{'kind': 'points', 'label': 'Points', 'environment': labels.get(name, name),
                        'before': _text(_metric_points(first, name)), 'after': _text(_metric_points(second, name))}
                       for name in environments if _metric_points(metric, name) > 0]
        else:
            kinds, details = _pair_changes(first, second, environments, labels)
        for kind in kinds:
            counts[kind] += 1
        if not kinds:
            counts['unchanged'] += 1
            continue
        kpis.append({'code': metric['code'], 'kpi': metric.get('kpi'), 'category': metric.get('category'),
                     'kpi_type': metric.get('kpi_type'), 'service': _service(metric), 'status': kinds[0] if kinds[0] in ('added', 'removed') else 'changed',
                     'kinds': kinds, **_shift(total_before, total_after), 'details': details})
    categories: dict[str, dict[str, Any]] = {}
    for first, second in pairs:
        for metric, side in ((first, 'before'), (second, 'after')):
            if metric is None:
                continue
            entry = categories.setdefault(str(metric.get('category') or ''), {
                'category': metric.get('category'), 'service': _service(metric), 'before': 0.0, 'after': 0.0})
            entry[side] += sum(_metric_points(metric, name) for name in environments)
    settings = []
    for key, value in sorted((after.get('interpolation') or {}).items()):
        was = (before.get('interpolation') or {}).get(key)
        if key != 'source_note' and was != value and _differ(was, value):
            settings.append({'label': f"Interpolation: {key.replace('_', ' ')}", 'before': _text(was), 'after': _text(value)})
    if list(before.get('gap_priority') or []) != list(after.get('gap_priority') or []):
        settings.append({'label': 'Order of the GAP priorities', 'before': 'Other order', 'after': 'Changed'})
    environment_rows = []
    for name in environments:
        was = _number((((before.get('scope') or {}).get('environments') or {}).get(name) or {}).get('total_points')) or 0.0
        now = _number((((after.get('scope') or {}).get('environments') or {}).get(name) or {}).get('total_points')) or 0.0
        environment_rows.append({'name': name, 'label': labels.get(name, name), **_shift(was, now)})
    same = not kpis and not settings and not any(row['delta'] for row in environment_rows)
    return {
        'same': same, 'counts': counts, 'kpis': kpis, 'environments': environment_rows, 'settings': settings,
        'categories': [{**entry, **_shift(entry['before'], entry['after'])} for entry in categories.values()],
        'kinds': {kind: label for kind, label in CHANGE_LABELS.items() if counts.get(kind)},
    }


# ---------------------------------------------------------------------------------------------------------------------
# The impact, from the results of both methodologies
# ---------------------------------------------------------------------------------------------------------------------

def _views(result: dict[str, Any], baseline: str, aliases: list[str], operator_groups: list[dict],
           vendor_groups: list[dict]) -> dict[str, dict[str, Any]]:
    """The score tables of a result (as Scoring Tables shows them) per environment."""
    job = {'levels': ['Operator'], 'aggregation_levels': ['Operator'], 'baseline_operator': baseline, 'baseline_aliases': aliases,
           'configuration': result.get('configuration'), 'aggregation_contract_version': AGGREGATION_CONTRACT_VERSION}
    views = build_scoring_views(job, result, operator_groups, vendor_mapping_groups=vendor_groups)
    refresh_baseline_warning(result, views, baseline)
    return {str((table.get('context') or {}).get('environment')): table for table in views.get('score_tables', [])}


def _points(row: dict[str, Any] | None, operator: str) -> float | None:
    return _number((((row or {}).get('values') or {}).get(operator) or {}).get('points'))


def _operators(before: dict[str, dict], after: dict[str, dict]) -> list[dict[str, Any]]:
    """The operators of the tables with their style, as the Operator Maps name them, in the order of the results."""
    styles: dict[str, Any] = {}
    order: dict[str, None] = {}
    reference = ''
    for tables in (after, before):
        for table in tables.values():
            styles = {**(table.get('operator_styles') or {}), **styles}
            order.update(dict.fromkeys(table.get('operators') or []))
            reference = reference or str(table.get('baseline_operator') or '')
    return [{'operator': name, 'label': (styles.get(name) or {}).get('label') or name, 'color': (styles.get(name) or {}).get('color'),
             'position': (styles.get(name) or {}).get('position', 0), 'is_reference': name == reference} for name in order]


def _scoring_part(before: dict[str, dict], after: dict[str, dict], environments: list[str],
                  operators: list[str]) -> dict[str, Any]:
    """Each operator before and after in each environment: points, share of the maximum and position."""
    part = {}
    for environment in environments:
        first, second = before.get(environment) or {}, after.get(environment) or {}
        total_before, total_after = first.get('total') or {}, second.get('total') or {}
        points_before = {name: _points(total_before, name) for name in operators}
        points_after = {name: _points(total_after, name) for name in operators}
        ranks_before, ranks_after = _ranks(points_before), _ranks(points_after)
        maximum_before, maximum_after = _number(total_before.get('max_points')), _number(total_after.get('max_points'))
        rows = {}
        for name in operators:
            if points_before[name] is None and points_after[name] is None:
                continue
            rows[name] = {**_shift(points_before[name], points_after[name]),
                          'rank_before': ranks_before.get(name), 'rank_after': ranks_after.get(name),
                          'complete': all(((table.get('values') or {}).get(name) or {}).get('complete') is not False
                                          for table in (total_before, total_after))}
        part[environment] = {'max_before': _rounded(maximum_before), 'max_after': _rounded(maximum_after), 'operators': rows,
                             'peak': _peak(rows.values())}
    return part


def _category_part(before: dict[str, dict], after: dict[str, dict], environments: list[str],
                   operators: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Each category of each environment: its maximum and the points of each operator before and after."""
    def sums(table: dict[str, Any]) -> dict[str, dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for row in _kpi_rows(table):
            maximum = _number(row.get('max_points')) or 0.0
            if maximum <= 0:
                continue
            group = groups.setdefault(str(row.get('category') or ''), {
                'service': _service(row), 'maximum': 0.0, 'points': {}})
            group['maximum'] += maximum
            for name in operators:
                points = _points(row, name)
                if points is not None:
                    group['points'][name] = group['points'].get(name, 0.0) + points
        return groups

    part = {}
    for environment in environments:
        first, second = sums(before.get(environment) or {}), sums(after.get(environment) or {})
        rows = []
        for category in dict.fromkeys([*second, *first]):
            was, now = first.get(category), second.get(category)
            # (A category one methodology does not have counts zero there.)
            cells = {name: _shift((was or {}).get('points', {}).get(name), (now or {}).get('points', {}).get(name),
                                  absent_is_zero=was is None or now is None) for name in operators}
            cells = {name: cell for name, cell in cells.items() if cell['before'] is not None or cell['after'] is not None}
            rows.append({'category': category, 'service': (now or was)['service'],
                         'max_before': _rounded((was or {}).get('maximum', 0.0)), 'max_after': _rounded((now or {}).get('maximum', 0.0)),
                         'operators': cells, 'peak': _peak(cells.values())})
        part[environment] = rows
    return part


def _kpi_part(pairs: list[tuple[dict | None, dict | None]], changes: dict[str, Any], before: dict[str, dict], after: dict[str, dict],
              environments: list[str], operators: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Each KPI of each environment with the points of each operator before and after, the KPIs that move most first."""
    kinds = {row['code']: row['kinds'] for row in changes['kpis']}
    part = {}
    for environment in environments:
        rows_before = {row['kpi_code']: row for row in _kpi_rows(before.get(environment) or {})}
        rows_after = {row['kpi_code']: row for row in _kpi_rows(after.get(environment) or {})}
        rows = []
        for first, second in pairs:
            metric = second or first
            was = rows_before.get(first['code']) if first else None
            now = rows_after.get(second['code']) if second else None
            maximum_before = _number((was or {}).get('max_points')) or 0.0
            maximum_after = _number((now or {}).get('max_points')) or 0.0
            if maximum_before <= 0 and maximum_after <= 0:
                continue
            absent = first is None or second is None or maximum_before <= 0 or maximum_after <= 0
            cells = {}
            for name in operators:
                value_before = ((was or {}).get('values') or {}).get(name) or {}
                value_after = ((now or {}).get('values') or {}).get(name) or {}
                cell = _shift(value_before.get('points'), value_after.get('points'), absent_is_zero=absent)
                if cell['before'] is None and cell['after'] is None:
                    continue
                cell.update({'value_before': _rounded(value_before.get('value')), 'value_after': _rounded(value_after.get('value')),
                             'score_before': _rounded(value_before.get('score')), 'score_after': _rounded(value_after.get('score'))})
                cells[name] = cell
            rows.append({'code': metric['code'], 'kpi': metric.get('kpi'), 'category': metric.get('category'),
                         'kpi_type': metric.get('kpi_type'), 'service': _service(metric), 'kinds': kinds.get(metric['code'], []),
                         'max_before': _rounded(maximum_before), 'max_after': _rounded(maximum_after),
                         'operators': cells, 'peak': _peak(cells.values())})
        part[environment] = sorted(rows, key=lambda row: -row['peak'])
    return part


def _gap_of(table: dict[str, Any] | None, operator: str, reference: str, rows: list[dict[str, Any]]) -> float | None:
    """What an operator is ahead of the reference on some KPI rows of its table (those both measured)."""
    gaps = [points - other for row in rows
            if (points := _points(row, operator)) is not None and (other := _points(row, reference)) is not None]
    return sum(gaps) if gaps else None


def _flip(cell: dict[str, Any]) -> bool:
    """Whether an operator is ahead of the reference before and behind it after, or the other way round."""
    first, second = _number(cell.get('before')), _number(cell.get('after'))
    return first is not None and second is not None and first * second < 0 and abs(first - second) > _SAME


def _gap_part(pairs: list[tuple[dict | None, dict | None]], before: dict[str, dict], after: dict[str, dict],
              environments: list[str], operators: list[str], reference: str) -> dict[str, Any]:
    """The GAP of each operator against the reference before and after, in total, per category and per KPI."""
    compared = [name for name in operators if name != reference]
    part = {}
    for environment in environments:
        first, second = before.get(environment) or {}, after.get(environment) or {}
        rows_before, rows_after = _kpi_rows(first), _kpi_rows(second)
        total_before, total_after = first.get('total') or {}, second.get('total') or {}

        def total_gap(total: dict[str, Any], name: str) -> float | None:
            points, other = _points(total, name), _points(total, reference)
            return points - other if points is not None and other is not None else None
        totals = {}
        for name in compared:
            cell = _shift(total_gap(total_before, name), total_gap(total_after, name))
            if cell['before'] is not None or cell['after'] is not None:
                totals[name] = {**cell, 'flip': _flip(cell)}
        categories = []
        names = dict.fromkeys(str(row.get('category') or '') for row in [*rows_after, *rows_before]
                              if (_number(row.get('max_points')) or 0) > 0)
        for category in names:
            members_before = [row for row in rows_before if str(row.get('category') or '') == category and (_number(row.get('max_points')) or 0) > 0]
            members_after = [row for row in rows_after if str(row.get('category') or '') == category and (_number(row.get('max_points')) or 0) > 0]
            cells = {}
            for name in compared:
                cell = _shift(_gap_of(first, name, reference, members_before), _gap_of(second, name, reference, members_after),
                              absent_is_zero=not members_before or not members_after)
                if cell['before'] is not None or cell['after'] is not None:
                    cells[name] = {**cell, 'flip': _flip(cell)}
            categories.append({'category': category, 'operators': cells, 'peak': _peak(cells.values())})
        kpis = []
        by_before, by_after = {row['kpi_code']: row for row in rows_before}, {row['kpi_code']: row for row in rows_after}
        for one, other in pairs:
            metric = other or one
            was, now = by_before.get(one['code']) if one else None, by_after.get(other['code']) if other else None
            maximum_before = _number((was or {}).get('max_points')) or 0.0
            maximum_after = _number((now or {}).get('max_points')) or 0.0
            if maximum_before <= 0 and maximum_after <= 0:
                continue
            cells = {}
            for name in compared:
                cell = _shift(_gap_of(first, name, reference, [was] if was else []), _gap_of(second, name, reference, [now] if now else []),
                              absent_is_zero=maximum_before <= 0 or maximum_after <= 0)
                if cell['before'] is not None or cell['after'] is not None:
                    cells[name] = {**cell, 'flip': _flip(cell)}
            kpis.append({'code': metric['code'], 'kpi': metric.get('kpi'), 'category': metric.get('category'),
                         'kpi_type': metric.get('kpi_type'), 'operators': cells, 'peak': _peak(cells.values())})
        part[environment] = {'total': totals, 'categories': categories,
                             'kpis': sorted(kpis, key=lambda row: -row['peak'])}
    return part


def _points_lost_part(pairs: list[tuple[dict | None, dict | None]], before: dict[str, dict], after: dict[str, dict],
                      configuration_before: dict[str, Any], configuration_after: dict[str, Any],
                      environments: list[str], operators: list[str]) -> dict[str, Any]:
    """The points each operator loses before and after, per kind of loss (see Points Lost), category and KPI."""
    def formulas(configuration: dict[str, Any]) -> dict[str, str]:
        return {str(metric.get('code')): str((metric.get('calculation') or {}).get('formula') or '')
                for metric in configuration.get('metrics') or []}

    def lost(row: dict[str, Any] | None, name: str) -> float | None:
        points, maximum = _points(row, name), _number((row or {}).get('max_points')) or 0.0
        return max(0.0, maximum - points) if points is not None and maximum > 0 else None

    formulas_before, formulas_after = formulas(configuration_before), formulas(configuration_after)
    part = {}
    for environment in environments:
        first, second = before.get(environment) or {}, after.get(environment) or {}
        rows_before, rows_after = _kpi_rows(first), _kpi_rows(second)
        kinds = {kind['key']: kind for kind in [*loss_kinds(first, formulas_before), *loss_kinds(second, formulas_after)]} if first or second else {}
        operators_part = {}
        for name in operators:
            parts_before = _losses(first, name, formulas_before)[0] if first else {}
            parts_after = _losses(second, name, formulas_after)[0] if second else {}
            if _points(first.get('total'), name) is None and _points(second.get('total'), name) is None:
                continue
            total = _shift(sum(parts_before.values()) if first else None, sum(parts_after.values()) if second else None)
            operators_part[name] = {**total, 'parts_before': {key: _rounded(value) for key, value in parts_before.items()},
                                    'parts_after': {key: _rounded(value) for key, value in parts_after.items()}}
        categories = []
        names = dict.fromkeys(str(row.get('category') or '') for row in [*rows_after, *rows_before]
                              if (_number(row.get('max_points')) or 0) > 0)
        for category in names:
            cells = {}
            for name in operators:
                values_before = [value for row in rows_before if str(row.get('category') or '') == category
                                 and (value := lost(row, name)) is not None]
                values_after = [value for row in rows_after if str(row.get('category') or '') == category
                                and (value := lost(row, name)) is not None]
                if values_before or values_after:
                    cells[name] = _shift(sum(values_before) if values_before else None, sum(values_after) if values_after else None,
                                         absent_is_zero=True)
            categories.append({'category': category, 'operators': cells, 'peak': _peak(cells.values())})
        kpis = []
        by_before, by_after = {row['kpi_code']: row for row in rows_before}, {row['kpi_code']: row for row in rows_after}
        for one, other in pairs:
            metric = other or one
            was, now = by_before.get(one['code']) if one else None, by_after.get(other['code']) if other else None
            cells = {}
            for name in operators:
                lost_before, lost_after = lost(was, name), lost(now, name)
                if lost_before is not None or lost_after is not None:
                    cells[name] = _shift(lost_before, lost_after, absent_is_zero=True)
            if cells:
                kpis.append({'code': metric['code'], 'kpi': metric.get('kpi'), 'category': metric.get('category'),
                             'kpi_type': metric.get('kpi_type'), 'operators': cells, 'peak': _peak(cells.values())})
        part[environment] = {'kinds': list(kinds.values()), 'operators': operators_part, 'categories': categories,
                             'kpis': sorted(kpis, key=lambda row: -row['peak'])}
    return part


def _area_points(result: dict[str, Any] | None, field: str, environments: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    """The points of each area, operator and environment; All Environments adds the environments measured there and scales
    them to the full maximum, as the Geographical Areas do."""
    areas: dict[str, dict[str, dict[str, Any]]] = {}
    for row in (result or {}).get('totals') or []:
        if not isinstance(row, dict) or row.get('category') != 'Overall' or row.get('environment') == COMBINED:
            continue
        area, operator, environment = row.get(field), row.get('operator'), row.get('environment')
        points, maximum = _number(row.get('weighted_points')), _number(row.get('max_points')) or 0.0
        if area in (None, '') or operator in (None, '') or environment not in environments or maximum <= 0:
            continue
        if not (_number(row.get('available_points')) or 0):
            continue
        cells = areas.setdefault(str(area), {}).setdefault(str(operator), {'points': {}, 'maximum': {}})
        cells['points'][environment], cells['maximum'][environment] = points or 0.0, maximum
    full = sum(_number((((result or {}).get('configuration') or {}).get('scope', {}).get('environments', {}).get(name) or {}).get('total_points')) or 0.0
               for name in environments)
    out: dict[str, dict[str, dict[str, float]]] = {}
    for area, operators in areas.items():
        for operator, cells in operators.items():
            reached = sum(cells['maximum'].values())
            combined = sum(cells['points'].values()) * (full / reached) if reached > 0 and full > 0 else None
            out.setdefault(area, {})[operator] = {**cells['points'], **({COMBINED: combined} if combined is not None else {})}
    return out


def _leader(cells: dict[str, dict[str, Any]], side: str) -> str | None:
    measured = {name: cell[side] for name, cell in cells.items() if cell.get(side) is not None}
    return max(measured, key=measured.get) if measured else None


def _area_part(results_before: dict[str, Any], results_after: dict[str, Any], environments: list[str],
               operators: list[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Each Region, Cluster and City of each environment: the points of each operator before and after and who leads, the
    areas that move most first."""
    part: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for level in AREA_LEVELS:
        before, after = results_before.get(level), results_after.get(level)
        if not before and not after:
            continue
        field = level.lower()
        points_before, points_after = _area_points(before, field, environments), _area_points(after, field, environments)
        names = sorted({*points_before, *points_after}, key=str.casefold)
        if not names:
            continue
        rows_by_environment: dict[str, list[dict[str, Any]]] = {}
        for environment in [COMBINED, *environments]:
            rows = []
            for area in names:
                cells = {}
                for name in operators:
                    cell = _shift(((points_before.get(area) or {}).get(name) or {}).get(environment),
                                  ((points_after.get(area) or {}).get(name) or {}).get(environment))
                    if cell['before'] is not None or cell['after'] is not None:
                        cells[name] = cell
                if cells:
                    leader_before, leader_after = _leader(cells, 'before'), _leader(cells, 'after')
                    rows.append({'area': area, 'operators': cells, 'peak': _peak(cells.values()),
                                 'leader_before': leader_before, 'leader_after': leader_after})
            rows_by_environment[environment] = sorted(rows, key=lambda row: (-row['peak'], row['area'].casefold()))
        part[level] = rows_by_environment
    return part


def _area_category_part(results_before: dict[str, Any], results_after: dict[str, Any], environments: list[str],
                        operators: list[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """The difference of each category in each area, for an operator: {level: {environment: [{area, categories: {category:
    {operator: difference}}}]}}. All Environments scales the environments measured in an area as the scoring of the area does."""
    part: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for level in AREA_LEVELS:
        before, after = results_before.get(level), results_after.get(level)
        if not before or not after:
            continue
        field = level.lower()
        points_before, points_after = _area_category_points(before, field, environments), _area_category_points(after, field, environments)
        by_environment: dict[str, list[dict[str, Any]]] = {}
        for environment in [COMBINED, *environments]:
            rows = []
            for area in sorted({*points_before, *points_after}, key=str.casefold):
                categories: dict[str, dict[str, float]] = {}
                for name in operators:
                    was = ((points_before.get(area) or {}).get(name) or {}).get(environment) or {}
                    now = ((points_after.get(area) or {}).get(name) or {}).get(environment) or {}
                    for category in {*was, *now}:
                        delta = now.get(category, 0.0) - was.get(category, 0.0)
                        categories.setdefault(category, {})[name] = _rounded(delta)
                if categories:
                    rows.append({'area': area, 'categories': categories})
            if rows:
                by_environment[environment] = rows
        if by_environment:
            part[level] = by_environment
    return part


def _area_category_points(result: dict[str, Any], field: str, environments: list[str]) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    """The points of each area, operator, environment and category of a result (All Environments as in _area_points)."""
    measured: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in result.get('totals') or []:
        if not isinstance(row, dict) or row.get('environment') == COMBINED or row.get('environment') not in environments:
            continue
        area, operator = row.get(field), row.get('operator')
        if area in (None, '') or operator in (None, ''):
            continue
        entry = measured.setdefault((str(area), str(operator), str(row['environment'])), {'points': {}, 'maximum': 0.0})
        if row.get('category') == 'Overall':
            if (_number(row.get('available_points')) or 0) > 0:
                entry['maximum'] = _number(row.get('max_points')) or 0.0
        else:
            entry['points'][str(row.get('category'))] = _number(row.get('weighted_points')) or 0.0
    full = sum(_number((((result.get('configuration') or {}).get('scope') or {}).get('environments', {}).get(name) or {}).get('total_points')) or 0.0
               for name in environments)
    reached: dict[tuple[str, str], float] = {}
    for (area, operator, _environment), entry in measured.items():
        reached[(area, operator)] = reached.get((area, operator), 0.0) + entry['maximum']
    out: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for (area, operator, environment), entry in measured.items():
        if entry['maximum'] <= 0:
            continue
        target = out.setdefault(area, {}).setdefault(operator, {})
        target[environment] = dict(entry['points'])
        factor = full / reached[(area, operator)] if reached[(area, operator)] > 0 and full > 0 else 1.0
        combined = target.setdefault(COMBINED, {})
        for category, points in entry['points'].items():
            combined[category] = combined.get(category, 0.0) + points * factor
    return out


def _campaign_change(label: str, value: str, before: dict[str, dict], after: dict[str, dict], names: list[str]) -> dict[str, Any]:
    """What the methodology changes on the tests of a campaign, per operator; a campaign without tests of a KPI of either
    methodology (that KPI did not exist yet) cannot be compared."""
    first, second = before.get(COMBINED) or {}, after.get(COMBINED) or {}
    missing = []
    for table in (first, second):
        for row in _kpi_rows(table):
            if (_number(row.get('max_points')) or 0) > 0 and not any(_points(row, name) is not None for name in table.get('operators') or []):
                missing.append(str(row.get('kpi') or row.get('kpi_code')))
    deltas = {}
    for name in names:
        was, now = _points(first.get('total'), name), _points(second.get('total'), name)
        if was is not None and now is not None:
            deltas[name] = _rounded(now - was)
    return {'campaign': value, 'label': label, 'operators': deltas, 'comparable': not missing and bool(deltas), 'missing': list(dict.fromkeys(missing))}


def _impact_part(results: dict[str, dict[str, Any]], baseline: str, aliases: list[str], operator_groups: list[dict],
                 vendor_groups: list[dict]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The panels of one scoring from the results of its calculations, and the KPI rows and score tables each methodology gives the
    maps (those of the whole country, with which the map is drawn)."""
    before_results, after_results = results['before'], results['after']
    configuration_before = before_results['Operator']['configuration']
    configuration_after = after_results['Operator']['configuration']
    before = _views(before_results['Operator'], baseline, aliases, operator_groups, vendor_groups)
    after = _views(after_results['Operator'], baseline, aliases, operator_groups, vendor_groups)
    active = _active_environments(configuration_after, configuration_before)
    measured = [name for name in active if name in before or name in after]
    environments = [COMBINED, *measured] if COMBINED in before or COMBINED in after else measured
    operators = _operators(before, after)
    names = [item['operator'] for item in operators]
    reference = next((item['operator'] for item in operators if item['is_reference']), baseline)
    pairs = _kpi_pairs(configuration_before.get('metrics') or [], configuration_after.get('metrics') or [])
    changes = methodology_changes(configuration_before, configuration_after)
    part = {
        'operators': operators, 'reference': reference,
        'environments': [{'name': name, 'label': _environment_labels(configuration_after, configuration_before).get(name, name)} for name in environments],
        'changes': changes,
        'scoring': _scoring_part(before, after, environments, names),
        'categories': _category_part(before, after, environments, names),
        'kpis': _kpi_part(pairs, changes, before, after, environments, names),
        'areas': _area_part(before_results, after_results, measured, names),
        'area_categories': _area_category_part(before_results, after_results, measured, names),
        'gap': _gap_part(pairs, before, after, environments, names, reference),
        'points_lost': _points_lost_part(pairs, before, after, configuration_before, configuration_after, environments, names),
    }
    part['competition'] = competition_part(part['scoring'], environments, names)
    part['drivers'] = drivers_part(part['kpis'], environments, names)
    part['exposure'] = exposure_part(part['kpis'], environments, names)
    campaigns = [{'campaign': results['tests']['value'], 'label': results['tests']['label'], 'current': True, 'comparable': True, 'missing': [],
                  'operators': {name: cell['delta'] for name, cell in ((part['scoring'].get(COMBINED) or {}).get('operators') or {}).items() if cell.get('delta') is not None}}]
    for other in results.get('others') or []:
        campaigns.append(_campaign_change(other['label'], other['value'], _views(other['before'], baseline, aliases, operator_groups, vendor_groups),
                                          _views(other['after'], baseline, aliases, operator_groups, vendor_groups), names))
    part['stability'] = stability_part(campaigns, names)
    country_before, country_after = before_results.get('Country'), after_results.get('Country')
    sides = {'before_rows': (country_before or before_results['Operator']).get('scoring') or [],
             'after_rows': (country_after or after_results['Operator']).get('scoring') or [],
             'before_tables': _views(country_before, baseline, aliases, operator_groups, vendor_groups) if country_before else before,
             'after_tables': _views(country_after, baseline, aliases, operator_groups, vendor_groups) if country_after else after}
    return part, sides


def _finish_part(part: dict[str, Any], maps: dict[str, Any] | None, scoring: str) -> None:
    """Add to the panels of a scoring what comes from the maps: the serving cells and, with all of it, the conclusions."""
    part['serving'] = ((maps or {}).get('serving') or {}).get(scoring) or {}
    environment = COMBINED if COMBINED in part['scoring'] else next(iter(part['scoring']), COMBINED)
    available = [name for name in ('City', 'Region', 'Cluster') if (((maps or {}).get('series') or {}).get(scoring) or {}).get(name)]
    measure = 'national' if available else 'own'
    field = (available or list(part['areas']) or [None])[0]
    where = impact_map(maps, part, scoring, field, environment, measure)['analysis'] if field else None
    part['conclusions'] = conclusions(part, {item['operator']: item['label'] for item in part['operators']}, where)


# ---------------------------------------------------------------------------------------------------------------------
# Preparing and calculating a comparison
# ---------------------------------------------------------------------------------------------------------------------

def _prepare_run(repository: Any, saved_filter: dict[str, Any], nr_mode: str, profile: dict[str, Any], entry: dict[str, Any],
                 baseline: str, cache: dict[Any, Any]) -> dict[str, Any]:
    """One calculation of the comparison: the tests of a campaign, within the scope of the Saved Filter, with a methodology."""
    wanted = {campaign_identity(value) for value in entry['spellings']}
    # The CDRs of the campaign the Saved Filter uses, else those the campaign uses by itself.
    own = [dataset_id for dataset_id, campaigns in _read_campaigns(repository, [int(value) for value in saved_filter.get('dataset_ids') or []]).items()
           if any(campaign_identity(value) in wanted for value in campaigns)]
    dataset_ids = own or auto_scoring_cdr_ids(repository, nr_mode, list(entry['spellings']))
    if not dataset_ids:
        raise ValueError(f"The campaign {entry['label']} has no Data, Voice and Speech CDRs of {nr_mode_label(nr_mode)}.")
    filters = {**(saved_filter.get('context_filters') or {}), 'Campaign': list(entry['spellings'])}
    prepared = _prepare_saved_filter(repository, dataset_ids, ['Operator'], nr_mode, baseline_operator=baseline,
                                     context_filters=filters, scoring_profile_id=profile['id'], cache=cache)
    snapshot = prepared['snapshot']
    return {'profile_id': profile['id'], 'profile_name': profile['name'], 'campaign': entry['value'], 'campaign_label': entry['label'],
            'nr_mode': prepared['nr_mode'], 'dataset_ids': prepared['dataset_ids'], 'result_key': prepared['result_key'],
            'source_fingerprint': prepared['source_fingerprint'], 'configuration': snapshot['configuration'],
            'filters': snapshot['resolved_context_filters'], 'baseline_operator': prepared['baseline_operator'],
            'baseline_aliases': snapshot['baseline_aliases'], 'operator_mappings': snapshot['operator_mappings']}


def prepare_impact(repository: Any, saved_filter: dict[str, Any], raw_selection: Any = None) -> dict[str, Any]:
    """What a comparison calculates and its key: the same tests with each methodology and, to see whether the effect is stable, the
    tests of the other campaigns with both."""
    options = impact_options(repository, saved_filter)
    selection = normalize_selection(raw_selection, options)
    profiles = repository.get_scoring_profiles()
    by_id = {profile['id']: profile for profile in profiles['profiles']}
    entries = {entry['value']: entry for entry in options['campaigns'][selection['nr_mode']]}
    baseline = str(saved_filter.get('baseline_operator') or DEFAULT_BASELINE_OPERATOR)
    notes = []
    if baseline == SAME_OPERATOR_NSA:
        # Same operator in NSA compares both NR Modes, and the impact is of one NR Mode.
        baseline = DEFAULT_BASELINE_OPERATOR
        notes.append(f'The GAP reference is {baseline}: Same operator in NSA compares both NR Modes, and this comparison is of one of them.')
    cache: dict[Any, Any] = {}
    sources_of = {}
    if selection['mode'] == 'campaigns':
        first, second = entries[selection['campaign_a']], entries[selection['campaign_b']]
        profile_before, profile_after = methodology_for(profiles, first['value']), methodology_for(profiles, second['value'])
        tests = second
        sources_of = {'before': first['label'], 'after': second['label']}
    else:
        profile_before, profile_after = by_id[selection['methodology_a']], by_id[selection['methodology_b']]
        tests = entries[selection['campaign']]
    nr_mode = selection['nr_mode']
    runs = {'before': _prepare_run(repository, saved_filter, nr_mode, profile_before, tests, baseline, cache)}
    runs['after'] = (runs['before'] if profile_before['id'] == profile_after['id'] else
                     _prepare_run(repository, saved_filter, nr_mode, profile_after, tests, baseline, cache))
    others = []
    if runs['after'] is not runs['before']:
        for entry in [item for item in options['campaigns'][nr_mode] if item['value'] != tests['value'] and not item['flex']][:OTHER_CAMPAIGNS]:
            try:
                others.append({'value': entry['value'], 'label': entry['label'],
                               'before': _prepare_run(repository, saved_filter, nr_mode, profile_before, entry, baseline, cache),
                               'after': _prepare_run(repository, saved_filter, nr_mode, profile_after, entry, baseline, cache)})
            except ValueError:  # (The filters leave nothing of that campaign: the same change is not tried on it.)
                continue
    postal = postal_areas.wanted(saved_filter) or bool(postal_areas.list_postal_layers(repository))
    key = scoring_cache.key_of({
        'kind': CACHE_KIND, 'code': _code_version(), 'selection': selection,
        'runs': {name: run['result_key'] for name, run in runs.items()},
        'others': [[item['before']['result_key'], item['after']['result_key']] for item in others],
        'postal': postal_areas.postal_version(repository, postal_areas.chosen_map(saved_filter)) if postal else '',
        'operator_groups': repository.list_operator_mapping_groups(), 'vendor_groups': repository.list_vendor_mapping_groups(),
    })
    return {'key': key, 'selection': selection, 'runs': runs, 'others': others, 'notes': notes, 'methodology_of': sources_of,
            'postal': postal, 'postal_map': postal_areas.chosen_map(saved_filter), 'tests': {'value': tests['value'], 'label': tests['label']},
            'saved_filter_id': saved_filter.get('id'), 'saved_filter_name': saved_filter.get('name') or ''}


class _CampaignRows:
    """The rows of the CDRs of a campaign, read once for the calculations of its methodologies."""

    def __init__(self, repository: Any, report: Callable[[str], None]) -> None:
        self.repository, self.report = repository, report
        self.campaign: str | None = None
        self.frames: dict[str, dict[str, Any]] = {}

    def read(self, run: dict[str, Any], filters: dict[str, list[str]]) -> dict[str, Any]:
        if run['campaign'] != self.campaign:
            self.campaign, self.frames = run['campaign'], {}
        key = json.dumps(filters, sort_keys=True, default=str)
        if key not in self.frames:
            self.report(f"Reading the CDR rows of {run['campaign_label']}")
            sources, _campaigns, _fingerprint = _source_snapshot(self.repository, run['dataset_ids'], expected_nr_mode=run['nr_mode'])
            for source in sources:
                source['levels'] = ['Operator', *AREA_LEVELS]
            self.frames[key] = _load_source_frames(self.repository, sources, lambda *_args: None, engine.load_input_columns, filters)
        return self.frames[key]


def _result_of(repository: Any, run: dict[str, Any], levels: list[str], filters: dict[str, list[str]], rows: _CampaignRows,
               vendor_operators: Iterable[str]) -> dict[str, Any]:
    """The scoring of a run split by ``levels``: from the Scoring History when it holds it, else from the rows of the CDRs."""
    options = {'baseline_operator': run['baseline_operator'], 'configuration': run['configuration'],
               'baseline_aliases': run['baseline_aliases'], 'operator_mappings': run['operator_mappings']}
    if not history_gap(repository, run['dataset_ids'], levels, run['configuration'], filters):
        try:
            result = calculate_scoring_from_history(repository, run['dataset_ids'], levels, context_filters=filters,
                                                    vendor_operators=vendor_operators, **options)
            result.pop('points_loss', None)
            return result
        except HistoryUnavailable:
            pass
    return engine.calculate_scoring(rows.read(run, filters), levels, with_points_loss=False, **options)


def _draw_maps(repository: Any, prepared: dict[str, Any], report: Callable[[str], None]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The Points Lost Map of the tests of the whole country with each methodology, as a Saved Filter draws it (in processes of their
    own, kept for the next comparison or Saved Filter with the same CDRs and methodology)."""
    documents = []
    for name in ('before', 'after'):
        run = prepared['runs'][name]
        job = {'id': prepared.get('saved_filter_id'), 'levels': ['Operator'], 'nr_mode': run['nr_mode'], 'baseline_operator': run['baseline_operator'],
               'baseline_aliases': run['baseline_aliases'], 'operator_mappings': run['operator_mappings'],
               'area_summary': {'postal_codes': True, 'postal_map': prepared['postal_map']} if prepared['postal'] else None}
        sources, _campaigns, _fingerprint = _source_snapshot(repository, run['dataset_ids'], expected_nr_mode=run['nr_mode'])

        def step(_value: float, detail: str, profile: str = run['profile_name']) -> None:
            report(f'Points Lost Map with {profile}: {detail}')
        document = _points_loss_of(repository, job, [dict(source) for source in sources], run['configuration'],
                                   whole_country_filters(run['filters']), engine, step)
        if not isinstance(document, dict) or not document.get('shares'):
            raise ValueError('The tests have no positions to place on a map.')
        documents.append(document)
    _attach_mapping_boundaries(repository, prepared['runs']['after']['dataset_ids'], {'points_loss': documents[1]})
    return documents[0], documents[1]


def calculate_impact(repository: Any, prepared: dict[str, Any], progress: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    """Score the tests with both methodologies and build the panels of each scoring they have. The maps go in ``maps`` (run_impact
    keeps them apart, they are read by area)."""
    report = progress or (lambda _progress, _message: None)
    runs = prepared['runs']
    summary = {'version': 2, 'key': prepared['key'], 'selection': prepared['selection'], 'before': _run_summary(runs['before']),
               'after': _run_summary(runs['after']), 'methodology_of': prepared['methodology_of'], 'nr_mode': runs['before']['nr_mode'],
               'notes': prepared['notes']}
    if runs['after'] is runs['before']:
        # Both campaigns are scored with the same methodology: it changes nothing.
        return {**summary, 'same_methodology': True, 'warnings': [], 'scorings': {}, 'maps_error': ''}
    current = 5
    rows = _CampaignRows(repository, lambda message: report(current, message))
    plan = [(name, level) for name in ('before', 'after') for level in ('Operator', *AREA_LEVELS)]
    area_filtered = has_area_filters(runs['before']['filters'])
    if area_filtered:
        plan.extend((name, 'Country') for name in ('before', 'after'))
    results: dict[str, dict[str, Any]] = {'before': {}, 'after': {}}
    catalogues = repository.cdr_catalogues_by_dataset(sorted({value for run in runs.values() for value in run['dataset_ids']}))
    vendor_operators = scoring_vendor_operators(catalogues, repository.list_operator_mapping_groups())
    for index, (name, level) in enumerate(plan):
        run = runs[name]
        current = 5 + round(index / len(plan) * 45)
        report(current, f"Scoring {run['campaign_label']} with {run['profile_name']}" + (f' per {level}' if level not in ('Operator', 'Country') else ''))
        levels = ['Operator'] if level in ('Operator', 'Country') else ['Operator', level]
        filters = run['filters'] if level == 'Operator' else whole_country_filters(run['filters'])
        try:
            results[name][level] = _result_of(repository, run, levels, filters, rows, vendor_operators)
        except ValueError:
            if level == 'Operator':
                raise
            # (The areas are optional, as in the Geographical Areas: a CDR without them leaves them out.)
            results[name][level] = None
    rows.frames = {}
    # The maps, with their own processes.
    current = 50
    maps_error = ''
    documents = None
    try:
        documents = _draw_maps(repository, prepared, lambda message: report(current, message))
    except Exception as exc:  # The scores stay; only the maps are missing, and the tab says why.
        maps_error = str(exc) or type(exc).__name__
    # The same change on the other campaigns.
    others = []
    for index, other in enumerate(prepared['others']):
        current = 72 + round(index / max(1, len(prepared['others'])) * 20)
        report(current, f"Trying the change on the tests of {other['label']}")
        try:
            entry = {'value': other['value'], 'label': other['label']}
            for name in ('before', 'after'):
                entry[name] = _result_of(repository, other[name], ['Operator'], other[name]['filters'], rows, vendor_operators)
            others.append(entry)
        except ValueError:
            continue
    rows.frames = {}
    report(94, 'Comparing the results')
    operator_groups = repository.list_operator_mapping_groups()
    vendor_groups = repository.list_vendor_mapping_groups()
    run = runs['before']
    baseline, aliases = run['baseline_operator'], run['baseline_aliases']
    results = {**results, 'others': others, 'tests': prepared['tests']}
    part, sides = _impact_part(results, baseline, aliases, operator_groups, vendor_groups)
    scorings = {BEST_NETWORK_SCORING: part}
    all_sides = {BEST_NETWORK_SCORING: sides}
    reliable = _most_reliable(results, baseline, run['configuration'])
    if reliable is not None:
        scorings[MOST_RELIABLE_SCORING], all_sides[MOST_RELIABLE_SCORING] = _impact_part(reliable, baseline, aliases, operator_groups, vendor_groups)
    maps = None
    if documents is not None:
        try:
            report(96, 'Comparing the maps')
            maps = build_maps(documents[0], documents[1], all_sides)
        except Exception as exc:  # (As above: only the maps are missing.)
            maps_error = str(exc) or type(exc).__name__
    for scoring, item in scorings.items():
        _finish_part(item, maps, scoring)
    warnings = [warning for name in ('before', 'after') for warning in (results[name].get('Operator') or {}).get('warnings') or []]
    if maps is not None:
        maps.pop('serving', None)
    return {**summary, 'same_methodology': False, 'warnings': list(dict.fromkeys(warnings)), 'scorings': scorings, 'maps_error': maps_error,
            'maps': maps}


def _most_reliable(results: dict[str, Any], baseline: str, configuration: dict[str, Any]) -> dict[str, Any] | None:
    """The same calculations in the Most Reliable scoring, when both methodologies have it."""
    reliable: dict[str, Any] = {'tests': results['tests']}
    for name in ('before', 'after'):
        converted = {level: (engine.most_reliable_result(result, baseline, result.get('configuration') or configuration) if result else None)
                     for level, result in results[name].items()}
        if converted.get('Operator') is None:
            return None
        reliable[name] = converted
    others = []
    for other in results.get('others') or []:
        before = engine.most_reliable_result(other['before'], baseline, other['before'].get('configuration') or configuration)
        after = engine.most_reliable_result(other['after'], baseline, other['after'].get('configuration') or configuration)
        if before is not None and after is not None:
            others.append({**other, 'before': before, 'after': after})
    reliable['others'] = others
    return reliable


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {'profile_id': run['profile_id'], 'profile_name': run['profile_name'], 'campaign': run['campaign'],
            'campaign_label': run['campaign_label'], 'datasets': len(run['dataset_ids'])}


# ---------------------------------------------------------------------------------------------------------------------
# The calculation in the background
# ---------------------------------------------------------------------------------------------------------------------

def _job_key(repository: Any, key: str) -> tuple[str, str]:
    return str(getattr(repository, 'db_path', '')), key


def impact_state(repository: Any, prepared: dict[str, Any]) -> dict[str, Any] | None:
    """The state of a comparison: completed with its panels, waiting or being calculated, failed, or None if it never ran."""
    return state_of(repository, prepared['key'])


def state_of(repository: Any, key: str) -> dict[str, Any] | None:
    """The state of a comparison by its key (see impact_state)."""
    with _guard:
        job = _jobs.get(_job_key(repository, key))
        if job is not None and job['status'] in ('queued', 'processing', 'failed'):
            return {'key': key, **{name: job[name] for name in ('status', 'progress', 'message', 'error')}}
    impact = scoring_cache.read(repository, CACHE_KIND, key) or (job or {}).get('impact')
    return {'key': key, 'status': 'completed', 'progress': 100, 'message': '', 'error': '', 'impact': impact} if impact else None


def read_impact(repository: Any, key: str) -> dict[str, Any] | None:
    """A comparison calculated before, by its key."""
    with _guard:
        job = _jobs.get(_job_key(repository, key))
    return scoring_cache.read(repository, CACHE_KIND, key) or (job or {}).get('impact')


def read_maps(repository: Any, key: str) -> dict[str, Any] | None:
    """The maps of a comparison calculated before, by its key."""
    return scoring_cache.read(repository, MAPS_CACHE_KIND, key)


def queue_impact(repository: Any, prepared: dict[str, Any], submit: Callable[..., Any], username: str) -> bool:
    """Queue the calculation of a comparison unless it is on its way; whether it was queued."""
    job_key = _job_key(repository, prepared['key'])
    with _guard:
        job = _jobs.get(job_key)
        if job is not None and job['status'] in ('queued', 'processing'):
            return False
        _jobs[job_key] = {'status': 'queued', 'progress': 0, 'message': 'Waiting for the work of the workspace before it', 'error': ''}
        for old in list(_jobs)[:-KEPT_JOBS]:
            if _jobs[old]['status'] not in ('queued', 'processing'):
                _jobs.pop(old)
    submit(run_impact, repository, prepared, username)
    return True


def _details(prepared: dict[str, Any]) -> dict[str, Any]:
    """What App Events records of a comparison."""
    runs = prepared['runs']
    return {'saved_filter_id': prepared.get('saved_filter_id'), 'name': prepared.get('saved_filter_name'),
            **prepared['selection'], 'before': runs['before']['profile_name'], 'after': runs['after']['profile_name'],
            'campaign': runs['before']['campaign'], 'datasets': runs['before']['dataset_ids']}


def run_impact(repository: Any, prepared: dict[str, Any], username: str) -> None:
    """Calculate a comparison and keep it, or its error, with an App Event."""
    job_key = _job_key(repository, prepared['key'])

    def update(progress: int, message: str) -> None:
        with _guard:
            job = _jobs.get(job_key)
            if job is not None:
                job.update(status='processing', progress=int(progress), message=message)
    try:
        update(2, 'Starting')
        impact = calculate_impact(repository, prepared, update)
        maps = impact.pop('maps', None)
        if maps is not None:
            scoring_cache.write(repository, MAPS_CACHE_KIND, prepared['key'], maps)
        scoring_cache.write(repository, CACHE_KIND, prepared['key'], impact)
    except Exception as exc:  # The tab shows why, and the user can try again.
        with _guard:
            _jobs[job_key] = {'status': 'failed', 'progress': 0, 'message': '', 'error': str(exc) or type(exc).__name__}
        repository.try_add_log(username, 'scoring_methodology_impact_failed', json.dumps({**_details(prepared), 'error': str(exc)}, default=str))
        return
    with _guard:
        _jobs[job_key] = {'status': 'completed', 'progress': 100, 'message': '', 'error': '', 'impact': impact}
    repository.try_add_log(username, 'scoring_methodology_impact_calculated', json.dumps(_details(prepared), default=str))
