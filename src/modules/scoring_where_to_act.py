"""Where to act, from the Points Lost of each operator: the views the Summary of Scoring & GAP Analysis opens with (Where
to act and its performance owners, after how the measurements ran) and adds after its biggest levers (the places ranked
and the route focus), as benchmark reports present them.

- **Where to act**: the themes that hold the points lost (voice calls, failed and below-par data tests), then the
  sites to review and the route stretches, each with what to do (the KPIs and stretches with the points of the scoring
  they lose, which the page and the slides highlight) and the view of the results to open.
- **Where to act, by performance owner**: a card per performance owner (the Regions of the CDRs, such as Vendor A,
  Vendor B, VMO2 North and VMO2 South) with its points lost, what drives them, its biggest areas, its high priority
  sites and where its points are (Cities, Towns, Roads and railways).
- **Places ranked**: the Cities, Towns, Roads and Railways of the latest campaign ranked by their share of the points,
  with their performance owners, their change, their Voice and Data shares and the points lost.
- **Route focus**: the route that loses most, its stretches on the map with their owner, the points of each owner and
  the five stretches with the most points.

The points lost of a place, owner or stretch are the points of the scoring it loses against the maximum (see scoring_points_loss). A calculation split
by City, Cluster or Region scores each place on the whole maximum: its points count by its share of the tests, so the
points of every place add up to national points (estimates).
"""
from __future__ import annotations

from typing import Any, Callable

COMBINED = 'Combined'
# The colours of the share of the points of a place: green from 85%, yellow from 75%, red under it.
GOOD_PERCENT, FAIR_PERCENT = 85.0, 75.0
SETTING_TITLES = {'Cities': 'Cities ranked', 'Towns': 'Towns ranked', 'Roads': 'Roads ranked', 'Railways': 'Railways ranked'}
SETTING_NOUNS = {'Cities': ('city', 'cities'), 'Towns': ('town', 'towns'), 'Roads': ('road', 'roads'),
                 'Railways': ('railway route', 'railway routes')}
# Where the points of an owner are: the settings of the places, the roads and railways together.
OWNER_SETTINGS = (('Cities', ('Cities',)), ('Towns', ('Towns',)), ('Roads and railways', ('Roads', 'Railways')))
MAX_OWNERS = 6
# The order in which the performance owners take the colours of the categories of the theme, on the page and in the
# exports: these owners of the UK measurements first, in this order (Vendor B takes the colour before that of Vendor A),
# the others after them by name.
OWNER_COLOUR_ORDER = ('VMO2 North', 'VMO2 South', 'Vendor B', 'Vendor A')
# The location fields of a scoring context: the views add up the places of a calculation split by them.
LOCATION_FIELDS = ('city', 'cluster', 'region')
MAX_OWNER_SHARES = 3
TOP_STRETCHES = 5
NOT_SPECIFIED = 'Not specified'
NOT_IDENTIFIED = 'Start cell not logged'


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _join(items: list[str]) -> str:
    items = [item for item in items if item]
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1] if items else ''


def _possessive(name: str) -> str:
    return f"{name}'" if name.endswith('s') else f"{name}'s"


def owner_order(names: Any) -> list[str]:
    """The performance owners in the order in which they take the colours of the theme (see OWNER_COLOUR_ORDER)."""
    known = {name: index for index, name in enumerate(OWNER_COLOUR_ORDER)}
    return sorted({str(name) for name in names if name}, key=lambda name: (known.get(name, len(known)), name))


def place_setting(place: dict[str, Any], kind: str) -> str:
    """Cities, Towns, Roads or Railways: that of most of the tests of the place, else a place is a City and a route a
    Road (results calculated before the settings were kept)."""
    setting = str(place.get('setting') or '')
    if setting:
        return setting
    return 'Cities' if kind == 'place' else 'Roads'


def owner_shares(place: dict[str, Any]) -> list[dict[str, Any]]:
    """The performance owners of the tests of a place (its Regions), the most first, those over 10%."""
    counts = {name: count for name, count in (place.get('region_tests') or {}).items() if name and name != NOT_SPECIFIED}
    total = sum(counts.values())
    return [{'name': name, 'share': count / total * 100}
            for name, count in sorted(counts.items(), key=lambda pair: -pair[1])[:MAX_OWNER_SHARES]
            if total and count / total >= .1]


def place_rankings(rankings: list[dict[str, Any]], places: dict[str, Any], weight: Weights,
                   environment: str = COMBINED) -> list[dict[str, Any]]:
    """The places of each operator (the City rankings of all environments) as Cities, Towns, Roads and Railways ranked."""
    items = []
    for item in rankings:
        if item.get('level') != 'City' or item.get('environment') != environment:
            continue
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in item['rows']:
            place = places.get(row['location']) or {}
            setting = place_setting(place, row.get('kind', 'place'))
            if setting not in SETTING_TITLES:
                continue
            modes = place.get('modes') or []
            groups.setdefault(setting, []).append({
                'location': row['location'], 'note': '(drive + walk)' if {'Drive', 'Walk'} <= set(modes) else '',
                'owners': owner_shares(place), 'percent': row['percent'], 'delta': row.get('delta'),
                'voice_percent': row.get('voice_percent'), 'data_percent': row.get('data_percent'),
                # The points it loses on the whole maximum, by its share of the tests.
                'lost': max(0.0, _number(row.get('lost'))) * weight({'city': row['location']}),
            })
        sections = []
        for setting in SETTING_TITLES:
            rows = sorted(groups.get(setting) or [], key=lambda row: (-row['percent'], row['location']))
            if not rows:
                continue
            singular, plural = SETTING_NOUNS[setting]
            under = [row for row in rows if row['percent'] < FAIR_PERCENT]
            most = max(rows, key=lambda row: row['lost'])
            count = f"{len(rows)} {plural if len(rows) > 1 else singular}"
            headline = (f"{most['location']} loses the most points ({most['lost']:.1f}); none of the {count} is under 75%"
                        if not under else f"Under 75% on {len(under)} of {count}; {most['location']} loses the most points")
            sections.append({'setting': setting, 'title': SETTING_TITLES[setting], 'headline': headline, 'rows': rows,
                             'peak_lost': max(row['lost'] for row in rows)})
        if sections:
            items.append({**{key: item.get(key) for key in ('environment', 'operator', 'label', 'color', 'is_reference',
                                                             'campaign', 'previous_campaign', 'context', 'title')},
                          'groups': sections})
    return items


class Weights:
    """The share of the tests of each place of a calculation (``weight(context)``: 1 without a place), so the points it
    loses count as national points."""

    def __init__(self, result: dict[str, Any] | None) -> None:
        self.areas = (((result or {}).get('points_loss') or {}).get('areas') or {})
        self.totals = {field: sum(_number(area.get('tests')) for area in (self.areas.get(field) or {}).values())
                       for field in ('City', 'Cluster', 'Region')}

    def __call__(self, context: dict[str, Any] | None) -> float:
        for key in LOCATION_FIELDS:
            value = (context or {}).get(key)
            field = key.title()
            if value not in (None, '') and self.totals.get(field):
                return _number(((self.areas.get(field) or {}).get(str(value)) or {}).get('tests')) / self.totals[field]
        return 1.0


def _scope(context: dict[str, Any] | None) -> tuple:
    """The context of an item without its place and campaign: the places of a calculation split by City, Cluster or
    Region add up."""
    return tuple(sorted((key, value) for key, value in (context or {}).items() if key not in (*LOCATION_FIELDS, 'campaign')))


def _merged(items: list[dict[str, Any]], weight: Weights) -> dict[str, Any]:
    """One Region map of the places of ``items``: the points of each owner and of each owner in each City or route."""
    first = items[0]
    areas: dict[str, float] = {}
    city_losses: dict[str, dict[str, float]] = {}
    for item in items:
        share = weight(item.get('context'))
        for area in item['areas']:
            areas[area['name']] = areas.get(area['name'], 0.0) + area['points'] * share
        for owner, cities in (item.get('city_losses') or {}).items():
            into = city_losses.setdefault(owner, {})
            for city, points in cities.items():
                into[city] = into.get(city, 0.0) + points * share
    total = sum(areas.values())
    return {**{key: first.get(key) for key in ('environment', 'operator', 'label', 'color', 'is_reference')},
            'context': {key: value for key, value in (first.get('context') or {}).items() if key not in LOCATION_FIELDS},
            'areas': [{'name': name, 'points': points, 'share': points / total if total else 0.0}
                      for name, points in sorted(areas.items(), key=lambda pair: -pair[1])],
            'city_losses': city_losses, 'total': total}


def _region_maps(maps: list[dict[str, Any]], weight: Weights) -> dict[tuple, dict[str, dict[str, Any]]]:
    """The Region maps of each operator, by environment, its places added up."""
    grouped: dict[tuple, dict[str, list[dict[str, Any]]]] = {}
    for item in maps:
        if item.get('field') == 'Region':
            grouped.setdefault((item['operator'], _scope(item.get('context'))), {}).setdefault(item['environment'], []).append(item)
    return {key: {environment: _merged(items, weight) for environment, items in by_environment.items()}
            for key, by_environment in grouped.items()}


def owner_cards(maps: list[dict[str, Any]], places: dict[str, Any], sites: list[dict[str, Any]], weight: Weights,
                environment_labels: dict[str, str] | None = None, environment: str = COMBINED) -> list[dict[str, Any]]:
    """A card per performance owner of each operator: its points lost, where they are and what drives them."""
    environment_labels = environment_labels or {}
    items = []
    high_sites: dict[str, list[dict[str, Any]]] = {}
    for item in sites:
        if item.get('environment') != environment:
            continue
        high_sites.setdefault(item['operator'], []).extend(row for row in item['rows'] if row.get('priority') == 'High')
    for (operator, _context), by_environment in _region_maps(maps, weight).items():
        combined = by_environment.get(environment)
        if combined is None:
            continue
        city_losses = combined.get('city_losses') or {}
        cards = []
        for area in combined['areas']:
            name = area['name']
            if name in (NOT_SPECIFIED, '') or area['points'] <= 0:
                continue
            cities = city_losses.get(name) or {}
            settings = dict.fromkeys(label for label, _settings in OWNER_SETTINGS)
            for city, points in cities.items():
                place = places.get(city) or {}
                setting = place_setting(place, place.get('kind', 'place'))
                label = next((label for label, members in OWNER_SETTINGS if setting in members), None)
                if label:
                    settings[label] = (settings[label] or 0.0) + points
            # The points of the owner in each environment, the most first.
            environments = []
            for key, map_item in by_environment.items():
                points = next((entry['points'] for entry in map_item['areas'] if entry['name'] == name), 0.0)
                if environment == COMBINED and key != COMBINED and points >= .05:
                    environments.append((environment_labels.get(key, key), points))
            environments.sort(key=lambda pair: -pair[1])
            top_setting = max(((label, points) for label, points in settings.items() if points), key=lambda pair: pair[1],
                              default=None)
            main = ''
            if top_setting:
                main = f"{top_setting[0].lower()} {top_setting[1]:.1f}"
                if environments:
                    main += f" ({', '.join(f'{label} {points:.1f}' for label, points in environments[:3])})"
            areas = [{'name': city, 'points': points,
                      'setting': place_setting(places.get(city) or {}, (places.get(city) or {}).get('kind', 'place'))}
                     for city, points in sorted(cities.items(), key=lambda pair: -pair[1])[:2] if city != NOT_SPECIFIED]
            owned = [row for row in high_sites.get(operator, []) if row.get('region') == name]
            # Results calculated before the points of each owner were kept per City or route have none: None, so the
            # card asks for the Saved Filter recalculated rather than showing zeros.
            cards.append({'owner': name, 'points': area['points'], 'share': area['share'] * 100,
                          'settings': {label: round(points or 0.0, 3) for label, points in settings.items()} if city_losses else None,
                          'main': main, 'areas': areas,
                          'high_sites': [{'site': row.get('site'), 'city': row.get('city')} for row in owned]})
        if not cards:
            continue
        cards.sort(key=lambda card: -card['points'])
        unidentified = next((area['points'] for area in combined['areas'] if area['name'] == NOT_SPECIFIED), 0.0)
        items.append({key: combined.get(key) for key in ('environment', 'operator', 'label', 'color', 'is_reference', 'context')}
                     | {'cards': cards[:MAX_OWNERS], 'total': combined['total'], 'unidentified': unidentified,
                        'campaign': (combined.get('context') or {}).get('campaign')})
    return items


def _kpi_parts(kpis: list[dict[str, Any]], count: int = 2) -> list[tuple[str, bool]]:
    """The KPIs that lose most, each with the points of the scoring it loses: CALL SUCCESS RATIO [%] (18.2 points) and
    POLQA < 1.6 [%] (14.1 points), as (text, whether it is points) parts."""
    rows = [row for row in kpis[:count] if row.get('kpi')]
    parts: list[tuple[str, bool]] = []
    for index, row in enumerate(rows):
        if index:
            parts.append((' and ' if index == len(rows) - 1 else ', ', False))
        parts += [(f"{row['kpi']} (", False), (f"{row['lost']:.1f} points", True), (')', False)]
    return parts


def _deep_dive(*links: tuple[str, str]) -> dict[str, Any]:
    """The views of Points Lost that show a theme in detail: their names and the sections of the page they open
    (points-kpi, sites or stretches)."""
    return {'deep_dive': 'Points Lost: ' + '; '.join(label for label, _section in links),
            'deep_dive_links': [{'label': label, 'section': section} for label, section in links]}


def _action(parts: list[tuple[str, bool]]) -> dict[str, Any]:
    """What to do as its text and its parts, those with points of the scoring marked (the page and the slides
    highlight them)."""
    parts = [(text, points) for text, points in parts if text]
    return {'action': ''.join(text for text, _points in parts),
            'action_parts': [{'text': text, 'points': points} for text, points in parts]}


def _losses_by_scope(result: dict[str, Any] | None, formulas: dict[str, str], weight: Weights,
                     environment: str = COMBINED, combined_weight: Callable[[Any, Any, Any], float] | None = None,
                     ) -> dict[tuple, dict[str, dict[str, Any]]]:
    """The points each operator loses in the latest campaign on Voice and Data, by kind (see scoring_insights.loss_kind),
    from the KPI rows of every environment measured, its places added up by their share of the tests: per scope, per
    operator, ``{service: {kind: points, kpis, failed_kpis, below_kpis}}`` (failed: not completed or below the minimum of
    the Reliable KPIs, see scoring_insights.FAILED_KINDS). All environments count in the points of All
    Environments: ``combined_weight(campaign, KPI code, environment)`` gives what one point of an environment is worth
    there."""
    from src.modules.scoring_insights import FAILED_KINDS, LOSS_KINDS, campaign_sort_key, loss_kind

    rows = [row for row in (result or {}).get('scoring') or [] if row.get('kpi_code')]
    campaigns = sorted({row.get('campaign') for row in rows if row.get('campaign')}, key=campaign_sort_key)
    latest = campaigns[-1] if campaigns else None
    levels = [str(level).lower() for level in (result or {}).get('aggregation_levels') or []]
    fields = [field for field in levels if field not in (*LOCATION_FIELDS, 'campaign', 'operator')]
    scopes: dict[tuple, dict[str, dict[str, Any]]] = {}
    kpis: dict[tuple, dict[str, float]] = {}
    for row in rows:
        if latest is not None and row.get('campaign') != latest:
            continue
        if environment != COMBINED and row.get('environment') != environment:
            continue
        maximum, points = row.get('max_points'), row.get('weighted_points')
        if not isinstance(maximum, (int, float)) or not isinstance(points, (int, float)) or maximum - points <= 0:
            continue
        lost = (maximum - points) * weight({field: row.get(field) for field in LOCATION_FIELDS})
        if environment == COMBINED and combined_weight:
            lost *= combined_weight(row.get('campaign'), row.get('kpi_code'), row.get('environment'))
        scope = tuple(sorted((field, row.get(field)) for field in fields))
        service = 'Data' if str(row.get('dataset_type') or row.get('source_kind') or '').casefold() == 'data' else 'Voice'
        kind = loss_kind(row, formulas)
        entry = scopes.setdefault(scope, {}).setdefault(str(row.get('operator')), {}).setdefault(service, dict.fromkeys(LOSS_KINDS, 0.0))
        entry[kind] += lost
        for key in ('kpis', 'failed_kpis' if kind in FAILED_KINDS else 'below_kpis'):
            totals = kpis.setdefault((scope, str(row.get('operator')), service, key), {})
            totals[str(row.get('kpi'))] = totals.get(str(row.get('kpi')), 0.0) + lost
    for (scope, operator, service, key), totals in kpis.items():
        scopes[scope][operator][service][key] = [{'kpi': kpi, 'lost': lost}
                                                 for kpi, lost in sorted(totals.items(), key=lambda pair: -pair[1])[:3]]
    return scopes


def _scaled_route(route: dict[str, Any], share: float) -> dict[str, Any]:
    if share == 1.0:
        return route
    return {**route, 'points': route['points'] * share,
            'stretches': [{**row, 'points': row['points'] * share} for row in route['stretches']],
            'all_stretches': [[*entry[:2], round(entry[2] * share, 3), *entry[3:]] for entry in route['all_stretches']]}


def _routes(stretches: list[dict[str, Any]], weight: Weights, environment: str = COMBINED) -> dict[tuple, dict[str, Any]]:
    """The routes of each operator and scope, the one that loses most first."""
    grouped: dict[tuple, dict[str, Any]] = {}
    for item in stretches:
        if item.get('environment') != environment:
            continue
        key = (item['operator'], _scope(item.get('context')))
        share = weight(item.get('context'))
        entry = grouped.setdefault(key, {**item, 'routes': [], 'total': 0.0,
                                         'context': {field: value for field, value in (item.get('context') or {}).items()
                                                     if field not in LOCATION_FIELDS}})
        entry['routes'].extend(_scaled_route(route, share) for route in item['routes'])
        entry['total'] += _number(item.get('total')) * share
    for entry in grouped.values():
        entry['routes'].sort(key=lambda route: -route['points'])
    return grouped


def act_plans(result: dict[str, Any] | None, formulas: dict[str, str], styles: dict[str, dict[str, Any]],
              sites: list[dict[str, Any]], stretches: list[dict[str, Any]], weight: Weights,
              environment: str = COMBINED, combined_weight: Callable[[Any, Any, Any], float] | None = None,
              ) -> list[dict[str, Any]]:
    """The themes that hold the points lost of each operator, with what to do and where to look further."""
    from src.modules.scoring_insights import FAILED_KINDS, LOSS_KINDS, campaign_sort_key

    items = []
    sites_of: dict[str, list[dict[str, Any]]] = {}
    for item in sites:
        if item.get('environment') == environment:
            sites_of.setdefault(item['operator'], []).extend(item['rows'])
    routes_of = _routes(stretches, weight, environment)
    campaigns = sorted({row.get('campaign') for row in (result or {}).get('scoring') or [] if row.get('campaign')},
                       key=campaign_sort_key)
    for scope, by_operator in _losses_by_scope(result, formulas, weight, environment, combined_weight).items():
        context = {**dict(scope), **({'campaign': campaigns[-1]} if campaigns else {})}
        stake = {'context': context, 'campaign': campaigns[-1] if campaigns else None, 'title': ''}
        for name, services in by_operator.items():
            style = styles.get(name) or {}
            operator = {'operator': name, 'label': style.get('label') or name, 'color': style.get('color'),
                        'is_reference': style.get('is_reference'),
                        'lost': sum(sum(_number(values.get(kind)) for kind in LOSS_KINDS)
                                    for values in services.values())}
            voice, data = services.get('Voice') or {}, services.get('Data') or {}
            rows = []
            voice_points = sum(_number(voice.get(kind)) for kind in LOSS_KINDS)
            if voice_points > 0:
                failed = sum(_number(voice.get(kind)) for kind in FAILED_KINDS)
                kpis = voice.get('kpis') or []
                parts = ([('Cut voice failures: failed calls cost ', False), (f"{failed:.1f} of the {voice_points:.1f} points", True)]
                         if failed >= voice_points / 2 else
                         [('Lift the voice quality: ', False), (f"{voice_points - failed:.1f} of the {voice_points:.1f} points", True)])
                parts += [('; first ', False), *_kpi_parts(kpis), ('.', False)] if kpis else [('.', False)]
                rows.append({'theme': 'Voice calls', 'points': voice_points, **_action(parts),
                             **_deep_dive(('Points lost per KPI (Voice)', 'points-kpi'))})
            failed_data = sum(_number(data.get(kind)) for kind in FAILED_KINDS)
            if failed_data > 0:
                kpis = data.get('failed_kpis') or []
                rows.append({'theme': 'Failed data tests', 'points': failed_data,
                             **_action([('Bring down the data failures: ', False),
                                        *(_kpi_parts(kpis) or [('every failed test', False)]), ('.', False)]),
                             **_deep_dive(('Points lost per KPI (Data)', 'points-kpi'), ('Sites to review', 'sites'))})
            below_data = _number(data.get('below_par')) + _number(data.get('quality'))
            if below_data > 0:
                kpis = data.get('below_kpis') or []
                rows.append({'theme': 'Below-par data tests', 'points': below_data,
                             **_action([('Lift the slowest data tests: ', False),
                                        *(_kpi_parts(kpis) or [('the KPIs below their threshold', False)]), ('.', False)]),
                             **_deep_dive(('Points lost per KPI (Data)', 'points-kpi'))})
            rows.sort(key=lambda row: -row['points'])
            review = sites_of.get(operator['operator']) or []
            if review:
                first = sorted(review, key=lambda row: (['High', 'Medium', 'Low'].index(row['priority']), -row['points']))[0]
                place = f" ({first['city']})" if first.get('city') else ''
                rows.append({'theme': 'Sites to review', 'points': None, 'within': True,
                             **_action([(f"Review {len(review)} sites, {first['site']}{place} first ({first['priority']} priority).", False)]),
                             **_deep_dive(('Sites to review', 'sites'))})
            routes = routes_of.get((operator['operator'], _scope(stake.get('context'))), {}).get('routes') or []
            if routes:
                route = routes[0]
                stretch = route['stretches'][0] if route['stretches'] else None
                parts = [(f"Check {route['route']}: ", False), (f"{route['points']:.1f} points", True)]
                parts += ([(f", {stretch['label']} first (", False), (f"{stretch['points']:.1f} points", True), (').', False)]
                          if stretch else [('.', False)])
                rows.append({'theme': 'Route stretches', 'points': None, 'within': True, **_action(parts),
                             **_deep_dive(('Route stretches', 'stretches'))})
            if not rows:
                continue
            ranked = [row['theme'].lower() for row in rows if row.get('points')]
            headline = (f"{ranked[0][:1].upper()}{ranked[0][1:]} first" + (f", then {_join(ranked[1:])}" if len(ranked) > 1 else '')
                        if ranked else 'Where the points go')
            if any(row['theme'] == 'Sites to review' for row in rows):
                headline += '; then the sites to review, High priority first'
            items.append({'environment': environment, 'operator': operator['operator'], 'label': operator.get('label'),
                          'color': operator.get('color'), 'is_reference': operator.get('is_reference'),
                          'context': stake.get('context'), 'campaign': stake.get('campaign'), 'title': stake.get('title'),
                          'headline': headline, 'lost': operator.get('lost'), 'rows': rows})
    return items


MAX_LANDMARKS = 8


def _landmarks(route: dict[str, Any], places: dict[str, Any]) -> list[dict[str, Any]]:
    """The measured cities around a route, to name the map: those within half a degree of it, the most tested first."""
    points = [*(route.get('path') or []), *([entry[0], entry[1]] for entry in route.get('all_stretches') or [])]
    if not points:
        return []
    south, north = min(point[0] for point in points) - .5, max(point[0] for point in points) + .5
    west, east = min(point[1] for point in points) - .8, max(point[1] for point in points) + .8
    nearby = [(name, place) for name, place in places.items()
              if place.get('kind') == 'place' and isinstance(place.get('latitude'), (int, float))
              and south <= place['latitude'] <= north and west <= place['longitude'] <= east]
    nearby.sort(key=lambda pair: -_number(pair[1].get('tests')))
    return [{'name': name, 'latitude': place['latitude'], 'longitude': place['longitude']} for name, place in nearby[:MAX_LANDMARKS]]


def route_focus(stretches: list[dict[str, Any]], maps: list[dict[str, Any]], places: dict[str, Any],
                weight: Weights, environment: str = COMBINED) -> list[dict[str, Any]]:
    """The routes of each operator with their stretches and owners: the points of each owner, the five stretches with
    the most points and what to review."""
    regions = {}
    for (operator, _context), by_environment in _region_maps(maps, weight).items():
        combined = by_environment.get(environment)
        if combined is not None:
            regions[operator] = combined.get('city_losses') or {}
    items = []
    for item in _routes(stretches, weight, environment).values():
        routes = []
        for route in item['routes']:
            place = places.get(route['route']) or {}
            tests = {name: count for name, count in (place.get('region_tests') or {}).items() if name and name != NOT_SPECIFIED}
            counted = sum(tests.values())
            losses = {owner: cities.get(route['route'], 0.0) for owner, cities in regions.get(item['operator'], {}).items()}
            owners = [{'name': name, 'points': points, 'tests_share': tests.get(name, 0) / counted * 100 if counted else None}
                      for name, points in sorted(losses.items(), key=lambda pair: -pair[1]) if points > 0]
            identified = sum(owner['points'] for owner in owners)
            if route['points'] - identified > .05:
                owners.append({'name': NOT_IDENTIFIED, 'points': route['points'] - identified, 'tests_share': None, 'unidentified': True})
            top = route['stretches'][:TOP_STRETCHES]
            held = sum(row['points'] for row in top)
            top_owners = list(dict.fromkeys(row.get('region') for row in top if row.get('region')))
            headline = (f"Points spread along the route: the {len(top)} stretches with the most hold {held:.1f} of the "
                        f"{route['points']:.1f}" + (f", all {top_owners[0]}" if len(top_owners) == 1 and all(row.get('region') for row in top) else ''))
            leader = next((owner['name'] for owner in owners if not owner.get('unidentified')), '')
            others = [owner['name'] for owner in owners[1:] if not owner.get('unidentified')]
            review = (f"{_possessive(leader)} start cells along the route, the {len(top)} stretches first"
                      + (f", with {_join(others)} for their parts." if others else '.')) if leader else ''
            routes.append({**route, 'setting': place_setting(place, place.get('kind', 'route')), 'owners': owners,
                           'top': top, 'headline': headline, 'review': review, 'landmarks': _landmarks(route, places)})
        if routes:
            items.append({key: item.get(key) for key in ('environment', 'operator', 'label', 'color', 'is_reference', 'context',
                                                          'total')} | {'routes': routes})
    return items


def build_where_to_act(insights: dict[str, Any], maps: list[dict[str, Any]], result: dict[str, Any] | None,
                       environment_labels: dict[str, str] | None = None, formulas: dict[str, str] | None = None,
                       styles: dict[str, dict[str, Any]] | None = None, *,
                       combined_weight: Callable[[Any, Any, Any], float] | None = None) -> dict[str, list[dict[str, Any]]]:
    """The views of where to act of every operator (see the module docstring), of the latest campaign; with
    ``combined_weight`` (see _losses_by_scope) All Environments counts in its own points."""
    from src.modules.scoring_summary_slides import latest_campaign_items

    places = ((((result or {}).get('points_loss') or {}).get('areas') or {}).get('City') or {})
    weight = Weights(result)
    regions = latest_campaign_items([item for item in maps if item.get('field') == 'Region'])
    stretches = latest_campaign_items(insights.get('route_stretches') or [])
    sites = insights.get('sites_to_review') or []
    # All environments together and each one, as the other insights of the Summary.
    environments = list(dict.fromkeys([COMBINED, *(str(row.get('environment')) for row in (result or {}).get('scoring') or []
                                                   if row.get('environment'))]))
    views: dict[str, list[Any]] = {'act_plans': [], 'owner_cards': [], 'place_rankings': [], 'route_focus': []}
    for environment in environments:
        views['act_plans'].extend(act_plans(result, formulas or {}, styles or {}, sites, stretches, weight, environment,
                                            combined_weight))
        views['owner_cards'].extend(owner_cards(regions, places, sites, weight, environment_labels, environment))
        views['place_rankings'].extend(place_rankings(insights.get('location_rankings') or [], places, weight, environment))
        views['route_focus'].extend(route_focus(stretches, regions, places, weight, environment))
    # The owners of every view in the order of their colours, shared by the page and the exports.
    views['owner_order'] = owner_order(
        [card['owner'] for item in views['owner_cards'] for card in item['cards']]
        + [owner['name'] for item in views['place_rankings'] for group in item['groups'] for row in group['rows'] for owner in row['owners']]
        + [owner['name'] for item in views['route_focus'] for route in item['routes'] for owner in route['owners'] if not owner.get('unidentified')])
    return views
