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
    login_super(client)
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
    configuration = {'scenarios': [default_scenario(name='National')]}

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


def test_events_of_the_application_belong_to_system(client) -> None:
    from src.modules import non_qualified_calls as nq
    from src.modules.repository import PROCESS_EVENT_DETAILS

    login(client)
    imported = PROCESS_EVENT_DETAILS[('import', 'nq_table_columns')]
    # Events recorded before under the name of a process (import) move to system when the workspace opens, once.
    with core.repository.connection() as conn:
        conn.execute('DELETE FROM audit_logs')
        conn.executemany('INSERT INTO audit_logs (username, action, details, created_at) VALUES (?, ?, ?, ?)', [
            ('import', 'nq_table_columns', 'Non-Qualified Calls table columns updated.', '2026-10-09T21:03:40.179524+02:00'),
            ('admin', 'nq_table_columns', 'Non-Qualified Calls table columns updated.', '2026-10-10T10:00:00.000000+02:00'),
        ])
    core.repository.initialize()
    core.repository.initialize()
    stored = [(row['username'], row['details']) for row in sorted(core.repository.list_logs(limit=None), key=lambda row: row['id'])
              if row['action'] == 'nq_table_columns']
    assert stored == [('system', imported), ('admin', 'Non-Qualified Calls table columns updated.')]
    assert events('migrate_app_event_users') == [{'events': 1, 'users': ['import']}]
    # App Events of a package exported before come in the same way, without repeating the event.
    assert core.repository.merge_logs([{
        'username': 'import', 'action': 'nq_table_columns', 'details': 'Non-Qualified Calls table columns updated.',
        'created_at': '2026-10-09T21:03:40.179524+02:00'}]) == 0

    # The table columns of an imported Non-Qualified Calls configuration are taken by system, which says so.
    nq.ensure_nq_tables(core.repository)
    document = json.loads(nq.export_configuration_document(core.repository))
    document['table_columns'] = {'builtin': [], 'cdr': ['Call_ID']}
    with core.repository.connection() as conn:
        conn.execute('DELETE FROM workspace_state WHERE key = ?', (nq.TABLE_COLUMNS_STATE_KEY,))
        conn.execute("DELETE FROM audit_logs WHERE action = 'nq_table_columns'")
    nq.import_configuration_document(core.repository, json.dumps(document))
    assert [(row['username'], row['details']) for row in core.repository.list_logs(limit=None)
            if row['action'] == 'nq_table_columns'] == [('system', imported)]

    # App Events shows system as System, tagged application, first in the User and Executed by lists (a line before
    # the users), and in the table.
    core.repository.add_log('admin', 'change_password', 'Password changed from the account badge.')
    page = client.get('/app-logs').text
    user_filter = page.split('data-app-log-user-filter multiple', 1)[1].split('</select>', 1)[0]
    first, second = (option.split('<option', 1)[1] for option in user_filter.split('</option>')[:2])
    assert first == (' value="system" data-name="System" data-system-user="true" data-tag="application" '
                     'data-tag-class="user-choice-tag-system" data-option-class="is-system-user">System · application')
    assert 'data-divider-before="true"' in second
    assert 'value="import"' not in user_filter
    assert ('<td><span class="app-log-system-user">System <span class="user-choice-tag app-log-badge user-choice-tag-system">'
            'application</span></span></td>') in page
    assert 'Application events recorded under import now belong to System: 1.' in page


def test_app_event_details_say_what_changed_once(client) -> None:
    login_super(client)
    core.repository.create_user('ELUILEY', 'secret123', 'user-viewer')
    target = next(row for row in core.repository.list_users() if row['username'] == 'ELUILEY')
    core.repository.update_user(int(target['id']), 'ELUILEY', 'user-viewer', False)
    response = client.post(f"/admin/users/{target['id']}/update", data={'username': 'ELUILEY', 'role': 'user-editor', 'active': '1'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200, response.text
    # The event records what changed, before and after, besides the account as saved.
    updated = events('update_user')[-1]
    assert updated['changes'] == {'role': ['user-viewer', 'user-editor'], 'active': [False, True]}
    assert (updated['role'], updated['active'], updated['password_changed']) == ('user-editor', True, False)
    workspace_id = core.active_workspace.id
    group_id = core.repository.save_workspace_group(None, 'Field', '', [])
    response = client.post(f'/admin/workspace-groups/{group_id}/update', data={
        'name': 'Field team', 'workspace_ids': [workspace_id], 'member_ids': [target['id']], 'initial_member_ids': []})
    assert response.status_code == 200, response.text
    group = events('update_workspace_group')[-1]
    assert group['changes'] == {'name': ['Field', 'Field team'], 'workspaces': [[], [core.active_workspace.name]]}
    assert group['added_users'] == ['ELUILEY']
    # Events recorded before with only the final state, and plain-text ones.
    core.repository.add_log('admin', 'update_user', json.dumps({'user_id': 15, 'username': 'OLDUSER', 'role': 'user-editor', 'active': True}))
    core.repository.add_log('admin', 'nq_call_options', 'Non-Qualified Calls statuses and teams updated.')

    # App Events shows one readable sentence per event, with the raw details folded away.
    page = client.get('/app-logs').text
    sentence = 'User ELUILEY: role user-viewer → user-editor; activated.'
    assert page.count(sentence) == 1
    assert f'<p class="app-log-summary">{sentence}</p><details class="app-log-raw"><summary>Raw details</summary><code>' in page
    assert f'Workspace Group Field team: name Field → Field team; Workspaces +{core.active_workspace.name}; users +ELUILEY.' in page
    assert ('<p class="app-log-summary">User OLDUSER saved (role user-editor, active); earlier versions did not record which '
            'fields changed.</p><details class="app-log-raw">') in page
    assert '<p class="app-log-summary">Non-Qualified Calls statuses and teams updated.</p></td>' in page
    # The refresh of the table gets the same sentence.
    logs = client.get('/api/app-logs').json()['logs']
    assert next(log for log in logs if log['action'] == 'update_user' and 'ELUILEY' in log['details_text'])['description'] == sentence


def test_app_events_filters_choose_several_values(client) -> None:
    from pathlib import Path

    login(client)
    core.repository.add_log('admin', 'change_password', 'Password changed from the account badge.')
    page = client.get('/app-logs').text
    # Every filter is a multi-select list (no "all" option): none chosen shows every event.
    for name, empty in (('date', 'All dates'), ('user', 'All users'), ('executor', 'All executors'), ('type', 'All events'),
                        ('action', 'All actions')):
        control = page.split(f'<select data-app-log-{name}-filter', 1)[1].split('</select>', 1)[0]
        assert control.startswith(f' multiple size="1" data-multiselect-empty-label="{empty}"')
        assert 'value="all"' not in control
    assert '<option value="change_password">change_password</option>' in page
    # The person who triggered each event: the column and its filter.
    assert '<th>Triggered by</th><th>Executed by</th>' in page and '<label>Triggered by\n' in page
    # An action wraps only at its underscores; the date shows its time as a badge below.
    assert '<td>change_<wbr>password</td>' in page
    # Every badge of the table (the time, the username or application, where it ran) has one size.
    css = (Path(core.__file__).parent / 'web_interface' / 'static' / 'css' / 'app.css').read_text(encoding='utf-8')
    assert '.app-logs-table .user-choice-tag.app-log-badge { font-size: var(--app-log-badge-size);' in css
    # The time in green, like the default user tag, its digits a little larger in a box as high as the other badges.
    assert '.app-logs-table .user-choice-tag.app-log-badge.user-choice-tag-time { font-size: calc(var(--app-log-badge-size) * 1.16);' in css
    assert '.user-choice-tag.user-choice-tag-time { border-color: #a8dccf; background: #e3f4f0; color: #0b6b66;' in css
    assert '<td class="app-log-date"><span class="app-log-when">20' in page and '<span class="user-choice-tag app-log-badge user-choice-tag-time">' in page


def test_an_open_app_events_filter_list_keeps_its_menu_while_the_table_refreshes() -> None:
    from pathlib import Path

    script = (Path(core.__file__).parent / 'web_interface' / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
    # The refresh does not rebuild a list while it is open: its new values wait until it closes.
    assert 'if (filterListOpen(control)) {\n      pendingFilterOptions.set(control, options);\n      return;\n    }' in script
    assert 'pendingFilterOptions.forEach((options, control) => { if (!filterListOpen(control)) setFilterOptions(control, options); });' in script


def test_every_field_changed_in_a_user_is_recorded_once_per_save(client) -> None:
    login_super(client)
    workspace = core.active_workspace
    profiles = {profile['name']: profile['id'] for profile in core.repository.list_modules_profiles()}
    first_profile, second_profile = list(profiles)[:2]
    group_id = core.repository.save_workspace_group(None, 'Field', '', [workspace.id])
    # A user created: the account as it was created, never its password.
    created = client.post('/admin/users', data={
        'username': 'MARTA', 'password': 'secret123', 'role': 'user-viewer', 'first_name': 'Marta',
        'modules_profile_id': str(profiles[first_profile])}, follow_redirects=False)
    assert created.status_code == 303, created.text
    account = events('create_user')[-1]
    assert (account['username'], account['first_name'], account['role'], account['active'], account['modules_profile']) == (
        'MARTA', 'Marta', 'user-viewer', True, first_profile)
    assert 'secret123' not in json.dumps(account)
    target_id = account['user_id']
    # One save changing the names, the Modules Profile, the Workspace Groups and the password: one event with each change.
    response = client.post(f'/admin/users/{target_id}/update', data={
        'username': 'MARTA', 'password': 'another123', 'role': 'user-viewer', 'active': '1', 'first_name': 'Marta',
        'last_name': 'Ruiz', 'modules_profile_id': str(profiles[second_profile]), 'workspace_group_ids': [group_id],
        'workspaces_submitted': '1'}, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200, response.text
    updated = events('update_user')[-1]
    assert updated['changes'] == {'last_name': ['', 'Ruiz'], 'modules_profile': [first_profile, second_profile],
                                  'workspace_groups': [[], ['Field']]}
    assert updated['password_changed'] is True and 'another123' not in json.dumps(updated)
    # Saved again as it is: no change.
    client.post(f'/admin/users/{target_id}/update', data={'username': 'MARTA', 'role': 'user-viewer', 'active': '1'},
                headers={'X-Requested-With': 'XMLHttpRequest'})
    assert events('update_user')[-1]['changes'] == {}
    page = client.get('/app-logs').text
    assert (f'User MARTA: last name none → Ruiz; Modules Profile {first_profile} → {second_profile}; Workspace Groups +Field; '
            'password changed.') in page
    assert 'User MARTA saved with no changes.' in page
    # A user deleted: the account as it was.
    assert client.post(f'/admin/users/{target_id}/delete', follow_redirects=False).status_code == 303
    assert events('delete_user')[-1]['last_name'] == 'Ruiz'


def test_app_events_are_filtered_and_paged_on_the_server(client) -> None:
    import inspect

    from src.modules.repository import APP_EVENTS_LIMIT, Repository

    login(client)
    # App Events shows the newest 10,000 events (every event is kept); one named limit.
    assert APP_EVENTS_LIMIT == 10_000 and inspect.signature(Repository.list_logs).parameters['limit'].default == APP_EVENTS_LIMIT
    with core.repository.connection() as conn:
        conn.execute('DELETE FROM audit_logs')
        conn.executemany('INSERT INTO audit_logs (username, action, details, created_at) VALUES (?, ?, ?, ?)', [
            ('admin' if index % 2 else 'system', 'login' if index % 3 else 'logout', '{}', f'2026-10-{10 + index % 5}T10:{index % 60:02d}:00.000000+02:00')
            for index in range(250)])
    first = client.get('/api/app-logs').json()
    assert (first['total'], first['matching'], first['page'], first['pages'], len(first['logs'])) == (250, 250, 1, 3, 100)
    assert first['facets']['user'] == ['admin', 'system'] and first['facets']['date'][0] == '2026-10-14'
    third = client.get('/api/app-logs?page=3').json()
    assert (third['page'], len(third['logs'])) == (3, 50)
    # Several values of a filter; each filter offers the values the other filters leave.
    chosen = client.get('/api/app-logs?user=ADMIN&action=logout&action=login&date=2026-10-11').json()
    assert chosen['filtered'] and chosen['matching'] == 25 and {log['username'] for log in chosen['logs']} == {'admin'}
    assert chosen['facets']['user'] == ['admin', 'system']
    assert chosen['facets']['date'] == ['2026-10-14', '2026-10-13', '2026-10-12', '2026-10-11', '2026-10-10']
    only_system = client.get('/api/app-logs?user=system&action=logout').json()
    assert only_system['facets']['action'] == ['login', 'logout'] and only_system['facets']['user'] == ['admin', 'system']
    # A refresh that knows the signature gets nothing while no event changes, and the events once one does.
    assert client.get(f"/api/app-logs?known={first['signature']}").json()['unchanged'] is True
    core.repository.add_log('admin', 'change_password', 'Password changed from the account badge.')
    refreshed = client.get(f"/api/app-logs?known={first['signature']}").json()
    assert 'unchanged' not in refreshed and refreshed['total'] == 251
    # The Date filter offers every date, whatever the other filters (here, an action of a single day).
    one_day = client.get('/api/app-logs?action=change_password').json()
    assert one_day['matching'] == 1 and one_day['facets']['date'] == refreshed['facets']['date']
    assert {'2026-10-10', '2026-10-14'} <= set(one_day['facets']['date']) and one_day['facets']['user'] == ['admin']
    # The page shows the first page, the total and a pager.
    page = client.get('/app-logs').text
    assert '>251 entries</span>' in page and 'data-app-log-pager' in page and 'Page 1 of 3' in page


def test_app_events_filters_exclude_their_values(client) -> None:
    login(client)
    with core.repository.connection() as conn:
        conn.execute('DELETE FROM audit_logs')
        conn.executemany('INSERT INTO audit_logs (username, action, details, created_at) VALUES (?, ?, ?, ?)', [
            ('admin' if index % 2 else 'system', 'login' if index % 3 else 'logout', '{}', f'2026-10-{10 + index % 5}T10:{index % 60:02d}:00.000000+02:00')
            for index in range(60)] + [('admin', 'change_password', '{}', '2026-10-15T10:00:00.000000+02:00')])
    # Every App Events filter offers Include / Exclude.
    page = client.get('/app-logs').text
    for name in ('date', 'user', 'executor', 'type', 'action'):
        assert 'data-multiselect-exclude aria-label=' in page.split(f'<select data-app-log-{name}-filter', 1)[1].split('>', 1)[0]
    # An excluded filter shows every event but those of its values; the others still choose theirs.
    no_logout = client.get('/api/app-logs?action=logout&exclude=action').json()
    assert no_logout['filtered'] and no_logout['matching'] == 41
    assert {log['action'] for log in no_logout['logs']} == {'login', 'change_password'}
    no_system = client.get('/api/app-logs?user=SYSTEM&exclude=user&action=logout').json()
    assert no_system['matching'] == 10 and {(log['username'], log['action']) for log in no_system['logs']} == {('admin', 'logout')}
    # Several values left out, and an unknown filter name changes nothing.
    assert client.get('/api/app-logs?action=logout&action=login&exclude=action').json()['matching'] == 1
    assert client.get('/api/app-logs?action=logout&exclude=nonsense').json()['matching'] == 20
    assert client.get('/api/app-logs?exclude=action').json()['matching'] == 61
    # The values a filter leaves out stay in its list while an event has them, whatever the other filters (only admin
    # changed a password); included values follow the other filters as before.
    system = client.get('/api/app-logs?user=system&action=change_password').json()
    assert system['matching'] == 0 and system['facets']['action'] == ['login', 'logout']
    kept = client.get('/api/app-logs?user=system&action=change_password&exclude=action').json()
    assert kept['matching'] == 30 and kept['facets']['action'] == ['change_password', 'login', 'logout']
    assert client.get('/api/app-logs?user=system&action=missing&exclude=action').json()['facets']['action'] == ['login', 'logout']


def test_executed_by_tells_where_each_event_ran(client) -> None:
    import io
    import zipfile

    login_super(client)
    with core.repository.connection() as conn:
        conn.execute('DELETE FROM audit_logs')
    # A change made from a page records its module; the server's work and earlier events are told by their action.
    target = next(row for row in core.repository.list_users() if row['username'] == 'demo')
    client.post(f"/admin/users/{target['id']}/update", data={'username': 'demo', 'role': 'user-viewer', 'active': '1', 'first_name': 'Demo'},
                headers={'X-Requested-With': 'XMLHttpRequest'})
    stored = {row['action']: row['origin'] for row in core.repository.list_logs(limit=None)}
    assert stored['update_user'] == 'module:super-admin'
    core.repository.add_log('system', 'process_dataset', '{"dataset_id": 1}')
    with core.repository.connection() as conn:
        conn.execute("INSERT INTO audit_logs (username, action, details, created_at) VALUES ('admin', 'nq_call_update', '{}', ?)",
                     ('2026-10-01T10:00:00.000000+02:00',))
    view = client.get('/api/app-logs').json()
    places = {log['action']: (log['executed_by'], log['executor_name'], log['executor_tag']) for log in view['logs']}
    assert places['update_user'] == ('module:super-admin', 'Super Admin', 'module')
    assert places['process_dataset'] == ('server:background', 'Server', 'Background job')
    assert places['nq_call_update'] == ('module:non-qualified-calls', 'Non-Qualified Calls', 'module')
    # The filter lists the server first, then the modules in their order, a line between the groups; it takes several.
    assert [(entry['value'], entry['divider']) for entry in view['executor_choices']] == [
        ('server:background', False), ('module:non-qualified-calls', True), ('module:super-admin', False)]
    chosen = client.get('/api/app-logs?executor=server:background&executor=module:super-admin').json()
    assert {log['action'] for log in chosen['logs']} == {'update_user', 'process_dataset'}
    page = client.get('/app-logs').text
    assert ('<td><span class="app-log-place app-log-place-server">Server <span class="user-choice-tag app-log-badge user-choice-tag-origin '
            'user-choice-tag-origin-server">Background job</span></span></td>') in page
    # Exported and imported with the events.
    package, _filename = core.build_export_archive('app-events')
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        document = json.loads(archive.read(manifest['archive_path']))
    assert {event['action']: event['origin'] for event in document['events']}['update_user'] == 'module:super-admin'
    with core.repository.connection() as conn:
        conn.execute("DELETE FROM audit_logs WHERE action = 'update_user'")
    core._restore_workspace_app_events(core.workspace_registry.get(core.active_workspace.id), json.dumps(document).encode('utf-8'))
    assert {row['action']: row['origin'] for row in core.repository.list_logs(limit=None)}['update_user'] == 'module:super-admin'


def test_public_pages_and_sign_in_are_where_their_events_ran(client) -> None:
    client.post('/login', data={'username': 'nobody', 'password': 'wrong'})
    failed = next(row for row in core.repository.list_logs(limit=None) if row['action'] == 'login')
    assert failed['origin'] == 'public:sign-in'
    login(client)
    log = next(log for log in client.get('/api/app-logs').json()['logs'] if log['action'] == 'login')
    assert (log['executor_name'], log['executor_tag']) == ('Public', 'Sign-in')


def test_every_application_start_is_recorded_in_every_workspace(client) -> None:
    from src.modules.repository import Repository

    assert core.STARTUP_READY.wait(timeout=30)
    started = events('application_started')
    assert len(started) == 1
    assert started[0]['version'] == core.__version__ and started[0]['active_workspace_id'] == core.active_workspace.id
    assert started[0]['ready_in_seconds'] >= 0 and started[0]['pid'] > 0 and started[0]['python'] and started[0]['platform']
    login(client)
    log = next(log for log in client.get('/api/app-logs').json()['logs'] if log['action'] == 'application_started')
    assert (log['username'], log['executor_name'], log['executor_tag'], log['log_type']) == ('system', 'Server', 'Startup', 'Info')
    assert log['description'].startswith(f'Application started (version {core.__version__}): active workspace ')
    # The other workspaces get the same event, an Error when the active one could not be opened; one never opened, without
    # a database yet, is left without one.
    other = core.workspace_registry.create('Other workspace')
    other_repository = Repository(other.database_path, core.repository.global_db_path, core.workspace_registry.registry_path)
    other_repository.initialize()
    unopened = core.workspace_registry.create('Unopened workspace')
    failed = {**started[0], 'error': 'The active workspace could not be opened: database is locked'}
    core._record_application_start(failed, skip_workspace_id=core.active_workspace.id)
    assert [json.loads(row['details']) for row in other_repository.list_logs() if row['action'] == 'application_started'] == [failed]
    assert len(events('application_started')) == 1 and not unopened.database_path.exists()
    assert core.classify_workspace_log_entry({'action': 'application_started', 'details': failed}) == 'Error'


def test_app_events_filter_lists_are_tall_and_compact() -> None:
    from pathlib import Path

    static = Path(core.__file__).parent / 'web_interface' / 'static'
    css = (static / 'css' / 'app.css').read_text(encoding='utf-8')
    script = (static / 'js' / 'app.js').read_text(encoding='utf-8')
    # Only the App Events lists: most of the window tall, values close together, the search and Select All / None fixed.
    assert ('.app-logs-filters .multiselect-menu { width: max-content; min-width: max(100%, 15rem); '
            'max-width: min(32rem, calc(100vw - 2rem));') in css
    assert 'right: auto; gap: .1rem; max-height: min(70vh, 720px); }' in css
    assert '.app-logs-filters .multiselect-option { padding: 0.36rem 0.65rem; line-height: 1.25; }' in css
    assert '.app-logs-filters .multiselect-menu > .multiselect-search { top: 0;' in css
    # Below the button, or above it when the window has more room there, and inside the window.
    assert "menu.classList.toggle('opens-upwards', upwards);" in script
    assert 'Math.min(window.innerHeight * 0.7, upwards ? above : below)' in script
