"""Postal Codes of a workspace: the areas of the postal codes of each country, for the Points Lost Map.

No free set of postal polygons covers the world, so the areas are worked out from the postal code points GeoNames publishes
for about 120 countries (https://www.geonames.org, Creative Commons Attribution 4.0): each code takes the land closest to
its points (Voronoi cells cut to its country). They are approximate, not the official borders, and the codes that only
have a point shared with others (the centre of a city, in the UK) are one area named after all of them.

The layer of a country stored with the workspace comes first (downloaded from GeoNames, or imported from a GeoJSON or a
zipped Shapefile, such as a licensed map), then the one shipped with the application in ``assets/map-areas/postal``. A
Saved Filter that asks for Postal Codes downloads those its countries lack. Layers travel with the Mappings & Reference
Data in Import / Export, transfers and backups. Tests are placed while the map is drawn, so the CDRs do not change.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import re
import urllib.error
import zipfile
from functools import lru_cache
from typing import Any, Callable, Iterable

import pandas as pd

from src.config import PROJECT_ROOT
from src.modules.map_areas import (
    MAX_UNITS, AreaIndex, _features_boundaries, _fetch, _tolerance, _valid_polygons, country_codes, country_name,
    country_outline, delete_layer, import_layer, layer_boundaries, list_layers, save_layer,
)
from src.modules.map_areas import bundled_rings as _map_area_rings

TABLE = 'map_area_postal_layers'
TABLE_TITLE = 'Map Area Postal Layers'
BUNDLED_DIR = PROJECT_ROOT / 'assets' / 'map-areas' / 'postal'
GEONAMES_URL = 'https://download.geonames.org/export/zip/{code}.zip'
GEONAMES_LICENSE = 'Creative Commons Attribution 4.0'
GEONAMES_ATTRIBUTION = 'GeoNames, www.geonames.org; areas worked out from its postal code points'
LEVEL_LABEL = 'postal code'
# A GeoNames file bigger than this is not a list of postal codes.
MAX_FILE_BYTES = 256 * 1024 * 1024
# The land of a country reaches a little off its coast, so that tests by the sea (bridges, piers) keep their code.
COAST_BUFFER = .02
# The countries with at least this share of the sampled tests have their postal codes downloaded.
MIN_COUNTRY_SHARE = .01
SAMPLE_ROWS = 2000


def wanted(saved_filter: dict[str, Any] | None) -> bool:
    """Whether a Saved Filter asks for Postal Codes (an option of its Geographical Areas)."""
    summary = (saved_filter or {}).get('area_summary') or (saved_filter or {}).get('geographical_areas')
    return bool(isinstance(summary, dict) and summary.get('postal_codes'))


# -- layers ---------------------------------------------------------------------------------------
def list_postal_layers(repository: Any) -> list[dict[str, Any]]:
    return list_layers(repository, table=TABLE)


def delete_postal_layer(repository: Any, layer_id: int) -> bool:
    return delete_layer(repository, layer_id, table=TABLE)


def import_postal_layer(repository: Any, filename: str, content: bytes, *, country_code: str, name_field: str,
                        username: str) -> dict[str, Any]:
    """A layer from a GeoJSON or a ZIP holding one Shapefile, such as a map the workspace has a licence for."""
    return import_layer(repository, filename, content, country_code=country_code, level_label=LEVEL_LABEL,
                        name_field=name_field, username=username, table=TABLE)


@lru_cache(maxsize=1)
def bundled_layers() -> dict[str, dict[str, Any]]:
    """The postal code layers shipped with the application, by country (the ``manifest.json`` of their folder)."""
    try:
        return json.loads((BUNDLED_DIR / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=4)
def bundled_rings(country_code: str) -> dict[str, list]:
    import gzip

    item = bundled_layers().get(country_code)
    if not item:
        return {}
    try:
        with gzip.open(BUNDLED_DIR / item['file']) as handle:
            return json.loads(handle.read()).get('boundaries') or {}
    except (OSError, ValueError):
        return {}


def postal_index(repository: Any) -> AreaIndex:
    """The postal code areas of a workspace, to place the tests: its own layers, else the ones shipped. A country
    without a layer has none: its tests stay out of the Postal Code map."""
    sources: dict[str, tuple[str, Any, bool]] = {
        code: (item.get('level_label') or LEVEL_LABEL, (lambda code=code: bundled_rings(code)), True)
        for code, item in bundled_layers().items()}
    for layer in list_postal_layers(repository):
        code = layer['country_code']
        sources[code] = (layer['level_label'], (lambda code=code: layer_boundaries(repository, code, table=TABLE)), False)
    index = AreaIndex(sources)
    index.attributions = {**{code: item.get('attribution') for code, item in bundled_layers().items()},
                          **{layer['country_code']: layer['attribution'] for layer in list_postal_layers(repository)}}
    return index


def postal_version(repository: Any) -> str:
    """The version of the postal code layers of a workspace: a map drawn with others is drawn again."""
    payload = json.dumps({
        'layers': [(layer['country_code'], layer['updated_at']) for layer in list_postal_layers(repository)],
        'shipped': sorted((code, str(item.get('year') or ''), str(item.get('unit_count') or ''))
                          for code, item in bundled_layers().items()),
    }, sort_keys=True)
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()[:16]


def postal_map(index: AreaIndex, used: Iterable[str]) -> dict[str, Any]:
    """The polygons of the postal codes ``used`` by a map, the outlines of their countries (drawn in grey under them) and
    who to credit for them."""
    used = set(used)
    boundaries: dict[str, list] = {}
    background: list = []
    attributions: dict[str, None] = {}
    for code in sorted(index.codes):
        found = {name: rings for name, rings in (index.sources[code][1]() or {}).items() if name in used}
        if found:
            boundaries.update(found)
            background.extend(country_outline(code))
            attributions.setdefault(str(getattr(index, 'attributions', {}).get(code) or ''))
    return {'boundaries': boundaries, 'background': background,
            'attribution': ' · '.join(text for text in attributions if text)}


# -- working the areas out from the points ----------------------------------------------------------
def read_geonames(content: bytes, alpha2: str) -> list[tuple[str, str, float, float]]:
    """The postal code, place, latitude and longitude of each row of a GeoNames postal code file."""
    name = f'{alpha2}.txt'
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if name not in archive.namelist():
                raise ValueError(f'The GeoNames file has no {name}.')
            if archive.getinfo(name).file_size > MAX_FILE_BYTES:
                raise ValueError(f'The GeoNames file {name} is too large.')
            text = archive.read(name).decode('utf-8', 'replace')
    except zipfile.BadZipFile as exc:
        raise ValueError('The GeoNames file is not a ZIP.') from exc
    points = []
    for line in text.splitlines():
        fields = line.split('\t')
        if len(fields) < 11:
            continue
        try:
            latitude, longitude = float(fields[9]), float(fields[10])
        except ValueError:
            continue
        code = fields[1].strip()
        if code and -90 <= latitude <= 90 and -180 <= longitude <= 180 and (latitude or longitude):
            points.append((code, fields[2].strip(), latitude, longitude))
    return points


def coarser_codes(points: list[tuple[str, str, float, float]]) -> tuple[list[tuple[str, str, float, float]], str]:
    """The points with their codes cut to their first characters when a country has more codes than a layer can hold,
    and the level of the codes."""
    length = max((len(point[0]) for point in points), default=0)
    codes = {point[0] for point in points}
    shortened = False
    while len(codes) > MAX_UNITS and length > 1:
        length -= 1
        shortened = True
        codes = {code[:length].rstrip(' -') for code in codes}
    if not shortened:
        return points, 'Postal code'
    return [(code[:length].rstrip(' -'), place, latitude, longitude) for code, place, latitude, longitude in points], \
        f'First {length} characters of the postal code'


def _code_order(code: str) -> list[Any]:
    """Codes in the order people read them: M2 before M10."""
    return [int(part) if part.isdigit() else part for part in re.findall(r'\d+|\D+', code)]


def _area_name(codes: list[str], place: str) -> str:
    """The name of an area: its code and place, or some of its codes when several codes are one area (M1, M4 +6 · Manchester)."""
    shown = codes if len(codes) <= 3 else codes[:2]
    label = ', '.join(shown) + (f' +{len(codes) - len(shown)}' if len(shown) < len(codes) else '')
    return f'{label} · {place}' if place else label


def _areas_of(points: list[tuple[str, str, float, float]]) -> list[tuple[list[str], list[tuple[float, float]], str]]:
    """The codes, points and place of each area. A code with points of its own leaves the points it shares; the codes left
    with a shared point cannot be told apart, so they are one area."""
    owners: dict[tuple[float, float], dict[str, str]] = {}
    held: dict[str, set[tuple[float, float]]] = {}
    for code, place, latitude, longitude in points:
        spot = (latitude, longitude)
        owners.setdefault(spot, {}).setdefault(code, place)
        held.setdefault(code, set()).add(spot)
    parents = {code: code for code in held}

    def root(code: str) -> str:
        while parents[code] != code:
            parents[code] = parents[parents[code]]
            code = parents[code]
        return code

    holder: dict[tuple[float, float], str] = {}
    for code, spots in held.items():
        for spot in {spot for spot in spots if len(owners[spot]) == 1} or spots:
            if spot in holder:
                parents[root(code)] = root(holder[spot])
            else:
                holder[spot] = code
    members: dict[str, list[str]] = {}
    for code in held:
        members.setdefault(root(code), []).append(code)
    spots_of: dict[str, list[tuple[float, float]]] = {}
    for spot, code in holder.items():
        spots_of.setdefault(root(code), []).append(spot)
    areas = []
    for key, codes in members.items():
        spots = spots_of.get(key) or []
        if not spots:
            continue
        latitude = sum(spot[0] for spot in spots) / len(spots)
        longitude = sum(spot[1] for spot in spots) / len(spots)
        # The place of the area: the one closest to its middle.
        nearest = min(spots, key=lambda spot: (spot[0] - latitude) ** 2 + (spot[1] - longitude) ** 2)
        place = next((owners[nearest][code] for code in sorted(codes, key=_code_order) if owners[nearest].get(code)), '')
        areas.append((sorted(codes, key=_code_order), spots, place))
    return areas


def postal_boundaries(points: list[tuple[str, str, float, float]], land: Any) -> dict[str, list]:
    """The simplified rings of each postal code area: the land closest to its points. ``land`` is the land of the country."""
    import numpy as np
    import shapely
    from shapely.geometry import MultiPolygon

    areas = _areas_of(points)
    spots = [spot for _codes, area_spots, _place in areas for spot in area_spots]
    if not spots:
        raise ValueError('The postal codes have no coordinates.')
    if len(spots) == 1:
        return _features_boundaries([(_area_name(areas[0][0], areas[0][2]), land)], _tolerance(1))
    latitudes = np.array([spot[0] for spot in spots])
    # Distances on the ground: a degree of longitude is shorter than one of latitude.
    scale = max(.05, math.cos(math.radians(float(latitudes.mean()))))
    xy = np.column_stack([np.array([spot[1] for spot in spots]) * scale, latitudes])
    left, bottom, right, top = land.bounds
    reach = shapely.box(min(left * scale, xy[:, 0].min()) - 1, min(bottom, latitudes.min()) - 1,
                        max(right * scale, xy[:, 0].max()) + 1, max(top, latitudes.max()) + 1)
    cells = np.array(shapely.get_parts(shapely.voronoi_polygons(shapely.multipoints(xy), extend_to=reach)))
    rows, found = shapely.STRtree(cells).query(shapely.points(xy), predicate='intersects')
    cell_of = np.full(len(spots), -1)
    cell_of[rows] = found
    cells = shapely.transform(cells, lambda coordinates: coordinates / np.array([scale, 1.0]))
    tolerance = _tolerance(len(areas))
    features = []
    start = 0
    for codes, area_spots, place in areas:
        own = cell_of[start:start + len(area_spots)]
        start += len(area_spots)
        merged = shapely.union_all(cells[own[own >= 0]])
        parts = [part for part in shapely.get_parts(shapely.intersection(merged, land))
                 if part.geom_type == 'Polygon' and not part.is_empty]
        if parts:
            features.append((_area_name(codes, place), MultiPolygon(parts)))
    return _features_boundaries(features, tolerance)


def land_of(repository: Any | None, country_code: str) -> Any:
    """The land of a country, from its Map Areas (or its outline): the postal code areas are cut to it."""
    import shapely

    boundaries = (layer_boundaries(repository, country_code) if repository is not None else {}) or _map_area_rings(country_code)
    polygons = [polygon for rings in boundaries.values() for ring in rings for polygon in _valid_polygons(ring)]
    if not polygons:
        raise ValueError(f'The land of {country_name(country_code)} is not known.')
    return shapely.union_all(polygons).buffer(COAST_BUFFER, quad_segs=2).simplify(COAST_BUFFER / 10, preserve_topology=True)


def alpha2_code(country_code: str) -> str:
    """The ISO alpha-2 code of a country, which names its GeoNames file."""
    try:
        import pycountry
    except ImportError as exc:
        raise ValueError('The postal codes cannot be downloaded without the country codes (pycountry).') from exc
    country = pycountry.countries.get(alpha_3=str(country_code).strip().upper())
    if country is None:
        raise ValueError('Choose the country of the postal codes (ISO 3166 alpha-3 code, for example ESP).')
    return str(country.alpha_2)


def download_postal_layer(repository: Any, country_code: str, username: str) -> dict[str, Any]:
    """Download the postal code points of a country from GeoNames and save the areas worked out from them."""
    code = str(country_code or '').strip().upper()
    alpha2 = alpha2_code(code)
    try:
        content = _fetch(GEONAMES_URL.format(code=alpha2), timeout=300)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ValueError(f'GeoNames has no postal codes for {country_name(code)}.') from exc
        raise ValueError(f'The postal codes could not be downloaded ({exc}).') from exc
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f'The postal codes could not be downloaded ({exc}).') from exc
    points, level = coarser_codes(read_geonames(content, alpha2))
    if not points:
        raise ValueError(f'GeoNames has no postal codes with coordinates for {country_name(code)}.')
    boundaries = postal_boundaries(points, land_of(repository, code))
    return save_layer(repository, country_code=code, level=level, level_label=LEVEL_LABEL, origin='GeoNames',
                      source=GEONAMES_URL.format(code=alpha2), license_text=GEONAMES_LICENSE,
                      attribution=GEONAMES_ATTRIBUTION, boundaries=boundaries, username=username, table=TABLE)


# -- the countries of a calculation -----------------------------------------------------------------
def _sample_coordinates(repository: Any, dataset_id: int, kind: str) -> pd.DataFrame | None:
    """A sample of the latitude and longitude of the tests of a CDR, from its columnar copy or its table."""
    from src.modules import cdr_store
    from src.modules.cdr_field_profiles import workspace_field_profile
    from src.modules.map_area_columns import _coordinate_columns

    coordinates = _coordinate_columns(repository.list_dataset_row_columns(dataset_id), kind, workspace_field_profile(repository))
    if coordinates is None:
        return None
    if dataset_id in cdr_store.shadow_ids(repository.db_path):
        frame = cdr_store.read_cdr(repository.db_path, kind, dataset_id, list(coordinates))
    else:
        latitude, longitude = (repository._quote_identifier(column) for column in coordinates)
        table = repository._quote_identifier(repository.dataset_rows_table_name(dataset_id))
        with repository.connection() as connection:
            frame = pd.read_sql_query(f'SELECT {latitude}, {longitude} FROM {table}', connection)
    frame = frame.iloc[::max(1, len(frame) // SAMPLE_ROWS)]
    frame.columns = ['latitude', 'longitude']
    return frame


def countries_of_tests(repository: Any, sources: Iterable[dict[str, Any]]) -> list[str]:
    """The countries with a relevant share of a sample of the tests of the CDRs of a calculation, most tests first."""
    counts: dict[str, int] = {}
    for source in sources:
        metadata = source.get('metadata') or {}
        try:
            frame = _sample_coordinates(repository, int(metadata['dataset_id']), str(metadata['kind']))
        except (KeyError, ValueError, TypeError):
            continue
        if frame is None or frame.empty:
            continue
        found = country_codes(pd.to_numeric(frame['latitude'], errors='coerce'),
                              pd.to_numeric(frame['longitude'], errors='coerce')).dropna()
        for code, count in found.value_counts().items():
            counts[str(code)] = counts.get(str(code), 0) + int(count)
    total = sum(counts.values())
    return [code for code, count in sorted(counts.items(), key=lambda item: -item[1]) if count >= total * MIN_COUNTRY_SHARE]


def ensure_postal_layers(repository: Any, sources: Iterable[dict[str, Any]], username: str = 'system',
                         progress: Callable[[str], None] = lambda _step: None) -> list[dict[str, str]]:
    """Download the postal codes of the countries of a calculation that have none; returns those that could not be, each
    with why (a map still draws the others)."""
    have = {*bundled_layers(), *(layer['country_code'] for layer in list_postal_layers(repository))}
    missing = []
    for code in countries_of_tests(repository, sources):
        if code in have:
            continue
        progress(f'Downloading the postal codes of {country_name(code)}')
        try:
            layer = download_postal_layer(repository, code, username)
        except ValueError as exc:
            missing.append({'code': code, 'name': country_name(code), 'error': str(exc)})
            repository.try_add_log(username, 'postal_areas_download_failed', json.dumps(
                {'country': code, 'error': str(exc)}, ensure_ascii=False))
            continue
        repository.try_add_log(username, 'postal_areas_download', json.dumps(
            {'country': code, 'level': layer['level'], 'areas': layer['unit_count']}, ensure_ascii=False))
    return missing
