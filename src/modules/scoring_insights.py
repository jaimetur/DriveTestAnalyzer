"""Scoring insights derived from the saved scoring views.

Where each operator stands (standings, position matrices, GAP parts and levers), the location cards and rankings,
the KPI GAP profiles, campaign trends and comparisons and the points at stake are built from the per-environment score
tables, and the Points Lost views from the points-lost shares of the result, so the web page and the PowerPoint/Word
exports show the same numbers.
"""
from __future__ import annotations

import json
import re
from typing import Any

from src.modules.column_names import campaign_sort_key as shared_campaign_sort_key, compact_campaign_value

LOCATION_LEVELS = ('City', 'Cluster', 'Region')
MAX_LOCATION_CARDS = 12
# A trend needs two campaigns (or periods) at least.
MIN_TREND_CAMPAIGNS = 2
MIN_COMPARISON_CAMPAIGNS = 2
_CONTEXT_FIELDS = ('vendor', 'region', 'cluster', 'city', 'campaign', 'dataset_type')
_LEVEL_FIELDS = {'Vendor': 'vendor', 'Region': 'region', 'Cluster': 'cluster', 'City': 'city', 'Campaign': 'campaign',
                 'Dataset Type': 'dataset_type'}
COMBINED = 'Combined'


def build_scoring_insights(score_tables: list[dict[str, Any]], configuration: dict[str, Any],
                           levels: list[str], result: dict[str, Any] | None = None, *,
                           location_minimum: int = 2) -> dict[str, Any]:
    """Insights for every environment of the views; each item names its environment. The location cards need
    ``location_minimum`` locations in a group (one for the Geographical calculation of London)."""
    environments = list(dict.fromkeys(str(table['context'].get('environment')) for table in score_tables))
    scopes = _scopes(score_tables)
    insights: dict[str, list[dict[str, Any]]] = {
        'location_cards': [], 'kpi_gap_profiles': [], 'campaign_trends': [], 'campaign_comparisons': [],
        'standings': [], 'position_matrices': [], 'gap_parts': [], 'levers': [], 'points_at_stake': [],
        'location_rankings': [],
    }
    formulas = {str(metric.get('code')): str((metric.get('calculation') or {}).get('formula') or '')
                for metric in configuration.get('metrics', [])}
    cities = ((((result or {}).get('points_loss') or {}).get('areas') or {}).get('City') or {})
    for environment in environments:
        summaries = {scope: _scope_summary(tables, environment) for scope, tables in scopes.items()}
        summaries = {scope: summary for scope, summary in summaries.items() if summary is not None}
        insights['location_cards'].extend(_location_cards(summaries, levels, environment, location_minimum))
        insights['campaign_trends'].extend(_campaign_trends(summaries, levels, environment))
        insights['campaign_comparisons'].extend(_campaign_comparisons(scopes, levels, environment))
        insights['kpi_gap_profiles'].extend(_kpi_gap_profiles(scopes, environment))
        insights['standings'].extend(_standings(scopes, levels, environment))
        insights['position_matrices'].extend(_position_matrices(scopes, levels, environment))
        insights['gap_parts'].extend(_gap_parts(scopes, levels, environment))
        insights['levers'].extend(_levers(scopes, levels, environment))
        insights['points_at_stake'].extend(_points_at_stake(scopes, levels, environment, formulas))
        insights['location_rankings'].extend(_location_rankings(summaries, levels, environment, cities))
    insights['campaign_scope'] = _campaign_scope(score_tables, configuration, result, environments)
    maps, insights['points_loss_background'] = _points_loss_maps(result, score_tables)
    # The maps of the areas; the Vendors, kinds of site, sites and stretches have their own views.
    insights['points_loss_maps'] = [item for item in maps if item['field'] in {'City', 'Area', 'Region', 'Cluster'}]
    insights.update(_serving_views(maps, result))
    # Where to act: the plan, each performance owner, the places ranked and the route that loses most.
    from src.modules.scoring_where_to_act import build_where_to_act
    labels = {name: str(scope.get('display_name') or name)
              for name, scope in (configuration.get('scope') or {}).get('environments', {}).items()}
    styles = {name: {**style, 'is_reference': name in {table.get('baseline_operator') for table in score_tables}}
              for name, style in operator_styles(score_tables).items()}
    insights.update(build_where_to_act(insights, maps, result, labels, formulas, styles))
    return insights


def operator_styles(score_tables: list[dict[str, Any]]) -> dict[str, Any]:
    """The label, colour and position of every operator of the score tables.

    Each table lists only its own operators, so an operator present in some
    campaigns or scopes only (such as VF SA) takes its style from those tables.
    """
    styles: dict[str, Any] = {}
    for table in score_tables:
        for operator, style in (table.get('operator_styles') or {}).items():
            styles.setdefault(operator, style)
    return styles


def _points_loss_maps(result: dict[str, Any] | None, score_tables: list[dict[str, Any]]) -> tuple[list, list]:
    """Points lost per area of each operator series, with the area locations to draw them."""
    from src.modules.scoring_points_loss import ENTRY_FIELDS, points_loss_maps
    document = (result or {}).get('points_loss')
    if not isinstance(document, dict) or not document.get('shares'):
        return [], []
    keys = [key for key in document['shares'][0] if key not in ENTRY_FIELDS]
    styles = operator_styles(score_tables)
    references = {table.get('baseline_operator') for table in score_tables}
    geometry = document.get('areas') or {}
    # What the map areas are, such as ITL3 areas or municipalities, and the countries without them.
    countries = (document.get('map_areas') or {}).get('countries') or []
    labels = list(dict.fromkeys(item.get('label') or 'area' for item in countries))
    area_label = labels[0] if len(labels) == 1 else 'map area'
    unmapped = (document.get('map_areas') or {}).get('unmapped_countries') or []
    maps = []
    for item in points_loss_maps(result, keys):
        context = item['context']
        operator = context.get('operator')
        style = styles.get(operator) or {}
        located = geometry.get(item['field']) or {}
        areas = []
        for name, points in sorted(item['areas'].items(), key=lambda entry: -entry[1]):
            place = located.get(name) or {}
            areas.append({'name': name, 'points': points, 'share': points / item['total'] if item['total'] else 0,
                          'latitude': place.get('latitude'), 'longitude': place.get('longitude'),
                          'kind': place.get('kind', 'place'), 'route': place.get('points') or [],
                          # The map areas holding its tests and how many, and the points it loses in each one:
                          # the City (or route) alone on the map.
                          'area_tests': place.get('area_tests') or {},
                          'area_losses': (item.get('area_losses') or {}).get(name) or {},
                          # All environments: the environments where the area loses points, most first.
                          'environments': (item.get('environments') or {}).get(name, []),
                          # A site: its network, ID, Vendor and City; a stretch: its route and Vendor.
                          **{key: place[key] for key in ('network', 'site', 'vendor', 'city', 'route_name', 'region') if place.get(key)}})
        maps.append({
            'environment': item.get('environment') or COMBINED, 'operator': operator, 'label': style.get('label') or operator,
            'color': style.get('color'), 'is_reference': operator in references, 'field': item['field'],
            'context': {field: value for field, value in context.items()
                        if field != 'operator' and value not in (None, '')},
            'areas': areas, 'total': item['total'],
            **({'area_label': area_label, 'unmapped_countries': unmapped} if item['field'] == 'Area' else {}),
            **{key: item[key] for key in ('failures', 'city_losses') if item.get(key)},
        })
    maps.sort(key=lambda item: ((styles.get(item['operator']) or {}).get('position', 99), str(item['operator']),
                                json.dumps(item['context'], sort_keys=True, default=str), item['field']))
    return maps, document.get('background') or []


def _scope_key(context: dict[str, Any]) -> tuple:
    return tuple((field, context.get(field)) for field in _CONTEXT_FIELDS)


def _scopes(score_tables: list[dict[str, Any]]) -> dict[tuple, dict[str, dict[str, Any]]]:
    scopes: dict[tuple, dict[str, dict[str, Any]]] = {}
    for table in score_tables:
        context = table.get('context') or {}
        scopes.setdefault(_scope_key(context), {})[str(context.get('environment'))] = table
    return scopes


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _service(row: dict[str, Any]) -> str:
    return 'Data' if str(row.get('source_kind') or '').casefold() == 'data' else 'Voice'


def _kpi_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in table.get('rows', []) if row.get('kpi_code')]


def _environment_points(table: dict[str, Any], operator: str) -> dict[str, Any]:
    """Voice and Data points of one operator in one environment table, with their maxima."""
    totals = {'Voice': 0.0, 'Data': 0.0, 'max_Voice': 0.0, 'max_Data': 0.0, 'measured': False, 'complete': True}
    for row in _kpi_rows(table):
        maximum = _number(row.get('max_points')) or 0.0
        if maximum <= 0:
            continue
        service = _service(row)
        totals[f'max_{service}'] += maximum
        value = (row.get('values') or {}).get(operator) or {}
        points = _number(value.get('points'))
        if points is None:
            totals['complete'] = False
            continue
        totals['measured'] = True
        totals[service] += points
        if value.get('complete') is False:
            totals['complete'] = False
    return totals


def _scope_summary(tables: dict[str, dict[str, Any]], environment: str) -> dict[str, Any] | None:
    """Points per operator of one scope, scaled to the full maximum of the environment.

    All Environments adds the environments measured for that scope and scales them to
    the full maximum, as NetCheck scales per-city rankings to 1,000 points.
    """
    if environment not in tables:
        return None
    table = tables[environment]
    if environment == COMBINED:
        sources = [source for name, source in tables.items()
                   if name != COMBINED and any((_number(row.get('max_points')) or 0) > 0 for row in _kpi_rows(source))]
    else:
        sources = [table]
    if not sources:
        return None
    # All Environments scales to the maximum of the methodology (that of its own table), also when an environment
    # has no measurements in the scope (a city without Connecting Roads, for example).
    totals_from = [table] if environment == COMBINED and any(
        (_number(row.get('max_points')) or 0) > 0 for row in _kpi_rows(table)) else sources
    maximum = max(sum(_number(row.get('max_points')) or 0.0 for source in sources for row in _kpi_rows(source)),
                  sum(_number(row.get('max_points')) or 0.0 for source in totals_from for row in _kpi_rows(source)))
    service_maximum = {service: max(sum(_number(row.get('max_points')) or 0.0 for source in group
                                        for row in _kpi_rows(source) if _service(row) == service)
                                    for group in (sources, totals_from))
                       for service in ('Voice', 'Data')}
    operators = []
    scaled = False
    for operator in table.get('operators', []):
        parts = [_environment_points(source, operator) for source in sources]
        measured = [part for part in parts if part['measured']]
        if not measured:
            continue
        reached = sum(part['max_Voice'] + part['max_Data'] for part in measured)
        factor = maximum / reached if reached > 0 else 1.0
        scaled = scaled or abs(factor - 1) > 1e-9
        voice = sum(part['Voice'] for part in measured) * factor
        data = sum(part['Data'] for part in measured) * factor
        style = (table.get('operator_styles') or {}).get(operator) or {}
        operators.append({
            'operator': operator, 'label': style.get('label') or operator, 'color': style.get('color'),
            'voice': voice, 'data': data, 'total': voice + data,
            'complete': all(part['complete'] for part in measured) and len(measured) == len(parts),
            'is_reference': operator == table.get('baseline_operator'),
        })
    if not operators:
        return None
    return {'context': dict(table.get('context') or {}), 'maximum': maximum, 'scaled': scaled,
            'max_voice': service_maximum['Voice'], 'max_data': service_maximum['Data'],
            'operators': operators, 'baseline_operator': table.get('baseline_operator')}


def _display(level: str, value: Any) -> str:
    return compact_campaign_value(value) if level == 'Campaign' else str(value)


def campaign_sort_key(value: Any) -> tuple:
    """Chronological campaign order shared by every module (plain, NSA, then SA in a quarter)."""
    return shared_campaign_sort_key(value)


def _group_label(context: dict[str, Any], levels: list[str], excluded: set[str]) -> str:
    parts = [f'{level}: {_display(level, context.get(field))}' for level, field in _LEVEL_FIELDS.items()
             if level in levels and level not in excluded and context.get(field) not in (None, '')]
    return ' · '.join(parts)


def _location_cards(summaries: dict[tuple, dict[str, Any]], levels: list[str], environment: str,
                    minimum: int = 2) -> list[dict[str, Any]]:
    selected = [level for level in LOCATION_LEVELS if level in levels]
    for level in selected:
        field = _LEVEL_FIELDS[level]
        groups: dict[tuple, list[dict[str, Any]]] = {}
        for summary in summaries.values():
            context = summary['context']
            if context.get(field) in (None, ''):
                continue
            key = tuple((name, context.get(name)) for name in _CONTEXT_FIELDS if name != field)
            groups.setdefault(key, []).append(summary)
        usable = [cards for cards in groups.values() if minimum <= len(cards) <= MAX_LOCATION_CARDS]
        if not usable:
            continue
        return [{
            'environment': environment, 'level': level,
            'title': _group_label(cards[0]['context'], levels, {level}),
            'maximum': cards[0]['maximum'], 'scaled': any(card['scaled'] for card in cards),
            'max_voice': cards[0]['max_voice'], 'max_data': cards[0]['max_data'],
            'campaign': cards[0]['context'].get('campaign') if level != 'Campaign' else None,
            'cards': [{'label': _display(level, card['context'].get(field)), 'operators': card['operators']}
                      for card in sorted(cards, key=lambda item: str(item['context'].get(field)).casefold())],
        } for cards in usable]
    return []


def _campaign_groups(summaries: dict[tuple, dict[str, Any]]) -> dict[tuple, list[dict[str, Any]]]:
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for summary in summaries.values():
        context = summary['context']
        if context.get('campaign') in (None, ''):
            continue
        key = tuple((name, context.get(name)) for name in _CONTEXT_FIELDS if name != 'campaign')
        groups.setdefault(key, []).append(summary)
    return groups


def _campaign_trends(summaries: dict[tuple, dict[str, Any]], levels: list[str], environment: str) -> list[dict[str, Any]]:
    if 'Campaign' not in levels:
        return []
    trends = []
    for members in _campaign_groups(summaries).values():
        members = sorted(members, key=lambda item: campaign_sort_key(item['context'].get('campaign')))
        if len(members) < MIN_TREND_CAMPAIGNS:
            continue
        operators: dict[str, dict[str, Any]] = {}
        for index, member in enumerate(members):
            for item in member['operators']:
                series = operators.setdefault(item['operator'], {
                    'operator': item['operator'], 'label': item['label'], 'color': item['color'],
                    'is_reference': item['is_reference'], 'points': [None] * len(members),
                })
                series['points'][index] = item['total']
        trends.append({
            'environment': environment, 'title': _group_label(members[0]['context'], levels, {'Campaign'}),
            'maximum': members[0]['maximum'],
            'campaigns': [_display('Campaign', member['context'].get('campaign')) for member in members],
            'series': list(operators.values()),
        })
    return trends


def _campaign_comparisons(scopes: dict[tuple, dict[str, dict[str, Any]]], levels: list[str],
                          environment: str) -> list[dict[str, Any]]:
    """Each operator's KPI points in the two latest campaigns of every group, latest minus previous, plus the KPI
    values and points of every campaign of the group (campaigns and kpis) so any two of them can be compared."""
    if 'Campaign' not in levels:
        return []
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for tables in scopes.values():
        table = tables.get(environment)
        if table is None or table['context'].get('campaign') in (None, ''):
            continue
        key = tuple((name, table['context'].get(name)) for name in _CONTEXT_FIELDS if name != 'campaign')
        groups.setdefault(key, []).append(table)
    comparisons = []
    for tables in groups.values():
        tables = sorted(tables, key=lambda table: campaign_sort_key(table['context'].get('campaign')))
        if len(tables) < MIN_COMPARISON_CAMPAIGNS:
            continue
        previous, latest = tables[-2], tables[-1]
        previous_rows = {row['kpi_code']: row for row in _kpi_rows(previous)}
        # Every KPI with points in a campaign of the group, in the order of the latest campaign first.
        campaign_rows = [{row['kpi_code']: row for row in _kpi_rows(table)} for table in tables]
        kpi_codes = list(dict.fromkeys(row['kpi_code'] for table in reversed(tables) for row in _kpi_rows(table)
                                       if (_number(row.get('max_points')) or 0) > 0))
        for operator in latest.get('operators', []):
            rows = []
            for row in _kpi_rows(latest):
                if (_number(row.get('max_points')) or 0) <= 0:
                    continue
                before = ((previous_rows.get(row['kpi_code']) or {}).get('values') or {}).get(operator) or {}
                after = (row.get('values') or {}).get(operator) or {}
                before_points, after_points = _number(before.get('points')), _number(after.get('points'))
                rows.append({
                    'kpi_code': row['kpi_code'], 'kpi': row.get('kpi'), 'category': row.get('category'),
                    'service': _service(row), 'previous_value': _number(before.get('value')),
                    'previous_points': before_points, 'latest_value': _number(after.get('value')),
                    'latest_points': after_points,
                    'delta': after_points - before_points if None not in (after_points, before_points) else None,
                })
            if not any(row['delta'] is not None for row in rows):
                continue
            rows.sort(key=lambda item: (item['delta'] is None, item['delta'] if item['delta'] is not None else 0))
            kpis = []
            for code in kpi_codes:
                row = next(rows_by_code[code] for rows_by_code in reversed(campaign_rows) if code in rows_by_code)
                values = []
                for rows_by_code in campaign_rows:
                    value = (((rows_by_code.get(code) or {}).get('values') or {}).get(operator) or {})
                    points = _number(value.get('points'))
                    values.append({'value': _number(value.get('value')), 'points': points} if points is not None else None)
                kpis.append({'kpi_code': code, 'kpi': row.get('kpi'), 'category': row.get('category'),
                             'service': _service(row), 'values': values})
            style = (latest.get('operator_styles') or {}).get(operator) or {}
            comparisons.append({
                'environment': environment, 'operator': operator, 'label': style.get('label') or operator,
                'color': style.get('color'),
                'title': _group_label(latest['context'], levels, {'Campaign'}),
                'previous_campaign': _display('Campaign', previous['context'].get('campaign')),
                'latest_campaign': _display('Campaign', latest['context'].get('campaign')),
                'rows': rows, 'total_delta': sum(row['delta'] for row in rows if row['delta'] is not None),
                'campaigns': [_display('Campaign', table['context'].get('campaign')) for table in tables], 'kpis': kpis,
            })
    return comparisons


def _kpi_gap_profiles(scopes: dict[tuple, dict[str, dict[str, Any]]], environment: str) -> list[dict[str, Any]]:
    """Per compared operator: the points lost against the maximum and the GAP to the reference, per KPI."""
    profiles = []
    for tables in scopes.values():
        table = tables.get(environment)
        if table is None:
            continue
        if environment == COMBINED:
            columns = [name for name, source in tables.items() if name != COMBINED
                       and any((_number(row.get('max_points')) or 0) > 0 for row in _kpi_rows(source))]
        else:
            columns = [environment]
        if not columns:
            continue
        reference = table.get('baseline_operator')
        for operator in table.get('operators', []):
            rows = []
            for row in _kpi_rows(table):
                to_maximum: dict[str, float | None] = {}
                to_reference: dict[str, float | None] = {}
                for name in columns:
                    source = next((item for item in _kpi_rows(tables[name]) if item['kpi_code'] == row['kpi_code']), None)
                    maximum = _number((source or {}).get('max_points')) or 0.0
                    points = _number((((source or {}).get('values') or {}).get(operator) or {}).get('points'))
                    to_maximum[name] = maximum - points if points is not None and maximum > 0 else None
                    gap = ((source or {}).get('gaps') or {}).get(operator)
                    to_reference[name] = _number(gap) if operator != reference else None
                if all(value is None for value in to_maximum.values()):
                    continue
                rows.append({
                    'kpi_code': row['kpi_code'], 'kpi': row.get('kpi'), 'category': row.get('category'),
                    'service': _service(row), 'kpi_type': row.get('kpi_type'),
                    'gap_to_maximum': to_maximum,
                    'total_gap_to_maximum': sum(value for value in to_maximum.values() if value is not None),
                    'gap_to_reference': to_reference,
                    'total_gap_to_reference': (sum(value for value in to_reference.values() if value is not None)
                                               if any(value is not None for value in to_reference.values()) else None),
                })
            if not rows:
                continue
            style = (table.get('operator_styles') or {}).get(operator) or {}
            profiles.append({
                'environment': environment, 'operator': operator, 'label': style.get('label') or operator,
                'color': style.get('color'), 'reference': reference, 'reference_label': ((table.get('operator_styles') or {}).get(reference) or {}).get('label') or reference,
                'context': {field: table['context'].get(field) for field in _CONTEXT_FIELDS if table['context'].get(field) not in (None, '')},
                'columns': columns,
                'to_maximum': sorted(rows, key=lambda item: -item['total_gap_to_maximum']),
                'to_reference': sorted(
                    (item for item in rows if item['total_gap_to_reference'] is not None),
                    key=lambda item: item['total_gap_to_reference']),
            })
    return profiles


# ---------------------------------------------------------------------------------------------------------------------
# Summary, Geographical Areas and Points Lost: where each operator stands, how it ranks in each environment and service, which
# parts of the scoring hold its GAP, the KPIs that would close it, the points it can still win back, every location
# ranked, and who serves the tests where it loses its points.
MAX_GAP_CAMPAIGNS = 6
MAX_LEVERS = 8
MAX_SITES = 25
MAX_STRETCH_ROUTES = 6
MAX_ROUTE_STRETCHES = 8
# A site is High priority with this many points lost and losses in an earlier campaign too, Medium with one of them.
SITE_PRIORITY_POINTS = 1.0
LOSS_KINDS = ('failed', 'below_par', 'quality')
LOSS_KIND_LABELS = {'failed': 'Failed tests', 'below_par': 'Below the threshold', 'quality': 'Quality shortfall'}
SERVICE_ORDER = ('Data', 'Voice')
SERVICES = ('Voice', 'Data', 'Overall')
_AGGREGATE_FORMULA = re.compile(r'(AVG|MEDIAN|PCT90)\(\w+\)')
_COMPASS = ('north', 'north-east', 'east', 'south-east', 'south', 'south-west', 'west', 'north-west')


def ordinal(number: int) -> str:
    suffix = 'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def _signed(value: float | None, digits: int = 1) -> str:
    return '—' if value is None else f'{value:+,.{digits}f}'.replace('-', '−')


def _clean_context(context: dict[str, Any], *, campaign: bool = True) -> dict[str, Any]:
    return {field: context.get(field) for field in _CONTEXT_FIELDS
            if context.get(field) not in (None, '') and (campaign or field != 'campaign')}


def _scope_groups(scopes: dict[tuple, dict[str, dict[str, Any]]], environment: str) -> list[list[dict[str, Any]]]:
    """The scopes with the same context but the campaign, each list in chronological order, with an ``environment``
    table in every member."""
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for tables in scopes.values():
        table = tables.get(environment)
        if table is None:
            continue
        context = table.get('context') or {}
        key = tuple((field, context.get(field)) for field in _CONTEXT_FIELDS if field != 'campaign')
        groups.setdefault(key, []).append(tables)
    return [sorted(members, key=lambda tables: campaign_sort_key(tables[environment]['context'].get('campaign')))
            for members in groups.values()]


def _styles(table: dict[str, Any], operator: str) -> dict[str, Any]:
    style = (table.get('operator_styles') or {}).get(operator) or {}
    return {'operator': operator, 'label': style.get('label') or operator, 'color': style.get('color'),
            'is_reference': operator == table.get('baseline_operator')}


def _by_reliability(table: dict[str, Any]) -> bool:
    """Whether the KPIs of a table are typed Reliable or not (the NetCheck methodologies): their parts are then the
    reliability and the quality of each service; otherwise the categories."""
    return any(str(row.get('kpi_type') or '').casefold() == 'reliable' for row in _kpi_rows(table))


def _part_of(row: dict[str, Any], by_reliability: bool) -> str:
    if by_reliability:
        kind = 'reliability' if str(row.get('kpi_type') or '').casefold() == 'reliable' else 'quality'
        return f'{_service(row)} {kind}'
    return str(row.get('category') or 'Other')


def _part_order(parts: list[str], by_reliability: bool) -> list[str]:
    if not by_reliability:
        return parts
    order = [f'{service} {kind}' for service in SERVICE_ORDER for kind in ('reliability', 'quality')]
    return sorted(parts, key=lambda part: order.index(part) if part in order else len(order))


def _part_gaps(table: dict[str, Any], by_reliability: bool) -> dict[str, dict[str, float]]:
    """Each operator's GAP to the reference in every part of the scoring (the sum of the GAPs of its KPIs)."""
    gaps: dict[str, dict[str, float]] = {}
    for row in _kpi_rows(table):
        if (_number(row.get('max_points')) or 0) <= 0:
            continue
        part = _part_of(row, by_reliability)
        for operator, gap in (row.get('gaps') or {}).items():
            value = _number(gap)
            if value is not None and operator != table.get('baseline_operator'):
                gaps.setdefault(operator, {})[part] = gaps.get(operator, {}).get(part, 0.0) + value
    return gaps


def _standing_takeaway(row: dict[str, Any], leader: dict[str, Any], below: dict[str, Any] | None,
                       reference_label: str, maximum: float, previous_campaign: str | None) -> str:
    text = f"{row['label']} is {ordinal(row['rank'])} of {row['of']} with {row['total']:,.1f} of {maximum:,.0f}"
    if row['rank'] == 1:
        text += f", {row['lead_over_below']:,.1f} ahead of {below['label']}" if below else ''
    else:
        text += f", {abs(row['gap_to_leader']):,.1f} behind {leader['label']}"
        if below:
            text += f" and {row['lead_over_below']:,.1f} ahead of {below['label']}"
    gap = row.get('gap_to_reference')
    # The GAP to the reference, unless the sentence already measured the operator against it.
    named = {leader['label']} if row['rank'] > 1 else set()
    named |= {below['label']} if below else set()
    if gap is not None and reference_label not in named:
        text += f"; {_signed(gap)} vs {reference_label}"
    parts = sorted(((name, value) for name, value in (row.get('parts') or {}).items() if value < -0.05),
                   key=lambda item: item[1])
    if parts and gap is not None and gap < 0:
        text += f"; {parts[0][0]} holds most of its GAP ({_signed(parts[0][1])})"
    if row.get('delta') is not None and previous_campaign:
        text += f"; {_signed(row['delta'])} since {previous_campaign}"
    return text + '.'


def _standings(scopes, levels: list[str], environment: str) -> list[dict[str, Any]]:
    """Per scope (its latest campaign): each operator's score and position, its distance to the leader, to the
    reference and to the operators around it, its change since the previous campaign and a sentence that says it."""
    items = []
    for members in _scope_groups(scopes, environment):
        latest = members[-1]
        summary = _scope_summary(latest, environment)
        if summary is None:
            continue
        previous = _scope_summary(members[-2], environment) if len(members) > 1 else None
        previous_totals = {item['operator']: item['total'] for item in (previous or {}).get('operators', [])}
        table = latest[environment]
        reference = table.get('baseline_operator')
        by_reliability = _by_reliability(table)
        parts = _part_gaps(table, by_reliability)
        operators = sorted(summary['operators'], key=lambda item: -item['total'])
        reference_item = next((item for item in operators if item['operator'] == reference), None)
        reference_label = (reference_item or {}).get('label') or reference
        context = table.get('context') or {}
        previous_campaign = _display('Campaign', members[-2][environment]['context'].get('campaign')) if previous else None
        rows = []
        for index, item in enumerate(operators):
            above = operators[index - 1] if index else None
            below = operators[index + 1] if index + 1 < len(operators) else None
            row = {
                **{key: item[key] for key in ('operator', 'label', 'color', 'voice', 'data', 'total', 'complete',
                                              'is_reference')},
                'reference': reference,
                'rank': 1 + sum(1 for other in operators if other['total'] > item['total'] + 1e-9),
                'of': len(operators),
                'gap_to_leader': item['total'] - operators[0]['total'],
                'gap_to_above': item['total'] - above['total'] if above else None,
                'above_label': above['label'] if above else None,
                'lead_over_below': item['total'] - below['total'] if below else None,
                'below_label': below['label'] if below else None,
                'gap_to_reference': (item['total'] - reference_item['total']
                                     if reference_item and item['operator'] != reference else None),
                'voice_gap': (item['voice'] - reference_item['voice']
                              if reference_item and item['operator'] != reference else None),
                'data_gap': (item['data'] - reference_item['data']
                             if reference_item and item['operator'] != reference else None),
                'previous': previous_totals.get(item['operator']),
                'parts': {part: parts[item['operator']][part]
                          for part in _part_order(list(parts.get(item['operator'], {})), by_reliability)},
            }
            row['delta'] = row['total'] - row['previous'] if row['previous'] is not None else None
            row['takeaway'] = _standing_takeaway(row, operators[0], below, reference_label, summary['maximum'],
                                                 previous_campaign)
            rows.append(row)
        items.append({
            'environment': environment, 'context': _clean_context(context),
            'title': _group_label(context, levels, {'Campaign'}),
            'campaign': _display('Campaign', context.get('campaign')) if context.get('campaign') else None,
            'previous_campaign': previous_campaign, 'maximum': summary['maximum'],
            'max_voice': summary['max_voice'], 'max_data': summary['max_data'], 'scaled': summary['scaled'],
            'reference': reference, 'reference_label': reference_label, 'by_reliability': by_reliability,
            'operators': rows,
        })
    return items


def _rank(values: dict[str, float | None]) -> dict[str, int]:
    known = {name: value for name, value in values.items() if value is not None}
    return {name: 1 + sum(1 for other in known.values() if other > value + 1e-9) for name, value in known.items()}


def _position_matrices(scopes, levels: list[str], environment: str) -> list[dict[str, Any]]:
    """Per scope (its latest campaign): each operator's position and share of the points available in Voice, Data and
    overall, in every environment and in all of them, with the points it missed there."""
    items = []
    for members in _scope_groups(scopes, environment):
        latest = members[-1]
        table = latest[environment]
        names = ([name for name, source in latest.items() if name != COMBINED
                  and any((_number(row.get('max_points')) or 0) > 0 for row in _kpi_rows(source))]
                 if environment == COMBINED else [environment])
        operators = list(table.get('operators', []))
        rows = []
        for name in [*names, *([COMBINED] if environment == COMBINED else [])]:
            if name == COMBINED:
                summary = _scope_summary(latest, COMBINED)
                if summary is None:
                    continue
                points = {item['operator']: {'Voice': item['voice'], 'Data': item['data']} for item in summary['operators']}
                maxima = {'Voice': summary['max_voice'], 'Data': summary['max_data']}
            else:
                parts = {operator: _environment_points(latest[name], operator) for operator in operators}
                points = {operator: {'Voice': part['Voice'], 'Data': part['Data']}
                          for operator, part in parts.items() if part['measured']}
                first = next(iter(parts.values()), None)
                maxima = {'Voice': first['max_Voice'] if first else 0.0, 'Data': first['max_Data'] if first else 0.0}
            if not points:
                continue
            maxima['Overall'] = maxima['Voice'] + maxima['Data']
            cells: dict[str, dict[str, Any]] = {}
            for service in SERVICES:
                maximum = maxima[service]
                if maximum <= 0:
                    continue
                scored = {operator: (values['Voice'] + values['Data'] if service == 'Overall' else values[service])
                          for operator, values in points.items()}
                ranks = _rank(scored)
                cells[service] = {operator: {'points': value, 'maximum': maximum, 'percent': value / maximum * 100,
                                             'missed': maximum - value, 'rank': ranks.get(operator), 'of': len(ranks)}
                                  for operator, value in scored.items()}
            rows.append({'environment': name, 'cells': cells})
        if not rows:
            continue
        context = table.get('context') or {}
        items.append({
            'environment': environment, 'context': _clean_context(context),
            'title': _group_label(context, levels, {'Campaign'}),
            'campaign': _display('Campaign', context.get('campaign')) if context.get('campaign') else None,
            'operators': [_styles(table, operator) for operator in operators], 'rows': rows,
        })
    return items


def _gap_parts(scopes, levels: list[str], environment: str) -> list[dict[str, Any]]:
    """Per scope and compared operator: its GAP to the reference in every part of the scoring (Voice and Data, their
    reliability and quality with the NetCheck KPI types, else each category) in the latest campaigns."""
    items = []
    for members in _scope_groups(scopes, environment):
        members = members[-MAX_GAP_CAMPAIGNS:]
        latest = members[-1][environment]
        reference = latest.get('baseline_operator')
        by_reliability = _by_reliability(latest)
        campaigns = [_display('Campaign', tables[environment]['context'].get('campaign'))
                     if tables[environment]['context'].get('campaign') else '' for tables in members]
        gaps = [_part_gaps(tables[environment], by_reliability) for tables in members]
        for operator in latest.get('operators', []):
            if operator == reference:
                continue
            names = _part_order(list(dict.fromkeys(part for gap in gaps for part in gap.get(operator, {}))), by_reliability)
            if not names:
                continue
            totals = [_number(((tables[environment].get('total') or {}).get('gaps') or {}).get(operator))
                      for tables in members]
            context = latest.get('context') or {}
            items.append({
                'environment': environment, **_styles(latest, operator), 'reference': reference,
                'reference_label': _styles(latest, reference)['label'] if reference else None,
                'context': _clean_context(context, campaign=False), 'title': _group_label(context, levels, {'Campaign'}),
                'campaigns': campaigns, 'by_reliability': by_reliability,
                'parts': [{'label': name, 'values': [gap.get(operator, {}).get(name) for gap in gaps]} for name in names],
                'totals': totals,
            })
    return items


def _levers(scopes, levels: list[str], environment: str) -> list[dict[str, Any]]:
    """Per scope (its latest campaign) and compared operator: the KPIs where matching the reference wins most points."""
    items = []
    for members in _scope_groups(scopes, environment):
        table = members[-1][environment]
        reference = table.get('baseline_operator')
        context = table.get('context') or {}
        for operator in table.get('operators', []):
            if operator == reference:
                continue
            rows = []
            for row in _kpi_rows(table):
                gap = _number((row.get('gaps') or {}).get(operator))
                if gap is None or gap >= -0.005:
                    continue
                values = row.get('values') or {}
                rows.append({'kpi_code': row['kpi_code'], 'kpi': row.get('kpi'), 'category': row.get('category'),
                             'service': _service(row), 'kpi_type': row.get('kpi_type'), 'unit': row.get('unit'),
                             'value': _number((values.get(operator) or {}).get('value')),
                             'reference_value': _number((values.get(reference) or {}).get('value')),
                             'gap': gap, 'max_points': _number(row.get('max_points'))})
            if not rows:
                continue
            rows.sort(key=lambda item: item['gap'])
            items.append({
                'environment': environment, **_styles(table, operator), 'reference': reference,
                'reference_label': _styles(table, reference)['label'] if reference else None,
                'context': _clean_context(context), 'title': _group_label(context, levels, {'Campaign'}),
                'campaign': _display('Campaign', context.get('campaign')) if context.get('campaign') else None,
                'levers': rows[:MAX_LEVERS], 'total_behind': sum(item['gap'] for item in rows), 'count': len(rows),
            })
    return items


def loss_kind(row: dict[str, Any], formulas: dict[str, str]) -> str:
    """How a KPI loses its points: on failed tests (Reliable KPIs), on tests below its threshold (the other ratios) or
    as a quality shortfall (averages, medians, percentiles and packet loss)."""
    if str(row.get('kpi_type') or '').casefold() == 'reliable':
        return 'failed'
    formula = formulas.get(str(row.get('kpi_code'))) or ''
    if not formula or _AGGREGATE_FORMULA.fullmatch(formula) or 'totalpacketlost' in formula:
        return 'quality'
    return 'below_par'


def _losses(table: dict[str, Any], operator: str, formulas: dict[str, str]) -> tuple[dict[str, float], dict[str, list]]:
    parts = dict.fromkeys(LOSS_KINDS, 0.0)
    kpis: dict[str, list] = {kind: [] for kind in LOSS_KINDS}
    for row in _kpi_rows(table):
        maximum = _number(row.get('max_points')) or 0.0
        points = _number(((row.get('values') or {}).get(operator) or {}).get('points'))
        if maximum <= 0 or points is None:
            continue
        lost = max(0.0, maximum - points)
        kind = loss_kind(row, formulas)
        parts[kind] += lost
        if lost > 0:
            kpis[kind].append({'kpi': row.get('kpi'), 'service': _service(row), 'lost': lost})
    return parts, {kind: sorted(rows, key=lambda item: -item['lost'])[:3] for kind, rows in kpis.items()}


def _service_losses(table: dict[str, Any], operator: str, formulas: dict[str, str]) -> dict[str, dict[str, Any]]:
    """The points lost on Voice and on Data by kind, with the KPIs that lose most: every kind of Voice (``kpis``), the
    failed Data tests (``failed_kpis``) and the Data below the thresholds or short of quality (``below_kpis``)."""
    services: dict[str, dict[str, Any]] = {}
    for row in _kpi_rows(table):
        maximum = _number(row.get('max_points')) or 0.0
        points = _number(((row.get('values') or {}).get(operator) or {}).get('points'))
        if maximum <= 0 or points is None or maximum - points <= 0:
            continue
        lost, kind, service = maximum - points, loss_kind(row, formulas), _service(row)
        entry = services.setdefault(service, {**dict.fromkeys(LOSS_KINDS, 0.0), 'kpis': [], 'failed_kpis': [], 'below_kpis': []})
        entry[kind] += lost
        kpi = {'kpi': row.get('kpi'), 'lost': lost, 'kind': kind}
        entry['kpis'].append(kpi)
        entry['failed_kpis' if kind == 'failed' else 'below_kpis'].append(kpi)
    for entry in services.values():
        for key in ('kpis', 'failed_kpis', 'below_kpis'):
            entry[key] = sorted(entry[key], key=lambda item: -item['lost'])[:3]
    return services


def _points_at_stake(scopes, levels: list[str], environment: str, formulas: dict[str, str]) -> list[dict[str, Any]]:
    """Per scope (its latest campaign): the points each operator lost, on failed tests, on tests below the KPI
    thresholds and as a quality shortfall, in all environments and in each one."""
    items = []
    for members in _scope_groups(scopes, environment):
        latest = members[-1]
        table = latest[environment]
        names = ([name for name in latest if name != COMBINED] if environment == COMBINED else [])
        operators = []
        for operator in table.get('operators', []):
            parts, kpis = _losses(table, operator, formulas)
            total = (_number((((table.get('total') or {}).get('values') or {}).get(operator) or {}).get('points')))
            if total is None:
                continue
            by_environment = {name: _losses(latest[name], operator, formulas)[0] for name in names
                              if any((_number(row.get('max_points')) or 0) > 0 for row in _kpi_rows(latest[name]))}
            operators.append({**_styles(table, operator), 'points': total, 'lost': sum(parts.values()),
                              'parts': parts, 'environments': by_environment, 'kpis': kpis,
                              'services': _service_losses(table, operator, formulas)})
        if not operators:
            continue
        context = table.get('context') or {}
        items.append({
            'environment': environment, 'context': _clean_context(context),
            'title': _group_label(context, levels, {'Campaign'}),
            'campaign': _display('Campaign', context.get('campaign')) if context.get('campaign') else None,
            'maximum': _number((table.get('total') or {}).get('max_points')), 'operators': operators,
            'kinds': [{'key': kind, 'label': LOSS_KIND_LABELS[kind]} for kind in LOSS_KINDS],
        })
    return items


def _location_rankings(summaries: dict[tuple, dict[str, Any]], levels: list[str], environment: str,
                       cities: dict[str, Any]) -> list[dict[str, Any]]:
    """Every City, Cluster or Region of the latest campaign ranked by its share of the points, per operator: its Voice
    and Data shares, its change since the previous campaign, the points it lost, its GAP to the reference and, for
    cities and routes, the vendors of the cells that served their tests."""
    items = []
    for level in [level for level in LOCATION_LEVELS if level in levels]:
        field = _LEVEL_FIELDS[level]
        groups: dict[tuple, list[dict[str, Any]]] = {}
        for summary in summaries.values():
            context = summary['context']
            if context.get(field) in (None, ''):
                continue
            key = tuple((name, context.get(name)) for name in _CONTEXT_FIELDS if name not in (field, 'campaign'))
            groups.setdefault(key, []).append(summary)
        for members in groups.values():
            campaigns = sorted({member['context'].get('campaign') for member in members
                                if member['context'].get('campaign')}, key=campaign_sort_key)
            latest = campaigns[-1] if campaigns else None
            previous = campaigns[-2] if len(campaigns) > 1 else None
            current = [member for member in members if member['context'].get('campaign') == latest]
            if len(current) < 2:
                continue
            before = {member['context'][field]: member for member in members
                      if previous and member['context'].get('campaign') == previous}
            styles: dict[str, dict[str, Any]] = {}
            for member in current:
                for item in member['operators']:
                    styles.setdefault(item['operator'], item)
            reference = current[0].get('baseline_operator')
            for operator, style in styles.items():
                rows = []
                for member in current:
                    item = next((entry for entry in member['operators'] if entry['operator'] == operator), None)
                    if item is None:
                        continue
                    shares = _location_shares(member, item)
                    earlier = before.get(member['context'][field])
                    old = next((entry for entry in (earlier or {}).get('operators', []) if entry['operator'] == operator), None)
                    base = next((entry for entry in member['operators'] if entry['operator'] == reference), None)
                    base_shares = _location_shares(member, base) if base and operator != reference else None
                    name = _display(level, member['context'][field])
                    place = cities.get(name) or {} if level == 'City' else {}
                    vendors = place.get('vendor_tests') or {}
                    total_tests = sum(vendors.values())
                    rows.append({
                        'location': name, 'kind': place.get('kind', 'place') if level == 'City' else level.lower(),
                        'points': item['total'], 'maximum': member['maximum'], **shares,
                        'lost': member['maximum'] - item['total'], 'complete': item['complete'],
                        'delta': (shares['percent'] - _location_shares(earlier, old)['percent']) if old else None,
                        'reference_percent': base_shares['percent'] if base_shares else None,
                        'gap': shares['percent'] - base_shares['percent'] if base_shares else None,
                        'voice_gap': (shares['voice_percent'] - base_shares['voice_percent']
                                      if base_shares and None not in (shares['voice_percent'], base_shares['voice_percent']) else None),
                        'data_gap': (shares['data_percent'] - base_shares['data_percent']
                                     if base_shares and None not in (shares['data_percent'], base_shares['data_percent']) else None),
                        'vendors': [{'name': vendor, 'share': count / total_tests * 100}
                                    for vendor, count in sorted(vendors.items(), key=lambda pair: -pair[1])[:2]
                                    if total_tests and count / total_tests >= .1],
                    })
                if not rows:
                    continue
                rows.sort(key=lambda row: (-row['percent'], row['location']))
                context = current[0]['context']
                items.append({
                    'environment': environment, 'level': level, **{key: style[key] for key in ('operator', 'label', 'color')},
                    'is_reference': operator == reference, 'reference': reference,
                    'reference_label': (styles.get(reference) or {}).get('label') or reference,
                    'title': _group_label(context, levels, {level, 'Campaign'}),
                    'context': _clean_context({**context, field: None}),
                    'campaign': _display('Campaign', latest) if latest else None,
                    'previous_campaign': _display('Campaign', previous) if previous else None,
                    'rows': rows,
                })
    return items


def _location_shares(summary: dict[str, Any], item: dict[str, Any]) -> dict[str, float | None]:
    return {'percent': item['total'] / summary['maximum'] * 100 if summary['maximum'] else 0.0,
            'voice_percent': item['voice'] / summary['max_voice'] * 100 if summary['max_voice'] else None,
            'data_percent': item['data'] / summary['max_data'] * 100 if summary['max_data'] else None}


def _campaign_scope(score_tables: list[dict[str, Any]], configuration: dict[str, Any], result: dict[str, Any] | None,
                    environments: list[str]) -> list[dict[str, Any]]:
    """How the measurements ran: the campaigns and dates, the environments and their points, the cities and routes and
    the tests of each operator in each environment (the latest campaign)."""
    campaigns = sorted({table['context'].get('campaign') for table in score_tables if table['context'].get('campaign')},
                       key=campaign_sort_key)
    latest = campaigns[-1] if campaigns else None
    tests: dict[str, dict[str, dict[str, int]]] = {}
    counts = (result or {}).get('test_counts')
    if isinstance(counts, list):
        # The tests of each group of the calculation, per operator, CDR type and environment.
        for entry in counts:
            if latest and entry.get('campaign') != latest or not entry.get('environment'):
                continue
            target = tests.setdefault(str(entry.get('operator')), {}).setdefault(str(entry.get('kind')), {})
            target[str(entry['environment'])] = target.get(str(entry['environment']), 0) + int(entry.get('tests') or 0)
    else:
        # Results saved before: the samples of the most measured KPI of each CDR type.
        for table in score_tables:
            context = table['context']
            name = str(context.get('environment'))
            if name == COMBINED or (latest and context.get('campaign') != latest):
                continue
            for operator in table.get('operators', []):
                largest: dict[str, int] = {}
                for row in _kpi_rows(table):
                    kind = str(row.get('source_kind') or '').casefold() or 'data'
                    count = ((row.get('values') or {}).get(operator) or {}).get('sample_count') or 0
                    largest[kind] = max(largest.get(kind, 0), int(count))
                target = tests.setdefault(operator, {})
                for kind, count in largest.items():
                    if count:
                        target.setdefault(kind, {})[name] = target.get(kind, {}).get(name, 0) + count
    styles = operator_styles(score_tables)
    scope = configuration.get('scope', {}).get('environments', {})
    maxima: dict[str, float] = {}
    for metric in configuration.get('metrics', []):
        for name, context in (metric.get('contexts') or {}).items():
            maxima[name] = maxima.get(name, 0.0) + (_number(context.get('max_points')) or 0.0)
    places = (((result or {}).get('points_loss') or {}).get('areas') or {}).get('City') or {}
    item = {
        'campaigns': [_display('Campaign', campaign) for campaign in campaigns],
        'latest_campaign': _display('Campaign', latest) if latest else None,
        'window': (result or {}).get('test_window'),
        'environments': [{'name': name, 'label': str((scope.get(name) or {}).get('display_name') or name),
                          'max_points': maxima.get(name, 0.0)} for name in scope],
        'operators': [{'operator': operator, 'label': style.get('label') or operator, 'color': style.get('color')}
                      for operator, style in sorted(styles.items(), key=lambda pair: (pair[1].get('position', 99), pair[0]))],
        'tests': tests,
        'places': {'cities': sum(1 for entry in places.values() if entry.get('kind') != 'route'),
                   'routes': sum(1 for entry in places.values() if entry.get('kind') == 'route')} if places else None,
    }
    return [{**item, 'environment': environment} for environment in environments]


def _bearing_label(latitude: float, longitude: float, places: dict[str, Any]) -> str:
    """Where a point is, from the nearest city of the measurements: near Leeds, or 14 km north-east of Leeds."""
    from math import atan2, cos, degrees, radians, sqrt
    best = None
    for name, place in places.items():
        if place.get('kind') == 'route' or place.get('latitude') is None or name == 'Not specified':
            continue
        dy = (latitude - place['latitude']) * 111.2
        dx = (longitude - place['longitude']) * 111.2 * cos(radians(latitude))
        distance = sqrt(dx * dx + dy * dy)
        if best is None or distance < best[0]:
            best = (distance, name, dx, dy)
    if best is None:
        return f'{latitude:.2f}, {longitude:.2f}'
    distance, name, dx, dy = best
    if distance < 8:
        return f'near {name}'
    direction = _COMPASS[round((degrees(atan2(dx, dy)) % 360) / 45) % 8]
    return f'{distance:,.0f} km {direction} of {name}'


def _serving_views(maps: list[dict[str, Any]], result: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """The Points Lost of each operator per Vendor, Site Type, site and route stretch, from its points-lost maps: each
    with its share of the points lost and, for vendors and kinds of site, its share of the tests."""
    from src.modules.scoring_points_loss import NOT_SPECIFIED, OTHER, SITE, SITE_TYPE, STRETCH, VENDOR
    document = (result or {}).get('points_loss') or {}
    places = (document.get('areas') or {}).get('City') or {}
    keys = [key for key in (document.get('shares') or [{}])[0]
            if key not in {'environment', 'kpi_code', 'areas', 'weight', 'tests'}]
    # The tests of each series and environment (None: all of them) per Vendor and Site Type.
    tests: dict[tuple, dict[str, dict[str, int]]] = {}
    for entry in document.get('serving_tests') or []:
        identity = tuple(entry.get(key) for key in keys)
        environment = str(entry.get('environment') or '')
        for target in (tests.setdefault((identity, None), {}), tests.setdefault((identity, environment), {})):
            for field, counts in (entry.get('counts') or {}).items():
                into = target.setdefault(field, {})
                for name, count in counts.items():
                    into[name] = into.get(name, 0) + int(count)
    views: dict[str, list[dict[str, Any]]] = {'vendor_losses': [], 'site_type_losses': [], 'sites_to_review': [],
                                              'route_stretches': []}
    sites_by_series: dict[tuple, dict[str, dict[str, Any]]] = {}
    for item in maps:
        field = item['field']
        if field not in (VENDOR, SITE_TYPE, SITE, STRETCH):
            continue
        context = {**item['context'], 'operator': item['operator']}
        identity = tuple(context.get(key) if key != 'operator' else item['operator'] for key in keys)
        environment_key = None if item['environment'] == COMBINED else item['environment']
        base = {key: item[key] for key in ('environment', 'operator', 'label', 'color', 'is_reference', 'context', 'total')}
        if field in (VENDOR, SITE_TYPE):
            counts = (tests.get((identity, environment_key)) or {}).get(field) or {}
            counted = sum(counts.values())
            rows = []
            for area in item['areas']:
                name = area['name']
                rows.append({
                    'name': 'Not identified' if name == NOT_SPECIFIED else name, 'identified': name != NOT_SPECIFIED,
                    'points': area['points'], 'share': area['share'] * 100,
                    'tests_share': counts.get(name, 0) / counted * 100 if counted else None,
                    'environments': area.get('environments') or [],
                    'cities': [{'name': city, 'points': points} for city, points in sorted(
                        ((item.get('city_losses') or {}).get(name) or {}).items(), key=lambda pair: -pair[1])[:3]
                        if city != NOT_SPECIFIED],
                })
            views['vendor_losses' if field == VENDOR else 'site_type_losses'].append(
                {**base, 'rows': rows, 'has_tests': bool(counted)})
        elif field == SITE:
            failures = item.get('failures') or {}
            sites = {}
            for area in item['areas']:
                if area['name'] in (NOT_SPECIFIED, OTHER):
                    continue
                sites[area['name']] = {'key': area['name'], 'site': area.get('site') or area['name'],
                                       'network': area.get('network'), 'vendor': area.get('vendor'),
                                       'city': area.get('city'), 'region': area.get('region'), 'latitude': area.get('latitude'),
                                       'longitude': area.get('longitude'), 'points': area['points'],
                                       'failures': failures.get(area['name'])}
            series = tuple((key, value) for key, value in sorted(item['context'].items()) if key != 'campaign')
            sites_by_series.setdefault((item['operator'], item['environment'], series), {})[
                item['context'].get('campaign') or ''] = {'base': base, 'sites': sites,
                                                          'unidentified': sum(area['points'] for area in item['areas']
                                                                              if area['name'] == NOT_SPECIFIED)}
        else:
            routes: dict[str, list[dict[str, Any]]] = {}
            for area in item['areas']:
                if area['name'] in (NOT_SPECIFIED, OTHER) or area.get('latitude') is None:
                    continue
                route = area.get('route_name') or area['name'].split('\x1e')[0]
                routes.setdefault(route, []).append({
                    'label': _bearing_label(area['latitude'], area['longitude'], places), 'points': area['points'],
                    'latitude': area['latitude'], 'longitude': area['longitude'], 'vendor': area.get('vendor'),
                    'region': area.get('region')})
            ordered = sorted(routes.items(), key=lambda pair: -sum(row['points'] for row in pair[1]))[:MAX_STRETCH_ROUTES]
            if ordered:
                from src.modules.scoring_where_to_act import _landmarks
                stretch_routes = [{
                    'route': route, 'points': sum(row['points'] for row in stretches),
                    'path': (places.get(route) or {}).get('points') or [],
                    'stretches': sorted(stretches, key=lambda row: -row['points'])[:MAX_ROUTE_STRETCHES],
                    # [latitude, longitude, points, performance owner (Region)] of every stretch.
                    'all_stretches': [[row['latitude'], row['longitude'], round(row['points'], 3), row.get('region') or '']
                                      for row in stretches],
                } for route, stretches in ordered]
                # The measured cities around each route, to name its map.
                for stretch_route in stretch_routes:
                    stretch_route['landmarks'] = _landmarks(stretch_route, places)
                views['route_stretches'].append({**base, 'routes': stretch_routes})
    for (operator, environment, _series), by_campaign in sites_by_series.items():
        campaigns = sorted(by_campaign, key=campaign_sort_key)
        latest = by_campaign[campaigns[-1]]
        earlier = campaigns[:-1][-2:]
        rows = []
        for site in sorted(latest['sites'].values(), key=lambda row: -row['points'])[:MAX_SITES]:
            history = [{'campaign': _display('Campaign', campaign) if campaign else '',
                        'points': (by_campaign[campaign]['sites'].get(site['key']) or {}).get('points'),
                        'failures': (by_campaign[campaign]['sites'].get(site['key']) or {}).get('failures')}
                       for campaign in earlier]
            recurring = any((entry['points'] or 0) > 0 for entry in history)
            heavy = site['points'] >= SITE_PRIORITY_POINTS
            rows.append({**site, 'history': history,
                         'priority': 'High' if heavy and recurring else 'Medium' if heavy or recurring else 'Low'})
        if rows:
            views['sites_to_review'].append({
                **latest['base'], 'campaign': _display('Campaign', campaigns[-1]) if campaigns[-1] else None,
                'earlier_campaigns': [_display('Campaign', campaign) for campaign in earlier if campaign],
                'rows': rows, 'listed_points': sum(row['points'] for row in rows),
                'unidentified': latest['unidentified'], 'priority_points': SITE_PRIORITY_POINTS,
            })
    return views
