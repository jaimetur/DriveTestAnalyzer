"""Fields that do not apply to a call (ticket #186) and the emails to the reviewers of the NQ calls (ticket #187)."""
import json
from datetime import datetime, timedelta

import pytest

import src.DriveTestAnalyzer as core
from src.modules.core import email_delivery, notifications
from src.modules.nq import non_qualified_calls as nq
from src.modules.nq import nq_call_emails, nq_catalog, nq_prioritization
from tests.nq.test_nq_prioritization import prepare, priority_rows

FLOW = 'https://prod-00.westeurope.logic.azure.com/workflows/abc/triggers/manual/paths/invoke?sig=secret-signature'


@pytest.fixture
def prioritized(client, tmp_path):
    return prepare(client, tmp_path, nq_prioritization.CUSTOM)


class FlowResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def flow(monkeypatch):
    received = []

    def urlopen(request, timeout=None):
        received.append(json.loads(request.data.decode()))
        return FlowResponse()

    monkeypatch.setattr(email_delivery.urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(notifications, 'submit', lambda task: task())
    return received


def call_of(service: str) -> str:
    rows = priority_rows()
    return next(key for key, row in rows.items() if str(row['service']).lower() == service)


def detail(client, key):
    return client.get(f'/api/non-qualified-calls/calls/{key}').json()['call']


def test_fields_that_do_not_apply_to_a_call_count_as_filled(prioritized):
    client = prioritized['client']
    fields = {field['key']: field for field in nq.list_fields(core.repository)}
    # The default conditions: the party and second vendor of a call between two UEs, the date and year of a planned measure.
    assert fields['failed_party']['applies_when'] == [{'field': '@service', 'op': 'in', 'values': ['Voice', 'Speech']}]
    assert fields['planned_date']['applies_when'] == [{'field': 'planned_status', 'op': 'in', 'values': ['Planned']}]
    data, voice = call_of('data'), call_of('voice')
    assert {'failed_party', 'vendor_2_when_failure', 'planned_date', 'planned_fy'} <= set(detail(client, data)['not_applicable'])
    assert 'failed_party' not in detail(client, voice)['not_applicable']
    # A planned measure needs its date and fiscal year.
    call = detail(client, data)
    updated = client.patch(f'/api/non-qualified-calls/calls/{data}', json={'changes': {'fields': {'planned_status': 'Planned'}},
                                                                          'version': call['version']})
    assert updated.status_code == 200, updated.text
    assert 'planned_date' not in updated.json()['call']['not_applicable']
    # N/A is a value of every type of field (a date here) and counts as filled.
    updated = client.patch(f'/api/non-qualified-calls/calls/{data}', json={
        'changes': {'fields': {'planned_date': 'n/a'}}, 'version': updated.json()['call']['version']})
    assert updated.status_code == 200, updated.text
    assert updated.json()['call']['fields']['planned_date'] == 'N/A'
    state = nq.analyst_fill_states(core.repository, [data])[data]
    filled = {label: value for _section, label, value in state['filled']}
    assert filled['Planned Date'] == 'N/A' and filled['Failed Party (MOC/MTC) (UE1/UE2)'] == 'N/A (Auto)'
    assert 'Planned Date' not in [label for _section, label in state['missing']]


def test_the_conditions_of_a_field_travel_with_the_catalog_and_follow_its_values():
    conditions = [{'field': 'planned_status', 'op': 'in', 'values': ['Planned']}, {'field': '@service', 'op': 'not_in', 'values': ['Data']},
                  {'field': 'notice_to_vf3', 'op': 'not_empty', 'values': []}]
    text = nq_catalog.conditions_text(conditions)
    assert text == 'planned_status in Planned; @service not_in Data; notice_to_vf3 not_empty'
    assert nq_catalog.conditions_from_text(text) == conditions
    # A value renamed in its list follows; a field removed takes its conditions on it away.
    before = [dict(field) for field in nq_catalog.DEFAULT_FIELDS]
    after = [dict(field, options=[dict(option, name='Scheduled', previous='Planned') if option['name'] == 'Planned' else option
                                  for option in field['options']]) if field['key'] == 'planned_status' else dict(field)
             for field in nq_catalog.DEFAULT_FIELDS]
    nq_catalog.applies_when_after_field_changes(after, before)
    assert next(field for field in after if field['key'] == 'planned_date')['applies_when'][0]['values'] == ['Scheduled']
    without = [dict(field) for field in nq_catalog.DEFAULT_FIELDS if field['key'] != 'planned_status']
    nq_catalog.applies_when_after_field_changes(without, before)
    assert next(field for field in without if field['key'] == 'planned_date')['applies_when'] == []


def test_the_reviewer_is_emailed_when_a_call_changes_a_status(prioritized, flow):
    client = prioritized['client']
    email_delivery.save_email_delivery_settings(core.repository, {
        'transport': 'webhook', 'webhook_url': FLOW, 'port': 587, 'from_address': 'admin@example.com', 'max_attachments_mb': 20,
        'link_days': 7, email_delivery.EVERY_NQ_CALL_KEY: ['super'],
    }, keep_password=False, keep_webhook_url=False)
    core.repository.set_user_email('super', 'super@example.com')
    # At once, and of its own changes too (ticket #194: a daily summary of the changes of others by default).
    core.repository.set_email_preferences('super', nq_frequency='immediate', nq_own_changes=True)
    key = call_of('data')
    call = detail(client, key)
    # Choosing the reviewer is a key field too (ticket #199): one email.
    updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={'changes': {'reviewer': 'super'}, 'version': call['version']})
    assert updated.status_code == 200, updated.text
    assert len(flow) == 1 and 'Reviewer' in json.dumps(flow[0])
    # A field that is not a key one emails nobody.
    del flow[:]
    updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={
        'changes': {'fields': {'analysis_status': 'Finished'}}, 'version': updated.json()['call']['version']})
    assert updated.status_code == 200, updated.text
    # One email (the reviewer is also among the users of every change), with what changed and the fields still empty.
    assert len(flow) == 1
    sent = json.dumps(flow[0])
    assert 'Changed' in sent and 'Analysis Status' in sent and 'Finished' in sent and 'Still empty' in sent
    assert 'NQ Call ' in flow[0].get('subject', sent)
    assert '/non-qualified-calls#call=' in sent
    assert any(json.loads(row['details']).get('kind') == 'nq_call' for row in core.repository.list_logs() if row['action'] == 'email_sent')
    # Switched off, nothing is sent.
    email_delivery.save_email_delivery_settings(core.repository, {
        'transport': 'webhook', 'port': 587, 'from_address': 'admin@example.com', 'max_attachments_mb': 20, 'link_days': 7,
        'notify_nq_calls': False}, keep_password=True)
    updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={
        'changes': {'fields': {'analysis_status': 'Ongoing'}}, 'version': updated.json()['call']['version']})
    assert updated.status_code == 200 and len(flow) == 1


def test_a_call_is_told_once_when_all_its_fields_are_filled():
    state = {'call_key': 'k1', 'join_id': 'J1', 'operator': 'EE', 'campaign': 'C1', 'service': 'data', 'start_time': '2026-11-11T10:00:00',
             'status': 'Analysis Finished', 'priority': 'P2', 'team': 'RAN', 'analyst': 'EAAAAAA', 'reviewer': 'EBBBBBB',
             'root_category': 'Coverage', 'root_cause': 'Weak', 'filled': [('Analysis', 'Findings', 'Overshooting')], 'missing': [],
             'complete': True}
    events = nq_call_emails.call_events({'k1': {'complete': False}}, {'k1': state}, {'k1': {'field:findings': ['', 'Overshooting']}},
                                        {}, {'status'})
    assert events['k1']['completed'] and events['k1']['changes'] == []
    # Already complete before: nothing to tell.
    assert nq_call_emails.call_events({'k1': {'complete': True}}, {'k1': state}, {'k1': {'field:findings': ['', 'x']}}, {}, {'status'}) == {}
    # Its Analyst and its Reviewer (ticket #199), and the users of every change.
    assert nq_call_emails.recipients_of(events, ['EJAITUR', 'ebbbbbb']) == {'eaaaaaa': ['k1'], 'ebbbbbb': ['k1'], 'ejaitur': ['k1']}
    subject, body = nq_call_emails.call_email('DriveTest Analyzer', 'UK', 'User A', events, ['k1'], 'https://tool', {})
    # The emails of one call keep its subject, whatever happened (which leads the title), so they are one conversation.
    assert subject == 'NQ Call J1 · EE · C1 · Data (UK)' and 'Completed' in body and 'Every field filled' in body and 'Filled · Analysis' in body
    assert nq_call_emails.call_thread('UK', 'k1') == 'nq-call-UK-k1'


def test_the_table_filters_by_the_day_of_the_call_and_tells_the_analyst_fields_filled(prioritized):
    """Ticket #191: the Call Date filter (Start Time without its time) and the Analyst Fields column."""
    client = prioritized['client']
    days = nq.filter_options(core.repository)['start_date']
    assert days and days == sorted(days, reverse=True) and all(len(day) == 10 for day in days)
    listed = client.post('/api/non-qualified-calls/calls', json={'filters': {'start_date': [days[0]]}, 'page_size': 100}).json()
    assert listed['total'] > 0 and all(call['start_time'].startswith(days[0]) for call in listed['calls'])
    assert nq.normalize_saved_filters({'start_date': [days[0]]}) == {'start_date': [days[0]]}
    key = call_of('data')
    join_id = priority_rows()[key]['join_id']
    progress = lambda: next(call for call in client.post('/api/non-qualified-calls/calls', json={'filters': {'join_id': [join_id]}}).json()['calls']
                            if call['call_key'] == key)['analyst_fields']
    before = progress()
    state = nq.analyst_fill_states(core.repository, [key])[key]
    assert before['total'] == len(state['filled']) + len(state['missing']) and before['filled'] == len(state['filled'])
    assert 'Header · Analyst' in before['missing']
    call = detail(client, key)
    updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={'changes': {'analyst': 'super'}, 'version': call['version']})
    assert updated.status_code == 200, updated.text
    after = progress()
    assert after['filled'] == before['filled'] + 1 and 'Header · Analyst' not in after['missing']


def test_the_reviewers_get_a_summary_of_the_nq_calls_as_often_as_they_chose(prioritized, flow):
    """Ticket #194: a daily summary at 17:00 by default, every hour, every Friday at 17:00, at once or never; one's own
    changes only when asked for."""
    client = prioritized['client']
    email_delivery.save_email_delivery_settings(core.repository, {
        'transport': 'webhook', 'webhook_url': FLOW, 'port': 587, 'from_address': 'admin@example.com', 'max_attachments_mb': 20,
        'link_days': 7, email_delivery.EVERY_NQ_CALL_KEY: ['super'],
    }, keep_password=False, keep_webhook_url=False)
    core.repository.set_user_email('super', 'super@example.com')
    key = call_of('data')
    version = detail(client, key)['version']
    for status in ('Ongoing', 'Finished'):
        updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={'changes': {'fields': {'analysis_status': status}},
                                                                              'version': version})
        assert updated.status_code == 200, updated.text
        version = updated.json()['call']['version']
    # The changes made by the user itself are not told by default.
    assert flow == [] and nq_call_emails.send_due_summaries(core.repository, 'DT Analyzer') == 0
    with core.repository.global_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM nq_email_queue').fetchone()[0] == 0
    core.repository.set_email_preferences('super', nq_frequency='daily', nq_own_changes=True)
    updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={'changes': {'fields': {'analysis_status': 'Rejected'}},
                                                                          'version': version})
    version = updated.json()['call']['version']
    client.patch(f'/api/non-qualified-calls/calls/{key}', json={'changes': {'fields': {'analysis_status': 'Ongoing'}}, 'version': version})
    assert flow == []
    with core.repository.global_connection() as conn:
        created = conn.execute('SELECT MAX(created_at) FROM nq_email_queue').fetchone()[0]
    made = datetime.fromisoformat(created).astimezone()
    # Nothing goes before 17:00 of the day after the changes when they were made after 17:00 (or of the same day otherwise).
    due = made.replace(hour=17, minute=0, second=0, microsecond=0)
    if due <= made:
        due += timedelta(days=1)
    assert nq_call_emails.send_due_summaries(core.repository, 'DT Analyzer', now=due - timedelta(minutes=1)) == 0
    assert nq_call_emails.send_due_summaries(core.repository, 'DT Analyzer', now=due) == 1
    assert len(flow) == 1
    sent = json.dumps(flow[0])
    # One call, its status from before the first change to after the last one.
    assert 'Daily summary' in sent and 'Analysis Status' in sent and 'Finished' in sent and 'Ongoing' in sent
    assert any(json.loads(row['details']).get('kind') == 'nq_call_summary' for row in core.repository.list_logs() if row['action'] == 'email_sent')
    with core.repository.global_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM nq_email_queue').fetchone()[0] == 0


def test_the_summaries_go_at_their_time_and_tell_each_call_once():
    friday = datetime(2026, 11, 20, 18, 30).astimezone()
    assert nq_call_emails.last_summary_time('hourly', friday).hour == 18
    assert nq_call_emails.last_summary_time('daily', friday) == friday.replace(hour=17, minute=0)
    assert nq_call_emails.last_summary_time('daily', friday.replace(hour=9)).day == 19
    assert nq_call_emails.last_summary_time('weekly', friday) == friday.replace(hour=17, minute=0)
    # Before 17:00 on a Friday, and on the Thursday after it, the last weekly summary was the Friday before.
    assert nq_call_emails.last_summary_time('weekly', friday.replace(hour=16)).day == 13
    assert nq_call_emails.last_summary_time('weekly', datetime(2026, 11, 26, 20).astimezone()).day == 20
    assert nq_call_emails.frequency_of({}) == 'daily' and nq_call_emails.frequency_of({'nq_frequency': 'weekly'}) == 'weekly'
    state = {'call_key': 'k1', 'complete': False}
    rows = [{'call_key': 'k1', 'actor': 'a', 'event_json': json.dumps({'state': state, 'changes': [['Analysis Status', 'Pending', 'Ongoing']], 'completed': False})},
            {'call_key': 'k1', 'actor': 'b', 'event_json': json.dumps({'state': state, 'changes': [['Analysis Status', 'Ongoing', 'Finished']], 'completed': False})},
            {'call_key': 'k2', 'actor': 'a', 'event_json': json.dumps({'state': state, 'changes': [['Analysis Status', 'Pending', 'Ongoing'], ['NQ Call Status', 'A', 'B']], 'completed': False})},
            {'call_key': 'k2', 'actor': 'a', 'event_json': json.dumps({'state': state, 'changes': [['Analysis Status', 'Ongoing', 'Pending']], 'completed': False})}]
    events, actors = nq_call_emails.merge_events(rows)
    assert events['k1']['changes'] == [('Analysis Status', 'Pending', 'Finished')] and actors == ['a', 'b']
    # A status back to its value is left out.
    assert events['k2']['changes'] == [('NQ Call Status', 'A', 'B')]


def test_each_user_chooses_how_often_it_gets_the_nq_call_emails(prioritized):
    """Ticket #194: Email preferences of the user badge."""
    client = prioritized['client']
    assert client.get('/account/email').json()['nq_email_frequency'] == 'daily'
    page = client.get('/non-qualified-calls').text
    assert 'Email preferences' in page and 'name="nq_email_frequency"' in page
    saved = client.post('/account/email', data={'email': 'super@example.com', 'nq_email_frequency': 'weekly', 'nq_email_own_changes': '1'})
    assert saved.status_code == 200 and saved.json()['nq_email_frequency_label'] == 'Weekly on Friday at 17:00'
    stored = client.get('/account/email').json()
    assert stored['nq_email_frequency'] == 'weekly' and stored['nq_email_own_changes'] is True
    assert client.post('/account/email', data={'email': '', 'nq_email_frequency': 'monthly'}).status_code == 400
    # A form without the choice keeps it.
    assert client.post('/account/email', data={'email': 'super@example.com'}).json()['nq_email_frequency'] == 'weekly'
    assert any(row['action'] == 'change_email' and 'nq_email_frequency' in row['details'] for row in core.repository.list_logs())
    # It travels with Users & Access.
    exported = next(user for user in core.repository.users_access_payload({})['users'] if user['username'] == 'super')
    assert exported['nq_email_frequency'] == 'weekly' and exported['nq_email_own_changes'] is True


def test_the_analyst_and_the_reviewer_are_emailed_of_a_new_comment(prioritized, flow):
    """Ticket #199: a comment emails the Analyst and the Reviewer of the call, with its text, but never its author."""
    client = prioritized['client']
    email_delivery.save_email_delivery_settings(core.repository, {
        'transport': 'webhook', 'webhook_url': FLOW, 'port': 587, 'from_address': 'admin@example.com', 'max_attachments_mb': 20,
        'link_days': 7}, keep_password=False, keep_webhook_url=False)
    core.repository.create_user('EANALYST', 'Secret123', 'user-editor')
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'EANALYST')
    core.repository.set_user_workspace_access(user_id, [core.active_workspace.id])
    core.repository.set_user_email('EANALYST', 'analyst@example.com')
    core.repository.set_email_preferences('EANALYST', nq_frequency='immediate')
    core.repository.set_user_email('super', 'super@example.com')
    key = call_of('data')
    call = detail(client, key)
    updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={'changes': {'analyst': 'EANALYST'}, 'version': call['version']})
    assert updated.status_code == 200, updated.text
    # The Analyst is told it was given the call (the author, super, is not told of its own change).
    assert len(flow) == 1 and 'analyst@example.com' in json.dumps(flow[0])
    del flow[:]
    response = client.post(f'/api/non-qualified-calls/calls/{key}/comments', json={'body': 'Please check the neighbours'})
    assert response.status_code == 200, response.text
    assert len(flow) == 1
    sent = json.dumps(flow[0])
    assert 'analyst@example.com' in sent and 'super@example.com' not in sent
    assert 'New comment' in sent and 'Please check the neighbours' in sent and 'commented on' in sent


def test_the_summaries_keep_the_comments_of_each_call():
    state = {'call_key': 'k1', 'join_id': 'J1', 'operator': 'EE', 'campaign': 'C1', 'service': 'data', 'start_time': '',
             'status': 'New', 'team': '', 'analyst': 'EAAAAAA', 'reviewer': '', 'root_category': '', 'root_cause': '',
             'filled': [], 'missing': [('Header', 'Team')], 'complete': False}
    rows = [{'call_key': 'k1', 'actor': 'EBBBBBB', 'event_json': json.dumps(nq_call_emails.comment_events(state, 'EBBBBBB', text)['k1'])}
            for text in ('First', 'Second')]
    events, actors = nq_call_emails.merge_events(rows)
    assert [comment['body'] for comment in events['k1']['comments']] == ['First', 'Second'] and actors == ['EBBBBBB']
    subject, body = nq_call_emails.summary_email('DriveTest Analyzer', 'UK', 'daily', events, actors, 'https://tool', {})
    assert body.count('New comment') >= 2 and 'Second' in body
