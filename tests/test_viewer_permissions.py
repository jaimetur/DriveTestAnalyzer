import io

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core


def _viewer(client, username='viewer', role='user-viewer'):
    core.repository.create_user(username, f'{username}123', role)
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == username)
    core.repository.set_user_workspace_access(user_id, [core.active_workspace.id])
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': f'{username}123'}, follow_redirects=False)
    assert response.status_code == 303


def _ready_cdr(tmp_path):
    source = tmp_path / 'cdr.csv'
    source.write_text('Operator\nEE\n', encoding='utf-8')
    dataset_id, _ = core.repository.add_dataset('cdr.csv', str(source), 'admin')
    core.repository.replace_dataset_rows(dataset_id, pd.DataFrame({'Operator': ['EE']}))
    core.repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind='data', nr_mode='NSA')
    return dataset_id


@pytest.mark.parametrize('method, path, kwargs', [
    ('post', '/datasets-analysis/upload', {'files': {'dataset_files': ('x.csv', io.BytesIO(b'a\n1\n'), 'text/csv')}}),
    ('post', '/datasets-analysis/delete/{id}', {}),
    ('post', '/datasets-analysis/retry/{id}', {}),
    ('post', '/dashboard/retry/{id}', {}),
    ('post', '/datasets-analysis/stop/{id}', {}),
    ('post', '/workspace/delete-datasets', {}),
    ('post', '/workspace/reprocess-datasets', {'data': {'dataset_ids': '{id}'}}),
    ('post', '/workspace/stop-datasets', {}),
    ('post', '/workspace/map-mappings', {'data': {'cdr_dataset_ids': '{id}', 'region_mapping_dataset_id': '1'}}),
    ('post', '/workspace/map-vendors', {'data': {'cdr_dataset_id': '{id}', 'three_mapping_dataset_id': '1'}}),
    ('post', '/workspace/map-regions', {'data': {'cdr_dataset_ids': '{id}', 'region_mapping_dataset_id': '1'}}),
    ('post', '/workspace/clear-mappings', {'data': {'cdr_dataset_ids': '{id}'}}),
    ('post', '/workspace/clear-regions', {'data': {'cdr_dataset_ids': '{id}'}}),
    ('post', '/workspace/clear-vendors', {'data': {'cdr_dataset_ids': '{id}'}}),
    ('post', '/workspace/datasets/{id}/nr-mode', {'json': {'nr_mode': 'SA'}}),
    ('post', '/workspace/combined/data/recreate', {}),
    ('post', '/api/workspace/auto-calculated-fields/rematerialize', {}),
    ('put', '/api/workspace/calculated-dimensions', {'json': {'dimensions': []}}),
    ('post', '/api/query-builder/save', {'json': {'name': 'q', 'query': 'SELECT 1'}}),
    ('delete', '/api/query-builder/saved/1', {}),
    ('delete', '/api/scoring/saved-filters/1', {}),
    ('post', '/api/scoring/saved-filters/1/duplicate', {'json': {'dataset_ids': [1]}}),
    ('put', '/api/ppt-dashboards/d1', {'json': {'name': 'D'}}),
    ('delete', '/api/ppt-dashboards/d1', {}),
    ('patch', '/api/ppt-dashboards/d1/name', {'json': {'name': 'D'}}),
    ('patch', '/api/ppt-dashboards/d1/comments', {'json': {'slide_comments': {}}}),
])
def test_user_viewer_cannot_change_the_workspace(client, tmp_path, method, path, kwargs):
    dataset_id = _ready_cdr(tmp_path)
    _viewer(client)
    path = path.replace('{id}', str(dataset_id))
    kwargs = {key: ({name: str(value).replace('{id}', str(dataset_id)) for name, value in item.items()} if key == 'data' else item)
              for key, item in kwargs.items()}
    response = getattr(client, method)(path, follow_redirects=False, **kwargs)
    assert response.status_code == 403, (path, response.status_code, response.text[:200])
    assert core.repository.get_dataset(dataset_id) is not None


def test_user_viewer_still_explores_and_generates_jobs(client, tmp_path):
    _ready_cdr(tmp_path)
    _viewer(client)
    assert client.get('/workspace').status_code == 200
    page = client.get('/ppt-dashboards')
    assert page.status_code == 200 and 'data-ds-manage-only' in page.text
    assert 'data-authenticated-role="user-viewer"' in page.text
    assert client.post('/api/scoring/saved-filters/match', json={}).status_code != 403
    # Editors keep changing the workspace.
    _viewer(client, 'editor', 'user-editor')
    assert client.post('/workspace/stop-datasets', follow_redirects=False).status_code != 403


def test_super_admins_see_every_module_and_admins_do_not_change_them(client):
    _viewer(client, 'boss', 'super-admin')
    boss_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'boss')
    _viewer(client, 'plainadmin', 'admin')
    admin_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'plainadmin')
    # Admins keep Admin; users, Modules Profiles and Workspace Groups are in Super Admin, for super-admins only.
    assert client.get('/admin').status_code == 200 and client.get('/super-admin').status_code == 403
    assert client.post('/admin/users/bulk', data={'user_ids': [boss_id], 'action': 'deactivate'}).status_code == 403
    client.cookies.clear()
    assert client.post('/login', data={'username': 'boss', 'password': 'boss123'}, follow_redirects=False).status_code == 303
    assert 'id="modules-profiles"' in client.get('/super-admin').text
    # A profile without Reporting removes it from its users, admins included, but never from super-admins.
    profile_id = core.repository.save_modules_profile(None, 'Workspace only', '', ['workspace'])
    response = client.post(f'/admin/modules-profiles/{profile_id}/update', data={
        'name': 'Workspace only', 'modules': ['workspace'], 'member_ids': [admin_id], 'initial_member_ids': [],
    })
    assert response.status_code == 200
    profiles = response.json()['profiles']
    assert next(profile for profile in profiles if profile['id'] == profile_id)['member_ids'] == [admin_id]
    assert all(boss_id not in profile['member_ids'] for profile in profiles)
    assert not core.user_has_feature(core.SessionUser(username='plainadmin', role='admin'), 'reporting')
    assert core.user_has_feature(core.SessionUser(username='boss', role='super-admin'), 'reporting')


def test_only_admins_upload_datasets_and_the_other_roles_see_why(client):
    _viewer(client, 'editor', 'user-editor')
    page = client.get('/workspace').text
    assert 'Only admins and super-admins can upload datasets to the workspace.' in page and '<form class="upload-dropzone"' not in page
    upload = client.post('/datasets-analysis/upload', files={'dataset_files': ('x.csv', io.BytesIO(b'a\n1\n'), 'text/csv')},
                         follow_redirects=False)
    assert upload.status_code == 403 and 'Only admins and super-admins can upload datasets' in upload.text
    started = client.post('/api/uploads', json={'workspace_id': core.active_workspace.id, 'files': [{'name': 'x.csv', 'size': 4}], 'form': {}})
    assert started.status_code == 403
    _viewer(client, 'manager', 'admin')
    page = client.get('/workspace').text
    assert '<form class="upload-dropzone"' in page and 'Only admins and super-admins can upload datasets' not in page


def test_only_admins_change_in_combined(client, tmp_path):
    dataset_id = _ready_cdr(tmp_path)
    _viewer(client, 'editor', 'user-editor')
    changed = client.post(f'/workspace/datasets/{dataset_id}/in-combined', json={'in_combined': 'no'})
    assert changed.status_code == 403 and 'Only admins and super-admins can change In Combined' in changed.text
    _viewer(client, 'manager', 'admin')
    assert client.post(f'/workspace/datasets/{dataset_id}/in-combined', json={'in_combined': 'no'}).status_code == 200
