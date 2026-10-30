"""Ticket Center (formerly Bugs Report): tickets of a type with screenshots, the reporter's edits, the super-admins'
attention, the design, access, the former addresses and portability."""
import html
import io
import json
import re
import time
import zipfile
from pathlib import Path

import pytest

import src.DriveTestAnalyzer as core
from src.modules.module_labels import section_links
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


def open_ticket(client, title='Export fails', priority='P2', screenshots=(('screen.png', PNG),), ticket_type='bug', module='scoring'):
    response = client.post('/api/tickets', data={'title': title, 'description': 'It fails.', 'module': module, 'priority': priority,
                                                 'ticket_type': ticket_type},
                           files=[('screenshots', (name, content, 'image/png')) for name, content in screenshots])
    assert response.status_code == 200, response.text
    return response.json()['id']


def logged(action):
    return [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == action]


def test_ticket_center_is_in_every_profile_once_and_opens_without_a_workspace(client):
    assert all('ticket-center' in profile['modules'] for profile in core.repository.list_modules_profiles())
    # A deployment from before the module gets it in every profile once; a profile it is taken out of keeps without it.
    nq = next(profile for profile in core.repository.list_modules_profiles() if profile['name'] == 'Non-Qualified Calls')
    with core.repository.global_connection() as conn:
        conn.execute("DELETE FROM application_state WHERE key = 'modules_profiles_added_modules'")
        conn.execute('UPDATE modules_profiles SET modules_json = ? WHERE id = ?', (json.dumps(['workspace', 'non-qualified-calls']), nq['id']))
    core.repository.initialize()
    modules = {profile['name']: profile['modules'] for profile in core.repository.list_modules_profiles()}
    assert modules['Non-Qualified Calls'] == ['workspace', 'non-qualified-calls', 'ticket-center']
    core.repository.save_modules_profile(nq['id'], nq['name'], nq['description'], ['workspace', 'non-qualified-calls'])
    core.repository.initialize()
    assert 'ticket-center' not in next(item for item in core.repository.list_modules_profiles() if item['id'] == nq['id'])['modules']

    login(client)
    core.close_active_workspace()
    page = client.get('/tickets')
    assert page.status_code == 200
    assert 'id="section-new-ticket"' in page.text and 'id="section-all-tickets"' in page.text
    # Each tile of the header lists its tickets, and the list filters them by chips and reporter too.
    assert 'data-tickets-filter="reporter"' in page.text
    assert all(f'data-tickets-stat="{key}"' in page.text for key in ('open', 'new', 'in_progress', 'waiting_info', 'recent', 'mine'))
    assert all(f'data-chip="{group}"' in page.text for group in ('types', 'statuses', 'priorities'))
    # Each group of chips starts with All, and the header chooses the view: the dashboard, Statistics or the tickets.
    assert all(f'data-chip-all="{group}"' in page.text for group in ('types', 'statuses', 'priorities'))
    assert all(f'data-tickets-tab="{view}"' in page.text for view in ('new-ticket', 'dashboard', 'statistics', 'tickets'))
    assert all(f'id="section-{view}"' in page.text for view in ('new-ticket', 'all-tickets', 'dashboard', 'statistics'))
    assert 'module-hero-ticket-center' in page.text
    # The sections menu of the tab lists the views in the order of the tabs.
    assert [entry[1] for entry in section_links('/tickets', 'ticket-center')] == ['New Ticket', 'All Tickets', 'Dashboard', 'Statistics']
    assert f'Ticket Center · Version {__version__}' in page.text
    # Its tab is a link even without a workspace, unlike the modules that use one.
    assert 'module-tab module-tab-ticket-center' in page.text and 'href="/tickets" title="Open Ticket Center"' in page.text
    assert 'title="Open a workspace to use Scoring &amp; GAP Analysis"' in page.text


def test_a_user_reports_a_bug_with_screenshots_and_its_version(client):
    add_user('ana', 'user-viewer')
    login(client, 'ana', 'secret123')
    ticket_id = open_ticket(client)
    from src.modules.ticket_center import get_ticket
    ticket = get_ticket(core.repository, ticket_id)
    assert (ticket['title'], ticket['priority'], ticket['status'], ticket['module'], ticket['created_by']) == ('Export fails', 'P2', 'new', 'scoring', 'ana')
    assert ticket['app_version'] == __version__ and ticket['created_at'][:4].isdigit()
    assert [item['file_name'] for item in ticket['attachments']] == ['screen.png']
    image = client.get(f"/tickets/attachments/{ticket['attachments'][0]['id']}")
    assert image.status_code == 200 and image.headers['content-type'] == 'image/png' and image.content == PNG
    assert logged('ticket_created')[0]['screenshots'] == ['screen.png']
    page = client.get(f'/tickets/{ticket_id}')
    assert page.status_code == 200 and 'Export fails' in page.text and f'v{__version__}' in page.text
    # Only images are attached, and a bug needs a title.
    refused = client.post('/api/tickets', data={'title': 'Text', 'ticket_type': 'bug'}, files=[('screenshots', ('notes.txt', b'hello', 'text/plain'))])
    assert refused.status_code == 400 and 'not a PNG, JPEG, GIF or WebP image' in refused.json()['detail']
    assert client.post('/api/tickets', data={'title': '  ', 'ticket_type': 'bug'}).status_code == 400


def test_the_reporter_edits_and_only_super_admins_attend(client):
    add_user('ana')
    add_user('bob')
    login(client, 'ana', 'secret123')
    ticket_id = open_ticket(client)
    listing = client.get('/tickets').text
    assert '<option value="ana" data-name="ana">ana</option>' in listing and 'data-reporter="ana"' in listing
    assert client.post(f'/api/tickets/{ticket_id}/update', data={'priority': 'P1', 'title': 'Export always fails'}).json()['changes'] == {
        'priority': ['P2', 'P1'], 'title': ['Export fails', 'Export always fails']}
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'status': 'resolved'}).status_code == 403
    login(client, 'bob', 'secret123')
    assert client.post(f'/api/tickets/{ticket_id}/update', data={'priority': 'P5'}).status_code == 403
    comment = client.post(f'/api/tickets/{ticket_id}/comments', data={'body': 'Me too'}).json()['id']
    assert client.post(f'/api/tickets/comments/{comment}/update', data={'body': 'Me too, in DE'}).status_code == 200

    login(client)
    assert client.post(f'/api/tickets/comments/{comment}/update', data={'body': 'No'}).status_code == 403
    attended = client.post(f'/api/tickets/{ticket_id}/manage', data={'status': 'in_progress'}).json()['changes']
    assert attended == {'status': ['new', 'in_progress'], 'assigned_to': ['', 'super']}
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'assigned_to': 'ana'}).status_code == 400
    resolved = client.post(f'/api/tickets/{ticket_id}/manage', data={'status': 'resolved'}).json()['changes']
    assert resolved == {'status': ['in_progress', 'resolved'], 'fixed_version': ['', __version__]}
    from src.modules.ticket_center import get_ticket
    ticket = get_ticket(core.repository, ticket_id)
    assert ticket['resolved_at'] and [entry['kind'] for entry in ticket['comments']] == ['change', 'comment', 'change', 'change']
    page = client.get(f'/tickets/{ticket_id}').text
    assert 'changed Status from <em>In Progress</em> to <em>Resolved</em>' in page and 'Me too, in DE' in page
    # Reopened, the date it was resolved is cleared.
    client.post(f'/api/tickets/{ticket_id}/manage', data={'status': 'waiting_info'})
    assert get_ticket(core.repository, ticket_id)['resolved_at'] == ''
    assert client.post(f'/api/tickets/comments/{comment}/delete').status_code == 200
    assert client.post(f'/api/tickets/{ticket_id}/delete').json()['deleted']
    assert client.get(f'/tickets/{ticket_id}').status_code == 404
    assert [entry['ticket_id'] for entry in logged('ticket_deleted')] == [ticket_id]
    assert logged('ticket_managed') and logged('ticket_updated') and logged('ticket_commented')


def test_accounts_without_the_module_cannot_open_it(client):
    profile_id = core.repository.save_modules_profile(None, 'Only Workspace', '', ['workspace'])
    user_id = core.repository.create_user('carl', 'secret123', 'user-editor')
    core.repository.set_users_modules_profile([user_id], profile_id)
    core.invalidate_module_access_cache()
    login(client, 'carl', 'secret123')
    assert client.get('/tickets').status_code == 403
    assert client.post('/api/tickets', data={'title': 'x'}).status_code == 403


def test_ticket_center_exports_imports_and_backs_up_on_its_own(client):
    login(client)
    ticket_id = open_ticket(client)
    client.post(f'/api/tickets/{ticket_id}/comments', data={'body': 'See this'}, files=[('screenshots', ('detail.png', PNG, 'image/png'))])
    package, filename = core.build_export_archive('ticket-center')
    assert filename.startswith('drivetest-analyzer-ticket-center_')
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read('manifest.json'))
    assert manifest['kind'] == 'ticket-center' and manifest['components'] == ['ticket_center']
    assert 'ticket-center/ticket-center.json' in names and len([name for name in names if name.startswith('ticket-center/attachments/')]) == 2

    from src.modules.ticket_center import delete_ticket, list_tickets
    delete_ticket(core.repository, ticket_id)
    inspected = client.post('/admin/import-export/inspect/upload', content=package, headers={'X-Import-File-Name': 'bugs.zip'})
    assert inspected.status_code == 200 and inspected.json()['kind'] == 'ticket-center'
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        notice = core.import_ticket_center(archive)
        assert notice == 'Imported Ticket Center: 1 ticket (1 new), 1 new comment and 2 new screenshots.'
        # Imported again, nothing is duplicated nor counted as updated.
        assert core.import_ticket_center(archive) == 'Imported Ticket Center: 1 ticket (1 unchanged), 0 new comments and 0 new screenshots.'
    tickets = list_tickets(core.repository)
    assert [(ticket['title'], ticket['comment_count'], ticket['attachment_count']) for ticket in tickets] == [('Export fails', 1, 2)]

    archive_path = core.create_recurring_database_backup({
        'components': ['ticket_center'], 'backup_path': str(core.application_data_dir / 'scheduled-backups'), 'max_backups': 30, 'workspace_ids': [],
    })
    assert core._backup_archive_components(archive_path) == ['ticket_center']
    delete_ticket(core.repository, int(tickets[0]['id']))
    core.restore_database_backup(archive_path, ['ticket_center'])
    assert [ticket['title'] for ticket in list_tickets(core.repository)] == ['Export fails']


def test_the_database_viewer_shows_screenshots_as_their_size_and_does_not_edit_them(client):
    login(client)
    open_ticket(client)
    assert {'tickets', 'ticket_comments', 'ticket_attachments'} <= set(core.repository.list_database_tables())
    page = core.repository.database_table_page('ticket_attachments')
    row = page['rows'][0]
    assert row['content'] == f'[binary data, {len(PNG):,} bytes]'
    with pytest.raises(ValueError, match='Binary values'):
        core.repository.update_database_table_row('ticket_attachments', int(row['__database_rowid__']), {'content': 'x'})
    admin = client.get('/super-admin').text
    assert 'data-type="Ticket Center"' in admin and '>Ticket Attachments<' in admin


def test_descriptions_and_comments_are_markdown_shown_and_edited_by_the_rich_text_script(client):
    login(client)
    ticket_id = open_ticket(client, screenshots=())
    client.post(f'/api/tickets/{ticket_id}/comments', data={'body': 'Cause\n- One\n  - Two\n<b>x</b>'})
    page = client.get(f'/tickets/{ticket_id}').text
    # The texts are kept as written (escaped) for rich_text.js, which shows them; the text areas become its editors.
    assert 'data-rich-text data-raw="Cause\n- One\n  - Two\n&lt;b&gt;x&lt;/b&gt;"' in page
    assert '<div class="ticket-text" data-rich-text data-raw="It fails.">It fails.</div>' in page
    assert 'js/rich_text.js' in page and 'css/rich_text.css' in page
    assert page.index('js/rich_text.js') < page.index('js/ticket_center.js')
    assert page.count('data-rich-editor data-rich-class="ticket-text"') == 2
    assert 'data-rich-files="form"' in page
    assert 'placeholder="Problem\n- What you did and what happened' in page
    assert 'rich_text_html' not in Path(core.__file__).read_text(encoding='utf-8')
    new_ticket = client.get('/tickets').text
    assert 'data-ticket-description data-rich-editor data-rich-class="ticket-text" data-rich-files="form"' in new_ticket
    assert 'js/rich_text.js' in new_ticket and 'css/rich_text.css' in new_ticket


def test_the_tickets_mentioned_as_numbers_are_given_to_the_rich_text_script(client):
    login(client)
    first = open_ticket(client, title='Export fails', screenshots=())
    second = open_ticket(client, title="Map's labels", screenshots=())
    client.post(f'/api/tickets/{second}/comments', data={'body': f'Same as #{first}, not #9999'})
    page = client.get(f'/tickets/{second}').text
    # The tickets that exist, with their title and status for the tooltip of their links; rich_text.js links them.
    references = json.loads(html.unescape(re.search(r"data-rich-refs='([^']*)'", page).group(1)))
    assert references == {'href': '/tickets/{id}', 'titles': {str(first): 'Export fails · New'},
                          'help': 'A link to ticket 7, once the text is saved'}
    assert "references: window.RichText.referencesOf(page)" in (Path(core.__file__).parent / 'web_interface/static/js/ticket_center.js').read_text(encoding='utf-8')
    client.post(f'/api/tickets/{first}/comments', data={'body': f"See #{second}"})
    page = client.get(f'/tickets/{first}').text
    # A title with a quote stays within the attribute.
    assert json.loads(html.unescape(re.search(r"data-rich-refs='([^']*)'", page).group(1)))['titles'] == {str(second): "Map's labels · New"}


def test_a_ticket_page_goes_to_the_first_previous_next_and_last_tickets(client):
    from src.modules.ticket_center import ticket_neighbours

    assert ticket_neighbours([3, 5, 9], 5) == {'first': 3, 'previous': 3, 'next': 9, 'last': 9, 'position': 2, 'total': 3}
    assert ticket_neighbours([3, 5, 9], 3) == {'first': None, 'previous': None, 'next': 5, 'last': 9, 'position': 1, 'total': 3}
    assert ticket_neighbours([3, 5, 9], 9) == {'first': 3, 'previous': 5, 'next': None, 'last': None, 'position': 3, 'total': 3}
    assert ticket_neighbours([3], 3) == {'first': None, 'previous': None, 'next': None, 'last': None, 'position': 1, 'total': 1}

    login(client)
    first, second, third, fourth = (open_ticket(client, title=title, screenshots=()) for title in ('Export fails', 'Map labels', 'Gone', "Chart's legend"))
    assert client.post(f'/api/tickets/{third}/delete').json()['deleted']
    # By number among every ticket, the way of a ticket outside the Tickets list, whose links keep it.
    page = client.get(f'/tickets/{second}').text
    assert (f'data-ticket-pager-link="first" aria-label="First ticket" href="/tickets/{first}?order=number" '
            f'title="First ticket · #{first} Export fails"') in page
    assert f'data-ticket-pager-link="previous" aria-label="Previous ticket" href="/tickets/{first}?order=number"' in page
    assert (f'data-ticket-pager-link="next" aria-label="Next ticket" href="/tickets/{fourth}?order=number" '
            f'title="Next ticket · #{fourth} Chart&#39;s legend"') in page
    assert f'data-ticket-pager-link="last" aria-label="Last ticket" href="/tickets/{fourth}?order=number"' in page
    assert '<span><strong>2</strong> of 3</span><small>By number</small>' in page
    # The titles of every ticket for the order of the list, which ticket_center.js takes from what the list showed.
    titles = json.loads(html.unescape(re.search(r"data-ticket-titles='([^']*)'", page).group(1)))
    assert titles == [[first, 'Export fails'], [second, 'Map labels'], [fourth, "Chart's legend"]]
    script = (Path(core.__file__).parent / 'web_interface/static/js/ticket_center.js').read_text(encoding='utf-8')
    assert 'window.localStorage.setItem(listOrderKey, JSON.stringify(rows.filter((row) => !row.hidden)' in script
    assert "get('order') !== 'number'" in script
    # The first and the last tickets cannot move further.
    page = client.get(f'/tickets/{first}').text
    assert 'data-ticket-pager-link="first" aria-label="First ticket" aria-disabled="true" title="First ticket"' in page
    assert 'data-ticket-pager-link="previous" aria-label="Previous ticket" aria-disabled="true"' in page
    assert f'data-ticket-pager-link="next" aria-label="Next ticket" href="/tickets/{second}?order=number"' in page
    page = client.get(f'/tickets/{fourth}').text
    assert 'data-ticket-pager-link="next" aria-label="Next ticket" aria-disabled="true"' in page
    assert 'data-ticket-pager-link="last" aria-label="Last ticket" aria-disabled="true"' in page


def test_anyone_reads_tickets_without_signing_in_but_only_signed_in_users_change_them(client):
    login(client)
    ticket_id = open_ticket(client)
    client.post(f'/api/tickets/{ticket_id}/comments', data={'body': 'Seen in DE too'})
    from src.modules.ticket_center import get_ticket
    screenshot = get_ticket(core.repository, ticket_id)['attachments'][0]['id']

    client.cookies.clear()
    listing = client.get('/tickets', follow_redirects=False)
    assert listing.status_code == 200 and 'Export fails' in listing.text
    assert 'href="/login?next=/tickets">Sign in to open a ticket</a>' in listing.text
    assert 'data-tickets-create-form' not in listing.text and 'data-tickets-stat="mine"' not in listing.text
    # The New Ticket tab shows its form, which cannot be filled without signing in.
    assert 'data-tickets-tab="new-ticket"' in listing.text and 'data-tickets-locked' in listing.text
    assert '<form class="tickets-form" inert aria-disabled="true" novalidate>' in listing.text
    page = client.get(f'/tickets/{ticket_id}', follow_redirects=False)
    assert page.status_code == 200 and 'Export fails' in page.text and 'Seen in DE too' in page.text
    assert f'href="/login?next=/tickets/{ticket_id}">Sign in</a> to comment' in page.text
    assert f'class="topnav-link topnav-link-signin" href="/login?next=/tickets/{ticket_id}"' in page.text
    assert not any(marker in page.text for marker in ('data-ticket-comment-form', 'data-ticket-edit-toggle', 'data-ticket-manage-form', 'data-ticket-shot-delete'))
    assert client.get(f'/tickets/attachments/{screenshot}').content == PNG
    # Opening, commenting and editing need a session.
    assert client.post('/api/tickets', data={'title': 'Anonymous'}).status_code == 401
    assert client.post(f'/api/tickets/{ticket_id}/comments', data={'body': 'Anonymous'}).status_code == 401
    assert client.post(f'/api/tickets/{ticket_id}/update', data={'priority': 'P1'}).status_code == 401

    # Signing in from a ticket returns to it; a link to another site is ignored.
    assert f'name="next" value="/tickets/{ticket_id}"' in client.get(f'/login?next=/tickets/{ticket_id}').text
    signed_in = client.post('/login', data={'username': 'super', 'password': 'super123', 'next': f'/tickets/{ticket_id}'}, follow_redirects=False)
    assert signed_in.headers['location'] == f'/tickets/{ticket_id}'
    client.cookies.clear()
    elsewhere = client.post('/login', data={'username': 'super', 'password': 'super123', 'next': '//evil.example/x'}, follow_redirects=False)
    assert elsewhere.headers['location'] == '/documents/view/help'


def test_super_admins_change_the_reporter_module_and_version_of_any_ticket(client):
    add_user('ana')
    add_user('bob')
    login(client, 'ana', 'secret123')
    ticket_id = open_ticket(client, screenshots=())
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'created_by': 'bob'}).status_code == 403

    login(client)
    changes = client.post(f'/api/tickets/{ticket_id}/manage', data={
        'created_by': 'bob', 'module': 'reporting', 'app_version': '0.6.1', 'assigned_to': 'super',
    }).json()['changes']
    assert changes == {'created_by': ['ana', 'bob'], 'module': ['scoring', 'reporting'], 'app_version': [__version__, '0.6.1'],
                       'assigned_to': ['', 'super']}
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'created_by': 'nobody'}).status_code == 400
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'module': 'not-a-module'}).status_code == 400
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'app_version': ' '}).status_code == 400
    page = client.get(f'/tickets/{ticket_id}').text
    assert 'changed Reported by from <em>ana</em> to <em>bob</em>' in page and 'changed Opened with from <em>v' in page
    assert '<h3>Manage</h3>' in page and 'name="created_by"' in page and 'name="app_version"' in page
    # The new reporter edits the ticket; the former one no longer does.
    login(client, 'bob', 'secret123')
    assert client.post(f'/api/tickets/{ticket_id}/update', data={'priority': 'P1'}).status_code == 200
    login(client, 'ana', 'secret123')
    assert client.post(f'/api/tickets/{ticket_id}/update', data={'priority': 'P5'}).status_code == 403


def test_super_admins_correct_the_dates_of_a_ticket_and_its_timeline_follows_them(client):
    from src.modules.ticket_center import get_ticket

    login(client)
    # A ticket recorded after the work it describes: opened, assigned, commented and resolved at once (its new dates in
    # summer time keep the hours given, whatever the time of the server when it was recorded).
    ticket_id = open_ticket(client, screenshots=())
    manage = f'/api/tickets/{ticket_id}/manage'
    client.post(manage, data={'assigned_to': 'super'})
    client.post(f'/api/tickets/{ticket_id}/comments', data={'body': 'Implemented in v0.8.4.'})
    client.post(manage, data={'status': 'resolved', 'fixed_version': '0.8.4'})
    entries = len(get_ticket(core.repository, ticket_id)['comments'])

    changes = client.post(manage, data={'created_at': '2020-07-10T09:30', 'resolved_at': '2020-07-12 18:00'}).json()['changes']

    assert set(changes) == {'created_at', 'resolved_at'}
    ticket = get_ticket(core.repository, ticket_id)
    assert ticket['created_at'].startswith('2020-07-10T09:30') and ticket['resolved_at'].startswith('2020-07-12T18:00')
    # The assignment follows the opening, the resolution (its comment and the change of status) the Resolved date; the
    # timeline keeps its order and records no new entry; the last update is the resolution.
    timeline = [(entry['kind'], entry['created_at'][:16]) for entry in ticket['comments']]
    assert timeline == [('change', '2020-07-10T09:30'), ('comment', '2020-07-12T18:00'), ('change', '2020-07-12T18:00')]
    assert [entry['created_at'] for entry in ticket['comments']] == sorted(entry['created_at'] for entry in ticket['comments'])
    assert len(ticket['comments']) == entries and ticket['updated_at'] == ticket['resolved_at']
    assert set(logged('ticket_managed')[0]['changes']) == {'created_at', 'resolved_at'}
    page = client.get(f'/tickets/{ticket_id}').text
    assert 'Opened by' in page and '2020-07-10 09:30' in page and 'name="created_at"' in page and 'name="resolved_at"' in page
    # Every save of the form sends the dates again: the minute they already have changes nothing.
    assert client.post(manage, data={'created_at': '2020-07-10T09:30', 'resolved_at': '2020-07-12T18:00',
                                     'status': 'resolved'}).json()['changes'] == {}
    assert client.post(manage, data={'resolved_at': '2020-07-09T10:00'}).status_code == 400
    assert client.post(manage, data={'created_at': 'last week'}).status_code == 400
    # Opened again, it has no Resolved date: the one the form still sends is left out.
    reopened = client.post(manage, data={'status': 'in_progress', 'resolved_at': '2020-07-12T18:00'}).json()['changes']
    assert reopened['status'] == ['resolved', 'in_progress'] and 'resolved_at' not in reopened
    assert client.post(manage, data={'resolved_at': '2020-07-13T18:00'}).json()['changes'] == {}


def test_corrected_dates_keep_the_timeline_written_between_and_after_them(monkeypatch):
    from src.modules.ticket_center import add_comment, create_ticket, get_ticket, set_ticket_dates, update_ticket

    # The dates are written in the time of the server: the server of the test is in the time zone of its dates (+01:00
    # in January), also on a machine in UTC.
    monkeypatch.setenv('TZ', 'Europe/Madrid')
    time.tzset()
    repository = core.repository
    repository.initialize()
    ticket_id = create_ticket(repository, title='Slow export', description='', module='', priority='P3', ticket_type='bug',
                              username='super', app_version=__version__, browser='', screenshots=[])
    update_ticket(repository, ticket_id, 'super', {'assigned_to': 'super'})
    add_comment(repository, ticket_id, 'super', 'Found the cause.')
    update_ticket(repository, ticket_id, 'super', {'status': 'resolved'})
    add_comment(repository, ticket_id, 'super', 'Confirmed by the reporter.')
    dates = ['2020-01-02T09:00:00+01:00', '2020-01-03T10:00:00+01:00', '2020-01-05T12:00:00+01:00', '2020-01-09T08:00:00+01:00']
    with repository.global_connection() as conn:
        conn.execute("UPDATE tickets SET created_at = '2020-01-01T10:00:00+01:00', resolved_at = ?, updated_at = ? WHERE id = ?",
                     (dates[2], dates[3], ticket_id))
        for entry_id, moment in zip([row['id'] for row in conn.execute(
                'SELECT id FROM ticket_comments WHERE ticket_id = ? ORDER BY id', (ticket_id,)).fetchall()], dates):
            conn.execute('UPDATE ticket_comments SET created_at = ? WHERE id = ?', (moment, entry_id))

    set_ticket_dates(repository, ticket_id, opened='2019-12-30T08:00:00+01:00', resolved='2020-01-06T12:00:00+01:00')

    ticket = get_ticket(repository, ticket_id)
    # The assignment, between both dates, and the comment written after the resolution keep theirs; the resolution (the
    # change of status and the comment just before it) moves a day with the Resolved date.
    assert [entry['created_at'][:16] for entry in ticket['comments']] == [
        '2020-01-02T09:00', '2020-01-04T10:00', '2020-01-06T12:00', '2020-01-09T08:00']
    assert ticket['created_at'].startswith('2019-12-30T08:00') and ticket['updated_at'].startswith('2020-01-09T08:00')
    with pytest.raises(ValueError, match='Resolved date cannot be before'):
        set_ticket_dates(repository, ticket_id, resolved='2019-12-01T08:00')


def test_a_ticket_has_a_type_that_only_super_admins_change(client):
    add_user('ana')
    login(client, 'ana', 'secret123')
    missing = client.post('/api/tickets', data={'title': 'Faster maps', 'priority': 'P3'})
    assert missing.status_code == 400 and 'Choose the type of the ticket' in missing.json()['detail']
    assert client.post('/api/tickets', data={'title': 'Faster maps', 'ticket_type': 'wish'}).status_code == 400
    ticket_id = open_ticket(client, title='Faster maps', ticket_type='improvement', screenshots=())
    assert logged('ticket_created')[0]['type'] == 'improvement'
    listing = client.get('/tickets').text
    assert f'data-id="{ticket_id}" data-type="improvement"' in listing and '<span class="ticket-type" data-type="improvement">' in listing
    # Its reporter edits it, but does not change its type.
    assert client.post(f'/api/tickets/{ticket_id}/update', data={'ticket_type': 'bug'}).json()['changes'] == {}
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'ticket_type': 'bug'}).status_code == 403

    login(client)
    assert client.post(f'/api/tickets/{ticket_id}/manage', data={'ticket_type': 'wish'}).status_code == 400
    changes = client.post(f'/api/tickets/{ticket_id}/manage', data={'ticket_type': 'new_feature'}).json()['changes']
    assert changes == {'ticket_type': ['improvement', 'new_feature']}
    assert logged('ticket_managed')[0]['changes'] == {'ticket_type': ['improvement', 'new_feature']}
    page = client.get(f'/tickets/{ticket_id}').text
    assert 'changed Type from <em>Improvement</em> to <em>New Feature</em>' in page
    assert '<select name="ticket_type">' in page and '<option value="new_feature" selected>New Feature</option>' in page
    # The guide of its type shows in the empty comment.
    assert 'placeholder="Need\n- What you want to do and why' in page


def test_the_tickets_of_earlier_versions_become_bugs(client):
    login(client)
    open_ticket(client, ticket_type='new_feature', screenshots=())
    with core.repository.global_connection() as conn:
        conn.execute('ALTER TABLE tickets DROP COLUMN ticket_type')
        conn.execute("INSERT INTO tickets (uid, title, created_by, created_at, updated_at) VALUES ('old', 'Old bug', 'super', '2026-01-02T10:00:00', '2026-01-02T10:00:00')")
    core.repository.initialize()
    from src.modules.ticket_center import list_tickets
    assert sorted((ticket['title'], ticket['ticket_type']) for ticket in list_tickets(core.repository)) == [('Export fails', 'bug'), ('Old bug', 'bug')]


def test_the_addresses_of_bugs_report_lead_to_ticket_center(client):
    login(client)
    ticket_id = open_ticket(client)
    for former, current in (('/bugs-report', '/tickets'), ('/bugs-report?status=new', '/tickets?status=new'),
                            (f'/bugs-report/{ticket_id}', f'/tickets/{ticket_id}'), ('/bugs-report/attachments/1', '/tickets/attachments/1')):
        response = client.get(former, follow_redirects=False)
        assert (response.status_code, response.headers['location']) == (307, current)
    # A page opened before the rename still comments, keeping its form.
    assert client.post(f'/api/bugs-report/{ticket_id}/comments', data={'body': 'Still here'}).status_code == 200
    assert 'Still here' in client.get(f'/bugs-report/{ticket_id}').text
    client.cookies.clear()
    assert client.get('/bugs-report', follow_redirects=False).headers['location'] == '/tickets'


def test_the_design_counts_tickets_by_type_status_priority_module_and_period():
    from datetime import date

    from src.modules.ticket_center import TREND_PERIODS, recently_resolved, ticket_dashboard

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
    # Resolved is the last status before the totals, after Rejected and Closed; the bars of each type follow that order.
    assert [status for status, _label in board['statuses']] == ['new', 'in_progress', 'waiting_info', 'rejected', 'closed', 'resolved']
    assert [segment['status'] for segment in rows['bug']['segments']] == ['new', 'in_progress', 'resolved']
    assert board['status_totals'] == {'new': 1, 'in_progress': 1, 'waiting_info': 1, 'resolved': 1, 'closed': 1, 'rejected': 1}
    # Every ticket of each module, those with most open tickets first.
    assert [(module['key'], module['count'], module['total']) for module in board['modules']] == [('scoring', 2, 2), ('reporting', 1, 1), ('', 0, 3)]
    assert board['max_module'] == 3
    # At a glance: open, resolved (or closed) and rejected, this week (from today, a Monday) and the open ones unassigned.
    glance = board['glance']
    assert [(part['key'], part['count']) for part in glance['ring']['segments']] == [('open', 3), ('done', 2), ('rejected', 1)]
    assert (glance['week_opened'], glance['week_resolved'], glance['unassigned'], glance['total']) == (1, 0, 3, 6)
    assert [row['median_resolve'] for row in board['types']] == ['2.0 days', '62 days', '—']
    # A chart per period, Weekly by default: twelve weeks from Monday, the current one last, with what was created and
    # resolved (not rejected) in each and a label every three weeks.
    trends = {trend['period']: trend for trend in board['trends']}
    assert list(trends) == list(TREND_PERIODS) and board['trend_period'] == 'week'
    weeks = trends['week']['periods']
    assert len(weeks) == 12 and weeks[0]['start'] == date(2026, 8, 3) and weeks[-1]['start'] == today
    assert [(week['created'], week['resolved']) for week in weeks[-3:]] == [(2, 0), (1, 1), (1, 0)]
    assert (trends['week']['created'], trends['week']['resolved'], trends['week']['peak']) == (4, 2, 2)
    assert [index for index, week in enumerate(weeks) if week['axis']] == [2, 5, 8, 11]
    assert (weeks[-1]['label'], weeks[-1]['name'], trends['week']['title'], trends['week']['note']) == (
        '19 Oct', 'Week of 19 Oct', 'Created vs resolved per week', 'Last 12 weeks')
    # The last 30 days, 12 months, 8 quarters and 5 years, each the current one last.
    days, months, quarters, years = (trends[period]['periods'] for period in ('day', 'month', 'quarter', 'year'))
    assert (len(days), days[0]['start'], days[-1]['start'], days[-1]['name']) == (30, date(2026, 9, 20), today, 'Mon 19 Oct')
    assert (trends['day']['created'], trends['day']['resolved'], trends['day']['peak']) == (4, 1, 2)
    assert (len(months), months[0]['label'], months[-1]['name']) == (12, 'Nov 2025', 'October 2026')
    assert [(month['created'], month['resolved']) for month in months[-3:]] == [(1, 0), (0, 1), (4, 1)]
    assert (len(quarters), quarters[0]['label'], [(quarter['created'], quarter['resolved']) for quarter in quarters[-2:]]) == (
        8, 'Q1 2025', [(2, 1), (4, 1)])
    assert [(year['label'], year['created'], year['resolved']) for year in years] == [
        ('2022', 0, 0), ('2023', 0, 0), ('2024', 0, 0), ('2025', 0, 0), ('2026', 6, 2)]
    assert (trends['year']['title'], trends['year']['note']) == ('Created vs resolved per year', 'Last 5 years')
    assert board['oldest_open'] == {'id': 1, 'title': 'T1', 'ticket_type': 'bug', 'days': 79, 'created_date': '2026-08-01'}
    assert ticket_dashboard([], today=today)['oldest_open'] is None


def test_the_dashboard_shows_the_tickets_to_attend_and_the_latest_activity():
    from datetime import date, datetime, timedelta, timezone

    from src.modules.ticket_center import ticket_attention, ticket_feed

    def ticket(number, status, priority='P3', created='2026-10-05T09:00', resolved='', assigned='', fixed=''):
        return {'id': number, 'title': f'T{number}', 'ticket_type': 'bug', 'status': status, 'priority': priority, 'module': '',
                'module_title': 'General', 'module_color': '#123456', 'created_by': 'ANA', 'created_by_name': 'User A',
                'assigned_to': assigned, 'assigned_to_name': 'User E' if assigned else '', 'fixed_version': fixed,
                'created_at': f'{created}:00+01:00', 'resolved_at': f'{resolved}:00+01:00' if resolved else ''}

    today = date(2026, 10, 19)
    now = datetime(2026, 10, 19, 12, 0, tzinfo=timezone(timedelta(hours=1)))
    tickets = [
        ticket(1, 'new', 'P2', created='2026-08-01T09:00'),
        ticket(2, 'in_progress', 'P1', assigned='EJ'),
        ticket(3, 'resolved', created='2026-10-12T09:00', resolved='2026-10-14T10:00', fixed='v0.10.0'),
        ticket(4, 'waiting_info', 'P1', created='2026-10-19T09:00'),
        ticket(5, 'closed', created='2026-07-01T09:00', resolved='2026-09-01T10:00'),
    ]
    # The most urgent priority first, then the oldest; the age of each (fresh, aging, old) against the oldest shown.
    attention = ticket_attention(tickets, today, limit=2, now=now)
    assert [(row['id'], row['age'], row['tone'], row['share'], row['assignee']) for row in attention['rows']] == [
        (2, '14 days', 'aging', 100.0, 'User E'), (4, 'Today', 'fresh', 4, '')]
    assert (attention['open'], attention['more'], attention['unassigned']) == (3, 1, 2)
    assert [(item['id'], item['fixed_version'], item['took'], item['ago']) for item in attention['resolved']] == [
        (3, '0.10.0', '2.0 days', '5 days ago'), (5, '', '62 days', '1 Sep')]
    # The newest entries: a change of status says the new one, another change the fields it changed.
    events = [
        {'ticket_id': 3, 'username': 'EJ', 'kind': 'change', 'changes_json': '{"status": ["new", "resolved"]}', 'created_at': '2026-10-14T10:00:00+01:00'},
        {'ticket_id': 3, 'username': 'BOB', 'kind': 'comment', 'changes_json': '', 'created_at': '2026-10-14T09:59:00+01:00'},
        {'ticket_id': 4, 'username': 'EJ', 'kind': 'change', 'changes_json': '{"priority": ["P3", "P1"], "assigned_to": ["", "EJ"]}',
         'created_at': '2026-10-19T11:30:00+01:00'},
        {'ticket_id': 99, 'username': 'EJ', 'kind': 'comment', 'changes_json': '', 'created_at': '2026-10-19T11:59:00+01:00'},
    ]
    feed = ticket_feed(tickets, events, names={'EJ': 'User E', 'BOB': 'User B'}, now=now, limit=4)
    assert [(entry['kind'], entry['who'], entry['verb'], entry['ticket_id'], entry['status'], entry['fields'], entry['ago']) for entry in feed] == [
        ('change', 'User E', 'updated', 4, '', 'Priority, Assigned to', '30 min ago'),
        ('opened', 'User A', 'opened', 4, '', '', '3 h ago'),
        ('status', 'User E', 'moved to', 3, 'resolved', '', '5 days ago'),
        ('comment', 'User B', 'commented', 3, '', '', '5 days ago'),
    ]
    assert feed[2]['status_label'] == 'Resolved' and feed[0]['when'] == '2026-10-19 11:30'


def test_the_statistics_measure_resolution_mix_backlog_versions_people_and_activity():
    from datetime import date

    from src.modules.ticket_center import ACTIVITY_WEEKS, DURATION_BUCKETS, STATISTICS_VERSIONS, ticket_statistics

    def ticket(number, ticket_type, status, priority='P3', created='2026-10-05T09:00', resolved='', created_by='ANA', assigned='',
               fixed='', version='0.9.0', module=''):
        return {'id': number, 'title': f'T{number}', 'ticket_type': ticket_type, 'status': status, 'priority': priority, 'module': module,
                'module_title': module.title() or 'General', 'module_color': '#123456', 'created_by': created_by,
                'created_by_name': created_by.title(), 'assigned_to': assigned, 'assigned_to_name': assigned.title(),
                'fixed_version': fixed, 'app_version': version, 'comment_count': 2, 'attachment_count': number % 2,
                'created_at': f'{created}:00+01:00', 'resolved_at': f'{resolved}:00+01:00' if resolved else ''}

    today = date(2026, 10, 19)  # A Monday.
    tickets = [
        ticket(1, 'bug', 'new', 'P1', created='2026-08-01T09:00', module='scoring'),
        ticket(2, 'bug', 'in_progress', 'P1', created_by='BOB', assigned='EJ', module='scoring'),
        ticket(3, 'bug', 'resolved', created='2026-10-12T09:00', resolved='2026-10-12T15:00', assigned='EJ', fixed='0.10.0'),
        ticket(4, 'improvement', 'resolved', created='2026-10-01T09:00', resolved='2026-10-11T09:00', fixed='v0.9.1'),
        ticket(5, 'improvement', 'closed', created='2026-08-20T09:00', resolved='2026-09-01T09:00', fixed='0.9.1'),
        ticket(6, 'new_feature', 'rejected', resolved='2026-10-06T09:00', assigned='EJ'),
        ticket(7, 'new_feature', 'resolved', created='2026-10-15T09:00', resolved='2026-10-17T09:00'),
    ]
    events = [{'kind': 'comment', 'created_at': '2026-10-12T10:00:00+01:00'}, {'kind': 'change', 'created_at': '2026-10-12T15:00:00+01:00'},
              {'kind': 'comment', 'created_at': '2026-01-01T10:00:00+01:00'}]
    stats = ticket_statistics(tickets, events, today=today)
    # Resolved or closed of every ticket; the median time of those resolved in the last 30 days (6 h, 2 and 10 days)
    # against the 30 days before (12 days); the tickets opened in each window; comments and screenshots per ticket.
    assert stats['health'] == {
        'total': 7, 'done': 4, 'rate': 57, 'resolve_time': '2.0 days', 'resolve_count': 3, 'resolve_previous': '12 days',
        'resolve_change': -83, 'created': 5, 'created_change': 5, 'window': 30, 'comments': 2.0, 'screenshots': 0.6,
    }
    # Donuts of every ticket, each part listing its tickets as the chips name them.
    mix = {donut['key']: donut for donut in stats['mix']}
    assert [(part['key'], part['count'], part['percent']) for part in mix['type']['segments']] == [('bug', 3, 43), ('improvement', 2, 29), ('new_feature', 2, 29)]
    assert mix['type']['segments'][1]['start'] == round(300 / 7, 3) and mix['type']['segments'][0]['show'] == {'types': ['bug'], 'statuses': []}
    assert [part['key'] for part in mix['status']['segments']] == ['new', 'in_progress', 'rejected', 'closed', 'resolved']
    assert mix['priority']['segments'][0]['show'] == {'priorities': ['P1'], 'statuses': []} and mix['priority']['total'] == 7
    # Time to resolve by groups of days (the rejected ticket left out) and the age of the open ones.
    resolved = stats['durations']['resolved']
    assert [bucket['total'] for bucket in resolved['buckets']] == [1, 1, 0, 2, 0, 0, 0] and len(resolved['buckets']) == len(DURATION_BUCKETS)
    assert (resolved['median'], resolved['average'], resolved['p90'], resolved['count']) == ('6.0 days', '6.1 days', '12 days', 4)
    assert [(item['type'], item['median']) for item in resolved['by_type']] == [('bug', '6 h'), ('improvement', '11 days'), ('new_feature', '2.0 days')]
    assert [(item['priority'], item['count']) for item in resolved['by_priority']] == [('P3', 4)]
    # That time added up: in all, on average and the longest; by module and assignee (the most first), type and priority.
    spent = stats['time_spent']
    assert (spent['total'], spent['count'], spent['average'], spent['longest']) == ('24 days', 4, '6.1 days', {'id': 5, 'title': 'T5', 'took': '12 days'})
    groups = {group['key']: group['rows'] for group in spent['groups']}
    assert [(row['key'], row['total'], row['count'], row['share']) for row in groups['module']] == [('', '24 days', 4, 100.0)]
    assert [(row['key'], row['total'], row['average']) for row in groups['type']] == [
        ('bug', '6 h', '6 h'), ('improvement', '22 days', '11 days'), ('new_feature', '2.0 days', '2.0 days')]
    assert [row['key'] for row in groups['priority']] == ['P3'] and groups['type'][0]['show'] == {'types': ['bug'], 'statuses': ['closed', 'resolved']}
    assert [(row['key'], row['label'], row['count']) for row in groups['assignee']] == [('', 'Unassigned', 3), ('ej', 'Ej', 1)]
    opened = stats['durations']['open']
    assert ([bucket['total'] for bucket in opened['buckets']], opened['median'], opened['p90']) == ([0, 0, 0, 0, 1, 1, 0], '46 days', '79 days')
    # Backlog: created, resolved (not rejected) and open by the end of each week, today last.
    week = next(backlog for backlog in stats['backlogs'] if backlog['period'] == 'week')
    assert [(entry['created'], entry['resolved'], entry['open']) for entry in week['periods'][-3:]] == [(5, 2, 2), (7, 4, 2), (7, 4, 2)]
    assert (week['created'], week['resolved'], week['open'], week['peak'], week['width']) == (7, 4, 2, 7, 120)
    assert week['lines']['created'].endswith('115,6.0') and week['areas']['resolved'].startswith('M5,100 L5,100.0')
    # Fixed in and opened with each version, by version number (v0.9.1 and 0.9.1 are the same).
    assert [(row['label'], row['total']) for row in stats['versions']['fixed']['rows']] == [('v0.9.1', 2), ('v0.10.0', 1)]
    assert (stats['versions']['unversioned'], STATISTICS_VERSIONS) == (1, 10)
    # With the versions of the tool, the latest ten, also those without tickets.
    releases = [f'0.{minor}.{patch}' for minor in (8, 9, 10) for patch in range(5)]
    fixed = ticket_statistics(tickets, events, today=today, versions=releases)['versions']['fixed']
    assert [row['label'] for row in fixed['rows']] == ['v0.9.0', 'v0.9.1', 'v0.9.2', 'v0.9.3', 'v0.9.4', 'v0.10.0', 'v0.10.1', 'v0.10.2',
                                                       'v0.10.3', 'v0.10.4']
    assert [row['total'] for row in fixed['rows']][:2] == [0, 2] and fixed['rows'][0]['segments'] == [] and fixed['earlier'] == 0
    # People and modules, the most tickets first; the assignees by open, resolved and rejected tickets.
    reporters = stats['people']['reporters']
    assert [(row['username'], row['name'], row['total'], row['open']) for row in reporters] == [('ana', 'Ana', 6, 1), ('bob', 'Bob', 1, 1)]
    assert [(part['type'], part['share']) for part in reporters[1]['segments']] == [('bug', round(100 / 6, 2))]
    assignee = stats['people']['assignees'][0]
    assert (assignee['username'], assignee['groups']) == ('ej', {'open': 1, 'resolved': 1, 'rejected': 1})
    assert stats['people']['unassigned_open'] == 1
    assert [(row['key'], row['total'], row['open']) for row in stats['modules']] == [('', 5, 0), ('scoring', 2, 2)]
    # Activity of each day of the last 26 weeks, from Monday; the comment of January is older.
    activity = stats['activity']
    assert len(activity['weeks']) == ACTIVITY_WEEKS and activity['weeks'][-1]['days'][0]['day'] == '2026-10-19'
    assert activity['weeks'][-1]['days'][1]['future'] and not activity['weeks'][-1]['days'][0]['future']
    assert (activity['opened'], activity['comments'], activity['changes'], activity['resolved']) == (7, 1, 1, 4)
    monday = activity['weeks'][-2]['days'][0]
    assert (monday['day'], monday['total'], monday['level']) == ('2026-10-12', 3, 4)
    assert monday['tip'] == 'Mon 12 Oct 2026: 1 opened, 1 comment, 1 change, 1 resolved'
    assert activity['busiest']['total'] == 3
    empty = ticket_statistics([], today=today)
    assert (empty['health']['rate'], empty['mix'][0]['segments'], empty['activity']['busiest']) == (0, [], None)


def test_the_type_travels_with_the_tickets(client):
    login(client)
    open_ticket(client, title='Dark theme', ticket_type='new_feature', screenshots=())
    from src.modules.ticket_center import EXPORT_FORMAT, delete_ticket, list_tickets, merge_ticket_center, ticket_center_payload
    payload, files = ticket_center_payload(core.repository)
    assert payload['format'] == EXPORT_FORMAT == 'drivetest-analyzer-ticket-center' and payload['tickets'][0]['ticket_type'] == 'new_feature'
    delete_ticket(core.repository, int(list_tickets(core.repository)[0]['id']))
    # A ticket without a valid type is a bug.
    untyped = {**payload, 'tickets': [{key: value for key, value in payload['tickets'][0].items() if key != 'ticket_type'}
                                      | {'uid': 'untyped', 'title': 'Untyped'}]}
    merge_ticket_center(core.repository, payload, files)
    merge_ticket_center(core.repository, untyped, {})
    assert sorted((ticket['title'], ticket['ticket_type']) for ticket in list_tickets(core.repository)) == [('Dark theme', 'new_feature'), ('Untyped', 'bug')]


def test_the_bugs_report_tables_settings_and_events_take_the_ticket_center_names(client):
    """Ticket Center was Bugs Report: an application database and App Events of before are renamed in place."""
    from src.modules.module_labels import MODULE_LABELS_STATE_KEY, load_module_labels
    from src.modules.ticket_center import get_ticket, list_tickets

    login(client)
    ticket_id = open_ticket(client)
    client.post(f'/api/tickets/{ticket_id}/comments', data={'body': 'Seen'})
    nq = next(profile for profile in core.repository.list_modules_profiles() if profile['name'] == 'Non-Qualified Calls')
    with core.repository.global_connection() as conn:
        # The names of before: tables, columns, the module key and the kind of the notices told.
        conn.execute('ALTER TABLE tickets RENAME TO bug_reports')
        conn.execute('ALTER TABLE ticket_comments RENAME TO bug_report_comments')
        conn.execute('ALTER TABLE ticket_attachments RENAME TO bug_report_attachments')
        conn.execute('ALTER TABLE bug_report_comments RENAME COLUMN ticket_id TO bug_id')
        conn.execute('ALTER TABLE bug_report_attachments RENAME COLUMN ticket_id TO bug_id')
        conn.execute("UPDATE modules_profiles SET modules_json = ? WHERE id = ?", (json.dumps(['workspace', 'bugs-report']), nq['id']))
        conn.execute("UPDATE application_state SET value = replace(value, '\"ticket-center\"', '\"bugs-report\"') "
                     "WHERE key = 'modules_profiles_added_modules'")
        conn.execute("INSERT INTO admin_notices_seen (user_id, kind, item_key, seen_at) VALUES (1, 'bug_report', 'x', '2026-10-01')")
    core.repository.set_application_state(MODULE_LABELS_STATE_KEY, json.dumps({
        'bugs-report': {'title': 'Tickets & Bugs', 'tab_icon': 'bugs-report', 'tab_color': '#123456'}}))
    with core.repository.connection() as conn:
        conn.execute("INSERT INTO audit_logs (username, action, details, created_at, origin) VALUES "
                     "('super', 'bug_report_managed', '{\"bug_id\": 1}', '2026-10-01', 'module:bugs-report'), "
                     "('ana', 'bug_report_created', '{\"bug_id\": 2}', '2026-10-01', 'public:bug-report')")
    core.repository.initialize()
    core.invalidate_module_access_cache()

    assert [(ticket['title'], ticket['comment_count'], ticket['attachment_count']) for ticket in list_tickets(core.repository)] == [
        ('Export fails', 1, 1)]
    assert [entry['body'] for entry in get_ticket(core.repository, ticket_id)['comments']] == ['Seen']
    with core.repository.global_connection() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert not tables & {'bug_reports', 'bug_report_comments', 'bug_report_attachments'}
        assert conn.execute("SELECT kind FROM admin_notices_seen WHERE item_key = 'x'").fetchone()[0] == 'ticket'
    profiles = {profile['name']: profile['modules'] for profile in core.repository.list_modules_profiles()}
    # The module stays where it was, and is not added again to a profile it was taken out of.
    assert profiles['Non-Qualified Calls'] == ['workspace', 'ticket-center']
    label = load_module_labels(core.repository)['ticket-center']
    assert (label['title'], label['tab_icon'], label['tab_color']) == ('Tickets & Bugs', 'ticket-center', '#123456')
    events = [(row['action'], row['details'], row['origin']) for row in core.repository.list_logs() if row['created_at'] == '2026-10-01']
    assert sorted(events) == [('ticket_created', '{"ticket_id": 2}', 'public:ticket-center'),
                              ('ticket_managed', '{"ticket_id": 1}', 'module:ticket-center')]


def test_a_stored_bugs_report_title_becomes_ticket_center_once(client):
    from src.modules.module_labels import (
        MODULE_LABELS_STATE_KEY, TICKET_CENTER_TITLE_MIGRATION_KEY, load_module_labels, migrate_ticket_center_title,
    )

    core.repository.set_application_state(TICKET_CENTER_TITLE_MIGRATION_KEY, '')
    profile = next(item for item in core.repository.list_modules_profiles() if item['name'] == 'Non-Qualified Calls')
    core.repository.save_modules_profile(profile['id'], profile['name'], 'Workspace, Non-Qualified Calls, Reporting, Builders & Bugs Report.',
                                         profile['modules'])
    core.repository.set_application_state(MODULE_LABELS_STATE_KEY, json.dumps({
        'ticket-center': {'title': 'Bugs Report', 'short_title': 'Bugs', 'tab_icon': 'bug', 'tab_color': '#123456'}}))
    assert migrate_ticket_center_title(core.repository) is True
    label = load_module_labels(core.repository)['ticket-center']
    assert (label['title'], label['short_title'], label['tab_icon'], label['tab_color']) == ('Ticket Center', 'Tickets', 'bug', '#123456')
    profile = next(item for item in core.repository.list_modules_profiles() if item['name'] == 'Non-Qualified Calls')
    assert profile['description'] == 'Workspace, Non-Qualified Calls, Reporting, Builders & Ticket Center.'
    # A name chosen afterwards stays, and the page and its notices take it.
    core.repository.set_application_state(MODULE_LABELS_STATE_KEY, json.dumps({'ticket-center': {'title': 'Bugs Report'}}))
    assert migrate_ticket_center_title(core.repository) is False
    login(client)
    assert 'Bugs Report · Version' in client.get('/tickets').text
    assert client.get('/api/admin-notices').json()['ticket_center_title'] == 'Bugs Report'
