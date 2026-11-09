"""A mirror of another installation (``DRIVETEST_ANALYZER_MIRROR_OF``, kept with tools/mirror): it starts no schedules of
its own, sends no emails and says on every page that it is a synchronized copy."""
from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import src.DriveTestAnalyzer as app_module
from conftest import _copy_client_workspace, _prepare_client_folders
from src.modules.core import email_delivery
from src.version import __version__

MIRROR_NOTICE = 'Mirror of the development Mac.</strong> This server is a synchronized copy of it'


def test_ordinary_server_starts_its_schedulers(client) -> None:
    assert sorted(thread.name for thread in app_module.SCHEDULER_THREADS) == ['recurring-backup-scheduler', 'reporting-jobs-scheduler']
    assert all(thread.is_alive() for thread in app_module.SCHEDULER_THREADS)
    assert client.get('/healthz').json() == {'status': 'ok', 'version': __version__}
    assert 'mirror-notice' not in client.get('/login').text


def test_mirror_keeps_no_schedules_and_sends_no_emails(tmp_path, monkeypatch, client_workspace_template) -> None:
    monkeypatch.setenv('DRIVETEST_ANALYZER_MIRROR_OF', ' the  development Mac ')
    _copy_client_workspace(client_workspace_template, tmp_path)
    _prepare_client_folders(tmp_path, monkeypatch, create=False)
    with TestClient(app_module.app) as client:
        assert app_module.STARTUP_READY.wait(timeout=300), 'The workspace of the test was not ready.'
        # No recurring backups and no Reporting schedules; the idle tasks (caches, presentations) run as anywhere.
        assert app_module.SCHEDULER_THREADS == []
        assert any(thread.name == 'idle-tasks' and thread.is_alive() for thread in threading.enumerate())
        assert client.get('/healthz').json() == {'status': 'ok', 'version': __version__, 'mirror_of': 'the development Mac'}
        # The notice is on the login page and, signed in, on every page.
        assert MIRROR_NOTICE in client.get('/login').text
        assert client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False).status_code == 303
        assert MIRROR_NOTICE in client.get('/documents/view/help').text
    with pytest.raises(RuntimeError, match='mirror of the development Mac: it sends no emails'):
        email_delivery.send_email(
            {'configured': True, 'transport': 'webhook', 'webhook_url': 'https://flow.example/trigger'},
            ['someone@example.com'], 'Subject', 'text', '<p>html</p>',
        )


def test_mirror_of_file_names_the_mirror_without_an_environment_variable(tmp_path, monkeypatch) -> None:
    """A server started without environment variables (the macOS launcher) is a mirror by a file of its configuration folder."""
    from src import config

    monkeypatch.delenv('DRIVETEST_ANALYZER_MIRROR_OF', raising=False)
    configured_dir = config.settings.config_dir
    object.__setattr__(config.settings, 'config_dir', tmp_path)
    try:
        assert config.mirror_of() == ''
        (tmp_path / 'mirror-of').write_text('  the development\n Mac \n', encoding='utf-8')
        assert config.mirror_of() == 'the development Mac'
        # The environment variable, when set, names the mirror.
        monkeypatch.setenv('DRIVETEST_ANALYZER_MIRROR_OF', 'the office server')
        assert config.mirror_of() == 'the office server'
    finally:
        object.__setattr__(config.settings, 'config_dir', configured_dir)
