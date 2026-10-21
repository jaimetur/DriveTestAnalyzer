from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.DriveTestAnalyzer as app_module
from src.modules.app_event_details import describe_app_event

WEB = Path(__file__).resolve().parents[1] / 'src/web_interface'
BUTTONS_SCRIPT = WEB / 'static/js/image_buttons.js'


def _events(action_start: str) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = {}
    for row in app_module.repository.list_logs(limit=50):
        if row['action'].startswith(action_start):
            events.setdefault(row['action'], []).append({**dict(row), 'details': json.loads(row['details'])})
    return events


def test_images_of_every_module_are_recorded_in_app_events(client):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    map_image = {
        'module': 'network-insights', 'section': 'Coverage & Interference Maps', 'kind': 'chart',
        'title': 'Coverage & Interference Maps — LTE Coverage (mean RSRP per grid square)', 'context': {'theme': 'ericsson'},
        'file_name': 'Coverage & Interference Maps — LTE Coverage (mean RSRP per grid square).png', 'format': 'png',
        'width': 640, 'height': 360,
    }

    assert client.post('/api/image-export', json=map_image).json() == {'recorded': True}
    assert client.post('/api/image-export', json={
        'module': 'ppt-dashboards', 'section': 'Dashboard viewer', 'kind': 'chart', 'title': 'CDR-Voice Validation',
        'context': {'slide': 'NSA · NetCheck CDR Report · Slide 3 / 20', 'theme': 'netcheck'}, 'destination': 'clipboard',
        'file_name': 'CDR-Voice Validation.png', 'format': 'png', 'width': 1200, 'height': 300,
    }).status_code == 200
    assert client.post('/api/image-export', json={
        'module': 'non-qualified-calls', 'section': 'Progress View', 'kind': 'table', 'title': 'Progress View — Status',
        'file_name': 'Progress View — Status.png', 'error': 'The browser could not draw it.',
    }).status_code == 200
    assert client.post('/api/image-export', json={'module': 'builders', 'kind': 'chart', 'title': 'Ad-hoc chart',
                                                  'context': {'cdr_type': 'data', 'cdrs': ''}}).status_code == 200

    events = _events('export_')
    [image] = events['export_network_insights_image']
    assert image['username'] == 'super'
    assert image['details'] == {
        'section': 'Coverage & Interference Maps', 'kind': 'chart',
        'title': 'Coverage & Interference Maps — LTE Coverage (mean RSRP per grid square)', 'theme': 'ericsson',
        'file_name': 'Coverage & Interference Maps — LTE Coverage (mean RSRP per grid square).png', 'format': 'png',
        'width': 640, 'height': 360,
    }
    assert describe_app_event(image['action'], image['details']).startswith(
        'Export network insights image: section Coverage & Interference Maps, kind chart')
    [copied] = events['export_dashboard_image']
    assert copied['details']['destination'] == 'clipboard' and copied['details']['slide'] == 'NSA · NetCheck CDR Report · Slide 3 / 20'
    [failure] = events['export_nq_calls_image_failed']
    assert failure['details']['error'] == 'The browser could not draw it.' and failure['details']['kind'] == 'table'
    # Empty values of the page are left out.
    [chart] = events['export_chart_builder_image']
    assert chart['details']['cdr_type'] == 'data' and 'cdrs' not in chart['details']


@pytest.mark.parametrize('payload, status', [
    ({'module': 'scoring', 'kind': 'chart'}, 400),
    ({'module': 'workspace', 'kind': 'table'}, 400),
])
def test_image_export_refuses_the_modules_it_does_not_record(client, payload, status):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)

    assert client.post('/api/image-export', json=payload).status_code == status
    assert not _events('export_scoring_image') and not _events('export_image')


def test_image_export_requires_login(client):
    assert client.post('/api/image-export', json={'module': 'network-insights', 'kind': 'chart'}).status_code == 401
    assert not _events('export_network_insights_image')


@pytest.mark.parametrize('template, script', [
    ('network_insights.html', 'js/network_insights.js'),
    ('non_qualified_calls.html', 'js/non_qualified_calls.js'),
    ('ppt_dashboards.html', 'js/ppt_dashboards.js'),
    ('scoring.html', 'js/scoring.js'),
])
def test_module_pages_load_the_image_buttons_before_their_script(template, script):
    page = (WEB / 'templates' / template).read_text(encoding='utf-8')

    assert page.index('js/element_image.js') < page.index('js/image_buttons.js') < page.index(script)


def test_every_module_puts_the_buttons_over_its_panels_charts_and_tables():
    insights = (WEB / 'static/js/network_insights.js').read_text(encoding='utf-8')
    calls = (WEB / 'static/js/non_qualified_calls.js').read_text(encoding='utf-8')
    dashboards = (WEB / 'static/js/ppt_dashboards.js').read_text(encoding='utf-8')
    dashboards_page = (WEB / 'templates/ppt_dashboards.html').read_text(encoding='utf-8')
    builder = (WEB / 'templates/chart_builder.html').read_text(encoding='utf-8')

    # Network Insights: each panel, its charts, maps, ladders and tables, and the larger view of one.
    assert "targets: `details.ni-panel, ${imageTables}, ${imageCharts}, .ni-expand-content`," in insights
    assert "module: 'network-insights'" in insights and "exclude: '.ni-chart-zoom, .ni-column-filter'" in insights
    # Non-Qualified Calls: each panel, and its KPIs, charts and tables (a table with its title is one image).
    assert "targets: `details.panel.collapsible-panel, ${imageTables}, ${imageCharts}, .nq-kpis, .nq-rate-overview, .nq-phase-cards, .nq-failure-section`," in calls
    assert "module: 'non-qualified-calls'" in calls
    # PPT Dashboards: the slide of the viewer and its charts, the Charts Panel and its thumbnails, the larger view of a
    # chart; the viewer and the larger view hold the buttons above them.
    assert "targets: '#ds-charts, #ds-charts > .ds-chart, #ds-ppt-charts-panel, #ds-ppt-charts-body > .report-chart-card, .ds-chart-expanded-canvas'," in dashboards
    assert 'id="ds-viewer" data-image-buttons-host' in dashboards_page
    assert 'id="ds-chart-expanded-overlay" data-image-buttons-host' in dashboards_page
    # Chart Builder: the card of its chart, once the shared scripts (loaded after its own) are there.
    assert "document.addEventListener('DOMContentLoaded', () => window.attachImageButtons?.({" in builder
    assert builder.index('js/dashboard_charts.js') < builder.index('js/element_image.js') < builder.index('js/image_buttons.js')
    assert "module: 'builders'" in builder


def test_the_buttons_live_in_dialogs_and_overlays_and_keep_clear_of_the_page_buttons():
    buttons = BUTTONS_SCRIPT.read_text(encoding='utf-8')

    # A dialog, or an overlay marked so, holds the buttons of what it shows, above it; its cards start there.
    assert "const HOSTS = 'dialog[open], [data-image-buttons-host]';" in buttons
    assert 'if (button.parentElement !== host) host.append(button, copy);' in buttons
    assert 'outer && (!host || host.contains(outer));' in buttons
    # An overlay that draws a filter places what it holds from its own corner.
    assert 'element.style.left = `${Math.round(2 * left - shown.left)}px`;' in buttons
    # Both buttons keep clear of every button of the page they would cover, and below every floating section bar.
    assert 'const span = size.width * 2 + 6;' in buttons
    assert "document.querySelectorAll('.section-bar, [data-section-bar]')" in buttons
    # Each module records its images (Scoring with its Saved Filter).
    assert "record = imageDetails => recordImageExport('/api/image-export', {module, ...imageDetails})," in buttons


def test_map_tiles_are_asked_for_with_cors_so_maps_can_be_saved_as_images():
    charts = (WEB / 'static/js/dashboard_charts.js').read_text(encoding='utf-8')

    assert "image.crossOrigin = 'anonymous';" in charts
    # A tile server that does not allow it is asked again plainly, so the map still shows.
    assert "image.removeAttribute('crossorigin');" in charts
