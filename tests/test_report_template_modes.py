"""Report Templates and PPT Dashboards without an NR Mode of their own (ticket #11, phase 1)."""
import csv
import io
import json
import sqlite3

from src.modules.bundle_report_templates import uncheck_other_mode_dashboards
from src.modules.cdr_reporting import CATALOG_HEADERS
from src.modules.report_template_modes import (
    TEMPLATE_MODE_MERGE_STATE_KEY, merge_mode_templates, merged_title, migrate_dashboard_definition,
    migrate_dashboards_state, render_nr_mode_tokens, template_base_name,
)
from src.modules.repository import Repository
import src.DriveTestAnalyzer as app_module



def template(subtitle: str, chart: str = 'FDFS DL', title: str = 'Data Analysis', filters: str = '') -> bytes:
    row = {header: '' for header in CATALOG_HEADERS}
    row.update({'Slide': '1', 'Slide Tittle': title, 'Slide Subtittle': subtitle, 'Layout': 'Title + 1 rows + 1 columns',
                'Chart Tittle': chart, 'Source Dataset': 'CDR-Data', 'KPI': 'Mean_Data_Rate', 'Chart type': 'CDF Line',
                'Filters': filters, 'Columns Split': 'Operator'})
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=CATALOG_HEADERS, lineterminator='\n')
    writer.writeheader()
    writer.writerow(row)
    return output.getvalue().encode()


def test_tokens_name_the_nr_mode_of_the_cdrs():
    assert render_nr_mode_tokens('{NR Mode} Charts · {NR Mode Name}', 'SA') == 'SA Charts · Standalone'
    assert render_nr_mode_tokens('{nr mode} Charts · {NR MODE NAME}', 'NSA') == 'NSA Charts · Non-Standalone'
    # Without an NR Mode the text reads NSA, and text without tokens stays as it is.
    assert render_nr_mode_tokens('{NR Mode}', None) == 'NSA'
    assert render_nr_mode_tokens('Plain {braces}', 'SA') == 'Plain {braces}'


def test_titles_that_only_differ_in_the_nr_mode_become_one():
    assert merged_title('Non-Standalone', 'Standalone') == '{NR Mode Name}'
    assert merged_title('NSA Charts Imported From Tableau', 'SA Charts Imported From Tableau') == '{NR Mode} Charts Imported From Tableau'
    # A title only one NR Mode names takes the token in both.
    assert merged_title('RF Quality Analysis', 'SA RF Quality Analysis') == '{NR Mode} RF Quality Analysis'
    assert merged_title('Voice', 'Data') is None
    assert template_base_name('NSA - NetCheck CDR Report', 'NSA') == 'NetCheck CDR Report'
    assert template_base_name('Coverage (SA)', 'SA') == 'Coverage'
    assert template_base_name('Coverage (SA)', 'NSA') == 'Coverage (SA)'


def test_nsa_and_sa_copies_of_a_template_are_merged_and_the_others_kept():
    merge = merge_mode_templates([
        {'technology': 'nsa', 'name': 'NSA - Report', 'content': template('Non-Standalone'), 'uid': 'u-nsa', 'is_default': True,
         'created_by': 'super'},
        {'technology': 'sa', 'name': 'SA - Report', 'content': template('Standalone'), 'uid': 'u-sa'},
        # Different charts: kept as two templates.
        {'technology': 'nsa', 'name': 'NSA - Other', 'content': template('Non-Standalone', chart='A'), 'uid': 'o-nsa'},
        {'technology': 'sa', 'name': 'SA - Other', 'content': template('Standalone', chart='B'), 'uid': 'o-sa'},
        # The same name in both NR Modes with other filters: the SA one takes " (SA)".
        {'technology': 'nsa', 'name': 'Same', 'content': template('x', filters='Operator = EE'), 'uid': 's-nsa'},
        {'technology': 'sa', 'name': 'Same', 'content': template('x', filters='Operator = O2'), 'uid': 's-sa'},
    ])
    templates = {item['name']: item for item in merge.templates}
    assert set(templates) == {'Report', 'NSA - Other', 'SA - Other', 'Same', 'Same (SA)'}
    assert b'{NR Mode Name}' in templates['Report']['content']
    assert templates['Report']['uid'] == 'u-nsa' and templates['Report']['created_by'] == 'super'
    assert [name for name, item in templates.items() if item['is_default']] == ['Report']
    assert merge.renames == {('nsa', 'NSA - Report'): 'Report', ('sa', 'SA - Report'): 'Report', ('sa', 'Same'): 'Same (SA)'}
    assert merge.uids == {'u-sa': 'u-nsa'}
    assert merge.merged == [('NSA - Report', 'SA - Report', 'Report')]


def test_dashboards_read_their_nr_mode_as_part_of_their_selection():
    renames = {('nsa', 'NSA - Report'): 'Report', ('sa', 'SA - Report'): 'Report'}
    migrated = migrate_dashboard_definition(
        {'name': 'London', 'template': 'SA - Report', 'technology': 'sa', 'template_technology': 'sa', 'template_uid': 'u-sa'},
        renames, {'u-sa': 'u-nsa'})
    assert migrated == {'name': 'London', 'template': 'Report', 'nr_mode': 'SA', 'template_uid': 'u-nsa'}
    dashboards, changed = migrate_dashboards_state({
        'a': {'name': 'London', 'template': 'NSA - Report', 'technology': 'nsa'},
        'b': {'name': 'London', 'template': 'SA - Report', 'technology': 'sa'},
    }, renames)
    assert changed
    # Names are unique whatever the NR Mode: the SA Dashboard named as an NSA one takes " (SA)".
    assert {key: (value['name'], value['template'], value['nr_mode']) for key, value in dashboards.items()} == {
        'a': ('London', 'Report', 'NSA'), 'b': ('London (SA)', 'Report', 'SA')}
    # Dashboards saved now stay as they are.
    assert migrate_dashboards_state(dashboards) == (dashboards, False)


def test_a_workspace_of_before_moves_its_templates_into_one_library_once(tmp_path):
    database = tmp_path / 'workspace.db'
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE report_templates (technology TEXT NOT NULL, name TEXT NOT NULL, content BLOB NOT NULL DEFAULT X'', "
            "is_default INTEGER NOT NULL DEFAULT 0, created_at TEXT, updated_at TEXT, updated_by TEXT NOT NULL DEFAULT '', "
            "created_by TEXT NOT NULL DEFAULT '', uid TEXT NOT NULL DEFAULT '', PRIMARY KEY (technology, name), "
            "CHECK (technology IN ('nsa', 'sa')))")
        connection.executemany('INSERT INTO report_templates (technology, name, content, is_default, uid) VALUES (?, ?, ?, ?, ?)', [
            ('nsa', 'NSA - Report', template('Non-Standalone'), 1, 'u-nsa'), ('sa', 'SA - Report', template('Standalone'), 1, 'u-sa'),
        ])
        connection.execute('CREATE TABLE workspace_state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        connection.execute("INSERT INTO workspace_state VALUES ('ppt_dashboards_v2', ?)", (json.dumps({
            'd-nsa': {'name': 'NSA report', 'template': 'NSA - Report', 'technology': 'nsa', 'template_technology': 'nsa',
                      'slide_comments': {'slide:x': ['Kept']}},
            'd-sa': {'name': 'SA report', 'template': 'SA - Report', 'technology': 'sa', 'template_technology': 'sa'},
        }),))
        connection.execute("CREATE TABLE dashboard_ppt_jobs (id INTEGER PRIMARY KEY, template_name TEXT, nr_mode TEXT)")
        connection.execute("INSERT INTO dashboard_ppt_jobs (template_name, nr_mode) VALUES ('SA - Report', 'sa')")
    repository = Repository(database, tmp_path / 'application.db')
    repository.initialize()
    repository.initialize()

    rows = repository.list_report_templates()
    assert [(row['name'], row['is_default'], row['uid']) for row in rows] == [('Report', 1, 'u-nsa')]
    assert render_nr_mode_tokens(bytes(rows[0]['content']).decode(), 'SA').count('Standalone') == 1
    dashboards = json.loads(repository.get_workspace_state('ppt_dashboards_v2'))
    assert {key: (value['template'], value['nr_mode']) for key, value in dashboards.items()} == {
        'd-nsa': ('Report', 'NSA'), 'd-sa': ('Report', 'SA')}
    assert dashboards['d-nsa']['slide_comments'] == {'slide:x': ['Kept']}
    assert not any({'technology', 'template_technology'} & set(value) for value in dashboards.values())
    assert repository.report_template_merge_state()[1] == {'u-sa': 'u-nsa'}
    assert json.loads(repository.get_workspace_state(TEMPLATE_MODE_MERGE_STATE_KEY))['renames']['sa|SA - Report'] == 'Report'
    with repository.connection() as connection:
        assert connection.execute('SELECT template_name FROM dashboard_ppt_jobs').fetchone()[0] == 'Report'
        events = connection.execute("SELECT details FROM audit_logs WHERE action = 'report_templates_nr_mode_merged'").fetchall()
    # Once, with what it merged.
    assert len(events) == 1 and json.loads(events[0][0])['merged'] == [{'nsa': 'NSA - Report', 'sa': 'SA - Report', 'name': 'Report'}]


def test_a_dashboard_shows_the_titles_of_its_nr_mode(client):
    content = template('{NR Mode Name}', chart='{NR Mode} FDFS DL')
    nsa, = app_module.load_template_catalogue(content, nr_mode='NSA')
    sa, = app_module.load_template_catalogue(content, nr_mode='SA')
    raw, = app_module.load_template_catalogue(content)
    assert (nsa.slide_subtitle, nsa.chart_title) == ('Non-Standalone', 'NSA FDFS DL')
    assert (sa.slide_subtitle, sa.chart_title) == ('Standalone', 'SA FDFS DL')
    # The editor reads the template as written.
    assert (raw.slide_subtitle, raw.chart_title) == ('{NR Mode Name}', '{NR Mode} FDFS DL')


def test_a_package_of_before_imports_its_nsa_and_sa_templates_as_one(client, tmp_path):
    workspace = app_module.workspace_registry.create('Package of before')
    repo = Repository(workspace.database_path, app_module.repository.global_db_path)
    repo.initialize()
    repo.set_workspace_state(app_module.DASHBOARD_STATE_KEY, json.dumps({
        'local': {'name': 'Local SA', 'template': 'SA - Report', 'technology': 'sa', 'template_technology': 'sa'},
    }))
    staging = tmp_path / 'package'
    for technology, prefix, subtitle in (('nsa', 'NSA', 'Non-Standalone'), ('sa', 'SA', 'Standalone')):
        folder = staging / 'report-templates' / 'library' / technology
        folder.mkdir(parents=True)
        (folder / f'{prefix} - Report.csv').write_bytes(template(subtitle))
    manifest = {'report_templates': [{'technology': 'nsa', 'name': 'NSA - Report', 'uid': 'p-nsa', 'created_by': 'super'},
                                     {'technology': 'sa', 'name': 'SA - Report', 'uid': 'p-sa', 'created_by': 'super'}]}
    assert app_module.import_slides_templates_archive(staging, [workspace.id], manifest, importing_user='super') == 1

    rows = {str(row['name']): row for row in repo.list_report_templates()}
    assert set(rows) == {'Report'} and rows['Report']['uid'] == 'p-nsa'
    dashboards = json.loads(repo.get_workspace_state(app_module.DASHBOARD_STATE_KEY))
    assert (dashboards['local']['template'], dashboards['local']['nr_mode']) == ('Report', 'SA')
    # Imported again, it is found by its identity: nothing is added.
    assert app_module.import_slides_templates_archive(staging, [workspace.id], manifest, importing_user='super') == 1
    assert [str(row['name']) for row in repo.list_report_templates()] == ['Report']


def test_template_archives_have_one_library(client, tmp_path):
    repo = app_module.repository
    repo.add_report_template('Library', template('{NR Mode Name}'), updated_by='super')
    package, _name = app_module.build_export_archive('ppt-templates')
    archive_path = tmp_path / 'templates.zip'
    archive_path.write_bytes(package)
    import zipfile
    with zipfile.ZipFile(archive_path) as archive:
        names = [name for name in archive.namelist() if name.endswith('.csv')]
    assert any(name.endswith('/library/Library.csv') for name in names)
    assert not any('/nsa/' in name or '/sa/' in name for name in names)


def test_bundle_favourites_of_before_keep_generating_the_dashboards_of_their_nr_mode():
    definition = {'filters': {'nr_mode': 'SA'}, 'sections': [{'key': 'dashboards', 'items': [
        {'key': 'nsa-dash', 'enabled': True, 'nr_mode': 'NSA'},
        {'key': 'sa-dash', 'enabled': True, 'nr_mode': 'SA'},
        {'key': 'unknown', 'enabled': True},
    ]}]}
    assert uncheck_other_mode_dashboards(definition, {'sa-dash': 'SA'}) == ['nsa-dash']
    assert [item['enabled'] for item in definition['sections'][0]['items']] == [False, True, True]


def test_bundle_report_templates_generate_every_dashboard_with_their_nr_mode(tmp_path):
    from types import SimpleNamespace
    from src.modules.bundle_report_templates import SectionGenerator, normalize_definition

    queued = []
    output = tmp_path / 'deck.pptx'
    output.write_bytes(b'pptx')
    tools = SimpleNamespace(
        list_dashboards=lambda _repository: {'nsa-dash': {'name': 'NSA one', 'nr_mode': 'NSA', 'template': 'Report', 'filters': {}}},
        queue_export=lambda key, _user, definition, theme=None: queued.append((key, definition['nr_mode'])) or 1,
        job=lambda _repository, _job_id: {'status': 'ready', 'output_path': str(output), 'progress': 100, 'last_error': ''},
    )
    definition = normalize_definition({'filters': {'nr_mode': 'SA'}, 'sections': [
        {'key': 'dashboards', 'enabled': True, 'items': [{'key': 'nsa-dash', 'enabled': True}], 'options': {'campaigns': []}}]})
    section = next(item for item in definition['sections'] if item['key'] == 'dashboards')
    deck = SectionGenerator(SimpleNamespace(dashboard_reporting=tools), SimpleNamespace(list_main_cities=lambda: []), 'super',
                            definition, tmp_path).dashboards(section)
    # The NSA Dashboard is generated with the SA CDRs of the report (its template serves both NR Modes).
    assert queued == [('nsa-dash', 'SA')] and deck.decks == [('nsa-dash', b'pptx')]


def test_reporting_jobs_keep_the_nr_mode_of_each_dashboard_entry():
    from src.modules.report_tasks import normalize_definition

    definition = normalize_definition({'dashboards': [
        {'dashboard_id': 'd1', 'nr_mode': 'sa', 'auto_cdrs': True}, {'dashboard_id': 'd2', 'auto_cdrs': True}]})
    # Empty: the Dashboard's own NR Mode, as the entries saved before.
    assert [entry['nr_mode'] for entry in definition['dashboards']] == ['SA', '']
