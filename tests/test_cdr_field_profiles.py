import dataclasses
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import cdr_types, ingestion, map_area_columns, network_insights, nq_call_map, scoring_points_loss, serving_cells
from src.modules import non_qualified_calls as nq
from src.modules.cdr_field_profiles import NETCHECK_PROFILE, field_profile, workspace_field_profile
from src.modules.repository import local_now_iso


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def add_cdr(tmp_path: Path, name: str, kind: str, rows: pd.DataFrame) -> int:
    source = tmp_path / name
    source.write_text('test source', encoding='utf-8')
    dataset_id, _created = core.repository.add_dataset(name, str(source), 'super')
    core.repository.replace_dataset_rows(dataset_id, rows)
    core.repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA',
                                           row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso())
    return dataset_id


def test_the_netcheck_profile_holds_the_columns_every_module_reads():
    # The module tables are the NetCheck profile, so NetCheck CDRs are read as before the profiles existed.
    assert ingestion.CDR_IGNORED_SHEETS is NETCHECK_PROFILE.ignored_sheets
    assert nq.FIELD_SOURCES is NETCHECK_PROFILE.nq_field_sources and nq.CALL_FIELDS == tuple(NETCHECK_PROFILE.nq_field_sources)
    assert nq.JOIN_SOURCES == ('JOIN_ID',) and nq.QUALIFIED_RESULT == 'completed'
    assert nq.FIELD_SOURCES['result'] == NETCHECK_PROFILE.nq_qualification_sources == ('status', 'Call_Status', 'Test_Result', 'Test_Status')
    assert network_insights.RF_FIELD_ALIASES is NETCHECK_PROFILE.rf_field_aliases
    assert network_insights.DIMENSION_ALIASES is NETCHECK_PROFILE.dimension_aliases
    assert serving_cells.START_COORDINATES is NETCHECK_PROFILE.start_coordinates
    assert serving_cells.CDR_CELL_COLUMNS[:3] == ('Cell_ID_A', 'Cell_IDs_A', 'Cell_ID')
    assert scoring_points_loss.COORDINATE_SOURCES is NETCHECK_PROFILE.coordinate_sources
    assert nq_call_map.NR_PCI_COLUMNS == {'data': ('NR_DL_PCell_PCI_Info_List',), 'voice': (), 'speech': ()}
    assert NETCHECK_PROFILE.operator_sheets_after == 'KPI Definition'


def test_a_cdr_type_without_its_own_profile_reads_as_netcheck():
    assert field_profile('netcheck') is NETCHECK_PROFILE
    assert field_profile('umlaut') is NETCHECK_PROFILE and field_profile('') is NETCHECK_PROFILE
    assert [option['value'] for option in cdr_types.cdr_type_options()] == ['netcheck', 'umlaut', 'p3']
    assert not cdr_types.CDR_TYPES['p3']['supported']


def test_the_cdr_type_of_a_file_comes_from_its_profile():
    frame = pd.DataFrame({'POLQA Value Overall': [4.2]})
    assert ingestion.infer_dataset_kind(frame, 'Voice_M2M_SQ_Samples.xlsx') == 'voice'
    samples_first = dataclasses.replace(NETCHECK_PROFILE, kind_name_words=(('sq samples', 'speech'), ('calls', 'voice')),
                                        kind_markers={'speech': frozenset({'POLQA Value Overall'})})
    assert ingestion.infer_dataset_kind(frame, 'Voice_M2M_SQ_Samples.xlsx', samples_first) == 'speech'
    assert ingestion.infer_dataset_kind(frame, 'Export.xlsx', samples_first) == 'speech'


def test_a_profile_chooses_the_columns_of_the_internal_fields():
    frame = pd.DataFrame({'Sequence Status Overall': ['SUCCESS', 'FAILED'], 'Call_Status': ['Completed', 'Completed']})
    assert ingestion._normalise_dataset(frame, Path('calls.xlsx'))['status'].tolist() == ['Completed', 'Completed']
    native = dataclasses.replace(NETCHECK_PROFILE, normalised_sources={
        **NETCHECK_PROFILE.normalised_sources, 'status': ('Sequence Status Overall',)})
    normalised = ingestion._normalise_dataset(frame, Path('calls.xlsx'), native)
    assert normalised['status'].tolist() == ['SUCCESS', 'FAILED']
    assert normalised['success'].tolist() == [True, False]


def test_non_qualified_calls_follow_the_qualification_column_of_the_profile():
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    pd.DataFrame({
        'Operator': ['WindTre'] * 3, 'Campaign': ['IT_Campaign_01'] * 3, 'Sequence': ['1', '2', '3'],
        'Call_Status': ['Completed', 'Completed', 'Failed'], 'Qualifier': ['QUALIFIED', 'NOT QUALIFIED', 'NOT QUALIFIED'],
    }).to_sql('dataset_rows_7', connection, index=False)
    dataset = {'id': 7, 'dataset_kind': 'voice', 'nr_mode': 'NSA'}
    netcheck = nq._dataset_calls(connection, dataset)
    assert len(netcheck['calls']) == 1 and sum(row[6] for row in netcheck['population']) == 1
    qualifier = dataclasses.replace(NETCHECK_PROFILE, nq_qualification_sources=('Qualifier',), nq_qualified_value='qualified',
                                    nq_identifier_sources={**NETCHECK_PROFILE.nq_identifier_sources, 'voice': ('Sequence',)})
    umlaut_like = nq._dataset_calls(connection, dataset, profile=qualifier)
    assert len(umlaut_like['calls']) == 2 and sum(row[6] for row in umlaut_like['population']) == 2
    # The result shown is still the call status; only what makes a call NQ changes.
    result = nq.CALL_FIELDS.index('result')
    assert sorted(call[5 + result] for call in umlaut_like['calls']) == ['Completed', 'Failed']


def test_coordinates_and_cells_come_from_the_profile():
    frame = pd.DataFrame({'Cell_ID_A': ['[1]->[2]'], 'Call_Start_Longitude_A': [-0.1], 'Call_Start_Latitude_A': [51.5]})
    assert serving_cells.serving_endpoints(frame, 'voice')['cell'].tolist() == ['1', '2']
    assert map_area_columns._coordinate_columns(['Test_Start_Latitude', 'Test_Start_Longitude'], 'data') == ('Test_Start_Latitude', 'Test_Start_Longitude')
    side_one = dataclasses.replace(NETCHECK_PROFILE, coordinate_sources={'data': (('Network Access LAT', 'Network Access LON'),)})
    assert map_area_columns._coordinate_columns(['Network Access LAT', 'Network Access LON'], 'data', side_one) == ('Network Access LAT', 'Network Access LON')
    assert network_insights.resolve_source_columns(['Operator', 'LTE_PCell_RSRP_Avg'], 'data') == {'operator': 'Operator', 'lte_rsrp': 'LTE_PCell_RSRP_Avg'}


def test_a_workspace_with_cdrs_keeps_its_cdr_type(client, tmp_path, monkeypatch):
    login(client)
    monkeypatch.setitem(cdr_types.CDR_TYPES, 'umlaut', {'label': 'Umlaut CDR', 'supported': True})
    assert workspace_field_profile(core.repository) is NETCHECK_PROFILE
    # Without CDRs the type can still change.
    assert cdr_types.set_workspace_cdr_type(core.repository, 'umlaut') == 'umlaut'
    assert cdr_types.set_workspace_cdr_type(core.repository, 'netcheck') == 'netcheck'
    add_cdr(tmp_path, 'Voice CDR.xlsx', 'voice', pd.DataFrame({'Operator': ['EE'], 'Call_Status': ['Completed']}))
    with pytest.raises(ValueError, match='already has NetCheck CDR files'):
        cdr_types.set_workspace_cdr_type(core.repository, 'umlaut')
    response = client.post('/workspace-config/cdr-type', data={'cdr_type': 'umlaut'})
    assert response.status_code == 400 and 'its CDR type cannot change' in response.text
    assert cdr_types.workspace_cdr_type(core.repository) == 'netcheck'
    assert cdr_types.set_workspace_cdr_type(core.repository, 'netcheck') == 'netcheck'
    page = client.get('/workspace-config').text
    assert '<option value="p3" disabled>P3 CDR (coming soon)</option>' in page
    assert 'kept once it has CDRs' in page
