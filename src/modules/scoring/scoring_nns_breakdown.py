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
VERSION = 2
CITY_KIND = 'City'
ROAD_KIND = 'Road'
NO_SCENARIO = 'No eMOCN scenario'
NNS_SCENARIO = 'NNS'
CAPACITIES = ('High', 'Medium', 'Low')
UNKNOWN_CAPACITY = 'Not in the Master Grid'
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
    return {'campaigns': campaigns, 'regions': sorted(regions.values(), key=str.casefold),
            'roads': roads if roads in ROAD_GROUPINGS else ROAD_GROUPINGS[0]}


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


def classify(frame: pd.DataFrame, lookup: dict[tuple[str, str], dict[str, str]], request: dict[str, Any]) -> pd.DataFrame:
    """The tests of a CDR type in the Regions of the request, each with its Region, area, area kind and size, scenario
    and serving site (``__nns_*`` columns)."""
    from src.modules.network.master_grid import host_operator

    region = _text(_column(frame, 'Region'))
    wanted = {value.casefold() for value in request.get('regions') or []}
    keep = region.ne('') & (region.str.casefold().isin(wanted) if wanted else True)
    frame, region = frame[keep.to_numpy(dtype=bool)].copy(), region[keep]
    level_2 = _text(_column(frame, 'G_Level_2'))
    size = _text(_column(frame, 'G_Level_3'))
    name = _text(_column(frame, 'G_Level_4'))
    city = level_2.str.casefold().eq('city') | (level_2.eq('') & size.str.contains(r'cit(?:y|ies)', case=False, regex=True))
    road_type = size.where(size.ne(''), 'Roads')
    if request.get('roads') == 'each':
        road_area = name.where(name.ne(''), road_type)
    else:
        road_area = road_type + ' – ' + region
    frame['__nns_region'] = region.to_numpy()
    frame['__nns_kind'] = city.map({True: CITY_KIND, False: ROAD_KIND}).to_numpy()
    frame['__nns_area'] = name.where(city & name.ne(''), road_area).to_numpy()
    frame['__nns_size'] = size.where(city, road_type).where(lambda values: values.ne(''), 'Unknown').to_numpy()
    scenario = _text(_column(frame, 'Serving_eMOCN_Scenario'))
    host = _text(_column(frame, 'Serving_Host_Network')).map(host_operator)
    site = _site_number(_column(frame, 'Serving_Site_ID'))
    details = [lookup.get((operator, number)) if operator and number else None for operator, number in zip(host, site)]
    capacity = pd.Series([item['config'] if item else '' for item in details], index=frame.index, dtype=object)
    nns = scenario.str.upper().eq(NNS_SCENARIO)
    label = scenario.where(scenario.ne(''), NO_SCENARIO)
    label = label.where(~nns, capacity.map(nns_label))
    frame['__nns_scenario'] = label.to_numpy()
    frame['__nns_host'] = host.to_numpy()
    frame['__nns_site'] = site.to_numpy()
    frame['__nns_raw_scenario'] = scenario.str.upper().to_numpy()
    return frame


def scoring_frames(frames: dict[str, pd.DataFrame], area: str, region: str | None = None) -> dict[str, pd.DataFrame]:
    """The classified rows with the Region, City and Cluster columns the engine splits by holding ``region`` (its
    Region), ``area`` (its area or its size) and the scenario."""
    prepared = {}
    for kind, frame in frames.items():
        frame = frame.copy()
        for level, source in ((_REGION, '__nns_region'), (_AREA, area), (_SCENARIO, '__nns_scenario')):
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
    """The NNS Break-down as an Excel workbook: Areas (each campaign's Best Network and Most Reliable points and tests),
    Sites (the serving sites of each area), Scenarios (the latest campaign by city size and scenario) and About."""
    from io import BytesIO

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from src.modules.cdr.column_names import format_campaign

    book = Workbook()
    header_font, header_fill = Font(bold=True, color='FFFFFF'), PatternFill('solid', fgColor='0F766E')

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
    header = ['NR Mode', 'Region', 'Area', 'Kind', 'Size', 'Operator']
    for campaign in campaigns:
        header += [f'{label(campaign)} Best Network', f'{label(campaign)} Most Reliable', f'{label(campaign)} Tests']
    rows = []
    for row in sorted(breakdown.get('areas') or [], key=lambda item: (item['nr_mode'], item['region'], item['kind'] != CITY_KIND,
                                                                     item['size'], item['area'], item['operator'])):
        values = [row['nr_mode'], row['region'], row['area'], row['kind'], row['size'], row['operator']]
        for campaign in campaigns:
            scored = (row.get('campaigns') or {}).get(campaign) or {}
            values += [_value(scored.get('best')), _value(scored.get('reliable')), scored.get('tests') if scored else None]
        rows.append(values)
    sheet('Areas', header, rows, first=True)
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
    about = [['Saved Scoring', title], ['Regions', ', '.join(request.get('regions') or []) or 'Every Region'],
             ['Connecting roads', 'Each road on its own' if request.get('roads') == 'each' else 'Grouped by Region (Roads, Highway)'],
             *[[f'{mode["nr_mode"]} campaigns', ', '.join(label(value) for value in mode.get('campaigns') or [])] for mode in modes],
             ['Master Grid', f"{grid.get('file_name', '')} ({grid.get('week', '')})" if grid else 'None'],
             ['Points', 'Best Network and Most Reliable points of each area, scaled to the full points when an area has '
                        'tests of one environment only (as every area of the Country Areas).'],
             ['Sites', 'The serving sites of the tests of the latest campaign: NNS sites by the High/Med/Low config of the '
                       'Master Grid, the other sites by eMOCN scenario, and the Keep sites the Master Grid plans for NNS '
                       '(Target Deployment FY) among those not NNS yet.'],
             *[['Warning', warning] for warning in breakdown.get('warnings') or []]]
    sheet('About', ['Item', 'Value'], about).column_dimensions['B'].width = 110
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
