"""Scheduled backups: light ones between weekly full ones, in their own folders, kept by days, weeks and months, and no
backup started without room."""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

import src.DriveTestAnalyzer as core


def login_super(client) -> None:
    response = client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    assert response.status_code == 303


def _backup(root: Path, started: str, origin: str | None = 'scheduled', level: str | None = 'full') -> Path:
    """A backup ZIP started at ``started`` (YYYYmmdd-HHMMSS) with the origin and level its manifest records."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'drivetest-analyzer-backup-{started}.zip'
    manifest = {'format': core.ARCHIVE_FORMAT, 'kind': 'database-backup', 'components': ['app_database']}
    if origin:
        manifest |= {'backup_origin': origin, 'backup_level': level}
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
    return path


def test_backups_record_their_origin_and_level(client):
    login_super(client)
    # Backup folders must be inside the application data folder.
    tmp_path = core.application_data_dir / 'test-backups'
    workspace = core.active_workspace
    config = {'components': ['app_database', 'workspace_database', 'dashboards'], 'workspace_ids': [workspace.id],
              'backup_path': str(tmp_path)}
    # Renamed as made: two backups started in the same second would have the same name.
    light = core.create_recurring_database_backup(config, origin='scheduled', level='light')
    assert light.parent == tmp_path / 'light'
    light = light.rename(light.with_name('drivetest-analyzer-backup-20980101-000000.zip'))
    with zipfile.ZipFile(light) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        names = archive.namelist()
    assert (manifest['backup_origin'], manifest['backup_level']) == ('scheduled', 'light')
    assert 'workspace_database' not in manifest['workspace_components'] and 'dashboards' in manifest['workspace_components']
    assert not any(name.endswith('/database.sqlite') for name in names)

    full = core.create_recurring_database_backup(config)
    assert full.parent == tmp_path / 'full'
    full = full.rename(full.with_name('drivetest-analyzer-backup-20990101-000000.zip'))
    with zipfile.ZipFile(full) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert any(name.endswith('/database.sqlite') for name in archive.namelist())
    assert (manifest['backup_origin'], manifest['backup_level']) == ('manual', 'full')
    old = _backup(tmp_path, '20200101-000000', origin=None)

    files = client.get('/api/admin/backup-files', params={'backup_path': str(tmp_path)}).json()['files']
    assert {item['path']: (item['origin'], item['level']) for item in files} == {
        f'light/{light.name}': ('scheduled', 'light'), f'full/{full.name}': ('manual', 'full'),
        # Backups made before, in the backup folder itself, count as scheduled full ones.
        old.name: ('scheduled', 'full'),
    }
    # Restore finds each backup by its path in the backup folder.
    inspected = client.post('/api/admin/backup-files/inspect', data={'backup_path': str(tmp_path), 'backup_file': f'full/{full.name}'})
    assert 'workspace_database' in inspected.json()['components']
    with pytest.raises(ValueError):
        core._backup_archive_file(str(tmp_path), f'other/{full.name}')


def test_light_backups_are_made_between_weekly_full_ones(client, tmp_path):
    config = core.recurring_backup_settings() | {
        'enabled': True, 'recurrence': 'daily', 'light_backups': True, 'full_backup_day': 6,
        'components': ['app_database', 'workspace_database'], 'backup_path': str(tmp_path),
    }
    level = core.scheduled_backup_level
    # The first backup is full; then light until the full-backup day (Sunday).
    assert level(config, datetime(2026, 10, 17, 5, 0)) == 'full'
    _backup(tmp_path / 'full', '20261018-050000')
    assert level(config, datetime(2026, 10, 19, 5, 0)) == 'light'
    assert level(config, datetime(2026, 10, 24, 5, 0)) == 'light'
    assert level(config, datetime(2026, 10, 25, 5, 0)) == 'full'
    # One full backup that day, the first, for hourly and every 4 hours schedules.
    _backup(tmp_path / 'full', '20261025-050000')
    assert level(config | {'recurrence': 'hourly'}, datetime(2026, 10, 25, 6, 0)) == 'light'
    assert level(config | {'recurrence': 'every_4_hours'}, datetime(2026, 10, 25, 9, 0)) == 'light'
    # A full backup missed is made at the next backup.
    (tmp_path / 'full' / 'drivetest-analyzer-backup-20261025-050000.zip').unlink()
    assert level(config, datetime(2026, 10, 26, 5, 0)) == 'full'
    # Weekly and monthly schedules, light backups off, or nothing heavy selected: always full.
    assert level(config | {'recurrence': 'weekly'}, datetime(2026, 10, 19, 5, 0)) == 'full'
    assert level(config | {'light_backups': False}, datetime(2026, 10, 19, 5, 0)) == 'full'
    assert level(config | {'components': ['app_database', 'dashboards']}, datetime(2026, 10, 19, 5, 0)) == 'full'


def test_retention_keeps_the_backups_of_the_last_days_weeks_and_months(client, tmp_path):
    full = ['20260405', '20260426', '20260510', '20260531', '20260628', '20260726', '20260830',
            '20260906', '20260927', '20261004', '20261011', '20261018']
    light = ['20260928', '20261012', '20261019', '20261020', '20261021']
    for day in full:
        _backup(tmp_path / 'full', f'{day}-050000')
    for day in light:
        _backup(tmp_path / 'light', f'{day}-050000', level='light')
    _backup(tmp_path, '20260301-050000', origin=None)
    manual = _backup(tmp_path / 'full', '20260101-120000', origin='manual')
    config = {'backup_path': str(tmp_path), 'keep_days': 3, 'keep_weeks': 4, 'keep_months': 6}

    def retain(now: datetime) -> set[str]:
        return {Path(path).name[26:34] for path, _size in core.apply_scheduled_backup_retention(config, now)}

    def remaining() -> set[str]:
        return {path.name[26:34] for path in tmp_path.rglob('*.zip')}

    # On Wednesday 21 October: every backup since Monday, and the newest full one of each week since 28 September and
    # of each month since May; the backups of Backup Now stay.
    assert retain(datetime(2026, 10, 21, 6, 0)) == {'20260928', '20261012', '20260906', '20260510', '20260426', '20260405', '20260301'}
    assert manual.is_file()
    assert remaining() == {'20260101', '20261021', '20261020', '20261019', '20261018', '20261011', '20261004', '20260927',
                           '20260830', '20260726', '20260628', '20260531'}
    # A month later, with no backups since: the weeks and months that have passed no longer keep theirs, and the
    # newest full backup stays.
    assert retain(datetime(2026, 11, 20, 6, 0)) == {'20261019', '20261020', '20261021', '20261011', '20261004', '20260531'}
    assert remaining() == {'20260101', '20261018', '20260927', '20260830', '20260726', '20260628'}


def test_every_4_hours_and_the_days_kept_by_earlier_schedules(client):
    config = {'enabled': True, 'recurrence': 'every_4_hours', 'execution_time': '01:30'}
    assert core._recurring_backup_period(config, datetime(2026, 10, 21, 5, 30)) == '2026102105'
    assert core._recurring_backup_period(config, datetime(2026, 10, 21, 6, 30)) is None
    assert core._recurring_backup_period(config, datetime(2026, 10, 21, 5, 31)) is None
    assert int(core.recurring_backup_next_run(config)[11:13]) % 4 == 1
    # Schedules that kept a number of backups keep the days those backups covered.
    for saved, days in (({'recurrence': 'hourly', 'max_backups': 50}, 3), ({'recurrence': 'daily', 'max_backups': 3}, 3),
                        ({'recurrence': 'weekly', 'max_backups': 2}, 14)):
        core.repository.set_application_state(core.RECURRING_BACKUP_STATE_KEY, json.dumps(saved))
        assert core.recurring_backup_settings()['keep_days'] == days


def test_a_backup_without_room_is_not_started(client, tmp_path, monkeypatch):
    tmp_path = tmp_path / 'backups'
    monkeypatch.setattr(core, 'available_disk_space', lambda _path: 10)
    config = {'components': ['app_database'], 'workspace_ids': [], 'backup_path': str(tmp_path)}
    try:
        core.create_recurring_database_backup(config)
    except core.BackupSpaceError as exc:
        assert exc.free == 10 and exc.needed > 10 and 'Not enough free space' in str(exc)
    else:
        raise AssertionError('The backup started without room for it.')
    assert not [path for path in tmp_path.rglob('*') if path.is_file()]


def _run_scheduler(monkeypatch, config, create):
    def run_immediately(callback, *args):
        callback(*args)

    monkeypatch.setattr(core, 'recurring_backup_settings', lambda: dict(config))
    monkeypatch.setattr(core, 'create_recurring_database_backup', create)
    monkeypatch.setattr(core, 'submit_background_task', run_immediately)
    monkeypatch.setattr(core, 'RECURRING_BACKUP_RUNNING', False)
    monkeypatch.setattr(core, '_recurring_backup_period', lambda _config, _now: 'test-period')
    core.run_recurring_backup_scheduler()


def test_the_schedule_records_why_a_backup_was_not_made(client, tmp_path, monkeypatch):
    login_super(client)
    config = core.recurring_backup_settings() | {
        'enabled': True, 'recurrence': 'hourly', 'last_run_period': '',
        'components': ['app_database', 'workspace_database'], 'backup_path': str(tmp_path), 'light_backups': False,
    }
    no_room = core.BackupSpaceError(50 * 1024 ** 3, 20 * 1024 ** 3, tmp_path)

    def full_needs_room(_config, *_args, level='full', **_kwargs):
        if level == 'full':
            raise no_room
        return _backup(tmp_path, datetime.now().strftime('%Y%m%d-%H%M%S'), level='light')

    _run_scheduler(monkeypatch, config, full_needs_room)
    [failed] = [row for row in core.repository.list_logs(limit=20) if row['action'] == 'scheduled_database_backup_failed']
    assert json.loads(failed['details'])['free'] == '20 GB'
    status = client.get('/api/admin/backup-status').json()
    assert 'Full backup not made: Not enough free space' in status['problem']

    # With light backups on, a full backup without room is made light, and the panel says so.
    _run_scheduler(monkeypatch, config | {'light_backups': True}, full_needs_room)
    actions = [row['action'] for row in core.repository.list_logs(limit=20)]
    assert 'scheduled_full_backup_made_light' in actions and 'scheduled_database_backup_completed' in actions
    assert 'Full backup made light' in client.get('/api/admin/backup-status').json()['problem']

    # A backup made as configured clears the problem.
    _run_scheduler(monkeypatch, config, lambda *_args, **_kwargs: _backup(tmp_path, '20990101-000000'))
    assert client.get('/api/admin/backup-status').json()['problem'] == ''
    # The size of the latest scheduled full and light backups, for the panel to estimate the space of those kept.
    sizes = client.get('/api/admin/backup-status').json()['latest_sizes']
    assert sizes['full'] == (tmp_path / 'drivetest-analyzer-backup-20990101-000000.zip').stat().st_size and sizes['light'] > 0


def test_scheduled_backup_tiers_are_saved(client):
    login_super(client)
    saved = client.post('/admin/database/backups', data={
        'enabled': 'true', 'components': ['app_database'], 'recurrence': 'every_4_hours', 'execution_time': '05:00',
        'weekly_day': '0', 'monthly_day': '1', 'light_backups': 'true', 'full_backup_day': '0',
        'keep_days': '2', 'keep_weeks': '5', 'keep_months': '12', 'backup_path': 'scheduled-backups',
    }, follow_redirects=False)
    assert saved.status_code == 303
    config = core.recurring_backup_settings()
    assert (config['recurrence'], config['light_backups'], config['full_backup_day'], config['keep_days'],
            config['keep_weeks'], config['keep_months']) == ('every_4_hours', True, 0, 2, 5, 12)
    [event] = [row for row in core.repository.list_logs(limit=20) if row['action'] == 'save_scheduled_backup_settings']
    assert json.loads(event['details'])['keep_weeks'] == 5
    page = client.get('/super-admin').text
    assert 'Every 4 hours' in page and 'Days to keep' in page and 'Months to keep' in page and 'data-backup-restore-type' in page


def test_backup_now_makes_a_full_or_a_light_backup(client, monkeypatch):
    login_super(client)
    workspace = core.active_workspace
    form = {'components': ['app_database', f'workspace:{workspace.id}', 'workspace_database', 'dashboards'],
            'backup_path': 'test-backup-now', 'backup_level': 'light'}
    monkeypatch.setattr(core, 'submit_background_task', lambda callback, *args: callback(*args))
    started = client.post('/admin/database/backups/run', data=form, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert started.status_code == 200
    job = core.MANUAL_BACKUP_JOBS[started.json()['job_id']]
    assert job['status'] == 'ready'
    [light] = (core.application_data_dir / 'test-backup-now' / 'light').glob('*.zip')
    with zipfile.ZipFile(light) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert not any(name.endswith('/database.sqlite') for name in archive.namelist())
    assert (manifest['backup_origin'], manifest['backup_level']) == ('manual', 'light')
    [event] = [row for row in core.repository.list_logs(limit=20) if row['action'] == 'start_manual_database_backup']
    assert json.loads(event['details'])['level'] == 'light'
    # A light backup of only what it leaves out has nothing to keep.
    nothing = client.post('/admin/database/backups/run', data=form | {'components': [f'workspace:{workspace.id}', 'workspace_database']},
                          headers={'X-Requested-With': 'XMLHttpRequest'})
    assert nothing.status_code == 400 and 'light backup leaves' in nothing.json()['detail']
    page = client.get('/super-admin').text
    assert 'data-backup-now-level' in page and 'data-backup-now-dialog' in page and 'data-backup-retention-maximum' in page


def test_earlier_backups_move_into_the_full_folder(client):
    root = core.recurring_backup_path(core.recurring_backup_settings())
    earlier = _backup(root, '20261016-030007', origin=None)
    clash = _backup(root, '20261017-030007', origin=None)
    _backup(root / 'full', '20261017-030007')
    light = _backup(root / 'light', '20261021-040014', level='light')

    moved = core.move_earlier_backups_to_full_folder()

    assert moved == [str((root / 'full' / earlier.name).resolve())]
    assert not earlier.exists() and (root / 'full' / earlier.name).is_file()
    # A backup of the same name already in the full folder is left where it is, and light ones stay in theirs.
    assert clash.is_file() and light.is_file()
    [event] = [row for row in core.repository.list_logs(limit=20) if row['action'] == 'move_earlier_backups_to_full_folder']
    assert json.loads(event['details'])['moved'] == moved
    assert core.move_earlier_backups_to_full_folder() == []


def test_the_tiles_tell_full_from_light_backups(client):
    login_super(client)
    root = core.application_data_dir / 'test-tiles'
    full = _backup(root / 'full', '20261018-050000')
    light = _backup(root / 'light', '20261020-050000', level='light')
    light.write_bytes(light.read_bytes() + b'x' * 2048)
    config = core.recurring_backup_settings() | {
        'enabled': True, 'backup_path': str(root), 'recurrence': 'daily', 'light_backups': True, 'full_backup_day': 6,
        'components': ['app_database', 'workspace_database'],
    }
    status = core.recurring_backup_status(config)
    assert status['count'] == 2 and status['count_detail'] == '1 full · 1 light'
    assert status['size_detail'] == f"{core.format_workspace_size(full.stat().st_size)} full · {core.format_workspace_size(light.stat().st_size)} light"
    # The newest by time is the light one; the next backup is full only on Sunday or once the latest full is a week old.
    assert status['last_level'] == 'Light backup'
    assert status['next_level'] in {'Full backup', 'Light backup'}
    assert core.recurring_backup_status(config | {'enabled': False})['next_level'] == ''
