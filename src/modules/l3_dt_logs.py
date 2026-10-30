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
# The fields of a record never shown on the maps.
HIDDEN_FIELDS = frozenset({'imsi'})

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
                build_points(target, points_path(repository.db_path, target_id))
                build_evidence(repository, target_id, target)
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
    # The JoinIDs of the first sessions, written in capitals (0X…), as the CDRs write them (0x…).
    connection.execute(f"UPDATE {SESSIONS_TABLE} SET join_id = '0x' || UPPER(SUBSTR(join_id, 3)) WHERE SUBSTR(join_id, 1, 2) = '0X'")
    # The JoinIDs of the sessions imported before their table was kept.
    if (connection.execute(f'SELECT 1 FROM {SESSIONS_TABLE} LIMIT 1').fetchone()
            and not connection.execute(f'SELECT 1 FROM {JOIN_IDS_TABLE} LIMIT 1').fetchone()):
        refresh_join_ids(connection)
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


def _session_dict(row: Any, evidence: bool = False) -> dict[str, Any]:
    item = dict(row)
    if not evidence:
        item.pop('evidence_json', None)
    return item


def sessions_of_join_ids(repository: Any, join_ids: Iterable[object], *, evidence: bool = False) -> dict[str, list[dict[str, Any]]]:
    """The sessions of each JoinID (any spelling of its case), one per UE read from the newest dataset that has it (with
    their evidence when asked)."""
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
                found[join_key].append(_session_dict(row, evidence))
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


# --------------------------------------------------------------------------------------------------------------
# The layers of the maps: the points of every session, as the KMZ files of the NQ team draw them

# Raise when the points change, so every dataset builds them again from its source.
POINTS_VERSION = 4
POINTS_FILE = 'points.parquet'
# The kinds of point and the layers of the KMZ files they give (the metrics of each kind are its layers).
POINT_KINDS: dict[str, dict[str, Any]] = {
    'lte_pcell': {'label': 'LTE PCell', 'tech': 'LTE', 'metrics': ('earfcn', 'pci', 'rsrp', 'rsrq', 'sinr')},
    'lte_scell': {'label': 'LTE SCell', 'tech': 'LTE', 'metrics': ('earfcn', 'pci', 'rsrp', 'rsrq', 'sinr')},
    'lte_ncell': {'label': 'LTE NCell', 'tech': 'LTE', 'metrics': ('earfcn', 'pci', 'rsrp', 'rsrq')},
    'lte_tx': {'label': 'LTE PCell UE Tx Power', 'tech': 'LTE', 'metrics': ('tx',)},
    'nr_pcell': {'label': 'NR PCell', 'tech': 'NR', 'metrics': ('nrarfcn', 'pci', 'rsrp', 'rsrq', 'sinr')},
    'nr_scell': {'label': 'NR SCell', 'tech': 'NR', 'metrics': ('nrarfcn', 'pci', 'rsrp', 'rsrq', 'sinr')},
    'nr_ncell': {'label': 'NR NCell', 'tech': 'NR', 'metrics': ('nrarfcn', 'pci', 'rsrp', 'rsrq')},
    'nr_lncell': {'label': 'NR LTE NCell', 'tech': 'LTE', 'metrics': ('earfcn', 'pci', 'rsrp', 'rsrq')},
    'nr_tx': {'label': 'NR PCell UE Tx Power', 'tech': 'NR', 'metrics': ('tx',)},
    # The 2G and 3G serving cells, which only the RAN Configuration layer draws.
    'gsm': {'label': 'GSM serving cell', 'tech': 'GSM', 'metrics': ()},
    'wcdma': {'label': 'WCDMA serving cell', 'tech': 'WCDMA', 'metrics': ()},
    'event': {'label': 'Event', 'tech': '', 'metrics': ()},
    'l3': {'label': 'L3 Signaling', 'tech': '', 'metrics': ()},
}
# The serving points, which the RAN Configuration layer draws.
SERVING_KINDS = ('lte_pcell', 'lte_scell', 'lte_tx', 'nr_pcell', 'nr_scell', 'nr_tx', 'gsm', 'wcdma')
EVENT_GROUPS = ('4G', '5G EN-DC', '5G NR', 'Other')
L3_GROUPS = ('LTE-NAS', 'LTE-RRC', 'NR-NAS', 'NR-RRC', 'SIP', 'Other')
RAN_CONFIGURATIONS = ('LTE', '5G EN-DC', '5G SA', 'GSM', 'UNKNOWN')
POINT_COLUMNS = ('join_id', 'ue', 'kind', 'ts', 'ms', 'lat', 'lon', 'ran', 'freq', 'pci', 'rsrp', 'rsrq', 'sinr', 'tx',
                 'cell', 'grp', 'name', 'detail', 'direction', 'row')

# NR bands by downlink frequency (MHz), in the order they are chosen where they overlap.
NR_BANDS_MHZ = (
    ('n1', 2110, 2170), ('n3', 1805, 1880), ('n7', 2620, 2690), ('n8', 925, 960), ('n20', 791, 821),
    ('n28', 758, 803), ('n32', 1452, 1496), ('n38', 2570, 2620), ('n40', 2300, 2400), ('n41', 2496, 2690),
    ('n78', 3300, 3800), ('n77', 3300, 4200), ('n79', 4400, 5000), ('n258', 24250, 27500), ('n257', 26500, 29500),
)


def frequency_label(channel: Any, technology: str) -> str:
    """The folder of a channel in the KMZ files: ``EARFCN 223 (B1, 2132.3 MHz)``, ``NRARFCN 628032 (n78, 3420.48 MHz)``."""
    from src.modules.inventory_insights import channel_frequency
    from src.modules.network_insights import lte_band_for_earfcn

    try:
        value = int(float(channel))
    except (TypeError, ValueError):
        return ''
    frequency = channel_frequency(value, technology)
    if str(technology).upper() == 'NR':
        band = next((name for name, low, high in NR_BANDS_MHZ if frequency is not None and low <= frequency <= high), '')
        detail = ', '.join(filter(None, (band, f'{round(frequency, 2):g} MHz' if frequency is not None else '')))
        return f'NRARFCN {value}' + (f' ({detail})' if detail else '')
    band = lte_band_for_earfcn(value)
    detail = ', '.join(filter(None, (band, f'{frequency:.1f} MHz' if frequency is not None else '')))
    return f'EARFCN {value}' + (f' ({detail})' if detail else '')


def _points_sql(source: Path, columns: set[str]) -> str:
    """The points of every session of a source, one row per point of each kind (see POINT_KINDS)."""
    def col(name: str) -> str:
        return quote(name) if name in columns else 'NULL'

    def number(name: str) -> str:
        return f'TRY_CAST({col(name)} AS DOUBLE)'

    def integer(name: str) -> str:
        return f'TRY_CAST(TRY_CAST({col(name)} AS DOUBLE) AS BIGINT)'

    def text(*names: str) -> str:
        values = [f"NULLIF(TRIM({col(name)}), '')" for name in names if name in columns]
        return f'COALESCE({", ".join(values)})' if len(values) > 1 else (values[0] if values else 'NULL')

    def select(kind: str, where: str, *, freq: str = 'NULL', pci: str = 'NULL', rsrp: str = 'NULL', rsrq: str = 'NULL',
               sinr: str = 'NULL', tx: str = 'NULL', cell: str = 'NULL', grp: str = 'NULL', name: str = 'NULL',
               detail: str = 'NULL', direction: str = 'NULL') -> str:
        return (f"SELECT join_id, ue, '{kind}' AS kind, ts, ms, lat, lon, ran, {freq} AS freq, {pci} AS pci, "
                f"{rsrp} AS rsrp, {rsrq} AS rsrq, {sinr} AS sinr, {tx} AS tx, {cell} AS cell, {grp} AS grp, "
                f"{name} AS name, {detail} AS detail, {direction} AS direction, row FROM rows WHERE {where}")

    source_table = col('SourceTable')
    lte_carrier = number('Radio_CarrierIndex')
    nr_carrier = number('NRRadio_CarrierIndex')
    msg_type = number('MsgType')
    neighbour_tech = f"LOWER(COALESCE({col('NRLTENL_Technology')}, ''))"
    event_group = (f"CASE WHEN {text('Event_EventGroup')} IN ('4G', '5G EN-DC', '5G NR') THEN {text('Event_EventGroup')} "
                   f"WHEN {text('ATE_EventTopGroup')} = '_4G' THEN '4G' WHEN {text('ATE_EventTopGroup')} = '_5G_EN_DC' THEN '5G EN-DC' "
                   f"WHEN {text('ATE_EventTopGroup')} = '_5G_NR' THEN '5G NR' ELSE 'Other' END")
    l3_layer = text('L3_Layer')
    l3_group = (f"CASE WHEN {l3_layer} IN ('LTE-NAS', 'LTE-RRC', 'SIP') THEN {l3_layer} WHEN {l3_layer} IN ('5GNR-NAS', '5G-NAS') THEN 'NR-NAS' "
                f"WHEN {l3_layer} = '5GNR-RRC' THEN 'NR-RRC' WHEN {l3_layer} IN ('NR-NAS', 'NR-RRC') THEN {l3_layer} ELSE 'Other' END")
    rows = (f"SELECT {join_id_expression(col('JoinID'))} AS join_id, {ue_expression(col('UE'))} AS ue, "
            f"SUBSTR(TRIM({col('EventFullDate')}), 1, 23) AS ts, "
            f"EPOCH_MS(TRY_CAST({col('EventFullDate')} AS TIMESTAMP)) AS ms, "
            f"{number('Latitude')} AS lat, {number('Longitude')} AS lon, {text('RANConfiguration')} AS ran, "
            f"file_row_number AS row, * EXCLUDE (file_row_number) "
            f"FROM read_parquet({sql_text(source)}, file_row_number = true) "
            # A session the parser exported under two log days (the same records twice) is drawn once, from its first.
            f"QUALIFY {col('Log_Day')} IS NOT DISTINCT FROM MIN({col('Log_Day')}) OVER (PARTITION BY "
            f"{join_id_expression(col('JoinID'))}, {ue_expression(col('UE'))})")
    parts = [
        select("lte_pcell", f"{source_table} = 'FactLTERadio' AND {integer('Radio_EARFCN')} IS NOT NULL AND COALESCE({lte_carrier}, 0) = 0",
               freq=integer('Radio_EARFCN'), pci=integer('Radio_PhyCellId'), rsrp=number('Radio_RSRP'), rsrq=number('Radio_RSRQ'),
               sinr=number('Radio_SINR'), cell=text('LTE_ECI_Combined', 'LTE_ECI')),
        select("lte_scell", f"{source_table} = 'FactLTERadio' AND {integer('Radio_EARFCN')} IS NOT NULL AND COALESCE({lte_carrier}, 0) <> 0",
               freq=integer('Radio_EARFCN'), pci=integer('Radio_PhyCellId'), rsrp=number('Radio_RSRP'), rsrq=number('Radio_RSRQ'),
               sinr=number('Radio_SINR'), cell=text('LTE_ECI_Combined', 'LTE_ECI')),
        select("lte_tx", f"{number('PUSCH_PuschTxPower')} IS NOT NULL", tx=number('PUSCH_PuschTxPower'),
               cell=text('LTE_ECI_Combined', 'LTE_ECI')),
        select("lte_ncell", f"{source_table} = 'FactLTENeighbors' AND {number('Neigh_RSRP')} IS NOT NULL",
               freq=integer('Neigh_DL_EARFCN'), pci=integer('Neigh_PCI'), rsrp=number('Neigh_RSRP'), rsrq=number('Neigh_RSRQ')),
        select("nr_pcell", f"{source_table} = 'FactNR5GRadio' AND {integer('NRRadio_NRARFCN')} IS NOT NULL AND COALESCE({nr_carrier}, 0) = 0",
               freq=integer('NRRadio_NRARFCN'), pci=integer('NRRadio_PCI'), rsrp=number('NRRadio_RSRP'), rsrq=number('NRRadio_RSRQ'),
               sinr=number('NRRadio_SINR'), cell=text('NR_NCI')),
        select("nr_scell", f"{source_table} = 'FactNR5GRadio' AND {integer('NRRadio_NRARFCN')} IS NOT NULL AND COALESCE({nr_carrier}, 0) <> 0",
               freq=integer('NRRadio_NRARFCN'), pci=integer('NRRadio_PCI'), rsrp=number('NRRadio_RSRP'), rsrq=number('NRRadio_RSRQ'),
               sinr=number('NRRadio_SINR'), cell=text('NR_NCI')),
        select("nr_tx", f"{number('NRPUSCH_PUSCHTxPower')} IS NOT NULL", tx=number('NRPUSCH_PUSCHTxPower'), cell=text('NR_NCI')),
        select("gsm", f"{source_table} = 'FactGSMRadio' AND COALESCE({integer('GSMRadio_ARFCN')}, {number('GSMRadio_RxLevel')}) IS NOT NULL", freq=integer('GSMRadio_ARFCN'), pci=integer('GSMRadio_BSIC'),
               rsrp=number('GSMRadio_RxLevel'), cell=text('GSMRadio_CI', 'GSMRadio_CID')),
        select("wcdma", f"{source_table} = 'FactWCDMARadio' AND {integer('WCDMARadio_UARFCN')} IS NOT NULL", freq=integer('WCDMARadio_UARFCN'), pci=integer('WCDMARadio_PSC'),
               rsrp=number('WCDMARadio_RSCP'), rsrq=number('WCDMARadio_EcNo'), cell=text('WCDMARadio_CID')),
        # The neighbour list of NR: its NR cells, and its LTE cells while the UE is on NR (5G EN-DC or SA; on LTE alone the
        # list repeats the LTE neighbours of FactLTENeighbors).
        select("nr_ncell", f"{source_table} = 'FactNR5GLTENeighborList' AND {neighbour_tech} LIKE '%nr%' "
                           f"AND {integer('NRLTENL_ARFCN')} IS NOT NULL",
               freq=integer('NRLTENL_ARFCN'), pci=integer('NRLTENL_PCI'), rsrp=number('NRLTENL_RSRP'), rsrq=number('NRLTENL_RSRQ')),
        select("nr_lncell", f"{source_table} = 'FactNR5GLTENeighborList' AND {neighbour_tech} LIKE '%lte%' "
                            f"AND COALESCE(ran, '') IN ('5G EN-DC', '5G SA') AND {number('NRLTENL_RSRP')} IS NOT NULL",
               freq=integer('NRLTENL_ARFCN'), pci=integer('NRLTENL_PCI'), rsrp=number('NRLTENL_RSRP'), rsrq=number('NRLTENL_RSRQ')),
        select("event", f"{source_table} IN ('FactEvent', 'FactAdvancedTriggerEvent')", grp=event_group,
               name=text('Event_EventName', 'ATE_EventFullName'), detail=text('Event_EventSummary', 'ATE_EventSummary')),
        select("l3", f"{source_table} = 'FactL3Messages'", grp=l3_group, name=text('L3_SimpleMsgName', 'L3_MsgName'),
               detail=text('L3_CombinedMsgNameSIPResponse', 'L3_SIPResponse'), direction=text('L3_Direction'),
               freq=integer('L3_ARFCN'), pci=integer('L3_PCI')),
    ]
    return f"WITH rows AS ({rows}) " + ' UNION ALL '.join(parts)


def points_path(database_path: Any, dataset_id: int) -> Path:
    return dataset_folder(database_path, dataset_id) / POINTS_FILE


def build_points(source: Path, target: Path) -> int:
    """Write the points of a source to ``target``, by session and time; returns how many there are."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f'.{target.name}.{os.getpid()}.tmp')
    with duckdb.connect(config={'memory_limit': '1GB', 'threads': 4}) as duck:
        columns = {row[0] for row in duck.execute(f'DESCRIBE SELECT * FROM read_parquet({sql_text(source)})').fetchall()}
        duck.execute(f'COPY (SELECT * FROM ({_points_sql(source, columns)}) ORDER BY join_id, ue, ms, kind, row) '
                     f'TO {sql_text(temporary)} (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 50000)')
        count = int(duck.execute(f'SELECT COUNT(*) FROM read_parquet({sql_text(temporary)})').fetchone()[0])
    os.replace(temporary, target)
    (target.parent / 'points.json').write_text(json.dumps({'version': POINTS_VERSION, 'points': count,
                                                           'source': str(source)}), encoding='utf-8')
    return count


def ensure_points(database_path: Any, dataset_id: int, source: Any) -> Path | None:
    """The points of a dataset, built again when they are missing or of an earlier version."""
    target = points_path(database_path, dataset_id)
    source = Path(str(source or ''))
    try:
        manifest = json.loads((target.parent / 'points.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        manifest = {}
    if target.is_file() and manifest.get('version') == POINTS_VERSION and manifest.get('source') == str(source):
        return target
    if not source.is_file():
        return None
    build_points(source, target)
    return target


# The columns of the points a map receives, in this order (see call_layers).
CLIENT_COLUMNS = ('kind', 'ms', 'ts', 'lat', 'lon', 'ran', 'freq', 'pci', 'rsrp', 'rsrq', 'sinr', 'tx', 'cell', 'grp', 'name',
                  'detail', 'direction', 'row')
MAX_CALL_POINTS = 60000


def _track(rows: list[tuple], ms_index: int, lat_index: int, lon_index: int) -> list[list[Any]]:
    """The way of the UE: its positions in time order, each once while it stays there."""
    track: list[list[Any]] = []
    for row in rows:
        lat, lon = row[lat_index], row[lon_index]
        if lat is None or lon is None or (lat == 0 and lon == 0):
            continue
        if track and track[-1][1] == lat and track[-1][2] == lon:
            continue
        track.append([row[ms_index], lat, lon])
    return track


def session_points(database_path: Any, session: dict[str, Any], limit: int = MAX_CALL_POINTS) -> list[tuple]:
    """The points of one session (in time order), read from the points of its dataset."""
    points = ensure_points(database_path, int(session['dataset_id']), session.get('source'))
    if points is None:
        return []
    names = ', '.join(CLIENT_COLUMNS)
    with duckdb.connect() as duck:
        return duck.execute(
            f'SELECT {names} FROM read_parquet({sql_text(points)}) WHERE join_id = ? AND ue = ? ORDER BY ms, row LIMIT ?',
            [normalise_join_id(session['join_id']), str(session['ue']), int(limit)]).fetchall()


def call_layers(repository: Any, join_id: str) -> dict[str, Any]:
    """The Layer 3 - DT Logs of a call for its map: its sessions (one per UE), their points by kind of layer, the way of
    each UE and the folder name of every channel (as the KMZ files name them)."""
    sessions = sessions_of_join_ids(repository, [join_id]).get(str(join_id or '').strip().casefold(), [])
    index = {name: position for position, name in enumerate(CLIENT_COLUMNS)}
    ues: dict[str, Any] = {}
    channels: dict[str, str] = {}
    for session in sessions:
        rows = session_points(repository.db_path, session)
        for row in rows:
            kind, freq = row[index['kind']], row[index['freq']]
            if freq is not None and kind in POINT_KINDS and POINT_KINDS[kind]['tech'] in {'LTE', 'NR'}:
                tech = POINT_KINDS[kind]['tech']
                channels.setdefault(f'{tech}:{freq}', frequency_label(freq, tech))
        ues[str(session['ue'])] = {
            'session': {key: session.get(key) for key in (
                'dataset_id', 'dataset_name', 'join_id', 'ue', 'campaign', 'operator', 'service', 'session_name', 'call_status',
                'start_time', 'end_time', 'duration_s', 'records', 'positions', 'ran_configurations', 'log_day', 'log_file')},
            'points': [list(row) for row in rows],
            'track': _track(rows, index['ms'], index['lat'], index['lon']),
            'truncated': len(rows) >= MAX_CALL_POINTS,
        }
    return {
        'join_id': join_id, 'columns': list(CLIENT_COLUMNS), 'ues': ues, 'channels': channels,
        'kinds': {key: {'label': value['label'], 'tech': value['tech'], 'metrics': list(value['metrics'])}
                  for key, value in POINT_KINDS.items()},
    }


def source_row(source: Any, row: int) -> dict[str, Any]:
    """Every value of one record of a source (its row number in the file), for the details of a point."""
    path = Path(str(source or ''))
    if not path.is_file():
        return {}
    with duckdb.connect() as duck:
        found = duck.execute(f'SELECT * EXCLUDE (file_row_number) FROM read_parquet({sql_text(path)}, file_row_number = true) '
                             f'WHERE file_row_number = ?', [int(row)]).fetchdf()
    if found.empty:
        return {}
    record = found.iloc[0].to_dict()
    # The subscriber identity of the test SIM is kept in the source but never shown.
    return {str(key): value for key, value in record.items()
            if str(key).casefold() not in HIDDEN_FIELDS and value is not None and str(value).strip() not in {'', 'nan', 'None'}}


# --------------------------------------------------------------------------------------------------------------
# What the log tells of each session, for the DT Analyzer RCA and the Diagnosis hints of the map of a call

# Raise when the evidence changes, so every dataset works it out again (and the DT Analyzer RCA reads it again).
EVIDENCE_VERSION = 3
# The seconds before the end of a session read as "at the failure" (the radio), and as "before the failure" (the rest).
RADIO_WINDOW_MS = 5000
EVENT_WINDOW_MS = 10000
# The SIP answers of a normal call or registration: the challenge of the registration, the end of a request cancelled
# and a subscription event the network does not support.
NORMAL_SIP_CODES = frozenset({401, 407, 487, 489})
ALARM_WORDS = re.compile(r'fail|reestablish|reject|drop|timeout|lost|abort|forced|release|irat|redirect|handover', re.IGNORECASE)
_SIP_CODE = re.compile(r'\b([1-6]\d\d)\b')


def sip_code(*texts: Any) -> int:
    """The SIP status code of a message (``408 Request Timeout``), 0 when it has none."""
    for text in texts:
        match = _SIP_CODE.search(str(text or ''))
        if match:
            return int(match.group(1))
    return 0


def compute_evidence(points: Path, source: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """The evidence of every session of a dataset, from its points (and its source for BLER and the sessions without
    measurements)."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    if not points.is_file():
        return found
    with duckdb.connect(config={'memory_limit': '1GB', 'threads': 4}) as duck:
        duck.execute(f"""CREATE TEMP VIEW q AS WITH p AS (SELECT * FROM read_parquet({sql_text(points)})),
            ends AS (SELECT join_id, ue, MAX(ms) AS end_ms FROM p GROUP BY 1, 2)
            SELECT p.*, e.end_ms, e.end_ms - p.ms AS before FROM p JOIN ends e USING (join_id, ue)""")
        serving = "kind IN ('lte_pcell', 'lte_scell', 'lte_tx', 'nr_pcell', 'nr_scell', 'nr_tx', 'gsm', 'wcdma')"
        radio = []
        for tech in ('lte', 'nr'):
            for measure in ('rsrp', 'sinr'):
                radio.append(f"COALESCE(AVG({measure}) FILTER (WHERE kind = '{tech}_pcell' AND before <= {RADIO_WINDOW_MS}), "
                             f"ARG_MAX({measure}, ms) FILTER (WHERE kind = '{tech}_pcell' AND {measure} IS NOT NULL)) AS {tech}_{measure}_end")
            radio.append(f"MIN(rsrp) FILTER (WHERE kind = '{tech}_pcell') AS {tech}_rsrp_min")
            radio.append(f"ARG_MAX(pci, ms) FILTER (WHERE kind = '{tech}_pcell') AS {tech}_pci_end")
            radio.append(f"ARG_MAX(freq, ms) FILTER (WHERE kind = '{tech}_pcell') AS {tech}_freq_end")
        recent = f"kind IN ('event', 'l3') AND before <= {EVENT_WINDOW_MS}"
        rows = duck.execute(f"""
            SELECT join_id, ue, MAX(end_ms), {', '.join(radio)},
                   COUNT(*) FILTER (WHERE {recent} AND name ILIKE '%reestablishment%') AS reestablishments,
                   COUNT(*) FILTER (WHERE {recent} AND kind = 'event' AND name ILIKE '%SCG Failure%') AS scg_failures,
                   COUNT(*) FILTER (WHERE {recent} AND kind = 'event' AND name ILIKE '%SCG Forced Release%') AS scg_releases,
                   COUNT(*) FILTER (WHERE {recent} AND kind = 'event' AND name ILIKE '%Handover Attempt%') AS handovers,
                   COUNT(*) FILTER (WHERE {recent} AND kind = 'event' AND (name ILIKE '%IRAT%' OR name ILIKE '%Redirection%')) AS irat,
                   COUNT(*) FILTER (WHERE {recent} AND name ILIKE '%release%') AS releases,
                   COUNT(*) FILTER (WHERE kind = 'l3' AND name ILIKE '%reject%') AS rejects,
                   MAX(tx) FILTER (WHERE kind IN ('lte_tx', 'nr_tx') AND before <= {EVENT_WINDOW_MS}) AS tx_max,
                   100.0 * COUNT(*) FILTER (WHERE kind IN ('lte_tx', 'nr_tx') AND before <= {EVENT_WINDOW_MS} AND tx >= 22)
                     / NULLIF(COUNT(*) FILTER (WHERE kind IN ('lte_tx', 'nr_tx') AND before <= {EVENT_WINDOW_MS}), 0) AS tx_high,
                   ARG_MAX(ran, ms) FILTER (WHERE {serving}) AS ran_end,
                   STRING_AGG(DISTINCT name, ' | ') FILTER (WHERE {recent} AND name IS NOT NULL) AS signalling,
                   LIST([CAST(ms AS VARCHAR), COALESCE(name, ''), COALESCE(detail, '')]) FILTER (WHERE kind = 'l3' AND grp = 'SIP') AS sip,
                   LIST([CAST(end_ms - ms AS VARCHAR), kind, COALESCE(grp, ''), COALESCE(name, ''), COALESCE(detail, ''),
                         COALESCE(CAST(pci AS VARCHAR), ''), COALESCE(CAST(freq AS VARCHAR), ''), CAST(ms AS VARCHAR)])
                     FILTER (WHERE kind IN ('event', 'l3') AND before <= 15000) AS recent_events
            FROM q GROUP BY 1, 2""").fetchall()
        names = ['end_ms', *(entry.rsplit(' AS ', 1)[1] for entry in radio), 'reestablishments', 'scg_failures', 'scg_releases',
                 'handovers', 'irat', 'releases', 'rejects', 'tx_max', 'tx_high', 'ran_end', 'signalling', 'sip', 'recent_events']
        for row in rows:
            found[(row[0], row[1])] = dict(zip(names, row[2:]))
        # The strongest LTE neighbour of the channel of the serving PCell against it, second by second, before the failure
        # (a neighbour of another channel stronger than the serving cell is no sign of a missing handover).
        for join_id, ue, delta, neighbour_pci, serving_pci, seconds in duck.execute(f"""
                WITH s AS (SELECT join_id, ue, CAST(ms / 1000 AS BIGINT) AS second, AVG(rsrp) AS rsrp, ANY_VALUE(pci) AS pci,
                                  ANY_VALUE(freq) AS freq FROM q
                           WHERE kind = 'lte_pcell' AND rsrp IS NOT NULL AND before <= {EVENT_WINDOW_MS} GROUP BY 1, 2, 3),
                     n AS (SELECT join_id, ue, CAST(ms / 1000 AS BIGINT) AS second, pci, freq, MAX(rsrp) AS rsrp FROM q
                           WHERE kind = 'lte_ncell' AND rsrp IS NOT NULL AND before <= {EVENT_WINDOW_MS} GROUP BY 1, 2, 3, 4, 5)
                SELECT n.join_id, n.ue, MAX(n.rsrp - s.rsrp), ARG_MAX(n.pci, n.rsrp - s.rsrp), ARG_MAX(s.pci, n.rsrp - s.rsrp),
                       COUNT(DISTINCT n.second) FILTER (WHERE n.rsrp - s.rsrp >= 3)
                FROM n JOIN s USING (join_id, ue, second) WHERE n.freq = s.freq AND n.pci <> s.pci GROUP BY 1, 2""").fetchall():
            entry = found.setdefault((join_id, ue), {})
            entry.update({'neighbour_delta': delta, 'neighbour_pci': neighbour_pci, 'neighbour_serving_pci': serving_pci,
                          'neighbour_seconds': seconds})
        # BLER (in % in the source, whatever its name says) and the sessions without measurements, from the source.
        if Path(source).is_file():
            columns = {row[0] for row in duck.execute(f'DESCRIBE SELECT * FROM read_parquet({sql_text(source)})').fetchall()}

            def col(name: str) -> str:
                return quote(name) if name in columns else 'NULL'

            moment = f"EPOCH_MS(TRY_CAST({col('EventFullDate')} AS TIMESTAMP))"
            for join_id, ue, lte_bler, nr_bler, empty in duck.execute(f"""
                    WITH r AS (SELECT {join_id_expression(col('JoinID'))} AS join_id, {ue_expression(col('UE'))} AS ue, {moment} AS ms,
                                      {col('SourceTable')} AS source_table, TRY_CAST({col('PDSCH_BLERDecimal')} AS DOUBLE) AS lte_bler,
                                      TRY_CAST({col('NRPDSCH_BLERDecimal')} AS DOUBLE) AS nr_bler
                               FROM read_parquet({sql_text(source)})),
                         e AS (SELECT *, MAX(ms) OVER (PARTITION BY join_id, ue) - ms AS before FROM r)
                    SELECT join_id, ue, AVG(lte_bler) FILTER (WHERE before <= {EVENT_WINDOW_MS}),
                           AVG(nr_bler) FILTER (WHERE before <= {EVENT_WINDOW_MS}),
                           COUNT(*) FILTER (WHERE source_table = 'NoMeasurements') FROM e GROUP BY 1, 2""").fetchall():
                entry = found.setdefault((join_id, ue), {})
                entry.update({'lte_bler': lte_bler, 'nr_bler': nr_bler, 'no_measurements': int(empty or 0)})
    for entry in found.values():
        sip = [(sip_code(detail, name), int(float(ms)), name, detail) for ms, name, detail in entry.pop('sip', None) or []]
        errors = [item for item in sip if item[0] >= 400 and item[0] not in NORMAL_SIP_CODES]
        worst = max(errors, key=lambda item: (item[0] >= 500, item[0]), default=None)
        entry['sip_error'] = worst[0] if worst else 0
        entry['sip_error_text'] = (worst[3] or worst[2]) if worst else ''
        events, seen = [], set()
        for before, kind, group, name, detail, pci, freq, ms in sorted(entry.pop('recent_events', None) or [], key=lambda item: float(item[0])):
            code = sip_code(detail, name) if group == 'SIP' else 0
            # An event the log gives twice at once (its event and its trigger event) counts once.
            if (name, ms) in seen:
                continue
            seen.add((name, ms))
            if ALARM_WORDS.search(name or '') or (code >= 400 and code not in NORMAL_SIP_CODES):
                events.append({'before_s': round(float(before) / 1000, 1), 'kind': kind, 'group': group, 'name': name, 'detail': detail,
                               'pci': pci, 'freq': freq, 'ms': int(float(ms))})
        entry['events'] = events[:12]
        entry['version'] = EVIDENCE_VERSION
    return found


def _store_evidence(repository: Any, dataset_id: int, evidence: dict[tuple[str, str], dict[str, Any]]) -> None:
    with repository.connection() as connection:
        connection.executemany(
            f'UPDATE {SESSIONS_TABLE} SET evidence_json = ? WHERE dataset_id = ? AND lower(join_id) = lower(?) AND ue = ?',
            [(json.dumps(value, ensure_ascii=False, default=str), int(dataset_id), key[0], key[1]) for key, value in evidence.items()])
        # Sessions with nothing the log tells are kept as read.
        connection.execute(f"UPDATE {SESSIONS_TABLE} SET evidence_json = ? WHERE dataset_id = ? AND evidence_json IS NULL",
                           (json.dumps({'version': EVIDENCE_VERSION}), int(dataset_id)))


def build_evidence(repository: Any, dataset_id: int, source: Any) -> int:
    """Work out and keep the evidence of every session of a dataset; returns how many sessions have some."""
    points = ensure_points(repository.db_path, int(dataset_id), source)
    evidence = compute_evidence(points, Path(str(source))) if points else {}
    _store_evidence(repository, int(dataset_id), evidence)
    return len(evidence)


def ensure_evidence(repository: Any) -> list[int]:
    """The evidence of the ready datasets whose sessions have none, or of an earlier version; returns their ids."""
    with repository.connection() as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (SESSIONS_TABLE,)).fetchone():
            return []
        stale = [int(row[0]) for row in connection.execute(
            f"SELECT DISTINCT dataset_id FROM {SESSIONS_TABLE} WHERE evidence_json IS NULL "
            f"OR COALESCE(json_extract(evidence_json, '$.version'), 0) <> ?", (EVIDENCE_VERSION,))]
    built = []
    for dataset in ready_datasets(repository):
        if dataset['id'] in stale:
            build_evidence(repository, dataset['id'], dataset['stored_path'])
            built.append(dataset['id'])
    return built


def rca_signature(repository: Any) -> dict[str, list[Any]]:
    """What the DT Analyzer RCA reads of the Layer 3 - DT Logs: each ready dataset with when it was processed and the
    Campaign of its rows (the calls of that campaign are calculated again when it changes)."""
    signature = {}
    for row in repository.list_datasets():
        if is_l3_kind(row['dataset_kind']) and str(row['status'] or '') == 'ready':
            summary = dataset_summary(row)
            signature[str(int(row['id']))] = [str(row['processed_at'] or row['uploaded_at'] or ''), summary.get('campaign_label') or '',
                                              EVIDENCE_VERSION]
    return signature


def _shown_number(value: Any, digits: int = 1) -> str:
    try:
        return f'{float(value):.{digits}f}'.rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return ''


def call_evidence(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """The inputs of the DT Analyzer RCA of a call from the evidence of its sessions (one per UE): counts added, the
    worst radio of its UEs, its signalling before the failure and a note for the evidence."""
    items = []
    for session in sessions:
        try:
            evidence = json.loads(session.get('evidence_json') or '{}') or {}
        except (TypeError, ValueError):
            evidence = {}
        items.append((str(session['ue']), evidence))
    if not items:
        return {}

    def numbers(key: str) -> list[float]:
        return [float(value) for _ue, evidence in items if (value := evidence.get(key)) is not None]

    def lowest(key: str) -> float | None:
        values = numbers(key)
        return min(values) if values else None

    def highest(key: str) -> float | None:
        values = numbers(key)
        return max(values) if values else None

    def total(key: str) -> int:
        return int(sum(numbers(key)))

    inputs: dict[str, Any] = {
        'l3_log': ', '.join(ue for ue, _evidence in items),
        'l3_lte_rsrp_end': lowest('lte_rsrp_end'), 'l3_lte_sinr_end': lowest('lte_sinr_end'),
        'l3_nr_rsrp_end': lowest('nr_rsrp_end'), 'l3_nr_sinr_end': lowest('nr_sinr_end'),
        'l3_lte_rsrp_min': lowest('lte_rsrp_min'), 'l3_nr_rsrp_min': lowest('nr_rsrp_min'),
        'l3_reestablishments': total('reestablishments'), 'l3_scg_failures': total('scg_failures'),
        'l3_handovers': total('handovers'), 'l3_irat': total('irat'), 'l3_releases': total('releases'), 'l3_rejects': total('rejects'),
        'l3_sip_error': int(highest('sip_error') or 0), 'l3_tx_max': highest('tx_max'), 'l3_tx_high_share': highest('tx_high'),
        'l3_neighbour_delta': highest('neighbour_delta'), 'l3_neighbour_seconds': highest('neighbour_seconds'),
        'l3_lte_bler': highest('lte_bler'), 'l3_nr_bler': highest('nr_bler'),
        'l3_no_measurements': total('no_measurements'),
        'l3_ran_end': next((evidence.get('ran_end') for ue, evidence in items if ue in {'A', 'Data'} and evidence.get('ran_end')),
                           next((evidence.get('ran_end') for _ue, evidence in items if evidence.get('ran_end')), '')) or '',
        'l3_signalling': ' · '.join(f"{'' if ue == 'Data' else f'UE {ue}: '}{evidence['signalling']}"
                                    for ue, evidence in items if evidence.get('signalling'))[:600],
    }
    notes = []
    for ue, evidence in items:
        prefix = '' if ue == 'Data' or len(items) == 1 else f'UE {ue}: '
        for event in (evidence.get('events') or [])[:3]:
            where = f" on PCI {event['pci']}" if event.get('pci') else ''
            notes.append(f"{prefix}{event['name'] or event['detail']} {_shown_number(event['before_s'])} s before the end{where}")
        if evidence.get('neighbour_delta') is not None and float(evidence['neighbour_delta']) >= 3:
            notes.append(f"{prefix}LTE neighbour PCI {evidence.get('neighbour_pci')} {_shown_number(evidence['neighbour_delta'])} dB above "
                         f"the serving PCI {evidence.get('neighbour_serving_pci')}")
    inputs[L3_NOTE] = ('Layer 3 - DT Logs: ' + '; '.join(notes)) if notes else ''
    return {key: value for key, value in inputs.items() if value is not None}


L3_NOTE = 'l3_note'


def rca_inputs(repository: Any, join_ids: Iterable[object]) -> dict[str, dict[str, Any]]:
    """The inputs of the DT Analyzer RCA of each JOIN_ID (any spelling of its case) with sessions in the logs."""
    ensure_evidence(repository)
    sessions = sessions_of_join_ids(repository, join_ids, evidence=True)
    return {key: call_evidence(items) for key, items in sessions.items() if items}


def map_checks(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Diagnosis hints the Layer 3 - DT Logs of a call give (its map): what failed in its last seconds and its radio
    there, each with the moment of the log it points at (``at``: the UE and the time of its point) when it has one."""
    checks: list[dict[str, Any]] = []

    def add(key: str, level: str, title: str, detail: str, ue: str = '', ms: Any = None) -> None:
        check = {'key': key, 'level': level, 'title': title, 'detail': detail, 'source': 'l3'}
        if ms is not None:
            check['at'] = {'ue': ue, 'ms': int(ms)}
        checks.append(check)

    for session in sessions:
        try:
            evidence = json.loads(session.get('evidence_json') or '{}') or {}
        except (TypeError, ValueError):
            continue
        ue = str(session['ue'])
        who = '' if ue == 'Data' or len(sessions) == 1 else f' (UE {ue})'
        events = evidence.get('events') or []

        def first(pattern: str) -> dict[str, Any] | None:
            return next((event for event in events if re.search(pattern, f"{event.get('name')} {event.get('detail')}", re.IGNORECASE)), None)

        if evidence.get('no_measurements') and evidence.get('lte_rsrp_end') is None and evidence.get('nr_rsrp_end') is None:
            add('l3_no_measurements', 'warn', f'No measurements in the log{who}',
                'The drivetest log of the session has records without measurements and no radio: check the device and its logging.', ue)
        scg = first(r'SCG Failure')
        if scg:
            add('l3_scg', 'bad', f'SCG failure{who}', f"{scg['name']} {_shown_number(scg['before_s'])} s before the end"
                f"{(' on PCI ' + str(scg['pci'])) if scg.get('pci') else ''}; NR RSRP at the end "
                f"{_shown_number(evidence.get('nr_rsrp_end')) or '—'} dBm.", ue, scg.get('ms'))
        reestablishment = first(r'reestablish')
        if reestablishment:
            add('l3_reestablishment', 'bad', f'RRC re-establishment{who}', f"{reestablishment['name']} {_shown_number(reestablishment['before_s'])} s "
                f"before the end: the radio link failed; LTE RSRP at the end {_shown_number(evidence.get('lte_rsrp_end')) or '—'} dBm.",
                ue, reestablishment.get('ms'))
        if int(evidence.get('sip_error') or 0) >= 400:
            sip = first(rf"\b{int(evidence['sip_error'])}\b")
            add('l3_sip', 'bad', f"SIP {int(evidence['sip_error'])}{who}", f"{evidence.get('sip_error_text') or ''} in the signalling of the call: "
                'the IMS answered with an error.', ue, (sip or {}).get('ms'))
        reject = first(r'reject')
        if reject:
            add('l3_reject', 'bad', f'Rejected by the network{who}', f"{reject['name']} {_shown_number(reject['before_s'])} s before the end.",
                ue, reject.get('ms'))
        delta, seconds = evidence.get('neighbour_delta'), evidence.get('neighbour_seconds') or 0
        if delta is not None and float(delta) >= 6 and seconds >= 3:
            handovers = int(evidence.get('handovers') or 0)
            add('l3_neighbour', 'bad' if not handovers else 'warn', f"{'Stronger neighbour without a handover' if not handovers else 'Stronger neighbour'}{who}",
                f"LTE PCI {evidence.get('neighbour_pci')} of the serving channel was up to {_shown_number(delta)} dB above the serving PCI "
                f"{evidence.get('neighbour_serving_pci')} for {seconds} s before the end, with {handovers} handover attempt"
                f"{'' if handovers == 1 else 's'}: a missing neighbour relation or a late handover.", ue)
        handover = first(r'Handover Attempt|IRAT|Redirection')
        if handover and not first(r'reestablish|SCG Failure'):
            add('l3_handover', 'warn', f'Handover before the failure{who}', f"{handover['name']} {_shown_number(handover['before_s'])} s before "
                'the end.', ue, handover.get('ms'))
        for tech in ('lte', 'nr'):
            rsrp, sinr = evidence.get(f'{tech}_rsrp_end'), evidence.get(f'{tech}_sinr_end')
            label = tech.upper()
            if rsrp is not None and float(rsrp) < -115:
                add(f'l3_{tech}_coverage', 'bad', f'{label} coverage at the failure{who}', f'{label} RSRP {_shown_number(rsrp)} dBm in the last '
                    f'{RADIO_WINDOW_MS // 1000} s of the log (PCI {evidence.get(f"{tech}_pci_end")}).', ue, evidence.get('end_ms'))
            elif sinr is not None and float(sinr) < -3 and (rsrp is None or float(rsrp) >= -105):
                add(f'l3_{tech}_interference', 'bad', f'{label} interference at the failure{who}', f'{label} SINR {_shown_number(sinr)} dB with RSRP '
                    f'{_shown_number(rsrp)} dBm in the last {RADIO_WINDOW_MS // 1000} s of the log.', ue, evidence.get('end_ms'))
        if (evidence.get('tx_high') or 0) >= 50:
            add('l3_uplink', 'warn', f'UE at maximum power{who}', f"UE Tx Power from 22 dBm in {round(float(evidence['tx_high']))}% of its last "
                f"samples (up to {_shown_number(evidence.get('tx_max'))} dBm): the uplink is limited.", ue)
        for tech in ('lte', 'nr'):
            bler = evidence.get(f'{tech}_bler')
            if bler is not None and float(bler) > 30:
                add(f'l3_{tech}_bler', 'warn', f'High {tech.upper()} BLER{who}', f'{tech.upper()} BLER {round(float(bler))}% in the last '
                    f'{EVENT_WINDOW_MS // 1000} s of the log.', ue)
    if sessions and not checks:
        add('l3_fine', 'ok', 'Layer 3 - DT Logs', 'Its log shows no failure, weak radio or rejection in the seconds before the end.')
    return checks
