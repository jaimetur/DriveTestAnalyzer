"""Network Insights on inventory snapshots: deployment, host networks, deployed spectrum, density and serving cells.

Every function reads the normalised ``inventory_cells`` of the selected snapshots (see ``network_inventory``) and,
for the serving-cell analyses, the normalised CDR samples of Network Insights. They are free of web-framework
dependencies so they can be tested directly.
"""

from __future__ import annotations

import math
import re
from collections import OrderedDict
from threading import Lock
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from src.modules.network_inventory import (
    INVENTORY_CELLS_TABLE, NETWORK_FAMILY_LABELS, dataset_revision, inventory_datasets, list_inventory_snapshots,
)
from src.modules.serving_cells import serving_families

# Inventory band labels (LTE800, NR3400…) to their 3GPP band and downlink frequency.
INVENTORY_BANDS: dict[str, tuple[str, int]] = {
    'LTE700': ('B28', 700), 'LTE800': ('B20', 800), 'LTE900': ('B8', 900), 'LTE1400': ('B32', 1500),
    'LTE1500': ('B32', 1500), 'LTE1800': ('B3', 1800), 'LTE2100': ('B1', 2100), 'LTE2300': ('B40', 2300),
    'LTE2600': ('B7', 2600), 'NR700': ('n28', 700), 'NR800': ('n20', 800), 'NR900': ('n8', 900),
    'NR1800': ('n3', 1800), 'NR2100': ('n1', 2100), 'NR2300': ('n40', 2300), 'NR2600': ('n7', 2600),
    'NR3400': ('n78', 3500), 'NR3500': ('n78', 3500), 'NR3600': ('n78', 3500), 'NR3700': ('n78', 3500),
    'N78': ('n78', 3500), 'N1': ('n1', 2100), 'N28': ('n28', 700), 'N8': ('n8', 900),
}
STATUS_IN_SERVICE = {'', 'in service', 'active', 'on air', 'live', 'unison created'}
DEPLOYMENT_DIMENSIONS: dict[str, str] = {
    'network': 'Owner Network', 'host_network': 'Host Network', 'vendor': 'RAN Vendor', 'technology': 'Technology',
    'band': 'Band', 'emocn': 'eMOCN Scenario', 'site_type': 'Site Type', 'region': 'Region', 'subregion': 'Subregion',
    'cluster': 'Cluster', 'city': 'City', 'urban_rural': 'Urban/Rural', 'performance_polygon': 'Performance Polygon',
    'status': 'Status', 'txrx_mode': 'MIMO (TX/RX)',
}
CELL_FIELDS = ('dataset_id', 'technology', 'network', 'network_family', 'host_network', 'host_family', 'vendor', 'site_id',
               'cell_name', 'node_id', 'cell_identity', 'band', 'channel', 'pci', 'bandwidth_mhz', 'latitude', 'longitude',
               'azimuth', 'beamwidth', 'height', 'site_type', 'emocn', 'region', 'subregion', 'cluster', 'city', 'urban_rural',
               'performance_polygon', 'status', 'oss_status', 'admin_state', 'oper_state', 'txrx_mode', 'tx_antennas')
# Columns derived once per snapshot by load_cells.
DERIVED_CELL_FIELDS = ('band_3gpp', 'in_service', 'site_key', 'is_lte', 'is_nr', 'state', 'state_known', 'mimo_tx')
# The states flagged around the weak areas, most severe first: cells in service that their administrative, OSS or
# operational state shows Locked, Halted or Disabled, and cells not on air yet (In progress or Planned).
CELL_STATES = ('Locked', 'Halted', 'Disabled', 'In progress', 'Planned')
OUTAGE_STATES = ('Locked', 'Halted', 'Disabled')
STATUS_IN_PROGRESS = {'in progress'}
STATUS_PLANNED = {'planned', 'proposed'}
# How the NR cell of an NSA sample was found from its NR PCI and band/SSB frequency.
NR_LEG_METHODS = {'anchor_site': 'On the anchor site', 'only_candidate': 'Only candidate nearby', 'nearest': 'Nearest of several'}
RANK_COLOURS = ('#F08A24', '#F2C230', '#8BC34A', '#2E8B57')
_cell_cache: OrderedDict[tuple, pd.DataFrame] = OrderedDict()
_cell_cache_lock = Lock()


def family_label(family: str, operator_labels: dict[str, str] | None = None) -> str:
    """The Operator a network family is shown as: its Operator Maps name, else Vodafone, 3, O2 or EE."""
    if operator_labels and family in operator_labels:
        return operator_labels[family]
    return NETWORK_FAMILY_LABELS.get(family, family or 'No network')


def nr_arfcn_frequency(arfcn: Any) -> float | None:
    """Downlink frequency (MHz) of an NR-ARFCN (TS 38.104 global raster)."""
    try:
        value = int(float(arfcn))
    except (TypeError, ValueError):
        return None
    if 0 <= value < 600000:
        return value * 0.005
    if 600000 <= value < 2016667:
        return 3000 + (value - 600000) * 0.015
    if 2016667 <= value <= 3279165:
        return 24250.08 + (value - 2016667) * 0.06
    return None


# Downlink EARFCN → frequency per LTE band: (lowest EARFCN, highest EARFCN, lowest frequency MHz) (TS 36.101).
LTE_DOWNLINK_RASTER = {
    'B1': (0, 599, 2110.0), 'B3': (1200, 1949, 1805.0), 'B7': (2750, 3449, 2620.0), 'B8': (3450, 3799, 925.0),
    'B20': (6150, 6449, 791.0), 'B28': (9210, 9659, 758.0), 'B32': (9920, 10359, 1452.0), 'B38': (37750, 38249, 2570.0),
    'B40': (38650, 39649, 2300.0), 'B41': (39650, 41589, 2496.0), 'B42': (41590, 43589, 3400.0), 'B43': (43590, 45589, 3600.0),
}


def channel_frequency(channel: Any, technology: Any) -> float | None:
    """Downlink centre frequency (MHz) of an LTE EARFCN or an NR-ARFCN; ``None`` for placeholders such as 0."""
    try:
        value = int(float(channel))
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    if str(technology).upper() == 'NR':
        return nr_arfcn_frequency(value)
    for low, high, frequency in LTE_DOWNLINK_RASTER.values():
        if low <= value <= high:
            return frequency + 0.1 * (value - low)
    return None


def _occupied_mhz(intervals: list[tuple[float, float]]) -> float:
    """Total width of the union of frequency intervals: overlapping carriers count once."""
    total, current_start, current_end = 0.0, None, None
    for start, end in sorted(intervals):
        if current_end is None or start > current_end:
            if current_end is not None:
                total += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        total += current_end - current_start
    return total


def cell_band(label: Any, technology: Any) -> str:
    """The 3GPP band (B3, n78) of an inventory cell from its band label."""
    text = re.sub(r'\s+', '', str(label or '')).upper()
    if text in INVENTORY_BANDS:
        return INVENTORY_BANDS[text][0]
    match = re.fullmatch(r'(?:B|BAND)?(\d{1,3})', text)
    if match:
        return ('n' if str(technology).upper() == 'NR' else 'B') + match.group(1)
    return str(label or '')


def snapshot_choice(snapshots: list[dict[str, Any]], choice: Any = '') -> dict[str, int]:
    """Network family → snapshot dataset ID: the chosen snapshot for the networks it covers, else the newest one."""
    chosen = None
    try:
        chosen = int(choice) if str(choice or '').strip() else None
    except (TypeError, ValueError):
        chosen = None
    selection: dict[str, int] = {}
    ordered = sorted(snapshots, key=lambda item: (item['snapshot_date'], item['dataset_id']), reverse=True)
    if chosen is not None:
        ordered = sorted(ordered, key=lambda item: item['dataset_id'] != chosen)
    for snapshot in ordered:
        for family, details in snapshot['families'].items():
            if family and details.get('cells') and family not in selection:
                selection[family] = int(snapshot['dataset_id'])
    return selection


def cell_states(cells: pd.DataFrame) -> pd.Series:
    """The state flagged for each cell: Locked, Halted or Disabled for a cell in service whose administrative, OSS or
    operational state says so, In progress or Planned for a cell not on air yet, else ''."""
    def upper(field: str) -> pd.Series:
        return cells[field].fillna('').astype(str).str.strip().str.upper() if field in cells else pd.Series('', index=cells.index)

    admin, oss, oper = upper('admin_state'), upper('oss_status'), upper('oper_state')
    status = cells['status'].fillna('').astype(str).str.strip().str.casefold()
    in_service = status.isin(STATUS_IN_SERVICE)
    # From the least to the most severe, so the most severe state of a cell wins.
    states = pd.Series('', index=cells.index, dtype=object)
    states = states.mask(status.isin(STATUS_PLANNED), 'Planned')
    states = states.mask(status.isin(STATUS_IN_PROGRESS), 'In progress')
    states = states.mask(in_service & (oper.eq('DISABLED') | oss.eq('DISABLED')), 'Disabled')
    states = states.mask(in_service & oss.eq('HALTED'), 'Halted')
    return states.mask(in_service & (admin.eq('LOCKED') | oss.eq('LOCKED')), 'Locked')


def mimo_tx(txrx_mode: pd.Series, tx_antennas: pd.Series) -> pd.Series:
    """TX antennas of each cell: the T of its TXRX mode (4T4R → 4, Huawei cells), else its used TX antennas (Ericsson)."""
    modes = txrx_mode.fillna('').astype(str)
    parsed = {}
    for value in pd.unique(modes):
        match = re.match(r'\s*(\d+)\s*T', value, re.IGNORECASE)
        parsed[value] = float(match.group(1)) if match else math.nan
    tx = modes.map(parsed).astype(float)
    tx = tx.where(tx.notna(), pd.to_numeric(tx_antennas, errors='coerce').astype(float))
    return tx.where(tx > 0)


def load_cells(repository: Any, selection: dict[str, int]) -> pd.DataFrame:
    """The cells of each selected (family, snapshot), cached in memory per snapshot revision."""
    if not selection:
        return pd.DataFrame(columns=[*CELL_FIELDS, *DERIVED_CELL_FIELDS]).astype(
            {'in_service': bool, 'is_lte': bool, 'is_nr': bool, 'state_known': bool, 'mimo_tx': float})
    revisions = {int(row['id']): dataset_revision(row) for row in inventory_datasets(repository)}
    key = (str(repository.db_path), tuple(sorted((family, dataset_id, revisions.get(dataset_id, '')) for family, dataset_id in selection.items())))
    with _cell_cache_lock:
        cached = _cell_cache.get(key)
        if cached is not None:
            _cell_cache.move_to_end(key)
            return cached
    clauses, parameters = [], []
    for family, dataset_id in sorted(selection.items()):
        clauses.append('(dataset_id = ? AND network_family = ?)')
        parameters.extend([dataset_id, family])
    with repository.connection() as connection:
        cells = pd.read_sql_query(
            f"SELECT {', '.join(CELL_FIELDS)} FROM {INVENTORY_CELLS_TABLE} WHERE {' OR '.join(clauses)}", connection, params=parameters)
    for field in ('technology', 'network', 'network_family', 'host_network', 'host_family', 'vendor', 'site_id', 'band', 'site_type',
                  'emocn', 'region', 'subregion', 'cluster', 'city', 'urban_rural', 'performance_polygon', 'status', 'txrx_mode'):
        cells[field] = cells[field].fillna('').astype(str)
    bands = {pair: cell_band(*pair) for pair in set(zip(cells['band'], cells['technology'], strict=True))}
    cells['band_3gpp'] = [bands[pair] for pair in zip(cells['band'], cells['technology'], strict=True)]
    cells['in_service'] = cells['status'].str.strip().str.casefold().isin(STATUS_IN_SERVICE)
    # Derived once per snapshot: every grouping counts sites by this key and LTE/NR cells by these flags.
    cells['site_key'] = _site_key(cells)
    cells['is_lte'] = cells['technology'].eq('LTE')
    cells['is_nr'] = cells['technology'].eq('NR')
    cells['state'] = cell_states(cells)
    # Only some inventories (the Ericsson cells of the Cell Configuration packages) carry these states.
    cells['state_known'] = (cells['admin_state'].fillna('').astype(str).str.strip().ne('')
                            | cells['oper_state'].fillna('').astype(str).str.strip().ne(''))
    cells['mimo_tx'] = mimo_tx(cells['txrx_mode'], cells['tx_antennas'])
    with _cell_cache_lock:
        _cell_cache[key] = cells
        while len(_cell_cache) > 4:
            _cell_cache.popitem(last=False)
    return cells


def snapshot_overview(repository: Any, choice: Any = '', operator_labels: dict[str, str] | None = None) -> dict[str, Any]:
    """The snapshots of the workspace and the one used for each network."""
    snapshots = list_inventory_snapshots(repository)
    selection = snapshot_choice(snapshots, choice)
    by_id = {item['dataset_id']: item for item in snapshots}
    networks = []
    for family, dataset_id in sorted(selection.items(), key=lambda item: family_label(item[0], operator_labels).casefold()):
        snapshot = by_id[dataset_id]
        details = snapshot['families'].get(family, {})
        networks.append({
            'family': family, 'operator': family_label(family, operator_labels), 'networks': details.get('networks', []),
            'dataset_id': dataset_id, 'file_name': snapshot['file_name'], 'snapshot_date': snapshot['snapshot_date'],
            'cells': details.get('cells', 0), 'sites': details.get('sites', 0), 'technologies': details.get('technologies', {}),
        })
    return {'snapshots': [{key: value for key, value in item.items() if key != 'families'} | {
        'networks': sorted(family_label(family, operator_labels) for family in item['families'] if family)} for item in snapshots],
        'selection': networks, 'choice': str(choice or '')}


def _filtered(cells: pd.DataFrame, in_service_only: bool, technology: str = '') -> pd.DataFrame:
    frame = cells
    if in_service_only:
        frame = frame.loc[frame['in_service']]
    if technology in {'LTE', 'NR'}:
        frame = frame.loc[frame['technology'] == technology]
    return frame


def _site_key(frame: pd.DataFrame) -> pd.Series:
    return frame['network_family'] + ':' + frame['site_id'].where(frame['site_id'] != '', 'cell:' + frame['cell_identity'].astype(str))


def deployment_tables(cells: pd.DataFrame, group: str, in_service_only: bool = True, technology: str = '',
                      operator_labels: dict[str, str] | None = None, value_names: Callable[[str, pd.Series], pd.Series] | None = None) -> list[dict[str, Any]]:
    """Sites and cells of each owner network grouped by one dimension (Host Network, Vendor, Band…)."""
    frame = _filtered(cells, in_service_only, technology)
    if frame.empty:
        return []
    column = 'band_3gpp' if group == 'band' else group
    values = frame[column].astype(str) if column in frame else pd.Series('', index=frame.index)
    if value_names is not None:
        values = value_names(group, frame)
    frame = frame[['network_family', 'site_key', 'is_lte', 'is_nr']].assign(group_value=values.replace('', 'Not set').to_numpy())
    counts = frame.groupby(['network_family', 'group_value'], sort=False).agg(
        sites=('site_key', 'nunique'), cells=('site_key', 'size'), lte_cells=('is_lte', 'sum'), nr_cells=('is_nr', 'sum')).reset_index()
    totals = frame.groupby('network_family', sort=False).agg(
        sites=('site_key', 'nunique'), cells=('site_key', 'size'), lte_cells=('is_lte', 'sum'), nr_cells=('is_nr', 'sum'))
    tables = []
    for family, part in counts.groupby('network_family', sort=False):
        part = part.sort_values(['sites', 'group_value'], ascending=[False, True])
        total = totals.loc[family]
        tables.append({
            'family': family, 'operator': family_label(family, operator_labels), 'group': group,
            'group_label': DEPLOYMENT_DIMENSIONS.get(group, group),
            'rows': [{'group': str(row.group_value), 'sites': int(row.sites), 'cells': int(row.cells),
                      'lte_cells': int(row.lte_cells), 'nr_cells': int(row.nr_cells)} for row in part.itertuples()],
            'totals': {'sites': int(total['sites']), 'cells': int(total['cells']),
                       'lte_cells': int(total['lte_cells']), 'nr_cells': int(total['nr_cells'])},
        })
    return sorted(tables, key=lambda table: table['operator'].casefold())


def host_matrix(cells: pd.DataFrame, in_service_only: bool = True, operator_labels: dict[str, str] | None = None) -> dict[str, Any]:
    """Cells and sites of each owner network carried by each host network (shared sites, MORAN and eMOCN)."""
    frame = _filtered(cells, in_service_only)
    if frame.empty:
        return {'owners': [], 'hosts': [], 'cells': {}, 'sites': {}}
    names = {value: family_label(value, operator_labels) for value in pd.unique(pd.concat([frame['network_family'], frame['host_family']]))}
    frame = frame[['network_family', 'host_family', 'site_key', 'cell_identity']].assign(
        owner=frame['network_family'].map(names), host=frame['host_family'].map(names))
    grouped = frame.groupby(['owner', 'host']).agg(cells=('cell_identity', 'size'), sites=('site_key', 'nunique')).reset_index()
    return {
        'owners': sorted(grouped['owner'].unique(), key=str.casefold), 'hosts': sorted(grouped['host'].unique(), key=str.casefold),
        'cells': {f'{row.owner}|{row.host}': int(row.cells) for row in grouped.itertuples()},
        'sites': {f'{row.owner}|{row.host}': int(row.sites) for row in grouped.itertuples()},
    }


def deployed_spectrum(cells: pd.DataFrame, operator_labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Per owner network and band: in-service sites and cells, carriers (distinct channels) and deployed MHz."""
    frame = _filtered(cells, True)
    frame = frame.loc[frame['band_3gpp'] != '']
    if frame.empty:
        return []
    frame = frame.assign(_site=frame['site_key'])
    rows = []
    for (family, technology, band), part in frame.groupby(['network_family', 'technology', 'band_3gpp'], sort=True):
        # A carrier is a distinct channel (0 is a placeholder); its bandwidth is the most frequent of its cells.
        located = part.loc[part['channel'].notna() & part['channel'].astype(float).gt(0)]
        carriers = located.groupby('channel')['bandwidth_mhz'].agg(
            lambda values: values.dropna().mode().iloc[0] if values.notna().any() else math.nan)
        bandwidths = part['bandwidth_mhz'].dropna()
        # The deployed MHz are the union of the carriers' frequency ranges: near-identical channels of one carrier
        # (several NR-ARFCN rasters) and overlapping carriers count once.
        intervals = []
        for channel, bandwidth in carriers.items():
            frequency = channel_frequency(channel, technology)
            if frequency is not None and bandwidth and not math.isnan(bandwidth):
                intervals.append((frequency - bandwidth / 2, frequency + bandwidth / 2))
        rows.append({
            'family': family, 'operator': family_label(family, operator_labels), 'technology': technology, 'band': band,
            'sites': int(part['_site'].nunique()), 'cells': int(len(part)), 'carriers': int(len(carriers)),
            'channels': [int(value) for value in carriers.index[:6]],
            'typical_bandwidth_mhz': float(bandwidths.mode().iloc[0]) if len(bandwidths) else None,
            'deployed_mhz': round(_occupied_mhz(intervals), 1) if intervals else None,
        })
    return sorted(rows, key=lambda row: (row['operator'].casefold(), row['technology'], _band_order(row['band'])))


def _band_order(band: str) -> tuple[int, int]:
    match = re.search(r'(\d+)', band)
    return (0 if band.startswith('B') else 1, int(match.group(1)) if match else 0)


def site_positions(cells: pd.DataFrame, in_service_only: bool = True) -> pd.DataFrame:
    """One row per site of each owner network: its median position, technologies, bands, vendor and host."""
    frame = _filtered(cells, in_service_only)
    frame = frame.loc[frame['latitude'].notna() & frame['longitude'].notna()]
    if frame.empty:
        return pd.DataFrame(columns=['site_key', 'family', 'site', 'latitude', 'longitude', 'has_nr', 'cells', 'vendor', 'host_family', 'bands'])
    grouped = frame.groupby('site_key', sort=False).agg(
        family=('network_family', 'first'), site=('site_id', 'first'), latitude=('latitude', 'median'),
        longitude=('longitude', 'median'), has_nr=('is_nr', 'max'), cells=('cell_identity', 'size'),
        vendor=('vendor', 'first'), host_family=('host_family', 'first'), region=('region', 'first'), cluster=('cluster', 'first'),
    )
    # The bands of each site, joined once per distinct (site, band) instead of per cell.
    bands = frame.loc[frame['band_3gpp'] != '', ['site_key', 'band_3gpp']].drop_duplicates()
    bands = bands.assign(order=bands['band_3gpp'].map({band: _band_order(band) for band in pd.unique(bands['band_3gpp'])}))
    joined = bands.sort_values('order').groupby('site_key', sort=False)['band_3gpp'].agg(' '.join)
    grouped['bands'] = joined.reindex(grouped.index).fillna('')
    grouped['has_nr'] = grouped['has_nr'].astype(bool)
    return grouped.reset_index()


def _metres(longitude: np.ndarray, latitude: np.ndarray, reference_latitude: float) -> np.ndarray:
    scale = 111_320.0
    return np.c_[np.asarray(longitude, dtype=float) * scale * math.cos(math.radians(reference_latitude)),
                 np.asarray(latitude, dtype=float) * scale]


def nearest_site_distances(sites: pd.DataFrame) -> pd.Series:
    """Distance (km) from each site to the nearest other site of its own network (the inter-site distance)."""
    from shapely import STRtree, points

    result = pd.Series(math.nan, index=sites.index, dtype='float64')
    for _family, part in sites.groupby('family'):
        if len(part) < 2:
            continue
        coordinates = _metres(part['longitude'].to_numpy(), part['latitude'].to_numpy(), float(part['latitude'].median()))
        geometries = points(coordinates)
        tree = STRtree(geometries)
        (_source, target), distances = tree.query_nearest(geometries, return_distance=True, exclusive=True, all_matches=False)
        nearest = pd.Series(distances / 1000.0, index=part.index[_source])
        result.loc[nearest.index] = nearest.groupby(level=0).min()
    return result


def density_rows(sites: pd.DataFrame, dimension: str, names: pd.Series, areas: dict[str, float],
                 operator_labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Sites, area, sites per km² and median inter-site distance of each owner network per area."""
    if sites.empty:
        return []
    frame = sites.assign(_area=names.reindex(sites.index).fillna('').replace('', 'Not set'), _isd=nearest_site_distances(sites))
    rows = []
    for (family, area), part in frame.groupby(['family', '_area'], sort=True):
        size = areas.get(area)
        rows.append({
            'family': family, 'operator': family_label(family, operator_labels), 'dimension': dimension, 'area': area,
            'sites': int(len(part)), 'nr_sites': int(part['has_nr'].sum()), 'area_km2': round(size, 1) if size else None,
            'sites_per_km2': round(len(part) / size, 3) if size else None,
            'median_isd_km': round(float(part['_isd'].median()), 3) if part['_isd'].notna().any() else None,
            'p90_isd_km': round(float(part['_isd'].quantile(.9)), 3) if part['_isd'].notna().any() else None,
        })
    return sorted(rows, key=lambda row: (row['area'] == 'Not set', row['area'].casefold(), row['operator'].casefold()))


def inventory_quality(cells: pd.DataFrame, operator_labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """What each network's cells lack: position, azimuth, band, vendor, site, or service."""
    rows = []
    for family, part in cells.groupby('network_family', sort=True):
        total = len(part)
        duplicates = int(part.duplicated(['technology', 'cell_identity']).sum())
        rows.append({
            'family': family, 'operator': family_label(family, operator_labels), 'cells': int(total),
            'without_position': int(part['latitude'].isna().sum()), 'without_azimuth': int(part['azimuth'].isna().sum()),
            'without_band': int((part['band'] == '').sum()), 'without_vendor': int((part['vendor'] == '').sum()),
            'without_site': int((part['site_id'] == '').sum()), 'duplicate_identities': duplicates,
            'not_in_service': int((~part['in_service']).sum()),
            'locked_or_disabled': int(part['admin_state'].fillna('').str.upper().eq('LOCKED').sum()
                                      + part['oper_state'].fillna('').str.upper().eq('DISABLED').sum()),
            'statuses': {str(key or 'Not set'): int(value) for key, value in part['status'].value_counts().head(8).items()},
        })
    return sorted(rows, key=lambda row: row['operator'].casefold())


# ---------------------------------------------------------------------------
# Serving cells of the CDR samples
# ---------------------------------------------------------------------------
def _haversine_km(lon1, lat1, lon2, lat2) -> np.ndarray:
    lon1, lat1, lon2, lat2 = (np.radians(np.asarray(value, dtype=float)) for value in (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def serving_cells(samples: pd.DataFrame, operators: pd.Series, cells: pd.DataFrame, config: dict[str, Any] | None,
                  max_distance_km: float) -> pd.DataFrame:
    """The inventory cell that served each sample (its first cell), with its distance and site; one row per sample.

    Only the networks allowed to serve the sample's Operator are searched, its own first; cells farther than
    ``max_distance_km`` from a located sample are not its serving cell.
    """
    columns = ['serving_cell', 'matched', 'network_family', 'host_family', 'vendor', 'site_id', 'band_3gpp', 'technology_cell',
               'site_latitude', 'site_longitude', 'distance_km', 'azimuth', 'site_key', 'mimo_tx', 'txrx_mode']
    result = pd.DataFrame(index=samples.index, columns=columns)
    result['serving_cell'] = [values[0] if len(values) else '' for values in samples['cells']]
    result['matched'] = False
    if cells.empty or samples.empty:
        return result
    allowed = []
    for operator in pd.unique(operators):
        for rank, family in enumerate(serving_families(operator)):
            allowed.append({'_operator': operator, 'network_family': family, '_rank': rank})
    allowed = pd.DataFrame(allowed, columns=['_operator', 'network_family', '_rank'])
    frame = pd.DataFrame({'_row': np.arange(len(samples)), 'serving_cell': result['serving_cell'].to_numpy(),
                          '_operator': operators.to_numpy(), '_lon': samples['longitude'].to_numpy(), '_lat': samples['latitude'].to_numpy()})
    frame = frame.loc[frame['serving_cell'].astype(str).str.fullmatch(r'\d+')]
    candidates = cells[['cell_identity', 'network_family', 'host_family', 'vendor', 'site_id', 'band_3gpp', 'technology',
                        'latitude', 'longitude', 'azimuth', 'mimo_tx', 'txrx_mode']].rename(
        columns={'cell_identity': 'serving_cell', 'technology': 'technology_cell'})
    matched = frame.merge(allowed, on='_operator').merge(candidates, on=['serving_cell', 'network_family'])
    if matched.empty:
        return result
    matched['distance_km'] = _haversine_km(matched['_lon'], matched['_lat'], matched['longitude'], matched['latitude'])
    matched = matched.loc[~(matched['distance_km'] > max_distance_km)]
    matched = matched.assign(_sort=matched['distance_km'].fillna(np.inf)).sort_values(['_row', '_rank', '_sort'], kind='stable')
    matched = matched.drop_duplicates('_row')
    positions = samples.index[matched['_row'].to_numpy()]
    result.loc[positions, 'matched'] = True
    for column in ('network_family', 'host_family', 'vendor', 'site_id', 'band_3gpp', 'technology_cell', 'distance_km', 'azimuth',
                   'mimo_tx', 'txrx_mode'):
        result.loc[positions, column] = matched[column].to_numpy()
    result.loc[positions, 'site_latitude'] = matched['latitude'].to_numpy()
    result.loc[positions, 'site_longitude'] = matched['longitude'].to_numpy()
    result.loc[positions, 'site_key'] = (matched['network_family'] + ':' + matched['site_id'].astype(str)).to_numpy()
    result['distance_km'] = pd.to_numeric(result['distance_km'], errors='coerce')
    result['mimo_tx'] = pd.to_numeric(result['mimo_tx'], errors='coerce')
    return result


def serving_summary(samples: pd.DataFrame, serving: pd.DataFrame, labels: pd.Series, overshoot_km: float) -> list[dict[str, Any]]:
    """Per analysis group: samples with a serving cell, found in the inventory, distances and overshooting share."""
    rows = []
    frame = serving.assign(_label=labels.to_numpy())
    for label, part in frame.groupby('_label', sort=False):
        with_cell = part['serving_cell'].astype(str).str.fullmatch(r'\d+')
        distances = part.loc[part['matched'].astype(bool), 'distance_km'].dropna()
        rows.append({
            'operator': str(label), 'samples': int(len(part)), 'with_cell': int(with_cell.sum()),
            'matched': int(part['matched'].astype(bool).sum()),
            'matched_share': round(float(part['matched'].astype(bool).sum()) / max(int(with_cell.sum()), 1) * 100, 1),
            'median_km': round(float(distances.median()), 3) if len(distances) else None,
            'p90_km': round(float(distances.quantile(.9)), 3) if len(distances) else None,
            'overshoot_share': round(float((distances > overshoot_km).mean()) * 100, 1) if len(distances) else None,
            'hosted_elsewhere_share': round(float((part.loc[part['matched'].astype(bool), 'host_family']
                                                   != part.loc[part['matched'].astype(bool), 'network_family']).mean()) * 100, 1)
            if part['matched'].astype(bool).any() else None,
        })
    return rows


def serving_breakdown(serving: pd.DataFrame, labels: pd.Series, field: str, overshoot_km: float) -> list[dict[str, Any]]:
    """Matched samples and distances per analysis group and serving-cell attribute (band, vendor, host network)."""
    frame = serving.assign(_label=labels.to_numpy()).loc[serving['matched'].astype(bool)]
    rows = []
    for (label, value), part in frame.groupby(['_label', field], sort=True):
        distances = part['distance_km'].dropna()
        rows.append({'operator': str(label), 'value': str(value or 'Not set'), 'samples': int(len(part)),
                     'median_km': round(float(distances.median()), 3) if len(distances) else None,
                     'overshoot_share': round(float((distances > overshoot_km).mean()) * 100, 1) if len(distances) else None})
    return rows


def overshooting_cells(samples: pd.DataFrame, serving: pd.DataFrame, overshoot_km: float, limit: int = 25,
                       family_labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """The cells that served the most samples beyond ``overshoot_km`` of their site."""
    frame = serving.loc[serving['matched'].astype(bool)].assign(_operator=samples['operator'].reindex(serving.index))
    far = frame.loc[frame['distance_km'] > overshoot_km]
    if far.empty:
        return []
    grouped = far.groupby(['_operator', 'serving_cell']).agg(
        samples=('distance_km', 'size'), median_km=('distance_km', 'median'), max_km=('distance_km', 'max'),
        site=('site_id', 'first'), band=('band_3gpp', 'first'), vendor=('vendor', 'first'), network=('network_family', 'first'),
        host=('host_family', 'first'), latitude=('site_latitude', 'first'), longitude=('site_longitude', 'first'),
    ).reset_index().sort_values(['samples', 'max_km'], ascending=False).head(limit)
    served = frame.groupby(['_operator', 'serving_cell']).size()
    return [{
        'operator': str(row['_operator']), 'cell': str(row['serving_cell']), 'site': str(row['site']), 'band': str(row['band']),
        'vendor': str(row['vendor']), 'network': family_label(str(row['network']), family_labels),
        'host': family_label(str(row['host']), family_labels),
        'samples_beyond': int(row['samples']), 'samples': int(served.get((row['_operator'], row['serving_cell']), 0)),
        'median_km': round(float(row['median_km']), 2), 'max_km': round(float(row['max_km']), 2),
        'latitude': float(row['latitude']) if pd.notna(row['latitude']) else None,
        'longitude': float(row['longitude']) if pd.notna(row['longitude']) else None,
    } for _index, row in grouped.iterrows()]


def nr_availability(samples: pd.DataFrame, serving: pd.DataFrame, labels: pd.Series, sites: pd.DataFrame,
                    limit: int = 25, nr_leg: pd.DataFrame | None = None) -> dict[str, Any]:
    """Samples anchored on LTE cells of sites that also have NR cells, and how many of them measured no NR.

    With ``nr_leg`` (see ``nsa_nr_cells``), the anchored samples that measured NR also show whether their NR cell was
    found, whether it is on the anchor's site and how far it is, and the NR sites that served the most samples.
    """
    nr_sites = set((sites.loc[sites['has_nr'], 'family'] + ':' + sites.loc[sites['has_nr'], 'site'].astype(str)))
    frame = serving.assign(_label=labels.to_numpy(), _nr=samples['nr_rsrp'].reindex(serving.index).notna().to_numpy(),
                           _operator=samples['operator'].reindex(serving.index).to_numpy())
    if nr_leg is not None:
        frame = frame.join(nr_leg[['nr_considered', 'nr_matched', 'nr_same_site', 'nr_distance_km', 'nr_site_key', 'nr_site_id',
                                   'nr_vendor', 'nr_site_latitude', 'nr_site_longitude']])
    anchored = frame.loc[frame['matched'].astype(bool) & (frame['technology_cell'] == 'LTE')]
    on_nr_site = anchored['site_key'].isin(nr_sites)
    rows = []
    for label, part in anchored.groupby('_label', sort=False):
        nr_part = part.loc[on_nr_site.loc[part.index]]
        other = part.loc[~on_nr_site.loc[part.index]]
        row = {
            'operator': str(label), 'anchored': int(len(part)), 'on_nr_sites': int(len(nr_part)),
            'without_nr_on_nr_sites': int((~nr_part['_nr']).sum()),
            'gap_share': round(float((~nr_part['_nr']).mean()) * 100, 1) if len(nr_part) else None,
            'without_nr_elsewhere_share': round(float((~other['_nr']).mean()) * 100, 1) if len(other) else None,
        }
        if nr_leg is not None:
            # The samples that measured NR with an NR PCI: was their NR cell found, on the anchor's site, how far?
            leg = part.loc[part['_nr'] & part['nr_considered'].astype(bool)]
            found = leg.loc[leg['nr_matched'].astype(bool)]
            distances = pd.to_numeric(found['nr_distance_km'], errors='coerce').dropna()
            row.update({
                'with_nr': int(part['_nr'].sum()), 'with_nr_pci': int(len(leg)),
                'nr_found_share': _percent(len(found), len(leg)),
                'nr_on_anchor_share': _percent(int(found['nr_same_site'].astype(bool).sum()), len(found)),
                'nr_median_km': round(float(distances.median()), 3) if len(distances) else None,
            })
        rows.append(row)
    gaps = anchored.loc[on_nr_site & ~anchored['_nr']]
    top = (gaps.groupby(['_operator', 'site_key']).agg(samples=('_nr', 'size'), site=('site_id', 'first'),
                                                       vendor=('vendor', 'first'), latitude=('site_latitude', 'first'),
                                                       longitude=('site_longitude', 'first'))
           .reset_index().sort_values('samples', ascending=False).head(limit))
    totals = anchored.loc[on_nr_site].groupby(['_operator', 'site_key']).size()
    result = {'rows': rows, 'sites': [{
        'operator': str(row['_operator']), 'site': str(row['site']), 'vendor': str(row['vendor']),
        'samples_without_nr': int(row['samples']), 'samples': int(totals.get((row['_operator'], row['site_key']), 0)),
        'latitude': float(row['latitude']) if pd.notna(row['latitude']) else None,
        'longitude': float(row['longitude']) if pd.notna(row['longitude']) else None,
    } for _index, row in top.iterrows()]}
    if nr_leg is not None:
        result['nr_sites'] = nr_leg_sites(frame, limit)
    return result


def _percent(part: int, total: int) -> float | None:
    return round(part / total * 100, 1) if total else None


# ---------------------------------------------------------------------------
# NR cell of the NSA samples
# ---------------------------------------------------------------------------
def nr_carriers(cells: pd.DataFrame) -> pd.DataFrame:
    """The NR cells with a PCI and the downlink range (MHz) of their carrier: centre frequency ± half the bandwidth."""
    nr = cells.loc[cells['is_nr'].astype(bool) & cells['pci'].notna()]
    channels = {value: channel_frequency(value, 'NR') for value in pd.unique(nr['channel'].dropna())}
    centre = nr['channel'].map(channels).astype(float)
    half = pd.to_numeric(nr['bandwidth_mhz'], errors='coerce').astype(float) / 2
    return pd.DataFrame({
        'nr_cell': nr['cell_identity'].astype(str), 'network_family': nr['network_family'], 'host_family': nr['host_family'],
        'vendor': nr['vendor'], 'site_id': nr['site_id'], 'site_key': nr['site_key'], 'band_3gpp': nr['band_3gpp'],
        'pci': pd.to_numeric(nr['pci'], errors='coerce').astype('int64'), 'low_mhz': centre - half, 'high_mhz': centre + half,
        'cell_latitude': nr['latitude'].astype(float), 'cell_longitude': nr['longitude'].astype(float),
        'mimo_tx': nr['mimo_tx'].astype(float), 'txrx_mode': nr['txrx_mode'],
    }).reset_index(drop=True)


def _carrier_fits(frame: pd.DataFrame) -> pd.Series:
    """Whether each (sample, NR cell) pair agrees on the band and the SSB frequency lies inside the cell's carrier.

    The CDRs report the SSB NR-ARFCN, not the carrier centre the inventories hold, so the frequencies only need to
    overlap; a value missing on either side does not exclude the cell.
    """
    band_ok = frame['_band'].eq('') | frame['band_3gpp'].eq('') | frame['_band'].eq(frame['band_3gpp'])
    frequency_ok = (frame['_ssb_mhz'].isna() | frame['low_mhz'].isna() | frame['high_mhz'].isna()
                    | (frame['_ssb_mhz'].ge(frame['low_mhz'] - 0.5) & frame['_ssb_mhz'].le(frame['high_mhz'] + 0.5)))
    return band_ok & frequency_ok


NR_LEG_COLUMNS = ('nr_considered', 'nr_matched', 'nr_method', 'nr_candidates', 'nr_cell', 'nr_network_family', 'nr_host_family',
                  'nr_vendor', 'nr_site_id', 'nr_site_key', 'nr_band_3gpp', 'nr_distance_km', 'nr_same_site', 'nr_site_latitude',
                  'nr_site_longitude', 'nr_mimo_tx', 'nr_txrx_mode')


def nsa_nr_cells(samples: pd.DataFrame, operators: pd.Series, serving: pd.DataFrame, cells: pd.DataFrame,
                 config: dict[str, Any] | None, max_distance_km: float, chunk_rows: int = 20_000) -> pd.DataFrame:
    """The NR cell that served each NSA sample, one row per sample.

    NSA CDRs only identify the LTE anchor cell; the NR leg is known by its PCI and its band or SSB NR-ARFCN. Among the
    NR cells with that PCI whose band and carrier agree, the one on the anchor's site wins (``anchor_site``); else the
    nearest one of the networks allowed to serve the sample's Operator within ``max_distance_km``, the anchor's
    network first: ``only_candidate`` when it is the only one of its network there, ``nearest`` (ambiguous) otherwise.
    """
    result = pd.DataFrame(index=samples.index, columns=list(NR_LEG_COLUMNS), dtype=object)
    for column in ('nr_considered', 'nr_matched', 'nr_same_site'):
        result[column] = False
    if samples.empty or 'nr_pci' not in samples:
        return result
    pci = pd.to_numeric(samples['nr_pci'], errors='coerce')
    band = samples['nr_band'].fillna('').astype(str) if 'nr_band' in samples else pd.Series('', index=samples.index)
    arfcn = pd.to_numeric(samples['nr_arfcn'], errors='coerce') if 'nr_arfcn' in samples else pd.Series(math.nan, index=samples.index)
    frequencies = {value: nr_arfcn_frequency(value) for value in pd.unique(arfcn.dropna())}
    ssb = arfcn.map(frequencies).astype(float)
    # SA samples are served by the NR cell itself; a PCI alone is too common to identify a cell.
    considered = pci.between(0, 1007) & samples['cells_technology'].ne('NR') & (band.ne('') | ssb.notna())
    result['nr_considered'] = considered.to_numpy()
    carriers = nr_carriers(cells) if not cells.empty else pd.DataFrame()
    if not considered.any() or carriers.empty:
        return result
    anchored = serving['matched'].astype(bool) & serving['technology_cell'].eq('LTE') & serving['site_id'].fillna('').astype(str).ne('')
    frame = pd.DataFrame({
        '_row': np.arange(len(samples)), '_operator': operators.to_numpy(), 'pci': pci.fillna(-1).astype('int64').to_numpy(),
        '_band': band.to_numpy(), '_ssb_mhz': ssb.to_numpy(), '_lon': samples['longitude'].to_numpy(dtype=float),
        '_lat': samples['latitude'].to_numpy(dtype=float),
        '_anchor_site': serving['site_key'].where(anchored, '').fillna('').to_numpy(),
        '_anchor_family': serving['network_family'].where(anchored, '').fillna('').to_numpy(),
    }).loc[considered.to_numpy()]

    def located(pairs: pd.DataFrame) -> pd.DataFrame:
        return pairs.assign(distance_km=_haversine_km(pairs['_lon'], pairs['_lat'], pairs['cell_longitude'], pairs['cell_latitude']))

    # 1. The NR cells with that PCI on the site of the LTE anchor.
    on_site = frame.loc[frame['_anchor_site'] != ''].merge(carriers, left_on=['_anchor_site', 'pci'], right_on=['site_key', 'pci'])
    on_site = located(on_site.loc[_carrier_fits(on_site)])
    on_site = on_site.assign(_sort=on_site['distance_km'].fillna(np.inf)).sort_values(['_row', '_sort'], kind='stable')
    best = [on_site.drop_duplicates('_row').assign(nr_method='anchor_site',
                                                   nr_candidates=on_site.groupby('_row')['_row'].transform('size'))]
    # 2. The other samples: the nearest NR cell with that PCI of the networks allowed to serve them.
    allowed = pd.DataFrame([{'_operator': operator, 'network_family': family, '_rank': rank}
                            for operator in pd.unique(operators) for rank, family in enumerate(serving_families(operator, config))],
                           columns=['_operator', 'network_family', '_rank'])
    rest = frame.loc[~frame['_row'].isin(set(on_site['_row'])) & frame['_lon'].notna() & frame['_lat'].notna()]
    for start in range(0, len(rest), chunk_rows):
        pairs = rest.iloc[start:start + chunk_rows].merge(allowed, on='_operator').merge(carriers, on=['network_family', 'pci'])
        pairs = located(pairs.loc[_carrier_fits(pairs)])
        pairs = pairs.loc[pairs['distance_km'] <= max_distance_km]
        if pairs.empty:
            continue
        pairs = pairs.assign(_other_network=pairs['network_family'] != pairs['_anchor_family'])
        pairs = pairs.sort_values(['_row', '_other_network', '_rank', 'distance_km'], kind='stable')
        chosen = pairs.drop_duplicates('_row')
        counts = pairs.groupby(['_row', 'network_family']).size()
        candidates = counts.reindex(pd.MultiIndex.from_arrays([chosen['_row'], chosen['network_family']])).to_numpy()
        best.append(chosen.assign(nr_candidates=candidates, nr_method=np.where(candidates > 1, 'nearest', 'only_candidate')))
    best = pd.concat([part for part in best if not part.empty], ignore_index=True) if any(not part.empty for part in best) else pd.DataFrame()
    if best.empty:
        return result
    positions = samples.index[best['_row'].to_numpy()]
    values = {
        'nr_matched': True, 'nr_method': best['nr_method'], 'nr_candidates': best['nr_candidates'], 'nr_cell': best['nr_cell'],
        'nr_network_family': best['network_family'], 'nr_host_family': best['host_family'], 'nr_vendor': best['vendor'],
        'nr_site_id': best['site_id'], 'nr_site_key': best['site_key'], 'nr_band_3gpp': best['band_3gpp'],
        'nr_distance_km': best['distance_km'], 'nr_same_site': best['site_key'].eq(best['_anchor_site']),
        'nr_site_latitude': best['cell_latitude'], 'nr_site_longitude': best['cell_longitude'],
        'nr_mimo_tx': best['mimo_tx'], 'nr_txrx_mode': best['txrx_mode'],
    }
    for column, value in values.items():
        result.loc[positions, column] = value.to_numpy() if isinstance(value, pd.Series) else value
    for column in ('nr_distance_km', 'nr_mimo_tx', 'nr_site_latitude', 'nr_site_longitude', 'nr_candidates'):
        result[column] = pd.to_numeric(result[column], errors='coerce')
    return result


def nr_leg_summary(nr_leg: pd.DataFrame, labels: pd.Series) -> list[dict[str, Any]]:
    """Per analysis group: the NSA samples with an NR PCI, how their NR cell was found and how far its site is."""
    frame = nr_leg.assign(_label=labels.to_numpy())
    rows = []
    for label, part in frame.loc[frame['nr_considered'].astype(bool)].groupby('_label', sort=False):
        found = part.loc[part['nr_matched'].astype(bool)]
        distances = pd.to_numeric(found['nr_distance_km'], errors='coerce').dropna()
        methods = found['nr_method'].value_counts()
        vendors = found['nr_vendor'].fillna('').replace('', 'Not set').value_counts()
        rows.append({
            'operator': str(label), 'with_nr_pci': int(len(part)), 'found': int(len(found)),
            'found_share': _percent(len(found), len(part)),
            **{f'{method}_share': _percent(int(methods.get(method, 0)), len(part)) for method in NR_LEG_METHODS},
            'median_km': round(float(distances.median()), 3) if len(distances) else None,
            'p90_km': round(float(distances.quantile(.9)), 3) if len(distances) else None,
            'vendors': [{'vendor': str(vendor), 'share': _percent(int(count), len(found))} for vendor, count in vendors.head(4).items()],
        })
    return rows


def nr_leg_sites(frame: pd.DataFrame, limit: int = 25) -> list[dict[str, Any]]:
    """The NR sites that served the most NSA samples, with the share served from the anchor's own site."""
    found = frame.loc[frame['nr_matched'].astype(bool)]
    if found.empty:
        return []
    grouped = (found.assign(_same=found['nr_same_site'].astype(bool), _km=pd.to_numeric(found['nr_distance_km'], errors='coerce'))
               .groupby(['_operator', 'nr_site_key'])
               .agg(samples=('_same', 'size'), same=('_same', 'mean'), median_km=('_km', 'median'), site=('nr_site_id', 'first'),
                    vendor=('nr_vendor', 'first'), latitude=('nr_site_latitude', 'first'), longitude=('nr_site_longitude', 'first'))
               .reset_index().sort_values('samples', ascending=False, kind='stable').head(limit))
    return [{
        'operator': str(row['_operator']), 'site': str(row['site']), 'vendor': str(row['vendor']), 'samples': int(row['samples']),
        'from_anchor_share': round(float(row['same']) * 100, 1),
        'median_km': round(float(row['median_km']), 3) if pd.notna(row['median_km']) else None,
        'latitude': float(row['latitude']) if pd.notna(row['latitude']) else None,
        'longitude': float(row['longitude']) if pd.notna(row['longitude']) else None,
    } for _index, row in grouped.iterrows()]


# ---------------------------------------------------------------------------
# MIMO: inventory antennas against the rank and layers the samples reported
# ---------------------------------------------------------------------------
def mimo_breakdown(samples: pd.DataFrame, serving: pd.DataFrame, nr_leg: pd.DataFrame | None, labels: pd.Series) -> list[dict[str, Any]]:
    """Per analysis group, technology and TX antennas of the serving cell: the samples, their mean rank, the time
    share per rank, the NR maximum MIMO layers and the rank use (mean rank ÷ min(TX antennas, 4)).

    LTE samples take the LTE cell that served them; NR samples the NR cell of SA samples or the NR cell found for
    NSA samples (see ``nsa_nr_cells``). Cells whose inventory gives no TXRX mode or TX antennas are ``Not set``.
    """
    matched = serving['matched'].astype(bool)
    sa = matched & serving['technology_cell'].eq('NR')
    rows = []
    for technology, rank, shares in (('LTE', 'lte_rank', 'lte_rank_shares'), ('NR', 'nr_rank', 'nr_rank_shares')):
        if rank not in samples:
            continue
        layers = pd.to_numeric(samples['nr_layers'], errors='coerce') if technology == 'NR' and 'nr_layers' in samples else None
        if technology == 'LTE':
            has_cell, tx, modes = matched & serving['technology_cell'].eq('LTE'), serving['mimo_tx'], serving['txrx_mode']
        else:
            leg = nr_leg if nr_leg is not None else pd.DataFrame(index=serving.index, columns=['nr_matched', 'nr_mimo_tx', 'nr_txrx_mode'])
            nsa = leg['nr_matched'].fillna(False).astype(bool) & ~sa
            has_cell = sa | nsa
            tx = serving['mimo_tx'].where(sa, leg['nr_mimo_tx'])
            modes = serving['txrx_mode'].where(sa, leg['nr_txrx_mode'])
        measured = samples[rank].notna() if layers is None else samples[rank].notna() | layers.notna()
        keep = (has_cell & measured).to_numpy()
        if not keep.any():
            continue
        tx = pd.to_numeric(tx, errors='coerce')
        frame = pd.DataFrame({
            '_label': labels.to_numpy()[keep], '_tx': tx.to_numpy(dtype=float)[keep], '_mode': modes.fillna('').astype(str).to_numpy()[keep],
            '_rank': pd.to_numeric(samples[rank], errors='coerce').to_numpy(dtype=float)[keep],
            '_shares': samples[shares].to_numpy()[keep] if shares in samples else None,
            '_layers': layers.to_numpy(dtype=float)[keep] if layers is not None else math.nan,
        })
        frame['_group'] = frame['_tx'].fillna(-1)
        for (label, group), part in frame.groupby(['_label', '_group'], sort=False):
            ranks = part['_rank'].dropna()
            distribution = [values for values in part['_shares'] if isinstance(values, tuple)]
            average = np.mean(np.array(distribution, dtype=float), axis=0) if distribution else None
            tx_count = None if group < 0 else int(group)
            mean_rank = float(ranks.mean()) if len(ranks) else None
            # The TXRX modes of the cells, and TX antennas for the cells that only give their number of antennas.
            modes_seen = [value for value in part['_mode'].value_counts().index if value][:3]
            if tx_count and part['_mode'].eq('').any():
                modes_seen.append('TX antennas')
            rows.append({
                'operator': str(label), 'technology': technology, 'tx_antennas': tx_count,
                'mimo': f'{tx_count}T' if tx_count else 'Not set', 'modes': modes_seen,
                'samples': int(len(part)), 'rank_samples': int(len(ranks)),
                'mean_rank': round(mean_rank, 2) if mean_rank is not None else None,
                'rank2_share': round(100 - float(average[0]), 1) if average is not None else None,
                'rank_classes': [{'label': f'Rank {index + 1}', 'share': round(float(share), 1), 'colour': RANK_COLOURS[index]}
                                 for index, share in enumerate(average)] if average is not None else [],
                'mean_layers': round(float(part['_layers'].mean()), 2) if part['_layers'].notna().any() else None,
                'rank_use': round(mean_rank / min(tx_count, 4) * 100, 1) if mean_rank is not None and tx_count else None,
            })
    return sorted(rows, key=lambda row: (row['technology'], row['tx_antennas'] is None, row['tx_antennas'] or 0))


# Vendor colours of the inventory sites drawn on the maps: none of them is a colour of the RSRP/SINR quality scale
# (green, yellow, orange, red), so a site never reads as a measurement.
VENDOR_COLOURS = {'ericsson': '#1971C2', 'huawei': '#9C36B5', 'nsn': '#0C8599', 'nokia': '#0C8599', 'samsung': '#343A40',
                  'mavenir': '#8B5E34', 'zte': '#D6336C'}


def vendor_colour(vendor: str) -> str:
    return VENDOR_COLOURS.get(str(vendor or '').strip().casefold(), '#868E96')


# Rings drawn around the inventory sites of the maps whose cells the snapshot flags (see cell_states): solid for
# outages, dashed for plans. Legend labels stay within the 28 characters the map legend shows.
STATE_RINGS = {'outage': ('Locked, halted or disabled', '#212529'), 'pipeline': ('Planned or in progress', '#ADB5BD')}


def _state_summary(flagged: pd.DataFrame) -> str:
    """``Locked: 2 cells (B3) · Planned: 3 cells (n78)``: the flagged cells of a site per state, with their bands."""
    parts = []
    for state in CELL_STATES:
        part = flagged.loc[flagged['state'] == state]
        if part.empty:
            continue
        bands = ', '.join(sorted(set(part['band_3gpp']) - {''}, key=_band_order))
        parts.append(f"{state}: {len(part)} cell{'s' if len(part) != 1 else ''}" + (f' ({bands})' if bands else ''))
    return ' · '.join(parts)


def sector_overlay(cells: pd.DataFrame, families: Iterable[str], centres: list[tuple[float, float]],
                   radius_km: float = 3.0, limit_sites: int = 600) -> dict[str, Any]:
    """The sites of the given networks near the given map positions, with one wedge per cell in service (azimuth,
    beamwidth and the colour of its vendor), to draw on the coverage and interference maps.

    Sites with cells that the snapshot flags Locked, Halted or Disabled carry a ring, and sites not on air yet or
    with cells In progress or Planned a dashed ring; their tooltip lists those cells per state.
    """
    wanted = set(families)
    states = cells['state'] if 'state' in cells else pd.Series('', index=cells.index)
    frame = cells.loc[cells['network_family'].isin(wanted) & (cells['in_service'] | states.isin(('In progress', 'Planned')))
                      & cells['latitude'].notna() & cells['longitude'].notna()]
    if frame.empty or not centres:
        return {'sectors': [], 'legend': []}
    sites = frame.groupby(['network_family', 'site_id'], sort=False).agg(latitude=('latitude', 'median'), longitude=('longitude', 'median'))
    near = np.zeros(len(sites), dtype=bool)
    distance_to_centre = np.full(len(sites), np.inf)
    for longitude, latitude in centres:
        distances = _haversine_km(sites['longitude'].to_numpy(), sites['latitude'].to_numpy(), np.full(len(sites), longitude), np.full(len(sites), latitude))
        near |= distances <= radius_km
        distance_to_centre = np.minimum(distance_to_centre, distances)
    chosen = sites.loc[near].assign(_distance=distance_to_centre[near]).sort_values('_distance').head(limit_sites)
    if chosen.empty:
        return {'sectors': [], 'legend': []}
    keys = set(chosen.index)
    selected = frame.loc[[key in keys for key in zip(frame['network_family'], frame['site_id'], strict=True)]]
    if 'state' not in selected:
        selected = selected.assign(state='')
    overlay, vendors, rings = [], set(), set()
    for (family, site), part in selected.groupby(['network_family', 'site_id'], sort=False):
        position = chosen.loc[(family, site)]
        on_air = part.loc[part['in_service'].astype(bool)]
        wedges = []
        for row in on_air.drop_duplicates(['azimuth', 'band_3gpp', 'vendor']).itertuples():
            vendors.add(row.vendor or 'Unknown')
            azimuth = None if pd.isna(row.azimuth) else round(float(row.azimuth), 1)
            beamwidth = None if pd.isna(row.beamwidth) else round(float(row.beamwidth), 1)
            wedges.append([azimuth, beamwidth, vendor_colour(row.vendor)])
        described = on_air if len(on_air) else part
        bands = ' '.join(sorted(set(described['band_3gpp']) - {''}, key=_band_order))
        flagged = part.loc[part['state'] != '']
        entry = {
            'lon': round(float(position['longitude']), 6), 'lat': round(float(position['latitude']), 6),
            'label': f"Site {site} · {family_label(family)}", 'detail': f"{', '.join(sorted(set(described['vendor']) - {''}))} · {bands}",
            'cells': wedges[:24],
        }
        if len(flagged):
            ring = 'outage' if flagged['state'].isin(OUTAGE_STATES).any() else 'pipeline'
            rings.add(ring)
            entry.update({'ring': ring, 'detail': f"{entry['detail']} · {_state_summary(flagged)}",
                          'series': 'Inventory site not on air yet' if on_air.empty else 'Inventory site with flagged cells'})
        overlay.append(entry)
    legend = [{'label': f'{vendor} sites', 'colour': vendor_colour(vendor), 'marker': 'triangle'} for vendor in sorted(vendors, key=str.casefold)]
    legend += [{'label': STATE_RINGS[ring][0], 'colour': STATE_RINGS[ring][1], 'marker': 'triangle'} for ring in STATE_RINGS if ring in rings]
    return {'sectors': overlay, 'legend': legend}


def cell_status_near_areas(cells: pd.DataFrame, families: Iterable[str], areas: list[dict[str, Any]], radius_km: float = 3.0,
                           limit: int = 40, family_labels: dict[str, str] | None = None) -> dict[str, Any]:
    """The sites of the given networks within ``radius_km`` of the weak areas whose cells the snapshot flags Locked,
    Halted, Disabled, In progress or Planned, nearest first, each with its nearest area.

    ``areas`` are the weakest coverage and highest interference areas (``kind``, ``latitude``, ``longitude``, ``city``).
    ``known_share`` is the share of the networks' cells whose administrative or operational state the snapshot gives:
    a cell without them is only flagged by its OSS status or inventory status.
    """
    wanted = set(families)
    part = cells.loc[cells['network_family'].isin(wanted)]
    result = {'rows': [], 'radius_km': radius_km, 'states': list(CELL_STATES), 'sites': {},
              'known_share': round(float(part['state_known'].astype(bool).mean()) * 100, 1) if len(part) else None}
    flagged = part.loc[part['state'].ne('') & part['latitude'].notna() & part['longitude'].notna()]
    if flagged.empty or not areas:
        return result
    sites = flagged.groupby('site_key', sort=False).agg(
        family=('network_family', 'first'), host=('host_family', 'first'), site=('site_id', 'first'), vendor=('vendor', 'first'),
        latitude=('latitude', 'median'), longitude=('longitude', 'median'))
    area_longitudes = np.array([float(area['longitude']) for area in areas])
    area_latitudes = np.array([float(area['latitude']) for area in areas])
    distances = _haversine_km(sites['longitude'].to_numpy()[:, None], sites['latitude'].to_numpy()[:, None],
                              area_longitudes[None, :], area_latitudes[None, :])
    sites = sites.assign(_area=distances.argmin(axis=1), _km=distances.min(axis=1))
    sites = sites.loc[sites['_km'] <= radius_km].sort_values('_km', kind='stable').head(limit)
    if sites.empty:
        return result
    on_air = set(part.loc[part['in_service'].astype(bool), 'site_key'])
    near = flagged.loc[flagged['site_key'].isin(set(sites.index))]
    by_site = dict(tuple(near.groupby('site_key', sort=False)))
    for key, site in sites.iterrows():
        site_cells = by_site[key]
        area = areas[int(site['_area'])]
        counts = site_cells['state'].value_counts()
        result['rows'].append({
            'site': str(site['site'] or key.split(':', 1)[-1]), 'network': family_label(str(site['family']), family_labels),
            'host': family_label(str(site['host']), family_labels), 'vendor': str(site['vendor']),
            'states': [{'state': state, 'cells': int(counts[state])} for state in CELL_STATES if state in counts],
            'summary': _state_summary(site_cells), 'on_air': key in on_air,
            'area_kind': str(area.get('kind') or ''), 'area': str(area.get('city') or f"{float(area['latitude']):.3f}, {float(area['longitude']):.3f}"),
            'distance_km': round(float(site['_km']), 2),
            'latitude': round(float(site['latitude']), 6), 'longitude': round(float(site['longitude']), 6),
        })
    for row in result['rows']:
        for item in row['states']:
            result['sites'][item['state']] = result['sites'].get(item['state'], 0) + 1
    return result


def compare_snapshots(current: pd.DataFrame, other: pd.DataFrame, operator_labels: dict[str, str] | None = None,
                      limit: int = 12) -> list[dict[str, Any]]:
    """What changed between two snapshots of each network: cells added and removed, and vendor swaps by region."""
    rows = []
    for family in sorted(set(current['network_family']) & set(other['network_family'])):
        now = current.loc[current['network_family'] == family].drop_duplicates(['technology', 'cell_identity'])
        before = other.loc[other['network_family'] == family].drop_duplicates(['technology', 'cell_identity'])
        merged = now.merge(before, on=['technology', 'cell_identity'], how='outer', suffixes=('', '_before'), indicator=True)
        common = merged.loc[merged['_merge'] == 'both']
        changed = common.loc[common['vendor'].fillna('') != common['vendor_before'].fillna('')]
        swaps = (changed.groupby(['vendor_before', 'vendor']).agg(cells=('cell_identity', 'size'), sites=('site_id', 'nunique'))
                 .reset_index().sort_values('cells', ascending=False).head(limit))
        regions = (changed.assign(region=changed['region'].replace('', 'Not set'))
                   .groupby('region').agg(cells=('cell_identity', 'size'), sites=('site_id', 'nunique'))
                   .reset_index().sort_values('cells', ascending=False).head(limit))
        rows.append({
            'family': family, 'operator': family_label(family, operator_labels),
            'cells': int(len(now)), 'cells_before': int(len(before)), 'common': int(len(common)),
            'added': int((merged['_merge'] == 'left_only').sum()), 'removed': int((merged['_merge'] == 'right_only').sum()),
            'vendor_changed': int(len(changed)), 'sites_with_vendor_change': int(changed['site_id'].nunique()),
            'swaps': [{'from': str(row.vendor_before or 'Not set'), 'to': str(row.vendor or 'Not set'), 'cells': int(row.cells), 'sites': int(row.sites)}
                      for row in swaps.itertuples()],
            'regions': [{'region': str(row.region), 'cells': int(row.cells), 'sites': int(row.sites)} for row in regions.itertuples()],
        })
    return rows
