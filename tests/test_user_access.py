"""Modules Profiles, Workspace Groups, the Users table and Users & Access in Import / Export / Transfer and Backup."""
import io
import json
import zipfile
from pathlib import Path

import src.DriveTestAnalyzer as core


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def user_id(username):
    return next(int(row['id']) for row in core.repository.list_users() if row['username'] == username)


def profile_of(username):
    return next((profile['name'] for profile in core.repository.list_modules_profiles() if user_id(username) in profile['member_ids']), None)


def groups_of(username):
    return sorted(group['name'] for group in core.repository.list_workspace_groups() if user_id(username) in group['member_ids'])


def test_former_user_groups_become_modules_profiles_and_workspace_groups(client):
    uk = core.workspace_registry.create('UK Drive')
    de = core.workspace_registry.create('DE Drive')
    for username, role in (('viewer', 'user-viewer'), ('editor', 'user-editor'), ('plain', 'user-editor'), ('boss', 'super-admin')):
        core.repository.create_user(username, 'secret123', role)
    ids = {row['username']: int(row['id']) for row in core.repository.list_users()}
    # The access model saved before Modules Profiles and Workspace Groups.
    module_groups = {'NQ Calls': 3, 'Benchmarking': 4, 'All Modules': 5}
    benchmarking = ['workspace', 'datasets-analysis', 'ppt-dashboards', 'scoring', 'network-insights', 'reporting', 'builders']
    rules = {key: {'default': 'all', 'allow': {'groups': [5, 4] + ([3] if key == 'workspace' else [])},
                   'deny': {'groups': [3] if key != 'workspace' else []}} for key in benchmarking}
    rules['non-qualified-calls'] = {'default': 'all', 'allow': {'groups': [5, 3]}, 'deny': {'groups': [4]}}
    rules['ppt-reporting-old'] = {'default': 'none', 'allow': {}, 'deny': {}}
    workspace_rules = {de.id: {'groups': [2], 'roles': []}, uk.id: {'groups': [1], 'roles': ['admin', 'super-admin']},
                       'workspace-deleted': {'groups': [1], 'roles': []}}
    with core.repository.global_connection() as conn:
        for table in ('modules_profiles', 'workspace_groups', 'workspace_group_members'):
            conn.execute(f'DELETE FROM {table}')
        conn.execute('UPDATE users SET modules_profile_id = NULL')
        conn.execute('CREATE TABLE user_groups (id INTEGER PRIMARY KEY, name TEXT, description TEXT, created_at TEXT)')
        conn.execute('CREATE TABLE user_group_members (group_id INTEGER, user_id INTEGER)')
        for group_id, name in ((1, 'UK'), (2, 'DE'), *((group_id, name) for name, group_id in module_groups.items())):
            conn.execute("INSERT INTO user_groups VALUES (?, ?, '', '')", (group_id, name))
        conn.executemany('INSERT INTO user_group_members VALUES (?, ?)', [
            (1, ids['viewer']), (3, ids['viewer']), (5, ids['editor']), (3, ids['editor']), (2, ids['boss']),
        ])
        conn.executemany('INSERT OR REPLACE INTO application_state (key, value) VALUES (?, ?)', [
            ('feature_activation_v1', json.dumps(rules)), ('workspace_access_rules_v1', json.dumps(workspace_rules)),
            ('module_access_groups_v1', '1'),
        ])
    core.repository.initialize()
    core.invalidate_module_access_cache()

    profiles = {profile['name']: profile for profile in core.repository.list_modules_profiles()}
    # Ticket Center (then Bugs Report), added to the tool after those groups, joins every profile.
    assert profiles['NQ Calls']['modules'] == ['workspace', 'non-qualified-calls', 'bugs-report']
    assert profiles['Benchmarking']['modules'] == [*benchmarking, 'bugs-report']
    assert profiles['All Modules']['is_default'] and 'ppt-reporting-old' not in profiles['All Modules']['modules']
    assert [profiles[name]['color'] for name in ('NQ Calls', 'Benchmarking', 'All Modules')] == ['#D74B75', '#1E61A3', '#096767']
    # One module group gives its profile; several give every module of them, and none the modules the user saw.
    assert (profile_of('viewer'), profile_of('editor'), profile_of('plain'), profile_of('boss')) == ('NQ Calls', 'All Modules', 'All Modules', None)
    groups = {group['name']: group for group in core.repository.list_workspace_groups()}
    assert set(groups) == {'UK', 'DE'}
    assert (groups['UK']['workspace_ids'], groups['DE']['workspace_ids']) == ([uk.id], [de.id])
    # Super-admins open every workspace, so groups never list them.
    assert (groups_of('viewer'), groups_of('boss')) == (['UK'], [])
    # The workspaces granted to a role become grants of its accounts.
    assert uk.id in core.repository.list_user_workspace_ids(ids['admin'])
    assert core.repository.user_has_workspace_access('viewer', uk.id) and not core.repository.user_has_workspace_access('viewer', de.id)
    assert core.user_has_feature(core.SessionUser(username='viewer', role='user-viewer'), 'non-qualified-calls')
    assert not core.user_has_feature(core.SessionUser(username='viewer', role='user-viewer'), 'scoring')
    with core.repository.global_connection() as conn:
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name IN ('user_groups', 'user_group_members')").fetchone()
        assert not conn.execute("SELECT 1 FROM application_state WHERE key IN ('feature_activation_v1', 'workspace_access_rules_v1')").fetchone()


def test_profile_and_group_cards_save_each_change(client):
    login(client)
    for username in ('ana', 'ben', 'cris'):
        core.repository.create_user(username, 'secret123', 'user-editor')
    profiles = {profile['name']: profile['id'] for profile in core.repository.list_modules_profiles()}
    nq = profiles['Non-Qualified Calls']
    core.repository.set_users_modules_profile([user_id('cris')], profiles['Benchmarking'])
    # Users added on a card leave their previous profile; one only removed gets the default profile, and a user
    # changed elsewhere since the page loaded keeps its change.
    response = client.post(f'/admin/modules-profiles/{nq}/update', data={
        'name': 'NQ Team', 'description': 'Analysts', 'modules': ['non-qualified-calls', 'workspace', 'unknown'], 'color': '#12ab9f',
        'member_ids': [user_id('ana'), user_id('ben')], 'initial_member_ids': [],
    })
    assert response.status_code == 200, response.text
    saved = next(profile for profile in response.json()['profiles'] if profile['id'] == nq)
    assert (saved['name'], saved['modules'], saved['member_ids']) == ('NQ Team', ['workspace', 'non-qualified-calls'], [user_id('ana'), user_id('ben')])
    assert saved['color'] == '#12AB9F' and 'style="--profile-color: #12AB9F"' in client.get('/admin').text
    client.post(f'/admin/modules-profiles/{nq}/update', data={
        'name': 'NQ Team', 'modules': ['workspace'], 'member_ids': [user_id('ben')], 'initial_member_ids': [user_id('ana'), user_id('ben'), user_id('cris')],
    })
    assert (profile_of('ana'), profile_of('ben'), profile_of('cris')) == ('All Modules', 'NQ Team', 'All Modules')
    assert client.post(f'/admin/modules-profiles/{nq}/update', data={'name': 'Benchmarking'}).status_code == 400
    # The default profile moves with Make default and cannot be deleted; deleting another gives its users the default.
    response = client.post(f'/admin/modules-profiles/{nq}/default')
    assert [profile['name'] for profile in response.json()['profiles'] if profile['is_default']] == ['NQ Team']
    assert 'cannot be deleted' in client.post(f'/admin/modules-profiles/{nq}/delete').text
    client.post(f"/admin/modules-profiles/{profiles['All Modules']}/delete", follow_redirects=False)
    assert (profile_of('ana'), profile_of('ben')) == ('NQ Team', 'NQ Team')
    # A Workspace Group card saves its workspaces and members the same way.
    group = core.repository.save_workspace_group(None, 'UK', '', [])
    response = client.post(f'/admin/workspace-groups/{group}/update', data={
        'name': 'UK', 'workspace_ids': [core.active_workspace.id, 'workspace-unknown'], 'member_ids': [user_id('ana')], 'initial_member_ids': [],
    })
    assert response.status_code == 200
    saved = next(item for item in response.json()['groups'] if item['id'] == group)
    assert (saved['workspace_ids'], saved['member_ids']) == ([core.active_workspace.id], [user_id('ana')])
    page = client.get('/admin').text
    assert 'data-access-card="profile"' in page and 'data-access-card="group"' in page
    assert 'class="access-chip"' in page and f'data-update-url="/admin/workspace-groups/{group}/update"' in page


def test_admins_change_only_the_workspaces_they_open(client):
    hidden = core.workspace_registry.create('Hidden')
    core.repository.create_user('boss', 'boss123', 'admin')
    core.repository.set_user_workspace_access(user_id('boss'), [core.active_workspace.id])
    group = core.repository.save_workspace_group(None, 'Mixed', '', [hidden.id])
    core.repository.create_user('field', 'field123', 'user-viewer')
    core.repository.set_user_workspace_access(user_id('field'), [hidden.id])
    login(client, 'boss', 'boss123')
    client.post(f'/admin/workspace-groups/{group}/update', data={'name': 'Mixed', 'workspace_ids': [core.active_workspace.id]})
    assert next(item for item in core.repository.list_workspace_groups() if item['id'] == group)['workspace_ids'] == sorted([hidden.id, core.active_workspace.id])
    response = client.post(f"/admin/users/{user_id('field')}/update", data={
        'username': 'field', 'role': 'user-viewer', 'active': '1', 'workspaces_submitted': '1', 'workspace_ids': [core.active_workspace.id],
    }, headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.status_code == 200
    assert core.repository.list_user_workspace_ids(user_id('field')) == sorted([hidden.id, core.active_workspace.id])


def test_the_selection_bar_changes_several_users_at_once(client):
    login(client)
    for username, role in (('ana', 'user-editor'), ('ben', 'user-viewer'), ('boss', 'super-admin')):
        core.repository.create_user(username, 'secret123', role)
    ids = [user_id('ana'), user_id('ben'), user_id('boss')]
    nq = next(profile['id'] for profile in core.repository.list_modules_profiles() if profile['name'] == 'Non-Qualified Calls')
    group = core.repository.save_workspace_group(None, 'UK', '', [core.active_workspace.id])
    response = client.post('/admin/users/bulk', data={'user_ids': ids, 'action': 'modules_profile', 'value': str(nq)})
    assert response.json() == {'updated': ['ana', 'ben', 'boss'], 'skipped': []}
    assert (profile_of('ana'), profile_of('ben'), profile_of('boss')) == ('Non-Qualified Calls', 'Non-Qualified Calls', 'Non-Qualified Calls')
    response = client.post('/admin/users/bulk', data={'user_ids': ids, 'action': 'add_workspace_group', 'value': str(group)})
    assert response.json() == {'updated': ['ana', 'ben'], 'skipped': ['boss: super-admins open every workspace']}
    assert (groups_of('ana'), groups_of('ben'), groups_of('boss')) == (['UK'], ['UK'], [])
    client.post('/admin/users/bulk', data={'user_ids': ids[:1], 'action': 'remove_workspace_group', 'value': str(group)})
    assert (groups_of('ana'), groups_of('ben')) == ([], ['UK'])
    client.post('/admin/users/bulk', data={'user_ids': ids[:2], 'action': 'role', 'value': 'admin'})
    assert {row['username']: row['role'] for row in core.repository.list_users()}['ben'] == 'admin'
    response = client.post('/admin/users/bulk', data={'user_ids': [user_id('super'), user_id('ben')], 'action': 'deactivate'})
    assert response.json() == {'updated': ['ben'], 'skipped': ['super: you cannot deactivate your own account']}
    assert client.post('/admin/users/bulk', data={'user_ids': ids, 'action': 'modules_profile', 'value': '999'}).status_code == 400
    assert client.post('/admin/users/bulk', data={'action': 'activate'}).status_code == 400
    page = client.get('/admin').text
    assert 'data-users-bulk' in page and 'data-users-filter="profile"' in page and 'id="user-create"' in page


def test_a_super_admin_sees_every_module_until_it_is_given_a_profile(client):
    login(client)
    core.repository.create_user('boss', 'secret123', 'super-admin')
    boss = core.SessionUser(username='boss', role='super-admin')
    assert core.user_has_feature(boss, 'ppt-reporting-old')
    all_modules = next(profile['id'] for profile in core.repository.list_modules_profiles() if profile['name'] == 'All Modules')
    update = {'username': 'boss', 'role': 'super-admin', 'active': '1'}
    response = client.post(f"/admin/users/{user_id('boss')}/update", data={**update, 'modules_profile_id': str(all_modules)},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.json()['user']['modules_profile_id'] == all_modules
    core.invalidate_module_access_cache()
    assert not core.user_has_feature(boss, 'ppt-reporting-old') and core.user_has_feature(boss, 'scoring')
    assert 'value="all" class="user-profile-full-access" >Full Access</option><hr>' in client.get('/admin').text
    # Full Access returns it to every module.
    response = client.post(f"/admin/users/{user_id('boss')}/update", data={**update, 'modules_profile_id': 'all'},
                           headers={'X-Requested-With': 'XMLHttpRequest'})
    assert response.json()['user']['modules_profile_id'] is None
    core.invalidate_module_access_cache()
    assert core.user_has_feature(boss, 'ppt-reporting-old')
    # A user who becomes super-admin sees every module until it is given a profile.
    core.repository.create_user('ana', 'secret123', 'admin')
    client.post(f"/admin/users/{user_id('ana')}/update", data={'username': 'ana', 'role': 'super-admin', 'active': '1',
                                                             'modules_profile_id': str(all_modules)},
                headers={'X-Requested-With': 'XMLHttpRequest'})
    assert profile_of('ana') is None
    # Admins do not change the profile of super-admins, on the cards either.
    core.repository.create_user('plain', 'plain123', 'admin')
    login(client, 'plain', 'plain123')
    response = client.post(f'/admin/modules-profiles/{all_modules}/update', data={
        'name': 'All Modules', 'modules': ['workspace'], 'member_ids': [user_id('boss')], 'initial_member_ids': [],
    })
    assert user_id('boss') not in next(profile for profile in response.json()['profiles'] if profile['id'] == all_modules)['member_ids']


def test_the_create_row_gives_names_profile_and_workspaces(client):
    login(client)
    group = core.repository.save_workspace_group(None, 'UK', '', [core.active_workspace.id])
    nq = next(profile['id'] for profile in core.repository.list_modules_profiles() if profile['name'] == 'Non-Qualified Calls')
    response = client.post('/admin/users', data={
        'username': 'ana', 'password': 'secret123', 'role': 'user-editor', 'first_name': 'Ana', 'last_name': 'García',
        'modules_profile_id': str(nq), 'workspace_group_ids': [group],
    }, follow_redirects=False)
    assert response.status_code == 303
    row = core.repository.get_user_by_id(user_id('ana'))
    assert (row['first_name'], row['last_name'], profile_of('ana'), groups_of('ana')) == ('Ana', 'García', 'Non-Qualified Calls', ['UK'])
    assert core.repository.user_has_workspace_access('ana', core.active_workspace.id)


def users_access_package(client):
    response = client.get('/admin/import-export/export?export_target=users-access')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        payload = json.loads(archive.read('users-access/users-access.json'))
    return response.content, manifest, payload


def repackage(manifest, payload):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('users-access/users-access.json', json.dumps(payload))
    return buffer.getvalue()


def import_package(client, content):
    response = client.post('/admin/import-export/import', data={'confirmed_import': 'true'},
                           files={'package': ('users-access.zip', content, 'application/zip')}, follow_redirects=False)
    assert response.status_code == 303, response.text
    return response


def wait_for_imports():
    import time
    for _attempt in range(200):
        with core.IMPORT_JOBS_LOCK:
            if all(job.get('status') not in {'queued', 'running'} for job in core.IMPORT_JOBS.values()):
                return
        time.sleep(0.05)


def test_users_access_exports_and_imports_users_profiles_and_groups(client):
    login(client)
    core.repository.create_user('ana', 'secret123', 'user-editor', first_name='Ana', last_name='García')
    nq = next(profile['id'] for profile in core.repository.list_modules_profiles() if profile['name'] == 'Non-Qualified Calls')
    core.repository.set_users_modules_profile([user_id('ana')], nq)
    group = core.repository.save_workspace_group(None, 'UK', 'Users of UK', [core.active_workspace.id])
    core.repository.set_user_workspace_groups(user_id('ana'), [group])
    content, manifest, payload = users_access_package(client)
    assert manifest['kind'] == 'users-access' and manifest['components'] == ['users_access']
    assert {'id': core.active_workspace.id, 'name': core.active_workspace.name} in manifest['source_workspaces']
    ana = next(item for item in payload['users'] if item['username'] == 'ana')
    assert (ana['first_name'], ana['modules_profile'], ana['workspace_groups']) == ('Ana', 'Non-Qualified Calls', ['UK'])
    assert next(item for item in payload['workspace_groups'] if item['name'] == 'UK')['workspaces'] == [core.active_workspace.name]
    assert 'Users & Access' in client.get('/admin').text

    # Here the user and its profile change, a workspace only this server has joins the group, and a user only this
    # server has exists.
    local_only = core.workspace_registry.create('Local only')
    core.repository.delete_user(user_id('ana'))
    core.repository.save_modules_profile(nq, 'Non-Qualified Calls', '', ['workspace'])
    core.repository.save_workspace_group(group, 'UK', 'Users of UK', [core.active_workspace.id, local_only.id])
    core.repository.create_user('local', 'secret123', 'user-viewer')
    # The package also demotes the importing super-admin and names a workspace this server does not have.
    super_entry = next(item for item in payload['users'] if item['username'] == 'super')
    super_entry.update({'role': 'user-viewer', 'active': False})
    payload['workspace_groups'].append({'name': 'DE', 'description': '', 'workspaces': ['Only there']})
    import_package(client, repackage(manifest, payload))
    wait_for_imports()

    assert profile_of('ana') == 'Non-Qualified Calls' and groups_of('ana') == ['UK']
    assert core.repository.get_user_by_id(user_id('ana'))['last_name'] == 'García'
    assert core.verify_password('secret123', core.repository.get_user('ana').password_hash)
    assert next(profile for profile in core.repository.list_modules_profiles() if profile['id'] == nq)['modules'] == \
        ['workspace', 'non-qualified-calls', 'reporting', 'builders', 'bugs-report']
    groups = {item['name']: item['workspace_ids'] for item in core.repository.list_workspace_groups()}
    assert groups == {'UK': sorted([core.active_workspace.id, local_only.id]), 'DE': []}
    assert core.repository.get_user('local') is not None
    record = core.repository.get_user('super')
    assert (record.role, record.active) == ('super-admin', True)


def test_users_access_never_leaves_no_active_super_admin():
    payload = {'modules_profiles': [], 'workspace_groups': [],
               'users': [{'username': 'super', 'password_hash': 'x', 'role': 'user-viewer', 'active': False}]}
    try:
        core.repository.merge_users_access(payload, {}, protected_username='import')
        raise AssertionError('The import should have been refused.')
    except ValueError as exc:
        assert 'no active super-admin' in str(exc)
    assert core.repository.get_user('super').role == 'super-admin'


def test_users_access_backs_up_and_restores_on_its_own(client, tmp_path: Path):
    core.repository.create_user('ana', 'secret123', 'user-editor', first_name='Ana', last_name='García')
    archive_path = core.create_recurring_database_backup({
        'components': ['users_access'], 'backup_path': str(tmp_path / 'backups'), 'max_backups': 30, 'workspace_ids': [],
    })
    with zipfile.ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        assert 'users-access/users-access.json' in archive.namelist() and 'application/application.db' not in archive.namelist()
    assert manifest['components'] == ['users_access']
    assert core._backup_archive_components(archive_path) == ['users_access']
    core.repository.delete_user(user_id('ana'))
    core.repository.create_user('later', 'secret123', 'user-viewer')
    core.restore_database_backup(archive_path, ['users_access'], importing_user='super')
    assert core.repository.get_user_by_id(user_id('ana'))['first_name'] == 'Ana'
    assert core.repository.get_user('later') is not None


def test_lists_of_users_show_names_with_the_default_users_first(client):
    login(client)
    core.repository.create_user('EZZZZZZ', 'secret123', 'user-editor', first_name='Ana', last_name='García')
    core.repository.create_user('EAAAAAA', 'secret123', 'user-editor', first_name='Zoe', last_name='Alba')
    entries = core.user_choices(['EAAAAAA', 'admin', 'system', 'EZZZZZZ', 'super'])
    # System (the application's user) first, then the default users and the others, with a line between the groups.
    assert [(entry['username'], entry['label'], entry['divider']) for entry in entries] == [
        ('system', 'System · application', False), ('super', 'super · default user', True), ('admin', 'admin · default user', False),
        ('EZZZZZZ', 'Ana García', True), ('EAAAAAA', 'Zoe Alba', False)]

    core.repository.add_log('EZZZZZZ', 'change_password', 'Password changed from the account badge.')
    events = client.get('/app-logs').text
    user_filter = events.split('data-app-log-user-filter multiple', 1)[1].split('</select>', 1)[0]
    assert '<option value="ezzzzzz" data-name="Ana García" data-divider-before="true">Ana García</option>' in user_filter
    assert 'data-default-user="true" data-tag="default user">super · default user</option>' in user_filter
    assert user_filter.index('super · default user') < user_filter.index('Ana García')
    # The table shows each person by name, with the username as a badge below (the names looked up once per page).
    assert ('<td><span class="app-log-person">Ana García <span class="user-choice-tag app-log-badge user-choice-tag-username">ezzzzzz</span>'
            '</span></td>') in events
    logs = client.get('/api/app-logs').json()['logs']
    assert next(log for log in logs if log['action'] == 'change_password')['user_name'] == 'Ana García'
    # The pickers of Admin and Workspace: names, the default users tagged, a line before the others, the username searchable.
    admin = client.get('/admin').text
    assert '<label class="user-choice-divider">' in admin
    assert '<span>Ana García</span><span class="sr-only">EZZZZZZ</span>' in admin and '<span class="user-choice-tag">default user</span>' in admin
    workspace = client.get('/workspace').text
    assert '<span>Ana García</span><span class="sr-only">EZZZZZZ</span>' in workspace
