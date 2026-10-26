"""The map of a Non-Qualified Call: its cells at their inventory sites, the sites and NQ calls around it and the RSRP / SINR
of the tests around it (nq_call_map), and its route with its App Events."""
import json

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import network_inventory, nq_call_map, nq_prioritization
from src.modules import non_qualified_calls as nq
from tests.test_non_qualified_calls import add_cdr, enable_module, login

LONDON = (51.5074, -0.1278)


@pytest.fixture(autouse=True)
def background_runs_at_once(monkeypatch):
    """The background work runs at once, so each test reads what it has just indexed."""
    monkeypatch.setattr(core, 'submit_background_task', lambda callback, *args: callback(*args))


def eci(node: int, cell: int) -> int:
    return node * 256 + cell


def inventory_rows() -> list[dict]:
    """Three Vodafone sites around London, three LTE B3 cells each; a cell of site 70002 has the PCI and EARFCN of the cell
    of 70001 that served the call."""
    rows = []
    for index, (site, node, latitude, longitude) in enumerate(((70001, 30001, 51.5080, -0.1280), (70002, 30002, 51.5120, -0.1200),
                                                                (70003, 30003, 51.5300, -0.0900))):
        for cell, azimuth in ((1, 20), (2, 140), (3, 260)):
            rows.append({'Technology': 'LTE', 'Network': 'Vodafone', 'Host Network': 'Vodafone', 'Site ID': site,
                         'Cell Name': f'{site}-L{cell}', 'eNodeB ID': node, 'Cell ID': cell, 'Band': 'LTE1800', 'EARFCN': 1392,
                         'PCI': 101 if (index, cell) in {(0, 1), (1, 2)} else 200 + index * 3 + cell,
                         'Latitude': latitude, 'Longitude': longitude, 'Azimuth': azimuth, 'Horizontal Beamwidth': 65, 'Vendor': 'Ericsson'})
    return rows


def voice_rows() -> pd.DataFrame:
    """A dropped Vodafone call that started on 70001 and ended on 70002, a failure of EE beside it, a completed call and a
    failure far away."""
    trace = f'[LTE E-UTRA 3, 101, {eci(30001, 1)}, 1392]->[LTE E-UTRA 3, 101, {eci(30002, 3)}, 1392]'
    return pd.DataFrame({
        'Operator': ['Vodafone UK', 'EE', 'Vodafone UK', 'Vodafone UK'],
        'Campaign': ['UK_Q3_NSA_2026'] * 4,
        'City': ['London'] * 4,
        'JOIN_ID': ['V1', 'V2', 'V3', 'V4'],
        'Session_ID_A': [1, 2, 3, 4],
        'Call_Status': ['Dropped', 'Failed', 'Completed', 'Failed'],
        'status': ['Dropped', 'Failed', 'Completed', 'Failed'],
        'Call_Start_Time': ['2026-09-10 10:00:00', '2026-09-10 10:05:00', '2026-09-10 10:10:00', '2026-09-11 09:00:00'],
        'event_start_time': ['2026-09-10 10:00:00', '2026-09-10 10:05:00', '2026-09-10 10:10:00', '2026-09-11 09:00:00'],
        'Failure_Classification': ['RF Problems', 'RF Problems', '', 'VoLTE Problems'],
        'Call_Start_Latitude_A': [51.5078, 51.5090, 51.5075, 52.4862],
        'Call_Start_Longitude_A': [-0.1279, -0.1260, -0.1270, -1.8904],
        'Call_End_Latitude_A': [51.5110, None, None, None],
        'Call_End_Longitude_A': [-0.1215, None, None, None],
        'LAC_CID_xARFCN_A': [trace, '', '', ''],
        'Cell_ID_A': [f'[{eci(30001, 1)}]->[{eci(30002, 3)}]', '', '', ''],
        'PCI_A': ['[101]->[206]', '', '', ''],
        '4G_RSRP_Min_A': [-121.0, -100.0, -85.0, -99.0],
        '4G_RSRP_Avg_A': [-114.5, -96.0, -80.5, -95.0],
        '4G_RSRP_Max_A': [-104.0, -90.0, -75.0, -90.0],
        '4G_SINR_Avg_A': [-2.5, 4.0, 15.0, 6.0],
        'Handovers_Info_A': ['[4G-Handover (1)]', None, None, None],
        'Serving_Site_ID': ['70001', '', '70001', ''],
        'Serving_Host_Network': ['Vodafone', '', 'Vodafone', ''],
    })


def prepare(client, tmp_path) -> dict[str, dict]:
    enable_module()
    login(client)
    inventory = add_cdr(tmp_path, 'Multivendor_Mapping_VFUK.csv', 'mapping_vodafone', pd.DataFrame(inventory_rows()))
    core.repository.update_dataset_profile(inventory, snapshot_date='2026-09-17')
    network_inventory.ensure_inventory_cells(core.repository)
    add_cdr(tmp_path, 'UK Voice CDR.xlsx', 'voice', voice_rows())
    nq.sync_nq_calls(core.repository)
    nq_prioritization.calculate(core.repository)
    calls = client.post('/api/non-qualified-calls/calls', json={'filters': {}, 'page_size': 50}).json()['calls']
    return {call['join_id']: call for call in calls}


def test_the_map_places_the_call_its_cells_the_sites_and_the_calls_and_tests_around(client, tmp_path):
    calls = prepare(client, tmp_path)
    response = client.get(f"/api/non-qualified-calls/calls/{calls['V1']['call_key']}/map", params={'radius_km': 2})
    assert response.status_code == 200
    data = response.json()
    call = data['call']
    # Where it failed: where it ended.
    assert call['start'] == [51.5078, -0.1279] and call['end'] == [51.511, -0.1215] and data['centre'] == [51.511, -0.1215]
    assert call['serving_site'] == '70001' and data['radius_km'] == 2.0
    # Its type, as the NQ Prioritization names it (the NQ calls around carry theirs too).
    assert call['kind'] == 'voice' and all(item['kind'] for item in data['failures'])
    # Its radio values: the Min / Avg / Max of a measure together.
    rsrp = next(item for item in call['radio'] if item['name'] == '4G RSRP (A)')
    assert (rsrp['min'], rsrp['avg'], rsrp['max']) == ('-121.0', '-114.5', '-104.0')
    assert any(item.get('value') == '[4G-Handover (1)]' for item in call['radio'])
    # Its cells, in order, at their inventory sites.
    start, end = data['trace']
    assert (start['role'], start['site_id'], start['cell'], start['pci']) == ('start', '70001', str(eci(30001, 1)), '101')
    assert (end['role'], end['site_id'], end['inventory']['name']) == ('end', '70002', '70002-L3')
    # The sites around, nearest first: the serving one marked, the cells with the PCI and channel of a cell of the call flagged.
    sites = {site['site_id']: site for site in data['sites']}
    # 70003 is beyond the radius and served nothing of the call.
    assert set(sites) == {'70001', '70002'} and data['sites'][0]['site_id'] == '70002'
    assert sites['70001']['serving'] and not sites['70002']['serving']
    assert sites['70001']['roles'] == ['Served the start'] and sites['70002']['roles'] == ['Served the end']
    flagged = [(site['site_id'], cell['name']) for site in data['sites'] for cell in site['cells'] if cell.get('same_pci')]
    assert flagged == [('70002', '70002-L2')]
    assert {item['family'] for item in data['snapshots']} == {'vodafone'}
    # The NQ calls around: itself, the EE failure beside it; the Vodafone failure in Birmingham is far away.
    failures = {item['join_id']: item for item in data['failures']}
    assert failures['V1']['self'] and set(failures) == {'V1', 'V2'}
    assert not failures['V2']['same_operator'] and failures['V2']['distance_km'] < 2
    # Each with its CDR and campaign, so the page shows those of the CDR, the campaign or every campaign chosen.
    assert failures['V2']['dataset_id'] == call['dataset_id'] and failures['V2']['campaign'] == call['campaign']
    assert data['failure_scopes'] == nq_call_map.FAILURE_SCOPES and nq_call_map.DEFAULT_FAILURE_SCOPE == 'every'
    # The tests around, completed or not, with their RSRP and SINR.
    tests = data['tests']
    assert tests['total'] == 3 and tests['kinds'] == ['voice'] and len(tests['rows']) == 3
    columns = tests['columns']
    rows = [dict(zip(columns, row)) for row in tests['rows']]
    assert sorted((tests['operators'][row['operator']], row['failed'], row['lte_rsrp']) for row in rows) == [
        ('EE', 1, -96.0), ('VF', 0, -80.5), ('VF', 1, -114.5)]
    # And the CDR each comes from, with its campaign.
    assert tests['cdrs'] == [{'dataset_id': call['dataset_id'], 'kind': 'voice', 'campaign': call['campaign'],
                              'nr_mode': call['nr_mode'], 'stage': tests['cdrs'][0]['stage']}]
    assert {row['cdr'] for row in rows} == {0}
    # App Events records the map opened.
    [event] = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'nq_call_map']
    assert event['join_id'] == 'V1' and event['sites'] == 2 and event['tests_around'] == 3 and event['radius_km'] == 2.0
    # A call of its cluster or of its run of consecutive failures shows wherever it is, marked as such.
    nq_prioritization.ensure_tables(core.repository)
    with core.repository.connection() as connection:
        for key in ('V1', 'V4'):
            connection.execute(f"INSERT INTO {nq_prioritization.PRIORITY_TABLE} (call_key, repeat_key, consecutive_key) VALUES (?, 'group:g', 'run:r') "
                               "ON CONFLICT(call_key) DO UPDATE SET repeat_key = 'group:g', consecutive_key = 'run:r'", (calls[key]['call_key'],))
    data = client.get(f"/api/non-qualified-calls/calls/{calls['V1']['call_key']}/map", params={'radius_km': 2}).json()
    far = next(item for item in data['failures'] if item['join_id'] == 'V4')
    assert far['same_cluster'] and far['same_run'] and not far['same_hotspot'] and far['distance_km'] > 2


def test_the_radius_the_samples_and_the_unknown_calls(client, tmp_path):
    calls = prepare(client, tmp_path)
    key = calls['V4']['call_key']
    # A radius that is not offered falls back to the default one; the samples of every CDR of the campaign take its CDR too.
    data = client.get(f'/api/non-qualified-calls/calls/{key}/map', params={'radius_km': 3, 'tests': 'campaign'}).json()
    assert data['radius_km'] == nq_call_map.DEFAULT_RADIUS_KM and data['tests_scope'] == 'campaign'
    # Far from every inventory site: no site, and a cell trace it does not have.
    assert data['sites'] == [] and data['trace'] == [] and data['tests']['total'] == 1
    # The Focus operators of the Operator Maps, for the Operators choice of the page: none until a label has the role.
    assert data['focus_labels'] == [] and data['focus_operators'] == []
    core.repository.replace_operator_mapping_group(None, 'VF', ['Vodafone UK'], '#E60000', 'focus')
    data = client.get(f'/api/non-qualified-calls/calls/{key}/map').json()
    assert data['focus_labels'] == ['VF'] and data['focus_operators'] == ['VF', 'Vodafone UK']
    assert client.get('/api/non-qualified-calls/calls/unknown/map').status_code == 404


def test_a_call_without_position_nor_inventory_cells_cannot_be_mapped(client, tmp_path):
    enable_module()
    login(client)
    rows = voice_rows().iloc[[3]].assign(Call_Start_Latitude_A=None, Call_Start_Longitude_A=None)
    add_cdr(tmp_path, 'UK Voice CDR.xlsx', 'voice', rows)
    nq.sync_nq_calls(core.repository)
    [call] = client.post('/api/non-qualified-calls/calls', json={'filters': {}, 'page_size': 10}).json()['calls']
    response = client.get(f"/api/non-qualified-calls/calls/{call['call_key']}/map")
    assert response.status_code == 422 and 'nothing to place on the map' in response.json()['detail']
    [event] = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'nq_call_map_failed']
    assert event['call_key'] == call['call_key'] and 'nothing to place' in event['error']


def test_radio_values_and_cell_traces_read_the_cdr_row():
    columns = ['NR_RSRP_Min_A', 'NR_RSRP_Avg_A', 'NR_RSRP_Max_A', 'Playing_SINR_NR_Avg', 'Operator', 'Handovers_Info']
    row = {'NR_RSRP_Min_A': -110, 'NR_RSRP_Avg_A': -101.5, 'NR_RSRP_Max_A': None, 'Playing_SINR_NR_Avg': 3.2, 'Operator': 'EE',
           'Handovers_Info': '[NR-Handover (2)]'}
    assert nq_call_map.radio_values(row, columns) == [
        {'name': 'NR RSRP (A)', 'min': '-110', 'avg': '-101.5', 'max': '', 'median': ''},
        {'name': 'Playing SINR NR', 'min': '', 'avg': '3.2', 'max': '', 'median': ''},
        {'name': 'Handovers Info', 'value': '[NR-Handover (2)]'}]
    # Without a trace, the Cell ID chain gives the cells (an NR cell by its identity); the PCI follow their order.
    cells = nq_call_map.cell_trace('voice', {'PCI_A': '[5]->[9]'}, ['PCI_A'], '[1993842]->[834682982]')
    assert [(cell['technology'], cell['cell'], cell['pci']) for cell in cells] == [('LTE', '1993842', '5'), ('NR', '834682982', '9')]


def test_the_diagnosis_the_decisions_the_drive_and_the_serving_site_of_the_call(client, tmp_path):
    calls = prepare(client, tmp_path)
    data = client.get(f"/api/non-qualified-calls/calls/{calls['V1']['call_key']}/map", params={'radius_km': 2}).json()
    checks = {check['key']: check for check in data['diagnosis']}
    # -114.5 dBm is below the weak LTE level; -2.5 dB of SINR follows that weak coverage.
    assert checks['coverage']['level'] == 'bad' and '-114.5' in checks['coverage']['detail']
    assert checks['interference']['level'] == 'warn' and checks['interference']['title'] == 'Low SINR with weak coverage'
    assert checks['pci']['level'] == 'warn' and '70002-L2' in checks['pci']['detail']
    assert checks['distance']['level'] == 'ok' and 'Site 70002' in checks['distance']['detail']
    assert checks['handovers']['level'] == 'info' and '1 handover' in checks['handovers']['detail']
    assert checks['repetition']['level'] == 'ok' and checks['operators']['level'] == 'info'
    assert {check['level'] for check in data['diagnosis']} <= {'bad', 'warn', 'ok', 'info'}
    # No other call at its place has a root cause yet.
    assert data['decisions'] == {'related': 0, 'undecided': 0, 'groups': []}
    # Its drive: the call itself (where and when it started) and the completed call of its operator ten minutes later.
    rows = data['drive']['rows']
    assert [(row['offset_s'], row['self'], row['failed']) for row in rows] == [(0, True, True), (600, False, False)]
    assert rows[1]['lte_rsrp'] == -80.5 and data['drive']['minutes'] == 15
    # Its serving site served its two Vodafone calls (one Non-Qualified) and none of EE.
    [campaign] = data['site_health']['campaigns']
    assert data['site_health']['site_id'] == '70001'
    assert (campaign['calls'], campaign['nq'], campaign['rate'], campaign['all_calls']) == (2, 1, 50.0, 2)
    assert campaign['operator_rate'] == round(2 * 100 / 3, 2)
    [event] = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'nq_call_map']
    assert event['to_check'] == ['coverage'] and 'pci' in event['worth_a_look']


def test_the_decisions_at_its_place_group_the_root_causes_of_its_repetitions():
    failures = [
        {'self': True, 'same_place': False, 'same_hotspot': False, 'root_domain': '', 'root_category': '', 'root_cause': ''},
        *({'self': False, 'same_place': True, 'same_hotspot': False, 'root_domain': 'RAN', 'root_category': 'Coverage',
           'root_cause': 'Coverage hole', 'campaign': campaign, 'status': status, 'start_time': f'2026-0{month}-01', 'join_id': f'J{month}'}
          for campaign, status, month in (('Q1', 'Closed', 1), ('Q2', 'Closed', 2), ('Q2', 'Open', 3))),
        {'self': False, 'same_place': False, 'same_hotspot': True, 'root_domain': 'Core', 'root_category': 'IMS', 'root_cause': '',
         'campaign': 'Q2', 'status': 'Open', 'start_time': '2026-03-05', 'join_id': 'J9'},
        {'self': False, 'same_place': True, 'same_hotspot': False, 'root_domain': '', 'root_category': '', 'root_cause': '',
         'campaign': 'Q2', 'status': 'Open', 'start_time': '2026-03-06', 'join_id': 'J10'},
        {'self': False, 'same_place': False, 'same_hotspot': False, 'root_domain': 'RAN', 'root_category': 'Coverage',
         'root_cause': 'Coverage hole', 'campaign': 'Q2', 'status': 'Open', 'start_time': '2026-03-07', 'join_id': 'J11'},
    ]
    decisions = nq_call_map.site_decisions(failures)
    assert (decisions['related'], decisions['undecided']) == (5, 1)
    first, second = decisions['groups']
    assert (first['root_cause'], first['calls'], first['campaigns'], first['statuses']) == ('Coverage hole', 3, ['Q1', 'Q2'], {'Closed': 2, 'Open': 1})
    assert first['join_ids'] == ['J1', 'J2', 'J3'] and (second['root_category'], second['calls']) == ('IMS', 1)


def test_workspaces_of_the_previous_schema_get_the_index_of_the_serving_sites(client, tmp_path):
    enable_module()
    login(client)
    with core.repository.connection() as connection:
        connection.execute(f'DROP INDEX IF EXISTS idx_{nq.NQ_CALL_POPULATION_TABLE}_site')
    core.repository.set_workspace_state(nq.SCHEMA_STATE_KEY, '2026-10-23.2')
    nq.ensure_nq_tables(core.repository)
    with core.repository.connection() as connection:
        indexes = {row[1] for row in connection.execute(f'PRAGMA index_list({nq.NQ_CALL_POPULATION_TABLE})')}
    assert f'idx_{nq.NQ_CALL_POPULATION_TABLE}_site' in indexes
    assert core.repository.get_workspace_state(nq.SCHEMA_STATE_KEY) == nq.SCHEMA_VERSION


def test_its_operator_is_compared_with_the_others_by_how_many_tests_each_did():
    def check(own: tuple[int, int], others: tuple[int, int]) -> dict:
        rows = [[0, 0, 0, 0, int(index < own[1]), -90.0, 5.0, None, None, 0, ''] for index in range(own[0])]
        rows += [[0, 0, 1, 0, int(index < others[1]), -88.0, 6.0, None, None, 0, ''] for index in range(others[0])]
        checks = nq_call_map.diagnosis({'operator': 'VF', 'campaign': 'Q3'}, {}, [], [], [], {'operators': ['VF', 'EE'], 'rows': rows}, 2.0, 2)
        return next(item for item in checks if item['key'] == 'operators')

    # 9% of 426 against 0% of 1447: clearly its network, though less than 10 points apart.
    assert check((426, 38), (1447, 0))['level'] == 'bad'
    # A little more, without enough tests to be sure.
    assert check((40, 3), (100, 2))['level'] == 'warn' and check((40, 3), (100, 2))['title'] == 'Fails a little more than the others'
    # Every operator fails there alike.
    assert check((40, 3), (100, 7))['title'] == 'Every operator fails here'
    assert check((40, 0), (100, 1))['level'] == 'ok' and check((4, 4), (100, 0))['level'] == 'info'


def test_the_diagnosis_judges_the_serving_distance_and_coverage_holes_by_the_inter_site_distance():
    call = {'operator': 'Vodafone UK'}
    end = {'site': 'vodafone|70002', 'site_id': '70002', 'network': 'Vodafone', 'role': 'end', 'distance_km': 3.0, 'cell': '1'}
    nearest = {'key': 'vodafone|70009', 'site_id': '70009', 'network': 'Vodafone', 'distance_km': .8, 'isd_km': 1.0}

    def checks(radio: dict, ran: dict) -> dict:
        return {check['key']: check for check in nq_call_map.diagnosis(call, radio, [end], [], [], {}, 2.0, 2, ran)}

    radio = {'lte_rsrp': -100.0, 'lte_sinr': 5.0}
    # 3 km from a site whose sites are 1 km apart: overshooting, though below the 5 km of a fixed distance.
    found = checks(radio, {'serving_isd': 1.0, 'nearest': nearest})['distance']
    assert found['level'] == 'bad' and '3.0 times the inter-site distance of its site (1.0 km)' in found['detail']
    assert 'Site 70009 (Vodafone) is 800 m away' in found['detail']
    # The same 3 km where its sites are 4 km apart (a road) is what is expected there.
    assert checks(radio, {'serving_isd': 4.0, 'nearest': {**nearest, 'distance_km': 2.9}})['distance']['level'] == 'ok'
    # A site without an ISD (alone in its network) is judged by the fixed distances: a site three times nearer was there.
    assert checks(radio, {'serving_isd': None, 'nearest': nearest})['distance']['level'] == 'warn'
    # Weak coverage with the nearest site beyond 1.5 times its inter-site distance: a coverage hole.
    found = checks({'lte_rsrp': -118.0}, {'serving_isd': 4.0, 'nearest': {**nearest, 'distance_km': 6.0, 'isd_km': 3.0}})['coverage']
    assert (found['level'], found['title']) == ('bad', 'Coverage hole') and '2.0 times its inter-site distance (3.0 km)' in found['detail']
    assert checks({'lte_rsrp': -118.0}, {'serving_isd': 4.0, 'nearest': nearest})['coverage']['title'] == 'Weak coverage'
