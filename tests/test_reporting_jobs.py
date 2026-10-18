import json
import time
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
    # Admins see Modules Profiles; viewers and editors do not change them.
    session(client, 'someone', 'admin')
    assert 'id="modules-profiles"' in client.get('/admin').text
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
        if run['status'] not in {'queued', 'running'}:
            return run
        time.sleep(0.1)
    raise AssertionError('The Reporting run did not finish.')


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
    assert owners == {'Owned by editor': 'editor', 'Owner from elsewhere': 'super', 'Older export': 'super',
                      **{name: 'system' for name in STARTER_JOBS}}
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
    assert 'id="workspace-groups"' in client.get('/admin').text
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
    page = client.get('/admin').text
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


def test_a_job_can_start_from_a_favourite_complete_report():
    definition = report_tasks.normalize_definition({'modules': {'complete_report': {
        'enabled': True, 'formats': ['powerpoint', 'word'], 'options': {'filters': {'favourites': ['7']}}}}})
    # The jobs table names the favourite the job generates (every one when it chooses none) with what it includes.
    contents = [{'title': 'Scoring & GAP Analysis', 'items': ['Summary', 'GAP Analysis']}]
    groups = report_tasks.artifact_groups(definition, {}, {'7': 'Weekly NetCheck'}, {'7': contents})
    assert groups == [{'module': 'Complete Report', 'items': ['Weekly NetCheck (PPT/Word)'], 'contents': [contents]}]
    assert report_tasks.based_on_favourite(definition)
    assert report_tasks.artifact_labels(definition, {}, {'7': 'Weekly NetCheck'}) == ['Complete Report · Weekly NetCheck (PPT/Word)']
    every = report_tasks.normalize_definition({'modules': {'complete_report': {'enabled': True, 'formats': ['powerpoint']}}})
    assert report_tasks.artifact_groups(every)[0]['items'] == ['Every favourite (PPT)']
    assert not report_tasks.based_on_favourite(every)
    assert not report_tasks.based_on_favourite({**definition, 'scoring': [SCORING_ENTRY]})
    page = (core.PROJECT_ROOT / 'src/web_interface/templates/report_jobs.html').read_text(encoding='utf-8')
    assert 'name="rj-source" value="favourite" checked' in page and 'name="rj-source" value="editor"' in page
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    # From a favourite, the job generates only its Complete Report; one that does opens as such in the editor.
    assert 'function favouriteDefinition(base)' in script and 'function favouriteOf(definition)' in script
    assert "if (jobSource() === 'favourite' && !$('rj-favourite')?.value)" in script
    # Based On tells a job of a favourite from one with artifacts chosen in the editor.
    assert '<th>Artifacts</th><th>Based On</th><th>Recurrence</th><th>Next Run</th>' in page and 'colspan="9"' in page
    assert "fromFavourite ? 'Complete Report' : 'Manual Artifacts'" in script and 'function favouriteContents(sections)' in script
    # The header of the panel counts the jobs of each kind.
    assert all(f'id="rj-count-{kind}"' in page for kind in ('total', 'favourite', 'manual'))
    assert "$('rj-count-manual').textContent = `Manual Artifacts: ${state.tasks.length - favourites}`;" in script


def test_reporting_page_keeps_its_scroll_position_when_reloaded():
    script = (core.PROJECT_ROOT / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    assert "const SCROLL_KEY = 'drivetest-analyzer:/reporting:scroll';" in script
    assert "['reload', 'back_forward'].includes(navigation)" in script
    # An editor reopened by the reload does not move the page to it.
    assert "if (!followingScroll) editor.scrollIntoView({behavior: 'smooth', block: 'start'});" in script


def test_imported_reporting_jobs_find_their_favourites_by_name(client):
    from src.modules import complete_reports
    login(client)
    weekly = complete_reports.save_favourite(core.repository, None, 'Weekly', {}, 'super')
    monthly = complete_reports.save_favourite(core.repository, None, 'Monthly', {'sections': [{'key': 'scoring', 'enabled': False}]}, 'super')
    report = {'enabled': True, 'formats': ['word'], 'options': {'filters': {'favourites': [str(monthly['id'])]}}}
    client.post('/api/reporting/tasks', json={'name': 'Monthly job', 'schedule': {'mode': 'manual'},
                                              'definition': {'modules': {'complete_report': report}}}).raise_for_status()
    exported = json.loads(report_tasks.export_tasks_document(core.repository))
    assert exported['favourite_names'] == {str(monthly['id']): 'Monthly'}
    # In another workspace the favourites have other IDs: the job takes the one of the same name.
    with core.repository.connection() as connection:
        connection.execute(f'DELETE FROM {complete_reports.COMPLETE_REPORTS_TABLE}')
    complete_reports.save_favourite(core.repository, None, 'Other', {}, 'super')
    here = complete_reports.save_favourite(core.repository, None, 'monthly', {}, 'super')
    assert here['id'] not in {weekly['id'], monthly['id']}
    assert core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(exported).encode(), 'super') >= 1
    job = next(task for task in report_tasks.list_tasks(core.repository) if task['name'] == 'Monthly job')
    assert job['definition']['modules']['complete_report']['options']['filters']['favourites'] == [str(here['id'])]
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
    assert job['definition']['modules']['complete_report']['options']['filters']['favourites'] == ['Missing']
    missing = report_tasks.export_tasks_document(core.repository)
    found = complete_reports.save_favourite(core.repository, None, 'Missing', {}, 'super')
    core._restore_workspace_reporting_jobs(core.active_workspace, missing, 'super')
    job = next(task for task in report_tasks.list_tasks(core.repository) if task['name'] == 'Monthly job')
    assert job['definition']['modules']['complete_report']['options']['filters']['favourites'] == [str(found['id'])]
    del exported['favourite_names']
    core._restore_workspace_reporting_jobs(core.active_workspace, json.dumps(exported).encode(), 'super')
    job = next(task for task in report_tasks.list_tasks(core.repository) if task['name'] == 'Monthly job')
    assert job['definition']['modules']['complete_report']['options']['filters']['favourites'] == [str(monthly['id'])]
