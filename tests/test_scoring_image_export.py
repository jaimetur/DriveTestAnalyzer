from __future__ import annotations

import json
from pathlib import Path

import src.DriveTestAnalyzer as app_module
from src.modules.app_event_details import app_event_origin, describe_app_event

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCORING_TEMPLATE = PROJECT_ROOT / 'src/web_interface/templates/scoring.html'
SCORING_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/scoring.js'
IMAGE_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/element_image.js'
BUTTONS_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/image_buttons.js'
APP_STYLES = PROJECT_ROOT / 'src/web_interface/static/css/app.css'


def test_downloaded_scoring_images_and_failures_are_recorded_in_app_events(client, monkeypatch):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    record = {'id': 9, 'name': 'Q3 London', 'pinned': True, 'status': 'completed'}
    monkeypatch.setattr(app_module, 'get_saved_filter', lambda _repository, filter_id: record if filter_id == 9 else None)
    downloaded = {
        'saved_filter_id': 9, 'tab': 'Scoring Charts', 'kind': 'chart', 'title': 'Best Network Scoring per Service',
        'environment': 'All Environments', 'theme': 'ericsson', 'file_name': 'Best Network Scoring per Service - All Environments.png',
        'format': 'png', 'width': 838, 'height': 720,
    }

    assert client.post('/api/scoring/image-export', json=downloaded).json() == {'recorded': True}
    assert client.post('/api/scoring/image-export', json={
        'tab': 'GAP Analysis', 'kind': 'table', 'title': 'KPI GAP Profile — O2 UK · GAP to EE per KPI',
        'file_name': 'KPI GAP Profile.png', 'error': 'The browser could not draw it.',
    }).status_code == 200

    events = {}
    for row in app_module.repository.list_logs(limit=20):
        events.setdefault(row['action'], []).append(row)
    [image] = events['export_scoring_image']
    assert json.loads(image['details']) == {**downloaded, 'name': 'Q3 London', 'starred': True}
    assert image['username'] == 'super'
    assert app_event_origin(image['action'], json.loads(image['details']), image['origin']) == 'module:scoring'
    assert describe_app_event(image['action'], json.loads(image['details'])).startswith(
        'Export scoring image: saved filter ID 9 (favourite), name Q3 London, tab Scoring Charts, kind chart')
    [failure] = events['export_scoring_image_failed']
    details = json.loads(failure['details'])
    assert details['error'] == 'The browser could not draw it.' and details['saved_filter_id'] is None
    assert details['kind'] == 'table' and details['title'] == 'KPI GAP Profile — O2 UK · GAP to EE per KPI'
    assert 'destination' not in json.loads(image['details'])


def test_scoring_images_copied_to_the_clipboard_are_recorded_as_such(client):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    copied = {'tab': 'Scoring Charts', 'kind': 'chart', 'title': 'Best Network Scoring per Service', 'format': 'png',
              'file_name': 'Best Network Scoring per Service - All Environments.png', 'width': 838, 'height': 720,
              'destination': 'clipboard'}

    assert client.post('/api/scoring/image-export', json=copied).json() == {'recorded': True}
    assert client.post('/api/scoring/image-export', json={**copied, 'destination': 'copy-dialog'}).status_code == 200
    rows = [row for row in app_module.repository.list_logs(limit=20) if row['action'] == 'export_scoring_image']
    assert sorted(json.loads(row['details'])['destination'] for row in rows) == ['clipboard', 'copy-dialog']


def test_scoring_image_export_requires_login(client):
    response = client.post('/api/scoring/image-export', json={'kind': 'chart'})

    assert response.status_code == 401
    assert not [row for row in app_module.repository.list_logs(limit=20) if row['action'].startswith('export_scoring_image')]


def test_scoring_results_place_one_download_button_over_the_chart_or_table_under_the_pointer():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    buttons = BUTTONS_SCRIPT.read_text(encoding='utf-8')
    styles = APP_STYLES.read_text(encoding='utf-8')

    # The drawing of the image and the buttons (shared by the modules) load before the page script that uses them.
    assert template.index("js/element_image.js") < template.index("js/image_buttons.js") < template.index("js/scoring.js")
    assert '.element-image-button { position: fixed;' in styles
    assert '[data-scoring-theme="midnight"] .element-image-button {' in template
    # The charts, maps, tables and panels of Scoring (the tables and the map of a route too), and the larger view of one.
    assert "const IMAGE_TABLES = '.scoring-insight-table-wrap, .scoring-matrix-wrap, .scoring-table-wrap, .scoring-position, .scoring-route-side > .scoring-insight-table';" in script
    assert "const IMAGE_CHARTS = '.scoring-chart-card, .scoring-loss-map-card, .scoring-expandable-part, .scoring-route-map-frame';" in script
    assert "target.previousElementSibling?.matches('.scoring-route-table-title')" in script
    assert '.scoring-best-network-layout, .scoring-insight-section, .scoring-expanded-holder`;' in script
    assert "within: '[data-result-pane], [data-scoring-chart-overlay]'," in script
    assert 'data-scoring-chart-overlay data-image-buttons-host' in template
    # Two pairs of buttons for the page: one over the whole card (the outermost chart, map, table or panel), which stays
    # in its place while the pointer moves over the card, and one over the chart or table of the card under it.
    assert "const slots = ['card', 'part'].map(level => {" in buttons
    assert 'outer = outer.parentElement?.closest(targets)) card = outer;' in buttons
    # A card that holds a single chart or table has the buttons of the card only.
    assert 'return {card, part: part === card || parts.length < 2 ? null : part};' in buttons
    # The buttons of a card stand on its top edge (in a dialog, in its corner); those of a chart or table at the right
    # side of its card have the right edge of those of the card (below them where they would meet), the others stay in
    # their corner, and the button of the card has an icon of its own.
    assert 'let top = onEdge ? bounds.top - size.height / 2 : bounds.top + 8;' in buttons
    assert 'if (cardButton.right - right < 48) {' in buttons and 'right = cardButton.right;' in buttons
    assert 'if (top < cardButton.bottom + 6 && top + size.height > cardButton.top - 6) top = cardButton.bottom + 6;' in buttons
    assert 'card: ICON(' in buttons and 'part: ICON(' in buttons
    # They stay at the top of their card, chart or table and show only while it is in sight, below the section bar and
    # the tab bar of the results (they do not follow the scroll down it).
    assert 'slot.inSight = top >= inset + 4 && top + size.height <= window.innerHeight;' in buttons
    assert "element.style.visibility = slot.inSight ? '' : 'hidden';" in buttons
    assert 'tabs?.height ? tabs.bottom + 3 : 0);' in script
    # Shown with a mouse over it, for a few seconds after a tap on touch screens, beside the zoom buttons.
    assert "if (event.pointerType !== 'mouse' || isImageButton(event.target)) return;" in buttons
    assert 'showAt(event.target, {hideAfter: 5000});' in buttons
    assert "obstacles: '.scoring-map-zoom'" in script
    assert "[[slot.button, `Download this ${kind} as an image (PNG)`]," in buttons
    # Beside each download, on its left, a screenshot that copies it to the clipboard (green a moment once copied).
    assert "[slot.copy, `Copy this ${kind} to the clipboard as a screenshot, to paste it elsewhere`]]) {" in buttons
    assert 'for (const [element, left] of [[button, right - size.width], [copy, right - size.width * 2 - 6]]) {' in buttons
    assert 'const draw = !copy ? window.downloadElementImage : clipboard ? window.copyElementImage : window.drawElementImage;' in buttons
    assert '.element-image-button.element-image-copy.is-copied {' in styles
    # The zoom buttons are left out of the image, and every download or copy (or failure) is recorded with the Saved Filter.
    assert "const IMAGE_EXCLUDED = '.scoring-map-zoom, .scoring-map-zoom-rect, .scoring-content-zoom-rect';" in script
    assert 'exclude: IMAGE_EXCLUDED,' in script
    assert 'const image = copy ? await draw(target, {exclude}) : await draw(target, file, {exclude});' in buttons
    assert "...(copy ? {destination: clipboard ? 'clipboard' : 'copy-dialog'} : {})," in buttons
    # Where the browser does not let the page copy images (an address that is not secure), the screenshot shows in a
    # dialog to copy it from the menu of the image, or to download it; the page behind does not scroll while it is open.
    assert "const clipboard = copy && window.isSecureContext && Boolean(navigator.clipboard?.write) && typeof ClipboardItem === 'function';" in buttons
    assert 'function showImageToCopy(blob, fileName) {' in buttons and '.element-image-copy-dialog {' in styles
    assert "document.documentElement.style.overflow = 'hidden';" in buttons
    assert 'overscroll-behavior: contain;' in styles.split('.element-image-copy-dialog {', 1)[1].split('}', 1)[0]
    assert "record: details => window.recordImageExport('/api/scoring/image-export', details)," in script
    assert 'record({...recorded, file_name: file, error: reason});' in buttons


def test_element_image_draws_the_element_as_shown_with_its_scrolled_content_whole():
    script = IMAGE_SCRIPT.read_text(encoding='utf-8')

    assert 'window.downloadElementImage = downloadElementImage;' in script
    # The screenshot: the same image copied to the clipboard, given to it within the click (as Safari requires).
    assert 'window.copyElementImage = copyElementImage;' in script
    assert 'window.drawElementImage = drawElementImage;' in script
    assert "await navigator.clipboard.write([new ClipboardItem({'image/png': png})]);" in script
    # The copy keeps the styles of the page (pseudo-elements too) over an initial-value reset, and the SVG shapes their
    # geometry from their attributes.
    assert "const RESET = '[data-element-image] :where(:not(style, [data-element-image-svg] *)) { all: unset; }';" in script
    assert "for (const pseudo of ['::before', '::after'])" in script
    assert "const SVG_GEOMETRY = ['d', 'x', 'y', 'cx', 'cy', 'r', 'rx', 'ry', 'width', 'height', 'transform'];" in script
    # What scrolls sideways is widened while the copy is made, then the page and its scroll positions are put back.
    assert '/^(auto|scroll)$/.test(getComputedStyle(node).overflowX)' in script
    # What scrolls downwards is as tall as its content while the copy is made, so every row is in the image.
    assert "/^(auto|scroll)$/.test(getComputedStyle(node).overflowY)" in script
    assert "for (const [name, value] of [['max-height', 'none'], ['height', 'auto']])" in script
    assert 'const restore = showScrolledContent(element);' in script
    # A part whose content fits in it on the page grows in the copy with what it holds (the page height is the least it
    # has), so the last rows of a table are never left out of the image; the image is as tall as the copy laid out.
    assert "for (const [name, value] of [['min-height', `${least}px`], ['height', 'auto'], ['max-height', 'none']]) {" in script
    assert "rows.replace(/(\\d*\\.?\\d+)px/g, 'minmax($1px, auto)')" in script
    assert '&& source.scrollHeight <= source.clientHeight + 1) growWithContent(copy);' in script
    assert 'height = Math.max(height, Math.ceil(copy.getBoundingClientRect().height));' in script
    assert 'for (const [node, left, top] of scrolled)' in script
    # Sharp in every browser, within the largest canvas Safari draws, and an SVG where a PNG cannot be saved.
    assert 'const MAX_PIXELS = 16e6;' in script
    assert 'viewBox="0 0 ${width} ${height}"' in script
    assert "saveFile(blob || new Blob([svg], {type: 'image/svg+xml'}), name);" in script
