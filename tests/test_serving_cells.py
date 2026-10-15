"""Serving-cell Vendor mapping: eligible networks, snapshot dates, distance guard and the Serving Networks."""

import json
from datetime import date

import pandas as pd

import src.DriveTestAnalyzer as core
from conftest import wait_for_background_dataset_work
from src.modules import network_inventory as ni
from src.modules import serving_cells as sc
from src.modules.repository import local_now_iso

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
        # The cell is 280 km away from the sample: not its serving cell.
        'Vodafone_Mixed (non-Ericsson)',
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
    assert 'id="serving-networks"' in config_page and 'O2 → Vodafone' in config_page
    assert client.post('/workspace-config/serving-networks/save', data={'serving_networks_csv': 'O2', 'max_distance_km': '20'},
                       follow_redirects=False).headers['location'].count('serving_networks_error') == 1
    assert any(row['action'] == 'network_serving_networks_saved' for row in core.repository.list_logs(limit=20))
    # The Serving Networks travel with Mappings & Reference Data.
    document = json.loads(core._mappings_reference_data_archive_payload(core.active_workspace))
    assert document['serving_networks']['rows'] == [{'operator': 'O2', 'networks': ['O2', 'Vodafone']}]


def test_inventory_snapshots_are_built_once_and_rebuilt_when_their_operator_changes(tmp_path):
    inventory = _inventory(tmp_path, 'O2_Network_Inventory.csv', [{'ECI': '1001', 'Vendor': 'Ericsson'}], None)
    snapshot = next(item for item in ni.ensure_inventory_cells(core.repository) if item['dataset_id'] == inventory)
    # Without an Operator or a Network column its cells belong to no network: they serve nobody.
    assert set(snapshot['families']) == {''}
    core.repository.update_dataset_profile(inventory, dataset_operator='O2')
    snapshot = next(item for item in ni.ensure_inventory_cells(core.repository) if item['dataset_id'] == inventory)
    assert set(snapshot['families']) == {'o2'} and snapshot['cells'] == 1
