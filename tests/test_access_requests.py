"""Access requests from the login page: an inactive editor in the chosen Workspace Groups with the chosen Modules Profile."""
import src.DriveTestAnalyzer as core


def workspace_group(name):
    """A Workspace Group that opens the active workspace, as DE or UK do in a deployment."""
    return core.repository.save_workspace_group(None, name, '', [core.active_workspace.id])


def profiles():
    return {profile['name']: profile for profile in core.repository.list_modules_profiles()}


def test_a_new_deployment_has_the_modules_profiles_of_each_team(client):
    available = profiles()
    assert set(available) == {'Non-Qualified Calls', 'Benchmarking', 'All Modules'}
    assert available['Non-Qualified Calls']['modules'] == ['workspace', 'non-qualified-calls', 'reporting', 'builders', 'ticket-center']
    assert set(available['Benchmarking']['modules']) == set(core.FEATURE_KEYS) - {'non-qualified-calls', 'ppt-reporting-old'}
    assert set(available['All Modules']['modules']) == set(core.FEATURE_KEYS) - {'ppt-reporting-old'}
    assert [name for name, profile in available.items() if profile['is_default']] == ['All Modules']
    assert {name: profile['color'] for name, profile in available.items()} == {'Non-Qualified Calls': '#D74B75', 'Benchmarking': '#1E61A3', 'All Modules': '#096767'}
    # Created once per deployment: the later changes of an administrator are kept.
    core.repository.delete_modules_profile(available['Benchmarking']['id'])
    core.repository.initialize()
    assert 'Benchmarking' not in profiles()


def test_access_request_creates_an_inactive_editor_with_the_chosen_access(client):
    uk = workspace_group('UK')
    core.repository.save_workspace_group(None, 'Empty', '', [])
    page = client.get('/login').text
    assert 'data-access-request-open' in page and '>Request Access</button>' in page
    assert 'name="first_name"' in page and 'name="last_name"' in page
    options = client.get('/api/access-requests/options').json()
    # Only the groups that open a workspace are offered.
    assert [group['name'] for group in options['workspace_groups']] == ['UK']
    assert options['workspace_groups'][0]['workspaces'] == [core.active_workspace.name]
    assert options['workspace_groups'][0]['description'] == ''
    assert [profile['name'] for profile in options['modules_profiles']] == ['All Modules', 'Benchmarking', 'Non-Qualified Calls']
    nq_calls = options['modules_profiles'][2]
    assert nq_calls['modules'] == ['Workspace', 'Non-Qualified Calls', 'Reporting', 'Builders', 'Ticket Center']
    assert nq_calls['module_tabs'][0]['title'] == 'Workspace' and nq_calls['module_tabs'][0]['color'] and nq_calls['module_tabs'][0]['icon']
    request = {'username': 'eabcdef', 'first_name': ' Ana ', 'last_name': 'García', 'password': 'secret1', 'password_confirmation': 'secret1',
               'workspace_group_ids': [uk], 'modules_profile_id': nq_calls['id']}
    # Only with the names, an Ericsson signum, matching passwords, and workspaces and modules of the lists.
    for change, message in (({'first_name': ''}, 'first name'), ({'last_name': ' '}, 'last name'),
                            ({'username': 'xabcdef'}, 'signum'), ({'username': 'eabc12f'}, 'signum'),
                            ({'username': 'eabcdefg'}, 'signum'), ({'password_confirmation': 'other'}, 'do not match'),
                            ({'workspace_group_ids': []}, 'workspace'), ({'workspace_group_ids': [uk + 99]}, 'workspace'),
                            ({'modules_profile_id': 999}, 'modules profile')):
        response = client.post('/api/access-requests', json={**request, **change})
        assert response.status_code == 400 and message in response.json()['detail']
    response = client.post('/api/access-requests', json=request)
    assert response.status_code == 201, response.text
    result = response.json()
    assert (result['username'], result['name']) == ('EABCDEF', 'Ana García')
    assert result['modules_profile'] == 'Non-Qualified Calls (Workspace, Non-Qualified Calls, Reporting, Builders, Ticket Center)'
    assert result['email']['to'] == 'jaime.tur@ericsson.com' and result['email']['subject'].endswith('access request: EABCDEF')
    # Copied to the approvers: any of them approves the request before the administrator activates the user.
    assert result['email']['cc'] == ['kleber.gomes@ericsson.com', 'angelo.reis@ericsson.com', 'mohammadreza.rajabi@ericsson.com',
                                     'alfonso.j.alvarez@ericsson.com']
    body = result['email']['body']
    assert body.startswith('Hello Jaime, Kleber, Angelo, Mohammadreza and Alfonso,')
    # The approvers' part is framed in capitals, and the administrator's line comes apart below it.
    assert ('APPROVAL NEEDED\nKleber, Angelo, Mohammadreza or Alfonso: please review the request and approve it by replying to all.\n'
            '========================================\n\nJaime: once one of them has approved it, please activate my user in Super Admin › Users.') in body
    assert 'User: EABCDEF' in body and 'Name: Ana García' in body and f'Workspaces: UK ({core.active_workspace.name})' in body
    record = core.repository.get_user('eabcdef')
    assert (record.username, record.role, record.active) == ('EABCDEF', 'user-editor', False)
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'EABCDEF')
    assert (core.repository.get_user_by_id(user_id)['first_name'], core.repository.get_user_by_id(user_id)['last_name']) == ('Ana', 'García')
    assert [group['name'] for group in core.repository.list_workspace_groups() if user_id in group['member_ids']] == ['UK']
    assert user_id in profiles()['Non-Qualified Calls']['member_ids']
    # The user signs in only once an administrator activates it.
    sign_in = {'password': 'secret1', 'workspace_id': core.active_workspace.id}
    assert client.post('/login', data={**sign_in, 'username': 'eabcdef'}, follow_redirects=False).status_code == 401
    core.repository.update_user(user_id, 'EABCDEF', 'user-editor', True)
    assert client.post('/login', data={**sign_in, 'username': 'eAbCdEf'}, follow_redirects=False).status_code == 303
    user = core.SessionUser(username='EABCDEF', role='user-editor')
    core.invalidate_module_access_cache()
    assert core.user_has_feature(user, 'workspace') and core.user_has_feature(user, 'non-qualified-calls')
    assert core.user_has_feature(user, 'reporting') and not core.user_has_feature(user, 'scoring')


def test_access_request_of_an_existing_user_changes_its_access_until_it_is_activated_again(client):
    uk = workspace_group('UK')
    de = workspace_group('DE')
    other = core.repository.save_workspace_group(None, 'Analysts', '', [])
    user_id = core.repository.create_user('EFGHIJK', 'secret1', 'user-viewer', first_name='Old', last_name='Name')
    core.repository.set_user_workspace_groups(user_id, [uk, other])
    core.repository.set_users_modules_profile([user_id], profiles()['Non-Qualified Calls']['id'])
    core.repository.create_user('EADMINS', 'secret1', 'admin')
    # The dialog warns when the signum already has a user.
    assert client.get('/api/access-requests/users/efghijk').json() == {'exists': True, 'username': 'EFGHIJK', 'administrator': False}
    assert client.get('/api/access-requests/users/eadmins').json()['administrator']
    assert client.get('/api/access-requests/users/enobody').json()['exists'] is False
    token = 'existing-user-session'
    core.SESSIONS[token] = core.SessionUser(username='EFGHIJK', role='user-viewer')
    request = {'username': 'efghijk', 'first_name': 'Eva', 'last_name': 'Fernández', 'password': 'wrong',
               'workspace_group_ids': [de], 'modules_profile_id': profiles()['All Modules']['id']}
    # Only with its current password, and never for an administrator.
    response = client.post('/api/access-requests', json=request)
    assert response.status_code == 403 and 'current password' in response.json()['detail']
    assert client.post('/api/access-requests', json={**request, 'username': 'eadmins', 'password': 'secret1'}).status_code == 403
    response = client.post('/api/access-requests', json={**request, 'password': 'secret1'})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['existing'] and (result['username'], result['role']) == ('EFGHIJK', 'user-viewer')
    assert result['email']['subject'].endswith('access change request: EFGHIJK') and len(result['email']['cc']) == 4
    assert 'please activate my user again in Super Admin › Users.' in result['email']['body']
    assert 'Previous workspaces: UK' in result['email']['body'] and 'Previous modules profile: Non-Qualified Calls' in result['email']['body']
    # Its Workspace Groups and profile are replaced, its group without workspaces kept, its name updated,
    # and it waits for the administrator.
    assert {group['name'] for group in core.repository.list_workspace_groups() if user_id in group['member_ids']} == {'DE', 'Analysts'}
    assert user_id in profiles()['All Modules']['member_ids']
    assert core.repository.get_user_by_id(user_id)['first_name'] == 'Eva'
    record = core.repository.get_user('EFGHIJK')
    assert (record.role, record.active) == ('user-viewer', False) and token not in core.SESSIONS
