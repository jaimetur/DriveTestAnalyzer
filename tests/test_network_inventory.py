"""Network Inventories of any Operator: uploaded with their Operator and, with cells and Vendors, used to map Vendors."""

import io
import json
from datetime import date

import pandas as pd

import src.DriveTestAnalyzer as core
from conftest import wait_for_background_dataset_work
from src.modules.cdr_reporting import assign_cdr_vendors, build_inventory_vendor_lookup, inventory_vendor_columns, operator_key
from src.modules.cell_identity import nr_nci, nr_nci_series
from src.modules.inventory_insights import snapshot_choice
from src.modules.network_inventory import infer_snapshot_date, list_inventory_snapshots, normalise_inventory
from src.modules.repository import local_now_iso
from src.modules.serving_cells import vendor_mapping_signature


def login(client):
    client.cookies.clear()
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303


def test_network_inventory_columns_and_cells():
    assert inventory_vendor_columns(['Site', 'ECI', 'OEM']) == {'vendor': 'OEM', 'cell': 'ECI'}
    assert inventory_vendor_columns(['eNB ID', 'Local Cell ID', 'Vendor']) == {'vendor': 'Vendor', 'enodeb': 'eNB ID', 'local_cell': 'Local Cell ID'}
    assert inventory_vendor_columns(['Site', 'Latitude', 'Longitude']) is None
    assert build_inventory_vendor_lookup(pd.DataFrame({'ECI': [1001.0, 1002], 'Vendor': ['Nokia', 'Ericsson']})) == {'1001': 'Nokia', '1002': 'Ericsson'}
    assert build_inventory_vendor_lookup(pd.DataFrame({'eNodeB ID': [10], 'Local Cell ID': [3], 'Vendor': ['Samsung']})) == {str(10 * 256 + 3): 'Samsung'}


def test_network_inventory_cells_take_the_identity_they_broadcast():
    # LTE and NR rows of one inventory: the Cell ID, not the internal Local Cell ID, completes the
    # identity, and NR cells of 22-bit gNodeB IDs are gNodeB ID × 16384 + Cell ID.
    inventory = pd.DataFrame({
        'eNodeB ID': [1491, 13008, None], 'gNodeB ID': [None, None, 16628], 'gNodeB ID Length': [None, None, 22.0],
        'Cell ID': [110, None, '515.000'], 'Local Cell ID': [7, 1, 10], 'OP/ Vendor': ['Huawei', 'Ericsson', 'Nokia'],
    })
    assert build_inventory_vendor_lookup(inventory) == {
        str(1491 * 256 + 110): 'Huawei', str(13008 * 256 + 1): 'Ericsson', str(16628 * 16384 + 515): 'Nokia',
    }


def test_nr_cells_whose_cell_id_is_already_their_nci_keep_it():
    # A Cell ID above the cell part is the NCI of its gNodeB as it is; one of another gNodeB gives no identity.
    nci = 26774 * 16384 + 527
    gnodeb, cell, local = [26774, 26774, 9346, 16628], [nci, nci, 416973229, 515], [nci, 7, 416973229, 10]
    frame = pd.DataFrame({'gNodeB ID': gnodeb, 'Cell ID': cell, 'Local Cell ID': local})
    series = nr_nci_series(frame['gNodeB ID'], frame['Cell ID'], frame['Local Cell ID'])
    # The second row has a usable Local Cell ID, which comes first as ever.
    expected = [nci, 26774 * 16384 + 7, None, 16628 * 16384 + 515]
    assert [None if pd.isna(value) else int(value) for value in series] == expected
    assert [nr_nci(*row) for row in zip(gnodeb, cell, local, strict=True)] == expected
    assert nr_nci(26774, nci, None, 24) is None
    cells = normalise_inventory(frame.assign(**{'OP/ Vendor': 'NSN', 'Network': 'Vodafone', 'source_row': range(1, 5)}), 'multivendor_mapping')
    assert cells['cell_identity'].tolist() == [str(nci), str(26774 * 16384 + 7), str(16628 * 16384 + 515)]
    # The NCI column of a Cell Configuration KMZ doubles those identities: the CDRs report the Cell ID.
    kmz = pd.DataFrame({'gNodeB ID': [24096], 'Cell ID': [394789379], 'NCI': [789578243], 'OP/ Vendor': ['NSN'], 'Network': ['Telefonica'], 'source_row': [1]})
    assert normalise_inventory(kmz, 'network_inventory')['cell_identity'].tolist() == ['394789379']


def test_network_inventories_map_the_vendor_of_their_operator():
    frame = pd.DataFrame({
        'Operator': ['O2', 'O2', 'O2', 'EE', 'Vodafone'],
        'Cell_ID_A': ['1001 -> 1001', '1001 -> 1002', '9', '1001', '1001'],
    })
    lookups = {operator_key('O2'): {'1001': 'Ericsson', '1002': 'Nokia'}}
    mapped = assign_cdr_vendors(frame, inventory_lookups=lookups)
    assert mapped['Operator_Vendor'].tolist() == ['O2_Ericsson', 'O2_Ericsson (Mixed)', 'O2_Mixed (non-Ericsson)', 'EE - All', 'Vodafone UK - All']
    assert mapped['Vendor'].tolist() == ['Ericsson', 'Ericsson (Mixed)', 'Mixed (non-Ericsson)', 'EE - All', 'Vodafone UK - All']


def test_inventory_upload_keeps_the_snapshot_date_chosen_or_found_in_its_name(client):
    login(client)
    inventory = 'Site,ECI,Vendor\nS1,1001,Ericsson\n'
    files = [('dataset_files', (name, io.BytesIO(inventory.encode()), 'text/csv')) for name in ('260917_O2_Inventory.csv', '250101_O2_Old_Inventory.csv')]
    response = client.post('/datasets-analysis/upload', data={
        'dataset_kinds': ['network_inventory', 'network_inventory'], 'dataset_operators': ['', ''], 'snapshot_dates': ['2026-08-01', ''],
    }, files=files, follow_redirects=False)
    assert response.status_code == 303
    wait_for_background_dataset_work()
    rows = {row['file_name']: row for row in core.repository.list_datasets()}
    # The date chosen in the upload replaces the one in the file name; without one, the file name gives it.
    assert rows['260917_O2_Inventory.csv']['snapshot_date'] == '2026-08-01'
    assert not rows['250101_O2_Old_Inventory.csv']['snapshot_date']
    assert core.effective_snapshot_date(rows['250101_O2_Old_Inventory.csv']) == '2025-01-01'
    logged = {json.loads(row['details'])['file']: json.loads(row['details']) for row in core.repository.list_logs(limit=20) if row['action'] == 'upload_dataset'}
    assert logged['260917_O2_Inventory.csv']['snapshot_date'] == '2026-08-01' and logged['250101_O2_Old_Inventory.csv']['snapshot_date'] == '2025-01-01'
    refused = client.post('/datasets-analysis/upload', data={'dataset_kinds': 'network_inventory', 'dataset_operators': '', 'snapshot_dates': '17/09/2026'},
                          files={'dataset_files': ('O2_Inventory.csv', io.BytesIO(inventory.encode()), 'text/csv')}, follow_redirects=False)
    assert refused.status_code == 422


def test_network_inventory_upload_with_its_operator_and_map_cdrs(client, tmp_path):
    login(client)
    inventory = 'Site,ECI,Vendor\nS1,1001,Ericsson\nS2,1002,Nokia\n'
    response = client.post(
        '/datasets-analysis/upload',
        data={'dataset_kinds': 'network_inventory', 'dataset_operators': ''},
        files={'dataset_files': ('O2_Network_Inventory.csv', io.BytesIO(inventory.encode()), 'text/csv')},
        follow_redirects=False,
    )
    assert response.status_code == 303
    wait_for_background_dataset_work()
    uploaded = next(row for row in core.repository.list_datasets() if row['file_name'] == 'O2_Network_Inventory.csv')
    # The Operator comes from the file name; the Network Inventory card lets it be changed.
    assert uploaded['dataset_kind'] == 'network_inventory' and uploaded['status'] == 'ready' and uploaded['dataset_operator'] == 'O2'
    assert client.post(f"/workspace/datasets/{uploaded['id']}/dataset-operator", json={'dataset_operator': 'O2'}).status_code == 200
    workspace = client.get('/workspace').text
    card = workspace.split('data-dataset-card="network-inventory"', 1)[1].split('</section>', 1)[0]
    assert 'O2_Network_Inventory.csv' in card and 'data-dataset-dataset-operator-select' in card
    assert f'name="network_inventory_dataset_ids" value="{uploaded["id"]}" checked' in workspace

    source = tmp_path / 'UK_Voice.csv'
    source.write_text('x\n1\n', encoding='utf-8')
    cdr_id, _created = core.repository.add_dataset(source.name, str(source), 'super')
    rows = pd.DataFrame({'Operator': ['O2', 'O2', 'EE'], 'Cell_ID_A': ['1001', '1001 -> 1002', '1001'], 'Session_ID_A': [1, 2, 3]})
    core.repository.replace_dataset_rows(cdr_id, rows)
    core.repository.update_dataset_profile(
        cdr_id, status='ready', progress=100, dataset_kind='voice', nr_mode='NSA', cdr_stage='final',
        row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso(),
        normalization_version=core.DATASET_NORMALIZATION_VERSION, vendor_mapping_applied=1,
    )
    mapped = client.post('/workspace/map-mappings', data={
        'cdr_dataset_ids': str(cdr_id), 'vendor_source': 'inventory', 'network_inventory_dataset_ids': str(uploaded['id']),
    }, follow_redirects=False)
    assert mapped.status_code == 303
    wait_for_background_dataset_work()
    result = core.repository.load_dataset_rows(cdr_id, ['Operator_Vendor'], {})
    assert result['Operator_Vendor'].tolist() == ['O2_Ericsson', 'O2_Ericsson (Mixed)', 'EE - All']
    options = json.loads(core.repository.get_dataset(cdr_id)['processing_options_json'])
    assert options['network_inventory_dataset_ids'] == [uploaded['id']]


MAPPING_CSV = (
    'Network,Host Network,OP/ Vendor,Site ID,eNodeB ID,Cell ID,Longitude,Latitude\n'
    'Vodafone,Vodafone,Ericsson,S1,10,1,-1.5,53.8\n'
    'H3G,H3G,Samsung,S2,20,2,-1.5,53.8\n'
)
INVENTORY_CSV = (
    'Network,Host Network,OP/ Vendor,Site ID,eNodeB ID,Cell ID,Longitude,Latitude\n'
    'Vodafone,Vodafone,Huawei,S1,10,1,-1.5,53.8\n'
    'Vodafone,Vodafone,NSN,S3,30,3,-1.5,53.8\n'
)


def _upload(client, name, content, kind, **fields):
    response = client.post('/datasets-analysis/upload', data={'dataset_kinds': kind, **fields},
                           files={'dataset_files': (name, content.encode(), 'text/csv')}, follow_redirects=False)
    assert response.status_code in {200, 303}
    wait_for_background_dataset_work()
    return core.serialize_dataset_row(next(row for row in core.repository.list_datasets() if row['file_name'] == name))


def _cdr(tmp_path, rows):
    source = tmp_path / 'UK_Voice.csv'
    source.write_text('x\n1\n', encoding='utf-8')
    cdr_id, _created = core.repository.add_dataset(source.name, str(source), 'super')
    frame = pd.DataFrame(rows)
    core.repository.replace_dataset_rows(cdr_id, frame)
    core.repository.update_dataset_profile(
        cdr_id, status='ready', progress=100, dataset_kind='voice', nr_mode='NSA', cdr_stage='final', row_count=len(frame),
        column_count=len(frame.columns), processed_at=local_now_iso(),
        normalization_version=core.DATASET_NORMALIZATION_VERSION, vendor_mapping_applied=1,
    )
    return cdr_id


def test_week_in_a_file_name_gives_its_snapshot_date():
    assert infer_snapshot_date('VF3_All_Vendor_2026_Week41_v3.xlsx') == '2026-10-05'
    assert infer_snapshot_date('x_2026_W05.csv') == '2026-01-26'
    assert infer_snapshot_date('260917_Week41.xlsx') == '2026-09-17'
    assert infer_snapshot_date('Multivendor_Mapping_VFUK.xlsx') is None
    assert infer_snapshot_date('Hw12_W60.csv') is None
    today = date.today()
    this_week = today.isocalendar().week
    assert infer_snapshot_date(f'Mapping_Week{this_week}.csv') == date.fromisocalendar(today.isocalendar().year, this_week, 1).isoformat()


def test_multivendor_mapping_gives_the_vendor_and_leaves_the_network_to_the_inventories(client, tmp_path):
    login(client)
    inventory = _upload(client, '260917_Cell_Config.csv', INVENTORY_CSV, 'network_inventory')
    mapping = _upload(client, 'VF3_All_Vendor_2026_Week41.csv', MAPPING_CSV, 'multivendor_mapping')
    assert mapping['status'] == 'ready' and mapping['input_kind_label'] == 'Multivendor Mapping'
    assert mapping['snapshot_date_effective'] == '2026-10-05'

    # Its Operators are read from its cells: those the networks of its cells serve.
    assert {'Three', 'VF'} <= set(mapping['mapping_operator_names'])
    assert 'EE' not in mapping['mapping_operator_names']

    # Whatever reads the network does not see it, although it is the newest file.
    snapshots = list_inventory_snapshots(core.repository)
    assert [item['dataset_id'] for item in snapshots] == [inventory['id']]
    assert snapshot_choice(snapshots) == {'vodafone': inventory['id']}
    with core.repository.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM inventory_cells WHERE dataset_id = ?', (mapping['id'],)).fetchone()[0] == 0
        assert connection.execute('SELECT COUNT(*) FROM multivendor_mapping_cells WHERE dataset_id = ?', (mapping['id'],)).fetchone()[0] == 2

    # The Map dialog offers it and the Network Inventory that completes it, both checked.
    workspace = client.get('/workspace').text
    assert f'name="multivendor_mapping_dataset_ids" value="{mapping["id"]}" checked' in workspace
    assert f'name="network_inventory_dataset_ids" value="{inventory["id"]}" checked' in workspace
    card = workspace.split('data-dataset-card="multivendor-mappings"', 1)[1].split('</section>', 1)[0]
    assert 'VF3_All_Vendor_2026_Week41.csv' in card and 'data-dataset-mapping-operators' in card

    # Mapped with both, the mapping wins where it has the cell and the inventory completes the others.
    rows = {'Operator': ['Vodafone UK', 'Vodafone UK', '3'], 'Cell_ID_A': [str(10 * 256 + 1), str(30 * 256 + 3), str(20 * 256 + 2)], 'Session_ID_A': [1, 2, 3]}
    cdr_id = _cdr(tmp_path, rows)
    assert client.post('/workspace/map-mappings', data={
        'cdr_dataset_ids': str(cdr_id), 'vendor_source': 'inventory', 'multivendor_mapping_dataset_ids': str(mapping['id']),
        'network_inventory_dataset_ids': str(inventory['id']),
    }, follow_redirects=False).status_code == 303
    wait_for_background_dataset_work()
    assert core.repository.load_dataset_rows(cdr_id, ['Vendor'], {})['Vendor'].tolist() == ['Ericsson', 'NSN', 'Samsung']
    options = json.loads(core.repository.get_dataset(cdr_id)['processing_options_json'])
    assert options['network_inventory_dataset_ids'] == [mapping['id'], inventory['id']]

    # Only the Multivendor Mapping: the cell it does not have stays Unknown.
    assert client.post('/workspace/map-mappings', data={
        'cdr_dataset_ids': str(cdr_id), 'vendor_source': 'inventory', 'multivendor_mapping_dataset_ids': str(mapping['id']),
    }, follow_redirects=False).status_code == 303
    wait_for_background_dataset_work()
    assert core.repository.load_dataset_rows(cdr_id, ['Vendor'], {})['Vendor'].tolist() == ['Ericsson', 'Unknown', 'Samsung']


def test_multivendor_mapping_applies_only_to_its_operators(client, tmp_path):
    login(client)
    mapping = _upload(client, 'VF3_All_Vendor_2026_Week41.csv', MAPPING_CSV, 'multivendor_mapping')
    url = f"/workspace/datasets/{mapping['id']}/mapping-operators"
    assert client.post(url, json={'operators': ['Nobody']}).status_code == 422
    assert client.post(url, json={'operators': ['Three']}).json()['operators'] == ['Three']
    row = core.repository.get_dataset(mapping['id'])
    assert json.loads(row['mapping_operators']) == ['Three']
    with core.repository.connection() as connection:
        event = connection.execute(
            "SELECT details FROM audit_logs WHERE action = 'update_dataset_mapping_operators' ORDER BY rowid DESC LIMIT 1").fetchone()
    assert json.loads(event['details'])['operators'] == ['Three']

    cdr_id = _cdr(tmp_path, {'Operator': ['Vodafone UK', '3'], 'Cell_ID_A': [str(10 * 256 + 1), str(20 * 256 + 2)], 'Session_ID_A': [1, 2]})
    assert client.post('/workspace/map-mappings', data={
        'cdr_dataset_ids': str(cdr_id), 'vendor_source': 'inventory', 'multivendor_mapping_dataset_ids': str(mapping['id']),
    }, follow_redirects=False).status_code == 303
    wait_for_background_dataset_work()
    mapped = core.repository.load_dataset_rows(cdr_id, ['Operator_Vendor', 'Vendor'], {})
    assert mapped['Vendor'].tolist()[1] == 'Samsung'
    # Vodafone has no source now: it is left without a Vendor of a cell, as an Operator no snapshot serves.
    assert mapped['Operator_Vendor'].tolist()[0].endswith(' - All')


def test_multivendor_mapping_applies_to_its_operators_without_operator_maps(client, tmp_path):
    login(client)
    with core.repository.connection() as connection:
        connection.execute("DELETE FROM chart_mapping_groups WHERE mapping_type = 'operator'")
    assert not core.repository.list_operator_mapping_groups()
    mapping = _upload(client, 'VF3_All_Vendor_2026_Week41.csv', MAPPING_CSV, 'multivendor_mapping')
    assert {'3', 'Vodafone'} <= set(mapping['mapping_operator_names']) and 'EE' not in mapping['mapping_operator_names']
    cdr_id = _cdr(tmp_path, {'Operator': ['Vodafone UK', '3', 'EE'], 'Cell_ID_A': [str(10 * 256 + 1), str(20 * 256 + 2), str(10 * 256 + 1)], 'Session_ID_A': [1, 2, 3]})
    assert client.post('/workspace/map-mappings', data={
        'cdr_dataset_ids': str(cdr_id), 'vendor_source': 'inventory', 'multivendor_mapping_dataset_ids': str(mapping['id']),
    }, follow_redirects=False).status_code == 303
    wait_for_background_dataset_work()
    assert core.repository.load_dataset_rows(cdr_id, ['Vendor'], {})['Vendor'].tolist()[:2] == ['Ericsson', 'Samsung']


def test_multivendor_mapping_without_a_network_column_belongs_to_its_operator(client, tmp_path):
    login(client)
    content = 'OP/ Vendor,Site ID,eNodeB ID,Cell ID,Longitude,Latitude\nHuawei,S1,40,4,-1.5,53.8\n'
    mapping = _upload(client, 'Mapping_2026_W05.csv', content, 'multivendor_mapping', mapping_operators=json.dumps(['Three']))
    assert mapping['mapping_operator_names'] == ['Three'] and mapping['snapshot_date_effective'] == '2026-01-26'
    with core.repository.connection() as connection:
        assert connection.execute('SELECT network_family FROM multivendor_mapping_cells WHERE dataset_id = ?', (mapping['id'],)).fetchone()[0] == 'three'
    response = client.post(f"/workspace/datasets/{mapping['id']}/mapping-operators", json={'operators': ['Three', 'VF']})
    assert response.status_code == 422 and 'no Network column' in response.json()['detail']


def test_vendor_mapping_outdated_follows_the_sources_of_the_cdr(client, tmp_path):
    login(client)
    inventory = _upload(client, '260917_Cell_Config.csv', INVENTORY_CSV, 'network_inventory')
    before = vendor_mapping_signature(core.repository)
    mapping = _upload(client, 'VF3_All_Vendor_2026_Week41.csv', MAPPING_CSV, 'multivendor_mapping')
    with_mapping = vendor_mapping_signature(core.repository)
    assert with_mapping != before

    # With a Multivendor Mapping, another Network Inventory only matters to the CDRs mapped with Network Inventories.
    completed = vendor_mapping_signature(core.repository, inventory_ids=[inventory['id']])
    assert completed != with_mapping
    _upload(client, '260918_Cell_Config.csv', INVENTORY_CSV, 'network_inventory')
    assert vendor_mapping_signature(core.repository) == with_mapping
    assert vendor_mapping_signature(core.repository, inventory_ids=[inventory['id']]) == completed

    assert client.post(f"/workspace/datasets/{mapping['id']}/mapping-operators", json={'operators': ['Three']}).status_code == 200
    assert vendor_mapping_signature(core.repository) != with_mapping
