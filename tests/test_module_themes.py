"""One colour theme per user for every themed module (Scoring & GAP Analysis, Network Insights, CDR Analysis and PPT
Dashboards): Ericsson by default, chosen in any of them, shown at once on their pages and at hand in their floating bar."""
from __future__ import annotations

import json

import src.DriveTestAnalyzer as core
from src.modules.ppt_dashboards import dashboard_viewer_tokens
from src.modules.scoring_themes import THEMES


def _login(client) -> None:
    client.cookies.clear()
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303


def test_a_theme_chosen_in_one_module_is_the_theme_of_every_module(client) -> None:
    _login(client)
    endpoints = ('/api/scoring/theme', '/api/network-insights/theme', '/api/cdr-analysis/theme', '/api/ppt-dashboards/theme')
    # Ericsson until the user chooses another one.
    assert {client.get(endpoint).json()['theme'] for endpoint in endpoints} == {'ericsson'}
    assert client.put('/api/cdr-analysis/theme', json={'theme': 'heatmap'}).json() == {'theme': 'heatmap'}
    assert {client.get(endpoint).json()['theme'] for endpoint in endpoints} == {'heatmap'}
    assert client.put('/api/ppt-dashboards/theme', json={'theme': 'Paper'}).json()['theme'] == 'paper'
    assert {client.get(endpoint).json()['theme'] for endpoint in endpoints} == {'paper'}
    assert client.put('/api/ppt-dashboards/theme', json={'theme': 'sunset'}).status_code == 400
    logs = {row['action']: json.loads(row['details']) for row in core.repository.list_logs()
            if row['action'].endswith('_theme_changed')}
    assert logs['cdr_analysis_theme_changed'] == {'theme': 'heatmap', 'previous': 'ericsson'}
    assert logs['ppt_dashboards_theme_changed'] == {'theme': 'paper', 'previous': 'heatmap'}


def test_the_pages_carry_the_theme_and_put_its_selector_in_the_floating_bar(client) -> None:
    _login(client)
    client.put('/api/cdr-analysis/theme', json={'theme': 'ericsson'})
    page = client.get('/datasets-analysis').text
    # The page is drawn in the theme (its cards, tables, tiles and charts read these variables); its selector, shown with
    # an open CDR, is copied into the floating bar of the page.
    assert 'data-cdr-theme="ericsson"' in page and '--cdr-header: #0068BF' in page
    template = (core.PROJECT_ROOT / 'src' / 'web_interface' / 'templates' / 'datasets_analysis.html').read_text(encoding='utf-8')
    assert 'data-cdr-theme-select data-section-bar-theme' in template and 'id="cdr-chart-tokens"' in template
    dashboards = client.get('/ppt-dashboards').text
    assert 'data-ds-theme="ericsson"' in dashboards and 'id="ds-viewer-tokens"' in dashboards
    assert 'id="ds-viewer-theme" aria-label="Colour theme of the Dashboard charts and PPTs" data-section-bar-theme' in dashboards


def test_the_page_variables_follow_each_theme() -> None:
    tokens = core.cdr_analysis_chart_tokens(THEMES['ericsson'])
    assert tokens['--cdr-header'] == THEMES['ericsson']['header'] and tokens['--cdr-tile-text'] == THEMES['ericsson']['header_text']
    assert tokens['--cdr-card'] == THEMES['ericsson']['surface'] and tokens['--cdr-chart-bar'] == THEMES['ericsson']['accent']
    viewer = dashboard_viewer_tokens('ericsson')
    # The slide titles of the viewer as on the content slides of the Dashboard PPTs.
    assert viewer['--ds-title-color'] == THEMES['ericsson']['titles']['heading_color']
    assert viewer['--ds-title-focus-color'] == THEMES['ericsson']['titles']['focus_color'] and viewer['--ds-title-focus-weight'] == '700'
    assert viewer['--ds-title-font'].startswith('"Ericsson Hilda Light"')
    assert dashboard_viewer_tokens('netcheck')['--ds-title-transform'] == 'uppercase'


def test_the_theme_is_chosen_only_in_the_floating_bar() -> None:
    root = core.PROJECT_ROOT / 'src' / 'web_interface' / 'static'
    script = (root / 'js' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'css' / 'app.css').read_text(encoding='utf-8')
    # The bar copies the Theme selector of Scoring & GAP Analysis, Network Insights, CDR Analysis and PPT Dashboards and
    # hides the one of the page, which stays as the one the module reads.
    assert "document.querySelector('select[data-section-bar-theme], select[data-scoring-theme-select], select#ni-theme')" in script
    assert "(themeSelect.closest('label') || themeSelect).classList.add('section-bar-theme-source');" in script
    assert '.section-bar-theme-source { display: none !important; }' in css
