"""Columnar copy of the CDR rows: one Parquet file per CDR, read with DuckDB.

SQLite stays the store of the CDR rows. Every ready CDR (Data, Voice or Speech) of a workspace is copied in the
background to ``.cdr-store/<kind>/<dataset id>.parquet`` beside the workspace database, with its SQLite row id, its
dataset id and its NR Mode, and copied again when its rows change: triggers on its table count every insert, update
and delete, so no writer has to tell. ``.cdr-store/catalog.duckdb`` holds one view per CDR type (``cdr_data``,
``cdr_voice``, ``cdr_speech``) over the CDRs the combined tables include, for tools such as Tableau.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable

import pandas as pd

STORE_FOLDER = '.cdr-store'
STORE_VERSION = 2
CDR_KINDS = ('data', 'voice', 'speech')
VERSIONS_TABLE = 'cdr_store_versions'
TABLE_TITLES = {VERSIONS_TABLE: 'CDR Store Versions'}
CATALOG_FILE = 'catalog.duckdb'
CATALOG_STATE_FILE = 'catalog.json'
# The columns the copy adds to the columns of the CDR.
ROWID, DATASET_ID, NR_MODE = '__rowid', '__dataset_id', '__nr_mode'
# A column with text and numbers keeps its text, and its integers and reals in companion columns, so it is read back
# with the Python type of each value.
INT_PREFIX, REAL_PREFIX = '__int__', '__real__'
READ_BATCH_ROWS = 50_000
# The copy of a CDR waits while the disk would keep less than this free after it: the Parquet file takes from 130 to
# 490 bytes per row, and DuckDB may spill as much while it writes.
FREE_SPACE_MARGIN = 1024 ** 3
BYTES_PER_ROW_ESTIMATE = 1_000
SYNC_PRIORITY = (9, 1)
STORE_IDLE_SECONDS = 2 * 60
# The application copies the CDRs by itself (the tests copy them when they need it).
AUTOMATIC = True


def quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def store_root(database_path: Any) -> Path:
    """The folder of the columnar copy of a workspace, beside its database."""
    return Path(str(database_path)).resolve().parent / STORE_FOLDER


def cdr_file(root: Path, kind: str, dataset_id: int) -> Path:
    return root / kind / f'{int(dataset_id)}.parquet'


def manifest_file(root: Path, kind: str, dataset_id: int) -> Path:
    return root / kind / f'{int(dataset_id)}.json'


def read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        manifest = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return manifest if isinstance(manifest, dict) and manifest.get('version') == STORE_VERSION else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False), encoding='utf-8')
    os.replace(temporary, path)


# ---------------------------------------------------------------------------------------------------------------------
# The changes of the rows of a CDR: a counter per CDR that the triggers of its table raise.

def ensure_versions_table(connection: sqlite3.Connection) -> None:
    connection.execute(f'CREATE TABLE IF NOT EXISTS {VERSIONS_TABLE} '
                       '(dataset_id INTEGER PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0)')


def ensure_change_triggers(connection: sqlite3.Connection, dataset_id: int) -> None:
    """Count every insert, update and delete of the rows of a CDR (a recreated table loses its triggers: the copy
    adds them again, and the new processing date of the CDR already tells its rows changed)."""
    dataset_id = int(dataset_id)
    table = quote(f'dataset_rows_{dataset_id}')
    connection.execute(f'INSERT OR IGNORE INTO {VERSIONS_TABLE} (dataset_id, version) VALUES (?, 0)', (dataset_id,))
    for event in ('INSERT', 'UPDATE', 'DELETE'):
        connection.execute(
            f'CREATE TRIGGER IF NOT EXISTS {quote(f"cdr_store_{dataset_id}_{event.lower()}")} AFTER {event} ON {table} '
            f'BEGIN UPDATE {VERSIONS_TABLE} SET version = version + 1 WHERE dataset_id = {dataset_id}; END')


def _versions(connection: sqlite3.Connection) -> dict[int, int]:
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (VERSIONS_TABLE,)).fetchone():
        return {}
    return {int(row[0]): int(row[1]) for row in connection.execute(f'SELECT dataset_id, version FROM {VERSIONS_TABLE}')}


def _table_columns(connection: sqlite3.Connection, dataset_id: int) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info({quote(f"dataset_rows_{int(dataset_id)}")})')]


def _ready_cdrs(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """The ready Data, Voice and Speech CDRs of the workspace with a table of rows."""
    tables = {str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'dataset_rows_%'")}
    rows = connection.execute(
        'SELECT d.id, d.file_name, p.status, p.dataset_kind, p.nr_mode, p.processed_at, p.normalization_version, p.row_count '
        'FROM datasets d JOIN dataset_profiles p ON p.dataset_id = d.id').fetchall()
    return {
        int(row[0]): {'id': int(row[0]), 'file_name': str(row[1] or ''), 'kind': str(row[3] or '').casefold(),
                      'nr_mode': str(row[4] or '').upper(), 'processed_at': str(row[5] or ''),
                      'normalization_version': int(row[6] or 1), 'row_count': int(row[7] or 0)}
        for row in rows
        if str(row[2] or '').casefold() == 'ready' and str(row[3] or '').casefold() in CDR_KINDS
        and f'dataset_rows_{int(row[0])}' in tables
    }


def revision(cdr: dict[str, Any], columns: list[str], version: int) -> str:
    """What the copy of a CDR depends on: its processing, its columns and the changes of its rows."""
    return json.dumps({
        'v': STORE_VERSION, 'kind': cdr['kind'], 'nr_mode': cdr['nr_mode'], 'processed_at': cdr['processed_at'],
        'normalization_version': cdr['normalization_version'], 'row_count': cdr['row_count'], 'columns': columns,
        'version': version,
    }, sort_keys=True, ensure_ascii=False)


def store_changes(database_path: Any) -> dict[str, Any]:
    """The CDRs whose copy is missing or out of date, and the copies of CDRs that are gone."""
    root = store_root(database_path)
    with sqlite3.connect(database_path, timeout=30) as connection:
        cdrs = _ready_cdrs(connection)
        versions = _versions(connection)
        pending = []
        for dataset_id, cdr in sorted(cdrs.items()):
            manifest = read_manifest(manifest_file(root, cdr['kind'], dataset_id))
            current = revision(cdr, _table_columns(connection, dataset_id), versions.get(dataset_id, 0))
            if manifest is None or manifest.get('revision') != current or not cdr_file(root, cdr['kind'], dataset_id).is_file():
                pending.append(cdr)
    orphans = [path for kind in CDR_KINDS for path in (root / kind).glob('*.json')
               if not path.stem.isdigit() or int(path.stem) not in cdrs or cdrs[int(path.stem)]['kind'] != kind]
    return {'pending': pending, 'orphans': orphans, 'cdrs': cdrs}


# ---------------------------------------------------------------------------------------------------------------------
# Copying one CDR.

def _column_types(connection: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, str]:
    """The type of each column over all its values, in one pass: BIGINT when every value is an integer, DOUBLE when
    every value is a number, VARCHAR when every value is text (or it has no value), and MIXED:I, MIXED:R or MIXED:IR
    when it has text and integers, reals or both."""
    flags = ', '.join(
        f"MAX(typeof({quote(column)}) IN ('text', 'blob')) * 4 + MAX(typeof({quote(column)}) = 'real') * 2 "
        f"+ MAX(typeof({quote(column)}) = 'integer')" for column in columns)
    row = connection.execute(f'SELECT {flags} FROM {quote(table)}').fetchone() if columns else ()
    types = {}
    for column, flag in zip(columns, row):
        flag = int(flag or 0)
        if flag & 4 and flag & 3:
            types[column] = 'MIXED:' + ('I' if flag & 1 else '') + ('R' if flag & 2 else '')
        else:
            types[column] = 'VARCHAR' if flag & 4 or not flag else ('DOUBLE' if flag & 2 else 'BIGINT')
    return types


def _stored_columns(columns: list[str], types: dict[str, str]) -> list[tuple[str, str, str]]:
    """The columns of the Parquet file of a CDR: (name, SQLite expression, type) for each column, and for a column with
    text and numbers its text, integers and reals apart."""
    stored = []
    for column in columns:
        source, column_type = quote(column), types[column]
        if column_type.startswith('MIXED:'):
            stored.append((column, f"CASE WHEN typeof({source}) IN ('text', 'blob') THEN CAST({source} AS TEXT) END", 'VARCHAR'))
            if 'I' in column_type:
                stored.append((INT_PREFIX + column, f"CASE WHEN typeof({source}) = 'integer' THEN {source} END", 'BIGINT'))
            if 'R' in column_type:
                stored.append((REAL_PREFIX + column, f"CASE WHEN typeof({source}) = 'real' THEN {source} END", 'DOUBLE'))
        else:
            stored.append((column, f'CAST({source} AS TEXT)' if column_type == 'VARCHAR' else source, column_type))
    return stored


def required_space(row_count: int) -> int:
    return int(row_count) * BYTES_PER_ROW_ESTIMATE + FREE_SPACE_MARGIN


def free_space(path: Path) -> int:
    from src.modules.disk_space import available_disk_space

    path.mkdir(parents=True, exist_ok=True)
    return available_disk_space(path)


class NotEnoughSpace(RuntimeError):
    def __init__(self, needed: int, free: int) -> None:
        super().__init__(f'{needed / 1024 ** 3:.1f} GB of free disk space needed, {free / 1024 ** 3:.1f} GB free')
        self.needed, self.free = needed, free


def export_rows(connection: sqlite3.Connection, dataset_id: int, nr_mode: str, columns: list[str], types: dict[str, str],
                target: Path, spill: Path, should_stop: Callable[[], bool] = lambda: False) -> int | None:
    """Write the rows of a CDR table, read in batches through ``connection``, to the Parquet file ``target`` with the
    given column types; returns how many rows it wrote, or None when it stopped."""
    import duckdb

    table = f'dataset_rows_{int(dataset_id)}'
    stored = _stored_columns(columns, types)
    duck = duckdb.connect(config={'memory_limit': '2GB', 'threads': 2, 'temp_directory': str(spill)})
    try:
        duck.execute(f'CREATE TABLE cdr ({quote(ROWID)} BIGINT, {quote(DATASET_ID)} BIGINT, {quote(NR_MODE)} VARCHAR'
                     + ''.join(f', {quote(name)} {column_type}' for name, _expression, column_type in stored) + ')')
        selected = ''.join(f', {expression}' for _name, expression, _column_type in stored)
        last = connection.execute(f'SELECT MAX(rowid) FROM {quote(table)}').fetchone()[0] or 0
        for low in range(0, int(last), READ_BATCH_ROWS):
            if should_stop():
                return None
            rows = connection.execute(f'SELECT rowid{selected} FROM {quote(table)} WHERE rowid > ? AND rowid <= ? ORDER BY rowid',
                                      (low, low + READ_BATCH_ROWS)).fetchall()
            if not rows:
                continue
            values = list(zip(*rows))
            frame = pd.DataFrame({
                ROWID: pd.Series(values[0], dtype='int64'), DATASET_ID: int(dataset_id), NR_MODE: nr_mode or None,
                **{name: pd.Series(column_values, dtype={'BIGINT': 'Int64', 'DOUBLE': 'float64'}.get(column_type, 'object'))
                   for (name, _expression, column_type), column_values in zip(stored, values[1:])},
            })
            duck.register('chunk', frame)
            duck.execute('INSERT INTO cdr BY NAME SELECT * FROM chunk')
            duck.unregister('chunk')
        literal = str(target).replace("'", "''")
        duck.execute(f"COPY cdr TO '{literal}' (FORMAT parquet, COMPRESSION zstd)")
        return int(duck.execute('SELECT COUNT(*) FROM cdr').fetchone()[0])
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    finally:
        duck.close()


def write_cdr(repository: Any, cdr: dict[str, Any], should_stop: Callable[[], bool] = lambda: False) -> dict[str, Any] | None:
    """Copy the rows of one CDR to its Parquet file, from one consistent snapshot of its table; returns its manifest,
    or None when it stopped. Raises NotEnoughSpace when the disk would keep too little room."""
    database_path = repository.db_path
    root = store_root(database_path)
    dataset_id, kind = int(cdr['id']), str(cdr['kind'])
    folder = root / kind
    folder.mkdir(parents=True, exist_ok=True)
    needed, free = required_space(cdr['row_count']), free_space(folder)
    if free < needed:
        raise NotEnoughSpace(needed, free)
    table = f'dataset_rows_{dataset_id}'
    target = cdr_file(root, kind, dataset_id)
    temporary = folder / f'.{dataset_id}.{os.getpid()}.parquet.tmp'
    spill = root / '.tmp'
    spill.mkdir(parents=True, exist_ok=True)
    with repository.connection() as writer:
        ensure_versions_table(writer)
        ensure_change_triggers(writer, dataset_id)
    with sqlite3.connect(database_path, timeout=30) as connection:
        # Every read below sees the same snapshot of the CDR (the database is in WAL mode).
        connection.execute('BEGIN')
        try:
            ready = _ready_cdrs(connection).get(dataset_id)
            if ready is None:
                return None
            columns = _table_columns(connection, dataset_id)
            current = revision(ready, columns, _versions(connection).get(dataset_id, 0))
            if any(column.casefold() in {ROWID, DATASET_ID, NR_MODE} or column.startswith((INT_PREFIX, REAL_PREFIX))
                   for column in columns):
                raise ValueError(f'The CDR {ready["file_name"]} has a column named like the columns the copy adds.')
            types = _column_types(connection, table, columns)
            rows_written = export_rows(connection, dataset_id, ready['nr_mode'], columns, types, temporary, spill, should_stop)
            if rows_written is None:
                return None
        finally:
            connection.rollback()
    os.replace(temporary, target)
    manifest = {
        'version': STORE_VERSION, 'dataset_id': dataset_id, 'kind': kind, 'file_name': ready['file_name'],
        'revision': current, 'rows': rows_written, 'columns': [[column, types[column]] for column in columns],
        'written_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    _write_json(manifest_file(root, kind, dataset_id), manifest)
    return manifest


def remove_copy(manifest_path: Path) -> None:
    """Remove the copy of a CDR that is gone (or now of another type)."""
    manifest_path.with_suffix('.parquet').unlink(missing_ok=True)
    manifest_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------------------------------------------------
# The catalog: one view per CDR type over the copies of the CDRs the combined tables include.

def _view_sql(kind: str, manifests: list[dict[str, Any]], root: Path) -> str:
    view = quote(f'cdr_{kind}')
    if not manifests:
        return (f'CREATE VIEW {view} AS SELECT CAST(NULL AS BIGINT) AS dataset_id, CAST(NULL AS BIGINT) AS source_row_id, '
                'CAST(NULL AS VARCHAR) AS "NR_Mode" WHERE false')
    types: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    companions: set[str] = set()
    for manifest in manifests:
        for column, column_type in manifest['columns']:
            identity = column.casefold()
            names.setdefault(identity, column)
            types.setdefault(identity, set()).add('VARCHAR' if column_type.startswith('MIXED:') else column_type)
            if column_type.startswith('MIXED:'):
                companions.update(prefix + column for prefix, part in ((INT_PREFIX, 'I'), (REAL_PREFIX, 'R'))
                                  if part in column_type)
    nr_mode = names.pop('nr_mode', None)
    # The view names its own dataset and row id columns.
    for identity in ('dataset_id', 'source_row_id'):
        names.pop(identity, None)
    for identity in ('nr_mode', 'dataset_id', 'source_row_id'):
        types.pop(identity, None)
    selected = [f'{quote(DATASET_ID)} AS dataset_id', f'{quote(ROWID)} AS source_row_id']
    for identity, column in names.items():
        column_types = types[identity]
        common = column_types.pop() if len(column_types) == 1 else ('DOUBLE' if column_types <= {'BIGINT', 'DOUBLE'} else 'VARCHAR')
        parts = [f'CAST({quote(name)} AS VARCHAR)' for name in (INT_PREFIX + column, REAL_PREFIX + column) if name in companions]
        value = f'COALESCE({quote(column)}, {", ".join(parts)})' if parts else quote(column)
        selected.append(f'CAST({value} AS {common}) AS {quote(column)}')
    # The NR Mode of a row: the CDR's own NR Mode column, or the NR Mode of the CDR.
    selected.append(f'COALESCE(CAST({quote(nr_mode)} AS VARCHAR), {quote(NR_MODE)}) AS "NR_Mode"' if nr_mode
                    else f'{quote(NR_MODE)} AS "NR_Mode"')
    files = ', '.join("'" + str(cdr_file(root, kind, manifest['dataset_id'])).replace("'", "''") + "'" for manifest in manifests)
    return f'CREATE VIEW {view} AS SELECT {", ".join(selected)} FROM read_parquet([{files}], union_by_name = true)'


def _catalog_inputs(database_path: Any, included: dict[str, set[int]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """The copies each view reads and the signature of the catalog they make."""
    root = store_root(database_path)
    manifests = {kind: [manifest for dataset_id in sorted(included.get(kind, ()))
                        if (manifest := read_manifest(manifest_file(root, kind, dataset_id)))
                        and cdr_file(root, kind, dataset_id).is_file()] for kind in CDR_KINDS}
    signature = {'version': STORE_VERSION, 'root': str(root),
                 'cdrs': {kind: [[manifest['dataset_id'], manifest['revision']] for manifest in items]
                          for kind, items in manifests.items()}}
    return manifests, signature


def catalog_outdated(database_path: Any, included: dict[str, set[int]]) -> bool:
    root = store_root(database_path)
    try:
        written = json.loads((root / CATALOG_STATE_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        written = None
    return written != _catalog_inputs(database_path, included)[1] or not (root / CATALOG_FILE).is_file()


def write_catalog(database_path: Any, included: dict[str, set[int]]) -> bool:
    """Write the catalog when the copies it reads changed (or the workspace moved); returns whether it was written."""
    import duckdb

    if not catalog_outdated(database_path, included):
        return False
    root = store_root(database_path)
    manifests, signature = _catalog_inputs(database_path, included)
    # A workspace without CDRs gets its catalog with its first copy.
    if not any(manifests.values()) and not (root / CATALOG_FILE).is_file():
        return False
    state_path = root / CATALOG_STATE_FILE
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f'.{CATALOG_FILE}.{os.getpid()}.tmp'
    temporary.unlink(missing_ok=True)
    catalog = duckdb.connect(str(temporary))
    try:
        for kind in CDR_KINDS:
            catalog.execute(_view_sql(kind, manifests[kind], root))
    finally:
        catalog.close()
    os.replace(temporary, root / CATALOG_FILE)
    _write_json(state_path, signature)
    return True


# ---------------------------------------------------------------------------------------------------------------------
# Copying in the background: one CDR at a time, after the other background work and while the server is idle.

_store_jobs: dict[str, dict[str, Any]] = {}
_store_jobs_guard = Lock()
# The CDR each workspace waits for disk space to copy, logged once in the App Events until it is copied.
_waiting_logged: dict[str, str] = {}


def _workspace_key(path: Any) -> str:
    return str(Path(str(path)).resolve())


def store_job(database_path: Any) -> dict[str, Any] | None:
    with _store_jobs_guard:
        job = _store_jobs.get(_workspace_key(database_path))
        return dict(job) if job else None


def included_cdrs(repository: Any) -> dict[str, set[int]]:
    """The ready CDRs of each type the combined tables include (In Combined), which the views read."""
    from src.modules.cdr_stage import combined_inclusion

    included: dict[str, set[int]] = {kind: set() for kind in CDR_KINDS}
    for dataset_id, item in combined_inclusion(repository).items():
        if item['included'] and item['kind'] in included:
            included[item['kind']].add(int(dataset_id))
    return included


def sync_step(repository: Any, included: Callable[[], dict[str, set[int]]], should_stop: Callable[[], bool],
              job: dict[str, Any]) -> bool:
    """Copy the next CDR that needs it (removing the copies of the CDRs that are gone first); returns whether more
    remain. The catalog follows once every copy is up to date."""
    changes = store_changes(repository.db_path)
    for orphan in changes['orphans']:
        remove_copy(orphan)
        with _store_jobs_guard:
            job['removed'] += 1
    pending = changes['pending']
    with _store_jobs_guard:
        job.update(total=max(job['total'], job['done'] + len(pending)))
    if pending:
        cdr = pending[0]
        with _store_jobs_guard:
            job.update(current=cdr['file_name'])
        key = _workspace_key(repository.db_path)
        try:
            manifest = write_cdr(repository, cdr, should_stop)
        except NotEnoughSpace as exc:
            with _store_jobs_guard:
                job.update(waiting=str(exc))
                first = _waiting_logged.get(key) != cdr['file_name']
                _waiting_logged[key] = cdr['file_name']
            if first:
                repository.try_add_log('system', 'cdr_store_waiting_for_space', json.dumps({
                    'file': cdr['file_name'], 'needed_mb': exc.needed // 1024 ** 2, 'free_mb': exc.free // 1024 ** 2,
                }))
            return False
        if manifest is None:
            return False
        with _store_jobs_guard:
            job.update(done=job['done'] + 1, waiting='')
            job['written'].append(cdr['file_name'])
            _waiting_logged.pop(key, None)
        # The next step copies the next CDR, or writes the catalog once none is left.
        return True
    if write_catalog(repository.db_path, included()):
        job['catalog'] = True
    return False


def start_store_sync(repository: Any, submit: Callable[[Callable[[], None]], Any],
                     included: Callable[[], dict[str, set[int]]], should_stop: Callable[[], bool] = lambda: False) -> dict[str, Any]:
    """Queue the copy of the workspace's new or changed CDRs, unless it is already queued or running: one CDR per
    background task, so the other background work goes on between them."""
    key = _workspace_key(repository.db_path)
    with _store_jobs_guard:
        current = _store_jobs.get(key)
        if current and current['status'] in {'queued', 'processing'}:
            return dict(current)
        job = {'status': 'queued', 'queued_at': time.time(), 'started_at': None, 'finished_at': None, 'error': '',
               'done': 0, 'total': 0, 'current': '', 'waiting': '', 'written': [], 'removed': 0, 'catalog': False}
        _store_jobs[key] = job

    def finish(status: str, error: str = '') -> None:
        with _store_jobs_guard:
            # A copy that waits for disk space keeps the name of the CDR it waits to copy.
            job.update(status=status, error=error, finished_at=time.time(), current=job['current'] if job['waiting'] else '')
        if job['written'] or job['removed']:
            repository.try_add_log('system', 'cdr_store_synced', json.dumps({
                'written': job['written'], 'removed': job['removed'], 'catalog': job['catalog'],
                'seconds': round(time.time() - (job['started_at'] or time.time()), 1),
            }, ensure_ascii=False))

    def run() -> None:
        with _store_jobs_guard:
            job.update(status='processing', started_at=job['started_at'] or time.time())
        try:
            more = sync_step(repository, included, should_stop, job)
        except Exception as exc:  # The next idle period tries again.
            finish('failed', str(exc))
            return
        if more and not should_stop():
            submit(run)
        else:
            finish('waiting' if job['waiting'] else 'ready')

    submit(run)
    with _store_jobs_guard:
        return dict(job)


def store_tasks(database_path: Any, task_id: str) -> list[dict[str, Any]]:
    """The copy among the background tasks, while it runs, waits for disk space or failed."""
    job = store_job(database_path)
    if not job or (job['status'] == 'ready' and time.time() - (job['finished_at'] or 0) > 5):
        return []
    if job['status'] == 'ready' and not job['written']:
        return []
    if job['status'] == 'failed':
        detail = job['error']
    elif job['waiting']:
        detail = f"Waiting for free disk space to copy {job['current'] or 'the next CDR'}: {job['waiting']}"
    elif job['current']:
        detail = f"Copying {job['current']} ({job['done'] + 1} of {job['total']})"
    else:
        detail = 'Copying the new or changed CDRs to the columnar store'
    return [{
        'id': task_id, 'label': 'CDR columnar copy', 'detail': detail,
        'status': 'queued' if job['status'] == 'waiting' else job['status'],
        'progress': round(100 * job['done'] / job['total']) if job['total'] else None,
        'queued_at': job['queued_at'], 'started_at': job['started_at'], 'completed_at': job['finished_at'],
    }]


def queue_store_sync(repository: Any, scheduler: Any, should_stop: Callable[[], bool] = lambda: False) -> dict[str, Any] | None:
    """Copy the new or changed CDRs of a workspace after the other background work: when a CDR finishes processing and
    when the workspace is opened."""
    if not AUTOMATIC:
        return None
    return start_store_sync(repository, lambda run: scheduler.submit_ordered(run, priority=SYNC_PRIORITY),
                            lambda: included_cdrs(repository), should_stop)


def install_cdr_store(core: Any) -> None:
    """Copy the CDRs of the active workspace when the server is idle, and show the copy among the background tasks."""

    def active_repository() -> Any | None:
        workspace = core.active_workspace
        if not workspace:
            return None
        return core.Repository(workspace.database_path, global_db_path=core.repository.global_db_path,
                               workspace_registry_db_path=core.workspace_registry.registry_path)

    def copy_when_idle() -> None:
        repository = active_repository()
        if repository is None or not AUTOMATIC:
            return
        job = store_job(repository.db_path)
        if job and job['status'] in {'queued', 'processing'}:
            return
        changes = store_changes(repository.db_path)
        if changes['pending'] or changes['orphans'] or catalog_outdated(repository.db_path, included_cdrs(repository)):
            queue_store_sync(repository, core.BACKGROUND_TASK_SCHEDULER, core.APP_SHUTTING_DOWN.is_set)

    def tasks(workspace: Any) -> list[dict[str, Any]]:
        return store_tasks(workspace.database_path, f'cdr-store:{workspace.id}')

    core.register_idle_task(copy_when_idle, STORE_IDLE_SECONDS)
    core.BACKGROUND_TASK_PROVIDERS.append(tasks)


# ---------------------------------------------------------------------------------------------------------------------
# Reading a copy back: the frame pandas.read_sql_query returns from the SQLite table of the CDR.

def _sqlite_like(values: pd.Series) -> Any:
    """A column as pandas.read_sql_query types it from SQLite values: no value at all gives objects (None), integers
    with a missing value give float64."""
    if values.isna().all():
        return pd.Series([None] * len(values), dtype=object, index=values.index)
    if isinstance(values.dtype, pd.Int64Dtype):
        return values.astype('float64') if values.isna().any() else values.astype('int64')
    return values


def read_cdr(database_path: Any, kind: str, dataset_id: int, columns: list[str], *,
             rowids: list[int] | None = None) -> pd.DataFrame:
    """The columns of one CDR as ``pandas.read_sql_query`` returns them from its SQLite table in row id order (only the
    rows ``rowids`` when given): the same values, with the same Python types and dtypes."""
    import duckdb
    from pandas.core.internals.construction import convert_object_array

    root = store_root(database_path)
    manifest = read_manifest(manifest_file(root, kind, dataset_id))
    if manifest is None or not cdr_file(root, kind, dataset_id).is_file():
        raise LookupError(f'The columnar copy of CDR {dataset_id} is not ready.')
    types = dict(manifest['columns'])
    missing = [column for column in columns if column not in types]
    if missing:
        raise KeyError(f'The CDR {dataset_id} has no column {missing[0]}.')
    parts = []
    for column in dict.fromkeys(columns):
        parts.append(quote(column))
        if types[column].startswith('MIXED:'):
            parts.extend(quote(prefix + column) for prefix, part in ((INT_PREFIX, 'I'), (REAL_PREFIX, 'R'))
                         if part in types[column])
    source = "'" + str(cdr_file(root, kind, dataset_id)).replace("'", "''") + "'"
    duck = duckdb.connect()
    try:
        where = ''
        if rowids is not None:
            duck.register('wanted', pd.DataFrame({'rowid': pd.Series(list(rowids), dtype='int64')}))
            where = f'WHERE {quote(ROWID)} IN (SELECT rowid FROM wanted)'
        raw = duck.execute(f'SELECT {", ".join(parts) or "1"} FROM read_parquet({source}) {where} ORDER BY {quote(ROWID)}').df()
    finally:
        duck.close()
    result = {}
    for column in columns:
        column_type = types[column]
        if not column_type.startswith('MIXED:'):
            result[column] = _sqlite_like(raw[column]).to_numpy()
            continue
        # The text, integers and reals of the column back in one column of Python values, typed as pandas does.
        values = raw[column].astype(object).to_numpy()
        for prefix, part, cast in ((INT_PREFIX, 'I', int), (REAL_PREFIX, 'R', float)):
            if part in column_type:
                numbers = raw[prefix + column]
                present = numbers.notna().to_numpy()
                values[present] = [cast(number) for number in numbers[present]]
        values[pd.isna(values)] = None
        result[column] = convert_object_array([values], dtype=None, coerce_float=True)[0]
    return pd.DataFrame(result, columns=list(columns)) if columns else pd.DataFrame(index=range(len(raw)))
