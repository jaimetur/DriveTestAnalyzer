"""NNS Break-down (ticket #195): an optional part of a Saved Scoring with its own campaigns, Regions and roads, the Master
Grid input that gives it the capacity of the NNS sites and the NNS sites planned, and its Excel workbook."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

import src.DriveTestAnalyzer as app_module
from src.modules.core.repository import Repository, local_now_iso
from src.modules.network import master_grid
from src.modules.scoring import saved_scorings
from src.modules.scoring import scoring_nns_breakdown as nb
from src.modules.scoring.scoring_area_summary import normalize_area_summary_request
from tests.support.scoring_cdr_synthetic import ROUTES, SOUTH, synthetic_cdr_frames

CAMPAIGNS = ('2026-Q2', '2026-Q3')
SIZES = {'London': 'Big Cities', 'Birmingham': 'Big Cities', 'Manchester': 'Medium Cities', 'Leeds': 'Medium Cities',
         'Glasgow': 'Big Cities', 'Bristol': 'Small Cities', 'Cardiff': 'Small Cities', 'Edinburgh': 'Medium Cities'}


def _master_grid_file(path: Path, sites: list[tuple]) -> Path:
    """A Master Grid workbook as delivered: notes above the header row of its MasterSiteGridList sheet."""
    book = Workbook()
    book.active.title = 'Notes'
    sheet = book.create_sheet('MasterSiteGridList')
    sheet.append([len(sites)])
    sheet.append([' Change Control'] * 6)
    sheet.append(['Site ID', 'SITE ID + Pairing', 'SiteRef2', 'Operator', 'Latitude', 'Longitude', 'Keep / Remove Status',
                  'High/Med/Low config', 'Target Deployment FY (Running Order)', 'NNS Vendor', 'Region'])
    for site in sites:
        sheet.append(list(site))
    book.save(path)
    return path


def test_master_grid_is_read_below_its_notes_and_matches_the_serving_sites(tmp_path):
    path = _master_grid_file(tmp_path / 'RED_PINK_MasterGridList V1.5 2026_Wk46.xlsx', [
        (14892, 14892, '8395o2', 'VF', 55.47, -2.79, 'Keep', 'High', 'FY28', 'VMo2', 'MORAN_East'),
        ('AAB002', 39180, None, '3UK', 51.1, -1.2, 'Remove', 'Low', None, 'Nokia', 'MORAN_West'),
    ])
    sites, sheet = master_grid.read_sites(path)
    assert sheet == 'MasterSiteGridList' and [site['site_id'] for site in sites] == ['14892', 'AAB002']
    lookup = master_grid.site_lookup(sites)
    # Vodafone by Site ID, 3 by SITE ID + Pairing, O2 by the number of SiteRef2.
    assert lookup[('VF', '14892')]['config'] == 'High' and lookup[('VF', '14892')]['target_fy'] == 'FY28'
    assert lookup[('3UK', '39180')]['keep_remove'] == 'Remove' and lookup[('O2', '8395')]['site_id'] == '14892'
    assert master_grid.host_operator('Vodafone') == 'VF' and master_grid.host_operator('H3G') == '3UK'
    assert master_grid._week_of(path.name) == '2026-W46'
    with pytest.raises(ValueError, match='not a Master Grid'):
        master_grid.read_sites(_master_grid_file_without_columns(tmp_path / 'other.xlsx'))


def _master_grid_file_without_columns(path: Path) -> Path:
    book = Workbook()
    book.active.append(['Site', 'Name'])
    book.save(path)
    return path


def test_nns_request_is_only_said_when_switched_on():
    assert nb.normalize_request(None) is None and nb.normalize_request({'enabled': False}) is None
    assert nb.normalize_request({}) == {'campaigns': ['@latest-4-campaigns'], 'regions': [], 'roads': 'region'}
    assert nb.normalize_request({'campaigns': ['2026-Q3', '2026-q3'], 'regions': ['VMO2 North', 'Vendor A', ''],
                                 'roads': 'each'}) == {'campaigns': ['2026-Q3'], 'regions': ['Vendor A', 'VMO2 North'],
                                                       'roads': 'each'}
    # A request without it keeps the form (and the identity of its Saved Scoring) it had.
    plain = normalize_area_summary_request({'breakdown': 'Region', 'cities': ['London']})
    assert nb.KEY not in plain
    assert normalize_area_summary_request({'breakdown': 'Region', 'cities': ['London'], 'nns_breakdown': {}})[nb.KEY] \
        == {'campaigns': ['@latest-4-campaigns'], 'regions': [], 'roads': 'region'}


def test_tests_are_classified_by_area_size_and_scenario():
    frame = pd.DataFrame({
        'region': ['Vendor A', 'Vendor A', 'Vendor A', 'VMO2 North', 'Vendor B'],
        'G_Level_2': ['City', 'City', 'Connecting Roads', 'Connecting Roads', 'City'],
        'G_Level_3': ['Big Cities', 'Big Cities', 'Highway', 'Roads', 'Small Cities'],
        'G_Level_4': ['London', 'London', 'M1', 'A1', 'Cardiff'],
        'Serving_eMOCN_Scenario': ['NNS', 'S1_CWP', 'NNS', '', 'S0'],
        'Serving_Host_Network': ['Vodafone', 'H3G', 'Vodafone', 'EE', 'Vodafone'],
        'Serving_Site_ID': ['101', '39180', '999', '7', '5'],
    })
    lookup = {('VF', '101'): {'config': 'High', 'keep_remove': 'Keep', 'target_fy': 'FY26', 'site_id': '101'},
              ('3UK', '39180'): {'config': 'Medium', 'keep_remove': 'Keep', 'target_fy': 'FY29', 'site_id': 'AAB002'}}
    classified = nb.classify(frame, lookup, {'regions': ['Vendor A', 'VMO2 North'], 'roads': 'region'})
    assert classified['__nns_area'].tolist() == ['London', 'London', 'Highway – Vendor A', 'Roads – VMO2 North']
    assert classified['__nns_kind'].tolist() == ['City', 'City', 'Road', 'Road']
    assert classified['__nns_size'].tolist() == ['Big Cities', 'Big Cities', 'Highway', 'Roads']
    assert classified['__nns_scenario'].tolist() == ['NNS – High capacity', 'S1_CWP', 'NNS – Not in the Master Grid',
                                                     'No eMOCN scenario']
    each = nb.classify(frame, lookup, {'regions': [], 'roads': 'each'})
    assert each['__nns_area'].tolist() == ['London', 'London', 'M1', 'A1', 'Cardiff']
    counts = nb.site_counts({'data': classified}, lookup)
    # London: one NNS site of High capacity, one 3 site with S1_CWP that the Master Grid plans for FY29.
    assert counts[('Vendor A', 'London')] == {'nns': {'High': 1}, 'scenarios': {'S1_CWP': 1}, 'planned': {'FY29': 1},
                                              'sites': 2, 'not_in_grid': 0}
    assert counts[('Vendor A', 'Highway – Vendor A')]['nns'] == {nb.UNKNOWN_CAPACITY: 1}
    assert counts[('Vendor A', 'Highway – Vendor A')]['not_in_grid'] == 1
    assert nb.scenario_order(['S1', 'No eMOCN scenario', 'S12', 'NNS – Low capacity', 'S2', 'NNS – High capacity']) == [
        'NNS – High capacity', 'NNS – Low capacity', 'S1', 'S2', 'S12', 'No eMOCN scenario']


def _add_cdrs(repository: Repository, tmp_path: Path, frames: dict[str, pd.DataFrame], campaign: str) -> list[int]:
    ids = []
    for kind, frame in frames.items():
        rows = frame[frame['Campaign'] == campaign].reset_index(drop=True)
        name = f'UK_{campaign}_NSA_{kind}.csv'
        source = tmp_path / name
        source.write_text('test source', encoding='utf-8')
        dataset_id, _created = repository.add_dataset(name, str(source), 'admin')
        repository.replace_dataset_rows(dataset_id, rows)
        repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA',
                                          campaign=campaign, row_count=len(rows), column_count=len(rows.columns),
                                          processed_at=local_now_iso())
        repository.replace_cdr_catalogue(dataset_id, vendors=['Nokia'], vendors_only=['Nokia'], regions=['North', 'South'],
                                         cities=sorted(rows['G_Level_4'].dropna().unique()), campaigns=[campaign])
        ids.append(dataset_id)
    return ids


def _with_areas(frame: pd.DataFrame) -> pd.DataFrame:
    place = frame['City']
    return frame.assign(
        Region=place.map(lambda value: 'South' if value in SOUTH else 'North'),
        G_Level_3=place.map(lambda value: 'Roads' if value in ROUTES else SIZES.get(value, 'Small Cities')),
        G_Level_4=place).drop(columns=['City'])


def test_a_saved_scoring_with_the_nns_breakdown_scores_each_area_and_exports_it(client, tmp_path, monkeypatch):
    assert client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False).status_code == 303
    active = app_module.active_workspace
    repository = Repository(active.database_path, global_db_path=app_module.repository.db_path,
                            workspace_registry_db_path=app_module.workspace_registry.registry_path)
    repository.initialize()
    data = {kind: _with_areas(frame) for kind, frame in synthetic_cdr_frames(campaigns=CAMPAIGNS, repeats=1).items()}
    ids = [*_add_cdrs(repository, tmp_path, data, '2026-Q2'), *_add_cdrs(repository, tmp_path, data, '2026-Q3')]
    # The Master Grid: the Vodafone sites of London (NNS in the CDRs) with High config, one planned for FY28.
    london = sorted({str(site) for site in data['data'].loc[(data['data']['G_Level_4'] == 'London')
                                                             & (data['data']['Serving_Host_Network'] == 'Vodafone'),
                                                             'Serving_Site_ID']})
    grid_path = _master_grid_file(tmp_path / 'MasterGridList 2026_Wk46.xlsx', [
        *((site, site, None, 'VF', 51.5, -0.1, 'Keep', 'High', 'FY28', 'Ericsson', 'London') for site in london)])
    grid_id, _created = repository.add_dataset(grid_path.name, str(grid_path), 'admin')
    repository.update_dataset_profile(grid_id, dataset_kind=master_grid.KIND, status='processing')
    assert master_grid.process_delivery(repository, grid_id, grid_path)['sites'] == len(london)
    assert master_grid.latest_dataset(repository)['week'] == '2026-W46'

    area_summary = {'breakdown': 'Region', 'cities': ['London'], 'country_areas': False, 'trends': False,
                    'nns_breakdown': {'campaigns': list(CAMPAIGNS), 'regions': ['South'], 'roads': 'region'}}
    saved, _ready = saved_scorings.save_saved_scoring(repository, ids, ['Operator', 'Campaign'], 'NSA', username='admin',
                                                      baseline_operator='EE', area_summary=area_summary)
    done = saved_scorings.calculate_saved_scoring(repository, saved['id'])
    assert done['status'] == 'completed', done.get('error')
    breakdown = done['result'][nb.KEY]
    assert breakdown['modes'] == [{'nr_mode': 'NSA', 'campaigns': list(CAMPAIGNS), 'latest_campaign': '2026-Q3'}]
    areas = {(row['area'], row['operator']): row for row in breakdown['areas']}
    # Only the South: its cities and its Roads together.
    assert {row['region'] for row in breakdown['areas']} == {'South'}
    assert {area for area, _operator in areas} == {'London', 'Bristol', 'Cardiff', 'Roads – South'}
    london_ee = areas[('London', 'EE')]
    assert london_ee['kind'] == 'City' and london_ee['size'] == 'Big Cities' and set(london_ee['campaigns']) == set(CAMPAIGNS)
    scored = london_ee['campaigns']['2026-Q3']
    assert 0 < scored['best']['points'] <= scored['best']['max_points'] and scored['tests'] > 0
    assert scored['reliable'] is None or scored['reliable']['points'] <= scored['reliable']['max_points']
    sites = {row['area']: row for row in breakdown['sites']}
    assert sites['London']['nns'].get('High', 0) >= 1
    scenarios = {(row['size'], row['scenario']) for row in breakdown['scenarios']}
    assert ('Big Cities', 'NNS – High capacity') in scenarios and all(row['campaign'] == '2026-Q3' for row in breakdown['scenarios'])
    assert breakdown['scenario_order'][0] == 'NNS – High capacity'
    # The GAP to #1 of each area: 0 for its leader, and the weighted GAPs summed per Region in its totals.
    latest = [row['campaigns']['2026-Q3']['best'] for row in breakdown['areas'] if row['area'] == 'London']
    assert min(item['gap'] for item in latest) < 0 and max(item['gap'] for item in latest) == 0
    assert {item['leader'] for item in latest} == {next(item['leader'] for item in latest)}
    south = {row['operator']: row for row in breakdown['gap_totals'] if row['region'] == 'South'}
    for operator, total in south.items():
        weighted = [row['campaigns']['2026-Q3']['best']['gap_region'] for row in breakdown['areas']
                    if row['operator'] == operator and '2026-Q3' in row['campaigns'] and row['campaigns']['2026-Q3']['best']]
        assert total['campaigns']['2026-Q3']['best'] == pytest.approx(sum(weighted), abs=1e-3)

    # The same selection without it is another Saved Scoring, whose result has none.
    plain, _ready = saved_scorings.save_saved_scoring(repository, ids, ['Operator', 'Campaign'], 'NSA', username='admin',
                                                      baseline_operator='EE',
                                                      area_summary={**area_summary, 'nns_breakdown': None})
    assert plain['id'] != saved['id']

    response = client.get(f"/scoring/saved-scorings/{saved['id']}/export/nns")
    assert response.status_code == 200, response.text
    book = load_workbook(BytesIO(response.content))
    assert book.sheetnames == ['Areas', 'GAP Totals', 'Sites', 'Scenarios', 'About']
    header = [cell.value for cell in book['Areas'][1]]
    assert header[:6] == ['NR Mode', 'Region', 'Area', 'Kind', 'Size', 'Operator'] and sum(str(name).endswith(' Best Network') for name in header) == 2
    assert sum(str(name).endswith('Most Reliable weighted GAP in its Region') for name in header) == 2
    assert [cell.value for cell in book['GAP Totals'][1]][:3] == ['NR Mode', 'Region', 'Operator']
    assert 'NNS High' in [cell.value for cell in book['Sites'][1]]
    assert client.get(f"/scoring/saved-scorings/{plain['id']}/export/nns").status_code in {404, 409}


def test_each_city_belongs_to_the_region_with_most_of_its_tests():
    """A city whose tests fall in two Regions (a wrong position, or streets across a Region border) is in one Region,
    with all its tests; the roads keep the Region of each test."""
    frame = pd.DataFrame({
        'Region': ['Vendor A'] * 5 + ['VMO2 South'] * 2 + ['VMO2 South', 'Vendor A'],
        'G_Level_2': ['City'] * 7 + ['Road', 'Road'],
        'G_Level_3': ['Medium Cities'] * 7 + ['Roads', 'Roads'],
        'G_Level_4': ['Reading'] * 7 + ['M4', 'M4'],
        'Serving_eMOCN_Scenario': ['S0'] * 9, 'Serving_Host_Network': ['Vodafone'] * 9, 'Serving_Site_ID': ['1'] * 9,
    })
    owners = nb.city_regions([frame])
    assert owners == {'Reading': 'Vendor A'}
    classified = nb.classify(frame, {}, {'regions': ['Vendor A', 'VMO2 South'], 'roads': 'region'}, owners)
    cities = classified[classified['__nns_kind'] == nb.CITY_KIND]
    assert set(cities['__nns_region']) == {'Vendor A'} and len(cities) == 7
    roads = classified[classified['__nns_kind'] == nb.ROAD_KIND]
    assert sorted(roads['__nns_area']) == ['Roads – VMO2 South', 'Roads – Vendor A']
    # Only VMO2 South chosen: Reading is not there any more.
    south = nb.classify(frame, {}, {'regions': ['VMO2 South'], 'roads': 'region'}, owners)
    assert set(south['__nns_kind']) == {nb.ROAD_KIND}


def test_the_gap_to_number_one_is_weighted_by_the_tests_of_each_area():
    def row(region, area, operator, points, tests):
        return {'nr_mode': 'NSA', 'region': region, 'area': area, 'operator': operator,
                'campaigns': {'Q3': {'best': {'points': points}, 'reliable': None, 'tests': tests}}}
    rows = [row('Vendor A', 'Reading', 'EE', 960.0, 100), row('Vendor A', 'Reading', 'VF', 980.0, 100),
            row('Vendor A', 'Luton', 'EE', 900.0, 300), row('Vendor A', 'Luton', 'VF', 850.0, 300),
            row('VMO2 South', 'Oxford', 'VF', 800.0, 400), row('VMO2 South', 'Oxford', 'EE', 820.0, 400)]
    totals = {(item['region'], item['operator']): item['campaigns']['Q3'] for item in nb.add_gaps(rows)}
    reading_ee = rows[0]['campaigns']['Q3']['best']
    assert reading_ee['leader'] == 'VF' and reading_ee['gap'] == -20.0
    assert reading_ee['gap_region'] == pytest.approx(-20 * 100 / 400) and reading_ee['gap_all'] == pytest.approx(-20 * 100 / 800)
    assert rows[1]['campaigns']['Q3']['best']['gap'] == 0 and rows[1]['campaigns']['Q3']['best']['leader'] == 'VF'
    # Vendor A: EE loses 5 in Reading, VF 37.5 in Luton; all Regions: VF also loses 10 in Oxford.
    assert totals[('Vendor A', 'EE')]['best'] == pytest.approx(-5.0) and totals[('Vendor A', 'VF')]['best'] == pytest.approx(-37.5)
    assert totals[('', 'VF')]['best'] == pytest.approx(-50 * 300 / 800 - 20 * 400 / 800)
    assert totals[('', 'EE')]['tests'] == 800 and 'reliable' not in totals[('', 'EE')]
