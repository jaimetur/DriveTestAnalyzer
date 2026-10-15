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


def load_cells(repository: Any, selection: dict[str, int]) -> pd.DataFrame:
    """The cells of each selected (family, snapshot), cached in memory per snapshot revision."""
    if not selection:
        return pd.DataFrame(columns=[*CELL_FIELDS, 'band_3gpp', 'in_service', 'site_key', 'is_lte', 'is_nr']).astype(
            {'in_service': bool, 'is_lte': bool, 'is_nr': bool})
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
               'site_latitude', 'site_longitude', 'distance_km', 'azimuth', 'site_key']
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
                        'latitude', 'longitude', 'azimuth']].rename(columns={'cell_identity': 'serving_cell', 'technology': 'technology_cell'})
    matched = frame.merge(allowed, on='_operator').merge(candidates, on=['serving_cell', 'network_family'])
    if matched.empty:
        return result
    matched['distance_km'] = _haversine_km(matched['_lon'], matched['_lat'], matched['longitude'], matched['latitude'])
    matched = matched.loc[~(matched['distance_km'] > max_distance_km)]
    matched = matched.assign(_sort=matched['distance_km'].fillna(np.inf)).sort_values(['_row', '_rank', '_sort'], kind='stable')
    matched = matched.drop_duplicates('_row')
    positions = samples.index[matched['_row'].to_numpy()]
    result.loc[positions, 'matched'] = True
    for column in ('network_family', 'host_family', 'vendor', 'site_id', 'band_3gpp', 'technology_cell', 'distance_km', 'azimuth'):
        result.loc[positions, column] = matched[column].to_numpy()
    result.loc[positions, 'site_latitude'] = matched['latitude'].to_numpy()
    result.loc[positions, 'site_longitude'] = matched['longitude'].to_numpy()
    result.loc[positions, 'site_key'] = (matched['network_family'] + ':' + matched['site_id'].astype(str)).to_numpy()
    result['distance_km'] = pd.to_numeric(result['distance_km'], errors='coerce')
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
                    limit: int = 25) -> dict[str, Any]:
    """Samples anchored on LTE cells of sites that also have NR cells, and how many of them measured no NR."""
    nr_sites = set((sites.loc[sites['has_nr'], 'family'] + ':' + sites.loc[sites['has_nr'], 'site'].astype(str)))
    frame = serving.assign(_label=labels.to_numpy(), _nr=samples['nr_rsrp'].reindex(serving.index).notna().to_numpy(),
                           _operator=samples['operator'].reindex(serving.index).to_numpy())
    anchored = frame.loc[frame['matched'].astype(bool) & (frame['technology_cell'] == 'LTE')]
    on_nr_site = anchored['site_key'].isin(nr_sites)
    rows = []
    for label, part in anchored.groupby('_label', sort=False):
        nr_part = part.loc[on_nr_site.loc[part.index]]
        other = part.loc[~on_nr_site.loc[part.index]]
        rows.append({
            'operator': str(label), 'anchored': int(len(part)), 'on_nr_sites': int(len(nr_part)),
            'without_nr_on_nr_sites': int((~nr_part['_nr']).sum()),
            'gap_share': round(float((~nr_part['_nr']).mean()) * 100, 1) if len(nr_part) else None,
            'without_nr_elsewhere_share': round(float((~other['_nr']).mean()) * 100, 1) if len(other) else None,
        })
    gaps = anchored.loc[on_nr_site & ~anchored['_nr']]
    top = (gaps.groupby(['_operator', 'site_key']).agg(samples=('_nr', 'size'), site=('site_id', 'first'),
                                                       vendor=('vendor', 'first'), latitude=('site_latitude', 'first'),
                                                       longitude=('site_longitude', 'first'))
           .reset_index().sort_values('samples', ascending=False).head(limit))
    totals = anchored.loc[on_nr_site].groupby(['_operator', 'site_key']).size()
    return {'rows': rows, 'sites': [{
        'operator': str(row['_operator']), 'site': str(row['site']), 'vendor': str(row['vendor']),
        'samples_without_nr': int(row['samples']), 'samples': int(totals.get((row['_operator'], row['site_key']), 0)),
        'latitude': float(row['latitude']) if pd.notna(row['latitude']) else None,
        'longitude': float(row['longitude']) if pd.notna(row['longitude']) else None,
    } for _index, row in top.iterrows()]}


VENDOR_COLOURS = {'ericsson': '#1C7ED6', 'huawei': '#E03131', 'nsn': '#7048E8', 'nokia': '#7048E8', 'samsung': '#0CA678',
                  'mavenir': '#F08C00', 'zte': '#C2255C'}


def vendor_colour(vendor: str) -> str:
    return VENDOR_COLOURS.get(str(vendor or '').strip().casefold(), '#868E96')


def sector_overlay(cells: pd.DataFrame, families: Iterable[str], centres: list[tuple[float, float]],
                   radius_km: float = 3.0, limit_sites: int = 600) -> dict[str, Any]:
    """The sites of the given networks near the given map positions, with one wedge per cell (azimuth, beamwidth and
    the colour of its vendor), to draw on the coverage and interference maps."""
    wanted = set(families)
    frame = cells.loc[cells['network_family'].isin(wanted) & cells['in_service'] & cells['latitude'].notna() & cells['longitude'].notna()]
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
    overlay, vendors = [], set()
    for (family, site), part in selected.groupby(['network_family', 'site_id'], sort=False):
        position = chosen.loc[(family, site)]
        wedges = []
        for row in part.drop_duplicates(['azimuth', 'band_3gpp', 'vendor']).itertuples():
            vendors.add(row.vendor or 'Unknown')
            azimuth = None if pd.isna(row.azimuth) else round(float(row.azimuth), 1)
            beamwidth = None if pd.isna(row.beamwidth) else round(float(row.beamwidth), 1)
            wedges.append([azimuth, beamwidth, vendor_colour(row.vendor)])
        bands = ' '.join(sorted(set(part['band_3gpp']) - {''}, key=_band_order))
        overlay.append({
            'lon': round(float(position['longitude']), 6), 'lat': round(float(position['latitude']), 6),
            'label': f"Site {site} · {family_label(family)}", 'detail': f"{', '.join(sorted(set(part['vendor']) - {''}))} · {bands}",
            'cells': wedges[:24],
        })
    legend = [{'label': f'{vendor} sectors', 'colour': vendor_colour(vendor)} for vendor in sorted(vendors, key=str.casefold)]
    return {'sectors': overlay, 'legend': legend}


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
