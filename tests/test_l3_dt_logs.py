"""Layer 3 - DT Logs: the parsed drivetest logs of each campaign, imported as one dataset per campaign."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import src.DriveTestAnalyzer as app_module
from src.modules import l3_dt_logs

HEADER = ['Log_Day', 'Campaign', 'Operator', 'Session_Type', 'Session_Name', 'Call_Status', 'JoinID', 'File_Name',
          'Call_Start_Time', 'Call_End_Time', 'Session_Duration', 'UE', 'SourceTable', 'EventFullDate', 'Latitude',
          'Longitude', 'RANConfiguration', 'Radio_EARFCN', 'Radio_PhyCellId', 'Radio_RSRP', 'Radio_CarrierIndex']


def login(client) -> None:
    response = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert response.status_code == 303


def log_rows() -> list[dict[str, str]]:
    """Two sessions of an NSA campaign (a voice call, UE A and B) and one data test of an SA campaign."""
    rows = []
    sessions = [
        ('UK_Q3_NSA_2026', '3', 'CALL', 'Failed', '0xaa11', 'A', 51.50),
        ('UK_Q3_NSA_2026', '3', 'CALL', 'Failed', '0xaa11', 'B', 51.60),
        ('UK_Q3_SA_2026', 'Vodafone SM', 'httpBrowser', 'Cutoff', '0xBB22', 'Data', 52.40),
    ]
    for campaign, operator, service, status, join_id, ue, latitude in sessions:
        for index in range(3):
            rows.append({
                'Log_Day': '2026-09-03', 'Campaign': campaign, 'Operator': operator, 'Session_Type': service,
                'Session_Name': '', 'Call_Status': status, 'JoinID': join_id, 'File_Name': f'{join_id}-{ue}.mf',
                'Call_Start_Time': '2026-09-03 08:08:16.000', 'Call_End_Time': '2026-09-03 08:08:40.000',
                'Session_Duration': '24.0', 'UE': ue, 'SourceTable': 'FactLTERadio',
                'EventFullDate': f'2026-09-03 08:08:{16 + index}.000', 'Latitude': str(latitude + index / 1000),
                'Longitude': str(-0.12 - index / 1000), 'RANConfiguration': 'LTE', 'Radio_EARFCN': '223',
                'Radio_PhyCellId': '114', 'Radio_RSRP': str(-90 - index), 'Radio_CarrierIndex': '0',
            })
    return rows


def csv_bytes(rows: list[dict[str, str]], header: list[str] = HEADER) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8')


def zip_bytes(rows: list[dict[str, str]]) -> bytes:
    """A delivery split in two CSV files, as the parser writes it (each file with rows of both campaigns)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('Consolidated_Dataset_1.csv', csv_bytes(rows[::2]))
        archive.writestr('Consolidated_Dataset_2.csv', csv_bytes(rows[1::2]))
    return buffer.getvalue()


def upload(client, name: str, content: bytes, media_type: str = 'application/zip'):
    return client.post('/datasets-analysis/upload', files={'dataset_files': (name, io.BytesIO(content), media_type)},
                       data={'dataset_kinds': 'l3_dt_logs'}, follow_redirects=False)


def l3_datasets() -> list[dict]:
    return [app_module.serialize_dataset_row(row) for row in app_module.repository.list_datasets()
            if row['dataset_kind'] == l3_dt_logs.KIND]


def sessions() -> list[dict]:
    with app_module.repository.connection() as connection:
        return [dict(row) for row in connection.execute(
            f'SELECT * FROM {l3_dt_logs.SESSIONS_TABLE} ORDER BY dataset_id, join_id, ue')]


def test_a_delivery_of_two_campaigns_is_one_dataset_per_campaign_read_from_parquet(client) -> None:
    login(client)
    response = upload(client, 'Consolidated_Dataset_3.zip', zip_bytes(log_rows()))
    assert response.status_code == 303

    datasets = sorted(l3_datasets(), key=lambda item: item['campaign_key'])
    assert [(item['status'], item['campaign'], item['l3']['nr_mode'], item['l3']['campaign_label']) for item in datasets] == [
        ('ready', '2026-Q3', 'NSA', 'UK_Q3_NSA_2026'), ('ready', '2026-Q3', 'SA', 'UK_Q3_SA_2026')]
    assert [item['file_name'] for item in datasets] == [
        'Consolidated_Dataset_3 - UK_Q3_NSA_2026', 'Consolidated_Dataset_3 - UK_Q3_SA_2026']
    nsa, sa = datasets
    assert (nsa['row_count'], nsa['l3']['sessions'], nsa['l3']['join_ids'], nsa['l3']['operators']) == (6, 2, 1, ['3'])
    assert (sa['row_count'], sa['l3']['sessions'], sa['l3']['services']) == (3, 1, {'httpBrowser': 1})
    # The rows are only in their Parquet sources: the delivery itself is removed, nothing is written to SQLite.
    input_files = sorted(path.name for path in Path(nsa['stored_path']).parent.iterdir())
    assert 'Consolidated_Dataset_3.zip' not in input_files
    assert all(Path(item['stored_path']).suffix == '.parquet' and Path(item['stored_path']).is_file() for item in datasets)
    assert app_module.repository.list_dataset_row_columns(int(nsa['id'])) == []
    assert [(row['join_id'], row['ue'], row['records'], row['positions']) for row in sessions()] == [
        ('0xAA11', 'A', 3, 3), ('0xAA11', 'B', 3, 3), ('0xBB22', 'Data', 3, 3)]
    first = sessions()[0]
    assert (first['call_status'], first['service'], first['ran_configurations']) == ('Failed', 'CALL', 'LTE')
    assert first['first_latitude'] == 51.5 and first['last_latitude'] == 51.502
    events = [dict(row) for row in app_module.repository.list_logs() if row['action'] == 'l3_dt_logs_processed']
    details = json.loads(events[0]['details'])
    assert [item['campaign_label'] for item in details['datasets']] == ['UK_Q3_NSA_2026', 'UK_Q3_SA_2026']

    page = client.get('/workspace').text
    card = page.split('data-dataset-card="l3-dt-logs"', 1)[1].split('</section>', 1)[0]
    assert 'Layer 3 - DT Logs' in card and 'UK_Q3_SA_2026' in card and '2 campaigns' in card and '3 sessions' in card
    preview = client.get(f"/workspace/preview/{nsa['id']}")
    assert preview.status_code == 200 and '0xaa11' in preview.text and 'Radio_RSRP' in preview.text


def test_a_delivery_uploaded_again_replaces_its_campaigns(client) -> None:
    login(client)
    upload(client, 'Consolidated_Dataset_3.zip', zip_bytes(log_rows()))
    before = sorted(int(item['id']) for item in l3_datasets())
    rows = [row for row in log_rows() if row['UE'] != 'B']
    upload(client, 'Consolidated_Dataset_3.zip', zip_bytes(rows))
    datasets = l3_datasets()
    assert len(datasets) == 2 and all(item['status'] == 'ready' for item in datasets)
    # The campaign of the dataset processed takes the place of the earlier one; the other campaign is refreshed.
    assert len(before) == 2 and before[1] in {int(item['id']) for item in datasets}
    assert sorted((row['join_id'], row['ue']) for row in sessions()) == [('0xAA11', 'A'), ('0xBB22', 'Data')]


def test_deleting_a_dataset_removes_its_sessions(client) -> None:
    login(client)
    upload(client, 'logs.csv', csv_bytes(log_rows()), 'text/csv')
    nsa = next(item for item in l3_datasets() if item['l3']['nr_mode'] == 'NSA')
    response = client.post(f"/datasets-analysis/delete/{nsa['id']}", follow_redirects=False)
    assert response.status_code == 303
    assert {row['join_id'] for row in sessions()} == {'0xBB22'}
    assert not Path(nsa['stored_path']).exists()


def test_a_file_without_the_columns_of_a_delivery_fails_with_the_missing_columns(client) -> None:
    login(client)
    header = [column for column in HEADER if column not in {'JoinID', 'UE'}]
    upload(client, 'logs.csv', csv_bytes(log_rows(), header), 'text/csv')
    dataset = next(app_module.serialize_dataset_row(row) for row in app_module.repository.list_datasets())
    assert dataset['status'] == 'failed'
    assert 'not a Layer 3 - DT Logs delivery' in dataset['last_error'] and 'JoinID, UE' in dataset['last_error']


def test_the_reserved_smart_orchestrator_logs_type_becomes_layer_3_dt_logs(tmp_path) -> None:
    connection = sqlite3.connect(tmp_path / 'workspace.db')
    connection.execute('CREATE TABLE dataset_profiles (dataset_id INTEGER, dataset_kind TEXT)')
    connection.execute("INSERT INTO dataset_profiles VALUES (1, 'smart_orchestrator_logs'), (2, 'data')")
    l3_dt_logs.ensure_workspace_schema(connection)
    assert connection.execute('SELECT dataset_kind FROM dataset_profiles ORDER BY dataset_id').fetchall() == [
        ('l3_dt_logs',), ('data',)]
    assert connection.execute(f'SELECT COUNT(*) FROM {l3_dt_logs.SESSIONS_TABLE}').fetchone() == (0,)


def test_campaign_profile_and_identifiers() -> None:
    assert l3_dt_logs.campaign_profile('UK_Q3_SA_2026') == {
        'campaign': '2026-Q3', 'campaign_label': 'UK_Q3_SA_2026', 'nr_mode': 'SA'}
    assert l3_dt_logs.campaign_profile('UK_Q3_NSA_2026')['nr_mode'] == 'NSA'
    assert l3_dt_logs.normalise_join_id(' 0xab12 ') == '0xAB12'
    assert [l3_dt_logs.normalise_ue(value) for value in ('a', 'B', 'Data', 'D', '')] == ['A', 'B', 'Data', 'Data', 'Data']
    assert l3_dt_logs.campaign_source_name('Consolidated_Dataset_3 - UK_Q3_SA_2026', 'UK_Q3_SA_2026') == (
        'Consolidated_Dataset_3 - UK_Q3_SA_2026.parquet')


def add_data_cdr(tmp_path: Path, join_ids: list[str]) -> int:
    """A Data CDR whose tests failed, one per JOIN_ID."""
    import pandas as pd
    from src.modules.repository import local_now_iso

    rows = pd.DataFrame({
        'Operator': ['Vodafone UK'] * len(join_ids), 'Campaign': ['UK_Q3_SA_2026'] * len(join_ids),
        'City': ['Leeds'] * len(join_ids), 'Test_ID': list(range(5001, 5001 + len(join_ids))),
        'Test_Name': ['HTTP DL'] * len(join_ids), 'Test_Result': ['Cutoff'] * len(join_ids),
        'status': ['Cutoff'] * len(join_ids), 'JOIN_ID': join_ids,
        'event_start_time': ['2026-09-03 09:00:00'] * len(join_ids),
        'Failure_Classification': ['RF Problems'] * len(join_ids),
    })
    source = tmp_path / 'data.csv'
    source.write_text('test source', encoding='utf-8')
    repository = app_module.repository
    dataset_id, _created = repository.add_dataset('data.csv', str(source), 'super')
    repository.replace_dataset_rows(dataset_id, rows)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind='data', nr_mode='SA',
                                      row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso())
    return int(dataset_id)


def test_nq_calls_list_filter_and_show_the_ues_of_their_layer_3_sessions(client, tmp_path, monkeypatch) -> None:
    from src.modules import non_qualified_calls as nq

    monkeypatch.setattr(app_module, 'submit_background_task', lambda callback, *args: callback(*args))
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    add_data_cdr(tmp_path, ['0xBB22', '0xcc33'])
    upload(client, 'Consolidated_Dataset_3.zip', zip_bytes(log_rows()))
    nq.sync_nq_calls(app_module.repository)

    def calls(**payload):
        response = client.post('/api/non-qualified-calls/calls', json=payload)
        assert response.status_code == 200, response.text
        return {call['join_id']: call for call in response.json()['calls']}

    listed = calls()
    assert {join_id: call['l3_log'] for join_id, call in listed.items()} == {'0xBB22': 'Data', '0xcc33': ''}
    assert list(calls(filters={'columns': {'l3_log': ['Data']}})) == ['0xBB22']
    assert list(calls(filters={'columns': {'l3_log': [nq.UNASSIGNED]}})) == ['0xcc33']
    assert list(calls(sort='l3_log', direction='desc'))[0] == '0xBB22'
    assert 'l3_log' in nq.OPTIONAL_COLUMNS
    detail = client.get(f"/api/non-qualified-calls/calls/{listed['0xBB22']['call_key']}").json()
    assert detail['call']['l3_log'] == 'Data'

    datasets = l3_datasets()
    app_module.add_l3_nq_calls(datasets)
    assert {item['l3']['nr_mode']: item['l3_nq_calls'] for item in datasets} == {'NSA': 0, 'SA': 1}
    sessions_of = l3_dt_logs.sessions_of_join_ids(app_module.repository, ['0xbb22', '0xAA11'])
    assert [session['ue'] for session in sessions_of['0xbb22']] == ['Data']
    assert [session['ue'] for session in sessions_of['0xaa11']] == ['A', 'B']
