"""Scoring & GAP Analysis NSA vs SA: the NSA and SA CDRs of the chosen campaigns scored together, each campaign with the
NR Mode of its CDRs, so the NSA and SA tests of an operator are compared side by side and never added together."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.modules import saved_filters, scoring_history
from src.modules.column_names import use_campaign_map
from src.modules.nr_mode import (
    NSA_VS_SA, campaign_with_nr_mode, normalize_scoring_nr_mode, nr_mode_label, nr_modes_of,
)
from src.modules.repository import Repository, local_now_iso
from src.modules.scoring_selection import expand_scoring_campaigns, load_scoring_selection, normalize_scoring_selection, scoring_auto_cdrs
from tests.scoring_fixtures import load_initial_scoring_configuration
from tests.test_scoring_history import _rows


def _add_cdr(repository: Repository, folder: Path, kind: str, nr_mode: str, campaign: str, seed: int) -> int:
    frame = _rows(kind, seed=seed)
    frame['Campaign'] = campaign
    name = f'NetCheck_UK_CDR_{kind.title()}_{campaign}_{nr_mode}.xlsx'
    source = folder / name
    source.write_text(f'{kind} {nr_mode} {campaign}', encoding='utf-8')
    dataset_id, _created = repository.add_dataset(name, str(source), 'super')
    repository.replace_dataset_rows(dataset_id, frame)
    repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode=nr_mode,
                                      row_count=len(frame), column_count=len(frame.columns), processed_at=local_now_iso())
    repository.replace_cdr_catalogue(dataset_id, vendors=[], regions=[], cities=[], campaigns=[campaign])
    return dataset_id


def _workspace(tmp_path: Path, sa_campaign: str = 'UK_Q3_SA_2026') -> tuple[Repository, dict[str, list[int]]]:
    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'global.db')
    repository.initialize()
    repository.replace_scoring_configuration(load_initial_scoring_configuration())
    ids = {
        'NSA': [_add_cdr(repository, tmp_path, kind, 'NSA', 'UK_Q3_NSA_2026', 3) for kind in ('data', 'voice', 'speech')],
        'SA': [_add_cdr(repository, tmp_path, kind, 'SA', sa_campaign, 7) for kind in ('data', 'voice', 'speech')],
    }
    return repository, ids


def _totals(result: dict, campaign: str) -> dict[tuple, float]:
    return {(row['operator'], row['environment']): round(row['weighted_points'] or 0, 6)
            for row in result['totals'] if row['campaign'] == campaign}


def test_nr_mode_helpers_name_the_nr_mode_of_each_campaign():
    assert normalize_scoring_nr_mode('NSA+SA') == normalize_scoring_nr_mode('nsa vs sa') == NSA_VS_SA
    assert normalize_scoring_nr_mode('sa') == 'SA' and normalize_scoring_nr_mode('LTE') is None
    assert nr_modes_of(NSA_VS_SA) == ('NSA', 'SA') and nr_modes_of('NSA') == ('NSA',)
    assert nr_mode_label(NSA_VS_SA) == 'NSA vs SA' and nr_mode_label('SA') == 'SA'
    # Campaigns that name their NR Mode, and NSA campaigns without one, stay as they are.
    assert campaign_with_nr_mode('UK_Q3_SA_2026', 'SA') == 'UK_Q3_SA_2026'
    assert campaign_with_nr_mode('UK_Q3_NSA_2026', 'NSA') == 'UK_Q3_NSA_2026'
    assert campaign_with_nr_mode('UK_Q2_2026', 'NSA') == 'UK_Q2_2026'
    # An SA campaign without its mode gets it, and one naming the other mode takes the mode of its CDR.
    assert campaign_with_nr_mode('UK_Q2_2026', 'SA') == 'UK_Q2_2026 SA'
    assert campaign_with_nr_mode('UK_Q2_SA_2026', 'NSA') == 'UK_Q2_NSA_2026'
    assert campaign_with_nr_mode('2026-W07', 'SA') == '2026-W07 SA'
    assert campaign_with_nr_mode(None, 'SA') is None


def test_nsa_vs_sa_is_offered_with_both_nr_modes_and_chooses_the_cdrs_of_both(tmp_path):
    repository, ids = _workspace(tmp_path)
    chosen = scoring_auto_cdrs(repository, NSA_VS_SA, {'Campaign': ['@latest-campaign']})
    assert chosen['nr_mode'] == NSA_VS_SA and chosen['nr_modes'] == ['NSA', 'SA', NSA_VS_SA]
    assert sorted(chosen['dataset_ids']) == sorted([*ids['NSA'], *ids['SA']])
    # Latest campaign is the newest quarter, with its NSA and SA campaigns.
    assert sorted(expand_scoring_campaigns(repository, NSA_VS_SA, ['@latest-campaign'])) == ['UK_Q3_NSA_2026', 'UK_Q3_SA_2026']
    assert expand_scoring_campaigns(repository, 'SA', ['@latest-campaign']) == ['UK_Q3_SA_2026']
    # A selection in NSA vs SA is always split by Campaign.
    selection, _warnings = normalize_scoring_selection(repository, {'nr_mode': NSA_VS_SA, 'aggregation_levels': ['Operator']})
    assert selection['nr_mode'] == NSA_VS_SA and 'Campaign' in selection['aggregation_levels']


def test_nsa_vs_sa_is_not_offered_with_one_nr_mode(tmp_path):
    repository = Repository(tmp_path / 'workspace.db', global_db_path=tmp_path / 'global.db')
    repository.initialize()
    repository.replace_scoring_configuration(load_initial_scoring_configuration())
    for kind in ('data', 'voice', 'speech'):
        _add_cdr(repository, tmp_path, kind, 'NSA', 'UK_Q3_NSA_2026', 3)
    chosen = scoring_auto_cdrs(repository, NSA_VS_SA, {})
    assert chosen['nr_mode'] == 'NSA' and chosen['nr_modes'] == ['NSA']
    selection, warnings = normalize_scoring_selection(repository, {'nr_mode': NSA_VS_SA})
    assert selection['nr_mode'] == 'NSA' and warnings


@pytest.mark.parametrize('sa_campaign, sa_label', [('UK_Q3_SA_2026', 'UK_Q3_SA_2026'),
                                                    # An SA campaign that does not name its mode gets it.
                                                    ('UK_Q3_NSA_2026', 'UK_Q3_SA_2026')])
def test_nsa_vs_sa_scores_each_nr_mode_apart_as_its_own_calculation(tmp_path, sa_campaign, sa_label):
    repository, ids = _workspace(tmp_path, sa_campaign)
    both, _ = saved_filters.save_saved_filter(repository, [*ids['NSA'], *ids['SA']], ['Operator'], NSA_VS_SA,
                                              baseline_operator='EE')
    assert both['nr_mode'] == NSA_VS_SA and 'Campaign' in both['levels']
    result = saved_filters.calculate_saved_filter(repository, both['id'])
    assert result['status'] == 'completed', result['error']
    combined = result['result']
    assert {row['campaign'] for row in combined['totals']} == {'UK_Q3_NSA_2026', sa_label}

    # The NSA and SA scores are those of each NR Mode on its own: the SA operators are no peers of the NSA ones.
    nsa, _ = saved_filters.save_saved_filter(repository, ids['NSA'], ['Operator', 'Campaign'], 'NSA', baseline_operator='EE')
    sa, _ = saved_filters.save_saved_filter(repository, ids['SA'], ['Operator', 'Campaign'], 'SA', baseline_operator='EE')
    nsa_result = saved_filters.calculate_saved_filter(repository, nsa['id'])['result']
    sa_result = saved_filters.calculate_saved_filter(repository, sa['id'])['result']
    assert _totals(combined, 'UK_Q3_NSA_2026') == _totals(nsa_result, 'UK_Q3_NSA_2026')
    assert _totals(combined, sa_label) == _totals(sa_result, sa_campaign)
    # The GAP compares each operator with the reference of its own NR Mode.
    gaps = {(row['operator'], row['campaign'], row['environment']): row['gap_points'] for row in combined['gap_totals']
            if row.get('gap_points') is not None}
    reference = {(row['operator'], row['environment']): row['gap_points'] for row in sa_result['gap_totals']
                 if row.get('gap_points') is not None}
    assert reference and all(gaps[(operator, sa_label, environment)] == pytest.approx(value)
                             for (operator, environment), value in reference.items())


def test_nsa_vs_sa_from_the_scoring_history_keeps_the_nr_modes_apart(tmp_path):
    repository, ids = _workspace(tmp_path, 'UK_Q3_NSA_2026')
    scoring_history.sync_history(repository)
    configuration = repository.get_scoring_profile()['configuration']
    dataset_ids = [*ids['NSA'], *ids['SA']]
    from_history = scoring_history.calculate_scoring_from_history(
        repository, dataset_ids, ['Operator', 'Campaign'], configuration=configuration, nr_mode_campaigns=True)
    assert {row['campaign'] for row in from_history['totals']} == {'UK_Q3_NSA_2026', 'UK_Q3_SA_2026'}
    weekly = scoring_history.calculate_scoring_from_history(
        repository, dataset_ids, ['Operator', 'Campaign'], configuration=configuration, nr_mode_campaigns=True,
        time_split='Weekly')
    assert {row['campaign'] for row in weekly['totals']} == {'2026-W28', '2026-W29', '2026-W28 SA', '2026-W29 SA'}
    sources, _campaigns, _fingerprint = saved_filters._source_snapshot(repository, dataset_ids, expected_nr_mode=NSA_VS_SA)
    for source in sources:
        source['levels'] = ['Operator', 'Campaign']
    from src.modules import scoring
    frames = saved_filters._load_source_frames(repository, sources, lambda *args: None, scoring.load_input_columns, {},
                                              nr_mode_campaigns=True)
    by_rows = scoring.calculate_scoring(frames, ['Operator', 'Campaign'], configuration=configuration)
    assert _totals(by_rows, 'UK_Q3_SA_2026') == pytest.approx(_totals(from_history, 'UK_Q3_SA_2026'), rel=1e-2)


def test_nsa_vs_sa_needs_campaign_labels_that_tell_the_nr_modes_apart(tmp_path):
    repository, ids = _workspace(tmp_path)
    dataset_ids = [*ids['NSA'], *ids['SA']]
    with use_campaign_map({'format': '{year}-Q{quarter}', 'modes_in_label': []}):
        with pytest.raises(ValueError, match='Campaign Map shows the NSA and SA campaigns alike'):
            saved_filters.save_saved_filter(repository, dataset_ids, ['Operator'], NSA_VS_SA)
    with pytest.raises(ValueError, match='time split other than All'):
        saved_filters.save_saved_filter(repository, dataset_ids, ['Operator'], NSA_VS_SA,
                                        area_summary={'time_split': 'All'})
    # A single NR Mode still needs CDRs of that mode only.
    with pytest.raises(ValueError, match='does not match the selected NSA NR Mode'):
        saved_filters.save_saved_filter(repository, dataset_ids, ['Operator'], 'NSA')


def test_nsa_vs_sa_saved_filters_travel_with_their_nr_mode(tmp_path):
    source_folder = tmp_path / 'source'
    source_folder.mkdir()
    source, ids = _workspace(source_folder)
    saved, _ = saved_filters.save_saved_filter(source, [*ids['NSA'], *ids['SA']], ['Operator'], NSA_VS_SA)
    document = saved_filters.saved_filters_document(source)
    [entry] = document['saved_filters']
    assert entry['nr_mode'] == NSA_VS_SA
    target_folder = tmp_path / 'target'
    target_folder.mkdir()
    target = Repository(target_folder / 'workspace.db', global_db_path=target_folder / 'global.db')
    target.initialize()
    target.replace_scoring_configuration(load_initial_scoring_configuration())
    assert saved_filters.import_saved_filters(target, document) == 1
    [imported] = saved_filters.list_saved_filters(target)
    assert imported['nr_mode'] == NSA_VS_SA


def test_the_saved_selection_keeps_nsa_vs_sa(tmp_path):
    repository, _ids = _workspace(tmp_path)
    from src.modules.scoring_selection import save_scoring_selection
    selection, _warnings = normalize_scoring_selection(repository, {'nr_mode': NSA_VS_SA, 'context_filters': {
        'Campaign': ['@latest-campaign']}})
    assert save_scoring_selection(repository, selection)
    loaded, warnings = load_scoring_selection(repository)
    assert loaded['nr_mode'] == NSA_VS_SA and not warnings and len(loaded['dataset_ids']) == 6


def test_reporting_jobs_and_bundle_report_templates_keep_nsa_vs_sa():
    from src.modules import bundle_report_templates, report_tasks
    from src.modules.scoring_reports import default_report_configuration
    definition = report_tasks.normalize_definition({'scoring': [
        {'nr_mode': 'NSA+SA', 'report': default_report_configuration()},
        {'nr_mode': 'LTE', 'report': default_report_configuration()}]})
    assert [entry['nr_mode'] for entry in definition['scoring']] == [NSA_VS_SA, 'NSA']
    assert report_tasks.scoring_entry_name({'nr_mode': NSA_VS_SA}) == 'NSA vs SA'
    template = bundle_report_templates.normalize_definition({'filters': {'nr_mode': 'SA'}, 'sections': [
        {'key': 'scoring', 'options': {'nsa_vs_sa': True}}]})
    [scoring] = [section for section in template['sections'] if section['key'] == 'scoring']
    # The section compares NSA vs SA; the report (and its other sections) keeps its NR Mode.
    assert scoring['options']['nsa_vs_sa'] and template['filters']['nr_mode'] == 'SA'
    assert 'NSA vs SA' in bundle_report_templates.section_lines(scoring)[1]
    assert not bundle_report_templates.normalize_definition({})['sections'][1]['options'].get('nsa_vs_sa')


def test_documents_name_nsa_vs_sa():
    from datetime import datetime
    from src.modules.cdr_report_filenames import build_scoring_report_filename
    from src.modules.scoring_exports import _scoring_filter_subtitle
    assert ' - NSA-vs-SA - ' in build_scoring_report_filename(datetime(2026, 10, 20), NSA_VS_SA, {})
    assert ' - NSA - ' in build_scoring_report_filename(datetime(2026, 10, 20), 'NSA', {})
    assert _scoring_filter_subtitle({'nr_mode': NSA_VS_SA}).startswith('Non-Standalone vs Standalone')
