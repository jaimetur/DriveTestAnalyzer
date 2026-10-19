"""The Role of each Operator label of the Operator Maps: Focus (the Focus operators of the Scoring exports) or Exclude
(left out of every analysis, filter, chart and report)."""
import json
import sqlite3

import numpy as np
import pandas as pd

import src.DriveTestAnalyzer as core
from src.modules.operator_roles import (
    drop_excluded_operators, excluded_operators, focus_operators, normalize_mapping_role, with_exclusions,
)
from src.modules.repository import Repository
from src.modules.value_maps import ValueMapper

GROUPS = [
    {'canonical': 'VF', 'aliases': ['Vodafone'], 'position': 0, 'color': '#E60000', 'role': 'focus'},
    {'canonical': 'Three', 'aliases': ['3', 'Three UK'], 'position': 1, 'color': '#000000', 'role': 'focus'},
    {'canonical': 'EE', 'aliases': [], 'position': 2, 'color': '#76B7B2'},
    {'canonical': 'Lebara', 'aliases': ['LEB'], 'position': 3, 'color': '#6F42C1', 'role': 'exclude'},
]


def login(client, username='super', password='super123'):
    client.cookies.clear()
    response = client.post('/login', data={'username': username, 'password': password}, follow_redirects=False)
    assert response.status_code == 303


def test_roles_name_the_focus_and_excluded_operators_with_every_name_of_the_cdrs():
    assert [normalize_mapping_role(value) for value in ('Focus', ' EXCLUDE ', 'other', None)] == ['focus', 'exclude', '', '']
    assert focus_operators(GROUPS) == ['VF', 'Vodafone', 'Three', '3', 'Three UK']
    assert excluded_operators({'operator_mapping_groups': GROUPS}) == ['Lebara', 'LEB']
    # An Operator filter leaves them out too: All becomes every operator but them.
    assert with_exclusions([], GROUPS) == ['-Lebara', '-LEB']
    assert with_exclusions(['VF', '-lebara'], GROUPS) == ['VF', '-lebara', '-LEB']
    frame = pd.DataFrame({'Operator': ['VF', ' leb ', 'Lebara', None, 'EE'], 'value': range(5)})
    assert drop_excluded_operators(frame, excluded_operators(GROUPS))['value'].tolist() == [0, 3, 4]
    assert drop_excluded_operators(frame, []) is frame


def test_lists_of_values_leave_out_the_excluded_operators():
    mapper = ValueMapper({'leb': 'Lebara', 'vodafone': 'VF'}, {}, GROUPS, [])
    assert mapper.values('operator', ['Vodafone', 'LEB', 'EE', 'Lebara']) == ['VF', 'EE']
    assert mapper.values('operator_vendor', ['Lebara_Ericsson', 'VF_Ericsson', 'Lebara - All']) == ['VF_Ericsson']
    assert mapper.values('vendor_operator', ['Ericsson_Lebara', 'Nokia_EE']) == ['Nokia_EE']
    assert mapper.values('vendor', ['Lebara']) == ['Lebara']
    assert mapper.excludes_operator(None, 'leb') and not mapper.excludes_operator('VF')


def test_the_operator_maps_keep_the_role_of_each_label(tmp_path):
    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'application.db')
    repository.initialize()
    repository.replace_operator_mapping_group(None, 'VF', ['Vodafone'], '#E60000', 'focus')
    repository.replace_operator_mapping_group(None, 'Lebara', ['LEB'], '#6F42C1', 'exclude')
    repository.replace_operator_mapping_group(None, 'EE', [], '#76B7B2')
    assert [(group['canonical'], group.get('role')) for group in repository.list_operator_mapping_groups()] == [
        ('VF', 'focus'), ('Lebara', 'exclude'), ('EE', None)]
    # Saved again without a role it keeps its own; replaced as a whole (imports, transfers, restores) each keeps the one given.
    repository.replace_operator_mapping_group('VF', 'VF', ['Vodafone', 'VF UK'], '#E60000')
    assert repository.list_operator_mapping_groups()[0]['role'] == 'focus'
    groups = repository.list_operator_mapping_groups()
    repository.replace_operator_mapping_groups([{**groups[0], 'role': ''}, *groups[1:]])
    assert [group.get('role') for group in repository.list_operator_mapping_groups()] == [None, 'exclude', None]


def test_a_workspace_database_written_before_the_roles_reads_none_and_takes_them_when_written(tmp_path):
    path = tmp_path / 'earlier.db'
    with sqlite3.connect(path) as connection:
        connection.executescript(
            'CREATE TABLE operator_mappings (source_value TEXT PRIMARY KEY COLLATE NOCASE, canonical_value TEXT NOT NULL);'
            'CREATE TABLE vendor_mappings (source_value TEXT PRIMARY KEY COLLATE NOCASE, canonical_value TEXT NOT NULL);'
            'CREATE TABLE chart_mapping_groups (mapping_type TEXT NOT NULL, canonical_value TEXT NOT NULL COLLATE NOCASE, '
            'position INTEGER NOT NULL DEFAULT 0, color TEXT NOT NULL, PRIMARY KEY (mapping_type, canonical_value));'
            "INSERT INTO chart_mapping_groups VALUES ('operator', 'EE', 0, '#76B7B2');"
            "INSERT INTO operator_mappings VALUES ('EE', 'EE');")
    repository = Repository(path, global_db_path=tmp_path / 'application.db')
    assert repository.list_operator_mapping_groups() == [{'canonical': 'EE', 'aliases': [], 'position': 0, 'color': '#76B7B2'}]
    repository.replace_operator_mapping_group(None, 'Lebara', [], '#6F42C1', 'exclude')
    assert repository.list_operator_mapping_groups()[-1]['role'] == 'exclude'


def test_the_operator_maps_editor_saves_the_role_of_each_label(client):
    login(client)
    response = client.post('/workspace-config/operator-mappings/save', data={
        'canonical_value': 'Lebara', 'aliases': 'LEB', 'color': '#6F42C1', 'role': 'exclude'}, follow_redirects=False)
    assert response.status_code == 303
    group = next(item for item in core.repository.list_operator_mapping_groups() if item['canonical'] == 'Lebara')
    assert group['role'] == 'exclude'
    # A page without the field keeps it; the role given changes it.
    client.post('/workspace-config/operator-mappings/save', data={
        'original_canonical': 'Lebara', 'canonical_value': 'Lebara', 'aliases': 'LEB\nLUK', 'color': '#6F42C1'})
    assert next(item for item in core.repository.list_operator_mapping_groups() if item['canonical'] == 'Lebara')['role'] == 'exclude'
    client.post('/workspace-config/operator-mappings/save', data={
        'original_canonical': 'Lebara', 'canonical_value': 'Lebara', 'aliases': 'LEB', 'color': '#6F42C1', 'role': 'focus'})
    assert next(item for item in core.repository.list_operator_mapping_groups() if item['canonical'] == 'Lebara')['role'] == 'focus'
    details = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'operator_mapping_group_save']
    assert {'role': 'focus', 'previous_role': 'exclude'}.items() <= details[0].items()
    # The Role column sits beside each Operator label (the Vendor Maps have none).
    page = client.get('/workspace-config').text
    operators = page[page.index('id="operator-maps"'):page.index('id="vendor-maps"')]
    vendors = page[page.index('id="vendor-maps"'):page.index('id="campaign-maps"')]
    assert 'mapping-role-column' in operators and 'mapping-role-column' not in vendors
    assert '<option value="focus" selected>Focus</option>' in operators


def test_the_dashboard_column_cache_leaves_out_the_excluded_values():
    from src.modules.dashboard_column_cache import SelectionTerms, keep_sheets

    terms = SelectionTerms(excluded_values=(('lower(operator)', frozenset({'lebara', 'leb'})),))
    assert terms.expressions() == ['lower(operator)']
    part = ('str', np.array([0, 1, -1, 2]), ['vf', 'lebara', 'leb'])
    assert keep_sheets(part, frozenset({'lebara', 'leb'})).tolist() == [True, False, True, False]


def test_non_qualified_calls_leave_out_the_excluded_operators():
    from src.modules.non_qualified_calls import _filter_sql

    where, params = _filter_sql({'_excluded_operators': ['Lebara', 'LEB']}, 'tester', [])
    assert "lower(COALESCE(operator, '')) NOT IN (?, ?)" in where and params[-2:] == ['lebara', 'leb']


def test_at_least_one_operator_label_stays_included(tmp_path):
    import pytest

    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'application.db')
    repository.initialize()
    with pytest.raises(ValueError, match='At least one Operator label must not be excluded'):
        repository.replace_operator_mapping_group(None, 'Lebara', ['LEB'], '#6F42C1', 'exclude')
    assert repository.list_operator_mapping_groups() == []
    repository.replace_operator_mapping_group(None, 'VF', [], '#E60000')
    repository.replace_operator_mapping_group(None, 'Lebara', ['LEB'], '#6F42C1', 'exclude')
    # Excluding, deleting or replacing the last label not excluded is refused, and nothing changes.
    for change in (lambda: repository.replace_operator_mapping_group('VF', 'VF', [], '#E60000', 'exclude'),
                   lambda: repository.delete_operator_mapping_group('VF'),
                   lambda: repository.replace_operator_mapping_groups(
                       [{**group, 'role': 'exclude'} for group in repository.list_operator_mapping_groups()])):
        with pytest.raises(ValueError, match='At least one Operator label must not be excluded'):
            change()
        assert [(group['canonical'], group.get('role')) for group in repository.list_operator_mapping_groups()] == [
            ('VF', None), ('Lebara', 'exclude')]
    # The Vendor Maps have no roles, and a workspace without labels is fine.
    repository.delete_operator_mapping_group('Lebara')
    repository.delete_operator_mapping_group('VF')
    assert repository.list_operator_mapping_groups() == []


def test_the_operator_maps_editor_keeps_one_operator_included(client):
    import shutil
    import subprocess
    from pathlib import Path
    from urllib.parse import parse_qs, urlparse

    import pytest

    login(client)
    repository = core.repository
    if not repository.list_operator_mapping_groups():
        repository.replace_operator_mapping_group(None, 'VF', [], '#E60000')
    groups = repository.list_operator_mapping_groups()
    last = next(group for group in groups if group.get('role') != 'exclude')
    for group in (group for group in groups if group is not last and group.get('role') != 'exclude'):
        repository.replace_operator_mapping_group(group['canonical'], group['canonical'], group['aliases'], group['color'], 'exclude')
    response = client.post('/workspace-config/operator-mappings/save', data={
        'original_canonical': last['canonical'], 'canonical_value': last['canonical'], 'aliases': '\n'.join(last['aliases']),
        'color': last['color'], 'role': 'exclude'}, follow_redirects=False)
    error = parse_qs(urlparse(response.headers['location']).query)['operator_mapping_error'][0]
    assert error.startswith('At least one Operator label must not be excluded')
    assert next(group for group in repository.list_operator_mapping_groups()
                if group['canonical'] == last['canonical']).get('role') == last.get('role')

    # The page puts the Role back at once, and adds no label as excluded when every label is.
    script = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/app.js').read_text(encoding='utf-8')
    helpers = script[script.index('const OPERATOR_ROLE_LAST_INCLUDED'):script.index("document.addEventListener('submit', (event) => {\n  const form")]
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for the Operator Maps editor checks.')
    program = helpers + r"""
const dialogs = [];
const showInfoDialog = (message) => dialogs.push(message);
const option = (value, selected) => ({value, defaultSelected: selected});
const select = (value) => ({value, options: [option('', value === ''), option('focus', value === 'focus'), option('exclude', value === 'exclude')],
  closest: (selector) => selector.startsWith('form') ? null : panel});
const selects = [select(''), select('exclude')];
const panel = {querySelectorAll: () => selects};
selects[0].value = 'exclude';
const refused = keepOneOperatorIncluded(selects[0]);
const after = selects.map(item => item.value);
selects[0].value = 'focus';
const accepted = keepOneOperatorIncluded(selects[0]);
console.log(JSON.stringify({refused, after, accepted, dialogs: dialogs.length, none: everyOperatorExcluded([]),
  newOnly: everyOperatorExcluded(['exclude'])}));
"""
    completed = subprocess.run([node, '-e', program], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {'refused': False, 'after': ['', 'exclude'], 'accepted': True, 'dialogs': 1,
                                            'none': False, 'newOnly': True}
