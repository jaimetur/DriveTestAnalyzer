from __future__ import annotations

import json
import re

import src.DriveTestAnalyzer as app_module
from src.modules import saved_filters
from tests.test_scoring_api import scoring_api


DEFAULT_HIERARCHY = ['Operator', 'Vendor', 'Region', 'City', 'Campaign']
CUSTOM_HIERARCHY = ['Campaign', 'Operator', 'Region', 'Vendor', 'City']
# Cluster follows Region when a hierarchy does not place it.
SAVED_HIERARCHY = ['Campaign', 'Operator', 'Region', 'Cluster', 'Vendor', 'City']


def page_hierarchy(client) -> list[str]:
    page = client.get('/scoring')
    config = re.search(r'<script type="application/json" data-scoring-config>(.*?)</script>', page.text, re.DOTALL)
    return json.loads(config.group(1))['aggregation_hierarchy']


def context_filter_position(text: str, level: str) -> int:
    # The <select> of the filter, not the CSS rules of the page that name it.
    return re.search(rf'<select\b[^>]*\bdata-scoring-context-filter="{level}"', text).start()


def test_scoring_hierarchy_controls_and_saved_job_order(scoring_api):
    client = scoring_api['client']
    page = client.get('/scoring')
    assert page.status_code == 200
    assert 'value="Dataset Type" data-aggregation-level' not in page.text
    for selector in ('data-aggregation-level', 'data-scoring-context-filter'):
        # The Campaign filter sits with NR Mode (they choose the CDRs), before the filters of the hierarchy.
        levels = ['Campaign', *(level for level in DEFAULT_HIERARCHY if level != 'Campaign')] if selector.endswith('filter') else DEFAULT_HIERARCHY
        positions = [context_filter_position(page.text, level) if selector.endswith('filter')
                     else page.text.index(f'value="{level}" data-aggregation-level') for level in levels]
        assert positions == sorted(positions)
    saved = client.put('/api/scoring/aggregation-hierarchy', json={'levels': CUSTOM_HIERARCHY})
    assert saved.status_code == 200, saved.text
    assert saved.json()['aggregation_hierarchy'] == SAVED_HIERARCHY
    page = client.get('/scoring')
    positions = [context_filter_position(page.text, level) for level in CUSTOM_HIERARCHY]
    assert positions == sorted(positions)
    payload = {'dataset_ids': scoring_api['complete_dataset_ids'], 'nr_mode': 'NSA',
               'aggregation_levels': ['Region', 'Operator', 'Campaign']}
    response = client.post('/api/scoring/saved-filters', json=payload)
    assert response.status_code == 200, response.text
    job = response.json()['saved_filter']
    assert job['aggregation_levels'] == ['Campaign', 'Operator', 'Region']
    assert job['aggregation_contract_version'] == 2
    assert job['aggregation_hierarchy'] == SAVED_HIERARCHY
    assert client.put('/api/scoring/aggregation-hierarchy', json={'levels': DEFAULT_HIERARCHY}).status_code == 200
    historical = saved_filters.get_saved_filter(scoring_api['repository'], job['id'])
    assert historical['aggregation_hierarchy'] == SAVED_HIERARCHY


def test_hierarchy_is_an_application_setting_outside_the_methodologies(scoring_api):
    client, repository = scoring_api['client'], scoring_api['repository']
    assert client.put('/api/scoring/aggregation-hierarchy', json={'levels': ['Operator', 'Operator']}).status_code == 400
    assert client.put('/api/scoring/aggregation-hierarchy', json={'levels': CUSTOM_HIERARCHY}).status_code == 200
    assert page_hierarchy(client) == SAVED_HIERARCHY
    # Methodologies neither save nor export a hierarchy, and a hierarchy in an imported methodology is ignored.
    configuration = repository.get_scoring_configuration()
    assert 'aggregation_hierarchy' not in configuration
    configuration['aggregation_hierarchy'] = DEFAULT_HIERARCHY
    assert client.put('/api/workspace-config/scoring-configuration', json=configuration).status_code == 200
    assert 'aggregation_hierarchy' not in repository.get_scoring_configuration()
    document = client.get('/api/workspace-config/scoring-configuration/export').json()
    assert 'aggregation_hierarchy' not in document['profiles'][0]['configuration']
    assert page_hierarchy(client) == SAVED_HIERARCHY


def test_reporting_follows_scoring_in_module_and_help_navigation(scoring_api):
    client = scoring_api['client']
    token = 'scoring-navigation-super-admin'
    app_module.SESSIONS[token] = app_module.SessionUser(username='super', role='super-admin')
    client.cookies.set(app_module.SESSION_COOKIE, token)
    page = client.get('/scoring')
    assert page.status_code == 200
    main_tabs = page.text.split('class="module-tabs-primary"', 1)[1].split('class="module-tabs-secondary"', 1)[0]
    assert main_tabs.index('href="/ppt-designer"') < main_tabs.index('href="/scoring"') < main_tabs.index('href="/reporting"')
    modules = page.text.split('aria-label="Main modules"', 1)[1].split('</nav>', 1)[0]
    assert modules.index('href="/ppt-designer"') < modules.index('href="/scoring"') < modules.index('href="/reporting"')
    documents = client.get('/api/documents/help-index').json()['documents']
    paths = [document['relative_path'] for document in documents]
    # Network Insights follows Scoring, then Non-Qualified Calls and Reporting, as in the main tabs.
    assert paths.index('network-insights.md') == paths.index('scoring-gap-analysis.md') + 1
    assert paths.index('non-qualified-calls.md') == paths.index('network-insights.md') + 1
    assert paths.index('reporting.md') == paths.index('non-qualified-calls.md') + 1
    # Scoring follows PPT Designer, as in the main tabs.
    assert paths.index('scoring-gap-analysis.md') == paths.index('ppt-designer.md') + 1
    # The Help navigation takes the group of each chapter from the server.
    groups = {document['relative_path']: document['group'] for document in documents}
    assert groups['scoring-gap-analysis.md'] == groups['reporting.md'] == 'Main Modules'
