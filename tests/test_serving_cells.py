"""Serving-cell Vendor mapping: eligible networks, snapshot dates, distance guard and the Serving Networks."""

import json
from datetime import date

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from conftest import wait_for_background_dataset_work
from src.modules.cdr import cdr_store
from src.modules.network import network_inventory as ni
from src.modules.network import serving_cells as sc
from src.modules.core.repository import local_now_iso

LEEDS = (-1.55, 53.80)
SWAPPED_CELL = str(1491 * 256 + 110)  # Huawei in August, Ericsson after the swap of September
VODAFONE_CELL = str(26141 * 256 + 26)
THREE_CELL = str(15660 * 16384 + 11)


def login(client):
    client.cookies.clear()
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303


def _inventory(tmp_path, name, rows, snapshot_date, kind='network_inventory'):
    source = tmp_path / name
    source.write_text('inventory', encoding='utf-8')
    dataset_id, _created = core.repository.add_dataset(name, str(source), 'super')
    frame = pd.DataFrame(rows)
    core.repository.replace_dataset_rows(dataset_id, frame)
    core.repository.update_dataset_profile(
        dataset_id, status='ready', progress=100, dataset_kind=kind, row_count=len(frame), column_count=len(frame.columns),
        processed_at=local_now_iso(), snapshot_date=snapshot_date,
    )
    return dataset_id


def _cells(vendor_of_swapped_cell):
    return [
        {'Network': 'Vodafone', 'Host Network': 'Vodafone', 'Vendor': vendor_of_swapped_cell, 'Site_ID': 'S1', 'eNodeB ID': 1491,
         'Cell ID': 110, 'Local Cell ID': 7, 'Longitude': LEEDS[0], 'Latitude': LEEDS[1], 'eMOCNScenario': 'NNS'},
        {'Network': 'Vodafone', 'Host Network': 'Telefonica', 'Vendor': 'NSN', 'Site_ID': 'S2', 'eNodeB ID': 26141,
         'Cell ID': 26, 'Local Cell ID': 26, 'Longitude': LEEDS[0] + 0.01, 'Latitude': LEEDS[1], 'eMOCNScenario': 'S0'},
        {'Network': 'H3G', 'Host Network': 'H3G', 'Vendor': 'Samsung', 'Site_ID': 'S3', 'gNodeB ID': 15660, 'Cell ID': 11,
         'Local Cell ID': 11, 'Longitude': LEEDS[0], 'Latitude': LEEDS[1] + 0.01},
    ]


def _cdr(measured: str) -> pd.DataFrame:
    return pd.DataFrame({
        'Operator': ['Vodafone UK', '3', 'Vodafone SA', 'EE', 'Vodafone UK', 'O2 (UK)'],
        'Cell_ID': [SWAPPED_CELL, f'{SWAPPED_CELL}->{VODAFONE_CELL}', THREE_CELL, SWAPPED_CELL, SWAPPED_CELL, VODAFONE_CELL],
        'Test_Start_Longitude': [LEEDS[0], LEEDS[0], LEEDS[0], LEEDS[0], -0.12, LEEDS[0]],
        'Test_Start_Latitude': [LEEDS[1], LEEDS[1], LEEDS[1], LEEDS[1], 51.50, LEEDS[1]],
        'Test_Start_Time': [f'{measured} 10:00:00'] * 6,
    })


def test_serving_networks_defaults_csv_and_snapshot_preference():
    assert sc.serving_families('Vodafone SM') == ('vodafone', 'three')
    assert sc.serving_families('3') == ('three', 'vodafone')
    assert sc.serving_families('Lebara') == ('vodafone', 'three')
    assert sc.serving_families('O2 (UK)') == ('o2',)
    config = sc.normalise_serving_networks({'rows': sc.parse_serving_networks_csv('Operator,Serving Networks\nO2,O2; Vodafone\n'), 'max_distance_km': '12'})
    assert sc.serving_families('O2 (UK)', config) == ('o2', 'vodafone') and config['max_distance_km'] == 12
    assert sc.serving_networks_csv(config['rows']) == 'Operator,Serving Networks\nO2,O2; Vodafone\n'
    snapshots = [{'dataset_id': 1, 'snapshot_date': '2026-08-20'}, {'dataset_id': 2, 'snapshot_date': '2026-09-17'}]
    assert sc.rank_snapshots(snapshots, date(2026, 9, 10)) == {2: 0, 1: 1}
    assert sc.rank_snapshots(snapshots, date(2026, 6, 1)) == {1: 0, 2: 1}
    assert sc.rank_snapshots(snapshots, None) == {2: 0, 1: 1}
    # Beside a Multivendor Mapping every other source comes last, however close its date is.
    sources = [{'dataset_id': 1, 'kind': 'mapping_vodafone', 'snapshot_date': '2026-08-20'}, {'dataset_id': 2, 'kind': 'network_inventory', 'snapshot_date': '2026-09-17'},
               {'dataset_id': 3, 'kind': 'multivendor_mapping', 'snapshot_date': '2026-10-05'}, {'dataset_id': 4, 'kind': 'mapping_three', 'snapshot_date': '2026-08-20'}]
    assert sc.complement_snapshots(sources) == {1, 2, 4} and sc.complement_snapshots(sources[:2]) == set()
    assert sc.rank_snapshots(sources, date(2026, 8, 20))[3] == 0
    assert sc.rank_snapshots(sources, date(2026, 8, 20))[2] == 3
    # The mapping gives the Vendor even when an older file has the cell in the Operator's own network.
    endpoints = pd.DataFrame({'row': [0, 1], 'end': ['first', 'first'], 'cell': ['10', '20'], 'longitude': [float('nan')] * 2, 'latitude': [float('nan')] * 2})
    cells = pd.DataFrame({'dataset_id': [1, 3, 1], 'cell_identity': ['10', '10', '20'], 'technology': 'LTE', 'network': ['Vodafone', '3', 'Vodafone'], 'network_family': ['vodafone', 'three', 'vodafone'],
                          'host_network': '', 'vendor': ['Huawei', 'Ericsson', 'NSN'], 'site_id': '', 'emocn': '', 'latitude': float('nan'), 'longitude': float('nan')})
    operators = pd.Series(['Vodafone UK', 'Vodafone UK'])
    dates = {1: '2026-08-20', 3: '2026-10-05'}
    assert sc.match_serving_cells(endpoints, operators, cells, {3: 0, 1: 1}, dates, None, 30.0, (), {1})['vendor'].tolist() == ['Ericsson', 'NSN']
    assert sc.match_serving_cells(endpoints, operators, cells, {1: 0, 3: 1}, dates, None, 30.0)['vendor'].tolist() == ['Huawei', 'NSN']
    assert sc.cdr_reference_date(_cdr('2026-09-10')) == date(2026, 9, 10)
    assert sc.cdr_reference_date(pd.DataFrame({'x': [1]}), '20260623 Final Data CDR.xlsx') == date(2026, 6, 23)


def test_samples_take_the_vendor_of_their_serving_cell_from_the_closest_snapshot(client, tmp_path):
    login(client)
    older = _inventory(tmp_path, 'Multivendor_Mapping_VFUK.csv', _cells('Huawei'), '2026-08-20')
    newer = _inventory(tmp_path, '260917_Cell_Config.zip', _cells('Ericsson'), '2026-09-17')
    september = sc.assign_serving_vendors(_cdr('2026-09-10'), 'data', core.repository, [older, newer])
    june = sc.assign_serving_vendors(_cdr('2026-06-01'), 'data', core.repository, [older, newer])

    assert september['Operator_Vendor'].tolist() == [
        'Vodafone_Ericsson',
        # 3 is served by a Vodafone cell (eMOCN); its two ends have different vendors.
        '3_Ericsson (Mixed)',
        # Vodafone SA is served by the NR cell of H3G.
        'Vodafone SA_Samsung',
        # No snapshot holds EE cells: the colliding identity is not EE's.
        'EE - All',
        # The cell is 280 km away from the sample: not its serving cell, and no other cell served it.
        'Vodafone_Unknown',
        # O2 is served only by O2 cells by default.
        'O2 (UK) - All',
    ]
    assert june['Operator_Vendor'].tolist()[0] == 'Vodafone_Huawei'
    assert september['Serving_Network'].tolist()[:3] == ['Vodafone', 'Vodafone', 'H3G']
    assert september['Serving_Host_Network'].tolist()[:2] == ['Vodafone', 'Vodafone']
    assert september['Serving_Site_ID'].tolist()[:3] == ['S1', 'S1', 'S3']
    assert september['Serving_eMOCN_Scenario'].tolist()[0] == 'NNS'
    assert september['Serving_Inventory_Snapshot'].tolist()[0] == '2026-09-17' and june['Serving_Inventory_Snapshot'][0] == '2026-08-20'
    assert september['Serving_Distance_km'][0] == 0 and pd.isna(september['Serving_Distance_km'][4])

    # Serving Networks let O2 be served by the Vodafone cells hosted for it.
    config = sc.normalise_serving_networks({'rows': [{'operator': 'O2', 'networks': ['O2', 'Vodafone']}]})
    shared = sc.assign_serving_vendors(_cdr('2026-09-10'), 'data', core.repository, [newer], config=config)
    assert shared['Operator_Vendor'].tolist()[5] == 'O2 (UK)_NSN'


def test_map_dialog_marks_outdated_vendor_mappings_and_serving_networks_are_saved(client, tmp_path):
    login(client)
    inventory = _inventory(tmp_path, '260917_Cell_Config.zip', _cells('Ericsson'), '2026-09-17')
    source = tmp_path / 'UK Data CDR.xlsx'
    source.write_text('cdr', encoding='utf-8')
    cdr_id, _created = core.repository.add_dataset(source.name, str(source), 'super')
    rows = _cdr('2026-09-10')
    core.repository.replace_dataset_rows(cdr_id, rows)
    core.repository.update_dataset_profile(
        cdr_id, status='ready', progress=100, dataset_kind='data', nr_mode='NSA', cdr_stage='final', row_count=len(rows),
        column_count=len(rows.columns), processed_at=local_now_iso(), normalization_version=core.DATASET_NORMALIZATION_VERSION,
        vendor_mapping_applied=1,
    )
    # Mapped before the serving-cell rule: outdated and selected when the dialog opens.
    assert 'value="%d" data-vendor-mapping-cdr-choice checked' % cdr_id in client.get('/workspace').text
    mapped = client.post('/workspace/map-mappings', data={
        'cdr_dataset_ids': str(cdr_id), 'vendor_source': 'inventory', 'network_inventory_dataset_ids': str(inventory),
    }, follow_redirects=False)
    assert mapped.status_code == 303
    wait_for_background_dataset_work()
    stored = core.repository.load_dataset_rows(cdr_id, ['Operator_Vendor', 'Serving_Network'], {})
    assert stored['Operator_Vendor'].tolist()[0] == 'Vodafone_Ericsson' and stored['Serving_Network'].tolist()[0] == 'Vodafone'
    workspace = client.get('/workspace').text
    assert 'value="%d" data-vendor-mapping-cdr-choice>' % cdr_id in workspace and 'class="vendor-mapping-outdated"' not in workspace

    saved = client.post('/workspace-config/serving-networks/save', data={
        'serving_networks_csv': 'Operator,Serving Networks\nO2,O2; Vodafone\n', 'max_distance_km': '20',
    }, follow_redirects=False)
    assert saved.status_code == 303 and 'serving_networks_notice' in saved.headers['location']
    assert sc.load_serving_networks(core.repository) == {'max_distance_km': 20.0, 'rows': [{'operator': 'O2', 'networks': ['O2', 'Vodafone']}]}
    assert 'class="vendor-mapping-outdated"' in client.get('/workspace').text
    config_page = client.get('/workspace-config').text
    assert 'id="serving-networks"' in config_page
    # The editor lists every Operator with its networks in order of preference and its defaults.
    editor = json.loads(config_page.split('data-serving-networks-data>', 1)[1].split('</script>', 1)[0])
    rows = {row['operator']: row for row in editor['rows']}
    assert rows['O2'] == {'operator': 'O2', 'networks': ['o2', 'vodafone'], 'defaults': ['o2'], 'configured': True}
    assert rows['Three']['networks'] == ['three', 'vodafone'] and rows['Three']['configured'] is False
    assert [item['label'] for item in editor['networks']][:4] == ['Vodafone', '3', 'O2', 'EE']
    assert client.post('/workspace-config/serving-networks/save', data={'serving_networks_csv': 'O2', 'max_distance_km': '20'},
                       follow_redirects=False).headers['location'].count('serving_networks_error') == 1
    assert any(row['action'] == 'network_serving_networks_saved' for row in core.repository.list_logs(limit=20))
    # The Serving Networks travel with Mappings & Reference Data.
    document = json.loads(core._mappings_reference_data_archive_payload(core.active_workspace))
    assert document['serving_networks']['rows'] == [{'operator': 'O2', 'networks': ['O2', 'Vodafone']}]


def test_inventory_snapshots_are_built_once_and_rebuilt_when_their_operator_changes(client, tmp_path):
    inventory = _inventory(tmp_path, 'O2_Network_Inventory.csv', [{'ECI': '1001', 'Vendor': 'Ericsson'}], None)
    snapshot = next(item for item in ni.ensure_inventory_cells(core.repository) if item['dataset_id'] == inventory)
    # Without an Operator or a Network column its cells belong to no network: they serve nobody.
    assert set(snapshot['families']) == {''}
    core.repository.update_dataset_profile(inventory, dataset_operator='O2')
    snapshot = next(item for item in ni.ensure_inventory_cells(core.repository) if item['dataset_id'] == inventory)
    assert set(snapshot['families']) == {'o2'} and snapshot['cells'] == 1


def test_mapping_the_vendor_of_a_cdr_in_its_copy_rewrites_only_its_columns(client, tmp_path, monkeypatch):
    login(client)
    first = _inventory(tmp_path, '260917_Cell_Config.zip', _cells('Ericsson'), '2026-09-17')
    source = tmp_path / 'UK Data CDR.xlsx'
    source.write_text('cdr', encoding='utf-8')
    cdr_id, _created = core.repository.add_dataset(source.name, str(source), 'super')
    rows = _cdr('2026-09-10')
    core.repository.replace_dataset_rows(cdr_id, rows)
    core.repository.update_dataset_profile(
        cdr_id, status='ready', progress=100, dataset_kind='data', nr_mode='NSA', cdr_stage='final', row_count=len(rows),
        column_count=len(rows.columns), processed_at=local_now_iso(), normalization_version=core.DATASET_NORMALIZATION_VERSION,
        vendor_mapping_applied=1,
    )
    assert client.post('/workspace/map-mappings', data={
        'cdr_dataset_ids': str(cdr_id), 'vendor_source': 'inventory', 'network_inventory_dataset_ids': str(first),
    }, follow_redirects=False).status_code == 303
    wait_for_background_dataset_work()
    repository = core.Repository(core.active_workspace.database_path, global_db_path=core.repository.global_db_path)
    cdr_store.start_store_sync(repository, lambda run: run(), lambda: cdr_store.included_cdrs(repository))
    cdr_store.empty_combined_table(repository, 'data')
    with core.repository.connection() as connection:
        assert cdr_id in cdr_store.shadows(connection)
    assert core.repository._combined_in_copies('data')
    others = cdr_store.read_cdr(core.repository.db_path, 'data', cdr_id, ['Operator', 'Cell_ID'])

    # A newer inventory changes the Vendor of the swapped cell: only the Vendor columns are read and rewritten.
    newer = _inventory(tmp_path, '261001_Cell_Config.zip', _cells('Samsung'), '2026-10-01')
    options = json.loads(core.repository.get_dataset(cdr_id)['processing_options_json'] or '{}')
    core.repository.update_dataset_profile(cdr_id, processing_options_json=json.dumps({**options, 'network_inventory_dataset_ids': [newer]}))
    monkeypatch.setattr(core, '_reporting_frame', lambda *_args: pytest.fail('The whole CDR was read.'))
    core.process_vendor_mapping(cdr_id, 'super', None, None, core.repository)
    row = core.repository.get_dataset(cdr_id)
    assert row['status'] == 'ready' and row['vendor_mapping_applied']
    stored = cdr_store.read_cdr(core.repository.db_path, 'data', cdr_id, ['Operator', 'Cell_ID', 'Operator_Vendor', 'Vendor', 'Serving_Distance_km'])
    assert stored['Operator_Vendor'].tolist()[0] == 'Vodafone_Samsung' and stored['Vendor'].tolist()[0] == 'Samsung'
    assert pd.api.types.is_float_dtype(stored['Serving_Distance_km'])
    assert stored[['Operator', 'Cell_ID']].equals(others)
    assert 'Samsung' in json.loads(row['filter_options_json'])['vendor']
    with core.repository.connection() as connection:
        assert cdr_id in cdr_store.shadows(connection)
        assert 'Samsung' in connection.execute('SELECT vendors_only_json FROM cdr_catalogues WHERE dataset_id = ?', (cdr_id,)).fetchone()[0]

    # An Auto-calculated Field that reads the Vendor needs the whole CDR.
    monkeypatch.setattr(core, 'load_repository_calculated_dimensions', lambda _repository: ('Vendor_Group from Vendor',))
    assert not core.map_vendor_in_copy(core.serialize_dataset_row(row), None, None, [newer], core.repository)


def test_the_region_mapping_a_cdr_already_has_keeps_the_mapping_vendor_only(client, tmp_path, monkeypatch):
    login(client)
    inventory = _inventory(tmp_path, '260917_Cell_Config.zip', _cells('Ericsson'), '2026-09-17')
    regions = _inventory(tmp_path, 'Regions.zip', [{'Region': 'North'}], '2026-09-17', kind='regions')
    other = _inventory(tmp_path, 'Regions_2.zip', [{'Region': 'South'}], '2026-09-17', kind='regions')
    source = tmp_path / 'UK Data CDR.xlsx'
    source.write_text('cdr', encoding='utf-8')
    cdr_id, _created = core.repository.add_dataset(source.name, str(source), 'super')
    rows = _cdr('2026-09-10')
    core.repository.replace_dataset_rows(cdr_id, rows)
    core.repository.update_dataset_profile(
        cdr_id, status='ready', progress=100, dataset_kind='data', nr_mode='NSA', cdr_stage='final', row_count=len(rows), column_count=len(rows.columns),
        processed_at=local_now_iso(), normalization_version=core.DATASET_NORMALIZATION_VERSION, vendor_mapping_applied=1, region_mapping_applied=1, region_mapping_dataset_id=regions,
    )
    calls = []
    monkeypatch.setattr(core, 'enqueue_vendor_mapping', lambda *_args, **_kwargs: calls.append('vendor'))
    monkeypatch.setattr(core, 'enqueue_dataset_processing', lambda *_args, **_kwargs: calls.append('whole'))

    def mapped_with(region):
        calls.clear()
        assert client.post('/workspace/map-mappings', data={
            'cdr_dataset_ids': str(cdr_id), 'vendor_source': 'inventory', 'network_inventory_dataset_ids': str(inventory), 'region_mapping_dataset_id': str(region),
        }, follow_redirects=False).status_code == 303
        return calls[0]

    assert mapped_with(regions) == 'vendor'
    assert mapped_with(other) == 'whole'
    # Polygons processed after the CDR was mapped are applied again.
    core.repository.update_dataset_profile(regions, processed_at=core.datetime(2099, 1, 1).astimezone().isoformat())
    assert mapped_with(regions) == 'whole'
