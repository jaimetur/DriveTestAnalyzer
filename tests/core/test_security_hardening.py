"""Access to the open workspace, password hashes, wrong passwords in a row and who sets where the emails lead
(ticket #110)."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace

import src.DriveTestAnalyzer as core
from src.modules.core import auth


def login(client, username='super', password='super123'):
    return client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)


def new_user(username: str, role: str, *, workspace: bool) -> None:
    core.repository.create_user(username, f'{username}123', role)
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == username)
    core.repository.set_user_workspace_access(user_id, [core.active_workspace.id] if workspace else [])


def test_the_open_workspace_is_refused_to_a_user_it_was_not_given_to(client):
    new_user('EOUTSID', 'user-editor', workspace=False)
    new_user('EINSIDE', 'user-editor', workspace=True)
    assert login(client, 'EOUTSID', 'EOUTSID123').status_code == 303
    # Its pages send to Workspace, which says why; its requests are refused.
    page = client.get('/scoring', headers={'accept': 'text/html'}, follow_redirects=False)
    assert page.status_code == 303 and page.headers['location'].startswith('/workspace?workspace_error=You+do+not+have+access')
    for path in ('/api/scoring/saved-filters', '/api/datasets/status', '/api/workspace-config/campaign-map', '/api/app-logs'):
        refused = client.get(path)
        assert refused.status_code == 403 and 'open workspace (Default)' in refused.json()['detail'], path
    assert client.post('/workspace/delete-datasets', data={'dataset_ids': ['1']}).status_code == 403
    assert client.post('/api/query-builder/run', json={'dataset_ids': [], 'query_sql': 'SELECT 1'}).status_code == 403
    # Workspace opens as with no workspace open (the workspaces to open, none of the data), and Ticket Center as ever.
    workspace = client.get('/workspace')
    assert workspace.status_code == 200 and 'data-workspace-open' in workspace.text
    assert client.get('/tickets').status_code == 200
    # A user of the workspace, and a super-admin without a grant, use it.
    assert login(client, 'EINSIDE', 'EINSIDE123').status_code == 303
    assert client.get('/api/scoring/saved-filters').status_code == 200
    assert login(client).status_code == 303
    assert client.get('/api/scoring/saved-filters').status_code == 200
    assert core.needs_open_workspace('/workspace') is False and core.needs_open_workspace('/reporting/files/1/x') is False
    assert core.needs_open_workspace('/workspace-config') and core.needs_open_workspace('/api/workspace/auto-calculated-fields')
    assert not core.needs_open_workspace('/api/workspaces/sizes')


def test_passwords_are_scrypt_hashes_and_those_of_earlier_versions_move_at_the_next_sign_in(client):
    stored = auth.hash_password('secret123')
    assert stored.startswith('scrypt$') and auth.verify_password('secret123', stored) and not auth.verify_password('secret124', stored)
    assert not auth.password_needs_rehash(stored)
    assert not auth.verify_password('secret123', 'scrypt$99$8$1$00$00') and not auth.verify_password('x', 'nothing')
    # An account kept as earlier versions did (salt$sha256) signs in with its password, and is kept as this one does.
    core.repository.create_user('ELEGACY', 'temporary1', 'user-viewer')
    legacy = 'abcd$' + hashlib.sha256(b'abcd:legacy-pass').hexdigest()
    with core.repository.global_connection() as connection:
        connection.execute('UPDATE users SET password_hash = ? WHERE username = ?', (legacy, 'ELEGACY'))
    assert auth.password_needs_rehash(legacy)
    assert login(client, 'ELEGACY', 'wrong').status_code == 401
    assert core.repository.get_user('ELEGACY').password_hash == legacy
    assert login(client, 'ELEGACY', 'legacy-pass').status_code == 303
    moved = core.repository.get_user('ELEGACY').password_hash
    assert moved.startswith('scrypt$') and auth.verify_password('legacy-pass', moved)
    assert login(client, 'ELEGACY', 'legacy-pass').status_code == 303


def test_wrong_passwords_in_a_row_make_a_username_wait(client, monkeypatch):
    for _attempt in range(5):
        assert login(client, 'admin', 'wrong').status_code == 401
    waiting = login(client, 'ADMIN', 'admin123')  # (Also the right password, and whatever the case of the username.)
    assert waiting.status_code == 429 and 'Too many wrong passwords for this username. Try again in 30 seconds.' in waiting.text
    assert [row['details'] for row in core.repository.list_logs(limit=5) if row['action'] == 'login'][0].count('too_many_attempts') == 1
    assert login(client).status_code == 303  # Another username signs in.
    # Each further wrong password doubles the wait, up to five minutes; a right one, once it may be tried, starts over.
    limiter = auth.AttemptLimiter()
    now = [1000.0]
    monkeypatch.setattr(auth, 'monotonic', lambda: now[0])
    waits = []
    for _attempt in range(10):
        limiter.failed('User')
        waits.append(limiter.wait_seconds('user'))
        now[0] += 400
    assert waits == [0, 0, 0, 0, 30, 60, 120, 240, 300, 300]
    limiter.succeeded('USER')
    assert limiter.wait_seconds('user') == 0
    limiter.failed('user')
    now[0] += 1801
    limiter.failed('user')  # Half an hour later the count starts again.
    assert limiter.wait_seconds('user') == 0


def test_where_the_emails_lead_is_set_by_admins_and_follows_the_addresses_of_the_server(client):
    new_user('EEDITOR', 'user-editor', workspace=True)
    assert login(client).status_code == 303  # A super-admin signs in at http://testserver: an address of this server.
    saved = client.post('/application-config', data={
        'timezone_name': 'Europe/Madrid', 'report_chart_renderer': 'canvas', 'max_background_tasks': '2',
        'public_address': 'https://dta.example.com'}, follow_redirects=False)
    assert saved.status_code == 303 and core.runtime_configuration()['public_address'] == 'https://dta.example.com'
    # A user-editor saves the rest of Application Config; the address of the links and Email Delivery are not theirs.
    assert login(client, 'EEDITOR', 'EEDITOR123').status_code == 303
    page = client.get('/application-config')
    assert page.status_code == 200 and 'name="public_address"' in page.text and 'Admins and super-admins change it' in page.text
    assert 'action="/application-config/email-delivery"' not in page.text and 'Admins and super-admins choose how the tool sends its emails' in page.text
    edited = client.post('/application-config', data={
        'timezone_name': 'Europe/London', 'report_chart_renderer': 'canvas', 'max_background_tasks': '3',
        'public_address': 'https://elsewhere.example.com'}, follow_redirects=False)
    assert edited.status_code == 303
    configuration = core.runtime_configuration()
    assert (configuration['timezone'], configuration['max_background_tasks'], configuration['public_address']) == (
        'Europe/London', 3, 'https://dta.example.com')
    assert client.post('/application-config/email-delivery', data={'transport': 'webhook', 'webhook_url': 'https://elsewhere.example.com/hook'},
                       follow_redirects=False).status_code == 403
    assert client.post('/application-config/email-delivery/test', data={'recipient': 'user@example.com'}, follow_redirects=False).status_code == 403

    # The links of the emails: the Public address; without one, the address of the request only where a super-admin has
    # signed in (a password reset is asked for without signing in, with whatever address its sender writes).
    def request(address: str):
        return SimpleNamespace(base_url=address + '/')
    assert core.email_base_url(request('http://evil.example')) == 'https://dta.example.com'
    assert login(client).status_code == 303
    client.post('/application-config', data={'timezone_name': 'Europe/Madrid', 'report_chart_renderer': 'canvas', 'max_background_tasks': '2',
                                             'public_address': ''})
    assert core.known_server_addresses() == ['http://testserver']
    assert core.email_base_url(request('http://testserver')) == 'http://testserver'
    assert core.email_base_url(request('http://evil.example')) == 'http://testserver'
    # A user who is not a super-admin does not make an address one of the server.
    login(client, 'EEDITOR', 'EEDITOR123')
    assert core.known_server_addresses() == ['http://testserver']
    core.repository.set_application_state(core.KNOWN_ADDRESSES_STATE_KEY, '[]')
    assert core.email_base_url(request('http://first.example')) == 'http://first.example'  # Nobody has signed in yet.
