"""Layer 3 - DT Logs: the parsed drivetest logs (Layer 3) of the tests of each campaign.

A delivery is one or more CSV files, or their ZIP, of a parser of the drivetest logs: one row per record of the
log of each test (radio samples of the LTE and NR serving, secondary and neighbour cells, events, L3 messages of
RRC, NAS and SIP, RRC states, PDSCH and PUSCH statistics and the call session), keyed by its JoinID (the JOIN_ID
of the CDRs) and its UE (A and B of a voice call, Data of a data test). The columns keep the names of the parser;
``FIELDS`` names the ones the tool reads.

The rows never go through SQLite. DuckDB reads the delivery and writes the rows of each campaign, as they come,
into one Parquet file of the input folder: the source of one dataset per campaign, as the CDRs are. A delivery of
several campaigns is split while it is processed, and its own file is removed once its campaigns are written.
Each dataset keeps one row per session (JoinID and UE) with its summary in ``l3_dt_log_sessions``; a session in
several datasets is read from the newest one.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable

import duckdb

KIND = 'l3_dt_logs'
LABEL = 'Layer 3 - DT Logs'
# The reserved input type it replaced: its datasets are read as Layer 3 - DT Logs.
LEGACY_KINDS = ('smart_orchestrator_logs',)
SESSIONS_TABLE = 'l3_dt_log_sessions'
# The UEs with a session of every JoinID (any spelling of its case), for the NQ calls that have a log.
JOIN_IDS_TABLE = 'l3_dt_log_join_ids'
TABLE_TITLES = {SESSIONS_TABLE: 'Layer 3 DT Log Sessions', JOIN_IDS_TABLE: 'Layer 3 DT Log JoinIDs'}
# The UEs of the sessions of an NQ call (A, B or Data), as SQL over the NQ calls (their join_id column).
CALL_LOG_SQL = f"COALESCE((SELECT ues FROM {JOIN_IDS_TABLE} WHERE join_key = lower(join_id)), '')"
STORE_FOLDER = '.l3-store'
SOURCE_SUFFIX = '.parquet'
# Raise when the sessions summary changes, so every dataset is summarised again from its source.
SESSIONS_VERSION = 1

# The columns of the parser the tool reads, by role.
FIELDS: dict[str, str] = {
    'log_day': 'Log_Day',
    'campaign': 'Campaign',
    'operator': 'Operator',
    'service': 'Session_Type',
    'session_name': 'Session_Name',
    'status': 'Call_Status',
    'join_id': 'JoinID',
    'log_file': 'File_Name',
    'start': 'Call_Start_Time',
    'end': 'Call_End_Time',
    'duration': 'Session_Duration',
    'ue': 'UE',
    'source_table': 'SourceTable',
    'time': 'EventFullDate',
    'latitude': 'Latitude',
    'longitude': 'Longitude',
    'ran': 'RANConfiguration',
}
REQUIRED_FIELDS = ('campaign', 'join_id', 'ue', 'time', 'latitude', 'longitude', 'source_table')
DATA_UE = 'Data'

SESSION_COLUMNS = (
    ('dataset_id', 'INTEGER NOT NULL'), ('join_id', 'TEXT NOT NULL'), ('ue', 'TEXT NOT NULL'),
    ('campaign', 'TEXT'), ('operator', 'TEXT'), ('service', 'TEXT'), ('session_name', 'TEXT'),
    ('call_status', 'TEXT'), ('start_time', 'TEXT'), ('end_time', 'TEXT'), ('duration_s', 'REAL'),
    ('records', 'INTEGER'), ('positions', 'INTEGER'),
    ('min_latitude', 'REAL'), ('max_latitude', 'REAL'), ('min_longitude', 'REAL'), ('max_longitude', 'REAL'),
    ('first_latitude', 'REAL'), ('first_longitude', 'REAL'), ('last_latitude', 'REAL'), ('last_longitude', 'REAL'),
    ('ran_configurations', 'TEXT'), ('source_tables', 'TEXT'), ('log_day', 'TEXT'), ('log_file', 'TEXT'),
    ('evidence_json', 'TEXT'),
)

ProgressCallback = Callable[[int], None]


def quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sql_text(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def is_l3_kind(kind: object) -> bool:
    return str(kind or '').casefold() in {KIND, *LEGACY_KINDS}


def store_root(database_path: Any) -> Path:
    """The folder of the derived files of the Layer 3 - DT Logs of a workspace, beside its database."""
    return Path(str(database_path)).resolve().parent / STORE_FOLDER


def dataset_folder(database_path: Any, dataset_id: int) -> Path:
    return store_root(database_path) / str(int(dataset_id))


# --------------------------------------------------------------------------------------------------------------
# Sessions table

def ensure_schema(connection: sqlite3.Connection) -> None:
    columns = ', '.join(f'{name} {kind}' for name, kind in SESSION_COLUMNS)
    connection.execute(f'CREATE TABLE IF NOT EXISTS {SESSIONS_TABLE} ({columns}, PRIMARY KEY (dataset_id, join_id, ue))')
    existing = {row[1] for row in connection.execute(f'PRAGMA table_info({SESSIONS_TABLE})')}
    for name, kind in SESSION_COLUMNS:
        if name not in existing:
            connection.execute(f'ALTER TABLE {SESSIONS_TABLE} ADD COLUMN {name} {kind.replace(" NOT NULL", "")}')
    connection.execute(f'CREATE INDEX IF NOT EXISTS idx_{SESSIONS_TABLE}_join ON {SESSIONS_TABLE} (join_id, ue)')
    connection.execute(f'CREATE INDEX IF NOT EXISTS idx_{SESSIONS_TABLE}_join_key ON {SESSIONS_TABLE} (lower(join_id))')
    connection.execute(f'CREATE TABLE IF NOT EXISTS {JOIN_IDS_TABLE} (join_key TEXT PRIMARY KEY, ues TEXT NOT NULL, '
                       'sessions INTEGER NOT NULL DEFAULT 0, dataset_ids TEXT NOT NULL DEFAULT \'\')')


def refresh_join_ids(connection: sqlite3.Connection) -> None:
    """The JoinIDs of every session of the workspace with their UEs (A, B or Data) and datasets."""
    connection.execute(f'DELETE FROM {JOIN_IDS_TABLE}')
    connection.execute(
        f"INSERT INTO {JOIN_IDS_TABLE} (join_key, ues, sessions, dataset_ids) "
        f"SELECT join_key, group_concat(ue, ', '), COUNT(*), group_concat(datasets, ',') FROM ("
        f"  SELECT lower(join_id) AS join_key, ue, group_concat(dataset_id, ',') AS datasets FROM {SESSIONS_TABLE} "
        f"  GROUP BY lower(join_id), ue ORDER BY lower(join_id), ue) GROUP BY join_key")


def normalise_join_id(value: object) -> str:
    """A JoinID as the CDRs write their JOIN_ID: 0x and its hexadecimal digits in capitals."""
    text = str(value or '').strip()
    return '0x' + text[2:].upper() if text[:2].casefold() == '0x' else text.upper()


def join_id_expression(column: str) -> str:
    """normalise_join_id in DuckDB SQL."""
    return (f"CASE WHEN LOWER(LEFT(TRIM({column}), 2)) = '0x' THEN '0x' || UPPER(SUBSTR(TRIM({column}), 3)) "
            f"ELSE UPPER(TRIM({column})) END")


def normalise_ue(value: object) -> str:
    """The UE of a session: A or B of a voice call, Data of a data test (also D, as the KMZ files name it)."""
    text = str(value or '').strip().upper()
    return DATA_UE if text in {'', 'DATA', 'D'} else text


def ue_expression(column: str) -> str:
    """normalise_ue in DuckDB SQL."""
    return (f"CASE WHEN COALESCE(UPPER(TRIM({column})), '') IN ('', 'DATA', 'D') THEN '{DATA_UE}' "
            f"ELSE UPPER(TRIM({column})) END")


# --------------------------------------------------------------------------------------------------------------
# Reading a delivery

def _resolved_columns(columns: Iterable[str]) -> dict[str, str]:
    """The column of the delivery of each role of FIELDS (any spelling of its case and separators)."""
    by_identity = {re.sub(r'[^a-z0-9]', '', str(column).casefold()): str(column) for column in columns}
    resolved: dict[str, str] = {}
    for role, name in FIELDS.items():
        column = by_identity.get(re.sub(r'[^a-z0-9]', '', name.casefold()))
        if column:
            resolved[role] = column
    return resolved


def _delivery_members(source: Path, work: Path) -> list[Path]:
    """The CSV or Parquet files of a delivery: the file itself, or the CSV files of its ZIP extracted into ``work``."""
    suffix = source.suffix.casefold()
    if suffix in {'.csv', '.txt', SOURCE_SUFFIX}:
        return [source]
    if suffix != '.zip':
        raise ValueError('A Layer 3 - DT Logs delivery is one or more CSV files or their ZIP.')
    members: list[Path] = []
    with zipfile.ZipFile(source) as archive:
        names = [info for info in archive.infolist() if not info.is_dir()
                 and Path(info.filename).suffix.casefold() in {'.csv', '.txt'}
                 and not Path(info.filename).name.startswith(('.', '__MACOSX'))
                 and '__MACOSX' not in Path(info.filename).parts]
        if not names:
            raise ValueError('The ZIP has no CSV file of a Layer 3 - DT Logs delivery.')
        needed = sum(int(info.file_size) for info in names)
        free = shutil.disk_usage(work.parent if work.parent.exists() else source.parent).free
        if needed + 512 * 1024 ** 2 > free:
            raise ValueError(f'Not enough free disk space to read the delivery: it needs {needed / 1024 ** 3:.1f} GB.')
        work.mkdir(parents=True, exist_ok=True)
        for index, info in enumerate(names):
            target = work / f'{index:03d}-{Path(info.filename).name}'
            with archive.open(info) as reader, target.open('wb') as writer:
                shutil.copyfileobj(reader, writer, 8 * 1024 ** 2)
            members.append(target)
    return members


def _read_relation(duck: duckdb.DuckDBPyConnection, members: list[Path]) -> str:
    """The SQL that reads the rows of a delivery, every value as the text it has in the files."""
    if all(member.suffix.casefold() == SOURCE_SUFFIX for member in members):
        files = ', '.join(sql_text(member) for member in members)
        return f'read_parquet([{files}], union_by_name = true)'
    files = ', '.join(sql_text(member) for member in members)
    return (f'read_csv([{files}], header = true, all_varchar = true, union_by_name = true, '
            f'null_padding = true, ignore_errors = false, max_line_size = 16777216)')


def campaign_profile(raw_campaign: str) -> dict[str, str]:
    """The campaign of a dataset (``2026-Q3``) and its NR Mode from the Campaign of its rows (``UK_Q3_SA_2026``)."""
    from src.modules.cdr_campaign import campaign_of_rows
    from src.modules.column_names import campaign_parts
    from src.modules.nr_mode import infer_nr_mode

    _year, _quarter, mode = campaign_parts(raw_campaign)
    return {
        'campaign': campaign_of_rows([raw_campaign]) or str(raw_campaign or '').strip(),
        'campaign_label': str(raw_campaign or '').strip(),
        'nr_mode': mode if mode in {'NSA', 'SA'} else infer_nr_mode(raw_campaign),
    }


def _safe_name(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', '_', str(text)).strip(' ._') or 'campaign'


def campaign_source_name(stem: str, raw_campaign: str) -> str:
    """The file name of the rows of one campaign of a delivery."""
    stem = re.sub(rf'\s*-\s*{re.escape(_safe_name(raw_campaign))}$', '', stem)
    return f'{_safe_name(stem)} - {_safe_name(raw_campaign)}{SOURCE_SUFFIX}'


def _session_rows(duck: duckdb.DuckDBPyConnection, table: str, columns: dict[str, str], raw_campaign: str) -> list[tuple]:
    """The summary of every session (JoinID and UE) of one campaign of a delivery."""
    def column(role: str) -> str:
        return quote(columns[role]) if role in columns else 'NULL'

    lat = f'TRY_CAST({column("latitude")} AS DOUBLE)'
    lon = f'TRY_CAST({column("longitude")} AS DOUBLE)'
    placed = f'({lat} IS NOT NULL AND {lon} IS NOT NULL AND NOT ({lat} = 0 AND {lon} = 0))'
    moment = f'TRY_CAST({column("time")} AS TIMESTAMP)'
    ue = ue_expression(column('ue'))
    query = f"""
        SELECT {join_id_expression(column('join_id'))} AS join_id, {ue} AS ue,
               ANY_VALUE({column('operator')}), ANY_VALUE({column('service')}), ANY_VALUE({column('session_name')}),
               ANY_VALUE({column('status')}), MIN({column('start')}), MAX({column('end')}),
               MAX(TRY_CAST({column('duration')} AS DOUBLE)), COUNT(*),
               COUNT(DISTINCT CASE WHEN {placed} THEN {lat}::VARCHAR || ',' || {lon}::VARCHAR END),
               MIN(CASE WHEN {placed} THEN {lat} END), MAX(CASE WHEN {placed} THEN {lat} END),
               MIN(CASE WHEN {placed} THEN {lon} END), MAX(CASE WHEN {placed} THEN {lon} END),
               ARG_MIN(CASE WHEN {placed} THEN {lat} END, {moment}) FILTER (WHERE {placed}),
               ARG_MIN(CASE WHEN {placed} THEN {lon} END, {moment}) FILTER (WHERE {placed}),
               ARG_MAX(CASE WHEN {placed} THEN {lat} END, {moment}) FILTER (WHERE {placed}),
               ARG_MAX(CASE WHEN {placed} THEN {lon} END, {moment}) FILTER (WHERE {placed}),
               STRING_AGG(DISTINCT NULLIF(TRIM({column('ran')}), ''), ', ' ORDER BY NULLIF(TRIM({column('ran')}), '')),
               STRING_AGG(DISTINCT NULLIF(TRIM({column('source_table')}), ''), ', ' ORDER BY NULLIF(TRIM({column('source_table')}), '')),
               MIN({column('log_day')}), ANY_VALUE({column('log_file')})
        FROM {table}
        WHERE {quote(columns['campaign'])} IS NOT DISTINCT FROM ? AND NULLIF(TRIM({column('join_id')}), '') IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    return [tuple(row) for row in duck.execute(query, [raw_campaign]).fetchall()]


def _summary(sessions: list[tuple], raw_campaign: str, profile: dict[str, str], records: int, columns: int,
             source_name: str) -> dict[str, Any]:
    operators = sorted({str(row[2]) for row in sessions if row[2]})
    services: dict[str, int] = {}
    statuses: dict[str, int] = {}
    days = sorted({str(row[21])[:10] for row in sessions if row[21]})
    for row in sessions:
        services[str(row[3] or 'Unknown')] = services.get(str(row[3] or 'Unknown'), 0) + 1
        statuses[str(row[5] or 'Unknown')] = statuses.get(str(row[5] or 'Unknown'), 0) + 1
    return {
        'l3': {
            'version': SESSIONS_VERSION, 'campaign': profile['campaign'], 'campaign_label': raw_campaign,
            'nr_mode': profile['nr_mode'], 'operators': operators, 'services': dict(sorted(services.items())),
            'statuses': dict(sorted(statuses.items())), 'sessions': len(sessions),
            'join_ids': len({row[0] for row in sessions}), 'records': int(records), 'columns': int(columns),
            'days': len(days), 'first_day': days[0] if days else '', 'last_day': days[-1] if days else '',
            'source': source_name,
        },
        'rows': int(records),
        'columns': [],
    }


def _write_sessions(repository: Any, dataset_id: int, sessions: list[tuple], raw_campaign: str) -> None:
    placeholders = ', '.join('?' for _ in SESSION_COLUMNS)
    names = ', '.join(name for name, _kind in SESSION_COLUMNS)
    rows = [(int(dataset_id), row[0], row[1], raw_campaign, *row[2:], None) for row in sessions]
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        ensure_schema(connection)
        connection.execute(f'DELETE FROM {SESSIONS_TABLE} WHERE dataset_id = ?', (int(dataset_id),))
        connection.executemany(f'INSERT INTO {SESSIONS_TABLE} ({names}) VALUES ({placeholders})', rows)
        refresh_join_ids(connection)


def _rename_dataset(repository: Any, dataset_id: int, file_name: str, stored_path: Path) -> None:
    with repository.connection() as connection:
        connection.execute('UPDATE datasets SET file_name = ?, stored_path = ? WHERE id = ?',
                           (file_name, str(stored_path), int(dataset_id)))


def _forget_dataset(repository: Any, dataset_id: int) -> None:
    """Remove a dataset whose campaign file another delivery of the same name now writes."""
    repository.delete_dataset(int(dataset_id))
    forget_datasets(repository, [int(dataset_id)])


def _ready_profile(raw_campaign: str, profile: dict[str, str], summary: dict[str, Any], records: int,
                   columns: int, processed_at: str) -> dict[str, Any]:
    from src.modules.repository import local_now_iso

    return {
        'status': 'ready', 'progress': 100, 'processing_step': 'Completed', 'dataset_kind': KIND,
        'row_count': int(records), 'column_count': int(columns), 'default_metric': '', 'default_aggregation': 'all',
        'available_metrics_json': '[]', 'available_aggregations_json': '[]', 'filter_options_json': '{}',
        'summary_json': json.dumps(summary, ensure_ascii=False), 'kpis_json': '{}',
        'processed_at': processed_at or local_now_iso(), 'last_error': None,
    }


def process_delivery(repository: Any, dataset_id: int, source: Path, *, progress: ProgressCallback | None = None,
                     normalization_version: int | None = None) -> dict[str, Any]:
    """Read a delivery and write the rows of each of its campaigns as the source of one dataset per campaign.

    The dataset being processed keeps the first campaign (by its Campaign value); every other campaign is a
    dataset of its own, created or, for a delivery uploaded again under the same name, refreshed. Returns the
    datasets it wrote, with their campaigns, sessions and rows.
    """
    from src.modules.repository import local_now_iso

    started = time.monotonic()
    report = progress or (lambda _value: None)
    dataset = repository.get_dataset(int(dataset_id))
    if not dataset:
        raise ValueError('Dataset not found.')
    uploaded_by = str(dataset['uploaded_by'] or '') if 'uploaded_by' in dataset.keys() else ''
    source = Path(source)
    root = store_root(repository.db_path)
    work = root / 'tmp' / f'{int(dataset_id)}-{os.getpid()}'
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    try:
        report(15)
        members = _delivery_members(source, work / 'members')
        report(25)
        # The parser writes the rows of each session together, so they are copied in their order, without
        # sorting the hundreds of columns of the log.
        duck = duckdb.connect(config={
            'memory_limit': '2GB', 'threads': 4, 'temp_directory': str(work / 'spill'), 'preserve_insertion_order': True})
        try:
            delivery = _read_relation(duck, members)
            header = [row[0] for row in duck.execute(f'DESCRIBE SELECT * FROM {delivery}').fetchall()]
            columns = _resolved_columns(header)
            missing = [FIELDS[role] for role in REQUIRED_FIELDS if role not in columns]
            if missing:
                raise ValueError('This file is not a Layer 3 - DT Logs delivery: it has no '
                                 + ', '.join(missing) + (' column.' if len(missing) == 1 else ' columns.'))
            campaign_column = quote(columns['campaign'])
            campaigns = [(row[0], int(row[1])) for row in duck.execute(
                f'SELECT {campaign_column}, COUNT(*) FROM {delivery} GROUP BY 1 ORDER BY 1 NULLS LAST').fetchall()]
            if not campaigns:
                raise ValueError('The delivery has no rows.')
            report(30)
            stem = Path(str(dataset['file_name'] or source.name)).stem
            processed_at = local_now_iso()
            for index, (raw, records) in enumerate(campaigns):
                raw_campaign = '' if raw is None else str(raw).strip()
                profile = campaign_profile(raw_campaign)
                target = source.parent / campaign_source_name(stem, raw_campaign or 'No campaign')
                temporary = target.with_name(f'.{target.name}.{os.getpid()}.tmp')
                duck.execute(
                    f'COPY (SELECT * FROM {delivery} WHERE {campaign_column} IS NOT DISTINCT FROM ?) '
                    f'TO {sql_text(temporary)} (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 122880)', [raw])
                sessions = _session_rows(duck, f'read_parquet({sql_text(temporary)})', columns, raw)
                summary = _summary(sessions, raw_campaign, profile, records, len(header), target.name)
                if index == 0:
                    target_id = int(dataset_id)
                    other = next((row for row in repository.list_datasets()
                                  if str(row['stored_path'] or '') == str(target) and int(row['id']) != target_id), None)
                    if other:
                        _forget_dataset(repository, int(other['id']))
                    os.replace(temporary, target)
                    if source.resolve() != target.resolve():
                        _rename_dataset(repository, target_id, target.stem, target)
                    created = False
                else:
                    os.replace(temporary, target)
                    target_id, created = repository.add_dataset(target.stem, str(target), uploaded_by)
                    target_id = int(target_id)
                    repository.update_dataset_profile(target_id, processing_started_at=processed_at)
                _write_sessions(repository, target_id, sessions, raw_campaign)
                profile_fields = _ready_profile(raw_campaign, profile, summary, records, len(header), processed_at)
                if normalization_version is not None:
                    profile_fields['normalization_version'] = int(normalization_version)
                if target_id != int(dataset_id):
                    repository.update_dataset_profile(target_id, **profile_fields)
                written.append({
                    'dataset_id': target_id, 'created': bool(created), 'campaign': profile['campaign'],
                    'campaign_label': raw_campaign, 'nr_mode': profile['nr_mode'], 'file': target.name,
                    'records': records, 'sessions': len(sessions), 'join_ids': summary['l3']['join_ids'],
                    'profile': profile_fields,
                })
                report(30 + int(65 * (index + 1) / len(campaigns)))
        finally:
            duck.close()
        if source.exists() and all(Path(source).resolve() != (source.parent / item['file']).resolve() for item in written):
            source.unlink()
        # The dataset processed is completed last, so the page shows its campaigns together.
        first = written[0]
        repository.update_dataset_profile(int(dataset_id), **first['profile'])
        return {'datasets': [{key: value for key, value in item.items() if key != 'profile'} for item in written],
                'seconds': round(time.monotonic() - started, 1)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def forget_datasets(repository: Any, dataset_ids: Iterable[int] | None = None) -> None:
    """Remove the sessions and derived files of deleted datasets (of those given, else of every missing one)."""
    with repository.connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (SESSIONS_TABLE,)).fetchone()
        alive = {int(row[0]) for row in connection.execute('SELECT id FROM datasets')}
        if exists:
            stale = ({int(value) for value in dataset_ids} - alive if dataset_ids is not None else
                     {int(row[0]) for row in connection.execute(f'SELECT DISTINCT dataset_id FROM {SESSIONS_TABLE}')} - alive)
            if stale:
                connection.executemany(f'DELETE FROM {SESSIONS_TABLE} WHERE dataset_id = ?', [(value,) for value in stale])
                ensure_schema(connection)
                refresh_join_ids(connection)
    root = store_root(repository.db_path)
    if root.is_dir():
        for folder in root.iterdir():
            if folder.is_dir() and folder.name.isdigit() and int(folder.name) not in alive:
                shutil.rmtree(folder, ignore_errors=True)


def ensure_workspace_schema(connection: sqlite3.Connection) -> None:
    """The sessions table of a workspace; the datasets of the reserved Smart Orchestrator Logs type become
    Layer 3 - DT Logs."""
    ensure_schema(connection)
    placeholders = ', '.join('?' for _ in LEGACY_KINDS)
    connection.execute(
        f"UPDATE dataset_profiles SET dataset_kind = ? WHERE LOWER(COALESCE(dataset_kind, '')) IN ({placeholders})",
        (KIND, *LEGACY_KINDS))


# --------------------------------------------------------------------------------------------------------------
# Reading the datasets

def ready_datasets(repository: Any) -> list[dict[str, Any]]:
    """The ready Layer 3 - DT Logs datasets of a workspace, newest first, with their campaign and summary."""
    datasets = []
    for row in repository.list_datasets():
        if not is_l3_kind(row['dataset_kind']) or str(row['status'] or '') != 'ready':
            continue
        try:
            summary = json.loads(row['summary_json'] or '{}').get('l3') or {}
        except (TypeError, ValueError):
            summary = {}
        datasets.append({'id': int(row['id']), 'file_name': row['file_name'], 'stored_path': row['stored_path'],
                         'uploaded_at': row['uploaded_at'], **summary})
    datasets.sort(key=lambda item: (str(item.get('uploaded_at') or ''), int(item['id'])), reverse=True)
    return datasets


def dataset_summary(row: Any) -> dict[str, Any]:
    """What the Datasets card shows of a Layer 3 - DT Logs dataset: its campaign, NR Mode, operators and sessions."""
    try:
        summary = json.loads((row.get('summary_json') if isinstance(row, dict) else row['summary_json']) or '{}')
    except (TypeError, ValueError):
        summary = {}
    return summary.get('l3') or {}


def source_columns(source: Any) -> list[str]:
    """The columns of the source of a Layer 3 - DT Logs dataset, as the parser named them."""
    path = Path(str(source or ''))
    if path.suffix.casefold() != SOURCE_SUFFIX or not path.is_file():
        return []
    with duckdb.connect() as duck:
        return [row[0] for row in duck.execute(f'DESCRIBE SELECT * FROM read_parquet({sql_text(path)})').fetchall()]


def preview_frame(source: Any, columns: Iterable[str], limit: int) -> Any:
    """The first rows of a Layer 3 - DT Logs dataset, read from its source (the dataset has no rows in SQLite)."""
    import pandas as pd

    path = Path(str(source or ''))
    wanted = [column for column in columns if column in set(source_columns(path))]
    if not wanted:
        return pd.DataFrame(columns=list(columns))
    with duckdb.connect() as duck:
        return duck.execute(
            f'SELECT {", ".join(quote(column) for column in wanted)} FROM read_parquet({sql_text(path)}) LIMIT {int(limit)}'
        ).fetchdf()


def _session_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    item.pop('evidence_json', None)
    return item


def sessions_of_join_ids(repository: Any, join_ids: Iterable[object]) -> dict[str, list[dict[str, Any]]]:
    """The sessions of each JoinID (any spelling of its case), one per UE read from the newest dataset that has it."""
    keys = sorted({str(value or '').strip().casefold() for value in join_ids if str(value or '').strip()})
    found: dict[str, list[dict[str, Any]]] = {key: [] for key in keys}
    if not keys:
        return found
    with repository.connection() as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (SESSIONS_TABLE,)).fetchone():
            return found
        order = {int(row['id']): (str(row['uploaded_at'] or ''), int(row['id']))
                 for row in connection.execute('SELECT id, uploaded_at FROM datasets')}
        for start in range(0, len(keys), 500):
            chunk = keys[start:start + 500]
            rows = connection.execute(
                f"SELECT s.*, d.file_name AS dataset_name, d.stored_path AS source FROM {SESSIONS_TABLE} s "
                f"JOIN datasets d ON d.id = s.dataset_id WHERE lower(s.join_id) IN ({', '.join('?' for _ in chunk)})",
                chunk).fetchall()
            newest: dict[tuple[str, str], Any] = {}
            for row in rows:
                key = (str(row['join_id']).casefold(), str(row['ue']))
                if key not in newest or order.get(int(row['dataset_id']), ('', 0)) > order.get(int(newest[key]['dataset_id']), ('', 0)):
                    newest[key] = row
            for (join_key, _ue), row in sorted(newest.items()):
                found[join_key].append(_session_dict(row))
    return found


def nq_calls_by_dataset(repository: Any) -> dict[int, int]:
    """How many NQ calls of the workspace have a session in each Layer 3 - DT Logs dataset."""
    with repository.connection() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if SESSIONS_TABLE not in tables or 'nq_calls' not in tables:
            return {}
        rows = connection.execute(
            f"SELECT s.dataset_id, COUNT(DISTINCT n.call_key) FROM nq_calls n "
            f"JOIN {SESSIONS_TABLE} s ON lower(s.join_id) = lower(n.join_id) WHERE n.join_id <> '' GROUP BY s.dataset_id"
        ).fetchall()
    return {int(row[0]): int(row[1]) for row in rows}
