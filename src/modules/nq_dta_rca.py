"""DT Analyzer RCA: the root cause of every Non-Qualified Call, found from the data of its CDR.

It is an RCA source of the NQ Analysis Center in every workspace, whatever its CDR type: beside the RCA the provider
brings (the NetCheck RCA of NetCheck CDRs), the Ericsson RCA and the analysts, it always shows after the Ericsson RCA.
Every call is read through the field profile of the workspace's CDR type (cdr_field_profiles ``nq_rca_sources``):
its result and failure (phase, technology, side and the provider's description of it, events and SCG failures), the
radio of LTE and NR on both sides (RSRP, RSRQ, SINR, BLER and transmit power), its mobility (handovers and the
technologies it used) and its KPIs (throughput, access, DNS and TCP times, packet loss, latency, setup time, speech
quality and RTP).

Ordered rules decide: the first enabled rule of the service of the call whose conditions hold (all of them, or any of
them) gives its Root Category and Root Cause on the Root Cause Catalog of the workspace, their root domain and the
evidence, the values that matched. The default rules are the same in every workspace: what the provider reports outside
the radio first (device, subscription, core and IMS), then the radio of the call, then the service once the radio is not
the cause, and a last rule for the calls none of them explains. Admins edit them per workspace (order, conditions,
thresholds, category and cause); they travel with the NQ Calls configuration (export, import, transfers and backups).

non_qualified_calls stores the inputs of every indexed call and calculates the results when the calls are indexed and
whenever the rules or the Root Cause Catalog change.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from src.modules.nq_catalog import keyword_found, keywords, normalized_text

ENGINE_VERSION = 1
SOURCE_LABEL = 'DT Analyzer RCA'
RULES_STATE_KEY = 'nq_dta_rca_rules'
FINGERPRINT_STATE_KEY = 'nq_dta_rca_fingerprint'
RESULTS_TABLE = 'nq_dta_rca_results'
# Learning from the decisions of the analysts: its setting, the root causes learned and what they depend on.
SETTINGS_STATE_KEY = 'nq_dta_rca_settings'
LEARNED_TABLE = 'nq_dta_rca_learned'
LEARNED_FINGERPRINT_STATE_KEY = 'nq_dta_rca_learned_fingerprint'
TABLE_TITLES = {RESULTS_TABLE: 'NQ DT Analyzer RCA Results', LEARNED_TABLE: 'NQ DT Analyzer RCA Learned'}
# A choice is learned when at least this many other calls of the same pattern have it, and more than half of them.
LEARNING_MIN_DECISIONS = 2
SERVICES = {'voice': 'Voice', 'speech': 'Speech', 'data': 'Data'}
MATCHES = {'all': 'All conditions', 'any': 'Any condition'}
MAX_RULES = 80
MAX_CONDITIONS = 8
MAX_TEXT = 120
MAX_EVIDENCE = 600
# The last default rule, for the calls no other rule explains: shown, but never recommended.
NOT_IDENTIFIED_KEY = 'not-identified'

# The values a rule reads: key -> (label, kind, unit, group). The call values come from the NQ index, the description of
# the failure joins the failure fields of the provider with its events, and the others come from the CDR.
INPUTS: dict[str, tuple[str, str, str, str]] = {
    'result': ('Result', 'text', '', 'Call'),
    'test_name': ('Test Name', 'text', '', 'Call'),
    'technology': ('Technology', 'text', '', 'Call'),
    'direction': ('Direction', 'text', '', 'Call'),
    'environment': ('Environment', 'text', '', 'Call'),
    'failure_text': ('Failure description', 'text', '', 'Failure'),
    'failure_phase': ('Failure Phase', 'text', '', 'Failure'),
    'failure_technology': ('Failure Technology', 'text', '', 'Failure'),
    'failure_side': ('Failure Side', 'text', '', 'Failure'),
    'radio_technology': ('Technology at the failure', 'text', '', 'Failure'),
    'radio_measured': ('Radio measured', 'text', '', 'Call'),
    'lte_rsrp': ('LTE RSRP (average)', 'number', 'dBm', 'LTE radio'),
    'lte_rsrp_min': ('LTE RSRP (minimum)', 'number', 'dBm', 'LTE radio'),
    'lte_rsrq': ('LTE RSRQ (average)', 'number', 'dB', 'LTE radio'),
    'lte_sinr': ('LTE SINR (average)', 'number', 'dB', 'LTE radio'),
    'lte_sinr_min': ('LTE SINR (minimum)', 'number', 'dB', 'LTE radio'),
    'lte_tx_power': ('LTE transmit power (maximum)', 'number', 'dBm', 'LTE radio'),
    'lte_bler': ('LTE BLER', 'number', '%', 'LTE radio'),
    'nr_rsrp': ('NR RSRP (average)', 'number', 'dBm', 'NR radio'),
    'nr_rsrp_min': ('NR RSRP (minimum)', 'number', 'dBm', 'NR radio'),
    'nr_rsrq': ('NR RSRQ (average)', 'number', 'dB', 'NR radio'),
    'nr_sinr': ('NR SINR (average)', 'number', 'dB', 'NR radio'),
    'nr_sinr_min': ('NR SINR (minimum)', 'number', 'dB', 'NR radio'),
    'nr_tx_power': ('NR transmit power (maximum)', 'number', 'dBm', 'NR radio'),
    'nr_bler': ('NR BLER', 'number', '%', 'NR radio'),
    'b_lte_rsrp': ('B side LTE RSRP (average)', 'number', 'dBm', 'B side radio'),
    'b_lte_sinr': ('B side LTE SINR (average)', 'number', 'dB', 'B side radio'),
    'b_nr_rsrp': ('B side NR RSRP (average)', 'number', 'dBm', 'B side radio'),
    'b_nr_sinr': ('B side NR SINR (average)', 'number', 'dB', 'B side radio'),
    'rat': ('Technologies used', 'text', '', 'Mobility'),
    'rat_timeline': ('Technology timeline', 'text', '', 'Mobility'),
    'handovers': ('Handovers', 'number', '', 'Mobility'),
    'handovers_info': ('Handover types', 'text', '', 'Mobility'),
    'throughput': ('Throughput', 'number', 'Mbit/s', 'KPIs'),
    'access_time': ('Service access time', 'number', 's', 'KPIs'),
    'dns_time': ('DNS time', 'number', 'ms', 'KPIs'),
    'dns_success': ('DNS success', 'number', '%', 'KPIs'),
    'tcp_rtt': ('TCP round-trip time', 'number', 'ms', 'KPIs'),
    'packet_loss': ('Packet loss', 'number', '%', 'KPIs'),
    'rtt': ('Latency (round-trip time)', 'number', 'ms', 'KPIs'),
    'setup_time': ('Call setup time', 'number', 's', 'KPIs'),
    'duration': ('Duration', 'number', 's', 'KPIs'),
    'mos': ('Speech quality (MOS)', 'number', '', 'KPIs'),
    'rtp_packet_loss': ('RTP packet loss', 'number', '%', 'KPIs'),
    'jitter': ('Jitter', 'number', 'ms', 'KPIs'),
}
# The inputs that are indexed fields of the call, and the failure fields its description joins (with two CDR inputs).
CALL_INPUTS = ('result', 'test_name', 'technology', 'direction', 'environment', 'failure_phase', 'failure_technology')
FAILURE_TEXT_FIELDS = ('failure_classification', 'failure_category', 'failure_subcategory', 'failure_comment')
FAILURE_TEXT_INPUTS = ('failure_events', 'scg_failures')
# The inputs found from the others: the description of the failure, the technology at the failure (the Failure Technology,
# else the technology of the call or the technologies it used) and the radio measured (LTE and NR, by their RSRP or SINR).
DERIVED_INPUTS = ('failure_text', 'radio_technology', 'radio_measured')
# The inputs read from the CDR (the profile lists their columns).
CDR_INPUTS = tuple(key for key in (*INPUTS, *FAILURE_TEXT_INPUTS) if key not in CALL_INPUTS and key not in DERIVED_INPUTS)
OPERATORS = {
    'lt': '<', 'le': '≤', 'gt': '>', 'ge': '≥', 'eq': '=', 'ne': '≠',
    'contains': 'contains', 'not_contains': 'does not contain', 'empty': 'is empty', 'not_empty': 'is not empty',
}
KIND_OPERATORS = {
    'number': ('lt', 'le', 'gt', 'ge', 'eq', 'ne', 'empty', 'not_empty'),
    'text': ('contains', 'not_contains', 'eq', 'ne', 'empty', 'not_empty'),
}
_VALUELESS = frozenset({'empty', 'not_empty'})
_VOICE = ('voice', 'speech')
_COVERAGE = 'coverage, plmn lost, no service, out of service'
_NR = (('radio_technology', 'contains', '5g, nr'), ('radio_technology', 'not_contains', '4g, lte'))
_LEGACY = (('radio_technology', 'contains', '2g, 3g, gsm, umts, wcdma'), ('radio_technology', 'not_contains', '4g, lte, 5g, nr'))
_MEASURED = ('radio_measured', 'not_empty', '')

# The default rules, in order: (key, name, services, match, conditions, Root Category, Root Cause). A text condition
# holds when the text contains one of its comma-separated terms ("a+b" needs both); a rule without conditions takes
# every call of its services that reaches it.
_DEFAULT_RULES: tuple[tuple[str, str, tuple[str, ...], str, tuple[tuple[str, str, Any], ...], str, str], ...] = (
    # What the provider reports outside the radio: the device, the subscription, the core and IMS.
    ('device', 'Device or test setup', (), 'any',
     (('failure_text', 'contains', 'modem, device, test setup, ue crash, at command, script error, battery'),),
     'UE / Test Setup Issue', 'Device or test setup'),
    ('subscriber-identity', 'Subscriber identity', (), 'any',
     (('failure_text', 'contains', 'imsi, ue identity cannot be derived'),), 'IMSI Issue', ''),
    ('authentication', 'Authentication or registration rejected', (), 'any',
     (('failure_text', 'contains', 'authentication, authorization, registration reject, attach reject, '
                                   'pdu session establishment reject'),), 'Authentication & Registration', 'Authentication/Authorization'),
    ('tracking-area-update', 'Tracking area update', (), 'any',
     (('failure_text', 'contains', 'tracking area update'),), 'Core Network', 'TAU reject'),
    ('bearer-deactivation', 'Bearer deactivated by the network', (), 'any',
     (('failure_text', 'contains', 'bearer deactivation, deregistered, detach request'),), 'Core Network', 'EPS bearer deactivation'),
    ('qci1', 'No QCI1 bearer for the call', _VOICE, 'any', (('failure_text', 'contains', 'qci1, qci 1'),), 'IMS / VoLTE',
     'No QCI1 established'),
    ('ims-core', 'VoLTE or IMS core', _VOICE, 'any',
     (('failure_text', 'contains', 'volte core, ims core, ims registration, sip, server internal error'),), 'IMS / VoLTE', 'VoLTE core'),
    ('eps-fallback', 'EPS fallback', _VOICE, 'any', (('failure_text', 'contains', 'epsfb, eps fallback'),), 'EPS Fallback',
     'EPS fallback failure'),
    ('paging', 'Paging', (), 'any', (('failure_text', 'contains', 'paging'),), 'RAN Performance', 'Paging'),
    ('session-in-gsm', 'Session in GSM', (), 'any', (('failure_text', 'contains', 'session in gsm'),), 'Core Network',
     'WhatsApp session in GSM'),
    # The radio of the call: the anchor (LTE) before NR, the A side before the B side.
    ('lte-coverage', 'Poor LTE coverage', (), 'all', (('lte_rsrp', 'lt', -110),), 'Poor Coverage LTE', 'Coverage'),
    ('nr-coverage', 'Poor NR coverage', (), 'all', (('nr_rsrp', 'lt', -110),), 'Poor Coverage NR', 'Coverage'),
    ('lte-uplink', 'LTE uplink at maximum power', (), 'all', (('lte_tx_power', 'ge', 23), ('lte_rsrp', 'lt', -100)),
     'Poor Coverage LTE', 'Coverage'),
    ('lte-interference', 'LTE downlink interference', (), 'all', (('lte_sinr', 'lt', 0),), 'DL Interference LTE', 'DL interference'),
    ('nr-interference', 'NR downlink interference', (), 'all', (('nr_sinr', 'lt', 0),), 'DL Interference NR', 'DL interference'),
    ('lte-dominance', 'No dominant LTE cell', (), 'all', (('lte_rsrq', 'lt', -15),), 'DL Interference LTE', 'Lack of dominant cell'),
    ('b-lte-coverage', 'Poor LTE coverage of the B side', _VOICE, 'all', (('b_lte_rsrp', 'lt', -110),), 'Poor Coverage LTE', 'Coverage'),
    ('b-nr-coverage', 'Poor NR coverage of the B side', _VOICE, 'all', (('b_nr_rsrp', 'lt', -110),), 'Poor Coverage NR', 'Coverage'),
    ('b-lte-interference', 'LTE interference on the B side', _VOICE, 'all', (('b_lte_sinr', 'lt', 0),),
     'DL Interference LTE', 'DL interference'),
    ('legacy-technology', 'Fallback to 2G or 3G', (), 'any',
     (('rat', 'contains', 'gsm, umts, wcdma, hspa, 2g, 3g'),), 'Poor Coverage 2G/3G', 'Inter-RAT transition'),
    ('lte-bler', 'High LTE BLER', (), 'all', (('lte_bler', 'gt', 10),), 'BLER LTE', 'BLER'),
    ('nr-bler', 'High NR BLER', (), 'all', (('nr_bler', 'gt', 10),), 'BLER NR', 'BLER'),
    ('nr-handover', 'NR handover failure', (), 'all',
     (('failure_text', 'contains', 'handover'), ('failure_technology', 'contains', '5g, nr')), 'Mobility NR', 'Handover failure'),
    ('handover', 'Handover failure', (), 'any', (('failure_text', 'contains', 'handover'),), 'Mobility LTE', 'Handover failure'),
    ('radio-link', 'Radio link failure', (), 'any',
     (('failure_text', 'contains', 'radio link failure, t310, reestablishment, random access, rach, scg failure, scgfailure, rrc'),),
     'RAN Performance', 'RRC layer'),
    ('inter-rat', 'Inter-RAT transition', (), 'any',
     (('failure_text', 'contains', 'inter-rat, irat, redirection, 4g -> 5g, 5g -> 4g'),), 'RAN Performance', 'Inter-RAT transition'),
    # What the provider reports about the radio, on the technology at the failure (LTE, the anchor, when it is not NR alone,
    # 2G or 3G alone).
    ('reported-coverage-nr', 'NR coverage reported by the provider', (), 'all', (('failure_text', 'contains', _COVERAGE), *_NR),
     'Poor Coverage NR', 'Coverage'),
    ('reported-coverage-legacy', '2G or 3G coverage reported by the provider', (), 'all',
     (('failure_text', 'contains', _COVERAGE), *_LEGACY), 'Poor Coverage 2G/3G', 'Coverage'),
    ('reported-coverage', 'Coverage reported by the provider', (), 'any', (('failure_text', 'contains', _COVERAGE),),
     'Poor Coverage LTE', 'Coverage'),
    ('reported-ul-interference-nr', 'NR uplink interference reported by the provider', (), 'all',
     (('failure_text', 'contains', 'ul interference, uplink interference'), *_NR), 'UL Interference NR', 'UL interference'),
    ('reported-ul-interference', 'Uplink interference reported by the provider', (), 'any',
     (('failure_text', 'contains', 'ul interference, uplink interference'),), 'UL Interference LTE', 'UL interference'),
    ('reported-interference-nr', 'NR interference reported by the provider', (), 'all',
     (('failure_text', 'contains', 'interference'), *_NR), 'DL Interference NR', 'DL interference'),
    ('reported-interference-legacy', '2G or 3G interference reported by the provider', (), 'all',
     (('failure_text', 'contains', 'interference'), *_LEGACY), 'DL Interference 2G/3G', 'DL interference'),
    ('reported-interference', 'Interference reported by the provider', (), 'any',
     (('failure_text', 'contains', 'interference'),), 'DL Interference LTE', 'DL interference'),
    # The service, once the radio is not the cause.
    ('dns', 'DNS', ('data',), 'any',
     (('failure_text', 'contains', 'dns'), ('dns_success', 'lt', 100), ('dns_time', 'gt', 1000)), 'Protocol / Server', 'DNS'),
    ('http', 'HTTP or server error', ('data',), 'any',
     (('failure_text', 'contains', 'http, server error, 200 ok'),), 'Protocol / Server', 'HTTP'),
    ('tcp', 'TCP connection', ('data',), 'any',
     (('failure_text', 'contains', 'tcp, handshake'), ('tcp_rtt', 'gt', 1000)), 'Protocol / Server', 'TCP connection errors'),
    ('no-dl-packets', 'No downlink packets', ('data',), 'any', (('failure_text', 'contains', 'no dl packets'),), 'Protocol / Server',
     'No DL packets'),
    ('packet-loss', 'Packet loss', ('data',), 'any',
     (('failure_text', 'contains', 'packet loss, no answer to ping, retransmission, no answer to hello'), ('packet_loss', 'gt', 5)),
     'Protocol / Server', 'Packet loss'),
    ('latency', 'High latency', ('data',), 'any', (('failure_text', 'contains', 'latency'), ('rtt', 'gt', 150)), 'Protocol / Server',
     'Latency'),
    ('timeout', 'Data transfer timeout', ('data',), 'any', (('failure_text', 'contains', 'timeout'),), 'Protocol / Server',
     'Data transfer timeout'),
    ('reported-low-throughput', 'Low throughput reported by the provider', ('data',), 'any',
     (('failure_text', 'contains', 'low throughput'),), 'RAN Performance', 'Low throughput'),
    # The radio measured and none of the rules above: a test cut off for its time, a call that failed with good radio.
    ('low-throughput', 'Low throughput with good radio', ('data',), 'all', (('result', 'contains', 'cutoff'), _MEASURED),
     'RAN Performance', 'Low throughput'),
    ('rtp-loss', 'RTP packet loss', ('speech',), 'any', (('rtp_packet_loss', 'gt', 5),), 'Protocol / Server', 'Packet loss'),
    ('voice-e2e', 'Voice failure with good radio', _VOICE, 'all', (_MEASURED,), 'E2E', 'Potential E2E Issue'),
    ('reported-e2e', 'End-to-end trace required', (), 'any', (('failure_text', 'contains', 'e2e'),), 'E2E', 'E2E trace required'),
    ('not-identified', 'Not identified', (), 'all', (), 'Unclear', ''),
)


def default_rules() -> list[dict[str, Any]]:
    """The default rules, the same in every workspace."""
    return [{'key': key, 'name': name, 'enabled': True, 'services': list(services), 'match': match,
             'conditions': [{'input': input_key, 'op': op, 'value': value} for input_key, op, value in conditions],
             'category': category, 'cause': cause}
            for key, name, services, match, conditions, category, cause in _DEFAULT_RULES]


def inputs_catalog() -> list[dict[str, str]]:
    """The inputs a rule can read, for the rules editor."""
    return [{'key': key, 'label': label, 'kind': kind, 'unit': unit, 'group': group}
            for key, (label, kind, unit, group) in INPUTS.items()]


def _clean(value: Any, limit: int = MAX_TEXT) -> str:
    return re.sub(r'\s+', ' ', str(value if value is not None else '')).strip()[:limit]


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(',', '.')) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float('inf') else None


def _rule_key(name: str, taken: set[str]) -> str:
    base = re.sub(r'[^a-z0-9]+', '-', name.casefold()).strip('-')[:40] or 'rule'
    key, index = base, 2
    while key in taken:
        key, index = f'{base}-{index}', index + 1
    return key


def _condition(item: Any, rule: str, strict: bool) -> dict[str, Any] | None:
    def invalid(message: str) -> None:
        if strict:
            raise ValueError(f'Rule "{rule}": {message}')

    if not isinstance(item, dict):
        invalid('a condition is invalid.')
        return None
    input_key = str(item.get('input') or '')
    if input_key not in INPUTS:
        invalid('choose the value each condition reads.')
        return None
    label, kind = INPUTS[input_key][:2]
    op = str(item.get('op') or '')
    if op not in KIND_OPERATORS[kind]:
        invalid(f'choose how {label} is compared.')
        return None
    if op in _VALUELESS:
        return {'input': input_key, 'op': op, 'value': ''}
    if kind == 'number':
        number = _number(item.get('value'))
        if number is None:
            invalid(f'{label} is compared with a number.')
            return None
        return {'input': input_key, 'op': op, 'value': int(number) if number.is_integer() else number}
    if op in {'contains', 'not_contains'}:
        terms = keywords(item.get('value'))
        if not terms:
            invalid(f'write the words {label} is searched for (separated by commas).')
            return None
        return {'input': input_key, 'op': op, 'value': ', '.join(terms)}
    text = _clean(item.get('value'))
    if not text:
        invalid(f'write the value {label} is compared with.')
        return None
    return {'input': input_key, 'op': op, 'value': text}


def normalize_rules(value: Any, *, strict: bool = False) -> list[dict[str, Any]]:
    """Valid rules: unique keys and names, known services, inputs and operators, and a Root Category or Root Cause each.
    ``strict`` tells what is wrong instead of leaving it out."""
    if not isinstance(value, list):
        if strict:
            raise ValueError('The rules of the DT Analyzer RCA are invalid.')
        return default_rules()
    if strict and len(value) > MAX_RULES:
        raise ValueError(f'Keep at most {MAX_RULES} rules.')
    rules: list[dict[str, Any]] = []
    keys: set[str] = set()
    names: set[str] = set()
    for item in value[:MAX_RULES]:
        if not isinstance(item, dict):
            if strict:
                raise ValueError('A rule of the DT Analyzer RCA is invalid.')
            continue
        name = _clean(item.get('name'), 80)
        if not name or name.casefold() in names:
            if strict:
                raise ValueError(f'The rule "{name}" is repeated.' if name else 'Every rule needs a name.')
            continue
        key = str(item.get('key') or '')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,47}', key) or key in keys:
            key = _rule_key(name, keys)
        services = [service for service in SERVICES if service in [str(entry) for entry in item.get('services') or []]]
        match = str(item.get('match') or 'all')
        if match not in MATCHES:
            if strict:
                raise ValueError(f'Rule "{name}": choose whether all its conditions or any of them must hold.')
            match = 'all'
        conditions = item.get('conditions') if isinstance(item.get('conditions'), list) else []
        if strict and len(conditions) > MAX_CONDITIONS:
            raise ValueError(f'Rule "{name}": keep at most {MAX_CONDITIONS} conditions.')
        cleaned = [condition for entry in conditions[:MAX_CONDITIONS] if (condition := _condition(entry, name, strict))]
        category, cause = _clean(item.get('category'), 80), _clean(item.get('cause'), 80)
        if not category and not cause:
            if strict:
                raise ValueError(f'Rule "{name}": choose the Root Category or the Root Cause it gives.')
            continue
        keys.add(key)
        names.add(name.casefold())
        rules.append({'key': key, 'name': name, 'enabled': bool(item.get('enabled', True)), 'services': services,
                      'match': match, 'conditions': cleaned, 'category': category, 'cause': cause})
    if strict and not rules:
        raise ValueError('Keep at least one rule.')
    return rules


def load_rules(repository: Any) -> list[dict[str, Any]]:
    """The rules of the workspace, or the default ones."""
    try:
        stored = json.loads(repository.get_workspace_state(RULES_STATE_KEY) or 'null')
    except (TypeError, ValueError):
        stored = None
    return normalize_rules(stored) if isinstance(stored, list) and stored else default_rules()


def save_rules(repository: Any, rules: Any, username: str, *, defaults: bool = False) -> list[dict[str, Any]]:
    """Save the rules of the workspace (the default ones with ``defaults``) and tell App Events what changed."""
    before = load_rules(repository)
    normalized = default_rules() if defaults else normalize_rules(rules, strict=True)
    repository.set_workspace_state(RULES_STATE_KEY, json.dumps(normalized, ensure_ascii=False))
    if hasattr(repository, 'try_add_log'):
        changes = rules_changes(before, normalized)
        message = ('DT Analyzer RCA rules restored to the default rules.' if defaults
                   else 'DT Analyzer RCA rules updated.')
        repository.try_add_log(username, 'nq_dta_rca_rules', json.dumps(
            {'message': message, 'rules': len(normalized), 'enabled': sum(rule['enabled'] for rule in normalized),
             'changes': changes or ['No change']}, ensure_ascii=False))
    return normalized


def default_settings() -> dict[str, Any]:
    """Learning from the decisions of the analysts is off in a new workspace."""
    return {'learn': False}


def normalize_settings(value: Any) -> dict[str, Any]:
    return {'learn': bool(value.get('learn'))} if isinstance(value, dict) else default_settings()


def load_settings(repository: Any) -> dict[str, Any]:
    try:
        return normalize_settings(json.loads(repository.get_workspace_state(SETTINGS_STATE_KEY) or 'null'))
    except (TypeError, ValueError):
        return default_settings()


def save_settings(repository: Any, settings: Any, username: str) -> dict[str, Any]:
    """Save the settings of the workspace and tell App Events when learning is turned on or off."""
    before = load_settings(repository)
    normalized = normalize_settings(settings)
    repository.set_workspace_state(SETTINGS_STATE_KEY, json.dumps(normalized))
    if normalized != before and hasattr(repository, 'try_add_log'):
        repository.try_add_log(username, 'nq_dta_rca_learning', json.dumps(
            {'message': 'DT Analyzer RCA learns from the decisions of the analysts.' if normalized['learn']
             else 'DT Analyzer RCA no longer learns from the decisions of the analysts.', 'learn': normalized['learn']}))
    return normalized


def learning_pattern(rule_key: str, call: Any) -> tuple[str, str, str]:
    """The pattern of a call the analysts' decisions are learned for: the rule that explains it, its service and the
    provider's description of its failure (classification, category and subcategory)."""
    failure = ' | '.join(normalized_text(_field(call, key)) for key in FAILURE_TEXT_FIELDS[:3])
    return rule_key, str(_field(call, 'service') or ''), failure


def learned_choice(choices: dict[tuple[str, str], set[str]], own: str) -> tuple[tuple[str, str], int, int] | None:
    """The Root Category and Cause the other calls of a pattern were given most: by at least LEARNING_MIN_DECISIONS calls
    and more than half of them (the call itself never counts); with how many calls chose it and how many were decided."""
    others = {choice: keys - {own} for choice, keys in choices.items()}
    others = {choice: keys for choice, keys in others.items() if keys}
    total = sum(len(keys) for keys in others.values())
    if not others:
        return None
    choice, keys = max(sorted(others.items()), key=lambda item: len(item[1]))
    if len(keys) < LEARNING_MIN_DECISIONS or len(keys) * 2 <= total:
        return None
    return choice, len(keys), total


def learned_evidence(rule: str, call: Any, count: int, total: int) -> str:
    failure = ' · '.join(text for key in FAILURE_TEXT_FIELDS[:3] if (text := _clean(_field(call, key))))
    return (f"Learned from the analysts: {count} of the {total} other calls of the rule “{rule}” with the same failure "
            f"({failure or 'no failure description'}) and the same service were given this root cause.")[:MAX_EVIDENCE]


def describe_condition(condition: dict[str, Any]) -> str:
    """A condition as a sentence: LTE RSRP (average) < -110 dBm."""
    label, _kind, unit = INPUTS.get(condition['input'], (condition['input'], 'text', ''))[:3]
    operator = OPERATORS.get(condition['op'], condition['op'])
    if condition['op'] in _VALUELESS:
        return f'{label} {operator}'
    value = condition['value']
    if condition['op'] in {'contains', 'not_contains'}:
        return f'{label} {operator} ' + ', '.join(f'“{term}”' for term in str(value).split(', '))
    return f'{label} {operator} {_shown(value)}{f" {unit}" if unit else ""}'


def describe_rule(rule: dict[str, Any]) -> str:
    """A rule as one line, for the App Events and the import previews."""
    services = ', '.join(SERVICES[service] for service in rule.get('services') or []) or 'Every service'
    joint = ' and ' if rule.get('match') == 'all' else ' or '
    conditions = joint.join(describe_condition(condition) for condition in rule.get('conditions') or []) or 'every call'
    result = ' · '.join(value for value in (rule.get('category'), rule.get('cause')) if value)
    return f"{services}: {conditions} → {result}{'' if rule.get('enabled', True) else ' (disabled)'}"


def rules_changes(before: Any, after: Any) -> list[str]:
    """What changed between two lists of rules, a line each: the rules added and removed, those changed and the order."""
    was = {rule['key']: rule for rule in normalize_rules(before)} if isinstance(before, list) else {}
    now = {rule['key']: rule for rule in normalize_rules(after)} if isinstance(after, list) else {}
    lines = [f"Rule added: {rule['name']} ({describe_rule(rule)})" for key, rule in now.items() if key not in was]
    lines += [f"Rule removed: {rule['name']}" for key, rule in was.items() if key not in now]
    for key, rule in now.items():
        previous = was.get(key)
        if previous is not None and json.dumps(previous, sort_keys=True) != json.dumps(rule, sort_keys=True):
            renamed = f'{previous["name"]} → ' if previous['name'] != rule['name'] else ''
            lines.append(f"Rule changed: {renamed}{rule['name']} ({describe_rule(rule)})")
    kept = [key for key in now if key in was]
    if kept != [key for key in was if key in now]:
        lines.append('Rules in a new order: ' + ', '.join(now[key]['name'] for key in list(now)[:8]) + ('…' if len(now) > 8 else ''))
    return lines


def _shown(value: Any) -> str:
    number = _number(value)
    if number is None:
        return str(value)
    text = f'{number:.2f}'.rstrip('0').rstrip('.') if not float(number).is_integer() else str(int(number))
    return text.replace('-', '−')


# ---------------------------------------------------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------------------------------------------------
def _by_name(items: list[dict[str, Any]], value: str) -> dict[str, Any] | None:
    key = normalized_text(value)
    return next((item for item in items if normalized_text(item['name']) == key), None) if key else None


def _by_keywords(items: list[dict[str, Any]], value: str) -> dict[str, Any] | None:
    text = normalized_text(value)
    return next((item for item in items if keyword_found(item.get('keywords') or [], text, 'words')), None) if text else None


def resolve_result(category: str, cause: str, taxonomy: dict[str, Any]) -> dict[str, str]:
    """The Root Category, Root Cause and root domain a rule gives on the catalog: the values of the same name, else those
    whose keywords the names contain; a cause mapped to a root category gives it when the rule names none. A value the
    catalog does not know keeps its name, without a domain."""
    categories, causes = taxonomy.get('categories') or [], taxonomy.get('causes') or []
    found_category = (_by_name(categories, category) or _by_keywords(categories, category)) if category else None
    found_cause = (_by_name(causes, cause) or _by_keywords(causes, cause)) if cause else None
    category_name = (found_category or {}).get('name') or category
    if not category_name and found_cause and found_cause.get('category'):
        found_category = _by_name(categories, found_cause['category'])
        category_name = (found_category or {}).get('name') or ''
    domain = (found_category or {}).get('domain') or (found_cause or {}).get('domain') or ''
    return {'category': category_name, 'cause': (found_cause or {}).get('name') or cause, 'domain': domain}


def fingerprint(rules: list[dict[str, Any]], taxonomy: dict[str, Any]) -> str:
    """What the results depend on: the version of the engine, the rules and the catalog values they resolve to."""
    catalog = {plural: [[item.get('name'), item.get('domain'), item.get('category'), item.get('keywords')]
                        for item in taxonomy.get(plural) or []] for plural in ('domains', 'categories', 'causes')}
    payload = json.dumps([ENGINE_VERSION, rules, catalog], sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()


def compile_rules(rules: list[dict[str, Any]], taxonomy: dict[str, Any]) -> list[dict[str, Any]]:
    """The enabled rules ready to evaluate: their result resolved on the catalog and their terms split."""
    compiled = []
    for rule in rules:
        if not rule.get('enabled', True):
            continue
        conditions = []
        for condition in rule['conditions']:
            kind = INPUTS[condition['input']][1]
            if condition['op'] in {'contains', 'not_contains'}:
                value: Any = keywords(condition['value'])
            elif kind == 'number' and condition['op'] not in _VALUELESS:
                value = float(condition['value'])
            else:
                value = normalized_text(condition['value'])
            conditions.append((condition, kind, value))
        compiled.append({'rule': rule, 'services': frozenset(rule['services']), 'all': rule['match'] == 'all',
                         'conditions': conditions, 'result': resolve_result(rule['category'], rule['cause'], taxonomy)})
    return compiled


def _field(call: Any, key: str) -> Any:
    try:
        return call[key]
    except (KeyError, IndexError, TypeError):
        return ''


def failure_text(call: Any, inputs: dict[str, Any]) -> str:
    """The provider's description of the failure: its failure fields, events and SCG failures."""
    values = []
    for key in FAILURE_TEXT_FIELDS:
        try:
            values.append(_clean(call[key], 300))
        except (KeyError, IndexError, TypeError):
            continue
    values += [_clean(inputs.get(key), 300) for key in FAILURE_TEXT_INPUTS]
    return ' · '.join(value for value in values if value)


def _holds(condition: dict[str, Any], kind: str, expected: Any, value: Any) -> bool:
    op = condition['op']
    if op == 'empty':
        return value in (None, '')
    if op == 'not_empty':
        return value not in (None, '')
    if kind == 'number':
        number = _number(value)
        if number is None:
            return False
        return {'lt': number < expected, 'le': number <= expected, 'gt': number > expected, 'ge': number >= expected,
                'eq': number == expected, 'ne': number != expected}[op]
    text = normalized_text(value)
    if op == 'contains':
        return keyword_found(expected, text, 'text')
    if op == 'not_contains':
        return not keyword_found(expected, text, 'text')
    return (text == expected) if op == 'eq' else (text != expected)


def _evidence(condition: dict[str, Any], kind: str, expected: Any, value: Any) -> str:
    label, _kind, unit = INPUTS[condition['input']][:3]
    unit = f' {unit}' if unit else ''
    if condition['op'] in _VALUELESS:
        return f"{label} {OPERATORS[condition['op']]}"
    if kind == 'number':
        return f"{label} {_shown(value)}{unit} ({OPERATORS[condition['op']]} {_shown(condition['value'])}{unit})"
    text = _clean(value, 160)
    if condition['op'] == 'contains':
        found = next((term for term in expected if keyword_found([term], normalized_text(value), 'text')), expected[0])
        return f"{label} contains “{found.replace('+', ' + ')}”: {text}"
    return f"{label} “{text or '—'}” ({OPERATORS[condition['op']]} {condition['value']})"


def evaluate(compiled: list[dict[str, Any]], call: Any, inputs: dict[str, Any]) -> dict[str, str] | None:
    """The result of the first rule of the service of the call whose conditions hold, with the evidence; None when no
    rule takes the call."""
    try:
        service = str(call['service'] or '')
    except (KeyError, IndexError, TypeError):
        service = ''
    values: dict[str, Any] = {}

    def value_of(key: str) -> Any:
        if key not in values:
            if key == 'failure_text':
                values[key] = failure_text(call, inputs)
            elif key == 'radio_technology':
                values[key] = next((text for name in ('failure_technology', 'technology')
                                    if (text := _clean(_field(call, name)))), '') or _clean(inputs.get('rat'))
            elif key == 'radio_measured':
                values[key] = ', '.join(name for name, keys in (('LTE', ('lte_rsrp', 'lte_sinr')), ('NR', ('nr_rsrp', 'nr_sinr')))
                                        if any(_number(inputs.get(item)) is not None for item in keys))
            elif key in CALL_INPUTS:
                try:
                    values[key] = call[key]
                except (KeyError, IndexError, TypeError):
                    values[key] = ''
            else:
                values[key] = inputs.get(key)
        return values[key]

    for entry in compiled:
        if entry['services'] and service not in entry['services']:
            continue
        held = []
        for condition, kind, expected in entry['conditions']:
            value = value_of(condition['input'])
            if _holds(condition, kind, expected, value):
                held.append(_evidence(condition, kind, expected, value))
            elif entry['all']:
                break
        else:
            if entry['conditions'] and not held:
                continue
            rule = entry['rule']
            evidence = '; '.join(held) if held else 'No earlier rule explains the failure.'
            return {'rule': rule['name'], 'rule_key': rule['key'], **entry['result'], 'evidence': evidence[:MAX_EVIDENCE]}
    return None
