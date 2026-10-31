"""Layer3 Logs: the parsed drivetest logs of each campaign, imported as one dataset per campaign."""

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
    assert 'Layer3 Logs' in card and 'UK_Q3_SA_2026' in card and '2 campaigns' in card and '3 sessions' in card
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
    assert 'not a Layer3 Logs delivery' in dataset['last_error'] and 'JoinID, UE' in dataset['last_error']


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


def record(**values) -> dict[str, str]:
    """A row of a delivery with the common fields of a voice session of UE A."""
    row = {'Log_Day': '2026-09-03', 'Campaign': 'UK_Q3_NSA_2026', 'Operator': '3', 'Session_Type': 'CALL', 'Call_Status': 'Failed',
           'JoinID': '0xaa11', 'UE': 'A', 'EventFullDate': '2026-09-03 08:08:16.000', 'Latitude': '51.5', 'Longitude': '-0.12',
           'RANConfiguration': 'LTE', 'IMSI': '234000000000001'}
    row.update({key: str(value) for key, value in values.items()})
    return row


def layer_rows() -> list[dict[str, str]]:
    """One record of every kind the layers of the KMZ files read, and some they leave out."""
    return [
        record(SourceTable='FactLTERadio', Radio_CarrierIndex='0', Radio_EARFCN='223', Radio_PhyCellId='114', Radio_RSRP='-85.1',
               Radio_RSRQ='-10', Radio_SINR='4.5', LTE_ECI='13226752'),
        record(SourceTable='FactLTERadio', Radio_CarrierIndex='1', Radio_EARFCN='6300', Radio_PhyCellId='167', Radio_RSRP='-99'),
        record(SourceTable='FactLTENeighbors', Neigh_DL_EARFCN='223', Neigh_PCI='35', Neigh_RSRP='-101', Neigh_RSRQ='-14'),
        record(SourceTable='FactLTEPUSCHStatisticsCarrier', PUSCH_PuschTxPower='23'),
        # An NR radio sample without RSRP still is a point of its NRARFCN and PCI layers.
        record(SourceTable='FactNR5GRadio', NRRadio_CarrierIndex='0', NRRadio_NRARFCN='628032', NRRadio_PCI='997',
               RANConfiguration='5G EN-DC'),
        record(SourceTable='FactNR5GLTENeighborList', MsgType='6605.0', NRLTENL_Technology='5G NR', NRLTENL_ARFCN='628032',
               NRLTENL_PCI='998', NRLTENL_RSRP='-95', RANConfiguration='5G EN-DC'),
        record(SourceTable='FactNR5GLTENeighborList', MsgType='6207.0', NRLTENL_Technology='LTE', NRLTENL_ARFCN='223',
               NRLTENL_PCI='35', NRLTENL_RSRP='-101', RANConfiguration='5G EN-DC'),
        # On LTE alone the neighbour list of NR repeats the LTE neighbours: no point.
        record(SourceTable='FactNR5GLTENeighborList', MsgType='6207.0', NRLTENL_Technology='LTE', NRLTENL_ARFCN='223',
               NRLTENL_PCI='35', NRLTENL_RSRP='-101'),
        record(SourceTable='FactEvent', Event_EventName='4G - Handover Attempt LTE PCell', Event_EventGroup='4G'),
        record(SourceTable='FactAdvancedTriggerEvent', ATE_EventFullName='5G EN-DC - SCG Failure NR SCG', ATE_EventTopGroup='_5G_EN_DC'),
        record(SourceTable='FactL3Messages', L3_Layer='5G-NAS', L3_SimpleMsgName='Registration request', L3_Direction='U'),
        record(SourceTable='FactL3Messages', L3_Layer='SIP', L3_SimpleMsgName='INVITE', L3_CombinedMsgNameSIPResponse='408 Request Timeout'),
        # A GSM sample without ARFCN nor RxLevel is no point.
        record(SourceTable='FactGSMRadio', RANConfiguration='GSM', GSMRadio_ARFCN='7', GSMRadio_BSIC='48'),
        record(SourceTable='FactGSMRadio', RANConfiguration='GSM'),
        # The same session exported under a second log day is drawn once.
        record(SourceTable='FactLTERadio', Log_Day='2026-09-04', Radio_CarrierIndex='0', Radio_EARFCN='223', Radio_PhyCellId='114',
               Radio_RSRP='-85.1'),
    ]


def test_the_points_of_the_layers_follow_the_kmz_files(tmp_path) -> None:
    import duckdb

    rows = layer_rows()
    header = sorted({key for row in rows for key in row})
    source = tmp_path / 'source.csv'
    source.write_bytes(csv_bytes(rows, header))
    parquet = tmp_path / 'source.parquet'
    with duckdb.connect() as duck:
        duck.execute(f"COPY (SELECT * FROM read_csv('{source}', all_varchar = true)) TO '{parquet}' (FORMAT parquet)")
    target = tmp_path / 'points.parquet'
    assert l3_dt_logs.build_points(parquet, target) == 12
    with duckdb.connect() as duck:
        points = duck.execute(f"SELECT kind, freq, pci, rsrp, grp, name, detail, ran FROM '{target}' ORDER BY kind, row").fetchall()
    by_kind = {}
    for point in points:
        by_kind.setdefault(point[0], []).append(point)
    assert {kind: len(items) for kind, items in by_kind.items()} == {
        'event': 2, 'gsm': 1, 'l3': 2, 'lte_ncell': 1, 'lte_pcell': 1, 'lte_scell': 1, 'lte_tx': 1, 'nr_lncell': 1, 'nr_ncell': 1,
        'nr_pcell': 1}
    assert by_kind['lte_pcell'][0][1:4] == (223, 114, -85.1)
    assert by_kind['nr_pcell'][0][1:4] == (628032, 997, None)
    assert sorted(point[4] for point in by_kind['event']) == ['4G', '5G EN-DC']
    assert sorted((point[4], point[5]) for point in by_kind['l3']) == [('NR-NAS', 'Registration request'), ('SIP', 'INVITE')]
    assert l3_dt_logs.frequency_label(223, 'LTE') == 'EARFCN 223 (B1, 2132.3 MHz)'
    assert l3_dt_logs.frequency_label(628032, 'NR') == 'NRARFCN 628032 (n78, 3420.48 MHz)'
    assert l3_dt_logs.frequency_label(152690, 'NR') == 'NRARFCN 152690 (n28, 763.45 MHz)'


def test_the_map_of_a_call_reads_its_layers_and_records(client, tmp_path, monkeypatch) -> None:
    from src.modules import non_qualified_calls as nq

    monkeypatch.setattr(app_module, 'submit_background_task', lambda callback, *args: callback(*args))
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    add_data_cdr(tmp_path, ['0xBB22'])
    rows = [*log_rows(), *[{**row, 'JoinID': '0xbb22', 'UE': 'Data', 'Campaign': 'UK_Q3_SA_2026'} for row in layer_rows()]]
    header = sorted({key for row in rows for key in row})
    client.post('/datasets-analysis/upload', files={'dataset_files': ('logs.csv', io.BytesIO(csv_bytes(rows, header)), 'text/csv')},
                data={'dataset_kinds': 'l3_dt_logs'}, follow_redirects=False)
    nq.sync_nq_calls(app_module.repository)
    call = client.post('/api/non-qualified-calls/calls', json={}).json()['calls'][0]
    assert call['l3_log'] == 'Data'
    layers = client.get(f"/api/non-qualified-calls/calls/{call['call_key']}/l3")
    assert layers.status_code == 200, layers.text
    payload = layers.json()
    data = payload['ues']['Data']
    kinds = [point[payload['columns'].index('kind')] for point in data['points']]
    assert kinds.count('lte_pcell') == 4 and 'event' in kinds and 'l3' in kinds
    assert data['track'][0][1:] == [52.4, -0.12] and len(data['track']) >= 3
    assert payload['channels']['LTE:223'] == 'EARFCN 223 (B1, 2132.3 MHz)'
    point = data['points'][kinds.index('l3')]
    found = client.get(f"/api/non-qualified-calls/calls/{call['call_key']}/l3/record",
                       params={'dataset_id': data['session']['dataset_id'], 'row': point[payload['columns'].index('row')]})
    assert found.status_code == 200
    assert found.json()['record']['SourceTable'] == 'FactL3Messages' and 'IMSI' not in found.json()['record']
    other = client.get(f"/api/non-qualified-calls/calls/{call['call_key']}/l3/record", params={'dataset_id': 999, 'row': 0})
    assert other.status_code == 404
    events = [row['action'] for row in app_module.repository.list_logs()]
    assert 'nq_call_l3_layers' in events


def weak_coverage_rows() -> list[dict[str, str]]:
    """A data test of 0xBB22 whose LTE PCell ends far below −115 dBm, with an SCG failure 2 s before its end."""
    rows = []
    for second in range(12):
        rows.append({**record(SourceTable='FactLTERadio', Radio_CarrierIndex='0', Radio_EARFCN='223', Radio_PhyCellId='114',
                              Radio_RSRP=str(-100 - second * 2), Radio_SINR='2'),
                     'JoinID': '0xBB22', 'UE': 'Data', 'Campaign': 'UK_Q3_SA_2026', 'Session_Type': 'httpBrowser',
                     'EventFullDate': f'2026-09-03 08:08:{10 + second:02d}.000', 'Latitude': str(52.4 + second / 1000)})
    rows.append({**record(SourceTable='FactEvent', Event_EventName='5G EN-DC - SCG Failure NR SCG', Event_EventGroup='5G EN-DC'),
                 'JoinID': '0xBB22', 'UE': 'Data', 'Campaign': 'UK_Q3_SA_2026', 'EventFullDate': '2026-09-03 08:08:19.000',
                 'Latitude': '52.409'})
    return rows


def test_the_dt_analyzer_rca_reads_the_layer_3_dt_logs_of_the_campaign_of_the_call(client, tmp_path, monkeypatch) -> None:
    from src.modules import non_qualified_calls as nq

    monkeypatch.setattr(app_module, 'submit_background_task', lambda callback, *args: callback(*args))
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    add_data_cdr(tmp_path, ['0xBB22'])
    nq.sync_nq_calls(app_module.repository)

    def dta():
        nq.refresh_dta_rca(app_module.repository)
        return client.post('/api/non-qualified-calls/calls', json={}).json()['calls'][0]['dta']

    before = dta()
    assert not str(before.get('dta_rule_key') or '').startswith('l3-')
    rows = weak_coverage_rows()
    header = sorted({key for row in rows for key in row})
    client.post('/datasets-analysis/upload', files={'dataset_files': ('logs.csv', io.BytesIO(csv_bytes(rows, header)), 'text/csv')},
                data={'dataset_kinds': 'l3_dt_logs'}, follow_redirects=False)
    with_log = dta()
    assert with_log['dta_rule_key'] == 'l3-lte-coverage', with_log
    assert (with_log['dta_category'], with_log['dta_cause']) == ('Poor Coverage LTE', 'Coverage')
    assert 'LTE RSRP at the failure (log)' in with_log['dta_evidence']
    assert 'Layer3 Logs: 5G EN-DC - SCG Failure NR SCG 2 s before the end' in with_log['dta_evidence']
    # Deleting the log calculates the calls of its campaign again, without it.
    dataset = next(item for item in l3_datasets())
    client.post(f"/datasets-analysis/delete/{dataset['id']}", follow_redirects=False)
    assert dta()['dta_rule_key'] == before['dta_rule_key']


def test_the_rules_of_a_workspace_take_the_rules_of_the_logs_and_keep_those_changed_by_hand() -> None:
    import json as json_module

    from src.modules import nq_dta_rca

    class Repository:
        def __init__(self, rules):
            self.state = {nq_dta_rca.RULES_STATE_KEY: json_module.dumps(rules)}

        def get_workspace_state(self, key):
            return self.state.get(key)

        def set_workspace_state(self, key, value):
            self.state[key] = value

    former = [{'input': key, 'op': op, 'value': value} for key, op, value in nq_dta_rca.CHANGED_RULES[4]['radio-link']]
    rules = [rule for rule in nq_dta_rca.default_rules() if not rule['key'].startswith('l3-')]
    for rule in rules:
        if rule['key'] == 'radio-link':
            rule['conditions'] = former
        if rule['key'] == 'handover':
            rule['conditions'] = [{'input': 'failure_text', 'op': 'contains', 'value': 'handover, ho'}]
        if rule['key'] in nq_dta_rca.CHANGED_RULES[4] and rule['key'] not in {'radio-link', 'handover'}:
            rule['conditions'] = [{'input': key, 'op': op, 'value': value} for key, op, value in nq_dta_rca.CHANGED_RULES[4][rule['key']]]
    repository = Repository(rules)
    added = nq_dta_rca.add_new_default_rules(repository, 4)
    renewed = nq_dta_rca.renew_changed_default_rules(repository, 4)
    assert len(added) == 13 and 'Radio link failure' in renewed and 'Handover failure' not in renewed
    stored = {rule['key']: rule for rule in nq_dta_rca.load_rules(repository)}
    assert any(condition['input'] == 'l3_signalling' for condition in stored['radio-link']['conditions'])
    assert stored['handover']['conditions'] == [{'input': 'failure_text', 'op': 'contains', 'value': 'handover, ho'}]
    order = [rule['key'] for rule in nq_dta_rca.load_rules(repository)]
    assert order.index('pci-collision') < order.index('l3-scg-failure-coverage') < order.index('lte-coverage')


def test_the_map_of_a_call_gives_the_hints_of_its_layer_3_dt_logs(client, tmp_path, monkeypatch) -> None:
    from src.modules import non_qualified_calls as nq

    monkeypatch.setattr(app_module, 'submit_background_task', lambda callback, *args: callback(*args))
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    add_data_cdr(tmp_path, ['0xBB22'])
    rows = weak_coverage_rows()
    header = sorted({key for row in rows for key in row})
    client.post('/datasets-analysis/upload', files={'dataset_files': ('logs.csv', io.BytesIO(csv_bytes(rows, header)), 'text/csv')},
                data={'dataset_kinds': 'l3_dt_logs'}, follow_redirects=False)
    nq.sync_nq_calls(app_module.repository)
    call = client.post('/api/non-qualified-calls/calls', json={}).json()['calls'][0]
    response = client.get(f"/api/non-qualified-calls/calls/{call['call_key']}/map")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['call']['l3_log'] == 'Data'
    hints = {check['key']: check for check in payload['diagnosis'] if check.get('source') == 'l3'}
    assert {'l3_scg', 'l3_lte_coverage'} <= set(hints)
    assert hints['l3_scg']['level'] == 'bad' and '2 s before the end' in hints['l3_scg']['detail']
    assert hints['l3_scg']['at']['ue'] == 'Data' and hints['l3_scg']['at']['ms'] > 0
    assert 'LTE RSRP -117 dBm in the last 5 s of the log' in hints['l3_lte_coverage']['detail']
    event = json.loads(next(row['details'] for row in app_module.repository.list_logs() if row['action'] == 'nq_call_map'))
    assert 'l3_scg' in event['to_check']


def test_layer_3_maps_gives_a_grid_zoomed_out_and_the_points_of_the_area_zoomed_in(client, tmp_path, monkeypatch) -> None:
    from src.modules import non_qualified_calls as nq

    monkeypatch.setattr(app_module, 'submit_background_task', lambda callback, *args: callback(*args))
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    add_data_cdr(tmp_path, ['0xBB22', '0xCC33'])
    rows = weak_coverage_rows()
    header = sorted({key for row in rows for key in row})
    client.post('/datasets-analysis/upload', files={'dataset_files': ('logs.csv', io.BytesIO(csv_bytes(rows, header)), 'text/csv')},
                data={'dataset_kinds': 'l3_dt_logs'}, follow_redirects=False)
    nq.sync_nq_calls(app_module.repository)

    def maps(**payload):
        response = client.post('/api/non-qualified-calls/l3-maps', json=payload)
        assert response.status_code == 200, response.text
        return response.json()

    country = maps(filters={}, zoom=6, layers=['lte_pcell:rsrp', 'event'], grid='lte_pcell:rsrp')
    # Every NQ call of the filters (those without Layer3 Logs too), with what colours them on the map.
    assert country['mode'] == 'grid' and sorted(call['join_id'] for call in country['calls']) == ['0xBB22', '0xCC33']
    assert country['calls_count'] == 2 and country['calls_with_log'] == 1 and all(call['kind'] for call in country['calls'])
    assert country['sessions'] == 1 and country['grid']['metric'] == 'rsrp' and country['grid']['cells']
    assert sum(cell[3] for cell in country['grid']['cells']) == 12 and country['extent'][0] == 52.4
    # Below the zoom of the events, the grid alone; no sites or samples without an area.
    assert country['ues'] == {} and country['routes'] == [] and country['sites'] is None and country['tests'] is None
    assert country['zooms'] == {'grid': 13, 'events': 10, 'sites': 11, 'tests': 13} and country['classes']['rsrp']
    assert [(level['label'], level['lower']) for level in country['classes']['rsrq']][:2] == [('Excellent', -10.0), ('Very good', -12.0)]
    assert 'focus_operators' in country and 'focus_labels' in country
    # From the zoom of the events, those of the area over the grid; the NQ calls only when asked for.
    town = maps(filters={}, zoom=11, bbox=[52.3, -0.4, 52.5, 0.2], layers=['lte_pcell:rsrp', 'event'], with_calls=False)
    assert town['mode'] == 'grid' and town['calls'] is None and town['calls_count'] == 2
    assert {point[town['columns'].index('kind')] for point in town['ues']['0xBB22|Data']['points']} == {'event'}
    street = maps(filters={}, zoom=16, bbox=[52.39, -0.2, 52.42, 0.0], layers=['lte_pcell:rsrp', 'event'], route=True, sites=True, tests=True)
    assert street['mode'] == 'points' and list(street['ues']) == ['0xBB22|Data']
    kinds = {point[street['columns'].index('kind')] for point in street['ues']['0xBB22|Data']['points']}
    assert kinds == {'lte_pcell', 'event'}
    # The route of each session in time order, and the sites and RSRP / SINR samples of the area.
    [route] = street['routes']
    assert route['key'] == '0xBB22|Data' and route['session']['join_id'] == '0xBB22' and len(route['points']) > 1
    assert [point[0] for point in route['points']] == sorted(point[0] for point in route['points'])
    assert street['sites']['sites'] == [] and isinstance(street['tests']['rows'], list)
    elsewhere = maps(filters={}, zoom=16, bbox=[40.0, 10.0, 40.1, 10.1], layers=['lte_pcell:rsrp'])
    assert elsewhere['ues'] == {} and elsewhere['sessions'] == 1
    around = maps(join_ids=['0xbb22', '0xcc33'], exclude='0xCC33', zoom=18, layers=['event'])
    assert around['calls'] == [] and list(around['ues']) == ['0xBB22|Data']
    assert any(row['action'] == 'nq_l3_maps' for row in app_module.repository.list_logs())


def test_layer_3_maps_reads_the_samples_of_the_area_from_a_copy_of_each_cdr(client, monkeypatch) -> None:
    import numpy as np

    from src.modules import non_qualified_calls as nq
    from src.modules import nq_call_map

    nq.sync_nq_calls(app_module.repository)
    entry = {'kind': 'data', 'latitude': np.array([52.40, 52.41, 53.0]), 'longitude': np.array([-0.10, -0.11, 1.0]),
             'operators': ['Vodafone UK'], 'operator': np.zeros(3, dtype=np.int32), 'tests': ['HTTP DL'], 'test': np.zeros(3, dtype=np.int32),
             'failed': np.array([True, False, False]),
             'start': np.array(['2026-09-03 09:00:00', '2026-09-03 09:01:00', '2026-09-03 09:02:00'], dtype=object),
             'lte_rsrp': np.array([-101.0, -95.0, np.nan], dtype=np.float32), 'lte_sinr': np.array([2.0, 8.0, 1.0], dtype=np.float32),
             'nr_rsrp': np.full(3, np.nan, dtype=np.float32), 'nr_sinr': np.full(3, np.nan, dtype=np.float32)}
    reads = []
    monkeypatch.setattr(nq_call_map, '_dataset_tests', lambda repository, dataset_id: reads.append(dataset_id) or entry)
    repository = app_module.repository
    area = nq_call_map.area_tests(repository, [7], [52.3, -0.3, 52.5, 0.0], lambda value: 'VFUK')
    # The tests of the area only, as the map of a call has them (the CDR read once, then from its copy in the cache).
    assert area['total'] == 2 and area['operators'] == ['VFUK'] and area['kinds'] == ['data'] and not area['truncated']
    assert sorted(row[5] for row in area['rows']) == [-101.0, -95.0] and {row[4] for row in area['rows']} == {0, 1}
    assert area['cdrs'][0]['dataset_id'] == 7 and area['test_names'] == ['HTTP DL']
    assert nq_call_map.area_tests(repository, [7], [52.0, -2.0, 54.0, 2.0])['total'] == 3 and reads == [7]
    # More tests than the map shows: an even sample of them.
    monkeypatch.setattr(nq_call_map, 'MAX_AREA_TESTS', 1)
    sampled = nq_call_map.area_tests(repository, [7], [52.0, -2.0, 54.0, 2.0])
    assert sampled['total'] == 3 and len(sampled['rows']) == 1 and sampled['truncated']
