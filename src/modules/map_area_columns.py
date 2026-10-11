"""The map area of each test, kept in the rows of its CDR.

Placing every test in the Map Areas of its country (the ITL3 areas of the UK) is the slowest part of a Points Lost
Map. Each CDR keeps the area of each of its tests in its ``Map_Area`` column, written in the background when the CDR is
processed (and for the CDRs processed before), with the version of the Map Areas it was placed with: when the Map Areas
change (downloaded, imported or deleted), the areas are placed again in the background, and until then the maps place
the tests themselves. A test outside every area keeps an empty area; one not placed yet keeps none.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from src.modules.column_names import resolve_column_name

MAP_AREA_COLUMN = 'Map_Area'
# The country of the Map Areas of each test (the map draws the areas of its countries).
MAP_AREA_COUNTRY_COLUMN = 'Map_Area_Country'
FILLS_TABLE = 'map_area_fills'
CDR_KINDS = ('data', 'voice', 'speech')


def ensure_table(repository: Any) -> None:
    with repository.connection() as connection:
        connection.execute(f'CREATE TABLE IF NOT EXISTS {FILLS_TABLE} (dataset_id INTEGER PRIMARY KEY, '
                           'version TEXT NOT NULL, filled_at TEXT NOT NULL)')


def areas_version(repository: Any) -> str:
    """The version of the Map Areas of a workspace: its own layers and the ones shipped with the application."""
    from src.modules.map_areas import bundled_layers, list_layers

    layers = [(layer['country_code'], layer['updated_at']) for layer in list_layers(repository)]
    shipped = sorted((code, str(layer.get('level') or ''), str(layer.get('year') or ''), str(layer.get('unit_count') or ''))
                     for code, layer in bundled_layers().items())
    payload = json.dumps({'layers': layers, 'shipped': shipped}, sort_keys=True)
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]


def _ready_cdrs(repository: Any) -> dict[int, str]:
    return {int(row['id']): str(row['dataset_kind']).casefold() for row in repository.list_datasets()
            if str(row['dataset_kind'] or '').casefold() in CDR_KINDS and str(row['status'] or '').casefold() == 'ready'
            and repository.dataset_rows_table_exists(int(row['id']))}


def current_datasets(repository: Any, dataset_ids: list[int]) -> set[int]:
    """The CDRs whose tests are placed with the current Map Areas (their ``Map_Area`` can be read)."""
    ensure_table(repository)
    version = areas_version(repository)
    ids = [int(value) for value in dataset_ids]
    with repository.connection() as connection:
        rows = connection.execute(
            f'SELECT dataset_id FROM {FILLS_TABLE} WHERE version = ? AND dataset_id IN ({", ".join("?" for _ in ids) or "NULL"})',
            [version, *ids]).fetchall()
    # A CDR processed again has new rows, without areas yet.
    return {int(row['dataset_id']) for row in rows
            if MAP_AREA_COLUMN in repository.list_dataset_row_columns(int(row['dataset_id']))}


def stale_datasets(repository: Any) -> list[tuple[int, str]]:
    """The ready CDRs whose tests are not placed with the current Map Areas, newest first."""
    ready = _ready_cdrs(repository)
    current = current_datasets(repository, list(ready))
    return sorted(((dataset_id, kind) for dataset_id, kind in ready.items() if dataset_id not in current), reverse=True)


def _coordinate_columns(available: list[str], kind: str) -> tuple[str, str] | None:
    from src.modules.scoring_points_loss import COORDINATE_SOURCES

    for latitude_name, longitude_name in COORDINATE_SOURCES.get(kind, ()):
        latitude, longitude = resolve_column_name(available, latitude_name), resolve_column_name(available, longitude_name)
        if latitude is not None and longitude is not None:
            return latitude, longitude
    return None


def fill_dataset(repository: Any, dataset_id: int, kind: str) -> int:
    """Place the tests of a CDR in the current Map Areas and keep their areas in its rows; returns how many."""
    from src.modules.map_areas import area_index

    ensure_table(repository)
    version = areas_version(repository)
    table = repository.dataset_rows_table_name(dataset_id)
    quoted = repository._quote_identifier(table)
    available = repository.list_dataset_row_columns(dataset_id)
    coordinates = _coordinate_columns(available, kind)
    with repository.connection() as connection:
        if coordinates is None:
            frame = pd.DataFrame({'rid': pd.Series(dtype='int64')})
        else:
            latitude, longitude = (repository._quote_identifier(column) for column in coordinates)
            frame = pd.read_sql_query(f'SELECT rowid AS rid, {latitude} AS latitude, {longitude} AS longitude FROM {quoted}',
                                      connection)
    if coordinates is not None and not frame.empty:
        places = area_index(repository).places_of(pd.to_numeric(frame['latitude'], errors='coerce'),
                                                  pd.to_numeric(frame['longitude'], errors='coerce'))
        frame['area'] = places['name'].fillna('').astype(str).to_numpy()
        frame['country'] = places['country'].fillna('').astype(str).to_numpy()
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        columns = {row['name'] for row in connection.execute(f'PRAGMA table_info({quoted})').fetchall()}
        if not columns:
            return 0  # The CDR was deleted meanwhile.
        area, country = (repository._quote_identifier(name) for name in (MAP_AREA_COLUMN, MAP_AREA_COUNTRY_COLUMN))
        for name, quoted_name in ((MAP_AREA_COLUMN, area), (MAP_AREA_COUNTRY_COLUMN, country)):
            if name not in columns:
                connection.execute(f'ALTER TABLE {quoted} ADD COLUMN {quoted_name} TEXT')
        if coordinates is None or frame.empty:
            # Tests without coordinates lie in no area.
            connection.execute(f"UPDATE {quoted} SET {area} = '', {country} = ''")
        else:
            connection.execute('CREATE TEMP TABLE IF NOT EXISTS map_area_fill (rid INTEGER PRIMARY KEY, area TEXT, country TEXT)')
            connection.execute('DELETE FROM map_area_fill')
            connection.executemany('INSERT INTO map_area_fill (rid, area, country) VALUES (?, ?, ?)',
                                   zip(frame['rid'].astype(int).tolist(), frame['area'].tolist(), frame['country'].tolist()))
            connection.execute(f'UPDATE {quoted} SET ({area}, {country}) = '
                               f'(SELECT area, country FROM map_area_fill WHERE map_area_fill.rid = {quoted}.rowid)')
            connection.execute('DROP TABLE map_area_fill')
        connection.execute(
            f'INSERT INTO {FILLS_TABLE} (dataset_id, version, filled_at) VALUES (?, ?, ?) '
            'ON CONFLICT(dataset_id) DO UPDATE SET version = excluded.version, filled_at = excluded.filled_at',
            (int(dataset_id), version, pd.Timestamp.now().isoformat(timespec='seconds')))
    return len(frame)


# -- the background job ----------------------------------------------------------------------------
_jobs: dict[str, dict[str, Any]] = {}
# The CDRs that could not be placed (each map places their tests) until the application restarts.
_failed: set[tuple[str, int]] = set()
_jobs_guard = threading.Lock()


def _key(database_path: Any) -> str:
    return str(Path(database_path).resolve())


def queue_fill(repository: Any, submit: Callable[[Callable[[], None]], Any]) -> bool:
    """Queue the placing of the tests of the CDRs not placed with the current Map Areas (once per workspace)."""
    key = _key(repository.db_path)
    with _jobs_guard:
        job = _jobs.get(key)
        if job and job['status'] == 'queued':
            return False
        if job and job['status'] == 'processing':
            job['again'] = True  # Placed again after the running job, with what changed meanwhile.
            return False
        _jobs[key] = {'status': 'queued', 'queued_at': time.time(), 'started_at': None, 'done': 0, 'total': 0,
                      'name': '', 'again': False}

    def run() -> None:
        # One CDR per job: the calculations queued meanwhile go before the next one.
        with _jobs_guard:
            _jobs[key].update(status='processing', started_at=_jobs[key]['started_at'] or time.time())
        follow = False
        try:
            stale = [item for item in stale_datasets(repository) if (key, item[0]) not in _failed]
            # Counted over every ready CDR of the workspace, whatever was placed before.
            ready = len(_ready_cdrs(repository))
            with _jobs_guard:
                _jobs[key].update(total=ready, done=ready - len(stale))
            if stale:
                dataset_id, kind = stale[0]
                name = next((str(row['file_name'] or '') for row in repository.list_datasets()
                             if int(row['id']) == dataset_id), '')
                with _jobs_guard:
                    _jobs[key]['name'] = name
                try:
                    fill_dataset(repository, dataset_id, kind)
                except Exception as exc:  # noqa: BLE001 - a CDR that cannot be placed is placed by each map.
                    _failed.add((key, dataset_id))
                    if hasattr(repository, 'try_add_log'):
                        repository.try_add_log('system', 'map_area_fill_failed', json.dumps(
                            {'dataset_id': dataset_id, 'error': str(exc)}))
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
                if again:
                    queue_fill(repository, submit)

    submit(run)
    return True


def fill_tasks(database_path: Any) -> list[dict[str, Any]]:
    """The placing of the tests in the Map Areas, as a background task card."""
    with _jobs_guard:
        job = dict(_jobs.get(_key(database_path)) or {})
    if not job:
        return []
    detail = ((f"{job['done']} of {job['total']} CDRs of the workspace placed; waiting for the work before the next"
               if job['total'] else 'Waiting for the work before it') if job['status'] == 'queued' else
              f"{job['name']} (CDR {job['done'] + 1} of {job['total']} of the workspace)" if job['total']
              else 'Finding the CDRs to place')
    return [{
        'id': 'map-area-fill', 'label': 'Map Areas of the tests', 'detail': detail, 'status': job['status'],
        'progress': round(100 * job['done'] / job['total']) if job['total'] else None,
        'queued_at': job['queued_at'], 'started_at': job['started_at'], 'completed_at': None,
    }]
