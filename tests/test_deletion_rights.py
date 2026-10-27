import json
from types import SimpleNamespace
from urllib.parse import quote

import src.DriveTestAnalyzer as core
from src.modules import saved_filters
from src.modules.deletion_rights import (
    PPT_DASHBOARDS, SCORING_METHODOLOGIES, SCORING_REPORT_CONFIGURATIONS, UNKNOWN_CREATOR_OWNER, assign_unknown_creators,
    can_delete, creator_of, creators, record_creator,
)
from src.modules.ppt_dashboards import STATE_KEY as DASHBOARDS_STATE_KEY
from src.modules.scoring_reports import (
    REPORT_CONFIGURATIONS_FORMAT, REPORT_CONFIGURATIONS_VERSION, default_report_configuration, default_scenario,
)
from tests.test_non_qualified_calls import login, workspace_user

REFUSAL = 'Only admins and super-admins, or the user who created it, can delete this'


def workspace_repository():
    return core.Repository(core.active_workspace.database_path, global_db_path=core.repository.global_db_path,
                           workspace_registry_db_path=core.workspace_registry.registry_path)


def team():
    """Two editors (alice and bob) and an admin (boss) of the open workspace."""
    workspace_user('alice', 'user-editor')
    workspace_user('bob', 'user-editor')
    workspace_user('boss', 'admin')


def add_saved_filter(repository, key, created_by):
    with repository.connection() as connection:
        cursor = connection.execute(
            f"INSERT INTO {saved_filters.SAVED_FILTERS_TABLE} (selection_key, name, nr_mode, created_by) VALUES (?, ?, 'NSA', ?)",
            (key, key, created_by))
        return int(cursor.lastrowid)


def saved_filter_ids(repository):
    with repository.connection() as connection:
        return {int(row[0]) for row in connection.execute(f'SELECT id FROM {saved_filters.SAVED_FILTERS_TABLE}')}


def test_admins_delete_everything_and_the_other_roles_what_they_created():
    editor = SimpleNamespace(role='user-editor', username='Alice')
    assert can_delete(editor, 'alice') and not can_delete(editor, 'bob')
    # Without a known creator only admins and super-admins delete it.
    assert not can_delete(editor, '') and not can_delete(editor, None)
    assert can_delete(SimpleNamespace(role='admin', username='boss'), 'bob')
    assert can_delete(SimpleNamespace(role='super-admin', username='super'), '')


def test_saved_filters_are_deleted_by_their_creator_or_an_admin(client):
    team()
    repository = workspace_repository()
    mine = add_saved_filter(repository, 'alice-filter', 'alice')
    theirs = add_saved_filter(repository, 'bob-filter', 'bob')
    unknown = add_saved_filter(repository, 'system-filter', 'system')

    login(client, 'bob', 'bob123')
    refused = client.delete(f'/api/scoring/saved-filters/{mine}')
    assert refused.status_code == 403 and REFUSAL in refused.json()['detail']
    # A bulk delete with one of another user deletes none of them.
    bulk = client.post('/api/scoring/saved-filters/delete', json={'ids': [theirs, mine]})
    assert bulk.status_code == 403 and 'alice-filter' in bulk.json()['detail']
    assert {mine, theirs, unknown} <= saved_filter_ids(repository)
    assert client.delete(f'/api/scoring/saved-filters/{theirs}').status_code == 200
    assert client.delete(f'/api/scoring/saved-filters/{unknown}').status_code == 403

    login(client, 'boss', 'boss123')
    assert client.post('/api/scoring/saved-filters/delete', json={'ids': [mine, unknown]}).status_code == 200
    assert not {mine, theirs, unknown} & saved_filter_ids(repository)


def test_a_saved_filter_belongs_to_the_user_who_starred_it(client):
    team()
    repository = workspace_repository()
    starred = add_saved_filter(repository, 'starred', 'bob')
    loose = add_saved_filter(repository, 'loose', 'bob')
    prepared = {'snapshot': {}, 'result_key': 'r', 'method_version': 'm', 'source_fingerprint': 'f', 'dataset_ids': [],
                'levels': ['Operator'], 'nr_mode': 'NSA', 'baseline_operator': 'EE'}

    def owner(filter_id):
        with repository.connection() as connection:
            return connection.execute(
                f'SELECT created_by FROM {saved_filters.SAVED_FILTERS_TABLE} WHERE id = ?', (filter_id,)).fetchone()[0]

    # Calculated last by bob, starred by alice: it is hers.
    login(client, 'alice', 'alice123')
    assert client.patch(f'/api/scoring/saved-filters/{starred}', json={'pinned': True}).status_code == 200
    assert owner(starred) == 'alice'
    # Recalculating a starred one keeps who starred it; one not starred belongs to whoever calculates it, but not to the
    # application.
    with repository.connection() as connection:
        saved_filters._queue_calculation(connection, starred, prepared, 'bob', 'now')
        saved_filters._queue_calculation(connection, loose, prepared, 'system', 'now')
    assert owner(starred) == 'alice' and owner(loose) == 'bob'
    with repository.connection() as connection:
        saved_filters._queue_calculation(connection, loose, prepared, 'boss', 'now')
    assert owner(loose) == 'boss'
    # Starring it again (once unstarred) gives it to who stars it; renaming does not.
    login(client, 'bob', 'bob123')
    assert client.patch(f'/api/scoring/saved-filters/{starred}', json={'name': 'Renamed'}).status_code == 200
    assert client.patch(f'/api/scoring/saved-filters/{starred}', json={'pinned': True}).status_code == 200
    assert owner(starred) == 'alice'
    assert client.delete(f'/api/scoring/saved-filters/{starred}').status_code == 403
    # Nor does bob unstar it (unstarred, it would go once another one is used); an admin does.
    refused = client.patch(f'/api/scoring/saved-filters/{starred}', json={'pinned': False})
    assert refused.status_code == 403 and 'who starred it' in refused.json()['detail']
    assert saved_filters.get_saved_filter(repository, starred)['pinned']
    login(client, 'boss', 'boss123')
    assert client.patch(f'/api/scoring/saved-filters/{starred}', json={'pinned': False}).status_code == 200
    assert not saved_filters.get_saved_filter(repository, starred)['pinned']


def test_report_configurations_are_deleted_by_whoever_saved_or_imported_them(client):
    team()
    configuration = {'scenarios': [default_scenario(name='National')]}
    login(client, 'alice', 'alice123')
    saved = client.post('/api/scoring/report-configurations', json={'name': 'Alice report', 'configuration': configuration})
    assert saved.status_code == 200, saved.text
    listed = {item['name']: item['created_by'] for item in saved.json()['configurations']}
    assert listed['Alice report'] == 'alice'

    login(client, 'bob', 'bob123')
    refused = client.delete(f"/api/scoring/report-configurations?name={quote('Alice report')}")
    assert refused.status_code == 403 and REFUSAL in refused.json()['detail']
    # Replacing them all with a file that leaves it out would delete it: refused too.
    document = json.dumps({'format': REPORT_CONFIGURATIONS_FORMAT, 'version': REPORT_CONFIGURATIONS_VERSION,
                           'configurations': [{'name': 'Bob report', 'configuration': configuration}]}).encode()
    replaced = client.post('/api/scoring/report-configurations/import', data={'replace': 'true'},
                           files={'package': ('reports.json', document, 'application/json')})
    assert replaced.status_code == 403 and 'Alice report' in replaced.json()['detail']
    imported = client.post('/api/scoring/report-configurations/import',
                           files={'package': ('reports.json', document, 'application/json')})
    assert imported.status_code == 200, imported.text
    assert {item['name']: item['created_by'] for item in imported.json()['configurations']}['Bob report'] == 'bob'
    assert client.delete(f"/api/scoring/report-configurations?name={quote('Bob report')}").status_code == 200

    login(client, 'alice', 'alice123')
    assert client.delete(f"/api/scoring/report-configurations?name={quote('Alice report')}").status_code == 200
    assert creator_of(workspace_repository(), SCORING_REPORT_CONFIGURATIONS, 'Alice report') == ''


def test_scoring_methodologies_are_deleted_by_their_creator_or_an_admin(client):
    team()
    login(client, 'alice', 'alice123')
    profiles = client.get('/api/workspace-config/scoring-profiles').json()
    shipped = [profile['id'] for profile in profiles['profiles']]
    profiles['profiles'].append({'id': 'alice-method', 'name': 'Alice method',
                                 'configuration': profiles['profiles'][0]['configuration']})
    saved = client.put('/api/workspace-config/scoring-profiles', json=profiles)
    assert saved.status_code == 200, saved.text
    # The shipped ones belong to the default super-admin since the workspace opened.
    assert client.get('/api/workspace-config/scoring-methodology-creators').json() == {
        **dict.fromkeys(shipped, UNKNOWN_CREATOR_OWNER), 'alice-method': 'alice'}

    login(client, 'bob', 'bob123')
    without = {**saved.json(), 'profiles': [profile for profile in saved.json()['profiles'] if profile['id'] != 'alice-method']}
    refused = client.put('/api/workspace-config/scoring-profiles', json=without)
    assert refused.status_code == 403 and 'Alice method' in refused.json()['detail']

    login(client, 'alice', 'alice123')
    assert client.put('/api/workspace-config/scoring-profiles', json=without).status_code == 200
    assert creators(workspace_repository(), SCORING_METHODOLOGIES) == dict.fromkeys(shipped, UNKNOWN_CREATOR_OWNER)
    # Only admins remove the shipped ones.
    profiles = client.get('/api/workspace-config/scoring-profiles').json()
    assert len(shipped) > 1
    others = [profile for profile in profiles['profiles'] if profile['id'] != profiles['active_profile_id']]
    trimmed = {**profiles, 'profiles': [profile for profile in profiles['profiles'] if profile is not others[0]]}
    assert client.put('/api/workspace-config/scoring-profiles', json=trimmed).status_code == 403
    login(client, 'boss', 'boss123')
    assert client.put('/api/workspace-config/scoring-profiles', json=trimmed).status_code == 200


def test_favourites_and_reporting_jobs_are_deleted_by_their_creator_or_an_admin(client):
    team()
    login(client, 'alice', 'alice123')
    definition = client.get('/api/reporting/bundle-report-template/options').json()['defaults']
    favourite = client.post('/api/reporting/bundle-report-template/favourites', json={'name': 'Alice bundle', 'definition': definition})
    assert favourite.status_code == 200, favourite.text
    favourite_id = favourite.json()['favourite']['id']
    job = client.post('/api/reporting/tasks', json={
        'name': 'Alice job', 'schedule': {'mode': 'manual'},
        'definition': {'scoring': [{'nr_mode': 'NSA', 'report': default_report_configuration()}]}})
    assert job.status_code == 200, job.text
    job_id = job.json()['task']['id']

    login(client, 'bob', 'bob123')
    refused = client.delete(f'/api/reporting/bundle-report-template/favourites/{favourite_id}')
    assert refused.status_code == 403 and REFUSAL in refused.json()['detail']
    refused = client.delete(f'/api/reporting/tasks/{job_id}')
    assert refused.status_code == 403 and REFUSAL in refused.json()['detail']

    # Deleting several at once deletes none of them while one belongs to another user.
    own = client.post('/api/reporting/tasks', json={
        'name': 'Bob job', 'schedule': {'mode': 'manual'},
        'definition': {'scoring': [{'nr_mode': 'NSA', 'report': default_report_configuration()}]}}).json()['task']['id']
    refused = client.post('/api/reporting/tasks/delete', json={'ids': [own, job_id]})
    assert refused.status_code == 403 and 'Alice job' in refused.json()['detail']
    names = lambda: {task['name'] for task in client.get('/api/reporting/state').json()['tasks']}
    assert {'Alice job', 'Bob job'} <= names()
    assert client.post('/api/reporting/tasks/delete', json={'ids': [own]}).json() == {'deleted': [own]}

    login(client, 'alice', 'alice123')
    assert client.delete(f'/api/reporting/bundle-report-template/favourites/{favourite_id}').status_code == 200
    login(client, 'boss', 'boss123')
    assert client.post('/api/reporting/tasks/delete', json={'ids': [job_id]}).json() == {'deleted': [job_id]}
    assert not {'Alice job', 'Bob job'} & names()


def test_dashboards_are_deleted_by_their_creator_or_an_admin(client):
    team()
    repository = workspace_repository()
    repository.set_workspace_state(DASHBOARDS_STATE_KEY, json.dumps({
        'alice-dashboard': {'name': 'Alice dashboard', 'template': 'T'}, 'old-dashboard': {'name': 'Old', 'template': 'T'}}))
    record_creator(repository, PPT_DASHBOARDS, 'alice-dashboard', 'alice')

    login(client, 'bob', 'bob123')
    listed = client.get('/api/ppt-dashboards').json()
    assert listed['alice-dashboard']['created_by'] == 'alice' and listed['old-dashboard']['created_by'] == ''
    refused = client.delete('/api/ppt-dashboards/alice-dashboard')
    assert refused.status_code == 403 and REFUSAL in refused.json()['detail']
    assert client.delete('/api/ppt-dashboards/old-dashboard').status_code == 403

    login(client, 'alice', 'alice123')
    assert client.delete('/api/ppt-dashboards/alice-dashboard').status_code == 200
    assert creator_of(repository, PPT_DASHBOARDS, 'alice-dashboard') == ''
    login(client, 'boss', 'boss123')
    assert client.delete('/api/ppt-dashboards/old-dashboard').status_code == 200


def test_ppt_templates_are_deleted_by_their_creator_or_an_admin(client):
    team()
    with core.repository.connection() as connection:
        columns = {row[1] for row in connection.execute('PRAGMA table_info(report_templates)')}
    assert 'created_by' in columns
    login(client, 'alice', 'alice123')
    assert client.post('/workspace-config/slides-templates/new', follow_redirects=False).status_code == 303
    created = next(item for item in core.report_catalogue_options() if item['name'] == 'New Template')
    assert created['created_by'] == 'alice'
    delete_url = f"/workspace-config/report-templates/{quote(created['identifier'])}/delete"

    login(client, 'bob', 'bob123')
    page = client.get('/workspace-config').text
    assert 'title="Only admins and super-admins, or the user who created it, can delete this PPT Template"' in page
    refused = client.post(delete_url)
    assert refused.status_code == 403
    assert any(item['name'] == 'New Template' for item in core.report_catalogue_options())

    login(client, 'alice', 'alice123')
    assert client.post(delete_url, follow_redirects=False).status_code in {200, 303}
    assert not any(item['name'] == 'New Template' for item in core.report_catalogue_options())


def test_items_without_a_known_creator_are_assigned_to_the_default_super_admin(client):
    repository = workspace_repository()
    system_filter = add_saved_filter(repository, 'system-filter', 'system')
    owned_filter = add_saved_filter(repository, 'owned-filter', 'alice')
    repository.set_workspace_state(DASHBOARDS_STATE_KEY, json.dumps({'old-dashboard': {'name': 'Old', 'template': 'T'}}))
    # They go to the super-admin every deployment starts with (whether or not the account still exists).
    assert UNKNOWN_CREATOR_OWNER == 'super'
    assigned = assign_unknown_creators(repository)
    owner = UNKNOWN_CREATOR_OWNER
    assert assigned['saved_filters'] == 1 and assigned['ppt_dashboards'] == 1
    with repository.connection() as connection:
        owners = dict(connection.execute(f'SELECT id, created_by FROM {saved_filters.SAVED_FILTERS_TABLE}').fetchall())
        templates = {row[0] for row in connection.execute('SELECT created_by FROM report_templates')}
    assert owners[system_filter] == owner and owners[owned_filter] == 'alice'
    assert templates <= {owner}
    assert creator_of(repository, PPT_DASHBOARDS, 'old-dashboard') == owner
    # Every shipped report configuration and methodology now has a creator; a second pass changes nothing.
    assert all(creators(repository, SCORING_REPORT_CONFIGURATIONS).values())
    assert assign_unknown_creators(repository) == {}
