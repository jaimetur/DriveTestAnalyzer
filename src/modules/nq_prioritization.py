"""NQ Prioritization: which Non-Qualified Calls the teams analyse first.

Every Non-Qualified Call (the latest version of each call, as the calls table lists it) gets three values:

- **Scoring Impact**: the points of the scoring its failure loses. For every KPI of the methodology of its campaign that
  counts tests (the ratios: call success, transfer success, POLQA below 1.6, throughput above a threshold...), the
  points the operator loses in that KPI in the environment of the call (Drive - City, Drive - Connecting Roads...) are
  shared equally among the tests that miss it, as the Points Lost Map shares them (see ``scoring_points_loss``); a call
  holds the share of every KPI it misses. The scoring of each campaign and NR Mode is calculated from the Scoring
  History over the CDRs the combined CDR tables include, with the methodology that applies to the campaign. The level is
  a Pareto within the campaign, operator and service of the call: the calls that hold the first share of the points lost
  (50 % by default) are High, those up to the second share (80 %) Medium and the others Low.
- **Repetition**: how many Non-Qualified Calls of the same operator failed at the same place in the quarter of the call
  and the quarters before it (one by default), whatever their service and NR Mode. The place is the site of the cell
  where the call ended (its eNB or gNB in the cell mappings of the workspace), else the site that served its start
  (serving-cell Vendor Mapping), else the eNB or gNB of its last cell, else a spot of about 100 m around where it
  started.
- **Prioritization**: ordered rules on Service, NR Mode, Operator, Region and City. The first rule whose conditions a
  call meets decides: Prioritized when the call meets its criterion (every call, repeated or high impact...), else Track
  only. The Priority of the open calls is filled with the priority the rule gives while nobody has chosen another one
  by hand.

The values are calculated in the background when the server is idle, after the indexing of the calls and the Scoring
History, whenever what they depend on changes; the rules apply again as soon as they are saved.

This module reads the NQ tables of ``non_qualified_calls`` (imported where it is needed, as that module imports this one).
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import re
import time
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Iterable

from src.modules import nq_catalog
from src.modules.nq_catalog import IMPACT_HIGH, NO_RULE, PRIORITIZED, TRACK_ONLY

PRIORITY_TABLE = 'nq_call_priority'
PRIORITY_CAMPAIGNS_TABLE = 'nq_priority_campaigns'
# Database Management titles of the tables.
TABLE_TITLES = {PRIORITY_TABLE: 'NQ Call Priority', PRIORITY_CAMPAIGNS_TABLE: 'NQ Priority Campaigns'}
SETTINGS_STATE_KEY = 'nq_prioritization_settings'
# What the last calculation depended on, and that of a calculation that failed (tried again when it changes).
FINGERPRINT_STATE_KEY = 'nq_prioritization_fingerprint'
FAILED_STATE_KEY = 'nq_prioritization_failed'
SUMMARY_STATE_KEY = 'nq_prioritization_summary'
# Bumped when the calculation changes: every value is calculated again.
IMPACT_VERSION = 1
# The scoring of every campaign is split by campaign and operator, as the points of the scoring are national.
LEVELS = ('Campaign', 'Operator')
SERVICES = ('voice', 'speech', 'data')
NR_MODES = ('NSA', 'SA')
CRITERIA = {
    'all': 'Every call', 'repeated_or_high': 'Repeated or high impact', 'repeated_and_high': 'Repeated and high impact',
    'repeated': 'Repeated issues only', 'high': 'High impact only', 'track': 'Track only',
}
MAX_RULES = 30
MAX_RULE_VALUES = 60
# The states of the scoring impact of a call and of a campaign.
SCORED, EXCLUDED, PENDING, NOT_SCORED = 'scored', 'excluded', 'pending', 'not_scored'
LEVEL_OF_STATE = {EXCLUDED: nq_catalog.IMPACT_EXCLUDED, PENDING: nq_catalog.IMPACT_NOT_SCORED,
                  NOT_SCORED: nq_catalog.IMPACT_NOT_SCORED}
PRIORITY_FIELD = 'priority'
# The priority a call keeps once someone changed or cleared the one the rules gave it.
BY_HAND = '@by-hand'
SYSTEM_USER = 'system'
MAX_KPIS_TEXT = 3
METERS_PER_DEGREE = 111_320.0

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {PRIORITY_TABLE} (
    call_key TEXT PRIMARY KEY,
    campaign_key TEXT NOT NULL DEFAULT '',
    impact_state TEXT NOT NULL DEFAULT '',
    impact_points REAL,
    impact_level TEXT NOT NULL DEFAULT '',
    impact_kpis TEXT NOT NULL DEFAULT '',
    impact_json TEXT NOT NULL DEFAULT '[]',
    place_key TEXT NOT NULL DEFAULT '',
    place_label TEXT NOT NULL DEFAULT '',
    repetitions INTEGER,
    repeated_campaigns INTEGER,
    repeated TEXT NOT NULL DEFAULT '',
    prioritization TEXT NOT NULL DEFAULT '',
    priority_rule TEXT NOT NULL DEFAULT '',
    suggested_priority TEXT NOT NULL DEFAULT '',
    priority_filled TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS {PRIORITY_CAMPAIGNS_TABLE} (
    campaign_key TEXT PRIMARY KEY,
    nr_mode TEXT NOT NULL DEFAULT '',
    campaign TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    methodology TEXT NOT NULL DEFAULT '',
    calls INTEGER NOT NULL DEFAULT 0,
    points REAL NOT NULL DEFAULT 0,
    calculated_at TEXT NOT NULL DEFAULT ''
);
"""


# ---------------------------------------------------------------------------
# Settings: the levels of the impact, the repetitions and the rules
# ---------------------------------------------------------------------------
def default_rules() -> list[dict[str, Any]]:
    """SA before NSA and Voice before Data, as the BNP prioritization asks: every Voice call, and the Data calls with a
    repeated issue or a high impact on the scoring (the others are tracked)."""
    def rule(name: str, services: list[str], nr_mode: str, criterion: str, priority: str) -> dict[str, Any]:
        return {'name': name, 'services': services, 'nr_modes': [nr_mode], 'operators': [], 'regions': [], 'cities': [],
                'criterion': criterion, 'priority': priority, 'track_priority': 'P5'}
    return [rule('SA Voice', ['voice', 'speech'], 'SA', 'all', 'P1'),
            rule('SA Data', ['data'], 'SA', 'repeated_or_high', 'P2'),
            rule('NSA Voice', ['voice', 'speech'], 'NSA', 'all', 'P3'),
            rule('NSA Data', ['data'], 'NSA', 'repeated_or_high', 'P4')]


def default_settings() -> dict[str, Any]:
    return {'high_share': 50, 'medium_share': 80, 'min_calls': 2, 'previous_quarters': 1, 'spot_meters': 100,
            'capacity': 20, 'fill_priority': True, 'rules': default_rules()}


def _whole(value: Any, default: int, low: int, high: int, label: str, strict: bool) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        if strict and value not in (None, ''):
            raise ValueError(f'{label} is a number.') from None
        return default
    if not math.isfinite(number) or not low <= number <= high:
        if strict:
            raise ValueError(f'{label} goes from {low} to {high}.')
        return min(high, max(low, int(number))) if math.isfinite(number) else default
    return int(round(number))


def _values(items: Any, allowed: Iterable[str] | None = None) -> list[str]:
    """The values of a condition of a rule, trimmed and once each (in their spelling of ``allowed`` when given)."""
    items = items if isinstance(items, list) else []
    known = {value.casefold(): value for value in allowed} if allowed is not None else None
    values: dict[str, str] = {}
    for item in items:
        text = re.sub(r'\s+', ' ', str(item if item is not None else '')).strip()[:80]
        if not text:
            continue
        if known is not None:
            if text.casefold() not in known:
                continue
            text = known[text.casefold()]
        values.setdefault(text.casefold(), text)
    return list(values.values())[:MAX_RULE_VALUES]


def normalize_settings(value: Any, *, strict: bool = False) -> dict[str, Any]:
    """Valid settings (the defaults for what is missing); ``strict`` refuses invalid values instead of fixing them."""
    value = value if isinstance(value, dict) else {}
    defaults = default_settings()
    high = _whole(value.get('high_share', defaults['high_share']), defaults['high_share'], 5, 95, 'The High share', strict)
    medium = _whole(value.get('medium_share', defaults['medium_share']), defaults['medium_share'], 5, 100,
                    'The Medium share', strict)
    if medium <= high:
        if strict:
            raise ValueError('The Medium share must be above the High share.')
        medium = min(100, high + 1)
    rules = value.get('rules') if isinstance(value.get('rules'), list) else (defaults['rules'] if 'rules' not in value else [])
    if strict and len(rules) > MAX_RULES:
        raise ValueError(f'Keep at most {MAX_RULES} Prioritization Rules.')
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for rule in rules[:MAX_RULES]:
        if not isinstance(rule, dict):
            if strict:
                raise ValueError('A Prioritization Rule is invalid.')
            continue
        name = re.sub(r'\s+', ' ', str(rule.get('name') or '')).strip()[:60]
        if not name:
            if strict:
                raise ValueError('Every Prioritization Rule needs a name.')
            continue
        if name.casefold() in names:
            if strict:
                raise ValueError(f'The Prioritization Rule "{name}" is repeated.')
            continue
        names.add(name.casefold())
        criterion = str(rule.get('criterion') or 'all')
        if criterion not in CRITERIA:
            if strict:
                raise ValueError(f'Choose the calls the rule "{name}" prioritizes.')
            criterion = 'all'
        normalized.append({
            'name': name, 'services': _values(rule.get('services'), SERVICES), 'nr_modes': _values(rule.get('nr_modes'), NR_MODES),
            'operators': _values(rule.get('operators')), 'regions': _values(rule.get('regions')), 'cities': _values(rule.get('cities')),
            'criterion': criterion, 'priority': str(rule.get('priority') or '').strip()[:40],
            'track_priority': str(rule.get('track_priority') or '').strip()[:40],
        })
    return {
        'high_share': high, 'medium_share': medium,
        'min_calls': _whole(value.get('min_calls', defaults['min_calls']), defaults['min_calls'], 2, 50,
                            'The calls of a repeated issue', strict),
        'previous_quarters': _whole(value.get('previous_quarters', defaults['previous_quarters']), defaults['previous_quarters'],
                                    0, 8, 'The previous quarters', strict),
        'spot_meters': _whole(value.get('spot_meters', defaults['spot_meters']), defaults['spot_meters'], 25, 2000,
                              'The size of a spot', strict),
        'capacity': _whole(value.get('capacity', defaults['capacity']), defaults['capacity'], 1, 500,
                           'The calls to analyse next', strict),
        'fill_priority': bool(value.get('fill_priority', defaults['fill_priority'])),
        'rules': normalized,
    }


def load_settings(repository: Any) -> dict[str, Any]:
    try:
        stored = json.loads(repository.get_workspace_state(SETTINGS_STATE_KEY) or 'null')
    except (TypeError, ValueError):
        stored = None
    return normalize_settings(stored) if isinstance(stored, dict) else default_settings()


def priority_options(repository: Any) -> list[str]:
    """The values of the Priority field the rules fill ([] when the workspace has no such list)."""
    from src.modules import non_qualified_calls as nq

    field = next((item for item in nq.list_fields(repository) if item['key'] == PRIORITY_FIELD), None)
    if field is None or field['source'] != 'user' or field['type'] != 'list':
        return []
    return [option['name'] for option in field['options']]


def rule_names(repository: Any) -> list[str]:
    """The names of the rules, the values of the Prioritization Rule field."""
    return [rule['name'] for rule in load_settings(repository)['rules']]


def save_settings(repository: Any, payload: Any, username: str) -> dict[str, Any]:
    """Save the settings and apply the rules again at once; the impact and the repetitions are calculated again in the
    background when their settings change."""
    settings = normalize_settings(payload, strict=True)
    options = {name.casefold(): name for name in priority_options(repository)}
    for rule in settings['rules']:
        for key in ('priority', 'track_priority'):
            if rule[key]:
                if options and rule[key].casefold() not in options:
                    raise ValueError(f'The priority {rule[key]} of the rule "{rule["name"]}" is not a value of the Priority field.')
                rule[key] = options.get(rule[key].casefold(), rule[key])
    before = load_settings(repository)
    repository.set_workspace_state(SETTINGS_STATE_KEY, json.dumps(settings, ensure_ascii=False))
    applied = apply_rules(repository, username, settings)
    if hasattr(repository, 'try_add_log'):
        repository.try_add_log(username, 'nq_prioritization_settings', json.dumps({
            'rules': [rule['name'] for rule in settings['rules']],
            'changed': sorted(key for key in settings if key != 'rules' and settings[key] != before.get(key)),
            'rules_changed': settings['rules'] != before.get('rules'), **applied}, ensure_ascii=False))
    return settings


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
def compile_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rules with their Operator, Region and City conditions ready to compare (patterns such as VF* or -Lebara)."""
    from src.modules.value_patterns import ValueSet
    return [{**rule, '_sets': {key: ValueSet(rule[key]) for key in ('operators', 'regions', 'cities') if rule[key]}} for rule in rules]


def rule_matches(rule: dict[str, Any], call: Any) -> bool:
    """Whether a call meets the conditions of a rule (of ``compile_rules``): an empty condition takes every value."""
    def value(key: str) -> str:
        try:
            return str(call[key] or '')
        except (KeyError, IndexError):
            return ''
    sets = rule.get('_sets') or {}
    return ((not rule['services'] or value('service') in rule['services'])
            and (not rule['nr_modes'] or value('nr_mode').upper() in rule['nr_modes'])
            and all(value(field) in sets[key] for key, field in (('operators', 'operator'), ('regions', 'region'),
                                                                   ('cities', 'city')) if key in sets))


def criterion_holds(criterion: str, repeated: bool, high: bool) -> bool:
    return {'all': True, 'repeated_or_high': repeated or high, 'repeated_and_high': repeated and high,
            'repeated': repeated, 'high': high, 'track': False}.get(criterion, False)


def decide(rules: list[dict[str, Any]], call: Any, repeated: bool, high: bool) -> tuple[str, str, str]:
    """(prioritization, rule, priority) of a call: the first rule (of ``compile_rules``) whose conditions it meets
    decides."""
    for rule in rules:
        if rule_matches(rule, call):
            if criterion_holds(rule['criterion'], repeated, high):
                return PRIORITIZED, rule['name'], rule['priority']
            return TRACK_ONLY, rule['name'], rule['track_priority']
    return NO_RULE, '', ''


# ---------------------------------------------------------------------------
# Scoring impact
# ---------------------------------------------------------------------------
def impact_levels(points: dict[str, float], high_share: float, medium_share: float) -> dict[str, str]:
    """High, Medium or Low for the calls of one campaign, operator and service: a Pareto of their points (calls with the
    same points share their level); No impact for the calls that lose no points."""
    total = sum(value for value in points.values() if value > 0)
    levels: dict[str, str] = {}
    before = 0.0
    by_value: dict[float, list[str]] = {}
    for key, value in points.items():
        by_value.setdefault(round(value, 6), []).append(key)
    for value in sorted(by_value, reverse=True):
        keys = by_value[value]
        if value <= 0 or total <= 0:
            level = nq_catalog.IMPACT_NONE
        else:
            share = before / total * 100
            level = IMPACT_HIGH if share < high_share else nq_catalog.IMPACT_MEDIUM if share < medium_share else nq_catalog.IMPACT_LOW
        levels.update({key: level for key in keys})
        before += max(0.0, value) * len(keys)
    return levels


def bad_tests(metric: dict[str, Any], value: float, count: int) -> int:
    """How many tests of a ratio KPI miss it, from its value and the tests it counts: those that fail its condition when
    higher is better (call success), those that meet it when lower is better (POLQA below 1.6)."""
    formula = str(metric['calculation']['formula'])
    scale = 100.0 if formula.startswith('100 * ') else 1.0
    share = max(0.0, min(1.0, float(value) / scale))
    missed = count * (1 - share) if metric['direction'] == 'higher_is_better' else count * share
    return int(round(missed))


def _text(value: Any) -> str:
    return '' if value is None or (isinstance(value, float) and math.isnan(value)) else str(value).strip()


def _nq_frame(repository: Any, dataset_id: int, kind: str, row_ids: list[int]):
    """The rows of some Non-Qualified Calls of a CDR with the scoring columns of its type under their canonical names
    (``__row`` is the row ID of the CDR)."""
    import pandas as pd

    from src.modules.column_names import resolve_column_name
    from src.modules.scoring import required_input_columns

    available = repository.list_dataset_row_columns(dataset_id)
    fields = required_input_columns(kind)
    resolved = {field: resolve_column_name(available, field) for field in fields}
    selected = list(dict.fromkeys(column for column in resolved.values() if column))
    table = repository.dataset_rows_table_name(dataset_id)
    rows: list[Any] = []
    with repository.connection() as connection:
        for start in range(0, len(row_ids), 500):
            chunk = row_ids[start:start + 500]
            columns = ', '.join(['rowid AS "__row"', *('"' + column.replace('"', '""') + '"' for column in selected)])
            rows.extend(connection.execute(
                f'SELECT {columns} FROM "{table}" WHERE rowid IN ({", ".join("?" for _ in chunk)})', chunk).fetchall())
    source = pd.DataFrame([tuple(row) for row in rows], columns=['__row', *selected])
    frame = pd.DataFrame({'__row': source['__row']} if len(source) else {'__row': []})
    for field in fields:
        column = resolved[field]
        frame[field] = source[column] if column is not None else pd.Series(float('nan'), index=source.index)
    for field in ('Operator', 'Campaign', 'G_Level_1', 'G_Level_2'):
        frame[field] = frame[field].map(_text) if field in frame else ''
    return frame


def _environments(frame, configuration: dict[str, Any]) -> list[str | None]:
    """The environment of each row, as the scoring matches it (the last one whose selectors it meets)."""
    environments = configuration['scope']['environments']
    found = []
    for level_1, level_2 in zip(frame['G_Level_1'], frame['G_Level_2']):
        matched = [name for name, context in environments.items()
                   if level_1 == context['source_filters']['G_Level_1']
                   and ('G_Level_2' not in context['source_filters'] or level_2 == context['source_filters']['G_Level_2'])]
        found.append(matched[-1] if matched else None)
    return found


def _losses(result: dict[str, Any], configuration: dict[str, Any], campaign: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    """For every operator, environment and KPI that counts tests of a campaign: the points it loses and the points each
    test that misses it holds."""
    from src.modules.cdr_auto_selection import campaign_identity
    from src.modules.scoring_points_loss import counts_tests

    identity = campaign_identity(campaign)
    metrics = {metric['code']: metric for metric in configuration['metrics']}
    losses = {}
    for row in result.get('scoring') or []:
        metric = metrics.get(row.get('kpi_code'))
        if metric is None or not counts_tests(metric) or campaign_identity(row.get('campaign')) != identity:
            continue
        if row.get('value') is None or row.get('weighted_points') is None or row.get('max_points') is None:
            continue
        lost = max(0.0, float(row['max_points']) - float(row['weighted_points']))
        missed = bad_tests(metric, row['value'], int(row.get('sample_count') or 0))
        if lost <= 0 or missed <= 0:
            continue
        losses[(str(row['operator'] or '').casefold(), str(row['environment']), metric['code'])] = {
            'lost': lost, 'tests': missed, 'each': lost / missed, 'kpi': str(row.get('kpi') or metric['kpi']),
            'category': str(row.get('category') or metric.get('category') or '')}
    return losses


def campaign_impact(repository: Any, nr_mode: str, campaign: str, rows: list[dict[str, Any]], profiles: dict[str, Any] | None,
                    operator_mappings: dict[str, str], excluded: Callable[[int, str], bool], kinds: dict[int, str]) -> dict[str, Any]:
    """The scoring impact of the Non-Qualified rows (``call_key``, ``dataset_id``, ``source_row_id``, ``join_id``) of
    one campaign and NR Mode: the state of the campaign and, per call, its points and the KPIs it loses them in."""
    from src.modules import scoring
    from src.modules.cdr_auto_selection import resolve_cdr_ids
    from src.modules.scoring_config import validate_scoring_configuration
    from src.modules.scoring_history import HistoryUnavailable, calculate_scoring_from_history, history_gap
    from src.modules.scoring_methodologies import methodology_for
    from src.modules.scoring_points_loss import counts_tests, test_weights

    def outcome(state: str, detail: str, methodology: str = '', calls: dict[str, Any] | None = None) -> dict[str, Any]:
        return {'state': state, 'detail': detail, 'methodology': methodology, 'calls': calls or {}}

    if not campaign:
        return outcome(NOT_SCORED, 'The calls have no campaign.')
    if not profiles:
        return outcome(NOT_SCORED, 'The workspace has no Scoring & GAP Analysis Methodology.')
    dataset_ids = resolve_cdr_ids(repository, nr_mode, [campaign])
    if not dataset_ids:
        return outcome(NOT_SCORED, 'No CDR of the campaign is in the combined CDR tables.')
    try:
        profile = methodology_for(profiles, campaign)
        configuration = validate_scoring_configuration(profile['configuration'])
    except (StopIteration, KeyError, ValueError) as error:
        return outcome(NOT_SCORED, f'The methodology of the campaign cannot be used: {error}')
    gap = history_gap(repository, dataset_ids, LEVELS, configuration, {})
    if gap:
        return outcome(PENDING, f'Waiting for the Scoring History: {gap}.', profile['name'])
    try:
        result = calculate_scoring_from_history(repository, dataset_ids, LEVELS, configuration=configuration,
                                                operator_mappings=operator_mappings)
    except (HistoryUnavailable, ValueError) as error:
        return outcome(PENDING, f'Waiting for the Scoring History: {error}', profile['name'])
    losses = _losses(result, configuration, campaign)
    mappings = {str(alias).strip().casefold(): str(name).strip() for alias, name in (operator_mappings or {}).items()
                if str(alias).strip() and str(name).strip()}
    calls: dict[str, dict[str, Any]] = {}
    by_dataset: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        calls.setdefault(row['call_key'], {'state': SCORED, 'points': 0.0, 'kpis': {}})
        if excluded(int(row['dataset_id']), row['join_id']):
            calls[row['call_key']]['state'] = EXCLUDED
            continue
        by_dataset.setdefault(int(row['dataset_id']), []).append(row)
    for dataset_id, items in by_dataset.items():
        kind = kinds.get(dataset_id, '')
        metrics = [metric for metric in configuration['metrics'] if metric['source_kind'] == kind and counts_tests(metric)]
        if not metrics:
            continue
        frame = _nq_frame(repository, dataset_id, kind, [int(item['source_row_id']) for item in items])
        if frame.empty:
            continue
        keys = {int(item['source_row_id']): item['call_key'] for item in items}
        environments = _environments(frame, configuration)
        operators = [mappings.get(name.casefold(), name).casefold() for name in frame['Operator']]
        for metric in metrics:
            try:
                weights = test_weights(frame, metric, {}, scoring._condition, scoring._filter)
            except (KeyError, ValueError, TypeError):
                continue
            for position in [index for index, weight in enumerate(weights.tolist()) if weight > 0]:
                loss = losses.get((operators[position], str(environments[position]), metric['code']))
                key = keys.get(int(frame['__row'].iat[position]))
                if loss is None or key is None or calls[key]['state'] == EXCLUDED:
                    continue
                entry = calls[key]['kpis'].setdefault((metric['code'], str(environments[position])), {
                    'code': metric['code'], 'kpi': loss['kpi'], 'category': loss['category'],
                    'environment': str(environments[position]), 'points': 0.0})
                entry['points'] += loss['each']
                calls[key]['points'] += loss['each']
    for call in calls.values():
        call['kpis'] = sorted(({**item, 'points': round(item['points'], 4)} for item in call['kpis'].values()),
                              key=lambda item: (-item['points'], item['code']))
        call['points'] = round(call['points'], 4)
    return outcome(SCORED, '', profile['name'], calls)


def kpi_label(item: dict[str, Any]) -> str:
    """A KPI with its category, as KPIs of several categories share a name (CALL SUCCESS RATIO [%] (WHATSAPP CALLS))."""
    return f"{item['kpi']} ({item['category']})" if item.get('category') else str(item['kpi'])


def kpis_text(kpis: list[dict[str, Any]]) -> str:
    """The KPIs a call loses its points in, the most first (CALL SUCCESS RATIO [%] (CLASSIC CALLS) · Drive - City 0.27)."""
    parts = [f"{kpi_label(item)} · {item['environment']} {item['points']:.2f}" for item in kpis[:MAX_KPIS_TEXT]]
    if len(kpis) > MAX_KPIS_TEXT:
        parts.append(f'+{len(kpis) - MAX_KPIS_TEXT} more')
    return '; '.join(parts)


# ---------------------------------------------------------------------------
# Repetition
# ---------------------------------------------------------------------------
def quarter_of(start_time: Any, campaign: Any = '') -> int | None:
    """The quarter of a call (year × 4 + quarter): from its start time, else from its campaign."""
    match = re.match(r'\s*(\d{4})-(\d{2})', str(start_time or ''))
    if match and 1 <= int(match.group(2)) <= 12:
        return int(match.group(1)) * 4 + (int(match.group(2)) - 1) // 3
    from src.modules.column_names import campaign_sort_key
    year, quarter, *_rest = campaign_sort_key(str(campaign or ''))
    return year * 4 + quarter - 1 if year > 0 and 1 <= quarter <= 4 else None


def spot_of(latitude: Any, longitude: Any, meters: float) -> tuple[str, str] | None:
    """The spot of about ``meters`` around a position: its key and label (the centre of the spot)."""
    try:
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(latitude) and math.isfinite(longitude)) or (latitude == 0 and longitude == 0):
        return None
    step = meters / METERS_PER_DEGREE
    row = round(latitude / step)
    centre = row * step
    step_east = meters / (METERS_PER_DEGREE * max(0.01, math.cos(math.radians(centre))))
    column = round(longitude / step_east)
    return f'spot:{meters:g}:{row}:{column}', f'Spot {centre:.4f}, {column * step_east:.4f}'


def place_of(call: dict[str, Any], node_details: Callable[[str, tuple[str, int]], dict[str, str] | None],
             spot_meters: float) -> tuple[str, str]:
    """Where a call failed, to compare it with the others (key and label): the site of the cell where it ended, else the
    site that served its start, else the eNB or gNB of its last cell, else the spot where it started."""
    from src.modules.non_qualified_calls import serving_node

    node = serving_node(call.get('cell_id'))
    details = node_details(str(call.get('operator') or ''), node) if node else None
    if details and details.get('site'):
        host = str(details.get('host') or '').strip()
        return f"site:{host.casefold()}|{details['site'].strip().casefold()}", f"Site {details['site'].strip()}" + (f' ({host})' if host else '')
    site = str(call.get('site_id') or '').strip()
    if site:
        host = str(call.get('host_network') or '').strip()
        return f'site:{host.casefold()}|{site.casefold()}', f'Site {site}' + (f' ({host})' if host else '')
    if node:
        return f'node:{node[0]} {node[1]}', f'{node[0]} {node[1]}'
    spot = spot_of(call.get('latitude'), call.get('longitude'), spot_meters)
    return spot if spot else ('', '')


def repetitions(calls: list[dict[str, Any]], previous_quarters: int) -> dict[str, tuple[int, int]]:
    """For every call with a place (``place_key``): the Non-Qualified Calls of its operator at the same place in its quarter
    and the ``previous_quarters`` before it (itself included), and their campaigns. Calls without a date count in every
    window of their place, and count every call of it."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for call in calls:
        if call.get('place_key'):
            groups.setdefault((str(call.get('operator') or '').casefold(), call['place_key']), []).append(call)
    found: dict[str, tuple[int, int]] = {}
    for members in groups.values():
        dated = sorted((call for call in members if call.get('quarter') is not None), key=lambda call: call['quarter'])
        quarters = [call['quarter'] for call in dated]
        undated = [call for call in members if call.get('quarter') is None]
        for call in members:
            if call.get('quarter') is None:
                window = members
            else:
                low = bisect.bisect_left(quarters, call['quarter'] - previous_quarters)
                high = bisect.bisect_right(quarters, call['quarter'])
                window = [*dated[low:high], *undated]
            found[call['call_key']] = (len(window), len({item.get('campaign_label') or '' for item in window}))
    return found


# ---------------------------------------------------------------------------
# The calculation
# ---------------------------------------------------------------------------
def ensure_tables(repository: Any) -> None:
    with repository.connection() as connection:
        connection.executescript(SCHEMA)


def fingerprint(repository: Any, settings: dict[str, Any] | None = None) -> str:
    """What the impact and the repetitions depend on: the calls and CDRs indexed, the Scoring History, the methodologies,
    the Operator Maps, the Excluded Calls, the cell mappings and the settings."""
    from src.modules import non_qualified_calls as nq
    from src.modules.repository import SCORING_CONFIGURATION_STATE_KEY

    settings = settings or load_settings(repository)
    with repository.connection() as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

        def rows(sql: str, table: str) -> list[tuple[Any, ...]]:
            return [tuple(row) for row in connection.execute(sql)] if table in tables else []

        history = rows('SELECT source_key, indexed_at FROM scoring_history_sources ORDER BY source_key', 'scoring_history_sources')
        lists = rows('SELECT id, enabled, content_hash, cdrs_json FROM scoring_exclusion_lists ORDER BY id', 'scoring_exclusion_lists')
        matches = rows('SELECT list_id, dataset_id, revision, keys_hash FROM scoring_exclusion_matches ORDER BY list_id, dataset_id',
                       'scoring_exclusion_matches')
    datasets = sorted((int(row['id']), str(row['dataset_kind'] or ''), str(row['status'] or ''), str(row['nr_mode'] or ''),
                       str(row['processed_at'] or ''), str(row['updated_at'] or '')) for row in repository.list_datasets())
    payload = [IMPACT_VERSION, {key: settings[key] for key in ('high_share', 'medium_share', 'min_calls', 'previous_quarters',
                                                               'spot_meters')},
               repository.get_workspace_state(nq.LATEST_STATE_KEY), history, lists, matches, datasets,
               repository.get_workspace_state(SCORING_CONFIGURATION_STATE_KEY), repository.list_operator_mappings()]
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _latest_calls(repository: Any) -> list[dict[str, Any]]:
    from src.modules import non_qualified_calls as nq

    with repository.connection() as connection:
        return [dict(row) for row in connection.execute(
            f'SELECT call_key, dataset_id, source_row_id, service, nr_mode, campaign, operator, region, city, site_id, '
            f"host_network, cell_id, latitude, longitude, start_time, join_id FROM {nq.NQ_CALL_LATEST_TABLE} "
            "WHERE version_state <> 'qualified'")]


def _call_rows(repository: Any) -> list[dict[str, Any]]:
    """Every Non-Qualified row of the latest version of the calls (each Speech sample of its CDR)."""
    from src.modules import non_qualified_calls as nq

    with repository.connection() as connection:
        return [dict(row) for row in connection.execute(
            f'SELECT n.call_key, n.dataset_id, n.source_row_id, n.join_id FROM {nq.NQ_CALLS_TABLE} n '
            f'JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = n.call_key AND l.dataset_id = n.dataset_id '
            "WHERE l.version_state <> 'qualified'")]


def _exclusions(repository: Any) -> Callable[[int, str], bool]:
    """Whether the JOIN_ID of a call of a CDR is in a list of Scoring Excluded Calls that applies to it."""
    from src.modules import scoring_exclusions

    scoring_exclusions.ensure_tables(repository)
    scope = scoring_exclusions.load_scope(repository)
    cache: dict[tuple[int, ...], set[str]] = {}

    def excluded(dataset_id: int, join_id: str) -> bool:
        if not scope or not join_id:
            return False
        ids = tuple(scope.list_ids_for(dataset_id))
        if not ids:
            return False
        if ids not in cache:
            with repository.connection() as connection:
                cache[ids] = {str(row[0]) for row in connection.execute(
                    f"SELECT join_key FROM {scoring_exclusions.CALLS_TABLE} WHERE list_id IN ({', '.join('?' for _ in ids)})", ids)}
        return scoring_exclusions.join_key(join_id) in cache[ids]
    return excluded


def _node_lookup(repository: Any) -> Callable[[str, tuple[str, int]], dict[str, str] | None]:
    """The site, host and vendor of an eNB or gNB of an operator, from the cell mappings of the workspace."""
    from src.modules import non_qualified_calls as nq

    mappings: dict[str, dict[tuple[str, int], dict[str, str]]] = {}
    with repository.connection() as connection:
        for dataset in repository.list_datasets():
            kind = str(dataset['dataset_kind'] or '')
            if kind in nq.MAPPING_OPERATORS and str(dataset['status'] or '') == 'ready':
                try:
                    mappings.setdefault(kind, {}).update(nq._node_mappings(connection, dataset))
                except Exception:  # noqa: BLE001 - an unreadable mapping only leaves its nodes without a site.
                    continue

    def details(operator: str, node: tuple[str, int]) -> dict[str, str] | None:
        kind = next((name for name, pattern in nq.MAPPING_OPERATORS.items() if pattern.match(operator.strip())), None)
        return mappings.get(kind, {}).get(node) if kind else None
    return details


def calculate(repository: Any, progress: Callable[[int, int, str], None] | None = None, *,
              username: str = SYSTEM_USER) -> dict[str, Any]:
    """Calculate the scoring impact and the repetitions of every Non-Qualified Call, then apply the rules."""
    from src.modules import non_qualified_calls as nq
    from src.modules.cdr_auto_selection import campaign_identity

    started = time.monotonic()
    nq.ensure_nq_tables(repository)
    nq.refresh_latest_calls(repository)
    settings = load_settings(repository)
    stamp = fingerprint(repository, settings)
    calls = _latest_calls(repository)
    rows = _call_rows(repository)
    try:
        profiles = repository.get_scoring_profiles()
    except ValueError:
        profiles = None
    mappings = repository.list_operator_mappings()
    kinds = {int(row['id']): str(row['dataset_kind'] or '').casefold() for row in repository.list_datasets()}
    excluded = _exclusions(repository)
    # The calls of each campaign and NR Mode, scored together.
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for call in calls:
        key = (str(call['nr_mode'] or '').upper(), campaign_identity(call['campaign']))
        group = groups.setdefault(key, {'campaign': str(call['campaign'] or ''), 'keys': set()})
        group['keys'].add(call['call_key'])
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_key.setdefault(row['call_key'], []).append(row)
    impacts: dict[str, dict[str, Any]] = {}
    campaigns = []
    now = nq.now_iso()
    for index, ((nr_mode, identity), group) in enumerate(sorted(groups.items(), key=lambda item: item[0]), start=1):
        if progress:
            progress(index - 1, len(groups), f"the scoring impact of {group['campaign'] or 'the calls without campaign'} {nr_mode}".rstrip())
        group_rows = [row for key in group['keys'] for row in rows_by_key.get(key, [])]
        outcome = campaign_impact(repository, nr_mode, group['campaign'], group_rows, profiles, mappings, excluded, kinds)
        campaign_key = f'{nr_mode}|{identity}'
        for key in group['keys']:
            impacts[key] = {**outcome['calls'].get(key, {'state': outcome['state'], 'points': 0.0, 'kpis': []}),
                            'campaign_key': campaign_key}
            if outcome['state'] != SCORED:
                impacts[key]['state'] = outcome['state']
        scored = [impacts[key] for key in group['keys'] if impacts[key]['state'] == SCORED]
        campaigns.append((campaign_key, nr_mode, group['campaign'], outcome['state'], outcome['detail'], outcome['methodology'],
                          len(group['keys']), round(sum(item['points'] for item in scored), 4), now))
    # The level of each call within its campaign, operator and service.
    by_call = {call['call_key']: call for call in calls}
    pareto: dict[tuple[str, str, str], dict[str, float]] = {}
    for key, impact in impacts.items():
        if impact['state'] == SCORED:
            call = by_call[key]
            pareto.setdefault((impact['campaign_key'], str(call['operator'] or '').casefold(), str(call['service'])), {})[key] = impact['points']
    levels: dict[str, str] = {}
    for points in pareto.values():
        levels.update(impact_levels(points, settings['high_share'], settings['medium_share']))
    # Where each call failed, and the calls of its operator at the same place.
    if progress:
        progress(len(groups), len(groups) + 1, 'the repetitions of the calls')
    lookup = _node_lookup(repository)
    for call in calls:
        call['place_key'], call['place_label'] = place_of(call, lookup, settings['spot_meters'])
        call['quarter'] = quarter_of(call['start_time'], call['campaign'])
        call['campaign_label'] = f"{call['campaign']}|{call['nr_mode']}"
    repeated = repetitions(calls, settings['previous_quarters'])
    values = []
    for call in calls:
        impact = impacts.get(call['call_key'], {'state': NOT_SCORED, 'points': 0.0, 'kpis': [], 'campaign_key': ''})
        state = impact['state']
        count, campaigns_count = repeated.get(call['call_key'], (None, None))
        values.append((
            call['call_key'], impact['campaign_key'], state, impact['points'] if state in {SCORED, EXCLUDED} else None,
            levels.get(call['call_key'], nq_catalog.IMPACT_NONE) if state == SCORED else LEVEL_OF_STATE[state],
            kpis_text(impact['kpis']) if state == SCORED else '', json.dumps(impact['kpis'] if state == SCORED else [], ensure_ascii=False),
            call['place_key'], call['place_label'], count, campaigns_count,
            ('Yes' if count is not None and count >= settings['min_calls'] else 'No'), now,
        ))
    ensure_tables(repository)
    with repository.connection() as connection:
        connection.executemany(
            f'INSERT INTO {PRIORITY_TABLE} (call_key, campaign_key, impact_state, impact_points, impact_level, impact_kpis, '
            'impact_json, place_key, place_label, repetitions, repeated_campaigns, repeated, updated_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(call_key) DO UPDATE SET '
            'campaign_key = excluded.campaign_key, impact_state = excluded.impact_state, impact_points = excluded.impact_points, '
            'impact_level = excluded.impact_level, impact_kpis = excluded.impact_kpis, impact_json = excluded.impact_json, '
            'place_key = excluded.place_key, place_label = excluded.place_label, repetitions = excluded.repetitions, '
            'repeated_campaigns = excluded.repeated_campaigns, repeated = excluded.repeated, updated_at = excluded.updated_at',
            values)
        connection.execute(f'DELETE FROM {PRIORITY_TABLE} WHERE call_key NOT IN (SELECT value FROM json_each(?))',
                           (json.dumps([call['call_key'] for call in calls]),))
        connection.execute(f'DELETE FROM {PRIORITY_CAMPAIGNS_TABLE}')
        connection.executemany(
            f'INSERT INTO {PRIORITY_CAMPAIGNS_TABLE} (campaign_key, nr_mode, campaign, state, detail, methodology, calls, points, '
            'calculated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', campaigns)
    applied = apply_rules(repository, username, settings)
    summary = {
        'calculated_at': now, 'seconds': round(time.monotonic() - started, 1), 'calls': len(calls),
        'campaigns': len(campaigns), 'scored': sum(1 for item in impacts.values() if item['state'] == SCORED),
        'pending': sum(1 for item in impacts.values() if item['state'] == PENDING),
        'repeated': sum(1 for value in values if value[11] == 'Yes'), **applied,
    }
    repository.set_workspace_state(FINGERPRINT_STATE_KEY, stamp)
    repository.set_workspace_state(SUMMARY_STATE_KEY, json.dumps(summary))
    if hasattr(repository, 'try_add_log'):
        repository.try_add_log(username, 'nq_prioritization_calculated', json.dumps(summary))
    return summary


def apply_rules(repository: Any, username: str, settings: dict[str, Any] | None = None) -> dict[str, int]:
    """Apply the rules to every calculated call and fill the Priority of the open calls with the priority of their rule
    while it is empty or still the one the rules gave (a priority chosen by hand stays, and the rules stop changing it)."""
    from src.modules import non_qualified_calls as nq

    settings = settings or load_settings(repository)
    ensure_tables(repository)
    options = nq.list_options(repository)
    closed = {item['name'].casefold() for item in options['statuses'] if item['closed']}
    default = nq.untracked_status(repository, options)
    priorities = {name.casefold(): name for name in priority_options(repository)}
    fill = bool(settings['fill_priority'] and priorities)
    rules = compile_rules(settings['rules'])
    when = nq.now_iso()
    counts = {'prioritized': 0, 'tracked': 0, 'no_rule': 0, 'priorities_set': 0}
    changed_keys = []
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT p.call_key, p.impact_level, p.repeated, p.prioritization, p.priority_rule, p.suggested_priority, "
            f"p.priority_filled, l.service, l.nr_mode, l.operator, l.region, l.city, "
            f"COALESCE(NULLIF(t.status, ''), ?) AS status, COALESCE(f.value, '') AS priority "
            f'FROM {PRIORITY_TABLE} p JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = p.call_key '
            f'LEFT JOIN {nq.NQ_CALL_TRACKING_TABLE} t ON t.call_key = p.call_key '
            f'LEFT JOIN {nq.NQ_FIELD_VALUES_TABLE} f ON f.call_key = p.call_key AND f.field_key = ?',
            (default, PRIORITY_FIELD)).fetchall()
        updates = []
        for row in rows:
            decision, rule, suggestion = decide(rules, row, row['repeated'] == 'Yes', row['impact_level'] == IMPACT_HIGH)
            counts[{PRIORITIZED: 'prioritized', TRACK_ONLY: 'tracked'}.get(decision, 'no_rule')] += 1
            suggestion = priorities.get(suggestion.casefold(), '') if suggestion else ''
            filled = str(row['priority_filled'] or '')
            current = str(row['priority'] or '')
            if fill and filled != BY_HAND and str(row['status']).casefold() not in closed:
                if filled and current != filled:
                    # Changed (or cleared) by hand: the rules no longer change it.
                    filled = BY_HAND
                elif (filled or not current) and suggestion != current:
                    if suggestion:
                        connection.execute(
                            f'INSERT INTO {nq.NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) '
                            'VALUES (?, ?, ?, ?, ?) ON CONFLICT(call_key, field_key) DO UPDATE SET value = excluded.value, '
                            'updated_by = excluded.updated_by, updated_at = excluded.updated_at',
                            (row['call_key'], PRIORITY_FIELD, suggestion, username, when))
                    else:
                        connection.execute(f'DELETE FROM {nq.NQ_FIELD_VALUES_TABLE} WHERE call_key = ? AND field_key = ?',
                                           (row['call_key'], PRIORITY_FIELD))
                    nq._record_history(connection, row['call_key'], f'field:{PRIORITY_FIELD}', current, suggestion, username, when)
                    counts['priorities_set'] += 1
                    changed_keys.append(row['call_key'])
                    filled = suggestion
            if (decision, rule, suggestion, filled) != (row['prioritization'], row['priority_rule'], row['suggested_priority'],
                                                       str(row['priority_filled'] or '')):
                updates.append((decision, rule, suggestion, filled, row['call_key']))
        connection.executemany(
            f'UPDATE {PRIORITY_TABLE} SET prioritization = ?, priority_rule = ?, suggested_priority = ?, priority_filled = ? '
            'WHERE call_key = ?', updates)
    # A status rule that reads the Priority follows it.
    if changed_keys and any(condition.get('field') == PRIORITY_FIELD for rule in nq.status_rules(repository)
                            for condition in rule['conditions']):
        nq.recompute_statuses(repository, username, changed_keys)
    return counts


# ---------------------------------------------------------------------------
# Calculating in the background
# ---------------------------------------------------------------------------
_jobs: dict[str, dict[str, Any]] = {}
_jobs_guard = Lock()


def _workspace_key(path: Any) -> str:
    return str(Path(str(path)).resolve())


def job(database_path: Any) -> dict[str, Any] | None:
    with _jobs_guard:
        current = _jobs.get(_workspace_key(database_path))
        return dict(current) if current else None


def needs_calculation(repository: Any) -> bool:
    """Whether what the values depend on changed since they were calculated (a calculation that failed is tried again
    once it changes)."""
    stamp = fingerprint(repository)
    return stamp not in {repository.get_workspace_state(FINGERPRINT_STATE_KEY), repository.get_workspace_state(FAILED_STATE_KEY)}


def start(repository: Any, submit: Callable[..., Any], *, username: str = SYSTEM_USER) -> dict[str, Any]:
    """Queue the calculation of the workspace, unless it is already queued or running."""
    key = _workspace_key(repository.db_path)
    with _jobs_guard:
        current = _jobs.get(key)
        if current and current['status'] in {'queued', 'processing'}:
            return dict(current)
        entry = {'status': 'queued', 'queued_at': time.time(), 'started_at': None, 'finished_at': None, 'error': '',
                 'done': 0, 'total': 0, 'current': '', 'result': None}
        _jobs[key] = entry

    def progress(done: int, total: int, step: str) -> None:
        with _jobs_guard:
            entry.update(done=done, total=total, current=step)

    def run() -> None:
        with _jobs_guard:
            entry.update(status='processing', started_at=time.time())
        try:
            result = calculate(repository, progress, username=username)
        except Exception as exc:  # noqa: BLE001 - tried again once what it depends on changes.
            try:
                repository.set_workspace_state(FAILED_STATE_KEY, fingerprint(repository))
                if hasattr(repository, 'try_add_log'):
                    repository.try_add_log(username, 'nq_prioritization_failed', str(exc))
            except Exception:  # noqa: BLE001 - the job reports the failure anyway.
                pass
            with _jobs_guard:
                entry.update(status='failed', error=str(exc), finished_at=time.time())
            return
        with _jobs_guard:
            entry.update(status='ready', result=result, finished_at=time.time())

    submit(run)
    with _jobs_guard:
        return dict(entry)


def status(repository: Any) -> dict[str, Any]:
    """When the values were calculated, whether a calculation runs and the state of each campaign."""
    ensure_tables(repository)
    try:
        summary = json.loads(repository.get_workspace_state(SUMMARY_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        summary = {}
    current = job(repository.db_path)
    with repository.connection() as connection:
        campaigns = [dict(row) for row in connection.execute(
            f'SELECT * FROM {PRIORITY_CAMPAIGNS_TABLE} ORDER BY nr_mode, campaign')]
    from src.modules.column_names import campaign_sort_key
    campaigns.sort(key=lambda item: (campaign_sort_key(item['campaign']), item['nr_mode']))
    return {'summary': summary if isinstance(summary, dict) else {}, 'campaigns': campaigns,
            'running': bool(current and current['status'] in {'queued', 'processing'}),
            'error': current['error'] if current and current['status'] == 'failed' else ''}


# ---------------------------------------------------------------------------
# The Prioritization panel
# ---------------------------------------------------------------------------
MAX_ISSUES = 25
MAX_PANEL_KPIS = 12


def conditions_text(rule: dict[str, Any]) -> str:
    """What a rule takes, in words: Voice, Speech · SA · VF* (Every call when it has no condition)."""
    from src.modules.non_qualified_calls import SERVICE_LABELS

    parts = [', '.join(SERVICE_LABELS.get(value, value) for value in rule['services']), ', '.join(rule['nr_modes']),
             *(', '.join(rule[key]) for key in ('operators', 'regions', 'cities'))]
    return ' · '.join(part for part in parts if part) or 'Every call'


def panel(repository: Any, filters: Any, username: str) -> dict[str, Any]:
    """The NQ Prioritization of the filtered calls: the calls of each rule, the KPIs whose points they lose, the
    repeated issues and the calls to analyse next (prioritized, open and not attended yet)."""
    from src.modules import non_qualified_calls as nq

    settings = load_settings(repository)
    options = nq.list_options(repository)
    definitions = nq.list_fields(repository)
    filters = nq._resolve_key_filters(repository, filters if isinstance(filters, dict) else {})
    closed = [item['name'] for item in options['statuses'] if item['closed']]
    closed_names = {name.casefold() for name in closed}
    base, base_params = nq._base_sql(nq.untracked_status(repository, options), repository, nq._scope(filters))
    where, params = nq._filter_sql(filters, username, closed, definitions)
    with repository.connection() as connection:
        base, base_params = nq._materialized(connection, base, base_params, bool(nq._scope(filters)))
        rows = [dict(row) for row in connection.execute(
            f'WITH calls AS ({base}) SELECT call_key, join_id, service, nr_mode, campaign, operator, result, start_time, status, '
            'updated_at, comment_count, root_category, field_values_json, impact_points, impact_level, impact_state, '
            'impact_json, place_label, repetitions, repeated_campaigns, repeated, prioritization, priority_rule, '
            f'suggested_priority FROM calls{where}', [*base_params, *params])]
    is_open = [str(row['status'] or '').casefold() not in closed_names for row in rows]
    attended = [bool(row['updated_at']) or int(row['comment_count'] or 0) > 0 for row in rows]
    # The calls of each rule, in the order of the rules, then those no rule takes.
    order = {rule['name']: index for index, rule in enumerate(settings['rules'])}
    rules = [{'name': rule['name'], 'conditions': conditions_text(rule), 'criterion': CRITERIA[rule['criterion']],
              'priority': rule['priority'], 'track_priority': rule['track_priority'], 'calls': 0, 'prioritized': 0,
              'tracked': 0, 'points': 0.0, 'open': 0, 'attended': 0} for rule in settings['rules']]
    unruled = {'name': '', 'conditions': 'The calls no rule takes', 'criterion': '', 'priority': '', 'track_priority': '',
               'calls': 0, 'prioritized': 0, 'tracked': 0, 'points': 0.0, 'open': 0, 'attended': 0}
    levels: dict[str, int] = {}
    kpis: dict[tuple[str, str, str], dict[str, Any]] = {}
    issues: dict[tuple[str, str], dict[str, Any]] = {}
    queue = []
    for row, opened, followed in zip(rows, is_open, attended):
        points = float(row['impact_points'] or 0)
        entry = rules[order[row['priority_rule']]] if row['priority_rule'] in order else unruled
        entry['calls'] += 1
        entry['prioritized'] += row['prioritization'] == PRIORITIZED
        entry['tracked'] += row['prioritization'] == TRACK_ONLY
        entry['points'] += points
        entry['open'] += opened
        entry['attended'] += followed
        level = row['impact_level'] or 'Waiting'
        levels[level] = levels.get(level, 0) + 1
        try:
            lost = json.loads(row['impact_json'] or '[]')
        except (TypeError, ValueError):
            lost = []
        for item in lost if isinstance(lost, list) else []:
            if isinstance(item, dict):
                key = (str(item.get('code') or ''), str(item.get('kpi') or ''), str(item.get('environment') or ''))
                kpi = kpis.setdefault(key, {'code': key[0], 'kpi': key[1], 'category': str(item.get('category') or ''),
                                            'environment': key[2], 'calls': 0, 'points': 0.0})
                kpi['calls'] += 1
                kpi['points'] += float(item.get('points') or 0)
        if row['repeated'] == 'Yes' and row['place_label']:
            issue = issues.setdefault((str(row['operator'] or ''), row['place_label']), {
                'operator': str(row['operator'] or ''), 'place': row['place_label'], 'calls': 0, 'campaigns': set(),
                'services': {}, 'nr_modes': {}, 'points': 0.0, 'open': 0, 'repetitions': 0, 'categories': {}})
            issue['calls'] += 1
            issue['campaigns'].add(f"{row['campaign']}|{row['nr_mode']}")
            label = nq.SERVICE_LABELS.get(str(row['service']), str(row['service']))
            issue['services'][label] = issue['services'].get(label, 0) + 1
            mode = str(row['nr_mode'] or 'Unknown')
            issue['nr_modes'][mode] = issue['nr_modes'].get(mode, 0) + 1
            issue['points'] += points
            issue['open'] += opened
            issue['repetitions'] = max(issue['repetitions'], int(row['repetitions'] or 0))
            if row['root_category']:
                issue['categories'][row['root_category']] = issue['categories'].get(row['root_category'], 0) + 1
        if row['prioritization'] == PRIORITIZED and opened and not followed:
            queue.append(row)
    # The calls to analyse next: by the order of their rule, the points they lose, their repetitions, the newest first.
    queue.sort(key=lambda row: str(row['start_time'] or ''), reverse=True)
    queue.sort(key=lambda row: (order.get(row['priority_rule'], len(order)), -float(row['impact_points'] or 0),
                                -int(row['repetitions'] or 0)))

    def priority_of(row: dict[str, Any]) -> str:
        try:
            values = json.loads(row['field_values_json'] or '{}') or {}
        except (TypeError, ValueError):
            values = {}
        return str(values.get(PRIORITY_FIELD) or row['suggested_priority'] or '')
    issue_rows = sorted(issues.values(), key=lambda item: (-item['calls'], -item['points'], item['operator'].casefold(), item['place']))
    for item in issue_rows:
        item['campaigns'] = len(item['campaigns'])
        item['points'] = round(item['points'], 2)
        item['category'] = max(item.pop('categories').items(), key=lambda pair: (pair[1], pair[0]))[0] if item['categories'] else ''
    for entry in (*rules, unruled):
        entry['points'] = round(entry['points'], 2)
    level_order = [name for name, _color in nq_catalog.IMPACT_LEVELS]
    return {
        'status': status(repository),
        'settings': {key: settings[key] for key in ('high_share', 'medium_share', 'min_calls', 'previous_quarters', 'capacity')},
        'totals': {
            'calls': len(rows), 'prioritized': sum(row['prioritization'] == PRIORITIZED for row in rows),
            'tracked': sum(row['prioritization'] == TRACK_ONLY for row in rows),
            'high': sum(row['impact_level'] == IMPACT_HIGH for row in rows),
            'repeated': sum(row['repeated'] == 'Yes' for row in rows), 'places': len(issues),
            'points': round(sum(float(row['impact_points'] or 0) for row in rows), 2), 'next': len(queue),
            'waiting': sum(not row['impact_state'] for row in rows),
        },
        'levels': [{'value': name, 'count': levels[name], 'color': dict(nq_catalog.IMPACT_LEVELS).get(name, '')}
                   for name in sorted(levels, key=lambda name: level_order.index(name) if name in level_order else len(level_order))],
        'rules': [*rules, *([unruled] if unruled['calls'] else [])],
        'kpis': sorted(({**item, 'points': round(item['points'], 2)} for item in kpis.values()),
                       key=lambda item: (-item['points'], item['code'], item['environment']))[:MAX_PANEL_KPIS],
        'issues': issue_rows[:MAX_ISSUES], 'issue_count': len(issue_rows),
        'queue': [{'call_key': row['call_key'], 'join_id': row['join_id'], 'operator': row['operator'],
                   'service': nq.SERVICE_LABELS.get(str(row['service']), str(row['service'])), 'nr_mode': row['nr_mode'],
                   'campaign': row['campaign'], 'result': row['result'], 'start_time': row['start_time'],
                   'rule': row['priority_rule'], 'priority': priority_of(row),
                   'points': None if row['impact_points'] is None else round(float(row['impact_points']), 2),
                   'level': row['impact_level'], 'repetitions': row['repetitions'], 'place': row['place_label']}
                  for row in queue[:settings['capacity']]],
    }
