import json
import subprocess
import time
from pathlib import Path

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import presentations
from src.modules.repository import local_now_iso


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def session(client, username, role):
    token = f'presentations-{username}-{role}'
    core.SESSIONS[token] = core.SessionUser(username=username, role=role)
    client.cookies.clear()
    client.cookies.set(core.SESSION_COOKIE, token)


def add_dataset(repository, name: str, kind: str, rows: int, campaign: str | None = None) -> int:
    source = Path(repository.db_path).parent / name
    source.write_text('source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'tester')
    frame = pd.DataFrame({'Operator': ['EE'] * rows, 'Campaign': [campaign or ''] * rows, 'score': [1.0] * rows})
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA', row_count=rows,
                                      column_count=len(frame.columns), processed_at=local_now_iso())
    if campaign:
        repository.replace_cdr_catalogue(dataset_id, vendors=[], vendors_only=[], regions=[], cities=[], campaigns=[campaign])
    return dataset_id


def wait_until(condition, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError('The condition was not met in time.')


def test_figures_of_the_workspaces_are_read_and_added_up(client):
    login(client)
    repository = core.repository
    add_dataset(repository, 'data_q1.csv', 'data', 30, 'UK_Q1_2026')
    add_dataset(repository, 'voice_q1.csv', 'voice', 20, 'UK_Q1_2026')
    add_dataset(repository, 'speech_q2.csv', 'speech', 10, 'UK_Q2_2026')
    add_dataset(repository, 'inventory.csv', 'network_inventory', 7)
    add_dataset(repository, 'vodafone.csv', 'mapping_vodafone', 5)
    figures = presentations.workspace_figures(core.active_workspace.database_path)
    assert (figures['cdrs'], figures['cdr_rows'], figures['inventory_rows'], figures['mapping_rows']) == (3, 60, 7, 5)
    # The calls are those of the Data and Voice CDRs, not of the Speech one.
    assert figures['cdr_calls'] == 50
    assert figures['campaigns'] == ['UK_Q1_2026', 'UK_Q2_2026']
    # With no workspace chosen, the figures are those of the workspace with the most CDR rows.
    totals = presentations.presentation_figures(core)
    assert totals['workspaces'] == [core.active_workspace.name]
    assert (totals['cdrs'], totals['cdr_calls'], totals['campaigns']) == (3, 50, 2)
    assert totals['users'] >= 1 and totals['roles'].get('super-admin', 0) >= 1
    assert totals['help_chapters'] > 20 and totals['releases'] > 1 and totals['tests'] > 100
    # A change of a figure gives another key, which generates them again.
    assert presentations.figures_key(totals) != presentations.figures_key({**totals, 'cdrs': 4})


def test_super_admin_chooses_the_workspaces_and_the_help_shows_the_generated_presentations(client, monkeypatch):
    login(client)
    workspace = core.active_workspace
    generated = []

    def fake_generate(self, figures, key, requested_by, reason=''):
        # What a generation leaves: the manifest of the presentations and their files, in current.
        current = self.root / 'current'
        current.mkdir(parents=True, exist_ok=True)
        (current / 'overview.pptx').write_bytes(b'deck')
        (current / presentations.MANIFEST).write_text(json.dumps({
            'presentations': [{'id': 'overview', 'title': 'Overview', 'file': 'overview.pptx', 'sections': []}],
            'key': key, 'figures': figures, 'generated_at': '2026-10-21T09:00:00+02:00'}), encoding='utf-8')
        generated.append((figures['workspaces'], requested_by, reason))
        with self.lock:
            self.running = False

    monkeypatch.setattr(presentations.PresentationGenerator, 'unavailable', staticmethod(lambda: ''))
    monkeypatch.setattr(presentations.PresentationGenerator, '_generate', fake_generate)
    # Only super-admins choose the workspaces, in Super Admin (not in Application Config).
    assert 'id="presentations"' in client.get('/super-admin').text
    assert 'id="presentations"' not in client.get('/application-config').text
    response = client.post('/super-admin/presentations', data={'workspace_ids': [workspace.id, 'missing']}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/super-admin#presentations'
    assert presentations.chosen_workspace_ids(core.repository) == [workspace.id]
    wait_until(lambda: generated)
    assert generated[0][:2] == ([workspace.name], 'super')
    log = next(row for row in core.repository.list_logs(limit=50) if row['action'] == 'save_presentation_figures')
    assert json.loads(log['details'])['workspaces'] == [workspace.name]
    # The Help shows the generated presentations, and their files come from them.
    manifest = client.get('/api/presentations').json()
    assert manifest['base'] == '/presentations/files' and manifest['generated_at'] and not manifest['updating']
    assert client.get('/presentations/files/overview.pptx').content == b'deck'
    # Unchanged figures do not generate them again; nothing outside the presentations is served.
    client.get('/api/presentations')
    assert len(generated) == 1
    assert client.get('/presentations/files/..%2F..%2Fpresentations.py').status_code == 404
    # Regenerate Presentations draws them again on demand, whatever changed, and App Events records it.
    page = client.get('/super-admin').text
    assert 'formaction="/super-admin/presentations/regenerate"' in page and 'Regenerate Presentations' in page
    response = client.post('/super-admin/presentations/regenerate', follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/super-admin#presentations'
    wait_until(lambda: len(generated) == 2)
    assert generated[1] == ([workspace.name], 'super', 'regenerated on demand')
    log = next(row for row in core.repository.list_logs(limit=50) if row['action'] == 'regenerate_presentations')
    assert json.loads(log['details'])['started'] is True
    assert client.get('/api/presentations/status').json()['generated_at']
    session(client, 'editor', 'user-editor')
    assert client.post('/super-admin/presentations', data={'workspace_ids': [workspace.id]}).status_code == 403
    assert client.post('/super-admin/presentations/regenerate').status_code == 403


def test_no_presentation_is_kept_with_the_application_and_the_help_says_why_until_they_are_generated(client, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    assert not (root / 'src/web_interface/static/presentations').exists()
    assert not list((root / 'tools/presentations/dt-analyzer-rca').glob('slide-*.png'))
    monkeypatch.setattr(presentations.PresentationGenerator, 'unavailable', staticmethod(lambda: 'Node.js is not installed on this server.'))
    login(client)
    manifest = client.get('/api/presentations').json()
    assert manifest.get('presentations', []) == [] and not manifest['updating']
    assert manifest['unavailable'] == 'Node.js is not installed on this server.'
    assert client.get('/presentations/files/roadmap/slide-01.png').status_code == 404
    # Super Admin tells why they are not generated, and cannot regenerate them.
    page = client.get('/super-admin').text
    assert 'Node.js is not installed on this server. The Help cannot show the presentations until they are generated.' in page
    assert 'Not generated yet' in page
    # A visitor who has not signed in sees the same without starting a generation.
    client.cookies.clear()
    assert client.get('/api/presentations').status_code == 200
    script = (root / 'src/web_interface/static/js/presentation_viewer.js').read_text(encoding='utf-8')
    assert 'The presentations cannot be generated on this server: ${data.unavailable}' in script


def test_the_server_generates_them_in_the_background_at_startup_when_one_is_missing(client, monkeypatch):
    calls = []
    generator = presentations._GENERATOR
    monkeypatch.setattr(presentations, 'GENERATE_AT_STARTUP', True)
    monkeypatch.setattr(presentations.PresentationGenerator, 'unavailable', staticmethod(lambda: ''))
    monkeypatch.setattr(presentations, 'expected_ids', lambda: ['overview', 'workspace', 'full-presentation'])
    monkeypatch.setattr(presentations.PresentationGenerator, 'ensure', lambda self, figures, requested_by='system', **options: calls.append(options) or True)
    # None generated yet: all of them, in the background, without the startup waiting for them.
    assert generator.missing() == ['overview', 'workspace', 'full-presentation']
    presentations.generate_at_startup(core).join(timeout=20)
    assert calls[-1] == {'force': True, 'reason': 'missing at startup: overview, workspace, full-presentation'}
    # One missing (or without the pictures of its slides): generated again at startup too.
    current = generator.root / 'current'
    (current / 'overview').mkdir(parents=True)
    (current / 'overview' / 'slide-01.png').write_bytes(b'png')
    for name in ('overview.pptx', 'workspace.pptx', 'full-presentation.pptx'):
        (current / name).write_bytes(b'deck')
    (current / presentations.MANIFEST).write_text(json.dumps({'presentations': [
        {'id': 'overview', 'file': 'overview.pptx', 'sections': [{'title': 'Introduction', 'slides': ['Cover']}]},
        {'id': 'workspace', 'file': 'workspace.pptx', 'sections': [{'title': 'Introduction', 'slides': ['Cover']}]},
        {'id': 'full-presentation', 'file': 'full-presentation.pptx', 'sections': [{'title': 'Overview', 'presentation': 'overview', 'slides': ['Cover']}]},
    ]}), encoding='utf-8')
    assert generator.missing() == ['workspace']
    # Every one there: only when their figures or generator changed.
    (current / 'workspace').mkdir()
    (current / 'workspace' / 'slide-01.png').write_bytes(b'png')
    assert generator.missing() == []
    presentations.generate_at_startup(core).join(timeout=20)
    assert calls[-1] == {}
    # Where they cannot be generated, App Events says why.
    monkeypatch.setattr(presentations.PresentationGenerator, 'unavailable', staticmethod(lambda: 'Node.js is not installed on this server.'))
    presentations.generate_at_startup(core).join(timeout=20)
    log = next(row for row in core.repository.list_logs(limit=50) if row['action'] == 'generate_presentations_failed')
    assert json.loads(log['details'])['error'] == 'Node.js is not installed on this server.'


def test_a_change_of_a_deck_or_of_the_logo_generates_them_again(tmp_path, monkeypatch):
    generator = tmp_path / 'presentations'
    (generator / 'benchmarking-providers').mkdir(parents=True)
    (generator / 'reporting').mkdir()
    (generator / 'node_modules' / 'pptxgenjs').mkdir(parents=True)
    (generator / 'build.js').write_text('// generator', encoding='utf-8')
    (generator / 'benchmarking-providers' / 'slide-01.png').write_bytes(b'first')
    (generator / 'reporting' / 'content.js').write_text('module.exports = {};', encoding='utf-8')
    logo = tmp_path / 'logo.png'
    logo.write_bytes(b'logo')
    monkeypatch.setattr(presentations, 'GENERATOR', generator)
    monkeypatch.setattr(presentations, 'LOGO', logo)
    before = presentations.generator_signature()
    (generator / 'node_modules' / 'pptxgenjs' / 'index.js').write_text('// package', encoding='utf-8')
    assert presentations.generator_signature() == before
    for change in (lambda: (generator / 'benchmarking-providers' / 'slide-01.png').write_bytes(b'second'),
                   lambda: (generator / 'reporting' / 'content.js').write_text('module.exports = { slides: [] };', encoding='utf-8'),
                   lambda: logo.write_bytes(b'new logo')):
        change()
        assert presentations.generator_signature() != before
        before = presentations.generator_signature()


def test_a_generation_removes_what_one_stopped_by_a_restart_left(tmp_path, monkeypatch):
    root = tmp_path / 'presentations'
    for name in ('.building-stopped', '.previous-1'):
        (root / name / 'presentations').mkdir(parents=True)
    (root / 'current').mkdir()
    logged = []

    def stopped(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, 'node', stderr=b'stopped')

    monkeypatch.setattr(presentations.subprocess, 'run', stopped)
    monkeypatch.setattr(presentations, 'node_executable', lambda: 'node')
    generator = presentations.PresentationGenerator(lambda: tmp_path, lambda *args: logged.append(args))
    generator._generate({'workspaces': []}, 'key', 'system')
    assert sorted(path.name for path in root.iterdir()) == ['current']
    assert logged[-1][1] == 'generate_presentations_failed'


GENERATOR_FOLDER = Path(__file__).resolve().parents[1] / 'tools/presentations'


def node_json(script: str):
    return json.loads(subprocess.run(['node', '-e', script], cwd=GENERATOR_FOLDER, check=True, capture_output=True, text=True).stdout)


@pytest.mark.skipif(presentations.node_executable() is None or not (GENERATOR_FOLDER / 'node_modules' / 'pptxgenjs').is_dir(),
                    reason='Node.js and the packages of the generator are needed.')
def test_every_main_module_has_its_presentation_at_the_start_of_its_chapter():
    help_folder = Path(__file__).resolve().parents[1] / 'help'
    ids = presentations.expected_ids()
    assert ids == ['overview', 'one-slider', 'roadmap', 'benchmarking-providers', 'workspace', 'workspace-config', 'cdr-analysis', 'ppt-designer',
                   'scoring-gap-analysis', 'network-insights', 'non-qualified-calls', 'dt-analyzer-rca', 'reporting', 'builders',
                   'ticket-center', 'administration', 'full-presentation']
    chapters = {'workspace-management': 'workspace\nworkspace-config', 'workspace-config': 'workspace-config',
                'datasets-analysis': 'cdr-analysis', 'ppt-designer': 'ppt-designer',
                'scoring-gap-analysis': 'scoring-gap-analysis', 'network-insights': 'network-insights',
                'non-qualified-calls': 'non-qualified-calls\ndt-analyzer-rca', 'reporting': 'reporting', 'chart-builder': 'builders',
                'query-builder': 'builders', 'ticket-center': 'ticket-center', 'super-admin': 'administration',
                'administrator-config': 'administration'}
    for chapter, blocks in chapters.items():
        text = (help_folder / f'{chapter}.md').read_text(encoding='utf-8')
        block = text.find(f'```presentations\n{blocks}\n```')
        tasks = min(index for index in (text.find('\n## In this guide'), text.find('\n## Choose your task')) if index >= 0)
        assert 0 <= block < tasks, chapter
    # Every slide of a deck drawn from its content.js has its title, section (one after the other) and notes.
    decks = node_json("const { DECKS } = require('./module_decks.js'); console.log(JSON.stringify(DECKS.map((id) => [id, require(`./${id}/content.js`)])));")
    assert [deck_id for deck_id, _deck in decks] == [item for item in ids[4:-1] if item != 'dt-analyzer-rca']
    for deck_id, deck in decks:
        assert deck['name'] and deck['description'] and deck['slides'], deck_id
        assert all(slide['id'] and slide['title'] and slide['notes'] and slide['section'] for slide in deck['slides']), deck_id
        sections = [slide['section'] for slide in deck['slides']]
        assert len(list(dict.fromkeys(sections))) == len([1 for index, section in enumerate(sections) if index == 0 or sections[index - 1] != section]), deck_id
    # Those of PPT Designer and Non-Qualified Calls explain the PPT Templates, and the groups of NQ calls and the map of
    # the call, and that of Workspace Config what to set up in a new workspace.
    by_id = dict(decks)
    assert {'operators', 'vendors-campaigns', 'places'} <= {slide['id'] for slide in by_id['workspace-config']['slides']}
    assert {'templates'} <= {slide['id'] for slide in by_id['ppt-designer']['slides']}
    assert {'groups', 'map', 'map-findings'} <= {slide['id'] for slide in by_id['non-qualified-calls']['slides']}
    # The DT Analyzer RCA keeps its slides.html, and the benchmarking providers deck its pictures.
    for name, count in (('dt-analyzer-rca', 12), ('benchmarking-providers', 24)):
        slides = json.loads((GENERATOR_FOLDER / name / 'slides.json').read_text(encoding='utf-8'))['slides']
        assert len(slides) == count and all(slide['title'] and slide['notes'] for slide in slides), name
    assert (GENERATOR_FOLDER / 'dt-analyzer-rca' / 'slides.html').is_file()
    assert all((GENERATOR_FOLDER / 'benchmarking-providers' / slide['image']).is_file()
               for slide in json.loads((GENERATOR_FOLDER / 'benchmarking-providers' / 'slides.json').read_text(encoding='utf-8'))['slides'])
    # Help Home and Product Presentations show every presentation: those of the tool (the Benchmarking Providers Roadmap
    # after the Overview), then those of the modules (Network Insights after CDR Analysis) and the full presentation, each
    # in their own section; Product Overview points to Product Presentations.
    general = ['overview', 'benchmarking-providers', 'one-slider', 'roadmap']
    modules_order = ['workspace', 'workspace-config', 'cdr-analysis', 'network-insights', 'ppt-designer', 'scoring-gap-analysis',
                     'non-qualified-calls', 'dt-analyzer-rca', 'reporting', 'builders', 'ticket-center', 'administration']
    assert sorted(general + modules_order + ['full-presentation']) == sorted(ids)
    for chapter, level in (('help', '###'), ('presentations', '##')):
        text = (help_folder / f'{chapter}.md').read_text(encoding='utf-8')
        tool, modules = text.find('```presentations\n' + '\n'.join(general) + '\n```'), text.find(f'\n{level} Module presentations\n')
        full = text.find(f'\n{level} Full presentation\n')
        assert 0 <= tool < modules < full, chapter
        assert '```presentations\n' + '\n'.join(modules_order) + '\n```' in text[modules:full], chapter
        assert '```presentations\nfull-presentation\n```' in text[full:], chapter
    overview = (help_folder / 'overview.md').read_text(encoding='utf-8')
    assert '```presentations' not in overview and '[Product Presentations](presentations.md)' in overview


@pytest.mark.skipif(bool(presentations.PresentationGenerator.unavailable()), reason='Node.js, its packages, Chromium and LibreOffice are needed.')
def test_the_server_generates_every_presentation_with_the_pictures_of_their_slides(tmp_path, monkeypatch):
    from PIL import Image
    from src.modules import pptx_to_docx

    logs, rendered = [], []
    document_pdf = pptx_to_docx.document_pdf
    monkeypatch.setattr(pptx_to_docx, 'document_pdf', lambda content, *args, **kwargs: rendered.append(len(content)) or document_pdf(content, *args, **kwargs))
    generator = presentations.PresentationGenerator(lambda: tmp_path, lambda *event: logs.append(event))
    figures = {**presentations.product_figures(), 'workspaces': ['UK'], 'month': 'October 2026'}
    assert generator.missing() == presentations.expected_ids()
    assert generator.ensure(figures, 'tester', reason='test', wait=True), generator.error
    assert generator.error == '' and logs[-1][1] == 'generate_presentations' and json.loads(logs[-1][2])['reason'] == 'test'
    manifest = generator.manifest()
    current = generator.current()
    assert [item['id'] for item in manifest['presentations']] == presentations.expected_ids() and generator.missing() == []
    by_id = {item['id']: item for item in manifest['presentations']}
    for item in manifest['presentations']:
        assert (current / item['file']).is_file(), item['id']
        if item['id'] != 'full-presentation':
            count = sum(len(section['slides']) for section in item['sections'])
            assert len(list((current / item['id']).glob('slide-*.png'))) == len(list((current / item['id']).glob('thumb-*.png'))) == count, item['id']
    # LibreOffice renders only the decks of native slides: build.js writes the pictures of the others, as large.
    assert len(rendered) == 3 and [item['id'] for item in manifest['presentations'] if not item.get('drawn')] == ['overview', 'one-slider', 'roadmap', 'full-presentation']
    assert Image.open(current / 'workspace-config' / 'slide-01.png').size == (1920, 1080)
    assert Image.open(current / 'workspace-config' / 'thumb-01.png').size == (600, 338)
    # The decks drawn by module_decks.js have their slides by section, as in their content.js.
    assert [slide for section in by_id['dt-analyzer-rca']['sections'] for slide in section['slides']] == [
        slide['title'] for slide in json.loads((GENERATOR_FOLDER / 'dt-analyzer-rca' / 'slides.json').read_text(encoding='utf-8'))['slides']]
    # The full presentation joins the others, each a section titled after it with the slides it has, and is not
    # rendered: the slide viewer shows the pictures of the slides in the presentation of their section.
    full = by_id['full-presentation']
    assert [section['presentation'] for section in full['sections']] == [
        'overview', 'benchmarking-providers', 'workspace', 'workspace-config', 'cdr-analysis', 'network-insights', 'ppt-designer',
        'scoring-gap-analysis', 'non-qualified-calls', 'reporting', 'builders', 'ticket-center', 'administration', 'dt-analyzer-rca', 'roadmap']
    for section in full['sections']:
        part = by_id[section['presentation']]
        assert section['title'] == part['title'].removeprefix('DriveTest Analyzer — ')
        assert section['slides'] == [title for part_section in part['sections'] for title in part_section['slides']]
    assert not (current / 'full-presentation').exists()
    script = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/presentation_viewer.js').read_text(encoding='utf-8')
    assert 'source: section.presentation, position' in script and '[slide.source, slide.position]' in script


def test_the_slide_viewer_goes_through_the_slides_from_its_footer_the_wheel_and_the_arrows():
    root = Path(__file__).resolve().parents[1]
    script = (root / 'src/web_interface/static/js/presentation_viewer.js').read_text(encoding='utf-8')
    styles = (root / 'src/web_interface/static/css/presentation_viewer.css').read_text(encoding='utf-8')
    # Every control stands in the footer: the zoom buttons and Slideshow, then the previous and next slide (arrows in two
    # colours), then Close and Download PowerPoint.
    footer = script[script.index('<footer class="presentation-dialog-actions">'):script.index('</footer>')]
    assert footer.index('data-presentation-viewer="zoom-in"') < footer.index('data-presentation-show-open') < footer.index('presentation-step-previous')
    assert 'class="presentation-step presentation-step-previous" data-presentation-viewer="previous" title="Previous slide (← or ↑)" aria-label="Previous slide"><svg' in footer
    assert 'class="presentation-step presentation-step-next" data-presentation-viewer="next" title="Next slide (→ or ↓)" aria-label="Next slide"><svg' in footer
    assert '.presentation-show-settings { position: absolute; z-index: 5; bottom: calc(100% + .45rem);' in styles
    assert '.presentation-stage { grid-row: 2;' in styles
    assert '<span class="presentation-page-label" aria-live="polite">' in footer and 'data-presentation-close>Close</button>' in footer
    assert 'data-presentation-viewer="previous"' not in script[:script.index('<footer class="presentation-dialog-actions">')]
    assert '.presentation-step-previous { background: #5b6b80; }' in styles and '.presentation-step-next { background: #1f6fbf; }' in styles
    # The up and down arrows and the wheel change slide; Ctrl/Cmd+wheel zooms.
    assert "if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(event.key)) showSlide(viewerIndex - 1);" in script
    assert "else if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(event.key)) showSlide(viewerIndex + 1);" in script
    assert "if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(event.key)) moveShow(-1);" in script
    assert 'if (event.ctrlKey || event.metaKey) {' in script and 'showSlide(viewerIndex + Math.sign(wheelTravel));' in script
    # On a phone the viewer fits the screen the browser leaves visible, the arrows first; a swipe changes slide (also in the
    # slideshow), two fingers zoom and a double tap shows the whole slide.
    assert '.presentation-dialog { width: 100vw; height: 100vh; height: 100dvh; max-height: 100dvh; border-radius: 0; }' in styles
    assert '.presentation-steps { order: -1; flex: 1 0 100%; justify-content: space-between; }' in styles
    assert "if (!pan && Math.abs(dx) > 50 && Math.abs(dx) > 1.5 * Math.abs(dy)) showSlide(viewerIndex + (dx < 0 ? 1 : -1));" in script
    assert 'zoomView(distance / pinch.distance, (a.x + b.x) / 2, (a.y + b.y) / 2);' in script and 'moveShow(dx < 0 ? 1 : -1);' in script


def test_a_direct_link_opens_its_presentation_in_the_slide_viewer(client):
    root = Path(__file__).resolve().parents[1]
    script = (root / 'src/web_interface/static/js/presentation_viewer.js').read_text(encoding='utf-8')
    footer = script[script.index('<footer class="presentation-dialog-actions">'):script.index('</footer>')]
    # Copy link, on each card and beside Close in the viewer, copies the link of the presentation (of the slide shown).
    assert footer.index('data-presentation-link') < footer.index('data-presentation-close>Close</button>')
    assert "share.addEventListener('click', () => copyLink(share, shareOf(presentation)));" in script
    assert "share.addEventListener('click', () => copyLink(share, shareOf(current, viewerIndex)));" in script
    # It is the short link of the presentation, at the public address of the server when it has one.
    assert "`${linkBase || window.location.origin}/presentations/${encodeURIComponent(presentation.id)}${index > 0 ? `?slide=${index + 1}` : ''}`" in script
    assert "linkBase = data.link_base || '';" in script
    # The link is the page with the presentation and its slide, which the viewer opens once it is there, also where the
    # page is not a secure context; while it is open, the address of the page is that link.
    assert "url.searchParams.set('presentation', presentation.id);" in script and "url.searchParams.set('slide', String(index + 1));" in script
    assert script.count('openLinked(data);') == 2 and "if (!blocks.length && !linked().id) return;" in script
    assert "document.execCommand('copy')" in script and 'window.history.replaceState' in script
    # Whoever has not signed in opens it too.
    client.cookies.clear()
    assert client.get('/documents/view/help/help.md?presentation=workspace-config&slide=3').status_code == 200
    # The short link opens it in Product Presentations (no .md for an app to take as a domain).
    response = client.get('/presentations/workspace-config?slide=3', follow_redirects=False)
    assert response.status_code == 302 and response.headers['location'] == '/documents/view/help/presentations.md?presentation=workspace-config&slide=3'
    assert client.get('/presentations/workspace-config', follow_redirects=False).headers['location'].endswith('?presentation=workspace-config')
    assert client.get('/presentations', follow_redirects=False).headers['location'] == '/documents/view/help/presentations.md'
    assert client.get('/presentations/workspace-config?slide=3').status_code == 200
    assert client.get('/api/presentations').json()['link_base'] == ''
    for chapter in ('help', 'presentations'):
        assert '**Copy link**, on each card and beside **Close** in the viewer' in (root / 'help' / f'{chapter}.md').read_text(encoding='utf-8')


def test_the_link_of_a_presentation_shows_its_title_and_the_picture_of_its_slide_where_it_is_shared(client):
    from PIL import Image

    # What a generation leaves: the pictures of the slides of a deck and the full presentation that shows them.
    current = presentations._GENERATOR.root / 'current'
    (current / 'workspace').mkdir(parents=True)
    for number, colour in ((1, 'navy'), (2, 'teal'), (3, 'orange')):
        Image.new('RGB', (1920, 1080), colour).save(current / 'workspace' / f'slide-{number:02d}.png')
    (current / presentations.MANIFEST).write_text(json.dumps({'key': 'abc', 'generated_at': '2026-10-25T09:00:00+02:00', 'presentations': [
        {'id': 'workspace', 'title': 'Workspace', 'description': 'Datasets & campaigns.', 'file': 'workspace.pptx', 'drawn': True,
         'sections': [{'title': 'Workspace', 'slides': ['Cover', 'Datasets', 'Campaigns']}]},
        {'id': 'full-presentation', 'title': 'Full Presentation', 'description': 'Every presentation in one.', 'file': 'full.pptx',
         'sections': [{'title': 'Overview', 'slides': []}, {'title': 'Workspace', 'presentation': 'workspace', 'slides': ['Cover', 'Datasets', 'Campaigns']}]},
    ]}), encoding='utf-8')
    # The apps that show a preview of a link (WhatsApp, Teams, Slack…) read it without signing in.
    client.cookies.clear()
    page = client.get('/documents/view/help/help.md?presentation=workspace&slide=2', headers={'User-Agent': 'WhatsApp/2.23'}).text
    assert '<title>Workspace</title>' in page and '<meta property="og:title" content="Workspace">' in page
    assert '<meta property="og:description" content="Slide 2 of 3: Datasets. Datasets &amp; campaigns.">' in page
    assert '<meta property="og:image" content="http://testserver/presentations/preview/workspace/2.jpg?v=abc">' in page
    assert '<meta name="twitter:card" content="summary_large_image">' in page
    assert '<meta property="og:url" content="http://testserver/presentations/workspace?slide=2">' in page
    # Its cover without a slide, and the first of the help home too.
    home = client.get('/documents/view/help?presentation=workspace').text
    assert '<meta property="og:description" content="Datasets &amp; campaigns.">' in home and '/presentations/preview/workspace/1.jpg' in home
    # The picture: a light JPEG of 1200 × 675 made once from the picture of the slide.
    response = client.get('/presentations/preview/workspace/2.jpg?v=abc')
    assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg'
    with Image.open(__import__('io').BytesIO(response.content)) as image:
        assert image.format == 'JPEG' and image.size == presentations.PREVIEW_SIZE
        assert image.getpixel((600, 337))[1] > 100  # teal, the second slide
    assert (current / 'workspace' / 'preview-02.jpg').is_file()
    # A slide of the full presentation is the picture of that slide in the presentation it comes from.
    page = client.get('/documents/view/help/presentations.md?presentation=full-presentation&slide=3').text
    assert 'Slide 3 of 3: Campaigns. Every presentation in one.' in page and '/presentations/preview/full-presentation/3.jpg' in page
    # The link of Product Presentations shows the cover of the Full Presentation; the other chapters show none.
    chapter = client.get('/documents/view/help/presentations.md').text
    assert '<meta property="og:title" content="Product Presentations">' in chapter and '<title>Product Presentations</title>' in chapter
    assert f'content="{presentations.HELP_CHAPTER_PREVIEW["description"]}"' in chapter
    assert '<meta property="og:image" content="http://testserver/presentations/preview/full-presentation/1.jpg?v=abc">' in chapter
    assert 'og:image' not in client.get('/documents/view/help/overview.md').text
    # The short links lead the apps to the same preview.
    assert '<meta property="og:title" content="Product Presentations">' in client.get('/presentations').text
    assert 'Slide 2 of 3: Datasets.' in client.get('/presentations/workspace?slide=2').text
    # With a public address, the links and their pictures use it, whatever address the page was opened with.
    core.repository.set_application_state(core.RUNTIME_CONFIGURATION_STATE_KEY, json.dumps({'public_address': 'https://dta.example.com:8443'}))
    page = client.get('/presentations/workspace?slide=2').text
    assert '<meta property="og:url" content="https://dta.example.com:8443/presentations/workspace?slide=2">' in page
    assert '<meta property="og:image" content="https://dta.example.com:8443/presentations/preview/workspace/2.jpg?v=abc">' in page
    assert client.get('/api/presentations').json()['link_base'] == 'https://dta.example.com:8443'
    assert client.get('/presentations/preview/full-presentation/3.jpg').status_code == 200 and (current / 'workspace' / 'preview-03.jpg').is_file()
    # A slide beyond the last is the last; an unknown presentation shows the page as always.
    assert 'Slide 3 of 3: Campaigns.' in client.get('/documents/view/help/help.md?presentation=workspace&slide=9').text
    plain = client.get('/documents/view/help/help.md?presentation=missing').text
    assert 'og:image' not in plain and '<title>DriveTest Analyzer</title>' in plain
    assert client.get('/presentations/preview/missing/1.jpg').status_code == 404
    assert 'og:image' not in client.get('/documents/view/changelog?presentation=workspace').text

