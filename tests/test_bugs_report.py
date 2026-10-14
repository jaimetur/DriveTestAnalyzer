"""Bugs Report: tickets with screenshots, the reporter's edits, the super-admins' attention, access and portability."""
import io
import json
import zipfile

import pytest

import src.DriveTestAnalyzer as core
from src.version import __version__

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def add_user(username, role='user-editor', profile='All Modules'):
    user_id = core.repository.create_user(username, 'secret123', role)
    profile_id = next(item['id'] for item in core.repository.list_modules_profiles() if item['name'] == profile)
    core.repository.set_users_modules_profile([user_id], profile_id)
    core.invalidate_module_access_cache()
    return user_id


def open_bug(client, title='Export fails', priority='P2', screenshots=(('screen.png', PNG),)):
    response = client.post('/api/bugs-report', data={'title': title, 'description': 'It fails.', 'module': 'scoring', 'priority': priority},
                           files=[('screenshots', (name, content, 'image/png')) for name, content in screenshots])
    assert response.status_code == 200, response.text
    return response.json()['id']


def logged(action):
    return [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == action]


def test_bugs_report_is_in_every_profile_once_and_opens_without_a_workspace(client):
    assert all('bugs-report' in profile['modules'] for profile in core.repository.list_modules_profiles())
    # A deployment from before the module gets it in every profile once; a profile it is taken out of keeps without it.
    nq = next(profile for profile in core.repository.list_modules_profiles() if profile['name'] == 'Non-Qualified Calls')
    with core.repository.global_connection() as conn:
        conn.execute("DELETE FROM application_state WHERE key = 'modules_profiles_added_modules'")
        conn.execute('UPDATE modules_profiles SET modules_json = ? WHERE id = ?', (json.dumps(['workspace', 'non-qualified-calls']), nq['id']))
    core.repository.initialize()
    modules = {profile['name']: profile['modules'] for profile in core.repository.list_modules_profiles()}
    assert modules['Non-Qualified Calls'] == ['workspace', 'non-qualified-calls', 'bugs-report']
    core.repository.save_modules_profile(nq['id'], nq['name'], nq['description'], ['workspace', 'non-qualified-calls'])
    core.repository.initialize()
    assert 'bugs-report' not in next(item for item in core.repository.list_modules_profiles() if item['id'] == nq['id'])['modules']

    login(client)
    core.close_active_workspace()
    page = client.get('/bugs-report')
    assert page.status_code == 200
    assert 'id="section-new-bug-report"' in page.text and 'id="section-bug-reports"' in page.text
    # Each count of the header lists its bug reports, and the list filters them by reporter too.
    assert 'data-bugs-filter="reporter"' in page.text
    assert all(f'data-bugs-stat="{key}"' in page.text for key in ('new', 'in_progress', 'waiting_info', 'resolved', 'mine'))
    assert f'Version {__version__}' in page.text
    # Its tab is a link even without a workspace, unlike the modules that use one.
    assert 'module-tab module-tab-bugs-report' in page.text and 'href="/bugs-report" title="Open Bugs Report"' in page.text
    assert 'title="Open a workspace to use Scoring &amp; GAP Analysis"' in page.text


def test_a_user_reports_a_bug_with_screenshots_and_its_version(client):
    add_user('ana', 'user-viewer')
    login(client, 'ana', 'secret123')
    bug_id = open_bug(client)
    from src.modules.bugs_report import get_bug
    bug = get_bug(core.repository, bug_id)
    assert (bug['title'], bug['priority'], bug['status'], bug['module'], bug['created_by']) == ('Export fails', 'P2', 'new', 'scoring', 'ana')
    assert bug['app_version'] == __version__ and bug['created_at'][:4].isdigit()
    assert [item['file_name'] for item in bug['attachments']] == ['screen.png']
    image = client.get(f"/bugs-report/attachments/{bug['attachments'][0]['id']}")
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png' and image.content == PNG
    assert logged('bug_report_created')[0]['screenshots'] == ['screen.png']
    page = client.get(f'/bugs-report/{bug_id}')
    assert page.status_code == 200 and 'Export fails' in page.text and f'v{__version__}' in page.text
    # Only images are attached, and a bug needs a title.
    refused = client.post('/api/bugs-report', data={'title': 'Text'}, files=[('screenshots', ('notes.txt', b'hello', 'text/plain'))])
    assert refused.status_code == 400 and 'not a PNG, JPEG, GIF or WebP image' in refused.json()['detail']
    assert client.post('/api/bugs-report', data={'title': '  '}).status_code == 400


def test_the_reporter_edits_and_only_super_admins_attend(client):
    add_user('ana')
    add_user('bob')
    login(client, 'ana', 'secret123')
    bug_id = open_bug(client)
    listing = client.get('/bugs-report').text
    assert '<option value="ana">ana</option>' in listing and 'data-reporter="ana"' in listing
    assert client.post(f'/api/bugs-report/{bug_id}/update', data={'priority': 'P1', 'title': 'Export always fails'}).json()['changes'] == {
        'priority': ['P2', 'P1'], 'title': ['Export fails', 'Export always fails']}
    assert client.post(f'/api/bugs-report/{bug_id}/manage', data={'status': 'resolved'}).status_code == 403
    login(client, 'bob', 'secret123')
    assert client.post(f'/api/bugs-report/{bug_id}/update', data={'priority': 'P5'}).status_code == 403
    comment = client.post(f'/api/bugs-report/{bug_id}/comments', data={'body': 'Me too'}).json()['id']
    assert client.post(f'/api/bugs-report/comments/{comment}/update', data={'body': 'Me too, in DE'}).status_code == 200

    login(client)
    assert client.post(f'/api/bugs-report/comments/{comment}/update', data={'body': 'No'}).status_code == 403
    attended = client.post(f'/api/bugs-report/{bug_id}/manage', data={'status': 'in_progress'}).json()['changes']
    assert attended == {'status': ['new', 'in_progress'], 'assigned_to': ['', 'super']}
    assert client.post(f'/api/bugs-report/{bug_id}/manage', data={'assigned_to': 'ana'}).status_code == 400
    resolved = client.post(f'/api/bugs-report/{bug_id}/manage', data={'status': 'resolved'}).json()['changes']
    assert resolved == {'status': ['in_progress', 'resolved'], 'fixed_version': ['', __version__]}
    from src.modules.bugs_report import get_bug
    bug = get_bug(core.repository, bug_id)
    assert bug['resolved_at'] and [entry['kind'] for entry in bug['comments']] == ['change', 'comment', 'change', 'change']
    page = client.get(f'/bugs-report/{bug_id}').text
    assert 'changed Status from <em>In Progress</em> to <em>Resolved</em>' in page and 'Me too, in DE' in page
    # Reopened, the date it was resolved is cleared.
    client.post(f'/api/bugs-report/{bug_id}/manage', data={'status': 'waiting_info'})
    assert get_bug(core.repository, bug_id)['resolved_at'] == ''
    assert client.post(f'/api/bugs-report/comments/{comment}/delete').status_code == 200
    assert client.post(f'/api/bugs-report/{bug_id}/delete').json()['deleted']
    assert client.get(f'/bugs-report/{bug_id}').status_code == 404
    assert [entry['bug_id'] for entry in logged('bug_report_deleted')] == [bug_id]
    assert logged('bug_report_managed') and logged('bug_report_updated') and logged('bug_report_commented')


def test_accounts_without_the_module_cannot_open_it(client):
    profile_id = core.repository.save_modules_profile(None, 'Only Workspace', '', ['workspace'])
    user_id = core.repository.create_user('carl', 'secret123', 'user-editor')
    core.repository.set_users_modules_profile([user_id], profile_id)
    core.invalidate_module_access_cache()
    login(client, 'carl', 'secret123')
    assert client.get('/bugs-report').status_code == 403
    assert client.post('/api/bugs-report', data={'title': 'x'}).status_code == 403


def test_bugs_report_exports_imports_and_backs_up_on_its_own(client):
    login(client)
    bug_id = open_bug(client)
    client.post(f'/api/bugs-report/{bug_id}/comments', data={'body': 'See this'}, files=[('screenshots', ('detail.png', PNG, 'image/png'))])
    package, filename = core.build_export_archive('bugs-report')
    assert filename.startswith('drivetest-analyzer-bugs-report_')
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read('manifest.json'))
    assert manifest['kind'] == 'bugs-report' and manifest['components'] == ['bugs_report']
    assert 'bugs-report/bugs-report.json' in names and len([name for name in names if name.startswith('bugs-report/attachments/')]) == 2

    from src.modules.bugs_report import delete_bug, list_bugs
    delete_bug(core.repository, bug_id)
    inspected = client.post('/admin/import-export/inspect/upload', content=package, headers={'X-Import-File-Name': 'bugs.zip'})
    assert inspected.status_code == 200 and inspected.json()['kind'] == 'bugs-report'
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        notice = core.import_bugs_report(archive)
        assert notice.startswith('Bugs Report imported: 1 new and 0 updated bug reports, 1 comments and 2 screenshots')
        # Imported again, nothing is duplicated.
        assert core.import_bugs_report(archive).startswith('Bugs Report imported: 0 new and 0 updated bug reports, 0 comments and 0 screenshots')
    bugs = list_bugs(core.repository)
    assert [(bug['title'], bug['comment_count'], bug['attachment_count']) for bug in bugs] == [('Export fails', 1, 2)]

    archive_path = core.create_recurring_database_backup({
        'components': ['bugs_report'], 'backup_path': str(core.application_data_dir / 'scheduled-backups'), 'max_backups': 30, 'workspace_ids': [],
    })
    assert core._backup_archive_components(archive_path) == ['bugs_report']
    delete_bug(core.repository, int(bugs[0]['id']))
    core.restore_database_backup(archive_path, ['bugs_report'])
    assert [bug['title'] for bug in list_bugs(core.repository)] == ['Export fails']


def test_the_database_viewer_shows_screenshots_as_their_size_and_does_not_edit_them(client):
    login(client)
    open_bug(client)
    assert {'bug_reports', 'bug_report_comments', 'bug_report_attachments'} <= set(core.repository.list_database_tables())
    page = core.repository.database_table_page('bug_report_attachments')
    row = page['rows'][0]
    assert row['content'] == f'[binary data, {len(PNG):,} bytes]'
    with pytest.raises(ValueError, match='Binary values'):
        core.repository.update_database_table_row('bug_report_attachments', int(row['__database_rowid__']), {'content': 'x'})
    admin = client.get('/admin').text
    assert 'data-type="Bugs Report"' in admin and '>Bug Report Attachments<' in admin


def test_descriptions_and_comments_read_with_nested_bullets_and_titles(client):
    from src.modules.bugs_report import rich_text_html

    text = 'Problem:\n- item1\n  - Item2\n    * item3\n- item4:\n  · under\n  goes on\n\nA plain line - not a bullet\nResolution: done.\n<b>x</b>'
    assert str(rich_text_html(text)) == (
        '<p class="bug-text-heading">Problem:</p>'
        '<ul><li>item1<ul><li>Item2<ul><li>item3</li></ul></li></ul></li>'
        '<li><span class="bug-text-heading">item4:</span><ul><li>under<br>goes on</li></ul></li></ul>'
        '<p>A plain line - not a bullet<br>Resolution: done.<br>&lt;b&gt;x&lt;/b&gt;</p>'
    )
    login(client)
    bug_id = open_bug(client, screenshots=())
    client.post(f'/api/bugs-report/{bug_id}/comments', data={'body': 'Cause:\n- One\n  - Two'})
    page = client.get(f'/bugs-report/{bug_id}').text
    # The comment reads with its bullets and keeps how it was written, to edit it.
    assert '<p class="bug-text-heading">Cause:</p><ul><li>One<ul><li>Two</li></ul></li></ul>' in page
    assert 'data-raw="Cause:\n- One\n  - Two"' in page
    assert 'placeholder="Problem:\n- What you did and what happened' in page


def test_anyone_reads_bug_reports_without_signing_in_but_only_signed_in_users_change_them(client):
    login(client)
    bug_id = open_bug(client)
    client.post(f'/api/bugs-report/{bug_id}/comments', data={'body': 'Seen in DE too'})
    from src.modules.bugs_report import get_bug
    screenshot = get_bug(core.repository, bug_id)['attachments'][0]['id']

    client.cookies.clear()
    listing = client.get('/bugs-report', follow_redirects=False)
    assert listing.status_code == 200 and 'Export fails' in listing.text
    assert 'href="/login?next=/bugs-report">Sign in to report a bug</a>' in listing.text
    assert 'data-bugs-create-form' not in listing.text and 'data-bugs-stat="mine"' not in listing.text
    page = client.get(f'/bugs-report/{bug_id}', follow_redirects=False)
    assert page.status_code == 200 and 'Export fails' in page.text and 'Seen in DE too' in page.text
    assert f'href="/login?next=/bugs-report/{bug_id}">Sign in</a> to comment' in page.text
    assert f'class="topnav-link topnav-link-signin" href="/login?next=/bugs-report/{bug_id}"' in page.text
    assert not any(marker in page.text for marker in ('data-bug-comment-form', 'data-bug-edit-toggle', 'data-bug-manage-form', 'data-bug-shot-delete'))
    assert client.get(f'/bugs-report/attachments/{screenshot}').content == PNG
    # Opening, commenting and editing need a session.
    assert client.post('/api/bugs-report', data={'title': 'Anonymous'}).status_code == 401
    assert client.post(f'/api/bugs-report/{bug_id}/comments', data={'body': 'Anonymous'}).status_code == 401
    assert client.post(f'/api/bugs-report/{bug_id}/update', data={'priority': 'P1'}).status_code == 401

    # Signing in from a bug report returns to it; a link to another site is ignored.
    assert f'name="next" value="/bugs-report/{bug_id}"' in client.get(f'/login?next=/bugs-report/{bug_id}').text
    signed_in = client.post('/login', data={'username': 'super', 'password': 'super123', 'next': f'/bugs-report/{bug_id}'}, follow_redirects=False)
    assert signed_in.headers['location'] == f'/bugs-report/{bug_id}'
    client.cookies.clear()
    elsewhere = client.post('/login', data={'username': 'super', 'password': 'super123', 'next': '//evil.example/x'}, follow_redirects=False)
    assert elsewhere.headers['location'] == '/documents/view/help'


def test_super_admins_change_the_reporter_module_and_version_of_any_bug_report(client):
    add_user('ana')
    add_user('bob')
    login(client, 'ana', 'secret123')
    bug_id = open_bug(client, screenshots=())
    assert client.post(f'/api/bugs-report/{bug_id}/manage', data={'created_by': 'bob'}).status_code == 403

    login(client)
    changes = client.post(f'/api/bugs-report/{bug_id}/manage', data={
        'created_by': 'bob', 'module': 'reporting', 'app_version': '0.6.1', 'assigned_to': 'super',
    }).json()['changes']
    assert changes == {'created_by': ['ana', 'bob'], 'module': ['scoring', 'reporting'], 'app_version': [__version__, '0.6.1'],
                       'assigned_to': ['', 'super']}
    assert client.post(f'/api/bugs-report/{bug_id}/manage', data={'created_by': 'nobody'}).status_code == 400
    assert client.post(f'/api/bugs-report/{bug_id}/manage', data={'module': 'not-a-module'}).status_code == 400
    assert client.post(f'/api/bugs-report/{bug_id}/manage', data={'app_version': ' '}).status_code == 400
    page = client.get(f'/bugs-report/{bug_id}').text
    assert 'changed Reported by from <em>ana</em> to <em>bob</em>' in page and 'changed Opened with from <em>v' in page
    assert '<h3>Manage</h3>' in page and 'name="created_by"' in page and 'name="app_version"' in page
    # The new reporter edits the bug report; the former one no longer does.
    login(client, 'bob', 'secret123')
    assert client.post(f'/api/bugs-report/{bug_id}/update', data={'priority': 'P1'}).status_code == 200
    login(client, 'ana', 'secret123')
    assert client.post(f'/api/bugs-report/{bug_id}/update', data={'priority': 'P5'}).status_code == 403
