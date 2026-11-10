"""AI Assistant: pseudonymized questions answered with the tools of the workspace (ticket #82)."""
from __future__ import annotations

import json
import re
import time
from collections import Counter

import pytest

import src.DriveTestAnalyzer as core
from src.modules.assistant import assistant, assistant_query, assistant_tools
from src.modules.nq import nq_prioritization
from src.modules.ppt_designer import comment_writers as writers
from src.modules.scoring import saved_filters, scoring_history
from src.modules.assistant.assistant_privacy import Pseudonymizer, workspace_pseudonymizer
from src.modules.core.repository import Repository
from tests.support.scoring_fixtures import load_initial_scoring_configuration
from tests.cdr.test_cdr_store import copy_everything
from tests.scoring.test_scoring_history import _add_cdr


def _catalogued(repository, ids):
    for dataset_id in ids:
        repository.replace_cdr_catalogue(dataset_id, vendors=['Vodafone UK_Ericsson', 'EE_Nokia'], vendors_only=['Ericsson', 'Nokia'],
                                         regions=['North', 'South'], cities=['London', 'Leeds', 'Glasgow'], campaigns=['2026-Q3'],
                                         operators=['EE', 'Vodafone UK', 'Three UK'], clusters=['C1', 'C2', 'C3'])


@pytest.fixture
def named_repository(tmp_path):
    """A workspace with the names of its CDRs (their catalogues), without scoring them."""
    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'global.db')
    repository.initialize()
    repository.replace_scoring_configuration(load_initial_scoring_configuration())
    ids = [_add_cdr(repository, tmp_path, kind) for kind in ('data', 'voice', 'speech')]
    _catalogued(repository, ids)
    return repository


@pytest.fixture
def scored_repository(tmp_path):
    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'global.db')
    repository.initialize()
    repository.replace_scoring_configuration(load_initial_scoring_configuration())
    ids = [_add_cdr(repository, tmp_path, kind) for kind in ('data', 'voice', 'speech')]
    _catalogued(repository, ids)
    scoring_history.sync_history(repository)
    return repository, ids


def test_names_leave_as_codes_and_come_back_as_names():
    names = Pseudonymizer()
    names.add('operator', 'VF', ['Vodafone UK', 'Vodafone'])
    names.add('operator', 'Three', ['3 UK', '3'])
    names.add('operator', 'EE')
    names.add_vendor('Ericsson (Mixed)')
    names.add('region', 'Vendor A')
    names.add('city', 'London')
    names.add('campaign', 'UK_Q3_NSA_2026')
    question = 'Scoring de Vodafone UK en Vendor A y London vs EE en UK_Q3_NSA_2026: three vendors, ee y 3 operadores'
    masked = names.mask_text(question)
    assert masked == 'Scoring de OP1 en RG1 y CT1 vs OP3 en CP1: three vendors, ee y 3 operadores'
    assert names.leaks(masked) == [] and names.leaks(question) == ['EE', 'London', 'UK_Q3_NSA_2026', 'Vendor A', 'Vodafone UK']
    # Vendor groups keep their words around the code of the vendor, and a JSON document is masked value by value.
    assert names.mask({'vendor': 'Mixed (non-Ericsson)', 'operator': 'VF', 'points': 921.81}) == {
        'vendor': 'Mixed (non-VN1)', 'operator': 'OP1', 'points': 921.81}
    assert names.unmask_text('OP1 suma 921,81 con VN1 y VN1 (Mixed) en RG1; OP99 sigue') == \
        'VF suma 921,81 con Ericsson y Ericsson (Mixed) en Vendor A; OP99 sigue'
    # The codes of a conversation are kept: a name added later takes the next code of its kind.
    kept = Pseudonymizer(json.loads(json.dumps(names.state())))
    assert kept.add('operator', 'O2') == 'OP4' and kept.mask_text('Vodafone') == 'OP1'


def test_every_figure_of_an_answer_comes_from_the_tools():
    allowed = {921.81, 292182.0, 76.393, 58.7, 0.9218}
    tables = [{'title': 'VF', 'columns': ['Vendor', 'Points'], 'rows': [['VN1', '921.81'], ['VN2', '700.5']]}]
    text = 'OP1 suma 921,81 puntos (92,18 %) con 292.182 muestras, el 76,4 % y 58,7 más; 2026-Q3 tiene 3 vendors y 123,45.'
    assert assistant.untraced_figures(text, tables, allowed) == ['123,45', '700.5']


def test_the_scoring_of_the_assistant_is_the_one_of_a_saved_filter(scored_repository):
    repository, ids = scored_repository
    job, _cached = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Vendor'], 'NSA')
    expected = saved_filters.calculate_saved_filter(repository, job['id'])['result']
    context = assistant_tools.ToolContext(repository=repository, workspace_name='UK', username='super')
    result = assistant_tools.scoring(context, {'campaigns': ['latest'], 'nr_mode': 'NSA', 'split_by': ['Operator', 'Vendor'],
                                               'detail': ['environments', 'gap', 'kpis']})
    totals = {(row['operator'], row['vendor']): round(row['total_points'], 2) for row in expected['totals']
              if row['environment'] == 'Combined' and row['category'] == 'Overall'}
    assert {(group['operator'], group['vendor']): group['points'] for group in result['groups']} == totals
    assert result['campaigns'] == ['2026-Q3'] and result['calculated_from'] == 'the Scoring History'
    assert result['gap_reference'] == 'EE' and all(row['operator'] != 'EE' for row in result['gap'])
    # "only" lists some groups without changing their points; an Operator filter is a calculation of its own.
    only = assistant_tools.scoring(context, {'campaigns': ['latest'], 'split_by': ['Operator', 'Vendor'],
                                             'only': {'Operator': ['Vodafone UK']}})
    assert {(group['operator'], group['vendor']): group['points'] for group in only['groups']} == {
        key: value for key, value in totals.items() if key[0] == 'Vodafone UK'}
    assert len(only['groups']) == 2
    with pytest.raises(assistant_tools.ToolError, match='split_by takes'):
        assistant_tools.scoring(context, {'split_by': ['Site']})


class ScriptedEngine:
    """An engine that lists the operators of the workspace and calculates, then answers (once with a made-up figure)."""
    id, label = 'claude', 'Claude'

    def __init__(self):
        self.received: list[str] = []

    def step(self, system, transcript):
        self.received.append(transcript[-1]['content'])
        opening = transcript[0]['content']
        operator = re.search(r'operators of (OP\d+)', opening).group(1)
        if len(self.received) == 1:
            return {'status': 'tools', 'note': 'Calculating', 'tool_calls': [
                {'tool': 'list_values', 'arguments_json': json.dumps({'field': 'Operator'})},
                {'tool': 'list_values', 'arguments_json': json.dumps({'field': 'City'})},
                {'tool': 'calculate', 'arguments_json': json.dumps({'expressions': ['3 * 41.5']})},
                {'tool': 'nope', 'arguments_json': '{}'}], 'answer': '', 'tables': [], 'follow_ups': []}, {'model': 'fake', 'input_tokens': 7}
        results = json.loads(self.received[1].split('\n', 1)[1])
        operators = [item['value'] for item in results[0]['result']['values']]
        cities = [item['value'] for item in results[1]['result']['values']]
        made_up = ' and 123.45 more' if len(self.received) == 2 else ''
        return {'status': 'answer', 'note': '', 'tool_calls': [], 'tables': [
            {'title': f'Cities of {operator}', 'columns': ['City', 'CDRs'], 'rows': [[city, '3'] for city in cities]}],
            'answer': f'**{operator}** is one of {", ".join(operators)}: 124.5 tests{made_up}.', 'follow_ups': [f'And {operator} by Vendor?']}, {
            'model': 'fake', 'output_tokens': 3}


def test_the_assistant_answers_with_the_tools_and_sends_no_name(named_repository):
    repository = named_repository
    conversation = assistant.create_conversation(repository, 'super')
    question = 'Which are the operators of Vodafone UK in London and Leeds?'
    question_id = assistant.add_message(repository, conversation, 'user', question)
    engine = ScriptedEngine()
    steps = []
    answer = assistant.answer_question(engine=engine, repository=repository, workspace_name='UK', username='super',
                                       conversation_id=conversation, question=question, question_id=question_id,
                                       progress=steps.append)
    sent = json.dumps(answer['sent'])
    for name in ('Vodafone', 'London', 'Leeds', 'Glasgow', 'Three UK', 'Ericsson', 'Nokia', 'North', '"EE"'):
        assert name not in sent and name not in ''.join(engine.received), name
    assert answer['content'].startswith('**Vodafone UK** is one of EE, Three UK, Vodafone UK: 124.5 tests.')
    assert answer['follow_ups'] == ['And Vodafone UK by Vendor?'] and answer['warning'] == ''
    assert [row[0] for row in answer['tables'][0]['rows']] == ['Glasgow', 'Leeds', 'London']
    # The made-up figure was sent back to the engine, which answered again without it.
    assert '123.45' in engine.received[2] and len(answer['sent']) == 3
    assert [entry['tool'] for entry in answer['trace']] == ['list_values', 'list_values', 'calculate', 'nope']
    assert answer['trace'][2]['summary'] == '3 * 41.5 = 124.5' and 'Unknown tool' in answer['trace'][3]['error']
    assert 'Checking the figures of the answer' in steps and answer['input_tokens'] == 7
    # The codes of the conversation are kept with it.
    stored = assistant.get_conversation(repository, conversation, 'super')
    assert Pseudonymizer(json.loads(stored['pseudonyms_json'])).name_of('OP1') == workspace_pseudonymizer(repository, 'UK').name_of('OP1')


def test_the_glossary_travels_and_merges_by_uid_then_term(tmp_path):
    source = Repository(tmp_path / 'a.db', global_db_path=tmp_path / 'g.db')
    source.initialize()
    entry = assistant.save_glossary_entry(source, 'super', 'Vendor A', 'Ericsson region')
    assistant.save_glossary_entry(source, 'demo', 'Mixed', 'Two vendors', status='suggested', source='chat')
    document = json.loads(assistant.export_glossary(source))
    assert [item['term'] for item in document['items']] == ['Vendor A']
    target = Repository(tmp_path / 'b.db', global_db_path=tmp_path / 'g.db')
    target.initialize()
    assistant.save_glossary_entry(target, 'admin', 'vendor a', 'old meaning')
    assistant.save_glossary_entry(target, 'admin', 'Local', 'kept')
    assert assistant.import_glossary(target, document, 'admin') == {'added': 0, 'replaced': 1}
    assert {(row['term'], row['meaning']) for row in assistant.list_glossary(target)} == {('Vendor A', 'Ericsson region'), ('Local', 'kept')}
    # A rename on the source reaches the entry with its uid.
    assistant.save_glossary_entry(source, 'super', 'Vendor A (Ericsson)', 'Ericsson region', entry_id=entry['id'])
    third = Repository(tmp_path / 'c.db', global_db_path=tmp_path / 'g.db')
    third.initialize()
    assistant.import_glossary(third, document, 'admin')
    assistant.import_glossary(third, json.loads(assistant.export_glossary(source)), 'admin')
    assert [row['term'] for row in assistant.list_glossary(third)] == ['Vendor A (Ericsson)']
    with pytest.raises(ValueError, match='not an AI Assistant Glossary'):
        assistant.import_glossary(third, {'format': 'other'}, 'admin')


def _login(client, username='super', password='super123'):
    client.cookies.clear()
    assert client.post('/login', data={'username': username, 'password': password}, follow_redirects=False).status_code == 303


def _wait(client, job_id):
    for _ in range(200):
        body = client.get(f'/api/assistant/jobs/{job_id}').json()
        if body['status'] != 'running':
            return body
        time.sleep(0.05)
    raise AssertionError('The question was not answered in time.')


def test_users_ask_in_the_page_and_editors_keep_the_glossary(client, monkeypatch):
    _login(client)
    page = client.get('/assistant')
    assert page.status_code == 200 and 'Ask your workspace in your own words' in page.text
    assert 'No AI engine is enabled' not in page.text  # told by the page script, not the server
    assert client.post('/api/assistant/ask', json={'question': 'Hello?'}).status_code == 400
    writers.save_settings(core.repository, {'enabled': ['claude'], 'default': 'claude'})

    class Answering:
        id, label = 'claude', 'Claude'

        def step(self, system, transcript):
            if not transcript[-1]['content'].startswith('Results'):
                return {'status': 'tools', 'note': 'Looking it up', 'tool_calls': [
                    {'tool': 'calculate', 'arguments_json': '{"expressions": ["940 - 863.5"]}'}], 'answer': '', 'tables': [],
                    'follow_ups': []}, {'model': 'fake'}
            return {'status': 'answer', 'note': '', 'tool_calls': [], 'answer': 'The gap is 76.5 points.', 'tables': [],
                    'follow_ups': []}, {'model': 'fake', 'input_tokens': 5, 'output_tokens': 2}
    monkeypatch.setattr(assistant, 'build_engine', lambda engine_id, _core, _username: Answering())
    asked = client.post('/api/assistant/ask', json={'question': 'What is the gap between 940 and 863.5?'})
    assert asked.status_code == 200, asked.text
    conversation_id = asked.json()['conversation_id']
    done = _wait(client, asked.json()['job']['id'])
    assert done['status'] == 'done' and done['message']['content'] == 'The gap is 76.5 points.', done.get('error')
    assert 'Looking it up' in done['steps']
    message_id = done['message']['id']
    opened = client.get(f'/api/assistant/conversations/{conversation_id}').json()
    assert [message['role'] for message in opened['messages']] == ['user', 'assistant']
    assert opened['conversation']['title'] == 'What is the gap between 940 and 863.5?'
    sent = client.get(f'/api/assistant/messages/{message_id}/sent').json()
    assert sent['sent'][0]['sent'].endswith('What is the gap between 940 and 863.5?') and 'calculate' in sent['system_prompt']
    feedback = client.post(f'/api/assistant/messages/{message_id}/feedback', json={'value': 'down', 'comment': 'Use the GAP'})
    assert feedback.json()['message']['feedback'] == 'down'
    suggested = client.post(f'/api/assistant/messages/{message_id}/suggest', json={'term': 'GAP', 'meaning': 'Points to the reference'})
    assert suggested.status_code == 200
    # Another user sees neither the conversation nor its answers.
    _login(client, 'admin', 'admin123')
    assert client.get(f'/api/assistant/conversations/{conversation_id}').status_code == 404
    assert client.get(f'/api/assistant/messages/{message_id}/sent').status_code == 404
    config = client.get('/workspace-config')
    assert 'AI Assistant Glossary' in config.text and 'Suggestions from the chat' in config.text and 'Points to the reference' in config.text
    entry_id = suggested.json()['entry']['id']
    accepted = client.post('/workspace-config/assistant-glossary/save', data={'entry_id': str(entry_id), 'term': 'GAP',
                                                                              'meaning': 'Points to the reference operator'},
                           follow_redirects=False)
    assert accepted.status_code == 303 and 'Accepted' in accepted.headers['location']
    added = client.post('/workspace-config/assistant-glossary/save', data={'term': 'Vendor A', 'meaning': 'Ericsson region'})
    assert added.status_code == 200
    rows = assistant.list_glossary(core.repository)
    assert {(row['term'], row['status']) for row in rows} == {('GAP', 'active'), ('Vendor A', 'active')}
    vendor_a = next(row['id'] for row in rows if row['term'] == 'Vendor A')
    client.post(f'/workspace-config/assistant-glossary/{vendor_a}/delete')
    assert [row['term'] for row in assistant.list_glossary(core.repository)] == ['GAP']
    _login(client)
    assert client.delete(f'/api/assistant/conversations/{conversation_id}').json() == {'ok': True}
    assert client.get('/api/assistant/conversations').json() == {'conversations': []}
    events = [(row['action'], json.loads(row['details'])) for row in core.repository.list_logs(limit=200)]
    actions = [action for action, _details in events]
    for action in ('assistant_question', 'assistant_answered', 'assistant_feedback', 'assistant_glossary_suggested',
                   'assistant_glossary_saved', 'assistant_glossary_deleted', 'assistant_conversation_deleted'):
        assert action in actions, action
    answered = next(details for action, details in events if action == 'assistant_answered')
    assert answered['tools'][0]['tool'] == 'calculate' and answered['engine'] == 'Claude' and answered['untraced_figures'] == []
    saved = [details for action, details in events if action == 'assistant_glossary_saved']
    assert any(details.get('accepted_suggestion') for details in saved)


def test_the_tables_of_the_assistant_are_in_database_management(client):
    _login(client)
    assistant.ensure_tables(core.repository)
    page = client.get('/super-admin')
    for title in assistant.TABLE_TITLES.values():
        assert title in page.text
    assert core.database_table_type('assistant_glossary') == ('AI Assistant', '#0E7490')


def test_the_glossary_travels_with_its_element_full_workspaces_and_backups(client, tmp_path):
    import zipfile
    from io import BytesIO

    _login(client)
    assistant.save_glossary_entry(core.repository, 'super', 'Vendor A', 'Ericsson region')
    assistant.save_glossary_entry(core.repository, 'super', 'Pending', 'not accepted', status='suggested', source='chat')
    payload = core._assistant_glossary_payload(core.active_workspace)
    assert [item['term'] for item in json.loads(payload)['items']] == ['Vendor A']
    document = json.loads(payload)
    document['items'].append({'uid': 'other', 'term': 'GAP', 'meaning': 'Points to the reference', 'created_by': 'ghost'})
    summary: list[str] = []
    assert core._restore_workspace_assistant_glossary(core.active_workspace, json.dumps(document).encode(), 'admin', summary) == 2
    rows = {row['term']: row for row in assistant.list_glossary(core.repository)}
    # A creator who is not a user here leaves the term to the user who imports it; suggestions stay as they are.
    assert set(rows) == {'Vendor A', 'GAP', 'Pending'} and rows['GAP']['created_by'] == 'admin' and rows['Pending']['status'] == 'suggested'
    assert 'assistant-glossary' in core.WORKSPACE_ELEMENT_EXPORT_TARGETS and core.WORKSPACE_ELEMENT_MODULES['assistant-glossary'] == 'assistant'
    assert core.archive_workspace_components_for_target('assistant-glossary') == ['assistant_glossary']
    assert 'assistant_glossary' in core.full_workspace_archive_components()
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        core._archive_workspace_assistant_glossary(archive, core.active_workspace, 'workspaces/Default')
    names = zipfile.ZipFile(BytesIO(output.getvalue())).namelist()
    assert names == [f'workspaces/Default/{core.ASSISTANT_GLOSSARY_ARCHIVE_NAME}']
    backup = tmp_path / 'backup.zip'
    backup.write_bytes(output.getvalue())
    assert 'assistant_glossary' in core._backup_archive_components(backup)
    assert 'AI Assistant Glossary (from active workspace)' in client.get('/admin').text


# -- ticket #93: lists of NQ Calls, general questions, PPT Designer, Network Insights and the Summary of the scoring -----

def test_users_and_names_inside_identifiers_leave_as_codes():
    names = Pseudonymizer()
    names.add('operator', 'VF', ['Vodafone UK', 'Vodafone'])
    names.add('vendor', 'Nokia')
    assert names.add_user('EUSER01', 'User A') == 'US1' and names.add_user('super', 'Super Admin') == 'US2'
    text = 'Vodafone_Voice_MO and EE_Nokia, assigned to EUSER01 (User A) by the super user of Super Admin'
    masked = names.mask_text(text)
    # A user name that is also a word (super) and the full name of a generic account stay words of the text.
    assert masked == 'OP1_Voice_MO and EE_VN1, assigned to US1 (US1) by the super user of Super Admin'
    assert names.unmask_text(masked) == 'VF_Voice_MO and EE_Nokia, assigned to EUSER01 (EUSER01) by the super user of Super Admin'
    # ...but a value of a user column always takes its code, kept with the conversation.
    kept = Pseudonymizer(json.loads(json.dumps(names.state())))
    assert kept.mask_value('user', 'super') == 'US2' and kept.name_of('US2') == 'super'


def test_the_query_tool_runs_one_select_over_its_own_tables_only():
    import duckdb

    connection = duckdb.connect()
    assert assistant_query.check_sql(
        connection, 'WITH q AS (SELECT * FROM nq_calls) SELECT count(*) FROM q JOIN cdrs USING (dataset_id)') == {'nq_calls', 'cdrs'}
    refused = {
        "COPY (SELECT 1) TO 'x.csv'": 'Only one SELECT', 'SELECT 1; SELECT 2': 'Only one SELECT', 'PRAGMA version': 'Only one SELECT',
        "SELECT * FROM read_csv('/etc/hosts')": 'read_csv cannot be read', "SELECT * FROM '/etc/hosts'": 'There is no table',
        'SELECT * FROM information_schema.tables': 'There is no table', 'SELECT * FROM duckdb_settings()': 'cannot be read',
        "SELECT * FROM nq_calls WHERE join_id IN (SELECT * FROM glob('*'))": 'glob cannot be read',
        'SELECT * FROM _nq_calls_rows': 'There is no table', 'DELETE FROM nq_calls': 'Only one SELECT',
    }
    for sql, error in refused.items():
        with pytest.raises(assistant_tools.ToolError, match=error):
            assistant_query.check_sql(connection, sql)
    hidden = ['Test_Start_Latitude', 'Call_End_Longitude_B', 'IMSI_A', 'IMEI', 'MSISDN_B', 'Dialed_Number', 'Subscriber',
              'Client_IP_IMS_A', 'DNS_Server_IPs', 'Source_IP', 'source_file']
    shown = ['Operator', 'IP_Service_Access_Result', 'IP_Layer_Transferred_Bytes_DL', 'Wagon_Number', 'File_Name', 'RSRP']
    assert [name for name in hidden + shown if assistant_query.hidden_column(name)] == hidden


@pytest.fixture
def nq_workspace(client, tmp_path, monkeypatch):
    """A workspace with NSA and SA CDRs, their Non-Qualified Calls prioritized (with their groups) and their copies."""
    from tests.nq.test_nq_prioritization import prepare

    monkeypatch.setattr(core, 'submit_background_task', lambda callback, *args: callback(*args))
    prepared = prepare(client, tmp_path, nq_prioritization.DEFAULT_STRATEGY)
    copy_everything()
    return prepared


class QueryEngine:
    """An engine that lists the JOIN_IDs of the calls in a Cluster and a Time-Window issue and shows the whole list."""
    id, label = 'claude', 'Claude'

    def __init__(self, sql):
        self.sql, self.received = sql, []

    def step(self, system, transcript):
        self.received.append(transcript[-1]['content'])
        if len(self.received) == 1:
            return {'status': 'tools', 'note': 'Listing', 'tool_calls': [
                {'tool': 'query', 'arguments_json': json.dumps({'sql': self.sql, 'max_rows': 2})}],
                'answer': '', 'tables': [], 'follow_ups': []}, {'model': 'fake'}
        result = json.loads(self.received[1].split('\n', 1)[1])[0]['result']
        return {'status': 'answer', 'note': '', 'tool_calls': [], 'follow_ups': [],
                'answer': f'There are {result["row_count"]} calls.', 'tables': [
                    {'title': 'Calls of OP1', 'columns': [], 'rows': [], 'result': result['result_id']}]}, {'model': 'fake'}


def test_the_query_tool_lists_the_nq_calls_of_their_groups_and_reads_the_cdr_rows(nq_workspace):
    from tests.nq.test_nq_prioritization import priority_rows

    context = assistant_tools.ToolContext(repository=core.repository, workspace_name='UK', username='super')
    try:
        expected = {str(row['join_id']): row for row in priority_rows().values()
                    if row['repeat_key'] and (row['repeat_size'] or 0) >= 2 and row['consecutive_key'] and (row['consecutive_size'] or 0) >= 2}
        assert expected, 'The workspace has calls in a Cluster and a Time-Window issue.'
        sql = ('SELECT join_id, nq_cluster_id, nq_cluster_calls, time_window_id, time_window_calls, hotspot_id FROM nq_calls '
               'WHERE nq_cluster_calls >= 2 AND time_window_calls >= 2 ORDER BY join_id')
        found = assistant_query.query(context, {'sql': sql, 'max_rows': 3})
        assert found['result_id'] == 'R1' and found['row_count'] == len(expected) and len(found['rows']) == min(3, len(expected))
        stored = context.cache['query_results']['R1']['rows']
        assert [row[0] for row in stored] == sorted(expected)
        for join_id, cluster_id, cluster_calls, window_id, window_calls, _hotspot in stored:
            row = expected[join_id]
            assert (cluster_id, cluster_calls) == (nq_prioritization.group_id('C', row['repeat_key']), row['repeat_size'])
            assert (window_id, window_calls) == (nq_prioritization.group_id('T', row['consecutive_key']), row['consecutive_size'])
        # The rows of the CDRs: the operators as the Operator Maps name them, without coordinates.
        frames = [rows for kinds in nq_workspace['frames'].values() for kind, rows in kinds.items() if kind == 'data']
        counts = Counter(assistant_tools._canonical_operator(context, value) for rows in frames for value in rows['Operator'])
        tests = assistant_query.query(context, {'sql': 'SELECT Operator, count(*) AS tests FROM cdr_data GROUP BY 1 ORDER BY 1'})
        assert dict(tests['rows']) == dict(counts)
        assert assistant_query.table_columns(context, {'table': 'cdr_data', 'search': 'latitude longitude'})['column_count'] == 0
        assert assistant_query.table_columns(context, {'table': 'nq_calls', 'search': 'time_window'})['columns'][0] == {
            'column': 'time_window_id', 'type': 'VARCHAR', 'description': assistant_query.NQ_COLUMNS[
                [name for name, _type, _text in assistant_query.NQ_COLUMNS].index('time_window_id')][2]}
    finally:
        context.close()
    # An answer shows the whole result, with its real values, without the engine copying it.
    conversation = assistant.create_conversation(core.repository, 'super')
    question = 'Which calls are in a Cluster and a Time-Window issue?'
    question_id = assistant.add_message(core.repository, conversation, 'user', question)
    engine = QueryEngine(sql)
    answer = assistant.answer_question(engine=engine, repository=core.repository, workspace_name='UK', username='super',
                                       conversation_id=conversation, question=question, question_id=question_id)
    table = answer['tables'][0]
    assert table['result'] == 'R1' and table['columns'][0] == 'join_id' and [row[0] for row in table['rows']] == sorted(expected)
    assert answer['content'] == f'There are {len(expected)} calls.' and answer['warning'] == ''
    assert len(json.loads(engine.received[1].split('\n', 1)[1])[0]['result']['rows']) == 2


def test_the_summary_of_the_scoring_comments_globally_on_the_operators_asked(scored_repository):
    repository, _ids = scored_repository
    context = assistant_tools.ToolContext(repository=repository, workspace_name='UK', username='super')
    result = assistant_tools.scoring(context, {'campaigns': ['latest'], 'split_by': ['Operator'], 'detail': ['insights'],
                                               'only': {'Operator': ['Vodafone UK']}})
    insights = result['insights']
    assert {'standings', 'gap_parts', 'levers', 'points_at_stake', 'act_plans'} <= set(insights)
    assert {entry['operator'] for item in insights['standings'] for entry in item['operators']} == {'Vodafone UK'}
    assert {item['operator'] for item in insights['act_plans']} == {'Vodafone UK'}
    assert all('color' not in item for item in insights['act_plans'])


def _services(user='super', role='super-admin'):
    from src.modules.core.auth import SessionUser

    return assistant.module_services(core, SessionUser(username=user, role=role), core.repository, lambda: False, lambda _step: None)


def test_the_assistant_reads_the_analysis_of_network_insights(nq_workspace):
    services = _services()
    assert set(services) == {'network_insights', 'design_outline', 'design_charts'}
    context = assistant_tools.ToolContext(repository=core.repository, workspace_name='UK', username='super', services=services)
    network = assistant_tools.run_tool(context, 'network_insights', {'campaigns': ['latest'], 'technology': 'lte',
                                                                     'group': ['operator'], 'parts': ['rf', 'findings']})
    assert network['selection']['campaigns'] and network['cdrs'] >= 1 and 'rf' in network and 'findings' in network
    assert 'maps' not in json.dumps(network) and set(network['parts_available']) == {
        'spectrum', 'bandwidth', 'interactivity', 'nr_bands', 'serving'}
    with pytest.raises(assistant_tools.ToolError, match='group takes'):
        assistant_tools.run_tool(context, 'network_insights', {'group': ['site']})


def test_the_assistant_reads_the_charts_of_a_design_as_its_auto_comments(client):
    from tests.ppt_designer.test_design_comments import prepare_rates_design

    body = prepare_rates_design(client)
    slide = body['slides'][0]
    generated = client.post('/api/ppt-designer/rates/comments/generate', json={
        'token': body['token'], 'slide': slide['number'],
        'charts': [{'index': chart['index'], 'hidden': [], 'shown': []} for chart in slide['charts']]}).json()
    context = assistant_tools.ToolContext(repository=core.repository, workspace_name='UK', username='super', services=_services())
    designs = assistant_tools.run_tool(context, 'ppt_designs', {})['designs']
    assert 'Rates' in [design['name'] for design in designs]
    outline = assistant_tools.run_tool(context, 'ppt_designs', {'design': 'rates'})
    assert [(item['slide'], [chart['title'] for chart in item['charts']]) for item in outline['slides']] == [
        (1, ['Rate CDF', 'Rate mean']), (2, ['Results'])]
    read = assistant_tools.run_tool(context, 'ppt_design_charts', {'design': 'Rates', 'slides': [slide['number']]})
    facts = read['slides'][0]
    assert [chart['title'] for chart in facts['charts']] == ['Rate CDF', 'Rate mean']
    # Each chart has its id: the answer draws it with the model of its viewer, which the engine never receives.
    assert [chart['chart_id'] for chart in facts['charts']] == ['G1', 'G2'] and 'chart_models' not in read
    model = context.cache['design_charts']['G2']['model']
    drawn = assistant.charts_module.build_chart({'source': 'G2', 'title': ''}, context.cache, [], assistant.charts_module.Colours({}))
    assert drawn['model'] == model and model['type'] in {'mean_bar', 'hbar', 'dot'} and drawn['origin'] == 'Rates · slide 1'
    assistant_tools.run_tool(context, 'ppt_design_charts', {'design': 'rates', 'slides': [slide['number']]})
    assert list(context.cache['design_charts']) == ['G1', 'G2']
    assert facts['rules_comments'] == [item['text'] for item in generated['suggestions']]
    assert read['focus_operators'] == ['A'] and {record['labels'].get('Operator') for chart in facts['charts']
                                                 for record in chart['records']} == {'A', 'B'}
    with pytest.raises(assistant_tools.ToolError, match='at most 4'):
        assistant_tools.run_tool(context, 'ppt_design_charts', {'design': 'rates', 'slides': [1, 2, 3, 4, 5]})
    with pytest.raises(assistant_tools.ToolError, match='There is no Design'):
        assistant_tools.run_tool(context, 'ppt_designs', {'design': 'Missing'})
    # A user whose Modules Profile has neither module gets neither tool.
    core.user_has_feature, before = (lambda _user, feature: feature not in {'ppt-designer', 'network-insights'}), core.user_has_feature
    try:
        assert _services('demo', 'user-editor') == {}
    finally:
        core.user_has_feature = before


class ChartEngine:
    """An engine that calculates the scoring, then draws it (once with a source that does not exist)."""
    id, label = 'claude', 'Claude'

    def __init__(self):
        self.received: list[str] = []

    def step(self, system, transcript):
        self.received.append(transcript[-1]['content'])
        if len(self.received) == 1:
            return {'status': 'tools', 'note': 'Calculating', 'tool_calls': [
                {'tool': 'scoring', 'arguments_json': json.dumps({'campaigns': ['latest'], 'split_by': ['Operator']})}],
                'answer': '', 'tables': [], 'charts': [], 'follow_ups': []}, {'model': 'fake'}
        result = json.loads(self.received[1].split('\n', 1)[1])[0]['result']
        rows = [[group['operator'], str(group['points'])] for group in result['groups']]
        charts = [{'title': 'Points of each operator', 'source': result['scoring_id'], 'view': 'points', 'type': '', 'x': [],
                   'y': [], 'series': ''},
                  {'title': '', 'source': 'T1', 'view': '', 'type': 'hbar', 'x': ['Operator'], 'y': ['Points'], 'series': ''}]
        if len(self.received) == 2:
            charts.append({'title': 'Wrong', 'source': 'S9', 'view': 'points', 'type': '', 'x': [], 'y': [], 'series': ''})
        return {'status': 'answer', 'note': '', 'tool_calls': [], 'follow_ups': [], 'charts': charts,
                'answer': 'The scoring of each operator.', 'tables': [
                    {'title': 'Scoring', 'columns': ['Operator', 'Points'], 'rows': rows, 'result': ''}]}, {'model': 'fake'}


def test_the_charts_of_an_answer_draw_the_data_of_the_tools_with_the_real_names(scored_repository):
    repository, _ids = scored_repository
    conversation = assistant.create_conversation(repository, 'super')
    question = 'Draw the scoring of each operator of the latest campaign'
    question_id = assistant.add_message(repository, conversation, 'user', question)
    engine = ChartEngine()
    steps = []
    answer = assistant.answer_question(engine=engine, repository=repository, workspace_name='UK', username='super',
                                       conversation_id=conversation, question=question, question_id=question_id,
                                       progress=steps.append)
    # The chart that cannot be drawn was sent back to the engine, which answered again without it.
    assert 'S9' in engine.received[2] and 'Checking the charts of the answer' in steps and answer['warning'] == ''
    context = assistant_tools.ToolContext(repository=repository, workspace_name='UK', username='super')
    expected = {group['operator']: group['points'] for group in assistant_tools.scoring(context, {'split_by': ['Operator']})['groups']}
    points, table = answer['charts']
    assert (points['source'], points['model']['type'], points['title']) == ('S1', 'mean_bar', 'Points of each operator')
    assert {bar['key'][0]: bar['value'] for bar in points['model']['bars']} == expected
    assert table['model']['type'] == 'hbar' and {row[0]: cells[0] for row, cells in zip(
        table['model']['row_keys'], table['model']['cells'], strict=True)} == expected
    # The engine never received a name nor a chart; the charts are kept with the answer.
    sent = json.dumps(answer['sent'])
    assert all(name not in sent for name in expected) and 'mean_bar' not in ''.join(engine.received)
    message_id = assistant.add_message(repository, conversation, 'assistant', answer['content'],
                                       **{key: value for key, value in answer.items() if key != 'content'})
    stored = assistant.get_message(repository, message_id, 'super')
    assert [chart['model']['type'] for chart in stored['charts']] == ['mean_bar', 'hbar']


def test_the_charts_of_tables_and_query_results_take_their_columns():
    from src.modules.assistant import assistant_charts as charts

    colours = charts.Colours(charts.operator_colours([{'canonical': 'EE', 'color': '#00a0a0', 'aliases': ['EE UK']},
                                                      {'canonical': 'VF', 'color': '#e60000'}]))
    columns = ['Campaign', 'Operator', 'Points']
    rows = [['2026-Q2', 'EE', '930.1'], ['2026-Q2', 'VF', '1.234,5'], ['2026-Q3', 'EE UK', '938.45'], ['2026-Q3', 'VF', '863,11']]
    line = charts.table_chart(columns, rows, {'type': 'line', 'x': ['Campaign'], 'y': ['Points'], 'series': 'Operator'}, '', colours)
    assert line['type'] == 'lines' and line['x_keys'] == [['2026-Q2'], ['2026-Q3']]
    assert [(item['name'], item['values'], item['colour']) for item in line['series']] == [
        ('EE', [930.1, None], '#00A0A0'), ('VF', [1234.5, 863.11], '#E60000'), ('EE UK', [None, 938.45], '#00A0A0')]
    bars = charts.table_chart(columns, rows, {'type': 'bar', 'x': ['Campaign', 'Operator'], 'y': ['Points'], 'series': ''}, 'T', colours)
    assert [bar['key'] for bar in bars['bars']][:2] == [['2026-Q2', 'EE'], ['2026-Q2', 'VF']]
    assert [bar['colour'] for bar in bars['bars']] == ['#00A0A0', '#E60000', '#00A0A0', '#E60000']
    pie = charts.table_chart(['Category', 'Calls'], [['Drop', '12'], ['Setup', '4'], ['None', '0']],
                             {'type': 'pie', 'x': [], 'y': [], 'series': ''}, '', colours)
    assert [(item['name'], item['share']) for item in pie['pies'][0]['slices']] == [('Drop', .75), ('Setup', .25)]
    with pytest.raises(charts.ChartError, match='"Rate" is not a column'):
        charts.table_chart(columns, rows, {'type': 'bar', 'x': ['Campaign'], 'y': ['Rate'], 'series': ''}, '', colours)
    with pytest.raises(charts.ChartError, match='type is one of'):
        charts.table_chart(columns, rows, {'type': 'radar', 'x': [], 'y': [], 'series': ''}, '', colours)
    built, problems = charts.build_charts([{'source': 'R1', 'type': 'bar', 'x': [], 'y': [], 'series': '', 'title': '', 'view': ''},
                                           {'source': 'X1', 'type': '', 'x': [], 'y': [], 'series': '', 'title': '', 'view': ''}],
                                          {'query_results': {'R1': {'columns': ['operator', 'calls'], 'rows': [['VF', 3], ['EE', 5]]}}},
                                          [], {})
    assert [bar['value'] for bar in built[0]['model']['bars']] == [3, 5] and problems == ['X1: source "X1" is not S1, G1, R1, T1 or P1.']


def test_the_scoring_charts_follow_the_views_of_the_module():
    from src.modules.assistant import assistant_charts as charts

    colours = charts.Colours(charts.operator_colours([{'canonical': 'VF', 'color': '#e60000', 'position': 1},
                                                      {'canonical': 'EE', 'color': '#00a0a0', 'position': 0}]))

    def total(campaign, operator, points, environment='Combined', category='Overall'):
        return {'campaign': campaign, 'operator': operator, 'environment': environment, 'category': category,
                'total_points': points, 'max_points': 1000}

    result = {
        'totals': [total('UK_Q3_NSA_2026', 'VF', 863.11), total('UK_Q3_NSA_2026', 'EE', 938.45),
                   total('UK_Q2_NSA_2026', 'VF', 850.0), total('UK_Q2_NSA_2026', 'EE', 921.81),
                   total('UK_Q3_NSA_2026', 'VF', 500.0, 'DriveCity'), total('UK_Q3_NSA_2026', 'EE', 520.0, 'DriveCity')],
        'gap_totals': [{'campaign': 'UK_Q3_NSA_2026', 'operator': 'VF', 'environment': 'Combined', 'category': 'Overall',
                        'gap_points': -75.34}],
        'scoring': [{'campaign': 'UK_Q3_NSA_2026', 'operator': 'VF', 'kpi': kpi, 'max_points': 100, 'weighted_points': points}
                    for kpi, points in (('Call Success', 60), ('Browsing', 90), ('Video', 75))],
    }
    stored = {'result': result, 'selection': {'campaigns': ['UK_Q3_NSA_2026', 'UK_Q2_NSA_2026'], 'baseline_operator': 'EE'},
              'only': {}}
    trend = charts.scoring_chart(stored, 'trend', '', '', colours)
    assert trend['x_keys'] == [['UK_Q2_NSA_2026'], ['UK_Q3_NSA_2026']]
    assert [(line['name'], line['values'], line['colour']) for line in trend['series']] == [
        ('EE', [921.81, 938.45], '#00A0A0'), ('VF', [850.0, 863.11], '#E60000')]
    points = charts.scoring_chart(stored, 'points', '', '', colours)
    # The campaigns oldest first, the operators in the order of the Operator Maps, the axis up to the methodology points.
    assert [bar['key'] for bar in points['bars']] == [['UK_Q2_NSA_2026', 'EE'], ['UK_Q2_NSA_2026', 'VF'],
                                                      ['UK_Q3_NSA_2026', 'EE'], ['UK_Q3_NSA_2026', 'VF']]
    assert points['domain']['y'] == [0.0, 1000.0]
    environments = charts.scoring_chart(stored, 'environments', '', '', colours)
    assert [bar['key'] for bar in environments['bars']] == [['DriveCity', 'UK_Q3_NSA_2026', 'EE'], ['DriveCity', 'UK_Q3_NSA_2026', 'VF']]
    gap = charts.scoring_chart(stored, 'gap', 'hbar', '', colours)
    assert gap['type'] == 'hbar' and gap['cells'] == [[-75.34]] and gap['title'] == 'GAP to EE'
    kpis = charts.scoring_chart({**stored, 'only': {'Operator': ['VF']}}, 'kpis', '', '', colours)
    assert kpis['row_keys'] == [['Call Success'], ['Video'], ['Browsing']] and kpis['cells'] == [[40.0], [25.0], [10.0]]
    # The campaigns of the data are shown as the page shows them (the Campaign Maps), before the styles name them.
    spec = {'source': 'S1', 'view': 'trend', 'title': '', 'type': '', 'styles': [{'series': '', 'colour': '', 'width': 6, 'dash': ''}]}
    built, problems = charts.build_charts([spec], {'scoring_results': {'S1': stored}}, [], {},
                                          relabel=lambda document: json.loads(json.dumps(document).replace('UK_Q2_NSA_2026', '26-Q2-NSA')))
    assert problems == [] and built[0]['model']['x_keys'][0] == ['26-Q2-NSA'] and built[0]['model']['series'][0]['width'] == 6
    with pytest.raises(charts.ChartError, match='two or more campaigns'):
        charts.scoring_chart({**stored, 'result': {'totals': result['totals'][:2]}}, 'trend', '', '', colours)


def test_the_charts_take_the_styles_asked_and_keep_one_colour_per_operator():
    from src.modules.assistant import assistant_charts as charts

    colours = charts.Colours(charts.operator_colours([{'canonical': 'EE', 'color': '#00a0a0'}, {'canonical': 'VF', 'color': '#e60000'}]))
    rows = [[threshold, f'{operator} {campaign}', value] for threshold, values in (('20', (10, 12, 8, 9)), ('40', (40, 45, 30, 33)))
            for (operator, campaign), value in zip((('EE', 'UK_Q2_2026'), ('EE', 'UK_Q3_NSA_2026'), ('VF', 'UK_Q2_2026'),
                                                    ('VF', 'UK_Q3_NSA_2026')), values, strict=True)]
    spec = {'type': 'line', 'x': ['Mbps'], 'y': ['CDF'], 'series': 'Series'}
    model = charts.table_chart(['Mbps', 'Series', 'CDF'], rows, spec, '', colours)
    # Each operator keeps its colour; its latest campaign is solid, the earlier one dashed.
    assert [(item['name'], item['colour'], item['dash']) for item in model['series']] == [
        ('EE UK_Q2_2026', '#00A0A0', [10, 6]), ('EE UK_Q3_NSA_2026', '#00A0A0', []),
        ('VF UK_Q2_2026', '#E60000', [10, 6]), ('VF UK_Q3_NSA_2026', '#E60000', [])]
    assert model['value_title'] == 'CDF'
    styled = charts.apply_styles(model, {'styles': [{'series': 'Q3_NSA', 'colour': '', 'width': 8, 'dash': ''},
                                                    {'series': 'VF UK_Q2_2026', 'colour': 'blue', 'width': 0, 'dash': 'dotted'}],
                                         'legend': 'bottom', 'x_title': 'DL throughput (Mbps)', 'y_title': 'Share of tests (%)'})
    assert [(item['width'], item['colour'], item['dash']) for item in styled['series']] == [
        (4, '#00A0A0', [10, 6]), (8, '#00A0A0', []), (4, '#1F5FBF', [2, 5]), (8, '#E60000', [])]
    legend = {item['label']: item for item in styled['legend']['items']}
    assert legend['EE UK_Q3_NSA_2026']['width'] == 8 and legend['VF UK_Q2_2026']['colour'] == '#1F5FBF'
    assert styled['legend']['position'] == 'bottom' and styled['value_title'] == 'Share of tests (%)'
    assert styled['category_title'] == 'DL throughput (Mbps)' and 'format_overrides' not in styled
    with pytest.raises(charts.ChartError, match='No series of the chart is named "O2"'):
        charts.apply_styles(model, {'styles': [{'series': 'O2', 'colour': '', 'width': 6, 'dash': ''}]})
    with pytest.raises(charts.ChartError, match='colour "sky" is not'):
        charts.apply_styles(model, {'styles': [{'series': '', 'colour': 'sky', 'width': 0, 'dash': ''}]})
    bars = charts.table_chart(['Operator', 'Points'], [['EE', '938.45'], ['VF', '863.11']], {'type': 'bar', 'x': [], 'y': []}, '', colours)
    with pytest.raises(charts.ChartError, match='no title on its x axis'):
        charts.apply_styles(bars, {'x_title': 'Operators'})
    design = charts.apply_styles({'type': 'cdf', 'series': []}, {'x_title': 'Mbps'})
    assert design['format_overrides'] == {'axes': {'x': {'title': 'Mbps'}}}
    assert [bar['colour'] for bar in charts.apply_styles(bars, {'styles': [{'series': 'VF', 'colour': '#123456', 'width': 0,
                                                                            'dash': ''}]})['bars']] == ['#00A0A0', '#123456']


class RestyleEngine:
    """An engine that draws a chart of an earlier answer again, thicker, without calling any tool."""
    id, label = 'claude', 'Claude'

    def __init__(self):
        self.received: list[str] = []

    def step(self, system, transcript):
        self.received.append(transcript[0]['content'])
        return {'status': 'answer', 'note': '', 'tool_calls': [], 'tables': [], 'follow_ups': [],
                'answer': 'The same chart, its latest campaign thicker.',
                'charts': [{'title': '', 'source': 'P2', 'view': '', 'type': '', 'x': [], 'y': [], 'series': '', 'legend': '',
                            'x_title': '', 'y_title': '', 'styles': [{'series': 'Q3', 'colour': '', 'width': 7, 'dash': ''}]}]}, {
            'model': 'fake'}


def test_a_chart_of_an_earlier_answer_is_drawn_again_with_another_style(named_repository):
    from src.modules.assistant import assistant_charts as charts

    repository = named_repository
    conversation = assistant.create_conversation(repository, 'super')
    assistant.add_message(repository, conversation, 'user', 'Draw the trend')
    colours = charts.Colours({})
    line = charts.line_model('Trend', 'Points', [['Q2'], ['Q3']], [('Q2 line', [1.0, 2.0], '#111111'),
                                                                   ('Q3 line', [2.0, 3.0], '#222222')], ['Campaign'])
    bars = charts.bar_model('Bars', 'Points', [(['A'], 1.0, colours.of('A'), 'A')], ['Operator'])
    assistant.add_message(repository, conversation, 'assistant', 'Two charts.', charts=[
        {'title': 'Bars', 'source': 'S1', 'view': 'points', 'type': '', 'model': bars},
        {'title': 'Trend', 'source': 'R1', 'view': '', 'type': 'line', 'model': line}])
    question = 'Make the lines of the latest campaign thicker'
    question_id = assistant.add_message(repository, conversation, 'user', question)
    engine = RestyleEngine()
    answer = assistant.answer_question(engine=engine, repository=repository, workspace_name='UK', username='super',
                                       conversation_id=conversation, question=question, question_id=question_id)
    assert 'P1 "Bars" (mean_bar); P2 "Trend" (lines)' in engine.received[0]
    chart = answer['charts'][0]
    assert chart['source'] == 'P2' and [item['width'] for item in chart['model']['series']] == [4, 7]
    assert chart['style'] == {'styles': [{'series': 'Q3', 'colour': '', 'width': 7, 'dash': ''}]}
    assert answer['warning'] == '' and answer['trace'] == []


def test_the_campaigns_are_shown_with_their_label_of_the_campaign_maps(named_repository):
    from src.modules.cdr.column_names import format_campaign
    from src.modules.mapping.campaign_maps import load_campaign_map, save_campaign_map

    repository = named_repository
    save_campaign_map(repository, {**load_campaign_map(repository), 'exceptions': [
        {'label': 'Summer 2026', 'sources': ['2026-Q3']}]})
    assert format_campaign('2026-Q3', load_campaign_map(repository)) == 'Summer 2026'
    names = workspace_pseudonymizer(repository, 'UK')
    code = names.mask_text('2026-Q3')
    # The label is another spelling of the campaign; the tools still receive the name of the data.
    assert names.mask_text('the campaign Summer 2026') == f'the campaign {code}' and names.unmask_text(code) == '2026-Q3'
    assert names.show_text(f'{code} leads') == 'Summer 2026 leads'
    # The values of the data are shown with the label too, also inside a series named by the query.
    table = assistant._shown_table({'title': f'Calls of {code}', 'columns': ['series', 'campaign', 'calls'], 'result': 'R1',
                                    'rows': [['EE - 2026-Q3', '2026-Q3', '3']]}, names)
    assert table['title'] == 'Calls of Summer 2026' and table['rows'] == [['EE - Summer 2026', 'Summer 2026', '3']]
    # A quarter written in a label is sent as it is, never taken for the campaign.
    other = Pseudonymizer()
    other.add_campaign('UK_Q4_2026', '2026-Q4')
    assert other.mask_text('UK_Q4_2026 in 2026-Q4') == 'CP1 in 2026-Q4' and other.show_text('CP1') == '2026-Q4'
