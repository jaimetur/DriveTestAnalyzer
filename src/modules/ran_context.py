"""The radio access network around a Non-Qualified Call, from the Network Inventory.

For each call: the inventory cell each cell of the call was (the networks serving its operator, its own first, the
nearest to where it served the call), the site that served its end and how far it was, the local inter-site distance
(ISD) of the sites, the nearest site in service of those networks, the cells around with the PCI and channel of a cell
of the call, the cells out of service on its sites and its ping-pong handovers.

The Map of a call (nq_call_map) shows them and the DT Analyzer RCA (nq_dta_rca) reads them with the same criteria:
whether a call was served from too far away (overshooting) or where no cell covers it (a coverage hole) depends on the
ISD of the sites around, not on a fixed distance, as a rural or road site serves farther than an urban one.
"""

from __future__ import annotations

import math
import threading
from collections import OrderedDict
from typing import Any, Iterable

import numpy as np
import pandas as pd

from src.modules.nq_call_map import OUTAGE_STATES, _distances, _number, _position, _site_id, _text, distance_km

# The local inter-site distance of a site: the mean distance to this many nearest sites in service of its network.
ISD_SITES = 3
# A call is served from too far away (overshooting) from this many times the ISD of the serving site, and this far.
OVERSHOOT_ISD = 2.0
OVERSHOOT_MIN_KM = 1.0
# A call is in a coverage hole when the nearest site of its networks is this many times the ISD of that site away.
HOLE_ISD = 1.5
# The nearest site was not the serving one when it was this share of the serving distance or less (a missing neighbour).
NEARER_SHARE = 1 / 3
# The cells around with the PCI and channel of a cell of the call, this close to where it failed.
PCI_RADIUS_KM = 2.0
# Sites are looked for in squares of this side, and no farther than this.
_GRID_KM = 2.0
_SEARCH_KM = 40.0
# The indexes of the inventories in use (one per cell selection), each one built once.
_CACHED = 2
_cache: OrderedDict[int, tuple[pd.DataFrame, RanIndex]] = OrderedDict()
_cache_lock = threading.Lock()


def _clean_number(value: Any) -> str:
    return _text(value).removesuffix('.0')


class _Grid:
    """Sites of one network in squares of _GRID_KM, to find the nearest ones to a point."""

    def __init__(self, keys: list[str], latitudes: np.ndarray, longitudes: np.ndarray) -> None:
        self.keys = keys
        self.latitudes = latitudes
        self.longitudes = longitudes
        self.reference = float(np.median(latitudes)) if len(latitudes) else 0.0
        self.squares: dict[tuple[int, int], list[int]] = {}
        for index, square in enumerate(zip(*self._squares(latitudes, longitudes), strict=True)):
            self.squares.setdefault(square, []).append(index)

    def _squares(self, latitudes: Any, longitudes: Any) -> tuple[np.ndarray, np.ndarray]:
        x = np.asarray(longitudes, dtype=float) * 111.320 * math.cos(math.radians(self.reference)) / _GRID_KM
        y = np.asarray(latitudes, dtype=float) * 110.574 / _GRID_KM
        return np.floor(x).astype(int), np.floor(y).astype(int)

    def nearest(self, point: tuple[float, float], count: int, skip: int | None = None) -> list[tuple[float, int]]:
        """The ``count`` nearest sites to ``point`` (distance in km, index), nearest first, ``skip`` left out."""
        if not self.keys:
            return []
        x, y = (int(value[0]) for value in self._squares([point[0]], [point[1]]))
        found: list[tuple[float, int]] = []
        for ring in range(int(_SEARCH_KM / _GRID_KM) + 1):
            indices = [index for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1)
                       if max(abs(dx), abs(dy)) == ring for index in self.squares.get((x + dx, y + dy), ()) if index != skip]
            if indices:
                chosen = np.asarray(indices)
                distances = _distances(self.latitudes[chosen], self.longitudes[chosen], point)
                found.extend(zip(distances.tolist(), indices, strict=True))
                found.sort()
                found = found[:count]
            # Every site beyond this ring is farther than the squares searched (a margin for the latitudes of the network).
            if len(found) >= count and found[-1][0] <= .8 * (ring - 1) * _GRID_KM:
                break
        return [item for item in found if item[0] <= _SEARCH_KM]


class RanIndex:
    """The sites and cells of the inventory cells of ``load_cells`` (see inventory_insights), indexed for the questions
    asked about each call."""

    def __init__(self, cells: pd.DataFrame) -> None:
        self.sites: dict[str, dict[str, Any]] = {}
        self._grids: dict[str, _Grid] = {}
        self._joined: dict[tuple[str, ...], _Grid] = {}
        self._positions: dict[str, int] = {}
        self._isd: dict[str, float | None] = {}
        self._identities: dict[str, list[tuple[Any, ...]]] = {}
        self._pcis: dict[tuple[str, str, str], list[tuple[str, float, float]]] = {}
        self._outages: dict[str, int] = {}
        self._frame: pd.DataFrame | None = None
        self._cells_lock = threading.Lock()
        if cells is None or cells.empty:
            return
        frame = self._frame = cells.reset_index(drop=True)
        keys = (frame['network_family'].astype(str) + '|' + frame['site_id'].astype(str)).str.casefold()
        states = frame['state'].fillna('').astype(str) if 'state' in frame else pd.Series('', index=frame.index)
        in_service = frame['in_service'].astype(bool) if 'in_service' in frame else pd.Series(True, index=frame.index)
        located = frame['latitude'].notna() & frame['longitude'].notna()
        # The sites in service: where their cells are (the median), by network.
        live = frame.loc[in_service & located].assign(_site=keys[in_service & located])
        for family, part in live.groupby('network_family', sort=False):
            grouped = part.groupby('_site', sort=False)
            medians = grouped[['latitude', 'longitude']].median()
            firsts = grouped[['site_id', 'network', 'host_network']].first()
            site_keys = [str(key) for key in medians.index]
            for position, key in enumerate(site_keys):
                self.sites[key] = {'key': key, 'site_id': _text(firsts.at[key, 'site_id']), 'network': _text(firsts.at[key, 'network']),
                                   'host_network': _text(firsts.at[key, 'host_network']), 'family': str(family),
                                   'latitude': float(medians.at[key, 'latitude']), 'longitude': float(medians.at[key, 'longitude'])}
                self._positions[key] = position
            self._grids[str(family)] = _Grid(site_keys, medians['latitude'].to_numpy(dtype=float), medians['longitude'].to_numpy(dtype=float))

    def _index_cells(self) -> None:
        """Every cell by its identity (as resolve_trace of the Map finds them), the drawn cells by PCI and channel and the
        cells out of service by site, indexed the first time they are asked for (the Map only asks for the sites)."""
        with self._cells_lock:
            if self._frame is None:
                return
            frame = self._frame
            keys = (frame['network_family'].astype(str) + '|' + frame['site_id'].astype(str)).str.casefold()
            states = frame['state'].fillna('').astype(str) if 'state' in frame else pd.Series('', index=frame.index)
            in_service = frame['in_service'].astype(bool) if 'in_service' in frame else pd.Series(True, index=frame.index)
            located = frame['latitude'].notna() & frame['longitude'].notna()
            drawn = in_service | states.isin(('In progress', 'Planned'))
            columns = zip(frame['cell_identity'].astype(str), frame['network_family'].astype(str), frame['technology'].astype(str), keys,
                          frame['latitude'], frame['longitude'], frame['pci'], frame['channel'], frame['site_id'], frame['network'],
                          frame['host_network'], drawn, located, states, strict=True)
            for identity, family, technology, key, latitude, longitude, pci, channel, site, network, host, shown, placed, state in columns:
                pci, channel = _clean_number(pci), _clean_number(channel)
                self._identities.setdefault(identity, []).append(
                    (family, technology, key, _number(latitude), _number(longitude), pci, channel, _text(site), _text(network), _text(host)))
                if shown and placed and pci and channel:
                    self._pcis.setdefault((technology, pci, channel), []).append((identity, float(latitude), float(longitude)))
                if state in OUTAGE_STATES:
                    self._outages[key] = self._outages.get(key, 0) + 1
            self._frame = None

    def isd(self, key: str) -> float | None:
        """The local inter-site distance of a site in service: the mean distance to its ISD_SITES nearest sites of its
        network (km), None when no other site is within _SEARCH_KM."""
        if key in self._isd:
            return self._isd[key]
        site = self.sites.get(key)
        value = None
        if site is not None:
            nearest = self._grids[site['family']].nearest((site['latitude'], site['longitude']), ISD_SITES, skip=self._positions[key])
            value = round(sum(distance for distance, _index in nearest) / len(nearest), 3) if nearest else None
        self._isd[key] = value
        return value

    def nearest(self, point: tuple[float, float] | None, families: Iterable[str]) -> dict[str, Any] | None:
        """The nearest site in service of ``families`` to ``point``, with its distance (km)."""
        if point is None:
            return None
        families = tuple(families)
        grid = self._joined.get(families)
        if grid is None:
            # The sites of every network serving the operator in one grid, built once per set of networks.
            keys = [key for family in families if family in self._grids for key in self._grids[family].keys]
            grid = self._joined[families] = _Grid(keys, np.asarray([self.sites[key]['latitude'] for key in keys], dtype=float),
                                                  np.asarray([self.sites[key]['longitude'] for key in keys], dtype=float))
        found = grid.nearest(point, 1)
        if not found:
            return None
        return {**self.sites[grid.keys[found[0][1]]], 'distance_km': round(found[0][0], 3)}

    def resolve(self, cell: str, technology: str, families: tuple[str, ...], where: tuple[float, float] | None,
                max_distance_km: float) -> dict[str, Any] | None:
        """The inventory cell a cell of the call was: of the first network of ``families`` that has it, the nearest to
        ``where`` within ``max_distance_km`` (one without position when none is placed); the same choice as the Map."""
        self._index_cells()
        found = self._identities.get(str(cell), ())
        if technology in {'LTE', 'NR'}:
            found = [item for item in found if item[1] == technology]
        for family in families:
            best = None
            for item in found:
                if item[0] != family:
                    continue
                position = _position(item[3], item[4])
                distance = distance_km(where, position) if where and position else None
                if distance is not None and distance > max_distance_km:
                    continue
                rank = math.inf if distance is None else distance
                if best is None or rank < best[0]:
                    best = (rank, item, distance)
            if best is not None:
                _rank, item, distance = best
                return {'site': item[2], 'site_id': item[7], 'network': item[8], 'host_network': item[9], 'technology': item[1],
                        'pci': item[5], 'channel': item[6], 'latitude': item[3], 'longitude': item[4],
                        'distance_km': None if distance is None else round(distance, 3)}
        return None

    def pci_collisions(self, steps: list[dict[str, Any]], point: tuple[float, float] | None, radius_km: float) -> int:
        """The cells within ``radius_km`` of ``point`` with the technology, PCI and channel of a cell of the call (other
        than that cell)."""
        if point is None:
            return 0
        self._index_cells()
        found = set()
        for step in steps:
            pci, channel = _clean_number(step.get('pci')), _clean_number(step.get('channel'))
            if not pci or not channel:
                continue
            for identity, latitude, longitude in self._pcis.get((step.get('technology') or '', pci, channel), ()):
                if identity != str(step.get('cell') or '') and distance_km(point, (latitude, longitude)) <= radius_km:
                    found.add((identity, latitude, longitude))
        return len(found)

    def out_of_service(self, sites: Iterable[str]) -> int:
        """The cells Locked, Halted or Disabled on ``sites``."""
        self._index_cells()
        return sum(self._outages.get(key, 0) for key in set(sites))


def ran_index(cells: pd.DataFrame) -> RanIndex:
    """The index of the cells ``load_cells`` gives (the same frame for the same inventories), built once."""
    key = id(cells)
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] is cells:
            _cache.move_to_end(key)
            return cached[1]
    index = RanIndex(cells)
    with _cache_lock:
        # The frame is kept with its index, so its id stays its own.
        _cache[key] = (cells, index)
        while len(_cache) > _CACHED:
            _cache.popitem(last=False)
    return index


def ping_pongs(cells: list[str]) -> list[tuple[str, str]]:
    """Each time the call went back to a cell right after leaving it (A → B → A): the two cells."""
    return [(cells[index], cells[index + 1]) for index in range(len(cells) - 2)
            if cells[index] and cells[index] == cells[index + 2] and cells[index] != cells[index + 1]]


def serving_isd_ratio(distance: float | None, isd: float | None) -> float | None:
    """How many times the ISD of its site the serving site was from the call."""
    return round(distance / isd, 2) if distance is not None and isd else None


def call_context(index: RanIndex, families: tuple[str, ...], steps: list[dict[str, Any]], start: tuple[float, float] | None,
                 end: tuple[float, float] | None, max_distance_km: float) -> dict[str, Any]:
    """What the DT Analyzer RCA reads of the network around a call: the serving distance and the ISD of the serving site,
    the nearest site and its ISD, the PCI collisions around, the cells out of service on its sites, and a note naming the
    serving and nearest sites for the evidence. ``steps`` are the cells of the call (nq_call_map.trace_cells)."""
    where = end or start
    resolved = []
    count = len(steps)
    for position, step in enumerate(steps):
        role = 'both' if count == 1 else 'start' if position == 0 else 'end' if position == count - 1 else 'handover'
        found = index.resolve(step['cell'], step.get('technology', ''), families,
                              start if role == 'start' and start else where, max_distance_km)
        resolved.append({**step, 'role': role, **({**found, 'pci': step.get('pci') or found['pci'],
                                                   'channel': step.get('channel') or found['channel']} if found else {'site': None})})
    values: dict[str, Any] = {}
    serving = next((step for step in reversed(resolved) if step.get('site') and step['role'] in ('end', 'both')), None)
    notes = []
    if serving is not None and serving.get('distance_km') is not None:
        isd = index.isd(serving['site'])
        values.update({'serving_distance': serving['distance_km'], 'serving_isd': isd,
                       'serving_isd_ratio': serving_isd_ratio(serving['distance_km'], isd)})
        notes.append(f"served from Site {serving['site_id']} ({serving['network']}) at {serving['distance_km']:.2f} km"
                     + (f", {values['serving_isd_ratio']:.1f} × its ISD of {isd:.2f} km" if isd else ''))
    nearest = index.nearest(where, families)
    if nearest is not None:
        isd = index.isd(nearest['key'])
        values.update({'nearest_site_distance': nearest['distance_km'],
                       'nearest_site_isd_ratio': serving_isd_ratio(nearest['distance_km'], isd)})
        if serving is None or nearest['key'] != serving['site']:
            notes.append(f"nearest site {nearest['site_id']} ({nearest['network']}) at {nearest['distance_km']:.2f} km"
                         + (f", ISD {isd:.2f} km" if isd else ''))
    if index.sites:
        values['pci_collisions'] = index.pci_collisions(resolved, where, PCI_RADIUS_KM)
        values['cells_out_of_service'] = index.out_of_service(step['site'] for step in resolved if step.get('site'))
    if notes:
        values['network_note'] = 'Network Inventory: ' + '; '.join(notes)
    return values
