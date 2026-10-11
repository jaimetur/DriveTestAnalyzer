from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest

from src.modules import saved_filters
from src.modules.repository import Repository, SCHEMA, SCORING_CONFIGURATION_STATE_KEY, local_now_iso
from src.modules.scoring_config import save_aggregation_hierarchy
from scoring_fixtures import scoring_configuration


@pytest.fixture()
def scoring_engine(monkeypatch):
    engine = ModuleType('src.modules.scoring')
    engine.METHOD_VERSION = 'test-method-v1'
    engine.required_input_columns = lambda kind, levels: [*levels, 'score']
    calls = []
    engine.configuration_snapshots = []
    engine.baseline_alias_snapshots = []
    engine.operator_mapping_snapshots = []

    def calculate_scoring(
        frames, levels, *, baseline_operator, configuration=None, baseline_aliases=None,
        operator_mappings=None,
    ):
        calls.append((frames, levels, baseline_operator))
        engine.configuration_snapshots.append(copy.deepcopy(configuration))
        engine.baseline_alias_snapshots.append(list(baseline_aliases or []))
        engine.operator_mapping_snapshots.append(dict(operator_mappings or {}))
        return {
            'scoring': [{'Operator': 'EE', 'Score': 4}],
            'gap': [{'Operator': 'EE', 'Gap': 0}],
            'charts': [],
            'warnings': [],
        }

    engine.calculate_scoring = calculate_scoring
    monkeypatch.setattr(saved_filters, '_scoring_engine', lambda: engine)
    return engine, calls


@pytest.fixture()
def repository(tmp_path: Path) -> Repository:
    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()
    repository.replace_scoring_configuration(scoring_configuration())
    return repository


def add_dataset(repository: Repository, name: str = 'UK_Q2_2026_NSA_Data.csv', *, kind: str = 'data', nr_mode: str = 'NSA') -> int:
    source = Path(repository.db_path).parent / name
    source.write_text('source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'tester')
    frame = pd.DataFrame({
        'Operator': ['EE', 'O2'],
        'Region': ['North', 'South'],
        'City': ['Leeds', 'London'],
        'Operator_Vendor': ['Nokia', 'Ericsson'],
        'Vendor': ['Nokia', 'Ericsson'],
        'Dataset_Kind': [kind, kind],
        'score': [3.0, 4.0],
        'unused_payload': ['large', 'field'],
    })
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(
        dataset_id,
        status='ready', progress=100, dataset_kind=kind, nr_mode=nr_mode,
        row_count=len(frame), column_count=len(frame.columns), processed_at=local_now_iso(),
    )
    repository.replace_cdr_catalogue(
        dataset_id, vendors=['Nokia', 'Ericsson'], vendors_only=['Nokia', 'Ericsson'], regions=['North', 'South'],
        cities=['Leeds', 'London'], campaigns=['2026-Q2'],
    )
    return dataset_id


def add_complete_scoring_sources(repository: Repository, prefix: str = 'Scoped') -> list[int]:
    dataset_ids = []
    for kind in ('data', 'voice', 'speech'):
        dataset_id = add_dataset(repository, f'{prefix}_NSA_{kind.title()}.csv', kind=kind)
        frame = pd.DataFrame({
            'Operator': ['VF_UK', 'VF_UK', 'O2', 'VF_UK', 'VF_UK'],
            'Region': ['North'] * 5,
            'City': ['Leeds', 'Manchester', 'Leeds', 'Leeds', 'Leeds'],
            'Operator_Vendor': ['Nokia', 'Nokia', 'Nokia', 'Ericsson', 'Nokia'],
            'Vendor': ['Nokia', 'Nokia', 'Nokia', 'Ericsson', 'Nokia'],
            'Campaign': ['2026-Q2', '2026-Q2', '2026-Q2', '2026-Q2', '2026-Q1'],
            'Dataset_Kind': [kind] * 5,
            'score': [3.0, 4.0, 5.0, 6.0, 7.0],
        })
        repository.replace_dataset_rows(dataset_id, frame)
        repository.update_dataset_profile(
            dataset_id, row_count=len(frame), column_count=len(frame.columns),
        )
        dataset_ids.append(dataset_id)
    return dataset_ids


def test_legacy_operator_alias_filter_matches_current_all_suffix(repository):
    dataset_id = add_dataset(repository)
    repository.replace_operator_mapping_groups([
        {'canonical': 'Vodafone UK', 'aliases': ['VF_UK'], 'color': '#FF0000'},
    ])
    repository.replace_dataset_rows(dataset_id, pd.DataFrame({
        'Operator': ['Vodafone UK', 'Vodafone UK'],
        'Operator_Vendor': ['Vodafone UK', 'Vodafone UK_Ericsson'],
        'Vendor': ['Vodafone UK - All', 'Ericsson'],
    }))

    matched = repository.load_dataset_rows(
        dataset_id, ['Operator', 'Vendor'], {'Vendor_Only': ['VF_UK - All Vendors']},
    )

    assert matched['Operator'].tolist() == ['Vodafone UK']
    assert matched['Vendor'].tolist() == ['Vodafone UK - All']


def test_saved_filters_persist_results_and_reuse_completed_cache(repository, scoring_engine):
    _engine, calls = scoring_engine
    global_kpi = {
        'campaign': '2026-Q2', 'region': 'North', 'operator': 'EE',
        'kpi_code': 'C5', 'kpi': 'CALL SUCCESS RATIO [%]', 'category': 'CLASSIC CALLS',
        'kpi_type': 'Reliable', 'value': 98.75, 'sample_count': 12,
        'environment': 'All Environments', 'complete_coverage': True, 'missing_environments': [],
    }
    original_calculate = _engine.calculate_scoring

    def calculate_with_global_kpis(*args, **kwargs):
        result = original_calculate(*args, **kwargs)
        result['global_kpis'] = [global_kpi]
        return result

    _engine.calculate_scoring = calculate_with_global_kpis
    dataset_id = add_dataset(repository)

    job, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region', 'City'], 'NSA', username='tester',
    )
    assert not reused
    assert job['status'] == 'queued'
    assert job['aggregation_levels'] == ['Operator', 'Region', 'City']
    assert job['campaigns'] == ['2026-Q2']
    duplicate, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region', 'City'], 'NSA', username='other-user',
    )
    assert reused
    assert duplicate['id'] == job['id']

    completed = saved_filters.calculate_saved_filter(repository, job['id'])
    assert completed['status'] == 'completed'
    assert completed['result']['scoring'] == [{'Operator': 'EE', 'Score': 4}]
    assert completed['result']['global_kpis'] == [global_kpi]
    reloaded = saved_filters.get_saved_filter(repository, job['id'], include_result=True)
    assert reloaded['result']['global_kpis'] == [global_kpi]
    assert len(calls) == 1
    loaded_frames, levels, baseline = calls[0]
    assert levels == ['Operator', 'Region', 'City']
    assert baseline == 'EE'
    assert 'unused_payload' not in loaded_frames['data'].columns

    cached, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region', 'City'], 'NSA', username='tester',
    )
    assert reused
    assert cached['id'] == job['id']
    assert cached['result']['gap'] == [{'Operator': 'EE', 'Gap': 0}]
    summaries = saved_filters.list_saved_filters(repository)
    assert len(summaries) == 1
    assert summaries[0]['result'] is None
    assert 'configuration' not in summaries[0]
    assert saved_filters.get_saved_filter(repository, 9999) is None


def test_scoring_job_creation_requires_a_persisted_configuration(repository):
    dataset_id = add_dataset(repository)
    repository.set_workspace_state(SCORING_CONFIGURATION_STATE_KEY, '')

    with pytest.raises(ValueError, match='Import a Scoring Configuration'):
        saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')


def test_force_creates_a_fresh_calculation_and_method_baseline_are_cached(repository, scoring_engine):
    _engine, calls = scoring_engine
    dataset_id = add_dataset(repository)
    first, _ = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')
    active, reused_active = saved_filters.save_saved_filter(
        repository, [dataset_id], [], 'NSA', force=True,
    )
    assert reused_active
    assert active['id'] == first['id']
    assert len(saved_filters.list_saved_filters(repository)) == 1
    saved_filters.calculate_saved_filter(repository, first['id'])

    forced, reused = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA', force=True)
    assert not reused
    assert forced['id'] == first['id']
    assert forced['status'] == 'queued'
    assert forced['result'] is None
    assert forced['error'] == ''
    assert len(saved_filters.list_saved_filters(repository)) == 1
    assert saved_filters.calculate_saved_filter(repository, forced['id'])['status'] == 'completed'

    other_baseline, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], [], 'NSA', baseline_operator='O2',
    )
    assert not reused
    assert other_baseline['id'] != forced['id']
    assert len(calls) == 2


def test_filters_used_again_move_to_the_top_with_their_last_use(repository, scoring_engine, monkeypatch):
    dataset_id = add_dataset(repository)
    monkeypatch.setattr(saved_filters, 'local_now_iso', lambda: '2026-10-02T12:00:00+02:00')
    first, _ = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')
    saved_filters.calculate_saved_filter(repository, first['id'])
    monkeypatch.setattr(saved_filters, 'local_now_iso', lambda: '2026-10-02T11:00:00+00:00')
    second, _ = saved_filters.save_saved_filter(
        repository, [dataset_id], [], 'NSA', baseline_operator='O2',
    )
    assert [job['id'] for job in saved_filters.list_saved_filters(repository)] == [second['id'], first['id']]

    monkeypatch.setattr(saved_filters, 'local_now_iso', lambda: '2026-10-02T12:00:00+00:00')
    recalculated, reused = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA', force=True)
    assert not reused
    assert recalculated['id'] == first['id']
    assert recalculated['last_used_at'] == '2026-10-02T12:00:00+00:00'
    assert recalculated['updated_at'] == recalculated['last_used_at']
    assert recalculated['created_at'] == '2026-10-02T12:00:00+02:00' and recalculated['use_count'] == 2
    assert [job['id'] for job in saved_filters.list_saved_filters(repository)] == [first['id'], second['id']]
    active, reused = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA', force=True)
    assert reused and active['use_count'] == 3
    # A pinned Saved Filter stays first.
    saved_filters.update_saved_filter(repository, second['id'], pinned=True, name='  O2   reference ')
    listed = saved_filters.list_saved_filters(repository)
    assert [job['id'] for job in listed] == [second['id'], first['id']]
    assert listed[0]['name'] == 'O2 reference' and listed[0]['pinned']


def test_force_retries_failed_calculation_in_place(repository, scoring_engine):
    _engine, _calls = scoring_engine
    dataset_id = add_dataset(repository)
    job, _ = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')
    saved_filters.calculate_saved_filter(repository, job['id'])
    with repository.connection() as connection:
        connection.execute(
            """UPDATE saved_filters SET status = 'failed', progress = 100,
               result_json = ?, last_error = ?, started_at = ?, finished_at = ?, message = ?
               WHERE id = ?""",
            ('{"old":true}', 'previous error', '2026-01-01T00:00:00+00:00',
             '2026-01-01T00:01:00+00:00', 'Failed', job['id']),
        )

    retry, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], [], 'NSA', force=True,
    )

    assert not reused
    assert retry['id'] == job['id']
    assert retry['status'] == 'queued'
    assert retry['progress'] == 0
    assert retry['result'] is None
    assert retry['error'] == ''
    assert retry['started_at'] == ''
    assert retry['finished_at'] == ''
    assert len(saved_filters.list_saved_filters(repository)) == 1
    assert saved_filters.calculate_saved_filter(repository, retry['id'])['status'] == 'completed'


@pytest.mark.parametrize('status', ['completed', 'queued', 'failed'])
def test_engine_upgrade_matches_saved_inputs_and_recalculates_in_place(repository, scoring_engine, status):
    dataset_id = add_dataset(repository)
    job, _ = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    with repository.connection() as connection:
        connection.execute(
            'UPDATE saved_filters SET result_key = ?, method_version = ?, status = ? WHERE id = ?',
            ('old-cache-format', 'previous-engine-version', status, job['id']),
        )
    match = saved_filters.find_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    assert match['id'] == job['id']
    assert match['result_key'] == 'old-cache-format'
    assert saved_filters.find_saved_filter(
        repository, [dataset_id], ['City'], 'NSA',
    ) is None
    assert saved_filters.find_saved_filter(
        repository, [dataset_id], ['Region'], 'NSA', baseline_operator='O2',
    ) is None
    retry, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region'], 'NSA', force=True,
    )
    assert retry['id'] == job['id']
    assert reused is (status == 'queued')
    assert len(saved_filters.list_saved_filters(repository)) == 1
    if not reused:
        assert retry['result_key'] == job['result_key']
        assert retry['method_version'] == job['method_version']
        assert saved_filters.calculate_saved_filter(repository, retry['id'])['status'] == 'completed'


def test_find_saved_filter_is_read_only_and_tells_whether_its_result_is_up_to_date(repository, scoring_engine):
    _engine, _calls = scoring_engine
    dataset_ids = add_complete_scoring_sources(repository, 'MatchIdentity')
    filters = {'Region': ['South', 'North'], 'Vendor': ['Nokia', 'Ericsson']}
    assert saved_filters.find_saved_filter(
        repository, dataset_ids, ['Region'], 'NSA', context_filters=filters,
    ) is None
    assert saved_filters.list_saved_filters(repository) == []

    job, reused = saved_filters.save_saved_filter(
        repository, dataset_ids, ['Region'], 'NSA', context_filters=filters,
    )
    assert not reused
    match = saved_filters.find_saved_filter(
        repository, [*reversed(dataset_ids), dataset_ids[0]], ['Region'], 'NSA',
        context_filters={'region': ['north', 'south'], 'vendor': ['ericsson', 'nokia']},
    )
    assert match['id'] == job['id']
    assert match['result_key'] == job['result_key']
    assert saved_filters.find_saved_filter(
        repository, dataset_ids, ['City'], 'NSA', context_filters=filters,
    ) is None
    assert saved_filters.find_saved_filter(
        repository, dataset_ids, ['Region'], 'NSA', baseline_operator='O2', context_filters=filters,
    ) is None
    assert len(saved_filters.list_saved_filters(repository)) == 1

    original_configuration = repository.get_scoring_configuration()
    changed_configuration = scoring_configuration()
    changed_configuration['metrics'][0]['contexts']['DriveCity']['thresholds']['low'] += 1
    saved_filters.calculate_saved_filter(repository, job['id'])
    assert saved_filters.find_saved_filter(
        repository, dataset_ids, ['Region'], 'NSA', context_filters=filters,
    )['up_to_date']
    # The same selection is the same Saved Filter whatever its methodology or CDRs hold today; its saved result
    # is then out of date.
    repository.replace_scoring_configuration(changed_configuration)
    match = saved_filters.find_saved_filter(
        repository, dataset_ids, ['Region'], 'NSA', context_filters=filters,
    )
    assert match['id'] == job['id'] and not match['up_to_date']
    repository.replace_scoring_configuration(original_configuration)
    assert saved_filters.find_saved_filter(
        repository, dataset_ids, ['Region'], 'NSA', context_filters=filters,
    )['up_to_date']
    repository.update_dataset_profile(dataset_ids[0], processed_at=local_now_iso())
    match = saved_filters.find_saved_filter(
        repository, dataset_ids, ['Region'], 'NSA', context_filters=filters,
    )
    assert match['id'] == job['id'] and not match['up_to_date']
    assert len(saved_filters.list_saved_filters(repository)) == 1


def test_a_queued_calculation_keeps_its_methodology_and_a_new_one_recalculates_the_filters(repository, scoring_engine):
    engine, _calls = scoring_engine
    dataset_id = add_dataset(repository)
    initial, _ = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    original_configuration = copy.deepcopy(initial['configuration'])

    changed_configuration = scoring_configuration()
    c5 = next(metric for metric in changed_configuration['metrics'] if metric['code'] == 'K1')
    c5['contexts']['DriveCity']['thresholds']['low'] = 86
    repository.replace_scoring_configuration(changed_configuration)
    # The same selection is the same Saved Filter, still calculating with the methodology it was queued with.
    same, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    assert reused and same['id'] == initial['id']
    completed = saved_filters.calculate_saved_filter(repository, initial['id'])
    assert completed['status'] == 'completed'
    assert completed['result']['configuration'] == original_configuration
    assert engine.configuration_snapshots[0] == original_configuration
    # Opened again, its result is calculated with the methodology of today.
    assert saved_filters.refresh_saved_filter(repository, initial['id']) == (True, '')
    recalculated = saved_filters.calculate_saved_filter(repository, initial['id'])
    assert recalculated['result']['configuration']['metrics'][0]['contexts']['DriveCity']['thresholds']['low'] == 86
    assert saved_filters.refresh_saved_filter(repository, initial['id']) == (False, '')


def test_legacy_job_configuration_snapshot_is_returned_without_walk_migration(repository, scoring_engine):
    engine, _calls = scoring_engine
    from src.modules.scoring import method_version_for_configuration

    engine.method_version_for_configuration = method_version_for_configuration
    dataset_id = add_dataset(repository)
    job, _reused = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')
    legacy = copy.deepcopy(job['configuration'])
    legacy['scope']['environments'].pop('Walk')
    for metric in legacy['metrics']:
        metric['contexts'].pop('Walk')

    with repository.connection() as connection:
        row = connection.execute(
            'SELECT source_metadata_json FROM saved_filters WHERE id = ?', (job['id'],),
        ).fetchone()
        snapshot = json.loads(row['source_metadata_json'])
        snapshot['configuration'] = legacy
        connection.execute(
            'UPDATE saved_filters SET source_metadata_json = ?, method_version = ? WHERE id = ?',
            (json.dumps(snapshot), method_version_for_configuration(legacy), job['id']),
        )

    loaded = saved_filters.get_saved_filter(repository, job['id'])
    assert loaded['configuration'] == legacy
    assert 'Walk' not in loaded['configuration']['scope']['environments']
    completed = saved_filters.calculate_saved_filter(repository, job['id'])
    assert completed['status'] == 'completed'
    assert completed['configuration'] == legacy
    with repository.connection() as connection:
        stored = connection.execute(
            'SELECT source_metadata_json FROM saved_filters WHERE id = ?', (job['id'],),
        ).fetchone()
    assert json.loads(stored['source_metadata_json'])['configuration'] == legacy


def test_active_profile_identity_partitions_cache_and_is_saved_with_job(repository, scoring_engine):
    dataset_id = add_dataset(repository)
    first, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    assert not reused
    assert first['scoring_profile_id'] == 'netcheck-2026'
    assert saved_filters.calculate_saved_filter(repository, first['id'])['status'] == 'completed'

    profiles = repository.get_scoring_profiles()
    second_profile = copy.deepcopy(profiles['profiles'][0])
    second_profile.update({'id': 'netcheck-alt', 'name': 'NetCheck Alternate'})
    profiles['profiles'].append(second_profile)
    profiles['active_profile_id'] = second_profile['id']
    repository.replace_scoring_profiles(profiles)

    second, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    assert not reused
    assert second['id'] != first['id']
    assert second['scoring_profile_id'] == 'netcheck-alt'
    assert second['scoring_profile_name'] == 'NetCheck Alternate'

    profiles['active_profile_id'] = 'netcheck-2026'
    repository.replace_scoring_profiles(profiles)
    cached, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    assert reused
    assert cached['id'] == first['id']


def test_explicit_inactive_profile_sets_job_snapshot_and_hierarchy_without_switching_active(
    repository, scoring_engine,
):
    engine, _calls = scoring_engine
    dataset_id = add_dataset(repository)
    profiles = repository.get_scoring_profiles()
    active_id = profiles['active_profile_id']
    active_configuration = copy.deepcopy(repository.get_scoring_configuration())
    inactive = copy.deepcopy(profiles['profiles'][0])
    inactive.update({'id': 'netcheck-2025', 'name': 'NetCheck 2025'})
    inactive['configuration']['version'] = 'NetCheck 2025'
    save_aggregation_hierarchy(repository, ['Region', 'Operator', 'Vendor', 'City', 'Campaign'])
    inactive['configuration']['metrics'][0]['contexts']['DriveCity']['max_points'] = 88
    profiles['profiles'].append(inactive)
    repository.replace_scoring_profiles(profiles)

    selected, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region', 'City'], 'NSA', scoring_profile_id='netcheck-2025',
    )

    assert not reused
    assert selected['scoring_profile_id'] == 'netcheck-2025'
    assert selected['scoring_profile_name'] == 'NetCheck 2025'
    assert selected['configuration']['metrics'][0]['contexts']['DriveCity']['max_points'] == 88
    assert selected['aggregation_hierarchy'] == ['Region', 'Cluster', 'Operator', 'Vendor', 'City', 'Campaign']
    assert selected['aggregation_levels'] == ['Region', 'Operator', 'City']
    assert repository.get_scoring_profiles()['active_profile_id'] == active_id
    assert repository.get_scoring_configuration() == active_configuration

    completed = saved_filters.calculate_saved_filter(repository, selected['id'])
    assert completed['status'] == 'completed'
    assert engine.configuration_snapshots[0]['metrics'][0]['contexts']['DriveCity']['max_points'] == 88

    default_job, default_reused = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region', 'City'], 'NSA',
    )
    assert not default_reused
    assert default_job['scoring_profile_id'] == active_id
    assert default_job['id'] != selected['id']


def test_explicit_same_configuration_profile_uses_separate_cache_entry(repository):
    dataset_id = add_dataset(repository)
    profiles = repository.get_scoring_profiles()
    alternate = copy.deepcopy(profiles['profiles'][0])
    alternate.update({'id': 'netcheck-copy', 'name': 'NetCheck Copy'})
    profiles['profiles'].append(alternate)
    repository.replace_scoring_profiles(profiles)

    active, reused_active = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    explicit, reused_explicit = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region'], 'NSA', scoring_profile_id='netcheck-copy',
    )

    assert not reused_active and not reused_explicit
    assert explicit['id'] != active['id']
    assert explicit['scoring_profile_id'] == 'netcheck-copy'


def test_unknown_explicit_profile_is_rejected(repository):
    dataset_id = add_dataset(repository)

    with pytest.raises(ValueError, match='Scoring methodology missing-profile was not found\\.'):
        saved_filters.save_saved_filter(
            repository, [dataset_id], ['Region'], 'NSA', scoring_profile_id='missing-profile',
        )


def test_job_levels_follow_configured_hierarchy_and_snapshot_contract(repository, scoring_engine):
    engine, _calls = scoring_engine
    save_aggregation_hierarchy(repository, ['Campaign', 'City', 'Operator', 'Region', 'Vendor'])
    repository.replace_operator_mapping_groups([
        {'canonical': 'Vodafone UK', 'aliases': ['VF_UK'], 'color': '#FF0000'},
    ])
    dataset_ids = add_complete_scoring_sources(repository, 'Hierarchy')

    job, reused = saved_filters.save_saved_filter(
        repository, dataset_ids, ['Vendor', 'Region', 'City', 'Campaign'], 'NSA',
    )

    assert not reused
    assert job['levels'] == ['Campaign', 'City', 'Operator', 'Region', 'Vendor']
    assert job['aggregation_levels'] == job['levels']
    assert job['aggregation_hierarchy'] == ['Campaign', 'City', 'Operator', 'Region', 'Cluster', 'Vendor']
    assert job['aggregation_contract_version'] == 2
    completed = saved_filters.calculate_saved_filter(repository, job['id'])
    assert completed['status'] == 'completed'
    assert completed['result']['aggregation_levels'] == job['levels']
    assert completed['result']['aggregation_contract_version'] == 2
    assert engine.operator_mapping_snapshots[0] == {
        'vf_uk': 'Vodafone UK', 'vodafone uk': 'Vodafone UK',
    }


def test_baseline_alias_snapshot_is_cached_and_passed_to_engine(repository, scoring_engine):
    engine, _calls = scoring_engine
    dataset_id = add_dataset(repository)
    repository.replace_operator_mapping_groups([
        {'canonical': 'Vodafone UK', 'aliases': ['VF_UK', 'VF UK'], 'color': '#FF0000'},
    ])

    job, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region'], 'NSA', baseline_operator='Vodafone UK',
    )
    assert not reused
    assert set(job['baseline_aliases']) == {'Vodafone UK', 'VF_UK', 'VF UK'}
    completed = saved_filters.calculate_saved_filter(repository, job['id'])
    assert completed['result']['baseline_aliases'] == job['baseline_aliases']
    assert engine.baseline_alias_snapshots[0] == job['baseline_aliases']

    repository.replace_operator_mapping_groups([
        {'canonical': 'Vodafone UK', 'aliases': ['VF_UK', 'VF UK', 'Voda'], 'color': '#FF0000'},
    ])
    updated, reused = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Region'], 'NSA', baseline_operator='Vodafone UK',
    )
    # The same Saved Filter is calculated again with the new aliases.
    assert not reused
    assert updated['id'] == job['id']
    assert 'Voda' in updated['baseline_aliases']


def test_scoring_context_filters_are_pushed_down_and_persisted(repository, scoring_engine, monkeypatch):
    _engine, calls = scoring_engine
    dataset_ids = add_complete_scoring_sources(repository)
    repository.replace_operator_mapping_groups([
        {'canonical': 'Vodafone UK', 'aliases': ['VF_UK'], 'color': '#FF0000'},
    ])
    filters = {
        'Region': ['North'], 'City': ['Leeds'], 'Operator': ['Vodafone UK'],
        'Vendor': ['Nokia'], 'Campaign': ['2026-Q2'],
    }
    load_filters = []
    original_load_dataset_rows = repository.load_dataset_rows

    def record_load(dataset_id, columns, dataset_filters):
        load_filters.append(dataset_filters)
        return original_load_dataset_rows(dataset_id, columns, dataset_filters)

    monkeypatch.setattr(repository, 'load_dataset_rows', record_load)

    job, reused = saved_filters.save_saved_filter(
        repository, dataset_ids, ['Region'], 'NSA', context_filters=filters,
    )

    assert not reused
    assert job['context_filters'] == filters
    assert saved_filters.get_saved_filter(repository, job['id'])['context_filters'] == filters
    assert saved_filters.list_saved_filters(repository)[0]['context_filters'] == filters
    completed = saved_filters.calculate_saved_filter(repository, job['id'])
    assert completed['status'] == 'completed'
    loaded_frames, _levels, _baseline = calls[0]
    assert set(loaded_frames) == {'data', 'voice', 'speech'}
    for frame in loaded_frames.values():
        assert len(frame) == 1
        assert frame.iloc[0]['Operator'] == 'VF_UK'
        assert frame.iloc[0]['Region'] == 'North'
        assert frame.iloc[0]['score'] == 3.0
    assert len(load_filters) == 3
    for dataset_filters in load_filters:
        assert dataset_filters['Region'] == ['North']
        assert dataset_filters['City'] == ['Leeds']
        assert dataset_filters['Operator'] == ['VF_UK', 'Vodafone UK']
        assert dataset_filters['Vendor'] == ['Nokia']
        assert dataset_filters['Campaign'] == ['2026-Q2']


def test_scoring_context_filter_cache_is_order_independent_and_scope_specific(repository, scoring_engine):
    _engine, _calls = scoring_engine
    dataset_ids = add_complete_scoring_sources(repository)

    first, reused = saved_filters.save_saved_filter(
        repository, dataset_ids, [], 'NSA', context_filters={'Region': ['North', 'South']},
    )
    reordered, reused_reordered = saved_filters.save_saved_filter(
        repository, dataset_ids, [], 'NSA', context_filters={'Region': ['South', 'North']},
    )
    different_case, reused_different_case = saved_filters.save_saved_filter(
        repository, dataset_ids, [], 'NSA', context_filters={'Region': ['north', 'south']},
    )
    narrowed, reused_narrowed = saved_filters.save_saved_filter(
        repository, dataset_ids, [], 'NSA', context_filters={'Region': ['North']},
    )

    assert not reused
    assert reused_reordered
    assert reordered['id'] == first['id']
    assert reused_different_case
    assert different_case['id'] == first['id']
    assert not reused_narrowed
    assert narrowed['id'] != first['id']


def test_scoring_context_filters_skip_empty_sources_and_fail_when_a_type_has_no_matches(repository, scoring_engine):
    _engine, _calls = scoring_engine
    dataset_ids = add_complete_scoring_sources(repository, 'Rows')
    data_empty_id = add_dataset(repository, 'Rows_Empty_NSA_Data.csv', kind='data')
    frame = pd.DataFrame({
        'Operator': ['O2'], 'Region': ['South'], 'City': ['London'],
        'Operator_Vendor': ['Ericsson'], 'Campaign': ['2026-Q2'], 'score': [5.0],
    })
    repository.replace_dataset_rows(data_empty_id, frame)
    repository.update_dataset_profile(data_empty_id, row_count=1, column_count=len(frame.columns))
    voice_missing_region_id = add_dataset(repository, 'Rows_No_Region_NSA_Voice.csv', kind='voice')
    missing_region_frame = pd.DataFrame({
        'Operator': ['EE'], 'City': ['Leeds'], 'Operator_Vendor': ['Nokia'],
        'Campaign': ['2026-Q2'], 'score': [8.0],
    })
    repository.replace_dataset_rows(voice_missing_region_id, missing_region_frame)
    repository.update_dataset_profile(
        voice_missing_region_id, row_count=1, column_count=len(missing_region_frame.columns),
    )

    job, _ = saved_filters.save_saved_filter(
        repository, [*dataset_ids, data_empty_id, voice_missing_region_id], [], 'NSA',
        context_filters={'Region': ['North']},
    )
    completed = saved_filters.calculate_saved_filter(repository, job['id'])
    assert completed['status'] == 'completed'
    assert len(completed['result']['scoring']) == 1

    no_matches, _ = saved_filters.save_saved_filter(
        repository, dataset_ids, [], 'NSA', context_filters={'Region': ['Nowhere']},
    )
    failed = saved_filters.calculate_saved_filter(repository, no_matches['id'])
    assert failed['status'] == 'failed'
    assert 'Missing: Data, Voice, Speech' in failed['error']


def test_scoring_geography_filters_resolve_legacy_g_level_columns(repository, scoring_engine):
    _engine, calls = scoring_engine
    dataset_ids = []
    for kind in ('data', 'voice', 'speech'):
        dataset_id = add_dataset(repository, f'Legacy_Geography_NSA_{kind.title()}.csv', kind=kind)
        frame = pd.DataFrame({
            'Operator': ['EE', 'O2'], 'G_Level_2': ['North', 'South'],
            'G_Level_4': ['Leeds', 'London'], 'score': [3.0, 4.0],
        })
        repository.replace_dataset_rows(dataset_id, frame)
        repository.update_dataset_profile(
            dataset_id, row_count=len(frame), column_count=len(frame.columns),
        )
        dataset_ids.append(dataset_id)

    job, _ = saved_filters.save_saved_filter(
        repository, dataset_ids, [], 'NSA', context_filters={
            'Region': ['North'], 'City': ['Leeds'],
        },
    )
    completed = saved_filters.calculate_saved_filter(repository, job['id'])

    assert completed['status'] == 'completed'
    loaded_frames, _levels, _baseline = calls[0]
    assert all(len(frame) == 1 for frame in loaded_frames.values())


def test_campaign_completeness_checks_only_selected_campaigns(repository):
    data_q1 = add_dataset(repository, 'Campaign_Q1_NSA_Data.csv', kind='data')
    data_q2 = add_dataset(repository, 'Campaign_Q2_NSA_Data.csv', kind='data')
    voice_q1 = add_dataset(repository, 'Campaign_Q1_NSA_Voice.csv', kind='voice')
    speech_q1 = add_dataset(repository, 'Campaign_Q1_NSA_Speech.csv', kind='speech')
    for dataset_id, campaign in (
        (data_q1, '2026-Q1'), (data_q2, '2026-Q2'),
        (voice_q1, '2026-Q1'), (speech_q1, '2026-Q1'),
    ):
        repository.replace_cdr_catalogue(
            dataset_id, vendors=['Nokia', 'Ericsson'], regions=['North', 'South'],
            cities=['Leeds', 'London'], campaigns=[campaign],
        )

    with pytest.raises(ValueError, match=r'2026-Q2 \(Voice, Speech\)'):
        saved_filters.validate_complete_scoring_cdr_selection(
            repository, [data_q1, data_q2, voice_q1, speech_q1], 'NSA',
        )

    selected = saved_filters.validate_complete_scoring_cdr_selection(
        repository, [data_q1, data_q2, voice_q1, speech_q1], 'NSA',
        context_filters={'Campaign': ['2026-Q1']},
    )
    assert selected == [data_q1, data_q2, voice_q1, speech_q1]


def test_legacy_saved_filters_default_to_no_context_filters(repository):
    dataset_id = add_dataset(repository)
    job, _ = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')
    with repository.connection() as connection:
        connection.execute(
            'UPDATE saved_filters SET source_metadata_json = ? WHERE id = ?',
            ('[{"name":"Legacy CDR"}]', job['id']),
        )

    reloaded = saved_filters.get_saved_filter(repository, job['id'])

    assert reloaded['context_filters'] == {}
    assert reloaded['aggregation_contract_version'] == 1
    assert reloaded['aggregation_hierarchy'] == []


def test_scoring_cache_invalidates_when_materialized_cdr_changes(repository, scoring_engine):
    _engine, calls = scoring_engine
    dataset_id = add_dataset(repository)
    job, _ = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    saved_filters.calculate_saved_filter(repository, job['id'])

    repository.update_dataset_profile(dataset_id, processed_at=local_now_iso())
    refreshed, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    # The same Saved Filter, with its result calculated again.
    assert not reused
    assert refreshed['id'] == job['id']
    saved_filters.calculate_saved_filter(repository, refreshed['id'])

    repository.update_dataset_profile(dataset_id, processed_at=local_now_iso())
    with repository.connection() as connection:
        connection.execute(
            "UPDATE dataset_profiles SET updated_at = '2099-01-01T00:00:00+00:00' WHERE dataset_id = ?",
            (dataset_id,),
        )
    edited, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    assert not reused
    assert edited['id'] == refreshed['id']
    assert len(calls) == 2


def test_scoring_cache_survives_dataset_reordering(repository, scoring_engine):
    _engine, _calls = scoring_engine
    first_id = add_dataset(repository, 'First_NSA_Data.csv')
    second_id = add_dataset(repository, 'Second_NSA_Voice.csv', kind='voice')
    job, _ = saved_filters.save_saved_filter(repository, [first_id, second_id], ['Region'], 'NSA')
    saved_filters.calculate_saved_filter(repository, job['id'])

    id_mapping = repository.reorder_dataset_ids([second_id, first_id])
    assert id_mapping == {first_id: 2, second_id: 1}
    reordered, reused = saved_filters.save_saved_filter(repository, [1, 2], ['Region'], 'NSA')

    assert reused
    assert reordered['id'] == job['id']
    assert reordered['dataset_ids'] == [2, 1]


def test_database_management_row_edits_invalidate_the_scoring_cache(repository, scoring_engine):
    _engine, _calls = scoring_engine
    dataset_id = add_dataset(repository)
    job, _ = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    saved_filters.calculate_saved_filter(repository, job['id'])

    repository.update_database_table_row(
        repository.dataset_rows_table_name(dataset_id), 1, {'score': 99.0},
    )
    edited, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')

    assert not reused
    assert edited['id'] == job['id'] and edited['status'] == 'queued'


@pytest.mark.parametrize(
    ('ids', 'mode', 'levels', 'expected_error'),
    [
        ([], 'NSA', ['Region'], 'Select at least one'),
        ([1], 'SA', ['Region'], 'does not match'),
        ([1], 'NSA', ['Unknown Dimension'], 'not available'),
    ],
)
def test_scoring_job_validates_cdr_mode_and_levels(repository, scoring_engine, ids, mode, levels, expected_error):
    _engine, _calls = scoring_engine
    add_dataset(repository)
    with pytest.raises(ValueError, match=expected_error):
        saved_filters.save_saved_filter(repository, ids, levels, mode)


def test_saved_filters_are_visible_and_interrupted_jobs_become_retryable(repository, scoring_engine):
    _engine, _calls = scoring_engine
    dataset_id = add_dataset(repository)
    job, _ = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')

    assert 'saved_filters' in repository.list_database_tables()
    interrupted_datasets, interrupted_reports = repository.fail_interrupted_background_jobs(fail_datasets=False)

    assert interrupted_datasets == []
    assert interrupted_reports == []
    recovered = saved_filters.get_saved_filter(repository, job['id'])
    assert recovered['status'] == 'failed'
    assert 'application restarted' in recovered['error']


def test_recover_interrupted_saved_filters_on_workspace_reopen(repository, scoring_engine):
    _engine, _calls = scoring_engine
    dataset_id = add_dataset(repository)

    completed_job, _ = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    saved_filters.calculate_saved_filter(repository, completed_job['id'])
    completed_before = saved_filters.get_saved_filter(
        repository, completed_job['id'], include_result=True,
    )

    queued_job, _ = saved_filters.save_saved_filter(repository, [dataset_id], ['City'], 'NSA')
    processing_job, _ = saved_filters.save_saved_filter(
        repository, [dataset_id], ['Vendor'], 'NSA', baseline_operator='O2',
    )
    with repository.connection() as connection:
        connection.execute(
            "UPDATE saved_filters SET status = 'processing', progress = 45 WHERE id = ?",
            (processing_job['id'],),
        )

    reopened_repository = Repository(Path(repository.db_path))
    reopened_repository.initialize()
    recovered_ids = saved_filters.recover_interrupted_saved_filters(reopened_repository)

    assert recovered_ids == sorted([queued_job['id'], processing_job['id']])
    for job_id in recovered_ids:
        recovered = saved_filters.get_saved_filter(reopened_repository, job_id)
        assert recovered['status'] == 'failed'
        assert 'application restarted' in recovered['error']

    completed_after = saved_filters.get_saved_filter(
        reopened_repository, completed_job['id'], include_result=True,
    )
    assert completed_after == completed_before
    assert saved_filters.recover_interrupted_saved_filters(reopened_repository) == []


LEGACY_SCORING_JOBS_DDL = """CREATE TABLE scoring_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT NOT NULL,
    method_version TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    dataset_ids_json TEXT NOT NULL DEFAULT '[]',
    source_metadata_json TEXT NOT NULL DEFAULT '[]',
    nr_mode TEXT NOT NULL,
    levels_json TEXT NOT NULL DEFAULT '[]',
    baseline_operator TEXT NOT NULL DEFAULT 'EE',
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued', 'processing', 'completed', 'failed', 'stopped', 'ready')),
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    last_error TEXT,
    created_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
)"""


def test_initialize_turns_the_scoring_jobs_of_earlier_versions_into_saved_filters(repository):
    result_json = '{"scoring":[{"Operator":"EE","Score":4}],"gap":[],"charts":[],"warnings":[]}'
    snapshot = '{"sources":[{"name":"Q2 CDR"}],"scoring_profile_id":"default","context_filters":{"Region":["North"]}}'

    def job(job_id, cache_key, status, created_at, result=None, dataset_ids='[3,5]', levels='["Region"]'):
        return {'id': job_id, 'cache_key': cache_key, 'method_version': 'method-v1', 'source_fingerprint': 'source',
                'dataset_ids_json': dataset_ids, 'source_metadata_json': snapshot, 'nr_mode': 'NSA',
                'levels_json': levels, 'baseline_operator': 'O2', 'status': status, 'progress': 100,
                'message': 'Saved', 'result_json': result, 'last_error': None, 'created_by': 'tester',
                'created_at': created_at, 'started_at': created_at, 'updated_at': created_at, 'finished_at': created_at}

    legacy_jobs = [
        # Two calculations of the same selection: one Saved Filter with the latest result, used twice.
        job(7, 'old-key', 'ready', '2026-09-29T10:00:00+00:00', result_json),
        job(9, 'new-key', 'completed', '2026-09-30T10:00:00+00:00', result_json.replace('4', '5')),
        # A calculation interrupted by the upgrade is kept as failed.
        job(11, 'other-key', 'processing', '2026-09-29T11:00:00+00:00', dataset_ids='[9]', levels='["City"]'),
    ]
    with repository.connection() as connection:
        connection.execute(LEGACY_SCORING_JOBS_DDL)
        columns = list(legacy_jobs[0])
        for legacy in legacy_jobs:
            connection.execute(
                f'INSERT INTO scoring_jobs ({", ".join(columns)}) VALUES ({", ".join("?" for _ in columns)})',
                [legacy[column] for column in columns],
            )

    repository.initialize()

    with repository.connection() as connection:
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'scoring_jobs'").fetchone() is None
    converted = {item['dataset_ids'][0]: item for item in saved_filters.list_saved_filters(repository)}
    assert len(converted) == 2
    merged = converted[3]
    assert merged['use_count'] == 2 and merged['last_used_at'] == '2026-09-30T10:00:00+00:00'
    assert merged['calculation_count'] == 2
    assert merged['status'] == 'completed' and merged['result_key'] == 'new-key'
    assert saved_filters.get_saved_filter(repository, merged['id'], include_result=True)['result']['scoring'] == [
        {'Operator': 'EE', 'Score': 5}]
    assert merged['context_filters']['Region'] == ['North'] and merged['scoring_profile_id'] == 'default'
    assert converted[9]['status'] == 'failed' and converted[9]['use_count'] == 1 and converted[9]['calculation_count'] == 0

    # A second start finds nothing to convert.
    repository.initialize()
    assert len(saved_filters.list_saved_filters(repository)) == 2


def test_workspace_database_backup_restore_keeps_completed_scoring_results(client, tmp_path: Path, scoring_engine):
    import src.DriveTestAnalyzer as app_module

    _engine, _calls = scoring_engine
    workspace = app_module.active_workspace
    assert workspace is not None
    app_module.repository.replace_scoring_configuration(scoring_configuration())
    dataset_id = add_dataset(app_module.repository, 'Backup_NSA_Data.csv')
    job, _ = saved_filters.save_saved_filter(
        app_module.repository, [dataset_id], ['Region'], 'NSA', username='tester',
    )
    completed = saved_filters.calculate_saved_filter(app_module.repository, job['id'])
    assert completed['status'] == 'completed'

    backup_path = app_module.create_recurring_database_backup({
        'components': ['workspace_database'],
        'workspace_ids': [workspace.id],
        'backup_path': str(tmp_path / 'scoring-backups'),
        'max_backups': 2,
    })
    with app_module.repository.connection() as connection:
        connection.execute('DELETE FROM saved_filters WHERE id = ?', (job['id'],))
    assert saved_filters.get_saved_filter(app_module.repository, job['id']) is None

    app_module.restore_database_backup(backup_path, ['workspace_database'])

    restored = saved_filters.get_saved_filter(app_module.repository, job['id'], include_result=True)
    assert restored is not None
    assert restored['status'] == 'completed'
    assert restored['result']['scoring'] == completed['result']['scoring']


def test_historical_jobs_use_current_environment_labels_without_rewriting_snapshots(repository, scoring_engine):
    dataset_id = add_dataset(repository)
    created, _ = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    saved_filters.calculate_saved_filter(repository, created['id'])
    original = saved_filters.get_saved_filter(repository, created['id'], include_result=True)
    configuration = repository.get_scoring_configuration()
    scope = configuration['scope']
    scope['environments']['Drive - City'] = scope['environments'].pop('DriveCity')
    scope['environments']['Drive - City']['display_name'] = 'Drive - City'
    for metric in configuration['metrics']:
        metric['contexts']['Drive - City'] = metric['contexts'].pop('DriveCity')
    repository.replace_scoring_configuration(configuration)

    displayed = saved_filters.get_saved_filter(repository, created['id'], include_result=True)
    assert displayed['configuration']['scope']['environments']['DriveCity']['display_name'] == 'Drive - City'
    assert displayed['result']['configuration']['scope']['environments']['DriveCity']['display_name'] == 'Drive - City'
    assert displayed['result']['scoring'] == original['result']['scoring']
    assert displayed['configuration']['metrics'] == original['configuration']['metrics']
    stored = saved_filters.get_saved_filter(repository, created['id'], include_result=True,
                                           include_internal_snapshot=True)
    assert stored['configuration'] == original['configuration']
    assert stored['result'] == original['result']
    new, reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region'], 'NSA')
    assert not reused
    assert 'Drive - City' in new['configuration']['scope']['environments']


def test_failed_calculations_are_written_to_the_app_logs(repository, scoring_engine):
    engine, _calls = scoring_engine

    def failing(*_args, **_kwargs):
        raise ValueError('side location conflict')

    engine.calculate_scoring = failing
    dataset_id = add_dataset(repository)
    job, _ = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')
    assert saved_filters.calculate_saved_filter(repository, job['id'])['status'] == 'failed'
    entry = next(row for row in repository.list_logs() if row['action'] == 'scoring_calculation_failed')
    details = json.loads(entry['details'])
    assert details['filter_id'] == job['id'] and details['error'] == 'ValueError: side location conflict'
    assert 'failing' in details['location']


@pytest.mark.parametrize('earlier, key_column', [('scoring_previous_filters', 'filter_key'), ('saved_scorings', 'selection_key')])
def test_initialize_keeps_the_saved_filters_of_a_workspace_opened_with_their_earlier_names(repository, earlier, key_column):
    with repository.connection() as connection:
        ddl = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'saved_filters'").fetchone()['sql']
        connection.execute('DROP TABLE saved_filters')
        connection.execute(ddl.replace('saved_filters', earlier).replace('selection_key', key_column))
        connection.execute(f'CREATE INDEX idx_{earlier}_order ON {earlier}(pinned DESC, last_used_at DESC)')
        connection.execute(f"INSERT INTO {earlier} ({key_column}, name, nr_mode, status) VALUES ('selection', 'Kept', 'NSA', 'completed')")

    repository.initialize()

    [kept] = saved_filters.list_saved_filters(repository)
    assert kept['name'] == 'Kept' and kept['selection_key'] == 'selection' and kept['status'] == 'completed'
    with repository.connection() as connection:
        names = {row['name'] for row in connection.execute('SELECT name FROM sqlite_master').fetchall()}
    assert earlier not in names and f'idx_{earlier}_order' not in names and 'idx_saved_filters_order' in names


def test_saved_filters_count_their_uses_and_their_calculations(repository, scoring_engine):
    dataset_id = add_dataset(repository)
    saved, _ = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')
    assert (saved['use_count'], saved['calculation_count']) == (1, 0)
    saved_filters.calculate_saved_filter(repository, saved['id'])
    # Calculate with its result up to date opens it: a use, not a calculation.
    opened, reused = saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA')
    assert reused and (opened['use_count'], opened['calculation_count']) == (2, 1)
    # Recalculate is a use and, once it finishes, a calculation.
    saved_filters.save_saved_filter(repository, [dataset_id], [], 'NSA', force=True)
    recalculated = saved_filters.calculate_saved_filter(repository, saved['id'])
    assert (recalculated['use_count'], recalculated['calculation_count']) == (3, 2)
    # Opening it from its card is a use.
    assert saved_filters.mark_saved_filter_used(repository, saved['id'])['use_count'] == 4


def test_saved_filters_of_earlier_versions_get_their_calculation_count(repository):
    with repository.connection() as connection:
        connection.execute("INSERT INTO saved_filters (selection_key, nr_mode, status) VALUES ('done', 'NSA', 'completed')")
        connection.execute("INSERT INTO saved_filters (selection_key, nr_mode, status) VALUES ('waiting', 'NSA', 'saved')")
        connection.execute('ALTER TABLE saved_filters DROP COLUMN calculation_count')
    repository.initialize()
    counts = {item['selection_key']: item['calculation_count'] for item in saved_filters.list_saved_filters(repository)}
    assert counts == {'done': 1, 'waiting': 0}


def test_only_starred_saved_filters_are_kept_when_another_one_is_used(repository, scoring_engine):
    dataset_id = add_dataset(repository)

    def calculated(levels, username='ana'):
        saved, _reused = saved_filters.save_saved_filter(repository, [dataset_id], levels, 'NSA', username=username)
        saved_filters.calculate_saved_filter(repository, saved['id'])
        return saved['id']

    starred = calculated(['Region'])
    saved_filters.update_saved_filter(repository, starred, pinned=True)
    unstarred = calculated(['City'])
    drawing = calculated(['Vendor'])
    someone_else = calculated(['Region', 'City'], username='bob')
    queued, _reused = saved_filters.save_saved_filter(repository, [dataset_id], ['Region', 'Vendor'], 'NSA',
                                                      username='ana')
    current = calculated(['City', 'Vendor'])
    saved_filters._points_loss_jobs[saved_filters._points_loss_key(repository.db_path, drawing)] = {'status': 'queued'}
    try:
        removed = saved_filters.prune_unpinned_saved_filters(repository, current, 'ana')
    finally:
        saved_filters._points_loss_jobs.clear()
    # The unstarred one goes; the starred, the one in use, those still calculating or drawing their map and those of
    # other users stay.
    assert removed == [unstarred]
    assert {item['id'] for item in saved_filters.list_saved_filters(repository)} == {
        starred, drawing, someone_else, queued['id'], current}
