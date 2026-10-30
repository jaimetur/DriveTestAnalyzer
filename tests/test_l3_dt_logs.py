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
