"""NNS Break-down: the scoring of each city and of the connecting roads, campaign by campaign, with the NNS and eMOCN
sites that serve them and the NNS sites planned by the Master Grid, and the scoring of the latest campaign by the kind
of site that served each test (ticket #195).

It is an optional part of a Scoring calculation, with a configuration of its own (in ``area_summary['nns_breakdown']``,
only when it is switched on, so the selections saved before keep their identity):

* ``campaigns``: the campaigns it scores, whatever the Campaign filter of the job (Latest 4 campaigns by default; an
  automatic choice stands for its campaigns when it is calculated);
* ``regions``: the Regions it covers (every Region without any);
* ``roads``: the connecting roads grouped by Region (``region``: a row for the Roads and one for the Highway of each
  Region) or each road on its own (``each``).

Each NR Mode of the job is scored apart (NSA vs SA: NSA, then SA), with the job's methodology (By campaign: each
campaign with its own) and its filters but Region, Cluster, City and Campaign.

A test is in a **city** when its ``G_Level_2`` is City (its name is ``G_Level_4``, its size ``G_Level_3``: Big, Medium
or Small Cities) and on a **connecting road** otherwise (``G_Level_3``: Roads or Highway). The **scenario** of a test is
the kind of site of the cell that served it (``Serving_eMOCN_Scenario`` of the Network Inventory): an NNS site with the
capacity the Master Grid gives it (its High/Med/Low config), or its eMOCN scenario (S0, S1, S1_CWP…).

Each **city** belongs to one Region: the one that holds most of its tests over the campaigns of the break-down (the
Region of a test is where it was measured, and the tests of a city near a Region border, or with a wrong position, would
otherwise split it). The connecting roads keep the Region of each test.

In each area and campaign, the **GAP to #1** of an operator is its points minus those of the operator with the most
points there, and its **weighted GAPs** are that GAP times its tests in the area over its tests in all the areas of the
Region, or of every chosen Region: summed, they give the GAP of the whole Region or of all the chosen Regions.

The scoring engine splits by Region, Cluster and City only: the calculation gives those columns of a copy of the rows
the area, the size and the scenario of each test, and names them back in the result.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

import pandas as pd

from src.modules.cdr.column_names import campaign_sort_key, resolve_column_name

KEY = 'nns_breakdown'
LABEL = 'NNS Break-down'
DEFAULT_CAMPAIGNS = ('@latest-4-campaigns',)
ROAD_GROUPINGS = ('region', 'each')
WARNING_PREFIX = 'NNS Break-down:'
# Raise when the calculation changes, so the results saved before are calculated again.
VERSION = 5
CITY_KIND = 'City'
ROAD_KIND = 'Road'
NO_SCENARIO = 'No eMOCN scenario'
NNS_SCENARIO = 'NNS'
CAPACITIES = ('High', 'Medium', 'Low')
UNKNOWN_CAPACITY = 'Not in the Master Grid'
# The yearly growth (%) of the reference operator in the projection, unless the request gives another one.
DEFAULT_REFERENCE_GROWTH = 0.5
# The fewest tests served by NNS sites whose points the projection trusts (fewer leave the projection of the area empty).
MIN_NNS_TESTS = 30
FIELDS = ('G_Level_2', 'G_Level_3', 'G_Level_4', 'Serving_eMOCN_Scenario', 'Serving_Host_Network', 'Serving_Site_ID')
_REGION, _AREA, _SCENARIO = 'Region', 'City', 'Cluster'


def nns_label(capacity: str) -> str:
    return f'NNS – {capacity} capacity' if capacity in CAPACITIES else f'NNS – {UNKNOWN_CAPACITY}'


SCENARIO_ORDER = (*(nns_label(capacity) for capacity in CAPACITIES), nns_label(''))


def normalize_request(value: Any) -> dict[str, Any] | None:
    """The configuration of an NNS Break-down switched on, or None (off)."""
    if not isinstance(value, dict) or value.get('enabled') is False:
        return None
    from src.modules.scoring.scoring_area_summary import normalize_trend_campaigns

    campaigns = normalize_trend_campaigns(value.get('campaigns')) or list(DEFAULT_CAMPAIGNS)
    regions: dict[str, str] = {}
    for region in value.get('regions') or []:
        text = str(region or '').strip()[:200]
        if text:
            regions.setdefault(text.casefold(), text)
    roads = str(value.get('roads') or '').strip().casefold()
    try:
        growth = float(value.get('reference_growth', DEFAULT_REFERENCE_GROWTH))
    except (TypeError, ValueError):
        growth = DEFAULT_REFERENCE_GROWTH
    growth = growth if growth == growth and -50 <= growth <= 50 else DEFAULT_REFERENCE_GROWTH
    request = {'campaigns': campaigns, 'regions': sorted(regions.values(), key=str.casefold),
               'roads': roads if roads in ROAD_GROUPINGS else ROAD_GROUPINGS[0]}
    # (Only when it differs from the default, so the selections saved before keep their identity.)
    if round(growth, 3) != DEFAULT_REFERENCE_GROWTH:
        request['reference_growth'] = round(growth, 3)
    return request


def requested(area_summary: Any) -> dict[str, Any] | None:
    """The NNS Break-down a job asks for, or None."""
    return normalize_request(area_summary.get(KEY)) if isinstance(area_summary, dict) else None


def job_modes(nr_mode: str) -> list[str]:
    """The NR Modes an NNS Break-down scores, each apart: NSA vs SA scores NSA, then SA."""
    from src.modules.cdr.nr_mode import NR_MODES, NSA_VS_SA

    return list(NR_MODES) if nr_mode == NSA_VS_SA else [nr_mode]


def _column(frame: pd.DataFrame, name: str) -> pd.Series:
    resolved = resolve_column_name(frame.columns, name)
    if resolved is None:
        return pd.Series([None] * len(frame), index=frame.index, dtype=object)
    return frame[resolved]


def _text(series: pd.Series) -> pd.Series:
    return series.astype(object).where(series.notna(), '').astype(str).str.strip()


def _site_number(series: pd.Series) -> pd.Series:
    return _text(series).str.replace(r'\.0+$', '', regex=True)


def _cities(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Whether each test is in a city, its size (``G_Level_3``) and its area name (``G_Level_4``)."""
    level_2 = _text(_column(frame, 'G_Level_2'))
    size = _text(_column(frame, 'G_Level_3'))
    name = _text(_column(frame, 'G_Level_4'))
    city = level_2.str.casefold().eq('city') | (level_2.eq('') & size.str.contains(r'cit(?:y|ies)', case=False, regex=True))
    return city, size, name


def city_regions(frames: Iterable[pd.DataFrame]) -> dict[str, str]:
    """The Region of each city: the one that holds most of its tests (of every CDR type), the first by name on a tie."""
    counts: dict[tuple[str, str], int] = {}
    for frame in frames:
        region = _text(_column(frame, 'Region'))
        city, _size, name = _cities(frame)
        mask = (city & name.ne('') & region.ne('')).to_numpy(dtype=bool)
        if not mask.any():
            continue
        for (area, owner), count in pd.DataFrame({'area': name[mask], 'region': region[mask]}).value_counts().items():
            counts[(area, owner)] = counts.get((area, owner), 0) + int(count)
    owners: dict[str, tuple[int, str]] = {}
    for (area, owner), count in counts.items():
        best = owners.get(area)
        if best is None or count > best[0] or (count == best[0] and owner.casefold() < best[1].casefold()):
            owners[area] = (count, owner)
    return {area: owner for area, (_count, owner) in owners.items()}


def scenario_lookup(cells: Iterable[tuple[Any, Any, Any, int]]) -> dict[tuple[str, str], str]:
    """The eMOCN scenario of each (host operator, site number) of an inventory such as the Multivendor Mapping of the
    workspace (rows of network, site, scenario and cells): NNS when any cell of the site is NNS, else the scenario of
    most of its cells."""
    from src.modules.network.master_grid import host_operator

    best: dict[tuple[str, str], tuple[tuple[int, int], str]] = {}
    for network, site, scenario, cells in cells:
        operator = host_operator(network)
        number = re.sub(r'\.0+$', '', str(site or '').strip())
        if not operator or not number:
            continue
        name = str(scenario or '').strip().upper()
        rank = (1 if name == NNS_SCENARIO else 0, int(cells or 0))
        key = (operator, number)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, name)
    return {key: name for key, (_rank, name) in best.items()}


def classify(frame: pd.DataFrame, lookup: dict[tuple[str, str], dict[str, str]], request: dict[str, Any],
             owners: dict[str, str] | None = None, scenarios: dict[tuple[str, str], str] | None = None) -> pd.DataFrame:
    """The tests of a CDR type in the Regions of the request, each with its Region (a city's is that of ``owners``,
    see city_regions), area, area kind and size, scenario and serving site (``__nns_*`` columns)."""
    from src.modules.network.master_grid import host_operator

    region = _text(_column(frame, 'Region'))
    test_region = region
    city, size, name = _cities(frame)
    if owners:
        region = name.map(owners).where(city & name.ne(''), region).fillna(region).astype(str)
    wanted = {value.casefold() for value in request.get('regions') or []}
    keep = region.ne('') & (region.str.casefold().isin(wanted) if wanted else True)
    mask = keep.to_numpy(dtype=bool)
    frame, region, city, size, name = frame[mask].copy(), region[mask], city[mask], size[mask], name[mask]
    frame['__nns_test_region'] = test_region[mask].to_numpy()
    road_type = size.where(size.ne(''), 'Roads')
    if request.get('roads') == 'each':
        road_area = name.where(name.ne(''), road_type)
    else:
        road_area = road_type + ' – ' + region
    frame['__nns_region'] = region.to_numpy()
    frame['__nns_kind'] = city.map({True: CITY_KIND, False: ROAD_KIND}).to_numpy()
    frame['__nns_area'] = name.where(city & name.ne(''), road_area).to_numpy()
    frame['__nns_size'] = size.where(city, road_type).where(lambda values: values.ne(''), 'Unknown').to_numpy()
    host = _text(_column(frame, 'Serving_Host_Network')).map(host_operator)
    site = _site_number(_column(frame, 'Serving_Site_ID'))
    # The scenario of the serving site in the inventory (the Multivendor Mapping), else the one the CDR row has.
    scenario = _text(_column(frame, 'Serving_eMOCN_Scenario'))
    if scenarios:
        found = pd.Series([scenarios.get((operator, number)) if operator and number else None
                           for operator, number in zip(host, site)], index=frame.index, dtype=object)
        scenario = found.where(found.notna(), scenario).astype(str)
    details = [lookup.get((operator, number)) if operator and number else None for operator, number in zip(host, site)]
    capacity = pd.Series([item['config'] if item else '' for item in details], index=frame.index, dtype=object)
    nns = scenario.str.upper().eq(NNS_SCENARIO)
    label = scenario.where(scenario.ne(''), NO_SCENARIO)
    label = label.where(~nns, capacity.map(nns_label))
    frame['__nns_scenario'] = label.to_numpy()
    frame['__nns_host'] = host.to_numpy()
    frame['__nns_site'] = site.to_numpy()
    frame['__nns_raw_scenario'] = scenario.str.upper().to_numpy()
    frame['__nns_is_nns'] = nns.map({True: NNS_SCENARIO, False: 'Other'}).to_numpy()
    return frame


def scoring_frames(frames: dict[str, pd.DataFrame], area: str, scenario: str = '__nns_scenario') -> dict[str, pd.DataFrame]:
    """The classified rows with the Region, City and Cluster columns the engine splits by holding their Region,
    ``area`` (its area or its size) and ``scenario`` (the scenario, or NNS or not)."""
    prepared = {}
    for kind, frame in frames.items():
        frame = frame.copy()
        for level, source in ((_REGION, '__nns_region'), (_AREA, area), (_SCENARIO, scenario)):
            column = resolve_column_name(frame.columns, level) or level
            frame[column] = frame[source].astype(object)
        prepared[kind] = frame
    return prepared


def site_counts(frames: dict[str, pd.DataFrame], lookup: dict[tuple[str, str], dict[str, str]]) -> dict[tuple[str, str], dict]:
    """The serving sites of the tests of each (Region, area): NNS sites by capacity, the other sites by eMOCN scenario,
    and the sites of the Master Grid kept and planned for NNS, by financial year."""
    rows = [frame[['__nns_region', '__nns_area', '__nns_host', '__nns_site', '__nns_raw_scenario']] for frame in frames.values()
            if len(frame)]
    if not rows:
        return {}
    sites = pd.concat(rows, ignore_index=True)
    sites = sites[sites['__nns_site'].ne('')].drop_duplicates()
    counts: dict[tuple[str, str], dict] = {}
    for (region, area), group in sites.groupby(['__nns_region', '__nns_area'], sort=False):
        # A site serving with several scenarios counts once, NNS first.
        by_site: dict[tuple[str, str], str] = {}
        for host, site, scenario in zip(group['__nns_host'], group['__nns_site'], group['__nns_raw_scenario']):
            key = (host or '?', site)
            if by_site.get(key) != NNS_SCENARIO:
                by_site[key] = scenario or ''
        entry = {'nns': {}, 'scenarios': {}, 'planned': {}, 'sites': len(by_site), 'not_in_grid': 0}
        for (host, site), scenario in by_site.items():
            details = lookup.get((host, site)) if host in ('VF', '3UK', 'O2') else None
            if host in ('VF', '3UK') and details is None:
                entry['not_in_grid'] += 1
            if scenario == NNS_SCENARIO:
                capacity = (details or {}).get('config') or UNKNOWN_CAPACITY
                entry['nns'][capacity] = entry['nns'].get(capacity, 0) + 1
                continue
            name = scenario or NO_SCENARIO
            entry['scenarios'][name] = entry['scenarios'].get(name, 0) + 1
            if details and details['keep_remove'].casefold() == 'keep' and details['target_fy']:
                entry['planned'][details['target_fy']] = entry['planned'].get(details['target_fy'], 0) + 1
        counts[(region, area)] = entry
    return counts


def area_details(frames: dict[str, pd.DataFrame]) -> dict[tuple[str, str], tuple[str, str]]:
    """The kind (City or Road) and size of each (Region, area)."""
    details: dict[tuple[str, str], tuple[str, str]] = {}
    for frame in frames.values():
        for region, area, kind, size in frame[['__nns_region', '__nns_area', '__nns_kind', '__nns_size']].drop_duplicates() \
                .itertuples(index=False):
            details.setdefault((region, area), (kind, size))
    return details


def _overall(rows: Iterable[dict], keys: tuple[str, ...]) -> dict[tuple, dict]:
    """The Overall points of each group of a result (its Combined environment)."""
    found = {}
    for row in rows or []:
        if row.get('environment') == 'Combined' and row.get('category') == 'Overall':
            found[tuple(str(row.get(key) or '') for key in keys)] = row
    return found


def _tests(result: dict, keys: tuple[str, ...]) -> dict[tuple, int]:
    tests: dict[tuple, int] = {}
    for row in result.get('test_counts') or []:
        key = tuple(str(row.get(name) or '') for name in keys)
        tests[key] = tests.get(key, 0) + int(row.get('tests') or 0)
    return tests


def _points(row: dict | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {'points': round(float(row.get('total_points') or 0), 2), 'max_points': round(float(row.get('max_points') or 0), 2),
            'complete': bool(row.get('complete_coverage'))}


def scores(result: dict, reliable: dict | None, keys: tuple[str, ...]) -> dict[tuple, dict[str, Any]]:
    """The Best Network and Most Reliable points and the tests of each group of a calculation."""
    best = _overall(result.get('totals'), keys)
    most = _overall((reliable or {}).get('totals'), keys)
    tests = _tests(result, keys)
    return {key: {'best': _points(best.get(key)), 'reliable': _points(most.get(key)), 'tests': tests.get(key, 0)}
            for key in dict.fromkeys([*best, *most])}


def add_gaps(rows: list[dict[str, Any]]) -> None:
    """The GAP to the #1 of each area (in place, in each campaign and scoring of each row: ``leader`` and ``gap``)."""
    leaders: dict[tuple, tuple[float, str]] = {}
    for row in rows:
        for campaign, values in (row.get('campaigns') or {}).items():
            for scoring in SCORINGS:
                scored = values.get(scoring)
                if not scored or scored.get('points') is None:
                    continue
                key = (row['region'], row['area'], campaign, scoring)
                best, points = leaders.get(key), float(scored['points'])
                if best is None or points > best[0] or (points == best[0] and row['operator'].casefold() < best[1].casefold()):
                    leaders[key] = (points, row['operator'])
    for row in rows:
        for campaign, values in (row.get('campaigns') or {}).items():
            for scoring in SCORINGS:
                scored, leader = values.get(scoring), leaders.get((row['region'], row['area'], campaign, scoring))
                if scored and scored.get('points') is not None and leader is not None:
                    scored.update({'leader': leader[1], 'gap': round(float(scored['points']) - leader[0], 2)})


SCORINGS = ('best', 'reliable')


def category_kinds(configuration: dict[str, Any]) -> dict[str, set[str]]:
    """The kinds of CDR (data, voice, speech) whose KPIs make each category of a methodology (Data, Voice)."""
    kinds: dict[str, set[str]] = {}
    for metric in configuration.get('metrics') or []:
        kinds.setdefault(str(metric.get('category')), set()).add(str(metric.get('source_kind') or '').lower())
    return kinds


def environment_points(result: dict | None, keys: tuple[str, ...]) -> dict[tuple, tuple[float, float]]:
    """The points and maximum of each group of a calculation in each environment and category (Data, Voice), before
    any scaling: what the group adds to a score of several groups."""
    found = {}
    for row in (result or {}).get('totals') or []:
        if row.get('environment') in (None, 'Combined') or row.get('category') in (None, 'Overall'):
            continue
        found[(*(str(row.get(key) or '') for key in keys), str(row['environment']), str(row['category']))] = (
            float(row.get('total_points') or 0), float(row.get('max_points') or 0))
    return found


def environment_tests(result: dict | None, keys: tuple[str, ...]) -> dict[tuple, int]:
    """The tests of each group of a calculation in each environment, per kind of CDR."""
    tests: dict[tuple, int] = {}
    for row in (result or {}).get('test_counts') or []:
        key = (*(str(row.get(name) or '') for name in keys), str(row.get('environment') or ''), str(row.get('kind') or '').lower())
        tests[key] = tests.get(key, 0) + int(row.get('tests') or 0)
    return tests


def overall_points(result: dict | None, keys: tuple[str, ...]) -> dict[tuple, tuple[float, float]]:
    """The points and maximum of each group of a calculation (its Combined environment, Overall)."""
    return {key: (float(row.get('total_points') or 0), float(row.get('max_points') or 0))
            for key, row in _overall((result or {}).get('totals'), keys).items()}


def reconcile(rows: list[dict[str, Any]], area_points: dict[str, dict[tuple, tuple[float, float]]],
              area_tests: dict[tuple, int], region_points: dict[str, dict[tuple, tuple[float, float]]],
              all_points: dict[str, dict[tuple, tuple[float, float]]], kinds: dict[str, set[str]],
              nr_mode: str) -> list[dict[str, Any]]:
    """The areas weighted as the methodology weighs them, against the scoring of their Region (as Country Areas).

    Each area adds to its Region its points in each environment and category (Data, Voice) times its share of the tests
    of the Region in that environment and category (the points of a City area share the City environment, those of the
    roads the Connecting Roads one). For each area row and scoring (in place): ``points_region`` (what it adds),
    ``weight_region`` (its share of the points of the Region) and ``gap_region`` (what it adds minus what the #1 of the
    Region adds there), and the same over every chosen Region (``_all``).

    Returns a row per Region (and one for all of them, ``region`` empty) and operator: per campaign and scoring, the
    real points of the Region, its #1, the real GAP to it, the weighted GAPs of its areas summed and the adjustment
    left by the scoring not being additive (rates, medians and thresholds of the Region are not those of its areas),
    so that the weighted GAPs plus the adjustment are the GAP of Country Areas.
    """
    category_tests: dict[tuple, int] = {}
    for (campaign, operator, region, area, environment, kind), count in area_tests.items():
        for category, category_kinds_ in kinds.items():
            if kind in category_kinds_:
                key = (campaign, operator, region, area, environment, category)
                category_tests[key] = category_tests.get(key, 0) + count
    in_region: dict[tuple, int] = {}
    in_all: dict[tuple, int] = {}
    for (campaign, operator, region, area, environment, category), count in category_tests.items():
        in_region[(campaign, operator, region, environment, category)] = in_region.get((campaign, operator, region, environment, category), 0) + count
        in_all[(campaign, operator, environment, category)] = in_all.get((campaign, operator, environment, category), 0) + count
    adds: dict[tuple, list[float]] = {}
    for scoring, table in area_points.items():
        for (campaign, operator, region, area, environment, category), (points, maximum) in table.items():
            count = category_tests.get((campaign, operator, region, area, environment, category), 0)
            for scope, total in (('region', in_region.get((campaign, operator, region, environment, category))),
                                 ('all', in_all.get((campaign, operator, environment, category)))):
                if total:
                    entry = adds.setdefault((scoring, scope, campaign, operator, region, area), [0.0, 0.0])
                    entry[0] += points * count / total
                    entry[1] += maximum * count / total

    def leaders(table: dict[tuple, tuple[float, float]], size: int) -> dict[tuple, tuple[str, float]]:
        found: dict[tuple, tuple[str, float]] = {}
        for key, (points, _maximum) in table.items():
            group, operator = (key[0], *key[2:size]), key[1]
            best = found.get(group)
            if best is None or points > best[1] or (points == best[1] and operator.casefold() < best[0].casefold()):
                found[group] = (operator, points)
        return found
    region_leaders = {scoring: leaders(table, 3) for scoring, table in region_points.items()}
    all_leaders = {scoring: leaders(table, 2) for scoring, table in all_points.items()}
    for row in rows:
        operator, region, area = row['operator'], row['region'], row['area']
        for campaign, values in (row.get('campaigns') or {}).items():
            for scoring in SCORINGS:
                scored = values.get(scoring)
                if not scored:
                    continue
                for scope, leader in (('region', region_leaders.get(scoring, {}).get((campaign, region))),
                                      ('all', all_leaders.get(scoring, {}).get((campaign,)))):
                    mine = adds.get((scoring, scope, campaign, operator, region, area))
                    maximum = (region_points if scope == 'region' else all_points).get(scoring, {}).get(
                        (campaign, operator, region) if scope == 'region' else (campaign, operator), (0, 0))[1]
                    if mine is None or leader is None:
                        scored.update({f'points_{scope}': None, f'weight_{scope}': None, f'gap_{scope}': None})
                        continue
                    reference = adds.get((scoring, scope, campaign, leader[0], region, area), [0.0, 0.0])
                    scored.update({f'points_{scope}': round(mine[0], 4),
                                   f'weight_{scope}': round(mine[1] / maximum, 6) if maximum else None,
                                   f'gap_{scope}': round(mine[0] - reference[0], 4), f'leader_{scope}': leader[0]})
    totals: dict[tuple, dict[str, Any]] = {}
    for scope, table_of, leaders_of, size in (('region', region_points, region_leaders, 3), ('all', all_points, all_leaders, 2)):
        for scoring, table in table_of.items():
            for key, (points, maximum) in table.items():
                campaign, operator = key[0], key[1]
                region = key[2] if size == 3 else ''
                leader = leaders_of[scoring].get((campaign, region) if size == 3 else (campaign,))
                entry = totals.setdefault((region, operator), {'nr_mode': nr_mode, 'region': region, 'operator': operator,
                                                               'campaigns': {}})
                scored = entry['campaigns'].setdefault(campaign, {'tests': 0})
                weighted = [values.get(scoring, {}).get(f'gap_{scope}') for row in rows
                            if row['operator'] == operator and (not region or row['region'] == region)
                            for values in [(row.get('campaigns') or {}).get(campaign) or {}]]
                weighted = [value for value in weighted if value is not None]
                added = [values.get(scoring, {}).get(f'points_{scope}') for row in rows
                         if row['operator'] == operator and (not region or row['region'] == region)
                         for values in [(row.get('campaigns') or {}).get(campaign) or {}]]
                added = [value for value in added if value is not None]
                gap = points - leader[1] if leader else None
                scored[scoring] = {'points': round(points, 2), 'max_points': round(maximum, 2), 'leader': leader[0] if leader else None,
                                   'gap': round(gap, 2) if gap is not None else None,
                                   'weighted_gap': round(sum(weighted), 4) if weighted else None,
                                   'weighted_points': round(sum(added), 4) if added else None,
                                   'adjustment': round(gap - sum(weighted), 4) if gap is not None and weighted else None}
    for row in rows:
        for campaign, values in (row.get('campaigns') or {}).items():
            for region in (row['region'], ''):
                entry = totals.get((region, row['operator']))
                if entry and campaign in entry['campaigns']:
                    entry['campaigns'][campaign]['tests'] += int(values.get('tests') or 0)
    return list(totals.values())


def projection_inputs(frames: dict[str, pd.DataFrame], lookup: dict[tuple[str, str], dict[str, str]],
                      operator_mappings: dict[str, str] | None = None) -> dict[tuple, dict]:
    """What the projection needs of each (Region, area, operator) in the latest campaign: its serving sites and those
    already NNS, its tests and those served by NNS sites, and the sites (and their tests) the Master Grid plans for NNS
    by financial year (Keep sites not NNS yet). The operators are named as the scoring names them (``operator_mappings``,
    alias to name)."""
    names = {str(alias).strip().casefold(): str(name).strip() for alias, name in (operator_mappings or {}).items()}
    rows = []
    for frame in frames.values():
        operator = resolve_column_name(frame.columns, 'Operator')
        if not len(frame) or operator is None:
            continue
        operators = frame[operator].astype(object).astype(str).str.strip()
        rows.append(pd.DataFrame({'region': frame['__nns_region'].to_numpy(), 'area': frame['__nns_area'].to_numpy(),
                                  'operator': operators.map(lambda value: names.get(value.casefold(), value)).to_numpy(),
                                  'host': frame['__nns_host'].to_numpy(), 'site': frame['__nns_site'].to_numpy(),
                                  'nns': frame['__nns_raw_scenario'].eq(NNS_SCENARIO).to_numpy()}))
    if not rows:
        return {}
    tests = pd.concat(rows, ignore_index=True)
    inputs: dict[tuple, dict] = {}
    for (region, area, operator), group in tests.groupby(['region', 'area', 'operator'], sort=False):
        entry = {'tests': int(len(group)), 'nns_tests': int(group['nns'].sum()), 'sites': 0, 'nns_sites': 0,
                 'planned_sites': {}, 'planned_tests': {}}
        served = group[group['site'].ne('')]
        for (host, site), site_tests in served.groupby(['host', 'site'], sort=False):
            entry['sites'] += 1
            if bool(site_tests['nns'].any()):
                entry['nns_sites'] += 1
                continue
            details = lookup.get((host, site))
            if details and details['keep_remove'].casefold() == 'keep' and details['target_fy']:
                year = details['target_fy']
                entry['planned_sites'][year] = entry['planned_sites'].get(year, 0) + 1
                entry['planned_tests'][year] = entry['planned_tests'].get(year, 0) + int(len(site_tests))
        inputs[(region, area, operator)] = entry
    return inputs


def projection(row: dict[str, Any], years: list[str], growth: float, reference: bool) -> dict[str, dict[str, Any]]:
    """The points of an area and operator projected over the financial years ``years``, by the share of NNS sites and by
    the share of tests served by NNS sites: each year adds to the year before its rise of the share times the points
    the NNS tests score above the area (the NNS points minus the area points); with fewer than MIN_NNS_TESTS NNS tests
    the points are not projected. The reference operator grows by ``growth`` % a year instead (from the first year on),
    at most to the maximum."""
    projected: dict[str, dict[str, Any]] = {}
    for scoring in SCORINGS:
        values = row.get(scoring) or {}
        area, nns, maximum = values.get('points'), values.get('nns_points'), values.get('max_points') or 1000
        if area is None:
            continue
        if int(row.get('nns_tests') or 0) < MIN_NNS_TESTS:
            nns = None   # (Too few NNS tests to project from.)
        lines: dict[str, list] = {'sites_share': [], 'sites': [], 'tests_share': [], 'tests': [], 'reference': []}
        for basis, total, now, planned in (('sites', row['sites'], row['nns_sites'], row['planned_sites']),
                                           ('tests', row['tests'], row['nns_tests'], row['planned_tests'])):
            share_before, points, added = (now / total if total else 0.0), float(area), 0
            for year in years:
                added += int(planned.get(year, 0))
                share = (now + added) / total if total else 0.0
                if nns is not None and not reference:
                    points = min(maximum, points + (share - share_before) * (float(nns) - float(area)))
                share_before = share
                lines[f'{basis}_share'].append(round(share, 4))
                lines[basis].append(round(points, 2) if nns is not None or reference else None)
        points = float(area)
        for index, _year in enumerate(years):
            if index:
                points = min(maximum, points * (1 + growth / 100))
            lines['reference'].append(round(points, 2))
        projected[scoring] = lines
    return projected


def region_projection(breakdown: dict[str, Any], years: list[str], growth: float) -> list[dict[str, Any]]:
    """The projection of each Region (and of all the chosen Regions, ``region`` empty) and operator: its points today (as
    Country Areas scores it) plus, each year, what the projections of its areas add to it weighted as the methodology
    weighs them (``weight_region``, ``weight_all``), by NNS sites and by NNS tests; the reference operator growing by
    ``growth`` % a year from its points today."""
    reference = str(breakdown.get('reference_operator') or '').strip().casefold()
    latest = {mode['nr_mode']: mode.get('latest_campaign') for mode in breakdown.get('modes') or [] if isinstance(mode, dict)}
    weights = {(row['nr_mode'], row['region'], row['area'], row['operator']): ((row.get('campaigns') or {}).get(latest.get(row['nr_mode'])) or {})
               for row in breakdown.get('areas') or []}
    totals = {(row['nr_mode'], row['region'], row['operator']): ((row.get('campaigns') or {}).get(latest.get(row['nr_mode'])) or {})
              for row in breakdown.get('gap_totals') or []}
    projected: dict[tuple, dict[str, Any]] = {}
    for row in breakdown.get('projection') or []:
        is_reference = row['operator'].strip().casefold() == reference
        lines_of = projection(row, years, growth, is_reference)
        for region, scope in ((row['region'], 'region'), ('', 'all')):
            key = (row['nr_mode'], region, row['operator'])
            if key not in totals:
                continue
            entry = projected.setdefault(key, {'nr_mode': row['nr_mode'], 'region': region, 'operator': row['operator'],
                                              'sites': 0, 'nns_sites': 0, 'tests': 0, 'nns_tests': 0, 'planned_sites': {},
                                              'planned_tests': {}, 'gains': {}})
            for name in ('sites', 'nns_sites', 'tests', 'nns_tests'):
                entry[name] += int(row.get(name) or 0)
            for name in ('planned_sites', 'planned_tests'):
                for year, count in (row.get(name) or {}).items():
                    entry[name][year] = entry[name].get(year, 0) + int(count)
            for scoring in SCORINGS:
                lines, weight = lines_of.get(scoring), (weights.get((row['nr_mode'], row['region'], row['area'], row['operator'])) or {}).get(scoring) or {}
                share = weight.get(f'weight_{scope}')
                if not lines or share is None or is_reference:
                    continue
                gains = entry['gains'].setdefault(scoring, {'sites': [0.0] * len(years), 'tests': [0.0] * len(years)})
                area_points = float((row.get(scoring) or {}).get('points') or 0)
                for basis in ('sites', 'tests'):
                    for index, points in enumerate(lines[basis]):
                        if points is not None:
                            gains[basis][index] += float(share) * (points - area_points)
    rows = []
    for (nr_mode, region, operator), entry in projected.items():
        is_reference = operator.strip().casefold() == reference
        for scoring in SCORINGS:
            today = (totals.get((nr_mode, region, operator)) or {}).get(scoring) or {}
            if today.get('points') is None:
                continue
            base, maximum = float(today['points']), float(today.get('max_points') or 1000)
            lines: dict[str, list] = {'sites_share': [], 'sites': [], 'tests_share': [], 'tests': [], 'reference': []}
            for basis, total, now, planned in (('sites', entry['sites'], entry['nns_sites'], entry['planned_sites']),
                                               ('tests', entry['tests'], entry['nns_tests'], entry['planned_tests'])):
                added = 0
                for index, year in enumerate(years):
                    added += int(planned.get(year, 0))
                    lines[f'{basis}_share'].append(round((now + added) / total, 4) if total else None)
                    gain = 0.0 if is_reference else entry['gains'].get(scoring, {}).get(basis, [0.0] * len(years))[index]
                    lines[basis].append(round(min(maximum, base + gain), 2))
            points = base
            for index, _year in enumerate(years):
                if index:
                    points = min(maximum, points * (1 + growth / 100))
                lines['reference'].append(round(points, 2))
            if is_reference:
                lines['sites'], lines['tests'] = list(lines['reference']), list(lines['reference'])
            rows.append({**{name: entry[name] for name in ('nr_mode', 'region', 'operator', 'sites', 'nns_sites', 'tests', 'nns_tests')},
                         'scoring': scoring, 'points': round(base, 2), 'lines': lines})
    return rows


def scenario_order(labels: Iterable[str]) -> list[str]:
    """The scenarios in their order: NNS by capacity, the eMOCN scenarios, then the tests without one."""
    labels = list(dict.fromkeys(labels))
    known = [label for label in SCENARIO_ORDER if label in labels]
    other = sorted((label for label in labels if label not in SCENARIO_ORDER and label != NO_SCENARIO),
                   key=lambda value: [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', value)])
    return [*known, *other, *([NO_SCENARIO] if NO_SCENARIO in labels else [])]


def sort_campaigns(campaigns: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(campaigns), key=lambda value: (campaign_sort_key(value), value))


def fy_order(values: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(values), key=lambda value: (int(match.group(1)) if (match := re.search(r'(\d+)', value)) else 999, value))


def operator_order(operators: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(operators), key=str.casefold)


def _value(points: Any) -> float | None:
    return round(float(points['points']), 2) if isinstance(points, dict) and points.get('points') is not None else None


def workbook(breakdown: dict[str, Any], title: str = '') -> bytes:
    """The NNS Break-down as an Excel workbook: Areas (each campaign's Best Network and Most Reliable points, tests and
    GAPs to #1), GAP Totals (per Region and for all the Regions), Sites (the serving sites of each area), Scenarios (the
    latest campaign by city size and scenario) and About."""
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from src.modules.cdr.column_names import format_campaign

    book = Workbook()
    header_font, header_fill = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor='10314A')

    def sheet(name: str, header: list[str], rows: list[list[Any]], first: bool = False):
        worksheet = book.active if first else book.create_sheet()
        worksheet.title = name
        worksheet.append(header)
        for cell in worksheet[1]:
            cell.font, cell.fill = header_font, header_fill
            cell.alignment = Alignment(wrap_text=True, vertical='center')
        for row in rows:
            worksheet.append(row)
        worksheet.freeze_panes = 'A2'
        worksheet.auto_filter.ref = worksheet.dimensions
        for index, column in enumerate(header, start=1):
            width = max([len(str(column))] + [len(str(row[index - 1])) for row in rows[:500] if row[index - 1] is not None])
            worksheet.column_dimensions[get_column_letter(index)].width = min(40, max(9, width + 2))
        return worksheet

    modes = [mode for mode in breakdown.get('modes') or [] if isinstance(mode, dict)]
    campaigns = sort_campaigns(campaign for mode in modes for campaign in mode.get('campaigns') or [])
    label = lambda value: format_campaign(value) or value
    scorings = (('best', 'Best Network'), ('reliable', 'Most Reliable'))
    # Each campaign under a band of its own colour, its Tests first, then its Best Network and its Most Reliable columns.
    # The colours of the tool: deep navy and teal shades, one per campaign; within a campaign Tests stay neutral, Best
    # Network takes a mid shade of it and Most Reliable a light one (its values on a faint tint too), with a strong
    # line between campaigns and a thin one between their parts.
    palette = ('10314A', '0F766E', '1D4E89', '0E7490', '334E68', '115E59', '1E3A8A', '155E75')
    part_shades = {'Tests': None, 'Best Network': .3, 'Most Reliable': .62}

    def tint(color: str, share: float) -> str:
        """``color`` mixed with white (``share`` of white)."""
        channels = [int(color[index:index + 2], 16) for index in (0, 2, 4)]
        return ''.join(f'{round(value + (255 - value) * share):02X}' for value in channels)

    def grouped_sheet(name: str, fixed: list[str], groups: list[tuple[str, list[tuple[str, list[str]]]]],
                      rows: list[list[Any]], first: bool = False):
        """A sheet with three header rows: each group (a campaign) in a band of its colour, its parts (Tests, a scoring)
        in a band of a shade of it, then the names of the columns; the fixed columns on the third row."""
        from openpyxl.styles import Border, Side

        worksheet = book.active if first else book.create_sheet()
        worksheet.title = name
        top, middle, bottom = [''] * len(fixed), [''] * len(fixed), list(fixed)
        spans, lines, faint = [], {}, []
        for index, (group, parts) in enumerate(groups):
            color = palette[index % len(palette)]
            start = len(bottom) + 1
            lines[start] = Side(style='medium', color=color)
            for position, (part, columns) in enumerate(parts):
                shade = part_shades.get(part, .45)
                first_column, last_column = len(bottom) + 1, len(bottom) + len(columns)
                if position:
                    lines.setdefault(first_column, Side(style='thin', color=tint(color, .2)))
                spans.append(('middle', first_column, last_column, part,
                              'E2E8F0' if shade is None else tint(color, shade), shade is not None and shade < .5,
                              'F1F5F9' if shade is None else tint(color, min(.9, shade + .52))))
                if shade is not None and shade >= .5:
                    faint.append((first_column, last_column, tint(color, .94)))
                middle += [part] + [''] * (len(columns) - 1)
                bottom += columns
            top += [group] + [''] * (len(bottom) - start)
            spans.append(('top', start, len(bottom), group, color, True, None))
        for values in (top, middle, bottom):
            worksheet.append(values)
        dark, white = Font(bold=True, color='17232D'), Font(bold=True, color='FFFFFF')
        # (The names of the fixed columns on the third row, with the filters; the two rows above them in one block.)
        for column in range(1, len(fixed) + 1):
            worksheet.merge_cells(start_row=1, start_column=column, end_row=2, end_column=column)
            for row in (1, 3):
                cell = worksheet.cell(row=row, column=column)
                cell.font, cell.fill = header_font, header_fill
                cell.alignment = Alignment(wrap_text=True, vertical='center')
        for row_name, first_column, last_column, text, color, light_text, names_color in spans:
            row = 1 if row_name == 'top' else 2
            if last_column > first_column:
                worksheet.merge_cells(start_row=row, start_column=first_column, end_row=row, end_column=last_column)
            cell = worksheet.cell(row=row, column=first_column)
            cell.fill = PatternFill('solid', fgColor=color)
            cell.font = white if light_text else dark
            cell.alignment = Alignment(horizontal='center', vertical='center')
            if names_color:
                for column in range(first_column, last_column + 1):
                    worksheet.cell(row=3, column=column).fill = PatternFill('solid', fgColor=names_color)
        for column in range(len(fixed) + 1, len(bottom) + 1):
            cell = worksheet.cell(row=3, column=column)
            cell.font, cell.alignment = Font(bold=True, color='17232D'), Alignment(wrap_text=True, vertical='center', horizontal='center')
        for row in rows:
            worksheet.append(row)
        # Shares as percentages, points and GAPs with two decimals, tests as whole numbers.
        for index, name in enumerate(bottom, start=1):
            if index <= len(fixed) and name not in ('Serving sites', 'NNS sites', 'Tests', 'NNS tests', 'Points', 'NNS points'):
                continue
            text = str(name)
            number_format = ('0.0%' if text.startswith(('Weight in', 'NNS %')) else '#,##0' if text in ('Tests', 'NNS tests', 'Serving sites', 'NNS sites')
                             else '0.00' if any(word in text for word in ('Points', 'points', 'GAP', 'Adjustment')) else None)
            if number_format:
                for row_cells in worksheet.iter_rows(min_row=4, max_row=worksheet.max_row, min_col=index, max_col=index):
                    row_cells[0].number_format = number_format
        # The values of Most Reliable on a faint tint, and the lines between the campaigns and their parts on every row.
        for first_column, last_column, color in faint:
            fill = PatternFill('solid', fgColor=color)
            for row_cells in worksheet.iter_rows(min_row=4, max_row=worksheet.max_row, min_col=first_column, max_col=last_column):
                for cell in row_cells:
                    cell.fill = fill
        for column, side in lines.items():
            for row_index in range(1, worksheet.max_row + 1):
                cell = worksheet.cell(row=row_index, column=column)
                cell.border = Border(left=side, top=cell.border.top, bottom=cell.border.bottom, right=cell.border.right)
        worksheet.freeze_panes = worksheet.cell(row=4, column=len(fixed) + 1)
        worksheet.auto_filter.ref = f'A3:{get_column_letter(len(bottom))}{max(3, worksheet.max_row)}'
        worksheet.row_dimensions[3].height = 45
        for index, column in enumerate(bottom, start=1):
            width = max([len(str(column)) if index <= len(fixed) else 10] + [len(str(row[index - 1])) for row in rows[:500] if row[index - 1] is not None])
            worksheet.column_dimensions[get_column_letter(index)].width = min(40, max(9, width + 2))
        return worksheet

    area_columns = ['Points', '#1 of the area', 'GAP to #1 of the area', 'Weight in its Region',
                    'Weighted GAP to #1 of the Region', 'Weighted GAP to #1 of all the Regions']
    area_parts = lambda: [('Tests', ['Tests']), *[(name, list(area_columns)) for _key, name in scorings]]
    totals = [row for row in breakdown.get('gap_totals') or [] if isinstance(row, dict)]
    rows = []
    # Each Region first with its own scoring (as Country Areas), then its areas, then the adjustment that closes the sum
    # of their weighted GAPs to its GAP; all the chosen Regions at the end.
    area_rows = sorted(breakdown.get('areas') or [], key=lambda item: (item['nr_mode'], item['region'], item['kind'] != CITY_KIND,
                                                                     item['size'], item['area'], item['operator']))
    regions = sorted({(row['nr_mode'], row['region']) for row in [*area_rows, *totals]}, key=lambda item: (item[0], item[1] == '', item[1]))

    def total_values(total: dict[str, Any], adjustment: bool) -> list[Any]:
        values = []
        for campaign in campaigns:
            entry = (total.get('campaigns') or {}).get(campaign) or {}
            values.append(None if adjustment else entry.get('tests'))
            for key, _name in scorings:
                scored = entry.get(key) or {}
                if adjustment:
                    column = scored.get('adjustment')
                    values += [None, None, None, None, column if total['region'] else None, None if total['region'] else column]
                else:
                    values += [scored.get('points'), scored.get('leader'), scored.get('gap'), 1 if total['region'] else None, None, None]
        return values
    for nr_mode, region in regions:
        name = region or 'All the chosen Regions'
        of_region = [total for total in totals if total['nr_mode'] == nr_mode and total['region'] == region]
        for total in sorted(of_region, key=lambda item: item['operator']):
            rows.append([nr_mode, region or name, f'{name} (whole Region)' if region else name, 'Region', '', total['operator'],
                         *total_values(total, False)])
        for row in (item for item in area_rows if item['nr_mode'] == nr_mode and item['region'] == region):
            values = [row['nr_mode'], row['region'], row['area'], row['kind'], row['size'], row['operator']]
            for campaign in campaigns:
                scored = (row.get('campaigns') or {}).get(campaign) or {}
                values.append(scored.get('tests') if scored else None)
                for key, _name in scorings:
                    points = scored.get(key) or {}
                    values += [_value(points), points.get('leader'), points.get('gap'), points.get('weight_region'),
                               points.get('gap_region'), points.get('gap_all')]
            rows.append(values)
        for total in sorted(of_region, key=lambda item: item['operator']):
            rows.append([nr_mode, region or name, 'Adjustment (the scoring is not additive)', 'Adjustment', '', total['operator'],
                         *total_values(total, True)])
    grouped_sheet('Areas', ['NR Mode', 'Region', 'Area', 'Kind', 'Size', 'Operator'],
                  [(label(campaign), area_parts()) for campaign in campaigns], rows, first=True)
    rows = []
    for total in sorted(totals, key=lambda item: (item['nr_mode'], item['region'] == '', item['region'], item['operator'])):
        values = [total['nr_mode'], total['region'] or 'All the chosen Regions', total['operator']]
        for campaign in campaigns:
            entry = (total.get('campaigns') or {}).get(campaign) or {}
            values.append(entry.get('tests'))
            for key, _name in scorings:
                scored = entry.get(key) or {}
                values += [scored.get('points'), scored.get('leader'), scored.get('gap'), scored.get('weighted_gap'),
                           scored.get('adjustment'), scored.get('weighted_points')]
        rows.append(values)
    grouped_sheet('GAP Totals', ['NR Mode', 'Region', 'Operator'],
                  [(label(campaign), [('Tests', ['Tests']), *[(name, ['Points', '#1', 'GAP to #1', 'Weighted GAP of its areas',
                                                                       'Adjustment', 'Weighted points of its areas'])
                                                              for _key, name in scorings]]) for campaign in campaigns], rows)
    # The projection: each area and operator of the latest campaign over the financial years the Master Grid plans.
    projected_rows = [row for row in breakdown.get('projection') or [] if isinstance(row, dict)]
    planned_years = fy_order(year for row in projected_rows for year in (row.get('planned_sites') or {}))
    numbers = [int(match.group(1)) for year in planned_years if (match := re.search(r'(\d+)', year))]
    years = [f'FY{number:02d}' for number in range(min(numbers), max(numbers) + 1)] if numbers else []
    reference = str(breakdown.get('reference_operator') or '').strip().casefold()
    growth = float(breakdown.get('reference_growth', DEFAULT_REFERENCE_GROWTH))
    rows = []
    # Each Region (and all the chosen Regions) first: its points today plus what its areas add, weighted as the methodology.
    region_rows = region_projection(breakdown, years, growth)
    region_reference = {(item['nr_mode'], item['region'], item['scoring']): item['lines']['reference'] for item in region_rows
                        if item['operator'].strip().casefold() == reference}
    for item in sorted(region_rows, key=lambda entry: (entry['nr_mode'], entry['region'] == '', entry['region'], entry['operator'],
                                                       entry['scoring'] != 'best')):
        name, lines = dict(scorings)[item['scoring']], item['lines']
        ahead = region_reference.get((item['nr_mode'], item['region'], item['scoring'])) or [None] * len(years)
        label_region = item['region'] or 'All the chosen Regions'
        values = [item['nr_mode'], label_region, f'{label_region} (whole Region)' if item['region'] else label_region, 'Region', '',
                  item['operator'], name, item['sites'], item['nns_sites'], item['tests'], item['nns_tests'], item['points'], None]
        for index, _year in enumerate(years):
            reference_points = ahead[index]
            gap = lambda points: round(points - reference_points, 2) if points is not None and reference_points is not None else None
            values += [lines['sites_share'][index], lines['sites'][index], lines['tests_share'][index], lines['tests'][index],
                       reference_points, gap(lines['sites'][index]), gap(lines['tests'][index])]
        rows.append(values)
    for row in sorted(projected_rows, key=lambda item: (item['nr_mode'], item['region'], item['kind'] != CITY_KIND, item['size'],
                                                        item['area'], item['operator'])):
        is_reference = row['operator'].strip().casefold() == reference
        own = projection(row, years, growth, is_reference)
        reference_row = next((item for item in projected_rows if item['nr_mode'] == row['nr_mode'] and item['region'] == row['region']
                              and item['area'] == row['area'] and item['operator'].strip().casefold() == reference), None)
        reference_lines = projection(reference_row, years, growth, True) if reference_row else {}
        for key, name in scorings:
            lines, base = own.get(key), row.get(key) or {}
            if not lines:
                continue
            ahead = (reference_lines.get(key) or {}).get('reference') or [None] * len(years)
            if is_reference:
                lines = {**lines, 'sites': lines['reference'], 'tests': lines['reference']}
            values = [row['nr_mode'], row['region'], row['area'], row['kind'], row['size'], row['operator'], name,
                      row['sites'], row['nns_sites'], row['tests'], row['nns_tests'], base.get('points'), base.get('nns_points')]
            for index, _year in enumerate(years):
                reference_points = ahead[index]
                gap = lambda points: round(points - reference_points, 2) if points is not None and reference_points is not None else None
                values += [lines['sites_share'][index], lines['sites'][index], lines['tests_share'][index], lines['tests'][index],
                           reference_points, gap(lines['sites'][index]), gap(lines['tests'][index])]
            rows.append(values)
    reference_label = breakdown.get('reference_operator') or 'reference'
    grouped_sheet('Projection', ['NR Mode', 'Region', 'Area', 'Kind', 'Size', 'Operator', 'Scoring', 'Serving sites', 'NNS sites',
                                 'Tests', 'NNS tests', 'Points', 'NNS points'],
                  [(year, [('By sites', ['NNS % of sites', 'Points']), ('By tests', ['NNS % of tests', 'Points']),
                           (f'{reference_label} (+{growth:g} %/year)', [f'{reference_label} points', 'GAP by sites', 'GAP by tests'])])
                   for year in years], rows)
    sites = breakdown.get('sites') or []
    capacities = [*CAPACITIES, *sorted({name for row in sites for name in row.get('nns') or {} if name not in CAPACITIES})]
    scenarios = scenario_order(name for row in sites for name in row.get('scenarios') or {})
    years = fy_order(name for row in sites for name in row.get('planned') or {})
    header = ['NR Mode', 'Region', 'Area', 'Serving sites', *(f'NNS {name}' for name in capacities), 'NNS total',
              *scenarios, *(f'Planned NNS {name}' for name in years), 'Planned NNS total', 'VF/3UK sites not in the Master Grid']
    rows = []
    for row in sorted(sites, key=lambda item: (item['nr_mode'], item['region'], item['area'])):
        nns, other, planned = row.get('nns') or {}, row.get('scenarios') or {}, row.get('planned') or {}
        rows.append([row['nr_mode'], row['region'], row['area'], row.get('sites', 0), *(nns.get(name, 0) for name in capacities),
                     sum(nns.values()), *(other.get(name, 0) for name in scenarios), *(planned.get(name, 0) for name in years),
                     sum(planned.values()), row.get('not_in_grid', 0)])
    sheet('Sites', header, rows)
    order = {name: index for index, name in enumerate(breakdown.get('scenario_order') or [])}
    rows = [[row['nr_mode'], label(row['campaign']), row['size'], row['scenario'], row['operator'], _value(row.get('best')),
             _value(row.get('reliable')), row.get('tests')]
            for row in sorted(breakdown.get('scenarios') or [], key=lambda item: (
                item['nr_mode'], item['size'], order.get(item['scenario'], 999), item['operator']))]
    sheet('Scenarios', ['NR Mode', 'Campaign', 'Size', 'Scenario', 'Operator', 'Best Network', 'Most Reliable', 'Tests'], rows)
    request, grid = breakdown.get('request') or {}, breakdown.get('master_grid') or {}
    inventory = breakdown.get('inventory') or {}
    reference_label = breakdown.get('reference_operator') or 'the reference operator'
    # What the workbook holds: its settings, then each sheet, its columns by group, and where their values come from.
    about = [
        ['Settings', '', 'Saved Scoring', title],
        ['Settings', '', 'Regions', ', '.join(request.get('regions') or []) or 'Every Region'],
        ['Settings', '', 'Connecting roads', 'Each road on its own' if request.get('roads') == 'each' else 'Grouped by Region (Roads, Highway)'],
        *[['Settings', '', f'{mode["nr_mode"]} campaigns', ', '.join(label(value) for value in mode.get('campaigns') or [])] for mode in modes],
        ['Settings', '', 'Inventory (scenarios)', inventory.get('file_name') or 'None: the eMOCN scenario of the CDR rows'],
        ['Settings', '', 'Master Grid', f"{grid.get('file_name', '')} ({grid.get('week', '')})" if grid else 'None'],
        ['Settings', '', 'Reference operator', f'{reference_label}, growing {breakdown.get("reference_growth", DEFAULT_REFERENCE_GROWTH):g} % a year in the projection'],
        ['Areas', 'Rows', 'Region, then its areas, then Adjustment',
         'Each Region first with its own scoring (as Country Areas scores it: every test of the Region with its own Region), '
         'then each city (G_Level_4, its size from G_Level_3) and its connecting roads (Roads and Highway, G_Level_3), then '
         'the adjustment of the Region. Each city belongs to the Region with most of its tests over the campaigns; the roads '
         'keep the Region of each test.'],
        ['Areas', 'Each campaign', 'Tests', 'The Data tests, Voice calls and Speech samples of the operator in the area (CDRs).'],
        ['Areas', 'Best Network / Most Reliable', 'Points',
         'The points of the area with the methodology of the campaign, scaled to the full points when the area is measured '
         'in one environment only (as each area of Country Areas). Region rows: the points of the whole Region.'],
        ['Areas', 'Best Network / Most Reliable', '#1 of the area, GAP to #1 of the area',
         'The operator with the most points in the area, and the points of the operator minus those of that #1.'],
        ['Areas', 'Best Network / Most Reliable', 'Weight in its Region',
         'The share of the points of the Region the area weighs, as the methodology weighs it: the maximum points of its '
         'environment and category (Data, Voice) times its share of the tests of the Region there.'],
        ['Areas', 'Best Network / Most Reliable', 'Weighted GAP to #1 of the Region',
         'What the area adds to the GAP of its Region to the #1 of the Region: its points in its environment and category '
         'times its share of the tests of the Region there, minus those of the #1 of the Region. The weighted GAPs of the '
         'areas of a Region plus its Adjustment row are the GAP of its Region row (and of Country Areas).'],
        ['Areas', 'Best Network / Most Reliable', 'Weighted GAP to #1 of all the Regions',
         'The same over every chosen Region, against the #1 of all of them; summed with the Adjustment row of All the '
         'chosen Regions, the GAP of All the chosen Regions.'],
        ['Areas', 'Adjustment rows', 'Weighted GAP',
         'The scoring is not additive (the rates, medians and thresholds of a Region are not those of its areas, and a few '
         'tests of a city lie in another Region): the adjustment is the GAP of the Region minus the weighted GAPs of its areas.'],
        ['GAP Totals', 'Each campaign and scoring', 'Points, #1, GAP to #1',
         'Each Region (and all the chosen Regions) scored as Country Areas scores it.'],
        ['GAP Totals', 'Each campaign and scoring', 'Weighted GAP of its areas, Adjustment, Weighted points of its areas',
         'The weighted GAPs of its areas summed, the adjustment that closes them to its GAP, and the points of its areas '
         'weighted the same way.'],
        ['Sites', 'Serving sites (latest campaign)', 'Serving sites, NNS High · Medium · Low · Not in the Master Grid, NNS total, '
         'S0 … S123, No eMOCN scenario',
         'The sites serving the tests of each area. Their eMOCN scenario (NNS or S0, S1…) comes from the inventory '
         '(Multivendor Mapping; without it, from the CDR rows); the capacity of the NNS sites from the High/Med/Low config '
         'of the Master Grid.'],
        ['Sites', 'Master Grid', 'Planned NNS FYxx, Planned NNS total, VF/3UK sites not in the Master Grid',
         'The Keep sites among them, not NNS yet, that the Master Grid plans for NNS, by Target Deployment FY; the sites '
         'serving Vodafone or 3 that the Master Grid does not list. A site is found by its own number or by that of the '
         'site it pairs with (SITE ID + Pairing, SiteRef2).'],
        ['Scenarios', 'Latest campaign', 'Size, Scenario, Best Network, Most Reliable, Tests',
         'Each test scored with the kind of site that served it: an NNS site by its capacity, or its eMOCN scenario '
         '(inventory), per city size and road type.'],
        ['Projection', 'Region rows', 'Points of each year',
         'Each Region (and all the chosen Regions) first: its points today, as Country Areas scores it, plus what the '
         'projections of its areas add, weighted as the methodology weighs them (Weight in its Region of the Areas sheet).'],
        ['Projection', 'Today (latest campaign)', 'Serving sites, NNS sites, Tests, NNS tests, Points, NNS points',
         'The sites and tests of the operator in the area, those of NNS sites, its points and the points of its tests '
         f'served by NNS sites (not projected with fewer than {MIN_NNS_TESTS} NNS tests).'],
        ['Projection', 'Each financial year', 'NNS % of sites, Points (by sites)',
         'The share of NNS sites once the sites the Master Grid plans up to that year are NNS; the points of the year '
         'before plus the rise of that share times the NNS points minus the points of the area (cumulative).'],
        ['Projection', 'Each financial year', 'NNS % of tests, Points (by tests)',
         'The same with the share of the tests served by those sites.'],
        ['Projection', 'Each financial year', f'{reference_label} points, GAP by sites, GAP by tests',
         f'{reference_label} growing its points {breakdown.get("reference_growth", DEFAULT_REFERENCE_GROWTH):g} % a year '
         'from the first year on (at most to the maximum), and the GAP of the projected points to it.'],
        *[['Warning', '', '', warning] for warning in breakdown.get('warnings') or []],
    ]
    about_sheet = sheet('About', ['Sheet', 'Group', 'Columns', 'What they hold and where they come from'], about)
    for column, width in (('A', 14), ('B', 28), ('C', 46), ('D', 110)):
        about_sheet.column_dimensions[column].width = width
    for row in about_sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    # (The Projection after the Scenarios, before About.)
    book.move_sheet('Projection', offset=book.sheetnames.index('About') - book.sheetnames.index('Projection') - 1)
    output = BytesIO()
    book.save(output)
    return output.getvalue()


def of_kind(frames: dict[str, pd.DataFrame], kind: str) -> dict[str, pd.DataFrame]:
    """The classified rows of the cities or of the connecting roads: each is scored apart, so an area measured in one
    environment only is scaled to the full points (as the areas of Country Areas)."""
    chosen = {}
    for name, frame in frames.items():
        mask = frame['__nns_kind'].eq(kind).to_numpy(dtype=bool)
        if mask.any():
            chosen[name] = frame[mask]
    return chosen
