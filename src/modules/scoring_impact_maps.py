"""The maps of the Methodology Impact (see scoring_impact): the Points Lost Map of the same tests with each methodology, compared
area by area. The points of the National scoring each area loses add up to what the operator loses, so what an area gains or loses
between both methodologies adds up to what the methodology moves for the operator, on any geography.
"""
from __future__ import annotations

from typing import Any

from src.modules.scoring_impact_analysis import COMBINED, MATERIAL, _rounded, linear_fit, pearson, quantile
from src.modules.scoring_insights import MIN_POSTAL_RATE_TESTS, MIN_RATE_TESTS, RATE_TESTS, _combined_weight_of, _combined_weights, _scopes, _series_tests
from src.modules.scoring_points_loss import AREA, POSTAL, map_background, map_boundaries, points_loss_maps

MAP_FIELDS = ('City', 'Region', 'Cluster', AREA, POSTAL)
FIELD_LABELS = {'City': 'City', 'Region': 'Region', 'Cluster': 'Cluster', AREA: 'Map Area', POSTAL: 'Postal Code'}
SERVING_FIELDS = {'Vendor': 'Vendor', 'Site Type': 'Kind of site'}
MEASURES = {'national': 'National points', 'rate': 'National points per 1,000 tests', 'own': 'Scoring of the area'}
CONCENTRATION_AREAS = 10
TOP_AREAS = 10
_MAP_DIGITS = 3


def _lost_of(document: dict[str, Any], rows: list[dict[str, Any]], tables: dict[str, dict]) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    """The National points each operator loses in each area: {field: {environment: {operator: {area: points}}}}."""
    weights = _combined_weight_of(_combined_weights(_scopes(list(tables.values()))))
    weight = (lambda _context, environment, kpi_code: weights(None, kpi_code, environment)) if weights else None
    lost: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for item in points_loss_maps({'points_loss': document, 'scoring': rows}, ['operator'], weight):
        field, operator = item['field'], (item.get('context') or {}).get('operator')
        if operator in (None, ''):
            continue
        environment = item.get('environment') or COMBINED
        lost.setdefault(field, {}).setdefault(environment, {})[str(operator)] = item['areas']
    return lost


def _places(document: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Where the areas without polygons of their own are drawn: each City or route."""
    places = {}
    for field in ('City', 'Region', 'Cluster'):
        entries = {}
        for name, place in ((document.get('areas') or {}).get(field) or {}).items():
            if place.get('latitude') is None:
                continue
            route = place.get('points') or []
            entries[name] = {'latitude': place['latitude'], 'longitude': place['longitude'], 'kind': place.get('kind', 'place'),
                             # (A route is drawn with some of its points.)
                             'route': route[:: max(1, len(route) // 40)] if route else []}
        if entries:
            places[field] = entries
    return places


def _compared(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """What each operator loses in each area with both methodologies: {field: {environment: {operator: {area: [before, after]}}}}."""
    series: dict[str, Any] = {}
    for field in (*MAP_FIELDS, *SERVING_FIELDS):
        for environment in {*(before.get(field) or {}), *(after.get(field) or {})}:
            first = (before.get(field) or {}).get(environment) or {}
            second = (after.get(field) or {}).get(environment) or {}
            operators = {}
            for name in {*first, *second}:
                areas = {*(first.get(name) or {}), *(second.get(name) or {})}
                operators[name] = {area: [round((first.get(name) or {}).get(area, 0.0), _MAP_DIGITS),
                                          round((second.get(name) or {}).get(area, 0.0), _MAP_DIGITS)] for area in areas}
            series.setdefault(field, {})[environment] = operators
    return series


def _serving(compared: dict[str, Any]) -> dict[str, Any]:
    """What each operator gains or loses in the tests of each Vendor and kind of site of their serving cells, the values that
    move most first: {field: {environment: rows}}."""
    fields = {}
    for field in SERVING_FIELDS:
        environments = {}
        for environment, operators in (compared.get(field) or {}).items():
            listed = []
            for name in sorted({name for areas in operators.values() for name in areas}, key=str.casefold):
                if name in ('', 'Not specified'):
                    continue
                cells = {operator: {'before': areas[name][0], 'after': areas[name][1], 'delta': _rounded(areas[name][0] - areas[name][1])}
                         for operator, areas in operators.items() if name in areas}
                listed.append({'name': name, 'operators': cells, 'peak': _rounded(max((abs(cell['delta'] or 0) for cell in cells.values()), default=0.0))})
            environments[environment] = sorted(listed, key=lambda row: -row['peak'])
        if environments:
            fields[field] = environments
    return fields


def build_maps(before_document: dict[str, Any], after_document: dict[str, Any], scorings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The maps of a comparison, per scoring (``scorings``: the KPI rows and score tables of each methodology), with where to draw
    their areas: every polygon comes with the map of the second methodology (the same tests give the same areas)."""
    series, serving = {}, {}
    for scoring, sides in scorings.items():
        compared = _compared(_lost_of(before_document, sides['before_rows'], sides['before_tables']),
                             _lost_of(after_document, sides['after_rows'], sides['after_tables']))
        series[scoring] = {field: value for field, value in compared.items() if field in MAP_FIELDS}
        serving[scoring] = _serving(compared)
    tests = {}
    for (identity, environment), fields in _series_tests(after_document, ['operator']).items():
        for field, counts in fields.items():
            if field in MAP_FIELDS:
                tests.setdefault(field, {}).setdefault(environment or COMBINED, {})[str(identity[0])] = counts
    result = {'points_loss': after_document}
    boundaries = {field: map_boundaries(result, field) for field in (AREA, 'Region', 'Cluster', POSTAL)}
    return {
        'version': 1, 'series': series, 'serving': serving, 'tests': tests, 'places': _places(after_document),
        'boundaries': {field: value for field, value in boundaries.items() if value},
        'outlines': {field: map_background(result, field) for field in (AREA, POSTAL) if map_background(result, field)},
        'background': after_document.get('background') or [], 'area_label': _area_label(after_document),
        'attribution': after_document.get('postal_attribution') or '',
    }


def _area_label(document: dict[str, Any]) -> str:
    labels = list(dict.fromkeys(item.get('label') or 'area' for item in ((document.get('map_areas') or {}).get('countries') or [])))
    return labels[0] if len(labels) == 1 else 'Map Area'


def _rows_of_measure(maps: dict[str, Any], part: dict[str, Any], scoring: str, field: str, environment: str, measure: str) -> list[dict[str, Any]]:
    """Each area with the value of each operator: what it gains (positive) or loses between both methodologies."""
    rows: list[dict[str, Any]] = []
    if measure == 'own':
        for row in ((part.get('areas') or {}).get(field) or {}).get(environment) or []:
            rows.append({'name': row['area'], 'tests': None, 'cells': {
                name: {'before': cell.get('before'), 'after': cell.get('after'), 'value': cell.get('delta')}
                for name, cell in row['operators'].items() if cell.get('delta') is not None}})
        return rows
    operators = (((maps.get('series') or {}).get(scoring) or {}).get(field) or {}).get(environment) or {}
    tests = ((maps.get('tests') or {}).get(field) or {}).get(environment) or {}
    minimum = MIN_POSTAL_RATE_TESTS if field == POSTAL else MIN_RATE_TESTS
    names = sorted({name for areas in operators.values() for name in areas}, key=str.casefold)
    for name in names:
        if name in ('', 'Not specified'):
            continue
        cells = {}
        total = 0
        for operator, areas in operators.items():
            if name not in areas:
                continue
            before, after = areas[name]
            value = before - after
            count = (tests.get(operator) or {}).get(name)
            total += int(count or 0)
            if measure == 'rate':
                if not count or count < minimum:
                    continue
                value = value / count * RATE_TESTS
            cells[operator] = {'before': before, 'after': after, 'value': _rounded(value), 'tests': count}
        if cells:
            rows.append({'name': name, 'tests': total, 'cells': cells})
    return rows


def area_analysis(rows: list[dict[str, Any]], operators: list[str], *, field: str = '', relative: bool = False) -> dict[str, Any]:
    """How the impact spreads among the areas: per operator its distribution, how concentrated it is, the areas that move most and
    whether it goes with what the area scored or lost before; and whether the operators move together in the same areas."""
    summary = {}
    for name in operators:
        entries = [(row['name'], row['cells'][name]) for row in rows if name in row['cells'] and row['cells'][name].get('value') is not None]
        if not entries:
            continue
        values = [cell['value'] for _name, cell in entries]
        ordered = sorted(values)
        sizes = sorted((abs(value) for value in values), reverse=True)
        moved = sum(sizes)
        ranked = sorted(entries, key=lambda entry: entry[1]['value'])
        befores = [(cell['before'], cell['value']) for _name, cell in entries if cell.get('before') is not None]
        tests = [(cell['tests'], cell['value']) for _name, cell in entries if cell.get('tests')]
        mean = sum(values) / len(values)
        summary[name] = {
            'count': len(values), 'total': _rounded(sum(values)), 'mean': _rounded(mean),
            'deviation': _rounded((sum((value - mean) ** 2 for value in values) / len(values)) ** .5),
            'low': ordered[0], 'q1': _rounded(quantile(ordered, .25)), 'median': _rounded(quantile(ordered, .5)),
            'q3': _rounded(quantile(ordered, .75)), 'high': ordered[-1],
            'up': sum(value >= MATERIAL for value in values), 'down': sum(value <= -MATERIAL for value in values),
            'concentration': _rounded(sum(sizes[:CONCENTRATION_AREAS]) / moved) if moved else None,
            'concentration_areas': min(CONCENTRATION_AREAS, len(values)),
            # How much of the movement the areas that move most hold, in order (the curve of the concentration).
            'curve': _curve(sizes),
            'best': {'name': ranked[-1][0], 'value': ranked[-1][1]['value']}, 'worst': {'name': ranked[0][0], 'value': ranked[0][1]['value']},
            'top': [{'name': area, 'value': cell['value']} for area, cell in reversed(ranked[-TOP_AREAS:]) if cell['value'] > 0],
            'bottom': [{'name': area, 'value': cell['value']} for area, cell in ranked[:TOP_AREAS] if cell['value'] < 0],
            'r_before': _rounded(pearson([item[0] for item in befores], [item[1] for item in befores])),
            'fit_before': linear_fit([item[0] for item in befores], [item[1] for item in befores]),
            'r_tests': _rounded(pearson([item[0] for item in tests], [item[1] for item in tests])),
        }
    together: dict[str, dict[str, Any]] = {}
    for first in summary:
        together[first] = {}
        for second in summary:
            if first == second:
                continue
            pairs = [(row['cells'][first]['value'], row['cells'][second]['value']) for row in rows
                     if row['cells'].get(first, {}).get('value') is not None and row['cells'].get(second, {}).get('value') is not None]
            together[first][second] = _rounded(pearson([item[0] for item in pairs], [item[1] for item in pairs]))
    return {'field': FIELD_LABELS.get(field, field), 'relative': relative, 'operators': summary, 'together': together}


def _curve(sizes: list[float], points: int = 20) -> list[list[float]]:
    """The share of the movement held by each share of the areas, the areas that move most first."""
    moved = sum(sizes)
    if not moved or not sizes:
        return []
    curve = [[0.0, 0.0]]
    running = 0.0
    step = max(1, len(sizes) // points)
    for index, size in enumerate(sizes, start=1):
        running += size
        if index % step == 0 or index == len(sizes):
            curve.append([round(index / len(sizes), 3), round(running / moved, 3)])
    return curve


def impact_map(maps: dict[str, Any] | None, part: dict[str, Any], scoring: str, field: str, environment: str, measure: str = 'national',
               relative: bool = False) -> dict[str, Any]:
    """The values of a map, with how they spread: ``relative`` gives each operator against the mean of the operators in each area,
    so an area that moves alike for all of them shows no colour."""
    maps = maps or {}
    available = {name for name in MAP_FIELDS if ((maps.get('series') or {}).get(scoring) or {}).get(name)}
    available |= {name for name in (part.get('areas') or {})}
    field = field if field in available else next((name for name in MAP_FIELDS if name in available), field)
    # (Only the areas with polygons or positions have one; without the maps, only the scoring of each area.)
    if measure == 'own' and field not in (part.get('areas') or {}):
        measure = 'national'
    if measure != 'own' and not ((maps.get('series') or {}).get(scoring) or {}).get(field):
        measure = 'own'
    operators = [item['operator'] for item in part.get('operators') or []]
    rows = _rows_of_measure(maps, part, scoring, field, environment, measure) if field in available else []
    if relative:
        for row in rows:
            values = [cell['value'] for cell in row['cells'].values() if cell.get('value') is not None]
            mean = sum(values) / len(values) if values else 0.0
            for cell in row['cells'].values():
                if cell.get('value') is not None:
                    cell['value'] = _rounded(cell['value'] - mean)
    places = ((maps.get('places') or {}).get(field) or {})
    for row in rows:
        if row['name'] in places:
            row['place'] = places[row['name']]
    has_polygons = bool((maps.get('boundaries') or {}).get(field))
    return {'field': field, 'label': FIELD_LABELS.get(field, field) if field != AREA else maps.get('area_label') or FIELD_LABELS[AREA],
            'area_label': maps.get('area_label') or FIELD_LABELS[AREA], 'measure': measure, 'measure_label': MEASURES.get(measure, measure), 'relative': relative, 'environment': environment,
            'available': [name for name in MAP_FIELDS if name in available],
            'measures': [key for key, _label in MEASURES.items() if key != 'own' or field in (part.get('areas') or {})],
            'shape': 'polygons' if has_polygons else 'places' if places else 'none',
            'rows': rows, 'analysis': area_analysis(rows, operators, field=field, relative=relative),
            'attribution': maps.get('attribution') if field == POSTAL else '',
            'map_error': maps.get('error') or ''}


def map_geometry(maps: dict[str, Any] | None, field: str) -> dict[str, Any]:
    """The polygons of a field and the outlines of their countries."""
    maps = maps or {}
    boundaries = (maps.get('boundaries') or {}).get(field) or {}
    outlines = (maps.get('outlines') or {}).get(field) or []
    if not boundaries:
        # The places are drawn on the Map Areas, in grey.
        outlines = [ring for rings in ((maps.get('boundaries') or {}).get(AREA) or {}).values() for ring in rings]
    return {'field': field, 'boundaries': boundaries, 'outlines': outlines}
