"""The maps of the Methodology Impact (see scoring_impact): the Points Lost Map of the same tests with each methodology, compared
area by area. The points of the National scoring each area loses add up to what the operator loses, so what an area gains or loses
between both methodologies adds up to what the methodology moves for the operator, on any geography.
"""
from __future__ import annotations

from typing import Any

from src.modules.scoring.scoring_impact_analysis import COMBINED, MATERIAL, _rounded
from src.modules.scoring.scoring_insights import MIN_POSTAL_RATE_TESTS, MIN_RATE_TESTS, RATE_TESTS, _combined_weight_of, _combined_weights, _scopes, _series_tests
from src.modules.scoring.scoring_points_loss import AREA, POSTAL, map_background, map_boundaries, points_loss_maps

MAP_FIELDS = ('City', 'Region', 'Cluster', AREA, POSTAL)
FIELD_LABELS = {'City': 'City', 'Region': 'Region', 'Cluster': 'Cluster', AREA: 'Map Area', POSTAL: 'Postal Code'}
MEASURES = {'national': 'National points', 'rate': 'National points per 1,000 tests', 'own': 'Scoring of the area'}
TOP_AREAS = 6
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
    for field in MAP_FIELDS:
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


def build_maps(before_document: dict[str, Any], after_document: dict[str, Any], scorings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The maps of a comparison, per scoring (``scorings``: the KPI rows and score tables of each methodology), with where to draw
    their areas: every polygon comes with the map of the second methodology (the same tests give the same areas)."""
    series = {}
    for scoring, sides in scorings.items():
        series[scoring] = _compared(_lost_of(before_document, sides['before_rows'], sides['before_tables']),
                                    _lost_of(after_document, sides['after_rows'], sides['after_tables']))
    tests = {}
    for (identity, environment), fields in _series_tests(after_document, ['operator']).items():
        for field, counts in fields.items():
            if field in MAP_FIELDS:
                tests.setdefault(field, {}).setdefault(environment or COMBINED, {})[str(identity[0])] = counts
    result = {'points_loss': after_document}
    boundaries = {field: map_boundaries(result, field) for field in (AREA, 'Region', 'Cluster', POSTAL)}
    return {
        'version': 1, 'series': series, 'tests': tests, 'places': _places(after_document),
        'boundaries': {field: value for field, value in boundaries.items() if value},
        'outlines': {field: map_background(result, field) for field in (AREA, POSTAL) if map_background(result, field)},
        'background': after_document.get('background') or [],
        'attribution': after_document.get('postal_attribution') or '',
    }


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


def area_analysis(rows: list[dict[str, Any]], operators: list[str], *, field: str = '') -> dict[str, Any]:
    """Per operator: what its areas add up to, how many move, and those where it gains and loses most."""
    summary = {}
    for name in operators:
        entries = [(row['name'], row['cells'][name]) for row in rows if name in row['cells'] and row['cells'][name].get('value') is not None]
        if not entries:
            continue
        values = [cell['value'] for _name, cell in entries]
        ranked = sorted(entries, key=lambda entry: entry[1]['value'])
        summary[name] = {
            'count': len(values), 'total': _rounded(sum(values)),
            'up': sum(value >= MATERIAL for value in values), 'down': sum(value <= -MATERIAL for value in values),
            'best': {'name': ranked[-1][0], 'value': ranked[-1][1]['value']}, 'worst': {'name': ranked[0][0], 'value': ranked[0][1]['value']},
            'top': [{'name': area, 'value': cell['value']} for area, cell in reversed(ranked[-TOP_AREAS:]) if cell['value'] > 0],
            'bottom': [{'name': area, 'value': cell['value']} for area, cell in ranked[:TOP_AREAS] if cell['value'] < 0],
        }
    return {'field': FIELD_LABELS.get(field, field), 'operators': summary}


def impact_map(maps: dict[str, Any] | None, part: dict[str, Any], scoring: str, field: str, environment: str, measure: str = 'national') -> dict[str, Any]:
    """The values of a map, with the areas that move most for each operator."""
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
    places = ((maps.get('places') or {}).get(field) or {})
    for row in rows:
        if row['name'] in places:
            row['place'] = places[row['name']]
    has_polygons = bool((maps.get('boundaries') or {}).get(field))
    return {'field': field, 'label': FIELD_LABELS.get(field, field), 'measure': measure, 'measure_label': MEASURES.get(measure, measure), 'environment': environment,
            'available': [name for name in MAP_FIELDS if name in available],
            'measures': [key for key, _label in MEASURES.items() if key != 'own' or field in (part.get('areas') or {})],
            'shape': 'polygons' if has_polygons else 'places' if places else 'none',
            'rows': rows, 'analysis': area_analysis(rows, operators, field=field),
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
