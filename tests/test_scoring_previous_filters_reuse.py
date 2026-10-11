"""Previous Filters: reused selections that travel with the Scoring Configuration, find their CDRs by file in
another workspace, tell when newer CDRs replace theirs, and keep their result when their CDRs are gone."""
from __future__ import annotations

from pathlib import Path

import src.DriveTestAnalyzer as app_module
from src.modules import scoring_previous_filters
from src.modules.repository import Repository, local_now_iso
from tests.scoring_fixtures import load_initial_scoring_configuration
from tests.test_scoring_history import _rows


def _workspace(tmp_path: Path, name: str) -> Repository:
    folder = tmp_path / name
    folder.mkdir()
    repository = Repository(folder / 'workspace.db', global_db_path=tmp_path / 'global.db')
    repository.initialize()
    repository.replace_scoring_configuration(load_initial_scoring_configuration())
    return repository


def _add_cdr(repository: Repository, folder: Path, kind: str, name: str, content: str, stage: str = 'final') -> int:
    frame = _rows(kind)
    source = folder / name
    source.write_text(content, encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'super')
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA',
                                      cdr_stage=stage, row_count=len(frame), column_count=len(frame.columns),
                                      processed_at=local_now_iso())
    return dataset_id


def _three_cdrs(repository: Repository, folder: Path, prefix: str = '') -> list[int]:
    return [_add_cdr(repository, folder, kind, f'{prefix}NetCheck_UK_CDR_{kind.title()}_2026_Q3.xlsx', f'{kind} file')
            for kind in ('data', 'voice', 'speech')]


def test_previous_filters_travel_without_results_and_find_their_cdrs_by_file(tmp_path):
    source = _workspace(tmp_path, 'source')
    ids = _three_cdrs(source, tmp_path / 'source')
    used, _ = scoring_previous_filters.save_previous_filter(
        source, ids, ['Operator', 'Region'], 'NSA', context_filters={'Region': ['North']})
    scoring_previous_filters.calculate_previous_filter(source, used['id'])
    scoring_previous_filters.update_previous_filter(source, used['id'], name='North by region', pinned=True)
    document = scoring_previous_filters.previous_filters_document(source)
    [entry] = document['previous_filters']
    assert entry['name'] == 'North by region' and entry['pinned'] and 'result' not in entry
    assert {cdr['kind'] for cdr in entry['cdrs']} == {'data', 'voice', 'speech'}
    assert all(len(cdr['sha256']) == 64 for cdr in entry['cdrs'])

    # In another workspace the filters wait for their CDRs…
    target = _workspace(tmp_path, 'target')
    assert scoring_previous_filters.import_previous_filters(target, document) == 1
    [waiting] = scoring_previous_filters.list_previous_filters(target)
    assert waiting['dataset_ids'] == [] and len(waiting['missing_cdrs']) == 3 and waiting['status'] == 'saved'
    assert scoring_previous_filters.refresh_previous_filter(target, waiting['id'])[1].startswith(
        'The CDRs of these filters are not in this workspace')
    # …found by the SHA-256 of their files, whatever their names and ids there.
    _add_cdr(target, tmp_path / 'target', 'voice', 'Unrelated voice.xlsx', 'another voice file')
    target_ids = _three_cdrs(target, tmp_path / 'target', prefix='Renamed ')
    [resolved] = scoring_previous_filters.list_previous_filters(target)
    assert sorted(resolved['dataset_ids']) == sorted(target_ids)
    assert resolved['name'] == 'North by region' and resolved['pinned'] and resolved['missing_cdrs'] == []
    # Opened, it is calculated with the CDRs and methodology of this workspace.
    assert scoring_previous_filters.refresh_previous_filter(target, resolved['id']) == (True, '')
    calculated = scoring_previous_filters.calculate_previous_filter(target, resolved['id'])
    assert calculated['status'] == 'completed' and calculated['result']['scoring']
    # Imported again, it joins the Previous Filter it already is.
    scoring_previous_filters.import_previous_filters(target, document)
    assert [item['id'] for item in scoring_previous_filters.list_previous_filters(target)] == [resolved['id']]
    # The same selection made here is that Previous Filter.
    same, reused = scoring_previous_filters.save_previous_filter(
        target, target_ids, ['Operator', 'Region'], 'NSA', context_filters={'Region': ['North']})
    assert same['id'] == resolved['id'] and reused


def test_a_final_cdr_replacing_a_daily_one_is_offered_and_deleted_cdrs_keep_the_saved_result(tmp_path):
    repository = _workspace(tmp_path, 'workspace')
    folder = tmp_path / 'workspace'
    data_id = _add_cdr(repository, folder, 'data', 'UK_Data_CDR_20260715.xlsx', 'daily data', stage='daily')
    voice_id = _add_cdr(repository, folder, 'voice', 'UK_Voice_Final.xlsx', 'voice file')
    speech_id = _add_cdr(repository, folder, 'speech', 'UK_Speech_Final.xlsx', 'speech file')
    previous_filter, _ = scoring_previous_filters.save_previous_filter(repository, [data_id, voice_id, speech_id],
                                                                       ['Operator'], 'NSA')
    scoring_previous_filters.calculate_previous_filter(repository, previous_filter['id'])
    assert scoring_previous_filters.list_previous_filters(repository)[0]['newer_cdrs'] == []

    final_id = _add_cdr(repository, folder, 'data', 'UK_Data_CDR_Final.xlsx', 'final data')
    [listed] = scoring_previous_filters.list_previous_filters(repository)
    assert listed['newer_cdrs'] == [{'id': data_id, 'name': 'UK_Data_CDR_20260715.xlsx', 'replaced_by': final_id,
                                     'replaced_by_name': 'UK_Data_CDR_Final.xlsx'}]

    # Without one of its CDRs, the saved result is still shown, saying why it is not calculated again.
    repository.delete_dataset(voice_id)
    queued, unavailable = scoring_previous_filters.refresh_previous_filter(repository, previous_filter['id'])
    assert not queued and 'no longer exist' in unavailable
    kept = scoring_previous_filters.get_previous_filter(repository, previous_filter['id'], include_result=True)
    assert kept['status'] == 'completed' and kept['result']['scoring']


def test_previous_filters_travel_with_the_scoring_configuration_backup(client, tmp_path: Path) -> None:
    response = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert response.status_code == 303
    workspace = app_module.active_workspace
    repository = Repository(workspace.database_path, global_db_path=app_module.repository.db_path,
                            workspace_registry_db_path=app_module.workspace_registry.registry_path)
    repository.initialize()
    repository.replace_scoring_configuration(load_initial_scoring_configuration())
    folder = tmp_path / 'cdrs'
    folder.mkdir()
    ids = _three_cdrs(repository, folder)
    used, _ = scoring_previous_filters.save_previous_filter(repository, ids, ['Operator'], 'NSA')
    scoring_previous_filters.update_previous_filter(repository, used['id'], name='Weekly view')
    backup_path = app_module.create_recurring_database_backup({
        'components': ['scoring_configuration'], 'workspace_ids': [workspace.id],
        'backup_path': str(tmp_path), 'max_backups': 5,
    })
    scoring_previous_filters.delete_previous_filter(repository, used['id'])
    app_module.restore_database_backup(backup_path, ['scoring_configuration'])
    [restored] = scoring_previous_filters.list_previous_filters(repository)
    assert restored['name'] == 'Weekly view' and sorted(restored['dataset_ids']) == sorted(ids)
    # Packages created before Previous Filters existed leave the current ones.
    app_module._restore_workspace_scoring_previous_filters(workspace, None)
    assert len(scoring_previous_filters.list_previous_filters(repository)) == 1
