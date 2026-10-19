"""Saved Filters: reused selections that travel as Favourites Filters, find their CDRs by file in
another workspace, tell when newer CDRs replace theirs, and keep their result when their CDRs are gone."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.DriveTestAnalyzer as app_module
from src.modules import saved_filters
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


def test_saved_filters_travel_without_results_and_find_their_cdrs_by_file(tmp_path):
    source = _workspace(tmp_path, 'source')
    ids = _three_cdrs(source, tmp_path / 'source')
    used, _ = saved_filters.save_saved_filter(
        source, ids, ['Operator', 'Region'], 'NSA', context_filters={'Region': ['North']})
    saved_filters.calculate_saved_filter(source, used['id'])
    saved_filters.update_saved_filter(source, used['id'], name='North by region', pinned=True)
    document = saved_filters.saved_filters_document(source)
    [entry] = document['saved_filters']
    assert entry['name'] == 'North by region' and entry['pinned'] and 'result' not in entry
    assert {cdr['kind'] for cdr in entry['cdrs']} == {'data', 'voice', 'speech'}
    assert all(len(cdr['sha256']) == 64 for cdr in entry['cdrs'])

    # In another workspace the filters wait for their CDRs…
    target = _workspace(tmp_path, 'target')
    assert saved_filters.import_saved_filters(target, document) == 1
    [waiting] = saved_filters.list_saved_filters(target)
    assert waiting['dataset_ids'] == [] and len(waiting['missing_cdrs']) == 3 and waiting['status'] == 'saved'
    assert saved_filters.refresh_saved_filter(target, waiting['id'])[1].startswith(
        'The CDRs of this Saved Filter are not in this workspace')
    # …found by the SHA-256 of their files, whatever their names and ids there.
    _add_cdr(target, tmp_path / 'target', 'voice', 'Unrelated voice.xlsx', 'another voice file')
    target_ids = _three_cdrs(target, tmp_path / 'target', prefix='Renamed ')
    [resolved] = saved_filters.list_saved_filters(target)
    assert sorted(resolved['dataset_ids']) == sorted(target_ids)
    assert resolved['name'] == 'North by region' and resolved['pinned'] and resolved['missing_cdrs'] == []
    # Opened, it is calculated with the CDRs and methodology of this workspace.
    assert saved_filters.refresh_saved_filter(target, resolved['id']) == (True, '')
    calculated = saved_filters.calculate_saved_filter(target, resolved['id'])
    assert calculated['status'] == 'completed' and calculated['result']['scoring']
    # Imported again, it joins the Saved Filter it already is.
    saved_filters.import_saved_filters(target, document)
    assert [item['id'] for item in saved_filters.list_saved_filters(target)] == [resolved['id']]
    # The same selection made here is that Saved Filter.
    same, reused = saved_filters.save_saved_filter(
        target, target_ids, ['Operator', 'Region'], 'NSA', context_filters={'Region': ['North']})
    assert same['id'] == resolved['id'] and reused


def test_a_final_cdr_replacing_a_daily_one_is_offered_and_deleted_cdrs_keep_the_saved_result(tmp_path):
    repository = _workspace(tmp_path, 'workspace')
    folder = tmp_path / 'workspace'
    data_id = _add_cdr(repository, folder, 'data', 'UK_Data_CDR_20260715.xlsx', 'daily data', stage='daily')
    voice_id = _add_cdr(repository, folder, 'voice', 'UK_Voice_Final.xlsx', 'voice file')
    speech_id = _add_cdr(repository, folder, 'speech', 'UK_Speech_Final.xlsx', 'speech file')
    saved_filter, _ = saved_filters.save_saved_filter(repository, [data_id, voice_id, speech_id],
                                                                       ['Operator'], 'NSA')
    saved_filters.calculate_saved_filter(repository, saved_filter['id'])
    assert saved_filters.list_saved_filters(repository)[0]['newer_cdrs'] == []

    final_id = _add_cdr(repository, folder, 'data', 'UK_Data_CDR_Final.xlsx', 'final data')
    [listed] = saved_filters.list_saved_filters(repository)
    assert listed['newer_cdrs'] == [{'id': data_id, 'name': 'UK_Data_CDR_20260715.xlsx', 'replaced_by': final_id,
                                     'replaced_by_name': 'UK_Data_CDR_Final.xlsx'}]

    # Without one of its CDRs, the saved result is still shown, saying why it is not calculated again.
    repository.delete_dataset(voice_id)
    queued, unavailable = saved_filters.refresh_saved_filter(repository, saved_filter['id'])
    assert not queued and 'no longer exist' in unavailable
    kept = saved_filters.get_saved_filter(repository, saved_filter['id'], include_result=True)
    assert kept['status'] == 'completed' and kept['result']['scoring']


def test_use_newer_cdrs_updates_the_same_saved_filter_and_merges_one_with_that_selection(tmp_path):
    repository = _workspace(tmp_path, 'workspace')
    folder = tmp_path / 'workspace'
    data_id = _add_cdr(repository, folder, 'data', 'UK_Data_CDR_20260715.xlsx', 'daily data', stage='daily')
    voice_id = _add_cdr(repository, folder, 'voice', 'UK_Voice_Final.xlsx', 'voice file')
    speech_id = _add_cdr(repository, folder, 'speech', 'UK_Speech_Final.xlsx', 'speech file')
    saved_filter, _ = saved_filters.save_saved_filter(repository, [data_id, voice_id, speech_id], ['Operator'], 'NSA')
    saved_filters.calculate_saved_filter(repository, saved_filter['id'])
    saved_filters.update_saved_filter(repository, saved_filter['id'], pinned=True)
    final_id = _add_cdr(repository, folder, 'data', 'UK_Data_CDR_Final.xlsx', 'final data')
    # A Saved Filter that already has the newer selection is merged, giving its name.
    other, _ = saved_filters.save_saved_filter(repository, [final_id, voice_id, speech_id], ['Operator'], 'NSA')
    saved_filters.update_saved_filter(repository, other['id'], name='2026-Q3')

    updated = saved_filters.use_newer_cdrs(repository, saved_filter['id'], 'super')

    assert updated['merged_filter_id'] == other['id']
    assert [item['replaced_by'] for item in updated['replaced']] == [final_id]
    [listed] = saved_filters.list_saved_filters(repository)
    assert listed['id'] == saved_filter['id'] and listed['pinned'] and listed['name'] == '2026-Q3'
    assert listed['dataset_ids'] == [final_id, voice_id, speech_id]
    assert listed['status'] == 'queued' and listed['newer_cdrs'] == []
    found = saved_filters.find_saved_filter(repository, [final_id, voice_id, speech_id], ['Operator'], 'NSA')
    assert found['id'] == saved_filter['id']
    try:
        saved_filters.use_newer_cdrs(repository, saved_filter['id'])
    except ValueError as exc:
        assert 'Wait until' in str(exc)
    else:
        raise AssertionError('A queued Saved Filter must not change its CDRs.')


def test_edit_saved_filter_changes_its_selection_in_place_and_merges_one_with_that_selection(tmp_path):
    repository = _workspace(tmp_path, 'workspace')
    ids = _three_cdrs(repository, tmp_path / 'workspace')
    saved_filter, _ = saved_filters.save_saved_filter(repository, ids, ['Operator'], 'NSA')
    saved_filters.calculate_saved_filter(repository, saved_filter['id'])
    saved_filters.update_saved_filter(repository, saved_filter['id'], name='2026-Q3', pinned=True)
    # A Saved Filter that already has the new selection is merged into the one edited.
    other, _ = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Region'], 'NSA',
                                               context_filters={'Region': ['North']})
    saved_filters.calculate_saved_filter(repository, other['id'])

    edited = saved_filters.edit_saved_filter(repository, saved_filter['id'], ids, ['Operator', 'Region'], 'NSA',
                                             username='super', context_filters={'Region': ['North']})

    assert edited['changed'] and edited['merged_filter_id'] == other['id']
    assert edited['previous']['levels'] == ['Operator'] and edited['previous']['context_filters']['Region'] == []
    [listed] = saved_filters.list_saved_filters(repository)
    assert listed['id'] == saved_filter['id'] and listed['pinned'] and listed['name'] == '2026-Q3'
    assert listed['levels'] == ['Operator', 'Region'] and listed['context_filters']['Region'] == ['North']
    assert listed['status'] == 'queued'
    found = saved_filters.find_saved_filter(repository, ids, ['Operator', 'Region'], 'NSA', context_filters={'Region': ['North']})
    assert found['id'] == saved_filter['id']
    try:
        saved_filters.edit_saved_filter(repository, saved_filter['id'], ids, ['Operator'], 'NSA')
    except ValueError as exc:
        assert 'Wait until' in str(exc)
    else:
        raise AssertionError('A queued Saved Filter must not be edited.')
    # Calculated, the same selection changes nothing and keeps its result.
    saved_filters.calculate_saved_filter(repository, saved_filter['id'])
    unchanged = saved_filters.edit_saved_filter(repository, saved_filter['id'], ids, ['Operator', 'Region'], 'NSA',
                                                context_filters={'Region': ['North']})
    assert not unchanged['changed'] and unchanged['merged_filter_id'] is None
    assert saved_filters.get_saved_filter(repository, saved_filter['id'])['status'] == 'completed'


def test_edit_saved_filter_endpoint_is_recorded_and_calculates_only_a_changed_selection(client, monkeypatch):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    repository = app_module.repository
    calls = []

    def edit(_repository, filter_id, dataset_ids, levels, nr_mode, **options):
        calls.append({'filter_id': filter_id, 'dataset_ids': dataset_ids, 'levels': levels, 'nr_mode': nr_mode, **options})
        return {'saved_filter': {'id': filter_id, 'name': 'Q3'}, 'changed': len(calls) == 1,
                'previous': {'nr_mode': 'NSA', 'levels': ['Operator']}, 'merged_filter_id': None}

    monkeypatch.setattr(app_module, 'edit_saved_filter', edit)
    monkeypatch.setattr(app_module, 'validate_complete_scoring_cdr_selection', lambda _repository, ids, *_args, **_kwargs: ids)
    queued = []
    monkeypatch.setattr(app_module, '_queue_saved_filter_calculation', lambda _repository, filter_id: queued.append(filter_id))
    monkeypatch.setattr(app_module, 'prune_unpinned_saved_filters', lambda *_args: None)
    payload = {'dataset_ids': [4, 5, 6], 'aggregation_levels': ['Operator', 'Region'], 'nr_mode': 'NSA',
               'baseline_operator': 'EE', 'context_filters': {'Region': ['North']}}

    response = client.post('/api/scoring/saved-filters/7/edit', json=payload)

    assert response.status_code == 200
    assert response.json() == {'saved_filter': {'id': 7, 'name': 'Q3'}, 'cached': False, 'changed': True}
    assert calls[0]['dataset_ids'] == [4, 5, 6] and calls[0]['levels'] == ['Operator', 'Region']
    assert calls[0]['username'] == 'super' and calls[0]['context_filters']['Region'] == ['North']
    assert queued == [7]
    [event] = [row for row in repository.list_logs(limit=20) if row['action'] == 'edit_saved_filter']
    assert '"previous": {"nr_mode": "NSA", "levels": ["Operator"]}' in event['details']
    assert '"levels": ["Operator", "Region"]' in event['details'] and '"changed": true' in event['details']
    # The same selection again: nothing is calculated.
    assert client.post('/api/scoring/saved-filters/7/edit', json=payload).json()['cached'] is True
    assert queued == [7]


def test_favourites_filters_travel_with_their_own_backup_element(client, tmp_path: Path) -> None:
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
    used, _ = saved_filters.save_saved_filter(repository, ids, ['Operator'], 'NSA')
    saved_filters.update_saved_filter(repository, used['id'], name='Weekly view', pinned=True)
    other, _ = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA')
    backup_path = app_module.create_recurring_database_backup({
        'components': ['scoring_configuration', 'scoring_favourites_filters'], 'workspace_ids': [workspace.id],
        'backup_path': str(tmp_path), 'max_backups': 5,
    })
    for item in (used, other):
        saved_filters.delete_saved_filter(repository, item['id'])
    # The Scoring & GAP Analysis Methodologies no longer carries them.
    app_module.restore_database_backup(backup_path, ['scoring_configuration'])
    assert saved_filters.list_saved_filters(repository) == []
    # The Favourites Filters (not the others) travel as an element of their own.
    app_module.restore_database_backup(backup_path, ['scoring_favourites_filters'])
    [restored] = saved_filters.list_saved_filters(repository)
    assert restored['name'] == 'Weekly view' and restored['pinned'] and sorted(restored['dataset_ids']) == sorted(ids)
    assert 'scoring-favourites-filters' in app_module.WORKSPACE_ELEMENT_EXPORT_TARGETS
    assert app_module.archive_workspace_components_for_target('scoring-favourites-filters') == ['scoring_favourites_filters']
    assert 'scoring_favourites_filters' in app_module.full_workspace_archive_components()
    # Scoring & GAP Analysis Methodologies packages created before keep restoring their Saved Filters (and those made
    # before Saved Filters existed leave the current ones).
    earlier_package = json.dumps(saved_filters.saved_filters_document(repository)).encode()
    saved_filters.delete_saved_filter(repository, restored['id'])
    app_module._restore_workspace_saved_filters(workspace, earlier_package)
    app_module._restore_workspace_saved_filters(workspace, None)
    assert [item['name'] for item in saved_filters.list_saved_filters(repository)] == ['Weekly view']


def _starred_order(repository: Repository) -> list[int]:
    return [int(item['id']) for item in saved_filters.list_saved_filters(repository) if item['pinned']]


def test_starred_saved_filters_keep_their_place_and_are_moved_by_dragging(tmp_path):
    repository = _workspace(tmp_path, 'source')
    ids = _three_cdrs(repository, tmp_path / 'source')
    created = [saved_filters.save_saved_filter(repository, ids, levels, 'NSA')[0]['id']
               for levels in (['Operator'], ['Operator', 'Region'], ['Operator', 'Campaign'])]
    first, second, third = created
    # A newly starred Saved Filter goes first; opening one does not move it.
    for filter_id in created:
        saved_filters.update_saved_filter(repository, filter_id, pinned=True)
    assert _starred_order(repository) == [third, second, first]
    saved_filters.mark_saved_filter_used(repository, first)
    assert _starred_order(repository) == [third, second, first]
    # Dragged: the order given, the starred ones left out after it.
    assert saved_filters.reorder_saved_filters(repository, [first, third]) == [first, third, second]
    assert _starred_order(repository) == [first, third, second]
    # Unstarred, it leaves the order of the starred ones.
    saved_filters.update_saved_filter(repository, third, pinned=False)
    assert _starred_order(repository) == [first, second]
    assert saved_filters.get_saved_filter(repository, third)['position'] is None

    # The order travels with the Saved Filters.
    document = saved_filters.saved_filters_document(repository)
    target = _workspace(tmp_path, 'target')
    assert saved_filters.import_saved_filters(target, document) == 3
    imported = [item for item in saved_filters.list_saved_filters(target) if item['pinned']]
    assert [item['levels'] for item in imported] == [['Operator'], ['Operator', 'Region']]


def test_the_starred_saved_filters_keep_the_order_they_had_before_their_place_was_stored(tmp_path):
    repository = _workspace(tmp_path, 'source')
    ids = _three_cdrs(repository, tmp_path / 'source')
    older = saved_filters.save_saved_filter(repository, ids, ['Operator'], 'NSA')[0]['id']
    newer = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Region'], 'NSA')[0]['id']
    with repository.connection() as connection:
        connection.execute("UPDATE saved_filters SET pinned = 1, last_used_at = '2026-01-01T00:00:00+00:00' WHERE id = ?", (older,))
        connection.execute("UPDATE saved_filters SET pinned = 1, last_used_at = '2026-02-01T00:00:00+00:00' WHERE id = ?", (newer,))
        connection.execute('ALTER TABLE saved_filters DROP COLUMN position')
    repository.initialize()
    assert _starred_order(repository) == [newer, older]
    assert [saved_filters.get_saved_filter(repository, filter_id)['position'] for filter_id in (newer, older)] == [1, 2]


def test_dragging_saved_filters_is_recorded_in_app_events(client, monkeypatch):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    repository = app_module.repository
    monkeypatch.setattr(saved_filters, 'reorder_saved_filters', lambda _repository, ids: [int(value) for value in ids])
    monkeypatch.setattr(app_module, 'list_saved_filters',
                        lambda _repository: [{'id': 4, 'pinned': True}, {'id': 9, 'pinned': True}])
    monkeypatch.setattr(app_module, 'reorder_saved_filters', lambda _repository, ids: [int(value) for value in ids])
    response = client.post('/api/scoring/saved-filters/order', json={'filter_ids': [9, 4]})
    assert response.status_code == 200 and response.json() == {'order': [9, 4]}
    [event] = [row for row in repository.list_logs(limit=20) if row['action'] == 'reorder_saved_filters']
    assert '"previous_order": [4, 9]' in event['details'] and '"order": [9, 4]' in event['details']


def test_use_newer_cdrs_endpoint_is_recorded_and_leaves_the_open_saved_filter_when_not_selecting(client, monkeypatch):
    client.post('/login', data={'username': 'super', 'password': 'super123'}, follow_redirects=False)
    repository = app_module.repository
    replaced = [{'id': 3, 'name': 'Daily.xlsx', 'replaced_by': 8, 'replaced_by_name': 'Final.xlsx'}]
    monkeypatch.setattr(app_module, 'use_newer_cdrs', lambda _repository, filter_id, _username: {
        'saved_filter': {'id': filter_id, 'name': 'Q3', 'dataset_ids': [8, 5, 6]}, 'replaced': replaced, 'merged_filter_id': None})
    queued, pruned = [], []
    monkeypatch.setattr(app_module, '_queue_saved_filter_calculation', lambda _repository, filter_id: queued.append(filter_id))
    monkeypatch.setattr(app_module, 'prune_unpinned_saved_filters', lambda _repository, keep_id, _username: pruned.append(keep_id))

    response = client.post('/api/scoring/saved-filters/7/use-newer-cdrs', json={'select': False})

    assert response.status_code == 200 and response.json()['saved_filter']['id'] == 7
    assert queued == [7] and pruned == []
    [event] = [row for row in repository.list_logs(limit=20) if row['action'] == 'saved_filter_use_newer_cdrs']
    assert '"replaced_by_file": "Final.xlsx"' in event['details'] and '"opened": false' in event['details']
    client.post('/api/scoring/saved-filters/7/use-newer-cdrs')
    assert pruned == [7]


def test_scoring_report_templates_travel_with_their_own_backup_element(client, tmp_path: Path) -> None:
    from src.modules import scoring_reports

    response = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False)
    assert response.status_code == 303
    workspace = app_module.active_workspace
    repository = Repository(workspace.database_path, global_db_path=app_module.repository.db_path,
                            workspace_registry_db_path=app_module.workspace_registry.registry_path)
    repository.initialize()
    scoring_reports.save_named_configuration(repository, 'Weekly custom', scoring_reports.default_report_configuration())
    names = lambda: [item['name'] for item in scoring_reports.load_report_state(repository)['configurations']]  # noqa: E731
    backup_path = app_module.create_recurring_database_backup({
        'components': ['scoring_configuration', 'scoring_report_templates'], 'workspace_ids': [workspace.id],
        'backup_path': str(tmp_path), 'max_backups': 5,
    })
    earlier_package = json.dumps(scoring_reports.report_configurations_document(scoring_reports.load_report_state(repository))).encode()
    scoring_reports.delete_named_configuration(repository, 'Weekly custom')
    # The Scoring & GAP Analysis Methodologies no longer carries them: they travel as an element of their own.
    app_module.restore_database_backup(backup_path, ['scoring_configuration'])
    assert 'Weekly custom' not in names()
    app_module.restore_database_backup(backup_path, ['scoring_report_templates'])
    assert 'Weekly custom' in names()
    assert 'scoring-report-templates' in app_module.WORKSPACE_ELEMENT_EXPORT_TARGETS
    assert app_module.archive_workspace_components_for_target('scoring-report-templates') == ['scoring_report_templates']
    assert 'scoring_report_templates' in app_module.full_workspace_archive_components()
    # Scoring & GAP Analysis Methodologies packages created before keep restoring the configurations they carried.
    scoring_reports.delete_named_configuration(repository, 'Weekly custom')
    app_module._restore_workspace_scoring_report_configurations(workspace, earlier_package)
    assert 'Weekly custom' in names()
    page = client.get('/admin').text
    assert 'Scoring &amp; GAP Report Templates (from active workspace)' in page


def test_saved_filters_travel_with_their_geographical_areas(tmp_path):
    source = _workspace(tmp_path, 'source')
    ids = _three_cdrs(source, tmp_path / 'source')
    area = {'breakdown': 'Cluster', 'cities': ['Leeds', 'Glasgow'], 'main_cities': True, 'time_split': 'Quarterly'}
    used, _ = saved_filters.save_saved_filter(source, ids, ['Operator', 'Region'], 'NSA', baseline_operator='VF',
                                              area_summary=area)
    saved_filters.update_saved_filter(source, used['id'], pinned=True)
    [before] = saved_filters.list_saved_filters(source)
    document = json.loads(json.dumps(saved_filters.saved_filters_document(source, favourites_only=True)))
    # Main Cities travel as such: the workspace that calculates the Saved Filter resolves them with its own.
    [entry] = document['saved_filters']
    assert entry['area_summary'] == before['area_summary'] == area
    # Packages made before the Focus operators came from the Operator Maps still import.
    entry['compared_operators'] = ['EE', 'O2']

    target = _workspace(tmp_path, 'target')
    saved_filters.import_saved_filters(target, document)
    _three_cdrs(target, tmp_path / 'target', prefix='Renamed ')
    fields = ('nr_mode', 'levels', 'baseline_operator', 'context_filters', 'area_summary', 'pinned')
    [after] = saved_filters.list_saved_filters(target)
    assert {key: after[key] for key in fields} == {key: before[key] for key in fields}
    assert saved_filters.refresh_saved_filter(target, after['id']) == (True, '')


def test_favourites_filters_with_a_campaign_choice_take_the_cdrs_it_stands_for_in_each_workspace(tmp_path):
    source = _workspace(tmp_path, 'source')
    _three_cdrs(source, tmp_path / 'source')
    used, _ = saved_filters.save_saved_filter(source, [], ['Operator'], 'NSA', context_filters={'Campaign': ['@latest-campaign']})
    saved_filters.update_saved_filter(source, used['id'], name='Latest campaign', pinned=True)
    document = json.loads(json.dumps(saved_filters.saved_filters_document(source, favourites_only=True)))
    # Another workspace with other files: the Favourites Filter waits until it has CDRs of the campaign it stands for.
    target = _workspace(tmp_path, 'target')
    saved_filters.import_saved_filters(target, document)
    assert saved_filters.list_saved_filters(target)[0]['dataset_ids'] == []
    target_ids = [_add_cdr(target, tmp_path / 'target', kind, f'Other {kind}.xlsx', f'other {kind} file')
                  for kind in ('data', 'voice', 'speech')]
    [resolved] = saved_filters.list_saved_filters(target)
    assert sorted(resolved['dataset_ids']) == sorted(target_ids) and resolved['name'] == 'Latest campaign' and resolved['pinned']
    # The starter Favourites Filters have no CDRs: they wait for those of their Campaign choice.
    entry = {key: value for key, value in document['saved_filters'][0].items() if key != 'cdrs'}
    fresh = _workspace(tmp_path, 'fresh')
    assert saved_filters.import_saved_filters(fresh, {**document, 'saved_filters': [entry]}) == 1
    [waiting] = saved_filters.list_saved_filters(fresh)
    assert waiting['dataset_ids'] == [] and waiting['missing_cdrs'] == ['Latest campaign CDRs']
    fresh_ids = _three_cdrs(fresh, tmp_path / 'fresh')
    assert sorted(saved_filters.list_saved_filters(fresh)[0]['dataset_ids']) == sorted(fresh_ids)
    # Without a Campaign choice, a Saved Filter needs its CDRs.
    with pytest.raises(ValueError, match='invalid'):
        saved_filters.import_saved_filters(fresh, {**document, 'saved_filters': [{**entry, 'context_filters': {}}]})


def test_favourites_filters_out_of_date_are_calculated_while_the_application_is_idle(client, tmp_path: Path, monkeypatch) -> None:
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
    favourite, _ = saved_filters.save_saved_filter(repository, ids, ['Operator'], 'NSA')
    saved_filters.update_saved_filter(repository, favourite['id'], name='Weekly view', pinned=True)
    other, _ = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA')
    for item in (favourite, other):
        saved_filters.calculate_saved_filter(repository, item['id'])
    queued = []
    monkeypatch.setattr(app_module, '_queue_saved_filter_calculation', lambda _repository, filter_id: queued.append(filter_id))
    # Up to date: nothing is calculated.
    app_module._calculate_favourites_filters_when_idle()
    assert queued == []
    # Out of date (here, an older calculation): the Favourites Filter is calculated again, not the others.
    with repository.connection() as connection:
        connection.execute("UPDATE saved_filters SET result_key = 'older' WHERE id IN (?, ?)", (favourite['id'], other['id']))
    app_module._calculate_favourites_filters_when_idle()
    assert queued == [favourite['id']]
    [event] = [row for row in repository.list_logs(limit=20) if row['action'] == 'scoring_calculation_requested']
    assert event['username'] == 'system' and '"idle": true' in event['details'] and 'Weekly view' in event['details']
    assert ('_calculate_favourites_filters_when_idle' in
            [callback.__name__ for _seconds, callback in app_module.IDLE_TASK_CALLBACKS])


def test_operator_filters_take_patterns_and_exclusions_when_they_are_calculated(tmp_path):
    repository = _workspace(tmp_path, 'w')
    ids = _three_cdrs(repository, tmp_path / 'w')

    def scored(values):
        saved, _ = saved_filters.save_saved_filter(repository, ids, ['Operator'], 'NSA', context_filters={'Operator': values})
        result = saved_filters.calculate_saved_filter(repository, saved['id'])['result']
        return saved, sorted({str(row.get('operator') or row.get('Operator')) for row in result['scoring']})

    excluded, operators = scored(['Not Three*'])
    assert operators == ['EE', 'Vodafone UK'] and excluded['context_filters']['Operator'] == ['Not Three*']
    assert scored(['vodafone*', 'EE'])[1] == ['EE', 'Vodafone UK']
    # Kept as such in the documents of the Saved Filters, which take them to other workspaces.
    saved_filters.update_saved_filter(repository, excluded['id'], pinned=True)
    [entry] = saved_filters.saved_filters_document(repository, favourites_only=True)['saved_filters']
    assert entry['context_filters']['Operator'] == ['Not Three*']
