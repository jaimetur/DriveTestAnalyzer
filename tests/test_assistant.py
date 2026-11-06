"""AI Assistant: pseudonymized questions answered with the tools of the workspace (ticket #82)."""
from __future__ import annotations

import json
import re
import time

import pytest

import src.DriveTestAnalyzer as core
from src.modules import assistant, assistant_tools, comment_writers as writers, saved_filters, scoring_history
from src.modules.assistant_privacy import Pseudonymizer, workspace_pseudonymizer
from src.modules.repository import Repository
from tests.scoring_fixtures import load_initial_scoring_configuration
from tests.test_scoring_history import _add_cdr


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
    assert done['status'] == 'done' and done['message']['content'] == 'The gap is 76.5 points.'
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
