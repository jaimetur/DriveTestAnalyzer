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
    # Each Region against its #1 as Country Areas scores it: the weighted GAPs of its areas plus the adjustment are its
    # real GAP, the weights of its areas share its points, and the projection has the areas of the latest campaign.
    south = {row['operator']: row['campaigns']['2026-Q3']['best'] for row in breakdown['gap_totals'] if row['region'] == 'South'}
    assert {total['leader'] for total in south.values()} == {next(iter(south.values()))['leader']}
    for operator, total in south.items():
        assert total['weighted_gap'] + total['adjustment'] == pytest.approx(total['gap'], abs=1e-2)
        assert 0 < total['points'] <= 1000 and 0 < total['weighted_points'] <= 1000
        weights = [row['campaigns']['2026-Q3']['best']['weight_region'] for row in breakdown['areas']
                   if row['operator'] == operator and row['campaigns'].get('2026-Q3', {}).get('best')]
        assert sum(weights) == pytest.approx(1, abs=0.02)
    assert {row['operator'] for row in breakdown['projection']} == {row['operator'] for row in breakdown['areas']}
    assert all(row['campaign'] == '2026-Q3' and row['tests'] >= row['nns_tests'] for row in breakdown['projection'])

    # The same selection without it is another Saved Scoring, whose result has none.
    plain, _ready = saved_scorings.save_saved_scoring(repository, ids, ['Operator', 'Campaign'], 'NSA', username='admin',
                                                      baseline_operator='EE',
                                                      area_summary={**area_summary, 'nns_breakdown': None})
    assert plain['id'] != saved['id']

    response = client.get(f"/scoring/saved-scorings/{saved['id']}/export/nns")
    assert response.status_code == 200, response.text
    assert response.headers['content-disposition'].endswith('-nns-breakdown-best_network.xlsx"')
    reliable = client.get(f"/scoring/saved-scorings/{saved['id']}/export/nns", params={'scoring': 'most_reliable'})
    assert reliable.headers['content-disposition'].endswith('-nns-breakdown-most_reliable.xlsx"')
    book = load_workbook(BytesIO(response.content))
    assert book.sheetnames == ['Areas', 'GAP Totals', 'Sites', 'Scenarios', 'Projection', 'About']
    # Three header rows: each campaign in a band of its own colour, its Tests then the scoring chosen in the tab.
    areas = book['Areas']
    bands, parts, header = ([cell.value for cell in areas[row]] for row in (1, 2, 3))
    assert header[:6] == ['NR Mode', 'Region', 'Area', 'Kind', 'Size', 'Operator'] and [name for name in bands[6:] if name] == ['26-Q2', '26-Q3']
    assert [name for name in parts[6:] if name] == ['Tests', 'Best Network'] * 2
    # Each export holds only its scoring (Best Network or Most Reliable) in every sheet.
    reliable_book = load_workbook(BytesIO(reliable.content))
    assert [name for name in [cell.value for cell in reliable_book['Areas'][2]][6:] if name] == ['Tests', 'Most Reliable'] * 2
    assert [cell.value for cell in book['Scenarios'][1]][5:] == ['Best Network', 'Tests']
    assert [cell.value for cell in reliable_book['Scenarios'][1]][5:] == ['Most Reliable', 'Tests']
    assert {row[6] for row in book['Projection'].iter_rows(min_row=4, values_only=True)} == {'Best Network'}
    assert {row[6] for row in reliable_book['Projection'].iter_rows(min_row=4, values_only=True)} == {'Most Reliable'}
    assert areas.cell(row=4, column=8).value != reliable_book['Areas'].cell(row=4, column=8).value
    both = client.get(f"/scoring/saved-scorings/{saved['id']}/export/nns", params={'scoring': 'both'})
    assert both.headers['content-disposition'].endswith('-nns-breakdown-both.xlsx"')
    both_book = load_workbook(BytesIO(both.content))
    assert [name for name in [cell.value for cell in both_book['Areas'][2]][6:] if name] == ['Tests', 'Best Network', 'Most Reliable'] * 2
    assert [cell.value for cell in both_book['Scenarios'][1]][5:] == ['Best Network', 'Most Reliable', 'Tests']
    assert client.get(f"/scoring/saved-scorings/{saved['id']}/export/scoring", params={'scoring': 'both'}).status_code == 400
    assert header[6:13] == ['Tests', 'Points', '#1 of the area', 'GAP to #1 of the area', 'Weight in its Region',
                            'Weighted GAP to #1 of the Region', 'Weighted GAP to #1 of all the Regions']
    # Each Region first (its own scoring), then its areas, then its adjustment.
    kinds = [row[3] for row in areas.iter_rows(min_row=4, values_only=True)]
    assert kinds[0] == 'Region' and 'Adjustment' in kinds and kinds.index('Adjustment') > kinds.index('City')
    assert areas.cell(row=1, column=7).fill.fgColor.rgb != areas.cell(row=1, column=14).fill.fgColor.rgb
    assert areas.freeze_panes == 'G4' and areas.cell(row=4, column=7).value is not None
    totals = book['GAP Totals']
    assert [cell.value for cell in totals[3]][:10] == ['NR Mode', 'Region', 'Operator', 'Tests', 'Points', '#1', 'GAP to #1',
                                                      'Weighted GAP of its areas', 'Adjustment', 'Weighted points of its areas']
    assert [cell.value for cell in book['Projection'][3]][:13] == [
        'NR Mode', 'Region', 'Area', 'Kind', 'Size', 'Operator', 'Scoring', 'Serving sites', 'NNS sites', 'Tests', 'NNS tests',
        'Points', 'NNS points']
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


def test_each_area_weighs_in_its_region_as_the_methodology_and_the_adjustment_closes_the_gap():
    """Each area adds its points in its environment and category times its share of the tests of the Region there: the
    weighted GAPs to the #1 of the Region plus the adjustment are the real GAP of the Region."""
    def row(area, operator):
        return {'nr_mode': 'NSA', 'region': 'Vendor A', 'area': area, 'operator': operator,
                'campaigns': {'Q3': {'best': {'points': 900.0}, 'reliable': None, 'tests': 100}}}
    rows = [row('Reading', 'EE'), row('Reading', 'VF'), row('Roads', 'EE'), row('Roads', 'VF')]
    city, road = 'Drive - City', 'Drive - Connecting Roads'
    # Points in each environment and category (Data 650 x 0.65 of City...), unscaled.
    area_points = {'best': {
        ('Q3', 'EE', 'Vendor A', 'Reading', city, 'Data'): (400.0, 422.5), ('Q3', 'EE', 'Vendor A', 'Reading', city, 'Voice'): (200.0, 227.5),
        ('Q3', 'VF', 'Vendor A', 'Reading', city, 'Data'): (410.0, 422.5), ('Q3', 'VF', 'Vendor A', 'Reading', city, 'Voice'): (210.0, 227.5),
        ('Q3', 'EE', 'Vendor A', 'Roads', road, 'Data'): (200.0, 227.5), ('Q3', 'EE', 'Vendor A', 'Roads', road, 'Voice'): (100.0, 122.5),
        ('Q3', 'VF', 'Vendor A', 'Roads', road, 'Data'): (150.0, 227.5), ('Q3', 'VF', 'Vendor A', 'Roads', road, 'Voice'): (90.0, 122.5)}}
    area_tests = {(campaign, operator, region, area, environment, kind): 10
                  for (campaign, operator, region, area, environment, _category) in area_points['best']
                  for kind in ('data', 'voice')}
    region_points = {'best': {('Q3', 'EE', 'Vendor A'): (905.0, 1000.0), ('Q3', 'VF', 'Vendor A'): (857.0, 1000.0)}}
    all_points = {'best': {('Q3', 'EE'): (905.0, 1000.0), ('Q3', 'VF'): (857.0, 1000.0)}}
    totals = nb.reconcile(rows, area_points, area_tests, region_points, all_points, {'Data': {'data'}, 'Voice': {'voice'}}, 'NSA')
    reading_vf = rows[1]['campaigns']['Q3']['best']
    # Reading is the whole City environment of the Region: it adds all its City points; EE (#1 of the Region) adds 600.
    assert reading_vf['points_region'] == pytest.approx(620) and reading_vf['gap_region'] == pytest.approx(20)
    assert reading_vf['weight_region'] == pytest.approx(0.65) and reading_vf['leader_region'] == 'EE'
    region = {(item['region'], item['operator']): item['campaigns']['Q3']['best'] for item in totals}
    vf = region[('Vendor A', 'VF')]
    assert vf['leader'] == 'EE' and vf['gap'] == pytest.approx(-48)
    assert vf['weighted_gap'] == pytest.approx(20 - 60) and vf['weighted_points'] == pytest.approx(860)
    assert vf['weighted_gap'] + vf['adjustment'] == pytest.approx(vf['gap'])
    assert region[('', 'VF')]['gap'] == pytest.approx(-48) and region[('Vendor A', 'EE')]['gap'] == 0


def test_the_projection_adds_each_year_the_rise_of_the_nns_share_times_the_nns_advantage():
    row = {'sites': 10, 'nns_sites': 2, 'tests': 100, 'nns_tests': 30, 'planned_sites': {'FY27': 1, 'FY28': 2},
           'planned_tests': {'FY27': 10, 'FY28': 20}, 'best': {'points': 950.0, 'max_points': 1000.0, 'nns_points': 970.0}}
    lines = nb.projection(row, ['FY26', 'FY27', 'FY28'], 0.5, reference=False)['best']
    assert lines['sites_share'] == [0.2, 0.3, 0.5] and lines['sites'] == [950.0, 952.0, 956.0]
    assert lines['tests_share'] == [0.3, 0.4, 0.6] and lines['tests'] == [950.0, 952.0, 956.0]
    # The reference grows 0.5 % a year from the first year on, as in the projection of the ticket.
    assert lines['reference'] == [950.0, 954.75, 959.52]
    assert nb.projection(row, ['FY26', 'FY27'], 0.5, reference=True)['best']['sites'] == [950.0, 950.0]

def test_the_master_grid_matches_the_sites_named_by_the_number_of_the_site_they_pair_with():
    """VodafoneThree and shared sites are often named in the CDRs by the number of the site they pair with."""
    sites = [{'operator': 'VF', 'site_id': '32961', 'site_pairing': '18567', 'site_ref2': '18567vf', 'config': 'High'},
             {'operator': '3UK', 'site_id': 'AAB002', 'site_pairing': '50419', 'site_ref2': '', 'config': 'Low'},
             {'operator': 'VF', 'site_id': '10020', 'site_pairing': '10020', 'site_ref2': '10020vf', 'config': 'Med'}]
    lookup = master_grid.site_lookup(sites)
    assert lookup[('VF', '32961')]['config'] == 'High' and lookup[('VF', '18567')]['site_id'] == '32961'
    assert lookup[('VF', '50419')]['config'] == 'Low' and lookup[('3UK', '50419')]['config'] == 'Low'
    assert lookup[('O2', '10020')]['config'] == 'Medium'


def test_the_projection_of_a_region_adds_what_its_areas_add_weighted_as_the_methodology():
    def area(name, operator, points, weight):
        return {'nr_mode': 'NSA', 'region': 'Vendor A', 'area': name, 'operator': operator,
                'campaigns': {'Q3': {'best': {'points': points, 'weight_region': weight, 'weight_all': weight}, 'tests': 100}}}
    def projected(name, operator, points, nns_points):
        return {'nr_mode': 'NSA', 'region': 'Vendor A', 'area': name, 'operator': operator, 'sites': 10, 'nns_sites': 0,
                'tests': 100, 'nns_tests': 50, 'planned_sites': {'FY27': 5}, 'planned_tests': {'FY27': 50},
                'best': {'points': points, 'max_points': 1000.0, 'nns_points': nns_points}}
    breakdown = {
        'reference_operator': 'EE', 'modes': [{'nr_mode': 'NSA', 'latest_campaign': 'Q3'}],
        'areas': [area('Reading', 'VF', 900.0, 0.6), area('Roads', 'VF', 800.0, 0.4), area('Reading', 'EE', 950.0, 0.6)],
        'gap_totals': [{'nr_mode': 'NSA', 'region': 'Vendor A', 'operator': operator, 'campaigns': {'Q3': {'best': {'points': points, 'max_points': 1000.0}}}}
                       for operator, points in (('VF', 860.0), ('EE', 940.0))],
        'projection': [projected('Reading', 'VF', 900.0, 940.0), projected('Roads', 'VF', 800.0, 900.0), projected('Reading', 'EE', 950.0, 960.0)]}
    rows = {(row['region'], row['operator']): row for row in nb.region_projection(breakdown, ['FY26', 'FY27'], 1.0)}
    vf = rows[('Vendor A', 'VF')]['lines']
    # Half of the sites become NNS in FY27: Reading adds 0.6 x 0.5 x 40, the roads 0.4 x 0.5 x 100.
    assert vf['sites'] == [860.0, 860.0 + 0.6 * 20 + 0.4 * 50] and vf['sites_share'] == [0.0, 0.5]
    assert rows[('Vendor A', 'EE')]['lines']['sites'] == [940.0, 949.4]
