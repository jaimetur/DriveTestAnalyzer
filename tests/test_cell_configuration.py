"""Cell Configuration KMZ packages as Network Inventories, and the normalised inventory snapshots."""

import io
import json
import zipfile

import pandas as pd

import src.DriveTestAnalyzer as core
from conftest import wait_for_background_dataset_work
from src.modules import network_inventory as ni
from src.modules.cell_configuration import is_cell_configuration_package, read_cell_configuration

LTE_CELLS = (
    # Huawei cell hosted by Vodafone for O2: its Cell ID (110), not its Local Cell ID (7), completes the ECI.
    {'Cell_name': 'TF1491110', 'Vendor': 'Huawei', 'Network': 'Telefonica', 'Host Network': 'Vodafone', 'Site_ID': '86579',
     'eNodeB ID': '1491', 'Cell ID': '110', 'Local Cell ID': '7', 'Band': 'LTE800', 'PCI': '501', 'Earfcn': '6300',
     'Azimuth': '10', 'Easting': '706943', 'Northing': '443513', 'Longitude': '2.662', 'Latitude': '53.797',
     'eMOCNScenario': 'S0', 'Evenflow Status': 'In Service', 'ECI': '381806'},
    {'Cell_name': 'ZF57744026', 'Vendor': 'Ericsson', 'Network': 'Vodafone', 'Host Network': 'Vodafone', 'Site_ID': '57744',
     'eNodeB ID': '26141', 'Cell ID': '26', 'Local Cell ID': '26', 'Band': 'LTE1800', 'PCI': '502', 'Earfcn': '1750',
     'Azimuth': '155', 'Longitude': '-0.1453441', 'Latitude': '51.5238105', 'eMOCNScenario': 'NNS',
     'Evenflow Status': 'In Service', 'ECI': '6692122'},
)
NR_CELLS = (
    {'Cell Name': 'TKJ4334525', 'OP/ Vendor': 'Samsung', 'Network': 'H3G', 'Host Network': 'H3G', 'Site ID': '43345',
     'gNodeB ID': '15660', 'Cell ID': '11.000', 'Local Cell ID': '11', 'Band': 'NR700', 'PCI': '359', 'ARFCN': '152600',
     'Longitude': '-0.321', 'Latitude': '51.513', 'gNodeB ID Length': '22.000', 'NCI': '256573451.000'},
)


def _placemark(values: dict[str, str]) -> str:
    description = '<br/>'.join(f'{key}: {value}' for key, value in values.items())
    return (f'<Placemark><name>{values.get("Cell_name") or values.get("Cell Name")}</name>'
            f'<description><![CDATA[<div style="font-size:14px;">{description}</div>]]></description>'
            '<Point><coordinates>0,0,0</coordinates></Point></Placemark>')


def _document(name: str, cells, site_points=()) -> str:
    placemarks = ''.join(_placemark(cell) for cell in cells)
    sites = ''.join(
        f'<Placemark><name>Site_ID={site}</name><description><![CDATA[<div>Site_ID: {site}<br/>Vendor: Ericsson<br/>Network: Vodafone</div>]]></description></Placemark>'
        for site in site_points)
    return ('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            f'<name>{name}</name><Folder><name>Network</name><Folder><name>Band</name>{placemarks}{sites}</Folder></Folder></Document></kml>')


def _kmz(document: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('doc.kml', document)
    return buffer.getvalue()


def cell_configuration_package() -> bytes:
    """A ZIP package like the operators' Cell Configuration export: folders of LTE and NR KMZ files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('Cell_Config/LTE_CONFIG_KMZ/Outcome1_LTE_Cell_Config_KMZ_London.kmz', _kmz(_document('LTE', LTE_CELLS)))
        archive.writestr('Cell_Config/LTE_CONFIG_KMZ/Outcome2_LTE_Site_Vendor_KMZ_London.kmz', _kmz(_document('Sites', (), ('57744',))))
        archive.writestr('Cell_Config/NR_CONFIG_KMZ/Outcome1_NR_Cell_Config_KMZ_London.kmz', _kmz(_document('NR', NR_CELLS)))
        archive.writestr('__MACOSX/Cell_Config/._Outcome1_NR_Cell_Config_KMZ_London.kmz', b'not a kmz')
    return buffer.getvalue()


def login(client):
    client.cookies.clear()
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303


def test_cell_configuration_package_has_one_row_per_cell(tmp_path):
    package = tmp_path / '260917_Cell_Config_LTE_NR_KMZ.zip'
    package.write_bytes(cell_configuration_package())
    kml = tmp_path / 'cells.kml'
    kml.write_text(_document('LTE cells', LTE_CELLS[:1]), encoding='utf-8')
    assert is_cell_configuration_package(package) and is_cell_configuration_package(kml)

    frame = read_cell_configuration(package)

    # The site-vendor points are not cells; the LTE and NR spellings of a key share one column.
    assert len(frame) == 3
    assert frame['Technology'].tolist() == ['LTE', 'LTE', 'NR']
    assert frame['Source_File'].tolist()[0] == 'Outcome1_LTE_Cell_Config_KMZ_London.kmz'
    assert frame['Cell_name'].tolist() == ['TF1491110', 'ZF57744026', 'TKJ4334525']
    assert frame['Site_ID'].tolist() == ['86579', '57744', '43345']
    assert len(read_cell_configuration(kml)) == 1


def test_inventory_normalisation_keeps_owner_and_host_networks_and_the_broadcast_identity(tmp_path):
    package = tmp_path / 'cells.zip'
    package.write_bytes(cell_configuration_package())
    cells = ni.normalise_inventory(read_cell_configuration(package), 'network_inventory')

    assert cells['cell_identity'].tolist() == [str(1491 * 256 + 110), str(26141 * 256 + 26), str(15660 * 16384 + 11)]
    assert cells['network'].tolist() == ['Telefonica', 'Vodafone', 'H3G']
    assert cells['network_family'].tolist() == ['o2', 'vodafone', 'three']
    assert cells['host_family'].tolist() == ['vodafone', 'vodafone', 'three']
    assert cells['vendor'].tolist() == ['Huawei', 'Ericsson', 'Samsung']
    assert cells['node_id'].tolist() == [1491, 26141, 15660]
    assert cells['channel'].tolist() == [6300, 1750, 152600]
    # Coordinates rounded to 3 decimals take the precise British National Grid position when it is given.
    assert round(cells['latitude'][0], 3) == 53.797 and cells['latitude'][0] != 53.797
    assert cells['latitude'][1] == 51.5238105


def test_vfuk_and_3uk_mappings_normalise_with_their_default_network():
    vfuk = pd.DataFrame({
        'source_sheet': ['4G', '5G', 'EUtranCellFDD'], 'Network': ['Vodafone', 'H3G', ''], 'OP/ Vendor': ['NSN', 'Ericsson', ''],
        'eNodeB ID': ['1491', None, None], 'gNodeB ID': [None, '16628', None], 'Cell ID': ['110', '515', '7'],
        'Local Cell ID': ['7', '10', None], 'CId___ECI': [str(1491 * 256 + 7), None, None], 'Site ID': ['1', '2', ''],
    })
    cells = ni.normalise_inventory(vfuk, 'mapping_vodafone')
    # The workbook's own CId___ECI (built with the Local Cell ID) is ignored; the ENM sheet has no cells.
    assert cells['cell_identity'].tolist() == [str(1491 * 256 + 110), str(16628 * 16384 + 515)]
    assert cells['technology'].tolist() == ['LTE', 'NR'] and cells['network_family'].tolist() == ['vodafone', 'three']
    three = pd.DataFrame({'CId___ECI': ['20539077', '20545083'], 'Vendor': ['Samsung', 'Ericsson'], 'MBNL_ID': ['A', 'B']})
    cells = ni.normalise_inventory(three, 'mapping_three')
    assert cells['network'].tolist() == ['3', '3'] and cells['technology'].tolist() == ['LTE', 'LTE']
    assert cells['site_id'].tolist() == ['A', 'B']


def test_snapshot_dates_come_from_the_name_the_upload_or_the_user():
    assert ni.infer_snapshot_date('260917_Cell_Config_LTE_NR_KMZ.zip') == '2026-09-17'
    assert ni.infer_snapshot_date('VFUK_Inventory_2026-08-20.xlsx') == '2026-08-20'
    assert ni.infer_snapshot_date('Multivendor_Mapping_VFUK.xlsx') is None
    assert ni.effective_snapshot_date({'file_name': 'Multivendor_Mapping_VFUK.xlsx', 'uploaded_at': '2026-10-09T14:05:53'}) == '2026-10-09'
    assert ni.effective_snapshot_date({'file_name': '260917_x.zip', 'snapshot_date': '2026-08-20'}) == '2026-08-20'
    assert ni.network_family('Vodafone SM') == 'vodafone' and ni.network_family('H3G') == 'three'
    assert ni.network_family('Telefonica') == 'o2' and ni.network_family('Lebara') == 'lebara'


def test_kmz_package_uploads_as_a_multi_operator_inventory_snapshot(client):
    login(client)
    response = client.post(
        '/datasets-analysis/upload',
        data={'dataset_kinds': 'network_inventory', 'dataset_operators': ''},
        files={'dataset_files': ('260917_Cell_Config_LTE_NR_KMZ.zip', io.BytesIO(cell_configuration_package()), 'application/zip')},
        follow_redirects=False,
    )
    assert response.status_code == 303
    wait_for_background_dataset_work()
    uploaded = next(row for row in core.repository.list_datasets() if row['file_name'] == '260917_Cell_Config_LTE_NR_KMZ.zip')
    assert uploaded['status'] == 'ready' and uploaded['row_count'] == 3 and not uploaded['dataset_operator']

    snapshots = ni.list_inventory_snapshots(core.repository)
    snapshot = next(item for item in snapshots if item['dataset_id'] == uploaded['id'])
    assert snapshot['snapshot_date'] == '2026-09-17' and snapshot['cells'] == 3
    assert set(snapshot['families']) == {'vodafone', 'o2', 'three'}

    workspace = client.get('/workspace').text
    card = workspace.split('data-dataset-card="network-inventory"', 1)[1].split('</section>', 1)[0]
    assert 'Multi-operator (Network column)' in card and 'value="2026-09-17" data-dataset-snapshot-date' in card

    # The user dates the snapshot; blank returns to the date of its name. Every change is an App Event.
    url = f"/workspace/datasets/{uploaded['id']}/snapshot-date"
    changed = client.post(url, json={'snapshot_date': '2026-08-20'})
    assert changed.status_code == 200 and changed.json()['snapshot_date_effective'] == '2026-08-20'
    assert client.post(url, json={'snapshot_date': '20/08/2026'}).status_code == 422
    assert client.post(url, json={'snapshot_date': ''}).json()['snapshot_date_effective'] == '2026-09-17'
    logs = [row for row in core.repository.list_logs(limit=50) if row['action'] == 'update_dataset_snapshot_date']
    assert len(logs) == 2 and json.loads(logs[0]['details'])['dataset_id'] == uploaded['id']

    # Deleting the inventory removes its snapshot.
    assert client.post(f"/datasets-analysis/delete/{uploaded['id']}", follow_redirects=False).status_code == 303
    assert all(item['dataset_id'] != uploaded['id'] for item in ni.list_inventory_snapshots(core.repository))
    with core.repository.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM inventory_cells WHERE dataset_id = ?', (uploaded['id'],)).fetchone()[0] == 0


def test_workbook_sheets_repeating_a_field_take_its_first_non_empty_column():
    # The VFUK workbook writes Site_ID and CELL_ID in its 2G sheet and Site ID and Cell ID in its 4G and 5G sheets.
    vfuk = pd.DataFrame({
        'source_sheet': ['2G', '4G', '5G'], 'Site_ID': ['A1', None, None], 'CELL_ID': ['7', None, None],
        'Site ID': [None, '57744', '43345'], 'Cell ID': [None, '110', '515'], 'Local Cell ID': [None, '7', '10'],
        'eNodeB ID': [None, '1491', None], 'gNodeB ID': [None, None, '16628'], 'OP/ Vendor': ['Nokia', 'Huawei', 'Ericsson'],
    })
    cells = ni.normalise_inventory(vfuk, 'mapping_vodafone')
    assert cells['site_id'].tolist() == ['57744', '43345']
    assert cells['cell_identity'].tolist() == [str(1491 * 256 + 110), str(16628 * 16384 + 515)]
