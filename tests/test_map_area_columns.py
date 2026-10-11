"""The map area of each test, kept in the rows of its CDR."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.modules import map_area_columns, map_areas, saved_filters
from src.modules.repository import Repository, local_now_iso
from src.modules.scoring import calculate_scoring
from tests.scoring_fixtures import scoring_configuration
from tests.test_map_areas import SPAIN

PLACES = {'Madrid': (40.45, -3.7), 'Getafe': (40.1, -3.7), 'Bilbao': (43.26, -2.93)}


@pytest.fixture()
def repository(tmp_path: Path) -> Repository:
    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()
    map_areas.save_layer(repository, country_code='ESP', level='ADM3', level_label='municipality', origin='geoBoundaries',
                         source='IGN', license_text='CC BY 4.0', attribution='IGN via geoBoundaries', boundaries=SPAIN,
                         username='super')
    return repository


def voice_rows() -> pd.DataFrame:
    rows = []
    for operator in ('EE', 'Vodafone UK'):
        for city, (latitude, longitude) in PLACES.items():
            for index in range(10):
                failed = operator != 'EE' and city == 'Madrid' and index < 3
                rows.append({'Campaign': '2026-Q2', 'Operator': operator, 'G_Level_1': 'Drive', 'G_Level_2': 'City',
                             'City': city, 'Session_Type': 'CALL', 'Call_Status': 'Failed' if failed else 'Completed',
                             'Call_Start_Latitude_A': latitude, 'Call_Start_Longitude_A': longitude})
    return pd.DataFrame(rows)


def add_voice_cdr(repository: Repository, name: str = 'Spain_Voice.csv') -> int:
    source = Path(repository.db_path).parent / name
    source.write_text(name, encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'tester')
    frame = voice_rows()
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind='voice', nr_mode='NSA',
                                      row_count=len(frame), column_count=len(frame.columns), processed_at=local_now_iso())
    return dataset_id


def test_the_tests_of_a_cdr_keep_their_map_area_until_the_map_areas_change(repository):
    dataset_id = add_voice_cdr(repository)
    _sources, _campaigns, fingerprint = saved_filters._source_snapshot(repository, [dataset_id])
    assert map_area_columns.stale_datasets(repository) == [(dataset_id, 'voice')]

    assert map_area_columns.fill_dataset(repository, dataset_id, 'voice') == 60
    stored = repository.load_dataset_rows(dataset_id, ['City', 'Map_Area', 'Map_Area_Country'], {})
    by_city = stored.drop_duplicates('City').set_index('City')
    assert by_city.loc['Madrid'].tolist() == ['Madrid', 'ESP']
    assert by_city.loc['Getafe'].tolist() == ['Getafe', 'ESP']
    # Bilbao lies outside every area of the workspace.
    assert by_city.loc['Bilbao'].tolist() == ['', '']
    assert map_area_columns.current_datasets(repository, [dataset_id]) == {dataset_id}
    assert map_area_columns.stale_datasets(repository) == []
    # The areas kept in the rows do not change the CDR for its scorings.
    assert saved_filters._source_snapshot(repository, [dataset_id])[2] == fingerprint

    # Other Map Areas: the tests are placed again.
    layer = map_areas.list_layers(repository)[0]
    map_areas.delete_layer(repository, layer['id'])
    assert map_area_columns.stale_datasets(repository) == [(dataset_id, 'voice')]
    assert map_area_columns.current_datasets(repository, [dataset_id]) == set()


def test_the_background_job_places_one_cdr_per_job(repository):
    first, second = add_voice_cdr(repository), add_voice_cdr(repository, 'Spain_Voice_2.csv')
    queued = []
    assert map_area_columns.queue_fill(repository, queued.append)
    # Queued once while it waits.
    assert not map_area_columns.queue_fill(repository, queued.append)
    assert [task['label'] for task in map_area_columns.fill_tasks(repository.db_path)] == ['Map Areas of the tests']
    queued.pop()()
    # The newest CDR first; the next one waits behind the work queued meanwhile.
    assert map_area_columns.current_datasets(repository, [first, second]) == {second}
    assert map_area_columns.fill_tasks(repository.db_path)[0]['detail'] == (
        '1 of 2 CDRs placed; waiting for the work before the next')
    queued.pop()()
    assert map_area_columns.current_datasets(repository, [first, second]) == {first, second}
    assert map_area_columns.fill_tasks(repository.db_path) == [] and queued == []


def test_the_map_reads_the_areas_kept_in_the_rows(repository, monkeypatch):
    dataset_id = add_voice_cdr(repository)
    configuration = scoring_configuration()
    placed = calculate_scoring({'voice': voice_rows()}, ['Operator'], configuration=configuration,
                               map_areas=map_areas.area_index(repository))['points_loss']
    map_area_columns.fill_dataset(repository, dataset_id, 'voice')
    columns = [*voice_rows().columns, 'Map_Area', 'Map_Area_Country']
    frame = repository.load_dataset_rows(dataset_id, columns, {})

    def no_placing(*_args, **_kwargs):
        raise AssertionError('The tests were placed again.')
    monkeypatch.setattr(map_areas.AreaIndex, '_places_of', no_placing)
    stored = calculate_scoring({'voice': frame}, ['Operator'], configuration=configuration,
                               map_areas=map_areas.area_index(repository))['points_loss']
    assert stored['shares'] == placed['shares']
    assert stored['map_areas'] == placed['map_areas']
