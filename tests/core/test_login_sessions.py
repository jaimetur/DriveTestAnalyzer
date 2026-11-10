"""Login sessions: they outlive a restart of the application for 90 days and end when they must."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

import src.DriveTestAnalyzer as core


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303
    return response


def restart():
    core.SESSIONS.clear()
    core.SESSION_CHECKS.clear()


def signed_in(client):
    return client.get('/workspace', follow_redirects=False).status_code == 200


def token_of(client):
    return client.cookies.get(core.SESSION_COOKIE)


def stored(token):
    return core.repository.login_session(hashlib.sha256(token.encode()).hexdigest())


def test_a_login_outlives_a_restart_for_90_days_and_keeps_only_the_hash_of_its_token(client):
    response = login(client)
    assert 'max-age=7776000' in response.headers['set-cookie'].casefold()
    token = token_of(client)
    row = stored(token)
    assert row['username'] == 'super' and token not in dict(row).values()
    assert datetime.fromisoformat(row['expires_at']) - datetime.fromisoformat(row['created_at']) == timedelta(days=90)
    marker = core.SESSIONS[token].session_marker
    restart()
    assert signed_in(client)
    assert core.SESSIONS[token].session_marker == marker

    # A session that expired ends.
    with core.repository.global_connection() as connection:
        connection.execute('UPDATE user_login_sessions SET expires_at = ?', ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec='seconds'),))
    restart()
    assert not signed_in(client) and stored(token) is None


def test_signing_out_ends_the_session_also_after_a_restart(client):
    login(client)
    token = token_of(client)
    client.get('/logout', follow_redirects=False)
    assert stored(token) is None
    restart()
    client.cookies.set(core.SESSION_COOKIE, token)
    assert not signed_in(client)


def test_a_session_follows_its_user_role_and_active_state(client, monkeypatch):
    login(client)
    created = core.repository.create_user('EUSER01', 'Secret123', 'user-viewer')
    login(client, 'EUSER01', 'Secret123')
    token = token_of(client)
    assert core.session_user(token).role == 'user-viewer'
    core.repository.update_user(created, 'EUSER01', 'admin', True)
    monkeypatch.setattr(core, 'SESSION_CHECK_SECONDS', -1.0)
    assert core.session_user(token).role == 'admin'
    core.repository.update_user(created, 'EUSER01', 'admin', False)
    assert core.session_user(token) is None and stored(token) is None


@pytest.mark.parametrize('how', ['change', 'reset'])
def test_a_new_password_ends_the_other_sessions(client, how):
    login(client)
    core.repository.create_user('EUSER02', 'Secret123', 'user-viewer')
    target = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'EUSER02')
    login(client, 'EUSER02', 'Secret123')
    other = token_of(client)
    login(client, 'EUSER02', 'Secret123')
    current = token_of(client)
    if how == 'change':
        assert client.post('/account/change-password', data={'current_password': 'Secret123', 'new_password': 'Secret456', 'new_password_confirmation': 'Secret456'}).status_code == 200
        assert core.session_user(current) is not None and stored(current) is not None
    else:
        login(client)
        assert client.post(f'/admin/users/{target}/reset-password', follow_redirects=False).status_code == 303
        assert stored(current) is None
    assert stored(other) is None and core.session_user(other) is None


def test_the_login_page_opens_the_application_when_already_signed_in(client):
    assert client.get('/login', follow_redirects=False).status_code == 200
    login(client)
    opened = client.get('/login', follow_redirects=False)
    assert opened.status_code == 303 and opened.headers['location'] == '/documents/view/help'
    assert client.get('/login?next=/tickets', follow_redirects=False).headers['location'] == '/tickets'
    # It also opens after a restart, without a new session.
    restart()
    with core.repository.global_connection() as connection:
        before = connection.execute('SELECT COUNT(*) FROM user_login_sessions').fetchone()[0]
    assert client.get('/login', follow_redirects=False).status_code == 303
    with core.repository.global_connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM user_login_sessions').fetchone()[0] == before
    client.get('/logout', follow_redirects=False)
    assert client.get('/login', follow_redirects=False).status_code == 200

