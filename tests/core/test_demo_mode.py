"""Demo Mode: the platform kept for the users of a demo; the others are warned, asked to save and signed out."""

import json
from datetime import datetime, timedelta, timezone

import pytest

import src.DriveTestAnalyzer as core
from src.modules.core import demo_mode as demo


def in_minutes(minutes):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat(timespec='seconds')


def login(client, username, password):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    return response


@pytest.fixture()
def accounts(client):
    core.repository.create_user('ADMIN01', 'Secret123', 'admin')
    core.repository.create_user('SUPER02', 'Secret123', 'super-admin')
    core.repository.create_user('EUSER01', 'Secret123', 'user-editor')
    core.repository.create_user('EUSER02', 'Secret123', 'user-viewer')
    return client


def heartbeat(client, unsaved=(), leave=False, tab='tab-1'):
    response = client.post('/api/demo-mode/heartbeat', json={'tab': tab, 'unsaved': list(unsaved), 'leave': leave})
    assert response.status_code == 200
    return response.json()


def events(action):
    return [row for row in core.repository.list_logs(None) if row['action'] == action]


def sessions_of(username):
    with core.repository.global_connection() as conn:
        return conn.execute('SELECT COUNT(*) FROM user_login_sessions WHERE username = ?', (username,)).fetchone()[0]


def test_only_admins_and_super_admins_start_it_and_an_admin_keeps_every_super_admin(accounts):
    client = accounts
    assert login(client, 'EUSER01', 'Secret123').status_code == 303
    assert client.post('/api/demo-mode/start', json={'expected_end': in_minutes(60)}).status_code == 403

    assert login(client, 'ADMIN01', 'Secret123').status_code == 303
    assert client.post('/api/demo-mode/start', json={'expected_end': in_minutes(-5)}).status_code == 400
    users = client.get('/api/demo-mode/users').json()
    rows = {row['username']: row for row in users['users']}
    assert users['default_message'] == demo.DEFAULT_MESSAGE
    assert rows['ADMIN01']['locked'] and rows['ADMIN01']['you'] and rows['SUPER02']['locked'] and rows['super']['locked']
    assert not rows['EUSER01']['locked'] and not rows['EUSER01']['selected']

    response = client.post('/api/demo-mode/start', json={'expected_end': in_minutes(60), 'message': 'Customer demo.', 'users': ['EUSER01', 'SUPER02']})
    assert response.status_code == 200
    state = response.json()['demo']
    assert state['users'] == ['ADMIN01', 'EUSER01', 'super', 'SUPER02'] and state['keep_super_admins'] is True
    assert state['message'] == 'Customer demo.'
    # An admin cannot leave the super-admins out when changing the users either.
    state = client.post('/api/demo-mode/update', json={'users': []}).json()['demo']
    assert state['users'] == ['ADMIN01', 'super', 'SUPER02']
    assert core.demo_mode.is_allowed('SUPER03', 'super-admin')
    assert events('demo_mode_started') and events('demo_mode_changed')


def test_a_super_admin_can_leave_other_super_admins_out(accounts):
    client = accounts
    login(client, 'super', 'super123')
    state = client.post('/api/demo-mode/start', json={'expected_end': in_minutes(30), 'users': []}).json()['demo']
    assert state['users'] == ['super'] and state['keep_super_admins'] is False
    assert login(client, 'SUPER02', 'Secret123').status_code == 403
    assert login(client, 'ADMIN01', 'Secret123').status_code == 403
    assert events('demo_mode_sign_in_refused')


def test_the_users_without_access_cannot_sign_in_until_it_ends(accounts):
    client = accounts
    login(client, 'ADMIN01', 'Secret123')
    client.post('/api/demo-mode/start', json={'expected_end': in_minutes(30), 'users': ['EUSER02']})
    refused = login(client, 'EUSER01', 'Secret123')
    assert refused.status_code == 403 and 'used for a demo' in refused.text
    assert login(client, 'EUSER02', 'Secret123').status_code == 303
    page = client.get('/login', follow_redirects=False)
    login(client, 'ADMIN01', 'Secret123')
    assert client.post('/api/demo-mode/end', json={}).status_code == 200
    assert login(client, 'EUSER01', 'Secret123').status_code == 303
    assert events('demo_mode_ended')
    assert page.status_code in {200, 303}
    public = client.get('/api/demo-mode/public').json()
    assert public['active'] is False


def test_the_sign_in_page_says_why_and_until_when(accounts):
    client = accounts
    login(client, 'ADMIN01', 'Secret123')
    client.post('/api/demo-mode/start', json={'expected_end': in_minutes(30), 'message': 'Back soon.'})
    client.cookies.clear()
    page = client.get('/login?demo=signed-out')
    assert 'You were signed out for a demo' in page.text and 'Back soon.' in page.text and 'data-demo-login-notice' in page.text
    public = client.get('/api/demo-mode/public').json()
    assert public['active'] and public['message'] == 'Back soon.' and public['started_by'] == 'ADMIN01'


def test_a_signed_in_user_is_warned_then_signed_out_and_cannot_change_anything(accounts):
    client = accounts
    login(client, 'EUSER01', 'Secret123')
    user_cookie = client.cookies.get(core.SESSION_COOKIE)
    heartbeat(client)  # (A page of the user is open.)
    core.repository.create_user('EUSER03', 'Secret123', 'user-viewer')
    login(client, 'EUSER03', 'Secret123')  # (A session without a page open.)

    login(client, 'ADMIN01', 'Secret123')
    client.post('/api/demo-mode/start', json={'expected_end': in_minutes(30)})
    # Without a page open: signed out at once.
    assert sessions_of('EUSER03') == 0
    assert any(json.loads(row['details'])['reason'] == 'no_page_open' for row in events('demo_mode_user_signed_out'))

    client.cookies.set(core.SESSION_COOKIE, user_cookie)
    reply = heartbeat(client)
    assert reply['leaving']['unsaved'] == [] and 0 < reply['leaving']['seconds_left'] <= demo.SIGN_OUT_GRACE_SECONDS
    assert events('demo_mode_user_warned')
    # Nothing to save: its changes are refused.
    refused = client.post('/account/email', data={'email': 'someone@example.com'})
    assert refused.status_code == 423
    # Sign out now.
    assert heartbeat(client, leave=True)['signed_out'] is True
    assert sessions_of('EUSER01') == 0


def test_a_user_with_unsaved_changes_is_signed_out_once_they_are_saved(accounts):
    client = accounts
    login(client, 'EUSER01', 'Secret123')
    user_cookie = client.cookies.get(core.SESSION_COOKIE)
    heartbeat(client, unsaved=['PPT Design “Weekly KPIs”'])
    login(client, 'ADMIN01', 'Secret123')
    overview = {row['username']: row for row in client.get('/api/demo-mode/users').json()['users']}
    assert overview['EUSER01']['online'] and overview['EUSER01']['unsaved'] == ['PPT Design “Weekly KPIs”']
    client.post('/api/demo-mode/start', json={'expected_end': in_minutes(30)})
    admin_cookie = client.cookies.get(core.SESSION_COOKIE)

    client.cookies.set(core.SESSION_COOKIE, user_cookie)
    reply = heartbeat(client, unsaved=['PPT Design “Weekly KPIs”'])
    assert reply['leaving'] == {'unsaved': ['PPT Design “Weekly KPIs”'], 'seconds_left': None}
    # Saving is possible.
    assert client.post('/account/email', data={'email': 'someone@example.com'}).status_code == 200

    client.cookies.set(core.SESSION_COOKIE, admin_cookie)
    manager = heartbeat(client, tab='admin-tab')
    assert manager['manage'] and manager['departures'][0]['username'] == 'EUSER01' and manager['departures'][0]['unsaved']

    client.cookies.set(core.SESSION_COOKIE, user_cookie)
    assert heartbeat(client)['signed_out'] is True
    signed_out = [json.loads(row['details']) for row in events('demo_mode_user_signed_out')]
    assert signed_out[-1]['reason'] == 'saved_changes'


def test_the_time_up_asks_to_extend_or_end_it(accounts):
    client = accounts
    login(client, 'ADMIN01', 'Secret123')
    client.post('/api/demo-mode/start', json={'expected_end': in_minutes(30)})
    assert heartbeat(client)['time_up'] is False
    state = dict(core.demo_mode.state())
    state['expected_end'] = in_minutes(-1)
    core.repository.set_application_state(demo.STATE_KEY, json.dumps(state))
    core.demo_mode.forget()
    reply = heartbeat(client)
    assert reply['time_up'] is True and reply['overdue'] is True and core.demo_mode.active
    assert reply['extend_minutes'] == [5, 15, 30, 45, 60]
    assert client.post('/api/demo-mode/update', json={'remind_minutes': 5}).status_code == 200
    assert heartbeat(client)['time_up'] is False
    assert client.post('/api/demo-mode/update', json={'extend_minutes': 20}).status_code == 400
    extended = client.post('/api/demo-mode/update', json={'extend_minutes': 15}).json()['demo']
    assert datetime.fromisoformat(extended['expected_end']) > datetime.now(timezone.utc) + timedelta(minutes=14)
    assert events('demo_mode_extended') and events('demo_mode_reminder_postponed')


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def unit(users, sessions):
    clock = FakeClock()
    stored = {'value': None}
    ended, logged = [], []
    mode = demo.DemoMode(load=lambda: stored['value'], save=lambda value: stored.update(value=value), users=lambda: users,
                         session_usernames=lambda: sessions, end_sessions=ended.append,
                         log=lambda username, action, details: logged.append((username, action, details)), clock=clock)
    return mode, clock, ended, logged


def account(username, role):
    return {'username': username, 'role': role, 'active': 1, 'first_name': '', 'last_name': ''}


def test_a_warned_user_is_signed_out_at_most_five_minutes_later_or_when_its_pages_close():
    users = [account('ADMIN01', 'admin'), account('EUSER01', 'user'), account('EUSER02', 'user')]
    mode, clock, ended, logged = unit(users, ['EUSER01', 'EUSER02'])
    mode.heartbeat('EUSER01', 'user', session='s1', tab='t')
    mode.heartbeat('EUSER02', 'user', session='s2', tab='t', unsaved=['Report'])
    mode.start('ADMIN01', 'admin', expected_end=in_minutes(60), message=None, users=[])
    assert mode.state()['message'] == demo.DEFAULT_MESSAGE
    assert mode.check_request('EUSER01', 'user')
    for _step in range(5):
        clock.now += (demo.SIGN_OUT_GRACE_SECONDS - 1) / 5
        mode.heartbeat('EUSER02', 'user', session='s2', tab='t', unsaved=['Report'])
        assert 'leaving' in mode.heartbeat('EUSER01', 'user', session='s1', tab='t')
    assert mode.check_request('EUSER01', 'user')
    clock.now += 2
    assert not mode.check_request('EUSER01', 'user') and ended == ['EUSER01']
    # A user still saving is not signed out by the time, only once its pages are closed.
    assert mode.check_request('EUSER02', 'user')
    clock.now += demo.PAGE_CLOSED_SECONDS + 1
    mode.sweep()
    assert ended == ['EUSER01', 'EUSER02']
    assert [details['reason'] for _user, action, details in logged if action == 'demo_mode_user_signed_out'] == ['warning_time_over', 'pages_closed']


def test_the_demo_outlives_a_restart_and_never_ends_by_itself():
    users = [account('ADMIN01', 'admin')]
    mode, clock, _ended, _logged = unit(users, [])
    mode.start('ADMIN01', 'admin', expected_end=in_minutes(1), message='x', users=[])
    stored = mode._load()
    again = demo.DemoMode(load=lambda: stored, save=lambda value: None, users=lambda: users, session_usernames=lambda: [],
                          end_sessions=lambda username: None, log=lambda *args: None, clock=clock,
                          now=lambda: datetime.now(timezone.utc) + timedelta(hours=3))
    assert again.active and again.public_info()['overdue'] is True


def test_admins_are_told_which_users_are_online(accounts):
    client = accounts
    login(client, 'EUSER01', 'Secret123')
    assert 'online' not in heartbeat(client)
    login(client, 'super', 'super123')
    assert heartbeat(client, tab='super-tab')['online'] == ['euser01', 'super']
    page = client.get('/super-admin')
    assert 'data-user-online="euser01"' in page.text and page.text.count('class="user-online-dot"') == len(core.repository.list_users())
