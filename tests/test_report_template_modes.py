"""Report Templates and PPT Designer without an NR Mode of their own (ticket #11, phase 1)."""
import csv
import io
import json
import sqlite3

from src.modules.bundle_report_templates import uncheck_other_mode_designs
from src.modules.cdr_reporting import CATALOG_HEADERS
from src.modules.report_template_modes import (
    TEMPLATE_MODE_MERGE_STATE_KEY, merge_mode_templates, merged_title, migrate_design_definition,
    migrate_designs_state, render_nr_mode_tokens, template_base_name,
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


def test_designs_read_their_nr_mode_as_part_of_their_selection():
    renames = {('nsa', 'NSA - Report'): 'Report', ('sa', 'SA - Report'): 'Report'}
    migrated = migrate_design_definition(
        {'name': 'London', 'template': 'SA - Report', 'technology': 'sa', 'template_technology': 'sa', 'template_uid': 'u-sa'},
        renames, {'u-sa': 'u-nsa'})
    assert migrated == {'name': 'London', 'template': 'Report', 'nr_mode': 'SA', 'template_uid': 'u-nsa'}
    designs, changed = migrate_designs_state({
        'a': {'name': 'London', 'template': 'NSA - Report', 'technology': 'nsa'},
        'b': {'name': 'London', 'template': 'SA - Report', 'technology': 'sa'},
    }, renames)
    assert changed
    # Names are unique whatever the NR Mode: the SA Design named as an NSA one takes " (SA)".
    assert {key: (value['name'], value['template'], value['nr_mode']) for key, value in designs.items()} == {
        'a': ('London', 'Report', 'NSA'), 'b': ('London (SA)', 'Report', 'SA')}
    # Designs saved now stay as they are.
    assert migrate_designs_state(designs) == (designs, False)


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
        connection.execute("INSERT INTO workspace_state VALUES ('ppt_designs_v2', ?)", (json.dumps({
            'd-nsa': {'name': 'NSA report', 'template': 'NSA - Report', 'technology': 'nsa', 'template_technology': 'nsa',
                      'slide_comments': {'slide:x': ['Kept']}},
            'd-sa': {'name': 'SA report', 'template': 'SA - Report', 'technology': 'sa', 'template_technology': 'sa'},
        }),))
        connection.execute("CREATE TABLE design_ppt_jobs (id INTEGER PRIMARY KEY, template_name TEXT, nr_mode TEXT)")
        connection.execute("INSERT INTO design_ppt_jobs (template_name, nr_mode) VALUES ('SA - Report', 'sa')")
    repository = Repository(database, tmp_path / 'application.db')
    repository.initialize()
    repository.initialize()

    rows = repository.list_report_templates()
    assert [(row['name'], row['is_default'], row['uid']) for row in rows] == [('Report', 1, 'u-nsa')]
    assert render_nr_mode_tokens(bytes(rows[0]['content']).decode(), 'SA').count('Standalone') == 1
    designs = json.loads(repository.get_workspace_state('ppt_designs_v2'))
    assert {key: (value['template'], value['nr_mode']) for key, value in designs.items()} == {
        'd-nsa': ('Report', 'NSA'), 'd-sa': ('Report', 'SA')}
    assert designs['d-nsa']['slide_comments'] == {'slide:x': ['Kept']}
    assert not any({'technology', 'template_technology'} & set(value) for value in designs.values())
    assert repository.report_template_merge_state()[1] == {'u-sa': 'u-nsa'}
    assert json.loads(repository.get_workspace_state(TEMPLATE_MODE_MERGE_STATE_KEY))['renames']['sa|SA - Report'] == 'Report'
    with repository.connection() as connection:
        assert connection.execute('SELECT template_name FROM design_ppt_jobs').fetchone()[0] == 'Report'
        events = connection.execute("SELECT details FROM audit_logs WHERE action = 'report_templates_nr_mode_merged'").fetchall()
    # Once, with what it merged.
    assert len(events) == 1 and json.loads(events[0][0])['merged'] == [{'nsa': 'NSA - Report', 'sa': 'SA - Report', 'name': 'Report'}]


def test_a_design_shows_the_titles_of_its_nr_mode(client):
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
    repo.set_workspace_state(app_module.DESIGN_STATE_KEY, json.dumps({
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
    designs = json.loads(repo.get_workspace_state(app_module.DESIGN_STATE_KEY))
    assert (designs['local']['template'], designs['local']['nr_mode']) == ('Report', 'SA')
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


def test_bundle_favourites_of_before_keep_generating_the_designs_of_their_nr_mode():
    definition = {'filters': {'nr_mode': 'SA'}, 'sections': [{'key': 'designs', 'items': [
        {'key': 'nsa-dash', 'enabled': True, 'nr_mode': 'NSA'},
        {'key': 'sa-dash', 'enabled': True, 'nr_mode': 'SA'},
        {'key': 'unknown', 'enabled': True},
    ]}]}
    assert uncheck_other_mode_designs(definition, {'sa-dash': 'SA'}) == ['nsa-dash']
    assert [item['enabled'] for item in definition['sections'][0]['items']] == [False, True, True]


def test_bundle_report_templates_generate_every_design_with_their_nr_mode(tmp_path):
    from types import SimpleNamespace
    from src.modules.bundle_report_templates import SectionGenerator, normalize_definition

    queued = []
    output = tmp_path / 'deck.pptx'
    output.write_bytes(b'pptx')
    tools = SimpleNamespace(
        list_designs=lambda _repository: {'nsa-dash': {'name': 'NSA one', 'nr_mode': 'NSA', 'template': 'Report', 'filters': {}}},
        queue_export=lambda key, _user, definition, theme=None: queued.append((key, definition['nr_mode'])) or 1,
        job=lambda _repository, _job_id: {'status': 'ready', 'output_path': str(output), 'progress': 100, 'last_error': ''},
    )
    definition = normalize_definition({'filters': {'nr_mode': 'SA'}, 'sections': [
        {'key': 'designs', 'enabled': True, 'items': [{'key': 'nsa-dash', 'enabled': True}], 'options': {'campaigns': []}}]})
    section = next(item for item in definition['sections'] if item['key'] == 'designs')
    deck = SectionGenerator(SimpleNamespace(design_reporting=tools), SimpleNamespace(list_main_cities=lambda: []), 'super',
                            definition, tmp_path).designs(section)
    # The NSA Design is generated with the SA CDRs of the report (its template serves both NR Modes).
    assert queued == [('nsa-dash', 'SA')] and deck.decks == [('nsa-dash', b'pptx')]


def test_bundle_report_templates_give_the_parameters_of_a_design_the_values_of_their_common_filters(tmp_path):
    from types import SimpleNamespace
    from src.modules.bundle_report_templates import SectionGenerator, normalize_definition

    queued = []
    output = tmp_path / 'deck.pptx'
    output.write_bytes(b'pptx')
    stored = {'name': 'City report', 'nr_mode': 'NSA', 'template': 'Cities', 'filters': {}, 'parameter_values': {'p-city': ['London']},
              'slide_comments': {'s1': [{'text': 'London is fine'}]}}
    tools = SimpleNamespace(
        list_designs=lambda _repository: {'city': stored},
        parameters=lambda _repository, _raw: [{'id': 'p-city', 'name': 'Chosen Cities', 'type': 'values', 'field': 'City'},
                                              {'id': 'p-note', 'name': 'Note', 'type': 'text'}],
        queue_export=lambda key, _user, definition, theme=None: queued.append(definition) or 1,
        job=lambda _repository, _job_id: {'status': 'ready', 'output_path': str(output), 'progress': 100, 'last_error': ''},
    )
    for cities, values, comments in ((['Leeds'], {'p-city': ['Leeds']}, {}), ([], {'p-city': ['London']}, stored['slide_comments'])):
        definition = normalize_definition({'filters': {'nr_mode': 'NSA', 'cities': cities}, 'sections': [
            {'key': 'designs', 'enabled': True, 'items': [{'key': 'city', 'enabled': True}], 'options': {'campaigns': []}}]})
        section = next(item for item in definition['sections'] if item['key'] == 'designs')
        SectionGenerator(SimpleNamespace(design_reporting=tools), SimpleNamespace(list_main_cities=lambda: []), 'super',
                         definition, tmp_path).designs(section)
        # The Cities of the report fill its City parameter, and the comments written for London stay out.
        assert (queued[-1]['parameter_values'], queued[-1]['slide_comments']) == (values, comments)


def test_reporting_jobs_keep_the_nr_mode_of_each_design_entry():
    from src.modules.report_tasks import normalize_definition

    definition = normalize_definition({'designs': [
        {'design_id': 'd1', 'nr_mode': 'sa', 'auto_cdrs': True}, {'design_id': 'd2', 'auto_cdrs': True}]})
    # Empty: the Design's own NR Mode, as the entries saved before.
    assert [entry['nr_mode'] for entry in definition['designs']] == ['SA', '']


# NSA & SA in one Design (ticket #11, phases 2 and 3).

def entry_of(**fields):
    from dataclasses import replace

    from src.modules.cdr_reporting import parse_catalog_csv
    return replace(parse_catalog_csv(template('{NR Mode Name}', chart='{NR Mode} DL Throughput', title='FDFS DL ({NR Mode})'))[0], **fields)


def test_a_design_of_both_nr_modes_names_them_and_tells_them_apart():
    from src.modules.report_template_modes import entry_for_nr_mode

    both = entry_for_nr_mode(entry_of(legend='Operator'), 'NSA+SA')
    assert (both.slide_title, both.slide_subtitle, both.chart_title) == (
        'FDFS DL (NSA & SA)', 'Non-Standalone & Standalone', 'NSA & SA DL Throughput')
    # A chart that reads both NR Modes gets NR Mode as the last level of the split of its legend, and of its legend.
    assert (both.columns_split, both.legend) == ('Operator × NR Mode', 'Operator, NR Mode')
    # One NR Mode: nothing to tell apart.
    single = entry_for_nr_mode(entry_of(legend='Operator'), 'SA')
    assert (single.chart_title, single.columns_split, single.legend) == ('SA DL Throughput', 'Operator', 'Operator')
    # A chart split by Campaign (whose SA campaigns name the mode) or by NR Mode is left as it is.
    for split in ('Operator × Campaign', 'Operator × NR Mode'):
        assert entry_for_nr_mode(entry_of(columns_split=split), 'NSA+SA').columns_split == split
    # A chart that keeps one NR Mode with its filters names that one.
    sa_chart = entry_for_nr_mode(entry_of(filters='NR Mode IN (SA)'), 'NSA+SA')
    assert (sa_chart.chart_title, sa_chart.slide_title, sa_chart.columns_split) == (
        'SA DL Throughput', 'FDFS DL (NSA & SA)', 'Operator')


def test_the_nr_modes_a_chart_keeps_with_its_filters():
    from src.modules.report_template_modes import chart_filter_nr_modes, design_nr_mode_value

    assert chart_filter_nr_modes(entry_of(filters='')) == ('NSA', 'SA')
    assert chart_filter_nr_modes(entry_of(filters='NR Mode IN (SA)')) == ('SA',)
    assert chart_filter_nr_modes(entry_of(filters='NR_Mode = NSA')) == ('NSA',)
    assert chart_filter_nr_modes(entry_of(filters='NR Mode NOT IN (NSA)')) == ('SA',)
    assert [design_nr_mode_value(value) for value in ('nsa', 'SA', 'NSA+SA', 'NSA & SA', None)] == [
        'NSA', 'SA', 'NSA+SA', 'NSA+SA', 'NSA']


def test_a_chart_says_which_nr_mode_has_no_samples_of_its_fields():
    from src.modules.report_template_modes import missing_nr_mode_fields, missing_nr_mode_note

    fields = {'NSA': {'meandatarate', 'operator', 'testresult', 'testname'}, 'SA': {'operator', 'testresult', 'testname'}}
    missing = missing_nr_mode_fields(entry_of(filters='Test_Result = Completed'), fields)
    assert missing == {'SA': ['Mean_Data_Rate']}
    assert missing_nr_mode_note(missing) == 'The SA CDRs have no Mean_Data_Rate: no SA samples.'
    # A chart of NSA alone, a Design of NSA alone and a field no CDR has say nothing.
    assert missing_nr_mode_fields(entry_of(filters='NR Mode IN (NSA)'), fields) == {}
    assert missing_nr_mode_fields(entry_of(), fields, 'NSA') == {}
    assert missing_nr_mode_fields(entry_of(kpi='Unknown_KPI'), fields) == {}


def test_combined_rows_keep_the_nr_mode_of_their_cdr(client, tmp_path):
    import pandas as pd

    repository = app_module.repository
    (tmp_path / 'sa.csv').write_text('test source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset('UK_Q3_SA_2026_Data.csv', str(tmp_path / 'sa.csv'), 'tester')
    repository.update_dataset_profile(dataset_id, dataset_kind='data', nr_mode='SA')
    repository.replace_dataset_rows(dataset_id, pd.DataFrame({'Operator': ['A', 'B'], 'Mean_Data_Rate': [10.0, 20.0]}))
    assert repository.copy_dataset_rows_to_reporting(dataset_id, 'data', ['Operator', 'Mean_Data_Rate']) == 'rows'
    rows = repository.load_reporting_rows('data', [dataset_id], ['Operator', 'NR Mode'])
    assert rows['NR Mode'].tolist() == ['SA', 'SA']
    # Nothing to do the next time; a CDR whose NR Mode is corrected takes it on its rows.
    assert repository.copy_dataset_rows_to_reporting(dataset_id, 'data', ['Operator']) is False
    repository.update_dataset_profile(dataset_id, nr_mode='NSA')
    assert repository.set_reporting_nr_mode(dataset_id, 'data') is True
    assert repository.load_reporting_rows('data', [dataset_id], ['NR_Mode'])['NR_Mode'].tolist() == ['NSA', 'NSA']
    # Rows filled before the column existed take it when it is requested.
    with repository.connection() as connection:
        connection.execute('UPDATE reporting_rows_data SET NR_Mode = NULL')
    assert repository.copy_dataset_rows_to_reporting(dataset_id, 'data', ['Operator']) == 'columns'
    assert repository.load_reporting_rows('data', [dataset_id], ['NR_Mode'])['NR_Mode'].tolist() == ['NSA', 'NSA']


def test_sa_series_take_a_lighter_tint_and_a_dash_of_their_operator():
    import pandas as pd

    from src.modules.cdr_reporting import _cdf_campaign_line_widths, _series_colours, _series_line_dashes

    frame = pd.DataFrame({'op': ['A'], 'mode': ['NSA']})
    frame.attrs['catalogue_dimension_labels'] = {'op': 'Operator', 'mode': 'NR Mode'}
    frame.attrs['operator_mapping_groups'] = []
    keys = [('A', 'NSA'), ('A', 'SA'), ('B', 'NSA'), ('B', 'SA')]
    colours = _series_colours(keys, ['op', 'mode'], frame, line_chart=True)
    assert colours[('A', 'NSA')] != colours[('B', 'NSA')]
    for operator in ('A', 'B'):
        nsa, sa = colours[(operator, 'NSA')], colours[(operator, 'SA')]
        assert sa != nsa and sum(int(sa[index:index + 2], 16) for index in (1, 3, 5)) > sum(int(nsa[index:index + 2], 16) for index in (1, 3, 5))
    dashes = _series_line_dashes(keys, ['op', 'mode'], frame)
    assert dashes[('A', 'NSA')] == () and dashes[('A', 'SA')]
    # The latest NSA and the latest SA campaigns of an operator are both drawn thick.
    widths = _cdf_campaign_line_widths(
        [(('A', 'NSA'), ['2026-Q1', '2026-Q2']), (('A', 'SA'), ['2026-Q3-SA'])], ['op', 'mode'], frame)
    assert widths[('A', 'SA')] == 4


def test_auto_comments_compare_each_operator_in_sa_with_itself_in_nsa():
    from src.modules.design_comments import ChartFacts, Record, chart_findings, kpi_semantics, slide_findings

    semantics = kpi_semantics('Mean Data Rate')
    records = [Record({'Operator': operator, 'NR Mode': mode}, value, 200)
               for operator, mode, value in (('A', 'NSA', 100.0), ('A', 'SA', 150.0), ('B', 'NSA', 90.0), ('B', 'SA', 80.0))]
    facts = ChartFacts(0, 'DL Throughput', 'stat', semantics, 'median', records, 1)
    texts = [finding.text for finding in chart_findings(facts, ['A'])]
    assert any('A' in text and 'higher in SA than in NSA' in text for text in texts), texts
    # Two charts of one slide, of NSA and of SA.
    nsa = ChartFacts(0, 'CDF_NSA', 'stat', semantics, 'median',
                     [Record({'Operator': 'A'}, 100.0, 200), Record({'Operator': 'B'}, 90.0, 200)], 1)
    sa = ChartFacts(1, 'CDF_SA', 'stat', semantics, 'median',
                    [Record({'Operator': 'A'}, 150.0, 200), Record({'Operator': 'B'}, 140.0, 200)], 1)
    texts = [finding.text for finding in slide_findings([nsa, sa])]
    assert any('better in SA than in NSA for every operator' in text for text in texts), texts


def add_data_cdr(tmp_path, name, nr_mode, campaign):
    import pandas as pd

    from src.modules.repository import local_now_iso

    repository = app_module.repository
    (tmp_path / name).write_text('test source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(tmp_path / name), 'super')
    rows = pd.DataFrame({'Operator': ['A', 'B'], 'Campaign': [campaign] * 2, 'Mean_Data_Rate': [10.0, 20.0],
                         'Transfer_Duration': [1.0, 2.0], 'Test_Result': ['Completed'] * 2,
                         'Test_Name': ['FDFS HTTPS DL ST'] * 2, 'Test_Start_Time': ['2026-09-01'] * 2})
    repository.replace_dataset_rows(dataset_id, rows)
    repository.update_dataset_profile(
        dataset_id, status='ready', progress=100, dataset_kind='data', nr_mode=nr_mode, cdr_stage='final', campaign=campaign,
        row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso(),
    )
    repository.copy_dataset_rows_to_reporting(dataset_id, 'data')
    return dataset_id


def test_a_chart_of_one_nr_mode_reads_only_the_cdrs_of_that_nr_mode(client, tmp_path, monkeypatch):
    import src.modules.ppt_designer as designs_module
    from src.modules.cdr_facets import fill_missing_facets

    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303
    nsa = add_data_cdr(tmp_path, 'nsa.csv', 'NSA', '2026-Q2')
    sa = add_data_cdr(tmp_path, 'sa.csv', 'SA', '2026-Q2-SA')
    fill_missing_facets(app_module.repository, [nsa, sa])
    definition = {'name': 'Both', 'template': 'DT Analyzer - FDFS DL (NSA & SA)', 'nr_mode': 'NSA+SA', 'auto_cdrs': True,
                  'filters': {'Campaign': ['@latest-campaign']}, 'sa_campaigns': ['@latest-campaign']}
    read = []
    for name in ('read_frame', 'read_grouped_frame'):
        def spy(cache, source, segments, *args, _original=getattr(designs_module, name), **kwargs):
            read.append({segment.dataset_id for segment in segments})
            return _original(cache, source, segments, *args, **kwargs)
        monkeypatch.setattr(designs_module, name, spy)
    prepared = client.post('/api/ppt-designer/prepare', json=definition)
    assert prepared.status_code == 200, prepared.text
    token = prepared.json()['token']
    charts = next(slide for slide in prepared.json()['slides'] if slide['charts'])['charts']
    datasets = {}
    for chart in charts:
        read.clear()
        drawn = client.get(f"/api/ppt-designer/chart/{token}/{chart['index']}")
        assert drawn.status_code == 200, drawn.text
        datasets[chart['title']] = set().union(*read)
    # CDF_NSA keeps NR Mode IN (NSA) and CDF_SA NR Mode IN (SA): each reads its own CDR; the chart of both reads both.
    assert datasets == {'CDF_NSA': {nsa}, 'CDF_SA': {sa}, 'Transfer time FDFS DL': {nsa, sa}}


def test_a_design_of_nsa_and_sa_reads_the_cdrs_of_each_nr_mode_by_its_campaigns(client, tmp_path):
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303
    nsa_q1 = add_data_cdr(tmp_path, 'q1.csv', 'NSA', '2026-Q1')
    nsa_q2 = add_data_cdr(tmp_path, 'q2.csv', 'NSA', '2026-Q2')
    sa_q2 = add_data_cdr(tmp_path, 'q2_sa.csv', 'SA', '2026-Q2-SA')
    sa_q3 = add_data_cdr(tmp_path, 'q3_sa.csv', 'SA', '2026-Q3-SA')
    definition = {'name': 'Comparison', 'template': 'DT Analyzer - FDFS DL (NSA & SA)', 'nr_mode': 'NSA+SA', 'auto_cdrs': True,
                  'filters': {'Campaign': ['@latest-campaign']}, 'sa_campaigns': ['@latest-2-campaigns']}
    from src.modules.cdr_facets import fill_missing_facets

    fill_missing_facets(app_module.repository, [nsa_q1, nsa_q2, sa_q2, sa_q3])
    automatic = client.post('/api/ppt-designer/auto-cdrs', json=definition)
    assert automatic.status_code == 200, automatic.text
    chosen = {row['id'] for row in automatic.json()['cdrs']['data']}
    assert chosen == {nsa_q2, sa_q2, sa_q3} and nsa_q1 not in chosen
    # The Campaign filter lists the NSA campaigns and SA Campaign the SA ones.
    assert automatic.json()['options']['Campaign'] == ['2026-Q1', '2026-Q2']
    assert automatic.json()['options']['SA Campaign'] == ['2026-Q2-SA', '2026-Q3-SA']

    prepared = client.post('/api/ppt-designer/prepare', json=definition)
    assert prepared.status_code == 200, prepared.text
    slide = next(slide for slide in prepared.json()['slides'] if slide['charts'])
    assert slide['title'] == 'FDFS DL Throughput and Transfer Time (NSA & SA)'
    assert [(chart['title'], chart['available']) for chart in slide['charts']] == [
        ('CDF_NSA', True), ('CDF_SA', True), ('Transfer time FDFS DL', True)]
    # In a Design of NSA alone, the chart of SA says why it shows nothing.
    prepared = client.post('/api/ppt-designer/prepare', json={**definition, 'nr_mode': 'NSA', 'sa_campaigns': []})
    charts = next(slide for slide in prepared.json()['slides'] if slide['charts'])['charts']
    assert charts[1]['available'] is False and 'shows the SA CDRs' in charts[1]['unavailable']


def test_lines_and_areas_of_both_nr_modes_draw_them_as_series_not_on_their_axis():
    from src.modules.report_template_modes import entry_for_nr_mode

    for chart_type in ('Lines', 'Dual Lines', 'Areas', '100% Stacked Areas', 'Bars and Line'):
        lines = entry_for_nr_mode(entry_of(chart_type=chart_type, rows_split='', columns_split='Hour', legend=''), 'NSA+SA')
        assert (lines.rows_split, lines.columns_split) == ('NR Mode', 'Hour'), chart_type
    # The other charts keep it in the split of their legend, or their Columns without one.
    bars = entry_for_nr_mode(entry_of(chart_type='Average Vertical Bars', rows_split='', columns_split='Hour', legend=''), 'NSA+SA')
    assert (bars.rows_split, bars.columns_split) == ('', 'Hour × NR Mode')
