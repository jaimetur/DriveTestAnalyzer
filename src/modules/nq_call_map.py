"""The map of a Non-Qualified Call: where it failed and what surrounds it, for its analysis and troubleshooting.

Around the place where the call failed (where it ended, else where it started) the map gathers:

- the call: where it started and ended, its radio values (RSRP, RSRQ, SINR, transmit power, handovers...) and the cells
  it went through (its Cell ID trace), placed at their inventory sites, and the NR cell of an NSA call found by its PCI;
- the inventory sites of the networks that serve its operator (Serving Networks) around it, with their cells (azimuth,
  beamwidth, band, channel, PCI and state); the cells with the PCI and channel of a cell of the call are flagged;
- the other Non-Qualified Calls around it, of every operator and campaign: those of its operator at the same place (its
  repetitions) and those of its hotspot, cluster and time-window issue are marked, with the shapes of its groups and the
  hotspot zone they make (``group_rings``); the page shows those of the campaigns of ``TEST_SCOPES``;
- the tests of the CDRs of the campaigns chosen in the filters of the page (every campaign while none is chosen) or of
  the campaign of the call (``TEST_SCOPES``, chosen in the page for everything the map draws from the CDRs) around it,
  completed or not, with their LTE and NR RSRP and SINR and the campaign of their CDR: the radio conditions of the area;
- what it all suggests (``diagnosis``: coverage, interference, serving distance, PCI, cell states, the other operators,
  repetition and handovers), the root causes already decided for the calls at its place (``decisions``), the tests of its
  drive in the minutes around it (``drive``) and the NQ rate of its serving site per campaign (``site_health``).

The tests of a CDR are read once and kept in memory for the next calls of the same CDR.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, OrderedDict
from threading import Lock
from typing import Any, Callable

import numpy as np
import pandas as pd

from src.modules import cdr_store, workspace_cache
from src.modules.cdr_field_profiles import NETCHECK_PROFILE, CdrFieldProfile, workspace_field_profile

# The radii offered. A call opens with the radius that holds every NQ call of its hotspot and its cluster (in tenths of a
# km, see ``group_radius``), else with the default one.
RADII_KM = (0.5, 1.0, 2.0, 5.0, 10.0)
DEFAULT_RADIUS_KM = 1.0
# The CDRs of the RSRP / SINR samples and of the drive around a call, as for its NQ calls: those of the campaigns chosen in
# the filters of the page (every campaign while none is chosen), or of the campaign of the call.
TEST_SCOPES = {'selected': 'Selected campaigns', 'campaign': 'Call campaign'}
DEFAULT_TEST_SCOPE = 'selected'
# What one map draws at most: the nearest first. Every NQ call of the campaign of the call within the radius (and of its
# groups and its site) is drawn, and at most MAX_FAILURES of the other campaigns.
MAX_TESTS = 6000
MAX_FAILURES = 600
MAX_SITES = 300
# The NR cell of an NSA call is looked for by its PCI this far from where it failed.
NR_LEG_KM = 5.0
# CDRs whose tests are kept in memory (a large Data CDR takes about 15 MB).
CACHED_CDRS = 6
# The radio columns of the CDR row of a call shown with it (RSRP, SINR, handovers, cells...).
RADIO_COLUMN = re.compile(
    r'RSRP|RSRQ|SINR|SNR|RxLev|RSCP|EcNo|Ec_No|TxPower|BLER|CQI|Handover|PCI|ARFCN|BAND|Speed|Rank_Index|MIMO|'
    r'RAT_Timeline|^Technology$|technology_primary|^LAC|Cell_ID|Serving_|latency_ms', re.I)
RADIO_STATISTIC = re.compile(r'^(?P<base>.+?)_(?P<statistic>Min|Avg|Max|Median)(?P<side>_[AB])?$', re.I)
MAX_RADIO_ROWS = 80
# The cell trace and the PCI of each cell of it, per CDR type (Voice uses the measuring A side).
# The PCIs and NR channel of the cells of a NetCheck call (every CDR type lists its own, see cdr_field_profiles).
PCI_COLUMNS = NETCHECK_PROFILE.pci_columns
NR_PCI_COLUMNS = NETCHECK_PROFILE.rf_field_aliases['nr_pci']
NR_CHANNEL_COLUMNS = NETCHECK_PROFILE.rf_field_aliases['nr_arfcn']
CELL_ROLES = {'start': 'Served the start', 'handover': 'Handover', 'end': 'Served the end', 'both': 'Served the whole call',
              'nr_leg': 'NR leg (by PCI)'}
# The diagnosis judges the serving distance and coverage holes by the inter-site distance (ISD) of the sites (ran_context);
# a site without others of its network around (no ISD) is judged by these distances: a cell this far serves from too far
# away (the overshooting distance of Network Insights), one this far while a site three times nearer was there was not
# the right one. Operators are compared with at least this many tests each.
OVERSHOOT_KM = 5.0
FAR_SERVING_KM = 1.5
MIN_COMPARED_TESTS = 5
# Its operator fails significantly more than the others from this z of a two-proportion test, at least this many times and
# points above them; every operator fails where the others do not complete this share of their tests (about five times the
# usual share of a network).
SIGNIFICANT_Z = 2.0
HINT_Z = 1.3
WORSE_RATIO = 1.5
WORSE_POINTS = .02
PLACE_FAILURES = .05
MANY_HANDOVERS = 4
# Ping-pong: handovers back to a cell the call had left, within this distance travelled, tell that no cell dominates there.
PING_PONG_METRES = 500
# The way of the car: a test of its drive follows the one before it only if a car could have driven between them (a speed of
# at most about 145 km/h, with a margin for the positions).
CAR_SPEED_MS, ROUTE_SLACK_M = 40.0, 300.0
OUTAGE_STATES = ('Locked', 'Halted', 'Disabled')
PIPELINE_STATES = ('In progress', 'Planned')
# The drive around the call: the tests of its operator this many minutes before and after it, this close.
DRIVE_MINUTES = 15
DRIVE_KM = 30.0
MAX_DRIVE_ROWS = 40
OSM_TILES = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
OSM_ATTRIBUTION = '© OpenStreetMap contributors'

_tests_cache: OrderedDict[tuple[str, int, str], dict[str, Any]] = OrderedDict()
_tests_guard = Lock()
_tests_locks: dict[tuple[str, int], Lock] = {}
# The campaign and NR Mode of each CDR by the version of its indexed calls (see _cdr_profiles).
_profiles_cache: dict[tuple[str, int], tuple[tuple[str, str], dict[str, Any] | None]] = {}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ''
    text = str(value).strip()
    return '' if text.casefold() in {'nan', 'none', '<na>'} else text


def _position(latitude: Any, longitude: Any) -> tuple[float, float] | None:
    lat, lon = _number(latitude), _number(longitude)
    if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180 or (abs(lat) < 1e-6 and abs(lon) < 1e-6):
        return None
    return lat, lon


def _seconds(values: Any) -> np.ndarray:
    """The moments of CDR times (``2026-09-07 13:59:56``) as seconds, NaN when a value is not a time."""
    moments = pd.to_datetime(pd.Series(values).astype(str).str.slice(0, 19).str.replace('T', ' '), errors='coerce', format='mixed')
    return np.where(moments.isna(), np.nan, moments.astype('int64', errors='ignore').astype('float64') / 1e9)


def _km(value: float | None) -> str:
    if value is None:
        return ''
    return f'{round(value * 1000)} m' if value < 1 else f'{value:.1f} km'


def distance_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*first, *second))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(value)))


def _bearing(first: tuple[float, float], second: tuple[float, float]) -> float:
    """The bearing (degrees from north, clockwise) from ``first`` to ``second``."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*first, *second))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _distances(latitudes: np.ndarray, longitudes: np.ndarray, centre: tuple[float, float]) -> np.ndarray:
    lat1, lon1 = math.radians(centre[0]), math.radians(centre[1])
    lat2, lon2 = np.radians(latitudes.astype(float)), np.radians(longitudes.astype(float))
    value = np.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(value, 0, 1)))


def bounding_box(centre: tuple[float, float], radius_km: float) -> tuple[float, float, float, float]:
    """South, north, west and east of a square around ``centre`` that holds the circle of ``radius_km``."""
    latitude_span = radius_km / 110.574
    longitude_span = radius_km / (111.320 * max(0.01, math.cos(math.radians(centre[0]))))
    return centre[0] - latitude_span, centre[0] + latitude_span, centre[1] - longitude_span, centre[1] + longitude_span


def normalise_radius(value: Any) -> float:
    """A radius offered, or one between them in tenths of a km (that of the groups of a call); else the default one."""
    number = _number(value)
    if number is None or not RADII_KM[0] <= number <= RADII_KM[-1]:
        return DEFAULT_RADIUS_KM
    return number if number in RADII_KM else math.ceil(round(number * 10, 6)) / 10


def group_radius(repository: Any, call: dict[str, Any], centre: tuple[float, float]) -> float | None:
    """The radius around ``centre`` that holds every NQ call of the hotspot and of the cluster of a call (of 2 calls or more),
    in tenths of a km between the smallest and the largest radius offered; None for a call in neither."""
    from src.modules import non_qualified_calls as nq
    from src.modules.nq_prioritization import PRIORITY_TABLE

    with repository.connection() as connection:
        own = connection.execute(f'SELECT cluster_key, cluster_size, repeat_key, repeat_size FROM {PRIORITY_TABLE} WHERE call_key = ?',
                                 (call.get('parent_key') or call['call_key'],)).fetchone()
        groups = [(column, _text(own[column])) for column, size in (('cluster_key', 'cluster_size'), ('repeat_key', 'repeat_size'))
                  if own and _text(own[column]) and (own[size] or 0) >= 2]
        if not groups:
            return None
        rows = connection.execute(
            f'SELECT l.latitude, l.longitude FROM {PRIORITY_TABLE} q JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = q.call_key '
            f'WHERE {" OR ".join(f"q.{column} = ?" for column, _ in groups)}', [value for _, value in groups]).fetchall()
    farthest = max((distance_km(centre, position) for row in rows if (position := _position(row['latitude'], row['longitude']))), default=0.0)
    return min(RADII_KM[-1], max(RADII_KM[0], math.ceil(round(farthest * 10, 6)) / 10))


def _first_value(row: dict[str, Any], columns: list[str], candidates: tuple[str, ...]) -> tuple[str, Any]:
    """The first candidate column of the row with a value: its name and value."""
    from src.modules.non_qualified_calls import _resolve_columns

    for column in _resolve_columns(columns, candidates):
        if _text(row.get(column)):
            return column, row[column]
    return '', None


def _sequence_numbers(value: Any) -> list[str]:
    """The first number of each element of an ``[a]->[b]`` sequence ('' for an element without one)."""
    from src.modules.network_insights import sequence_values

    found = []
    for item in sequence_values(value):
        match = re.search(r'\d+', item)
        found.append(match.group(0) if match else '')
    return found


# ---------------------------------------------------------------------------
# The call: its places, radio values and cells
# ---------------------------------------------------------------------------
def call_positions(service: str, row: dict[str, Any], columns: list[str],
                   profile: CdrFieldProfile = NETCHECK_PROFILE) -> dict[str, Any]:
    """Where the call started and ended (Voice records both; the other CDR types where the test or sample started)."""
    def first(pairs):
        for longitude, latitude in pairs:
            _column, lon = _first_value(row, columns, (longitude,))
            _column, lat = _first_value(row, columns, (latitude,))
            found = _position(lat, lon)
            if found:
                return found
        return None

    start = first(profile.start_coordinates.get(service, ()))
    end = first(profile.end_coordinates.get(service, ()))
    return {'start': start, 'end': end}


def radio_values(row: dict[str, Any], columns: list[str]) -> list[dict[str, Any]]:
    """The radio columns of the CDR row with a value, in their CDR order: the Min / Avg / Max of a measure together."""
    rows: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, Any]] = {}
    for column in columns:
        value = _text(row.get(column))
        if not value or not RADIO_COLUMN.search(column):
            continue
        match = RADIO_STATISTIC.match(column)
        if match:
            side = (match.group('side') or '').lstrip('_').upper()
            name = match.group('base').replace('_', ' ') + (f' ({side})' if side else '')
            entry = grouped.get(name)
            if entry is None:
                entry = grouped[name] = {'name': name, 'min': '', 'avg': '', 'max': '', 'median': ''}
                rows.append(entry)
            entry[match.group('statistic').lower()] = value
        else:
            rows.append({'name': column.replace('_', ' '), 'value': value})
    return rows[:MAX_RADIO_ROWS]


def cell_trace(service: str, row: dict[str, Any], columns: list[str], cell_id: Any,
               profile: CdrFieldProfile = NETCHECK_PROFILE) -> list[dict[str, str]]:
    """The cells the call went through, in order: technology, band, cell identity, channel and PCI."""
    _column, trace = _first_value(row, columns, profile.rf_field_aliases['cell_trace'].get(service, ()))
    _column, pcis = _first_value(row, columns, profile.pci_columns.get(service, ()))
    return trace_cells(trace, pcis, cell_id)


def _same_cell(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Whether two steps of a call are the same cell: the same technology and identity, and neither another channel nor
    another PCI (its area may change, such as a new TAC)."""
    return (bool(first.get('cell')) and first.get('cell') == second.get('cell') and first.get('technology') == second.get('technology')
            and all(not first.get(key) or not second.get(key) or first[key] == second[key] for key in ('channel', 'pci')))


def merged_repeats(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The cells of a call with a cell repeated in a row once, as the PCI and Cell ID columns of the CDR give them: neither a
    new area (TAC / LAC) nor a moment on a cell without identity it came back from
    (``[LTE E-UTRA 7, 41061, 6468370, 2850]->[5G NR Unknown, , , 641376]->[LTE E-UTRA 7, , 6468370, 2850]``) is a
    handover. The step kept takes the values its repeats give and it lacks."""
    known = [index for index, step in enumerate(steps) if step.get('cell')]
    merged: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if not step.get('cell'):
            before = next((steps[other] for other in reversed(known) if other < index), None)
            after = next((steps[other] for other in known if other > index), None)
            if before is not None and after is not None and _same_cell(before, after):
                continue
        if merged and _same_cell(merged[-1], step):
            merged[-1].update({key: value for key, value in step.items() if value and not merged[-1].get(key)})
            continue
        merged.append(dict(step))
    return merged


def trace_cells(trace: Any, pcis: Any, cell_id: Any) -> list[dict[str, str]]:
    """The cells of a cell trace of the CDR (``[LTE E-UTRA 20, TAC, ECI, EARFCN]->[...]``), else of the cell identities of
    the call, a cell repeated in a row once (merged_repeats), each with the PCI of the PCI column in its place: the column
    gives one PCI for each element of the trace, for each cell or for each cell once its repeats are merged (else the last
    one is that of the last cell)."""
    from src.modules.network_insights import parse_cell_trace, sequence_values
    from src.modules.non_qualified_calls import MAX_ECI

    pci_values = _sequence_numbers(pcis)
    # Each element of the trace (None for one without a cell it can read), with the PCI in its place when the column gives
    # one for each, those without identity among them.
    elements = [cell for item in sequence_values(trace) for cell in (parse_cell_trace(f'[{item}]') or [None])]
    placed = bool(elements) and len(pci_values) == len(elements)
    for element, pci in zip(elements, pci_values if placed else []):
        if element is not None:
            element['pci'] = pci
    cells = [cell for cell in elements if cell is not None and re.fullmatch(r'\d+', cell['cell'])]
    if not cells:
        # The cells of the call itself: a trace (its technologies known; a cell without identity is left out, never the
        # number of its band), else plain cell identities.
        placed = False
        parsed = parse_cell_trace(cell_id)
        if parsed:
            cells = [cell for cell in parsed if re.fullmatch(r'\d+', cell['cell'])]
        else:
            for value in _sequence_numbers(cell_id):
                if value:
                    cells.append({'technology': 'NR' if int(value) > MAX_ECI else 'LTE', 'band': '', 'cell': value, 'channel': ''})
    if not placed and len(pci_values) == len(cells):
        for cell, pci in zip(cells, pci_values):
            cell['pci'] = pci
        placed = True
    cells = merged_repeats(cells)
    if not placed:
        for index, cell in enumerate(cells):
            cell['pci'] = pci_values[index] if len(pci_values) == len(cells) else (pci_values[-1] if index == len(cells) - 1 and pci_values else '')
    return cells


_TRACE_HEAD = re.compile(r'(?:5G\s+)?(LTE E-UTRA|NR|UMTS|GSM)\s*n?(\d*)', re.I)


def cell_steps(value: Any) -> list[dict[str, str]]:
    """Every cell of a cell trace (``[GSM 900, LAC, CI, ARFCN]->[LTE E-UTRA 20, TAC, ECI, EARFCN]``) as the map names it:
    technology, band (``B20``, ``n78``, ``900``), area (TAC / LAC), identity and channel, also those without an identity;
    plain cell identities (``[37171]``) without their technology. A cell repeated in a row is one (merged_repeats)."""
    from src.modules.network_insights import lte_band_for_earfcn, sequence_values

    steps = []
    for item in sequence_values(value):
        parts = [part.strip() for part in str(item).split(',')]
        head = _TRACE_HEAD.match(parts[0])
        if head and len(parts) >= 4:
            technology = 'LTE' if head.group(1).upper().startswith('LTE') else head.group(1).upper()
            band = head.group(2)
            band = (f'B{band}' if technology == 'LTE' else f'n{band}' if technology == 'NR' else band) if band else ''
            if technology == 'LTE' and not band and parts[3]:
                band = lte_band_for_earfcn(parts[3]) or ''
            steps.append({'technology': technology, 'band': band, 'area': parts[1], 'cell': parts[2], 'channel': parts[3]})
        elif all(re.fullmatch(r'\d+', part) for part in parts if part):
            steps.extend({'technology': '', 'band': '', 'area': '', 'cell': part, 'channel': ''} for part in parts if part)
    return merged_repeats(steps)


def cell_label(step: dict[str, Any], name: str = '') -> str:
    """A cell of a call in words: its inventory name with its technology and band, else those with its identity
    (``GSM 900 · LAC 876 · CI 37171``, ``LTE B20 · 30001001``) or its channel when the CDR gives no identity."""
    kind = ' '.join(part for part in (step.get('technology'), step.get('band')) if part)
    if name:
        return f'{name} ({kind})' if kind else name
    cell, area, channel = step.get('cell') or '', step.get('area') or '', step.get('channel') or ''
    if cell and step.get('technology') in ('GSM', 'UMTS'):
        identity = f'LAC {area} · CI {cell}' if area else f'CI {cell}'
    else:
        identity = cell or (f'channel {channel}' if channel else '')
    if not kind and cell:
        identity = f'Cell {cell}'
    return ' · '.join(part for part in (kind, identity) if part) or 'Unknown cell'


def labelled_cells(steps: list[dict[str, Any]], names: dict[str, str] | None = None,
                   far: dict[str, float] | None = None) -> list[dict[str, str]]:
    """The cells of a call in order, each with its role (``both`` alone, else ``start``, ``handover`` and ``end``), its
    technology and its label, by its inventory name when ``names`` (cell identity → name) has it, and how far it is when
    ``far`` (cell identity → km) places it beyond the distance a cell is looked for (see resolve_trace)."""
    count = len(steps)
    labelled = []
    for index, step in enumerate(steps):
        label = cell_label(step, (names or {}).get(step.get('cell') or '', ''))
        if step.get('cell') in (far or {}):
            label = f"{label} · {_km(far[step['cell']])} away"
        labelled.append({'role': 'both' if count == 1 else 'start' if index == 0 else 'end' if index == count - 1 else 'handover',
                         'technology': step.get('technology') or '', 'label': label})
    return labelled


# The frequency of each LTE band, as the RAT timeline of a CDR names it (LTE_800).
LTE_BAND_MHZ = {'1': '2100', '3': '1800', '7': '2600', '8': '900', '20': '800', '28': '700', '32': '1500', '38': '2600', '40': '2300'}
_TIMELINE_ITEM = re.compile(r'([^()>,\[\]]+?)\s*\(\s*(\d+(?:\.\d+)?)\s*\)')


def _timeline_band(name: str) -> str:
    """A band of a RAT timeline (5G_NR_N1, LTE_800, LTE_TDD_2300, GSM_900) as _cell_band names it; '' for No service and the
    others."""
    token = re.sub(r'\s+', '_', name.strip().upper())
    if found := re.fullmatch(r'5G_NR_N(\d+)', token):
        return f'NR n{found.group(1)}'
    if found := re.fullmatch(r'(LTE|GSM|UMTS)_(?:TDD_|FDD_)?(\d+)', token):
        return f'{found.group(1)} {found.group(2)}'
    return ''


def _cell_band(technology: str, band: str) -> str:
    """The band of a cell as a RAT timeline names it: an LTE band by its frequency, an NR band by its number."""
    number = re.sub(r'\D', '', band or '')
    if not number:
        return ''
    if technology == 'LTE':
        return f"LTE {LTE_BAND_MHZ.get(number, '')}" if number in LTE_BAND_MHZ else ''
    if technology == 'NR':
        return f'NR n{number}'
    return f'{technology} {number}' if technology in ('GSM', 'UMTS') else ''


def handover_points(steps: list[dict[str, Any]], timeline: Any, way: list[tuple[float, float]] | None,
                    bands: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Where each handover of a call took place along its way (``way``: from where it started to where it ended, or the way
    simulated of a Data test, see simulated_way), an estimate: the CDR records its cells in order and, in its RAT timeline,
    how long it stayed on each band, not where it changed cell. Each cell is matched to the band of the timeline it was on
    (``bands``: the band of each cell identity in the cell trace) and the cells of a band share its time, so that a handover
    is placed where the call was when it took place, at an even speed (``fraction``: the share of its way behind it); when
    the timeline does not match the cells, the handovers are spread evenly in their order. Without a way there is no way to
    place them."""
    way = [point for point in way or [] if point]
    if len(steps) < 2 or len(way) < 2:
        return []
    segments = [(_timeline_band(name), float(seconds)) for name, seconds in _TIMELINE_ITEM.findall(str(timeline or ''))]
    total = sum(seconds for _band, seconds in segments)
    fractions, by = None, 'order'
    if segments and total > 0:
        owners, position = [], 0
        for step in steps:
            band = _cell_band(step.get('technology') or '', step.get('band') or (bands or {}).get(step.get('cell') or '', '')
                              or (step.get('inventory') or {}).get('band', ''))
            while band and position < len(segments) and segments[position][0] != band:
                position += 1
            if not band or position == len(segments):
                owners = None
                break
            owners.append(position)
        if owners:
            begins, elapsed = [], 0.0
            for _band, seconds in segments:
                begins.append(elapsed)
                elapsed += seconds
            counts, seen, times = Counter(owners), Counter(), []
            for owner in owners:
                times.append(begins[owner] + segments[owner][1] * seen[owner] / counts[owner])
                seen[owner] += 1
            fractions, by = [time / total for time in times[1:]], 'time'
    if fractions is None:
        fractions = [index / len(steps) for index in range(1, len(steps))]
    lengths = [0.0]
    for first, second in zip(way, way[1:]):
        lengths.append(lengths[-1] + distance_km(first, second))

    def along(fraction: float) -> tuple[float, float]:
        at = lengths[-1] * fraction
        index = next((index for index in range(1, len(way)) if lengths[index] >= at), len(way) - 1)
        share = (at - lengths[index - 1]) / ((lengths[index] - lengths[index - 1]) or 1)
        first, second = way[index - 1], way[index]
        return first[0] + (second[0] - first[0]) * share, first[1] + (second[1] - first[1]) * share

    return [{'order': step['order'], 'latitude': round(along(fraction)[0], 6), 'longitude': round(along(fraction)[1], 6), 'by': by,
             'fraction': round(fraction, 4)}
            for step, fraction in zip(steps[1:], fractions, strict=True)]


def name_failure_cells(failures: list[dict[str, Any]], cells: pd.DataFrame, families: tuple[str, ...],
                       max_distance_km: float) -> None:
    """Give every NQ call around its cells (``cells``, see labelled_cells), by their inventory name for the calls of the
    operator of the call: the cell of a network serving it with that identity and technology nearest to the NQ call,
    within ``max_distance_km`` (cell identities are only unique within an operator); and the sites where it started and
    ended (``ends``): those of its first and last cells, else for its start the site the CDR gives (its serving site)."""
    steps = {id(failure): cell_steps(failure.get('cell_id')) for failure in failures}
    wanted = {step['cell'] for failure in failures if failure.get('same_operator') for step in steps[id(failure)] if step['cell']}
    index: dict[str, list[Any]] = {}
    if wanted and not cells.empty:
        found = cells.loc[cells['cell_identity'].astype(str).isin(wanted) & cells['network_family'].isin(families)]
        for cell in found.itertuples(index=False):
            index.setdefault(str(cell.cell_identity), []).append(cell)
    for failure in failures:
        names: dict[str, str] = {}
        sites: dict[str, dict[str, str]] = {}
        position = _position(failure.get('latitude'), failure.get('longitude'))
        for step in steps[id(failure)] if failure.get('same_operator') else []:
            best = None
            for cell in index.get(step['cell'], []):
                if step['technology'] and _text(cell.technology) != step['technology']:
                    continue
                where = _position(cell.latitude, cell.longitude)
                distance = distance_km(position, where) if position and where else None
                if distance is not None and distance > max_distance_km:
                    continue
                if best is None or (distance if distance is not None else math.inf) < best[0]:
                    best = (distance if distance is not None else math.inf, _text(cell.cell_name), cell)
            if best and best[1]:
                names[step['cell']] = best[1]
            if best:
                sites[step['cell']] = {'site_id': _text(best[2].site_id), 'network': _text(best[2].host_network) or _text(best[2].network)}
        failure['cells'] = labelled_cells(steps[id(failure)], names)
        own = steps[id(failure)]
        ends = {'start': sites.get(own[0]['cell']) if own else None, 'end': sites.get(own[-1]['cell']) if own else None}
        if not ends['start'] and failure.get('site_id'):
            ends['start'] = {'site_id': failure['site_id'], 'network': failure.get('host_network') or ''}
        failure['ends'] = {role: site for role, site in ends.items() if site}


def _cell_payload(cell: Any, colours: dict[str, str]) -> dict[str, Any]:
    from src.modules.inventory_insights import vendor_colour

    azimuth = _number(cell.azimuth)
    return {
        'name': _text(cell.cell_name), 'identity': _text(cell.cell_identity), 'technology': _text(cell.technology),
        'band': _text(cell.band_3gpp) or _text(cell.band), 'channel': _text(cell.channel).removesuffix('.0'),
        'pci': _text(cell.pci).removesuffix('.0'), 'azimuth': None if azimuth is None else round(azimuth, 1),
        'beamwidth': _number(cell.beamwidth), 'height': _number(cell.height), 'vendor': _text(cell.vendor),
        'state': _text(cell.state) or ('In service' if bool(cell.in_service) else _text(cell.status)),
        'colour': vendor_colour(_text(cell.vendor), colours),
    }


def _site_id(family: str, site: str) -> str:
    return f'{family}|{site}'.casefold()


def resolve_trace(trace: list[dict[str, str]], cells: pd.DataFrame, families: tuple[str, ...], positions: dict[str, Any],
                  max_distance_km: float, colours: dict[str, str]) -> list[dict[str, Any]]:
    """Each cell of the trace with the inventory cell it was (a network serving the operator, its own first; the nearest to
    where it served the call within ``max_distance_km``, else, farther, the nearest with the PCI and channel the CDR gives
    it, ``far``: a cell on a high mast serves a call on high ground from much farther, while an identity alone farther may
    be another cell with that number) and its site, or without them when no inventory has it."""
    resolved = []
    reference = positions.get('end') or positions.get('start')
    count = len(trace)
    for index, step in enumerate(trace):
        role = 'both' if count == 1 else 'start' if index == 0 else 'end' if index == count - 1 else 'handover'
        where = positions.get('start') if role == 'start' and positions.get('start') else reference
        entry = {**step, 'order': index + 1, 'role': role, 'role_label': CELL_ROLES[role], 'site': None}
        if not cells.empty:
            found = cells.loc[(cells['cell_identity'].astype(str) == step['cell']) & cells['network_family'].isin(families)]
            if step.get('technology'):
                found = found.loc[found['technology'] == step['technology']]
            best = None
            for rank, family in enumerate(families):
                for cell in found.loc[found['network_family'] == family].itertuples(index=False):
                    position = _position(cell.latitude, cell.longitude)
                    distance = distance_km(where, position) if where and position else None
                    if distance is not None and distance > max_distance_km:
                        continue
                    key = (rank, math.inf if distance is None else distance)
                    if best is None or key < best[0]:
                        best = (key, cell, distance)
                if best is not None:
                    break
            far = False
            if best is None and step.get('pci') and step.get('channel'):
                for cell in found.itertuples(index=False):
                    if (_text(cell.pci).removesuffix('.0') != str(step['pci'])
                            or _text(cell.channel).removesuffix('.0') != str(step['channel'])):
                        continue
                    position = _position(cell.latitude, cell.longitude)
                    distance = distance_km(where, position) if where and position else None
                    if distance is not None and (best is None or distance < best[0]):
                        best = (distance, cell, distance)
                far = best is not None
            if best is not None:
                _key, cell, distance = best
                entry.update({'site': _site_id(cell.network_family, _text(cell.site_id)), 'site_id': _text(cell.site_id),
                              'network': _text(cell.network), 'host_network': _text(cell.host_network),
                              'latitude': _number(cell.latitude), 'longitude': _number(cell.longitude), 'far': far,
                              'distance_km': None if distance is None else round(distance, 3), 'inventory': _cell_payload(cell, colours)})
                entry['pci'] = entry['pci'] or entry['inventory']['pci']
                entry['band'] = entry['band'] or entry['inventory']['band']
        resolved.append(entry)
    return resolved


def nr_leg(service: str, row: dict[str, Any], columns: list[str], cells: pd.DataFrame, families: tuple[str, ...],
           point: tuple[float, float] | None, anchor_site: str, colours: dict[str, str],
           profile: CdrFieldProfile = NETCHECK_PROFILE) -> dict[str, Any] | None:
    """The NR cell of an NSA call where it failed, from its NR PCI (and NR-ARFCN when the CDR has it): on the site of its
    LTE anchor when one of its NR cells has that PCI, else the nearest within NR_LEG_KM."""
    _column, pcis = _first_value(row, columns, profile.rf_field_aliases['nr_pci'].get(service, ()))
    pci = next((value for value in reversed(_sequence_numbers(pcis)) if value), '')
    if not pci or cells.empty or point is None:
        return None
    _column, channels = _first_value(row, columns, profile.rf_field_aliases['nr_arfcn'].get(service, ()))
    channel = next((value for value in reversed(_sequence_numbers(channels)) if value), '')
    found = cells.loc[(cells['technology'] == 'NR') & cells['network_family'].isin(families)
                      & (cells['pci'].astype(str).str.removesuffix('.0') == pci)]
    if channel:
        same_channel = found.loc[found['channel'].astype(str).str.removesuffix('.0') == channel]
        found = same_channel if not same_channel.empty else found
    best = None
    for cell in found.itertuples(index=False):
        position = _position(cell.latitude, cell.longitude)
        if not position:
            continue
        distance = distance_km(point, position)
        on_anchor = _site_id(cell.network_family, _text(cell.site_id)) == anchor_site
        if distance > NR_LEG_KM and not on_anchor:
            continue
        key = (not on_anchor, distance)
        if best is None or key < best[0]:
            best = (key, cell, distance)
    if best is None:
        return {'technology': 'NR', 'band': '', 'cell': '', 'channel': channel, 'pci': pci, 'order': 0, 'role': 'nr_leg',
                'role_label': CELL_ROLES['nr_leg'], 'site': None}
    _key, cell, distance = best
    payload = _cell_payload(cell, colours)
    return {'technology': 'NR', 'band': payload['band'], 'cell': payload['identity'], 'channel': channel or payload['channel'],
            'pci': pci, 'order': 0, 'role': 'nr_leg', 'role_label': CELL_ROLES['nr_leg'],
            'site': _site_id(cell.network_family, _text(cell.site_id)), 'site_id': _text(cell.site_id), 'network': _text(cell.network),
            'host_network': _text(cell.host_network), 'latitude': _number(cell.latitude), 'longitude': _number(cell.longitude),
            'distance_km': round(distance, 3), 'inventory': payload, 'on_anchor': not best[0][0]}


# ---------------------------------------------------------------------------
# The inventory sites around the call
# ---------------------------------------------------------------------------
def inventory_cells(repository: Any, families: tuple[str, ...]) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """The cells of the newest inventory snapshot of each network serving the operator, and those snapshots."""
    from src.modules.inventory_insights import load_cells, snapshot_choice
    from src.modules.network_inventory import list_inventory_snapshots

    try:
        snapshots = list_inventory_snapshots(repository)
    except Exception:  # noqa: BLE001 - a workspace without inventories shows the map without sites.
        return pd.DataFrame(), []
    selection = {family: dataset_id for family, dataset_id in snapshot_choice(snapshots).items() if family in families}
    if not selection:
        return pd.DataFrame(), []
    by_id = {item['dataset_id']: item for item in snapshots}
    used = [{'family': family, 'file_name': by_id[dataset_id]['file_name'], 'snapshot_date': by_id[dataset_id]['snapshot_date']}
            for family, dataset_id in selection.items()]
    return load_cells(repository, selection), used


def nearby_sites(cells: pd.DataFrame, centre: tuple[float, float], radius_km: float, keep: set[str],
                 colours: dict[str, str]) -> list[dict[str, Any]]:
    """The sites with cells in service (or not on air yet) within ``radius_km`` of ``centre``, nearest first, and those of
    ``keep`` wherever they are: each with its cells."""
    if cells.empty:
        return []
    states = cells['state'] if 'state' in cells else pd.Series('', index=cells.index)
    drawn = cells.loc[(cells['in_service'] | states.isin(('In progress', 'Planned'))) & cells['latitude'].notna()
                      & cells['longitude'].notna()]
    south, north, west, east = bounding_box(centre, radius_km)
    keys = drawn['network_family'].astype(str) + '|' + drawn['site_id'].astype(str)
    keys = keys.str.casefold()
    wanted = (drawn['latitude'].between(south, north) & drawn['longitude'].between(west, east)) | keys.isin(keep)
    if not wanted.any():
        return []
    chosen = drawn.loc[wanted].assign(_site=keys[wanted])
    sites = []
    for key, part in chosen.groupby('_site', sort=False):
        position = (float(part['latitude'].median()), float(part['longitude'].median()))
        distance = distance_km(centre, position)
        if distance > radius_km and key not in keep:
            continue
        first = part.iloc[0]
        cell_rows = sorted((_cell_payload(cell, colours) for cell in part.itertuples(index=False)),
                           key=lambda item: (item['technology'], item['azimuth'] if item['azimuth'] is not None else -1, item['band']))
        vendors = sorted({cell['vendor'] for cell in cell_rows if cell['vendor']}, key=str.casefold)
        sites.append({
            'key': key, 'site_id': _text(first['site_id']), 'network': _text(first['network']), 'family': _text(first['network_family']),
            'host_network': _text(first['host_network']), 'vendors': vendors, 'site_type': _text(first.get('site_type')),
            'emocn': _text(first.get('emocn')), 'city': _text(first.get('city')),
            'latitude': round(position[0], 6), 'longitude': round(position[1], 6), 'distance_km': round(distance, 3),
            'cells': cell_rows,
        })
    sites.sort(key=lambda site: (site['key'] not in keep, site['distance_km']))
    kept = [site for site in sites if site['key'] in keep]
    others = [site for site in sites if site['key'] not in keep][:max(0, MAX_SITES - len(kept))]
    ordered = sorted(kept + others, key=lambda site: site['distance_km'])
    for rank, site in enumerate(ordered, start=1):
        site['rank'] = rank
    return ordered


def flag_same_pci(sites: list[dict[str, Any]], trace: list[dict[str, Any]]) -> None:
    """Mark the cells around with the PCI and channel of a cell of the call (other than that cell): a PCI collision or
    confusion to check."""
    owned = {}
    for step in trace:
        channel = str(step.get('channel') or (step.get('inventory') or {}).get('channel') or '')
        if step.get('pci') and channel:
            owned[(step.get('technology') or '', str(step['pci']), channel)] = (f"{step['role_label']} · PCI {step['pci']}", step.get('cell'))
    if not owned:
        return
    for site in sites:
        for cell in site['cells']:
            match = owned.get((cell['technology'], cell['pci'], cell['channel']))
            if match and cell['identity'] != match[1]:
                cell['same_pci'] = match[0]


# ---------------------------------------------------------------------------
# The Non-Qualified Calls around it
# ---------------------------------------------------------------------------
def nearby_failures(repository: Any, call: dict[str, Any], centre: tuple[float, float], radius_km: float
                    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """The Non-Qualified Calls (their latest version) within ``radius_km`` of ``centre`` and those of the operator of the call
    at its place or in its hotspot, cluster or time-window issue wherever they are, nearest first: each with how
    it relates to the call. Every one of its campaign (and NR Mode) and of its groups and site is kept, and the nearest
    MAX_FAILURES of the other campaigns; also how many of those were left out, and the groups of the call (how many calls
    its hotspot, cluster and run hold, and whether it has a site)."""
    from src.modules import non_qualified_calls as nq
    from src.modules.nq_prioritization import PRIORITY_TABLE, call_kind

    options = nq.list_options(repository)
    base, params = nq._base_sql(nq.untracked_status(repository, options), repository)
    south, north, west, east = bounding_box(centre, radius_km)
    with repository.connection() as connection:
        own = connection.execute(f'SELECT place_key, cluster_key, cluster_size, repeat_key, repeat_size, repeat_all_key, consecutive_key, '
                                 f'consecutive_size FROM {PRIORITY_TABLE} WHERE call_key = ?', (call.get('parent_key') or call['call_key'],)).fetchone()
        place, hotspot, cluster, run = ((_text(own['place_key']), _text(own['cluster_key']), _text(own['repeat_key']), _text(own['consecutive_key']))
                                        if own else ('', '', '', ''))
        rows = connection.execute(f"""
            WITH calls AS ({base})
            SELECT c.call_key, c.dataset_id, c.join_id, c.service, c.test_name, c.session_type, c.operator, c.campaign, c.nr_mode, c.result,
                   c.failure_classification, c.failure_category, c.failure_subcategory, c.failure_phase, c.technology,
                   c.start_time, c.latitude, c.longitude, c.site_id, c.host_network, c.cell_id, c.city, c.status,
                   c.root_domain, c.root_category, c.root_cause, COALESCE(q.place_key, '') AS place_key, COALESCE(q.place_label, '') AS place_label,
                   COALESCE(q.cluster_key, '') AS cluster_key, COALESCE(q.repeat_key, '') AS repeat_key,
                   COALESCE(q.repeat_all_key, '') AS repeat_all_key, COALESCE(q.consecutive_key, '') AS consecutive_key,
                   q.repetitions AS repetitions
            FROM calls c LEFT JOIN {PRIORITY_TABLE} q ON q.call_key = c.call_key
            WHERE (c.latitude BETWEEN ? AND ? AND c.longitude BETWEEN ? AND ?)
               OR (? <> '' AND q.place_key = ?) OR (? <> '' AND q.cluster_key = ?) OR (? <> '' AND q.repeat_key = ?)
               OR (? <> '' AND q.consecutive_key = ?)
        """, [*params, south, north, west, east, place, place, hotspot, hotspot, cluster, cluster, run, run]).fetchall()
    own_key = call.get('parent_key') or call['call_key']
    operator = _text(call.get('operator')).casefold()
    failures = []
    for row in rows:
        position = _position(row['latitude'], row['longitude'])
        distance = distance_km(centre, position) if position else None
        same_operator = _text(row['operator']).casefold() == operator
        same_place = bool(place) and row['place_key'] == place and same_operator
        same_hotspot = bool(hotspot) and row['cluster_key'] == hotspot
        same_cluster = bool(cluster) and row['repeat_key'] == cluster
        same_run = bool(run) and row['consecutive_key'] == run
        is_self = row['call_key'] == own_key
        if not is_self and not (same_place or same_hotspot or same_cluster or same_run) and (distance is None or distance > radius_km):
            continue
        kind = call_kind(row['service'], row['test_name'], row['session_type'])
        failures.append({
            'call_key': row['call_key'], 'dataset_id': None if row['dataset_id'] is None else int(row['dataset_id']),
            'join_id': _text(row['join_id']), 'service': row['service'], 'kind': kind,
            'test_name': _text(row['test_name']), 'operator': _text(row['operator']), 'campaign': _text(row['campaign']),
            'nr_mode': _text(row['nr_mode']), 'result': _text(row['result']), 'technology': _text(row['technology']),
            'failure_classification': _text(row['failure_classification']), 'failure_category': _text(row['failure_category']),
            'failure_subcategory': _text(row['failure_subcategory']), 'failure_phase': _text(row['failure_phase']),
            'start_time': _text(row['start_time']), 'city': _text(row['city']), 'status': _text(row['status']),
            'root_domain': _text(row['root_domain']), 'root_category': _text(row['root_category']), 'root_cause': _text(row['root_cause']),
            'site_id': _text(row['site_id']), 'host_network': _text(row['host_network']), 'cell_id': _text(row['cell_id']),
            'place_label': _text(row['place_label']), 'repetitions': row['repetitions'],
            'latitude': position[0] if position else None, 'longitude': position[1] if position else None,
            'distance_km': None if distance is None else round(distance, 3),
            'self': is_self, 'same_operator': same_operator, 'same_place': same_place and not is_self,
            'same_hotspot': same_hotspot and not is_self, 'same_cluster': same_cluster and not is_self, 'same_run': same_run and not is_self,
            # The keys of its groups, so that the page can tell those of the group that filters the list of calls.
            'cluster_key': _text(row['cluster_key']), 'repeat_key': _text(row['repeat_key']), 'repeat_all_key': _text(row['repeat_all_key']),
            'consecutive_key': _text(row['consecutive_key']),
        })
    def order(item: dict[str, Any]) -> tuple[Any, ...]:
        return (not item['self'], not (item['same_hotspot'] or item['same_cluster'] or item['same_run'] or item['same_place']),
                math.inf if item['distance_km'] is None else item['distance_km'])

    def kept(item: dict[str, Any]) -> bool:
        return (item['self'] or item['same_hotspot'] or item['same_cluster'] or item['same_run']
                or item['same_place'] or (item['campaign'] == _text(call.get('campaign')) and item['nr_mode'] == _text(call.get('nr_mode'))))
    failures.sort(key=order)
    others = [item for item in failures if not kept(item)]
    groups = {'hotspot': (own['cluster_size'] or 0) if hotspot else 0, 'cluster': (own['repeat_size'] or 0) if cluster else 0,
              'run': (own['consecutive_size'] or 0) if run else 0, 'site': bool(place)}
    return (sorted([*(item for item in failures if kept(item)), *others[:MAX_FAILURES]], key=order),
            max(0, len(others) - MAX_FAILURES), groups)


# ---------------------------------------------------------------------------
# The tests of the CDRs around it (their RSRP and SINR)
# ---------------------------------------------------------------------------
def _dataset_tests(repository: Any, dataset_id: int) -> dict[str, Any] | None:
    """The located tests of a CDR: position, operator, result, test name and LTE / NR RSRP and SINR (kept in memory)."""
    from src.modules import non_qualified_calls as nq

    with repository.connection() as connection:
        profile = connection.execute('SELECT dataset_kind FROM dataset_profiles WHERE dataset_id = ?', (dataset_id,)).fetchone()
        source = connection.execute(f'SELECT revision FROM {nq.NQ_CALL_SOURCES_TABLE} WHERE dataset_id = ?', (dataset_id,)).fetchone()
    kind = _text(profile['dataset_kind']) if profile else ''
    if kind not in nq.SERVICES:
        return None
    workspace = str(repository.db_path)
    key = (workspace, int(dataset_id), _text(source['revision']) if source else '')
    with _tests_guard:
        if key in _tests_cache:
            _tests_cache.move_to_end(key)
            return _tests_cache[key]
        lock = _tests_locks.setdefault((workspace, int(dataset_id)), Lock())
    with lock:
        with _tests_guard:
            if key in _tests_cache:
                return _tests_cache[key]
        table = f'dataset_rows_{int(dataset_id)}'
        fields_profile = workspace_field_profile(repository)
        with repository.connection() as connection:
            columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info({nq._quote(table)})').fetchall()]
        aliases, sources = fields_profile.rf_field_aliases, fields_profile.nq_field_sources
        # The columns of each value of the tests, the first one with a value taken.
        picked = {name: nq._resolve_columns(columns, candidates) for name, candidates in (
            ('latitude', aliases['latitude'].get(kind, ())), ('longitude', aliases['longitude'].get(kind, ())),
            ('operator', sources['operator']), ('result', fields_profile.nq_qualification_sources), ('test', sources['test_name']),
            ('start', sources['start_time']), *((name, aliases[name].get(kind, ())) for name in ('lte_rsrp', 'lte_sinr', 'nr_rsrp', 'nr_sinr')))}
        if not picked['latitude'] or not picked['longitude']:
            return None
        if int(dataset_id) in cdr_store.fresh_copies(repository.db_path, [dataset_id]):
            frame = cdr_store.coalesced_frame(repository.db_path, kind, int(dataset_id), list(picked.items()), ['latitude', 'longitude'])
        else:
            def expression(found: list[str]) -> str:
                quoted = [nq._quote(column) for column in found]
                return 'NULL' if not quoted else quoted[0] if len(quoted) == 1 else f"COALESCE({', '.join(quoted)})"

            latitude, longitude = expression(picked['latitude']), expression(picked['longitude'])
            with repository.connection() as connection:
                frame = pd.read_sql_query(
                    f"SELECT {', '.join(f'{expression(found)} AS {name}' for name, found in picked.items())} "
                    f'FROM {nq._quote(table)} WHERE {latitude} IS NOT NULL AND {longitude} IS NOT NULL', connection)
        latitudes = pd.to_numeric(frame['latitude'], errors='coerce')
        longitudes = pd.to_numeric(frame['longitude'], errors='coerce')
        valid = latitudes.between(-90, 90) & longitudes.between(-180, 180) & ~((latitudes.abs() < 1e-6) & (longitudes.abs() < 1e-6))
        frame = frame.loc[valid]
        # The operators and test names of the tests, each once (codes by hashing: their order means nothing).
        operator_codes, operators = pd.factorize(frame['operator'].fillna('').astype(str).str.strip().to_numpy())
        test_codes, tests = pd.factorize(frame['test'].fillna('').astype(str).str.strip().to_numpy())
        results = frame['result'].fillna('').astype(str).str.strip().str.casefold()
        metrics = {}
        for name, low, high in (('lte_rsrp', -160, -20), ('nr_rsrp', -160, -20), ('lte_sinr', -30, 50), ('nr_sinr', -30, 50)):
            values = pd.to_numeric(frame[name], errors='coerce')
            metrics[name] = values.where(values.between(low, high)).to_numpy(dtype=np.float32)
        entry = {
            'kind': kind, 'latitude': latitudes[valid].to_numpy(dtype=float), 'longitude': longitudes[valid].to_numpy(dtype=float),
            'operators': [str(value) for value in operators], 'operator': operator_codes.astype(np.int32),
            'tests': [str(value) for value in tests], 'test': test_codes.astype(np.int32),
            'failed': (results.ne(fields_profile.nq_qualified_value) & results.ne('')).to_numpy(dtype=bool),
            'start': frame['start'].fillna('').astype(str).str.slice(0, 19).to_numpy(dtype=object),
            'moment': _seconds(frame['start']),
            **metrics,
        }
        with _tests_guard:
            _tests_cache[key] = entry
            while len(_tests_cache) > CACHED_CDRS:
                _tests_cache.popitem(last=False)
        return entry


def test_datasets(repository: Any, call: dict[str, Any], scope: str, campaigns: Any = ()) -> list[int]:
    """The CDRs whose tests the map shows, that of the call first, always of the NR Mode of the call (NSA and SA fail along
    different paths): every CDR with the latest calls of the ``campaigns`` chosen in the filters of the page (of every
    campaign while none is chosen), or of the campaign of the call (``scope`` ``campaign``)."""
    from src.modules import non_qualified_calls as nq

    own = [int(call['dataset_id'])]
    if scope == 'campaign':
        if not _text(call.get('campaign')):
            return own
        conditions, params = ['campaign = ?', 'nr_mode = ?'], [call['campaign'], _text(call.get('nr_mode'))]
    else:
        chosen = [_text(value) for value in campaigns or () if _text(value)]
        conditions, params = ['nr_mode = ?'], [_text(call.get('nr_mode')), *chosen]
        if chosen:
            conditions.append(f"campaign IN ({', '.join('?' for _ in chosen)})")
    where = ''.join(f' AND {condition}' for condition in conditions)
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT DISTINCT dataset_id FROM {nq.NQ_CALL_POPULATION_TABLE} WHERE is_latest = 1 AND service IN ('voice', 'speech', 'data')"
            f'{where} ORDER BY dataset_id', params).fetchall()
    return list(dict.fromkeys([*own, *(int(row[0]) for row in rows)]))


def _cdr_profiles(connection: Any, workspace: str, dataset_ids: list[int]) -> dict[int, dict[str, Any]]:
    """The campaign and NR Mode of each CDR as its calls give them (the most common). Counting its calls reads all of
    them, so each answer is kept until the calls of the CDR are indexed again (its revision and sync time)."""
    from src.modules import non_qualified_calls as nq

    placeholders = ', '.join('?' for _ in dataset_ids) or 'NULL'
    versions = {int(row[0]): (_text(row[1]), _text(row[2])) for row in connection.execute(
        f'SELECT dataset_id, revision, synced_at FROM {nq.NQ_CALL_SOURCES_TABLE} WHERE dataset_id IN ({placeholders})', dataset_ids)}
    profiles: dict[int, dict[str, Any]] = {}
    missing = []
    with _tests_guard:
        for dataset_id in dataset_ids:
            cached = _profiles_cache.get((workspace, dataset_id))
            if cached is not None and cached[0] == versions.get(dataset_id):
                if cached[1] is not None:
                    profiles[dataset_id] = cached[1]
            else:
                missing.append(dataset_id)
    if missing:
        found: dict[int, dict[str, Any]] = {}
        for row in connection.execute(
                f'SELECT dataset_id, campaign, nr_mode, COUNT(*) AS calls FROM {nq.NQ_CALL_POPULATION_TABLE} '
                f"WHERE dataset_id IN ({', '.join('?' for _ in missing)}) GROUP BY dataset_id, campaign, nr_mode ORDER BY calls DESC",
                missing):
            found.setdefault(int(row['dataset_id']), {'campaign': row['campaign'], 'nr_mode': row['nr_mode']})
        profiles.update(found)
        with _tests_guard:
            for dataset_id in missing:
                if dataset_id in versions:
                    _profiles_cache[(workspace, dataset_id)] = (versions[dataset_id], found.get(dataset_id))
    return profiles


def nearby_tests(repository: Any, dataset_ids: list[int], centre: tuple[float, float], radius_km: float,
                 operator_label: Callable[[str], str] = str) -> dict[str, Any]:
    """The tests of the CDRs within ``radius_km`` of ``centre`` (the nearest MAX_TESTS), as compact rows: latitude, longitude,
    operator (its label in the Operator Maps), CDR type, failed, LTE RSRP, LTE SINR, NR RSRP, NR SINR, test name, start
    time and CDR (its campaign, NR Mode, type and stage in ``cdrs``)."""
    operators: list[str] = []
    operator_index: dict[str, int] = {}
    labels: dict[str, str] = {}
    kinds: list[str] = []
    names: list[str] = []
    name_index: dict[str, int] = {}
    parts = []
    cdrs: list[dict[str, Any]] = []
    cdr_index: dict[int, int] = {}
    south, north, west, east = bounding_box(centre, radius_km)
    # The campaign and NR Mode of each CDR as its calls give them (the most common), and its stage.
    placeholders = ', '.join('?' for _ in dataset_ids) or 'NULL'
    with repository.connection() as connection:
        stages = {int(row['dataset_id']): _text(row['cdr_stage']) for row in connection.execute(
            f'SELECT dataset_id, cdr_stage FROM dataset_profiles WHERE dataset_id IN ({placeholders})', [int(value) for value in dataset_ids])}
        profiles = _cdr_profiles(connection, str(repository.db_path), [int(value) for value in dataset_ids])
    for dataset_id in dataset_ids:
        entry = _dataset_tests(repository, dataset_id)
        if not entry:
            continue
        inside = np.flatnonzero((entry['latitude'] >= south) & (entry['latitude'] <= north)
                                & (entry['longitude'] >= west) & (entry['longitude'] <= east))
        if not len(inside):
            continue
        distances = _distances(entry['latitude'][inside], entry['longitude'][inside], centre)
        keep = distances <= radius_km
        inside, distances = inside[keep], distances[keep]
        if entry['kind'] not in kinds:
            kinds.append(entry['kind'])
        profile = profiles.get(int(dataset_id))
        cdr_index[int(dataset_id)] = len(cdrs)
        cdrs.append({'dataset_id': int(dataset_id), 'kind': entry['kind'],
                     'campaign': _text(profile['campaign']) if profile else '', 'nr_mode': _text(profile['nr_mode']) if profile else '',
                     'stage': stages.get(int(dataset_id), '')})
        parts.append((entry, inside, distances, kinds.index(entry['kind']), cdr_index[int(dataset_id)]))
    total = sum(len(part[1]) for part in parts)
    candidates = [(float(distance), part_index, int(row)) for part_index, (_entry, inside, distances, _kind, _cdr) in enumerate(parts)
                  for row, distance in zip(inside, distances)]
    candidates.sort(key=lambda item: item[0])
    rows = []

    def rounded(value: Any, digits: int = 1) -> float | None:
        return None if value is None or not math.isfinite(float(value)) else round(float(value), digits)

    for distance, part_index, row in candidates[:MAX_TESTS]:
        entry, _inside, _distances_, kind, cdr = parts[part_index]
        source = entry['operators'][entry['operator'][row]]
        if source not in labels:
            labels[source] = str(operator_label(source) or source)
        operator = labels[source]
        if operator not in operator_index:
            operator_index[operator] = len(operators)
            operators.append(operator)
        name = entry['tests'][entry['test'][row]]
        if name not in name_index:
            name_index[name] = len(names)
            names.append(name)
        rows.append([round(float(entry['latitude'][row]), 6), round(float(entry['longitude'][row]), 6), operator_index[operator], kind,
                     int(bool(entry['failed'][row])), rounded(entry['lte_rsrp'][row]), rounded(entry['lte_sinr'][row]),
                     rounded(entry['nr_rsrp'][row]), rounded(entry['nr_sinr'][row]), name_index[name], str(entry['start'][row]), cdr])
    covered = candidates[min(len(candidates), MAX_TESTS) - 1][0] if len(candidates) > MAX_TESTS else radius_km
    return {'operators': operators, 'kinds': kinds, 'test_names': names, 'cdrs': cdrs, 'rows': rows, 'total': total,
            'truncated': total > len(rows), 'covered_km': round(covered, 3),
            'columns': ['latitude', 'longitude', 'operator', 'kind', 'failed', 'lte_rsrp', 'lte_sinr', 'nr_rsrp', 'nr_sinr', 'test', 'start', 'cdr']}


# ---------------------------------------------------------------------------
# What the map suggests, the decisions at its place, its drive and its serving site
# ---------------------------------------------------------------------------
def call_radio(service: str, row: dict[str, Any], columns: list[str],
               profile: CdrFieldProfile = NETCHECK_PROFILE) -> dict[str, float | None]:
    """The average LTE and NR RSRP and SINR of the call in its CDR row (None without a valid value)."""
    values: dict[str, float | None] = {}
    for name, low, high in (('lte_rsrp', -160, -20), ('nr_rsrp', -160, -20), ('lte_sinr', -30, 50), ('nr_sinr', -30, 50)):
        _column, value = _first_value(row, columns, profile.rf_field_aliases[name].get(service, ()))
        number = _number(value)
        values[name] = number if number is not None and low <= number <= high else None
    return values


def _check(key: str, level: str, title: str, detail: str) -> dict[str, str]:
    """One finding of the diagnosis: ``bad``, ``warn``, ``ok`` or ``info``."""
    return {'key': key, 'level': level, 'title': title, 'detail': detail}


def _share(part: int, total: int) -> str:
    return f'{round(part * 100 / total)}%' if total else '—'


def diagnosis(call: dict[str, Any], radio: dict[str, float | None], trace: list[dict[str, Any]], sites: list[dict[str, Any]],
              failures: list[dict[str, Any]], tests: dict[str, Any], radius_km: float, min_calls: int,
              ran: dict[str, Any] | None = None, point: tuple[float, float] | None = None,
              travel: dict[str, float | None] | None = None) -> list[dict[str, str]]:
    """What the map suggests about the failure, one finding per check: coverage (a coverage hole too), interference,
    serving distance, overshooting cells, PCI, the state of the cells around, the other operators, repetition and handovers
    (ping-pong). ``ran`` gives the inter-site distance (ISD) of the serving site and the nearest site of the networks serving
    the operator, with its ISD, and the ISD of every site of its cells (``isds``, ran_context): the serving distance, the
    overshooting cells and the coverage holes are judged by them. ``point`` is where the call failed (the overshooting cells
    point at it) and ``travel`` how far (``metres``) and how long (``seconds``) it went."""
    from src.modules.network_insights import (
        DEFAULT_COVERAGE_THRESHOLD, DEFAULT_INTERFERENCE_THRESHOLD, DEFAULT_NR_COVERAGE_THRESHOLD, DEFAULT_NR_INTERFERENCE_THRESHOLD,
    )
    from src.modules.ran_context import HOLE_ISD, NEARER_SHARE, OVERSHOOT_ISD, OVERSHOOT_MIN_KM, serving_isd_ratio

    limits = {'LTE': (DEFAULT_COVERAGE_THRESHOLD, DEFAULT_INTERFERENCE_THRESHOLD),
              'NR': (DEFAULT_NR_COVERAGE_THRESHOLD, DEFAULT_NR_INTERFERENCE_THRESHOLD)}
    operator = _text(call.get('operator')) or 'its operator'
    checks = []
    # Coverage and interference, from the averages of the call.
    rsrp = [(tech, radio[f'{tech.lower()}_rsrp'], limits[tech][0]) for tech in limits if radio.get(f'{tech.lower()}_rsrp') is not None]
    sinr = [(tech, radio[f'{tech.lower()}_sinr'], limits[tech][1]) for tech in limits if radio.get(f'{tech.lower()}_sinr') is not None]
    weak = [item for item in rsrp if item[1] < item[2]]
    text = ' · '.join(f'{tech} RSRP {value:.1f} dBm' for tech, value, _limit in rsrp)
    # No site of its networks near: the nearest one beyond HOLE_ISD times its own inter-site distance.
    closest = (ran or {}).get('nearest')
    hole = bool(closest and closest.get('isd_km') and closest['distance_km'] >= HOLE_ISD * closest['isd_km'])
    away = (f"the nearest site of its networks, Site {closest['site_id']} ({closest['network']}), is {_km(closest['distance_km'])} "
            f"away, {serving_isd_ratio(closest['distance_km'], closest.get('isd_km')):.1f} times its inter-site distance "
            f"({_km(closest.get('isd_km'))})") if hole else ''
    if not rsrp and hole:
        checks.append(_check('coverage', 'bad', 'Coverage hole', f'The CDR gives no RSRP of the call and {away}.'))
    elif not rsrp:
        checks.append(_check('coverage', 'info', 'Coverage', 'The CDR gives no RSRP of the call.'))
    elif weak and hole:
        checks.append(_check('coverage', 'bad', 'Coverage hole', f'{text}: below {weak[0][2]:g} dBm in {weak[0][0]}, and {away}.'))
    elif weak:
        checks.append(_check('coverage', 'bad', 'Weak coverage', f'{text}: below {weak[0][2]:g} dBm in {weak[0][0]}.'))
    elif any(value < limit + 10 for _tech, value, limit in rsrp):
        checks.append(_check('coverage', 'warn', 'Fair coverage', f'{text}: less than 10 dB above the weak level.'))
    else:
        checks.append(_check('coverage', 'ok', 'Good coverage', f'{text}.'))
    text = ' · '.join(f'{tech} SINR {value:.1f} dB' for tech, value, _limit in sinr)
    low = [item for item in sinr if item[1] < item[2]]
    if not sinr:
        checks.append(_check('interference', 'info', 'Interference', 'The CDR gives no SINR of the call.'))
    elif low and not weak:
        checks.append(_check('interference', 'bad', 'Interference', f'{text} with a good RSRP: look for overlapping or overshooting cells and PCI collisions.'))
    elif low:
        checks.append(_check('interference', 'warn', 'Low SINR with weak coverage', f'{text}: the SINR follows the weak coverage.'))
    elif any(value < limit + 3 for _tech, value, limit in sinr):
        checks.append(_check('interference', 'warn', 'Fair SINR', f'{text}: less than 3 dB above the interference level.'))
    else:
        checks.append(_check('interference', 'ok', 'Good SINR', f'{text}.'))
    # The cell where the call ended (or that served all of it) against the nearest site of the networks serving the operator.
    end = next((step for step in reversed(trace) if step.get('site') and step['role'] in ('end', 'both')), None)
    nearest = closest or (sites[0] if sites else None)
    if end is None or end.get('distance_km') is None:
        checks.append(_check('distance', 'info', 'Serving distance', 'The cell where the call ended is not in the Network Inventory near the call.'))
    else:
        distance, name = end['distance_km'], f"Site {end['site_id']} ({end['network']})"
        isd = (ran or {}).get('serving_isd')
        ratio = serving_isd_ratio(distance, isd)
        nearer = nearest and nearest['key'] != end['site'] and nearest['distance_km'] <= distance * NEARER_SHARE
        spacing = f', {ratio:.1f} times the inter-site distance of its site ({_km(isd)})' if ratio is not None else ''
        # Beyond twice the ISD of its site is too far; beyond it, with a site three times nearer, not the right site.
        far, beyond = ((ratio >= OVERSHOOT_ISD and distance >= OVERSHOOT_MIN_KM, ratio >= 1) if ratio is not None
                       else (distance >= OVERSHOOT_KM, distance >= FAR_SERVING_KM))
        if far:
            there = f" Site {nearest['site_id']} ({nearest['network']}) is {_km(nearest['distance_km'])} away." if nearer else ''
            checks.append(_check('distance', 'bad', 'Served from far away',
                                 f'The cell where it failed is on {name}, {_km(distance)} away{spacing}: overshooting?{there}'))
        elif beyond and nearer:
            checks.append(_check('distance', 'warn', 'Not served by the nearest sites',
                                 f"Served from {name} at {_km(distance)}{spacing} while Site {nearest['site_id']} ({nearest['network']}) is "
                                 f"{_km(nearest['distance_km'])} away: a missing neighbour or overshooting?"))
        else:
            near = f" (nearest site {_km(nearest['distance_km'])})" if nearest and nearest['key'] != end['site'] else ' (the nearest site)'
            checks.append(_check('distance', 'ok', 'Serving distance', f'Served from {name} at {_km(distance)}{spacing}{near}.'))
    # Cells of the call that served it from far away, pointing at it: at least OVERSHOOT_MIN_KM and OVERSHOOT_ISD times the ISD
    # of their site (else OVERSHOOT_KM) away, the call within their beam (at least 30° each side).
    isds = (ran or {}).get('isds') or {}
    overshooting, seen = [], set()
    for step in trace:
        info, distance = step.get('inventory') or {}, step.get('distance_km')
        if not step.get('site') or distance is None or step['cell'] in seen or point is None or info.get('azimuth') is None:
            continue
        seen.add(step['cell'])
        ratio = serving_isd_ratio(distance, isds.get(step['site']))
        far = ratio >= OVERSHOOT_ISD and distance >= OVERSHOOT_MIN_KM if ratio is not None else distance >= OVERSHOOT_KM
        bearing = _bearing((step['latitude'], step['longitude']), point)
        off = abs((bearing - float(info['azimuth']) + 180) % 360 - 180)
        if far and off <= max(30.0, float(info.get('beamwidth') or 65) / 2):
            spacing = f', {ratio:.1f} times the inter-site distance of its site' if ratio is not None else ''
            overshooting.append(f"{info.get('name') or step['cell']} (Site {step['site_id']}, {step['role_label'].lower()}) from {_km(distance)}"
                                f"{spacing}, {off:.0f}° off its azimuth")
    if overshooting:
        checks.append(_check('overshooting', 'warn', 'Overshooting cell' if len(overshooting) == 1 else 'Overshooting cells',
                             f"{'; '.join(overshooting[:3])}: it reaches the place of the call with its main beam. Its tilt is worth a look."))
    # Cells around with the PCI and channel of a cell of the call.
    flagged = [(site, cell) for site in sites for cell in site['cells'] if cell.get('same_pci')]
    if flagged:
        listed = ', '.join(f"{cell['name'] or cell['identity']} (Site {site['site_id']}, {_km(site['distance_km'])})" for site, cell in flagged[:3])
        more = f' and {len(flagged) - 3} more' if len(flagged) > 3 else ''
        many = len(flagged) > 1
        checks.append(_check('pci', 'warn', 'PCI collision', f'{len(flagged)} cell{"s" if many else ""} around {"share" if many else "shares"} '
                                                              f'the PCI and channel of a cell of the call: {listed}{more}.'))
    elif any(step.get('pci') for step in trace):
        checks.append(_check('pci', 'ok', 'No PCI collision', 'No cell around shares the PCI and channel of the cells of the call.'))
    else:
        checks.append(_check('pci', 'info', 'PCI', 'The CDR gives no PCI of the cells of the call.'))
    # Cells out of service on the sites of the call, or around it.
    own_sites = {step['site'] for step in trace if step.get('site')}
    around = [site for site in sites if site['distance_km'] <= radius_km or site['key'] in own_sites]
    down_own = [(site, cell) for site in around if site['key'] in own_sites for cell in site['cells'] if cell['state'] in OUTAGE_STATES]
    down_around = [site for site in around if site['key'] not in own_sites and any(cell['state'] in OUTAGE_STATES for cell in site['cells'])]
    planned = [site for site in around if any(cell['state'] in PIPELINE_STATES for cell in site['cells'])]
    if down_own:
        states = ', '.join(sorted({cell['state'] for _site, cell in down_own}))
        checks.append(_check('state', 'bad', 'Cells out of service on its sites',
                             f"{len(down_own)} cell{'s' if len(down_own) > 1 else ''} of the sites of the call {'are' if len(down_own) > 1 else 'is'} {states}: "
                             + ', '.join(f"{cell['name'] or cell['identity']} (Site {site['site_id']})" for site, cell in down_own[:4]) + '.'))
    elif down_around:
        checks.append(_check('state', 'warn', 'Cells out of service around', f"{len(down_around)} site{'s' if len(down_around) > 1 else ''} around "
                                                                          'have locked, halted or disabled cells: '
                             + ', '.join(f"Site {site['site_id']} ({_km(site['distance_km'])})" for site in down_around[:4]) + '.'))
    elif planned:
        checks.append(_check('state', 'info', 'Sites planned around', f"{len(planned)} site{'s' if len(planned) > 1 else ''} around "
                                                                     'have cells planned or in progress: '
                             + ', '.join(f"Site {site['site_id']} ({_km(site['distance_km'])})" for site in planned[:4]) + '.'))
    elif around:
        checks.append(_check('state', 'ok', 'Cells in service', 'Every cell of the inventory around is in service.'))
    else:
        checks.append(_check('state', 'info', 'Network state', 'No site of the Network Inventory around.'))
    # Its operator against the others in the tests around.
    names = tests.get('operators') or []
    own_name = _text(call.get('operator')).casefold()
    own = [row for row in tests.get('rows') or [] if str(names[row[2]]).casefold() == own_name]
    others = [row for row in tests.get('rows') or [] if str(names[row[2]]).casefold() != own_name]
    if len(own) < MIN_COMPARED_TESTS or len(others) < MIN_COMPARED_TESTS:
        checks.append(_check('operators', 'info', 'Other operators', f'Not enough tests around to compare the operators ({len(own)} of '
                                                                     f'{operator}, {len(others)} of the others): choose a larger radius or the '
                                                                     'samples of every CDR of its campaign.'))
    else:
        own_failed, other_failed = sum(row[4] for row in own), sum(row[4] for row in others)
        own_rate, other_rate = own_failed / len(own), other_failed / len(others)
        # A two-proportion test: how far its share of tests not completed is above that of the others, given how many each did.
        pooled = (own_failed + other_failed) / (len(own) + len(others))
        spread = math.sqrt(pooled * (1 - pooled) * (1 / len(own) + 1 / len(others)))
        z = (own_rate - other_rate) / spread if spread else 0.0

        def median_rsrp(rows: list[list[Any]]) -> float | None:
            values = sorted(row[5] for row in rows if row[5] is not None)
            return values[len(values) // 2] if values else None

        own_rsrp, other_rsrp = median_rsrp(own), median_rsrp(others)
        rsrp_text = (f'; median LTE RSRP {own_rsrp:.0f} against {other_rsrp:.0f} dBm' if own_rsrp is not None and other_rsrp is not None else '')
        detail = (f'{operator}: {_share(own_failed, len(own))} of {len(own)} tests not completed ({own_failed}); the other operators '
                  f'{_share(other_failed, len(others))} of {len(others)} ({other_failed}){rsrp_text}')
        worse = own_rate >= WORSE_RATIO * other_rate and own_rate - other_rate >= WORSE_POINTS
        if z >= SIGNIFICANT_Z and worse:
            checks.append(_check('operators', 'bad', 'Its network fails more here', f'{detail}: a problem of its network.'))
        elif z >= HINT_Z and own_rate > other_rate:
            checks.append(_check('operators', 'warn', 'Fails a little more than the others',
                                 f'{detail}: more than the others, though not clearly with these tests.'))
        elif other_rate >= PLACE_FAILURES:
            checks.append(_check('operators', 'warn', 'Every operator fails here', f'{detail}: the place (a tunnel, indoors, speed…) may explain it.'))
        else:
            checks.append(_check('operators', 'ok', 'Like the other operators', f'{detail}.'))
    # Other Non-Qualified Calls of its operator at its place, and its hotspot.
    own_entry = next((item for item in failures if item['self']), {})
    place = own_entry.get('place_label') or 'its place'
    same = [item for item in failures if item['same_place']]
    hotspot = [item for item in failures if item['same_hotspot']]
    campaigns = {item['campaign'] for item in same} | {_text(call.get('campaign'))}
    count = len(same) + 1
    tail = f' {len(hotspot)} more in its hotspot.' if hotspot else ''
    if count >= min_calls and len(campaigns) > 1:
        checks.append(_check('repetition', 'bad', 'Repeated issue', f'{count} NQ calls of {operator} at {place} in {len(campaigns)} campaigns.{tail}'))
    elif count >= min_calls:
        checks.append(_check('repetition', 'warn', 'Repeated issue', f'{count} NQ calls of {operator} at {place} in its campaign.{tail}'))
    else:
        checks.append(_check('repetition', 'ok' if not hotspot else 'warn', 'First NQ call at its place' if not hotspot else 'Part of a hotspot',
                             f'No other NQ call of {operator} at {place}.{tail}'))
    # Its cells: ping-pong, many handovers, the cell it failed on.
    cells = [step['cell'] for step in trace if step['role'] != 'nr_leg' and step.get('cell')]
    handovers = max(0, len(cells) - 1)
    pong = next(((cells[index], cells[index + 1]) for index in range(len(cells) - 2)
                 if cells[index] == cells[index + 2] and cells[index] != cells[index + 1]), None)
    # Handovers back to a cell it had left, and in how much distance and time: many in little distance, no dominant cell.
    returns = sum(1 for index in range(2, len(cells)) if cells[index] in cells[:index - 1])
    metres, seconds = (travel or {}).get('metres'), (travel or {}).get('seconds')
    names = {step['cell']: (step.get('inventory') or {}).get('name') or step['cell'] for step in trace if step.get('cell')}
    if pong:
        went = ' and '.join(part for part in (f'{_km(metres / 1000)}' if metres is not None else '', f'{seconds:.0f} s' if seconds else '') if part)
        involved = ', '.join(dict.fromkeys(names.get(cell, cell) for cell in cells if cells.count(cell) > 1))
        level = 'bad' if returns >= 2 and (metres is None or metres <= PING_PONG_METRES) else 'warn'
        checks.append(_check('handovers', level, 'Ping-pong handovers',
                             f"{handovers} handovers{f' in {went}' if went else ''}, {returns} of them back to a cell it had left "
                             f"({involved}): no cell dominates where it was."))
    elif handovers >= MANY_HANDOVERS:
        checks.append(_check('handovers', 'warn', 'Many handovers', f'{handovers} handovers during the call.'))
    elif handovers:
        checks.append(_check('handovers', 'info', 'Handovers', f"{handovers} handover{'s' if handovers > 1 else ''}: it ended on cell {cells[-1]}."))
    elif cells:
        checks.append(_check('handovers', 'ok', 'No handover', f'Cell {cells[0]} served the whole call.'))
    leg = next((step for step in trace if step['role'] == 'nr_leg'), None)
    if leg and not leg.get('site'):
        checks.append(_check('nr_leg', 'info', 'NR leg not found', f"No NR cell with PCI {leg['pci']} on its LTE site or within {NR_LEG_KM:g} km."))
    return checks


def site_decisions(failures: list[dict[str, Any]]) -> dict[str, Any]:
    """The root causes already chosen for the other Non-Qualified Calls at the place of the call (its repetitions) and in its
    hotspot: one group per root category and cause, the most frequent first."""
    related = [item for item in failures if not item['self'] and (item['same_place'] or item['same_hotspot'])]
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for item in related:
        if not (item['root_category'] or item['root_cause']):
            continue
        group = groups.setdefault((item['root_category'], item['root_cause']), {
            'root_domain': item['root_domain'], 'root_category': item['root_category'], 'root_cause': item['root_cause'],
            'calls': 0, 'campaigns': set(), 'statuses': Counter(), 'latest': '', 'join_ids': []})
        group['calls'] += 1
        group['campaigns'].add(item['campaign'])
        group['statuses'][item['status'] or '—'] += 1
        group['latest'] = max(group['latest'], item['start_time'])
        if item['join_id'] and len(group['join_ids']) < 3:
            group['join_ids'].append(item['join_id'])
    ordered = sorted(groups.values(), key=lambda group: (-group['calls'], group['latest']), reverse=False)
    return {
        'related': len(related), 'undecided': sum(not (item['root_category'] or item['root_cause']) for item in related),
        'groups': [{**group, 'campaigns': sorted(group['campaigns']), 'statuses': dict(group['statuses'].most_common())} for group in ordered],
    }


def drive_context(repository: Any, dataset_ids: list[int], call: dict[str, Any], centre: tuple[float, float],
                  operator_label: Callable[[str], str], start_point: tuple[float, float] | None = None) -> dict[str, Any]:
    """The tests of the operator of the call in the minutes before and after it, close to it (its drive): their time from the
    call, result, radio and distance, the call itself marked (the test that started where and when it started)."""
    origin = start_point or centre
    start = _seconds([_text(call.get('start_time'))])[0]
    if math.isnan(start):
        return {'rows': [], 'minutes': DRIVE_MINUTES}
    own = _text(call.get('operator')).casefold()
    found = []
    for dataset_id in dataset_ids:
        entry = _dataset_tests(repository, dataset_id)
        if not entry or 'moment' not in entry:
            continue
        codes = [index for index, name in enumerate(entry['operators']) if str(operator_label(name) or name).casefold() == own]
        if not codes:
            continue
        offsets = entry['moment'] - start
        near = np.flatnonzero(np.isin(entry['operator'], codes) & (np.abs(offsets) <= DRIVE_MINUTES * 60))
        if not len(near):
            continue
        distances = _distances(entry['latitude'][near], entry['longitude'][near], centre)
        from_start = _distances(entry['latitude'][near], entry['longitude'][near], origin)
        for row, distance, gap in zip(near, distances, from_start):
            if distance > DRIVE_KM:
                continue
            offset = float(offsets[row])

            def value(name: str) -> float | None:
                number = float(entry[name][row])
                return None if math.isnan(number) else round(number, 1)

            found.append({
                'offset_s': round(offset), 'time': str(entry['start'][row])[11:19], 'kind': entry['kind'],
                'test': entry['tests'][entry['test'][row]], 'failed': bool(entry['failed'][row]),
                'lte_rsrp': value('lte_rsrp'), 'lte_sinr': value('lte_sinr'), 'nr_rsrp': value('nr_rsrp'), 'nr_sinr': value('nr_sinr'),
                'distance_km': round(float(distance), 3), 'latitude': round(float(entry['latitude'][row]), 6),
                'longitude': round(float(entry['longitude'][row]), 6), 'self': bool(abs(offset) <= 2 and float(gap) <= .05),
            })
    found.sort(key=lambda item: (abs(item['offset_s']), not item['self']))
    rows = sorted(found[:MAX_DRIVE_ROWS], key=lambda item: item['offset_s'])
    return {'rows': rows, 'total': len(found), 'minutes': DRIVE_MINUTES, 'route': drive_route(rows, origin)}


def drive_route(rows: list[dict[str, Any]], start_point: tuple[float, float] | None) -> list[list[float]]:
    """The way of the car through the tests of its drive, in their order: from the call (the test that is the call, else
    where it started) to the tests after it and back to those before it, each one kept only when a car could have driven
    to it from the one kept before it (CAR_SPEED_MS, ROUTE_SLACK_M), so that the tests of another car of the operator
    measuring at the same time nearby are left out. Points of [latitude, longitude, seconds from the call]."""
    own = next((row for row in rows if row.get('self')), None)
    anchor = (own['latitude'], own['longitude'], 0) if own else (start_point[0], start_point[1], 0) if start_point else None
    if anchor is None:
        return []

    def follow(items: list[dict[str, Any]]) -> list[tuple[float, float, float]]:
        kept, last = [], anchor
        for item in items:
            gap = abs(item['offset_s'] - last[2])
            if gap and distance_km((last[0], last[1]), (item['latitude'], item['longitude'])) * 1000 <= CAR_SPEED_MS * gap + ROUTE_SLACK_M:
                last = (item['latitude'], item['longitude'], item['offset_s'])
                kept.append(last)
        return kept

    after = follow([row for row in rows if row['offset_s'] > 0 and row is not own])
    before = follow(sorted((row for row in rows if row['offset_s'] < 0 and row is not own), key=lambda row: -row['offset_s']))
    route = [*reversed(before), anchor, *after]
    return [[round(latitude, 6), round(longitude, 6), round(seconds)] for latitude, longitude, seconds in route] if len(route) > 1 else []


def _destination(point: tuple[float, float], bearing: float, metres: float) -> tuple[float, float]:
    """The place ``metres`` away from ``point`` on ``bearing`` (degrees from north, clockwise)."""
    latitude, longitude, heading = math.radians(point[0]), math.radians(point[1]), math.radians(bearing)
    angle = metres / 6371008.8
    end = math.asin(math.sin(latitude) * math.cos(angle) + math.cos(latitude) * math.sin(angle) * math.cos(heading))
    return math.degrees(end), math.degrees(longitude + math.atan2(math.sin(heading) * math.sin(angle) * math.cos(latitude),
                                                                  math.cos(angle) - math.sin(latitude) * math.sin(end)))


def simulated_way(route: list[list[float]], metres: float | None) -> dict[str, Any] | None:
    """Where a test that gives only where it started (a Data test) can have gone: the distance it travelled, from where it
    started along the way of its car (towards its tests after it, ``by`` after; else on from the one before it, ``by``
    before), straight on once that way runs out. None when the way of its car is unknown."""
    anchor = next((index for index, point in enumerate(route) if point[2] == 0), None)
    if not metres or metres <= 0 or anchor is None:
        return None
    way, left, heading = [(route[anchor][0], route[anchor][1])], float(metres), None
    for latitude, longitude, _seconds in route[anchor + 1:]:
        step = distance_km(way[-1], (latitude, longitude)) * 1000
        if step < 1:
            continue
        heading = _bearing(way[-1], (latitude, longitude))
        if step >= left:
            way.append(_destination(way[-1], heading, left))
            left = 0
            break
        way.append((latitude, longitude))
        left -= step
    by = 'after'
    if heading is None:
        behind = next(((point[0], point[1]) for point in reversed(route[:anchor]) if distance_km((point[0], point[1]), way[0]) * 1000 >= 1), None)
        if behind is None:
            return None
        heading, by = _bearing(behind, way[0]), 'before'
    if left > 0:
        way.append(_destination(way[-1], heading, left))
    return {'points': [[round(latitude, 6), round(longitude, 6)] for latitude, longitude in way], 'by': by}


def site_health(repository: Any, call: dict[str, Any], site_id: str, host: str, operator_label: Callable[[str], str]) -> dict[str, Any] | None:
    """The calls the serving site of the call served in each campaign and NR Mode (their latest version), how many were
    Non-Qualified, for its operator and for every operator, against the NQ rate of its operator over every site."""
    from src.modules import non_qualified_calls as nq
    from src.modules.column_names import campaign_sort_key

    if not site_id:
        return None
    where, params = ('site_id = ? AND host_network = ?', [site_id, host]) if host else ('site_id = ?', [site_id])
    with repository.connection() as connection:
        rows = connection.execute(
            f'SELECT campaign, nr_mode, operator, COUNT(*) AS calls, SUM(is_nq) AS nq FROM {nq.NQ_CALL_POPULATION_TABLE} '
            f'WHERE is_latest = 1 AND {where} GROUP BY campaign, nr_mode, operator', params).fetchall()
        own = _text(call.get('operator')).casefold()
        labels = {str(row['operator']): str(operator_label(str(row['operator'])) or row['operator']) for row in rows}
        own_names = sorted({name for name, label in labels.items() if label.casefold() == own})
        campaigns = sorted({str(row['campaign']) for row in rows})
        totals = {}
        if own_names and campaigns:
            for row in connection.execute(
                    f"SELECT campaign, nr_mode, COUNT(*) AS calls, SUM(is_nq) AS nq FROM {nq.NQ_CALL_POPULATION_TABLE} "
                    f"WHERE is_latest = 1 AND service IN ('voice', 'speech', 'data') "
                    f"AND campaign IN ({', '.join('?' for _ in campaigns)}) AND operator IN ({', '.join('?' for _ in own_names)}) "
                    'GROUP BY campaign, nr_mode', [*campaigns, *own_names]):
                totals[(str(row['campaign']), str(row['nr_mode']))] = (int(row['calls']), int(row['nq'] or 0))
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row['campaign']), str(row['nr_mode']))
        entry = entries.setdefault(key, {'campaign': key[0], 'nr_mode': key[1], 'calls': 0, 'nq': 0, 'all_calls': 0, 'all_nq': 0})
        entry['all_calls'] += int(row['calls'])
        entry['all_nq'] += int(row['nq'] or 0)
        if labels[str(row['operator'])].casefold() == own:
            entry['calls'] += int(row['calls'])
            entry['nq'] += int(row['nq'] or 0)
    result = []
    for key, entry in entries.items():
        operator_calls, operator_nq = totals.get(key, (0, 0))
        result.append({**entry, 'rate': round(entry['nq'] * 100 / entry['calls'], 1) if entry['calls'] else None,
                       'all_rate': round(entry['all_nq'] * 100 / entry['all_calls'], 1) if entry['all_calls'] else None,
                       'operator_rate': round(operator_nq * 100 / operator_calls, 2) if operator_calls else None})
    result.sort(key=lambda item: (campaign_sort_key(item['campaign']), item['nr_mode']), reverse=True)
    return {'site_id': site_id, 'host_network': host, 'campaigns': result}


# ---------------------------------------------------------------------------
# The whole map
# ---------------------------------------------------------------------------
def enclosing_circle(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """The smallest circle (x, y, radius) that holds the points (x, y) of a plane (Welzl, iteratively)."""
    def circle_of(*given: tuple[float, float]) -> tuple[float, float, float]:
        if len(given) == 1:
            return given[0][0], given[0][1], 0.0
        if len(given) == 2:
            (ax, ay), (bx, by) = given
            return (ax + bx) / 2, (ay + by) / 2, math.hypot(ax - bx, ay - by) / 2
        (ax, ay), (bx, by), (cx, cy) = given
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if abs(d) < 1e-9:
            # In a line: the circle of its two farthest points.
            pairs = [(given[i], given[j]) for i in range(3) for j in range(i + 1, 3)]
            return circle_of(*max(pairs, key=lambda pair: math.hypot(pair[0][0] - pair[1][0], pair[0][1] - pair[1][1])))
        ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
        uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
        return ux, uy, math.hypot(ax - ux, ay - uy)

    def inside(circle: tuple[float, float, float], point: tuple[float, float]) -> bool:
        return math.hypot(point[0] - circle[0], point[1] - circle[1]) <= circle[2] + 1e-6

    ordered = sorted(set(points))
    circle = circle_of(ordered[0])
    for i, first in enumerate(ordered):
        if inside(circle, first):
            continue
        circle = circle_of(first)
        for j, second in enumerate(ordered[:i]):
            if inside(circle, second):
                continue
            circle = circle_of(first, second)
            for third in ordered[:j]:
                if not inside(circle, third):
                    circle = circle_of(first, second, third)
    return circle


def enclosing_ellipse(points: list[tuple[float, float]], margin: float) -> tuple[float, float, float, float, float]:
    """An ellipse (x, y, semi-major, semi-minor, angle of the major axis from the x axis in radians) along the main direction
    of the points of a plane that holds them all, ``margin`` wider at its ends and at least that wide."""
    count = len(points)
    mx, my = sum(x for x, _ in points) / count, sum(y for _, y in points) / count
    sxx = sum((x - mx) ** 2 for x, _ in points)
    syy = sum((y - my) ** 2 for _, y in points)
    sxy = sum((x - mx) * (y - my) for x, y in points)
    angle = 0.5 * math.atan2(2 * sxy, sxx - syy)
    ux, uy = math.cos(angle), math.sin(angle)
    along = [(x - mx) * ux + (y - my) * uy for x, y in points]
    across = [-(x - mx) * uy + (y - my) * ux for x, y in points]
    # Centred on the middle of the points along its axis.
    shift = (max(along) + min(along)) / 2
    mx, my = mx + shift * ux, my + shift * uy
    along = [value - shift for value in along]
    semi_major = max(abs(value) for value in along) * 1.12 + margin
    semi_minor = max([margin] + [abs(v) / math.sqrt(max(1e-9, 1 - (u / semi_major) ** 2)) + margin for u, v in zip(along, across)])
    return mx, my, max(semi_major, semi_minor), semi_minor, angle


def group_rings(repository: Any, call: dict[str, Any], failed_at: tuple[float, float] | None = None) -> list[dict[str, Any]]:
    """The shapes of the groups of a call, as the Groups slide of the presentation draws them: a circle around the NQ calls of
    each cluster and an ellipse along those of each time-window issue (its drive) that make its hotspot, which is what they
    make together (their envelope with the OR join, where they meet with AND, drawn by the page); its own cluster and
    time-window issue whole (with the calls of the campaigns of its Cluster period), those of the other calls of its hotspot
    with its calls. A call in no hotspot takes the shapes of its cluster and its time-window issue. Every NQ call of its
    groups is inside one: a call of its hotspot in neither takes a circle of the whole hotspot. Each shape the smallest that
    holds its calls (those of the call itself also where it failed, ``failed_at``, as the map places it, besides where it
    started, as the rules measure), a little wider; each with the key of its group, and a time window with where its
    failures started in their order (its ``path``). None for a call in no group of 2 calls or more."""
    from src.modules import non_qualified_calls as nq
    from src.modules.nq_prioritization import PRIORITY_TABLE

    key = call.get('parent_key') or call['call_key']
    select = (f'SELECT p.call_key, p.cluster_key, p.cluster_size, p.repeat_key, p.repeat_size, p.consecutive_key, p.consecutive_size, '
              f'p.isd_km, l.latitude, l.longitude, l.start_time FROM {PRIORITY_TABLE} p '
              f'JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = p.call_key')
    with repository.connection() as connection:
        own = connection.execute(f'{select} WHERE p.call_key = ?', (key,)).fetchone()
        if own is None:
            return []

        def grouped(row: Any, column: str, size: str) -> str:
            return _text(row[column]) if _text(row[column]) and (row[size] or 0) >= 2 else ''
        hotspot = grouped(own, 'cluster_key', 'cluster_size')
        hotspot_rows = [dict(row) for row in connection.execute(f'{select} WHERE p.cluster_key = ?', (hotspot,))] if hotspot else []
        # Its own groups, and with a hotspot those of every call of it.
        wanted = {('cluster', grouped(row, 'repeat_key', 'repeat_size')) for row in [own, *hotspot_rows]}
        wanted |= {('run', grouped(row, 'consecutive_key', 'consecutive_size')) for row in [own, *hotspot_rows]}
        wanted = {(kind, value) for kind, value in wanted if value}
        if not wanted and not hotspot:
            return []
        members: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for kind, column in (('cluster', 'repeat_key'), ('run', 'consecutive_key')):
            values = [value for found, value in wanted if found == kind]
            if values:
                for row in connection.execute(f'{select} WHERE p.{column} IN ({", ".join("?" for _ in values)})', values):
                    members.setdefault((kind, _text(row[column])), []).append(dict(row))
    own_groups = {('cluster', grouped(own, 'repeat_key', 'repeat_size')), ('run', grouped(own, 'consecutive_key', 'consecutive_size'))}
    in_hotspot = {row['call_key'] for row in hotspot_rows}
    origin = _position(own['latitude'], own['longitude']) or _position(call.get('latitude'), call.get('longitude'))
    if origin is None:
        return []
    scale = 6371008.8 * math.pi / 180

    def plane(row: dict[str, Any]) -> tuple[float, float] | None:
        found = _position(row['latitude'], row['longitude'])
        return None if found is None else ((found[1] - origin[1]) * scale * math.cos(math.radians(origin[0])), (found[0] - origin[0]) * scale)

    failed = plane({'latitude': failed_at[0], 'longitude': failed_at[1]}) if failed_at else None

    def shape_of(kind: str, rows: list[dict[str, Any]], is_own: bool, key: str = '') -> dict[str, Any] | None:
        points = [point for row in rows if (point := plane(row)) is not None]
        if is_own and failed is not None:
            points.append(failed)
        if not points:
            return None
        if kind == 'run' and len(set(points)) > 1:
            x, y, radius, minor, angle = enclosing_ellipse(points, 40)
        else:
            x, y, radius = enclosing_circle(points)
            radius = max(radius * 1.04 + 10, 50)
            minor, angle = radius, 0.0
        found = {'kind': kind, 'own': is_own, 'key': key, 'calls': len(rows), 'metres': round(radius), 'xy': (x, y),
                 'centre': [origin[0] + y / scale, origin[1] + x / (scale * math.cos(math.radians(origin[0])))],
                 'minor_metres': round(minor), 'angle': round(angle, 4)}
        if kind == 'run':
            found['path'] = [list(position) for row in sorted(rows, key=lambda item: (_text(item['start_time']), item['call_key']))
                             if (position := _position(row['latitude'], row['longitude'])) is not None]
        return found
    rings = []
    for (kind, value), rows in sorted(members.items(), key=lambda item: (item[0] not in own_groups, item[0])):
        is_own = (kind, value) in own_groups
        # The groups of the other calls of its hotspot with the calls of the hotspot (a cluster also counts the campaigns of
        # its Cluster period, which the hotspot leaves out).
        found = shape_of(kind, rows if is_own or not in_hotspot else [row for row in rows if row['call_key'] in in_hotspot], is_own, value)
        if found:
            rings.append(found)

    def holds(ring: dict[str, Any], point: tuple[float, float]) -> bool:
        dx, dy = point[0] - ring['xy'][0], point[1] - ring['xy'][1]
        along = dx * math.cos(ring['angle']) + dy * math.sin(ring['angle'])
        across = -dx * math.sin(ring['angle']) + dy * math.cos(ring['angle'])
        return (along / ring['metres']) ** 2 + (across / max(1, ring['minor_metres'])) ** 2 <= 1.0001
    outside = [row for row in hotspot_rows if (point := plane(row)) is not None and not any(holds(ring, point) for ring in rings)]
    if outside:
        found = shape_of('hotspot', hotspot_rows, True)
        if found:
            rings.append(found)
    isd = _number(own['isd_km'])
    names = {'cluster': 'cluster', 'run': 'time window', 'hotspot': 'hotspot'}
    for ring in rings:
        del ring['xy']
        size = f"{_km(ring['metres'] / 1000)}" + (f" ({round(ring['metres'] / (isd * 1000), 2):g} ISD)" if isd else '')
        reach = f"along {_km(ring['metres'] * 2 / 1000)}" if ring['kind'] == 'run' else f'within {size}'
        ring['label'] = f"{'Its' if ring['own'] else 'A'} {names[ring['kind']]}: {ring['calls']} NQ calls {reach}"
    return rings


def call_map(repository: Any, call_key: str, *, radius_km: Any = None, tests: str = DEFAULT_TEST_SCOPE, campaigns: Any = ()
             ) -> dict[str, Any] | None:
    """Everything the map of a call shows around where it failed (see the module); None for an unknown call. Without
    ``radius_km`` the radius holds the NQ calls of its hotspot and its cluster (``group_radius``), else it is the default
    one. ``campaigns``: those chosen in the filters of the page, for the samples of Selected campaigns."""
    from src.modules import non_qualified_calls as nq
    from src.modules.inventory_insights import configured_vendor_colours
    from src.modules.nq_prioritization import call_kind
    from src.modules.operator_roles import FOCUS, focus_operators, labels_with_role
    from src.modules.serving_cells import load_serving_networks, serving_families
    from src.modules.value_maps import ValueMapper, field_kind

    scope = tests if tests in TEST_SCOPES else DEFAULT_TEST_SCOPE
    options = nq.list_options(repository)
    with repository.connection() as connection:
        found = nq._call_row(connection, call_key, nq.untracked_status(repository, options), repository)
        if found is None:
            return None
        call = nq._call_payload(found)
        source = nq.source_row(connection, repository.db_path, call['dataset_id'], call['source_row_id'])
        dataset = connection.execute('SELECT file_name FROM datasets WHERE id = ?', (int(call['dataset_id']),)).fetchone()
    row = source or {}
    columns = list(row)
    service = _text(call.get('service'))
    fields_profile = workspace_field_profile(repository)
    positions = call_positions(service, row, columns, fields_profile) if row else {'start': None, 'end': None}
    if not positions['start']:
        positions['start'] = _position(call.get('latitude'), call.get('longitude'))
    if not positions['start'] and _text(call.get('l3_log')) and _text(call.get('join_id')):
        # The CDR without its position: where its Layer 3 - DT Logs started and ended (that of UE A or Data first).
        from src.modules import l3_dt_logs

        sessions = l3_dt_logs.sessions_of_join_ids(repository, [call['join_id']]).get(_text(call['join_id']).casefold(), [])
        session = next((item for item in sessions if item['ue'] in {'A', 'Data'}), sessions[0] if sessions else None)
        if session:
            positions = {'start': _position(session.get('first_latitude'), session.get('first_longitude')),
                         'end': _position(session.get('last_latitude'), session.get('last_longitude'))}
    notes = []
    config = load_serving_networks(repository)
    families = tuple(serving_families(call.get('operator'), config))
    cells, snapshots = inventory_cells(repository, families)
    colours = configured_vendor_colours(repository.list_vendor_mapping_groups())
    trace = resolve_trace(cell_trace(service, row, columns, call.get('cell_id'), fields_profile), cells, families, positions,
                          float(config.get('max_distance_km') or 30.0), colours)
    point = positions['end'] or positions['start']
    if point is None:
        located = next((step for step in reversed(trace) if step.get('site')), None)
        if located is None:
            raise ValueError('The CDR does not give the position of this call, and its cells are not in a Network Inventory: '
                             'there is nothing to place on the map.')
        point = (located['latitude'], located['longitude'])
        notes.append('The CDR does not give the position of this call: the map is centred on the site of its last cell.')
    group = group_radius(repository, call, point) if radius_km is None else None
    radius = (group or DEFAULT_RADIUS_KM) if radius_km is None else normalise_radius(radius_km)
    anchor = next((step['site'] for step in reversed(trace) if step.get('site') and step.get('technology') == 'LTE'), '')
    leg = (nr_leg(service, row, columns, cells, families, point, anchor, colours, fields_profile)
           if _text(call.get('nr_mode')).upper() != 'SA' else None)
    # Every cell of the call in words (also those the inventory does not hold, such as 2G and 3G cells), by its inventory
    # name when it has one.
    _column, trace_text = _first_value(row, columns, fields_profile.rf_field_aliases['cell_trace'].get(service, ()))
    call_cells = labelled_cells(cell_steps(trace_text) or cell_steps(call.get('cell_id')),
                                {step['cell']: step['inventory']['name'] for step in trace if step.get('inventory') and step['inventory'].get('name')},
                                {step['cell']: step['distance_km'] for step in trace if step.get('far') and step.get('distance_km') is not None})
    if leg:
        trace.append(leg)
        if leg.get('inventory'):
            call_cells.append({'role': 'nr_leg', 'technology': 'NR', 'label': cell_label(leg, leg['inventory'].get('name') or '')})
    keep = {step['site'] for step in trace if step.get('site')}
    # Its serving site: that of the cell that served its end (where it failed), else of the one that served its start, else
    # the site the CDR gives (from the cell that served its start).
    end_step = next((step for step in reversed(trace) if step.get('site') and step['role'] in ('end', 'both')), None)
    start_step = next((step for step in trace if step.get('site') and step['role'] in ('start', 'both')), None)
    chosen = end_step or start_step
    if chosen:
        serving_key, serving_site = chosen['site'], chosen['site_id']
        serving_host = chosen.get('host_network') or chosen.get('network') or ''
        serving_role, serving_distance = ('end' if chosen is end_step else 'start'), chosen.get('distance_km')
    else:
        serving_key, serving_site = '', _text(row.get('Serving_Site_ID')) or _text(call.get('site_id'))
        serving_host = _text(row.get('Serving_Host_Network')) or _text(call.get('host_network'))
        serving_role, serving_distance = ('start' if serving_site else ''), _number(row.get('Serving_Distance_km'))
    # Where it started and where it ended: the sites of the cells that served them (the start also the site the CDR gives),
    # else, for a cell the inventory does not hold (such as a 2G or 3G cell), the nearest site of the networks serving its
    # operator to where it started and where it failed, an estimate (often a site with that cell too).
    from src.modules import ran_context

    index = ran_context.ran_index(cells) if not cells.empty else None
    path = [cell for cell in call_cells if cell['role'] != 'nr_leg']
    reach = float(config.get('max_distance_km') or 30.0)
    ends: dict[str, dict[str, Any]] = {}
    for role, step, where, cell in (('start', start_step, positions['start'] or point, path[0] if path else None),
                                     ('end', end_step, point, path[-1] if path else None)):
        site = index.sites.get(step['site']) if index and step else None
        if role == 'start' and site is None and index and not end_step and serving_site:
            site = next((index.sites[key] for key in (f'{family}|{serving_site}'.casefold() for family in families) if key in index.sites
                         and (not serving_host or serving_host.casefold() in {index.sites[key]['host_network'].casefold(),
                                                                              index.sites[key]['network'].casefold()})), None)
        estimated = site is None
        if estimated and index and cell and where:
            site = index.nearest(where, families)
            site = site if site and site['distance_km'] <= reach else None
        if site:
            ends[role] = {'key': site['key'], 'site_id': site['site_id'], 'network': site['network'], 'host_network': site['host_network'],
                          'estimated': estimated, 'distance_km': round(distance_km(where, (site['latitude'], site['longitude'])), 3) if where else None,
                          'cell': cell['label'] if cell else '', 'technology': cell['technology'] if cell else ''}
            keep.add(site['key'])
    sites = nearby_sites(cells, point, radius, keep, colours)
    for site in sites:
        site['roles'] = [step['role_label'] for step in trace if step.get('site') == site['key']]
        site['ends'] = [{'role': role, 'estimated': end['estimated']} for role, end in ends.items() if end['key'] == site['key']]
        site['serving'] = site['key'] == serving_key if serving_key else bool(serving_site) and site['site_id'].casefold() == serving_site.casefold() and (
            not serving_host or serving_host.casefold() in {site['host_network'].casefold(), site['network'].casefold()})
    flag_same_pci(sites, trace)
    end_cell = next((cell for cell in reversed(call_cells) if cell['role'] in ('end', 'both')), None)
    if not snapshots:
        notes.append(f"No Network Inventory lists the cells of the networks that serve {call.get('operator') or 'this operator'}: "
                     'the map shows no sites. Upload one in Workspace to see them.')
    elif call_cells and not any(step.get('site') for step in trace):
        notes.append(f"The cells of this call ({', '.join(cell['label'] for cell in call_cells)}) are not in the Network Inventory "
                     f'of the networks that serve its operator within {_km(reach)} of it: its serving site and cell cannot be placed'
                     + ('; the dashed rings mark the nearest sites to where it started and failed.' if any(end['estimated'] for end in ends.values()) else '.'))
    elif serving_role == 'start' and end_cell:
        notes.append(f"The cell that served the end of this call ({end_cell['label']}) is not in the Network Inventory of the "
                     f'networks that serve its operator within {_km(reach)} of it: the site ringed is the one that served its start.')
    failures, failures_left_out, groups = nearby_failures(repository, call, point, radius)
    name_failure_cells(failures, cells, families, float(config.get('max_distance_km') or 30.0))
    # The operators of the tests with the labels of the Operator Maps, as the calls show them.
    mapper = ValueMapper.from_settings(repository.chart_mapping_settings())
    datasets = test_datasets(repository, call, scope, campaigns)
    test_points = nearby_tests(repository, datasets, point, radius,
                               lambda value: mapper.map(field_kind('operator'), value))
    if test_points['truncated']:
        notes.append(f"The area has {test_points['total']:,} tests: the map shows the {len(test_points['rows']):,} nearest "
                     f"(within {test_points['covered_km']:g} km).")
    from src.modules.nq_prioritization import load_settings as prioritization_settings

    label = lambda value: mapper.map(field_kind('operator'), value)  # noqa: E731 - the label of an Operator in the Operator Maps.
    # The inter-site distance of the serving site and the nearest site of the networks serving the operator (ran_context).
    serving_step = next((step for step in reversed(trace) if step.get('site') and step['role'] in ('end', 'both')), None)
    nearest = index.nearest(point, families) if index else None
    ran = {'serving_isd': index.isd(serving_step['site']) if index and serving_step else None,
           'nearest': {**nearest, 'isd_km': index.isd(nearest['key'])} if nearest else None}
    # How far and how long it went: the distance a Data test gives (Test_Distance, metres), else from where it started to
    # where it ended; its duration.
    _column, travelled = _first_value(row, columns, ('Test_Distance',))
    travelled_m = _number(travelled)
    _column, lasted = _first_value(row, columns, ('Test_Duration', 'Call_Duration', 'duration_seconds'))
    travel = {'metres': travelled_m if travelled_m is not None else (round(distance_km(positions['start'], positions['end']) * 1000)
                                                                       if positions['start'] and positions['end'] else None),
              'seconds': _number(lasted)}
    ran['isds'] = {step['site']: index.isd(step['site']) for step in trace if step.get('site')} if index else {}
    checks = diagnosis(call, call_radio(service, row, columns, fields_profile), trace, sites, failures, test_points, radius,
                       int(prioritization_settings(repository).get('min_calls') or 2), ran, point, travel)
    # What its Layer 3 - DT Logs show in its last seconds (l3_dt_logs), each pointing at its moment of the log.
    if _text(call.get('join_id')) and _text(call.get('l3_log')):
        from src.modules import l3_dt_logs

        l3_dt_logs.ensure_evidence(repository)
        sessions = l3_dt_logs.sessions_of_join_ids(repository, [call['join_id']], evidence=True).get(_text(call['join_id']).casefold(), [])
        checks += l3_dt_logs.map_checks(sessions)
    drive = drive_context(repository, datasets, call, point, label, positions['start'])
    # Its way: from where it started to where it ended, else (a Data test) simulated along the way of its car. Where each
    # handover took place along it, an estimate by the time on each band of its RAT timeline (that of the A side of a Voice
    # call, the PCell one of a Data test, which names its bands).
    way = ({'points': [list(positions['start']), list(positions['end'])], 'by': 'ends'} if positions['start'] and positions['end']
           else simulated_way(drive.get('route') or [], travelled_m))
    _column, rat_timeline = _first_value(row, columns, ('RAT_Timeline_A', 'PCell_RAT_Timeline', 'RAT_Timeline'))
    handovers = handover_points([step for step in trace if step['role'] != 'nr_leg'], rat_timeline,
                                [tuple(point) for point in way['points']] if way else None,
                                {step['cell']: step['band'] for step in cell_steps(trace_text) if step['cell'] and step['band']})
    health = site_health(repository, call, serving_site, serving_host, label)
    return {
        'call': {
            'call_key': call['call_key'], 'parent_key': _text(call.get('parent_key')), 'join_id': _text(call.get('join_id')),
            # The UEs of the call with a session in the Layer 3 - DT Logs, whose layers the map reads apart (l3_dt_logs).
            'l3_log': _text(call.get('l3_log')),
            'service': service, 'service_label': call.get('service_label'), 'operator': _text(call.get('operator')),
            'kind': call_kind(service, call.get('test_name'), call.get('session_type')),
            'campaign': _text(call.get('campaign')), 'nr_mode': _text(call.get('nr_mode')), 'result': _text(call.get('result')),
            'technology': _text(call.get('technology')), 'test_name': _text(call.get('test_name')),
            'failure_phase': _text(call.get('failure_phase')), 'failure_technology': _text(call.get('failure_technology')),
            'failure_classification': _text(call.get('failure_classification')), 'failure_category': _text(call.get('failure_category')),
            'failure_subcategory': _text(call.get('failure_subcategory')), 'failure_comment': _text(call.get('failure_comment')),
            'start_time': _text(call.get('start_time')), 'end_time': _text(call.get('end_time')), 'city': _text(call.get('city')),
            'environment': _text(call.get('environment')), 'dataset_id': int(call['dataset_id']),
            'dataset_name': _text(dataset['file_name']) if dataset else '',
            'start': list(positions['start']) if positions['start'] else None, 'end': list(positions['end']) if positions['end'] else None,
            # Its serving site (``serving_role``: of the cell that served its end, or its start) and its cells in words.
            'serving_site': serving_site, 'serving_host': serving_host, 'serving_role': serving_role,
            'serving_distance_km': serving_distance, 'cells': call_cells, 'handovers': handovers,
            # How far a Data test went from where it started (the CDR gives no other place of it), and its way: from where it
            # started to where it ended (``by`` ends), else simulated along the way of its car (else its travelled zone).
            'travelled_m': travelled_m, 'travelled_s': travel['seconds'], 'way': way,
            # The sites where it started and ended (``estimated``: the nearest to it, its cell not in the inventory).
            'ends': {role: {key: end[key] for key in ('site_id', 'network', 'host_network', 'estimated', 'distance_km', 'cell', 'technology')}
                     for role, end in ends.items()},
            'radio': radio_values(row, columns),
        },
        # How far from the call a cell of its trace is looked for by its identity alone (farther, also by its PCI and channel).
        'cell_reach_km': reach, 'centre': [point[0], point[1]], 'radius_km': radius, 'radii_km': sorted({*RADII_KM, radius}), 'group_radius_km': group,
        'tests_scope': scope, 'tests_scopes': TEST_SCOPES,
        # The Focus operators of the Operator Maps: their labels, and with every name of the CDRs they stand for.
        'focus_labels': labels_with_role(repository, FOCUS), 'focus_operators': focus_operators(repository),
        'families': list(families), 'snapshots': snapshots, 'trace': trace, 'sites': sites, 'failures': failures,
        'tests': test_points, 'classes': sample_classes(), 'notes': notes,
        'failures_left_out': failures_left_out, 'failures_max': MAX_FAILURES, 'groups': groups, 'rings': group_rings(repository, call, point),
        'hotspot_join': str(prioritization_settings(repository).get('hotspot_join') or 'or'),
        'diagnosis': checks, 'decisions': site_decisions(failures), 'drive': drive, 'site_health': health,
        'basemap': {'url_template': OSM_TILES, 'attribution': OSM_ATTRIBUTION},
    }


# Below the Very poor RSRP of Network Insights, the level the Layer 3 - DT Logs draw too (their legend starts at −120 dBm).
RSRP_FLOOR_CLASS = ('Extremely poor', -120.0, '#8B0A1A')


def sample_classes() -> dict[str, list[dict[str, Any]]]:
    """The levels of the RSRP and SINR of the samples, as Network Insights colours them, with Extremely poor below
    −120 dBm: the same on both maps for the samples of the CDRs and the points of the Layer 3 - DT Logs."""
    from src.modules.network_insights import RSRP_CLASSES, SINR_CLASSES

    floor_label, floor, floor_colour = RSRP_FLOOR_CLASS
    rsrp = [(label, floor if math.isinf(lower) else lower, colour) for label, lower, colour in RSRP_CLASSES]
    rsrp.append((floor_label, float('-inf'), floor_colour))
    return {
        'rsrp': [{'label': label, 'lower': None if math.isinf(lower) else lower, 'colour': colour} for label, lower, colour in rsrp],
        'sinr': [{'label': label, 'lower': None if math.isinf(lower) else lower, 'colour': colour} for label, lower, colour in SINR_CLASSES],
    }


# ---------------------------------------------------------------------------
# NQ Maps: the sites and the RSRP / SINR samples of the area shown
# ---------------------------------------------------------------------------
# The sites show from this zoom level of the map, the samples of the CDRs from this one.
AREA_SITES_ZOOM = 11
AREA_TESTS_ZOOM = 13
MAX_AREA_TESTS = 20000
# The located tests of a CDR for the maps of an area, kept in the cache of the workspace (one small Parquet file per CDR,
# until its calls are indexed again): moving the map reads only the tests of the area shown.
AREA_TESTS_VERSION = 1
AREA_TEST_COLUMNS = ('dataset_id', 'kind', 'lat', 'lon', 'operator', 'failed', 'lte_rsrp', 'lte_sinr', 'nr_rsrp', 'nr_sinr', 'test', 'start')


def area_centre(bbox: Any) -> tuple[tuple[float, float], float]:
    """The centre of an area (south, west, north, east) and the radius in km of the circle around it."""
    south, west, north, east = (float(value) for value in bbox)
    centre = ((south + north) / 2, (west + east) / 2)
    return centre, max(.05, distance_km(centre, (north, east)))


def area_sites(repository: Any, operators: Any, bbox: Any) -> dict[str, Any]:
    """The inventory sites (with their cells) of the networks that serve ``operators`` in the area, nearest to its centre
    first (MAX_SITES at most), as the map of a call draws them."""
    from src.modules.inventory_insights import configured_vendor_colours
    from src.modules.serving_cells import load_serving_networks, serving_families

    config = load_serving_networks(repository)
    families = tuple(dict.fromkeys(family for operator in sorted({_text(value) for value in operators} - {''})
                                   for family in serving_families(operator, config)))
    cells, snapshots = inventory_cells(repository, families)
    centre, radius = area_centre(bbox)
    sites = nearby_sites(cells, centre, radius, set(), configured_vendor_colours(repository.list_vendor_mapping_groups()))
    for site in sites:
        site.update(roles=[], ends=[], serving=False)
    return {'sites': sites, 'families': list(families), 'snapshots': snapshots, 'truncated': len(sites) >= MAX_SITES}


def area_test_datasets(repository: Any, calls: list[dict[str, Any]]) -> list[int]:
    """The CDRs whose tests an area shows: every CDR with the latest calls of the campaigns and NR Modes of ``calls``."""
    from src.modules import non_qualified_calls as nq

    pairs = sorted({(_text(call.get('campaign')), _text(call.get('nr_mode'))) for call in calls if _text(call.get('campaign'))})
    if not pairs:
        return []
    condition = ' OR '.join('(campaign = ? AND nr_mode = ?)' for _pair in pairs)
    with repository.connection() as connection:
        rows = connection.execute(
            f"SELECT DISTINCT dataset_id FROM {nq.NQ_CALL_POPULATION_TABLE} WHERE is_latest = 1 AND service IN ('voice', 'speech', 'data') "
            f'AND ({condition}) ORDER BY dataset_id', [value for pair in pairs for value in pair]).fetchall()
    return [int(row[0]) for row in rows]


def _area_tests_file(repository: Any, dataset_id: int) -> Any:
    """The file of the located tests of a CDR for the maps of an area (AREA_TEST_COLUMNS), written from its tests the
    first time; None for a CDR without located tests."""
    import duckdb

    from src.modules import non_qualified_calls as nq

    with repository.connection() as connection:
        source = connection.execute(f'SELECT revision FROM {nq.NQ_CALL_SOURCES_TABLE} WHERE dataset_id = ?', (int(dataset_id),)).fetchone()
    revision = hashlib.sha1(f"{_text(source['revision']) if source else ''}|{AREA_TESTS_VERSION}".encode()).hexdigest()[:12]
    folder = workspace_cache.of_database(repository.db_path, workspace_cache.NQ_CALLS)
    target = folder / f'tests-{int(dataset_id)}-{revision}.parquet'
    empty = target.with_suffix('.none')
    if target.exists():
        return target
    if empty.exists():
        return None
    entry = _dataset_tests(repository, int(dataset_id))
    folder.mkdir(parents=True, exist_ok=True)
    for stale in folder.glob(f'tests-{int(dataset_id)}-*'):
        if stale.name not in {target.name, empty.name}:
            stale.unlink(missing_ok=True)
    if not entry or not len(entry['latitude']):
        empty.touch()
        return None
    frame = pd.DataFrame({
        'dataset_id': np.full(len(entry['latitude']), int(dataset_id), dtype=np.int64), 'kind': entry['kind'],
        'lat': entry['latitude'], 'lon': entry['longitude'], 'operator': np.asarray(entry['operators'], dtype=object)[entry['operator']],
        'failed': entry['failed'], **{name: entry[name] for name in ('lte_rsrp', 'lte_sinr', 'nr_rsrp', 'nr_sinr')},
        'test': np.asarray(entry['tests'], dtype=object)[entry['test']], 'start': entry['start'],
    })
    partial = target.with_suffix('.partial')
    with duckdb.connect() as duck:
        duck.register('tests', frame)
        duck.execute(f"COPY (SELECT * FROM tests) TO '{str(partial).replace(chr(39), chr(39) * 2)}' (FORMAT parquet)")
    partial.replace(target)
    return target


def area_tests(repository: Any, dataset_ids: list[int], bbox: Any, operator_label: Callable[[str], str] = str) -> dict[str, Any]:
    """The tests of the CDRs in the area (south, west, north, east), MAX_AREA_TESTS at most (an even sample of them when
    there are more), as compact rows in the form of nearby_tests."""
    import duckdb

    south, west, north, east = (float(value) for value in bbox)
    files = [str(path) for dataset_id in dataset_ids if (path := _area_tests_file(repository, int(dataset_id)))]
    result: dict[str, Any] = {'operators': [], 'kinds': [], 'test_names': [], 'cdrs': [], 'rows': [], 'total': 0, 'truncated': False,
                              'columns': ['latitude', 'longitude', 'operator', 'kind', 'failed', 'lte_rsrp', 'lte_sinr', 'nr_rsrp', 'nr_sinr', 'test', 'start', 'cdr']}
    if not files:
        return result
    source = f"read_parquet([{', '.join(chr(39) + file.replace(chr(39), chr(39) * 2) + chr(39) for file in files)}], union_by_name = true)"
    inside = 'lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?'
    with duckdb.connect() as duck:
        total = int(duck.execute(f'SELECT COUNT(*) FROM {source} WHERE {inside}', [south, north, west, east]).fetchone()[0])
        query = f"SELECT {', '.join(AREA_TEST_COLUMNS)} FROM {source} WHERE {inside}"
        if total > MAX_AREA_TESTS:
            query = f'SELECT * FROM ({query}) USING SAMPLE reservoir({MAX_AREA_TESTS} ROWS) REPEATABLE (7)'
        rows = duck.execute(query, [south, north, west, east]).fetchall()
    ids = sorted({int(row[0]) for row in rows})
    placeholders = ', '.join('?' for _ in ids) or 'NULL'
    with repository.connection() as connection:
        stages = {int(row['dataset_id']): _text(row['cdr_stage']) for row in connection.execute(
            f'SELECT dataset_id, cdr_stage FROM dataset_profiles WHERE dataset_id IN ({placeholders})', ids)}
        profiles = _cdr_profiles(connection, str(repository.db_path), ids)
    operators: dict[str, int] = {}
    labels: dict[str, str] = {}
    names: dict[str, int] = {}
    cdrs: dict[int, int] = {}
    kinds: dict[str, int] = {}

    def rounded(value: Any, digits: int = 1) -> float | None:
        return None if value is None or not math.isfinite(float(value)) else round(float(value), digits)

    for dataset_id, kind, lat, lon, operator, failed, lte_rsrp, lte_sinr, nr_rsrp, nr_sinr, test, start in rows:
        source_name = _text(operator)
        if source_name not in labels:
            labels[source_name] = str(operator_label(source_name) or source_name)
        label = labels[source_name]
        kinds.setdefault(kind, len(kinds))
        operators.setdefault(label, len(operators))
        names.setdefault(_text(test), len(names))
        if int(dataset_id) not in cdrs:
            profile = profiles.get(int(dataset_id))
            cdrs[int(dataset_id)] = len(result['cdrs'])
            result['cdrs'].append({'dataset_id': int(dataset_id), 'kind': kind, 'campaign': _text(profile['campaign']) if profile else '',
                                   'nr_mode': _text(profile['nr_mode']) if profile else '', 'stage': stages.get(int(dataset_id), '')})
        result['rows'].append([round(float(lat), 6), round(float(lon), 6), operators[label], kinds[kind], int(bool(failed)),
                               rounded(lte_rsrp), rounded(lte_sinr), rounded(nr_rsrp), rounded(nr_sinr), names[_text(test)],
                               _text(start), cdrs[int(dataset_id)]])
    result.update(operators=list(operators), kinds=list(kinds), test_names=list(names), total=total, truncated=total > len(rows))
    return result
