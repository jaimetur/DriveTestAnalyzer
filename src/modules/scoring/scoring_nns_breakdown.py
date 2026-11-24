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
VERSION = 4
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


def classify(frame: pd.DataFrame, lookup: dict[tuple[str, str], dict[str, str]], request: dict[str, Any],
             owners: dict[str, str] | None = None) -> pd.DataFrame:
    """The tests of a CDR type in the Regions of the request, each with its Region (a city's is that of ``owners``,
    see city_regions), area, area kind and size, scenario and serving site (``__nns_*`` columns)."""
    from src.modules.network.master_grid import host_operator

    region = _text(_column(frame, 'Region'))
    city, size, name = _cities(frame)
    if owners:
        region = name.map(owners).where(city & name.ne(''), region).fillna(region).astype(str)
    wanted = {value.casefold() for value in request.get('regions') or []}
    keep = region.ne('') & (region.str.casefold().isin(wanted) if wanted else True)
    mask = keep.to_numpy(dtype=bool)
    frame, region, city, size, name = frame[mask].copy(), region[mask], city[mask], size[mask], name[mask]
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


def add_gaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The GAP to #1 of each area row (in place, in each campaign and scoring: ``leader``, ``gap``, ``gap_region`` and
    ``gap_all``), and the weighted GAPs (``best``, ``reliable``) and points (``best_points``, ``reliable_points``) summed
    per Region and for all the Regions (``region`` empty), per operator."""
    scorings = ('best', 'reliable')
    leaders: dict[tuple, tuple[float, str]] = {}
    tests_region: dict[tuple, int] = {}
    tests_all: dict[tuple, int] = {}
    for row in rows:
        for campaign, values in (row.get('campaigns') or {}).items():
            tests = int(values.get('tests') or 0)
            tests_region[(row['region'], row['operator'], campaign)] = tests_region.get((row['region'], row['operator'], campaign), 0) + tests
            tests_all[(row['operator'], campaign)] = tests_all.get((row['operator'], campaign), 0) + tests
            for scoring in scorings:
                scored = values.get(scoring)
                if not scored or scored.get('points') is None:
                    continue
                key = (row['region'], row['area'], campaign, scoring)
                best = leaders.get(key)
                points = float(scored['points'])
                if best is None or points > best[0] or (points == best[0] and row['operator'].casefold() < best[1].casefold()):
                    leaders[key] = (points, row['operator'])
    totals: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        for campaign, values in (row.get('campaigns') or {}).items():
            tests = int(values.get('tests') or 0)
            for region in (row['region'], ''):
                total = totals.setdefault((region, row['operator']), {
                    'nr_mode': row.get('nr_mode'), 'region': region, 'operator': row['operator'], 'campaigns': {}})
                entry = total['campaigns'].setdefault(campaign, {'tests': 0})
                entry['tests'] += tests
            for scoring in scorings:
                scored = values.get(scoring)
                leader = leaders.get((row['region'], row['area'], campaign, scoring))
                if not scored or scored.get('points') is None or leader is None:
                    continue
                gap = float(scored['points']) - leader[0]
                in_region = tests_region.get((row['region'], row['operator'], campaign)) or 0
                in_all = tests_all.get((row['operator'], campaign)) or 0
                scored.update({'leader': leader[1], 'gap': round(gap, 2),
                               'gap_region': round(gap * tests / in_region, 4) if in_region else None,
                               'gap_all': round(gap * tests / in_all, 4) if in_all else None})
                # The points of the area weighted the same way: summed, the points of the Region or of all the Regions.
                for region, share, weight in ((row['region'], scored['gap_region'], tests / in_region if in_region else None),
                                              ('', scored['gap_all'], tests / in_all if in_all else None)):
                    entry = totals[(region, row['operator'])]['campaigns'][campaign]
                    if share is not None:
                        entry[scoring] = round(entry.get(scoring, 0.0) + share, 4)
                    if weight is not None:
                        entry[f'{scoring}_points'] = round(entry.get(f'{scoring}_points', 0.0) + float(scored['points']) * weight, 4)
    return list(totals.values())


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
    scorings = (('best', 'Best Network'), ('reliable', 'Most Reliable'))
    # Each campaign under a band of its own colour, its Tests first, then its Best Network and its Most Reliable columns.
    palette = ('1F4E79', '0F766E', '7C3AED', 'B45309', 'BE185D', '15803D', '0369A1', '9F1239')

    def tint(color: str, share: float) -> str:
        """``color`` mixed with white (``share`` of white)."""
        channels = [int(color[index:index + 2], 16) for index in (0, 2, 4)]
        return ''.join(f'{round(value + (255 - value) * share):02X}' for value in channels)

    def grouped_sheet(name: str, fixed: list[str], groups: list[tuple[str, list[tuple[str, list[str]]]]],
                      rows: list[list[Any]], first: bool = False):
        """A sheet with three header rows: each group (a campaign) in a band of its colour, its parts (Tests, a scoring)
        in a lighter band, then the names of the columns; the fixed columns span the three rows."""
        worksheet = book.active if first else book.create_sheet()
        worksheet.title = name
        top, middle, bottom = [''] * len(fixed), [''] * len(fixed), list(fixed)
        spans = []
        for index, (group, parts) in enumerate(groups):
            color = palette[index % len(palette)]
            start = len(bottom) + 1
            for part, columns in parts:
                spans.append(('middle', len(bottom) + 1, len(bottom) + len(columns), part, tint(color, .35 if part != 'Tests' else .55)))
                middle += [part] + [''] * (len(columns) - 1)
                bottom += columns
            top += [group] + [''] * (len(bottom) - start)
            spans.append(('top', start, len(bottom), group, color))
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
        for row_name, first_column, last_column, text, color in spans:
            row = 1 if row_name == 'top' else 2
            if last_column > first_column:
                worksheet.merge_cells(start_row=row, start_column=first_column, end_row=row, end_column=last_column)
            cell = worksheet.cell(row=row, column=first_column)
            cell.fill = PatternFill('solid', fgColor=color)
            cell.font = white if row == 1 else dark
            cell.alignment = Alignment(horizontal='center', vertical='center')
            for column in range(first_column, last_column + 1):
                worksheet.cell(row=3, column=column).fill = PatternFill('solid', fgColor=tint(color, .8 if row == 1 else .55))
        for column in range(len(fixed) + 1, len(bottom) + 1):
            cell = worksheet.cell(row=3, column=column)
            cell.font, cell.alignment = Font(bold=True, color='17232D'), Alignment(wrap_text=True, vertical='center', horizontal='center')
        for row in rows:
            worksheet.append(row)
        worksheet.freeze_panes = worksheet.cell(row=4, column=len(fixed) + 1)
        worksheet.auto_filter.ref = f'A3:{get_column_letter(len(bottom))}{max(3, worksheet.max_row)}'
        worksheet.row_dimensions[3].height = 45
        for index, column in enumerate(bottom, start=1):
            width = max([len(str(column)) if index <= len(fixed) else 10] + [len(str(row[index - 1])) for row in rows[:500] if row[index - 1] is not None])
            worksheet.column_dimensions[get_column_letter(index)].width = min(40, max(9, width + 2))
        return worksheet

    area_parts = lambda: [('Tests', ['Tests']), *[(name, ['Points', '#1', 'GAP to #1', 'Weighted GAP to #1 in its Region',
                                                       'Weighted GAP to #1 in all the Regions']) for _key, name in scorings]]
    rows = []
    for row in sorted(breakdown.get('areas') or [], key=lambda item: (item['nr_mode'], item['region'], item['kind'] != CITY_KIND,
                                                                     item['size'], item['area'], item['operator'])):
        values = [row['nr_mode'], row['region'], row['area'], row['kind'], row['size'], row['operator']]
        for campaign in campaigns:
            scored = (row.get('campaigns') or {}).get(campaign) or {}
            values.append(scored.get('tests') if scored else None)
            for key, _name in scorings:
                points = scored.get(key) or {}
                values += [_value(points), points.get('leader'), points.get('gap'), points.get('gap_region'), points.get('gap_all')]
        rows.append(values)
    grouped_sheet('Areas', ['NR Mode', 'Region', 'Area', 'Kind', 'Size', 'Operator'],
                  [(label(campaign), area_parts()) for campaign in campaigns], rows, first=True)
    rows = []
    for row in sorted(breakdown.get('gap_totals') or [], key=lambda item: (item['nr_mode'], item['region'] == '', item['region'],
                                                                           item['operator'])):
        values = [row['nr_mode'], row['region'] or 'All the chosen Regions', row['operator']]
        for campaign in campaigns:
            entry = (row.get('campaigns') or {}).get(campaign) or {}
            values.append(entry.get('tests'))
            for key, _name in scorings:
                values += [entry.get(f'{key}_points'), entry.get(key)]
        rows.append(values)
    grouped_sheet('GAP Totals', ['NR Mode', 'Region', 'Operator'],
                  [(label(campaign), [('Tests', ['Tests']), *[(name, ['Weighted points', 'Weighted GAP to #1'])
                                                              for _key, name in scorings]]) for campaign in campaigns], rows)
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
             ['Cities', 'Each city belongs to the Region that holds most of its tests over the campaigns, with all its '
                        'tests; the connecting roads keep the Region of each test.'],
             ['GAP to #1', 'The points of the operator minus those of the operator with the most points in the area and '
                           'campaign (#1).'],
             ['Weighted GAP to #1', 'The GAP to #1 times the tests of the operator in the area, over its tests in all the '
                                    'areas of the Region (in its Region) or of every chosen Region (in all the Regions). '
                                    'Summed (GAP Totals), they give the GAP of the whole Region or of all the chosen Regions.'],
             ['Weighted points', 'GAP Totals: the points of the areas weighted the same way (by the tests of the operator), '
                                 'summed per Region and for all the chosen Regions.'],
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
