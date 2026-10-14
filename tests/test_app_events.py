"""User actions written to the App Events of the active workspace."""
from __future__ import annotations

import json
import time

import pytest

import src.DriveTestAnalyzer as core
from src.modules.scoring_reports import default_scenario
from tests.test_app import login, login_super
from tests.test_nq_analysis_center import setup_calls


def events(action: str) -> list[dict]:
    """The details of the App Events of one action, oldest first."""
    rows = [row for row in core.repository.list_logs() if row['action'] == action]
    return [json.loads(row['details']) for row in sorted(rows, key=lambda row: row['id'])]


def test_deleting_a_workspace_is_recorded_in_the_open_workspace(client) -> None:
    login(client)
    removed = core.workspace_registry.create('Removed workspace')
    admin = next(row for row in core.repository.list_users() if row['username'] == 'admin')
    core.repository.set_user_workspace_access(int(admin['id']), [removed.id])

    deleted = client.post('/workspace/delete', data={'workspace_id': removed.id}, follow_redirects=False)

    assert deleted.status_code == 303
    assert events('delete_workspace') == [{'workspace': removed.id, 'name': 'Removed workspace', 'delete_files': False}]


def test_creating_a_backup_folder_is_recorded(client) -> None:
    login(client)
    parent = client.get('/api/admin/backup-directories').json()['path']

    created = client.post('/api/admin/backup-directories', data={'parent_path': parent, 'name': 'audited-folder'})

    assert created.status_code == 200
    assert events('create_backup_directory') == [{'path': created.json()['path']}]


def test_export_package_jobs_record_their_request_outcome_and_download(client) -> None:
    login_super(client)
    started = client.post('/admin/import-export/export/jobs', data={'export_target': 'config'})
    assert started.status_code == 200
    payload = {}
    for _ in range(200):
        payload = client.get(started.json()['status_url']).json()
        if payload['status'] in {'ready', 'failed'}:
            break
        time.sleep(0.01)
    assert payload['status'] == 'ready'
    assert client.get(payload['download_url']).status_code == 200

    job_id = started.json()['job_id']
    assert [event['job_id'] for event in events('export_package_queued')] == [job_id]
    completed = events('export_package_completed')
    assert completed[0]['job_id'] == job_id and completed[0]['executed_by'] == 'system'
    assert events('download_export_package') == [{'job_id': job_id, 'file': payload['filename']}]


def test_scoring_report_configuration_changes_are_recorded(client) -> None:
    login(client)
    configuration = {'scenarios': [default_scenario(name='National', operators=['Three UK'])]}

    assert client.post('/api/scoring/report-configurations', json={'name': 'Audited', 'configuration': configuration}).status_code == 200
    exported = client.get('/api/scoring/report-configurations/export')
    assert client.delete('/api/scoring/report-configurations?name=Audited').status_code == 200
    imported = client.post('/api/scoring/report-configurations/import',
                           files={'package': ('reports.json', exported.content, 'application/json')})
    assert imported.status_code == 200

    assert events('save_scoring_report_configuration') == [{'name': 'Audited'}]
    assert events('delete_scoring_report_configuration') == [{'name': 'Audited'}]
    assert events('export_scoring_report_configurations')[0]['configurations'] == len(exported.json()['configurations'])
    assert events('import_scoring_report_configurations') == [{'file': 'reports.json', 'replace': False}]


def test_report_template_export_is_recorded(client) -> None:
    login(client)

    exported = client.get('/workspace-config/report-templates/nsa/export')

    assert exported.status_code == 200
    assert [event['technology'] for event in events('export_report_template')] == ['nsa']


@pytest.fixture()
def indexing_runs_at_once(monkeypatch):
    monkeypatch.setattr(core, 'submit_background_task', lambda callback, *args: callback(*args))


def test_nq_analysis_center_actions_are_recorded(client, tmp_path, indexing_runs_at_once) -> None:
    calls = setup_calls(client, tmp_path)
    call = calls['0xA1']

    assert client.patch(f"/api/non-qualified-calls/calls/{call['call_key']}",
                        json={'changes': {'status': 'Under Planning'}}).status_code == 200
    keys = [item['call_key'] for item in calls.values()]
    assert client.post('/api/non-qualified-calls/calls/bulk', json={'call_keys': keys, 'changes': {'team': 'Operations'}}).status_code == 200
    comment = client.post(f"/api/non-qualified-calls/calls/{call['call_key']}/comments", json={'body': 'Traces requested.'}).json()['comment']
    assert client.patch(f"/api/non-qualified-calls/comments/{comment['id']}", json={'body': 'Traces received.'}).status_code == 200
    assert client.delete(f"/api/non-qualified-calls/comments/{comment['id']}").status_code == 200
    assert client.post('/api/non-qualified-calls/export', json={'filters': {}}).status_code == 200
    assert client.get('/api/non-qualified-calls/catalog/export').status_code == 200

    assert events('nq_call_update') == [{'call_key': call['call_key'], 'fields': ['status']}]
    bulk = events('nq_calls_bulk_update')
    assert bulk[0]['selected'] == len(keys) and bulk[0]['fields'] == ['team']
    assert events('nq_comment_add') == [{'call_key': call['call_key'], 'comment_id': comment['id']}]
    assert events('nq_comment_edit') == [{'comment_id': comment['id']}]
    assert events('nq_comment_delete') == [{'comment_id': comment['id']}]
    assert len(events('nq_calls_export')) == 1
    assert len(events('nq_catalog_export')) == 1


def test_app_events_export_import_and_back_up_on_their_own(client) -> None:
    import io
    import zipfile

    login_super(client)
    with core.repository.connection() as conn:
        conn.execute('DELETE FROM audit_logs')
        conn.executemany('INSERT INTO audit_logs (username, action, details, created_at) VALUES (?, ?, ?, ?)', [
            ('ana', 'first_event', '{}', '2026-10-01T10:00:00.000000+02:00'),
            ('bob', 'second_event', '{"n": 2}', '2026-10-02T10:00:00.000000+02:00'),
        ])
    package, filename = core.build_export_archive('app-events')
    assert filename.endswith('.zip') and '_app-events_' in filename
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        document = json.loads(archive.read(manifest['archive_path']))
    assert manifest['kind'] == 'app-events' and manifest['workspace_components'] == ['app_events']
    assert [event['action'] for event in document['events'][:2]] == ['first_event', 'second_event']

    # Imported into the workspace, only the events it does not have are added, among the others by their time.
    with core.repository.connection() as conn:
        conn.execute("DELETE FROM audit_logs WHERE action = 'first_event'")
    workspace = core.workspace_registry.get(core.active_workspace.id)
    payload = json.dumps(document).encode('utf-8')
    assert core._restore_workspace_app_events(workspace, payload) == 1
    assert core._restore_workspace_app_events(workspace, payload) == 0
    by_time = [row['action'] for row in core.repository.list_logs(limit=None, by_time=True)]
    assert by_time.index('second_event') < by_time.index('first_event')
    inspected = client.post('/admin/import-export/inspect/upload', content=package, headers={'X-Import-File-Name': 'events.zip'})
    assert inspected.status_code == 200 and inspected.json()['kind'] == 'app-events' and inspected.json()['requires_destination_workspaces']

    # Backed up and restored on their own.
    archive_path = core.create_recurring_database_backup({
        'components': ['app_events'], 'backup_path': str(core.application_data_dir / 'scheduled-backups'),
        'max_backups': 30, 'workspace_ids': [core.active_workspace.id],
    })
    assert core._backup_archive_components(archive_path) == ['app_events']
    with core.repository.connection() as conn:
        conn.execute("DELETE FROM audit_logs WHERE action IN ('first_event', 'second_event')")
    core.restore_database_backup(archive_path, ['app_events'])
    assert {'first_event', 'second_event'} <= {row['action'] for row in core.repository.list_logs(limit=None)}
