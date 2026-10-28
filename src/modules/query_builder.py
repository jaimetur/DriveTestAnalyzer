"""Read-only SQL workspace queries over explicitly selected CDR sources."""

from __future__ import annotations

import csv
import io
import math
import re
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from src.modules import cdr_store
from src.modules.column_names import column_identity, vendor_filter_column

MAX_PREVIEW_ROWS = 50
MAX_FILTER_VALUES = 500
MAX_FILTER_OPTIONS = 200
_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _string_literal(value: str) -> str:
    """Return a SQLite string literal, escaping embedded single quotes."""
    return "'" + value.replace("'", "''") + "'"


def rename_identifiers(query: str, renames: dict[str, str]) -> str:
    """A saved query with renamed columns (a renamed Auto-calculated Field): each identifier that names an old column,
    bare or quoted ("…", […] or `…`, without case differences as SQLite compares them), takes the new name; string
    literals and comments are left as they are."""
    targets = {str(old).casefold(): str(new) for old, new in renames.items() if str(old).strip() and str(new).strip()}
    if not targets:
        return query

    def renamed(name: str) -> str | None:
        new = targets.get(name.casefold())
        return None if new is None else (new if _IDENTIFIER.match(new) else _quote(new))

    parts: list[str] = []
    index, length = 0, len(query)
    while index < length:
        char = query[index]
        if char == "'" or query.startswith('--', index) or query.startswith('/*', index):
            # String literals and comments stay as they are.
            if char == "'":
                end = index + 1
                while end < length and not (query[end] == "'" and not query.startswith("''", end)):
                    end += 2 if query.startswith("''", end) else 1
                end += 1
            elif char == '-':
                end = query.find('\n', index)
                end = length if end < 0 else end
            else:
                end = query.find('*/', index + 2)
                end = length if end < 0 else end + 2
            parts.append(query[index:end])
            index = end
        elif char in '"[`':
            closing = {'"': '"', '[': ']', '`': '`'}[char]
            end = index + 1
            while end < length and not (query[end] == closing and not (closing == '"' and query.startswith('""', end))):
                end += 2 if closing == '"' and query.startswith('""', end) else 1
            inner = query[index + 1:end]
            name = inner.replace('""', '"') if closing == '"' else inner
            new = targets.get(name.casefold())
            parts.append(query[index:end + 1] if new is None else _quote(new))
            index = end + 1
        elif char.isdigit():
            # A number (or a word that starts with one, such as 3G) is not a column name.
            end = index + 1
            while end < length and (query[end].isalnum() or query[end] in '_.'):
                end += 1
            parts.append(query[index:end])
            index = end
        elif char.isalpha() or char == '_':
            end = index + 1
            while end < length and (query[end].isalnum() or query[end] == '_'):
                end += 1
            word = query[index:end]
            parts.append(renamed(word) or word)
            index = end
        else:
            parts.append(char)
            index += 1
    return ''.join(parts)


def normalize_query(query: str) -> str:
    query = str(query or '').strip().rstrip(';').strip()
    if not query:
        raise ValueError('Enter a SQL query.')
    if ';' in query or not re.match(r'^(?:select|with)\b', query, flags=re.I):
        raise ValueError('Only one SELECT query (optionally starting with WITH) is allowed.')
    return query


def _selected_views(connection: sqlite3.Connection, datasets: Iterable[dict[str, Any]],
                    given: dict[int, tuple[str, set[str]]] | None = None, seen: bool = False) -> list[str]:
    """Create one temporary union view per selected CDR kind.

    A view contains every physical source column, with NULL for a heading not
    present in one selected file. This preserves ad-hoc access to CDR fields
    without widening the persistent combined reporting tables. With ``given``
    the views are made again, each CDR in it read from its TEMP table (and its
    columns) instead of its empty table, and with ``seen`` noting the rows of
    those tables that each view gives (see _execute).
    """
    grouped: dict[str, list[dict[str, Any]]] = {'data': [], 'voice': [], 'speech': []}
    for dataset in datasets:
        kind = str(dataset['kind'])
        if kind in grouped:
            grouped[kind].append(dataset)
    created: list[str] = []
    for kind, rows in grouped.items():
        if not rows:
            continue
        if given is not None:
            connection.execute(f'DROP VIEW IF EXISTS temp.{_quote(f"selected_{kind}")}')
        schemas: dict[int, list[str]] = {}
        all_columns: list[str] = []
        for row in rows:
            table = f"dataset_rows_{int(row['id'])}"
            cols = [str(item[1]) for item in connection.execute(f'PRAGMA main.table_info({_quote(table)})')]
            schemas[int(row['id'])] = cols
            for column in cols:
                if column not in all_columns:
                    all_columns.append(column)
        selects: list[str] = []
        for row in rows:
            dataset_id = int(row['id'])
            table = f'main.{_quote(f"dataset_rows_{dataset_id}")}'
            known = set(schemas[dataset_id])
            where = ''
            if given and dataset_id in given:
                name, provided = given[dataset_id]
                table = f'temp.{_quote(name)}'
                known = {column for column in known if column.casefold() in provided}
                # A correlated subquery is evaluated after the other conditions of the row: it notes only the rows given.
                where = f' AS given_rows WHERE (SELECT {_SEEN_FUNCTION}({dataset_id}, given_rows.rowid))' if seen else ''
            values = [
                f'{dataset_id} AS source_dataset_id',
                f'{_string_literal(str(row["name"]))} AS source_dataset_name',
                'rowid AS source_row_id',
            ]
            values.extend(_quote(column) if column in known else f'NULL AS {_quote(column)}' for column in all_columns)
            selects.append(f"SELECT {', '.join(values)} FROM {table}{where}")
        view = f'selected_{kind}'
        connection.execute(f'CREATE TEMP VIEW {_quote(view)} AS ' + ' UNION ALL '.join(selects))
        created.append(view)
    return created


# A statement that reads the rows of its CDR tables once each, in one pass in row id order: its plan has no other steps.
_ONE_PASS_PLAN = re.compile(r'CO-ROUTINE .+|COMPOUND QUERY|LEFT-MOST SUBQUERY|UNION ALL|SCAN [^ ]+')
# Steps that need every row (aggregates, sorts, temporary tables and indexes).
_EVERY_ROW_OPCODES = frozenset({'AggStep', 'AggStep1', 'AggFinal', 'AggValue', 'AggInverse', 'SorterOpen', 'OpenEphemeral',
                                'OpenAutoindex'})
# The function the views call to note the rows they give, and how many rows it notes at most.
_SEEN_FUNCTION = 'query_builder_seen_row'
MAX_SEEN_ROWS = 20_000
# The rows of the CDR tables first given to a statement whose first rows are wanted, times its rows.
FIRST_ROWS_WINDOW = 5_000


def _cdr_reads(connection: sqlite3.Connection, sql: str, parameters: Any) -> tuple[dict[int, set[str]], list[int], bool]:
    """What SQLite reads of the CDR tables to run ``sql``, from its compiled statement (not run): the columns of each
    table (by dataset id, casefolded), those it reads on a cursor of the table and those of each of its indexes it
    opens; the tables in the order it opens them; and whether it reads their rows in one pass in row id order, each
    once, with no aggregate, sort, temporary table, index or join."""
    roots = {int(row[0]): (str(row[1]), str(row[2]), str(row[3])) for row in connection.execute(
        "SELECT rootpage, type, name, tbl_name FROM main.sqlite_master WHERE type IN ('table', 'index') "
        "AND tbl_name LIKE 'dataset\\_rows\\_%' ESCAPE '\\'") if str(row[3])[13:].isdigit()}
    names: dict[str, list[str]] = {}
    cursors: dict[int, tuple[str, str, int]] = {}
    reads: dict[int, set[str]] = {}
    order: list[int] = []
    one_pass = True
    for _address, opcode, p1, p2, p3, _p4, _p5, _comment in connection.execute(f'EXPLAIN {sql}', parameters).fetchall():
        if opcode in _EVERY_ROW_OPCODES:
            one_pass = False
        elif opcode in {'OpenRead', 'ReopenIdx'} and p3 == 0 and p2 in roots:
            kind, name, table = roots[p2]
            dataset_id = int(table[13:])
            cursors[p1] = (kind, table, dataset_id)
            reads.setdefault(dataset_id, set())
            if dataset_id not in order:
                order.append(dataset_id)
            if kind == 'index':
                one_pass = False
                reads[dataset_id] |= cdr_store.index_columns(connection, table)[name][2]
        elif opcode == 'Column' and cursors.get(p1, ('',))[0] == 'table':
            _kind, table, dataset_id = cursors[p1]
            columns = names.setdefault(table, [str(row[1]) for row in connection.execute(f'PRAGMA main.table_info({_quote(table)})')])
            if p2 < len(columns):
                reads[dataset_id].add(columns[p2].casefold())
    if one_pass and order:
        plan = connection.execute(f'EXPLAIN QUERY PLAN {sql}', parameters).fetchall()
        loops = [int(row[1]) for row in plan if str(row[3]).startswith('SCAN ')]
        one_pass = all(_ONE_PASS_PLAN.fullmatch(str(row[3])) for row in plan) and len(loops) == len(set(loops))
    return reads, order, one_pass


def _give_rows(connection: sqlite3.Connection, datasets: list[dict[str, Any]], sql: str, ids: list[int],
               columns: dict[int, set[str]], in_part: dict[int, tuple[set[str], Any]] | None = None,
               seen: bool = False, first: dict[int, int] | None = None) -> str:
    """The TEMP tables of the CDRs ``ids`` with ``columns`` from their copies (``first`` and ``in_part``: see
    cdr_store.provide_rows), in place of their empty tables, for the views and for ``sql`` where it names them
    (returned)."""
    for (name,) in connection.execute("SELECT name FROM temp.sqlite_master WHERE type = 'table' AND name LIKE 'cdr\\_rows\\_%' ESCAPE '\\'").fetchall():
        connection.execute(f'DROP TABLE temp.{_quote(name)}')
    given: dict[int, tuple[str, set[str]]] = {}
    for dataset_id in ids:
        name = f'cdr_rows_{dataset_id}_{uuid4().hex[:12]}'
        cdr_store.provide_rows(connection, dataset_id, columns[dataset_id], name, first=(first or {}).get(dataset_id),
                               in_part=(in_part or {}).get(dataset_id))
        given[dataset_id] = (name, {str(row[1]).casefold() for row in connection.execute(f'PRAGMA temp.table_info({_quote(name)})')})
        sql = cdr_store.table_reference(dataset_id).sub(f'temp.{_quote(name)}', sql)
    _selected_views(connection, datasets, given, seen=seen)
    return sql


def _execute(connection: sqlite3.Connection, database_path: Path, datasets: list[dict[str, Any]], sql: str,
             parameters: Any = (), first: int | None = None,
             choosing: tuple[str, Any] | None = None) -> tuple[sqlite3.Cursor, list[Any] | None]:
    """Run a statement of a query with the read-only authorizer, and with ``first`` fetch its first rows. Where the
    columnar copy of a CDR it reads is its only store (its table empty, see cdr_store), it is first given the rows of the
    columns it reads from the copy, in a TEMP table that the view of its type reads instead (and that the statement
    reads where it names the table itself).

    A statement whose first rows are wanted, that reads the CDR tables in one pass in row id order, runs twice: first
    with only the columns that choose its rows (those ``choosing``, the statement that counts them, reads), noting the
    rows the views give; then with every column it reads for those rows only. Both runs read the first rows of the
    tables (more each time until the statement gives its first rows, or every row), a prefix of the rows it reads when
    it reads them all: they give the same rows, in the same order."""
    emptied = cdr_store.shadow_ids(database_path)
    connection.set_authorizer(None)
    order: list[int] = []
    if emptied:
        _give_rows(connection, datasets, sql, [], {})
        try:
            reads, order, one_pass = _cdr_reads(connection, sql, parameters)
        except sqlite3.Error:
            # The statement fails as it is when it runs.
            order = []
    given_ids = [dataset_id for dataset_id in order if dataset_id in emptied]
    text = sql
    # (Only the views note the rows they give: not a statement that names the table of a CDR itself.)
    if (given_ids and first is not None and choosing is not None and one_pass
            and not any(cdr_store.table_reference(dataset_id).search(sql) for dataset_id in given_ids)):
        chosen, _order, _one_pass = _cdr_reads(connection, *choosing)
        part = {dataset_id: chosen.get(dataset_id, set()) for dataset_id in given_ids}
        counts = {dataset_id: cdr_store.copied_rows(database_path, dataset_id) for dataset_id in given_ids}
        # A prefix of the rows read only when every table it reads gives its rows from a copy.
        window = max(first * 4, FIRST_ROWS_WINDOW) if given_ids == order else None
        noted: dict[int, list[int]] = {}

        def note(dataset_id: int, rowid: int) -> int:
            rows = noted.get(int(dataset_id))
            if rows is not None and sum(len(items) for items in noted.values()) <= MAX_SEEN_ROWS:
                rows.append(int(rowid))
            return 1

        connection.create_function(_SEEN_FUNCTION, 2, note)
        while True:
            limits: dict[int, int] = {}
            left = window
            for dataset_id in given_ids if window is not None else ():
                limits[dataset_id] = min(left, counts[dataset_id])
                left -= limits[dataset_id]
            noted.clear()
            noted.update({dataset_id: [] for dataset_id in given_ids})
            probe = _give_rows(connection, datasets, sql, given_ids, part, seen=True, first=limits)
            connection.set_authorizer(_read_only_authorizer)
            probe_cursor = connection.execute(probe, parameters)
            given_first = len(probe_cursor.fetchmany(first))
            probe_cursor.close()
            connection.set_authorizer(None)
            if window is None or given_first >= first or all(limits[item] == counts[item] for item in given_ids):
                break
            window *= 8
        if sum(len(rows) for rows in noted.values()) <= MAX_SEEN_ROWS:
            text = _give_rows(connection, datasets, sql, given_ids, reads,
                              {dataset_id: (part[dataset_id], noted[dataset_id]) for dataset_id in given_ids}, first=limits)
            given_ids = []
    if given_ids:
        text = _give_rows(connection, datasets, sql, given_ids, reads)
    connection.set_authorizer(_read_only_authorizer)
    cursor = connection.execute(text, parameters)
    return cursor, (cursor.fetchmany(first) if first is not None else None)


def _read_only_authorizer(action: int, _arg1: str | None, _arg2: str | None, _database: str | None, _source: str | None) -> int:
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
    return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY


def _result_columns(connection: sqlite3.Connection, query: str) -> list[str]:
    cursor = connection.execute(f'SELECT * FROM ({query}) LIMIT 0')
    return [str(item[0]) for item in cursor.description or []]


def validate_query(database_path: Path, datasets: list[dict[str, Any]], query: str) -> list[str]:
    """Check a saved query's read-only SQL and source columns without running it."""
    query = normalize_query(query)
    if not datasets:
        raise ValueError('Select at least one ready CDR source.')
    connection = sqlite3.connect(f'file:{database_path.resolve()}?mode=ro', uri=True, timeout=30.0)
    try:
        _selected_views(connection, datasets)
        connection.set_authorizer(_read_only_authorizer)
        return _result_columns(connection, query)
    finally:
        connection.close()


def _vendor_filter_index(columns: list[str], index: int) -> int:
    """Former vendor names (Vendor V3, Vendor_Only, OP_Vendor) filter the result's Vendor or Operator_Vendor column."""
    target = column_identity(vendor_filter_column(columns[index]))
    if target == column_identity(columns[index]):
        return index
    resolved = next((i for i, column in enumerate(columns) if column_identity(column) == target), None)
    return index if resolved is None else resolved


def _normalize_column_filters(
    column_filters: Any,
    columns: list[str],
    *,
    exclude_index: int | None = None,
) -> list[tuple[int, list[Any]]]:
    if column_filters is None:
        return []
    if not isinstance(column_filters, list):
        raise ValueError('Column filters must be a list.')
    if exclude_index is not None:
        exclude_index = _vendor_filter_index(columns, exclude_index)
    normalized: list[tuple[int, list[Any]]] = []
    seen: set[int] = set()
    for item in column_filters:
        if not isinstance(item, dict):
            raise ValueError('Each column filter must include an index and values.')
        index = item.get('index')
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(columns):
            raise ValueError('A column filter refers to an invalid result column.')
        index = _vendor_filter_index(columns, index)
        if index in seen:
            raise ValueError('A result column can only have one filter.')
        seen.add(index)
        values = item.get('values')
        if not isinstance(values, list):
            raise ValueError('Column filter values must be a list.')
        if len(values) > MAX_FILTER_VALUES:
            raise ValueError(f'A column filter can contain at most {MAX_FILTER_VALUES} values.')
        if index == exclude_index:
            continue
        for value in values:
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError('Column filter values must be JSON scalar values.')
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Column filter values must be finite numbers.')
        normalized.append((index, values))
    return normalized


def _filter_predicates(
    filters: list[tuple[int, list[Any]]], columns: list[str],
) -> tuple[str, list[Any]]:
    predicates: list[str] = []
    parameters: list[Any] = []
    for index, values in filters:
        column = _quote(columns[index])
        if not values:
            predicates.append('0')
            continue
        alternatives: list[str] = []
        for value in values:
            if value is None:
                alternatives.append(f'{column} IS NULL')
            else:
                # The type check keeps a selected text value such as "1" distinct
                # from a numeric 1 while retaining SQLite's normal scalar equality.
                sqlite_type = 'text' if isinstance(value, str) else 'real' if isinstance(value, float) else 'integer'
                alternatives.append(f"(typeof({column}) = '{sqlite_type}' AND {column} IS ?)")
                parameters.append(value)
        predicates.append('(' + ' OR '.join(alternatives) + ')')
    if not predicates:
        return '', parameters
    return ' WHERE ' + ' AND '.join(predicates), parameters


def _filtered_query(
    query: str,
    columns: list[str],
    filters: list[tuple[int, list[Any]]],
) -> tuple[str, list[Any]]:
    where_clause, parameters = _filter_predicates(filters, columns)
    return f'SELECT * FROM ({query}) AS _query_builder_rows{where_clause}', parameters


def execute_query(
    database_path: Path, datasets: list[dict[str, Any]], query: str, row_limit: int = MAX_PREVIEW_ROWS,
    cancel_requested: Callable[[], bool] | None = None,
    offset: int = 0,
    include_total: bool = False,
    column_filters: Any = None,
) -> tuple[list[str], list[tuple[Any, ...]], bool, list[str]] | tuple[list[str], list[tuple[Any, ...]], bool, list[str], int]:
    query = normalize_query(query)
    if not datasets:
        raise ValueError('Select at least one ready CDR source.')
    if offset < 0:
        raise ValueError('Query offset must be non-negative.')
    # A read-only connection must observe committed WAL frames from CDR processing.
    connection = sqlite3.connect(f'file:{database_path.resolve()}?mode=ro', uri=True, timeout=30.0)
    try:
        if cancel_requested:
            connection.set_progress_handler(lambda: 1 if cancel_requested() else 0, 1_000)
        views = _selected_views(connection, datasets)
        connection.set_authorizer(_read_only_authorizer)
        columns = _result_columns(connection, query) if column_filters is not None else []
        filters = _normalize_column_filters(column_filters, columns) if column_filters is not None else []
        result_query, filter_parameters = _filtered_query(query, columns, filters) if filters else (query, [])
        count_query = f'SELECT COUNT(*) FROM ({result_query})' if filters else f'SELECT COUNT(*) FROM ({query})'
        cursor, rows = _execute(
            connection, database_path, datasets,
            f'SELECT * FROM ({result_query}) LIMIT ? OFFSET ?' if filters else f'SELECT * FROM ({query}) LIMIT ? OFFSET ?',
            (*filter_parameters, max(1, int(row_limit)) + 1, offset), first=max(1, int(row_limit)) + 1,
            choosing=(count_query, filter_parameters),
        )
        columns = [str(item[0]) for item in cursor.description or []]
        cursor.close()
        truncated = len(rows) > row_limit
        page = (columns, [tuple(row) for row in rows[:row_limit]], truncated, views)
        if include_total:
            if not truncated and (rows or offset == 0):
                total_rows = offset + len(rows)
            else:
                total_rows = int(_execute(connection, database_path, datasets, count_query, filter_parameters, first=1)[1][0][0])
            return (*page, total_rows)
        return page
    finally:
        connection.close()


def iter_query_csv(
    database_path: Path, datasets: list[dict[str, Any]], query: str,
    on_complete: Callable[[int], None] | None = None,
    column_filters: Any = None,
) -> Iterator[str]:
    query = normalize_query(query)
    if not datasets:
        raise ValueError('Select at least one ready CDR source.')
    connection = sqlite3.connect(
        f'file:{database_path.resolve()}?mode=ro', uri=True,
        timeout=30.0, check_same_thread=False,
    )
    try:
        _selected_views(connection, datasets)
        connection.set_authorizer(_read_only_authorizer)
        columns = _result_columns(connection, query) if column_filters is not None else []
        filters = _normalize_column_filters(column_filters, columns) if column_filters is not None else []
        if filters:
            result_query, parameters = _filtered_query(query, columns, filters)
            cursor, _rows = _execute(connection, database_path, datasets, result_query, parameters)
        else:
            cursor, _rows = _execute(connection, database_path, datasets, query)
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow([str(item[0]) for item in cursor.description or []])
        yield output.getvalue()
        row_count = 0
        while rows := cursor.fetchmany(1_000):
            output.seek(0)
            output.truncate(0)
            writer.writerows(rows)
            row_count += len(rows)
            yield output.getvalue()
        if on_complete:
            on_complete(row_count)
    finally:
        connection.close()


def query_column_values(
    database_path: Path,
    datasets: list[dict[str, Any]],
    query: str,
    column_index: int,
    column_filters: Any = None,
    search: str = '',
) -> tuple[list[Any], bool]:
    """Return distinct result values, constrained by the other active filters."""
    query = normalize_query(query)
    if not datasets:
        raise ValueError('Select at least one ready CDR source.')
    if isinstance(column_index, bool) or not isinstance(column_index, int) or column_index < 0:
        raise ValueError('Select a valid result column.')
    if not isinstance(search, str):
        raise ValueError('Filter value search must be text.')
    if len(search) > 200:
        raise ValueError('Filter value search is too long.')
    connection = sqlite3.connect(f'file:{database_path.resolve()}?mode=ro', uri=True, timeout=30.0)
    try:
        _selected_views(connection, datasets)
        connection.create_function('casefold', 1, lambda value: str(value).casefold() if value is not None else None)
        connection.set_authorizer(_read_only_authorizer)
        columns = _result_columns(connection, query)
        if column_index >= len(columns):
            raise ValueError('Select a valid result column.')
        filters = _normalize_column_filters(column_filters, columns, exclude_index=column_index)
        result_query, parameters = _filtered_query(query, columns, filters) if filters else (query, [])
        selected_column = _quote(columns[_vendor_filter_index(columns, column_index)])
        search_clause = ''
        if search:
            search_clause = f' WHERE instr(casefold(CAST(_query_builder_filter_rows.{selected_column} AS TEXT)), casefold(?)) > 0'
            parameters = [*parameters, search]
        cursor, _rows = _execute(
            connection, database_path, datasets,
            f'SELECT DISTINCT _query_builder_filter_rows.{selected_column} AS _query_builder_filter_value '
            f'FROM ({result_query}) AS _query_builder_filter_rows{search_clause} '
            'ORDER BY _query_builder_filter_value LIMIT ?',
            (*parameters, MAX_FILTER_OPTIONS + 1),
        )
        rows = cursor.fetchall()
        return [row[0] for row in rows[:MAX_FILTER_OPTIONS]], len(rows) > MAX_FILTER_OPTIONS
    finally:
        connection.close()
