"""NQ Prioritization: the scoring impact, the repeated issues and the Prioritization Rules of the Non-Qualified Calls."""
import io
import json
from pathlib import Path

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import non_qualified_calls as nq
from src.modules import nq_catalog, nq_prioritization, scoring, scoring_exclusions, scoring_history
from src.modules.repository import local_now_iso
from tests.scoring_cdr_synthetic import synthetic_cdr_frames
from tests.scoring_fixtures import load_initial_scoring_configuration
from tests.test_non_qualified_calls import enable_module, login, workspace_user


@pytest.fixture(autouse=True)
def background_runs_at_once(monkeypatch):
    """The background work runs at once, so each test reads what it has just calculated."""
    monkeypatch.setattr(core, 'submit_background_task', lambda callback, *args: callback(*args))


# -- the parts without a workspace ---------------------------------------------------------------
def test_impact_levels_are_a_pareto_of_the_points_with_ties_together():
    points = {'a': 5.0, 'b': 3.0, 'c': 1.0, 'd': 1.0, 'e': 0.0}
    # 10 points: a holds the first 50% (High), b reaches 80% (Medium), c and d share their level (Low), e loses none.
    assert nq_prioritization.impact_levels(points, 50, 80) == {
        'a': 'High', 'b': 'Medium', 'c': 'Low', 'd': 'Low', 'e': 'No impact'}
    # Calls with the same points share their level, also across the High share.
    assert set(nq_prioritization.impact_levels({'a': 1.0, 'b': 1.0, 'c': 1.0}, 50, 80).values()) == {'High'}
    assert nq_prioritization.impact_levels({'a': 0.0}, 50, 80) == {'a': 'No impact'}


def test_bad_tests_follow_the_direction_of_the_kpi():
    success = {'calculation': {'formula': '100 * SUM(Call_Status == "Completed") / COUNT(Call_Status)'}, 'direction': 'higher_is_better'}
    polqa = {'calculation': {'formula': '100 * SUM(LQ <= 1.6) / COUNT(Session_Type)'}, 'direction': 'lower_is_better'}
    assert nq_prioritization.bad_tests(success, 95.0, 200) == 10
    assert nq_prioritization.bad_tests(polqa, 2.5, 200) == 5


def test_the_first_rule_whose_conditions_a_call_meets_decides():
    rules = nq_prioritization.compile_rules(nq_prioritization.normalize_settings({'rules': [
        {'name': 'London Voice', 'services': ['voice'], 'nr_modes': ['NSA'], 'cities': ['London'], 'criterion': 'all', 'priority': 'P1'},
        {'name': 'VF Data', 'services': ['data'], 'operators': ['VF*', '-VF SM'], 'criterion': 'repeated_or_high',
         'priority': 'P2', 'track_priority': 'P5'},
        {'name': 'Both', 'services': ['data'], 'criterion': 'repeated_and_high', 'priority': 'P3'},
    ]})['rules'])
    voice = {'service': 'voice', 'nr_mode': 'NSA', 'operator': 'EE', 'region': '', 'city': 'London'}
    assert nq_prioritization.decide(rules, voice, False, False) == ('Prioritized', 'London Voice', 'P1')
    assert nq_prioritization.decide(rules, {**voice, 'city': 'Leeds'}, False, False) == ('No rule', '', '')
    data = {'service': 'data', 'nr_mode': 'SA', 'operator': 'VF UK', 'region': '', 'city': 'Leeds'}
    assert nq_prioritization.decide(rules, data, True, False) == ('Prioritized', 'VF Data', 'P2')
    # Not repeated nor high impact: tracked with the tracked priority of its rule, not passed to the next rule.
    assert nq_prioritization.decide(rules, data, False, False) == ('Track only', 'VF Data', 'P5')
    # The patterns of the operators: VF SM is left out, so the next rule decides.
    assert nq_prioritization.decide(rules, {**data, 'operator': 'VF SM'}, True, False) == ('Track only', 'Both', '')
    assert nq_prioritization.decide(rules, {**data, 'operator': 'VF SM'}, True, True) == ('Prioritized', 'Both', 'P3')


def test_settings_are_validated():
    defaults = nq_prioritization.normalize_settings(None)
    assert [rule['name'] for rule in defaults['rules']] == ['SA Voice', 'SA Data', 'NSA Voice', 'NSA Data']
    assert (defaults['high_share'], defaults['medium_share'], defaults['min_calls'], defaults['previous_quarters']) == (50, 80, 2, 1)
    for settings, message in (({'high_share': 60, 'medium_share': 50}, 'above the High share'),
                              ({'rules': [{'name': 'A'}, {'name': 'a'}]}, 'repeated'),
                              ({'rules': [{'name': ''}]}, 'needs a name'),
                              ({'min_calls': 1}, 'goes from 2'),
                              ({'rules': [{'name': 'A', 'criterion': 'some'}]}, 'Choose the calls')):
        with pytest.raises(ValueError, match=message):
            nq_prioritization.normalize_settings(settings, strict=True)
    # Unknown services and NR Modes are left out, the others take their spelling.
    rule = nq_prioritization.normalize_settings({'rules': [{'name': 'A', 'services': ['VOICE', 'fax'], 'nr_modes': ['sa']}]})['rules'][0]
    assert (rule['services'], rule['nr_modes']) == (['voice'], ['SA'])


def test_repetitions_count_the_calls_of_the_operator_at_the_place_in_the_quarter_and_those_before():
    calls = [
        {'call_key': 'a', 'operator': 'EE', 'place_key': 'site:|s1', 'quarter': 8100, 'campaign_label': 'Q1'},
        {'call_key': 'b', 'operator': 'EE', 'place_key': 'site:|s1', 'quarter': 8101, 'campaign_label': 'Q2'},
        {'call_key': 'c', 'operator': 'EE', 'place_key': 'site:|s1', 'quarter': 8103, 'campaign_label': 'Q4'},
        {'call_key': 'd', 'operator': 'VF', 'place_key': 'site:|s1', 'quarter': 8101, 'campaign_label': 'Q2'},
        {'call_key': 'e', 'operator': 'EE', 'place_key': '', 'quarter': 8101, 'campaign_label': 'Q2'},
    ]
    found = nq_prioritization.repetitions(calls, 1)
    assert found['a'] == (1, 1) and found['b'] == (2, 2) and found['c'] == (1, 1) and found['d'] == (1, 1)
    assert 'e' not in found
    assert nq_prioritization.repetitions(calls, 3)['c'] == (3, 3)


def test_place_of_a_call_falls_back_from_the_site_of_its_last_cell_to_a_spot():
    def lookup(operator, node):
        return {'site': 'LON001', 'host': 'OSS1'} if node == ('eNB', 1000) else None
    assert nq_prioritization.place_of({'cell_id': str(1000 * 256 + 1), 'operator': 'VF', 'site_id': 'S9'}, lookup, 100) == (
        'site:oss1|lon001', 'Site LON001 (OSS1)')
    assert nq_prioritization.place_of({'cell_id': str(2000 * 256 + 1), 'operator': 'VF', 'site_id': 'S9', 'host_network': 'H3G'},
                                      lookup, 100) == ('site:h3g|s9', 'Site S9 (H3G)')
    assert nq_prioritization.place_of({'cell_id': str(2000 * 256 + 1), 'operator': 'VF'}, lookup, 100) == ('node:eNB 2000', 'eNB 2000')
    near = nq_prioritization.place_of({'latitude': 51.50001, 'longitude': -0.12001}, lookup, 100)
    assert near[0].startswith('spot:') and near == nq_prioritization.place_of({'latitude': 51.50002, 'longitude': -0.12002}, lookup, 100)
    assert nq_prioritization.place_of({}, lookup, 100) == ('', '')


# -- in a workspace -----------------------------------------------------------------------------------
def add_cdr(tmp_path: Path, name: str, kind: str, rows: pd.DataFrame, nr_mode: str) -> int:
    source = tmp_path / name
    source.write_text('test source', encoding='utf-8')
    dataset_id, _created = core.repository.add_dataset(name, str(source), 'super')
    core.repository.replace_dataset_rows(dataset_id, rows)
    core.repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode=nr_mode,
                                           row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso())
    return dataset_id


def nq_frames(prefix: str, campaigns=('2026-Q3',), seed=11) -> dict[str, pd.DataFrame]:
    """Synthetic CDR rows with their result and a JOIN_ID per call (the samples of a Speech call share it)."""
    frames = synthetic_cdr_frames(seed=seed, campaigns=campaigns, repeats=1)
    for kind, frame in frames.items():
        if kind == 'voice':
            frame['status'] = frame['Call_Status']
            frame['JOIN_ID'] = [f'{prefix}V{index}' for index in range(len(frame))]
        elif kind == 'data':
            frame['status'] = frame['Test_Result']
            frame['JOIN_ID'] = [f'{prefix}D{index}' for index in range(len(frame))]
        else:
            frame['status'] = ['Completed' if value > 1.6 else 'Failed' for value in frame['LQ']]
            frame['JOIN_ID'] = [f'{prefix}S{index // 2}' for index in range(len(frame))]
    return frames


@pytest.fixture
def prioritized(client, tmp_path):
    """A workspace with NSA and SA CDRs of a campaign, its Scoring History and the calls indexed and prioritized."""
    enable_module()
    core.repository.replace_scoring_configuration(load_initial_scoring_configuration())
    frames = {'NSA': nq_frames('N'), 'SA': nq_frames('A', seed=12)}
    for mode, kinds in frames.items():
        for kind, rows in kinds.items():
            add_cdr(tmp_path, f'NetCheck_UK_CDR_{kind.title()}_{mode}_2026_Q3.xlsx', kind, rows, mode)
    scoring_history.sync_history(core.repository)
    nq.sync_nq_calls(core.repository)
    login(client)
    summary = nq_prioritization.calculate(core.repository)
    return {'client': client, 'frames': frames, 'summary': summary}


def priority_rows() -> dict[str, dict]:
    with core.repository.connection() as connection:
        return {str(row['call_key']): dict(row) for row in connection.execute(
            f'SELECT p.*, l.service, l.nr_mode, l.operator, l.join_id FROM {nq_prioritization.PRIORITY_TABLE} p '
            f'JOIN {nq.NQ_CALL_LATEST_TABLE} l ON l.call_key = p.call_key')}


def test_every_call_holds_its_share_of_the_points_its_kpis_lose(prioritized):
    rows = priority_rows()
    assert rows and prioritized['summary']['scored'] == len(rows)
    assert {row['impact_state'] for row in rows.values()} == {'scored'}
    campaigns = nq_prioritization.status(core.repository)['campaigns']
    assert sorted((item['nr_mode'], item['campaign'], item['state']) for item in campaigns) == [
        ('NSA', '2026-Q3', 'scored'), ('SA', '2026-Q3', 'scored')]
    # The points of the call success ratio the operators lose in the scoring of the NSA CDRs (calculated from their rows),
    # which every Non-Qualified Voice call shares.
    from src.modules.scoring_config import validate_scoring_configuration
    from src.modules.scoring_methodologies import methodology_for
    configuration = validate_scoring_configuration(methodology_for(core.repository.get_scoring_profiles(), '2026-Q3')['configuration'])
    result = scoring.calculate_scoring(prioritized['frames']['NSA'], ['Campaign', 'Operator'], configuration=configuration,
                                       operator_mappings=core.repository.list_operator_mappings())
    lost = {(row['operator'], row['environment']): row['max_points'] - row['weighted_points'] for row in result['scoring']
            if row['kpi_code'] == 'K1' and row['weighted_points'] is not None}
    held: dict[tuple, float] = {}
    for row in rows.values():
        if row['nr_mode'] != 'NSA':
            continue
        for item in json.loads(row['impact_json']):
            if item['code'] == 'K1':
                held[(row['operator'], item['environment'])] = held.get((row['operator'], item['environment']), 0) + item['points']
    assert held and set(held) <= set(lost)
    for key, points in held.items():
        assert points == pytest.approx(lost[key], abs=0.01)
    # The level of the calls of each campaign, operator and service is a Pareto of their points.
    groups: dict[tuple, dict[str, list[float]]] = {}
    for row in rows.values():
        group = groups.setdefault((row['campaign_key'], row['operator'], row['service']), {})
        group.setdefault(row['impact_level'], []).append(row['impact_points'])
    assert any('High' in group for group in groups.values())
    for group in groups.values():
        if 'High' in group:
            assert min(group['High']) >= max(group.get('Medium', [0]) + group.get('Low', [0]))
        assert all(points == 0 for points in group.get('No impact', []))


def test_rules_prioritize_the_calls_and_fill_their_priority_until_it_is_chosen_by_hand(prioritized):
    rows = priority_rows()
    sa_voice = [row for row in rows.values() if row['nr_mode'] == 'SA' and row['service'] in {'voice', 'speech'}]
    assert sa_voice and {(row['prioritization'], row['priority_rule'], row['suggested_priority']) for row in sa_voice} == {
        ('Prioritized', 'SA Voice', 'P1')}
    nsa_data = [row for row in rows.values() if row['nr_mode'] == 'NSA' and row['service'] == 'data']
    for row in nsa_data:
        expected = 'Prioritized' if row['repeated'] == 'Yes' or row['impact_level'] == 'High' else 'Track only'
        assert (row['prioritization'], row['priority_rule']) == (expected, 'NSA Data')
        assert row['suggested_priority'] == ('P4' if expected == 'Prioritized' else 'P5')
    # The Priority of every open call is the one of its rule, recorded in its history.
    key = sa_voice[0]['call_key']
    with core.repository.connection() as connection:
        values = dict(connection.execute("SELECT call_key, value FROM nq_analysis_field_values WHERE field_key = 'priority'").fetchall())
        history = connection.execute("SELECT new_value, changed_by FROM nq_call_history WHERE call_key = ? AND field = 'field:priority'",
                                     (key,)).fetchall()
    assert len(values) == len(rows) and values[key] == 'P1'
    assert [tuple(row) for row in history] == [('P1', 'system')]
    # Chosen by hand: the rules keep it, also when they change.
    client = prioritized['client']
    call = client.get(f'/api/non-qualified-calls/calls/{key}').json()
    response = client.patch(f'/api/non-qualified-calls/calls/{key}', json={'changes': {'fields': {'priority': 'P3'}},
                                                                           'version': call['call']['version']})
    assert response.status_code == 200, response.text
    settings = nq_prioritization.load_settings(core.repository)
    settings['rules'][0]['priority'] = 'P2'
    response = client.put('/api/non-qualified-calls/prioritization/settings', json={'settings': settings})
    assert response.status_code == 200, response.text
    with core.repository.connection() as connection:
        values = dict(connection.execute("SELECT call_key, value FROM nq_analysis_field_values WHERE field_key = 'priority'").fetchall())
    assert values[key] == 'P3'
    assert {values[row['call_key']] for row in sa_voice if row['call_key'] != key} == {'P2'}
    assert priority_rows()[key]['priority_filled'] == nq_prioritization.BY_HAND
    # A priority the Priority field does not have is refused.
    settings['rules'][0]['priority'] = 'Urgent'
    response = client.put('/api/non-qualified-calls/prioritization/settings', json={'settings': settings})
    assert response.status_code == 400 and 'not a value of the Priority field' in response.json()['detail']


def test_repeated_issues_count_every_service_and_nr_mode_of_the_operator(prioritized):
    rows = priority_rows()
    repeated = [row for row in rows.values() if row['repeated'] == 'Yes']
    assert repeated and all(row['repetitions'] >= 2 for row in repeated)
    places: dict[tuple, set] = {}
    for row in rows.values():
        if row['place_key']:
            places.setdefault((row['operator'], row['place_key']), set()).add((row['service'], row['nr_mode']))
    # Some places repeat across services and across NR Modes.
    assert any(len({service for service, _mode in found}) > 1 for found in places.values())
    assert any(len({mode for _service, mode in found}) > 1 for found in places.values())
    for row in rows.values():
        if row['place_key']:
            assert row['repetitions'] == sum(1 for other in rows.values()
                                             if other['operator'] == row['operator'] and other['place_key'] == row['place_key'])


def test_panel_filters_and_exports_show_the_prioritization(prioritized):
    from pptx import Presentation

    client = prioritized['client']
    panel = client.post('/api/non-qualified-calls/prioritization', json={'filters': {}}).json()
    rows = priority_rows()
    assert panel['totals']['calls'] == len(rows)
    assert panel['totals']['prioritized'] == sum(row['prioritization'] == 'Prioritized' for row in rows.values())
    assert [rule['name'] for rule in panel['rules']] == ['SA Voice', 'SA Data', 'NSA Voice', 'NSA Data']
    assert panel['queue'] and len(panel['queue']) <= 20 and panel['queue'][0]['rule'] == 'SA Voice'
    assert panel['issues'] and panel['kpis']
    # Its values are fields of the calls: columns, filters and breakdowns of the Summary.
    fields = {field['source_ref']: field for field in nq.list_fields(core.repository) if field['source'] == 'priority'}
    assert set(fields) == set(nq_catalog.PRIORITY_REFS)
    assert [option['name'] for option in fields['priority_rule']['options']] == ['SA Voice', 'SA Data', 'NSA Voice', 'NSA Data']
    filtered = client.post('/api/non-qualified-calls/calls', json={
        'filters': {'fields': {fields['prioritization']['key']: ['Track only']}}, 'page_size': 100}).json()
    assert filtered['total'] == panel['totals']['tracked']
    assert {call['values'][fields['prioritization']['key']] for call in filtered['calls']} == {'Track only'}
    labels = [breakdown['label'] for breakdown in filtered['breakdowns']]
    assert {'By Prioritization', 'By Scoring Impact', 'By Repeated Issue'} <= set(labels)
    ordered = client.post('/api/non-qualified-calls/calls', json={
        'filters': {}, 'sort': f"field:{fields['impact_points']['key']}", 'direction': 'desc', 'page_size': 10}).json()
    points = [call['values'][fields['impact_points']['key']] for call in ordered['calls']]
    assert points == sorted(points, reverse=True)
    issue = panel['issues'][0]
    place = client.post('/api/non-qualified-calls/calls', json={'filters': {'place': [f"{issue['operator']}||{issue['place']}"]}}).json()
    assert place['total'] == issue['calls']
    # In the PowerPoint, each table on its slides.
    deck = client.post('/api/non-qualified-calls/export/powerpoint', json={'filters': {}})
    titles = [slide.shapes.title.text_frame.text for slide in Presentation(io.BytesIO(deck.content)).slides if slide.shapes.title is not None]
    assert any(title.startswith('NQ Prioritization') for title in titles)


def test_excluded_calls_lose_no_points(prioritized):
    rows = priority_rows()
    target = next(row for row in rows.values() if row['service'] == 'voice' and row['impact_points'])
    scoring_exclusions.create_list(core.repository, name='Faulty phone', calls=[{'join_id': target['join_id']}], username='super')
    scoring_exclusions.match_pending(core.repository)
    scoring_history.sync_history(core.repository)
    assert nq_prioritization.needs_calculation(core.repository)
    nq_prioritization.calculate(core.repository)
    row = priority_rows()[target['call_key']]
    assert (row['impact_state'], row['impact_level'], row['impact_points']) == ('excluded', 'Excluded from Scoring', 0.0)
    assert not nq_prioritization.needs_calculation(core.repository)


def test_campaigns_wait_for_the_scoring_history(client, tmp_path):
    enable_module()
    core.repository.replace_scoring_configuration(load_initial_scoring_configuration())
    for kind, rows in nq_frames('W').items():
        add_cdr(tmp_path, f'NetCheck_UK_CDR_{kind.title()}_2026_Q3.xlsx', kind, rows, 'NSA')
    nq.sync_nq_calls(core.repository)
    nq_prioritization.calculate(core.repository)
    campaign = nq_prioritization.status(core.repository)['campaigns'][0]
    assert campaign['state'] == 'pending' and 'Scoring History' in campaign['detail']
    assert {row['impact_level'] for row in priority_rows().values()} == {'Not scored'}
    # The repetitions do not wait.
    assert any(row['repeated'] == 'Yes' for row in priority_rows().values())


def test_only_admins_change_the_rules_and_editors_recalculate(prioritized):
    client = prioritized['client']
    workspace_user('editor', 'user-editor')
    login(client, 'editor', 'editor123')
    settings = nq_prioritization.load_settings(core.repository)
    assert client.put('/api/non-qualified-calls/prioritization/settings', json={'settings': settings}).status_code == 403
    response = client.post('/api/non-qualified-calls/prioritization/recalculate')
    assert response.status_code == 200, response.text
    assert client.get('/api/non-qualified-calls/prioritization/settings').json()['settings']['rules'][0]['name'] == 'SA Voice'
    assert 'nq_prioritization_recalculate' in [row['action'] for row in core.repository.list_logs(limit=50)]


def test_rules_travel_with_the_configuration(prioritized):
    settings = nq_prioritization.load_settings(core.repository)
    settings['rules'] = settings['rules'][:2]
    settings['high_share'] = 40
    nq_prioritization.save_settings(core.repository, settings, 'super')
    document = nq.export_configuration_document(core.repository)
    assert json.loads(document)['prioritization']['high_share'] == 40
    core.repository.set_workspace_state(nq_prioritization.SETTINGS_STATE_KEY, json.dumps(nq_prioritization.default_settings()))
    nq.import_configuration_document(core.repository, document)
    restored = nq_prioritization.load_settings(core.repository)
    assert [rule['name'] for rule in restored['rules']] == ['SA Voice', 'SA Data'] and restored['high_share'] == 40


def test_workspaces_of_earlier_versions_get_the_tables_and_fields(client, tmp_path):
    enable_module()
    nq.ensure_nq_tables(core.repository)
    keys = nq.V23_FIELD_KEYS
    fields = [field for field in nq.list_fields(core.repository) if field['key'] not in keys]
    nq._store_fields(core.repository, fields)
    with core.repository.connection() as connection:
        connection.execute(f'DROP TABLE {nq_prioritization.PRIORITY_TABLE}')
        connection.execute("DELETE FROM workspace_state WHERE key IN (?, ?)", (nq.ANALYSIS_CENTER_V23_STATE_KEY, nq.SCHEMA_STATE_KEY))
    nq.ensure_nq_tables(core.repository)
    with core.repository.connection() as connection:
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (nq_prioritization.PRIORITY_TABLE,)).fetchone()
    order = [field['key'] for field in nq.list_fields(core.repository)]
    assert keys <= set(order) and order.index('prioritization') == order.index('priority') + 1
    shown = {field['key'] for field in nq.list_fields(core.repository) if field['in_table']}
    assert {'prioritization', 'scoring_impact', 'scoring_points_lost', 'repeated_issue'} <= shown
