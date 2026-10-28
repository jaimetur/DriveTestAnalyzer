"""Scoring History: the KPI components of every CDR per day and area, and the scoring calculated from them."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd
import pytest

from src.modules import saved_filters, scoring, scoring_history
from src.modules.repository import Repository, local_now_iso
from tests.scoring_fixtures import load_initial_scoring_configuration

OPERATORS = ('EE', 'Vodafone UK', 'Three UK')
PLACES = (('London', 'South', 'C1'), ('Leeds', 'North', 'C2'), ('Glasgow', 'North', 'C3'))
DAYS = ('2026-07-06 10:00:00', '2026-07-07 11:00:00', '2026-07-15 09:30:00')
# Medians and 90th percentiles come from sketches, within a quarter of a percent.
APPROXIMATE = {'K20', 'K25', 'K32'}


def _base(generator, operator, place, day):
    city, region, cluster = place
    return {'Operator': operator, 'Campaign': '2026-Q3', 'G_Level_1': 'Drive',
            'G_Level_2': generator.choice(['City', 'Connectionroad']), 'City': city, 'Region': region,
            'Cluster': cluster, 'Vendor': generator.choice(['Nokia', 'Ericsson']), 'Event_Start_Time': day}


def _rows(kind: str, seed: int = 3) -> pd.DataFrame:
    generator = random.Random(seed)
    rows = []
    for operator in OPERATORS:
        for place in PLACES:
            for day in DAYS:
                for _ in range(12):
                    row = _base(generator, operator, place, day)
                    if kind == 'voice':
                        row.update({'Session_Type': generator.choice(['CALL', 'MultiRAB CALL', 'WhatsApp CALL']),
                                    'Call_Status': generator.choice(['Completed'] * 8 + ['Dropped', 'Failed']),
                                    'Call_Setup_Time': round(generator.uniform(1, 14), 2),
                                    'Disturbed_and_Impaired_Call': generator.choice(['Yes', None, None]),
                                    'Test_Status': generator.choice(['Successful', 'Failed'])})
                    elif kind == 'speech':
                        row.update({'Session_Type': generator.choice(['CALL', 'MultiRAB CALL', 'WhatsApp CALL']),
                                    'LQ': generator.choice([None, round(generator.uniform(1, 4.8), 2)])})
                    else:
                        test = generator.choice(['FDFS DL', 'FDFS UL', 'FDTT DL', 'UDP UL', 'httpBrowser',
                                                 'VideoStreaming', 'Interactivity'])
                        row.update({'Test_Result': generator.choice(['Completed'] * 5 + ['Failed'])})
                        if test.startswith(('FDFS', 'FDTT', 'UDP')):
                            row.update({'Test_Name': test, 'Transfer_Duration': round(generator.uniform(1, 20), 2),
                                        'Mean_Data_Rate': round(generator.uniform(1, 800), 2)})
                        elif test == 'httpBrowser':
                            row.update({'Type_of_Test': test, 'http_Browser_Transferred_Bytes': generator.choice([10, 1000000]),
                                        'http_Browser_1MB_Reached_Duration': generator.randint(500, 9000)})
                        elif test == 'VideoStreaming':
                            row.update({'Type_of_Test': test, 'VideoStream_Time_to_First_Picture': generator.randint(1, 20),
                                        'Irritating_Video_Playout': generator.choice(['No', None])})
                        else:
                            row.update({'Type_of_Test': test, 'Packets_Lost': generator.randint(0, 3),
                                        'Packets_Discarded': generator.choice([None, 1]), 'Packets_Corrupted': 1.5,
                                        'Packets_Not_Sent': 0, 'Packets_Sent': 100,
                                        'Interactivity_RTT_Median': round(generator.uniform(15, 80), 1)})
                    rows.append(row)
    return pd.DataFrame(rows)


def _add_cdr(repository: Repository, tmp_path: Path, kind: str, name: str | None = None) -> int:
    name = name or f'NetCheck_UK_CDR_{kind.title()}_2026_Q3.xlsx'
    frame = _rows(kind)
    source = tmp_path / name
    source.write_text(f'{kind} source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'super')
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA',
                                      row_count=len(frame), column_count=len(frame.columns), processed_at=local_now_iso())
    return dataset_id


@pytest.fixture
def history_repository(tmp_path):
    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'global.db')
    repository.initialize()
    repository.replace_scoring_configuration(load_initial_scoring_configuration())
    ids = [_add_cdr(repository, tmp_path, kind) for kind in ('data', 'voice', 'speech')]
    return repository, ids, repository.get_scoring_profile()['configuration']


def _by_rows(repository, ids, levels, configuration, context_filters=None, time_split=None):
    sources, _campaigns, _fingerprint = saved_filters._source_snapshot(repository, ids)
    for source in sources:
        source['levels'] = [*levels, *(scoring.START_TIME_COLUMNS if time_split else ())]
    frames = saved_filters._load_source_frames(repository, sources, lambda *args: None, scoring.load_input_columns,
                                              context_filters or {})
    return scoring.calculate_scoring(frames, levels, baseline_operator='EE', configuration=configuration,
                                     time_split=time_split)


def _assert_same(rows_result, history_result):
    for part, fields in (('scoring', ('value', 'sample_count', 'weighted_points')), ('global_kpis', ('value', 'sample_count')),
                         ('totals', ('weighted_points', 'max_points'))):
        def key(row):
            return tuple(sorted((name, str(value)) for name, value in row.items()
                                if name in {'campaign', 'operator', 'vendor', 'region', 'cluster', 'city', 'environment',
                                            'kpi_code', 'category', 'dataset_type'}))
        left = {key(row): row for row in rows_result[part]}
        right = {key(row): row for row in history_result[part]}
        assert set(left) == set(right), part
        for row_key, row in left.items():
            approximate = row.get('kpi_code') in APPROXIMATE or part == 'totals'
            for field in fields:
                expected, actual = row.get(field), right[row_key].get(field)
                if expected is None or actual is None:
                    assert expected is None and actual is None, (part, field, row_key)
                elif field == 'value' and approximate:
                    assert actual == pytest.approx(expected, rel=0.01), (part, field, row_key)
                elif field == 'weighted_points' and approximate:
                    assert actual == pytest.approx(expected, abs=1.5), (part, field, row_key)
                else:
                    assert actual == pytest.approx(expected, rel=1e-9, abs=1e-9), (part, field, row_key)
    assert sorted(rows_result['warnings']) == sorted(history_result['warnings'])


def test_sketches_give_medians_and_percentiles_within_a_quarter_of_a_percent():
    generator = random.Random(5)
    values = pd.Series([generator.uniform(0.5, 900) for _ in range(500)] + [0.0, 0.0])
    sketch = {}
    for key in scoring_history._sketch_keys(values):
        sketch[key] = sketch.get(key, 0) + 1
    for quantile in (0.5, 0.9):
        assert scoring_history._sketch_quantile(sketch, quantile) == pytest.approx(values.quantile(quantile), rel=0.0025)


@pytest.mark.parametrize('levels, context_filters, time_split', [
    (['Operator', 'Campaign'], None, None),
    (['Operator', 'Vendor', 'Campaign'], None, None),
    (['Operator', 'Region', 'Cluster'], None, None),
    (['Operator', 'City'], {'City': ['London', 'leeds']}, None),
    (['Operator', 'Campaign'], {'Region': ['North']}, 'Weekly'),
    (['Operator', 'Campaign'], None, 'Daily'),
    (['Operator', 'Dataset Type'], None, None),
])
def test_the_history_scores_as_the_rows_of_the_cdrs(history_repository, levels, context_filters, time_split):
    repository, ids, configuration = history_repository
    assert scoring_history.sync_history(repository) == {'indexed': 3}
    assert scoring_history.history_covers(repository, ids, levels, configuration, context_filters or {})
    by_rows = _by_rows(repository, ids, levels, configuration, context_filters, time_split)
    from_history = scoring_history.calculate_scoring_from_history(
        repository, ids, levels, configuration=configuration, context_filters=context_filters, time_split=time_split)
    assert by_rows['scoring'] and from_history['source'] == 'history'
    _assert_same(by_rows, from_history)


def test_a_cdr_is_identified_by_its_file_and_processing_not_its_name(history_repository, tmp_path):
    repository, ids, configuration = history_repository
    scoring_history.sync_history(repository)
    data_id = ids[0]
    # A new name keeps the history: the CDR is identified by the SHA-256 of its file.
    with repository.connection() as connection:
        connection.execute('UPDATE datasets SET file_name = ? WHERE id = ?', ('Renamed data CDR.xlsx', data_id))
    changed, _metrics = scoring_history.history_changes(repository)
    assert changed == []
    # Processing it again replaces the history of its former processing.
    with repository.connection() as connection:
        old_keys = {row[0] for row in connection.execute('SELECT source_key FROM scoring_history_sources').fetchall()}
    repository.update_dataset_profile(data_id, processed_at=local_now_iso() + 'x')
    assert scoring_history.sync_history(repository) == {'indexed': 1}
    with repository.connection() as connection:
        keys = {row[0] for row in connection.execute('SELECT source_key FROM scoring_history_sources').fetchall()}
        sources = connection.execute('SELECT COUNT(*) FROM scoring_history_sources').fetchone()[0]
    assert sources == 3 and len(keys - old_keys) == 1
    # A deleted CDR keeps its history.
    repository.delete_dataset(ids[2])
    scoring_history.sync_history(repository)
    with repository.connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM scoring_history_sources').fetchone()[0] == 3
    # A split the history does not keep reads the rows of the CDRs.
    assert not scoring_history.history_covers(repository, ids[:2], ['Operator', 'Unknown level'], configuration)


def test_a_job_is_calculated_from_the_history_and_gets_its_points_lost_map(history_repository):
    repository, ids, _configuration = history_repository
    scoring_history.sync_history(repository)
    job, cached = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA')
    assert not cached
    finished = saved_filters.calculate_saved_filter(repository, job['id'])
    assert finished['status'] == 'completed'
    result = finished['result']
    assert result['source'] == 'history' and result['scoring']
    # The Points Lost Map is added from the rows of the tests once the scores are saved.
    assert 'pending' not in result['points_loss'] and 'shares' in result['points_loss']
    assert finished['message'] == 'Scoring tables, GAP analysis and Points Lost Map are ready'
    # Without the history the same job reads the rows, with the same scores.
    by_rows = _by_rows(repository, ids, ['Operator', 'Campaign'], result['configuration'])
    _assert_same(by_rows, result)


def test_the_points_lost_map_of_a_result_from_the_history_is_a_job_of_its_own(history_repository):
    repository, ids, _configuration = history_repository
    scoring_history.sync_history(repository)
    saved, _cached = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA')
    submitted = []
    finished = saved_filters.calculate_saved_filter(repository, saved['id'], submitted.append)
    # The scores are ready at once; the map waits in its own job, shown among the background tasks.
    assert finished['status'] == 'completed' and finished['result']['points_loss'] == {'version': 2, 'pending': True}
    [task] = saved_filters.points_loss_tasks(repository.db_path)
    assert task['label'] == f"Points Lost Map #{saved['id']}" and task['status'] == 'queued'
    [job] = submitted
    assert saved_filters.is_saved_filter_work(job, (), saved['id']) and not saved_filters.is_saved_filter_work(job, (), 0)
    job()
    result = saved_filters.get_saved_filter(repository, saved['id'], include_result=True)['result']
    assert 'pending' not in result['points_loss'] and 'shares' in result['points_loss']
    assert saved_filters.points_loss_tasks(repository.db_path) == []


def test_queued_work_of_the_saved_filter_being_looked_at_goes_first():
    from threading import Event
    from src.modules.background_scheduler import BackgroundTaskScheduler

    scheduler = BackgroundTaskScheduler(max_workers=1)
    release, order = Event(), []
    scheduler.submit_ordered(release.wait, workspace_key='w', priority=(0, 0))
    futures = [scheduler.submit_ordered(order.append, name, workspace_key='w', priority=(4, 0, 0))
               for name in ('first', 'second', 'selected')]
    assert scheduler.promote(lambda _callback, args: args == ('selected',), (4, -1, -1)) == 1
    release.set()
    for future in futures:
        future.result(timeout=5)
    scheduler.shutdown()
    assert order == ['selected', 'first', 'second']


def test_a_city_without_measurements_in_the_filtered_campaigns_is_left_out_of_the_area_summary(history_repository):
    repository, ids, configuration = history_repository
    scoring_history.sync_history(repository)
    filters = {'Campaign': ['2026-Q3']}
    # A city of the area summary the filtered campaigns never measured gives no rows instead of failing the scoring.
    result = scoring_history.calculate_scoring_from_history(repository, ids, ['Operator'], configuration=configuration,
                                                            context_filters=filters, cities=['Madrid'])
    assert result['scoring'] == []
    from src.modules.scoring_area_summary import calculate_area_summary_from_history

    def calculate(levels, *, time_split=None, cities=None):
        return scoring_history.calculate_scoring_from_history(repository, ids, levels, configuration=configuration,
                                                              context_filters=filters, time_split=time_split, cities=cities)
    summary = calculate_area_summary_from_history(
        calculate, ['Operator'], {'breakdown': 'Region', 'cities': ['Madrid'], 'time_split': 'Monthly'})
    assert 'National & Geographical Areas Trends: the selected CDRs have no Madrid measurements.' in summary['warnings']
    # A filter that leaves a CDR type without rows still fails the scoring.
    with pytest.raises(ValueError, match='no matching processed rows'):
        scoring_history.calculate_scoring_from_history(repository, ids, ['Operator'], configuration=configuration,
                                                       context_filters={'Campaign': ['2025-Q1']})


def test_the_points_lost_map_job_reports_its_step_and_progress(history_repository, monkeypatch):
    repository, ids, _configuration = history_repository
    scoring_history.sync_history(repository)
    saved, _cached = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA')
    submitted = []
    saved_filters.calculate_saved_filter(repository, saved['id'], submitted.append)
    reports = []
    complete = saved_filters._complete_points_loss

    def recorded(*args, **kwargs):
        report = args[-1]
        return complete(*args[:-1], lambda value, step: (reports.append((value, step)), report(value, step)))
    monkeypatch.setattr(saved_filters, '_complete_points_loss', recorded)
    [job] = submitted
    job()
    values = [value for value, _step in reports]
    steps = [step for _value, step in reports]
    # The CDRs read, then the KPIs mapped CDR type by CDR type, then the boundaries and the save.
    assert steps[0] == f'Reading the rows of the tests: CDR 1 of {len(ids)}'
    assert any(step.startswith('Mapping the Data tests: KPI 1 of ') for step in steps)
    assert steps[-2:] == ['Adding the area boundaries', 'Saving the map']
    assert values == sorted(values) and values[-1] == 99


def _points_loss_inputs_of(repository, ids):
    saved, _cached = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA')
    saved_filter = saved_filters.get_saved_filter(repository, saved['id'], include_internal_snapshot=True)
    sources, _campaigns, _fingerprint = saved_filters._source_snapshot(repository, ids, expected_nr_mode='NSA')
    configuration = saved_filters.validate_scoring_configuration(saved_filter['configuration'])
    return saved_filter, sources, configuration, saved_filter.get('context_filters', {})


def test_the_points_lost_map_drawn_apart_is_the_one_drawn_in_the_application(history_repository):
    repository, ids, _configuration = history_repository
    saved_filter, sources, configuration, filters = _points_loss_inputs_of(repository, ids)
    steps = []
    apart = saved_filters._draw_points_loss_apart(repository, saved_filter, [dict(source) for source in sources],
                                                  configuration, filters, lambda value, step: steps.append(step))
    here = saved_filters.draw_points_loss(repository, saved_filter, [dict(source) for source in sources], configuration,
                                          filters, saved_filters._scoring_engine())
    assert saved_filters._serialize_result_value(apart) == saved_filters._serialize_result_value(here)
    assert apart['shares'] and any(step.startswith('Mapping the Data tests: KPI ') for step in steps)


def test_the_points_lost_map_reads_each_cdr_type_from_the_copies_with_the_same_rows_and_map(history_repository):
    from src.modules import cdr_store

    repository, ids, _configuration = history_repository
    assert cdr_store.start_store_sync(repository, lambda run: run(), lambda: cdr_store.included_cdrs(repository))['status'] == 'ready'
    saved_filter, sources, configuration, filters = _points_loss_inputs_of(repository, ids)
    for source in sources:
        source['levels'] = list(saved_filter['levels'])
    by_rows = saved_filters._load_source_frames(repository, [dict(source) for source in sources], lambda *args: None,
                                                scoring.load_input_columns, filters)
    by_type = saved_filters._load_source_frames(repository, [dict(source) for source in sources], lambda *args: None,
                                                scoring.load_input_columns, filters, columnar=True)
    # The same rows and values, the text as Categoricals.
    assert set(by_type) == set(by_rows)
    assert any(isinstance(dtype, pd.CategoricalDtype) for frame in by_type.values() for dtype in frame.dtypes)
    for kind, frame in by_rows.items():
        assert list(by_type[kind].columns) == list(frame.columns)
        for column in frame.columns:
            expected, actual = frame[column], by_type[kind][column]
            if isinstance(actual.dtype, pd.CategoricalDtype):
                actual, expected = actual.astype(object).where(actual.notna(), None), expected.where(expected.notna(), None)
            pd.testing.assert_series_equal(actual, expected, check_exact=True)
    options = saved_filters._engine_kwargs(repository, saved_filter, configuration, scoring.calculate_scoring)
    expected = scoring.calculate_points_loss(by_rows, saved_filter['levels'], configuration=configuration,
                                             operator_mappings=options.get('operator_mappings'),
                                             map_areas=options.get('map_areas'))
    drawn = saved_filters.draw_points_loss(repository, saved_filter, [dict(source) for source in sources], configuration,
                                           filters, scoring)
    assert saved_filters._serialize_result_value(drawn) == saved_filters._serialize_result_value(expected)
    assert drawn['shares']


def test_stopping_the_points_lost_map_ends_its_process_at_once(history_repository, monkeypatch):
    import subprocess

    repository, ids, _configuration = history_repository
    saved_filter, sources, configuration, filters = _points_loss_inputs_of(repository, ids)
    processes = []
    popen = subprocess.Popen

    def recorded(*args, **kwargs):
        processes.append(popen(*args, **kwargs))
        return processes[-1]
    monkeypatch.setattr(subprocess, 'Popen', recorded)

    def stop(_value, _step):
        raise saved_filters._MapStopped()
    with pytest.raises(saved_filters._MapStopped):
        saved_filters._draw_points_loss_apart(repository, saved_filter, sources, configuration, filters, stop)
    [process] = processes
    assert process.poll() is not None


def test_a_stopped_points_lost_map_keeps_the_scores_and_is_drawn_again_when_resumed(history_repository):
    repository, ids, _configuration = history_repository
    scoring_history.sync_history(repository)
    saved, _cached = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA')
    submitted = []
    saved_filters.calculate_saved_filter(repository, saved['id'], submitted.append)
    [job] = submitted
    # A user stops the map from its card before it is drawn.
    assert saved_filters.request_points_loss_stop(repository.db_path, saved['id'])
    job()
    stopped = saved_filters.get_saved_filter(repository, saved['id'], include_result=True)
    assert stopped['result']['points_loss'] == {'version': 2, 'error': saved_filters.POINTS_LOSS_STOPPED}
    assert stopped['result']['scoring'] and saved_filters.stopped_points_loss_ids(repository) == [saved['id']]
    # Once the application is idle it is drawn again.
    assert saved_filters.resume_stopped_points_loss(repository, saved['id'])
    assert saved_filters.stopped_points_loss_ids(repository) == []
    resumed = []
    saved_filters.queue_points_loss(repository, saved['id'], resumed.append)
    [job] = resumed
    job()
    drawn = saved_filters.get_saved_filter(repository, saved['id'], include_result=True)
    assert drawn['result']['points_loss']['shares'] and not saved_filters.resume_stopped_points_loss(repository, saved['id'])


def test_the_points_lost_map_task_shows_its_progress_and_the_time_left(monkeypatch):
    key = saved_filters._points_loss_key('/tmp/progress-workspace.db', 7)
    started = saved_filters.time.time() - 120
    monkeypatch.setitem(saved_filters._points_loss_jobs, key, {
        'status': 'processing', 'queued_at': started, 'started_at': started, 'progress': 40.0,
        'detail': 'Mapping the Voice tests: group 30 of 90'})
    [task] = saved_filters.points_loss_tasks('/tmp/progress-workspace.db')
    # 40% in two minutes: about three more.
    assert task['progress'] == 40.0
    assert task['detail'] == 'Mapping the Voice tests: group 30 of 90 · about 3 min left'


def test_saved_filters_reuse_the_points_lost_maps_and_trends_of_the_same_cdrs_and_methodology(history_repository, monkeypatch):
    from src.modules import scoring_cache

    repository, ids, _configuration = history_repository
    scoring_history.sync_history(repository)
    written = []
    write = scoring_cache.write
    monkeypatch.setattr(scoring_cache, 'write', lambda repo, kind, key, value: (written.append(kind), write(repo, kind, key, value)))
    area = {'breakdown': 'Region', 'cities': ['London'], 'time_split': 'Campaign', 'campaigns': ['@all-campaigns']}

    submitted = []

    def calculated(**options):
        saved, _cached = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA', area_summary=area, **options)
        written.clear()
        submitted.clear()
        result = saved_filters.calculate_saved_filter(repository, saved['id'], submitted.append)['result']
        for job in submitted:
            job()
        return saved_filters.get_saved_filter(repository, saved['id'], include_result=True)['result'] if submitted else result

    national = calculated()
    assert sorted(written) == ['points-loss', 'trends'] and 'shares' in national['points_loss'] and len(submitted) == 1
    # Another GAP reference: the same map (which does not depend on it), at once without a job of its own, and new trends.
    other_reference = calculated(baseline_operator='Vodafone UK')
    assert written == ['trends'] and submitted == [] and other_reference['points_loss'] == national['points_loss']
    # A Region filter: the trends of the whole country, as those of the first one, and a map of its own.
    north = calculated(context_filters={'Region': ['North']})
    assert written == ['points-loss'] and north['area_summary'] == national['area_summary']
    assert north['points_loss'] != national['points_loss']


def test_rows_are_read_only_from_the_cdrs_of_the_chosen_campaigns():
    sources = [{'metadata': {'campaigns': ['UK_Q2_2026']}}, {'metadata': {'campaigns': ['UK_Q3_2026']}}, {'metadata': {'campaigns': []}}]
    assert saved_filters._campaign_sources(sources, {'Campaign': ['2026-Q3']}) == sources[1:]
    assert saved_filters._campaign_sources(sources, {'Campaign': []}) == sources


def test_a_running_job_sees_the_work_of_its_workspace_waiting_before_it():
    from threading import Event
    from src.modules.background_scheduler import BackgroundTaskScheduler

    scheduler = BackgroundTaskScheduler(max_workers=1)
    started, release, seen = Event(), Event(), []

    def map_job():
        started.set()
        release.wait()
        seen.append((scheduler.current_priority(), scheduler.has_waiting_before('w', scheduler.current_priority())))

    done = scheduler.submit_ordered(map_job, workspace_key='w', priority=(5, 0, 0))
    assert started.wait(5) and scheduler.current_priority() is None
    later = scheduler.submit_ordered(lambda: None, workspace_key='w', priority=(5, 0, 0))
    other_workspace = scheduler.submit_ordered(lambda: None, workspace_key='x', priority=(4, 0, 0))
    calculation = scheduler.submit_ordered(lambda: None, workspace_key='w', priority=(4, 0, 0))
    release.set()
    for future in (done, later, other_workspace, calculation):
        future.result(timeout=5)
    scheduler.shutdown()
    # Only the calculation of its own workspace waits before the map (not another map, nor another workspace).
    assert seen == [((5, 0, 0), True)]


def test_a_points_lost_map_gives_way_to_the_work_waiting_and_goes_on_later(history_repository):
    repository, ids, _configuration = history_repository
    scoring_history.sync_history(repository)
    saved, _cached = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA')
    submitted, waiting = [], [True]
    saved_filters.calculate_saved_filter(repository, saved['id'], submitted.append, lambda: waiting[0])
    # Another calculation waits: the map gives way at its first step and is queued again, still pending.
    submitted.pop()()
    assert len(submitted) == 1 and saved_filters.points_loss_tasks(repository.db_path)[0]['status'] == 'queued'
    result = saved_filters.get_saved_filter(repository, saved['id'], include_result=True)['result']
    assert result['points_loss'] == {'version': 2, 'pending': True}
    # Once nothing waits, it is drawn.
    waiting[0] = False
    submitted.pop()()
    result = saved_filters.get_saved_filter(repository, saved['id'], include_result=True)['result']
    assert 'shares' in result['points_loss'] and submitted == [] and saved_filters.points_loss_tasks(repository.db_path) == []


def test_the_history_takes_the_operator_patterns_as_the_rows_of_the_cdrs(history_repository):
    repository, ids, configuration = history_repository
    scoring_history.sync_history(repository)
    for filters in ({'Operator': ['Not Three*']}, {'Operator': ['vodafone*', 'EE']}):
        by_rows = _by_rows(repository, ids, ['Operator'], configuration, filters)
        from_history = scoring_history.calculate_scoring_from_history(repository, ids, ['Operator'], configuration=configuration,
                                                                     context_filters=filters)
        assert {row['operator'] for row in from_history['scoring']} == {'EE', 'Vodafone UK'}
        _assert_same(by_rows, from_history)
