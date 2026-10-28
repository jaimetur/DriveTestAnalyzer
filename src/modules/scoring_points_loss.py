"""Where the scoring points are lost: KPI point losses attributed to the tests that cause them.

For every KPI of every scoring group, the tests that make the KPI lose points get a
weight: the tests that miss the KPI condition (a failed call, POLQA below 1.6, a
transfer below 2 Mbit/s...) weigh one each, and for averages, medians and P90 each test
weighs what it misses the KPI's High threshold by. The share of each area (City,
Region or Cluster of the CDR rows, and the map area containing the test: the area of the Map Areas
of its country, such as the ITL3 areas of the UK, see ``map_areas``) is the
sum of its tests' weights over the total, so the points an operator loses in a KPI can be placed
on a map with any scoring's points. The points each City (or route) loses in each map area are
kept too (``City|Area``), to show the losses of a City alone on the map.

Workspaces with a Clusters or Region Mapping dataset also map the Cluster and Region losses on
its polygons.

Besides the areas, the losses are shared among who serves the tests: the RAN Vendor of the cell that served each
test (``Vendor``), the kind of its site (``Site Type``: the network that owns the site and, when another network hosts
it, the host, NNS sites apart) and the site itself (``Site``), and, on the Connecting Roads routes, among stretches of
about 20 km (``Stretch``), so each owner sees where its points go.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from src.modules.cdr_field_profiles import NETCHECK_PROFILE

# The areas and positions of a NetCheck test (every CDR type lists its own, see cdr_field_profiles).
AREA_FIELDS = NETCHECK_PROFILE.area_fields
COORDINATE_SOURCES = NETCHECK_PROFILE.coordinate_sources
# The map areas of every country (the ITL3 areas in the UK) and the losses of each City in each one.
AREA = 'Area'
CITY_AREA = 'City|Area'
CITY_AREA_SEPARATOR = '\x1f'
MAP_FIELDS = (*AREA_FIELDS, AREA)
NOT_SPECIFIED = 'Not specified'
AREA_COLUMN = '__area_{}'
# The area of each test as a category (empty areas as Not specified), to sum the weights of each area at once.
SHARE_COLUMN = '__share_{}'
# Who serves each test: the RAN Vendor, the kind of site and the site of its serving cell, and the stretch of the
# Connecting Roads route it is on. They share the losses like the areas, without polygons.
VENDOR, SITE_TYPE, SITE, STRETCH = 'Vendor', 'Site Type', 'Site', 'Stretch'
SERVING_FIELDS = (VENDOR, SITE_TYPE, SITE, STRETCH)
SHARE_FIELDS = (*MAP_FIELDS, *SERVING_FIELDS)
# The points each Vendor loses in each City or route, for the biggest areas of each Vendor, and each Region (the
# performance owners of the networks, such as Vendor A or VMO2 North) in each City or route.
VENDOR_CITY = 'Vendor|City'
REGION_CITY = 'Region|City'
# Where each test ran (Cities, Towns, Roads or Railways) and how (Drive or Walk), for the places ranked in the Summary.
SETTING, MODE = '__setting', '__mode'
SETTINGS = ('Cities', 'Towns', 'Roads', 'Railways')
SERVING_SOURCES = {'vendor': ('Vendor',), 'network': ('Serving_Network',), 'host': ('Serving_Host_Network',),
                   'site': ('Serving_Site_ID',), 'scenario': ('Serving_eMOCN_Scenario',)}
# A site key is its network and its site ID, as site IDs repeat across networks.
SITE_SEPARATOR = '\x1e'
# A stretch of a route is the route and a cell of this grid (about 22 km by 20 km in the UK).
STRETCH_LATITUDE_STEP, STRETCH_LONGITUDE_STEP = .18, .3
# Every KPI keeps the shares of at most this many sites and stretches; the rest of its losses are Other.
MAX_SITE_SHARES, MAX_STRETCH_SHARES = 80, 160
OTHER = 'Other'
# The fields of a share entry that are not the fields of its scoring series.
ENTRY_FIELDS = frozenset({'environment', 'kpi_code', 'areas', 'weight', 'tests'})
LATITUDE, LONGITUDE, PLACE = '__latitude', '__longitude', '__place'
MAX_AREA_POINTS = 60
# The columns AreaGeometry reads.
_PLACE_COLUMNS = frozenset({LATITUDE, LONGITUDE, PLACE, SETTING, MODE,
                            *(AREA_COLUMN.format(field) for field in (*AREA_FIELDS, AREA, VENDOR, SITE, STRETCH))})
MAX_BACKGROUND_POINTS = 4000
_RATIO = re.compile(r'(100 \* )?(SUM|COUNT)\((.+)\) / (SUM|COUNT)\((\w+)\)')
# The packet loss KPI weighs each test by the packets it lost.
PACKET_LOSS_FORMULA = '100 * SUM(totalpacketlost) / SUM(Packets_Sent)'
LOST_PACKET_FIELDS = ('Packets_Lost', 'Packets_Discarded', 'Packets_Corrupted', 'Packets_Not_Sent')
# The pairs of areas whose losses are kept together: each City (or route) in each map area, each Vendor and each Region
# in each City or route.
PAIR_FIELDS = ((CITY_AREA, 'City', AREA), (VENDOR_CITY, VENDOR, 'City'), (REGION_CITY, 'Region', 'City'))
_AGGREGATE = re.compile(r'(AVG|MEDIAN|PCT90)\((\w+)\)')


def source_columns(kind: str) -> list[str]:
    """CDR columns read for the points-lost map, in addition to the scoring columns."""
    columns = [name for aliases in AREA_FIELDS.values() for name in aliases]
    columns.extend(name for pair in COORDINATE_SOURCES.get(kind, ()) for name in pair)
    columns.extend(name for aliases in SERVING_SOURCES.values() for name in aliases)
    columns.extend(('G_Level_1', 'G_Level_2', 'G_Level_3'))
    return columns


def site_type_label(network: Any, host: Any, scenario: Any = None) -> str:
    """The kind of a serving site: its owner network, ``on <host>`` when another network hosts it, NNS sites apart."""
    network, host = str(network or '').strip(), str(host or '').strip()
    if not network:
        return ''
    label = network if not host or host.casefold() == network.casefold() else f'{network} on {host}'
    return f'NNS · {label}' if str(scenario or '').strip().casefold() == 'nns' else label


def site_key(network: Any, site: Any) -> str:
    return f'{str(network or "").strip()}{SITE_SEPARATOR}{str(site or "").strip()}'


def site_parts(key: str) -> tuple[str, str]:
    network, _separator, site = str(key).partition(SITE_SEPARATOR)
    return (network, site) if _separator else ('', network)


def _distinct(values: pd.Series | pd.DataFrame) -> tuple[pd.Series | pd.DataFrame, Any] | None:
    """The distinct values (or rows) of text columns, in the order they first appear, and the position of each row
    among them, so an operation that looks at each value alone runs once per value; None for other columns."""
    import numpy as np

    columns = [values] if isinstance(values, pd.Series) else [values[name] for name in values.columns]
    if (columns and all(isinstance(column.dtype, pd.CategoricalDtype) for column in columns)
            and np.prod([float(len(column.cat.categories) + 1) for column in columns]) < 2.0 ** 62):
        # Read as Categoricals (see cdr_store.read_kind_frame): the combinations of their codes.
        key = np.zeros(len(values), dtype=np.int64)
        size = 1
        for column in columns:
            key = key * (len(column.cat.categories) + 1) + (column.cat.codes.to_numpy().astype(np.int64) + 1)
            size *= len(column.cat.categories) + 1
        _unique, rows, codes = unique_keys(key, size)
        return values.iloc[rows], codes
    if any(column.dtype == object and pd.api.types.infer_dtype(column, skipna=True) not in ('string', 'empty')
           for column in columns):
        return None
    if isinstance(values, pd.Series):
        codes, _uniques = pd.factorize(values, use_na_sentinel=False)
    else:
        codes = values.groupby(list(values.columns), dropna=False, sort=False, observed=True).ngroup().to_numpy()
    _unique, first = np.unique(codes, return_index=True)
    return values.iloc[first], codes


def unique_keys(keys: Any, size: int | None = None) -> tuple[Any, Any, Any]:
    """The distinct keys (sorted), a row of each and the position of each row's key among them, as ``numpy.unique``
    (``return_index``, ``return_inverse``) but without sorting the rows when the keys (0 to ``size`` - 1) are few: the
    row given for each key is one of its rows (not always the first)."""
    import numpy as np

    keys = np.asarray(keys, dtype=np.int64)
    if size is None:
        size = int(keys.max()) + 1 if len(keys) else 0
    if not len(keys) or size > max(1 << 22, 4 * len(keys)):
        return np.unique(keys, return_index=True, return_inverse=True)
    rows = np.full(size, -1, dtype=np.int64)
    rows[keys] = np.arange(len(keys), dtype=np.int64)
    unique = np.flatnonzero(rows >= 0)
    rank = np.zeros(size, dtype=np.int64)
    rank[unique] = np.arange(len(unique), dtype=np.int64)
    return unique, rows[unique], rank[keys]


def _each_distinct(values: pd.Series, operation: Callable[[pd.Series], Any]) -> Any:
    """``operation`` (which looks at each value alone) of every value, run once per distinct value. Text of a
    Categorical stays a Categorical (of the same values)."""
    distinct = _distinct(values)
    if distinct is None:
        return operation(values)
    result = operation(distinct[0])
    if isinstance(values.dtype, pd.CategoricalDtype) and isinstance(result, pd.Series) \
            and isinstance(result.dtype, pd.StringDtype):
        return _text_categorical(result, distinct[1], values.index)
    taken = (result.take(distinct[1]) if isinstance(result, pd.Categorical)
             else result.array.take(distinct[1]))
    return taken if isinstance(result, pd.Categorical) else pd.Series(taken, index=values.index, name=result.name)


def _text_categorical(result: pd.Series, codes: Any, index: pd.Index) -> pd.Series:
    """The text of each distinct value (``result``, one per code) for every row, as a Categorical."""
    import numpy as np

    texts = result.astype(object)
    present = texts.notna().to_numpy()
    names = sorted({str(text) for text in texts[present]})
    position = {name: number for number, name in enumerate(names)}
    result_codes = np.asarray([position[str(text)] if kept else -1 for text, kept in zip(texts, present)], dtype=np.int64)
    taken = result_codes[np.asarray(codes)] if len(result_codes) else np.full(len(codes), -1, dtype=np.int64)
    return pd.Series(pd.Categorical.from_codes(taken, categories=names), index=index, name=result.name)


def _area_codes(values: pd.Series) -> tuple[Any, Any]:
    """``pandas.factorize(values.fillna(NOT_SPECIFIED), sort=True)``, from the codes of a Categorical."""
    import numpy as np

    if not isinstance(values.dtype, pd.CategoricalDtype):
        return pd.factorize(values.fillna(NOT_SPECIFIED), sort=True)
    labels = [*(str(category) for category in values.cat.categories), NOT_SPECIFIED]
    codes = values.cat.codes.to_numpy().astype(np.int64)
    codes = np.where(codes < 0, len(labels) - 1, codes)
    used = np.flatnonzero(np.bincount(codes, minlength=len(labels)))
    names = sorted({labels[index] for index in used.tolist()})
    position = {name: number for number, name in enumerate(names)}
    remap = np.asarray([position.get(label, -1) for label in labels], dtype=np.int64)
    return remap[codes], np.asarray(names, dtype=object)


def _serving_columns(frame: pd.DataFrame, source: pd.DataFrame, resolve) -> None:
    """The Vendor, Site Type and Site of the cell that served each test, when the CDR has them."""
    resolved = {name: next((found for alias in aliases if (found := resolve(source.columns, alias)) is not None), None)
                for name, aliases in SERVING_SOURCES.items()}
    columns = list(dict.fromkeys(column for column in resolved.values() if column is not None))
    distinct = _distinct(source[columns]) if columns else None
    if distinct is None:
        _serving_labels(frame, source, resolved)
        return
    # The labels of each distinct combination of the serving columns, then of every row.
    labels = pd.DataFrame(index=distinct[0].index)
    _serving_labels(labels, distinct[0], resolved)
    categorical = all(isinstance(dtype, pd.CategoricalDtype) for dtype in source[columns].dtypes)
    for name in labels.columns:
        frame[name] = (_text_categorical(labels[name], distinct[1], frame.index) if categorical
                       else pd.Series(labels[name].array.take(distinct[1]), index=frame.index))


def _serving_labels(frame: pd.DataFrame, source: pd.DataFrame, resolved: dict[str, str | None]) -> None:
    def column(name: str):
        return (source[resolved[name]].astype('string').str.strip().replace('', pd.NA) if resolved[name] is not None
                else None)

    vendor, network, host, site, scenario = (column(name) for name in ('vendor', 'network', 'host', 'site', 'scenario'))
    if vendor is not None:
        # Unknown and empty vendors are not a vendor that loses points.
        frame[AREA_COLUMN.format(VENDOR)] = vendor.mask(vendor.str.casefold().isin({'unknown', 'n/a', 'none', 'nan'}))
    if network is not None:
        # As site_type_label, for every row at once.
        owner = network.fillna('')
        hosted = host.fillna('') if host is not None else pd.Series('', index=source.index, dtype='string')
        types = owner.where(~((hosted != '') & (hosted.str.casefold() != owner.str.casefold())), owner + ' on ' + hosted)
        if scenario is not None:
            types = types.where(scenario.fillna('').str.casefold() != 'nns', 'NNS · ' + types)
        frame[AREA_COLUMN.format(SITE_TYPE)] = types.where(owner != '').replace('', pd.NA)
        if site is not None:
            keys = network.fillna('') + SITE_SEPARATOR + site
            frame[AREA_COLUMN.format(SITE)] = keys.where(site.notna() & network.notna())


def _stretch_column(frame: pd.DataFrame) -> None:
    """The stretch of each Connecting Roads test: its route and the grid cell of its position."""
    city = AREA_COLUMN.format('City')
    if city not in frame or LATITUDE not in frame or PLACE not in frame:
        return
    latitude, longitude = frame[LATITUDE], frame[LONGITUDE]
    located = latitude.between(-90, 90) & longitude.between(-180, 180) & ~((latitude == 0) & (longitude == 0))
    on_route = located & ~frame[PLACE].fillna(True).astype(bool) & frame[city].notna()
    if not on_route.any():
        return
    import numpy as np

    rows = pd.Series(np.floor(latitude[on_route].to_numpy(dtype=float) / STRETCH_LATITUDE_STEP).astype(int),
                     index=latitude[on_route].index).astype('string')
    columns = pd.Series(np.floor(longitude[on_route].to_numpy(dtype=float) / STRETCH_LONGITUDE_STEP).astype(int),
                        index=longitude[on_route].index).astype('string')
    stretches = pd.Series(pd.NA, index=frame.index, dtype='string')
    stretches[on_route] = frame.loc[on_route, city].astype('string') + SITE_SEPARATOR + rows + ',' + columns
    frame[AREA_COLUMN.format(STRETCH)] = stretches


def setting_of(level_3: Any, level_2: Any) -> str:
    """Cities, Towns, Roads or Railways from the levels of a test (see cdr_environments): big cities are Cities, medium
    and small ones Towns, train routes Railways and the other connecting routes Roads."""
    from src.modules.cdr_environments import environment_class

    environment = environment_class(level_3) or environment_class(level_2)
    if environment != 'Roads and railways':
        return environment
    text = f'{level_3 or ""} {level_2 or ""}'.casefold()
    return 'Railways' if 'train' in text or 'rail' in text else 'Roads'


def _setting_columns(frame: pd.DataFrame, source: pd.DataFrame, resolve) -> None:
    """Where each test ran (``SETTING``) and how (``MODE``: Drive or Walk), when the CDR names them."""
    from src.modules.network_insights_findings import mode_of_test

    def column(name: str) -> pd.Series:
        resolved = resolve(source.columns, name)
        return (source[resolved] if resolved is not None else pd.Series('', index=source.index, dtype=object))

    # Each distinct level (or pair of levels) once.
    levels = pd.DataFrame({'level_3': column('G_Level_3'), 'level_2': column('G_Level_2')}, index=source.index)
    distinct = _distinct(levels)
    if distinct is None:
        pairs = pd.Series(list(zip(*(levels[name].astype(object).where(levels[name].notna(), '') for name in levels))),
                          index=source.index)
        settings = {pair: setting_of(*pair) for pair in pd.unique(pairs)}
        frame[SETTING] = pairs.map(settings).replace('', pd.NA).astype('string')
    else:
        rows = distinct[0].astype(object).where(distinct[0].notna(), '')
        labels = pd.Series([setting_of(level_3, level_2) for level_3, level_2 in zip(rows['level_3'], rows['level_2'])],
                           dtype=object).replace('', pd.NA).astype('string')
        frame[SETTING] = (_text_categorical(labels, distinct[1], frame.index)
                          if all(isinstance(dtype, pd.CategoricalDtype) for dtype in levels.dtypes)
                          else pd.Series(labels.array.take(distinct[1]), index=frame.index))
    frame[MODE] = _each_distinct(column('G_Level_1'), lambda values: values.astype(object).where(values.notna(), '').map(
        mode_of_test).replace('', pd.NA).astype('string'))


def attach_location(frame: pd.DataFrame, source: pd.DataFrame, kind: str, resolve, areas=None) -> None:
    """Copy the area and coordinate columns of the source rows into the scoring frame.

    ``areas`` (a ``map_areas.AreaIndex``) names the map area of each test; without it, the ones shipped.
    """
    for field, aliases in AREA_FIELDS.items():
        column = next((resolved for alias in aliases if (resolved := resolve(source.columns, alias)) is not None), None)
        if column is not None:
            frame[AREA_COLUMN.format(field)] = _each_distinct(source[column], lambda values: values.astype('string').str.strip())
    for latitude_name, longitude_name in COORDINATE_SOURCES.get(kind, ()):
        latitude, longitude = resolve(source.columns, latitude_name), resolve(source.columns, longitude_name)
        if latitude is not None and longitude is not None:
            frame[LATITUDE] = pd.to_numeric(source[latitude], errors='coerce')
            frame[LONGITUDE] = pd.to_numeric(source[longitude], errors='coerce')
            # The areas kept in the rows of the CDR when placed with the current Map Areas (empty outside every
            # area); the tests without one are placed here.
            stored = resolve(source.columns, 'Map_Area')
            if (stored is not None and isinstance(source[stored].dtype, pd.CategoricalDtype)
                    and not source[stored].isna().any()):
                # Every test placed (read as a Categorical): each area name once.
                names = _each_distinct(source[stored], lambda values: values.astype('string'))
            else:
                names = (source[stored].astype('string') if stored is not None
                         else pd.Series(pd.NA, index=source.index, dtype='string'))
            unplaced = names.isna()
            if areas is None and (unplaced.any() or stored is not None):
                from src.modules.map_areas import area_index
                areas = area_index(None)
            if stored is not None and not unplaced.all():
                # The map draws the areas of the countries of the tests placed before.
                country = resolve(source.columns, 'Map_Area_Country')
                if country is not None:
                    areas.note_countries(source.loc[~unplaced, country].dropna().astype(str).unique())
            if unplaced.any():
                names = names.copy()
                names[unplaced] = areas.names_of(frame.loc[unplaced, LATITUDE], frame.loc[unplaced, LONGITUDE])
            frame[AREA_COLUMN.format(AREA)] = (
                names.cat.remove_categories([''] if '' in names.cat.categories else [])
                if isinstance(names.dtype, pd.CategoricalDtype) else names.replace('', pd.NA))
            break
    level_2 = resolve(source.columns, 'G_Level_2')
    # Drive City tests are places; other tests (Connecting Roads) follow a route.
    frame[PLACE] = (_each_distinct(source[level_2], lambda values: values.astype('string').str.casefold() == 'city')
                    if level_2 is not None else True)
    _setting_columns(frame, source, resolve)
    _serving_columns(frame, source, resolve)
    _stretch_column(frame)
    for field in SHARE_FIELDS:
        column = AREA_COLUMN.format(field)
        if column in frame:
            frame[SHARE_COLUMN.format(field)] = _each_distinct(frame[column], lambda values: pd.Categorical(
                values.astype(object).fillna(NOT_SPECIFIED).replace('', NOT_SPECIFIED).astype(str)))


def _rings(geometry, precision: int) -> list[list[list[float]]]:
    polygons = geometry.geoms if geometry.geom_type == 'MultiPolygon' else [geometry]
    return [[[round(x, precision), round(y, precision)] for x, y in polygon.exterior.coords]
            for polygon in polygons if not polygon.is_empty]


def mapping_boundaries(
    path: Path, field: str, tolerance: float = .002, operator: str | None = None,
) -> dict[str, list[list[list[float]]]]:
    """Simplified outer rings of a workspace Regions, Clusters or Vendors dataset, by its attribute.

    Vendor polygons are named ``<Operator> · <Vendor>`` with ``operator`` or, without it, their Operator attribute.
    """
    from src.modules.geospatial import _cluster_field, _operator_field, _read_region_mapping, _region_field, _vendor_field

    label = {'Cluster': 'Clusters', 'Vendor': 'Vendor polygons'}.get(field, 'Regions')
    polygons = _read_region_mapping(path, label)
    if polygons.empty or polygons.crs is None:
        return {}
    name_field = {'Cluster': _cluster_field, 'Vendor': _vendor_field}.get(field, _region_field)(polygons.columns)
    polygons = polygons.to_crs('EPSG:4326')
    names = polygons[name_field].astype(str).str.strip()
    if field == 'Vendor':
        operator_field = _operator_field(polygons.columns)
        operators = pd.Series(operator or '', index=polygons.index) if operator or not operator_field else polygons[operator_field].astype(str).str.strip()
        names = [f'{owner} · {vendor}' if owner else vendor for owner, vendor in zip(operators, names)]
    boundaries: dict[str, list] = {}
    for name, geometry in zip(names, polygons.geometry):
        if geometry is None or geometry.is_empty or geometry.geom_type not in {'Polygon', 'MultiPolygon'}:
            continue
        boundaries.setdefault(name, []).extend(_rings(geometry.simplify(tolerance, preserve_topology=True), 4))
    return boundaries


def map_boundaries(result: dict[str, Any] | None, field: str) -> dict[str, list[list[list[float]]]]:
    """Polygons of a points-lost field: the map areas or the workspace mapping saved with the job.

    The map areas shipped with the application (or the whole country) are read from the application and
    the others are saved with the job.
    """
    document = result.get('points_loss') if isinstance(result, dict) else None
    if field == AREA:
        areas = (document or {}).get('map_areas') if isinstance(document, dict) else None
        if not isinstance(areas, dict):
            return {}
        from src.modules.map_areas import bundled_rings
        shipped = {}
        for item in areas.get('countries') or []:
            if item.get('bundled'):
                shipped.update(bundled_rings(item['code']))
        return {**shipped, **(areas.get('boundaries') or {})}
    saved = (document or {}).get('boundaries') if isinstance(document, dict) else None
    return dict((saved or {}).get(field) or {})


def map_background(result: dict[str, Any] | None, field: str) -> list[list[list[float]]]:
    """The outlines of the countries whose areas are saved with the job, drawn in grey under them."""
    document = result.get('points_loss') if isinstance(result, dict) else None
    areas = (document or {}).get('map_areas') if isinstance(document, dict) and field == AREA else None
    return list(areas.get('background') or []) if isinstance(areas, dict) else []


def _numeric(frame: pd.DataFrame, field: str) -> pd.Series:
    return pd.to_numeric(frame[field], errors='coerce')


def test_weights(frame: pd.DataFrame, metric: dict[str, Any], thresholds: dict[str, Any],
                 condition, apply_filters) -> pd.Series:
    """Weight of each test in the points a KPI loses; tests outside the KPI weigh nothing."""
    selected = apply_filters(frame, metric['calculation']['filters'])
    formula = metric['calculation']['formula']
    higher_is_better = metric['direction'] == 'higher_is_better'
    weights = pd.Series(0.0, index=frame.index)
    if selected.empty:
        return weights
    if formula == PACKET_LOSS_FORMULA:
        lost = sum((_numeric(selected, field).fillna(0) if field in selected else 0) for field in LOST_PACKET_FIELDS)
        weights.loc[selected.index] = pd.Series(lost, index=selected.index).clip(lower=0)
        return weights
    ratio = _RATIO.fullmatch(formula)
    if ratio:
        _multiplier, _operation, expression, _denominator_operation, denominator = ratio.groups()
        counted = selected[selected[denominator].notna()] if denominator in selected else selected
        expression = expression.strip()
        try:
            matches = condition(counted, expression).astype(bool)
        except (KeyError, ValueError):
            weights.loc[counted.index] = 1.0
            return weights
        # Higher-is-better ratios lose points on the tests that miss the condition, and
        # lower-is-better ratios (POLQA < 1.6, setup time > 10 s) on the tests that meet it.
        bad = ~matches if higher_is_better else matches
        weights.loc[counted.index] = bad.astype(float)
        return weights
    aggregate = _AGGREGATE.fullmatch(formula)
    if aggregate and aggregate.group(2) in selected:
        values = _numeric(selected, aggregate.group(2))
        target = thresholds.get('high')
        if isinstance(target, (int, float)):
            shortfall = (target - values) if higher_is_better else (values - target)
            weights.loc[selected.index] = shortfall.clip(lower=0).fillna(0)
            return weights
    weights.loc[selected.index] = 1.0
    return weights


def counts_tests(metric: dict[str, Any]) -> bool:
    """Whether a KPI's test weights count tests (a ratio of tests that miss it), so its total weight is a number of
    tests: failed calls, POLQA below 1.6, transfers below a threshold..."""
    formula = metric['calculation']['formula']
    return formula != PACKET_LOSS_FORMULA and _RATIO.fullmatch(formula) is not None


def _category_shares(frame: pd.DataFrame, weights: pd.Series, total: float) -> dict[str, dict[str, float]]:
    """``area_shares`` from the area categories of the rows (see ``attach_location``)."""
    import numpy as np

    values = weights.to_numpy(dtype=float)
    shares: dict[str, dict[str, float]] = {}
    codes = {}
    for field in SHARE_FIELDS:
        column = SHARE_COLUMN.format(field)
        if column not in frame:
            continue
        category = frame[column].cat
        codes[field] = (category.codes.to_numpy(), list(category.categories))
        by_area = np.bincount(codes[field][0], weights=values, minlength=len(codes[field][1]))
        field_shares = {str(codes[field][1][index]): round(float(by_area[index]) / total, 6)
                        for index in np.flatnonzero(by_area > 0)}
        if field == STRETCH:
            # Tests off the routes have no stretch.
            field_shares.pop(NOT_SPECIFIED, None)
        if field in SERVING_FIELDS:
            field_shares = _capped_shares(field_shares, field)
        if field_shares:
            shares[field] = field_shares
    lost = values > 0
    for pair_field, first, second in PAIR_FIELDS:
        if first not in codes or second not in codes or not lost.any():
            continue
        # Where each City (or route) loses, in each map area; where each Vendor loses, in each City or route.
        (first_codes, firsts), (second_codes, seconds) = codes[first], codes[second]
        pairs = first_codes[lost].astype(np.int64) * len(seconds) + second_codes[lost]
        by_pair = pd.Series(values[lost]).groupby(pairs).sum()
        pair_shares = {
            f'{firsts[pair // len(seconds)]}{CITY_AREA_SEPARATOR}{seconds[pair % len(seconds)]}': round(float(value) / total, 6)
            for pair, value in by_pair.items() if value > 0}
        if pair_field in (VENDOR_CITY, REGION_CITY):
            pair_shares = {pair: share for pair, share in pair_shares.items()
                           if not pair.startswith(NOT_SPECIFIED + CITY_AREA_SEPARATOR)}
        if pair_shares:
            shares[pair_field] = pair_shares
    return shares


def serving_counts(frame: pd.DataFrame, *, areas: bool = True) -> dict[str, dict[str, int]]:
    """The tests of a scoring group per Vendor and per Site Type of their serving cell, to compare each one's share of
    the tests with its share of the points lost, and, with ``areas`` (the calls and tests, not the samples of Speech),
    per City, Region and Cluster, for the points each place loses per 1,000 of its tests."""
    counts: dict[str, dict[str, int]] = {}
    for field in (VENDOR, SITE_TYPE, *(AREA_FIELDS if areas else ())):
        column = SHARE_COLUMN.format(field)
        if column in frame:
            values = frame[column].value_counts()
            counts[field] = {str(name): int(count) for name, count in values.items() if count}
    return counts


def _capped_shares(shares: dict[str, float], field: str) -> dict[str, float]:
    """The sites and stretches that lose most of a KPI; the rest of its losses is Other (vendors and kinds of site
    are few, so they are all kept)."""
    limit = {SITE: MAX_SITE_SHARES, STRETCH: MAX_STRETCH_SHARES}.get(field)
    if limit is None or len(shares) <= limit:
        return shares
    ordered = sorted(shares.items(), key=lambda item: -item[1])
    kept = dict(ordered[:limit])
    rest = sum(share for _name, share in ordered[limit:])
    if rest > 0:
        kept[OTHER] = round(kept.get(OTHER, 0.0) + rest, 6)
    return kept


def area_shares(frame: pd.DataFrame, weights: pd.Series) -> dict[str, dict[str, float]]:
    """Share of the KPI's weight in each area, for every area field of the rows."""
    total = float(weights.sum())
    if total <= 0:
        return {}
    if any(SHARE_COLUMN.format(field) in frame for field in MAP_FIELDS):
        return _category_shares(frame, weights, total)
    shares: dict[str, dict[str, float]] = {}
    for field in SHARE_FIELDS:
        column = AREA_COLUMN.format(field)
        if column not in frame:
            continue
        by_area = weights.groupby(frame[column].astype(object).fillna(NOT_SPECIFIED).replace('', NOT_SPECIFIED)).sum()
        field_shares = {str(area): round(float(value) / total, 6) for area, value in by_area.items() if value > 0
                        and not (field == STRETCH and area == NOT_SPECIFIED)}
        if field_shares:
            shares[field] = _capped_shares(field_shares, field) if field in SERVING_FIELDS else field_shares
    city, area = AREA_COLUMN.format('City'), AREA_COLUMN.format(AREA)
    if city in frame and area in frame:
        # Where each City (or route) loses: the share of each City in each map area.
        lost = weights[weights > 0]
        if not lost.empty:
            pairs = (frame.loc[lost.index, city].astype(object).fillna(NOT_SPECIFIED).astype(str) + CITY_AREA_SEPARATOR
                     + frame.loc[lost.index, area].astype(object).fillna(NOT_SPECIFIED).astype(str))
            by_pair = lost.groupby(pairs).sum()
            shares[CITY_AREA] = {str(pair): round(float(value) / total, 6) for pair, value in by_pair.items() if value > 0}
    return shares


def _most_common(pairs: pd.DataFrame, column: str, label_column: str) -> dict[str, str]:
    """The most common label of each value of ``column``, as ``value_counts().index[0]`` of its labels: the most
    frequent one, ties ordered as pandas orders them."""
    import numpy as np
    from pandas.core.sorting import nargsort

    names, name_values = pd.factorize(pairs[column])
    labels, label_values = pd.factorize(pairs[label_column])
    if not len(names):
        return {}
    unique, first, counts = np.unique(names.astype(np.int64) * len(label_values) + labels, return_index=True,
                                      return_counts=True)
    owners = unique // len(label_values)
    # The labels of each value in the order they first appear, as value_counts lists them before sorting.
    order = np.lexsort((first, owners))
    owners, labels, counts = owners[order], (unique % len(label_values))[order], counts[order]
    bounds = np.searchsorted(owners, np.arange(len(name_values) + 1))
    common = {}
    for position, (low, high) in enumerate(zip(bounds[:-1].tolist(), bounds[1:].tolist())):
        if high - low == 1:
            best = low
        else:
            top = int(np.argmax(counts[low:high]))
            # A tie for the most frequent is broken as pandas breaks it.
            best = low + (top if int((counts[low:high] == counts[low + top]).sum()) == 1
                          else int(nargsort(counts[low:high], kind='quicksort', ascending=False)[0]))
        common[str(name_values[position])] = str(label_values[labels[best]])
    return common


def _value_counts_by(keys: Any, values: pd.Series, count: int) -> list[list[tuple[str, int]]]:
    """For each key (0 to ``count`` - 1), ``values.dropna().value_counts()`` of its rows as (value, count) pairs in the
    order pandas lists them: the most frequent first, ties ordered as pandas orders them."""
    import numpy as np
    from pandas.core.sorting import nargsort

    present = values.notna().to_numpy()
    labels, label_values = pd.factorize(values[present])
    by_key: list[list[tuple[str, int]]] = [[] for _key in range(count)]
    if not len(labels):
        return by_key
    unique, first, counts = np.unique(np.asarray(keys)[present].astype(np.int64) * len(label_values) + labels,
                                      return_index=True, return_counts=True)
    owners = unique // len(label_values)
    # The values of each key in the order they first appear, as value_counts lists them before sorting.
    order = np.lexsort((first, owners))
    owners, labels, counts = owners[order], (unique % len(label_values))[order], counts[order]
    bounds = np.searchsorted(owners, np.arange(count + 1))
    names = [str(value) for value in label_values]
    for key, (low, high) in enumerate(zip(bounds[:-1].tolist(), bounds[1:].tolist())):
        if high - low == 1:
            by_key[key] = [(names[labels[low]], int(counts[low]))]
        elif high > low:
            chunk = counts[low:high]
            # Counts that all differ have one order; ties are ordered as pandas orders them.
            order = (np.argsort(-chunk, kind='stable') if len(np.unique(chunk)) == len(chunk)
                     else nargsort(chunk, kind='quicksort', ascending=False))
            by_key[key] = [(names[labels[low + index]], int(counts[low + index])) for index in order]
    return by_key


class AreaGeometry:
    """Centroids, route points and a background sample of the test locations."""

    def __init__(self) -> None:
        self.areas: dict[str, dict[str, dict[str, Any]]] = {field: {} for field in AREA_FIELDS}
        # Where the sites and the stretches of the routes are, and who they are.
        self.places: dict[str, dict[str, dict[str, Any]]] = {SITE: {}, STRETCH: {}}
        self.background: list[list[float]] = []
        self._seen = 0
        # The map areas with tests.
        self.used_areas: set[str] = set()

    def add(self, frame: pd.DataFrame) -> None:
        import numpy as np

        if LATITUDE not in frame or LONGITUDE not in frame:
            return
        # Only the columns of the places are copied.
        frame = frame[[column for column in frame.columns if column in _PLACE_COLUMNS]]
        located = frame[frame[LATITUDE].between(-90, 90) & frame[LONGITUDE].between(-180, 180)
                        & ~((frame[LATITUDE] == 0) & (frame[LONGITUDE] == 0))]
        if located.empty:
            return
        map_area = AREA_COLUMN.format(AREA)
        if map_area in located:
            self.used_areas.update(str(name) for name in located[map_area].dropna().unique())
        step = max(1, len(located) // 1500)
        for latitude, longitude in located[[LATITUDE, LONGITUDE]].iloc[::step].itertuples(index=False):
            self._seen += 1
            if len(self.background) < MAX_BACKGROUND_POINTS:
                self.background.append([round(float(latitude), 4), round(float(longitude), 4)])
        for field in AREA_FIELDS:
            column = AREA_COLUMN.format(field)
            if column not in located:
                continue
            # Each area in the order of its name, with its tests together in the order of the rows.
            codes, names = _area_codes(located[column])
            order = np.argsort(codes, kind='stable')
            sizes = np.bincount(codes, minlength=len(names))
            ends = np.cumsum(sizes)
            starts = ends - sizes
            latitudes = located[LATITUDE].to_numpy(dtype=float)[order]
            longitudes = located[LONGITUDE].to_numpy(dtype=float)[order]
            places = (np.bincount(codes[located[PLACE].fillna(True).astype(bool).to_numpy()], minlength=len(names))
                      if PLACE in located else sizes)
            counted = {}
            if field == 'City':
                # The map areas of the tests of each City or route (to show it alone on the map), the vendors of the
                # cells that served them, and their Regions (performance owners), settings and modes.
                for key, source_column in (('area_tests', AREA_COLUMN.format(AREA)), ('vendor_tests', AREA_COLUMN.format(VENDOR)),
                                           ('region_tests', AREA_COLUMN.format('Region')), ('setting_tests', SETTING),
                                           ('mode_tests', MODE)):
                    if source_column in located:
                        counted[key] = _value_counts_by(codes, located[source_column], len(names))
            for position, area in enumerate(names):
                entry = self.areas[field].setdefault(str(area), {
                    'latitude_sum': 0.0, 'longitude_sum': 0.0, 'tests': 0, 'places': 0, 'points': [], 'area_tests': {}})
                for key, by_area in counted.items():
                    counts = entry.setdefault(key, {})
                    for name, count in by_area[position]:
                        if key in ('area_tests', 'vendor_tests') or (name and name != NOT_SPECIFIED):
                            counts[name] = counts.get(name, 0) + count
                low, high = int(starts[position]), int(ends[position])
                entry['latitude_sum'] += float(latitudes[low:high].sum())
                entry['longitude_sum'] += float(longitudes[low:high].sum())
                entry['tests'] += high - low
                entry['places'] += int(places[position])
                room = MAX_AREA_POINTS - len(entry['points'])
                if room > 0:
                    step = max(1, (high - low) // room)
                    entry['points'].extend([round(float(lat), 4), round(float(lon), 4)] for lat, lon
                                           in zip(latitudes[low:high:step][:room].tolist(),
                                                  longitudes[low:high:step][:room].tolist()))

        self._add_places(located)

    def _add_places(self, located: pd.DataFrame) -> None:
        """The position of every serving site and route stretch, with its network, Vendor and City."""
        for field in (SITE, STRETCH):
            column = AREA_COLUMN.format(field)
            if column not in located:
                continue
            rows = located[located[column].notna()]
            if rows.empty:
                continue
            columns = {LATITUDE: 'sum', LONGITUDE: 'sum'}
            categorical = isinstance(rows[column].dtype, pd.CategoricalDtype)
            # A Categorical groups by its codes (the same groups, in the same order, as its text).
            grouped = rows.groupby(rows[column].cat.codes if categorical else rows[column].astype(str), sort=False)
            sums = grouped.agg(columns)
            counts = grouped.size()
            labels = {}
            for label_field in ((VENDOR, 'City', 'Region') if field == SITE else (VENDOR, 'Region')):
                label_column = AREA_COLUMN.format(label_field)
                if label_column in rows:
                    pairs = rows[[column, label_column]].dropna()
                    labels[label_field] = _most_common(pairs if categorical and isinstance(
                        pairs[label_column].dtype, pd.CategoricalDtype) else pairs.astype(str), column, label_column)
            entries = self.places[field]
            names = ([str(rows[column].cat.categories[code]) for code in sums.index.tolist()] if categorical
                     else sums.index.tolist())
            for name, latitude, longitude, tests in zip(names, sums[LATITUDE].tolist(),
                                                        sums[LONGITUDE].tolist(), counts.tolist()):
                entry = entries.setdefault(name, {'latitude_sum': 0.0, 'longitude_sum': 0.0, 'tests': 0})
                entry['latitude_sum'] += float(latitude)
                entry['longitude_sum'] += float(longitude)
                entry['tests'] += int(tests)
                for label_field, values in labels.items():
                    if name in values and label_field.casefold() not in entry:
                        entry[label_field.casefold()] = values[name]

    def map_areas(self, index) -> dict[str, Any]:
        """The map areas of the tests (see ``map_areas.AreaIndex.document``)."""
        return index.document(self.used_areas)

    def document(self) -> dict[str, Any]:
        areas = {}
        for field, entries in self.areas.items():
            if not entries:
                continue
            areas[field] = {
                area: {
                    'latitude': round(entry['latitude_sum'] / entry['tests'], 5),
                    'longitude': round(entry['longitude_sum'] / entry['tests'], 5),
                    'tests': entry['tests'],
                    # A City value of Connecting Roads tests is a route between cities.
                    'kind': 'place' if entry['places'] * 2 >= entry['tests'] else 'route',
                    'points': entry['points'] if entry['places'] * 2 < entry['tests'] else [],
                    **({'area_tests': entry['area_tests']} if entry['area_tests'] else {}),
                    **({'vendor_tests': entry['vendor_tests']} if entry.get('vendor_tests') else {}),
                    **({'region_tests': entry['region_tests']} if entry.get('region_tests') else {}),
                    # The setting of most of its tests and the modes it was tested in (Drive, Walk).
                    **({'setting': max(entry['setting_tests'], key=entry['setting_tests'].get)} if entry.get('setting_tests') else {}),
                    **({'modes': sorted(entry['mode_tests'], key=lambda mode: ({'Drive': 0, 'Walk': 1}.get(mode, 2), mode))}
                       if entry.get('mode_tests') else {}),
                }
                for area, entry in entries.items()
            }
        for field, entries in self.places.items():
            if not entries:
                continue
            located = {}
            for name, entry in entries.items():
                item = {'latitude': round(entry['latitude_sum'] / entry['tests'], 5),
                        'longitude': round(entry['longitude_sum'] / entry['tests'], 5), 'tests': entry['tests']}
                if field == SITE:
                    item['network'], item['site'] = site_parts(name)
                    item.update({key: entry[key] for key in ('vendor', 'city', 'region') if entry.get(key)})
                else:
                    item['route_name'] = name.partition(SITE_SEPARATOR)[0]
                    item.update({key: entry[key] for key in ('vendor', 'region') if entry.get(key)})
                located[name] = item
            areas[field] = located
        return {'areas': areas, 'background': self.background}


def row_area_links(areas: list[dict[str, Any]]) -> dict[str, list[str]]:
    """The map areas of each City or route, the one with most of its tests first.

    A City or route belongs to the areas holding at least 2% of its tests (``area_tests``).
    """
    links: dict[str, list[str]] = {}
    for area in areas:
        counts = area.get('area_tests') or {}
        total = sum(counts.values())
        if area.get('name') == NOT_SPECIFIED or not total:
            continue
        ordered = sorted(counts, key=lambda name: -counts[name])
        links[area['name']] = [name for name in ordered if counts[name] / total >= .02] or ordered[:1]
    return links


def row_area_values(areas: list[dict[str, Any]]) -> dict[str, float]:
    """Each map area with the points of the City or route that loses most in it."""
    points = {area['name']: float(area['points']) for area in areas}
    values: dict[str, float] = {}
    for row, names in row_area_links(areas).items():
        for name in names:
            values[name] = max(values.get(name, 0.0), points[row])
    return values


def points_loss_maps(result: dict[str, Any], keys: list[str],
                     weight: Callable[[dict[str, Any], str, Any], float] | None = None) -> list[dict[str, Any]]:
    """Points lost per area for each scoring series, all environments together and in each one.

    Each KPI loses its maximum points minus the points scored; the loss is spread over
    the areas by their shares. ``keys`` are the series fields other than the environment.
    The maps of all environments (``environment`` None) give each area the points it loses
    in each environment, most first (``environments``), in the points of all environments:
    ``weight`` (the series fields, the environment and the KPI code) gives what one point of
    an environment is worth there, more than one when environments without results in any
    series are scaled out of the Combined scores.
    """
    document = result.get('points_loss') if isinstance(result, dict) else None
    if not isinstance(document, dict) or not document.get('shares'):
        return []
    rows = {}
    for row in result.get('scoring') or []:
        rows[(tuple(row.get(key) for key in keys), row.get('environment'), row.get('kpi_code'))] = row
    series: dict[tuple, dict[str, dict[str, float]]] = {}
    by_environment: dict[tuple, dict[str, dict[str, dict[str, float]]]] = {}
    # The failed tests (calls, sessions…) of each site: the tests that miss the Reliable KPIs counted in tests.
    failures: dict[tuple, dict[str, float]] = {}
    for entry in document['shares']:
        identity = tuple(entry.get(key) for key in keys)
        row = rows.get((identity, entry.get('environment'), entry.get('kpi_code')))
        if row is None:
            continue
        maximum = float(row.get('max_points') or 0)
        points = row.get('weighted_points')
        if maximum <= 0 or points is None:
            continue
        lost = max(0.0, maximum - float(points))
        if lost <= 0:
            continue
        environment = str(entry.get('environment') or '')
        counted = entry.get('tests') and str(row.get('kpi_type') or '').casefold() == 'reliable'
        combined = weight(dict(zip(keys, identity)), environment, entry.get('kpi_code')) if weight else 1.0
        for key in ((identity, None), (identity, environment)):
            target = series.setdefault(key, {})
            points = lost * combined if key[1] is None else lost
            for field, shares in (entry.get('areas') or {}).items():
                areas = target.setdefault(field, {})
                for area, share in shares.items():
                    areas[area] = areas.get(area, 0.0) + points * float(share)
                    if key[1] is None:
                        split = by_environment.setdefault(identity, {}).setdefault(field, {}).setdefault(area, {})
                        split[environment] = split.get(environment, 0.0) + points * float(share)
                    if counted and field == SITE:
                        failed = failures.setdefault(key, {})
                        failed[area] = failed.get(area, 0.0) + float(entry.get('weight') or 0) * float(share)
    maps = []
    for (identity, environment), fields in series.items():
        context = dict(zip(keys, identity))
        # The points each City loses in each map area, kept on the City map, and each Vendor in each City or route.
        pair_losses: dict[str, dict[str, dict[str, float]]] = {CITY_AREA: {}, VENDOR_CITY: {}, REGION_CITY: {}}
        for pair_field, losses in pair_losses.items():
            for pair, points in (fields.get(pair_field) or {}).items():
                first, _separator, second = pair.partition(CITY_AREA_SEPARATOR)
                losses.setdefault(first, {})[second] = points
        city_areas = pair_losses[CITY_AREA]
        for field, areas in fields.items():
            if not areas or field in pair_losses:
                continue
            item = {'context': context, 'field': field, 'areas': areas, 'total': sum(areas.values()),
                    'environment': environment}
            if field == 'City' and city_areas:
                item['area_losses'] = city_areas
            if field == VENDOR and pair_losses[VENDOR_CITY]:
                item['city_losses'] = pair_losses[VENDOR_CITY]
            if field == 'Region' and pair_losses[REGION_CITY]:
                item['city_losses'] = pair_losses[REGION_CITY]
            if field == SITE and failures.get((identity, environment)):
                item['failures'] = {name: round(value, 2) for name, value in failures[(identity, environment)].items()}
            if environment is None:
                split = by_environment.get(identity, {}).get(field, {})
                item['environments'] = {area: [name for name, _points in sorted(
                    split.get(area, {}).items(), key=lambda pair: -pair[1]) if name] for area in areas}
            maps.append(item)
    return maps

