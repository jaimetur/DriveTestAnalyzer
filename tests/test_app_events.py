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
