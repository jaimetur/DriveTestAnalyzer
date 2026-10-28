"""E2E Dashboards and PPT Dashboards are stored as PPT Designer, and Reporting (old) as PPT Reporting (old)."""
import json
import sqlite3

from src.modules import ppt_naming


class _State:
    def __init__(self, values):
        self.values = values

    def get_application_state(self, key):
        return self.values.get(key)

    def set_application_state(self, key, value):
        self.values[key] = value


def test_features_activation_and_interface_settings_follow_the_new_module_names():
    rule = {'default': 'none', 'allow': {'roles': ['super-admin']}}
    labels = {
        'e2e-dashboards': {'title': 'E2E Dashboards', 'short_title': 'Dashboards', 'tab_icon': 'e2e-dashboards', 'position': 2},
        'reporting-old': {'title': 'My old reports', 'short_title': 'Reporting (old)', 'tab_icon': 'reporting-old', 'position': 3},
        'scoring': {'title': 'Scoring & GAP Analysis'},
    }
    state = _State({'features': json.dumps({'e2e-dashboards': rule, 'reporting-old': rule}), 'labels': json.dumps(labels)})
    ppt_naming.migrate_application_state(state, ('features', 'labels', 'missing'))
    assert json.loads(state.values['features']) == {'ppt-designer': rule, 'ppt-reporting-old': rule}
    migrated = json.loads(state.values['labels'])
    assert set(migrated) == {'ppt-designer', 'ppt-reporting-old', 'scoring'}
    assert migrated['ppt-designer'] == {'title': 'PPT Designer', 'short_title': 'Designer', 'tab_icon': 'ppt-designer', 'position': 2}
    # A title chosen in Interface Settings is kept.
    assert migrated['ppt-reporting-old']['title'] == 'My old reports'
    assert migrated['ppt-reporting-old']['short_title'] == 'PPT Reporting (old)'
    assert migrated['ppt-reporting-old']['tab_icon'] == 'ppt-reporting-old'
    # Settings already migrated are left as they are, except a former title of the module.
    state.values['labels'] = json.dumps({**migrated, 'ppt-reporting-old': {
        **migrated['ppt-reporting-old'], 'title': 'E2E Reporting', 'short_title': 'E2E Reporting'}})
    ppt_naming.migrate_application_state(state, ('labels',))
    assert {field: json.loads(state.values['labels'])['ppt-reporting-old'][field] for field in ('title', 'short_title')} == {
        'title': 'PPT Reporting (old)', 'short_title': 'PPT Reporting (old)'}
    before = dict(state.values)
    ppt_naming.migrate_application_state(state, ('features', 'labels'))
    assert state.values == before


def test_the_dashboards_of_an_e2e_workspace_become_designs_with_their_definitions(tmp_path):
    database = tmp_path / 'workspace.db'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE workspace_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.executemany('INSERT INTO workspace_state VALUES (?, ?)', [
            ('e2e_dashboards_v2', '{"a": {"name": "NetCheck CDR Report"}}'),
            ('e2e_dashboard_default_filters_v6', '1'),
            ('campaign_map', '{}'),
        ])
    ppt_naming.migrate_workspace_database(database)
    with sqlite3.connect(database) as connection:
        stored = dict(connection.execute('SELECT key, value FROM workspace_state').fetchall())
    assert stored == {'ppt_designs_v2': '{"a": {"name": "NetCheck CDR Report"}}',
                      'ppt_design_default_filters_v6': '1', 'campaign_map': '{}'}
    # A missing database, or one without the table, is left untouched.
    ppt_naming.migrate_workspace_database(tmp_path / 'missing.db')
    assert not (tmp_path / 'missing.db').exists()


def test_ppt_dashboards_becomes_ppt_designer_keeping_designs_jobs_drafts_pictures_and_events(tmp_path):
    database = tmp_path / 'workspace.db'
    dashboards = {'weekly': {'name': 'Weekly', 'template': 'T', 'design_overrides': {'hidden_slides': ['s2']}, 'design': None},
                  'mine': {'name': 'Mine', 'template': 'T', 'design': {'version': 1, 'slides': []}, 'design_overrides': {}}}
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE workspace_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.executemany('INSERT INTO workspace_state VALUES (?, ?)', [
            ('ppt_dashboards_v2', json.dumps(dashboards)), ('ppt_dashboard_default_filters_v6', '1'),
            ('creators:ppt-dashboards', '{"weekly": "super"}'), ('identities:ppt-dashboards', '{"weekly": "uid-1"}'),
            ('bundle_report_template_dashboard_nr_modes_v1', '1'), ('dashboard_main_cities', '["London"]'),
        ])
        connection.execute('CREATE TABLE dashboard_ppt_jobs (id TEXT PRIMARY KEY, dashboard_id TEXT NOT NULL, dashboard_name TEXT NOT NULL)')
        connection.execute("INSERT INTO dashboard_ppt_jobs VALUES ('j1', 'weekly', 'Weekly')")
        connection.execute('CREATE TABLE dashboard_design_drafts (dashboard_id TEXT, username TEXT, state_json TEXT)')
        connection.execute("INSERT INTO dashboard_design_drafts VALUES ('weekly', 'super', '{}')")
        connection.execute('CREATE TABLE dashboard_design_images (id TEXT PRIMARY KEY, data BLOB)')
        connection.execute("INSERT INTO dashboard_design_images VALUES ('abc', x'00')")
        connection.execute('CREATE TABLE dashboard_filter_selections (selection_key TEXT)')
        connection.execute('CREATE TABLE audit_logs (action TEXT, details TEXT, origin TEXT)')
        connection.executemany('INSERT INTO audit_logs VALUES (?, ?, ?)', [
            ('save_dashboard', '{"dashboard_id": "weekly"}', 'module:ppt-dashboards'),
            ('dashboard_design_saved', '{"id": "weekly", "design_overrides": {}}', 'module:ppt-dashboards'),
            ('ppt_dashboards_theme_changed', '{}', 'module:ppt-dashboards'),
            ('save_scoring_filter', '{"name": "dashboard of the week"}', 'module:scoring'),
        ])
    ppt_naming.migrate_workspace_database(database)
    ppt_naming.migrate_workspace_database(database)
    with sqlite3.connect(database) as connection:
        stored = dict(connection.execute('SELECT key, value FROM workspace_state').fetchall())
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        job = connection.execute('SELECT id, design_id, design_name FROM design_ppt_jobs').fetchone()
        draft = connection.execute('SELECT design_id FROM design_drafts').fetchone()
        events = connection.execute('SELECT action, details, origin FROM audit_logs').fetchall()
    # Every Design keeps its definition, its slides under their current names.
    assert json.loads(stored['ppt_designs_v2']) == {
        'weekly': {'name': 'Weekly', 'template': 'T', 'slide_overrides': {'hidden_slides': ['s2']}, 'own_slides': None},
        'mine': {'name': 'Mine', 'template': 'T', 'own_slides': {'version': 1, 'slides': []}, 'slide_overrides': {}}}
    assert {key: stored[key] for key in ('ppt_design_default_filters_v6', 'creators:ppt-designer', 'identities:ppt-designer',
                                          'bundle_report_template_design_nr_modes_v1', 'dashboard_main_cities')} == {
        'ppt_design_default_filters_v6': '1', 'creators:ppt-designer': '{"weekly": "super"}', 'identities:ppt-designer': '{"weekly": "uid-1"}',
        'bundle_report_template_design_nr_modes_v1': '1', 'dashboard_main_cities': '["London"]'}
    assert not {'ppt_dashboards_v2', 'creators:ppt-dashboards'} & set(stored)
    assert {'design_ppt_jobs', 'design_drafts', 'design_images'} <= tables
    assert not {'dashboard_ppt_jobs', 'dashboard_design_drafts', 'dashboard_design_images', 'dashboard_filter_selections'} & tables
    assert job == ('j1', 'weekly', 'Weekly') and draft == ('weekly',)
    assert events == [
        ('save_design', '{"design_id": "weekly"}', 'module:ppt-designer'),
        ('design_slides_saved', '{"id": "weekly", "slide_overrides": {}}', 'module:ppt-designer'),
        ('ppt_designer_theme_changed', '{}', 'module:ppt-designer'),
        ('save_scoring_filter', '{"name": "dashboard of the week"}', 'module:scoring'),
    ]


def test_the_application_database_names_ppt_designer(tmp_path):
    with sqlite3.connect(tmp_path / 'application.db') as connection:
        connection.execute('CREATE TABLE modules_profiles (id INTEGER PRIMARY KEY, modules_json TEXT)')
        connection.execute("""INSERT INTO modules_profiles VALUES (1, '["workspace", "ppt-dashboards", "scoring"]')""")
        connection.execute('CREATE TABLE tickets (id INTEGER PRIMARY KEY, module TEXT)')
        connection.execute("INSERT INTO tickets VALUES (26, 'ppt-dashboards'), (27, 'scoring')")
        connection.execute('CREATE TABLE application_state (key TEXT PRIMARY KEY, value TEXT)')
        connection.executemany('INSERT INTO application_state VALUES (?, ?)', [
            ('recurring_database_backup', '{"components": ["workspace_database", "dashboards"]}'),
            ('runtime_configuration_v1', '{"report_chart_renderer": "dashboard-canvas"}'),
        ])
        ppt_naming.migrate_application_database(connection)
        assert connection.execute('SELECT modules_json FROM modules_profiles').fetchone()[0] == '["workspace", "ppt-designer", "scoring"]'
        assert connection.execute('SELECT module FROM tickets ORDER BY id').fetchall() == [('ppt-designer',), ('scoring',)]
        state = dict(connection.execute('SELECT key, value FROM application_state').fetchall())
    assert json.loads(state['recurring_database_backup'])['components'] == ['workspace_database', 'designs']
    assert json.loads(state['runtime_configuration_v1'])['report_chart_renderer'] == 'canvas'
