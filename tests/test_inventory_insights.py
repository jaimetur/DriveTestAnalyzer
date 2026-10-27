"""Network Insights on inventory snapshots: deployment, host networks, deployed spectrum, density and serving cells."""

import pandas as pd

import src.DriveTestAnalyzer as core
from src.modules import inventory_insights as ii
from src.modules import serving_cells as sc
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
    assert quality['Three']['not_in_service'] == 1 and quality['VF']['without_position'] == 0
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
    # The percentiles of the distance CDF, shown in the table under it.
    assert row['p10_km'] <= row['median_km'] <= row['p90_km']
    assert {item['value'] for item in serving['by_vendor']} == {'Ericsson', 'Huawei'}
    # Operator Maps name the Vodafone network VF in this workspace.
    assert {item['value']: item['samples'] for item in serving['by_host']} == {'VF': 9, 'O2': 3}
    # Every sample is served by a Vodafone cell, also those on the site Telefonica hosts.
    assert {item['value']: item['samples'] for item in serving['by_network']} == {'VF': 12}
    assert serving['overshooting_cells'] and serving['overshooting_cells'][0]['max_km'] > 8
    nr = serving['nr_availability']['rows'][0]
    # Samples anchored on VF0 and VF1, the sites with NR cells: half of them measured no NR.
    assert nr['on_nr_sites'] == 6 and nr['without_nr_on_nr_sites'] == 3
    assert serving['distance_cdf']['type'] == 'cdf'


def test_serving_cells_follow_the_configured_serving_networks(client, tmp_path):
    login(client)
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _inventory_rows())
    rows = _cdr_rows()
    # Three of the Vodafone samples were served by the 3 cell T1 (eNodeB 2000, cell 1).
    for row in rows[::4]:
        row.update({'LAC_CID_xARFCN': f'[LTE E-UTRA 3, 100, {2000 * 256 + 1}, 1300]', 'Cell_ID': f'[{2000 * 256 + 1}]', 'LTE_PCC_EARFCN': 1300})
    cdr = _dataset(tmp_path, 'Data CDR NSA.xlsx', 'data', rows, nr_mode='NSA')
    request = {'datasets': {'data': [cdr]}, 'technology': 'lte', 'group': ['operator']}
    shared = client.post('/api/network-insights/analysis', json=request).json()['serving']
    # By default 3 serves Vodafone (eMOCN), so the samples on T1 find their cell.
    assert shared['summary'][0]['matched'] == 12 and {item['value'] for item in shared['by_vendor']} == {'Ericsson', 'Huawei', 'Samsung'}
    sc.save_serving_networks(core.repository, {'rows': [{'operator': 'Vodafone', 'networks': ['Vodafone']}]})
    own = client.post('/api/network-insights/analysis', json=request).json()['serving']
    assert own['summary'][0]['matched'] == 9 and {item['value'] for item in own['by_vendor']} == {'Ericsson', 'Huawei'}


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
    assert overlay['legend'] == [{'label': 'Ericsson sites', 'colour': ii.vendor_colour('Ericsson'), 'marker': 'triangle'}]
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


def _phase3_inventory_rows():
    """``_inventory_rows`` with NR PCIs, the MIMO of the cells and their states, an NR-only site and a planned site."""
    rows = []
    for row in _inventory_rows():
        row = dict(row)
        site = row.get('Site_ID')
        if row['Technology'] == 'NR':
            # VF0 broadcasts NR PCI 100 with 32 TX antennas; VF1 PCI 101 in 64T64R.
            row.update({'PCI': 100, 'noOfUsedTxAntennas': 32} if site == 'VF0' else {'PCI': 101, 'TXRXMODE': '64T64R'})
        elif site == 'VF0':
            row['TXRXMODE'] = '4T4R'
        elif site == 'VF1':
            row['noOfUsedTxAntennas'] = 2
        if site == 'VF2' and row.get('Cell ID') == 1:
            row.update({'administrativeState': 'LOCKED', 'operationalState': 'ENABLED'})
        rows.append(row)
    nr = {'Technology': 'NR', 'Network': 'Vodafone', 'Host Network': 'Vodafone', 'Vendor': 'Ericsson', 'Cell ID': 1, 'Band': 'NR3400',
          'ARFCN': 642000, 'Bandwidth': 100, 'Azimuth': 0, 'Latitude': LEEDS[1]}
    rows.append({**nr, 'Site_ID': 'VF4', 'gNodeB ID': 5004, 'PCI': 100, 'Longitude': LEEDS[0] + 0.1, 'Evenflow Status': 'In Service'})
    rows.append({**nr, 'Site_ID': 'VF5', 'gNodeB ID': 5005, 'Longitude': LEEDS[0] + 0.04, 'Latitude': LEEDS[1] + 0.005,
                 'Evenflow Status': 'Planned'})
    return rows


def _phase3_cdr_rows():
    """``_cdr_rows`` with the NR PCI, SSB NR-ARFCN, rank and MIMO layers CDR Data reports for NSA samples."""
    rows = _cdr_rows()
    for index, row in enumerate(rows):
        row.update({
            # Anchored on VF0 and VF2: PCI 100; on VF1 and VF3: PCI 101 (the first of the sequence).
            'NR_DL_PCell_PCI_Info_List': '[100]' if index % 4 in (0, 3) else '[101]->[100]',
            'NR_DL_PCell_ARFCN': '[641376]', 'NR_DL_PCell_Band': '[NR BAND 78]',
            'LTE_DL_Rank_Index': '([Rank1: 50.00],[Rank2: 50.00],[Rank3: 0.00],[Rank4: 0.00])',
            'NR_DL_Rank_Index': '([Rank1: 0.00],[Rank2: 100.00],[Rank3: 0.00],[Rank4: 0.00])' if index % 2 else None,
            'NR_DL_Max_MIMO_Layers': 4 if index % 2 else None,
        })
    return rows


def _phase3_analysis(client, tmp_path, **request):
    login(client)
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _phase3_inventory_rows())
    cdr = _dataset(tmp_path, 'Data CDR NSA.xlsx', 'data', _phase3_cdr_rows(), nr_mode='NSA')
    response = client.post('/api/network-insights/analysis', json={'datasets': {'data': [cdr]}, 'technology': 'lte', 'group': ['operator'], **request})
    assert response.status_code == 200
    return response.json()


def test_nsa_samples_find_their_nr_cell_on_the_anchor_site_or_nearby(client, tmp_path):
    serving = _phase3_analysis(client, tmp_path)['serving']
    leg = serving['nr_leg']['rows'][0]
    # VF0 and VF1 anchors have their NR cell on site; VF3 anchors find PCI 101 only on VF1; VF2 anchors find PCI 100
    # on VF0 (2 km) and VF4 (4.6 km) and take the nearest.
    assert leg['with_nr_pci'] == 12 and leg['found'] == 12 and leg['found_share'] == 100.0
    assert (leg['anchor_site_share'], leg['only_candidate_share'], leg['nearest_share']) == (50.0, 25.0, 25.0)
    assert leg['vendors'] == [{'vendor': 'Ericsson', 'share': 100.0}]
    assert serving['nr_leg']['by_vendor'][0]['value'] == 'Ericsson' and serving['nr_leg']['by_vendor'][0]['samples'] == 12
    nr = serving['nr_availability']['rows'][0]
    # The six samples that measured NR: those anchored on VF1 found it there, those anchored on VF2 on VF0.
    assert nr['with_nr'] == 6 and nr['nr_found_share'] == 100.0 and nr['nr_on_anchor_share'] == 50.0
    sites = {row['site']: row for row in serving['nr_availability']['nr_sites']}
    assert set(sites) == {'VF0', 'VF1'} and sites['VF0']['samples'] == 6 and sites['VF0']['from_anchor_share'] == 50.0
    assert sites['VF0']['vendor'] == 'Ericsson' and 1.5 < sites['VF0']['median_km'] < 2.5


def test_nr_carrier_must_contain_the_ssb_frequency_and_band():
    frame = pd.DataFrame({'_band': ['n78', 'n78', '', 'n1'], '_ssb_mhz': [3620.64, 3700.0, 3620.64, float('nan')],
                          'band_3gpp': ['n78', 'n78', 'n78', 'n78'], 'low_mhz': [3580.0, 3580.0, 3580.0, 3580.0],
                          'high_mhz': [3680.0, 3680.0, 3680.0, 3680.0]})
    assert ii._carrier_fits(frame).tolist() == [True, False, True, False]


def test_mimo_breakdown_crosses_inventory_antennas_with_reported_rank(client, tmp_path):
    rows = {(row['technology'], row['mimo']): row for row in _phase3_analysis(client, tmp_path)['serving']['mimo']}
    assert set(rows) == {('LTE', '2T'), ('LTE', '4T'), ('LTE', 'Not set'), ('NR', '32T'), ('NR', '64T')}
    four = rows[('LTE', '4T')]
    assert four['samples'] == 3 and four['modes'] == ['4T4R'] and four['mean_rank'] == 1.5 and four['rank_use'] == 37.5
    assert [item['share'] for item in four['rank_classes']] == [50.0, 50.0, 0.0, 0.0] and four['rank2_share'] == 50.0
    assert rows[('LTE', '2T')]['rank_use'] == 75.0 and rows[('LTE', '2T')]['modes'] == ['TX antennas']
    assert rows[('LTE', 'Not set')]['samples'] == 6 and rows[('LTE', 'Not set')]['rank_use'] is None
    # NR rank comes from the NR cell found for each NSA sample: VF1 (64T64R) and VF0 (32 TX antennas).
    massive = rows[('NR', '32T')]
    assert massive['samples'] == 3 and massive['mean_rank'] == 2.0 and massive['mean_layers'] == 4.0 and massive['rank_use'] == 50.0
    assert rows[('NR', '64T')]['modes'] == ['64T64R']


def test_cell_states_near_the_weak_areas_in_the_table_and_on_the_maps(client, tmp_path):
    analysis = _phase3_analysis(client, tmp_path, coverage_threshold=-80, min_samples=1)
    maps = analysis['sections'][0]['maps']
    status = maps['cell_status']
    rows = {row['site']: row for row in status['rows']}
    # VF2's locked cell, the planned VF5 site and the planned 3 site lie near the weak areas.
    assert set(rows) == {'VF2', 'VF5', 'T1'}
    assert rows['VF2']['states'] == [{'state': 'Locked', 'cells': 1}] and rows['VF2']['summary'] == 'Locked: 1 cell (B20)'
    assert rows['VF2']['on_air'] and not rows['VF5']['on_air'] and rows['VF5']['summary'] == 'Planned: 1 cell (n78)'
    assert rows['VF2']['area_kind'] == 'coverage' and rows['VF2']['distance_km'] < 1
    assert status['sites'] == {'Locked': 1, 'Planned': 2} and status['snapshot_dates'] == ['2026-09-17']
    # Only VF2's cell has an administrative or operational state: 1 of the 17 Vodafone and 3 cells.
    assert status['known_share'] == round(1 / 17 * 100, 1)
    sectors = {site['label']: site for site in maps['coverage']['sectors']}
    assert sectors['Site VF2 · Vodafone']['ring'] == 'outage' and 'Locked: 1 cell (B20)' in sectors['Site VF2 · Vodafone']['detail']
    assert sectors['Site VF5 · Vodafone']['ring'] == 'pipeline' and sectors['Site VF5 · Vodafone']['cells'] == []
    assert 'ring' not in sectors['Site VF0 · Vodafone']
    legend = [item['label'] for item in maps['coverage']['legend']['items']]
    assert 'Locked, halted, disabled' in legend and 'Planned or in progress' in legend
    marks = {item['label']: item.get('marker') for item in maps['coverage']['legend']['items']}
    assert marks['Locked, halted, disabled'] == 'ring' and marks['Planned or in progress'] == 'ring-dashed'


def test_cell_states_and_mimo_of_the_inventory_cells():
    cells = pd.DataFrame({
        'status': ['In Service', 'In Service', 'In Service', 'In Progress', 'Planned', 'Ex Service', 'In Service'],
        'admin_state': ['LOCKED', '', 'UNLOCKED', 'LOCKED', None, 'LOCKED', ''],
        'oss_status': ['ACTIVE', 'HALTED', 'ACTIVE', 'LOCKED', 'Unknown', 'LOCKED', 'Unknown'],
        'oper_state': ['ENABLED', '', 'DISABLED', '', None, '', ''],
        'txrx_mode': ['4T4R', '', '', '64T64R', '', '', '2t4r'], 'tx_antennas': [None, 2, 32, None, None, None, None],
    })
    # A planned or in-progress cell keeps that status even when it is locked; a cell out of service is not flagged.
    assert ii.cell_states(cells).tolist() == ['Locked', 'Halted', 'Disabled', 'In progress', 'Planned', '', '']
    assert ii.mimo_tx(cells['txrx_mode'], cells['tx_antennas']).tolist()[:4] == [4.0, 2.0, 32.0, 64.0]
    assert ii.mimo_tx(cells['txrx_mode'], cells['tx_antennas']).tolist()[6] == 2.0


def test_map_sites_loads_the_sites_inside_the_view_of_the_enlarged_map(client, tmp_path):
    login(client)
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _inventory_rows())
    # A view around VF0 (-1.55) and VF1 (-1.53): VF2 (-1.51), VF3 (-1.49) and the 3 site (planned) lie outside.
    view = [LEEDS[0] - .005, LEEDS[1] - .005, LEEDS[0] + .025, LEEDS[1] + .005]
    payload = client.post('/api/network-insights/map-sites', json={'families': ['vodafone', 'three'], 'bbox': view}).json()
    assert {site['label'] for site in payload['sectors']} == {'Site VF0 · Vodafone', 'Site VF1 · Vodafone'}
    # The sites take the colours of the Vendor Maps.
    configured = ii.configured_vendor_colours(core.repository.list_vendor_mapping_groups())
    assert payload['legend'] == [{'label': 'Ericsson sites', 'colour': ii.vendor_colour('Ericsson', configured), 'marker': 'triangle'}]
    # Wide views load no sites; networks without a snapshot give none; a view needs its four limits.
    wide = client.post('/api/network-insights/map-sites', json={'families': ['vodafone'], 'bbox': [-4, 52, -1, 55]}).json()
    assert wide == {'sectors': [], 'legend': [], 'too_wide': True}
    assert client.post('/api/network-insights/map-sites', json={'families': ['ee'], 'bbox': view}).json() == {'sectors': [], 'legend': []}
    assert client.post('/api/network-insights/map-sites', json={'families': ['vodafone'], 'bbox': [0, 1]}).status_code == 422


def test_analysis_maps_name_the_networks_and_snapshot_of_their_sites(client, tmp_path):
    login(client)
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _inventory_rows())
    cdr = _dataset(tmp_path, 'Data CDR NSA.xlsx', 'data', _cdr_rows(), nr_mode='NSA')
    analysis = client.post('/api/network-insights/analysis', json={'datasets': {'data': [cdr]}, 'technology': 'lte', 'group': ['operator'],
                                                                   'min_samples': 1}).json()
    maps = analysis['sections'][0]['maps']
    # Vodafone UK is served by the Vodafone and 3 networks (Serving Networks): the enlarged map loads their sites.
    assert maps['coverage']['sector_source'] == maps['interference']['sector_source'] == {'families': ['three', 'vodafone'], 'snapshot': ''}


def test_sites_take_the_vendor_colours_of_the_vendor_maps_by_name_or_alias():
    groups = [{'canonical': 'Huawei', 'aliases': ['HW'], 'color': '#fbbd00'}, {'canonical': 'Nokia', 'aliases': ['NSN'], 'color': 'not a colour'}]
    configured = ii.configured_vendor_colours(groups)
    assert configured == {'huawei': '#FBBD00', 'hw': '#FBBD00'}
    assert ii.vendor_colour('HW', configured) == '#FBBD00'
    # Vendors without a valid Vendor Maps colour keep the fallback palette.
    assert ii.vendor_colour('NSN', configured) == ii.VENDOR_COLOURS['nsn'] and ii.vendor_colour('Other', configured) == '#868E96'


def test_inventory_cells_and_snapshot_panels_are_kept_on_disk_with_the_network_colours(client, tmp_path):
    from pathlib import Path

    login(client)
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _inventory_rows())
    payload = client.post('/api/network-insights/snapshot', json={'group': 'vendor'}).json()
    folder = Path(core.repository.db_path).resolve().parent / '.network-insights-cache'
    # The derived cells of the snapshot and the snapshot panels are stored for the next runs, also after a restart.
    assert list(folder.glob('cells-*.pkl')) and list(folder.glob('snapshot-base-*.json')) and len(list(folder.glob('snapshot-*.json'))) >= 2
    from src.modules.network_inventory import ensure_inventory_cells
    selection = ii.snapshot_choice(ensure_inventory_cells(core.repository))
    first = ii.load_cells(core.repository, selection)
    ii._cell_cache.clear()
    pd.testing.assert_frame_equal(ii.load_cells(core.repository, selection), first)
    # Every network named by the panels has its Operator Maps colour (or one of the fallback palette).
    assert {'VF', 'Three'} <= set(payload['colours']) and all(colour.startswith('#') for colour in payload['colours'].values())


def test_snapshot_panels_list_the_networks_in_operator_maps_order(client, tmp_path):
    login(client)
    rows = _inventory_rows() + [{**row, 'Network': 'H3G', 'Host Network': 'H3G', 'Site_ID': 'T2', 'eNodeB ID': 2001, 'Evenflow Status': 'In Service'}
                                for row in _inventory_rows() if row.get('Site_ID') == 'T1']
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', rows)
    groups = core.repository.list_operator_mapping_groups()
    by_name = {group['canonical']: group for group in groups}
    # Three before VF, unlike the order of the Operator Maps of the United Kingdom.
    core.repository.replace_operator_mapping_groups([by_name['Three'], by_name['VF'], *(group for group in groups if group['canonical'] not in {'VF', 'Three'})])
    payload = client.post('/api/network-insights/snapshot', json={'group': 'host_network'}).json()
    assert payload['network_order'][:2] == ['Three', 'VF']
    assert [item['operator'] for item in payload['selection']][:2] == ['Three', 'VF']
    assert [table['operator'] for table in payload['deployment']][:2] == ['Three', 'VF']
    assert [row['operator'] for row in payload['quality']][:2] == ['Three', 'VF']
    assert payload['host_matrix']['owners'][:2] == ['Three', 'VF']


def _duplex_inventory_rows():
    def cell(network, host, vendor, site, technology, band, channel, lon, lat, status='In Service', region='North'):
        node = 'gNodeB ID' if technology == 'NR' else 'eNodeB ID'
        return {'Technology': technology, 'Network': network, 'Host Network': host, 'Vendor': vendor, 'Site_ID': site,
                node: abs(hash(site)) % 100000, 'Cell ID': 1 if band.endswith(('3400', '3600', '800')) else 2, 'Band': band,
                'ARFCN' if technology == 'NR' else 'Earfcn': channel, 'Bandwidth': 20, 'Azimuth': 0, 'Longitude': lon,
                'Latitude': lat, 'Evenflow Status': status, 'Region': region}

    lon, lat = LEEDS
    return [
        # VF0: NR TDD and FDD; VF1: NR FDD only; VF2: LTE only.
        cell('Vodafone', 'Vodafone', 'Ericsson', 'VF0', 'LTE', 'LTE800', 6300, lon, lat),
        cell('Vodafone', 'Vodafone', 'Ericsson', 'VF0', 'NR', 'NR3400', 642000, lon, lat),
        cell('Vodafone', 'Vodafone', 'Ericsson', 'VF0', 'NR', 'NR2100', 428000, lon, lat),
        cell('Vodafone', 'Telefonica', 'Huawei', 'VF1', 'NR', 'NR2100', 428000, lon + 0.02, lat, region='South'),
        cell('Vodafone', 'Vodafone', 'Ericsson', 'VF2', 'LTE', 'LTE800', 6300, lon + 0.04, lat),
        # T1 stands about 20 m from VF0: the same physical site. T2 is only planned.
        cell('H3G', 'H3G', 'Samsung', 'T1', 'NR', 'NR3600', 650000, lon, lat + 0.0002),
        cell('H3G', 'H3G', 'Samsung', 'T2', 'NR', 'NR700', 152000, lon + 0.06, lat, status='Planned'),
    ]


def test_nr_sites_by_duplex_mode_count_logical_and_physical_sites(client, tmp_path):
    login(client)
    _dataset(tmp_path, '260917_Cell_Config.zip', 'network_inventory', _duplex_inventory_rows())
    payload = client.post('/api/network-insights/nr-duplex-sites', json={}).json()
    rows = {row['operator']: row for row in payload['rows']}
    keys = ('sites', 'tdd_sites', 'fdd_sites', 'both_sites', 'tdd_only_sites', 'fdd_only_sites', 'physical_sites',
            'physical_tdd_sites', 'physical_fdd_sites')
    assert [rows['VF'][key] for key in keys] == [2, 1, 2, 1, 0, 1, 2, 1, 2]
    assert [rows['Three'][key] for key in keys] == [1, 1, 0, 0, 1, 0, 1, 1, 0]
    # The site shared by VF0 and T1 counts once among the physical sites of every network.
    assert [rows['All networks'][key] for key in keys] == [3, 2, 2, 1, 1, 1, 2, 1, 2]
    assert payload['rows'][-1]['all_networks'] and payload['radius_m'] == 50

    three = client.post('/api/network-insights/nr-duplex-sites', json={'operators': ['Three']}).json()
    assert [row['operator'] for row in three['rows']] == ['Three', 'All networks']
    assert three['filters'] == {'operators': 1}
    huawei = client.post('/api/network-insights/nr-duplex-sites', json={'vendors': ['Huawei']}).json()
    assert {row['operator']: row['fdd_only_sites'] for row in huawei['rows']} == {'VF': 1, 'All networks': 1}
    paired = client.post('/api/network-insights/nr-duplex-sites', json={'operator_vendors': ['VF_Huawei']}).json()
    assert {row['operator']: row['sites'] for row in paired['rows']} == {'VF': 1, 'All networks': 1}
    south = client.post('/api/network-insights/nr-duplex-sites', json={'regions': ['South']}).json()
    assert {row['operator']: row['sites'] for row in south['rows']} == {'VF': 1, 'All networks': 1}

    by_host = client.post('/api/network-insights/nr-duplex-sites', json={'split': 'host_network'}).json()
    assert by_host['split_label'] == 'Host Network'
    assert {(row['area'], row['operator']): row['sites'] for row in by_host['rows']} == {
        ('Three', 'Three'): 1, ('Three', 'All networks'): 1, ('O2', 'VF'): 1, ('O2', 'All networks'): 1,
        ('VF', 'VF'): 1, ('VF', 'All networks'): 1}
    events = [row for row in core.repository.list_logs(limit=20) if row['action'] == 'network_insights_nr_duplex_sites']
    assert events
