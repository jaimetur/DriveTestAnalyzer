"""The leftovers of interrupted imports, exports, transfers, backups and uploads are removed once nothing uses them."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import src.DriveTestAnalyzer as core


def _age(path: Path, hours: float) -> None:
    """Make a file, or a folder and everything in it, look untouched for ``hours``."""
    moment = time.time() - hours * 3600
    for item in [path, *path.rglob('*')] if path.is_dir() else [path]:
        os.utime(item, (moment, moment))


def test_stale_leftovers_are_removed_and_recorded(client, tmp_path, monkeypatch):
    system_temp = tmp_path / 'system-temp'
    system_temp.mkdir()
    monkeypatch.setattr(core.tempfile, 'gettempdir', lambda: str(system_temp))
    # An import killed long ago, and one running now.
    stale_import = system_temp / 'drivetest-analyzer-import-old'
    (stale_import / 'workspace').mkdir(parents=True)
    (stale_import / 'workspace' / 'database.sqlite').write_bytes(b'x' * 2048)
    _age(stale_import, 30)
    fresh_import = system_temp / 'drivetest-analyzer-import-new'
    fresh_import.mkdir()
    (fresh_import / 'part').write_bytes(b'x')
    # The snapshot of an export killed while it was being made.
    package_dir = core.export_package_dir()
    package_dir.mkdir(parents=True, exist_ok=True)
    stale_snapshot = package_dir / 'drivetest-analyzer-export-old'
    stale_snapshot.mkdir()
    (stale_snapshot / 'snapshot.db').write_bytes(b'x' * 4096)
    _age(stale_snapshot, 30)
    # A backup killed mid-write in the backup folder.
    backup_root = core.recurring_backup_path(core.recurring_backup_settings())
    backup_root.mkdir(parents=True, exist_ok=True)
    partial = backup_root / '.drivetest-analyzer-backup-20261018-030016.zip.partial'
    partial.write_bytes(b'x' * 100)
    _age(partial, 30)
    # Temporary files of the caches of a workspace, never those of its Input folder.
    workspace = core.active_workspace
    cache_leftover = workspace.database_path.parent / '.design-data-cache' / 'frames' / 'model.abc.tmp'
    cache_leftover.parent.mkdir(parents=True, exist_ok=True)
    cache_leftover.write_bytes(b'x')
    _age(cache_leftover, 30)
    input_file = workspace.input_dir / 'upload.tmp'
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_bytes(b'x')
    _age(input_file, 30)
    fresh_cache = workspace.database_path.parent / '.design-data-cache' / 'frames' / 'writing.tmp'
    fresh_cache.write_bytes(b'x')

    removed = {path for path, _size in core.remove_stale_leftovers()}
    assert {str(stale_import), str(stale_snapshot), str(partial), str(cache_leftover)} <= removed
    assert not stale_import.exists() and not stale_snapshot.exists() and not partial.exists() and not cache_leftover.exists()
    assert fresh_import.exists() and input_file.exists() and fresh_cache.exists()
    [event] = [row for row in core.repository.list_logs(limit=20) if row['action'] == 'remove_stale_leftovers']
    details = json.loads(event['details'])
    assert {item['path'] for item in details['removed']} == removed and details['freed']


def test_temporary_folders_stay_while_long_work_runs(client, tmp_path, monkeypatch):
    system_temp = tmp_path / 'system-temp'
    system_temp.mkdir()
    monkeypatch.setattr(core.tempfile, 'gettempdir', lambda: str(system_temp))
    stale_restore = system_temp / 'drivetest-analyzer-restore-old'
    stale_restore.mkdir()
    (stale_restore / 'payload').write_bytes(b'x')
    _age(stale_restore, 30)
    monkeypatch.setitem(core.MANUAL_RESTORE_JOBS, 'running', {'status': 'processing'})
    core.remove_stale_leftovers()
    assert stale_restore.exists()


def test_the_cleanup_runs_once_a_night_while_the_server_is_idle(client, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(core, 'remove_stale_leftovers', lambda: calls.append(1) or [])
    core.repository.delete_application_state(core.LEFTOVER_CLEANUP_STATE_KEY)
    # The idle monitor calls it only after a quarter of an hour without anyone using the application.
    assert (core.LEFTOVER_CLEANUP_IDLE_SECONDS, core._remove_leftovers_when_idle) in core.IDLE_TASK_CALLBACKS

    # Seen first by day: nothing yet, the night comes first.
    assert not core.run_leftover_cleanup_if_due(datetime(2026, 10, 21, 14, 0))
    # Once a night, not while long work runs.
    monkeypatch.setitem(core.MANUAL_RESTORE_JOBS, 'running', {'status': 'processing'})
    assert not core.run_leftover_cleanup_if_due(datetime(2026, 10, 22, 2, 0))
    core.MANUAL_RESTORE_JOBS.pop('running')
    assert core.run_leftover_cleanup_if_due(datetime(2026, 10, 22, 2, 30))
    assert not core.run_leftover_cleanup_if_due(datetime(2026, 10, 22, 6, 59))
    assert not core.run_leftover_cleanup_if_due(datetime(2026, 10, 22, 7, 0))
    assert core.run_leftover_cleanup_if_due(datetime(2026, 10, 23, 0, 5))
    # A server busy or off every night is cleaned at any hour once two days pass without a cleanup.
    assert not core.run_leftover_cleanup_if_due(datetime(2026, 10, 24, 18, 0))
    assert core.run_leftover_cleanup_if_due(datetime(2026, 10, 25, 12, 0))
    assert calls == [1, 1, 1]
