"""Starter content: every workspace starts with the shipped methodology, Report Templates and Dashboards."""
import csv
import io
import json
import re

from src.config import PROJECT_ROOT
from src.modules import starter_content

ASSETS = PROJECT_ROOT / 'assets'
VENDOR_FILTER = re.compile(r'^\s*(Operator|Vendor|Operator_Vendor|Vendor_Operator)\s', re.IGNORECASE | re.MULTILINE)


def _seed_favourites(repository):
    """The favourites a new workspace starts with, which the client fixture leaves out (see conftest)."""
    return (starter_content._seed_favourites_filters(repository),
            starter_content._seed_bundle_report_template_favourites(repository, 'system'))


def test_the_shipped_content_names_no_operator_or_vendor():
    # One library: each template serves any NR Mode.
    templates = sorted((ASSETS / 'ppt-templates').glob('*.csv'))
    assert not list((ASSETS / 'ppt-templates').glob('*/*.csv'))
    assert {path.stem for path in templates} == {'NetCheck CDR Report', 'NetCheck CDR Report (Main Cities)', 'RF Quality (RSRP & SINR)',
                                                 'Tableau Dashboards', 'Tableau Charts', 'Tableau Charts - Only Maps'}
    for path in templates:
        rows = list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8'))))
        # No template filters an Operator, nor Vendors by their operator (3_Ericsson); the Tableau templates of the UK
        # workspace chart some Vendors of their own.
        assert rows and not re.search(r'Operator\s+(NOT\s+)?IN\s*\(', path.read_text(encoding='utf-8')), path.name
        assert not any(re.search(r'\bVendor\s+(NOT\s+)?IN\s*\([^)]*_', row.get('Filters') or '', re.I) for row in rows), path.name
        # Nor a city of the UK workspace (each Dashboard chooses its own Main Cities), nor the UK in its title.
        assert not re.search(r'G_Level_4\s+(NOT\s+)?IN\s*\(', path.read_text(encoding='utf-8')), path.name
        assert not any(re.search(r'\bUK\b', row.get('Slide Tittle') or '') for row in rows), path.name
        assert path.stem.startswith('Tableau') or not any(VENDOR_FILTER.search(row.get('Filters') or '') for row in rows), path.name
    dashboards = [json.loads(path.read_text(encoding='utf-8')) for path in (ASSETS / 'ppt-dashboards').glob('*.json')]
    # The Dashboards of the UK workspace, one per NR Mode.
    assert {(item['name'], item['template'], item['nr_mode']) for item in dashboards} == {
        (f'{nr_mode} - {template}', template, nr_mode) for nr_mode in ('NSA', 'SA') for template in (
            'NetCheck CDR Report', 'NetCheck CDR Report (Main Cities)', 'RF Quality (RSRP & SINR)', 'Tableau Dashboards', 'Tableau Charts')}
    assert not any({'technology', 'template_technology'} & set(item) for item in dashboards)
    # The (Main Cities) Dashboards use the Main Cities of each workspace.
    assert all(item['filters']['City'] == ['@main-cities'] for item in dashboards if item['name'].endswith('(Main Cities)'))
    for item in dashboards:
        assert 'datasets' not in item and not any(
            field.replace(' ', '_').casefold() in {'operator', 'vendor', 'operator_vendor', 'vendor_operator'}
            for field in item.get('filters') or {})
        # Each Dashboard uses a shipped Report Template.
        assert (ASSETS / 'ppt-templates' / f"{item['template']}.csv").exists()
    methodology = json.loads((ASSETS / 'scoring-methodologies' / 'NetCheck_2026.json').read_text(encoding='utf-8'))
    assert [profile['name'] for profile in methodology['profiles']] == ['NetCheck 2026']


def test_a_new_workspace_starts_with_the_shipped_content_once(client):
    import src.DriveTestAnalyzer as app_module

    repository = app_module.repository
    assert repository.get_workspace_state(starter_content.STATE_KEY) == '1'
    assert 'NetCheck 2026' in [profile['name'] for profile in repository.get_scoring_profiles()['profiles']]
    templates = {row['name'] for row in repository.list_report_templates()}
    assert {'NetCheck CDR Report', 'NetCheck CDR Report (Main Cities)', 'RF Quality (RSRP & SINR)'} <= templates
    dashboards = json.loads(repository.get_workspace_state(starter_content.DASHBOARDS_STATE_KEY))
    names = sorted((item['name'], item['template'], item['nr_mode']) for item in dashboards.values())
    assert ('NSA - NetCheck CDR Report', 'NetCheck CDR Report', 'NSA') in names
    assert ('SA - NetCheck CDR Report', 'NetCheck CDR Report', 'SA') in names
    assert ('NSA - RF Quality (RSRP & SINR)', 'RF Quality (RSRP & SINR)', 'NSA') in names
    assert ('SA - Tableau Charts', 'Tableau Charts', 'SA') in names
    # It is added once: content deleted or renamed later is not added again.
    assert starter_content.seed_starter_content(repository) is None
    # A workspace that already has content with those names keeps it.
    _seed_favourites(repository)
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
    # Scoring report configurations without filters of a market (the GAP compares the Focus operators of the Operator
    # Maps); their Geographical Areas show the Main Cities of the workspace.
    saved = {item['name']: item['configuration'] for item in load_report_state(repository)['configurations']}
    assert {'National', 'National - Best Network Only', 'National - Most Reliable Network Only', 'National & Main Cities',
            'National per Vendor'} <= set(saved)
    for configuration in saved.values():
        for scenario in configuration['scenarios']:
            assert scenario['context_filters'] == {}
            assert all('operators' not in options['gap'] for options in scenario['scorings'].values())
            assert not scenario['area_summary']['cities'] and scenario['area_summary']['main_cities']
    # Query Builder queries on the views of the chosen CDRs.
    queries = {row['name']: row for row in repository.list_query_builder_queries()}
    assert len(queries) >= 7 and all(json.loads(row['dataset_ids_json']) == [] for row in queries.values())
    assert all(re.search(r'\bselected_(data|voice|speech)\b', row['query_sql']) for row in queries.values())
    # The Reporting Jobs of the UK workspace, in its order, with the starter Dashboards.
    shipped = sorted((json.loads(path.read_text(encoding='utf-8')) for path in (ASSETS / 'reporting-jobs').glob('*.json')),
                     key=lambda item: item['position'])
    assert [task['name'] for task in report_tasks.list_tasks(repository)] == [item['name'] for item in shipped]
    assert all(not item['send_email'] and item['recipients'] == [] for item in shipped)
    jobs = {task['name']: task for task in report_tasks.list_tasks(repository)}
    dashboards = json.loads(repository.get_workspace_state(starter_content.DASHBOARDS_STATE_KEY))
    weekly = jobs['PPT Weekly (@latest campaings)']
    # The weekly job is disabled until it is enabled in the workspace.
    assert weekly['enabled'] is False and weekly['schedule']['mode'] == 'weekly'
    assert sorted(dashboards[entry['dashboard_id']]['name'] for entry in weekly['definition']['dashboards']) == [
        'NSA - NetCheck CDR Report', 'NSA - RF Quality (RSRP & SINR)', 'SA - NetCheck CDR Report']
    # Every operator (the Operator Maps leave out the excluded ones).
    assert all(entry['filters'] == {'Campaign': ['@latest-campaign']} for entry in weekly['definition']['dashboards'])
    # The others each generate a favourite Bundle Report Template of the whole country, by hand.
    assert all(task['enabled'] and task['schedule']['mode'] == 'manual'
               and task['definition']['modules']['bundle_report_template']['enabled']
               for name, task in jobs.items() if name != 'PPT Weekly (@latest campaings)')


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


def test_netcheck_2025_follows_the_2025_26_methodology_up_to_2026_q1():
    from src.modules.scoring_config import validate_scoring_profiles
    from src.modules.scoring_methodologies import methodology_for

    def load(name):
        return json.loads((ASSETS / 'scoring-methodologies' / name).read_text(encoding='utf-8'))['profiles'][0]

    old, base, q3 = load('NetCheck_2025.json'), load('NetCheck_2026.json'), load('NetCheck_2026-Q3.json')
    assert (old['id'], old['name']) == ('netcheck-2025', 'NetCheck 2025')
    metrics = {m['code']: m for m in old['configuration']['metrics']}
    base_metrics = {m['code']: m for m in base['configuration']['metrics']}
    # Call Setup Time > 15 s instead of > 10 s, with the same thresholds.
    assert metrics['K3']['kpi'] == 'CALL SETUP TIME > 15 s [%]'
    assert metrics['K3']['calculation']['formula'] == '100 * SUM(Call_Setup_Time > 15) / COUNT(Call_Status)'
    assert metrics['K3']['contexts']['Drive - City']['thresholds'] == base_metrics['K3']['contexts']['Drive - City']['thresholds']
    # The 2025/26 drive test points (City 65 %, Roads 35 %): classic calls 252, WhatsApp calls 84, Multi RAB 14.
    city = lambda code: round(metrics[code]['contexts']['Drive - City']['max_points'], 4)
    road = lambda code: round(metrics[code]['contexts']['Drive - Connecting Roads']['max_points'], 4)
    assert [city(f'K{n}') for n in range(1, 12)] == [92.82, 10.92, 5.46, 27.3, 9.1, 18.2, 36.4, 9.1, 3.0333, 6.0667, 9.1]
    assert [road(f'K{n}') for n in range(1, 12)] == [49.98, 5.88, 2.94, 14.7, 4.9, 9.8, 19.6, 4.9, 1.6333, 3.2667, 4.9]
    for environment, total in (('Drive - City', 650), ('Drive - Connecting Roads', 350)):
        assert round(sum(m['contexts'][environment]['max_points'] for m in metrics.values()), 6) == total
    # Data, thresholds and Most Reliable points are those of NetCheck 2026 (weight_share is derived from the points).
    plain = lambda metric: {**metric, 'contexts': {name: {key: value for key, value in context.items() if key != 'weight_share'}
                                                   for name, context in metric['contexts'].items()}}
    for code in metrics:
        if int(code[1:]) > 11:
            assert plain(metrics[code]) == plain(base_metrics[code])
        for environment in ('Drive - City', 'Drive - Connecting Roads'):
            assert metrics[code]['contexts'][environment].get('most_reliable_points') == base_metrics[code]['contexts'][environment].get('most_reliable_points')
    # Each shipped methodology applies to its campaigns, without overlaps.
    assert [old['campaigns'], base['campaigns'], q3['campaigns']] == [
        {'from': '', 'to': '2026-Q1'}, {'from': '2026-Q2', 'to': '2026-Q2'}, {'from': '2026-Q3', 'to': ''}]
    profiles = validate_scoring_profiles({'active_profile_id': base['id'], 'profiles': [base, old, q3]})
    assert [methodology_for(profiles, campaign)['id'] for campaign in ('UK_BM_Q2_2025', 'UK_Q1_2026', 'UK_Q2_2026', 'UK_Q3_NSA_2026')] == [
        'netcheck-2025', 'netcheck-2025', 'netcheck-2026', 'netcheck-2026-q3']


def test_netcheck_2025_reaches_a_workspace_with_overlapping_campaigns_without_them(client):
    import src.DriveTestAnalyzer as app_module

    repository = app_module.repository
    profiles = repository.get_scoring_profiles()
    # A new workspace keeps NetCheck 2026 as its active methodology.
    assert profiles['active_profile_id'] == 'netcheck-2026'
    assert 'netcheck-2025' in [profile['id'] for profile in profiles['profiles']]
    # A workspace whose NetCheck 2026 applies up to 2026-Q2, set up before NetCheck 2025 was shipped.
    kept = [{**profile, 'campaigns': {'from': '', 'to': '2026-Q2'}} if profile['id'] == 'netcheck-2026' else profile
            for profile in profiles['profiles'] if profile['id'] != 'netcheck-2025']
    repository.replace_scoring_profiles({**profiles, 'profiles': kept})
    repository.set_workspace_state(starter_content.METHODOLOGIES_STATE_KEY, json.dumps(['netcheck-2026', 'netcheck-2026-q3']))
    assert starter_content.seed_starter_content(repository) == {'methodologies': 1}
    added = next(profile for profile in repository.get_scoring_profiles()['profiles'] if profile['id'] == 'netcheck-2025')
    assert not added.get('campaigns')


def test_a_new_workspace_starts_with_the_favourites_of_the_uk_workspace(client):
    import src.DriveTestAnalyzer as app_module
    from src.modules import bundle_report_templates, saved_filters

    repository = app_module.repository

    def shipped(folder):
        return [json.loads(path.read_text(encoding='utf-8')) for path in sorted((ASSETS / folder).glob('*.json'))]

    assert _seed_favourites(repository) == (len(shipped('scoring-favourites-filters')),
                                            len(shipped('bundle-report-template-favourites')))

    # The favourite Bundle Report Templates, with the shipped Dashboards of their NR Mode checked as they were.
    favourites = {item['name']: item['definition'] for item in bundle_report_templates.list_favourites(repository)}
    assert {item['name'] for item in shipped('bundle-report-template-favourites')} <= set(favourites)
    # For the whole country and every operator (the Operator Maps leave out the SA tests of Three).
    assert all(not any(definition['filters'][key] for key in ('operators', 'regions', 'clusters', 'cities'))
               for definition in favourites.values())
    dashboards = json.loads(repository.get_workspace_state(starter_content.DASHBOARDS_STATE_KEY))
    for name, nr_mode in (('SCO+NI+NQ+PPT+CDR (@Latest 2 campaigns) · NSA · Nationwide', 'NSA'),
                          ('SCO+NI+NQ+PPT+CDR (@Latest 2 campaigns) · SA · Nationwide', 'SA')):
        items = next(section for section in favourites[name]['sections'] if section['key'] == 'dashboards')['items']
        checked = [dashboards[item['key']] for item in items if item['enabled']]
        assert checked and all(dashboard['nr_mode'] == nr_mode for dashboard in checked)
        assert f'{nr_mode} - NetCheck CDR Report (Main Cities)' in [dashboard['name'] for dashboard in checked]
    # The Favourites Filters, in their order, wait for the CDRs of their Campaign choice.
    filters = [item for item in saved_filters.list_saved_filters(repository) if item['pinned']]
    assert [item['name'] for item in filters] == [item['name'] for item in sorted(
        shipped('scoring-favourites-filters'), key=lambda item: item['position'])]
    assert all(item['dataset_ids'] == [] and item['area_summary']['main_cities'] for item in filters)
    assert filters[0]['missing_cdrs'] == ['Latest campaign CDRs']
    for item in shipped('scoring-favourites-filters'):
        assert 'cdrs' not in item and item['context_filters']['Campaign'][0].startswith('@')
        assert not any(values for key, values in item['context_filters'].items() if key != 'Campaign')


def test_the_starter_jobs_generate_the_starter_favourites_they_name(client):
    import src.DriveTestAnalyzer as app_module
    from src.modules import bundle_report_templates, report_tasks

    repository = app_module.repository
    for task in report_tasks.list_tasks(repository):
        report_tasks.delete_task(repository, task['id'])
    _seed_favourites(repository)
    shipped = [json.loads(path.read_text(encoding='utf-8')) for path in (ASSETS / 'reporting-jobs').glob('*.json')]
    assert starter_content._seed_reporting_jobs(repository, 'system') == len(shipped)
    # Each job of a favourite Bundle Report Template generates the one of this workspace with the name of the asset.
    favourites = {str(item['id']): item['name'] for item in bundle_report_templates.list_favourites(repository)}
    generated = {}
    for task in report_tasks.list_tasks(repository):
        report = task['definition']['modules'].get('bundle_report_template') or {}
        if report.get('enabled'):
            generated[task['name']] = [favourites.get(value) for value in report['options']['filters']['favourites']]
    assert len(generated) == 8 and all(names == [name] for name, names in generated.items())
