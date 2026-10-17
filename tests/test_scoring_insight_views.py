"""Summary, Locations, GAP by part and Points Lost insights of Scoring & GAP Analysis, and their slides.

They are calculated from synthetic NetCheck CDRs with NetCheck 2026: four operators in eight cities and on four
Connecting Roads routes over three campaigns, with the serving cell of every test and a few sites that fail often.
"""
from __future__ import annotations

from io import BytesIO
import zlib

import pytest
from pptx import Presentation

from src.modules.scoring_exports import export_scoring_powerpoint
from src.modules.scoring_insights import MAX_LEVERS, MAX_ROUTE_STRETCHES, MAX_SITES
from src.modules.scoring_views import build_scoring_views
from tests.scoring_cdr_synthetic import ROUTES, synthetic_cdr_result
from tests.test_scoring_exports import TEMPLATE


@pytest.fixture(scope='module')
def national():
    job, result = synthetic_cdr_result(levels=('Operator', 'Campaign'))
    return job, result, build_scoring_views(job, result)['insights']


@pytest.fixture(scope='module')
def cities():
    job, result = synthetic_cdr_result(levels=('Operator', 'City', 'Campaign'), campaigns=('2026-Q2', '2026-Q3'))
    return job, result, build_scoring_views(job, result)['insights']


def _combined(items, operator=None):
    return [item for item in items if item['environment'] == 'Combined' and (operator is None or item['operator'] == operator)]


def test_standings_rank_every_operator_and_measure_its_distances(national):
    _job, _result, insights = national
    standing = _combined(insights['standings'])[0]
    assert (standing['campaign'], standing['previous_campaign']) == ('2026-Q3', '2026-Q2')
    rows = standing['operators']
    assert [row['rank'] for row in rows] == [1, 2, 3, 4]
    assert [row['total'] for row in rows] == sorted((row['total'] for row in rows), reverse=True)
    reference = next(row for row in rows if row['operator'] == 'EE')
    assert reference['gap_to_reference'] is None
    for index, row in enumerate(rows):
        assert row['total'] == pytest.approx(row['data'] + row['voice'])
        assert row['delta'] == pytest.approx(row['total'] - row['previous'])
        assert row['takeaway'].startswith(row['label'])
        if index:
            assert row['gap_to_above'] == pytest.approx(row['total'] - rows[index - 1]['total'])
        if row['operator'] != 'EE':
            assert row['gap_to_reference'] == pytest.approx(row['total'] - reference['total'])
            # The GAP of every part of the scoring adds up to the GAP to the reference.
            assert sum(row['parts'].values()) == pytest.approx(row['gap_to_reference'], abs=.05)


def test_position_matrix_ranks_each_service_of_each_environment(national):
    _job, _result, insights = national
    matrix = _combined(insights['position_matrices'])[0]
    environments = [row['environment'] for row in matrix['rows']]
    assert environments[-1] == 'Combined' and len(environments) == 3
    for row in matrix['rows']:
        for service, cells in row['cells'].items():
            assert sorted(cell['rank'] for cell in cells.values()) == list(range(1, len(cells) + 1))
            for cell in cells.values():
                assert cell['percent'] == pytest.approx(cell['points'] / cell['maximum'] * 100)
                assert cell['missed'] == pytest.approx(cell['maximum'] - cell['points'])


def test_levers_are_the_kpis_behind_the_reference_that_win_most(national):
    _job, _result, insights = national
    levers = _combined(insights['levers'], 'Three UK')[0]
    gaps = [row['gap'] for row in levers['levers']]
    assert 0 < len(gaps) <= MAX_LEVERS and all(gap < 0 for gap in gaps) and gaps == sorted(gaps)
    assert levers['total_behind'] <= sum(gaps) + 1e-9


def test_campaign_scope_counts_the_tests_of_the_latest_campaign(national):
    _job, _result, insights = national
    scope = next(item for item in insights['campaign_scope'] if item['environment'] == 'Combined')
    assert scope['campaigns'] == ['2026-Q1', '2026-Q2', '2026-Q3'] and scope['latest_campaign'] == '2026-Q3'
    assert scope['window']['first'] == '2026-02-09' and scope['window']['days'] > 3
    # 8 cities × 6 positions and 4 routes × 9 positions, twice, with 7 Data tests and 4 calls each.
    assert scope['tests']['Vodafone UK']['data'] == {'Drive - City': 672, 'Drive - Connecting Roads': 504}
    assert scope['tests']['Vodafone UK']['voice'] == {'Drive - City': 384, 'Drive - Connecting Roads': 288}
    assert scope['places'] == {'cities': 8, 'routes': 4}


def test_gap_parts_add_up_to_the_total_gap_of_each_campaign(national):
    _job, _result, insights = national
    item = _combined(insights['gap_parts'], 'O2 UK')[0]
    assert item['by_reliability'] is True and item['campaigns'] == ['2026-Q1', '2026-Q2', '2026-Q3']
    assert [part['label'] for part in item['parts']] == ['Data reliability', 'Data quality', 'Voice reliability', 'Voice quality']
    for index, total in enumerate(item['totals']):
        assert sum(part['values'][index] for part in item['parts']) == pytest.approx(total)


def test_points_at_stake_share_every_point_lost(national):
    _job, _result, insights = national
    stake = _combined(insights['points_at_stake'])[0]
    assert [kind['key'] for kind in stake['kinds']] == ['failed', 'below_par', 'quality']
    for row in stake['operators']:
        assert sum(row['parts'].values()) == pytest.approx(row['lost'])
        assert row['lost'] + row['points'] == pytest.approx(stake['maximum'])


def test_sites_vendors_and_stretches_find_where_the_points_are_lost(national):
    _job, _result, insights = national
    sites = next(item for item in _combined(insights['sites_to_review'], 'Vodafone UK') if item['context'].get('campaign') == '2026-Q3')
    assert 0 < len(sites['rows']) <= MAX_SITES
    points = [row['points'] for row in sites['rows']]
    assert points == sorted(points, reverse=True)
    # The site of Leeds that fails many tests in every campaign is the one to review first.
    leeds = f"{zlib.crc32(b'Leeds') % 900 + 100}03"
    first = sites['rows'][0]
    assert (first['site'], first['city'], first['priority']) == (leeds, 'Leeds', 'High')
    assert [entry['campaign'] for entry in first['history']] == ['2026-Q1', '2026-Q2']
    vendors = _combined(insights['vendor_losses'], 'Vodafone UK')[-1]
    assert {row['name'] for row in vendors['rows']} <= {'Ericsson', 'Nokia'}
    assert sum(row['share'] for row in vendors['rows']) == pytest.approx(100, abs=.2)
    kinds = {row['name'] for item in _combined(insights['site_type_losses'], 'Three UK') for row in item['rows']}
    assert {'H3G', 'NNS · Vodafone'} <= kinds
    stretches = _combined(insights['route_stretches'], 'Vodafone UK')[-1]
    assert {route['route'] for route in stretches['routes']} <= set(ROUTES)
    assert stretches['routes'][0]['route'] == 'Manchester to Leeds'
    for route in stretches['routes']:
        shown = [row['points'] for row in route['stretches']]
        assert len(shown) <= MAX_ROUTE_STRETCHES and shown == sorted(shown, reverse=True)


def test_locations_are_ranked_and_compared_with_the_reference(cities):
    _job, _result, insights = cities
    rankings = _combined(insights['location_rankings'], 'Three UK')
    ranking = next(item for item in rankings if item['level'] == 'City')
    percents = [row['percent'] for row in ranking['rows']]
    assert len(percents) == 12 and percents == sorted(percents, reverse=True)
    for row in ranking['rows']:
        assert row['gap'] == pytest.approx(row['percent'] - row['reference_percent'])
        assert row['delta'] is not None and row['vendors']
    assert {row['kind'] for row in ranking['rows']} == {'place', 'route'}


def test_powerpoint_follows_the_order_of_the_results_tabs(national):
    job, result, _insights = national
    presentation = Presentation(BytesIO(export_scoring_powerpoint(job, result, TEMPLATE)))
    titles = [slide.shapes.title.text_frame.text.replace('\n', ' ') for slide in presentation.slides
              if slide.shapes.title is not None]

    def first(prefix):
        return next(index for index, title in enumerate(titles) if title.startswith(prefix))

    order = ['Best Network — Standings', 'Position — per environment', 'Biggest levers — vs EE', 'How the measurements ran',
             'Best Network Scoring per Service', 'Scoring Tables — Summary', 'GAP Analysis — ', 'GAP by part — vs EE',
             'KPI GAP Profile — ', 'Points Lost — where the points go', 'Points lost per KPI — ', 'Points Lost per City — ',
             'Points Lost — per Vendor', 'Points Lost — per kind of site', 'Sites to review — ', 'Route stretches — ',
             'Best Network Campaign Comparison']
    positions = [first(prefix) for prefix in order]
    assert positions == sorted(positions)
