"""Network Insights on inventory snapshots: deployment, host networks, deployed spectrum, density and serving cells."""

import pandas as pd

import src.DriveTestAnalyzer as core
from src.modules import inventory_insights as ii
from src.modules.repository import local_now_iso

LEEDS = (-1.55, 53.80)


def login(client):
    client.cookies.clear()
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303


def _dataset(tmp_path, name, kind, rows, **profile):
    source = tmp_path / name
    source.write_text('source', encoding='utf-8')
    dataset_id, _created = core.repository.add_dataset(name, str(source), 'super')
    frame = pd.DataFrame(rows)
    core.repository.replace_dataset_rows(dataset_id, frame)
    core.repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, row_count=len(frame),
                                           column_count=len(frame.columns), processed_at=local_now_iso(), **profile)
    return dataset_id


def _inventory_rows():
    rows = []
    for site in range(4):
        lon, lat = LEEDS[0] + site * 0.02, LEEDS[1]
        for sector, azimuth in enumerate((0, 120, 240), start=1):
            rows.append({'Technology': 'LTE', 'Network': 'Vodafone', 'Host Network': 'Vodafone' if site < 3 else 'Telefonica',
                         'Vendor': 'Ericsson' if site < 2 else 'Huawei', 'Site_ID': f'VF{site}', 'eNodeB ID': 1000 + site,
                         'Cell ID': sector, 'Band': 'LTE800', 'Earfcn': 6300, 'Bandwidth': 10, 'Azimuth': azimuth,
                         'Longitude': lon, 'Latitude': lat, 'Evenflow Status': 'In Service', 'Region': 'North'})
        if site < 2:
            rows.append({'Technology': 'NR', 'Network': 'Vodafone', 'Host Network': 'Vodafone', 'Vendor': 'Ericsson',
                         'Site_ID': f'VF{site}', 'gNodeB ID': 5000 + site, 'Cell ID': 1, 'Band': 'NR3400', 'ARFCN': 642000,
                         'Bandwidth': 100, 'Azimuth': 0, 'Longitude': lon, 'Latitude': lat, 'Evenflow Status': 'In Service'})
    rows.append({'Technology': 'LTE', 'Network': 'H3G', 'Host Network': 'H3G', 'Vendor': 'Samsung', 'Site_ID': 'T1',
                 'eNodeB ID': 2000, 'Cell ID': 1, 'Band': 'LTE1800', 'Earfcn': 1300, 'Bandwidth': 20, 'Azimuth': 90,
                 'Longitude': LEEDS[0], 'Latitude': LEEDS[1] + 0.01, 'Evenflow Status': 'Planned'})
    return rows


def _cdr_rows():
    cells = [1000 * 256 + 1, 1001 * 256 + 2, 1003 * 256 + 3, 1002 * 256 + 1]
    rows = []
    for index in range(12):
        cell = cells[index % 4]
        # The first eight samples are near their site; the last four 9 km away (overshooting).
        lat = LEEDS[1] + (0.0 if index < 8 else 0.08)
        rows.append({'Operator': 'Vodafone UK', 'Campaign': '2026-Q3', 'Region': 'North', 'City': 'Leeds',
                     'Test_Start_Latitude': lat, 'Test_Start_Longitude': LEEDS[0] + 0.01 * (index % 4),
                     'LTE_PCell_RSRP_Avg': -90.0, 'LTE_PCell_SINR_Avg': 10.0,
                     'NR_PCell_RSRP_Avg': -95.0 if index % 2 else None, 'NR_PCell_SINR_Avg': 5.0 if index % 2 else None,
                     'LAC_CID_xARFCN': f'[LTE E-UTRA 20, 100, {cell}, 6300]', 'Cell_ID': f'[{cell}]',
                     'LTE_PCC_EARFCN': 6300, 'LTE_DL_PCell_Bandwidth': 10, 'NR_DL_PCell_Band': ''})
    return rows


def test_snapshot_endpoint_groups_deployment_hosts_spectrum_quality_and_density(client, tmp_path):
    login(client)
    inventory = _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _inventory_rows())
    response = client.post('/api/network-insights/snapshot', json={'group': 'vendor'})
    assert response.status_code == 200
    payload = response.json()
    assert [item['dataset_id'] for item in payload['selection']] == [inventory, inventory]
    assert payload['selection'][0]['snapshot_date'] == '2026-09-17'
    vodafone = next(table for table in payload['deployment'] if table['family'] == 'vodafone')
    assert vodafone['totals'] == {'sites': 4, 'cells': 14, 'lte_cells': 12, 'nr_cells': 2}
    assert {row['group']: row['sites'] for row in vodafone['rows']} == {'Ericsson': 2, 'Huawei': 2}
    # The planned H3G cell is not in service.
    assert all(table['family'] != 'three' for table in payload['deployment'])
    hosted = client.post('/api/network-insights/snapshot', json={'group': 'host_network', 'in_service_only': False}).json()
    vodafone = next(table for table in hosted['deployment'] if table['family'] == 'vodafone')
    assert {row['group']: row['cells'] for row in vodafone['rows']} == {'VF': 11, 'O2': 3}
    assert hosted['host_matrix']['cells']['VF|O2'] == 3
    spectrum = {(row['operator'], row['band']): row for row in payload['spectrum']}
    assert spectrum[('VF', 'B20')]['carriers'] == 1 and spectrum[('VF', 'B20')]['deployed_mhz'] == 10
    assert spectrum[('VF', 'n78')]['deployed_mhz'] == 100
    quality = {row['operator']: row for row in payload['quality']}
    assert quality['3']['not_in_service'] == 1 and quality['VF']['without_position'] == 0
    density = {row['area']: row for row in payload['density']['region'] if row['operator'] == 'VF'}
    assert density['North']['sites'] == 4 and 1.2 < density['North']['median_isd_km'] < 1.4


def test_analysis_describes_the_serving_cells_distances_and_nr_availability(client, tmp_path):
    login(client)
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _inventory_rows())
    cdr = _dataset(tmp_path, 'Data CDR NSA.xlsx', 'data', _cdr_rows(), nr_mode='NSA')
    response = client.post('/api/network-insights/analysis', json={'datasets': {'data': [cdr]}, 'technology': 'lte', 'group': ['operator']})
    assert response.status_code == 200
    serving = response.json()['serving']
    row = serving['summary'][0]
    assert row['samples'] == 12 and row['matched'] == 12 and row['matched_share'] == 100.0
    assert row['overshoot_share'] == round(4 / 12 * 100, 1)
    assert {item['value'] for item in serving['by_vendor']} == {'Ericsson', 'Huawei'}
    # Operator Maps name the Vodafone network VF in this workspace.
    assert {item['value']: item['samples'] for item in serving['by_host']} == {'VF': 9, 'O2': 3}
    assert serving['overshooting_cells'] and serving['overshooting_cells'][0]['max_km'] > 8
    nr = serving['nr_availability']['rows'][0]
    # Samples anchored on VF0 and VF1, the sites with NR cells: half of them measured no NR.
    assert nr['on_nr_sites'] == 6 and nr['without_nr_on_nr_sites'] == 3
    assert serving['distance_cdf']['type'] == 'cdf'


def test_inventory_bands_and_snapshot_choice():
    assert ii.cell_band('LTE800', 'LTE') == 'B20' and ii.cell_band('NR3600', 'NR') == 'n78' and ii.cell_band('78', 'NR') == 'n78'
    assert round(ii.nr_arfcn_frequency(642000), 1) == 3630.0 and ii.nr_arfcn_frequency(152600) == 763.0
    snapshots = [
        {'dataset_id': 1, 'snapshot_date': '2026-08-20', 'families': {'vodafone': {'cells': 5}, 'three': {'cells': 2}}},
        {'dataset_id': 2, 'snapshot_date': '2026-09-17', 'families': {'vodafone': {'cells': 6}}},
    ]
    assert ii.snapshot_choice(snapshots) == {'vodafone': 2, 'three': 1}
    assert ii.snapshot_choice(snapshots, '1') == {'vodafone': 1, 'three': 1}


def test_sector_overlay_draws_the_sites_near_the_weak_areas_in_their_vendor_colours(client, tmp_path):
    login(client)
    inventory = _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _inventory_rows())
    from src.modules.network_inventory import ensure_inventory_cells
    snapshots = ensure_inventory_cells(core.repository)
    cells = ii.load_cells(core.repository, ii.snapshot_choice(snapshots))
    overlay = ii.sector_overlay(cells, {'vodafone'}, [(LEEDS[0], LEEDS[1])], radius_km=1.5)
    # VF0 and VF1 lie within 1.5 km of the weak area; VF2 (2.6 km) and the H3G site are left out.
    assert [site['label'] for site in overlay['sectors']] == ['Site VF0 · Vodafone', 'Site VF1 · Vodafone']
    assert [cell[:2] for cell in overlay['sectors'][0]['cells']][:3] == [[0.0, None], [120.0, None], [240.0, None]]
    assert overlay['sectors'][0]['cells'][0][2] == ii.vendor_colour('Ericsson')
    assert overlay['legend'] == [{'label': 'Ericsson sectors', 'colour': ii.vendor_colour('Ericsson')}]
    assert inventory


def test_snapshot_comparison_counts_added_removed_cells_and_vendor_swaps(client, tmp_path):
    login(client)
    rows = _inventory_rows()
    older = [{**row, 'Vendor': 'Huawei'} if row.get('Site_ID') == 'VF1' else row for row in rows if row.get('Site_ID') != 'VF3']
    before = _dataset(tmp_path, 'Multivendor_Mapping_VFUK.csv', 'network_inventory', older, snapshot_date='2026-08-20')
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', rows)
    payload = client.post('/api/network-insights/snapshot', json={'compare': str(before)}).json()
    comparison = {row['operator']: row for row in payload['comparison']['networks']}
    vodafone = comparison['VF']
    # VF3 (3 cells) is new; VF1's 4 cells (3 LTE, 1 NR) went from Huawei to Ericsson.
    assert vodafone['added'] == 3 and vodafone['removed'] == 0 and vodafone['vendor_changed'] == 4
    assert vodafone['swaps'] == [{'from': 'Huawei', 'to': 'Ericsson', 'cells': 4, 'sites': 1}]
    assert payload['comparison']['snapshot_date'] == '2026-08-20'
