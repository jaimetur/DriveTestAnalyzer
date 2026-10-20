"""Scoring Excluded Calls: lists of calls (by JOIN_ID) left out of every scoring, the CDRs each one applies to, the calls
found in each CDR, and how they reach the scorings, their caches and the Scoring History."""
from __future__ import annotations

import io
import json
import random
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from src.modules import saved_filters, scoring, scoring_exclusions, scoring_history
from src.modules.repository import Repository, local_now_iso
from tests.scoring_fixtures import load_initial_scoring_configuration

OPERATORS = ('EE', 'Vodafone UK', 'Three UK')


def _rows(kind: str, campaign: str, prefix: str, seed: int = 5) -> pd.DataFrame:
    """CDR rows with a JOIN_ID: a Data test or a Voice call per row, and four Speech samples per call."""
    generator = random.Random(seed)
    rows = []
    for operator in OPERATORS:
        for index in range(30):
            join_id = f'0x{prefix}{operator[:2].upper()}{index:04d}'
            base = {'JOIN_ID': join_id, 'Operator': operator, 'Campaign': campaign, 'G_Level_1': 'Drive',
                    'G_Level_2': 'City', 'City': 'London', 'Region': 'South', 'Vendor': 'Nokia',
                    'Event_Start_Time': '2026-07-06 10:00:00'}
            if kind == 'voice':
                rows.append({**base, 'Session_Type': 'CALL',
                             'Call_Status': 'Dropped' if index < 6 else 'Completed',
                             'Call_Setup_Time': round(generator.uniform(1, 8), 2), 'Test_Status': 'Successful'})
            elif kind == 'speech':
                rows.extend({**base, 'Session_Type': 'CALL', 'LQ': 1.2 if index < 6 else 4.2} for _sample in range(4))
            else:
                rows.append({**base, 'Test_Name': 'FDFS DL', 'Test_Result': 'Failed' if index < 6 else 'Completed',
                             'Transfer_Duration': round(generator.uniform(1, 20), 2),
                             'Mean_Data_Rate': round(generator.uniform(1, 800), 2)})
    return pd.DataFrame(rows)


def _add_cdr(repository: Repository, tmp_path: Path, kind: str, campaign: str = '2026-Q3', prefix: str = 'A') -> int:
    name = f'NetCheck_UK_CDR_{kind.title()}_{campaign}.xlsx'
    frame = _rows(kind, campaign, prefix)
    source = tmp_path / name
    source.write_text(f'{kind} {campaign} source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'super')
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA',
                                      row_count=len(frame), column_count=len(frame.columns), processed_at=local_now_iso())
    repository.replace_cdr_catalogue(dataset_id, vendors=['Nokia'], regions=['South'], cities=['London'],
                                     campaigns=[campaign], operators=list(OPERATORS))
    return dataset_id


@pytest.fixture
def workspace(tmp_path):
    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'global.db')
    repository.initialize()
    repository.replace_scoring_configuration(load_initial_scoring_configuration())
    # The tests of the Data CDR have JOIN_IDs of their own; the Speech samples carry those of the Voice calls.
    ids = {kind: _add_cdr(repository, tmp_path, kind, prefix='D' if kind == 'data' else 'A')
           for kind in ('data', 'voice', 'speech')}
    ids['voice_q2'] = _add_cdr(repository, tmp_path, 'voice', '2026-Q2', prefix='B')
    ids['speech_q2'] = _add_cdr(repository, tmp_path, 'speech', '2026-Q2', prefix='B')
    return repository, ids


def _name(repository: Repository, dataset_id: int) -> str:
    return next(str(row['file_name']) for row in repository.list_datasets() if int(row['id']) == dataset_id)


def _calls(*ids: str) -> list[dict[str, str]]:
    return [{'join_id': value, 'reason': ''} for value in ids]


def _frames(repository: Repository, ids: list[int]) -> dict[str, pd.DataFrame]:
    sources, _campaigns, _fingerprint = saved_filters._source_snapshot(repository, ids)
    for source in sources:
        source['levels'] = ['Operator']
    return saved_filters._load_source_frames(repository, sources, lambda *args: None, scoring.load_input_columns, {})


def test_a_file_gives_each_join_id_once_with_its_reason():
    csv_file = 'Campaign;JOINT_ID;Reason\nQ3; 0xabc ;Test phone failure\nQ3;0xABC;again\nQ3;;\nQ3;0xdef;\n'.encode()
    read = scoring_exclusions.read_calls_file(csv_file, 'calls.csv')
    assert read['calls'] == [{'join_id': '0xabc', 'reason': 'Test phone failure'}, {'join_id': '0xdef', 'reason': ''}]
    assert (read['column'], read['repeated'], read['empty'], read['reasons']) == ('JOINT_ID', 1, 1, 1)
    # A single column without a header is a list of JOIN_IDs.
    assert [call['join_id'] for call in scoring_exclusions.read_calls_file(b'0x1\n0x2\n', 'ids.txt')['calls']] == ['0x1', '0x2']
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['Call Key', 'Comment'])
    sheet.append(['0x77', 'Wrong route'])
    content = io.BytesIO()
    workbook.save(content)
    assert scoring_exclusions.read_calls_file(content.getvalue(), 'calls.xlsx')['calls'] == [
        {'join_id': '0x77', 'reason': 'Wrong route'}]
    with pytest.raises(ValueError, match='JOIN_ID column'):
        scoring_exclusions.read_calls_file(b'Operator,City\nEE,London\n', 'calls.csv')
    with pytest.raises(ValueError, match='CSV, TXT'):
        scoring_exclusions.read_calls_file(b'0x1', 'calls.pdf')
    assert scoring_exclusions.read_calls_file(scoring_exclusions.template_csv(), 'template.csv')['calls']


def test_a_list_applies_to_every_cdr_or_to_its_cdrs_and_their_voice_or_speech_companion(workspace):
    repository, ids = workspace
    everywhere = scoring_exclusions.create_list(repository, name='Everywhere', calls=_calls('0xAEE0000'), username='super')
    voice_only = scoring_exclusions.create_list(repository, name='Q3 voice', calls=_calls('0xAEE0001'), username='super',
                                                cdrs=[_name(repository, ids['voice'])])
    scope = scoring_exclusions.load_scope(repository)
    lists = {item['name']: item for item in scope.lists}
    assert scope.targets(lists['Everywhere']) == sorted(ids.values())
    # The Speech CDR of the same campaign and NR Mode holds the samples of the same calls; Q2 and Data do not.
    assert scope.targets(lists['Q3 voice']) == sorted([ids['voice'], ids['speech']])
    assert everywhere['all_cdrs'] and not voice_only['all_cdrs']
    assert voice_only['companions'] == [_name(repository, ids['speech'])]


def test_the_rows_of_the_excluded_calls_are_left_out_of_the_scoring(workspace):
    repository, ids = workspace
    selected = [ids['data'], ids['voice'], ids['speech']]
    before = _frames(repository, selected)
    scoring_exclusions.create_list(repository, name='Drops', username='super',
                                   calls=_calls('0xaee0000', '0xAEE0001', '0xDEE0000', '0xdee0001', '0xmissing'))
    after = _frames(repository, selected)
    assert len(before['voice']) - len(after['voice']) == 2
    assert len(before['speech']) - len(after['speech']) == 8
    assert len(before['data']) - len(after['data']) == 2
    # Switched off, the list leaves nothing out.
    item = scoring_exclusions.list_lists(repository)[0]
    scoring_exclusions.update_list(repository, item['id'], 'super', enabled=False)
    assert len(_frames(repository, selected)['voice']) == len(before['voice'])


def test_the_calls_found_in_each_cdr_keep_the_scorings_of_the_cdrs_a_list_does_not_touch(workspace):
    repository, ids = workspace
    selected = [ids['voice'], ids['speech']]
    _sources, _campaigns, fingerprint = saved_filters._source_snapshot(repository, selected)
    _sources, _campaigns, q2_fingerprint = saved_filters._source_snapshot(repository, [ids['voice_q2']])
    scoring_exclusions.create_list(repository, name='Drops', calls=_calls('0xAEE0000'), username='super')
    # While the calls are looked for, every CDR the list applies to may change.
    assert saved_filters._source_snapshot(repository, selected)[2] != fingerprint
    assert scoring_exclusions.has_pending(repository)
    assert scoring_exclusions.match_pending(repository) == 5
    assert not scoring_exclusions.has_pending(repository)
    # Found in the Q3 Voice and Speech CDRs only: the Q2 CDR keeps its scorings.
    assert saved_filters._source_snapshot(repository, [ids['voice_q2']])[2] == q2_fingerprint
    assert saved_filters._source_snapshot(repository, selected)[2] != fingerprint
    item = scoring_exclusions.list_lists(repository)[0]
    found = {entry['id']: (entry['calls'], entry['rows']) for entry in item['targets']}
    assert found[ids['voice']] == (1, 1) and found[ids['speech']] == (1, 4) and found[ids['voice_q2']] == (0, 0)
    assert (item['found_calls'], item['found_rows'], item['pending_cdrs'], item['not_found']) == (1, 5, 0, 0)
    # Processing a CDR again looks for the calls in it again.
    repository.update_dataset_profile(ids['voice'], processed_at=local_now_iso() + 'x')
    assert scoring_exclusions.match_pending(repository) == 1


def test_a_saved_filter_leaves_the_calls_out_and_says_so(workspace):
    repository, ids = workspace
    selected = [ids['data'], ids['voice'], ids['speech']]
    plain, _cached = saved_filters.save_saved_filter(repository, selected, ['Operator'], 'NSA')
    plain = saved_filters.calculate_saved_filter(repository, plain['id'])
    scoring_exclusions.create_list(repository, name='Drops of EE', username='super',
                                   calls=_calls(*(f'0x{kind}EE{index:04d}' for kind in 'AD' for index in range(6))))
    job, cached = saved_filters.save_saved_filter(repository, selected, ['Operator'], 'NSA')
    assert not cached
    finished = saved_filters.calculate_saved_filter(repository, job['id'])
    result = finished['result']
    # The calls are still being looked for in the CDRs: how many is not known yet, but their rows are left out.
    assert result['excluded_calls']['calls'] == 0 and result['excluded_calls']['pending_cdrs'] == 3
    assert 'Excluded Calls: the calls of the list “Drops of EE” are left out of this scoring; they are still being found in 3 of its CDRs, so how many is not known yet.' in result['warnings']

    def success_ratio(payload):
        return next(row['value'] for row in payload['scoring'] if row['operator'] == 'EE' and row['kpi_code'] == 'K1')
    # EE loses its dropped calls: its call success ratio rises.
    assert success_ratio(result) > success_ratio(plain['result'])
    # Once the calls are found, the Scoring History indexes the CDRs without them and gives the same scores.
    scoring_history.sync_history(repository)
    assert not scoring_history.history_gap(repository, selected, ['Operator'], result['configuration'])
    job, _cached = saved_filters.save_saved_filter(repository, selected, ['Operator'], 'NSA')
    from_history = saved_filters.calculate_saved_filter(repository, job['id'])['result']
    assert from_history['source'] == 'history'
    assert success_ratio(from_history) == pytest.approx(success_ratio(result))
    assert any(warning.startswith('Excluded Calls: 12 calls (36 CDR rows)') for warning in from_history['warnings'])


def test_the_history_waits_for_the_calls_to_be_found(workspace):
    repository, ids = workspace
    configuration = repository.get_scoring_profile()['configuration']
    scoring_history.sync_history(repository)
    selected = [ids['voice'], ids['speech']]
    assert not scoring_history.history_gap(repository, selected, ['Operator'], configuration)
    scoring_exclusions.create_list(repository, name='Drops', calls=_calls('0xAEE0000'), username='super')
    assert scoring_history.history_gap(repository, selected, ['Operator'], configuration) == (
        'the Excluded Calls are still being found in 2 of its 2 CDRs')
    changed, _metrics = scoring_history.history_changes(repository)
    assert changed == []
    # The sync finds the calls first, then indexes the CDRs that hold them (and only those).
    assert scoring_history.sync_history(repository) == {'indexed': 2}
    assert not scoring_history.history_gap(repository, selected, ['Operator'], configuration)


def test_lists_travel_as_a_document_with_their_cdrs_by_name(workspace, tmp_path):
    repository, ids = workspace
    scoring_exclusions.create_list(repository, name='Q3 voice', username='super', reason='Wrong route',
                                   calls=[{'join_id': '0xAEE0001', 'reason': 'Phone reset'}],
                                   cdrs=[_name(repository, ids['voice'])], enabled=False)
    document = scoring_exclusions.export_document(repository)
    payload = json.loads(document)
    assert payload['format'] == 'drivetest-analyzer-scoring-excluded-calls'
    assert payload['lists'][0]['calls'] == [['0xAEE0001', 'Phone reset']]
    other = Repository(tmp_path / 'other.db', global_db_path=tmp_path / 'global.db')
    other.initialize()
    assert scoring_exclusions.import_document(other, document, 'admin') == 1
    # Importing it again replaces the list of the same name.
    assert scoring_exclusions.import_document(other, document, 'admin') == 1
    [item] = scoring_exclusions.list_lists(other)
    assert (item['name'], item['reason'], item['enabled'], item['cdrs'], item['call_count']) == (
        'Q3 voice', 'Wrong route', False, [_name(repository, ids['voice'])], 1)
    assert item['created_by'] == 'super' and item['updated_by'] == 'admin'
    assert item['missing_cdrs'] == [_name(repository, ids['voice'])]
    with pytest.raises(ValueError, match='not a DriveTest Analyzer Scoring Excluded Calls'):
        scoring_exclusions.import_document(other, b'{"format": "other"}', 'admin')


def _login_workspace(client, tmp_path):
    import src.DriveTestAnalyzer as app_module

    response = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert response.status_code == 303
    workspace = app_module.active_workspace
    repository = Repository(workspace.database_path, app_module.repository.global_db_path,
                            app_module.workspace_registry.registry_path)
    repository.initialize()
    ids = {kind: _add_cdr(repository, tmp_path, kind) for kind in ('voice', 'speech')}
    return app_module, workspace, repository, ids


def test_the_panel_imports_changes_and_deletes_lists_and_records_them_in_app_events(client, tmp_path, monkeypatch):
    app_module, _workspace, repository, ids = _login_workspace(client, tmp_path)
    queued = []
    monkeypatch.setattr(app_module, 'queue_scoring_history', lambda task_repository: queued.append(task_repository.db_path))
    voice, speech = _name(repository, ids['voice']), _name(repository, ids['speech'])
    page = client.get('/scoring').text
    assert 'data-scoring-exclusions' in page and 'js/scoring_exclusions.js' in page and '<h2>Excluded Calls</h2>' in page
    state = client.get('/api/scoring/excluded-calls').json()
    assert state['lists'] == [] and state['can_edit'] and {cdr['name'] for cdr in state['cdrs']} == {voice, speech}
    content = b'JOIN_ID;Reason\n0xAEE0000;Phone reset\n0xaee0000;\n0xAEE0001;\n'
    check = client.post('/api/scoring/excluded-calls/check', files={'file': ('Q3 drops.csv', content, 'text/csv')}).json()
    assert (check['calls'], check['repeated'], check['reasons'], check['column']) == (2, 1, 1, 'JOIN_ID')
    response = client.post('/api/scoring/excluded-calls', files={'file': ('Q3 drops.csv', content, 'text/csv')},
                           data={'name': '', 'reason': 'Faulty test phone', 'cdrs': [voice]})
    assert response.status_code == 200, response.text
    item = response.json()['imported']
    assert (item['name'], item['cdrs'], item['companions'], item['call_count']) == ('Q3 drops', [voice], [speech], 2)
    # The calls are looked for in the background, before the Scoring History indexes the CDRs.
    assert queued and item['pending_cdrs'] == 2
    duplicate = client.post('/api/scoring/excluded-calls', files={'file': ('Q3 drops.csv', content, 'text/csv')})
    assert duplicate.status_code == 400 and 'already exists' in duplicate.json()['detail']
    assert client.post('/api/scoring/excluded-calls/check', files={'file': ('x.csv', b'A,B\n1,2\n', 'text/csv')}).status_code == 400
    response = client.put(f"/api/scoring/excluded-calls/{item['id']}", json={'enabled': False})
    assert response.status_code == 200 and response.json()['lists'][0]['enabled'] is False
    download = client.get(f"/api/scoring/excluded-calls/{item['id']}/calls")
    assert download.text.splitlines() == ['JOIN_ID,Reason', '0xAEE0000,Phone reset', '0xAEE0001,']
    # Database Management, in Super Admin, lists the tables.
    assert client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False).status_code == 303
    assert 'Scoring Exclusion Lists' in client.get('/super-admin').text
    response = client.delete(f"/api/scoring/excluded-calls/{item['id']}")
    assert response.status_code == 200 and response.json()['lists'] == []
    assert client.delete(f"/api/scoring/excluded-calls/{item['id']}").status_code == 404
    events = {row['action']: json.loads(row['details']) for row in repository.list_logs(limit=20)}
    assert events['import_scoring_excluded_calls']['list'] == 'Q3 drops'
    assert events['import_scoring_excluded_calls']['repeated_ids_skipped'] == 1
    assert events['update_scoring_excluded_calls']['changes'] == {'enabled': [True, False]}
    assert events['download_scoring_excluded_calls']['calls'] == 2
    assert events['delete_scoring_excluded_calls']['calls'] == 2
    # Only those who edit the Scoring Methodologies change the lists.
    app_module.repository.create_user('viewer1', 'secret123', 'user-viewer')
    client.post('/logout')
    client.post('/login', data={'username': 'viewer1', 'password': 'secret123'}, follow_redirects=False)
    assert client.post('/api/scoring/excluded-calls/check', files={'file': ('a.csv', content, 'text/csv')}).status_code == 403


def test_the_lists_travel_with_import_export_transfers_and_backups(client, tmp_path, monkeypatch):
    import zipfile

    app_module, workspace, repository, ids = _login_workspace(client, tmp_path)
    monkeypatch.setattr(app_module, 'queue_scoring_history', lambda task_repository: None)
    scoring_exclusions.create_list(repository, name='Q3 voice', username='admin', reason='Wrong route',
                                   calls=_calls('0xAEE0001'), cdrs=[_name(repository, ids['voice'])])
    assert 'scoring-excluded-calls' in app_module.WORKSPACE_ELEMENT_EXPORT_TARGETS
    assert app_module.archive_workspace_components_for_target('scoring-excluded-calls') == ['scoring_excluded_calls']
    assert 'scoring_excluded_calls' in app_module.full_workspace_archive_components()
    assert 'Scoring Excluded Calls (from active workspace)' in client.get('/admin').text
    exported = client.get('/admin/import-export/export?export_target=scoring-excluded-calls')
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        document = json.loads(archive.read(manifest['archive_path']))
    assert manifest['kind'] == 'scoring-excluded-calls'
    assert [entry['name'] for entry in document['lists']] == ['Q3 voice']

    def forget() -> None:
        for item in scoring_exclusions.list_lists(repository):
            scoring_exclusions.delete_list(repository, item['id'])
        assert scoring_exclusions.list_lists(repository) == []

    def restored() -> dict:
        [item] = scoring_exclusions.list_lists(repository)
        return {key: item[key] for key in ('name', 'reason', 'cdrs', 'call_count')}
    expected = {'name': 'Q3 voice', 'reason': 'Wrong route', 'cdrs': [_name(repository, ids['voice'])], 'call_count': 1}
    forget()
    package = tmp_path / 'scoring-excluded-calls.zip'
    package.write_bytes(exported.content)
    message = app_module._apply_import_archive(package, app_module.read_import_manifest(package),
                                               destination_workspace_ids=[workspace.id])
    assert message == 'Imported 1 lists of Scoring Excluded Calls into 1 workspaces.'
    assert restored() == expected
    backup_path = app_module.create_recurring_database_backup({
        'components': ['scoring_excluded_calls'], 'workspace_ids': [workspace.id], 'backup_path': str(tmp_path), 'max_backups': 5})
    assert app_module._backup_archive_components(backup_path) == ['scoring_excluded_calls']
    forget()
    app_module.restore_database_backup(backup_path, ['scoring_excluded_calls'])
    assert restored() == expected
