"""The map of a Non-Qualified Call: its cells at their inventory sites, the sites and NQ calls around it and the RSRP / SINR
of the tests around it (nq_call_map), and its route with its App Events."""
import json
import math

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import network_inventory, nq_call_map, nq_prioritization
from src.modules import non_qualified_calls as nq
from src.modules.value_maps import ValueMapper, field_kind
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


def prepare(client, tmp_path, rows: pd.DataFrame | None = None) -> dict[str, dict]:
    enable_module()
    login(client)
    inventory = add_cdr(tmp_path, 'Multivendor_Mapping_VFUK.csv', 'mapping_vodafone', pd.DataFrame(inventory_rows()))
    core.repository.update_dataset_profile(inventory, snapshot_date='2026-09-17')
    network_inventory.ensure_inventory_cells(core.repository)
    add_cdr(tmp_path, 'UK Voice CDR.xlsx', 'voice', voice_rows() if rows is None else rows)
    nq.sync_nq_calls(core.repository)
    nq_prioritization.calculate(core.repository)
    calls = client.post('/api/non-qualified-calls/calls', json={'filters': {}, 'page_size': 50}).json()['calls']
    return {call['join_id']: call for call in calls}


def test_the_map_places_the_call_its_cells_the_sites_and_the_calls_and_tests_around(client, tmp_path, monkeypatch):
    calls = prepare(client, tmp_path)
    response = client.get(f"/api/non-qualified-calls/calls/{calls['V1']['call_key']}/map", params={'radius_km': 2})
    assert response.status_code == 200
    data = response.json()
    call = data['call']
    # Where it failed: where it ended.
    assert call['start'] == [51.5078, -0.1279] and call['end'] == [51.511, -0.1215] and data['centre'] == [51.511, -0.1215]
    # Its serving site: that of the cell that served its end, where it failed (the CDR gives that of its start).
    assert (call['serving_site'], call['serving_role']) == ('70002', 'end') and data['radius_km'] == 2.0
    # Where it started and ended, and its cells in words: by their inventory name, start and end.
    assert {role: (end['site_id'], end['estimated']) for role, end in call['ends'].items()} == {'start': ('70001', False), 'end': ('70002', False)}
    assert [(cell['role'], cell['label']) for cell in call['cells']] == [('start', '70001-L1 (LTE B3)'), ('end', '70002-L3 (LTE B3)')]
    # Its handover, halfway along its way (the CDR gives no RAT timeline here): an estimate.
    assert call['handovers'] == [{'order': 2, 'latitude': 51.5094, 'longitude': -0.1247, 'by': 'order', 'fraction': .5}]
    # Its way: from where it started to where it ended.
    assert call['way']['by'] == 'ends' and call['way']['points'][0] == call['start'] and call['way']['points'][-1] == call['end']
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
    assert sites['70002']['serving'] and not sites['70001']['serving']
    assert sites['70001']['ends'] == [{'role': 'start', 'estimated': False}] and sites['70002']['ends'] == [{'role': 'end', 'estimated': False}]
    assert sites['70001']['roles'] == ['Served the start'] and sites['70002']['roles'] == ['Served the end']
    flagged = [(site['site_id'], cell['name']) for site in data['sites'] for cell in site['cells'] if cell.get('same_pci')]
    assert flagged == [('70002', '70002-L2')]
    assert {item['family'] for item in data['snapshots']} == {'vodafone'}
    # The NQ calls around: itself, the EE failure beside it; the Vodafone failure in Birmingham is far away.
    failures = {item['join_id']: item for item in data['failures']}
    assert failures['V1']['self'] and set(failures) == {'V1', 'V2'}
    assert not failures['V2']['same_operator'] and failures['V2']['distance_km'] < 2
    # Each with its cells in words, by their inventory name for those of its operator.
    assert [(cell['role'], cell['label']) for cell in failures['V1']['cells']] == [('start', '70001-L1'), ('end', '70002-L3')]
    assert failures['V2']['cells'] == []
    # And the sites where it started and ended: those of its first and last cells (else for the start, the one the CDR gives).
    assert {role: site['site_id'] for role, site in failures['V1']['ends'].items()} == {'start': '70001', 'end': '70002'}
    assert failures['V2']['ends'] == {}
    # Each with its CDR and campaign, so the page shows those of the CDR, the campaign or every campaign chosen.
    assert failures['V2']['dataset_id'] == call['dataset_id'] and failures['V2']['campaign'] == call['campaign']
    assert data['failure_scopes'] == nq_call_map.FAILURE_SCOPES and nq_call_map.DEFAULT_FAILURE_SCOPE == 'every'
    assert data['failures_left_out'] == 0 and data['failures_max'] == nq_call_map.MAX_FAILURES
    # Alone in its hotspot (of 1 call: the page counts no hotspot), in no cluster and no run.
    assert {key: data['groups'][key] for key in ('hotspot', 'cluster', 'run')} == {'hotspot': 1, 'cluster': 0, 'run': 0}
    # Every NQ call of its campaign comes, whatever the maximum; those of the other campaigns up to it, nearest first.
    monkeypatch.setattr(nq_call_map, 'MAX_FAILURES', 0)
    point = tuple(data['centre'])
    kept, left_out, _groups = nq_call_map.nearby_failures(core.repository, call, point, 2.0)
    assert {item['join_id'] for item in kept} == {'V1', 'V2'} and left_out == 0
    kept, left_out, _groups = nq_call_map.nearby_failures(core.repository, {**call, 'campaign': 'Another campaign'}, point, 2.0)
    assert {item['join_id'] for item in kept} == {'V1'} and left_out == 1
    monkeypatch.undo()
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
    # A call of its cluster or of its time-window issue shows wherever it is, marked as such.
    nq_prioritization.ensure_tables(core.repository)
    with core.repository.connection() as connection:
        for key in ('V1', 'V4'):
            connection.execute(f"INSERT INTO {nq_prioritization.PRIORITY_TABLE} (call_key, repeat_key, repeat_size, consecutive_key) VALUES (?, 'group:g', 2, 'run:r') "
                               "ON CONFLICT(call_key) DO UPDATE SET repeat_key = 'group:g', repeat_size = 2, consecutive_key = 'run:r'", (calls[key]['call_key'],))
    data = client.get(f"/api/non-qualified-calls/calls/{calls['V1']['call_key']}/map", params={'radius_km': 2}).json()
    far = next(item for item in data['failures'] if item['join_id'] == 'V4')
    assert far['same_cluster'] and far['same_run'] and not far['same_hotspot'] and far['distance_km'] > 2
    # With the keys of its groups, so that the page paints the group that filters the list of calls.
    assert (far['repeat_key'], far['consecutive_key'], far['same_cluster_all']) == ('group:g', 'run:r', False)
    # Opened without a radius, the call takes the one that holds every NQ call of its hotspot and cluster (in tenths of a km),
    # up to the largest radius offered (V4 is 160 km away).
    data = client.get(f"/api/non-qualified-calls/calls/{calls['V1']['call_key']}/map").json()
    grouped = [item['distance_km'] for item in data['failures'] if item['same_cluster'] or item['same_hotspot']]
    assert data['group_radius_km'] == data['radius_km'] == min(nq_call_map.RADII_KM[-1], math.ceil(max(grouped) * 10) / 10)
    assert (data['groups']['cluster'], data['groups']['run']) == (2, 0)
    assert data['radius_km'] in data['radii_km'] and data['radii_km'] == sorted(data['radii_km'])


def test_the_radius_the_samples_and_the_unknown_calls(client, tmp_path):
    calls = prepare(client, tmp_path)
    key = calls['V4']['call_key']
    # A radius beyond those offered falls back to the default one (1 km), one between them is kept in tenths of a km; the
    # samples of every CDR of the campaign take its CDR too.
    assert nq_call_map.DEFAULT_RADIUS_KM == 1.0 and nq_call_map.normalise_radius(2.34) == 2.4
    data = client.get(f'/api/non-qualified-calls/calls/{key}/map', params={'radius_km': 30, 'tests': 'campaign'}).json()
    assert data['radius_km'] == nq_call_map.DEFAULT_RADIUS_KM and data['tests_scope'] == 'campaign'
    # Far from every inventory site: no site, and a cell trace it does not have.
    assert data['sites'] == [] and data['trace'] == [] and data['tests']['total'] == 1
    # The Focus operators of the Operator Maps, for the Operators choice of the page: none until a label has the role.
    assert data['focus_labels'] == [] and data['focus_operators'] == []
    core.repository.replace_operator_mapping_group(None, 'VF', ['Vodafone UK'], '#E60000', 'focus')
    data = client.get(f'/api/non-qualified-calls/calls/{key}/map').json()
    assert data['focus_labels'] == ['VF'] and data['focus_operators'] == ['VF', 'Vodafone UK']
    # A call in no hotspot or cluster opens with 1 km.
    assert data['group_radius_km'] is None and data['radius_km'] == 1.0
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
    # The way of the car: from the call (where it started) to its next test.
    assert data['drive']['route'] == [[51.5078, -0.1279, 0], [51.5075, -0.127, 600]]
    # A Voice call gives where it ended: no travelled zone, its way from where it started to where it ended.
    assert data['call']['travelled_m'] is None and data['call']['way']['by'] == 'ends'
    # Its serving site (where it ended) started no call; the site where its two Vodafone calls (one Non-Qualified) started.
    assert data['site_health']['site_id'] == '70002' and data['site_health']['campaigns'] == []
    mapper = ValueMapper.from_settings(core.repository.chart_mapping_settings())
    health = nq_call_map.site_health(core.repository, data['call'], '70001', 'Vodafone', lambda value: mapper.map(field_kind('operator'), value))
    [campaign] = health['campaigns']
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


def holds(shape: dict, latitude: float, longitude: float) -> bool:
    """Whether a shape of the groups of a call (``group_rings``) holds a position, a little tolerant of the projection."""
    scale = 6371008.8 * math.pi / 180
    dx = (longitude - shape['centre'][1]) * scale * math.cos(math.radians(shape['centre'][0]))
    dy = (latitude - shape['centre'][0]) * scale
    along = dx * math.cos(shape['angle']) + dy * math.sin(shape['angle'])
    across = -dx * math.sin(shape['angle']) + dy * math.cos(shape['angle'])
    return (along / shape['metres']) ** 2 + (across / max(1, shape['minor_metres'])) ** 2 <= 1.01


def test_the_enclosing_circle_and_ellipse_hold_every_point():
    import random

    generator = random.Random(7)
    for _ in range(100):
        points = [(generator.uniform(-2000, 2000), generator.uniform(-2000, 2000)) for _ in range(generator.randint(1, 30))]
        x, y, radius = nq_call_map.enclosing_circle(points)
        assert all(math.hypot(px - x, py - y) <= radius + 1e-6 for px, py in points)
        # The smallest: never wider than the circle of the two farthest points by more than 2 / sqrt(3).
        farthest = max((math.hypot(a[0] - b[0], a[1] - b[1]) for a in points for b in points), default=0)
        assert radius <= farthest / math.sqrt(3) + 1e-6
    # A drive: an ellipse along it, long and narrow, that holds every failure.
    angle = math.radians(30)
    drive = [(step * 600 * math.cos(angle) + generator.uniform(-40, 40), step * 600 * math.sin(angle) + generator.uniform(-40, 40))
             for step in range(6)]
    x, y, major, minor, axis = nq_call_map.enclosing_ellipse(drive, 40)
    for px, py in drive:
        along = (px - x) * math.cos(axis) + (py - y) * math.sin(axis)
        across = -(px - x) * math.sin(axis) + (py - y) * math.cos(axis)
        assert (along / major) ** 2 + (across / minor) ** 2 <= 1 + 1e-9
    assert abs(math.sin(axis - angle)) < .1 and major > 1500 and minor < major / 3


def test_the_shapes_of_the_groups_of_a_call_hold_every_call_of_them(client, tmp_path):
    from tests.test_nq_prioritization import prepare, priority_rows

    prepare(client, tmp_path, nq_prioritization.CUSTOM)
    rows = priority_rows()
    hotspots: dict[str, list[dict]] = {}
    for row in rows.values():
        if (row['cluster_size'] or 0) >= 2:
            hotspots.setdefault(row['cluster_key'], []).append(row)
    checked = 0
    for members in hotspots.values():
        row = members[0]
        shapes = nq_call_map.group_rings(core.repository, {'call_key': row['call_key']})
        assert shapes and {shape['kind'] for shape in shapes} <= {'cluster', 'run', 'hotspot'}
        # Every call of its hotspot is inside a circle of a cluster or an ellipse of a time window of it.
        for member in members:
            if member['latitude'] is not None:
                assert any(holds(shape, member['latitude'], member['longitude']) for shape in shapes), member['call_key']
        # Its own groups, of 2 calls or more, are among them with their keys; each time window with its failures in their order.
        own = {(kind, row[column]) for kind, column, size in (('cluster', 'repeat_key', 'repeat_size'), ('run', 'consecutive_key', 'consecutive_size'))
               if (row[size] or 0) >= 2}
        assert own <= {(shape['kind'], shape['key']) for shape in shapes if shape['own']}
        for shape in shapes:
            if shape['kind'] == 'run':
                times = sorted((other['start_time'], other['call_key']) for other in rows.values() if other['consecutive_key'] == shape['key']
                               and (shape['own'] or other['cluster_key'] == row['cluster_key']) and other['latitude'] is not None)
                assert shape['path'] == [[rows[key]['latitude'], rows[key]['longitude']] for _time, key in times]
        checked += 1
    assert checked >= 3
    # A call in no group has none; the map of a call gives them with the join of its hotspots.
    alone = next(key for key, row in rows.items() if (row['cluster_size'] or 0) < 2 and (row['repeat_size'] or 0) < 2
                 and (row['consecutive_size'] or 0) < 2)
    assert nq_call_map.group_rings(core.repository, {'call_key': alone}) == []
    payload = client.get(f"/api/non-qualified-calls/calls/{next(iter(hotspots.values()))[0]['call_key']}/map").json()
    assert payload['rings'] and payload['hotspot_join'] == 'or'


def test_a_call_on_cells_the_inventory_does_not_hold_shows_the_nearest_sites_to_where_it_started_and_failed(client, tmp_path):
    rows = voice_rows()
    # V4 failed on a GSM cell beside the London sites: the Network Inventory holds only LTE and NR cells.
    rows.loc[3, ['Call_Start_Latitude_A', 'Call_Start_Longitude_A', 'LAC_CID_xARFCN_A', 'Cell_ID_A']] = [51.5079, -0.1277, '[GSM 900, 876, 37171, 2]', '[37171]']
    calls = prepare(client, tmp_path, rows)
    data = client.get(f"/api/non-qualified-calls/calls/{calls['V4']['call_key']}/map", params={'radius_km': 2}).json()
    call = data['call']
    # Its cell is named as the CDR gives it, never taken for an LTE cell with its number.
    assert call['cells'] == [{'role': 'both', 'technology': 'GSM', 'label': 'GSM 900 · LAC 876 · CI 37171'}]
    assert call['ends']['end']['technology'] == 'GSM'
    assert [step['technology'] for step in data['trace']] == ['GSM'] and not data['trace'][0]['site']
    assert any('GSM 900 · LAC 876 · CI 37171' in note and 'dashed rings' in note for note in data['notes'])
    # The nearest site to where it started and failed (both here), an estimate; no serving site.
    assert {role: (end['site_id'], end['estimated']) for role, end in call['ends'].items()} == {'start': ('70001', True), 'end': ('70001', True)}
    sites = {site['site_id']: site for site in data['sites']}
    assert sites['70001']['ends'] == [{'role': 'start', 'estimated': True}, {'role': 'end', 'estimated': True}]
    assert not any(site['serving'] for site in data['sites']) and call['serving_site'] == ''
    assert data['site_health'] is None


def test_the_cells_of_a_call_in_words():
    steps = nq_call_map.cell_steps('[LTE E-UTRA 20, 3001, 30001001, 6300]->[LTE E-UTRA Unknown, 3001, 30001002, 1617]->[NR 78, , 1234567890, 632640]')
    assert [cell['label'] for cell in nq_call_map.labelled_cells(steps, {'30001002': '70002-L3'})] == [
        'LTE B20 · 30001001', '70002-L3 (LTE B3)', 'NR n78 · 1234567890']
    assert [cell['role'] for cell in nq_call_map.labelled_cells(steps)] == ['start', 'handover', 'end']
    assert [cell['label'] for cell in nq_call_map.labelled_cells(nq_call_map.cell_steps('[37171, 37172]'))] == ['Cell 37171', 'Cell 37172']
    assert nq_call_map.cell_label(nq_call_map.cell_steps('[GSM 900, , , 113]')[0]) == 'GSM 900 · channel 113'
    # A trace of the call without cell identities gives no cells, never the numbers of its bands.
    assert nq_call_map.trace_cells('', '', '[GSM 900, , , 113]->[GSM 900, 994, , 21]') == []
    assert nq_call_map.trace_cells('', '', '[GSM 900, 876, 37171, 2]')[0]['technology'] == 'GSM'


def test_where_each_handover_took_place_is_estimated_by_the_time_on_each_band():
    trace = ('[5G NR n1, 146011, 9803874315, 431070]->[5G NR n1, 146011, 9670885386, 431070]->[5G NR n3, 146011, 9670885389, 372490]'
             '->[LTE E-UTRA 20, 21890, 7300621, 6225]')
    steps = [dict(step, order=index + 1) for index, step in enumerate(nq_call_map.trace_cells(trace, '', ''))]
    bands = {step['cell']: step['band'] for step in nq_call_map.cell_steps(trace) if step['cell'] and step['band']}
    start, end = (51.0, 0.0), (51.1, 0.0)
    # 20 s on n1 (two cells, 10 s each), 20 s on n3 and 10 s on LTE 800, then 10 s without service: 60 s in all.
    points = nq_call_map.handover_points(steps, '5G_NR_N1 (20.0)->5G_NR_N3 (20.0)->LTE_800 (10.0)->No service (10.0)', [start, end], bands)
    assert [(point['order'], point['latitude'], point['by']) for point in points] == [
        (2, round(51.0 + .1 * 10 / 60, 6), 'time'), (3, round(51.0 + .1 * 20 / 60, 6), 'time'), (4, round(51.0 + .1 * 40 / 60, 6), 'time')]
    assert [point['fraction'] for point in points] == [round(10 / 60, 4), round(20 / 60, 4), round(40 / 60, 4)]
    # A timeline that does not match the cells spreads them evenly; without where the call ended there is nothing to place.
    assert [point['by'] for point in nq_call_map.handover_points(steps, 'LTE_1800 (5.0)', [start, end], bands)] == ['order'] * 3
    assert nq_call_map.handover_points(steps, '', [start, end], bands)[0]['latitude'] == 51.025
    assert nq_call_map.handover_points(steps, '5G_NR_N1 (20.0)', [start, None], bands) == []
    assert nq_call_map.handover_points(steps, '5G_NR_N1 (20.0)', None, bands) == []
    # Along a way that turns (the way simulated of a Data test): halfway is past its corner.
    turned = nq_call_map.handover_points(steps[:2], '', [(51.0, 0.0), (51.01, 0.0), (51.01, 0.03)], bands)
    assert turned[0]['fraction'] == .5 and turned[0]['latitude'] == 51.01 and 0 < turned[0]['longitude'] < .03
    # The PCell timeline of a Data test names its TDD bands so (LTE_TDD_2300: band 40).
    assert nq_call_map._timeline_band('LTE_TDD_2300') == 'LTE 2300' == nq_call_map._cell_band('LTE', '40')


def test_the_way_of_the_car_leaves_out_the_tests_another_car_could_not_reach():
    rows = [
        {'offset_s': -120, 'latitude': 51.4600, 'longitude': -2.6000, 'self': False},
        {'offset_s': -60, 'latitude': 51.4650, 'longitude': -2.6030, 'self': False},
        {'offset_s': 0, 'latitude': 51.4702, 'longitude': -2.6052, 'self': True},
        # Another car of the operator, 20 km away a minute later: no car drives that far.
        {'offset_s': 60, 'latitude': 51.6500, 'longitude': -2.6050, 'self': False},
        {'offset_s': 90, 'latitude': 51.4740, 'longitude': -2.6080, 'self': False},
    ]
    route = nq_call_map.drive_route(rows, (51.4702, -2.6052))
    assert [point[2] for point in route] == [-120, -60, 0, 90]
    assert nq_call_map.drive_route([], (51.47, -2.6)) == [] and nq_call_map.drive_route(rows[:0], None) == []


def test_the_way_of_a_data_test_is_simulated_along_the_way_of_its_car():
    # Its car went on to a test 500 m north of where it started: its 275 m go that way.
    route = [[51.4650, -2.6052, -60], [51.4702, -2.6052, 0], [51.474697, -2.6052, 90]]
    way = nq_call_map.simulated_way(route, 275)
    assert way['by'] == 'after' and len(way['points']) == 2
    assert nq_call_map.distance_km(tuple(way['points'][0]), tuple(way['points'][1])) * 1000 == pytest.approx(275, abs=1)
    assert way['points'][1][0] > 51.4702
    # Past its next test, straight on: 800 m end 300 m beyond it.
    longer = nq_call_map.simulated_way(route, 800)
    assert len(longer['points']) == 3 and nq_call_map.distance_km(tuple(longer['points'][1]), tuple(longer['points'][2])) * 1000 == pytest.approx(300, abs=2)
    # No test after it: on from where it came (the test before it was to the south).
    back = nq_call_map.simulated_way(route[:2], 275)
    assert back['by'] == 'before' and back['points'][1][0] > 51.4702
    # Without the way of its car or the distance it travelled, nothing is simulated.
    assert nq_call_map.simulated_way([], 275) is None and nq_call_map.simulated_way(route, None) is None
    assert nq_call_map.simulated_way([[51.4702, -2.6052, 0]], 275) is None


def test_the_diagnosis_tells_overshooting_cells_and_ping_pong_handovers():
    point = (51.470239, -2.605175)

    def step(order, cell, site, latitude, longitude, distance, azimuth, role='handover'):
        return {'order': order, 'cell': cell, 'role': role, 'role_label': {'start': 'Served the start', 'end': 'Served the end'}.get(role, 'Handover'),
                'site': f'vodafone|{site}', 'site_id': site, 'network': 'Vodafone', 'latitude': latitude, 'longitude': longitude,
                'distance_km': distance, 'inventory': {'name': f'ZE{site}-{cell}', 'azimuth': azimuth, 'beamwidth': 65}}
    # A cell 5 km to the south-east pointing at the call (330°), and cells of two sites near it that take it back and forth.
    far = step(3, '1664802', '511', 51.4333, -2.5684, 5.02, 330.0)
    near_a, near_b = step(1, '917282', '1154', 51.4686, -2.5923, 1.0, 210.0, 'start'), step(2, '917272', '3522', 51.4566, -2.6118, 1.6, 60.0)
    trace = [near_a, near_b, dict(near_a, order=4, role='handover'), far, dict(near_b, order=6, role='end')]
    checks = {check['key']: check for check in nq_call_map.diagnosis(
        {'operator': 'VF', 'campaign': 'Q3'}, {}, trace, [], [], {}, 2.0, 2, {'isds': {'vodafone|511': 1.5}}, point,
        {'metres': 275.0, 'seconds': 30.2})}
    assert checks['overshooting']['level'] == 'warn' and 'ZE511-1664802' in checks['overshooting']['detail']
    assert '3.4 times' in checks['overshooting']['detail'] and 'ZE1154' not in checks['overshooting']['detail']
    assert checks['handovers']['level'] == 'bad' and checks['handovers']['title'] == 'Ping-pong handovers'
    assert checks['handovers']['detail'].startswith('4 handovers in 275 m and 30 s, 2 of them back to a cell it had left')
