"""The SQL tool of the AI Assistant: one read-only SELECT (DuckDB) over the Non-Qualified Calls and the rows of the CDRs.

The tables the engine can read:

- ``nq_calls``: one row per Non-Qualified Call, the latest version of each call, as the NQ Calls list of the module
  shows it. Each row has its follow-up, its DT Analyzer RCA, its impact and priority, and its Hotspot, Time-Window
  and Cluster groups (their IDs and sizes, as the NQ Hotspots, Time-Window & Clustered Issues panel shows them).
- ``cdr_data``, ``cdr_voice``, ``cdr_speech``: the rows of the CDRs, read from their columnar copies (cdr_store).
- ``cdrs``: the ready CDRs of the workspace.

Every table leaves out the operators that the Operator Maps exclude, and the operator columns hold the names of the
Operator Maps. No table holds coordinates, subscriber identifiers (IMSI, IMEI, MSISDN, dialled number), IP addresses
or the paths of the files on the server.

Only one SELECT runs. Its syntax tree may read only these tables and its own CTEs, and no table function, so it reads
no file. It runs on a DuckDB database in memory that can read files only in the folder of the copies, with a locked
configuration. It is stopped after QUERY_SECONDS, or when the question is stopped. Each result keeps up to
MAX_RESULT_ROWS rows: the engine receives the first ones, and an answer can show the whole result as a table (see
assistant.py) without the engine copying it.
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import math
import re
import sqlite3
import threading
import time
from typing import Any

from src.modules.assistant.assistant_tools import ToolContext, ToolError, _canonical_operator, _excluded_operators, _ready_cdrs

QUERY_SECONDS = 90
MAX_RESULT_ROWS = 5000
DEFAULT_SENT_ROWS = 50
MAX_SENT_ROWS = 200
MAX_COLUMNS_LISTED = 400
CDR_TABLES = {'cdr_data': 'data', 'cdr_voice': 'voice', 'cdr_speech': 'speech'}
TABLES = {
    'nq_calls': 'One row per Non-Qualified Call (the failed or not qualified Data tests and Voice and Speech calls), the '
                'latest version of each, as the NQ Calls list of the module shows it: its CDR fields, follow-up, DT '
                'Analyzer RCA, scoring impact, priority, and its Hotspot, Time-Window and Cluster groups.',
    'cdr_data': 'Every row of the Data CDRs (one per test) with every column of the CDRs.',
    'cdr_voice': 'Every row of the Voice CDRs (one per call) with every column of the CDRs.',
    'cdr_speech': 'Every row of the Speech CDRs (one per speech sample) with every column of the CDRs.',
    'cdrs': 'The ready CDRs of the workspace: their dataset_id (the dataset_id of the rows of the other tables), type, '
            'NR Mode, file name, rows and campaigns.',
}
# The columns of nq_calls, in their order, with their type and what they hold.
NQ_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ('join_id', 'VARCHAR', 'The JOIN_ID of the call, the same in the Daily and Final CDRs.'),
    ('call_key', 'VARCHAR', 'The key of the call in the tool (unique).'),
    ('dataset_id', 'BIGINT', 'The CDR of its latest version (cdrs.dataset_id).'),
    ('source_row_id', 'BIGINT', 'Its row in that CDR (source_row_id of the cdr_* tables).'),
    ('service', 'VARCHAR', 'data, voice or speech.'),
    ('call_type', 'VARCHAR', 'Voice, WhatsApp, Data or Ping.'),
    ('nr_mode', 'VARCHAR', 'NSA or SA.'),
    ('campaign', 'VARCHAR', 'Its campaign.'),
    ('operator', 'VARCHAR', 'Its operator, as the Operator Maps name it.'),
    ('vendor', 'VARCHAR', 'The RAN vendor of the cells that served it.'),
    ('operator_vendor', 'VARCHAR', 'Operator and vendor together, as the CDR gives them.'),
    ('host_network', 'VARCHAR', 'The network that served it (another operator when the cell is shared).'),
    ('region', 'VARCHAR', 'Its region.'),
    ('cluster', 'VARCHAR', 'Its cluster (an area of the CDRs, not the Cluster of NQ Calls: see nq_cluster_id).'),
    ('city', 'VARCHAR', 'Its city.'),
    ('environment', 'VARCHAR', 'Its environment (city, road...).'),
    ('area', 'VARCHAR', 'Cities or Connecting Roads, as the NQ Prioritization tells them apart.'),
    ('technology', 'VARCHAR', 'The technology of the call.'),
    ('test_name', 'VARCHAR', 'The test.'),
    ('session_type', 'VARCHAR', 'The session type.'),
    ('direction', 'VARCHAR', 'The direction (MO, MT...).'),
    ('result', 'VARCHAR', 'The result of the call in the CDR.'),
    ('start_time', 'TIMESTAMP', 'When it started.'),
    ('end_time', 'TIMESTAMP', 'When it ended.'),
    ('failure_phase', 'VARCHAR', 'The phase of the failure.'),
    ('failure_technology', 'VARCHAR', 'The technology of the failure.'),
    ('failure_classification', 'VARCHAR', 'The failure classification of the CDR.'),
    ('failure_category', 'VARCHAR', 'The failure category of the CDR.'),
    ('failure_subcategory', 'VARCHAR', 'The failure subcategory of the CDR.'),
    ('failure_comment', 'VARCHAR', 'The failure comment of the CDR.'),
    ('site_id', 'VARCHAR', 'The site that served it.'),
    ('cell_id', 'VARCHAR', 'The chain of its cells.'),
    ('last_cell_id', 'VARCHAR', 'The cell where it ended.'),
    ('status', 'VARCHAR', 'Its status of follow-up.'),
    ('team', 'VARCHAR', 'The team that analyses it.'),
    ('analyst', 'VARCHAR', 'Who analyses it: a username, or the name of an analyst without account (analyses of the previous tool).'),
    ('reviewer', 'VARCHAR', 'Who reviewed its analysis: a username, or the name of a reviewer without account (analyses of the previous tool).'),
    ('root_domain', 'VARCHAR', 'The root cause domain the analysts chose.'),
    ('root_category', 'VARCHAR', 'The root category the analysts chose.'),
    ('root_cause', 'VARCHAR', 'The root cause the analysts chose.'),
    ('updated_by', 'VARCHAR', 'The user who changed its follow-up last.'),
    ('updated_at', 'TIMESTAMP', 'When its follow-up changed last.'),
    ('comments', 'BIGINT', 'How many comments it has.'),
    ('dta_rca_domain', 'VARCHAR', 'The domain the DT Analyzer RCA gives it.'),
    ('dta_rca_category', 'VARCHAR', 'The category the DT Analyzer RCA gives it.'),
    ('dta_rca_cause', 'VARCHAR', 'The cause the DT Analyzer RCA gives it.'),
    ('impact_points', 'DOUBLE', 'The scoring points it makes its operator lose.'),
    ('impact_level', 'VARCHAR', 'High, Medium or Low impact.'),
    ('impact_kpis', 'VARCHAR', 'The KPIs whose points it loses.'),
    ('place', 'VARCHAR', 'Its place (the site of its last cell, or a spot).'),
    ('repetitions', 'BIGINT', 'How many calls of its operator failed near it, in its campaign and the previous ones.'),
    ('repeated_campaigns', 'BIGINT', 'In how many campaigns those calls are.'),
    ('repeated', 'VARCHAR', 'Yes when it is a Repeated Issue (a call of a Cluster).'),
    ('priority', 'VARCHAR', 'Its priority (P1 first), the one of the analysts or else the one the rules suggest.'),
    ('suggested_priority', 'VARCHAR', 'The priority the rules suggest.'),
    ('prioritization', 'VARCHAR', 'Whether the NQ Prioritization prioritizes it, only tracks it or leaves it out.'),
    ('priority_rule', 'VARCHAR', 'The step of the strategy that takes it.'),
    ('queue', 'VARCHAR', 'The queue of the analysts it is in (Voice, Data or Unique).'),
    ('queue_step', 'BIGINT', 'Its step in the queue.'),
    ('expected_points', 'DOUBLE', 'The points expected back when it is fixed.'),
    ('hotspot_id', 'VARCHAR', 'The Hotspot (H-...) it is in, empty when none: a Cluster and a Time-Window issue together.'),
    ('hotspot_calls', 'BIGINT', 'How many NQ Calls its Hotspot holds.'),
    ('time_window_id', 'VARCHAR', 'The Time-Window issue (T-...) it is in, empty when none: consecutive failures of '
                                  'its drive, minutes apart and close.'),
    ('time_window_calls', 'BIGINT', 'How many NQ Calls its Time-Window issue holds.'),
    ('nq_cluster_id', 'VARCHAR', 'The Cluster of NQ Calls (C-...) it is in, empty when none: failures of its operator '
                                 'close to each other.'),
    ('nq_cluster_calls', 'BIGINT', 'How many NQ Calls its Cluster holds.'),
    ('version_state', 'VARCHAR', 'How the CDRs see it: current, changed, newer, not_in_final or qualified.'),
    ('cdr_count', 'BIGINT', 'In how many CDRs it is.'),
)
# The NQ Calls fields of the analysts that become columns (field_<key>): not the long texts.
FIELD_TYPES = {'list': 'VARCHAR', 'text': 'VARCHAR', 'number': 'DOUBLE', 'date': 'VARCHAR', 'yes_no': 'VARCHAR'}
# The CDR columns no table holds: coordinates, subscriber identifiers, IP addresses and the paths of the files.
_HIDDEN = re.compile(r'latitude|longitude|imsi|imei|msisdn|iccid|subscriber|dial(?:l)?ed_?number|called_?number|'
                     r'calling_?number|phone|^source_file$', re.IGNORECASE)
_IP_TOKEN = re.compile(r'^ips?$', re.IGNORECASE)
# The operator columns of the CDRs, given the names of the Operator Maps.
OPERATOR_COLUMNS = ('operator', 'operator_a', 'operator_b', 'home_operator', 'home_operator_a', 'home_operator_b',
                    'host_network')


def hidden_column(name: str) -> bool:
    """Whether a CDR column is never readable: coordinates, subscriber identifiers, IP addresses (not the KPIs of the
    IP service or layer) and the paths of the files."""
    if _HIDDEN.search(str(name)):
        return True
    tokens = [token.casefold() for token in re.split(r'[_/\s]+', str(name)) if token]
    return any(_IP_TOKEN.match(token) for token in tokens) and not {'service', 'layer'} & set(tokens)


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _text(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


# -- the SQL ------------------------------------------------------------------------------------------------------------

def _walk(node: Any, found: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        if node.get('type') in {'BASE_TABLE', 'TABLE_FUNCTION'}:
            found.append(node)
        for value in node.values():
            _walk(value, found)
    elif isinstance(node, list):
        for value in node:
            _walk(value, found)


def _cte_names(node: Any, names: set[str]) -> None:
    if isinstance(node, dict):
        cte_map = node.get('cte_map') if isinstance(node.get('cte_map'), dict) else {}
        for item in cte_map.get('map') or []:
            if isinstance(item, dict) and item.get('key'):
                names.add(str(item['key']).casefold())
        for value in node.values():
            _cte_names(value, names)
    elif isinstance(node, list):
        for value in node:
            _cte_names(value, names)


def check_sql(connection: Any, sql: str) -> set[str]:
    """The tables a query reads; a ToolError unless it is one SELECT that reads only the tables of the assistant."""
    import duckdb

    text = str(sql or '').strip().rstrip(';').strip()
    if not text:
        raise ToolError('sql is one SELECT query.')
    if len(text) > 20_000:
        raise ToolError('A query has at most 20,000 characters.')
    try:
        statements = connection.extract_statements(text)
    except duckdb.Error as exc:
        raise ToolError(f'The query is not valid SQL: {str(exc).splitlines()[0]}') from exc
    if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
        raise ToolError('Only one SELECT query (it may start with WITH) runs: the assistant only reads.')
    tree = json.loads(connection.execute('SELECT json_serialize_sql(?)', [text]).fetchall()[0][0])
    if tree.get('error'):
        raise ToolError(f'The query is not valid SQL: {tree.get("error_message") or "it cannot be read"}')
    references: list[dict[str, Any]] = []
    _walk(tree.get('statements'), references)
    ctes: set[str] = set()
    _cte_names(tree.get('statements'), ctes)
    tables: set[str] = set()
    for reference in references:
        if reference.get('type') == 'TABLE_FUNCTION':
            name = ((reference.get('function') or {}).get('function_name')) or 'a table function'
            raise ToolError(f'{name} cannot be read: read only the tables {", ".join(TABLES)}.')
        name = str(reference.get('table_name') or '').casefold()
        if reference.get('catalog_name') or reference.get('schema_name') or (name not in TABLES and name not in ctes):
            shown = '.'.join(part for part in (reference.get('catalog_name'), reference.get('schema_name'),
                                                reference.get('table_name')) if part)
            raise ToolError(f'There is no table {shown}: read only {", ".join(TABLES)} (and your own WITH queries).')
        if name in TABLES:
            tables.add(name)
    return tables


# -- the database -------------------------------------------------------------------------------------------------------

class QueryDatabase:
    """The DuckDB database of one question: its tables made when a query first reads them."""

    def __init__(self, context: ToolContext) -> None:
        import duckdb
        from src.modules.cdr import cdr_store

        self.context = context
        self.root = cdr_store.store_root(context.repository.db_path)
        self.connection = duckdb.connect(':memory:')
        for statement in ("SET python_enable_replacements = false", "SET threads = 2", "SET memory_limit = '2GB'",
                          f"SET allowed_directories = [{_text(str(self.root) + '/')}]",
                          'SET enable_external_access = false', 'SET lock_configuration = true'):
            self.connection.execute(statement)
        self.made: set[str] = set()
        self.notes: dict[str, str] = {}

    def close(self) -> None:
        self.connection.close()

    def prepare(self, tables: set[str]) -> None:
        for table in sorted(tables - self.made):
            if table == 'nq_calls':
                self._nq_calls()
            elif table == 'cdrs':
                self._cdrs()
            else:
                self._cdr_view(table)
            self.made.add(table)

    # The tables.

    def _nq_calls(self) -> None:
        frame, fields = nq_calls_frame(self.context)
        self.connection.register('_nq_calls_rows', frame)
        times = ', '.join(f"TRY_CAST(replace(substr(CAST({name} AS VARCHAR), 1, 19), 'T', ' ') AS TIMESTAMP) AS {name}"
                          for name in ('start_time', 'end_time', 'updated_at'))
        self.connection.execute(f'CREATE VIEW nq_calls AS SELECT * REPLACE ({times}) FROM _nq_calls_rows')
        self.notes['nq_calls'] = ', '.join(f'field_{key} ({label})' for key, label in fields)

    def _cdrs(self) -> None:
        import pandas as pd
        from src.modules.cdr.cdr_auto_selection import cdr_campaigns

        rows = _ready_cdrs(self.context.repository)
        campaigns = cdr_campaigns(self.context.repository, [int(row['id']) for row in rows]) if rows else {}
        frame = pd.DataFrame([{
            'dataset_id': int(row['id']), 'cdr_type': str(row.get('dataset_kind') or ''), 'nr_mode': str(row.get('nr_mode') or ''),
            'file_name': str(row.get('file_name') or row.get('name') or ''), 'rows': int(row.get('row_count') or 0),
            'campaigns': ', '.join(str(value) for value in campaigns.get(int(row['id']), [])),
            'processed_at': str(row.get('processed_at') or ''),
        } for row in rows], columns=['dataset_id', 'cdr_type', 'nr_mode', 'file_name', 'rows', 'campaigns', 'processed_at'])
        self.connection.register('_cdrs_rows', frame)
        self.connection.execute('CREATE VIEW cdrs AS SELECT * FROM _cdrs_rows')

    def _cdr_view(self, table: str) -> None:
        from src.modules.cdr import cdr_store

        kind = CDR_TABLES[table]
        repository = self.context.repository
        manifests, _signature = cdr_store._catalog_inputs(repository.db_path, cdr_store.included_cdrs(repository))
        source = f'_source_{kind}'
        self.connection.execute(cdr_store._view_sql(kind, manifests[kind], self.root).replace(
            f'CREATE VIEW {cdr_store.quote(f"cdr_{kind}")}', f'CREATE VIEW {_quote(source)}', 1))
        columns = [(str(row[0]), str(row[1])) for row in self.connection.execute(f'DESCRIBE {_quote(source)}').fetchall()]
        hidden = [name for name, _type in columns if hidden_column(name)]
        canonical = self._operator_names()
        replaced = []
        for name, column_type in columns:
            if name.casefold() in OPERATOR_COLUMNS and column_type == 'VARCHAR' and canonical and name not in hidden:
                cases = ' '.join(f'WHEN {_text(spelling)} THEN {_text(value)}' for spelling, value in canonical.items())
                replaced.append(f'CASE lower(trim({_quote(name)})) {cases} ELSE {_quote(name)} END AS {_quote(name)}')
        excluded = sorted(spelling for spelling, value in canonical.items() if value.casefold() in _excluded_operators(self.context))
        operator = next((name for name, column_type in columns if name.casefold() in OPERATOR_COLUMNS[:6]
                         and column_type == 'VARCHAR'), None)
        where = (f' WHERE {_quote(operator)} IS NULL OR lower(trim({_quote(operator)})) NOT IN ({", ".join(_text(value) for value in excluded)})'
                 if operator and excluded else '')
        star = 'SELECT *' + (f' EXCLUDE ({", ".join(_quote(name) for name in hidden)})' if hidden else '') + \
            (f' REPLACE ({", ".join(replaced)})' if replaced else '')
        self.connection.execute(f'CREATE VIEW {table} AS {star} FROM {_quote(source)}{where}')
        missing = len(cdr_store.included_cdrs(repository).get(kind, set())) - len(manifests[kind])
        if missing > 0:
            self.notes[table] = f'{missing} CDR(s) of this type are not in the table yet: their copy is being written.'

    def _operator_names(self) -> dict[str, str]:
        """Every spelling of an operator (casefold) and the name the Operator Maps give it."""
        from src.modules.assistant.assistant_tools import _operator_groups

        names: dict[str, str] = {}
        for group in _operator_groups(self.context):
            canonical = str(group.get('canonical') or '').strip()
            for spelling in [canonical, *(str(alias) for alias in group.get('aliases') or [])]:
                if spelling.strip() and canonical:
                    names.setdefault(spelling.strip().casefold(), canonical)
        return names

    # Reading.

    def columns(self, table: str) -> list[tuple[str, str]]:
        self.prepare({table})
        return [(str(row[0]), str(row[1])) for row in self.connection.execute(f'DESCRIBE {table}').fetchall()]

    def run(self, sql: str, limit: int) -> tuple[list[str], list[list[Any]], bool]:
        """The columns and first ``limit`` rows of a query, and whether it has more; stopped after QUERY_SECONDS or
        when the question is stopped."""
        import duckdb

        text = str(sql).strip().rstrip(';').strip()
        done, stopped = threading.Event(), []

        def watch() -> None:
            deadline = time.monotonic() + QUERY_SECONDS
            while not done.wait(0.25):
                if self.context.cancelled() or time.monotonic() > deadline:
                    stopped.append('stopped' if self.context.cancelled() else 'timeout')
                    self.connection.interrupt()
                    return

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            described = self.connection.execute(f'DESCRIBE {text}').fetchall()
            names = [str(row[0]) for row in described]
            # Times with a time zone are read as text (their Python values need a module the tool does not have). The
            # query ends on a line of its own: one that closes with a line comment keeps the parenthesis outside it.
            casts = [f'CAST(#{index + 1} AS VARCHAR)' if 'TIME ZONE' in str(row[1]).upper() else f'#{index + 1}'
                     for index, row in enumerate(described)]
            cursor = self.connection.execute(f'SELECT {", ".join(casts)} FROM ({text}\n) AS assistant_query LIMIT {int(limit) + 1}')
            rows = [list(row) for row in cursor.fetchall()]
        except duckdb.InterruptException as exc:
            if stopped and stopped[0] == 'stopped':
                raise ToolError('Stopped.') from exc
            raise ToolError(f'The query took more than {QUERY_SECONDS} seconds: aggregate or filter more.') from exc
        except duckdb.Error as exc:
            raise ToolError(f'The query failed: {str(exc).splitlines()[0][:500]}') from exc
        finally:
            done.set()
        return names, rows[:limit], len(rows) > limit


def database(context: ToolContext) -> QueryDatabase:
    if 'query_database' not in context.cache:
        context.cache['query_database'] = QueryDatabase(context)
        context.on_close(context.cache['query_database'].close)
    return context.cache['query_database']


# -- nq_calls -----------------------------------------------------------------------------------------------------------

_BASE_COLUMNS = (
    'call_key', 'dataset_id', 'source_row_id', 'join_id', 'service', 'nr_mode', 'campaign', 'operator', 'vendor',
    'operator_vendor', 'host_network', 'region', 'cluster', 'city', 'environment', 'technology', 'test_name', 'session_type',
    'direction', 'result', 'start_time', 'end_time', 'failure_phase', 'failure_technology', 'failure_classification',
    'failure_category', 'failure_subcategory', 'failure_comment', 'site_id', 'cell_id', 'last_cell_id', 'status', 'team',
    'analyst', 'reviewer', 'root_domain', 'root_category', 'root_cause', 'updated_by', 'updated_at', 'comment_count',
    'field_values_json', 'dta_json', 'impact_points', 'impact_level', 'impact_kpis', 'place_label', 'repetitions',
    'repeated_campaigns', 'repeated', 'prioritization', 'priority_rule', 'suggested_priority', 'queue', 'queue_step',
    'expected_points', 'cluster_key', 'cluster_size', 'consecutive_key', 'consecutive_size', 'repeat_key', 'repeat_size',
    'version_state', 'cdr_count',
)


def _loads(value: Any) -> dict[str, Any]:
    try:
        loaded = json.loads(value or '{}')
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _whole(value: Any) -> int | None:
    try:
        return None if value is None or value == '' else int(value)
    except (TypeError, ValueError):
        return None


def nq_calls_frame(context: ToolContext):
    """The rows of nq_calls (see NQ_COLUMNS), and the fields of the analysts that are columns too (key, label)."""
    import pandas as pd
    from src.modules.nq import non_qualified_calls as nq
    from src.modules.nq import nq_prioritization as prioritization

    repository = context.repository
    try:
        fields = [field for field in nq.list_fields(repository) if field['source'] == 'user' and field['type'] in FIELD_TYPES
                  and re.fullmatch(r'[A-Za-z0-9_]+', field['key'])]
        base, parameters = nq._base_sql(nq.untracked_status(repository), repository)
        with repository.connection() as connection:
            available = {str(item[0]) for item in connection.execute(f'WITH calls AS ({base}) SELECT * FROM calls LIMIT 0',
                                                                     parameters).description}
            selected = [name if name in available else f'NULL AS {name}' for name in _BASE_COLUMNS]
            rows = [dict(row) for row in connection.execute(f'WITH calls AS ({base}) SELECT {", ".join(selected)} FROM calls',
                                                            parameters).fetchall()]
    except sqlite3.OperationalError as exc:
        if 'no such table' not in str(exc):
            raise
        fields, rows = [], []
    excluded = _excluded_operators(context)
    records = []
    for row in rows:
        operator = _canonical_operator(context, row['operator'] or '')
        if operator.casefold() in excluded:
            continue
        dta, values = _loads(row['dta_json']), _loads(row['field_values_json'])
        record = {
            **{name: row[name] for name in ('join_id', 'call_key', 'dataset_id', 'source_row_id', 'service')},
            'call_type': prioritization.KIND_LABELS[prioritization.call_kind(row['service'], row['test_name'], row['session_type'])],
            'nr_mode': row['nr_mode'], 'campaign': row['campaign'], 'operator': operator, 'vendor': row['vendor'],
            'operator_vendor': row['operator_vendor'],
            'host_network': _canonical_operator(context, row['host_network'] or '') if row['host_network'] else row['host_network'],
            **{name: row[name] for name in ('region', 'cluster', 'city', 'environment')},
            'area': prioritization.STEP_AREAS[prioritization.call_area(row['environment'])],
            **{name: row[name] for name in (
                'technology', 'test_name', 'session_type', 'direction', 'result', 'start_time', 'end_time', 'failure_phase',
                'failure_technology', 'failure_classification', 'failure_category', 'failure_subcategory', 'failure_comment',
                'site_id', 'cell_id', 'last_cell_id', 'status', 'team', 'analyst', 'reviewer', 'root_domain', 'root_category', 'root_cause',
                'updated_by', 'updated_at')},
            'comments': _whole(row['comment_count']) or 0,
            'dta_rca_domain': str(dta.get('dta_domain') or ''), 'dta_rca_category': str(dta.get('dta_category') or ''),
            'dta_rca_cause': str(dta.get('dta_cause') or ''),
            'impact_points': row['impact_points'], 'impact_level': row['impact_level'], 'impact_kpis': row['impact_kpis'],
            'place': row['place_label'], 'repetitions': _whole(row['repetitions']),
            'repeated_campaigns': _whole(row['repeated_campaigns']), 'repeated': row['repeated'],
            'priority': str(values.get(prioritization.PRIORITY_FIELD) or row['suggested_priority'] or ''),
            **{name: row[name] for name in ('suggested_priority', 'prioritization', 'priority_rule', 'queue')},
            'queue_step': _whole(row['queue_step']), 'expected_points': row['expected_points'],
        }
        # Its groups as the NQ Hotspots, Time-Window & Clustered Issues panel shows them: those of 2 calls or more.
        for prefix, letter, key, size in (('hotspot', 'H', 'cluster_key', 'cluster_size'),
                                          ('time_window', 'T', 'consecutive_key', 'consecutive_size'),
                                          ('nq_cluster', 'C', 'repeat_key', 'repeat_size')):
            calls = _whole(row[size])
            grouped = bool(row[key]) and (calls or 0) >= 2
            record[f'{prefix}_id'] = prioritization.group_id(letter, str(row[key])) if grouped else ''
            record[f'{prefix}_calls'] = calls if grouped else None
        record['version_state'], record['cdr_count'] = row['version_state'], _whole(row['cdr_count'])
        for field in fields:
            value = values.get(field['key'])
            if field['type'] == 'number':
                try:
                    value = float(value) if value not in (None, '') else None
                except (TypeError, ValueError):
                    value = None
            record[f'field_{field["key"]}'] = value if value not in ('',) else None
        records.append(record)
    columns = [name for name, _type, _text in NQ_COLUMNS] + [f'field_{field["key"]}' for field in fields]
    frame = pd.DataFrame.from_records(records, columns=columns)
    for name, column_type, _description in NQ_COLUMNS:
        if column_type in {'BIGINT', 'DOUBLE'}:
            frame[name] = pd.to_numeric(frame[name], errors='coerce')
            if column_type == 'BIGINT':
                frame[name] = frame[name].astype('Int64')
        else:
            frame[name] = frame[name].astype(object)
    return frame, [(field['key'], field['label']) for field in fields]


# -- the tools ----------------------------------------------------------------------------------------------------------

def _value(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        value = float(value)
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else round(value, 4)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat(sep=' ') if isinstance(value, dt.datetime) else value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return '(binary)'
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _value(item) for key, item in value.items()}
    return value


def query(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one SELECT: its columns, its first rows for the engine, and a result id (R1, R2…) an answer can show whole."""
    try:
        sent_rows = max(1, min(MAX_SENT_ROWS, int(arguments.get('max_rows') or DEFAULT_SENT_ROWS)))
    except (TypeError, ValueError) as exc:
        raise ToolError('max_rows is a number.') from exc
    sql = str(arguments.get('sql') or '')
    store = database(context)
    tables = check_sql(store.connection, sql)
    context.progress('Reading ' + ', '.join(sorted(tables)) if tables else 'Running the query')
    store.prepare(tables)
    columns, rows, more = store.run(sql, MAX_RESULT_ROWS)
    rows = [[_value(value) for value in row] for row in rows]
    results = context.cache.setdefault('query_results', {})
    result_id = f'R{len(results) + 1}'
    results[result_id] = {'columns': columns, 'rows': rows, 'more': more, 'sql': sql.strip()}
    found = {'result_id': result_id, 'columns': columns, 'row_count': len(rows), 'rows': rows[:sent_rows]}
    if more:
        found['note'] = (f'The query gives more than {MAX_RESULT_ROWS} rows: only the first {MAX_RESULT_ROWS} are kept. '
                         'Aggregate, filter or count instead.')
    elif len(rows) > sent_rows:
        found['note'] = (f'Only the first {sent_rows} of the {len(rows)} rows are given here. To show every row in the '
                         f'answer, add a table with "result": "{result_id}" (the tool fills its rows); for figures, '
                         'aggregate in SQL.')
    notes = [store.notes[table] for table in sorted(tables) if store.notes.get(table) and table in CDR_TABLES]
    if notes:
        found['coverage'] = notes
    return found


def table_columns(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """The tables of the query tool, or the columns of one (those whose name holds ``search``)."""
    table = str(arguments.get('table') or '').strip().casefold()
    if not table:
        return {'tables': [{'table': name, 'description': description} for name, description in TABLES.items()]}
    if table not in TABLES:
        raise ToolError(f'table is one of {", ".join(TABLES)}.')
    store = database(context)
    words = [word.casefold() for word in re.split(r'[\s,]+', str(arguments.get('search') or '')) if word]
    described = {name: description for name, _type, description in NQ_COLUMNS}
    columns = []
    for name, column_type in store.columns(table):
        if words and not any(word in name.casefold() for word in words):
            continue
        item = {'column': name, 'type': column_type}
        if table == 'nq_calls':
            item['description'] = described.get(name) or 'A field the analysts fill in.'
        columns.append(item)
    found: dict[str, Any] = {'table': table, 'description': TABLES[table], 'columns': columns[:MAX_COLUMNS_LISTED],
                             'column_count': len(columns)}
    if table in CDR_TABLES:
        found['note'] = ('Coordinates, subscriber identifiers, IP addresses and file paths are left out. Column names are '
                         'case-insensitive; quote those with other characters ("MO_CC_Setup/SIP_Invite").')
        if store.notes.get(table):
            found['coverage'] = store.notes[table]
    if table == 'nq_calls' and store.notes.get('nq_calls'):
        found['fields_of_the_analysts'] = store.notes['nq_calls']
    if len(columns) > MAX_COLUMNS_LISTED:
        found['note_columns'] = f'Only the first {MAX_COLUMNS_LISTED} columns are listed: search for the ones you need.'
    return found
