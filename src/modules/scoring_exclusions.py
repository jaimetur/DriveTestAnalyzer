"""Excluded Calls of Scoring & GAP Analysis: lists of calls, by their NetCheck JOIN_ID, left out of every scoring.

A list is imported from a CSV or Excel file with a JOIN_ID column (JOINT_ID and Call Key are read as well, and a Reason
column when it has one). It applies to every CDR, or to the CDRs it is assigned to: a list assigned to a Voice or
Speech CDR also applies to the Speech or Voice CDR of the same NR Mode, stage and campaign, whose samples carry the
JOIN_IDs of the same calls. Each list is switched on or off on its own.

The rows of the excluded calls are left out when the scoring reads the rows of the CDRs (``row_condition``) and when
the Scoring History indexes them. Which calls of each list every CDR holds is found in the background, before the
Scoring History indexes the CDRs (``match_pending``). The signature of a CDR (``ExclusionScope.signature``) names the
lists that leave calls of it out, so the scorings and the history of the CDRs a list does not touch stay valid.

Lists belong to the workspace and travel as the Scoring Excluded Calls element of Import / Export / Transfer, Full
Workspace transfers and backups, assigned to their CDRs by file name.
"""
import csv
import hashlib
import io
import json
import re
import sqlite3
import uuid
from typing import Any, Callable, Iterable

from src.modules.cdr_stage import dataset_cdr_stage
from src.modules.column_names import resolve_column_name
from src.modules.nq_rca import _cell, _table
from src.modules.nr_mode import dataset_nr_mode
from src.modules.repository import local_now_iso

LISTS_TABLE = 'scoring_exclusion_lists'
CALLS_TABLE = 'scoring_excluded_calls'
MATCHES_TABLE = 'scoring_exclusion_matches'
TABLE_TITLES = {LISTS_TABLE: 'Scoring Exclusion Lists', CALLS_TABLE: 'Scoring Excluded Calls',
                MATCHES_TABLE: 'Scoring Exclusion Matches'}
EXCLUSIONS_FORMAT = 'drivetest-analyzer-scoring-excluded-calls'
EXCLUSIONS_VERSION = 1
JOIN_COLUMN = 'JOIN_ID'
CDR_KINDS = ('data', 'voice', 'speech')
CALL_KINDS = ('voice', 'speech')
FILE_SUFFIXES = ('.csv', '.txt', '.tsv', '.xlsx', '.xlsm')
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_CALLS = 100_000
MAX_LISTS = 200
MAX_NAME_LENGTH = 120
MAX_REASON_LENGTH = 300
# Column identities (letters and digits only) of the ID and the reason of each call.
ID_HEADERS = ('joinid', 'jointid', 'callkey')
REASON_HEADERS = ('reason', 'exclusionreason', 'comment', 'comments', 'note', 'notes')
FILE_FORMAT_HELP = ('A CSV (comma, semicolon or tab separated) or Excel file with a JOIN_ID column (JOINT_ID or Call Key '
                    'are read too) and, optionally, a Reason column; a file of a single column without a header is a '
                    'list of JOIN_IDs.')
SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {LISTS_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    file_name TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    cdrs_json TEXT NOT NULL DEFAULT '[]',
    enabled INTEGER NOT NULL DEFAULT 1,
    call_count INTEGER NOT NULL DEFAULT 0,
    content_hash TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_scoring_exclusion_lists_name ON {LISTS_TABLE}(name COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS {CALLS_TABLE} (
    list_id INTEGER NOT NULL REFERENCES {LISTS_TABLE}(id) ON DELETE CASCADE,
    join_key TEXT NOT NULL,
    join_id TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (list_id, join_key)
);
CREATE INDEX IF NOT EXISTS idx_scoring_excluded_calls_key ON {CALLS_TABLE}(join_key);
CREATE TABLE IF NOT EXISTS {MATCHES_TABLE} (
    list_id INTEGER NOT NULL REFERENCES {LISTS_TABLE}(id) ON DELETE CASCADE,
    dataset_id INTEGER NOT NULL,
    revision TEXT NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0,
    row_count INTEGER NOT NULL DEFAULT 0,
    keys_hash TEXT NOT NULL DEFAULT '',
    keys_json TEXT NOT NULL DEFAULT '[]',
    checked_at TEXT NOT NULL,
    PRIMARY KEY (list_id, dataset_id)
);
"""


def ensure_tables(repository: Any) -> None:
    with repository.connection() as connection:
        connection.executescript(SCHEMA)


def _has_tables(connection: sqlite3.Connection) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (LISTS_TABLE,)).fetchone() is not None


def join_key(value: Any) -> str:
    """The JOIN_ID as calls are compared: trimmed, in capitals."""
    return str(value if value is not None else '').strip().upper()


def _key_sql(column: str) -> str:
    return f'UPPER(TRIM(CAST({column} AS TEXT)))'


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def row_condition(column: str, list_ids: Iterable[int]) -> tuple[str, list[int]]:
    """The SQL condition that keeps the rows whose JOIN_ID (``column``, quoted) is in none of the lists; rows without a
    JOIN_ID are kept."""
    ids = [int(value) for value in list_ids]
    marks = ', '.join('?' for _ in ids)
    return (f'({column} IS NULL OR {_key_sql(column)} NOT IN '
            f'(SELECT join_key FROM {CALLS_TABLE} WHERE list_id IN ({marks})))', ids)


def _identity(value: Any) -> str:
    return re.sub(r'[^a-z0-9]', '', str(value or '').casefold())


def _name(value: Any, limit: int = MAX_NAME_LENGTH) -> str:
    return ' '.join(str(value or '').split())[:limit]


def _content_hash(keys: Iterable[str]) -> str:
    return hashlib.sha256('\n'.join(sorted(keys)).encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------------------------------------------------
# Files


def read_calls_file(content: bytes, file_name: str) -> dict[str, Any]:
    """The calls of a file: each JOIN_ID once, with its reason, and what was left out (empty and repeated IDs)."""
    if not str(file_name or '').casefold().endswith(FILE_SUFFIXES):
        raise ValueError('Choose a CSV, TXT, TSV or Excel (XLSX or XLSM) file.')
    if len(content) > MAX_FILE_BYTES:
        raise ValueError(f'The file must not exceed {MAX_FILE_BYTES // (1024 * 1024)} MiB.')
    try:
        rows = _table(content, file_name)
    except Exception as exc:  # openpyxl and zipfile raise several kinds of errors for files that are not workbooks.
        raise ValueError('The file could not be read as a CSV or Excel file.') from exc
    rows = [[_cell(value) for value in row] for row in rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        raise ValueError('The file is empty.')
    header_index = next((index for index, row in enumerate(rows[:3])
                         if any(_identity(value) in ID_HEADERS for value in row)), None)
    if header_index is not None:
        header = [_identity(value) for value in rows[header_index]]
        id_index = next(index for index, value in enumerate(header) if value in ID_HEADERS)
        reason_index = next((index for index, value in enumerate(header) if value in REASON_HEADERS), None)
        column = rows[header_index][id_index]
        body = rows[header_index + 1:]
    elif all(sum(1 for value in row if value) <= 1 for row in rows):
        # One column without a header: every value is a JOIN_ID.
        id_index, reason_index, column = None, None, ''
        body = rows
    else:
        raise ValueError('The file needs a JOIN_ID column (JOINT_ID or Call Key are read too).')
    calls: dict[str, dict[str, str]] = {}
    empty = repeated = 0
    for row in body:
        value = next((item for item in row if item), '') if id_index is None else (row[id_index] if id_index < len(row) else '')
        key = join_key(value)
        if not key:
            empty += 1
            continue
        if key in calls:
            repeated += 1
            continue
        reason = row[reason_index] if reason_index is not None and reason_index < len(row) else ''
        calls[key] = {'join_id': value.strip(), 'reason': reason[:MAX_REASON_LENGTH]}
    if not calls:
        raise ValueError('The file has no JOIN_IDs.')
    if len(calls) > MAX_CALLS:
        raise ValueError(f'A list keeps up to {MAX_CALLS:,} calls; the file has {len(calls):,}.')
    return {'calls': list(calls.values()), 'column': column, 'empty': empty, 'repeated': repeated,
            'reasons': sum(1 for call in calls.values() if call['reason'])}


def template_csv() -> bytes:
    """An Excluded Calls file with its columns and one example row."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['JOIN_ID', 'Reason'])
    writer.writerow(['0x2A3496FFC886CCC9A7102540954CCE61', 'Test equipment failure'])
    return output.getvalue().encode('utf-8')


def calls_csv(calls: Iterable[dict[str, str]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['JOIN_ID', 'Reason'])
    for call in calls:
        writer.writerow([call['join_id'], call.get('reason') or ''])
    return output.getvalue().encode('utf-8')


# ---------------------------------------------------------------------------------------------------------------------
# Which lists apply to each CDR


def _revision(row: dict[str, Any]) -> str:
    """The processing of a CDR whose calls a list was matched to."""
    return f"{row['processed_at']}|{row['updated_at']}|{row['row_count']}"


class ExclusionScope:
    """The lists of a workspace, the CDRs each one applies to and the calls of each CDR they leave out."""

    def __init__(self, repository: Any = None, lists: Iterable[dict[str, Any]] = (), datasets: Iterable[Any] = (),
                 matches: Iterable[Any] = (), campaigns: dict[int, set[str]] | None = None) -> None:
        self._repository = repository
        self.lists = list(lists)
        self.datasets: dict[int, dict[str, Any]] = {}
        for row in datasets:
            kind = str(row['dataset_kind'] or '').casefold()
            self.datasets[int(row['id'])] = {
                'id': int(row['id']), 'file_name': str(row['file_name'] or ''), 'kind': kind,
                'nr_mode': dataset_nr_mode(kind, row['nr_mode'], row['file_name']) or '',
                'stage': dataset_cdr_stage(kind, row['cdr_stage'], row['file_name']) or '',
                'status': str(row['status'] or '').casefold(), 'processed_at': str(row['processed_at'] or ''),
                'updated_at': str(row['updated_at'] or ''), 'row_count': int(row['row_count'] or 0),
            }
        self.matches = {(int(row['list_id']), int(row['dataset_id'])): dict(row) for row in matches}
        self._campaigns = campaigns or {}
        self._targets = {item['id']: self._list_targets(item) for item in self.lists}

    def __bool__(self) -> bool:
        return bool(self.lists)

    def _list_targets(self, item: dict[str, Any]) -> set[int] | None:
        """The CDRs of a list assigned to some CDRs (with their Voice or Speech companions); None: every CDR."""
        if not item['cdrs']:
            return None
        names = {name.casefold() for name in item['cdrs']}
        assigned = [row for row in self.datasets.values() if row['file_name'].casefold() in names and row['kind'] in CDR_KINDS]
        targets = {row['id'] for row in assigned}
        for row in self.datasets.values():
            if row['kind'] in CALL_KINDS and row['id'] not in targets and any(
                    other['kind'] in CALL_KINDS and other['kind'] != row['kind'] and other['nr_mode'] == row['nr_mode']
                    and other['stage'] == row['stage']
                    and self._campaigns.get(other['id'], set()) & self._campaigns.get(row['id'], set())
                    for other in assigned):
                targets.add(row['id'])
        return targets

    def targets(self, item: dict[str, Any]) -> list[int]:
        """The CDRs a list applies to."""
        targets = self._targets.get(item['id'])
        return sorted(row['id'] for row in self.datasets.values()
                      if row['kind'] in CDR_KINDS and (targets is None or row['id'] in targets))

    def applies(self, item: dict[str, Any], dataset_id: int) -> bool:
        row = self.datasets.get(int(dataset_id))
        if row is None or row['kind'] not in CDR_KINDS:
            return False
        targets = self._targets.get(item['id'])
        return targets is None or int(dataset_id) in targets

    def lists_for(self, dataset_id: int, *, enabled_only: bool = True) -> list[dict[str, Any]]:
        return [item for item in self.lists if (item['enabled'] or not enabled_only) and self.applies(item, dataset_id)]

    def list_ids_for(self, dataset_id: int) -> list[int]:
        """The lists switched on whose calls the rows of a CDR leave out."""
        return [item['id'] for item in self.lists_for(dataset_id)]

    def revision(self, dataset_id: int) -> str:
        row = self.datasets.get(int(dataset_id))
        return _revision(row) if row else ''

    def match(self, item: dict[str, Any], dataset_id: int) -> dict[str, Any] | None:
        """The calls of a list found in a CDR at its current processing, if they were looked for."""
        found = self.matches.get((item['id'], int(dataset_id)))
        return found if found and found['revision'] == self.revision(dataset_id) else None

    def unmatched_lists(self, dataset_id: int) -> list[dict[str, Any]]:
        """The lists (switched on or off) whose calls are still to be looked for in a CDR."""
        return [item for item in self.lists_for(dataset_id, enabled_only=False) if self.match(item, dataset_id) is None]

    def pending(self, dataset_id: int) -> bool:
        """Whether the calls of a list switched on are still to be looked for in a CDR."""
        return any(self.match(item, dataset_id) is None for item in self.lists_for(dataset_id))

    def signature(self, dataset_id: int) -> list[list[str]]:
        """The lists switched on that leave calls of a CDR out (or may, while they are looked for), for the signature
        of the CDR: empty when none does, so the scorings of the CDR stay valid."""
        entries = []
        for item in self.lists_for(dataset_id):
            found = self.match(item, dataset_id)
            if found is None:
                entries.append([item['uid'], 'pending', item['content_hash']])
            elif int(found['call_count']):
                entries.append([item['uid'], str(found['keys_hash'])])
        return sorted(entries)

    def found_keys(self, item: dict[str, Any], dataset_ids: Iterable[int]) -> set[str]:
        """The JOIN_IDs of a list found in some CDRs."""
        ids = [int(value) for value in dataset_ids if self.match(item, value) is not None]
        if not ids or self._repository is None:
            return set()
        with self._repository.connection() as connection:
            rows = connection.execute(
                f'SELECT keys_json FROM {MATCHES_TABLE} WHERE list_id = ? AND dataset_id IN ({", ".join("?" for _ in ids)})',
                [item['id'], *ids]).fetchall()
        return {str(key) for row in rows for key in json.loads(row['keys_json'] or '[]')}

    def summary(self, dataset_ids: Iterable[int]) -> dict[str, Any] | None:
        """The calls the lists switched on leave out of a calculation of some CDRs; None when no list applies."""
        ids = [int(value) for value in dataset_ids]
        lists, all_keys, rows, waiting = [], set(), 0, set()
        for item in self.lists:
            if not item['enabled']:
                continue
            applied = [dataset_id for dataset_id in ids if self.applies(item, dataset_id)]
            if not applied:
                continue
            waiting.update(dataset_id for dataset_id in applied if self.match(item, dataset_id) is None)
            keys = self.found_keys(item, applied)
            list_rows = sum(int(found['row_count']) for dataset_id in applied
                            if (found := self.match(item, dataset_id)) is not None)
            all_keys |= keys
            rows += list_rows
            lists.append({'name': item['name'], 'calls': len(keys), 'rows': list_rows})
        if not lists:
            return None
        return {'lists': lists, 'calls': len(all_keys), 'rows': rows, 'pending_cdrs': len(waiting)}


def summary_warning(summary: dict[str, Any] | None) -> str:
    """What a scoring says about the calls it leaves out."""
    if not summary or not (summary['calls'] or summary['pending_cdrs']):
        return ''
    names = [f"“{item['name']}”" for item in summary['lists'] if item['calls'] or summary['pending_cdrs']]
    named = f"the list{'s' if len(names) > 1 else ''} " + (
        names[0] if len(names) == 1 else ', '.join(names[:-1]) + f' and {names[-1]}')
    waiting = f"{summary['pending_cdrs']} of its CDR{'s' if summary['pending_cdrs'] > 1 else ''}"
    if not summary['calls']:
        return (f'Excluded Calls: the calls of {named} are left out of this scoring; they are still being found in '
                f'{waiting}, so how many is not known yet.')
    text = (f"Excluded Calls: {summary['calls']:,} calls ({summary['rows']:,} CDR rows) are left out of this scoring by "
            f'{named}.')
    if summary['pending_cdrs']:
        text += f' More may be: they are still being found in {waiting}.'
    return text


def _campaigns(repository: Any) -> dict[int, set[str]]:
    try:
        with repository.connection() as connection:
            rows = connection.execute('SELECT dataset_id, campaigns_json FROM cdr_catalogues').fetchall()
    except sqlite3.OperationalError:
        return {}
    campaigns: dict[int, set[str]] = {}
    for row in rows:
        try:
            values = json.loads(row['campaigns_json'] or '[]')
        except (TypeError, ValueError):
            values = []
        campaigns[int(row['dataset_id'])] = {str(value).strip().casefold() for value in values or [] if str(value).strip()}
    return campaigns


def _list_item(row: Any) -> dict[str, Any]:
    try:
        cdrs = [str(name) for name in json.loads(row['cdrs_json'] or '[]') if str(name).strip()]
    except (TypeError, ValueError):
        cdrs = []
    return {'id': int(row['id']), 'uid': str(row['uid']), 'name': str(row['name']), 'file_name': str(row['file_name'] or ''),
            'reason': str(row['reason'] or ''), 'cdrs': cdrs, 'enabled': bool(row['enabled']),
            'call_count': int(row['call_count'] or 0), 'content_hash': str(row['content_hash'] or ''),
            'created_by': str(row['created_by'] or ''), 'created_at': str(row['created_at'] or ''),
            'updated_by': str(row['updated_by'] or ''), 'updated_at': str(row['updated_at'] or '')}


def load_scope(repository: Any, datasets: Iterable[Any] | None = None) -> ExclusionScope:
    """The lists of the workspace and their calls found in its CDRs (``datasets``: every dataset, when already read)."""
    with repository.connection() as connection:
        if not _has_tables(connection):
            return ExclusionScope(repository)
        lists = [_list_item(row) for row in connection.execute(
            f'SELECT * FROM {LISTS_TABLE} ORDER BY name COLLATE NOCASE, id').fetchall()]
        if not lists:
            return ExclusionScope(repository)
        matches = connection.execute(
            f'SELECT list_id, dataset_id, revision, call_count, row_count, keys_hash, checked_at FROM {MATCHES_TABLE}'
        ).fetchall()
    rows = list(datasets) if datasets is not None else repository.list_datasets()
    campaigns = _campaigns(repository) if any(item['cdrs'] for item in lists) else {}
    return ExclusionScope(repository, lists, rows, matches, campaigns)


# ---------------------------------------------------------------------------------------------------------------------
# Finding the calls of the lists in the CDRs


def _ready(repository: Any, scope: ExclusionScope) -> list[int]:
    return [dataset_id for dataset_id, row in scope.datasets.items()
            if row['kind'] in CDR_KINDS and row['status'] == 'ready' and repository.dataset_rows_table_exists(dataset_id)]


def has_pending(repository: Any) -> bool:
    """Whether the calls of a list are still to be looked for in a CDR of the workspace."""
    scope = load_scope(repository)
    return bool(scope) and any(scope.unmatched_lists(dataset_id) for dataset_id in _ready(repository, scope))


def _match_dataset(repository: Any, scope: ExclusionScope, dataset_id: int, lists: list[dict[str, Any]]) -> None:
    columns = repository.list_dataset_row_columns(dataset_id)
    column = resolve_column_name(columns, JOIN_COLUMN)
    ids = [item['id'] for item in lists]
    marks = ', '.join('?' for _ in ids)
    found: dict[str, int] = {}
    keys_of: dict[int, set[str]] = {list_id: set() for list_id in ids}
    with repository.connection() as connection:
        if column is not None:
            quoted = _quote(column)
            table = _quote(repository.dataset_rows_table_name(dataset_id))
            found = {str(row[0]): int(row[1]) for row in connection.execute(
                f'SELECT {_key_sql(quoted)}, COUNT(*) FROM {table} WHERE {quoted} IS NOT NULL AND {_key_sql(quoted)} IN '
                f'(SELECT join_key FROM {CALLS_TABLE} WHERE list_id IN ({marks})) GROUP BY 1', ids).fetchall()}
        if found:
            for list_id, key in connection.execute(
                    f'SELECT list_id, join_key FROM {CALLS_TABLE} WHERE list_id IN ({marks})', ids).fetchall():
                if key in found:
                    keys_of[int(list_id)].add(str(key))
        revision, now = scope.revision(dataset_id), local_now_iso()
        for list_id, keys in keys_of.items():
            ordered = sorted(keys)
            # A list deleted meanwhile is left out.
            connection.execute(
                f'INSERT OR REPLACE INTO {MATCHES_TABLE} (list_id, dataset_id, revision, call_count, row_count, keys_hash, '
                f'keys_json, checked_at) SELECT ?, ?, ?, ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM {LISTS_TABLE} WHERE id = ?)',
                (list_id, dataset_id, revision, len(ordered), sum(found[key] for key in ordered),
                 _content_hash(ordered) if ordered else '', json.dumps(ordered), now, list_id))


def match_pending(repository: Any, progress: Callable[[int, int, str], None] | None = None) -> int:
    """Look for the calls of the lists in the CDRs where they were not looked for at their current processing (one
    reading of each CDR); returns how many CDRs were read."""
    scope = load_scope(repository)
    if not scope:
        return 0
    work = [(dataset_id, lists) for dataset_id in _ready(repository, scope) if (lists := scope.unmatched_lists(dataset_id))]
    for index, (dataset_id, lists) in enumerate(work):
        if progress:
            progress(index, len(work), scope.datasets[dataset_id]['file_name'])
        _match_dataset(repository, scope, dataset_id, lists)
    with repository.connection() as connection:
        known = list(scope.datasets)
        connection.execute(f'DELETE FROM {MATCHES_TABLE} WHERE dataset_id NOT IN ({", ".join("?" for _ in known) or "NULL"})', known)
    return len(work)


# ---------------------------------------------------------------------------------------------------------------------
# Lists


def _cdr_names(names: Iterable[Any]) -> list[str]:
    return sorted({str(name).strip() for name in names or [] if str(name or '').strip()}, key=str.casefold)


def list_lists(repository: Any) -> list[dict[str, Any]]:
    """Every list with the CDRs it applies to and the calls of it found in each one."""
    scope = load_scope(repository)
    ready = set(_ready(repository, scope)) if scope else set()
    items = []
    for item in scope.lists:
        cdrs, found_keys, rows, waiting = [], set(), 0, 0
        targets = [dataset_id for dataset_id in scope.targets(item) if dataset_id in ready]
        for dataset_id in targets:
            found = scope.match(item, dataset_id)
            row = scope.datasets[dataset_id]
            if found is None:
                waiting += 1
            else:
                rows += int(found['row_count'])
            cdrs.append({'id': dataset_id, 'name': row['file_name'], 'kind': row['kind'],
                         'calls': None if found is None else int(found['call_count']),
                         'rows': None if found is None else int(found['row_count'])})
        found_keys = scope.found_keys(item, targets)
        assigned = {name.casefold() for name in item['cdrs']}
        missing = [name for name in item['cdrs']
                   if not any(row['file_name'].casefold() == name.casefold() for row in scope.datasets.values())]
        items.append({**{key: value for key, value in item.items() if key != 'content_hash'},
                      'all_cdrs': not item['cdrs'], 'missing_cdrs': missing,
                      'companions': [entry['name'] for entry in cdrs if entry['name'].casefold() not in assigned]
                      if item['cdrs'] else [],
                      'targets': cdrs, 'found_calls': len(found_keys), 'found_rows': rows, 'pending_cdrs': waiting,
                      'not_found': None if waiting else item['call_count'] - len(found_keys)})
    return items


def get_list(repository: Any, list_id: int) -> dict[str, Any] | None:
    return next((item for item in list_lists(repository) if item['id'] == int(list_id)), None)


def _check_name(connection: sqlite3.Connection, name: str, list_id: int | None = None) -> None:
    if not name:
        raise ValueError('Enter a name for the list of Excluded Calls.')
    clash = connection.execute(f'SELECT id FROM {LISTS_TABLE} WHERE name = ? COLLATE NOCASE', (name,)).fetchone()
    if clash and (list_id is None or int(clash['id']) != int(list_id)):
        raise ValueError(f'A list of Excluded Calls named "{name}" already exists.')


def create_list(repository: Any, *, name: str, calls: list[dict[str, str]], username: str, file_name: str = '',
                reason: str = '', cdrs: Iterable[str] = (), enabled: bool = True, created_by: str = '',
                created_at: str = '') -> dict[str, Any]:
    """Save a list of calls (each JOIN_ID once) assigned to some CDRs (none: every CDR)."""
    ensure_tables(repository)
    name = _name(name)
    unique: dict[str, dict[str, str]] = {}
    for call in calls:
        key = join_key(call.get('join_id'))
        if key and key not in unique:
            unique[key] = {'join_id': str(call['join_id']).strip()[:300], 'reason': str(call.get('reason') or '')[:MAX_REASON_LENGTH]}
    if not unique:
        raise ValueError('The list has no JOIN_IDs.')
    if len(unique) > MAX_CALLS:
        raise ValueError(f'A list keeps up to {MAX_CALLS:,} calls.')
    now = local_now_iso()
    with repository.connection() as connection:
        _check_name(connection, name)
        if connection.execute(f'SELECT COUNT(*) FROM {LISTS_TABLE}').fetchone()[0] >= MAX_LISTS:
            raise ValueError(f'A workspace keeps up to {MAX_LISTS} lists of Excluded Calls.')
        cursor = connection.execute(
            f'INSERT INTO {LISTS_TABLE} (uid, name, file_name, reason, cdrs_json, enabled, call_count, content_hash, '
            'created_by, created_at, updated_by, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (uuid.uuid4().hex, name, _name(file_name, 255), _name(reason, MAX_REASON_LENGTH),
             json.dumps(_cdr_names(cdrs), ensure_ascii=False), int(bool(enabled)), len(unique), _content_hash(unique),
             created_by or username, created_at or now, username, now))
        list_id = int(cursor.lastrowid)
        connection.executemany(f'INSERT INTO {CALLS_TABLE} (list_id, join_key, join_id, reason) VALUES (?, ?, ?, ?)',
                               [(list_id, key, call['join_id'], call['reason']) for key, call in unique.items()])
    return get_list(repository, list_id)


def update_list(repository: Any, list_id: int, username: str, *, name: str | None = None, reason: str | None = None,
                cdrs: Iterable[str] | None = None, enabled: bool | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rename a list, change its reason or CDRs, or switch it on or off; returns it before and after."""
    before = get_list(repository, list_id)
    if before is None:
        raise LookupError('The list of Excluded Calls no longer exists.')
    values = {
        'name': _name(name) if name is not None else before['name'],
        'reason': _name(reason, MAX_REASON_LENGTH) if reason is not None else before['reason'],
        'cdrs_json': json.dumps(_cdr_names(cdrs) if cdrs is not None else before['cdrs'], ensure_ascii=False),
        'enabled': int(bool(enabled)) if enabled is not None else int(before['enabled']),
    }
    with repository.connection() as connection:
        _check_name(connection, values['name'], list_id)
        connection.execute(
            f'UPDATE {LISTS_TABLE} SET name = ?, reason = ?, cdrs_json = ?, enabled = ?, updated_by = ?, updated_at = ? '
            'WHERE id = ?', (values['name'], values['reason'], values['cdrs_json'], values['enabled'], username,
                             local_now_iso(), int(list_id)))
    return before, get_list(repository, list_id)


def delete_list(repository: Any, list_id: int) -> dict[str, Any] | None:
    item = get_list(repository, list_id)
    if item is not None:
        with repository.connection() as connection:
            connection.execute(f'DELETE FROM {LISTS_TABLE} WHERE id = ?', (int(list_id),))
    return item


def list_calls(repository: Any, list_id: int, *, not_found: bool = False) -> list[dict[str, str]]:
    """The calls of a list (``not_found``: those found in none of its CDRs)."""
    ensure_tables(repository)
    with repository.connection() as connection:
        rows = connection.execute(f'SELECT join_key, join_id, reason FROM {CALLS_TABLE} WHERE list_id = ? ORDER BY rowid',
                                  (int(list_id),)).fetchall()
    calls = [{'key': str(row['join_key']), 'join_id': str(row['join_id']), 'reason': str(row['reason'] or '')} for row in rows]
    if not_found:
        scope = load_scope(repository)
        item = next((entry for entry in scope.lists if entry['id'] == int(list_id)), None)
        found = scope.found_keys(item, scope.targets(item)) if item else set()
        calls = [call for call in calls if call['key'] not in found]
    return [{'join_id': call['join_id'], 'reason': call['reason']} for call in calls]


# ---------------------------------------------------------------------------------------------------------------------
# Import / Export, transfers and backups


def export_document(repository: Any) -> bytes:
    """Every list with its calls, as a portable document (its CDRs by file name)."""
    lists = []
    for item in list_lists(repository):
        lists.append({'name': item['name'], 'file_name': item['file_name'], 'reason': item['reason'],
                      'cdrs': item['cdrs'], 'enabled': item['enabled'], 'created_by': item['created_by'],
                      'created_at': item['created_at'],
                      'calls': [[call['join_id'], call['reason']] for call in list_calls(repository, item['id'])]})
    return json.dumps({'format': EXCLUSIONS_FORMAT, 'version': EXCLUSIONS_VERSION, 'lists': lists},
                      ensure_ascii=False, indent=2).encode('utf-8')


def import_document(repository: Any, content: bytes | str, username: str) -> int:
    """Add the lists of a portable document, replacing those of the same name; returns how many it had."""
    document = json.loads(content)
    if not isinstance(document, dict) or document.get('format') != EXCLUSIONS_FORMAT:
        raise ValueError('The file is not a DriveTest Analyzer Scoring Excluded Calls export.')
    if document.get('version') != EXCLUSIONS_VERSION:
        raise ValueError('Unsupported Scoring Excluded Calls version.')
    entries = [entry for entry in document.get('lists') or [] if isinstance(entry, dict) and _name(entry.get('name'))]
    ensure_tables(repository)
    for entry in entries:
        calls = [{'join_id': str(call[0]), 'reason': str(call[1]) if len(call) > 1 else ''}
                 for call in entry.get('calls') or [] if isinstance(call, list) and call]
        name = _name(entry['name'])
        with repository.connection() as connection:
            connection.execute(f'DELETE FROM {LISTS_TABLE} WHERE name = ? COLLATE NOCASE', (name,))
        create_list(repository, name=name, calls=calls, username=username, file_name=str(entry.get('file_name') or ''),
                    reason=str(entry.get('reason') or ''), cdrs=entry.get('cdrs') or [],
                    enabled=bool(entry.get('enabled', True)), created_by=str(entry.get('created_by') or ''),
                    created_at=str(entry.get('created_at') or ''))
    return len(entries)


# ---------------------------------------------------------------------------------------------------------------------
# Routes


def install_scoring_exclusion_routes(core: Any) -> None:
    """The Excluded Calls panel of Scoring & GAP Analysis: anyone with the workspace sees the lists, and those who edit
    the Scoring Methodologies import, change and delete them (each action recorded in App Events)."""
    from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
    from fastapi.responses import JSONResponse, Response

    from src.modules.app_event_details import changed_values

    no_store = {'Cache-Control': 'no-store'}

    def cdr_options(repository: Any) -> list[dict[str, Any]]:
        rows = [row for row in repository.list_datasets()
                if str(row['dataset_kind'] or '').casefold() in CDR_KINDS and str(row['status'] or '').casefold() == 'ready']
        catalogues = repository.cdr_catalogues_by_dataset([int(row['id']) for row in rows])
        return [{'id': int(row['id']), 'name': str(row['file_name'] or ''), 'kind': str(row['dataset_kind']).casefold(),
                 'nr_mode': dataset_nr_mode(row['dataset_kind'], row['nr_mode'], row['file_name']) or '',
                 'campaigns': list(catalogues.get(int(row['id']), {}).get('campaigns') or [])}
                for row in sorted(rows, key=lambda item: str(item['file_name'] or '').casefold())]

    def payload(repository: Any, user: Any) -> dict[str, Any]:
        return {'lists': list_lists(repository), 'cdrs': cdr_options(repository),
                'can_edit': user.role in {'user-editor', 'admin', 'super-admin'},
                'format_help': FILE_FORMAT_HELP, 'max_calls': MAX_CALLS}

    def event_details(item: dict[str, Any]) -> dict[str, Any]:
        return {'list': item['name'], 'file': item['file_name'], 'calls': item['call_count'],
                'cdrs': item['cdrs'] or 'All CDRs', 'enabled': item['enabled'], 'reason': item['reason']}

    async def read_upload(upload: UploadFile) -> tuple[bytes, str]:
        try:
            content = await upload.read(MAX_FILE_BYTES + 1)
        finally:
            await upload.close()
        return content, str(upload.filename or '')

    @core.app.get('/api/scoring/excluded-calls')
    def excluded_calls_lists(user=Depends(core.current_user)) -> JSONResponse:
        return JSONResponse(payload(core.scoring_repository(user), user), headers=no_store)

    @core.app.get('/api/scoring/excluded-calls/template')
    def excluded_calls_template(user=Depends(core.current_user)) -> Response:
        core.scoring_repository(user)
        return Response(template_csv(), media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="scoring-excluded-calls-template.csv"'})

    @core.app.post('/api/scoring/excluded-calls/check')
    async def check_excluded_calls_file(file: UploadFile = File(...), user=Depends(core.config_editor_user)) -> JSONResponse:
        core.scoring_repository(user)
        content, file_name = await read_upload(file)
        try:
            read = read_calls_file(content, file_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({'calls': len(read['calls']), 'column': read['column'], 'repeated': read['repeated'],
                             'empty': read['empty'], 'reasons': read['reasons'],
                             'sample': [call['join_id'] for call in read['calls'][:5]]}, headers=no_store)

    @core.app.post('/api/scoring/excluded-calls')
    async def import_excluded_calls(
        file: UploadFile = File(...), name: str = Form(''), reason: str = Form(''), cdrs: list[str] = Form(default=[]),
        user=Depends(core.config_editor_user),
    ) -> JSONResponse:
        repository = core.scoring_repository(user)
        content, file_name = await read_upload(file)
        try:
            read = read_calls_file(content, file_name)
            item = create_list(repository, name=name or re.sub(r'\.[^.]+$', '', file_name), calls=read['calls'],
                               username=user.username, file_name=file_name, reason=reason, cdrs=cdrs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        repository.add_log(user.username, 'import_scoring_excluded_calls', json.dumps({
            **event_details(item), 'repeated_ids_skipped': read['repeated'], 'empty_ids_skipped': read['empty']}))
        # The calls are looked for in the CDRs in the background, before the Scoring History indexes them.
        core.queue_scoring_history(repository)
        return JSONResponse({**payload(repository, user), 'imported': item}, headers=no_store)

    @core.app.put('/api/scoring/excluded-calls/{list_id}')
    async def update_excluded_calls(list_id: int, request: Request, user=Depends(core.config_editor_user)) -> JSONResponse:
        repository = core.scoring_repository(user)
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError('Send the changes of the list.')
            before, after = update_list(
                repository, list_id, user.username, name=body.get('name'), reason=body.get('reason'),
                cdrs=body['cdrs'] if isinstance(body.get('cdrs'), list) else None,
                enabled=bool(body['enabled']) if 'enabled' in body else None)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        changes = changed_values({key: before[key] for key in ('name', 'reason', 'cdrs', 'enabled')},
                                 {key: after[key] for key in ('name', 'reason', 'cdrs', 'enabled')})
        if changes:
            repository.add_log(user.username, 'update_scoring_excluded_calls', json.dumps({
                'list': after['name'], 'calls': after['call_count'], 'changes': changes}))
            core.queue_scoring_history(repository)
        return JSONResponse(payload(repository, user), headers=no_store)

    @core.app.delete('/api/scoring/excluded-calls/{list_id}')
    def delete_excluded_calls(list_id: int, user=Depends(core.config_editor_user)) -> JSONResponse:
        repository = core.scoring_repository(user)
        item = delete_list(repository, list_id)
        if item is None:
            raise HTTPException(status_code=404, detail='The list of Excluded Calls no longer exists.')
        repository.add_log(user.username, 'delete_scoring_excluded_calls', json.dumps(event_details(item)))
        # The CDRs it left calls out of are indexed again in the Scoring History.
        core.queue_scoring_history(repository)
        return JSONResponse(payload(repository, user), headers=no_store)

    @core.app.get('/api/scoring/excluded-calls/{list_id}/calls')
    def download_excluded_calls(list_id: int, not_found: bool = False, user=Depends(core.current_user)) -> Response:
        repository = core.scoring_repository(user)
        item = get_list(repository, list_id)
        if item is None:
            raise HTTPException(status_code=404, detail='The list of Excluded Calls no longer exists.')
        calls = list_calls(repository, list_id, not_found=not_found)
        repository.add_log(user.username, 'download_scoring_excluded_calls', json.dumps({
            'list': item['name'], 'calls': len(calls), 'only_not_found': not_found}))
        stem = re.sub(r'[^A-Za-z0-9._-]+', '_', item['name']).strip('_') or 'excluded-calls'
        return Response(calls_csv(calls), media_type='text/csv', headers={
            'Content-Disposition': f'attachment; filename="{stem}{"_not-found" if not_found else ""}.csv"'})
