"""The emails of the tool through Email Delivery (an SMTP server or a Power Automate flow): access requests and the
activation of their users, password resets from the login page, the email address of each user, the updates of Ticket
Center for the reporters of the tickets, and the download links (and OneDrive copy) of the Reporting emails."""
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

import src.DriveTestAnalyzer as core
from src.modules import email_delivery, notifications, report_tasks
from src.modules.repository import derived_email

FLOW = 'https://prod-00.westeurope.logic.azure.com/workflows/abc/triggers/manual/paths/invoke?sig=secret-signature'


class FlowResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture()
def flow(monkeypatch):
    """The requests the Power Automate flow receives, sent at once (not in the background)."""
    received = []

    def urlopen(request, timeout=None):
        received.append({'url': request.full_url, **json.loads(request.data.decode())})
        return FlowResponse()

    monkeypatch.setattr(email_delivery.urllib.request, 'urlopen', urlopen)
    monkeypatch.setattr(notifications, 'submit', lambda task: task())
    return received


def use_flow(**values):
    email_delivery.save_email_delivery_settings(core.repository, {
        'transport': 'webhook', 'webhook_url': FLOW, 'port': 587, 'from_address': 'admin@example.com', 'max_attachments_mb': 20,
        'link_days': 7, **values,
    }, keep_password=False, keep_webhook_url=False)
    # The links of the emails take the Public address of the server of Application Runtime.
    core.repository.set_application_state(core.RUNTIME_CONFIGURATION_STATE_KEY, json.dumps({'public_address': 'https://tool.example:8443'}))


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def logged(action):
    return [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == action]


def test_email_delivery_sends_through_a_power_automate_flow(client, flow):
    login(client)
    saved = client.post('/application-config/email-delivery', data={
        'transport': 'webhook', 'webhook_url': FLOW, 'link_days': '5',
        'from_address': 'admin@example.com', 'port': '587', 'max_attachments_mb': '20', 'notify_tickets': 'true',
    }, follow_redirects=False)
    assert saved.status_code == 303 and 'error' not in saved.headers['location']
    settings = core.email_delivery_settings(core.repository, include_password=True)
    assert (settings['transport'], settings['configured'], settings['webhook_url'], settings['link_days']) == ('webhook', True, FLOW, 5)
    # Unchecked switches are off; the flow address is a secret the page never shows, kept when left empty.
    assert (settings['notify_tickets'], settings['notify_access_requests'], settings['onedrive_copy']) == (True, False, False)
    page = client.get('/application-config').text
    assert 'Power Automate flow' in page and 'secret-signature' not in page
    client.post('/application-config/email-delivery', data={'transport': 'webhook', 'webhook_url': '', 'port': '587',
                                                            'max_attachments_mb': '20', 'link_days': '5'})
    assert core.email_delivery_settings(core.repository, include_password=True)['webhook_url'] == FLOW
    assert 'secret-signature' not in json.dumps(logged('save_email_delivery'))
    invalid = client.post('/application-config/email-delivery', data={'transport': 'webhook', 'webhook_url': 'http://insecure',
                                                                      'port': '587', 'max_attachments_mb': '20'}, follow_redirects=False)
    assert 'error=' in invalid.headers['location']
    tested = client.post('/application-config/email-delivery/test', data={'recipient': 'someone@example.com'}, follow_redirects=False)
    assert 'notice=' in tested.headers['location'], tested.headers['location']
    message = flow[-1]
    assert message['url'] == FLOW and message['kind'] == 'test' and message['to'] == 'someone@example.com'
    assert message['reply_to'] == 'admin@example.com' and 'can deliver its emails' in message['html']
    # A flow sends no attachments, and a request too large for it is refused before it is sent.
    with pytest.raises(RuntimeError, match='attachments'):
        email_delivery.send_email(core.email_delivery_settings(core.repository, include_password=True), ['a@example.com'], 'S', 'T', 'H',
                                  [('file.pptx', Path(__file__))])
    with pytest.raises(RuntimeError, match='KB'):
        email_delivery.send_email(core.email_delivery_settings(core.repository, include_password=True), ['a@example.com'], 'S', 'T',
                                  'x' * 40_000)


def test_signed_links_expire_and_cannot_be_forged(client):
    token = email_delivery.sign_link(core.repository, {'k': 'report-file', 'p': 'run/file.pptx'}, seconds=60)
    assert email_delivery.read_link(core.repository, token, 'report-file')['p'] == 'run/file.pptx'
    assert email_delivery.read_link(core.repository, token, 'password-reset') is None
    body, signature = token.split('.')
    assert email_delivery.read_link(core.repository, f'{body[:-2]}xx.{signature}', 'report-file') is None
    expired = email_delivery.sign_link(core.repository, {'k': 'report-file', 'p': 'x'}, seconds=-1)
    assert email_delivery.read_link(core.repository, expired, 'report-file') is None


def test_users_have_an_email_derived_from_their_names_that_they_and_the_administrators_change(client):
    assert derived_email('José María', 'García López') == 'jose.maria.garcia.lopez@ericsson.com'
    assert derived_email('Ana', '') == ''
    # The accounts of earlier versions get it once, unless two would share it.
    for username, first, last in (('EAAAAAA', 'Ana', 'Ruiz'), ('EBBBBBB', 'Luis', 'Paz'), ('ECCCCCC', 'Luis', 'Paz')):
        core.repository.create_user(username, 'secret123', 'user-editor', first_name=first, last_name=last)
    with core.repository.global_connection() as conn:
        conn.execute('ALTER TABLE users DROP COLUMN email')
    core.repository.initialize()
    emails = {row['username']: row['email'] for row in core.repository.list_users()}
    assert (emails['EAAAAAA'], emails['EBBBBBB'], emails['ECCCCCC']) == ('ana.ruiz@ericsson.com', '', '')
    # Each user changes it from the account badge.
    login(client)
    page = client.get('/documents/view/help').text
    assert 'data-account-email-open' in page and 'Email address' in page
    assert client.post('/account/email', data={'email': 'not an address'}).status_code == 400
    assert client.post('/account/email', data={'email': 'super.user@example.com'}).json() == {'email': 'super.user@example.com'}
    assert client.get('/account/email').json()['email'] == 'super.user@example.com'
    assert logged('change_email')[-1] == {'changes': {'email': ['', 'super.user@example.com']}}
    # And the super-admins from Users.
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'EBBBBBB')
    response = client.post(f'/admin/users/{user_id}/update', data={'username': 'EBBBBBB', 'role': 'user-editor', 'active': '1',
                                                                   'email': 'luis.x.paz@example.com', 'edited_field': 'email'},
                           headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json'})
    assert response.status_code == 200 and response.json()['user']['email'] == 'luis.x.paz@example.com'
    assert logged('update_user')[-1]['changes']['email'] == ['', 'luis.x.paz@example.com']
    assert 'luis.x.paz@example.com' in client.get('/super-admin').text
    # It travels with Users & Access: a package of before keeps the local address.
    payload = core.repository.users_access_payload({})
    account = next(item for item in payload['users'] if item['username'] == 'EBBBBBB')
    assert account['email'] == 'luis.x.paz@example.com'
    core.repository.set_user_email('EBBBBBB', 'changed@example.com')
    core.repository.merge_users_access(payload, {}, protected_username='super')
    assert core.repository.get_user('EBBBBBB').email == 'luis.x.paz@example.com'
    del account['email']
    core.repository.set_user_email('EBBBBBB', 'kept@example.com')
    core.repository.merge_users_access(payload, {}, protected_username='super')
    assert core.repository.get_user('EBBBBBB').email == 'kept@example.com'


def test_access_requests_are_emailed_and_the_requester_is_told_when_activated(client, flow):
    use_flow(notify_access_requests=True)
    uk = core.repository.save_workspace_group(None, 'UK', '', [core.active_workspace.id])
    profile = next(item for item in core.repository.list_modules_profiles() if item['name'] == 'All Modules')
    assert 'data-password-reset-open' in client.get('/login').text
    request = {'username': 'eabcdef', 'first_name': 'Ana', 'last_name': 'García', 'email': 'ana.garcia@example.com',
               'password': 'secret1', 'password_confirmation': 'secret1', 'workspace_group_ids': [uk], 'modules_profile_id': profile['id']}
    assert client.post('/api/access-requests', json={**request, 'email': ''}).json()['detail'] == 'Enter your email address.'
    assert client.post('/api/access-requests', json={**request, 'email': 'nope'}).json()['detail'] == 'Enter a valid email address.'
    response = client.post('/api/access-requests', json=request)
    assert response.status_code == 201, response.text
    assert response.json()['email_sent'] is True
    message = flow[-1]
    assert message['kind'] == 'access_request' and message['to'] == 'jaime.tur@ericsson.com'
    assert message['cc'].split(';')[-1] == 'ana.garcia@example.com' and len(message['cc'].split(';')) == 5
    assert message['reply_to'] == 'ana.garcia@example.com' and message['subject'].endswith('access request: EABCDEF')
    assert 'on behalf of <strong>Ana García</strong>' in message['html'] and 'Email: ana.garcia@example.com' in message['html']
    assert core.repository.get_user('EABCDEF').email == 'ana.garcia@example.com'
    assert logged('email_sent')[-1]['kind'] == 'access_request'
    # Once a super-admin activates the user, the requester is told.
    login(client)
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'EABCDEF')
    client.post('/admin/users/bulk', data={'user_ids': [user_id], 'action': 'activate'})
    granted = flow[-1]
    assert granted['kind'] == 'access_granted' and granted['to'] == 'ana.garcia@example.com'
    assert 'https://tool.example:8443/login' in granted['html'] and 'EABCDEF' in granted['html']
    # Not again for a user that waits for nothing.
    count = len(flow)
    client.post('/admin/users/bulk', data={'user_ids': [user_id], 'action': 'activate'})
    assert len(flow) == count
    # Without the switch, the requester sends it from its mail client.
    use_flow(notify_access_requests=False)
    other = client.post('/api/access-requests', json={**request, 'username': 'eghijkl', 'email': 'luis@example.com'})
    assert other.json()['email_sent'] is False and len(flow) == count


def test_a_user_who_forgot_the_password_chooses_a_new_one_from_an_emailed_link(client, flow):
    use_flow()
    core.repository.create_user('EPENDNG', 'old-secret', 'user-editor', active=False, email='pending@example.com')
    core.repository.create_user('ENOMAIL', 'old-secret', 'user-editor')
    assert client.post('/api/password-reset', json={'username': 'enobody'}).status_code == 404
    assert 'no email address' in client.post('/api/password-reset', json={'username': 'enomail'}).json()['detail']
    response = client.post('/api/password-reset', json={'username': 'ependng'})
    assert response.status_code == 200, response.text
    assert response.json()['email'] == 'p******@example.com'
    # One link a minute.
    assert client.post('/api/password-reset', json={'username': 'ependng'}).status_code == 429
    message = flow[-1]
    assert message['kind'] == 'password_reset' and message['to'] == 'pending@example.com'
    link = re.search(r'href="(https://tool\.example:8443/login\?reset_token=[^"]+)"', message['html']).group(1)
    token = parse_qs(urlsplit(link.replace('&amp;', '&')).query)['reset_token'][0]
    page = client.get(f'/login?reset_token={token}').text
    assert 'Choose a new password' in page and 'EPENDNG' in page
    assert client.post('/api/password-reset/confirm', json={'token': token, 'password': 'new', 'password_confirmation': 'other'}).status_code == 400
    done = client.post('/api/password-reset/confirm', json={'token': token, 'password': 'new-secret', 'password_confirmation': 'new-secret'})
    assert done.json() == {'username': 'EPENDNG', 'active': False}
    assert core.verify_password('new-secret', core.repository.get_user('EPENDNG').password_hash)
    # The link works once.
    assert client.post('/api/password-reset/confirm', json={'token': token, 'password': 'x', 'password_confirmation': 'x'}).status_code == 400
    assert 'expired or was already used' in client.get(f'/login?reset_token={token}').text
    assert [item['email'] for item in logged('password_reset_requested')] == ['pending@example.com'] and logged('password_reset')


def test_the_reporter_of_a_ticket_is_told_of_the_changes_of_others_also_in_the_tickets_that_mention_it(client, flow):
    use_flow(notify_tickets=True)
    for username, email in (('EREPORT', 'reporter@example.com'), ('EOTHERS', 'others@example.com')):
        user_id = core.repository.create_user(username, 'secret123', 'user-editor', first_name=username.title(), last_name='User',
                                              email=email)
        profile = next(item['id'] for item in core.repository.list_modules_profiles() if item['name'] == 'All Modules')
        core.repository.set_users_modules_profile([user_id], profile)
    core.invalidate_module_access_cache()
    login(client, 'EREPORT', 'secret123')
    first = client.post('/api/tickets', data={'title': 'Export fails', 'description': 'It fails.', 'module': 'scoring', 'priority': 'P2',
                                              'ticket_type': 'bug'}).json()['id']
    # Its reporter gets the confirmation.
    assert [(item['to'], item['subject']) for item in flow] == [('reporter@example.com', f'Ticket #{first} opened: Export fails')]
    assert f'https://tool.example:8443/tickets/{first}' in flow[-1]['html'] and 'It fails.' in flow[-1]['html']
    # Its own comments are not told to it.
    client.post(f'/api/tickets/{first}/comments', data={'body': 'More details.'})
    assert len(flow) == 1
    login(client, 'EOTHERS', 'secret123')
    client.post(f'/api/tickets/{first}/comments', data={'body': 'I see it too.'})
    assert (flow[-1]['to'], flow[-1]['subject']) == ('reporter@example.com', f'Ticket #{first} new comment: Export fails')
    assert 'Eothers User</strong> added a comment' in flow[-1]['html'] and 'I see it too.' in flow[-1]['html']
    # A ticket of another reporter that mentions it: its reporter is told of the new ticket and of its changes.
    second = client.post('/api/tickets', data={'title': 'Same as before', 'description': f'Like #{first}.', 'priority': 'P3',
                                               'ticket_type': 'bug'}).json()['id']
    told = {item['to']: item for item in flow[-2:]}
    assert set(told) == {'others@example.com', 'reporter@example.com'}
    assert f'mentions your ticket <strong>#{first}</strong> (Export fails)' in told['reporter@example.com']['html']
    count = len(flow)
    login(client)
    client.post(f'/api/tickets/{second}/manage', data={'status': 'in_progress'})
    assert {item['to'] for item in flow[count:]} == {'others@example.com', 'reporter@example.com'}
    assert all('In Progress' in item['html'] for item in flow[count:])
    assert logged('email_sent')[-1]['kind'] == 'ticket'
    # Without the switch, nothing is sent.
    use_flow(notify_tickets=False)
    count = len(flow)
    client.post(f'/api/tickets/{first}/comments', data={'body': 'Quiet.'})
    assert len(flow) == count


def test_reporting_emails_give_download_links_and_the_flow_copies_the_files_to_onedrive(client, flow):
    from tests.test_reporting_jobs import wait_for_run
    from src.modules.report_tasks import register_report_artifact_provider

    def generate(config, folder, stamp, user):
        path = folder / f'{stamp} - Big report.pptx'
        path.write_bytes(b'big report')
        return [{'module': 'fake', 'title': 'Big report', 'file_name': path.name, 'size': 10, 'status': 'ready',
                 'details': ['Filter: everything']}]

    register_report_artifact_provider('fake', 'Fake module', 'datasets-analysis', generate)
    try:
        use_flow(onedrive_copy=True)
        login(client)
        task = client.post('/api/reporting/tasks', json={
            'name': 'Weekly check', 'definition': {'modules': {'fake': {'enabled': True}}}, 'send_email': True,
            'recipients': 'a@example.com; b@example.com', 'schedule': {'mode': 'weekly', 'time': '08:00', 'weekdays': [0]}, 'enabled': False,
        }).json()['task']
        run = wait_for_run(client, client.post(f"/api/reporting/tasks/{task['id']}/run").json()['run_id'])
        assert run['status'] == 'sent' and 'as links, copied to OneDrive' in run['email_status'], run
        message = flow[-1]
        assert message['kind'] == 'report' and message['to'] == 'a@example.com;b@example.com'
        files = message['onedrive']['files']
        assert message['onedrive']['folder'].startswith('DriveTest Analyzer/Reporting/') and [item['name'] for item in files] == [
            run['artifacts'][0]['file_name']]
        assert report_tasks.ONEDRIVE_LINK_PLACEHOLDER in message['html'] and 'valid for 7 days' in message['html']
        assert files[0]['url'] in message['html'] and 'Filter: everything' in message['html']
        # The link downloads the file without signing in, while it is valid.
        client.cookies.clear()
        path = urlsplit(files[0]['url']).path
        downloaded = client.get(path)
        assert downloaded.status_code == 200 and downloaded.content == b'big report'
        assert logged('download_reporting_file_link')[-1]['file'] == run['artifacts'][0]['file_name']
        assert client.get(path[:-3] + 'abc').status_code == 410
    finally:
        report_tasks.ARTIFACT_PROVIDERS.pop('fake', None)
