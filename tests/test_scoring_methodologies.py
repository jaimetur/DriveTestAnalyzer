from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from src.modules import saved_filters
from src.modules.repository import Repository, local_now_iso
from src.modules.scoring_config import validate_scoring_profiles
from src.modules.scoring_methodologies import (
    BY_CAMPAIGN, campaign_quarters, check_campaign_overlaps, display_configuration, merge_results, methodology_for, methodology_groups,
    methodology_label, normalize_campaign_range, split_result,
)
from scoring_fixtures import scoring_configuration
from test_saved_filters import scoring_engine  # noqa: F401 - the fake engine fixture


def two_methodologies(earlier: dict | None = None, later: dict | None = None) -> dict:
    first = scoring_configuration()
    second = copy.deepcopy(first)
    extra = copy.deepcopy(second['metrics'][0])
    extra['code'] = 'TIKTOK'
    extra['name'] = 'TikTok'
    second['metrics'].append(extra)
    return validate_scoring_profiles({'active_profile_id': 'netcheck-2026', 'profiles': [
        {'id': 'netcheck-2026', 'name': 'NetCheck 2026', 'configuration': first,
         **({'campaigns': earlier} if earlier else {})},
        {'id': 'netcheck-2026-q3', 'name': 'NetCheck 2026-Q3', 'configuration': second,
         **({'campaigns': later} if later else {})},
    ]})


def test_campaign_ranges_are_validated_and_open_ends_are_kept():
    assert normalize_campaign_range({'from': '2026-Q3', 'to': ''}) == {'from': '2026-Q3', 'to': ''}
    assert normalize_campaign_range({'from': '', 'to': ''}) is None
    with pytest.raises(ValueError, match='year and quarter'):
        normalize_campaign_range({'from': 'Summer'})
    with pytest.raises(ValueError, match='before its last one'):
        normalize_campaign_range({'from': '2026-Q3', 'to': '2026-Q1'})
    with pytest.raises(ValueError, match='NetCheck 2026 and NetCheck 2026-Q3 overlap'):
        check_campaign_overlaps(two_methodologies({'to': '2026-Q3'}, {'from': '2026-Q3'})['profiles'])
    with pytest.raises(ValueError, match='overlap'):
        check_campaign_overlaps(two_methodologies({'from': '2025-Q1'}, {'from': '2026-Q3', 'to': '2026-Q4'})['profiles'])
    check_campaign_overlaps(two_methodologies({'from': '2025-Q1', 'to': '2026-Q2'}, {'from': '2026-Q3'})['profiles'])
    with pytest.raises(ValueError):
        validate_scoring_profiles({'active_profile_id': BY_CAMPAIGN, 'profiles': [
            {'id': BY_CAMPAIGN, 'name': 'By campaign', 'configuration': scoring_configuration()}]})


def test_each_campaign_gets_the_methodology_whose_campaigns_include_it():
    profiles = two_methodologies({'to': '2026-Q2'}, {'from': '2026-Q3'})
    assert [p.get('campaigns') for p in profiles['profiles']] == [{'from': '', 'to': '2026-Q2'},
                                                                  {'from': '2026-Q3', 'to': ''}]
    assert methodology_for(profiles, '2025-Q4')['id'] == 'netcheck-2026'
    assert methodology_for(profiles, 'UK 2026 Q3')['id'] == 'netcheck-2026-q3'
    # A campaign without year and quarter takes the default methodology.
    assert methodology_for(profiles, 'Pilot')['id'] == 'netcheck-2026'
    groups = methodology_groups(profiles, ['2026-Q3', '2026-Q1', '2026-Q2'])
    assert [(group['profile_id'], group['campaigns']) for group in groups] == [
        ('netcheck-2026', ['2026-Q1', '2026-Q2']), ('netcheck-2026-q3', ['2026-Q3'])]
    assert methodology_label(groups) == 'By campaign (NetCheck 2026: 2026-Q1, 2026-Q2 · NetCheck 2026-Q3: 2026-Q3)'
    # The result shows the latest methodology, with the KPIs only earlier ones have at no points.
    codes = [metric['code'] for metric in display_configuration(groups)['metrics']]
    assert 'TIKTOK' in codes and len(codes) == len(set(codes))


def test_campaign_choices_are_the_quarters_of_the_workspace_campaigns():
    assert campaign_quarters(['2026-Q2', 'UK 2025 Q4', '2026-Q2 retest', 'Pilot']) == ['2025-Q4', '2026-Q2']


def test_results_of_each_methodology_keep_their_rows_and_split_back():
    profiles = two_methodologies({'to': '2026-Q2'}, {'from': '2026-Q3'})
    groups = methodology_groups(profiles, ['2026-Q2', '2026-Q3'])
    parts = [
        (groups[0], {'scoring': [{'Campaign': '2026-Q2', 'Score': 1}], 'totals': [], 'campaigns': ['2026-Q2'],
                     'warnings': ['a']}),
        (groups[1], {'scoring': [{'Campaign': '2026-Q3', 'Score': 2}], 'totals': [], 'campaigns': ['2026-Q3'],
                     'warnings': ['a', 'b', 'National & Area Summary: the selected CDRs have no London measurements.']}),
    ]
    merged = merge_results(parts)
    # A warning of the area summary names the methodology and campaigns it concerns.
    assert merged['warnings'][-1] == ('NetCheck 2026-Q3 (2026-Q3): National & Area Summary: the selected CDRs have no '
                                      'London measurements.')
    merged['warnings'] = merged['warnings'][:-1]
    assert [(row['Campaign'], row['methodology']) for row in merged['scoring']] == [
        ('2026-Q2', 'netcheck-2026'), ('2026-Q3', 'netcheck-2026-q3')]
    assert merged['warnings'] == ['a', 'b']
    assert merged['campaigns'] == ['2026-Q2', '2026-Q3']
    assert [group['profile_id'] for group in merged['methodology_groups']] == ['netcheck-2026', 'netcheck-2026-q3']
    part = split_result(merged, merged['methodology_groups'][1])
    assert [row['Campaign'] for row in part['scoring']] == ['2026-Q3']
    assert part['configuration'] == groups[1]['configuration']


def test_the_same_scaling_notice_of_every_methodology_is_told_once():
    profiles = two_methodologies({'to': '2026-Q2'}, {'from': '2026-Q3'})
    groups = methodology_groups(profiles, ['2026-Q2', '2026-Q3'])

    def merged_notices(*notices):
        return merge_results([(group, {'scoring': [], 'totals': [], 'campaigns': group['campaigns'], 'notices': items})
                              for group, items in zip(groups, notices)])['notices']
    scaled = 'Scaled to the maximum scoring: Drive - Connecting Roads has no results.'
    assert merged_notices([scaled], [scaled]) == [scaled]
    # A scaling of one methodology only, or a different one, names the methodology and campaigns it concerns.
    assert merged_notices([scaled], []) == [f'NetCheck 2026 (2026-Q2): {scaled}']
    assert merged_notices([scaled], ['Other scaling.']) == [f'NetCheck 2026 (2026-Q2): {scaled}',
                                                             'NetCheck 2026-Q3 (2026-Q3): Other scaling.']


def add_campaign_dataset(repository: Repository, name: str, campaign: str, kind: str = 'data') -> int:
    source = Path(repository.db_path).parent / name
    source.write_text('source', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'tester')
    frame = pd.DataFrame({
        'Operator': ['EE', 'O2'], 'Region': ['North', 'South'], 'City': ['Leeds', 'London'],
        'Operator_Vendor': ['Nokia', 'Ericsson'], 'Vendor': ['Nokia', 'Ericsson'], 'Campaign': [campaign, campaign],
        'Dataset_Kind': [kind, kind], 'score': [3.0, 4.0],
    })
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA',
                                      row_count=len(frame), column_count=len(frame.columns),
                                      processed_at=local_now_iso())
    repository.replace_cdr_catalogue(dataset_id, vendors=['Nokia', 'Ericsson'], vendors_only=['Nokia', 'Ericsson'],
                                     regions=['North', 'South'], cities=['Leeds', 'London'], campaigns=[campaign])
    return dataset_id


def test_a_saved_filter_by_campaign_scores_each_campaign_with_its_methodology(tmp_path, scoring_engine):  # noqa: F811
    engine, calls = scoring_engine
    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()
    repository.replace_scoring_profiles(two_methodologies({'to': '2026-Q2'}, {'from': '2026-Q3'}))
    dataset_ids = [add_campaign_dataset(repository, f'UK_{quarter}_2026_NSA_{kind.title()}.csv', f'2026-{quarter}', kind)
                   for quarter in ('Q2', 'Q3') for kind in ('data', 'voice', 'speech')]

    with pytest.raises(ValueError, match='needs Campaign in the Split by'):
        saved_filters.save_saved_filter(repository, dataset_ids, ['Region'], 'NSA', scoring_profile_id=BY_CAMPAIGN)

    saved, _reused = saved_filters.save_saved_filter(repository, dataset_ids, ['Campaign'], 'NSA',
                                                     scoring_profile_id=BY_CAMPAIGN)
    assert saved['scoring_profile_id'] == BY_CAMPAIGN
    assert saved['scoring_profile_name'] == (
        'By campaign (NetCheck 2026: 2026-Q2 · NetCheck 2026-Q3: 2026-Q3)')
    result = saved_filters.calculate_saved_filter(repository, saved['id'])
    assert result['status'] == 'completed', result['error']
    # One calculation per methodology, with the rows of its campaigns only (the scoring_engine fixture leaves out the
    # Geographical Areas & Scoring Trends; see test_scoring_area_summary).
    own = [index for index, (_frames, levels, _baseline) in enumerate(calls) if not {'Region', 'City'} & set(levels)]
    assert len(own) == 2 and len(calls) == 2
    assert [sorted({campaign for frame in calls[index][0].values() for campaign in frame['Campaign']})
            for index in own] == [['2026-Q2'], ['2026-Q3']]
    assert ['TIKTOK' in [metric['code'] for metric in engine.configuration_snapshots[index]['metrics']]
            for index in own] == [False, True]
    assert [row['methodology'] for row in result['result']['scoring']] == ['netcheck-2026', 'netcheck-2026-q3']


def test_campaign_ranges_travel_in_methodology_exports():
    from src.modules.scoring_config import scoring_profiles_document, unwrap_scoring_profiles_payload

    profiles = two_methodologies({'to': '2026-Q2'}, {'from': '2026-Q3'})
    restored = unwrap_scoring_profiles_payload(scoring_profiles_document(profiles))
    assert [profile.get('campaigns') for profile in restored['profiles']] == [
        {'from': '', 'to': '2026-Q2'}, {'from': '2026-Q3', 'to': ''}]


def test_overlapping_methodologies_saved_before_are_read_but_not_saved_again(tmp_path):
    repository = Repository(tmp_path / 'workspace.db')
    repository.initialize()
    overlapping = two_methodologies({'to': '2026-Q3'}, {'from': '2026-Q3'})
    repository.set_workspace_state('scoring_configuration', json.dumps(overlapping))
    profiles = repository.get_scoring_profiles()
    # The shared campaign takes the methodology that starts latest.
    assert methodology_for(profiles, '2026-Q3')['id'] == 'netcheck-2026-q3'
    with pytest.raises(ValueError, match='overlap'):
        repository.replace_scoring_profiles(profiles)
    profiles['profiles'][0]['campaigns'] = {'to': '2026-Q2'}
    assert repository.replace_scoring_profiles(profiles)['profiles'][0]['campaigns'] == {'from': '', 'to': '2026-Q2'}


def test_each_campaign_of_a_result_by_campaign_is_shown_with_its_methodology():
    from src.modules import scoring
    from src.modules.scoring_views import build_scoring_views
    from tests.test_scoring_history import _rows

    profiles = two_methodologies({'to': '2026-Q2'}, {'from': '2026-Q3'})
    groups = methodology_groups(profiles, ['2026-Q2', '2026-Q3'])
    parts = []
    for group, campaign in zip(groups, ('2026-Q2', '2026-Q3')):
        frames = {kind: _rows(kind).assign(Campaign=campaign) for kind in ('data', 'voice', 'speech')}
        parts.append((group, scoring.calculate_scoring(frames, ['Operator', 'Campaign'], baseline_operator='EE',
                                                       configuration=group['configuration'])))
    merged = merge_results(parts)
    from src.modules.saved_filters import AGGREGATION_CONTRACT_VERSION
    views = build_scoring_views({'levels': ['Operator', 'Campaign'],
                                 'aggregation_contract_version': AGGREGATION_CONTRACT_VERSION}, merged)
    by_campaign = {}
    for table in views['score_tables']:
        by_campaign.setdefault(table['context'].get('campaign'), []).append(table)
    assert set(by_campaign) == {'2026-Q2', '2026-Q3'}

    def codes(tables):
        return {row.get('kpi_code') or row.get('code') for table in tables for row in table['rows']}
    # The earlier campaign has no TikTok and is not incomplete for lacking it; the later one has it.
    assert 'TIKTOK' not in codes(by_campaign['2026-Q2']) and 'TIKTOK' in codes(by_campaign['2026-Q3'])
    assert not any('Incomplete KPI coverage' in json.dumps(table) for table in by_campaign['2026-Q2'])
    # The table of every campaign together: TikTok does not apply to the earlier campaign, which stays complete.
    assert views['hierarchy_score_tables']
    for table in views['hierarchy_score_tables']:
        assert not table['coverage_note']
        tiktok = next(row for row in table['rows'] if row['kpi_code'] == 'TIKTOK')
        assert {cell.get('not_applicable', False) for cell in tiktok['values'].values()} == {True, False}
        assert all(cell['complete'] for row in table['rows'] for cell in row['values'].values() if cell.get('not_applicable'))
