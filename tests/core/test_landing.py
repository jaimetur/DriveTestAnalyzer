"""The public landing page: served at the root to visitors, /landing redirects to it, signed-in users open the
application, and its What's new comes from the Changelog."""
import src.DriveTestAnalyzer as core
from src.modules.core import landing


def test_visitors_see_the_landing_page_at_the_root(client):
    client.cookies.clear()
    page = client.get('/', follow_redirects=False)
    assert page.status_code == 200
    assert 'From drive test CDRs' in page.text and 'href="/login"' in page.text
    # Every module, its presentation and its Help chapter.
    for module in landing.MODULES:
        assert f'id="m-{module["key"]}"' in page.text
        assert f'href="/presentations/{module["presentation"]}?back=%2F"' in page.text
        assert f'href="/documents/view/help/{module["chapter"]}?guide=1&amp;back=%2F"' in page.text
    # The latest release of the Changelog.
    assert f'v{core.__version__}' in page.text


def test_the_old_landing_address_redirects_to_the_root(client):
    for path in ('/landing', '/landing/'):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 301 and response.headers['location'] == '/'


def test_signed_in_users_open_the_application_or_the_landing_page_when_asked(client):
    core.repository.create_user('EUSER01', 'Secret123', 'user-editor')
    client.cookies.clear()
    assert client.post('/login', data={'username': 'EUSER01', 'password': 'Secret123'},
                       follow_redirects=False).status_code in {302, 303}
    response = client.get('/', follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/documents/view/help'
    page = client.get('/?landing', follow_redirects=False)
    assert page.status_code == 200 and 'Open the app' in page.text


def test_the_help_chapters_of_the_landing_page_exist():
    from pathlib import Path
    help_dir = Path(__file__).resolve().parents[2] / 'help'
    for chapter in [module['chapter'] for module in landing.MODULES] + [topic['chapter'] for topic in landing.HELP_TOPICS]:
        assert (help_dir / chapter).is_file(), chapter


def test_whats_new_takes_the_headlines_of_the_latest_releases():
    changelog = '''# CHANGELOG

## Release: v2.0.0
### Release Date: 2026-12-01
#### ⚠️ Breaking Changes:

#### 🌟 New Features:
- **Scoring & GAP Analysis — NNS Break-down:** an optional part of the scoring ([ticket #1](https://example/1)).

#### 🚀 Enhancements:
- **Reporting:** `faster` reports.

#### 🐛 Bug fixes:
- **Sign in — Links:** fixed.

## Release: v1.9.0
### Release Date: 2026-11-01
#### 🌟 New Features:
- **Builders — Charts:** new charts.

## Release: v1.8.0
### Release Date: 2026-10-01
#### 🌟 New Features:
- **Old:** left out.
'''
    news = landing.latest_news(changelog)
    assert [release['version'] for release in news] == ['2.0.0', '1.9.0']
    assert news[0]['date'] == '2026-12-01' and news[0]['anchor'] == 'release-v2.0.0'
    assert news[0]['items'] == [
        {'kind': 'New', 'module': 'Scoring & GAP Analysis', 'title': 'NNS Break-down',
         'summary': 'An optional part of the scoring (ticket #1).'},
        {'kind': 'Improved', 'module': '', 'title': 'Reporting', 'summary': 'Faster reports.'},
    ]
    assert len(landing.latest_news(changelog, limit=1)[0]['items']) == 1


def test_the_sign_in_page_and_the_help_lead_back_to_the_landing_page(client):
    client.cookies.clear()
    for path in ('/login', '/documents/view/help'):
        page = client.get(path).text
        assert 'class="topnav-link topnav-link-home" href="/"' in page, path
    assert 'topnav-link-signin' not in client.get('/login').text


def test_a_presentation_link_keeps_only_a_local_page_to_return_to(client):
    response = client.get('/presentations/overview?back=%2F', follow_redirects=False)
    assert response.status_code == 302 and response.headers['location'].endswith('presentation=overview&back=%2F')
    for outside in ('https://example.com/', '//example.com/'):
        response = client.get('/presentations/overview', params={'back': outside}, follow_redirects=False)
        assert 'back=' not in response.headers['location']
