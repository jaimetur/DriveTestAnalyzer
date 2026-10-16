"""Starter content: every workspace starts with the shipped methodology, Report Templates and Dashboards."""
import csv
import io
import json
import re

from src.config import PROJECT_ROOT
from src.modules import starter_content

ASSETS = PROJECT_ROOT / 'assets'
VENDOR_FILTER = re.compile(r'^\s*(Operator|Vendor|Operator_Vendor|Vendor_Operator)\s', re.IGNORECASE | re.MULTILINE)


def test_the_shipped_content_names_no_operator_or_vendor():
    templates = sorted((ASSETS / 'ppt-templates').glob('*/*.csv'))
    assert {(path.parent.name, path.stem) for path in templates} >= {
        ('nsa', 'NSA - NetCheck CDR Report'), ('sa', 'SA - NetCheck CDR Report'), ('nsa', 'NSA - RF Quality (RSRP & SINR)')}
    for path in templates:
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8'))))
        # No template filters an Operator, nor Vendors by their operator (3_Ericsson); the Tableau templates of the UK
        # workspace chart some Vendors of their own.
        assert rows and not re.search(r'Operator\s+(NOT\s+)?IN\s*\(', path.read_text(encoding='utf-8')), path.name
        assert not any(re.search(r'\bVendor\s+(NOT\s+)?IN\s*\([^)]*_', row.get('Filters') or '', re.I) for row in rows), path.name
        assert 'G_Level_4 NOT IN (London)' not in path.read_text(encoding='utf-8'), path.name
        assert path.stem.startswith('Tableau') or not any(VENDOR_FILTER.search(row.get('Filters') or '') for row in rows), path.name
    dashboards = [json.loads(path.read_text(encoding='utf-8')) for path in (ASSETS / 'ppt-dashboards').glob('*.json')]
    assert {(item['name'], item['template_technology']) for item in dashboards} >= {
        ('NetCheck CDR Report', 'nsa'), ('NetCheck CDR Report', 'sa'), ('RF Quality (RSRP & SINR)', 'nsa'),
        ('NetCheck CDR Report (Main Cities)', 'nsa'), ('NetCheck CDR Report (Main Cities)', 'sa'),
        ('Tableau Dashboards', 'nsa'), ('Tableau Charts', 'nsa')}
    # The (Main Cities) Dashboards use the Main Cities of each workspace.
    assert all(item['filters']['City'] == ['@main-cities'] for item in dashboards if item['name'].endswith('(Main Cities)'))
    for item in dashboards:
        assert 'datasets' not in item and not any(
            field.replace(' ', '_').casefold() in {'operator', 'vendor', 'operator_vendor', 'vendor_operator'}
            for field in item.get('filters') or {})
        # Each Dashboard uses a shipped Report Template.
        assert (ASSETS / 'ppt-templates' / item['template_technology'] / f"{item['template']}.csv").exists()
    methodology = json.loads((ASSETS / 'scoring-methodologies' / 'NetCheck_2026.json').read_text(encoding='utf-8'))
    assert [profile['name'] for profile in methodology['profiles']] == ['NetCheck 2026']


def test_a_new_workspace_starts_with_the_shipped_content_once(client):
    import src.DriveTestAnalyzer as app_module

    repository = app_module.repository
    assert repository.get_workspace_state(starter_content.STATE_KEY) == '1'
    assert 'NetCheck 2026' in [profile['name'] for profile in repository.get_scoring_profiles()['profiles']]
    templates = {(technology, row['name']) for technology in ('nsa', 'sa') for row in repository.list_report_templates(technology)}
    assert {('nsa', 'NSA - NetCheck CDR Report'), ('sa', 'SA - NetCheck CDR Report'), ('nsa', 'NSA - RF Quality (RSRP & SINR)')} <= templates
    dashboards = json.loads(repository.get_workspace_state(starter_content.DASHBOARDS_STATE_KEY))
    names = sorted((item['name'], item['template_technology']) for item in dashboards.values())
    assert ('NetCheck CDR Report', 'nsa') in names and ('RF Quality (RSRP & SINR)', 'nsa') in names
    # It is added once: content deleted or renamed later is not added again.
    assert starter_content.seed_starter_content(repository) is None
    # A workspace that already has content with those names keeps it.
    repository.set_workspace_state(starter_content.STATE_KEY, '0')
    assert set(starter_content.seed_starter_content(repository).values()) == {0}


def test_a_workspace_already_set_up_gets_the_auto_calculated_fields_the_templates_use(client):
    import src.DriveTestAnalyzer as app_module

    repository = app_module.repository
    shipped = json.loads((ASSETS / 'autocalculated-fields' / 'default-autocalculated-fields.json').read_text(encoding='utf-8'))
    repository.replace_calculated_dimensions([shipped[0]])
    repository.set_workspace_state(starter_content.STATE_KEY, '0')
    added = starter_content.seed_starter_content(repository)
    assert added['auto_calculated_fields'] == len(shipped) - 1
    assert [item['name'] for item in repository.list_calculated_dimensions()] == [item['name'] for item in shipped]


def test_the_other_starter_content_fits_any_market(client):
    import src.DriveTestAnalyzer as app_module
    from src.modules import report_tasks
    from src.modules.scoring_reports import load_report_state

    repository = app_module.repository
    # Scoring report configurations without filters of a market; the GAP compares every operator.
    saved = {item['name']: item['configuration'] for item in load_report_state(repository)['configurations']}
    assert {'National', 'National & Main Cities', 'National per Vendor'} <= set(saved)
    for configuration in saved.values():
        for scenario in configuration['scenarios']:
            assert scenario['context_filters'] == {}
            assert all(options['gap']['operators'] == [] for options in scenario['scorings'].values())
    # Query Builder queries on the views of the chosen CDRs.
    queries = {row['name']: row for row in repository.list_query_builder_queries()}
    assert len(queries) >= 6 and all(json.loads(row['dataset_ids_json']) == [] for row in queries.values())
    assert all(re.search(r'\bselected_(data|voice|speech)\b', row['query_sql']) for row in queries.values())
    # The Reporting Jobs of the UK workspace, with the starter Dashboards and their own Scoring reports.
    jobs = {task['name']: task for task in report_tasks.list_tasks(repository)}
    assert {'Weekly NetCheck Report (@latest campaign)', 'All Modules Report (@latest 2 campaigns)',
            'Scoring Report (@All Campaigns)'} <= set(jobs)
    dashboards = json.loads(repository.get_workspace_state(starter_content.DASHBOARDS_STATE_KEY))
    weekly = jobs['Weekly NetCheck Report (@latest campaign)']
    # The weekly job is disabled until it is enabled in the workspace.
    assert weekly['enabled'] is False and weekly['schedule']['mode'] == 'weekly'
    assert sorted(dashboards[entry['dashboard_id']]['name'] for entry in weekly['definition']['dashboards']) == [
        'NetCheck CDR Report', 'NetCheck CDR Report', 'RF Quality (RSRP & SINR)']
    assert all(entry['filters'] == {'Campaign': ['@latest-campaign']} for entry in weekly['definition']['dashboards'])
    assert [scenario['name'] for scenario in weekly['definition']['scoring'][0]['report']['scenarios']] == ['National', 'Main Cities']
    every = jobs['All Modules Report (@latest 2 campaigns)']['definition']
    assert sorted((dashboards[entry['dashboard_id']]['name'], dashboards[entry['dashboard_id']]['template_technology'])
                  for entry in every['dashboards']) == [
        ('NetCheck CDR Report', 'nsa'), ('NetCheck CDR Report', 'sa'), ('NetCheck CDR Report (Main Cities)', 'nsa'),
        ('NetCheck CDR Report (Main Cities)', 'sa'), ('RF Quality (RSRP & SINR)', 'nsa')]
    assert [entry['selection']['nr_mode'] for entry in every['network_insights']] == ['NSA', 'SA']
    assert every['dataset_analysis']['enabled'] and every['dataset_analysis']['auto_cdrs']
    assert every['modules']['non_qualified_calls']['enabled']
    assert [scenario['name'] for scenario in every['scoring'][0]['report']['scenarios']] == ['National', 'London', 'Main Cities']
    scoring = jobs['Scoring Report (@All Campaigns)']['definition']['scoring']
    assert [(entry['nr_mode'], entry['campaigns']) for entry in scoring] == [('NSA', ['@all-campaigns']), ('SA', ['@all-campaigns'])]


def test_new_workspaces_take_their_vendor_maps_from_the_assets(client):
    import src.DriveTestAnalyzer as app_module

    shipped = json.loads((ASSETS / 'labels-vendors' / 'default-vendor-maps.json').read_text(encoding='utf-8'))
    groups = app_module.repository.list_vendor_mapping_groups()
    assert [group['canonical'] for group in groups[:len(shipped)]] == [item['canonical'] for item in shipped]
    assert [group['color'] for group in groups[:len(shipped)]] == [item['color'] for item in shipped]


def test_netcheck_2026_q3_splits_video_streaming_between_youtube_and_tiktok():
    def load(name):
        return json.loads((ASSETS / 'scoring-methodologies' / name).read_text(encoding='utf-8'))['profiles'][0]

    base, q3 = load('NetCheck_2026.json'), load('NetCheck_2026-Q3.json')
    assert q3['name'] == 'NetCheck 2026-Q3' and q3['id'] != base['id']
    video = {m['kpi']: m for m in q3['configuration']['metrics'] if m['category'] == 'VIDEO STREAM'}
    assert sorted(video) == sorted([f'{service} VIDEO STREAMING {kpi}' for service in ('YOUTUBE', 'TIK TOK')
                                    for kpi in ('SUCCESS RATIO [%]', 'TTFP >= 10 s [%]', 'IRRITATING EXPERIENCE [%]')])
    tiktok = video['TIK TOK VIDEO STREAMING SUCCESS RATIO [%]']
    assert tiktok['calculation']['filters'] == {'Type_of_Test': ['VideoStreaming'], 'Test_Name': ['TikTok']}
    assert (tiktok['contexts']['Drive - City']['max_points'], tiktok['contexts']['Drive - City']['most_reliable_points']) == (18.928, 29.575)
    assert video['YOUTUBE VIDEO STREAMING SUCCESS RATIO [%]']['calculation']['filters']['Test_Name'] == ['YouTube']
    # Video Streaming keeps its 20 %: every environment keeps its Best Network and Most Reliable points.
    for environment in ('Drive - City', 'Drive - Connecting Roads'):
        for field in ('max_points', 'most_reliable_points'):
            total = lambda profile: round(sum(m['contexts'][environment].get(field) or 0 for m in profile['configuration']['metrics']), 6)
            assert total(q3) == total(base)
    # The other KPIs are those of NetCheck 2026.
    others = lambda profile: [m for m in profile['configuration']['metrics'] if m['category'] != 'VIDEO STREAM']
    assert others(q3) == others(base)


def test_a_methodology_shipped_later_reaches_existing_workspaces_once(client):
    import src.DriveTestAnalyzer as app_module

    repository = app_module.repository
    names = lambda: [profile['name'] for profile in repository.get_scoring_profiles()['profiles']]
    # A workspace set up before NetCheck 2026-Q3 was shipped.
    profiles = repository.get_scoring_profiles()
    repository.replace_scoring_profiles({**profiles, 'profiles': [p for p in profiles['profiles'] if p['name'] != 'NetCheck 2026-Q3']})
    with repository.connection() as connection:
        connection.execute("DELETE FROM workspace_state WHERE key = ?", (starter_content.METHODOLOGIES_STATE_KEY,))
    active = repository.get_scoring_profiles()['active_profile_id']
    assert 'NetCheck 2026-Q3' not in names()
    assert starter_content.seed_starter_content(repository) == {'methodologies': 1}
    assert 'NetCheck 2026-Q3' in names() and repository.get_scoring_profiles()['active_profile_id'] == active
    # Deleted later, it is not given again.
    profiles = repository.get_scoring_profiles()
    repository.replace_scoring_profiles({**profiles, 'profiles': [p for p in profiles['profiles'] if p['name'] != 'NetCheck 2026-Q3']})
    assert starter_content.seed_starter_content(repository) is None and 'NetCheck 2026-Q3' not in names()
