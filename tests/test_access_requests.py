"""Access requests from the login page: an inactive editor in the user groups of the chosen workspace and modules."""
import src.DriveTestAnalyzer as core


def workspace_group(name):
    """A user group that opens the active workspace, as DE or UK do in a deployment."""
    group_id = core.repository.save_user_group(None, name, '', [])
    rule = core.repository.workspace_access_rules().get(core.active_workspace.id, {'roles': [], 'groups': []})
    core.repository.set_workspace_access_rule(core.active_workspace.id, rule['roles'], [*rule['groups'], group_id])
    return group_id


def test_module_access_groups_give_their_modules(client):
    groups = {group['name']: group['id'] for group in core.repository.list_user_groups()}
    assert {'NQ Calls', 'Benchmarking', 'All Modules'} <= set(groups)
    rules = core.feature_activation_settings()

    def allowed(name):
        return {key for key in core.FEATURE_KEYS if core.feature_rule_allows(rules[key], 'user-editor', None, {groups[name]}, '')}

    assert allowed('NQ Calls') == {'workspace', 'non-qualified-calls'}
    assert allowed('Benchmarking') == set(core.FEATURE_KEYS) - {'non-qualified-calls', 'ppt-reporting-old'}
    assert allowed('All Modules') == set(core.FEATURE_KEYS) - {'ppt-reporting-old'}
    # Created once per deployment: the later changes of an administrator are kept.
    core.repository.delete_user_group(groups['Benchmarking'])
    core.ensure_module_access_groups()
    assert 'Benchmarking' not in {group['name'] for group in core.repository.list_user_groups()}


def test_access_request_creates_an_inactive_editor_in_the_chosen_groups(client):
    uk = workspace_group('UK')
    page = client.get('/login').text
    assert 'data-access-request-open' in page and '>Request Access</button>' in page
    options = client.get('/api/access-requests/options').json()
    assert [group['name'] for group in options['workspace_groups']] == ['UK']
    assert options['workspace_groups'][0]['workspaces'] == [core.active_workspace.name]
    assert [group['name'] for group in options['module_groups']] == ['NQ Calls', 'Benchmarking', 'All Modules']
    nq_calls = options['module_groups'][0]
    assert nq_calls['modules'] == ['Workspace', 'Non-Qualified Calls']
    request = {'username': 'eabcdef', 'password': 'secret1', 'password_confirmation': 'secret1',
               'workspace_group_ids': [uk], 'module_group_id': nq_calls['id']}
    # Only an Ericsson signum, matching passwords, and workspaces and modules of the lists.
    for change, message in (({'username': 'xabcdef'}, 'signum'), ({'username': 'eabc12f'}, 'signum'),
                            ({'username': 'eabcdefg'}, 'signum'), ({'password_confirmation': 'other'}, 'do not match'),
                            ({'workspace_group_ids': []}, 'workspace'), ({'workspace_group_ids': [nq_calls['id']]}, 'workspace'),
                            ({'module_group_id': uk}, 'modules')):
        response = client.post('/api/access-requests', json={**request, **change})
        assert response.status_code == 400 and message in response.json()['detail']
    response = client.post('/api/access-requests', json=request)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['username'] == 'EABCDEF' and result['modules'] == 'NQ Calls (Workspace, Non-Qualified Calls)'
    assert result['email']['to'] == 'jaime.tur@ericsson.com' and result['email']['subject'].endswith('access request: EABCDEF')
    assert 'User: EABCDEF' in result['email']['body'] and f'Workspaces: UK ({core.active_workspace.name})' in result['email']['body']
    record = core.repository.get_user('eabcdef')
    assert (record.username, record.role, record.active) == ('EABCDEF', 'user-editor', False)
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'EABCDEF')
    assert {group['name'] for group in core.repository.list_user_groups() if user_id in group['member_ids']} == {'UK', 'NQ Calls'}
    # The user signs in only once an administrator activates it.
    sign_in = {'password': 'secret1', 'workspace_id': core.active_workspace.id}
    assert client.post('/login', data={**sign_in, 'username': 'eabcdef'}, follow_redirects=False).status_code == 401
    core.repository.update_user(user_id, 'EABCDEF', 'user-editor', True)
    core.invalidate_feature_activation_cache()
    assert client.post('/login', data={**sign_in, 'username': 'eAbCdEf'}, follow_redirects=False).status_code == 303
    user = core.SessionUser(username='EABCDEF', role='user-editor')
    assert core.user_has_feature(user, 'workspace') and core.user_has_feature(user, 'non-qualified-calls')
    assert not core.user_has_feature(user, 'scoring') and not core.user_has_feature(user, 'reporting')


def test_access_request_of_an_existing_user_changes_its_access_until_it_is_activated_again(client):
    uk = workspace_group('UK')
    de = workspace_group('DE')
    other = core.repository.save_user_group(None, 'Analysts', '', [])
    groups = {group['name']: group['id'] for group in core.repository.list_user_groups()}
    user_id = core.repository.create_user('EFGHIJK', 'secret1', 'user-viewer')
    core.repository.set_user_groups(user_id, [uk, groups['NQ Calls'], other])
    core.repository.create_user('EADMINS', 'secret1', 'admin')
    # The dialog warns when the signum already has a user.
    assert client.get('/api/access-requests/users/efghijk').json() == {'exists': True, 'username': 'EFGHIJK', 'administrator': False}
    assert client.get('/api/access-requests/users/eadmins').json()['administrator']
    assert client.get('/api/access-requests/users/enobody').json()['exists'] is False
    token = 'existing-user-session'
    core.SESSIONS[token] = core.SessionUser(username='EFGHIJK', role='user-viewer')
    request = {'username': 'efghijk', 'password': 'wrong', 'workspace_group_ids': [de], 'module_group_id': groups['All Modules']}
    # Only with its current password, and never for an administrator.
    response = client.post('/api/access-requests', json=request)
    assert response.status_code == 403 and 'current password' in response.json()['detail']
    assert client.post('/api/access-requests', json={**request, 'username': 'eadmins', 'password': 'secret1'}).status_code == 403
    response = client.post('/api/access-requests', json={**request, 'password': 'secret1'})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['existing'] and (result['username'], result['role']) == ('EFGHIJK', 'user-viewer')
    assert result['email']['subject'].endswith('access change request: EFGHIJK')
    assert 'Previous workspaces: UK' in result['email']['body'] and 'Previous modules: NQ Calls' in result['email']['body']
    # Its workspace and module groups are replaced, its other groups kept, and it waits for the administrator.
    members = {group['name'] for group in core.repository.list_user_groups() if user_id in group['member_ids']}
    assert members == {'DE', 'All Modules', 'Analysts'}
    record = core.repository.get_user('EFGHIJK')
    assert (record.role, record.active) == ('user-viewer', False) and token not in core.SESSIONS
