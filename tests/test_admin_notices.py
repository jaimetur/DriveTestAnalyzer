"""Admin notices: after signing in and while signed in, each super-admin is told once of the access requests waiting for
activation and of the new bug reports of other users."""
import json
from pathlib import Path

import src.DriveTestAnalyzer as core
from src.modules import admin_notices

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def user_id(username):
    return next(int(row['id']) for row in core.repository.list_users() if row['username'].casefold() == username.casefold())


def requested_at(username):
    return next(str(row['access_requested_at']) for row in core.repository.list_users() if row['username'].casefold() == username.casefold())


def logged(action):
    return [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == action]


def request_access(client, username='eabcdef', password='secret1', first_name='Ana', last_name='García'):
    client.cookies.clear()
    group = next((item['id'] for item in core.repository.list_workspace_groups() if item['name'] == 'UK'), None)
    group = group or core.repository.save_workspace_group(None, 'UK', '', [core.active_workspace.id])
    profile = next(item['id'] for item in core.repository.list_modules_profiles() if item['name'] == 'All Modules')
    response = client.post('/api/access-requests', json={
        'username': username, 'first_name': first_name, 'last_name': last_name, 'password': password,
        'password_confirmation': password, 'workspace_group_ids': [group], 'modules_profile_id': profile,
    })
    assert response.status_code == 201, response.text


def notices(client):
    response = client.get('/api/admin-notices')
    assert response.status_code == 200, response.text
    return response.json()


def polled(client):
    """The ids every page of a super-admin receives with its poll of incoming transfer offers."""
    response = client.get('/admin/import-export/transfers/offers')
    assert response.status_code == 200, response.text
    return response.json()['admin_notices']


def acknowledge(client, payload, choice='close', page='/documents/view/help'):
    response = client.post('/api/admin-notices/seen', headers={'Referer': f'http://testserver{page}'}, json={
        'choice': choice, 'access_requests': [item['key'] for item in payload['access_requests']],
        'bug_reports': [item['key'] for item in payload['bug_reports']],
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_each_super_admin_is_told_once_of_each_access_request(client):
    core.repository.create_user('chief', 'secret123', 'super-admin')
    core.repository.create_user('helper', 'secret123', 'admin')
    request_access(client)
    assert not core.repository.get_user('EABCDEF').active and requested_at('EABCDEF')

    # Only super-admins are told.
    login(client, 'helper', 'secret123')
    assert client.get('/api/admin-notices').status_code == 403
    assert client.post('/api/admin-notices/seen', json={}).status_code == 403

    login(client)
    payload = notices(client)
    assert payload['bug_reports'] == []
    assert [(item['username'], item['name'], item['role']) for item in payload['access_requests']] == [('EABCDEF', 'Ana García', 'user-editor')]
    assert payload['access_requests'][0]['requested_at'][:4].isdigit()
    assert payload['access_requests_url'] == '/admin?users=access-requests#users'
    # The Users table lists the pending request with its own status filter.
    page = client.get('/admin').text
    assert '<option value="access-request">Pending access requests</option>' in page
    assert 'data-username="EABCDEF"' in page and 'data-access-request="1"' in page
    assert acknowledge(client, payload, 'access-requests') == {'access_requests': 1, 'bug_reports': 0}
    assert notices(client)['access_requests'] == []
    assert logged('admin_notices_seen')[0] == {'choice': 'Open Access Requests', 'access_requests': ['EABCDEF'], 'bug_reports': []}

    # Every super-admin is told on its own.
    login(client, 'chief', 'secret123')
    assert [item['username'] for item in notices(client)['access_requests']] == ['EABCDEF']

    # A later request of the same user is told again, until the user is activated.
    request_access(client, first_name='Ana', last_name='Gómez')
    login(client)
    again = notices(client)['access_requests']
    assert [item['name'] for item in again] == ['Ana Gómez'] and again[0]['key'] != payload['access_requests'][0]['key']
    core.repository.update_user(user_id('EABCDEF'), 'EABCDEF', 'user-editor', True)
    assert requested_at('EABCDEF') == ''
    assert notices(client)['access_requests'] == []
    assert 'data-access-request="1"' not in client.get('/admin').text
    # Acknowledging forgets what is no longer pending, and keys of other items are ignored.
    acknowledge(client, {'access_requests': [{'key': 'unknown'}], 'bug_reports': [{'key': 'unknown'}]})
    with core.repository.global_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM admin_notices_seen').fetchone()[0] == 0
    # Deleting a super-admin deletes what it was told.
    request_access(client, 'eklmnop', first_name='Luis', last_name='Pérez')
    login(client, 'chief', 'secret123')
    acknowledge(client, notices(client))
    login(client)
    core.repository.delete_user(user_id('chief'))
    with core.repository.global_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM admin_notices_seen').fetchone()[0] == 0


def test_each_super_admin_is_told_once_of_new_bug_reports_of_other_users(client):
    from src.modules.bugs_report import create_bug, delete_bug

    core.repository.create_user('ana', 'secret123', 'user-viewer', first_name='Ana', last_name='García')
    reported = create_bug(core.repository, title='Export fails', description='', module='scoring', priority='P2', username='ana', app_version='0.7.1')
    attended = create_bug(core.repository, title='Map is empty', description='', module='', priority='P3', username='ana', app_version='0.7.1')
    own = create_bug(core.repository, title='My own bug', description='', module='', priority='P4', username='super', app_version='0.7.1')
    with core.repository.global_connection() as conn:
        conn.execute("UPDATE bug_reports SET status = 'in_progress' WHERE id = ?", (attended,))

    login(client)
    payload = notices(client)
    # Only the reports still New of other users.
    scoring = next(module['title'] for module in core.bug_report_modules() if module['key'] == 'scoring')
    assert [(bug['id'], bug['title'], bug['priority'], bug['reported_by'], bug['module']) for bug in payload['bug_reports']] == [
        (reported, 'Export fails', 'P2', 'Ana García', scoring)]
    assert payload['bugs_report_url'] == '/bugs-report?status=new#section-bug-reports'
    assert acknowledge(client, payload) == {'access_requests': 0, 'bug_reports': 1}
    assert notices(client)['bug_reports'] == []
    assert logged('admin_notices_seen')[0] == {'choice': 'Close', 'access_requests': [], 'bug_reports': [f'#{reported} Export fails']}

    # Another super-admin is told of the report of super too, unless it opens it.
    core.repository.create_user('chief', 'secret123', 'super-admin')
    login(client, 'chief', 'secret123')
    assert [bug['id'] for bug in notices(client)['bug_reports']] == [reported, own]
    assert client.get(f'/bugs-report/{reported}').status_code == 200
    assert [bug['id'] for bug in notices(client)['bug_reports']] == [own]
    # A deleted report is forgotten.
    delete_bug(core.repository, reported)
    acknowledge(client, {'access_requests': [], 'bug_reports': []})
    with core.repository.global_connection() as conn:
        seen = conn.execute("SELECT user_id FROM admin_notices_seen WHERE kind = 'bug_report'").fetchall()
    assert [row[0] for row in seen] == [user_id('super')]

    # Super-admins whose Modules Profile has no Bugs Report are not told of bug reports.
    create_bug(core.repository, title='Another bug', description='', module='', priority='P1', username='ana', app_version='0.7.1')
    profile = next(item for item in core.repository.list_modules_profiles() if item['name'] == 'Benchmarking')
    core.repository.save_modules_profile(profile['id'], profile['name'], profile['description'], ['workspace'])
    core.repository.set_users_modules_profile([user_id('chief')], profile['id'])
    core.invalidate_module_access_cache()
    assert notices(client)['bug_reports'] == []


def test_the_dialog_and_its_links_are_in_the_pages(client):
    root = Path(core.__file__).parent / 'web_interface' / 'static' / 'js'
    script = (root / 'app.js').read_text(encoding='utf-8')
    assert "fetch('/api/admin-notices'" in script and "'/api/admin-notices/seen'" in script
    # The poll of incoming transfer offers hands the ids to the dialog.
    assert "new CustomEvent('drivetest-analyzer:admin-notices'" in script and 'Administrator notice' in script
    assert "get('status')" in (root / 'bugs_report.js').read_text(encoding='utf-8')
    login(client)
    assert "get('users') === 'access-requests'" in client.get('/admin').text
    # The table is listed in Database Management.
    assert core.database_table_type('admin_notices_seen')[0] == 'Application'
    assert 'Admin Notices Seen' in client.get('/admin').text


def test_the_poll_of_the_pages_tells_super_admins_while_signed_in(client):
    from src.modules.bugs_report import create_bug

    login(client)
    assert polled(client) == {'access_requests': [], 'bug_reports': []}
    # A request and a bug report arrive while the super-admin is signed in.
    waiting = core.repository.create_user('EQRSTUV', 'secret1', 'user-editor', active=False, first_name='Eva', last_name='Ruiz')
    core.repository.set_access_requested(waiting, '2026-10-15T10:00:00+02:00')
    bug = create_bug(core.repository, title='Chart is blank', description='', module='', priority='P2', username='ana', app_version='0.7.1')
    create_bug(core.repository, title='Mine', description='', module='', priority='P2', username='super', app_version='0.7.1')
    assert polled(client) == {'access_requests': [waiting], 'bug_reports': [bug]}
    payload = notices(client)
    assert [item['username'] for item in payload['access_requests']] == ['EQRSTUV'] and [item['id'] for item in payload['bug_reports']] == [bug]
    # Told once: the App Event runs in the module of the page the dialog was shown on.
    acknowledge(client, payload, 'bugs-report', page='/bugs-report')
    assert polled(client) == {'access_requests': [], 'bug_reports': []}
    with core.repository.connection() as conn:
        origin = conn.execute("SELECT origin FROM audit_logs WHERE action = 'admin_notices_seen' ORDER BY id DESC").fetchone()[0]
    assert origin == 'module:bugs-report'
    assert logged('admin_notices_seen')[0]['choice'] == 'Open Bugs Report'
    # The poll and the notices it reports are not activity, so the idle tasks still run.
    assert not core.is_interactive_request('GET', '/admin/import-export/transfers/offers', 'application/json')
    assert not core.is_interactive_request('GET', '/api/admin-notices', 'application/json')
    # Only super-admins poll for them.
    core.repository.create_user('helper', 'secret123', 'admin')
    login(client, 'helper', 'secret123')
    assert client.get('/admin/import-export/transfers/offers').status_code == 403


def test_inactive_users_of_earlier_versions_and_users_access_keep_their_access_requests(client):
    core.repository.create_user('waiting', 'secret123', 'user-editor', active=False)
    core.repository.create_user('stopped', 'secret123', 'admin', active=False)
    core.repository.create_user('working', 'secret123', 'user-viewer')
    # A database of an earlier version, without the column.
    with core.repository.global_connection() as conn:
        conn.execute('ALTER TABLE users DROP COLUMN access_requested_at')
    core.repository.initialize()
    rows = {row['username']: row for row in core.repository.list_users()}
    assert rows['waiting']['access_requested_at'] == rows['waiting']['created_at']
    assert rows['stopped']['access_requested_at'] == '' and rows['working']['access_requested_at'] == ''
    assert [item['username'] for item in admin_notices.pending_access_requests(core.repository)] == ['waiting']

    # Users & Access carries the pending request of an inactive user.
    payload = core.repository.users_access_payload({})
    waiting = next(item for item in payload['users'] if item['username'] == 'waiting')
    assert waiting['access_requested_at'] == rows['waiting']['access_requested_at']
    assert next(item for item in payload['users'] if item['username'] == 'working')['access_requested_at'] == ''
    core.repository.delete_user(user_id('waiting'))
    core.repository.merge_users_access(payload, {}, protected_username='super')
    assert requested_at('waiting') == rows['waiting']['access_requested_at']
    # A package of an earlier version keeps the local request; an active account has none.
    earlier = {**payload, 'users': [{key: value for key, value in item.items() if key != 'access_requested_at'} for item in payload['users']]}
    core.repository.merge_users_access(earlier, {}, protected_username='super')
    assert requested_at('waiting') == rows['waiting']['access_requested_at']
    for item in earlier['users']:
        item['active'] = item['active'] or item['username'] == 'waiting'
    core.repository.merge_users_access(earlier, {}, protected_username='super')
    assert requested_at('waiting') == ''
