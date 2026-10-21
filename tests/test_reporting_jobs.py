import io
import json
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.DriveTestAnalyzer as core
from src.modules import report_tasks
from src.modules.report_tasks import (
    next_run_after, normalize_definition, normalize_schedule, recurrence_label, register_report_artifact_provider,
    safe_file_name,
)
from src.modules.scoring_reports import default_report_configuration

# The Reporting Jobs every workspace starts with (assets/reporting-jobs).
STARTER_JOBS = {'Weekly NetCheck Report (@latest campaign)', 'All Modules Report (@latest 2 campaigns)', 'Scoring Report (@All Campaigns)'}

TZ = timezone(timedelta(hours=2))
# Every Scoring artifact is configured with the report editor.
SCORING_ENTRY = {'nr_mode': 'NSA', 'report': default_report_configuration()}


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


def test_definitions_keep_every_module_option_and_need_an_artifact():
    with pytest.raises(ValueError):
        normalize_definition({})
    definition = normalize_definition({
        'dashboards': [{'dashboard_id': 'd1', 'scope': 'multivendor', 'vendor_comparison': 'vendor_only',
                        'datasets': {'data': [3, '4']}, 'date_from': '2026-01-01',
                        'filters': {'Operator': ['EE', ''], 'RAT': []}}],
        'scoring': [{'nr_mode': 'sa', 'label': 'Weekly', 'report': default_report_configuration(
            context_filters={'Vendor': ['Huawei']}, aggregation_levels=['Operator', 'Campaign'], main_cities=True)}],
    })
    # An entry saved when CDRs were chosen by hand keeps them until it is migrated (see migrate_auto_cdrs).
    assert definition['dashboards'] == [{
        'dashboard_id': 'd1', 'label': '', 'scope': 'multivendor', 'vendor_comparison': 'vendor_only', 'auto_cdrs': False,
        'datasets': {'data': [3, 4]}, 'cdr_selection': '', 'date_from': '2026-01-01', 'date_to': '', 'filters': {'Operator': ['EE']},
    }]
    # The entries of the editor choose their CDRs by Campaign: they carry no CDRs.
    automatic = normalize_definition({
        'dashboards': [{'dashboard_id': 'd1', 'auto_cdrs': True, 'datasets': {'data': [3]}, 'cdr_selection': 'newest',
                        'filters': {'Campaign': ['@latest-2-campaigns']}}],
        'scoring': [{**SCORING_ENTRY, 'auto_cdrs': True, 'campaigns': ['@latest-campaign'], 'dataset_ids': [1]}],
        'network_insights': [{'auto_cdrs': True, 'selection': {'datasets': {'data': [1]}, 'campaigns': ['2026-Q2']}}],
    })
    assert (automatic['dashboards'][0]['datasets'], automatic['dashboards'][0]['cdr_selection']) == ({}, '')
    assert automatic['dashboards'][0]['filters'] == {'Campaign': ['@latest-2-campaigns']}
    assert (automatic['scoring'][0]['dataset_ids'], automatic['scoring'][0]['campaigns']) == ([], ['@latest-campaign'])
    assert automatic['network_insights'][0]['selection']['datasets'] == {}
    assert automatic['network_insights'][0]['selection']['campaigns'] == ['2026-Q2']
    scoring = definition['scoring'][0]
    scenario = scoring['report']['scenarios'][0]
    assert (scoring['nr_mode'], scenario['aggregation_levels'], scenario['context_filters'], scenario['main_cities']) == (
        'SA', ['Operator', 'Campaign'], {'Vendor': ['Huawei']}, True)
    # Filters and aggregation belong to the report scenarios only.
    assert not {'aggregation_levels', 'context_filters', 'main_cities'} & set(scoring)
    with pytest.raises(ValueError, match='Configure the report content'):
        normalize_definition({'scoring': [{'nr_mode': 'NSA'}]})
    assert safe_file_name('Scoring: A/B ' + 'x' * 300 + '.pptx').endswith('.pptx')


def test_modules_profiles_control_the_modules_of_each_user(client):
    analyst_id = workspace_user('analyst', 'user-viewer')
    login(client)
    # Super-admins see every module, PPT Reporting (old) included, although it is in no profile.
    page = client.get('/workspace').text
    assert 'href="/reporting"' in page and 'href="/non-qualified-calls"' in page and 'href="/ppt-reporting-old"' in page
    order = [page.index(f'href="{path}"') for path in ('/datasets-analysis', '/ppt-dashboards', '/scoring', '/network-insights', '/non-qualified-calls', '/reporting')]
    assert order == sorted(order)
    # A user without a profile has the default one: every module but PPT Reporting (old).
    session(client, 'analyst', 'user-viewer')
    page = client.get('/workspace').text
    assert 'href="/reporting"' in page and 'href="/ppt-reporting-old"' not in page
    assert client.get('/reporting').status_code == 200
    assert client.get('/scoring').status_code == 200
    assert client.get('/ppt-reporting-old').status_code == 403
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


def test_help_readme_and_changelog_are_public_except_ppt_reporting_old(client):
    client.cookies.clear()
    assert client.get('/documents/view/help').status_code == 200
    assert 'Sign in' in client.get('/documents/view/readme').text
    assert client.get('/api/documents/changelog').status_code == 200
    index = [item['relative_path'] for item in client.get('/api/documents/help-index').json()['documents']]
    assert 'reporting.md' in index and 'ppt-reporting-old.md' not in index
    assert client.get('/api/documents/help/ppt-reporting-old.md').status_code == 403
    assert 'ppt-reporting-old.md' not in client.get('/api/documents/help').json()['content']
    assert 'Email Delivery' in client.get('/api/documents/help/app-config.md').json()['content']
    # Super-admins see the chapter of every module; other users only those of their Modules Profile.
    login(client)
    assert 'ppt-reporting-old.md' in [item['relative_path'] for item in client.get('/api/documents/help-index').json()['documents']]
    workspace_user('writer', 'user-editor')
    login(client, 'writer', 'writer123')
    index = [item['relative_path'] for item in client.get('/api/documents/help-index').json()['documents']]
    assert 'ppt-reporting-old.md' not in index
    default = next(profile for profile in core.repository.list_modules_profiles() if profile['is_default'])
    core.repository.save_modules_profile(default['id'], default['name'], default['description'], [*default['modules'], 'ppt-reporting-old'])
    core.invalidate_module_access_cache()
    index = [item['relative_path'] for item in client.get('/api/documents/help-index').json()['documents']]
    assert index.index('ppt-dashboards.md') < index.index('ppt-reporting-old.md') < index.index('scoring-gap-analysis.md') < index.index('reporting.md')
    assert client.get('/api/documents/help/ppt-reporting-old.md').status_code == 200


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
    created = client.post('/api/reporting/tasks', json={
        'name': 'Two steps', 'definition': {'modules': {'fake_first': {'enabled': True}, 'fake_second': {'enabled': True}}},
        'schedule': {'mode': 'manual'},
    })
    assert created.status_code == 200, created.text
    return created.json()['task']


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
        run_id = client.post(f"/api/reporting/tasks/{task['id']}/run").json()['run_id']
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
        # Only editors stop, rerun or delete runs.
        session(client, 'reader', 'user-viewer')
        assert client.post('/api/reporting/runs/stop', json={'ids': [active]}).status_code == 403
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
        run_id = client.post(f"/api/reporting/tasks/{task['id']}/run").json()['run_id']
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


def test_reporting_job_runs_emails_and_travels_with_exports(client, monkeypatch, tmp_path):
    import smtplib

    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP)
    FakeSMTP.sent = []

    def generate(config, folder, stamp, user):
        path = folder / f'{stamp} - Fake report.pptx'
        path.write_bytes(b'fake')
        return [{'module': 'fake', 'title': 'Fake report', 'file_name': path.name, 'size': 4, 'status': 'ready',
                 'details': ['Filter: everything']}]

    register_report_artifact_provider('fake', 'Fake module', 'datasets-analysis', generate)
    try:
        login(client)
        core.save_email_delivery_settings(core.repository, {
            'host': 'smtp.example.com', 'port': 587, 'security': 'starttls', 'from_address': 'reports@example.com',
            'max_attachments_mb': 10,
        }, keep_password=False)
        options = client.get('/api/reporting/options').json()
        assert any(provider['key'] == 'fake' for provider in options['providers'])
        payload = {
            'name': 'Weekly check', 'definition': {'modules': {'fake': {'enabled': True}}},
            'send_email': True, 'recipients': 'a@example.com; b@example.com',
            'schedule': {'mode': 'weekly', 'time': '08:00', 'weekdays': [0]}, 'enabled': True,
        }
        created = client.post('/api/reporting/tasks', json=payload)
        assert created.status_code == 200, created.text
        task = created.json()['task']
        assert task['recipients'] == ['a@example.com', 'b@example.com'] and task['next_run_at']
        assert client.post('/api/reporting/tasks', json={**payload, 'recipients': 'bad'}).status_code == 400
        run_id = client.post(f"/api/reporting/tasks/{task['id']}/run").json()['run_id']
        run = wait_for_run(client, run_id)
        assert run['status'] == 'sent', run
        message = FakeSMTP.sent[-1]
        assert message['To'] == 'a@example.com, b@example.com'
        body = message.get_body(('plain',)).get_content()
        assert 'Fake report' in body and 'Filter: everything' in body
        assert [part.get_filename() for part in message.iter_attachments()] == [run['artifacts'][0]['file_name']]
        assert client.get(f'/api/reporting/runs/{run_id}/download').status_code == 200
        state = client.get('/api/reporting/state').json()
        assert next(item for item in state['tasks'] if item['id'] == task['id'])['last_run']['id'] == run_id
        # Duplicates are disabled copies.
        copy = client.post(f"/api/reporting/tasks/{task['id']}/duplicate").json()['task']
        assert copy['name'] == 'Weekly check (copy)' and not copy['enabled'] and copy['next_run_at'] is None
        # Due jobs run once per schedule check.
        with core.repository.connection() as connection:
            connection.execute("UPDATE report_tasks SET next_run_at = ? WHERE id = ?",
                               ((datetime.now().astimezone() - timedelta(minutes=1)).isoformat(), task['id']))
        due = core.run_due_report_tasks()
        assert len(due) == 1 and core.run_due_report_tasks() == []
        wait_for_run(client, due[0])
        # Reporting Jobs travel with workspace packages.
        document = json.loads(report_tasks.export_tasks_document(core.repository))
        # The starter Reporting Jobs of every workspace travel too.
        assert {item['name'] for item in document['reporting_jobs']} == {'Weekly check', 'Weekly check (copy)', *STARTER_JOBS}
        assert core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(document).encode(), 'super') == 2 + len(STARTER_JOBS)
        assert len(client.get('/api/reporting/state').json()['tasks']) == 2 + len(STARTER_JOBS)
        assert client.delete(f"/api/reporting/tasks/{copy['id']}").status_code == 200
    finally:
        report_tasks.ARTIFACT_PROVIDERS.pop('fake', None)



def test_reporting_jobs_travel_with_every_field_of_their_scoring_artifacts(client):
    login(client)
    area = {'enabled': True, 'time_split': 'Quarterly', 'breakdown': 'Cluster', 'cities': ['Leeds', 'Glasgow'],
            'main_cities': True, 'campaigns': ['Latest 2 campaigns']}
    report = default_report_configuration()
    report['scenarios'][0]['area_summary'] = area
    # Patterns (VF*, Not Lebara) travel as such in the Operator filters; Focus operators saved before are left out.
    report['scenarios'][0]['context_filters'] = {'Operator': ['Not Lebara']}
    entry = {**SCORING_ENTRY, 'label': 'Every field', 'auto_cdrs': True, 'campaigns': ['Latest campaign'],
             'formats': ['powerpoint', 'word'], 'baseline_operator': 'VF', 'compared_operators': ['EE', 'O2', 'VF*'], 'report': report}
    created = client.post('/api/reporting/tasks', json={'name': 'Every field', 'definition': {'scoring': [entry]},
                                                         'schedule': {'mode': 'manual'}})
    assert created.status_code == 200, created.text
    task = created.json()['task']
    document = report_tasks.export_tasks_document(core.repository)
    assert client.delete(f"/api/reporting/tasks/{task['id']}").status_code == 200
    core._restore_workspace_reporting_jobs(core.active_workspace, document, 'super')
    [imported] = [item for item in report_tasks.list_tasks(core.repository) if item['name'] == 'Every field']
    assert imported['definition'] == task['definition']
    [scoring] = imported['definition']['scoring']
    assert 'compared_operators' not in scoring and scoring['baseline_operator'] == 'VF'
    assert scoring['report']['scenarios'][0]['area_summary'] == area
    assert scoring['report']['scenarios'][0]['context_filters'] == {'Operator': ['Not Lebara']}

def test_scoring_entries_choose_the_cdrs_of_their_campaigns_at_each_run(client, monkeypatch):
    definition = normalize_definition({'scoring': [
        {**SCORING_ENTRY, 'cdr_selection': 'all_complete'}, SCORING_ENTRY, {**SCORING_ENTRY, 'cdr_selection': 'other'}]})
    assert [entry['cdr_selection'] for entry in definition['scoring']] == ['all_complete', 'newest', 'newest']
    calls = []
    # Each campaign with Data, Voice and Speech CDRs is scored; the CDRs are chosen when the job runs.
    monkeypatch.setattr(report_tasks, 'complete_campaign_cdrs',
                        lambda repository, nr_mode, campaigns: calls.append((nr_mode, list(campaigns))) or ([11, 12, 13], []))

    def build(repository, base, report, username):
        calls.append(base['dataset_ids'])
        return b'pptx', 'Scoring.pptx', {'dataset_ids': base['dataset_ids']}

    monkeypatch.setattr(core, 'build_scoring_report_document', build)
    login(client)
    # A job saved with every complete set of CDRs scores every complete campaign.
    payload = {'name': 'Every complete set', 'schedule': {'mode': 'manual'},
               'definition': {'scoring': [{**SCORING_ENTRY, 'cdr_selection': 'all_complete'}]}}
    created = client.post('/api/reporting/tasks', json=payload)
    assert created.status_code == 200, created.text
    run = wait_for_run(client, client.post(f"/api/reporting/tasks/{created.json()['task']['id']}/run").json()['run_id'])
    assert calls == [('NSA', []), [11, 12, 13]], run
    # The editor opens such jobs with the campaigns of their former choice: every campaign, or the newest one.
    newest = client.post('/api/reporting/tasks', json={**payload, 'name': 'Newest set', 'definition': {'scoring': [SCORING_ENTRY]}})
    tasks = {task['name']: task for task in client.get('/api/reporting/state').json()['tasks']}
    assert tasks['Every complete set']['definition']['scoring'][0] | {'report': None} == tasks['Every complete set']['definition']['scoring'][0] | {
        'auto_cdrs': True, 'campaigns': [], 'dataset_ids': [], 'report': None}
    assert tasks['Newest set']['definition']['scoring'][0]['campaigns'] == ['@latest-campaign']
    assert newest.status_code == 200
    # The CDR Analysis artifact keeps showing the CDRs each automatic choice selects now, per NR Mode.
    def every_complete_set(repository, nr_mode):
        if nr_mode == 'SA':
            raise ValueError('There is no complete set of Data, Voice and Speech CDRs in SA NR Mode.')
        return [11, 12, 13]

    monkeypatch.setattr(core, 'select_all_complete_cdrs', every_complete_set)
    preview = client.get('/api/reporting/options').json()['automatic_cdrs']
    assert preview == {'NSA': {'newest': [], 'all_complete': [11, 12, 13]}, 'SA': {'newest': [], 'all_complete': []}}


def test_cdr_analysis_chooses_its_cdrs_by_nr_mode_and_campaigns(client, monkeypatch):
    asked = []

    def chosen_cdrs(repository, nr_mode, campaigns=None, kinds=None):
        asked.append((nr_mode, list(campaigns or [])))
        return {'data': [21], 'voice': [22], 'speech': [23]} if nr_mode == 'NSA' else {'data': [31], 'voice': [], 'speech': []}

    used = []

    def write_summary(dataset_ids, export_kind, destination, username, **kwargs):
        used.append(list(dataset_ids))
        Path(destination).write_bytes(b'pptx')
        return destination, [], []

    monkeypatch.setattr(report_tasks, 'resolve_cdrs', chosen_cdrs)
    monkeypatch.setattr(core, 'write_dataset_summary', write_summary)
    login(client)
    # A job saved with every complete set of CDRs chooses every campaign of NSA; a new one its NR Mode and Campaigns.
    for definition in ({'enabled': True, 'cdr_selection': 'all_complete'},
                       {'enabled': True, 'auto_cdrs': True, 'nr_mode': 'SA', 'campaigns': ['@latest-campaign']}):
        created = client.post('/api/reporting/tasks', json={'name': f"CDR Analysis {len(used)}", 'schedule': {'mode': 'manual'},
                                                             'definition': {'dataset_analysis': definition}})
        assert created.status_code == 200, created.text
        run = wait_for_run(client, client.post(f"/api/reporting/tasks/{created.json()['task']['id']}/run").json()['run_id'])
        assert run['status'] in {'completed', 'partial'}, run
    assert ('NSA', []) in asked and ('SA', ['@latest-campaign']) in asked
    assert used == [[21, 22, 23], [31]]


def test_imported_reporting_jobs_keep_an_owner_that_exists_here(client):
    login(client)
    workspace_user('editor', 'user-editor')
    definition = {'scoring': [SCORING_ENTRY]}
    document = {
        'format': 'drivetest-analyzer-reporting-jobs', 'version': 1, 'dataset_names': {},
        'reporting_jobs': [
            {'name': 'Owned by editor', 'definition': definition, 'schedule': {'mode': 'manual'}, 'created_by': 'editor'},
            {'name': 'Owner from elsewhere', 'definition': definition, 'schedule': {'mode': 'manual'}, 'created_by': 'nobody-here'},
            {'name': 'Older export', 'definition': definition, 'schedule': {'mode': 'manual'}},
        ],
    }
    # A job imported by an earlier version keeps the placeholder owner until it is imported again.
    with core.repository.connection() as connection:
        report_tasks.ensure_report_task_tables(core.repository)
        connection.execute(
            "INSERT INTO report_tasks (name, definition_json, send_email, recipients_json, schedule_json, enabled, "
            "created_by, created_at, updated_at) VALUES ('Older export', ?, 0, '[]', '{\"mode\": \"manual\"}', 1, 'import', '', '')",
            (json.dumps(definition),),
        )

    assert core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(document).encode(), 'super') == 3

    owners = {task['name']: task['created_by'] for task in report_tasks.list_tasks(core.repository)}
    # The starter jobs, created by the application, belong to the default super-admin once the workspace opens.
    assert owners == {'Owned by editor': 'editor', 'Owner from elsewhere': 'super', 'Older export': 'super',
                      **{name: 'super' for name in STARTER_JOBS}}
    exported = json.loads(report_tasks.export_tasks_document(core.repository))
    assert {item['name']: item['created_by'] for item in exported['reporting_jobs']} == owners


def test_reporting_jobs_only_include_modules_of_their_author(client):
    editor_id = workspace_user('editor', 'user-editor')
    login(client, 'editor', 'editor123')
    profile_id = core.repository.save_modules_profile(None, 'No Scoring', '', [key for key in core.FEATURE_KEYS if key != 'scoring'])
    core.repository.set_users_modules_profile([editor_id], profile_id)
    core.invalidate_module_access_cache()
    payload = {'name': 'Scoring only', 'definition': {'scoring': [SCORING_ENTRY]}, 'schedule': {'mode': 'manual'}}
    response = client.post('/api/reporting/tasks', json=payload)
    assert response.status_code == 403
    assert 'Scoring' in response.json()['detail']
    assert client.get('/api/reporting/options').json()['allowed_modules']['scoring'] is False


def test_network_insights_entries_keep_their_own_selection_and_read_single_selections():
    definition = normalize_definition({'network_insights': [
        {'label': 'NSA LTE', 'formats': ['word'], 'selection': {'nr_mode': 'NSA', 'technology': 'lte', 'operators': ['EE']}},
        {'formats': ['powerpoint'], 'selection': {'nr_mode': 'sa', 'technology': 'nr', 'nr_coverage_threshold': -118}},
    ]})
    first, second = definition['network_insights']
    assert (first['label'], first['formats'], first['selection']['operators']) == ('NSA LTE', ['word'], ['EE'])
    assert (second['selection']['nr_mode'], second['selection']['technology'], second['selection']['nr_coverage_threshold']) == ('SA', 'nr', -118)
    assert report_tasks.network_entry_name(second) == 'SA NR'
    labels = report_tasks.artifact_labels(definition)
    assert 'Network Insights · NSA LTE (Word)' in labels and 'Network Insights · SA NR (PPT)' in labels
    # Jobs saved with one Network Insights selection keep it as one entry.
    legacy = normalize_definition({'network_insights': {'enabled': True, 'formats': ['word'], 'selection': {
        'technology': 'nr', 'coverage_threshold': -112, 'datasets': {'data': [5]}}}})
    assert len(legacy['network_insights']) == 1
    assert legacy['network_insights'][0]['selection']['nr_coverage_threshold'] == -112
    assert report_tasks._remap_dataset_ids(legacy, {5: 9})['network_insights'][0]['selection']['datasets'] == {'data': [9]}
    with pytest.raises(ValueError):
        normalize_definition({'network_insights': {'enabled': False, 'selection': {}}})


def test_every_artifact_with_cdrs_offers_the_two_automatic_choices():
    definition = normalize_definition({
        'dataset_analysis': {'enabled': True, 'cdr_selection': 'newest'},
        'network_insights': [{'cdr_selection': 'all_complete', 'selection': {'nr_mode': 'SA'}}, {'selection': {}}],
        'dashboards': [{'dashboard_id': 'd1', 'cdr_selection': 'newest'}, {'dashboard_id': 'd2', 'all_datasets': True},
                       {'dashboard_id': 'd3', 'datasets': {'data': [5]}}],
    })
    assert definition['dataset_analysis']['cdr_selection'] == 'newest'
    # Jobs saved with every ready CDR use every complete set; a Dashboard without one uses its CDRs.
    assert [entry['cdr_selection'] for entry in definition['network_insights']] == ['all_complete', 'all_complete']
    assert [entry['cdr_selection'] for entry in definition['dashboards']] == ['newest', 'all_complete', '']
    assert normalize_definition({'dataset_analysis': {'enabled': True}})['dataset_analysis']['cdr_selection'] == 'all_complete'


def test_reporting_runs_appear_in_background_tasks(client):
    login(client)
    task = client.post('/api/reporting/tasks', json={
        'name': 'Background check', 'definition': {'scoring': [SCORING_ENTRY]}, 'schedule': {'mode': 'manual'},
    }).json()['task']
    report_tasks.create_run(core.repository, report_tasks.get_task(core.repository, task['id']), 'manual', 'super')
    groups = client.get('/api/background-tasks').json()
    labels = [item['label'] for group in (groups.get('workspaces') or groups.get('groups') or []) for item in group['tasks']] \
        if isinstance(groups, dict) else []
    assert any(label == 'Reporting Job: Background check' for label in labels) or 'Reporting Job: Background check' in json.dumps(groups)


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
    assert '<th>User</th><th>Password</th><th>Role</th><th>Modules Profile</th><th>Active</th><th>Workspaces</th>' in page
    assert 'name="first_name" value="Ana"' in page and '>AG</span>' in page
    # A form without the workspace selector keeps the memberships, the names and the profile.
    client.post(f'/admin/users/{analyst_id}/update', data={'username': 'analyst', 'role': 'user-viewer', 'active': '1'},
                headers={'X-Requested-With': 'XMLHttpRequest'})
    assert next(group for group in core.repository.list_workspace_groups() if group['id'] == group_id)['member_ids'] == [analyst_id]
    assert core.repository.get_user_by_id(analyst_id)['first_name'] == 'Ana'
    assert next(profile for profile in core.repository.list_modules_profiles() if analyst_id in profile['member_ids'])['id'] == profile_id


def test_cdr_analysis_artifact_keeps_metrics_filters_and_single_choices():
    definition = report_tasks.normalize_definition({'dataset_analysis': {
        'enabled': True, 'formats': ['powerpoint'], 'metrics': {'data': ['Mean_Data_Rate'], 'voice': [], 'other': ['x']},
        'filters': {'operators': ['EE'], 'clusters': [], 'unknown': ['x']},
        'aggregation': 'vendor', 'cdf_grouping': 'nonsense',
    }})['dataset_analysis']
    assert definition['metrics'] == {'data': ['Mean_Data_Rate']} and definition['filters'] == {'operators': ['EE']}
    assert definition['aggregation'] == 'vendor' and definition['cdf_grouping'] == 'operator'


def test_reporting_options_list_cdr_analysis_metrics_per_cdr_type(client):
    login(client)
    options = client.get('/api/reporting/options').json()
    assert set(options['cdr_metrics']) == {'data', 'voice', 'speech'}
    assert options['cdr_kinds'] == {'data': 'CDR Data', 'voice': 'CDR Voice', 'speech': 'CDR Speech'}
    assert options['cdr_aggregations']['all'] == 'Auto' and options['cdr_cdf_groupings']['all'] == 'Single CDF'


def test_network_insights_grouping_keeps_operator_unless_vendor():
    entries = lambda group: report_tasks.normalize_definition(
        {'network_insights': [{'enabled': True, 'formats': ['powerpoint'], 'selection': {'group': group}}]})['network_insights']
    assert entries(['campaign'])[0]['selection']['group'] == ['operator', 'campaign']
    assert entries(['vendor', 'campaign'])[0]['selection']['group'] == ['vendor', 'campaign']


def test_reporting_options_list_filter_values_per_cdr(client):
    login(client)
    options = client.get('/api/reporting/options').json()
    assert isinstance(options['values_by_dataset'], dict)
    for values in options['values_by_dataset'].values():
        assert set(values) == {'Operator', 'Operator_Vendor', 'Vendor', 'Region', 'Cluster', 'City', 'Campaign'}


def test_reporting_state_names_its_workspace_for_editor_drafts(client):
    login(client)
    assert client.get('/api/reporting/state').json()['workspace_id'] == core.active_workspace.id


def test_module_artifacts_always_include_a_document_with_their_excel():
    from src.modules import report_tasks

    register_report_artifact_provider('document_and_excel_test', 'Document Test', 'reporting', lambda *_args: [],
                                      formats=('powerpoint', 'word', 'excel'))
    try:
        only_excel = normalize_definition({'modules': {'document_and_excel_test': {'enabled': True, 'formats': ['excel']}}})
        assert only_excel['modules']['document_and_excel_test']['formats'] == ['powerpoint', 'excel']
        word_and_excel = normalize_definition({'modules': {'document_and_excel_test': {'enabled': True, 'formats': ['word', 'excel']}}})
        assert word_and_excel['modules']['document_and_excel_test']['formats'] == ['word', 'excel']
    finally:
        report_tasks.ARTIFACT_PROVIDERS.pop('document_and_excel_test', None)


def test_job_artifacts_are_grouped_by_module_with_their_entries():
    from src.modules import report_tasks

    groups = report_tasks.artifact_groups({
        'dataset_analysis': {'enabled': True, 'formats': ['powerpoint', 'word']},
        'network_insights': [{'nr_mode': 'NSA', 'technology': 'lte', 'formats': ['powerpoint']},
                             {'nr_mode': 'SA', 'technology': 'lte_nr', 'formats': ['word']}],
        'dashboards': [{'dashboard_id': 'd1', 'label': 'Main Cities'}],
        'scoring': [], 'modules': {},
    })
    assert [group['module'] for group in groups] == ['CDR Analysis', 'Network Insights', 'PPT Dashboards']
    assert groups[0]['items'] == ['(PPT/Word)']
    assert len(groups[1]['items']) == 2 and groups[1]['items'][1].endswith('(Word)')
    assert groups[2]['items'] == ['Main Cities (PPT)']


def test_cdr_analysis_word_keeps_the_powerpoint_of_the_same_run(tmp_path, monkeypatch):
    # The PowerPoint and the Word of one CDR Analysis artifact share their name; building the Word
    # from an intermediate presentation must not replace or remove the PowerPoint next to it.
    monkeypatch.setattr(core, 'build_dataset_summary_reports', lambda *_args, **_kwargs: ([], []))
    monkeypatch.setattr(core, 'export_dataset_summary_powerpoint', lambda path, _reports: Path(path).write_bytes(b'pptx'))
    monkeypatch.setattr('src.modules.pptx_to_docx.pptx_to_docx', lambda content, *_args, **_kwargs: b'docx')
    powerpoint = tmp_path / '20261007_120000 - CDR Analysis.pptx'
    core.write_dataset_summary([1], 'powerpoint', powerpoint, 'super')
    word = tmp_path / '20261007_120000 - CDR Analysis.docx'
    core.write_dataset_summary([1], 'word', word, 'super')
    assert powerpoint.read_bytes() == b'pptx' and word.read_bytes() == b'docx'
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([powerpoint.name, word.name])


def test_the_non_qualified_calls_artifact_keeps_campaign_choices_until_each_run():
    root = Path(__file__).parents[1]
    script = (root / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    module = (root / 'src/modules/non_qualified_calls.py').read_text(encoding='utf-8')

    # Its Campaign filter offers the automatic choices first, each alone, and keeps a saved one when NR Mode changes.
    assert "const presets = key === 'campaign' ? campaignPresets : [];" in script
    assert "...(presets.length ? {exclusive: presets} : {})," in script
    assert "chosen = chosen.filter((value) => allowed.has(String(value)) || presets.some(([preset]) => preset === value));" in script
    # Each run resolves the choice among the campaigns of the calls of its NR Modes (none when it stands for none).
    assert 'filters = resolve_report_campaigns(repository, filters)' in module
    assert "chosen = [value for group in preset_campaign_groups(campaign_groups(campaigns), presets[:1]) for value in group]" in module
    assert "return {**filters, 'campaign': chosen or [NO_PREVIOUS_CAMPAIGN]}" in module


def test_a_job_can_start_from_a_favourite_bundle_report_template():
    definition = report_tasks.normalize_definition({'modules': {'bundle_report_template': {
        'enabled': True, 'formats': ['powerpoint', 'word'], 'options': {'filters': {'favourites': ['7']}}}}})
    # The jobs table names the favourite the job generates (every one when it chooses none) with what it includes.
    contents = [{'title': 'Scoring & GAP Analysis', 'items': ['Summary', 'GAP Analysis']}]
    groups = report_tasks.artifact_groups(definition, {}, {'7': 'Weekly NetCheck'}, {'7': contents})
    assert groups == [{'module': 'Bundle Report Template', 'items': ['Weekly NetCheck (PPT/Word)'], 'contents': [contents], 'missing': [False]}]
    assert report_tasks.based_on_favourite(definition)
    assert report_tasks.artifact_labels(definition, {}, {'7': 'Weekly NetCheck'}) == ['Bundle Report Template · Weekly NetCheck (PPT/Word)']
    every = report_tasks.normalize_definition({'modules': {'bundle_report_template': {'enabled': True, 'formats': ['powerpoint']}}})
    assert report_tasks.artifact_groups(every)[0]['items'] == ['Every favourite (PPT)']
    assert not report_tasks.based_on_favourite(every)
    assert not report_tasks.based_on_favourite({**definition, 'scoring': [SCORING_ENTRY]})
    page = (core.PROJECT_ROOT / 'src/web_interface/templates/report_jobs.html').read_text(encoding='utf-8')
    assert 'name="rj-source" value="favourite" checked' in page and 'name="rj-source" value="editor"' in page
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    # From a favourite, the job generates only its Bundle Report Template; one that does opens as such in the editor.
    assert 'function favouriteDefinition(base)' in script and 'function favouriteOf(definition)' in script
    assert "if (jobSource() === 'favourite' && !$('rj-favourite')?.value)" in script
    # Based On tells a job of a favourite from one with artifacts chosen in the editor.
    assert '<th>Artifacts</th><th>Based On</th><th>Recurrence</th><th>Next Run</th>' in page and 'colspan="9"' in page
    assert "fromFavourite ? 'Bundle Report Template' : 'Manual Artifacts'" in script and 'function favouriteContents(sections)' in script
    # The header of the panel counts the jobs of each kind.
    assert all(f'id="rj-count-{kind}"' in page for kind in ('total', 'favourite', 'manual'))
    assert "$('rj-count-manual').textContent = `Manual Artifacts: ${state.tasks.length - favourites}`;" in script


def test_jobs_are_labelled_with_the_area_and_nr_modes_of_their_artifacts(client):
    # As the Favourites Filters of Scoring & GAP Analysis: a job of a favourite takes its common filters (every favourite
    # when it chooses none), with the only Region, Cluster, City, Operator or Vendor filtered, or All.
    favourites = {'7': {'nr_mode': 'NSA', 'regions': [], 'cities': ['London'], 'main_cities': False},
                  '8': {'nr_mode': 'SA', 'regions': ['Vendor A', 'VMO2 North'], 'cities': [], 'main_cities': False},
                  '9': {'nr_mode': 'NSA', 'regions': [], 'cities': [], 'main_cities': False}}
    london = {'modules': {'bundle_report_template': {'enabled': True, 'options': {'filters': {'favourites': ['7']}}}}}
    assert report_tasks.job_scope(london, favourites) == {
        'scopes': [{'dimension': 'city', 'text': 'London', 'title': 'City: London'}], 'nr_modes': ['NSA']}
    every = report_tasks.job_scope({'modules': {'bundle_report_template': {'enabled': True, 'options': {}}}}, favourites)
    assert [scope['text'] for scope in every['scopes']] == ['London', 'Vendor A, VMO2 North', 'Nationwide']
    assert every['nr_modes'] == ['NSA', 'SA']
    # Manual artifacts: each Network Insights entry, Dashboard, Scoring scenario (Main Cities a City) and module gives its
    # area once (whatever the case), none when it filters several fields, and the NR Modes of the job (NSA vs SA too).
    manual = {'network_insights': [{'selection': {'nr_mode': 'SA', 'cities': ['London']}}],
              'dashboards': [{'filters': {'Campaign': ['@latest-campaign']}}],
              'scoring': [{'nr_mode': 'NSA+SA', 'report': {'scenarios': [
                  {'context_filters': {}}, {'context_filters': {'City': ['LONDON']}}, {'context_filters': {}, 'main_cities': True},
                  {'context_filters': {'City': ['Leeds'], 'Operator': ['EE']}}]}}],
              'modules': {'non_qualified_calls': {'enabled': True, 'options': {'filters': {'nr_mode': ['NSA'], 'region': ['Vendor B']}}}}}
    result = report_tasks.job_scope(manual)
    assert [(scope['dimension'], scope['text']) for scope in result['scopes']] == [
        ('city', 'London'), ('all', 'Nationwide'), ('city', 'Main Cities'), ('region', 'Vendor B')]
    assert result['nr_modes'] == ['NSA', 'SA', 'NSA+SA']
    # The jobs table receives them with each job and shows them on top of its name.
    login(client)
    client.post('/api/reporting/tasks', json={'name': 'Labelled', 'schedule': {'mode': 'manual'},
                                              'definition': {'scoring': [SCORING_ENTRY]}}).raise_for_status()
    task = next(item for item in client.get('/api/reporting/state').json()['tasks'] if item['name'] == 'Labelled')
    assert task['nr_modes'] == ['NSA'] and task['scopes'][0]['dimension'] == 'all'
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    styles = (core.PROJECT_ROOT / 'src/web_interface/static/css/report_jobs.css').read_text(encoding='utf-8')
    assert 'const tabs = scopeTabs(task);' in script and "label.dataset.nrMode = mode === 'NSA+SA' ? 'nsa-vs-sa' : mode.toLowerCase();" in script
    # The NR Modes on the line of the modules, after a separator.
    assert "if (modes.length && line.childElementCount) line.append(node('span', undefined, 'rj-task-separator'));" in script
    assert '.report-jobs .rj-task-scope[data-dimension="city"] { border-color: #b06d00; background: #b06d00; }' in styles


def test_jobs_name_their_modules_abbreviated_and_move_or_delete_several_at_once(client):
    # The modules a job generates artifacts of: its own and the sections of the favourites it generates (every favourite
    # when it chooses none), in the order of the sections, CDR Analysis last.
    favourites = {'7': ['network_insights', 'scoring'], '8': ['dashboards']}
    favourite = {'modules': {'bundle_report_template': {'enabled': True, 'options': {'filters': {'favourites': ['7']}}}}}
    assert report_tasks.job_modules(favourite, favourites) == ['scoring', 'network_insights']
    every = {'modules': {'bundle_report_template': {'enabled': True, 'options': {}}}}
    assert report_tasks.job_modules(every, favourites) == ['scoring', 'network_insights', 'dashboards']
    manual = {'dataset_analysis': {'enabled': True}, 'dashboards': [{'dashboard_id': 'a'}], 'scoring': [SCORING_ENTRY],
              'modules': {'non_qualified_calls': {'enabled': True}}}
    assert report_tasks.job_modules(manual) == ['scoring', 'non_qualified_calls', 'dashboards', 'dataset_analysis']
    login(client)
    client.post('/api/reporting/tasks', json={'name': 'Modules', 'schedule': {'mode': 'manual'},
                                              'definition': {'scoring': [SCORING_ENTRY]}}).raise_for_status()
    task = next(item for item in client.get('/api/reporting/state').json()['tasks'] if item['name'] == 'Modules')
    assert task['modules'] == ['scoring']
    page = (core.PROJECT_ROOT / 'src/web_interface/templates/report_jobs.html').read_text(encoding='utf-8')
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    styles = (core.PROJECT_ROOT / 'src/web_interface/static/css/report_jobs.css').read_text(encoding='utf-8')
    # On the first line of the name, always on one line: the box of the job and its modules abbreviated.
    assert "const MODULE_TAGS = {scoring: 'SCO', network_insights: 'NI', non_qualified_calls: 'NQ', dashboards: 'PPT', dataset_analysis: 'CDR'};" in script
    assert '.report-jobs .rj-task-modules { display: flex; flex-wrap: nowrap;' in styles
    assert '#rj-tasks th:nth-child(1), #rj-tasks td:nth-child(1) { width: 18rem;' in styles
    # The box that selects a job sits on top of the tab on the left of its name, by which it is dragged.
    assert "if (state.can_edit) nameCell.append(dragHandle(), taskCheck(task));" in script
    assert '.report-jobs .rj-drag-handle { position: absolute; top: .55rem; bottom: .55rem;' in styles
    assert '.report-jobs .rj-task-check-box { position: absolute; z-index: 1; top: .55rem;' in styles
    # The area labels stay on one line too (the column widens for them), and the campaigns of the job follow on a line of
    # their own: each choice once, after the modules that make it when they choose differently.
    assert 'text-overflow: ellipsis; white-space: nowrap; }' in styles.split('.report-jobs .rj-task-scope, .report-jobs .rj-task-mode {', 1)[1].split('\n', 1)[0]
    campaigns = {'7': [('scoring', ['@latest-2-campaigns']), ('network_insights', ['@latest-campaign']),
                       ('non_qualified_calls', []), ('dashboards', ['@latest-2-campaigns'])]}
    assert report_tasks.job_campaigns(favourite, campaigns) == [
        {'campaigns': 'Latest 2 campaigns', 'modules': ['scoring', 'dashboards']},
        {'campaigns': 'Latest campaign', 'modules': ['network_insights']},
        {'campaigns': 'All campaigns', 'modules': ['non_qualified_calls']}]
    assert report_tasks.job_campaigns({'scoring': [{'campaigns': ['@all-campaigns']}, {'campaigns': []}],
                                       'dashboards': [{'filters': {'Campaign': ['UK_Q2_2026', 'UK_Q3_2026']}}]}) == [
        {'campaigns': 'All campaigns', 'modules': ['scoring']}, {'campaigns': '2026-Q2, 2026-Q3', 'modules': ['dashboards']}]
    assert task['campaigns'] == [{'campaigns': 'Latest campaign', 'modules': ['scoring']}]
    assert "const modules = choices.length > 1 ? choice.modules.map((key) => MODULE_TAGS[key] || key.slice(0, 3).toUpperCase()).join(' · ') : '';" in script
    # The actions in a light toolbar of icon buttons (an icon of its own for each, in the colour of its action), and the
    # times of Next Run and Last Run below their dates, leave the room to Artifacts.
    assert '.reporting-jobs-table .table-actions.rj-task-actions { display: inline-flex; flex-wrap: nowrap;' in styles
    assert 'width: 1.75rem; min-width: 1.75rem; height: 1.75rem; min-height: 0; padding: 0; border: 0; border-radius: 7px; background: transparent;' in styles
    assert all(f'.report-jobs #rj-tasks .rj-task-actions {selector} {{ --rj-icon: url("data:image/svg+xml,' in styles for selector in (
        '[aria-label="Run now"]', '[aria-label="Edit"]', '[aria-label="Duplicate (disabled copy)"]',
        '[aria-label="Delete the job and its runs"]'))
    # The runs of the Run History share the toolbar and the download of the jobs, with icons of their own for Rerun, Stop and
    # Delete.
    assert "const actions = node('div', undefined, 'table-actions rj-task-actions');" in script
    assert '.report-jobs :is(#rj-tasks, #rj-runs) .rj-task-actions .rj-download { --rj-icon: url("data:image/svg+xml,' in styles
    assert all(f'.report-jobs #rj-runs .rj-task-actions {selector} {{ --rj-action:' in styles
               for selector in ('.rj-rerun', '.rj-run-delete'))
    assert '.report-jobs :is(#rj-tasks, #rj-runs) .rj-task-actions .rj-stop { --rj-action:' in styles
    assert "const lastCell = timeCell(last ? last.started_at || last.created_at : '');" in script
    assert "task.enabled ? timeCell(task.next_run_at) : node('td', 'Disabled')" in script
    assert '.report-jobs #rj-tasks th:nth-child(2) { width: 38%; }' in styles
    # Select all, Move Up, Move Down and Delete, as on the Favourites Filters, in a bar that stays at the top.
    assert '<input type="checkbox" id="rj-select-all"> Select all' in page
    assert 'data-rj-move="up"' in page and 'data-rj-move="down"' in page and 'id="rj-delete-selected"' in page
    assert 'function movedTaskOrder(order, step) {' in script and 'void saveOrder();' in script
    assert '.report-jobs .rj-bulk { position: sticky;' in styles and '.report-jobs .rj-bulk.is-stuck::before {' in styles
    assert '.report-jobs details.collapsible-panel:has(> .collapsible-panel-body > .rj-bulk) { overflow: clip; }' in styles
    # The checked jobs are deleted together after one confirmation that names them, none of them while one belongs to
    # another user.
    assert "await api('/api/reporting/tasks/delete', {method: 'POST', body: JSON.stringify({ids: targets.map((task) => task.id)})});" in script
    assert "const refused = targets.filter((task) => !(window.canDeleteShared?.(task.created_by) ?? true));" in script
    assert "syncBulkButton(deleteCheckedTasks, 'Delete', checked, (task) => window.canDeleteShared?.(task.created_by) ?? true, deletingCheckedTasks);" in script
    assert "button.textContent = on ? `${label} (${items.length})` : label;" in script


def test_reporting_page_keeps_its_scroll_position_when_reloaded():
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    assert "const SCROLL_KEY = 'drivetest-analyzer:/reporting:scroll';" in script
    assert "['reload', 'back_forward'].includes(navigation)" in script
    # An editor reopened by the reload does not move the page to it.
    assert "if (!followingScroll) editor.scrollIntoView({behavior: 'smooth', block: 'start'});" in script


def test_imported_reporting_jobs_find_their_favourites_by_name(client):
    from src.modules import bundle_report_templates
    login(client)
    weekly = bundle_report_templates.save_favourite(core.repository, None, 'Weekly', {}, 'super')
    monthly = bundle_report_templates.save_favourite(core.repository, None, 'Monthly', {'sections': [{'key': 'scoring', 'enabled': False}]}, 'super')
    report = {'enabled': True, 'formats': ['word'], 'options': {'filters': {'favourites': [str(monthly['id'])]}}}
    client.post('/api/reporting/tasks', json={'name': 'Monthly job', 'schedule': {'mode': 'manual'},
                                              'definition': {'modules': {'bundle_report_template': report}}}).raise_for_status()
    exported = json.loads(report_tasks.export_tasks_document(core.repository))
    assert exported['favourite_names'] == {str(monthly['id']): 'Monthly'}
    # In another workspace the favourites have other IDs: the job takes the one of the same name.
    with core.repository.connection() as connection:
        connection.execute(f'DELETE FROM {bundle_report_templates.BUNDLE_REPORT_TEMPLATES_TABLE}')
    bundle_report_templates.save_favourite(core.repository, None, 'Other', {}, 'super')
    here = bundle_report_templates.save_favourite(core.repository, None, 'monthly', {}, 'super')
    assert here['id'] not in {weekly['id'], monthly['id']}
    assert core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(exported).encode(), 'super') >= 1
    job = next(task for task in report_tasks.list_tasks(core.repository) if task['name'] == 'Monthly job')
    assert job['definition']['modules']['bundle_report_template']['options']['filters']['favourites'] == [str(here['id'])]
    state = client.get('/api/reporting/state').json()
    listed = next(task for task in state['tasks'] if task['name'] == 'Monthly job')
    assert listed['based_on'] == 'favourite'
    assert listed['artifact_groups'][-1]['items'] == ['monthly (Word)']
    assert listed['artifact_groups'][-1]['contents'][0][0]['title'] == 'Scoring & GAP Analysis'
    # A favourite the destination does not have is kept by name (never every favourite) and found once it is there;
    # documents without names keep the IDs.
    exported['favourite_names'] = {str(monthly['id']): 'Missing'}
    core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(exported).encode(), 'super')
    job = next(task for task in report_tasks.list_tasks(core.repository) if task['name'] == 'Monthly job')
    assert job['definition']['modules']['bundle_report_template']['options']['filters']['favourites'] == ['Missing']
    missing = report_tasks.export_tasks_document(core.repository)
    found = bundle_report_templates.save_favourite(core.repository, None, 'Missing', {}, 'super')
    core._restore_workspace_reporting_jobs(core.active_workspace, missing, 'super')
    job = next(task for task in report_tasks.list_tasks(core.repository) if task['name'] == 'Monthly job')
    assert job['definition']['modules']['bundle_report_template']['options']['filters']['favourites'] == [str(found['id'])]
    del exported['favourite_names']
    core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(exported).encode(), 'super')
    job = next(task for task in report_tasks.list_tasks(core.repository) if task['name'] == 'Monthly job')
    assert job['definition']['modules']['bundle_report_template']['options']['filters']['favourites'] == [str(monthly['id'])]


def test_deleting_a_favourite_disables_the_jobs_based_on_it(client):
    from src.modules import bundle_report_templates
    login(client)
    weekly = bundle_report_templates.save_favourite(core.repository, None, 'Weekly', {}, 'super')
    other = bundle_report_templates.save_favourite(core.repository, None, 'Other', {}, 'super')
    report = lambda *ids: {'enabled': True, 'formats': ['word'], 'options': {'filters': {'favourites': [str(value) for value in ids]}}}
    based = client.post('/api/reporting/tasks', json={'name': 'Weekly', 'schedule': {'mode': 'daily', 'time': '08:00'},
                                                      'definition': {'modules': {'bundle_report_template': report(weekly['id'])}}}).json()['task']
    both = client.post('/api/reporting/tasks', json={'name': 'Both', 'schedule': {'mode': 'manual'},
                                                     'definition': {'modules': {'bundle_report_template': report(weekly['id'], other['id'])}}}).json()['task']
    jobs = client.get(f"/api/reporting/bundle-report-template/favourites/{weekly['id']}/jobs").json()
    assert jobs == {'based_on': ['Weekly'], 'others': ['Both']}
    response = client.delete(f"/api/reporting/bundle-report-template/favourites/{weekly['id']}")
    assert response.status_code == 200 and response.json()['disabled_jobs'] == ['Weekly']
    tasks = {task['id']: task for task in client.get('/api/reporting/state').json()['tasks']}
    # The job based on it is disabled and both name it as no longer existing (never every favourite).
    assert tasks[based['id']]['enabled'] is False and tasks[based['id']]['next_run_at'] is None
    assert tasks[both['id']]['enabled'] is True
    assert tasks[based['id']]['definition']['modules']['bundle_report_template']['options']['filters']['favourites'] == ['Weekly']
    group = tasks[based['id']]['artifact_groups'][-1]
    assert group['items'] == ['Weekly (Word)'] and group['missing'] == [True]
    assert tasks[both['id']]['artifact_groups'][-1]['missing'] == [True, False]
    actions = [row['action'] for row in core.repository.list_logs(limit=20)] if hasattr(core.repository, 'list_logs') else []
    if actions:
        assert 'bundle_report_template_favourite_deleted' in actions and 'disable_reporting_job' in actions
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    assert "'The associated Bundle Report Template no longer exists.'" in script


def test_renaming_a_favourite_renames_the_jobs_based_on_it(client):
    from src.modules import bundle_report_templates
    login(client)
    weekly = bundle_report_templates.save_favourite(core.repository, None, 'Weekly', {}, 'super')
    bundle_report_templates.save_favourite(core.repository, None, 'Taken', {}, 'super')
    report = {'enabled': True, 'formats': ['word'], 'options': {'filters': {'favourites': [str(weekly['id'])]}}}
    ids = [client.post('/api/reporting/tasks', json={'name': name, 'schedule': {'mode': 'manual'},
                                                     'definition': {'modules': {'bundle_report_template': report}}}).json()['task']['id']
           for name in ('Weekly', 'My weekly job')]
    # A job that also generates other artifacts keeps its name.
    other = client.post('/api/reporting/tasks', json={'name': 'Everything', 'schedule': {'mode': 'manual'}, 'definition': {
        'modules': {'bundle_report_template': report}, 'scoring': [SCORING_ENTRY]}}).json()['task']['id']
    assert client.post(f"/api/reporting/bundle-report-template/favourites/{weekly['id']}/rename", json={'name': 'Taken'}).status_code == 400
    response = client.post(f"/api/reporting/bundle-report-template/favourites/{weekly['id']}/rename", json={'name': 'Weekly NetCheck'})
    assert response.status_code == 200, response.text
    assert response.json()['favourite']['name'] == 'Weekly NetCheck'
    assert response.json()['renamed_jobs'] == ['Weekly NetCheck', 'Weekly NetCheck']
    # Every job based on it takes the new name, also one that was given another name; all of them name the new favourite.
    tasks = {task['id']: task for task in client.get('/api/reporting/state').json()['tasks']}
    assert [tasks[task_id]['name'] for task_id in ids] == ['Weekly NetCheck', 'Weekly NetCheck']
    assert tasks[other]['name'] == 'Everything'
    assert tasks[ids[1]]['artifact_groups'][-1]['items'] == ['Weekly NetCheck (Word)']
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/bundle_report_template.js').read_text(encoding='utf-8')
    assert 'const named = (await jobsOf(selected)).based_on;' in script
    assert bundle_report_templates.get_favourite(core.repository, weekly['id'])['definition'] == weekly['definition']
    page = (core.PROJECT_ROOT / 'src/web_interface/templates/report_jobs.html').read_text(encoding='utf-8')
    assert 'id="brt-rename"' in page


def test_reporting_jobs_keep_the_order_they_are_dragged_to(client):
    login(client)
    names = [task['name'] for task in report_tasks.list_tasks(core.repository)]
    created = [client.post('/api/reporting/tasks', json={'name': name, 'schedule': {'mode': 'manual'},
                                                         'definition': {'scoring': [SCORING_ENTRY]}}).json()['task']['id']
               for name in ('Zulu', 'Alpha')]
    # New jobs go to the end, in the order they are created.
    assert [task['name'] for task in report_tasks.list_tasks(core.repository)] == [*names, 'Zulu', 'Alpha']
    response = client.post('/api/reporting/tasks/order', json={'ids': [created[1], created[0]]})
    assert response.status_code == 200
    order = [task['name'] for task in report_tasks.list_tasks(core.repository)]
    assert order == ['Alpha', 'Zulu', *names]
    # A copy follows its job.
    client.post(f'/api/reporting/tasks/{created[1]}/duplicate').raise_for_status()
    assert [task['name'] for task in report_tasks.list_tasks(core.repository)][:3] == ['Alpha', 'Alpha (copy)', 'Zulu']
    # The order travels with the jobs: an import puts them in their order, before the jobs only this workspace has.
    exported = json.loads(report_tasks.export_tasks_document(core.repository))
    assert [item['position'] for item in exported['reporting_jobs']] == list(range(1, len(exported['reporting_jobs']) + 1))
    client.post('/api/reporting/tasks/order', json={'ids': list(reversed([task['id'] for task in report_tasks.list_tasks(core.repository)]))})
    client.post('/api/reporting/tasks', json={'name': 'Only here', 'schedule': {'mode': 'manual'}, 'definition': {'scoring': [SCORING_ENTRY]}})
    core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(exported).encode(), 'super')
    assert [task['name'] for task in report_tasks.list_tasks(core.repository)] == [item['name'] for item in exported['reporting_jobs']] + ['Only here']
    actions = [str(row['action']) for row in core.repository.list_logs(limit=50)] if hasattr(core.repository, 'list_logs') else []
    if actions:
        assert 'reorder_reporting_jobs' in actions
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    assert "api('/api/reporting/tasks/order', {method: 'POST', body: JSON.stringify({ids})})" in script


def test_jobs_saved_before_the_order_keep_their_alphabetical_order(tmp_path):
    import sqlite3

    class Repository:
        def __init__(self, path):
            self.path = path

        def connection(self):
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            return _Committing(connection)

    class _Committing:
        def __init__(self, connection):
            self.inner = connection

        def __enter__(self):
            return self.inner

        def __exit__(self, kind, *_args):
            if kind is None:
                self.inner.commit()
            self.inner.close()

    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE report_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, definition_json TEXT NOT NULL DEFAULT '{}', "
                           "send_email INTEGER NOT NULL DEFAULT 1, recipients_json TEXT NOT NULL DEFAULT '[]', schedule_json TEXT NOT NULL DEFAULT '{}', "
                           "enabled INTEGER NOT NULL DEFAULT 1, next_run_at TEXT, last_run_id INTEGER, created_by TEXT NOT NULL, created_at TEXT NOT NULL, "
                           "updated_at TEXT NOT NULL)")
        for name in ('Charlie', 'alpha', 'Bravo'):
            connection.execute("INSERT INTO report_tasks (name, created_by, created_at, updated_at) VALUES (?, 'super', '', '')", (name,))
    repository = Repository(path)
    assert [task['name'] for task in report_tasks.list_tasks(repository)] == ['alpha', 'Bravo', 'Charlie']
    assert [task['position'] for task in report_tasks.list_tasks(repository)] == [1, 2, 3]


def test_jobs_saved_before_store_one_theme(tmp_path):
    # Jobs saved when each artifact had its own theme (or none) store the default theme of the job, once, and those saved
    # when Bundle Report Templates had a former name their current artifact key.
    from src.modules.repository import Repository
    from src.modules.scoring_themes import DEFAULT_THEME

    repository = Repository(tmp_path / 'workspace.db')
    with repository.connection() as connection:
        connection.executescript(report_tasks.SCHEMA)
        for name, definition in (
                ('Legacy', {'network_insights': [{'formats': ['powerpoint'], 'theme': 'umlaut'}],
                            'scoring': [{'report': {'scenarios': [], 'theme': 'netcheck'}}]}),
                ('Chosen', {'theme': 'midnight', 'network_insights': [{'formats': ['powerpoint']}]}),
                ('Former', {'theme': 'paper', 'modules': {'complete_report': {'enabled': True, 'formats': ['word']}}})):
            connection.execute(f'INSERT INTO {report_tasks.REPORT_TASKS_TABLE} (name, definition_json, created_by, created_at, updated_at) '
                               "VALUES (?, ?, 'super', '2026-10-18', '2026-10-18')", (name, json.dumps(definition)))
    report_tasks.ensure_report_task_tables(repository)
    with repository.connection() as connection:
        stored = {row['name']: json.loads(row['definition_json']) for row in connection.execute(
            f'SELECT name, definition_json FROM {report_tasks.REPORT_TASKS_TABLE}')}
    assert stored['Legacy']['theme'] == DEFAULT_THEME == 'ericsson'
    assert 'theme' not in stored['Legacy']['network_insights'][0] and 'theme' not in stored['Legacy']['scoring'][0]['report']
    assert stored['Chosen']['theme'] == 'midnight'
    assert stored['Former']['modules'] == {'bundle_report_template': {'enabled': True, 'formats': ['word']}}


def test_nsa_vs_sa_scoring_entries_show_each_nr_mode_as_chosen(client, monkeypatch):
    definition = normalize_definition({'scoring': [
        {**SCORING_ENTRY, 'nr_mode': 'NSA+SA', 'nr_layout': 'grouped', 'nr_charts': 'separate',
         'report': {**default_report_configuration(), 'nr_layout': 'interleaved'}},
        {**SCORING_ENTRY, 'nr_layout': 'other'}]})
    nsa_vs_sa, nsa = definition['scoring']
    assert (nsa_vs_sa['nr_layout'], nsa_vs_sa['nr_charts']) == ('grouped', 'separate')
    # Each panel: NSA then SA and NSA & SA in the same chart by default; the entry chooses them, not its report.
    assert (nsa['nr_layout'], nsa['nr_charts']) == ('interleaved', 'same') and 'nr_layout' not in nsa_vs_sa['report']
    reports = []
    monkeypatch.setattr(report_tasks, 'complete_campaign_cdrs', lambda *_args: ([11, 12, 13], []))

    def build(repository, base, report, username):
        reports.append((base['nr_mode'], report))
        return b'pptx', 'Scoring.pptx', {'dataset_ids': base['dataset_ids'], 'nr_mode': base['nr_mode']}

    monkeypatch.setattr(core, 'build_scoring_report_document', build)
    login(client)
    payload = {'name': 'NSA vs SA views', 'schedule': {'mode': 'manual'}, 'definition': {'scoring': [
        {**SCORING_ENTRY, 'nr_mode': 'NSA+SA', 'auto_cdrs': True, 'nr_layout': 'grouped', 'nr_charts': 'separate'},
        {**SCORING_ENTRY, 'auto_cdrs': True}]}}
    created = client.post('/api/reporting/tasks', json=payload)
    assert created.status_code == 200, created.text
    wait_for_run(client, client.post(f"/api/reporting/tasks/{created.json()['task']['id']}/run").json()['run_id'])
    (mode, report), (_mode, single) = reports
    assert mode == 'NSA+SA' and (report['nr_layout'], report['nr_charts']) == ('grouped', 'separate')
    assert 'nr_layout' not in single
    options = client.get('/api/reporting/options').json()
    assert options['nr_layouts'] == [['interleaved', 'Each panel: NSA then SA'], ['grouped', 'All NSA, then all SA']]
    # The editor offers both choices while NR Mode is NSA vs SA.
    script = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    assert "const syncNrViews = () => { nrViews.hidden = nrMode.value !== 'NSA+SA'; };" in script
    assert 'nr_layout: nrLayout.value, nr_charts: nrCharts.value,' in script


def test_the_jobs_table_enables_and_disables_a_job_with_its_switch(client):
    login(client)
    task = client.post('/api/reporting/tasks', json={'name': 'Switched', 'schedule': {'mode': 'daily', 'time': '08:00'},
                                                     'definition': {'scoring': [SCORING_ENTRY]}}).json()['task']
    assert task['enabled'] is True and task['next_run_at']
    response = client.post(f"/api/reporting/tasks/{task['id']}/enabled", json={'enabled': False})
    assert response.status_code == 200 and response.json()['task']['enabled'] is False
    assert response.json()['task']['next_run_at'] is None
    assert client.post(f"/api/reporting/tasks/{task['id']}/enabled", json={'enabled': True}).json()['task']['enabled'] is True
    actions = [row['action'] for row in core.repository.list_logs(limit=10)] if hasattr(core.repository, 'list_logs') else []
    if actions:
        assert 'disable_reporting_job' in actions and 'enable_reporting_job' in actions
    # The table shows the switch in its own column, before the actions (which no longer have ⏸ / ⏵).
    page = (core.PROJECT_ROOT / 'src/web_interface/templates/report_jobs.html').read_text(encoding='utf-8')
    assert '<th>Status</th><th>Enable/Disable</th><th>Actions</th>' in page
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    assert "const switchLabel = node('label', undefined, 'rj-enabled-switch rj-table-switch');" in script
    assert 'lastCell, statusCell, cellWith(switchLabel), cellWith(actions),' in script
    assert "'Disable the schedule'" not in script and "emptyRow(body, 'No Reporting Jobs yet.', 10);" in script


def test_checked_jobs_and_runs_run_stop_download_and_delete_from_a_toolbar(client):
    login(client)
    page = client.get('/reporting').text
    for button in ('data-rj-move="up"', 'id="rj-run-selected"', 'id="rj-stop-tasks-selected"', 'id="rj-download-selected"',
                   'id="rj-delete-selected"', 'id="rj-rerun-selected"', 'id="rj-stop-selected"', 'id="rj-download-runs-selected"',
                   'id="rj-delete-runs-selected"'):
        assert button in page
    assert page.count('class="bulk-toolbar" role="toolbar"') == 2
    script = (Path(__file__).parents[1] / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    # Each button acts only when every checked job or run has that button on in its row.
    assert 'const on = !busy && items.length > 0 && items.every(test);' in script
    assert "syncBulkButton(stopCheckedTasks, 'Stop', checked, (task) => taskStoppableRuns(task).length > 0, deletingCheckedTasks);" in script
    assert "syncBulkButton(downloadCheckedRuns, 'Download', checked, runDownloadable, actingOnCheckedRuns);" in script
    assert "actionButton('■', 'Stop its queued or running run', () => stopRuns(taskStoppableRuns(task)), 'icon-action rj-stop')" in script
    styles = (Path(__file__).parents[1] / 'src/web_interface/static/css/app.css').read_text(encoding='utf-8')
    assert all(f'.bulk-toolbar .bulk-action-{name} {{' in styles for name in ('up', 'down', 'run', 'stop', 'download', 'rerun', 'newer', 'delete'))


def test_several_runs_download_in_one_zip_with_a_folder_each(client):
    def generate(config, folder, stamp, user):
        path = folder / f'{stamp} - Fake report.pptx'
        path.write_bytes(b'fake')
        return [{'module': 'fake', 'title': 'Fake report', 'file_name': path.name, 'size': 4, 'status': 'ready', 'details': []}]

    register_report_artifact_provider('fake', 'Fake module', 'datasets-analysis', generate)
    try:
        login(client)
        task = client.post('/api/reporting/tasks', json={
            'name': 'Zip check', 'definition': {'modules': {'fake': {'enabled': True}}},
            'schedule': {'mode': 'manual'}, 'enabled': True,
        }).json()['task']
        runs = [wait_for_run(client, client.post(f"/api/reporting/tasks/{task['id']}/run").json()['run_id']) for _ in range(2)]
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
    from src.modules import bundle_report_templates
    from src.modules.report_tasks import artifact_path

    assert bundle_report_templates.BUNDLE_REPORT_FILE_PREFIX == 'DT Analyzer Bundle Report'
    source = (Path(__file__).parents[1] / 'src/modules/bundle_report_templates.py').read_text(encoding='utf-8')
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
        task = client.post('/api/reporting/tasks', json={
            'name': 'Progress check', 'definition': {'modules': {'slow': {'enabled': True}}},
            'schedule': {'mode': 'manual'}, 'enabled': True,
        }).json()['task']
        run_id = client.post(f"/api/reporting/tasks/{task['id']}/run").json()['run_id']
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
