"""NQ Prioritization: which Non-Qualified Calls the teams analyse first.

Every Non-Qualified Call (the latest version of each call, as the calls table lists it) gets three values:

- **Scoring Impact**: the points of the scoring its failure loses. For every KPI of the methodology of its campaign that
  counts tests (the ratios: call success, transfer success, POLQA below 1.6, throughput above a threshold...), the
  points the operator loses in that KPI in the environment of the call (Drive - City, Drive - Connecting Roads...) are
  shared equally among the tests that miss it, as the Points Lost Map shares them (see ``scoring_points_loss``); a call
  holds the share of every KPI it misses. The scoring of each campaign and NR Mode is calculated from the Scoring
  History over the CDRs the combined CDR tables include, with the methodology that applies to the campaign. The level is
  a Pareto within the campaign, operator and service of the call, the calls in scope compared only with each other: the
  calls that hold the first share of the points lost (50 % by default) are High, those up to the second share (80 %)
  Medium and the others Low.
- **Repetition**: how many Non-Qualified Calls of the same operator failed at the same place in the quarter of the call
  and the quarters before it (one by default), whatever their service and NR Mode. The place is the site of the cell
  where the call ended (the site ID and host network of its eNB or gNB in the inventory cells of the workspace, in the
  networks that serve its operator and within their distance of the call), else the site that served its start
  (serving-cell Vendor Mapping), else the eNB or gNB of its last cell, else a spot of about 250 m around where it
  started.
- **Prioritization**: the strategy of the workspace (admins choose it) gives every call its step, its queue and its
  Priority:

  - **Dual Queue (Cities first)** (the default) and **Dual Queue (Roads first)** order the calls of the operators of their
    SA and NSA steps (the Focus operators by name by default, the SA steps those that use SA; the calls of the regions
    out of scope and of the SA campaigns of an operator without SA stay out) with two lists, their steps giving the
    Priority from P1 to P8. During a
    campaign, list 1 takes each call by what it says about itself, which never changes: P1 SA Voice in Cities (on
    Connecting Roads with Roads first), P2 SA Data (the consecutive failures of a hotspot, 2+ failed data tests at one
    spot of a drive), P3 SA Voice on
    Connecting Roads (in Cities), P4 SA WhatsApp, P5 NSA Data, P6 NSA Voice, P7 NSA WhatsApp and P8 the tracked calls.
    Once the Final CDR of the campaign is scored, list 2 orders its calls by their real impact. Admins change every field
    of the steps, their conditions joined by AND or OR. Voice and WhatsApp calls go to the Voice queue, Data calls to the
    Data queue; inside a step the calls with the highest Expected Gain go first (from the Final CDR of the latest
    campaign), then the oldest.
  - **Points Lost Based** (the Custom rules of the first version, whose rules become its steps): SA before NSA and Voice
    before Data, every Voice and WhatsApp call and the Data calls of a cluster with a high impact (the others are
    tracked with P5), with list 1 for every call until the admins turn its list 2 on.
  - Strategies of the admins: steps like the others, created as a copy of one of them.

  Admins can rename every strategy. The Priority of the open calls is filled with the priority of their step while
  nobody has chosen another one by hand, and never changes once the analysis of the call has started.

The values are calculated in the background when the server is idle, after the indexing of the calls and the Scoring
History, whenever what they depend on changes; the strategy and its steps apply again as soon as they are saved.

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
IMPACT_VERSION = 11
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
# The strategies that give every call its step, queue and Priority.
CITIES_FIRST, ROADS_FIRST, CUSTOM, VODAFONE_PROPOSAL = 'cities_first', 'roads_first', 'custom', 'vodafone_proposal'
STRATEGIES = {CITIES_FIRST: 'Dual Queue (Cities first)', ROADS_FIRST: 'Dual Queue (Roads first)', CUSTOM: 'Points Lost Based',
              VODAFONE_PROPOSAL: 'Vodafone Proposal'}
# The strategies of the application that use list 1 alone by default (every call, also once its Final CDR is scored).
LIST_1_ONLY = (CUSTOM, VODAFONE_PROPOSAL)
# The strategies admins create beside them (steps like the Dual Queue strategies), and the steps they add to any strategy.
USER_STRATEGY = re.compile(r'^strategy-[a-z0-9]{3,24}$')
ADDED_STEP = re.compile(r'^(campaign|final)-s[0-9]{1,6}$')
MAX_STRATEGIES = 20
MAX_LIST_STEPS = 20
DEFAULT_STRATEGY = CITIES_FIRST
VOICE_QUEUE, DATA_QUEUE = 'Voice', 'Data'
# List 1 orders the calls of a campaign until its Final CDR is scored; list 2 orders them after.
CAMPAIGN_LIST, FINAL_LIST = 'campaign', 'final'
LIST_LABELS = {CAMPAIGN_LIST: 'Campaign', FINAL_LIST: 'Final'}
# A hotspot by default: failures of one call type in one drive, each at most 15 minutes after the previous one, the same
# day, at most 250 m from it or at the same site (the Hotspot time and distance of the settings; the distance is the
# Cluster distance by default too).
CLUSTER_MINUTES = 15
CLUSTER_METERS = 250.0
# The settings of the clusters and the hotspots, applied at once when they change (the places, repetitions and hotspots
# of the calls are calculated again from their stored values, without the scoring impact).
PLACE_SETTINGS = ('min_calls', 'previous_quarters', 'spot_meters', 'hotspot_meters', 'hotspot_minutes')
# The columns of a data CDR that give the order of its tests in the drive (two failures are consecutive tests when their
# sequence numbers follow each other in the same file).
# The columns that give the order of the tests of a drive: those of the data CDRs, else those of the voice CDRs.
FILE_COLUMNS, SEQUENCE_COLUMNS = ('File_ID', 'File_ID_A'), ('Sequence_ID_per_File', 'Sequence_ID_A')
# The kinds of call the strategies tell apart.
VOICE, WHATSAPP, DATA, PING = 'voice', 'whatsapp', 'data', 'ping'
KIND_LABELS = {VOICE: 'Voice', WHATSAPP: 'WhatsApp', DATA: 'Data', PING: 'Ping'}
# The Priority of the calls the strategies only track (the steps give P1 to P7).
TRACKED_PRIORITY = 'P8'
STRATEGY_PRIORITY_NAMES = tuple(f'P{number}' for number in range(1, 9))
# The fields of a step of a strategy, which admins change: the NR Mode, the type and the area of the calls it
# takes (where they failed: Connecting Roads and highways, else Cities, from their environment), the condition they meet (during the campaign, list 1, only what a call says about itself; once the Final CDR of the
# campaign is scored, list 2, also its impact and repetitions) and its queue (none: the step only tracks its calls). A
# cluster is 2+ failed data tests at one spot of a drive.
STEP_NR_MODES = {'SA': 'SA', 'NSA': 'NSA', 'any': 'Any'}
CALL_TYPES = {'voice': 'Voice', 'whatsapp': 'WhatsApp', 'data': 'Data', 'any': 'Any'}
CALL_TYPE_TAKES = {'voice': 'Voice calls', 'whatsapp': 'WhatsApp calls', 'data': 'Data tests', 'any': 'calls'}
STEP_AREAS = {'city': 'Cities', 'roads': 'Connecting Roads', 'any': 'Any'}
AREA_TAKES = {'city': ' in cities', 'roads': ' on connecting roads and highways', 'any': ''}
# The Call Types of the first version of the steps, which also gave the area.
LEGACY_CALL_TYPES = {'voice_cities': ('voice', 'city'), 'voice_roads': ('voice', 'roads')}
# The conditions of a step, chosen one by one, each joined to the one before by AND or OR, AND first: "Consecutive
# failures AND Hotspots OR High impact" takes the consecutive failures of a hotspot and the calls with a High impact
# (Every call alone takes every call). AND ( and OR ( start a group, one level of parentheses: "(High impact OR Medium
# impact) AND Repeated". Consecutive failures: the test right before or after it in the drive failed too.
EVERY_CALL = 'all'
JOINS = {'and': 'AND', 'or': 'OR', 'and_group': 'AND (', 'or_group': 'OR ('}
GROUP_JOINS = {'and_group': 'and', 'or_group': 'or'}
JOIN_WORDS = {'and': 'and', 'or': 'or'}
MAX_CONDITIONS = 6
CONDITION_LABELS = {EVERY_CALL: 'Every call', 'consecutive': 'Consecutive failures', 'cluster': 'Hotspots', 'drop': 'Drops', 'setup': 'Setup failures', 'high': 'High impact', 'medium': 'Medium impact', 'low': 'Low impact',
                    'repeated': 'Cluster'}
# Every call type and both lists take every condition (the impact levels by the Expected Gain of the call, see
# ``expected_levels``: during the campaign from the latest Final CDR of its NR Mode, then its own points).
CONDITIONS = {key: CONDITION_LABELS[key] for key in (EVERY_CALL, 'consecutive', 'repeated', 'cluster', 'high', 'medium', 'low',
                                                     'drop', 'setup')}
# The conditions of the first versions, and those that stand for them (Biggest impact was the High impact of the Expected
# Gain, as the impact levels are now).
FORMER_CONDITIONS = {'biggest': 'high'}
CAMPAIGN_CONDITIONS = FINAL_CONDITIONS = CONDITIONS
CONDITION_TAKES = {
    EVERY_CALL: 'every one', 'consecutive': 'the consecutive failures (the test right before or after failed too)',
    'cluster': 'the failures of a hotspot (2+ failures of the same call type at one spot of a drive)',
    'drop': 'the drops (calls dropped and data tests cut off once established)',
    'setup': 'the setup failures (calls and data tests that failed before being established)',
    'high': 'those with a High impact (by Expected Gain)',
    'medium': 'those with a Medium impact (by Expected Gain)', 'low': 'those with a Low impact (or none, by Expected Gain)',
    'repeated': 'those of a cluster (a Repeated Issue: the operator failed at the same place in several calls)',
}
# What each condition is based on, as a tag beside it: the scoring (unstable during the campaign), the place, the place
# and the time, the order of the tests of the drive, or the result of the call itself.
CONDITION_KINDS = {
    'consecutive': ('Sequence-based', 'sequence'), 'cluster': ('Position & time', 'position'), 'repeated': ('Position-based', 'position'),
    'high': ('Scoring-based', 'scoring'), 'medium': ('Scoring-based', 'scoring'),
    'low': ('Scoring-based', 'scoring'), 'drop': ('Result-based', 'result'), 'setup': ('Result-based', 'result'),
}
# What each condition means, as the Prioritization Rules dialog explains it.
CONDITION_HELP = {
    EVERY_CALL: 'Every call of the step.',
    'consecutive': 'The test right before or after it in the same drive failed too.',
    'cluster': 'Two or more failures of the same call type at one spot of one drive: each within the Hotspot time of the '
               'previous one, the same day, within the Hotspot distance of it or at the same site.',
    'repeated': 'The operator failed at the same place (its site, else a spot of the Cluster distance) in at least Cluster size '
                'calls of the quarter and the Cluster period before it, in any drive.',
    'high': 'Within the first High share of the Expected Gain of the calls in scope of its campaign, operator and service: during '
            'the campaign what its failure lost in the latest Final CDR of its NR Mode, then its own points.',
    'medium': 'The next calls by Expected Gain, up to the Medium share.',
    'low': 'The rest by Expected Gain, or no Expected Gain.',
    'drop': 'The call dropped, or the data test was cut off, once established.',
    'setup': 'The call or the data test failed before being established.',
}
STEP_QUEUES = {VOICE_QUEUE: 'Voice', DATA_QUEUE: 'Data', '': 'Tracked'}
MAX_STEP_NUMBER = 20
# The operators of a step that stand for the Focus operators of the Operator Maps (alone). By default the steps take the
# Focus operators by name: the SA steps those that use SA, the others those with calls. An operator uses SA when at least
# SA_SHARE of its Non-Qualified Calls of the SA campaigns ran on NR SA (an operator without SA, such as Three, drives them
# on LTE and EN-DC).
FOCUSED_OPERATORS = '@focused'
FOCUSED_LABEL = 'Focused Operators'
# The calls the strategies leave out of the queues: those of the regions and of the NR Mode and operator pairs out of the
# scope of the team (chosen by the admins; SA · Three by default, the SA campaigns of an operator without SA, whose calls
# there are NSA calls its NSA campaigns already have).
OUT_OF_SCOPE = 'Out of scope'
OUT_OF_SCOPE_KIND = 'out_of_scope'
# The regions out of scope until the admins choose others: Vendor B, the region of the other vendor, which is not the
# responsibility of the team.
DEFAULT_EXCLUDED_REGIONS = ('Vendor B',)
SA_TECHNOLOGY = re.compile(r'(?<![A-Z])SA(?![A-Z])|NE-DC', re.IGNORECASE)
SA_SHARE = 0.10

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
    updated_at TEXT NOT NULL DEFAULT '',
    cluster_key TEXT NOT NULL DEFAULT '',
    cluster_size INTEGER,
    consecutive TEXT NOT NULL DEFAULT '',
    final_list INTEGER NOT NULL DEFAULT 0,
    expected_points REAL,
    expected_campaign TEXT NOT NULL DEFAULT '',
    queue TEXT NOT NULL DEFAULT '',
    queue_step INTEGER,
    queue_list TEXT NOT NULL DEFAULT ''
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
# The columns of the strategies, added to the tables written before them.
STRATEGY_COLUMNS = (('cluster_key', "TEXT NOT NULL DEFAULT ''"), ('cluster_size', 'INTEGER'), ('consecutive', "TEXT NOT NULL DEFAULT ''"),
                    ('final_list', 'INTEGER NOT NULL DEFAULT 0'), ('expected_points', 'REAL'),
                    ('expected_campaign', "TEXT NOT NULL DEFAULT ''"), ('queue', "TEXT NOT NULL DEFAULT ''"),
                    ('queue_step', 'INTEGER'), ('queue_list', "TEXT NOT NULL DEFAULT ''"))


def ensure_columns(connection: Any) -> None:
    """The tables of the NQ Prioritization with the columns of this version."""
    connection.executescript(SCHEMA)
    present = {str(row[1]) for row in connection.execute(f'PRAGMA table_info({PRIORITY_TABLE})')}
    for column, definition in STRATEGY_COLUMNS:
        if column not in present:
            connection.execute(f'ALTER TABLE {PRIORITY_TABLE} ADD COLUMN {column} {definition}')


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


def default_settings(operators: dict[str, list[str]] | None = None, modes: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """The default settings; ``operators`` gives the operators of the steps by NR Mode (``default_step_operators``) and
    ``modes`` the NR Mode and operator pairs out of scope (``default_excluded_modes``)."""
    return {'strategy': DEFAULT_STRATEGY, 'steps': default_steps(operators), 'high_share': 50,
            'medium_share': 80, 'min_calls': 2, 'previous_quarters': 1, 'spot_meters': int(CLUSTER_METERS), 'hotspot_meters': int(CLUSTER_METERS),
            'hotspot_minutes': CLUSTER_MINUTES, 'capacity': 20,
            'fill_priority': True, 'excluded_regions': list(DEFAULT_EXCLUDED_REGIONS),
            'excluded_modes': [dict(item) for item in modes or []], 'strategies': [], 'strategy_names': {},
            'final_lists': {key: key not in LIST_1_ONLY for key in STRATEGIES}}


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


def normalize_settings(value: Any, *, strict: bool = False, operators: dict[str, list[str]] | None = None,
                       modes: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Valid settings (the defaults for what is missing, the operators of the steps from ``operators``, the NR Mode and
    operator pairs out of scope from ``modes`` until they are chosen); ``strict`` refuses invalid values instead of fixing
    them."""
    value = value if isinstance(value, dict) else {}
    defaults = default_settings(operators, modes)
    high = _whole(value.get('high_share', defaults['high_share']), defaults['high_share'], 5, 95, 'The High share', strict)
    medium = _whole(value.get('medium_share', defaults['medium_share']), defaults['medium_share'], 5, 100,
                    'The Medium share', strict)
    if medium <= high:
        if strict:
            raise ValueError('The Medium share must be above the High share.')
        medium = min(100, high + 1)
    # The rules of Points Lost Based of the first version become its steps, unless it has steps already.
    legacy = legacy_rules(value['rules']) if isinstance(value.get('rules'), list) else None
    given_steps = value.get('steps') if isinstance(value.get('steps'), dict) else {}
    final_lists = value.get('final_lists') if isinstance(value.get('final_lists'), dict) else {}
    if legacy is not None and legacy != default_rules() and CUSTOM not in given_steps:
        given_steps = {**given_steps, CUSTOM: steps_from_rules(legacy, operators)}
        final_lists = {**final_lists, CUSTOM: False}
    names = normalize_strategy_names(value.get('strategy_names'), strict)
    own = normalize_strategies(value.get('strategies'), strict, {**STRATEGIES, **names}.values())
    labels = strategy_labels({'strategies': own, 'strategy_names': names})
    strategy = value.get('strategy')
    if strategy is None:
        # Settings saved before the strategies: rules of their own stay in use (as the steps of Points Lost Based), the
        # default ones give way to the default strategy.
        strategy = CUSTOM if value and legacy is not None and legacy != default_rules() else DEFAULT_STRATEGY
    elif strategy not in labels:
        if strict:
            raise ValueError('Choose the strategy of the NQ Prioritization.')
        strategy = DEFAULT_STRATEGY
    return {
        'strategy': strategy, 'strategies': own, 'strategy_names': names,
        'steps': normalize_steps(given_steps, strict, operators, labels),
        'high_share': high, 'medium_share': medium,
        'min_calls': _whole(value.get('min_calls', defaults['min_calls']), defaults['min_calls'], 2, 50,
                            'The Cluster size', strict),
        'previous_quarters': _whole(value.get('previous_quarters', defaults['previous_quarters']), defaults['previous_quarters'],
                                    0, 8, 'The Cluster period', strict),
        'spot_meters': _whole(value.get('spot_meters', defaults['spot_meters']), defaults['spot_meters'], 25, 2000,
                              'The Cluster distance', strict),
        'hotspot_meters': _whole(value.get('hotspot_meters', defaults['hotspot_meters']), defaults['hotspot_meters'], 25, 5000,
                                 'The Hotspot distance', strict),
        'hotspot_minutes': _whole(value.get('hotspot_minutes', defaults['hotspot_minutes']), defaults['hotspot_minutes'], 1, 240,
                                  'The Hotspot time', strict),
        'capacity': _whole(value.get('capacity', defaults['capacity']), defaults['capacity'], 1, 500,
                           'The calls to analyse next', strict),
        'fill_priority': bool(value.get('fill_priority', defaults['fill_priority'])),
        'excluded_regions': _values(value['excluded_regions']) if isinstance(value.get('excluded_regions'), list) else list(DEFAULT_EXCLUDED_REGIONS),
        'excluded_modes': (normalize_modes(value['excluded_modes'], strict) if isinstance(value.get('excluded_modes'), list)
                           else defaults['excluded_modes']),
        # Whether each strategy applies its list 2 once the Final CDR of a campaign is scored (else list 1 goes on): all but
        # Points Lost Based and Vodafone Proposal by default.
        'final_lists': {key: bool(final_lists.get(key, key not in LIST_1_ONLY)) for key in labels},
    }


def normalize_modes(value: list[Any], strict: bool = False) -> list[dict[str, str]]:
    """The NR Mode (SA or NSA) and operator pairs out of scope, once each."""
    modes: list[dict[str, str]] = []
    for item in value[:MAX_RULE_VALUES]:
        mode = str((item or {}).get('nr_mode') or '').upper() if isinstance(item, dict) else ''
        operator = re.sub(r'\s+', ' ', str((item or {}).get('operator') or '') if isinstance(item, dict) else '').strip()[:80]
        if mode not in NR_MODES or not operator:
            if strict:
                raise ValueError('Choose the NR Mode and the operator of every pair out of scope.')
            continue
        if not any(known['nr_mode'] == mode and known['operator'].casefold() == operator.casefold() for known in modes):
            modes.append({'nr_mode': mode, 'operator': operator})
    return modes


def load_settings(repository: Any) -> dict[str, Any]:
    try:
        stored = json.loads(repository.get_workspace_state(SETTINGS_STATE_KEY) or 'null')
    except (TypeError, ValueError):
        stored = None
    operators, modes = default_step_operators(repository), default_excluded_modes(repository)
    settings = normalize_settings(stored, operators=operators, modes=modes) if isinstance(stored, dict) else default_settings(operators, modes)
    # The operators excluded in the Operator Maps are left out everywhere, also of the pairs out of scope saved before.
    excluded = excluded_names(repository)
    settings['excluded_modes'] = [item for item in settings['excluded_modes'] if item['operator'].casefold() not in excluded]
    return settings


def priority_options(repository: Any) -> list[str]:
    """The values of the Priority field the rules fill ([] when the workspace has no such list)."""
    from src.modules import non_qualified_calls as nq

    field = next((item for item in nq.list_fields(repository) if item['key'] == PRIORITY_FIELD), None)
    if field is None or field['source'] != 'user' or field['type'] != 'list':
        return []
    return [option['name'] for option in field['options']]


def rule_names(repository: Any) -> list[str]:
    """The values of the Prioritization Rule field: the steps of the strategy."""
    settings = load_settings(repository)
    return [step['rule'] for step in strategy_steps(settings['strategy'], settings['steps'].get(settings['strategy']))]


def save_settings(repository: Any, payload: Any, username: str) -> dict[str, Any]:
    """Save the settings and apply the rules again at once; the impact and the repetitions are calculated again in the
    background when their settings change."""
    settings = normalize_settings(payload, strict=True, operators=default_step_operators(repository),
                                  modes=default_excluded_modes(repository))
    before = load_settings(repository)
    repository.set_workspace_state(SETTINGS_STATE_KEY, json.dumps(settings, ensure_ascii=False))
    if any(settings[name] != before[name] for name in PLACE_SETTINGS):
        refresh_places(repository, settings)
    # The levels compare the calls in scope with each other: the shares and the scope change them at once.
    if any(settings[name] != before[name] for name in ('high_share', 'medium_share', 'excluded_regions', 'excluded_modes')):
        refresh_levels(repository, settings)
    applied = apply_rules(repository, username, settings)
    if hasattr(repository, 'try_add_log'):
        labels, before_labels = strategy_labels(settings), strategy_labels(before)
        if settings['strategy'] != before['strategy']:
            repository.try_add_log(username, 'nq_prioritization_strategy', json.dumps({
                'from': before_labels.get(before['strategy'], before['strategy']), 'to': labels[settings['strategy']], **applied},
                ensure_ascii=False))
        # The steps whose fields changed, as "Dual Queue (Cities first) · Campaign 1 · SA Voice · Cities: Priority P1 → P3;
        # Operators Focused Operators → VF", and those added or deleted.
        steps_changed = []
        for strategy, label in labels.items():
            if strategy not in before_labels:
                continue
            old_steps = {step['id']: step for step in strategy_steps(strategy, before['steps'].get(strategy))}
            new_steps = {step['id']: step for step in strategy_steps(strategy, settings['steps'].get(strategy))}
            for key, step in new_steps.items():
                previous = old_steps.get(key)
                if previous is None:
                    steps_changed.append(f"{label} · Added step {step['rule']}")
                    continue
                changes = [f'{name} {step_field_text(previous, field)} → {step_field_text(step, field)}'
                           for field, name in STEP_FIELD_LABELS.items() if step_field_value(step, field) != step_field_value(previous, field)]
                if changes:
                    steps_changed.append(f"{label} · {previous['rule']}: {'; '.join(changes)}")
            steps_changed += [f"{label} · Deleted step {step['rule']}" for key, step in old_steps.items() if key not in new_steps]
        repository.try_add_log(username, 'nq_prioritization_settings', json.dumps({
            'strategy': labels[settings['strategy']], 'steps_changed': steps_changed,
            'strategies_added': [labels[key] for key in labels if key not in before_labels],
            'strategies_deleted': [before_labels[key] for key in before_labels if key not in labels],
            'strategies_renamed': [f'{before_labels[key]} → {labels[key]}' for key in labels
                                   if key in before_labels and before_labels[key] != labels[key]],
            'excluded_regions': settings['excluded_regions'],
            'excluded_modes': [f"{item['nr_mode']} · {item['operator']}" for item in settings['excluded_modes']],
            'changed': sorted(key for key in settings if settings[key] != before.get(key)), **applied}, ensure_ascii=False))
    return settings


# ---------------------------------------------------------------------------
# Rules of the first version (Points Lost Based before it had steps)
# ---------------------------------------------------------------------------
def legacy_rules(rules: list[Any]) -> list[dict[str, Any]]:
    """The valid rules of Points Lost Based of the first version (named once each), as saved before it had steps."""
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for rule in rules[:MAX_RULES]:
        if not isinstance(rule, dict):
            continue
        name = re.sub(r'\s+', ' ', str(rule.get('name') or '')).strip()[:60]
        if not name or name.casefold() in names:
            continue
        names.add(name.casefold())
        normalized.append({
            'name': name, 'services': _values(rule.get('services'), SERVICES), 'nr_modes': _values(rule.get('nr_modes'), NR_MODES),
            'operators': _values(rule.get('operators')), 'regions': _values(rule.get('regions')), 'cities': _values(rule.get('cities')),
            'criterion': str(rule.get('criterion') or 'all') if rule.get('criterion') in CRITERIA else 'all',
            'priority': str(rule.get('priority') or '').strip()[:40], 'track_priority': str(rule.get('track_priority') or '').strip()[:40],
        })
    return normalized


# The conditions of a step that stand for the criterion of a rule of the first version.
CRITERION_CONDITIONS = {'all': ([EVERY_CALL], []), 'repeated_or_high': (['repeated', 'high'], ['or']),
                        'repeated_and_high': (['repeated', 'high'], ['and']), 'repeated': (['repeated'], []), 'high': (['high'], []),
                        'track': ([EVERY_CALL], [])}


def steps_from_rules(rules: list[dict[str, Any]], operators: dict[str, list[str]] | None = None) -> dict[str, dict[str, Any]]:
    """The steps of list 1 of Points Lost Based from the rules of the first version (of ``legacy_rules``), in their order:
    one per rule and Call Type (Voice and WhatsApp for the Voice and Speech services, Data, or Any), with its NR Mode, its
    operators (by name; the default ones of the NR Mode when it took every operator or patterns), its criterion as
    conditions, the Priority of its prioritized calls and the queue of its calls (Tracked for Track only); a last tracked
    step takes the calls they leave, with the Priority the rules gave their tracked calls. The default steps are deleted;
    a Region or City of a rule has no step field (the Regions out of scope stand for them)."""
    known = {name.casefold(): name for name in STRATEGY_PRIORITY_NAMES}
    steps: dict[str, dict[str, Any]] = {step['id']: {'deleted': True} for step in strategy_steps(CUSTOM) if step['list'] == CAMPAIGN_LIST}
    rows = []
    for rule in rules:
        services = set(rule['services'])
        voice, data = bool(services & {'voice', 'speech'}), 'data' in services
        kinds = ['voice', WHATSAPP] if voice and not data else ['data'] if data and not voice else ['any']
        nr_mode = rule['nr_modes'][0] if len(rule['nr_modes']) == 1 else 'any'
        names = [value for value in rule['operators'] if not value.startswith('-') and not re.search(r'[*?]', value)]
        conditions, joins = CRITERION_CONDITIONS[rule['criterion']]
        queue = '' if rule['criterion'] == 'track' else DATA_QUEUE if kinds == ['data'] else VOICE_QUEUE
        priority = known.get(rule['priority'].casefold(), TRACKED_PRIORITY)
        rows += [(priority, nr_mode, kind, list(conditions), list(joins), queue,
                  names or list((operators or {}).get(nr_mode) or [FOCUSED_OPERATORS])) for kind in kinds]
    tracked = [known[rule['track_priority'].casefold()] for rule in rules if rule['track_priority'].casefold() in known]
    rows.append((max(set(tracked), key=tracked.count) if tracked else TRACKED_PRIORITY, 'any', 'any', [EVERY_CALL], [], '',
                 list((operators or {}).get('any') or [FOCUSED_OPERATORS])))
    for index, (priority, nr_mode, kind, conditions, joins, queue, names) in enumerate(rows[:MAX_LIST_STEPS], start=1):
        steps[f'{CAMPAIGN_LIST}-s{index}'] = {'number': index, 'priority': priority, 'nr_mode': nr_mode, 'call_type': kind, 'area': 'any',
                                              'conditions': conditions, 'joins': joins, 'queue': queue, 'operators': names}
    return steps


# ---------------------------------------------------------------------------
# Strategies: Dual Queue (Cities first), Dual Queue (Roads first) and Points Lost Based
# ---------------------------------------------------------------------------
def _default_rows(strategy: str) -> dict[str, list[tuple[Any, ...]]]:
    """The steps of the two lists of a strategy by default, in order: (Priority, NR Mode, call type, area, conditions, queue)
    and the operators between the conditions when they are not OR. List 1 of the Dual Queue strategies differs only in the
    place of SA Voice: in Cities first (P1, Connecting Roads P3) with Cities first, on Connecting Roads first with Roads
    first; their data steps take the consecutive failures of a cluster (Consecutive failures AND Cluster). List 2 is the
    same in every strategy of the application, by the impact levels: SA Voice High P1, SA Data High P2, SA Voice Medium and
    Low P3, SA WhatsApp High, Medium and Low P4, NSA Data High P5, NSA Voice P6, NSA WhatsApp P7 and the tracked calls P8.
    Points Lost Based uses it as its list 1 (alone). Vodafone Proposal (list 1 alone) puts SA before NSA and Voice before
    Data: every Voice and WhatsApp call, and the Data calls of a cluster (the others are tracked with P5)."""
    every = (EVERY_CALL,)
    final = [('P1', 'SA', 'voice', 'any', ('high',), VOICE_QUEUE), ('P2', 'SA', 'data', 'any', ('high',), DATA_QUEUE),
             ('P3', 'SA', 'voice', 'any', ('medium',), VOICE_QUEUE), ('P3', 'SA', 'voice', 'any', ('low',), VOICE_QUEUE),
             ('P4', 'SA', 'whatsapp', 'any', ('high',), VOICE_QUEUE), ('P4', 'SA', 'whatsapp', 'any', ('medium',), VOICE_QUEUE),
             ('P4', 'SA', 'whatsapp', 'any', ('low',), VOICE_QUEUE), ('P5', 'NSA', 'data', 'any', ('high',), DATA_QUEUE),
             ('P6', 'NSA', 'voice', 'any', every, VOICE_QUEUE), ('P7', 'NSA', 'whatsapp', 'any', every, VOICE_QUEUE),
             (TRACKED_PRIORITY, 'any', 'any', 'any', every, '')]
    if strategy == CUSTOM:
        return {CAMPAIGN_LIST: list(final), FINAL_LIST: final}
    if strategy == VODAFONE_PROPOSAL:
        cluster = ('repeated',)
        return {CAMPAIGN_LIST: [('P1', 'SA', 'voice', 'any', every, VOICE_QUEUE), ('P1', 'SA', 'whatsapp', 'any', every, VOICE_QUEUE),
                                ('P2', 'SA', 'data', 'any', cluster, DATA_QUEUE), ('P3', 'NSA', 'voice', 'any', every, VOICE_QUEUE),
                                ('P3', 'NSA', 'whatsapp', 'any', every, VOICE_QUEUE), ('P4', 'NSA', 'data', 'any', cluster, DATA_QUEUE),
                                ('P5', 'any', 'any', 'any', every, '')],
                FINAL_LIST: final}
    if strategy not in (CITIES_FIRST, ROADS_FIRST):
        # A strategy of the admins has only the steps they gave it.
        return {CAMPAIGN_LIST: [], FINAL_LIST: []}
    first, third = ('city', 'roads') if strategy == CITIES_FIRST else ('roads', 'city')
    data, both = ('consecutive', 'repeated'), ('and',)
    return {
        CAMPAIGN_LIST: [('P1', 'SA', 'voice', first, every, VOICE_QUEUE), ('P2', 'SA', 'data', 'any', data, DATA_QUEUE, both),
                        ('P3', 'SA', 'voice', third, every, VOICE_QUEUE), ('P4', 'SA', 'whatsapp', 'any', every, VOICE_QUEUE),
                        ('P5', 'NSA', 'data', 'any', data, DATA_QUEUE, both), ('P6', 'NSA', 'voice', 'any', every, VOICE_QUEUE),
                        ('P7', 'NSA', 'whatsapp', 'any', every, VOICE_QUEUE), (TRACKED_PRIORITY, 'any', 'any', 'any', every, '')],
        FINAL_LIST: final,
    }


def _former_rows(strategy: str, list_name: str) -> list[list[tuple[Any, ...]]]:
    """The default steps of a list of a strategy of the application before the current ones (a list saved exactly as one of
    them takes the current defaults, see ``normalize_steps``). List 1 of the Dual Queue strategies: its Data steps took
    Consecutive failures AND Hotspots, and before Consecutive failures OR Hotspots (Cities first) or Hotspots (Roads
    first). List 1 of Points Lost Based: SA before NSA and Voice before Data, its Data steps Cluster OR / AND High impact.
    List 2: ten steps, one for SA WhatsApp High OR Medium impact, and before them the Data steps of the Dual Queue
    strategies took High impact OR Cluster; Points Lost Based copied its list 1 (Cluster OR / AND High impact)."""
    every = (EVERY_CALL,)
    if strategy not in STRATEGIES or strategy == VODAFONE_PROPOSAL:
        return []
    points_lost = [('P1', 'SA', 'voice', 'any', every, VOICE_QUEUE), ('P1', 'SA', 'whatsapp', 'any', every, VOICE_QUEUE),
                   ('P2', 'SA', 'data', 'any', ('repeated', 'high'), DATA_QUEUE), ('P3', 'NSA', 'voice', 'any', every, VOICE_QUEUE),
                   ('P3', 'NSA', 'whatsapp', 'any', every, VOICE_QUEUE), ('P4', 'NSA', 'data', 'any', ('repeated', 'high'), DATA_QUEUE),
                   ('P5', 'any', 'any', 'any', every, '')]
    points_lost_and = [(*row, ('and',)) if row[4] == ('repeated', 'high') else row for row in points_lost]
    if list_name == CAMPAIGN_LIST:
        if strategy == CUSTOM:
            return [points_lost, points_lost_and]
        current = _default_rows(strategy)[CAMPAIGN_LIST]
        variants = [(('consecutive', 'cluster'), ('and',)), (('consecutive', 'cluster'), None), (('cluster',), None)]
        return [[(*row[:4], data, row[5], *([joins] if joins else [])) if row[2] == 'data' else row for row in current]
                for data, joins in variants]

    def ten(data: tuple[str, ...]) -> list[tuple[Any, ...]]:
        return [('P1', 'SA', 'voice', 'any', ('high',), VOICE_QUEUE), ('P2', 'SA', 'data', 'any', data, DATA_QUEUE),
                ('P3', 'SA', 'voice', 'any', ('medium',), VOICE_QUEUE), ('P3', 'SA', 'voice', 'any', ('low',), VOICE_QUEUE),
                ('P4', 'SA', 'whatsapp', 'any', ('high', 'medium'), VOICE_QUEUE), ('P4', 'SA', 'whatsapp', 'any', ('low',), VOICE_QUEUE),
                ('P5', 'NSA', 'data', 'any', data, DATA_QUEUE), ('P6', 'NSA', 'voice', 'any', every, VOICE_QUEUE),
                ('P7', 'NSA', 'whatsapp', 'any', every, VOICE_QUEUE), (TRACKED_PRIORITY, 'any', 'any', 'any', every, '')]
    former = [ten(('high',))]
    if strategy in (CITIES_FIRST, ROADS_FIRST):
        return [*former, ten(('high', 'repeated'))]
    return [*former, points_lost, points_lost_and]


def _saved_as_former(given: dict[str, Any], strategy: str, list_name: str) -> bool:
    """Whether the steps of a list of a strategy were saved exactly as its former defaults (``_former_rows``), no step
    deleted or added: every Save keeps every step of every strategy, so only those still follow the defaults."""
    saved = {key: step for key, step in given.items() if str(key).startswith(f'{list_name}-')}
    for rows in _former_rows(strategy, list_name):
        keys = {step_id(list_name, index, len(rows)): row for index, row in enumerate(rows, start=1)}
        if set(saved) != set(keys):
            continue
        if all(isinstance(saved[key], dict) and not saved[key].get('deleted')
               and (saved[key].get('priority'), saved[key].get('nr_mode'), saved[key].get('call_type'), saved[key].get('area'),
                    list(saved[key].get('conditions') or []), list(saved[key].get('joins') or []), saved[key].get('queue') or '')
               == (row[0], row[1], row[2], row[3], list(row[4]), joins_of(list(row[4]), list(row[6]) if len(row) > 6 else None), row[5])
               for key, row in keys.items()):
            return True
    return False


# The fields of a step the admins add, before they change them: tracked, every call.
NEW_STEP = (TRACKED_PRIORITY, 'any', 'any', 'any', (EVERY_CALL,), '')


def step_id(list_name: str, index: int, count: int) -> str:
    """The key of a step in the settings: campaign-1, final-9, and campaign-tracked / final-tracked for the last one."""
    return f'{list_name}-{"tracked" if index == count else index}'


def conditions_of(list_name: str) -> dict[str, str]:
    return CAMPAIGN_CONDITIONS if list_name == CAMPAIGN_LIST else FINAL_CONDITIONS


def joins_of(conditions: list[str], joins: Any = None) -> list[str]:
    """The operator before each condition of a step after the first: the one given (and, or), else or (the steps saved
    before the operators could be chosen took the calls that met any of their conditions)."""
    given = [str(value).lower() for value in joins] if isinstance(joins, list) else []
    return [given[index] if index < len(given) and given[index] in JOINS else 'or' for index in range(max(len(conditions) - 1, 0))]


def condition_groups(conditions: list[str], joins: Any = None) -> tuple[list[tuple[list[str], list[str]]], list[str]]:
    """The groups of the conditions of a step, each started by AND ( or OR (, with the operators (and, or) inside each
    group, and the operators between the groups."""
    groups: list[tuple[list[str], list[str]]] = [([conditions[0]], [])] if conditions else []
    between: list[str] = []
    for join, key in zip(joins_of(conditions, joins), conditions[1:]):
        if join in GROUP_JOINS:
            between.append(GROUP_JOINS[join])
            groups.append(([key], []))
        else:
            groups[-1][0].append(key)
            groups[-1][1].append(join)
    return groups, between


def _expression(conditions: list[str], joins: Any, words: dict[str, str], join_words: dict[str, str]) -> str:
    """The conditions of a step written with ``words`` and ``join_words``, the groups of several in parentheses when
    there are more groups."""
    groups, between = condition_groups(conditions, joins)
    parts = [words[keys[0]] + ''.join(f' {join_words[join]} {words[key]}' for join, key in zip(inner, keys[1:])) for keys, inner in groups]
    if len(parts) > 1:
        parts = [f'({part})' if len(keys) > 1 else part for part, (keys, _) in zip(parts, groups)]
    return parts[0] + ''.join(f' {join_words[join]} {part}' for join, part in zip(between, parts[1:]))


def step_conditions_text(conditions: list[str], joins: Any = None) -> str:
    """The conditions of a step in words: Every call, or each joined to the one before by its operator, the groups in
    parentheses ((High impact OR Medium impact) AND Repeated)."""
    if not conditions or EVERY_CALL in conditions:
        return CONDITION_LABELS[EVERY_CALL]
    return _expression(conditions, joins, CONDITION_LABELS, JOINS)


def clean_conditions(values: Any, allowed: dict[str, str], joins: Any = None) -> tuple[list[str], list[str]] | None:
    """The conditions of a step of a list in the order chosen, with the operator before each one after the first (Every
    call alone takes every call); None when one is not a condition of the list, an operator is not AND or OR, or there
    are more than MAX_CONDITIONS."""
    chosen = [str(value) for value in values or []]
    joins = list(joins) if isinstance(joins, list) else joins
    # A condition of the first versions takes the one that stands for it, once (with the operator before it).
    for index in range(len(chosen) - 1, -1, -1):
        current = FORMER_CONDITIONS.get(chosen[index], chosen[index])
        if current != chosen[index] and current in chosen:
            del chosen[index]
            if isinstance(joins, list) and joins:
                del joins[max(index - 1, 0)]
        else:
            chosen[index] = current
    if any(value not in allowed for value in chosen) or len(chosen) > MAX_CONDITIONS:
        return None
    if not chosen or EVERY_CALL in chosen:
        return [EVERY_CALL], []
    if isinstance(joins, list) and any(str(value).lower() not in JOINS for value in joins):
        return None
    return chosen, joins_of(chosen, joins)


def _step_rule(list_name: str, number: int | None, label: str) -> str:
    """The value of the Prioritization Rule field of a step: Campaign 1 · SA Voice · Cities, Final 10 · Tracked."""
    return f'{LIST_LABELS[list_name]} {number} · {label}' if number else f'{LIST_LABELS[list_name]} · {label}'


def step_label(step: dict[str, Any]) -> str:
    """What a step takes, in short: SA Voice · Cities, SA Data · Consecutive failures OR Hotspots, Tracked."""
    parts = [STEP_NR_MODES[step['nr_mode']] if step['nr_mode'] != 'any' else '',
             CALL_TYPES[step['call_type']] if step['call_type'] != 'any' else '']
    base = ' '.join(part for part in parts if part) or 'Every call'
    if step['area'] != 'any':
        base = f"{base} · {STEP_AREAS[step['area']]}"
    label = base if step['conditions'] == [EVERY_CALL] else f"{base} · {step_conditions_text(step['conditions'], step['joins'])}"
    if not step['queue']:
        return 'Tracked' if label == 'Every call' else f'Tracked · {label}'
    return label


def _current_step(chosen: dict[str, Any]) -> dict[str, Any]:
    """The fields of a step saved with a Call Type of the first version (Voice · Cities), with its type and area apart."""
    if chosen.get('call_type') not in LEGACY_CALL_TYPES:
        return chosen
    call_type, area = LEGACY_CALL_TYPES[chosen['call_type']]
    return {**chosen, 'call_type': call_type, 'area': chosen.get('area') or area}


def strategy_steps(strategy: str, configured: dict[str, Any] | None = None,
                   operators: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """The steps of the two lists of a strategy, in the order of their rows: key, list, number, Priority, NR Mode, call
    type, area, condition, queue and operators, as the admins chose them in ``configured`` (the steps of that strategy in the
    settings), else by default (Focused Operators), with their label, the value of the Prioritization Rule field and what
    they take."""
    configured = configured if isinstance(configured, dict) else {}
    steps = []
    for list_name, rows in _default_rows(strategy).items():
        # The default steps, then those the admins added (keys campaign-s1, final-s2...), at the end of the list.
        keyed = [(step_id(list_name, index, len(rows)), index, row) for index, row in enumerate(rows, start=1)]
        added = sorted((key for key in configured if ADDED_STEP.match(key) and key.startswith(f'{list_name}-')),
                       key=lambda key: int(key.rsplit('-s', 1)[1]))
        keyed += [(key, len(rows) + offset, NEW_STEP) for offset, key in enumerate(added, start=1)]
        for key, index, (priority, nr_mode, call_type, area, conditions, queue, *joins) in keyed:
            chosen = _current_step(configured[key]) if isinstance(configured.get(key), dict) else {}
            if chosen.get('deleted'):
                continue
            step = {'id': key, 'list': list_name, 'number': index, 'priority': priority, 'nr_mode': nr_mode, 'call_type': call_type,
                    'area': area, 'conditions': list(conditions), 'joins': joins_of(list(conditions), list(joins[0]) if joins else None),
                    'queue': queue, 'operators': list((operators or {}).get(nr_mode) or [FOCUSED_OPERATORS])}
            step['default'] = {name: step[name] for name in ('number', 'priority', 'nr_mode', 'call_type', 'area', 'conditions', 'joins',
                                                             'queue')}
            step['added'] = bool(ADDED_STEP.match(key))
            for name, allowed in (('priority', STRATEGY_PRIORITY_NAMES), ('nr_mode', STEP_NR_MODES), ('call_type', CALL_TYPES),
                                  ('area', STEP_AREAS), ('queue', STEP_QUEUES)):
                if chosen.get(name) in allowed:
                    step[name] = chosen[name]
            if isinstance(chosen.get('conditions'), list):
                cleaned = clean_conditions(chosen['conditions'], conditions_of(list_name), chosen.get('joins'))
                if cleaned:
                    step['conditions'], step['joins'] = cleaned
            if isinstance(chosen.get('number'), int) and 1 <= chosen['number'] <= MAX_STEP_NUMBER:
                step['number'] = chosen['number']
            if isinstance(chosen.get('operators'), list):
                step['operators'] = list(chosen['operators'])
            step['label'] = step_label(step)
            step['rule'] = _step_rule(list_name, step['number'], step['label'])
            mode = '' if step['nr_mode'] == 'any' else f"{step['nr_mode']} "
            if not step['queue'] and (step['nr_mode'], step['call_type'], step['area'], step['conditions']) == (
                    'any', 'any', 'any', [EVERY_CALL]):
                step['takes'] = 'The calls no step takes: the other data failures, the Ping tests and the Excluded Calls'
            else:
                step['takes'] = (f"{mode}{CALL_TYPE_TAKES[step['call_type']]}{AREA_TAKES[step['area']]}: "
                                 + _expression(step['conditions'], step['joins'], CONDITION_TAKES, JOIN_WORDS)
                                 + ('' if step['queue'] else ', only tracked'))
            steps.append(step)
    return steps


STEP_FIELD_LABELS = {'priority': 'Priority', 'number': 'Step', 'nr_mode': 'NR Mode', 'call_type': 'Call Type', 'area': 'Area',
                     'conditions': 'Condition', 'operators': 'Operators', 'queue': 'Queue'}


def step_field_value(step: dict[str, Any], key: str) -> Any:
    """A field of a step as compared to tell a change: the Condition with the operators between its conditions."""
    return (step['conditions'], step['joins']) if key == 'conditions' else step[key]


def step_field_text(step: dict[str, Any], key: str) -> str:
    """A field of a step in words, as the dialog shows it."""
    value = step[key]
    return {'nr_mode': lambda: STEP_NR_MODES[value], 'call_type': lambda: CALL_TYPES[value], 'area': lambda: STEP_AREAS[value],
            'conditions': lambda: step_conditions_text(value, step['joins']), 'operators': lambda: operators_text(value),
            'queue': lambda: STEP_QUEUES[value]}.get(key, lambda: str(value))()


STEP_FIELDS = ('number', 'priority', 'nr_mode', 'call_type', 'area', 'conditions', 'joins', 'queue', 'operators')


def default_steps(operators: dict[str, list[str]] | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Every field of every step of the strategies of the application by default (the operators by NR Mode from
    ``operators``, else Focused Operators)."""
    return {strategy: {step['id']: {name: step[name] for name in STEP_FIELDS} for step in strategy_steps(strategy, None, operators)}
            for strategy in STRATEGIES}


def _valid_step(step: dict[str, Any], chosen: dict[str, Any], list_name: str, strict: bool, label: str) -> dict[str, Any]:
    """The fields of a step from those chosen, valid (the given ``step`` keeps the others); ``strict`` refuses an invalid
    value."""
    step = dict(step)
    if 'priority' in chosen and str(chosen['priority'] or '').strip().upper() in STRATEGY_PRIORITY_NAMES:
        chosen = {**chosen, 'priority': str(chosen['priority']).strip().upper()}
    for name, allowed, message in (
            ('priority', STRATEGY_PRIORITY_NAMES, 'The priority of a step goes from P1 to P8'),
            ('nr_mode', STEP_NR_MODES, 'Choose the NR Mode of each step'),
            ('call_type', CALL_TYPES, 'Choose the Call Type of each step'),
            ('area', STEP_AREAS, 'Choose the Area of each step'),
            ('queue', STEP_QUEUES, 'Choose the queue of each step')):
        if name not in chosen or chosen[name] is None:
            continue
        if chosen[name] in allowed:
            step[name] = chosen[name]
        elif strict:
            raise ValueError(f'{message} ({label}).')
    if isinstance(chosen.get('conditions'), list):
        cleaned = clean_conditions(chosen['conditions'], conditions_of(list_name), chosen.get('joins'))
        if cleaned is not None:
            step['conditions'], step['joins'] = cleaned
        elif strict:
            raise ValueError(f'Choose the conditions of each step, joined by AND or OR ({label}).')
    if 'number' in chosen:
        try:
            number = int(chosen['number'])
        except (TypeError, ValueError):
            number = 0
        if 1 <= number <= MAX_STEP_NUMBER:
            step['number'] = number
        elif strict:
            raise ValueError(f'The step of a row goes from 1 to {MAX_STEP_NUMBER} ({label}).')
    if isinstance(chosen.get('operators'), list):
        values = _values(chosen['operators'])
        # Focused Operators stands alone: the other operators chosen with it are left out.
        step['operators'] = [FOCUSED_OPERATORS] if FOCUSED_OPERATORS in values else values
    return step


def normalize_steps(value: Any, strict: bool = False, operators: dict[str, list[str]] | None = None,
                    strategies: dict[str, str] | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """Every field of every step of the strategies (those of the application and those of the admins, with their labels in
    ``strategies``): its number (1 to 20), Priority (P1 to P8), NR Mode, call type, area, condition (of its list),
    queue and operators (operator names, or Focused Operators alone). A default step the admins deleted stays as deleted;
    the steps they added (campaign-s1, final-s2...) follow, at most MAX_LIST_STEPS per list. ``strict`` refuses an invalid
    value instead of keeping the default one."""
    value = value if isinstance(value, dict) else {}
    strategies = strategies or dict(STRATEGIES)
    steps: dict[str, dict[str, dict[str, Any]]] = {}
    for strategy, label in strategies.items():
        given = value.get(strategy) if isinstance(value.get(strategy), dict) else {}
        # A list saved exactly as its former defaults takes the current ones.
        for list_name in (CAMPAIGN_LIST, FINAL_LIST):
            if _saved_as_former(given, strategy, list_name):
                given = {key: step for key, step in given.items() if not str(key).startswith(f'{list_name}-')}
        defaults = {step['id']: {name: step[name] for name in STEP_FIELDS} for step in strategy_steps(strategy, None, operators)}
        result: dict[str, dict[str, Any]] = {}
        for key, step in defaults.items():
            chosen = _current_step(given[key]) if isinstance(given.get(key), dict) else {}
            result[key] = {'deleted': True} if chosen.get('deleted') else _valid_step(step, chosen, key.split('-')[0], strict, label)
        base = dict(zip(('priority', 'nr_mode', 'call_type', 'area', 'conditions', 'queue'), NEW_STEP))
        base.update(number=1, conditions=[EVERY_CALL], joins=[], operators=list((operators or {}).get('any') or [FOCUSED_OPERATORS]))
        for key, chosen in given.items():
            if key in defaults or not ADDED_STEP.match(str(key)) or not isinstance(chosen, dict) or chosen.get('deleted'):
                continue
            result[key] = _valid_step(base, _current_step(chosen), key.split('-')[0], strict, label)
        for list_name in (CAMPAIGN_LIST, FINAL_LIST):
            live = [key for key, step in result.items() if key.startswith(f'{list_name}-') and not step.get('deleted')]
            if len(live) > MAX_LIST_STEPS:
                if strict:
                    raise ValueError(f'A list has at most {MAX_LIST_STEPS} steps ({label}).')
                for key in live[MAX_LIST_STEPS:]:
                    result.pop(key)
        steps[strategy] = result
    return steps


def normalize_strategy_names(value: Any, strict: bool = False) -> dict[str, str]:
    """The names the admins gave the strategies of the application, those that differ from the default one, each strategy
    with a name of its own."""
    items = value if isinstance(value, dict) else {}
    chosen = {key: re.sub(r'\s+', ' ', str(items.get(key) or '')).strip()[:60] or default for key, default in STRATEGIES.items()}
    while True:
        seen: dict[str, str] = {}
        clash = next((key for key, name in chosen.items() if seen.setdefault(name.casefold(), key) != key), None)
        if clash is None:
            break
        if strict:
            raise ValueError(f'Give every strategy a name of its own ({chosen[clash]}).')
        # Of two strategies with one name, the renamed one takes its default name back.
        renamed = clash if chosen[clash] != STRATEGIES[clash] else seen[chosen[clash].casefold()]
        chosen[renamed] = STRATEGIES[renamed]
    return {key: name for key, name in chosen.items() if name != STRATEGIES[key]}


def normalize_strategies(value: Any, strict: bool = False, reserved: Iterable[str] = STRATEGIES.values()) -> list[dict[str, str]]:
    """The strategies the admins created: key (strategy-...) and name, once each and none with a name of ``reserved`` (the
    names of the strategies of the application), at most MAX_STRATEGIES."""
    items = value if isinstance(value, list) else []
    names = {label.casefold() for label in reserved}
    strategies: list[dict[str, str]] = []
    for item in items:
        key = str((item or {}).get('key') or '') if isinstance(item, dict) else ''
        name = re.sub(r'\s+', ' ', str((item or {}).get('name') or '') if isinstance(item, dict) else '').strip()[:60]
        if not USER_STRATEGY.match(key) or any(strategy['key'] == key for strategy in strategies):
            continue
        if not name or name.casefold() in names:
            if strict:
                raise ValueError(f'Give every strategy a name of its own ({name or "no name"}).')
            continue
        names.add(name.casefold())
        strategies.append({'key': key, 'name': name})
    if len(strategies) > MAX_STRATEGIES:
        if strict:
            raise ValueError(f'At most {MAX_STRATEGIES} strategies of your own.')
        strategies = strategies[:MAX_STRATEGIES]
    return strategies


def strategy_labels(settings: dict[str, Any]) -> dict[str, str]:
    """The name of every strategy: the three of the application (as the admins renamed them), then those of the admins."""
    return {**STRATEGIES, **(settings.get('strategy_names') or {}), **{item['key']: item['name'] for item in settings.get('strategies') or []}}


def call_kind(service: Any, test_name: Any = '', session_type: Any = '') -> str:
    """Voice, WhatsApp, Data or Ping: Speech samples are Voice calls."""
    text = f'{test_name or ""} {session_type or ""}'.casefold()
    if str(service or '').casefold() == 'data':
        return PING if 'ping' in text else DATA
    return WHATSAPP if 'whatsapp' in text else VOICE


def call_area(environment: Any) -> str:
    """Connecting Roads (roads and highways) or Cities, from the environment of the call."""
    text = str(environment or '').casefold()
    return 'roads' if 'road' in text or 'highway' in text else 'city'


def type_matches(step: dict[str, Any], call: dict[str, Any]) -> bool:
    """Whether a call is of the Call Type (Any takes the Ping tests too) and the area of a step."""
    return step['call_type'] in {'any', call['kind']} and step['area'] in {'any', call.get('area')}


def _joined(values: list[bool], joins: list[str]) -> bool:
    """Values joined by and / or, AND first: true when every value of one of the runs between the ORs is."""
    held, run = False, values[0]
    for join, value in zip(joins, values[1:]):
        if join == 'and':
            run = run and value
        else:
            held, run = held or run, value
    return held or run


def condition_holds(conditions: list[str], call: dict[str, Any], joins: Any = None) -> bool:
    """Whether a call meets the conditions of a step joined by their operators (or when not given), AND first, inside
    each group (in parentheses) and between the groups (Every call: every call). A failure is consecutive when the test
    right before or after it in the drive failed too (unknown when its CDR does not give the order of its tests)."""
    if not conditions:
        return False
    level = call.get('level')
    high, medium = level == IMPACT_HIGH, level == nq_catalog.IMPACT_MEDIUM
    result = str(call.get('result') or '').casefold()
    met = {EVERY_CALL: True, 'consecutive': call.get('consecutive') == 'Yes', 'cluster': (call.get('cluster_size') or 0) >= 2,
           'drop': 'drop' in result or 'cutoff' in result, 'setup': result == 'failed',
           'high': high, 'medium': medium, 'low': not (high or medium), 'repeated': bool(call.get('repeated'))}
    groups, between = condition_groups(conditions, joins)
    return _joined([_joined([met.get(key, False) for key in keys], inner) for keys, inner in groups], between)


def strategy_decision(strategy: str, call: dict[str, Any], steps: list[dict[str, Any]] | None = None,
                      takes: Callable[[list[str], str], bool] | None = None,
                      final_list: bool = True) -> tuple[str, str, str, str, int | None, str]:
    """(prioritization, Prioritization Rule, Priority, queue, step, list) of a call with a strategy whose ``steps`` (of
    ``strategy_steps``, the defaults when not given) have their fields; ``takes(operators, operator)`` tells whether the
    operators of a step take the operator of the call (every operator when not given). The call gives ``operator``,
    ``nr_mode`` (of its campaign), ``kind``, ``area``, ``excluded``, ``final`` (its campaign has its Final CDR scored),
    ``level`` (by its Expected Gain, see ``expected_levels``), ``repeated``, ``cluster_size``, ``consecutive`` (Yes, No or ''
    when unknown) and ``result`` (Failed, Dropped, Cutoff).

    A call out of scope (``scope``, its reason) is out of the queues. A call takes list 2 once the Final CDR of its campaign
    is scored when the strategy applies it (``final_list``), else list 1. The steps of its list are tried by Priority and
    step number. A call of an SA campaign takes the steps of SA (or Any)
    whose Call Type, Area and operators take it; when none takes its operator (an operator without SA, such as Three), those of
    NSA. The first of them whose condition the call meets decides; a call none decides, a Ping test or an Excluded Call is
    tracked by the first tracked step (without queue) that takes it, and is out of the queues otherwise."""
    if call.get('scope'):
        return NO_RULE, call['scope'], '', '', None, ''
    steps = steps or strategy_steps(strategy)
    takes = takes or (lambda operators, operator: True)
    operator = str(call.get('operator') or '')
    list_name = FINAL_LIST if call['final'] and final_list else CAMPAIGN_LIST
    rank = {name: index for index, name in enumerate(STRATEGY_PRIORITY_NAMES)}
    ordered = sorted((step for step in steps if step['list'] == list_name),
                     key=lambda step: (rank.get(step['priority'], len(rank)), step['number']))
    modes = ['SA', 'NSA'] if str(call.get('nr_mode') or '').upper() == 'SA' else ['NSA']
    if not (call['excluded'] or call['kind'] == PING):
        for mode in modes:
            candidates = [step for step in ordered if step['queue'] and step['nr_mode'] in {mode, 'any'}
                          and type_matches(step, call) and takes(step['operators'], operator)]
            if not candidates:
                continue
            for step in candidates:
                if condition_holds(step['conditions'], call, step['joins']):
                    return PRIORITIZED, step['rule'], step['priority'], step['queue'], step['number'], list_name
            modes = [mode]
            break
    for step in ordered:
        if (not step['queue'] and (step['nr_mode'] == 'any' or step['nr_mode'] in modes) and type_matches(step, call)
                and takes(step['operators'], operator) and condition_holds(step['conditions'], call, step['joins'])):
            return TRACK_ONLY, step['rule'], step['priority'], '', step['number'], list_name
    return NO_RULE, '', '', '', None, ''


def order_queue(rows: list[dict[str, Any]], priorities: list[str]) -> list[dict[str, Any]]:
    """The calls of a queue in the order the analysts take them: Priority, the newest campaign first, the step of its
    list, the highest Expected Gain first, then the oldest call (``priority`` of each row is its Priority)."""
    from src.modules.column_names import campaign_sort_key

    rank = {name.casefold(): index for index, name in enumerate(priorities)}
    ordered = sorted(rows, key=lambda row: str(row.get('start_time') or ''))
    ordered.sort(key=lambda row: -float(row['expected_points']) if row.get('expected_points') is not None else math.inf)
    ordered.sort(key=lambda row: row.get('queue_step') or 0)
    ordered.sort(key=lambda row: campaign_sort_key(str(row.get('campaign') or '')), reverse=True)
    ordered.sort(key=lambda row: rank.get(str(row.get('priority') or '').casefold(), len(rank)))
    return ordered


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


def level_group(row: Any, out_of_scope: Callable[[Any], bool] | None = None) -> tuple[str, str, str, bool]:
    """The calls whose points the level of a call compares it with: those of its campaign, operator and service, the calls
    within the scope of the team apart from those out of it (which never change the levels of the calls in scope)."""
    return (str(row['campaign_key'] or ''), str(row['operator'] or '').casefold(), str(row['service'] or ''),
            bool(out_of_scope(row)) if out_of_scope else False)


def scope_test(repository: Any, settings: dict[str, Any]) -> Callable[[Any], bool]:
    """Whether a call (its region, NR Mode and operator) is out of scope, to keep it apart in the levels."""
    reason = scope_of(repository, settings)
    return lambda row: bool(reason(row['region'], row['nr_mode'], row['operator'])[0])


def scored_levels(rows: Iterable[dict[str, Any]], high_share: float, medium_share: float,
                  out_of_scope: Callable[[Any], bool] | None = None) -> dict[str, str]:
    """The Scoring Impact level of every scored call of ``rows`` (call_key, campaign_key, operator, service, region, nr_mode,
    impact_state and impact_points, as stored): ``impact_levels`` within its ``level_group``. It needs no new calculation
    of the scoring, so a change of the High or Medium share or of the scope applies at once."""
    pareto: dict[tuple[str, str, str, bool], dict[str, float]] = {}
    for row in rows:
        if row['impact_state'] == SCORED and row['impact_points'] is not None:
            pareto.setdefault(level_group(row, out_of_scope), {})[row['call_key']] = float(row['impact_points'])
    levels: dict[str, str] = {}
    for points in pareto.values():
        levels.update(impact_levels(points, high_share, medium_share))
    return levels


def refresh_levels(repository: Any, settings: dict[str, Any]) -> int:
    """Write the Scoring Impact levels of ``scored_levels`` (the High and Medium shares of ``settings``) into the calculated
    calls (how many changed)."""
    from src.modules import non_qualified_calls as nq

    with repository.connection() as connection:
        rows = [dict(row) for row in connection.execute(
            f'SELECT p.call_key, p.campaign_key, p.impact_state, p.impact_points, p.impact_level, l.operator, l.service, '
            f'l.region, l.nr_mode FROM {PRIORITY_TABLE} p JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = p.call_key')]
        levels = scored_levels(rows, settings['high_share'], settings['medium_share'], scope_test(repository, settings))
        changes = [(levels[row['call_key']], row['call_key']) for row in rows
                   if row['call_key'] in levels and levels[row['call_key']] != row['impact_level']]
        connection.executemany(f'UPDATE {PRIORITY_TABLE} SET impact_level = ? WHERE call_key = ?', changes)
    return len(changes)


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


def campaign_losses(repository: Any, nr_mode: str, campaign: str, profiles: dict[str, Any] | None,
                    operator_mappings: dict[str, str]) -> dict[str, Any]:
    """The scoring of one campaign and NR Mode: its state and, once scored, its methodology, configuration and the points
    each test that misses a KPI holds (see ``_losses``)."""
    from src.modules.cdr_auto_selection import resolve_cdr_ids
    from src.modules.scoring_config import validate_scoring_configuration
    from src.modules.scoring_history import HistoryUnavailable, calculate_scoring_from_history, history_gap
    from src.modules.scoring_methodologies import methodology_for

    def outcome(state: str, detail: str, methodology: str = '', configuration: dict[str, Any] | None = None,
                losses: dict[tuple[str, str, str], dict[str, Any]] | None = None) -> dict[str, Any]:
        return {'state': state, 'detail': detail, 'methodology': methodology, 'configuration': configuration,
                'losses': losses or {}, 'calls': {}}

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
    return outcome(SCORED, '', profile['name'], configuration, _losses(result, configuration, campaign))


def attribute_losses(repository: Any, rows: list[dict[str, Any]], configuration: dict[str, Any],
                     losses: dict[tuple[str, str, str], dict[str, Any]], operator_mappings: dict[str, str],
                     excluded: Callable[[int, str], bool], kinds: dict[int, str]) -> dict[str, dict[str, Any]]:
    """Per call of the Non-Qualified rows (``call_key``, ``dataset_id``, ``source_row_id``, ``join_id``): the points it
    holds of the losses of a scoring (in every KPI that counts tests it misses, in the environment of the call) and those
    KPIs; Excluded when it is in a list of Scoring Excluded Calls."""
    from src.modules import scoring
    from src.modules.scoring_points_loss import counts_tests, test_weights

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
    return calls


def campaign_impact(repository: Any, nr_mode: str, campaign: str, rows: list[dict[str, Any]], profiles: dict[str, Any] | None,
                    operator_mappings: dict[str, str], excluded: Callable[[int, str], bool], kinds: dict[int, str]) -> dict[str, Any]:
    """The scoring impact of the Non-Qualified rows of one campaign and NR Mode: the state of the campaign (with its
    configuration and losses) and, per call, its points and the KPIs it loses them in."""
    outcome = campaign_losses(repository, nr_mode, campaign, profiles, operator_mappings)
    if outcome['state'] == SCORED:
        outcome['calls'] = attribute_losses(repository, rows, outcome['configuration'], outcome['losses'], operator_mappings,
                                            excluded, kinds)
    return outcome


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


def place_of(call: dict[str, Any], node_details: Callable[[dict[str, Any], tuple[str, int]], dict[str, str] | None],
             spot_meters: float) -> tuple[str, str]:
    """Where a call failed, to compare it with the others (key and label): the site of the cell where it ended (the site ID
    and host network of its eNB or gNB, ``node_details``), else the site that served its start, else the eNB or gNB of its
    last cell, else the spot where it started. A site is the same place whichever of the two gives it."""
    from src.modules.non_qualified_calls import serving_node

    node = serving_node(call.get('cell_id'))
    details = node_details(call, node) if node else None
    site, host = ((details['site'], details.get('host')) if details and details.get('site')
                  else (call.get('site_id'), call.get('host_network')))
    site, host = str(site or '').strip(), str(host or '').strip()
    if site:
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
# Data clusters, consecutive failures, Final CDRs and the Expected Gain
# ---------------------------------------------------------------------------
def _moment(value: Any) -> Any:
    from datetime import datetime

    text = str(value or '').strip().replace('T', ' ')[:19]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _meters(first: dict[str, Any], second: dict[str, Any]) -> float:
    try:
        lat1, lon1, lat2, lon2 = (float(first['latitude']), float(first['longitude']), float(second['latitude']),
                                  float(second['longitude']))
    except (TypeError, ValueError):
        return math.inf
    if not all(math.isfinite(value) for value in (lat1, lon1, lat2, lon2)):
        return math.inf
    return math.hypot((lon2 - lon1) * METERS_PER_DEGREE * math.cos(math.radians(lat1)), (lat2 - lat1) * METERS_PER_DEGREE)


def data_clusters(calls: list[dict[str, Any]], minutes: float = CLUSTER_MINUTES,
                  meters: float = CLUSTER_METERS) -> dict[str, tuple[str, int]]:
    """For every failure of one call type (``call_key``, ``operator``, ``nr_mode``, ``campaign``, ``start_time``, ``latitude``,
    ``longitude``, ``site_id``): its hotspot (cluster) and how many failures it has. A test joins the cluster of the same
    operator, NR Mode and campaign whose last test failed the same day at most ``minutes`` before it, at most ``meters``
    away or at the same site; else it starts one (a test without a date stays alone)."""
    from src.modules.cdr_auto_selection import campaign_identity

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for call in calls:
        groups.setdefault((str(call.get('operator') or '').casefold(), str(call.get('nr_mode') or '').upper(),
                           campaign_identity(call.get('campaign'))), []).append(call)
    found: dict[str, tuple[str, int]] = {}
    for members in groups.values():
        timed = sorted(((moment, call) for call in members if (moment := _moment(call.get('start_time'))) is not None),
                       key=lambda pair: (pair[0], pair[1]['call_key']))
        clusters: list[list[tuple[Any, dict[str, Any]]]] = [[(None, call)] for call in members if _moment(call.get('start_time')) is None]
        active: list[list[tuple[Any, dict[str, Any]]]] = []
        for moment, call in timed:
            active = [cluster for cluster in active if cluster[-1][0].date() == moment.date()
                      and (moment - cluster[-1][0]).total_seconds() <= minutes * 60]
            site = str(call.get('site_id') or '').strip().casefold()
            target = next((cluster for cluster in active if _meters(cluster[-1][1], call) <= meters
                           or (site and site == str(cluster[-1][1].get('site_id') or '').strip().casefold())), None)
            if target is None:
                target = []
                active.append(target)
                clusters.append(target)
            target.append((moment, call))
        for cluster in clusters:
            key = f'cluster:{cluster[0][1]["call_key"]}'
            found.update({call['call_key']: (key, len(cluster)) for _moment_, call in cluster})
    return found


_places_cache: dict[str, tuple[Any, dict[str, dict[str, Any]]]] = {}


def place_values(repository: Any, settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The place, repetitions and hotspot of every calculated call with the cluster and hotspot settings given, from the
    stored values: the stored place of a call with a site or an eNB / gNB, else its spot of the Cluster distance
    (``spot_meters``); the calls of its operator at its place in its quarter and the ``previous_quarters`` before it (a
    cluster, Repeated Issue, from ``min_calls``); its hotspot of ``hotspot_minutes`` and ``hotspot_meters`` among the
    failures of its call type. The latest result is kept for each workspace until the settings or the calculation change."""
    from src.modules import non_qualified_calls as nq

    ensure_tables(repository)
    key = (tuple(settings[name] for name in PLACE_SETTINGS), repository.get_workspace_state(SUMMARY_STATE_KEY),
           repository.get_workspace_state(nq.LATEST_STATE_KEY))
    workspace = _workspace_key(repository.db_path)
    cached = _places_cache.get(workspace)
    if cached and cached[0] == key:
        return cached[1]
    with repository.connection() as connection:
        calls = [dict(row) for row in connection.execute(
            f'SELECT l.call_key, l.service, l.nr_mode, l.campaign, l.operator, l.site_id, l.latitude, l.longitude, l.start_time, '
            f'l.test_name, l.session_type, p.place_key, p.place_label FROM {PRIORITY_TABLE} p '
            f'JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = p.call_key')]
    for call in calls:
        # Only the place of a call without a site or a node depends on the settings.
        if not call['place_key'] or str(call['place_key']).startswith('spot:'):
            call['place_key'], call['place_label'] = spot_of(call['latitude'], call['longitude'], settings['spot_meters']) or ('', '')
        call['quarter'] = quarter_of(call['start_time'], call['campaign'])
        call['campaign_label'] = f"{call['campaign']}|{call['nr_mode']}"
    repeated = repetitions(calls, settings['previous_quarters'])
    kinds_of = {call['call_key']: call_kind(call['service'], call.get('test_name'), call.get('session_type')) for call in calls}
    clusters: dict[str, tuple[str, int]] = {}
    for kind in (VOICE, WHATSAPP, DATA):
        clusters.update(data_clusters([call for call in calls if kinds_of[call['call_key']] == kind], settings['hotspot_minutes'],
                                      settings['hotspot_meters']))
    values = {}
    for call in calls:
        count, campaigns_count = repeated.get(call['call_key'], (None, None))
        cluster_key, cluster_size = clusters.get(call['call_key'], ('', None))
        values[call['call_key']] = {
            'place_key': call['place_key'], 'place_label': call['place_label'], 'repetitions': count, 'repeated_campaigns': campaigns_count,
            'repeated': 'Yes' if count is not None and count >= settings['min_calls'] else 'No',
            'cluster_key': cluster_key, 'cluster_size': cluster_size}
    _places_cache[workspace] = (key, values)
    return values


def refresh_places(repository: Any, settings: dict[str, Any]) -> int:
    """Write the places, repetitions and hotspots of ``place_values`` into the calculated calls (how many changed)."""
    values = place_values(repository, settings)
    fields = ('place_key', 'place_label', 'repetitions', 'repeated_campaigns', 'repeated', 'cluster_key', 'cluster_size')
    with repository.connection() as connection:
        stored = {row['call_key']: tuple(row[name] for name in fields) for row in connection.execute(
            f"SELECT call_key, {', '.join(fields)} FROM {PRIORITY_TABLE}")}
        changes = [(*(value[name] for name in fields), key) for key, value in values.items()
                   if key in stored and stored[key] != tuple(value[name] for name in fields)]
        connection.executemany(f"UPDATE {PRIORITY_TABLE} SET {', '.join(f'{name} = ?' for name in fields)} WHERE call_key = ?", changes)
    return len(changes)


def consecutive_failures(repository: Any, calls: list[dict[str, Any]]) -> dict[str, str]:
    """For every failure (calls and data tests, Ping tests too): Yes when the test right before or after it in the drive
    failed too (the previous or next sequence number of the same file of its CDR is another of these failures), No when
    neither did, '' when its CDR does not give the order of its tests."""
    from src.modules.column_names import resolve_column_name

    positions: dict[str, tuple[int, str, int]] = {}
    by_dataset: dict[int, list[dict[str, Any]]] = {}
    for call in calls:
        by_dataset.setdefault(int(call['dataset_id']), []).append(call)
    for dataset_id, items in by_dataset.items():
        try:
            available = repository.list_dataset_row_columns(dataset_id)
        except Exception:  # noqa: BLE001 - a CDR that cannot be read gives no order.
            continue
        file_column = next((name for name in (resolve_column_name(available, column) for column in FILE_COLUMNS) if name), None)
        sequence_column = next((name for name in (resolve_column_name(available, column) for column in SEQUENCE_COLUMNS) if name), None)
        if not file_column or not sequence_column:
            continue
        table = repository.dataset_rows_table_name(dataset_id)
        keys = {int(item['source_row_id']): item['call_key'] for item in items}
        ids = list(keys)
        with repository.connection() as connection:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                for row in connection.execute(
                        f'SELECT rowid, "{file_column.replace(chr(34), chr(34) * 2)}", "{sequence_column.replace(chr(34), chr(34) * 2)}" '
                        f'FROM "{table}" WHERE rowid IN ({", ".join("?" for _ in chunk)})', chunk):
                    try:
                        positions[keys[int(row[0])]] = (dataset_id, str(row[1] or '').strip(), int(float(row[2])))
                    except (TypeError, ValueError, KeyError):
                        continue
    failed = set(positions.values())
    found: dict[str, str] = {}
    for call in calls:
        place = positions.get(call['call_key'])
        if place is None:
            found[call['call_key']] = ''
            continue
        dataset_id, file_id, sequence = place
        found[call['call_key']] = 'Yes' if {(dataset_id, file_id, sequence - 1), (dataset_id, file_id, sequence + 1)} & failed else 'No'
    return found


def final_campaigns(repository: Any) -> dict[tuple[str, str], set[str]]:
    """The campaigns with their Final CDR in the combined CDR tables, by (NR Mode, campaign identity): the CDR types
    (data, voice, speech) whose Final CDR is there ('' NR Mode when the CDR does not tell it)."""
    from src.modules.cdr_auto_selection import campaign_identity
    from src.modules.cdr_stage import combined_inclusion

    found: dict[tuple[str, str], set[str]] = {}
    for item in combined_inclusion(repository).values():
        if item.get('stage') == 'final' and item.get('included'):
            for campaign in item.get('campaigns') or []:
                found.setdefault((str(item.get('nr_mode') or '').upper(), campaign_identity(campaign)), set()).add(str(item['kind']))
    return found


def has_final(finals: dict[tuple[str, str], set[str]], nr_mode: str, identity: str, kind: str | None = None) -> bool:
    """Whether a campaign of an NR Mode has its Final CDR (of a CDR type, or of any)."""
    kinds = finals.get((nr_mode, identity), set()) | finals.get(('', identity), set())
    return bool(kinds) if kind is None else kind in kinds


def previous_final_campaign(finals: dict[tuple[str, str], set[str]], labels: dict[tuple[str, str], str], nr_mode: str,
                            campaign: str) -> str:
    """The latest campaign of an NR Mode before ``campaign`` with its Final CDR ('' when there is none)."""
    from src.modules.cdr_auto_selection import campaign_identity
    from src.modules.column_names import campaign_sort_key

    order = campaign_sort_key(campaign)
    if order[0] <= 0:
        return ''
    candidates = [labels.get((mode, identity), identity) for mode, identity in finals
                  if mode in {nr_mode, ''} and identity != campaign_identity(campaign)]
    earlier = [label for label in candidates if campaign_sort_key(label)[0] > 0 and campaign_sort_key(label)[:2] < order[:2]]
    return max(earlier, key=campaign_sort_key) if earlier else ''


# ---------------------------------------------------------------------------
# The calculation
# ---------------------------------------------------------------------------
def ensure_tables(repository: Any) -> None:
    with repository.connection() as connection:
        ensure_columns(connection)


def fingerprint(repository: Any) -> str:
    """What the impact and the repetitions depend on: the calls and CDRs indexed, the Scoring History, the methodologies,
    the Operator Maps, the Excluded Calls, the cell mappings and inventory cells with the Serving Networks (the levels of
    the impact and the settings of the clusters and the hotspots apply at once, see ``refresh_levels`` and
    ``refresh_places``)."""
    from src.modules import non_qualified_calls as nq
    from src.modules.repository import SCORING_CONFIGURATION_STATE_KEY
    from src.modules.serving_cells import SERVING_NETWORKS_STATE_KEY

    with repository.connection() as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

        def rows(sql: str, table: str) -> list[tuple[Any, ...]]:
            return [tuple(row) for row in connection.execute(sql)] if table in tables else []

        history = rows('SELECT source_key, indexed_at FROM scoring_history_sources ORDER BY source_key', 'scoring_history_sources')
        lists = rows('SELECT id, enabled, content_hash, cdrs_json FROM scoring_exclusion_lists ORDER BY id', 'scoring_exclusion_lists')
        matches = rows('SELECT list_id, dataset_id, revision, keys_hash FROM scoring_exclusion_matches ORDER BY list_id, dataset_id',
                       'scoring_exclusion_matches')
        # The sites of the eNB and gNB come from the inventory cells, in the networks that serve each operator.
        inventories = rows('SELECT dataset_id, version, revision FROM inventory_snapshots ORDER BY dataset_id', 'inventory_snapshots')
    def field(row: Any, key: str) -> str:
        try:
            return str(row[key] or '')
        except (KeyError, IndexError):
            return ''
    # The stage of each CDR and whether the combined CDR tables include it decide when a campaign has its Final CDR.
    datasets = sorted((int(row['id']), str(row['dataset_kind'] or ''), str(row['status'] or ''), str(row['nr_mode'] or ''),
                       str(row['processed_at'] or ''), str(row['updated_at'] or ''), field(row, 'cdr_stage'),
                       field(row, 'in_combined')) for row in repository.list_datasets())
    payload = [IMPACT_VERSION, repository.get_workspace_state(nq.LATEST_STATE_KEY), history, lists, matches, datasets,
               repository.get_workspace_state(SCORING_CONFIGURATION_STATE_KEY), repository.list_operator_mappings(),
               inventories, repository.get_workspace_state(SERVING_NETWORKS_STATE_KEY)]
    return hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _latest_calls(repository: Any) -> list[dict[str, Any]]:
    from src.modules import non_qualified_calls as nq

    with repository.connection() as connection:
        return [dict(row) for row in connection.execute(
            f'SELECT call_key, dataset_id, source_row_id, service, nr_mode, campaign, operator, region, city, site_id, '
            f'host_network, cell_id, latitude, longitude, start_time, join_id, test_name, session_type '
            f"FROM {nq.NQ_CALL_LATEST_TABLE} WHERE version_state <> 'qualified'")]


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


def _node_lookup(repository: Any) -> Callable[[dict[str, Any], tuple[str, int]], dict[str, str] | None]:
    """The site, host network and vendor of the eNB or gNB of a call, from the inventory cells of the workspace: in the
    networks allowed to serve its operator, within the maximum serving distance of the call."""
    from src.modules import non_qualified_calls as nq

    return nq.node_site_lookup(repository)


def calculate(repository: Any, progress: Callable[[int, int, str], None] | None = None, *,
              username: str = SYSTEM_USER) -> dict[str, Any]:
    """Calculate the scoring impact and the repetitions of every Non-Qualified Call, then apply the rules."""
    from src.modules import non_qualified_calls as nq
    from src.modules.cdr_auto_selection import campaign_identity

    started = time.monotonic()
    nq.ensure_nq_tables(repository)
    nq.refresh_latest_calls(repository)
    settings = load_settings(repository)
    stamp = fingerprint(repository)
    # The operators excluded in the Operator Maps are left out of every count: their calls get no values.
    excluded_operators = excluded_names(repository)
    calls = [call for call in _latest_calls(repository) if str(call['operator'] or '').strip().casefold() not in excluded_operators]
    kept = {call['call_key'] for call in calls}
    rows = [row for row in _call_rows(repository) if row['call_key'] in kept]
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
    outcomes: dict[tuple[str, str], dict[str, Any]] = {}
    campaigns = []
    now = nq.now_iso()
    for index, ((nr_mode, identity), group) in enumerate(sorted(groups.items(), key=lambda item: item[0]), start=1):
        if progress:
            progress(index - 1, len(groups), f"the scoring impact of {group['campaign'] or 'the calls without campaign'} {nr_mode}".rstrip())
        group_rows = [row for key in group['keys'] for row in rows_by_key.get(key, [])]
        outcome = campaign_impact(repository, nr_mode, group['campaign'], group_rows, profiles, mappings, excluded, kinds)
        outcomes[(nr_mode, identity)] = outcome
        campaign_key = f'{nr_mode}|{identity}'
        for key in group['keys']:
            impacts[key] = {**outcome['calls'].get(key, {'state': outcome['state'], 'points': 0.0, 'kpis': []}),
                            'campaign_key': campaign_key}
            if outcome['state'] != SCORED:
                impacts[key]['state'] = outcome['state']
        scored = [impacts[key] for key in group['keys'] if impacts[key]['state'] == SCORED]
        campaigns.append((campaign_key, nr_mode, group['campaign'], outcome['state'], outcome['detail'], outcome['methodology'],
                          len(group['keys']), round(sum(item['points'] for item in scored), 4), now))
    # The level of each call within its campaign, operator and service, the calls in scope apart from those out of it.
    by_call = {call['call_key']: call for call in calls}
    levels = scored_levels(({'call_key': key, 'campaign_key': impact['campaign_key'], 'impact_state': impact['state'],
                             'impact_points': impact['points'], **{name: by_call[key][name] for name in ('operator', 'service', 'region', 'nr_mode')}}
                            for key, impact in impacts.items()), settings['high_share'], settings['medium_share'],
                           scope_test(repository, settings))
    # Where each call failed, and the calls of its operator at the same place.
    if progress:
        progress(len(groups), len(groups) + 1, 'the repetitions of the calls')
    lookup = _node_lookup(repository)
    for call in calls:
        call['place_key'], call['place_label'] = place_of(call, lookup, settings['spot_meters'])
        call['quarter'] = quarter_of(call['start_time'], call['campaign'])
        call['campaign_label'] = f"{call['campaign']}|{call['nr_mode']}"
    repeated = repetitions(calls, settings['previous_quarters'])
    # The hotspots of each call type, and the failures whose test right before or after failed too.
    if progress:
        progress(len(groups), len(groups) + 1, 'the hotspots and the expected gain of the calls')
    kinds_of = {call['call_key']: call_kind(call['service'], call.get('test_name'), call.get('session_type')) for call in calls}
    clusters: dict[str, tuple[str, int]] = {}
    for kind in (VOICE, WHATSAPP, DATA):
        clusters.update(data_clusters([call for call in calls if kinds_of[call['call_key']] == kind], settings['hotspot_minutes'],
                                      settings['hotspot_meters']))
    consecutive = consecutive_failures(repository, calls)
    # Whether the Final CDR of the campaign of each call is scored (list 2 then orders it), and its Expected Gain: its
    # own points then, else what its failure lost in the latest campaign of its NR Mode with a Final CDR.
    finals = final_campaigns(repository)
    labels = {key: group['campaign'] for key, group in groups.items()}
    previous_outcomes: dict[str, dict[str, Any]] = {}
    final_list: dict[str, int] = {}
    expected: dict[str, tuple[float | None, str]] = {}
    for (nr_mode, identity), group in groups.items():
        outcome = outcomes[(nr_mode, identity)]
        estimates: dict[str, dict[str, Any]] = {}
        source = ''
        waiting = [key for key in group['keys']
                   if not (outcome['state'] == SCORED and has_final(finals, nr_mode, identity, kinds.get(int(by_call[key]['dataset_id']))))]
        previous = previous_final_campaign(finals, labels, nr_mode, group['campaign']) if waiting else ''
        if previous:
            if previous not in previous_outcomes:
                known = outcomes.get((nr_mode, campaign_identity(previous)))
                previous_outcomes[previous] = known if known is not None else campaign_losses(repository, nr_mode, previous, profiles, mappings)
            before = previous_outcomes[previous]
            if before['state'] == SCORED:
                source = previous
                estimates = attribute_losses(repository, [row for key in waiting for row in rows_by_key.get(key, [])],
                                             before['configuration'], before['losses'], mappings, excluded, kinds)
        waiting_keys = set(waiting)
        for key in group['keys']:
            impact = impacts[key]
            if key not in waiting_keys:
                final_list[key] = 1
                expected[key] = (impact['points'], group['campaign'])
            elif key in estimates and estimates[key]['state'] == SCORED:
                expected[key] = (estimates[key]['points'], source)
    values = []
    for call in calls:
        impact = impacts.get(call['call_key'], {'state': NOT_SCORED, 'points': 0.0, 'kpis': [], 'campaign_key': ''})
        state = impact['state']
        count, campaigns_count = repeated.get(call['call_key'], (None, None))
        cluster_key, cluster_size = clusters.get(call['call_key'], ('', None))
        gain, gain_campaign = expected.get(call['call_key'], (None, ''))
        values.append((
            call['call_key'], impact['campaign_key'], state, impact['points'] if state in {SCORED, EXCLUDED} else None,
            levels.get(call['call_key'], nq_catalog.IMPACT_NONE) if state == SCORED else LEVEL_OF_STATE[state],
            kpis_text(impact['kpis']) if state == SCORED else '', json.dumps(impact['kpis'] if state == SCORED else [], ensure_ascii=False),
            call['place_key'], call['place_label'], count, campaigns_count,
            ('Yes' if count is not None and count >= settings['min_calls'] else 'No'), now,
            cluster_key, cluster_size, consecutive.get(call['call_key'], ''), final_list.get(call['call_key'], 0),
            None if gain is None else round(float(gain), 4), gain_campaign,
        ))
    ensure_tables(repository)
    with repository.connection() as connection:
        connection.executemany(
            f'INSERT INTO {PRIORITY_TABLE} (call_key, campaign_key, impact_state, impact_points, impact_level, impact_kpis, '
            'impact_json, place_key, place_label, repetitions, repeated_campaigns, repeated, updated_at, cluster_key, '
            'cluster_size, consecutive, final_list, expected_points, expected_campaign) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(call_key) DO UPDATE SET '
            'campaign_key = excluded.campaign_key, impact_state = excluded.impact_state, impact_points = excluded.impact_points, '
            'impact_level = excluded.impact_level, impact_kpis = excluded.impact_kpis, impact_json = excluded.impact_json, '
            'place_key = excluded.place_key, place_label = excluded.place_label, repetitions = excluded.repetitions, '
            'repeated_campaigns = excluded.repeated_campaigns, repeated = excluded.repeated, updated_at = excluded.updated_at, '
            'cluster_key = excluded.cluster_key, cluster_size = excluded.cluster_size, consecutive = excluded.consecutive, '
            'final_list = excluded.final_list, expected_points = excluded.expected_points, '
            'expected_campaign = excluded.expected_campaign',
            values)
        connection.execute(f'DELETE FROM {PRIORITY_TABLE} WHERE call_key NOT IN (SELECT value FROM json_each(?))',
                           (json.dumps([call['call_key'] for call in calls]),))
        connection.execute(f'DELETE FROM {PRIORITY_CAMPAIGNS_TABLE}')
        connection.executemany(
            f'INSERT INTO {PRIORITY_CAMPAIGNS_TABLE} (campaign_key, nr_mode, campaign, state, detail, methodology, calls, points, '
            'calculated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', campaigns)
    applied = apply_rules(repository, username, settings)
    summary = {
        'calculated_at': now, 'seconds': round(time.monotonic() - started, 1), 'calls': len(calls), 'version': IMPACT_VERSION,
        'campaigns': len(campaigns), 'scored': sum(1 for item in impacts.values() if item['state'] == SCORED),
        'pending': sum(1 for item in impacts.values() if item['state'] == PENDING),
        'repeated': sum(1 for value in values if value[11] == 'Yes'), **applied,
    }
    repository.set_workspace_state(FINGERPRINT_STATE_KEY, stamp)
    repository.set_workspace_state(SUMMARY_STATE_KEY, json.dumps(summary))
    if hasattr(repository, 'try_add_log'):
        repository.try_add_log(username, 'nq_prioritization_calculated', json.dumps(summary))
    return summary


def _operator_aliases(repository: Any) -> dict[str, set[str]]:
    """Every name (casefolded) of the Operator Maps with every name of its label."""
    try:
        groups = repository.list_operator_mapping_groups()
    except Exception:  # noqa: BLE001 - without Operator Maps, a label only stands for itself.
        groups = []
    aliases: dict[str, set[str]] = {}
    for group in groups or []:
        names = {str(name or '').strip().casefold() for name in [group.get('canonical'), *(group.get('aliases') or [])]}
        names.discard('')
        for name in names:
            aliases.setdefault(name, set()).update(names)
    return aliases


def operators_with_sa(rows: Iterable[tuple[Any, ...]], aliases: dict[str, set[str]] | None = None,
                      share: float = SA_SHARE) -> set[str] | None:
    """The names (casefolded, with every name of their label) of the operators that use SA, from the (operator,
    technology[, calls]) of the Non-Qualified Calls of the SA campaigns: at least ``share`` of the calls of the label ran on
    NR SA (NR SA, NE-DC). None when no call gives its technology (every operator then counts)."""
    aliases = aliases or {}
    counts: dict[frozenset[str], list[int]] = {}
    known = False
    for operator, technology, *calls in rows:
        name = str(operator or '').strip().casefold()
        if not name:
            continue
        text = str(technology or '').strip()
        known = known or bool(text)
        weight = int(calls[0]) if calls else 1
        item = counts.setdefault(frozenset(aliases.get(name, {name})), [0, 0])
        item[0] += weight
        item[1] += weight if SA_TECHNOLOGY.search(text) else 0
    if not known:
        return None
    return {name for names, (total, sa) in counts.items() if sa >= share * total for name in names}


def _operator_counts(repository: Any) -> list[tuple[Any, ...]]:
    """(operator, technology, NR Mode, calls) of the Non-Qualified Calls, but those of the operators excluded in the
    Operator Maps."""
    from src.modules import non_qualified_calls as nq

    excluded = excluded_names(repository)
    with repository.connection() as connection:
        try:
            rows = [tuple(row) for row in connection.execute(f'SELECT operator, technology, nr_mode, COUNT(*) FROM {nq.NQ_CALL_LATEST_TABLE} '
                                                             'GROUP BY operator, technology, nr_mode')]
        except Exception:  # noqa: BLE001 - before the calls are indexed.
            return []
    return [row for row in rows if str(row[0] or '').strip().casefold() not in excluded]


def operators_using_sa(repository: Any, rows: list[tuple[Any, ...]] | None = None) -> set[str] | None:
    """The names (casefolded) of the operators that use SA (``operators_with_sa`` on the calls of the SA campaigns of the
    workspace); None when the calls do not give their technology."""
    rows = _operator_counts(repository) if rows is None else rows
    return operators_with_sa([(row[0], row[1], row[3]) for row in rows if str(row[2] or '').upper() == 'SA'], _operator_aliases(repository))


def operator_label(repository: Any) -> Callable[[Any], str]:
    """The label of the Operator Maps that a name of the CDRs stands for (the name itself when it has none)."""
    try:
        groups = repository.list_operator_mapping_groups()
    except Exception:  # noqa: BLE001 - without Operator Maps, a name stands for itself.
        groups = []
    labels: dict[str, str] = {}
    for group in groups or []:
        canonical = str(group.get('canonical') or '').strip()
        for name in [canonical, *(group.get('aliases') or [])] if canonical else []:
            if str(name or '').strip():
                labels.setdefault(str(name).strip().casefold(), canonical)
    return lambda name: labels.get(str(name or '').strip().casefold(), str(name or '').strip())


def excluded_names(repository: Any) -> set[str]:
    """Every name (casefolded) of the operators excluded in the Operator Maps (left out everywhere)."""
    from src.modules.operator_roles import EXCLUDE, names_with_role

    return {name.casefold() for name in names_with_role(repository, EXCLUDE)}


def focus_names(repository: Any) -> set[str] | None:
    """Every name (casefolded) of the Focus operators of the Operator Maps; None when the workspace has none."""
    from src.modules.operator_roles import FOCUS, names_with_role

    return {name.casefold() for name in names_with_role(repository, FOCUS)} or None


# Why the pairs of an operator that is not a Focus operator are out of scope, as the dialog tells it.
NOT_FOCUS_REASON = 'Not a Focus operator of the Operator Maps: its calls of both NR Modes are always out of scope'


def fixed_excluded_modes(repository: Any) -> list[dict[str, str]]:
    """The NR Mode and operator pairs always out of scope, in every strategy: SA and NSA with every operator that is not a
    Focus operator of the Operator Maps (by its label, or its name in the CDRs when it has none); none when the workspace
    has no Focus operator; the operators excluded in the Operator Maps are left out."""
    focus = focus_names(repository)
    if focus is None:
        return []
    label = operator_label(repository)
    excluded = excluded_names(repository)
    names: dict[str, str] = {}
    for name in [*operator_choices(repository), *(row[0] for row in _operator_counts(repository))]:
        text = str(name or '').strip()
        if text and text.casefold() not in excluded and text.casefold() not in focus:
            names.setdefault(label(text).casefold(), label(text))
    return [{'nr_mode': mode, 'operator': name} for name in sorted(names.values(), key=str.casefold) for mode in ('SA', 'NSA')]


def default_excluded_modes(repository: Any) -> list[dict[str, str]]:
    """The NR Mode and operator pairs out of scope until the admins choose others: SA with each Focus operator of the SA
    campaigns that does not use SA (Three: its calls there are NSA calls, which its NSA campaigns already have), by its
    label in the Operator Maps (the other operators are always out of scope, see ``fixed_excluded_modes``, and those excluded
    in the Operator Maps are left out)."""
    rows = _operator_counts(repository)
    with_sa = operators_using_sa(repository, rows)
    if with_sa is None:
        return []
    focus = focus_names(repository)
    label = operator_label(repository)
    excluded = excluded_names(repository)
    found: dict[str, str] = {}
    for operator, _technology, nr_mode, _calls in rows:
        name = str(operator or '').strip()
        if (str(nr_mode or '').upper() != 'SA' or not name or name.casefold() in with_sa or name.casefold() in excluded
                or (focus is not None and name.casefold() not in focus)):
            continue
        found.setdefault(label(name).casefold(), label(name))
    return [{'nr_mode': 'SA', 'operator': name} for name in sorted(found.values(), key=str.casefold)]


def excluded_modes_of(repository: Any, settings: dict[str, Any]) -> dict[tuple[str, str], str]:
    """The NR Mode and operator pairs out of scope chosen by the admins, by NR Mode and every name of the operator in the
    Operator Maps (casefolded): their label (SA · Three)."""
    aliases = _operator_aliases(repository)
    return {(item['nr_mode'], name): f"{item['nr_mode']} · {item['operator']}" for item in settings['excluded_modes']
            for name in aliases.get(item['operator'].casefold(), {item['operator'].casefold()})}


def scope_of(repository: Any, settings: dict[str, Any]) -> Callable[[Any, Any, Any], tuple[str, str]]:
    """Why a call (region, NR Mode, operator) is out of the queues of every strategy, and its kind (('', '') when it is in
    scope): its region (Vendor B, 'region'), its operator, not a Focus operator of the Operator Maps (both NR Modes,
    always, 'operator'), or its NR Mode and operator chosen by the admins (SA · Three, 'mode')."""
    regions = {name.casefold() for name in settings['excluded_regions']}
    chosen = excluded_modes_of(repository, settings)
    focus = focus_names(repository)
    label = operator_label(repository)

    def reason(region: Any, nr_mode: Any, operator: Any) -> tuple[str, str]:
        if str(region or '').strip().casefold() in regions:
            return f'{OUT_OF_SCOPE} · {str(region).strip()}', 'region'
        mode, name = str(nr_mode or '').upper(), str(operator or '').strip()
        if focus is not None and name.casefold() not in focus:
            return ' · '.join(part for part in (OUT_OF_SCOPE, mode, label(name)) if part), 'operator'
        found = chosen.get((mode, name.casefold()))
        return (f'{OUT_OF_SCOPE} · {found}', 'mode') if found else ('', '')
    return reason


def region_choices(repository: Any) -> list[str]:
    """The regions of the Non-Qualified Calls (but those of the operators excluded in the Operator Maps), for the regions
    out of scope."""
    from src.modules import non_qualified_calls as nq

    excluded = excluded_names(repository)
    with repository.connection() as connection:
        try:
            rows = connection.execute(f"SELECT DISTINCT region, operator FROM {nq.NQ_CALL_LATEST_TABLE} WHERE region <> ''").fetchall()
        except Exception:  # noqa: BLE001 - before the calls are indexed.
            return []
    regions = {str(row[0]) for row in rows if str(row[1] or '').strip().casefold() not in excluded}
    return sorted(regions, key=str.casefold)


def default_step_operators(repository: Any) -> dict[str, list[str]]:
    """The operators each step takes by default, by its NR Mode, by name: the NSA and tracked steps the Focus operators of
    the Operator Maps with Non-Qualified Calls (VF & Three), the SA steps those of them that use SA (VF). Focused Operators
    when the workspace has no Focus operator."""
    from src.modules.operator_roles import FOCUS, labels_with_role

    labels = labels_with_role(repository, FOCUS)
    if not labels:
        return {mode: [FOCUSED_OPERATORS] for mode in STEP_NR_MODES}
    aliases = _operator_aliases(repository)
    rows = _operator_counts(repository)

    def names(label: str) -> set[str]:
        return aliases.get(label.casefold(), {label.casefold()})
    present = {str(row[0] or '').strip().casefold() for row in rows}
    called = [label for label in labels if names(label) & present] or labels
    with_sa = operators_using_sa(repository, rows)
    sa = called if with_sa is None else [label for label in called if names(label) & with_sa]
    return {'SA': sa, 'NSA': called, 'any': called}


def operator_takes(repository: Any) -> Callable[[list[str], str], bool]:
    """Whether the operators of a step take an operator: the operators chosen (with every name of the CDRs each label of
    the Operator Maps stands for) and, with Focused Operators, the Focus operators of the Operator Maps (every operator
    when the workspace has none)."""
    from src.modules.operator_roles import FOCUS, names_with_role

    focus = {name.casefold() for name in names_with_role(repository, FOCUS)}
    aliases = _operator_aliases(repository)
    cache: dict[tuple[str, ...], set[str] | None] = {}

    def takes(operators: list[str], operator: str) -> bool:
        key = tuple(operators)
        if key not in cache:
            chosen: set[str] = set()
            every = False
            for value in operators:
                if value == FOCUSED_OPERATORS:
                    every = every or not focus
                    chosen |= focus
                else:
                    name = str(value).strip().casefold()
                    chosen |= aliases.get(name, {name})
            cache[key] = None if every else chosen
        names = cache[key]
        return names is None or operator.strip().casefold() in names
    return takes


def operators_text(operators: list[str]) -> str:
    """The operators of a step in words, as the dialog shows them: Focused Operators, or VF & Three."""
    return ' & '.join(FOCUSED_LABEL if value == FOCUSED_OPERATORS else value for value in operators) or 'No operator'


def operator_choices(repository: Any) -> list[str]:
    """The operators a step can take: the labels of the Operator Maps but the excluded ones, else the operators of the
    Non-Qualified Calls."""
    from src.modules import non_qualified_calls as nq
    from src.modules.operator_roles import EXCLUDE, labels_with_role

    excluded = {name.casefold() for name in labels_with_role(repository, EXCLUDE)}
    try:
        groups = repository.list_operator_mapping_groups()
    except Exception:  # noqa: BLE001 - without Operator Maps, the operators of the calls.
        groups = []
    labels = [str(group.get('canonical') or '').strip() for group in groups or []]
    labels = [label for label in labels if label and label.casefold() not in excluded]
    if labels:
        return labels
    with repository.connection() as connection:
        try:
            return [str(row[0]) for row in connection.execute(
                f"SELECT DISTINCT operator FROM {nq.NQ_CALL_LATEST_TABLE} WHERE operator <> '' ORDER BY operator COLLATE NOCASE")]
        except Exception:  # noqa: BLE001 - before the calls are indexed.
            return []


def expected_levels(rows: Iterable[Any], high_share: float, medium_share: float,
                    out_of_scope: Callable[[Any], bool] | None = None) -> dict[str, str]:
    """The impact level the conditions of the strategies read for every call of ``rows`` (call_key, campaign_key, operator,
    service, region, nr_mode, impact_state and expected_points): ``impact_levels`` of the Expected Gain of the calls of its
    ``level_group``. During a campaign the Expected Gain is what the failure lost in the latest Final CDR of its NR Mode;
    once the Final CDR of its campaign is scored, its own points. The Excluded Calls and the calls without Expected Gain
    have no level."""
    pareto: dict[tuple[str, str, str, bool], dict[str, float]] = {}
    for row in rows:
        value = row['expected_points']
        if value is not None and row['impact_state'] != EXCLUDED:
            pareto.setdefault(level_group(row, out_of_scope), {})[str(row['call_key'])] = float(value)
    levels: dict[str, str] = {}
    for points in pareto.values():
        levels.update(impact_levels(points, high_share, medium_share))
    return levels


def apply_rules(repository: Any, username: str, settings: dict[str, Any] | None = None) -> dict[str, int]:
    """Apply the strategy (its steps) to every calculated call and fill the Priority of the open calls with the priority of
    their step while it is empty or still the one they gave (a priority chosen by hand stays, and they stop changing it);
    the Priority of a call whose analysis started never changes."""
    from src.modules import non_qualified_calls as nq

    settings = settings or load_settings(repository)
    ensure_tables(repository)
    options = nq.list_options(repository)
    closed = {item['name'].casefold() for item in options['statuses'] if item['closed']}
    default = nq.untracked_status(repository, options)
    priorities = {name.casefold(): name for name in priority_options(repository)}
    fill = bool(settings['fill_priority'] and priorities)
    strategy = settings['strategy']
    takes = operator_takes(repository)
    steps = strategy_steps(strategy, settings['steps'].get(strategy))
    final_list = settings['final_lists'].get(strategy, True)
    scope_reason = scope_of(repository, settings)
    when = nq.now_iso()
    counts = {'prioritized': 0, 'tracked': 0, 'no_rule': 0, 'out_of_scope': 0, 'priorities_set': 0}
    changed_keys = []
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT p.call_key, p.impact_level, p.impact_state, p.repeated, p.prioritization, p.priority_rule, "
            f"p.suggested_priority, p.priority_filled, p.cluster_size, p.consecutive, p.final_list, p.queue, p.queue_step, "
            f"p.queue_list, p.campaign_key, p.impact_points, p.expected_points, l.service, l.nr_mode, l.operator, l.region, l.city, "
            f"l.environment, l.test_name, l.session_type, l.result, "
            f"COALESCE(NULLIF(t.status, ''), ?) AS status, COALESCE(f.value, '') AS priority "
            f'FROM {PRIORITY_TABLE} p JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = p.call_key '
            f'LEFT JOIN {nq.NQ_CALL_TRACKING_TABLE} t ON t.call_key = p.call_key '
            f'LEFT JOIN {nq.NQ_FIELD_VALUES_TABLE} f ON f.call_key = p.call_key AND f.field_key = ?',
            (default, PRIORITY_FIELD)).fetchall()
        updates = []
        # The calls of the operators excluded in the Operator Maps count nowhere (the calculation gives them no values).
        excluded_operators = excluded_names(repository)
        rows = [row for row in rows if str(row['operator'] or '').strip().casefold() not in excluded_operators]
        # The levels of the calls in scope compare them with each other only, as the #Calls of the rules.
        levels = expected_levels(rows, settings['high_share'], settings['medium_share'],
                                 lambda row: bool(scope_reason(row['region'], row['nr_mode'], row['operator'])[0]))
        for row in rows:
            # The calls out of scope stay out of the queues whatever the strategy.
            scope = scope_reason(row['region'], row['nr_mode'], row['operator'])[0]
            counts['out_of_scope'] += bool(scope)
            if scope:
                decision, rule, suggestion, queue, step, list_name = NO_RULE, scope, '', '', None, ''
            else:
                decision, rule, suggestion, queue, step, list_name = strategy_decision(strategy, {
                    'scope': scope, 'operator': str(row['operator'] or ''), 'nr_mode': str(row['nr_mode'] or ''),
                    'kind': call_kind(row['service'], row['test_name'], row['session_type']), 'area': call_area(row['environment']),
                    'excluded': row['impact_state'] == EXCLUDED, 'final': bool(row['final_list']), 'level': levels.get(row['call_key'], ''),
                    'repeated': row['repeated'] == 'Yes', 'cluster_size': row['cluster_size'], 'consecutive': row['consecutive'] or '',
                    'result': row['result'] or ''},
                    steps, takes, final_list)
            counts[{PRIORITIZED: 'prioritized', TRACK_ONLY: 'tracked'}.get(decision, 'no_rule')] += 1
            suggestion = priorities.get(suggestion.casefold(), '') if suggestion else ''
            filled = str(row['priority_filled'] or '')
            current = str(row['priority'] or '')
            started = str(row['status']).casefold() != default.casefold()
            if fill and filled != BY_HAND and str(row['status']).casefold() not in closed:
                if filled and current != filled:
                    # Changed (or cleared) by hand: the rules no longer change it.
                    filled = BY_HAND
                elif (filled or not current) and suggestion != current and not (started and current):
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
            if (decision, rule, suggestion, filled, queue, step, list_name) != (
                    row['prioritization'], row['priority_rule'], row['suggested_priority'], str(row['priority_filled'] or ''),
                    row['queue'] or '', row['queue_step'], row['queue_list'] or ''):
                updates.append((decision, rule, suggestion, filled, queue, step, list_name, row['call_key']))
        connection.executemany(
            f'UPDATE {PRIORITY_TABLE} SET prioritization = ?, priority_rule = ?, suggested_priority = ?, priority_filled = ?, '
            'queue = ?, queue_step = ?, queue_list = ? WHERE call_key = ?', updates)
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


def step_counts(repository: Any, settings: dict[str, Any]) -> dict[str, Any]:
    """How many calls each step of the strategy of ``settings`` takes in the latest campaign with its Final CDR scored of
    each NR Mode: list 1 as during the campaign, list 2 (when the strategy applies it) as once its Final CDR is scored. The
    calls outside the queues count apart, as [name, calls] pairs, the most calls first: those out of scope (``scope``: by
    region, by NR Mode and operator not Focus, SA · EE, and by NR Mode and operator chosen, SA · Three) and, in each list
    (``lists``), the tracked ones
    (by kind, and by operator and NR Mode) and those no step takes (by operator and NR Mode)."""
    from src.modules import non_qualified_calls as nq
    from src.modules.column_names import campaign_sort_key, compact_campaign_value

    def pairs(counts: dict[str, int]) -> list[list[Any]]:
        return [[name, calls] for name, calls in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]

    strategy = settings['strategy']
    result: dict[str, Any] = {'counts': {}, 'campaigns': [], 'out_of_scope': 0, 'calls': 0,
                              'scope': {'regions': [], 'operators': [], 'modes': []},
                              'lists': {}}
    ensure_tables(repository)
    with repository.connection() as connection:
        rows = [dict(row) for row in connection.execute(
            f"SELECT p.call_key, p.campaign_key, p.impact_level, p.impact_state, p.impact_points, p.expected_points, p.repeated, "
            f"p.cluster_size, p.consecutive, l.service, l.nr_mode, l.campaign, l.operator, l.region, l.environment, l.test_name, "
            f"l.session_type, l.result FROM {PRIORITY_TABLE} p JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = p.call_key "
            "WHERE p.final_list = 1")]
    # The latest campaign with its Final CDR of each NR Mode.
    latest: dict[str, str] = {}
    for row in rows:
        mode, campaign = str(row['nr_mode'] or '').upper(), str(row['campaign'] or '')
        if mode not in latest or campaign_sort_key(campaign) > campaign_sort_key(latest[mode]):
            latest[mode] = campaign
    rows = [row for row in rows if latest.get(str(row['nr_mode'] or '').upper()) == str(row['campaign'] or '')]
    # The calls of the operators excluded in the Operator Maps count nowhere.
    excluded_operators = excluded_names(repository)
    rows = [row for row in rows if str(row['operator'] or '').strip().casefold() not in excluded_operators]
    # The campaigns as the Campaign Maps name them (2026-Q3-SA).
    result['campaigns'] = [compact_campaign_value(name) or name for name in sorted(set(latest.values()), key=campaign_sort_key)]
    scope_reason = scope_of(repository, settings)
    label = operator_label(repository)
    takes = operator_takes(repository)
    steps = strategy_steps(strategy, settings['steps'].get(strategy))
    lists = [CAMPAIGN_LIST] + ([FINAL_LIST] if settings['final_lists'].get(strategy, True) else [])
    # The clusters and hotspots of the settings being edited, at once (the impact levels follow them in each list).
    places = place_values(repository, settings)
    for row in rows:
        place = places.get(row['call_key'])
        if place:
            row['repeated'], row['cluster_size'] = place['repeated'], place['cluster_size']
    in_scope = []
    found: dict[str, dict[str, int]] = {'region': {}, 'operator': {}, 'mode': {}}
    for row in rows:
        reason, kind = scope_reason(row['region'], row['nr_mode'], row['operator'])
        if not reason:
            in_scope.append(row)
            continue
        result['out_of_scope'] += 1
        # The region (Vendor B), the operator that is not a Focus operator (SA · EE) or the pair chosen (SA · Three).
        name = reason.split(' · ', 1)[1]
        found[kind][name] = found[kind].get(name, 0) + 1
    result['calls'] = len(in_scope)
    result['scope'] = {'regions': pairs(found['region']), 'operators': pairs(found['operator']), 'modes': pairs(found['mode'])}
    for list_name in lists:
        final = list_name == FINAL_LIST
        by_rule = {step['rule']: step['id'] for step in steps if step['list'] == list_name}
        result['counts'].update({step_id_: 0 for step_id_ in by_rule.values()})
        # The impact levels by the Expected Gain: the calls of a campaign with its Final CDR have their own points, in both
        # lists (during a campaign, its calls take the estimate from the Final CDR before it).
        levels = expected_levels(in_scope, settings['high_share'], settings['medium_share'])
        tracked_kinds: dict[str, int] = {}
        tracked_operators: dict[str, int] = {}
        untaken: dict[str, int] = {}
        for row in in_scope:
            call = {'operator': str(row['operator'] or ''), 'nr_mode': str(row['nr_mode'] or ''),
                    'kind': call_kind(row['service'], row['test_name'], row['session_type']), 'area': call_area(row['environment']),
                    'excluded': row['impact_state'] == EXCLUDED, 'final': final, 'level': levels.get(row['call_key'], ''),
                    'repeated': row['repeated'] == 'Yes', 'cluster_size': row['cluster_size'], 'consecutive': row['consecutive'] or '',
                    'result': row['result'] or ''}
            decision = strategy_decision(strategy, call, steps, takes, True)
            if decision[1] in by_rule:
                result['counts'][by_rule[decision[1]]] += 1
            # The operator with the NR Mode of its campaign (Three NSA), so that no SA call of an operator without SA seems taken.
            operator = f"{label(call['operator']) or 'No operator'} {call['nr_mode'].upper()}".strip()
            if decision[0] == TRACK_ONLY:
                # The Excluded Calls and the Ping tests never enter a queue; the others met no step of a queue.
                call_type = CALL_TYPES[call['kind']] if call['kind'] in CALL_TYPES else ''
                kind = ('Excluded Calls' if call['excluded'] else 'Ping tests' if call['kind'] == PING
                        else f'{call_type} calls no {call_type} step takes')
                tracked_kinds[kind] = tracked_kinds.get(kind, 0) + 1
                tracked_operators[operator] = tracked_operators.get(operator, 0) + 1
            elif decision[0] == NO_RULE:
                untaken[operator] = untaken.get(operator, 0) + 1
        result['lists'][list_name] = {'tracked': pairs(tracked_kinds), 'tracked_operators': pairs(tracked_operators),
                                      'untaken': pairs(untaken)}
    return result


def _workspace_key(path: Any) -> str:
    return str(Path(str(path)).resolve())


def job(database_path: Any) -> dict[str, Any] | None:
    with _jobs_guard:
        current = _jobs.get(_workspace_key(database_path))
        return dict(current) if current else None


def outdated(repository: Any) -> bool:
    """Whether the values were never calculated, or by an earlier version of the calculation (their panel then
    calculates them at once instead of waiting for the server to be idle)."""
    try:
        summary = json.loads(repository.get_workspace_state(SUMMARY_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        summary = {}
    return not isinstance(summary, dict) or summary.get('version') != IMPACT_VERSION


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


def panel(repository: Any, filters: Any, username: str) -> dict[str, Any]:
    """The NQ Prioritization of the filtered calls: the calls of each step, the KPIs whose points they lose, the
    repeated issues and the calls to analyse next (prioritized, open and not attended yet) in each queue, and the tracked
    ones apart."""
    from src.modules import non_qualified_calls as nq
    from src.modules.column_names import compact_campaign_value

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
            f'suggested_priority, queue, queue_step, queue_list, expected_points, expected_campaign FROM calls{where}',
            [*base_params, *params])]
    is_open = [str(row['status'] or '').casefold() not in closed_names for row in rows]
    attended = [bool(row['updated_at']) or int(row['comment_count'] or 0) > 0 for row in rows]
    strategy = settings['strategy']
    # The calls of each step of the strategy, in their order, then those none takes.
    # Each step with its number and list, its fields as the Prioritization Rules show them (NR Mode, Call Type, Area,
    # Condition and queue, with their keys for their colours) and what it takes in short and in full.
    entries = [{'kind': 'step', 'name': step['rule'], 'number': step['number'], 'label': step['label'], 'conditions': step['takes'],
                'criterion': f"{step['queue']} queue" if step['queue'] else 'Tracked',
                'priority': step['priority'], 'track_priority': '', 'list': step['list'],
                'operators': operators_text(step['operators']), 'nr_mode': step['nr_mode'], 'call_type': CALL_TYPES[step['call_type']],
                'area': STEP_AREAS[step['area']], 'condition': step_conditions_text(step['conditions'], step['joins']),
                'queue': STEP_QUEUES[step['queue']]}
               for step in strategy_steps(strategy, settings['steps'].get(strategy))
               if step['list'] == CAMPAIGN_LIST or settings['final_lists'].get(strategy, True)]
    unruled_text = 'The calls of the operators no step takes'
    # The calls out of scope, one entry whatever their reason.
    modes = [f"{item['nr_mode']} · {item['operator']}" for item in settings['excluded_modes']]
    entries.append({'kind': OUT_OF_SCOPE_KIND, 'name': OUT_OF_SCOPE, 'number': None, 'list': '',
                    'label': 'Regions, operators and NR Mode · operator pairs out of scope', 'conditions': 'The calls of the regions'
                    + (f" ({', '.join(settings['excluded_regions'])})" if settings['excluded_regions'] else '')
                    + ', of the operators that are not Focus operators and of the NR Mode · operator pairs'
                    + (f" ({', '.join(modes)})" if modes else '') + ' out of scope',
                    'criterion': 'Out of the queues',
                    'priority': '', 'track_priority': '', 'operators': ''})
    order = {entry['name']: index for index, entry in enumerate(entries)}
    # Waiting: open and not attended yet, as the queues count their calls.
    rules = [{**entry, 'calls': 0, 'prioritized': 0, 'tracked': 0, 'points': 0.0, 'open': 0, 'attended': 0, 'waiting': 0}
             for entry in entries]
    unruled = {'kind': 'none', 'name': '', 'number': None, 'list': '', 'label': unruled_text, 'conditions': unruled_text,
               'criterion': '', 'priority': '', 'track_priority': '', 'operators': '',
               'calls': 0, 'prioritized': 0, 'tracked': 0, 'points': 0.0, 'open': 0, 'attended': 0, 'waiting': 0}
    levels: dict[str, int] = {}
    kpis: dict[tuple[str, str, str], dict[str, Any]] = {}
    issues: dict[tuple[str, str], dict[str, Any]] = {}
    queue: list[dict[str, Any]] = []
    # The open calls nobody attended yet that only a tracked step takes, in no team queue.
    tracked: list[dict[str, Any]] = []
    for row, opened, followed in zip(rows, is_open, attended):
        points = float(row['impact_points'] or 0)
        name = OUT_OF_SCOPE if str(row['priority_rule'] or '').startswith(OUT_OF_SCOPE) else row['priority_rule']
        entry = rules[order[name]] if name in order else unruled
        entry['calls'] += 1
        entry['prioritized'] += row['prioritization'] == PRIORITIZED
        entry['tracked'] += row['prioritization'] == TRACK_ONLY
        entry['points'] += points
        entry['open'] += opened
        entry['attended'] += followed
        entry['waiting'] += opened and not followed
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
        if opened and not followed:
            if row['prioritization'] == PRIORITIZED:
                queue.append(row)
            elif row['prioritization'] == TRACK_ONLY:
                tracked.append(row)

    def priority_of(row: dict[str, Any]) -> str:
        try:
            values = json.loads(row['field_values_json'] or '{}') or {}
        except (TypeError, ValueError):
            values = {}
        return str(values.get(PRIORITY_FIELD) or row['suggested_priority'] or '')
    # A queue per team, in the order the analysts take its calls.
    queues = []
    names = priority_options(repository) or list(STRATEGY_PRIORITY_NAMES)
    for name in (VOICE_QUEUE, DATA_QUEUE):
        members = [{**row, 'priority': priority_of(row)} for row in queue if row['queue'] == name]
        queues.append({'name': name, 'total': len(members), 'rows': order_queue(members, names)})
    queue = []
    tracked = order_queue([{**row, 'priority': priority_of(row)} for row in tracked], names)
    issue_rows = sorted(issues.values(), key=lambda item: (-item['calls'], -item['points'], item['operator'].casefold(), item['place']))
    for item in issue_rows:
        item['campaigns'] = len(item['campaigns'])
        item['points'] = round(item['points'], 2)
        item['category'] = max(item.pop('categories').items(), key=lambda pair: (pair[1], pair[0]))[0] if item['categories'] else ''
    for entry in (*rules, unruled):
        entry['points'] = round(entry['points'], 2)
    level_order = [name for name, _color in nq_catalog.IMPACT_LEVELS]

    def queue_row(row: dict[str, Any], position: int) -> dict[str, Any]:
        return {'position': position, 'call_key': row['call_key'], 'join_id': row['join_id'], 'operator': row['operator'],
                'service': nq.SERVICE_LABELS.get(str(row['service']), str(row['service'])), 'nr_mode': row['nr_mode'],
                'campaign': compact_campaign_value(row['campaign']) or row['campaign'], 'result': row['result'],
                'start_time': row['start_time'], 'rule': row['priority_rule'], 'priority': priority_of(row), 'step': row.get('queue_step'),
                'points': None if row['impact_points'] is None else round(float(row['impact_points']), 2),
                'gain': None if row.get('expected_points') is None else round(float(row['expected_points']), 2),
                'gain_campaign': row.get('expected_campaign') or '', 'list': row.get('queue_list') or '',
                'level': row['impact_level'], 'repetitions': row['repetitions'], 'place': row['place_label']}
    return {
        'status': status(repository),
        'strategy': {'key': strategy, 'label': strategy_labels(settings)[strategy]},
        'settings': {key: settings[key] for key in ('high_share', 'medium_share', 'min_calls', 'previous_quarters', 'capacity')},
        'totals': {
            'calls': len(rows), 'prioritized': sum(row['prioritization'] == PRIORITIZED for row in rows),
            'tracked': sum(row['prioritization'] == TRACK_ONLY for row in rows),
            'high': sum(row['impact_level'] == IMPACT_HIGH for row in rows),
            'repeated': sum(row['repeated'] == 'Yes' for row in rows), 'places': len(issues),
            'points': round(sum(float(row['impact_points'] or 0) for row in rows), 2),
            'next': len(queue) + sum(item['total'] for item in queues),
            'waiting': sum(not row['impact_state'] for row in rows),
        },
        'levels': [{'value': name, 'count': levels[name], 'color': dict(nq_catalog.IMPACT_LEVELS).get(name, '')}
                   for name in sorted(levels, key=lambda name: level_order.index(name) if name in level_order else len(level_order))],
        'rules': [*rules, *([unruled] if unruled['calls'] else [])],
        'kpis': sorted(({**item, 'points': round(item['points'], 2)} for item in kpis.values()),
                       key=lambda item: (-item['points'], item['code'], item['environment']))[:MAX_PANEL_KPIS],
        'issues': issue_rows[:MAX_ISSUES], 'issue_count': len(issue_rows),
        'queue': [queue_row(row, position) for position, row in enumerate(queue[:settings['capacity']], start=1)],
        'queues': [{'name': item['name'], 'total': item['total'],
                    'rows': [queue_row(row, position) for position, row in enumerate(item['rows'][:settings['capacity']], start=1)]}
                   for item in queues],
        # The tracked calls, which no team takes, in the same order (the panel folds them below the queues).
        'tracked': {'name': 'Tracked', 'total': len(tracked),
                    'rows': [queue_row(row, position) for position, row in enumerate(tracked[:settings['capacity']], start=1)]},
    }
