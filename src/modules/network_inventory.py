"""Network inventory snapshots: every cell of every inventory dataset in one normalised, indexed table.

Each ready inventory dataset — a VFUK or 3UK Multivendor Mapping or a Network Inventory of any layout,
including Cell Configuration KMZ packages — is one *snapshot* of the network on its snapshot date. Its
cells are normalised once into ``inventory_cells`` (technology, owner Network, Host Network, vendor, site,
global cell identity, band, channel, PCI, position, azimuth, configuration and status), so Network Insights
and the Vendor mapping switch between snapshots, or combine them, without reading the source rows again.

The owner ``network`` of a cell (whose cell it is) and its ``host_network`` (whose RAN equipment carries it,
hence its vendor) are kept apart: an Operator's samples can be served by cells of other networks.
"""

from __future__ import annotations

import json
import math
import re
from datetime import date
from typing import Any, Iterable

import pandas as pd

from src.modules.cell_identity import lte_eci_series, nr_nci_series
from src.modules.column_names import column_identity

INVENTORY_DATASET_KINDS = ('mapping_vodafone', 'mapping_three', 'network_inventory')
INVENTORY_CELLS_TABLE = 'inventory_cells'
INVENTORY_SNAPSHOTS_TABLE = 'inventory_snapshots'
# Raise when the normalisation changes, so every snapshot is built again from its rows.
INVENTORY_CELLS_VERSION = 3
# The owner network of the cells of an inventory without a Network column.
DEFAULT_NETWORK_BY_KIND = {'mapping_vodafone': 'Vodafone', 'mapping_three': '3'}
NETWORK_FAMILY_LABELS = {'vodafone': 'Vodafone', 'three': '3', 'o2': 'O2', 'ee': 'EE'}

# Source headers of each normalised field, in order of preference.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    'technology': ('Technology', 'RAT'),
    'source_sheet': ('source_sheet',),
    'network': ('Network', 'MNO'),
    'host_network': ('Host Network', 'Host_Network'),
    'vendor': ('OP/ Vendor', 'OP_Vendor', 'Vendor', 'OEM', 'Manufacturer', 'Supplier'),
    'site_id': ('Site_ID', 'Site ID', 'MBNL_ID', 'Site'),
    'cell_name': ('Cell_name', 'Cell Name', 'CELL_NAME', 'EUtranCellFDD_id', 'H3G_Cell_Reference'),
    'enodeb_id': ('eNodeB ID', 'eNodeB_ID', 'eNB ID', 'eNBId', 'ENBID'),
    'gnodeb_id': ('gNodeB ID', 'gNodeB_ID', 'gNB ID', 'GNBID'),
    'cell_id': ('Cell ID', 'cellId', 'CellID'),
    'local_cell_id': ('Local Cell ID', 'Local_Cell_ID', 'LCID'),
    'gnodeb_length': ('gNodeB ID Length', 'gNodeB_ID_Length'),
    'global_id': ('ECI', 'NCI', 'GCID', 'CId___ECI', 'Cid__ECI', 'Global Cell ID', 'Global CI', 'Cell Identity',
                  'ECGI', 'NCGI', 'CGI'),
    'band': ('Band', 'Frequency Band'),
    'channel': ('Earfcn', 'EARFCN', 'earfcndl', 'ARFCN', 'earfcndl_u', 'arfcndl_u'),
    'pci': ('PCI', 'physicalLayerCellId', 'nRPCI'),
    'tac': ('TAC', 'tac', 'nRTAC'),
    'bandwidth': ('Bandwidth', 'Downlink_Bandwidth'),
    'bandwidth_khz': ('dlChannelBandwidth',),
    'latitude': ('Latitude', 'Lat', 'Site Latitude', 'Site_Latitude'),
    'longitude': ('Longitude', 'Long', 'Lon', 'Site Longitude', 'Site_Longitude'),
    'easting': ('Easting', 'Site Easting'),
    'northing': ('Northing', 'Site Northing'),
    'azimuth': ('Azimuth',),
    'beamwidth': ('Horizontal Beamwidth',),
    'height': ('Height', 'Antenna_Height'),
    'mech_tilt': ('Mech. Tilt', 'Mech_Tilt', 'Mechanical Downtilt (°)'),
    'elec_tilt': ('Elec.Tilt', 'Elec_Tilt', 'electricalAntennaTilt'),
    'site_type': ('Site Type', 'Site_Type'),
    'emocn': ('eMOCNScenario',),
    'region': ('Region', 'UK "Regional"'),
    'subregion': ('Subregion',),
    'cluster': ('Engineering Polygon', 'Cluster', 'Cluster Name', 'Regional Optimisation Polygon'),
    'city': ('Beacon2Town', 'City', 'Town', 'Major Town and Cities v3/BUA'),
    'urban_rural': ('Urban/Rural',),
    'performance_polygon': ('Performance Polygon',),
    'status': ('Evenflow Status', 'BIS/TTO stage'),
    'oss_status': ('OSS Status',),
    'admin_state': ('administrativeState',),
    'oper_state': ('operationalState',),
    'txrx_mode': ('TXRXMODE',),
    'tx_antennas': ('noOfUsedTxAntennas', 'noOfTxAntennas'),
}

# Stored columns and their SQLite types.
CELL_COLUMNS: tuple[tuple[str, str], ...] = (
    ('dataset_id', 'INTEGER NOT NULL'), ('source_row', 'INTEGER'), ('technology', 'TEXT'),
    ('network', 'TEXT'), ('network_family', 'TEXT'), ('host_network', 'TEXT'), ('host_family', 'TEXT'),
    ('vendor', 'TEXT'), ('site_id', 'TEXT'), ('cell_name', 'TEXT'), ('node_id', 'INTEGER'),
    ('cell_identity', 'TEXT'), ('band', 'TEXT'), ('channel', 'INTEGER'), ('pci', 'INTEGER'), ('tac', 'TEXT'),
    ('bandwidth_mhz', 'REAL'), ('latitude', 'REAL'), ('longitude', 'REAL'), ('azimuth', 'REAL'),
    ('beamwidth', 'REAL'), ('height', 'REAL'), ('mech_tilt', 'REAL'), ('elec_tilt', 'REAL'),
    ('site_type', 'TEXT'), ('emocn', 'TEXT'), ('region', 'TEXT'), ('subregion', 'TEXT'), ('cluster', 'TEXT'),
    ('city', 'TEXT'), ('urban_rural', 'TEXT'), ('performance_polygon', 'TEXT'), ('status', 'TEXT'),
    ('oss_status', 'TEXT'), ('admin_state', 'TEXT'), ('oper_state', 'TEXT'), ('txrx_mode', 'TEXT'),
    ('tx_antennas', 'INTEGER'),
)
CELL_COLUMN_NAMES = tuple(name for name, _type in CELL_COLUMNS)
TEXT_FIELDS = ('network', 'host_network', 'vendor', 'site_id', 'cell_name', 'band', 'tac', 'site_type', 'emocn',
               'region', 'subregion', 'cluster', 'city', 'urban_rural', 'performance_polygon', 'status',
               'oss_status', 'admin_state', 'oper_state', 'txrx_mode')
NUMERIC_FIELDS = ('latitude', 'longitude', 'azimuth', 'beamwidth', 'height', 'mech_tilt', 'elec_tilt')
# Placeholders that mean "no value" in the source inventories.
EMPTY_TEXT = {'', 'nan', 'none', 'null', '<na>', 'n/a', '#n/a', '-'}
SNAPSHOT_DATE_PATTERNS = (
    re.compile(r'(?<!\d)(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)'),
    re.compile(r'(?<!\d)(\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)'),
)


def network_family(value: object) -> str:
    """One identity for every spelling of a network: vodafone, three, o2, ee or the compacted name."""
    key = re.sub(r'[^a-z0-9]+', '', str(value or '').casefold())
    if not key:
        return ''
    if key.startswith(('vodafone', 'vf')):
        return 'vodafone'
    if key.startswith(('three', 'h3g', 'hutchison')) or re.match(r'^3(?![0-9])', key):
        return 'three'
    if key.startswith(('o2', 'telefonica', 'vmo2', 'virginmediao2')):
        return 'o2'
    if key in {'ee', 'eeuk', 'everythingeverywhere', 'btee'}:
        return 'ee'
    return key


def infer_snapshot_date(file_name: str) -> str | None:
    """The date in an inventory file name (``260917_…`` or ``…_2026-09-17…``), as ``YYYY-MM-DD``."""
    stem = re.sub(r'\.[^.]+$', '', str(file_name or ''))
    for index, pattern in enumerate(SNAPSHOT_DATE_PATTERNS):
        match = pattern.search(stem)
        if not match:
            continue
        year, month, day = match.groups()
        year = int(year) + (2000 if index else 0)
        try:
            return date(year, int(month), int(day)).isoformat()
        except ValueError:
            continue
    return None


def normalise_snapshot_date(value: object) -> str | None:
    """``YYYY-MM-DD`` of a snapshot date entered by a user, ``None`` when empty, ValueError when invalid."""
    text = str(value or '').strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise ValueError('Enter the snapshot date as YYYY-MM-DD.') from exc


def effective_snapshot_date(dataset: dict[str, Any] | Any) -> str:
    """The snapshot date of an inventory: chosen, else in its file name, else its upload date."""
    def field(name: str) -> Any:
        try:
            return dataset[name]
        except (KeyError, IndexError, TypeError):
            return None

    chosen = str(field('snapshot_date') or '').strip()
    if chosen:
        return chosen[:10]
    return infer_snapshot_date(str(field('file_name') or '')) or str(field('uploaded_at') or '')[:10]


def _column_lookup(columns: Iterable[object]) -> dict[str, list[str]]:
    """Every column of each identity: workbooks repeat a field in their sheets (Site_ID in 2G, Site ID in 4G)."""
    lookup: dict[str, list[str]] = {}
    for column in columns:
        lookup.setdefault(column_identity(column), []).append(str(column))
    return lookup


def resolve_fields(columns: Iterable[object]) -> dict[str, list[str]]:
    """The source columns of each normalised field, in order of preference (each row takes the first non-empty)."""
    lookup = _column_lookup(columns)
    resolved: dict[str, list[str]] = {}
    for field, aliases in FIELD_ALIASES.items():
        found = list(dict.fromkeys(column for alias in aliases for column in lookup.get(column_identity(alias), [])))
        if found:
            resolved[field] = found
    return resolved


def _clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ''
    text = str(value).strip()
    if text.casefold() in EMPTY_TEXT:
        return ''
    # Whole numbers stored as text (12.000) keep their integer spelling.
    return re.sub(r'\.0+$', '', text) if re.fullmatch(r'-?\d+\.0+', text) else text


def _text(series: pd.Series) -> pd.Series:
    values = series.astype(object)
    # Inventories repeat a few labels over hundreds of thousands of cells: clean each one once.
    cleaned = {value: _clean_text(value) for value in pd.unique(values)}
    return values.map(cleaned).astype(object)


def _first_text(frame: pd.DataFrame, columns: list[str] | None) -> pd.Series:
    result = pd.Series('', index=frame.index, dtype=object)
    for column in columns or []:
        result = result.where(result != '', _text(frame[column]))
    return result


def _number(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors='coerce').astype('float64')
    values = series.astype(object)
    parsed = {value: pd.to_numeric(str(value).replace(',', '.').strip(), errors='coerce') if value is not None else math.nan
              for value in pd.unique(values)}
    return values.map(parsed).astype('float64')


def _first_number(frame: pd.DataFrame, columns: list[str] | None) -> pd.Series:
    result = pd.Series(math.nan, index=frame.index, dtype='float64')
    for column in columns or []:
        result = result.where(result.notna(), _number(frame[column]))
    return result


def _technology(frame: pd.DataFrame, fields: dict[str, list[str]]) -> pd.Series:
    """LTE, NR, GSM or UMTS of each row: its Technology, its VFUK worksheet, its node type or its identity column."""
    explicit = _first_text(frame, fields.get('technology')).str.upper().map(
        {'LTE': 'LTE', '4G': 'LTE', 'E-UTRA': 'LTE', 'NR': 'NR', '5G': 'NR', 'GSM': 'GSM', '2G': 'GSM', 'UMTS': 'UMTS', '3G': 'UMTS'}
    ).fillna('')
    sheets = _first_text(frame, fields.get('source_sheet')).str.casefold().map(
        {'4g': 'LTE', '5g': 'NR', '2g': 'GSM', '3g': 'UMTS'}).fillna('')
    result = explicit.where(explicit != '', sheets)
    gnodeb = _first_number(frame, fields.get('gnodeb_id')).notna()
    enodeb = _first_number(frame, fields.get('enodeb_id')).notna()
    result = result.mask(result.eq('') & gnodeb, 'NR').mask(result.eq('') & enodeb, 'LTE')
    global_columns = [column_identity(column) for column in fields.get('global_id', [])]
    if not global_columns and fields.get('cell_id') and not (fields.get('enodeb_id') or fields.get('gnodeb_id')):
        global_columns = ['cellid']
    fallback = 'NR' if global_columns and global_columns[0] in {'nci', 'ncgi'} else 'LTE' if global_columns else ''
    return result.where(result != '', fallback)


def normalise_inventory(frame: pd.DataFrame, kind: str, dataset_operator: str | None = None) -> pd.DataFrame:
    """One normalised row per cell of an inventory frame (rows without a cell identity are dropped).

    ``frame`` keeps the source columns and a ``source_row`` column with the row id of each source row.
    """
    fields = resolve_fields(frame.columns)
    result = pd.DataFrame(index=frame.index)
    result['source_row'] = pd.to_numeric(frame['source_row'], errors='coerce') if 'source_row' in frame else range(1, len(frame) + 1)
    result['technology'] = _technology(frame, fields)
    for field in TEXT_FIELDS:
        result[field] = _first_text(frame, fields.get(field))
    default_network = str(dataset_operator or '').strip() or DEFAULT_NETWORK_BY_KIND.get(kind, '')
    result['network'] = result['network'].where(result['network'] != '', default_network)
    result['host_network'] = result['host_network'].where(result['host_network'] != '', result['network'])
    families = {value: network_family(value) for value in pd.unique(pd.concat([result['network'], result['host_network']]))}
    result['network_family'] = result['network'].map(families)
    result['host_family'] = result['host_network'].map(families)

    # Each part of the identity takes the first non-empty column of its field (a workbook's sheets repeat them).
    cell_id = _first_number(frame, fields.get('cell_id')) if fields.get('cell_id') else None
    local = _first_number(frame, fields.get('local_cell_id')) if fields.get('local_cell_id') else None
    enodeb = _first_number(frame, fields.get('enodeb_id'))
    gnodeb = _first_number(frame, fields.get('gnodeb_id'))
    length = _first_number(frame, fields.get('gnodeb_length')) if fields.get('gnodeb_length') else None
    lte = lte_eci_series(enodeb, cell_id, local)
    nr = nr_nci_series(gnodeb, cell_id, local, length)
    # The VFUK workbook's own CId___ECI keys Huawei and Nokia cells by their internal Local Cell ID, and its
    # GCID was calculated the same way before: its cells take only the identity of their node and Cell ID.
    has_nodes = bool(fields.get('enodeb_id') or fields.get('gnodeb_id'))
    node_based = kind == 'mapping_vodafone' and has_nodes
    # Without node columns, a Cell ID column is the global identity of the cell (as in the Vendor mapping).
    global_fields = [*fields.get('global_id', []), *([] if has_nodes else fields.get('cell_id', []))]
    global_id = pd.Series('', index=frame.index, dtype=object) if node_based else _first_text(
        frame, global_fields).map(lambda value: value if re.fullmatch(r'\d+', value) else '')
    identity = pd.Series('', index=frame.index, dtype=object)
    is_lte, is_nr = result['technology'].eq('LTE'), result['technology'].eq('NR')
    identity = identity.mask(is_lte & lte.notna(), lte.astype(str))
    identity = identity.mask(is_nr & nr.notna(), nr.astype(str))
    identity = identity.where(identity != '', global_id)
    result['cell_identity'] = identity
    nodes = _first_number(frame, fields.get('enodeb_id')).where(is_lte)
    nodes = nodes.where(nodes.notna(), _first_number(frame, fields.get('gnodeb_id')).where(is_nr))
    result['node_id'] = nodes.where(nodes.notna() & nodes.ge(0)).astype('Int64')

    result['channel'] = _first_number(frame, fields.get('channel')).where(lambda values: values.ge(0)).round().astype('Int64')
    result['pci'] = _first_number(frame, fields.get('pci')).where(lambda values: values.between(0, 1007)).round().astype('Int64')
    bandwidth = _first_number(frame, fields.get('bandwidth'))
    bandwidth = bandwidth.where(bandwidth.notna(), _first_number(frame, fields.get('bandwidth_khz')) / 1000)
    result['bandwidth_mhz'] = bandwidth.where(bandwidth.between(0.1, 400))
    for field in NUMERIC_FIELDS:
        result[field] = _first_number(frame, fields.get(field))
    result['tx_antennas'] = _first_number(frame, fields.get('tx_antennas')).where(lambda values: values.between(1, 256)).round().astype('Int64')
    invalid = ~(result['latitude'].between(-90, 90) & result['longitude'].between(-180, 180)) | (
        result['latitude'].abs().lt(1e-6) & result['longitude'].abs().lt(1e-6))
    result.loc[invalid, ['latitude', 'longitude']] = math.nan
    if fields.get('easting') and fields.get('northing'):
        # Sites without WGS84 coordinates, or with coordinates rounded to 3 decimals (about 100 m, as in the
        # Cell Configuration KMZ descriptions), take them from their British National Grid position in metres.
        east, north = _first_number(frame, fields['easting']), _first_number(frame, fields['northing'])
        rounded = ((result['latitude'] * 1000).sub((result['latitude'] * 1000).round()).abs().lt(1e-6)
                   & (result['longitude'] * 1000).sub((result['longitude'] * 1000).round()).abs().lt(1e-6))
        missing = (result['latitude'].isna() | rounded) & east.gt(0) & north.gt(0)
        if missing.any():
            from pyproj import Transformer
            transformer = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
            lon, lat = transformer.transform(east[missing].to_numpy(), north[missing].to_numpy())
            result.loc[missing, 'longitude'], result.loc[missing, 'latitude'] = lon, lat
    for field in ('azimuth',):
        result[field] = result[field].where(result[field].between(0, 360))
    result['beamwidth'] = result['beamwidth'].where(result['beamwidth'].between(1, 360))
    result['height'] = result['height'].where(result['height'].between(0, 500))
    keep = result['cell_identity'].ne('') & result['technology'].isin({'LTE', 'NR', 'GSM', 'UMTS'})
    return result.loc[keep, [name for name in CELL_COLUMN_NAMES if name != 'dataset_id']].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def ensure_inventory_schema(connection: Any) -> None:
    columns = ', '.join(f'{name} {kind}' for name, kind in CELL_COLUMNS)
    connection.execute(f'CREATE TABLE IF NOT EXISTS {INVENTORY_CELLS_TABLE} ({columns})')
    connection.execute(f'CREATE INDEX IF NOT EXISTS idx_inventory_cells_snapshot ON {INVENTORY_CELLS_TABLE} (dataset_id, network_family, technology)')
    connection.execute(f'CREATE INDEX IF NOT EXISTS idx_inventory_cells_identity ON {INVENTORY_CELLS_TABLE} (cell_identity)')
    connection.execute(f'CREATE INDEX IF NOT EXISTS idx_inventory_cells_site ON {INVENTORY_CELLS_TABLE} (dataset_id, site_id)')
    connection.execute(
        f'CREATE TABLE IF NOT EXISTS {INVENTORY_SNAPSHOTS_TABLE} ('
        'dataset_id INTEGER PRIMARY KEY, version INTEGER NOT NULL, revision TEXT NOT NULL, cells INTEGER NOT NULL, '
        "sites INTEGER NOT NULL, summary_json TEXT NOT NULL DEFAULT '{}', built_at TEXT NOT NULL)"
    )


def dataset_revision(dataset: Any) -> str:
    def field(name: str) -> str:
        try:
            return str(dataset[name] or '')
        except (KeyError, IndexError, TypeError):
            return ''
    return '|'.join((field('processed_at'), field('row_count'), field('dataset_operator'), field('stored_path')))


def _read_source_rows(repository: Any, dataset_id: int) -> pd.DataFrame:
    """The source rows of an inventory dataset, only the columns the normalisation reads."""
    columns = repository.list_dataset_row_columns(dataset_id)
    fields = resolve_fields(columns)
    selected = list(dict.fromkeys(column for names in fields.values() for column in names))
    if not selected:
        return pd.DataFrame()
    quote = repository._quote_identifier
    table = quote(repository.dataset_rows_table_name(dataset_id))
    with repository.connection() as connection:
        return pd.read_sql_query(
            f"SELECT rowid AS source_row, {', '.join(quote(column) for column in selected)} FROM {table}", connection)


def _summary(cells: pd.DataFrame) -> dict[str, Any]:
    """Cells and sites of a snapshot per owner network family and technology."""
    families: dict[str, Any] = {}
    for family, part in cells.groupby('network_family', sort=True):
        families[str(family)] = {
            'networks': sorted({str(value) for value in part['network'] if str(value)}),
            'cells': int(len(part)), 'sites': int(part['site_id'].replace('', pd.NA).dropna().nunique()),
            'technologies': {str(key): int(value) for key, value in part['technology'].value_counts().items()},
            'located': int(part['latitude'].notna().sum()),
        }
    return {'families': families, 'technologies': {str(key): int(value) for key, value in cells['technology'].value_counts().items()}}


def build_inventory_cells(repository: Any, dataset: Any) -> dict[str, Any]:
    """Normalise one inventory dataset into ``inventory_cells`` (replacing its previous cells)."""
    dataset_id = int(dataset['id'])
    kind = str(dataset['dataset_kind'] or '')
    try:
        operator = str(dataset['dataset_operator'] or '').strip()
    except (KeyError, IndexError):
        operator = ''
    source = _read_source_rows(repository, dataset_id)
    cells = normalise_inventory(source, kind, operator) if not source.empty else pd.DataFrame(columns=CELL_COLUMN_NAMES[1:])
    cells.insert(0, 'dataset_id', dataset_id)
    summary = _summary(cells)
    sites = int(cells['site_id'].replace('', pd.NA).dropna().nunique()) if len(cells) else 0
    records = cells.astype(object).where(cells.notna(), None)
    placeholders = ', '.join('?' for _ in CELL_COLUMN_NAMES)
    with repository.connection() as connection:
        connection.execute('BEGIN IMMEDIATE')
        ensure_inventory_schema(connection)
        connection.execute(f'DELETE FROM {INVENTORY_CELLS_TABLE} WHERE dataset_id = ?', (dataset_id,))
        connection.executemany(
            f"INSERT INTO {INVENTORY_CELLS_TABLE} ({', '.join(CELL_COLUMN_NAMES)}) VALUES ({placeholders})",
            records[list(CELL_COLUMN_NAMES)].itertuples(index=False, name=None),
        )
        connection.execute(
            f'INSERT OR REPLACE INTO {INVENTORY_SNAPSHOTS_TABLE} (dataset_id, version, revision, cells, sites, summary_json, built_at) '
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (dataset_id, INVENTORY_CELLS_VERSION, dataset_revision(dataset), int(len(cells)), sites, json.dumps(summary)),
        )
    return {'dataset_id': dataset_id, 'cells': int(len(cells)), 'sites': sites, 'summary': summary}


def delete_inventory_cells(repository: Any, dataset_ids: Iterable[int] | None = None) -> int:
    """Remove the cells of the given datasets, or of every dataset that no longer exists."""
    with repository.connection() as connection:
        ensure_inventory_schema(connection)
        if dataset_ids is None:
            stale = [int(row[0]) for row in connection.execute(
                f'SELECT dataset_id FROM {INVENTORY_SNAPSHOTS_TABLE} WHERE dataset_id NOT IN (SELECT id FROM datasets)')]
        else:
            stale = [int(value) for value in dataset_ids]
        for dataset_id in stale:
            connection.execute(f'DELETE FROM {INVENTORY_CELLS_TABLE} WHERE dataset_id = ?', (dataset_id,))
            connection.execute(f'DELETE FROM {INVENTORY_SNAPSHOTS_TABLE} WHERE dataset_id = ?', (dataset_id,))
    return len(stale)


def inventory_datasets(repository: Any) -> list[Any]:
    """The ready inventory datasets of the workspace, newest first."""
    return [row for row in repository.list_datasets()
            if row['status'] == 'ready' and str(row['dataset_kind'] or '') in INVENTORY_DATASET_KINDS]


def ensure_inventory_cells(repository: Any, progress: Any = None) -> list[dict[str, Any]]:
    """Build the cells of every ready inventory whose snapshot is missing or outdated; return the snapshots."""
    datasets = inventory_datasets(repository)
    with repository.connection() as connection:
        ensure_inventory_schema(connection)
        built = {int(row['dataset_id']): (int(row['version']), str(row['revision']))
                 for row in connection.execute(f'SELECT dataset_id, version, revision FROM {INVENTORY_SNAPSHOTS_TABLE}')}
    stale_ids = set(built) - {int(row['id']) for row in datasets}
    if stale_ids:
        delete_inventory_cells(repository, stale_ids)
    for dataset in datasets:
        if built.get(int(dataset['id'])) != (INVENTORY_CELLS_VERSION, dataset_revision(dataset)):
            if progress:
                progress(dataset)
            build_inventory_cells(repository, dataset)
    return list_inventory_snapshots(repository, datasets)


def list_inventory_snapshots(repository: Any, datasets: list[Any] | None = None) -> list[dict[str, Any]]:
    """Every built snapshot with its date, cells, sites and owner networks, newest snapshot date first."""
    datasets = inventory_datasets(repository) if datasets is None else datasets
    with repository.connection() as connection:
        ensure_inventory_schema(connection)
        rows = {int(row['dataset_id']): row for row in connection.execute(f'SELECT * FROM {INVENTORY_SNAPSHOTS_TABLE}')}
    snapshots = []
    for dataset in datasets:
        row = rows.get(int(dataset['id']))
        if row is None:
            continue
        summary = json.loads(row['summary_json'] or '{}')
        snapshots.append({
            'dataset_id': int(dataset['id']), 'file_name': str(dataset['file_name']),
            'kind': str(dataset['dataset_kind']), 'snapshot_date': effective_snapshot_date(dataset),
            'cells': int(row['cells']), 'sites': int(row['sites']),
            'families': summary.get('families', {}), 'technologies': summary.get('technologies', {}),
        })
    return sorted(snapshots, key=lambda item: (item['snapshot_date'], item['dataset_id']), reverse=True)
