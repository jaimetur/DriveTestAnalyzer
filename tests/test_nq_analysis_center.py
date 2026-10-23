"""NQ Analysis Center: field catalog by section, automatic NQ Call Status, root cause catalog, RCA script results,
recommendation from the three root cause sources, lifecycle and RCA insights, the Excel layout and the catalog workbook."""

import io
import json
import sqlite3
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

import src.DriveTestAnalyzer as core
from src.modules import non_qualified_calls as nq
from src.modules import non_qualified_calls_visuals as visuals
from src.modules import nq_analyses_rules, nq_catalog, nq_rca
from tests.test_non_qualified_calls import add_cdr, enable_module, login, query, workspace_user


@pytest.fixture(autouse=True)
def indexing_runs_at_once(monkeypatch):
    monkeypatch.setattr(core, 'submit_background_task', lambda callback, *args: callback(*args))


def calls_frame() -> pd.DataFrame:
    """Three Non-Qualified Voice calls with a JOIN_ID and NetCheck RCA, and one completed call."""
    return pd.DataFrame({
        'JOIN_ID': ['0xA1', '0xB2', '0xC3', '0xD4'],
        'Session_ID_A': [1, 2, 3, 4],
        'Operator': ['Vodafone UK', 'Vodafone UK', 'EE', 'EE'],
        'Campaign': ['UK_Q3_2026'] * 4,
        'Session_Type': ['CALL', 'WhatsApp CALL', 'MultiRAB CALL', 'CALL'],
        'Call_Status': ['Failed', 'Dropped', 'Failed', 'Completed'],
        'status': ['Failed', 'Dropped', 'Failed', 'Completed'],
        'Call_Start_Time': ['2026-09-01 10:00:00', '2026-09-02 11:00:00', '2026-09-03 12:00:00', '2026-09-03 13:00:00'],
        'Technology': ['LTE', 'LTE', 'NR', 'LTE'],
        'Failure_Classification': ['RF_Problems', 'RF Problems', 'VoLTE Problems', ''],
        'Failure_Category': ['Coverage problem', 'Interference problem', 'VoLTE Core', ''],
        'Failure_Subcategory': ['DL coverage problems', 'DL interference problems', 'No QCI1 bearer activation', ''],
        'Cell_ID_A': ['123456', '123457', '9876543210', '1'],
        'Vendor': ['Ericsson', 'Huawei', 'Nokia', 'Nokia'],
        'Call_Start_Latitude_A': [51.5, 51.6, 51.7, 51.8],
        'Call_Start_Longitude_A': [-0.1, -0.2, -0.3, -0.4],
    })


def setup_calls(client, tmp_path) -> dict[str, dict]:
    enable_module()
    add_cdr(tmp_path, 'UK_Voice_Q3.xlsx', 'voice', calls_frame())
    login(client)
    return {call['join_id']: call for call in query(client)['calls']}


def patch(client, call, changes):
    response = client.patch(f"/api/non-qualified-calls/calls/{call['call_key']}", json={'changes': changes})
    assert response.status_code == 200, response.text
    return response.json()['call']


def test_new_workspaces_get_the_catalog_of_the_meeting_workbook(client, tmp_path):
    setup_calls(client, tmp_path)
    state = client.get('/api/non-qualified-calls/state').json()
    fields = state['fields']
    # The 37 fields of the meeting workbook, with the Auto RCA fields, the Last Cell ID and Failure Comment of the CDR and
    # the fields of the analyses of the previous tool and of the NQ Prioritization, each next to the field it goes with in the
    # Excel export.
    assert len(fields) == 64
    keys = [field['key'] for field in fields]
    for before, after in (('nq_call_status', 'priority'), ('priority', 'prioritization'), ('assignee', 'analyst'), ('analyst', 'reviewer'),
                          ('planned_date', 'planned_fy'), ('implementation_status', 'implementation_team'),
                          ('initial_root_category', 'initial_root_cause'),
                          ('vendor_when_failure', 'vendor_2_when_failure'), ('reviewer', 'unique_id'),
                          ('solution_location', 'polygon_area'), ('polygon_area', 'description')):
        assert keys.index(after) == keys.index(before) + 1, (before, after)
    assert keys.index('initial_root_cause') < keys.index('selected_root_category')
    assert [field['key'] for field in fields if field['section'] == 'failure_event'][-3:] == [
        'vendor_when_failure', 'vendor_2_when_failure', 'failure_comment']
    assert next(field for field in fields if field['key'] == 'last_cell_id')['source_ref'] == 'last_cell_id'
    assert [field['key'] for field in fields if field['section'] == 'analysis'][:3] == ['analysis_status', 'tunnel_failure', 'needed_technology']
    assert [field['key'] for field in fields if field['section'] == 'analysis'][-3:] == ['description', 'findings', 'proposed_measure']
    assert [section['label'] for section in state['sections']][2] == 'Failure Details'
    # The NetCheck RCA comes before the Ericsson RCA.
    assert [field['label'] for field in fields[:4]] == ['NetCheck RCA Failure Classification', 'NetCheck RCA Suggested Category',
                                                         'NetCheck RCA Suggested Cause', 'Ericsson RCA Category A']
    by_key = {field['key']: field for field in fields}
    assert by_key['rca_suggested_cause']['source'] == 'rca' and by_key['rca_suggested_cause']['label'] == 'Ericsson RCA Suggested Cause'
    assert [field['label'] for field in fields if field['source'] == 'rca'][-1] == 'Ericsson RCA Evidence'
    assert by_key['netcheck_suggested_cause']['source_ref'] == 'failure_subcategory'
    # The suggested causes are columns only when chosen in Columns; every column shows the colour of its group,
    # the call columns that of the call, as in the Excel export.
    assert not by_key['rca_suggested_cause']['in_table'] and not by_key['netcheck_suggested_cause']['in_table']
    assert [field['key'] for field in fields if field['in_table'] and field['source'] != 'tracking'] == [
        'prioritization', 'scoring_impact', 'scoring_points_lost', 'repeated_issue', 'analysis_status', 'implementation_status']
    assert state['call_section'] == nq.CALL_SECTION
    assert by_key['selected_root_category']['source'] == 'tracking' and by_key['nq_call_status']['section'] == 'general'
    assert by_key['analysis_status']['section'] == 'analysis'
    assert [option['name'] for option in by_key['planned_status']['options']] == ['Not Planned', 'Planned']
    assert [section['key'] for section in state['sections']] == list(nq_catalog.SECTION_KEYS)
    assert state['sections'][1]['color'] == '#FFC000'
    assert [item['name'] for item in state['options']['statuses']][:2] == ['Not Attended', 'Under Analysis']
    assert 'RAN Planning Coverage' in [item['name'] for item in state['options']['teams']]
    root = state['root_causes']
    assert 'Poor Coverage LTE' in [item['name'] for item in root['categories']]
    causes = {item['name']: item for item in root['causes']}
    # The causes of the meeting and those of the first catalog, each in a domain.
    assert causes['NLOS due to clutter or terrain profile']['domain'] == 'RF' and causes['DNS']['domain'] == 'Protocol'
    assert state['status_rules'][0]['status'] == 'Closed'


def test_status_follows_the_phase_fields_until_it_is_set_by_hand(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    call = calls['0xA1']
    assert call['status'] == 'Not Attended' and call['status_mode'] == 'auto'
    # A comment attends the call: it is open, Under Analysis.
    assert client.post(f"/api/non-qualified-calls/calls/{call['call_key']}/comments", json={'body': 'Looking at it'}).status_code == 200
    assert {item['join_id']: item for item in query(client)['calls']}['0xA1']['status'] == 'Under Analysis'
    updated = patch(client, call, {'fields': {'analysis_status': 'Ongoing'}})
    assert updated['status'] == 'Under Analysis'
    updated = patch(client, call, {'fields': {'implementation_status': 'Under evaluation'}})
    assert updated['status'] == 'Under Implementation'
    updated = patch(client, call, {'fields': {'implementation_status': 'Implemented'}})
    assert updated['status'] == 'Closed'
    # Chosen by hand, the status no longer follows the fields...
    updated = patch(client, call, {'status': 'Under Planning'})
    assert updated['status'] == 'Under Planning' and updated['status_mode'] == 'manual'
    updated = patch(client, call, {'fields': {'analysis_status': 'Finished'}})
    assert updated['status'] == 'Under Planning'
    # ...until it goes back to automatic.
    updated = patch(client, call, {'status_mode': 'auto'})
    assert updated['status'] == 'Closed' and updated['status_mode'] == 'auto'
    detail = client.get(f"/api/non-qualified-calls/calls/{call['call_key']}").json()
    assert {'status_auto', 'status', 'status_mode'} <= {entry['field'] for entry in detail['history']}
    # A status set by the rules follows, in the history, the change that moved it.
    fields = [entry['field'] for entry in detail['history']]
    assert fields[fields.index('field:implementation_status') + 1] == 'status_auto' and fields[-2:] == ['status_mode', 'status_auto']
    # The rules adapt to renamed list values and the calls follow new rules at once.
    fields = client.get('/api/non-qualified-calls/state').json()['fields']
    for field in fields:
        if field['key'] == 'implementation_status':
            field['options'] = [{**option, 'previous': option['name']} for option in field['options']]
            field['options'][3]['name'] = 'Done'
    assert client.put('/api/non-qualified-calls/fields', json={'fields': fields}).status_code == 200
    rules = client.get('/api/non-qualified-calls/state').json()['status_rules']
    assert ['Done'] in [condition['values'] for rule in rules for condition in rule['conditions']]
    other = calls['0xB2']
    patch(client, other, {'fields': {'planned_status': 'Planned'}})
    rules = [{'status': 'Closed', 'conditions': [{'field': 'planned_status', 'op': 'in', 'values': ['Planned']}]}]
    assert client.put('/api/non-qualified-calls/status-rules', json={'rules': rules}).status_code == 200
    assert {item['join_id']: item for item in query(client)['calls']}['0xB2']['status'] == 'Closed'
    bad = client.put('/api/non-qualified-calls/status-rules', json={'rules': [{'status': 'Nope', 'conditions': []}]})
    assert bad.status_code == 400


def test_default_statuses_replace_statuses_the_rules_gave_but_not_those_set_by_hand(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    state = client.get('/api/non-qualified-calls/state').json()
    teams = [{**item, 'previous': item['name'], 'members': []} for item in state['options']['teams']]
    renamed = [{**item, 'previous': item['name'], 'name': 'Analysis Started' if item['name'] == 'Under Analysis' else item['name']}
               for item in state['options']['statuses']]
    assert client.put('/api/non-qualified-calls/options', json={'statuses': renamed, 'teams': teams}).status_code == 200
    by_rules = patch(client, calls['0xA1'], {'fields': {'analysis_status': 'Ongoing'}})
    by_hand = patch(client, calls['0xB2'], {'status': 'Analysis Started'})
    assert (by_rules['status'], by_rules['status_mode'], by_hand['status_mode']) == ('Analysis Started', 'auto', 'manual')
    current = {item['name'] for item in renamed}
    defaults = [{**item, 'previous': item['name'] if item['name'] in current else ''} for item in state['default_options']['statuses']]
    response = client.put('/api/non-qualified-calls/options', json={'statuses': defaults, 'teams': teams})
    assert response.status_code == 400 and 'set by hand on 1 call' in response.text
    patch(client, calls['0xB2'], {'status_mode': 'auto'})
    assert client.put('/api/non-qualified-calls/options', json={'statuses': defaults, 'teams': teams}).status_code == 200
    statuses = [item['name'] for item in client.get('/api/non-qualified-calls/state').json()['options']['statuses']]
    assert statuses == [item['name'] for item in state['default_options']['statuses']]
    # The call the rules had moved follows them again.
    assert {item['join_id']: item for item in query(client)['calls']}['0xA1']['status'] in statuses


def test_each_configuration_goes_back_to_the_values_of_a_new_workspace(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    events = lambda action: [row['details'] for row in repository.list_logs() if row['action'] == action]
    state = client.get('/api/non-qualified-calls/state').json()
    defaults = state['default_fields']
    assert [field['key'] for field in defaults] == [field['key'] for field in nq_catalog.default_fields()]
    # Default Columns: no optional or CDR columns.
    assert client.put('/api/non-qualified-calls/table-columns', json={'builtin': ['join_id'], 'cdr': ['City']}).status_code == 200
    reset = client.put('/api/non-qualified-calls/table-columns', json={'builtin': [], 'cdr': [], 'defaults': True})
    assert reset.json()['table_columns'] == {'builtin': [], 'cdr': [], 'export_cdr': []}
    assert events('nq_table_columns')[0] == 'Non-Qualified Calls table columns restored to the default columns.'
    # Default Fields & Sections: a field that is not a default one stays while a call uses it.
    fields = [*state['fields'], {'label': 'Custom Note', 'section': 'analysis', 'type': 'text', 'source': 'user', 'options': []}]
    assert client.put('/api/non-qualified-calls/fields', json={'fields': fields}).status_code == 200
    patch(client, calls['0xA1'], {'fields': {'custom_note': 'Kept'}})
    sections = [{**section, 'label': f"{section['label']} X"} for section in state['default_sections']]
    assert client.put('/api/non-qualified-calls/sections', json={'sections': sections}).status_code == 200
    refused = client.put('/api/non-qualified-calls/fields', json={'fields': defaults, 'defaults': True})
    assert refused.status_code == 400 and 'Custom Note' in refused.text
    patch(client, calls['0xA1'], {'fields': {'custom_note': ''}})
    assert client.put('/api/non-qualified-calls/fields', json={'fields': defaults, 'defaults': True}).status_code == 200
    assert client.put('/api/non-qualified-calls/sections', json={'sections': state['default_sections'], 'defaults': True}).status_code == 200
    after = client.get('/api/non-qualified-calls/state').json()
    assert [field['key'] for field in after['fields']] == [field['key'] for field in defaults]
    assert after['sections'] == state['default_sections']
    assert events('nq_analysis_fields')[0] == 'Non-Qualified Calls field catalog restored to the default fields.'
    assert events('nq_sections')[0] == 'Non-Qualified Calls sections restored to the default sections.'
    # Default Catalog: a root category that is not a default one stays while a call uses it.
    root = client.get('/api/non-qualified-calls/root-causes').json()
    root['categories'] = [*({**item, 'previous': item['name']} for item in root['categories']),
                          {'name': 'Custom Category', 'domain': '', 'keywords': ''}]
    assert client.put('/api/non-qualified-calls/root-causes', json={**root, 'require_to_close': True}).status_code == 200
    patch(client, calls['0xA1'], {'root_category': 'Custom Category'})
    catalog = {**state['root_cause_defaults'], 'require_to_close': False, 'defaults': True}
    refused = client.put('/api/non-qualified-calls/root-causes', json=catalog)
    assert refused.status_code == 400 and 'Custom Category' in refused.text
    patch(client, calls['0xA1'], {'root_category': ''})
    saved = client.put('/api/non-qualified-calls/root-causes', json=catalog)
    assert saved.status_code == 200, saved.text
    assert [item['name'] for item in saved.json()['categories']] == [item['name'] for item in state['root_cause_defaults']['categories']]
    assert saved.json()['require_to_close'] is False
    assert events('nq_root_causes')[0] == 'Non-Qualified Calls root cause catalog restored to the default catalog.'
    # Default Equivalences: the import uses only those of the tool again.
    repository.set_workspace_state(nq.ANALYSES_EQUIVALENCES_STATE_KEY, json.dumps(
        {'field:analysis_status': {'done': {'value': 'Done', 'to': 'Finished', 'domain': ''}}}))
    assert client.delete('/api/non-qualified-calls/analyses/equivalences').json() == {'forgotten': 1}
    assert nq.workspace_equivalences(repository) == {}
    assert json.loads(events('nq_analyses_equivalences_reset')[0]) == {'forgotten': 1}
    # Only admins and super-admins import analyses and forget their equivalences.
    token = 'defaults-editor'
    core.SESSIONS[token] = core.SessionUser(username='editor', role='user-editor')
    client.cookies.set(core.SESSION_COOKIE, token)
    assert client.delete('/api/non-qualified-calls/analyses/equivalences').status_code == 403


def excel_headers(client) -> list[str]:
    exported = client.post('/api/non-qualified-calls/export', json={'filters': {}})
    assert exported.status_code == 200, exported.text
    return [cell.value for cell in load_workbook(io.BytesIO(exported.content))['NQ Calls'][2]]


def test_only_admins_change_the_configuration_and_every_user_has_a_table_layout(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    workspace_user('editor', 'user-editor')
    workspace_user('viewer', 'user-viewer')
    events = lambda action: [row['details'] for row in repository.list_logs() if row['action'] == action]
    state = client.get('/api/non-qualified-calls/state').json()
    assert state['user']['can_configure'] is True and state['table_layout']['view'] == 'workspace'
    assert state['table_layout']['mine'] is None and state['table_layout']['effective'] == state['table_layout']['workspace']
    # The NQ Analysis Configuration: admins and super-admins only.
    login(client, 'editor', 'editor123')
    refused = {
        ('put', '/api/non-qualified-calls/options'): {'statuses': state['options']['statuses'], 'teams': state['options']['teams']},
        ('put', '/api/non-qualified-calls/fields'): {'fields': state['fields']},
        ('put', '/api/non-qualified-calls/sections'): {'sections': state['sections']},
        ('put', '/api/non-qualified-calls/status-rules'): {'rules': state['status_rules']},
        ('put', '/api/non-qualified-calls/root-causes'): {'domains': [], 'categories': [], 'causes': []},
        ('put', '/api/non-qualified-calls/table-columns'): {'builtin': ['join_id']},
        ('post', '/api/non-qualified-calls/analysts/assign'): {'assignments': {}},
        ('post', '/api/non-qualified-calls/root-causes/apply-categories'): {'preview': True},
        ('post', '/api/non-qualified-calls/table-layout/publish'): None,
    }
    for (method, path), body in refused.items():
        response = getattr(client, method)(path, **({'json': body} if body is not None else {}))
        assert response.status_code == 403 and 'admins and super-admins' in response.text, path
    assert client.delete('/api/non-qualified-calls/rca').status_code == 403
    # They see it, locked under a card, and their own table layout.
    page = client.get('/non-qualified-calls').text
    assert 'Only admins and super-admins can change the NQ Analysis Configuration.' in page
    assert 'Only admins and super-admins can change the fields and sections.' in page
    assert page.count('class="nq-config-fieldset" disabled') >= 8
    for save in ('nq-options-save', 'nq-fields-save', 'nq-root-save', 'nq-status-rules-save'):
        assert f'id="{save}" hidden>Save</button>' in page, save
    assert 'id="nq-columns-open"' in page and 'id="nq-layout-publish"' not in page
    # Their layout: only for them, from the workspace one, with a CDR column and Priority in the table and in Excel.
    saved = client.put('/api/non-qualified-calls/table-layout/mine', json={
        'cdr': ['Cell_ID_A'], 'fields': ['analysis_status', 'priority'], 'excel_fields': ['analysis_status', 'priority', 'comments'],
        'order': ['field:priority', 'start_time']})
    assert saved.status_code == 200, saved.text
    layouts = saved.json()['table_layout']
    assert layouts['view'] == 'mine' and layouts['effective']['cdr'] == ['Cell_ID_A']
    assert layouts['effective']['fields'] == ['priority', 'analysis_status'] and layouts['effective']['order'][0] == 'field:priority'
    assert layouts['workspace'] == state['table_layout']['workspace']
    assert 'Cell_ID_A' in nq.indexed_cdr_columns(repository)
    headers = excel_headers(client)
    assert 'Cell_ID_A' in headers and 'Priority' in headers and 'Findings' not in headers
    # Workspace: the layout of every user; Mine keeps theirs.
    switched = client.put('/api/non-qualified-calls/table-layout/view', json={'view': 'workspace'}).json()['table_layout']
    assert switched['view'] == 'workspace' and switched['mine']['cdr'] == ['Cell_ID_A']
    assert 'Cell_ID_A' not in excel_headers(client) and 'Findings' in excel_headers(client)
    # Removing a CDR column keeps it indexed, so the CDRs are not indexed again.
    client.put('/api/non-qualified-calls/table-layout/mine', json={'cdr': []})
    assert 'Cell_ID_A' in nq.indexed_cdr_columns(repository)
    # A user-viewer has their own layout too, and opens the configuration to see it like the editors.
    login(client, 'viewer', 'viewer123')
    assert client.put('/api/non-qualified-calls/table-layout/mine', json={'builtin': ['join_id']}).status_code == 200
    assert client.put('/api/non-qualified-calls/fields', json={'fields': state['fields']}).status_code == 403
    page = client.get('/non-qualified-calls').text
    assert 'id="nq-config-toggle"' in page and 'Only admins and super-admins can change the NQ Analysis Configuration.' in page
    for dialog in ('nq-options-dialog', 'nq-fields-dialog', 'nq-root-dialog', 'nq-status-rules-dialog', 'nq-rca-dialog',
                   'nq-assign-analysts-dialog', 'nq-analyses-dialog'):
        assert f'id="{dialog}"' in page, dialog
    assert page.count('class="nq-config-fieldset" disabled') >= 10 and 'data-nq-status-rules-open title=' in page
    for path in ('/api/non-qualified-calls/analysts', '/api/non-qualified-calls/analyses/template',
                 '/api/non-qualified-calls/analyses/equivalences'):
        assert client.get(path).status_code == 200, path
    assert client.post('/api/non-qualified-calls/analysts/assign', json={'assignments': {}}).status_code == 403
    assert client.post('/api/non-qualified-calls/analysts/assign', json={'assignments': {}, 'preview': True}).status_code == 200
    # Admins save their layout for the workspace: its columns, the Table column and Excel of the fields and the order.
    login(client)
    client.put('/api/non-qualified-calls/table-layout/mine', json={'builtin': ['cell_id'], 'fields': ['priority'],
                                                                   'order': ['operator', 'start_time']})
    published = client.post('/api/non-qualified-calls/table-layout/publish')
    assert published.status_code == 200, published.text
    workspace = published.json()['table_layout']['workspace']
    assert workspace['builtin'] == ['cell_id'] and workspace['fields'] == ['priority'] and workspace['order'] == ['operator', 'start_time']
    assert {field['key']: field['in_table'] for field in nq.list_fields(repository)}['priority'] is True
    # The CDR columns no layout shows any more leave the index with the next change of the workspace columns.
    assert 'Cell_ID_A' not in nq.indexed_cdr_columns(repository)
    login(client, 'editor', 'editor123')
    client.put('/api/non-qualified-calls/table-layout/view', json={'view': 'workspace'})
    assert client.get('/api/non-qualified-calls/state').json()['table_layout']['effective']['builtin'] == ['cell_id']
    # Every action is in App Events.
    assert any(item.startswith('Non-Qualified Calls table layout of editor saved: ') for item in events('nq_table_layout'))
    assert 'switched to the workspace layout' in events('nq_table_layout_view')[0]
    assert 'of super saved for the workspace: 1 call columns' in events('nq_table_layout_publish')[0]


def test_workspaces_before_the_layouts_get_the_table_of_the_user_layouts(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    with repository.connection() as connection:
        connection.execute(f'DROP TABLE {nq.NQ_USER_LAYOUTS_TABLE}')
    repository.set_workspace_state(nq.SCHEMA_STATE_KEY, '2026-10-16.2')
    nq.ensure_nq_tables(repository)
    assert nq.save_user_layout(repository, 'super', {'builtin': ['join_id']})['effective']['builtin'] == ['join_id']


def test_transfers_take_the_layouts_and_settings_of_the_package(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    # The source: its columns (also for Excel only), a layout of its own, the Priority in the table and first, a
    # suggestion rule of its own and a root category required to close a call.
    nq.save_table_columns(repository, ['join_id'], ['Technology'], 'super', ['Vendor'])
    nq.save_user_layout(repository, 'super', {'builtin': ['cell_id'], 'order': ['operator']})
    nq.save_user_layout(repository, 'ghost', {'cdr': ['Vendor']})
    nq.publish_user_layout(repository, 'super')
    nq.save_user_layout(repository, 'super', {'builtin': ['nr_mode']})
    fields = nq.list_fields(repository)
    priority = next(field for field in fields if field['key'] == 'priority')
    fields = [priority, *(field for field in fields if field['key'] != 'priority')]
    priority['in_table'], priority['section'] = True, 'analysis'
    nq._store_fields(repository, fields)
    rule = {**nq.DEFAULT_ROOT_CAUSE_RULE, 'comments': not nq.DEFAULT_ROOT_CAUSE_RULE['comments']}
    repository.set_workspace_state(nq.ROOT_CAUSE_RULE_STATE_KEY, json.dumps(rule))
    root = nq.list_root_causes(repository)
    nq.save_root_causes(repository, {kind: [{**item, 'previous': item['name']} for item in root[kind]]
                                     for kind in ('domains', 'categories', 'causes')}, True, 'super')
    document = nq.export_configuration_document(repository)
    source = nq.table_layouts(repository, 'super')
    # The destination has its own of everything.
    nq.save_table_columns(repository, ['end_time'], [], 'super')
    nq.save_user_layout(repository, 'super', {'builtin': ['direction'], 'order': []})
    nq.set_layout_view(repository, 'super', 'workspace')
    repository.set_workspace_state(nq.COLUMN_ORDER_STATE_KEY, '[]')
    repository.set_workspace_state(nq.ROOT_CAUSE_RULE_STATE_KEY, json.dumps(nq.DEFAULT_ROOT_CAUSE_RULE))
    repository.set_workspace_state(nq.ROOT_CAUSE_SETTINGS_STATE_KEY, json.dumps({'require_to_close': False}))
    nq._store_fields(repository, [{**field, 'in_table': False, 'section': 'general'} if field['key'] == 'priority' else field
                                  for field in sorted(fields, key=lambda field: field['key'] == 'priority')])
    # The import takes the package: nothing of the destination stays in its way.
    nq.import_configuration_document(repository, document)
    taken = nq.table_layouts(repository, 'super')
    assert taken['workspace'] == source['workspace'] and taken['mine'] == source['mine'] and taken['view'] == 'mine'
    assert nq.table_layouts(repository, 'ghost')['mine']['cdr'] == ['Vendor']
    imported = nq.list_fields(repository)
    assert imported[0]['key'] == 'priority' and imported[0]['in_table'] is True and imported[0]['section'] == 'analysis'
    assert json.loads(repository.get_workspace_state(nq.ROOT_CAUSE_RULE_STATE_KEY)) == nq.normalize_root_cause_rule(rule)
    assert nq.list_root_causes(repository)['require_to_close'] is True
    assert 'Vendor' in nq.indexed_cdr_columns(repository)
    assert any('(ghost, super) taken from an imported configuration' in row['details']
               for row in repository.list_logs() if row['action'] == 'nq_table_layout')


def test_root_category_and_cause_are_independent_and_set_the_domain(client, tmp_path):
    call = setup_calls(client, tmp_path)['0xA1']
    updated = patch(client, call, {'root_category': 'Poor Coverage LTE', 'root_cause': 'Tunnel Issue'})
    assert (updated['root_category'], updated['root_cause'], updated['root_domain']) == ('Poor Coverage LTE', 'Tunnel Issue', 'RF')
    assert client.patch(f"/api/non-qualified-calls/calls/{call['call_key']}", json={'changes': {'root_cause': 'Unknown cause'}}).status_code == 400
    # Renamed catalog values follow on the calls; values in use cannot be removed.
    root = client.get('/api/non-qualified-calls/root-causes').json()
    for item in root['categories']:
        item['previous'] = item['name']
        if item['name'] == 'Poor Coverage LTE':
            item['name'], item['domain'] = 'LTE Coverage', 'RAN'
    response = client.put('/api/non-qualified-calls/root-causes', json=root)
    assert response.status_code == 200, response.text
    updated = client.get(f"/api/non-qualified-calls/calls/{call['call_key']}").json()['call']
    assert (updated['root_category'], updated['root_domain']) == ('LTE Coverage', 'RAN')
    root = client.get('/api/non-qualified-calls/root-causes').json()
    root['causes'] = [item for item in root['causes'] if item['name'] != 'Tunnel Issue']
    assert client.put('/api/non-qualified-calls/root-causes', json=root).status_code == 400


def test_rca_script_results_are_imported_by_join_id_and_recommend_the_root_cause(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    csv = ('JOIN_ID;Auto_RCA_Category_A;Auto_RCA_Subcategory_A;RCA_Suggested_Category;RCA_Suggested_Cause;Confidence\n'
           '0xa1;RF;Coverage;Poor Coverage LTE;NLOS due to clutter or terrain profile;0.9\n'
           '0xUNKNOWN;RF;Coverage;Poor Coverage LTE;LOS but weak signal;0.4\n').encode()
    preview = client.post('/api/non-qualified-calls/rca/import', data={'preview': '1'},
                          files={'file': ('rca.csv', io.BytesIO(csv), 'text/csv')}).json()
    assert (preview['rows'], preview['matched'], preview['unmatched']) == (2, 1, 1)
    assert preview['extra'] == ['Confidence'] and client.get('/api/non-qualified-calls/rca').json()['total'] == 0
    imported = client.post('/api/non-qualified-calls/rca/import', files={'file': ('rca.csv', io.BytesIO(csv), 'text/csv')})
    assert imported.status_code == 200 and client.get('/api/non-qualified-calls/rca').json()['matched'] == 1
    call = {item['join_id']: item for item in query(client)['calls']}['0xA1']
    assert call['values']['rca_suggested_category'] == 'Poor Coverage LTE'
    assert call['values']['netcheck_suggested_cause'] == 'DL coverage problems'
    assert call['values']['session_type'] == 'CALL'
    recommendation = call['rca_recommendation']
    sources = {source['source']: source for source in recommendation['sources']}
    # The RCA script and NetCheck (mapped by keywords) agree on the category.
    assert sources['script']['category'] == 'Poor Coverage LTE' and sources['netcheck']['category'] == 'Poor Coverage LTE'
    assert recommendation['recommendation']['category'] == 'Poor Coverage LTE'
    # NetCheck weighs more, so its cause wins among the sources that agree on the category.
    assert recommendation['recommendation']['cause'] == sources['netcheck']['cause'] == 'Coverage'
    assert recommendation['recommendation']['confidence'] == 'high'
    # Accepting the recommendations of several calls at once.
    keys = [calls['0xA1']['call_key'], calls['0xB2']['call_key']]
    assert client.post('/api/non-qualified-calls/calls/bulk', json={'call_keys': keys, 'changes': {'apply_recommendation': True}}).json() == {'changed': 2}
    decided = {item['join_id']: item for item in query(client)['calls']}
    assert decided['0xA1']['root_category'] == 'Poor Coverage LTE'
    assert decided['0xB2']['root_category'] == 'DL Interference LTE' and decided['0xB2']['root_cause'] == 'DL interference'
    # Previous decisions teach the recommendation of calls with the same NetCheck values.
    learned = nq.learned_decisions(sqlite3.connect(core.repository.db_path, factory=_RowConnection))
    assert learned[nq_rca.learned_key('netcheck', 'Coverage problem', 'DL coverage problems')] == {
        ('Poor Coverage LTE', 'Coverage'): {calls['0xA1']['call_key']}}
    # A decision never teaches the call that made it.
    assert 'learned' not in {source['source'] for source in decided['0xA1']['rca_recommendation']['sources']}
    # Filtering and sorting by catalog fields of any source.
    filtered = query(client, filters={'fields': {'rca_suggested_category': ['Poor Coverage LTE']}})
    assert [item['join_id'] for item in filtered['calls']] == ['0xA1']
    derived = query(client, filters={'fields': {'session_type': ['MULTI-RAB']}})
    assert [item['join_id'] for item in derived['calls']] == ['0xC3']
    ordered = query(client, sort='field:session_type', direction='asc')['calls']
    assert [item['values']['session_type'] for item in ordered] == ['CALL', 'MULTI-RAB', 'WhatsApp']
    assert client.delete('/api/non-qualified-calls/rca').json()['deleted'] == 2


class _RowConnection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.row_factory = sqlite3.Row


def test_lifecycle_and_rca_insights_compare_the_three_sources(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    csv = 'JOIN_ID,RCA_Suggested_Category,RCA_Suggested_Cause\n0xA1,Poor Coverage LTE,LOS but weak signal\n0xB2,E2E,Potential E2E Issue\n'
    client.post('/api/non-qualified-calls/rca/import', files={'file': ('rca.csv', io.BytesIO(csv.encode()), 'text/csv')})
    patch(client, calls['0xA1'], {'root_category': 'Poor Coverage LTE', 'root_cause': 'LOS but weak signal'})
    patch(client, calls['0xB2'], {'root_category': 'DL Interference LTE', 'fields': {'analysis_status': 'Ongoing'}})
    insights = client.post('/api/non-qualified-calls/rca/insights', json={'filters': {}}).json()
    assert insights['coverage'] == {'total': 3, 'script': 2, 'netcheck': 3, 'selected': 2}
    assert insights['agreement']['selected_script'] == {'agree': 1, 'compared': 2, 'rate': 50.0}
    assert insights['agreement']['selected_netcheck']['agree'] == 2
    assert insights['confusion']['script']['rows'] and insights['domains']['selected'][0]['domain'] == 'RF'
    # The root domains of each source count the calls it covers.
    assert sum(item['count'] for item in insights['domains']['script']) == 2
    assert sum(item['count'] for item in insights['domains']['netcheck']) == 3
    assert insights['hierarchies']['netcheck'][0]['causes']
    # Each category of a hierarchy names the root domains its calls fall in.
    selected = {group['category']: group['domains'] for group in insights['hierarchies']['selected']}
    assert [item['domain'] for item in selected['Poor Coverage LTE']] == ['RF']
    assert all(group['domains'] for name in ('netcheck', 'script') for group in insights['hierarchies'][name])
    # And so does each category of the catalog a source translates its own onto.
    assert {item['category']: [domain['domain'] for domain in item['domains']] for item in insights['mapped']['script']}[
        'Poor Coverage LTE'] == ['RF']
    lifecycle = client.post('/api/non-qualified-calls/lifecycle', json={'filters': {}}).json()
    pipeline = {item['status']: item['count'] for item in lifecycle['pipeline']}
    assert pipeline['Under Analysis'] == 2 and 'Open' not in pipeline and pipeline['Not Attended'] == 1
    # Open is the sum of the statuses of the attended calls not closed yet.
    assert lifecycle['open_statuses'] == ['Under Analysis', 'Under Implementation', 'Under Planning']
    assert lifecycle['open'] == sum(pipeline[name] for name in lifecycle['open_statuses'])
    # Not Attended: the calls in the first status, with its colour.
    assert lifecycle['not_attended'] == {'status': 'Not Attended', 'count': pipeline['Not Attended'], 'color': '#9aa5ad'}
    # The stalled calls are open ones: the call not attended, months old, is not stalled.
    assert lifecycle['stalled_total'] <= lifecycle['open']
    assert all(item['status'] in lifecycle['open_statuses'] for item in lifecycle['stalled'])
    # The Stalled card filters the calls it counts: an open call last changed months ago.
    with core.repository.connection() as connection:
        connection.execute(f"UPDATE {nq.NQ_CALL_TRACKING_TABLE} SET updated_at = '2026-01-05T10:00:00+01:00' "
                           "WHERE status = 'Under Analysis' AND call_key = (SELECT MIN(call_key) FROM "
                           f"{nq.NQ_CALL_TRACKING_TABLE} WHERE status = 'Under Analysis')")
    life = client.post('/api/non-qualified-calls/lifecycle', json={'filters': {}}).json()
    stalled = client.post('/api/non-qualified-calls/lifecycle', json={'filters': {'state': ['stalled']}}).json()
    assert life['stalled_total'] == 1 and stalled['total'] == stalled['stalled_total'] == 1
    assert [call['call_key'] for call in query(client, filters={'state': ['stalled']})['calls']] == [life['stalled'][0]['call_key']]
    # The Follow-up filter takes the calls in any of the states chosen.
    closed_or_stalled = query(client, filters={'state': ['stalled', 'closed']})['total']
    assert closed_or_stalled == 1 + query(client, filters={'state': ['closed']})['total']
    assert query(client, filters={'state': ['attended', 'not_attended']})['total'] == life['total']
    # Open: the calls the Open card counts, in one filter.
    assert query(client, filters={'state': ['open']})['total'] == life['open']
    assert query(client, filters={'state': ['open']})['total'] == query(client, filters={'status': life['open_statuses']})['total']
    phases = {phase['key']: phase for phase in lifecycle['phases']}
    assert next(item['count'] for item in phases['analysis_status']['items'] if item['value'] == 'Ongoing') == 1
    assert lifecycle['modes'] == {'auto': 3, 'manual': 0}
    assert any(move['to'] == 'Under Analysis' for move in lifecycle['moves'])
    # A field whose values have no colour takes the palette, one colour per value.
    proposals = [item['color'] for item in phases['implementation_proposal']['items']]
    assert all(proposals) and len(set(proposals)) == len(proposals)
    assert [item['color'] for item in phases['analysis_status']['items']] == [
        option['color'] for field in nq.list_fields(core.repository) if field['key'] == 'analysis_status' for option in field['options']]
    assert len(set(visuals.series_colours(45))) == 45
    # In the documents a field with many values has a slide of its own after the others.
    proposal = phases['implementation_proposal']
    many = [{'value': f'Proposal {index}', 'count': index, 'color': colour}
            for index, colour in enumerate(visuals.series_colours(visuals.WIDE_PHASE_VALUES + 1))]
    wide = {**lifecycle, 'phases': [*lifecycle['phases'], {**proposal, 'label': 'Implementation Proposals', 'items': many}]}
    assert [subtitle for subtitle, _image in visuals._phases_panels(lifecycle, {})] == ['Phases']
    assert [subtitle for subtitle, _image in visuals._phases_panels(wide, {})] == ['Phases', 'Implementation Proposals']
    # Both panels are slides of the PowerPoint export.
    document = client.post('/api/non-qualified-calls/export/powerpoint', json={'filters': {}})
    assert document.status_code == 200


def test_excel_export_groups_the_catalog_by_section_with_its_colours(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    call = calls['0xA1']
    client.post(f"/api/non-qualified-calls/calls/{call['call_key']}/comments", json={'body': 'First look'})
    client.post(f"/api/non-qualified-calls/calls/{call['call_key']}/comments", json={'body': 'Coverage hole'})
    patch(client, call, {'fields': {'findings': 'Hill behind the site', 'tunnel_failure': 'No'}})
    sheet = load_workbook(io.BytesIO(client.post('/api/non-qualified-calls/export', json={'filters': {}}).content))['NQ Calls']
    sections = [cell.value for cell in sheet[1] if cell.value]
    assert sections[:3] == ['CALL', 'RCA', 'GENERAL'] and sections[-4:-1] == ['ANALYSIS', 'IMPLEMENTATION', 'PLANNING']
    headers = [cell.value for cell in sheet[2]]
    # The catalog in its order, each field after its section title, with the follow-up companions.
    assert headers.index('NetCheck RCA Suggested Cause') < headers.index('Ericsson RCA Category A') < headers.index('Selected Root Cause') \
        < headers.index('NQ Call Status') \
        < headers.index('Session Type') < headers.index('Findings') < headers.index('Planned Date')
    # JOIN_ID and the call key first; the root cause decision ends the RCA block; the last update last.
    assert headers[:3] == ['JOIN_ID', 'Call Key', 'CDR'] and headers[-2:] == ['Updated By', 'Updated At']
    selected = headers.index('Selected Root Category')
    assert headers[selected - 4:selected] == ['Root Domain', 'Recommended Root Category', 'Recommended Root Cause',
                                              'Recommendation Sources'] and headers[selected + 1] == 'Selected Root Cause'
    assert headers[headers.index('NQ Call Status') + 1] == 'Status Set'
    # The status of each block and the fields read most stand out, darker than their section, whose other fields share one
    # shade (also those from the CDR or derived); the long texts of the analysis in wider columns.
    fill = lambda label: sheet.cell(2, headers.index(label) + 1).fill.fgColor.rgb[-6:]
    assert fill('NQ Call Status') == nq._tint('#0070C0', nq.KEY_FIELD_TINT) != fill('Status Set')
    assert fill('Status Set') == fill('Priority') == fill('Team Responsible') == nq._tint('#0070C0', nq.FIELD_TINT)
    assert fill('Session Type') == fill('Last Cell ID') == fill('Band when Failure')
    assert fill('Analysis Status') == nq._tint('#7030A0', nq.KEY_FIELD_TINT)
    assert fill('Findings') == fill('Description') == fill('Proposed Measure') == fill('Analysis Status') != fill('Tunnel Failure')
    assert fill('Selected Root Category') == fill('Selected Root Cause') == nq._tint('#FFC000', nq.KEY_FIELD_TINT) \
        != fill('Initial Root Category')
    assert fill('Comments') == fill('NQ Call Status') != fill('Priority')
    assert fill('Failure Comment') == nq._tint('#FF0000', nq.KEY_FIELD_TINT) != fill('Band when Failure')
    assert fill('JOIN_ID') == fill('Call Key') == nq._tint('#5E6B75', nq.KEY_FIELD_TINT) != fill('CDR')
    width = lambda label: sheet.column_dimensions[sheet.cell(2, headers.index(label) + 1).column_letter].width
    assert width('Findings') == width('Description') == width('Proposed Measure') == 50 and width('Tunnel Failure') < 30
    assert fill('Implementation Status') == nq._tint('#00B050', nq.KEY_FIELD_TINT)
    assert fill('Planned Status') == nq._tint('#00843D', nq.KEY_FIELD_TINT)
    rca_fill = sheet.cell(1, headers.index('NetCheck RCA Failure Classification') + 1).fill.fgColor.rgb
    assert rca_fill.endswith('FFC000')
    rows = [dict(zip(headers, (cell.value for cell in row))) for row in sheet.iter_rows(min_row=3)]
    row = next(item for item in rows if item['JOIN_ID'] == '0xA1')
    assert row['Findings'] == 'Hill behind the site' and row['Tunnel Failure'] == 'No'
    comments = row['Comments'].split('\n')
    assert len(comments) == 2 and comments[0].endswith('super: First look') and comments[1].endswith('super: Coverage hole')
    assert row['NetCheck RCA Suggested Cause'] == 'DL coverage problems' and row['Session Type'] == 'CALL'



def test_excel_export_keeps_the_comments_and_changes_of_each_call_together(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    for join_id, body in (('0xB2', 'First on B'), ('0xA1', 'Only on A'), ('0xB2', 'Second on B')):
        assert client.post(f"/api/non-qualified-calls/calls/{calls[join_id]['call_key']}/comments", json={'body': body}).status_code == 200
    workbook = load_workbook(io.BytesIO(client.post('/api/non-qualified-calls/export', json={'filters': {}}).content))
    order = [row[0] for row in list(workbook['NQ Calls'].values)[2:]]
    comments = [(row[0], row[5]) for row in list(workbook['Comments'].values)[1:]]
    # In the order of the calls of the NQ Calls sheet, each call by date.
    expected = sorted([('0xB2', 'First on B'), ('0xA1', 'Only on A'), ('0xB2', 'Second on B')], key=lambda item: order.index(item[0]))
    assert comments == expected

def test_catalog_workbook_round_trip_and_the_meeting_layout(client, tmp_path):
    setup_calls(client, tmp_path)
    exported = client.get('/api/non-qualified-calls/catalog/export')
    assert exported.status_code == 200
    workbook = load_workbook(io.BytesIO(exported.content))
    assert {'About', 'Sections', 'Fields', 'Lists', 'Root Catalog', 'Statuses and Teams', 'Status Rules'} <= set(workbook.sheetnames)
    fields = workbook['Fields']
    fields.append([38, 'Analysis', 'Drive Route', '', 'list', 'user', '', 'Yes', 'Yes', 'Yes', 'No', '', 'Route of the retest'])
    workbook['Lists'].append(['Drive Route', 'M25', '#123456', ''])
    workbook['Lists'].append(['Drive Route', 'A1', '', ''])
    workbook['Root Catalog'].append(['Root Cause', 'Fibre cut', 'Operational', '', 'fibre'])
    workbook['Statuses and Teams'].append(['Team', 'Field Team', '#0f6f7d', '', ''])
    output = io.BytesIO()
    workbook.save(output)
    preview = client.post('/api/non-qualified-calls/catalog/import', data={'preview': '1'},
                          files={'workbook': ('catalog.xlsx', io.BytesIO(output.getvalue()))}).json()
    assert preview['added'] == ['Drive Route'] and preview['root_added']['causes'] == ['Fibre cut']
    assert preview['teams_added'] == ['Field Team']
    imported = client.post('/api/non-qualified-calls/catalog/import', files={'workbook': ('catalog.xlsx', io.BytesIO(output.getvalue()))})
    assert imported.status_code == 200, imported.text
    route = next(field for field in imported.json()['fields'] if field['label'] == 'Drive Route')
    assert [option['name'] for option in route['options']] == ['M25', 'A1'] and route['section'] == 'analysis' and route['in_table']
    assert len(imported.json()['fields']) == 65
    # The workbook of the meeting: sections in the first row, fields in the second, values below.
    meeting = Workbook()
    sheet = meeting.active
    sheet.append(['FAILURE EVENT', None, 'PLANNING'])
    sheet.append(['Band when Failure', 'Weather', 'Planned Date'])
    sheet.append(['TO BE ADDED'] * 3)
    sheet.append(['Lista customizable', 'Lista customizable', 'Fecha'])
    sheet.append(['', '', ''])
    sheet.append(['LTE2100', 'Rain', 'User Define'])
    sheet.append(['NR3500', 'Snow', None])
    output = io.BytesIO()
    meeting.save(output)
    catalog = nq_catalog.read_catalog_workbook(output.getvalue())
    by_label = {field['label']: field for field in catalog['fields']}
    assert by_label['Band when Failure']['key'] == 'band_when_failure'
    assert 'NR3500' in [option['name'] for option in by_label['Band when Failure']['options']]
    assert by_label['Weather']['section'] == 'failure_event' and [option['name'] for option in by_label['Weather']['options']] == ['Rain', 'Snow']
    assert by_label['Planned Date']['type'] == 'date' and by_label['Planned Date']['section'] == 'planning'


def test_tracking_document_carries_the_analysis_center(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    client.post('/api/non-qualified-calls/rca/import',
                files={'file': ('rca.csv', io.BytesIO(b'JOIN_ID,RCA_Suggested_Category\n0xA1,E2E\n'), 'text/csv')})
    patch(client, calls['0xA1'], {'root_category': 'E2E', 'status': 'Under Planning'})
    sections = client.get('/api/non-qualified-calls/state').json()['sections']
    sections[0]['label'] = 'Overview'
    assert client.put('/api/non-qualified-calls/sections', json={'sections': sections}).status_code == 200
    document = json.loads(nq.export_tracking_document(core.repository))
    assert document['version'] == 3 and document['sections'][0]['label'] == 'Overview'
    assert document['rca_results'][0]['join_id'] == '0xA1' and document['status_rules']
    assert document['tracking'][0]['status_mode'] == 'manual' and document['tracking'][0]['root_category'] == 'E2E'
    with core.repository.connection() as connection:
        connection.execute(f'DELETE FROM {nq.NQ_RCA_RESULTS_TABLE}')
        connection.execute(f'DELETE FROM {nq.NQ_CALL_TRACKING_TABLE}')
    core.repository.set_workspace_state(nq.SECTIONS_STATE_KEY, '[]')
    assert nq.import_tracking_document(core.repository, json.dumps(document)) >= 1
    call = {item['join_id']: item for item in query(client)['calls']}['0xA1']
    assert (call['status'], call['status_mode'], call['root_category']) == ('Under Planning', 'manual', 'E2E')
    assert call['values']['rca_suggested_category'] == 'E2E'
    assert nq.list_sections(core.repository)[0]['label'] == 'Overview'


def test_tracking_documents_find_their_calls_by_join_id(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    key = calls['0xA1']['call_key']
    patch(client, calls['0xA1'], {'team': 'Netcheck', 'fields': {'analyst': 'Anudeep'}})
    assert client.post(f'/api/non-qualified-calls/calls/{key}/comments', json={'body': 'Checked'}).status_code == 200
    document = nq.export_tracking_document(core.repository).decode('utf-8')
    # Each call travels with its JOIN_ID and service.
    assert {'call_key': key, 'service': 'voice', 'join_id': '0xA1'} in json.loads(document)['calls']
    # A document whose keys were computed otherwise (a former version) still finds the call by its JOIN_ID.
    former = document.replace(key, 'feedfacefeedfacefeedface')
    with core.repository.connection() as connection:
        for table in (nq.NQ_CALL_TRACKING_TABLE, nq.NQ_CALL_COMMENTS_TABLE, nq.NQ_CALL_HISTORY_TABLE, nq.NQ_FIELD_VALUES_TABLE):
            connection.execute(f'DELETE FROM {table}')
    assert nq.import_tracking_document(core.repository, former) == 1
    detail = client.get(f'/api/non-qualified-calls/calls/{key}').json()
    assert detail['call']['team'] == 'Netcheck' and detail['call']['fields']['analyst'] == 'Anudeep'
    assert [comment['body'] for comment in detail['comments']] == ['Checked'] and detail['history']
    # A call without a JOIN_ID keeps its key, and so does a Speech sample with the key of its JOIN_ID and sample.
    assert nq._document_call_keys([{'call_key': 'abc', 'service': 'voice', 'join_id': ''}]) == {}
    sample = nq.sample_key_for(nq.call_key_for('speech', {}, join_id='0xS1'), '7')
    assert nq._document_call_keys([{'call_key': 'abc', 'service': 'speech', 'join_id': '0xS1', 'sample_id': '7'}]) == {'abc': sample}


def test_first_version_workspaces_move_to_the_analysis_center(client, tmp_path):
    enable_module()
    add_cdr(tmp_path, 'UK_Voice_Q3.xlsx', 'voice', calls_frame())
    login(client)
    repository = core.repository
    nq.ensure_nq_tables(repository)
    # The tables and defaults of the first version: its root cause taxonomy, statuses and analysis fields.
    with repository.connection() as connection:
        connection.execute(f'DROP TABLE IF EXISTS {nq.NQ_ROOT_CATALOG_TABLE}')
        connection.execute("CREATE TABLE nq_root_causes (domain TEXT, cause TEXT, color TEXT, keywords TEXT, position INTEGER)")
        connection.executemany('INSERT INTO nq_root_causes VALUES (?, ?, ?, ?, ?)', [
            ('RF', '', '#123456', '["rf"]', 0), ('RF', 'Coverage', '', '["coverage"]', 0),
            ('Transport', '', '#654321', '["backhaul"]', 1), ('Transport', 'Backhaul', '', '["backhaul"]', 0)])
        for table in (nq.NQ_FIELDS_TABLE, nq.NQ_CALL_OPTIONS_TABLE):
            connection.execute(f'DELETE FROM {table}')
        connection.executemany(f"INSERT INTO {nq.NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES (?, ?, ?, ?, ?)",
                               [('status', name, '#000000', index, int(name == 'Resolved'))
                                for index, name in enumerate(nq._FIRST_STATUSES)] +
                               [('team', name, '#000000', index, 0) for index, name in enumerate(nq._FIRST_TEAMS)])
        connection.execute(f"INSERT INTO {nq.NQ_FIELDS_TABLE} (field_key, label, field_type, options_json, position) "
                           "VALUES ('findings', 'Findings', 'long_text', '[]', 0)")
        connection.execute(f"INSERT INTO {nq.NQ_FIELD_VALUES_TABLE} (call_key, field_key, value) VALUES ('k1', 'findings', 'Old note')")
        connection.execute(f"INSERT INTO {nq.NQ_CALL_TRACKING_TABLE} (call_key, status, team, root_domain, root_cause, version) "
                           "VALUES ('k1', 'Resolved', 'Transport', 'Transport', 'Backhaul', 1)")
    repository.set_workspace_state(nq.ANALYSIS_CENTER_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    root = nq.list_root_causes(repository)
    assert {'RF', 'Transport'} <= {item['name'] for item in root['domains']}
    assert next(item for item in root['domains'] if item['name'] == 'RF')['color'] == '#123456'
    assert next(item for item in root['causes'] if item['name'] == 'Backhaul')['domain'] == 'Transport'
    with repository.connection() as connection:
        assert not connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'nq_root_causes'").fetchone()
        tracking = connection.execute(f"SELECT status, status_mode, root_cause FROM {nq.NQ_CALL_TRACKING_TABLE} WHERE call_key = 'k1'").fetchone()
    assert tuple(tracking) == ('Closed', 'manual', 'Backhaul')
    assert [item['name'] for item in nq.list_options(repository)['statuses']][0] == 'Not Attended'
    # The workspace's field keeps its key and values and takes its place in the catalog.
    findings = next(field for field in nq.list_fields(repository) if field['label'] == 'Findings')
    assert findings['key'] == 'findings' and findings['section'] == 'analysis' and len(nq.list_fields(repository)) == 64


def test_recommendation_engine_maps_each_source_onto_the_catalog():
    root = {'domains': [{'name': name, 'color': color, 'keywords': list(keywords)} for name, color, keywords in nq_catalog.DEFAULT_DOMAINS],
            'categories': [{'name': name, 'domain': domain, 'keywords': nq_catalog.keywords(list(keywords))}
                           for name, domain, keywords in nq_catalog.DEFAULT_CATEGORIES],
            'causes': [{'name': name, 'domain': domain, 'keywords': nq_catalog.keywords(list(keywords))}
                       for name, domain, keywords in nq_catalog.DEFAULT_CAUSES]}
    rule = nq.DEFAULT_ROOT_CAUSE_RULE
    call = {'failure_classification': 'RF_Problems', 'failure_category': 'Interference problem',
            'failure_subcategory': 'DL interference problems', 'technology': 'NR', 'failure_technology': '5G', 'failure_comment': ''}
    suggestion = nq_rca.suggest_from_text(call, root, rule)
    assert suggestion == {'domain': 'RF', 'category': 'DL Interference NR', 'cause': 'DL interference', 'source': 'netcheck'}
    # "a+b" keywords need every word, as whole words.
    assert nq_catalog.keyword_found(['coverage+lte'], 'dl coverage problems | lte')
    assert not nq_catalog.keyword_found(['coverage+lte'], 'dl coverage problems | nr')
    result = nq_rca.recommend(call, {'rca_category': 'UL Interference NR', 'rca_cause': 'External UL interference'}, root, rule)
    # NetCheck (weight 3) wins over the script (weight 2) when they disagree, with medium confidence; the script alone
    # gives a low one.
    assert result['recommendation']['category'] == 'DL Interference NR' and result['recommendation']['confidence'] == 'medium'
    alone = nq_rca.recommend({'technology': 'NR'}, {'rca_category': 'UL Interference NR', 'rca_cause': 'External UL interference'}, root, rule)
    assert alone['recommendation']['category'] == 'UL Interference NR' and alone['recommendation']['confidence'] == 'low'
    # Two other calls with the same NetCheck values chose a category: it is proposed once per call, never for the call itself.
    choice = ('DL Interference NR', 'DL interference')
    learned = {nq_rca.learned_key('netcheck', 'Interference problem', 'DL interference problems'): {choice: {'k1', 'k2', 'own'}},
               nq_rca.learned_key('script', 'UL Interference NR', 'External UL interference'): {choice: {'k1'}}}
    taught = nq_rca.recommend({**call, 'call_key': 'own'}, {'rca_category': 'UL Interference NR', 'rca_cause': 'External UL interference'},
                              root, rule, learned=learned)
    sources = {source['source']: source for source in taught['sources']}
    assert sources['learned']['count'] == 2 and sources['learned']['category'] == 'DL Interference NR'
    assert nq_catalog.evaluate_status(nq_catalog.default_status_rules(), {'analysis_status': 'Finished'}, 'Not Attended') == 'Closed'
    assert nq_catalog.evaluate_status(nq_catalog.default_status_rules(), {'@attended': 'Yes'}, 'Not Attended') == 'Under Analysis'


def test_calls_are_read_from_their_latest_versions_kept_up_to_date(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    # The latest version of every call is kept in a table, rebuilt when the indexed CDRs or the maps change.
    with repository.connection() as connection:
        latest = {row['call_key']: row for row in connection.execute(f'SELECT * FROM {nq.NQ_CALL_LATEST_TABLE}')}
    assert {call['call_key'] for call in calls.values()} == set(latest)
    assert latest[calls['0xA1']['call_key']]['last_cell_id'] == '123456'
    assert calls['0xA1']['values']['last_cell_id'] == '123456' and calls['0xA1']['values']['failure_comment'] == ''
    assert not nq.refresh_latest_calls(repository)
    repository.replace_operator_mapping_group('VF', 'VF Lab', ['Vodafone UK'])
    operators = {item['operator'] for item in query(client)['calls']}
    assert 'VF Lab' in operators and 'Vodafone UK' not in operators
    # A filter saved with an Operator the maps now show with another name keeps selecting its calls, also in the page.
    client.put('/api/non-qualified-calls/filters', json={'filters': {'operator': ['Vodafone UK', 'EE']}})
    assert client.get('/api/non-qualified-calls/state').json()['saved_filters']['operator'] == ['VF Lab', 'EE']
    assert query(client, filters={'operator': ['Vodafone UK']})['total'] == query(client, filters={'operator': ['VF Lab']})['total'] > 0
    # The follow-up is read as it is now.
    updated = patch(client, calls['0xC3'], {'root_category': 'E2E'})
    assert {item['join_id']: item for item in query(client)['calls']}['0xC3']['root_category'] == updated['root_category'] == 'E2E'
    # A choice of CDRs reads their own latest versions.
    dataset = str(query(client)['calls'][0]['dataset_id'])
    assert query(client, filters={'datasets': [dataset]})['total'] == 3
    # Without the Summary on screen, its breakdowns are left out.
    assert query(client, breakdowns=False)['breakdowns'] == [] and query(client)['breakdowns']
    # Once in place, the schema is checked without writing.
    assert nq._schema_ready(repository)


def test_an_assignee_brings_the_call_to_their_team(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    core.repository.create_user('analyst', 'analyst123', 'user-editor')
    user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == 'analyst')
    core.repository.set_user_workspace_access(user_id, [core.active_workspace.id])
    state = client.get('/api/non-qualified-calls/state').json()
    statuses = [{**status, 'previous': status['name']} for status in state['options']['statuses']]
    members = {'Netcheck': ['analyst'], 'Operations': ['super']}
    teams = [{**team, 'previous': team['name'], 'members': members.get(team['name'], [])} for team in state['options']['teams']]
    assert client.put('/api/non-qualified-calls/options', json={'statuses': statuses, 'teams': teams}).status_code == 200
    assert patch(client, calls['0xA1'], {'assignee': 'analyst'})['team'] == 'Netcheck'
    # Out of a team with other members, the assignee moves the call to their own team.
    other = patch(client, calls['0xB2'], {'team': 'Operations'})
    assert other['team'] == 'Operations' and patch(client, calls['0xB2'], {'assignee': 'analyst'})['team'] == 'Netcheck'


def test_analysts_become_the_asignees_of_their_calls(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    # A signum is found by the first name of its account.
    names = {'EANUDRE': ('Anudeep', 'Reddy'), 'jorge.m': ('Jorge', 'Martin')}
    for username in ('rajkumar.s', 'EANUDRE', 'ashish.a', 'ashish.b', 'jorge.m'):
        first, last = names.get(username, ('', ''))
        core.repository.create_user(username, 'analyst123', 'user-editor', first_name=first, last_name=last)
        user_id = next(int(row['id']) for row in core.repository.list_users() if row['username'] == username)
        core.repository.set_user_workspace_access(user_id, [core.active_workspace.id])
    state = client.get('/api/non-qualified-calls/state').json()
    statuses = [{**status, 'previous': status['name']} for status in state['options']['statuses']]
    teams = [{**team, 'previous': team['name'], 'members': ['super'] if team['name'] == 'Netcheck' else []}
             for team in state['options']['teams']]
    assert client.put('/api/non-qualified-calls/options', json={'statuses': statuses, 'teams': teams}).status_code == 200
    patch(client, calls['0xA1'], {'fields': {'analyst': 'Raj Kumar'}, 'team': 'Netcheck'})
    patch(client, calls['0xB2'], {'fields': {'analyst': 'rajkumar'}, 'assignee': 'super'})
    patch(client, calls['0xC3'], {'fields': {'analyst': 'Anudeep', 'reviewer': 'Jorge'}})
    # Analyst and Reviewer filter the calls by the names they hold.
    state = client.get('/api/non-qualified-calls/state').json()
    assert state['value_filter_fields'] == ['analyst', 'reviewer'] and state['user_names']['EANUDRE'] == 'Anudeep Reddy'
    assert state['default_users'] == ['super', 'admin', 'demo']
    assert state['filter_options']['field:analyst'] == ['Anudeep', 'Raj Kumar', 'rajkumar']
    assert state['filter_options']['field:reviewer'] == ['Jorge']
    assert [call['join_id'] for call in query(client, filters={'fields': {'analyst': ['Raj Kumar', 'rajkumar']}})['calls']] == ['0xB2', '0xA1']
    assert [call['join_id'] for call in query(client, filters={'fields': {'reviewer': [nq.UNASSIGNED]}})['calls']] == ['0xB2', '0xA1']
    # An analysis imported for a call whose CDR is not loaded yet waits for it.
    with core.repository.connection() as connection:
        connection.execute(f"INSERT INTO {nq.NQ_FIELD_VALUES_TABLE} (call_key, field_key, value, updated_by, updated_at) "
                           "VALUES ('waiting-call', 'analyst', 'Anudeep', 'import', '2026-09-01T10:00:00')")
    # One row per analyst or reviewer (the same letters are one name), with the user named as them; also the analyses
    # waiting for their CDR.
    listed = client.get('/api/non-qualified-calls/analysts').json()
    assert [(item['key'], item['analyst_calls'], item['reviewer_calls'], item['unassigned'], item['suggested'])
            for item in listed['people']] == [('anudeep', 2, 0, 2, 'EANUDRE'), ('rajkumar', 2, 0, 1, 'rajkumar.s'),
                                              ('jorge', 0, 1, 0, 'jorge.m')]
    assert sorted(listed['people'][1]['spellings']) == ['Raj Kumar', 'rajkumar'] and 'ashish.a' in listed['users']
    assert listed['user_names'] == {'EANUDRE': 'Anudeep Reddy', 'jorge.m': 'Jorge Martin'}
    assert nq._analyst_user(['Ashish'], listed['users']) == ''
    # The preview counts the calls without an assignee, the Analysts named as their account (when it has a name) and
    # the teams the user joins, and changes nothing.
    assignments = {'rajkumar': 'rajkumar.s', 'anudeep': 'EANUDRE'}
    preview = client.post('/api/non-qualified-calls/analysts/assign', json={'assignments': assignments, 'preview': True}).json()
    assert preview == {'calls': 3, 'assignees': 3, 'analyst_names': 2, 'reviewer_names': 0, 'waiting': 1,
                       'people': {'rajkumar': 1, 'anudeep': 2}, 'joins': [{'team': 'Netcheck', 'user': 'rajkumar.s'}]}
    assert client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()['call']['assignee'] == ''
    applied = client.post('/api/non-qualified-calls/analysts/assign', json={'assignments': assignments}).json()
    assert applied['calls'] == 3
    # The waiting analysis changes too, with its history, for when its CDR is loaded.
    with core.repository.connection() as connection:
        waiting = connection.execute(f"SELECT assignee FROM {nq.NQ_CALL_TRACKING_TABLE} WHERE call_key = 'waiting-call'").fetchone()
        analyst = connection.execute(f"SELECT value FROM {nq.NQ_FIELD_VALUES_TABLE} WHERE call_key = 'waiting-call' "
                                     "AND field_key = 'analyst'").fetchone()
        changes = {row[0] for row in connection.execute(f"SELECT field FROM {nq.NQ_CALL_HISTORY_TABLE} WHERE call_key = 'waiting-call'")}
    assert (waiting[0], analyst[0]) == ('EANUDRE', 'Anudeep Reddy') and {'assignee', 'field:analyst'} <= changes
    detail = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()
    assert (detail['call']['assignee'], detail['call']['team']) == ('rajkumar.s', 'Netcheck')
    assert any(entry['field'] == 'assignee' and entry['new_value'] == 'rajkumar.s' for entry in detail['history'])
    third = client.get(f"/api/non-qualified-calls/calls/{calls['0xC3']['call_key']}").json()
    assert (third['call']['assignee'], third['call']['team']) == ('EANUDRE', '')
    # The Analyst takes the name of the account, in the history; one without a name keeps its own.
    assert third['call']['fields']['analyst'] == 'Anudeep Reddy' and detail['call']['fields']['analyst'] == 'Raj Kumar'
    assert any(entry['field'] == 'field:analyst' and entry['old_value'] == 'Anudeep' for entry in third['history'])
    # So does the Reviewer.
    reviewed = client.post('/api/non-qualified-calls/analysts/assign', json={'assignments': {'jorge': 'jorge.m'}}).json()
    assert (reviewed['calls'], reviewed['assignees'], reviewed['reviewer_names'], reviewed['people']) == (1, 0, 1, {'jorge': 1})
    assert client.get(f"/api/non-qualified-calls/calls/{calls['0xC3']['call_key']}").json()['call']['fields']['reviewer'] == 'Jorge Martin'
    netcheck = next(team for team in nq.list_options(core.repository)['teams'] if team['name'] == 'Netcheck')
    assert sorted(netcheck['members']) == ['rajkumar.s', 'super']
    # The Asignee a call already has stays unless replaced.
    assert client.post('/api/non-qualified-calls/analysts/assign', json={'assignments': assignments}).json()['calls'] == 0
    replaced = client.post('/api/non-qualified-calls/analysts/assign', json={'assignments': assignments, 'overwrite': True}).json()
    assert replaced['calls'] == 1
    assert client.get(f"/api/non-qualified-calls/calls/{calls['0xB2']['call_key']}").json()['call']['assignee'] == 'rajkumar.s'
    assert client.get('/api/non-qualified-calls/analysts').json()['people'][0]['unassigned'] == 0
    unknown = client.post('/api/non-qualified-calls/analysts/assign', json={'assignments': {'anudeep': 'nobody'}})
    assert unknown.status_code == 400 and 'nobody' in unknown.json()['detail']


def test_each_filter_lists_the_values_the_other_filters_leave(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    patch(client, calls['0xA1'], {'fields': {'analyst': 'Raj Kumar'}, 'team': 'Netcheck'})
    values = lambda filters: client.post('/api/non-qualified-calls/filters/values', json={'filters': filters}).json()['values']
    every = values({})
    operators = sorted({call['operator'] for call in calls.values()})
    dataset = str(calls['0xA1']['dataset_id'])
    assert every['operator'] == operators and every['technology'] == ['LTE', 'NR'] and every['datasets'] == [dataset]
    assert every['field:analyst'] == ['', 'Raj Kumar'] and every['team'] == ['', 'Netcheck']
    # A filter leaves in the others only the values of its calls, and keeps all of its own.
    ee = calls['0xC3']['operator']
    chosen = values({'operator': [ee]})
    assert chosen['operator'] == operators and chosen['technology'] == ['NR'] and chosen['datasets'] == [dataset]
    assert chosen['field:analyst'] == [''] and chosen['team'] == ['']
    # The fields of the analysis too, also against the other filters.
    raj = values({'fields': {'analyst': ['Raj Kumar']}})
    assert raj['field:analyst'] == ['', 'Raj Kumar'] and raj['technology'] == ['LTE'] and raj['operator'] == [calls['0xA1']['operator']]
    assert values({'operator': [ee], 'fields': {'analyst': ['Raj Kumar']}})['datasets'] == []


def test_the_spellings_of_a_netcheck_rca_value_are_one_value(client, tmp_path):
    # The CDR writes RF_Problems and RF Problems: one value, with spaces and the capitals most calls use.
    calls = setup_calls(client, tmp_path)
    assert {calls['0xA1']['failure_classification'], calls['0xB2']['failure_classification']} == {'RF Problems'}
    state = client.get('/api/non-qualified-calls/state').json()
    assert state['filter_options']['failure_classification'] == ['RF Problems', 'VoLTE Problems']
    values = client.post('/api/non-qualified-calls/filters/values', json={'filters': {}}).json()['values']
    assert values['failure_classification'] == ['RF Problems', 'VoLTE Problems']
    # A filter saved with another spelling selects the value.
    assert [call['join_id'] for call in query(client, filters={'failure_classification': ['RF_Problems']})['calls']] == ['0xB2', '0xA1']
    client.put('/api/non-qualified-calls/filters', json={'filters': {'failure_classification': ['RF_Problems', 'RF Problems']}})
    assert client.get('/api/non-qualified-calls/state').json()['saved_filters']['failure_classification'] == ['RF Problems']
    detail = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()
    assert {version['failure_classification'] for version in detail['versions']} == {'RF Problems'}
    # A word in singular or plural is the same value too; Access keeps its double s and an acronym its capital S.
    assert nq.unified_spellings({'RF_Problems': 8, 'RF Problems': 3, 'RF problems': 1, 'Interference  problem': 2,
                                 'Interference problem': 5, 'Interference Problems': 1, 'E2E traces required': 1,
                                 'E2E Trace Required': 4, 'RAB Access': 2, 'RAB Acces': 1, 'HTTPS': 1, 'HTTP': 1}) == {
        'RF_Problems': 'RF Problems', 'RF Problems': 'RF Problems', 'RF problems': 'RF Problems',
        'Interference  problem': 'Interference problem', 'Interference problem': 'Interference problem',
        'Interference Problems': 'Interference problem', 'E2E traces required': 'E2E Trace Required',
        'E2E Trace Required': 'E2E Trace Required', 'RAB Access': 'RAB Access', 'RAB Acces': 'RAB Acces', 'HTTPS': 'HTTPS', 'HTTP': 'HTTP'}


def test_first_layout_workspaces_take_the_second_one(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    # A workspace of the first layout: its colours, names, Analysis order, no CDR fields in Failure Event.
    sections = [{**section, 'color': nq_catalog.FIRST_SECTION_COLORS.get(section['key'], section['color']),
                 'label': nq_catalog.FIRST_SECTION_LABELS.get(section['key'], section['label'])} for section in nq.list_sections(repository)]
    repository.set_workspace_state(nq.SECTIONS_STATE_KEY, json.dumps(sections))
    fields = [field for field in nq.list_fields(repository) if field['key'] not in {'last_cell_id', 'failure_comment'}]
    by_key = {field['key']: field for field in fields}
    keys = [field['key'] for field in fields]
    positions = sorted(keys.index(key) for key in nq_catalog.FIRST_ANALYSIS_ORDER)
    for position, key in zip(positions, nq_catalog.FIRST_ANALYSIS_ORDER):
        fields[position] = by_key[key]
    by_key['serving_cell_when_failure']['suggest_from'] = 'cell_id'
    nq._store_fields(repository, fields)
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V2_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    upgraded = {section['key']: section for section in nq.list_sections(repository)}
    assert upgraded['failure_event'] == {'key': 'failure_event', 'label': 'Failure Details', 'color': '#FF0000'}
    assert upgraded['implementation']['color'] == '#00B050' and upgraded['planning']['color'] == '#00843D'
    fields = nq.list_fields(repository)
    failure = [field['key'] for field in fields if field['section'] == 'failure_event']
    assert failure.index('last_cell_id') == failure.index('serving_cell_when_failure') - 1 and failure[-1] == 'failure_comment'
    assert [field['key'] for field in fields if field['section'] == 'analysis'][-2:] == ['findings', 'proposed_measure']
    assert next(field for field in fields if field['key'] == 'serving_cell_when_failure')['suggest_from'] == 'last_cell_id'



def test_workspaces_before_the_auto_rca_fields_get_them_around_the_suggestion(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    new = {'rca_initial_category', 'rca_initial_subcategory', 'rca_evidence'}
    nq._store_fields(repository, [field for field in nq.list_fields(repository) if field['key'] not in new])
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V4_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    keys = [field['key'] for field in nq.list_fields(repository)]
    assert keys[keys.index('auto_rca_subcategory_b') + 1:keys.index('rca_evidence') + 1] == [
        'rca_initial_category', 'rca_initial_subcategory', 'rca_suggested_category', 'rca_suggested_cause', 'rca_evidence']


def test_workspaces_before_the_fields_of_the_previous_analyses_get_them_in_place(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    expected = [field['key'] for field in nq.list_fields(repository)]
    nq._store_fields(repository, [field for field in nq.list_fields(repository) if field['key'] not in nq.ANALYSES_FIELD_KEYS])
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V6_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    assert [field['key'] for field in nq.list_fields(repository)] == expected


def test_workspaces_before_the_ericsson_rca_name_get_netcheck_first(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    fields = nq.list_fields(repository)
    netcheck = [field for field in fields if field['section'] == 'rca' and field['source'] == 'cdr']
    rest = [field for field in fields if field not in netcheck]
    # The earlier layout: the NetCheck fields after the script ones, with the descriptions that named the RCA script.
    place = max(position for position, field in enumerate(rest) if field['section'] == 'rca' and field['source'] == 'rca')
    rest[place + 1:place + 1] = netcheck
    rest[0]['description'] = 'Root cause category of the A side found by the RCA script (imported by JOIN_ID).'
    nq._store_fields(repository, rest)
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V5_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    upgraded = nq.list_fields(repository)
    rca = [field['key'] for field in upgraded if field['section'] == 'rca']
    assert rca[:4] == ['netcheck_failure_classification', 'netcheck_suggested_category', 'netcheck_suggested_cause', 'auto_rca_category_a']
    assert rca[-2:] == ['selected_root_category', 'selected_root_cause'] and len(upgraded) == len(fields)
    assert next(field for field in upgraded if field['key'] == 'auto_rca_category_a')['description'] == \
        'Root cause category of the A side found by the Ericsson RCA (imported by JOIN_ID).'


def test_auto_rca_summary_fills_each_side_combines_rows_and_completes_the_catalog(client, tmp_path):
    setup_calls(client, tmp_path)
    csv = ('Log_Day,JoinID,UE,RCA_Category,RCA_Subcategory,Final_RCA_Category,Final_RCA_Subcategory,LTE_Avg_PCell_RSRP,RCA_Evidence\n'
           # A call: each side has its own diagnosis and the final one, that of the call, is the same on both sides.
           '2026-09-03,0xA1,B,Mobility Issue LTE,Missing or Late Handover LTE,Poor Coverage LTE,,-98.1,Late handover on the B side.\n'
           '2026-09-03,0xA1,A,Poor Coverage LTE,,Poor Coverage LTE,,-102.3,Weak signal on the A side.\n'
           '2026-09-03,0xB2,Data,Poor Coverage LTE,,Poor Coverage LTE,,-118.0,RSRP below the threshold.\n'
           '2026-09-03,0xB2,Data,DL Interference LTE,,DL Interference LTE,,-101.0,SINR below the threshold.\n'
           '2026-09-03,0xC3,Data,Other NR,,,,,No NR condition matched.\n'
           # The same session again without its measurements: nothing to add.
           '2026-09-03,0xC3,Data,UNKNOWN,,UNKNOWN,,,Anchor Access could not be determined.\n').encode()
    preview = client.post('/api/non-qualified-calls/rca/import', data={'preview': '1'},
                          files={'file': ('RCA_Summary.csv', io.BytesIO(csv), 'text/csv')}).json()
    assert (preview['rows'], preview['matched'], preview['duplicates']) == (3, 3, 3)
    assert {'Ericsson RCA Initial Category', 'Ericsson RCA Suggested Category', 'Ericsson RCA Category B',
            'Ericsson RCA Evidence'} <= set(preview['columns'])
    # The initial category and subcategory have their own fields; the other columns stay with the call.
    assert {'LTE_Avg_PCell_RSRP', 'Log_Day'} <= set(preview['extra']) and 'RCA_Category' not in preview['extra']
    # Mobility Issue and the late handover map onto the catalog by keywords; the generic results do not.
    assert [(item['kind'], item['name'], item['domain']) for item in preview['unmapped']] == [('category', 'Other NR', 'RAN')]
    imported = client.post('/api/non-qualified-calls/rca/import', data={'add_to_catalog': '1'},
                           files={'file': ('RCA_Summary.csv', io.BytesIO(csv), 'text/csv')}).json()
    assert [item['name'] for item in imported['added_to_catalog']] == ['Other NR']
    categories = {item['name']: item for item in client.get('/api/non-qualified-calls/state').json()['root_causes']['categories']}
    assert categories['Other NR']['domain'] == 'RAN'
    calls = {item['join_id']: item for item in query(client)['calls']}
    voice = calls['0xA1']['values']
    # Each side fills its own fields with its own diagnosis; the suggestion is the final one of the call.
    assert (voice['auto_rca_category_a'], voice['auto_rca_category_b'], voice['auto_rca_subcategory_b']) == (
        'Poor Coverage LTE', 'Mobility Issue LTE', 'Missing or Late Handover LTE')
    assert (voice['rca_suggested_category'], voice['rca_suggested_cause']) == ('Poor Coverage LTE', '')
    assert (voice['rca_initial_category'], voice['rca_initial_subcategory']) == ('Poor Coverage LTE', '')
    assert voice['rca_evidence'] == 'A: Weak signal on the A side. | B: Late handover on the B side.'
    data = calls['0xB2']['values']
    assert data['rca_suggested_category'] == 'Poor Coverage LTE' and not data['auto_rca_category_a']
    assert data['rca_initial_category'] == 'Poor Coverage LTE'
    assert data['rca_evidence'] == ('1 (Poor Coverage LTE): RSRP below the threshold. | '
                                    '2 (DL Interference LTE): SINR below the threshold.')
    # A row without a final category keeps the preliminary one.
    assert calls['0xC3']['values']['rca_suggested_category'] == calls['0xC3']['values']['rca_initial_category'] == 'Other NR'
    assert calls['0xC3']['values']['rca_evidence'] == 'No NR condition matched.'
    detail = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()
    assert detail['call']['rca']['extra:LTE_Avg_PCell_RSRP'] == 'A: -102.3 | B: -98.1'
    assert detail['call']['rca']['extra:Log_Day'] == '2026-09-03'
    recommendation = calls['0xA1']['rca_recommendation']
    script = next(source for source in recommendation['sources'] if source['source'] == 'script')
    assert (script['category'], script['cause']) == ('Poor Coverage LTE', 'Coverage')


def test_root_cause_analysis_counts_each_source_apart_and_filters_by_it(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    csv = ('JOIN_ID,RCA_Suggested_Category\n0xA1,Poor Coverage LTE\n0xC3,DL Interference LTE\n').encode()
    assert client.post('/api/non-qualified-calls/rca/import', files={'file': ('rca.csv', io.BytesIO(csv), 'text/csv')}).status_code == 200
    patch(client, calls['0xB2'], {'root_category': 'E2E'})

    def stats(source):
        return client.post('/api/non-qualified-calls/root-causes/stats',
                           json={'filters': {}, 'source': source, 'include_suggestions': False}).json()

    analysts, netcheck, script = stats('analysts'), stats('netcheck'), stats('script')
    assert (analysts['source'], analysts['summary']['labelled'], analysts['summary']['unclassified']) == ('analysts', 1, 2)
    assert {item['value']: item['count'] for item in analysts['domains']} == {'IMS/E2E': 1, 'Not classified': 2}
    # The RCA script counts the two calls it has results for, mapped onto the catalog.
    assert (script['summary']['labelled'], script['summary']['unclassified']) == (2, 1)
    assert {item['value']: item['count'] for item in script['domains']} == {'RF': 2, 'Not classified': 1}
    # The root categories keep the technology of the script values.
    assert {(item['domain'], item['category']): item['count'] for item in script['categories']} == {
        ('RF', 'Poor Coverage LTE'): 1, ('RF', 'DL Interference LTE'): 1}
    assert [(item['domain'], item['category']) for item in analysts['categories']] == [('IMS/E2E', 'E2E')]
    # NetCheck counts every call by its Failure Classification, Category and Subcategory, never by the analysts.
    assert netcheck['summary']['labelled'] == 3 and netcheck['summary']['suggested'] == 0
    assert {item['value'] for item in netcheck['domains']} >= {'RF'}
    # A domain, domain·category or domain·cause of a source filters its calls.
    joins = lambda filters: sorted(item['join_id'] for item in query(client, filters=filters)['calls'])
    assert joins({'script_domain': ['RF']}) == ['0xA1', '0xC3']
    assert joins({'script_domain': [nq.UNASSIGNED]}) == ['0xB2']
    assert joins({'script_category': ['RF||DL Interference LTE']}) == ['0xC3']
    cause = next(item for item in netcheck['causes'] if item['domain'] == 'RF' and item['value'] == 'Coverage')
    assert joins({'netcheck_cause': [f"RF||{cause['value']}"]}) == ['0xA1']


def test_lifecycle_counts_the_rca_identification(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    patch(client, calls['0xA1'], {'root_category': 'Poor Coverage LTE'})
    life = client.post('/api/non-qualified-calls/lifecycle', json={'filters': {}}).json()
    assert life['rca'] == {'identified': 1, 'not_identified': 2}
    assert [item['join_id'] for item in query(client, filters={'state': ['identified']})['calls']] == ['0xA1']
    assert query(client, filters={'state': ['not_identified']})['total'] == 2


def test_admins_import_the_analyses_of_the_previous_tool_by_join_id(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    template = client.get('/api/non-qualified-calls/analyses/template').text.lstrip('﻿').splitlines()[0].split(',')
    assert template[0] == 'JOIN_ID' and template[-1] == 'Comments' and {'NQ Call Status', 'Analysis Status', 'Findings'} <= set(template)
    patch(client, calls['0xB2'], {'fields': {'analysis_status': 'Ongoing'}})
    csv = ('JOIN_ID,Analysis Status,Selected Root Category,Team Responsible,Findings,Comments,Netcheck Suggested Cause,Old Column\n'
           '0xa1,Finished,Poor Coverage LTE,RAN Planning Coverage,"Hill behind the site\nNo dominant cell",Reviewed in the old tool,x,y\n'
           '0xB2,Bogus,,,Interference,,,\n'
           '0xZZ,Finished,,,,,,\n').encode()
    send = lambda **form: client.post('/api/non-qualified-calls/analyses/import', data=form,
                                      files={'file': ('analyses.csv', io.BytesIO(csv), 'text/csv')})
    preview = send(preview='1').json()
    assert (preview['calls'], preview['matched'], preview['unmatched_ids'], preview['pending']) == (3, 2, ['0xZZ'], 1)
    # The columns without a field go to the import note of each call: nothing of the file is left out.
    assert preview['read_only'] == [] and preview['noted'] == ['Netcheck Suggested Cause', 'Old Column']
    # Bogus would be a new Analysis Status, but 0xB2 keeps its own: the note keeps it and the catalog gets nothing.
    assert preview['invalid'] == [] and preview['new_options'] == []
    assert (preview['changed'], preview['comments'], preview['notes'], preview['analysed']) == (2, 1, 2, 1)
    assert query(client, filters={'fields': {'analysis_status': ['Finished']}})['total'] == 0
    # Only the empty values are filled: 0xB2 keeps its Analysis Status and gets its Findings.
    result = send().json()
    assert (result['changed'], result['pending'], result['comments'], result['notes'], result['failures']) == (2, 1, 1, 2, [])
    imported = {call['join_id']: call for call in query(client)['calls']}
    assert imported['0xA1']['values']['analysis_status'] == 'Finished' and imported['0xA1']['root_category'] == 'Poor Coverage LTE'
    assert imported['0xA1']['team'] == 'RAN Planning Coverage'
    assert imported['0xA1']['values']['findings'] == 'Hill behind the site\nNo dominant cell'
    assert imported['0xB2']['values']['analysis_status'] == 'Ongoing' and imported['0xB2']['values']['findings'] == 'Interference'
    assert 'Bogus' not in [option['name'] for field in client.get('/api/non-qualified-calls/state').json()['fields']
                           if field['key'] == 'analysis_status' for option in field['options']]
    bodies = lambda call_key: sorted(comment['body'] for comment in
                                     client.get(f'/api/non-qualified-calls/calls/{call_key}').json()['comments'])
    assert bodies(calls['0xA1']['call_key']) == [
        'Imported from analyses.csv · row 2\nNetcheck Suggested Cause: x\nOld Column: y', 'Reviewed in the old tool']
    assert bodies(calls['0xB2']['call_key']) == ['Imported from analyses.csv · row 3\nAnalysis Status (the call keeps Ongoing): Bogus']
    # Importing again changes nothing and never repeats a comment or a note; replacing overwrites what the calls have.
    again = send().json()
    assert (again['changed'], again['comments'], again['notes']) == (0, 0, 0)
    # 0xZZ is not in the workspace yet: its analysis waits for its CDR.
    frame = calls_frame().iloc[[0]].assign(JOIN_ID='0xZZ', Session_ID_A=9)
    add_cdr(tmp_path, 'UK_Voice_Q4.xlsx', 'voice', frame)
    assert {call['join_id']: call for call in query(client)['calls']}['0xZZ']['values']['analysis_status'] == 'Finished'
    csv = b'JOIN_ID,Analysis Status\n0xB2,Finished\n'
    assert send(overwrite='1').json()['changed'] == 1
    assert {call['join_id']: call for call in query(client)['calls']}['0xB2']['values']['analysis_status'] == 'Finished'
    # The Excel export of Non-Qualified Calls (its first row names the sections) can be imported too.
    exported = client.post('/api/non-qualified-calls/export', json={'filters': {}}).content
    again = client.post('/api/non-qualified-calls/analyses/import', data={'preview': '1'},
                        files={'file': ('export.xlsx', io.BytesIO(exported), 'application/octet-stream')}).json()
    assert again['matched'] == 4 and 'Analysis Status' in again['columns'] and again['changed'] == 0
    # The NQ Analysis Configuration menu ends with both imports and Analysts / Reviewers → Asignees after a line, and the sections
    # menu of the module lists it after a line with every option (the page opens them); only admins and super-admins
    # import analyses.
    page = client.get('/non-qualified-calls').text
    center = page.split('id="nq-config-menu"', 1)[1].split('</div>\n  </div>', 1)[0]
    assert center.index('nq-menu-separator') < center.index('id="nq-rca-open"') < center.index('id="nq-analyses-open"') \
        < center.index('id="nq-assign-analysts-open"')
    assert 'Import Ericsson RCA Results</strong>' in center and 'Import Previous NQ Analyses</strong>' in center
    assert 'nq-import-toggle' not in page
    menu = page.split('data-module-sections-for="non-qualified-calls"', 1)[1].split('</nav>', 1)[0]
    assert menu.index('<span>Non-Qualified Calls</span>') < menu.index('module-sections-separator') < menu.index('<span>NQ Analysis Configuration</span>')
    script = (Path(__file__).parents[1] / 'src/web_interface/static/js/non_qualified_calls.js').read_text(encoding='utf-8')
    anchors = ('fields-and-sections', 'statuses-and-teams', 'status-rules', 'root-cause-catalog', 'import-ericsson-rca-results',
               'import-previous-nq-analyses', 'analysts-reviewers-to-asignees')
    for anchor in ('section-nq-analysis-configuration', *anchors):
        assert f'href="/non-qualified-calls#{anchor}"' in menu and f"'{anchor}':" in script, anchor
    assert menu.index('#root-cause-catalog') < menu.rindex('module-sections-separator') < menu.index('#import-ericsson-rca-results')
    # Columns is a button of the table, before Default column order, not an option of the NQ Analysis Configuration.
    assert 'nq-columns-open' not in center and 'additional-columns' not in menu
    # Layout (Mine / Workspace), Save for the workspace (admins) and Default column order, then Columns.
    toolbar = page.split('class="nq-toolbar-actions"', 1)[1].split('id="nq-export"', 1)[0]
    assert toolbar.index('data-nq-layout-view="mine"') < toolbar.index('id="nq-layout-publish"') \
        < toolbar.index('id="nq-column-order-reset"') < toolbar.index('id="nq-columns-open"')
    assert 'in your own layout (only for you)">Columns</button>' in toolbar
    # The Global Status and the Team / Assignee come before the comments; the calls panel follows the Filters.
    head = page.split('<thead>', 1)[1].split('</thead>', 1)[0]
    assert head.index('data-sort="root_category"') < head.index('data-sort="status"') < head.index('data-sort="team"') \
        < head.index('data-sort="comments"') and '>Global Status</span>' in head
    assert page.index('nq-filters-panel') < page.index('nq-calls-panel') < page.index('nq-summary-panel')
    # The General Filters (the CDRs and the call), then the NQ Analysis Fields Filters with those of the catalog fields of
    # the CDR and the follow-up (the script adds the others and puts all in the order of the catalog).
    general = page.split('>General Filters:</p>', 1)[1].split('id="nq-field-filters-title"', 1)[0]
    fields = page.split('id="nq-field-filters-title">NQ Analysis Fields Filters:</p>', 1)[1].split('id="nq-column-filters-title"', 1)[0]
    assert 'data-nq-filter="campaign"' in general and 'data-nq-filter="version"' in general and 'data-nq-filter="status"' not in general
    for name in ('failure_classification', 'failure_category', 'status', 'status_mode', 'state', 'team', 'assignee', 'root_domain',
                 'root_category', 'root_cause'):
        assert f'data-nq-filter="{name}"' in fields, name
    # Each group in a card of its own.
    assert page.count('<section class="nq-filter-card"') == 3
    # The phase cards leave out the calls without a value unless Show Empty Status (unchecked) is checked.
    assert '<input type="checkbox" id="nq-life-show-empty"> Show Empty Status</label>' in page
    assert "const base = phase.drill || showEmpty ? total : items.reduce((sum, item) => sum + item.count, 0);" in script
    # The rules of the pipeline cards start on one line, Open frames the phase statuses and the phase cards share a row.
    assert "const top = node('div', undefined, 'nq-pipeline-head');" in script and "'nq-pipeline-group-head'" in script
    assert "style.setProperty('--nq-phase-count'" in script
    # The Root Cause Analysis leaves out the Not classified calls of every source unless shown.
    assert '<input type="checkbox" id="nq-root-show-unclassified"> Show Not classified</label>' in page
    assert "const showUnclassified = $('nq-root-show-unclassified').checked;" in script
    # The Progress View shows the calls per month by default.
    assert '<option value="month" selected>Month</option>' in page
    # The Status Rules warn, above the rules, that changing them reclassifies the calls.
    rules_dialog = page.split('id="nq-status-rules-dialog"', 1)[1].split('</dialog>', 1)[0]
    assert rules_dialog.index('class="nq-rules-warning"') < rules_dialog.index('id="nq-status-rules"')
    assert 'can completely change how the calls are classified' in rules_dialog
    # Every configuration has its button to go back to the values of a new workspace.
    for button in ('id="nq-columns-default"', 'id="nq-fields-default"', 'id="nq-root-default-catalog"', 'id="nq-root-defaults"',
                   'data-nq-option-defaults="statuses"', 'data-nq-option-defaults="teams"', 'id="nq-status-rules-default"',
                   'id="nq-rule-default"', 'data-nq-analyses-equivalences-reset'):
        assert button in page, button
    workspace_user('editor', 'user-editor')
    login(client, 'editor', 'editor123')
    assert send(preview='1').status_code == 403
    # Editors open it to see it, under its card, with the file, equivalences and mode locked and no Preview or Import;
    # they download the template and the equivalences the import uses, but cannot upload or forget them.
    page = client.get('/non-qualified-calls').text
    assert '<button type="button" role="menuitem" id="nq-analyses-open">' in page
    dialog = page.split('id="nq-analyses-dialog"', 1)[1].split('</dialog>', 1)[0]
    assert 'Only admins and super-admins can import the analyses of the previous tool.' in dialog
    assert dialog.count('class="nq-config-fieldset" disabled') == 2 and '<fieldset class="nq-analyses-mode" disabled>' in dialog
    assert 'data-nq-analyses-preview disabled' in dialog and dialog.count(' hidden>Preview</button>') == 1
    assert dialog.count(' hidden>Import Analyses</button>') == 1
    assert client.get('/api/non-qualified-calls/analyses/template').status_code == 200
    assert client.get('/api/non-qualified-calls/analyses/equivalences').status_code == 200
    assert client.delete('/api/non-qualified-calls/analyses/equivalences').status_code == 403
    assert client.put('/api/non-qualified-calls/analyses/equivalences', files={'file': ('rules.xlsx', io.BytesIO(b'x'))}).status_code == 403


def mtl_workbook() -> bytes:
    """A workbook of the previous tool: the CDR export and the analysis after it, one sheet per operator, a sheet of
    area analyses listing several calls and a hidden sheet of lists."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Vodafone NSA'
    sheet.append(['JOIN_ID', 'Campaign', 'Operator', 'Session_ID_A', 'Call_Direction', 'Session_Type', 'Unique ID', 'Priority', 'Team',
                  'Responsible Stream', 'Asignee', 'Final Category/Classification', 'Final Cause/Subcategory',
                  'Initial Category/Classification', 'Analysis Finished', 'Failed Party', 'Status', 'Evaluation', 'Planned Date',
                  'Findings', 'Findings Comments', 'Comments', 'Comments only to fill out by BNP NQ stream', 'Polygon Area', 'Band', 'Vendor',
                  'Date last modification'])
    sheet.append(['0xA1', 'UK_Q3_2026', 'Vodafone UK', 1, 'B->A', 'CALL', 'U1', 'P2', 'Raj Kumar', 'RAN planning coverage', None,
                  'Additional Investigation LTE', 'Pending Investigation', 0, 'Yes', 'MTC', 'Not planned', 'Solved', 'FY27\nFY28',
                  'Weak DL', 'Checked twice', 'Old tool comment', 'Stream comment', 'Leeds North', 'L800', 'Ericsson\nHuawei', '2026-03-12'])
    # 0xD4 completed: its analysis waits for the call.
    sheet.append(['0xD4', 'UK_Q3_2026', 'EE', 4, 'A->B', 'CALL', 'U2', 'P1', 'Rajkumar', 'Transport Stream', None, 'Poor Coverage LTE',
                  None, None, 'No', 'MOC', None, None, None, None, None, None, None, None, None, None, None])
    # A WhatsApp call without JOIN_ID is its Operator, Campaign and session, as in the CDR.
    sheet.append([None, 'UK_Q3_2026', 'Vodafone UK', 77, 'A->B', 'WhatsApp CALL', 'U3', 'P4', 'Sujay', 'E2E Team', None, 'E2E', None,
                  None, 'Yes', None, None, None, None, 'No answer from the server', None, None, None, None, None, 'Samsung/NSN/Huawei',
                  'last week'])
    area = workbook.create_sheet('MBB Data Analysis')
    area.append(['JOIN_ID', 'Test Type', 'Priority', 'Campaign', 'Final Category/Classification', 'Analysis Finished', 'Comments'])
    area.append(['0xB2\n0xC3', 'HTTP', 'P3', 'UK_Q3_2026', 'Poor LTE Coverage', 'Yes', 'Area analysis'])
    # 0xC3 in a second area: the first row gives its values, the note keeps the others.
    area.append(['0xC3', 'HTTP', 'P1', 'UK_Q2_2026', 'Poor LTE Coverage', 'Yes', 'Second area'])
    lists = workbook.create_sheet('Lists')
    lists.append(['JOIN_ID', 'Priority'])
    lists.append(['0xC3', 4])
    lists.sheet_state = 'hidden'
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_analyses_of_the_previous_tool_keep_everything_through_reviewed_equivalences(client, tmp_path, monkeypatch):
    calls = setup_calls(client, tmp_path)
    whatsapp = calls_frame().iloc[[1]].assign(JOIN_ID='', Session_ID_A=77, Session_Type='WhatsApp CALL', Campaign='UK_Q3_2026')
    add_cdr(tmp_path, 'UK_Voice_WhatsApp.xlsx', 'voice', whatsapp)
    whatsapp_key = next(call['call_key'] for call in query(client)['calls'] if not call['join_id'])
    content = mtl_workbook()
    upload = lambda url, method='post', **form: client.request(method, url, data=form, files={
        'file': ('MTL.xlsx', io.BytesIO(content), 'application/octet-stream')})
    # The equivalences of the values of the file, to review: the new root category gets a new domain, the cause stays
    # in the note.
    review = upload('/api/non-qualified-calls/analyses/equivalences')
    assert review.status_code == 200, review.text
    workbook = load_workbook(io.BytesIO(review.content))
    sheet = workbook['Equivalences']
    header = [cell.value for cell in sheet[1]]
    assert header == list(nq.EQUIVALENCES_COLUMNS)
    rows = {(row[0], row[1]): row for row in sheet.iter_rows(min_row=2, values_only=True)}
    assert rows[('Failed Party (MOC/MTC) (UE1/UE2)', 'MTC')][3:6] == ('UE_B (MT)', None, 'By the direction of the call (UE_A or UE_B)')
    assert rows[('Analysis Status', 'Yes')][3] == 'Finished' and rows[('Implementation Status', 'Solved')][3:6:2] == ('Implemented', 'Value of the catalog')
    assert rows[('Team Responsible', 'Transport Stream')][5] == 'New value'
    for row in sheet.iter_rows(min_row=2):
        if row[1].value == 'Additional Investigation LTE':
            row[3].value, row[4].value = 'Additional Investigation LTE', 'Additional Investigation'
        if row[1].value == 'Pending Investigation':
            row[3].value = None
        if row[1].value == 'Poor LTE Coverage':
            row[3].value = 'Poor Coverage LTE'
    output = io.BytesIO()
    workbook.save(output)
    content, reviewed = output.getvalue(), content
    saved = upload('/api/non-qualified-calls/analyses/equivalences', 'put')
    assert saved.status_code == 200, saved.text
    content = reviewed
    preview = upload('/api/non-qualified-calls/analyses/import', preview='1').json()
    assert [item['sheet'] for item in preview['sheets']] == ['Vodafone NSA', 'MBB Data Analysis']
    assert (preview['calls'], preview['matched'], preview['pending'], preview['duplicates'], preview['skipped']) == (5, 4, 1, 1, 0)
    assert preview['noted'] == ['Campaign'] and preview['cdr_columns'] == 5
    assert preview['new_categories'] == [{'value': 'Additional Investigation LTE', 'domain': 'Additional Investigation', 'rows': 1}]
    assert preview['new_teams'] == [{'value': 'Transport Stream', 'rows': 1}]
    assert query(client, filters={'fields': {'analysis_status': ['Finished']}})['total'] == 0
    result = upload('/api/non-qualified-calls/analyses/import').json()
    assert (result['changed'], result['pending'], result['comments']) == (4, 1, 5)
    imported = {call['join_id']: call for call in query(client)['calls']}
    first = imported['0xA1']
    assert (first['root_category'], first['root_domain'], first['root_cause'], first['team']) == (
        'Additional Investigation LTE', 'Additional Investigation', '', 'RAN Planning Coverage')
    values = first['values']
    assert (values['priority'], values['analyst'], values['analysis_status'], values['failed_party']) == ('P2', 'Raj Kumar', 'Finished', 'UE_A (MT)')
    # Two vendors in one cell are Vendor 1 and Vendor 2.
    assert (values['band_when_failure'], values['vendor_when_failure'], values['vendor_2_when_failure']) == ('LTE800', 'Ericsson', 'Huawei')
    assert (values['planned_status'], values['implementation_status'], values['planned_fy']) == ('Not Planned', 'Implemented', 'FY27')
    assert values['findings'] == 'Weak DL\n\n[Findings Comments] Checked twice' and not values.get('initial_root_category')
    # The changes, comments and note of the call take the date of its analysis, also the status the rules give it.
    detail = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()
    assert detail['call']['updated_at'].startswith('2026-03-12')
    assert {comment['created_at'][:10] for comment in detail['comments']} == {'2026-03-12'}
    assert {entry['changed_at'][:10] for entry in detail['history']} == {'2026-03-12'}
    assert (result['dated'], result['estimated']) == (1, 3)
    # Without the date of its analysis, a call found takes its own date a week later (0xB2 started on 2026-09-02).
    detail = client.get(f"/api/non-qualified-calls/calls/{calls['0xB2']['call_key']}").json()
    assert detail['call']['updated_at'].startswith('2026-09-09') and {entry['changed_at'][:10] for entry in detail['history']} == {'2026-09-09'}
    # Each comment column is a comment; what no field holds is in the import note of the call.
    bodies = sorted(comment['body'] for comment in client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()['comments'])
    assert (values['unique_id'], values['polygon_area']) == ('U1', 'Leeds North')
    assert bodies == ['Imported from MTL.xlsx · Vodafone NSA, row 2\n'
                      'Selected Root Cause (not a value of the field): Pending Investigation\nPlanned Date (as written): FY27\nFY28',
                      'Old tool comment', '[Comments only to fill out by BNP NQ stream] Stream comment']
    # The analysis of an area goes to each of its calls; the hidden sheet is not read.
    assert imported['0xB2']['values']['priority'] == imported['0xC3']['values']['priority'] == 'P3'
    assert imported['0xC3']['root_category'] == 'Poor Coverage LTE'
    # The note keeps how the file names a root category the equivalences turn into another one, the values of another
    # row of the same call and a copy of the CDR that does not say what the CDR of the call says (the other is left out).
    assert ('Imported from MTL.xlsx · MBB Data Analysis, row 2; MBB Data Analysis, row 3\n'
            'Priority (MBB Data Analysis, row 3): P1\nCampaign: UK_Q2_2026\nSelected Root Category (as written): Poor LTE Coverage'
            in [comment['body'] for comment in client.get(f"/api/non-qualified-calls/calls/{calls['0xC3']['call_key']}").json()['comments']])
    by_key = {call['call_key']: call for call in query(client)['calls']}
    assert (by_key[whatsapp_key]['root_category'], by_key[whatsapp_key]['values']['findings']) == ('E2E', 'No answer from the server')
    # Three vendors: the first two fill Vendor 1 and 2 and the note keeps the cell.
    assert (by_key[whatsapp_key]['values']['vendor_when_failure'], by_key[whatsapp_key]['values']['vendor_2_when_failure']) == ('Samsung', 'NSN')
    assert any('Vendor (as written): Samsung/NSN/Huawei' in comment['body'] and 'Date last modification: last week' in comment['body']
               for comment in client.get(f'/api/non-qualified-calls/calls/{whatsapp_key}').json()['comments'])
    # Importing again adds nothing, also when the comments of the calls are read in several reads.
    monkeypatch.setattr(nq, 'KEYED_READ_CHUNK', 1)
    again = upload('/api/non-qualified-calls/analyses/import').json()
    assert (again['changed'], again['pending'], again['comments'], again['notes']) == (0, 0, 0, 0)
    state = client.get('/api/non-qualified-calls/state').json()
    assert 'Transport Stream' in [team['name'] for team in state['options']['teams']]
    # The equivalences travel with the configuration of the workspace.
    assert 'tracking:root_category' in nq.analyses_equivalences(core.repository)
    # The pending call takes its analysis (and the analyst its most used spelling) when its CDR comes.
    frame = calls_frame().iloc[[3]].assign(Call_Status='Failed', status='Failed')
    add_cdr(tmp_path, 'UK_Voice_Q4.xlsx', 'voice', frame)
    later = {call['join_id']: call for call in query(client)['calls']}['0xD4']
    assert (later['values']['analysis_status'], later['values']['analyst'], later['values']['failed_party'], later['team']) == (
        'Pending', 'Raj Kumar', 'UE_A (MO)', 'Transport Stream')


def test_workspaces_before_the_vendor_2_get_it_with_p1_to_p4_and_the_e2e_team(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    # The layout before: Vendor when Failure alone, priorities 1 to 4, the Implementation Stream and the team E2E stream
    # with a call and a member.
    fields = [field for field in nq.list_fields(repository) if field['key'] != 'vendor_2_when_failure']
    for field in fields:
        if field['key'] == 'vendor_when_failure':
            field['label'] = 'Vendor when Failure'
        if field['key'] == 'priority':
            field['options'] = [{'name': str(number), 'color': ''} for number in range(1, 5)]
        if field['key'] == 'implementation_team':
            field['key'], field['label'] = 'implementation_stream', 'Implementation Stream'
            field['options'] = [dict(option, name='E2E stream' if option['name'] == 'E2E Team' else option['name']) for option in field['options']]
    nq._store_fields(repository, fields)
    with repository.connection() as connection:
        connection.execute(f"UPDATE {nq.NQ_CALL_OPTIONS_TABLE} SET name = 'E2E stream' WHERE kind = 'team' AND name = 'E2E Team'")
        connection.execute(f"INSERT INTO {nq.NQ_TEAM_MEMBERS_TABLE} (team, username) VALUES ('E2E stream', 'super')")
    patch(client, calls['0xA1'], {'team': 'E2E stream', 'root_cause': 'Tunnel Issue',
                                  'fields': {'priority': '2', 'implementation_stream': 'E2E stream'}})
    # And the domain Core 2G/4G/5G, with a call in it and in the shared filters.
    with repository.connection() as connection:
        connection.execute(f"UPDATE {nq.NQ_ROOT_CATALOG_TABLE} SET name = 'Core 2G/4G/5G' WHERE kind = 'domain' AND name = 'Core'")
        connection.execute(f"UPDATE {nq.NQ_ROOT_CATALOG_TABLE} SET domain = 'Core 2G/4G/5G' WHERE kind <> 'domain' AND domain = 'Core'")
        connection.execute(f"UPDATE {nq.NQ_CALL_TRACKING_TABLE} SET root_domain = 'Core 2G/4G/5G' WHERE root_domain = 'Core'")
    repository.set_workspace_state(nq.SAVED_FILTERS_STATE_KEY, json.dumps({'root_domain': ['Core 2G/4G/5G', 'RF']}))
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V9_STATE_KEY, '')
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V12_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    upgraded = {field['key']: field for field in nq.list_fields(repository)}
    keys = list(upgraded)
    assert upgraded['vendor_when_failure']['label'] == 'Vendor 1 when Failure'
    assert keys.index('vendor_2_when_failure') == keys.index('vendor_when_failure') + 1
    assert [option['name'] for option in upgraded['priority']['options']] == ['P1', 'P2', 'P3', 'P4']
    call = {item['join_id']: item for item in query(client)['calls']}['0xA1']
    assert (call['team'], call['values']['priority'], call['values']['implementation_team']) == ('E2E Team', 'P2', 'E2E Team')
    assert upgraded['implementation_team']['label'] == 'Implementation Team' and 'implementation_stream' not in upgraded
    teams = {team['name']: team for team in nq.list_options(repository)['teams']}
    assert 'E2E stream' not in teams and teams['E2E Team']['members'] == ['super']
    root = nq.list_root_causes(repository)
    assert 'Core' in [domain['name'] for domain in root['domains']] and 'Core 2G/4G/5G' not in [domain['name'] for domain in root['domains']]
    assert next(item for item in root['causes'] if item['name'] == 'Tunnel Issue')['domain'] == 'Core'
    assert call['root_domain'] == 'Core'
    assert json.loads(repository.get_workspace_state(nq.SAVED_FILTERS_STATE_KEY))['root_domain'] == ['Core', 'RF']


def test_root_causes_map_to_their_category_and_take_their_domain_by_hand_or_automatically(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    root = client.get('/api/non-qualified-calls/root-causes').json()
    # Stored by hand: every default category and cause keeps its domain.
    assert all(item['domain_from'] == 'manual' for item in root['categories'] + root['causes'])
    payload = {'domains': root['domains'], 'require_to_close': False,
               'categories': [{'name': item['name'], 'previous': item['name'], 'keywords': item['keywords'],
                               'domain': '' if item['name'] in {'E2E', 'Mobility LTE'} else item['manual_domain']} for item in root['categories']],
               'causes': [{'name': item['name'], 'previous': item['name'], 'keywords': item['keywords'],
                           'domain': '' if item['name'] in {'Tunnel Issue', 'Paging'} else item['manual_domain'],
                           'category': 'Mobility LTE' if item['name'] == 'Tunnel Issue' else ''} for item in root['causes']]}
    saved = client.put('/api/non-qualified-calls/root-causes', json=payload)
    assert saved.status_code == 200, saved.text
    catalog = saved.json()
    categories = {item['name']: item for item in catalog['categories']}
    causes = {item['name']: item for item in catalog['causes']}
    # E2E has no domain keyword in its name or keywords; Mobility LTE neither: they have no domain.
    assert (categories['E2E']['domain'], categories['E2E']['domain_from']) == ('', '')
    # A cause takes the domain of its root category, else the keywords of the domains (paging is a RAN keyword).
    assert (causes['Tunnel Issue']['category'], causes['Tunnel Issue']['domain_from']) == ('Mobility LTE', '')
    assert (causes['Paging']['domain'], causes['Paging']['domain_from']) == ('RAN', 'keywords')
    payload['categories'] = [dict(item, domain='RAN' if item['name'] == 'Mobility LTE' else item['domain']) for item in payload['categories']]
    causes = {item['name']: item for item in client.put('/api/non-qualified-calls/root-causes', json=payload).json()['causes']}
    assert (causes['Tunnel Issue']['domain'], causes['Tunnel Issue']['domain_from']) == ('RAN', 'category')
    # Choosing a cause for a call without root category gives it the category of the cause, never over a chosen one.
    updated = patch(client, calls['0xA1'], {'root_cause': 'Tunnel Issue'})
    assert (updated['root_category'], updated['root_cause'], updated['root_domain']) == ('Mobility LTE', 'Tunnel Issue', 'RAN')
    updated = patch(client, calls['0xB2'], {'root_category': 'Poor Coverage LTE'})
    assert patch(client, updated, {'root_cause': 'Tunnel Issue'})['root_category'] == 'Poor Coverage LTE'
    # A category renamed or given another domain carries its causes and the domain of their calls.
    payload['categories'] = [dict(item, name='LTE Mobility', domain='Core') if item['name'] == 'Mobility LTE' else item
                             for item in payload['categories']]
    causes = {item['name']: item for item in client.put('/api/non-qualified-calls/root-causes', json=payload).json()['causes']}
    assert (causes['Tunnel Issue']['category'], causes['Tunnel Issue']['domain']) == ('LTE Mobility', 'Core')
    call = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()['call']
    assert (call['root_category'], call['root_domain']) == ('LTE Mobility', 'Core')
    # The catalog workbook and the configuration carry the category of each cause and only the domains chosen by hand.
    workbook = load_workbook(io.BytesIO(client.get('/api/non-qualified-calls/catalog/export').content))
    rows = {row[1]: row for row in workbook['Root Catalog'].iter_rows(min_row=2, values_only=True)}
    assert [cell.value for cell in workbook['Root Catalog'][1]][:4] == ['Kind', 'Name', 'Root Category', 'Domain']
    assert rows['Tunnel Issue'][2:4] == ('LTE Mobility', None) and rows['Paging'][3] is None
    document = json.loads(nq.export_configuration_document(core.repository))
    with core.repository.connection() as connection:
        connection.execute(f'DELETE FROM {nq.NQ_ROOT_CATALOG_TABLE}')
    nq.import_configuration_document(core.repository, json.dumps(document))
    causes = {item['name']: item for item in nq.list_root_causes(core.repository)['causes']}
    assert (causes['Paging']['domain_from'], causes['Tunnel Issue']['domain_from'], causes['Tunnel Issue']['category']) == (
        'keywords', 'category', 'LTE Mobility')


def test_reviewed_domains_change_the_catalog_and_new_causes_take_the_domain_of_the_keywords(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    content = b'JOIN_ID,Final Category/Classification,Final Cause/Subcategory\n0xA1,Poor LTE Coverage,Waiting for paging\n'
    upload = lambda url, method='post', **form: client.request(method, url, data=form, files={
        'file': ('analyses.csv', io.BytesIO(content), 'text/csv')})
    workbook = load_workbook(io.BytesIO(upload('/api/non-qualified-calls/analyses/equivalences').content))
    for row in workbook['Equivalences'].iter_rows(min_row=2):
        if row[1].value == 'Poor LTE Coverage':
            row[3].value, row[4].value = 'Poor Coverage LTE', 'RAN'
        if row[1].value == 'Waiting for paging':
            row[3].value, row[4].value = 'Waiting for paging', None
    output = io.BytesIO()
    workbook.save(output)
    content, analyses = output.getvalue(), content
    assert upload('/api/non-qualified-calls/analyses/equivalences', 'put').json()['saved'] == 2
    content = analyses
    preview = upload('/api/non-qualified-calls/analyses/import', preview='1').json()
    assert preview['domain_changes'] == [{'kind': 'Root Category', 'value': 'Poor Coverage LTE', 'from': 'RF', 'to': 'RAN', 'rows': 1, 'others': []}]
    assert preview['new_causes'] == [{'value': 'Waiting for paging', 'domain': '', 'rows': 1}]
    assert upload('/api/non-qualified-calls/analyses/import').status_code == 200
    root = nq.list_root_causes(core.repository)
    category = next(item for item in root['categories'] if item['name'] == 'Poor Coverage LTE')
    cause = next(item for item in root['causes'] if item['name'] == 'Waiting for paging')
    assert (category['domain'], category['domain_from']) == ('RAN', 'manual')
    assert (cause['domain'], cause['domain_from']) == ('RAN', 'keywords')
    call = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()['call']
    assert (call['root_category'], call['root_cause'], call['root_domain']) == ('Poor Coverage LTE', 'Waiting for paging', 'RAN')


def test_calls_with_a_cause_and_no_category_take_the_category_of_their_cause_on_demand(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    patch(client, calls['0xA1'], {'root_cause': 'Paging'})
    patch(client, calls['0xB2'], {'root_category': 'E2E', 'root_cause': 'Paging'})
    apply = lambda preview: client.post('/api/non-qualified-calls/root-causes/apply-categories', json={'preview': preview}).json()['calls']
    assert apply(True) == 0
    root = client.get('/api/non-qualified-calls/root-causes').json()
    payload = {'domains': root['domains'], 'require_to_close': False,
               'categories': [{'name': item['name'], 'previous': item['name'], 'domain': item['manual_domain'], 'keywords': item['keywords']}
                              for item in root['categories']],
               'causes': [{'name': item['name'], 'previous': item['name'], 'domain': item['manual_domain'], 'keywords': item['keywords'],
                           'category': 'Mobility LTE' if item['name'] == 'Paging' else ''} for item in root['causes']]}
    assert client.put('/api/non-qualified-calls/root-causes', json=payload).status_code == 200
    # Only the call without root category takes it; the preview changes nothing.
    assert apply(True) == 1 and apply(True) == 1
    assert apply(False) == 1 and apply(True) == 0
    detail = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()
    assert (detail['call']['root_category'], detail['call']['root_domain']) == ('Mobility LTE', 'RAN')
    assert any(entry.get('field') == 'root_category' and entry.get('new_value') == 'Mobility LTE' for entry in detail['history'])
    assert client.get(f"/api/non-qualified-calls/calls/{calls['0xB2']['call_key']}").json()['call']['root_category'] == 'E2E'


def test_the_second_vendor_of_earlier_upgrades_keeps_its_values_as_vendor_2(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    fields = nq.list_fields(repository)
    for field in fields:
        if field['key'] == 'vendor_when_failure':
            field['label'] = 'Vendor A when Failure'
        if field['key'] == 'vendor_2_when_failure':
            field['key'], field['label'] = 'vendor_b_when_failure', 'Vendor B when Failure'
    nq._store_fields(repository, fields)
    patch(client, calls['0xA1'], {'fields': {'vendor_b_when_failure': 'Huawei'}})
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V9_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    upgraded = {field['key']: field for field in nq.list_fields(repository)}
    assert 'vendor_b_when_failure' not in upgraded and upgraded['vendor_2_when_failure']['label'] == 'Vendor 2 when Failure'
    assert upgraded['vendor_when_failure']['label'] == 'Vendor 1 when Failure'
    call = {item['join_id']: item for item in query(client)['calls']}['0xA1']
    assert call['values']['vendor_2_when_failure'] == 'Huawei'
    history = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()['history']
    assert any(entry.get('field') == 'field:vendor_2_when_failure' for entry in history)


def test_the_rules_of_the_tool_import_the_previous_workbooks_without_uploading_equivalences(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    csv = ('JOIN_ID,Final Category/Classification,Final Cause/Subcategory,Responsible Stream,Priority\n'
           '0xA1,E2E Issue,Poor LTE Coverage,Operation Team,B\n'
           '0xB2,Additional Investigation LTE,,E2E stream,1\n').encode()
    result = client.post('/api/non-qualified-calls/analyses/import', files={'file': ('mtl.csv', io.BytesIO(csv), 'text/csv')}).json()
    assert result['new_categories'] == [{'value': 'Additional Investigation LTE', 'domain': 'Additional Investigation', 'rows': 1}]
    imported = {call['join_id']: call for call in query(client)['calls']}
    first, second = imported['0xA1'], imported['0xB2']
    assert (first['root_category'], first['root_cause'], first['team'], first['values']['priority']) == ('E2E', 'Coverage', 'Operations', 'P2')
    assert (second['root_category'], second['root_domain'], second['team'], second['values']['priority']) == (
        'Additional Investigation LTE', 'Additional Investigation', 'E2E Team', 'P1')
    # The rules, with the values each cell takes, can be downloaded without a file; uploaded as they are, the workspace
    # keeps nothing of its own.
    response = client.get('/api/non-qualified-calls/analyses/equivalences')
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    rows = list(workbook['Equivalences'].iter_rows(min_row=2, values_only=True))
    assert len(rows) == len(nq_analyses_rules.ANALYSES_RULES) and {row[5] for row in rows} == {'Rule of the tool'}
    lists = workbook['Lists']
    assert lists['A1'].value == 'Domain' and 'Additional Investigation' in [cell.value for cell in lists['A']]
    # A rule without a domain of its own shows the domain the catalog gives the value of Maps to (it follows Maps to),
    # in grey while it is that one.
    coverage = next(row for row in workbook['Equivalences'].iter_rows(min_row=2) if row[1].value == 'Poor LTE Coverage')
    assert coverage[3].value == 'Coverage' and coverage[4].value == f'=IFERROR(VLOOKUP($D{coverage[4].row},CauseDomains,2,FALSE),"")'
    assert ('Coverage', 'RF') in [(row[3], row[4]) for row in workbook['Catalog'].iter_rows(min_row=2, values_only=True)]
    assert workbook['Equivalences'].conditional_formatting
    assert workbook['Equivalences'].data_validations.dataValidation
    saved = client.put('/api/non-qualified-calls/analyses/equivalences', files={'file': ('rules.xlsx', io.BytesIO(response.content))})
    assert saved.json() == {'saved': 0, 'total': 0}
    # A change for this workspace comes before the rule.
    for row in workbook['Equivalences'].iter_rows(min_row=2):
        if row[1].value == 'E2E Issue':
            row[3].value = 'Unclear'
        if row[1].value == 'Poor LTE Coverage':
            row[4].value = 'RAN'
    output = io.BytesIO()
    workbook.save(output)
    saved = client.put('/api/non-qualified-calls/analyses/equivalences', files={'file': ('rules.xlsx', io.BytesIO(output.getvalue()))})
    assert saved.json() == {'saved': 2, 'total': 2}
    equivalences = nq.analyses_equivalences(core.repository)
    assert equivalences['tracking:root_category']['e2e issue']['to'] == 'Unclear'
    assert (equivalences['tracking:root_cause']['poor lte coverage']['to'], equivalences['tracking:root_cause']['poor lte coverage']['domain']) == (
        'Coverage', 'RAN')
    rows = load_workbook(io.BytesIO(client.get('/api/non-qualified-calls/analyses/equivalences').content))['Equivalences']
    assert [row[5] for row in rows.iter_rows(min_row=2, values_only=True) if row[1] == 'E2E Issue'] == ['Reviewed in this workspace']


def test_the_implementation_stream_becomes_the_implementation_team(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    # A workspace of before: the Implementation Stream with a value, its history, a Status Rule, a shared filter and a
    # reviewed equivalence.
    fields = nq.list_fields(repository)
    stream = next(field for field in fields if field['key'] == 'implementation_team')
    stream['key'], stream['label'] = 'implementation_stream', 'Implementation Stream'
    stream['description'] = nq.V12_FORMER_TEAM_FIELD[2]
    nq._store_fields(repository, fields)
    patch(client, calls['0xA1'], {'fields': {'implementation_stream': 'Operations'}})
    rules = nq.status_rules(repository)
    rules[0]['conditions'].append({'field': 'implementation_stream', 'op': 'in', 'values': ['Operations']})
    repository.set_workspace_state(nq.STATUS_RULES_STATE_KEY, json.dumps(rules))
    repository.set_workspace_state(nq.SAVED_FILTERS_STATE_KEY, json.dumps({'fields': {'implementation_stream': ['Operations']}}))
    repository.set_workspace_state(nq.ANALYSES_EQUIVALENCES_STATE_KEY, json.dumps(
        {'field:implementation_stream': {'acp': {'value': 'ACP', 'to': 'Operations', 'domain': ''}}}))
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V12_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    upgraded = {field['key']: field for field in nq.list_fields(repository)}
    assert 'implementation_stream' not in upgraded
    assert upgraded['implementation_team']['label'] == 'Implementation Team'
    assert upgraded['implementation_team']['description'].startswith('The team responsible for the implementation')
    call = {item['join_id']: item for item in query(client)['calls']}['0xA1']
    assert call['values']['implementation_team'] == 'Operations'
    with repository.connection() as connection:
        assert connection.execute(f"SELECT COUNT(*) FROM {nq.NQ_CALL_HISTORY_TABLE} WHERE field = 'field:implementation_team'").fetchone()[0]
        assert not connection.execute(f"SELECT COUNT(*) FROM {nq.NQ_CALL_HISTORY_TABLE} WHERE field LIKE '%implementation_stream'").fetchone()[0]
    assert {'field': 'implementation_team', 'op': 'in', 'values': ['Operations']} in nq.status_rules(repository)[0]['conditions']
    assert json.loads(repository.get_workspace_state(nq.SAVED_FILTERS_STATE_KEY))['fields'] == {'implementation_team': ['Operations']}
    assert set(nq.workspace_equivalences(repository)) == {'field:implementation_team'}


def test_a_list_takes_a_value_typed_in_the_call_and_the_planned_fy_only_fiscal_years(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    add = lambda key, name: client.post(f'/api/non-qualified-calls/fields/{key}/options', json={'name': name})
    # A list takes the value as typed, at the end of its values, and the call can take it.
    added = add('implementation_proposal', 'Small Cell').json()
    assert (added['value'], added['added'], added['field']['options'][-1]['name']) == ('Small Cell', True, 'Small Cell')
    patch(client, calls['0xA1'], {'fields': {'implementation_proposal': 'Small Cell'}})
    assert add('implementation_proposal', 'small  cell').json() == {**add('implementation_proposal', 'Small Cell').json(), 'added': False}
    assert add('description', 'Anything').status_code == 400
    # The Planned FY writes a year as a fiscal year, in its order, and refuses what is not one.
    fiscal = add('planned_fy', '2034').json()
    assert (fiscal['value'], fiscal['added']) == ('FY34', True)
    assert [option['name'] for option in fiscal['field']['options']] == [f'FY{year}' for year in (*range(26, 32), 34)]
    assert (add('planned_fy', 'fy 2034').json()['value'], add('planned_fy', 'fy 2034').json()['added']) == ('FY34', False)
    assert add('planned_fy', 'next year').status_code == 400
    # So do the new values of Fields & Sections.
    fields = nq.list_fields(repository)
    next(field for field in fields if field['key'] == 'planned_fy')['options'].append({'name': '2035', 'color': ''})
    saved = client.put('/api/non-qualified-calls/fields', json={'fields': fields})
    assert saved.status_code == 200, saved.text
    assert 'FY35' in [option['name'] for field in saved.json()['fields'] if field['key'] == 'planned_fy' for option in field['options']]
    next(field for field in fields if field['key'] == 'planned_fy')['options'].append({'name': 'Soon', 'color': ''})
    assert client.put('/api/non-qualified-calls/fields', json={'fields': fields}).status_code == 400
    # And the import: a year is its fiscal year, and what is not one stays in the import note.
    csv = b'JOIN_ID,Planned FY\n0xA1,2030\n0xB2,next year\n'
    client.post('/api/non-qualified-calls/analyses/import', files={'file': ('fy.csv', io.BytesIO(csv), 'text/csv')})
    found = {item['join_id']: item for item in query(client)['calls']}
    assert found['0xA1']['values']['planned_fy'] == 'FY30' and not found['0xB2']['values'].get('planned_fy')


def test_workspaces_before_write_their_planned_years_as_fiscal_years(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    # A workspace of before: years among the fiscal years, with calls and a shared filter.
    fields = nq.list_fields(repository)
    planned = next(field for field in fields if field['key'] == 'planned_fy')
    planned['options'] += [{'name': '2030', 'color': ''}, {'name': '2033', 'color': '#123456'}, {'name': 'FY32', 'color': ''}]
    nq._store_fields(repository, fields)
    patch(client, calls['0xA1'], {'fields': {'planned_fy': '2030'}})
    patch(client, calls['0xB2'], {'fields': {'planned_fy': '2033'}})
    repository.set_workspace_state(nq.SAVED_FILTERS_STATE_KEY, json.dumps({'fields': {'planned_fy': ['2030', 'FY30']}}))
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V13_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    options = next(field for field in nq.list_fields(repository) if field['key'] == 'planned_fy')['options']
    assert [option['name'] for option in options] == [f'FY{year}' for year in range(26, 34)]
    assert next(option for option in options if option['name'] == 'FY33')['color'] == '#123456'
    found = {item['join_id']: item for item in query(client)['calls']}
    assert (found['0xA1']['values']['planned_fy'], found['0xB2']['values']['planned_fy']) == ('FY30', 'FY33')
    assert json.loads(repository.get_workspace_state(nq.SAVED_FILTERS_STATE_KEY))['fields'] == {'planned_fy': ['FY30']}


def test_workspaces_before_hide_the_suggested_causes_and_show_the_implementation_status(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    fields = nq.list_fields(repository)
    for field in fields:
        field['in_table'] = field['in_table'] or field['key'] in nq.V14_HIDDEN_COLUMNS
        if field['key'] in nq.V16_SHOWN_COLUMNS:
            field['in_table'] = False
    nq._store_fields(repository, fields)
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V14_STATE_KEY, '')
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V16_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    upgraded = {field['key']: field for field in nq.list_fields(repository)}
    assert not upgraded['netcheck_suggested_cause']['in_table'] and not upgraded['rca_suggested_cause']['in_table']
    assert upgraded['implementation_status']['in_table']


def test_the_default_columns_of_the_workspace_layout_and_the_priority_in_workspaces_before(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    assert {field['key']: field['in_table'] for field in nq.list_fields(repository)}['priority'] is True
    # A new workspace: the Prioritization with the Priority, Repeated Issue, Scoring Points Lost and the phase statuses.
    assert nq.workspace_layout(repository)['fields'] == [
        'priority', 'prioritization', 'scoring_points_lost', 'repeated_issue', 'analysis_status', 'implementation_status']
    # A workspace of before, without the Priority in its table, takes it once.
    fields = nq.list_fields(repository)
    nq._store_fields(repository, [{**field, 'in_table': False} if field['key'] in nq.V26_SHOWN_COLUMNS else field for field in fields])
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V26_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    assert {'priority', 'prioritization'} <= set(nq.workspace_layout(repository)['fields'])
    # Taken once: hidden again by hand, it stays hidden.
    nq._store_fields(repository, [{**field, 'in_table': False} if field['key'] == 'priority' else field for field in nq.list_fields(repository)])
    nq.ensure_nq_tables(repository)
    assert 'priority' not in nq.workspace_layout(repository)['fields']


def test_workspaces_before_name_the_rca_fields_after_their_source(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    # The former names, one of them changed by hand.
    former = dict(nq.V15_FORMER_LABELS)
    fields = nq.list_fields(repository)
    for field in fields:
        if field['key'] in former:
            field['label'] = 'My evidence' if field['key'] == 'rca_evidence' else former[field['key']]
    nq._store_fields(repository, fields)
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V15_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    labels = {field['key']: field['label'] for field in nq.list_fields(repository)}
    assert labels['netcheck_suggested_cause'] == 'NetCheck RCA Suggested Cause'
    assert labels['auto_rca_subcategory_b'] == 'Ericsson RCA Subcategory B'
    assert labels['rca_initial_category'] == 'Ericsson RCA Initial Category'
    assert labels['rca_evidence'] == 'My evidence'


def test_workspaces_before_name_the_implementation_proposals_in_plural(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    label = lambda: next(field['label'] for field in nq.list_fields(repository) if field['key'] == 'implementation_proposal')
    assert label() == 'Implementation Proposals'
    for former, expected in (('Implementation Proposal', 'Implementation Proposals'), ('Action Proposal', 'Action Proposal')):
        fields = nq.list_fields(repository)
        next(field for field in fields if field['key'] == 'implementation_proposal')['label'] = former
        nq._store_fields(repository, fields)
        repository.set_workspace_state(nq.ANALYSIS_CENTER_V22_STATE_KEY, '')
        nq.ensure_nq_tables(repository)
        # A name chosen in the workspace stays.
        assert label() == expected


def test_workspaces_before_put_the_findings_after_the_description(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    fields = nq.list_fields(repository)
    findings = next(field for field in fields if field['key'] == 'findings')
    fields.remove(findings)
    fields.insert([field['key'] for field in fields].index('proposed_measure') + 1, findings)
    nq._store_fields(repository, fields)
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V17_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    keys = [field['key'] for field in nq.list_fields(repository)]
    assert keys.index('description') + 1 == keys.index('findings') == keys.index('proposed_measure') - 1


def test_the_implementation_status_keeps_implementation_values_on_import(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    # Planned and Not Planned are planning statuses, Closed is Implemented and Invalidated Not Applicable; a Status column
    # that already gives the Planned Status keeps it, and the other value stays in the note.
    csv = (b'JOIN_ID,Evaluation,Status\n0xA1,Not planned,\n0xB2,Closed,\n0xC3,Planned,Not planned\n'
           b'0xD4,Invalidated,\n')
    result = client.post('/api/non-qualified-calls/analyses/import', files={'file': ('mtl.csv', io.BytesIO(csv), 'text/csv')}).json()
    assert result['new_options'] == [] or all(item['field'] != 'Implementation Status' for item in result['new_options'])
    found = {call['join_id']: call['values'] for call in query(client)['calls']}
    assert (found['0xA1'].get('implementation_status', ''), found['0xA1']['planned_status']) == ('', 'Not Planned')
    assert found['0xB2']['implementation_status'] == 'Implemented'
    assert (found['0xC3'].get('implementation_status', ''), found['0xC3']['planned_status']) == ('', 'Not Planned')
    notes = [comment['body'] for comment in client.get(f"/api/non-qualified-calls/calls/{calls['0xC3']['call_key']}").json()['comments']]
    assert any('Implementation Status: Planned' in body for body in notes)
    options = [option['name'] for field in nq.list_fields(core.repository) if field['key'] == 'implementation_status'
               for option in field['options']]
    assert options == ['Not yet evaluated', 'Under evaluation', 'Evaluated', 'Implemented', 'Not Applicable']


def test_workspaces_before_move_the_planning_values_out_of_the_implementation_status(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    # A workspace of before: planning, invalidated and closed values in the Implementation Status, its first value grey.
    fields = nq.list_fields(repository)
    implementation = next(field for field in fields if field['key'] == 'implementation_status')
    implementation['options'] = [dict(option, color=nq.V18_FORMER_NOT_EVALUATED_COLOR) if option['name'] == 'Not yet evaluated' else option
                                 for option in implementation['options'] if option['name'] != 'Not Applicable']
    implementation['options'] += [{'name': name, 'color': ''} for name in ('Not Planned', 'Planned', 'Invalidated', 'Closed')]
    nq._store_fields(repository, fields)
    patch(client, calls['0xA1'], {'fields': {'implementation_status': 'Not Planned'}})
    patch(client, calls['0xB2'], {'fields': {'implementation_status': 'Planned', 'planned_status': 'Not Planned'}})
    patch(client, calls['0xC3'], {'fields': {'implementation_status': 'Closed'}})
    repository.set_workspace_state(nq.SAVED_FILTERS_STATE_KEY, json.dumps({'fields': {'implementation_status': ['Planned', 'Invalidated']}}))
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V18_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    upgraded = {field['key']: field for field in nq.list_fields(repository)}
    assert [option['name'] for option in upgraded['implementation_status']['options']] == [
        'Not yet evaluated', 'Under evaluation', 'Evaluated', 'Implemented']
    assert upgraded['implementation_status']['options'][0]['color'] == '#b0234f'
    found = {call['join_id']: call for call in query(client)['calls']}
    assert (found['0xA1']['values'].get('implementation_status', ''), found['0xA1']['values']['planned_status']) == ('', 'Not Planned')
    # 0xB2 keeps its own Planned Status; its history tells the value removed.
    assert (found['0xB2']['values'].get('implementation_status', ''), found['0xB2']['values']['planned_status']) == ('', 'Not Planned')
    history = client.get(f"/api/non-qualified-calls/calls/{calls['0xB2']['call_key']}").json()['history']
    assert any(entry['field'] == 'field:implementation_status' and entry['old_value'] == 'Planned' for entry in history)
    # Closed is Implemented, so the call is closed by the Status Rules.
    assert found['0xC3']['values']['implementation_status'] == 'Implemented' and found['0xC3']['status'] == 'Closed'
    assert json.loads(repository.get_workspace_state(nq.SAVED_FILTERS_STATE_KEY))['fields'] == {
        'implementation_status': ['Not Applicable'], 'planned_status': ['Planned']}


def test_workspaces_before_make_open_the_group_of_the_phase_statuses(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    # A workspace of before: the status Open, given by the rule of the attended calls and set by hand on one call.
    with repository.connection() as connection:
        connection.execute(f"UPDATE {nq.NQ_CALL_OPTIONS_TABLE} SET position = position + 1 WHERE kind = 'status' AND position > 0")
        connection.execute(f"INSERT INTO {nq.NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('status', 'Open', '#d14a68', 1, 0)")
    rules = nq.status_rules(repository)
    rules[-1]['status'] = 'Open'
    repository.set_workspace_state(nq.STATUS_RULES_STATE_KEY, json.dumps(rules))
    client.post(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}/comments", json={'body': 'Looking at it'})
    patch(client, calls['0xB2'], {'status': 'Open'})
    assert {item['join_id']: item['status'] for item in query(client)['calls']} == {'0xA1': 'Open', '0xB2': 'Open', '0xC3': 'Not Attended'}
    repository.set_workspace_state(nq.SAVED_FILTERS_STATE_KEY, json.dumps({'status': ['Open', 'Closed']}))
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V19_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    assert 'Open' not in [item['name'] for item in nq.list_options(repository)['statuses']]
    assert nq.status_rules(repository)[-1]['status'] == 'Under Analysis'
    found = {item['join_id']: item for item in query(client)['calls']}
    assert (found['0xA1']['status'], found['0xA1']['status_mode']) == ('Under Analysis', 'auto')
    assert (found['0xB2']['status'], found['0xB2']['status_mode']) == ('Under Analysis', 'manual')
    assert json.loads(repository.get_workspace_state(nq.SAVED_FILTERS_STATE_KEY))['status'] == [
        'Under Analysis', 'Under Implementation', 'Under Planning', 'Closed']


def test_the_progress_view_counts_the_statuses_the_rules_set(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    # The Status Rules close the call (Implemented) and move another one Under Implementation, without a status by hand.
    patch(client, calls['0xA1'], {'fields': {'implementation_status': 'Implemented'}})
    patch(client, calls['0xB2'], {'fields': {'implementation_status': 'Under evaluation'}})
    progress = client.post('/api/non-qualified-calls/progress', json={'filters': {}, 'granularity': 'week'}).json()
    assert sum(period['closed'] for period in progress['periods']) == 1
    moved = Counter()
    for period in progress['periods']:
        moved.update(period['statuses'])
    assert moved['Closed'] == 1 and moved['Under Implementation'] == 1
    # The moves to a closed status are the Closed column, not one of their own; the days to close count from the call.
    assert 'Closed' not in progress['statuses'] and 'Under Implementation' in progress['statuses']
    assert progress['summary']['avg_days_to_close'] > 1


def test_the_default_rules_go_from_the_end_of_the_pipeline_and_invalid_analyses_are_invalidated(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    rules = nq_catalog.default_status_rules()
    assert [rule['status'] for rule in rules] == ['Closed', 'Closed', 'Closed', 'Under Planning', 'Under Implementation',
                                                 'Under Analysis', 'Under Analysis']
    # A finished analysis closes the call unless it is planned or in implementation.
    evaluate = lambda values: nq_catalog.evaluate_status(rules, {'@attended': 'Yes', **values}, 'Not Attended')
    assert evaluate({'analysis_status': 'Finished'}) == 'Closed'
    assert evaluate({'analysis_status': 'Finished', 'planned_status': 'Planned'}) == 'Under Planning'
    assert evaluate({'analysis_status': 'Finished', 'implementation_status': 'Under evaluation'}) == 'Under Implementation'
    # No_Vendor_B and No_JoinID Missing of the analyses are Invalidated, the note keeping them as written.
    csv = b'JOIN_ID,Analysis Finished\n0xA1,No_Vendor_B\n0xB2,No_JoinID Missing\n'
    client.post('/api/non-qualified-calls/analyses/import', files={'file': ('mtl.csv', io.BytesIO(csv), 'text/csv')})
    found = {call['join_id']: call for call in query(client)['calls']}
    assert found['0xA1']['values']['analysis_status'] == found['0xB2']['values']['analysis_status'] == 'Invalidated'
    assert found['0xA1']['status'] == 'Closed'
    notes = [comment['body'] for comment in client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()['comments']]
    assert any('Analysis Status (as written): No_Vendor_B' in body for body in notes)


def test_workspaces_before_invalidate_the_invalid_analyses_and_renumber_their_default_rules(client, tmp_path):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    fields = nq.list_fields(repository)
    analysis = next(field for field in fields if field['key'] == 'analysis_status')
    analysis['options'] += [{'name': 'No_Vendor_B', 'color': ''}, {'name': 'No_JoinID Missing', 'color': ''}]
    nq._store_fields(repository, fields)
    patch(client, calls['0xA1'], {'fields': {'analysis_status': 'No_Vendor_B'}})
    former = [{'status': status, 'conditions': [{'field': field, 'op': op, 'values': list(values)} for field, op, values in conditions]}
              for status, conditions in nq.V20_FORMER_RULES]
    repository.set_workspace_state(nq.STATUS_RULES_STATE_KEY, json.dumps(former))
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V20_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    assert nq.status_rules(repository) == nq_catalog.default_status_rules()
    options = [option['name'] for field in nq.list_fields(repository) if field['key'] == 'analysis_status' for option in field['options']]
    assert 'No_Vendor_B' not in options and 'No_JoinID Missing' not in options and 'Invalidated' in options
    call = {item['join_id']: item for item in query(client)['calls']}['0xA1']
    assert (call['values']['analysis_status'], call['status']) == ('Invalidated', 'Closed')
    history = client.get(f"/api/non-qualified-calls/calls/{calls['0xA1']['call_key']}").json()['history']
    assert any(entry['field'] == 'field:analysis_status' and entry['old_value'] == 'No_Vendor_B' for entry in history)
    # Rules changed by the workspace stay as they are.
    custom = [{'status': 'Closed', 'conditions': [{'field': 'analysis_status', 'op': 'in', 'values': ['Finished']}]}]
    repository.set_workspace_state(nq.STATUS_RULES_STATE_KEY, json.dumps(custom))
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V20_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    assert nq.status_rules(repository) == custom


def test_rf_is_blue_also_in_workspaces_before(client, tmp_path):
    setup_calls(client, tmp_path)
    repository = core.repository
    domains = lambda: {item['name']: item['color'] for item in nq.list_root_causes(repository)['domains']}
    assert domains()['RF'] == '#3a7fc1'
    with repository.connection() as connection:
        connection.execute(f"UPDATE {nq.NQ_ROOT_CATALOG_TABLE} SET color = '#C8102E' WHERE kind = 'domain' AND name = 'RF'")
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V21_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    assert domains()['RF'] == '#3a7fc1'
    # A colour chosen in the workspace stays.
    with repository.connection() as connection:
        connection.execute(f"UPDATE {nq.NQ_ROOT_CATALOG_TABLE} SET color = '#123456' WHERE kind = 'domain' AND name = 'RF'")
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V21_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    assert domains()['RF'] == '#123456'


def test_the_documents_leave_out_not_classified_and_empty_unless_asked(monkeypatch):
    from src.modules import non_qualified_calls_export as export
    from src.modules import non_qualified_calls_visuals as visuals

    stats = {'source': 'netcheck', 'summary': {'total': 10}, 'columns': ['RF', 'Not classified'],
             'domains': [{'value': 'RF', 'count': 4}, {'value': 'Not classified', 'count': 6}],
             'categories': [{'domain': 'RF', 'category': 'Coverage', 'count': 4}], 'causes': [],
             'call_types': [{'name': 'Data', 'total': 7, 'counts': {'RF': 1, 'Not classified': 6}},
                            {'name': 'Classic', 'total': 3, 'counts': {'RF': 3}}],
             'nr_modes': [{'name': 'SA', 'total': 6, 'counts': {'Not classified': 6}}],
             'technologies': [{'name': 'LTE', 'total': 7, 'counts': {'RF': 1, 'Not classified': 6}},
                              {'name': 'NR', 'total': 3, 'counts': {'RF': 3}}], 'nodes': []}
    shown = export.classified_root_stats(stats)
    assert shown['columns'] == ['RF'] and [item['value'] for item in shown['domains']] == ['RF']
    assert [(row['name'], row['total']) for row in shown['call_types']] == [('Data', 1), ('Classic', 3)]
    assert shown['nr_modes'] == [] and [row['name'] for row in shown['technologies']] == ['NR', 'LTE']
    # The documents draw the panels from these, unless Show Not classified and Show Empty Status are asked for.
    drawn = {}
    monkeypatch.setattr(visuals, 'root_cause_panels', lambda value: drawn.setdefault('root', value) and [])
    monkeypatch.setattr(visuals, 'lifecycle_panels', lambda value, sections=None: drawn.setdefault('life', value) and [])
    for name in ('executive_summary_panels', 'progress_view_panels', 'rate_panels', 'rca_insight_panels'):
        monkeypatch.setattr(visuals, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(export, 'root_cause_table_panels', lambda value: [])
    monkeypatch.setattr(export, 'detail_tables', lambda progress: [])
    life = {'phases': [{'key': 'analysis_status', 'empty': 5, 'items': []}]}
    export.report_panels({}, [], {'granularity': 'month'}, {'root_causes': [stats], 'lifecycle': life})
    assert drawn['root']['columns'] == ['RF'] and drawn['life']['phases'][0]['empty'] == 0
    drawn.clear()
    export.report_panels({}, [], {'granularity': 'month'}, {'root_causes': [stats], 'lifecycle': life,
                                                            'show_not_classified': True, 'show_empty': True})
    assert drawn['root'] is stats and drawn['life']['phases'][0]['empty'] == 5


@pytest.mark.parametrize('no_team_exists', [False, True])
def test_successful_call_excluded_is_no_longer_a_team_and_its_calls_go_to_no_team(client, tmp_path, no_team_exists):
    calls = setup_calls(client, tmp_path)
    repository = core.repository
    assert 'Successful Call-Excluded' not in [team['name'] for team in nq.list_options(repository)['teams']]
    # A workspace of before: the team and the Implementation Stream, with a call.
    fields = nq.list_fields(repository)
    stream = next(field for field in fields if field['key'] == 'implementation_team')
    stream['key'], stream['label'] = 'implementation_stream', 'Implementation Stream'
    stream['options'].append({'name': 'Successful Call-Excluded', 'color': ''})
    priority = next(field for field in fields if field['key'] == 'priority')
    assert [option['name'] for option in priority['options']] == [f'P{number}' for number in range(1, 9)]
    priority['options'] = priority['options'][:4]
    nq._store_fields(repository, fields)
    with repository.connection() as connection:
        connection.execute(f"INSERT INTO {nq.NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) "
                           "VALUES ('team', 'Successful Call-Excluded', '#7b8790', 50, 0)")
        if no_team_exists:
            connection.execute(f"INSERT INTO {nq.NQ_CALL_OPTIONS_TABLE} (kind, name, color, position, is_closed) VALUES ('team', 'No Team', '', 51, 0)")
    patch(client, calls['0xA1'], {'team': 'Successful Call-Excluded', 'fields': {'implementation_stream': 'Successful Call-Excluded'}})
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V10_STATE_KEY, '')
    repository.set_workspace_state(nq.ANALYSIS_CENTER_V12_STATE_KEY, '')
    nq.ensure_nq_tables(repository)
    teams = [team['name'] for team in nq.list_options(repository)['teams']]
    assert 'Successful Call-Excluded' not in teams and teams.count('No Team') == 1
    options = [option['name'] for field in nq.list_fields(repository) if field['key'] == 'implementation_team' for option in field['options']]
    assert 'Successful Call-Excluded' not in options and 'No Team' in options
    assert [option['name'] for field in nq.list_fields(repository) if field['key'] == 'priority' for option in field['options']] == [
        'P1', 'P2', 'P3', 'P4', 'P5']
    call = {item['join_id']: item for item in query(client)['calls']}['0xA1']
    assert (call['team'], call['values']['implementation_team']) == ('No Team', 'No Team')
    # The analysis workbooks that still name it give No Team too.
    csv = b'JOIN_ID,Responsible Stream\n0xB2,Successful Call-Excluded\n'
    client.post('/api/non-qualified-calls/analyses/import', files={'file': ('mtl.csv', io.BytesIO(csv), 'text/csv')})
    assert {item['join_id']: item for item in query(client)['calls']}['0xB2']['team'] == 'No Team'


def test_the_import_of_previous_analyses_streams_its_progress(client, tmp_path):
    setup_calls(client, tmp_path)
    csv = b'JOIN_ID,Analysis Status,Findings\n0xA1,Finished,Weak DL\n0xZZ,Finished,\n'
    response = client.post('/api/non-qualified-calls/analyses/import', data={'stream': '1'},
                           files={'file': ('analyses.csv', io.BytesIO(csv), 'text/csv')})
    assert response.status_code == 200 and response.headers['content-type'].startswith('application/x-ndjson')
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    steps = [event for event in events if 'step' in event]
    assert steps[0]['step'] == 'Reading the file' and steps[-1] == {'step': 'Done', 'progress': 1.0}
    assert [event['progress'] for event in steps] == sorted(event['progress'] for event in steps)
    assert 'Writing the analyses' in {event['step'] for event in steps}
    assert events[-1]['result']['changed'] == 1 and events[-1]['result']['pending'] == 1
    # A file that cannot be read ends the stream with its error.
    bad = client.post('/api/non-qualified-calls/analyses/import', data={'stream': '1'},
                      files={'file': ('analyses.csv', io.BytesIO(b'Nothing,Here\n1,2\n'), 'text/csv')})
    assert 'JOIN_ID column' in [json.loads(line) for line in bad.text.splitlines() if line.strip()][-1]['error']
