"""Designer (ticket #26): the Design of a template, the overrides of a Design and their API."""
import copy
import csv
import json
from dataclasses import replace
from io import BytesIO, StringIO
from pathlib import Path

import pytest

import src.DriveTestAnalyzer as core
from src.modules import design_slides as dd
from src.modules.cdr_reporting import catalogue_csv, parse_catalog_csv
from src.modules.report_layouts import csv_with_slide_ids

TEMPLATES = Path(__file__).parents[1] / 'assets' / 'ppt-templates'


def visible(slide_set):
    """The slides and elements a resolved Design shows, without the marks of the resolution."""
    marks = {'origin', 'overridden'}
    return [
        {**{key: value for key, value in slide.items() if key not in marks},
         'elements': [{key: value for key, value in element.items() if key not in marks}
                      for element in slide.get('elements') or [] if not element.get('hidden')]}
        for slide in slide_set['slides']
    ]


@pytest.mark.parametrize('path', sorted(TEMPLATES.glob('*.csv')), ids=lambda path: path.stem)
def test_every_starter_template_reads_back_the_same_through_its_design(path):
    entries = parse_catalog_csv(path.read_bytes())
    slide_set = dd.slides_from_entries(entries)
    read = dd.entries_from_slides(slide_set)
    assert catalogue_csv([replace(entry, format='') for entry in read]) == catalogue_csv([replace(entry, format='') for entry in entries])
    # What a row keeps in its Format (a KPI card) reads back too, beside the ids of its slide and place.
    for entry, back in zip(entries, read, strict=True):
        assert json.loads(entry.format or '{}').items() <= json.loads(back.format or '{}').items()
    # Ids stored once are the positional ones the template was read with, and read back the same.
    stored = parse_catalog_csv(catalogue_csv(dd.with_slide_ids(entries)))
    assert dd.slides_from_entries(stored) == slide_set
    assert dd.entries_from_slides(dd.slides_from_entries(stored)) == stored


def test_the_format_column_is_optional_and_must_hold_a_json_object():
    content = (TEMPLATES / 'FDFS DL (NSA & SA).csv').read_bytes()
    assert not catalogue_csv(parse_catalog_csv(content)).split(b'\n')[0].endswith(b',Format')
    with_ids = catalogue_csv(dd.with_slide_ids(parse_catalog_csv(content)))
    assert with_ids.split(b'\n')[0].endswith(b',Format')
    broken = with_ids.replace(b'"{""slide""', b'"[""slide""', 1)
    with pytest.raises(ValueError, match='Format must be a JSON object'):
        parse_catalog_csv(broken)


def test_rows_copied_in_the_table_take_ids_of_their_own():
    entries = dd.with_slide_ids(parse_catalog_csv((TEMPLATES / 'NetCheck CDR Report.csv').read_bytes()))
    rows = list(csv.reader(StringIO(catalogue_csv(entries).decode())))
    chart_row = next(index for index, entry in enumerate(entries, start=1) if not entry.structural_type)
    # A chart row duplicated into its slide, and a row without ids added to it.
    edited = rows[:chart_row + 1] + [list(rows[chart_row]), rows[chart_row][:-1] + ['']] + rows[chart_row + 1:]
    output = StringIO()
    csv.writer(output, lineterminator='\n').writerows(edited)
    fixed = parse_catalog_csv(csv_with_slide_ids(output.getvalue().encode()))
    ids = [dd.row_format(entry).get('id') for entry in fixed if not entry.structural_type]
    assert all(ids) and len(set(ids)) == len(ids)
    # The rows of before keep theirs.
    assert {dd.row_format(entry).get('id') for entry in entries if not entry.structural_type} <= set(ids)
    assert dd.row_format(fixed[chart_row - 1]).get('id') == dd.row_format(entries[chart_row - 1]).get('id')


def netcheck_slide_set():
    return dd.slides_from_entries(dd.with_slide_ids(parse_catalog_csv((TEMPLATES / 'NetCheck CDR Report.csv').read_bytes())))


def test_a_design_keeps_only_what_it_changes_and_follows_the_rest_of_its_template():
    template = netcheck_slide_set()
    shown, report = dd.resolve_slides(template, None)
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
    assert visible(dd.resolve_slides(template, overrides)[0]) == visible(edited)
    # The hidden slide is left out of the rows.
    assert len(dd.entries_from_slides(dd.resolve_slides(template, overrides)[0])) == len(dd.entries_from_slides(shown)) - len(content[1]['elements'])

    # A template change reaches the Design unless it changed that same thing: then it is flagged.
    changed = copy.deepcopy(template)
    changed_content = [slide for slide in changed['slides'] if slide['kind'] == 'content']
    changed_content[0]['title'] = 'Completed calls'
    changed_content[5]['title'] = 'Renamed in the template'
    template_chart = changed_content[2]['elements'][0]
    template_chart['filters'] = dd.join_conditions(dd.filter_conditions(template_chart['filters']) + ['Operator IN (A)'])
    resolved, report = dd.resolve_slides(changed, overrides)
    titles = {slide['id']: slide['title'] for slide in resolved['slides']}
    assert titles[content[0]['id']] == 'Voice in London'
    assert titles[changed_content[5]['id']] == 'Renamed in the template'
    assert 'Operator IN (A)' in dd.filter_conditions(next(
        element for slide in resolved['slides'] for element in slide.get('elements') or [] if element['id'] == chart['id'])['filters'])
    assert [(item.get('slide'), item['property']) for item in report['template_changed']] == [(content[0]['id'], 'title')]
    # Keep mine stops flagging it; Reset to template takes the template value.
    assert dd.resolve_slides(changed, dd.keep_overrides(overrides, changed))[1]['template_changed'] == []
    reset = dd.drop_override(overrides, slide=content[0]['id'], name='title')
    assert {slide['id']: slide['title'] for slide in dd.resolve_slides(changed, reset)[0]['slides']}[content[0]['id']] == 'Completed calls'
    # What the template deleted is reported, and the overrides of it can be left out.
    removed = copy.deepcopy(changed)
    removed['slides'] = [slide for slide in removed['slides'] if slide['id'] != content[1]['id']]
    assert {'slide': content[1]['id']} in dd.resolve_slides(removed, overrides)[1]['dropped']
    assert content[1]['id'] not in dd.without_dropped(overrides, removed)['hidden_slides']


def test_optional_template_slides_are_shown_only_where_switched_on():
    template = netcheck_slide_set()
    optional = next(slide for slide in template['slides'] if slide['kind'] == 'content')
    optional['optional'] = True
    position = template['slides'].index(optional)
    shown, _report = dd.resolve_slides(template, None)
    assert shown['slides'][position]['optional_off'] is True
    assert len(dd.entries_from_slides(shown)) == len(dd.entries_from_slides(template)) - len(optional['elements'])
    edited = copy.deepcopy(shown)
    edited['slides'][position].pop('optional_off')
    overrides = dd.overrides_between(template, edited)
    assert overrides['shown_optional'] == [optional['id']]
    assert not dd.resolve_slides(template, overrides)[0]['slides'][position].get('optional_off')
    # The flag travels in the Format column.
    assert dd.slides_from_entries(parse_catalog_csv(dd.slides_csv(template)))['slides'][position]['optional'] is True


def test_parameters_fill_filters_titles_and_settings_and_all_leaves_the_condition_out():
    parameters = dd.validate_parameters([
        {'name': 'City', 'type': 'values', 'field': 'City'},
        {'name': 'Threshold', 'type': 'number', 'default': 1.6},
    ])
    template = netcheck_slide_set()
    template['parameters'] = parameters
    chart = next(slide for slide in template['slides'] if slide['kind'] == 'content')['elements'][0]
    chart['filters'] = dd.join_conditions(dd.filter_conditions(chart['filters']) + ['City IN ({City})', 'LQ < {Threshold}'])
    chart['chart_title'] = 'Calls in {City}'
    stored = parse_catalog_csv(dd.slides_csv(template))
    assert dd.slides_from_entries(stored)['parameters'] == parameters
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
    with pytest.raises(ValueError, match='built-in token'):
        dd.validate_parameters([{'name': 'Cities', 'type': 'text'}])
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
    definition = {'name': 'Design one', 'template': 'Design test', 'nr_mode': 'NSA', 'datasets': {'data': [1]}}
    for design_id, name in (('design-a', 'Design one'), ('design-b', 'Design sibling')):
        saved = client.put(f'/api/ppt-designer/{design_id}', json={**definition, 'name': name})
        assert saved.status_code == 200, saved.text
    return definition


def logged(action):
    return [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == action]


def stored(design_id):
    return json.loads(core.repository.get_workspace_state('ppt_designs_v2'))[design_id]


def test_the_designer_reads_saves_and_previews_a_design_slides(client):
    definition = setup(client)
    assert client.get('/api/ppt-designer/design-a/slides').status_code == 200
    # Reading it alone leaves the template as it is; entering Design gives it ids of its own.
    assert b'Format' not in core.repository.report_template_content('Design test').split(b'\n', 1)[0]
    read = client.get('/api/ppt-designer/design-a/slides?edit=1')
    assert read.status_code == 200, read.text
    body = read.json()
    assert body['rights'] == {'design': True, 'template': True}
    assert [slide['title'] for slide in body['slide_set']['slides']] == ['Comparison', 'Next']
    assert {item['id'] for item in body['template']['designs']} >= {'design-a', 'design-b'}
    # Reading it gave the template ids of its own (the positional ones it was read with).
    assert b',Format\n' in core.repository.report_template_content('Design test').split(b'\n', 1)[0] + b'\n'
    assert logged('report_template_slide_ids_assigned')[-1]['template'] == 'Design test'

    prepared = client.post('/api/ppt-designer/prepare', json=definition)
    assert prepared.status_code == 200, prepared.text
    edited = copy.deepcopy(body['slide_set'])
    edited['slides'][0]['title'] = 'Comparison in London'
    edited['slides'][1]['hidden'] = True
    preview = client.post('/api/ppt-designer/slides/preview', json={
        'token': prepared.json()['token'], 'slide_set': edited, 'overrides': body['overrides']})
    assert preview.status_code == 200, preview.text
    assert [slide['title'] for slide in preview.json()['slides']] == ['Comparison in London']
    assert preview.json()['summary']['hidden_slides'] == 1
    chart = client.get(f"/api/ppt-designer/chart/{preview.json()['token']}/0")
    assert chart.status_code == 200, chart.text

    saved = client.put('/api/ppt-designer/design-a/slides', json={'slide_set': edited, 'overrides': body['overrides']})
    assert saved.status_code == 200, saved.text
    assert saved.json()['summary']['slide_properties'] == 1 and saved.json()['summary']['hidden_slides'] == 1
    assert logged('design_slides_saved')[-1]['overrides']['hidden_slides'] == 1
    # Saving its filters from a viewer opened before keeps its Design; its sibling follows the template as it is.
    assert client.put('/api/ppt-designer/design-a', json={**definition, 'filters': {'City': ['London']}}).status_code == 200
    assert stored('design-a')['slide_overrides']['hidden_slides']
    mine = client.post('/api/ppt-designer/prepare', json={**definition, 'slide_overrides': stored('design-a')['slide_overrides']})
    assert [slide['title'] for slide in mine.json()['slides']] == ['Comparison in London']
    sibling = client.post('/api/ppt-designer/prepare', json={**definition, 'name': 'Design sibling'})
    assert [slide['title'] for slide in sibling.json()['slides']] == ['Comparison', 'Next']

    # A template change reaches both, except what design-a changed itself.
    template = copy.deepcopy(saved.json()['template']['slide_set'])
    template['slides'][0]['title'] = 'Comparison of operators'
    template['slides'][1]['subtitle'] = 'From the template'
    changed = client.put('/api/ppt-designer/design-b/slides', json={
        'template_slide_set': template, 'template_updated_at': saved.json()['template']['updated_at']})
    assert changed.status_code == 200, changed.text
    assert [slide['title'] for slide in changed.json()['slide_set']['slides']] == ['Comparison of operators', 'Next']
    again = client.get('/api/ppt-designer/design-a/slides').json()
    assert again['slide_set']['slides'][0]['title'] == 'Comparison in London'
    assert again['report']['template_changed'][0]['property'] == 'title'
    # The template it was read from changed: a stale Designer is refused.
    stale = client.put('/api/ppt-designer/design-b/slides', json={
        'template_slide_set': template, 'template_updated_at': saved.json()['template']['updated_at']})
    assert stale.status_code == 409


def test_detach_save_as_template_and_deleting_a_template_keep_every_design_working(client):
    definition = setup(client)
    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    edited = copy.deepcopy(body['slide_set'])
    edited['slides'][0]['title'] = 'Mine'
    assert client.put('/api/ppt-designer/design-a/slides', json={'slide_set': edited}).status_code == 200

    copy_response = client.post('/api/ppt-designer/design-a/save-as-template', json={'name': 'Design copy'})
    assert copy_response.status_code == 200, copy_response.text
    copied = core.load_template_catalogue(core.repository.report_template_content('Design copy'))
    assert copied[0].slide_title == 'Mine'
    assert client.post('/api/ppt-designer/design-a/save-as-template', json={'name': 'design copy'}).status_code == 409

    detached = client.post('/api/ppt-designer/design-a/detach')
    assert detached.status_code == 200, detached.text
    assert detached.json()['detached'] is True and stored('design-a')['own_slides']['slides'][0]['title'] == 'Mine'

    # Deleting the template detaches the Designs still following it.
    assert client.post('/ppt-designer/templates/Design test/delete', follow_redirects=False).status_code == 303
    assert stored('design-b')['own_slides']['slides'][0]['title'] == 'Comparison'
    assert logged('delete_report_template')[-1]['detached_designs'] == 1
    for name in ('Design one', 'Design sibling'):
        design_id = 'design-a' if name == 'Design one' else 'design-b'
        prepared = client.post('/api/ppt-designer/prepare', json={**definition, 'name': name, 'own_slides': stored(design_id)['own_slides']})
        assert prepared.status_code == 200, prepared.text


def test_a_user_editor_designs_only_what_they_created(client):
    setup(client)
    user_id = core.repository.create_user('editor', 'secret123', 'user-editor')
    core.repository.set_user_workspace_access(user_id, [core.active_workspace.id])
    profile_id = next(item['id'] for item in core.repository.list_modules_profiles() if item['name'] == 'All Modules')
    core.repository.set_users_modules_profile([user_id], profile_id)
    core.invalidate_module_access_cache()
    login(client, 'editor', 'secret123')
    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    assert body['rights'] == {'design': False, 'template': False}
    assert client.put('/api/ppt-designer/design-a/slides', json={'slide_set': body['slide_set']}).status_code == 403
    assert client.put('/api/ppt-designer/design-a/slides', json={'template_slide_set': body['template']['slide_set']}).status_code == 403
    # Their own Design: its Design yes, the template of another user no.
    assert client.put('/api/ppt-designer/mine', json={'name': 'Mine', 'template': 'Design test'}).status_code == 200
    mine = client.get('/api/ppt-designer/mine/slides?edit=1').json()
    assert mine['rights'] == {'design': True, 'template': False}
    assert client.put('/api/ppt-designer/mine/slides', json={'slide_set': mine['slide_set']}).status_code == 200
    saved = client.post('/ppt-designer/templates/Design test/save', data={'catalogue_content': TEMPLATE},
                        headers={'accept': 'application/json'})
    assert saved.status_code == 403


def test_a_template_slide_missing_from_the_edited_design_is_hidden_not_brought_back():
    template = netcheck_slide_set()
    shown, _report = dd.resolve_slides(template, None)
    edited = copy.deepcopy(shown)
    dropped = edited['slides'].pop(2)
    overrides = dd.overrides_between(template, edited)
    assert overrides['hidden_slides'] == [dropped['id']]
    assert dropped['id'] not in [slide['id'] for slide in dd.resolve_slides(template, overrides)[0]['slides'] if not slide.get('hidden')]


def test_drafts_layouts_and_previews_after_detaching(client):
    definition = setup(client)
    layouts = client.get('/api/ppt-designer/slides/layouts')
    assert layouts.status_code == 200, layouts.text
    grid = next(layout for layout in layouts.json()['layouts'] if layout['name'] == 'Title + 1 rows + 2 columns + comments down')
    assert grid['grid'] == [1, 2] and len(grid['places']) == 2
    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    # A draft is kept per user until it is saved or discarded (App Events).
    assert client.get('/api/ppt-designer/design-a/slides/draft').json() == {'draft': None}
    assert client.put('/api/ppt-designer/design-a/slides/draft', json={'state': {'slide_set': body['slide_set']}}).status_code == 200
    assert client.get('/api/ppt-designer/design-a/slides/draft').json()['draft']['slide_set'] == body['slide_set']
    assert client.delete('/api/ppt-designer/design-a/slides/draft?discarded=1').json() == {'deleted': True}
    assert logged('design_draft_discarded')[-1] == {'id': 'design-a', 'draft': True}
    # A preview starts from the Design saved now, even on a selection prepared before it was detached.
    prepared = client.post('/api/ppt-designer/prepare', json=definition).json()
    assert client.post('/api/ppt-designer/design-a/detach').status_code == 200
    own = client.get('/api/ppt-designer/design-a/slides?edit=1').json()['slide_set']
    own['slides'] = own['slides'][:1]
    own['slides'][0]['title'] = 'Only mine'
    preview = client.post('/api/ppt-designer/slides/preview', json={'token': prepared['token'], 'design_id': 'design-a', 'slide_set': own})
    assert preview.status_code == 200, preview.text
    assert [slide['title'] for slide in preview.json()['slides']] == ['Only mine']
    assert client.put('/api/ppt-designer/design-a/slides', json={'slide_set': own}).status_code == 200
    assert [slide['title'] for slide in stored('design-a')['own_slides']['slides']] == ['Only mine']
    fields = client.get(f"/api/ppt-designer/slides/fields?token={preview.json()['token']}")
    assert fields.status_code == 200 and 'Mean_Data_Rate' in fields.json()['columns_by_source']['cdr-data']


def test_the_chart_builder_reads_fields_and_values_and_adds_a_chart_to_a_design(client):
    definition = setup(client)
    token = client.post('/api/ppt-designer/prepare', json=definition).json()['token']
    fields = client.get(f'/api/ppt-designer/slides/fields?token={token}').json()['fields']['cdr-data']
    assert {'name': 'Operator', 'type': 'text', 'category': 'CDR-Main fields'} in fields or any(item['name'] == 'Operator' for item in fields)
    values = client.get(f'/api/ppt-designer/slides/values?token={token}&source=CDR-Data&field=Operator')
    assert values.status_code == 200, values.text
    assert values.json()['values'] == [{'value': 'A', 'count': 2}, {'value': 'B', 'count': 1}]
    targets = client.get('/api/ppt-designer/targets').json()['designs']
    target = next(item for item in targets if item['id'] == 'design-a')
    assert [slide['title'] for slide in target['slides']] == ['Comparison', 'Next'] and target['slides'][0]['free'] == 0
    chart = {'chart_title': 'Rate by city', 'cdr_source': 'CDR-Data', 'kpi': 'Mean_Data_Rate', 'chart_type': 'Average Vertical Bars',
             'rows_split': 'City', 'columns_split': '', 'legend': '', 'filters': 'Operator IN (A)', 'legend_position': 'Top'}
    full = client.post('/api/ppt-designer/design-a/add-chart', json={'element': chart, 'slide_id': target['slides'][0]['id']})
    assert full.status_code == 409
    added = client.post('/api/ppt-designer/design-a/add-chart', json={'element': chart})
    assert added.status_code == 200, added.text
    assert added.json() == {'design': 'Design one', 'slide': 'Rate by city'}
    assert stored('design-a')['slide_overrides']['local_slides'][0]['slide']['elements'][0]['kpi'] == 'Mean_Data_Rate'
    assert logged('design_chart_added')[-1]['new_slide'] is True
    prepared = client.post('/api/ppt-designer/prepare?design_id=design-a', json=definition)
    assert [slide['title'] for slide in prepared.json()['slides']] == ['Comparison', 'Next', 'Rate by city']
    # Chart Builder reads the same fields and values from the CDRs chosen.
    builder_fields = client.post('/api/chart-builder/fields', json={'dataset_ids': [1]}).json()['fields']
    assert any(item['name'] == 'Mean_Data_Rate' for item in builder_fields)
    builder_values = client.post('/api/chart-builder/values', json={'dataset_ids': [1], 'field': 'City'}).json()['values']
    assert builder_values == [{'value': 'London', 'count': 2}, {'value': 'Leeds', 'count': 1}]


def test_the_chart_builder_reads_only_the_columns_of_its_chart_once_and_leaves_out_of_scope_operators_out(client, monkeypatch):
    setup(client)
    reads = []
    original = core.repository.load_dataset_rows

    def load_dataset_rows(dataset_id, columns, filters, **kwargs):
        reads.append(sorted(columns))
        return original(dataset_id, columns, filters, **kwargs)

    # (The CDRs of the tests have no columnar copy: their columns are read from their tables.)
    monkeypatch.setattr(core.repository, 'load_dataset_rows', load_dataset_rows)
    chart = {'chart_title': 'Rate', 'cdr_source': 'CDR-Data', 'kpi': 'MEDIAN(Mean_Data_Rate)', 'chart_type': 'Average Vertical Bars',
             'rows_split': 'Operator', 'columns_split': '', 'legend': '', 'filters': '', 'legend_position': 'Top'}
    core._clear_chart_preview_caches()
    first = client.post('/api/chart-builder/preview', json={'dataset_ids': [1], 'definition': chart})
    assert first.status_code == 200, first.text
    assert [bar['value'] for bar in first.json()['bars']] == [20.0, 20.0]
    # Its measure and splits (with the Operator and Campaign fields every chart consults), never the other columns of the CDR.
    assert len(reads) == 1 and {'Mean_Data_Rate', 'Operator'} <= set(reads[0])
    assert not set(reads[0]) & {'City', 'Test_Name', 'Test_Start_Time'}
    # A field dropped on a shelf reads only its own column; a chart drawn before reads nothing.
    second = client.post('/api/chart-builder/preview', json={'dataset_ids': [1], 'definition': {**chart, 'columns_split': 'City'}})
    assert second.status_code == 200, second.text
    assert reads[1:] == [['City']]
    again = client.post('/api/chart-builder/preview', json={'dataset_ids': [1], 'definition': chart})
    assert again.json() == first.json() and len(reads) == 2
    # The operators out of scope in the NR Mode of the CDR (the NR Modes of the Operator Maps) are left out: B has a
    # network only in SA, and the CDR is of NSA.
    core.repository.replace_operator_mapping_group(None, 'B', ['B'], nr_modes=['SA'])
    core._clear_chart_preview_caches()
    scoped = client.post('/api/chart-builder/preview', json={'dataset_ids': [1], 'definition': chart})
    assert scoped.status_code == 200, scoped.text
    assert [bar['key'] for bar in scoped.json()['bars']] == [['A', '(all)']]


def test_a_kpi_card_of_the_chart_builder_previews_with_its_settings_and_joins_a_design_as_a_kpi_card(client):
    setup(client)
    settings = {'measure': 'count', 'comparison': 'none', 'sparkline': False}
    card = {'chart_title': 'Samples', 'cdr_source': 'CDR-Data', 'kpi': 'Mean_Data_Rate', 'chart_type': 'KPI Card', 'rows_split': 'Campaign',
            'columns_split': '', 'legend': '', 'filters': '', 'legend_position': 'Top', 'kpi_card': settings}
    preview = client.post('/api/chart-builder/preview', json={'dataset_ids': [1], 'definition': card})
    assert preview.status_code == 200, preview.text
    assert preview.json()['type'] == 'kpi'
    assert [item['value'] for item in preview.json()['cards']] == [3]
    added = client.post('/api/ppt-designer/design-a/add-chart', json={'element': card})
    assert added.status_code == 200, added.text
    element = stored('design-a')['slide_overrides']['local_slides'][-1]['slide']['elements'][0]
    assert (element['kind'], element['chart_type'], element['kpi_card']) == ('kpi', 'KPI Card', settings)


def test_the_chart_builder_draws_one_chart_per_value_with_its_format_and_adds_them_to_a_design(client):
    setup(client)
    style = {'legend': {'position': 'bottom'}, 'series': {'A': {'colour': '#FF0000'}}}
    chart = {'chart_title': 'Rate', 'cdr_source': 'CDR-Data', 'kpi': 'Mean_Data_Rate', 'chart_type': 'Average Vertical Bars', 'rows_split': 'Operator',
             'columns_split': '', 'legend': 'Operator', 'filters': '', 'legend_position': 'top', 'style': style, 'repeat': {'field': 'City'}}
    preview = client.post('/api/chart-builder/preview', json={'dataset_ids': [1], 'definition': chart})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert (body['type'], body['field'], [item['value'] for item in body['charts']]) == ('repeat', 'City', ['Leeds', 'London'])
    assert [item['model']['title'] for item in body['charts']] == ['Rate – Leeds', 'Rate – London']
    assert all(item['model']['format_overrides'] == style for item in body['charts'])
    # London: A twice (10 and 30); Leeds: B once (20).
    assert [item['model']['cells'] for item in body['charts']] == [[[20.0]], [[20.0]]]
    single = client.post('/api/chart-builder/preview', json={'dataset_ids': [1], 'definition': {**chart, 'repeat': None}}).json()
    assert single['type'] == 'mean_bar' and single['format_overrides'] == style
    added = client.post('/api/ppt-designer/design-a/add-chart', json={'element': chart})
    assert added.status_code == 200, added.text
    element = stored('design-a')['slide_overrides']['local_slides'][-1]['slide']['elements'][0]
    assert (element['style'], element['repeat']) == (style, {'field': 'City'})


def test_the_chart_builder_adds_a_chart_with_its_format_to_a_ppt_template_and_every_design_following_it(client):
    setup(client)
    targets = client.get('/api/ppt-designer/targets').json()
    template = next(item for item in targets['templates'] if item['name'] == 'Design test')
    assert [slide['title'] for slide in template['slides']] == ['Comparison', 'Next']
    style = {'legend': {'position': 'bottom'}}
    chart = {'chart_title': 'Rate by city', 'cdr_source': 'CDR-Data', 'kpi': 'Mean_Data_Rate', 'chart_type': 'Average Vertical Bars',
             'rows_split': 'City', 'columns_split': '', 'legend': '', 'filters': '', 'legend_position': 'Top', 'style': style}
    added = client.post('/api/ppt-designer/templates/Design test/add-chart', json={'element': chart})
    assert added.status_code == 200, added.text
    assert added.json() == {'template': 'Design test', 'slide': 'Rate by city'}
    for design_id in ('design-a', 'design-b'):
        slides = client.get(f'/api/ppt-designer/{design_id}/slides').json()['slide_set']['slides']
        assert [slide['title'] for slide in slides] == ['Comparison', 'Next', 'Rate by city']
        assert slides[-1]['elements'][0]['style'] == style
    event = logged('template_chart_added')[-1]
    assert (event['template'], event['slide'], event['new_slide'], event['designs']) == ('Design test', 'Rate by city', True, 2)
    assert client.post('/api/ppt-designer/templates/Missing/add-chart', json={'element': chart}).status_code == 404


def test_the_gallery_shows_each_template_with_its_first_slides_laid_out(client):
    setup(client)
    gallery = client.get('/api/ppt-designer/templates-gallery')
    assert gallery.status_code == 200, gallery.text
    template = next(item for item in gallery.json()['templates'] if item['name'] == 'Design test')
    assert (template['identifier'], template['slides']) == ('Design test', 2) and template['charts'] >= 1
    first = template['preview'][0]
    # Each element with its place on the slide (fractions of it) and its chart type, as the Designer lays it out.
    assert first['kind'] == 'content' and first['title'] == 'Comparison' and first['places']
    assert all(len(first['places'][element['place']]) == 4 and element['chart_type'] for element in first['elements'])


def test_the_format_of_a_chart_travels_in_its_row_and_reaches_its_model(client):
    definition = setup(client)
    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    edited = copy.deepcopy(body['slide_set'])
    style = {'series': {'A': {'colour': '#FF0000', 'width': 3, 'dash': 'dashed'}}, 'legend': {'position': 'bottom'},
             'axes': {'x': {'title': 'Rate (Mbit/s)', 'decimals': 0}}}
    edited['slides'][0]['elements'][0]['style'] = style
    assert client.put('/api/ppt-designer/design-a/slides', json={'slide_set': edited}).status_code == 200
    assert stored('design-a')['slide_overrides']['elements']['s1e1']['style']['value'] == style
    prepared = client.post('/api/ppt-designer/prepare?design_id=design-a', json=definition).json()
    chart = next(chart for chart in prepared['slides'][0]['charts'] if chart['element'] == 's1e1')
    model = client.get(f"/api/ppt-designer/chart/{prepared['token']}/{chart['index']}").json()
    assert model['format_overrides'] == style
    # In Template scope it is written in the Format column of the row.
    template = copy.deepcopy(body['template']['slide_set'])
    template['slides'][0]['elements'][1]['style'] = {'labels': {'colour': '#123456'}}
    assert client.put('/api/ppt-designer/design-b/slides', json={'template_slide_set': template}).status_code == 200
    rows = parse_catalog_csv(core.repository.report_template_content('Design test'))
    assert dd.row_format(rows[1])['style'] == {'labels': {'colour': '#123456'}}


# --------------------------------------------------------------------------------------------------------------------
# Free layouts and the elements other than charts (phase 4)
# --------------------------------------------------------------------------------------------------------------------

def test_kpi_cards_text_boxes_pictures_places_and_repeat_travel_in_the_format_column():
    from src.modules import ppt_designer as designs
    slide_set = {'version': 1, 'parameters': [], 'slides': [{
        'id': 's1', 'kind': 'content', 'title': 'Overview', 'subtitle': '', 'layout': 'Title and 2 columns + Comments', 'optional': False,
        'options': {'geometry': [[0, 0, 30, 100], [32, 0, 68, 100]], 'grid': {'rows': [1], 'columns': [0.3, 0.7], 'areas': [[0, 0, 1, 1], [0, 1, 1, 1]]}},
        'elements': [
            {'id': 's1e1', 'kind': 'text', 'place': 1, 'chart_type': 'Text Box', 'chart_title': '', 'content': {'text': '# Notes', 'align': 'center'}},
            {'id': 's1e2', 'kind': 'kpi', 'place': 0, 'chart_type': 'KPI Card', 'chart_title': 'Rate', 'cdr_source': 'CDR-Data', 'kpi': 'Mean_Data_Rate', 'rows_split': 'Campaign',
             'kpi_card': {'measure': 'median', 'comparison': 'target', 'target': 15}, 'repeat': {'field': 'City'}},
            {'id': 's1e3', 'kind': 'image', 'place': 2, 'chart_type': 'Image', 'chart_title': '', 'content': {'image': 'a' * 32, 'fit': 'cover'}},
        ]}]}
    entries = dd.entries_from_slides(slide_set)
    # The rows follow the order of the places; each kind keeps what it needs.
    assert [entry.chart_type for entry in entries] == ['KPI Card', 'Text Box', 'Image']
    assert dd.row_format(entries[0])['kpi'] == {'measure': 'median', 'comparison': 'target', 'target': 15}
    assert designs.repeat_field(entries[0]) == 'City'
    back = dd.slides_from_entries(parse_catalog_csv(catalogue_csv(entries)))
    slide = back['slides'][0]
    assert slide['options']['geometry'] == [[0, 0, 30, 100], [32, 0, 68, 100]]
    assert {element['id']: (element['kind'], element['place']) for element in slide['elements']} == {
        's1e2': ('kpi', 0), 's1e1': ('text', 1), 's1e3': ('image', 2)}
    assert next(element for element in slide['elements'] if element['id'] == 's1e1')['content'] == {'text': '# Notes', 'align': 'center'}
    # The places of a free layout, and which place each row takes (a place can stay empty; repeated places are refused).
    assert designs.slide_geometry(entries) == [[0, 0, 30, 100], [32, 0, 68, 100]]
    assert designs.explicit_places(entries, 3) == [0, 1, 2]
    assert designs.explicit_places(entries, 2) is None
    assert designs.explicit_places([replace(entries[0], format='')], 3) is None
    # A rectangle of the chart area as a frame of the slide, and a place divided for the small multiples.
    assert designs.frame_from_rect([50, 0, 50, 50], [(100, 200, 400, 300), (500, 200, 400, 300)]) == (500, 200, 400, 150)
    cells = designs.subdivided([0, 0, 60, 40], 4)
    assert len(cells) == 4 and all(cell[2] > 0 and cell[3] > 0 for cell in cells)
    assert max(cell[0] + cell[2] for cell in cells) == pytest.approx(60) and max(cell[1] + cell[3] for cell in cells) == pytest.approx(40)


def element(element_id, kind, place, content):
    """A text box or a picture as the Designer adds it: no CDR, only its content."""
    blank = dict.fromkeys(dd.ELEMENT_FIELDS, '') | {'exclude_null_empty': False, 'exclude_zero': False}
    return {**blank, 'id': element_id, 'kind': kind, 'place': place, 'chart_type': dd.KIND_CHART_TYPES[kind], 'content': content}


def png(width=4, height=2):
    from PIL import Image
    buffer = BytesIO()
    Image.new('RGB', (width, height), (220, 20, 60)).save(buffer, format='PNG')
    return buffer.getvalue()


def test_free_places_kpi_cards_repeat_text_and_pictures_are_laid_out_on_the_prepared_cdrs(client):
    definition = setup(client)
    picture = png()
    uploaded = client.post('/api/ppt-designer/images', files={'file': ('logo.png', picture, 'image/png')})
    assert uploaded.status_code == 200, uploaded.text
    image = uploaded.json()
    assert (image['width'], image['height'], image['name']) == (4, 2, 'logo.png')
    served = client.get(image['url'])
    assert served.status_code == 200 and served.content == picture and served.headers['content-type'] == 'image/png'
    assert logged('design_image_uploaded')[-1]['id'] == image['id']
    refused = client.post('/api/ppt-designer/images', files={'file': ('notes.svg', b'<svg/>', 'image/svg+xml')})
    assert refused.status_code == 400
    assert client.get(f"/api/ppt-designer/images/{'0' * 32}").status_code == 404

    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    edited = copy.deepcopy(body['slide_set'])
    first, second = edited['slides']
    first['options'] = {'geometry': [[0, 0, 30, 100], [32, 0, 68, 100]]}
    kpi, chart = first['elements']
    kpi.update(kind='kpi', chart_type='KPI Card', chart_title='Rate', kpi_card={'measure': 'average', 'comparison': 'target', 'target': 15}, place=0)
    chart.update(repeat={'field': 'City'}, place=1)
    second['options'] = {'geometry': [[0, 0, 50, 100], [50, 0, 50, 100]]}
    second['elements'] = [
        element(second['elements'][0]['id'], 'text', 0, {'text': '# Summary\n- **Fast** in London\nPlain line', 'size': 'medium', 'align': 'left'}),
        element('s2e9', 'image', 1, {'image': image['id'], 'fit': 'contain'}),
    ]
    token = client.post('/api/ppt-designer/prepare', json=definition).json()['token']
    preview = client.post('/api/ppt-designer/slides/preview', json={'token': token, 'design_id': 'design-a', 'slide_set': edited})
    assert preview.status_code == 200, preview.text
    overview, summary = preview.json()['slides']
    # The KPI card keeps its place; the chart repeated by City is one chart per city in the other place.
    card = next(item for item in overview['charts'] if item.get('kind') == 'kpi')
    assert card['position'] == pytest.approx([0, 0, 30, 100])
    repeated = [item for item in overview['charts'] if item.get('element') == chart['id']]
    assert len(repeated) == 2
    assert all(item['position'][0] >= 32 - 1e-6 and item['position'][0] + item['position'][2] <= 100 + 1e-6 for item in repeated)
    model = client.get(f"/api/ppt-designer/chart/{preview.json()['token']}/{card['index']}").json()
    assert model['type'] == 'kpi'
    assert model['cards'][0]['value'] == pytest.approx(20) and model['cards'][0]['n'] == 3
    assert model['cards'][0]['comparison_label'] == 'Target' and model['cards'][0]['improves'] is True
    # The text box and the picture read no CDR: the viewer shows their content.
    text, picture_chart = sorted(summary['charts'], key=lambda item: item['position'][0])
    assert text['kind'] == 'text' and text['content']['text'].startswith('# Summary') and text['available'] is False
    assert picture_chart['kind'] == 'image' and picture_chart['content']['url'] == image['url']
    assert picture_chart['position'] == pytest.approx([50, 0, 50, 100])


def test_the_pictures_of_designs_and_templates_travel_with_their_packages(client, tmp_path):
    import io
    import zipfile
    setup(client)
    image = client.post('/api/ppt-designer/images', files={'file': ('logo.png', png(8, 2), 'image/png')}).json()
    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    edited = copy.deepcopy(body['slide_set'])
    second = edited['slides'][1]
    second['options'] = {'geometry': [[0, 0, 50, 100], [50, 0, 50, 100]]}
    second['elements'] = [second['elements'][0], element('s2e9', 'image', 1, {'image': image['id'], 'fit': 'contain'})]
    # The picture in a slide of the Design (This Design) and of its template (Template scope).
    assert client.put('/api/ppt-designer/design-a/slides', json={'slide_set': edited}).status_code == 200
    assert client.put('/api/ppt-designer/design-a/slides', json={'template_slide_set': edited, 'template_updated_at': body['template']['updated_at']}).status_code == 200

    def forget_picture():
        with core.repository.connection() as connection:
            connection.execute('DELETE FROM design_images WHERE id = ?', (image['id'],))
        assert client.get(f"/api/ppt-designer/images/{image['id']}").status_code == 404

    # PPT Designs: the package brings the pictures of their slides, and an import adds them.
    workspace = core.active_workspace
    payload = core._design_archive_payload(workspace)
    assert list(json.loads(payload)['images']) == [image['id']]
    forget_picture()
    core._import_workspace_designs(workspace, payload, 'super')
    assert client.get(f"/api/ppt-designer/images/{image['id']}").status_code == 200
    # PPT Templates: beside their CSV files.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        core._archive_workspace_report_templates(archive, workspace, 'report-templates')
    with zipfile.ZipFile(buffer) as archive:
        assert 'report-templates/design-images.json' in archive.namelist()
        archive.extractall(tmp_path)
    forget_picture()
    core.import_slides_templates_archive(tmp_path, [workspace.id], {}, includes_designs=True)
    assert client.get(f"/api/ppt-designer/images/{image['id']}").status_code == 200


def test_text_boxes_and_pictures_are_native_shapes_of_the_exported_ppt(client):
    import time
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE
    definition = setup(client)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and core.repository.get_dataset(1)['status'] != 'ready':
        time.sleep(0.05)
    image = client.post('/api/ppt-designer/images', files={'file': ('logo.png', png(8, 2), 'image/png')}).json()
    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    edited = copy.deepcopy(body['slide_set'])
    edited['slides'][0]['hidden'] = True
    second = edited['slides'][1]
    second['options'] = {'geometry': [[0, 0, 40, 100], [40, 0, 40, 100], [80, 0, 20, 100]]}
    second['elements'] = [
        element(second['elements'][0]['id'], 'text', 0, {'text': '# Summary\n- **Fast** in London\nPlain line', 'size': 'medium', 'align': 'left'}),
        element('s2e9', 'image', 1, {'image': image['id'], 'fit': 'contain'}),
        # (A new chart still without its measure keeps its place empty in the PPT.)
        {**dict.fromkeys(dd.ELEMENT_FIELDS, ''), 'exclude_null_empty': False, 'exclude_zero': False, 'id': 's2e10', 'kind': 'chart', 'place': 2,
         'chart_type': 'Scatter', 'cdr_source': 'CDR-Data', 'chart_title': 'New chart'},
    ]
    assert client.put('/api/ppt-designer/design-a/slides', json={'slide_set': edited}).status_code == 200
    payload = {**definition, 'slide_overrides': stored('design-a')['slide_overrides']}
    queued = client.post('/api/ppt-designer/design-a/export-ppt', json={'definition': payload})
    assert queued.status_code == 202, queued.text
    job_id = queued.json()['job_id']
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = next(item for item in client.get('/api/ppt-designer/ppt-jobs').json()['jobs'] if item['id'] == job_id)
        if job['status'] in {'ready', 'failed'}:
            break
        time.sleep(0.05)
    assert job['status'] == 'ready', job
    with core.repository.connection() as connection:
        output = connection.execute('SELECT output_path FROM design_ppt_jobs WHERE id = ?', (job_id,)).fetchone()['output_path']
    slides = list(Presentation(output).slides)
    assert len(slides) == 1
    shapes = slides[0].shapes
    box = next(shape for shape in shapes if shape.has_text_frame and 'Summary' in shape.text_frame.text)
    assert [paragraph.text for paragraph in box.text_frame.paragraphs] == ['Summary', '• Fast in London', 'Plain line']
    assert [run.font.bold for run in box.text_frame.paragraphs[1].runs] == [False, True, False]
    pictures = [shape for shape in shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pictures) == 1
    # Fitted in its place keeping its ratio (4:1), centred on the right half.
    assert pictures[0].width / pictures[0].height == pytest.approx(4, rel=0.01)
    assert pictures[0].left > box.left


def test_a_chart_still_being_built_reads_no_cdr_and_keeps_what_it_has():
    blank = dict.fromkeys(dd.ELEMENT_FIELDS, '') | {'exclude_null_empty': False, 'exclude_zero': False}
    chart = {**blank, 'id': 'e1', 'kind': 'chart', 'place': 0, 'chart_title': 'Rate', 'cdr_source': 'CDR-Data', 'kpi': 'Mean_Data_Rate',
             'chart_type': 'CDF Line', 'rows_split': 'Operator'}
    new = {**blank, 'id': 'e2', 'kind': 'chart', 'place': 1, 'chart_title': 'New chart', 'cdr_source': 'CDR-Voice', 'chart_type': 'Scatter',
           'filters': 'City IN (London)'}
    slide_set = {'version': 1, 'parameters': [], 'slides': [{'id': 's1', 'kind': 'content', 'title': 'Two', 'subtitle': '',
                                                              'layout': 'Title + 1 rows + 2 columns + comments down', 'elements': [chart, new]}]}
    assert dd.is_draft_chart(new) and not dd.is_draft_chart(chart)
    # Its row reads no CDR (Chart in progress), so the template stays valid; its Format column keeps what it has.
    entries = dd.entries_from_slides(slide_set)
    assert [(entry.chart_type, entry.cdr_source, entry.filters) for entry in entries] == [
        ('CDF Line', 'CDR-Data', ''), (dd.DRAFT_CHART_TYPE, '', '')]
    assert [entry.chart_type for entry in parse_catalog_csv(dd.slides_csv(slide_set))] == ['CDF Line', dd.DRAFT_CHART_TYPE]
    back = dd.slides_from_entries(entries)['slides'][0]['elements'][1]
    assert {key: back[key] for key in ('id', 'kind', 'chart_title', 'cdr_source', 'kpi', 'chart_type', 'filters')} == {
        'id': 'e2', 'kind': 'chart', 'chart_title': 'New chart', 'cdr_source': 'CDR-Voice', 'kpi': '', 'chart_type': 'Scatter',
        'filters': 'City IN (London)'}
    # Given its measure and a split, it is a chart again.
    drawn = dd.entries_from_slides({**slide_set, 'slides': [{**slide_set['slides'][0], 'elements': [chart, {**new, 'kpi': 'MOS | LQ', 'rows_split': 'Operator'}]}]})
    assert drawn[1].chart_type == 'Scatter' and drawn[1].cdr_source == 'CDR-Voice'
    # A new chart turned into a KPI card is one in progress too until it has its measure.
    card = {**new, 'kind': 'kpi', 'chart_type': 'KPI Card', 'rows_split': 'Campaign', 'kpi_card': {'measure': 'average'}}
    kpi_set = {**slide_set, 'slides': [{**slide_set['slides'][0], 'elements': [chart, card]}]}
    assert dd.is_draft_chart(card) and dd.entries_from_slides(kpi_set)[1].chart_type == dd.DRAFT_CHART_TYPE
    assert [entry.chart_type for entry in parse_catalog_csv(dd.slides_csv(kpi_set))] == ['CDF Line', dd.DRAFT_CHART_TYPE]
    back = dd.slides_from_entries(dd.entries_from_slides(kpi_set))['slides'][0]['elements'][1]
    assert (back['kind'], back['chart_type'], back['rows_split'], back['kpi_card']) == ('kpi', 'KPI Card', 'Campaign', {'measure': 'average'})
    assert dd.entries_from_slides({**kpi_set, 'slides': [{**kpi_set['slides'][0], 'elements': [chart, {**card, 'kpi': 'MOS'}]}]})[1].chart_type == 'KPI Card'


def test_titles_and_text_boxes_name_the_selection_of_the_design(client):
    import time
    definition = setup(client)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and core.repository.get_dataset(1)['status'] != 'ready':
        time.sleep(0.05)
    body = client.get('/api/ppt-designer/design-a/slides?edit=1').json()
    edited = copy.deepcopy(body['slide_set'])
    first, second = edited['slides']
    first['title'] = '{Design}: {Operators} in {Cities}'
    first['subtitle'] = '{Scope} · {NR Mode}'
    first['elements'][0]['chart_title'] = 'Rate in {Regions}'
    second['elements'] = [element(second['elements'][0]['id'], 'text', 0, {'text': '**{Cities}** · {NR Mode Name} · {Vendors}'})]
    saved = client.put('/api/ppt-designer/design-a/slides', json={'slide_set': edited})
    assert saved.status_code == 200, saved.text
    overrides = stored('design-a')['slide_overrides']

    def shown(filters):
        prepared = client.post('/api/ppt-designer/prepare?design_id=design-a', json={**definition, 'filters': filters, 'slide_overrides': overrides})
        assert prepared.status_code == 200, prepared.text
        return prepared.json()['slides']

    overview, notes = shown({'City': ['London']})
    assert (overview['title'], overview['subtitle']) == ('Design one: All Operators in London', 'Operator Comparison · NSA')
    assert overview['charts'][0]['title'] == 'Rate in All Regions'
    assert notes['charts'][0]['content']['text'] == '**London** · Non-Standalone · All Vendors'
    # Every value of the CDRs reads as All, as on the cover.
    overview, _notes = shown({'City': ['London', 'Leeds'], 'Operator': ['B']})
    assert overview['title'] == 'Design one: B in All Cities'
    # The Design keeps the tokens: each Design writes its own.
    assert stored('design-a')['slide_overrides']['slides'][first['id']]['title']['value'] == '{Design}: {Operators} in {Cities}'
