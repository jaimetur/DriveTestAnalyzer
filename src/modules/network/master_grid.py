"""Master Grid: the list of sites of the VodafoneThree network, Keep or Remove, with the configuration and the financial
year in which each site is to be upgraded to the new network (NNS).

The Master Grid List is a workbook delivered every week (``RED_PINK_MasterGridList V1.5 2026_Wk46 ….xlsx``). Its sheet
``MasterSiteGridList`` holds one row per site, under a header row with ``Site ID`` and ``Keep / Remove Status`` (two
rows of notes above it). Only the columns the scoring needs are kept, in the table ``master_grid_sites`` of the
workspace: the rows of the newest Master Grid are those read.

A site of the Master Grid is matched with the serving site of the tests (``Serving_Site_ID`` and
``Serving_Host_Network`` of the CDRs, from the Network Inventory):

* a Vodafone site by its ``Site ID`` (a number);
* a 3 site by its ``SITE ID + Pairing`` (the number of the 3UK site; the ``Site ID`` is its MBNL ID);
* an O2 site by its ``SiteRef2`` (``<number>o2``).

The dataset keeps its workbook as its source: it travels with the workspace (backups, packages and transfers) and is
read again when it is processed again.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

KIND = 'master_grid'
LABEL = 'Master Grid'
SITES_TABLE = 'master_grid_sites'
TABLE_TITLES = {SITES_TABLE: 'Master Grid Sites'}
SHEET_NAME = 'MasterSiteGridList'
# The columns kept, by the header the workbook gives them (in order of preference).
COLUMNS: dict[str, tuple[str, ...]] = {
    'site_id': ('Site ID',),
    'site_pairing': ('SITE ID + Pairing',),
    'site_ref2': ('SiteRef2',),
    'jvco_id': ('JVCO_ID',),
    'operator': ('Operator',),
    'latitude': ('Latitude',),
    'longitude': ('Longitude',),
    'rural_urban': ('Rural / Urban',),
    'keep_remove': ('Keep / Remove Status',),
    'config': ('High/Med/Low config',),
    'target_fy': ('Target Deployment FY (Running Order)', 'Target Deployment FY'),
    'cma_year': ('CMA Year',),
    'nns_vendor': ('NNS Vendor',),
    'region': ('Region',),
    'vodafone_region': ('Vodafone Region',),
}
REQUIRED = ('site_id', 'operator', 'keep_remove', 'config', 'target_fy')
_TEXT_COLUMNS = tuple(name for name in COLUMNS if name not in ('latitude', 'longitude'))
# The host network of the serving cell of a test (Serving_Host_Network) and the operator of its site in the Master Grid.
HOST_OPERATORS = {'vodafone': 'VF', 'h3g': '3UK', '3': '3UK', 'three': '3UK', 'telefonica': 'O2', 'o2': 'O2'}
CONFIG_LABELS = {'high': 'High', 'med': 'Medium', 'medium': 'Medium', 'low': 'Low'}

ProgressCallback = Callable[[int], None]


def _identity(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').casefold())


def _text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


SCHEMA = (f'CREATE TABLE IF NOT EXISTS {SITES_TABLE} (dataset_id INTEGER NOT NULL, '
          + ', '.join(f'{name} {"REAL" if name in ("latitude", "longitude") else "TEXT"}' for name in COLUMNS) + ');\n'
          f'CREATE INDEX IF NOT EXISTS idx_{SITES_TABLE}_dataset ON {SITES_TABLE}(dataset_id);')


def _table_in_place(connection: Any) -> bool:
    from src.modules.core.repository import schema_in_place

    return schema_in_place(connection, SCHEMA)


def ensure_table(repository: Any) -> None:
    with repository.connection() as connection:
        if not _table_in_place(connection):
            connection.executescript(SCHEMA)


def _header_map(row: tuple) -> dict[str, int] | None:
    """The place of each kept column in a header row, or None when it is not the header of the Master Grid."""
    places = {_identity(value): index for index, value in enumerate(row) if _text(value)}
    found = {}
    for name, headers in COLUMNS.items():
        index = next((places[_identity(header)] for header in headers if _identity(header) in places), None)
        if index is not None:
            found[name] = index
    return found if all(name in found for name in REQUIRED) else None


def read_sites(source: Path, progress: ProgressCallback | None = None) -> tuple[list[dict[str, Any]], str]:
    """The sites of a Master Grid workbook (its MasterSiteGridList sheet, or the first sheet with its header) and the
    sheet read."""
    import openpyxl

    report = progress or (lambda _value: None)
    workbook = openpyxl.load_workbook(source, read_only=True, data_only=True)
    try:
        names = [SHEET_NAME, *(name for name in workbook.sheetnames if name != SHEET_NAME)] \
            if SHEET_NAME in workbook.sheetnames else list(workbook.sheetnames)
        for name in names:
            sheet = workbook[name]
            total = max(1, int(sheet.max_row or 1))
            rows = sheet.iter_rows(values_only=True)
            header = None
            for _index, row in zip(range(15), rows):
                header = _header_map(row)
                if header:
                    break
            if not header:
                continue
            sites = []
            for index, row in enumerate(rows, start=1):
                site = {key: row[place] if place < len(row) else None for key, place in header.items()}
                if not _text(site.get('site_id')):
                    continue
                sites.append({**{key: _text(site.get(key)) for key in _TEXT_COLUMNS},
                              'latitude': _number(site.get('latitude')), 'longitude': _number(site.get('longitude'))})
                if index % 5000 == 0:
                    report(15 + int(70 * index / total))
            return sites, name
    finally:
        workbook.close()
    raise ValueError('This file is not a Master Grid: no sheet has the columns Site ID, Operator, Keep / Remove Status, '
                     'High/Med/Low config and Target Deployment FY.')


def _week_of(file_name: str) -> str:
    """The week of a Master Grid as its file names it (2026_Wk46), or ''."""
    match = re.search(r'(20\d\d)[_\- ]?w(?:ee)?k[_\- ]?(\d{1,2})', str(file_name or ''), re.IGNORECASE)
    return f'{match.group(1)}-W{int(match.group(2)):02d}' if match else ''


def process_delivery(repository: Any, dataset_id: int, source: Path, *, progress: ProgressCallback | None = None,
                     normalization_version: int | None = None) -> dict[str, Any]:
    """Read a Master Grid workbook into ``master_grid_sites`` (its previous rows replaced) and mark the dataset ready."""
    from src.modules.core.repository import local_now_iso

    started = time.monotonic()
    report = progress or (lambda _value: None)
    dataset = repository.get_dataset(int(dataset_id))
    if not dataset:
        raise ValueError('Dataset not found.')
    report(12)
    sites, sheet = read_sites(Path(source), report)
    if not sites:
        raise ValueError('The Master Grid has no sites.')
    report(88)
    ensure_table(repository)
    names = list(COLUMNS)
    with repository.connection() as connection:
        connection.execute(f'DELETE FROM {SITES_TABLE} WHERE dataset_id = ?', (int(dataset_id),))
        connection.executemany(
            f'INSERT INTO {SITES_TABLE} (dataset_id, {", ".join(names)}) VALUES (?, {", ".join("?" for _ in names)})',
            [(int(dataset_id), *(site[name] for name in names)) for site in sites])
    counts: dict[str, dict[str, int]] = {'operators': {}, 'keep_remove': {}, 'config': {}, 'target_fy': {}}
    for site in sites:
        for key, field in (('operators', 'operator'), ('keep_remove', 'keep_remove'), ('config', 'config'),
                           ('target_fy', 'target_fy')):
            value = site[field] or '(blank)'
            counts[key][value] = counts[key].get(value, 0) + 1
    week = _week_of(dataset['file_name'] or Path(source).name)
    summary = {'master_grid': {'sites': len(sites), 'sheet': sheet, 'week': week,
                               'keep': sum(1 for site in sites if site['keep_remove'].casefold() == 'keep'), **counts}}
    profile = {
        'status': 'ready', 'progress': 100, 'processing_step': 'Completed', 'dataset_kind': KIND,
        'row_count': len(sites), 'column_count': len(names), 'default_metric': '', 'default_aggregation': 'all',
        'available_metrics_json': '[]', 'available_aggregations_json': '[]', 'filter_options_json': '{}',
        'summary_json': json.dumps(summary, ensure_ascii=False), 'kpis_json': '{}',
        'processed_at': local_now_iso(), 'last_error': None,
    }
    if normalization_version is not None:
        profile['normalization_version'] = int(normalization_version)
    repository.replace_dataset_source_columns(int(dataset_id), [COLUMNS[name][0] for name in names])
    repository.update_dataset_profile(int(dataset_id), **profile)
    return {'sites': len(sites), 'sheet': sheet, 'week': week, 'seconds': round(time.monotonic() - started, 1)}


def forget_datasets(repository: Any) -> None:
    """Remove the sites of the Master Grids deleted."""
    with repository.connection() as connection:
        if _table_in_place(connection):
            connection.execute(f'DELETE FROM {SITES_TABLE} WHERE dataset_id NOT IN (SELECT id FROM datasets)')


def dataset_summary(row: Any) -> dict[str, Any]:
    """What the Datasets card shows of a Master Grid: its sites, Keep sites and week."""
    try:
        summary = json.loads((row.get('summary_json') if isinstance(row, dict) else row['summary_json']) or '{}')
    except (TypeError, ValueError):
        summary = {}
    return summary.get('master_grid') or {}


def latest_dataset(repository: Any) -> dict[str, Any] | None:
    """The newest ready Master Grid of a workspace: its id, file, week and when it was processed."""
    chosen = None
    for row in repository.list_datasets():
        if str(row['dataset_kind'] or '') != KIND or str(row['status'] or '') != 'ready':
            continue
        key = (str(row['uploaded_at'] or ''), int(row['id']))
        if chosen is None or key > chosen[0]:
            chosen = (key, row)
    if chosen is None:
        return None
    row = chosen[1]
    summary = dataset_summary(dict(row))
    return {'id': int(row['id']), 'file_name': str(row['file_name'] or ''), 'week': summary.get('week') or '',
            'processed_at': str(row['processed_at'] or ''), 'sites': int(summary.get('sites') or 0)}


def load_sites(repository: Any, dataset_id: int) -> Any:
    """The sites of a Master Grid as a DataFrame (empty without its table)."""
    import pandas as pd

    with repository.connection() as connection:
        if not _table_in_place(connection):
            return pd.DataFrame(columns=list(COLUMNS))
        rows = connection.execute(f'SELECT {", ".join(COLUMNS)} FROM {SITES_TABLE} WHERE dataset_id = ?',
                                  (int(dataset_id),)).fetchall()
    return pd.DataFrame([tuple(row) for row in rows], columns=list(COLUMNS))


def site_lookup(sites: Any) -> dict[tuple[str, str], dict[str, str]]:
    """The Master Grid site of each (operator, site number) a serving cell can name: Vodafone sites by Site ID, 3 sites
    by SITE ID + Pairing and O2 sites by the number of their SiteRef2."""
    lookup: dict[tuple[str, str], dict[str, str]] = {}
    for site in sites.to_dict('records') if hasattr(sites, 'to_dict') else sites:
        operator = str(site.get('operator') or '').strip().upper()
        details = {'config': CONFIG_LABELS.get(str(site.get('config') or '').strip().casefold(), ''),
                   'keep_remove': str(site.get('keep_remove') or '').strip(),
                   'target_fy': str(site.get('target_fy') or '').strip().upper(),
                   'site_id': str(site.get('site_id') or '').strip()}
        keys = []
        if operator == 'VF':
            keys.append(('VF', str(site.get('site_id') or '').strip()))
        elif operator == '3UK':
            keys.append(('3UK', str(site.get('site_pairing') or '').strip()))
        reference = re.fullmatch(r'(\d+)o2', str(site.get('site_ref2') or '').strip(), re.IGNORECASE)
        if reference:
            keys.append(('O2', reference.group(1)))
        for key in keys:
            if key[1]:
                lookup.setdefault(key, details)
    return lookup


def host_operator(host_network: Any) -> str:
    """The operator of the Master Grid of the host network of a serving cell (VF, 3UK or O2), or ''."""
    return HOST_OPERATORS.get(_identity(host_network), '')


def preview_columns() -> list[str]:
    """The columns of a Master Grid in its Preview: those kept, as the workbook names them."""
    return [headers[0] for headers in COLUMNS.values()]


def preview_frame(repository: Any, dataset_id: int, columns: Any, limit: int) -> Any:
    """The first sites of a Master Grid, read from ``master_grid_sites`` (it has no rows of its own in SQLite)."""
    frame = load_sites(repository, dataset_id).head(int(limit))
    frame.columns = preview_columns()
    wanted = [column for column in columns or [] if column in frame.columns]
    return frame[wanted] if wanted else frame
