"""Columnar copy of the CDR rows: the Parquet files of each CDR, read with DuckDB, their only store.

Every ready CDR (Data, Voice or Speech) of a workspace is copied in the background to ``.cdr-store/<kind>/<dataset
id>/part-*.parquet`` beside the workspace database, with its SQLite row id, its dataset id and its NR Mode, and copied
again when its rows change: triggers on its table count every insert, update and delete, so no writer has to tell.
Once copied, its table is emptied (its columns and indexes kept), and so are the combined tables once the copies hold
their CDRs: the SQL of the application that reads them is given their rows from the copies (see Repository's
coordinated connection), and a writer holds the CDR, which puts its rows back in its table first. ``.cdr-store/
catalog.duckdb`` holds one view per CDR type (``cdr_data``, ``cdr_voice``, ``cdr_speech``) over the CDRs the combined
tables include, for tools such as Tableau.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable

import numpy as np
import pandas as pd

STORE_FOLDER = '.cdr-store'
STORE_VERSION = 5
CDR_KINDS = ('data', 'voice', 'speech')
VERSIONS_TABLE = 'cdr_store_versions'
# The CDRs whose table is kept empty (its columns and indexes only) while their copy holds their rows.
SHADOWS_TABLE = 'cdr_store_shadows'
# The combined tables kept empty the same way, and the CDR row each of their rows is.
COMBINED_SHADOWS_TABLE = 'cdr_store_combined_shadows'
COMBINED_ROWS_TABLE = 'cdr_store_combined_rows'
TABLE_TITLES = {VERSIONS_TABLE: 'CDR Store Versions', SHADOWS_TABLE: 'CDR Store Shadows',
                COMBINED_SHADOWS_TABLE: 'CDR Store Combined Shadows', COMBINED_ROWS_TABLE: 'CDR Store Combined Rows'}
CATALOG_FILE = 'catalog.duckdb'
CATALOG_STATE_FILE = 'catalog.json'
# The same views for PostgreSQL with pg_duckdb (the Tableau server keeps them as materialized views): their SELECT, with
# {root} for the folder of the copies as the server sees it.
POSTGRES_VIEWS_FILE = 'postgres-views.json'
# The columns the copy adds to the columns of the CDR.
ROWID, DATASET_ID, NR_MODE = '__rowid', '__dataset_id', '__nr_mode'
# A column with text and numbers keeps its text, and its integers and reals in companion columns, so it is read back
# with the Python type of each value.
INT_PREFIX, REAL_PREFIX = '__int__', '__real__'
READ_BATCH_ROWS = 50_000
# The copy of a CDR waits while the disk would keep less than this free after it (its files take from 130 to 490
# bytes per row, written batch after batch without holding the CDR in memory).
FREE_SPACE_MARGIN = 1024 ** 3
BYTES_PER_ROW_ESTIMATE = 600
SYNC_PRIORITY = (9, 1)
STORE_IDLE_SECONDS = 2 * 60
# The application copies the CDRs by itself (the tests copy them when they need it).
AUTOMATIC = True


def quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def store_root(database_path: Any) -> Path:
    """The folder of the columnar copy of a workspace, beside its database."""
    return Path(str(database_path)).resolve().parent / STORE_FOLDER


def cdr_folder(root: Path, kind: str, dataset_id: int) -> Path:
    """The folder of the copy of a CDR: one Parquet file per batch of its rows."""
    return root / kind / str(int(dataset_id))


def cdr_parts(root: Path, kind: str, dataset_id: int) -> str:
    """The files of the copy of a CDR, as DuckDB reads them."""
    return str(cdr_folder(root, kind, dataset_id) / '*.parquet')


def _sql_text(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


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


def ensure_shadows_table(connection: sqlite3.Connection) -> None:
    connection.execute(f'CREATE TABLE IF NOT EXISTS {SHADOWS_TABLE} (dataset_id INTEGER PRIMARY KEY, emptied_at TEXT)')


def shadows(connection: sqlite3.Connection) -> set[int]:
    """The CDRs whose table is empty, their copy holding their rows."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (SHADOWS_TABLE,)).fetchone():
        return set()
    return {int(row[0]) for row in connection.execute(f'SELECT dataset_id FROM {SHADOWS_TABLE}')}


def forget_shadow(connection: sqlite3.Connection, dataset_id: int) -> None:
    """The table of a CDR holds its rows again (written again, or removed with the CDR); once committed, ``filled``
    tells this process."""
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (SHADOWS_TABLE,)).fetchone():
        connection.execute(f'DELETE FROM {SHADOWS_TABLE} WHERE dataset_id = ?', (int(dataset_id),))


def _as_it_is(connection: Any) -> None:
    """The store reads and writes the tables of the CDRs as they are (see Repository's coordinated connection)."""
    if hasattr(connection, 'write_cdr_tables'):
        connection.write_cdr_tables()


def filled(database_path: Any, dataset_id: int) -> None:
    """The table of a CDR holds its rows again, committed (see forget_shadow)."""
    _set_shadow(database_path, dataset_id, False)


# The emptied tables of each workspace, as this process knows them: a table joins them before it is emptied and
# leaves them once its rows are back, so the SQL that reads it is always given its rows (see provide_rows). They belong
# to the database file they were read from: a database put in its place (by a restore or an import) is read again.
_shadow_sets: dict[str, tuple[Any, set[int]]] = {}
_shadow_guard = Lock()


def _database_file(database_path: Any) -> Any:
    try:
        found = os.stat(database_path)
    except OSError:
        return None
    return found.st_dev, found.st_ino


def _known_set(sets: dict[str, tuple[Any, set[Any]]], database_path: Any, read: Callable[[sqlite3.Connection], set[Any]]) -> set[Any]:
    """The set ``read`` gives of a workspace database, read once for each database file (callers hold no guard)."""
    key, file = _workspace_key(database_path), _database_file(database_path)
    with _shadow_guard:
        known = sets.get(key)
    if known is None or known[0] != file:
        try:
            with sqlite3.connect(f'file:{Path(str(database_path)).resolve()}?mode=ro', uri=True, timeout=30) as connection:
                found = read(connection)
        except sqlite3.Error:
            found = set()
        with _shadow_guard:
            known = sets.get(key)
            if known is None or known[0] != file:
                known = sets[key] = (file, set(found))
    return known[1]


def shadow_ids(database_path: Any) -> frozenset[int]:
    found = _known_set(_shadow_sets, database_path, shadows)
    with _shadow_guard:
        return frozenset(found)


def _set_shadow(database_path: Any, dataset_id: int, empty: bool) -> None:
    found = _known_set(_shadow_sets, database_path, shadows)
    with _shadow_guard:
        (found.add if empty else found.discard)(int(dataset_id))


def forget_shadow_sets(database_path: Any = None) -> None:
    """Read the emptied tables of a workspace (of every one, without one) from its database again."""
    with _shadow_guard:
        for sets in (_shadow_sets, _combined_shadow_sets):
            if database_path is None:
                sets.clear()
            else:
                sets.pop(_workspace_key(database_path), None)


def provide_rows(connection: sqlite3.Connection, dataset_id: int, columns: Any, name: str, first: int | None = None,
                 in_part: tuple[Any, Any] | None = None) -> None:
    """Give the SQL of ``connection`` the rows of a CDR whose table is empty: the TEMP table ``name`` with ``columns`` (the
    first column without any), with their declared types, the row ids and the indexes on those columns, from the copy of
    the CDR (the SQL then reads it in place of the empty table, see Repository's coordinated connection); with ``first``,
    its first rows only (in row id order). With ``in_part`` (some of those columns, and some of those rows by row id),
    every row has the values of those columns, and only those rows the others."""
    dataset_id = int(dataset_id)
    table = f'dataset_rows_{dataset_id}'
    declared = [(str(row[1]), str(row[2] or '')) for row in connection.execute(f'PRAGMA main.table_info({quote(table)})')]
    names = {column.casefold(): column for column, _type in declared}
    wanted = {names[str(column).casefold()] for column in columns if str(column).casefold() in names}
    if not wanted and declared:
        wanted = {declared[0][0]}
    database = next((str(row[2]) for row in connection.execute('PRAGMA database_list') if row[1] == 'main'), '')
    kind = str(connection.execute('SELECT dataset_kind FROM main.dataset_profiles WHERE dataset_id = ?',
                                  (dataset_id,)).fetchone()[0]).casefold()
    selected = [(column, column_type) for column, column_type in declared if column in wanted]
    connection.execute(f'CREATE TEMP TABLE {quote(name)} ({", ".join(f"{quote(column)} {column_type}".strip() for column, column_type in selected)})')

    def insert(names: list[str], rowids: Any = None, left_out: Any = None) -> None:
        values, _length = _raw(database, kind, dataset_id, [ROWID, *names], rowids=rowids, first=None if rowids else first)
        rows = zip(*(_python_values(values[column]).tolist() for column in [ROWID, *names]))
        if left_out:
            rows = (row for row in rows if row[0] not in left_out)
        connection.executemany(f'INSERT INTO temp.{quote(name)} (rowid{"".join(", " + quote(column) for column in names)}) '
                               f'VALUES ({", ".join("?" for _ in range(len(names) + 1))})', rows)

    every = [column for column, _type in selected]
    if in_part is None:
        insert(every)
    else:
        part = {names[str(column).casefold()] for column in in_part[0] if str(column).casefold() in names}
        full = {int(rowid) for rowid in in_part[1]}
        insert([column for column in every if column in part], left_out=full)
        if full:
            insert(every, rowids=sorted(full))
    _copy_indexes(connection, table, name, every)


# ---------------------------------------------------------------------------------------------------------------------
# The combined tables of a workspace whose copies are the only store: empty, each of their rows a row of a CDR.

def ensure_combined_tables(connection: sqlite3.Connection) -> None:
    connection.execute(f'CREATE TABLE IF NOT EXISTS {COMBINED_SHADOWS_TABLE} (kind TEXT PRIMARY KEY, emptied_at TEXT)')
    connection.execute(f'CREATE TABLE IF NOT EXISTS {COMBINED_ROWS_TABLE} (kind TEXT NOT NULL, row_id INTEGER NOT NULL, '
                       'dataset_id INTEGER NOT NULL, source_row_id INTEGER NOT NULL, PRIMARY KEY (kind, row_id))')
    connection.execute(f'CREATE INDEX IF NOT EXISTS idx_{COMBINED_ROWS_TABLE}_dataset ON {COMBINED_ROWS_TABLE} (kind, dataset_id)')


def combined_shadows(connection: sqlite3.Connection) -> set[str]:
    """The CDR types whose combined table is empty, the copies of its CDRs holding its rows."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                              (COMBINED_SHADOWS_TABLE,)).fetchone():
        return set()
    return {str(row[0]) for row in connection.execute(f'SELECT kind FROM {COMBINED_SHADOWS_TABLE}')}


_combined_shadow_sets: dict[str, tuple[Any, set[str]]] = {}
# The CDRs the SQL being run reads of the combined tables, when its caller knows them (see combined_scope).
_combined_scope: ContextVar[frozenset[int] | None] = ContextVar('cdr_store_combined_scope', default=None)


# The rows (row ids) the SQL being run reads of a combined table, when its caller knows them (see combined_rows).
_combined_rows: ContextVar[frozenset[int] | None] = ContextVar('cdr_store_combined_rows', default=None)


@contextmanager
def combined_rows(row_ids: Any):
    """Run SQL that reads these rows only of the combined tables (its WHERE keeps their row ids): an emptied combined
    table is given them alone."""
    token = _combined_rows.set(frozenset(int(item) for item in row_ids))
    try:
        yield
    finally:
        _combined_rows.reset(token)


@contextmanager
def combined_scope(dataset_ids: Any):
    """Run SQL that reads the rows of these CDRs only from the combined tables (its WHERE keeps their dataset ids): an
    emptied combined table is given their rows alone, with their row ids and order."""
    token = _combined_scope.set(frozenset(int(item) for item in dataset_ids))
    try:
        yield
    finally:
        _combined_scope.reset(token)


def combined_shadow_kinds(database_path: Any) -> frozenset[str]:
    found = _known_set(_combined_shadow_sets, database_path, combined_shadows)
    with _shadow_guard:
        return frozenset(found)


def _set_combined_shadow(database_path: Any, kind: str, empty: bool) -> None:
    found = _known_set(_combined_shadow_sets, database_path, combined_shadows)
    with _shadow_guard:
        (found.add if empty else found.discard)(str(kind))


def empty_combined_table(repository: Any, kind: str) -> bool:
    """Empty the combined table of a CDR type once the copy of each of its CDRs holds the CDR as it is: it keeps its
    columns and indexes (how SQLite reads it), and the CDR row each of its rows is, in CDR Store Combined Rows; returns
    whether it was emptied."""
    kind = str(kind).casefold()
    table = f'reporting_rows_{kind}'
    with sqlite3.connect(repository.db_path, timeout=30) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
            return False
        if kind in combined_shadows(connection):
            return False
        cdrs = {int(row[0]) for row in connection.execute(f'SELECT DISTINCT dataset_id FROM {quote(table)}')}
    if not cdrs <= fresh_copies(repository.db_path, cdrs):
        return False
    _set_combined_shadow(repository.db_path, kind, True)
    try:
        with repository.connection() as connection:
            _as_it_is(connection)
            connection.execute('BEGIN IMMEDIATE')
            ensure_combined_tables(connection)
            connection.execute(f'DELETE FROM {COMBINED_ROWS_TABLE} WHERE kind = ?', (kind,))
            connection.execute(f'INSERT INTO {COMBINED_ROWS_TABLE} (kind, row_id, dataset_id, source_row_id) '
                               f'SELECT ?, rowid, dataset_id, source_row_id FROM {quote(table)}', (kind,))
            connection.execute(f'DELETE FROM {quote(table)}')
            connection.execute(f'INSERT OR REPLACE INTO {COMBINED_SHADOWS_TABLE} (kind, emptied_at) VALUES (?, ?)',
                               (kind, datetime.now(timezone.utc).isoformat(timespec='seconds')))
    except BaseException:
        _set_combined_shadow(repository.db_path, kind, False)
        raise
    return True


def provide_combined_rows(connection: sqlite3.Connection, kind: str, columns: Any, name: str) -> None:
    """Give the SQL of ``connection`` the rows of an empty combined table: the TEMP table ``name`` with ``columns`` (the
    first column without any), their declared types, the row ids and the indexes on those columns, each row read from the
    copy of its CDR as the combined table copied it (the last column of the CDR with the identity of the combined
    column; the dataset id, the row id in the CDR and the NR Mode of the CDR unless the CDR has an NR Mode column)."""
    from src.modules.column_names import column_identity
    from src.modules.nr_mode import dataset_nr_mode

    table = f'reporting_rows_{kind}'
    declared = [(str(row[1]), str(row[2] or '')) for row in connection.execute(f'PRAGMA main.table_info({quote(table)})')]
    names = {column.casefold(): column for column, _type in declared}
    wanted = {names[str(column).casefold()] for column in columns if str(column).casefold() in names}
    if not wanted and declared:
        wanted = {declared[0][0]}
    selected = [(column, column_type) for column, column_type in declared if column in wanted]
    database = next((str(row[2]) for row in connection.execute('PRAGMA database_list') if row[1] == 'main'), '')
    scope, rows = _combined_scope.get(), _combined_rows.get()
    mapped = connection.execute(
        f'SELECT row_id, dataset_id, source_row_id FROM main.{COMBINED_ROWS_TABLE} WHERE kind = ?'
        + (f' AND dataset_id IN ({", ".join("?" for _ in scope)})' if scope is not None else '')
        + (' AND row_id IN (SELECT value FROM json_each(?))' if rows is not None else '') + ' ORDER BY row_id',
        (kind, *(sorted(scope) if scope is not None else ()), *([json.dumps(sorted(rows))] if rows is not None else ()))).fetchall()
    length = len(mapped)
    values = {column: np.full(length, None, dtype=object) for column, _type in selected}
    by_dataset: dict[int, list[int]] = {}
    for position, row in enumerate(mapped):
        by_dataset.setdefault(int(row[1]), []).append(position)
    root = store_root(database)
    # A CDR whose copy is not up to date yet (just processed) gives the rows of its table.
    fresh = fresh_copies(database, list(by_dataset))
    for dataset_id, positions in by_dataset.items():
        source_rows = [int(mapped[position][2]) for position in positions]
        if dataset_id in fresh:
            manifest = read_manifest(manifest_file(root, kind, dataset_id)) or {'columns': []}
            cdr_columns_in_order = [column for column, _type in manifest['columns']]
        else:
            cdr_columns_in_order = [str(row[1]) for row in connection.execute(
                f'PRAGMA main.table_info({quote(f"dataset_rows_{dataset_id}")})')]
        lookup = {column_identity(column): column for column in cdr_columns_in_order}
        profile = connection.execute('SELECT d.file_name, p.nr_mode FROM main.datasets d LEFT JOIN main.dataset_profiles p '
                                     'ON p.dataset_id = d.id WHERE d.id = ?', (dataset_id,)).fetchone()
        nr_mode = dataset_nr_mode(kind, profile[1], profile[0]) if profile else None
        physical = {}
        for column, _type in selected:
            identity = column_identity(column)
            physical[column] = ('dataset' if column == 'dataset_id' else 'source' if column == 'source_row_id'
                                else ('cdr', lookup[identity]) if identity in lookup
                                else 'nr_mode' if identity == column_identity('NR_Mode') else None)
        read = sorted({item[1] for item in physical.values() if isinstance(item, tuple)})
        if not read:
            found = {}
        elif dataset_id in fresh:
            found = rows_by_rowid(database, kind, dataset_id, read, source_rows)
        else:
            found = {}
            for start in range(0, len(source_rows), 500):
                chunk = source_rows[start:start + 500]
                found.update({int(row[0]): tuple(row[1:]) for row in connection.execute(
                    f'SELECT rowid{"".join(", " + quote(column) for column in read)} FROM main.{quote(f"dataset_rows_{dataset_id}")} '
                    f'WHERE rowid IN ({", ".join("?" for _ in chunk)})', chunk)})
        at = {column: index for index, column in enumerate(read)}
        for column, source in physical.items():
            if source == 'dataset':
                values[column][positions] = dataset_id
            elif source == 'source':
                values[column][positions] = source_rows
            elif source == 'nr_mode':
                values[column][positions] = nr_mode
            elif isinstance(source, tuple):
                index = at[source[1]]
                values[column][positions] = [found[row][index] if row in found else None for row in source_rows]
    connection.execute(f'CREATE TEMP TABLE {quote(name)} ({", ".join(f"{quote(column)} {column_type}".strip() for column, column_type in selected)})')
    connection.executemany(
        f'INSERT INTO temp.{quote(name)} (rowid{"".join(", " + quote(column) for column, _type in selected)}) '
        f'VALUES ({", ".join("?" for _ in range(len(selected) + 1))})',
        zip([int(row[0]) for row in mapped], *(values[column].tolist() for column, _type in selected)))
    _copy_indexes(connection, table, name, [column for column, _type in selected])


def map_cdr_rows(connection: sqlite3.Connection, kind: str, dataset_id: int, source_rows: list[int]) -> int:
    """Put the rows of a CDR in an emptied combined table, after its other rows, with the row ids SQLite would give
    them (one more than the last row id, in the order of the rows of the CDR)."""
    connection.execute(f'DELETE FROM {COMBINED_ROWS_TABLE} WHERE kind = ? AND dataset_id = ?', (kind, int(dataset_id)))
    last = int(connection.execute(f'SELECT MAX(row_id) FROM {COMBINED_ROWS_TABLE} WHERE kind = ?', (kind,)).fetchone()[0] or 0)
    connection.executemany(f'INSERT INTO {COMBINED_ROWS_TABLE} (kind, row_id, dataset_id, source_row_id) VALUES (?, ?, ?, ?)',
                           [(kind, last + position, int(dataset_id), int(row)) for position, row in enumerate(source_rows, start=1)])
    return len(source_rows)


def unmap_cdr_rows(connection: sqlite3.Connection, kind: str, dataset_ids: Any = None, *, orphans: bool = False) -> int:
    """Take the rows of CDRs (or of the CDRs that are gone, ``orphans``) out of an emptied combined table."""
    if orphans:
        return connection.execute(f'DELETE FROM {COMBINED_ROWS_TABLE} WHERE kind = ? AND dataset_id NOT IN (SELECT id FROM datasets)',
                                  (kind,)).rowcount
    ids = [int(item) for item in dataset_ids or ()]
    if not ids:
        return 0
    return connection.execute(f'DELETE FROM {COMBINED_ROWS_TABLE} WHERE kind = ? AND dataset_id IN ({", ".join("?" for _ in ids)})',
                              (kind, *ids)).rowcount


def mapped_cdrs(connection: sqlite3.Connection, kind: str) -> set[int]:
    """The CDRs whose rows an emptied combined table holds."""
    return {int(row[0]) for row in connection.execute(f'SELECT DISTINCT dataset_id FROM {COMBINED_ROWS_TABLE} WHERE kind = ?', (kind,))}


def cdr_rowids(connection: sqlite3.Connection, kind: str, dataset_id: int) -> list[int]:
    """The row ids of a CDR in their order: from its table, or from its copy when the table is empty."""
    dataset_id = int(dataset_id)
    if dataset_id in shadows(connection):
        database = next((str(row[2]) for row in connection.execute('PRAGMA database_list') if row[1] == 'main'), '')
        return [int(rowid) for rowid in cdr_columns(database, kind, dataset_id, [ROWID])[ROWID]]
    return [int(row[0]) for row in connection.execute(f'SELECT rowid FROM main.{quote(f"dataset_rows_{dataset_id}")} ORDER BY rowid')]


def combined_reference(kind: str) -> re.Pattern[str]:
    """How SQL names a combined table, quoted or not (not in a schema it names)."""
    table = f'reporting_rows_{kind}'
    return re.compile(rf'(?<![.\w"`\[])(?:"{table}"|`{table}`|\[{table}\]|{table}\b)', re.IGNORECASE)


def index_columns(connection: sqlite3.Connection, table: str) -> dict[str, tuple[int, str, set[str]]]:
    """The indexes of ``table``: by name, their position, CREATE INDEX and the columns they read (those they name quoted,
    and those of the table they name bare, casefolded)."""
    names = {str(row[1]).casefold() for row in connection.execute(f'PRAGMA main.table_info({quote(table)})')}
    found = {}
    for position, (index_name, sql) in enumerate(connection.execute(
            "SELECT name, sql FROM main.sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL", (table,)).fetchall()):
        indexed = str(sql)[str(sql).upper().index(' ON ') + 4:]
        indexed = indexed[indexed.index('('):] if '(' in indexed else ''
        referenced = {match.group(1).replace('""', '"').casefold() for match in re.finditer(r'"((?:[^"]|"")*)"', indexed)}
        referenced |= {word.casefold() for word in re.findall(r'(?<!["\w])([A-Za-z_]\w*)(?![\w"])', indexed)
                       if word.casefold() in names}
        found[str(index_name)] = (position, str(sql), referenced)
    return found


def _copy_indexes(connection: sqlite3.Connection, table: str, name: str, columns: list[str]) -> None:
    """The indexes of ``table`` on ``columns`` on the TEMP table ``name``, so SQLite reads its rows in the same order."""
    for position, sql, referenced in index_columns(connection, table).values():
        if referenced <= {column.casefold() for column in columns}:
            body = str(sql)[str(sql).upper().index(' ON ') + 4:].lstrip()
            body = re.sub(rf'^(?:"{table}"|{table})', quote(name), body, flags=re.IGNORECASE)
            connection.execute(f'CREATE INDEX temp.{quote(f"{name}_index_{position}")} ON {body}')


def table_reference(dataset_id: int) -> re.Pattern[str]:
    """How SQL names the table of a CDR, quoted or not (not in a schema it names, as main.dataset_rows_1: the table
    itself)."""
    table = f'dataset_rows_{int(dataset_id)}'
    return re.compile(rf'(?<![.\w"`\[])(?:"{table}"|`{table}`|\[{table}\]|{table}\b)', re.IGNORECASE)


def drop_change_triggers(connection: sqlite3.Connection, dataset_id: int) -> None:
    for event in ('insert', 'update', 'delete'):
        connection.execute(f'DROP TRIGGER IF EXISTS {quote(f"cdr_store_{int(dataset_id)}_{event}")}')


def _versions(connection: sqlite3.Connection) -> dict[int, int]:
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (VERSIONS_TABLE,)).fetchone():
        return {}
    return {int(row[0]): int(row[1]) for row in connection.execute(f'SELECT dataset_id, version FROM {VERSIONS_TABLE}')}


def table_schema(connection: sqlite3.Connection, dataset_id: int) -> dict[str, Any]:
    """How the table of a CDR is created: its CREATE TABLE and the CREATE INDEX of its indexes (not the triggers of
    the copy), to make the table again from its copy."""
    table = f'dataset_rows_{int(dataset_id)}'
    created = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    indexes = [str(row[0]) for row in connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL ORDER BY rowid", (table,))]
    return {'table': str(created[0]) if created else '', 'indexes': indexes}


def _table_columns(connection: sqlite3.Connection, dataset_id: int) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info({quote(f"dataset_rows_{int(dataset_id)}")})')]


def _ready_cdrs(connection: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    """The ready Data, Voice and Speech CDRs of the workspace: those with a table of rows (``table``), which their copy
    follows, and those whose copy is their only store (their table empty, or gone)."""
    empty = shadows(connection)
    tables = {str(row[0]) for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'dataset_rows_%'")}
    rows = connection.execute(
        'SELECT d.id, d.file_name, p.status, p.dataset_kind, p.nr_mode, p.processed_at, p.normalization_version, p.row_count '
        'FROM datasets d JOIN dataset_profiles p ON p.dataset_id = d.id').fetchall()
    from src.modules.nr_mode import dataset_nr_mode

    # The NR Mode of a CDR as its combined rows keep it.
    return {
        int(row[0]): {'id': int(row[0]), 'file_name': str(row[1] or ''), 'kind': str(row[3] or '').casefold(),
                      'nr_mode': dataset_nr_mode(row[3], row[4], row[1]) or '', 'processed_at': str(row[5] or ''),
                      'normalization_version': int(row[6] or 1), 'row_count': int(row[7] or 0),
                      'table': f'dataset_rows_{int(row[0])}' in tables and int(row[0]) not in empty}
        for row in rows
        if str(row[2] or '').casefold() == 'ready' and str(row[3] or '').casefold() in CDR_KINDS
    }


def revision(cdr: dict[str, Any], columns: list[str], version: int) -> str:
    """What the copy of a CDR depends on: its processing, its columns and the changes of its rows."""
    return json.dumps({
        'v': STORE_VERSION, 'kind': cdr['kind'], 'nr_mode': cdr['nr_mode'], 'processed_at': cdr['processed_at'],
        'normalization_version': cdr['normalization_version'], 'row_count': cdr['row_count'], 'columns': columns,
        'version': version,
    }, sort_keys=True, ensure_ascii=False)


def fresh_copies(database_path: Any, dataset_ids: Any) -> set[int]:
    """The CDRs among ``dataset_ids`` whose copy holds their rows as they are now."""
    root = store_root(database_path)
    if not root.is_dir():
        return set()
    with sqlite3.connect(database_path, timeout=30) as connection:
        cdrs = _ready_cdrs(connection)
        versions = _versions(connection)
        fresh = set()
        for dataset_id in {int(item) for item in dataset_ids}:
            cdr = cdrs.get(dataset_id)
            if cdr is None:
                continue
            manifest = read_manifest(manifest_file(root, cdr['kind'], dataset_id))
            if not manifest or not cdr_folder(root, cdr['kind'], dataset_id).is_dir():
                continue
            # Without a table the copy is the store of the CDR.
            if not cdr['table'] or manifest.get('revision') == revision(cdr, _table_columns(connection, dataset_id),
                                                                         versions.get(dataset_id, 0)):
                fresh.add(dataset_id)
    return fresh


def store_changes(database_path: Any) -> dict[str, Any]:
    """The CDRs whose copy is missing or out of date (of those with a table of rows), and the copies of CDRs that are
    gone: deleted, or now of another type while their table holds them. The copy of a CDR being processed again, or
    whose copy is its only store, is kept. Where the copies are the only store, ``tables`` are the CDRs whose table can
    go (their copy holds them as they are)."""
    root = store_root(database_path)
    only = only_copies(database_path)
    with sqlite3.connect(database_path, timeout=30) as connection:
        cdrs = _ready_cdrs(connection)
        versions = _versions(connection)
        existing = {int(row[0]) for row in connection.execute('SELECT id FROM datasets')}
        pending, tables = [], []
        for dataset_id, cdr in sorted(cdrs.items()):
            if not cdr['table']:
                continue
            manifest = read_manifest(manifest_file(root, cdr['kind'], dataset_id))
            current = revision(cdr, _table_columns(connection, dataset_id), versions.get(dataset_id, 0))
            if manifest is None or manifest.get('revision') != current or not cdr_folder(root, cdr['kind'], dataset_id).is_dir():
                pending.append(cdr)
            elif only and not held(database_path, dataset_id):
                tables.append(dataset_id)
    orphans = [path for kind in CDR_KINDS for path in (root / kind).glob('*.json')
               if not path.stem.isdigit() or int(path.stem) not in existing
               or (int(path.stem) in cdrs and cdrs[int(path.stem)]['table'] and cdrs[int(path.stem)]['kind'] != kind)]
    return {'pending': pending, 'orphans': orphans, 'cdrs': cdrs, 'tables': tables}


# ---------------------------------------------------------------------------------------------------------------------
# Copying one CDR.

def _column_types(connection: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, str]:
    """The type of each column over all its values, in one pass: BIGINT when every value is an integer, DOUBLE when
    every value is a real, DOUBLE:I when it has integers and reals, VARCHAR when every value is text (or it has no
    value), and MIXED:I, MIXED:R or MIXED:IR when it has text and integers, reals or both."""
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
            types[column] = 'VARCHAR' if flag & 4 or not flag else {1: 'BIGINT', 2: 'DOUBLE', 3: 'DOUBLE:I'}[flag]
    return types


def _stored_columns(columns: list[str], types: dict[str, str]) -> list[tuple[str, str, str]]:
    """The columns of the Parquet file of a CDR: (name, SQLite expression, type) for each column, for a column with
    text and numbers its text, integers and reals apart, and for a column with integers and reals its integers too."""
    stored = []
    for column in columns:
        source, column_type = quote(column), types[column]
        if column_type == 'DOUBLE:I':
            stored.append((column, source, 'DOUBLE'))
            stored.append((INT_PREFIX + column, f"CASE WHEN typeof({source}) = 'integer' THEN {source} END", 'BIGINT'))
        elif column_type.startswith('MIXED:'):
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
    """The space the file system has free: a copy never counts on what macOS may free on demand later."""
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free


class NotEnoughSpace(RuntimeError):
    def __init__(self, needed: int, free: int) -> None:
        super().__init__(f'{needed / 1024 ** 3:.1f} GB of free disk space needed, {free / 1024 ** 3:.1f} GB free')
        self.needed, self.free = needed, free


def export_rows(connection: sqlite3.Connection, dataset_id: int, nr_mode: str, columns: list[str], types: dict[str, str],
                target: Path, should_stop: Callable[[], bool] = lambda: False) -> int | None:
    """Write the rows of a CDR table, read in batches through ``connection``, to the folder ``target``, one Parquet file
    per batch with the given column types (nothing of the CDR is held in memory or spilled to disk); returns how many
    rows it wrote, or None when it stopped."""
    import duckdb

    table = f'dataset_rows_{int(dataset_id)}'
    stored = [(ROWID, 'rowid', 'BIGINT'), (DATASET_ID, str(int(dataset_id)), 'BIGINT'), (NR_MODE, '', 'VARCHAR'),
              *_stored_columns(columns, types)]
    casts = ', '.join(f'CAST({quote(name)} AS {column_type}) AS {quote(name)}' for name, _expression, column_type in stored)
    target.mkdir(parents=True, exist_ok=True)
    duck = duckdb.connect(config={'memory_limit': '1GB', 'threads': 2})
    written = 0
    try:
        last = connection.execute(f'SELECT MAX(rowid) FROM {quote(table)}').fetchone()[0] or 0
        selected = ''.join(f', {expression}' for _name, expression, _column_type in stored[3:])
        for part, low in enumerate(range(0, int(last), READ_BATCH_ROWS), start=1):
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
                   for (name, _expression, column_type), column_values in zip(stored[3:], values[1:])},
            })
            duck.register('chunk', frame)
            duck.execute(f'COPY (SELECT {casts} FROM chunk) TO {_sql_text(target / f"part-{part:05d}.parquet")} '
                         '(FORMAT parquet, COMPRESSION zstd)')
            duck.unregister('chunk')
            written += len(frame)
        if not written:
            # A CDR without rows keeps the columns of its copy.
            duck.register('chunk', pd.DataFrame({name: pd.Series([], dtype=object) for name, _expression, _type in stored}))
            duck.execute(f'COPY (SELECT {casts} FROM chunk) TO {_sql_text(target / "part-00000.parquet")} (FORMAT parquet)')
        return written
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
    target = cdr_folder(root, kind, dataset_id)
    temporary = folder / f'.{dataset_id}.{os.getpid()}.tmp'
    database_file = _database_file(database_path)
    shutil.rmtree(temporary, ignore_errors=True)
    with repository.connection() as writer:
        ensure_versions_table(writer)
        ensure_change_triggers(writer, dataset_id)
    with sqlite3.connect(database_path, timeout=30) as connection:
        # Every read below sees the same snapshot of the CDR (the database is in WAL mode).
        connection.execute('BEGIN')
        try:
            ready = _ready_cdrs(connection).get(dataset_id)
            if ready is None or not ready['table']:
                return None
            columns = _table_columns(connection, dataset_id)
            current = revision(ready, columns, _versions(connection).get(dataset_id, 0))
            if any(column.casefold() in {ROWID, DATASET_ID, NR_MODE} or column.startswith((INT_PREFIX, REAL_PREFIX))
                   for column in columns):
                raise ValueError(f'The CDR {ready["file_name"]} has a column named like the columns the copy adds.')
            types = _column_types(connection, table, columns)
            schema = table_schema(connection, dataset_id)
            rows_written = export_rows(connection, dataset_id, ready['nr_mode'], columns, types, temporary, should_stop)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        finally:
            connection.rollback()
    if rows_written is None:
        shutil.rmtree(temporary, ignore_errors=True)
        return None
    # The new copy takes the place of the old one at once (readers of the old one keep their open files), once no
    # archive is taking the copies, and not when the database was replaced meanwhile (it is a copy of the one before).
    lock = copies_lock(root)
    while not lock.acquire(timeout=1):
        if should_stop():
            shutil.rmtree(temporary, ignore_errors=True)
            return None
    try:
        if _database_file(database_path) != database_file:
            shutil.rmtree(temporary, ignore_errors=True)
            return None
        previous = folder / f'.{dataset_id}.{os.getpid()}.old'
        if target.exists():
            os.replace(target, previous)
        os.replace(temporary, target)
        shutil.rmtree(previous, ignore_errors=True)
        (folder / f'{dataset_id}.parquet').unlink(missing_ok=True)  # The single file of earlier copies.
        manifest = {
            'version': STORE_VERSION, 'dataset_id': dataset_id, 'kind': kind, 'file_name': ready['file_name'],
            'revision': current, 'rows': rows_written, 'columns': [[column, types[column]] for column in columns],
            'schema': schema, 'written_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        }
        _write_json(manifest_file(root, kind, dataset_id), manifest)
    finally:
        lock.release()
    return manifest


def remove_copy(manifest_path: Path) -> bool:
    """Remove the copy of a CDR that is gone (or now of another type); returns whether it did (not while an archive is
    taking the copies)."""
    lock = copies_lock(manifest_path.parent.parent)
    if not lock.acquire(blocking=False):
        return False
    try:
        shutil.rmtree(manifest_path.with_suffix(''), ignore_errors=True)
        manifest_path.with_suffix('.parquet').unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
    finally:
        lock.release()
    return True


# ---------------------------------------------------------------------------------------------------------------------
# The copies in backups, packages and duplicates: they travel with the database of their workspace.

# The folder of the copies in an archive of a workspace, beside its database.sqlite.
ARCHIVE_FOLDER = 'cdr-store'

# The copies of a workspace (by its store) change one at a time under its lock: a new copy takes the place of the old
# one, or the copy of a CDR that is gone is removed. An archive of the workspace holds it from the snapshot of the
# database until it has taken the copies, which then are those of that snapshot.
_copies_locks: dict[str, RLock] = {}


def copies_lock(root: Path) -> RLock:
    with _shadow_guard:
        return _copies_locks.setdefault(_workspace_key(root), RLock())


@contextmanager
def steady_copies(database_path: Any):
    """No copy of the workspace changes meanwhile (see copies_lock)."""
    with copies_lock(store_root(database_path)):
        yield


def snapshot_copies(snapshot_path: Any, database_path: Any) -> list[tuple[Path, str]]:
    """The files of the copies a snapshot of a workspace database takes with it, as (file, path in the store) pairs: those
    of the CDRs whose copy is their only store, and those whose copy holds their table as the snapshot has it (the
    others are copied again). Taken under steady_copies, from the snapshot made under it."""
    root = store_root(database_path)
    if not root.is_dir():
        return []
    files: list[tuple[Path, str]] = []
    with sqlite3.connect(f'file:{Path(str(snapshot_path)).resolve()}?mode=ro', uri=True, timeout=30) as connection:
        cdrs = _ready_cdrs(connection)
        versions = _versions(connection)
        for dataset_id, cdr in sorted(cdrs.items()):
            manifest_path = manifest_file(root, cdr['kind'], dataset_id)
            manifest = read_manifest(manifest_path)
            folder = cdr_folder(root, cdr['kind'], dataset_id)
            if manifest is None or not folder.is_dir():
                continue
            if cdr['table'] and manifest.get('revision') != revision(cdr, _table_columns(connection, dataset_id),
                                                                     versions.get(dataset_id, 0)):
                continue
            files += [(part, part.relative_to(root).as_posix()) for part in sorted(folder.glob('*.parquet'))]
            files.append((manifest_path, manifest_path.relative_to(root).as_posix()))
    return files


def replace_copies(database_path: Any, source: Path | None = None) -> None:
    """The copies of a workspace whose database was put in place by a restore or an import: those that came with it
    (``source``, a folder laid out as the store, moved into place), or none, its CDRs then being copied again from their
    tables."""
    root = store_root(database_path)
    with copies_lock(root):
        if root.exists():
            previous = root.with_name(f'{root.name}.{os.getpid()}.{time.time_ns()}.old')
            os.replace(root, previous)
            shutil.rmtree(previous, ignore_errors=True)
        if source is not None and source.is_dir():
            try:
                os.replace(source, root)
            except OSError:
                # Another volume (a staging folder elsewhere).
                shutil.copytree(source, root)
    forget_shadow_sets(database_path)


# ---------------------------------------------------------------------------------------------------------------------
# The table of a CDR whose copy is its only store, made again from the copy while it is changed.

# Whether the copies are the only store of the CDRs of a workspace (its workspace state, '1'): the table of a CDR then
# goes once its copy holds it.
ONLY_COPIES_STATE_KEY = 'cdr_store_only_copies'

_holds: dict[tuple[str, int], int] = {}
_holds_guard = Lock()
_restore_locks: dict[tuple[str, int], Lock] = {}


def only_copies(database_path: Any) -> bool:
    with sqlite3.connect(database_path, timeout=30) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'workspace_state'").fetchone():
            return False
        row = connection.execute('SELECT value FROM workspace_state WHERE key = ?', (ONLY_COPIES_STATE_KEY,)).fetchone()
    return bool(row and str(row[0]) == '1')


def restore_table(repository: Any, dataset_id: int) -> bool:
    """Put the rows of a CDR back in its table from its copy, as they were: its row ids and values (with their SQLite
    types), in its empty table, or in the table made again as it was (its CREATE TABLE and indexes) when it is gone;
    returns whether it did (not when the table holds the rows or the CDR has no copy)."""
    import duckdb

    database_path = repository.db_path
    dataset_id = int(dataset_id)
    table = f'dataset_rows_{dataset_id}'

    def state(connection: sqlite3.Connection) -> str:
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
        return 'gone' if not exists else 'empty' if dataset_id in shadows(connection) else 'full'

    with sqlite3.connect(database_path, timeout=30) as connection:
        if state(connection) == 'full':
            return False
        row = connection.execute('SELECT dataset_kind FROM dataset_profiles WHERE dataset_id = ?', (dataset_id,)).fetchone()
    kind = str(row[0] or '').casefold() if row else ''
    root = store_root(database_path)
    manifest = read_manifest(manifest_file(root, kind, dataset_id)) if kind in CDR_KINDS else None
    if manifest is None or not cdr_folder(root, kind, dataset_id).is_dir():
        return False
    schema = manifest.get('schema') or {}
    columns = [column for column, _type in manifest['columns']]
    with duckdb.connect() as duck:
        last = duck.execute(f'SELECT MAX({quote(ROWID)}) FROM read_parquet({_sql_text(cdr_parts(root, kind, dataset_id))})').fetchone()[0]
    insert = (f'INSERT INTO {quote(table)} (rowid{"".join(", " + quote(column) for column in columns)}) '
              f'VALUES ({", ".join("?" for _ in range(len(columns) + 1))})')
    with repository.connection() as connection:
        _as_it_is(connection)
        connection.execute('BEGIN IMMEDIATE')
        current = state(connection)
        if current == 'full':
            return False
        if current == 'gone':
            if not schema.get('table'):
                raise LookupError(f'The copy of CDR {dataset_id} does not say how its table is made.')
            connection.execute(schema['table'])
        # The rows come back without counting as a change of the CDR.
        drop_change_triggers(connection, dataset_id)
        for low in range(0, int(last or 0), READ_BATCH_ROWS):
            values, _length = _raw(database_path, kind, dataset_id, [ROWID, *columns], rowid_range=(low, low + READ_BATCH_ROWS))
            connection.executemany(insert, zip(*(_python_values(values[column]).tolist() for column in [ROWID, *columns])))
        if current == 'gone':
            for sql in schema.get('indexes') or []:
                connection.execute(sql)
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (SHADOWS_TABLE,)).fetchone():
            connection.execute(f'DELETE FROM {SHADOWS_TABLE} WHERE dataset_id = ?', (dataset_id,))
        ensure_versions_table(connection)
        ensure_change_triggers(connection, dataset_id)
    # Its rows are in the table again.
    _set_shadow(database_path, dataset_id, False)
    return True


@contextmanager
def hold(repository: Any, dataset_id: int, *, restore: bool = True):
    """Keep the table of rows of a CDR while it is changed, made again from its copy first when the copy is its only
    store (with ``restore``); its copy follows it afterwards in the background, and where the copies are the only store
    the table then goes (never while it is held)."""
    key = (_workspace_key(repository.db_path), int(dataset_id))
    with _holds_guard:
        _holds[key] = _holds.get(key, 0) + 1
        lock = _restore_locks.setdefault(key, Lock())
    try:
        # A table being removed goes first (see drop_copied_table).
        with lock:
            if restore:
                restore_table(repository, dataset_id)
        yield
    finally:
        with _holds_guard:
            _holds[key] -= 1
            if not _holds[key]:
                del _holds[key]


def held(database_path: Any, dataset_id: int) -> bool:
    with _holds_guard:
        return (_workspace_key(database_path), int(dataset_id)) in _holds


def drop_copied_table(repository: Any, dataset_id: int) -> bool:
    """Empty the table of a CDR whose copy holds it as it is, where the copies are the only store: it keeps its columns
    and indexes (how SQLite reads it) without its rows; returns whether it was emptied (not while it is held, nor when the
    copy is out of date)."""
    dataset_id = int(dataset_id)
    key = (_workspace_key(repository.db_path), dataset_id)
    with _holds_guard:
        lock = _restore_locks.setdefault(key, Lock())
    # A writer that holds the CDR from now on waits for the table to go, and makes it again.
    with lock:
        with _holds_guard:
            if key in _holds:
                return False
        if dataset_id not in fresh_copies(repository.db_path, [dataset_id]):
            return False
        # From now on the SQL that reads the table is given the rows of the copy (they are the same).
        _set_shadow(repository.db_path, dataset_id, True)
        emptied = False
        try:
            emptied = _empty_table(repository, dataset_id)
        finally:
            if not emptied:
                _set_shadow(repository.db_path, dataset_id, False)
        return emptied


def _empty_table(repository: Any, dataset_id: int) -> bool:
    """Empty the table of a CDR and list it among the shadows (whether it was there to empty)."""
    with repository.connection() as connection:
        _as_it_is(connection)
        connection.execute('BEGIN IMMEDIATE')
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                                  (f'dataset_rows_{dataset_id}',)).fetchone():
            return False
        # Emptying the table is no change of the CDR (and its dropped triggers make SQLite prepare again the
        # statements that read it).
        drop_change_triggers(connection, dataset_id)
        connection.execute(f'DELETE FROM {quote(f"dataset_rows_{dataset_id}")}')
        ensure_shadows_table(connection)
        connection.execute(f'INSERT OR REPLACE INTO {SHADOWS_TABLE} (dataset_id, emptied_at) VALUES (?, ?)',
                           (dataset_id, datetime.now(timezone.utc).isoformat(timespec='seconds')))
    return True


# ---------------------------------------------------------------------------------------------------------------------
# The copies become the only store of the CDRs of a workspace, and its database gives back the room of the rows.

# The share of free pages, and their size, from which the database of a workspace is compacted.
COMPACT_FREE_SHARE = 0.25
COMPACT_FREE_BYTES = 1024 ** 3


def move_rows_to_copies(repository: Any, step: Callable[[int, int], None] = lambda done, total: None) -> dict[str, int]:
    """Make the copies the only store of the CDRs of a workspace: the table of each CDR whose copy holds it as it is is
    emptied now (``step`` hears each), those of the others once copied in the background, and the combined table of each
    CDR type once the copies hold all its CDRs (here, or when the server is idle, see install_cdr_store). Returns how many
    CDR and combined tables it emptied."""
    if not only_copies(repository.db_path):
        repository.set_workspace_state(ONLY_COPIES_STATE_KEY, '1')
    tables = store_changes(repository.db_path)['tables']
    emptied = 0
    for position, dataset_id in enumerate(tables, start=1):
        step(position, len(tables))
        emptied += bool(drop_copied_table(repository, dataset_id))
    combined = sum(bool(empty_combined_table(repository, kind)) for kind in CDR_KINDS)
    return {'cdr_tables': emptied, 'combined_tables': combined}


def compact_database(repository: Any, starting: Callable[[], None] = lambda: None) -> dict[str, int] | None:
    """Give the disk back the room the emptied tables leave in the database of a workspace: VACUUM it when a quarter of
    it, and at least 1 GB, is free pages, and its disk has room for twice its used pages (VACUUM writes them to a
    temporary file beside the database, then through its WAL). Returns its size before and after (``skipped`` with the
    room it needs when the disk has too little), or None when it is not needed; ``starting`` hears it start. Writers of
    this process wait meanwhile."""
    from src.modules.repository import workspace_write_lock

    database_path = Path(str(repository.db_path)).resolve()
    with sqlite3.connect(database_path, timeout=30) as connection:
        page_size = int(connection.execute('PRAGMA page_size').fetchone()[0])
        pages = int(connection.execute('PRAGMA page_count').fetchone()[0])
        free = int(connection.execute('PRAGMA freelist_count').fetchone()[0])
    if free * page_size < COMPACT_FREE_BYTES or free < pages * COMPACT_FREE_SHARE:
        return None
    before, needed = pages * page_size, 2 * (pages - free) * page_size + FREE_SPACE_MARGIN
    if free_space(database_path.parent) < needed:
        return {'before': before, 'skipped': 1, 'needed': needed}
    starting()
    with workspace_write_lock(database_path):
        connection = sqlite3.connect(database_path, timeout=600, isolation_level=None)
        previous = connection.execute('PRAGMA temp_store_directory').fetchone()
        try:
            connection.execute(f'PRAGMA temp_store_directory = {_sql_text(str(database_path.parent))}')
            connection.execute('VACUUM')
            connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally:
            connection.execute(f'PRAGMA temp_store_directory = {_sql_text(str(previous[0]) if previous else "")}')
            connection.close()
    return {'before': before, 'after': database_path.stat().st_size}


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
            types.setdefault(identity, set()).add('VARCHAR' if column_type.startswith('MIXED:') else
                                                  'DOUBLE' if column_type == 'DOUBLE:I' else column_type)
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
    files = ', '.join(_sql_text(cdr_parts(root, kind, manifest['dataset_id'])) for manifest in manifests)
    return f'CREATE VIEW {view} AS SELECT {", ".join(selected)} FROM read_parquet([{files}], union_by_name = true)'


def _catalog_inputs(database_path: Any, included: dict[str, set[int]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """The copies each view reads and the signature of the catalog they make."""
    root = store_root(database_path)
    manifests = {kind: [manifest for dataset_id in sorted(included.get(kind, ()))
                        if (manifest := read_manifest(manifest_file(root, kind, dataset_id)))
                        and cdr_folder(root, kind, dataset_id).is_dir()] for kind in CDR_KINDS}
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
    return (written != _catalog_inputs(database_path, included)[1] or not (root / CATALOG_FILE).is_file()
            or not (root / POSTGRES_VIEWS_FILE).is_file())


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
    _write_json(root / POSTGRES_VIEWS_FILE, {
        'version': 1, 'signature': hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest(),
        'views': {f'cdr_{kind}': _postgres_view_sql(kind, manifests[kind]) for kind in CDR_KINDS},
    })
    _write_json(state_path, signature)
    return True


_POSTGRES_TYPES = {'BIGINT': 'bigint', 'DOUBLE': 'double precision', 'VARCHAR': 'text'}


def _postgres_view_sql(kind: str, manifests: list[dict[str, Any]]) -> str:
    """The SELECT of the view of a CDR type for PostgreSQL with pg_duckdb, as the catalog view (_view_sql) reads the
    copies: the dataset id and row id of each row, every column of the CDRs with one type (text when the CDRs give it
    text, or text and numbers), and the NR Mode of each row; the files under {root}."""
    def name(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def field(value: str) -> str:
        return "r['" + value.replace("'", "''") + "']"

    if not manifests:
        return 'SELECT NULL::bigint AS dataset_id, NULL::bigint AS source_row_id, NULL::text AS "NR_Mode" WHERE false'
    types: dict[str, set[str]] = {}
    names: dict[str, str] = {}
    companions: set[str] = set()
    for manifest in manifests:
        for column, column_type in manifest['columns']:
            identity = column.casefold()
            names.setdefault(identity, column)
            types.setdefault(identity, set()).add('VARCHAR' if column_type.startswith('MIXED:') else
                                                  'DOUBLE' if column_type == 'DOUBLE:I' else column_type)
            if column_type.startswith('MIXED:'):
                companions.update(prefix + column for prefix, part in ((INT_PREFIX, 'I'), (REAL_PREFIX, 'R')) if part in column_type)
    nr_mode = names.pop('nr_mode', None)
    for identity in ('dataset_id', 'source_row_id'):
        names.pop(identity, None)
    selected = [f'{field(DATASET_ID)}::bigint AS dataset_id', f'{field(ROWID)}::bigint AS source_row_id']
    # PostgreSQL keeps 63 bytes of a name: two columns that start alike keep apart.
    taken = {'dataset_id', 'source_row_id', 'nr_mode'}
    for identity, column in names.items():
        column_types = types[identity]
        common = column_types.pop() if len(column_types) == 1 else ('DOUBLE' if column_types <= {'BIGINT', 'DOUBLE'} else 'VARCHAR')
        parts = [f'{field(other)}::text' for other in (INT_PREFIX + column, REAL_PREFIX + column) if other in companions]
        value = (f'COALESCE({field(column)}::text, {", ".join(parts)})' if parts
                 else f'{field(column)}::{_POSTGRES_TYPES[common]}')
        label, suffix = column.encode('utf-8')[:63].decode('utf-8', 'ignore'), 1
        while label.casefold() in taken:
            suffix += 1
            label = column.encode('utf-8')[:60].decode('utf-8', 'ignore') + f'_{suffix}'
        taken.add(label.casefold())
        selected.append(f'{value} AS {name(label)}')
    selected.append(f'COALESCE({field(nr_mode)}::text, {field(NR_MODE)}::text) AS "NR_Mode"' if nr_mode
                    else f'{field(NR_MODE)}::text AS "NR_Mode"')
    files = ', '.join("'{root}/" + f"{kind}/{int(manifest['dataset_id'])}/part-*.parquet'" for manifest in manifests)
    return f'SELECT {", ".join(selected)} FROM read_parquet(ARRAY[{files}], union_by_name := true) r'



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
    """The ready CDRs of each type the combined tables include (Active), which the views read."""
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
        if remove_copy(orphan):
            with _store_jobs_guard:
                job['removed'] += 1
    for dataset_id in changes['tables']:
        drop_copied_table(repository, dataset_id)
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
        if only_copies(repository.db_path):
            drop_copied_table(repository, cdr['id'])
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

    def combined_tables_busy(workspace_id: str) -> bool:
        with core.AUTO_CALCULATED_FIELD_JOBS_LOCK:
            return any(job.get('workspace_id') == workspace_id and job.get('status') in {'queued', 'processing'}
                       for job in core.AUTO_CALCULATED_FIELD_JOBS.values())

    def copy_when_idle() -> None:
        repository = active_repository()
        if repository is None or not AUTOMATIC:
            return
        job = store_job(repository.db_path)
        if job and job['status'] in {'queued', 'processing'}:
            return
        # The combined tables whose CDRs the copies all hold go, while no update of the combined tables runs.
        if only_copies(repository.db_path) and not combined_tables_busy(core.active_workspace.id):
            emptied = [kind for kind in CDR_KINDS if empty_combined_table(repository, kind)]
            if emptied:
                repository.try_add_log('system', 'cdr_store_combined_emptied', json.dumps({'kinds': emptied}))
        changes = store_changes(repository.db_path)
        if (changes['pending'] or changes['orphans'] or changes['tables']
                or catalog_outdated(repository.db_path, included_cdrs(repository))):
            queue_store_sync(repository, core.BACKGROUND_TASK_SCHEDULER, core.APP_SHUTTING_DOWN.is_set)

    def tasks(workspace: Any) -> list[dict[str, Any]]:
        return store_tasks(workspace.database_path, f'cdr-store:{workspace.id}')

    core.register_idle_task(copy_when_idle, STORE_IDLE_SECONDS)
    core.BACKGROUND_TASK_PROVIDERS.append(tasks)


# ---------------------------------------------------------------------------------------------------------------------
# Reading a copy back: the frame pandas.read_sql_query returns from the SQLite table of the CDR.

def _raw(database_path: Any, kind: str, dataset_id: int, columns: list[str], rowids: list[int] | None = None,
         rowid_range: tuple[int, int] | None = None, first: int | None = None) -> tuple[dict[str, tuple[str, Any]], int]:
    """The values of some physical columns of one CDR (its ``first`` rows, with it), in row id order, before pandas types
    them: for each column ('int', Int64 array), ('real', float64 array with NaN for no value), ('text', array of strings
    and None) or ('object', array of Python values of several types), and the number of rows."""
    import duckdb

    root = store_root(database_path)
    manifest = read_manifest(manifest_file(root, kind, dataset_id))
    if manifest is None or not cdr_folder(root, kind, dataset_id).is_dir():
        raise LookupError(f'The columnar copy of CDR {dataset_id} is not ready.')
    # The columns of the CDR, and those the copy adds.
    types = {**dict(manifest['columns']), ROWID: 'BIGINT', DATASET_ID: 'BIGINT', NR_MODE: 'VARCHAR'}
    missing = [column for column in columns if column not in types]
    if missing:
        raise KeyError(f'The CDR {dataset_id} has no column {missing[0]}.')
    wanted = list(dict.fromkeys(columns))
    parts = [quote(column) for column in stored_parts(wanted, types)]
    source = _sql_text(cdr_parts(root, kind, dataset_id))
    duck = duckdb.connect()
    try:
        where = ''
        if rowids is not None:
            duck.register('wanted', pd.DataFrame({'rowid': pd.Series(list(rowids), dtype='int64')}))
            where = f'WHERE {quote(ROWID)} IN (SELECT rowid FROM wanted)'
        elif rowid_range is not None:
            where = f'WHERE {quote(ROWID)} > {int(rowid_range[0])} AND {quote(ROWID)} <= {int(rowid_range[1])}'
        raw = duck.execute(f'SELECT {", ".join(parts) or quote(ROWID)} FROM read_parquet({source}) {where} '
                           f'ORDER BY {quote(ROWID)}{f" LIMIT {int(first)}" if first is not None else ""}').df()
    finally:
        duck.close()
    return copy_values(raw, wanted, types), len(raw)


def stored_parts(columns: list[str], types: dict[str, str]) -> list[str]:
    """The columns of a copy that hold ``columns``: each, and its integer and real companions."""
    parts = []
    for column in columns:
        parts.append(column)
        if types[column].startswith('MIXED:'):
            parts.extend(prefix + column for prefix, part in ((INT_PREFIX, 'I'), (REAL_PREFIX, 'R')) if part in types[column])
        elif types[column] == 'DOUBLE:I':
            parts.append(INT_PREFIX + column)
    return parts


def copy_values(raw: pd.DataFrame, wanted: list[str], types: dict[str, str]) -> dict[str, tuple[str, Any]]:
    """The values of ``wanted`` columns of a frame DuckDB read from a copy (with their companions, see stored_parts),
    as _raw gives them."""
    values: dict[str, tuple[str, Any]] = {}
    for column in wanted:
        column_type = types[column]
        if column_type == 'BIGINT':
            values[column] = ('int', raw[column].astype('Int64'))
        elif column_type == 'DOUBLE':
            values[column] = ('real', raw[column].astype('float64').to_numpy())
        elif column_type == 'DOUBLE:I':
            # The reals, and the integers as integers, in one column of Python values.
            numbers = raw[column].astype(object).to_numpy()
            integers = raw[INT_PREFIX + column]
            present = integers.notna().to_numpy()
            numbers[present] = [int(number) for number in integers[present]]
            numbers[pd.isna(numbers)] = None
            values[column] = ('object', numbers)
        elif column_type.startswith('MIXED:'):
            # The text, integers and reals of the column back in one column of Python values.
            mixed = raw[column].astype(object).to_numpy()
            for prefix, part, cast in ((INT_PREFIX, 'I', int), (REAL_PREFIX, 'R', float)):
                if part in column_type:
                    numbers = raw[prefix + column]
                    present = numbers.notna().to_numpy()
                    mixed[present] = [cast(number) for number in numbers[present]]
            mixed[pd.isna(mixed)] = None
            values[column] = ('object', mixed)
        else:
            text_values = raw[column].astype(object).to_numpy()
            text_values[pd.isna(text_values)] = None
            values[column] = ('text', text_values)
    return values


def _python_values(part: tuple[str, Any]) -> Any:
    """A raw column as an array of the Python values SQLite gives (None for no value)."""
    tag, values = part
    if tag == 'int':
        return values.to_numpy(dtype=object, na_value=None)
    if tag == 'real':
        result = values.astype(object)
        result[pd.isna(values)] = None
        return result
    return values


def _typed(parts: list[tuple[str, Any]], length: int) -> Any:
    """Columns of several CDRs as one column typed as pandas.read_sql_query types the values of all of them: no value at
    all gives objects (None), integers alone int64 (float64 with a missing value), numbers float64, anything else
    objects with the Python type of each value."""
    from pandas.core.internals.construction import convert_object_array

    tags = {tag for tag, _values in parts}
    if tags <= {'int', 'real'} and parts:
        numbers = pd.concat([pd.Series(values, dtype='Int64' if tag == 'int' else 'float64') for tag, values in parts],
                            ignore_index=True)
        if numbers.isna().all():
            return np.full(length, None, dtype=object)
        if tags == {'int'} and not numbers.isna().any():
            return numbers.astype('int64').to_numpy()
        return numbers.astype('float64').to_numpy()
    values = np.concatenate([_python_values(part) for part in parts]) if parts else np.empty(0, dtype=object)
    if all(value is None for value in values):
        return np.full(length, None, dtype=object)
    return convert_object_array([values.astype(object)], dtype=None, coerce_float=True)[0]


def read_cdr(database_path: Any, kind: str, dataset_id: int, columns: list[str], *,
             rowids: list[int] | None = None) -> pd.DataFrame:
    """The columns of one CDR as ``pandas.read_sql_query`` returns them from its SQLite table in row id order (only the
    rows ``rowids`` when given): the same values, with the same Python types and dtypes."""
    values, length = _raw(database_path, kind, dataset_id, columns, rowids)
    return pd.DataFrame({column: _typed([values[column]], length) for column in columns}, columns=list(columns),
                        index=range(length))


def cdr_columns(database_path: Any, kind: str, dataset_id: int, columns: list[str]) -> dict[str, Any]:
    """The Python values sqlite3 gives for ``columns`` of every row of one CDR, read from its copy: an array per column, in
    row id order."""
    values, _length = _raw(database_path, kind, dataset_id, columns)
    return {column: _python_values(values[column]) for column in dict.fromkeys(columns)}


def coalesced_frame(database_path: Any, kind: str, dataset_id: int, outputs: list[tuple[str, list[str]]],
                    required: list[str]) -> pd.DataFrame:
    """The frame ``pandas.read_sql_query`` gives for ``SELECT COALESCE(<columns>) AS <alias>, ... FROM dataset_rows_<id>
    WHERE <alias> IS NOT NULL AND ...`` (the ``required`` aliases; an alias of no column is NULL), read from the copy of the
    CDR: the same rows, in row id order, with the same values and types."""
    from pandas.io.sql import _wrap_result

    physical = list(dict.fromkeys(column for _alias, columns in outputs for column in columns))
    if physical:
        values = cdr_columns(database_path, kind, dataset_id, physical)
        length = len(values[physical[0]])
    else:
        values, length = {}, int((read_manifest(manifest_file(store_root(database_path), kind, dataset_id)) or {}).get('rows') or 0)
    results: dict[str, np.ndarray] = {}
    for alias, columns in outputs:
        merged = np.full(length, None, dtype=object)
        for column in columns:
            # The first column with a value, as COALESCE takes it.
            empty = np.fromiter((value is None for value in merged), dtype=bool, count=length)
            merged[empty] = np.asarray(values[column], dtype=object)[empty]
        results[alias] = merged
    kept = np.ones(length, dtype=bool)
    for alias in required:
        kept &= np.fromiter((value is not None for value in results[alias]), dtype=bool, count=length)
    aliases = [alias for alias, _columns in outputs]
    return _wrap_result(list(zip(*(results[alias][kept].tolist() for alias in aliases))), aliases)


def rows_by_rowid(database_path: Any, kind: str, dataset_id: int, columns: list[str], rowids: Any) -> dict[int, tuple[Any, ...]]:
    """The Python values sqlite3 gives for ``columns`` of the rows ``rowids`` of one CDR, read from its copy, by row id (the
    row ids it does not have are left out)."""
    wanted = sorted({int(rowid) for rowid in rowids})
    values, length = _raw(database_path, kind, dataset_id, [ROWID, *columns], wanted)
    found = [_python_values(values[column]) for column in [ROWID, *columns]]
    return {int(found[0][index]): tuple(column[index] for column in found[1:]) for index in range(length)}


def fresh_rows_by_rowid(database_path: Any, dataset_id: int, columns: list[str], rowids: Any) -> dict[int, tuple[Any, ...]] | None:
    """``rows_by_rowid`` when the copy of the CDR holds its rows as they are now; None otherwise."""
    kind = fresh_kind(database_path, dataset_id)
    return rows_by_rowid(database_path, kind, dataset_id, columns, rowids) if kind else None


def resolve_column(existing: Any, requested: str) -> str | None:
    """The column of a table a requested name reads, as the CDR tables resolve it: the same name, else the same name in
    another case, else the same name with other separators (see Repository._resolve_dataset_row_column_name)."""
    from src.modules.column_names import column_identity

    existing = set(existing)
    if requested in existing:
        return requested
    lowered = str(requested).strip().lower()
    case_matches = [column for column in existing if str(column).strip().lower() == lowered]
    if case_matches:
        return next((column for column in case_matches if column == lowered), None) or sorted(case_matches)[0]
    identity = column_identity(requested)
    matches = [column for column in existing if column_identity(column) == identity]
    return sorted(matches)[0] if matches else None


def read_cdrs(database_path: Any, kind: str, dataset_ids: Any, columns: list[str], *,
              existing_columns: Any = None) -> pd.DataFrame:
    """The rows of some CDRs of one type as ``pandas.read_sql_query`` returns them from their combined table with
    ``SELECT <column> AS <requested> ... WHERE dataset_id IN (...)``: CDR after CDR by dataset id and row, each requested
    name resolved among ``existing_columns`` (the columns of the combined table; by default those of the CDRs) and read
    from the column of each CDR with the same identity, ``NR_Mode`` from the CDR when it has no such column,
    ``dataset_id`` and ``source_row_id`` from the copy, typed over every CDR as one result."""
    from src.modules.column_names import column_identity

    root = store_root(database_path)
    ids = sorted({int(item) for item in dataset_ids})
    manifests = {dataset_id: read_manifest(manifest_file(root, kind, dataset_id)) for dataset_id in ids}
    if any(manifest is None for manifest in manifests.values()):
        raise LookupError(f'The columnar copy of a CDR of {sorted(i for i, m in manifests.items() if m is None)} is not ready.')
    if existing_columns is None:
        existing_columns = {column for manifest in manifests.values() for column, _type in manifest['columns']}
    existing_columns = set(existing_columns) | {'dataset_id', 'source_row_id', 'NR_Mode'}
    selected = [(requested, physical) for requested in columns
                if (physical := resolve_column(existing_columns, requested)) is not None]
    parts: dict[str, list[tuple[str, Any]]] = {requested: [] for requested, _physical in selected}
    total = 0
    for dataset_id in ids:
        manifest = manifests[dataset_id]
        # Each combined column takes its values from the column of the CDR with the same identity (the last one).
        lookup = {column_identity(column): column for column, _type in manifest['columns']}
        sources = {requested: lookup.get(column_identity(physical)) for requested, physical in selected}
        wanted = [source for requested, source in sources.items()
                  if source and column_identity(requested) not in {'datasetid', 'sourcerowid'}]
        nr_mode = next((physical for requested, physical in selected if column_identity(physical) == 'nrmode'), None)
        values, length = _raw(database_path, kind, dataset_id, [*wanted, ROWID, NR_MODE])
        for requested, physical in selected:
            identity = column_identity(physical)
            if identity == 'datasetid':
                parts[requested].append(('int', pd.Series([dataset_id] * length, dtype='Int64')))
            elif identity == 'sourcerowid':
                parts[requested].append(values[ROWID])
            elif physical == nr_mode and sources[requested] is None:
                parts[requested].append(values[NR_MODE])
            elif sources[requested] is not None:
                parts[requested].append(values[sources[requested]])
            else:
                parts[requested].append(('object', np.full(length, None, dtype=object)))
        total += length
    return pd.DataFrame({requested: _typed(parts[requested], total) for requested, _physical in selected},
                        columns=[requested for requested, _physical in selected], index=range(total))


def copied_rows(database_path: Any, dataset_id: int) -> int:
    """How many rows the copy of a CDR holds (0 without a copy)."""
    with sqlite3.connect(database_path, timeout=30) as connection:
        row = connection.execute('SELECT dataset_kind FROM dataset_profiles WHERE dataset_id = ?', (int(dataset_id),)).fetchone()
    kind = str(row[0] or '').casefold() if row else ''
    manifest = read_manifest(manifest_file(store_root(database_path), kind, int(dataset_id))) if kind in CDR_KINDS else None
    return int(manifest['rows']) if manifest else 0


def fresh_kind(database_path: Any, dataset_id: int) -> str | None:
    """The type of a CDR whose copy holds its rows as they are now (None when it has no such copy)."""
    if int(dataset_id) not in fresh_copies(database_path, [dataset_id]):
        return None
    with sqlite3.connect(database_path, timeout=30) as connection:
        row = connection.execute('SELECT dataset_kind FROM dataset_profiles WHERE dataset_id = ?', (int(dataset_id),)).fetchone()
    return str(row[0]).casefold() if row else None


def _plan_hint(connection: sqlite3.Connection, table: str, query: str, params: Any) -> str | None:
    """How SQLite reads ``table`` for ``query``: 'NOT INDEXED' for a scan in row id order, 'INDEXED BY <index>' for one
    index (rows in its order), or None for any other plan."""
    import re

    details = [str(row[3]) for row in connection.execute(f'EXPLAIN QUERY PLAN {query}', list(params)).fetchall()]
    own = [detail for detail in details if re.search(rf'\b(SCAN|SEARCH) {re.escape(table)}\b', detail)]
    if len(own) != 1:
        return None
    if re.fullmatch(rf'SCAN {re.escape(table)}', own[0]):
        return 'NOT INDEXED'
    match = re.fullmatch(rf'SEARCH {re.escape(table)} USING (?:COVERING )?INDEX (\S+) \(.*\)', own[0])
    return f'INDEXED BY {quote(match.group(1))}' if match else None


def _plan_rowids(database_path: Any, kind: str, dataset_id: int, query: str, where: str, params: Any,
                 filter_columns: Any) -> list[int] | None:
    """The row ids ``query`` (a SELECT on ``dataset_rows_<id>`` with ``where``) reads on the workspace database, in the
    order it reads them, found on the copy: SQLite evaluates the WHERE (its subqueries reading the workspace database,
    attached read-only) on a table in memory holding only ``filter_columns``, forced into the plan of the workspace
    database (the same expression index, or a scan). None when that plan is not one index or a scan, or the WHERE reads
    a column it was not given."""
    table = f'dataset_rows_{int(dataset_id)}'
    source = f'file:{Path(str(database_path)).resolve()}?mode=ro'
    with sqlite3.connect(source, uri=True, timeout=30) as workspace:
        hint = _plan_hint(workspace, table, query, params)
        index_sql = None
        if hint and hint.startswith('INDEXED BY'):
            index_sql = workspace.execute("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
                                          (hint[len('INDEXED BY '):].strip('"').replace('""', '"'),)).fetchone()
            index_sql = index_sql[0] if index_sql else None
    if hint is None or (hint.startswith('INDEXED BY') and not index_sql):
        return None
    filters = list(dict.fromkeys(filter_columns))
    order_keys = _index_columns(index_sql, table) if index_sql else []
    if order_keys is not None and not re.search(r'\b(_?_?rowid|oid|_rowid_)\b', str(where), re.IGNORECASE):
        try:
            return _plan_rowids_by_combination(source, table, *_filter_combinations(database_path, kind, dataset_id, filters),
                                               filters, where, params, order_keys)
        except sqlite3.OperationalError:
            return None
    values, _length = _raw(database_path, kind, dataset_id, [ROWID, *filters])
    memory = sqlite3.connect('file::memory:', uri=True)
    try:
        memory.execute('ATTACH DATABASE ? AS workspace', (source,))
        memory.execute(f'CREATE TABLE main.{quote(table)} ({quote(ROWID)} INTEGER PRIMARY KEY'
                       + ''.join(f', {quote(column)}' for column in filters) + ')')
        memory.executemany(f'INSERT INTO main.{quote(table)} VALUES ({", ".join("?" * (len(filters) + 1))})',
                           zip(*(_python_values(values[column]) for column in [ROWID, *filters])))
        if index_sql:
            memory.execute(index_sql)
        return [row[0] for row in memory.execute(f'SELECT {quote(ROWID)} FROM main.{quote(table)} {hint} WHERE {where}',
                                                  list(params)).fetchall()]
    except sqlite3.OperationalError:
        return None
    finally:
        memory.close()


def _index_columns(index_sql: str, table: str) -> list[str] | None:
    """The expressions of the columns of ``CREATE INDEX ... ON <table>(<columns>)``, in their order; None for an index
    whose order they do not tell alone (a partial index, a collation or a descending column)."""
    match = re.match(rf'\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+.+?\s+ON\s+(?:"?{re.escape(table)}"?)\s*\((.*)\)\s*$',
                     str(index_sql), re.IGNORECASE | re.DOTALL)
    if not match or re.search(r'\b(COLLATE|DESC|WHERE)\b', match.group(1), re.IGNORECASE):
        return None
    columns, depth, current, quoted = [], 0, '', None
    for character in match.group(1):
        if quoted:
            quoted = None if character == quoted else quoted
        elif character in '"\'`[':
            quoted = ']' if character == '[' else character
        elif character == '(':
            depth += 1
        elif character == ')':
            depth -= 1
        elif character == ',' and depth == 0:
            columns.append(current.strip())
            current = ''
            continue
        current += character
    columns.append(current.strip())
    return [re.sub(r'\s+ASC\s*$', '', column, flags=re.IGNORECASE) for column in columns if column]


def _filter_combinations(database_path: Any, kind: str, dataset_id: int, columns: list[str]):
    """The row ids of a CDR in row id order, the combination of values of ``columns`` of each row (0, 1...), and the
    values of each combination (for each column, its Python values as SQLite gives them), worked out by DuckDB on the
    copy without making a Python value of every row."""
    import duckdb

    root = store_root(database_path)
    manifest = read_manifest(manifest_file(root, kind, dataset_id))
    if manifest is None or not cdr_folder(root, kind, dataset_id).is_dir():
        raise LookupError(f'The columnar copy of CDR {dataset_id} is not ready.')
    types = {**dict(manifest['columns']), ROWID: 'BIGINT', DATASET_ID: 'BIGINT', NR_MODE: 'VARCHAR'}
    missing = [column for column in columns if column not in types]
    if missing:
        raise KeyError(f'The CDR {dataset_id} has no column {missing[0]}.')
    # A value is the tuple of its parts (a column and its integer and real companions).
    parts = [quote(part) for part in stored_parts(list(columns), types)]
    source = _sql_text(cdr_parts(root, kind, dataset_id))
    duck = duckdb.connect()
    try:
        if not parts:
            rowids = duck.execute(f'SELECT {quote(ROWID)} FROM read_parquet({source}) ORDER BY {quote(ROWID)}').fetchnumpy()[ROWID]
            return np.asarray(rowids, dtype=np.int64), np.zeros(len(rowids), dtype=np.int64), []
        listed = ', '.join(parts)
        duck.execute(f'CREATE TEMP TABLE combinations AS SELECT row_number() OVER () - 1 AS "__combination", * '
                     f'FROM (SELECT DISTINCT {listed} FROM read_parquet({source}))')
        distinct = duck.execute(f'SELECT {listed} FROM combinations ORDER BY "__combination"').df()
        rows = duck.execute(
            f'SELECT p.{quote(ROWID)} AS rowid, c."__combination" AS combination FROM read_parquet({source}) p '
            f'JOIN combinations c ON ' + ' AND '.join(f'p.{part} IS NOT DISTINCT FROM c.{part}' for part in parts)
            + f' ORDER BY p.{quote(ROWID)}').fetchnumpy()
    finally:
        duck.close()
    values = copy_values(distinct, list(columns), types)
    return (np.asarray(rows['rowid'], dtype=np.int64), np.asarray(rows['combination'], dtype=np.int64),
            [_python_values(values[column]) for column in columns])


def _plan_rowids_by_combination(source: str, table: str, rowids: Any, combination: Any, columns: list[Any],
                                filters: list[str], where: str, params: Any, order_keys: list[str]) -> list[int]:
    """_plan_rowids from the distinct combinations of the filter columns (see _filter_combinations): the WHERE of a row
    (and the key of the index it is read through) only depends on its values of those columns, so SQLite evaluates each
    combination once instead of each row. The rows are those whose combination it keeps, in row id order, or in the
    order of the index (its key, then the row id) when the plan reads one."""
    if not len(rowids):
        return []
    count = int(combination.max()) + 1
    memory = sqlite3.connect('file::memory:', uri=True)
    try:
        memory.execute('ATTACH DATABASE ? AS workspace', (source,))
        memory.execute(f'CREATE TABLE main.{quote(table)} ({quote(ROWID)} INTEGER PRIMARY KEY'
                       + ''.join(f', {quote(column)}' for column in filters) + ')')
        memory.executemany(f'INSERT INTO main.{quote(table)} VALUES ({", ".join("?" * (len(filters) + 1))})',
                           ((index, *(column[index] for column in columns)) for index in range(count)))
        kept = np.zeros(count, dtype=bool)
        kept[[row[0] for row in memory.execute(f'SELECT {quote(ROWID)} FROM main.{quote(table)} WHERE {where}',
                                               list(params)).fetchall()]] = True
        rank = np.zeros(count, dtype=np.int64)
        if order_keys:
            for index, key_rank in memory.execute(
                    f'SELECT {quote(ROWID)}, DENSE_RANK() OVER (ORDER BY {", ".join(order_keys)}) FROM main.{quote(table)}'):
                rank[index] = key_rank
    finally:
        memory.close()
    rows = np.flatnonzero(kept[combination])
    order = np.lexsort((rowids[rows], rank[combination[rows]]))
    return rowids[rows[order]].tolist()


def query_cdr(database_path: Any, kind: str, dataset_id: int, selected: list[tuple[str, str]], where: str = '',
              params: Any = (), filter_columns: Any = ()) -> pd.DataFrame | None:
    """What ``pandas.read_sql_query`` returns for ``SELECT <physical> AS <requested> ... FROM dataset_rows_<id>
    [WHERE <where>]`` on the workspace database, read from the copy of the CDR (see _plan_rowids for the rows and their
    order; ``filter_columns`` are the columns the WHERE reads). None when the copy cannot give them."""
    physical = list(dict.fromkeys(column for _requested, column in selected))

    def frame_of(values: dict[str, tuple[str, Any]], length: int, order: Any = None) -> pd.DataFrame:
        # Each column is put in ``order`` before the frame is built, so it is built once.
        typed = {column: _typed([values[column]], length) for column in physical}
        if order is not None:
            order = np.asarray(order, dtype=np.intp)
            typed = {column: array.take(order) for column, array in typed.items()}
            length = len(order)
        return pd.DataFrame({requested: typed[column] for requested, column in selected},
                            columns=[requested for requested, _column in selected], index=range(length))

    if not where:
        values, length = _raw(database_path, kind, dataset_id, physical)
        return frame_of(values, length)
    table = f'dataset_rows_{int(dataset_id)}'
    query = f'SELECT {", ".join(f"{quote(column)} AS {quote(requested)}" for requested, column in selected)} FROM {quote(table)} WHERE {where}'
    rowids = _plan_rowids(database_path, kind, dataset_id, query, where, params, filter_columns)
    if rowids is None:
        return None
    values, length = _raw(database_path, kind, dataset_id, physical, rowids)
    # The rows come back in row id order: put them in the order of the plan.
    position = {rowid: index for index, rowid in enumerate(sorted(rowids))}
    return frame_of(values, length, [position[rowid] for rowid in rowids])


def plan_rows(database_path: Any, kind: str, dataset_id: int, selected: list[tuple[str, str]], where: str = '',
              params: Any = (), filter_columns: Any = ()) -> list[int] | None:
    """The row ids query_cdr reads, in its order (every row of the CDR without ``where``); None when the copy cannot
    give them."""
    if not where:
        root = store_root(database_path)
        return _filter_combinations(database_path, kind, dataset_id, [])[0].tolist() if read_manifest(
            manifest_file(root, kind, dataset_id)) is not None else None
    table = f'dataset_rows_{int(dataset_id)}'
    query = f'SELECT {", ".join(f"{quote(column)} AS {quote(requested)}" for requested, column in selected)} FROM {quote(table)} WHERE {where}'
    return _plan_rowids(database_path, kind, dataset_id, query, where, params, filter_columns)


def read_kind_frame(database_path: Any, kind: str, parts: list[dict[str, Any]]) -> tuple[pd.DataFrame, np.ndarray]:
    """The rows of several CDRs of one type as ``pandas.concat`` (``ignore_index``, ``sort=False``) of their query_cdr
    frames gives them, each part (``dataset_id``, ``selected`` (requested, physical) columns, ``rowids`` in their
    order, ``constants`` (column: value added after them) and ``transforms`` (column: function of each value)) in
    turn, and the part of each row. The text columns (VARCHAR in every CDR) come as Categoricals of the same values,
    read by DuckDB without making a Python value of every row; the others as query_cdr types them."""
    import duckdb

    root = store_root(database_path)
    manifests = []
    for part in parts:
        manifest = read_manifest(manifest_file(root, kind, int(part['dataset_id'])))
        if manifest is None or not cdr_folder(root, kind, int(part['dataset_id'])).is_dir():
            raise LookupError(f"The columnar copy of CDR {part['dataset_id']} is not ready.")
        manifests.append({**dict(manifest['columns']), ROWID: 'BIGINT', DATASET_ID: 'BIGINT', NR_MODE: 'VARCHAR'})
    # The columns of the concatenation, in its order.
    order: list[str] = []
    for part in parts:
        for name in [*(requested for requested, _physical in part['selected']), *part.get('constants', {})]:
            if name not in order:
                order.append(name)
    text = [name for name in order if not any(name in part.get('constants', {}) for part in parts)
            and all(types.get(physical) == 'VARCHAR' for part, types in zip(parts, manifests)
                    for requested, physical in part['selected'] if requested == name)]
    sizes = np.asarray([len(part['rowids']) for part in parts], dtype=np.int64)
    part_of_row = np.repeat(np.arange(len(parts), dtype=np.int64), sizes)
    length = int(sizes.sum())
    columns: dict[str, Any] = {}
    if text and length:
        duck = duckdb.connect()
        try:
            duck.register('wanted', pd.DataFrame({
                'part': part_of_row,
                'position': np.arange(length, dtype=np.int64),
                'rowid': np.concatenate([np.asarray(part['rowids'], dtype=np.int64) for part in parts]),
            }))
            selects = []
            for index, (part, types) in enumerate(zip(parts, manifests)):
                physical = {requested: column for requested, column in part['selected']}
                listed = ''.join(f', {quote(physical[name])} AS {quote(name)}' for name in text if name in physical)
                selects.append(f'SELECT {index} AS "__part", {quote(ROWID)}{listed} '
                               f'FROM read_parquet({_sql_text(cdr_parts(root, kind, int(part["dataset_id"])))})')
            duck.execute(f'CREATE TEMP TABLE kind_rows AS SELECT w.position, u.* FROM ({" UNION ALL BY NAME ".join(selects)}) u '
                         f'JOIN wanted w ON u."__part" = w.part AND u.{quote(ROWID)} = w.rowid')
            present = {row[0] for row in duck.execute("SELECT column_name FROM duckdb_columns() WHERE table_name = 'kind_rows'").fetchall()}
            casts, plain = [], []
            for index, name in enumerate(text):
                if name not in present:
                    continue
                count = duck.execute(f'SELECT approx_count_distinct({quote(name)}) FROM kind_rows').fetchone()[0]
                if count > max(1000, length // 20):
                    # Nearly a value per row (times, identifiers): a Categorical would not save anything.
                    plain.append(name)
                    casts.append(quote(name))
                elif count:
                    duck.execute(f'CREATE TYPE "__text_{index}" AS ENUM (SELECT DISTINCT {quote(name)} FROM kind_rows '
                                 f'WHERE {quote(name)} IS NOT NULL ORDER BY 1)')
                    casts.append(f'CAST({quote(name)} AS "__text_{index}") AS {quote(name)}')
            read = duck.execute(f'SELECT {", ".join(casts) or "1 AS one"} FROM kind_rows ORDER BY position').df()
        finally:
            duck.close()
        for name in text:
            if name in plain:
                # As query_cdr types text: the strings, None for no value.
                values = read[name].to_numpy(dtype=object)
                values[pd.isna(values)] = None
                columns[name] = values
            elif name in read.columns:
                columns[name] = pd.Categorical(read[name]).as_unordered()
            else:
                columns[name] = pd.Categorical([None] * length, categories=[])
    elif text:
        columns.update({name: pd.Categorical([], categories=[]) for name in text})
    others = [name for name in order if name not in text]
    if others:
        frames = []
        for part in parts:
            physical = [(requested, column) for requested, column in part['selected'] if requested in others]
            frame = pd.DataFrame(index=range(len(part['rowids'])))
            if physical and len(part['rowids']):
                wanted = list(dict.fromkeys(column for _requested, column in physical))
                values, count = _raw(database_path, kind, int(part['dataset_id']), wanted, list(part['rowids']))
                # The rows come back in row id order: put them in the order of the plan.
                positions = np.searchsorted(np.sort(np.asarray(part['rowids'], dtype=np.int64)),
                                            np.asarray(part['rowids'], dtype=np.int64))
                typed = {column: _typed([values[column]], count).take(positions) for column in wanted}
                frame = pd.DataFrame({requested: typed[column] for requested, column in physical},
                                     columns=[requested for requested, _column in physical], index=range(len(positions)))
            elif physical:
                frame = pd.DataFrame({requested: np.empty(0, dtype=object) for requested, _column in physical})
            for name, value in part.get('constants', {}).items():
                frame[name] = value
            frames.append(frame)
        combined = pd.concat(frames, ignore_index=True, sort=False)
        for name in others:
            columns[name] = combined[name].to_numpy() if name in combined else np.full(length, np.nan)
    frame = pd.DataFrame({name: columns[name] for name in order}, columns=order, index=range(length))
    for name in order:
        transforms = [part.get('transforms', {}).get(name) for part in parts]
        if not any(transforms):
            continue
        if name not in text:
            values = frame[name].copy()
            for index, function in enumerate(transforms):
                rows = (part_of_row == index) & frame[name].notna().to_numpy()
                if function is not None and rows.any():
                    values[rows] = frame[name][rows].map(
                        {value: function(value) for value in frame[name][rows].unique()})
            frame[name] = values
            continue
        # A function of each value of each part: computed once per value and part.
        values = frame[name].cat
        keys = part_of_row * (len(values.categories) + 1) + (values.codes.to_numpy().astype(np.int64) + 1)
        unique, inverse = np.unique(keys, return_inverse=True)
        mapped = []
        for key in unique.tolist():
            part_index, code = divmod(key, len(values.categories) + 1)
            value = values.categories[code - 1] if code else None
            function = transforms[part_index]
            mapped.append(function(value) if function is not None and value is not None else value)
        frame[name] = pd.Categorical(np.asarray(mapped, dtype=object)[inverse]).as_unordered()
    return frame, part_of_row


def query_cdr_rows(database_path: Any, kind: str, dataset_id: int, query: str, selected: list[tuple[str, str]],
                   where: str = '', params: Any = (), filter_columns: Any = (), rowid_alias: str | None = None,
                   ) -> list[dict[str, Any]] | None:
    """The rows ``query`` (``SELECT [rowid AS <rowid_alias>,] <physical> AS <alias> ... FROM dataset_rows_<id> [WHERE
    <where>]``) gives on the workspace database, read from the copy of the CDR: one dict per row with the Python value
    sqlite3 gives for each alias, in the same order. None when the copy cannot give them."""
    physical = list(dict.fromkeys(column for _alias, column in selected))
    rowids = _plan_rowids(database_path, kind, dataset_id, query, where, params, filter_columns) if where else None
    if where and rowids is None:
        return None
    values, length = _raw(database_path, kind, dataset_id, [ROWID, *physical], rowids)
    columns = {column: _python_values(values[column]) for column in [ROWID, *physical]}
    order = range(length)
    if rowids is not None:
        position = {rowid: index for index, rowid in enumerate(columns[ROWID])}
        order = [position[rowid] for rowid in rowids]
    rows = []
    for index in order:
        row = {alias: columns[column][index] for alias, column in selected}
        if rowid_alias:
            row[rowid_alias] = columns[ROWID][index]
        rows.append(row)
    return rows
