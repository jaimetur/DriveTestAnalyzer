"""Dashboard Designer (ticket #26): the Design of a template, the overrides of a Dashboard and their API."""
import copy
import csv
import json
from dataclasses import replace
from io import BytesIO, StringIO
from pathlib import Path

import pytest

import src.DriveTestAnalyzer as core
from src.modules import dashboard_design as dd
from src.modules.cdr_reporting import catalogue_csv, parse_catalog_csv
from src.modules.report_layouts import csv_with_design_ids

TEMPLATES = Path(__file__).parents[1] / 'assets' / 'ppt-templates'


def visible(design):
    """The slides and elements a resolved Design shows, without the marks of the resolution."""
    marks = {'origin', 'overridden'}
    return [
        {**{key: value for key, value in slide.items() if key not in marks},
         'elements': [{key: value for key, value in element.items() if key not in marks}
                      for element in slide.get('elements') or [] if not element.get('hidden')]}
        for slide in design['slides']
    ]


@pytest.mark.parametrize('path', sorted(TEMPLATES.glob('*.csv')), ids=lambda path: path.stem)
def test_every_starter_template_reads_back_the_same_through_its_design(path):
    entries = parse_catalog_csv(path.read_bytes())
    design = dd.design_from_entries(entries)
    assert catalogue_csv([replace(entry, format='') for entry in dd.entries_from_design(design)]) == catalogue_csv(entries)
    # Ids stored once are the positional ones the template was read with, and read back the same.
    stored = parse_catalog_csv(catalogue_csv(dd.with_design_ids(entries)))
    assert dd.design_from_entries(stored) == design
    assert dd.entries_from_design(dd.design_from_entries(stored)) == stored


def test_the_format_column_is_optional_and_must_hold_a_json_object():
    content = (TEMPLATES / 'FDFS DL (NSA & SA).csv').read_bytes()
    assert not catalogue_csv(parse_catalog_csv(content)).split(b'\n')[0].endswith(b',Format')
    with_ids = catalogue_csv(dd.with_design_ids(parse_catalog_csv(content)))
    assert with_ids.split(b'\n')[0].endswith(b',Format')
    broken = with_ids.replace(b'"{""slide""', b'"[""slide""', 1)
    with pytest.raises(ValueError, match='Format must be a JSON object'):
        parse_catalog_csv(broken)


def test_rows_copied_in_the_table_take_ids_of_their_own():
    entries = dd.with_design_ids(parse_catalog_csv((TEMPLATES / 'NetCheck CDR Report.csv').read_bytes()))
    rows = list(csv.reader(StringIO(catalogue_csv(entries).decode())))
    chart_row = next(index for index, entry in enumerate(entries, start=1) if not entry.structural_type)
    # A chart row duplicated into its slide, and a row without ids added to it.
    edited = rows[:chart_row + 1] + [list(rows[chart_row]), rows[chart_row][:-1] + ['']] + rows[chart_row + 1:]
    output = StringIO()
    csv.writer(output, lineterminator='\n').writerows(edited)
    fixed = parse_catalog_csv(csv_with_design_ids(output.getvalue().encode()))
    ids = [dd.row_format(entry).get('id') for entry in fixed if not entry.structural_type]
    assert all(ids) and len(set(ids)) == len(ids)
    # The rows of before keep theirs.
    assert {dd.row_format(entry).get('id') for entry in entries if not entry.structural_type} <= set(ids)
    assert dd.row_format(fixed[chart_row - 1]).get('id') == dd.row_format(entries[chart_row - 1]).get('id')


def netcheck_design():
    return dd.design_from_entries(dd.with_design_ids(parse_catalog_csv((TEMPLATES / 'NetCheck CDR Report.csv').read_bytes())))


def test_a_dashboard_keeps_only_what_it_changes_and_follows_the_rest_of_its_template():
    template = netcheck_design()
    shown, report = dd.resolve_design(template, None)
    assert report == {'dropped': [], 'template_changed': []}
    edited = copy.deepcopy(shown)
    content = [slide for slide in edited['slides'] if slide['kind'] == 'content']
    content[0]['title'] = 'Voice in London'
    content[1]['hidden'] = True
    chart = content[2]['elements'][0]
    chart['filters'] = dd.join_conditions(dd.filter_conditions(chart['filters']) + ['City IN (London)'])
    hidden_element = content[3]['elements'].pop()['id']
    local = {'id': 'slocal', 'kind': 'content', 'title': 'Only here', 'subtitle': '', 'layout': content[0]['layout'],
             'optional': False, 'elements': [dict(content[0]['elements'][0], id='elocal')]}
    edited['slides'].insert(edited['slides'].index(content[4]) + 1, local)

    overrides = dd.overrides_between(template, edited)
    assert dd.overrides_summary(overrides) == {
        'slide_properties': 1, 'element_properties': 0, 'chart_filters': 1, 'hidden_slides': 1,
        'shown_optional_slides': 0, 'hidden_elements': 1, 'local_slides': 1, 'local_elements': 0,
    }
    assert overrides['filters'][chart['id']] == {'add': ['City IN (London)'], 'remove': []}
    assert overrides['hidden_elements'] == [hidden_element]
    assert overrides['local_slides'][0]['after'] == content[4]['id']
    assert visible(dd.resolve_design(template, overrides)[0]) == visible(edited)
    # The hidden slide is left out of the rows.
    assert len(dd.entries_from_design(dd.resolve_design(template, overrides)[0])) == len(dd.entries_from_design(shown)) - len(content[1]['elements'])

    # A template change reaches the Dashboard unless it changed that same thing: then it is flagged.
    changed = copy.deepcopy(template)
    changed_content = [slide for slide in changed['slides'] if slide['kind'] == 'content']
    changed_content[0]['title'] = 'Completed calls'
    changed_content[5]['title'] = 'Renamed in the template'
    template_chart = changed_content[2]['elements'][0]
    template_chart['filters'] = dd.join_conditions(dd.filter_conditions(template_chart['filters']) + ['Operator IN (A)'])
    resolved, report = dd.resolve_design(changed, overrides)
    titles = {slide['id']: slide['title'] for slide in resolved['slides']}
    assert titles[content[0]['id']] == 'Voice in London'
    assert titles[changed_content[5]['id']] == 'Renamed in the template'
    assert 'Operator IN (A)' in dd.filter_conditions(next(
        element for slide in resolved['slides'] for element in slide.get('elements') or [] if element['id'] == chart['id'])['filters'])
    assert [(item.get('slide'), item['property']) for item in report['template_changed']] == [(content[0]['id'], 'title')]
    # Keep mine stops flagging it; Reset to template takes the template value.
    assert dd.resolve_design(changed, dd.keep_overrides(overrides, changed))[1]['template_changed'] == []
    reset = dd.drop_override(overrides, slide=content[0]['id'], name='title')
    assert {slide['id']: slide['title'] for slide in dd.resolve_design(changed, reset)[0]['slides']}[content[0]['id']] == 'Completed calls'
    # What the template deleted is reported, and the overrides of it can be left out.
    removed = copy.deepcopy(changed)
    removed['slides'] = [slide for slide in removed['slides'] if slide['id'] != content[1]['id']]
    assert {'slide': content[1]['id']} in dd.resolve_design(removed, overrides)[1]['dropped']
    assert content[1]['id'] not in dd.without_dropped(overrides, removed)['hidden_slides']


def test_optional_template_slides_are_shown_only_where_switched_on():
    template = netcheck_design()
    optional = next(slide for slide in template['slides'] if slide['kind'] == 'content')
    optional['optional'] = True
    position = template['slides'].index(optional)
    shown, _report = dd.resolve_design(template, None)
    assert shown['slides'][position]['optional_off'] is True
    assert len(dd.entries_from_design(shown)) == len(dd.entries_from_design(template)) - len(optional['elements'])
    edited = copy.deepcopy(shown)
    edited['slides'][position].pop('optional_off')
    overrides = dd.overrides_between(template, edited)
    assert overrides['shown_optional'] == [optional['id']]
    assert not dd.resolve_design(template, overrides)[0]['slides'][position].get('optional_off')
    # The flag travels in the Format column.
    assert dd.design_from_entries(parse_catalog_csv(dd.design_csv(template)))['slides'][position]['optional'] is True


def test_parameters_fill_filters_titles_and_settings_and_all_leaves_the_condition_out():
    parameters = dd.validate_parameters([
        {'name': 'City', 'type': 'values', 'field': 'City'},
        {'name': 'Threshold', 'type': 'number', 'default': 1.6},
    ])
    template = netcheck_design()
    template['parameters'] = parameters
    chart = next(slide for slide in template['slides'] if slide['kind'] == 'content')['elements'][0]
    chart['filters'] = dd.join_conditions(dd.filter_conditions(chart['filters']) + ['City IN ({City})', 'LQ < {Threshold}'])
    chart['chart_title'] = 'Calls in {City}'
    stored = parse_catalog_csv(dd.design_csv(template))
    assert dd.design_from_entries(stored)['parameters'] == parameters
    index = next(position for position, entry in enumerate(stored) if dd.row_format(entry).get('id') == chart['id'])
    every_city = dd.apply_parameters(stored, parameters, {})[index]
    assert 'City' not in every_city.filters and 'LQ < 1.6' in every_city.filters
    assert every_city.chart_title == 'Calls in All'
    two = dd.apply_parameters(stored, parameters, {parameters[0]['id']: ['London', 'Leeds'], parameters[1]['id']: 2})[index]
    assert 'City IN (London, Leeds)' in two.filters and 'LQ < 2' in two.filters
    assert two.chart_title == 'Calls in London, Leeds'
    assert dd.parameter_uses(template, 'city') and not dd.parameter_uses(template, 'Region')
    renamed = next(element for slide in dd.rename_parameter(template, 'City', 'Town')['slides']
                   for element in slide['elements'] if element['id'] == chart['id'])
    assert 'City IN ({Town})' in renamed['filters'] and renamed['chart_title'] == 'Calls in {Town}'
    with pytest.raises(ValueError, match='built-in token'):
        dd.validate_parameters([{'name': 'NR Mode', 'type': 'text'}])
    with pytest.raises(ValueError, match='Two parameters'):
        dd.validate_parameters([{'name': 'A', 'type': 'text'}, {'name': 'a', 'type': 'text'}])


# --------------------------------------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------------------------------------

TEMPLATE = (
    'Slide,Slide tittle,Slide Subtittle,Layout,Chart Tittle,CDR source,KPI,Chart type,Filters,Rows Split,Columns Split,Legend,Legend Position\n'
    '1,Comparison,,Title and 2 columns + Comments,Rate,CDR-Data,Mean_Data_Rate,CDF Line,,Operator,,,Top\n'
    '1,Comparison,,Title and 2 columns + Comments,Rate again,CDR-Data,Mean_Data_Rate,CDF Line,,Operator,,,Top\n'
    '2,Next,,Title and 1 column + Comments,Rate next,CDR-Data,Mean_Data_Rate,CDF Line,,Operator,,,Top\n'
)


def login(client, username='super', password='super123'):
    client.cookies.clear()
    assert client.post('/login', data={'username': username, 'password': password}, follow_redirects=False).status_code == 303


def setup(client, *, created_by='super'):
    login(client)
    response = client.post('/datasets-analysis/upload', data={'dataset_kinds': 'data'}, files={
        'dataset_files': ('sample.csv', BytesIO(b'Operator,City,Mean_Data_Rate,Test_Name,Test_Start_Time\nA,London,10,HTTP DL,2026-09-01\nB,Leeds,20,HTTP DL,2026-09-02\nA,London,30,HTTP DL,2026-09-03\n'), 'text/csv'),
    })
    assert response.status_code == 200
    core.repository.add_report_template('Design test', TEMPLATE.encode(), updated_by=created_by)
    definition = {'name': 'Design dashboard', 'template': 'Design test', 'nr_mode': 'NSA', 'datasets': {'data': [1]}}
    for dashboard_id, name in (('design-a', 'Design dashboard'), ('design-b', 'Design sibling')):
        saved = client.put(f'/api/ppt-dashboards/{dashboard_id}', json={**definition, 'name': name})
        assert saved.status_code == 200, saved.text
    return definition


def logged(action):
    return [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == action]


def stored(dashboard_id):
    return json.loads(core.repository.get_workspace_state('ppt_dashboards_v2'))[dashboard_id]


def test_the_designer_reads_saves_and_previews_a_dashboard_design(client):
    definition = setup(client)
    assert client.get('/api/ppt-dashboards/design-a/design').status_code == 200
    # Reading it alone leaves the template as it is; entering Design gives it ids of its own.
    assert b'Format' not in core.repository.report_template_content('Design test').split(b'\n', 1)[0]
    read = client.get('/api/ppt-dashboards/design-a/design?edit=1')
    assert read.status_code == 200, read.text
    body = read.json()
    assert body['rights'] == {'dashboard': True, 'template': True}
    assert [slide['title'] for slide in body['design']['slides']] == ['Comparison', 'Next']
    assert {item['id'] for item in body['template']['dashboards']} >= {'design-a', 'design-b'}
    # Reading it gave the template ids of its own (the positional ones it was read with).
    assert b',Format\n' in core.repository.report_template_content('Design test').split(b'\n', 1)[0] + b'\n'
    assert logged('report_template_design_ids_assigned')[-1]['template'] == 'Design test'

    prepared = client.post('/api/ppt-dashboards/prepare', json=definition)
    assert prepared.status_code == 200, prepared.text
    edited = copy.deepcopy(body['design'])
    edited['slides'][0]['title'] = 'Comparison in London'
    edited['slides'][1]['hidden'] = True
    preview = client.post('/api/ppt-dashboards/design/preview', json={
        'token': prepared.json()['token'], 'design': edited, 'overrides': body['overrides']})
    assert preview.status_code == 200, preview.text
    assert [slide['title'] for slide in preview.json()['slides']] == ['Comparison in London']
    assert preview.json()['summary']['hidden_slides'] == 1
    chart = client.get(f"/api/ppt-dashboards/chart/{preview.json()['token']}/0")
    assert chart.status_code == 200, chart.text

    saved = client.put('/api/ppt-dashboards/design-a/design', json={'design': edited, 'overrides': body['overrides']})
    assert saved.status_code == 200, saved.text
    assert saved.json()['summary']['slide_properties'] == 1 and saved.json()['summary']['hidden_slides'] == 1
    assert logged('dashboard_design_saved')[-1]['overrides']['hidden_slides'] == 1
    # Saving its filters from a viewer opened before keeps its Design; its sibling follows the template as it is.
    assert client.put('/api/ppt-dashboards/design-a', json={**definition, 'filters': {'City': ['London']}}).status_code == 200
    assert stored('design-a')['design_overrides']['hidden_slides']
    mine = client.post('/api/ppt-dashboards/prepare', json={**definition, 'design_overrides': stored('design-a')['design_overrides']})
    assert [slide['title'] for slide in mine.json()['slides']] == ['Comparison in London']
    sibling = client.post('/api/ppt-dashboards/prepare', json={**definition, 'name': 'Design sibling'})
    assert [slide['title'] for slide in sibling.json()['slides']] == ['Comparison', 'Next']

    # A template change reaches both, except what design-a changed itself.
    template = copy.deepcopy(saved.json()['template']['design'])
    template['slides'][0]['title'] = 'Comparison of operators'
    template['slides'][1]['subtitle'] = 'From the template'
    changed = client.put('/api/ppt-dashboards/design-b/design', json={
        'template_design': template, 'template_updated_at': saved.json()['template']['updated_at']})
    assert changed.status_code == 200, changed.text
    assert [slide['title'] for slide in changed.json()['design']['slides']] == ['Comparison of operators', 'Next']
    again = client.get('/api/ppt-dashboards/design-a/design').json()
    assert again['design']['slides'][0]['title'] == 'Comparison in London'
    assert again['report']['template_changed'][0]['property'] == 'title'
    # The template it was read from changed: a stale Designer is refused.
    stale = client.put('/api/ppt-dashboards/design-b/design', json={
        'template_design': template, 'template_updated_at': saved.json()['template']['updated_at']})
    assert stale.status_code == 409


def test_detach_save_as_template_and_deleting_a_template_keep_every_dashboard_working(client):
    definition = setup(client)
    body = client.get('/api/ppt-dashboards/design-a/design?edit=1').json()
    edited = copy.deepcopy(body['design'])
    edited['slides'][0]['title'] = 'Mine'
    assert client.put('/api/ppt-dashboards/design-a/design', json={'design': edited}).status_code == 200

    copy_response = client.post('/api/ppt-dashboards/design-a/design/save-as-template', json={'name': 'Design copy'})
    assert copy_response.status_code == 200, copy_response.text
    copied = core.load_template_catalogue(core.repository.report_template_content('Design copy'))
    assert copied[0].slide_title == 'Mine'
    assert client.post('/api/ppt-dashboards/design-a/design/save-as-template', json={'name': 'design copy'}).status_code == 409

    detached = client.post('/api/ppt-dashboards/design-a/design/detach')
    assert detached.status_code == 200, detached.text
    assert detached.json()['detached'] is True and stored('design-a')['design']['slides'][0]['title'] == 'Mine'

    # Deleting the template detaches the Dashboards still following it.
    assert client.post('/workspace-config/report-templates/Design test/delete', follow_redirects=False).status_code == 303
    assert stored('design-b')['design']['slides'][0]['title'] == 'Comparison'
    assert logged('delete_report_template')[-1]['detached_dashboards'] == 1
    for name in ('Design dashboard', 'Design sibling'):
        dashboard_id = 'design-a' if name == 'Design dashboard' else 'design-b'
        prepared = client.post('/api/ppt-dashboards/prepare', json={**definition, 'name': name, 'design': stored(dashboard_id)['design']})
        assert prepared.status_code == 200, prepared.text


def test_a_user_editor_designs_only_what_they_created(client):
    setup(client)
    user_id = core.repository.create_user('editor', 'secret123', 'user-editor')
    core.repository.set_user_workspace_access(user_id, [core.active_workspace.id])
    profile_id = next(item['id'] for item in core.repository.list_modules_profiles() if item['name'] == 'All Modules')
    core.repository.set_users_modules_profile([user_id], profile_id)
    core.invalidate_module_access_cache()
    login(client, 'editor', 'secret123')
    body = client.get('/api/ppt-dashboards/design-a/design?edit=1').json()
    assert body['rights'] == {'dashboard': False, 'template': False}
    assert client.put('/api/ppt-dashboards/design-a/design', json={'design': body['design']}).status_code == 403
    assert client.put('/api/ppt-dashboards/design-a/design', json={'template_design': body['template']['design']}).status_code == 403
    # Their own Dashboard: its Design yes, the template of another user no.
    assert client.put('/api/ppt-dashboards/mine', json={'name': 'Mine', 'template': 'Design test'}).status_code == 200
    mine = client.get('/api/ppt-dashboards/mine/design?edit=1').json()
    assert mine['rights'] == {'dashboard': True, 'template': False}
    assert client.put('/api/ppt-dashboards/mine/design', json={'design': mine['design']}).status_code == 200
    saved = client.post('/workspace-config/report-templates/Design test/save', data={'catalogue_content': TEMPLATE},
                        headers={'accept': 'application/json'})
    assert saved.status_code == 403


def test_a_template_slide_missing_from_the_edited_design_is_hidden_not_brought_back():
    template = netcheck_design()
    shown, _report = dd.resolve_design(template, None)
    edited = copy.deepcopy(shown)
    dropped = edited['slides'].pop(2)
    overrides = dd.overrides_between(template, edited)
    assert overrides['hidden_slides'] == [dropped['id']]
    assert dropped['id'] not in [slide['id'] for slide in dd.resolve_design(template, overrides)[0]['slides'] if not slide.get('hidden')]


def test_drafts_layouts_and_previews_after_detaching(client):
    definition = setup(client)
    layouts = client.get('/api/ppt-dashboards/design/layouts')
    assert layouts.status_code == 200, layouts.text
    grid = next(layout for layout in layouts.json()['layouts'] if layout['name'] == 'Title + 1 rows + 2 columns + comments down')
    assert grid['grid'] == [1, 2] and len(grid['places']) == 2
    body = client.get('/api/ppt-dashboards/design-a/design?edit=1').json()
    # A draft is kept per user until it is saved or discarded (App Events).
    assert client.get('/api/ppt-dashboards/design-a/design/draft').json() == {'draft': None}
    assert client.put('/api/ppt-dashboards/design-a/design/draft', json={'state': {'design': body['design']}}).status_code == 200
    assert client.get('/api/ppt-dashboards/design-a/design/draft').json()['draft']['design'] == body['design']
    assert client.delete('/api/ppt-dashboards/design-a/design/draft?discarded=1').json() == {'deleted': True}
    assert logged('dashboard_design_draft_discarded')[-1] == {'id': 'design-a', 'draft': True}
    # A preview starts from the Design saved now, even on a selection prepared before it was detached.
    prepared = client.post('/api/ppt-dashboards/prepare', json=definition).json()
    assert client.post('/api/ppt-dashboards/design-a/design/detach').status_code == 200
    own = client.get('/api/ppt-dashboards/design-a/design?edit=1').json()['design']
    own['slides'] = own['slides'][:1]
    own['slides'][0]['title'] = 'Only mine'
    preview = client.post('/api/ppt-dashboards/design/preview', json={'token': prepared['token'], 'dashboard_id': 'design-a', 'design': own})
    assert preview.status_code == 200, preview.text
    assert [slide['title'] for slide in preview.json()['slides']] == ['Only mine']
    assert client.put('/api/ppt-dashboards/design-a/design', json={'design': own}).status_code == 200
    assert [slide['title'] for slide in stored('design-a')['design']['slides']] == ['Only mine']
    fields = client.get(f"/api/ppt-dashboards/design/fields?token={preview.json()['token']}")
    assert fields.status_code == 200 and 'Mean_Data_Rate' in fields.json()['columns_by_source']['cdr-data']


def test_the_chart_builder_reads_fields_and_values_and_adds_a_chart_to_a_dashboard(client):
    definition = setup(client)
    token = client.post('/api/ppt-dashboards/prepare', json=definition).json()['token']
    fields = client.get(f'/api/ppt-dashboards/design/fields?token={token}').json()['fields']['cdr-data']
    assert {'name': 'Operator', 'type': 'text', 'category': 'CDR-Main fields'} in fields or any(item['name'] == 'Operator' for item in fields)
    values = client.get(f'/api/ppt-dashboards/design/values?token={token}&source=CDR-Data&field=Operator')
    assert values.status_code == 200, values.text
    assert values.json()['values'] == [{'value': 'A', 'count': 2}, {'value': 'B', 'count': 1}]
    targets = client.get('/api/ppt-dashboards/design/targets').json()['dashboards']
    target = next(item for item in targets if item['id'] == 'design-a')
    assert [slide['title'] for slide in target['slides']] == ['Comparison', 'Next'] and target['slides'][0]['free'] == 0
    chart = {'chart_title': 'Rate by city', 'cdr_source': 'CDR-Data', 'kpi': 'Mean_Data_Rate', 'chart_type': 'Average Vertical Bars',
             'rows_split': 'City', 'columns_split': '', 'legend': '', 'filters': 'Operator IN (A)', 'legend_position': 'Top'}
    full = client.post('/api/ppt-dashboards/design-a/design/add-chart', json={'element': chart, 'slide_id': target['slides'][0]['id']})
    assert full.status_code == 409
    added = client.post('/api/ppt-dashboards/design-a/design/add-chart', json={'element': chart})
    assert added.status_code == 200, added.text
    assert added.json() == {'dashboard': 'Design dashboard', 'slide': 'Rate by city'}
    assert stored('design-a')['design_overrides']['local_slides'][0]['slide']['elements'][0]['kpi'] == 'Mean_Data_Rate'
    assert logged('dashboard_chart_added')[-1]['new_slide'] is True
    prepared = client.post('/api/ppt-dashboards/prepare?dashboard_id=design-a', json=definition)
    assert [slide['title'] for slide in prepared.json()['slides']] == ['Comparison', 'Next', 'Rate by city']
    # Chart Builder reads the same fields and values from the CDRs chosen.
    builder_fields = client.post('/api/chart-builder/fields', json={'dataset_ids': [1]}).json()['fields']
    assert any(item['name'] == 'Mean_Data_Rate' for item in builder_fields)
    builder_values = client.post('/api/chart-builder/values', json={'dataset_ids': [1], 'field': 'City'}).json()['values']
    assert builder_values == [{'value': 'London', 'count': 2}, {'value': 'Leeds', 'count': 1}]


def test_the_format_of_a_chart_travels_in_its_row_and_reaches_its_model(client):
    definition = setup(client)
    body = client.get('/api/ppt-dashboards/design-a/design?edit=1').json()
    edited = copy.deepcopy(body['design'])
    style = {'series': {'A': {'colour': '#FF0000', 'width': 3, 'dash': 'dashed'}}, 'legend': {'position': 'bottom'},
             'axes': {'x': {'title': 'Rate (Mbit/s)', 'decimals': 0}}}
    edited['slides'][0]['elements'][0]['style'] = style
    assert client.put('/api/ppt-dashboards/design-a/design', json={'design': edited}).status_code == 200
    assert stored('design-a')['design_overrides']['elements']['s1e1']['style']['value'] == style
    prepared = client.post('/api/ppt-dashboards/prepare?dashboard_id=design-a', json=definition).json()
    chart = next(chart for chart in prepared['slides'][0]['charts'] if chart['element'] == 's1e1')
    model = client.get(f"/api/ppt-dashboards/chart/{prepared['token']}/{chart['index']}").json()
    assert model['format_overrides'] == style
    # In Template scope it is written in the Format column of the row.
    template = copy.deepcopy(body['template']['design'])
    template['slides'][0]['elements'][1]['style'] = {'labels': {'colour': '#123456'}}
    assert client.put('/api/ppt-dashboards/design-b/design', json={'template_design': template}).status_code == 200
    rows = parse_catalog_csv(core.repository.report_template_content('Design test'))
    assert dd.row_format(rows[1])['style'] == {'labels': {'colour': '#123456'}}
