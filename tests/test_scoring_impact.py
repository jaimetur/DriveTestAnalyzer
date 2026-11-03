"""Methodology Impact: the same tests scored with two methodologies, so every difference comes from the methodology."""
from __future__ import annotations

import copy
import csv
import json
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd
import pytest
from pptx import Presentation

import src.DriveTestAnalyzer as app_module
from src.modules import saved_filters, scoring_cache, scoring_impact
from src.modules.repository import Repository, local_now_iso
from src.modules.scoring import calculate_scoring
from src.modules.scoring_config import validate_scoring_configuration
from src.modules.scoring_export_panels import default_export_panels, normalize_export_panels
from src.modules.scoring_impact_exports import export_impact_csv, export_impact_powerpoint
from tests.scoring_cdr_synthetic import SOUTH, netcheck_2026_configuration, synthetic_cdr_frames
from tests.test_scoring_exports import TEMPLATE

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGNS = ('2026-Q2', '2026-Q3')


def _methodology(name: str) -> dict:
    return json.loads((ROOT / 'assets' / 'scoring-methodologies' / f'{name}.json').read_text())['profiles'][0]


def _reweighted(configuration: dict) -> dict:
    """A methodology that moves points between two KPIs of a category and tightens the thresholds of another KPI."""
    changed = copy.deepcopy(configuration)
    first, second, third = changed['metrics'][0], changed['metrics'][1], changed['metrics'][12]
    for environment, context in first['contexts'].items():
        if context['max_points'] > 0:
            moved = context['max_points'] * .25
            context['max_points'] -= moved
            second['contexts'][environment]['max_points'] += moved
    for context in third['contexts'].values():
        context['thresholds']['medium'] = context['thresholds']['medium'] * 1.02
    return validate_scoring_configuration(changed)


@pytest.fixture(scope='module')
def frames():
    data = synthetic_cdr_frames(campaigns=('2026-Q3',), repeats=1)
    return {kind: frame.assign(Region=frame['City'].map(lambda city: 'South' if city in SOUTH else 'North')) for kind, frame in data.items()}


def _passes(frames, configuration) -> dict:
    options = {'baseline_operator': 'EE', 'configuration': configuration, 'with_points_loss': False}
    return {'Operator': calculate_scoring(frames, ['Operator'], **options), 'Region': calculate_scoring(frames, ['Operator', 'Region'], **options),
            'City': calculate_scoring(frames, ['Operator', 'City'], **options)}


def _part(before, after, earlier=None) -> dict:
    results = {'before': before, 'after': after, **({'earlier': earlier} if earlier else {})}
    return scoring_impact._impact_part(results, 'EE', ['EE'], [], [])


def test_scores_are_the_same_without_the_points_lost_map(frames):
    configuration = netcheck_2026_configuration()
    full = calculate_scoring(frames, ['Operator'], baseline_operator='EE', configuration=configuration)
    light = calculate_scoring(frames, ['Operator'], baseline_operator='EE', configuration=configuration, with_points_loss=False)
    assert light['points_loss'] is None and full['points_loss']
    for field in ('scoring', 'totals', 'gap', 'gap_totals', 'global_kpis', 'notices'):
        assert light[field] == full[field]


def test_what_changed_between_the_methodologies_of_the_workspace():
    changes = scoring_impact.methodology_changes(validate_scoring_configuration(_methodology('NetCheck_2026')['configuration']),
                                                 validate_scoring_configuration(_methodology('NetCheck_2026-Q3')['configuration']))
    assert not changes['same']
    # NetCheck 2026-Q3 adds TikTok to Video Streaming and shares the points of its category among its KPIs.
    added = [row for row in changes['kpis'] if row['status'] == 'added']
    assert len(added) == changes['counts']['added'] == 3 and all(row['before'] == 0 and row['after'] > 0 for row in added)
    assert all('TIK TOK' in row['kpi'] for row in added)
    assert changes['counts']['removed'] == 0 and changes['counts']['unchanged'] > 0
    assert all(abs(row['delta']) < .01 for row in changes['categories'])
    # The KPI renamed for YouTube is the same KPI: its code ties it, with another name, filters and points.
    youtube = next(row for row in changes['kpis'] if row['kpi'].startswith('YOUTUBE'))
    assert youtube['status'] == 'changed' and {'definition', 'calculation', 'points'} <= set(youtube['kinds'])
    assert any(item['label'] == 'Name' and item['before'].startswith('VIDEO') for item in youtube['details'])


def test_a_methodology_compared_with_itself_changes_nothing(frames):
    configuration = netcheck_2026_configuration()
    assert scoring_impact.methodology_changes(configuration, copy.deepcopy(configuration))['same']
    results = _passes(frames, configuration)
    part = _part(results, results)
    assert part['changes']['same'] and part['takeaways'][0] == 'The scoring of every operator stays the same in All Environments.'
    for entry in part['scoring'].values():
        assert all(cell['delta'] == 0 and cell['rank_before'] == cell['rank_after'] for cell in entry['operators'].values())


def test_each_change_is_reported_with_what_it_moves():
    configuration = netcheck_2026_configuration()
    changed = _reweighted(configuration)
    changes = scoring_impact.methodology_changes(configuration, changed)
    by_code = {row['code']: row for row in changes['kpis']}
    assert by_code[changed['metrics'][0]['code']]['kinds'] == ['points']
    assert by_code[changed['metrics'][0]['code']]['delta'] < 0 < by_code[changed['metrics'][1]['code']]['delta']
    assert by_code[changed['metrics'][12]['code']]['kinds'] == ['thresholds']
    assert {item['label'] for item in by_code[changed['metrics'][12]['code']]['details']} == {'Medium'}
    assert changes['counts']['points'] == 2 and changes['counts']['thresholds'] == 1
    # A removed KPI, and one added.
    removed = copy.deepcopy(configuration)
    gone = removed['metrics'].pop(5)
    both = scoring_impact.methodology_changes(configuration, removed)
    assert [row['code'] for row in both['kpis'] if row['status'] == 'removed'] == [gone['code']]
    assert [row['code'] for row in scoring_impact.methodology_changes(removed, configuration)['kpis'] if row['status'] == 'added'] == [gone['code']]


def test_the_panels_add_up_on_the_same_tests(frames):
    configuration = netcheck_2026_configuration()
    part = _part(_passes(frames, configuration), _passes(frames, _reweighted(configuration)))
    names = [item['operator'] for item in part['operators']]
    assert part['reference'] == 'EE' and [item['operator'] for item in part['operators'] if item['is_reference']] == ['EE']
    assert [item['name'] for item in part['environments']] == ['Combined', 'Drive - City', 'Drive - Connecting Roads']
    for item in part['environments']:
        environment = item['name']
        scoring = part['scoring'][environment]['operators']
        assert scoring and {*scoring} <= {*names}
        lost = part['points_lost'][environment]['operators']
        for name, cell in scoring.items():
            assert cell['delta'] == pytest.approx(cell['after'] - cell['before'], abs=2e-3)
            # The KPIs and the categories of each operator add up to its scoring.
            assert sum((row['operators'].get(name) or {}).get('delta') or 0 for row in part['kpis'][environment]) == pytest.approx(cell['delta'], abs=.02)
            assert sum((row['operators'].get(name) or {}).get('delta') or 0 for row in part['categories'][environment]) == pytest.approx(cell['delta'], abs=.02)
            # With the same maximum, what the scoring wins is what the points lost lose.
            assert lost[name]['delta'] == pytest.approx(-cell['delta'], abs=.01)
            assert sum(lost[name]['parts_after'].values()) == pytest.approx(lost[name]['after'], abs=.01)
        gap = part['gap'][environment]['total']
        for name, cell in gap.items():
            assert cell['delta'] == pytest.approx(scoring[name]['delta'] - scoring['EE']['delta'], abs=.01)
            assert cell['flip'] == (cell['before'] * cell['after'] < 0)
        assert 'EE' not in gap
    # The KPIs that move most come first.
    peaks = [row['peak'] for row in part['kpis']['Combined']]
    assert peaks == sorted(peaks, reverse=True) and peaks[0] > 0
    assert part['bridge'] is None


def test_the_areas_scale_all_environments_as_the_geographical_areas(frames):
    configuration = netcheck_2026_configuration()
    part = _part(_passes(frames, configuration), _passes(frames, _reweighted(configuration)))
    assert set(part['areas']) == {'Region', 'City'}
    regions = {row['area']: row for row in part['areas']['Region']['Combined']}
    assert set(regions) == {'North', 'South'}
    # A city is only measured in one environment: All Environments scales it to the full maximum.
    cities = {row['area']: row for row in part['areas']['City']['Combined']}
    drive = {row['area']: row for row in part['areas']['City']['Drive - City']}
    assert drive['London']['operators']['EE']['before'] <= 650
    assert cities['London']['operators']['EE']['before'] == pytest.approx(drive['London']['operators']['EE']['before'] / .65, abs=.01)
    assert all(row['leader_before'] in row['operators'] and row['leader_after'] in row['operators'] for row in cities.values())


def test_the_bridge_separates_the_network_from_the_methodology():
    configuration = netcheck_2026_configuration()
    data = synthetic_cdr_frames(campaigns=CAMPAIGNS, repeats=1)
    earlier = {kind: frame[frame['Campaign'] == '2026-Q2'] for kind, frame in data.items()}
    later = {kind: frame[frame['Campaign'] == '2026-Q3'] for kind, frame in data.items()}
    options = {'baseline_operator': 'EE', 'with_points_loss': False}
    part = _part({'Operator': calculate_scoring(later, ['Operator'], configuration=configuration, **options)},
                 {'Operator': calculate_scoring(later, ['Operator'], configuration=_reweighted(configuration), **options)},
                 {'Operator': calculate_scoring(earlier, ['Operator'], configuration=configuration, **options)})
    for row in part['bridge']['Combined'].values():
        assert row['network'] + row['methodology'] == pytest.approx(row['total'], abs=.01)
        assert row['earlier'] + row['total'] == pytest.approx(row['latest'], abs=.01)
        assert abs(row['network']) > 0


# ---- The comparison of a Saved Filter, from its CDRs ---------------------------------------------------------------------

def _add_cdrs(repository: Repository, tmp_path: Path, frames: dict[str, pd.DataFrame], campaign: str) -> list[int]:
    ids = []
    for kind, frame in frames.items():
        rows = frame[frame['Campaign'] == campaign].reset_index(drop=True)
        name = f"UK_{campaign}_NSA_{kind}.csv"
        source = tmp_path / name
        source.write_text('test source', encoding='utf-8')
        dataset_id, _created = repository.add_dataset(name, str(source), 'admin')
        repository.replace_dataset_rows(dataset_id, rows)
        repository.update_dataset_profile(dataset_id, status='ready', progress=100, dataset_kind=kind, nr_mode='NSA', campaign=campaign,
                                          row_count=len(rows), column_count=len(rows.columns), processed_at=local_now_iso())
        repository.replace_cdr_catalogue(dataset_id, vendors=['Nokia'], vendors_only=['Nokia'], regions=['North', 'South'],
                                         cities=sorted(rows['City'].dropna().unique()), campaigns=[campaign])
        ids.append(dataset_id)
    return ids


@pytest.fixture()
def workspace(client, tmp_path):
    assert client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=False).status_code == 303
    active = app_module.active_workspace
    repository = Repository(active.database_path, global_db_path=app_module.repository.db_path,
                            workspace_registry_db_path=app_module.workspace_registry.registry_path)
    repository.initialize()
    first, second = _methodology('NetCheck_2026'), _methodology('NetCheck_2026-Q3')
    repository.replace_scoring_profiles({'active_profile_id': second['id'], 'profiles': [first, second]})
    data = synthetic_cdr_frames(campaigns=CAMPAIGNS, repeats=1)
    data = {kind: frame.assign(Region=frame['City'].map(lambda city: 'South' if city in SOUTH else 'North')) for kind, frame in data.items()}
    ids = [*_add_cdrs(repository, tmp_path, data, '2026-Q2'), *_add_cdrs(repository, tmp_path, data, '2026-Q3')]
    saved, _created = saved_filters.save_saved_filter(repository, ids, ['Operator', 'Campaign'], 'NSA', username='admin', baseline_operator='EE',
                                                      scoring_profile_id='by-campaign')
    return {'client': client, 'repository': repository, 'filter_id': saved['id'], 'ids': ids}


def _wait_inline(monkeypatch) -> list:
    """The jobs of the workspace run at once."""
    jobs = []

    def run(_repository, callback, *args, **_kwargs):
        jobs.append(callback)
        callback(*args)
    monkeypatch.setattr(app_module, '_submit_workspace_job', run)
    return jobs


def test_the_comparison_of_a_saved_filter_is_calculated_once_and_exported(workspace, monkeypatch):
    client, repository, filter_id = workspace['client'], workspace['repository'], workspace['filter_id']
    jobs = _wait_inline(monkeypatch)
    offered = client.get(f'/api/scoring/saved-filters/{filter_id}/impact/options').json()
    # The latest campaign and the nearest earlier one with another methodology, by default.
    defaults = offered['defaults']
    assert defaults['mode'] == 'campaigns' and defaults['campaign_b'] == '2026-Q3' and defaults['campaign_a'] == '2026-Q2'
    assert {entry['value']: entry['methodology_name'] for entry in offered['campaigns']['NSA']} == {'2026-Q3': 'NetCheck 2026-Q3', '2026-Q2': 'NetCheck 2026'}
    assert defaults['methodology_a'] == 'netcheck-2026' and defaults['methodology_b'] == 'netcheck-2026-q3'
    response = client.get(f'/api/scoring/saved-filters/{filter_id}/impact')
    assert response.status_code == 200, response.text
    state = response.json()
    assert state['status'] == 'completed' and len(jobs) == 1
    impact = state['impact']
    assert impact['before']['profile_name'] == 'NetCheck 2026' and impact['after']['profile_name'] == 'NetCheck 2026-Q3'
    assert impact['before']['campaign'] == impact['after']['campaign'] == '2026-Q3' and impact['earlier']['campaign'] == '2026-Q2'
    assert set(impact['scorings']) >= {'best_network'}
    part = impact['scorings']['best_network']
    assert part['changes']['counts']['added'] == 3 and part['bridge'] and part['areas']['City']
    # Asked again, it is read from the cache.
    assert client.get(f'/api/scoring/saved-filters/{filter_id}/impact').json()['impact']['key'] == impact['key'] and len(jobs) == 1
    with repository.connection() as connection:
        events = [row[0] for row in connection.execute("SELECT action FROM audit_logs WHERE action LIKE '%methodology_impact%'").fetchall()]
    assert set(events) == {'scoring_methodology_impact_requested', 'scoring_methodology_impact_calculated'}
    # Two methodologies on the tests of one campaign have no bridge.
    other = client.get(f'/api/scoring/saved-filters/{filter_id}/impact', params={
        'mode': 'methodologies', 'methodology_a': 'netcheck-2026-q3', 'methodology_b': 'netcheck-2026', 'campaign': '2026-Q2'}).json()
    assert other['impact']['earlier'] is None and other['impact']['before']['profile_name'] == 'NetCheck 2026-Q3'
    assert other['impact']['scorings']['best_network']['bridge'] is None and len(jobs) == 2
    # The exports.
    query = {'mode': 'campaigns'}
    csv_response = client.get(f'/scoring/saved-filters/{filter_id}/impact/export/csv', params=query)
    rows = list(csv.DictReader(StringIO(csv_response.content.decode('utf-8-sig'))))
    assert {row['Panel'] for row in rows} >= {'What changed', 'Scoring', 'Category', 'KPI', 'Geographical area', 'GAP', 'Points Lost', 'Network and methodology'}
    deck = client.get(f'/scoring/saved-filters/{filter_id}/impact/export/ppt', params=query)
    assert deck.status_code == 200, deck.text
    titles = [slide.shapes.title.text_frame.paragraphs[0].text for slide in Presentation(BytesIO(deck.content)).slides if slide.shapes.title is not None]
    assert any('What changed' in title for title in titles) and any('Per category' in title for title in titles)
    with repository.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM audit_logs WHERE action LIKE 'export_scoring_impact_%'").fetchone()[0] == 2


def test_a_campaign_keeps_the_scope_of_the_saved_filter_and_refuses_what_cannot_be_compared(workspace, monkeypatch):
    client, repository, filter_id = workspace['client'], workspace['repository'], workspace['filter_id']
    url = f'/api/scoring/saved-filters/{filter_id}/impact'
    assert client.get(url, params={'mode': 'campaigns', 'campaign_a': '2026-Q2', 'campaign_b': '2026-Q2'}).status_code == 400
    assert client.get(url, params={'mode': 'methodologies', 'methodology_a': 'netcheck-2026', 'methodology_b': 'netcheck-2026'}).status_code == 400
    assert client.get(url, params={'mode': 'methodologies', 'campaign': 'unknown'}).status_code == 400
    # Another NR Mode takes the campaigns of its own: it never receives those of the first one.
    offered = {'nr_modes': ['NSA', 'SA'], 'methodologies': [{'id': 'first'}, {'id': 'second'}],
               'campaigns': {'NSA': [{'value': 'Q2'}, {'value': 'Q3'}], 'SA': [{'value': 'Q2-SA'}, {'value': 'Q3-SA'}]},
               'by_nr_mode': {'NSA': {'campaign_a': 'Q2', 'campaign_b': 'Q3', 'methodology_a': 'first', 'methodology_b': 'second', 'campaign': 'Q3'},
                              'SA': {'campaign_a': 'Q2-SA', 'campaign_b': 'Q3-SA', 'methodology_a': 'first', 'methodology_b': 'second', 'campaign': 'Q3-SA'}},
               'defaults': {'mode': 'campaigns', 'nr_mode': 'NSA', 'campaign_a': 'Q2', 'campaign_b': 'Q3', 'methodology_a': 'first', 'methodology_b': 'second', 'campaign': 'Q3'}}
    sa = scoring_impact.normalize_selection({'nr_mode': 'SA'}, offered)
    assert (sa['campaign_a'], sa['campaign_b'], sa['campaign']) == ('Q2-SA', 'Q3-SA', 'Q3-SA')
    assert scoring_impact.normalize_selection({'nr_mode': 'Unknown'}, offered)['nr_mode'] == 'NSA'
    saved_filter = saved_filters.get_saved_filter(repository, filter_id, include_internal_snapshot=True)
    saved_filter['context_filters'] = {**saved_filter['context_filters'], 'Operator': ['EE', 'Three UK']}
    # The earlier campaign comes first whichever was chosen first, and the filters stay.
    prepared = scoring_impact.prepare_impact(repository, saved_filter, {'mode': 'campaigns', 'campaign_a': '2026-Q3', 'campaign_b': '2026-Q2'})
    assert prepared['selection']['campaign_a'] == '2026-Q2' and prepared['selection']['campaign_b'] == '2026-Q3'
    assert prepared['runs']['before']['campaign'] == '2026-Q3' and prepared['runs']['earlier']['campaign'] == '2026-Q2'
    assert set(prepared['runs']['before']['dataset_ids']) & set(workspace['ids'][3:]) and not set(prepared['runs']['before']['dataset_ids']) & set(workspace['ids'][:3])
    assert 'EE' in prepared['runs']['before']['filters']['Operator']
    impact = scoring_impact.calculate_impact(repository, prepared)
    assert {item['operator'] for item in impact['scorings']['best_network']['operators']} == {'EE', 'Three'}
    # Without a change of methodology, the same tests are scored once and all the difference is the network.
    same = copy.deepcopy(repository.get_scoring_profiles())
    same['profiles'][1]['campaigns'] = {}
    same['profiles'][0]['campaigns'] = {'from': '2026-Q1', 'to': ''}
    repository.replace_scoring_profiles(same)
    alike = scoring_impact.prepare_impact(repository, saved_filter, {'mode': 'campaigns'})
    assert alike['runs']['before'] is alike['runs']['after']
    result = scoring_impact.calculate_impact(repository, alike)
    assert result['same_methodology'] and all(row['methodology'] == 0 for row in result['scorings']['best_network']['bridge']['Combined'].values())


def test_a_failed_calculation_says_why_and_can_be_tried_again(workspace, monkeypatch):
    client, repository, filter_id = workspace['client'], workspace['repository'], workspace['filter_id']
    _wait_inline(monkeypatch)
    url = f'/api/scoring/saved-filters/{filter_id}/impact'
    with monkeypatch.context() as patch:
        patch.setattr(scoring_impact, 'calculate_impact', lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('No rows')))
        state = client.get(url).json()
        assert state['status'] == 'failed' and state['error'] == 'No rows'
        # It stays failed until it is asked again.
        assert client.get(url).json()['status'] == 'failed'
    assert client.get(url).json()['status'] == 'failed'
    assert client.get(url, params={'retry': 'true'}).json()['status'] == 'completed'
    with repository.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM audit_logs WHERE action = 'scoring_methodology_impact_failed'").fetchone()[0] == 1


def test_the_document_follows_the_scoring_export_panels(frames):
    configuration = netcheck_2026_configuration()
    part = _part(_passes(frames, configuration), _passes(frames, _reweighted(configuration)))
    impact = {'before': {'profile_name': 'First', 'campaign_label': '26-Q3'}, 'after': {'profile_name': 'Second', 'campaign_label': '26-Q3'},
              'earlier': None, 'same_methodology': False, 'nr_mode': 'NSA', 'notes': [], 'scorings': {'best_network': part}}

    def titles(**options) -> list[str]:
        deck = Presentation(BytesIO(export_impact_powerpoint(impact, TEMPLATE, [], **options)))
        return [slide.shapes.title.text_frame.paragraphs[0].text for slide in deck.slides if slide.shapes.title is not None]
    every = titles()
    for expected in ('What changed', 'Scoring per operator', 'Per category', 'KPIs affected', 'Per Region', 'Per City', 'GAP against', 'Points Lost', 'Points lost per category'):
        assert any(expected in title for title in every), expected
    # A panel that is not exportable is left out.
    panels = default_export_panels()
    assert set(panels['impact']) == {'changes', 'scoring', 'bridge', 'categories', 'kpis', 'areas', 'gap', 'points'}
    panels['impact']['areas']['exportable'] = False
    panels['impact']['points']['exportable'] = False
    fewer = titles(panels=panels)
    assert not any('Per City' in title or 'Points Lost' in title for title in fewer) and any('Per category' in title for title in fewer)
    # Settings saved before keep the default of the panels they do not know.
    assert normalize_export_panels({'panels': {'summary': {'act': {'exportable': False}}}})['impact']['kpis']['exportable'] is True
    # The operators chosen in the page, and the Focus operators in the panels that export them.
    panels = default_export_panels()
    panels['impact']['categories']['operators'] = 'focus'
    focus = [{'canonical': 'Three UK', 'aliases': [], 'position': 0, 'color': '#000000', 'role': 'focus'}]
    deck = Presentation(BytesIO(export_impact_powerpoint(impact, TEMPLATE, focus, panels=panels)))
    slide = next(item for item in deck.slides if item.shapes.title is not None and 'Per category' in item.shapes.title.text_frame.text)
    table = next(shape.table for shape in slide.shapes if shape.has_table)
    assert [cell.text for cell in table.rows[0].cells] == ['Category', 'Three UK']
    csv_text = export_impact_csv(impact)
    assert csv_text.startswith('Panel,Environment,Operator,Level,Item,First methodology,Second methodology,Before,After,Difference')


def test_the_key_of_a_comparison_changes_with_what_it_depends_on(workspace):
    repository, filter_id = workspace['repository'], workspace['filter_id']
    saved_filter = saved_filters.get_saved_filter(repository, filter_id, include_internal_snapshot=True)
    key = scoring_impact.prepare_impact(repository, saved_filter)['key']
    assert scoring_impact.prepare_impact(repository, saved_filter)['key'] == key
    assert scoring_impact.prepare_impact(repository, saved_filter, {'mode': 'methodologies'})['key'] != key
    profiles = copy.deepcopy(repository.get_scoring_profiles())
    profile = next(item for item in profiles['profiles'] if item['id'] == 'netcheck-2026-q3')
    profile['configuration']['metrics'][0]['contexts']['Drive - City']['thresholds']['medium'] = 97.0
    repository.replace_scoring_profiles(profiles)
    assert scoring_impact.prepare_impact(repository, saved_filter)['key'] != key
    assert scoring_cache.read(repository, scoring_impact.CACHE_KIND, key) is None


def test_the_tab_is_in_the_page_and_the_menu(workspace):
    page = workspace['client'].get('/scoring').text
    assert 'data-result-tab="impact"' in page and 'data-result-pane="impact"' in page and 'js/scoring_impact.js' in page
    assert 'scoring-results-methodology-impact' in page
    script = (ROOT / 'src/web_interface/static/js/scoring.js').read_text()
    assert "'points', 'impact']" in script and "'scoring-results-methodology-impact': 'impact'" in script
    config = workspace['client'].get('/workspace-config').text
    assert 'name="exportable:impact:kpis"' in config and 'Methodology Impact' in config
