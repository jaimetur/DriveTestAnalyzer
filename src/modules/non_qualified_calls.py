"""Non-Qualified Calls: follow-up of every CDR call and test that did not complete.

A Non-Qualified (NQ) call is a Voice or Speech call, or a Data test, whose result
is anything other than ``Completed`` (for example Failed, Dropped or Cutoff).
The module indexes those rows of every ready CDR of the active workspace in
``nq_calls`` and lets the teams follow each one up: a status, a responsible team,
an assignee and a shared comment thread. Every change is recorded in
``nq_call_history`` with its author and time.

Each call can also be labelled with a root cause from a configurable two-level
taxonomy (``nq_root_causes``): a domain (RF, RAN, Core, IMS/E2E…) and a cause
inside it. The keywords of every domain and cause suggest a root cause from the
CDR failure classification, and the Root Cause Analysis summarises the labelled
calls per domain and cause, call type, NR mode, technology and eNB/gNB.

Follow-up is keyed by a stable ``call_key`` derived from the call itself: its
NetCheck ``JOIN_ID`` when the CDR has one, otherwise its service, Operator,
Campaign and test/session identifier. Statuses, comments and analysis fields
therefore survive reprocessing, uploading the same CDR again, and the move from
the Daily CDRs of a campaign to its Final CDR. A call can be in several CDRs:
the list shows it once, with the data of the most recent CDR (a Final CDR before
the Daily ones, then the newest data) and tells when a newer CDR changed it.
Speech calls are listed once per call; each of their samples keeps its own
follow-up (``sample_key``).

Every call of every CDR, qualified or not, is counted in ``nq_call_population``
so the share of Non-Qualified Calls of each campaign and operator can be shown.

Its Executive Summary and Progress Status report is a Reporting artifact
(PowerPoint, Word or Excel) registered with ``register_report_artifact_provider``.
"""

import csv
import hashlib
import io
import json
import math
import queue
import re
import sqlite3
import tempfile
import threading
import time
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from io import BytesIO
from threading import Lock
from typing import Any, Callable

from src.modules import cdr_field_dictionary
from src.modules.cdr_field_profiles import NETCHECK_PROFILE, CdrFieldProfile, workspace_field_profile
from src.modules.cdr_stage import CDR_STAGE_LABELS, combined_inclusion, dataset_cdr_stage
from src.modules.cell_identity import nr_cell_bits
from src.modules.column_names import campaign_sort_key, column_identity
from src.modules.value_maps import ValueMapper, field_kind
from src.modules.value_patterns import ValueSet, is_pattern, sql_condition
from src.modules.operator_roles import FOCUS, excluded_operators, labels_with_role
from src.modules.mapping_order import dimension_order_key, mapping_group
from src.modules import nq_catalog
from src.modules.nq_catalog import (
    ATTENDED_FIELD, FIELD_TYPES, MAX_LONG_TEXT, YES_NO, evaluate_status, keyword_found, keywords as _keywords,
    normalized_text as _normalized_text,
)
from src.modules import nq_analyses, nq_analyses_rules, nq_call_map, nq_dta_rca, nq_prioritization, nq_rca
from src.modules.non_qualified_calls_visuals import series_colours

NQ_CALLS_TABLE = 'nq_calls'
NQ_CALL_SOURCES_TABLE = 'nq_call_sources'
NQ_CALL_TRACKING_TABLE = 'nq_call_tracking'
NQ_CALL_COMMENTS_TABLE = 'nq_call_comments'
NQ_CALL_HISTORY_TABLE = 'nq_call_history'
NQ_CALL_OPTIONS_TABLE = 'nq_call_options'
NQ_TEAM_MEMBERS_TABLE = 'nq_team_members'
NQ_ROOT_CATALOG_TABLE = 'nq_root_catalog'
NQ_RCA_RESULTS_TABLE = 'nq_rca_results'
NQ_CALL_POPULATION_TABLE = 'nq_call_population'
NQ_CALL_VERSIONS_TABLE = 'nq_call_versions'
NQ_CALL_LATEST_TABLE = 'nq_call_latest'
NQ_FIELDS_TABLE = 'nq_analysis_fields'
NQ_FIELD_VALUES_TABLE = 'nq_analysis_field_values'
NQ_USER_LAYOUTS_TABLE = 'nq_user_table_layouts'
NQ_DTA_RESULTS_TABLE = nq_dta_rca.RESULTS_TABLE
NQ_DTA_LEARNED_TABLE = nq_dta_rca.LEARNED_TABLE
# Database Management titles of the module tables.
NQ_TABLE_TITLES = {
    NQ_CALLS_TABLE: 'NQ Calls',
    NQ_CALL_SOURCES_TABLE: 'NQ Call Sources',
    NQ_CALL_TRACKING_TABLE: 'NQ Call Tracking',
    NQ_CALL_COMMENTS_TABLE: 'NQ Call Comments',
    NQ_CALL_HISTORY_TABLE: 'NQ Call History',
    NQ_CALL_OPTIONS_TABLE: 'NQ Call Options',
    NQ_TEAM_MEMBERS_TABLE: 'NQ Team Members',
    NQ_ROOT_CATALOG_TABLE: 'NQ Root Catalog',
    NQ_RCA_RESULTS_TABLE: 'NQ RCA Results',
    NQ_CALL_POPULATION_TABLE: 'NQ Call Population',
    NQ_CALL_VERSIONS_TABLE: 'NQ Call Versions',
    NQ_CALL_LATEST_TABLE: 'NQ Call Latest',
    NQ_FIELDS_TABLE: 'NQ Analysis Fields',
    NQ_FIELD_VALUES_TABLE: 'NQ Analysis Field Values',
    NQ_USER_LAYOUTS_TABLE: 'NQ User Table Layouts',
    **nq_prioritization.TABLE_TITLES,
    **nq_dta_rca.TABLE_TITLES,
}
SERVICES = ('voice', 'speech', 'data')
SERVICE_LABELS = {'voice': 'Voice', 'speech': 'Speech', 'data': 'Data'}
# The result of a qualified NetCheck call (each CDR type tells its own, see cdr_field_profiles).
QUALIFIED_RESULT = NETCHECK_PROFILE.nq_qualified_value
# Bump when the indexed fields or the call key change so every CDR is indexed again (7: the inputs of the DT Analyzer
# RCA; 8: its resource blocks and the cells of the call with their PCIs and where it ended).
INDEX_VERSION = 8
# The call key of version 3: the JOIN_ID first, and Speech calls (not samples).
KEY_SCHEME = '3'
KEY_SCHEME_STATE_KEY = 'nq_calls_key_scheme'
TRACKING_FORMAT = 'nq-call-tracking'
TRACKING_FORMAT_VERSION = 3
CONFIGURATION_FORMAT = 'nq-calls-configuration'
CONFIGURATION_FORMAT_VERSION = 1
UNASSIGNED = '__unassigned__'
MAX_COMMENT_LENGTH = 5000
# The rows of a page of the calls table, the first one by default (also with All panels).
PAGE_SIZES = (10, 25, 50, 100)
DEFAULT_PAGE_SIZE = PAGE_SIZES[0]
OPTION_KINDS = ('status', 'team')
COLOR_PATTERN = re.compile(r'#[0-9a-fA-F]{6}')
DEFAULT_STATUSES = nq_catalog.DEFAULT_STATUSES
DEFAULT_TEAMS = nq_catalog.DEFAULT_TEAMS
# The statuses and teams of the first version: replaced by the Analysis Center ones while unchanged.
_FIRST_STATUSES = ('Open', 'Under Investigation', 'Pending Information', 'Resolved', 'Not Applicable')
_FIRST_STATUS_MOVES = {'under investigation': 'Under Analysis', 'pending information': 'Open', 'resolved': 'Closed',
                       'not applicable': 'Closed'}
_FIRST_TEAMS = ('RAN Optimisation', 'Core Network', 'IMS / VoLTE', 'Transport', 'Device & Test Setup')
ROOT_CAUSE_SETTINGS_STATE_KEY = 'nq_calls_root_cause_settings'
ROOT_CAUSE_RULE_STATE_KEY = 'nq_calls_root_cause_rule'
SECTIONS_STATE_KEY = 'nq_calls_sections'
STATUS_RULES_STATE_KEY = 'nq_calls_status_rules'
# Set once the Analysis Center catalog, statuses, teams and rules have been added to the workspace.
ANALYSIS_CENTER_STATE_KEY = 'nq_analysis_center_v1'
# The second layout of the Analysis Center (section colours and the order of the Analysis fields), applied once.
ANALYSIS_CENTER_V2_STATE_KEY = 'nq_analysis_center_v2'
# The fields of the Auto RCA output of the Ericsson RCA (its initial category and subcategory and its evidence),
# added once to the workspaces created before them.
ANALYSIS_CENTER_V4_STATE_KEY = 'nq_analysis_center_v4'
# The NetCheck RCA fields before those of the Ericsson RCA, and the descriptions that named the RCA script, once.
ANALYSIS_CENTER_V5_STATE_KEY = 'nq_analysis_center_v5'
# The fields the analyses of the previous tool bring (initial root category and cause, priority, analyst, reviewer,
# description, implementation team and planned fiscal year), added once to the workspaces created before them.
ANALYSIS_CENTER_V6_STATE_KEY = 'nq_analysis_center_v6'
ANALYSES_FIELD_KEYS = {'initial_root_category', 'initial_root_cause', 'priority', 'analyst', 'reviewer', 'description',
                       'implementation_team', 'planned_fy'}
# Vendor 1 and Vendor 2 when Failure, the priorities P1 to P4, the E2E Team (formerly E2E stream) and the Core domain
# (formerly Core 2G/4G/5G), once.
ANALYSIS_CENTER_V9_STATE_KEY = 'nq_analysis_center_v9'
# Successful Call-Excluded is no longer a team (nor an Implementation Stream): its calls go to No Team; and the
# priorities go to P5, once.
ANALYSIS_CENTER_V10_STATE_KEY = 'nq_analysis_center_v10'
# The Unique ID and Polygon Area of the analyses of the previous tool, once.
ANALYSIS_CENTER_V11_STATE_KEY = 'nq_analysis_center_v11'
ANALYSES_V11_FIELD_KEYS = {'unique_id', 'polygon_area'}
# The Implementation Stream becomes the Implementation Team, once.
ANALYSIS_CENTER_V12_STATE_KEY = 'nq_analysis_center_v12'
# The Planned FY writes its years as fiscal years (2030 is FY30), in order, once.
ANALYSIS_CENTER_V13_STATE_KEY = 'nq_analysis_center_v13'
V13_FORMER_DESCRIPTION = 'The fiscal year (or year) the measure is planned for, when there is no exact date.'
# The suggested causes of the NetCheck RCA and the Ericsson RCA leave the table (shown from Columns), once.
ANALYSIS_CENTER_V14_STATE_KEY = 'nq_analysis_center_v14'
V14_HIDDEN_COLUMNS = ('netcheck_suggested_cause', 'rca_suggested_cause')
# The Implementation Status joins the table after the Analysis Status, once.
ANALYSIS_CENTER_V16_STATE_KEY = 'nq_analysis_center_v16'
V16_SHOWN_COLUMNS = ('implementation_status',)
# Findings follows the Description, before the Proposed Measure, once.
ANALYSIS_CENTER_V17_STATE_KEY = 'nq_analysis_center_v17'
# The Implementation Status keeps implementation values only, once: Planned and Not Planned move to the Planned Status,
# Invalidated is Not Applicable and Closed is Implemented; Not yet evaluated turns red.
ANALYSIS_CENTER_V18_STATE_KEY = 'nq_analysis_center_v18'
V18_IMPLEMENTATION_RENAMES = {'invalidated': 'Not Applicable', 'closed': 'Implemented'}
V18_FORMER_NOT_EVALUATED_COLOR = '#9aa5ad'
# Open is no longer a status but the group of the phase statuses: an attended call is Under Analysis until a later
# phase, once: (former status, status its calls take).
ANALYSIS_CENTER_V19_STATE_KEY = 'nq_analysis_center_v19'
V19_FORMER_OPEN = ('Open', 'Under Analysis')
# Once: the Analysis Status values of the previous tool that invalidate an analysis are Invalidated, and the default
# Status Rules go from the end of the pipeline to its start (those of before, still unchanged, give way to them).
ANALYSIS_CENTER_V20_STATE_KEY = 'nq_analysis_center_v20'
V20_INVALIDATED_ANALYSES = ('No_Vendor_B', 'No_JoinID Missing')
V20_FORMER_RULES = (
    ('Closed', (('analysis_status', 'in', ('Rejected', 'Invalidated')),)),
    ('Closed', (('implementation_status', 'in', ('Implemented',)),)),
    ('Under Planning', (('planned_status', 'in', ('Planned',)),)),
    ('Under Implementation', (('implementation_status', 'in', ('Not yet evaluated', 'Under evaluation', 'Evaluated')),)),
    ('Closed', (('analysis_status', 'in', ('Finished',)),)),
    ('Under Analysis', (('analysis_status', 'in', ('Ongoing',)),)),
    ('Under Analysis', (('@attended', 'in', ('Yes',)),)),
)
# RF, the most frequent root domain, is blue instead of red, once (unless its colour was changed): (domain, former colour).
ANALYSIS_CENTER_V21_STATE_KEY = 'nq_analysis_center_v21'
V21_FORMER_RF_COLOR = ('RF', '#c8102e')
# The fields of the NetCheck RCA and of the Ericsson RCA named after their source, once: (key, former label).
ANALYSIS_CENTER_V15_STATE_KEY = 'nq_analysis_center_v15'
V15_FORMER_LABELS = (
    ('netcheck_failure_classification', 'Netcheck Failure Classification'),
    ('netcheck_suggested_category', 'Netcheck Suggested Category'),
    ('netcheck_suggested_cause', 'Netcheck Suggested Cause'),
    ('auto_rca_category_a', 'Auto_RCA_Category_A'),
    ('auto_rca_subcategory_a', 'Auto_RCA_Subcategory_A'),
    ('auto_rca_category_b', 'Auto_RCA_Category_B'),
    ('auto_rca_subcategory_b', 'Auto_RCA_Subcategory_B'),
    ('rca_initial_category', 'RCA Category'),
    ('rca_initial_subcategory', 'RCA Subcategory'),
    ('rca_suggested_category', 'RCA Suggested Category'),
    ('rca_suggested_cause', 'RCA Suggested Cause'),
    ('rca_evidence', 'RCA Evidence'),
)
# The Implementation Proposals (in plural, as a call can take one of many), once: (key, former label).
ANALYSIS_CENTER_V22_STATE_KEY = 'nq_analysis_center_v22'
V22_FORMER_LABELS = (('implementation_proposal', 'Implementation Proposal'),)
# The fields of the NQ Prioritization (scoring impact, repetitions and prioritization), once, after the Priority.
ANALYSIS_CENTER_V23_STATE_KEY = 'nq_analysis_center_v23'
V23_FIELD_KEYS = {'prioritization', 'prioritization_rule', 'scoring_impact', 'scoring_points_lost', 'scoring_kpis_lost',
                  'repeated_issue', 'repetitions', 'repeated_campaigns', 'repetition_place'}
# The fields of the strategies of the NQ Prioritization (the queue and the Expected Gain of a call), once.
ANALYSIS_CENTER_V24_STATE_KEY = 'nq_analysis_center_v24'
V24_FIELD_KEYS = {'prioritization_queue', 'expected_gain'}
# The priorities P1 to P8 without a colour take those of the queues and steps of the NQ Prioritization, once.
ANALYSIS_CENTER_V25_STATE_KEY = 'nq_analysis_center_v25'
# The Priority is a column of the table in the workspace layout, once.
ANALYSIS_CENTER_V26_STATE_KEY = 'nq_analysis_center_v26'
V26_SHOWN_COLUMNS = ('priority',)
# The fields of the DT Analyzer RCA, once, after those of the Ericsson RCA.
ANALYSIS_CENTER_V27_STATE_KEY = 'nq_analysis_center_v27'
V27_FIELD_KEYS = {'dta_rca_domain', 'dta_rca_category', 'dta_rca_cause', 'dta_rca_rule', 'dta_rca_evidence'}
# The fields of the DT Analyzer RCA named after its short name (formerly DriveTest Analyzer RCA), once.
ANALYSIS_CENTER_V28_STATE_KEY = 'nq_analysis_center_v28'
V28_FORMER_NAME = 'DriveTest Analyzer RCA'
# The Root Categories of the causes the DT Analyzer RCA finds outside the radio coverage and interference, and the default
# causes they group (those still without a category), once.
ANALYSIS_CENTER_V29_STATE_KEY = 'nq_analysis_center_v29'
# The fields of the DT Analyzer RCA first among those of the RCA sources, once.
ANALYSIS_CENTER_V30_STATE_KEY = 'nq_analysis_center_v30'
# The Root Category and Root Causes of the lack of resources and the ping-pongs of the DT Analyzer RCA, and its new
# default rules in the workspaces with rules of their own.
ANALYSIS_CENTER_V31_STATE_KEY = 'nq_analysis_center_v31'
# The keywords of the Root Categories of the DT Analyzer RCA, which translate the NetCheck values onto the catalog, for
# those categories that still have none, once.
ANALYSIS_CENTER_V32_STATE_KEY = 'nq_analysis_center_v32'
# The descriptions of the repetitions of the NQ Prioritization, counted within the Cluster distance of the call or at its
# site (formerly at its place), where they are still the former defaults, once: (key, former description).
ANALYSIS_CENTER_V33_STATE_KEY = 'nq_analysis_center_v33'
V33_FORMER_DESCRIPTIONS = (
    ('repeated_issue', 'Yes when other Non-Qualified Calls of the operator failed at the same place in the quarter of the call or '
                       'the quarter before it.'),
    ('repetitions', 'The Non-Qualified Calls of the operator at the same place in the quarter of the call and the quarters before '
                    'it (the call included), whatever their service and NR Mode.'),
    ('repetition_place', 'Where the repetitions are counted: the site of the cell where the call ended, the site that served its '
                         'start, its eNB / gNB or the spot where it started.'),
)
# Set once the tables and columns of this version exist, so the requests check the schema without writing.
SCHEMA_STATE_KEY = 'nq_calls_schema'
SCHEMA_VERSION = '2026-10-26.1'
# Indexed call fields that the suggestion rule can read, with their labels.
RULE_FIELDS = {
    'failure_classification': 'Failure Classification', 'failure_category': 'Failure Category',
    'failure_subcategory': 'Failure Subcategory', 'failure_comment': 'Failure Comment',
    'failure_phase': 'Failure Phase', 'failure_technology': 'Failure Technology', 'result': 'Result',
    'test_name': 'Test Name', 'technology': 'Technology', 'direction': 'Direction',
}
RULE_MATCHES = ('words', 'text')
DEFAULT_ROOT_CAUSE_RULE = {
    'domain_fields': ['failure_classification'],
    'cause_fields': ['failure_category', 'failure_subcategory', 'failure_comment'],
    'causes_in_domain': True, 'comments': True, 'comment_domain': True, 'match': 'words',
}
NOT_CLASSIFIED = 'Not classified'

# Indexed field -> CDR columns, in order of preference: those of NetCheck CDRs (every CDR type lists its own columns
# for the same fields, see cdr_field_profiles).
FIELD_SOURCES: dict[str, tuple[str, ...]] = NETCHECK_PROFILE.nq_field_sources
CALL_FIELDS = tuple(FIELD_SOURCES)
# The fields of every call (qualified or not) kept for the rates per Vendor, host network, site and environment.
POPULATION_FIELDS = ('vendor', 'host_network', 'site_id', 'environment', 'session_type', 'city', 'region')
# The values a catalog field can read from the call: the indexed fields and the last cell of the Cell ID chain.
CATALOG_CALL_FIELDS = (*CALL_FIELDS, 'last_cell_id')


def last_cell_sql(column: str) -> str:
    """The last element of a Cell ID chain ("[a]->[b]->[c]" gives "c"): the cell where the call ended."""
    return f"trim(substr({column}, length(rtrim({column}, replace({column}, '>', ''))) + 1), '[] ')"
NUMERIC_FIELDS = frozenset({'latitude', 'longitude'})
# NetCheck's identifier of each voice call and data test, the same in the Daily and Final CDRs.
JOIN_SOURCES = NETCHECK_PROFILE.nq_join_sources
# Without a JOIN_ID: the test of a Data CDR, the session (the call) of a Voice or Speech CDR.
IDENTIFIER_SOURCES = NETCHECK_PROFILE.nq_identifier_sources
# A Speech sample inside its call.
SAMPLE_SOURCES = NETCHECK_PROFILE.nq_sample_sources
SUBSCRIBER_SOURCES = NETCHECK_PROFILE.nq_subscriber_sources
# Filters on indexed fields; the tracking filters are handled separately.
FIELD_FILTERS = (
    'service', 'campaign', 'operator', 'operator_vendor', 'vendor_operator', 'vendor', 'region', 'cluster', 'city',
    'technology', 'test_name', 'result', 'failure_classification', 'failure_category',
)
TRACKING_FILTERS = ('status', 'team', 'assignee', 'root_domain', 'root_category', 'root_cause', 'status_mode')
# Filters typed as a list of values rather than chosen among them (a JOIN_ID has too many values to list).
TYPED_FILTERS = ('join_id',)
TRACKING_FIELDS = ('status', 'team', 'assignee', 'root_domain', 'root_category', 'root_cause', 'status_mode')
# Filters set by clicking the Progress View and Root Cause Analysis: NR mode, call type
# (Classic, WhatsApp, Data), a timeline period ("month:2026-07"), the age of open calls,
# a labelled root cause ("RF||Coverage"), the root domain or cause counting the suggested
# ones, the eNB/gNB of the last cell ("EE||eNB 525176"), the place of the repeated issues of the NQ Prioritization
# ("EE||Site S1") and its hotspots (their key).
# The indicator cards filter by follow-up state (closed, attended, with team...) and the
# Suggested card by the calls without a root cause that have a suggestion.
EXTRA_FILTERS = ('nr_mode', 'call_type', 'period', 'age', 'root_pair', 'effective_domain', 'effective_cause', 'node',
                 'state', 'rca_state', 'place', 'hotspot')
KEY_FILTERS = ('effective_domain', 'effective_cause', 'node', 'rca_state', 'netcheck_domain', 'netcheck_category',
               'netcheck_cause', 'script_domain', 'script_category', 'script_cause', 'dta_domain', 'dta_category', 'dta_cause',
               'netcheck_raw', 'script_raw', 'dta_raw')
# The sources the Root Cause Analysis counts the calls with: the decision of the analysts, the NetCheck RCA of the CDR or
# the Ericsson RCA mapped onto the Root Cause Catalog, or the DT Analyzer RCA.
ROOT_SOURCES = ('analysts', 'netcheck', 'script', 'dta')
# The RCA sources whose root domain, category and cause filter the calls (computed per call).
RCA_FILTER_SOURCES = ('netcheck', 'script', 'dta')
_ATTENDED_SQL = "(updated_at <> '' OR comment_count > 0)"
STATE_SQL = {
    'attended': _ATTENDED_SQL, 'not_attended': f'NOT {_ATTENDED_SQL}', 'with_team': "team <> ''",
    'assigned': "assignee <> ''", 'commented': 'comment_count > 0', 'labelled': "root_domain <> ''",
    # RCA Identification: a root category or cause is selected.
    'identified': "(root_category <> '' OR root_cause <> '')", 'not_identified': "(root_category = '' AND root_cause = '')",
}
SORT_COLUMNS = {
    'service': 'service', 'start_time': 'start_time', 'operator': 'operator', 'operator_vendor': 'operator_vendor', 'vendor': 'vendor',
    'campaign': 'campaign', 'city': 'city', 'technology': 'technology', 'test_name': 'test_name',
    'result': 'result', 'failure': 'failure_classification', 'status': 'status', 'team': 'team',
    'assignee': 'assignee', 'root_cause': 'root_domain', 'root_category': 'root_category', 'cause': 'root_cause',
    'comments': 'comment_count',
    'updated_at': 'updated_at', 'join_id': 'join_id', 'region': 'region', 'cluster': 'cluster', 'nr_mode': 'nr_mode',
    'cell_id': 'cell_id', 'direction': 'direction', 'session_type': 'session_type', 'end_time': 'end_time', 'cdr': 'dataset_id',
    'version': 'version_state',
}
# The breakdowns of the Summary, in the order of the page and of the one-slide Executive Summary.
BREAKDOWNS = (
    ('service', 'By Service'), ('result', 'By Result'), ('status', 'By Status'), ('team', 'By Team'),
    ('root_domain', 'By Root Domain'), ('root_category', 'By Root Category'), ('root_cause', 'By Root Cause'),
    ('failure_classification', 'By Failure Classification'),
    ('campaign', 'By Campaign'), ('operator', 'By Operator'), ('vendor', 'By Vendor'), ('region', 'By Region'),
    ('cluster', 'By Cluster'), ('city', 'By City'),
)
SEARCH_FIELDS = (
    'operator', 'operator_vendor', 'vendor', 'campaign', 'region', 'cluster', 'city', 'technology', 'test_name', 'result',
    'failure_classification', 'failure_category', 'failure_subcategory', 'failure_comment', 'cell_id', 'join_id', 'session_type',
    'extra_json',
)
# How the CDRs see a call (see ``_base_sql``); "current" is the latest version with nothing to tell.
VERSION_STATES = ('current', 'changed', 'newer', 'not_in_final', 'qualified')
VERSION_LABELS = {
    'current': 'Latest version', 'changed': 'Changed between CDRs', 'newer': 'Newer version in another CDR',
    'not_in_final': 'Not in the Final CDR', 'qualified': 'Completed in a newer CDR',
}

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {NQ_CALLS_TABLE} (
    dataset_id INTEGER NOT NULL,
    source_row_id INTEGER NOT NULL,
    call_key TEXT NOT NULL,
    service TEXT NOT NULL,
    nr_mode TEXT NOT NULL DEFAULT '',
    {', '.join(f"{field} REAL" if field in NUMERIC_FIELDS else f"{field} TEXT NOT NULL DEFAULT ''" for field in CALL_FIELDS)},
    join_id TEXT NOT NULL DEFAULT '',
    sample_key TEXT NOT NULL DEFAULT '',
    sample_id TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{{}}',
    rca_inputs_json TEXT NOT NULL DEFAULT '{{}}',
    PRIMARY KEY (dataset_id, source_row_id)
);
CREATE INDEX IF NOT EXISTS idx_{NQ_CALLS_TABLE}_call_key ON {NQ_CALLS_TABLE}(call_key);
CREATE TABLE IF NOT EXISTS {NQ_CALL_SOURCES_TABLE} (
    dataset_id INTEGER PRIMARY KEY,
    revision TEXT NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL,
    stage_rank INTEGER NOT NULL DEFAULT 1,
    data_date TEXT NOT NULL DEFAULT '',
    population_count INTEGER NOT NULL DEFAULT 0,
    combined_rank INTEGER NOT NULL DEFAULT -1
);
CREATE TABLE IF NOT EXISTS {NQ_CALL_POPULATION_TABLE} (
    dataset_id INTEGER NOT NULL,
    call_key TEXT NOT NULL,
    service TEXT NOT NULL,
    campaign TEXT NOT NULL DEFAULT '',
    operator TEXT NOT NULL DEFAULT '',
    nr_mode TEXT NOT NULL DEFAULT '',
    is_nq INTEGER NOT NULL DEFAULT 0,
    is_latest INTEGER NOT NULL DEFAULT 0,
    {', '.join(f"{field} TEXT NOT NULL DEFAULT ''" for field in POPULATION_FIELDS)},
    PRIMARY KEY (dataset_id, call_key)
);
CREATE INDEX IF NOT EXISTS idx_{NQ_CALL_POPULATION_TABLE}_key ON {NQ_CALL_POPULATION_TABLE}(call_key);
CREATE INDEX IF NOT EXISTS idx_{NQ_CALL_POPULATION_TABLE}_latest ON {NQ_CALL_POPULATION_TABLE}(is_latest, service);
-- Covers the NQ rate of the latest version of every call, read from the index alone.
CREATE INDEX IF NOT EXISTS idx_{NQ_CALL_POPULATION_TABLE}_rates
    ON {NQ_CALL_POPULATION_TABLE}(is_latest, service, campaign, operator, nr_mode, is_nq);
-- The calls served by a site, for the Serving site health of the map of a call (nq_call_map).
CREATE INDEX IF NOT EXISTS idx_{NQ_CALL_POPULATION_TABLE}_site ON {NQ_CALL_POPULATION_TABLE}(site_id, host_network);
CREATE TABLE IF NOT EXISTS {NQ_CALL_VERSIONS_TABLE} (
    call_key TEXT PRIMARY KEY,
    latest_dataset_id INTEGER NOT NULL,
    latest_is_nq INTEGER NOT NULL DEFAULT 1,
    in_final INTEGER NOT NULL DEFAULT 0,
    final_covered INTEGER NOT NULL DEFAULT 0,
    changed INTEGER NOT NULL DEFAULT 0,
    cdr_count INTEGER NOT NULL DEFAULT 1
);
-- The latest version of every call (the Final CDR first, then the newest data) with its Operator and Vendor
-- mapped: the part of the calls query that only changes when the CDRs are indexed or the maps change.
CREATE TABLE IF NOT EXISTS {NQ_CALL_LATEST_TABLE} (
    dataset_id INTEGER NOT NULL,
    source_row_id INTEGER NOT NULL,
    call_key TEXT PRIMARY KEY,
    service TEXT NOT NULL,
    nr_mode TEXT NOT NULL DEFAULT '',
    {', '.join(f"{field} REAL" if field in NUMERIC_FIELDS else f"{field} TEXT NOT NULL DEFAULT ''" for field in CALL_FIELDS)},
    vendor_operator TEXT NOT NULL DEFAULT '',
    last_cell_id TEXT NOT NULL DEFAULT '',
    join_id TEXT NOT NULL DEFAULT '',
    extra_json TEXT NOT NULL DEFAULT '{{}}',
    nq_samples INTEGER NOT NULL DEFAULT 1,
    latest_dataset_id INTEGER NOT NULL DEFAULT 0,
    cdr_count INTEGER NOT NULL DEFAULT 1,
    version_state TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS {NQ_FIELDS_TABLE} (
    field_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    field_type TEXT NOT NULL,
    options_json TEXT NOT NULL DEFAULT '[]',
    position INTEGER NOT NULL DEFAULT 0,
    in_table INTEGER NOT NULL DEFAULT 0,
    in_summary INTEGER NOT NULL DEFAULT 0,
    required_to_close INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    section TEXT NOT NULL DEFAULT 'analysis',
    source TEXT NOT NULL DEFAULT 'user',
    source_ref TEXT NOT NULL DEFAULT '',
    in_export INTEGER NOT NULL DEFAULT 1,
    suggest_from TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS {NQ_FIELD_VALUES_TABLE} (
    call_key TEXT NOT NULL,
    field_key TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (call_key, field_key)
);
CREATE INDEX IF NOT EXISTS idx_{NQ_FIELD_VALUES_TABLE}_field ON {NQ_FIELD_VALUES_TABLE}(field_key, value);
CREATE TABLE IF NOT EXISTS {NQ_CALL_TRACKING_TABLE} (
    call_key TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT '',
    team TEXT NOT NULL DEFAULT '',
    assignee TEXT NOT NULL DEFAULT '',
    root_domain TEXT NOT NULL DEFAULT '',
    root_cause TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 0,
    root_category TEXT NOT NULL DEFAULT '',
    status_mode TEXT NOT NULL DEFAULT 'auto',
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS {NQ_CALL_COMMENTS_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL UNIQUE,
    call_key TEXT NOT NULL,
    body TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    edited_by TEXT NOT NULL DEFAULT '',
    edited_at TEXT NOT NULL DEFAULT '',
    deleted_by TEXT NOT NULL DEFAULT '',
    deleted_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_{NQ_CALL_COMMENTS_TABLE}_call ON {NQ_CALL_COMMENTS_TABLE}(call_key, id);
CREATE TABLE IF NOT EXISTS {NQ_CALL_HISTORY_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL UNIQUE,
    call_key TEXT NOT NULL,
    field TEXT NOT NULL,
    old_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{NQ_CALL_HISTORY_TABLE}_call ON {NQ_CALL_HISTORY_TABLE}(call_key, id);
CREATE TABLE IF NOT EXISTS {NQ_CALL_OPTIONS_TABLE} (
    kind TEXT NOT NULL CHECK(kind IN ('status', 'team')),
    name TEXT NOT NULL COLLATE NOCASE,
    color TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    is_closed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, name)
);
CREATE TABLE IF NOT EXISTS {NQ_TEAM_MEMBERS_TABLE} (
    team TEXT NOT NULL COLLATE NOCASE,
    username TEXT NOT NULL COLLATE NOCASE,
    PRIMARY KEY (team, username)
);
CREATE TABLE IF NOT EXISTS {NQ_USER_LAYOUTS_TABLE} (
    username TEXT PRIMARY KEY COLLATE NOCASE,
    layout_json TEXT NOT NULL DEFAULT '',
    view TEXT NOT NULL DEFAULT 'mine',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS {NQ_ROOT_CATALOG_TABLE} (
    kind TEXT NOT NULL CHECK(kind IN ('domain', 'category', 'cause')),
    name TEXT NOT NULL COLLATE NOCASE,
    domain TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (kind, name)
);
CREATE TABLE IF NOT EXISTS {NQ_RCA_RESULTS_TABLE} (
    join_id TEXT PRIMARY KEY,
    original_join_id TEXT NOT NULL,
    values_json TEXT NOT NULL DEFAULT '{{}}',
    source_file TEXT NOT NULL DEFAULT '',
    imported_by TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT ''
);
-- The DT Analyzer RCA of every indexed row (call, test or Speech sample), calculated from its inputs.
CREATE TABLE IF NOT EXISTS {NQ_DTA_RESULTS_TABLE} (
    dataset_id INTEGER NOT NULL,
    source_row_id INTEGER NOT NULL,
    rule TEXT NOT NULL DEFAULT '',
    rule_key TEXT NOT NULL DEFAULT '',
    domain TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    cause TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (dataset_id, source_row_id)
);
-- The root causes the DT Analyzer RCA learns from the decisions of the analysts (only while it learns), for the rows whose
-- pattern the analysts decided otherwise than its rule.
CREATE TABLE IF NOT EXISTS {NQ_DTA_LEARNED_TABLE} (
    dataset_id INTEGER NOT NULL,
    source_row_id INTEGER NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '',
    cause TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL DEFAULT '',
    decisions INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dataset_id, source_row_id)
);
"""

_sync_locks: dict[str, Lock] = {}
_sync_locks_guard = Lock()
# The NQ rate counts of each workspace and CDR scope, kept until the indexed CDRs change.
_rate_counts_cache: dict[tuple[Any, ...], list[tuple[Any, ...]]] = {}
_rate_counts_guard = Lock()
RATE_COUNTS_CACHE_SIZE = 32


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, float):
        if math.isnan(value):
            return ''
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    return '' if text.casefold() in {'nan', 'nat', 'none', '<na>'} else text


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


_LEGACY_ROOT_CAUSES_TABLE = 'nq_root_causes'


def _columns_of(connection: Any, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info({table})').fetchall()}


def _schema_ready(task_repository: Any) -> bool:
    """Whether every table of this version exists and the upgrades ran: read without taking the write lock."""
    with task_repository.connection() as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not set(NQ_TABLE_TITLES) <= tables or 'workspace_state' not in tables:
            return False
        keys = (SCHEMA_STATE_KEY, ANALYSIS_CENTER_STATE_KEY, ANALYSIS_CENTER_V2_STATE_KEY, ANALYSIS_CENTER_V4_STATE_KEY,
                ANALYSIS_CENTER_V5_STATE_KEY, ANALYSIS_CENTER_V6_STATE_KEY, ANALYSIS_CENTER_V9_STATE_KEY,
                ANALYSIS_CENTER_V10_STATE_KEY, ANALYSIS_CENTER_V11_STATE_KEY, ANALYSIS_CENTER_V12_STATE_KEY,
                ANALYSIS_CENTER_V13_STATE_KEY, ANALYSIS_CENTER_V14_STATE_KEY, ANALYSIS_CENTER_V15_STATE_KEY,
                ANALYSIS_CENTER_V16_STATE_KEY, ANALYSIS_CENTER_V17_STATE_KEY, ANALYSIS_CENTER_V18_STATE_KEY,
                ANALYSIS_CENTER_V19_STATE_KEY, ANALYSIS_CENTER_V20_STATE_KEY, ANALYSIS_CENTER_V21_STATE_KEY,
                ANALYSIS_CENTER_V22_STATE_KEY, ANALYSIS_CENTER_V23_STATE_KEY, ANALYSIS_CENTER_V24_STATE_KEY, ANALYSIS_CENTER_V25_STATE_KEY,
                ANALYSIS_CENTER_V26_STATE_KEY, ANALYSIS_CENTER_V27_STATE_KEY, ANALYSIS_CENTER_V28_STATE_KEY,
                ANALYSIS_CENTER_V29_STATE_KEY, ANALYSIS_CENTER_V30_STATE_KEY, ANALYSIS_CENTER_V31_STATE_KEY,
                ANALYSIS_CENTER_V32_STATE_KEY, ANALYSIS_CENTER_V33_STATE_KEY)
        states = {str(row[0]): str(row[1]) for row in connection.execute(
            f"SELECT key, value FROM workspace_state WHERE key IN ({', '.join('?' for _ in keys)})", keys)}
    return states.get(SCHEMA_STATE_KEY) == SCHEMA_VERSION and all(states.get(key) for key in keys[1:])


def ensure_nq_tables(task_repository: Any) -> None:
    """Create the module tables, add the columns of later versions and seed the defaults once.

    Every request calls it: once the schema of this version is in place it only reads, so the pages never wait
    for the workspace writer (the indexing or a CDR being processed).
    """
    if _schema_ready(task_repository):
        return
    with task_repository.connection() as connection:
        existed = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (NQ_CALL_OPTIONS_TABLE,),
        ).fetchone()
        catalog_existed = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (NQ_ROOT_CATALOG_TABLE,),
        ).fetchone()
        tracking = _columns_of(connection, NQ_CALL_TRACKING_TABLE)
        for column, definition in (('root_domain', "TEXT NOT NULL DEFAULT ''"), ('root_cause', "TEXT NOT NULL DEFAULT ''"),
                                   ('root_category', "TEXT NOT NULL DEFAULT ''"), ('status_mode', "TEXT NOT NULL DEFAULT 'auto'")):
            if tracking and column not in tracking:
                connection.execute(f'ALTER TABLE {NQ_CALL_TRACKING_TABLE} ADD COLUMN {column} {definition}')
        definitions = _columns_of(connection, NQ_FIELDS_TABLE)
        for column, definition in (('section', "TEXT NOT NULL DEFAULT 'analysis'"), ('source', "TEXT NOT NULL DEFAULT 'user'"),
                                   ('source_ref', "TEXT NOT NULL DEFAULT ''"), ('in_export', 'INTEGER NOT NULL DEFAULT 1'),
                                   ('suggest_from', "TEXT NOT NULL DEFAULT ''")):
            if definitions and column not in definitions:
                connection.execute(f'ALTER TABLE {NQ_FIELDS_TABLE} ADD COLUMN {column} {definition}')
        indexed = _columns_of(connection, NQ_CALLS_TABLE)
        if indexed and not set(CALL_FIELDS) <= indexed:
            # The index is rebuilt from the CDRs whenever its fields change.
            connection.execute(f'DROP TABLE {NQ_CALLS_TABLE}')
            connection.execute(f'DROP TABLE IF EXISTS {NQ_CALL_SOURCES_TABLE}')
            indexed = set()
        # Columns added later keep the indexed rows, so the follow-up can move to the new call keys.
        for column, definition in (('join_id', "TEXT NOT NULL DEFAULT ''"), ('sample_key', "TEXT NOT NULL DEFAULT ''"),
                                   ('sample_id', "TEXT NOT NULL DEFAULT ''"), ('extra_json', "TEXT NOT NULL DEFAULT '{}'"),
                                   ('rca_inputs_json', "TEXT NOT NULL DEFAULT '{}'")):
            if indexed and column not in indexed:
                connection.execute(f'ALTER TABLE {NQ_CALLS_TABLE} ADD COLUMN {column} {definition}')
        # The key of the rule of the DT Analyzer RCA results of before; they are calculated again.
        dta_results = _columns_of(connection, NQ_DTA_RESULTS_TABLE)
        if dta_results and 'rule_key' not in dta_results:
            connection.execute(f"ALTER TABLE {NQ_DTA_RESULTS_TABLE} ADD COLUMN rule_key TEXT NOT NULL DEFAULT ''")
            connection.execute('DELETE FROM workspace_state WHERE key = ?', (nq_dta_rca.FINGERPRINT_STATE_KEY,))
        # The root category each root cause is mapped to.
        catalog_columns = _columns_of(connection, NQ_ROOT_CATALOG_TABLE)
        if catalog_columns and 'category' not in catalog_columns:
            connection.execute(f"ALTER TABLE {NQ_ROOT_CATALOG_TABLE} ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        # The serving cell, environment, session, City and Region of every call (indexed again with INDEX_VERSION).
        population = _columns_of(connection, NQ_CALL_POPULATION_TABLE)
        for column in POPULATION_FIELDS:
            if population and column not in population:
                connection.execute(f"ALTER TABLE {NQ_CALL_POPULATION_TABLE} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
        sources = _columns_of(connection, NQ_CALL_SOURCES_TABLE)
        for column, definition in (('stage_rank', 'INTEGER NOT NULL DEFAULT 1'), ('data_date', "TEXT NOT NULL DEFAULT ''"),
                                   ('population_count', 'INTEGER NOT NULL DEFAULT 0'),
                                   ('combined_rank', 'INTEGER NOT NULL DEFAULT -1')):
            if sources and column not in sources:
                connection.execute(f'ALTER TABLE {NQ_CALL_SOURCES_TABLE} ADD COLUMN {column} {definition}')
        latest = _columns_of(connection, NQ_CALL_LATEST_TABLE)
        if latest and set(LATEST_COLUMNS) - latest:
            connection.execute(f'DROP TABLE {NQ_CALL_LATEST_TABLE}')
            connection.execute('DELETE FROM workspace_state WHERE key = ?', (LATEST_STATE_KEY,))
        connection.executescript(SCHEMA)
        nq_prioritization.ensure_columns(connection)
        if not existed:
            connection.executemany(
                f"INSERT OR IGNORE INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('status', ?, ?, ?, ?)",
                [(name, color, index, int(closed)) for index, (name, color, closed) in enumerate(DEFAULT_STATUSES)],
            )
            connection.executemany(
                f"INSERT OR IGNORE INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('team', ?, ?, ?, 0)",
                [(name, color, index) for index, (name, color) in enumerate(DEFAULT_TEAMS)],
            )
        if not catalog_existed:
            _write_root_catalog(connection, _initial_root_catalog(connection))
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_STATE_KEY):
        _install_analysis_center(task_repository, fresh=not existed)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V2_STATE_KEY):
        _upgrade_analysis_center_v2(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V4_STATE_KEY):
        _upgrade_analysis_center_v4(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V5_STATE_KEY):
        _upgrade_analysis_center_v5(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V6_STATE_KEY):
        _upgrade_analysis_center_v6(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V9_STATE_KEY):
        _upgrade_analysis_center_v9(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V10_STATE_KEY):
        _upgrade_analysis_center_v10(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V11_STATE_KEY):
        _upgrade_analysis_center_v11(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V12_STATE_KEY):
        _upgrade_analysis_center_v12(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V13_STATE_KEY):
        _upgrade_analysis_center_v13(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V14_STATE_KEY):
        _upgrade_analysis_center_v14(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V15_STATE_KEY):
        _upgrade_analysis_center_v15(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V16_STATE_KEY):
        _upgrade_analysis_center_v16(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V17_STATE_KEY):
        _upgrade_analysis_center_v17(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V18_STATE_KEY):
        _upgrade_analysis_center_v18(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V19_STATE_KEY):
        _upgrade_analysis_center_v19(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V20_STATE_KEY):
        _upgrade_analysis_center_v20(task_repository)
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V21_STATE_KEY):
        name, former = V21_FORMER_RF_COLOR
        color = next(item[1] for item in nq_catalog.DEFAULT_DOMAINS if item[0] == name)
        with task_repository.connection() as connection:
            connection.execute(f"UPDATE {NQ_ROOT_CATALOG_TABLE} SET color = ? WHERE kind = 'domain' AND name = ? COLLATE NOCASE "
                               'AND lower(color) = ?', (color, name, former))
        task_repository.set_workspace_state(ANALYSIS_CENTER_V21_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V22_STATE_KEY):
        _rename_default_labels(task_repository, V22_FORMER_LABELS)
        task_repository.set_workspace_state(ANALYSIS_CENTER_V22_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V23_STATE_KEY):
        fields = list_fields(task_repository)
        if _add_default_fields(fields, V23_FIELD_KEYS):
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                       CATALOG_CALL_FIELDS))
        task_repository.set_workspace_state(ANALYSIS_CENTER_V23_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V24_STATE_KEY):
        fields = list_fields(task_repository)
        priority = next((field for field in fields if field['key'] == 'priority'), None)
        # The strategies give priorities up to P8: a Priority list that still has the default P1 to P5 takes P6 to P8.
        grown = priority is not None and [option['name'] for option in priority['options']] == [f'P{number}' for number in range(1, 6)]
        if grown:
            priority['options'].extend({'name': f'P{number}', 'color': ''} for number in range(6, 9))
        if _add_default_fields(fields, V24_FIELD_KEYS) or grown:
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                       CATALOG_CALL_FIELDS))
        task_repository.set_workspace_state(ANALYSIS_CENTER_V24_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V25_STATE_KEY):
        fields = list_fields(task_repository)
        priority = next((field for field in fields if field['key'] == 'priority'), None)
        colors = {f'P{number}': color for number, color in enumerate(nq_catalog.PRIORITY_COLORS, start=1)}
        painted = [option for option in (priority or {}).get('options') or []
                   if not option.get('color') and str(option.get('name') or '').upper() in colors]
        for option in painted:
            option['color'] = colors[str(option['name']).upper()]
        if painted:
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                       CATALOG_CALL_FIELDS))
        task_repository.set_workspace_state(ANALYSIS_CENTER_V25_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V26_STATE_KEY):
        fields = list_fields(task_repository)
        shown = [field for field in fields if field['key'] in V26_SHOWN_COLUMNS and not field['in_table']]
        for field in shown:
            field['in_table'] = True
        if shown:
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                       CATALOG_CALL_FIELDS))
        task_repository.set_workspace_state(ANALYSIS_CENTER_V26_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V27_STATE_KEY):
        fields = list_fields(task_repository)
        if _add_default_fields(fields, V27_FIELD_KEYS):
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                       CATALOG_CALL_FIELDS))
        task_repository.set_workspace_state(ANALYSIS_CENTER_V27_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V28_STATE_KEY):
        defaults = {field['key']: field for field in nq_catalog.DEFAULT_FIELDS if field['key'] in V27_FIELD_KEYS}
        _rename_default_labels(task_repository, tuple(
            (key, field['label'].replace(nq_dta_rca.SOURCE_LABEL, V28_FORMER_NAME)) for key, field in defaults.items()))
        fields = list_fields(task_repository)
        described = [field for field in fields if field['key'] in defaults
                     and field['description'] == defaults[field['key']]['description'].replace(nq_dta_rca.SOURCE_LABEL, V28_FORMER_NAME)]
        for field in described:
            field['description'] = defaults[field['key']]['description']
        if described:
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                       CATALOG_CALL_FIELDS))
        task_repository.set_workspace_state(ANALYSIS_CENTER_V28_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V29_STATE_KEY):
        _add_dta_categories(task_repository)
        task_repository.set_workspace_state(ANALYSIS_CENTER_V29_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V30_STATE_KEY):
        _dta_fields_first(task_repository)
        task_repository.set_workspace_state(ANALYSIS_CENTER_V30_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V31_STATE_KEY):
        _add_dta_categories(task_repository)
        nq_dta_rca.add_new_default_rules(task_repository, 2)
        task_repository.set_workspace_state(ANALYSIS_CENTER_V31_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V32_STATE_KEY):
        _add_dta_category_keywords(task_repository)
        task_repository.set_workspace_state(ANALYSIS_CENTER_V32_STATE_KEY, '1')
    if not task_repository.get_workspace_state(ANALYSIS_CENTER_V33_STATE_KEY):
        defaults = {field['key']: field['description'] for field in nq_catalog.DEFAULT_FIELDS}
        former = dict(V33_FORMER_DESCRIPTIONS)
        fields = list_fields(task_repository)
        described = [field for field in fields if field['key'] in former and field['description'] == former[field['key']]]
        for field in described:
            field['description'] = defaults[field['key']]
        if described:
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                       CATALOG_CALL_FIELDS))
        task_repository.set_workspace_state(ANALYSIS_CENTER_V33_STATE_KEY, '1')
    task_repository.set_workspace_state(SCHEMA_STATE_KEY, SCHEMA_VERSION)


def _dta_fields_first(task_repository: Any) -> None:
    """The fields of the DT Analyzer RCA move before the first field of the other RCA sources (the RCA of the CDR and
    the Ericsson RCA) in the RCA section, keeping their order; the other fields stay where they are."""
    fields = list_fields(task_repository)
    rca = [field for field in fields if field['section'] == 'rca']
    dta = [field for field in rca if field['source'] == 'dta']
    others = [field for field in rca if field['source'] != 'dta']
    first = next((position for position, field in enumerate(others) if field['source'] in {'cdr', 'rca'}), None)
    if not dta or first is None:
        return
    ordered = [*others[:first], *dta, *others[first:]]
    if [field['key'] for field in ordered] == [field['key'] for field in rca]:
        return
    moved = iter(ordered)
    fields = [next(moved) if field['section'] == 'rca' else field for field in fields]
    _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                               CATALOG_CALL_FIELDS))


def _add_dta_categories(task_repository: Any) -> None:
    """The Root Categories and Root Causes of the DT Analyzer RCA the catalog lacks (by name), in their default domain when
    the catalog has it, and each default cause without a Root Category mapped to its own; the rest of the catalog stays
    as it is."""
    defaults = nq_catalog.default_root_catalog()
    with task_repository.connection() as connection:
        current = nq_catalog.stored_root_catalog(_read_root_catalog(connection))
        names = {item['name'].casefold() for item in current['categories']}
        added = [{'name': item['name'], 'domain': item['domain'], 'keywords': list(item['keywords'])}
                 for item in defaults['categories'] if item['name'] in nq_catalog.DTA_CATEGORIES and item['name'].casefold() not in names]
        current['categories'] += added
        names = {item['name'].casefold() for item in current['causes']}
        causes = [{'name': item['name'], 'domain': item['domain'], 'keywords': list(item['keywords'])}
                  for item in defaults['causes'] if item['name'] in nq_catalog.DTA_CAUSES and item['name'].casefold() not in names]
        current['causes'] += causes
        known = {item['name'].casefold() for item in current['categories']}
        mapped = 0
        for cause in current['causes']:
            category = next((value for name, value in nq_catalog.DEFAULT_CAUSE_CATEGORIES.items() if name.casefold() == cause['name'].casefold()), '')
            if category and not cause.get('category') and category.casefold() in known:
                cause['category'] = category
                mapped += 1
        if added or causes or mapped:
            _write_root_catalog(connection, nq_catalog.normalize_root_catalog(current))
    if (added or causes or mapped) and hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log('system', 'nq_root_causes', json.dumps(
            {'message': 'Root Categories and Root Causes of the DT Analyzer RCA added to the root cause catalog.',
             'categories': [item['name'] for item in added], 'causes': [item['name'] for item in causes], 'causes_mapped': mapped},
            ensure_ascii=False))


def _add_dta_category_keywords(task_repository: Any) -> None:
    """The default keywords of the Root Categories of the DT Analyzer RCA (Protocol / Server, Authentication & Registration…)
    for those still without any, so the values of NetCheck such as DNS or Registration reject find their category; the
    keywords a workspace gave them stay."""
    with task_repository.connection() as connection:
        current = nq_catalog.stored_root_catalog(_read_root_catalog(connection))
        defaults = {name.casefold(): keywords for name, keywords in nq_catalog.DTA_CATEGORY_KEYWORDS.items()}
        given = []
        for item in current['categories']:
            keywords = defaults.get(item['name'].casefold())
            if keywords and not item.get('keywords'):
                item['keywords'] = list(keywords)
                given.append(item['name'])
        if given:
            _write_root_catalog(connection, nq_catalog.normalize_root_catalog(current))
    if given and hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log('system', 'nq_root_causes', json.dumps(
            {'message': 'Keywords of the Root Categories of the DT Analyzer RCA added to the root cause catalog.', 'categories': given},
            ensure_ascii=False))


def _initial_root_catalog(connection: Any) -> dict[str, list[dict[str, Any]]]:
    """The default root cause catalog, merged with the domains and causes of the first version's taxonomy."""
    catalog = nq_catalog.default_root_catalog()
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                              (_LEGACY_ROOT_CAUSES_TABLE,)).fetchone():
        return catalog
    rows = connection.execute(
        f'SELECT domain, cause, color, keywords FROM {_LEGACY_ROOT_CAUSES_TABLE} ORDER BY position, cause COLLATE NOCASE').fetchall()
    domains = {item['name'].casefold(): item for item in catalog['domains']}
    causes = {item['name'].casefold(): item for item in catalog['causes']}
    for row in rows:
        name, cause = str(row['domain']), str(row['cause'] or '')
        words = _keywords(json.loads(row['keywords'] or '[]'))
        if not cause:
            # The workspace's own domains keep their colour and keywords.
            target = domains.get(name.casefold())
            if target is None:
                target = {'name': name, 'color': str(row['color'] or '#7b8790'), 'keywords': words}
                catalog['domains'].append(target)
                domains[name.casefold()] = target
            else:
                target.update(color=str(row['color'] or target['color']), keywords=words)
        elif cause.casefold() in causes:
            causes[cause.casefold()].update(domain=name, keywords=words)
        else:
            item = {'name': cause, 'domain': name, 'keywords': words}
            catalog['causes'].append(item)
            causes[cause.casefold()] = item
    connection.execute(f'DROP TABLE {_LEGACY_ROOT_CAUSES_TABLE}')
    return catalog


def _install_analysis_center(task_repository: Any, fresh: bool) -> None:
    """Add the Analysis Center to a workspace once: its fields, statuses, teams and status rules.

    Fields with the name of a default field keep their key and values and take its section and
    place. The statuses and teams of the first version are replaced (and their calls moved to the
    new statuses) while nobody changed them; otherwise the missing defaults are added.
    """
    current = list_fields(task_repository)
    by_label = {field['label'].casefold(): field for field in current}
    by_key = {field['key']: field for field in current}
    merged: list[dict[str, Any]] = []
    used: set[str] = set()
    for default in nq_catalog.default_fields():
        existing = by_key.get(default['key']) or by_label.get(default['label'].casefold())
        if existing is not None and existing['source'] == 'user' and default['source'] == 'user' and existing['type'] == default['type']:
            merged.append({**default, 'key': existing['key'], 'options': existing['options'] or default['options'],
                           'in_table': existing['in_table'] or default['in_table'],
                           'in_summary': existing['in_summary'] or default['in_summary'],
                           'required_to_close': existing['required_to_close']})
            used.add(existing['key'])
        elif default['key'] in by_key:
            merged.append(by_key[default['key']])
            used.add(default['key'])
        else:
            merged.append(default)
    merged += [field for field in current if field['key'] not in used]
    _store_fields(task_repository, nq_catalog.normalize_fields(merged, by_key, CATALOG_CALL_FIELDS))
    options = list_options(task_repository)
    names = [item['name'] for item in options['statuses']]
    with task_repository.connection() as connection:
        if fresh or [name.casefold() for name in names] == [name.casefold() for name in _FIRST_STATUSES]:
            for old, new in _FIRST_STATUS_MOVES.items():
                connection.execute(f'UPDATE {NQ_CALL_TRACKING_TABLE} SET status = ? WHERE status = ? COLLATE NOCASE', (new, old))
            connection.execute(f"DELETE FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = 'status'")
            connection.executemany(
                f"INSERT INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('status', ?, ?, ?, ?)",
                [(name, color, index, int(closed)) for index, (name, color, closed) in enumerate(DEFAULT_STATUSES)])
        else:
            known = {name.casefold() for name in names}
            missing = [entry for entry in DEFAULT_STATUSES if entry[0].casefold() not in known]
            if missing and missing[0][0] == DEFAULT_STATUSES[0][0]:
                connection.execute(f"UPDATE {NQ_CALL_OPTIONS_TABLE} SET position = position + 1 WHERE kind = 'status'")
                connection.execute(f"INSERT INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('status', ?, ?, 0, ?)",
                                   (missing[0][0], missing[0][1], int(missing[0][2])))
                missing = missing[1:]
            position = len(names) + 1
            for name, color, closed in missing:
                connection.execute(f"INSERT INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('status', ?, ?, ?, ?)",
                                   (name, color, position, int(closed)))
                position += 1
        teams = [item['name'] for item in options['teams']]
        teams_used = connection.execute(f"SELECT COUNT(*) FROM {NQ_CALL_TRACKING_TABLE} WHERE team <> ''").fetchone()[0]
        if fresh or ([name.casefold() for name in teams] == [name.casefold() for name in _FIRST_TEAMS] and not teams_used):
            connection.execute(f"DELETE FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = 'team'")
            connection.execute(f'DELETE FROM {NQ_TEAM_MEMBERS_TABLE}')
            connection.executemany(
                f"INSERT INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('team', ?, ?, ?, 0)",
                [(name, color, index) for index, (name, color) in enumerate(DEFAULT_TEAMS)])
        # The follow-up of the first version was chosen by hand: it stays as it is, except the first status.
        connection.execute(f"UPDATE {NQ_CALL_TRACKING_TABLE} SET status_mode = CASE WHEN status IN ('', ?, 'Open') "
                           "THEN 'auto' ELSE 'manual' END", (DEFAULT_STATUSES[0][0],))
    statuses = [item['name'] for item in list_options(task_repository)['statuses']]
    fields = list_fields(task_repository)
    rules = []
    known = nq_catalog.condition_fields(fields)
    for rule in nq_catalog.default_status_rules():
        conditions = [condition for condition in rule['conditions'] if condition['field'] in known]
        if rule['status'] in statuses and conditions:
            rules.append({**rule, 'conditions': conditions})
    task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
    task_repository.set_workspace_state(ANALYSIS_CENTER_STATE_KEY, '1')
    recompute_statuses(task_repository, 'system')


def _upgrade_analysis_center_v2(task_repository: Any) -> None:
    """The second layout once, for what the workspace kept of the first one: Failure Details (formerly Failure Event)
    in red and Implementation and Planning in green, the Last Cell ID and Failure Comment of the CDR in Failure
    Details (Serving Cell when Failure proposing the last cell), and the Analysis fields in the order of the call panel."""
    try:
        sections = json.loads(task_repository.get_workspace_state(SECTIONS_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        sections = []
    defaults = {section['key']: section for section in nq_catalog.default_sections()}
    changed = False
    for section in sections if isinstance(sections, list) else []:
        if not isinstance(section, dict) or section.get('key') not in defaults:
            continue
        key = section['key']
        first_color = nq_catalog.FIRST_SECTION_COLORS.get(key)
        if first_color and str(section.get('color') or '').casefold() == first_color.casefold():
            section['color'] = defaults[key]['color']
            changed = True
        if nq_catalog.FIRST_SECTION_LABELS.get(key) == str(section.get('label') or ''):
            section['label'] = defaults[key]['label']
            changed = True
    if changed:
        task_repository.set_workspace_state(SECTIONS_STATE_KEY, json.dumps(nq_catalog.normalize_sections(sections)))
    fields = list_fields(task_repository)
    keys = [field['key'] for field in fields]
    first = list(nq_catalog.FIRST_ANALYSIS_ORDER)
    if [key for key in keys if key in first] == first:
        order = [field['key'] for field in nq_catalog.default_fields() if field['key'] in first]
        by_key = {field['key']: field for field in fields}
        for position, key in zip(sorted(keys.index(key) for key in first), order):
            fields[position] = by_key[key]
    # The new fields of the CDR.
    _add_default_fields(fields, {'last_cell_id', 'failure_comment'})
    for field in fields:
        if field['key'] == 'serving_cell_when_failure' and field.get('suggest_from') == 'cell_id':
            field['suggest_from'] = 'last_cell_id'
    _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                               CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V2_STATE_KEY, '1')


def _upgrade_analysis_center_v4(task_repository: Any) -> None:
    """The fields of the Auto RCA output of the Ericsson RCA, once: its initial RCA Category and Subcategory
    before the suggestion and the RCA Evidence after it."""
    fields = list_fields(task_repository)
    if _add_default_fields(fields, {'rca_initial_category', 'rca_initial_subcategory', 'rca_evidence'}, same_source=True):
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                   CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V4_STATE_KEY, '1')


def _upgrade_analysis_center_v5(task_repository: Any) -> None:
    """NetCheck before the Ericsson RCA, once: the RCA fields from the CDR move before the first field of the
    script (keeping their order), and the default fields whose description named the RCA script take the new one."""
    fields = list_fields(task_repository)
    defaults = {field['key']: field for field in nq_catalog.default_fields()}
    changed = False
    rca = [field for field in fields if field['section'] == 'rca']
    script = next((position for position, field in enumerate(rca) if field['source'] == 'rca'), None)
    if script is not None and any(field['source'] == 'cdr' for field in rca[script:]):
        netcheck = [field for field in rca if field['source'] == 'cdr']
        others = [field for field in rca if field['source'] != 'cdr']
        first = next(position for position, field in enumerate(others) if field['source'] == 'rca')
        others[first:first] = netcheck
        ordered = iter(others)
        fields = [next(ordered) if field['section'] == 'rca' else field for field in fields]
        changed = True
    for field in fields:
        if 'RCA script' in str(field.get('description') or '') and field['key'] in defaults:
            field['description'] = defaults[field['key']]['description']
            changed = True
    if changed:
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                   CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V5_STATE_KEY, '1')


def _upgrade_analysis_center_v6(task_repository: Any) -> None:
    """The fields of the analyses of the previous tool, once, each after the field it follows by default."""
    fields = list_fields(task_repository)
    if _add_default_fields(fields, ANALYSES_FIELD_KEYS):
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                   CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V6_STATE_KEY, '1')


# The default values renamed once by the ninth version: (field, former value, value).
V9_OPTION_RENAMES = (*(('priority', str(number), f'P{number}') for number in range(1, 6)),
                     ('implementation_stream', 'E2E stream', 'E2E Team'))
V9_TEAM_RENAMES = (('E2E stream', 'E2E Team'),)
V9_DOMAIN_RENAMES = (('Core 2G/4G/5G', 'Core'),)
# The vendor fields: former labels of the first one, and the former key and label of the second one.
V9_VENDOR_LABELS = {'vendor when failure', 'vendor a when failure'}
V9_SECOND_VENDOR = ('vendor_b_when_failure', 'Vendor B when Failure')


def _upgrade_analysis_center_v9(task_repository: Any) -> None:
    """Once: Vendor when Failure becomes Vendor 1 when Failure, followed by Vendor 2 when Failure (with the values of
    the former Vendor B when Failure); the default priorities 1 to 4 become P1 to P4, the team E2E stream becomes
    E2E Team and the domain Core 2G/4G/5G becomes Core, with their calls (unless the workspace already has the new
    name)."""
    defaults = {field['key']: field for field in nq_catalog.DEFAULT_FIELDS}
    fields = list_fields(task_repository)
    before = [dict(field, options=[dict(option) for option in field['options']]) for field in fields]
    by_key = {field['key']: field for field in fields}
    vendor = by_key.get('vendor_when_failure')
    if vendor and vendor['label'].casefold() in V9_VENDOR_LABELS:
        vendor['label'] = defaults['vendor_when_failure']['label']
        vendor['description'] = vendor.get('description') or defaults['vendor_when_failure']['description']
    second = by_key.get(V9_SECOND_VENDOR[0])
    if second and 'vendor_2_when_failure' not in by_key:
        second['key'] = 'vendor_2_when_failure'
        if second['label'] == V9_SECOND_VENDOR[1]:
            second['label'] = defaults['vendor_2_when_failure']['label']
    _add_default_fields(fields, {'vendor_2_when_failure'})
    renamed: list[tuple[str, str, str]] = []
    for key, old, new in V9_OPTION_RENAMES:
        options = (by_key.get(key) or {}).get('options') or []
        names = {option['name'].casefold() for option in options}
        option = next((option for option in options if option['name'].casefold() == old.casefold()), None)
        if option and new.casefold() not in names:
            option['previous'], option['name'] = option['name'], new
            renamed.append((key, old, new))
    with task_repository.connection() as connection:
        if second is not None and second['key'] == 'vendor_2_when_failure':
            connection.execute(f'UPDATE {NQ_FIELD_VALUES_TABLE} SET field_key = ? WHERE field_key = ?', ('vendor_2_when_failure', V9_SECOND_VENDOR[0]))
            connection.execute(f'UPDATE {NQ_CALL_HISTORY_TABLE} SET field = ? WHERE field = ?',
                               ('field:vendor_2_when_failure', f'field:{V9_SECOND_VENDOR[0]}'))
        for key, old, new in renamed:
            connection.execute(f'UPDATE {NQ_FIELD_VALUES_TABLE} SET value = ? WHERE field_key = ? AND value = ? COLLATE NOCASE',
                               (new, key, old))
        teams = {str(row[0]).casefold() for row in connection.execute(f"SELECT name FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = 'team'")}
        for old, new in V9_TEAM_RENAMES:
            if old.casefold() in teams and new.casefold() not in teams:
                connection.execute(f"UPDATE {NQ_CALL_OPTIONS_TABLE} SET name = ? WHERE kind = 'team' AND name = ? COLLATE NOCASE", (new, old))
                connection.execute(f'UPDATE {NQ_CALL_TRACKING_TABLE} SET team = ? WHERE team = ? COLLATE NOCASE', (new, old))
                connection.execute(f'UPDATE {NQ_TEAM_MEMBERS_TABLE} SET team = ? WHERE team = ? COLLATE NOCASE', (new, old))
        domains = {str(row[0]).casefold() for row in connection.execute(f"SELECT name FROM {NQ_ROOT_CATALOG_TABLE} WHERE kind = 'domain'")}
        renamed_domains = [(old, new) for old, new in V9_DOMAIN_RENAMES if old.casefold() in domains and new.casefold() not in domains]
        for old, new in renamed_domains:
            connection.execute(f"UPDATE {NQ_ROOT_CATALOG_TABLE} SET name = ? WHERE kind = 'domain' AND name = ? COLLATE NOCASE", (new, old))
            connection.execute(f"UPDATE {NQ_ROOT_CATALOG_TABLE} SET domain = ? WHERE kind <> 'domain' AND domain = ? COLLATE NOCASE", (new, old))
            connection.execute(f'UPDATE {NQ_CALL_TRACKING_TABLE} SET root_domain = ? WHERE root_domain = ? COLLATE NOCASE', (new, old))
    normalized = nq_catalog.normalize_fields(fields, {field['key']: field for field in before}, CATALOG_CALL_FIELDS)
    if renamed:
        rules = nq_catalog.rules_after_field_changes(status_rules(task_repository), before, normalized)
        task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
    _store_fields(task_repository, normalized)
    # The reviewed equivalences of the analyses and the shared filters name the renamed domain too.
    if renamed_domains:
        names = {old.casefold(): new for old, new in renamed_domains}
        equivalences = workspace_equivalences(task_repository)
        for values in equivalences.values():
            for item in values.values():
                item['domain'] = names.get(item['domain'].casefold(), item['domain'])
        _save_equivalences(task_repository, equivalences)
        try:
            saved = json.loads(task_repository.get_workspace_state(SAVED_FILTERS_STATE_KEY) or '{}')
        except (TypeError, ValueError):
            saved = {}
        if isinstance(saved, dict) and isinstance(saved.get('root_domain'), list):
            saved['root_domain'] = [names.get(str(value).casefold(), value) for value in saved['root_domain']]
            task_repository.set_workspace_state(SAVED_FILTERS_STATE_KEY, json.dumps(saved, ensure_ascii=False, sort_keys=True))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V9_STATE_KEY, '1')


def _upgrade_analysis_center_v11(task_repository: Any) -> None:
    """The Unique ID and Polygon Area fields, once, each after the field it follows by default."""
    fields = list_fields(task_repository)
    if _add_default_fields(fields, ANALYSES_V11_FIELD_KEYS):
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                   CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V11_STATE_KEY, '1')


# A former default team and Implementation Stream (now Implementation Team), and the value its calls take.
V10_REMOVED_TEAM = ('Successful Call-Excluded', 'No Team')


def _upgrade_analysis_center_v10(task_repository: Any) -> None:
    """Once: the team Successful Call-Excluded is removed; its calls (and members) go to No Team, which it becomes
    when the workspace has none. The value of Implementation Stream follows the same way. The priorities P1 to P4
    get P5 after them."""
    old, new = V10_REMOVED_TEAM
    with task_repository.connection() as connection:
        teams = {str(row[0]).casefold(): str(row[0]) for row in connection.execute(
            f"SELECT name FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = 'team'")}
        if old.casefold() in teams:
            used = connection.execute(f'SELECT COUNT(*) FROM {NQ_CALL_TRACKING_TABLE} WHERE team = ? COLLATE NOCASE', (old,)).fetchone()[0]
            if used and new.casefold() not in teams:
                connection.execute(f"UPDATE {NQ_CALL_OPTIONS_TABLE} SET name = ? WHERE kind = 'team' AND name = ? COLLATE NOCASE", (new, old))
            else:
                connection.execute(f"DELETE FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = 'team' AND name = ? COLLATE NOCASE", (old,))
            target = teams.get(new.casefold(), new)
            connection.execute(f'UPDATE {NQ_CALL_TRACKING_TABLE} SET team = ? WHERE team = ? COLLATE NOCASE', (target, old))
            connection.execute(f'UPDATE OR IGNORE {NQ_TEAM_MEMBERS_TABLE} SET team = ? WHERE team = ? COLLATE NOCASE', (target, old))
            connection.execute(f'DELETE FROM {NQ_TEAM_MEMBERS_TABLE} WHERE team = ? COLLATE NOCASE', (old,))
        used_stream = connection.execute(
            f"SELECT COUNT(*) FROM {NQ_FIELD_VALUES_TABLE} WHERE field_key = 'implementation_stream' AND value = ? COLLATE NOCASE",
            (old,)).fetchone()[0]
        if used_stream:
            connection.execute(f"UPDATE {NQ_FIELD_VALUES_TABLE} SET value = ? WHERE field_key = 'implementation_stream' AND value = ? COLLATE NOCASE",
                               (new, old))
    fields = list_fields(task_repository)
    changed = False
    priority = next((field for field in fields if field['key'] == 'priority'), None)
    if priority is not None and [option['name'] for option in priority['options']] == [f'P{number}' for number in range(1, 5)]:
        priority['options'].append({'name': 'P5', 'color': ''})
        changed = True
    stream = next((field for field in fields if field['key'] == 'implementation_stream'), None)
    if stream is not None and any(option['name'].casefold() == old.casefold() for option in stream['options']):
        names = {option['name'].casefold() for option in stream['options']}
        if used_stream and new.casefold() not in names:
            stream['options'] = [dict(option, name=new) if option['name'].casefold() == old.casefold() else option for option in stream['options']]
        else:
            stream['options'] = [option for option in stream['options'] if option['name'].casefold() != old.casefold()]
        changed = True
    if changed:
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                   CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V10_STATE_KEY, '1')


# The former key, label and description of the Implementation Team.
V12_FORMER_TEAM_FIELD = ('implementation_stream', 'Implementation Stream',
                         'The stream responsible for the implementation (it can differ from the team that analysed the call).')


def _upgrade_analysis_center_v12(task_repository: Any) -> None:
    """Once: the field Implementation Stream becomes Implementation Team (its label and description too unless they
    were changed), with its values, history, Status Rules, shared filters and reviewed equivalences."""
    old_key, old_label, old_description = V12_FORMER_TEAM_FIELD
    new_key = 'implementation_team'
    fields = list_fields(task_repository)
    field = next((field for field in fields if field['key'] == old_key), None)
    if field is not None and all(other['key'] != new_key for other in fields):
        default = next(item for item in nq_catalog.DEFAULT_FIELDS if item['key'] == new_key)
        before = [dict(item, options=[dict(option) for option in item['options']]) for item in fields]
        field['key'] = new_key
        if field['label'].casefold() == old_label.casefold():
            field['label'] = default['label']
        if field.get('description') == old_description:
            field['description'] = default['description']
        with task_repository.connection() as connection:
            connection.execute(f'UPDATE {NQ_FIELD_VALUES_TABLE} SET field_key = ? WHERE field_key = ?', (new_key, old_key))
            connection.execute(f'UPDATE {NQ_CALL_HISTORY_TABLE} SET field = ? WHERE field = ?', (f'field:{new_key}', f'field:{old_key}'))
        try:
            rules = json.loads(task_repository.get_workspace_state(STATUS_RULES_STATE_KEY) or '[]')
        except (TypeError, ValueError):
            rules = []
        if isinstance(rules, list) and rules:
            for rule in rules:
                for condition in (rule.get('conditions') or []) if isinstance(rule, dict) else []:
                    if isinstance(condition, dict) and condition.get('field') == old_key:
                        condition['field'] = new_key
            task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
        try:
            saved = json.loads(task_repository.get_workspace_state(SAVED_FILTERS_STATE_KEY) or '{}')
        except (TypeError, ValueError):
            saved = {}
        if isinstance(saved, dict) and isinstance(saved.get('fields'), dict) and old_key in saved['fields']:
            saved['fields'][new_key] = saved['fields'].pop(old_key)
            task_repository.set_workspace_state(SAVED_FILTERS_STATE_KEY, json.dumps(saved, ensure_ascii=False, sort_keys=True))
        equivalences = workspace_equivalences(task_repository)
        if f'field:{old_key}' in equivalences:
            equivalences.setdefault(f'field:{new_key}', {}).update(equivalences.pop(f'field:{old_key}'))
            _save_equivalences(task_repository, equivalences)
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {item['key']: item for item in before}, CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V12_STATE_KEY, '1')


def _upgrade_analysis_center_v13(task_repository: Any) -> None:
    """Once: the values of the Planned FY written as years or quarters become fiscal years (2030 is FY30, merged with
    FY30 when the list has it), the fiscal years in order, with the values of the calls, the Status Rules, the shared
    filters and the reviewed equivalences; and its default description names the fiscal years."""
    fields = list_fields(task_repository)
    field = next((item for item in fields if item['key'] == FISCAL_FIELD and item['type'] == 'list'), None)
    if field is not None and field.get('description') == V13_FORMER_DESCRIPTION:
        field['description'] = next(item for item in nq_catalog.DEFAULT_FIELDS if item['key'] == FISCAL_FIELD)['description']
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {item['key']: item for item in list_fields(task_repository)},
                                                                   CATALOG_CALL_FIELDS))
        fields = list_fields(task_repository)
        field = next(item for item in fields if item['key'] == FISCAL_FIELD)
    if field is not None:
        before = {item['key']: dict(item, options=[dict(option) for option in item['options']]) for item in fields}
        names = {option['name']: nq_analyses.fiscal_year(option['name']) for option in field['options']}
        names = {old: new for old, new in names.items() if new and new != old}
        options: dict[str, dict[str, Any]] = {}
        for option in field['options']:
            name = names.get(option['name'], option['name'])
            kept = options.setdefault(name.casefold(), dict(option, name=name))
            if not kept.get('color') and option.get('color'):
                kept['color'] = option['color']
        ordered = _in_fiscal_order(list(options.values()))
        if names or [option['name'] for option in ordered] != [option['name'] for option in field['options']]:
            field['options'] = ordered
            renamed = {old.casefold(): new for old, new in names.items()}
            with task_repository.connection() as connection:
                for old, new in names.items():
                    connection.execute(f'UPDATE {NQ_FIELD_VALUES_TABLE} SET value = ? WHERE field_key = ? AND value = ? COLLATE NOCASE',
                                       (new, FISCAL_FIELD, old))
            try:
                rules = json.loads(task_repository.get_workspace_state(STATUS_RULES_STATE_KEY) or '[]')
            except (TypeError, ValueError):
                rules = []
            if names and isinstance(rules, list) and rules:
                for rule in rules:
                    for condition in (rule.get('conditions') or []) if isinstance(rule, dict) else []:
                        if isinstance(condition, dict) and condition.get('field') == FISCAL_FIELD and isinstance(condition.get('values'), list):
                            condition['values'] = list(dict.fromkeys(renamed.get(str(value).casefold(), value) for value in condition['values']))
                task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
            try:
                saved = json.loads(task_repository.get_workspace_state(SAVED_FILTERS_STATE_KEY) or '{}')
            except (TypeError, ValueError):
                saved = {}
            if names and isinstance(saved, dict) and isinstance((saved.get('fields') or {}).get(FISCAL_FIELD), list):
                saved['fields'][FISCAL_FIELD] = list(dict.fromkeys(renamed.get(str(value).casefold(), value)
                                                                   for value in saved['fields'][FISCAL_FIELD]))
                task_repository.set_workspace_state(SAVED_FILTERS_STATE_KEY, json.dumps(saved, ensure_ascii=False, sort_keys=True))
            equivalences = workspace_equivalences(task_repository)
            if names and f'field:{FISCAL_FIELD}' in equivalences:
                for item in equivalences[f'field:{FISCAL_FIELD}'].values():
                    item['to'] = renamed.get(item['to'].casefold(), item['to'])
                _save_equivalences(task_repository, equivalences)
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, before, CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V13_STATE_KEY, '1')


def _upgrade_analysis_center_v14(task_repository: Any) -> None:
    """Once: the suggested cause columns of the NetCheck RCA and of the Ericsson RCA leave the table."""
    fields = list_fields(task_repository)
    before = {item['key']: dict(item, options=[dict(option) for option in item['options']]) for item in fields}
    changed = False
    for field in fields:
        if field['key'] in V14_HIDDEN_COLUMNS and field['in_table']:
            field['in_table'] = False
            changed = True
    if changed:
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, before, CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V14_STATE_KEY, '1')


def _upgrade_analysis_center_v15(task_repository: Any) -> None:
    """Once: the fields of the NetCheck RCA start with NetCheck RCA and those of the Ericsson RCA with Ericsson RCA
    (those renamed by hand keep their name)."""
    _rename_default_labels(task_repository, V15_FORMER_LABELS)
    task_repository.set_workspace_state(ANALYSIS_CENTER_V15_STATE_KEY, '1')


def _rename_default_labels(task_repository: Any, former_labels: tuple[tuple[str, str], ...]) -> None:
    """The default fields still named as before take their current name (those renamed by hand keep theirs)."""
    fields = list_fields(task_repository)
    before = {item['key']: dict(item, options=[dict(option) for option in item['options']]) for item in fields}
    defaults = {item['key']: item['label'] for item in nq_catalog.DEFAULT_FIELDS}
    former = dict(former_labels)
    taken = {field['label'].casefold() for field in fields}
    changed = False
    for field in fields:
        label = defaults.get(field['key'], '')
        if field['key'] in former and field['label'].casefold() == former[field['key']].casefold() and label.casefold() not in taken:
            field['label'] = label
            changed = True
    if changed:
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, before, CATALOG_CALL_FIELDS))


def _upgrade_analysis_center_v16(task_repository: Any) -> None:
    """Once: the Implementation Status is a column of the table, after the Analysis Status."""
    fields = list_fields(task_repository)
    before = {item['key']: dict(item, options=[dict(option) for option in item['options']]) for item in fields}
    shown = [field for field in fields if field['key'] in V16_SHOWN_COLUMNS and not field['in_table']]
    for field in shown:
        field['in_table'] = True
    if shown:
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, before, CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V16_STATE_KEY, '1')


def _upgrade_analysis_center_v17(task_repository: Any) -> None:
    """Once: the Findings move right after the Description when they followed the Proposed Measure."""
    fields = list_fields(task_repository)
    keys = [field['key'] for field in fields]
    if {'description', 'proposed_measure', 'findings'} <= set(keys) \
            and keys.index('description') < keys.index('proposed_measure') < keys.index('findings'):
        findings = fields.pop(keys.index('findings'))
        fields.insert(keys.index('description') + 1, findings)
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {item['key']: item for item in list_fields(task_repository)},
                                                                   CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V17_STATE_KEY, '1')


def _upgrade_analysis_center_v18(task_repository: Any) -> None:
    """Once: the Implementation Status keeps implementation values only. Its Planned and Not Planned move to the
    Planned Status of their calls (one that already has another keeps it, and the history tells the value removed),
    Invalidated becomes Not Applicable and Closed becomes Implemented, with the Status Rules, the shared filters and the
    reviewed equivalences; Not yet evaluated turns red. The statuses follow."""
    fields = list_fields(task_repository)
    by_key = {field['key']: field for field in fields}
    implementation, planned = by_key.get('implementation_status'), by_key.get('planned_status')
    if not implementation or implementation['type'] != 'list' or implementation['source'] != 'user':
        task_repository.set_workspace_state(ANALYSIS_CENTER_V18_STATE_KEY, '1')
        return
    before = {item['key']: dict(item, options=[dict(option) for option in item['options']]) for item in fields}
    defaults = {option['name']: option['color'] for field in nq_catalog.DEFAULT_FIELDS if field['key'] == 'implementation_status'
                for option in field['options']}
    planning = nq_analyses.PLANNING_STATUSES if planned and planned['type'] == 'list' and planned['source'] == 'user' else ()
    planned_names = {option['name'].casefold(): option['name'] for option in (planned or {}).get('options', [])}
    renamed: dict[str, str] = {}
    moved: set[str] = set()
    when = now_iso()
    with task_repository.connection() as connection:
        for old, new in V18_IMPLEMENTATION_RENAMES.items():
            rows = connection.execute(f"SELECT call_key, value FROM {NQ_FIELD_VALUES_TABLE} WHERE field_key = 'implementation_status' "
                                      'AND value = ? COLLATE NOCASE', (old,)).fetchall()
            for row in rows:
                _record_history(connection, str(row['call_key']), 'field:implementation_status', str(row['value']), new, 'system', when)
            if rows:
                renamed[old] = new
                connection.execute(f"UPDATE {NQ_FIELD_VALUES_TABLE} SET value = ? WHERE field_key = 'implementation_status' "
                                   'AND value = ? COLLATE NOCASE', (new, old))
        for row in connection.execute(f"SELECT call_key, value, updated_by, updated_at FROM {NQ_FIELD_VALUES_TABLE} "
                                      f"WHERE field_key = 'implementation_status' AND lower(value) IN ({', '.join('?' for _ in planning) or "''"})",
                                      list(planning)).fetchall():
            call_key, value = str(row['call_key']), str(row['value'])
            name = planned_names.get(value.casefold(), value)
            moved.add(name)
            current = connection.execute(f"SELECT value FROM {NQ_FIELD_VALUES_TABLE} WHERE call_key = ? AND field_key = 'planned_status'",
                                         (call_key,)).fetchone()
            if not current or not str(current['value']).strip():
                connection.execute(
                    f'INSERT INTO {NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, ?) '
                    'ON CONFLICT(call_key, field_key) DO UPDATE SET value = excluded.value',
                    (call_key, 'planned_status', name, row['updated_by'], row['updated_at']))
                _record_history(connection, call_key, 'field:planned_status', '', name, 'system', when)
            _record_history(connection, call_key, 'field:implementation_status', value, '', 'system', when)
            connection.execute(f"DELETE FROM {NQ_FIELD_VALUES_TABLE} WHERE call_key = ? AND field_key = 'implementation_status'",
                               (call_key,))
    # The lists: the Implementation Status without the planning, invalidated and closed values (Not Applicable and
    # Implemented in their place), the Planned Status with the planning values it lacked.
    dropped = {*planning, *V18_IMPLEMENTATION_RENAMES}
    options = [option for option in implementation['options'] if option['name'].casefold() not in dropped]
    for name in dict.fromkeys(V18_IMPLEMENTATION_RENAMES.values()):
        if name.casefold() not in {option['name'].casefold() for option in options} \
                and (name in renamed.values() or any(option['name'].casefold() == name.casefold() for option in implementation['options'])):
            options.append({'name': name, 'color': defaults.get(name, '')})
    for option in options:
        if option['name'] == 'Not yet evaluated' and option.get('color', '').casefold() == V18_FORMER_NOT_EVALUATED_COLOR:
            option['color'] = defaults['Not yet evaluated']
        if not option.get('color') and defaults.get(option['name']):
            option['color'] = defaults[option['name']]
    implementation['options'] = options
    if planned:
        for name in sorted(moved):
            if name.casefold() not in {option['name'].casefold() for option in planned['options']}:
                planned['options'].append({'name': name, 'color': ''})
    mapping = {**{old: new for old, new in V18_IMPLEMENTATION_RENAMES.items()}}
    def implementation_values(values: list[Any]) -> list[str]:
        return list(dict.fromkeys(mapping.get(str(value).casefold(), str(value)) for value in values
                                  if str(value).casefold() not in planning))
    try:
        rules = json.loads(task_repository.get_workspace_state(STATUS_RULES_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        rules = []
    if isinstance(rules, list) and rules:
        for rule in rules:
            for condition in (rule.get('conditions') or []) if isinstance(rule, dict) else []:
                if isinstance(condition, dict) and condition.get('field') == 'implementation_status' and isinstance(condition.get('values'), list):
                    condition['values'] = implementation_values(condition['values'])
        task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
    try:
        saved = json.loads(task_repository.get_workspace_state(SAVED_FILTERS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        saved = {}
    chosen = (saved.get('fields') or {}).get('implementation_status') if isinstance(saved, dict) and isinstance(saved.get('fields'), dict) else None
    if isinstance(chosen, list):
        moved_filter = [planned_names.get(str(value).casefold(), str(value)) for value in chosen if str(value).casefold() in planning]
        saved['fields']['implementation_status'] = implementation_values(chosen)
        if moved_filter:
            saved['fields']['planned_status'] = list(dict.fromkeys([*saved['fields'].get('planned_status', []), *moved_filter]))
        if not saved['fields']['implementation_status']:
            del saved['fields']['implementation_status']
        task_repository.set_workspace_state(SAVED_FILTERS_STATE_KEY, json.dumps(saved, ensure_ascii=False, sort_keys=True))
    equivalences = workspace_equivalences(task_repository)
    if 'field:implementation_status' in equivalences:
        for item in equivalences['field:implementation_status'].values():
            item['to'] = mapping.get(item['to'].casefold(), item['to'])
        _save_equivalences(task_repository, equivalences)
    _store_fields(task_repository, nq_catalog.normalize_fields(fields, before, CATALOG_CALL_FIELDS))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V18_STATE_KEY, '1')
    recompute_statuses(task_repository, 'system')


def _upgrade_analysis_center_v19(task_repository: Any) -> None:
    """Once: the status Open leaves the statuses and becomes the group of the phase statuses. Its rules (the attended
    calls) give Under Analysis, its calls set by hand are Under Analysis by hand (the history tells it), the shared
    filters choose the phase statuses instead, and the statuses follow the rules again."""
    old, new = V19_FORMER_OPEN
    statuses = list_options(task_repository)['statuses']
    names = {item['name'].casefold(): item for item in statuses}
    if old.casefold() not in names or new.casefold() not in names or names[old.casefold()]['closed'] \
            or statuses[0]['name'].casefold() == old.casefold():
        task_repository.set_workspace_state(ANALYSIS_CENTER_V19_STATE_KEY, '1')
        return
    old_name, new_name = names[old.casefold()]['name'], names[new.casefold()]['name']
    group = [item['name'] for item in statuses[1:] if not item['closed'] and item['name'] != old_name]
    try:
        rules = json.loads(task_repository.get_workspace_state(STATUS_RULES_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        rules = []
    if isinstance(rules, list) and rules:
        for rule in rules:
            if isinstance(rule, dict) and str(rule.get('status') or '').casefold() == old.casefold():
                rule['status'] = new_name
        task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
    try:
        saved = json.loads(task_repository.get_workspace_state(SAVED_FILTERS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        saved = {}
    if isinstance(saved, dict) and isinstance(saved.get('status'), list) \
            and any(str(value).casefold() == old.casefold() for value in saved['status']):
        saved['status'] = list(dict.fromkeys(name for value in saved['status']
                                             for name in (group if str(value).casefold() == old.casefold() else [value])))
        task_repository.set_workspace_state(SAVED_FILTERS_STATE_KEY, json.dumps(saved, ensure_ascii=False, sort_keys=True))
    when = now_iso()
    with task_repository.connection() as connection:
        for row in connection.execute(f"SELECT call_key FROM {NQ_CALL_TRACKING_TABLE} WHERE status = ? COLLATE NOCASE AND status_mode = 'manual'",
                                      (old,)).fetchall():
            _record_history(connection, str(row['call_key']), 'status', old_name, new_name, 'system', when)
        connection.execute(f"UPDATE {NQ_CALL_TRACKING_TABLE} SET status = ? WHERE status = ? COLLATE NOCASE AND status_mode = 'manual'",
                           (new_name, old))
        connection.execute(f"DELETE FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = 'status' AND name = ? COLLATE NOCASE", (old,))
    task_repository.set_workspace_state(ANALYSIS_CENTER_V19_STATE_KEY, '1')
    recompute_statuses(task_repository, 'system')


def _rules_shape(rules: Any) -> list[tuple[str, list[tuple[str, str, list[str]]]]]:
    """The rules as comparable data: status, then each condition's field, operator and values, ignoring case."""
    if not isinstance(rules, (list, tuple)):
        return []
    return [(str(rule.get('status', '')).casefold(), [(str(condition.get('field', '')), str(condition.get('op', '')),
                                                       sorted(str(value).casefold() for value in condition.get('values') or []))
                                                      for condition in rule.get('conditions') or [] if isinstance(condition, dict)])
            for rule in rules if isinstance(rule, dict)]


def _upgrade_analysis_center_v20(task_repository: Any) -> None:
    """Once: No_Vendor_B and No_JoinID Missing of the Analysis Status become Invalidated (the history keeps the value of
    before, and the Status Rules, shared filters and reviewed equivalences follow), and Status Rules still equal to the
    defaults of before take the new defaults, numbered from the end of the pipeline (they give every call the same
    status). The statuses follow."""
    fields = list_fields(task_repository)
    analysis = next((field for field in fields if field['key'] == 'analysis_status' and field['type'] == 'list'), None)
    renames = {name.casefold(): 'Invalidated' for name in V20_INVALIDATED_ANALYSES}
    if analysis is not None:
        target = next((option['name'] for option in analysis['options'] if option['name'].casefold() == 'invalidated'), 'Invalidated')
        renames = {old: target for old in renames}
        before = {item['key']: dict(item, options=[dict(option) for option in item['options']]) for item in fields}
        when = now_iso()
        with task_repository.connection() as connection:
            for old in V20_INVALIDATED_ANALYSES:
                rows = connection.execute(f"SELECT call_key, value FROM {NQ_FIELD_VALUES_TABLE} WHERE field_key = 'analysis_status' "
                                          'AND value = ? COLLATE NOCASE', (old,)).fetchall()
                for row in rows:
                    _record_history(connection, str(row['call_key']), 'field:analysis_status', str(row['value']), target, 'system', when)
                connection.execute(f"UPDATE {NQ_FIELD_VALUES_TABLE} SET value = ? WHERE field_key = 'analysis_status' AND value = ? COLLATE NOCASE",
                                   (target, old))
        options = [option for option in analysis['options'] if option['name'].casefold() not in renames]
        if target.casefold() not in {option['name'].casefold() for option in options}:
            options.append({'name': target, 'color': '#7b8790'})
        if len(options) != len(analysis['options']) or options != analysis['options']:
            analysis['options'] = options
            _store_fields(task_repository, nq_catalog.normalize_fields(fields, before, CATALOG_CALL_FIELDS))
    try:
        rules = json.loads(task_repository.get_workspace_state(STATUS_RULES_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        rules = []
    former = [{'status': status, 'conditions': [{'field': field, 'op': op, 'values': list(values)} for field, op, values in conditions]}
              for status, conditions in V20_FORMER_RULES]
    if isinstance(rules, list) and rules:
        if _rules_shape(rules) == _rules_shape(former):
            rules = nq_catalog.default_status_rules()
        else:
            for rule in rules:
                for condition in (rule.get('conditions') or []) if isinstance(rule, dict) else []:
                    if isinstance(condition, dict) and condition.get('field') == 'analysis_status' and isinstance(condition.get('values'), list):
                        condition['values'] = list(dict.fromkeys(renames.get(str(value).casefold(), value) for value in condition['values']))
        task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
    try:
        saved = json.loads(task_repository.get_workspace_state(SAVED_FILTERS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        saved = {}
    chosen = (saved.get('fields') or {}).get('analysis_status') if isinstance(saved, dict) and isinstance(saved.get('fields'), dict) else None
    if isinstance(chosen, list) and any(str(value).casefold() in renames for value in chosen):
        saved['fields']['analysis_status'] = list(dict.fromkeys(renames.get(str(value).casefold(), value) for value in chosen))
        task_repository.set_workspace_state(SAVED_FILTERS_STATE_KEY, json.dumps(saved, ensure_ascii=False, sort_keys=True))
    equivalences = workspace_equivalences(task_repository)
    if 'field:analysis_status' in equivalences:
        for item in equivalences['field:analysis_status'].values():
            item['to'] = renames.get(item['to'].casefold(), item['to'])
        _save_equivalences(task_repository, equivalences)
    task_repository.set_workspace_state(ANALYSIS_CENTER_V20_STATE_KEY, '1')
    recompute_statuses(task_repository, 'system')


def _add_default_fields(fields: list[dict[str, Any]], keys: set[str], same_source: bool = False) -> bool:
    """Insert the default fields of ``keys`` a catalog lacks (by key or name), each after the field (of its source with
    ``same_source``) it follows by default or at the end of its section; whether any was added."""
    default_fields = nq_catalog.default_fields()
    labels = {field['label'].casefold() for field in fields}
    added = False
    for index, default in enumerate(default_fields):
        if default['key'] not in keys or default['key'] in {field['key'] for field in fields} \
                or default['label'].casefold() in labels:
            continue
        previous = [field['key'] for field in default_fields[:index] if not same_source or field['source'] == default['source']]
        place = max((position for position, field in enumerate(fields) if field['key'] in previous
                     and field['section'] == default['section']), default=None)
        if place is None:
            place = max((position for position, field in enumerate(fields) if field['section'] == default['section']), default=len(fields) - 1)
        fields.insert(place + 1, default)
        added = True
    return added


# ---------------------------------------------------------------------------
# Indexing the NQ calls of every CDR
# ---------------------------------------------------------------------------
def _resolve_columns(columns: list[str], candidates: tuple[str, ...]) -> list[str]:
    """Every CDR column matching the candidates, in order of preference."""
    exact = set(columns)
    identities: dict[str, str] = {}
    for column in columns:
        identities.setdefault(column_identity(column), column)
    resolved = [candidate if candidate in exact else identities.get(column_identity(candidate)) for candidate in candidates]
    return list(dict.fromkeys(column for column in resolved if column))


def _resolve_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    return next(iter(_resolve_columns(columns, candidates)), None)


def call_key_for(service: str, values: dict[str, Any], identifier: str = '', subscriber: str = '', join_id: str = '') -> str:
    """A stable identity for a call: the same call keeps it across uploads, reprocessing and CDRs.

    The NetCheck JOIN_ID identifies each voice call and data test in the Daily and the Final
    CDRs alike; without it, the call is its service, Operator, Campaign and test or session
    identifier (or its subscriber, test name and start and end times).
    """
    if join_id:
        parts: tuple[str, ...] = (service, 'join', join_id.casefold())
    else:
        base = (service, _text(values.get('operator')).casefold(), _text(values.get('campaign')).casefold())
        if identifier:
            parts = (*base, 'id', identifier)
        else:
            parts = (*base, subscriber.casefold(), _text(values.get('test_name')).casefold(),
                     _text(values.get('start_time')), _text(values.get('end_time')))
    return hashlib.sha1('\x1f'.join(parts).encode('utf-8')).hexdigest()[:24]


def sample_key_for(call_key: str, sample: str) -> str:
    """The identity of one Speech sample inside its call."""
    return hashlib.sha1('\x1f'.join((call_key, 'sample', sample)).encode('utf-8')).hexdigest()[:24]


TABLE_COLUMNS_STATE_KEY = 'nq_calls_table_columns'
# Optional columns of the Calls table, with their labels.
OPTIONAL_COLUMNS = {
    'join_id': 'JOIN_ID', 'nr_mode': 'NR Mode', 'cell_id': 'Cell ID',
    'direction': 'Direction', 'session_type': 'Session Type (CDR)', 'end_time': 'End Time', 'cdr': 'CDR',
}
MAX_CDR_COLUMNS = 12
# CDR columns exported to Excel besides those of the table.
MAX_EXPORT_CDR_COLUMNS = 100
# The optional columns filtered by their own values; CDR uses the CDRs filter.
COLUMN_FILTER_SQL = {
    'join_id': 'join_id', 'nr_mode': 'nr_mode', 'cell_id': 'cell_id', 'direction': 'direction', 'session_type': 'session_type',
    'end_time': 'end_time',
}
MAX_COLUMN_FILTER_VALUES = 5000


def column_filter_sql(key: str) -> str | None:
    """The SQL value of a filterable table column: an optional column, or a CDR column (``cdr:<name>``)."""
    if key in COLUMN_FILTER_SQL:
        return f"COALESCE(CAST({COLUMN_FILTER_SQL[key]} AS TEXT), '')"
    if key.startswith('cdr:') and key[4:].strip():
        name = key[4:].replace('"', '').replace("'", '')
        return f"COALESCE(CAST(json_extract(extra_json, '$.\"{name}\"') AS TEXT), '')"
    return None


def table_columns(repository: Any) -> dict[str, list[str]]:
    """The Additional Columns of the workspace: built-in and CDR columns of the table, and CDR columns only exported to Excel."""
    try:
        stored = json.loads(repository.get_workspace_state(TABLE_COLUMNS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        stored = {}
    stored = stored if isinstance(stored, dict) else {}
    builtin = [column for column in _strings(stored.get('builtin')) if column in OPTIONAL_COLUMNS]
    cdr = [column for column in _strings(stored.get('cdr')) if column.strip()][:MAX_CDR_COLUMNS]
    export_cdr = [column for column in _strings(stored.get('export_cdr')) if column.strip() and column not in cdr][:MAX_EXPORT_CDR_COLUMNS]
    return {'builtin': builtin, 'cdr': cdr, 'export_cdr': export_cdr}


def indexed_cdr_columns(repository: Any) -> list[str]:
    """The CDR columns kept with every call: those of the table, those only exported to Excel, those of the personal
    table layouts and those of the catalog."""
    columns = table_columns(repository)
    try:
        catalog = [field['source_ref'][7:] for field in list_fields(repository)
                   if field['source'] == 'cdr' and field['source_ref'].startswith('column:')]
    except Exception:  # noqa: BLE001 - the catalog table may not exist yet while the module tables are created.
        catalog = []
    return list(dict.fromkeys([*columns['cdr'], *columns['export_cdr'], *_user_cdr_columns(repository), *catalog]))


def save_table_columns(repository: Any, builtin: Any, cdr: Any, username: str, export_cdr: Any = (), *,
                       imported: bool = False, defaults: bool = False) -> dict[str, list[str]]:
    unknown = [column for column in _strings(builtin) if column not in OPTIONAL_COLUMNS]
    if unknown:
        raise ValueError(f'Unknown columns: {", ".join(unknown)}.')
    cdr_columns = list(dict.fromkeys(column.strip()[:120] for column in _strings(cdr) if column.strip()))
    if len(cdr_columns) > MAX_CDR_COLUMNS:
        raise ValueError(f'Choose at most {MAX_CDR_COLUMNS} CDR columns for the table.')
    # The table's CDR columns are always exported; these are exported to Excel only.
    export_columns = [column for column in dict.fromkeys(column.strip()[:120] for column in _strings(export_cdr) if column.strip())
                      if column not in cdr_columns]
    if len(export_columns) > MAX_EXPORT_CDR_COLUMNS:
        raise ValueError(f'Choose at most {MAX_EXPORT_CDR_COLUMNS} CDR columns for Excel only.')
    repository.set_workspace_state(TABLE_COLUMNS_STATE_KEY, json.dumps(
        {'builtin': _strings(builtin), 'cdr': cdr_columns, 'export_cdr': export_columns}))
    # The calls are indexed again for the new columns: those no personal layout shows any more go too.
    _remember_user_cdr_columns(repository, prune=True)
    if hasattr(repository, 'try_add_log'):
        repository.try_add_log(username, 'nq_table_columns', 'Non-Qualified Calls table columns taken from an imported '
                               'configuration.' if imported else 'Non-Qualified Calls table columns restored to the default '
                               'columns.' if defaults else 'Non-Qualified Calls table columns updated.')
    return table_columns(repository)


# ---------------------------------------------------------------------------
# Table layouts: the columns of the Calls table and of its Excel export, and their order, of the workspace (what
# every user sees) or of each user (only for them)
# ---------------------------------------------------------------------------
COLUMN_ORDER_STATE_KEY = 'nq_calls_column_order'
# The CDR columns the personal layouts showed: kept indexed when a user removes one, so the CDRs are not indexed again;
# the next change of the workspace columns forgets those no personal layout shows.
USER_CDR_COLUMNS_STATE_KEY = 'nq_calls_user_cdr_columns'
LAYOUT_VIEWS = ('mine', 'workspace')
MAX_ORDER_COLUMNS = 400


def _column_order(value: Any) -> list[str]:
    return [item[:160] for item in _strings(value) if item.strip()][:MAX_ORDER_COLUMNS]


def _user_cdr_columns(repository: Any) -> list[str]:
    try:
        return _strings(json.loads(repository.get_workspace_state(USER_CDR_COLUMNS_STATE_KEY) or '[]'))
    except (TypeError, ValueError):
        return []


def _stored_user_layouts(repository: Any) -> list[Any]:
    with repository.connection() as connection:
        return connection.execute(
            f'SELECT username, layout_json, view, updated_at FROM {NQ_USER_LAYOUTS_TABLE} ORDER BY username COLLATE NOCASE').fetchall()


def _remember_user_cdr_columns(repository: Any, *, prune: bool = False) -> None:
    """Keep indexed the CDR columns of the personal layouts (``prune``: only those they show now)."""
    try:
        rows = _stored_user_layouts(repository)
    except sqlite3.OperationalError:
        return
    current: list[str] = []
    for row in rows:
        try:
            layout = json.loads(row['layout_json'] or '{}')
        except (TypeError, ValueError):
            continue
        if isinstance(layout, dict):
            current += [name.strip()[:120] for name in [*_strings(layout.get('cdr')), *_strings(layout.get('export_cdr'))] if name.strip()]
    kept = list(dict.fromkeys(current if prune else [*_user_cdr_columns(repository), *current]))
    if kept != _user_cdr_columns(repository):
        repository.set_workspace_state(USER_CDR_COLUMNS_STATE_KEY, json.dumps(kept, ensure_ascii=False))


def workspace_layout(task_repository: Any, fields: list[dict[str, Any]] | None = None) -> dict[str, list[str]]:
    """The layout of the workspace: its Additional Columns, the catalog fields that are table columns and those exported
    to Excel (Table column and Excel of Fields & Sections), and the column order."""
    fields = list_fields(task_repository) if fields is None else fields
    try:
        order = json.loads(task_repository.get_workspace_state(COLUMN_ORDER_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        order = []
    return {**table_columns(task_repository),
            'fields': [field['key'] for field in fields if field['in_table'] and field['source'] != 'tracking'],
            'excel_fields': [field['key'] for field in fields if field.get('in_export', True)],
            'known_fields': [field['key'] for field in fields], 'order': _column_order(order)}


def _normalize_layout(layout: Any, fields: list[dict[str, Any]], *, strict: bool = True) -> dict[str, list[str]]:
    """A valid layout; ``strict`` refuses too many CDR columns instead of keeping the first ones."""
    layout = layout if isinstance(layout, dict) else {}
    keys = [field['key'] for field in fields]
    columns = [key for key in keys if next(field for field in fields if field['key'] == key)['source'] != 'tracking']
    cdr = list(dict.fromkeys(name.strip()[:120] for name in _strings(layout.get('cdr')) if name.strip()))
    export = [name for name in dict.fromkeys(name.strip()[:120] for name in _strings(layout.get('export_cdr')) if name.strip())
              if name not in cdr]
    if strict and len(cdr) > MAX_CDR_COLUMNS:
        raise ValueError(f'Choose at most {MAX_CDR_COLUMNS} CDR columns for the table.')
    if strict and len(export) > MAX_EXPORT_CDR_COLUMNS:
        raise ValueError(f'Choose at most {MAX_EXPORT_CDR_COLUMNS} CDR columns for Excel only.')
    shown, exported = set(_strings(layout.get('fields'))), set(_strings(layout.get('excel_fields')))
    known = set(_strings(layout.get('known_fields'))) if 'known_fields' in layout else set(keys)
    return {'builtin': [column for column in _strings(layout.get('builtin')) if column in OPTIONAL_COLUMNS],
            'cdr': cdr[:MAX_CDR_COLUMNS], 'export_cdr': export[:MAX_EXPORT_CDR_COLUMNS],
            'fields': [key for key in columns if key in shown], 'excel_fields': [key for key in keys if key in exported],
            'known_fields': [key for key in keys if key in known], 'order': _column_order(layout.get('order'))}


def _resolved_layout(layout: dict[str, list[str]], workspace: dict[str, list[str]], fields: list[dict[str, Any]]) -> dict[str, list[str]]:
    """A personal layout as it shows: the fields added to the catalog after it was saved follow the workspace."""
    known = set(layout['known_fields'])
    pick = lambda key, mine, theirs: key in mine if key in known else key in theirs  # noqa: E731
    shown, exported = set(layout['fields']), set(layout['excel_fields'])
    return {**layout,
            'fields': [field['key'] for field in fields if field['source'] != 'tracking'
                       and pick(field['key'], shown, set(workspace['fields']))],
            'excel_fields': [field['key'] for field in fields if pick(field['key'], exported, set(workspace['excel_fields']))]}


def table_layouts(task_repository: Any, username: str) -> dict[str, Any]:
    """The layout of the workspace, that of the user (None while they have none), which one they see (``view``) and the
    layout they see (``effective``)."""
    fields = list_fields(task_repository)
    workspace = workspace_layout(task_repository, fields)
    with task_repository.connection() as connection:
        row = connection.execute(f'SELECT layout_json, view FROM {NQ_USER_LAYOUTS_TABLE} WHERE username = ?', (username,)).fetchone()
    mine = None
    if row is not None and row['layout_json']:
        try:
            mine = _resolved_layout(_normalize_layout(json.loads(row['layout_json']), fields, strict=False), workspace, fields)
        except (TypeError, ValueError):
            mine = None
    view = 'mine' if mine is not None and row['view'] == 'mine' else 'workspace'
    return {'workspace': workspace, 'mine': mine, 'view': view, 'effective': mine if view == 'mine' else workspace}


def _layout_summary(layout: dict[str, list[str]]) -> str:
    return (f"{len(layout['builtin'])} call columns, {len(layout['cdr'])} CDR columns in the table and {len(layout['export_cdr'])} "
            f"in Excel only, {len(layout['fields'])} Analysis Center fields in the table and {len(layout['excel_fields'])} in Excel, "
            f"{'a column order of its own' if layout['order'] else 'the default column order'}")


def _store_user_layout(task_repository: Any, username: str, layout: dict[str, list[str]] | None, view: str) -> None:
    with task_repository.connection() as connection:
        connection.execute(
            f'INSERT INTO {NQ_USER_LAYOUTS_TABLE} (username, layout_json, view, updated_at) VALUES (?, ?, ?, ?) '
            'ON CONFLICT(username) DO UPDATE SET layout_json = excluded.layout_json, view = excluded.view, updated_at = excluded.updated_at',
            (username, json.dumps(layout, ensure_ascii=False) if layout is not None else '', view, now_iso()))


LAYOUT_REASONS = {
    'changed': 'saved', 'defaults': 'put back to the default columns', 'order': 'saved with a new column order',
    'default_order': 'put back to the default column order', 'copied': 'copied from the workspace layout',
}


def save_user_layout(task_repository: Any, username: str, changes: dict[str, Any], *, reason: str = 'changed') -> dict[str, Any]:
    """Save the layout of a user and show it to them: the parts not given keep those of their layout (or, without one,
    those of the workspace)."""
    current = table_layouts(task_repository, username)
    base = current['mine'] or current['workspace']
    fields = list_fields(task_repository)
    given = {key: value for key, value in (changes or {}).items() if value is not None}
    if 'fields' in given or 'excel_fields' in given:
        given.setdefault('known_fields', [field['key'] for field in fields])
    layout = _normalize_layout({**base, **given}, fields)
    _store_user_layout(task_repository, username, layout, 'mine')
    _remember_user_cdr_columns(task_repository)
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_table_layout', f'Non-Qualified Calls table layout of {username} '
                                    f'{LAYOUT_REASONS.get(reason, "saved")}: {_layout_summary(layout)}.')
    return table_layouts(task_repository, username)


def set_layout_view(task_repository: Any, username: str, view: str) -> dict[str, Any]:
    """Show the user their own layout (a copy of the workspace one the first time) or that of the workspace."""
    if view not in LAYOUT_VIEWS:
        raise ValueError('Choose Mine or Workspace.')
    current = table_layouts(task_repository, username)
    if view == 'mine' and current['mine'] is None:
        return save_user_layout(task_repository, username, {}, reason='copied')
    _store_user_layout(task_repository, username, current['mine'], view)
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_table_layout_view', f'Non-Qualified Calls table layout of {username} switched '
                                    f'to {"their own layout" if view == "mine" else "the workspace layout"}.')
    return table_layouts(task_repository, username)


def copy_workspace_layout(task_repository: Any, username: str) -> dict[str, Any]:
    """Start the layout of the user again from that of the workspace."""
    return save_user_layout(task_repository, username, dict(table_layouts(task_repository, username)['workspace']), reason='copied')


def publish_user_layout(task_repository: Any, username: str) -> dict[str, Any]:
    """Make the layout of the user that of the workspace (Save for the workspace): its columns, the Table column and Excel
    of the catalog fields and the column order."""
    layout = table_layouts(task_repository, username)['mine']
    if layout is None:
        raise ValueError('Arrange your own layout first: the workspace takes it.')
    task_repository.set_workspace_state(TABLE_COLUMNS_STATE_KEY, json.dumps(
        {'builtin': layout['builtin'], 'cdr': layout['cdr'], 'export_cdr': layout['export_cdr']}, ensure_ascii=False))
    task_repository.set_workspace_state(COLUMN_ORDER_STATE_KEY, json.dumps(layout['order'], ensure_ascii=False))
    _store_layout_flags(task_repository, layout['fields'], layout['excel_fields'])
    _remember_user_cdr_columns(task_repository, prune=True)
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_table_layout_publish', f'Non-Qualified Calls table layout of {username} saved '
                                    f'for the workspace: {_layout_summary(layout)}.')
    return table_layouts(task_repository, username)


def _store_layout_flags(task_repository: Any, shown: list[str], exported: list[str]) -> None:
    """The Table column and Excel of the catalog fields (the follow-up fields always have their column)."""
    fields = list_fields(task_repository)
    for field in fields:
        if field['source'] != 'tracking':
            field['in_table'] = field['key'] in shown
        field['in_export'] = field['key'] in exported
    _store_fields(task_repository, fields)


def user_layouts(task_repository: Any) -> list[dict[str, Any]]:
    """Every personal layout of the workspace, for its exports."""
    layouts = []
    for row in _stored_user_layouts(task_repository):
        try:
            layout = json.loads(row['layout_json']) if row['layout_json'] else None
        except (TypeError, ValueError):
            layout = None
        layouts.append({'username': str(row['username']), 'layout': layout, 'view': str(row['view']),
                        'updated_at': str(row['updated_at'])})
    return layouts


def available_cdr_columns(task_repository: Any) -> list[str]:
    """Every column of the indexed CDRs, for the CDR columns of the Calls table."""
    ids = [int(row['id']) for row in _cdr_datasets(task_repository)]
    if not ids:
        return []
    names: dict[str, str] = {}
    with task_repository.connection() as connection:
        rows = connection.execute(
            f"SELECT dataset_id, column_name FROM dataset_source_columns WHERE dataset_id IN ({', '.join('?' for _ in ids)})", ids,
        ).fetchall()
        described = {int(row['dataset_id']) for row in rows}
        columns = [str(row['column_name']) for row in rows]
        # CDRs without their source headings list the columns of their table.
        for dataset_id in ids:
            if dataset_id not in described:
                columns.extend(str(row[1]) for row in connection.execute(f'PRAGMA table_info({_quote(f"dataset_rows_{dataset_id}")})'))
    for column in columns:
        names.setdefault(column_identity(column), column)
    return sorted(names.values(), key=str.casefold)


def _dataset_revision(row: Any, signature: str = '') -> str:
    stage = dataset_cdr_stage(row['dataset_kind'], row['cdr_stage'] if 'cdr_stage' in row.keys() else None, row['file_name'])
    return ('|'.join(str(row[key] or '') for key in ('updated_at', 'processed_at', 'row_count', 'normalization_version'))
            + f'|{stage}|v{INDEX_VERSION}|{signature}')


def _columns_signature(cdr_columns: list[str]) -> str:
    return hashlib.sha1(json.dumps(sorted(column_identity(column) for column in cdr_columns)).encode('utf-8')).hexdigest()[:12] \
        if cdr_columns else ''


def _cdr_datasets(task_repository: Any) -> list[Any]:
    return [
        row for row in task_repository.list_datasets()
        if str(row['dataset_kind'] or '') in SERVICES and str(row['status'] or '') == 'ready'
    ]


_CALL_COLUMNS = ('dataset_id', 'source_row_id', 'call_key', 'service', 'nr_mode', *CALL_FIELDS,
                 'join_id', 'sample_key', 'sample_id', 'extra_json', 'rca_inputs_json')
# The identity of a call needs only these fields.
_KEY_FIELDS = ('operator', 'campaign', 'test_name', 'start_time', 'end_time')


def _time_text(value: Any) -> str:
    return _text(value).replace('T', ' ')[:19]


def source_labels(task_repository: Any) -> dict[str, str]:
    """The names of the root cause sources, the RCA of the CDR named after the provider of the workspace's CDRs."""
    return {**nq_rca.SOURCE_LABELS, 'netcheck': provider_texts(task_repository)['rca']}


def provider_field_labels(fields: list[dict[str, Any]], task_repository: Any) -> list[dict[str, Any]]:
    """The fields of the catalog as the page and the exports show them: the NetCheck RCA of their default names and
    descriptions is the RCA of the provider of the workspace's CDRs (the Umlaut RCA in an Umlaut workspace)."""
    provider = provider_texts(task_repository)
    if provider['name'] == 'NetCheck':
        return fields
    renamed = []
    for field in fields:
        texts = {key: str(field[key]).replace('NetCheck RCA', provider['rca']).replace('NetCheck', provider['name'])
                 for key in ('label', 'description') if isinstance(field.get(key), str) and 'NetCheck' in field[key]}
        renamed.append({**field, **texts} if texts else field)
    return renamed


def provider_texts(task_repository: Any) -> dict[str, Any]:
    """How Non-Qualified Calls names the provider of the workspace's CDRs: its name, its RCA source (the NetCheck RCA
    in a NetCheck workspace), which calls are NQ and whether its CDRs bring an RCA of their own and a JOIN_ID (the
    calls are found by it)."""
    from src.modules.cdr_types import CDR_TYPES, workspace_cdr_type

    profile = workspace_field_profile(task_repository)
    name = CDR_TYPES[workspace_cdr_type(task_repository)]['provider']
    hierarchy = any(profile.nq_field_sources.get(field) for field in ('failure_classification', 'failure_category', 'failure_subcategory'))
    return {'name': name, 'rca': f'{name} RCA', 'definition': profile.nq_definition, 'rca_hierarchy': hierarchy,
            'join_id': bool(profile.nq_join_sources)}


def _sample_radio(connection: Any, datasets: Any, profile: CdrFieldProfile) -> dict[tuple[str, str, str], dict[str, float]]:
    """The mean radio of the Speech samples of every call (its Operator, Campaign and identifier), for the Voice calls
    whose CDR has the radio of their setup only (see CdrFieldProfile.nq_call_radio_from_samples)."""
    radio: dict[tuple[str, str, str], dict[str, float]] = {}
    for dataset in datasets:
        if not profile.nq_call_radio_from_samples or str(dataset['dataset_kind']) != 'speech':
            continue
        table = f'dataset_rows_{int(dataset["id"])}'
        columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info({_quote(table)})').fetchall()]
        keys = [_resolve_column(columns, sources) for sources in (
            profile.nq_field_sources['operator'], profile.nq_field_sources['campaign'], profile.nq_identifier_sources['speech'])]
        inputs = {name: column for name in profile.nq_call_radio_from_samples
                  if (column := _resolve_column(columns, profile.nq_rca_sources.get(name, ())))}
        if not keys[2] or not inputs:
            continue
        key_sql = [f'{_quote(column)}' if column else "''" for column in keys]
        means = ', '.join(f"AVG(CASE WHEN TRIM(CAST({_quote(column)} AS TEXT)) <> '' THEN CAST({_quote(column)} AS REAL) END)"
                          for column in inputs.values())
        for row in connection.execute(f"SELECT {', '.join(key_sql)}, {means} FROM {_quote(table)} GROUP BY {', '.join(key_sql)}"):
            key = (_text(row[0]).casefold(), _text(row[1]).casefold(), _text(row[2]))
            values = {name: round(float(value), 4) for name, value in zip(inputs, tuple(row)[3:], strict=True) if value is not None}
            if key[2] and values:
                radio.setdefault(key, values)
    return radio


def _dataset_calls(connection: Any, dataset: Any, cdr_columns: tuple[str, ...] = (),
                   profile: CdrFieldProfile = NETCHECK_PROFILE,
                   sample_radio: dict[tuple[str, str, str], dict[str, float]] | None = None) -> dict[str, Any]:
    """The NQ rows of one CDR, ready to insert into ``nq_calls``, and every call of it for ``nq_call_population``.

    Speech CDRs list one row per sample: their samples share the call key of their call (the
    JOIN_ID or the A-side session) and each one has its own ``sample_key``. The columns are those of
    the field profile of the CDR type, and a call is Non-Qualified when its qualification column does
    not hold the profile's qualified value. Each row keeps the values the DT Analyzer RCA reads
    (``rca_inputs_json``, see nq_dta_rca), the numbers in its units; a Voice call takes the mean radio
    of its Speech samples from ``sample_radio`` (see _sample_radio).
    """
    dataset_id = int(dataset['id'])
    service = str(dataset['dataset_kind'])
    table = f'dataset_rows_{dataset_id}'
    empty = {'calls': [], 'population': [], 'data_date': ''}
    columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info({_quote(table)})').fetchall()]
    if not columns:
        return empty
    resolved = {field: _resolve_columns(columns, candidates) for field, candidates in profile.nq_field_sources.items()}
    qualification = _resolve_columns(columns, profile.nq_qualification_sources)
    if not qualification:
        return empty
    result_column = qualification[0]
    qualified = profile.nq_qualified_value
    identifiers = profile.nq_identifier_sources
    join_column = _resolve_column(columns, profile.nq_join_sources)
    identifier_column = _resolve_column(columns, identifiers.get(service, identifiers['data']))
    subscriber_column = _resolve_column(columns, profile.nq_subscriber_sources)
    sample_column = _resolve_column(columns, profile.nq_sample_sources) if service == 'speech' else None
    extra = {name: column for name in cdr_columns if (column := _resolve_column(columns, (name,)))}
    rca_inputs = {name: resolved_columns for name in nq_dta_rca.CDR_INPUTS
                  if (resolved_columns := _resolve_columns(columns, profile.nq_rca_sources.get(name, ())))}
    # The cells of the call with their PCIs and where it ended, read as its Map reads them (nq_call_map).
    ends = profile.end_coordinates.get(service, ())
    trace_sources = {'cell_trace': profile.rf_field_aliases['cell_trace'].get(service, ()), 'cell_pcis': profile.pci_columns.get(service, ()),
                     'end_latitude': tuple(latitude for _longitude, latitude in ends),
                     'end_longitude': tuple(longitude for longitude, _latitude in ends)}
    rca_inputs.update({name: resolved_columns for name, candidates in trace_sources.items()
                       if (resolved_columns := _resolve_columns(columns, candidates))})
    rca_numbers = {name for name in rca_inputs
                   if nq_dta_rca.INPUTS.get(name, ('', 'text'))[1] == 'number' or name in nq_dta_rca.NUMBER_SOURCES}
    nr_mode = _text(dataset['nr_mode'])

    def identity(row: Any, aliases: dict[str, str], values: dict[str, Any]) -> tuple[str, str]:
        join_id = _text(row[aliases[join_column]]) if join_column else ''
        identifier = _text(row[aliases[identifier_column]]) if identifier_column else ''
        subscriber = _text(row[aliases[subscriber_column]]) if subscriber_column else ''
        return call_key_for(service, values, identifier, subscriber, join_id), join_id

    # Every call of the CDR, with whether it is Non-Qualified: the population of the NQ rates.
    key_selected = list(dict.fromkeys(column for column in (
        result_column, join_column, identifier_column, subscriber_column,
        *(column for field in (*_KEY_FIELDS, *POPULATION_FIELDS) for column in resolved[field])) if column))
    key_aliases = {column: f'c{index}' for index, column in enumerate(key_selected)}
    population: dict[str, list[Any]] = {}
    data_date = ''
    for row in connection.execute(
        f"SELECT {', '.join(f'{_quote(column)} AS {key_aliases[column]}' for column in key_selected)} FROM {_quote(table)}"
    ):
        result = _text(row[key_aliases[result_column]]).casefold()
        if not result:
            continue
        values = {field: next((text for column in resolved[field] if (text := _text(row[key_aliases[column]]))), '')
                  for field in (*_KEY_FIELDS, *POPULATION_FIELDS)}
        key, _join_id = identity(row, key_aliases, values)
        is_nq = int(result != qualified)
        entry = population.get(key)
        if entry is None:
            population[key] = [dataset_id, key, service, values['campaign'], values['operator'], nr_mode, is_nq,
                               *(values[field] for field in POPULATION_FIELDS)]
        elif is_nq:
            entry[6] = 1
        moment = _time_text(values['start_time'])
        if moment > data_date:
            data_date = moment

    selected = list(dict.fromkeys(
        column for column in (*(item for items in resolved.values() for item in items), join_column, identifier_column,
                              subscriber_column, sample_column, *extra.values(),
                              *(item for items in rca_inputs.values() for item in items))
        if column
    ))
    aliases = {column: f'c{index}' for index, column in enumerate(selected)}
    normalized = f'LOWER(TRIM(CAST({_quote(result_column)} AS TEXT)))'
    # Range conditions use the CDR's normalized status index when it exists.
    query = (
        f"SELECT rowid AS source_row_id, {', '.join(f'{_quote(column)} AS {aliases[column]}' for column in selected)} "
        f"FROM {_quote(table)} WHERE {normalized} > ? OR ({normalized} < ? AND {normalized} > '')"
    )
    calls = []
    for row in connection.execute(query, (qualified, qualified)).fetchall():
        values: dict[str, Any] = {}
        for field, candidates in resolved.items():
            # The first candidate column with a value wins.
            if field in NUMERIC_FIELDS:
                values[field] = next((number for column in candidates if (number := _number(row[aliases[column]])) is not None), None)
            else:
                values[field] = next((text for column in candidates if (text := _text(row[aliases[column]]))), '')
        key, join_id = identity(row, aliases, values)
        sample_id = sample_key = ''
        if service == 'speech':
            sample_id = (_text(row[aliases[sample_column]]) if sample_column else '') or values['start_time'] or str(row['source_row_id'])
            sample_key = sample_key_for(key, sample_id)
        extras = {name: _text(row[aliases[column]]) for name, column in extra.items()}
        inputs: dict[str, Any] = {}
        for name, candidates in rca_inputs.items():
            if name in rca_numbers:
                number = next((number for column in candidates if (number := _number(row[aliases[column]])) is not None), None)
                if number is not None:
                    inputs[name] = round(number * profile.nq_rca_scales.get(name, 1.0), 4)
            elif text := next((text for column in candidates if (text := _text(row[aliases[column]]))), ''):
                inputs[name] = text[:2000 if name in nq_dta_rca.TRACE_SOURCES else 300]
        if sample_radio and service == 'voice' and identifier_column:
            inputs.update(sample_radio.get((values['operator'].casefold(), values['campaign'].casefold(),
                                            _text(row[aliases[identifier_column]])), {}))
        calls.append((dataset_id, int(row['source_row_id']), key, service, nr_mode, *(values[field] for field in CALL_FIELDS),
                      join_id, sample_key, sample_id, json.dumps(extras, ensure_ascii=False), json.dumps(inputs, ensure_ascii=False)))
    return {'calls': calls, 'population': list(population.values()), 'data_date': data_date}


def _move_follow_up(connection: Any, old_rows: list[Any], calls: list[tuple[Any, ...]]) -> int:
    """Move the follow-up of the previous call keys to the new ones (once, when the call key changes).

    Each previous key goes to the call (or Speech sample) of the row it was shown with. When two
    previous keys reach the same call, the newest follow-up wins and comments, history and analysis
    fields are kept from both.
    """
    position = {name: index for index, name in enumerate(_CALL_COLUMNS)}
    target = {(int(call[position['dataset_id']]), int(call[position['source_row_id']])):
              str(call[position['sample_key']] or call[position['call_key']]) for call in calls}
    shown: dict[str, tuple[int, tuple[int, int]]] = {}
    for row in old_rows:
        old_key, rowid = str(row['call_key']), int(row['rowid'])
        if old_key not in shown or rowid > shown[old_key][0]:
            shown[old_key] = (rowid, (int(row['dataset_id']), int(row['source_row_id'])))
    mapping = {old: target[place] for old, (_rowid, place) in shown.items() if place in target and target[place] != old}
    mapping = {old: new for old, new in mapping.items() if new not in mapping}
    for old, new in mapping.items():
        previous = connection.execute(f'SELECT * FROM {NQ_CALL_TRACKING_TABLE} WHERE call_key = ?', (old,)).fetchone()
        if previous is not None:
            current = connection.execute(f'SELECT updated_at FROM {NQ_CALL_TRACKING_TABLE} WHERE call_key = ?', (new,)).fetchone()
            if current is None:
                connection.execute(f'UPDATE {NQ_CALL_TRACKING_TABLE} SET call_key = ? WHERE call_key = ?', (new, old))
            elif str(previous['updated_at']) > str(current['updated_at']):
                connection.execute(f'DELETE FROM {NQ_CALL_TRACKING_TABLE} WHERE call_key = ?', (new,))
                connection.execute(f'UPDATE {NQ_CALL_TRACKING_TABLE} SET call_key = ? WHERE call_key = ?', (new, old))
            else:
                connection.execute(f'DELETE FROM {NQ_CALL_TRACKING_TABLE} WHERE call_key = ?', (old,))
        for table in (NQ_CALL_COMMENTS_TABLE, NQ_CALL_HISTORY_TABLE):
            connection.execute(f'UPDATE {table} SET call_key = ? WHERE call_key = ?', (new, old))
        connection.execute(
            f'INSERT OR IGNORE INTO {NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) '
            f'SELECT ?, field_key, value, updated_by, updated_at FROM {NQ_FIELD_VALUES_TABLE} WHERE call_key = ?', (new, old))
        connection.execute(f'DELETE FROM {NQ_FIELD_VALUES_TABLE} WHERE call_key = ?', (old,))
    return len(mapping)


def _rebuild_versions(connection: Any, affected: set[str]) -> None:
    """Which CDR holds the latest version of each call and how the versions differ.

    The latest version is the one of a Final CDR before the Daily ones, then of the CDR with the
    newest data. Only the calls of the changed CDRs are recalculated, except whether a Final CDR
    covers the campaign of the calls that are only in Weekly or Daily CDRs.
    """
    connection.execute('CREATE TEMP TABLE IF NOT EXISTS nq_affected_keys (call_key TEXT PRIMARY KEY)')
    connection.execute('DELETE FROM nq_affected_keys')
    keys = list(affected)
    for start in range(0, len(keys), 5000):
        connection.executemany('INSERT OR IGNORE INTO nq_affected_keys (call_key) VALUES (?)',
                               [(key,) for key in keys[start:start + 5000]])
    connection.execute(
        f'UPDATE {NQ_CALL_POPULATION_TABLE} SET is_latest = 0 '
        f'WHERE is_latest = 1 AND call_key IN (SELECT call_key FROM nq_affected_keys)')
    connection.execute(f"""
        UPDATE {NQ_CALL_POPULATION_TABLE} SET is_latest = 1 WHERE rowid IN (
            SELECT rid FROM (
                SELECT p.rowid AS rid, ROW_NUMBER() OVER (
                    PARTITION BY p.call_key ORDER BY s.combined_rank DESC, s.stage_rank DESC, s.data_date DESC, p.dataset_id DESC) AS rn
                FROM {NQ_CALL_POPULATION_TABLE} p
                JOIN {NQ_CALL_SOURCES_TABLE} s ON s.dataset_id = p.dataset_id
                WHERE p.call_key IN (SELECT call_key FROM nq_affected_keys)
            ) WHERE rn = 1)
    """)
    connection.execute(f'DELETE FROM {NQ_CALL_VERSIONS_TABLE} WHERE call_key IN (SELECT call_key FROM nq_affected_keys)')
    connection.execute(f"""
        INSERT INTO {NQ_CALL_VERSIONS_TABLE} (call_key, latest_dataset_id, latest_is_nq, in_final, changed, cdr_count)
        SELECT k.call_key, l.dataset_id, l.is_nq,
               EXISTS (SELECT 1 FROM {NQ_CALL_POPULATION_TABLE} f JOIN {NQ_CALL_SOURCES_TABLE} s ON s.dataset_id = f.dataset_id
                       WHERE f.call_key = k.call_key AND s.stage_rank = 1),
               (SELECT COUNT(DISTINCT lower(c.result || '|' || replace(replace(c.failure_classification, '_', ''), ' ', '')
                                            || '|' || replace(replace(c.failure_category, '_', ''), ' ', '')))
                FROM {NQ_CALLS_TABLE} c WHERE c.call_key = k.call_key) > 1,
               (SELECT COUNT(*) FROM {NQ_CALL_POPULATION_TABLE} n WHERE n.call_key = k.call_key)
        FROM (SELECT DISTINCT call_key FROM {NQ_CALLS_TABLE} WHERE call_key IN (SELECT call_key FROM nq_affected_keys)) k
        JOIN {NQ_CALL_POPULATION_TABLE} l ON l.call_key = k.call_key AND l.is_latest = 1
    """)
    # A Final CDR covers the campaigns (of its service and NR Mode) it contains.
    connection.execute('CREATE TEMP TABLE IF NOT EXISTS nq_final_campaigns (service TEXT, nr_mode TEXT, campaign TEXT)')
    connection.execute('DELETE FROM nq_final_campaigns')
    connection.execute(f"""
        INSERT INTO nq_final_campaigns (service, nr_mode, campaign)
        SELECT DISTINCT p.service, p.nr_mode, lower(p.campaign) FROM {NQ_CALL_POPULATION_TABLE} p
        JOIN {NQ_CALL_SOURCES_TABLE} s ON s.dataset_id = p.dataset_id WHERE s.stage_rank = 1
    """)
    connection.execute(f"""
        UPDATE {NQ_CALL_VERSIONS_TABLE} SET final_covered = CASE WHEN in_final = 0 AND EXISTS (
            SELECT 1 FROM {NQ_CALL_POPULATION_TABLE} p JOIN nq_final_campaigns f
              ON f.service = p.service AND f.nr_mode = p.nr_mode AND f.campaign = lower(p.campaign)
            WHERE p.call_key = {NQ_CALL_VERSIONS_TABLE}.call_key AND p.is_latest = 1) THEN 1 ELSE 0 END
    """)


def _combined_ranks(task_repository: Any) -> dict[int, int]:
    """How each CDR ranks among the versions of a call: the CDRs the combined tables include first (the Final CDR of
    a campaign, else its newest Weekly or Daily CDRs, or the In Combined? choice of Workspace), then the Final, the
    Weekly and the Daily CDRs."""
    try:
        inclusion = combined_inclusion(task_repository)
    except Exception:  # noqa: BLE001 - the versions keep their order until the next indexing.
        return {}
    order = {'final': 2, 'weekly': 1, 'daily': 0}
    return {int(dataset_id): (10 if item.get('included') else 0) + order.get(str(item.get('stage') or 'final'), 2)
            for dataset_id, item in inclusion.items()}


def _rank_changes(task_repository: Any, ranks: dict[int, int] | None = None) -> dict[int, int]:
    """The indexed CDRs whose rank changed (another In Combined? choice, or a Final CDR that replaces them)."""
    ranks = _combined_ranks(task_repository) if ranks is None else ranks
    with task_repository.connection() as connection:
        stored = {int(row[0]): int(row[1]) for row in connection.execute(
            f'SELECT dataset_id, combined_rank FROM {NQ_CALL_SOURCES_TABLE}')}
    return {dataset_id: ranks[dataset_id] for dataset_id, rank in stored.items() if dataset_id in ranks and ranks[dataset_id] != rank}


def _index_changes(task_repository: Any, force: bool = False) -> tuple[list[str], str, dict[int, Any], list[int], list[Any]]:
    """The indexed CDR columns and their signature, the CDRs, the indexed CDRs now removed and the CDRs to index."""
    cdr_columns = indexed_cdr_columns(task_repository)
    signature = _columns_signature(cdr_columns)
    # Fields changed in the CDR Field Dictionary change the columns the calls are read from.
    if dictionary := cdr_field_dictionary.fingerprint(cdr_field_dictionary.load_overrides(task_repository)):
        signature = f'{signature}:{dictionary}'
    datasets = {int(row['id']): row for row in _cdr_datasets(task_repository)}
    with task_repository.connection() as connection:
        indexed = {
            int(row['dataset_id']): str(row['revision'])
            for row in connection.execute(f'SELECT dataset_id, revision FROM {NQ_CALL_SOURCES_TABLE}').fetchall()
        }
    removed = [dataset_id for dataset_id in indexed if dataset_id not in datasets]
    changed = [row for dataset_id, row in datasets.items()
               if force or indexed.get(dataset_id) != _dataset_revision(row, signature)]
    return cdr_columns, signature, datasets, removed, changed


def sync_nq_calls(task_repository: Any, *, force: bool = False) -> dict[str, Any]:
    """Index the NQ calls and the population of new or changed CDRs and forget removed ones; ``force`` indexes
    every CDR again (Reindex)."""
    ensure_nq_tables(task_repository)
    with _sync_lock(task_repository):
        cdr_columns, signature, datasets, removed, changed = _index_changes(task_repository, force)
        profile = workspace_field_profile(task_repository)
        if profile.nq_call_radio_from_samples and (removed or any(str(row['dataset_kind']) == 'speech' for row in changed)):
            # The Voice calls take the radio of their Speech samples: new samples index them again.
            indexed = {int(row['id']) for row in changed}
            changed = [*changed, *(row for dataset_id, row in datasets.items()
                                   if str(row['dataset_kind']) == 'voice' and dataset_id not in indexed)]
        # The key scheme, and the CDR Field Dictionary that can change the identifiers of the calls: when either
        # changes, the follow-up of every call moves to its new call key.
        dictionary = cdr_field_dictionary.fingerprint(cdr_field_dictionary.load_overrides(task_repository))
        key_scheme = f'{KEY_SCHEME}:{dictionary}' if dictionary else KEY_SCHEME
        stored_scheme = str(task_repository.get_workspace_state(KEY_SCHEME_STATE_KEY) or '')
        migrating = stored_scheme != key_scheme
        moved = 0
        ranks = _combined_ranks(task_repository)
        if removed or changed:
            # Read every changed CDR before taking the write transaction.
            with task_repository.connection() as connection:
                sample_radio = _sample_radio(connection, datasets.values(), profile) if profile.nq_call_radio_from_samples else None
                fresh = {int(row['id']): _dataset_calls(connection, row, tuple(cdr_columns), profile, sample_radio) for row in changed}
                touched = [*removed, *fresh]
                marks = ', '.join('?' for _ in touched)
                affected = {str(row[0]) for row in connection.execute(
                    f'SELECT DISTINCT call_key FROM {NQ_CALL_POPULATION_TABLE} WHERE dataset_id IN ({marks})', touched)}
                old_rows = connection.execute(
                    f'SELECT rowid, dataset_id, source_row_id, call_key FROM {NQ_CALLS_TABLE} WHERE dataset_id IN ({marks})',
                    touched).fetchall() if migrating else []
            columns = ', '.join(_CALL_COLUMNS)
            placeholders = ', '.join('?' for _ in _CALL_COLUMNS)
            with task_repository.connection() as connection:
                for dataset_id in touched:
                    connection.execute(f'DELETE FROM {NQ_CALLS_TABLE} WHERE dataset_id = ?', (dataset_id,))
                    connection.execute(f'DELETE FROM {NQ_DTA_RESULTS_TABLE} WHERE dataset_id = ?', (dataset_id,))
                    connection.execute(f'DELETE FROM {NQ_DTA_LEARNED_TABLE} WHERE dataset_id = ?', (dataset_id,))
                    connection.execute(f'DELETE FROM {NQ_CALL_SOURCES_TABLE} WHERE dataset_id = ?', (dataset_id,))
                    connection.execute(f'DELETE FROM {NQ_CALL_POPULATION_TABLE} WHERE dataset_id = ?', (dataset_id,))
                # What their rows learned is gone: the DT Analyzer RCA learns again once they are indexed.
                connection.execute('DELETE FROM workspace_state WHERE key = ?', (nq_dta_rca.LEARNED_FINGERPRINT_STATE_KEY,))
                for dataset_id, content in fresh.items():
                    row = datasets[dataset_id]
                    connection.executemany(f'INSERT OR REPLACE INTO {NQ_CALLS_TABLE} ({columns}) VALUES ({placeholders})',
                                           content['calls'])
                    connection.executemany(
                        f'INSERT OR REPLACE INTO {NQ_CALL_POPULATION_TABLE} '
                        f"(dataset_id, call_key, service, campaign, operator, nr_mode, is_nq, {', '.join(POPULATION_FIELDS)}) "
                        f"VALUES ({', '.join('?' for _ in range(7 + len(POPULATION_FIELDS)))})",
                        content['population'])
                    stage = dataset_cdr_stage(row['dataset_kind'], row['cdr_stage'] if 'cdr_stage' in row.keys() else None,
                                              row['file_name'])
                    connection.execute(
                        f'INSERT INTO {NQ_CALL_SOURCES_TABLE} (dataset_id, revision, call_count, synced_at, stage_rank, '
                        'data_date, population_count, combined_rank) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (dataset_id, _dataset_revision(row, signature), len({call[2] for call in content['calls']}), now_iso(),
                         int(stage == 'final'), content['data_date'], len(content['population']), ranks.get(dataset_id, -1)),
                    )
                    affected.update(entry[1] for entry in content['population'])
                if old_rows:
                    moved = _move_follow_up(connection, old_rows, [call for content in fresh.values() for call in content['calls']])
                _rebuild_versions(connection, affected)
        # A CDR that the combined tables include or leave out now changes the version of its calls, without reading it.
        reranked = _rank_changes(task_repository, ranks)
        if reranked:
            with task_repository.connection() as connection:
                marks = ', '.join('?' for _ in reranked)
                connection.executemany(f'UPDATE {NQ_CALL_SOURCES_TABLE} SET combined_rank = ? WHERE dataset_id = ?',
                                       [(rank, dataset_id) for dataset_id, rank in reranked.items()])
                _rebuild_versions(connection, {str(row[0]) for row in connection.execute(
                    f'SELECT DISTINCT call_key FROM {NQ_CALL_POPULATION_TABLE} WHERE dataset_id IN ({marks})', list(reranked))})
        if migrating:
            task_repository.set_workspace_state(KEY_SCHEME_STATE_KEY, key_scheme)
            if moved and hasattr(task_repository, 'try_add_log'):
                reason = ('their JOIN_ID call keys' if stored_scheme.partition(':')[0] != KEY_SCHEME
                          else 'their call keys of the changed CDR Field Dictionary')
                task_repository.try_add_log('system', 'nq_call_keys_upgraded',
                                            f'Non-Qualified Calls follow-up of {moved} calls moved to {reason}.')
        # The latest versions of the calls and the DT Analyzer RCA of the new ones are calculated here, in the
        # background, rather than by the next page.
        refresh_latest_calls(task_repository)
        _refresh_dta_rca(task_repository)
        with task_repository.connection() as connection:
            total = connection.execute(f'SELECT COUNT(DISTINCT call_key) FROM {NQ_CALLS_TABLE}').fetchone()[0]
            synced_at = connection.execute(f'SELECT MAX(synced_at) FROM {NQ_CALL_SOURCES_TABLE}').fetchone()[0]
    return {'datasets': len(datasets), 'reindexed': len(changed), 'removed': len(removed),
            'calls': int(total or 0), 'synced_at': synced_at or ''}


# ---------------------------------------------------------------------------
# Indexing in the background: new, changed or removed CDRs are indexed once the server has been idle for a while
# (or at once the first time, and on Reindex), never while a page waits for its calls.
NQ_INDEX_IDLE_SECONDS = 2 * 60
# The NQ Prioritization is calculated after the indexing (see nq_prioritization).
NQ_PRIORITIZATION_IDLE_SECONDS = 3 * 60
_index_jobs: dict[str, dict[str, Any]] = {}
_index_jobs_guard = Lock()


def _workspace_key(path: Any) -> str:
    return str(Path(str(path)).resolve())


def nq_index_job(database_path: Any) -> dict[str, Any] | None:
    with _index_jobs_guard:
        job = _index_jobs.get(_workspace_key(database_path))
        return dict(job) if job else None


def start_nq_index(task_repository: Any, submit: Callable[..., Any], *, force: bool = False) -> dict[str, Any]:
    """Queue the indexing of the workspace (every CDR again with ``force``), unless it is already queued or running."""
    key = _workspace_key(task_repository.db_path)
    with _index_jobs_guard:
        current = _index_jobs.get(key)
        if current and current['status'] in {'queued', 'processing'}:
            return dict(current)
        job = {'status': 'queued', 'force': force, 'queued_at': time.time(), 'started_at': None, 'finished_at': None,
               'error': '', 'result': None}
        _index_jobs[key] = job

    def run() -> None:
        with _index_jobs_guard:
            job.update(status='processing', started_at=time.time())
        try:
            result = sync_nq_calls(task_repository, force=force)
        except Exception as exc:  # The next idle period or a Reindex tries again.
            with _index_jobs_guard:
                job.update(status='failed', error=str(exc), finished_at=time.time())
            return
        with _index_jobs_guard:
            job.update(status='ready', result=result, finished_at=time.time())

    submit(run)
    with _index_jobs_guard:
        return dict(job)


def nq_index_status(task_repository: Any) -> dict[str, Any]:
    """The indexed calls and CDRs, when they were last indexed, the CDRs waiting to be indexed and the running job."""
    _columns, _signature, datasets, removed, changed = _index_changes(task_repository)
    reranked = [dataset_id for dataset_id in _rank_changes(task_repository) if dataset_id not in {int(row['id']) for row in changed}]
    with task_repository.connection() as connection:
        total = connection.execute(f'SELECT COUNT(DISTINCT call_key) FROM {NQ_CALLS_TABLE}').fetchone()[0]
        synced_at = connection.execute(f'SELECT MAX(synced_at) FROM {NQ_CALL_SOURCES_TABLE}').fetchone()[0]
    job = nq_index_job(task_repository.db_path)
    running = bool(job and job['status'] in {'queued', 'processing'})
    return {'datasets': len(datasets), 'calls': int(total or 0), 'synced_at': synced_at or '',
            'pending': len(removed) + len(changed) + len(reranked), 'indexing': running, 'reindexing': running and bool(job['force']),
            'error': job['error'] if job and job['status'] == 'failed' else ''}


# ---------------------------------------------------------------------------
# Options: statuses and teams
# ---------------------------------------------------------------------------
def list_options(task_repository: Any) -> dict[str, list[dict[str, Any]]]:
    """The statuses and the teams, each team with its members."""
    with task_repository.connection() as connection:
        rows = connection.execute(
            f'SELECT kind, name, color, is_closed FROM {NQ_CALL_OPTIONS_TABLE} ORDER BY kind, position, name COLLATE NOCASE'
        ).fetchall()
        members: dict[str, list[str]] = {}
        for row in connection.execute(f'SELECT team, username FROM {NQ_TEAM_MEMBERS_TABLE} ORDER BY username COLLATE NOCASE'):
            members.setdefault(str(row['team']).casefold(), []).append(str(row['username']))
    options: dict[str, list[dict[str, Any]]] = {'statuses': [], 'teams': []}
    for row in rows:
        item = {'name': str(row['name']), 'color': str(row['color'])}
        if row['kind'] == 'status':
            options['statuses'].append({**item, 'closed': bool(row['is_closed'])})
        else:
            options['teams'].append({**item, 'members': members.get(item['name'].casefold(), [])})
    return options


def team_members(options: dict[str, list[dict[str, Any]]]) -> dict[str, set[str]]:
    """Casefolded members of every team that has members."""
    return {team['name'].casefold(): {member.casefold() for member in team.get('members') or []}
            for team in options['teams'] if team.get('members')}


def default_status(options: dict[str, list[dict[str, Any]]]) -> str:
    """Untracked calls show the first status."""
    return options['statuses'][0]['name'] if options['statuses'] else 'Open'


def _normalize_option_list(items: Any, kind: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError(f'The {kind} list is invalid.')
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f'The {kind} list is invalid.')
        name = re.sub(r'\s+', ' ', str(item.get('name') or '')).strip()[:60]
        if not name:
            raise ValueError(f'Every {kind} needs a name.')
        if name.casefold() in seen:
            raise ValueError(f'The {kind} "{name}" is repeated.')
        seen.add(name.casefold())
        color = str(item.get('color') or '').strip()
        option = {
            'name': name,
            'previous': re.sub(r'\s+', ' ', str(item.get('previous') or '')).strip(),
            'color': color if COLOR_PATTERN.fullmatch(color) else '#7b8790',
            'closed': bool(item.get('closed')) if kind == 'status' else False,
        }
        # Teams edited without their members keep the members they have.
        if kind == 'team' and isinstance(item.get('members'), list):
            option['members'] = list(dict.fromkeys(
                str(member).strip() for member in item['members'] if str(member).strip()
            ))
        # The teams merged into this one: their calls (and members) move here.
        if kind == 'team' and isinstance(item.get('merged'), list):
            option['merged'] = list(dict.fromkeys(
                name for name in (re.sub(r'\s+', ' ', str(merged)).strip() for merged in item['merged']) if name))
        normalized.append(option)
    return normalized


def save_options(
    task_repository: Any, statuses: Any, teams: Any, username: str, users: set[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Replace the statuses and teams; renamed values follow on every call, removed ones must be unused (a status
    only by the calls that have it set by hand: the automatic ones follow the Status Rules again).

    A team lists in ``merged`` the teams merged into it: their calls move to it and they are removed. Team members
    must be users of the workspace when ``users`` is given.
    """
    current = list_options(task_repository)
    lists = {'status': _normalize_option_list(statuses, 'status'), 'team': _normalize_option_list(teams, 'team')}
    if users is not None:
        known = {name.casefold(): name for name in users}
        for team in lists['team']:
            if 'members' not in team:
                continue
            unknown = [member for member in team['members'] if member.casefold() not in known]
            if unknown:
                raise ValueError(f'{", ".join(unknown)} cannot join "{team["name"]}": choose users with access to this workspace.')
            team['members'] = [known[member.casefold()] for member in team['members']]
    if not lists['status']:
        raise ValueError('Keep at least one status.')
    existing_statuses = {item['name'].casefold() for item in current['statuses']}
    renamed_statuses = {item['previous'].casefold(): item['name'] for item in lists['status']
                        if item['previous'] and item['previous'].casefold() in existing_statuses}
    try:
        stored_rules = json.loads(task_repository.get_workspace_state(STATUS_RULES_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        stored_rules = []
    with task_repository.connection() as connection:
        for kind, column in (('status', 'status'), ('team', 'team')):
            existing = {item['name'].casefold(): item['name'] for item in current['statuses' if kind == 'status' else 'teams']}
            # A merged team is renamed to the team it is merged into, before the other renames.
            renamed = {name.casefold(): item['name'] for item in lists[kind] for name in item.get('merged', [])
                       if name.casefold() in existing and name.casefold() != item['name'].casefold()}
            renamed.update({item['previous'].casefold(): item['name'] for item in lists[kind]
                            if item['previous'] and item['previous'].casefold() in existing})
            kept = {item['name'].casefold() for item in lists[kind]} | set(renamed)
            for old_key, old_name in existing.items():
                if old_key in kept:
                    continue
                # A status given by the Status Rules does not keep it: those calls follow the rules again below.
                by_hand = " AND status_mode = 'manual'" if kind == 'status' else ''
                used = connection.execute(
                    f'SELECT COUNT(*) FROM {NQ_CALL_TRACKING_TABLE} WHERE {column} = ? COLLATE NOCASE{by_hand}', (old_name,),
                ).fetchone()[0]
                if used and kind == 'status':
                    raise ValueError(f'The status "{old_name}" is set by hand on {used} call{"" if used == 1 else "s"}; '
                                     'rename it or move those calls first.')
                if used:
                    raise ValueError(f'The {kind} "{old_name}" is in use; rename it, merge it into another team or move its calls first.')
            for old_key, new_name in renamed.items():
                old_name = existing[old_key]
                if old_name != new_name:
                    connection.execute(
                        f'UPDATE {NQ_CALL_TRACKING_TABLE} SET {column} = ? WHERE {column} = ? COLLATE NOCASE',
                        (new_name, old_name),
                    )
            connection.execute(f'DELETE FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = ?', (kind,))
            connection.executemany(
                f'INSERT INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES (?, ?, ?, ?, ?)',
                [(kind, item['name'], item['color'], index, int(item['closed'])) for index, item in enumerate(lists[kind])],
            )
            if kind == 'team':
                previous_members = {item['name'].casefold(): item.get('members') or [] for item in current['teams']}
                connection.execute(f'DELETE FROM {NQ_TEAM_MEMBERS_TABLE}')
                rows = []
                for item in lists['team']:
                    members = item['members'] if 'members' in item else previous_members.get(
                        (item['previous'] or item['name']).casefold(), previous_members.get(item['name'].casefold(), []))
                    # A team with members takes the members of the teams merged into it (one for everyone stays so).
                    if 'members' not in item and members:
                        members = list(dict.fromkeys(members + [member for name in item.get('merged', [])
                                                                 for member in previous_members.get(name.casefold(), [])]))
                    rows.extend((item['name'], member) for member in members)
                connection.executemany(
                    f'INSERT OR IGNORE INTO {NQ_TEAM_MEMBERS_TABLE} (team, username) VALUES (?, ?)', rows,
                )
    # The status rules follow renamed statuses and forget removed ones.
    if isinstance(stored_rules, list):
        rules = nq_catalog.rules_after_status_changes(
            [rule for rule in stored_rules if isinstance(rule, dict) and rule.get('status')], renamed_statuses,
            [item['name'] for item in lists['status']])
        task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
    recompute_statuses(task_repository, username)
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_call_options', 'Non-Qualified Calls statuses and teams updated.')
    return list_options(task_repository)


# ---------------------------------------------------------------------------
# The field catalog: every field of the Analysis Center, in its section
# ---------------------------------------------------------------------------
MAX_FIELDS = nq_catalog.MAX_FIELDS


def list_fields(task_repository: Any) -> list[dict[str, Any]]:
    """The fields of the workspace catalog, in order, with their section, source and options."""
    with task_repository.connection() as connection:
        rows = connection.execute(f'SELECT * FROM {NQ_FIELDS_TABLE} ORDER BY position, label COLLATE NOCASE').fetchall()
    fields = []
    for row in rows:
        try:
            options = json.loads(row['options_json'] or '[]')
        except (TypeError, ValueError):
            options = []
        keys = row.keys()
        fields.append({
            'key': str(row['field_key']), 'label': str(row['label']), 'type': str(row['field_type']),
            'options': [{'name': str(item.get('name') or ''), 'color': str(item.get('color') or ''),
                         'keywords': _keywords(item.get('keywords'))}
                        for item in options if isinstance(item, dict) and item.get('name')],
            'in_table': bool(row['in_table']), 'in_summary': bool(row['in_summary']),
            'required_to_close': bool(row['required_to_close']), 'description': str(row['description'] or ''),
            'section': str(row['section'] if 'section' in keys else 'analysis') or 'analysis',
            'source': str(row['source'] if 'source' in keys else 'user') or 'user',
            'source_ref': str(row['source_ref'] if 'source_ref' in keys else '') or '',
            'in_export': bool(row['in_export'] if 'in_export' in keys else 1),
            'suggest_from': str(row['suggest_from'] if 'suggest_from' in keys else '') or '',
        })
    # The lists of the NQ Prioritization take their values from it (the rules are the values of Prioritization Rule).
    priority = [field for field in fields if field['source'] == 'priority']
    if priority:
        names = nq_prioritization.rule_names(task_repository) if any(field['source_ref'] == 'priority_rule' for field in priority) else []
        for field in priority:
            field['type'] = nq_catalog.PRIORITY_TYPES.get(field['source_ref'], field['type'])
            field['options'] = nq_catalog.priority_options(field['source_ref'], names)
    return fields


def _store_fields(task_repository: Any, fields: list[dict[str, Any]]) -> None:
    with task_repository.connection() as connection:
        connection.execute(f'DELETE FROM {NQ_FIELDS_TABLE}')
        connection.executemany(
            f'INSERT INTO {NQ_FIELDS_TABLE} (field_key, label, field_type, options_json, position, in_table, in_summary, '
            'required_to_close, description, section, source, source_ref, in_export, suggest_from) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            [(field['key'], field['label'], field['type'],
              json.dumps([{'name': option['name'], 'color': option.get('color', ''),
                           **({'keywords': option['keywords']} if option.get('keywords') else {})}
                          for option in field['options']], ensure_ascii=False),
              index, int(field['in_table']), int(field['in_summary']), int(field['required_to_close']), field['description'],
              field['section'], field['source'], field['source_ref'], int(field.get('in_export', True)), field.get('suggest_from', ''))
             for index, field in enumerate(fields)],
        )


def save_fields(task_repository: Any, items: Any, username: str, *, defaults: bool = False) -> list[dict[str, Any]]:
    """Replace the field catalog; renamed list values follow on every call and in the status rules, values in use
    cannot be removed, and the follow-up fields (status, team, assignee…) stay."""
    existing = {field['key']: field for field in list_fields(task_repository)}
    if not isinstance(items, list):
        raise ValueError('The field list is invalid.')
    # The follow-up fields (status, team, assignee…) cannot be removed: those left out keep their place at the end.
    given = {str(item.get('source_ref')) for item in items if isinstance(item, dict) and item.get('source') == 'tracking'}
    given |= {str(existing[str(item.get('key'))]['source_ref']) for item in items
              if isinstance(item, dict) and str(item.get('key')) in existing and existing[str(item.get('key'))]['source'] == 'tracking'}
    items = [*items, *(field for field in existing.values() if field['source'] == 'tracking' and field['source_ref'] not in given)]
    normalized = nq_catalog.normalize_fields(items, existing, CATALOG_CALL_FIELDS)
    kept = {field['key'] for field in normalized}
    # The new values of the Planned FY are fiscal years (2027 is FY27).
    for field in normalized:
        if field['key'] == FISCAL_FIELD and field['type'] == 'list':
            known = {option['name'].casefold() for option in (existing.get(FISCAL_FIELD) or {}).get('options', [])}
            options: dict[str, dict[str, Any]] = {}
            for option in field['options']:
                name = option['name'] if option['name'].casefold() in known else _fiscal_value(field, option['name'])
                options.setdefault(name.casefold(), dict(option, name=name))
            field['options'] = list(options.values())
    with task_repository.connection() as connection:
        def used(key: str, value: str | None = None) -> int:
            sql = f"SELECT COUNT(*) FROM {NQ_FIELD_VALUES_TABLE} WHERE field_key = ? AND value <> ''"
            params: list[Any] = [key]
            if value is not None:
                sql += ' AND value = ? COLLATE NOCASE'
                params.append(value)
            return int(connection.execute(sql, params).fetchone()[0])

        for key, field in existing.items():
            if key not in kept and field['source'] == 'user' and used(key):
                raise ValueError(f'The field "{field["label"]}" has values; clear them before removing it.')
        for field in normalized:
            previous = existing.get(field['key'])
            if previous is None or previous['source'] != 'user':
                continue
            if (previous['type'] != field['type'] or field['source'] != 'user') and used(field['key']):
                raise ValueError(f'"{field["label"]}" has values: its type and source cannot change.')
            if field['type'] != 'list' or previous['type'] != 'list':
                continue
            old = {option['name'].casefold(): option['name'] for option in previous['options']}
            renamed = {option['previous'].casefold(): option['name'] for option in field['options']
                       if option.get('previous') and option['previous'].casefold() in old}
            names = {option['name'].casefold() for option in field['options']} | set(renamed)
            for key, name in old.items():
                if key not in names and used(field['key'], name):
                    raise ValueError(f'The value "{name}" of "{field["label"]}" is in use; rename it or change those calls first.')
            for key, name in renamed.items():
                if old[key] != name:
                    connection.execute(
                        f'UPDATE {NQ_FIELD_VALUES_TABLE} SET value = ? WHERE field_key = ? AND value = ? COLLATE NOCASE',
                        (name, field['key'], old[key]))
    rules = nq_catalog.rules_after_field_changes(status_rules(task_repository), list(existing.values()), normalized)
    _store_fields(task_repository, normalized)
    task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
    recompute_statuses(task_repository, username)
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_analysis_fields', 'Non-Qualified Calls field catalog restored to the default '
                                    'fields.' if defaults else 'Non-Qualified Calls field catalog updated.')
    return list_fields(task_repository)


def list_sections(task_repository: Any) -> list[dict[str, str]]:
    """The six sections with the names and colours of the workspace."""
    try:
        stored = json.loads(task_repository.get_workspace_state(SECTIONS_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        stored = []
    return nq_catalog.normalize_sections(stored if isinstance(stored, list) else [])


# The field of the fiscal years: its values are written FY27 (the year 2027 is FY27).
FISCAL_FIELD = 'planned_fy'


def _fiscal_value(field: dict[str, Any], value: str) -> str:
    fiscal = nq_analyses.fiscal_year(value)
    if fiscal is None:
        raise ValueError(f'{field["label"]} takes fiscal years such as FY27 (the year 2027 is FY27), not "{value}".')
    return fiscal


def _in_fiscal_order(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The fiscal years first, from the earliest, then any other value in its order."""
    fiscal = [option for option in options if nq_analyses.fiscal_year(option['name']) == option['name']]
    return sorted(fiscal, key=lambda option: int(option['name'][2:])) + [option for option in options if option not in fiscal]


def add_field_option(task_repository: Any, key: str, name: Any, username: str) -> dict[str, Any]:
    """A new value of a list field of the analysts, typed in the list of a call: at the end of its list (a fiscal year
    of the Planned FY in its order, a year written as a fiscal year), or the value of the same name when the list has
    it; the field, the value and whether it was added."""
    fields = list_fields(task_repository)
    field = next((item for item in fields if item['key'] == key), None)
    if field is None:
        raise LookupError('The field does not exist.')
    if field['type'] != 'list' or field['source'] != 'user':
        raise ValueError(f'{field["label"]} does not take new values.')
    value = re.sub(r'\s+', ' ', str(name if name is not None else '')).strip()
    if not value:
        raise ValueError('Type the new value.')
    if len(value) > 80:
        raise ValueError('A value has 80 characters at most.')
    if key == FISCAL_FIELD:
        value = _fiscal_value(field, value)
    found = next((option['name'] for option in field['options'] if option['name'].casefold() == value.casefold()), None)
    if found is None:
        before = {item['key']: dict(item, options=[dict(option) for option in item['options']]) for item in fields}
        field['options'].append({'name': value, 'color': ''})
        if key == FISCAL_FIELD:
            field['options'] = _in_fiscal_order(field['options'])
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, before, CATALOG_CALL_FIELDS))
        if hasattr(task_repository, 'try_add_log'):
            task_repository.try_add_log(username, 'nq_analysis_fields', f'Non-Qualified Calls value {value} added to {field["label"]}.')
    return {'field': next(item for item in list_fields(task_repository) if item['key'] == key), 'value': found or value,
            'added': found is None}


def save_sections(task_repository: Any, items: Any, username: str, *, defaults: bool = False) -> list[dict[str, str]]:
    sections = nq_catalog.normalize_sections(items if isinstance(items, list) else [])
    task_repository.set_workspace_state(SECTIONS_STATE_KEY, json.dumps(sections, ensure_ascii=False))
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_sections', 'Non-Qualified Calls sections restored to the default sections.'
                                    if defaults else 'Non-Qualified Calls sections updated.')
    return sections


def _field_value(field: dict[str, Any], value: Any) -> str:
    """A valid value of a field entered by the analysts ('' clears it)."""
    text = str(value if value is not None else '').strip()
    if not text:
        return ''
    if field['source'] != 'user':
        raise ValueError(f'{field["label"]} is set automatically.')
    kind = field['type']
    if kind == 'list':
        names = {option['name'].casefold(): option['name'] for option in field['options']}
        if text.casefold() not in names:
            raise ValueError(f'Choose one of the values of {field["label"]}.')
        return names[text.casefold()]
    if kind == 'yes_no':
        names = {name.casefold(): name for name in YES_NO}
        if text.casefold() not in names:
            raise ValueError(f'{field["label"]} is Yes or No.')
        return names[text.casefold()]
    if kind == 'number':
        number = _number(text.replace(',', '.'))
        if number is None:
            raise ValueError(f'{field["label"]} is a number.')
        return str(int(number)) if number.is_integer() else repr(number)
    if kind == 'date':
        try:
            return datetime.strptime(text[:10], '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError as exc:
            raise ValueError(f'{field["label"]} is a date (YYYY-MM-DD).') from exc
    limit = MAX_LONG_TEXT if kind == 'long_text' else 300
    if len(text) > limit:
        raise ValueError(f'{field["label"]} accepts up to {limit} characters.')
    return text if kind == 'long_text' else re.sub(r'\s+', ' ', text)


def field_values(connection: Any, keys: list[str]) -> dict[str, dict[str, str]]:
    values: dict[str, dict[str, str]] = {}
    for start in range(0, len(keys), 500):
        chunk = keys[start:start + 500]
        for row in connection.execute(
            f"SELECT call_key, field_key, value FROM {NQ_FIELD_VALUES_TABLE} WHERE value <> '' "
            f"AND call_key IN ({', '.join('?' for _ in chunk)})", chunk,
        ):
            values.setdefault(str(row['call_key']), {})[str(row['field_key'])] = str(row['value'])
    return values


def derived_value(field: dict[str, Any], call: Any) -> str:
    """The value of a derived list: the first option whose keywords appear in the call values it reads."""
    text = ' '.join(_normalized_text(_call_value(call, name)) for name in field['source_ref'].split(','))
    return next((option['name'] for option in field['options'] if keyword_found(option.get('keywords') or [], text, 'text')), '')


def _call_value(call: Any, key: str) -> Any:
    key = key.strip()
    try:
        if key.startswith('column:'):
            extra = call['extra'] if isinstance(call, dict) and 'extra' in call else json.loads(call['extra_json'] or '{}')
            return (extra or {}).get(key[7:], '')
        return call[key]
    except (KeyError, IndexError, TypeError, ValueError):
        return ''


def dta_of(call: Any) -> dict[str, str]:
    """The DT Analyzer RCA of a call row or payload (its dta_domain, dta_category, dta_cause, dta_rule and dta_evidence)."""
    if isinstance(call, dict) and isinstance(call.get('dta'), dict):
        return call['dta']
    try:
        return json.loads(call['dta_json'] or '{}') or {}
    except (KeyError, IndexError, TypeError, ValueError):
        return {}


def catalog_value(field: dict[str, Any], call: Any, rca: dict[str, str] | None = None, stored: dict[str, str] | None = None) -> Any:
    """The value of a catalog field for a call: entered, followed up, from the CDR, the Ericsson RCA, the DT Analyzer
    RCA or derived."""
    source, ref = field['source'], field['source_ref']
    if source == 'user':
        return (stored or {}).get(field['key'], '')
    if source == 'tracking':
        return _call_value(call, 'comment_count' if ref == 'comments' else ref)
    if source == 'cdr':
        return _call_value(call, ref)
    if source == 'rca':
        return (rca or {}).get(ref, '')
    if source == 'dta':
        return dta_of(call).get(ref, '')
    if source == 'derived':
        return derived_value(field, call)
    if source == 'priority':
        value = _call_value(call, ref)
        if ref in {'impact_points', 'expected_points'} and isinstance(value, (int, float)):
            return round(float(value), 2)
        return '' if value is None else value
    return ''


def field_sql(field: dict[str, Any]) -> str:
    """The SQL value of a catalog field in the calls query (``calls`` rows of ``_base_sql``)."""
    source, ref = field['source'], field['source_ref']
    if source == 'user':
        return f"COALESCE(json_extract(field_values_json, '$.\"{field['key']}\"'), '')"
    if source == 'tracking':
        return {'comments': 'comment_count', 'updated_at': "substr(updated_at, 1, 10)"}.get(ref, ref) \
            if ref in nq_catalog.TRACKING_REFS else "''"
    if source == 'cdr':
        if ref in CATALOG_CALL_FIELDS:
            return f"COALESCE(CAST({ref} AS TEXT), '')"
        name = ref[7:].replace('"', '').replace("'", '') if ref.startswith('column:') else ref
        return f"COALESCE(CAST(json_extract(extra_json, '$.\"{name}\"') AS TEXT), '')"
    if source == 'rca':
        name = ref.replace('"', '').replace("'", '')
        return f"COALESCE(json_extract(rca_json, '$.\"{name}\"'), '')"
    if source == 'dta':
        return f"COALESCE(json_extract(dta_json, '$.{ref}'), '')" if ref in nq_catalog.DTA_REFS else "''"
    if source == 'priority':
        # The numbers stay numbers, so they sort as such.
        return f"COALESCE({ref}, '')" if ref in nq_catalog.PRIORITY_REFS else "''"
    if source == 'derived':
        names = [name.strip() for name in ref.split(',') if name.strip() in CALL_FIELDS]
        if not names:
            return "''"
        text = "lower(' ' || " + " || ' ' || ".join(f"COALESCE({name}, '')" for name in names) + " || ' ')"
        text = f"replace({text}, '_', ' ')"
        cases = []
        for option in field['options']:
            tests = []
            for keyword in option.get('keywords') or []:
                parts = [part.replace("'", "''") for part in keyword.split('+')]
                tests.append('(' + ' AND '.join(f"instr({text}, '{part}') > 0" for part in parts) + ')')
            if tests:
                cases.append(f"WHEN {' OR '.join(tests)} THEN '{option['name'].replace(chr(39), chr(39) * 2)}'")
        return f"(CASE {' '.join(cases)} ELSE '' END)" if cases else "''"
    return "''"


def catalog_document(task_repository: Any) -> bytes:
    """The whole catalog of the workspace as an Excel workbook, to edit and import again."""
    options = list_options(task_repository)
    root = list_root_causes(task_repository)
    return nq_catalog.catalog_workbook(list_sections(task_repository), list_fields(task_repository), options['statuses'],
                                       options['teams'], root, status_rules(task_repository))


def _merged_catalog(task_repository: Any, incoming: dict[str, Any]) -> dict[str, Any]:
    """The catalog after an import: incoming entries first (matched by key or name), then the current ones it leaves out."""
    current_fields = list_fields(task_repository)
    by_key = {field['key']: field for field in current_fields}
    by_label = {field['label'].casefold(): field for field in current_fields}
    fields: list[dict[str, Any]] = []
    used: set[str] = set()
    for item in incoming.get('fields') or []:
        existing = by_key.get(str(item.get('key') or '')) or by_label.get(str(item.get('label') or '').casefold())
        if existing is not None:
            if existing['key'] in used:
                continue
            item = {**existing, **{key: value for key, value in item.items() if value not in (None, '')}, 'key': existing['key']}
            if existing['source'] != 'user':
                item.update(source=existing['source'], source_ref=existing['source_ref'], type=existing['type'])
            if not item.get('options'):
                item['options'] = existing['options']
            used.add(existing['key'])
        elif item.get('source') == 'tracking' and item.get('source_ref') in {field['source_ref'] for field in current_fields
                                                                             if field['source'] == 'tracking'}:
            continue
        fields.append(item)
    fields += [field for field in current_fields if field['key'] not in used]
    options = list_options(task_repository)
    statuses, teams = options['statuses'], options['teams']
    for plural, items in (('statuses', incoming.get('statuses')), ('teams', incoming.get('teams'))):
        if not items:
            continue
        current = statuses if plural == 'statuses' else teams
        names = {item['name'].casefold(): item for item in current}
        ordered = []
        for item in items:
            name = str(item.get('name') or '').strip()
            if not name:
                continue
            base = names.get(name.casefold(), {})
            ordered.append({**base, **{key: value for key, value in item.items() if value not in (None, '')},
                            'previous': base.get('name', ''), **({'members': base.get('members', [])} if plural == 'teams' and not item.get('members') else {})})
        chosen = {item['name'].casefold() for item in ordered}
        ordered += [{**item, 'previous': item['name']} for item in current if item['name'].casefold() not in chosen]
        if plural == 'statuses':
            statuses = ordered
        else:
            teams = ordered
    root = list_root_causes(task_repository)
    stored = nq_catalog.stored_root_catalog(root)
    catalog = {plural: [dict(item, previous=item['name']) for item in stored[plural]] for plural in ('domains', 'categories', 'causes')}
    for plural, items in (incoming.get('root') or {}).items():
        names = {item['name'].casefold(): item for item in catalog.get(plural, [])}
        for item in items:
            name = str(item.get('name') or '').strip()
            if not name:
                continue
            if name.casefold() in names:
                names[name.casefold()].update({key: value for key, value in item.items() if value not in (None, '', [])})
            else:
                catalog[plural].append(dict(item))
    return {'sections': incoming.get('sections'), 'fields': fields, 'statuses': statuses, 'teams': teams, 'root': catalog,
            'rules': incoming.get('rules'), 'require_to_close': root['require_to_close']}


def preview_catalog(task_repository: Any, content: bytes) -> dict[str, Any]:
    """What importing a catalog workbook would change, without changing anything."""
    incoming = nq_catalog.read_catalog_workbook(content)
    merged = _merged_catalog(task_repository, incoming)
    current_fields = {field['key']: field for field in list_fields(task_repository)}
    normalized = nq_catalog.normalize_fields(merged['fields'], current_fields, CATALOG_CALL_FIELDS)
    added = [field['label'] for field in normalized if field['key'] not in current_fields]
    changed = [field['label'] for field in normalized if field['key'] in current_fields and any(
        field[key] != current_fields[field['key']].get(key) for key in ('label', 'section', 'type', 'in_table', 'in_export'))
        or (field['key'] in current_fields and [option['name'] for option in field['options']]
            != [option['name'] for option in current_fields[field['key']]['options']])]
    root = list_root_causes(task_repository)
    root_added = {plural: [item['name'] for item in merged['root'][plural]
                           if item['name'].casefold() not in {entry['name'].casefold() for entry in root[plural]}]
                  for plural in ('domains', 'categories', 'causes')}
    options = list_options(task_repository)
    return {
        'format': incoming.get('format'), 'fields': len(normalized), 'added': added, 'changed': changed,
        'root_added': root_added, 'sections': bool(incoming.get('sections')),
        'statuses_added': [item['name'] for item in merged['statuses']
                           if item['name'].casefold() not in {entry['name'].casefold() for entry in options['statuses']}],
        'teams_added': [item['name'] for item in merged['teams']
                        if item['name'].casefold() not in {entry['name'].casefold() for entry in options['teams']}],
        'rules': len(incoming.get('rules') or []),
    }


def import_catalog(task_repository: Any, content: bytes, username: str, users: set[str] | None = None) -> dict[str, Any]:
    """Import a catalog workbook: the new fields, list values, catalog entries, statuses and teams are added, and the
    sections and status rules it has are taken. Nothing is removed."""
    incoming = nq_catalog.read_catalog_workbook(content)
    merged = _merged_catalog(task_repository, incoming)
    if merged['sections']:
        save_sections(task_repository, merged['sections'], username)
    save_options(task_repository, merged['statuses'], merged['teams'], username, users)
    save_root_causes(task_repository, merged['root'], merged['require_to_close'], username)
    save_fields(task_repository, merged['fields'], username)
    if merged['rules']:
        save_status_rules(task_repository, merged['rules'], username)
    return {'fields': list_fields(task_repository), 'sections': list_sections(task_repository),
            'root_causes': list_root_causes(task_repository), 'options': list_options(task_repository),
            'status_rules': status_rules(task_repository)}


# ---------------------------------------------------------------------------
# Root cause catalog: domains, root categories and root causes
# ---------------------------------------------------------------------------
def _write_root_catalog(connection: Any, catalog: dict[str, list[dict[str, Any]]]) -> None:
    """Store a catalog in its stored form: the domain chosen by hand of each root category and cause, and the root
    category of each cause."""
    connection.execute(f'DELETE FROM {NQ_ROOT_CATALOG_TABLE}')
    rows = [('domain', item['name'], '', '', item.get('color') or '#7b8790', json.dumps(_keywords(item.get('keywords'))), index)
            for index, item in enumerate(catalog['domains'])]
    for kind, plural in (('category', 'categories'), ('cause', 'causes')):
        rows += [(kind, item['name'], item.get('domain') or '', (item.get('category') or '') if kind == 'cause' else '', '',
                  json.dumps(_keywords(item.get('keywords'))), index)
                 for index, item in enumerate(catalog[plural])]
    connection.executemany(
        f'INSERT INTO {NQ_ROOT_CATALOG_TABLE} (kind, name, domain, category, color, keywords, position) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)


def _read_root_catalog(connection: Any) -> dict[str, list[dict[str, Any]]]:
    """The catalog with the domain of every root category and cause resolved (``nq_catalog.resolve_root_catalog``);
    ``nq_catalog.stored_root_catalog`` gives it back in its stored form to change and write it."""
    rows = connection.execute(
        f'SELECT kind, name, domain, category, color, keywords FROM {NQ_ROOT_CATALOG_TABLE} '
        'ORDER BY position, name COLLATE NOCASE').fetchall()
    catalog: dict[str, list[dict[str, Any]]] = {'domains': [], 'categories': [], 'causes': []}
    plural = {'domain': 'domains', 'category': 'categories', 'cause': 'causes'}
    for row in rows:
        item = {'name': str(row['name']), 'keywords': _keywords(json.loads(row['keywords'] or '[]'))}
        if row['kind'] == 'domain':
            item['color'] = str(row['color'] or '#7b8790')
        else:
            item['domain'] = str(row['domain'] or '')
        if row['kind'] == 'cause':
            item['category'] = str(row['category'] or '')
        catalog[plural[str(row['kind'])]].append(item)
    nq_catalog.resolve_root_catalog(catalog)
    colors = {item['name']: item['color'] for item in catalog['domains']}
    for plural_name in ('categories', 'causes'):
        for item in catalog[plural_name]:
            item['color'] = colors.get(item['domain'], '')
    return catalog


def root_cause_settings(repository: Any) -> dict[str, Any]:
    try:
        stored = json.loads(repository.get_workspace_state(ROOT_CAUSE_SETTINGS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        stored = {}
    return {'require_to_close': bool(isinstance(stored, dict) and stored.get('require_to_close')),
            'rule': root_cause_rule(repository)}


def normalize_root_cause_rule(rule: Any) -> dict[str, Any]:
    """A valid suggestion rule: known fields in their order, flags and the keyword matching."""
    if not isinstance(rule, dict):
        raise ValueError('The root cause rule is invalid.')

    def fields(key: str) -> list[str]:
        values = rule.get(key)
        if not isinstance(values, list):
            raise ValueError('The root cause rule is invalid.')
        unknown = [str(value) for value in values if str(value) not in RULE_FIELDS]
        if unknown:
            raise ValueError(f'Unknown root cause rule fields: {", ".join(unknown)}.')
        return list(dict.fromkeys(str(value) for value in values))

    normalized = {'domain_fields': fields('domain_fields'), 'cause_fields': fields('cause_fields')}
    if not normalized['domain_fields'] and not normalized['cause_fields'] and not rule.get('comments'):
        raise ValueError('The rule must read at least one field or the comments.')
    normalized.update({key: bool(rule.get(key)) for key in ('causes_in_domain', 'comments', 'comment_domain')})
    normalized['match'] = str(rule.get('match') or 'words')
    if normalized['match'] not in RULE_MATCHES:
        raise ValueError('Choose whole-word or partial keyword matching.')
    return normalized


def root_cause_rule(repository: Any) -> dict[str, Any]:
    """The workspace suggestion rule, or the default one."""
    try:
        stored = json.loads(repository.get_workspace_state(ROOT_CAUSE_RULE_STATE_KEY) or 'null')
        return normalize_root_cause_rule(stored) if stored else dict(DEFAULT_ROOT_CAUSE_RULE)
    except (TypeError, ValueError):
        return dict(DEFAULT_ROOT_CAUSE_RULE)


def save_root_cause_rule(repository: Any, rule: Any, username: str) -> dict[str, Any]:
    """Save the suggestion rule; None restores the default one."""
    if rule is None:
        repository.set_workspace_state(ROOT_CAUSE_RULE_STATE_KEY, '')
    else:
        repository.set_workspace_state(ROOT_CAUSE_RULE_STATE_KEY, json.dumps(normalize_root_cause_rule(rule)))
    if hasattr(repository, 'try_add_log'):
        repository.try_add_log(username, 'nq_root_cause_rule', 'Non-Qualified Calls root cause suggestion rule updated.')
    return root_cause_rule(repository)


def list_root_causes(task_repository: Any) -> dict[str, Any]:
    """The root cause catalog (domains, root categories and root causes, in order) and its settings."""
    with task_repository.connection() as connection:
        catalog = _read_root_catalog(connection)
    return {**catalog, **root_cause_settings(task_repository)}


def root_category_of(catalog: dict[str, Any], cause: str) -> str:
    """The root category a root cause is mapped to (empty when it has none)."""
    item = next((entry for entry in catalog.get('causes') or [] if cause and entry['name'].casefold() == cause.casefold()), None)
    return str((item or {}).get('category') or '')


def domain_of(catalog: dict[str, Any], category: str, cause: str) -> str:
    """The domain of a root category, else of a root cause."""
    for plural, name in (('categories', category), ('causes', cause)):
        item = next((entry for entry in catalog.get(plural) or [] if name and entry['name'].casefold() == name.casefold()), None)
        if item and item.get('domain'):
            return item['domain']
    return ''


def dta_rule_values(task_repository: Any, catalog: dict[str, Any] | None = None) -> dict[str, dict[str, list[str]]]:
    """The domains, Root Categories and Root Causes of the catalog the DT Analyzer RCA rules give (enabled or not), each
    with the names of its rules: the catalog cannot remove them, nor rename the categories and causes, as the rules name
    them."""
    catalog = catalog or list_root_causes(task_repository)
    kinds = (('domains', 'domain'), ('categories', 'category'), ('causes', 'cause'))
    known = {plural: {item['name'].casefold(): item['name'] for item in catalog.get(plural) or []} for plural, _key in kinds}
    used: dict[str, dict[str, list[str]]] = {plural: {} for plural, _key in kinds}
    for rule in nq_dta_rca.load_rules(task_repository):
        result = nq_dta_rca.resolve_result(rule['category'], rule['cause'], catalog)
        for plural, key in kinds:
            name = known[plural].get(result[key].casefold())
            if name and rule['name'] not in used[plural].setdefault(name, []):
                used[plural][name].append(rule['name'])
    return used


def root_catalog_payload(task_repository: Any, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """The root cause catalog for the page, with the values the DT Analyzer RCA rules give (``dta_rules``)."""
    catalog = catalog or list_root_causes(task_repository)
    return {**catalog, 'dta_rules': dta_rule_values(task_repository, catalog)}


def _dta_rules_refusal(title: str, name: str, rules: list[str], action: str) -> str:
    """Why a value the DT Analyzer RCA rules give cannot be removed or renamed."""
    listed = ', '.join(f'"{rule}"' for rule in rules[:3]) + (f' and {len(rules) - 3} more' if len(rules) > 3 else '')
    return (f'The {title} "{name}" is given by the DT Analyzer RCA rule{"s" if len(rules) > 1 else ""} {listed}; '
            f'change {"those rules" if len(rules) > 1 else "the rule"} first to {action} it.')


def save_root_causes(task_repository: Any, catalog: Any, require_to_close: bool, username: str, *,
                     defaults: bool = False) -> dict[str, Any]:
    """Replace the root cause catalog; renamed values follow on every call, removed ones must be unused, and the values
    the DT Analyzer RCA rules give stay."""
    current = list_root_causes(task_repository)
    normalized = nq_catalog.normalize_root_catalog(catalog)
    used = dta_rule_values(task_repository, current)
    columns = {'domains': 'root_domain', 'categories': 'root_category', 'causes': 'root_cause'}
    titles = {'domains': 'domain', 'categories': 'Root Category', 'causes': 'Root Cause'}
    with task_repository.connection() as connection:
        for plural, column in columns.items():
            existing = {item['name'].casefold(): item['name'] for item in current[plural]}
            renamed = {item['previous'].casefold(): item['name'] for item in normalized[plural]
                       if item['previous'] and item['previous'].casefold() in existing}
            kept = {item['name'].casefold() for item in normalized[plural]} | set(renamed)
            for key, name in existing.items():
                if key in kept:
                    continue
                if connection.execute(f'SELECT COUNT(*) FROM {NQ_CALL_TRACKING_TABLE} WHERE {column} = ? COLLATE NOCASE',
                                      (name,)).fetchone()[0]:
                    raise ValueError(f'The {titles[plural]} "{name}" is in use; rename it or change the root cause of its calls first.')
            # The values the DT Analyzer RCA rules give stay, and so do the names of their categories and causes (the
            # categories and causes of a renamed domain follow it).
            names = {item['name'].casefold() for item in normalized[plural]}
            for name, rules in used[plural].items():
                key = name.casefold()
                if key in names or (key in renamed and (plural == 'domains' or nq_catalog.normalized_text(renamed[key])
                                                        == nq_catalog.normalized_text(name))):
                    continue
                raise ValueError(_dta_rules_refusal(titles[plural], name, rules, 'rename' if key in renamed else 'remove'))
            for key, name in renamed.items():
                if existing[key] != name:
                    connection.execute(f'UPDATE {NQ_CALL_TRACKING_TABLE} SET {column} = ? WHERE {column} = ? COLLATE NOCASE',
                                       (name, existing[key]))
        _write_root_catalog(connection, normalized)
        _refresh_root_domains(connection, normalized)
    task_repository.set_workspace_state(ROOT_CAUSE_SETTINGS_STATE_KEY, json.dumps({'require_to_close': bool(require_to_close)}))
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_root_causes', 'Non-Qualified Calls root cause catalog restored to the default '
                                    'catalog.' if defaults else 'Non-Qualified Calls root cause catalog updated.')
    return list_root_causes(task_repository)


# Who analysed and who reviewed each call, as the analysis workbooks name them (also before they had an account).
ANALYST_FIELD = 'analyst'
REVIEWER_FIELD = 'reviewer'
# The accounts every new deployment starts with (repository.py): first in the lists of assignees, apart and tagged.
DEFAULT_USERS = ('super', 'admin', 'demo')
# Temporary: accounts that change the Prioritization Rules without being admins (remove them when no longer needed).
PRIORITIZATION_EDITORS = ('EDANREC',)


def _analyst_rows(connection: Any, field: str = ANALYST_FIELD) -> list[Any]:
    """The Analyst (or the Reviewer) of every call of the workspace with its assignee and team, also of the calls whose
    CDR is not loaded yet (``loaded`` 0: their imported analysis waits for it)."""
    return connection.execute(
        f"SELECT f.call_key, f.value, COALESCE(t.assignee, '') AS assignee, COALESCE(t.team, '') AS team, "
        f"(f.call_key IN (SELECT call_key FROM {NQ_CALLS_TABLE}) OR f.call_key IN (SELECT sample_key FROM {NQ_CALLS_TABLE} "
        f"WHERE sample_key <> '')) AS loaded FROM {NQ_FIELD_VALUES_TABLE} f "
        f"LEFT JOIN {NQ_CALL_TRACKING_TABLE} t ON t.call_key = f.call_key WHERE f.field_key = ? AND f.value <> ''", (field,)).fetchall()


def _analyst_user(spellings: list[str], users: Any) -> str:
    """The only user named as the analyst, by its username or its first and last name (``users``: username → name):
    the whole name (Raj Kumar is rajkumar), then the first part of the user (Anudeep is anudeep.kumar or Anudeep
    Reddy), then the first part of both (Raj Kumar is raj.k)."""
    users = users if isinstance(users, dict) else {user: '' for user in users}
    whole = lambda value: nq_analyses.identity(value)
    first = lambda value: nq_analyses.identity(re.split(r'[\s._@-]+', str(value).strip())[0])
    for analyst_part, user_part in ((whole, whole), (whole, first), (first, first)):
        names = {analyst_part(spelling) for spelling in spellings} - {''}
        found = [user for user, name in users.items() if {user_part(user), user_part(name) if name else ''} & names]
        if len(found) == 1:
            return found[0]
    return ''


def analyst_assignments(task_repository: Any, users: Any = ()) -> dict[str, Any]:
    """Who analysed or reviewed the calls (also those whose CDR is not loaded yet): each person with the spellings they
    are written with (the same letters: Raj Kumar is Rajkumar), their calls as Analyst and as Reviewer, their analysed
    calls without an assignee and the suggested user (the only user named as them, or the assignee most of their
    analysed calls have)."""
    with task_repository.connection() as connection:
        rows = [(role, row) for role, field in (('analyst', ANALYST_FIELD), ('reviewer', REVIEWER_FIELD))
                for row in _analyst_rows(connection, field)]
    groups: dict[str, dict[str, Any]] = {}
    for role, row in rows:
        key = nq_analyses.identity(row['value'])
        group = groups.setdefault(key, {'spellings': Counter(), 'analyst': 0, 'reviewer': 0, 'unassigned': 0, 'assignees': Counter()})
        group['spellings'][str(row['value'])] += 1
        group[role] += 1
        if role == 'analyst':
            if row['assignee']:
                group['assignees'][str(row['assignee'])] += 1
            else:
                group['unassigned'] += 1
    people = []
    for key, group in groups.items():
        spellings = [spelling for spelling, _count in group['spellings'].most_common()]
        people.append({'key': key, 'name': spellings[0], 'spellings': spellings, 'analyst_calls': group['analyst'],
                       'reviewer_calls': group['reviewer'], 'unassigned': group['unassigned'],
                       'suggested': _analyst_user(spellings, users)
                       or (group['assignees'].most_common(1)[0][0] if group['assignees'] else '')})
    people.sort(key=lambda item: (-item['analyst_calls'] - item['reviewer_calls'], item['name'].casefold()))
    return {'people': people}


def assign_analysts(task_repository: Any, assignments: Any, username: str, users: set[str], *,
                    names: dict[str, str] | None = None, overwrite: bool = False, preview: bool = False) -> dict[str, Any]:
    """Link each analyst or reviewer to the user chosen for them (``assignments``: name key → user name). The calls
    they analysed get the user as assignee (only those without one unless ``overwrite``; every call keeps its team and
    the user joins the teams with members they are not one of), and their Analyst and Reviewer take the first and last
    name of the user (``names``: username → name) when it has them. The calls whose CDR is not loaded yet change as
    their imported analysis does (``waiting`` counts them). ``preview`` counts the calls and teams without changing
    anything."""
    lookup = {name.casefold(): name for name in users}
    names = names or {}
    chosen = {str(key): str(name).strip() for key, name in (assignments.items() if isinstance(assignments, dict) else []) if str(name).strip()}
    unknown = [name for name in chosen.values() if name.casefold() not in lookup]
    if unknown:
        raise ValueError(f'{unknown[0]} is not a user of this workspace.')
    options = list_options(task_repository)
    members = team_members(options)
    team_names = {team['name'].casefold(): team['name'] for team in options['teams']}
    defined = {field['key'] for field in list_fields(task_repository)}
    changes: dict[str, dict[str, Any]] = {}
    joins: set[tuple[str, str]] = set()
    per_person: dict[str, set[str]] = {}
    waiting: set[str] = set()
    counts: Counter = Counter()
    with task_repository.connection() as connection:
        rows = [(field, row) for field in (ANALYST_FIELD, REVIEWER_FIELD) for row in _analyst_rows(connection, field)]
    for field, row in rows:
        key = nq_analyses.identity(row['value'])
        if key not in chosen or field not in defined:
            continue
        user = lookup[chosen[key].casefold()]
        call_key = str(row['call_key'])
        change: dict[str, Any] = {}
        if field == ANALYST_FIELD:
            assignee, team = str(row['assignee']), team_names.get(str(row['team']).casefold(), str(row['team']))
            if assignee.casefold() != user.casefold() and (not assignee or overwrite):
                if team and members.get(team.casefold()) and user.casefold() not in members[team.casefold()]:
                    joins.add((team, user))
                change.update({'assignee': user, 'team': team})
                counts['assignees'] += 1
        # The Analyst or Reviewer takes the name of the account.
        if names.get(user) and str(row['value']) != names[user]:
            change['fields'] = {field: names[user]}
            counts[f'{field}_names'] += 1
        if change:
            merged = changes.setdefault(call_key, {})
            merged.update({name: value for name, value in change.items() if name != 'fields'})
            if 'fields' in change:
                merged['fields'] = {**merged.get('fields', {}), **change['fields']}
            per_person.setdefault(key, set()).add(call_key)
            if not row['loaded']:
                waiting.add(call_key)
    summary = {'calls': len(changes), 'assignees': counts['assignees'], 'analyst_names': counts[f'{ANALYST_FIELD}_names'],
               'reviewer_names': counts[f'{REVIEWER_FIELD}_names'], 'waiting': len(waiting),
               'people': {key: len(keys) for key, keys in per_person.items()},
               'joins': [{'team': team, 'user': user} for team, user in sorted(joins)]}
    if preview or not summary['calls']:
        return summary
    if joins:
        with task_repository.connection() as connection:
            connection.executemany(f'INSERT OR IGNORE INTO {NQ_TEAM_MEMBERS_TABLE} (team, username) VALUES (?, ?)', sorted(joins))
    # The loaded calls with the same changes, at once; the others as their imported analysis.
    batches: dict[str, list[str]] = {}
    for call_key, change in changes.items():
        if call_key not in waiting:
            batches.setdefault(json.dumps(change, sort_keys=True), []).append(call_key)
    for change, keys in batches.items():
        update_tracking(task_repository, keys, json.loads(change), username, users)
    if waiting:
        _update_waiting_calls(task_repository, {key: changes[key] for key in waiting}, username)
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_analyst_assignees', json.dumps(
            {'calls': summary['calls'], 'assignees': summary['assignees'], 'analyst_names': summary['analyst_names'],
             'reviewer_names': summary['reviewer_names'], 'waiting': summary['waiting'], 'overwrite': overwrite,
             'assignments': chosen}, ensure_ascii=False))
    return summary


def _update_waiting_calls(task_repository: Any, changes: dict[str, dict[str, Any]], username: str) -> None:
    """Change the imported analysis of calls whose CDR is not loaded yet as the import writes it (``changes``: call key
    → assignee, team and fields): their follow-up and fields with their history; their status follows the Status Rules."""
    keys = list(changes)
    default = untracked_status(task_repository)
    when = now_iso()
    with task_repository.connection() as connection:
        tracking = {str(row['call_key']): dict(row) for row in _rows_of_calls(connection, f'SELECT * FROM {NQ_CALL_TRACKING_TABLE}', keys)}
        stored = field_values(connection, keys)
        for call_key, change in changes.items():
            current = tracking.get(call_key) or {'status': default, 'status_mode': 'auto', 'team': '', 'assignee': '',
                                                 'root_domain': '', 'root_category': '', 'root_cause': ''}
            follow_up = {ref: change[ref] for ref in ('assignee', 'team') if ref in change and str(current.get(ref) or '') != change[ref]}
            if follow_up:
                row = {**current, **follow_up}
                connection.execute(
                    f'INSERT INTO {NQ_CALL_TRACKING_TABLE} (call_key, status, team, assignee, root_domain, root_category, root_cause, '
                    'status_mode, version, updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) ON CONFLICT(call_key) DO UPDATE SET '
                    'team = excluded.team, assignee = excluded.assignee, version = version + 1, updated_by = excluded.updated_by, '
                    'updated_at = excluded.updated_at',
                    (call_key, row['status'], row['team'], row['assignee'], row['root_domain'], row['root_category'], row['root_cause'],
                     row['status_mode'], username, when))
                for ref, value in follow_up.items():
                    _record_history(connection, call_key, ref, str(current.get(ref) or ''), value, username, when)
            for ref, value in (change.get('fields') or {}).items():
                connection.execute(
                    f'INSERT INTO {NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, ?) '
                    'ON CONFLICT(call_key, field_key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, '
                    'updated_at = excluded.updated_at', (call_key, ref, value, username, when))
                _record_history(connection, call_key, f'field:{ref}', stored.get(call_key, {}).get(ref, ''), value, username, when)
    recompute_statuses(task_repository, username, keys)


def apply_cause_categories(task_repository: Any, username: str, dry_run: bool = False) -> int:
    """Give every call with a root cause and no root category the category its cause is mapped to (``dry_run`` only
    counts them); the history, the domain and the Status Rules of the calls follow. Returns how many calls."""
    taxonomy = list_root_causes(task_repository)
    mapped = {item['name'].casefold(): item['category'] for item in taxonomy['causes'] if item.get('category')}
    if not mapped:
        return 0
    when = now_iso()
    changed: list[str] = []
    with task_repository.connection() as connection:
        rows = connection.execute(
            f"SELECT call_key, root_cause FROM {NQ_CALL_TRACKING_TABLE} WHERE root_category = '' AND root_cause <> ''").fetchall()
        for row in rows:
            category = mapped.get(str(row['root_cause']).casefold())
            if not category:
                continue
            changed.append(str(row['call_key']))
            if dry_run:
                continue
            connection.execute(
                f'UPDATE {NQ_CALL_TRACKING_TABLE} SET root_category = ?, root_domain = ?, version = version + 1, updated_by = ?, '
                'updated_at = ? WHERE call_key = ?',
                (category, domain_of(taxonomy, category, str(row['root_cause'])), username, when, row['call_key']))
            _record_history(connection, str(row['call_key']), 'root_category', '', category, username, when)
    if changed and not dry_run:
        recompute_statuses(task_repository, username, changed)
        if hasattr(task_repository, 'try_add_log'):
            task_repository.try_add_log(username, 'nq_root_causes',
                                        f'{len(changed)} Non-Qualified Calls took the root category of their root cause.')
    return len(changed)


def _refresh_root_domains(connection: Any, catalog: dict[str, Any]) -> None:
    """The stored domain of every call follows the domain of its root category (else of its root cause) as the
    catalog resolves it; a call whose values the catalog does not know keeps its domain."""
    catalog = nq_catalog.resolve_root_catalog(nq_catalog.stored_root_catalog(catalog))
    known = {plural: {item['name'].casefold() for item in catalog[plural]} for plural in ('categories', 'causes')}
    rows = connection.execute(
        f"SELECT call_key, root_domain, root_category, root_cause FROM {NQ_CALL_TRACKING_TABLE} "
        "WHERE root_category <> '' OR root_cause <> ''").fetchall()
    for row in rows:
        category, cause = str(row['root_category']), str(row['root_cause'])
        domain = domain_of(catalog, category, cause)
        if not domain and category.casefold() not in known['categories'] and cause.casefold() not in known['causes']:
            domain = str(row['root_domain'] or '')
        if domain != str(row['root_domain'] or ''):
            connection.execute(f'UPDATE {NQ_CALL_TRACKING_TABLE} SET root_domain = ? WHERE call_key = ?', (domain, row['call_key']))


def suggest_root_cause(call: Any, taxonomy: dict[str, Any], comments: str = '') -> dict[str, str] | None:
    """The domain, root category and root cause the CDR (or the comments) suggest, following the workspace rule."""
    return nq_rca.suggest_from_text(call, taxonomy, taxonomy.get('rule') or DEFAULT_ROOT_CAUSE_RULE, comments)


def _comment_texts(connection: Any, keys: list[str]) -> dict[str, str]:
    """The text of the comments of each call (deleted comments left out), for the root cause fallback."""
    texts: dict[str, list[str]] = {}
    for start in range(0, len(keys), 500):
        chunk = keys[start:start + 500]
        for row in connection.execute(
            f"SELECT call_key, body FROM {NQ_CALL_COMMENTS_TABLE} WHERE deleted_at = '' "
            f"AND call_key IN ({', '.join('?' for _ in chunk)}) ORDER BY id", chunk,
        ):
            texts.setdefault(str(row['call_key']), []).append(str(row['body']))
    return {key: '\n'.join(bodies) for key, bodies in texts.items()}




# ---------------------------------------------------------------------------
# NQ Call Status: rules on the phase fields, or a status set by hand
# ---------------------------------------------------------------------------
def status_rules(task_repository: Any) -> list[dict[str, Any]]:
    """The status rules of the workspace; conditions on fields or statuses that no longer exist are left out."""
    try:
        stored = json.loads(task_repository.get_workspace_state(STATUS_RULES_STATE_KEY) or '[]')
    except (TypeError, ValueError):
        stored = []
    statuses = {item['name'].casefold(): item['name'] for item in list_options(task_repository)['statuses']}
    known = nq_catalog.condition_fields(list_fields(task_repository))
    rules = []
    for rule in stored if isinstance(stored, list) else []:
        if not isinstance(rule, dict) or str(rule.get('status') or '').casefold() not in statuses:
            continue
        conditions = [condition for condition in rule.get('conditions') or []
                      if isinstance(condition, dict) and condition.get('field') in known
                      and condition.get('op') in nq_catalog.RULE_OPERATORS]
        if conditions:
            rules.append({'status': statuses[str(rule['status']).casefold()], 'conditions': conditions})
    return rules


def save_status_rules(task_repository: Any, rules: Any, username: str) -> list[dict[str, Any]]:
    statuses = [item['name'] for item in list_options(task_repository)['statuses']]
    normalized = nq_catalog.normalize_status_rules(rules, statuses, list_fields(task_repository))
    task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(normalized, ensure_ascii=False))
    changed = recompute_statuses(task_repository, username)
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_status_rules', f'Non-Qualified Calls status rules updated ({changed} calls changed).')
    return normalized


def _status_inputs(call: Any, stored: dict[str, str], fields: list[dict[str, Any]], tracking: dict[str, Any], attended: bool) -> dict[str, str]:
    """The values the status rules read for a call."""
    values = {field['key']: (stored.get(field['key'], '') if field['source'] == 'user' else derived_value(field, call) if call is not None else '')
              for field in fields if field['source'] in {'user', 'derived'}}
    values[ATTENDED_FIELD] = 'Yes' if attended else 'No'
    for ref in ('team', 'assignee', 'root_category', 'root_cause'):
        values[f'@{ref}'] = str(tracking.get(ref) or '')
    return values


def untracked_status(task_repository: Any, options: dict[str, list[dict[str, Any]]] | None = None) -> str:
    """The status of a call nobody has followed up: what the rules say without any value, else the first status."""
    options = options or list_options(task_repository)
    fallback = default_status(options)
    rules = status_rules(task_repository)
    return evaluate_status(rules, _status_inputs(None, {}, [], {}, False), fallback) if rules else fallback


def recompute_statuses(task_repository: Any, username: str, keys: list[str] | None = None,
                       when_of: dict[str, str] | None = None) -> int:
    """Set again the automatic status of the followed-up or commented calls; returns how many changed. ``when_of``
    dates the change of some calls (the date of the analyses imported for them)."""
    options = list_options(task_repository)
    fallback = default_status(options)
    rules = status_rules(task_repository)
    fields = list_fields(task_repository)
    needs_call = any(field['source'] == 'derived' for field in fields)
    when = now_iso()
    changed = 0
    with task_repository.connection() as connection:
        tracked = {str(row['call_key']): dict(row) for row in connection.execute(f'SELECT * FROM {NQ_CALL_TRACKING_TABLE}')}
        commented = {str(row[0]) for row in connection.execute(
            f"SELECT DISTINCT call_key FROM {NQ_CALL_COMMENTS_TABLE} WHERE deleted_at = ''")}
        candidates = set(tracked) | commented | {str(row[0]) for row in connection.execute(
            f'SELECT DISTINCT call_key FROM {NQ_FIELD_VALUES_TABLE}')}
        if keys is not None:
            candidates &= set(keys)
        candidates = [key for key in candidates if tracked.get(key, {}).get('status_mode', 'auto') != 'manual']
        stored = field_values(connection, candidates)
        rows: dict[str, Any] = {}
        if needs_call:
            for start in range(0, len(candidates), 500):
                chunk = candidates[start:start + 500]
                marks = ', '.join('?' for _ in chunk)
                for row in connection.execute(
                        f'SELECT * FROM {NQ_CALLS_TABLE} WHERE call_key IN ({marks}) OR sample_key IN ({marks})', [*chunk, *chunk]):
                    rows.setdefault(str(row['sample_key'] or row['call_key']), row)
                    rows.setdefault(str(row['call_key']), row)
        for key in candidates:
            tracking = tracked.get(key, {})
            attended = bool(tracking.get('updated_at')) or key in commented
            status = evaluate_status(rules, _status_inputs(rows.get(key), stored.get(key, {}), fields, tracking, attended), fallback)
            current = str(tracking.get('status') or '') or fallback
            if status == current:
                continue
            connection.execute(
                f"INSERT INTO {NQ_CALL_TRACKING_TABLE} (call_key, status, status_mode, version, updated_by, updated_at) "
                "VALUES (?, ?, 'auto', 1, '', '') ON CONFLICT(call_key) DO UPDATE SET status = excluded.status, version = version + 1",
                (key, status))
            _record_history(connection, key, 'status_auto', current, status, username, (when_of or {}).get(key) or when)
            changed += 1
    return changed


# ---------------------------------------------------------------------------
# Querying calls
# ---------------------------------------------------------------------------
# Operators and Vendors are indexed as the CDRs spell them and shown with their Operator
# and Vendor Maps labels, so filters, breakdowns, the table and exports use the mapped values.
MAPPED_FIELDS = ('operator', 'operator_vendor', 'vendor')
# The NetCheck RCA of the CDRs is written differently from one campaign to another (RF_Problems, RF Problems,
# RF problems, E2E traces required): the spellings of one value are indexed as they are and shown as one.
SPELLING_FIELDS = ('failure_classification', 'failure_category', 'failure_subcategory')
# The columns of the calls read through a map of ``_value_maps``.
MAPPED_COLUMNS = (*MAPPED_FIELDS, *SPELLING_FIELDS)


def _spelling_key(value: str) -> str:
    """What the spellings of one value share: its letters and digits, each word in singular (traces is trace; an
    acronym keeps its capital S: HTTPS is not HTTP)."""
    singular = lambda word: word[:-1] if len(word) > 3 and word.endswith('s') and not word.lower().endswith('ss') else word
    return ''.join(nq_analyses.identity(singular(word)) for word in re.split(r'[\W_]+', value)) or value


def unified_spellings(counts: dict[str, int]) -> dict[str, str]:
    """The spelling each value is shown with (``counts``: calls by value as written): the values with the same
    letters and digits, a word in singular or plural, are one, written with spaces for underscores and single
    spaces, as most of their calls."""
    clean = lambda value: re.sub(r'\s+', ' ', value.replace('_', ' ')).strip()
    groups: dict[str, Counter] = {}
    for value, count in counts.items():
        groups.setdefault(_spelling_key(value), Counter())[clean(value)] += count
    chosen = {key: min(forms.items(), key=lambda item: (-item[1], item[0]))[0] for key, forms in groups.items()}
    return {value: chosen[_spelling_key(value)] for value in counts}


_value_maps_cache: dict[tuple[str, str], dict[str, str]] = {}
_value_maps_guard = Lock()


def _value_maps(task_repository: Any) -> dict[str, str]:
    """For each mapped field, a JSON object from the indexed source values to their mapped labels.

    ``vendor_operator`` maps each source Operator_Vendor to its mapped Vendor_Operator, and the NetCheck RCA fields
    map each spelling to the one their value is shown with. The maps are kept until the indexed calls or the Operator
    and Vendor Maps change.
    """
    settings = task_repository.chart_mapping_settings()
    with task_repository.connection() as connection:
        stamp = tuple(connection.execute(f'SELECT COUNT(*), MAX(rowid) FROM {NQ_CALLS_TABLE}').fetchone())
    key = (_workspace_key(task_repository.db_path),
           hashlib.sha1(json.dumps([stamp, settings], sort_keys=True, default=str).encode()).hexdigest())
    with _value_maps_guard:
        if key in _value_maps_cache:
            return dict(_value_maps_cache[key])
    mapper = ValueMapper.from_settings(settings)
    maps = {}
    with task_repository.connection() as connection:
        for field in MAPPED_FIELDS:
            rows = connection.execute(f"SELECT DISTINCT {field} AS value FROM {NQ_CALLS_TABLE} WHERE {field} <> ''").fetchall()
            mapped = {str(row['value']): str(mapper.map(field_kind(field), row['value'])) for row in rows}
            maps[field] = json.dumps({source: label for source, label in mapped.items() if source != label})
            if field == 'operator_vendor':
                maps['vendor_operator'] = json.dumps({source: mapper.vendor_operators([label])[0]
                                                      for source, label in mapped.items()})
        for field in SPELLING_FIELDS:
            counts = {str(row[0]): int(row[1]) for row in connection.execute(
                f"SELECT {field}, COUNT(*) FROM {NQ_CALLS_TABLE} WHERE {field} <> '' GROUP BY {field} ORDER BY {field}")}
            maps[field] = json.dumps({source: spelling for source, spelling in unified_spellings(counts).items() if source != spelling})
    with _value_maps_guard:
        if len(_value_maps_cache) > 16:
            _value_maps_cache.clear()
        _value_maps_cache[key] = dict(maps)
    return maps


def _materialized(connection: Any, base: str, params: list[Any], scoped: bool) -> tuple[str, list[Any]]:
    """The calls of a choice of CDRs read once into a temporary table of the connection, for the several queries of
    one request (without a choice the latest versions table is already fast)."""
    if not scoped:
        return base, params
    connection.execute('DROP TABLE IF EXISTS temp.nq_scoped_calls')
    connection.execute(f'CREATE TEMP TABLE nq_scoped_calls AS {base}', params)
    return 'SELECT * FROM temp.nq_scoped_calls', []


def _scope(filters: dict[str, Any] | None) -> list[int]:
    """The CDRs chosen in the CDRs filter (none means every CDR)."""
    return [int(value) for value in _strings((filters or {}).get('datasets')) if value.lstrip('-').isdigit()]


# The columns of the latest version of each call that only change when the CDRs are indexed or the maps change.
LATEST_COLUMNS = ('dataset_id', 'source_row_id', 'call_key', 'service', 'nr_mode', *CALL_FIELDS, 'vendor_operator', 'last_cell_id',
                  'join_id', 'extra_json', 'nq_samples', 'latest_dataset_id', 'cdr_count', 'version_state')
LATEST_STATE_KEY = 'nq_call_latest_fingerprint'
_latest_locks: dict[str, Lock] = {}
_latest_guard = Lock()


def _latest_sql(maps: dict[str, str], dataset_ids: list[int] | None = None) -> tuple[str, list[Any]]:
    """The latest version of every call among the chosen CDRs (every CDR when none is chosen).

    A Final CDR comes before the Daily ones, then the CDR with the newest data. ``version_state``
    tells how the other CDRs see the call: ``qualified`` (the latest CDR has it Completed),
    ``not_in_final`` (only in Weekly or Daily CDRs while a Final CDR covers its campaign), ``newer`` (a newer
    CDR outside the chosen ones has it) or ``changed`` (its result or failure differs between CDRs).
    Speech calls count their Non-Qualified samples in ``nq_samples``.
    """
    columns = ', '.join(
        f'COALESCE((SELECT m.value FROM json_each(?) m WHERE m.key = c.{column}), c.{column}) AS {column}'
        if column in MAPPED_COLUMNS else f'c.{column}'
        for column in ('dataset_id', 'source_row_id', 'call_key', 'service', 'nr_mode', *CALL_FIELDS)
    )
    params: list[Any] = [maps[column] for column in ('dataset_id', 'source_row_id', 'call_key', 'service', 'nr_mode', *CALL_FIELDS)
                         if column in MAPPED_COLUMNS]
    # Vendor_Operator: the mapped Operator_Vendor the other way round.
    params.append(maps['vendor_operator'])
    scope = list(dict.fromkeys(int(value) for value in dataset_ids or []))
    scope_sql = f"WHERE n.dataset_id IN ({', '.join('?' for _ in scope)})" if scope else ''
    sql = f"""
        SELECT {columns},
               COALESCE((SELECT m.value FROM json_each(?) m WHERE m.key = c.operator_vendor), '') AS vendor_operator,
               {last_cell_sql('c.cell_id')} AS last_cell_id,
               c.join_id, c.extra_json, c.nq_samples,
               COALESCE(v.latest_dataset_id, c.dataset_id) AS latest_dataset_id,
               COALESCE(v.cdr_count, 1) AS cdr_count,
               CASE WHEN v.latest_is_nq = 0 THEN 'qualified'
                    WHEN v.in_final = 0 AND v.final_covered = 1 THEN 'not_in_final'
                    WHEN v.latest_dataset_id IS NOT NULL AND v.latest_dataset_id <> c.dataset_id THEN 'newer'
                    WHEN v.changed = 1 THEN 'changed' ELSE '' END AS version_state
        FROM (
            SELECT n.*, COUNT(*) OVER (PARTITION BY n.call_key, n.dataset_id) AS nq_samples,
                   ROW_NUMBER() OVER (PARTITION BY n.call_key
                                      ORDER BY s.combined_rank DESC, s.stage_rank DESC, s.data_date DESC, n.dataset_id DESC,
                                               n.start_time, n.rowid) AS rn
            FROM {NQ_CALLS_TABLE} n JOIN {NQ_CALL_SOURCES_TABLE} s ON s.dataset_id = n.dataset_id
            {scope_sql}
        ) c
        LEFT JOIN {NQ_CALL_VERSIONS_TABLE} v ON v.call_key = c.call_key
        WHERE c.rn = 1
    """
    return sql, [*params, *scope]


def _latest_fingerprint(connection: Any, maps: dict[str, str]) -> str:
    """What the latest versions depend on: the indexed CDRs, their calls and the Operator and Vendor maps."""
    sources = [tuple(row) for row in connection.execute(
        f'SELECT dataset_id, revision, stage_rank, data_date, synced_at, combined_rank FROM {NQ_CALL_SOURCES_TABLE} '
        'ORDER BY dataset_id')]
    calls = tuple(connection.execute(f'SELECT COUNT(*), MAX(rowid) FROM {NQ_CALLS_TABLE}').fetchone())
    payload = json.dumps([INDEX_VERSION, sources, calls, maps], sort_keys=True, default=str)
    return hashlib.sha1(payload.encode()).hexdigest()


def refresh_latest_calls(task_repository: Any, *, force: bool = False, maps: dict[str, str] | None = None) -> bool:
    """Rebuild the latest version of every call when the indexed CDRs or the maps changed; returns whether it did."""
    maps = maps or _value_maps(task_repository)
    key = _workspace_key(task_repository.db_path)
    with _latest_guard:
        lock = _latest_locks.setdefault(key, Lock())
    with lock:
        with task_repository.connection() as connection:
            fingerprint = _latest_fingerprint(connection, maps)
            stored = connection.execute('SELECT value FROM workspace_state WHERE key = ?', (LATEST_STATE_KEY,)).fetchone()
        if not force and stored and str(stored[0]) == fingerprint:
            return False
        sql, params = _latest_sql(maps)
        columns = ', '.join(LATEST_COLUMNS)
        with task_repository.connection() as connection:
            connection.execute(f'DELETE FROM {NQ_CALL_LATEST_TABLE}')
            connection.execute(f'INSERT INTO {NQ_CALL_LATEST_TABLE} ({columns}) SELECT {columns} FROM ({sql})', params)
            connection.execute('INSERT INTO workspace_state (key, value) VALUES (?, ?) '
                               'ON CONFLICT(key) DO UPDATE SET value = excluded.value', (LATEST_STATE_KEY, fingerprint))
    return True


def _latest_ready(task_repository: Any, maps: dict[str, str]) -> bool:
    """Whether the calls are read from the latest versions table: rebuilt first when needed, except while the
    CDRs are being indexed, when the previous versions stay until the indexing ends."""
    job = nq_index_job(task_repository.db_path)
    if job and job['status'] in {'queued', 'processing'}:
        with task_repository.connection() as connection:
            return connection.execute('SELECT 1 FROM workspace_state WHERE key = ?', (LATEST_STATE_KEY,)).fetchone() is not None
    refresh_latest_calls(task_repository, maps=maps)
    return True


# ---------------------------------------------------------------------------
# DT Analyzer RCA (see nq_dta_rca)
# ---------------------------------------------------------------------------
# The columns of an indexed row its rules read, besides its inputs.
_DTA_COLUMNS = ('dataset_id', 'source_row_id', 'service', 'operator', 'latitude', 'longitude', 'cell_id', *nq_dta_rca.CALL_INPUTS,
                *nq_dta_rca.FAILURE_TEXT_FIELDS, 'rca_inputs_json')
# The result of the row of a call, as the calls query reads it (``s`` the call row): what it learned from the analysts,
# else what its rule gives.
DTA_JSON_SQL = (f"COALESCE((SELECT json_object('dta_domain', l.domain, 'dta_category', l.category, 'dta_cause', l.cause, "
                f"'dta_rule', d.rule, 'dta_rule_key', d.rule_key, 'dta_evidence', l.evidence, 'dta_learned', 'Yes') "
                f"FROM {NQ_DTA_LEARNED_TABLE} l JOIN {NQ_DTA_RESULTS_TABLE} d ON d.dataset_id = l.dataset_id AND d.source_row_id = l.source_row_id "
                "WHERE l.dataset_id = s.dataset_id AND l.source_row_id = s.source_row_id), "
                f"(SELECT json_object('dta_domain', d.domain, 'dta_category', d.category, 'dta_cause', d.cause, "
                f"'dta_rule', d.rule, 'dta_rule_key', d.rule_key, 'dta_evidence', d.evidence) FROM {NQ_DTA_RESULTS_TABLE} d "
                "WHERE d.dataset_id = s.dataset_id AND d.source_row_id = s.source_row_id), '{}')")


def _sync_lock(task_repository: Any) -> Lock:
    with _sync_locks_guard:
        return _sync_locks.setdefault(str(task_repository.db_path), Lock())


def _dta_network_signature(task_repository: Any) -> str:
    """The network the DT Analyzer RCA reads around the calls: the Network Inventory snapshot of each network (with its
    revision) and the networks serving each operator; empty without an inventory."""
    from src.modules.inventory_insights import snapshot_choice
    from src.modules.network_inventory import dataset_revision, inventory_datasets, list_inventory_snapshots
    from src.modules.serving_cells import load_serving_networks

    try:
        datasets = inventory_datasets(task_repository)
        selection = snapshot_choice(list_inventory_snapshots(task_repository, datasets))
    except Exception:  # noqa: BLE001 - a workspace without inventories reads no network around its calls.
        return ''
    if not selection:
        return ''
    revisions = {int(row['id']): dataset_revision(row) for row in datasets}
    return json.dumps([sorted((family, dataset_id, revisions.get(dataset_id, '')) for family, dataset_id in selection.items()),
                       load_serving_networks(task_repository)], sort_keys=True, default=str)


def _dta_context(task_repository: Any, rows: list[Any], network: bool) -> dict[tuple[int, int], dict[str, Any]]:
    """What the rules read of each row beyond its CDR: its ping-pongs, from the cells of the call, and with a Network
    Inventory (``network``) the network around it (ran_context), as the Map of the call shows them."""
    from src.modules import nq_call_map, ran_context
    from src.modules.serving_cells import load_serving_networks, serving_families

    config = load_serving_networks(task_repository)
    families: dict[str, tuple[str, ...]] = {}
    for row in rows:
        operator = _text(row['operator'])
        if operator not in families:
            families[operator] = tuple(serving_families(operator, config))
    index = None
    if network and rows:
        cells, _snapshots = nq_call_map.inventory_cells(task_repository, tuple(dict.fromkeys(item for value in families.values() for item in value)))
        index = ran_context.ran_index(cells) if not cells.empty else None
    max_distance = float(config.get('max_distance_km') or 30.0)
    context = {}
    for row in rows:
        try:
            inputs = json.loads(row['rca_inputs_json'] or '{}') or {}
        except (TypeError, ValueError):
            inputs = {}
        steps = nq_call_map.trace_cells(inputs.get('cell_trace'), inputs.get('cell_pcis'), row['cell_id'])
        values: dict[str, Any] = {'ping_pong': len(ran_context.ping_pongs([step['cell'] for step in steps]))} if steps else {}
        if index is not None:
            values.update(ran_context.call_context(
                index, families[_text(row['operator'])], steps, nq_call_map._position(row['latitude'], row['longitude']),
                nq_call_map._position(inputs.get('end_latitude'), inputs.get('end_longitude')), max_distance))
        if values:
            context[(int(row['dataset_id']), int(row['source_row_id']))] = values
    return context


def dta_rca_fingerprint(task_repository: Any) -> str:
    """What the DT Analyzer RCA of the calls depends on: its rules, the Root Cause Catalog and the network around the
    calls (the Network Inventory and the networks serving each operator)."""
    return nq_dta_rca.fingerprint(nq_dta_rca.load_rules(task_repository), list_root_causes(task_repository),
                                  _dta_network_signature(task_repository))


def refresh_dta_rca(task_repository: Any, *, force: bool = False, wait: bool = True) -> int | None:
    """Calculate the DT Analyzer RCA of the indexed rows without one, or of every row when its rules or the Root
    Cause Catalog changed (or with ``force``); returns the rows calculated, or None when the calls are being indexed and
    ``wait`` is not set (the indexing calculates them when it ends)."""
    lock = _sync_lock(task_repository)
    if not lock.acquire(blocking=wait):
        return None
    try:
        return _refresh_dta_rca(task_repository, force=force)
    finally:
        lock.release()


def _refresh_dta_rca(task_repository: Any, *, force: bool = False) -> int:
    """refresh_dta_rca, the indexing lock taken."""
    rules = nq_dta_rca.load_rules(task_repository)
    taxonomy = list_root_causes(task_repository)
    network = _dta_network_signature(task_repository)
    fingerprint = nq_dta_rca.fingerprint(rules, taxonomy, network)
    everything = force or str(task_repository.get_workspace_state(nq_dta_rca.FINGERPRINT_STATE_KEY) or '') != fingerprint
    missing = '' if everything else (f' WHERE NOT EXISTS (SELECT 1 FROM {NQ_DTA_RESULTS_TABLE} r '
                                     'WHERE r.dataset_id = c.dataset_id AND r.source_row_id = c.source_row_id)')
    with task_repository.connection() as connection:
        rows = connection.execute(f"SELECT {', '.join(f'c.{column}' for column in _DTA_COLUMNS)} FROM {NQ_CALLS_TABLE} c{missing}").fetchall()
    compiled = nq_dta_rca.compile_rules(rules, taxonomy)
    context = _dta_context(task_repository, rows, bool(network))
    results = []
    for row in rows:
        try:
            inputs = json.loads(row['rca_inputs_json'] or '{}') or {}
        except (TypeError, ValueError):
            inputs = {}
        inputs.update(context.get((int(row['dataset_id']), int(row['source_row_id'])), {}))
        found = nq_dta_rca.evaluate(compiled, row, inputs) or {}
        results.append((int(row['dataset_id']), int(row['source_row_id']), found.get('rule', ''), found.get('rule_key', ''),
                        found.get('domain', ''), found.get('category', ''), found.get('cause', ''), found.get('evidence', '')))
    with task_repository.connection() as connection:
        if everything:
            connection.execute(f'DELETE FROM {NQ_DTA_RESULTS_TABLE}')
        else:
            # The rows the index no longer has (an index rebuilt from the CDRs).
            connection.execute(f'DELETE FROM {NQ_DTA_RESULTS_TABLE} WHERE NOT EXISTS (SELECT 1 FROM {NQ_CALLS_TABLE} c '
                               f'WHERE c.dataset_id = {NQ_DTA_RESULTS_TABLE}.dataset_id '
                               f'AND c.source_row_id = {NQ_DTA_RESULTS_TABLE}.source_row_id)')
        connection.executemany(f'INSERT OR REPLACE INTO {NQ_DTA_RESULTS_TABLE} '
                               '(dataset_id, source_row_id, rule, rule_key, domain, category, cause, evidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                               results)
        connection.execute('INSERT INTO workspace_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                           (nq_dta_rca.FINGERPRINT_STATE_KEY, fingerprint))
    _refresh_dta_learning(task_repository)
    return len(results)


def _dta_learning_fingerprint(task_repository: Any) -> str:
    """What the root causes learned depend on: whether it learns, the results of the rules, the decisions of the
    analysts and the indexed CDRs (a workspace whose Reindex removed what it learned, before they were part of it,
    learns again once)."""
    learn = nq_dta_rca.load_settings(task_repository)['learn']
    if not learn:
        return 'off'
    with task_repository.connection() as connection:
        decisions = connection.execute(
            f"SELECT call_key, root_category, root_cause FROM {NQ_CALL_TRACKING_TABLE} "
            "WHERE root_category <> '' OR root_cause <> '' ORDER BY call_key").fetchall()
        results = tuple(connection.execute(f'SELECT COUNT(*), MAX(rowid) FROM {NQ_DTA_RESULTS_TABLE}').fetchone())
        sources = connection.execute(
            f'SELECT dataset_id, revision, synced_at FROM {NQ_CALL_SOURCES_TABLE} ORDER BY dataset_id').fetchall()
    payload = json.dumps([str(task_repository.get_workspace_state(nq_dta_rca.FINGERPRINT_STATE_KEY) or ''), results,
                          [tuple(row) for row in decisions], [tuple(row) for row in sources]], default=str)
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()


def _refresh_dta_learning(task_repository: Any) -> int:
    """The root causes the DT Analyzer RCA learns from the decisions of the analysts (none while it does not learn):
    a row takes the Root Category and Cause most of the other calls of its pattern (rule, service and failure of the
    provider) were given, when at least LEARNING_MIN_DECISIONS of them and more than half agree; returns the rows that
    learned. The indexing lock is taken."""
    fingerprint = _dta_learning_fingerprint(task_repository)
    if str(task_repository.get_workspace_state(nq_dta_rca.LEARNED_FINGERPRINT_STATE_KEY) or '') == fingerprint:
        with task_repository.connection() as connection:
            return int(connection.execute(f'SELECT COUNT(*) FROM {NQ_DTA_LEARNED_TABLE}').fetchone()[0])
    learned: list[tuple[Any, ...]] = []
    if fingerprint != 'off':
        taxonomy = list_root_causes(task_repository)
        with task_repository.connection() as connection:
            rows = connection.execute(f"""
                SELECT c.dataset_id, c.source_row_id, c.call_key, c.sample_key, c.service, c.failure_classification,
                       c.failure_category, c.failure_subcategory, d.rule, d.rule_key, d.category AS rule_category, d.cause AS rule_cause
                FROM {NQ_CALLS_TABLE} c
                JOIN {NQ_DTA_RESULTS_TABLE} d ON d.dataset_id = c.dataset_id AND d.source_row_id = c.source_row_id""").fetchall()
            decisions = {str(row[0]): (str(row[1] or ''), str(row[2] or '')) for row in connection.execute(
                f"SELECT call_key, root_category, root_cause FROM {NQ_CALL_TRACKING_TABLE} WHERE root_category <> '' OR root_cause <> ''")}
        # The calls (a Speech sample by its own key) of each pattern the analysts decided, by the choice they made.
        patterns: dict[tuple[str, str, str], dict[tuple[str, str], set[str]]] = {}
        for row in rows:
            key = str(row['sample_key'] or row['call_key'])
            if key in decisions:
                patterns.setdefault(nq_dta_rca.learning_pattern(str(row['rule_key']), row), {}).setdefault(decisions[key], set()).add(key)
        for row in rows:
            choices = patterns.get(nq_dta_rca.learning_pattern(str(row['rule_key']), row))
            found = nq_dta_rca.learned_choice(choices, str(row['sample_key'] or row['call_key'])) if choices else None
            if found is None:
                continue
            (category, cause), count, total = found
            if (category, cause) == (str(row['rule_category'] or ''), str(row['rule_cause'] or '')):
                continue
            learned.append((int(row['dataset_id']), int(row['source_row_id']), domain_of(taxonomy, category, cause), category, cause,
                            nq_dta_rca.learned_evidence(str(row['rule']), row, count, total), count))
    with task_repository.connection() as connection:
        connection.execute(f'DELETE FROM {NQ_DTA_LEARNED_TABLE}')
        connection.executemany(f'INSERT OR REPLACE INTO {NQ_DTA_LEARNED_TABLE} '
                               '(dataset_id, source_row_id, domain, category, cause, evidence, decisions) VALUES (?, ?, ?, ?, ?, ?, ?)', learned)
        connection.execute('INSERT INTO workspace_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                           (nq_dta_rca.LEARNED_FINGERPRINT_STATE_KEY, fingerprint))
    return len(learned)


def _dta_ready(task_repository: Any) -> None:
    """The DT Analyzer RCA calculated again before the calls are read when its rules or the Root Cause Catalog
    changed, and what it learns when the decisions of the analysts changed, unless the calls are being indexed."""
    if str(task_repository.get_workspace_state(nq_dta_rca.FINGERPRINT_STATE_KEY) or '') != dta_rca_fingerprint(task_repository):
        refresh_dta_rca(task_repository, wait=False)
    elif str(task_repository.get_workspace_state(nq_dta_rca.LEARNED_FINGERPRINT_STATE_KEY) or '') != _dta_learning_fingerprint(task_repository):
        lock = _sync_lock(task_repository)
        if lock.acquire(blocking=False):
            try:
                _refresh_dta_learning(task_repository)
            finally:
                lock.release()


def dta_rules_payload(task_repository: Any) -> dict[str, Any]:
    """The rules of the DT Analyzer RCA of the workspace, the default ones, the Non-Qualified Calls each rule explains
    and whether the calls still wait for their calculation (while the CDRs are being indexed)."""
    _dta_ready(task_repository)
    rules = nq_dta_rca.load_rules(task_repository)
    pending = str(task_repository.get_workspace_state(nq_dta_rca.FINGERPRINT_STATE_KEY) or '') != dta_rca_fingerprint(task_repository)
    with task_repository.connection() as connection:
        learned = int(connection.execute(
            f"SELECT COUNT(*) FROM {NQ_CALL_LATEST_TABLE} c JOIN {NQ_DTA_LEARNED_TABLE} l "
            "ON l.dataset_id = c.dataset_id AND l.source_row_id = c.source_row_id WHERE c.version_state <> 'qualified'").fetchone()[0])
    return {'rules': rules, 'defaults': nq_dta_rca.default_rules(), 'counts': dta_rule_counts(task_repository), 'pending': pending,
            'settings': nq_dta_rca.load_settings(task_repository), 'learned': learned,
            'learning_min_decisions': nq_dta_rca.LEARNING_MIN_DECISIONS}


def dta_rule_counts(task_repository: Any) -> dict[str, int]:
    """The Non-Qualified Calls (the latest version of each one) each rule of the DT Analyzer RCA explains."""
    with task_repository.connection() as connection:
        return {str(row[0]): int(row[1]) for row in connection.execute(
            f"SELECT d.rule, COUNT(*) FROM {NQ_CALL_LATEST_TABLE} l JOIN {NQ_DTA_RESULTS_TABLE} d "
            "ON d.dataset_id = l.dataset_id AND d.source_row_id = l.source_row_id "
            "WHERE l.version_state <> 'qualified' GROUP BY d.rule")}


# The NQ Prioritization of each call (a Speech sample shows that of its call): its scoring impact, repetitions and rule.
PRIORITY_COLUMNS_SQL = (
    "p.impact_points AS impact_points, COALESCE(p.impact_level, '') AS impact_level, "
    "COALESCE(p.impact_state, '') AS impact_state, COALESCE(p.impact_kpis, '') AS impact_kpis, "
    "COALESCE(p.impact_json, '[]') AS impact_json, COALESCE(p.place_label, '') AS place_label, "
    "p.repetitions AS repetitions, p.repeated_campaigns AS repeated_campaigns, COALESCE(p.repeated, '') AS repeated, "
    "COALESCE(p.prioritization, '') AS prioritization, COALESCE(p.priority_rule, '') AS priority_rule, "
    "COALESCE(p.suggested_priority, '') AS suggested_priority, COALESCE(p.queue, '') AS queue, p.queue_step AS queue_step, "
    "COALESCE(p.queue_list, '') AS queue_list, p.expected_points AS expected_points, "
    "COALESCE(p.expected_campaign, '') AS expected_campaign, COALESCE(p.cluster_key, '') AS cluster_key, "
    "p.cluster_size AS cluster_size"
)


def _base_sql(default: str, task_repository: Any, dataset_ids: list[int] | None = None) -> tuple[str, list[Any]]:
    """One row per call with its follow-up: the version of the most recent CDR among the chosen ones.

    Without a choice of CDRs the latest versions come from the ``nq_call_latest`` table; the follow-up (status,
    team, assignee, root cause, comments, fields and RCA results) is always read as it is now.
    """
    maps = _value_maps(task_repository)
    _dta_ready(task_repository)
    scope = list(dict.fromkeys(int(value) for value in dataset_ids or []))
    if not scope and _latest_ready(task_repository, maps):
        source, source_params = NQ_CALL_LATEST_TABLE, []
    else:
        latest, source_params = _latest_sql(maps, scope)
        source = f'({latest})'
    sql = f"""
        SELECT s.*,
               COALESCE(NULLIF(t.status, ''), ?) AS status,
               COALESCE(t.team, '') AS team,
               COALESCE(t.assignee, '') AS assignee,
               COALESCE(t.root_domain, '') AS root_domain,
               COALESCE(t.root_category, '') AS root_category,
               COALESCE(t.root_cause, '') AS root_cause,
               COALESCE(t.status_mode, 'auto') AS status_mode,
               COALESCE(t.version, 0) AS version,
               COALESCE(t.updated_by, '') AS updated_by,
               COALESCE(t.updated_at, '') AS updated_at,
               (SELECT COUNT(*) FROM {NQ_CALL_COMMENTS_TABLE} m WHERE m.call_key = s.call_key AND m.deleted_at = '') AS comment_count,
               (SELECT json_group_object(f.field_key, f.value) FROM {NQ_FIELD_VALUES_TABLE} f
                WHERE f.call_key = s.call_key AND f.value <> '') AS field_values_json,
               COALESCE((SELECT r.values_json FROM {NQ_RCA_RESULTS_TABLE} r
                         WHERE s.join_id <> '' AND r.join_id = lower(s.join_id)), '{{}}') AS rca_json,
               {DTA_JSON_SQL} AS dta_json,
               {PRIORITY_COLUMNS_SQL}
        FROM {source} s
        LEFT JOIN {NQ_CALL_TRACKING_TABLE} t ON t.call_key = s.call_key
        LEFT JOIN {nq_prioritization.PRIORITY_TABLE} p ON p.call_key = s.call_key
    """
    # Placeholders in order: the default status (select list), then those of the latest versions (maps and CDRs).
    return sql, [default, *source_params]


def _sample_sql(default: str, task_repository: Any) -> tuple[str, list[Any]]:
    """The Speech samples with their own follow-up, as call rows keyed by their ``sample_key``."""
    maps = _value_maps(task_repository)
    _dta_ready(task_repository)
    columns = ', '.join(
        f'COALESCE((SELECT m.value FROM json_each(?) m WHERE m.key = c.{column}), c.{column}) AS {column}'
        if column in MAPPED_COLUMNS else f'c.{column}'
        for column in ('dataset_id', 'source_row_id', 'service', 'nr_mode', *CALL_FIELDS)
    )
    params = [maps[column] for column in ('dataset_id', 'source_row_id', 'service', 'nr_mode', *CALL_FIELDS) if column in MAPPED_COLUMNS]
    sql = f"""
        SELECT {columns}, c.sample_key AS call_key, c.call_key AS parent_key, c.sample_id, c.join_id, c.extra_json,
               1 AS nq_samples, '' AS vendor_operator, {last_cell_sql('c.cell_id')} AS last_cell_id,
               COALESCE(NULLIF(t.status, ''), ?) AS status, COALESCE(t.team, '') AS team,
               COALESCE(t.assignee, '') AS assignee, COALESCE(t.root_domain, '') AS root_domain,
               COALESCE(t.root_category, '') AS root_category, COALESCE(t.root_cause, '') AS root_cause,
               COALESCE(t.status_mode, 'auto') AS status_mode, COALESCE(t.version, 0) AS version,
               COALESCE(t.updated_by, '') AS updated_by, COALESCE(t.updated_at, '') AS updated_at,
               (SELECT COUNT(*) FROM {NQ_CALL_COMMENTS_TABLE} m WHERE m.call_key = c.sample_key AND m.deleted_at = '') AS comment_count,
               c.dataset_id AS latest_dataset_id, 1 AS cdr_count, '' AS version_state,
               (SELECT json_group_object(f.field_key, f.value) FROM {NQ_FIELD_VALUES_TABLE} f
                WHERE f.call_key = c.sample_key AND f.value <> '') AS field_values_json,
               COALESCE((SELECT r.values_json FROM {NQ_RCA_RESULTS_TABLE} r
                         WHERE c.join_id <> '' AND r.join_id = lower(c.join_id)), '{{}}') AS rca_json,
               {DTA_JSON_SQL.replace('s.dataset_id', 'c.dataset_id').replace('s.source_row_id', 'c.source_row_id')} AS dta_json,
               {PRIORITY_COLUMNS_SQL}
        FROM {NQ_CALLS_TABLE} c
        JOIN {NQ_CALL_SOURCES_TABLE} s ON s.dataset_id = c.dataset_id
        LEFT JOIN {NQ_CALL_TRACKING_TABLE} t ON t.call_key = c.sample_key
        LEFT JOIN {nq_prioritization.PRIORITY_TABLE} p ON p.call_key = c.call_key
        WHERE c.sample_key <> ''
    """
    return sql, [*params, default]


def _strings(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(str(value) for value in values if value is not None))


# The Filters panel is shared: every user of the workspace finds the last selection, in any session.
SAVED_FILTERS_STATE_KEY = 'nq_calls_filters'
# NQ Calls in Scope Only (in_scope): only the calls in the scope of the team, as the Out of Scope settings of the NQ
# Prioritization tell them apart, in every list, panel, chart, count and share.
FLAG_FILTERS = ('open_only', 'mine', 'without_comments', 'in_scope')


def normalize_saved_filters(filters: Any) -> dict[str, Any]:
    """The known filters of a selection: value lists, flags and the search text."""
    filters = filters if isinstance(filters, dict) else {}
    saved: dict[str, Any] = {}
    for field in (*FIELD_FILTERS, *TRACKING_FILTERS, *TYPED_FILTERS, *EXTRA_FILTERS, 'datasets', 'version'):
        values = _strings(filters.get(field))[:5000]
        if values:
            saved[field] = values
    fields = filters.get('fields') if isinstance(filters.get('fields'), dict) else {}
    chosen = {str(key): _strings(values)[:5000] for key, values in fields.items() if _strings(values)}
    if chosen:
        saved['fields'] = chosen
    columns = filters.get('columns') if isinstance(filters.get('columns'), dict) else {}
    chosen_columns = {str(key): _strings(values)[:MAX_COLUMN_FILTER_VALUES] for key, values in columns.items()
                      if column_filter_sql(str(key)) and _strings(values)}
    if chosen_columns:
        saved['columns'] = chosen_columns
    saved.update({flag: True for flag in FLAG_FILTERS if filters.get(flag) is True})
    search = str(filters.get('search') or '').strip()[:200]
    if search:
        saved['search'] = search
    return saved


def saved_filters(repository: Any) -> dict[str, Any]:
    try:
        return normalize_saved_filters(json.loads(repository.get_workspace_state(SAVED_FILTERS_STATE_KEY) or '{}'))
    except (TypeError, ValueError):
        return {}


def save_filters(repository: Any, filters: Any) -> dict[str, Any]:
    saved = normalize_saved_filters(filters)
    repository.set_workspace_state(SAVED_FILTERS_STATE_KEY, json.dumps(saved, ensure_ascii=False, sort_keys=True))
    return saved


CALL_TYPE_SQL = ("CASE WHEN service = 'data' THEN 'Data' WHEN instr(lower(test_name), 'whatsapp') > 0 "
                 "THEN 'WhatsApp' ELSE 'Classic' END")
START_SQL = "replace(substr(start_time, 1, 19), 'T', ' ')"
_AGE_DAYS = f"(julianday('now', 'localtime') - julianday({START_SQL}))"
AGE_SQL = {
    'Under 7 days': f'{_AGE_DAYS} < 7', '7–30 days': f'({_AGE_DAYS} >= 7 AND {_AGE_DAYS} < 30)',
    '30–90 days': f'({_AGE_DAYS} >= 30 AND {_AGE_DAYS} < 90)', 'Over 90 days': f'{_AGE_DAYS} >= 90',
    'Unknown date': f'julianday({START_SQL}) IS NULL',
}


def period_bounds(value: str) -> tuple[str, str] | None:
    """Start and end (excluded) of a timeline period such as "month:2026-07" or "week:2026-W28"."""
    from datetime import timedelta

    granularity, _, label = str(value).partition(':')
    try:
        if granularity == 'week':
            year, week = label.split('-W')
            start = datetime.fromisocalendar(int(year), int(week), 1)
            end = start + timedelta(days=7)
        elif granularity == 'month':
            year, month = (int(part) for part in label.split('-'))
            start = datetime(year, month, 1)
            end = datetime(year + (month == 12), month % 12 + 1, 1)
        elif granularity == 'quarter':
            year, quarter = label.split('-Q')
            month = (int(quarter) - 1) * 3 + 1
            start = datetime(int(year), month, 1)
            end = datetime(int(year) + (month == 10), (month + 2) % 12 + 1, 1)
        elif granularity == 'year':
            start, end = datetime(int(label), 1, 1), datetime(int(label) + 1, 1, 1)
        else:
            return None
    except (TypeError, ValueError):
        return None
    return start.strftime('%Y-%m-%d %H:%M:%S'), end.strftime('%Y-%m-%d %H:%M:%S')


_key_filters_cache: dict[tuple[str, str], tuple[str, ...]] = {}
_key_filters_guard = Lock()


def _mapped_filters(task_repository: Any, filters: dict[str, Any]) -> dict[str, Any]:
    """The Operator and Vendor values of a selection as the Operator and Vendor Maps show them, so a source spelling
    saved before (for example Vodafone SM) selects its mapped label (VF SM), and the NetCheck RCA ones as they are
    shown (RF_Problems selects RF Problems)."""
    if any(_strings(filters.get(field)) for field in (*MAPPED_FIELDS, 'vendor_operator')):
        mapper = ValueMapper.from_repository(task_repository)
        filters = {**filters, **{field: list(dict.fromkeys(str(mapper.map(field_kind(field), value)) for value in _strings(filters.get(field))))
                                 for field in (*MAPPED_FIELDS, 'vendor_operator') if _strings(filters.get(field))}}
    if any(_strings(filters.get(field)) for field in SPELLING_FIELDS):
        maps = _value_maps(task_repository)
        filters = {**filters, **{field: list(dict.fromkeys(json.loads(maps[field]).get(value, value) for value in _strings(filters.get(field))))
                                 for field in SPELLING_FIELDS if _strings(filters.get(field))}}
    return filters


def _resolve_key_filters(task_repository: Any, filters: dict[str, Any]) -> dict[str, Any]:
    """Turn the filters computed per call (root cause counting suggestions, eNB/gNB, the stalled calls) into call keys,
    with the Operator, Vendor and NetCheck RCA values as they are shown."""
    filters = _call_key_filters(task_repository, _mapped_filters(task_repository, filters))
    excluded = excluded_operators(task_repository)
    if excluded:
        # The operators the Operator Maps exclude are left out of every list, count and export.
        filters = {**filters, '_excluded_operators': excluded}
    if filters.get('in_scope') is True:
        # NQ Calls in Scope Only: the calls out of scope (their region, operator or NR Mode · operator pair) count nowhere.
        filters = {**filters, '_scope_sql': nq_prioritization.scope_sql(task_repository)}
    states = _strings(filters.get('state'))
    if 'open' in states:
        # Open: the attended calls not closed, in neither the first status nor a closed one.
        statuses = list_options(task_repository)['statuses']
        filters = {**filters, '_first_status': statuses[0]['name'] if statuses else ''}
    return _stalled_filter(task_repository, filters) if 'stalled' in states else filters


def _stalled_filter(task_repository: Any, filters: dict[str, Any]) -> dict[str, Any]:
    """The Stalled state: the keys of the open calls without any change for STALLED_DAYS days or more, as the
    Lifecycle & Phases count them."""
    options = list_options(task_repository)
    statuses = options['statuses']
    closed = {item['name'].casefold() for item in statuses if item['closed']}
    first = statuses[0]['name'] if statuses else ''
    base, base_params = _base_sql(untracked_status(task_repository, options), task_repository, _scope(filters))
    now = datetime.now()
    with task_repository.connection() as connection:
        keys = [str(row['call_key']) for row in connection.execute(
            f'WITH calls AS ({base}) SELECT call_key, status, updated_at, start_time FROM calls', base_params)
            if stalled_days(str(row['status'] or ''), row['updated_at'], row['start_time'], closed, first, now) is not None]
    return {**filters, '_stalled_keys': keys}


def _call_key_filters(task_repository: Any, filters: dict[str, Any]) -> dict[str, Any]:
    """The root cause counting suggestions, the RCA sources and the eNB/gNB filters as call keys."""
    wanted = {field: set(_strings(filters.get(field))) for field in KEY_FILTERS}
    if not any(wanted.values()):
        return filters
    suggestions_needed = bool(wanted['effective_domain'] or wanted['effective_cause'] or wanted['rca_state'])
    sources_needed = [source for source in RCA_FILTER_SOURCES
                      if any(wanted[f'{source}_{level}'] for level in ('domain', 'category', 'cause'))]
    options = list_options(task_repository)
    taxonomy = list_root_causes(task_repository)
    base, base_params = _base_sql(untracked_status(task_repository, options), task_repository, _scope(filters))
    # The panels of one filter change ask for the same calls at once: they are found once while nothing changes.
    with task_repository.connection() as connection:
        stamp = [tuple(connection.execute(sql).fetchone()) for sql in (
            f'SELECT COUNT(*), SUM(version), MAX(updated_at) FROM {NQ_CALL_TRACKING_TABLE}',
            f'SELECT COUNT(*), MAX(id), MAX(edited_at), MAX(deleted_at) FROM {NQ_CALL_COMMENTS_TABLE}',
            f'SELECT COUNT(*), MAX(imported_at) FROM {NQ_RCA_RESULTS_TABLE}',
            f"SELECT COUNT(*), (SELECT value FROM workspace_state WHERE key = '{nq_dta_rca.FINGERPRINT_STATE_KEY}') FROM {NQ_DTA_RESULTS_TABLE}")]
    cache_key = (_workspace_key(task_repository.db_path), hashlib.sha1(json.dumps(
        [base, base_params, stamp, taxonomy, {field: sorted(values) for field, values in wanted.items()}],
        sort_keys=True, default=str).encode()).hexdigest())
    with _key_filters_guard:
        cached = _key_filters_cache.get(cache_key)
    if cached is not None:
        return {**filters, '_call_keys': list(cached)}
    columns = ', '.join(dict.fromkeys(('call_key', 'root_domain', 'root_cause', 'cell_id', 'operator', *RULE_FIELDS,
                                       'failure_classification', 'failure_category', 'failure_subcategory', 'rca_json', 'dta_json')))
    with task_repository.connection() as connection:
        calls = connection.execute(f'WITH calls AS ({base}) SELECT {columns} FROM calls', base_params).fetchall()
        notes = _comment_texts(connection, [str(call['call_key']) for call in calls if not call['root_domain']]) \
            if suggestions_needed else {}
    keys = []
    for call in calls:
        key = str(call['call_key'])
        if suggestions_needed:
            domain, cause = str(call['root_domain'] or ''), str(call['root_cause'] or '')
            suggestion = None if domain else suggest_root_cause(call, taxonomy, notes.get(key, ''))
            if suggestion:
                domain, cause = suggestion['domain'], suggestion['cause']
            if wanted['rca_state'] and not ('suggested' in wanted['rca_state'] and suggestion):
                continue
            if wanted['effective_domain'] and (domain or UNASSIGNED) not in wanted['effective_domain']:
                continue
            if wanted['effective_cause'] and f'{domain}||{cause}' not in wanted['effective_cause']:
                continue
        # The root domain, domain·category or domain·cause the NetCheck RCA, the Ericsson RCA or the DT Analyzer RCA
        # gives the call, and the category or category·cause of its own hierarchy.
        if any(not _source_matches(source_root(call, source, taxonomy), wanted[f'{source}_domain'],
                                   wanted[f'{source}_category'], wanted[f'{source}_cause'])
               for source in sources_needed):
            continue
        if any(wanted[f'{source}_raw'] and not _raw_matches(rca_raw_pair(call, source, taxonomy), wanted[f'{source}_raw'])
               for source in RCA_FILTER_SOURCES):
            continue
        if wanted['node']:
            node = serving_node(call['cell_id'])
            if node is None or f"{call['operator'] or ''}||{node[0]} {node[1]}" not in wanted['node']:
                continue
        keys.append(key)
    with _key_filters_guard:
        if len(_key_filters_cache) >= 16:
            _key_filters_cache.pop(next(iter(_key_filters_cache)))
        _key_filters_cache[cache_key] = tuple(keys)
    return {**filters, '_call_keys': keys}


def rca_raw_pair(call: Any, source: str, taxonomy: dict[str, Any]) -> tuple[str, str]:
    """The category and cause of the own hierarchy of one RCA source for a call: the Failure Category (else
    Classification) and Subcategory of the CDR, the suggested category and cause of the Ericsson RCA, or the Root
    Category and Root Cause the DT Analyzer RCA finds."""
    if source == 'netcheck':
        return str(call['failure_category'] or call['failure_classification'] or ''), str(call['failure_subcategory'] or '')
    if source == 'script':
        try:
            rca = json.loads(call['rca_json'] or '{}') or {}
        except (TypeError, ValueError):
            rca = {}
        return (str(rca.get('rca_category') or rca.get('auto_rca_category_a') or ''),
                str(rca.get('rca_cause') or rca.get('auto_rca_subcategory_a') or ''))
    found = source_root(call, 'dta', taxonomy)
    return str(found['category'] or ''), str(found['cause'] or '')


def _raw_matches(pair: tuple[str, str], wanted: set[str]) -> bool:
    """Whether the own category (a value) or category·cause ("category||cause") of a source is one of those wanted; a
    call the source says nothing about never matches."""
    return any(pair) and (pair[0] in wanted or f'{pair[0]}||{pair[1]}' in wanted)


def _source_matches(mapped: dict[str, str], domains: set[str], categories: set[str], causes: set[str]) -> bool:
    if domains and (mapped['domain'] or UNASSIGNED) not in domains:
        return False
    if categories and f"{mapped['domain']}||{mapped['category']}" not in categories:
        return False
    return not causes or f"{mapped['domain']}||{mapped['cause']}" in causes


def _filter_sql(filters: dict[str, Any], username: str, closed_statuses: list[str],
                definitions: list[dict[str, Any]] | None = None) -> tuple[str, list[Any]]:
    known = {field['key']: field for field in definitions or []}
    clauses: list[str] = []
    params: list[Any] = []
    for field in (*FIELD_FILTERS, *TRACKING_FILTERS):
        values = _strings(filters.get(field))
        if not values:
            continue
        values = ['' if value == UNASSIGNED else value for value in values]
        if any(is_pattern(value) for value in values):
            # Patterns (VF*, -Lebara) are resolved whatever the case (see value_patterns).
            clause, clause_params = sql_condition(f"lower(COALESCE({field}, ''))", values)
            clauses.append(clause)
            params.extend(clause_params)
            continue
        clauses.append(f"{field} IN ({', '.join('?' for _ in values)})")
        params.extend(values)
    excluded = [str(name).strip().lower() for name in filters.get('_excluded_operators') or [] if str(name).strip()]
    if excluded:
        clauses.append(f"lower(COALESCE(operator, '')) NOT IN ({', '.join('?' for _ in excluded)})")
        params.extend(excluded)
    if isinstance(filters.get('_scope_sql'), tuple):
        scope_clause, scope_params = filters['_scope_sql']
        clauses.append(scope_clause)
        params.extend(scope_params)
    # The JOIN_IDs typed in their filter, whatever their case.
    join_ids = [value.casefold() for value in _strings(filters.get('join_id'))]
    if join_ids:
        clauses.append('lower(join_id) IN (SELECT value FROM json_each(?))')
        params.append(json.dumps(join_ids))
    # The CDRs filter chooses the versions in the base query. A call whose latest CDR has it
    # Completed is listed only on request, or while that CDR is not among the chosen ones.
    versions = ['' if value == 'current' else value for value in _strings(filters.get('version')) if value in VERSION_STATES]
    scope = _scope(filters)
    if versions:
        clauses.append(f"version_state IN ({', '.join('?' for _ in versions)})")
        params.extend(versions)
    elif scope:
        clauses.append(f"(version_state <> 'qualified' OR latest_dataset_id NOT IN ({', '.join('?' for _ in scope)}))")
        params.extend(scope)
    else:
        clauses.append("version_state <> 'qualified'")
    fields = filters.get('fields') if isinstance(filters.get('fields'), dict) else {}
    for key, values in fields.items():
        values = _strings(values)
        if not values:
            continue
        definition = known.get(str(key))
        if definition is not None and definition['source'] != 'user':
            # Fields from the follow-up, the CDR, the Ericsson RCA or derived: compared with their value.
            chosen = ['' if value == UNASSIGNED else value for value in values]
            clauses.append(f"{field_sql(definition)} IN ({', '.join('?' for _ in chosen)})")
            params.extend(chosen)
            continue
        chosen = [value for value in values if value != UNASSIGNED]
        parts = []
        if chosen:
            parts.append(f"EXISTS (SELECT 1 FROM {NQ_FIELD_VALUES_TABLE} f WHERE f.call_key = calls.call_key AND f.field_key = ? "
                         f"AND f.value IN ({', '.join('?' for _ in chosen)}))")
            params.extend([str(key), *chosen])
        if UNASSIGNED in values:
            parts.append(f"NOT EXISTS (SELECT 1 FROM {NQ_FIELD_VALUES_TABLE} f WHERE f.call_key = calls.call_key "
                         "AND f.field_key = ? AND f.value <> '')")
            params.append(str(key))
        clauses.append('(' + ' OR '.join(parts) + ')')
    # The optional and CDR columns of the table, filtered by their values ("Empty" for blank ones).
    columns = filters.get('columns') if isinstance(filters.get('columns'), dict) else {}
    for key, values in columns.items():
        expression = column_filter_sql(str(key))
        values = ['' if value == UNASSIGNED else value for value in _strings(values)]
        if expression and values:
            clauses.append(f"{expression} IN ({', '.join('?' for _ in values)})")
            params.extend(values)
    # The Follow-up: the calls in any of the states chosen.
    states, parts = _strings(filters.get('state')), []
    for state in states:
        if state == 'closed':
            parts.append(f"status IN ({', '.join('?' for _ in closed_statuses) or "''"})")
            params.extend(closed_statuses)
        elif state == 'open':
            parts.append(f"(status NOT IN ({', '.join('?' for _ in closed_statuses) or "''"}) AND status <> ?)")
            params.extend([*closed_statuses, str(filters.get('_first_status') or '')])
        elif state == 'stalled':
            parts.append('call_key IN (SELECT value FROM json_each(?))')
            params.append(json.dumps(list(filters.get('_stalled_keys') or [])))
        elif state in STATE_SQL:
            parts.append(STATE_SQL[state])
    if parts:
        clauses.append('(' + ' OR '.join(parts) + ')')
    if filters.get('open_only') and closed_statuses:
        clauses.append(f"status NOT IN ({', '.join('?' for _ in closed_statuses)})")
        params.extend(closed_statuses)
    if filters.get('mine'):
        clauses.append('assignee = ? COLLATE NOCASE')
        params.append(username)
    if filters.get('without_comments'):
        clauses.append('comment_count = 0')
    nr_modes = ['' if value in {UNASSIGNED, 'Unknown'} else value for value in _strings(filters.get('nr_mode'))]
    if nr_modes:
        clauses.append(f"nr_mode IN ({', '.join('?' for _ in nr_modes)})")
        params.extend(nr_modes)
    call_types = _strings(filters.get('call_type'))
    if call_types:
        clauses.append(f"({CALL_TYPE_SQL}) IN ({', '.join('?' for _ in call_types)})")
        params.extend(call_types)
    ranges = [bounds for value in _strings(filters.get('period')) if (bounds := period_bounds(value))]
    if ranges:
        clauses.append('(' + ' OR '.join(f'({START_SQL} >= ? AND {START_SQL} < ?)' for _ in ranges) + ')')
        params.extend(bound for pair in ranges for bound in pair)
    ages = [condition for value in _strings(filters.get('age')) if (condition := AGE_SQL.get(value))]
    if ages:
        clauses.append('(' + ' OR '.join(ages) + ')')
    pairs = _strings(filters.get('root_pair'))
    if pairs:
        clauses.append(f"(root_domain || '||' || root_cause) IN ({', '.join('?' for _ in pairs)})")
        params.extend('||' if value == UNASSIGNED else value for value in pairs)
    places = _strings(filters.get('place'))
    if places:
        clauses.append(f"(COALESCE(operator, '') || '||' || place_label) IN ({', '.join('?' for _ in places)})")
        params.extend(places)
    spots = _strings(filters.get('hotspot'))
    if spots:
        clauses.append(f"cluster_key IN ({', '.join('?' for _ in spots)})")
        params.extend(spots)
    if '_call_keys' in filters:
        clauses.append('call_key IN (SELECT value FROM json_each(?))')
        params.append(json.dumps(list(filters['_call_keys'])))
    search = str(filters.get('search') or '').strip().casefold()
    if search:
        haystack = " || ' ' || ".join(f"COALESCE({field}, '')" for field in SEARCH_FIELDS)
        clauses.append(
            f"(instr(lower({haystack}), ?) > 0 OR EXISTS (SELECT 1 FROM {NQ_CALL_COMMENTS_TABLE} s "
            f"WHERE s.call_key = calls.call_key AND s.deleted_at = '' AND instr(lower(s.body), ?) > 0) "
            f"OR EXISTS (SELECT 1 FROM {NQ_FIELD_VALUES_TABLE} f WHERE f.call_key = calls.call_key AND instr(lower(f.value), ?) > 0))"
        )
        params.extend([search, search, search])
    return (' WHERE ' + ' AND '.join(clauses)) if clauses else '', params


def _call_payload(row: Any) -> dict[str, Any]:
    payload = {key: row[key] for key in row.keys()}
    payload['service_label'] = SERVICE_LABELS.get(str(payload.get('service')), str(payload.get('service') or ''))
    for source, target in (('field_values_json', 'fields'), ('extra_json', 'extra'), ('rca_json', 'rca'), ('dta_json', 'dta')):
        try:
            value = json.loads(payload.pop(source, None) or '{}')
        except (TypeError, ValueError):
            value = {}
        payload[target] = value if isinstance(value, dict) else {}
    return payload


def _order_sql(sort: str, task_repository: Any) -> str:
    """The ORDER BY expression of a sort key: a column, an analysis field or a CDR column."""
    if sort.startswith('field:'):
        key = sort.split(':', 1)[1]
        definition = next((field for field in list_fields(task_repository) if field['key'] == key), None)
        if definition is not None:
            return field_sql(definition)
    if sort.startswith('cdr:'):
        name = sort.split(':', 1)[1]
        if name in indexed_cdr_columns(task_repository):
            return f"COALESCE(json_extract(extra_json, '$.\"{name.replace(chr(34), '')}\"'), '')"
    return SORT_COLUMNS.get(sort, 'start_time')


def _comments_by_call(connection: Any, keys: list[str]) -> dict[str, dict[str, Any]]:
    if not keys:
        return {}
    rows = connection.execute(
        f"SELECT call_key, body, created_by, created_at FROM {NQ_CALL_COMMENTS_TABLE} "
        f"WHERE deleted_at = '' AND call_key IN ({', '.join('?' for _ in keys)}) ORDER BY id",
        keys,
    ).fetchall()
    return {str(row['call_key']): {'body': str(row['body']), 'created_by': str(row['created_by']),
                                   'created_at': str(row['created_at'])} for row in rows}


def query_calls(task_repository: Any, request: dict[str, Any], username: str) -> dict[str, Any]:
    """A page of calls with the executive summary of every call that matches the filters."""
    options = list_options(task_repository)
    definitions = list_fields(task_repository)
    filters = request.get('filters') if isinstance(request.get('filters'), dict) else {}
    filters = _resolve_key_filters(task_repository, filters)
    closed = [item['name'] for item in options['statuses'] if item['closed']]
    base, base_params = _base_sql(untracked_status(task_repository, options), task_repository, _scope(filters))
    where, params = _filter_sql(filters, username, closed, definitions)
    sort_key = str(request.get('sort') or '')
    sort = _order_sql(sort_key, task_repository)
    direction = 'ASC' if str(request.get('direction') or '').lower() == 'asc' else 'DESC'
    page_size = int(request.get('page_size') or DEFAULT_PAGE_SIZE)
    page_size = page_size if page_size in PAGE_SIZES else DEFAULT_PAGE_SIZE
    # The breakdowns of the Summary are left out while it is not shown.
    with_breakdowns = request.get('breakdowns', True) is not False
    with task_repository.connection() as connection:
        base, base_params = _materialized(connection, base, base_params, bool(_scope(filters)))
        filtered = f'WITH calls AS ({base}) SELECT * FROM calls{where}'
        all_params = [*base_params, *params]
        total = int(connection.execute(f'SELECT COUNT(*) FROM ({filtered})', all_params).fetchone()[0])
        pages = max(1, math.ceil(total / page_size))
        page = min(max(1, int(request.get('page') or 1)), pages)
        rows = connection.execute(
            f'SELECT * FROM ({filtered}) ORDER BY {sort} = \'\', {sort} {direction}, start_time DESC, call_key '
            f'LIMIT ? OFFSET ?',
            [*all_params, page_size, (page - 1) * page_size],
        ).fetchall()
        calls = [_call_payload(row) for row in rows]
        last_comments = _comments_by_call(connection, [call['call_key'] for call in calls])
        notes = _comment_texts(connection, [call['call_key'] for call in calls])
        taxonomy = list_root_causes(task_repository)
        learned = learned_decisions(connection)
        names = {int(row['id']): str(row['file_name']) for row in connection.execute('SELECT id, file_name FROM datasets')}
        for call in calls:
            call['last_comment'] = last_comments.get(call['call_key'])
            note = notes.get(call['call_key'], '')
            call['suggested_root_cause'] = suggest_root_cause(call, taxonomy, note)
            call['rca_recommendation'] = recommendation_for(call, taxonomy, note, learned)
            call['values'] = {field['key']: catalog_value(field, call, call.get('rca'), call.get('fields')) for field in definitions}
            call['dataset_name'] = names.get(int(call['dataset_id']), '')
            call['latest_dataset_name'] = names.get(int(call['latest_dataset_id'] or call['dataset_id']), '')
        breakdowns = []
        mapping_settings = task_repository.chart_mapping_settings()
        for field, label in BREAKDOWNS if with_breakdowns else ():
            values = connection.execute(
                f'SELECT {field} AS value, COUNT(*) AS count FROM ({filtered}) GROUP BY {field} ORDER BY count DESC, value LIMIT 12',
                all_params,
            ).fetchall()
            items = [{'value': str(row['value'] or ''), 'count': int(row['count'])} for row in values]
            # The largest Operators and Vendors are listed in Operator Map and Vendor Map order,
            # and Campaigns chronologically (the plain, NSA and SA campaigns of a quarter in that order).
            if field in {'operator', 'vendor', 'operator_vendor'}:
                items.sort(key=lambda item, field=field: dimension_order_key(
                    field, item['value'], mapping_settings['operator_mapping_groups'], mapping_settings['vendor_mapping_groups'],
                ))
            elif field == 'campaign':
                items.sort(key=lambda item: campaign_sort_key(item['value']))
            breakdowns.append({'field': field, 'label': label, 'items': items})
        # The catalog fields shown in the Summary, as one more breakdown each.
        for definition in [field for field in definitions if with_breakdowns and field['in_summary']
                           and field['source'] in {'user', 'derived', 'cdr', 'rca', 'priority'}]:
            values = connection.execute(
                f"SELECT {field_sql(definition)} AS value, COUNT(*) AS count "
                f"FROM ({filtered}) GROUP BY value ORDER BY count DESC, value LIMIT 12", all_params,
            ).fetchall()
            order = [option['name'] for option in definition['options']] or list(YES_NO)
            items = [{'value': str(row['value'] or ''), 'count': int(row['count'])} for row in values]
            items.sort(key=lambda item: (order.index(item['value']) if item['value'] in order else len(order), -item['count']))
            breakdowns.append({'field': f"field:{definition['key']}", 'label': f"By {definition['label']}", 'items': items,
                               'colors': {option['name']: option['color'] for option in definition['options'] if option['color']}})
        closed_marks = ', '.join('?' for _ in closed) or "''"
        summary = connection.execute(
            f"SELECT COUNT(*) AS total, "
            f"SUM(CASE WHEN status IN ({closed_marks}) THEN 1 ELSE 0 END) AS closed, "
            f"SUM(CASE WHEN comment_count > 0 THEN 1 ELSE 0 END) AS commented, "
            # Attended: followed up (a status, team, assignee or root cause change) or commented.
            f"SUM(CASE WHEN updated_at <> '' OR comment_count > 0 THEN 1 ELSE 0 END) AS attended, "
            f"SUM(CASE WHEN team <> '' THEN 1 ELSE 0 END) AS with_team, "
            f"SUM(CASE WHEN assignee <> '' THEN 1 ELSE 0 END) AS assigned "
            f"FROM ({filtered})",
            [*closed, *all_params],
        ).fetchone()
    summary_payload = {key: int(summary[key] or 0) for key in ('total', 'closed', 'attended', 'commented', 'with_team', 'assigned')}
    summary_payload['open'] = summary_payload['total'] - summary_payload['closed']
    return {
        'calls': calls, 'total': total, 'page': page, 'pages': pages, 'page_size': page_size,
        'sort': sort_key if sort_key.startswith(('field:', 'cdr:')) and sort != 'start_time'
        else next((key for key, column in SORT_COLUMNS.items() if column == sort), 'start_time'),
        'direction': direction.lower(), 'summary': summary_payload, 'breakdowns': breakdowns,
    }


# The text fields of people (who analysed and who reviewed each call): filtered, like lists, by the names they hold.
VALUE_FILTER_FIELDS = ('analyst', 'reviewer')


def filter_options(task_repository: Any, layout: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    """Distinct values of every indexed filter; Operators and Vendors with their mapped labels and the NetCheck RCA
    with the spelling of its values; the column filters of the table ``layout`` (that of the workspace by default)."""
    values: dict[str, list[str]] = {}
    mapper = ValueMapper.from_repository(task_repository)
    maps = _value_maps(task_repository)
    with task_repository.connection() as connection:
        for field in FIELD_FILTERS:
            if field == 'vendor_operator':
                # Derived from the mapped Operator_Vendor values (listed before it).
                values[field] = mapper.values('vendor_operator', mapper.vendor_operators(values.get('operator_vendor') or []))
                continue
            rows = connection.execute(
                f"SELECT DISTINCT {field} AS value FROM {NQ_CALLS_TABLE} WHERE {field} <> '' ORDER BY value COLLATE NOCASE"
            ).fetchall()
            values[field] = [str(row['value']) for row in rows]
            if field in MAPPED_FIELDS:
                values[field] = [str(value) for value in mapper.values(field_kind(field), values[field])]
            elif field in SPELLING_FIELDS:
                spellings = json.loads(maps[field])
                values[field] = sorted({spellings.get(value, value) for value in values[field]}, key=str.casefold)
            elif field == 'campaign':
                values[field] = sorted(values[field], key=campaign_sort_key)
        assignees = connection.execute(
            f"SELECT DISTINCT assignee FROM {NQ_CALL_TRACKING_TABLE} WHERE assignee <> '' ORDER BY assignee COLLATE NOCASE"
        ).fetchall()
        # The values of every optional and CDR column of the table, for their header filters.
        chosen = layout or table_columns(task_repository)
        for key in [*(column for column in chosen['builtin'] if column in COLUMN_FILTER_SQL), *(f'cdr:{name}' for name in chosen['cdr'])]:
            expression = column_filter_sql(key)
            rows = connection.execute(
                f"SELECT DISTINCT {expression} AS value FROM {NQ_CALLS_TABLE} WHERE {expression} <> '' "
                f"ORDER BY value COLLATE NOCASE LIMIT {MAX_COLUMN_FILTER_VALUES}"
            ).fetchall()
            values[f'column:{key}'] = [str(row['value']) for row in rows]
        # The names of the people of the calls (Analyst, Reviewer), as the calls of the workspace hold them.
        for key in VALUE_FILTER_FIELDS:
            values[f'field:{key}'] = [str(row[0]) for row in connection.execute(
                f"SELECT DISTINCT value FROM {NQ_FIELD_VALUES_TABLE} WHERE field_key = ? AND value <> '' "
                f"AND call_key IN (SELECT call_key FROM {NQ_CALLS_TABLE}) ORDER BY value COLLATE NOCASE "
                f"LIMIT {MAX_COLUMN_FILTER_VALUES}", (key,))]
    values['assignee'] = [str(row['assignee']) for row in assignees]
    # NR Mode, the first General Filter: with Campaign it says which CDRs the calls come from.
    with task_repository.connection() as connection:
        values['nr_mode'] = sorted({str(row[0]) for row in connection.execute(
            f"SELECT DISTINCT nr_mode FROM {NQ_CALLS_TABLE} WHERE nr_mode <> ''")}, key=lambda value: (value != 'NSA', value))
    return values


def _filter_expressions(task_repository: Any, definitions: list[dict[str, Any]]) -> dict[str, str]:
    """The SQL value, in the calls query, of every filter of the Filters panel listed with its values (CDRs and CDR
    Version aside): the indexed and follow-up fields, the fields of the analysis and the columns of the table."""
    expressions = {field: field for field in (*FIELD_FILTERS, *TRACKING_FILTERS)}
    expressions['nr_mode'] = 'nr_mode'
    for definition in definitions:
        if definition['source'] in {'user', 'derived', 'priority'} and (definition['type'] in {'list', 'yes_no'} or definition['key'] in VALUE_FILTER_FIELDS):
            expressions[f"field:{definition['key']}"] = field_sql(definition)
    # Every optional and indexed CDR column, as the table layout of each user may show it.
    for key in [*COLUMN_FILTER_SQL, *(f'cdr:{name}' for name in indexed_cdr_columns(task_repository))]:
        expressions[f'column:{key}'] = column_filter_sql(key)
    return expressions


def _filter_chosen(filters: dict[str, Any], key: str) -> list[str]:
    """The values chosen in one filter (``field:<key>`` and ``column:<key>`` for the analysis fields and columns)."""
    for prefix, group in (('field:', 'fields'), ('column:', 'columns')):
        if key.startswith(prefix):
            chosen = filters.get(group) if isinstance(filters.get(group), dict) else {}
            return _strings(chosen.get(key[len(prefix):]))
    return _strings(filters.get(key))


def _without_filter(filters: dict[str, Any], key: str) -> dict[str, Any]:
    """The filters but one."""
    rest = dict(filters)
    for prefix, group in (('field:', 'fields'), ('column:', 'columns')):
        if key.startswith(prefix):
            chosen = filters.get(group) if isinstance(filters.get(group), dict) else {}
            rest[group] = {name: values for name, values in chosen.items() if name != key[len(prefix):]}
            return rest
    rest.pop(key, None)
    return rest


def available_filter_values(task_repository: Any, filters: Any, username: str) -> dict[str, list[str]]:
    """What the list of every filter offers: the values of the calls that match the other filters ('' for the calls
    without one), so a filter shows only the values left by the others and keeps its own. The CDRs are those with
    some of these calls; CDR Version keeps its states."""
    options = list_options(task_repository)
    definitions = list_fields(task_repository)
    filters = _resolve_key_filters(task_repository, filters if isinstance(filters, dict) else {})
    closed = [item['name'] for item in options['statuses'] if item['closed']]
    default = untracked_status(task_repository, options)
    expressions = _filter_expressions(task_repository, definitions)
    # The filters not chosen share the same other filters (all of them): one pass for all; one more for each chosen one.
    idle = [key for key in expressions if not _filter_chosen(filters, key)]
    passes = [(filters, idle), *((_without_filter(filters, key), [key]) for key in expressions if key not in idle)]
    values: dict[str, list[str]] = {}
    with task_repository.connection() as connection:
        base, base_params = _materialized(connection, *_base_sql(default, task_repository, _scope(filters)), bool(_scope(filters)))
        for chosen, keys in passes:
            if not keys:
                continue
            where, params = _filter_sql(chosen, username, closed, definitions)
            row = connection.execute(
                f"WITH calls AS ({base}) SELECT {', '.join(f'json_group_array(DISTINCT {expressions[key]})' for key in keys)} "
                f"FROM calls{where}", [*base_params, *params]).fetchone()
            for key, found in zip(keys, row):
                values[key] = sorted({'' if value is None else str(value) for value in json.loads(found or '[]')})
        # The CDRs with some of the calls of the other filters, whatever CDRs they choose.
        latest, latest_params = _base_sql(default, task_repository)
        where, params = _filter_sql(_without_filter(filters, 'datasets'), username, closed, definitions)
        values['datasets'] = [str(row[0]) for row in connection.execute(
            f"WITH calls AS ({latest}) SELECT DISTINCT dataset_id FROM {NQ_CALLS_TABLE} "
            f"WHERE call_key IN (SELECT call_key FROM calls{where}) ORDER BY dataset_id", [*latest_params, *params])]
    return values


PROGRESS_GRANULARITIES = ('week', 'month', 'quarter', 'year')
AGE_BUCKETS = ((7, 'Under 7 days'), (30, '7–30 days'), (90, '30–90 days'), (None, 'Over 90 days'))


def stalled_days(status: str, updated_at: Any, start_time: Any, closed: set[str], first: str, now: datetime) -> int | None:
    """The days an open call (attended and not closed: neither in the first status nor in a closed one) has gone
    without any change, from its last change or else its start, when they are STALLED_DAYS or more."""
    if status.casefold() in closed or status == first:
        return None
    last = _parse_time(updated_at) or _parse_time(start_time)
    if last is None or (now - last).days < STALLED_DAYS:
        return None
    return int((now - last).total_seconds() // 86400)


def _parse_time(value: Any) -> datetime | None:
    text = _text(value).replace('T', ' ')
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is None else parsed.astimezone().replace(tzinfo=None)


def period_label(moment: datetime, granularity: str) -> str:
    """The week (ISO), month, quarter or year a moment belongs to."""
    if granularity == 'week':
        year, week, _day = moment.isocalendar()
        return f'{year}-W{week:02d}'
    if granularity == 'quarter':
        return f'{moment.year}-Q{(moment.month - 1) // 3 + 1}'
    if granularity == 'year':
        return str(moment.year)
    return f'{moment.year}-{moment.month:02d}'


KEYED_READ_CHUNK = 500
# With more calls than this, the history or comments of the calls are read once and kept for the calls in Python.
KEYED_READ_SCAN = 4000


def _rows_of_calls(connection: Any, select: str, keys: list[str], where: str = '', order: str = '') -> list[Any]:
    """The rows of a follow-up table (history, comments) for some calls: by key for a few calls, or in one read."""
    condition = f' AND ({where})' if where else ''
    order_sql = f' ORDER BY {order}' if order else ''
    if len(keys) > KEYED_READ_SCAN:
        wanted = set(keys)
        return [row for row in connection.execute(f'{select} WHERE 1 = 1{condition}{order_sql}') if str(row['call_key']) in wanted]
    rows: list[Any] = []
    for start in range(0, len(keys), KEYED_READ_CHUNK):
        chunk = keys[start:start + KEYED_READ_CHUNK]
        rows.extend(connection.execute(
            f"{select} WHERE call_key IN ({', '.join('?' for _ in chunk)}){condition}{order_sql}", chunk).fetchall())
    if len(keys) > KEYED_READ_CHUNK and order:
        rows.sort(key=lambda row: tuple(row[name.split()[0]] for name in order.split(', ')))
    return rows


def progress_stats(task_repository: Any, filters: dict[str, Any], username: str, granularity: str = 'week') -> dict[str, Any]:
    """Follow-up progress of the calls matching the filters.

    Distributions by status, team, assignee, service and result; how many calls
    were detected, attended (first change or comment), commented, moved to each
    status, closed and reopened per week, month, quarter or year; the open
    backlog, the age of open calls, the workload of teams and assignees and the
    activity of every user.
    """
    granularity = granularity if granularity in PROGRESS_GRANULARITIES else 'week'
    options = list_options(task_repository)
    closed_names = {item['name'].casefold() for item in options['statuses'] if item['closed']}
    base, base_params = _base_sql(untracked_status(task_repository, options), task_repository, _scope(filters))
    where, params = _filter_sql(_resolve_key_filters(task_repository, filters), username,
                                [item['name'] for item in options['statuses'] if item['closed']], list_fields(task_repository))
    with task_repository.connection() as connection:
        calls = connection.execute(
            f'WITH calls AS ({base}) SELECT call_key, start_time, status, team, assignee, service, result FROM calls{where}',
            [*base_params, *params],
        ).fetchall()
        keys = [str(row['call_key']) for row in calls]
        history = _rows_of_calls(connection, f'SELECT id, call_key, field, old_value, new_value, changed_by, changed_at '
                                             f'FROM {NQ_CALL_HISTORY_TABLE}', keys, order='changed_at, id')
        comments = _rows_of_calls(connection, f'SELECT id, call_key, created_by, created_at, deleted_at FROM {NQ_CALL_COMMENTS_TABLE}',
                                  keys, order='created_at, id')

    def distribution(field: str, empty: str, order: list[str] | None = None) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for row in calls:
            value = str(row[field] or '') or empty
            counts[value] = counts.get(value, 0) + 1
        ordered = [name for name in (order or []) if name in counts]
        ordered += sorted((name for name in counts if name not in ordered), key=lambda name: (-counts[name], name.casefold()))
        return [{'value': name, 'count': counts[name]} for name in ordered]

    first_followup: dict[str, datetime] = {}
    closed_at: dict[str, datetime] = {}
    timeline: dict[str, dict[str, Any]] = {}

    def bucket(moment: datetime | None) -> dict[str, Any] | None:
        if moment is None:
            return None
        label = period_label(moment, granularity)
        return timeline.setdefault(label, {
            'period': label, 'detected': 0, 'attended': 0, 'comments': 0, 'changes': 0,
            'closed': 0, 'reopened': 0, 'statuses': {}, 'close_days': [],
        })

    def follow_up(key: str, moment: datetime | None) -> None:
        if moment is not None and (key not in first_followup or moment < first_followup[key]):
            first_followup[key] = moment

    activity: dict[str, dict[str, int]] = {}
    for row in history:
        moment = _parse_time(row['changed_at'])
        key = str(row['call_key'])
        follow_up(key, moment)
        user = activity.setdefault(str(row['changed_by'] or '—'), {'changes': 0, 'comments': 0, 'closed': 0})
        user['changes'] += 1
        target = bucket(moment)
        if target is not None:
            target['changes'] += 1
        # A status chosen by hand or set by the Status Rules (as importing analyses does) moves the call alike.
        if row['field'] not in {'status', 'status_auto'} or target is None:
            continue
        new_value, old_value = str(row['new_value']), str(row['old_value'])
        target['statuses'][new_value] = target['statuses'].get(new_value, 0) + 1
        if new_value.casefold() in closed_names and old_value.casefold() not in closed_names:
            target['closed'] += 1
            user['closed'] += 1
            closed_at[key] = moment
        elif old_value.casefold() in closed_names and new_value.casefold() not in closed_names:
            target['reopened'] += 1
            closed_at.pop(key, None)
    for row in comments:
        moment = _parse_time(row['created_at'])
        follow_up(str(row['call_key']), moment)
        activity.setdefault(str(row['created_by'] or '—'), {'changes': 0, 'comments': 0, 'closed': 0})['comments'] += 1
        target = bucket(moment)
        if target is not None:
            target['comments'] += 1
    for row in calls:
        target = bucket(_parse_time(row['start_time']))
        if target is not None:
            target['detected'] += 1
    for key, moment in first_followup.items():
        bucket(moment)['attended'] += 1
    # The days to close count from the call (imported analyses follow a call up and close it at once).
    starts = {str(row['call_key']): _parse_time(row['start_time']) for row in calls}
    close_days = {key: (moment - starts[key]).total_seconds() / 86400 for key, moment in closed_at.items()
                  if starts.get(key) is not None and moment >= starts[key]}
    for key, days in close_days.items():
        bucket(closed_at[key])['close_days'].append(days)

    periods = []
    backlog = 0
    for label in sorted(timeline):
        item = timeline[label]
        backlog += item['detected'] - item['closed'] + item['reopened']
        days = item.pop('close_days')
        periods.append({**item, 'open_backlog': max(backlog, 0),
                        'avg_days_to_close': round(sum(days) / len(days), 1) if days else None})

    open_calls = [row for row in calls if str(row['status']).casefold() not in closed_names]
    now = datetime.now()
    ages: dict[str, int] = {label: 0 for _limit, label in AGE_BUCKETS}
    ages['Unknown date'] = 0
    for row in open_calls:
        moment = _parse_time(row['start_time'])
        if moment is None:
            ages['Unknown date'] += 1
            continue
        days = (now - moment).total_seconds() / 86400
        ages[next(label for limit, label in AGE_BUCKETS if limit is None or days < limit)] += 1

    def workload(field: str) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for row in calls:
            name = str(row[field] or '') or 'Unassigned'
            entry = rows.setdefault(name, {'name': name, 'open': 0, 'closed': 0, 'total': 0})
            entry['total'] += 1
            entry['closed' if str(row['status']).casefold() in closed_names else 'open'] += 1
        return sorted(rows.values(), key=lambda entry: (-entry['open'], -entry['total'], entry['name'].casefold()))

    attended = [key for key in keys if key in first_followup]
    response_days = []
    for key in attended:
        if starts.get(key) is not None and first_followup[key] >= starts[key]:
            response_days.append((first_followup[key] - starts[key]).total_seconds() / 86400)
    total = len(calls)
    closed_total = total - len(open_calls)
    return {
        'granularity': granularity,
        'summary': {
            'total': total, 'attended': len(attended), 'not_attended': total - len(attended),
            'open': len(open_calls), 'closed': closed_total,
            'closure_rate': round(closed_total * 100 / total, 1) if total else 0.0,
            'comments': sum(1 for row in comments if not row['deleted_at']),
            'changes': len(history), 'contributors': len(activity),
            'avg_days_to_first_follow_up': round(sum(response_days) / len(response_days), 1) if response_days else None,
            'avg_days_to_close': round(sum(close_days.values()) / len(close_days), 1) if close_days else None,
        },
        'distributions': [
            {'field': 'status', 'label': 'By Status', 'items': distribution('status', '—', [item['name'] for item in options['statuses']])},
            {'field': 'team', 'label': 'By Team', 'items': distribution('team', 'Unassigned', [item['name'] for item in options['teams']])},
            {'field': 'assignee', 'label': 'By Assignee', 'items': distribution('assignee', 'Unassigned')},
            {'field': 'service', 'label': 'By Service', 'items': [
                {**item, 'value': SERVICE_LABELS.get(item['value'], item['value']), 'filter': item['value']}
                for item in distribution('service', '—')]},
            {'field': 'result', 'label': 'By Result', 'items': distribution('result', '—')},
        ],
        'aging': [{'value': label, 'count': count} for label, count in ages.items() if count or label != 'Unknown date'],
        'periods': periods,
        # The moves to each open status (those to a closed status are the closures of the Closed column).
        'statuses': [item['name'] for item in options['statuses'] if not item['closed']],
        'teams': workload('team'),
        'assignees': workload('assignee')[:20],
        'activity': sorted(({'name': name, **values} for name, values in activity.items()),
                           key=lambda entry: (-(entry['changes'] + entry['comments']), entry['name'].casefold()))[:20],
    }


# ---------------------------------------------------------------------------
# Root Cause Analysis
# ---------------------------------------------------------------------------
MAX_ECI = 268_435_455  # 28-bit E-UTRAN Cell Identity; larger identities are NR cells (36-bit NCI).
MAX_NODES = 25
MAX_RATS = 12
_CELL_NUMBERS = re.compile(r'\d+')
NODE_TECHNOLOGIES = {'eNB': 'LTE', 'gNB': 'NR'}
# Node (eNB / gNB, number, owner network family) -> its sites: (site ID, host network, vendor, latitude, longitude).
NodeSites = dict[tuple[str, int, str], list[tuple[str, str, str, float | None, float | None]]]
_node_sites_cache: dict[str, tuple[str, NodeSites]] = {}


def call_type(service: str, test_name: str) -> str:
    """Classic or WhatsApp for Voice and Speech calls; Data for the Data tests."""
    if service == 'data':
        return 'Data'
    return 'WhatsApp' if 'whatsapp' in str(test_name or '').casefold() else 'Classic'


def serving_node(cell_id: Any) -> tuple[str, int] | None:
    """The eNB or gNB of the last cell of the call (where it failed), or the cell itself for 2G/3G cells."""
    numbers = _CELL_NUMBERS.findall(str(cell_id or ''))
    if not numbers:
        return None
    value = int(numbers[-1])
    if value > MAX_ECI:
        # NR Cell Identities of the UK operators' 22-bit gNodeB IDs: gNB × 16384 + cell.
        return 'gNB', value >> nr_cell_bits()
    if value > 65535:
        return 'eNB', value >> 8
    return 'Cell', value


def node_sites(repository: Any) -> NodeSites:
    """The sites of every eNB and gNB of the inventory cells of the workspace (its Network Inventories and cell mappings),
    by node number and owner network family, as node numbers are only unique within a network: each with its site ID,
    host network, vendor and position, from the newest snapshot that lists the node in that network (cached until the
    snapshots change)."""
    from src.modules.network_inventory import INVENTORY_CELLS_TABLE, INVENTORY_SNAPSHOTS_TABLE, list_inventory_snapshots

    snapshots = list_inventory_snapshots(repository)
    with repository.connection() as connection:
        built = [tuple(row) for row in connection.execute(
            f'SELECT dataset_id, version, revision, built_at FROM {INVENTORY_SNAPSHOTS_TABLE} ORDER BY dataset_id')]
    workspace = str(Path(str(repository.db_path)).resolve())
    stamp = json.dumps([built, [item['dataset_id'] for item in snapshots]], default=str)
    cached = _node_sites_cache.get(workspace)
    if cached and cached[0] == stamp:
        return cached[1]
    ranks = {item['dataset_id']: rank for rank, item in enumerate(snapshots)}
    kinds = {technology: kind for kind, technology in NODE_TECHNOLOGIES.items()}
    found: dict[tuple[str, int, str], tuple[int, list[tuple[int, str, str, str, float | None, float | None]]]] = {}
    with repository.connection() as connection:
        rows = connection.execute(
            f'SELECT dataset_id, technology, node_id, network_family, host_network, site_id, MAX(vendor), AVG(latitude), '
            f'AVG(longitude), COUNT(*) FROM {INVENTORY_CELLS_TABLE} '
            f"WHERE technology IN ('LTE', 'NR') AND node_id > 0 AND site_id <> '' AND network_family <> '' "
            'GROUP BY dataset_id, technology, node_id, network_family, host_network, site_id')
        for dataset_id, technology, node_id, family, host, site, vendor, latitude, longitude, cells in rows:
            if int(dataset_id) not in ranks:
                continue
            key = (kinds[str(technology)], int(node_id), str(family))
            rank = ranks[int(dataset_id)]
            entry = found.get(key)
            if entry is None or rank < entry[0]:
                entry = found[key] = (rank, [])
            if rank == entry[0]:
                entry[1].append((-int(cells), str(site), str(host or ''), str(vendor or ''), latitude, longitude))
    # The site with the most cells of the node first (a node of one network is almost always on one site).
    sites: NodeSites = {key: [item[1:] for item in sorted(values)] for key, (_rank, values) in found.items()}
    _node_sites_cache[workspace] = (stamp, sites)
    return sites


def _distance_km(latitude: float, longitude: float, other_latitude: float, other_longitude: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (latitude, longitude, other_latitude, other_longitude))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(value)))


def node_site(sites: NodeSites, families: tuple[str, ...], node: tuple[str, int], latitude: Any, longitude: Any,
              max_distance_km: float) -> dict[str, str] | None:
    """The site of the eNB or gNB of a call, as the serving-cell Vendor Mapping chooses a cell: in the first network
    allowed to serve the call's operator (its own first) with a node of that number within ``max_distance_km`` of the call
    (any when the call or the site has no position), the nearest one; None when no network has it."""
    lat, lon = _number(latitude), _number(longitude)
    located = lat is not None and lon is not None and not (lat == 0 and lon == 0)
    for family in families:
        best: tuple[float, dict[str, str]] | None = None
        for site, host, vendor, site_lat, site_lon in sites.get((node[0], node[1], family), ()):
            distance = _distance_km(lat, lon, site_lat, site_lon) if located and site_lat is not None and site_lon is not None else None
            if distance is not None and distance > max_distance_km:
                continue
            rank = math.inf if distance is None else distance
            if best is None or rank < best[0]:
                best = (rank, {'site': site, 'host': host, 'vendor': vendor})
        if best is not None:
            return best[1]
    return None


def node_site_lookup(repository: Any) -> Callable[[Any, tuple[str, int]], dict[str, str] | None]:
    """The site, host network and vendor of the eNB or gNB of a call (its operator, latitude and longitude) from the
    inventory cells of the workspace, with its Serving Networks and their maximum distance (see ``node_site``)."""
    from src.modules.serving_cells import load_serving_networks, serving_families

    try:
        sites = node_sites(repository)
    except Exception:  # noqa: BLE001 - unreadable inventory cells only leave the nodes without a site.
        sites = {}
    config = load_serving_networks(repository)
    families: dict[str, tuple[str, ...]] = {}

    def value(call: Any, key: str) -> Any:
        try:
            return call[key]
        except (KeyError, IndexError):
            return None

    def lookup(call: Any, node: tuple[str, int]) -> dict[str, str] | None:
        if not sites or node[0] not in NODE_TECHNOLOGIES:
            return None
        operator = str(value(call, 'operator') or '').strip()
        if operator not in families:
            families[operator] = serving_families(operator, config)
        return node_site(sites, families[operator], node, value(call, 'latitude'), value(call, 'longitude'),
                         float(config['max_distance_km']))
    return lookup


def source_root(call: Any, source: str, taxonomy: dict[str, Any]) -> dict[str, str]:
    """The domain, category and cause the NetCheck RCA of the CDR (its fields, never the comments), the Ericsson
    Script RCA or the DT Analyzer RCA gives a call on the Root Cause Catalog; empty values when the source says
    nothing the catalog knows."""
    rule = taxonomy.get('rule') or DEFAULT_ROOT_CAUSE_RULE
    mapped: dict[str, str] | None = None
    if source == 'dta':
        result = dta_of(call)
        return {'domain': str(result.get('dta_domain') or ''), 'category': str(result.get('dta_category') or ''),
                'cause': str(result.get('dta_cause') or '')}
    if source == 'netcheck':
        if any(str(call[key] or '') for key in ('failure_classification', 'failure_category', 'failure_subcategory')):
            mapped = nq_rca.suggest_from_text(call, taxonomy, {**rule, 'comments': False, 'comment_domain': False})
    elif source == 'script':
        try:
            rca = json.loads(call['rca_json'] or '{}') or {}
        except (TypeError, ValueError):
            rca = {}
        raw = (str(rca.get('rca_category') or rca.get('auto_rca_category_a') or ''),
               str(rca.get('rca_cause') or rca.get('auto_rca_subcategory_a') or ''))
        if any(raw):
            mapped = nq_rca.map_to_catalog(*raw, taxonomy, rule.get('match', 'words'))
    mapped = mapped or {}
    return {'domain': mapped.get('domain') or '', 'category': mapped.get('category') or '', 'cause': mapped.get('cause') or ''}


def root_cause_stats(task_repository: Any, filters: dict[str, Any], username: str,
                     include_suggestions: bool = True, source: str = 'analysts') -> dict[str, Any]:
    """Root Cause Analysis of the calls matching the filters.

    Calls are counted per root domain, category and cause, Classic/WhatsApp/Data call type, NR
    mode (NSA or SA), technology and the eNB/gNB of their last cell, with the site, host network and vendor most of
    its calls have in the inventory cells of the workspace (``node_site_lookup``). With the ``analysts`` source the
    calls count with the root cause the analysts chose, and those without one with their suggested one when ``include_suggestions`` is set; the
    ``netcheck``, ``script`` and ``dta`` sources count every call with what that source gives it on the catalog.
    """
    source = source if source in ROOT_SOURCES else 'analysts'
    include_suggestions = include_suggestions and source == 'analysts'
    options = list_options(task_repository)
    taxonomy = list_root_causes(task_repository)
    base, base_params = _base_sql(untracked_status(task_repository, options), task_repository, _scope(filters))
    where, params = _filter_sql(_resolve_key_filters(task_repository, filters), username,
                                [item['name'] for item in options['statuses'] if item['closed']], list_fields(task_repository))
    with task_repository.connection() as connection:
        calls = connection.execute(f'WITH calls AS ({base}) SELECT * FROM calls{where}', [*base_params, *params]).fetchall()
        notes = _comment_texts(connection, [str(call['call_key']) for call in calls if not call['root_domain']]) \
            if include_suggestions else {}
    site_of = node_site_lookup(task_repository)
    colors ={domain['name']: domain['color'] for domain in taxonomy['domains']}
    order = [domain['name'] for domain in taxonomy['domains']]
    counts = {'labelled': 0, 'suggested': 0, 'unclassified': 0}
    domains: dict[str, int] = {}
    categories: dict[tuple[str, str], int] = {}
    causes: dict[tuple[str, str], int] = {}
    matrices: dict[str, dict[str, dict[str, int]]] = {'call_type': {}, 'nr_mode': {}, 'technology': {}}
    nodes: dict[tuple[str, str, int], dict[str, Any]] = {}
    for call in calls:
        if source == 'analysts':
            domain, category, cause = (str(call[key] or '') for key in ('root_domain', 'root_category', 'root_cause'))
        else:
            mapped = source_root(call, source, taxonomy)
            domain, category, cause = mapped['domain'], mapped['category'], mapped['cause']
        if domain:
            counts['labelled'] += 1
        elif include_suggestions and (suggestion := suggest_root_cause(call, taxonomy, notes.get(str(call['call_key']), ''))):
            domain, category, cause = suggestion['domain'], suggestion['category'], suggestion['cause']
            counts['suggested'] += 1
        else:
            counts['unclassified'] += 1
        domain = domain or NOT_CLASSIFIED
        domains[domain] = domains.get(domain, 0) + 1
        categories[(domain, category)] = categories.get((domain, category), 0) + 1
        causes[(domain, cause)] = causes.get((domain, cause), 0) + 1
        groups = {'call_type': call_type(str(call['service']), str(call['test_name'] or '')),
                  'nr_mode': str(call['nr_mode'] or '') or 'Unknown', 'technology': str(call['technology'] or '') or 'Unknown'}
        for name, group in groups.items():
            row = matrices[name].setdefault(group, {})
            row[domain] = row.get(domain, 0) + 1
        node = serving_node(call['cell_id'])
        if node is None:
            continue
        operator = str(call['operator'] or '')
        entry = nodes.setdefault((operator, *node), {
            'operator': operator, 'type': node[0], 'id': node[1], 'calls': 0, 'domains': {},
            'vendor': str(call['vendor'] or ''), 'site': '', 'host': '', 'sites': Counter(),
        })
        entry['calls'] += 1
        entry['domains'][domain] = entry['domains'].get(domain, 0) + 1
        if details := site_of(call, node):
            entry['sites'][(details['site'], details['host'], details['vendor'])] += 1
    for entry in nodes.values():
        # The site of the node where most of its calls were (the same number can be a node of another network elsewhere).
        sites = entry.pop('sites')
        if sites:
            site, host, vendor = max(sites, key=lambda item: (sites[item], item))
            entry.update({key: value for key, value in (('site', site), ('host', host), ('vendor', vendor)) if value})

    def domain_key(name: str) -> tuple[int, int, str]:
        return (order.index(name) if name in order else len(order), -domains.get(name, 0), name.casefold())

    columns = sorted(domains, key=domain_key)

    def matrix(name: str, limit: int | None = None) -> list[dict[str, Any]]:
        rows = [{'name': group, 'counts': values, 'total': sum(values.values())} for group, values in matrices[name].items()]
        rows.sort(key=lambda row: (-row['total'], row['name'].casefold()))
        return rows[:limit] if limit else rows

    top_nodes = sorted(nodes.values(), key=lambda entry: (-entry['calls'], entry['operator'].casefold(), entry['id']))[:MAX_NODES]
    for entry in top_nodes:
        entry['top_domain'] = max(entry['domains'], key=lambda name: (entry['domains'][name], name)) if entry['domains'] else ''
        entry['node'] = f"{entry['type']} {entry['id']}"
    return {
        'include_suggestions': include_suggestions, 'source': source, 'provider': provider_texts(task_repository),
        'summary': {'total': len(calls), **counts},
        'domains': [{'value': name, 'count': domains[name], 'color': colors.get(name, '#b8c0c6')} for name in columns],
        'categories': [{'domain': domain, 'category': category or 'No category', 'value': category, 'count': count,
                        'color': colors.get(domain, '#b8c0c6')}
                       for (domain, category), count in sorted(categories.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
                       if domain != NOT_CLASSIFIED],
        'causes': [{'domain': domain, 'cause': cause or 'No cause', 'value': cause, 'count': count,
                    'color': colors.get(domain, '#b8c0c6')}
                   for (domain, cause), count in sorted(causes.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
                   if domain != NOT_CLASSIFIED],
        'columns': columns,
        'call_types': matrix('call_type'),
        'nr_modes': matrix('nr_mode'),
        'technologies': matrix('technology', MAX_RATS),
        'nodes': top_nodes,
    }


# The filters that also apply to every call (qualified or not) of the NQ rates.
RATE_FILTERS = ('datasets', 'service', 'campaign', 'operator', 'nr_mode')


def nq_rates(task_repository: Any, filters: dict[str, Any]) -> dict[str, Any]:
    """Calls, Non-Qualified Calls and their share for each campaign and operator.

    Every call counts once, in the most recent of the chosen CDRs that has it (a Final CDR before
    the Daily ones), so a call that is Completed there is no longer Non-Qualified. Only the CDRs,
    Service, Campaign, Operator and NR Mode filters apply: the other filters describe Non-Qualified
    Calls only. Operators show their Operator Map label.
    """
    scope = _scope(filters)
    services = _strings(filters.get('service'))
    campaigns = set(_strings(filters.get('campaign')))
    nr_modes = {'' if value in {UNASSIGNED, 'Unknown'} else value for value in _strings(filters.get('nr_mode'))}
    mapper = ValueMapper.from_repository(task_repository)
    # (Patterns, such as VF*, take every operator they match; see value_patterns. The operators the Operator Maps exclude
    # are left out.)
    operators = ValueSet([*(str(mapper.map(field_kind('operator'), value)) for value in _strings(filters.get('operator'))),
                          *(f'-{name}' for name in sorted(mapper.excluded_operators))])
    # NQ Calls in Scope Only: the calls out of scope (also the qualified ones) count neither as calls nor as NQ calls.
    in_scope = filters.get('in_scope') is True
    columns = ['service', 'campaign', 'operator', 'nr_mode', *(['region'] if in_scope else [])]
    where, params = [], []
    if services:
        where.append(f"p.service IN ({', '.join('?' for _ in services)})")
        params.extend(services)
    if scope:
        where.append(f"p.dataset_id IN ({', '.join('?' for _ in scope)})")
        params.extend(scope)
        source = f"""
            SELECT {', '.join(columns)}, COUNT(*) AS total, SUM(is_nq) AS nq FROM (
                SELECT {', '.join(f'p.{column}' for column in columns)}, p.is_nq, ROW_NUMBER() OVER (
                    PARTITION BY p.call_key ORDER BY s.combined_rank DESC, s.stage_rank DESC, s.data_date DESC,
                                                     p.dataset_id DESC) AS rn
                FROM {NQ_CALL_POPULATION_TABLE} p JOIN {NQ_CALL_SOURCES_TABLE} s ON s.dataset_id = p.dataset_id
                WHERE {' AND '.join(where)}
            ) WHERE rn = 1 GROUP BY {', '.join(columns)}"""
    else:
        where.append('p.is_latest = 1')
        source = f"""
            SELECT {', '.join(f'p.{column}' for column in columns)}, COUNT(*) AS total, SUM(p.is_nq) AS nq
            FROM {NQ_CALL_POPULATION_TABLE} p WHERE {' AND '.join(where)}
            GROUP BY {', '.join(f'p.{column}' for column in columns)}"""
    with task_repository.connection() as connection:
        # The counts change only when the indexed CDRs do, so the same sources and scope reuse them.
        sources = tuple(tuple(row) for row in connection.execute(
            f'SELECT dataset_id, revision, synced_at FROM {NQ_CALL_SOURCES_TABLE} ORDER BY dataset_id').fetchall())
        key = (str(task_repository.db_path), sources, tuple(sorted(scope or ())), tuple(sorted(services)), in_scope)
        with _rate_counts_guard:
            rows = _rate_counts_cache.get(key)
        if rows is None:
            rows = [tuple(row) for row in connection.execute(source, params).fetchall()]
            with _rate_counts_guard:
                if len(_rate_counts_cache) >= RATE_COUNTS_CACHE_SIZE:
                    _rate_counts_cache.pop(next(iter(_rate_counts_cache)))
                _rate_counts_cache[key] = rows
    if in_scope:
        reason = nq_prioritization.scope_of(task_repository, nq_prioritization.load_settings(task_repository))
        rows = [row[:4] + row[5:] for row in rows if not reason(row[4], row[3], row[2])[0]]
    groups: dict[str, dict[tuple[str, str], list[int]]] = {}
    for row_service, row_campaign, row_operator, row_nr_mode, row_total, row_nq in rows:
        campaign, operator = str(row_campaign or ''), str(mapper.map(field_kind('operator'), row_operator or '') or '')
        if campaigns and campaign not in campaigns:
            continue
        if operators and operator not in operators:
            continue
        if nr_modes and str(row_nr_mode or '') not in nr_modes:
            continue
        for service in (str(row_service), 'all'):
            cell = groups.setdefault(service, {}).setdefault((campaign, operator), [0, 0])
            cell[0] += int(row_total or 0)
            cell[1] += int(row_nq or 0)
    mapping_settings = task_repository.chart_mapping_settings()

    def matrix(service: str) -> dict[str, Any]:
        cells = groups.get(service, {})
        campaign_list = sorted({campaign for campaign, _operator in cells}, key=campaign_sort_key)
        operator_list = sorted({operator for _campaign, operator in cells}, key=lambda value: dimension_order_key(
            'operator', value, mapping_settings['operator_mapping_groups'], mapping_settings['vendor_mapping_groups']))

        def summary(total: int, nq: int) -> dict[str, Any]:
            return {'total': total, 'nq': nq, 'rate': round(nq * 100 / total, 2) if total else None}

        return {
            'service': service, 'label': 'All services' if service == 'all' else SERVICE_LABELS.get(service, service),
            'campaigns': campaign_list, 'operators': operator_list,
            # The colour of each operator in the Operator Maps, for its name.
            'operator_colors': {operator: str(group.get('color') or '') for operator in operator_list
                                if (group := mapping_group(operator, mapping_settings['operator_mapping_groups']))},
            'cells': {campaign: {operator: summary(*cells[(campaign, operator)]) for operator in operator_list
                                 if (campaign, operator) in cells} for campaign in campaign_list},
            'campaign_totals': {campaign: summary(*map(sum, zip(*(value for (row, _operator), value in cells.items()
                                                                   if row == campaign)))) for campaign in campaign_list},
            'operator_totals': {operator: summary(*map(sum, zip(*(value for (_row, column), value in cells.items()
                                                                   if column == operator)))) for operator in operator_list},
            'total': summary(*map(sum, zip(*cells.values()))) if cells else summary(0, 0),
        }

    ordered = [service for service in (*SERVICES, 'all') if service in groups]
    # "All services" adds calls and data tests: it is listed last, and only with several services.
    if len([service for service in ordered if service != 'all']) < 2:
        ordered = [service for service in ordered if service != 'all']
    return {'matrices': [matrix(service) for service in ordered], 'filters': list(RATE_FILTERS)}


# The sites of each operator with the most Non-Qualified Calls, and the fewest calls a site needs to be listed.
MAX_FAILURE_SITES = 25
MIN_SITE_CALLS = 5
NOT_REPORTED = 'Not reported'


def _population_counts(task_repository: Any, filters: dict[str, Any], fields: tuple[str, ...]) -> list[dict[str, Any]]:
    """Calls and Non-Qualified Calls of the latest version of every call per Service, Campaign, Operator, NR Mode and
    ``fields`` (of POPULATION_FIELDS). As the NQ rates, only the CDRs, Service, Campaign, Operator and NR Mode filters
    apply; Operators show their Operator Map label and Vendors their Vendor Map label."""
    scope = _scope(filters)
    services = _strings(filters.get('service'))
    campaigns = set(_strings(filters.get('campaign')))
    nr_modes = {'' if value in {UNASSIGNED, 'Unknown'} else value for value in _strings(filters.get('nr_mode'))}
    mapper = ValueMapper.from_repository(task_repository)
    # (Patterns, such as VF*, take every operator they match; see value_patterns. The operators the Operator Maps exclude
    # are left out.)
    operators = ValueSet([*(str(mapper.map(field_kind('operator'), value)) for value in _strings(filters.get('operator'))),
                          *(f'-{name}' for name in sorted(mapper.excluded_operators))])
    # NQ Calls in Scope Only: the calls out of scope (also the qualified ones) count nowhere.
    in_scope = filters.get('in_scope') is True
    columns = ['service', 'campaign', 'operator', 'nr_mode', *fields, *(['region'] if in_scope and 'region' not in fields else [])]
    where, params = [], []
    if services:
        where.append(f"p.service IN ({', '.join('?' for _ in services)})")
        params.extend(services)
    if scope:
        where.append(f"p.dataset_id IN ({', '.join('?' for _ in scope)})")
        params.extend(scope)
        source = f"""
            SELECT {', '.join(columns)}, COUNT(*) AS total, SUM(is_nq) AS nq FROM (
                SELECT {', '.join(f'p.{column}' for column in columns)}, p.is_nq, ROW_NUMBER() OVER (
                    PARTITION BY p.call_key ORDER BY s.combined_rank DESC, s.stage_rank DESC, s.data_date DESC,
                                                     p.dataset_id DESC) AS rn
                FROM {NQ_CALL_POPULATION_TABLE} p JOIN {NQ_CALL_SOURCES_TABLE} s ON s.dataset_id = p.dataset_id
                WHERE {' AND '.join(where)}
            ) WHERE rn = 1 GROUP BY {', '.join(columns)}"""
    else:
        where.append('p.is_latest = 1')
        source = f"""
            SELECT {', '.join(f'p.{column}' for column in columns)}, COUNT(*) AS total, SUM(p.is_nq) AS nq
            FROM {NQ_CALL_POPULATION_TABLE} p WHERE {' AND '.join(where)} GROUP BY {', '.join(f'p.{column}' for column in columns)}"""
    with task_repository.connection() as connection:
        sources = tuple(tuple(row) for row in connection.execute(
            f'SELECT dataset_id, revision, synced_at FROM {NQ_CALL_SOURCES_TABLE} ORDER BY dataset_id').fetchall())
        key = (str(task_repository.db_path), sources, tuple(sorted(scope or ())), tuple(sorted(services)), fields, in_scope)
        with _rate_counts_guard:
            rows = _rate_counts_cache.get(key)
        if rows is None:
            rows = [tuple(row) for row in connection.execute(source, params).fetchall()]
            with _rate_counts_guard:
                if len(_rate_counts_cache) >= RATE_COUNTS_CACHE_SIZE:
                    _rate_counts_cache.pop(next(iter(_rate_counts_cache)))
                _rate_counts_cache[key] = rows
    reason = nq_prioritization.scope_of(task_repository, nq_prioritization.load_settings(task_repository)) if in_scope else None
    counts = []
    for row in rows:
        entry = dict(zip([*columns, 'total', 'nq'], row))
        if reason is not None and reason(entry['region'], entry['nr_mode'], entry['operator'])[0]:
            continue
        if 'region' not in fields:
            entry.pop('region', None)
        entry['operator'] = str(mapper.map(field_kind('operator'), entry['operator'] or '') or '')
        if campaigns and str(entry['campaign'] or '') not in campaigns:
            continue
        if operators and entry['operator'] not in operators:
            continue
        if nr_modes and str(entry['nr_mode'] or '') not in nr_modes:
            continue
        if 'vendor' in entry:
            entry['vendor'] = str(mapper.map(field_kind('vendor'), entry['vendor'] or '') or '')
        counts.append(entry)
    return counts


def failure_breakdowns(task_repository: Any, filters: dict[str, Any], username: str) -> dict[str, Any]:
    """How and where the Non-Qualified Calls fail, per Service and Operator:

    - ``types``: the result of the filtered calls (Failed, Dropped, Cutoff…) per environment, as a share of every call;
    - ``technology``: the technology at the failure (else of the call) against the NetCheck failure classification;
    - ``serving``: the calls and Non-Qualified Calls per Vendor and host network of the serving cell, with their shares;
    - ``sites``: the serving sites with the most Non-Qualified Calls and their rate.
    The shares and rates divide by every call of the CDRs, Service, Campaign, Operator and NR Mode filters.
    """
    rows, _context = _filtered_calls(task_repository, filters, username,
                                     'service, operator, environment, result, technology, failure_technology, failure_classification')
    mapping_settings = task_repository.chart_mapping_settings()

    def operator_order(values: set[str]) -> list[str]:
        return sorted(values, key=lambda value: dimension_order_key('operator', value, mapping_settings['operator_mapping_groups'],
                                                                     mapping_settings['vendor_mapping_groups']))

    colors = {operator: str(group.get('color') or '') for operator in {str(row['operator'] or '') for row in rows}
              if (group := mapping_group(operator, mapping_settings['operator_mapping_groups']))}
    population = _population_counts(task_repository, filters, ('environment',))
    calls: dict[tuple[str, str, str], int] = {}
    for entry in population:
        key = (str(entry['service']), entry['operator'], str(entry['environment'] or ''))
        calls[key] = calls.get(key, 0) + int(entry['total'] or 0)
    types = []
    for service in SERVICES:
        members = [row for row in rows if row['service'] == service]
        if not members:
            continue
        results = [name for name, _count in Counter(str(row['result'] or NOT_REPORTED) for row in members).most_common()]
        grouped: dict[tuple[str, str], Counter] = {}
        for row in members:
            grouped.setdefault((str(row['operator'] or ''), str(row['environment'] or '')), Counter())[str(row['result'] or NOT_REPORTED)] += 1
        table = []
        for operator in operator_order({operator for operator, _environment in grouped}):
            for environment in sorted({environment for name, environment in grouped if name == operator}):
                counts = grouped[(operator, environment)]
                total = calls.get((service, operator, environment), 0)
                table.append({'operator': operator, 'environment': environment or NOT_REPORTED, 'calls': total,
                              'nq': sum(counts.values()), 'counts': dict(counts),
                              'rates': {name: round(count * 100 / total, 2) if total else None for name, count in counts.items()}})
        types.append({'service': service, 'label': SERVICE_LABELS[service], 'results': results, 'rows': table})
    technology = []
    for service in SERVICES:
        members = [row for row in rows if row['service'] == service]
        if not members:
            continue
        cells: dict[str, dict[str, Counter]] = {}
        for row in members:
            name = str(row['failure_technology'] or row['technology'] or NOT_REPORTED)
            cells.setdefault(str(row['operator'] or ''), {}).setdefault(name, Counter())[
                str(row['failure_classification'] or NOT_CLASSIFIED)] += 1
        technologies = [name for name, _count in Counter(
            name for by_name in cells.values() for name, counts in by_name.items() for _ in range(sum(counts.values()))).most_common()]
        classes = [name for name, _count in Counter(
            name for by_name in cells.values() for counts in by_name.values() for name in counts.elements()).most_common()]
        technology.append({'service': service, 'label': SERVICE_LABELS[service], 'operators': operator_order(set(cells)),
                           'technologies': technologies, 'classes': classes,
                           'cells': {operator: {name: dict(counts) for name, counts in by_name.items()}
                                     for operator, by_name in cells.items()}})
    serving_counts = _population_counts(task_repository, filters, ('vendor', 'host_network'))
    serving = []
    for service in SERVICES:
        members = [entry for entry in serving_counts if entry['service'] == service]
        if not members or all(not entry['vendor'] and not entry['host_network'] for entry in members):
            continue
        by_operator: dict[str, dict[tuple[str, str], list[int]]] = {}
        for entry in members:
            cell = by_operator.setdefault(entry['operator'], {}).setdefault(
                (entry['vendor'] or NOT_REPORTED, entry['host_network'] or NOT_REPORTED), [0, 0])
            cell[0] += int(entry['total'] or 0)
            cell[1] += int(entry['nq'] or 0)
        operators = []
        for operator in operator_order(set(by_operator)):
            cells = by_operator[operator]
            total_calls, total_nq = sum(value[0] for value in cells.values()), sum(value[1] for value in cells.values())
            operators.append({'operator': operator, 'calls': total_calls, 'nq': total_nq, 'rows': [
                {'vendor': vendor, 'host_network': host, 'calls': value[0], 'nq': value[1],
                 'rate': round(value[1] * 100 / value[0], 2) if value[0] else None,
                 'calls_share': round(value[0] * 100 / total_calls, 1) if total_calls else None,
                 'nq_share': round(value[1] * 100 / total_nq, 1) if total_nq else None}
                for (vendor, host), value in sorted(cells.items(), key=lambda item: -item[1][1])]})
        serving.append({'service': service, 'label': SERVICE_LABELS[service], 'operators': operators})
    site_counts = _population_counts(task_repository, filters, ('host_network', 'site_id', 'vendor', 'city'))
    sites_by_operator: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    for entry in site_counts:
        if not entry['site_id']:
            continue
        site = sites_by_operator.setdefault(entry['operator'], {}).setdefault(
            (entry['host_network'] or '', entry['site_id']), {'calls': 0, 'nq': 0, 'vendors': Counter(), 'cities': Counter()})
        site['calls'] += int(entry['total'] or 0)
        site['nq'] += int(entry['nq'] or 0)
        site['vendors'][entry['vendor'] or ''] += int(entry['total'] or 0)
        site['cities'][str(entry['city'] or '')] += int(entry['total'] or 0)
    sites = []
    for operator in operator_order(set(sites_by_operator)):
        listed = [(key, value) for key, value in sites_by_operator[operator].items() if value['nq'] and value['calls'] >= MIN_SITE_CALLS]
        listed.sort(key=lambda item: (-item[1]['nq'], -item[1]['nq'] / item[1]['calls']))
        if listed:
            sites.append({'operator': operator, 'rows': [
                {'host_network': host, 'site_id': site, 'calls': value['calls'], 'nq': value['nq'],
                 'rate': round(value['nq'] * 100 / value['calls'], 2),
                 'vendor': value['vendors'].most_common(1)[0][0], 'city': value['cities'].most_common(1)[0][0]}
                for (host, site), value in listed[:MAX_FAILURE_SITES]]})
    return {'types': types, 'technology': technology, 'serving': serving, 'sites': sites, 'operator_colors': colors,
            'min_site_calls': MIN_SITE_CALLS}


def indexed_datasets(task_repository: Any) -> list[dict[str, Any]]:
    with task_repository.connection() as connection:
        counts = {int(row['dataset_id']): int(row['call_count'])
                  for row in connection.execute(f'SELECT dataset_id, call_count FROM {NQ_CALL_SOURCES_TABLE}').fetchall()}
    return [
        {'id': int(row['id']), 'name': str(row['file_name']), 'service': str(row['dataset_kind']),
         'nr_mode': _text(row['nr_mode']), 'calls': counts.get(int(row['id']), 0)}
        for row in sorted(_cdr_datasets(task_repository), key=lambda item: str(item['file_name']).casefold())
    ]


# ---------------------------------------------------------------------------
# One call: details, follow-up and comments
# ---------------------------------------------------------------------------
def _call_row(connection: Any, call_key: str, default: str, task_repository: Any) -> Any:
    """A call (its latest version) or a Speech sample, with its follow-up."""
    base, params = _base_sql(default, task_repository)
    row = connection.execute(f'WITH calls AS ({base}) SELECT * FROM calls WHERE call_key = ?', [*params, call_key]).fetchone()
    if row is not None:
        return row
    sample, sample_params = _sample_sql(default, task_repository)
    return connection.execute(
        f'WITH samples AS ({sample}) SELECT * FROM samples WHERE call_key = ? ORDER BY dataset_id DESC LIMIT 1',
        [*sample_params, call_key]).fetchone()


def _call_versions(connection: Any, call_key: str, spellings: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Every CDR that contains the call: Final, Weekly or Daily, its newest data, and the call's result in it (its
    Failure Classification with the spelling of ``spellings``)."""
    spellings = spellings or {}
    rows = connection.execute(f"""
        SELECT p.dataset_id, p.is_nq, p.is_latest, s.stage_rank, s.data_date, d.file_name, dp.dataset_kind, dp.cdr_stage,
               (SELECT c.result FROM {NQ_CALLS_TABLE} c WHERE c.call_key = p.call_key AND c.dataset_id = p.dataset_id
                ORDER BY c.start_time LIMIT 1) AS result,
               (SELECT c.failure_classification FROM {NQ_CALLS_TABLE} c WHERE c.call_key = p.call_key AND c.dataset_id = p.dataset_id
                ORDER BY c.start_time LIMIT 1) AS failure_classification
        FROM {NQ_CALL_POPULATION_TABLE} p
        JOIN {NQ_CALL_SOURCES_TABLE} s ON s.dataset_id = p.dataset_id
        LEFT JOIN datasets d ON d.id = p.dataset_id
        LEFT JOIN dataset_profiles dp ON dp.dataset_id = p.dataset_id
        WHERE p.call_key = ?
        ORDER BY s.combined_rank DESC, s.stage_rank DESC, s.data_date DESC, p.dataset_id DESC
    """, (call_key,)).fetchall()
    return [{
        'dataset_id': int(row['dataset_id']), 'name': str(row['file_name'] or ''),
        'stage': 'Final' if int(row['stage_rank']) else CDR_STAGE_LABELS.get(
            dataset_cdr_stage(row['dataset_kind'], row['cdr_stage'], row['file_name']) or '', 'Daily'),
        'data_date': str(row['data_date'] or ''),
        'non_qualified': bool(row['is_nq']), 'latest': bool(row['is_latest']),
        'result': str(row['result'] or ('Completed' if not row['is_nq'] else '')),
        'failure_classification': spellings.get(str(row['failure_classification'] or ''), str(row['failure_classification'] or '')),
    } for row in rows]


def _call_samples(connection: Any, call: dict[str, Any], default: str, task_repository: Any) -> list[dict[str, Any]]:
    """The Non-Qualified samples of a Speech call in the CDR of its shown version, with their follow-up."""
    if call.get('service') != 'speech' or call.get('parent_key'):
        return []
    sample, params = _sample_sql(default, task_repository)
    rows = connection.execute(
        f'WITH samples AS ({sample}) SELECT * FROM samples WHERE parent_key = ? AND dataset_id = ? ORDER BY start_time, source_row_id',
        [*params, call['call_key'], int(call['dataset_id'])]).fetchall()
    return [_call_payload(row) for row in rows]


def _comment_payload(row: Any) -> dict[str, Any]:
    deleted = bool(row['deleted_at'])
    return {
        'id': int(row['id']), 'body': '' if deleted else str(row['body']), 'created_by': str(row['created_by']),
        'created_at': str(row['created_at']), 'edited_by': str(row['edited_by']), 'edited_at': str(row['edited_at']),
        'deleted_by': str(row['deleted_by']), 'deleted_at': str(row['deleted_at']),
    }


def call_detail(task_repository: Any, call_key: str) -> dict[str, Any] | None:
    """A call or a Speech sample: its fields, follow-up, comments, history, CDR versions and samples."""
    options = list_options(task_repository)
    default = untracked_status(task_repository, options)
    definitions = list_fields(task_repository)
    with task_repository.connection() as connection:
        row = _call_row(connection, call_key, default, task_repository)
        if row is None:
            return None
        call = _call_payload(row)
        versions = _call_versions(connection, str(call.get('parent_key') or call_key),
                                  json.loads(_value_maps(task_repository)['failure_classification']))
        samples = _call_samples(connection, call, default, task_repository)
        learned = learned_decisions(connection)
        parent = None
        if call.get('parent_key'):
            parent_row = _call_row(connection, str(call['parent_key']), default, task_repository)
            parent = _call_payload(parent_row) if parent_row is not None else None
        comments = [_comment_payload(item) for item in connection.execute(
            f'SELECT * FROM {NQ_CALL_COMMENTS_TABLE} WHERE call_key = ? ORDER BY id', (call_key,),
        ).fetchall()]
        history = [
            {'id': int(item['id']), 'field': str(item['field']), 'old_value': str(item['old_value']),
             'new_value': str(item['new_value']), 'changed_by': str(item['changed_by']), 'changed_at': str(item['changed_at'])}
            for item in connection.execute(
                f"SELECT * FROM {NQ_CALL_HISTORY_TABLE} WHERE call_key = ? ORDER BY id", (call_key,),
            ).fetchall()
        ]
        table = f"dataset_rows_{int(call['dataset_id'])}"
        try:
            source = connection.execute(f'SELECT * FROM {_quote(table)} WHERE rowid = ?', (int(call['source_row_id']),)).fetchone()
        except Exception:  # noqa: BLE001 - the CDR may have been removed since it was indexed.
            source = None
        dataset = connection.execute('SELECT file_name FROM datasets WHERE id = ?', (int(call['dataset_id']),)).fetchone()
    fields = []
    if source is not None:
        fields = [[key, _text(source[key])] for key in source.keys() if _text(source[key])]
    call['dataset_name'] = str(dataset['file_name']) if dataset else ''
    notes = '\n'.join(comment['body'] for comment in comments if not comment['deleted_at'])
    taxonomy = list_root_causes(task_repository)
    call['suggested_root_cause'] = suggest_root_cause(call, taxonomy, notes)
    call['rca_recommendation'] = recommendation_for(call, taxonomy, notes, learned)
    # CDR columns of the catalog are read from the CDR row itself.
    source_values = {key: _text(source[key]) for key in source.keys()} if source is not None else {}
    call['extra'] = {**source_values, **(call.get('extra') or {})}
    call['values'] = {field['key']: catalog_value(field, call, call.get('rca'), call.get('fields')) for field in definitions}
    # Values of the CDR proposed for the empty fields that name one (for example the failure position).
    call['proposals'] = {field['key']: _text(_call_value(call, field['suggest_from'])) for field in definitions
                         if field['source'] == 'user' and field.get('suggest_from') and not (call.get('fields') or {}).get(field['key'])
                         and _text(_call_value(call, field['suggest_from']))}
    for sample in samples:
        sample['suggested_root_cause'] = suggest_root_cause(sample, taxonomy, '')
        sample['rca_recommendation'] = recommendation_for(sample, taxonomy, '', learned)
    return {'call': call, 'comments': comments, 'history': history, 'fields': fields, 'versions': versions,
            'samples': samples, 'parent': parent}


def _record_history(connection: Any, call_key: str, field: str, old: str, new: str, username: str, when: str) -> None:
    connection.execute(
        f'INSERT INTO {NQ_CALL_HISTORY_TABLE} (uid, call_key, field, old_value, new_value, changed_by, changed_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?)',
        (uuid.uuid4().hex, call_key, field, old, new, username, when),
    )


def _validate_changes(changes: dict[str, Any], options: dict[str, list[dict[str, Any]]], users: set[str],
                      taxonomy: dict[str, Any]) -> dict[str, str]:
    validated: dict[str, str] = {}
    if 'status' in changes:
        names = {item['name'].casefold(): item['name'] for item in options['statuses']}
        status = names.get(str(changes.get('status') or '').strip().casefold())
        if not status:
            raise ValueError('Choose one of the configured statuses.')
        validated['status'] = status
        validated['status_mode'] = 'manual'
    if changes.get('status_mode') == 'auto':
        validated.pop('status', None)
        validated['status_mode'] = 'auto'
    if 'team' in changes:
        names = {item['name'].casefold(): item['name'] for item in options['teams']}
        value = str(changes.get('team') or '').strip()
        if value and value.casefold() not in names:
            raise ValueError('Choose one of the configured teams.')
        validated['team'] = names.get(value.casefold(), '')
    if 'assignee' in changes:
        value = str(changes.get('assignee') or '').strip()
        lookup = {name.casefold(): name for name in users}
        if value and value.casefold() not in lookup:
            raise ValueError('Choose a user with access to this workspace.')
        validated['assignee'] = lookup.get(value.casefold(), '')
    for key, plural, title in (('root_category', 'categories', 'Root Categories'), ('root_cause', 'causes', 'Root Causes')):
        if key in changes:
            names = {item['name'].casefold(): item['name'] for item in taxonomy[plural]}
            value = str(changes.get(key) or '').strip()
            if value and value.casefold() not in names:
                raise ValueError(f'Choose one of the {title} of the root cause catalog.')
            validated[key] = names.get(value.casefold(), '')
    if changes.get('apply_recommendation') or changes.get('apply_suggestion'):
        validated['apply_recommendation'] = '1'
    if not validated and not changes.get('fields'):
        raise ValueError('There is nothing to change.')
    return validated


def _validate_field_changes(changes: dict[str, Any], definitions: list[dict[str, Any]]) -> dict[str, str]:
    values = changes.get('fields')
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError('The analysis fields are invalid.')
    known = {field['key']: field for field in definitions}
    unknown = [str(key) for key in values if str(key) not in known]
    if unknown:
        raise ValueError(f'Unknown fields: {", ".join(unknown)}.')
    return {str(key): _field_value(known[str(key)], value) for key, value in values.items()}


class TrackingConflict(Exception):
    """Another user changed the call after it was loaded."""


def learned_decisions(connection: Any) -> dict[tuple[str, str, str], dict[tuple[str, str], set[str]]]:
    """For the RCA values of every call with a root category or cause, the categories and causes the analysts chose,
    with the calls that chose each one (so a call counts once and never for itself)."""
    learned: dict[tuple[str, str, str], dict[tuple[str, str], set[str]]] = {}
    rows = connection.execute(f"""
        SELECT t.call_key, t.root_category, t.root_cause, c.failure_category, c.failure_classification, c.failure_subcategory,
               COALESCE(r.values_json, '{{}}') AS rca_json, COALESCE(d.category, '') AS dta_category, COALESCE(d.cause, '') AS dta_cause
        FROM {NQ_CALL_TRACKING_TABLE} t
        JOIN {NQ_CALLS_TABLE} c ON c.call_key = t.call_key
        LEFT JOIN {NQ_RCA_RESULTS_TABLE} r ON c.join_id <> '' AND r.join_id = lower(c.join_id)
        LEFT JOIN {NQ_DTA_RESULTS_TABLE} d ON d.dataset_id = c.dataset_id AND d.source_row_id = c.source_row_id
        WHERE t.root_category <> '' OR t.root_cause <> ''
        GROUP BY t.call_key
    """).fetchall()
    for row in rows:
        choice = (str(row['root_category'] or ''), str(row['root_cause'] or ''))
        try:
            rca = json.loads(row['rca_json'] or '{}')
        except (TypeError, ValueError):
            rca = {}
        pairs = [('netcheck', str(row['failure_category'] or row['failure_classification'] or ''), str(row['failure_subcategory'] or '')),
                 ('script', str(rca.get('rca_category') or rca.get('auto_rca_category_a') or ''),
                  str(rca.get('rca_cause') or rca.get('auto_rca_subcategory_a') or '')),
                 ('dta', str(row['dta_category'] or ''), str(row['dta_cause'] or ''))]
        for source, category, cause in pairs:
            if category or cause:
                learned.setdefault(nq_rca.learned_key(source, category, cause), {}).setdefault(choice, set()).add(str(row['call_key']))
    return learned


def recommendation_for(call: dict[str, Any], taxonomy: dict[str, Any], comments: str,
                       learned: dict[tuple[str, str, str], dict[tuple[str, str], set[str]]]) -> dict[str, Any]:
    return nq_rca.recommend(call, call.get('rca') or {}, taxonomy, taxonomy.get('rule') or DEFAULT_ROOT_CAUSE_RULE,
                            comments, learned, dta_of(call))


def update_tracking(
    task_repository: Any, call_keys: list[str], changes: dict[str, Any], username: str, users: set[str],
    expected_version: int | None = None,
) -> list[str]:
    """Apply follow-up and field changes; returns the calls that changed.

    A team with members only accepts them as assignees: assigning anybody else is refused, and
    moving a call to such a team clears an assignee who is not a member. ``apply_recommendation``
    gives the calls without a root category and cause the recommended ones, and a root cause chosen for
    a call without root category brings the category it is mapped to. Choosing a status sets
    it by hand; otherwise (or after going back to automatic) the status rules set it from the
    fields. A call cannot be closed without the fields required to close it.
    """
    options = list_options(task_repository)
    taxonomy = list_root_causes(task_repository)
    definitions = list_fields(task_repository)
    validated = _validate_changes(changes, options, users, taxonomy)
    field_changes = _validate_field_changes(changes, definitions)
    required = [field for field in definitions if field['required_to_close']]
    apply_recommendation = bool(validated.pop('apply_recommendation', None))
    closed = {item['name'].casefold() for item in options['statuses'] if item['closed']}
    members = team_members(options)
    default = untracked_status(task_repository, options)
    fallback = default_status(options)
    rules = status_rules(task_repository)
    when = now_iso()
    changed: list[str] = []
    with task_repository.connection() as connection:
        learned = learned_decisions(connection) if apply_recommendation else {}
        for call_key in dict.fromkeys(call_keys):
            row = _call_row(connection, call_key, default, task_repository)
            if row is None:
                raise LookupError('The call is no longer available. Refresh the list.')
            if expected_version is not None and int(row['version']) != int(expected_version):
                raise TrackingConflict(
                    f"{row['updated_by'] or 'Another user'} changed this call at {row['updated_at']}. Review it and try again."
                )
            current = {field: str(row[field]) for field in TRACKING_FIELDS}
            current.update(validated)
            if apply_recommendation:
                recommended = None
                if not current['root_category'] and not current['root_cause']:
                    call = _call_payload(row)
                    notes = _comment_texts(connection, [call_key]).get(call_key, '')
                    recommended = recommendation_for(call, taxonomy, notes, learned)['recommendation']
                if recommended:
                    current['root_category'], current['root_cause'] = recommended['category'], recommended['cause']
                elif not validated and not field_changes:
                    # Nothing to accept: the call stays as it is.
                    continue
            # A root cause chosen for a call without root category brings the category the cause is mapped to.
            if validated.get('root_cause') and 'root_category' not in validated and not current['root_category']:
                current['root_category'] = root_category_of(taxonomy, current['root_cause'])
            current['root_domain'] = domain_of(taxonomy, current['root_category'], current['root_cause'])
            # An assignee chosen alone brings the call to their team (the first one when they are in several),
            # unless the call already has a team they belong to.
            if validated.get('assignee') and 'team' not in validated:
                current_members = members.get(current['team'].casefold())
                if not current['team'] or (current_members and current['assignee'].casefold() not in current_members):
                    team = next((item['name'] for item in options['teams']
                                 if current['assignee'].casefold() in members.get(item['name'].casefold(), set())), '')
                    if team:
                        current['team'] = team
            allowed = members.get(current['team'].casefold())
            if allowed and current['assignee'] and current['assignee'].casefold() not in allowed:
                if 'assignee' in validated:
                    raise ValueError(f'{current["assignee"]} is not a member of the {current["team"]} team.')
                current['assignee'] = ''
            stored = field_values(connection, [call_key]).get(call_key, {})
            field_differences = {key: value for key, value in field_changes.items() if stored.get(key, '') != value}
            merged = {**stored, **field_changes}
            if current['status_mode'] != 'manual':
                current['status'] = evaluate_status(rules, _status_inputs(row, merged, definitions, current, True), fallback)
            differences = {field: value for field, value in current.items() if str(row[field]) != value}
            if not differences and not field_differences:
                continue
            closing = current['status'].casefold() in closed
            if (taxonomy['require_to_close'] and closing and not current['root_category']
                    and ('status' in differences or 'root_category' in differences)):
                raise ValueError(f'Choose a root category before closing a call as {current["status"]}.')
            if closing and required:
                missing = [field['label'] for field in required if not merged.get(field['key'])]
                if missing and ('status' in differences or field_differences):
                    raise ValueError(f'Fill {", ".join(missing)} before closing a call as {current["status"]}.')
            connection.execute(
                f'INSERT INTO {NQ_CALL_TRACKING_TABLE} (call_key, status, team, assignee, root_domain, root_category, root_cause, '
                'status_mode, version, updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) ON CONFLICT(call_key) DO UPDATE SET '
                'status = excluded.status, team = excluded.team, assignee = excluded.assignee, '
                'root_domain = excluded.root_domain, root_category = excluded.root_category, root_cause = excluded.root_cause, '
                'status_mode = excluded.status_mode, version = version + 1, '
                'updated_by = excluded.updated_by, updated_at = excluded.updated_at',
                (call_key, current['status'], current['team'], current['assignee'], current['root_domain'],
                 current['root_category'], current['root_cause'], current['status_mode'], username, when),
            )
            automatic = current['status_mode'] != 'manual'
            for field, value in differences.items():
                # The domain follows the category and cause; a status chosen by hand tells its mode itself; a status
                # set by the rules is recorded after the changes that moved it.
                if field == 'root_domain' or (field == 'status_mode' and value == 'manual') or (field == 'status' and automatic):
                    continue
                _record_history(connection, call_key, field, str(row[field]), value, username, when)
            for key, value in field_differences.items():
                connection.execute(
                    f'INSERT INTO {NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, ?) '
                    'ON CONFLICT(call_key, field_key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, '
                    'updated_at = excluded.updated_at', (call_key, key, value, username, when))
                _record_history(connection, call_key, f'field:{key}', stored.get(key, ''), value, username, when)
            if 'status' in differences and automatic:
                _record_history(connection, call_key, 'status_auto', str(row['status']), differences['status'], username, when)
            changed.append(call_key)
    return changed


def delete_history(task_repository: Any, username: str, *, call_keys: list[str] | None = None,
                   entry_ids: list[int] | None = None) -> int:
    """Delete history entries: some entries by id, or every entry of some calls; returns how many were deleted.

    The follow-up values and the comments of the calls stay as they are.
    """
    keys = list(dict.fromkeys(str(key) for key in call_keys or [] if str(key)))
    ids = list(dict.fromkeys(int(entry) for entry in entry_ids or []))
    if not keys and not ids:
        raise ValueError('Choose the history to delete.')
    deleted = 0
    with task_repository.connection() as connection:
        for column, values in (('call_key', keys), ('id', ids)):
            for start in range(0, len(values), 500):
                chunk = values[start:start + 500]
                deleted += connection.execute(
                    f"DELETE FROM {NQ_CALL_HISTORY_TABLE} WHERE {column} IN ({', '.join('?' for _ in chunk)})", chunk,
                ).rowcount
    if deleted and hasattr(task_repository, 'try_add_log'):
        scope = f'{len(keys)} calls' if keys else f'{len(ids)} entries'
        task_repository.try_add_log(username, 'nq_call_history_delete', f'Non-Qualified Calls history deleted ({scope}, {deleted} entries).')
    return deleted


def _clean_comment(body: Any) -> str:
    text = str(body or '').replace('\r\n', '\n').strip()
    if not text:
        raise ValueError('Write a comment first.')
    if len(text) > MAX_COMMENT_LENGTH:
        raise ValueError(f'Comments are limited to {MAX_COMMENT_LENGTH} characters.')
    return text


def add_comment(task_repository: Any, call_key: str, body: Any, username: str) -> dict[str, Any]:
    text = _clean_comment(body)
    options = list_options(task_repository)
    with task_repository.connection() as connection:
        if _call_row(connection, call_key, untracked_status(task_repository, options), task_repository) is None:
            raise LookupError('The call is no longer available. Refresh the list.')
        cursor = connection.execute(
            f'INSERT INTO {NQ_CALL_COMMENTS_TABLE} (uid, call_key, body, created_by, created_at) VALUES (?, ?, ?, ?, ?)',
            (uuid.uuid4().hex, call_key, text, username, now_iso()),
        )
        row = connection.execute(f'SELECT * FROM {NQ_CALL_COMMENTS_TABLE} WHERE id = ?', (cursor.lastrowid,)).fetchone()
    # A comment attends the call: its automatic status follows.
    recompute_statuses(task_repository, username, [call_key])
    return _comment_payload(row)


def _comment_for_change(connection: Any, comment_id: int, username: str, moderator: bool) -> Any:
    row = connection.execute(f'SELECT * FROM {NQ_CALL_COMMENTS_TABLE} WHERE id = ?', (comment_id,)).fetchone()
    if row is None or row['deleted_at']:
        raise LookupError('The comment no longer exists.')
    if str(row['created_by']).casefold() != username.casefold() and not moderator:
        raise PermissionError('Only the author or an admin can change this comment.')
    return row


def edit_comment(task_repository: Any, comment_id: int, body: Any, username: str, moderator: bool) -> dict[str, Any]:
    text = _clean_comment(body)
    when = now_iso()
    with task_repository.connection() as connection:
        row = _comment_for_change(connection, comment_id, username, moderator)
        if str(row['body']) != text:
            connection.execute(
                f'UPDATE {NQ_CALL_COMMENTS_TABLE} SET body = ?, edited_by = ?, edited_at = ? WHERE id = ?',
                (text, username, when, comment_id),
            )
            _record_history(connection, str(row['call_key']), 'comment_edit', str(row['body']), text, username, when)
        updated = connection.execute(f'SELECT * FROM {NQ_CALL_COMMENTS_TABLE} WHERE id = ?', (comment_id,)).fetchone()
    return _comment_payload(updated)


def delete_comment(task_repository: Any, comment_id: int, username: str, moderator: bool) -> dict[str, Any]:
    """Comments are hidden, not erased: the history keeps their text."""
    when = now_iso()
    with task_repository.connection() as connection:
        row = _comment_for_change(connection, comment_id, username, moderator)
        connection.execute(
            f'UPDATE {NQ_CALL_COMMENTS_TABLE} SET deleted_by = ?, deleted_at = ? WHERE id = ?', (username, when, comment_id),
        )
        _record_history(connection, str(row['call_key']), 'comment_delete', str(row['body']), '', username, when)
        updated = connection.execute(f'SELECT * FROM {NQ_CALL_COMMENTS_TABLE} WHERE id = ?', (comment_id,)).fetchone()
    return _comment_payload(updated)


# ---------------------------------------------------------------------------
# Ericsson RCA results: imported by JOIN_ID
# ---------------------------------------------------------------------------
def import_rca_results(task_repository: Any, content: bytes, file_name: str, username: str, *, replace: bool = False,
                       dry_run: bool = False, add_to_catalog: bool = False) -> dict[str, Any]:
    """Read an RCA results file and (unless ``dry_run``) store its rows by JOIN_ID; ``replace`` forgets the previous ones
    and ``add_to_catalog`` adds the script categories and causes the Root Cause Catalog has no entry for, in the domain
    proposed for each one."""
    parsed = nq_rca.read_rca_file(content, file_name)
    results = parsed['results']
    ensure_nq_tables(task_repository)
    with task_repository.connection() as connection:
        known = {str(row[0]) for row in connection.execute(
            f"SELECT DISTINCT lower(join_id) FROM {NQ_CALLS_TABLE} WHERE join_id <> ''")}
        matched = sum(1 for item in results if item['join_id'].casefold() in known)
        existing = {str(row[0]) for row in connection.execute(f'SELECT join_id FROM {NQ_RCA_RESULTS_TABLE}')}
        unmapped = nq_rca.unmapped_values(results, _read_root_catalog(connection))
        summary = {
            'file_name': file_name, 'rows': len(results), 'matched': matched, 'unmatched': len(results) - matched,
            'columns': parsed['columns'], 'extra': parsed['extra'], 'skipped': parsed['skipped'], 'duplicates': parsed['duplicates'],
            'new': sum(1 for item in results if item['join_id'].casefold() not in existing),
            'replace': replace, 'unmapped': unmapped, 'added_to_catalog': [],
            'preview': [{'join_id': item['join_id'], **item['values']} for item in results[:8]],
        }
        if dry_run:
            return summary
        when = now_iso()
        if replace:
            connection.execute(f'DELETE FROM {NQ_RCA_RESULTS_TABLE}')
        connection.executemany(
            f'INSERT OR REPLACE INTO {NQ_RCA_RESULTS_TABLE} (join_id, original_join_id, values_json, source_file, imported_by, imported_at) '
            'VALUES (?, ?, ?, ?, ?, ?)',
            [(item['join_id'].casefold(), item['join_id'], json.dumps(item['values'], ensure_ascii=False), file_name, username, when)
             for item in results])
        if add_to_catalog and unmapped:
            catalog = nq_catalog.stored_root_catalog(_read_root_catalog(connection))
            for item in unmapped:
                catalog['categories' if item['kind'] == 'category' else 'causes'].append(
                    {'name': item['name'], 'domain': item['domain'], 'keywords': []})
            _write_root_catalog(connection, nq_catalog.normalize_root_catalog(catalog))
            summary['added_to_catalog'] = unmapped
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_rca_import', json.dumps(
            {'file': file_name, 'rows': len(results), 'matched': matched, 'replace': replace,
             'added_to_catalog': [item['name'] for item in summary['added_to_catalog']]}))
    return summary


def rca_results_summary(task_repository: Any) -> dict[str, Any]:
    """The imported RCA results: how many, how many match a call, and each imported file."""
    with task_repository.connection() as connection:
        total = connection.execute(f'SELECT COUNT(*) FROM {NQ_RCA_RESULTS_TABLE}').fetchone()[0]
        # The JOIN_IDs of the calls are read once (a lookup of lower(join_id) per result scanned every call each time).
        matched = connection.execute(
            f"SELECT COUNT(*) FROM {NQ_RCA_RESULTS_TABLE} WHERE join_id IN "
            f"(SELECT lower(join_id) FROM {NQ_CALLS_TABLE} WHERE join_id <> '')").fetchone()[0]
        files = [{'name': str(row['source_file']), 'rows': int(row['rows']), 'imported_at': str(row['imported_at']),
                  'imported_by': str(row['imported_by'])}
                 for row in connection.execute(
                     f'SELECT source_file, COUNT(*) AS rows, MAX(imported_at) AS imported_at, MAX(imported_by) AS imported_by '
                     f'FROM {NQ_RCA_RESULTS_TABLE} GROUP BY source_file ORDER BY imported_at DESC')]
    return {'total': int(total or 0), 'matched': int(matched or 0), 'files': files, 'format': nq_rca.RCA_FILE_FORMAT_HELP}


def clear_rca_results(task_repository: Any, username: str) -> int:
    with task_repository.connection() as connection:
        deleted = connection.execute(f'DELETE FROM {NQ_RCA_RESULTS_TABLE}').rowcount
    if hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_rca_clear', f'{deleted} Ericsson RCA results deleted.')
    return int(deleted or 0)


# ---------------------------------------------------------------------------
# Analyses of the previous tool: imported by JOIN_ID (admins and super-admins)
# ---------------------------------------------------------------------------
# Follow-up columns named otherwise than their catalog field; the catalog fields are found by name or key.
ANALYSES_TRACKING = ('status', 'team', 'assignee', 'root_category', 'root_cause')
MAX_ANALYSES_ISSUES = 20
# The equivalences reviewed for the analyses of the previous tool: what each value of their workbooks becomes.
ANALYSES_EQUIVALENCES_STATE_KEY = 'nq_analyses_equivalences'
# Columns of the analysis that repeat a value the tool has from the CDR (by the identity of their name): the import
# note leaves them out when they say what the CDR of the call says.
ANALYSES_CDR_COPIES = {
    'campaign': 'campaign', 'region': 'region', 'operator': 'operator', 'city': 'city', 'vendor': 'vendor',
    'netcheckfailureclassification': 'failure_classification', 'failureclassification': 'failure_classification',
    'netcheckcategory': 'failure_category', 'failurecategory': 'failure_category', 'netchecksuggestedcategory': 'failure_category',
    'netchecksubcategory': 'failure_subcategory', 'failuresubcategory': 'failure_subcategory',
    'netchecksuggestedcause': 'failure_subcategory',
}
# A call whose analysis has no date takes the date of the call this many days later (the analysts' usual delay).
ANALYSES_DAYS_AFTER_CALL = 7
# A cell of these fields with two values (one per line, or Ericsson/Huawei) gives the second one to its pair.
ANALYSES_PAIRS = {('field', 'vendor_when_failure'): ('field', 'vendor_2_when_failure')}
# Values of a list the import may add to it (every list but these, whose values say which UE failed).
ANALYSES_CLOSED_LISTS = {'failed_party'}
# Name lengths of the catalog: teams and domains, list values, root categories and causes.
TEAM_NAME_LIMIT, OPTION_NAME_LIMIT = 60, 80
# The colours of the teams and domains the import adds.
ANALYSES_COLORS = ('#0f6f7d', '#b85b20', '#6941a4', '#2e8b57', '#245a96', '#c8102e', '#e08a1e', '#5b6b2e', '#7b8790', '#d14a68')


def analyses_equivalences(task_repository: Any) -> dict[str, dict[str, dict[str, str]]]:
    """The equivalences the import uses: target (``tracking:root_cause``, ``field:analysis_status``) -> value
    (lowercase) -> ``{'value', 'to', 'domain'}``; an empty ``to`` leaves the value out of the field (it stays in the
    import note). The rules of the tool (``nq_analyses_rules``) with those the workspace reviewed over them."""
    merged = builtin_equivalences()
    for target, values in workspace_equivalences(task_repository).items():
        merged.setdefault(target, {}).update(values)
    return merged


def builtin_equivalences() -> dict[str, dict[str, dict[str, str]]]:
    """The equivalences of the analysis workbooks of the previous tool every workspace uses."""
    rules: dict[str, dict[str, dict[str, str]]] = {}
    for target, value, to, domain in nq_analyses_rules.ANALYSES_RULES:
        rules.setdefault(target, {})[value.casefold()] = {'value': value, 'to': to, 'domain': domain}
    return _normalize_equivalences(rules)


def workspace_equivalences(task_repository: Any) -> dict[str, dict[str, dict[str, str]]]:
    """The equivalences the workspace reviewed (uploaded in Previous NQ Analyses), which come before the rules."""
    try:
        stored = json.loads(task_repository.get_workspace_state(ANALYSES_EQUIVALENCES_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        return {}
    return _normalize_equivalences(stored)


def _normalize_equivalences(stored: Any) -> dict[str, dict[str, dict[str, str]]]:
    result: dict[str, dict[str, dict[str, str]]] = {}
    for target, values in (stored.items() if isinstance(stored, dict) else []):
        if not isinstance(values, dict) or not re.fullmatch(r'(tracking|field):[a-z0-9_]+', str(target)):
            continue
        for key, item in values.items():
            if isinstance(item, dict) and str(key).strip():
                result.setdefault(str(target), {})[str(key).strip().casefold()] = {
                    'value': str(item.get('value') or key).strip(), 'to': re.sub(r'\s+', ' ', str(item.get('to') or '')).strip(),
                    'domain': re.sub(r'\s+', ' ', str(item.get('domain') or '')).strip()[:TEAM_NAME_LIMIT]}
    return result


def _save_equivalences(task_repository: Any, equivalences: dict[str, dict[str, dict[str, str]]]) -> None:
    task_repository.set_workspace_state(ANALYSES_EQUIVALENCES_STATE_KEY,
                                        json.dumps(_normalize_equivalences(equivalences), ensure_ascii=False))


def reset_analyses_equivalences(task_repository: Any) -> dict[str, int]:
    """Forget the equivalences the workspace reviewed (Default Equivalences): the import uses those of the tool again."""
    forgotten = sum(len(values) for values in workspace_equivalences(task_repository).values())
    _save_equivalences(task_repository, {})
    return {'forgotten': forgotten}


class _AnalysesTranslator:
    """Turns the values of the analyses into values of the Analysis Center: the reviewed equivalences first, then the
    values of the catalog (same name or same letters), the old names of some values, and new values where the catalog
    accepts them (list values and teams; root categories and causes only through an equivalence with their domain)."""

    def __init__(self, task_repository: Any, users: set[str]) -> None:
        self.fields = {field['key']: field for field in list_fields(task_repository)}
        options = list_options(task_repository)
        self.statuses = [item['name'] for item in options['statuses']]
        self.teams = [item['name'] for item in options['teams']]
        self.users = {name.casefold(): name for name in users}
        self.taxonomy = list_root_causes(task_repository)
        self.domains = [item['name'] for item in self.taxonomy['domains']]
        self.equivalences = analyses_equivalences(task_repository)
        self.labels = {('tracking', ref): label for ref, label in nq_catalog.TRACKING_REFS.items()}
        self.labels.update({('tracking', field['source_ref']) if field['source'] == 'tracking' else ('field', key): field['label']
                            for key, field in self.fields.items() if field['source'] in {'user', 'tracking'}})
        # What the import adds to the catalog: list values by field and teams, each way of writing them counted (the
        # most used spelling names the new value: Not Planned and Not planned are one value).
        self.new_options: dict[str, dict[str, Counter]] = {}
        self.new_teams: dict[str, Counter] = {}
        self.new_roots: dict[str, dict[str, dict[str, Any]]] = {'categories': {}, 'causes': {}}
        # The domains the review gives root categories and causes of the catalog: name -> {'name', 'from', 'to': Counter}.
        self.domain_changes: dict[str, dict[str, dict[str, Any]]] = {'categories': {}, 'causes': {}}
        self.names: dict[str, str] = {}

    def label(self, target: tuple[str, str]) -> str:
        return self.labels.get(target, target[1])

    def blank(self, target: tuple[str, str], value: str) -> bool:
        """Whether a cell says nothing for its field (0 for an initial category of the first analyses)."""
        field = self.fields.get(target[1]) if target[0] == 'field' else None
        return bool(field and field['type'] in {'text', 'list'} and value.strip() in nq_analyses.EMPTY_TEXTS)

    @staticmethod
    def _count_new(pool: dict[str, Counter], value: str) -> str:
        pool.setdefault(nq_analyses.identity(value), Counter())[value] += 1
        return value

    @staticmethod
    def _spellings(pool: dict[str, Counter]) -> dict[str, tuple[str, int]]:
        return {key: (counts.most_common(1)[0][0], sum(counts.values())) for key, counts in pool.items()}

    def canonical(self, kind: str, ref: str, value: str) -> str:
        """The name of a new list value or team: the spelling of it most rows use."""
        pool = self.new_teams if (kind, ref) == ('tracking', 'team') else self.new_options.get(ref, {}) if kind == 'field' else {}
        counts = pool.get(nq_analyses.identity(value))
        return counts.most_common(1)[0][0] if counts else value

    def added_options(self) -> dict[str, dict[str, tuple[str, int]]]:
        return {ref: self._spellings(pool) for ref, pool in self.new_options.items()}

    def added_teams(self) -> dict[str, tuple[str, int]]:
        return self._spellings(self.new_teams)

    def added_teams_names(self) -> set[str]:
        return {name for name, _count in self.added_teams().values()} | {
            value for counts in self.new_teams.values() for value in counts}

    def added_option_names(self, ref: str) -> set[str]:
        return {value for counts in self.new_options.get(ref, {}).values() for value in counts}

    def _equivalence(self, target: tuple[str, str], value: str) -> dict[str, str] | None:
        return self.equivalences.get(f'{target[0]}:{target[1]}', {}).get(value.casefold())

    def reviewed(self, target: tuple[str, str], value: str) -> bool:
        """Whether the reviewed equivalences say what the value becomes."""
        return self._equivalence(target, value) is not None

    def _root(self, plural: str, value: str, target: tuple[str, str]) -> str | None:
        """The root category or cause of a value: through its equivalence (a new one is added, with the domain of the
        review or, without one, the domain its category or the keywords give it; the domain the review gives a value of
        the catalog becomes its own), else the value of the catalog with its name."""
        names = [item['name'] for item in self.taxonomy[plural]]
        equivalence = self._equivalence(target, value)
        if equivalence is not None:
            wanted = equivalence['to'][:OPTION_NAME_LIMIT]
            if not wanted:
                return None
            # A domain the catalog has renamed since the review takes its new name.
            domain = BUILTIN_ANALYSES_VALUES['domain'].get(equivalence['domain'].casefold(), equivalence['domain'])
            domain = (nq_analyses.list_choice(domain, self.domains) or domain) if domain else ''
            existing = nq_analyses.list_choice(wanted, names)
            if existing:
                current = next(item for item in self.taxonomy[plural] if item['name'] == existing)
                if domain and domain.casefold() != (current.get('domain') or '').casefold():
                    change = self.domain_changes[plural].setdefault(existing.casefold(), {
                        'name': existing, 'from': current.get('domain') or '', 'to': Counter()})
                    change['to'][domain] += 1
                return existing
            item = self.new_roots[plural].setdefault(wanted.casefold(), {'name': wanted, 'domain': domain, 'rows': 0})
            item['domain'] = item['domain'] or domain
            item['rows'] += 1
            return item['name']
        return next((name for name in names if name.casefold() == value.casefold()), None)

    def translate(self, target: tuple[str, str], value: str, direction: str = '') -> tuple[str, str, str] | None:
        """The (kind, ref, value) a value fills, or None when it is not a value of the field."""
        kind, ref = target
        if kind == 'tracking':
            if ref == 'root_category':
                found = self._root('categories', value, target)
            elif ref == 'root_cause':
                found = self._root('causes', value, target)
            elif ref == 'status':
                equivalence = self._equivalence(target, value)
                found = nq_analyses.list_choice(equivalence['to'] if equivalence else value, self.statuses)
            elif ref == 'assignee':
                found = self.users.get((self._equivalence(target, value) or {}).get('to', value).casefold())
            else:
                equivalence = self._equivalence(target, value)
                wanted = (equivalence['to'] if equivalence else BUILTIN_ANALYSES_VALUES['team'].get(value.casefold(), value))[:TEAM_NAME_LIMIT]
                found = nq_analyses.list_choice(wanted, self.teams) if wanted else None
                if wanted and found is None:
                    found = self._count_new(self.new_teams, re.sub(r'\s+', ' ', wanted).strip())
            return (kind, ref, found) if found else None
        field = self.fields.get(ref)
        if field is None or field['source'] != 'user':
            return None
        if field['type'] in {'text', 'list'} and value.strip() in nq_analyses.EMPTY_TEXTS:
            return None
        if ref in {'analyst', 'reviewer'}:
            value = self.names.get(nq_analyses.identity(value), value)
        equivalence = self._equivalence(target, value)
        if equivalence is not None:
            if not equivalence['to']:
                return None
            value = equivalence['to']
        if field['type'] == 'list':
            # A cell with several values (two bands, one per line) gives the field the first one; the note keeps the cell.
            lines = [line.strip() for line in value.splitlines() if line.strip()]
            if equivalence is None and len(lines) > 1:
                return self.translate(target, lines[0], direction)
            options = [option['name'] for option in field['options']]
            if ref == 'failed_party':
                value = nq_analyses.failed_party(value, direction) or value
            elif ref == 'band_when_failure':
                value = nq_analyses.band_name(value)
            elif ref == 'implementation_status' and value.strip().casefold() in nq_analyses.PLANNING_STATUSES \
                    and (self.fields.get('planned_status') or {}).get('source') == 'user':
                # Planned and Not Planned are planning statuses.
                return self.translate(('field', 'planned_status'), value, direction)
            elif ref == FISCAL_FIELD:
                # The Planned FY takes fiscal years only: 2030 is FY30, and another value stays in the import note.
                value = nq_analyses.fiscal_year(value) or ''
                if not value:
                    return None
            value = BUILTIN_ANALYSES_VALUES.get(ref, {}).get(value.casefold(), value)
            found = nq_analyses.list_choice(value, options)
            if found is None:
                if ref in ANALYSES_CLOSED_LISTS:
                    return None
                found = self._count_new(self.new_options.setdefault(ref, {}), re.sub(r'\s+', ' ', value).strip()[:OPTION_NAME_LIMIT])
            return ('field', ref, found)
        if field['type'] == 'date':
            parsed = nq_analyses.parse_date(value)
            if parsed:
                return ('field', ref, parsed)
            # A fiscal year or a year has no day: it goes to the Planned FY (the first one when the cell lists several,
            # the cell staying in the import note as it is written).
            fiscal = self.fields.get(FISCAL_FIELD)
            periods = [part for part in re.split(r'[\n,;/]+', value) if part.strip()]
            if ref == 'planned_date' and fiscal and fiscal['source'] == 'user' and periods \
                    and all(nq_analyses.fiscal_year(part) for part in periods):
                return self.translate(('field', FISCAL_FIELD), periods[0])
            return None
        try:
            return ('field', ref, _field_value(field, value))
        except ValueError:
            return None


BUILTIN_ANALYSES_VALUES = nq_analyses.BUILTIN_VALUES


def _session_columns(header: list[str], profile: CdrFieldProfile = NETCHECK_PROFILE) -> dict[str, Any]:
    """Where a sheet that repeats the CDR keeps what identifies a call without JOIN_ID, as the CDR index reads it: the
    Operator and Campaign columns and the test or session identifier of each service."""
    def first(columns: list[str]) -> list[int]:
        return [header.index(column) for column in columns]

    sources = profile.nq_field_sources
    return {'operator': first(_resolve_columns(header, sources['operator'])),
            'campaign': first(_resolve_columns(header, sources['campaign'])),
            'ids': {service: header.index(column) for service, candidates in profile.nq_identifier_sources.items()
                    if (column := _resolve_column(header, candidates))}}


def _analyses_session(columns: dict[str, Any], cells: list[str]) -> dict[str, Any] | None:
    """The Operator, Campaign and identifier (by service) of a row without JOIN_ID, when it has an identifier."""
    def cell(index: int) -> str:
        return cells[index] if index < len(cells) else ''

    ids = {service: cell(index) for service, index in columns['ids'].items() if cell(index)}
    if not ids:
        return None
    return {'operator': next((cell(index) for index in columns['operator'] if cell(index)), ''),
            'campaign': next((cell(index) for index in columns['campaign'] if cell(index)), ''), 'ids': ids}


def _session_keys(session: dict[str, Any]) -> dict[str, str]:
    """The call key a row without JOIN_ID has in each service it can belong to."""
    return {service: call_key_for(service, {'operator': session['operator'], 'campaign': session['campaign']}, identifier)
            for service, identifier in session['ids'].items()}


def read_analyses(content: bytes, file_name: str, definitions: list[dict[str, Any]], on_sheet: Any = None,
                  profile: CdrFieldProfile = NETCHECK_PROFILE) -> dict[str, Any]:
    """The analyses of a file by call: every visible sheet with a JOIN_ID (or Call Key) column, each row giving the
    values of its call (an analysis of several calls gives them to each one), its comments and its import note. A row
    without JOIN_ID is its call by the Operator, Campaign and session of the CDR it repeats, as the CDR index names
    calls without JOIN_ID."""
    tables, skipped_sheets = nq_analyses.read_tables(content, file_name, on_sheet)
    if not tables:
        raise ValueError('The file needs a JOIN_ID column (or Call Key) in one of the first three rows of a visible sheet.')
    keys = {field['key'] for field in definitions}
    entries: dict[str, dict[str, Any]] = {}
    recognized: list[str] = []
    read_only: list[str] = []
    noted: list[str] = []
    cdr = skipped = 0
    sheets = []
    for table in tables:
        layout = nq_analyses.resolve_layout(table, definitions, ANALYSES_TRACKING)
        if not (layout.targets or layout.comments or layout.appends or layout.notes):
            skipped_sheets.append(table.sheet)
            continue
        sheets.append({'sheet': table.sheet, 'rows': len(table.rows), 'export': table.export})
        recognized += [name for name in layout.recognized(table.header) if name not in recognized]
        read_only += [name for name in layout.read_only if name not in read_only]
        noted += [table.header[index] for index in layout.notes if table.header[index] not in noted]
        cdr = max(cdr, len(layout.cdr))
        session_columns = _session_columns(table.header, profile)
        start_column = next((table.header.index(column) for column in _resolve_columns(table.header, profile.nq_field_sources['start_time'])), None)
        for number, cells in table.rows:
            def cell(index: int | None) -> str:
                return cells[index] if index is not None and index < len(cells) else ''

            identities = nq_analyses.join_ids(cell(layout.join)) if layout.join is not None else []
            if not identities and cell(layout.key):
                identities = [cell(layout.key)]
            session = None if identities else _analyses_session(session_columns, cells)
            if session:
                identities = [f"{session['operator']} · {session['campaign']} · session "
                              f"{next(iter(session['ids'].values()))}"]
            if not identities:
                skipped += any(cells)
                continue
            origin = f'{table.sheet}, row {number}' if table.sheet != 'CSV' else f'row {number}'
            values: list[tuple[int, tuple[str, str], str]] = []
            for index, target in layout.targets.items():
                value = cell(index)
                if nq_analyses.is_empty(value):
                    continue
                pair = ANALYSES_PAIRS.get(target)
                parts = [part.strip() for part in re.split(r'[\n/]+', value) if part.strip()] if pair else []
                # Two vendors fill Vendor 1 and Vendor 2 (unless the sheet has its own column for the second one).
                if len(parts) > 1 and pair[1] in keys and pair not in layout.targets.values():
                    values += [(index, target, parts[0]), (index, pair, parts[1])]
                    if len(parts) > 2:
                        values.append((index, ('note', ''), value))
                else:
                    values.append((index, target, value))
            comments = [(table.header[index], cell(index)) for index in layout.comments if not nq_analyses.is_empty(cell(index))]
            appends = [(ref, table.header[index], cell(index)) for index, ref in layout.appends.items()
                       if not nq_analyses.is_empty(cell(index))]
            # A second column of a value with the same value as the first one says nothing more.
            filled = {nq_analyses.identity(table.header[index]): cell(index).strip().casefold() for index in layout.targets}
            notes = [(table.header[index], cell(index)) for index in layout.notes if not nq_analyses.is_empty(cell(index))
                     and filled.get(nq_analyses.identity(table.header[index])) != cell(index).strip().casefold()]
            # The date of the row dates the changes of its call; a cell that is not a date stays in the note.
            moment = nq_analyses.parse_moment(cell(layout.when)) if layout.when is not None and cell(layout.when) else None
            if layout.when is not None and cell(layout.when) and moment is None and not nq_analyses.is_empty(cell(layout.when)):
                notes.append((table.header[layout.when], cell(layout.when)))
            for identity in identities:
                by_join = layout.join is not None and identity != cell(layout.key) and not session
                entry = entries.setdefault(identity.casefold(), {
                    'join_id': identity if by_join else '', 'call_key': '' if by_join or session else identity,
                    'session': session, 'label': identity, 'values': {}, 'comments': [], 'appends': [], 'notes': [],
                    'origins': [], 'direction': '', 'rows': 0, 'sheet': table.sheet, 'service_hint': _service_hint(table.header),
                    'when': '', 'call_date': ''})
                entry['rows'] += 1
                entry['when'] = max(entry['when'], moment or '')
                entry['call_date'] = entry['call_date'] or cell(start_column)
                entry['origins'].append(origin)
                entry['direction'] = entry['direction'] or cell(layout.direction)
                # A call in several rows takes the values of the first one; the note keeps the others (and a cell of
                # more values than its fields take).
                for index, target, value in values:
                    if target[0] == 'note':
                        if (f'{table.header[index]} (as written)', value) not in entry['notes']:
                            entry['notes'].append((f'{table.header[index]} (as written)', value))
                        continue
                    kept = entry['values'].setdefault(target, value)
                    if kept.strip().casefold() != value.strip().casefold():
                        entry['notes'].append((f'{table.header[index]} ({origin})', value))
                for item in comments:
                    if item not in entry['comments']:
                        entry['comments'].append(item)
                for item in appends:
                    if item not in entry['appends']:
                        entry['appends'].append(item)
                for item in notes:
                    if item not in entry['notes']:
                        entry['notes'].append(item)
    return {'entries': list(entries.values()), 'skipped': skipped, 'columns': recognized, 'read_only': read_only,
            'noted': noted, 'cdr_columns': cdr, 'sheets': sheets, 'sheets_skipped': skipped_sheets,
            'duplicates': sum(1 for entry in entries.values() if entry['rows'] > 1)}


def _service_hint(header: list[str]) -> str:
    """The service of the calls of a sheet when none of them is in the workspace: voice calls name their session type."""
    names = {nq_analyses.identity(name) for name in header}
    if names & {'sessiontype', 'callstatus', 'calldirection'}:
        return 'voice'
    if names & {'testtype', 'datathroughput', 'findingsbucketization'}:
        return 'data'
    return ''


def _known_call_values(connection: Any, keys: list[str], join_ids: list[str], mapper: ValueMapper) -> dict[str, dict[str, set[str]]]:
    """What the tool has of each call to compare the copies of the analyses with: the values of its CDRs (every
    version) by field (the Operator as the Operator Maps name it), and its Ericsson RCA results by the identity of
    their column, all as normalized text."""
    known: dict[str, dict[str, set[str]]] = {}
    fields = sorted(set(ANALYSES_CDR_COPIES.values()))
    for row in _rows_of_calls(connection, f'SELECT call_key, {", ".join(fields)} FROM {NQ_CALLS_TABLE}', keys) if keys else []:
        values = known.setdefault(str(row['call_key']), {})
        for field in fields:
            value = mapper.map('operator', row[field]) if field == 'operator' else row[field]
            values.setdefault(field, set()).add(_normalized_text(value))
    by_join = {join_id.casefold(): key for key, join_id in zip(keys, join_ids) if join_id}
    for start in range(0, len(by_join), 500):
        chunk = list(by_join)[start:start + 500]
        for row in connection.execute(f"SELECT join_id, values_json FROM {NQ_RCA_RESULTS_TABLE} "
                                      f"WHERE join_id IN ({', '.join('?' for _ in chunk)})", chunk):
            values = known.setdefault(by_join[str(row['join_id'])], {})
            for name, value in (json.loads(row['values_json'] or '{}') or {}).items():
                for column in {name, nq_catalog.RCA_REFS.get(name, name)}:
                    values.setdefault(f'rca:{nq_analyses.identity(column)}', set()).add(_normalized_text(value))
    return known


def _repeats_the_call(known: dict[str, set[str]], column: str, value: str, mapper: ValueMapper) -> bool:
    """Whether a column of the analysis repeats what the tool has of the call (its CDR or its Ericsson RCA), also as the
    workbooks write it: the Operator by the Operator Maps, the Region as the letter of its Vendor area (B for Vendor B)
    and the Campaign as a part of its name (Q3 for UK_Q3_2025)."""
    name = nq_analyses.identity(column)
    field = ANALYSES_CDR_COPIES.get(name)
    values = known.get(field) if field else known.get(f'rca:{name}')
    if not values:
        return False
    text = _normalized_text(mapper.map('operator', value) if field == 'operator' else value)
    if text in values:
        return True
    if field == 'region':
        return f'vendor {text}' in values
    if field == 'campaign':
        return any(text in re.split(r'[\s_\-]+', campaign) for campaign in values)
    return False


def _analyses_note(source: str, lines: list[str]) -> str:
    """What the import keeps of a call that no field holds (the columns of the analysis without a field, the values that
    are not values of their field, the cells a field takes only part of and the values the call already had otherwise),
    after where they come from."""
    return '\n'.join([source, *lines])[:MAX_COMMENT_LENGTH] if lines else ''


def import_analyses(task_repository: Any, content: bytes, file_name: str, username: str, users: set[str], *,
                    overwrite: bool = False, dry_run: bool = False,
                    progress: Callable[[str, float], None] | None = None) -> dict[str, Any]:
    """Import the analyses of the previous tool into the follow-up of the calls, by JOIN_ID.

    Every visible sheet with a JOIN_ID column is read. Values are checked as if they were chosen in the call, after the
    reviewed equivalences: list values and teams the catalog lacks are added, root categories and causes only through an
    equivalence that gives their domain; anything else, and every column without a field, stays in the import note of
    the call. Each comment column becomes a comment. Calls not in the workspace yet keep their analysis for when their
    CDR is added. Without ``overwrite`` only empty values are filled. ``dry_run`` only reports what the import would do.
    ``progress(step, fraction)`` is told how far the import is.
    """
    report = progress or (lambda _step, _fraction: None)
    definitions = list_fields(task_repository)
    report('Reading the file', 0.02)
    parsed = read_analyses(content, file_name, definitions, lambda name, index, count: report(
        f'Reading the sheet {name}', 0.02 + 0.33 * index / max(count, 1)), workspace_field_profile(task_repository))
    report('Finding the calls in the workspace', 0.36)
    translator = _AnalysesTranslator(task_repository, users)
    # Every way a name of an analyst or a reviewer is written becomes its most used spelling.
    translator.names = nq_analyses.canonical_names([value for entry in parsed['entries'] for (kind, ref), value in entry['values'].items()
                                                   if (kind, ref) in {('field', 'analyst'), ('field', 'reviewer')}])
    with task_repository.connection() as connection:
        known: dict[str, tuple[str, str]] = {}
        for row in connection.execute(f'SELECT DISTINCT call_key, join_id, service FROM {NQ_CALLS_TABLE}'):
            known[str(row['call_key']).casefold()] = (str(row['call_key']), str(row['service']))
            if row['join_id']:
                known.setdefault(str(row['join_id']).casefold(), (str(row['call_key']), str(row['service'])))
        tracked = {str(row[0]) for row in connection.execute(f'SELECT call_key FROM {NQ_CALL_TRACKING_TABLE}')}

    def found(entry: dict[str, Any]) -> tuple[str, str] | None:
        if entry['session']:
            return next((known[key] for key in _session_keys(entry['session']).values() if key in known), None)
        return known.get((entry['join_id'] or entry['call_key']).casefold())

    # What the tool has of the calls found, to leave their copies out of the note.
    located = list(dict.fromkeys(hit[0] for entry in parsed['entries'] if (hit := found(entry))))
    with task_repository.connection() as connection:
        join_of = {str(row['call_key']): str(row['join_id']) for row in _rows_of_calls(
            connection, f"SELECT call_key, join_id FROM {NQ_CALLS_TABLE}", located, where="join_id <> ''")} if located else {}
        mapper = ValueMapper.from_repository(task_repository)
        call_values = _known_call_values(connection, located, [join_of.get(key, '') for key in located], mapper)
        starts = {str(row['call_key']): str(row['start_time'] or '') for row in _rows_of_calls(
            connection, f'SELECT call_key, start_time FROM {NQ_CALLS_TABLE}', located)} if located else {}
    # The service of the calls a sheet does not find: the one most of its found calls have, else what its columns say.
    services: dict[str, Counter] = {}
    for entry in parsed['entries']:
        hit = found(entry)
        if hit:
            services.setdefault(entry['sheet'], Counter())[hit[1]] += 1
    plans: list[dict[str, Any]] = []
    invalid: Counter = Counter()
    unmatched: list[str] = []
    unplaced: list[str] = []
    for number, entry in enumerate(parsed['entries']):
        if number % 200 == 0:
            report('Translating the values', 0.42 + 0.13 * number / max(len(parsed['entries']), 1))
        identity = entry['label']
        hit = found(entry)
        if hit:
            call_key = hit[0]
        else:
            unmatched.append(identity)
            service = (services.get(entry['sheet']) or Counter()).most_common(1)
            service = service[0][0] if service else entry['service_hint']
            key = (_session_keys(entry['session']).get(service) if entry['session'] else
                   call_key_for(service, {}, join_id=entry['join_id']) if entry['join_id'] else '') if service else ''
            if not key:
                unplaced.append(identity)
                continue
            call_key = key
        changes: dict[tuple[str, str], str] = {}
        written: dict[tuple[str, str], str] = {}
        routed: dict[tuple[str, str], tuple[tuple[str, str], str]] = {}
        # The copies of the CDR or of the Ericsson RCA that say what the tool has of the call are left out of the note.
        repeated = call_values.get(call_key, {}) if hit else {}
        lines = [f'{column}: {value}' for column, value in entry['notes'] if not _repeats_the_call(repeated, column, value, mapper)]
        for target, value in entry['values'].items():
            if translator.blank(target, value):
                continue
            result = translator.translate(target, value, entry['direction'])
            if result is None:
                label = translator.label(target)
                invalid[(label, value[:60])] += 1
                lines.append(f'{label} (not a value of the field): {value}')
                continue
            key = (result[0], result[1])
            if key in changes and nq_analyses.identity(changes[key]) != nq_analyses.identity(result[2]):
                # Two columns of the row give the field a value: its own column wins over one that only leads to it
                # (Planned in an implementation column), and the other value stays in the note.
                if key == target and key in routed:
                    routed_target, routed_value = routed.pop(key)
                    lines.append(f'{translator.label(routed_target)}: {routed_value}')
                    changes[key], written[key] = result[2], value
                else:
                    lines.append(f'{translator.label(target)}: {value}')
                continue
            changes.setdefault(key, result[2])
            written.setdefault(key, value)
            if key != target:
                routed.setdefault(key, (target, value))
            # A cell the field takes only part of (several fiscal years or bands), and a value the reviewed equivalences
            # name otherwise, stay in the note as they are written.
            partial = '\n' in value.strip() and ((result[0], result[1]) != target or result[2] != value)
            renamed = (translator.reviewed(target, value) or value.strip().casefold() in nq_analyses.KEPT_IN_NOTE.get(target[1], ())) \
                and nq_analyses.identity(result[2]) != nq_analyses.identity(value)
            if partial or renamed:
                lines.append(f'{translator.label(target)} (as written): {value}')
        # A call the analysts invalidated is an invalidated analysis.
        if (changes.get(('tracking', 'root_category'), '').casefold() == 'invalidated' and ('field', 'analysis_status') not in changes
                and nq_analyses.list_choice('Invalidated', [option['name'] for option in
                                                            translator.fields.get('analysis_status', {}).get('options') or []])):
            changes[('field', 'analysis_status')] = 'Invalidated'
        # Without the date of its analysis, the call takes its own date a week later (from the CDR of the row, or of the call).
        when, estimated = entry['when'], False
        if not when:
            when = nq_analyses.moment_after(entry['call_date'] or starts.get(call_key, ''), ANALYSES_DAYS_AFTER_CALL) or ''
            estimated = bool(when)
        plans.append({'identity': identity, 'call_key': call_key, 'found': bool(hit), 'changes': changes, 'when': when,
                      'estimated': estimated,
                      'written': written, 'appends': entry['appends'], 'lines': lines,
                      'source': f"Imported from {file_name} · {'; '.join(dict.fromkeys(entry['origins']))}",
                      'comments': [value if nq_analyses.identity(column) == 'comments' else f'[{column}] {value}'
                                   for column, value in entry['comments']]})
    # New list values and teams take the spelling most rows use.
    for plan in plans:
        plan['changes'] = {(kind, ref): translator.canonical(kind, ref, value) for (kind, ref), value in plan['changes'].items()}
    keys = [plan['call_key'] for plan in plans]
    labels = {target: translator.label(target) for plan in plans for target in plan['changes']}
    result = _write_analyses(task_repository, plans, username, labels, overwrite=overwrite, dry_run=dry_run,
                             progress=lambda done, total: report('Comparing with the calls' if dry_run else 'Writing the analyses',
                                                                 0.55 + 0.35 * done / max(total, 1)))
    # The catalog gets the new values some call takes (a value no call takes, as the calls keep theirs, stays out).
    applied = result.pop('applied')
    if not dry_run and applied:
        report('Adding the new values to the catalog', 0.96)
        _add_analyses_catalog(task_repository, translator, applied)
    report('Done', 1.0)
    summary_new = {
        'new_options': [{'field': translator.fields[ref]['label'], 'value': name, 'rows': count}
                        for ref, names in translator.added_options().items()
                        for name, count in sorted(names.values(), key=lambda item: -item[1])
                        if ('field', ref, name.casefold()) in applied],
        'new_teams': [{'value': name, 'rows': count} for name, count in sorted(translator.added_teams().values(), key=lambda item: -item[1])
                      if ('tracking', 'team', name.casefold()) in applied],
        'new_categories': [{'value': item['name'], 'domain': item['domain'], 'rows': item['rows']}
                           for item in translator.new_roots['categories'].values()
                           if ('tracking', 'root_category', item['name'].casefold()) in applied],
        'new_causes': [{'value': item['name'], 'domain': item['domain'], 'rows': item['rows']}
                       for item in translator.new_roots['causes'].values()
                       if ('tracking', 'root_cause', item['name'].casefold()) in applied],
        'domain_changes': [{'kind': title, 'value': item['name'], 'from': item['from'], 'to': item['to'].most_common(1)[0][0],
                            'rows': sum(item['to'].values()), 'others': [name for name in item['to'] if name != item['to'].most_common(1)[0][0]]}
                           for plural, ref, title in (('categories', 'root_category', 'Root Category'), ('causes', 'root_cause', 'Root Cause'))
                           for item in translator.domain_changes[plural].values()
                           if ('tracking', ref, item['name'].casefold()) in applied],
    }
    summary = {
        'rows': sum(entry['rows'] for entry in parsed['entries']) + parsed['skipped'], 'calls': len(parsed['entries']),
        'matched': len(parsed['entries']) - len(unmatched), 'unmatched': len(unmatched),
        'unmatched_ids': unmatched[:MAX_ANALYSES_ISSUES], 'unplaced': len(unplaced),
        'skipped': parsed['skipped'], 'duplicates': parsed['duplicates'],
        'analysed': sum(1 for key in keys if key in tracked), 'columns': parsed['columns'], 'read_only': parsed['read_only'],
        'noted': parsed['noted'], 'cdr_columns': parsed['cdr_columns'], 'sheets': parsed['sheets'],
        'sheets_skipped': parsed['sheets_skipped'],
        'invalid': [{'column': column, 'value': value, 'rows': count}
                    for (column, value), count in invalid.most_common(MAX_ANALYSES_ISSUES)],
        'invalid_total': sum(invalid.values()), **result, **summary_new, 'overwrite': overwrite, 'dry_run': dry_run,
    }
    if not dry_run and hasattr(task_repository, 'try_add_log'):
        task_repository.try_add_log(username, 'nq_analyses_import', json.dumps({
            'file': file_name, 'overwrite': overwrite, 'matched': summary['matched'], 'pending': summary['pending'],
            'changed': summary['changed'], 'comments': summary['comments'], 'notes': summary['notes'],
        }))
    return summary


def _add_analyses_catalog(task_repository: Any, translator: _AnalysesTranslator, applied: set[tuple[str, str, str]]) -> None:
    """Add to the catalog the list values, teams, domains, root categories and causes the analyses bring to some call
    (``applied``: kind, ref and lowercase value of every value written)."""
    added = translator.added_options()
    if added:
        fields = list_fields(task_repository)
        for field in fields:
            for name, _count in added.get(field['key'], {}).values():
                if ('field', field['key'], name.casefold()) in applied \
                        and name.casefold() not in {option['name'].casefold() for option in field['options']}:
                    field['options'].append({'name': name, 'color': '', 'keywords': []})
        _store_fields(task_repository, nq_catalog.normalize_fields(fields, {field['key']: field for field in list_fields(task_repository)},
                                                                   CATALOG_CALL_FIELDS))
    with task_repository.connection() as connection:
        teams = [name for name, _count in translator.added_teams().values() if ('tracking', 'team', name.casefold()) in applied]
        if teams:
            position = connection.execute(
                f"SELECT COALESCE(MAX(position), -1) FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = 'team'").fetchone()[0]
            for index, name in enumerate(teams):
                connection.execute(
                    f"INSERT OR IGNORE INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('team', ?, ?, ?, 0)",
                    (name, ANALYSES_COLORS[index % len(ANALYSES_COLORS)], position + 1 + index))
        refs = (('categories', 'root_category'), ('causes', 'root_cause'))
        roots = {plural: {key: item for key, item in translator.new_roots[plural].items()
                          if ('tracking', ref, item['name'].casefold()) in applied} for plural, ref in refs}
        # The domain the review gives a root category or cause of the catalog (the one most of its rows give).
        changes = {plural: {key: item['to'].most_common(1)[0][0] for key, item in translator.domain_changes[plural].items()
                            if ('tracking', ref, item['name'].casefold()) in applied} for plural, ref in refs}
        if any(roots.values()) or any(changes.values()):
            catalog = nq_catalog.stored_root_catalog(_read_root_catalog(connection))
            domains = {item['name'].casefold() for item in catalog['domains']}

            def domain_of_review(name: str) -> str:
                if name and name.casefold() not in domains:
                    catalog['domains'].append({'name': name, 'keywords': [],
                                               'color': ANALYSES_COLORS[len(catalog['domains']) % len(ANALYSES_COLORS)]})
                    domains.add(name.casefold())
                return name

            for plural in ('categories', 'causes'):
                names = {item['name'].casefold() for item in catalog[plural]}
                for item in catalog[plural]:
                    if item['name'].casefold() in changes[plural]:
                        item['domain'] = domain_of_review(changes[plural][item['name'].casefold()])
                for key, item in roots[plural].items():
                    if key not in names:
                        catalog[plural].append({'name': item['name'], 'domain': domain_of_review(item['domain']), 'keywords': []})
                        names.add(key)
            normalized = nq_catalog.normalize_root_catalog(catalog)
            _write_root_catalog(connection, normalized)
            _refresh_root_domains(connection, normalized)


def _write_analyses(task_repository: Any, plans: list[dict[str, Any]], username: str, labels: dict[tuple[str, str], str], *,
                    overwrite: bool, dry_run: bool, progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Write (or count) what each call gets: its follow-up and fields (only the empty ones without ``overwrite``: the
    values a call keeps go to the note), the texts added to its fields, its comments and its import note; the statuses
    follow the Status Rules afterwards. ``applied`` holds every value written (kind, ref, lowercase value)."""
    taxonomy = list_root_causes(task_repository)
    default = untracked_status(task_repository)
    now = now_iso()
    changed = pending = added_comments = notes = dated = estimated = 0
    touched: dict[str, str] = {}
    applied: set[tuple[str, str, str]] = set()
    with task_repository.connection() as connection:
        keys = [plan['call_key'] for plan in plans]
        tracking = {str(row['call_key']): dict(row) for row in _rows_of_calls(
            connection, f'SELECT * FROM {NQ_CALL_TRACKING_TABLE}', keys)} if keys else {}
        values = field_values(connection, keys) if keys else {}
        comment_rows: dict[str, list[Any]] = {}
        for row in (_rows_of_calls(connection, f'SELECT id, call_key, body, created_by, created_at, deleted_at FROM {NQ_CALL_COMMENTS_TABLE}',
                                   keys, order='created_at, id') if keys else []):
            comment_rows.setdefault(str(row['call_key']), []).append(row)
        for number, plan in enumerate(plans):
            if progress is not None and number % 100 == 0:
                progress(number, len(plans))
            call_key = plan['call_key']
            current = tracking.get(call_key) or {'status': default, 'status_mode': 'auto', 'team': '', 'assignee': '',
                                                  'root_domain': '', 'root_category': '', 'root_cause': '', 'version': 0}
            stored = values.get(call_key, {})
            existing = {str(row['body']).strip() for row in comment_rows.get(call_key, []) if not row['deleted_at']} \
                | {_comment_log(comment_rows.get(call_key, []))}
            follow_up = {ref: value for (kind, ref), value in plan['changes'].items() if kind == 'tracking'
                         and (overwrite or not str(current.get(ref) or '') or (ref == 'status' and current.get('status_mode') != 'manual'))
                         and str(current.get(ref) or '') != value}
            fields = {ref: value for (kind, ref), value in plan['changes'].items() if kind == 'field'
                      and (overwrite or not stored.get(ref)) and stored.get(ref, '') != value}
            # A root cause without root category brings the category it is mapped to, as when it is chosen in the call.
            if follow_up.get('root_cause') and not follow_up.get('root_category') and not str(current.get('root_category') or ''):
                mapped = root_category_of(taxonomy, follow_up['root_cause'])
                if mapped:
                    follow_up['root_category'] = mapped
            # A value the call keeps (it has another one) stays in the note as the file writes it; a text the import
            # added a column to (Findings Comments after the Findings) is the same value.
            lines = list(plan['lines'])
            for (kind, ref), value in plan['changes'].items():
                had = str(current.get(ref) or '') if kind == 'tracking' else stored.get(ref, '')
                same = had.casefold() == value.casefold() or had.startswith(f'{value}\n\n[')
                if ref not in (follow_up if kind == 'tracking' else fields) and not same:
                    lines.append(f"{labels.get((kind, ref), ref)} (the call keeps {had}): {plan['written'][(kind, ref)]}")
            applied.update(('tracking', ref, value.casefold()) for ref, value in follow_up.items())
            applied.update(('field', ref, value.casefold()) for ref, value in fields.items())
            for ref, column, text in plan['appends']:
                base = fields.get(ref, stored.get(ref, ''))
                addition = f'[{column}] {text}'
                if addition not in base:
                    fields[ref] = f'{base}\n\n{addition}'.strip()[:nq_catalog.MAX_LONG_TEXT]
            comments = [body[:MAX_COMMENT_LENGTH] for body in dict.fromkeys(plan['comments']) if body[:MAX_COMMENT_LENGTH] not in existing]
            note = _analyses_note(plan['source'], lines)
            note = note if note not in existing else ''
            if not follow_up and not fields and not comments and not note:
                continue
            changed += bool((follow_up or fields) and plan['found'])
            pending += not plan['found']
            added_comments += len(comments)
            notes += bool(note)
            dated += bool(plan['when']) and not plan['estimated']
            estimated += plan['estimated']
            if dry_run:
                continue
            # The changes of the call take the date the analysts last changed its analysis (else the date of the call a
            # week later, else the time of the import); its last modification does not go back before a later change.
            when = plan['when'] or now
            last = max(str(current.get('updated_at') or ''), when)
            row = {**current, **follow_up}
            if 'status' in follow_up:
                row['status_mode'] = 'manual'
            row['root_domain'] = domain_of(taxonomy, str(row['root_category']), str(row['root_cause'])) or str(row['root_domain'] or '')
            # As a change made in the call, a change of its fields is its last modification too.
            if follow_up or fields:
                connection.execute(
                    f'INSERT INTO {NQ_CALL_TRACKING_TABLE} (call_key, status, team, assignee, root_domain, root_category, root_cause, '
                    'status_mode, version, updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?) ON CONFLICT(call_key) DO UPDATE SET '
                    'status = excluded.status, team = excluded.team, assignee = excluded.assignee, root_domain = excluded.root_domain, '
                    'root_category = excluded.root_category, root_cause = excluded.root_cause, status_mode = excluded.status_mode, '
                    'version = version + 1, updated_by = excluded.updated_by, updated_at = excluded.updated_at',
                    (call_key, row['status'], row['team'], row['assignee'], row['root_domain'], row['root_category'], row['root_cause'],
                     row['status_mode'], username, last))
                for ref, value in follow_up.items():
                    _record_history(connection, call_key, ref, str(current.get(ref) or ''), value, username, when)
            for ref, value in fields.items():
                connection.execute(
                    f'INSERT INTO {NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) VALUES (?, ?, ?, ?, ?) '
                    'ON CONFLICT(call_key, field_key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, '
                    'updated_at = excluded.updated_at', (call_key, ref, value, username, when))
                _record_history(connection, call_key, f'field:{ref}', stored.get(ref, ''), value, username, when)
            for body in [*comments, *([note] if note else [])]:
                connection.execute(
                    f'INSERT INTO {NQ_CALL_COMMENTS_TABLE} (uid, call_key, body, created_by, created_at) VALUES (?, ?, ?, ?, ?)',
                    (uuid.uuid4().hex, call_key, body, username, when))
            touched[call_key] = when
    if touched:
        if progress is not None:
            progress(len(plans), len(plans))
        recompute_statuses(task_repository, username, list(touched), when_of=touched)
    return {'changed': changed, 'pending': pending, 'comments': added_comments, 'notes': notes, 'dated': dated,
            'estimated': estimated, 'failures': [], 'applied': applied}


EQUIVALENCES_SHEET = 'Equivalences'
EQUIVALENCES_COLUMNS = ('Field', 'Value in the file', 'Rows', 'Maps to', 'Domain', 'How', 'Target')


def analyses_equivalences_workbook(task_repository: Any, content: bytes | None, file_name: str, users: set[str]) -> bytes:
    """The values of the follow-up and list fields an analyses file brings, each with what it becomes (an equivalence
    of the tool or of the workspace, the same value, a value the catalog writes another way, a suggestion or a new
    value) for the users to review: change Maps to (and the Domain of a root category or cause) and upload the workbook
    back. Without a file, the equivalences the import uses: the rules of the tool and those the workspace reviewed."""
    definitions = list_fields(task_repository)
    translator = _AnalysesTranslator(task_repository, users)
    if content is None:
        rows = _rule_equivalence_rows(task_repository, translator, definitions)
    else:
        rows = _file_equivalence_rows(task_repository, content, file_name, translator, definitions)
    return _equivalences_workbook(task_repository, rows, translator, definitions, users)


def _equivalence_origin(task_repository: Any, target: str, value: str) -> str:
    """Where the equivalence of a value comes from: the workspace (its review) or the rules of the tool."""
    if value.casefold() in workspace_equivalences(task_repository).get(target, {}):
        return 'Reviewed in this workspace'
    return 'Rule of the tool'


def _rule_equivalence_rows(task_repository: Any, translator: _AnalysesTranslator,
                           definitions: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """One row per equivalence the import uses, in the order of the catalog."""
    reviewed = workspace_equivalences(task_repository)
    rows = []
    for target, values in translator.equivalences.items():
        kind, ref = target.split(':', 1)
        for key, item in values.items():
            how = 'Reviewed in this workspace' if key in reviewed.get(target, {}) else 'Rule of the tool'
            rows.append((translator.label((kind, ref)), item['value'], None, item['to'], item['domain'], how, target))
    return _sorted_equivalence_rows(rows, definitions)


def _sorted_equivalence_rows(rows: list[tuple[Any, ...]], definitions: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """The follow-up first, then the fields in the order of the catalog; the values most rows use first."""
    position = {f'tracking:{ref}': index for index, ref in enumerate(ANALYSES_TRACKING)}
    position.update({f"field:{field['key']}": len(ANALYSES_TRACKING) + index for index, field in enumerate(definitions)})
    return sorted(rows, key=lambda row: (position.get(row[6], len(position)), -(row[2] or 0), str(row[1]).casefold()))


def _file_equivalence_rows(task_repository: Any, content: bytes, file_name: str, translator: _AnalysesTranslator,
                           definitions: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    """One row per value of the follow-up and list columns of an analyses file, with what it becomes and why."""
    parsed = read_analyses(content, file_name, definitions, profile=workspace_field_profile(task_repository))
    translator.names = nq_analyses.canonical_names([value for entry in parsed['entries'] for (kind, ref), value in entry['values'].items()
                                                   if (kind, ref) in {('field', 'analyst'), ('field', 'reviewer')}])
    reviewable = {('tracking', ref) for ref in ANALYSES_TRACKING} | {
        ('field', field['key']) for field in definitions if field['source'] == 'user' and field['type'] in {'list', 'yes_no'}}
    counts: Counter = Counter()
    categories_of: dict[str, Counter] = {}
    for entry in parsed['entries']:
        for target, value in entry['values'].items():
            if target in reviewable and not translator.blank(target, value):
                counts[(target, value.strip())] += 1
        cause = entry['values'].get(('tracking', 'root_cause'), '').strip()
        category = entry['values'].get(('tracking', 'root_category'), '').strip()
        if cause and category:
            categories_of.setdefault(cause.casefold(), Counter())[category] += 1
    taxonomy = translator.taxonomy
    rule_match = (taxonomy.get('rule') or DEFAULT_ROOT_CAUSE_RULE).get('match', 'words')
    category_domains = {item['name'].casefold(): item['domain'] for item in taxonomy['categories']}
    results = {key: translator.translate(key[0], key[1], 'A->B') for key in counts}
    # A new value takes the spelling most rows use (Not Planned and Not planned are one value).
    spellings: dict[tuple[str, str, str], Counter] = {}
    for (target, value), result in results.items():
        if result:
            spellings.setdefault((result[0], result[1], nq_analyses.identity(result[2])), Counter())[result[2]] += counts[(target, value)]
    rows = []
    for (target, value), count in counts.items():
        stored = translator.equivalences.get(f'{target[0]}:{target[1]}', {}).get(value.casefold())
        result = results[(target, value)]
        maps_to, domain = (result[2] if result else ''), ''
        new = result is not None and (target == ('tracking', 'team') and maps_to in translator.added_teams_names()
                                      or target[0] == 'field' and maps_to in translator.added_option_names(target[1]))
        if new:
            maps_to = spellings[(result[0], result[1], nq_analyses.identity(maps_to))].most_common(1)[0][0]
        if stored is not None:
            how, maps_to, domain = _equivalence_origin(task_repository, f'{target[0]}:{target[1]}', value), stored['to'], stored['domain']
        elif target == ('field', 'failed_party') and nq_analyses.failed_party(value, 'A->B'):
            how = 'By the direction of the call (UE_A or UE_B)'
        elif result is not None and len([line for line in value.splitlines() if line.strip()]) > 1 and maps_to != value:
            how = 'Several values: the field takes the first one (the note keeps the cell)'
        elif result is None and target in {('tracking', 'root_category'), ('tracking', 'root_cause')}:
            # A root category or cause the catalog lacks: the one its words suggest, else a new one in a domain to choose.
            suggestion = nq_rca.map_to_catalog(value, '', taxonomy, rule_match) if target[1] == 'root_category' \
                else nq_rca.map_to_catalog('', value, taxonomy, rule_match)
            suggested = suggestion['category'] if target[1] == 'root_category' else suggestion['cause']
            if suggested:
                how, maps_to = 'Suggested: check it', suggested
            else:
                how, maps_to = 'New value: choose its Domain (empty: the keywords give it)', value
                if target[1] == 'root_cause':
                    category = (categories_of.get(value.casefold()) or Counter()).most_common(1)
                    domain = category_domains.get(category[0][0].casefold(), '') if category else ''
        elif result is None:
            how = 'Not a value of the field: kept in the import note'
        elif new:
            how = 'New value'
        elif maps_to.casefold() == value.casefold():
            how = 'Same value'
        else:
            how = 'Value of the catalog'
        rows.append((translator.label(target), value, count, maps_to, domain, how, f'{target[0]}:{target[1]}'))
    return _sorted_equivalence_rows(rows, definitions)


def _catalog_domains(taxonomy: dict[str, Any]) -> dict[str, dict[str, str]]:
    """The domain each root category and cause of the catalog has, by target and lowercase name."""
    return {'tracking:root_category': {item['name'].casefold(): item['domain'] for item in taxonomy['categories']},
            'tracking:root_cause': {item['name'].casefold(): item['domain'] for item in taxonomy['causes']}}


def _equivalences_workbook(task_repository: Any, rows: list[tuple[Any, ...]], translator: _AnalysesTranslator,
                           definitions: list[dict[str, Any]], users: set[str]) -> bytes:
    """The Equivalences sheet, with lists of the values each Maps to and Domain cell takes (those of the catalog and
    those the equivalences add; a new name can be typed too), and how to review it."""
    from openpyxl import Workbook
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.workbook.defined_name import DefinedName
    from openpyxl.worksheet.datavalidation import DataValidation

    taxonomy = translator.taxonomy
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = EQUIVALENCES_SHEET
    sheet.append(EQUIVALENCES_COLUMNS)
    # The domain the catalog gives each root category and cause, for the Domain cells to look up.
    catalog = workbook.create_sheet('Catalog')
    catalog.sheet_state = 'hidden'
    catalog.append(['Root Category', 'Domain', None, 'Root Cause', 'Domain'])
    categories = [(item['name'], item['domain']) for item in taxonomy['categories']]
    causes = [(item['name'], item['domain']) for item in taxonomy['causes']]
    for index in range(max(len(categories), len(causes))):
        catalog.append([*(categories[index] if index < len(categories) else (None, None)), None,
                        *(causes[index] if index < len(causes) else (None, None))])
    workbook.defined_names['CategoryDomains'] = DefinedName('CategoryDomains', attr_text='Catalog!$A:$B')
    workbook.defined_names['CauseDomains'] = DefinedName('CauseDomains', attr_text='Catalog!$D:$E')

    def catalog_domain(row: int, target: str) -> str:
        table = 'CategoryDomains' if target == 'tracking:root_category' else 'CauseDomains'
        return f'IFERROR(VLOOKUP($D{row},{table},2,FALSE),"")'

    # A root category or cause without a domain of its own shows the domain the catalog gives the value of Maps to (it
    # follows Maps to); choosing a domain in the list replaces it.
    for index, row in enumerate(rows, start=2):
        domain = row[4]
        if not domain and row[6] in {'tracking:root_category', 'tracking:root_cause'}:
            domain = f'={catalog_domain(index, row[6])}'
        sheet.append((*row[:4], domain, *row[5:]))
    header = PatternFill('solid', fgColor='B0234F')
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = header
    editable = PatternFill('solid', fgColor='FFF4D6')
    for row in sheet.iter_rows(min_row=2, min_col=4, max_col=5):
        for cell in row:
            cell.fill = editable
    # In grey while it is the domain of the catalog (nothing changes), in black when another one is chosen.
    if rows:
        lookup = (f'IF($G2="tracking:root_category",{catalog_domain(2, "tracking:root_category")},'
                  f'{catalog_domain(2, "tracking:root_cause")})')
        sheet.conditional_formatting.add(f'E2:E{len(rows) + 1}', FormulaRule(
            formula=[f'AND($E2<>"",OR($G2="tracking:root_category",$G2="tracking:root_cause"),$E2={lookup})'],
            font=Font(italic=True, color='7B8790')))
    for letter, width in zip('ABCDEFG', (28, 48, 8, 48, 26, 44, 30)):
        sheet.column_dimensions[letter].width = width
    sheet.column_dimensions['G'].hidden = True
    sheet.freeze_panes = 'C2'
    sheet.auto_filter.ref = sheet.dimensions
    # The values each target takes: those of the catalog, then the new ones the equivalences name.
    choices: dict[str, list[str]] = {
        'tracking:status': list(translator.statuses), 'tracking:team': list(translator.teams), 'tracking:assignee': sorted(users, key=str.casefold),
        'tracking:root_category': [item['name'] for item in taxonomy['categories']],
        'tracking:root_cause': [item['name'] for item in taxonomy['causes']]}
    for field in definitions:
        if field['source'] == 'user' and field['type'] in {'list', 'yes_no'}:
            choices[f"field:{field['key']}"] = [option['name'] for option in field['options']] if field['type'] == 'list' else list(YES_NO)
    domains = [item['name'] for item in taxonomy['domains']]
    for values in translator.equivalences.values():
        for item in values.values():
            if item['domain'] and item['domain'].casefold() not in {name.casefold() for name in domains}:
                domains.append(item['domain'])
    for row in rows:
        names = choices.setdefault(row[6], [])
        if row[3] and str(row[3]).casefold() not in {name.casefold() for name in names}:
            names.append(str(row[3]))
    lists = workbook.create_sheet('Lists')
    lists.sheet_state = 'hidden'
    columns = {'domain': (1, domains)}
    for index, target in enumerate(sorted({row[6] for row in rows}), start=2):
        columns[target] = (index, choices.get(target) or [])
    for target, (column, names) in columns.items():
        lists.cell(1, column, 'Domain' if target == 'domain' else translator.label(tuple(target.split(':', 1))))
        for offset, name in enumerate(names, start=2):
            lists.cell(offset, column, name)
    for target, (column, names) in columns.items():
        cells = [f'{"E" if target == "domain" else "D"}{index}' for index, row in enumerate(rows, start=2)
                 if (row[6] in {'tracking:root_category', 'tracking:root_cause'} if target == 'domain' else row[6] == target)]
        if not names or not cells:
            continue
        letter = get_column_letter(column)
        validation = DataValidation(type='list', formula1=f'=Lists!${letter}$2:${letter}${len(names) + 1}', allow_blank=True,
                                    showErrorMessage=False)
        sheet.add_data_validation(validation)
        for cell in cells:
            validation.add(cell)
    notes = workbook.create_sheet('How to review')
    for line in (
        'Each row is a value of the analysis workbooks in a follow-up or list field: Maps to is what the calls get.',
        'Rule of the tool: the import uses it in every workspace; Reviewed in this workspace: uploaded here, it comes before the rules.',
        'Maps to and Domain list the values of the catalog and those the equivalences add: choose one, or type a new name '
        '(list values and teams are added to the catalog).',
        'Domain: the domain the Root Category or Root Cause takes in the catalog (an existing one or a new name, which becomes a domain). '
        'In grey, the one the catalog gives the value of Maps to (it follows Maps to): left so, or empty, the catalog keeps it; '
        'another one turns black and changes it. Empty for a new value, it takes the domain of its keywords.',
        'Leave Maps to empty to leave a value out of its field: it stays in the import note of the call.',
        'Upload the workbook in Previous NQ Analyses: the rows that differ from the rules of the tool are kept in the workspace '
        'for its next imports.',
    ):
        notes.append([line])
    notes.column_dimensions['A'].width = 110
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def save_analyses_equivalences(task_repository: Any, content: bytes, users: set[str]) -> dict[str, Any]:
    """Keep the equivalences of a reviewed workbook in the workspace: the values whose Maps to (or Domain) the review
    changed from what the import does with the rules of the tool replace those of the same values; a value left as the
    rules take it forgets the equivalence of the workspace."""
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    if EQUIVALENCES_SHEET not in workbook.sheetnames:
        raise ValueError('The workbook has no Equivalences sheet: download it from Previous NQ Analyses first.')
    rows = [[nq_analyses.cell_text(value) for value in row] for row in workbook[EQUIVALENCES_SHEET].iter_rows(values_only=True)]
    if not rows:
        raise ValueError('The Equivalences sheet is empty.')
    header = {name: index for index, name in enumerate(rows[0])}
    missing = [name for name in ('Value in the file', 'Maps to', 'Domain', 'Target') if name not in header]
    if missing:
        raise ValueError(f'The Equivalences sheet lacks its {", ".join(missing)} column.')
    equivalences = workspace_equivalences(task_repository)
    rules = builtin_equivalences()
    # What the import does with each value with the rules of the tool alone (MOC and MTC as for an A->B call, as the
    # workbook shows them): a row the review left so needs no equivalence of the workspace.
    translator = _AnalysesTranslator(task_repository, users)
    translator.equivalences = rules
    current = _catalog_domains(translator.taxonomy)
    saved = 0
    for row in rows[1:]:
        def cell(name: str) -> str:
            index = header[name]
            return row[index].strip() if index < len(row) else ''

        target, value = cell('Target'), cell('Value in the file')
        if not value or not re.fullmatch(r'(tracking|field):[a-z0-9_]+', target):
            continue
        kind, ref = target.split(':', 1)
        default = translator.translate((kind, ref), value, 'A->B')
        # A Domain other than that of the rule (or, without one, than that of the catalog) is kept: it becomes the domain
        # of the root category or cause in the catalog.
        rule = rules.get(target, {}).get(value.casefold())
        if rule is not None and rule['domain']:
            same_domain = cell('Domain').casefold() == rule['domain'].casefold()
        else:
            same_domain = cell('Domain').casefold() in {'', current.get(target, {}).get(cell('Maps to').casefold(), '').casefold()}
        if cell('Maps to').casefold() == (default[2] if default else '').casefold() and same_domain:
            equivalences.get(target, {}).pop(value.casefold(), None)
            continue
        equivalences.setdefault(target, {})[value.casefold()] = {'value': value, 'to': cell('Maps to'), 'domain': cell('Domain')}
        saved += 1
    _save_equivalences(task_repository, equivalences)
    return {'saved': saved, 'total': sum(len(values) for values in workspace_equivalences(task_repository).values())}


def analyses_template(task_repository: Any) -> bytes:
    """An empty analyses file: JOIN_ID and every follow-up and analysts' field in the catalog order, then Comments."""
    columns = ['JOIN_ID'] + [field['label'] for field in list_fields(task_repository)
                             if field['source'] == 'user' or (field['source'] == 'tracking' and field['source_ref'] in ANALYSES_TRACKING)]
    output = io.StringIO()
    csv.writer(output).writerow([*columns, 'Comments'])
    return output.getvalue().encode('utf-8-sig')


# ---------------------------------------------------------------------------
# Lifecycle and RCA insights
# ---------------------------------------------------------------------------
STALLED_DAYS = 14
PHASE_SECTIONS = ('analysis', 'implementation', 'planning')


def _filtered_calls(task_repository: Any, filters: dict[str, Any], username: str, columns: str = '*') -> tuple[list[Any], dict[str, Any]]:
    options = list_options(task_repository)
    definitions = list_fields(task_repository)
    base, base_params = _base_sql(untracked_status(task_repository, options), task_repository, _scope(filters))
    where, params = _filter_sql(_resolve_key_filters(task_repository, filters), username,
                                [item['name'] for item in options['statuses'] if item['closed']], definitions)
    with task_repository.connection() as connection:
        rows = connection.execute(f'WITH calls AS ({base}) SELECT {columns} FROM calls{where}', [*base_params, *params]).fetchall()
    return rows, {'options': options, 'definitions': definitions}


def lifecycle_stats(task_repository: Any, filters: dict[str, Any], username: str) -> dict[str, Any]:
    """Where the filtered calls are in their follow-up: the status pipeline, how the statuses were set, the
    phase fields, the time spent in each status, the most frequent moves and the calls without recent changes."""
    rows, context = _filtered_calls(task_repository, filters, username,
                                    'call_key, start_time, status, status_mode, updated_at, comment_count, field_values_json, '
                                    'service, test_name, session_type, operator, campaign, city, root_category, root_cause')
    options, definitions = context['options'], context['definitions']
    statuses = options['statuses']
    closed = {item['name'].casefold() for item in statuses if item['closed']}
    now = datetime.now()
    counts: Counter = Counter()
    ages: dict[str, list[float]] = {}
    modes: Counter = Counter()
    stalled = []
    keys = [str(row['call_key']) for row in rows]
    # The first status is that of the calls not attended; the open calls are those between it and the closed ones.
    first = statuses[0]['name'] if statuses else ''
    for row in rows:
        status = str(row['status'] or '')
        counts[status] += 1
        modes[str(row['status_mode'] or 'auto')] += 1
        started = _parse_time(row['start_time'])
        if started is not None:
            ages.setdefault(status, []).append((now - started).total_seconds() / 86400)
        # Stalled: open calls (attended and not closed) without any change for a while.
        days = stalled_days(status, row['updated_at'], row['start_time'], closed, first, now)
        if days is not None:
            stalled.append({'call_key': str(row['call_key']), 'status': status, 'operator': str(row['operator'] or ''),
                            'campaign': str(row['campaign'] or ''), 'city': str(row['city'] or ''),
                            'days': days, 'followed_up': bool(row['updated_at'])})
    pipeline = [{'status': item['name'], 'color': item['color'], 'closed': item['closed'], 'count': counts.get(item['name'], 0),
                 'avg_age_days': round(sum(ages.get(item['name'], [])) / len(ages[item['name']]), 1) if ages.get(item['name']) else None}
                for item in statuses]
    pipeline += [{'status': name, 'color': '', 'closed': False, 'count': count, 'avg_age_days': None}
                 for name, count in counts.items() if name not in {item['name'] for item in statuses}]
    phases = []
    for field in definitions:
        if field['section'] not in PHASE_SECTIONS or field['type'] != 'list' or field['source'] not in {'user', 'derived'}:
            continue
        values: Counter = Counter()
        for row in rows:
            try:
                stored = json.loads(row['field_values_json'] or '{}') or {}
            except (TypeError, ValueError):
                stored = {}
            values[stored.get(field['key'], '') if field['source'] == 'user' else derived_value(field, row)] += 1
        # A field whose values have no colour takes the palette, so that its values can be told apart.
        colours = ([option['color'] for option in field['options']] if any(option['color'] for option in field['options'])
                   else series_colours(len(field['options'])))
        phases.append({'key': field['key'], 'label': field['label'], 'section': field['section'], 'empty': values.pop('', 0),
                       'items': [{'value': option['name'], 'count': values.get(option['name'], 0), 'color': colour}
                                 for option, colour in zip(field['options'], colours)]})
    durations: dict[str, list[float]] = {}
    moves: Counter = Counter()
    with task_repository.connection() as connection:
        history: dict[str, list[Any]] = {}
        for entry in _rows_of_calls(connection, f'SELECT id, call_key, old_value, new_value, changed_at FROM {NQ_CALL_HISTORY_TABLE}',
                                    keys, where="field IN ('status', 'status_auto')", order='changed_at, id'):
            history.setdefault(str(entry['call_key']), []).append(entry)
    starts = {str(row['call_key']): _parse_time(row['start_time']) for row in rows}
    for key, entries in history.items():
        previous = starts.get(key)
        for entry in entries:
            moment = _parse_time(entry['changed_at'])
            moves[(str(entry['old_value'] or '—'), str(entry['new_value'] or '—'))] += 1
            if previous is not None and moment is not None and moment >= previous:
                durations.setdefault(str(entry['old_value'] or ''), []).append((moment - previous).total_seconds() / 86400)
            previous = moment or previous
    time_in_status = [{'status': name, 'avg_days': round(sum(values) / len(values), 1), 'moves': len(values)}
                      for name, values in durations.items() if name]
    order = [item['name'] for item in statuses]
    time_in_status.sort(key=lambda item: order.index(item['status']) if item['status'] in order else len(order))
    stalled.sort(key=lambda item: -item['days'])
    identified = sum(1 for row in rows if row['root_category'] or row['root_cause'])
    # Open: the attended calls not closed yet, every status between the first one (not attended) and the closed ones.
    open_statuses = [item['status'] for item in pipeline if not item['closed'] and item['status'] != first]
    waiting = next((item for item in pipeline if item['status'] == first and not item['closed']), None)
    return {
        'total': len(rows), 'pipeline': pipeline, 'modes': {'auto': modes.get('auto', 0), 'manual': modes.get('manual', 0)},
        'open': sum(item['count'] for item in pipeline if item['status'] in open_statuses), 'open_statuses': open_statuses,
        # Not Attended: the calls in the first status, nobody has followed them up yet.
        'not_attended': {'status': waiting['status'], 'count': waiting['count'], 'color': waiting['color']} if waiting else None,
        'rca': {'identified': identified, 'not_identified': len(rows) - identified},
        'phases': phases, 'time_in_status': time_in_status,
        'moves': [{'from': old, 'to': new, 'count': count} for (old, new), count in moves.most_common(12)],
        'stalled_days': STALLED_DAYS, 'stalled_total': len(stalled), 'stalled': stalled[:15],
        'rules': status_rules(task_repository),
        # The names of the fields the rules read and the colours of their values, to draw the rules as the page does.
        'rule_fields': {key: {'label': item['label'], 'colors': {option['name']: option.get('color', '')
                                                                  for field in definitions if field['key'] == key
                                                                  for option in field['options']}}
                        for key, item in nq_catalog.condition_fields(definitions).items()},
    }


def rca_insights(task_repository: Any, filters: dict[str, Any], username: str) -> dict[str, Any]:
    """The root cause sources of the filtered calls compared (the NetCheck RCA, the Ericsson RCA, the DriveTest Analyzer
    RCA and the analysts): how many calls each one covers, how often they agree, the root domains and category → cause
    hierarchies of each one and how the analysts' choices relate to each RCA.

    The root domains of a source count the calls it covers: those its values map onto no catalog domain are Not classified.
    """
    rows, _context = _filtered_calls(task_repository, filters, username,
                                     'call_key, rca_json, dta_json, failure_classification, failure_category, failure_subcategory, '
                                     'failure_comment, technology, failure_technology, root_domain, root_category, root_cause')
    taxonomy = list_root_causes(task_repository)
    rule = taxonomy.get('rule') or DEFAULT_ROOT_CAUSE_RULE
    # NetCheck alone: the CDR fields, never the comments.
    cdr_rule = {**rule, 'comments': False, 'comment_domain': False}
    colors = {item['name']: item['color'] for item in taxonomy['domains']}
    coverage = Counter()
    agreement = {name: Counter() for name in ('selected_netcheck', 'selected_script', 'selected_dta', 'netcheck_script', 'netcheck_dta',
                                              'script_dta')}
    sources = ('netcheck', 'script', 'dta', 'selected')
    hierarchies: dict[str, dict[str, Counter]] = {source: {} for source in sources}
    confusion: dict[str, Counter] = {source: Counter() for source in RCA_FILTER_SOURCES}
    domains: dict[str, Counter] = {source: Counter() for source in sources}
    # The root domains the calls of each category fall in: the categories of the source, and those of the catalog.
    category_domains: dict[str, dict[str, Counter]] = {source: {} for source in sources}
    mapped_domains: dict[str, dict[str, Counter]] = {source: {} for source in sources}
    mapped_counts: dict[str, Counter] = {source: Counter() for source in sources}

    def count_domain(source: str, category: str, mapped: str, domain: str) -> None:
        domains[source][domain] += 1
        category_domains[source].setdefault(category, Counter())[domain] += 1
        mapped_counts[source][mapped] += 1
        mapped_domains[source].setdefault(mapped, Counter())[domain] += 1
    for row in rows:
        script_raw = rca_raw_pair(row, 'script', taxonomy)
        netcheck_raw = rca_raw_pair(row, 'netcheck', taxonomy)
        selected = (str(row['root_category'] or ''), str(row['root_cause'] or ''))
        script = nq_rca.map_to_catalog(*script_raw, taxonomy, rule.get('match', 'words')) if any(script_raw) else None
        netcheck = nq_rca.suggest_from_text(row, taxonomy, cdr_rule) if any(netcheck_raw) else None
        found = source_root(row, 'dta', taxonomy)
        dta = found if found['category'] or found['cause'] else None
        coverage['total'] += 1
        if script is not None:
            coverage['script'] += 1
            count_domain('script', script_raw[0] or '—', script['category'] or '—', script.get('domain') or NOT_CLASSIFIED)
            hierarchies['script'].setdefault(script_raw[0] or '—', Counter())[script_raw[1] or '—'] += 1
        if any(netcheck_raw):
            coverage['netcheck'] += 1
            count_domain('netcheck', netcheck_raw[0] or '—', (netcheck or {}).get('category') or '—',
                         (netcheck or {}).get('domain') or NOT_CLASSIFIED)
            hierarchies['netcheck'].setdefault(netcheck_raw[0] or '—', Counter())[netcheck_raw[1] or '—'] += 1
        if dta is not None:
            # Its categories and causes are those of the catalog already.
            coverage['dta'] += 1
            count_domain('dta', dta['category'] or '—', dta['category'] or '—', dta['domain'] or NOT_CLASSIFIED)
            hierarchies['dta'].setdefault(dta['category'] or '—', Counter())[dta['cause'] or '—'] += 1
        if any(selected):
            coverage['selected'] += 1
            count_domain('selected', selected[0] or '—', selected[0] or '—',
                         str(row['root_domain'] or '') or domain_of(taxonomy, *selected) or NOT_CLASSIFIED)
            hierarchies['selected'].setdefault(selected[0] or '—', Counter())[selected[1] or '—'] += 1
            for source, mapped in (('netcheck', netcheck), ('script', script), ('dta', dta)):
                if mapped and (mapped.get('category') or mapped.get('cause')):
                    confusion[source][(mapped.get('category') or '—', selected[0] or '—')] += 1
                    target = agreement[f'selected_{source}']
                    target['compared'] += 1
                    same = (mapped.get('category') and mapped['category'] == selected[0]) or \
                        (not mapped.get('category') and mapped.get('cause') and mapped['cause'] == selected[1])
                    target['agree'] += int(bool(same))
        if script and netcheck and (script.get('category') or netcheck.get('category')):
            agreement['netcheck_script']['compared'] += 1
            agreement['netcheck_script']['agree'] += int(bool(script.get('category')) and script.get('category') == netcheck.get('category'))
        for name, other in (('netcheck_dta', netcheck), ('script_dta', script)):
            if dta and other and (other.get('category') or other.get('cause')):
                # The category when both give one, else the cause (many rules of the DT Analyzer RCA give only a cause).
                agreement[name]['compared'] += 1
                both = bool(dta['category'] and other.get('category'))
                agreement[name]['agree'] += int(dta['category'] == other.get('category') if both
                                                else bool(dta['cause']) and dta['cause'] == other.get('cause'))

    def domain_list(counts: Counter | None) -> list[dict[str, Any]]:
        return [{'domain': domain, 'count': count, 'color': colors.get(domain, '#b8c0c6')}
                for domain, count in (counts or Counter()).most_common()]

    def hierarchy(name: str, limit: int = 12) -> list[dict[str, Any]]:
        groups = hierarchies[name]
        ordered = sorted(groups.items(), key=lambda item: -sum(item[1].values()))[:limit]
        return [{'category': category, 'count': sum(causes.values()), 'domains': domain_list(category_domains[name].get(category)),
                 'causes': [{'cause': cause, 'count': count} for cause, count in causes.most_common(8)]} for category, causes in ordered]

    def matrix(source: str) -> dict[str, Any]:
        cells = confusion[source]
        totals_rows = Counter()
        totals_columns = Counter()
        for (row_name, column_name), count in cells.items():
            totals_rows[row_name] += count
            totals_columns[column_name] += count
        rows_order = [name for name, _count in totals_rows.most_common(10)]
        columns_order = [name for name, _count in totals_columns.most_common(10)]
        return {'rows': rows_order, 'columns': columns_order,
                'cells': [[cells.get((row_name, column_name), 0) for column_name in columns_order] for row_name in rows_order]}

    def rate(name: str) -> dict[str, Any]:
        target = agreement[name]
        return {'agree': target['agree'], 'compared': target['compared'],
                'rate': round(target['agree'] * 100 / target['compared'], 1) if target['compared'] else None}

    return {
        'provider': provider_texts(task_repository),
        'coverage': {key: coverage.get(key, 0) for key in ('total', 'netcheck', 'script', 'dta', 'selected')},
        'agreement': {name: rate(name) for name in agreement},
        'hierarchies': {name: hierarchy(name) for name in hierarchies},
        # What each source proposes on the Root Cause Catalog: its categories translated onto the catalog ('—' for none).
        'mapped': {name: [{'category': category, 'count': count, 'domains': domain_list(mapped_domains[name].get(category))}
                          for category, count in counts.most_common(12)] for name, counts in mapped_counts.items()},
        'domains': {name: [{'domain': domain, 'count': count, 'color': colors.get(domain, '#b8c0c6')}
                           for domain, count in counts.most_common()] for name, counts in domains.items()},
        'confusion': {source: matrix(source) for source in confusion},
        'rca_results': rca_results_summary(task_repository),
    }


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------
# The call itself, before the catalog fields: what identifies the call and what the CDR says about it.
# JOIN_ID, the call key and its CDR first, to find a call at once.
EXPORT_COLUMNS = (
    ('JOIN_ID', 'join_id'), ('Call Key', 'call_key'), ('CDR', 'dataset_name'), ('Service', 'service_label'), ('Start Time', 'start_time'), ('End Time', 'end_time'), ('Operator', 'operator'),
    ('Operator_Vendor', 'operator_vendor'), ('Vendor_Operator', 'vendor_operator'), ('Vendor', 'vendor'),
    ('Campaign', 'campaign'), ('NR Mode', 'nr_mode'), ('Region', 'region'), ('Cluster', 'cluster'), ('City', 'city'),
    ('Technology', 'technology'), ('Test Name', 'test_name'), ('Session Type (CDR)', 'session_type'), ('Direction', 'direction'),
    ('Result', 'result'), ('Failure Phase', 'failure_phase'), ('Failure Technology', 'failure_technology'),
    ('Cell ID', 'cell_id'), ('Latitude', 'latitude'), ('Longitude', 'longitude'),
    ('CDR Version', 'version_label'), ('Latest CDR', 'latest_dataset_name'),
    ('NQ Samples', 'nq_samples'),
)
CALL_SECTION = {'key': 'call', 'label': 'Call', 'color': '#5E6B75'}
# Columns of the export that follow a follow-up field: (field reference, label, value key).
EXPORT_COMPANIONS = {'status': [('Status Set', 'status_set')]}
# Columns that come before the selected root category (or cause): the root cause decision ends the RCA block.
EXPORT_ROOT_COMPANIONS = [('Root Domain', 'root_domain'), ('Recommended Root Category', 'recommended_category'),
                          ('Recommended Root Cause', 'recommended_cause'), ('Recommendation Sources', 'recommendation_sources')]
# Header shades: every field of a section in one light shade of it, and the status of each block and the fields read
# most darker than the section: the selected root category and cause, the Failure Comment, the Comments and the long
# texts of the analysis (in wider columns), and the JOIN_ID and Call Key of the call.
KEY_FIELD_TINT = -0.2
FIELD_TINT = 0.35
CALL_FIELD_TINT = 0.75
EMPHASIS_FIELDS = {'selected_root_category', 'selected_root_cause', 'failure_comment', 'comments', 'description', 'findings',
                   'proposed_measure'}
EMPHASIS_CALL_COLUMNS = {'join_id', 'call_key'}
WIDE_FIELDS = {'description': 50, 'findings': 50, 'proposed_measure': 50}


def _tint(color: str, amount: float) -> str:
    """A lighter shade of a colour (amount 0 keeps it, 1 is white; below 0 darker), as RRGGBB."""
    value = int(color.lstrip('#'), 16) if nq_catalog.COLOR_PATTERN.fullmatch(color or '') else 0x7B8790
    channels = [(value >> shift) & 255 for shift in (16, 8, 0)]
    if amount < 0:
        return ''.join(f'{round(channel * (1 + amount)):02X}' for channel in channels)
    return ''.join(f'{round(channel + (255 - channel) * amount):02X}' for channel in channels)


def key_fields(definitions: list[dict[str, Any]]) -> set[str]:
    """The status field of each block: the NQ Call Status and the first list of Analysis, Implementation and Planning."""
    keys = {field['key'] for field in definitions if field['source'] == 'tracking' and field['source_ref'] == 'status'}
    for section in PHASE_SECTIONS:
        first = next((field for field in definitions if field['section'] == section and field['type'] == 'list'
                      and field['source'] in {'user', 'derived'}), None)
        if first:
            keys.add(first['key'])
    return keys


def _comment_log(rows: list[Any]) -> str:
    """Every comment of a call, one per line: date and time, author and text."""
    lines = []
    for row in rows:
        if row['deleted_at']:
            continue
        moment = str(row['created_at'] or '').replace('T', ' ')[:16]
        lines.append(f"{moment} · {row['created_by']}: {str(row['body']).strip()}")
    return '\n'.join(lines)


def export_workbook(task_repository: Any, filters: dict[str, Any], username: str, *, workspace_layout_only: bool = False) -> bytes:
    """Every call that matches the filters with its catalog fields by section, its comments and its change history: the
    fields and CDR columns of the table layout the user sees (``workspace_layout_only``: that of the workspace)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    options = list_options(task_repository)
    definitions = provider_field_labels(list_fields(task_repository), task_repository)
    layouts = table_layouts(task_repository, username)
    layout = layouts['workspace'] if workspace_layout_only else layouts['effective']
    excel = set(layout['excel_fields'])
    sections = {section['key']: section for section in list_sections(task_repository)}
    closed = [item['name'] for item in options['statuses'] if item['closed']]
    default = untracked_status(task_repository, options)
    base, base_params = _base_sql(default, task_repository, _scope(filters))
    where, params = _filter_sql(_resolve_key_filters(task_repository, filters), username, closed, definitions)
    with task_repository.connection() as connection:
        rows = connection.execute(
            f'WITH calls AS ({base}) SELECT * FROM calls{where} ORDER BY start_time DESC, call_key', [*base_params, *params],
        ).fetchall()
        calls = [_call_payload(row) for row in rows]
        keys = [call['call_key'] for call in calls]
        names = {int(row['id']): str(row['file_name']) for row in connection.execute('SELECT id, file_name FROM datasets')}
        comments: list[Any] = []
        history: list[Any] = []
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            marks = ', '.join('?' for _ in chunk)
            comments.extend(connection.execute(
                f'SELECT * FROM {NQ_CALL_COMMENTS_TABLE} WHERE call_key IN ({marks}) ORDER BY id', chunk).fetchall())
            history.extend(connection.execute(
                f'SELECT * FROM {NQ_CALL_HISTORY_TABLE} WHERE call_key IN ({marks}) ORDER BY id', chunk).fetchall())
        sample_sql, sample_params = _sample_sql(default, task_repository)
        samples = [_call_payload(row) for row in connection.execute(
            f'WITH samples AS ({sample_sql}) SELECT * FROM samples WHERE parent_key IN (SELECT value FROM json_each(?)) '
            'ORDER BY parent_key, start_time',
            [*sample_params, json.dumps([call['call_key'] for call in calls if call['service'] == 'speech'])]).fetchall()]
        sample_keys = [sample['call_key'] for sample in samples]
        for start in range(0, len(sample_keys), 500):
            chunk = sample_keys[start:start + 500]
            marks = ', '.join('?' for _ in chunk)
            comments.extend(connection.execute(
                f'SELECT * FROM {NQ_CALL_COMMENTS_TABLE} WHERE call_key IN ({marks}) ORDER BY id', chunk).fetchall())
            history.extend(connection.execute(
                f'SELECT * FROM {NQ_CALL_HISTORY_TABLE} WHERE call_key IN ({marks}) ORDER BY id', chunk).fetchall())
        learned = learned_decisions(connection)
    by_key = {call['call_key']: call for call in calls}
    by_key.update({sample['call_key']: sample for sample in samples})
    taxonomy = list_root_causes(task_repository)
    labels = source_labels(task_repository)
    per_call: dict[str, list[Any]] = {}
    for row in comments:
        per_call.setdefault(str(row['call_key']), []).append(row)
    for call in [*calls, *samples]:
        notes = '\n'.join(str(row['body']) for row in per_call.get(call['call_key'], []) if not row['deleted_at'])
        recommendation = recommendation_for(call, taxonomy, notes, learned)['recommendation'] or {}
        call['values'] = {field['key']: catalog_value(field, call, call.get('rca'), call.get('fields')) for field in definitions}
        call['comment_log'] = _comment_log(per_call.get(call['call_key'], []))
        call['status_set'] = 'By hand' if call.get('status_mode') == 'manual' else 'Automatic'
        call['recommended_category'] = recommendation.get('category', '')
        call['recommended_cause'] = recommendation.get('cause', '')
        call['recommendation_sources'] = ', '.join(labels.get(name, name) for name in recommendation.get('sources') or [])
        call['dataset_name'] = names.get(int(call['dataset_id']), '')
        call['latest_dataset_name'] = names.get(int(call.get('latest_dataset_id') or call['dataset_id']), '')
        call['version_label'] = VERSION_LABELS.get(call.get('version_state') or 'current', '')

    # (section, label, getter, tint): the call columns, the catalog in its order, the CDR columns and the keys.
    columns: list[tuple[dict[str, str], str, Callable[[dict[str, Any]], Any], float]] = [
        (CALL_SECTION, label, (lambda call, key=key: call.get(key)), KEY_FIELD_TINT if key in EMPHASIS_CALL_COLUMNS else CALL_FIELD_TINT)
        for label, key in EXPORT_COLUMNS]
    exported = [field for field in definitions if field['key'] in excel]
    highlighted = key_fields(definitions)
    # The recommendation goes right before the selected root category (or cause, without the category).
    selected = next((field['key'] for field in exported if field['source'] == 'tracking'
                     and field['source_ref'] in {'root_category', 'root_cause'}), None)
    # The column (1-based) and width of the wide fields.
    wide_columns: dict[int, int] = {}
    for field in exported:
        section = sections.get(field['section'], CALL_SECTION)
        tint = KEY_FIELD_TINT if field['key'] in highlighted or field['key'] in EMPHASIS_FIELDS else FIELD_TINT
        if field['key'] == selected:
            columns += [(section, label, lambda call, key=key: call.get(key, ''), FIELD_TINT)
                        for label, key in EXPORT_ROOT_COMPANIONS]
        if field['source'] == 'tracking' and field['source_ref'] == 'comments':
            columns.append((section, field['label'], lambda call: call.get('comment_log', ''), tint))
        elif field['source'] == 'tracking' and field['source_ref'] == 'updated_at':
            columns.append((section, field['label'], lambda call: str(call.get('updated_at') or '').replace('T', ' ')[:19], tint))
        else:
            columns.append((section, field['label'], lambda call, key=field['key']: call['values'].get(key, ''), tint))
        if field['key'] in WIDE_FIELDS:
            wide_columns[len(columns)] = WIDE_FIELDS[field['key']]
        if field['source'] == 'tracking':
            for label, key in EXPORT_COMPANIONS.get(field['source_ref'], []):
                columns.append((section, label, lambda call, key=key: call.get(key, ''), FIELD_TINT))
    extra_section = {'key': 'cdr', 'label': 'CDR Columns', 'color': '#5E6B75'}
    columns += [(extra_section, name, (lambda call, name=name: (call.get('extra') or {}).get(name, '')), 0.8)
                for name in dict.fromkeys([*layout['cdr'], *layout['export_cdr']])
                if not any(field['source'] == 'cdr' and field['source_ref'] == f'column:{name}' for field in definitions)]
    columns += [(CALL_SECTION, 'Updated By', lambda call: call.get('updated_by', ''), CALL_FIELD_TINT),
                (CALL_SECTION, 'Updated At', lambda call: str(call.get('updated_at') or '').replace('T', ' ')[:19], CALL_FIELD_TINT)]

    workbook = Workbook()
    thin = Side(style='thin', color='FFFFFF')
    sheet = workbook.active
    sheet.title = 'NQ Calls'
    # Row 1: the sections, merged over their columns; row 2: the fields, in a lighter shade of their section.
    position = 1
    while position <= len(columns):
        section = columns[position - 1][0]
        end = position
        while end < len(columns) and columns[end][0] is section:
            end += 1
        cell = sheet.cell(1, position, section['label'].upper())
        cell.font = Font(bold=True, color=nq_catalog.contrast_color(section['color']))
        cell.fill = PatternFill('solid', fgColor=section['color'].lstrip('#'))
        cell.alignment = Alignment(horizontal='center', vertical='center')
        if end > position:
            sheet.merge_cells(start_row=1, start_column=position, end_row=1, end_column=end)
        position = end + 1
    for index, (section, label, _getter, tint) in enumerate(columns, start=1):
        cell = sheet.cell(2, index, label)
        shade = _tint(section['color'], tint)
        cell.fill = PatternFill('solid', fgColor=shade)
        cell.font = Font(bold=True, color=nq_catalog.contrast_color(f'#{shade}'))
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        cell.border = Border(left=thin, right=thin)
        sheet.column_dimensions[get_column_letter(index)].width = wide_columns.get(index) or max(12, min(48, len(label) + 6))
    for call in calls:
        sheet.append([_excel_value(getter(call)) for _section, _label, getter, _tint_value in columns])
    sheet.freeze_panes = 'A3'
    sheet.row_dimensions[2].height = 32
    if calls:
        sheet.auto_filter.ref = f'A2:{get_column_letter(len(columns))}{len(calls) + 2}'
    log_columns = [index for index, (_section, label, _getter, _tint_value) in enumerate(columns, start=1)
                   if any(field['source_ref'] == 'comments' and field['label'] == label for field in definitions)]
    for index in log_columns:
        sheet.column_dimensions[get_column_letter(index)].width = 70
        for cell in sheet.iter_rows(min_row=3, min_col=index, max_col=index):
            cell[0].alignment = Alignment(wrap_text=True, vertical='top')

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill('solid', fgColor='9C1C47')

    def write_sheet(target, headers: list[str], data: list[list[Any]], widths: list[int]) -> None:
        target.append(headers)
        for cell in target[1]:
            cell.font, cell.fill = header_font, header_fill
            cell.alignment = Alignment(vertical='center')
        for values in data:
            target.append([_excel_value(value) for value in values])
        target.freeze_panes = 'A2'
        if data:
            target.auto_filter.ref = target.dimensions
        for index, width in enumerate(widths, start=1):
            target.column_dimensions[get_column_letter(index)].width = width

    if samples:
        # Speech samples with their own follow-up, below the call they belong to.
        sample_columns = [('JOIN_ID', lambda sample: sample.get('join_id')),
                          ('Call Start Time', lambda sample: by_key.get(str(sample['parent_key']), {}).get('start_time', '')),
                          ('Operator', lambda sample: sample.get('operator')), ('Campaign', lambda sample: sample.get('campaign')),
                          ('Sample', lambda sample: sample.get('sample_id')), ('Start Time', lambda sample: sample.get('start_time')),
                          ('Result', lambda sample: sample.get('result')),
                          *((field['label'], lambda sample, key=field['key']: sample['values'].get(key, ''))
                            for field in definitions if field['key'] in excel and field['source_ref'] != 'comments'),
                          ('Comments', lambda sample: sample.get('comment_log', '')),
                          ('Call Key', lambda sample: sample.get('parent_key')), ('Sample Key', lambda sample: sample.get('call_key'))]
        write_sheet(workbook.create_sheet('Speech Samples'), [label for label, _getter in sample_columns],
                    [[getter(sample) for _label, getter in sample_columns] for sample in samples],
                    [max(12, min(40, len(label) + 6)) for label, _getter in sample_columns])

    def call_context(call_key: str) -> list[Any]:
        call = by_key.get(call_key, {})
        return [call.get('join_id', ''), call.get('service_label', ''), call.get('operator', ''), call.get('campaign', ''),
                call.get('start_time', '')]

    # The comments and changes of each call together, in the order of the NQ Calls sheet (a Speech sample with its
    # call), then by date.
    position = {call['call_key']: index for index, call in enumerate(calls)}
    position.update({sample['call_key']: position.get(str(sample['parent_key']), len(calls)) for sample in samples})

    def by_call(rows: list[Any], moment: str) -> list[Any]:
        return sorted(rows, key=lambda row: (position.get(str(row['call_key']), len(calls)), str(row['call_key']),
                                             str(row[moment] or ''), int(row['id'])))

    write_sheet(
        workbook.create_sheet('Comments'),
        ['JOIN_ID', 'Service', 'Operator', 'Campaign', 'Start Time', 'Comment', 'Author', 'Created At', 'Edited By',
         'Edited At', 'Deleted By', 'Deleted At', 'Call Key'],
        [[*call_context(str(row['call_key'])), str(row['body']), row['created_by'], row['created_at'], row['edited_by'],
          row['edited_at'], row['deleted_by'], row['deleted_at'], row['call_key']] for row in by_call(comments, 'created_at')],
        [36, 10, 16, 16, 24, 70, 16, 26, 16, 26, 16, 26, 28],
    )
    write_sheet(
        workbook.create_sheet('History'),
        ['JOIN_ID', 'Service', 'Operator', 'Campaign', 'Start Time', 'Change', 'Previous Value', 'New Value', 'Changed By',
         'Changed At', 'Call Key'],
        [[*call_context(str(row['call_key'])), history_label(str(row['field']), definitions),
          row['old_value'], row['new_value'], row['changed_by'], row['changed_at'], row['call_key']] for row in by_call(history, 'changed_at')],
        [36, 10, 16, 16, 24, 18, 40, 40, 16, 26, 28],
    )
    for target in workbook.worksheets[1:]:
        for row in target.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical='top')
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _excel_value(value: Any) -> Any:
    if value is None:
        return ''
    if isinstance(value, str) and value.startswith('='):
        # Text that would be written as a formula.
        return "'" + value
    return value


HISTORY_LABELS = {
    'status': 'Status', 'status_auto': 'Status (automatic)', 'status_mode': 'Status set', 'team': 'Team', 'assignee': 'Assignee',
    'root_domain': 'Root Domain', 'root_category': 'Root Category', 'root_cause': 'Root Cause',
    'comment_edit': 'Comment edited', 'comment_delete': 'Comment deleted',
}


def history_label(field: str, definitions: list[dict[str, Any]]) -> str:
    if field.startswith('field:'):
        key = field[6:]
        return next((item['label'] for item in definitions if item['key'] == key), key)
    return HISTORY_LABELS.get(field, field)


# ---------------------------------------------------------------------------
# Portability: export, import, transfers and backups
# ---------------------------------------------------------------------------
def _call_identities(connection: Any, keys: set[str]) -> list[dict[str, str]]:
    """The JOIN_ID and service of each call (and the sample of each Speech sample) among ``keys``: what its key is
    computed from, so a document finds its calls whatever way the keys are computed."""
    identities: dict[str, dict[str, str]] = {}
    for row in connection.execute(
            f"SELECT call_key, sample_key, sample_id, service, join_id FROM {NQ_CALLS_TABLE} WHERE join_id <> '' ORDER BY rowid"):
        if str(row['call_key']) in keys:
            identities.setdefault(str(row['call_key']), {'call_key': str(row['call_key']), 'service': str(row['service']),
                                                         'join_id': str(row['join_id'])})
        if row['sample_key'] and str(row['sample_key']) in keys:
            identities.setdefault(str(row['sample_key']), {'call_key': str(row['sample_key']), 'service': str(row['service']),
                                                           'join_id': str(row['join_id']), 'sample_id': str(row['sample_id'])})
    return sorted(identities.values(), key=lambda item: item['call_key'])


def _document_call_keys(calls: list[dict[str, Any]]) -> dict[str, str]:
    """The key of each call of a document as this version computes it from its JOIN_ID, when it differs."""
    keys = {}
    for item in calls:
        key, service, join_id = _text(item.get('call_key')), _text(item.get('service')), _text(item.get('join_id'))
        if not key or not join_id or service not in SERVICE_LABELS:
            continue
        current = call_key_for(service, {}, join_id=join_id)
        if _text(item.get('sample_id')):
            current = sample_key_for(current, _text(item.get('sample_id')))
        if current != key:
            keys[key] = current
    return keys


def export_tracking_document(task_repository: Any) -> bytes:
    """The statuses, teams, follow-up, comments and history of a workspace, with the JOIN_ID and service of each
    call (``calls``) to find it again whatever way its key is computed."""
    ensure_nq_tables(task_repository)
    with task_repository.connection() as connection:
        tracking = [dict(row) for row in connection.execute(
            f'SELECT call_key, status, status_mode, team, assignee, root_domain, root_category, root_cause, version, updated_by, '
            f'updated_at FROM {NQ_CALL_TRACKING_TABLE} ORDER BY call_key')]
        rca_results = [dict(row) for row in connection.execute(
            f'SELECT original_join_id AS join_id, values_json, source_file, imported_by, imported_at '
            f'FROM {NQ_RCA_RESULTS_TABLE} ORDER BY join_id')]
        comments = [dict(row) for row in connection.execute(
            f'SELECT uid, call_key, body, created_by, created_at, edited_by, edited_at, deleted_by, deleted_at '
            f'FROM {NQ_CALL_COMMENTS_TABLE} ORDER BY id')]
        history = [dict(row) for row in connection.execute(
            f'SELECT uid, call_key, field, old_value, new_value, changed_by, changed_at FROM {NQ_CALL_HISTORY_TABLE} ORDER BY id')]
        values = [dict(row) for row in connection.execute(
            f"SELECT call_key, field_key, value, updated_by, updated_at FROM {NQ_FIELD_VALUES_TABLE} "
            "ORDER BY call_key, field_key")]
        calls = _call_identities(connection, {str(item['call_key']) for item in (*tracking, *comments, *history, *values)})
    document = {
        'format': TRACKING_FORMAT, 'version': TRACKING_FORMAT_VERSION, **_configuration(task_repository), 'calls': calls,
        'tracking': tracking, 'comments': comments, 'history': history, 'field_values': values, 'rca_results': rca_results,
    }
    return json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')


def _configuration(task_repository: Any) -> dict[str, Any]:
    return {
        'options': list_options(task_repository), 'root_causes': list_root_causes(task_repository),
        'fields': list_fields(task_repository), 'sections': list_sections(task_repository),
        'status_rules': status_rules(task_repository), 'table_columns': table_columns(task_repository),
        'column_order': workspace_layout(task_repository)['order'], 'user_layouts': user_layouts(task_repository),
        'analyses_equivalences': workspace_equivalences(task_repository),
        'prioritization': nq_prioritization.load_settings(task_repository),
        'dta_rca_rules': nq_dta_rca.load_rules(task_repository),
        'dta_rca_settings': nq_dta_rca.load_settings(task_repository),
    }


def export_configuration_document(task_repository: Any) -> bytes:
    """The Analysis Center configuration of a workspace, without the follow-up of its calls."""
    ensure_nq_tables(task_repository)
    document = {'format': CONFIGURATION_FORMAT, 'version': CONFIGURATION_FORMAT_VERSION, **_configuration(task_repository)}
    return json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')


def import_configuration_document(task_repository: Any, payload: bytes | str) -> None:
    """Merge an Analysis Center configuration like the configuration part of a tracking document."""
    document = json.loads(payload.decode('utf-8') if isinstance(payload, bytes) else payload)
    if not isinstance(document, dict) or document.get('format') != CONFIGURATION_FORMAT:
        raise ValueError('The file is not a Non-Qualified Calls configuration export.')
    if int(document.get('version') or 0) > CONFIGURATION_FORMAT_VERSION:
        raise ValueError('The Non-Qualified Calls configuration export was created by a newer version.')
    ensure_nq_tables(task_repository)
    _merge_configuration(task_repository, document)


def _incoming_root_catalog(document: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The root cause catalog of a tracking document; the first version listed causes inside their domains."""
    root = document.get('root_causes') if isinstance(document.get('root_causes'), dict) else {}
    catalog: dict[str, list[dict[str, Any]]] = {'domains': [], 'categories': [], 'causes': []}
    for domain in root.get('domains') or []:
        if not isinstance(domain, dict) or not domain.get('name'):
            continue
        catalog['domains'].append({'name': domain['name'], 'color': domain.get('color') or '', 'keywords': domain.get('keywords') or []})
        for cause in domain.get('causes') or []:
            if isinstance(cause, dict) and cause.get('name'):
                catalog['causes'].append({'name': cause['name'], 'domain': domain['name'], 'keywords': cause.get('keywords') or []})
    for plural in ('categories', 'causes'):
        catalog[plural] += [item for item in root.get(plural) or [] if isinstance(item, dict) and item.get('name')]
    # The domains chosen by hand travel, not those the categories or keywords give.
    stored = nq_catalog.stored_root_catalog(catalog)
    return {'domains': catalog['domains'], 'categories': stored['categories'], 'causes': stored['causes']}


def _merged_fields(current_fields: list[dict[str, Any]], incoming_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The fields of a workspace with those of a document merged: its missing fields added (in their section) and the
    values of its list fields merged, with the settings of the document (section, Table column, Excel and Summary
    breakdown), in the order of the document, then those only the workspace has."""
    labels = {field['label'].casefold() for field in current_fields}
    refs = {field['source_ref'] for field in current_fields if field['source'] == 'tracking'}
    merged = [dict(field) for field in current_fields]
    for item in incoming_fields:
        target = next((field for field in merged if field['key'] == item['key']), None)
        if target is None:
            if (str(item['label']).casefold() in labels or str(item.get('type')) not in FIELD_TYPES
                    or (item.get('source') == 'tracking' and item.get('source_ref') in refs)):
                continue
            merged.append({**item, 'options': [option for option in item.get('options') or [] if isinstance(option, dict)]})
            continue
        if target['type'] == 'list' and str(item.get('type')) == 'list' and target['source'] in {'user', 'derived'}:
            names = {option['name'].casefold() for option in target['options']}
            target['options'] = [*target['options'], *(
                option for option in item.get('options') or []
                if isinstance(option, dict) and str(option.get('name') or '').casefold() not in names)]
        # The settings of the package: its section, Table column, Excel and Summary breakdown.
        target.update({key: item[key] for key in ('section', 'in_table', 'in_export', 'in_summary') if key in item})
    # The fields of the package in its order, then those only the workspace has, in theirs.
    order = {str(item['key']): index for index, item in enumerate(incoming_fields)}
    merged.sort(key=lambda field: order.get(field['key'], len(order)))
    return merged


def predicted_configuration(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """The configuration document of a workspace (``current``, as export_configuration_document gives it) after
    importing ``incoming``, as _merge_configuration merges it, for the preview of an import (nothing is written): the
    missing statuses, teams (and the members of the teams), root cause catalog entries, fields and list values are
    added and the equivalences the workspace has not reviewed, and the sections, status rules, field settings, table
    columns and order, personal layouts (by username), root cause rule and settings, NQ Prioritization and DT Analyzer
    RCA rules of the document are taken."""
    predicted = json.loads(json.dumps(current))

    def merged_by_name(current_items: Any, incoming_items: Any, members: bool = False) -> list[dict[str, Any]]:
        merged = [dict(item) for item in current_items or [] if isinstance(item, dict)]
        found = {str(item.get('name') or '').casefold(): item for item in merged}
        for item in incoming_items or []:
            if not isinstance(item, dict) or not str(item.get('name') or '').strip():
                continue
            target = found.get(str(item['name']).casefold())
            if target is None:
                merged.append(dict(item))
                found[str(item['name']).casefold()] = merged[-1]
            elif members:
                names = {str(name).casefold(): name for name in [*(target.get('members') or []), *(item.get('members') or [])]}
                target['members'] = sorted(names.values(), key=lambda name: str(name).casefold())
        return merged

    options, incoming_options = predicted.get('options') or {}, incoming.get('options') or {}
    if isinstance(options, dict) and isinstance(incoming_options, dict):
        options['statuses'] = merged_by_name(options.get('statuses'), incoming_options.get('statuses'))
        options['teams'] = merged_by_name(options.get('teams'), incoming_options.get('teams'), members=True)
        predicted['options'] = options
    roots, incoming_roots = predicted.get('root_causes') or {}, incoming.get('root_causes') or {}
    if isinstance(roots, dict) and isinstance(incoming_roots, dict):
        for plural in ('domains', 'categories', 'causes'):
            roots[plural] = merged_by_name(roots.get(plural), incoming_roots.get(plural))
        roots.update({key: incoming_roots[key] for key in ('rule', 'require_to_close') if key in incoming_roots})
        predicted['root_causes'] = roots
    incoming_fields = [item for item in incoming.get('fields') or [] if isinstance(item, dict) and item.get('key') and item.get('label')]
    if incoming_fields and isinstance(predicted.get('fields'), list):
        predicted['fields'] = _merged_fields(predicted['fields'], incoming_fields)
    for key, kind in (('sections', list), ('status_rules', list), ('table_columns', dict), ('column_order', list), ('prioritization', dict),
                      ('dta_rca_rules', list), ('dta_rca_settings', dict)):
        if isinstance(incoming.get(key), kind):
            predicted[key] = incoming[key]
    layouts = {str(item.get('username') or '').casefold(): item for item in predicted.get('user_layouts') or [] if isinstance(item, dict)}
    for item in incoming.get('user_layouts') or []:
        if isinstance(item, dict) and str(item.get('username') or '').strip():
            layouts[str(item['username']).strip().casefold()] = {**layouts.get(str(item['username']).strip().casefold(), {}), **item}
    predicted['user_layouts'] = list(layouts.values())
    equivalences = predicted.get('analyses_equivalences') if isinstance(predicted.get('analyses_equivalences'), dict) else {}
    for target, values in _normalize_equivalences(incoming.get('analyses_equivalences')).items():
        for key, item in values.items():
            equivalences.setdefault(target, {}).setdefault(key, item)
    predicted['analyses_equivalences'] = equivalences
    return predicted


# The settings of a field of the catalog and of the other entries of the configuration, as an import tells their changes.
CONFIGURATION_LABELS = {
    'label': 'Label', 'section': 'Section', 'type': 'Type', 'in_table': 'Table column', 'in_export': 'Excel',
    'in_summary': 'Summary breakdown', 'required_to_close': 'Required to close', 'suggest_from': 'Suggested from',
    'description': 'Description', 'color': 'Colour', 'closed': 'Closed', 'members': 'Members', 'keywords': 'Keywords',
    'domain': 'Domain', 'category': 'Category',
}


def configuration_changes(before: Any, after: Any) -> list[str]:
    """What changed in the NQ Calls Configuration of a workspace, from its export documents before and after an import (or
    as the import would leave it), a line each: the statuses and teams, the sections, the fields of the catalog and their
    values, the Status Rules, the root cause catalog and its suggestion rule, the layout of the workspace and those of the
    users, the equivalences of the Previous NQ Analyses, the NQ Prioritization and the DT Analyzer RCA rules."""
    from src.modules.import_changes import describe_changes, field_label, list_change

    old = before if isinstance(before, dict) else {}
    new = after if isinstance(after, dict) else {}
    lines: list[str] = []
    dicts = lambda value: [item for item in value or [] if isinstance(item, dict)] if isinstance(value, list) else []  # noqa: E731
    section = lambda document, key: document.get(key) if isinstance(document.get(key), dict) else {}  # noqa: E731

    def entries(title: str, singular: str, old_items: Any, new_items: Any, attributes: tuple[str, ...], key: str = 'name',
                name: Any = None) -> None:
        """The entries of a list found by ``key``: those added and removed, then what changed in each of the others."""
        name = name or (lambda item: str(item.get(key)))
        was = {str(item.get(key) or '').casefold(): item for item in dicts(old_items) if str(item.get(key) or '').strip()}
        now = {str(item.get(key) or '').casefold(): item for item in dicts(new_items) if str(item.get(key) or '').strip()}
        if set(was) != set(now):
            lines.append(list_change(title, [name(item) for item in was.values()], [name(item) for item in now.values()]))
        for found, item in now.items():
            if found not in was:
                continue
            values = lambda entry: {attribute: entry.get(attribute) for attribute in attributes}  # noqa: E731
            described = describe_changes(values(was[found]), values(item), CONFIGURATION_LABELS)
            if item.get('type') == 'list' and was[found].get('type') == 'list':
                # The values of a list field by name, then those whose colour changed.
                options = lambda entry: {str(option.get('name')): option for option in dicts(entry.get('options'))}  # noqa: E731
                previous, current = options(was[found]), options(item)
                if set(previous) != set(current):
                    described.append(list_change('Values', list(previous), list(current)))
                recoloured = [value for value in current if value in previous and current[value].get('color') != previous[value].get('color')]
                if recoloured:
                    described.append(f"Colour of {', '.join(recoloured)}")
            if described:
                lines.append(f'{singular} {name(item)}: {"; ".join(described)}')

    options, new_options = section(old, 'options'), section(new, 'options')
    entries('Statuses', 'Status', options.get('statuses'), new_options.get('statuses'), ('color', 'closed'))
    entries('Teams', 'Team', options.get('teams'), new_options.get('teams'), ('color', 'members'))
    entries('Sections', 'Section', old.get('sections'), new.get('sections'), ('label', 'color'), key='key',
            name=lambda item: str(item.get('label') or item.get('key')))
    entries('Fields', 'Field', old.get('fields'), new.get('fields'),
            ('label', 'section', 'type', 'in_table', 'in_export', 'in_summary', 'required_to_close', 'suggest_from', 'description'),
            key='key', name=lambda item: str(item.get('label') or item.get('key')))
    # The Status Rules by the status they set, then their order (the first rule a call meets sets its status).
    rules = lambda document: [item for item in dicts(document.get('status_rules')) if str(item.get('status') or '').strip()]  # noqa: E731
    by_status = lambda items: {str(item['status']): [other for other in items if other['status'] == item['status']] for item in items}  # noqa: E731
    was_rules, now_rules = by_status(rules(old)), by_status(rules(new))
    if set(was_rules) != set(now_rules):
        lines.append(list_change('Status Rules', list(was_rules), list(now_rules)))
    changed_rules = [status for status in now_rules if status in was_rules and json.dumps(now_rules[status], sort_keys=True) != json.dumps(was_rules[status], sort_keys=True)]
    if changed_rules:
        lines.append(f"Status Rules changed: {', '.join(changed_rules)}")
    elif set(was_rules) == set(now_rules) and [item['status'] for item in rules(old)] != [item['status'] for item in rules(new)]:
        lines.append('Status Rules: new order')
    roots, new_roots = section(old, 'root_causes'), section(new, 'root_causes')
    entries('Root Domains', 'Root Domain', roots.get('domains'), new_roots.get('domains'), ('color', 'keywords'))
    entries('Root Categories', 'Root Category', roots.get('categories'), new_roots.get('categories'), ('domain', 'color', 'keywords'))
    entries('Root Causes', 'Root Cause', roots.get('causes'), new_roots.get('causes'), ('domain', 'category', 'color', 'keywords'))
    rule = describe_changes(section(roots, 'rule'), section(new_roots, 'rule'))
    if rule:
        lines.append(f"Root Cause Suggestion Rule: {'; '.join(rule)}")
    if bool(roots.get('require_to_close')) != bool(new_roots.get('require_to_close')):
        lines.append(f"Root Cause required to close: {'Yes' if new_roots.get('require_to_close') else 'No'}")
    # The layout of the workspace (the Table column and Excel of the fields are told with the fields) and those of the users.
    labels = {**{f"field:{item.get('key')}": str(item.get('label')) for item in dicts(new.get('fields'))}, **OPTIONAL_COLUMNS}
    field_names = {str(item.get('key')): str(item.get('label')) for item in dicts(new.get('fields'))}

    def layout_changes(was: dict[str, Any], now: dict[str, Any]) -> list[str]:
        named = lambda values, names: [names.get(str(value), str(value)) for value in values or []]  # noqa: E731
        parts = []
        for key, title, names in (('fields', 'Columns', field_names), ('excel_fields', 'Excel', field_names),
                                  ('builtin', 'Additional Columns', OPTIONAL_COLUMNS), ('cdr', 'CDR Columns', {}),
                                  ('export_cdr', 'CDR Columns for Excel only', {})):
            if key in was or key in now:
                if sorted(map(str, was.get(key) or [])) != sorted(map(str, now.get(key) or [])):
                    parts.append(list_change(title, named(was.get(key), names), named(now.get(key), names)))
        if (was.get('order') or []) != (now.get('order') or []):
            parts.append('Column order: default' if not now.get('order') else 'Column order: ' + ', '.join(
                labels.get(str(key), field_label(str(key))) for key in now['order'][:8]) + ('…' if len(now['order']) > 8 else ''))
        return parts

    workspace = layout_changes({**section(old, 'table_columns'), 'order': old.get('column_order') or []},
                               {**section(new, 'table_columns'), 'order': new.get('column_order') or []})
    if workspace:
        lines.append(f"Workspace layout: {'; '.join(workspace)}")
    was_layouts = {str(item.get('username') or '').casefold(): item for item in dicts(old.get('user_layouts')) if item.get('username')}
    now_layouts = {str(item.get('username') or '').casefold(): item for item in dicts(new.get('user_layouts')) if item.get('username')}
    if set(was_layouts) != set(now_layouts):
        lines.append(list_change('Layouts of the users', [str(item['username']) for item in was_layouts.values()],
                                 [str(item['username']) for item in now_layouts.values()]))
    for found, item in now_layouts.items():
        if found not in was_layouts:
            continue
        previous = was_layouts[found]
        parts = layout_changes(previous.get('layout') if isinstance(previous.get('layout'), dict) else {},
                               item.get('layout') if isinstance(item.get('layout'), dict) else {})
        if str(previous.get('view') or '') != str(item.get('view') or ''):
            parts.append(f"Shown: {str(item.get('view') or '').title()}")
        if parts:
            lines.append(f"Layout of {item['username']}: {'; '.join(parts)}")
    # The equivalences of the Previous NQ Analyses, by the field (or follow-up value) they map to.
    was_equivalences, now_equivalences = section(old, 'analyses_equivalences'), section(new, 'analyses_equivalences')
    for target in dict.fromkeys([*now_equivalences, *was_equivalences]):
        previous = was_equivalences.get(target) if isinstance(was_equivalences.get(target), dict) else {}
        current = now_equivalences.get(target) if isinstance(now_equivalences.get(target), dict) else {}
        counts = [(sum(key not in previous for key in current), 'new'),
                  (sum(key in previous and json.dumps(previous[key], sort_keys=True) != json.dumps(value, sort_keys=True)
                       for key, value in current.items()), 'changed'),
                  (sum(key not in current for key in previous), 'removed')]
        parts = [f'{count} {word}' for count, word in counts if count]
        if parts:
            name = field_names.get(target[6:], target[6:]) if str(target).startswith('field:') else field_label(str(target))
            lines.append(f"Equivalences of the Previous NQ Analyses · {name}: {', '.join(parts)}")
    if json.dumps(old.get('prioritization'), sort_keys=True) != json.dumps(new.get('prioritization'), sort_keys=True):
        try:
            prioritization = nq_prioritization.settings_changes(old.get('prioritization'), new.get('prioritization'))
        except (AttributeError, KeyError, TypeError, ValueError):
            prioritization = []
        lines += [f'NQ Prioritization · {line}' for line in prioritization] or ['NQ Prioritization']
    if isinstance(new.get('dta_rca_rules'), list) and json.dumps(old.get('dta_rca_rules'), sort_keys=True) != json.dumps(
            new.get('dta_rca_rules'), sort_keys=True):
        lines += [f'DT Analyzer RCA rules · {line}' for line in nq_dta_rca.rules_changes(
            old.get('dta_rca_rules') if isinstance(old.get('dta_rca_rules'), list) else nq_dta_rca.default_rules(),
            new['dta_rca_rules'])] or ['DT Analyzer RCA rules']
    if isinstance(new.get('dta_rca_settings'), dict) and nq_dta_rca.normalize_settings(old.get('dta_rca_settings')) != nq_dta_rca.normalize_settings(
            new['dta_rca_settings']):
        lines.append('DT Analyzer RCA · Learn from the decisions of the analysts: '
                     + ('Yes' if nq_dta_rca.normalize_settings(new['dta_rca_settings'])['learn'] else 'No'))
    return lines


def _merge_configuration(task_repository: Any, document: dict[str, Any]) -> None:
    """Add the missing statuses, teams, fields, list values and root cause catalog entries of a document and take its
    sections, status rules, field settings (section, order, Table column, Excel and Summary breakdown), table layouts (that
    of the workspace and those of the users, by username), suggestion rule, Require setting, NQ Prioritization settings
    and DT Analyzer RCA rules (their calls take them at the next reading)."""
    options = document.get('options') if isinstance(document.get('options'), dict) else {}
    # Missing fields are added (in their section) and the values of the list fields are merged.
    incoming_fields = [item for item in document.get('fields') or [] if isinstance(item, dict) and item.get('key') and item.get('label')]
    if incoming_fields:
        current_fields = list_fields(task_repository)
        by_key = {field['key']: field for field in current_fields}
        merged = _merged_fields(current_fields, incoming_fields)
        if merged != current_fields:
            _store_fields(task_repository, nq_catalog.normalize_fields(merged, by_key, CATALOG_CALL_FIELDS))
    if isinstance(document.get('sections'), list):
        task_repository.set_workspace_state(SECTIONS_STATE_KEY, json.dumps(nq_catalog.normalize_sections(document['sections'])))
    # The reviewed equivalences of the analyses imports: those of values the workspace has not reviewed itself.
    incoming = _normalize_equivalences(document.get('analyses_equivalences'))
    if incoming:
        equivalences = workspace_equivalences(task_repository)
        for target, values in incoming.items():
            for key, item in values.items():
                equivalences.setdefault(target, {}).setdefault(key, item)
        _save_equivalences(task_repository, equivalences)
    columns = document.get('table_columns')
    if isinstance(columns, dict):
        try:
            # The application takes them (system), not a user: the event says they come from the imported configuration.
            save_table_columns(task_repository, columns.get('builtin') or [], columns.get('cdr') or [], 'system',
                               columns.get('export_cdr') or [], imported=True)
        except ValueError:
            pass
    if isinstance(document.get('column_order'), list):
        task_repository.set_workspace_state(COLUMN_ORDER_STATE_KEY, json.dumps(_column_order(document['column_order']), ensure_ascii=False))
    with task_repository.connection() as connection:
        for kind, key in (('status', 'statuses'), ('team', 'teams')):
            items = options.get(key) if isinstance(options.get(key), list) else []
            position = connection.execute(
                f'SELECT COALESCE(MAX(position), -1) FROM {NQ_CALL_OPTIONS_TABLE} WHERE kind = ?', (kind,)).fetchone()[0]
            for item in _normalize_option_list([item for item in items if isinstance(item, dict) and item.get('name')], kind):
                position += 1
                connection.execute(
                    f'INSERT OR IGNORE INTO {NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES (?, ?, ?, ?, ?)',
                    (kind, item['name'], item['color'], position, int(item['closed'])),
                )
                connection.executemany(
                    f'INSERT OR IGNORE INTO {NQ_TEAM_MEMBERS_TABLE} (team, username) VALUES (?, ?)',
                    [(item['name'], member) for member in item.get('members') or []],
                )
        incoming = _incoming_root_catalog(document)
        if any(incoming.values()):
            current = nq_catalog.stored_root_catalog(_read_root_catalog(connection))
            for plural in ('domains', 'categories', 'causes'):
                names = {item['name'].casefold() for item in current[plural]}
                current[plural] += [item for item in incoming[plural] if str(item['name']).casefold() not in names]
            _write_root_catalog(connection, nq_catalog.normalize_root_catalog(current))
    root_causes = document.get('root_causes') if isinstance(document.get('root_causes'), dict) else {}
    if isinstance(root_causes.get('rule'), dict):
        try:
            task_repository.set_workspace_state(ROOT_CAUSE_RULE_STATE_KEY, json.dumps(normalize_root_cause_rule(root_causes['rule'])))
        except ValueError:
            pass
    if 'require_to_close' in root_causes:
        task_repository.set_workspace_state(ROOT_CAUSE_SETTINGS_STATE_KEY,
                                            json.dumps({'require_to_close': bool(root_causes['require_to_close'])}))
    if isinstance(document.get('prioritization'), dict):
        # The Prioritization settings of the package replace those of the workspace (applied at the next calculation).
        task_repository.set_workspace_state(nq_prioritization.SETTINGS_STATE_KEY, json.dumps(
            nq_prioritization.normalize_settings(document['prioritization'], operators=nq_prioritization.default_step_operators(task_repository),
                                                 modes=nq_prioritization.default_excluded_modes(task_repository)),
            ensure_ascii=False))
    if isinstance(document.get('dta_rca_rules'), list) and document['dta_rca_rules']:
        # The rules of the package replace those of the workspace; the calls are calculated again when they are read.
        task_repository.set_workspace_state(nq_dta_rca.RULES_STATE_KEY, json.dumps(nq_dta_rca.normalize_rules(document['dta_rca_rules']),
                                                                               ensure_ascii=False))
    if isinstance(document.get('dta_rca_settings'), dict):
        task_repository.set_workspace_state(nq_dta_rca.SETTINGS_STATE_KEY, json.dumps(nq_dta_rca.normalize_settings(document['dta_rca_settings'])))
    if isinstance(document.get('status_rules'), list):
        try:
            rules = nq_catalog.normalize_status_rules(document['status_rules'], [item['name'] for item in list_options(task_repository)['statuses']],
                                                      list_fields(task_repository))
            task_repository.set_workspace_state(STATUS_RULES_STATE_KEY, json.dumps(rules, ensure_ascii=False))
        except ValueError:
            pass
    # The layout of each user replaces theirs, also of a user the workspace does not have yet.
    layouts = [item for item in document.get('user_layouts') or []
               if isinstance(item, dict) and str(item.get('username') or '').strip()]
    if layouts:
        fields = list_fields(task_repository)
        for item in layouts:
            layout = _normalize_layout(item['layout'], fields, strict=False) if isinstance(item.get('layout'), dict) else None
            view = str(item.get('view')) if layout is not None and item.get('view') in LAYOUT_VIEWS else 'workspace'
            _store_user_layout(task_repository, str(item['username']).strip()[:120], layout, view)
        _remember_user_cdr_columns(task_repository)
        if hasattr(task_repository, 'try_add_log'):
            task_repository.try_add_log('system', 'nq_table_layout', f'{len(layouts)} personal Non-Qualified Calls table layouts '
                                        f'({", ".join(str(item["username"]).strip() for item in layouts)}) taken from an imported configuration.')


def import_tracking_document(task_repository: Any, payload: bytes | str) -> int:
    """Merge a tracking document; returns the number of calls whose follow-up was added or updated.

    Missing statuses, teams, fields, list values and root cause catalog entries are added, the
    sections and status rules of the document are taken, newer follow-up replaces older follow-up,
    and comments, history entries and RCA results are added once, so importing the same document
    again changes nothing. The calls with a JOIN_ID take the key this version computes from it (``calls``),
    so a document whose keys were computed otherwise still finds them; the others keep their key.
    """
    document = json.loads(payload.decode('utf-8') if isinstance(payload, bytes) else payload)
    if not isinstance(document, dict) or document.get('format') != TRACKING_FORMAT:
        raise ValueError('The file is not a Non-Qualified Calls tracking export.')
    if int(document.get('version') or 0) > TRACKING_FORMAT_VERSION:
        raise ValueError('The Non-Qualified Calls tracking export was created by a newer version.')
    ensure_nq_tables(task_repository)

    def records(name: str) -> list[dict[str, Any]]:
        items = document.get(name) or []
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ValueError(f'The "{name}" section of the tracking export is invalid.')
        return items

    tracking, comments, history = records('tracking'), records('comments'), records('history')
    value_records, rca_records = records('field_values'), records('rca_results')
    rekeyed = _document_call_keys(records('calls'))
    key_of = lambda item: (lambda key: rekeyed.get(key, key))(_text(item.get('call_key')))
    touched: set[str] = set()
    _merge_configuration(task_repository, document)
    with task_repository.connection() as connection:
        for item in tracking:
            call_key = key_of(item)
            if not call_key:
                continue
            existing = connection.execute(
                f'SELECT updated_at FROM {NQ_CALL_TRACKING_TABLE} WHERE call_key = ?', (call_key,)).fetchone()
            incoming_at = _text(item.get('updated_at'))
            if existing is not None and str(existing['updated_at']) >= incoming_at:
                continue
            mode = 'manual' if _text(item.get('status_mode')) == 'manual' or (
                'status_mode' not in item and _text(item.get('status')) not in {'', 'Open'}) else 'auto'
            connection.execute(
                f'INSERT OR REPLACE INTO {NQ_CALL_TRACKING_TABLE} (call_key, status, status_mode, team, assignee, root_domain, '
                'root_category, root_cause, version, updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (call_key, _text(item.get('status')), mode, _text(item.get('team')), _text(item.get('assignee')),
                 _text(item.get('root_domain')), _text(item.get('root_category')), _text(item.get('root_cause')),
                 int(item.get('version') or 1), _text(item.get('updated_by')), incoming_at),
            )
            touched.add(call_key)
        for item in comments:
            uid, call_key, body = _text(item.get('uid')), key_of(item), str(item.get('body') or '')
            if not uid or not call_key or not body:
                continue
            existing = connection.execute(
                f'SELECT edited_at, deleted_at FROM {NQ_CALL_COMMENTS_TABLE} WHERE uid = ?', (uid,)).fetchone()
            values = (body, _text(item.get('edited_by')), _text(item.get('edited_at')),
                      _text(item.get('deleted_by')), _text(item.get('deleted_at')))
            if existing is None:
                connection.execute(
                    f'INSERT INTO {NQ_CALL_COMMENTS_TABLE} (uid, call_key, created_by, created_at, body, edited_by, edited_at, '
                    'deleted_by, deleted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (uid, call_key, _text(item.get('created_by')) or 'import', _text(item.get('created_at')), *values),
                )
                touched.add(call_key)
            elif (values[2], values[4]) > (str(existing['edited_at']), str(existing['deleted_at'])):
                connection.execute(
                    f'UPDATE {NQ_CALL_COMMENTS_TABLE} SET body = ?, edited_by = ?, edited_at = ?, deleted_by = ?, '
                    'deleted_at = ? WHERE uid = ?', (*values, uid),
                )
                touched.add(call_key)
        for item in history:
            uid, call_key = _text(item.get('uid')), key_of(item)
            if not uid or not call_key:
                continue
            connection.execute(
                f'INSERT OR IGNORE INTO {NQ_CALL_HISTORY_TABLE} (uid, call_key, field, old_value, new_value, changed_by, changed_at) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)',
                (uid, call_key, _text(item.get('field')), str(item.get('old_value') or ''), str(item.get('new_value') or ''),
                 _text(item.get('changed_by')) or 'import', _text(item.get('changed_at'))),
            )
        for item in value_records:
            call_key, field_key = key_of(item), _text(item.get('field_key'))
            if not call_key or not field_key:
                continue
            existing = connection.execute(
                f'SELECT updated_at FROM {NQ_FIELD_VALUES_TABLE} WHERE call_key = ? AND field_key = ?', (call_key, field_key),
            ).fetchone()
            incoming_at = _text(item.get('updated_at'))
            if existing is not None and str(existing['updated_at']) >= incoming_at:
                continue
            connection.execute(
                f'INSERT OR REPLACE INTO {NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) '
                'VALUES (?, ?, ?, ?, ?)',
                (call_key, field_key, str(item.get('value') or ''), _text(item.get('updated_by')) or 'import', incoming_at))
            touched.add(call_key)
        for item in rca_records:
            join_id = _text(item.get('join_id'))
            if not join_id:
                continue
            existing = connection.execute(
                f'SELECT imported_at FROM {NQ_RCA_RESULTS_TABLE} WHERE join_id = ?', (join_id.casefold(),)).fetchone()
            incoming_at = _text(item.get('imported_at'))
            if existing is not None and str(existing['imported_at']) >= incoming_at:
                continue
            values = item.get('values_json')
            connection.execute(
                f'INSERT OR REPLACE INTO {NQ_RCA_RESULTS_TABLE} (join_id, original_join_id, values_json, source_file, imported_by, '
                'imported_at) VALUES (?, ?, ?, ?, ?, ?)',
                (join_id.casefold(), join_id, values if isinstance(values, str) else json.dumps(values or {}, ensure_ascii=False),
                 _text(item.get('source_file')), _text(item.get('imported_by')) or 'import', incoming_at))
    if touched:
        recompute_statuses(task_repository, 'import', list(touched))
    return len(touched)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def install_non_qualified_calls_routes(core: Any) -> None:
    from fastapi import Depends, HTTPException, Request

    def index_when_idle() -> None:
        """Index the new, changed or removed CDRs of the active workspace once nobody has used the server for a while,
        if the module has been opened there."""
        workspace = core.active_workspace
        if not workspace:
            return
        repository = core.Repository(workspace.database_path, global_db_path=core.repository.global_db_path,
                                     workspace_registry_db_path=core.workspace_registry.registry_path)
        with repository.connection() as connection:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                                      (NQ_CALL_SOURCES_TABLE,)).fetchone():
                return
        status = nq_index_status(repository)
        if status['pending'] and not status['indexing']:
            start_nq_index(repository, core.submit_background_task)

    def index_tasks(workspace: Any) -> list[dict[str, Any]]:
        job = nq_index_job(workspace.database_path)
        if not job or (job['status'] in {'ready', 'failed'} and time.time() - (job['finished_at'] or 0) > 5):
            return []
        detail = 'Indexing the calls of every CDR again' if job['force'] else 'Indexing the calls of new or changed CDRs'
        return [{
            'id': f'nq-index:{workspace.id}', 'label': 'Non-Qualified Calls indexing',
            'detail': job['error'] or detail, 'status': job['status'], 'progress': None,
            'queued_at': job['queued_at'], 'started_at': job['started_at'], 'completed_at': job['finished_at'],
        }]

    def prioritize_when_idle() -> None:
        """Calculate the NQ Prioritization of the active workspace once the server is idle, after the indexing of the
        calls and the Scoring History, when what it depends on changed."""
        workspace = core.active_workspace
        if not workspace:
            return
        repository = core.Repository(workspace.database_path, global_db_path=core.repository.global_db_path,
                                     workspace_registry_db_path=core.workspace_registry.registry_path)
        with repository.connection() as connection:
            if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                                      (nq_prioritization.PRIORITY_TABLE,)).fetchone():
                return
        from src.modules.scoring_history import history_job
        running = [nq_index_job(repository.db_path), history_job(repository.db_path), nq_prioritization.job(repository.db_path)]
        if any(item and item['status'] in {'queued', 'processing'} for item in running) or nq_index_status(repository)['pending']:
            return
        if nq_prioritization.needs_calculation(repository):
            nq_prioritization.start(repository, core.submit_background_task)

    def prioritization_tasks(workspace: Any) -> list[dict[str, Any]]:
        job = nq_prioritization.job(workspace.database_path)
        if not job or (job['status'] in {'ready', 'failed'} and time.time() - (job['finished_at'] or 0) > 5):
            return []
        detail = job['error'] or (f"Calculating {job['current']} ({job['done'] + 1} of {job['total']})" if job['current']
                                  else 'Calculating the scoring impact, repetitions and priorities of the calls')
        return [{
            'id': f'nq-prioritization:{workspace.id}', 'label': 'NQ Prioritization', 'detail': detail, 'status': job['status'],
            'progress': round(job['done'] / job['total'] * 100) if job['total'] else None,
            'queued_at': job['queued_at'], 'started_at': job['started_at'], 'completed_at': job['finished_at'],
        }]

    core.register_idle_task(index_when_idle, NQ_INDEX_IDLE_SECONDS)
    core.register_idle_task(prioritize_when_idle, NQ_PRIORITIZATION_IDLE_SECONDS)
    core.BACKGROUND_TASK_PROVIDERS.append(index_tasks)
    core.BACKGROUND_TASK_PROVIDERS.append(prioritization_tasks)
    from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
    from pydantic import BaseModel, Field

    class QueryPayload(BaseModel):
        filters: dict[str, Any] = Field(default_factory=dict)
        sort: str = 'start_time'
        direction: str = 'desc'
        page: int = 1
        page_size: int = DEFAULT_PAGE_SIZE
        breakdowns: bool = True

    class TrackingPayload(BaseModel):
        changes: dict[str, Any] = Field(default_factory=dict)
        version: int | None = None

    class BulkTrackingPayload(BaseModel):
        call_keys: list[str] = Field(default_factory=list)
        changes: dict[str, Any] = Field(default_factory=dict)

    class CommentPayload(BaseModel):
        body: str = ''

    class HistoryPayload(BaseModel):
        call_keys: list[str] = Field(default_factory=list)

    class OptionsPayload(BaseModel):
        statuses: list[dict[str, Any]] = Field(default_factory=list)
        teams: list[dict[str, Any]] = Field(default_factory=list)

    class RootCausesPayload(BaseModel):
        domains: list[dict[str, Any]] = Field(default_factory=list)
        categories: list[dict[str, Any]] = Field(default_factory=list)
        causes: list[dict[str, Any]] = Field(default_factory=list)
        require_to_close: bool = False
        # Saved after Default Catalog: App Events says so.
        defaults: bool = False

    class ApplyCategoriesPayload(BaseModel):
        preview: bool = False

    class AnalystAssignmentsPayload(BaseModel):
        assignments: dict[str, str] = Field(default_factory=dict)
        overwrite: bool = False
        preview: bool = False

    class SectionsPayload(BaseModel):
        sections: list[dict[str, Any]] = Field(default_factory=list)
        # Saved after Default Fields & Sections: App Events says so.
        defaults: bool = False

    class StatusRulesPayload(BaseModel):
        rules: list[dict[str, Any]] = Field(default_factory=list)

    class PrioritizationPayload(BaseModel):
        settings: dict[str, Any] = Field(default_factory=dict)
        # Saved after Default Rules: App Events says so.
        defaults: bool = False

    class StrategyPayload(BaseModel):
        strategy: str = ''

    class RootCauseRulePayload(BaseModel):
        rule: dict[str, Any] | None = None

    class DtaRulesPayload(BaseModel):
        rules: list[dict[str, Any]] = Field(default_factory=list)
        # Saved after Default Rules: App Events says so.
        defaults: bool = False
        # Whether it learns from the decisions of the analysts (unchanged when not sent).
        learn: bool | None = None

    class RootCauseStatsPayload(BaseModel):
        filters: dict[str, Any] = Field(default_factory=dict)
        include_suggestions: bool = True
        source: str = 'analysts'

    class ProgressPayload(BaseModel):
        filters: dict[str, Any] = Field(default_factory=dict)
        granularity: str = 'week'
        include_suggestions: bool = True
        # The PowerPoint and Word follow these checkboxes of the page (both unchecked by default).
        show_not_classified: bool = False
        show_empty: bool = False

    class ExportPayload(BaseModel):
        filters: dict[str, Any] = Field(default_factory=dict)

    class FieldsPayload(BaseModel):
        fields: list[dict[str, Any]] = Field(default_factory=list)
        # Saved after Default Fields & Sections: App Events says so.
        defaults: bool = False

    class FieldOptionPayload(BaseModel):
        name: str = ''

    class TableColumnsPayload(BaseModel):
        builtin: list[str] = Field(default_factory=list)
        cdr: list[str] = Field(default_factory=list)
        export_cdr: list[str] = Field(default_factory=list)
        # Saved after Default Columns: App Events says so.
        defaults: bool = False

    class TableLayoutPayload(BaseModel):
        # The parts left out keep those of the layout of the user (or of the workspace, while they have none).
        builtin: list[str] | None = None
        cdr: list[str] | None = None
        export_cdr: list[str] | None = None
        fields: list[str] | None = None
        excel_fields: list[str] | None = None
        known_fields: list[str] | None = None
        order: list[str] | None = None
        # changed, defaults (Default Columns), order, default_order (Default column order): App Events says which.
        reason: str = 'changed'

    class LayoutViewPayload(BaseModel):
        view: str = 'mine'

    def workspace_repository(user):
        if not core.active_workspace:
            raise HTTPException(409, 'Open a workspace before using Non-Qualified Calls.')
        core.require_workspace_access(user, core.active_workspace.id)
        repository = core.Repository(core.active_workspace.database_path, global_db_path=core.repository.global_db_path,
                                     workspace_registry_db_path=core.workspace_registry.registry_path)
        ensure_nq_tables(repository)
        return repository

    def can_edit(user) -> bool:
        return user.role in core.WORKSPACE_EDITOR_ROLES

    def can_moderate(user) -> bool:
        return user.role in {'admin', 'super-admin'}

    def can_configure_rule(user) -> bool:
        """Everybody sees the suggestion rule; admins and super-admins change it."""
        return user.role in {'admin', 'super-admin'}

    def rule_user(user=Depends(core.current_user)):
        if not can_configure_rule(user):
            raise HTTPException(403, 'Only admins and super-admins can change the root cause suggestion rule.')
        return user

    def moderator_user(user=Depends(core.current_user)):
        if not can_moderate(user):
            raise HTTPException(403, 'Only admins and super-admins can delete the history of Non-Qualified Calls.')
        return user

    def editor_user(user=Depends(core.current_user)):
        if not can_edit(user):
            raise HTTPException(403, 'The user-viewer role can read Non-Qualified Calls but cannot change them.')
        return user

    def can_configure(user) -> bool:
        """The NQ Analysis Configuration and the table layout of the workspace: admins and super-admins."""
        return user.role in {'admin', 'super-admin'}

    def config_user(user=Depends(core.current_user)):
        if not can_configure(user):
            raise HTTPException(403, 'Only admins and super-admins can change the NQ Analysis Configuration.')
        return user

    def can_prioritize(user) -> bool:
        """The Prioritization Rules: admins and super-admins, and for now the accounts of PRIORITIZATION_EDITORS."""
        return can_configure(user) or str(user.username).casefold() in {name.casefold() for name in PRIORITIZATION_EDITORS}

    def prioritization_user(user=Depends(core.current_user)):
        if not can_prioritize(user):
            raise HTTPException(403, 'Only admins and super-admins can change the Prioritization Rules.')
        return user

    def workspace_users() -> list[str]:
        """Active accounts that can open the active workspace: the assignable users."""
        names = []
        for row in core.repository.list_users():
            if not row['active']:
                continue
            username = str(row['username'])
            if row['role'] == 'super-admin' or core.repository.user_has_workspace_access(username, core.active_workspace.id):
                names.append(username)
        return sorted(names, key=str.casefold)

    def user_names() -> dict[str, str]:
        """The first and last name of every account that has them, by username: how the page shows the users."""
        names = {}
        for row in core.repository.list_users():
            name = ' '.join(str(row[key] or '').strip() for key in ('first_name', 'last_name') if key in row.keys()).strip()
            if name:
                names[str(row['username'])] = name
        return names

    def translate(action):
        try:
            return action()
        except TrackingConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc).strip("'\"")) from exc
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    # -- Reporting Jobs artifact ---------------------------------------------
    # NR Mode first and Campaign after it, listing only the campaigns of the NR Modes chosen (campaign@nr_mode).
    report_filters = (
        ('nr_mode', 'NR Mode'), ('campaign', 'Campaign'), ('service', 'Service'), ('operator', 'Operator'),
        ('operator_vendor', 'Operator_Vendor'), ('vendor_operator', 'Vendor_Operator'), ('vendor', 'Vendor'),
        ('region', 'Region'), ('cluster', 'Cluster'), ('city', 'City'), ('result', 'Result'), ('failure_classification', 'Failure Classification'),
        ('status', 'Status'), ('status_mode', 'Status Set'), ('team', 'Team'), ('assignee', 'Assignee'), ('root_domain', 'Root Domain'),
        ('root_category', 'Root Category'), ('root_cause', 'Root Cause'), ('version', 'CDR Version'),
    )
    report_settings = (
        {'key': 'granularity', 'label': 'Progress periods', 'default': 'week',
         'choices': [['week', 'Week'], ['month', 'Month'], ['quarter', 'Quarter'], ['year', 'Year']]},
        {'key': 'open_only', 'label': 'Calls', 'default': '',
         'choices': [['', 'Every call'], ['1', 'Open calls only']]},
        {'key': 'include_suggestions', 'label': 'Root Cause Analysis', 'default': '1',
         'choices': [['1', 'Count suggested root causes'], ['', 'Labelled root causes only']]},
    )

    def report_values(user) -> dict[str, list[Any]]:
        repository = workspace_repository(user)
        values = filter_options(repository)
        options = list_options(repository)
        values['datasets'] = [[str(item['id']), item['name']] for item in indexed_datasets(repository)]
        values['status'] = [item['name'] for item in options['statuses']]
        values['team'] = [[UNASSIGNED, 'Unassigned'], *[item['name'] for item in options['teams']]]
        values['assignee'] = [[UNASSIGNED, 'Unassigned'], *workspace_users()]
        taxonomy = list_root_causes(repository)
        values['root_domain'] = [[UNASSIGNED, NOT_CLASSIFIED], *[domain['name'] for domain in taxonomy['domains']]]
        values['root_category'] = [[UNASSIGNED, NOT_CLASSIFIED], *[item['name'] for item in taxonomy['categories']]]
        values['root_cause'] = [[UNASSIGNED, 'No cause'], *[item['name'] for item in taxonomy['causes']]]
        values['status_mode'] = [['auto', 'Automatic'], ['manual', 'By hand']]
        values['version'] = [[key, label] for key, label in VERSION_LABELS.items()]
        # The campaigns of each NR Mode: the Campaign filter lists those of the NR Modes chosen.
        with repository.connection() as connection:
            pairs = connection.execute(
                f"SELECT DISTINCT nr_mode, campaign FROM {NQ_CALLS_TABLE} WHERE campaign <> ''").fetchall()
        by_mode: dict[str, set[str]] = {}
        for nr_mode, campaign in pairs:
            by_mode.setdefault(str(nr_mode or ''), set()).add(str(campaign))
        values['campaign@nr_mode'] = {mode: sorted(campaigns, key=campaign_sort_key) for mode, campaigns in by_mode.items()}
        return values

    def summary_parts(repository, filters: dict[str, Any], username: str, granularity: str, include_suggestions: bool = True):
        """The executive summary, progress status, options and selection lines of one NQ selection.

        The options carry the Root Cause Analysis of the selection under ``root_causes``, one per source:
        DT Analyzer RCA, NetCheck RCA, Ericsson RCA and the analysts (with the suggested root causes when
        ``include_suggestions``).
        """
        from src.modules.non_qualified_calls_export import selection_lines

        executive = query_calls(repository, {'filters': filters, 'page_size': 25}, username)
        progress = progress_stats(repository, filters, username, granularity)
        options = {**list_options(repository),
                   'root_causes': [root_cause_stats(repository, filters, username, include_suggestions, source)
                                   for source in ('dta', 'netcheck', 'script', 'analysts')],
                   'rates': nq_rates(repository, filters),
                   'failures': failure_breakdowns(repository, filters, username),
                   'prioritization': nq_prioritization.panel(repository, filters, username),
                   'lifecycle': lifecycle_stats(repository, filters, username),
                   'rca_insights': rca_insights(repository, filters, username),
                   'sections': list_sections(repository)}
        names = {str(item['id']): item['name'] for item in indexed_datasets(repository)}
        labels = {field['key']: field['label'] for field in list_fields(repository)}
        return executive, progress, options, selection_lines(filters, names, granularity, labels)

    def write_summary_document(export_format: str, destination: Path, executive, progress, options, lines,
                               components: list[str] | None = None, compose: bool = True) -> None:
        """The summary in PowerPoint or Word, composed as the Non-Qualified Calls section of a Bundle Report Template; without
        ``compose`` (the Bundle Report Template itself), the PowerPoint is the deck of the module."""
        from src.modules.bundle_report_templates import module_document
        from src.modules.non_qualified_calls_export import export_powerpoint

        if not compose:
            export_powerpoint(destination, lines, executive['summary'], executive['breakdowns'], progress, options,
                              components=components)
            return
        # The deck of the module has its own name, so it never replaces a document written next to it.
        deck = destination.with_name(f'.{destination.stem}.{uuid.uuid4().hex}.pptx')
        try:
            export_powerpoint(deck, lines, executive['summary'], executive['breakdowns'], progress, options,
                              components=components)
            destination.write_bytes(module_document('non_qualified_calls', deck.read_bytes(), export_format, 'Non-Qualified Calls'))
        finally:
            deck.unlink(missing_ok=True)

    def resolve_report_campaigns(repository, filters: dict[str, list[str]]) -> dict[str, list[str]]:
        """The filters of a Reporting Job with an automatic Campaign choice (Latest campaign, Previous campaign, Latest 2
        campaigns or All available campaigns) as the campaigns of its NR Modes it stands for at this run."""
        from src.modules.cdr_auto_selection import NO_PREVIOUS_CAMPAIGN, campaign_groups, campaign_presets, preset_campaign_groups

        presets = campaign_presets(filters.get('campaign'))
        if not presets:
            return filters
        modes = {str(value).casefold() for value in filters.get('nr_mode') or []}
        with repository.connection() as connection:
            pairs = connection.execute(f"SELECT DISTINCT nr_mode, campaign FROM {NQ_CALLS_TABLE} WHERE campaign <> ''").fetchall()
        campaigns = [str(campaign) for nr_mode, campaign in pairs if not modes or str(nr_mode or '').casefold() in modes]
        chosen = [value for group in preset_campaign_groups(campaign_groups(campaigns), presets[:1]) for value in group]
        # A choice that stands for no campaign (Previous campaign with only one) chooses no call, not every one.
        return {**filters, 'campaign': chosen or [NO_PREVIOUS_CAMPAIGN]}

    def generate_report(config, folder, stamp, user) -> list[dict[str, Any]]:
        from src.modules.report_tasks import artifact_path

        repository = workspace_repository(user)
        sync_nq_calls(repository)
        settings = config.get('options') if isinstance(config.get('options'), dict) else {}
        filters = {key: [str(value) for value in values] for key, values in (settings.get('filters') or {}).items()
                   if isinstance(values, list) and values}
        filters = resolve_report_campaigns(repository, filters)
        if str(settings.get('open_only') or '') == '1':
            filters['open_only'] = True
        granularity = str(settings.get('granularity') or 'week')
        include_suggestions = str(settings.get('include_suggestions', '1') or '') == '1'
        executive, progress, options, lines = summary_parts(repository, filters, user.username, granularity,
                                                            include_suggestions)
        # A Bundle Report Template chooses the charts and tables (``components``) and whether the Root Cause Analysis shows
        # the Not classified calls and the Lifecycle the calls without a value.
        options = {**options, 'show_not_classified': str(settings.get('show_not_classified') or '') == '1',
                   'show_empty': str(settings.get('show_empty') or '') == '1'}
        components = [str(value) for value in settings['components']] if isinstance(settings.get('components'), list) else None
        # A Bundle Report Template composes the deck of the module itself.
        compose = settings.get('compose', True) is not False
        summary = executive['summary']
        details = [*lines[:-1], f"{summary['total']:,} Non-Qualified Calls · {summary['open']:,} open · {summary['closed']:,} closed · "
                   f"{progress['summary']['attended']:,} attended"]
        artifacts = []
        for export_format in config.get('formats') or ['powerpoint']:
            suffix = {'powerpoint': '.pptx', 'word': '.docx', 'excel': '.xlsx'}[export_format]
            label = {'powerpoint': 'PPT', 'word': 'Word', 'excel': 'Excel'}[export_format]
            destination = artifact_path(folder, stamp, 'Non-Qualified Calls', 'Executive Summary and Progress Status', suffix)
            if export_format in {'powerpoint', 'word'}:
                write_summary_document(export_format, destination, executive, progress, options, lines, components, compose)
            else:
                destination.write_bytes(export_workbook(repository, filters, user.username, workspace_layout_only=True))
            artifacts.append({'module': 'non_qualified_calls', 'title': f'Non-Qualified Calls ({label})',
                              'file_name': destination.name, 'size': destination.stat().st_size,
                              'status': 'ready', 'details': details})
        return artifacts

    from src.modules.report_tasks import register_report_artifact_provider

    register_report_artifact_provider(
        'non_qualified_calls', 'Non-Qualified Calls', 'non-qualified-calls', generate_report,
        formats=('powerpoint', 'word', 'excel'), filters=report_filters, settings=report_settings, values=report_values,
    )

    def log_action(repository: Any, user: Any, action: str, details: dict[str, Any]) -> None:
        """Write a user action of the module to the App Events of the workspace."""
        if hasattr(repository, 'try_add_log'):
            repository.try_add_log(user.username, action, json.dumps(details, ensure_ascii=False))

    @core.app.get('/non-qualified-calls', response_class=HTMLResponse)
    def non_qualified_calls_page(request: Request, user=Depends(core.current_user)):
        return core.render_template(request, 'non_qualified_calls.html', {
            'user': user, 'nq_can_edit': can_edit(user), 'nq_can_configure': can_configure(user), 'nq_can_prioritize': can_prioritize(user),
            'nq_can_import_analyses': can_moderate(user), 'nq_page_sizes': PAGE_SIZES, 'nq_default_page_size': DEFAULT_PAGE_SIZE,
            'nq_provider': provider_texts(core.repository) if core.active_workspace else {},
        })

    @core.app.get('/api/non-qualified-calls/state')
    def nq_state(user=Depends(core.current_user)) -> JSONResponse:
        repository = workspace_repository(user)
        sync = nq_index_status(repository)
        if sync['pending'] and not sync['synced_at'] and not sync['indexing']:
            # Nothing indexed yet (the first time the module opens): it is indexed at once, in the background.
            start_nq_index(repository, core.submit_background_task)
            sync = nq_index_status(repository)
        layouts = table_layouts(repository, user.username)
        # The operators the steps of the strategies take by default: the Focus operators by name (the SA steps those with SA).
        step_operators = nq_prioritization.default_step_operators(repository)
        prioritization = nq_prioritization.load_settings(repository)
        return JSONResponse({
            'sync': sync, 'options': list_options(repository), 'filter_options': filter_options(repository, layouts['effective']),
            'datasets': indexed_datasets(repository), 'users': workspace_users(), 'user_names': user_names(),
            'default_users': list(DEFAULT_USERS),
            'user': {'username': user.username, 'can_edit': can_edit(user), 'can_moderate': can_moderate(user),
                     'can_configure_rule': can_configure_rule(user), 'can_configure': can_configure(user)},
            'unassigned': UNASSIGNED, 'page_sizes': list(PAGE_SIZES),
            'main_cities': list(repository.list_main_cities()),
            # The page chooses the saved values in its lists, which hold them as they are shown.
            'saved_filters': _mapped_filters(repository, saved_filters(repository)),
            'root_causes': root_catalog_payload(repository), 'root_cause_defaults': nq_catalog.default_root_catalog(),
            'root_cause_rule_fields': RULE_FIELDS, 'default_root_cause_rule': DEFAULT_ROOT_CAUSE_RULE,
            'fields': provider_field_labels(list_fields(repository), repository),
            'default_fields': provider_field_labels(nq_catalog.default_fields(), repository), 'field_types': FIELD_TYPES,
            'field_sources': nq_catalog.FIELD_SOURCES,
            'tracking_refs': nq_catalog.TRACKING_REFS, 'rca_refs': nq_catalog.RCA_REFS, 'call_fields': list(CATALOG_CALL_FIELDS),
            'sections': list_sections(repository), 'default_sections': nq_catalog.default_sections(), 'call_section': CALL_SECTION,
            'value_filter_fields': list(VALUE_FILTER_FIELDS),
            'status_rules': status_rules(repository), 'default_status_rules': nq_catalog.default_status_rules(),
            'default_options': {'statuses': [{'name': name, 'color': color, 'closed': closed} for name, color, closed in DEFAULT_STATUSES],
                                'teams': [{'name': name, 'color': color, 'members': []} for name, color in DEFAULT_TEAMS]},
            'rule_operators': nq_catalog.RULE_OPERATORS, 'condition_fields': nq_catalog.condition_fields(list_fields(repository)),
            'rca_results': rca_results_summary(repository), 'rca_sources': source_labels(repository),
            'dta_refs': nq_catalog.DTA_REFS,
            'dta_rca': {'inputs': nq_dta_rca.inputs_catalog(), 'operators': nq_dta_rca.OPERATORS,
                        'kind_operators': nq_dta_rca.KIND_OPERATORS, 'services': nq_dta_rca.SERVICES,
                        'matches': nq_dta_rca.MATCHES, 'max_rules': nq_dta_rca.MAX_RULES,
                        'max_conditions': nq_dta_rca.MAX_CONDITIONS},
            'table_columns': table_columns(repository), 'table_layout': layouts, 'optional_columns': OPTIONAL_COLUMNS,
            'cdr_columns': available_cdr_columns(repository), 'max_cdr_columns': MAX_CDR_COLUMNS,
            'version_labels': VERSION_LABELS,
            'priority_refs': nq_catalog.PRIORITY_REFS, 'priority_types': nq_catalog.PRIORITY_TYPES,
            'prioritization': prioritization,
            'default_prioritization': nq_prioritization.default_settings(step_operators, nq_prioritization.default_excluded_modes(repository)),
            'prioritization_strategies': nq_prioritization.STRATEGIES, 'prioritization_step_operators': step_operators,
            'focus_operators': labels_with_role(repository, FOCUS),
            'prioritization_operators': nq_prioritization.operator_choices(repository),
            'prioritization_regions': nq_prioritization.region_choices(repository),
            # The NR Mode · operator pairs always out of scope (the operators that are not Focus operators), and why.
            'prioritization_fixed_modes': nq_prioritization.fixed_excluded_modes(repository),
            'prioritization_fixed_reason': nq_prioritization.NOT_FOCUS_REASON,
            'prioritization_fields': {'nr_modes': nq_prioritization.STEP_NR_MODES, 'call_types': nq_prioritization.CALL_TYPES,
                                      'areas': nq_prioritization.STEP_AREAS,
                                      'conditions': {nq_prioritization.CAMPAIGN_LIST: nq_prioritization.CAMPAIGN_CONDITIONS,
                                                     nq_prioritization.FINAL_LIST: nq_prioritization.FINAL_CONDITIONS},
                                      'queues': nq_prioritization.STEP_QUEUES, 'condition_help': nq_prioritization.CONDITION_HELP,
                                      'condition_kinds': nq_prioritization.CONDITION_KINDS},
            'prioritization_steps': {key: nq_prioritization.strategy_steps(key, None, step_operators) for key in nq_prioritization.STRATEGIES},
            'priority_options': nq_prioritization.priority_options(repository),
        })

    @core.app.post('/api/non-qualified-calls/reindex')
    def nq_reindex(user=Depends(core.current_user)) -> JSONResponse:
        """Index the calls of every CDR again in the background, keeping their follow-up."""
        repository = workspace_repository(user)
        start_nq_index(repository, core.submit_background_task, force=True)
        if hasattr(repository, 'try_add_log'):
            repository.try_add_log(user.username, 'nq_calls_reindex_queued', '{}')
        return JSONResponse({'sync': nq_index_status(repository)})

    @core.app.get('/api/non-qualified-calls/index-status')
    def nq_index_status_route(user=Depends(core.current_user)) -> JSONResponse:
        """Whether the indexing still runs, for the page to reload its calls once it ends."""
        return JSONResponse({'sync': nq_index_status(workspace_repository(user))})

    @core.app.put('/api/non-qualified-calls/fields')
    def nq_save_fields(payload: FieldsPayload, user=Depends(config_user)) -> JSONResponse:
        """The analysis fields of the workspace (user-editor and above)."""
        repository = workspace_repository(user)
        return JSONResponse({'fields': translate(lambda: save_fields(repository, payload.fields, user.username,
                                                                     defaults=payload.defaults))})

    @core.app.post('/api/non-qualified-calls/fields/{key}/options')
    def nq_add_field_option(key: str, payload: FieldOptionPayload, user=Depends(editor_user)) -> JSONResponse:
        """A new value of a list field, typed in the list of a call (user-editor and above)."""
        repository = workspace_repository(user)
        return JSONResponse(translate(lambda: add_field_option(repository, key, payload.name, user.username)))

    async def uploaded_file(request: Request, name: str, limit_mb: int) -> tuple[bytes, str, dict[str, Any]]:
        form = await request.form()
        upload = form.get(name)
        if upload is None or not hasattr(upload, 'read'):
            raise HTTPException(400, 'Choose a file.')
        content = await upload.read()
        if len(content) > limit_mb * 1024 * 1024:
            raise HTTPException(400, f'The file is larger than {limit_mb} MB.')
        return content, str(getattr(upload, 'filename', '') or 'upload'), {key: form.get(key) for key in form.keys()}

    @core.app.put('/api/non-qualified-calls/sections')
    def nq_save_sections(payload: SectionsPayload, user=Depends(config_user)) -> JSONResponse:
        """The names and colours of the six sections (user-editor and above)."""
        repository = workspace_repository(user)
        return JSONResponse({'sections': save_sections(repository, payload.sections, user.username, defaults=payload.defaults)})

    @core.app.post('/api/non-qualified-calls/prioritization')
    def nq_prioritization_panel(payload: ExportPayload, user=Depends(core.current_user)) -> JSONResponse:
        """The NQ Prioritization of the filtered calls; the first time (and after an update of its calculation), it is
        calculated at once in the background."""
        repository = workspace_repository(user)
        current = nq_prioritization.job(repository.db_path)
        if (nq_prioritization.outdated(repository) and not nq_index_status(repository)['indexing']
                and not (current and current['status'] in {'queued', 'processing'}) and nq_prioritization.needs_calculation(repository)):
            nq_prioritization.start(repository, core.submit_background_task)
        return JSONResponse(nq_prioritization.panel(repository, payload.filters, user.username))

    @core.app.post('/api/non-qualified-calls/prioritization/recalculate')
    def nq_prioritization_recalculate(user=Depends(editor_user)) -> JSONResponse:
        """Calculate the scoring impact, repetitions and priorities of every call again, in the background."""
        repository = workspace_repository(user)
        job = nq_prioritization.start(repository, core.submit_background_task)
        log_action(repository, user, 'nq_prioritization_recalculate', {})
        return JSONResponse({'job': {key: job[key] for key in ('status', 'error')}, 'status': nq_prioritization.status(repository)})

    @core.app.get('/api/non-qualified-calls/prioritization/settings')
    def nq_prioritization_settings(user=Depends(core.current_user)) -> JSONResponse:
        repository = workspace_repository(user)
        return JSONResponse({'settings': nq_prioritization.load_settings(repository),
                             'defaults': nq_prioritization.default_settings(nq_prioritization.default_step_operators(repository),
                                                                            nq_prioritization.default_excluded_modes(repository)),
                             'strategies': nq_prioritization.strategy_labels(nq_prioritization.load_settings(repository)),
                             'priority_options': nq_prioritization.priority_options(repository)})

    @core.app.put('/api/non-qualified-calls/prioritization/settings')
    def nq_save_prioritization_settings(payload: PrioritizationPayload, user=Depends(prioritization_user)) -> JSONResponse:
        """The Prioritization Rules and the levels of the impact and the repetitions: the rules apply at once; a change of
        the levels is calculated again in the background."""
        repository = workspace_repository(user)
        before = nq_prioritization.fingerprint(repository)
        settings = translate(lambda: nq_prioritization.save_settings(repository, payload.settings, user.username))
        if payload.defaults:
            log_action(repository, user, 'nq_prioritization_defaults', {'strategy': nq_prioritization.strategy_labels(settings)[settings['strategy']]})
        if nq_prioritization.fingerprint(repository) != before:
            nq_prioritization.start(repository, core.submit_background_task)
        return JSONResponse({'settings': settings, 'status': nq_prioritization.status(repository)})

    @core.app.put('/api/non-qualified-calls/prioritization/strategy')
    def nq_save_prioritization_strategy(payload: StrategyPayload, user=Depends(prioritization_user)) -> JSONResponse:
        """The strategy the module uses, chosen in the NQ Prioritization & Queues panel (as in the Prioritization Rules): the
        other settings stay as saved, and every call takes its step, queue and Priority at once."""
        repository = workspace_repository(user)
        settings = nq_prioritization.load_settings(repository)
        if payload.strategy not in nq_prioritization.strategy_labels(settings):
            raise HTTPException(400, 'Choose the strategy of the NQ Prioritization.')
        settings = translate(lambda: nq_prioritization.save_settings(repository, {**settings, 'strategy': payload.strategy}, user.username))
        return JSONResponse({'settings': settings, 'status': nq_prioritization.status(repository)})

    @core.app.post('/api/non-qualified-calls/prioritization/step-counts')
    def nq_prioritization_step_counts(payload: PrioritizationPayload, user=Depends(core.current_user)) -> JSONResponse:
        """How many calls each step of the strategy of the settings being edited takes in the latest campaigns with their
        Final CDR (the #Calls of the Prioritization Rules)."""
        repository = workspace_repository(user)
        settings = nq_prioritization.normalize_settings(payload.settings, operators=nq_prioritization.default_step_operators(repository))
        return JSONResponse(nq_prioritization.step_counts(repository, settings))

    @core.app.put('/api/non-qualified-calls/status-rules')
    def nq_save_status_rules(payload: StatusRulesPayload, user=Depends(config_user)) -> JSONResponse:
        """The rules that set the automatic NQ Call Status; the calls follow them at once."""
        repository = workspace_repository(user)
        rules = translate(lambda: save_status_rules(repository, payload.rules, user.username))
        return JSONResponse({'status_rules': rules})

    @core.app.get('/api/non-qualified-calls/catalog/export')
    def nq_catalog_export(user=Depends(core.current_user)) -> Response:
        """The catalog (sections, fields, lists, root cause catalog, statuses, teams and status rules) as Excel."""
        repository = workspace_repository(user)
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', f'{core.active_workspace.name}_NQ_Analysis_Center_catalog.xlsx')
        log_action(repository, user, 'nq_catalog_export', {'file': name})
        return Response(catalog_document(repository),
                        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': f'attachment; filename="{name}"'})

    @core.app.post('/api/non-qualified-calls/catalog/import')
    async def nq_catalog_import(request: Request, user=Depends(config_user)) -> JSONResponse:
        """Preview (``preview=1``) or import a catalog workbook: its format, or the layout of the meeting workbook."""
        repository = workspace_repository(user)
        content, name, form = await uploaded_file(request, 'workbook', 10)
        try:
            if str(form.get('preview') or '') == '1':
                return JSONResponse(preview_catalog(repository, content))
            imported = import_catalog(repository, content, user.username, set(workspace_users()))
            log_action(repository, user, 'nq_catalog_import', {'file': name})
            return JSONResponse(imported)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 - an unreadable file is a user error.
            raise HTTPException(400, f'The workbook could not be read: {exc}') from exc

    @core.app.get('/api/non-qualified-calls/rca')
    def nq_rca_summary(user=Depends(core.current_user)) -> JSONResponse:
        return JSONResponse(rca_results_summary(workspace_repository(user)))

    @core.app.get('/api/non-qualified-calls/rca/template')
    def nq_rca_template(user=Depends(core.current_user)) -> Response:
        workspace_repository(user)
        return Response(nq_rca.rca_template(), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="NQ_RCA_results_template.csv"'})

    @core.app.post('/api/non-qualified-calls/rca/import')
    async def nq_rca_import(request: Request, user=Depends(config_user)) -> JSONResponse:
        """Preview (``preview=1``) or import Ericsson RCA results by JOIN_ID; ``replace=1`` forgets the previous results and
        ``add_to_catalog=1`` adds the script categories and causes missing from the Root Cause Catalog."""
        repository = workspace_repository(user)
        content, name, form = await uploaded_file(request, 'file', 100)
        try:
            return JSONResponse(import_rca_results(repository, content, name, user.username,
                                                   replace=str(form.get('replace') or '') == '1',
                                                   dry_run=str(form.get('preview') or '') == '1',
                                                   add_to_catalog=str(form.get('add_to_catalog') or '') == '1'))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - an unreadable file is a user error.
            raise HTTPException(400, f'The RCA file could not be read: {exc}') from exc

    def analyses_user(user=Depends(core.current_user)):
        if not can_moderate(user):
            raise HTTPException(403, 'Only admins and super-admins can import the analyses of the previous tool.')
        return user

    @core.app.get('/api/non-qualified-calls/analyses/template')
    def nq_analyses_template(user=Depends(core.current_user)) -> Response:
        return Response(analyses_template(workspace_repository(user)), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="NQ_analyses_template.csv"'})

    @core.app.post('/api/non-qualified-calls/analyses/import')
    async def nq_analyses_import(request: Request, user=Depends(analyses_user)) -> Response:
        """Preview (``preview=1``) or import the analyses of the previous tool by JOIN_ID into the active workspace;
        ``overwrite=1`` replaces the values the calls already have instead of filling only the empty ones. With
        ``stream=1`` the answer is one JSON object per line: the progress (``step`` and ``progress`` from 0 to 1) while
        the import runs, then its ``result`` (or its ``error``)."""
        repository = workspace_repository(user)
        content, name, form = await uploaded_file(request, 'file', 100)
        users = set(workspace_users())
        options = {'overwrite': str(form.get('overwrite') or '') == '1', 'dry_run': str(form.get('preview') or '') == '1'}
        if str(form.get('stream') or '') != '1':
            try:
                return JSONResponse(import_analyses(repository, content, name, user.username, users, **options))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            except Exception as exc:  # noqa: BLE001 - an unreadable file is a user error.
                raise HTTPException(400, f'The analyses file could not be read: {exc}') from exc
        events: queue.Queue = queue.Queue()

        def run() -> None:
            try:
                result = import_analyses(repository, content, name, user.username, users, **options,
                                         progress=lambda step, fraction: events.put({'step': step, 'progress': round(fraction, 3)}))
                events.put({'result': result})
            except ValueError as exc:
                events.put({'error': str(exc)})
            except Exception as exc:  # noqa: BLE001 - an unreadable file is a user error.
                events.put({'error': f'The analyses file could not be read: {exc}'})
            finally:
                events.put(None)

        threading.Thread(target=run, name='nq-analyses-import', daemon=True).start()

        def lines() -> Any:
            while (event := events.get()) is not None:
                yield json.dumps(event, ensure_ascii=False) + '\n'

        return StreamingResponse(lines(), media_type='application/x-ndjson')

    @core.app.post('/api/non-qualified-calls/analyses/equivalences')
    async def nq_analyses_equivalences_download(request: Request, user=Depends(analyses_user)) -> Response:
        """The values of an analyses file with what each one becomes, to review before importing it."""
        repository = workspace_repository(user)
        content, name, _form = await uploaded_file(request, 'file', 100)
        try:
            workbook = analyses_equivalences_workbook(repository, content, name, set(workspace_users()))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - an unreadable file is a user error.
            raise HTTPException(400, f'The analyses file could not be read: {exc}') from exc
        log_action(repository, user, 'nq_analyses_equivalences_export', {'file': name})
        return Response(workbook, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': 'attachment; filename="NQ_analyses_equivalences.xlsx"'})

    @core.app.get('/api/non-qualified-calls/analyses/equivalences')
    def nq_analyses_rules_download(user=Depends(core.current_user)) -> Response:
        """The equivalences the import uses (the rules of the tool and those of the workspace), to review and upload back."""
        repository = workspace_repository(user)
        workbook = analyses_equivalences_workbook(repository, None, '', set(workspace_users()))
        log_action(repository, user, 'nq_analyses_equivalences_export', {})
        return Response(workbook, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': 'attachment; filename="NQ_analyses_equivalences.xlsx"'})

    @core.app.put('/api/non-qualified-calls/analyses/equivalences')
    async def nq_analyses_equivalences_upload(request: Request, user=Depends(analyses_user)) -> JSONResponse:
        """Keep the equivalences of a reviewed workbook for the imports of the workspace."""
        repository = workspace_repository(user)
        content, name, _form = await uploaded_file(request, 'file', 20)
        try:
            saved = save_analyses_equivalences(repository, content, set(workspace_users()))
            log_action(repository, user, 'nq_analyses_equivalences_save', {'file': name})
            return JSONResponse(saved)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - an unreadable file is a user error.
            raise HTTPException(400, f'The equivalences workbook could not be read: {exc}') from exc

    @core.app.delete('/api/non-qualified-calls/analyses/equivalences')
    def nq_analyses_equivalences_reset(user=Depends(analyses_user)) -> JSONResponse:
        """Forget the equivalences of the workspace (Default Equivalences): the import uses those of the tool."""
        repository = workspace_repository(user)
        result = reset_analyses_equivalences(repository)
        log_action(repository, user, 'nq_analyses_equivalences_reset', result)
        return JSONResponse(result)

    @core.app.delete('/api/non-qualified-calls/rca')
    def nq_rca_clear(user=Depends(config_user)) -> JSONResponse:
        repository = workspace_repository(user)
        return JSONResponse({'deleted': clear_rca_results(repository, user.username), 'rca_results': rca_results_summary(repository)})

    @core.app.post('/api/non-qualified-calls/lifecycle')
    def nq_lifecycle(payload: ExportPayload, user=Depends(core.current_user)) -> JSONResponse:
        repository = workspace_repository(user)
        return JSONResponse(lifecycle_stats(repository, payload.filters, user.username))

    @core.app.post('/api/non-qualified-calls/rca/insights')
    def nq_rca_insights(payload: ExportPayload, user=Depends(core.current_user)) -> JSONResponse:
        repository = workspace_repository(user)
        return JSONResponse(rca_insights(repository, payload.filters, user.username))

    @core.app.put('/api/non-qualified-calls/table-columns')
    def nq_save_table_columns(payload: TableColumnsPayload, user=Depends(config_user)) -> JSONResponse:
        """The optional columns of the Calls table: built-in ones and CDR columns (indexed again)."""
        repository = workspace_repository(user)
        columns = translate(lambda: save_table_columns(repository, payload.builtin, payload.cdr, user.username, payload.export_cdr,
                                                       defaults=payload.defaults))
        # New CDR columns are indexed in the background.
        start_nq_index(repository, core.submit_background_task)
        return JSONResponse({'table_columns': columns, 'sync': nq_index_status(repository)})

    @core.app.put('/api/non-qualified-calls/table-layout/mine')
    def nq_save_user_layout(payload: TableLayoutPayload, user=Depends(core.current_user)) -> JSONResponse:
        """The table layout of the user, only for them (every role)."""
        repository = workspace_repository(user)
        changes = payload.model_dump(exclude={'reason'})
        layouts = translate(lambda: save_user_layout(repository, user.username, changes, reason=payload.reason))
        start_nq_index(repository, core.submit_background_task)
        return JSONResponse({'table_layout': layouts, 'sync': nq_index_status(repository)})

    @core.app.put('/api/non-qualified-calls/table-layout/view')
    def nq_layout_view(payload: LayoutViewPayload, user=Depends(core.current_user)) -> JSONResponse:
        """Whether the user sees their own layout or that of the workspace."""
        repository = workspace_repository(user)
        layouts = translate(lambda: set_layout_view(repository, user.username, payload.view))
        start_nq_index(repository, core.submit_background_task)
        return JSONResponse({'table_layout': layouts, 'sync': nq_index_status(repository)})

    @core.app.post('/api/non-qualified-calls/table-layout/mine/copy')
    def nq_copy_workspace_layout(user=Depends(core.current_user)) -> JSONResponse:
        """Start the layout of the user again from that of the workspace."""
        repository = workspace_repository(user)
        return JSONResponse({'table_layout': copy_workspace_layout(repository, user.username)})

    @core.app.post('/api/non-qualified-calls/table-layout/publish')
    def nq_publish_layout(user=Depends(config_user)) -> JSONResponse:
        """Save the layout of the user for the workspace (admins and super-admins)."""
        repository = workspace_repository(user)
        layouts = translate(lambda: publish_user_layout(repository, user.username))
        start_nq_index(repository, core.submit_background_task)
        return JSONResponse({'table_layout': layouts, 'sync': nq_index_status(repository)})

    @core.app.post('/api/non-qualified-calls/rates')
    def nq_rates_route(payload: ExportPayload, user=Depends(core.current_user)) -> JSONResponse:
        """Calls and Non-Qualified Calls of every campaign and operator."""
        repository = workspace_repository(user)
        return JSONResponse(nq_rates(repository, payload.filters))

    @core.app.post('/api/non-qualified-calls/failures')
    def nq_failures_route(payload: ExportPayload, user=Depends(core.current_user)) -> JSONResponse:
        """How and where the filtered calls fail: result, technology, serving Vendor and host network, and sites."""
        return JSONResponse(failure_breakdowns(workspace_repository(user), payload.filters, user.username))

    @core.app.put('/api/non-qualified-calls/filters')
    def nq_save_filters(payload: QueryPayload, user=Depends(core.current_user)) -> JSONResponse:
        repository = workspace_repository(user)
        before = saved_filters(repository).get('in_scope') is True
        filters = save_filters(repository, payload.filters)
        if (filters.get('in_scope') is True) != before:
            # NQ Calls in Scope Only, switched on or off: every panel of the module counts other calls.
            log_action(repository, user, 'nq_calls_scope_only', {'in_scope': filters.get('in_scope') is True})
        return JSONResponse({'filters': filters})

    @core.app.post('/api/non-qualified-calls/filters/values')
    def nq_filter_values(payload: QueryPayload, user=Depends(core.current_user)) -> JSONResponse:
        """The values each filter offers among the calls of the other filters."""
        return JSONResponse({'values': available_filter_values(workspace_repository(user), payload.filters, user.username)})

    @core.app.post('/api/non-qualified-calls/calls')
    def nq_calls(payload: QueryPayload, user=Depends(core.current_user)) -> JSONResponse:
        repository = workspace_repository(user)
        result = query_calls(repository, payload.model_dump(), user.username)
        return JSONResponse({**result, 'sync': nq_index_status(repository)})

    @core.app.get('/api/non-qualified-calls/calls/{call_key}')
    def nq_call(call_key: str, user=Depends(core.current_user)) -> JSONResponse:
        detail = call_detail(workspace_repository(user), call_key)
        if detail is None:
            raise HTTPException(404, 'The call is no longer available. Refresh the list.')
        return JSONResponse(detail)

    @core.app.get('/api/non-qualified-calls/calls/{call_key}/map')
    def nq_call_map_route(call_key: str, radius_km: float = nq_call_map.DEFAULT_RADIUS_KM, tests: str = nq_call_map.DEFAULT_TEST_SCOPE,
                          user=Depends(core.current_user)) -> JSONResponse:
        """The map of the area where a call failed: its cells and sites, the sites around, the other Non-Qualified Calls
        and the radio levels of the tests around it (see nq_call_map). App Events records each map opened."""
        repository = workspace_repository(user)
        started = time.monotonic()
        details = {'call_key': call_key, 'radius_km': nq_call_map.normalise_radius(radius_km), 'tests': tests}
        try:
            payload = nq_call_map.call_map(repository, call_key, radius_km=radius_km, tests=tests)
        except ValueError as error:
            log_action(repository, user, 'nq_call_map_failed', {**details, 'error': str(error)})
            raise HTTPException(422, str(error)) from error
        except Exception as error:  # noqa: BLE001 - App Events keeps what failed for its troubleshooting.
            log_action(repository, user, 'nq_call_map_failed', {**details, 'error': f'{type(error).__name__}: {error}'[:500]})
            raise HTTPException(500, 'The map of the call could not be prepared. App Events keeps the error.') from error
        if payload is None:
            raise HTTPException(404, 'The call is no longer available. Refresh the list.')
        log_action(repository, user, 'nq_call_map', {
            **details, 'join_id': payload['call']['join_id'], 'operator': payload['call']['operator'],
            'sites': len(payload['sites']), 'cells_of_the_call': len(payload['trace']), 'nq_calls_around': len(payload['failures']),
            'tests_around': payload['tests']['total'], 'tests_shown': len(payload['tests']['rows']),
            # What its Diagnosis hints flagged, for the troubleshooting of the call.
            'to_check': [check['key'] for check in payload['diagnosis'] if check['level'] == 'bad'],
            'worth_a_look': [check['key'] for check in payload['diagnosis'] if check['level'] == 'warn'],
            'seconds': round(time.monotonic() - started, 2)})
        return JSONResponse(payload)

    @core.app.patch('/api/non-qualified-calls/calls/{call_key}')
    def nq_update_call(call_key: str, payload: TrackingPayload, user=Depends(editor_user)) -> JSONResponse:
        repository = workspace_repository(user)
        changed = translate(lambda: update_tracking(repository, [call_key], payload.changes, user.username,
                                                    set(workspace_users()), payload.version))
        if changed:
            log_action(repository, user, 'nq_call_update', {'call_key': call_key, 'fields': sorted(payload.changes)})
        return JSONResponse(call_detail(repository, call_key))

    @core.app.post('/api/non-qualified-calls/calls/bulk')
    def nq_bulk_update(payload: BulkTrackingPayload, user=Depends(editor_user)) -> JSONResponse:
        if not payload.call_keys:
            raise HTTPException(400, 'Select at least one call.')
        if len(payload.call_keys) > 5000:
            raise HTTPException(400, 'Change at most 5000 calls at once.')
        repository = workspace_repository(user)
        changed = translate(lambda: update_tracking(repository, payload.call_keys, payload.changes, user.username,
                                                    set(workspace_users())))
        if changed:
            log_action(repository, user, 'nq_calls_bulk_update', {
                'selected': len(payload.call_keys), 'changed': len(changed), 'fields': sorted(payload.changes),
            })
        return JSONResponse({'changed': len(changed)})

    @core.app.post('/api/non-qualified-calls/calls/{call_key}/comments')
    def nq_add_comment(call_key: str, payload: CommentPayload, user=Depends(editor_user)) -> JSONResponse:
        repository = workspace_repository(user)
        comment = translate(lambda: add_comment(repository, call_key, payload.body, user.username))
        log_action(repository, user, 'nq_comment_add', {'call_key': call_key, 'comment_id': comment['id']})
        return JSONResponse({'comment': comment})

    @core.app.patch('/api/non-qualified-calls/comments/{comment_id}')
    def nq_edit_comment(comment_id: int, payload: CommentPayload, user=Depends(editor_user)) -> JSONResponse:
        repository = workspace_repository(user)
        comment = translate(lambda: edit_comment(repository, comment_id, payload.body, user.username, can_moderate(user)))
        log_action(repository, user, 'nq_comment_edit', {'comment_id': comment_id})
        return JSONResponse({'comment': comment})

    @core.app.delete('/api/non-qualified-calls/comments/{comment_id}')
    def nq_delete_comment(comment_id: int, user=Depends(editor_user)) -> JSONResponse:
        repository = workspace_repository(user)
        comment = translate(lambda: delete_comment(repository, comment_id, user.username, can_moderate(user)))
        log_action(repository, user, 'nq_comment_delete', {'comment_id': comment_id})
        return JSONResponse({'comment': comment})

    @core.app.delete('/api/non-qualified-calls/history/{entry_id}')
    def nq_delete_history_entry(entry_id: int, user=Depends(moderator_user)) -> JSONResponse:
        deleted = translate(lambda: delete_history(workspace_repository(user), user.username, entry_ids=[entry_id]))
        if not deleted:
            raise HTTPException(404, 'The history entry no longer exists.')
        return JSONResponse({'deleted': deleted})

    @core.app.post('/api/non-qualified-calls/history/clear')
    def nq_clear_history(payload: HistoryPayload, user=Depends(moderator_user)) -> JSONResponse:
        if len(payload.call_keys) > 5000:
            raise HTTPException(400, 'Clear the history of at most 5000 calls at once.')
        deleted = translate(lambda: delete_history(workspace_repository(user), user.username, call_keys=payload.call_keys))
        return JSONResponse({'deleted': deleted})

    @core.app.put('/api/non-qualified-calls/options')
    def nq_save_options(payload: OptionsPayload, user=Depends(config_user)) -> JSONResponse:
        repository = workspace_repository(user)
        options = translate(lambda: save_options(repository, payload.statuses, payload.teams, user.username, set(workspace_users())))
        return JSONResponse({'options': options})

    @core.app.get('/api/non-qualified-calls/root-causes')
    def nq_root_causes(user=Depends(core.current_user)) -> JSONResponse:
        return JSONResponse(root_catalog_payload(workspace_repository(user)))

    @core.app.put('/api/non-qualified-calls/root-causes')
    def nq_save_root_causes(payload: RootCausesPayload, user=Depends(config_user)) -> JSONResponse:
        repository = workspace_repository(user)
        catalog = {'domains': payload.domains, 'categories': payload.categories, 'causes': payload.causes}
        return JSONResponse(root_catalog_payload(repository, translate(lambda: save_root_causes(
            repository, catalog, payload.require_to_close, user.username, defaults=payload.defaults))))

    @core.app.get('/api/non-qualified-calls/analysts')
    def nq_analysts(user=Depends(core.current_user)) -> JSONResponse:
        """The analysts and reviewers of the calls with their calls and assignees, and the users of the workspace."""
        repository = workspace_repository(user)
        users, names = workspace_users(), user_names()
        return JSONResponse({**analyst_assignments(repository, {user: names.get(user, '') for user in users}),
                             'users': users, 'user_names': names})

    @core.app.post('/api/non-qualified-calls/analysts/assign')
    def nq_assign_analysts(payload: AnalystAssignmentsPayload, user=Depends(core.current_user)) -> JSONResponse:
        """The calls of each analyst assigned to the user chosen for them, and the Analyst and Reviewer of the calls
        named as their users (``preview`` counts them, for every role; admins and super-admins apply them)."""
        if not payload.preview:
            config_user(user)
        repository = workspace_repository(user)
        return JSONResponse(translate(lambda: assign_analysts(
            repository, payload.assignments, user.username, set(workspace_users()), names=user_names(),
            overwrite=payload.overwrite, preview=payload.preview)))

    @core.app.post('/api/non-qualified-calls/root-causes/apply-categories')
    def nq_apply_cause_categories(payload: ApplyCategoriesPayload, user=Depends(config_user)) -> JSONResponse:
        """Give the calls with a root cause and no root category the category of their cause (``preview`` counts them)."""
        repository = workspace_repository(user)
        return JSONResponse({'calls': apply_cause_categories(repository, user.username, dry_run=payload.preview)})

    @core.app.put('/api/non-qualified-calls/root-causes/rule')
    def nq_save_root_cause_rule(payload: RootCauseRulePayload, user=Depends(rule_user)) -> JSONResponse:
        """The suggestion rule of the workspace (admins and super-admins); no rule restores the default one."""
        repository = workspace_repository(user)
        return JSONResponse({'rule': translate(lambda: save_root_cause_rule(repository, payload.rule, user.username))})

    @core.app.get('/api/non-qualified-calls/dta-rca/rules')
    def nq_dta_rca_rules(user=Depends(core.current_user)) -> JSONResponse:
        """The rules of the DT Analyzer RCA, the default ones and the Non-Qualified Calls each rule explains."""
        return JSONResponse(dta_rules_payload(workspace_repository(user)))

    @core.app.put('/api/non-qualified-calls/dta-rca/rules')
    def nq_save_dta_rca_rules(payload: DtaRulesPayload, user=Depends(config_user)) -> JSONResponse:
        """Save the rules of the DT Analyzer RCA (admins and super-admins): every call is calculated again at once,
        or when the indexing of the CDRs ends."""
        repository = workspace_repository(user)
        translate(lambda: nq_dta_rca.save_rules(repository, payload.rules, user.username, defaults=payload.defaults))
        if payload.learn is not None:
            nq_dta_rca.save_settings(repository, {'learn': payload.learn}, user.username)
        calculated = refresh_dta_rca(repository, wait=False)
        if calculated is not None:
            log_action(repository, user, 'nq_dta_rca_calculated', {'rows': calculated})
        return JSONResponse({**dta_rules_payload(repository), 'calculated': calculated})

    @core.app.post('/api/non-qualified-calls/root-causes/stats')
    def nq_root_cause_stats(payload: RootCauseStatsPayload, user=Depends(core.current_user)) -> JSONResponse:
        repository = workspace_repository(user)
        return JSONResponse(root_cause_stats(repository, payload.filters, user.username, payload.include_suggestions, payload.source))

    @core.app.post('/api/non-qualified-calls/progress')
    def nq_progress(payload: ProgressPayload, user=Depends(core.current_user)) -> JSONResponse:
        repository = workspace_repository(user)
        return JSONResponse(progress_stats(repository, payload.filters, user.username, payload.granularity))

    @core.app.post('/api/non-qualified-calls/export/{export_format}')
    def nq_export_document(export_format: str, payload: ProgressPayload, user=Depends(core.current_user)) -> Response:
        """The Executive Summary, Progress Status and Root Cause Analysis of the filtered calls, in PowerPoint or Word."""
        if export_format not in {'powerpoint', 'word'}:
            raise HTTPException(404, 'Unsupported export type.')
        repository = workspace_repository(user)
        executive, progress, options, lines = summary_parts(repository, payload.filters, user.username, payload.granularity,
                                                            payload.include_suggestions)
        options = {**options, 'show_not_classified': payload.show_not_classified, 'show_empty': payload.show_empty}
        suffix = '.pptx' if export_format == 'powerpoint' else '.docx'
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        name = re.sub(r'[^A-Za-z0-9._ -]+', '_', f'{stamp} - Non-Qualified Calls - {core.active_workspace.name}{suffix}')
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / f'summary{suffix}'
            write_summary_document(export_format, destination, executive, progress, options, lines)
            content = destination.read_bytes()
        media_type = ('application/vnd.openxmlformats-officedocument.presentationml.presentation' if export_format == 'powerpoint'
                      else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        log_action(repository, user, f'nq_summary_export_{export_format}', {'file': name})
        return Response(content, media_type=media_type, headers={'Content-Disposition': f'attachment; filename="{name}"'})

    @core.app.post('/api/non-qualified-calls/export')
    def nq_export(payload: ExportPayload, user=Depends(core.current_user)) -> Response:
        repository = workspace_repository(user)
        content = export_workbook(repository, payload.filters, user.username)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        name = re.sub(r'[^A-Za-z0-9._-]+', '_', f'{core.active_workspace.name}_non-qualified-calls_{stamp}.xlsx')
        log_action(repository, user, 'nq_calls_export', {'file': name})
        return Response(content, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': f'attachment; filename="{name}"'})
