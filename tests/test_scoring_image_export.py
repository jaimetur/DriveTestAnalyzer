from __future__ import annotations

import json
from pathlib import Path

import src.DriveTestAnalyzer as app_module
from src.modules.app_event_details import app_event_origin, describe_app_event

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCORING_TEMPLATE = PROJECT_ROOT / 'src/web_interface/templates/scoring.html'
SCORING_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/scoring.js'
IMAGE_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/element_image.js'


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


def test_scoring_image_export_requires_login(client):
    response = client.post('/api/scoring/image-export', json={'kind': 'chart'})

    assert response.status_code == 401
    assert not [row for row in app_module.repository.list_logs(limit=20) if row['action'].startswith('export_scoring_image')]


def test_scoring_results_place_one_download_button_over_the_chart_or_table_under_the_pointer():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    # The drawing of the image loads before the page script that uses it.
    assert template.index("js/element_image.js") < template.index("js/scoring.js")
    assert '.scoring-image-download { position: fixed;' in template
    assert '[data-scoring-theme="midnight"] .scoring-image-download {' in template
    # One button for the page, over the innermost chart, map, table or panel of the results.
    assert "const IMAGE_TABLES = '.scoring-insight-table-wrap, .scoring-matrix-wrap, .scoring-table-wrap, .scoring-position';" in script
    assert "const IMAGE_CHARTS = '.scoring-chart-card, .scoring-loss-map-card, .scoring-expandable-part';" in script
    assert "const target = node?.closest?.(IMAGE_TARGETS);" in script
    assert "return target?.closest('[data-result-pane]') && root.contains(target) ? target : null;" in script
    # Shown with a mouse over it, for a few seconds after a tap on touch screens, beside the zoom buttons.
    assert "if (event.pointerType !== 'mouse' || imageButton.contains(event.target)) return;" in script
    assert 'imageHideTimer = window.setTimeout(hideImageButton, 5000);' in script
    assert "for (const toolbar of imageTarget.querySelectorAll('.scoring-map-zoom'))" in script
    assert "const label = `Download this ${imageKind(target)} as an image (PNG)`;" in script
    # The zoom buttons are left out of the image, and every download (or failure) is recorded.
    assert "const IMAGE_EXCLUDED = '.scoring-map-zoom, .scoring-map-zoom-rect, .scoring-content-zoom-rect';" in script
    assert "await window.downloadElementImage(target, fileName, {exclude: IMAGE_EXCLUDED});" in script
    assert "fetch('/api/scoring/image-export', {" in script
    assert 'recordImageDownload({...details, file_name: fileName, error: reason});' in script


def test_element_image_draws_the_element_as_shown_with_its_scrolled_content_whole():
    script = IMAGE_SCRIPT.read_text(encoding='utf-8')

    assert 'window.downloadElementImage = downloadElementImage;' in script
    # The copy keeps the styles of the page (pseudo-elements too) over an initial-value reset, and the SVG shapes their
    # geometry from their attributes.
    assert "const RESET = '[data-element-image] :where(:not(style, [data-element-image-svg] *)) { all: unset; }';" in script
    assert "for (const pseudo of ['::before', '::after'])" in script
    assert "const SVG_GEOMETRY = ['d', 'x', 'y', 'cx', 'cy', 'r', 'rx', 'ry', 'width', 'height', 'transform'];" in script
    # What scrolls sideways is widened while the copy is made, then the page and its scroll positions are put back.
    assert '/^(auto|scroll)$/.test(getComputedStyle(node).overflowX)' in script
    assert 'const restore = showScrolledContent(element);' in script
    assert 'for (const [node, left, top] of scrolled)' in script
    # Sharp in every browser, within the largest canvas Safari draws, and an SVG where a PNG cannot be saved.
    assert 'const MAX_PIXELS = 16e6;' in script
    assert 'viewBox="0 0 ${width} ${height}"' in script
    assert "saveFile(blob || new Blob([svg], {type: 'image/svg+xml'}), name);" in script
