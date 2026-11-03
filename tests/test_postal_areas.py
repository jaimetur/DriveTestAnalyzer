"""Postal Codes of the Points Lost Map: their areas, worked out from postal code points, and the map of a Saved Filter."""
from __future__ import annotations

import io
import json
import random
import sqlite3
import zipfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from pptx import Presentation

from src.modules import map_areas, postal_areas, saved_filters
from src.modules import scoring_points_loss as points_loss
from src.modules.map_areas import AreaIndex
from src.modules.repository import Repository
from src.modules.scoring import calculate_points_loss, calculate_scoring
from src.modules.scoring_exports import export_scoring_powerpoint, export_scoring_report
from src.modules.scoring_export_panels import default_export_panels
from src.modules.scoring_points_loss import POSTAL, map_background, map_boundaries
from src.modules.scoring_reports import default_scenario
from src.modules.scoring_views import build_scoring_views
from tests.scoring_fixtures import scoring_configuration
from tests.test_scoring_exports import TEMPLATE

PLACES = {'Leeds': (53.80, -1.55), 'Manchester': (53.48, -2.24), 'London': (51.51, -0.13)}
# One square postal code around each city; nothing covers the tests of the road.
AREAS = {f'{code} · {city}': [[[lon - .1, lat - .1], [lon + .1, lat - .1], [lon + .1, lat + .1], [lon - .1, lat + .1], [lon - .1, lat - .1]]]
         for code, (city, (lat, lon)) in zip(('LS1', 'M1', 'E1'), PLACES.items())}
LAND = [[[-9.0, 49.0], [2.0, 49.0], [2.0, 60.0], [-9.0, 60.0], [-9.0, 49.0]]]


class FakeRepository:
    """The workspace database calls the layers use, on a SQLite file."""

    def __init__(self, path):
        self.db_path = path
        self.logs = []

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def try_add_log(self, username, action, details):
        self.logs.append((username, action, json.loads(details)))


@pytest.fixture()
def fake_repository(tmp_path):
    return FakeRepository(tmp_path / 'workspace.db')


def _geonames_zip(alpha2='ES', rows=None):
    rows = rows if rows is not None else [
        ('28001', 'Madrid', 40.42, -3.68), ('28040', 'Moncloa', 40.44, -3.72), ('08001', 'Barcelona', 41.38, 2.17),
    ]
    text = '\n'.join('\t'.join([alpha2, code, place, '', '', '', '', '', '', str(latitude), str(longitude), '4'])
                     for code, place, latitude, longitude in rows)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(f'{alpha2}.txt', text)
        archive.writestr('readme.txt', 'GeoNames')
    return buffer.getvalue()


def _land():
    from shapely.geometry import Polygon
    return Polygon(LAND[0])


# -- the areas ------------------------------------------------------------------------------------
def test_geonames_rows_are_read_without_the_ones_without_coordinates():
    content = _geonames_zip(rows=[('28001', 'Madrid', 40.42, -3.68), ('28002', 'Nowhere', 0, 0), ('', 'No code', 40.0, -3.0)])
    assert postal_areas.read_geonames(content, 'ES') == [('28001', 'Madrid', 40.42, -3.68)]
    with pytest.raises(ValueError, match='has no ES.txt'):
        postal_areas.read_geonames(_geonames_zip('FR'), 'ES')
    with pytest.raises(ValueError, match='not a ZIP'):
        postal_areas.read_geonames(b'<html>not found</html>', 'ES')


def test_each_code_takes_the_land_closest_to_its_points():
    points = [('A1', 'North', 55.0, -3.0), ('A1', 'North East', 55.0, -2.0), ('B2', 'South', 51.0, -2.5)]
    boundaries = postal_areas.postal_boundaries(points, _land())
    assert set(boundaries) == {'A1 · North', 'B2 · South'}
    index = AreaIndex({'GBR': ('postal code', lambda: boundaries, True)})
    placed = index.names_of(pd.Series([54.0, 54.0, 52.0, 48.0]), pd.Series([-2.6, -2.1, -2.5, -2.5]))
    # Closer to any point of A1, closer to B2, and off the land of the country.
    assert placed.tolist()[:3] == ['A1 · North', 'A1 · North', 'B2 · South'] and pd.isna(placed.iloc[3])


def test_codes_that_only_share_a_point_are_one_area_and_the_others_leave_it():
    # The centre of a city: M1 and M2 have no other point; M9 also has its own.
    points = [('M1', 'Manchester', 53.48, -2.24), ('M2', 'Manchester', 53.48, -2.24), ('M9', 'Manchester', 53.48, -2.24),
              ('M9', 'Blackley', 53.52, -2.21), ('S1', 'Sheffield', 53.38, -1.47)]
    boundaries = postal_areas.postal_boundaries(points, _land())
    assert set(boundaries) == {'M1, M2 · Manchester', 'M9 · Blackley', 'S1 · Sheffield'}


def test_the_name_of_an_area_shows_some_of_many_codes_in_the_order_people_read_them():
    points = [(code, 'London', 51.5, -.12) for code in ('EC10', 'EC2', 'EC1', 'WC1')] + [('N1', 'Islington', 51.54, -.1)]
    assert set(postal_areas.postal_boundaries(points, _land())) == {'EC1, EC2 +2 · London', 'N1 · Islington'}


def test_a_country_with_more_codes_than_a_layer_holds_groups_them_by_their_first_characters(monkeypatch):
    monkeypatch.setattr(postal_areas, 'MAX_UNITS', 2)
    points = [('1001', 'A', 1.0, 1.0), ('1002', 'B', 1.1, 1.0), ('2001', 'C', 2.0, 1.0)]
    coarser, level = postal_areas.coarser_codes(points)
    assert [point[0] for point in coarser] == ['100', '100', '200'] and level == 'First 3 characters of the postal code'
    assert postal_areas.coarser_codes(points[:2]) == (points[:2], 'Postal code')


def test_the_postal_codes_shipped_cover_the_uk():
    layer = postal_areas.bundled_layers()['GBR']
    assert layer['license'] == 'Creative Commons Attribution 4.0' and 'GeoNames' in layer['attribution']
    rings = postal_areas.bundled_rings('GBR')
    assert len(rings) == layer['unit_count'] > 2000
    index = AreaIndex({'GBR': ('postal code', lambda: rings, True)})
    # Newbury, Leeds and Belfast (Northern Ireland is in the GeoNames file).
    placed = index.names_of(pd.Series([51.40, 53.80, 54.60]), pd.Series([-1.32, -1.55, -5.93]))
    assert placed[0].startswith('RG14') and placed[1].startswith('LS') and placed[2].startswith('BT')
    # Worked out from the full postcodes: the districts of the centre of a city are areas of their own.
    assert {'M1 · Manchester', 'M4 · Manchester', 'EC2R · London', 'WC2N · London'} <= set(rings)
    assert 'Royal Mail' in layer['attribution']


def _builder():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / 'tools' / 'build_postal_layer.py'
    specification = importlib.util.spec_from_file_location('build_postal_layer', path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_a_file_of_full_codes_is_read_and_each_code_counts_for_its_district():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('GB_full.txt', 'GB\tM1 1AA\tManchester\t\t\t\t\t\t\t53.4801\t-2.2301\t6\n')
    assert postal_areas.read_geonames(buffer.getvalue(), 'GB') == [('M1 1AA', 'Manchester', 53.4801, -2.2301)]
    # In one cell of the grid, the district with most codes keeps it, at the middle of its codes.
    points = [('M1 1AA', 'Manchester', 53.48012, -2.23012), ('M1 1AB', 'Manchester', 53.48018, -2.23018),
              ('M4 1AA', 'Ancoats', 53.48015, -2.23015)]
    assert _builder().district_points(points) == [('M1', 'Manchester', 53.48015, -2.23015)]


def test_a_stray_code_draws_no_island_but_a_district_keeps_its_last_cell():
    step = .001
    grid = [('A%d 1AA' % 1, 'Town', 50 + row * step + .0002, 1 + column * step + .0002) for row in range(3) for column in range(3)]
    # One code of B in the middle of A, with another cell of B far away: the middle joins A.
    stray = [point for point in grid if not (abs(point[2] - 50.0012) < 1e-9 and abs(point[3] - 1.0012) < 1e-9)]
    points = [*stray, ('B1 1AA', 'Village', 50.0012, 1.0012), ('B1 1AB', 'Village', 52.0, 3.0)]
    found = _builder().district_points(points)
    assert sum(item[0] == 'A1' for item in found) == 9 and [item[0] for item in found if item[0] == 'B1'] == ['B1']
    # Without the other cell, it is the last one of B: it stays.
    found = _builder().district_points([*stray, ('B1 1AA', 'Village', 50.0012, 1.0012)])
    assert sum(item[0] == 'B1' for item in found) == 1


def test_the_place_of_an_area_is_the_one_with_most_of_its_points():
    points = [('RG14', 'Newbury', 51.40, -1.32), ('RG14', 'Newbury', 51.41, -1.33), ('RG14', 'Speen', 51.405, -1.325),
              ('S1', 'Sheffield', 53.38, -1.47)]
    assert set(postal_areas.postal_boundaries(points, _land())) == {'RG14 · Newbury', 'S1 · Sheffield'}


# -- the layers of a workspace --------------------------------------------------------------------
def test_download_saves_a_layer_apart_from_the_map_areas(fake_repository, monkeypatch):
    requested = []
    monkeypatch.setattr(postal_areas, '_fetch', lambda url, timeout: requested.append(url) or _geonames_zip())
    layer = postal_areas.download_postal_layer(fake_repository, 'esp', 'super')
    assert requested == ['https://download.geonames.org/export/zip/ES.zip']
    assert layer['country_code'] == 'ESP' and layer['origin'] == 'GeoNames' and layer['license'] == postal_areas.GEONAMES_LICENSE
    assert layer['unit_count'] == 3
    assert map_areas.list_layers(fake_repository) == []
    index = postal_areas.postal_index(fake_repository)
    assert 'GBR' in index.codes and 'ESP' in index.codes
    assert index.names_of(pd.Series([41.38]), pd.Series([2.17])).tolist() == ['08001 · Barcelona']
    assert postal_areas.delete_postal_layer(fake_repository, layer['id'])
    assert postal_areas.list_postal_layers(fake_repository) == []


def test_a_country_geonames_does_not_have_says_so(fake_repository, monkeypatch):
    import urllib.error

    def missing(url, timeout):
        raise urllib.error.HTTPError(url, 404, 'Not Found', None, None)
    monkeypatch.setattr(postal_areas, '_fetch', missing)
    with pytest.raises(ValueError, match='GeoNames has no postal codes for Spain'):
        postal_areas.download_postal_layer(fake_repository, 'ESP', 'super')
    with pytest.raises(ValueError, match='alpha-3'):
        postal_areas.download_postal_layer(fake_repository, 'XXX', 'super')


def test_a_calculation_downloads_the_postal_codes_its_countries_lack(fake_repository, monkeypatch):
    monkeypatch.setattr(postal_areas, 'countries_of_tests', lambda repository, sources: ['GBR', 'ESP', 'FRA'])
    fetched = []

    def fetch(url, timeout):
        fetched.append(url)
        if url.endswith('FR.zip'):
            raise OSError('no route to host')
        return _geonames_zip()
    monkeypatch.setattr(postal_areas, '_fetch', fetch)
    missing = postal_areas.ensure_postal_layers(fake_repository, [], 'super')
    # The UK has them shipped; France could not be downloaded, which the map tells, and App Events records both.
    assert [url.rsplit('/', 1)[1] for url in fetched] == ['ES.zip', 'FR.zip']
    assert [item['name'] for item in missing] == ['France'] and 'no route to host' in missing[0]['error']
    assert [(action, details['country']) for _user, action, details in fake_repository.logs] == [
        ('postal_areas_download', 'ESP'), ('postal_areas_download_failed', 'FRA')]
    # Downloaded once.
    fetched.clear()
    postal_areas.ensure_postal_layers(fake_repository, [], 'super')
    assert fetched == [url for url in fetched if url.endswith('FR.zip')]


def test_layers_round_trip_in_their_document(fake_repository, tmp_path):
    postal_areas.save_layer(fake_repository, country_code='ESP', level='Postal code', level_label='postal code', origin='GeoNames',
                            source='test', license_text='CC BY 4.0', attribution='GeoNames', boundaries={'28001': LAND},
                            username='super', table=postal_areas.TABLE)
    document = map_areas.layers_document(fake_repository, table=postal_areas.TABLE)
    assert document['layers'][0]['boundaries'] == {'28001': LAND}
    other = FakeRepository(tmp_path / 'other.db')
    assert map_areas.import_layers_document(other, document, 'super', table=postal_areas.TABLE) == 1
    assert [layer['country_code'] for layer in postal_areas.list_postal_layers(other)] == ['ESP']
    assert map_areas.list_layers(other) == []


# -- the map --------------------------------------------------------------------------------------
def _frames():
    random.seed(7)
    rows = []
    for operator in ('EE', 'Vodafone UK'):
        for city, (latitude, longitude) in PLACES.items():
            for index in range(40):
                failed = operator != 'EE' and ((city == 'Leeds' and index < 8) or (city == 'Manchester' and index < 2))
                rows.append({'Campaign': '2026-Q2', 'Operator': operator, 'G_Level_1': 'Drive', 'G_Level_2': 'City',
                             'City': city, 'Session_Type': 'CALL', 'Call_Status': 'Failed' if failed else 'Completed',
                             'Call_Start_Latitude_A': latitude + random.uniform(-.02, .02),
                             'Call_Start_Longitude_A': longitude + random.uniform(-.02, .02)})
    return {'voice': pd.DataFrame(rows)}


def _index():
    return AreaIndex({'GBR': ('postal code', lambda: AREAS, True)})


def _postal_result():
    result = calculate_scoring(_frames(), ['Operator'], configuration=scoring_configuration())
    result['points_loss'] = calculate_points_loss(_frames(), ['Operator'], configuration=scoring_configuration(),
                                                  postal_areas=_index())
    job = {'id': 1, 'levels': ['Operator'], 'baseline_operator': 'EE', 'configuration': result['configuration'],
           'campaigns': ['2026-Q2']}
    return job, result


def test_a_map_without_postal_codes_is_the_same_map():
    configuration = scoring_configuration()
    plain = calculate_points_loss(_frames(), ['Operator'], configuration=configuration)
    with_postal = calculate_points_loss(_frames(), ['Operator'], configuration=configuration, postal_areas=_index())
    assert not any(POSTAL in (entry.get('areas') or {}) for entry in plain['shares'])
    assert 'boundaries' not in plain and 'postal_background' not in plain
    # The Postal Codes only add their own shares: every other figure of the map stays.
    assert [{**entry, 'areas': {field: value for field, value in entry['areas'].items() if field != POSTAL}}
            for entry in with_postal['shares']] == plain['shares']
    assert with_postal['areas'] == plain['areas']


def test_the_points_lost_are_spread_over_the_postal_codes():
    job, result = _postal_result()
    document = result['points_loss']
    entry = next(item for item in document['shares'] if POSTAL in item['areas'])
    assert sum(entry['areas'][POSTAL].values()) == pytest.approx(1, abs=.001)
    maps = build_scoring_views(job, result)['insights']['points_loss_maps']
    of = {item['field']: item for item in maps if item['operator'] == 'Vodafone UK' and item['environment'] == 'Combined'}
    postal = {area['name']: area for area in of[POSTAL]['areas']}
    assert postal['LS1 · Leeds']['points'] == pytest.approx(next(area['points'] for area in of['City']['areas'] if area['name'] == 'Leeds'))
    assert of[POSTAL]['total'] == pytest.approx(of['City']['total'])
    # A map holds thousands of postal codes: only what the table and the map read.
    assert set(postal['LS1 · Leeds']) == {'name', 'points', 'share', 'tests', 'rate', 'environments'}
    assert postal['LS1 · Leeds']['tests'] == 40 and postal['LS1 · Leeds']['rate'] is None
    assert of[POSTAL]['rate_minimum'] == 100
    # Its polygons and the outline of the country are kept with the map.
    assert set(map_boundaries(result, POSTAL)) == set(AREAS) and map_background(result, POSTAL)
    assert map_boundaries(result, 'Cluster') == {}


def test_postal_codes_rank_by_their_points_per_1000_tests_with_a_lower_minimum(monkeypatch):
    from src.modules import scoring_insights

    monkeypatch.setattr(scoring_insights, 'MIN_POSTAL_RATE_TESTS', 35)
    job, result = _postal_result()
    maps = build_scoring_views(job, result)['insights']['points_loss_maps']
    of = {item['field']: item for item in maps if item['operator'] == 'Vodafone UK' and item['environment'] == 'Combined'}
    leeds = next(area for area in of[POSTAL]['areas'] if area['name'] == 'LS1 · Leeds')
    assert of[POSTAL]['rate_minimum'] == 35 and leeds['rate'] == pytest.approx(leeds['points'] / 40 * 1000)
    # The Cities keep their own minimum.
    assert of['City']['rate_minimum'] == scoring_insights.MIN_RATE_TESTS


def _titles(content):
    return [slide.shapes.title.text_frame.text.split('\n')[0] for slide in Presentation(BytesIO(content)).slides
            if slide.shapes.title is not None]


def test_the_powerpoint_has_the_postal_code_maps_only_when_the_saved_filter_has_them():
    job, result = _postal_result()
    content = export_scoring_powerpoint(job, result, TEMPLATE)
    assert 'Points Lost per Postal Code — Vodafone UK' in _titles(content)
    deck = Presentation(BytesIO(content))
    slide = next(slide for slide in deck.slides if slide.shapes.title is not None
                 and slide.shapes.title.text_frame.text.startswith('Points Lost per Postal Code — Vodafone UK'))
    assert 'Scoring Points Lost Map' in {shape.name for shape in slide.shapes}
    note = next(shape for shape in slide.shapes if shape.name == 'Scoring Points Lost National Note')
    assert 'Approximate areas, not official borders' in note.text_frame.text
    # The option of the report leaves them out; the map per City stays.
    scenario = default_scenario()
    for options in scenario['scorings'].values():
        options['points']['postal_map'] = False
    without = export_scoring_report([{'job': job, 'result': result, 'scenario': scenario}], TEMPLATE)
    assert not any(title.startswith('Points Lost per Postal Code') for title in _titles(without))
    assert any(title.startswith('Points Lost per City') for title in _titles(without))
    # A result without Postal Codes has no such slide.
    plain = calculate_scoring(_frames(), ['Operator'], configuration=scoring_configuration())
    assert not any(title.startswith('Points Lost per Postal Code') for title in _titles(export_scoring_powerpoint(job, plain, TEMPLATE)))


def test_the_postal_code_map_is_a_scoring_export_panel():
    assert default_export_panels()['points']['postal_map'] == {'exportable': True, 'operators': 'focus'}


# -- the Saved Filter -----------------------------------------------------------------------------
@pytest.fixture()
def repository(tmp_path: Path) -> Repository:
    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()
    repository.replace_scoring_configuration(scoring_configuration())
    return repository


def _voice_dataset(repository: Repository) -> int:
    source = Path(repository.db_path).parent / 'UK_Q2_2026_NSA_Voice.csv'
    source.write_text('source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(source.name, str(source), 'tester')
    frame = _frames()['voice'].assign(Dataset_Kind='voice', NR_Mode='NSA')
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', dataset_kind='voice', row_count=len(frame),
                                      column_count=len(frame.columns), nr_mode='NSA')
    return dataset_id


SUMMARY = {'breakdown': 'Region', 'cities': ['London'], 'time_split': 'Campaign'}


def test_postal_codes_are_a_selection_of_their_own_and_every_other_keeps_its_identity():
    plain = saved_filters.saved_filter_key([1], ['Operator'], 'NSA', 'EE', {}, '', SUMMARY)
    from src.modules.scoring_area_summary import normalize_area_summary_request
    assert 'postal_codes' not in normalize_area_summary_request(SUMMARY)
    assert normalize_area_summary_request({**SUMMARY, 'postal_codes': True})['postal_codes'] is True
    assert saved_filters.saved_filter_key([1], ['Operator'], 'NSA', 'EE', {}, '', {**SUMMARY, 'postal_codes': True}) != plain
    assert postal_areas.wanted({'area_summary': {**SUMMARY, 'postal_codes': True}})
    assert postal_areas.wanted({'area_summary': None, 'geographical_areas': {'postal_codes': True}})
    assert not postal_areas.wanted({'area_summary': SUMMARY}) and not postal_areas.wanted(None)


def test_a_saved_filter_that_asks_for_postal_codes_draws_them_with_its_map(repository):
    dataset_id = _voice_dataset(repository)
    postal, _reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Operator'], 'NSA', username='tester',
                                                      area_summary={**SUMMARY, 'postal_codes': True})
    plain, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Operator'], 'NSA', username='tester',
                                                    area_summary=SUMMARY)
    assert not reused and plain['id'] != postal['id']
    done = saved_filters.calculate_saved_filter(repository, postal['id'])
    assert done['status'] == 'completed' and done['area_summary']['postal_codes'] is True
    document = done['result']['points_loss']
    assert any(POSTAL in entry['areas'] for entry in document['shares'])
    # Leeds is a postal code of the layer shipped with the application.
    names = {name for entry in document['shares'] for name in entry['areas'].get(POSTAL, {})}
    assert any(name.startswith('LS') for name in names)
    # (The polygons of the codes with tests too: those without losses are drawn in the colour of no loss.)
    assert set(document['boundaries'][POSTAL]) >= names - {points_loss.NOT_SPECIFIED}
    assert document['postal_attribution'].startswith('GeoNames') and document['postal_background']
    other = saved_filters.calculate_saved_filter(repository, plain['id'])['result']['points_loss']
    assert not any(POSTAL in entry['areas'] for entry in other['shares']) and POSTAL not in (other.get('boundaries') or {})
