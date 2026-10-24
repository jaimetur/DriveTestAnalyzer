import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

import src.DriveTestAnalyzer as core
from src.modules import cdr_field_dictionary, cdr_types, ingestion, umlaut_cdr
from src.modules import non_qualified_calls as nq
from src.modules.cdr_field_profiles import NETCHECK_PROFILE, UMLAUT_PROFILE, field_profile, workspace_field_profile


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def umlaut_voice_workbook(path: Path) -> Path:
    """An Umlaut Voice_M2M_Calls export: a Statistics sheet and the sheet of one operator, each side of a call in its block."""
    workbook = Workbook()
    workbook.active.title = 'Statistics'
    workbook.active.append(['KPI', 'Value'])
    sheet = workbook.create_sheet('client11_WindTre')
    sheet.append(['Operator', 'Side1 System ID', 'Sequence', 'Filename', 'Side1 Call Type', 'Route Name',
                  'Side1 Call Setup latest available eNodeB/RNC', 'Side1 Call Setup latest available Sector/Cell ID',
                  'Side1 Call Setup latest available RSRP (dBm)', 'Side1 Call End eNodeB/RNC', 'Side1 Call End Sector/Cell ID',
                  'Side2 System ID', 'Sequence', 'Filename', 'Side2 Call Type', 'Route Name',
                  'Session TA Start', 'Session TA End', 'Call Setup Duration (Alerting) [s]', 'Sequence Status Overall',
                  'Sequence Detailed Status Overall', 'Qualifier'])
    sheet.append(['WindTre', 1, 616114000, 'IT__System1__0616114000', 'VOICE M2M MOC', 'Milano', 226015, '13', -91.0, 226015, '14',
                  2, 616114000, 'IT__System2__0616114000', 'VOICE M2M MTC', 'Milano',
                  '2025-06-16 11:40:02.556', '2025-06-16 11:41:20.657', 1.6, 'SUCCESS', 'Successful', 'QUALIFIED'])
    sheet.append(['WindTre', 1, 616114143, 'IT__System1__0616114143', 'VOICE M2M MTC', 'Torino', 3001, '300', -118.0, None, None,
                  2, 616114143, 'IT__System2__0616114143', 'VOICE M2M MOC', 'Torino',
                  '2025-06-16 11:41:43.000', '2025-06-16 11:42:10.000', None, 'DROPPED', 'Disconnect before end of call duration',
                  'NOT QUALIFIED'])
    target = path / 'WindTre_Vendor_Benchmark_2025_Round1_Voice_M2M_Calls_2025-07-30_16-05-07.xlsx'
    workbook.save(target)
    return target


def test_a_repeated_header_takes_the_side_of_its_block():
    headers = ['Side1 System ID', 'Sequence', 'Route Name', 'Side 2 Meta Status', 'Sequence', 'Route Name', 'Sequence']
    assert ingestion._make_unique_headers(headers, umlaut_cdr.SIDE_HEADER_PATTERN) == [
        'Side1 System ID', 'Sequence', 'Route Name', 'Side 2 Meta Status', 'Side2 Sequence', 'Side2 Route Name', 'Sequence_Duplicate_3']
    # Without a pattern (NetCheck) a repeated header is still <header>_Duplicate_<n>.
    assert ingestion._make_unique_headers(headers) == [
        'Side1 System ID', 'Sequence', 'Route Name', 'Side 2 Meta Status', 'Sequence_Duplicate_2', 'Route Name_Duplicate_2',
        'Sequence_Duplicate_3']
    assert NETCHECK_PROFILE.side_header_pattern == '' and NETCHECK_PROFILE.derive_columns is None


def test_the_campaign_and_the_summaries_come_from_the_export_file_name():
    name = 'WindTre_Vendor_Benchmark_2025_Round1_HTTP_File_DL_2025-07-30_16-05-07.xlsx'
    assert umlaut_cdr.export_campaign(name) == 'WindTre_Vendor_Benchmark_2025_Round1'
    assert umlaut_cdr.export_campaign('WindTre_Round1_Voice_M2M_SQ_Samples_2025-07-30.xlsx') == 'WindTre_Round1'
    assert umlaut_cdr.export_campaign('export.xlsx') == ''
    assert umlaut_cdr.is_summary_file('WindTre_Vendor_Benchmark_2025_Round1_All_Data_2025-07-30_16-05-07.xlsx')
    assert not umlaut_cdr.is_summary_file(name)


def test_the_tool_derives_the_test_key_and_the_lte_cells():
    frame = pd.DataFrame({
        'Campaign': [None, None, None], 'Filename': ['F1', 'F1', 'F2'], 'Task Name': ['Ping 40B', 'Ping 40B', 'Ping 800B'],
        'Ping TA Start': ['10:00:01', '10:00:02', '10:00:03'],
        'Ping RNC/eNodeB Start': [226015, 3001, None], 'Ping Cell ID/Sector Start': ['13', '300', '1'],
        'Session RNC/eNodeB End': [226015, None, 1000], 'Session Cell ID/Sector End': ['14', None, '2'],
    })
    derived = umlaut_cdr.derive_columns(frame, 'WindTre_Round1_Ping_2025-07-30_16-05-07.xlsx')
    assert derived['Campaign'].tolist() == ['WindTre_Round1'] * 3
    assert derived['Test_Key'].tolist() == ['F1|Ping 40B|10:00:01', 'F1|Ping 40B|10:00:02', 'F2|Ping 800B|10:00:03']
    # eNodeB × 256 + Cell ID where the row started and ended; a Cell ID above 255 is not an LTE cell.
    assert derived['ECI'].tolist()[0] == f'{226015 * 256 + 13}->{226015 * 256 + 14}'
    assert pd.isna(derived['ECI'].tolist()[1]) and derived['ECI'].tolist()[2] == str(1000 * 256 + 2)
    # A CDR with its own Campaign keeps it.
    own = umlaut_cdr.derive_columns(pd.DataFrame({'Campaign': ['IT_Campaign_01'], 'Filename': ['F']}), 'WindTre_Round1_DNS.xlsx')
    assert own['Campaign'].tolist() == ['IT_Campaign_01']


def test_an_umlaut_export_is_read_with_its_own_names_values_and_units(tmp_path):
    source_columns: list[str] = []
    calls = ingestion.load_dataset(umlaut_voice_workbook(tmp_path), source_columns=source_columns, profile=UMLAUT_PROFILE)
    assert calls['source_sheet'].tolist() == ['client11_WindTre'] * 2 and calls['dataset_kind'].iloc[0] == 'voice'
    assert {'Side2 Sequence', 'Side2 Filename', 'Side2 Route Name'} <= set(source_columns)
    assert calls['Campaign'].tolist() == ['WindTre_Vendor_Benchmark_2025_Round1'] * 2
    assert calls['status'].tolist() == ['Completed', 'Dropped'] and calls['Call_Status'].tolist() == ['Completed', 'Dropped']
    assert calls['success'].tolist() == [True, False] and calls['dropped'].tolist() == [False, True]
    assert calls['ECI'].tolist()[0] == f'{226015 * 256 + 13}->{226015 * 256 + 14}'
    assert calls['setup_time_seconds'].tolist()[0] == 1.6
    data = ingestion._normalise_dataset(pd.DataFrame({
        'Operator': ['WindTre'], 'Filename': ['F'], 'Task Name': ['HTTPS 10MB Download'], 'Network Access TA Start': ['2025-06-16 11:43:34'],
        'Overall Session Status': ['FAILED'], 'Transfer Throughput [kbit/s]': [179372.0],
    }), Path('WindTre_Round1_HTTP_File_DL_2025-07-30_16-05-07.xlsx'), UMLAUT_PROFILE)
    assert data['dataset_kind'].iloc[0] == 'data' and data['status'].tolist() == ['Failed']
    assert data['throughput_mbps'].tolist() == [pytest.approx(179.372)]
    assert data['Test_Key'].tolist() == ['F|HTTPS 10MB Download|2025-06-16 11:43:34']
    # The service in the name tells the type, the samples before the calls.
    assert ingestion.infer_dataset_kind(pd.DataFrame(), 'X_Voice_M2M_SQ_Samples_2025.xlsx', UMLAUT_PROFILE) == 'speech'
    assert ingestion.infer_dataset_kind(pd.DataFrame(), 'X_Conversational_App_Calls_2025.xlsx', UMLAUT_PROFILE) == 'voice'
    assert ingestion.infer_dataset_kind(pd.DataFrame(), 'X_Youtube_2025.xlsx', UMLAUT_PROFILE) == 'data'


def test_umlaut_calls_are_non_qualified_by_their_qualifier_and_take_the_radio_of_their_samples():
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    pd.DataFrame({
        'Operator': ['WindTre'] * 3, 'Campaign': ['Round1'] * 3, 'Sequence': [1, 2, 3],
        'Call_Status': ['Completed', 'Completed', 'Dropped'], 'event_start_time': ['2025-06-16 10:00:00'] * 3,
        'Qualifier': ['QUALIFIED', 'NOT QUALIFIED', 'NOT QUALIFIED'],
        'Side1 Call Setup latest available RSRP (dBm)': [-90.0, -91.0, -118.0],
        'Sequence Detailed Status Overall': ['Successful', 'Successful', 'Disconnect before end of call duration'],
    }).to_sql('dataset_rows_1', connection, index=False)
    pd.DataFrame({
        'Operator': ['WindTre'] * 3, 'Campaign': ['Round1'] * 3, 'Sequence': [3, 3, 2], 'POLQA Sample TA Start': ['a', 'b', 'c'],
        'Qualifier': ['QUALIFIED', 'NOT QUALIFIED', 'QUALIFIED'], 'Side1 Sample Start RSRP (dBm)': [-100.0, -110.0, ''],
        'Side1 Sample Start SINR (dB)': [2.0, 4.0, 5.0],
    }).to_sql('dataset_rows_2', connection, index=False)
    datasets = [{'id': 1, 'dataset_kind': 'voice', 'nr_mode': 'NSA'}, {'id': 2, 'dataset_kind': 'speech', 'nr_mode': 'NSA'}]
    radio = nq._sample_radio(connection, datasets, UMLAUT_PROFILE)
    assert radio[('windtre', 'round1', '3')] == {'lte_rsrp': -105.0, 'lte_sinr': 3.0}
    # An empty sample value is not a zero.
    assert radio[('windtre', 'round1', '2')] == {'lte_sinr': 5.0}
    voice = nq._dataset_calls(connection, datasets[0], profile=UMLAUT_PROFILE, sample_radio=radio)
    assert len(voice['calls']) == 2 and sum(row[6] for row in voice['population']) == 2 and len(voice['population']) == 3
    calls = {dict(zip(nq._CALL_COLUMNS, call))['source_row_id']: dict(zip(nq._CALL_COLUMNS, call)) for call in voice['calls']}
    assert json.loads(calls[3]['rca_inputs_json'])['lte_rsrp'] == -105.0
    # Without samples of its own radio, a call keeps the radio of its setup.
    assert json.loads(calls[2]['rca_inputs_json']) == {'lte_rsrp': -91.0, 'lte_sinr': 5.0}
    assert calls[3]['failure_comment'] == 'Disconnect before end of call duration'
    samples = nq._dataset_calls(connection, datasets[1], profile=UMLAUT_PROFILE)
    sample = dict(zip(nq._CALL_COLUMNS, samples['calls'][0]))
    # The sample shares the call key of the Speech call of its Sequence.
    assert len(samples['calls']) == 1 and sample['sample_id'] == 'b'
    assert sample['call_key'] == nq.call_key_for('speech', {'operator': 'WindTre', 'campaign': 'Round1'}, '3')


def test_the_cdr_field_dictionary_changes_the_columns_of_a_field(client):
    login(client)
    assert workspace_field_profile(core.repository) is NETCHECK_PROFILE
    entries = {row['key']: row for row in cdr_field_dictionary.entries(NETCHECK_PROFILE)}
    assert entries['nq_qualification_sources']['defaults'] == list(NETCHECK_PROFILE.nq_qualification_sources)
    assert entries['rf_field_aliases.lte_rsrp.voice']['defaults'] == ['4G_RSRP_Avg_A']
    assert entries['nq_rca_sources.lte_rsrp']['label'] == 'LTE RSRP (average)'
    # Unknown fields, defaults and empty fields are not kept.
    assert cdr_field_dictionary.normalize_overrides({'nope': ['A'], 'nq_rca_sources.mos': ['POLQA_LQ_Avg', 'LQ'],
                                                     'nq_join_sources': ' ; '}, NETCHECK_PROFILE) == {}
    response = client.post('/workspace-config/cdr-field-dictionary/save', data={
        'field:nq_rca_sources.mos': 'MOS_Avg; POLQA_LQ_Avg', 'field:rf_field_aliases.lte_rsrp.voice': '4G_RSRP_Avg_A',
        'field:cell_columns': 'ECI',
    }, follow_redirects=False)
    assert response.status_code == 303 and 'cdr_field_dictionary_notice' in response.headers['location']
    profile = workspace_field_profile(core.repository)
    assert profile.nq_rca_sources['mos'] == ('MOS_Avg', 'POLQA_LQ_Avg') and profile.cell_columns == ('ECI',)
    assert profile.rf_field_aliases['lte_rsrp'] == NETCHECK_PROFILE.rf_field_aliases['lte_rsrp']
    assert NETCHECK_PROFILE.nq_rca_sources['mos'] == ('POLQA_LQ_Avg', 'LQ')
    with core.repository.connection() as connection:
        event = connection.execute(
            "SELECT details FROM audit_logs WHERE action = 'cdr_field_dictionary_saved' ORDER BY rowid DESC").fetchone()
    assert json.loads(event[0])['changes']['cell_columns'] == {'before': 'default', 'after': ['ECI']}
    # The NQ calls follow the changed fields.
    nq.ensure_nq_tables(core.repository)
    assert ':' in nq._index_changes(core.repository)[1]
    # The follow-up of the calls moves to their call keys when the dictionary changes them.
    nq.sync_nq_calls(core.repository)
    fingerprint = cdr_field_dictionary.fingerprint(cdr_field_dictionary.load_overrides(core.repository))
    assert core.repository.get_workspace_state(nq.KEY_SCHEME_STATE_KEY) == f'{nq.KEY_SCHEME}:{fingerprint}'
    page = client.get('/workspace-config').text
    assert 'id="cdr-field-dictionary"' in page and 'name="field:nq_rca_sources.mos" value="MOS_Avg; POLQA_LQ_Avg"' in page
    # It travels with Mappings & Reference Data: a package restores it, one of another CDR type is left out.
    payload = core._mappings_reference_data_archive_payload(core.active_workspace)
    exported = json.loads(payload)['cdr_field_dictionary']
    assert exported['cdr_type'] == 'netcheck' and exported['fields']['cell_columns'] == ['ECI']
    cdr_field_dictionary.save_overrides(core.repository, {}, NETCHECK_PROFILE)
    core._restore_workspace_mappings_reference_data(core.active_workspace, payload)
    assert cdr_field_dictionary.load_overrides(core.repository)['cell_columns'] == ['ECI']
    other = {**json.loads(payload), 'cdr_field_dictionary': {**exported, 'cdr_type': 'umlaut', 'fields': {}}}
    core._restore_workspace_mappings_reference_data(core.active_workspace, json.dumps(other).encode())
    assert cdr_field_dictionary.load_overrides(core.repository)['cell_columns'] == ['ECI']
    # Fields saved for another CDR type do not apply.
    core.repository.set_workspace_state(cdr_types.CDR_TYPE_STATE_KEY, 'umlaut')
    assert cdr_field_dictionary.load_overrides(core.repository) == {} and workspace_field_profile(core.repository) is field_profile('umlaut')


def test_the_upload_names_and_recognises_the_cdrs_of_the_workspace_provider(client):
    login(client)
    assert core.upload_cdr_profile(core.repository) == {'type': 'netcheck', 'label': 'NetCheck CDR', 'kind_words': [], 'summary_words': []}
    core.repository.set_workspace_state(cdr_types.CDR_TYPE_STATE_KEY, 'umlaut')
    umlaut = core.upload_cdr_profile(core.repository)
    assert umlaut['label'] == 'Umlaut CDR' and ['sq samples', 'speech'] in umlaut['kind_words']
    assert umlaut['summary_words'] == ['all data', 'all voice']
    page = client.get('/workspace').text
    assert 'data-cdr-profile=' in page and 'Umlaut CDR workbooks (Data, Voice and Speech)' in page


def test_non_qualified_calls_name_the_provider_of_the_cdrs(client):
    login(client)
    assert nq.provider_texts(core.repository) == {
        'name': 'NetCheck', 'rca': 'NetCheck RCA', 'definition': 'whose result is not Completed (Failed, Dropped, Cutoff…)',
        'rca_hierarchy': True, 'join_id': True}
    page = client.get('/non-qualified-calls').text
    assert 'whose result is not Completed (Failed, Dropped, Cutoff…) in the ready CDRs' in page and '>NetCheck RCA</button>' in page
    core.repository.set_workspace_state(cdr_types.CDR_TYPE_STATE_KEY, 'umlaut')
    umlaut = nq.provider_texts(core.repository)
    assert umlaut['rca'] == 'Umlaut RCA' and not umlaut['rca_hierarchy']
    assert nq.source_labels(core.repository)['netcheck'] == 'Umlaut RCA'
    page = client.get('/non-qualified-calls').text
    assert 'whose Umlaut qualifier is NOT QUALIFIED' in page and '>Umlaut RCA</button>' in page
    assert 'decided from Umlaut, the Ericsson RCA' in page and 'Umlaut CDRs bring no RCA of their own' in page
    # Umlaut calls have no JOIN_ID to find them by.
    assert '<label class="nq-join-search" data-nq-join-search hidden>' in page
    nq.ensure_nq_tables(core.repository)
    fields = {field['key']: field for field in nq.provider_field_labels(nq.list_fields(core.repository), core.repository)}
    assert fields['netcheck_failure_classification']['label'] == 'Umlaut RCA Failure Classification'
    assert 'NetCheck' not in fields['failure_comment']['description']
    from src.modules.non_qualified_calls_visuals import root_cause_title
    assert str(root_cause_title({'source': 'netcheck', 'provider': umlaut})) == 'Root Cause Analysis · Umlaut RCA'
    assert str(root_cause_title({'source': 'netcheck'})) == 'Root Cause Analysis · NetCheck RCA'
