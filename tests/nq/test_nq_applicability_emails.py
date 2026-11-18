"""Fields that do not apply to a call (ticket #186) and the emails to the reviewers of the NQ calls (ticket #187)."""
import json

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
    key = call_of('data')
    call = detail(client, key)
    # Choosing the reviewer changes no status: nobody is emailed.
    updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={'changes': {'reviewer': 'super'}, 'version': call['version']})
    assert updated.status_code == 200, updated.text
    assert flow == []
    updated = client.patch(f'/api/non-qualified-calls/calls/{key}', json={
        'changes': {'fields': {'analysis_status': 'Finished'}}, 'version': updated.json()['call']['version']})
    assert updated.status_code == 200, updated.text
    # One email (the reviewer is also among the users of every change), with what changed and the fields still empty.
    assert len(flow) == 1
    sent = json.dumps(flow[0])
    assert 'Status changed' in sent and 'Analysis Status' in sent and 'Finished' in sent and 'Still empty' in sent
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
    assert nq_call_emails.recipients_of(events, ['EJAITUR', 'ebbbbbb']) == {'ebbbbbb': ['k1'], 'ejaitur': ['k1']}
    subject, body = nq_call_emails.call_email('DriveTest Analyzer', 'UK', 'User A', events, ['k1'], 'https://tool', {})
    assert subject.startswith('NQ Calls - Completed - J1') and 'Every field filled' in body and 'Filled · Analysis' in body
