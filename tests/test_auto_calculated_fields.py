"""The Auto-calculated Fields editor: its operators, rules kept as written, one field saved, checked and tried at a time,
and materialization against what the CDR tables hold."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules.cdr_reporting import (
    calculated_dimension_editor_json, calculated_dimension_preview, calculated_dimensions_json,
    materialize_calculated_dimensions, parse_calculated_dimensions,
)
from src.modules.repository import Repository, local_now_iso

NR_MODE_FROM_RAT = {
    'name': 'NR_Mode_from_RAT', 'sources': ['cdr-data', 'cdr-voice', 'cdr-speech'], 'default': 'Others',
    'default_from': '', 'expression': '',
    'rules': [
        {'when': "[RAT] OR [RAT_A] CONTAINS ('NR SA', NE-DC, VoNR, EPSFB, '5G NR') OR [RAT] OR [RAT_A] MATCHES '(^|/)NR(/|$)'", 'value': 'SA'},
        {'when': '[RAT] OR [RAT_A] CONTAINS (EN-DC, LTE-5GNR)', 'value': 'NSA'},
    ],
}
RATS = ['EN-DC', 'NR SA/EN-DC', 'NR/LTE', 'LTE-5GNR/LTE', 'LTE', None, 'Unknown', 'VoNR/VoLTE', 'NE-DC/LTE', 'EPSFB', 'Unreachable']
EXPECTED = ['NSA', 'SA', 'SA', 'NSA', 'Others', 'Others', 'Others', 'SA', 'SA', 'SA', 'Others']


def login(client) -> None:
    response = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert response.status_code == 303


def add_cdr(tmp_path: Path, name: str, kind: str, rows: pd.DataFrame) -> int:
    source = tmp_path / name
    source.write_text('test source', encoding='utf-8')
    dataset_id, _created = core.repository.add_dataset(name, str(source), 'admin')
    core.repository.replace_dataset_rows(dataset_id, rows)
    core.repository.update_dataset_profile(
        dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='SA',
        row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso(),
    )
    return dataset_id


def test_new_operators_classify_each_sample_by_its_rat() -> None:
    shipped = json.loads((Path(core.PROJECT_ROOT) / 'assets' / 'autocalculated-fields' / 'default-autocalculated-fields.json').read_text())
    assert next(item for item in shipped if item['name'] == 'NR_Mode_from_RAT') == NR_MODE_FROM_RAT
    dimensions = parse_calculated_dimensions([NR_MODE_FROM_RAT])
    frame = materialize_calculated_dimensions(pd.DataFrame({'RAT': RATS}), dimensions, 'cdr-voice')

    assert frame['NR_Mode_from_RAT'].tolist() == EXPECTED
    edges = parse_calculated_dimensions([{
        'name': 'Edge', 'sources': ['cdr-data'], 'rules': [
            {'when': '[RAT] IS EMPTY', 'value': 'Empty'},
            {'when': '[RAT] STARTS WITH (nr, ne)', 'value': 'Starts'},
            {'when': "[RAT] ENDS WITH '/lte'", 'value': 'Ends'},
            {'when': "[RAT] NOT MATCHES '^(EN|LTE)'", 'value': 'Other'},
        ],
    }])
    values = materialize_calculated_dimensions(
        pd.DataFrame({'RAT': [None, ' ', 'NR SA', 'EN-DC/LTE', 'Unknown', 'LTE']}), edges, 'cdr-data',
    )['Edge'].tolist()
    assert values[:5] == ['Empty', 'Empty', 'Starts', 'Ends', 'Other']
    assert pd.isna(values[5])


def test_shipped_rat_group_keeps_each_technology_and_groups_its_combinations() -> None:
    shipped = json.loads((Path(core.PROJECT_ROOT) / 'assets' / 'autocalculated-fields' / 'default-autocalculated-fields.json').read_text())
    dimensions = parse_calculated_dimensions(shipped)
    expected = {
        'EN-DC': 'EN-DC', 'LTE-5GNR': 'EN-DC', 'EN-DC/LTE': 'ENDC Mixed', 'EN-DC/LTE/UMTS': 'ENDC Mixed', 'LTE-5GNR/LTE': 'ENDC Mixed',
        'NR SA': 'NR SA', 'NE-DC': 'NR SA', 'NR': 'NR SA', 'NR SA/GSM': 'NR SA Mixed', 'NR/LTE': 'NR SA Mixed', 'LTE/NR/GSM': 'NR SA Mixed',
        'NR SA/EN-DC/LTE': 'NR SA Mixed', 'VoNR': 'VoNR', 'VoNR/VoLTE - ISHO': 'VoNR Mixed', 'EPSFB': 'EPSFB', 'VoLTE': 'VoLTE',
        'VoLTE(F)/CSFB/GSM': 'VoLTE Mixed', 'CSFB/UMTS': 'CSFB', 'LTE': 'LTE', 'LTE/GSM': 'LTE Mixed', 'UMTS/GSM': '2G/3G',
        'Partially_No_Service': 'No Service', 'Unknown': 'Unknown',
    }
    frame = materialize_calculated_dimensions(pd.DataFrame({'RAT': list(expected)}), dimensions, 'cdr-speech')

    assert dict(zip(frame['RAT'], frame['RAT_Group'])) == expected
    assert '7_Cities' not in {item['name'] for item in shipped}


def test_rules_are_kept_as_written_and_read_back_the_same() -> None:
    dimensions = parse_calculated_dimensions([{
        'name': 'Status', 'sources': ['cdr-data'], 'rules': [
            {'when': "([Test_Result] = 'Visible Completed' OR [Test_Result] IN (Completed, 'Cut off')) AND [Score] >= 3", 'value': 'Good'},
            {'when': "[Pattern] MATCHES '\\d+\\s'", 'value': 'Digits'},
        ],
    }])
    saved = calculated_dimensions_json(dimensions)[0]

    # One rule stays one rule: its OR is not split into two.
    assert [rule['when'] for rule in saved['rules']] == [
        "([Test_Result] = 'Visible Completed' OR [Test_Result] IN (Completed, 'Cut off')) AND [Score] >= 3",
        "[Pattern] MATCHES '\\\\d+\\\\s'",
    ]
    assert len(dimensions[0].rules) == 3
    assert parse_calculated_dimensions([saved]) == dimensions
    frame = materialize_calculated_dimensions(pd.DataFrame({
        'Test_Result': ['Visible Completed', 'cut off', 'Completed', 'Failed'], 'Score': [3, 5, 1, 9],
        'Pattern': ['', '', '', '12 '],
    }), dimensions, 'cdr-data')
    assert frame['Status'].fillna('').tolist() == ['Good', 'Good', '', 'Digits']
    editor = calculated_dimension_editor_json(dimensions[0])
    assert editor['rules'][0]['join'] is None
    assert editor['rules'][1] | {'join': 'AND'} == editor['rules'][1]
    assert editor['reads'] == ['Pattern', 'Score', 'Test_Result']


def test_preview_counts_values_and_the_rows_each_rule_takes() -> None:
    dimensions = parse_calculated_dimensions([NR_MODE_FROM_RAT])
    preview = calculated_dimension_preview(pd.DataFrame({'RAT': RATS}), dimensions, 'NR_Mode_from_RAT', 'cdr-voice')

    assert preview['rows'] == len(RATS)
    assert {item['value']: item['count'] for item in preview['values']} == {'SA': 5, 'NSA': 2, 'Others': 4}
    assert [rule['count'] for rule in preview['rules']] == [5, 2]
    assert preview['unmatched'] == 4 and preview['from_default'] == 4 and preview['missing'] == []
    # Why no rule takes them: the values they have in the field the rules read.
    (why,) = preview['unmatched_fields']
    assert why['field'] == 'RAT' and why['distinct'] == 4
    assert sorted((item['value'], item['count']) for item in why['values']) == [('', 1), ('LTE', 1), ('Unknown', 1), ('Unreachable', 1)]


def _cdr_table(tmp_path: Path) -> Repository:
    repository = Repository(tmp_path / 'auto-fields.db')
    repository.initialize()
    with repository.connection() as connection:
        connection.execute('CREATE TABLE dataset_rows_1 (RAT TEXT, Score TEXT)')
        connection.executemany('INSERT INTO dataset_rows_1 VALUES (?, ?)', [(rat, '1') for rat in RATS])
    return repository


def test_sql_materialization_gives_the_values_of_the_rows_materialization(tmp_path: Path) -> None:
    repository = _cdr_table(tmp_path)
    dimensions = parse_calculated_dimensions([NR_MODE_FROM_RAT])

    assert core._incremental_auto_field_table_update(repository, 'dataset_rows_1', 'cdr-data', (), dimensions, {}) is True
    with repository.connection() as connection:
        values = [row[0] for row in connection.execute('SELECT NR_Mode_from_RAT FROM dataset_rows_1 ORDER BY rowid')]
    assert values == EXPECTED
    # The table holds the field as it is: it is left alone.
    assert core._incremental_auto_field_table_update(repository, 'dataset_rows_1', 'cdr-data', dimensions, dimensions, {}) is False


def test_a_field_reading_a_changed_field_is_worked_out_again(tmp_path: Path) -> None:
    repository = _cdr_table(tmp_path)
    first = {'name': 'Family', 'sources': ['cdr-data'], 'rules': [{'when': '[RAT] CONTAINS NR', 'value': '5G'}], 'default': '4G'}
    reader = {'name': 'Label', 'sources': ['cdr-data'], 'rules': [{'when': '[Family] = 5G', 'value': 'New'}], 'default': 'Old'}
    previous = parse_calculated_dimensions([first, reader])
    core._incremental_auto_field_table_update(repository, 'dataset_rows_1', 'cdr-data', (), previous, {})
    current = parse_calculated_dimensions([{**first, 'rules': [{'when': '[RAT] CONTAINS LTE', 'value': '5G'}]}, reader])

    assert core.calculated_dimension_changes(previous, current) == {'family', 'label'}
    core._incremental_auto_field_table_update(repository, 'dataset_rows_1', 'cdr-data', previous, current, {})
    with repository.connection() as connection:
        rows = connection.execute('SELECT RAT, Label FROM dataset_rows_1 ORDER BY rowid').fetchall()
    assert [row['Label'] for row in rows if row['RAT'] == 'NR/LTE'] == ['New']
    assert [row['Label'] for row in rows if row['RAT'] == 'EN-DC'] == ['Old']


def test_combined_tables_keep_the_columns_of_the_application(tmp_path: Path) -> None:
    repository = Repository(tmp_path / 'combined.db')
    repository.initialize()
    with repository.connection() as connection:
        connection.execute('CREATE TABLE reporting_rows_data (dataset_id INTEGER, RAT TEXT, NR_Mode TEXT)')
        connection.execute("INSERT INTO reporting_rows_data VALUES (1, 'LTE', 'SA')")
    previous = parse_calculated_dimensions([{'name': 'NR_Mode', 'sources': ['cdr-data'], 'default': 'Others'}])

    core._apply_auto_field_table_update(repository, 'reporting_rows_data', 'cdr-data', previous, (), {})
    core._apply_auto_field_table_update(repository, 'reporting_rows_data', 'cdr-data', (), previous, {})
    with repository.connection() as connection:
        assert connection.execute('SELECT NR_Mode FROM reporting_rows_data').fetchone()[0] == 'SA'


def test_save_check_and_try_one_field(client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    login(client)
    # New workspaces already have the shipped NR_Mode_from_RAT: this one is another field like it.
    field = {**NR_MODE_FROM_RAT, 'name': 'Per Sample Mode'}
    add_cdr(tmp_path, 'voice.csv', 'voice', pd.DataFrame({'Operator': ['EE'] * len(RATS), 'RAT': RATS, 'Call_Setup_Time': [1.5] * len(RATS)}))
    jobs = []

    def queue(*args, before_submit=None, **_kwargs):
        job = {'id': 'job-1', 'status': 'queued', 'affected_sources': ['cdr-voice']}
        jobs.append(args)
        if before_submit:
            before_submit(job)
        return job

    monkeypatch.setattr(core, 'start_auto_calculated_field_job', queue)

    editor = client.get('/api/workspace/auto-calculated-fields').json()
    assert 'RAT' in editor['columns']['cdr-voice'] and editor['can_edit'] is True
    assert {item['key'] for item in editor['operators']} >= {'MATCHES', 'IS EMPTY', 'STARTS WITH'}

    reserved = client.post('/api/workspace/auto-calculated-fields/check', json={'field': {**field, 'name': 'NR_Mode'}}).json()
    assert reserved['ok'] is False and 'NR Mode of the CDR' in reserved['errors'][0]
    clash = client.post('/api/workspace/auto-calculated-fields/check', json={'field': {**field, 'name': 'call setup time'}}).json()
    assert clash['ok'] is False and 'already have a field' in clash['errors'][0]
    broken = client.post('/api/workspace/auto-calculated-fields/check', json={'field': {**field, 'rules': [{'when': '[RAT] MATCHES (', 'value': 'X'}]}}).json()
    assert broken['ok'] is False and broken['errors']
    checked = client.post('/api/workspace/auto-calculated-fields/check', json={'field': field}).json()
    assert checked['ok'] is True and checked['field']['rules'][0]['join'] == 'OR'
    assert checked['field']['rules'][0]['conditions'][0]['values'][0] == 'NR SA'

    tried = client.post('/api/workspace/auto-calculated-fields/preview', json={'field': field}).json()
    voice = tried['sources']['cdr-voice']
    assert voice['rows'] == len(RATS) and voice['total_rows'] == len(RATS)
    assert {item['value']: item['count'] for item in voice['values']} == {'SA': 5, 'NSA': 2, 'Others': 4}
    values = client.post('/api/workspace/auto-calculated-fields/values', json={'fields': ['RAT'], 'sources': ['cdr-voice']}).json()
    assert {item['value'] for item in values['values']} >= {'EN-DC', 'NR/LTE'}

    saved = client.post('/api/workspace/auto-calculated-fields/save', json={'field': field})
    assert saved.status_code == 200, saved.text
    assert saved.json()['field']['name'] == 'Per Sample Mode' and saved.json()['materialization_job'] == 'job-1'
    assert any(item.name == 'Per Sample Mode' for item in core.load_workspace_calculated_dimensions())
    again = client.post('/api/workspace/auto-calculated-fields/save', json={'field': field})
    assert again.status_code == 400 and 'already a field' in again.json()['detail']

    reader = {'name': 'Is SA', 'sources': ['cdr-voice'], 'default': 'No', 'rules': [{'when': '[Per Sample Mode] = SA', 'value': 'Yes'}]}
    assert client.post('/api/workspace/auto-calculated-fields/save', json={'field': reader}).status_code == 200
    renamed = client.post('/api/workspace/auto-calculated-fields/save', json={
        'field': {**field, 'name': 'Sample 5G Mode'}, 'original_name': 'Per Sample Mode'})
    assert renamed.status_code == 200, renamed.text
    # No template uses it: none is saved again (their filters keep their text as it is).
    assert renamed.json()['renamed_templates'] == 0
    fields = {item['name']: item for item in renamed.json()['fields']}
    assert fields['Is SA']['rules'][0]['when'] == '[Sample 5G Mode] = SA'

    blocked = client.post('/api/workspace/auto-calculated-fields/delete', json={'name': 'Sample 5G Mode'})
    assert blocked.status_code == 400 and 'Is SA' in blocked.json()['detail']
    names = [item['name'] for item in renamed.json()['fields']]
    wrong = client.post('/api/workspace/auto-calculated-fields/reorder', json={'names': [*names[:-2], names[-1], names[-2]]})
    assert wrong.status_code == 400 and 'must stay below' in wrong.json()['detail']
    assert client.post('/api/workspace/auto-calculated-fields/delete', json={'name': 'Is SA'}).status_code == 200
    assert 'Is SA' not in {item.name for item in core.load_workspace_calculated_dimensions()}
    actions = [row['action'] for row in core.repository.list_logs(limit=50)]
    assert {'save_auto_calculated_field', 'delete_auto_calculated_field'} <= set(actions)


def test_a_save_that_changes_no_cdr_leaves_nothing_pending(client) -> None:
    login(client)
    current = core.load_workspace_calculated_dimensions()
    core.record_materialized_calculated_dimensions(core.repository, current)
    names = [item.name for item in current]

    response = client.post('/api/workspace/auto-calculated-fields/reorder', json={'names': list(reversed(names))})

    assert response.status_code == 200, response.text
    assert response.json()['notice'].startswith('Saved. The CDR tables already hold')
    assert core.repository.get_workspace_state('calculated_dimensions_need_materialization') == '0'


def test_fields_saved_while_the_tables_are_updated_stay_pending(tmp_path: Path) -> None:
    repository = Repository(tmp_path / 'pending.db')
    repository.initialize()
    worked_out = parse_calculated_dimensions([NR_MODE_FROM_RAT])
    repository.replace_calculated_dimensions(calculated_dimensions_json(worked_out))

    core.materialize_workspace_auto_fields_incrementally((), worked_out, {}, repository, {'cdr-voice'})
    assert repository.get_workspace_state('calculated_dimensions_need_materialization') == '0'

    # Saved meanwhile: the pass that worked out the former definitions leaves the new ones pending.
    repository.replace_calculated_dimensions(calculated_dimensions_json(parse_calculated_dimensions([{**NR_MODE_FROM_RAT, 'default': 'Other RAT'}])))
    core.materialize_workspace_auto_fields_incrementally((), worked_out, {}, repository, {'cdr-voice'})
    assert repository.get_workspace_state('calculated_dimensions_need_materialization') == '1'
