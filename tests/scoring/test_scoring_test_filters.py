"""The Test Name and Test Type filters of Scoring & GAP Analysis leave tests out of a scoring (ticket #207)."""
from __future__ import annotations

import pandas as pd

from src.modules.scoring import saved_scorings
from src.modules.scoring.scoring_exports import _canonical_scope_filter_labels
from src.modules.scoring.scoring_selection import _normalize_context_filters as normalize_panel_filters
from src.modules.scoring.scoring_test_filters import scoring_test_filter_options
from tests.scoring.test_saved_scorings import add_dataset, repository, scoring_engine  # noqa: F401

TESTS = {
    'data': {'Test_Name': ['Ping 40', 'Ping 800', 'YouTube', 'YouTube'],
             'Type_of_Test': ['ICMP Ping', 'ICMP Ping', 'VideoStreaming', 'VideoStreaming']},
    # The calls keep in Test_Name the data session of a MultiRAB call.
    'voice': {'Test_Name': ['HTTP DL', None, None, None], 'Type_Of_Test': ['MultiRAB CALL', 'CALL', 'CALL', 'WhatsApp CALL']},
    'speech': {'Test_Name': ['HTTP DL', None, None, None], 'Type_Of_Test': ['MultiRAB CALL', 'CALL', 'CALL', 'WhatsApp CALL']},
}


def _sources(repository) -> list[int]:
    ids = []
    for kind, tests in TESTS.items():
        dataset_id = add_dataset(repository, f'Tests_NSA_{kind.title()}.csv', kind=kind)
        frame = pd.DataFrame({'Operator': ['EE'] * 4, 'Region': ['North'] * 4, 'City': ['Leeds'] * 4,
                              'Campaign': ['2026-Q2'] * 4, 'Dataset_Kind': [kind] * 4, 'score': [1.0, 2.0, 3.0, 4.0], **tests})
        repository.replace_dataset_rows(dataset_id, frame)
        repository.update_dataset_profile(dataset_id, row_count=len(frame), column_count=len(frame.columns))
        ids.append(dataset_id)
    return ids


def _scored(repository, calls, ids, filters) -> dict[str, list[float]]:
    job, _reused = saved_scorings.save_saved_scoring(repository, ids, ['Operator'], 'NSA', context_filters=filters)
    assert saved_scorings.calculate_saved_scoring(repository, job['id'])['status'] == 'completed'
    frames = calls[-1][0]
    return {kind: sorted(frames[kind]['score'].tolist()) if kind in frames else [] for kind in TESTS}


def test_test_name_and_test_type_leave_tests_out_of_the_scoring(repository, scoring_engine):
    _engine, calls = scoring_engine
    ids = _sources(repository)
    # Test Name leaves out Data tests only: the calls and speech samples with HTTP DL (MultiRAB) are scored all the same.
    assert _scored(repository, calls, ids, {'Test_Name': ['-Ping 40', '-Ping 800']}) == {
        'data': [3.0, 4.0], 'voice': [1.0, 2.0, 3.0, 4.0], 'speech': [1.0, 2.0, 3.0, 4.0]}
    # Only some Data tests: the calls are still scored as they are.
    assert _scored(repository, calls, ids, {'Test_Name': ['YouTube']}) == {
        'data': [3.0, 4.0], 'voice': [1.0, 2.0, 3.0, 4.0], 'speech': [1.0, 2.0, 3.0, 4.0]}
    # Test Type is the type of every test: of the Data tests and of the calls (with patterns too).
    assert _scored(repository, calls, ids, {'Test_Type': ['-ICMP*', '-WhatsApp CALL']}) == {
        'data': [3.0, 4.0], 'voice': [1.0, 2.0, 3.0], 'speech': [1.0, 2.0, 3.0]}
    # Each choice is a Saved Scoring of its own, which keeps them.
    saved = saved_scorings.list_saved_scorings(repository)
    assert {tuple(job['context_filters'].get('Test_Type') or []) for job in saved} >= {('-ICMP*', '-WhatsApp CALL')}
    assert len({job['id'] for job in saved}) == 3


def test_the_test_filters_list_every_test_of_the_cdrs_and_are_kept_by_the_panel(repository):
    ids = _sources(repository)
    cdrs = [{'id': dataset_id, 'kind': kind} for dataset_id, kind in zip(ids, TESTS)]
    assert scoring_test_filter_options(repository, cdrs) == {
        'Test_Name': ['Ping 40', 'Ping 800', 'YouTube'],
        'Test_Type': ['CALL', 'ICMP Ping', 'MultiRAB CALL', 'VideoStreaming', 'WhatsApp CALL']}
    # The panel keeps them only when used, and the exports say which tests were left out.
    warnings: list[str] = []
    kept = normalize_panel_filters({'Operator': [], 'Test_Name': ['-Ping 40']}, ['Operator', 'Campaign'], warnings)
    assert kept['Test_Name'] == ['-Ping 40'] and 'Test_Type' not in kept and not warnings
    assert 'Test_Name' not in normalize_panel_filters({'Operator': []}, ['Operator', 'Campaign'], warnings)
    labels = _canonical_scope_filter_labels({'Operator': [], 'Test_Name': ['-Ping 40', '-Ping 800'], 'Test_Type': ['CALL']})
    assert labels[-2:] == ['Test Name: All except Ping 40, Ping 800', 'Test Type: CALL']
