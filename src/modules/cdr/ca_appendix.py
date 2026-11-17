"""CA Appendix: the Carrier Aggregation details NetCheck delivers every quarter for each test of its CDRs.

A CA Appendix is one row per test, keyed by its ``JOIN_ID`` (the JOIN_ID of the CDRs), with the aggregated
bandwidths, numbers of carriers and band combinations of the test and, for each carrier (LTE PCC and SCC1–4, NR PCC
and SCC1–5), its band, bandwidth, channel, PCI and radio and scheduling statistics, plus the eNodeBs and gNodeBs that
served it. It has no Campaign, Operator mapping or position of its own: they come from the CDR test with its JOIN_ID.

The rows never go through SQLite. The delivery (an XLSX workbook, CSV files or their ZIP; it can be larger than 1 GB)
is read as it streams and written as one Parquet file in the input folder, every value as the text it has in the file:
the source of the dataset. Its fields are then derived once into ``.ca-store/<dataset id>/fields.parquet``: one row per
JOIN_ID, every column but the identity of the test as ``CA_<column>`` (the ``Main`` values, written ``value(seconds)``,
read as their value; numbers as numbers) plus the eNodeB and gNodeB of the test.

The CDRs keep those fields in their own rows: every ready CDR whose tests have a JOIN_ID of a CA Appendix gets its
``CA_`` columns in its columnar copy, written in the background (see ``queue_fill``) and again when a CA Appendix is
uploaded, processed again or deleted, so Campaign, Operator, NR Mode and every filter of the CDR apply to them and every
module reads them as any other field. For a JOIN_ID in several CA Appendices the newest one is read.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
import shutil
import threading
import time
import zipfile
from glob import escape as glob_escape
from pathlib import Path
from typing import Any, Callable, Iterable

import duckdb

KIND = 'ca_appendix'
LABEL = 'CA Appendix'
STORE_FOLDER = '.ca-store'
FIELDS_FILE = 'fields.parquet'
SOURCE_SUFFIX = '.parquet'
# The rows of each row group of its Parquet files: hundreds of columns, so a row group is written in little memory.
ROW_GROUP_ROWS = 16384
# Raise when the derived fields change, so every CA Appendix is derived again from its source and the CDRs refilled.
FIELDS_VERSION = 1
COLUMN_PREFIX = 'CA_'
JOIN_COLUMN = 'JOIN_ID'
KEY_COLUMN = '__join_key'
FILLS_TABLE = 'ca_appendix_fills'
TABLE_TITLES = {FILLS_TABLE: 'CA Appendix Fills'}
CDR_KINDS = ('data', 'voice', 'speech')
NODE_COLUMN = 'eNodeB_gNodeB_Result_Changes'
# The columns of the identity of the test: the CDR test with the same JOIN_ID already has them.
IDENTITY_COLUMNS = frozenset(name.casefold() for name in (
    'Validity', 'JOIN_ID', 'SessionId', 'TestId', 'FileId_A', 'FileId_B', 'Test_Status', 'Test_Type', 'Test_Name',
    'Test_Info', 'HomeOperator', 'Operator', 'Region', 'Vendor', 'G_Level_1', 'G_Level_2', 'G_Level_3', 'G_Level_4',
    'G_Level_5', 'Remark', 'Train_Type', 'Train_Name', 'Wagon_Number', 'Repeater_Wagon', 'Campaign',
))
# The fields derived from the eNodeBs and gNodeBs of the test (``4G:548710 -> 4G:505868, 5G:17029``).
NODE_FIELDS = ('CA_eNodeB_ID', 'CA_gNodeB_ID', 'CA_eNodeB_Changes', 'CA_gNodeB_Changes')
# The operator of the test as the CA Appendix names it, kept for its summary only.
OPERATOR_COLUMN = 'HomeOperator'
TEST_TYPE_COLUMN = 'Test_Type'

ProgressCallback = Callable[[int], None]


def quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sql_text(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def is_ca_kind(kind: object) -> bool:
    return str(kind or '').casefold() == KIND


def store_root(database_path: Any) -> Path:
    """The folder of the derived files of the CA Appendices of a workspace, beside its database."""
    return Path(str(database_path)).resolve().parent / STORE_FOLDER


def fields_path(database_path: Any, dataset_id: int) -> Path:
    return store_root(database_path) / str(int(dataset_id)) / FIELDS_FILE


def field_name(column: str) -> str:
    """The field of a CDR that holds a column of the CA Appendix."""
    return COLUMN_PREFIX + re.sub(r'\s+', '_', str(column).strip())


def is_ca_field(column: object) -> bool:
    return str(column or '').startswith(COLUMN_PREFIX)


# --------------------------------------------------------------------------------------------------------------
# Reading a delivery

_CELL = re.compile(rb'<c\b([^>]*?)(?:/>|>(.*?)</c>)', re.S)
_REF = re.compile(rb'\br="([A-Z]+)\d*"')
_TYPE = re.compile(rb'\bt="([a-zA-Z]+)"')
_VALUE = re.compile(rb'<v>(.*?)</v>', re.S)
_TEXT = re.compile(rb'<t\b[^>]*>(.*?)</t>', re.S)
_ROW_END = b'</row>'
_SHARED_ITEM = re.compile(rb'<si>(.*?)</si>', re.S)
_SHEET_PATH = re.compile(r'^xl/worksheets/sheet\d+\.xml$')


def _column_index(letters: bytes) -> int:
    index = 0
    for letter in letters:
        index = index * 26 + (letter - 64)
    return index - 1


def _xml_text(value: bytes) -> str:
    text = value.decode('utf-8', errors='replace')
    return html.unescape(text) if '&' in text else text


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        content = archive.read('xl/sharedStrings.xml')
    except KeyError:
        return []
    return [_xml_text(b''.join(_TEXT.findall(item))) for item in _SHARED_ITEM.findall(content)]


def _first_sheet(archive: zipfile.ZipFile) -> str:
    """The XML of the first sheet of a workbook (the one its workbook lists first)."""
    names = archive.namelist()
    try:
        workbook = archive.read('xl/workbook.xml')
        relations = archive.read('xl/_rels/workbook.xml.rels')
        first = re.search(rb'<sheet\b[^>]*\br:id="([^"]+)"', workbook) or re.search(rb'<sheet\b[^>]*\bid="([^"]+)"', workbook)
        if first:
            target = re.search(rb'<Relationship\b[^>]*\bId="' + re.escape(first.group(1)) + rb'"[^>]*\bTarget="([^"]+)"', relations) \
                or re.search(rb'<Relationship\b[^>]*\bTarget="([^"]+)"[^>]*\bId="' + re.escape(first.group(1)) + rb'"', relations)
            if target:
                path = target.group(1).decode('utf-8').lstrip('/')
                path = path if path.startswith('xl/') else f'xl/{path}'
                if path in names:
                    return path
    except KeyError:
        pass
    sheets = sorted((name for name in names if _SHEET_PATH.match(name)), key=lambda name: int(re.sub(r'\D', '', name) or 0))
    if not sheets:
        raise ValueError('The workbook has no sheet.')
    return sheets[0]


def xlsx_to_csv(source: Path, target: Path, progress: ProgressCallback | None = None) -> int:
    """Write the first sheet of a workbook to a CSV file as it streams, every value as the text of the cell (the
    workbook is never held whole: a CA Appendix can be larger than 1 GB). Returns the rows written, the header included.

    openpyxl reads a workbook of this size in hours; the cells of the sheet XML are read here with regular expressions,
    a block at a time."""
    report = progress or (lambda _value: None)
    rows = 0
    with zipfile.ZipFile(source) as archive:
        shared = _shared_strings(archive)
        sheet = _first_sheet(archive)
        total = max(1, archive.getinfo(sheet).file_size)
        with archive.open(sheet) as reader, target.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            width = 0
            pending = b''
            read = 0
            last = -1
            while True:
                block = reader.read(16 * 1024 ** 2)
                read += len(block)
                data = pending + block
                end = data.rfind(_ROW_END) if block else len(data)
                if end < 0:
                    pending = data
                    continue
                cut = end + len(_ROW_END) if block else end
                complete, pending = data[:cut], data[cut:]
                for row_xml in complete.split(_ROW_END):
                    if b'<c' not in row_xml:
                        continue
                    values: dict[int, str] = {}
                    position = -1
                    for match in _CELL.finditer(row_xml, row_xml.find(b'<row')):
                        attributes, inner = match.group(1), match.group(2)
                        reference = _REF.search(attributes)
                        position = _column_index(reference.group(1)) if reference else position + 1
                        if not inner:
                            continue
                        kind = _TYPE.search(attributes)
                        kind = kind.group(1) if kind else b'n'
                        if kind == b'inlineStr':
                            text = _xml_text(b''.join(_TEXT.findall(inner)))
                        else:
                            value = _VALUE.search(inner)
                            if not value:
                                continue
                            if kind == b's':
                                index = int(value.group(1))
                                text = shared[index] if index < len(shared) else ''
                            elif kind == b'b':
                                text = 'TRUE' if value.group(1) == b'1' else 'FALSE'
                            else:
                                text = _xml_text(value.group(1))
                        if text != '':
                            values[position] = text
                    if not values:
                        continue
                    if rows == 0:
                        width = max(values) + 1
                    writer.writerow([values.get(index, '') for index in range(width)])
                    rows += 1
                step = int(100 * read / total)
                if step != last:
                    last = step
                    report(min(100, step))
                if not block:
                    break
    return rows


def _delivery_files(source: Path, work: Path, progress: ProgressCallback) -> list[Path]:
    """The CSV or Parquet files of a delivery: the file itself, its workbook as CSV, or the files of its ZIP."""
    suffix = source.suffix.casefold()
    if suffix in {'.csv', '.txt', SOURCE_SUFFIX}:
        return [source]
    work.mkdir(parents=True, exist_ok=True)
    if suffix in {'.xlsx', '.xlsm'}:
        _check_space(source.stat().st_size * 6, work)
        target = work / f'{source.stem}.csv'
        xlsx_to_csv(source, target, progress)
        return [target]
    if suffix != '.zip':
        raise ValueError('A CA Appendix is an XLSX workbook, CSV files or their ZIP.')
    files: list[Path] = []
    with zipfile.ZipFile(source) as archive:
        members = [info for info in archive.infolist() if not info.is_dir()
                   and Path(info.filename).suffix.casefold() in {'.csv', '.txt', '.xlsx', '.xlsm'}
                   and not Path(info.filename).name.startswith(('.', '~$'))
                   and '__MACOSX' not in Path(info.filename).parts]
        if not members:
            raise ValueError('The ZIP has no workbook or CSV file of a CA Appendix.')
        _check_space(sum(int(info.file_size) for info in members) * 2, work)
        for index, info in enumerate(members):
            target = work / f'{index:03d}-{Path(info.filename).name}'
            with archive.open(info) as reader, target.open('wb') as writer:
                shutil.copyfileobj(reader, writer, 8 * 1024 ** 2)
            if target.suffix.casefold() in {'.xlsx', '.xlsm'}:
                converted = target.with_suffix('.csv')
                xlsx_to_csv(target, converted, lambda value, i=index: progress(int(100 * (i + value / 100) / len(members))))
                target.unlink()
                target = converted
            files.append(target)
    return files


def _check_space(needed: int, work: Path) -> None:
    free = shutil.disk_usage(work if work.exists() else work.parent).free
    if needed + 512 * 1024 ** 2 > free:
        raise ValueError(f'Not enough free disk space to read the CA Appendix: it needs {needed / 1024 ** 3:.1f} GB.')


def _read_relation(files: list[Path]) -> str:
    """The SQL that reads the rows of a delivery, every value as the text it has in the files."""
    names = ', '.join(sql_text(path) for path in files)
    if all(path.suffix.casefold() == SOURCE_SUFFIX for path in files):
        return f'read_parquet([{names}], union_by_name = true)'
    return (f'read_csv([{names}], header = true, all_varchar = true, union_by_name = true, null_padding = true, '
            f'max_line_size = 16777216)')


# --------------------------------------------------------------------------------------------------------------
# The fields of a CA Appendix

def _identity(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(name).casefold())


def join_column(columns: Iterable[str]) -> str | None:
    by_identity = {_identity(column): column for column in columns}
    return by_identity.get(_identity(JOIN_COLUMN)) or by_identity.get('joinid')


def field_columns(columns: Iterable[str]) -> list[str]:
    """The columns of a CA Appendix the CDRs take as their ``CA_`` fields: all but the identity of the test."""
    return [column for column in columns if str(column).casefold() not in IDENTITY_COLUMNS and str(column).strip()]


def is_main_column(column: str) -> bool:
    """A ``Main`` value: the value the test had for longest, written ``value(seconds)`` or ``[value](seconds)``."""
    name = str(column).casefold()
    return 'main' in name and 'timeline' not in name


_TEXT_FIELD = re.compile(r'timeline|combination|_hos$|technology|_band$|result_changes', re.IGNORECASE)


def is_text_field(name: str) -> bool:
    """A field whose values are texts (timelines, bands, band combinations, handovers), by its name."""
    return bool(_TEXT_FIELD.search(str(name)))


def main_value_sql(expression: str) -> str:
    """The value of a ``value(seconds)`` text (of the longest segment of ``[a](1.0)->[b](2.0)``); other texts as they
    are."""
    segment = r"'^\s*\[?([^\]\(]*?)\]?\s*\(\s*-?[0-9.]+\s*\)\s*$'"
    seconds = r"'\(\s*(-?[0-9.]+)\s*\)\s*$'"
    return (f"CASE WHEN NULLIF(TRIM({expression}), '') IS NULL THEN NULL "
            f"WHEN NOT regexp_matches({expression}, '\\(\\s*-?[0-9.]+\\s*\\)\\s*$') THEN TRIM({expression}) "
            f"ELSE NULLIF(TRIM(list_sort(list_transform(string_split({expression}, '->'), lambda s: "
            f"{{'seconds': TRY_CAST(regexp_extract(s, {seconds}, 1) AS DOUBLE), "
            f"'value': regexp_extract(s, {segment}, 1)}}), 'DESC')[1].value), '') END")


def _node_sql(expression: str, technology: str) -> tuple[str, str]:
    """The first node of a technology (``4G`` or ``5G``) of the test and how many times it changed."""
    nodes = f"regexp_extract_all(COALESCE({expression}, ''), '{technology}\\s*:\\s*([0-9]+)', 1)"
    first = f"TRY_CAST({nodes}[1] AS DOUBLE)"
    changes = (f"CASE WHEN len({nodes}) = 0 THEN NULL ELSE CAST(len(list_filter(list_transform(range(1, len({nodes})), "
               f"lambda i: {nodes}[i + 1] <> {nodes}[i]), lambda x: x)) AS DOUBLE) END")
    return first, changes


def build_fields(source: Path, target: Path) -> dict[str, Any]:
    """Derive the fields of a CA Appendix from its source into ``target``: its JOIN_ID key and its ``CA_`` fields, typed
    (a column whose every value is a number is a number). Returns the fields and which are numbers."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'.{target.name}.{os.getpid()}.tmp')
    spill = target.parent / f'.spill-{os.getpid()}'
    # The rows are streamed from the source (never held whole: hundreds of columns for every test of a quarter).
    duck = duckdb.connect(config={'memory_limit': '2GB', 'threads': 2, 'temp_directory': str(spill),
                                  'preserve_insertion_order': False})
    try:
        relation = f'read_parquet({sql_text(source)}, file_row_number = true)'
        header = [row[0] for row in duck.execute(f'DESCRIBE SELECT * FROM read_parquet({sql_text(source)})').fetchall()]
        key = join_column(header)
        if not key:
            raise ValueError('This file is not a CA Appendix: it has no JOIN_ID column.')
        columns = field_columns(header)
        expressions: dict[str, str] = {}
        for column in columns:
            text = f'CAST({quote(column)} AS VARCHAR)'
            expressions[field_name(column)] = main_value_sql(text) if is_main_column(column) else f"NULLIF(TRIM({text}), '')"
        node = next((column for column in header if _identity(column) == _identity(NODE_COLUMN)), None)
        if node:
            enb, enb_changes = _node_sql(quote(node), '4G')
            gnb, gnb_changes = _node_sql(quote(node), '5G')
            expressions.update(dict(zip(NODE_FIELDS, (enb, gnb, enb_changes, gnb_changes))))
        own_key = f"lower(TRIM(CAST({quote(key)} AS VARCHAR)))"
        derived = (f"SELECT {own_key} AS {quote(KEY_COLUMN)}, file_row_number, "
                   + ', '.join(f'{expression} AS {quote(name)}' for name, expression in expressions.items())
                   + f" FROM {relation} WHERE NULLIF(TRIM(CAST({quote(key)} AS VARCHAR)), '') IS NOT NULL")
        # A column is a number when every value it has is one; a column without values (an SCC no test used) takes
        # the type its name gives, so it keeps it in the next CA Appendix.
        names = list(expressions)
        counts = duck.execute('SELECT ' + ', '.join(
            f'COUNT({quote(name)}), COUNT(TRY_CAST({quote(name)} AS DOUBLE))' for name in names) + f' FROM ({derived})').fetchone()
        filled = {name: counts[2 * index] == counts[2 * index + 1] for index, name in enumerate(names) if counts[2 * index]}

        def empty_is_number(name: str) -> bool:
            # The same field of another carrier (NR_SCC4_Main_Band as NR_PCC_Main_Band), else what its name says.
            sibling = re.sub(r'_(PCC|SCC\d+)_', '_{}_', name)
            siblings = [filled[other] for other in filled if re.sub(r'_(PCC|SCC\d+)_', '_{}_', other) == sibling and other != name]
            return all(siblings) if siblings and sibling != name else not is_text_field(name)

        numeric = [name for name in names if (filled[name] if name in filled else empty_is_number(name))]
        numbers = set(numeric)
        typed = ', '.join(f'TRY_CAST({quote(name)} AS DOUBLE) AS {quote(name)}' if name in numbers else quote(name)
                          for name in names)
        # One row per JOIN_ID: the last one of the file, chosen by its row number alone (the rows are never sorted).
        duck.execute(f'CREATE TEMP TABLE kept AS SELECT MAX(file_row_number) AS file_row_number FROM {relation} '
                     f"WHERE NULLIF(TRIM(CAST({quote(key)} AS VARCHAR)), '') IS NOT NULL GROUP BY {own_key}")
        duck.execute(f'COPY (SELECT {quote(KEY_COLUMN)}, {typed} FROM ({derived}) '
                     f'WHERE file_row_number IN (SELECT file_row_number FROM kept)) '
                     f'TO {sql_text(temporary)} (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_ROWS})')
        tests = int(duck.execute(f'SELECT COUNT(*) FROM read_parquet({sql_text(temporary)})').fetchone()[0])
    finally:
        duck.close()
        shutil.rmtree(spill, ignore_errors=True)
    os.replace(temporary, target)
    return {'fields': names, 'numeric': numeric, 'join_ids': tests}


def _summary(duck: duckdb.DuckDBPyConnection, relation: str, header: list[str], records: int, fields: dict[str, Any],
             source_name: str) -> dict[str, Any]:
    by_identity = {_identity(column): column for column in header}

    def counts(column_name: str) -> dict[str, int]:
        column = by_identity.get(_identity(column_name))
        if not column:
            return {}
        return {str(value): int(count) for value, count in duck.execute(
            f"SELECT NULLIF(TRIM({quote(column)}), ''), COUNT(*) FROM {relation} GROUP BY 1 ORDER BY 1 NULLS LAST").fetchall()
            if value is not None}

    return {
        'ca': {
            'version': FIELDS_VERSION, 'records': int(records), 'join_ids': int(fields['join_ids']),
            'columns': len(header), 'fields': len(fields['fields']), 'numeric_fields': len(fields['numeric']),
            'operators': counts(OPERATOR_COLUMN), 'test_types': counts(TEST_TYPE_COLUMN), 'source': source_name,
        },
        'rows': int(records),
        'columns': [],
    }


def process_delivery(repository: Any, dataset_id: int, source: Path, *, progress: ProgressCallback | None = None,
                     normalization_version: int | None = None) -> dict[str, Any]:
    """Read a CA Appendix and write it as the Parquet source of its dataset, then derive its fields.

    The rows are read as they stream (a workbook is converted a block at a time), written with DuckDB and never held
    whole. Returns its rows, JOIN_IDs and fields."""
    from src.modules.core.repository import local_now_iso

    started = time.monotonic()
    report = progress or (lambda _value: None)
    dataset = repository.get_dataset(int(dataset_id))
    if not dataset:
        raise ValueError('Dataset not found.')
    source = Path(source)
    root = store_root(repository.db_path)
    work = root / 'tmp' / f'{int(dataset_id)}-{os.getpid()}'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    try:
        report(12)
        files = _delivery_files(source, work / 'files', lambda value: report(12 + int(value * 0.5)))
        report(62)
        stem = Path(str(dataset['file_name'] or source.name)).stem
        target = source.parent / f'{stem}{SOURCE_SUFFIX}'
        # The files left by a processing that was stopped.
        for leftover in source.parent.glob(f'.{glob_escape(target.name)}.*.tmp'):
            leftover.unlink(missing_ok=True)
        # Its own source read again (Reprocess) is not written again.
        rewrite = [path.resolve() for path in files] != [target.resolve()]
        temporary = target.with_name(f'.{target.name}.{os.getpid()}.tmp') if rewrite else target
        # Hundreds of text columns: written in the order of the file by one thread, in small row groups, so the rows
        # being written stay in little memory.
        duck = duckdb.connect(config={'memory_limit': '2GB', 'threads': 1, 'temp_directory': str(work / 'spill'),
                                      'preserve_insertion_order': True})
        try:
            delivery = _read_relation(files)
            header = [row[0] for row in duck.execute(f'DESCRIBE SELECT * FROM {delivery}').fetchall()]
            if not join_column(header):
                raise ValueError('This file is not a CA Appendix: it has no JOIN_ID column.')
            if rewrite:
                duck.execute(f'COPY (SELECT * FROM {delivery}) TO {sql_text(temporary)} '
                             f'(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_ROWS})')
            records = int(duck.execute(f'SELECT COUNT(*) FROM read_parquet({sql_text(temporary)})').fetchone()[0])
            if not records:
                raise ValueError('The CA Appendix has no rows.')
            report(75)
            fields = build_fields(temporary, fields_path(repository.db_path, dataset_id))
            report(92)
            summary = _summary(duck, f'read_parquet({sql_text(temporary)})', header, records, fields, target.name)
        finally:
            duck.close()
        if rewrite:
            os.replace(temporary, target)
        if source.resolve() != target.resolve():
            if source.exists():
                source.unlink()
            with repository.connection() as connection:
                connection.execute('UPDATE datasets SET stored_path = ? WHERE id = ?', (str(target), int(dataset_id)))
        profile = {
            'status': 'ready', 'progress': 100, 'processing_step': 'Completed', 'dataset_kind': KIND,
            'row_count': records, 'column_count': len(header), 'default_metric': '', 'default_aggregation': 'all',
            'available_metrics_json': '[]', 'available_aggregations_json': '[]', 'filter_options_json': '{}',
            'summary_json': json.dumps(summary, ensure_ascii=False), 'kpis_json': '{}',
            'processed_at': local_now_iso(), 'last_error': None,
        }
        if normalization_version is not None:
            profile['normalization_version'] = int(normalization_version)
        # Its columns as the file names them, which its Preview shows as source columns.
        repository.replace_dataset_source_columns(int(dataset_id), header)
        repository.update_dataset_profile(int(dataset_id), **profile)
        return {'records': records, 'join_ids': fields['join_ids'], 'fields': len(fields['fields']),
                'numeric_fields': len(fields['numeric']), 'file': target.name,
                'seconds': round(time.monotonic() - started, 1)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def forget_datasets(repository: Any) -> None:
    """Remove the derived files of the CA Appendices deleted."""
    root = store_root(repository.db_path)
    if not root.is_dir():
        return
    with repository.connection() as connection:
        alive = {int(row[0]) for row in connection.execute('SELECT id FROM datasets')}
    for folder in root.iterdir():
        if folder.is_dir() and folder.name.isdigit() and int(folder.name) not in alive:
            shutil.rmtree(folder, ignore_errors=True)


def dataset_summary(row: Any) -> dict[str, Any]:
    """What the Datasets card shows of a CA Appendix: its tests, fields and operators."""
    try:
        summary = json.loads((row.get('summary_json') if isinstance(row, dict) else row['summary_json']) or '{}')
    except (TypeError, ValueError):
        summary = {}
    return summary.get('ca') or {}


def source_columns(source: Any) -> list[str]:
    path = Path(str(source or ''))
    if path.suffix.casefold() != SOURCE_SUFFIX or not path.is_file():
        return []
    with duckdb.connect() as duck:
        return [row[0] for row in duck.execute(f'DESCRIBE SELECT * FROM read_parquet({sql_text(path)})').fetchall()]


def preview_frame(source: Any, columns: Iterable[str], limit: int) -> Any:
    """The first rows of a CA Appendix, read from its source (it has no rows in SQLite)."""
    import pandas as pd

    path = Path(str(source or ''))
    wanted = [column for column in columns if column in set(source_columns(path))]
    if not wanted:
        return pd.DataFrame(columns=list(columns))
    with duckdb.connect() as duck:
        return duck.execute(
            f'SELECT {", ".join(quote(column) for column in wanted)} FROM read_parquet({sql_text(path)}) LIMIT {int(limit)}'
        ).fetchdf()


def ready_datasets(repository: Any) -> list[dict[str, Any]]:
    """The ready CA Appendices of a workspace with their derived fields, newest first."""
    datasets = []
    for row in repository.list_datasets():
        if not is_ca_kind(row['dataset_kind']) or str(row['status'] or '') != 'ready':
            continue
        path = fields_path(repository.db_path, int(row['id']))
        if not path.is_file():
            continue
        datasets.append({'id': int(row['id']), 'file_name': row['file_name'], 'uploaded_at': row['uploaded_at'],
                         'processed_at': row['processed_at'], 'fields_path': path, **dataset_summary(row)})
    datasets.sort(key=lambda item: (str(item.get('uploaded_at') or ''), int(item['id'])), reverse=True)
    return datasets


def ensure_fields(repository: Any) -> list[int]:
    """Derive again the fields of the ready CA Appendices whose fields are missing or of an older version."""
    rebuilt = []
    for row in repository.list_datasets():
        if not is_ca_kind(row['dataset_kind']) or str(row['status'] or '') != 'ready':
            continue
        path = fields_path(repository.db_path, int(row['id']))
        if path.is_file() and int(dataset_summary(row).get('version') or 0) == FIELDS_VERSION:
            continue
        source = Path(str(row['stored_path'] or ''))
        if source.suffix.casefold() != SOURCE_SUFFIX or not source.is_file():
            continue
        fields = build_fields(source, path)
        try:
            summary = json.loads(row['summary_json'] or '{}')
        except (TypeError, ValueError):
            summary = {}
        ca = summary.get('ca') or {}
        ca.update(version=FIELDS_VERSION, join_ids=fields['join_ids'], fields=len(fields['fields']),
                  numeric_fields=len(fields['numeric']))
        summary['ca'] = ca
        repository.update_dataset_profile(int(row['id']), summary_json=json.dumps(summary, ensure_ascii=False))
        rebuilt.append(int(row['id']))
    return rebuilt


# --------------------------------------------------------------------------------------------------------------
# The CA fields of the CDRs

def ensure_table(repository: Any) -> None:
    from src.modules.core.repository import schema_in_place

    schema = (f'CREATE TABLE IF NOT EXISTS {FILLS_TABLE} (dataset_id INTEGER PRIMARY KEY, version TEXT NOT NULL, '
              'cdr_revision TEXT NOT NULL, matched INTEGER NOT NULL DEFAULT 0, appendix_ids TEXT NOT NULL DEFAULT \'\', '
              'filled_at TEXT NOT NULL)')
    with repository.connection() as connection:
        if not schema_in_place(connection, schema):
            connection.execute(schema)


def fields_version(appendices: list[dict[str, Any]]) -> str:
    """The version of the CA fields of a workspace: its ready CA Appendices, newest first, as processed."""
    payload = json.dumps([FIELDS_VERSION, [(item['id'], str(item.get('processed_at') or '')) for item in appendices]])
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]


def _ready_cdrs(repository: Any) -> dict[int, dict[str, Any]]:
    return {int(row['id']): {'kind': str(row['dataset_kind']).casefold(), 'revision': str(row['processed_at'] or ''),
                             'file_name': str(row['file_name'] or '')}
            for row in repository.list_datasets()
            if str(row['dataset_kind'] or '').casefold() in CDR_KINDS and str(row['status'] or '').casefold() == 'ready'}


def stale_datasets(repository: Any) -> list[tuple[int, str]]:
    """The ready CDRs (whose columnar copy holds their rows) whose CA fields are not those of the current CA Appendices,
    newest first. A CDR still in its table is filled once it is copied."""
    from src.modules.cdr import cdr_store

    ensure_table(repository)
    ready = _ready_cdrs(repository)
    if not ready:
        return []
    # The derived fields of a CA Appendix restored or imported without them are derived again first.
    ensure_fields(repository)
    version = fields_version(ready_datasets(repository))
    copied = cdr_store.shadow_ids(repository.db_path)
    with repository.connection() as connection:
        fills = {int(row['dataset_id']): row for row in connection.execute(f'SELECT * FROM {FILLS_TABLE}').fetchall()}
    stale = []
    for dataset_id, cdr in ready.items():
        if dataset_id not in copied:
            continue
        fill = fills.get(dataset_id)
        if fill is None and not ready_datasets_cached(repository):
            # No CA Appendix and never filled: nothing to write or remove.
            continue
        if (fill is None or fill['version'] != version or fill['cdr_revision'] != cdr['revision']
                or (int(fill['matched'] or 0) > 0 and not any(is_ca_field(column) for column in
                                                              repository.list_dataset_row_columns(dataset_id)))):
            stale.append((dataset_id, cdr['kind']))
    return sorted(stale, reverse=True)


def ready_datasets_cached(repository: Any) -> bool:
    return any(is_ca_kind(row['dataset_kind']) and str(row['status'] or '') == 'ready' for row in repository.list_datasets())


def _cdr_parts(repository: Any, kind: str, dataset_id: int) -> str:
    from src.modules.cdr import cdr_store

    return cdr_store.cdr_parts(cdr_store.store_root(repository.db_path), kind, dataset_id)


def keyed_fields_sql(appendices: list[dict[str, Any]]) -> tuple[str, list[str], list[str]]:
    """The SQL of the CA fields of the JOIN_IDs of ``KEYS_TOKEN`` (each of the newest CA Appendix that has it, see
    cdr_store.change_copy_columns), with the fields and those that are numbers in every CA Appendix."""
    from src.modules.cdr.cdr_store import KEYS_TOKEN

    if not appendices:
        return '', [], []
    files = [str(item['fields_path']) for item in appendices]
    fields: list[str] = []
    types: dict[str, set[str]] = {}
    with duckdb.connect() as duck:
        for path in files:
            for name, kind, *_rest in duck.execute(f'DESCRIBE SELECT * FROM read_parquet({sql_text(path)})').fetchall():
                if name == KEY_COLUMN:
                    continue
                if name not in types:
                    fields.append(name)
                types.setdefault(name, set()).add(str(kind).upper())
    numeric = [name for name in fields if types[name] == {'DOUBLE'}]
    order = 'CASE filename ' + ' '.join(f'WHEN {sql_text(path)} THEN {index}' for index, path in enumerate(files)) + ' END'
    selected = ', '.join([quote(KEY_COLUMN)] + [
        (f'TRY_CAST({quote(name)} AS DOUBLE) AS {quote(name)}' if name in numeric else f'CAST({quote(name)} AS VARCHAR) AS {quote(name)}')
        for name in fields])
    names = ', '.join(sql_text(path) for path in files)
    sql = (f'SELECT {selected} FROM read_parquet([{names}], union_by_name = true, filename = true) '
           f'WHERE {quote(KEY_COLUMN)} IN {KEYS_TOKEN} '
           f'QUALIFY row_number() OVER (PARTITION BY {quote(KEY_COLUMN)} ORDER BY {order}) = 1')
    return sql, fields, numeric


def _matched_tests(repository: Any, kind: str, dataset_id: int, join_id: str, appendices: list[dict[str, Any]]) -> int:
    if not appendices:
        return 0
    files = ', '.join(sql_text(str(item['fields_path'])) for item in appendices)
    with duckdb.connect() as duck:
        return int(duck.execute(
            f'SELECT COUNT(*) FROM read_parquet({sql_text(_cdr_parts(repository, kind, dataset_id))}) p '
            f'WHERE lower(TRIM(CAST(p.{quote(join_id)} AS VARCHAR))) IN '
            f'(SELECT {quote(KEY_COLUMN)} FROM read_parquet([{files}], union_by_name = true))').fetchone()[0])


def _record_fill(repository: Any, dataset_id: int, version: str, revision: str, matched: int, appendix_ids: list[int]) -> None:
    from src.modules.core.repository import local_now_iso

    with repository.connection() as connection:
        connection.execute(
            f'INSERT INTO {FILLS_TABLE} (dataset_id, version, cdr_revision, matched, appendix_ids, filled_at) '
            'VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(dataset_id) DO UPDATE SET version = excluded.version, '
            'cdr_revision = excluded.cdr_revision, matched = excluded.matched, appendix_ids = excluded.appendix_ids, '
            'filled_at = excluded.filled_at',
            (int(dataset_id), version, revision, int(matched), ','.join(str(value) for value in appendix_ids), local_now_iso()))


def fill_dataset(repository: Any, dataset_id: int, kind: str, should_stop: Callable[[], bool] = lambda: False) -> int:
    """Write the CA fields of the tests of a CDR in its columnar copy (its ``CA_`` columns, only those rewritten): the
    fields of the current CA Appendices for the tests with their JOIN_ID; a CDR without any keeps no ``CA_`` column.
    Returns the tests with CA fields, or -1 when it has to be filled later (a writer holds it, or the application
    stops)."""
    from src.modules.cdr import cdr_store
    from src.modules.cdr.column_names import resolve_column_name

    ensure_table(repository)
    dataset_id = int(dataset_id)
    cdr = _ready_cdrs(repository).get(dataset_id)
    if cdr is None or dataset_id not in cdr_store.shadow_ids(repository.db_path):
        return -1
    ensure_fields(repository)
    appendices = ready_datasets(repository)
    version = fields_version(appendices)
    columns = repository.list_dataset_row_columns(dataset_id)
    existing = [column for column in columns if is_ca_field(column)]
    join_id = resolve_column_name(columns, JOIN_COLUMN)
    matched = _matched_tests(repository, kind, dataset_id, join_id, appendices) if join_id else 0
    if should_stop():
        return -1
    if not matched:
        if existing and not cdr_store.change_copy_columns(repository, dataset_id, drop=existing, should_stop=should_stop):
            return -1
    else:
        sql, fields, numeric = keyed_fields_sql(appendices)
        drop = [column for column in existing if column not in set(fields)]
        if not cdr_store.change_copy_columns(repository, dataset_id, drop=drop, should_stop=should_stop,
                                             keyed=(sql, join_id, KEY_COLUMN, fields), numeric=numeric):
            return -1
    _record_fill(repository, dataset_id, version, cdr['revision'], matched, [item['id'] for item in appendices])
    return matched


def fill_stamps(repository: Any) -> dict[int, str]:
    """When the CA fields of each CDR were last written (what reads them keeps its results until they change)."""
    with repository.connection() as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (FILLS_TABLE,)).fetchone():
            return {}
        return {int(row['dataset_id']): f"{row['filled_at']}:{row['matched']}"
                for row in connection.execute(f'SELECT dataset_id, filled_at, matched FROM {FILLS_TABLE}').fetchall()}


def matched_by_appendix(repository: Any) -> dict[str, Any]:
    """The CDRs with CA fields and how many of their tests have them, for the CA Appendix card."""
    ensure_table(repository)
    ready = _ready_cdrs(repository)
    with repository.connection() as connection:
        rows = connection.execute(f'SELECT dataset_id, matched FROM {FILLS_TABLE} WHERE matched > 0').fetchall()
    cdrs = [{'dataset_id': int(row['dataset_id']), 'file_name': ready[int(row['dataset_id'])]['file_name'],
             'matched': int(row['matched'])} for row in rows if int(row['dataset_id']) in ready]
    return {'cdrs': cdrs, 'tests': sum(item['matched'] for item in cdrs)}


# -- the background job ----------------------------------------------------------------------------
_jobs: dict[str, dict[str, Any]] = {}
# The CDRs that could not be filled, until the application restarts.
_failed: set[tuple[str, int]] = set()
_jobs_guard = threading.Lock()


def _key(database_path: Any) -> str:
    return str(Path(database_path).resolve())


def queue_fill(repository: Any, submit: Callable[[Callable[[], None]], Any],
               should_stop: Callable[[], bool] = lambda: False) -> bool:
    """Queue the writing of the CA fields of the CDRs whose fields are not those of the current CA Appendices (once per
    workspace, one CDR per job)."""
    key = _key(repository.db_path)
    with _jobs_guard:
        job = _jobs.get(key)
        if job and job['status'] == 'queued':
            return False
        if job and job['status'] == 'processing':
            job['again'] = True
            return False
        _jobs[key] = {'status': 'queued', 'queued_at': time.time(), 'started_at': None, 'done': 0, 'total': 0,
                      'name': '', 'again': False}

    def run() -> None:
        with _jobs_guard:
            _jobs[key].update(status='processing', started_at=_jobs[key]['started_at'] or time.time())
        follow = False
        try:
            if should_stop():
                return
            stale = [item for item in stale_datasets(repository) if (key, item[0]) not in _failed]
            with _jobs_guard:
                _jobs[key]['total'] = max(_jobs[key]['total'], _jobs[key]['done'] + len(stale))
            if stale:
                dataset_id, kind = stale[0]
                name = _ready_cdrs(repository).get(dataset_id, {}).get('file_name', '')
                with _jobs_guard:
                    _jobs[key]['name'] = name
                try:
                    matched = fill_dataset(repository, dataset_id, kind, should_stop)
                    if matched < 0:
                        return
                    if hasattr(repository, 'try_add_log'):
                        repository.try_add_log('system', 'ca_appendix_fields_filled', json.dumps(
                            {'dataset_id': dataset_id, 'file': name, 'tests_with_ca_fields': matched}, ensure_ascii=False))
                except Exception as exc:  # noqa: BLE001 - a CDR that cannot be filled keeps its fields until restart.
                    _failed.add((key, dataset_id))
                    if hasattr(repository, 'try_add_log'):
                        repository.try_add_log('system', 'ca_appendix_fill_failed', json.dumps(
                            {'dataset_id': dataset_id, 'file': name, 'error': str(exc)}, ensure_ascii=False))
                with _jobs_guard:
                    _jobs[key]['done'] += 1
                follow = any((key, item) not in _failed for item, _kind in stale_datasets(repository))
        finally:
            if follow:
                with _jobs_guard:
                    _jobs[key]['status'] = 'queued'
                submit(run)
            else:
                with _jobs_guard:
                    again = _jobs[key].get('again')
                    _jobs.pop(key, None)
                if again and not should_stop():
                    queue_fill(repository, submit, should_stop)

    submit(run)
    return True


def fill_tasks(database_path: Any) -> list[dict[str, Any]]:
    """The writing of the CA fields in the CDRs, as a background task card."""
    with _jobs_guard:
        job = dict(_jobs.get(_key(database_path)) or {})
    if not job:
        return []
    detail = ((f"{job['done']} of {job['total']} CDRs written; waiting for the work before the next" if job['total']
               else 'Waiting for the work before it') if job['status'] == 'queued' else
              f"{job['name']} (CDR {job['done'] + 1} of {job['total']})" if job['total'] else 'Finding the CDRs to write')
    return [{
        'id': 'ca-appendix-fill', 'label': 'CA Appendix fields of the CDRs', 'detail': detail, 'status': job['status'],
        'progress': round(100 * job['done'] / job['total']) if job['total'] else None,
        'queued_at': job['queued_at'], 'started_at': job['started_at'], 'completed_at': None,
    }]
