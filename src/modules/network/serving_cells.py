"""Serving-cell Vendor mapping: the Vendor of each CDR sample from the inventory cells that served it.

A sample's first and last serving cells are looked up among the cells of the networks allowed to serve its
Operator (its own network and, for example, the eMOCN partner network or the host network of an MVNO), in the
inventory snapshots selected for the CDR. When a cell is in several snapshots, the snapshot whose date is closest
to the CDR's measurements wins (the newest on a tie), so a CDR measured before a vendor swap keeps the vendor it
measured. A cell farther than the maximum serving distance from the sample is ignored: global cell identities are
only unique within an Operator, and a distant cell with the same number is not the one that served the sample.

The sources are the Multivendor Mappings chosen for the CDR and the Network Inventories chosen with them, which then only
complete the cells the Multivendor Mappings do not have. Every source gives every Operator its serving cell, but beside
Multivendor Mappings only the Operators chosen for them receive a Vendor: the others keep their name, as an Operator that
no source serves (O2, whose inventory covers only the cells Vodafone hosts for it).

Besides ``Operator_Vendor`` and ``Vendor`` (same rule as before: the same Vendor at both ends, Ericsson
(Mixed) or Mixed (non-Ericsson)), each sample receives the owner network, host network, site, eMOCN scenario and
distance of the cell that served its start, and the date of the snapshot it came from; and, from both ends as the
Vendor (the same at both, else MIX), its RAN Vendor with the network that hosts it (``Serving_RAN_Vendor``:
VF_Hosted_Ericsson, VMO2_Hosted_Nokia…) and its site type (``Serving_Site_Class``: 3UK_Legacy, VF_eMOCN_S1, VF_NNS…).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.modules.cdr.cdr_field_profiles import NETCHECK_PROFILE, CdrFieldProfile, workspace_field_profile
from src.modules.cdr_analysis.cdr_reporting import (
    VENDOR_UNKNOWN, _first_existing, _normalise_operator, _split_global_cells, _vendor_from_ends, _vendor_prefix, _with_vendor_columns,
    operator_key,
)
from src.modules.network.network_inventory import (
    INVENTORY_CELLS_TABLE, MAPPING_CELLS_TABLE, MULTIVENDOR_MAPPING_KIND, NETWORK_FAMILY_LABELS, dataset_revision,
    effective_snapshot_date, ensure_inventory_cells, ensure_mapping_cells, infer_snapshot_date, inventory_datasets,
    mapping_datasets, network_family,
)

SERVING_NETWORKS_STATE_KEY = 'network_serving_networks'
# Raise when the mapping rule changes, so the CDRs mapped before show that they need mapping again (3: the RAN Vendor
# and the site type of the samples, ticket #85).
SERVING_ENGINE_VERSION = 3
DEFAULT_MAX_DISTANCE_KM = 30.0
# The networks whose cells serve the subscribers of each network family, in order of preference: Vodafone and
# Three share their RAN through eMOCN, and Lebara subscribers use the Vodafone network.
DEFAULT_SERVING_FAMILIES: dict[str, tuple[str, ...]] = {
    'vodafone': ('vodafone', 'three'), 'three': ('three', 'vodafone'), 'lebara': ('vodafone', 'three'),
}
# The cell chain, positions and time of a NetCheck sample (every CDR type lists its own, see cdr_field_profiles).
CDR_CELL_COLUMNS = NETCHECK_PROFILE.cell_columns
START_COORDINATES = NETCHECK_PROFILE.start_coordinates
END_COORDINATES = NETCHECK_PROFILE.end_coordinates
TIME_COLUMNS = NETCHECK_PROFILE.time_columns
SERVING_FIELDS = ('Serving_Network', 'Serving_Host_Network', 'Serving_Site_ID', 'Serving_eMOCN_Scenario',
                  'Serving_Distance_km', 'Serving_Inventory_Snapshot', 'Serving_RAN_Vendor', 'Serving_Site_Class')
# The short name of each network in the RAN Vendor and site type classes (VF_Hosted_Ericsson, 3UK_eMOCN_S1, VMO2_Legacy).
NETWORK_CLASS_LABELS = {'vodafone': 'VF', 'three': '3UK', 'o2': 'VMO2', 'ee': 'EE'}
# A sample whose first and last serving cells are of different classes.
CLASS_MIX = 'MIX'


# ---------------------------------------------------------------------------
# Serving Networks configuration
# ---------------------------------------------------------------------------
def default_serving_families(family: str) -> tuple[str, ...]:
    return DEFAULT_SERVING_FAMILIES.get(family, (family,) if family else ())


def normalise_serving_networks(document: Any) -> dict[str, Any]:
    """Validated Serving Networks: rows of an Operator and the networks that serve it, and the maximum distance."""
    document = document if isinstance(document, dict) else {}
    rows = []
    seen = set()
    for row in document.get('rows') or []:
        if not isinstance(row, dict):
            continue
        operator = str(row.get('operator') or '').strip()
        networks = [str(value).strip() for value in (row.get('networks') or []) if str(value).strip()]
        family = network_family(operator)
        if not operator or not networks or family in seen:
            continue
        seen.add(family)
        rows.append({'operator': operator, 'networks': list(dict.fromkeys(networks))})
    try:
        distance = float(document.get('max_distance_km') or DEFAULT_MAX_DISTANCE_KM)
    except (TypeError, ValueError):
        distance = DEFAULT_MAX_DISTANCE_KM
    if not math.isfinite(distance) or distance <= 0:
        distance = DEFAULT_MAX_DISTANCE_KM
    return {'max_distance_km': round(min(distance, 500.0), 3), 'rows': rows}


def parse_serving_networks_csv(text: str) -> list[dict[str, Any]]:
    """``Operator,Serving Networks`` rows (networks separated by ``;`` or ``|``) into Serving Networks rows."""
    rows = []
    for number, line in enumerate(str(text or '').splitlines(), start=1):
        if not line.strip():
            continue
        operator, _separator, networks = line.replace('\t', ',').partition(',')
        if number == 1 and operator.strip().casefold() == 'operator':
            continue
        values = [value.strip() for value in re.split(r'[;|,]', networks) if value.strip()]
        if not operator.strip() or not values:
            raise ValueError(f'Line {number}: write the Operator and at least one serving network, for example "3,3; Vodafone".')
        rows.append({'operator': operator.strip(), 'networks': values})
    return rows


def serving_networks_csv(rows: Iterable[dict[str, Any]]) -> str:
    lines = ['Operator,Serving Networks']
    lines.extend(f"{row['operator']},{'; '.join(row['networks'])}" for row in rows)
    return '\n'.join(lines) + '\n'


def load_serving_networks(repository: Any) -> dict[str, Any]:
    try:
        return normalise_serving_networks(json.loads(repository.get_workspace_state(SERVING_NETWORKS_STATE_KEY) or '{}'))
    except (TypeError, ValueError):
        return normalise_serving_networks({})


def save_serving_networks(repository: Any, document: dict[str, Any]) -> dict[str, Any]:
    normalised = normalise_serving_networks(document)
    repository.set_workspace_state(SERVING_NETWORKS_STATE_KEY, json.dumps(normalised, ensure_ascii=False))
    return normalised


def serving_families(operator: object, config: dict[str, Any] | None = None) -> tuple[str, ...]:
    """The network families allowed to serve an Operator, its own family first."""
    family = network_family(operator)
    for row in (config or {}).get('rows') or []:
        if network_family(row['operator']) == family:
            return tuple(dict.fromkeys(network_family(network) for network in row['networks'] if network_family(network)))
    return default_serving_families(family)


def effective_serving_rows(config: dict[str, Any], operators: Iterable[str]) -> list[dict[str, Any]]:
    """The configured rows plus the default ones of the other Operators, to show what applies."""
    rows = list(config.get('rows') or [])
    configured = {network_family(row['operator']) for row in rows}
    for operator in operators:
        family = network_family(operator)
        if family and family not in configured:
            configured.add(family)
            rows.append({'operator': operator, 'networks': [NETWORK_FAMILY_LABELS.get(value, value) for value in default_serving_families(family)],
                         'default': True})
    return rows


def serving_networks_editor(config: dict[str, Any], operators: Iterable[str],
                            inventory_networks: dict[str, str] | None = None) -> dict[str, Any]:
    """The Serving Networks editor: every Operator with its serving and default networks, and the networks to choose from.

    The networks are the known UK networks, those of the inventory snapshots and any one already serving an Operator.
    """
    labels = dict(NETWORK_FAMILY_LABELS)
    for family, label in (inventory_networks or {}).items():
        labels.setdefault(family, label)
    rows = []
    for row in effective_serving_rows(config, operators):
        family = network_family(row['operator'])
        networks = []
        for network in row['networks']:
            key = network_family(network)
            if key:
                labels.setdefault(key, str(network))
                networks.append(key)
        defaults = list(default_serving_families(family))
        for key in defaults:
            labels.setdefault(key, str(row['operator']))
        rows.append({'operator': str(row['operator']), 'networks': list(dict.fromkeys(networks)), 'defaults': defaults,
                     'configured': not row.get('default')})
    known = list(NETWORK_FAMILY_LABELS)
    order = sorted(labels, key=lambda key: (key not in known, known.index(key) if key in known else 0, labels[key].casefold()))
    return {'networks': [{'family': key, 'label': labels[key]} for key in order],
            'rows': sorted(rows, key=lambda row: row['operator'].casefold())}


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------
def cdr_reference_date(frame: pd.DataFrame, file_name: str = '', profile: CdrFieldProfile = NETCHECK_PROFILE) -> date | None:
    """When a CDR was measured: the median date of its samples, else the date in its file name."""
    column = _first_existing(frame, profile.time_columns)
    if column is not None:
        sample = frame[column].dropna()
        sample = sample.iloc[:: max(1, len(sample) // 5000)]
        parsed = pd.to_datetime(sample.astype(str), errors='coerce', utc=True, format='mixed')
        parsed = parsed.dropna()
        if len(parsed):
            return parsed.sort_values().iloc[len(parsed) // 2].date()
    inferred = infer_snapshot_date(file_name)
    return date.fromisoformat(inferred) if inferred else None


def complement_snapshots(snapshots: list[dict[str, Any]]) -> set[int]:
    """Beside a Multivendor Mapping, the dataset IDs of the other snapshots (VFUK and 3UK too), whatever their date: they only
    complete the cells the mappings do not have."""
    if not any(snapshot.get('kind') == MULTIVENDOR_MAPPING_KIND for snapshot in snapshots):
        return set()
    return {int(snapshot['dataset_id']) for snapshot in snapshots if snapshot.get('kind') != MULTIVENDOR_MAPPING_KIND}


def rank_snapshots(snapshots: list[dict[str, Any]], reference: date | None) -> dict[int, int]:
    """Snapshot dataset ID → preference rank: closest date to ``reference`` first, the newest on a tie, the snapshots that
    only complete a Multivendor Mapping last."""
    complements = complement_snapshots(snapshots)

    def key(snapshot: dict[str, Any]) -> tuple[bool, float, float]:
        try:
            moment = date.fromisoformat(str(snapshot['snapshot_date'])[:10])
        except ValueError:
            moment = date.min
        distance = abs((moment - reference).days) if reference else 0
        return int(snapshot['dataset_id']) in complements, distance, -moment.toordinal()
    ordered = sorted(snapshots, key=key)
    return {int(snapshot['dataset_id']): rank for rank, snapshot in enumerate(ordered)}


def _coordinates(frame: pd.DataFrame, pairs: Iterable[tuple[str, str]]) -> tuple[pd.Series, pd.Series]:
    for longitude, latitude in pairs:
        lon_column, lat_column = _first_existing(frame, [longitude]), _first_existing(frame, [latitude])
        if lon_column and lat_column:
            lon = pd.to_numeric(frame[lon_column], errors='coerce')
            lat = pd.to_numeric(frame[lat_column], errors='coerce')
            invalid = ~(lat.between(-90, 90) & lon.between(-180, 180)) | (lat.abs().lt(1e-6) & lon.abs().lt(1e-6))
            return lon.mask(invalid), lat.mask(invalid)
    empty = pd.Series(math.nan, index=frame.index, dtype='float64')
    return empty, empty


def _haversine_km(lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _candidate_cells(repository: Any, dataset_ids: list[int], families: list[str], identities: list[str]) -> pd.DataFrame:
    """The cells of the given snapshots and owner families whose identity is in ``identities``."""
    if not dataset_ids or not families or not identities:
        return pd.DataFrame()
    with repository.connection() as connection:
        connection.execute('CREATE TEMP TABLE IF NOT EXISTS serving_identities (identity TEXT PRIMARY KEY)')
        connection.execute('DELETE FROM serving_identities')
        connection.executemany('INSERT OR IGNORE INTO serving_identities VALUES (?)', ((value,) for value in identities))
        frame = pd.read_sql_query(
            ' UNION ALL '.join(
                f"SELECT c.dataset_id, c.cell_identity, c.technology, c.network, c.network_family, c.host_network, c.vendor, "
                f"c.site_id, c.emocn, c.latitude, c.longitude FROM {table} c "
                "JOIN serving_identities w ON w.identity = c.cell_identity "
                f"WHERE c.dataset_id IN ({', '.join('?' for _ in dataset_ids)}) "
                f"AND c.network_family IN ({', '.join('?' for _ in families)})"
                for table in (INVENTORY_CELLS_TABLE, MAPPING_CELLS_TABLE)),
            connection, params=[*dataset_ids, *families] * 2,
        )
        connection.execute('DROP TABLE IF EXISTS serving_identities')
    return frame


def serving_endpoints(frame: pd.DataFrame, dataset_kind: str, profile: CdrFieldProfile = NETCHECK_PROFILE) -> pd.DataFrame:
    """The first and last serving cell of every sample, with the position where each was measured."""
    cell_column = _first_existing(frame, profile.cell_columns)
    if not cell_column:
        raise ValueError('The selected CDR must contain a Cell ID field. Supported names include Cell_ID_A, Cell_IDs_A, Cell_ID, Global CI, GCID, GCI, CGI or ECI.')
    values = frame[cell_column].astype(object)
    parsed = {value: _split_global_cells(value) for value in pd.unique(values)}
    cells = values.map(parsed)
    start_lon, start_lat = _coordinates(frame, profile.start_coordinates.get(dataset_kind, ()))
    end_lon, end_lat = _coordinates(frame, profile.end_coordinates.get(dataset_kind, ()))
    end_lon, end_lat = end_lon.where(end_lon.notna(), start_lon), end_lat.where(end_lat.notna(), start_lat)
    positions = np.arange(len(frame))
    first = pd.DataFrame({'row': positions, 'end': 'first', 'cell': cells.map(lambda items: items[0] if items else '').to_numpy(),
                          'longitude': start_lon.to_numpy(), 'latitude': start_lat.to_numpy()})
    last = pd.DataFrame({'row': positions, 'end': 'last', 'cell': cells.map(lambda items: items[-1] if items else '').to_numpy(),
                         'longitude': end_lon.to_numpy(), 'latitude': end_lat.to_numpy()})
    endpoints = pd.concat([first, last], ignore_index=True)
    return endpoints.loc[endpoints['cell'].astype(str).str.fullmatch(r'\d+')].reset_index(drop=True)


def match_serving_cells(
    endpoints: pd.DataFrame, operators: pd.Series, candidates: pd.DataFrame, snapshot_ranks: dict[int, int],
    snapshot_dates: dict[int, str], config: dict[str, Any] | None, max_distance_km: float,
    excluded: Iterable[tuple[str, int]] = (), complements: Iterable[int] = (),
) -> pd.DataFrame:
    """The inventory cell chosen for every sample end: an allowed network (own first), the preferred snapshot,
    then the nearest cell; cells beyond ``max_distance_km`` of a located sample are never chosen, nor those of a
    snapshot that does not apply to the Operator (``excluded``: its Operator and dataset ID pairs). A snapshot of
    ``complements`` gives a cell only when no other has it, in any allowed network."""
    columns = ['row', 'end', 'vendor', 'network', 'host_network', 'site_id', 'emocn', 'distance_km', 'snapshot_date']
    if endpoints.empty or candidates.empty:
        return pd.DataFrame(columns=columns)
    operator_families = []
    for operator in pd.unique(operators):
        for rank, family in enumerate(serving_families(operator, config)):
            operator_families.append({'operator': operator, 'network_family': family, 'family_rank': rank})
    allowed = pd.DataFrame(operator_families, columns=['operator', 'network_family', 'family_rank'])
    sample_operators = pd.DataFrame({'row': np.arange(len(operators)), 'operator': operators.to_numpy()})
    matched = (endpoints.merge(sample_operators, on='row')
               .merge(allowed, on='operator')
               .merge(candidates.rename(columns={'cell_identity': 'cell', 'latitude': 'cell_latitude', 'longitude': 'cell_longitude'}),
                      on=['cell', 'network_family']))
    excluded = set(excluded)
    if excluded:
        matched = matched.loc[[pair not in excluded for pair in zip(matched['operator'], matched['dataset_id'])]]
    if matched.empty:
        return pd.DataFrame(columns=columns)
    matched['distance_km'] = _haversine_km(matched['longitude'].to_numpy(dtype=float), matched['latitude'].to_numpy(dtype=float),
                                           matched['cell_longitude'].to_numpy(dtype=float), matched['cell_latitude'].to_numpy(dtype=float))
    matched = matched.loc[~(matched['distance_km'] > max_distance_km)]
    matched['snapshot_rank'] = matched['dataset_id'].map(snapshot_ranks)
    matched['snapshot_date'] = matched['dataset_id'].map(snapshot_dates)
    matched['sort_distance'] = matched['distance_km'].fillna(np.inf)
    matched['complement'] = matched['dataset_id'].isin(set(complements))
    matched = matched.sort_values(['row', 'end', 'complement', 'family_rank', 'snapshot_rank', 'sort_distance'], kind='stable')
    return matched.drop_duplicates(['row', 'end'])[columns].reset_index(drop=True)


def serving_input_columns(columns: Iterable[str], dataset_kind: str, profile: CdrFieldProfile = NETCHECK_PROFILE) -> list[str]:
    """The columns of a CDR that ``assign_serving_vendors`` reads: its Operator, cells, positions and measurement times."""
    wanted = {'operator', *(name.casefold() for name in (*profile.cell_columns, *profile.time_columns))}
    for pairs in (profile.start_coordinates.get(dataset_kind, ()), profile.end_coordinates.get(dataset_kind, ())):
        wanted |= {name.casefold() for pair in pairs for name in pair}
    return [column for column in columns if str(column).casefold() in wanted]


def assign_serving_vendors(
    frame: pd.DataFrame, dataset_kind: str, repository: Any, inventory_dataset_ids: Iterable[int], *,
    file_name: str = '', config: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Operator_Vendor, Vendor and the serving-cell fields of every sample from the selected inventory snapshots."""
    operator_column = _first_existing(frame, ['operator', 'Operator'])
    if not operator_column:
        raise ValueError('The CDR must contain Operator to map Vendors.')
    config = config if config is not None else load_serving_networks(repository)
    profile = workspace_field_profile(repository)
    selected = {int(value) for value in inventory_dataset_ids}
    snapshots = [item for item in [*ensure_inventory_cells(repository), *ensure_mapping_cells(repository)] if item['dataset_id'] in selected]
    ranks = rank_snapshots(snapshots, cdr_reference_date(frame, file_name, profile))
    dates = {item['dataset_id']: item['snapshot_date'] for item in snapshots}
    result = frame.reset_index(drop=True).copy()
    operators = result[operator_column].fillna('').astype(str).str.strip()
    families = {operator: serving_families(operator, config) for operator in pd.unique(operators)}
    # Every snapshot gives each Operator its serving cell; beside Multivendor Mappings, only the Operators chosen for them
    # receive a Vendor (the others keep their name, as an Operator no snapshot serves).
    labels = operator_labels(repository)

    def identity(name: str) -> str:
        # Each Operator of the Operator Maps on its own (VF and VF SA); without them, the identity of its spellings.
        return labels.get(name.casefold(), name).casefold() if labels else operator_key(name)

    mappings = [item for item in snapshots if 'operators' in item]
    chosen = {identity(name) for item in mappings for name in item['operators']}
    available = {family for item in snapshots for family in item['families']}
    endpoints = serving_endpoints(result, dataset_kind, profile)
    wanted = sorted({family for values in families.values() for family in set(values) & available})
    candidates = _candidate_cells(repository, list(ranks), wanted, sorted(set(endpoints['cell'])))
    matches = match_serving_cells(endpoints, operators, candidates, ranks, dates, config,
                                  float(config.get('max_distance_km') or DEFAULT_MAX_DISTANCE_KM),
                                  complements=complement_snapshots(snapshots))
    first = matches.loc[matches['end'] == 'first'].set_index('row')
    last = matches.loc[matches['end'] == 'last'].set_index('row')
    first_vendor = first['vendor'].reindex(range(len(result)))
    last_vendor = last['vendor'].reindex(range(len(result)))
    mapped_operators = {operator for operator, values in families.items()
                        if set(values) & available and (not mappings or identity(operator) in chosen)}
    # Like the Vendor polygons, a sample none of whose cells is in the snapshots is Unknown: an Operator whose
    # inventory covers only part of its network (O2's cells hosted by Vodafone) would otherwise look Mixed.
    assigned = [
        (f'{_vendor_prefix(operator)}_{VENDOR_UNKNOWN}' if _text(start) is None and _text(end) is None
         else _vendor_from_ends(_vendor_prefix(operator), _text(start), _text(end))) if operator in mapped_operators
        else _normalise_operator(operator)
        for operator, start, end in zip(operators, first_vendor, last_vendor, strict=True)
    ]
    # The cell that served the start of the sample (its end when the start is unknown) describes it.
    serving = first.combine_first(last).reindex(range(len(result)))
    result = result.drop(columns=[column for column in SERVING_FIELDS if column in result.columns])
    result['Serving_Network'] = serving['network'].fillna('').to_numpy()
    result['Serving_Host_Network'] = serving['host_network'].fillna('').to_numpy()
    result['Serving_Site_ID'] = serving['site_id'].fillna('').to_numpy()
    result['Serving_eMOCN_Scenario'] = serving['emocn'].fillna('').to_numpy()
    result['Serving_Distance_km'] = serving['distance_km'].round(3).to_numpy()
    result['Serving_Inventory_Snapshot'] = serving['snapshot_date'].fillna('').to_numpy()
    # The RAN Vendor (only for the Operators that receive a Vendor) and the site type of both ends of the sample.
    first_ran, first_site = _end_classes(first, len(result))
    last_ran, last_site = _end_classes(last, len(result))
    result['Serving_RAN_Vendor'] = np.where(operators.isin(mapped_operators).to_numpy(), classes_from_ends(first_ran, last_ran), '')
    result['Serving_Site_Class'] = classes_from_ends(first_site, last_site)
    return _with_vendor_columns(result, operator_column, assigned)


def network_class_label(network: object) -> str:
    """The short name of a network in the RAN Vendor and site type classes: VF, 3UK, VMO2, EE or its own name."""
    text = str(network or '').strip()
    return NETWORK_CLASS_LABELS.get(network_family(text), text)


def ran_vendor_class(host: object, vendor: object) -> str:
    """The RAN Vendor of a serving cell with the network that hosts it (VF_Hosted_Ericsson, VMO2_Hosted_Nokia); empty
    without a Vendor."""
    vendor_text, host_text = _text(vendor), _text(host)
    if vendor_text is None:
        return ''
    return f'{network_class_label(host_text)}_Hosted_{vendor_text}' if host_text else vendor_text


def site_class(network: object, scenario: object) -> str:
    """The site type of a serving cell from its network and eMOCN scenario: <network>_NNS, <network>_eMOCN_<code> (S0,
    S1, S12, S0_CWP… as the inventory names them) or <network>_Legacy without a code; empty without a network."""
    network_text = _text(network)
    if network_text is None:
        return ''
    label, code = network_class_label(network_text), _text(scenario)
    if code is None:
        return f'{label}_Legacy'
    return f'{label}_NNS' if code.casefold() == 'nns' else f'{label}_eMOCN_{code}'


def _end_classes(end: pd.DataFrame, rows: int) -> tuple[pd.Series, pd.Series]:
    """The RAN Vendor and the site type (see ran_vendor_class and site_class) of the cell at one end of every sample,
    empty where no cell matched."""
    cells = end.reindex(range(rows)).reindex(columns=['vendor', 'network', 'host_network', 'emocn'])
    cells = cells.fillna('').astype(str).apply(lambda column: column.str.strip())
    labels = {value: network_class_label(value) for value in pd.unique(pd.concat([cells['network'], cells['host_network']]))}
    host, network, vendor, code = cells['host_network'].map(labels), cells['network'].map(labels), cells['vendor'], cells['emocn']
    ran = (host + '_Hosted_' + vendor).where(host != '', vendor).where(vendor != '', '')
    site = (network + '_eMOCN_' + code).where(code != '', network + '_Legacy')
    site = site.where(code.str.casefold() != 'nns', network + '_NNS').where(network != '', '')
    return ran, site


def classes_from_ends(first: Iterable[str], last: Iterable[str]) -> np.ndarray:
    """The class of every sample from those of its first and last serving cells, as the Vendor: the same class at
    both ends, else MIX (one end without a cell included); empty when neither end has a cell."""
    first_values, last_values = np.asarray(list(first), dtype=object), np.asarray(list(last), dtype=object)
    return np.where((first_values == '') & (last_values == ''), '',
                    np.where(first_values == last_values, first_values, CLASS_MIX)).astype(object)


def _text(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def operator_labels(repository: Any) -> dict[str, str]:
    """Every spelling of each Operator of the Operator Maps (in lower case), to its name there."""
    labels: dict[str, str] = {}
    for group in repository.list_operator_mapping_groups():
        canonical = str(group.get('canonical') or '').strip()
        for value in [canonical, *(group.get('aliases') or [])]:
            if canonical and str(value or '').strip():
                labels[str(value).strip().casefold()] = canonical
    return labels


def suggest_mapping_operators(repository: Any, families: Iterable[str], operators: Iterable[str], config: dict[str, Any] | None = None) -> list[str]:
    """The ``operators`` offered in the workspace that the networks of a Multivendor Mapping serve (see Serving Networks)."""
    config = config if config is not None else load_serving_networks(repository)
    families = {family for family in families if family}
    return [name for name in operators if families & set(serving_families(name, config))]


def vendor_mapping_signature(repository: Any, config: dict[str, Any] | None = None, inventory_ids: Iterable[int] = ()) -> str:
    """What a Vendor mapping depends on: the rule version, the Serving Networks and every snapshot it can read. With
    Multivendor Mappings in the workspace, a Network Inventory counts only if the CDR was mapped with it (``inventory_ids``).

    A CDR mapped under another signature shows that its Vendor may be outdated.
    """
    config = config if config is not None else load_serving_networks(repository)
    parts = [str(SERVING_ENGINE_VERSION), json.dumps(config, sort_keys=True)]
    mappings = mapping_datasets(repository)
    chosen = {int(value) for value in inventory_ids}
    sources = [*mappings, *(row for row in inventory_datasets(repository)
                            if not mappings or str(row['dataset_kind'] or '') != 'network_inventory' or int(row['id']) in chosen)]
    parts.extend(sorted(f"{row['id']}:{dataset_revision(row)}:{effective_snapshot_date(row)}" for row in sources))
    if mappings:
        # Since v0.12.0 the Operators of the Multivendor Mappings are the only ones that receive a Vendor (ticket #80).
        parts.append('vendor-for-mapping-operators-only')
        parts.extend(sorted(f"{row['id']}:{row['mapping_operators']}" for row in mappings))
    return hashlib.sha256('\n'.join(parts).encode('utf-8')).hexdigest()[:16]
