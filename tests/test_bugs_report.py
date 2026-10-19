"""Ticket Center (formerly Bugs Report): tickets of a type with screenshots, the reporter's edits, the super-admins'
attention, the dashboard, access, the former addresses and portability."""
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


def open_bug(client, title='Export fails', priority='P2', screenshots=(('screen.png', PNG),), ticket_type='bug', module='scoring'):
    response = client.post('/api/tickets', data={'title': title, 'description': 'It fails.', 'module': module, 'priority': priority,
                                                 'ticket_type': ticket_type},
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
    page = client.get('/tickets')
    assert page.status_code == 200
    assert 'id="section-new-ticket"' in page.text and 'id="section-tickets"' in page.text
    # Each tile of the header lists its tickets, and the list filters them by chips and reporter too.
    assert 'data-bugs-filter="reporter"' in page.text
    assert all(f'data-bugs-stat="{key}"' in page.text for key in ('open', 'new', 'in_progress', 'waiting_info', 'recent', 'mine'))
    assert all(f'data-chip="{group}"' in page.text for group in ('types', 'statuses', 'priorities'))
    assert f'Ticket Center · Version {__version__}' in page.text
    # Its tab is a link even without a workspace, unlike the modules that use one.
    assert 'module-tab module-tab-bugs-report' in page.text and 'href="/tickets" title="Open Ticket Center"' in page.text
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
    image = client.get(f"/tickets/attachments/{bug['attachments'][0]['id']}")
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png' and image.content == PNG
    assert logged('bug_report_created')[0]['screenshots'] == ['screen.png']
    page = client.get(f'/tickets/{bug_id}')
    assert page.status_code == 200 and 'Export fails' in page.text and f'v{__version__}' in page.text
    # Only images are attached, and a bug needs a title.
    refused = client.post('/api/tickets', data={'title': 'Text', 'ticket_type': 'bug'}, files=[('screenshots', ('notes.txt', b'hello', 'text/plain'))])
    assert refused.status_code == 400 and 'not a PNG, JPEG, GIF or WebP image' in refused.json()['detail']
    assert client.post('/api/tickets', data={'title': '  ', 'ticket_type': 'bug'}).status_code == 400


def test_the_reporter_edits_and_only_super_admins_attend(client):
    add_user('ana')
    add_user('bob')
    login(client, 'ana', 'secret123')
    bug_id = open_bug(client)
    listing = client.get('/tickets').text
    assert '<option value="ana" data-name="ana">ana</option>' in listing and 'data-reporter="ana"' in listing
    assert client.post(f'/api/tickets/{bug_id}/update', data={'priority': 'P1', 'title': 'Export always fails'}).json()['changes'] == {
        'priority': ['P2', 'P1'], 'title': ['Export fails', 'Export always fails']}
    assert client.post(f'/api/tickets/{bug_id}/manage', data={'status': 'resolved'}).status_code == 403
    login(client, 'bob', 'secret123')
    assert client.post(f'/api/tickets/{bug_id}/update', data={'priority': 'P5'}).status_code == 403
    comment = client.post(f'/api/tickets/{bug_id}/comments', data={'body': 'Me too'}).json()['id']
    assert client.post(f'/api/tickets/comments/{comment}/update', data={'body': 'Me too, in DE'}).status_code == 200

    login(client)
    assert client.post(f'/api/tickets/comments/{comment}/update', data={'body': 'No'}).status_code == 403
    attended = client.post(f'/api/tickets/{bug_id}/manage', data={'status': 'in_progress'}).json()['changes']
    assert attended == {'status': ['new', 'in_progress'], 'assigned_to': ['', 'super']}
    assert client.post(f'/api/tickets/{bug_id}/manage', data={'assigned_to': 'ana'}).status_code == 400
    resolved = client.post(f'/api/tickets/{bug_id}/manage', data={'status': 'resolved'}).json()['changes']
    assert resolved == {'status': ['in_progress', 'resolved'], 'fixed_version': ['', __version__]}
    from src.modules.bugs_report import get_bug
    bug = get_bug(core.repository, bug_id)
    assert bug['resolved_at'] and [entry['kind'] for entry in bug['comments']] == ['change', 'comment', 'change', 'change']
    page = client.get(f'/tickets/{bug_id}').text
    assert 'changed Status from <em>In Progress</em> to <em>Resolved</em>' in page and 'Me too, in DE' in page
    # Reopened, the date it was resolved is cleared.
    client.post(f'/api/tickets/{bug_id}/manage', data={'status': 'waiting_info'})
    assert get_bug(core.repository, bug_id)['resolved_at'] == ''
    assert client.post(f'/api/tickets/comments/{comment}/delete').status_code == 200
    assert client.post(f'/api/tickets/{bug_id}/delete').json()['deleted']
    assert client.get(f'/tickets/{bug_id}').status_code == 404
    assert [entry['bug_id'] for entry in logged('bug_report_deleted')] == [bug_id]
    assert logged('bug_report_managed') and logged('bug_report_updated') and logged('bug_report_commented')


def test_accounts_without_the_module_cannot_open_it(client):
    profile_id = core.repository.save_modules_profile(None, 'Only Workspace', '', ['workspace'])
    user_id = core.repository.create_user('carl', 'secret123', 'user-editor')
    core.repository.set_users_modules_profile([user_id], profile_id)
    core.invalidate_module_access_cache()
    login(client, 'carl', 'secret123')
    assert client.get('/tickets').status_code == 403
    assert client.post('/api/tickets', data={'title': 'x'}).status_code == 403


def test_bugs_report_exports_imports_and_backs_up_on_its_own(client):
    login(client)
    bug_id = open_bug(client)
    client.post(f'/api/tickets/{bug_id}/comments', data={'body': 'See this'}, files=[('screenshots', ('detail.png', PNG, 'image/png'))])
    package, filename = core.build_export_archive('bugs-report')
    assert filename.startswith('drivetest-analyzer-ticket-center_')
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
        assert notice.startswith('Ticket Center imported: 1 new and 0 updated tickets, 1 comments and 2 screenshots')
        # Imported again, nothing is duplicated.
        assert core.import_bugs_report(archive).startswith('Ticket Center imported: 0 new and 0 updated tickets, 0 comments and 0 screenshots')
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
    assert 'data-type="Ticket Center"' in admin and '>Ticket Attachments<' in admin


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
    client.post(f'/api/tickets/{bug_id}/comments', data={'body': 'Cause:\n- One\n  - Two'})
    page = client.get(f'/tickets/{bug_id}').text
    # The comment reads with its bullets and keeps how it was written, to edit it.
    assert '<p class="bug-text-heading">Cause:</p><ul><li>One<ul><li>Two</li></ul></li></ul>' in page
    assert 'data-raw="Cause:\n- One\n  - Two"' in page
    assert 'placeholder="Problem:\n- What you did and what happened' in page


def test_anyone_reads_bug_reports_without_signing_in_but_only_signed_in_users_change_them(client):
    login(client)
    bug_id = open_bug(client)
    client.post(f'/api/tickets/{bug_id}/comments', data={'body': 'Seen in DE too'})
    from src.modules.bugs_report import get_bug
    screenshot = get_bug(core.repository, bug_id)['attachments'][0]['id']

    client.cookies.clear()
    listing = client.get('/tickets', follow_redirects=False)
    assert listing.status_code == 200 and 'Export fails' in listing.text
    assert 'href="/login?next=/tickets">Sign in to open a ticket</a>' in listing.text
    assert 'data-bugs-create-form' not in listing.text and 'data-bugs-stat="mine"' not in listing.text
    page = client.get(f'/tickets/{bug_id}', follow_redirects=False)
    assert page.status_code == 200 and 'Export fails' in page.text and 'Seen in DE too' in page.text
    assert f'href="/login?next=/tickets/{bug_id}">Sign in</a> to comment' in page.text
    assert f'class="topnav-link topnav-link-signin" href="/login?next=/tickets/{bug_id}"' in page.text
    assert not any(marker in page.text for marker in ('data-bug-comment-form', 'data-bug-edit-toggle', 'data-bug-manage-form', 'data-bug-shot-delete'))
    assert client.get(f'/tickets/attachments/{screenshot}').content == PNG
    # Opening, commenting and editing need a session.
    assert client.post('/api/tickets', data={'title': 'Anonymous'}).status_code == 401
    assert client.post(f'/api/tickets/{bug_id}/comments', data={'body': 'Anonymous'}).status_code == 401
    assert client.post(f'/api/tickets/{bug_id}/update', data={'priority': 'P1'}).status_code == 401

    # Signing in from a ticket returns to it; a link to another site is ignored.
    assert f'name="next" value="/tickets/{bug_id}"' in client.get(f'/login?next=/tickets/{bug_id}').text
    signed_in = client.post('/login', data={'username': 'super', 'password': 'super123', 'next': f'/tickets/{bug_id}'}, follow_redirects=False)
    assert signed_in.headers['location'] == f'/tickets/{bug_id}'
    client.cookies.clear()
    elsewhere = client.post('/login', data={'username': 'super', 'password': 'super123', 'next': '//evil.example/x'}, follow_redirects=False)
    assert elsewhere.headers['location'] == '/documents/view/help'


def test_super_admins_change_the_reporter_module_and_version_of_any_bug_report(client):
    add_user('ana')
    add_user('bob')
    login(client, 'ana', 'secret123')
    bug_id = open_bug(client, screenshots=())
    assert client.post(f'/api/tickets/{bug_id}/manage', data={'created_by': 'bob'}).status_code == 403

    login(client)
    changes = client.post(f'/api/tickets/{bug_id}/manage', data={
        'created_by': 'bob', 'module': 'reporting', 'app_version': '0.6.1', 'assigned_to': 'super',
    }).json()['changes']
    assert changes == {'created_by': ['ana', 'bob'], 'module': ['scoring', 'reporting'], 'app_version': [__version__, '0.6.1'],
                       'assigned_to': ['', 'super']}
    assert client.post(f'/api/tickets/{bug_id}/manage', data={'created_by': 'nobody'}).status_code == 400
    assert client.post(f'/api/tickets/{bug_id}/manage', data={'module': 'not-a-module'}).status_code == 400
    assert client.post(f'/api/tickets/{bug_id}/manage', data={'app_version': ' '}).status_code == 400
    page = client.get(f'/tickets/{bug_id}').text
    assert 'changed Reported by from <em>ana</em> to <em>bob</em>' in page and 'changed Opened with from <em>v' in page
    assert '<h3>Manage</h3>' in page and 'name="created_by"' in page and 'name="app_version"' in page
    # The new reporter edits the ticket; the former one no longer does.
    login(client, 'bob', 'secret123')
    assert client.post(f'/api/tickets/{bug_id}/update', data={'priority': 'P1'}).status_code == 200
    login(client, 'ana', 'secret123')
    assert client.post(f'/api/tickets/{bug_id}/update', data={'priority': 'P5'}).status_code == 403


def test_a_ticket_has_a_type_that_only_super_admins_change(client):
    add_user('ana')
    login(client, 'ana', 'secret123')
    missing = client.post('/api/tickets', data={'title': 'Faster maps', 'priority': 'P3'})
    assert missing.status_code == 400 and 'Choose the type of the ticket' in missing.json()['detail']
    assert client.post('/api/tickets', data={'title': 'Faster maps', 'ticket_type': 'wish'}).status_code == 400
    ticket_id = open_bug(client, title='Faster maps', ticket_type='improvement', screenshots=())
    assert logged('bug_report_created')[0]['type'] == 'improvement'
    listing = client.get('/tickets').text
    assert f'data-id="{ticket_id}" data-type="improvement"' in listing and '<span class="ticket-type" data-type="improvement">' in listing
    # Its reporter edits it, but does not change its type.
    assert client.post(f'/api/tickets/{ticket_id}/update', data={'ticket_type': 'bug'}).json()['changes'] == {}
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'ticket_type': 'bug'}).status_code == 403

    login(client)
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'ticket_type': 'wish'}).status_code == 400
    changes = client.post(f'/api/tickets/{ticket_id}/manage', data={'ticket_type': 'new_feature'}).json()['changes']
    assert changes == {'ticket_type': ['improvement', 'new_feature']}
    assert logged('bug_report_managed')[0]['changes'] == {'ticket_type': ['improvement', 'new_feature']}
    page = client.get(f'/tickets/{ticket_id}').text
    assert 'changed Type from <em>Improvement</em> to <em>New Feature</em>' in page
    assert '<select name="ticket_type">' in page and '<option value="new_feature" selected>New Feature</option>' in page
    # The guide of its type shows in the empty comment.
    assert 'placeholder="Need:\n- What you want to do and why' in page


def test_the_tickets_of_earlier_versions_become_bugs(client):
    login(client)
    open_bug(client, ticket_type='new_feature', screenshots=())
    with core.repository.global_connection() as conn:
        conn.execute('ALTER TABLE bug_reports DROP COLUMN ticket_type')
        conn.execute("INSERT INTO bug_reports (uid, title, created_by, created_at, updated_at) VALUES ('old', 'Old bug', 'super', '2026-01-02T10:00:00', '2026-01-02T10:00:00')")
    core.repository.initialize()
    from src.modules.bugs_report import list_bugs
    assert sorted((bug['title'], bug['ticket_type']) for bug in list_bugs(core.repository)) == [('Export fails', 'bug'), ('Old bug', 'bug')]


def test_the_addresses_of_bugs_report_lead_to_ticket_center(client):
    login(client)
    ticket_id = open_bug(client)
    for former, current in (('/bugs-report', '/tickets'), ('/bugs-report?status=new', '/tickets?status=new'),
                            (f'/bugs-report/{ticket_id}', f'/tickets/{ticket_id}'), ('/bugs-report/attachments/1', '/tickets/attachments/1')):
        response = client.get(former, follow_redirects=False)
        assert (response.status_code, response.headers['location']) == (307, current)
    # A page opened before the rename still comments, keeping its form.
    assert client.post(f'/api/bugs-report/{ticket_id}/comments', data={'body': 'Still here'}).status_code == 200
    assert 'Still here' in client.get(f'/bugs-report/{ticket_id}').text
    client.cookies.clear()
    assert client.get('/bugs-report', follow_redirects=False).headers['location'] == '/tickets'


def test_the_dashboard_counts_tickets_by_type_status_priority_module_and_week():
    from datetime import date

    from src.modules.bugs_report import recently_resolved, ticket_dashboard

    def ticket(number, ticket_type, status, priority='P3', module='', created='2026-10-05', resolved='', created_by='ana'):
        return {'id': number, 'title': f'T{number}', 'ticket_type': ticket_type, 'status': status, 'priority': priority, 'module': module,
                'module_title': module.title() or 'General', 'module_color': '#123456', 'created_by': created_by,
                'created_at': f'{created}T09:00:00+01:00', 'resolved_at': f'{resolved}T10:00:00+01:00' if resolved else ''}

    today = date(2026, 10, 19)  # A Monday.
    tickets = [
        ticket(1, 'bug', 'new', 'P1', 'scoring', created='2026-08-01'),
        ticket(2, 'bug', 'in_progress', 'P1', 'scoring', created_by='bob'),
        ticket(3, 'bug', 'resolved', created='2026-10-12', resolved='2026-10-14'),
        ticket(4, 'improvement', 'waiting_info', 'P4', 'reporting', created='2026-10-19'),
        ticket(5, 'improvement', 'closed', created='2026-07-01', resolved='2026-09-01'),
        ticket(6, 'new_feature', 'rejected', resolved='2026-10-06'),
    ]
    board = ticket_dashboard(tickets, username='ANA', today=today)
    assert board['kpis'] == {'open': 3, 'new': 1, 'in_progress': 1, 'waiting_info': 1, 'resolved_recent': 1, 'mine_open': 2}
    assert [recently_resolved(item, today) for item in tickets] == [False, False, True, False, False, False]
    rows = {row['type']: row for row in board['types']}
    assert rows['bug']['counts'] == {'new': 1, 'in_progress': 1, 'waiting_info': 0, 'resolved': 1, 'closed': 0, 'rejected': 0}
    assert (rows['bug']['total'], rows['bug']['open'], rows['new_feature']['total'], rows['new_feature']['open']) == (3, 2, 1, 0)
    assert [(item['priority'], item['count']) for item in rows['bug']['priorities']] == [('P1', 2), ('P2', 0), ('P3', 0), ('P4', 0), ('P5', 0)]
    assert [(segment['status'], segment['count']) for segment in rows['improvement']['segments']] == [('waiting_info', 1), ('closed', 1)]
    assert board['status_totals'] == {'new': 1, 'in_progress': 1, 'waiting_info': 1, 'resolved': 1, 'closed': 1, 'rejected': 1}
    assert [(module['key'], module['count']) for module in board['modules']] == [('scoring', 2), ('reporting', 1)]
    # Twelve weeks from Monday, the current one last: what was created and resolved (not rejected) in each.
    weeks = board['weeks']
    assert len(weeks) == 12 and weeks[0]['start'] == date(2026, 8, 3) and weeks[-1]['start'] == today
    assert [(week['created'], week['resolved']) for week in weeks[-3:]] == [(2, 0), (1, 1), (1, 0)]
    assert (board['weeks_created'], board['weeks_resolved'], board['week_peak']) == (4, 2, 2)
    assert board['oldest_open'] == {'id': 1, 'title': 'T1', 'ticket_type': 'bug', 'days': 79, 'created_date': '2026-08-01'}
    assert ticket_dashboard([], today=today)['oldest_open'] is None


def test_the_type_travels_with_the_tickets_and_packages_of_before_import_as_bugs(client):
    login(client)
    open_bug(client, title='Dark theme', ticket_type='new_feature', screenshots=())
    from src.modules.bugs_report import EXPORT_VERSION, bugs_report_payload, delete_bug, list_bugs, merge_bugs_report
    payload, files = bugs_report_payload(core.repository)
    assert payload['version'] == EXPORT_VERSION == 2 and payload['bug_reports'][0]['ticket_type'] == 'new_feature'
    delete_bug(core.repository, int(list_bugs(core.repository)[0]['id']))
    # A Bugs Report package of an earlier version has no type: its tickets are bugs.
    former = {**payload, 'version': 1, 'bug_reports': [{key: value for key, value in payload['bug_reports'][0].items() if key != 'ticket_type'}
                                                       | {'uid': 'former', 'title': 'Old export'}]}
    merge_bugs_report(core.repository, payload, files)
    merge_bugs_report(core.repository, former, {})
    assert sorted((bug['title'], bug['ticket_type']) for bug in list_bugs(core.repository)) == [('Dark theme', 'new_feature'), ('Old export', 'bug')]


def test_a_stored_bugs_report_title_becomes_ticket_center_once(client):
    from src.modules.module_labels import (
        MODULE_LABELS_STATE_KEY, TICKET_CENTER_TITLE_MIGRATION_KEY, load_module_labels, migrate_ticket_center_title,
    )

    core.repository.set_application_state(TICKET_CENTER_TITLE_MIGRATION_KEY, '')
    profile = next(item for item in core.repository.list_modules_profiles() if item['name'] == 'Non-Qualified Calls')
    core.repository.save_modules_profile(profile['id'], profile['name'], 'Workspace, Non-Qualified Calls, Reporting, Builders & Bugs Report.',
                                         profile['modules'])
    core.repository.set_application_state(MODULE_LABELS_STATE_KEY, json.dumps({
        'bugs-report': {'title': 'Bugs Report', 'short_title': 'Bugs', 'tab_icon': 'bugs-report', 'tab_color': '#123456'}}))
    assert migrate_ticket_center_title(core.repository) is True
    label = load_module_labels(core.repository)['bugs-report']
    assert (label['title'], label['short_title'], label['tab_icon'], label['tab_color']) == ('Ticket Center', 'Tickets', 'ticket-center', '#123456')
    profile = next(item for item in core.repository.list_modules_profiles() if item['name'] == 'Non-Qualified Calls')
    assert profile['description'] == 'Workspace, Non-Qualified Calls, Reporting, Builders & Ticket Center.'
    # A name chosen afterwards stays, and the page and its notices take it.
    core.repository.set_application_state(MODULE_LABELS_STATE_KEY, json.dumps({'bugs-report': {'title': 'Bugs Report'}}))
    assert migrate_ticket_center_title(core.repository) is False
    login(client)
    assert 'Bugs Report · Version' in client.get('/tickets').text
    assert client.get('/api/admin-notices').json()['bugs_report_title'] == 'Bugs Report'
