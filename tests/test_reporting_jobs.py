import io
import json
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.DriveTestAnalyzer as core
from src.modules.core.app_event_details import app_event_origin
from src.modules.reporting import bundle_report_templates, report_tasks
from src.modules.reporting.report_tasks import (
    next_run_after, normalize_definition, normalize_schedule, recurrence_label, register_report_artifact_provider,
    safe_file_name,
)
from src.modules.scoring.scoring_reports import default_report_configuration

TZ = timezone(timedelta(hours=2))
# A Scoring artifact designed in a job, as the jobs saved before the reports owned their schedules have them.
SCORING_ENTRY = {'nr_mode': 'NSA', 'report': default_report_configuration()}
PNG = b'\x89PNG\r\n\x1a\nfake'
RECIPIENTS = {'parse_recipients': core.parse_recipients, 'invalid_recipients': core.invalid_recipients}


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def session(client, username, role):
    token = f'reporting-{username}-{role}'
    core.SESSIONS[token] = core.SessionUser(username=username, role=role)
    client.cookies.clear()
    client.cookies.set(core.SESSION_COOKIE, token)


def workspace_user(username, role):
    """A real account with access to the active workspace."""
    core.repository.create_user(username, f'{username}123', role)
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == username)
    core.repository.set_user_workspace_access(user_id, [core.active_workspace.id])
    return user_id


def test_schedules_compute_the_next_execution():
    after = datetime(2026, 10, 5, 9, 30, tzinfo=TZ)  # A Monday.
    assert next_run_after(normalize_schedule({'mode': 'daily', 'time': '08:00'}), after) == datetime(2026, 10, 6, 8, 0, tzinfo=TZ)
    assert next_run_after(normalize_schedule({'mode': 'daily', 'time': '10:00'}), after) == datetime(2026, 10, 5, 10, 0, tzinfo=TZ)
    weekly = normalize_schedule({'mode': 'weekly', 'time': '08:00', 'weekdays': [0, 4]})
    assert next_run_after(weekly, after) == datetime(2026, 10, 9, 8, 0, tzinfo=TZ)
    # The last day of a shorter month replaces a missing day.
    monthly = normalize_schedule({'mode': 'monthly', 'time': '07:15', 'day_of_month': 31})
    assert next_run_after(monthly, datetime(2026, 11, 2, tzinfo=TZ)) == datetime(2026, 11, 30, 7, 15, tzinfo=TZ)
    once = normalize_schedule({'mode': 'once', 'date': '2026-10-05', 'time': '09:00'})
    assert next_run_after(once, after) is None
    assert next_run_after(normalize_schedule({'mode': 'manual'}), after) is None
    assert recurrence_label(weekly) == 'Weekly · Mon, Fri · 08:00'
    with pytest.raises(ValueError):
        normalize_schedule({'mode': 'weekly', 'time': '08:00', 'weekdays': []})
    with pytest.raises(ValueError):
        normalize_schedule({'mode': 'daily', 'time': '25:00'})


def test_definitions_only_keep_the_report_they_generate():
    # A schedule generates its report: without one, or with artifacts designed in a job (removed with the Job Editor),
    # there is nothing to generate.
    for raw in ({}, {'scoring': [SCORING_ENTRY], 'designs': [{'design_id': 'd1'}], 'dataset_analysis': {'enabled': True}}):
        with pytest.raises(ValueError, match='Choose the report to generate.'):
            normalize_definition(raw)
    definition = normalize_definition({**report_tasks.report_definition(7, ['word', 'excel']), 'scoring': [SCORING_ENTRY]})
    assert definition == {'modules': {'bundle_report_template': {'enabled': True, 'formats': ['word'], 'options': {'filters': {'favourites': ['7']}}}},
                          'theme': 'ericsson'}
    assert report_tasks.report_favourite_id({'definition': definition}) == '7'
    assert report_tasks.report_definition('7')['modules']['bundle_report_template']['formats'] == ['powerpoint']
    # Every report at once, or several, is no schedule of one report.
    every = {'modules': {'bundle_report_template': {'enabled': True, 'formats': ['word'], 'options': {}}}}
    several = {'modules': {'bundle_report_template': {'enabled': True, 'options': {'filters': {'favourites': ['7', '8']}}}}}
    assert report_tasks.report_favourite_id({'definition': every}) == report_tasks.report_favourite_id({'definition': several}) == ''
    assert safe_file_name('Scoring: A/B ' + 'x' * 300 + '.pptx').endswith('.pptx')


def test_sites_to_review_open_their_map_only_for_the_users_of_non_qualified_calls(client):
    analyst_id = workspace_user('analyst', 'user-viewer')
    login(client)
    # The scripts and styles of the maps of Non-Qualified Calls, read the first time a site opens its map.
    page = client.get('/scoring').text
    assert 'data-scoring-nq-map' in page and 'js/nq/nq_call_map.js' in page and 'css/nq/non_qualified_calls.css' in page
    # Without Non-Qualified Calls in their Modules Profile, the sites of Sites to review stay plain text.
    assert client.post('/admin/modules-profiles', data={'name': 'Scoring only', 'description': 'Team', 'modules': ['workspace', 'scoring'],
                                                       'member_ids': [analyst_id]}, follow_redirects=False).status_code == 303
    session(client, 'analyst', 'user-viewer')
    response = client.get('/scoring')
    assert response.status_code == 200 and 'data-scoring-nq-map' not in response.text


def test_modules_profiles_control_the_modules_of_each_user(client):
    analyst_id = workspace_user('analyst', 'user-viewer')
    login(client)
    # Super-admins see every module.
    page = client.get('/workspace').text
    assert 'href="/reporting"' in page and 'href="/non-qualified-calls"' in page
    order = [page.index(f'href="{path}"') for path in ('/datasets-analysis', '/ppt-designer', '/scoring', '/network-insights', '/non-qualified-calls', '/reporting')]
    assert order == sorted(order)
    # A user without a profile has the default one: every module.
    session(client, 'analyst', 'user-viewer')
    page = client.get('/workspace').text
    assert 'href="/reporting"' in page and 'href="/scoring"' in page
    assert client.get('/reporting').status_code == 200
    assert client.get('/scoring').status_code == 200
    # A profile gives its modules to its users.
    login(client)
    assert client.post('/admin/modules-profiles', data={'name': 'Reporting only', 'description': 'Team', 'modules': ['workspace', 'reporting'],
                                                       'member_ids': [analyst_id]}, follow_redirects=False).status_code == 303
    profile_id = next(profile['id'] for profile in core.repository.list_modules_profiles() if profile['name'] == 'Reporting only')
    session(client, 'analyst', 'user-viewer')
    assert client.get('/reporting').status_code == 200
    assert client.get('/scoring').status_code == 403
    # Changing the modules of a profile changes them for all its users at once.
    login(client)
    response = client.post(f'/admin/modules-profiles/{profile_id}/update', data={
        'name': 'Reporting only', 'modules': ['reporting'], 'member_ids': [analyst_id], 'initial_member_ids': [analyst_id],
    })
    assert response.status_code == 200, response.text
    assert next(profile for profile in response.json()['profiles'] if profile['id'] == profile_id)['modules'] == ['reporting']
    session(client, 'analyst', 'user-viewer')
    assert client.get('/workspace').status_code == 403
    assert client.get('/reporting').status_code == 200
    # Super-admins see Modules Profiles in Super Admin; admins, viewers and editors do not change them.
    session(client, 'someone', 'admin')
    assert client.get('/super-admin').status_code == 403
    assert client.post(f'/admin/modules-profiles/{profile_id}/update', data={'name': 'x'}).status_code == 403
    session(client, 'boss', 'super-admin')
    assert 'id="modules-profiles"' in client.get('/super-admin').text
    session(client, 'writer', 'user-editor')
    assert client.post(f'/admin/modules-profiles/{profile_id}/update', data={'name': 'x'}).status_code == 403


def test_help_readme_and_changelog_are_public(client):
    client.cookies.clear()
    assert client.get('/documents/view/help').status_code == 200
    assert 'Sign in' in client.get('/documents/view/readme').text
    assert client.get('/api/documents/changelog').status_code == 200
    index = [item['relative_path'] for item in client.get('/api/documents/help-index').json()['documents']]
    assert 'reporting.md' in index and 'ppt-reporting-old.md' not in index
    assert client.get('/api/documents/help/ppt-reporting-old.md').status_code == 404
    assert 'ppt-reporting-old.md' not in client.get('/api/documents/help').json()['content']
    assert 'Email Delivery' in client.get('/api/documents/help/app-config.md').json()['content']
    # Every user sees the same chapters, in the order of the main tabs.
    login(client)
    super_index = [item['relative_path'] for item in client.get('/api/documents/help-index').json()['documents']]
    workspace_user('writer', 'user-editor')
    login(client, 'writer', 'writer123')
    index = [item['relative_path'] for item in client.get('/api/documents/help-index').json()['documents']]
    assert index == super_index and 'ppt-reporting-old.md' not in index
    assert index.index('ppt-designer.md') < index.index('scoring-gap-analysis.md') < index.index('reporting.md')


def test_email_delivery_settings_keep_the_saved_password(client):
    login(client)
    saved = client.post('/application-config/email-delivery', data={
        'host': 'smtp.example.com', 'port': '587', 'security': 'starttls', 'username': 'bot', 'password': 'secret',
        'from_address': 'reports@example.com', 'from_name': 'Reports', 'max_attachments_mb': '10',
    }, follow_redirects=False)
    assert saved.status_code == 303
    client.post('/application-config/email-delivery', data={
        'host': 'smtp.example.com', 'port': '465', 'security': 'ssl', 'username': 'bot', 'password': '',
        'from_address': 'reports@example.com', 'from_name': 'Reports', 'max_attachments_mb': '10',
    })
    settings = core.email_delivery_settings(core.repository, include_password=True)
    assert (settings['port'], settings['security'], settings['password'], settings['configured']) == (465, 'ssl', 'secret', True)
    page = client.get('/application-config').text
    assert 'Email Delivery' in page and 'secret' not in page
    invalid = client.post('/application-config/email-delivery', data={
        'host': 'smtp.example.com', 'port': '587', 'security': 'starttls', 'from_address': 'not-an-address', 'max_attachments_mb': '10',
    }, follow_redirects=False)
    assert 'error=' in invalid.headers['location']


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass

    def login(self, username, password):
        pass

    def send_message(self, message):
        FakeSMTP.sent.append(message)


def wait_for_run(client, run_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = next(item for item in client.get('/api/reporting/state').json()['runs'] if item['id'] == run_id)
        if run['status'] not in {'queued', 'running', 'stopping'}:
            return run
        time.sleep(0.1)
    raise AssertionError('The Reporting run did not finish.')


def wait_until(condition, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError('The condition was not met in time.')


def module_job(name, *modules):
    """A schedule of the fake modules a test registers, as a report registers its own."""
    return report_tasks.save_task(core.repository, None, {
        'name': name, 'definition': {'modules': {key: {'enabled': True} for key in modules}}, 'schedule': {'mode': 'manual'},
    }, 'super', **RECIPIENTS)


def start_run(task, username='super'):
    """Generate a schedule now, as Generate does for a report."""
    return core.start_report_run(core.repository, task, 'manual', username)


def report(client, name, schedule=None):
    """A report saved from its page, with its schedule when given."""
    response = client.post('/api/reporting/bundle-report-template/favourites', json={
        'name': name, 'definition': bundle_report_templates.normalize_definition({}),
        **({'schedule': schedule} if schedule is not None else {})})
    assert response.status_code == 200, response.text
    return response.json()['favourite']


def generate(client, favourite_id, refresh=False):
    """Generate a report from its page; returns its run."""
    response = client.post(f'/api/reporting/bundle-report-template/favourites/{favourite_id}/generate', json={'refresh': refresh})
    assert response.status_code == 200, response.text
    return response.json()['run_id']


def fake_reports(monkeypatch):
    """Reports generated at once: one file per format and the preview of the run, as the provider writes them; returns
    who generated each one, with its options."""
    generated = []

    def generate_report(config, folder, stamp, user):
        generated.append({'user': user.username, 'reuse': config['reuse'], 'formats': config['formats']})
        formats, artifacts = {}, []
        for export_format, suffix in (('powerpoint', 'pptx'), ('word', 'docx')):
            if export_format in config['formats']:
                path = folder / f'{stamp} - Fake report.{suffix}'
                path.write_bytes(b'PK report')
                artifacts.append({'module': 'bundle_report_template', 'title': 'Fake report', 'format': export_format, 'file_name': path.name,
                                  'size': path.stat().st_size, 'status': 'ready', 'details': ['Filter: everything']})
                formats[export_format] = {'file_name': path.name, 'previews': 1, 'navigation': []}
        preview = folder / bundle_report_templates.RUN_REPORT_FOLDER
        preview.mkdir()
        (preview / 'preview-pptx-0.png').write_bytes(PNG)
        (preview / 'report.json').write_text(json.dumps({'title': 'Fake report', 'formats': formats, 'outline': [], 'warnings': [],
                                                         'reused': [], 'document_reused': False}), encoding='utf-8')
        return artifacts

    monkeypatch.setitem(report_tasks.ARTIFACT_PROVIDERS['bundle_report_template'], 'generate', generate_report)
    return generated


def make_due(task):
    with core.repository.connection() as connection:
        connection.execute('UPDATE report_tasks SET next_run_at = ? WHERE id = ?',
                           ((datetime.now().astimezone() - timedelta(minutes=1)).isoformat(), task['id']))


def workspace_database(path):
    """The database of a workspace of its own, without the application."""
    repository = core.Repository(path)
    repository.initialize()
    return repository


def two_step_job(client, first, second):
    """A job of two fake modules: ``first`` and ``second`` generate its artifacts (in this order)."""
    def provider(label, behaviour):
        def generate(config, folder, stamp, user):
            behaviour()
            path = folder / f'{stamp} - {label}.pptx'
            path.write_bytes(b'fake')
            return [{'module': label, 'title': label, 'file_name': path.name, 'size': 4, 'status': 'ready', 'details': []}]
        return generate

    register_report_artifact_provider('fake_first', 'First fake', 'datasets-analysis', provider('First', first))
    register_report_artifact_provider('fake_second', 'Second fake', 'datasets-analysis', provider('Second', second))
    return module_job('Two steps', 'fake_first', 'fake_second')


def run_row(run_id):
    return report_tasks.get_run(core.repository, run_id)


def test_reporting_runs_stop_rerun_and_delete_from_the_run_history(client):
    login(client)
    calls = {'first': 0, 'second': 0}
    release = __import__('threading').Event()

    def first():
        calls['first'] += 1

    def second():
        calls['second'] += 1
        # A long step that looks whether its run was stopped while it works.
        while not release.is_set():
            report_tasks.check_run_stopped()
            time.sleep(0.05)

    try:
        task = two_step_job(client, first, second)
        run_id = start_run(task)
        wait_until(lambda: calls['second'] == 1)
        # A running run stops after the step it is on, keeping what it generated, without its email.
        response = client.post('/api/reporting/runs/stop', json={'ids': [run_id]})
        assert response.json() == {'stopped': [], 'stopping': [run_id], 'skipped': []}
        assert run_row(run_id)['status'] in {'stopping', 'stopped'}
        run = wait_for_run(client, run_id)
        assert run['status'] == 'stopped' and run['message'] == 'Stopped by super after 1 of 2 steps'
        assert [item['title'] for item in run['artifacts']] == ['First']
        # A run that is not queued or running is not stopped; a stopped one is run again from the beginning, in its row.
        assert client.post('/api/reporting/runs/stop', json={'ids': [run_id]}).json()['skipped'] == [run_id]
        release.set()
        assert client.post('/api/reporting/runs/rerun', json={'ids': [run_id]}).json() == {'rerun': [run_id], 'skipped': []}
        run = wait_for_run(client, run_id)
        assert run['status'] == 'completed' and [item['title'] for item in run['artifacts']] == ['First', 'Second']
        assert calls == {'first': 2, 'second': 2} and run['trigger'] == 'manual' and run['requested_by'] == 'super'
        # A completed run is not run again.
        assert client.post('/api/reporting/runs/rerun', json={'ids': [run_id]}).json()['skipped'] == [run_id]
        # A queued run stopped before it starts never starts.
        queued = report_tasks.create_run(core.repository, report_tasks.get_task(core.repository, task['id']), 'manual', 'super')
        assert client.post('/api/reporting/runs/stop', json={'ids': [queued]}).json()['stopped'] == [queued]
        assert run_row(queued)['status'] == 'stopped' and run_row(queued)['message'] == 'Stopped by super before it started'
        # Several runs are deleted at once, never one that is still active.
        active = report_tasks.create_run(core.repository, report_tasks.get_task(core.repository, task['id']), 'manual', 'super')
        result = client.post('/api/reporting/runs/delete', json={'ids': [run_id, queued, active]}).json()
        assert result == {'deleted': [run_id, queued], 'skipped': [active]}
        assert run_row(run_id) is None and run_row(active)['status'] == 'queued'
        # Only editors rerun or delete runs, and stop those of other users.
        workspace_user('reader', 'user-viewer')
        login(client, 'reader', 'reader123')
        assert client.post('/api/reporting/runs/stop', json={'ids': [active]}).json()['skipped'] == [active]
        assert client.post('/api/reporting/runs/rerun', json={'ids': [active]}).status_code == 403
        assert client.post('/api/reporting/runs/delete', json={'ids': [active]}).status_code == 403
        login(client)
        # Every action is recorded in App Events.
        actions = {row['action'] for row in core.repository.list_logs(limit=200)}
        assert {'stop_reporting_job_run', 'rerun_reporting_job_run', 'delete_reporting_job_run'} <= actions
    finally:
        release.set()
        report_tasks.ARTIFACT_PROVIDERS.pop('fake_first', None)
        report_tasks.ARTIFACT_PROVIDERS.pop('fake_second', None)


def test_reporting_runs_interrupted_by_a_restart_go_on_from_their_step(client):
    login(client)
    calls = {'first': 0, 'second': 0}
    release = __import__('threading').Event()

    def first():
        calls['first'] += 1

    def second():
        calls['second'] += 1
        release.wait(30)

    try:
        task = two_step_job(client, first, second)
        run_id = start_run(task)
        wait_until(lambda: calls['second'] == 1)
        # What a restart leaves: the run running, after its first step, with what the second one began to write.
        interrupted = run_row(run_id)
        assert interrupted['control']['done'] == 1 and [item['title'] for item in interrupted['artifacts']] == ['First']
        release.set()
        wait_for_run(client, run_id)
        with core.repository.connection() as connection:
            connection.execute("UPDATE report_task_runs SET status = 'running', finished_at = NULL, artifacts_json = ?, "
                               "control_json = ? WHERE id = ?",
                               (json.dumps(interrupted['artifacts']), json.dumps(interrupted['control']), run_id))
        folder = Path(interrupted['output_dir'])
        second_file = next(path for path in folder.iterdir() if 'Second' in path.name)
        second_file.write_bytes(b'half written')
        # Another run interrupted by too many restarts fails, and one being stopped ends as stopped.
        job = report_tasks.get_task(core.repository, task['id'])
        too_often = report_tasks.create_run(core.repository, job, 'manual', 'super')
        stopping = report_tasks.create_run(core.repository, job, 'manual', 'super')
        with core.repository.connection() as connection:
            connection.execute("UPDATE report_task_runs SET status = 'running', control_json = ? WHERE id = ?",
                               (json.dumps({'restarts': report_tasks.MAX_RUN_RESUMES}), too_often))
            connection.execute("UPDATE report_task_runs SET status = 'stopping', control_json = ? WHERE id = ?",
                               (json.dumps({'stopped_by': 'super'}), stopping))
        core.run_due_report_tasks()
        run = wait_for_run(client, run_id)
        # The first step is not generated again: the run goes on with the second one in its folder.
        assert calls == {'first': 1, 'second': 2}
        assert run['status'] == 'completed' and [item['title'] for item in run['artifacts']] == ['First', 'Second']
        assert run_row(run_id)['control']['restarts'] == 1
        assert sorted(path.name for path in folder.iterdir()) == sorted(item['file_name'] for item in run['artifacts'])
        assert run_row(too_often)['status'] == 'failed' and 'not resumed again' in run_row(too_often)['error']
        assert run_row(stopping)['status'] == 'stopped' and run_row(stopping)['message'] == 'Stopped by super'
        actions = {row['action'] for row in core.repository.list_logs(limit=200)}
        assert {'resume_reporting_job_run', 'fail_interrupted_reporting_job_run', 'stop_interrupted_reporting_job_run'} <= actions
    finally:
        release.set()
        report_tasks.ARTIFACT_PROVIDERS.pop('fake_first', None)
        report_tasks.ARTIFACT_PROVIDERS.pop('fake_second', None)


def test_workspace_access_by_workspace_group_and_user(client):
    login(client)
    workspace_id = core.active_workspace.id
    core.repository.create_user('field', 'field123', 'user-viewer')
    field_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'field')
    assert not core.repository.user_has_workspace_access('field', workspace_id)
    # A Workspace Group opens its workspaces to its members.
    assert client.post('/admin/workspace-groups', data={'name': 'Field', 'description': '', 'workspace_ids': [workspace_id],
                                                        'member_ids': [field_id]}, follow_redirects=False).status_code == 303
    group_id = next(group['id'] for group in core.repository.list_workspace_groups() if group['name'] == 'Field')
    assert core.repository.user_has_workspace_access('field', workspace_id)
    assert 'id="workspace-groups"' in client.get('/super-admin').text
    # Its card removes the user; a user granted the workspace individually still opens it.
    response = client.post(f'/admin/workspace-groups/{group_id}/update', data={
        'name': 'Field', 'workspace_ids': [workspace_id], 'member_ids': [], 'initial_member_ids': [field_id],
    })
    assert response.status_code == 200, response.text
    assert next(group for group in response.json()['groups'] if group['id'] == group_id)['member_ids'] == []
    assert not core.repository.user_has_workspace_access('field', workspace_id)
    core.repository.set_user_workspace_access(field_id, [workspace_id])
    assert core.repository.user_has_workspace_access('field', workspace_id)
    core.repository.set_user_workspace_access(field_id, [])
    # Workspace Management saves the Workspace Groups and the users of the workspace.
    name = core.active_workspace.name
    assert client.post('/workspace/save', data={'workspace_id': workspace_id, 'name': name, 'workspace_group_ids': [],
                                                'usernames': ['field']}, follow_redirects=False).status_code == 303
    assert next(group for group in core.repository.list_workspace_groups() if group['id'] == group_id)['workspace_ids'] == []
    assert workspace_id in core.repository.list_user_workspace_ids(field_id)
    client.post('/workspace/save', data={'workspace_id': workspace_id, 'name': name, 'workspace_group_ids': [group_id]}, follow_redirects=False)
    assert next(group for group in core.repository.list_workspace_groups() if group['id'] == group_id)['workspace_ids'] == [workspace_id]


def test_users_table_sets_profile_workspace_groups_and_names(client):
    login(client)
    workspace = core.active_workspace
    core.repository.create_user('analyst', 'analyst123', 'user-viewer')
    analyst_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'analyst')
    group_id = core.repository.save_workspace_group(None, 'Analysts', '', [workspace.id])
    profile_id = next(profile['id'] for profile in core.repository.list_modules_profiles() if profile['name'] == 'Non-Qualified Calls')
    response = client.post(f'/admin/users/{analyst_id}/update', data={
        'username': 'analyst', 'first_name': ' Ana ', 'last_name': 'García', 'role': 'user-viewer', 'active': '1',
        'modules_profile_id': str(profile_id), 'workspace_group_ids': [group_id], 'workspaces_submitted': '1',
    }, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200, response.text
    user = response.json()['user']
    assert (user['first_name'], user['last_name'], user['modules_profile_id'], user['workspace_group_ids']) == ('Ana', 'García', profile_id, [group_id])
    assert core.repository.user_has_workspace_access('analyst', workspace.id)
    page = client.get('/super-admin').text
    header = page.split('<table class="users-table">', 1)[1].split('</thead>', 1)[0]
    assert re.findall(r'<th[^>]*>(?:<button[^>]*>)?([^<]+)', header) == [
        'User', 'Last Log-in', 'Password', 'Role', 'Modules Profile', 'Active', 'Workspaces']
    assert 'name="first_name" value="Ana"' in page and '>AG</span>' in page
    # A form without the workspace selector keeps the memberships, the names and the profile.
    client.post(f'/admin/users/{analyst_id}/update', data={'username': 'analyst', 'role': 'user-viewer', 'active': '1'},
                headers={'X-Requested-With': 'XMLHttpRequest'})
    assert next(group for group in core.repository.list_workspace_groups() if group['id'] == group_id)['member_ids'] == [analyst_id]
    assert core.repository.get_user_by_id(analyst_id)['first_name'] == 'Ana'
    assert next(profile for profile in core.repository.list_modules_profiles() if analyst_id in profile['member_ids'])['id'] == profile_id


def test_reporting_options_list_cdr_analysis_metrics_per_cdr_type(client):
    login(client)
    options = client.get('/api/reporting/options').json()
    assert set(options['cdr_metrics']) == {'data', 'voice', 'speech'}
    assert options['cdr_kinds'] == {'data': 'CDR Data', 'voice': 'CDR Voice', 'speech': 'CDR Speech'}
    assert options['cdr_aggregations']['all'] == 'Auto' and options['cdr_cdf_groupings']['all'] == 'Single CDF'


def test_reporting_state_names_its_workspace_for_editor_drafts(client):
    login(client)
    assert client.get('/api/reporting/state').json()['workspace_id'] == core.active_workspace.id


def test_cdr_analysis_word_keeps_the_powerpoint_of_the_same_run(tmp_path, monkeypatch):
    # The PowerPoint and the Word of one CDR Analysis artifact share their name; building the Word
    # from an intermediate presentation must not replace or remove the PowerPoint next to it.
    monkeypatch.setattr(core, 'build_dataset_summary_reports', lambda *_args, **_kwargs: ([], []))
    monkeypatch.setattr(core, 'export_dataset_summary_powerpoint', lambda path, _reports: Path(path).write_bytes(b'pptx'))
    monkeypatch.setattr('src.modules.reporting.pptx_to_docx.pptx_to_docx', lambda content, *_args, **_kwargs: b'docx')
    # No workspace is open: the user's theme (kept in the workspace) is the default one.
    monkeypatch.setattr(core, 'load_user_theme', lambda *_args, **_kwargs: 'ericsson')
    powerpoint = tmp_path / '20261007_120000 - CDR Analysis.pptx'
    core.write_dataset_summary([1], 'powerpoint', powerpoint, 'super')
    word = tmp_path / '20261007_120000 - CDR Analysis.docx'
    core.write_dataset_summary([1], 'word', word, 'super')
    assert powerpoint.read_bytes() == b'pptx' and word.read_bytes() == b'docx'
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([powerpoint.name, word.name])


def test_several_runs_download_in_one_zip_with_a_folder_each(client):
    def generate(config, folder, stamp, user):
        path = folder / f'{stamp} - Fake report.pptx'
        path.write_bytes(b'fake')
        return [{'module': 'fake', 'title': 'Fake report', 'file_name': path.name, 'size': 4, 'status': 'ready', 'details': []}]

    register_report_artifact_provider('fake', 'Fake module', 'datasets-analysis', generate)
    try:
        login(client)
        task = module_job('Zip check', 'fake')
        runs = [wait_for_run(client, start_run(task)) for _ in range(2)]
        response = client.get('/api/reporting/runs/download', params=[('ids', run['id']) for run in runs])
        assert response.status_code == 200 and 'Reporting - 2 runs.zip' in response.headers['content-disposition']
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            folders = {name.split('/')[0] for name in archive.namelist()}
        assert len(folders) == 2 and all('Zip check' in folder for folder in folders)
        assert any(row['action'] == 'download_reporting_job_runs' for row in core.repository.list_logs(limit=20))
        assert client.get('/api/reporting/runs/download', params={'ids': 999999}).status_code == 404
    finally:
        report_tasks.ARTIFACT_PROVIDERS.pop('fake', None)


def test_bundle_report_files_of_reporting_jobs_are_named_dt_analyzer_bundle_report():
    from src.modules.reporting import bundle_report_templates
    from src.modules.reporting.report_tasks import artifact_path

    assert bundle_report_templates.BUNDLE_REPORT_FILE_PREFIX == 'DT Analyzer Bundle Report'
    source = (Path(__file__).parents[1] / 'src/modules/reporting/bundle_report_templates.py').read_text(encoding='utf-8')
    assert "artifact_path(folder, stamp, BUNDLE_REPORT_FILE_PREFIX, favourite['name'], suffix)" in source
    assert artifact_path(Path('/nonexistent'), '20261021_050000', 'DT Analyzer Bundle Report', 'Complete Report', '.pptx').name \
        == '20261021_050000 - DT Analyzer Bundle Report - Complete Report.pptx'


def test_a_long_step_moves_the_progress_of_its_run(client):
    release = __import__('threading').Event()

    def generate(config, folder, stamp, user):
        report_tasks.report_step_progress(50, 'Composing the PowerPoint')
        release.wait(10)
        path = folder / f'{stamp} - Slow report.pptx'
        path.write_bytes(b'slow')
        return [{'module': 'slow', 'title': 'Slow report', 'file_name': path.name, 'size': 4, 'status': 'ready', 'details': []}]

    register_report_artifact_provider('slow', 'Slow module', 'datasets-analysis', generate)
    try:
        login(client)
        run_id = start_run(module_job('Progress check', 'slow'))
        # Halfway through its only step, the run is at 45% and says what the step is doing.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (run_row(run_id)['progress'] or 0) < 45:
            time.sleep(0.1)
        row = run_row(run_id)
        assert row['progress'] == 45 and row['message'] == 'Generating Slow module (1/1): Composing the PowerPoint'
        release.set()
        assert wait_for_run(client, run_id)['status'] == 'completed'
        # Outside a run it does nothing.
        report_tasks.report_step_progress(50, 'Nothing')
    finally:
        release.set()
        report_tasks.ARTIFACT_PROVIDERS.pop('slow', None)


def test_a_report_schedule_emails_its_runs_and_runs_when_due(client, monkeypatch):
    import smtplib

    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    FakeSMTP.sent = []
    generated = fake_reports(monkeypatch)
    login(client)
    core.save_email_delivery_settings(core.repository, {
        'host': 'smtp.example.com', 'port': 587, 'security': 'starttls', 'from_address': 'reports@example.com',
        'max_attachments_mb': 10,
    }, keep_password=False)
    favourite = report(client, 'Weekly check', schedule={'schedule': {'mode': 'weekly', 'time': '08:00', 'weekdays': [0]}, 'formats': ['powerpoint'],
                                                         'send_email': True, 'recipients': 'a@example.com; b@example.com'})
    task = report_tasks.report_task(core.repository, favourite['id'])
    assert task['recipients'] == ['a@example.com', 'b@example.com'] and task['next_run_at']
    run_id = generate(client, favourite['id'])
    run = wait_for_run(client, run_id)
    assert run['status'] == 'sent', run
    message = FakeSMTP.sent[-1]
    assert message['To'] == 'a@example.com, b@example.com' and message['Subject'].startswith('DT Analyzer - Weekly check · ')
    body = message.get_body(('plain',)).get_content()
    assert 'Fake report' in body and 'Filter: everything' in body
    assert [part.get_filename() for part in message.iter_attachments()] == [run['artifacts'][0]['file_name']]
    assert client.get(f'/api/reporting/runs/{run_id}/download').status_code == 200
    state = client.get('/api/reporting/state').json()
    assert next(item for item in state['reports'] if item['id'] == favourite['id'])['last_run']['id'] == run_id
    # Due schedules run once per schedule check.
    make_due(task)
    due = core.run_due_report_tasks()
    assert len(due) == 1 and core.run_due_report_tasks() == []
    assert wait_for_run(client, due[0])['trigger'] == 'schedule' and len(generated) == 2


def test_imported_report_schedules_keep_an_owner_that_exists_here(client):
    login(client)
    workspace_user('editor', 'user-editor')
    names = ('Owned by editor', 'Owner from elsewhere', 'Older export')
    ids = {name: bundle_report_templates.save_favourite(core.repository, None, name, {}, 'super')['id'] for name in names}
    document = {
        'format': 'drivetest-analyzer-reporting-jobs', 'version': 2, 'favourite_names': {str(index): name for index, name in enumerate(names, 101)},
        'reporting_jobs': [
            {'name': 'Owned by editor', 'definition': report_tasks.report_definition(101), 'schedule': {'mode': 'manual'}, 'created_by': 'editor'},
            {'name': 'Owner from elsewhere', 'definition': report_tasks.report_definition(102), 'schedule': {'mode': 'manual'}, 'created_by': 'nobody-here'},
            {'name': 'Older export', 'definition': report_tasks.report_definition(103), 'schedule': {'mode': 'manual'}},
        ],
    }
    # A schedule imported by an earlier version keeps the placeholder owner until it is imported again.
    report_tasks.save_report_schedule(core.repository, ids['Older export'], 'Older export', {}, 'import', **RECIPIENTS)

    assert core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(document).encode(), 'super') == 3

    owners = {task['name']: task['created_by'] for task in report_tasks.list_tasks(core.repository)}
    assert owners == {'Owned by editor': 'editor', 'Owner from elsewhere': 'super', 'Older export': 'super'}
    exported = json.loads(report_tasks.export_tasks_document(core.repository))
    assert {item['name']: item['created_by'] for item in exported['reporting_jobs']} == owners


def test_a_report_is_generated_only_with_the_modules_of_who_generates_it(client):
    editor_id = workspace_user('editor', 'user-editor')
    login(client, 'editor', 'editor123')
    profile_id = core.repository.save_modules_profile(None, 'No Scoring', '', [key for key in core.FEATURE_KEYS if key != 'scoring'])
    core.repository.set_users_modules_profile([editor_id], profile_id)
    core.invalidate_module_access_cache()
    definition = bundle_report_templates.normalize_definition({})
    for section in definition['sections']:
        section['enabled'] = section['key'] == 'scoring'
    favourite = bundle_report_templates.save_favourite(core.repository, None, 'Scoring only', definition, 'super')
    response = client.post(f"/api/reporting/bundle-report-template/favourites/{favourite['id']}/generate", json={})
    assert response.status_code == 400 and 'your account can use' in response.json()['detail']
    assert report_tasks.report_task(core.repository, favourite['id']) is None


def test_reporting_runs_appear_in_background_tasks(client):
    login(client)
    favourite = bundle_report_templates.save_favourite(core.repository, None, 'Background check', {}, 'super')
    task = report_tasks.save_report_schedule(core.repository, favourite['id'], favourite['name'], {}, 'super', **RECIPIENTS)
    report_tasks.create_run(core.repository, task, 'manual', 'super')
    assert 'Report: Background check' in json.dumps(client.get('/api/background-tasks').json())


def test_reporting_options_list_the_filter_values_of_the_cdrs(client):
    login(client)
    options = client.get('/api/reporting/options').json()
    assert set(options['values']) == {'Operator', 'Operator_Vendor', 'Vendor_Operator', 'Vendor', 'Region', 'Cluster', 'City', 'Campaign'}
    assert set(options['campaigns']) == {'NSA', 'SA', report_tasks.NSA_VS_SA} and options['catalogues_pending'] is False
    assert options['email_configured'] is False and options['timezone']


def test_reports_are_labelled_with_their_area_operators_nr_mode_and_campaigns(client):
    # As the Favourites Filters of Scoring & GAP Analysis: the Region, Cluster or City filtered (Nationwide when none), then
    # the Operator or Vendor; the checked modules in their order, the NR Mode and each choice of campaigns once.
    nationwide = bundle_report_templates.report_labels({})
    assert nationwide['scopes'] == [{'dimension': 'all', 'text': 'Nationwide', 'title': 'No Region, Cluster or City is filtered'}]
    assert nationwide['nr_mode'] == 'NSA' and nationwide['modules'] == ['scoring', 'network_insights', 'non_qualified_calls', 'dataset_analysis']
    definition = bundle_report_templates.normalize_definition({'filters': {
        'nr_mode': 'SA', 'regions': ['Vendor A', 'VMO2 North'], 'main_cities': True, 'cities': ['Leeds'], 'operators': ['-Three']}})
    for section in definition['sections']:
        section['enabled'] = section['key'] in {'scoring', 'network_insights', 'non_qualified_calls'}
        section['options']['campaigns'] = {'scoring': ['@latest-2-campaigns'], 'network_insights': ['@latest-campaign']}.get(section['key'], [])
    labels = bundle_report_templates.report_labels(definition)
    assert [(scope['dimension'], scope['text']) for scope in labels['scopes']] == [
        ('region', 'Vendor A, VMO2 North'), ('city', 'Main Cities, Leeds'), ('operator', '-Three')]
    assert (labels['modules'], labels['nr_mode']) == (['scoring', 'network_insights', 'non_qualified_calls'], 'SA')
    assert labels['campaigns'] == [{'campaigns': 'Latest 2 campaigns', 'modules': ['scoring']}, {'campaigns': 'Latest campaign', 'modules': ['network_insights']},
                                   {'campaigns': 'All campaigns', 'modules': ['non_qualified_calls']}]
    # The card of the report receives them with the report, and shows them with the colours of their dimension.
    login(client)
    saved = bundle_report_templates.save_favourite(core.repository, None, 'Labelled', definition, 'super')
    listed = next(item for item in client.get('/api/reporting/state').json()['reports'] if item['id'] == saved['id'])
    assert listed['labels'] == labels
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/reporting/bundle_report_template.js').read_text(encoding='utf-8')
    styles = (core.PROJECT_ROOT / 'src/web_interface/static/css/reporting/report_jobs.css').read_text(encoding='utf-8')
    assert "const tag = node('span', scope.text, `rp-scope rp-scope-${scope.dimension}`);" in script
    assert all(f'.rp-scope-{dimension} {{' in styles for dimension in ('all', 'region', 'cluster', 'city', 'operator', 'vendor'))


def test_history_filters_its_runs_by_column_and_acts_on_the_checked_ones(client):
    login(client)
    page = client.get('/reporting').text
    assert 'id="rp-tab-reports"' in page and 'id="rp-tab-history"' in page
    for button in ('id="rp-rerun-selected"', 'id="rp-stop-selected"', 'id="rp-download-selected"', 'id="rp-delete-selected"'):
        assert button in page
    assert page.count('class="bulk-toolbar" role="toolbar"') == 1
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/reporting/reporting_history.js').read_text(encoding='utf-8')
    # Each button acts only when every checked run allows it, and tells how many it acts on.
    assert 'const ok = chosen.length > 0 && chosen.every(test);' in script
    assert "set('rp-stop-selected', 'Stop', (run) => STOPPABLE.includes(run.status));" in script
    assert "set('rp-download-selected', 'Download', downloadable);" in script
    assert 'button.textContent = ok ? `${label} (${chosen.length})` : label;' in script
    # Every column but Actions filters as in Excel, kept in the browser for each workspace and user; the bar counts the rows
    # shown, and the rows the filters hide are unchecked.
    assert 'persistKey: `drivetest-analyzer:reporting:history-filters:${filtersScope}`,' in script
    assert 'count.textContent = `Showing ${all.filter((row) => !row.hidden).length} of ${all.length} runs`;' in script
    assert 'checked.delete(Number(row.dataset.runId));' in script
    # Select all acts on the rows shown.
    assert "rows().filter((row) => !row.hidden).forEach((row) => {" in script


def test_jobs_become_the_schedules_of_their_reports_once(tmp_path, monkeypatch):
    repository = workspace_database(tmp_path / 'workspace.db')
    weekly = bundle_report_templates.save_favourite(repository, None, 'Weekly', {}, 'super')
    monthly = bundle_report_templates.save_favourite(repository, None, 'Monthly', {}, 'super')

    def report_job(favourite_id, formats, key='bundle_report_template'):
        return {'modules': {key: {'enabled': True, 'formats': formats, 'options': {'filters': {'favourites': [str(favourite_id)]}}}}}

    weekday = {'mode': 'weekly', 'time': '08:00', 'weekdays': [0]}
    jobs = [('My weekly job', report_job(weekly['id'], ['word'], 'complete_report'), {'mode': 'manual'}),
            ('Monthly by hand', report_job(monthly['id'], ['word']), {'mode': 'manual'}),
            ('Monthly on Mondays', report_job(monthly['id'], ['powerpoint']), weekday),
            ('Designed', {'scoring': [SCORING_ENTRY]}, weekday),
            ('Every report', {'modules': {'bundle_report_template': {'enabled': True, 'formats': ['word'], 'options': {}}}}, {'mode': 'manual'}),
            ('Report gone', report_job(999, ['word']), weekday)]
    ids, folders = {}, {}
    with repository.connection() as connection:
        connection.executescript(report_tasks.SCHEMA)
        for position, (name, definition, schedule) in enumerate(jobs, 1):
            ids[name] = connection.execute(
                f"INSERT INTO {report_tasks.REPORT_TASKS_TABLE} (name, definition_json, send_email, schedule_json, created_by, created_at, updated_at, "
                "position) VALUES (?, ?, 0, ?, 'editor', '2026-10-01', '2026-10-01', ?)",
                (name, json.dumps(definition), json.dumps(schedule), position)).lastrowid
            folders[name] = tmp_path / 'output' / 'reports' / 'reporting-jobs' / name
            folders[name].mkdir(parents=True)
            connection.execute(f"INSERT INTO {report_tasks.REPORT_TASK_RUNS_TABLE} (task_id, task_name, trigger, status, requested_by, created_at, output_dir) "
                               "VALUES (?, ?, 'manual', 'completed', 'editor', '2026-10-02', ?)", (ids[name], name, str(folders[name])))
    monkeypatch.setattr(report_tasks, '_LEGACY_JOBS_STORED', set())
    report_tasks.ensure_report_task_tables(repository)

    tasks = {task['name']: task for task in report_tasks.list_tasks(repository)}
    # A job that generates one report becomes its schedule, named after it, with its formats (a former key of the artifact too).
    assert set(tasks) == {'Weekly', 'Monthly'}
    assert tasks['Weekly']['id'] == ids['My weekly job'] and report_tasks.report_favourite_id(tasks['Weekly']) == str(weekly['id'])
    assert tasks['Weekly']['definition']['modules'] == report_tasks.report_definition(weekly['id'], ['word'])['modules']
    # Of the jobs of one report the scheduled one stays, and the runs of the others stay in History with it.
    assert tasks['Monthly']['id'] == ids['Monthly on Mondays'] and tasks['Monthly']['schedule'] == weekday
    assert tasks['Monthly']['definition']['modules'] == report_tasks.report_definition(monthly['id'], ['powerpoint'])['modules']
    assert report_tasks.report_task(repository, monthly['id'])['id'] == ids['Monthly on Mondays']
    assert {run['task_name']: run['task_id'] for run in report_tasks.list_runs(repository)} == {
        'My weekly job': ids['My weekly job'], 'Monthly by hand': ids['Monthly on Mondays'], 'Monthly on Mondays': ids['Monthly on Mondays']}
    # The jobs of artifacts designed in the job, of every report or of a report that no longer exists go with their runs and folders.
    assert sorted(name for name, folder in folders.items() if folder.exists()) == ['Monthly by hand', 'Monthly on Mondays', 'My weekly job']
    # App Events tells what changed.
    events = [row for row in repository.list_logs(limit=10) if row['action'] == 'reporting_jobs_became_report_schedules']
    assert [row['username'] for row in events] == ['system']
    event = json.loads(events[0]['details'])
    assert event['kept'] == [{'id': ids['My weekly job'], 'report': 'Weekly'}, {'id': ids['Monthly on Mondays'], 'report': 'Monthly'}]
    assert event['merged'] == [{'id': ids['Monthly by hand'], 'name': 'Monthly by hand', 'into': ids['Monthly on Mondays']}]
    assert [item['name'] for item in event['deleted']] == ['Designed', 'Every report', 'Report gone']
    assert app_event_origin('reporting_jobs_became_report_schedules', event) == 'server:startup'
    # Another process finds the schedules of the reports as they are: nothing changes, and nothing is told.
    monkeypatch.setattr(report_tasks, '_LEGACY_JOBS_STORED', set())
    report_tasks.ensure_report_task_tables(repository)
    assert {task['name']: task['id'] for task in report_tasks.list_tasks(repository)} == {name: task['id'] for name, task in tasks.items()}
    assert len([row for row in repository.list_logs(limit=10) if row['action'] == 'reporting_jobs_became_report_schedules']) == 1


def test_each_report_has_one_schedule_renamed_and_deleted_with_it(tmp_path):
    repository = workspace_database(tmp_path / 'workspace.db')
    weekly = bundle_report_templates.save_favourite(repository, None, 'Weekly', {}, 'super')
    other = bundle_report_templates.save_favourite(repository, None, 'Other', {}, 'super')
    assert report_tasks.report_task(repository, weekly['id']) is None
    task = report_tasks.save_report_schedule(repository, weekly['id'], 'Weekly', {
        'schedule': {'mode': 'weekly', 'time': '07:30', 'weekdays': [0]}, 'formats': ['word', 'excel'],
        'send_email': True, 'recipients': 'a@example.com; b@example.com'}, 'editor', **RECIPIENTS)
    assert (task['name'], task['created_by'], task['recurrence'], task['recipients']) == (
        'Weekly', 'editor', 'Weekly · Mon · 07:30', ['a@example.com', 'b@example.com'])
    assert task['enabled'] and task['next_run_at']
    # It generates its report, in the formats chosen among those of a report.
    assert task['definition']['modules'] == report_tasks.report_definition(weekly['id'], ['word'])['modules']
    assert report_tasks.report_favourite_id(task) == str(weekly['id'])
    assert report_tasks.report_task(repository, weekly['id'])['id'] == task['id']
    # A report has one schedule: saving it again changes it and keeps its owner; by default, by hand and in both formats.
    again = report_tasks.save_report_schedule(repository, weekly['id'], 'Weekly', {'enabled': False}, 'super', **RECIPIENTS)
    assert (again['id'], again['created_by'], again['enabled'], again['next_run_at'], again['schedule']['mode'], again['send_email']) == (
        task['id'], 'editor', False, None, 'manual', False)
    assert again['definition']['modules']['bundle_report_template']['formats'] == ['powerpoint', 'word']
    assert list(report_tasks.report_tasks_by_favourite(repository)) == [str(weekly['id'])]
    # What is wrong is refused, and the report stays without a schedule.
    with pytest.raises(ValueError, match='Enter a name for the report.'):
        report_tasks.save_report_schedule(repository, other['id'], ' ', {}, 'super', **RECIPIENTS)
    for wrong in ({'schedule': {'mode': 'monthly', 'day_of_month': 40}}, {'send_email': True, 'recipients': ''}, {'send_email': True, 'recipients': 'bad'},
                  {'schedule': {'mode': 'once', 'date': '2020-01-01', 'time': '08:00'}}):
        with pytest.raises(ValueError):
            report_tasks.save_report_schedule(repository, other['id'], 'Other', wrong, 'super', **RECIPIENTS)
    assert report_tasks.report_task(repository, other['id']) is None
    # A renamed report renames its schedule; its runs keep the name they had.
    run_id = report_tasks.create_run(repository, again, 'manual', 'super')
    report_tasks.rename_report_task(repository, weekly['id'], 'Weekly v2')
    report_tasks.rename_report_task(repository, other['id'], 'Other v2')
    assert report_tasks.report_task(repository, weekly['id'])['name'] == 'Weekly v2'
    assert report_tasks.get_run(repository, run_id)['task_name'] == 'Weekly'
    assert report_tasks.report_task(repository, other['id']) is None
    # A deleted report takes its schedule and its runs, and gives the folders of the runs to remove.
    report_tasks.update_run(repository, run_id, output_dir=str(tmp_path / 'run'))
    assert report_tasks.delete_report_task(repository, weekly['id']) == [str(tmp_path / 'run')]
    assert report_tasks.report_task(repository, weekly['id']) is None and report_tasks.get_run(repository, run_id) is None
    assert report_tasks.delete_report_task(repository, other['id']) == []
    # What no longer exists says so.
    with pytest.raises(ValueError, match='The schedule of the report no longer exists.'):
        report_tasks.delete_task(repository, task['id'])
    with pytest.raises(ValueError, match='The schedule of the report no longer exists.'):
        report_tasks.save_task(repository, task['id'], {'name': 'Weekly', 'definition': report_tasks.report_definition(weekly['id'])}, 'super', **RECIPIENTS)


def test_report_schedules_travel_to_the_report_of_the_same_name(tmp_path):
    source = workspace_database(tmp_path / 'source.db')
    destination = workspace_database(tmp_path / 'destination.db')
    weekly = bundle_report_templates.save_favourite(source, None, 'Weekly', {}, 'super')
    only_source = bundle_report_templates.save_favourite(source, None, 'Only here', {}, 'super')
    report_tasks.save_report_schedule(source, weekly['id'], 'Weekly', {
        'schedule': {'mode': 'daily', 'time': '06:00'}, 'formats': ['word'], 'send_email': True, 'recipients': 'team@example.com'}, 'editor', **RECIPIENTS)
    report_tasks.save_report_schedule(source, only_source['id'], 'Only here', {'schedule': {'mode': 'weekly', 'time': '08:00', 'weekdays': [2]}}, 'super', **RECIPIENTS)
    document = json.loads(report_tasks.export_tasks_document(source))
    # Each schedule names its report; the reports travel as an element of their own.
    assert (document['format'], document['version']) == ('drivetest-analyzer-reporting-jobs', 2)
    assert document['favourite_names'] == {str(weekly['id']): 'Weekly', str(only_source['id']): 'Only here'}
    assert [item['name'] for item in document['reporting_jobs']] == ['Weekly', 'Only here'] and all(item['uid'] for item in document['reporting_jobs'])
    assert 'favourites' not in document and 'complete_reports' not in document
    # Documents of before also carry jobs of artifacts designed in the job.
    document['reporting_jobs'].append({'name': 'Designed', 'definition': {'scoring': [SCORING_ENTRY]}, 'schedule': {'mode': 'manual'}})
    # The destination has the report of that name (whatever its case) with another ID, and a schedule for it.
    bundle_report_templates.save_favourite(destination, None, 'Monthly', {}, 'super')
    here = bundle_report_templates.save_favourite(destination, None, 'weekly', {}, 'super')
    assert here['id'] != weekly['id']
    previous = report_tasks.save_report_schedule(destination, here['id'], 'weekly', {}, 'super', **RECIPIENTS)
    summary = []
    assert report_tasks.import_tasks_document(destination, json.dumps(document), 'importer', **RECIPIENTS,
                                              user_exists=lambda name: name == 'editor', summary=summary) == 1
    # It replaces the schedule of that report, keeping the owner it had when that user is here, and the others are left out.
    assert summary == ['2 schedules left out: this workspace has no report of their names, or they generated artifacts designed in the job.']
    [task] = report_tasks.list_tasks(destination)
    assert (task['id'], task['name'], task['created_by']) == (previous['id'], 'weekly', 'editor')
    assert report_tasks.report_favourite_id(task) == str(here['id'])
    assert (task['recurrence'], task['send_email'], task['recipients']) == ('Daily · 06:00', True, ['team@example.com'])
    assert task['definition']['modules']['bundle_report_template']['formats'] == ['word']
    # And back: the schedule of the report there is replaced and the other one stays.
    summary = []
    assert report_tasks.import_tasks_document(source, report_tasks.export_tasks_document(destination), 'importer', **RECIPIENTS, summary=summary) == 1
    assert summary == []
    schedules = report_tasks.report_tasks_by_favourite(source)
    assert set(schedules) == {str(weekly['id']), str(only_source['id'])}
    assert schedules[str(weekly['id'])]['created_by'] == 'importer' and schedules[str(weekly['id'])]['recurrence'] == 'Daily · 06:00'
    assert schedules[str(only_source['id'])]['recurrence'] == 'Weekly · Wed · 08:00'
    with pytest.raises(ValueError, match='not a DriveTest Analyzer Report Schedules export'):
        report_tasks.import_tasks_document(source, json.dumps({'format': 'other'}), 'importer', **RECIPIENTS)


def test_saving_a_report_saves_its_schedule_and_a_wrong_one_saves_nothing(client):
    login(client)
    url = '/api/reporting/bundle-report-template/favourites'
    definition = bundle_report_templates.normalize_definition({})
    # A wrong schedule, or email without valid recipients, is refused before the report is saved.
    for schedule, message in (({'schedule': {'mode': 'weekly', 'time': '08:00', 'weekdays': []}}, 'Choose at least one weekday.'),
                              ({'schedule': {'mode': 'daily', 'time': '25:00'}}, 'Enter the time as HH:MM.'),
                              ({'send_email': True, 'recipients': ''}, 'Add at least one email recipient or turn email off.'),
                              ({'send_email': True, 'recipients': 'bad'}, 'Invalid email recipients: bad.')):
        response = client.post(url, json={'name': 'Refused', 'definition': definition, 'schedule': schedule})
        assert response.status_code == 400 and response.json()['detail'] == message
    assert bundle_report_templates.list_favourites(core.repository) == []
    # Without a schedule it starts without one.
    assert report_tasks.report_task(core.repository, report(client, 'Plain')['id']) is None
    response = client.post(url, json={'name': 'Weekly', 'definition': definition, 'schedule': {
        'enabled': True, 'schedule': {'mode': 'weekly', 'time': '07:30', 'weekdays': [0, 4]}, 'formats': ['word'],
        'send_email': True, 'recipients': 'a@example.com; b@example.com'}})
    assert response.status_code == 200, response.text
    favourite = response.json()['favourite']
    task = report_tasks.report_task(core.repository, favourite['id'])
    assert (task['name'], task['recurrence'], task['recipients'], task['created_by']) == (
        'Weekly', 'Weekly · Mon, Fri · 07:30', ['a@example.com', 'b@example.com'], 'super')
    assert task['definition']['modules']['bundle_report_template']['formats'] == ['word'] and task['next_run_at']
    saved = next(json.loads(row['details']) for row in core.repository.list_logs(limit=20) if row['action'] == 'bundle_report_template_favourite_saved')
    assert saved['created'] is True and saved['schedule']['recurrence'] == 'Weekly · Mon, Fri · 07:30'
    # Saved without one, the report keeps its schedule; turned off, it is only generated with Generate and keeps when it runs.
    assert client.put(f"{url}/{favourite['id']}", json={'name': 'Weekly', 'definition': definition}).status_code == 200
    assert report_tasks.report_task(core.repository, favourite['id'])['next_run_at'] == task['next_run_at']
    response = client.put(f"{url}/{favourite['id']}", json={'name': 'Weekly', 'definition': definition, 'schedule': {
        'enabled': False, 'schedule': {'mode': 'weekly', 'time': '07:30', 'weekdays': [0, 4]}}})
    assert response.status_code == 200, response.text
    paused = report_tasks.report_task(core.repository, favourite['id'])
    assert (paused['id'], paused['enabled'], paused['next_run_at'], paused['schedule']['mode'], paused['send_email']) == (task['id'], False, None, 'weekly', False)
    assert len(report_tasks.list_tasks(core.repository)) == 1
    # Only editors save reports and their schedules.
    workspace_user('reader', 'user-viewer')
    login(client, 'reader', 'reader123')
    assert client.put(f"{url}/{favourite['id']}", json={'name': 'Weekly', 'definition': definition, 'schedule': {'enabled': True}}).status_code == 403


def test_a_single_execution_in_the_past_is_refused_before_the_report_is_saved(client):
    login(client)
    response = client.post('/api/reporting/bundle-report-template/favourites', json={
        'name': 'Refused', 'definition': bundle_report_templates.normalize_definition({}),
        'schedule': {'schedule': {'mode': 'once', 'date': '2020-01-01', 'time': '08:00'}}})
    assert response.status_code == 400 and response.json()['detail'] == 'The single execution must be in the future.'
    assert bundle_report_templates.list_favourites(core.repository) == []


def test_generate_runs_a_report_as_who_asks_and_history_opens_its_preview(client, monkeypatch):
    generated = fake_reports(monkeypatch)
    login(client)
    weekly = report(client, 'Weekly')
    other = report(client, 'Other', schedule={'schedule': {'mode': 'daily', 'time': '06:00'}, 'formats': ['powerpoint']})
    workspace_user('writer', 'user-editor')
    login(client, 'writer', 'writer123')
    # A report without a schedule gets one, generated only with Generate, which belongs to who generates it.
    run_id = generate(client, weekly['id'], refresh=True)
    task = report_tasks.report_task(core.repository, weekly['id'])
    assert (task['schedule']['mode'], task['created_by'], task['next_run_at']) == ('manual', 'writer', None)
    assert task['definition']['modules']['bundle_report_template']['formats'] == ['powerpoint', 'word']
    run = wait_for_run(client, run_id)
    assert (run['status'], run['trigger'], run['requested_by'], run['report_id'], run['has_preview']) == ('completed', 'manual', 'writer', weekly['id'], True)
    # Generated as who asks, every section again with refresh.
    assert generated[-1] == {'user': 'writer', 'reuse': False, 'formats': ['powerpoint', 'word']}
    # So is a report that has a schedule of another user, in the formats of its schedule; the schedule itself runs as its owner.
    other_task = report_tasks.report_task(core.repository, other['id'])
    wait_for_run(client, generate(client, other['id']))
    assert generated[-1] == {'user': 'writer', 'reuse': True, 'formats': ['powerpoint']}
    assert other_task['created_by'] == 'super'
    make_due(other_task)
    [due] = core.run_due_report_tasks()
    assert wait_for_run(client, due)['trigger'] == 'schedule' and generated[-1]['user'] == 'super'

    # The state of the page: each report with its labels, its schedule and its last run, and the runs of History.
    state = client.get('/api/reporting/state').json()
    assert set(state) == {'reports', 'runs', 'can_edit', 'workspace_id'} and state['can_edit'] is True and state['workspace_id'] == core.active_workspace.id
    reports = {item['name']: item for item in state['reports']}
    assert set(reports['Weekly']) == {'id', 'name', 'created_by', 'updated_at', 'labels', 'starred', 'schedule', 'last_run'}
    assert reports['Weekly']['last_run']['id'] == run_id and reports['Weekly']['created_by'] == 'super' and reports['Weekly']['labels']['nr_mode'] == 'NSA'
    assert reports['Other']['last_run']['id'] == due
    schedule = reports['Other']['schedule']
    assert {key: schedule[key] for key in ('enabled', 'schedule', 'recurrence', 'formats', 'send_email', 'recipients', 'owner')} == {
        'enabled': True, 'schedule': {'mode': 'daily', 'time': '06:00'}, 'recurrence': 'Daily · 06:00', 'formats': ['powerpoint'],
        'send_email': False, 'recipients': [], 'owner': 'super'}
    assert schedule['next_run_at']
    listed = next(item for item in state['runs'] if item['id'] == run_id)
    assert listed['artifacts_size'] == sum(item['size'] for item in listed['artifacts']) > 0 and all(item['available'] for item in listed['artifacts'])
    # A report without a schedule yet shows the one it would have.
    plain = bundle_report_templates.save_favourite(core.repository, None, 'Plain', {}, 'super')
    listed_plain = next(item for item in client.get('/api/reporting/state').json()['reports'] if item['id'] == plain['id'])
    assert listed_plain['last_run'] is None and listed_plain['schedule'] == {
        'enabled': True, 'schedule': {'mode': 'manual', 'time': '08:00'}, 'recurrence': 'Manual only', 'next_run_at': None,
        'formats': ['powerpoint', 'word'], 'send_email': False, 'recipients': [], 'owner': ''}

    # The preview of a run: what its folder keeps, with the download of each format.
    opened = client.get(f'/api/reporting/runs/{run_id}/report').json()
    assert (opened['run']['id'], opened['run']['status'], opened['run']['task_name']) == (run_id, 'completed', 'Weekly')
    assert opened['report']['title'] == 'Fake report' and opened['report']['downloads'] == {
        'powerpoint': f'/api/reporting/runs/{run_id}/artifacts/0', 'word': f'/api/reporting/runs/{run_id}/artifacts/1'}
    assert client.get(opened['report']['downloads']['word']).content == b'PK report'
    assert client.get(f'/api/reporting/runs/{run_id}/preview/powerpoint/0').content == PNG
    # Opened large with no PDF to render it from, a page shows its preview; a page or a format that has none is not found.
    assert client.get(f'/api/reporting/runs/{run_id}/preview/powerpoint/0?large=true').content == PNG
    assert client.get(f'/api/reporting/runs/{run_id}/preview/powerpoint/1').status_code == 404
    assert client.get(f'/api/reporting/runs/{run_id}/preview/pdf/0').status_code == 404
    # A run that has not finished, or whose report.json is gone or unreadable, opens without a preview.
    queued = report_tasks.create_run(core.repository, task, 'manual', 'writer')
    assert client.get(f'/api/reporting/runs/{queued}/report').json()['report'] is None
    assert client.get(f'/api/reporting/runs/{queued}/preview/powerpoint/0').status_code == 404
    report_json = Path(run['output_dir']) / bundle_report_templates.RUN_REPORT_FOLDER / 'report.json'
    report_json.write_text('not json', encoding='utf-8')
    assert client.get(f'/api/reporting/runs/{run_id}/report').json()['report'] is None
    report_json.unlink()
    assert client.get(f'/api/reporting/runs/{run_id}/report').json()['report'] is None
    assert next(item for item in client.get('/api/reporting/state').json()['runs'] if item['id'] == run_id)['has_preview'] is False
    assert client.get('/api/reporting/runs/999999/report').status_code == 404
    assert client.post('/api/reporting/bundle-report-template/favourites/999999/generate', json={}).status_code == 404
    requested = next(json.loads(row['details']) for row in core.repository.list_logs(limit=50)
                     if row['action'] == 'bundle_report_template_requested' and json.loads(row['details'])['run_id'] == run_id)
    assert requested['id'] == weekly['id'] and requested['refresh'] is True
    assert app_event_origin('bundle_report_template_requested', requested) == 'module:reporting'


def test_each_user_marks_their_own_reports_with_the_star(client):
    login(client)
    one = bundle_report_templates.save_favourite(core.repository, None, 'One', {}, 'super')
    other = bundle_report_templates.save_favourite(core.repository, None, 'Other', {}, 'super')
    starred = lambda: {item['name'] for item in client.get('/api/reporting/state').json()['reports'] if item['starred']}  # noqa: E731
    assert starred() == set()
    url = f"/api/reporting/bundle-report-template/favourites/{one['id']}/star"
    assert client.post(url, json={'starred': True}).json() == {'id': one['id'], 'starred': True}
    assert starred() == {'One'}
    assert 'bundle_report_template_starred' in {row['action'] for row in core.repository.list_logs(limit=20)}
    # A user who is no editor marks them too, and only for themself.
    workspace_user('reader', 'user-viewer')
    login(client, 'reader', 'reader123')
    assert starred() == set()
    assert client.post(f"/api/reporting/bundle-report-template/favourites/{other['id']}/star", json={'starred': True}).status_code == 200
    assert starred() == {'Other'}
    login(client)
    assert starred() == {'One'}
    assert client.post(url, json={'starred': False}).status_code == 200
    assert starred() == set()
    # A report that no longer exists has no star to give.
    missing = client.post('/api/reporting/bundle-report-template/favourites/9999/star', json={'starred': True})
    assert missing.status_code == 404 and missing.json()['detail'] == 'The report no longer exists.'


def test_reports_are_read_online_in_the_slide_viewer_of_the_presentations(client):
    login(client)
    assert 'js/help/presentation_viewer.js' in client.get('/reporting').text
    root = Path(__file__).resolve().parents[1] / 'src/web_interface/static/js'
    viewer = (root / 'help/presentation_viewer.js').read_text(encoding='utf-8')
    assert 'window.PresentationViewer = {enhance, open: openViewer};' in viewer
    script = (root / 'reporting/bundle_report_template.js').read_text(encoding='utf-8')
    assert 'window.PresentationViewer.open(reportPresentation(job, available[0], available), index);' in script
    assert '`/api/reporting/runs/${job.id}/preview/${format}/' in script


def test_a_run_is_stopped_by_who_asked_for_it_or_an_editor(client):
    login(client)
    favourite = bundle_report_templates.save_favourite(core.repository, None, 'Weekly', {}, 'super')
    task = report_tasks.save_report_schedule(core.repository, favourite['id'], 'Weekly', {}, 'super', **RECIPIENTS)
    workspace_user('asker', 'user-viewer')
    workspace_user('other', 'user-viewer')
    mine = report_tasks.create_run(core.repository, task, 'manual', 'asker')
    theirs = report_tasks.create_run(core.repository, task, 'manual', 'asker')
    # Another user who is no editor leaves it as it is.
    login(client, 'other', 'other123')
    assert client.post('/api/reporting/runs/stop', json={'ids': [mine]}).json() == {'stopped': [], 'stopping': [], 'skipped': [mine]}
    assert run_row(mine)['status'] == 'queued'
    # Only editors change the other things of a run.
    refused = client.post('/api/reporting/runs/delete', json={'ids': [mine]})
    assert refused.status_code == 403 and refused.json()['detail'] == 'Editor access is required to change reports and their runs.'
    # Who asked for it stops it, without being an editor.
    login(client, 'asker', 'asker123')
    assert client.post('/api/reporting/runs/stop', json={'ids': [mine]}).json() == {'stopped': [mine], 'stopping': [], 'skipped': []}
    assert run_row(mine)['status'] == 'stopped' and run_row(mine)['message'] == 'Stopped by asker before it started'
    # Editors stop any run.
    login(client)
    assert client.post('/api/reporting/runs/stop', json={'ids': [theirs]}).json()['stopped'] == [theirs]
    stops = {json.loads(row['details'])['run_id']: row['username'] for row in core.repository.list_logs(limit=50) if row['action'] == 'stop_reporting_job_run'}
    assert stops == {mine: 'asker', theirs: 'super'}


def test_deleting_a_report_deletes_its_schedule_and_its_runs(client, monkeypatch):
    fake_reports(monkeypatch)
    login(client)
    weekly = report(client, 'Weekly', schedule={'schedule': {'mode': 'daily', 'time': '08:00'}})
    other = report(client, 'Other')
    run = wait_for_run(client, generate(client, weekly['id']))
    other_run = wait_for_run(client, generate(client, other['id']))
    folder = Path(run['output_dir'])
    assert folder.is_dir() and Path(other_run['output_dir']).is_dir()
    response = client.delete(f"/api/reporting/bundle-report-template/favourites/{weekly['id']}")
    assert response.status_code == 200 and [item['name'] for item in response.json()['favourites']] == ['Other']
    assert report_tasks.report_task(core.repository, weekly['id']) is None and run_row(run['id']) is None and not folder.exists()
    # The other report keeps them.
    assert report_tasks.report_task(core.repository, other['id']) is not None and run_row(other_run['id']) is not None
    assert Path(other_run['output_dir']).is_dir()
    deleted = next(json.loads(row['details']) for row in core.repository.list_logs(limit=20) if row['action'] == 'bundle_report_template_favourite_deleted')
    assert deleted == {'id': weekly['id'], 'name': 'Weekly', 'runs_deleted': 1}
    assert client.delete(f"/api/reporting/bundle-report-template/favourites/{weekly['id']}").status_code == 404


def test_renaming_a_report_renames_its_schedule(client):
    login(client)
    weekly = report(client, 'Weekly', schedule={'schedule': {'mode': 'daily', 'time': '08:00'}})
    report(client, 'Taken')
    run_id = report_tasks.create_run(core.repository, report_tasks.report_task(core.repository, weekly['id']), 'manual', 'super')
    url = f"/api/reporting/bundle-report-template/favourites/{weekly['id']}"
    refused = client.post(f'{url}/rename', json={'name': 'Taken'})
    assert refused.status_code == 400 and refused.json()['detail'] == 'A report named "Taken" already exists.'
    assert client.post(f'{url}/rename', json={'name': ' '}).json()['detail'] == 'Enter a name for the report.'
    response = client.post(f'{url}/rename', json={'name': 'Weekly NetCheck'})
    assert response.status_code == 200 and response.json()['favourite']['name'] == 'Weekly NetCheck'
    # Its schedule takes the new name, and its runs keep the one they had.
    assert report_tasks.report_task(core.repository, weekly['id'])['name'] == 'Weekly NetCheck'
    assert run_row(run_id)['task_name'] == 'Weekly'
    assert bundle_report_templates.get_favourite(core.repository, weekly['id'])['definition'] == weekly['definition']
    renamed = next(json.loads(row['details']) for row in core.repository.list_logs(limit=20) if row['action'] == 'bundle_report_template_favourite_renamed')
    assert (renamed['old_name'], renamed['name']) == ('Weekly', 'Weekly NetCheck')
    # Saved with another name too.
    assert client.put(url, json={'name': 'Weekly v3', 'definition': weekly['definition']}).status_code == 200
    assert report_tasks.report_task(core.repository, weekly['id'])['name'] == 'Weekly v3'
    assert client.post('/api/reporting/bundle-report-template/favourites/999999/rename', json={'name': 'Gone'}).status_code == 404
