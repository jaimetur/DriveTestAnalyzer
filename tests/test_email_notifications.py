"""The emails of the tool through Email Delivery (an SMTP server or a Power Automate flow): access requests and the
activation of their users, password resets from the login page, the email address of each user, the updates of Ticket
Center for the reporters of the tickets, and the download links of the Reporting emails."""
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

import src.DriveTestAnalyzer as core
from src.modules.core import email_delivery, notifications
from src.modules.core.email_markdown import markdown_html
from src.modules.reporting import report_tasks
from src.modules.core.repository import derived_email

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
    # The download links of the report emails work 60 days unless Email Delivery says otherwise.
    assert core.email_delivery_settings(core.repository)['link_days'] == 60
    login(client)
    saved = client.post('/application-config/email-delivery', data={
        'transport': 'webhook', 'webhook_url': FLOW, 'link_days': '5',
        'from_address': 'admin@example.com', 'port': '587', 'max_attachments_mb': '20', 'notify_tickets': 'true',
    }, follow_redirects=False)
    assert saved.status_code == 303 and 'error' not in saved.headers['location']
    settings = core.email_delivery_settings(core.repository, include_password=True)
    assert (settings['transport'], settings['configured'], settings['webhook_url'], settings['link_days']) == ('webhook', True, FLOW, 5)
    # Unchecked switches are off; the flow address is a secret the page never shows, kept when left empty.
    assert (settings['notify_tickets'], settings['notify_access_requests']) == (True, False)
    page = client.get('/application-config').text
    assert 'Power Automate flow' in page and 'secret-signature' not in page
    client.post('/application-config/email-delivery', data={'transport': 'webhook', 'webhook_url': '', 'port': '587',
                                                            'from_address': 'admin@example.com', 'max_attachments_mb': '20',
                                                            'link_days': '5', 'notify_tickets': 'true'})
    assert core.email_delivery_settings(core.repository, include_password=True)['webhook_url'] == FLOW
    assert 'secret-signature' not in json.dumps(logged('save_email_delivery'))
    invalid = client.post('/application-config/email-delivery', data={'transport': 'webhook', 'webhook_url': 'http://insecure',
                                                                      'port': '587', 'max_attachments_mb': '20'}, follow_redirects=False)
    assert 'error=' in invalid.headers['location']
    tested = client.post('/application-config/email-delivery/test', data={'recipient': 'someone@example.com'}, follow_redirects=False)
    assert 'notice=' in tested.headers['location'], tested.headers['location']
    message = flow[-1]
    assert message['url'] == FLOW and message['kind'] == 'test' and message['to'] == 'someone@example.com'
    # Every email of the tool starts its subject with the prefix of the tool, once.
    assert message['subject'] == 'DT Analyzer - Test email' and email_delivery.subject_line(message['subject']) == message['subject']
    assert message['reply_to'] == 'admin@example.com' and 'can deliver its emails' in message['html']
    # It starts a conversation; when the mailbox of the flow (the sender address) receives it too, the flow deletes its
    # copy in Sent Items, so the email shows once.
    assert (message['thread'], message['previous_folder'], message['delete_sent_copy']) == (False, 'SentItems', False)
    client.post('/application-config/email-delivery/test', data={'recipient': 'Admin@Example.com'})
    assert (flow[-1]['to'], flow[-1]['previous_folder'], flow[-1]['delete_sent_copy']) == ('Admin@Example.com', 'Inbox', True)
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
    assert message['reply_to'] == 'ana.garcia@example.com' and message['subject'] == 'DT Analyzer - Access request: EABCDEF'
    assert 'on behalf of <strong>Ana García</strong>' in message['html'] and 'Email: ana.garcia@example.com' in message['html']
    assert core.repository.get_user('EABCDEF').email == 'ana.garcia@example.com'
    assert logged('email_sent')[-1]['kind'] == 'access_request'
    # Once a super-admin activates the user, the requester is told.
    login(client)
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'EABCDEF')
    client.post('/admin/users/bulk', data={'user_ids': [user_id], 'action': 'activate'})
    granted = flow[-1]
    assert granted['kind'] == 'access_granted' and granted['to'] == 'ana.garcia@example.com'
    assert granted['subject'] == 'DT Analyzer - Your access has been granted'
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
    assert message['subject'] == 'DT Analyzer - Choose a new password'
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


def test_the_texts_of_a_ticket_email_read_with_their_formats_as_on_the_page_of_the_ticket():
    text = ('## Problem\nCategory: Bug Fixes:\n- One **bold** `code`\n  - Nested, like #7 and #8\n1. First\n2. Second\n'
            '> [!WARNING] Careful\n> Read it.\n\n```\n<b>raw</b>\n```\n[page](/tickets) [bad](javascript:alert(1)) <script>x</script>')
    markup = markdown_html(text, base_url='https://tool.example:8443', tickets={7: 'Seven'})
    blocks = re.findall(r'<div[^>]*>(.*?)</div>', markup)
    assert blocks[:2] == ['Problem', 'Category: Bug Fixes:'] and 'font-size:1.25em">Problem' in markup
    assert '•&nbsp;</span>One <strong>bold</strong> <code' in markup and '◦&nbsp;</span>Nested' in markup
    assert '1.&nbsp;</span>First' in markup and '2.&nbsp;</span>Second' in markup
    # Only the tickets given are linked; the pages of the tool at its address; never a script.
    assert '<a href="https://tool.example:8443/tickets/7" title="Seven"' in markup and 'tickets/8' not in markup
    assert 'href="https://tool.example:8443/tickets"' in markup and 'javascript' not in markup.replace('(javascript:alert(1))', '')
    assert '<script>' not in markup and '&lt;script&gt;' in markup and '&lt;b&gt;raw&lt;/b&gt;</pre>' in markup
    assert 'border-left:4px solid #a8590a' in markup and 'Careful</div><div>Read it.</div>' in markup
    # The text of the email keeps one line per line.
    assert notifications.html_to_text(markup).splitlines()[:4] == ['Problem', 'Category: Bug Fixes:', '• One bold code', '◦ Nested, like #7 and #8']
    # A text whose formats would not fit a flow goes line by line as it was written.
    long = notifications.text_block('\n'.join(f'- **{index}**' for index in range(300)))
    assert len(long) < notifications.TEXT_HTML_LIMIT and '- **0**<br>- **1**<br>' in long


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
    # Every email of a ticket has the same subject (one conversation in the mail client); its title says what happened.
    assert [(item['to'], item['subject']) for item in flow] == [('reporter@example.com', f'DT Analyzer - Ticket #{first}: Export fails')]
    assert f'<span style="color:#1E61A3">New Ticket</span><span style="color:#9ca3af"> · </span>Ticket #{first}: Export fails</p>' in flow[-1]['html']
    assert f'https://tool.example:8443/tickets/{first}' in flow[-1]['html'] and 'It fails.' in flow[-1]['html']
    # The flow answers the email before with that subject (Outlook keeps emails in one conversation when each answers the
    # one before), in the Sent Items of its mailbox when that mailbox does not receive it.
    assert (flow[-1]['thread'], flow[-1]['previous_folder'], flow[-1]['delete_sent_copy']) == (True, 'SentItems', False)
    # Its own comments are not told to it.
    client.post(f'/api/tickets/{first}/comments', data={'body': 'More details.'})
    assert len(flow) == 1
    login(client, 'EOTHERS', 'secret123')
    client.post(f'/api/tickets/{first}/comments', data={'body': 'I see it too.'})
    assert (flow[-1]['to'], flow[-1]['subject']) == ('reporter@example.com', f'DT Analyzer - Ticket #{first}: Export fails')
    assert '<span style="color:#0F766E">New Comment</span>' in flow[-1]['html']
    assert 'Eothers User</strong> added a comment' in flow[-1]['html'] and 'I see it too.' in flow[-1]['html']
    # A ticket of another reporter that mentions it: its reporter is told of the new ticket and of its changes.
    second = client.post('/api/tickets', data={'title': 'Same as before', 'description': f'Like #{first}.', 'priority': 'P3',
                                               'ticket_type': 'bug'}).json()['id']
    told = {item['to']: item for item in flow[-2:]}
    assert set(told) == {'others@example.com', 'reporter@example.com'}
    assert f'mentions your ticket <strong>#{first}</strong> (Export fails)' in told['reporter@example.com']['html']
    assert f'Like <a href="https://tool.example:8443/tickets/{first}" title="Export fails"' in told['reporter@example.com']['html']
    count = len(flow)
    login(client)
    client.post(f'/api/tickets/{second}/manage', data={'status': 'in_progress'})
    assert {item['to'] for item in flow[count:]} == {'others@example.com', 'reporter@example.com'}
    assert all('In Progress' in item['html'] for item in flow[count:])
    assert all('<span style="color:#2563EB">In Progress</span>' in item['html'] for item in flow[count:])
    assert {item['subject'] for item in flow[count:]} == {f'DT Analyzer - Ticket #{second}: Same as before'}
    count = len(flow)
    client.post(f'/api/tickets/{second}/manage', data={'status': 'resolved'})
    assert all('<span style="color:#15803D">Resolved</span>' in item['html'] for item in flow[count:]) and flow[count:]
    assert logged('email_sent')[-1]['kind'] == 'ticket'
    # Without the switch, nothing is sent.
    use_flow(notify_tickets=False)
    count = len(flow)
    client.post(f'/api/tickets/{first}/comments', data={'body': 'Quiet.'})
    assert len(flow) == count


def test_the_users_chosen_in_email_delivery_are_also_told_of_their_own_ticket_changes(client, flow):
    use_flow(notify_tickets=True)
    profile = next(item['id'] for item in core.repository.list_modules_profiles() if item['name'] == 'All Modules')
    for username, email in (('EOWNER', 'owner@example.com'), ('EREPORT', 'reporter@example.com')):
        user_id = core.repository.create_user(username, 'secret123', 'user-editor', first_name=username.title(), last_name='User',
                                              email=email)
        core.repository.set_users_modules_profile([user_id], profile)
    core.invalidate_module_access_cache()
    # Nobody is chosen by default.
    assert core.email_delivery_settings(core.repository)['own_ticket_changes_users'] == []
    login(client)
    form = {'transport': 'webhook', 'webhook_url': '', 'port': '587', 'from_address': 'admin@example.com', 'max_attachments_mb': '20',
            'link_days': '7', 'notify_tickets': 'true'}
    saved = client.post('/application-config/email-delivery', data={**form, 'own_ticket_changes_users': ['EOWNER']}, follow_redirects=False)
    assert saved.status_code == 303 and 'error' not in saved.headers['location']
    assert core.email_delivery_settings(core.repository)['own_ticket_changes_users'] == ['EOWNER']
    assert logged('save_email_delivery')[-1]['changes']['own_ticket_changes_users'] == [[], ['EOWNER']]
    page = client.get('/application-config').text
    assert 'Users Told Of Their Own Changes' in page
    assert '<option value="EOWNER" selected>Eowner User (EOWNER)</option>' in page and '<option value="EREPORT" >' in page
    # The chosen user gets the emails of the changes it makes to its own tickets; the others still do not.
    told = {}
    for username in ('EOWNER', 'EREPORT'):
        login(client, username, 'secret123')
        ticket = client.post('/api/tickets', data={'title': f'Ticket of {username}', 'description': 'It fails.', 'priority': 'P3',
                                                   'ticket_type': 'bug'}).json()['id']
        count = len(flow)
        client.post(f'/api/tickets/{ticket}/comments', data={'body': 'More details.'})
        told[username] = [(item['to'], item['subject']) for item in flow[count:]]
    assert told == {'EOWNER': [('owner@example.com', f'DT Analyzer - Ticket #{ticket - 1}: Ticket of EOWNER')], 'EREPORT': []}
    # A form that chooses nobody takes it back.
    login(client)
    client.post('/application-config/email-delivery', data=form)
    assert core.email_delivery_settings(core.repository)['own_ticket_changes_users'] == []


def test_reporting_emails_give_links_to_view_online_or_download_the_files_kept_on_the_server_after_signing_in(client, flow):
    from tests.test_reporting_jobs import RECIPIENTS, start_run, wait_for_run
    from src.modules.reporting.report_tasks import register_report_artifact_provider, save_task

    def generate(config, folder, stamp, user):
        path = folder / f'{stamp} - Big report.pptx'
        path.write_bytes(b'big report')
        # The PowerPoint of a report with its preview opens online too.
        (folder / '.report').mkdir(exist_ok=True)
        (folder / '.report' / 'report.json').write_text(json.dumps({'title': 'Big report', 'formats': {
            'powerpoint': {'file_name': path.name, 'previews': 1, 'navigation': []}}}), encoding='utf-8')
        other = folder / f'{stamp} - Big table.xlsx'
        other.write_bytes(b'big table')
        return [{'module': 'fake', 'title': 'Big report', 'file_name': path.name, 'size': 10, 'status': 'ready',
                 'details': ['Filter: everything']},
                {'module': 'fake', 'title': 'Big table', 'file_name': other.name, 'size': 9, 'status': 'ready', 'details': []}]

    register_report_artifact_provider('fake', 'Fake module', 'datasets-analysis', generate)
    try:
        use_flow()
        login(client)
        task = save_task(core.repository, None, {
            'name': 'Weekly check', 'definition': {'modules': {'fake': {'enabled': True}}}, 'send_email': True,
            'recipients': 'a@example.com; b@example.com', 'schedule': {'mode': 'weekly', 'time': '08:00', 'weekdays': [0]}, 'enabled': False,
        }, 'super', **RECIPIENTS)
        run = wait_for_run(client, start_run(task))
        assert run['status'] == 'sent' and 'as links' in run['email_status'], run
        message = flow[-1]
        assert message['kind'] == 'report' and message['to'] == 'a@example.com;b@example.com'
        assert message['subject'].startswith('DT Analyzer - Weekly check · ')
        assert 'onedrive' not in message and 'valid for 7 days' in message['html'] and 'Filter: everything' in message['html']
        assert 'Sign in to DriveTest Analyzer to view each file online or download it' in message['html']
        links = re.findall(r'href="(https://tool\.example:8443/reporting/files/[^"]+)"', message['html'])
        views = re.findall(r'href="(https://tool\.example:8443/reporting/view/[^"]+)"[^>]*>View Online<', message['html'])
        assert len(links) == 2 and run['artifacts'][0]['file_name'] in message['html']
        # Only the file with a preview opens online, with the same signed link as its download, before Download.
        assert len(views) == 1 and urlsplit(views[0]).path.rsplit('/', 1)[1] == urlsplit(links[0]).path.rsplit('/', 1)[1]
        assert message['html'].index(views[0]) < message['html'].index(links[0])
        report_file, table_file = (item['file_name'] for item in run['artifacts'])
        # Without signing in, a link asks to sign in first and the sign-in page returns to it: the download then starts
        # from a page that says so.
        path, view = urlsplit(links[0]).path, urlsplit(views[0]).path
        client.cookies.clear()
        asked = client.get(path, follow_redirects=False)
        assert asked.status_code == 303 and asked.headers['location'] == '/login?' + urlencode({'next': f'{path}?after_sign_in=1'})
        assert client.get(view, follow_redirects=False).headers['location'] == '/login?' + urlencode({'next': view})
        assert not logged('download_reporting_file_link')
        signed = client.post('/login', data={'username': 'super', 'password': 'super123', 'next': f'{path}?after_sign_in=1'},
                             follow_redirects=False)
        assert signed.headers['location'] == f'{path}?after_sign_in=1'
        page = client.get(signed.headers['location'])
        assert page.status_code == 200 and f'Downloading {report_file}' in page.text and f'url={path}"' in page.text
        downloaded = client.get(path)
        assert downloaded.status_code == 200 and downloaded.content == b'big report'
        event = logged('download_reporting_file_link')[-1]
        assert (event['file'], event['run_id'], event['workspace_id'], event['report_owner']) == (
            report_file, run['id'], core.active_workspace.id, 'super')
        assert [row['username'] for row in core.repository.list_logs() if row['action'] == 'download_reporting_file_link'] == ['super']
        assert client.get(path[:-3] + 'abc').status_code == 410
        # View Online opens the report of the run in the viewer of Reporting, in the format of the file.
        opened = client.get(view, follow_redirects=False)
        assert opened.status_code == 303 and opened.headers['location'] == '/reporting?' + urlencode({'report_run': run['id'],
                                                                                                         'format': 'powerpoint'})
        event = logged('view_reporting_file_link')[-1]
        assert (event['file'], event['run_id'], event['format'], event['name']) == (report_file, run['id'], 'powerpoint', 'Weekly check')
        # A file without a preview does not open online.
        table_link = urlsplit(links[1]).path.replace('/reporting/files/', '/reporting/view/')
        assert table_file in message['html'] and client.get(table_link, follow_redirects=False).status_code == 404
        # A user without access to the workspace of the report opens neither link.
        core.repository.create_user('ENOACCS', 'secret123', 'user-editor', email='noaccess@example.com')
        login(client, 'ENOACCS', 'secret123')
        assert client.get(path).status_code == 403 and client.get(view, follow_redirects=False).status_code == 403
        assert logged('report_email_link_denied')[-1] == {'file': report_file, 'workspace_id': core.active_workspace.id,
                                                          'reason': 'workspace_access'}
    finally:
        report_tasks.ARTIFACT_PROVIDERS.pop('fake', None)


def test_the_recipients_of_a_report_can_be_chosen_among_the_users_of_the_tool_with_an_email_address(client):
    core.repository.create_user('EWITHMAIL', 'secret123', 'user-editor', email='with.mail@example.com')
    core.repository.create_user('ENOMAIL', 'secret123', 'user-editor')
    core.repository.create_user('EINACTV', 'secret123', 'user-editor', active=False, email='inactive@example.com')
    member = next(row for row in core.repository.list_users() if row['username'] == 'EWITHMAIL')
    login(client)
    users = {person['username']: person for person in client.get('/api/reporting/recipients').json()['users']}
    # Only the active users with an email address, saying who could not open the links of the email.
    assert 'EWITHMAIL' in users and 'ENOMAIL' not in users and 'EINACTV' not in users
    assert users['EWITHMAIL'] == {'username': 'EWITHMAIL', 'name': 'EWITHMAIL', 'email': 'with.mail@example.com', 'can_open': False}
    core.repository.set_user_workspace_access(int(member['id']), [core.active_workspace.id])
    assert {person['username']: person for person in client.get('/api/reporting/recipients').json()['users']}['EWITHMAIL']['can_open']
    # The editor of a report says how to separate the addresses and offers Add users.
    page = client.get('/reporting').text
    assert 'Separate several addresses with commas, semicolons, spaces or new lines.' in page and 'id="rp-add-users"' in page


def test_report_emails_name_the_format_of_each_file_so_the_powerpoint_and_word_versions_are_told_apart():
    from datetime import datetime

    artifacts = [{'status': 'ready', 'title': f'Bundle Report Template · Weekly ({label})', 'file_name': f'Weekly report.{suffix}',
                  'size': 2 * 1024 * 1024, 'details': ['NR Mode: NSA']} for label, suffix in (('PPT', 'pptx'), ('Word', 'docx'))]
    links = {item['file_name']: f"https://tool.example:8443/reporting/files/{item['file_name']}" for item in artifacts}
    views = {'Weekly report.pptx': 'https://tool.example:8443/reporting/view/Weekly report.pptx'}
    text, markup = report_tasks.email_bodies('Weekly', datetime(2026, 11, 8, 9, 0), artifacts, 'DriveTest Analyzer', links=links,
                                             attached=False, link_days=7, views=views)
    # Each file is a card under a heading of its format, in the colour of its application, with its download link and
    # size on the heading.
    assert '[PowerPoint] Bundle Report Template · Weekly (PPT)' in text and '[Word] Bundle Report Template · Weekly (Word)' in text
    assert 'Download PowerPoint: https://tool.example:8443/reporting/files/Weekly report.pptx' in text
    assert 'View online: https://tool.example:8443/reporting/view/Weekly report.pptx' in text and text.count('View online') == 1
    for name, suffix, colour, tint in (('PowerPoint', 'pptx', '#C43E1C', '#FBEDE8'), ('Word', 'docx', '#185ABD', '#E8EFFA')):
        heading = re.search(rf'<td style="background:{colour};padding:6px 12px"><table[^>]*><tr><td style="color:#ffffff;font-size:15px;'
                            rf'font-weight:bold">{name}</td><td align="right"[^>]*>(.*?)</td></tr></table></td></tr><tr><td '
                            rf'style="background:{tint};', markup)
        assert heading and f'href="https://tool.example:8443/reporting/files/Weekly report.{suffix}"' in heading.group(1)
        assert f'color:{colour};' in heading.group(1) and heading.group(1).endswith('>Download</a> · 2.0 MB')
        # View Online, before Download, for the file whose report opens online.
        assert ('>View Online</a> <a href="https://tool.example:8443/reporting/files/' in heading.group(1)) == (suffix == 'pptx')
    assert markup.count('<table role="presentation"') == 4 and '<ol>' not in markup
    # An email that must be shorter lists the files with their format before each title.
    _text, short = report_tasks.email_bodies('Weekly', datetime(2026, 11, 8, 9, 0), artifacts, 'DriveTest Analyzer', links=links,
                                             attached=False, link_days=7, details=False, cards=False, views=views)
    assert '<strong>View online</strong></a> · <a href="https://tool.example:8443/reporting/files/Weekly report.pptx">' in short
    assert '<table' not in short and 'NR Mode' not in short
    assert 'background:#185ABD;color:#ffffff;font-size:12px;font-weight:bold">Word</span><strong>Bundle Report' in short
    assert '<strong>Download Word</strong></a> · 2.0 MB)' in short
    # Other files name their format too, an unknown one by its extension.
    assert report_tasks.email_file_format('table.xlsx') == ('Excel', '#107C41')
    assert report_tasks.email_file_format('layers.kmz')[0] == 'KMZ'
