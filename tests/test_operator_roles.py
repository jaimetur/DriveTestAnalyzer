"""The Role of each Operator label of the Operator Maps: Focus (the Focus operators of the Scoring exports) or Exclude
(left out of every analysis, filter, chart and report)."""
import json
import sqlite3

import numpy as np
import pandas as pd

import src.DriveTestAnalyzer as core
from src.modules.operator_roles import (
    drop_excluded_operators, drop_out_of_scope_operators, excluded_operators, focus_operators, normalize_mapping_role,
    normalize_nr_modes, out_of_scope_operators, out_of_scope_pairs, out_of_scope_sql, with_exclusions,
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
    # Include, posted as such (an empty value would reach the server as no value), takes the Role away.
    client.post('/workspace-config/operator-mappings/save', data={
        'original_canonical': 'Lebara', 'canonical_value': 'Lebara', 'aliases': 'LEB', 'color': '#6F42C1', 'role': 'include'})
    assert 'role' not in next(item for item in core.repository.list_operator_mapping_groups() if item['canonical'] == 'Lebara')
    details = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'operator_mapping_group_save']
    assert {'role': '', 'previous_role': 'focus'}.items() <= details[0].items()
    client.post('/workspace-config/operator-mappings/save', data={
        'original_canonical': 'Lebara', 'canonical_value': 'Lebara', 'aliases': 'LEB', 'color': '#6F42C1', 'role': 'focus'})
    # The Role column sits beside each Operator label (the Vendor Maps have none).
    page = client.get('/workspace-config').text
    operators = page[page.index('id="operator-maps"'):page.index('id="vendor-maps"')]
    vendors = page[page.index('id="vendor-maps"'):page.index('id="campaign-maps"')]
    assert 'mapping-role-column' in operators and 'mapping-role-column' not in vendors
    # A note above the labels explains what each Role does.
    assert 'data-mapping-role-help' in operators and 'data-mapping-role-help' not in vendors
    assert '<option value="focus" selected>Focus</option>' in operators
    # A label with neither role shows Include.
    assert '<option value="include" selected>Include</option>' in operators and '>None</option>' not in operators


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
const select = (value) => ({value, options: [option('include', value === 'include'), option('focus', value === 'focus'), option('exclude', value === 'exclude')],
  closest: (selector) => selector.startsWith('form') ? null : panel});
const selects = [select('include'), select('exclude')];
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
    assert json.loads(completed.stdout) == {'refused': False, 'after': ['include', 'exclude'], 'accepted': True, 'dialogs': 1,
                                            'none': False, 'newOnly': True}


def test_the_names_of_the_cdrs_show_the_role_of_their_label_read_only(client, monkeypatch):
    import shutil
    import subprocess
    from pathlib import Path

    import pytest
    from lxml import html

    login(client)
    core.repository.replace_operator_mapping_groups(GROUPS)
    rows = [{'value': 'Vodafone UK', 'cdrs': ['a.csv'], 'label': 'VF', 'assigned': True, 'canonical': False, 'merged_with': []},
            {'value': 'LEB', 'cdrs': ['a.csv'], 'label': 'Lebara', 'assigned': True, 'canonical': False, 'merged_with': []},
            {'value': 'EE', 'cdrs': ['a.csv'], 'label': 'EE', 'assigned': True, 'canonical': True, 'merged_with': []},
            {'value': 'Sky', 'cdrs': ['a.csv'], 'label': 'Sky', 'assigned': False, 'canonical': False, 'merged_with': []}]
    monkeypatch.setattr(core, 'mapping_assignment_rows', lambda: {'operator': rows, 'vendor': rows})
    page = html.fromstring(client.get('/workspace-config').text)
    table = page.xpath('//*[@id="operator-assignments"]//table')[0]
    # After the Status, the Role of the label of each name (read only), then its comments.
    assert [th.text_content().strip() for th in table.xpath('.//th')][3:] == [
        'Status', 'RoleOf its label, below', 'CommentsWhat this name holds, as a reminder']
    badges = {row.xpath('.//input[@name="source"]/@value')[0]: row.xpath('.//*[@data-mapping-role-badge]')[0]
              for row in table.xpath('.//tbody/tr')}
    assert {name: (badge.text_content(), badge.get('class'), badge.get('hidden') is not None) for name, badge in badges.items()} == {
        'Vodafone UK': ('Focus', 'mapping-role-badge is-focus', False),
        'LEB': ('Exclude', 'mapping-role-badge is-exclude', False),
        'EE': ('Include', 'mapping-role-badge is-include', False),
        # A name without a label has no Role.
        'Sky': ('', 'mapping-role-badge', True)}
    # The Vendor Maps have no Role.
    assert not page.xpath('//*[@id="vendor-assignments"]//*[@data-mapping-role-badge]')

    # The Role follows the label chosen for a name, before it is saved.
    script = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/app.js').read_text(encoding='utf-8')
    start = script.index('function refreshMappingRoleBadge(select) {')
    helper = script[start:script.index('\n}\n', start) + 3]
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for the Operator Maps editor checks.')
    program = helper + r"""
const badge = {hidden: false, className: '', textContent: ''};
const choose = (value, role) => {
  refreshMappingRoleBadge({value, selectedOptions: [{dataset: role === undefined ? {} : {role}}], closest: () => ({querySelector: () => badge})});
  return [badge.hidden, badge.className, badge.textContent];
};
console.log(JSON.stringify([choose('VF', 'focus'), choose('Lebara', 'exclude'), choose('BT', ''), choose('__new__'), choose('')]));
"""
    completed = subprocess.run([node, '-e', program], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == [
        [False, 'mapping-role-badge is-focus', 'Focus'], [False, 'mapping-role-badge is-exclude', 'Exclude'],
        [False, 'mapping-role-badge is-include', 'Include'], [False, 'mapping-role-badge is-include', 'Include'],
        [True, 'mapping-role-badge', '']]


def test_the_nr_modes_of_a_label_leave_its_tests_of_the_other_nr_mode_out_of_scope():
    groups = [GROUPS[0], {**GROUPS[1], 'nr_modes': ['NSA']}, GROUPS[2], {**GROUPS[3], 'nr_modes': ['SA']}]
    assert [normalize_nr_modes(value) for value in ('NSA', ' sa ', 'NSA,SA', ['SA', 'NSA'], '', None, ['5G'])] == [
        ['NSA'], ['SA'], [], [], [], [], []]
    # Lebara, excluded with its Role, is out in every NR Mode anyway.
    assert out_of_scope_pairs(groups) == [{'nr_mode': 'SA', 'operator': 'Three'}]
    assert out_of_scope_operators(groups, 'SA') == ['Three', '3', 'Three UK']
    assert out_of_scope_operators(groups, 'NSA') == out_of_scope_operators(groups, None) == []
    frame = pd.DataFrame({'Operator': ['VF', ' three uk ', '3', 'EE'], 'value': range(4)})
    assert drop_out_of_scope_operators(frame, groups, 'SA')['value'].tolist() == [0, 3]
    assert drop_out_of_scope_operators(frame, groups, 'NSA') is frame
    # An SQL condition on the rows of several CDRs of one table, by the NR Mode of each, or on those of one CDR.
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE rows (dataset_id INTEGER, Operator TEXT)')
    connection.executemany('INSERT INTO rows VALUES (?, ?)', [(1, 'Three'), (1, 'VF'), (2, ' 3 '), (2, 'VF'), (3, None)])
    clause, params = out_of_scope_sql(groups, {1: 'NSA', 2: 'SA', 3: 'SA'}, '"Operator"', 'dataset_id')
    assert connection.execute(f'SELECT dataset_id, Operator FROM rows WHERE {clause} ORDER BY rowid', params).fetchall() == [
        (1, 'Three'), (1, 'VF'), (2, 'VF'), (3, None)]
    clause, params = out_of_scope_sql(groups, {2: 'SA'}, '"Operator"')
    assert connection.execute(f'SELECT Operator FROM rows WHERE dataset_id = 2 AND {clause}', params).fetchall() == [('VF',)]
    assert out_of_scope_sql(groups, {1: 'NSA'}, '"Operator"') == ('1', [])
    connection.close()
    # Nor do the lists of values offer them for those CDRs.
    mapper = ValueMapper({'3': 'Three'}, {}, groups, [])
    assert mapper.excluded_value('operator_vendor', 'Three_Ericsson', out_of_scope_operators(groups, 'SA'))
    assert not mapper.excluded_value('operator', 'Three') and not mapper.excluded_value('operator', 'VF', ['Three'])


def test_the_operator_maps_keep_the_nr_modes_of_each_label(tmp_path):
    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'application.db')
    repository.initialize()
    repository.replace_operator_mapping_group(None, 'VF', ['Vodafone'], '#E60000', 'focus')
    repository.replace_operator_mapping_group(None, 'Three', ['3'], '#000000', 'focus', ['NSA'])
    assert [(group['canonical'], group.get('nr_modes')) for group in repository.list_operator_mapping_groups()] == [
        ('VF', None), ('Three', ['NSA'])]
    # Saved again without them it keeps its own; both NR Modes, the default, are not carried.
    repository.replace_operator_mapping_group('Three', 'Three', ['3', 'Three UK'], '#000000')
    assert repository.list_operator_mapping_groups()[1]['nr_modes'] == ['NSA']
    repository.replace_operator_mapping_group('Three', 'Three', ['3'], '#000000', None, 'NSA,SA')
    assert 'nr_modes' not in repository.list_operator_mapping_groups()[1]
    # Replaced as a whole (imports, transfers, restores) each label takes those given, both without them (a package of
    # before the NR Modes).
    groups = repository.list_operator_mapping_groups()
    repository.replace_operator_mapping_groups([{**groups[0], 'nr_modes': ['SA']}, groups[1]])
    assert [group.get('nr_modes') for group in repository.list_operator_mapping_groups()] == [['SA'], None]
    # The rows of a CDR leave out those of the operators out of scope in its NR Mode only when asked (an analysis; never a
    # rewrite of the rows).
    source = tmp_path / 'sa.csv'
    source.write_text('sa', encoding='utf-8')
    dataset_id, _created = repository.add_dataset('UK_Q3_SA_2026_Data.csv', str(source), 'super')
    repository.replace_dataset_rows(dataset_id, pd.DataFrame({'Operator': ['Vodafone', 'Three', '3', 'EE'], 'value': range(4)}))
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind='data', nr_mode='NSA', row_count=4)
    repository.replace_operator_mapping_group('VF', 'VF', ['Vodafone'], '#E60000', 'focus', [])
    repository.replace_operator_mapping_group('Three', 'Three', ['3'], '#000000', None, ['NSA'])
    assert repository.load_dataset_rows(dataset_id, ['value'], {}, in_scope_only=True)['value'].tolist() == [0, 1, 2, 3]
    repository.update_dataset_profile(dataset_id, nr_mode='SA')
    assert repository.load_dataset_rows(dataset_id, ['value'], {}, in_scope_only=True)['value'].tolist() == [0, 3]
    assert repository.load_dataset_rows(dataset_id, ['value'], {})['value'].tolist() == [0, 1, 2, 3]


def test_a_workspace_database_written_before_the_nr_modes_reads_none(tmp_path):
    path = tmp_path / 'earlier.db'
    with sqlite3.connect(path) as connection:
        connection.executescript(
            'CREATE TABLE operator_mappings (source_value TEXT PRIMARY KEY COLLATE NOCASE, canonical_value TEXT NOT NULL);'
            'CREATE TABLE vendor_mappings (source_value TEXT PRIMARY KEY COLLATE NOCASE, canonical_value TEXT NOT NULL);'
            'CREATE TABLE chart_mapping_groups (mapping_type TEXT NOT NULL, canonical_value TEXT NOT NULL COLLATE NOCASE, '
            "position INTEGER NOT NULL DEFAULT 0, color TEXT NOT NULL, role TEXT NOT NULL DEFAULT '', "
            'PRIMARY KEY (mapping_type, canonical_value));'
            "INSERT INTO chart_mapping_groups VALUES ('operator', 'Three', 0, '#000000', 'focus');"
            "INSERT INTO operator_mappings VALUES ('Three', 'Three');")
    repository = Repository(path, global_db_path=tmp_path / 'application.db')
    assert repository.list_operator_mapping_groups() == [
        {'canonical': 'Three', 'aliases': [], 'position': 0, 'color': '#000000', 'role': 'focus'}]
    repository.replace_operator_mapping_group('Three', 'Three', [], '#000000', None, ['NSA'])
    assert repository.list_operator_mapping_groups()[0]['nr_modes'] == ['NSA']


def test_the_operator_maps_editor_saves_the_nr_modes_of_each_label(client):
    login(client)
    group = next(item for item in core.repository.list_operator_mapping_groups()
                 if 'three' in {name.casefold() for name in [item['canonical'], *item['aliases']]})
    label, aliases = group['canonical'], '\n'.join(group['aliases'])

    def save(**fields):
        response = client.post('/workspace-config/operator-mappings/save', data={
            'original_canonical': label, 'canonical_value': label, 'aliases': aliases, 'color': group['color'], **fields},
            follow_redirects=False)
        assert response.status_code == 303 and 'operator_mapping_error' not in response.headers['location']
        return next(item for item in core.repository.list_operator_mapping_groups() if item['canonical'] == label)

    assert save(nr_modes='NSA')['nr_modes'] == ['NSA']
    # A page without the field keeps them; those given change them, and App Events records them before and after.
    assert save()['nr_modes'] == ['NSA']
    assert 'nr_modes' not in save(nr_modes='NSA,SA')
    details = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'operator_mapping_group_save']
    assert {'nr_modes': ['NSA', 'SA'], 'previous_nr_modes': ['NSA']}.items() <= details[0].items()
    # The NR Modes column sits beside the Role of each Operator label (the Vendor Maps have none).
    save(nr_modes='NSA')
    page = client.get('/workspace-config').text
    operators = page[page.index('id="operator-maps"'):page.index('id="vendor-maps"')]
    vendors = page[page.index('id="vendor-maps"'):page.index('id="campaign-maps"')]
    assert 'mapping-nr-modes-column' in operators and 'mapping-nr-modes-column' not in vendors
    assert '<option value="NSA" selected>NSA only</option>' in operators
    # Under them, what is out of scope; above the subpanels, what is out of scope in the workspace; and every page has the
    # pairs for the modules to name them beside their selection.
    assert 'data-mapping-nr-modes-note>SA out of scope in every module</span>' in operators
    summary = operators[operators.index('data-operator-scope-summary'):operators.index('id="operator-assignments"')]
    assert f'SA · {label}</span>' in summary and 'Non-Qualified Calls only' in summary
    assert f'<script id="operator-out-of-scope" type="application/json">[{{"nr_mode": "SA", "operator": "{label}"}}]</script>' in page


def test_every_module_names_the_operators_out_of_scope_of_its_nr_modes():
    import shutil
    import subprocess
    from pathlib import Path

    import pytest

    script = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/app.js').read_text(encoding='utf-8')
    helpers = script[script.index('function outOfScopePairs(nrModes) {'):script.index('globalThis.outOfScopePill = outOfScopePill;')]
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for the out of scope pill checks.')
    program = r"""
const created = [];
const document = {
  getElementById: () => ({textContent: JSON.stringify([{nr_mode: 'SA', operator: 'Three'}, {nr_mode: 'NSA', operator: 'X'}])}),
  createElement: () => { const element = {className: '', textContent: '', title: ''}; created.push(element); return element; },
};
""" + helpers + r"""
console.log(JSON.stringify({sa: outOfScopePairs('SA'), both: outOfScopePairs('NSA+SA'), list: outOfScopePairs(['nsa', 'SA']),
  none: outOfScopePairs(''), pill: outOfScopePill('SA', 'extra').textContent, className: created.at(-1).className,
  empty: outOfScopePill('LTE')}));
"""
    completed = subprocess.run([node, '-e', program], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        'sa': ['SA · Three'], 'both': ['SA · Three', 'NSA · X'], 'list': ['SA · Three', 'NSA · X'], 'none': [],
        'pill': 'Out of scope: SA · Three', 'className': 'out-of-scope-pill extra', 'empty': None}
