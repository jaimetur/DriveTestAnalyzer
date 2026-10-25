"""DT Analyzer RCA of Non-Qualified Calls: the engine and its default rules, the inputs read from the CDR while
indexing, the results in every place the RCA sources are listed, the editable rules and their transfer."""

import hashlib
import json

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import non_qualified_calls as nq
from src.modules import nq_catalog, nq_dta_rca
from tests.test_non_qualified_calls import add_cdr, enable_module, login, query, workspace_user


@pytest.fixture(autouse=True)
def indexing_runs_at_once(monkeypatch):
    monkeypatch.setattr(core, 'submit_background_task', lambda callback, *args: callback(*args))


def evaluate(call: dict, inputs: dict, rules=None):
    compiled = nq_dta_rca.compile_rules(rules or nq_dta_rca.default_rules(), nq_catalog.default_root_catalog())
    return nq_dta_rca.evaluate(compiled, {'service': 'data', 'result': 'Failed', **call}, inputs)


def test_every_default_rule_is_valid_and_gives_a_domain_of_the_default_catalog():
    rules = nq_dta_rca.default_rules()
    assert nq_dta_rca.normalize_rules(rules, strict=True) == rules
    compiled = nq_dta_rca.compile_rules(rules, nq_catalog.default_root_catalog())
    assert all(entry['result']['domain'] for entry in compiled), [entry['rule']['name'] for entry in compiled if not entry['result']['domain']]
    # The last rule takes every call the others leave.
    assert rules[-1]['name'] == 'Not identified' and not rules[-1]['conditions']


def test_the_first_rule_that_holds_gives_the_root_cause_with_its_evidence():
    # The radio comes before the service: a DNS failure in poor coverage is a coverage problem.
    dns = {'failure_classification': 'Protocol Problems', 'failure_category': 'DNS', 'failure_subcategory': 'No response from DNS'}
    result = evaluate(dns, {'lte_rsrp': -118.4, 'lte_sinr': 4})
    assert (result['rule'], result['category'], result['cause'], result['domain']) == ('Poor LTE coverage', 'Poor Coverage LTE', 'Coverage', 'RF')
    assert result['evidence'] == 'LTE RSRP (average) −118.4 dBm (< −110 dBm)'
    result = evaluate(dns, {'lte_rsrp': -85, 'lte_sinr': 12})
    assert (result['rule'], result['cause'], result['domain']) == ('DNS', 'DNS', 'Protocol')
    assert 'No response from DNS' in result['evidence']
    # What the provider reports outside the radio comes first, also in poor coverage.
    voice = evaluate({'service': 'voice', 'failure_subcategory': 'No QCI1 bearer activation'}, {'lte_rsrp': -120})
    assert voice['cause'] == 'No QCI1 established'
    # A Voice failure with good radio and nothing else is a potential E2E issue; a Data one is not identified.
    assert evaluate({'service': 'voice', 'result': 'Dropped'}, {'lte_rsrp': -80, 'lte_sinr': 15})['cause'] == 'Potential E2E Issue'
    assert evaluate({'test_name': 'Ping 40'}, {'lte_rsrp': -80})['rule'] == 'Not identified'
    # Any condition: a packet loss above 5 % holds without a failure description.
    assert evaluate({}, {'packet_loss': 12.5})['rule'] == 'Packet loss'
    # A Cutoff test with good radio has a low throughput.
    assert evaluate({'result': 'Cutoff'}, {'lte_rsrp': -80, 'lte_sinr': 15})['cause'] == 'Low throughput'


def test_good_radio_needs_the_radio_measured_and_reported_radio_takes_the_category_of_its_technology():
    # Without radio values, a Cutoff test or a Voice failure says nothing about the radio.
    assert evaluate({'result': 'Cutoff'}, {})['rule'] == 'Not identified'
    assert evaluate({'service': 'voice', 'result': 'Dropped'}, {})['rule'] == 'Not identified'
    assert evaluate({'service': 'voice', 'result': 'Dropped'}, {'nr_sinr': 12})['cause'] == 'Potential E2E Issue'
    interference = {'failure_classification': 'RF Problems', 'failure_category': 'Interference problem',
                    'failure_subcategory': 'DL interference problems'}
    for technology, category in (('5G', 'DL Interference NR'), ('5G/4G', 'DL Interference LTE'), ('2G', 'DL Interference 2G/3G'),
                                 ('', 'DL Interference LTE')):
        assert evaluate({**interference, 'failure_technology': technology}, {})['category'] == category, technology
    # Without a Failure Technology, the technology of the call decides.
    assert evaluate({**interference, 'technology': 'NR SA'}, {})['category'] == 'DL Interference NR'
    coverage = {'failure_category': 'Coverage gaps (PLMN lost)', 'failure_technology': '5G SA'}
    assert (evaluate(coverage, {})['category'], evaluate(coverage, {})['cause']) == ('Poor Coverage NR', 'Coverage')
    uplink = evaluate({'failure_subcategory': 'UL interference problems', 'failure_technology': '4G'}, {})
    assert (uplink['category'], uplink['cause']) == ('UL Interference LTE', 'UL interference')


def test_rules_keep_to_their_services_and_disabled_rules_are_skipped():
    rules = nq_dta_rca.default_rules()
    voice_only = [dict(rule, services=['voice']) if rule['key'] == 'lte-coverage' else rule for rule in rules]
    assert evaluate({}, {'lte_rsrp': -120}, voice_only)['rule'] != 'Poor LTE coverage'
    disabled = [dict(rule, enabled=False) if rule['key'] == 'lte-coverage' else rule for rule in rules]
    assert evaluate({}, {'lte_rsrp': -120}, disabled)['rule'] != 'Poor LTE coverage'
    assert nq_dta_rca.compile_rules(disabled, nq_catalog.default_root_catalog())[0]['rule']['key'] == rules[0]['key']


def test_invalid_rules_say_what_is_wrong():
    rule = {'name': 'Weak', 'services': ['data'], 'match': 'all', 'category': 'Poor Coverage LTE', 'cause': '',
            'conditions': [{'input': 'lte_rsrp', 'op': 'lt', 'value': '-100'}]}
    assert nq_dta_rca.normalize_rules([rule], strict=True)[0]['conditions'][0]['value'] == -100
    for change, message in (({'conditions': [{'input': 'unknown', 'op': 'lt', 'value': 1}]}, 'choose the value'),
                            ({'conditions': [{'input': 'lte_rsrp', 'op': 'contains', 'value': 'x'}]}, 'how LTE RSRP'),
                            ({'conditions': [{'input': 'lte_rsrp', 'op': 'lt', 'value': 'weak'}]}, 'with a number'),
                            ({'conditions': [{'input': 'failure_text', 'op': 'contains', 'value': ' , '}]}, 'write the words'),
                            ({'category': '', 'cause': ''}, 'Root Category or the Root Cause')):
        with pytest.raises(ValueError, match=message):
            nq_dta_rca.normalize_rules([{**rule, **change}], strict=True)
    with pytest.raises(ValueError, match='repeated'):
        nq_dta_rca.normalize_rules([rule, rule], strict=True)
    with pytest.raises(ValueError, match='at least one rule'):
        nq_dta_rca.normalize_rules([], strict=True)


def voice_frame() -> pd.DataFrame:
    """Three Non-Qualified Voice calls: one in poor LTE coverage, one with a VoLTE core failure in good radio, one with good
    radio and no failure description; and a completed call."""
    return pd.DataFrame({
        'JOIN_ID': ['0xA1', '0xB2', '0xC3', '0xD4'],
        'Session_ID_A': [1, 2, 3, 4],
        'Operator': ['EE'] * 4,
        'Campaign': ['UK_Q3_2026'] * 4,
        'Session_Type': ['CALL'] * 4,
        'Call_Status': ['Failed', 'Failed', 'Dropped', 'Completed'],
        'status': ['Failed', 'Failed', 'Dropped', 'Completed'],
        'Call_Start_Time': ['2026-09-01 10:00:00', '2026-09-02 11:00:00', '2026-09-03 12:00:00', '2026-09-03 13:00:00'],
        'Technology': ['LTE'] * 4,
        'Failure_Classification': ['', 'VoLTE Problems', '', ''],
        'Failure_Category': ['', 'VoLTE Core', '', ''],
        'Failure_Subcategory': ['', 'VoLTE Core Failure', '', ''],
        '4G_RSRP_Avg_A': [-121.5, -80.0, -82.0, -75.0],
        '4G_SINR_Avg_A': [2.0, 15.0, 14.0, 20.0],
        'Cell_ID_A': ['123456', '123457', '123458', '1'],
    })


def setup_calls(client, tmp_path) -> dict[str, dict]:
    enable_module()
    add_cdr(tmp_path, 'UK_Voice_Q3.xlsx', 'voice', voice_frame())
    login(client)
    return {call['join_id']: call for call in query(client)['calls']}


def detail(client, call) -> dict:
    response = client.get(f"/api/non-qualified-calls/calls/{call['call_key']}")
    assert response.status_code == 200, response.text
    return response.json()['call']


def test_every_call_gets_the_dta_rca_in_its_fields_recommendation_and_panels(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    assert set(calls) == {'0xA1', '0xB2', '0xC3'}
    # The inputs of the RCA are read from the CDR while indexing, in the units of the RCA.
    with core.repository.connection() as connection:
        inputs = {str(row['join_id']): json.loads(row['rca_inputs_json']) for row in connection.execute(
            'SELECT join_id, rca_inputs_json FROM nq_calls')}
    assert inputs['0xA1']['lte_rsrp'] == -121.5 and inputs['0xA1']['lte_sinr'] == 2.0
    coverage, core_failure, good = (detail(client, calls[key]) for key in ('0xA1', '0xB2', '0xC3'))
    # Its five fields come first in the RCA section, before those of the NetCheck RCA.
    state = client.get('/api/non-qualified-calls/state').json()
    keys = [field['key'] for field in state['fields']]
    assert keys[keys.index('netcheck_failure_classification') - 5:keys.index('netcheck_failure_classification')] == [
        'dta_rca_domain', 'dta_rca_category', 'dta_rca_cause', 'dta_rca_rule', 'dta_rca_evidence']
    assert state['dta_refs'] == nq_catalog.DTA_REFS and state['rca_sources']['dta'] == 'DT Analyzer RCA'
    assert (coverage['values']['dta_rca_domain'], coverage['values']['dta_rca_category'], coverage['values']['dta_rca_cause']) == (
        'RF', 'Poor Coverage LTE', 'Coverage')
    assert coverage['values']['dta_rca_rule'] == 'Poor LTE coverage'
    assert '−121.5 dBm' in coverage['values']['dta_rca_evidence']
    assert core_failure['values']['dta_rca_cause'] == 'VoLTE core'
    assert (good['values']['dta_rca_category'], good['values']['dta_rca_cause']) == ('E2E', 'Potential E2E Issue')
    # The recommendation has its card after the NetCheck RCA, with the rule and the evidence.
    sources = {source['source']: source for source in coverage['rca_recommendation']['sources']}
    assert sources['dta']['label'] == 'DT Analyzer RCA' and sources['dta']['raw_category'] == 'Poor LTE coverage'
    assert sources['dta']['evidence'] and coverage['rca_recommendation']['recommendation']['category'] == 'Poor Coverage LTE'
    # The Root Cause Analysis counts the calls with it, and its root domain filters them.
    response = client.post('/api/non-qualified-calls/root-causes/stats', json={'filters': {}, 'source': 'dta'})
    assert response.status_code == 200, response.text
    stats = response.json()
    assert stats['source'] == 'dta' and stats['summary']['labelled'] == 3
    assert {item['value']: item['count'] for item in stats['domains']} == {'RF': 1, 'IMS/E2E': 2}
    filtered = query(client, filters={'dta_domain': ['RF']})['calls']
    assert [call['join_id'] for call in filtered] == ['0xA1']
    # RCA Insights compares it with the other sources.
    insights = client.post('/api/non-qualified-calls/rca/insights', json={'filters': {}}).json()
    assert insights['coverage']['dta'] == 3
    assert {item['domain'] for item in insights['domains']['dta']} == {'RF', 'IMS/E2E'}
    assert {'selected_dta', 'netcheck_dta', 'script_dta'} <= set(insights['agreement']) and 'dta' in insights['confusion']
    # The table column of a field of the RCA reads it in the query, and the Excel export has it.
    columns = nq.field_sql({'source': 'dta', 'source_ref': 'dta_cause', 'key': 'dta_rca_cause'})
    assert 'dta_json' in columns


def test_admins_change_the_rules_and_every_call_follows_them(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    payload = client.get('/api/non-qualified-calls/dta-rca/rules').json()
    assert payload['rules'] == nq_dta_rca.default_rules() and payload['counts']['Poor LTE coverage'] == 1
    # A stricter coverage threshold leaves the call to the Voice rule of good radio.
    rules = [dict(rule, conditions=[{'input': 'lte_rsrp', 'op': 'lt', 'value': -125}]) if rule['key'] == 'lte-coverage' else rule
             for rule in payload['rules']]
    response = client.put('/api/non-qualified-calls/dta-rca/rules', json={'rules': rules})
    assert response.status_code == 200, response.text
    assert response.json()['calculated'] == 3 and 'Poor LTE coverage' not in response.json()['counts']
    assert detail(client, calls['0xA1'])['values']['dta_rca_cause'] == 'Potential E2E Issue'
    log = next(row for row in core.repository.list_logs(limit=50) if row['action'] == 'nq_dta_rca_rules')
    details = json.loads(log['details'])
    assert details['message'] == 'DT Analyzer RCA rules updated.'
    assert any(line.startswith('Rule changed: Poor LTE coverage') and '−125 dBm' in line for line in details['changes'])
    # A rule the editor cannot save tells why.
    response = client.put('/api/non-qualified-calls/dta-rca/rules',
                          json={'rules': [{'name': 'Broken', 'conditions': [], 'category': '', 'cause': ''}]})
    assert response.status_code == 400 and 'Root Category or the Root Cause' in response.json()['detail']
    # Default Rules brings the default rules back.
    response = client.put('/api/non-qualified-calls/dta-rca/rules', json={'rules': [], 'defaults': True})
    assert response.status_code == 200 and response.json()['rules'] == nq_dta_rca.default_rules()
    assert detail(client, calls['0xA1'])['values']['dta_rca_cause'] == 'Coverage'
    # Only admins and super-admins change them; every user reads them.
    workspace_user('analyst', 'user-editor')
    login(client, 'analyst', 'analyst123')
    assert client.get('/api/non-qualified-calls/dta-rca/rules').status_code == 200
    assert client.put('/api/non-qualified-calls/dta-rca/rules', json={'rules': rules}).status_code == 403


def test_the_rules_travel_with_the_nq_calls_configuration(client, tmp_path):
    setup_calls(client, tmp_path)
    rules = [dict(rule, enabled=False) if rule['key'] == 'voice-e2e' else rule for rule in nq_dta_rca.default_rules()]
    nq_dta_rca.save_rules(core.repository, rules, 'super')
    document = json.loads(nq.export_configuration_document(core.repository))
    assert document['dta_rca_rules'] == rules
    current = json.loads(nq.export_configuration_document(core.repository))
    changed = dict(document, dta_rca_rules=nq_dta_rca.default_rules())
    lines = nq.configuration_changes(current, nq.predicted_configuration(current, changed))
    assert any(line.startswith('DT Analyzer RCA rules · Rule changed: Voice failure with good radio') for line in lines)
    nq.import_configuration_document(core.repository, json.dumps(changed))
    assert nq_dta_rca.load_rules(core.repository) == nq_dta_rca.default_rules()
    # The results follow the imported rules as soon as the calls are read.
    calls = {call['join_id']: call for call in query(client)['calls']}
    assert detail(client, calls['0xC3'])['values']['dta_rca_cause'] == 'Potential E2E Issue'


def test_a_change_of_the_catalog_calculates_the_calls_again(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    catalog = nq.list_root_causes(core.repository)
    for item in catalog['domains']:
        item['previous'] = item['name']
        if item['name'] == 'RF':
            item['name'] = 'Radio'
    nq.save_root_causes(core.repository, catalog, False, 'super')
    # The rule gives Poor Coverage LTE, whose domain is renamed.
    values = detail(client, calls['0xA1'])['values']
    assert (values['dta_rca_category'], values['dta_rca_domain']) == ('Poor Coverage LTE', 'Radio')
    with core.repository.connection() as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert nq_dta_rca.RESULTS_TABLE in tables and nq.NQ_TABLE_TITLES[nq_dta_rca.RESULTS_TABLE] == 'NQ DT Analyzer RCA Results'


def test_the_catalog_keeps_the_values_the_rules_give(client, tmp_path):
    setup_calls(client, tmp_path)
    payload = client.get('/api/non-qualified-calls/root-causes').json()
    given = payload['dta_rules']
    assert {'Poor LTE coverage', 'LTE uplink at maximum power'} <= set(given['categories']['Poor Coverage LTE'])
    assert 'Device or test setup' in given['causes']['Device or test setup'] and 'AAA' in given['domains']
    assert 'Procedure Overlap' not in given['categories']
    base = {kind: [{**item, 'previous': item['name']} for item in payload[kind]] for kind in ('domains', 'categories', 'causes')}

    def put(**changes):
        return client.put('/api/non-qualified-calls/root-causes', json={**base, 'require_to_close': False, **changes})

    def renamed(kind, name, new_name):
        return [dict(item, name=new_name) if item['name'] == name else item for item in base[kind]]

    # A category or cause a rule gives can be neither renamed nor removed, and a domain it gives cannot be removed.
    refused = put(categories=renamed('categories', 'Poor Coverage LTE', 'LTE Coverage'))
    assert refused.status_code == 400
    rules = given['categories']['Poor Coverage LTE']
    assert refused.json()['detail'] == (f'The Root Category "Poor Coverage LTE" is given by the DT Analyzer RCA rules "{rules[0]}", '
                                        f'"{rules[1]}", "{rules[2]}" and {len(rules) - 3} more; change those rules first to rename it.')
    refused = put(domains=[item for item in base['domains'] if item['name'] != 'AAA'])
    assert refused.status_code == 400 and refused.json()['detail'].startswith('The domain "AAA" is given by the DT Analyzer RCA rule ')
    # Also when the rule is disabled.
    nq_dta_rca.save_rules(core.repository, [dict(rule, enabled=rule['key'] != 'device') for rule in nq_dta_rca.load_rules(core.repository)], 'super')
    refused = put(causes=[item for item in base['causes'] if item['name'] != 'Device or test setup'])
    assert refused.status_code == 400 and refused.json()['detail'].endswith('"Device or test setup"; change the rule first to remove it.')
    # Nothing changed; a change of case keeps the name the rules read, a domain is renamed with its categories and
    # causes, and a value no rule gives is renamed.
    assert nq.list_root_causes(core.repository)['domains'] == payload['domains']
    saved = put(domains=renamed('domains', 'RF', 'Radio'), categories=renamed('categories', 'Procedure Overlap', 'Overlapping Procedures'),
                causes=renamed('causes', 'Device or test setup', 'Device or Test Setup'))
    assert saved.status_code == 200, saved.text
    assert saved.json()['dta_rules']['categories']['Poor Coverage LTE'] == given['categories']['Poor Coverage LTE']
    assert {item['name']: item['domain'] for item in saved.json()['categories']}['Poor Coverage LTE'] == 'Radio'
    # Once no rule gives it, it can go.
    rules = [dict(rule, category='Poor Coverage NR') if rule['category'] == 'Poor Coverage LTE' else rule
             for rule in nq_dta_rca.load_rules(core.repository)]
    nq_dta_rca.save_rules(core.repository, rules, 'super')
    payload = client.get('/api/non-qualified-calls/root-causes').json()
    assert 'Poor Coverage LTE' not in payload['dta_rules']['categories']
    categories = [{**item, 'previous': item['name']} for item in payload['categories'] if item['name'] != 'Poor Coverage LTE']
    assert client.put('/api/non-qualified-calls/root-causes', json={**payload, 'categories': categories}).status_code == 200


def test_workspaces_with_the_former_name_of_its_fields_take_the_short_name(client, tmp_path):
    setup_calls(client, tmp_path)
    fields = nq.list_fields(core.repository)
    for field in fields:
        if field['key'] in nq.V27_FIELD_KEYS:
            field['label'] = field['label'].replace('DT Analyzer RCA', 'DriveTest Analyzer RCA')
            field['description'] = field['description'].replace('DT Analyzer RCA', 'DriveTest Analyzer RCA')
    nq._store_fields(core.repository, fields)
    core.repository.set_workspace_state(nq.ANALYSIS_CENTER_V28_STATE_KEY, '')
    core.repository.set_workspace_state(nq.SCHEMA_STATE_KEY, '')
    nq.ensure_nq_tables(core.repository)
    renamed = {field['key']: field for field in nq.list_fields(core.repository) if field['key'] in nq.V27_FIELD_KEYS}
    assert renamed['dta_rca_category']['label'] == 'DT Analyzer RCA Root Category'
    assert all('DriveTest Analyzer RCA' not in field['label'] + field['description'] for field in renamed.values())


def test_every_rule_gives_a_root_category_and_workspaces_get_its_categories(client, tmp_path):
    compiled = nq_dta_rca.compile_rules(nq_dta_rca.default_rules(), nq_catalog.normalize_root_catalog(nq_catalog.default_root_catalog()))
    assert all(entry['result']['category'] for entry in compiled), [entry['rule']['name'] for entry in compiled if not entry['result']['category']]
    setup_calls(client, tmp_path)
    # A catalog of before, without the categories of the DT Analyzer RCA and with DNS mapped to no category.
    catalog = nq.list_root_causes(core.repository)
    catalog['categories'] = [item for item in catalog['categories'] if item['name'] not in nq_catalog.DTA_CATEGORIES]
    for item in catalog['causes']:
        if item['name'] in nq_catalog.DEFAULT_CAUSE_CATEGORIES:
            item['category'] = ''
    # Stored as it was then: today the catalog keeps the categories the rules give.
    with core.repository.connection() as connection:
        nq._write_root_catalog(connection, nq_catalog.normalize_root_catalog(catalog))
    core.repository.set_workspace_state(nq.ANALYSIS_CENTER_V29_STATE_KEY, '')
    core.repository.set_workspace_state(nq.SCHEMA_STATE_KEY, '')
    nq.ensure_nq_tables(core.repository)
    root = nq.list_root_causes(core.repository)
    assert set(nq_catalog.DTA_CATEGORIES) <= {item['name'] for item in root['categories']}
    causes = {item['name']: item for item in root['causes']}
    assert causes['DNS']['category'] == 'Protocol / Server' and causes['DNS']['domain'] == 'Protocol'
    assert causes['Low throughput']['category'] == 'RAN Performance'
    log = next(row for row in core.repository.list_logs(limit=50) if row['action'] == 'nq_root_causes' and 'DT Analyzer' in row['details'])
    assert json.loads(log['details'])['causes_mapped'] == len(nq_catalog.DEFAULT_CAUSE_CATEGORIES)


def test_it_learns_from_the_decisions_of_the_analysts_when_asked(client, tmp_path):
    enable_module()
    frame = pd.DataFrame({
        'JOIN_ID': [f'0xE{index}' for index in range(4)], 'Session_ID_A': [1, 2, 3, 4], 'Operator': ['EE'] * 4,
        'Campaign': ['UK_Q3_2026'] * 4, 'Session_Type': ['CALL'] * 4, 'Call_Status': ['Dropped'] * 4, 'status': ['Dropped'] * 4,
        'Call_Start_Time': [f'2026-09-0{index + 1} 10:00:00' for index in range(4)], 'Technology': ['LTE'] * 4,
        '4G_RSRP_Avg_A': [-80.0] * 4, '4G_SINR_Avg_A': [15.0] * 4, 'Cell_ID_A': ['1', '2', '3', '4'],
    })
    add_cdr(tmp_path, 'UK_Voice_Q3.xlsx', 'voice', frame)
    login(client)
    calls = {call['join_id']: call for call in query(client)['calls']}
    for key in ('0xE0', '0xE1', '0xE2'):
        response = client.patch(f"/api/non-qualified-calls/calls/{calls[key]['call_key']}",
                                json={'changes': {'root_category': 'Poor Coverage LTE', 'root_cause': 'LOS but weak signal'}})
        assert response.status_code == 200, response.text
    # Off by default: the rule gives every call its root cause.
    assert detail(client, calls['0xE3'])['values']['dta_rca_cause'] == 'Potential E2E Issue'
    payload = client.get('/api/non-qualified-calls/dta-rca/rules').json()
    assert payload['settings'] == {'learn': False} and payload['learned'] == 0
    response = client.put('/api/non-qualified-calls/dta-rca/rules', json={'rules': payload['rules'], 'learn': True})
    assert response.status_code == 200 and response.json()['settings'] == {'learn': True}
    # The undecided call takes what the analysts gave the three others of its pattern; a decided one learns from the
    # two others only (its own decision never counts).
    learned = detail(client, calls['0xE3'])
    assert (learned['values']['dta_rca_category'], learned['values']['dta_rca_cause'], learned['values']['dta_rca_domain']) == (
        'Poor Coverage LTE', 'LOS but weak signal', 'RF')
    assert learned['values']['dta_rca_rule'] == 'Voice failure with good radio'
    assert learned['values']['dta_rca_evidence'].startswith('Learned from the analysts: 3 of the 3 other calls')
    source = next(item for item in learned['rca_recommendation']['sources'] if item['source'] == 'dta')
    assert source['learned'] and source['category'] == 'Poor Coverage LTE'
    assert detail(client, calls['0xE0'])['values']['dta_rca_evidence'].startswith('Learned from the analysts: 2 of the 2 other calls')
    assert client.get('/api/non-qualified-calls/dta-rca/rules').json()['learned'] == 4
    log = next(row for row in core.repository.list_logs(limit=50) if row['action'] == 'nq_dta_rca_learning')
    assert json.loads(log['details'])['learn'] is True
    # A decision less leaves two others for the undecided call, and one for each decided call: they go back to the rule.
    client.patch(f"/api/non-qualified-calls/calls/{calls['0xE2']['call_key']}", json={'changes': {'root_category': '', 'root_cause': ''}})
    assert detail(client, calls['0xE3'])['values']['dta_rca_cause'] == 'LOS but weak signal'
    assert detail(client, calls['0xE0'])['values']['dta_rca_cause'] == 'Potential E2E Issue'
    # The setting travels with the configuration; off again, every call takes its rule.
    assert json.loads(nq.export_configuration_document(core.repository))['dta_rca_settings'] == {'learn': True}
    client.put('/api/non-qualified-calls/dta-rca/rules', json={'rules': payload['rules'], 'learn': False})
    assert detail(client, calls['0xE3'])['values']['dta_rca_cause'] == 'Potential E2E Issue'


def test_what_it_learned_comes_back_after_a_reindex(client, tmp_path):
    enable_module()
    frame = pd.DataFrame({
        'JOIN_ID': [f'0xE{index}' for index in range(4)], 'Session_ID_A': [1, 2, 3, 4], 'Operator': ['EE'] * 4,
        'Campaign': ['UK_Q3_2026'] * 4, 'Session_Type': ['CALL'] * 4, 'Call_Status': ['Dropped'] * 4, 'status': ['Dropped'] * 4,
        'Call_Start_Time': [f'2026-09-0{index + 1} 10:00:00' for index in range(4)], 'Technology': ['LTE'] * 4,
        '4G_RSRP_Avg_A': [-80.0] * 4, '4G_SINR_Avg_A': [15.0] * 4, 'Cell_ID_A': ['1', '2', '3', '4'],
    })
    add_cdr(tmp_path, 'UK_Voice_Q3.xlsx', 'voice', frame)
    login(client)
    calls = {call['join_id']: call for call in query(client)['calls']}
    for key in ('0xE0', '0xE1', '0xE2'):
        client.patch(f"/api/non-qualified-calls/calls/{calls[key]['call_key']}",
                     json={'changes': {'root_category': 'Poor Coverage LTE', 'root_cause': 'LOS but weak signal'}})
    rules = client.get('/api/non-qualified-calls/dta-rca/rules').json()['rules']
    client.put('/api/non-qualified-calls/dta-rca/rules', json={'rules': rules, 'learn': True})
    assert client.get('/api/non-qualified-calls/dta-rca/rules').json()['learned'] == 4
    # A Reindex removes what the rows of every CDR learned and gives their results the same count and row numbers: the
    # calls learn again.
    assert client.post('/api/non-qualified-calls/reindex').status_code == 200
    calls = {call['join_id']: call for call in query(client)['calls']}
    assert client.get('/api/non-qualified-calls/dta-rca/rules').json()['learned'] == 4
    assert detail(client, calls['0xE3'])['values']['dta_rca_cause'] == 'LOS but weak signal'
    # A workspace a Reindex left without what it learned, with the fingerprint of before (without the indexed CDRs),
    # learns again once.
    with core.repository.connection() as connection:
        connection.execute(f'DELETE FROM {nq.NQ_DTA_LEARNED_TABLE}')
        decisions = connection.execute(f"SELECT call_key, root_category, root_cause FROM {nq.NQ_CALL_TRACKING_TABLE} "
                                       "WHERE root_category <> '' OR root_cause <> '' ORDER BY call_key").fetchall()
        results = tuple(connection.execute(f'SELECT COUNT(*), MAX(rowid) FROM {nq.NQ_DTA_RESULTS_TABLE}').fetchone())
    before = json.dumps([core.repository.get_workspace_state(nq_dta_rca.FINGERPRINT_STATE_KEY), results,
                         [tuple(row) for row in decisions]], default=str)
    core.repository.set_workspace_state(nq_dta_rca.LEARNED_FINGERPRINT_STATE_KEY, hashlib.sha1(before.encode('utf-8')).hexdigest())
    query(client)
    assert client.get('/api/non-qualified-calls/dta-rca/rules').json()['learned'] == 4


def test_the_lack_of_resources_is_found_from_the_provider_and_from_the_cdr_itself():
    # The provider reports insufficient resources of the core: before the reject is taken for an authentication one.
    found = evaluate({'failure_category': 'PDU Session Establishment Reject', 'failure_subcategory': 'Insufficient resources'}, {})
    assert (found['rule_key'], found['category'], found['cause']) == ('core-resources', 'Core Network', 'Insufficient resources')
    # The signalling of the CDR itself, without any RCA of the provider: the network rejected the RRC connection.
    found = evaluate({}, {'failure_events': '[RRCConnectionRequest]->[RRCConnectionReject]'})
    assert (found['rule_key'], found['category'], found['cause']) == ('access-rejected', 'RAN Capacity', 'Access rejected (no resources)')
    assert found['evidence'].startswith('Signalling events contains “rrcconnectionreject”')
    assert evaluate({}, {'failure_events': '[RRCConnectionReestablishmentReject]'})['rule_key'] != 'access-rejected'
    # A test cut off with good radio on a carrier that gave it few of its resource blocks: a loaded cell.
    radio = {'lte_rsrp': -85.0, 'lte_sinr': 15.0}
    found = evaluate({'result': 'Cutoff'}, {**radio, 'lte_dl_rbs': 12.0, 'lte_dl_bandwidth': 20.0})
    assert (found['rule_key'], found['category'], found['cause']) == ('cell-load', 'RAN Capacity', 'Cell overload')
    assert 'LTE DL resource blocks used 12 % (< 25 %)' in found['evidence']
    assert evaluate({'result': 'Cutoff'}, {**radio, 'lte_dl_rbs': 80.0, 'lte_dl_bandwidth': 20.0})['rule_key'] == 'low-throughput'
    # The resource blocks of the carrier: LTE by its bandwidth, NR at 30 kHz in TDD bands and wide carriers, else 15 kHz.
    assert nq_dta_rca.resource_block_share(50, 20, 'LTE') == 50.0
    assert nq_dta_rca.resource_block_share(136.5, 100, 'NR', 'n78') == 50.0
    assert nq_dta_rca.resource_block_share(26, 10, 'NR', 'n28') == 50.0
    assert nq_dta_rca.resource_block_share(None, 20, 'LTE') is None and nq_dta_rca.resource_block_share(10, 7, 'NR') is None


def test_the_network_around_the_call_finds_holes_overshooting_pci_collisions_outages_and_ping_pongs():
    weak = {'lte_rsrp': -116.0, 'lte_sinr': 1.0}
    note = 'Network Inventory: nearest site 12 (Vodafone) at 7.00 km'
    found = evaluate({}, {**weak, 'nearest_site_distance': 7.0, 'nearest_site_isd_ratio': 2.3, 'network_note': note})
    assert (found['rule_key'], found['category'], found['cause']) == ('coverage-hole', 'Poor Coverage LTE', 'Large distance to the nearest site')
    assert found['evidence'].endswith(f'. {note}')
    assert evaluate({}, {'nearest_site_isd_ratio': 2.3})['rule_key'] == 'no-service-hole'
    # Served from beyond twice the inter-site distance of its site: overshooting, in NR alone too; not where sites are far apart.
    far = {'serving_distance': 3.0, 'serving_isd_ratio': 2.5, 'nearest_site_isd_ratio': .4}
    found = evaluate({}, {**weak, **far})
    assert (found['rule_key'], found['category'], found['cause']) == ('overshooting', 'DL Interference LTE', 'Overshooting or excessive cell overlap')
    found = evaluate({'failure_technology': '5G SA'}, {'nr_rsrp': -100.0, 'nr_sinr': -2.0, **far})
    assert (found['rule_key'], found['category']) == ('nr-overshooting', 'DL Interference NR')
    assert evaluate({}, {**weak, **far, 'serving_isd_ratio': 1.2})['rule_key'] == 'lte-coverage'
    # A cell around with the PCI and channel of its own, with interference.
    found = evaluate({}, {'lte_rsrp': -95.0, 'lte_sinr': .5, 'pci_collisions': 2})
    assert (found['rule_key'], found['cause']) == ('pci-collision', 'PCI Collision/PCI MOD 3 Collision')
    # Cells out of service on its sites, when its radio suffered.
    found = evaluate({}, {'lte_rsrp': -108.0, 'lte_sinr': 8.0, 'cells_out_of_service': 3})
    assert (found['rule_key'], found['category'], found['cause']) == ('cell-outage', 'Operational', 'Cell/Site Outage')
    assert evaluate({}, {'lte_rsrp': -90.0, 'lte_sinr': 12.0, 'cells_out_of_service': 3})['rule_key'] != 'cell-outage'
    # Back and forth between two cells, once the radio is not the cause.
    found = evaluate({'service': 'voice', 'result': 'Dropped'}, {'lte_rsrp': -90.0, 'lte_sinr': 12.0, 'ping_pong': 2})
    assert (found['rule_key'], found['category'], found['cause']) == ('ping-pong', 'Mobility LTE', 'Ping-pong handover')


def test_workspaces_with_rules_of_their_own_take_the_new_default_rules_and_catalog_values(client, tmp_path):
    setup_calls(client, tmp_path)
    added = nq_dta_rca.ADDED_RULES[2]
    custom = {'key': 'mine', 'name': 'My rule', 'enabled': True, 'services': [], 'match': 'all',
              'conditions': [{'input': 'failure_text', 'op': 'contains', 'value': 'my failure'}], 'category': 'E2E', 'cause': ''}
    before = [custom, *(rule for rule in nq_dta_rca.default_rules() if rule['key'] not in added)]
    core.repository.set_workspace_state(nq_dta_rca.RULES_STATE_KEY, json.dumps(before))
    catalog = nq.list_root_causes(core.repository)
    catalog['categories'] = [item for item in catalog['categories'] if item['name'] != 'RAN Capacity']
    catalog['causes'] = [item for item in catalog['causes'] if item['name'] not in nq_catalog.DTA_CAUSES]
    with core.repository.connection() as connection:
        nq._write_root_catalog(connection, nq_catalog.normalize_root_catalog(catalog))
    core.repository.set_workspace_state(nq.ANALYSIS_CENTER_V31_STATE_KEY, '')
    core.repository.set_workspace_state(nq.SCHEMA_STATE_KEY, '')
    nq.ensure_nq_tables(core.repository)
    keys = [rule['key'] for rule in nq_dta_rca.load_rules(core.repository)]
    # Its own rule stays first; each new rule follows the default rule before it.
    assert keys[0] == 'mine' and set(added) <= set(keys)
    assert keys[keys.index('subscriber-identity') + 1:keys.index('authentication')] == ['core-resources', 'access-rejected']
    assert keys[keys.index('timeout') + 1:keys.index('timeout') + 3] == ['nr-cell-load', 'cell-load']
    root = nq.list_root_causes(core.repository)
    causes = {item['name']: item for item in root['causes']}
    assert 'RAN Capacity' in {item['name'] for item in root['categories']}
    assert causes['Access rejected (no resources)']['category'] == 'RAN Capacity' and causes['Ping-pong handover']['category'] == 'Mobility LTE'
    log = next(row for row in core.repository.list_logs(limit=50) if row['action'] == 'nq_dta_rca_rules')
    assert json.loads(log['details'])['message'] == 'New default rules of the DT Analyzer RCA added to the rules of the workspace.'
    # Once: the rules a workspace removes afterwards do not come back.
    core.repository.set_workspace_state(nq_dta_rca.RULES_STATE_KEY, json.dumps(before))
    nq.ensure_nq_tables(core.repository)
    assert [rule['key'] for rule in nq_dta_rca.load_rules(core.repository)] == [rule['key'] for rule in before]


def test_the_network_inventory_gives_the_calls_the_network_around_them(client, tmp_path):
    from tests.test_nq_call_map import prepare

    calls = prepare(client, tmp_path)
    # V1 started on a cell whose PCI and channel a cell of the next site has, and its SINR is low: a PCI collision.
    values = detail(client, calls['V1'])['values']
    assert (values['dta_rca_rule'], values['dta_rca_category'], values['dta_rca_cause']) == (
        'PCI collision', 'DL Interference LTE', 'PCI Collision/PCI MOD 3 Collision')
    assert 'PCI collisions around 1 (≥ 1)' in values['dta_rca_evidence']
    assert 'Network Inventory: served from Site 70002 (Vodafone)' in values['dta_rca_evidence']
    # The cells of the call and its PCIs were indexed with it.
    with core.repository.connection() as connection:
        inputs = json.loads(connection.execute(f"SELECT rca_inputs_json FROM {nq.NQ_CALLS_TABLE} WHERE join_id = 'V1'").fetchone()[0])
    assert inputs['cell_pcis'] == '[101]->[206]' and inputs['end_latitude'] == 51.511 and 'LTE E-UTRA 3' in inputs['cell_trace']


def test_the_help_lists_every_default_rule_in_its_order():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / 'help' / 'non-qualified-calls.md').read_text(encoding='utf-8')
    section = text.split('\n### Default rules\n', 1)[1].split('\n### Root domains, categories and causes\n', 1)[0]
    for number, rule in enumerate(nq_dta_rca.default_rules(), 1):
        assert f"| {number} | {rule['name']} |" in section, rule['name']
