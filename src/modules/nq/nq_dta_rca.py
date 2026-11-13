"""DT Analyzer RCA: the root cause of every Non-Qualified Call, found from the data of its CDR.

It is an RCA source of the NQ Analysis Center in every workspace, whatever its CDR type: beside the RCA the provider
brings (the NetCheck RCA of NetCheck CDRs), the Ericsson RCA and the analysts, it always shows first.
Every call is read through the field profile of the workspace's CDR type (cdr_field_profiles ``nq_rca_sources``):
its result and failure (phase, technology, side and the provider's description of it, events and SCG failures), the
radio of LTE and NR on both sides (RSRP, RSRQ, SINR, BLER, transmit power and the resource blocks used), its mobility
(handovers, ping-pongs and the technologies it used) and its KPIs (throughput, access, DNS and TCP times, packet loss,
latency, setup time, speech quality and RTP). The Network Inventory adds the network around it (ran_context): how far
its serving site was against the inter-site distance (ISD) of that site, the nearest site, PCI collisions and cells out
of service on its sites.

Ordered rules decide: the first enabled rule of the service of the call whose conditions hold (all of them, or any of
them) gives its Root Category and Root Cause on the Root Cause Catalog of the workspace, their root domain and the
evidence, the values that matched. The default rules are the same in every workspace: what the provider reports outside
the radio first (device, subscription, lack of resources, core and IMS) and cells out of service, then the radio of the
call (coverage holes, overshooting and PCI collisions before the plain coverage and interference), its handovers, then
the service once the radio is not the cause (a cell short of resource blocks first), and a last rule for the calls none
of them explains. Admins edit them per workspace (order, conditions,
thresholds, category and cause); they travel with the NQ Calls configuration (export, import, transfers and backups).

non_qualified_calls stores the inputs of every indexed call and calculates the results when the calls are indexed and
whenever the rules or the Root Cause Catalog change.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from src.modules.nq.nq_catalog import keyword_found, keywords, normalized_text

ENGINE_VERSION = 9
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
MAX_RULES = 120
MAX_CONDITIONS = 8
MAX_TEXT = 120
MAX_EVIDENCE = 1200
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
    'signalling_events': ('Signalling events', 'text', '', 'Failure'),
    'failure_phase': ('Failure Phase', 'text', '', 'Failure'),
    'failure_technology': ('Failure Technology', 'text', '', 'Failure'),
    'failure_side': ('Failure Side', 'text', '', 'Failure'),
    'radio_technology': ('Technology at the failure', 'text', '', 'Failure'),
    'radio_rsrp': ('RSRP at the failure', 'number', 'dBm', 'Failure'),
    'radio_sinr': ('SINR at the failure', 'number', 'dB', 'Failure'),
    'radio_measured': ('Radio measured', 'text', '', 'Call'),
    'lte_rsrp': ('LTE RSRP (average)', 'number', 'dBm', 'LTE radio'),
    'lte_rsrp_min': ('LTE RSRP (minimum)', 'number', 'dBm', 'LTE radio'),
    'lte_rsrq': ('LTE RSRQ (average)', 'number', 'dB', 'LTE radio'),
    'lte_sinr': ('LTE SINR (average)', 'number', 'dB', 'LTE radio'),
    'lte_sinr_min': ('LTE SINR (minimum)', 'number', 'dB', 'LTE radio'),
    'lte_tx_power': ('LTE transmit power (maximum)', 'number', 'dBm', 'LTE radio'),
    'lte_bler': ('LTE BLER', 'number', '%', 'LTE radio'),
    'lte_dl_rb_share': ('LTE DL resource blocks used', 'number', '%', 'LTE radio'),
    'nr_rsrp': ('NR RSRP (average)', 'number', 'dBm', 'NR radio'),
    'nr_rsrp_min': ('NR RSRP (minimum)', 'number', 'dBm', 'NR radio'),
    'nr_rsrq': ('NR RSRQ (average)', 'number', 'dB', 'NR radio'),
    'nr_sinr': ('NR SINR (average)', 'number', 'dB', 'NR radio'),
    'nr_sinr_min': ('NR SINR (minimum)', 'number', 'dB', 'NR radio'),
    'nr_tx_power': ('NR transmit power (maximum)', 'number', 'dBm', 'NR radio'),
    'nr_bler': ('NR BLER', 'number', '%', 'NR radio'),
    'nr_dl_rb_share': ('NR DL resource blocks used', 'number', '%', 'NR radio'),
    'b_lte_rsrp': ('B side LTE RSRP (average)', 'number', 'dBm', 'B side radio'),
    'b_lte_sinr': ('B side LTE SINR (average)', 'number', 'dB', 'B side radio'),
    'b_nr_rsrp': ('B side NR RSRP (average)', 'number', 'dBm', 'B side radio'),
    'b_nr_sinr': ('B side NR SINR (average)', 'number', 'dB', 'B side radio'),
    'rat': ('Technologies used', 'text', '', 'Mobility'),
    'rat_timeline': ('Technology timeline', 'text', '', 'Mobility'),
    'handovers': ('Handovers', 'number', '', 'Mobility'),
    'handovers_info': ('Handover types', 'text', '', 'Mobility'),
    'ping_pong': ('Ping-pong handovers', 'number', '', 'Mobility'),
    'serving_distance': ('Serving site distance', 'number', 'km', 'Network Inventory'),
    'serving_isd': ('Serving site ISD', 'number', 'km', 'Network Inventory'),
    'serving_isd_ratio': ('Serving site distance / its ISD', 'number', '×', 'Network Inventory'),
    'nearest_site_distance': ('Nearest site distance', 'number', 'km', 'Network Inventory'),
    'nearest_site_isd_ratio': ('Nearest site distance / its ISD', 'number', '×', 'Network Inventory'),
    'pci_collisions': ('PCI collisions around', 'number', '', 'Network Inventory'),
    'cells_out_of_service': ('Cells out of service on its sites', 'number', '', 'Network Inventory'),
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
    # What the Layer3 Logs of the call tell (l3_dt_logs.call_evidence): only for the calls with a session in them, the
    # radio of its last seconds and what happened in the seconds before it failed.
    'l3_log': ('UEs with a Layer3 Log', 'text', '', 'Layer3 Logs'),
    'l3_signalling': ('Signalling before the failure (log)', 'text', '', 'Layer3 Logs'),
    'l3_ran_end': ('RAN Configuration at the failure (log)', 'text', '', 'Layer3 Logs'),
    'l3_lte_rsrp_end': ('LTE RSRP at the failure (log)', 'number', 'dBm', 'Layer3 Logs'),
    'l3_lte_sinr_end': ('LTE SINR at the failure (log)', 'number', 'dB', 'Layer3 Logs'),
    'l3_nr_rsrp_end': ('NR RSRP at the failure (log)', 'number', 'dBm', 'Layer3 Logs'),
    'l3_nr_sinr_end': ('NR SINR at the failure (log)', 'number', 'dB', 'Layer3 Logs'),
    'l3_lte_rsrp_min': ('LTE RSRP (minimum, log)', 'number', 'dBm', 'Layer3 Logs'),
    'l3_nr_rsrp_min': ('NR RSRP (minimum, log)', 'number', 'dBm', 'Layer3 Logs'),
    'l3_reestablishments': ('RRC re-establishments before the failure (log)', 'number', '', 'Layer3 Logs'),
    'l3_scg_failures': ('SCG failures before the failure (log)', 'number', '', 'Layer3 Logs'),
    'l3_handovers': ('Handovers before the failure (log)', 'number', '', 'Layer3 Logs'),
    'l3_irat': ('Inter-RAT moves before the failure (log)', 'number', '', 'Layer3 Logs'),
    'l3_releases': ('RRC releases before the failure (log)', 'number', '', 'Layer3 Logs'),
    'l3_rejects': ('Rejects in the signalling (log)', 'number', '', 'Layer3 Logs'),
    'l3_sip_error': ('SIP error (log)', 'number', '', 'Layer3 Logs'),
    'l3_tx_max': ('UE Tx Power before the failure (maximum, log)', 'number', 'dBm', 'Layer3 Logs'),
    'l3_tx_high_share': ('UE Tx Power from 22 dBm before the failure (log)', 'number', '%', 'Layer3 Logs'),
    'l3_neighbour_delta': ('Neighbour of the serving channel above the serving cell (log)', 'number', 'dB', 'Layer3 Logs'),
    'l3_neighbour_seconds': ('Seconds a neighbour was 3 dB above the serving cell (log)', 'number', 's', 'Layer3 Logs'),
    'l3_lte_bler': ('LTE BLER before the failure (log)', 'number', '%', 'Layer3 Logs'),
    'l3_nr_bler': ('NR BLER before the failure (log)', 'number', '%', 'Layer3 Logs'),
    'l3_no_measurements': ('Records without measurements (log)', 'number', '', 'Layer3 Logs'),
    # What the imported Ericsson RCA of the call measured in its logs before the failure (its evidence, ericsson_inputs):
    # the PCell of LTE and NR and the UE transmit power, the worst of its sides.
    'eri_lte_rsrp': ('LTE PCell RSRP before the failure (Ericsson RCA)', 'number', 'dBm', 'Ericsson RCA'),
    'eri_lte_sinr': ('LTE PCell SINR before the failure (Ericsson RCA)', 'number', 'dB', 'Ericsson RCA'),
    'eri_nr_rsrp': ('NR PCell RSRP before the failure (Ericsson RCA)', 'number', 'dBm', 'Ericsson RCA'),
    'eri_nr_sinr': ('NR PCell SINR before the failure (Ericsson RCA)', 'number', 'dB', 'Ericsson RCA'),
    'eri_tx_power': ('UE Tx Power before the failure (Ericsson RCA)', 'number', 'dBm', 'Ericsson RCA'),
    'eri_neighbour_delta': ('Neighbour above the PCell before the failure (Ericsson RCA)', 'number', 'dB', 'Ericsson RCA'),
    # The radio of each side of a voice call (UE A calls, MO; UE B is called, MT) at the failure, from its Layer3 Log, else
    # its Ericsson RCA: that of the side that failed (the Failure Side, else the failure description naming MO or MT
    # alone) and of the other side; the worst of both sides (or of the test) when the side that failed is unknown.
    'failed_side': ('Failed side (A = MO, B = MT)', 'text', '', 'Failed side radio'),
    **{f'{prefix}_{key}': (f'{label} of the {where}', kind, unit, group)
       for prefix, where, group in (('side', 'failed side', 'Failed side radio'), ('peer', 'other side', 'Other side radio'))
       for key, (label, kind, unit) in (
           ('lte_rsrp', ('LTE RSRP', 'number', 'dBm')), ('lte_sinr', ('LTE SINR', 'number', 'dB')),
           ('nr_rsrp', ('NR RSRP', 'number', 'dBm')), ('nr_sinr', ('NR SINR', 'number', 'dB')),
           ('tx_power', ('UE Tx Power', 'number', 'dBm')),
           ('lte_neighbour_delta', ('Strongest LTE neighbour above the PCell', 'number', 'dB')),
           ('nr_neighbour_delta', ('Strongest NR neighbour above the PCell', 'number', 'dB')))},
}
# The inputs that are indexed fields of the call, and the failure fields its description joins (with two CDR inputs).
CALL_INPUTS = ('result', 'test_name', 'technology', 'direction', 'environment', 'failure_phase', 'failure_technology')
FAILURE_TEXT_FIELDS = ('failure_classification', 'failure_category', 'failure_subcategory', 'failure_comment')
FAILURE_TEXT_INPUTS = ('failure_events', 'scg_failures')
# The inputs found from the others: the description of the failure, its signalling events alone (the events and SCG failures
# of the CDR, without the provider's RCA), the technology at the failure (the Failure Technology, else the technology of
# the call or the technologies it used) and its RSRP and SINR (those of NR when it failed in NR alone, else those of LTE,
# the anchor, each one else the other; of each technology the most precise one measured: its Layer3 Log at the failure,
# else the Ericsson RCA before the failure, else the average of the CDR), the radio measured (LTE and NR, by their RSRP or SINR) and the share of the
# resource blocks of the primary carrier the call used.
DERIVED_INPUTS = ('failure_text', 'signalling_events', 'radio_technology', 'radio_rsrp', 'radio_sinr', 'radio_measured', 'lte_dl_rb_share',
                  'nr_dl_rb_share', 'failed_side')
# The radio of the side that failed and of the other side (from the Layer3 Logs and the Ericsson RCA of the call).
SIDE_INPUTS = tuple(key for key in INPUTS if key.startswith(('side_', 'peer_')))
# The inputs of the network around the call (ran_context) and its ping-pongs, which non_qualified_calls adds from the
# Network Inventory and the cells of the call; a ``network_note`` names its serving and nearest sites for the evidence.
CONTEXT_INPUTS = ('ping_pong', 'serving_distance', 'serving_isd', 'serving_isd_ratio', 'nearest_site_distance',
                  'nearest_site_isd_ratio', 'pci_collisions', 'cells_out_of_service')
NETWORK_NOTE = 'network_note'
# Values read from the CDR that are no input themselves: the resource blocks and the bandwidth of the primary carriers (for
# the share used), and the cells of the call with their PCIs and where it ended (read through the Map fields of the profile).
RB_SOURCES = ('lte_dl_rbs', 'lte_dl_bandwidth', 'nr_dl_rbs', 'nr_dl_bandwidth', 'nr_dl_band')
TRACE_SOURCES = ('cell_trace', 'cell_pcis', 'end_latitude', 'end_longitude')
NUMBER_SOURCES = frozenset(('lte_dl_rbs', 'lte_dl_bandwidth', 'nr_dl_rbs', 'nr_dl_bandwidth', 'end_latitude', 'end_longitude'))
# The inputs of the Layer3 Logs of the call, which non_qualified_calls adds from its sessions (l3_dt_logs); an
# ``l3_note`` tells what its log shows before the failure, for the evidence.
L3_INPUTS = tuple(key for key in INPUTS if key.startswith('l3_'))
L3_NOTE = 'l3_note'
# The inputs of the Ericsson RCA imported for the call, which non_qualified_calls adds from its evidence.
ERICSSON_INPUTS = tuple(key for key in INPUTS if key.startswith('eri_'))
# Where the radio at the failure is read, the most precise first: (source, RSRP and SINR input of a technology).
RADIO_SOURCES = (('Layer3 Log, at the failure', 'l3_{tech}_{measure}_end'), ('Ericsson RCA, before the failure', 'eri_{tech}_{measure}'),
                 ('CDR, call average', '{tech}_{measure}'))
# The radio of each side of the call (A, B), which the Layer3 Logs (a session per UE) and the Ericsson RCA ("A: … | B: …")
# give apart: {side: {lte_rsrp, lte_sinr, nr_rsrp, nr_sinr, tx_power}}. The radio at the failure is read from the side
# that failed (Failure Side, MO = A and MT = B), and the evidence shows each side on its own.
SIDE_SOURCES = (('Layer3 Log, at the failure', 'l3_sides'), ('Ericsson RCA, before the failure', 'eri_sides'))
SIDES = ('A', 'B')
_SIDE_NAMES = {'a': 'A', 'mo': 'A', 'b': 'B', 'mt': 'B'}
# The inputs read from the CDR (the profile lists their columns).
CDR_INPUTS = tuple(key for key in (*INPUTS, *FAILURE_TEXT_INPUTS, *RB_SOURCES)
                   if key not in CALL_INPUTS and key not in DERIVED_INPUTS and key not in CONTEXT_INPUTS and key not in L3_INPUTS
                   and key not in ERICSSON_INPUTS and key not in SIDE_INPUTS)
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

# What the radio of a side of the call measured at the failure (Layer3 Log, else Ericsson RCA) tells, the most specific first:
# weak coverage, a stronger neighbour it did not hand over to, a neighbour as strong as the PCell with a low SINR (no
# dominant cell), a low SINR without one (interference) and the UE at high power (uplink). It comes before the causes
# the provider names (IMSI, TAU, QCI1, SIP, paging…), which a radio this poor can bring about, after the device and the
# rejects of the network; the other side of a voice call next, as the setup of a call needs both sides (the QCI1 bearer
# of the caller waits for the answer of the called side).
def _side_rules(prefix: str, where: str, services: tuple[str, ...]) -> tuple[tuple[Any, ...], ...]:
    rules = []
    for tech, label in (('lte', 'LTE'), ('nr', 'NR')):
        rules += [
            (f'{prefix}-{tech}-coverage', f'Weak {label} coverage on the {where}', services, 'all',
             ((f'{prefix}_{tech}_rsrp', 'lt', -110),), f'Poor Coverage {label}', 'Coverage'),
        ]
    for tech, label in (('lte', 'LTE'), ('nr', 'NR')):
        rules += [
            (f'{prefix}-{tech}-handover', f'Stronger {label} neighbour on the {where}', services, 'all',
             ((f'{prefix}_{tech}_neighbour_delta', 'ge', 3), (f'{prefix}_{tech}_sinr', 'lt', 3)), f'Mobility {label}',
             'Missing or late handover'),
            # A weak signal (below −105 dBm) with a low SINR is limited by the noise: coverage, not interference.
            (f'{prefix}-{tech}-weak-coverage', f'Weak {label} signal with a low SINR on the {where}', services, 'all',
             ((f'{prefix}_{tech}_rsrp', 'lt', -105), (f'{prefix}_{tech}_sinr', 'lt', 0)), f'Poor Coverage {label}', 'Coverage'),
            (f'{prefix}-{tech}-dominance', f'No dominant {label} cell on the {where}', services, 'all',
             ((f'{prefix}_{tech}_sinr', 'lt', 0), (f'{prefix}_{tech}_neighbour_delta', 'ge', -3), (f'{prefix}_{tech}_rsrp', 'ge', -105)),
             f'DL Interference {label}', 'Lack of dominant cell'),
            (f'{prefix}-{tech}-interference', f'{label} interference on the {where}', services, 'all',
             ((f'{prefix}_{tech}_sinr', 'lt', 0), (f'{prefix}_{tech}_rsrp', 'ge', -105)), f'DL Interference {label}', 'DL interference'),
        ]
    if prefix == 'side':
        rules += [
            ('side-uplink-coverage', 'UE at high power with weak coverage on the failed side', services, 'all',
             (('side_tx_power', 'ge', 21), ('side_lte_rsrp', 'lt', -100)), 'Poor Coverage LTE', 'Coverage'),
            ('side-uplink-interference', 'UE at high power with good coverage on the failed side', services, 'all',
             (('side_tx_power', 'ge', 21), ('side_lte_rsrp', 'ge', -95)), 'UL Interference LTE', 'UL interference'),
        ]
    return tuple(rules)


_SIDE_RULES = (*_side_rules('side', 'failed side', ()), *_side_rules('peer', 'other side', _VOICE))
SIDE_RULE_KEYS = tuple(rule[0] for rule in _SIDE_RULES)
# The rules of the network around the call (Network Inventory), which come before the radio of the sides.
NETWORK_RULE_KEYS = ('cell-outage', 'cell-outage-interference', 'nr-coverage-hole', 'coverage-hole', 'no-service-hole', 'nr-overshooting',
                     'overshooting', 'nr-overshooting-coverage', 'overshooting-coverage', 'nr-pci-collision', 'pci-collision')

# The default rules, in order: (key, name, services, match, conditions, Root Category, Root Cause). A text condition
# holds when the text contains one of its comma-separated terms ("a+b" needs both); a rule without conditions takes
# every call of its services that reaches it.
_DEFAULT_RULES: tuple[tuple[str, str, tuple[str, ...], str, tuple[tuple[str, str, Any], ...], str, str], ...] = (
    # What the provider reports outside the radio: the device, the subscription, the core and IMS.
    ('device', 'Device or test setup', (), 'any',
     (('failure_text', 'contains', 'modem, device, test setup, ue crash, at command, script error, battery'),),
     'UE / Test Setup Issue', 'Device or test setup'),
    # A log whose UE measured nothing: the device or the logging of the test.
    ('l3-no-measurements', 'No measurements in the drivetest log', (), 'all',
     (('l3_no_measurements', 'ge', 1), ('l3_lte_rsrp_end', 'empty', ''), ('l3_nr_rsrp_end', 'empty', '')),
     'UE / Test Setup Issue', 'Device or test setup'),
    # A lack of resources: the insufficient resources or congestion the provider reports of the core, and the access the
    # network rejects in the signalling of the CDR itself (or as the provider reports it).
    ('core-resources', 'Insufficient resources of the core', (), 'any',
     (('failure_text', 'contains', 'insufficient resources, service reject+congestion'),), 'Core Network', 'Insufficient resources'),
    ('access-rejected', 'Access rejected by the network', (), 'any',
     (('signalling_events', 'contains', 'rrcconnectionreject, rrcreject, immediate assignment reject'),
      ('failure_text', 'contains', 'rrc connection reject'), ('l3_signalling', 'contains', 'rrcconnectionreject, rrcreject')),
     'RAN Capacity', 'Access rejected (no resources)'),
    ('authentication', 'Authentication or registration rejected', (), 'any',
     (('failure_text', 'contains', 'authentication, authorization, registration reject, attach reject, '
                                   'pdu session establishment reject'),
      ('l3_signalling', 'contains', 'authentication reject, registration reject, attach reject, pdu session establishment reject')),
     'Authentication & Registration', 'Authentication/Authorization'),
    # Cells of its sites out of service in the Network Inventory, when its radio suffered.
    ('cell-outage', 'Cells out of service on its sites', (), 'all', (('cells_out_of_service', 'ge', 1), ('radio_rsrp', 'lt', -105)),
     'Operational', 'Cell/Site Outage'),
    ('cell-outage-interference', 'Cells out of service on its sites with interference', (), 'all',
     (('cells_out_of_service', 'ge', 1), ('radio_sinr', 'lt', 3)), 'Operational', 'Cell/Site Outage'),
    # The network around the call (Network Inventory), before the coverage and interference it brings: no site near it (the
    # nearest one beyond 1.5 times its inter-site distance), a serving site beyond twice its inter-site distance, a cell
    # around with the PCI and channel of one of its own.
    ('nr-coverage-hole', 'NR coverage hole', (), 'all', (('nearest_site_isd_ratio', 'ge', 1.5), ('nr_rsrp', 'lt', -110), *_NR),
     'Poor Coverage NR', 'Large distance to the nearest site'),
    ('coverage-hole', 'Coverage hole', (), 'all', (('nearest_site_isd_ratio', 'ge', 1.5), ('lte_rsrp', 'lt', -110)),
     'Poor Coverage LTE', 'Large distance to the nearest site'),
    ('no-service-hole', 'Coverage hole without service', (), 'all', (('nearest_site_isd_ratio', 'ge', 1.5), ('radio_measured', 'empty', '')),
     'Poor Coverage LTE', 'Large distance to the nearest site'),
    ('nr-overshooting', 'NR overshooting', (), 'all',
     (('serving_isd_ratio', 'ge', 2), ('serving_distance', 'ge', 1), ('nr_sinr', 'lt', 3), *_NR),
     'DL Interference NR', 'Overshooting or excessive cell overlap'),
    ('overshooting', 'Overshooting', (), 'all', (('serving_isd_ratio', 'ge', 2), ('serving_distance', 'ge', 1), ('lte_sinr', 'lt', 3)),
     'DL Interference LTE', 'Overshooting or excessive cell overlap'),
    ('nr-overshooting-coverage', 'NR overshooting with weak coverage', (), 'all',
     (('serving_isd_ratio', 'ge', 2), ('serving_distance', 'ge', 1), ('nr_rsrp', 'lt', -105), *_NR),
     'Poor Coverage NR', 'Overshooting or excessive cell overlap'),
    ('overshooting-coverage', 'Overshooting with weak coverage', (), 'all',
     (('serving_isd_ratio', 'ge', 2), ('serving_distance', 'ge', 1), ('lte_rsrp', 'lt', -105)),
     'Poor Coverage LTE', 'Overshooting or excessive cell overlap'),
    ('nr-pci-collision', 'NR PCI collision', (), 'all', (('pci_collisions', 'ge', 1), ('nr_sinr', 'lt', 3), *_NR),
     'DL Interference NR', 'PCI Collision/PCI MOD 3 Collision'),
    ('pci-collision', 'PCI collision', (), 'all', (('pci_collisions', 'ge', 1), ('lte_sinr', 'lt', 3)),
     'DL Interference LTE', 'PCI Collision/PCI MOD 3 Collision'),
    *_SIDE_RULES,
    ('subscriber-identity', 'Subscriber identity', (), 'any',
     (('failure_text', 'contains', 'imsi, ue identity cannot be derived'),), 'IMSI Issue', ''),
    ('tracking-area-update', 'Tracking area update', (), 'any',
     (('failure_text', 'contains', 'tracking area update'), ('l3_signalling', 'contains', 'tracking area update reject')),
     'Core Network', 'TAU reject'),
    ('bearer-deactivation', 'Bearer deactivated by the network', (), 'any',
     (('failure_text', 'contains', 'bearer deactivation, deregistered, detach request'),), 'Core Network', 'EPS bearer deactivation'),
    ('qci1', 'No QCI1 bearer for the call', _VOICE, 'any', (('failure_text', 'contains', 'qci1, qci 1'),), 'IMS / VoLTE',
     'No QCI1 established'),
    ('ims-core', 'VoLTE or IMS core', _VOICE, 'any',
     (('failure_text', 'contains', 'volte core, ims core, ims registration, sip, server internal error'),
      ('l3_sip_error', 'ge', 400)), 'IMS / VoLTE', 'VoLTE core'),
    ('eps-fallback', 'EPS fallback', _VOICE, 'any', (('failure_text', 'contains', 'epsfb, eps fallback'),), 'EPS Fallback',
     'EPS fallback failure'),
    ('paging', 'Paging', (), 'any', (('failure_text', 'contains', 'paging'),), 'RAN Performance', 'Paging'),
    ('session-in-gsm', 'Session in GSM', (), 'any', (('failure_text', 'contains', 'session in gsm'),), 'Core Network',
     'WhatsApp session in GSM'),
    # What the Layer3 Logs of the call show at its failure, more precise than the averages of the CDR: the radio of
    # its last seconds and what failed before it (a call without a log goes on to the rules of its CDR).
    ('l3-scg-failure-coverage', 'SCG failure with weak NR coverage (drivetest log)', (), 'all',
     (('l3_scg_failures', 'ge', 1), ('l3_nr_rsrp_end', 'lt', -110)), 'Poor Coverage NR', 'Coverage'),
    ('l3-reestablishment-coverage', 'Re-establishment with weak LTE coverage (drivetest log)', (), 'all',
     (('l3_reestablishments', 'ge', 1), ('l3_lte_rsrp_end', 'lt', -110)), 'Poor Coverage LTE', 'Coverage'),
    ('l3-missing-handover', 'Stronger neighbour without a handover (drivetest log)', (), 'all',
     (('l3_neighbour_delta', 'ge', 6), ('l3_neighbour_seconds', 'ge', 3), ('l3_handovers', 'eq', 0)),
     'Mobility LTE', 'Missing or late handover'),
    ('l3-lte-coverage', 'Weak LTE coverage at the failure (drivetest log)', (), 'all', (('l3_lte_rsrp_end', 'lt', -115),),
     'Poor Coverage LTE', 'Coverage'),
    ('l3-nr-coverage', 'Weak NR coverage at the failure (drivetest log)', (), 'all',
     (('l3_nr_rsrp_end', 'lt', -115), ('l3_ran_end', 'contains', '5g sa')), 'Poor Coverage NR', 'Coverage'),
    ('l3-uplink', 'UE at maximum power before the failure (drivetest log)', (), 'all',
     (('l3_tx_high_share', 'ge', 50), ('l3_lte_rsrp_end', 'lt', -100)), 'Poor Coverage LTE', 'Coverage'),
    ('l3-lte-interference', 'LTE interference at the failure (drivetest log)', (), 'all',
     (('l3_lte_sinr_end', 'lt', -3), ('l3_lte_rsrp_end', 'ge', -105)), 'DL Interference LTE', 'DL interference'),
    ('l3-nr-interference', 'NR interference at the failure (drivetest log)', (), 'all',
     (('l3_nr_sinr_end', 'lt', -3), ('l3_nr_rsrp_end', 'ge', -105), ('l3_ran_end', 'contains', '5g')), 'DL Interference NR',
     'DL interference'),
    ('l3-scg-failure', 'SCG failure before the failure (drivetest log)', (), 'all', (('l3_scg_failures', 'ge', 1),),
     'RAN Performance', 'RRC layer'),
    ('l3-reestablishment', 'RRC re-establishment before the failure (drivetest log)', (), 'all', (('l3_reestablishments', 'ge', 1),),
     'RAN Performance', 'RRC layer'),
    ('l3-lte-bler', 'High LTE BLER before the failure (drivetest log)', (), 'all', (('l3_lte_bler', 'gt', 30),), 'BLER LTE', 'BLER'),
    ('l3-nr-bler', 'High NR BLER before the failure (drivetest log)', (), 'all', (('l3_nr_bler', 'gt', 30),), 'BLER NR', 'BLER'),
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
    # Its handovers: back and forth between two cells, then the handover failures.
    ('nr-ping-pong', 'NR ping-pong handovers', (), 'all', (('ping_pong', 'ge', 1), *_NR), 'Mobility NR', 'Ping-pong handover'),
    ('ping-pong', 'Ping-pong handovers', (), 'all', (('ping_pong', 'ge', 1),), 'Mobility LTE', 'Ping-pong handover'),
    ('nr-handover', 'NR handover failure', (), 'all',
     (('failure_text', 'contains', 'handover'), ('failure_technology', 'contains', '5g, nr')), 'Mobility NR', 'Handover failure'),
    ('handover', 'Handover failure', (), 'any',
     (('failure_text', 'contains', 'handover'), ('l3_signalling', 'contains', 'handover failure')), 'Mobility LTE', 'Handover failure'),
    ('radio-link', 'Radio link failure', (), 'any',
     (('failure_text', 'contains', 'radio link failure, t310, reestablishment, random access, rach, scg failure, scgfailure, rrc'),
      ('l3_signalling', 'contains', 'radio link failure, rlf')), 'RAN Performance', 'RRC layer'),
    ('inter-rat', 'Inter-RAT transition', (), 'any',
     (('failure_text', 'contains', 'inter-rat, irat, redirection, 4g -> 5g, 5g -> 4g'), ('l3_irat', 'ge', 1)),
     'RAN Performance', 'Inter-RAT transition'),
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
    # A test cut off with good radio on a carrier that gave it few of its resource blocks: a loaded cell.
    ('nr-cell-load', 'NR cell short of resource blocks', ('data',), 'all',
     (('result', 'contains', 'cutoff'), _MEASURED, ('nr_dl_rb_share', 'lt', 25)), 'RAN Capacity', 'Cell overload'),
    ('cell-load', 'Cell short of resource blocks', ('data',), 'all',
     (('result', 'contains', 'cutoff'), _MEASURED, ('lte_dl_rb_share', 'lt', 25)), 'RAN Capacity', 'Cell overload'),
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


# The default rules each version of the engine added: a workspace with rules of its own takes them once, in their place.
ADDED_RULES = {
    2: ('core-resources', 'access-rejected', 'cell-outage', 'cell-outage-interference', 'nr-coverage-hole', 'coverage-hole', 'no-service-hole', 'nr-overshooting',
        'overshooting', 'nr-overshooting-coverage', 'overshooting-coverage', 'nr-pci-collision', 'pci-collision', 'nr-ping-pong',
        'ping-pong', 'nr-cell-load', 'cell-load'),
    # The rules of the Layer3 Logs.
    4: ('l3-no-measurements', 'l3-scg-failure-coverage', 'l3-reestablishment-coverage', 'l3-missing-handover', 'l3-lte-coverage',
        'l3-nr-coverage', 'l3-uplink', 'l3-lte-interference', 'l3-nr-interference', 'l3-scg-failure', 'l3-reestablishment',
        'l3-lte-bler', 'l3-nr-bler'),
    # The radio of the failed side and of the other side (Layer3 Logs and Ericsson RCA).
    8: tuple(key for key in SIDE_RULE_KEYS if not key.endswith('-weak-coverage')),
    # A weak signal with a low SINR is coverage, before the lack of dominant cell and the interference.
    9: tuple(key for key in SIDE_RULE_KEYS if key.endswith('-weak-coverage')),
}
# The default rules each version of the engine moved: (rules, the rule they followed, the rule they now follow). A
# workspace whose rules are still together right after the one they followed (as the default rules had them) takes the new
# place, once, before the new rules of that version are added.
MOVED_RULES = {8: ((NETWORK_RULE_KEYS, 'session-in-gsm', 'authentication'),
                   (('subscriber-identity',), 'l3-no-measurements', SIDE_RULE_KEYS[-1]))}
# The default rules each version of the engine changed, with their conditions before it: a workspace whose rule is still
# as it was takes the new conditions, a rule an admin changed is kept as it is.
CHANGED_RULES = {
    9: {
        **{f'{prefix}-{tech}-dominance': ((f'{prefix}_{tech}_sinr', 'lt', 0), (f'{prefix}_{tech}_neighbour_delta', 'ge', -3))
           for prefix in ('side', 'peer') for tech in ('lte', 'nr')},
        **{f'{prefix}-{tech}-interference': ((f'{prefix}_{tech}_sinr', 'lt', 0), (f'{prefix}_{tech}_rsrp', 'ge', -110))
           for prefix in ('side', 'peer') for tech in ('lte', 'nr')},
    },
    4: {
        'access-rejected': (('signalling_events', 'contains', 'rrcconnectionreject, rrcreject, immediate assignment reject'),
                            ('failure_text', 'contains', 'rrc connection reject')),
        'authentication': (('failure_text', 'contains', 'authentication, authorization, registration reject, attach reject, '
                                                        'pdu session establishment reject'),),
        'tracking-area-update': (('failure_text', 'contains', 'tracking area update'),),
        'ims-core': (('failure_text', 'contains', 'volte core, ims core, ims registration, sip, server internal error'),),
        'handover': (('failure_text', 'contains', 'handover'),),
        'radio-link': (('failure_text', 'contains', 'radio link failure, t310, reestablishment, random access, rach, scg failure, '
                                                    'scgfailure, rrc'),),
        'inter-rat': (('failure_text', 'contains', 'inter-rat, irat, redirection, 4g -> 5g, 5g -> 4g'),),
    },
}


def with_added_rules(rules: list[dict[str, Any]], keys: tuple[str, ...]) -> tuple[list[dict[str, Any]], list[str]]:
    """The rules of a workspace with the default rules of ``keys`` it lacks (by key and name), each right after the
    nearest default rule before it that the workspace has (first when none), within MAX_RULES; and the names added."""
    result = list(rules)
    added = []
    defaults = default_rules()
    for position, rule in enumerate(defaults):
        names = {item['name'].casefold() for item in result}
        present = {item['key'] for item in result}
        if rule['key'] not in keys or rule['key'] in present or rule['name'].casefold() in names or len(result) >= MAX_RULES:
            continue
        anchor = next((item['key'] for item in reversed(defaults[:position]) if item['key'] in present), None)
        place = next((index + 1 for index, item in enumerate(result) if item['key'] == anchor), 0)
        result.insert(place, rule)
        added.append(rule['name'])
    return result, added


def move_default_rules(repository: Any, version: int) -> list[str]:
    """Move the default rules of ``version`` in the rules of a workspace (with rules of its own) to their new place,
    where they are still right after the rule they followed; App Events says which."""
    try:
        stored = json.loads(repository.get_workspace_state(RULES_STATE_KEY) or 'null')
    except (TypeError, ValueError):
        stored = None
    if not isinstance(stored, list) or not stored:
        return []
    rules = normalize_rules(stored)
    moved = []
    for block, before, after in MOVED_RULES.get(version, ()):
        keys = [rule['key'] for rule in rules]
        if before not in keys or after not in keys or any(key not in keys for key in block):
            continue
        first = keys.index(before) + 1
        if keys[first:first + len(block)] != list(block):
            continue
        taken = rules[first:first + len(block)]
        del rules[first:first + len(block)]
        place = [item['key'] for item in rules].index(after) + 1
        rules[place:place] = taken
        moved += [rule['name'] for rule in taken]
    if moved:
        repository.set_workspace_state(RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
        if hasattr(repository, 'try_add_log'):
            repository.try_add_log('system', 'nq_dta_rca_rules', json.dumps(
                {'message': 'Default rules of the DT Analyzer RCA moved in the rules of the workspace.', 'rules': len(rules),
                 'enabled': sum(rule['enabled'] for rule in rules),
                 'changes': [f'Rule moved: {name}' for name in moved]}, ensure_ascii=False))
    return moved


def add_new_default_rules(repository: Any, version: int) -> list[str]:
    """Give a workspace with rules of its own the default rules of ``version`` it lacks; App Events says which (the
    workspaces with the default rules take them anyway)."""
    try:
        stored = json.loads(repository.get_workspace_state(RULES_STATE_KEY) or 'null')
    except (TypeError, ValueError):
        stored = None
    if not isinstance(stored, list) or not stored:
        return []
    rules, added = with_added_rules(normalize_rules(stored), ADDED_RULES.get(version, ()))
    if added:
        repository.set_workspace_state(RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
        if hasattr(repository, 'try_add_log'):
            repository.try_add_log('system', 'nq_dta_rca_rules', json.dumps(
                {'message': 'New default rules of the DT Analyzer RCA added to the rules of the workspace.', 'rules': len(rules),
                 'enabled': sum(rule['enabled'] for rule in rules), 'changes': [f'Rule added: {name}' for name in added]},
                ensure_ascii=False))
    return added


def renew_changed_default_rules(repository: Any, version: int) -> list[str]:
    """Give the rules of a workspace (with rules of its own) the conditions the default rules of ``version`` changed,
    where they are still as they were; App Events says which (the workspaces with the default rules take them anyway)."""
    try:
        stored = json.loads(repository.get_workspace_state(RULES_STATE_KEY) or 'null')
    except (TypeError, ValueError):
        stored = None
    if not isinstance(stored, list) or not stored:
        return []
    rules = normalize_rules(stored)
    former = {key: [{'input': input_key, 'op': op, 'value': value} for input_key, op, value in conditions]
              for key, conditions in CHANGED_RULES.get(version, {}).items()}
    defaults = {rule['key']: rule for rule in default_rules()}
    renewed = []
    for rule in rules:
        before = former.get(rule['key'])
        if before is not None and normalize_rules([{**rule, 'conditions': before}])[0]['conditions'] == rule['conditions']:
            rule['conditions'] = [dict(condition) for condition in defaults[rule['key']]['conditions']]
            renewed.append(rule['name'])
    if renewed:
        repository.set_workspace_state(RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
        if hasattr(repository, 'try_add_log'):
            repository.try_add_log('system', 'nq_dta_rca_rules', json.dumps(
                {'message': 'Default rules of the DT Analyzer RCA renewed in the rules of the workspace.', 'rules': len(rules),
                 'enabled': sum(rule['enabled'] for rule in rules), 'changes': [f'Rule renewed: {name}' for name in renewed]},
                ensure_ascii=False))
    return renewed


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


def fingerprint(rules: list[dict[str, Any]], taxonomy: dict[str, Any], network: str = '') -> str:
    """What the results depend on: the version of the engine, the rules, the catalog values they resolve to and the
    network around the calls (the Network Inventory and the networks serving each operator, ``network``)."""
    catalog = {plural: [[item.get('name'), item.get('domain'), item.get('category'), item.get('keywords')]
                        for item in taxonomy.get(plural) or []] for plural in ('domains', 'categories', 'causes')}
    payload = json.dumps([ENGINE_VERSION, rules, catalog] + ([network] if network else []), sort_keys=True, ensure_ascii=False,
                         default=str)
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


# The resource blocks of a carrier by its bandwidth (MHz): LTE (TS 36.101), NR at 15 kHz and at 30 kHz (TS 38.101-1),
# which the TDD bands and the carriers wider than 50 MHz use.
LTE_RESOURCE_BLOCKS = {1.4: 6, 3: 15, 5: 25, 10: 50, 15: 75, 20: 100}
NR_RESOURCE_BLOCKS_15 = {5: 25, 10: 52, 15: 79, 20: 106, 25: 133, 30: 160, 40: 216, 50: 270}
NR_RESOURCE_BLOCKS_30 = {10: 24, 15: 38, 20: 51, 25: 65, 30: 78, 40: 106, 50: 133, 60: 162, 70: 189, 80: 217, 90: 245, 100: 273}
NR_TDD_BANDS = frozenset(('n38', 'n40', 'n41', 'n48', 'n77', 'n78', 'n79'))


def resource_block_share(blocks: Any, bandwidth: Any, technology: str, band: Any = '') -> float | None:
    """The share (%) of the resource blocks of its primary carrier the call was given on average."""
    blocks, bandwidth = _number(blocks), _number(bandwidth)
    if not blocks or not bandwidth:
        return None
    if technology == 'LTE':
        total = LTE_RESOURCE_BLOCKS.get(bandwidth) or bandwidth * 5
    else:
        match = re.search(r'(\d+)', str(band or ''))
        wide = bandwidth > 50 or (match is not None and f'n{match.group(1)}' in NR_TDD_BANDS)
        total = (NR_RESOURCE_BLOCKS_30 if wide else NR_RESOURCE_BLOCKS_15).get(int(round(bandwidth)))
    return round(min(blocks / total * 100, 100.0), 1) if total else None


def signalling_events(inputs: dict[str, Any]) -> str:
    """The events and SCG failures of the CDR, without the provider's RCA."""
    return ' · '.join(value for key in FAILURE_TEXT_INPUTS if (value := _clean(inputs.get(key), 300)))


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


# The averages of the call the provider writes in its failure comment (NetCheck), a block per technology:
# "(ENDC-5G)Mean RSRP, Mean SINR, %RSRP<=-115dBm, %SINR<=0dB : -71.54dBm 6.77dB 3% 10%" (decimals with a comma too).
_NUMBER = r'-?\d+(?:[.,]\d+)?'
_AVERAGES = re.compile(
    rf'\(([^()]{{1,20}})\)\s*Mean RSRP,\s*Mean SINR,\s*%RSRP\s*<=\s*({_NUMBER})\s*dBm,\s*%SINR\s*<=\s*({_NUMBER})\s*dB\s*:\s*'
    rf'({_NUMBER})\s*dBm\s+({_NUMBER})\s*dB(?:\s+({_NUMBER})\s*%)?(?:\s+({_NUMBER})\s*%)?', re.IGNORECASE)
# The radio of the PCell the Ericsson RCA writes in its evidence, by side ("A: … | B: …"):
# "LTE PCell RSRP=-82.8 dBm, SINR=5.2375, TxPower=-13.0; none of the … conditions matched."
_ERICSSON_PCELL = re.compile(r'\b(LTE|NR) PCell RSRP\s*=\s*(-?\d+(?:\.\d+)?)', re.IGNORECASE)
_ERICSSON_VALUE = {'sinr': re.compile(r'\bSINR\s*=\s*(-?\d+(?:\.\d+)?)'), 'tx_power': re.compile(r'\bTxPower\s*=\s*(-?\d+(?:\.\d+)?)'),
                   'neighbour_delta': re.compile(r'\bRSRP diff\s*=\s*(-?\d+(?:\.\d+)?)')}


def _decimal(text: str | None) -> float | None:
    return _number(text.replace(',', '.')) if text else None


def provider_averages(text: Any) -> list[dict[str, Any]]:
    """The averages of the call in the provider's failure comment, a block per technology (its label as written, such as
    ENDC-5G): mean RSRP and SINR and the share of the samples at or below the RSRP and SINR thresholds."""
    blocks = []
    for match in _AVERAGES.finditer(str(text or '')):
        label, rsrp_limit, sinr_limit, rsrp, sinr, rsrp_share, sinr_share = match.groups()
        blocks.append({'label': label.strip(), 'rsrp': _decimal(rsrp), 'sinr': _decimal(sinr), 'rsrp_limit': _decimal(rsrp_limit),
                       'sinr_limit': _decimal(sinr_limit), 'rsrp_share': _decimal(rsrp_share), 'sinr_share': _decimal(sinr_share)})
    return blocks


def ericsson_inputs(evidence: Any) -> dict[str, Any]:
    """The radio the Ericsson RCA measured before the failure, from its evidence: the RSRP and SINR of the LTE and NR
    PCell, the UE transmit power and how far a neighbour was above the PCell, the worst of its sides (the lowest RSRP and
    SINR, the highest power and neighbour), and in ``eri_sides`` those of each side it names (A, B)."""
    found: dict[str, list[float]] = {}
    sides: dict[str, dict[str, float]] = {}
    for part in str(evidence or '').split(' | '):
        named = re.match(r'\s*(?:UE\s*)?([AB])\s*:', part, re.IGNORECASE)
        side = sides.setdefault(named.group(1).upper(), {}) if named else {}
        matches = list(_ERICSSON_PCELL.finditer(part))
        for index, match in enumerate(matches):
            # The SINR and power of a PCell are written after it, before the next PCell of the part.
            end = matches[index + 1].start() if index + 1 < len(matches) else len(part)
            technology = match.group(1).lower()
            values = {f'{technology}_rsrp': float(match.group(2))}
            sinr = _ERICSSON_VALUE['sinr'].search(part, match.end(), end)
            if sinr:
                values[f'{technology}_sinr'] = float(sinr.group(1))
            power = _ERICSSON_VALUE['tx_power'].search(part, match.end(), end)
            if power and _number(power.group(1)) is not None:
                values['tx_power'] = float(power.group(1))
            # A stronger neighbour it found than the PCell (RSRP diff, of the same frequency or another).
            delta = _ERICSSON_VALUE['neighbour_delta'].search(part, match.end(), end)
            if delta:
                values[f'{technology}_neighbour_delta'] = float(delta.group(1))
            for key, value in values.items():
                found.setdefault('eri_neighbour_delta' if key.endswith('neighbour_delta') else f'eri_{key}', []).append(value)
                side.setdefault(key, round(value, 2))
    result: dict[str, Any] = {key: round(max(values) if key in {'eri_tx_power', 'eri_neighbour_delta'} else min(values), 2)
                              for key, values in found.items()}
    if any(sides.values()):
        result['eri_sides'] = {name: values for name, values in sides.items() if values}
    return result


def failed_side(call: Any, inputs: dict[str, Any]) -> str:
    """The side of the call that failed: A or B from the Failure Side of the CDR (MO = A, MT = B), else from the failure
    description when it names one side only; empty when unknown."""
    side = _SIDE_NAMES.get(normalized_text(inputs.get('failure_side')).strip(), '')
    if side:
        return side
    text = failure_text(call, inputs)
    named = {_SIDE_NAMES[word.lower()] for word in re.findall(r'\b(MO|MT)\b', text)}
    return named.pop() if len(named) == 1 else ''


# The values of the radio of a side (SIDE_INPUTS without their prefix), the inputs of the worst of the sides of the call
# that stand for each one when the side that failed is unknown (Layer3 Log, Ericsson RCA) and whether the highest is the
# worst. The strongest neighbour is the highest the sources found (the log measures the channel of the PCell, the
# Ericsson RCA the other frequencies too).
_SIDE_VALUES = {
    'lte_rsrp': (('l3_lte_rsrp_end', 'eri_lte_rsrp'), False), 'lte_sinr': (('l3_lte_sinr_end', 'eri_lte_sinr'), False),
    'nr_rsrp': (('l3_nr_rsrp_end', 'eri_nr_rsrp'), False), 'nr_sinr': (('l3_nr_sinr_end', 'eri_nr_sinr'), False),
    'tx_power': (('l3_tx_max', 'eri_tx_power'), True), 'lte_neighbour_delta': (('l3_neighbour_delta',), True),
    'nr_neighbour_delta': ((), True),
}


def side_value(inputs: dict[str, Any], side: str, key: str) -> tuple[float | None, str]:
    """A value of the radio of one side of the call (``side`` A or B), or of the worst of its sides (``side`` empty),
    from the Layer3 Log, else the Ericsson RCA, with where it was read."""
    aggregated, highest = _SIDE_VALUES[key]
    pick = max if highest else min
    if key.endswith('neighbour_delta'):
        # Every source: they measure different neighbours.
        found = [(number, source) for source, sides_key in SIDE_SOURCES
                 for name, values in (inputs.get(sides_key) or {}).items() if isinstance(inputs.get(sides_key), dict)
                 and (not side or name == side) and (number := _number((values or {}).get(key))) is not None]
        found += [(number, source) for source, input_key in zip((item[0] for item in SIDE_SOURCES), aggregated)
                  if not side and (number := _number(inputs.get(input_key))) is not None]
        if not found:
            return None, ''
        number, source = pick(found, key=lambda item: item[0])
        return number, (f'UE {side}, {source}' if side else source)
    for (source, sides_key), input_key in zip(SIDE_SOURCES, (*aggregated, None, None)):
        sides = inputs.get(sides_key) if isinstance(inputs.get(sides_key), dict) else {}
        numbers = [number for name, values in sides.items() if (not side or name == side)
                   and (number := _number((values or {}).get(key))) is not None]
        if not numbers and not side and input_key and (number := _number(inputs.get(input_key))) is not None:
            numbers = [number]
        if numbers:
            return pick(numbers), (f'UE {side}, {source}' if side else source)
    return None, ''


def side_radio(inputs: dict[str, Any], side: str, technology: str, measure: str) -> tuple[float | None, str]:
    """The RSRP or SINR (``measure``) of a technology on one side of the call from its most precise source that has it,
    with that source."""
    for source, key in SIDE_SOURCES:
        sides = inputs.get(key)
        number = _number((sides.get(side) or {}).get(f'{technology}_{measure}')) if isinstance(sides, dict) else None
        if number is not None:
            return number, source
    return None, ''


def provider_description(call: Any, inputs: dict[str, Any]) -> str:
    """The provider's description of the failure for the evidence: its failure fields, events and SCG failures, without
    the averages of its comment (shown on their own line) and with a space after each technology label."""
    values = []
    for key in FAILURE_TEXT_FIELDS:
        text = str(_field(call, key) or '')
        if key == 'failure_comment':
            text = _AVERAGES.sub(' ', text)
        values.append(_clean(re.sub(r'\)(?=[^\s),.;:])', ') ', text), 300))
    values += [_clean(inputs.get(key), 300) for key in FAILURE_TEXT_INPUTS]
    return ' · '.join(dict.fromkeys(value for value in values if value))


def _measure(value: Any, unit: str) -> str:
    return f'{_shown(value)} {unit}'


def averages_line(call: Any, inputs: dict[str, Any]) -> str:
    """The averages of the whole call: those of the provider's comment, else those of the CDR."""
    blocks = provider_averages(_field(call, 'failure_comment'))
    if blocks:
        parts = []
        for block in blocks:
            text = f"{block['label']} mean RSRP {_measure(block['rsrp'], 'dBm')}, mean SINR {_measure(block['sinr'], 'dB')}"
            shares = [f"RSRP ≤ {_measure(block['rsrp_limit'], 'dBm')} in {_shown(block['rsrp_share'])} %" if block['rsrp_share'] is not None else '',
                      f"SINR ≤ {_measure(block['sinr_limit'], 'dB')} in {_shown(block['sinr_share'])} %" if block['sinr_share'] is not None else '']
            shares = [share for share in shares if share]
            parts.append(text + (f" ({', '.join(shares)} of the samples)" if shares else ''))
        return 'Call average (provider comment): ' + ' · '.join(parts)
    parts = []
    for technology in ('lte', 'nr'):
        values = [f'{name} {_measure(number, unit)}' for name, key, unit in (('RSRP', f'{technology}_rsrp', 'dBm'), ('SINR', f'{technology}_sinr', 'dB'))
                  if (number := _number(inputs.get(key))) is not None]
        if values:
            parts.append(f"{technology.upper()} {', '.join(values)}")
    return 'Call average (CDR): ' + ' · '.join(parts) if parts else ''


def _side_text(values: dict[str, Any], logged: bool) -> str:
    parts = []
    for technology in ('lte', 'nr'):
        found = [f"{name} {_measure(number, unit)}" for name, measure, unit in (('RSRP', 'rsrp', 'dBm'), ('SINR', 'sinr', 'dB'))
                 if (number := _number(values.get(f'{technology}_{measure}'))) is not None]
        if found:
            parts.append(f"{technology.upper()} PCell {', '.join(found)}")
    power = _number(values.get('tx_power'))
    if power is not None:
        parts.append(f"UE Tx Power{' (maximum)' if logged else ''} {_measure(power, 'dBm')}")
    for technology in ('lte', 'nr'):
        delta = _number(values.get(f'{technology}_neighbour_delta'))
        if delta is not None:
            parts.append(f"strongest {technology.upper()} neighbour {_measure(abs(delta), 'dB')} "
                         f"{'above' if delta >= 0 else 'below'} the PCell")
    # A finding each, as the Ericsson RCA separates them: the page shows them as bullets.
    return '; '.join(parts)


def radio_line(inputs: dict[str, Any], failed: str = '') -> str:
    """The radio before the failure from each source that measured it, a line each, the most precise first: the Layer3
    Log of the call at the failure and the Ericsson RCA (its logs before the failure); empty when only the averages of
    the CDR have it. With both sides of the call measured, each side on its own ("A (failed side): … | B: …")."""
    lines = []
    for (source, template), (_source, key) in zip(RADIO_SOURCES[:2], SIDE_SOURCES):
        logged = source.startswith('Layer3')
        sides = inputs.get(key) if isinstance(inputs.get(key), dict) else {}
        texts = [(side, text) for side in SIDES if (text := _side_text(sides.get(side) or {}, logged))]
        if len(texts) > 1 or (texts and failed):
            lines.append(f"Radio ({source}): " + ' | '.join(f"{side}{' (failed side)' if side == failed else ''}: {text}"
                                                            for side, text in texts))
            continue
        parts = []
        for technology in ('lte', 'nr'):
            values = [f"{name} {_measure(number, unit)}" for name, measure, unit in (('RSRP', 'rsrp', 'dBm'), ('SINR', 'sinr', 'dB'))
                      if (number := _number(inputs.get(template.format(tech=technology, measure=measure)))) is not None]
            if values:
                parts.append(f"{technology.upper()} PCell {', '.join(values)}")
        if parts:
            power = _number(inputs.get('l3_tx_max' if logged else 'eri_tx_power'))
            # The log gives the highest UE Tx Power of its last seconds, the Ericsson RCA that of its window.
            power_text = f", UE Tx Power{' (maximum)' if logged else ''} {_measure(power, 'dBm')}" if power is not None else ''
            lines.append(f"Radio ({source}): {' · '.join(parts)}{power_text}")
    return '\n'.join(lines)


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


# The text inputs the provider's description shows on its own line of the evidence.
_DESCRIBED = frozenset(('failure_text', 'signalling_events'))


def _evidence(condition: dict[str, Any], kind: str, expected: Any, value: Any, source: str = '') -> str:
    label, _kind, unit = INPUTS[condition['input']][:3]
    unit = f' {unit}' if unit else ''
    if source:
        label = f'{label} ({source})'
    if condition['op'] in _VALUELESS:
        return f"{label} {OPERATORS[condition['op']]}"
    if kind == 'number':
        return f"{label} {_shown(value)}{unit} ({OPERATORS[condition['op']]} {_shown(condition['value'])}{unit})"
    text = _clean(value, 160)
    if condition['op'] == 'contains':
        found = next((term for term in expected if keyword_found([term], normalized_text(value), 'text')), expected[0])
        shown = f"{label} contains “{found.replace('+', ' + ')}”"
        return shown if condition['input'] in _DESCRIBED else f'{shown}: {text}'
    return f"{label} “{text or '—'}” ({OPERATORS[condition['op']]} {condition['value']})"


def evaluate(compiled: list[dict[str, Any]], call: Any, inputs: dict[str, Any]) -> dict[str, str] | None:
    """The result of the first rule of the service of the call whose conditions hold, with the evidence; None when no
    rule takes the call."""
    try:
        service = str(call['service'] or '')
    except (KeyError, IndexError, TypeError):
        service = ''
    values: dict[str, Any] = {}
    # Where the radio at the failure was read (radio_rsrp, radio_sinr): its technology and source.
    sources: dict[str, str] = {}

    def value_of(key: str) -> Any:
        if key not in values:
            if key == 'failure_text':
                values[key] = failure_text(call, inputs)
            elif key == 'signalling_events':
                values[key] = signalling_events(inputs)
            elif key == 'lte_dl_rb_share':
                values[key] = resource_block_share(inputs.get('lte_dl_rbs'), inputs.get('lte_dl_bandwidth'), 'LTE')
            elif key == 'nr_dl_rb_share':
                values[key] = resource_block_share(inputs.get('nr_dl_rbs'), inputs.get('nr_dl_bandwidth'), 'NR', inputs.get('nr_dl_band'))
            elif key == 'radio_technology':
                values[key] = next((text for name in ('failure_technology', 'technology')
                                    if (text := _clean(_field(call, name)))), '') or _clean(inputs.get('rat'))
            elif key in {'radio_rsrp', 'radio_sinr'}:
                measure = key.removeprefix('radio_')
                technology = normalized_text(value_of('radio_technology'))
                nr_alone = bool(re.search(r'(?<![a-z0-9])(5g|nr)', technology)) and not re.search(r'(?<![a-z0-9])(4g|lte)', technology)
                order = ('nr', 'lte') if nr_alone else ('lte', 'nr')
                # The side that failed when the logs measured it, else the worst of the sides (or the CDR average).
                side = failed_side(call, inputs)
                found = next(((number, tech, f'UE {side}, {source}') for tech in order
                              for number, source in [side_radio(inputs, side, tech, measure)] if number is not None),
                             (None, '', '')) if side else (None, '', '')
                if found[0] is None:
                    found = next(((number, tech, source) for tech in order for source, template in RADIO_SOURCES
                                  if (number := _number(inputs.get(template.format(tech=tech, measure=measure)))) is not None),
                                 (None, '', ''))
                values[key] = found[0]
                if found[1]:
                    sources[key] = f'{found[1].upper()}, {found[2]}'

            elif key == 'failed_side':
                values[key] = failed_side(call, inputs)
            elif key in SIDE_INPUTS:
                prefix, name = key.split('_', 1)
                side = failed_side(call, inputs)
                if prefix == 'peer':
                    side = {'A': 'B', 'B': 'A'}.get(side, '')
                number, source = side_value(inputs, side, name) if side or prefix == 'side' else (None, '')
                values[key] = number
                if source:
                    sources[key] = source
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
                held.append(_evidence(condition, kind, expected, value, sources.get(condition['input'], '')))
            elif entry['all']:
                break
        else:
            if entry['conditions'] and not held:
                continue
            rule = entry['rule']
            read = {condition['input'] for condition, _kind, _value in entry['conditions']}
            # A line each: what held, the provider's description when the rule read it, the radio before the failure from
            # the most precise source (Layer3 Log, else Ericsson RCA), the averages of the call, the sites a rule of the
            # network around the call read and what the Layer3 Logs show before the failure when the rule read them.
            lines = ['; '.join(held) if held else 'No earlier rule explains the failure.']
            # The provider's description also when the radio of a side explains the failure it reports.
            if read & (_DESCRIBED | set(SIDE_INPUTS)) and (description := provider_description(call, inputs)):
                lines.append(f'Provider description: {description}')
            lines += [radio_line(inputs, failed_side(call, inputs)), averages_line(call, inputs)]
            if inputs.get(NETWORK_NOTE) and read & set(CONTEXT_INPUTS[1:]):
                lines.append(str(inputs[NETWORK_NOTE]))
            if inputs.get(L3_NOTE) and read & {*L3_INPUTS, *SIDE_INPUTS}:
                lines.append(str(inputs[L3_NOTE]))
            evidence = '\n'.join(line for line in lines if line)
            return {'rule': rule['name'], 'rule_key': rule['key'], **entry['result'], 'evidence': evidence[:MAX_EVIDENCE]}
    return None
