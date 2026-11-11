"""Summary, Geographical Areas, GAP by part and Points Lost insights of Scoring & GAP Analysis, and their slides.

They are calculated from synthetic NetCheck CDRs with NetCheck 2026: four operators in eight cities and on four
Connecting Roads routes over three campaigns, with the serving cell of every test and a few sites that fail often.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zlib

import pytest
from pptx import Presentation

from src.modules.scoring.scoring_exports import export_scoring_powerpoint
from src.modules.scoring.scoring_insights import MAX_LEVERS, MAX_ROUTE_STRETCHES, MAX_SITES
from src.modules.scoring.scoring_views import build_scoring_views
from tests.support.scoring_cdr_synthetic import ROUTES, synthetic_cdr_result
from tests.support.scoring_fixtures import export_panels_only
from tests.support.shared_results import shared_result
from tests.scoring.test_scoring_exports import TEMPLATE


# (Once per run, see tests.shared_results; the tests of a process run in the order of their durations, see conftest.py.)
@pytest.fixture(scope='session')
def national():
    return shared_result('insight_views', _insights, ('Operator', 'Campaign'))


@pytest.fixture(scope='session')
def cities():
    return shared_result('insight_views', _insights, ('Operator', 'City', 'Campaign'), campaigns=('2026-Q2', '2026-Q3'))


def _insights(levels, **options):
    job, result = synthetic_cdr_result(levels=levels, **options)
    return job, result, build_scoring_views(job, result)['insights']


def _combined(items, operator=None):
    return [item for item in items if item['environment'] == 'Combined' and (operator is None or item['operator'] == operator)]


def test_standings_rank_every_operator_and_measure_its_distances(national):
    _job, _result, insights = national
    standing = _combined(insights['standings'])[0]
    assert (standing['campaign'], standing['previous_campaign']) == ('26-Q3', '26-Q2')
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
    assert scope['campaigns'] == ['26-Q1', '26-Q2', '26-Q3'] and scope['latest_campaign'] == '26-Q3'
    assert scope['window']['first'] == '2026-02-09' and scope['window']['days'] > 3
    # 8 cities × 6 positions and 4 routes × 9 positions, twice, with 7 Data tests and 4 calls each.
    assert scope['tests']['Vodafone UK']['data'] == {'Drive - City': 672, 'Drive - Connecting Roads': 504}
    assert scope['tests']['Vodafone UK']['voice'] == {'Drive - City': 384, 'Drive - Connecting Roads': 288}
    assert scope['places'] == {'cities': 8, 'routes': 4}


def test_campaign_scope_names_the_campaign_scored_without_campaign_in_the_split_by():
    job, result = synthetic_cdr_result(levels=('Operator',), campaigns=('2026-Q2',))
    scope = next(item for item in build_scoring_views(job, result)['insights']['campaign_scope']
                 if item['environment'] == 'Combined')
    assert scope['campaigns'] == ['26-Q2'] and scope['latest_campaign'] == '26-Q2'
    assert scope['tests_campaign'] == '26-Q2' and scope['tests']['Vodafone UK']['data']


def test_gap_parts_add_up_to_the_total_gap_of_each_campaign(national):
    _job, _result, insights = national
    item = _combined(insights['gap_parts'], 'O2 UK')[0]
    assert item['by_reliability'] is True and item['campaigns'] == ['26-Q1', '26-Q2', '26-Q3']
    assert [part['label'] for part in item['parts']] == ['Data reliability', 'Data quality', 'Voice reliability', 'Voice quality']
    for index, total in enumerate(item['totals']):
        assert sum(part['values'][index] for part in item['parts']) == pytest.approx(total)


def test_operators_without_identified_sites_are_listed_apart_from_the_sites_to_review():
    from src.modules.scoring.scoring_insights import _serving_views
    from src.modules.scoring.scoring_points_loss import NOT_SPECIFIED, SITE

    def site_map(operator, areas):
        return {'field': SITE, 'operator': operator, 'label': operator, 'color': '#123456', 'is_reference': operator == 'BT',
                'environment': 'Combined', 'context': {'campaign': '2026-Q3'}, 'total': sum(area['points'] for area in areas),
                'areas': areas}
    views = _serving_views([
        site_map('VF', [{'name': 'S1', 'site': 'S1', 'points': 12.0, 'share': .8}, {'name': NOT_SPECIFIED, 'points': 3.0, 'share': .2}]),
        # Every serving cell of BT is missing from the inventories: no site of it can be reviewed.
        site_map('BT', [{'name': NOT_SPECIFIED, 'points': 61.5, 'share': 1.0}]),
    ], {})
    assert [item['operator'] for item in views['sites_to_review']] == ['VF']
    [missing] = views['sites_unidentified']
    assert (missing['operator'], missing['unidentified'], missing['campaign']) == ('BT', 61.5, '26-Q3')
    script = (Path(__file__).resolve().parents[2] / 'src/web_interface/static/js/scoring/scoring.js').read_text(encoding='utf-8')
    assert "const unidentified = insightItems(payload, 'sites_unidentified', environment);" in script
    assert 'none of the cells `' in script and 'cannot be `' in script


def test_points_lost_per_vendor_puts_the_vendor_series_of_an_operator_together():
    # Ticket #81: split by Vendor, each Vendor is a series of its own, whose table held that Vendor alone at 100%.
    from src.modules.scoring.scoring_exports import _slide
    from src.modules.scoring.scoring_insights import VENDORS_TOTAL_LABEL, _serving_views
    from src.modules.scoring.scoring_points_loss import VENDOR
    from src.modules.scoring.scoring_summary_slides import add_serving_loss_slides

    def vendor_map(operator, vendor, total, cities):
        return {'field': VENDOR, 'operator': operator, 'label': operator, 'color': '#E60000', 'is_reference': False,
                'environment': 'Combined', 'context': {'vendor': vendor, 'city': 'London', 'campaign': '2026-Q3'},
                'total': total, 'areas': [{'name': vendor, 'points': total, 'share': 1.0, 'environments': ['City']}],
                'city_losses': {vendor: cities}}

    series = {'operator': 'VF', 'city': 'London', 'campaign': '2026-Q3', 'environment': 'City'}
    result = {'points_loss': {
        'shares': [{**series, 'vendor': 'Ericsson', 'kpi_code': 'K1', 'areas': {}}],
        'serving_tests': [{**series, 'vendor': vendor, 'counts': {VENDOR: {vendor: count}}}
                          for vendor, count in (('Ericsson', 300), ('Samsung', 100))]}}
    views = _serving_views([vendor_map('VF', 'Samsung', 120.0, {'London': 120.0}),
                            vendor_map('VF', 'Ericsson', 40.0, {'London': 30.0, 'Leeds': 10.0}),
                            vendor_map('EE', 'All', 25.0, {'London': 25.0})], result)
    vf, ee = views['vendor_losses']
    # One table per operator, without the Vendor in its scope: a row per Vendor with the points it costs the operator
    # (ticket #115: its own points lost in proportion to its tests), the Vendor that costs most first, and its own scoring.
    assert vf['by_vendor'] and vf['context'] == {'city': 'London', 'campaign': '2026-Q3'}
    assert {row['name']: (row['points'], row['own_points']) for row in vf['rows']} == {
        'Samsung': pytest.approx((30.0, 120.0)), 'Ericsson': pytest.approx((30.0, 40.0))}
    assert {row['name']: row['tests_share'] for row in vf['rows']} == {'Samsung': pytest.approx(25.0), 'Ericsson': pytest.approx(75.0)}
    assert sum(row['share'] for row in vf['rows']) == pytest.approx(100.0)
    ericsson = next(row for row in vf['rows'] if row['name'] == 'Ericsson')
    assert ericsson['cities'] == [{'name': 'London', 'points': pytest.approx(22.5)}, {'name': 'Leeds', 'points': pytest.approx(7.5)}]
    # The rows add up to the total: the average of the Vendors weighted by their tests.
    assert vf['total_label'] == VENDORS_TOTAL_LABEL and vf['total'] == pytest.approx(120 * .25 + 40 * .75)
    assert sum(row['points'] for row in vf['rows']) == pytest.approx(vf['total'])
    # An operator without a Vendor has one row All (without tests counted, the plain average).
    assert [row['name'] for row in ee['rows']] == ['All'] and ee['total'] == 25.0 and not ee['has_tests']

    deck = Presentation(TEMPLATE)
    add_serving_loss_slides(deck, views['vendor_losses'], title='Points Lost — per Vendor', column='Vendor', subtitle='',
                            new_slide=_slide)
    tables = [shape.table for slide in deck.slides for shape in slide.shapes if shape.has_table]
    table = next(table for table in tables if table.cell(1, 0).text in ('Samsung', 'Ericsson'))
    headers = [cell.text for cell in table.rows[0].cells]
    assert headers[:5] == ['Vendor', 'Points lost', 'Share of points', 'Own scoring', 'Share of tests']
    assert [cell.text for cell in table.rows[len(table.rows) - 1].cells][:5] == [VENDORS_TOTAL_LABEL, '60.00', '100.0%', '', '100.0%']
    texts = [shape.text_frame.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame]
    assert any('VF · 2 Vendors · 60.0 points lost on average (weighted by tests)' in text for text in texts)


def test_points_lost_per_ran_vendor_and_site_type_count_the_calls_and_tests():
    # Ticket #85: the multivendor analysis shares the points lost among the RAN Vendors with their host network and the
    # site types (Legacy, eMOCN, NNS) of the serving cells, with the calls and tests and the points lost per 1,000 of them.
    import pandas as pd

    from src.modules.scoring.scoring import calculate_scoring
    from src.modules.scoring.scoring_exports import _slide
    from src.modules.scoring.scoring_summary_slides import add_serving_loss_slides
    from src.modules.network.serving_cells import ran_vendor_class, site_class
    from tests.support.scoring_cdr_synthetic import netcheck_2026_configuration, synthetic_cdr_frames

    frames = synthetic_cdr_frames(campaigns=('2026-Q3',), repeats=1)
    for frame in frames.values():
        scenarios = frame.get('Serving_eMOCN_Scenario', pd.Series('', index=frame.index))
        frame['Serving_RAN_Vendor'] = [ran_vendor_class(host, vendor) for host, vendor in zip(frame['Serving_Host_Network'], frame['Vendor'])]
        frame['Serving_Site_Class'] = [site_class(network, code) for network, code in zip(frame['Serving_Network'], scenarios)]
    levels = ['Operator', 'Campaign']
    result = calculate_scoring(frames, levels, baseline_operator='EE', configuration=netcheck_2026_configuration())
    job = {'id': 1, 'levels': levels, 'aggregation_levels': levels, 'baseline_operator': 'EE', 'nr_mode': 'NSA',
           'configuration': result['configuration'], 'campaigns': list(result.get('campaigns') or []), 'status': 'completed'}
    insights = build_scoring_views(job, result)['insights']

    [vodafone] = _combined(insights['ran_vendor_losses'], 'Vodafone UK')
    assert {row['name'] for row in vodafone['rows']} <= {'VF_Hosted_Ericsson', 'VF_Hosted_Nokia', 'VMO2_Hosted_Ericsson', 'VMO2_Hosted_Nokia'}
    assert any(row['name'].startswith('VMO2_Hosted_') for row in vodafone['rows'])
    assert vodafone['has_counts'] and sum(row['tests'] for row in vodafone['rows']) == vodafone['tests']
    assert sum(row['share'] for row in vodafone['rows']) == pytest.approx(100, abs=.2)
    assert sum(row['tests_share'] for row in vodafone['rows']) == pytest.approx(100)
    for row in vodafone['rows']:
        expected = row['points'] / row['tests'] * 1000 if row['tests'] >= 100 else None
        assert row['rate'] == (pytest.approx(expected) if expected is not None else None)
        assert row['cities']
    assert vodafone['rate'] == pytest.approx(vodafone['total'] / vodafone['tests'] * 1000)
    # Three is served by Vodafone cells (eMOCN, NNS here) on part of its tests; its own cells are Legacy (the synthetic
    # Speech samples have no eMOCN scenario, so their Vodafone cells are Legacy).
    [three] = _combined(insights['site_class_losses'], 'Three UK')
    assert {'3UK_Legacy', 'VF_NNS'} <= {row['name'] for row in three['rows']} <= {'3UK_Legacy', 'VF_NNS', 'VF_Legacy'}
    [vodafone_sites] = _combined(insights['site_class_losses'], 'Vodafone UK')
    assert {row['name'] for row in vodafone_sites['rows']} == {'VF_Legacy', 'VF_eMOCN_S1'}

    deck = Presentation(TEMPLATE)
    add_serving_loss_slides(deck, insights['ran_vendor_losses'], title='Points Lost — per RAN Vendor (host and vendor)',
                            column='RAN Vendor', subtitle='', new_slide=_slide)
    tables = [shape.table for slide in deck.slides for shape in slide.shapes if shape.has_table]
    headers = [cell.text for cell in tables[0].rows[0].cells]
    assert headers[:6] == ['RAN Vendor', 'Points lost', 'Share of points', 'Tests', 'Share of tests', 'Per 1,000 tests']
    texts = [shape.text_frame.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame]
    assert any('all its serving cells, MIX when they differ' in text for text in texts)


def test_points_lost_per_ran_vendor_puts_the_vendors_of_an_operator_together_by_host_network():
    # Split by Vendor, the RAN Vendors of each Vendor series of an operator are one table, each Vendor counting in
    # proportion to its tests; the slide shows the network that hosts them once for all its Vendors, as the page.
    from src.modules.scoring.scoring_exports import _slide
    from src.modules.scoring.scoring_insights import VENDORS_TOTAL_LABEL, _serving_views
    from src.modules.scoring.scoring_points_loss import RAN_VENDOR
    from src.modules.scoring.scoring_summary_slides import add_serving_loss_slides, hosted_vendor_rows

    def ran_map(vendor, areas):
        total = sum(points for _name, points in areas)
        return {'field': RAN_VENDOR, 'operator': 'VF', 'label': 'VF', 'color': '#E60000', 'is_reference': False,
                'environment': 'Combined', 'context': {'vendor': vendor, 'campaign': '2026-Q3'}, 'total': total,
                'areas': [{'name': name, 'points': points, 'share': points / total, 'environments': ['City']} for name, points in areas],
                'city_losses': {name: {'London': points} for name, points in areas}}

    series = {'operator': 'VF', 'campaign': '2026-Q3', 'environment': 'City'}
    counts = {'Ericsson': {'VF_Hosted_Ericsson': 250, 'MIX': 50},
              'Samsung': {'VF_Hosted_Samsung': 60, 'VMO2_Hosted_Samsung': 20, 'MIX': 20}}
    result = {'points_loss': {
        'shares': [{**series, 'vendor': 'Ericsson', 'kpi_code': 'K1', 'areas': {}}],
        'serving_tests': [{**series, 'vendor': vendor, 'counts': {RAN_VENDOR: values}} for vendor, values in counts.items()]}}
    views = _serving_views([ran_map('Ericsson', [('VF_Hosted_Ericsson', 30.0), ('MIX', 10.0)]),
                            ran_map('Samsung', [('VF_Hosted_Samsung', 80.0), ('VMO2_Hosted_Samsung', 20.0), ('MIX', 20.0)])],
                           result)
    [vodafone] = views['ran_vendor_losses']
    assert vodafone['vendors_together'] and vodafone['context'] == {'campaign': '2026-Q3'}
    # Ericsson holds 300 of the 400 tests and Samsung 100: their points lost count three to one.
    assert [(row['name'], row['points']) for row in vodafone['rows']] == pytest.approx(
        [('VF_Hosted_Ericsson', 22.5), ('VF_Hosted_Samsung', 20.0), ('MIX', 12.5), ('VMO2_Hosted_Samsung', 5.0)])
    assert vodafone['total'] == pytest.approx(40.0 * .75 + 120.0 * .25) and vodafone['total_label'] == VENDORS_TOTAL_LABEL
    assert [row['tests'] for row in vodafone['rows']] == [250, 60, 70, 20] and vodafone['tests'] == 400
    assert sum(row['share'] for row in vodafone['rows']) == pytest.approx(100)
    assert [row['rate'] for row in vodafone['rows']] == [pytest.approx(90.0), None, None, None]
    assert vodafone['rate'] == pytest.approx(150.0)
    # The network that loses most first (VF_Hosted, 42.5), each with its Vendors; MIX without a network.
    assert [(host, vendor) for _row, host, vendor in hosted_vendor_rows(vodafone['rows'])] == [
        ('VF_Hosted', 'Ericsson'), ('VF_Hosted', 'Samsung'), ('MIX', None), ('VMO2_Hosted', 'Samsung')]

    deck = Presentation(TEMPLATE)
    add_serving_loss_slides(deck, views['ran_vendor_losses'], title='Points Lost — per RAN Vendor (host and vendor)',
                            column='RAN Vendor', subtitle='', new_slide=_slide, hosted=True)
    [table] = [shape.table for slide in deck.slides for shape in slide.shapes if shape.has_table]
    assert [cell.text for cell in table.rows[0].cells][:4] == ['Host network', 'Vendor', 'Points lost', 'Share of points']
    assert [(table.cell(index, 0).text, table.cell(index, 1).text) for index in range(1, 5)] == [
        ('VF_Hosted', 'Ericsson'), ('', 'Samsung'), ('MIX', ''), ('VMO2_Hosted', 'Samsung')]
    assert table.cell(1, 0).is_merge_origin and table.cell(1, 0).span_height == 2
    assert not table.cell(3, 0).is_merge_origin and table.cell(3, 1).text == ''
    # A rule under every network but the last (the bottom of its last row and of its merged cell).
    from pptx.oxml.ns import qn

    def ruled(row, column):
        properties = table.cell(row, column)._tc.tcPr
        return properties is not None and properties.find(qn('a:lnB')) is not None
    assert [row for row in range(1, 5) if all(ruled(row, column) for column in range(1, len(table.columns)))] == [2, 3]
    assert ruled(1, 0) and ruled(3, 0) and not ruled(4, 0)
    total = len(table.rows) - 1
    assert table.cell(total, 0).span_width == 2 and table.cell(total, 0).text == VENDORS_TOTAL_LABEL
    assert table.cell(total, 2).text == '60.00'
    texts = [shape.text_frame.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame]
    assert any('VF · 60.0 points lost on average of its Vendors (weighted by tests)' in text for text in texts)


def _vendor_summary(vendor, *operators):
    return {'context': {'vendor': vendor, 'campaign': '2026-Q3'}, 'maximum': 1000.0, 'scaled': False,
            'max_voice': 350.0, 'max_data': 650.0,
            'operators': [{'operator': name, 'label': name, 'color': '#123456', 'voice': total * .35, 'data': total * .65,
                           'total': total, 'complete': True, 'is_reference': name == 'EE', 'position': position}
                          for name, total, position in operators]}


def test_scoring_nationwide_split_by_vendor_is_a_grid_of_operators_and_vendors():
    # Split by Vendor, the scoring Nationwide was a card per Vendor that did not say which: a column per operator and a
    # row per Vendor (each Vendor always on its own row), a small card where the operator was measured with it, with its
    # position among the operators of the Vendor.
    from src.modules.scoring.scoring_exports import _slide
    from src.modules.scoring.scoring_insight_slides import add_location_card_slides
    from src.modules.scoring.scoring_insights import _location_cards, _national_cards

    summaries = {index: summary for index, summary in enumerate([
        _vendor_summary('Unknown', ('VF', 482.0, 3)),
        _vendor_summary('Ericsson', ('VF', 922.0, 3), ('Three', 921.0, 2)),
        _vendor_summary('All', ('EE', 940.0, 0), ('O2', 795.0, 1)),
        _vendor_summary('Ericsson (Mixed)', ('Three', 707.0, 2)),
        _vendor_summary('Huawei', ('Three', 749.0, 2), ('VF', 732.0, 3)),
    ])}
    [group] = _national_cards(summaries, ['Operator', 'Vendor'], 'Combined')
    assert group['by_vendor'] and group['level'] == 'National' and group['title'] == '' and group['context'] == {}
    columns = [column['operator'] for column in group['operator_columns']]
    assert columns == ['EE', 'O2', 'Three', 'VF']
    rows = {row['label']: row['cards'] for row in group['vendor_rows']}
    assert list(rows) == ['All', 'Ericsson', 'Huawei', 'Ericsson (Mixed)', 'Unknown']

    def cell(vendor, operator):
        card = rows[vendor].get(operator)
        return card and (card['operators'][0]['rank'], round(card['operators'][0]['behind'], 1))
    assert [cell('All', operator) for operator in columns] == [(1, 0.0), (2, -145.0), None, None]
    assert [cell('Ericsson', operator) for operator in columns] == [None, None, (2, -1.0), (1, 0.0)]
    assert [cell('Huawei', operator) for operator in columns] == [None, None, (1, 0.0), (2, -17.0)]
    assert cell('Ericsson (Mixed)', 'VF') is None and cell('Unknown', 'VF') == (1, 0.0)

    # The cards of the areas split by Vendor name their Vendor.
    regions = {index: {**summary, 'context': {**summary['context'], 'region': region}}
               for index, (summary, region) in enumerate((summary, region) for summary in summaries.values()
                                                           for region in ('North', 'South'))}
    areas = _location_cards(regions, ['Operator', 'Vendor', 'Region'], 'Combined')
    assert {(item['title'], item['context'].get('vendor')) for item in areas} >= {('Vendor: Ericsson', 'Ericsson'), ('Vendor: All', 'All')}

    deck = Presentation(TEMPLATE)
    add_location_card_slides(deck, [group], scoring_label='Best Network', subtitle='', new_slide=_slide)
    names = [shape.name for slide in deck.slides for shape in slide.shapes]
    assert {'Scoring Vendor Card VF Ericsson', 'Scoring Vendor Card VF Unknown', 'Scoring Vendor Card EE All'} <= set(names)
    assert 'Scoring Vendor Card Three Unknown' not in names
    texts = [shape.text_frame.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame]
    assert any('scoring of the whole country per Vendor' in text for text in texts)
    assert any(text.startswith('921') and '−1.0' in text for text in texts)


def test_points_at_stake_share_every_point_lost(national):
    _job, _result, insights = national
    stake = _combined(insights['points_at_stake'])[0]
    assert [kind['key'] for kind in stake['kinds']] == ['not_completed', 'below_minimum', 'below_par', 'quality']
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
    assert [entry['campaign'] for entry in first['history']] == ['26-Q1', '26-Q2']
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
        # The measured cities around the route name its map, and each numbered stretch its nearest city.
        assert route['landmarks'] and all({'name', 'latitude', 'longitude'} <= set(place) for place in route['landmarks'])
        assert all(row['label'] for row in route['stretches'])
    assert {'Manchester', 'Leeds'} <= {place['name'] for place in stretches['routes'][0]['landmarks']}


def test_the_route_stretch_map_colours_each_stretch_by_its_points_lost(national) -> None:
    from PIL import Image

    from src.modules.scoring.scoring_summary_slides import render_stretch_map, stretch_colour
    from src.modules.scoring.scoring_themes import THEMES
    scale = THEMES['ericsson']['scale']
    # From the third colour of the quality scale (little lost) through the second to the first (the most lost).
    assert (stretch_colour(0, scale), stretch_colour(.5, scale), stretch_colour(1, scale)) == (scale[2], scale[1], scale[0])
    _job, _result, insights = national
    route = _combined(insights['route_stretches'], 'Vodafone UK')[-1]['routes'][0]
    square = [[-3.0, 52.5], [-0.5, 52.5], [-0.5, 54.5], [-3.0, 54.5], [-3.0, 52.5]]
    image = Image.open(BytesIO(render_stretch_map(route, '#E60000', [], boundaries={'Area': [square]})))
    assert image.size == (1100, 900)
    # The map areas are the land: white over the grey sea.
    assert image.getpixel((5, 5)) == (233, 238, 243) and (255, 255, 255) in {colour for _count, colour in image.getcolors(1 << 20)}


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
    # Their slides name the level instead of Location, as the page does.
    from src.modules.scoring.scoring_summary_slides import add_location_ranking_slides, add_location_versus_slides
    from src.modules.scoring.scoring_exports import _slide
    deck = Presentation(TEMPLATE)
    add_location_ranking_slides(deck, [ranking], subtitle='', new_slide=_slide)
    add_location_versus_slides(deck, [ranking], subtitle='', new_slide=_slide)
    texts = [shape.text_frame.text for slide in deck.slides for shape in slide.shapes if shape.has_text_frame]
    headers = [shape.table.cell(0, column).text for slide in deck.slides for shape in slide.shapes if shape.has_table
               for column in range(2)]
    assert 'City' in headers and 'Location' not in headers
    titles = [slide.shapes.title.text_frame.paragraphs[0].text for slide in deck.slides]
    assert any(title.startswith('Three UK against') and title.endswith(' per city or route') for title in titles)
    assert any(title == 'Cities and routes ranked — Three UK' for title in titles)
    # Without routes, the City level is named as cities only.
    cities_only = {**ranking, 'rows': [row for row in ranking['rows'] if row['kind'] != 'route']}
    deck = Presentation(TEMPLATE)
    add_location_ranking_slides(deck, [cities_only], subtitle='', new_slide=_slide)
    add_location_versus_slides(deck, [cities_only], subtitle='', new_slide=_slide)
    titles = [slide.shapes.title.text_frame.paragraphs[0].text for slide in deck.slides]
    assert titles[0] == 'Cities ranked — Three UK' and titles[-1].endswith(' per city')
    assert any('available in each city or route' in text for text in texts)


def test_powerpoint_follows_the_order_of_the_results_tabs(national):
    job, result, _insights = national
    # (The deck has the panels of the checks, in All Environments.)
    job = {**job, '_export_panels': export_panels_only(
        'summary.scope', 'summary.act', 'summary.standings', 'summary.position', 'summary.levers', 'charts.service',
        'tables.summary', 'tables.campaign_comparison', 'gap.all_operators', 'gap.parts', 'gap.profile', 'points.stake',
        'points.kpis', 'points.map', 'points.vendors', 'points.site_types', 'points.sites', 'points.stretches')}
    presentation = Presentation(BytesIO(export_scoring_powerpoint(job, result, TEMPLATE, environments=['Combined'])))
    titles = [slide.shapes.title.text_frame.text.replace('\n', ' ') for slide in presentation.slides
              if slide.shapes.title is not None]

    def first(prefix):
        return next(index for index, title in enumerate(titles) if title.startswith(prefix))

    order = ['How the measurements ran', 'Where to act — ', 'Best Network — Standings', 'Position — per environment',
             'Biggest levers — vs EE', 'Best Network Scoring per Service', 'Scoring Tables — Summary',
             # The comparison of the campaigns closes the Scoring Tables, as on the page.
             'Best Network Campaign Comparison', 'GAP Analysis — ', 'GAP by part — vs EE',
             'KPI GAP Profile — ', 'Points Lost — where the points go', 'Points lost per KPI — ', 'Points Lost per City — ',
             'Points Lost — per Vendor', 'Points Lost — per kind of site', 'Sites to review — ', 'Route stretches — ']
    positions = [first(prefix) for prefix in order]
    assert positions == sorted(positions)
    # The tables of the points lost close with their total row.
    closing = {}
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_table and shape.name in ('Scoring KPI GAP Maximum Table', 'Scoring KPI GAP Reference Table',
                                                  'Scoring Serving Loss Table', 'Scoring Sites Table', 'Scoring Route Stretch Table'):
                closing.setdefault(shape.name, [cell.text for cell in shape.table.rows[len(shape.table.rows) - 1].cells])
    assert len(closing) == 5
    assert closing['Scoring KPI GAP Maximum Table'][0] == 'Total points lost'
    assert closing['Scoring KPI GAP Reference Table'][0] == 'Total KPI GAP'
    assert closing['Scoring Serving Loss Table'][0] == closing['Scoring Sites Table'][0] == 'Total'
    assert closing['Scoring Route Stretch Table'][1].startswith('Total of the ')


def test_the_campaigns_card_lists_the_other_analysed_campaigns_below_the_reference(national):
    job, result, _insights = national
    # (The deck has only How the measurements ran.)
    job = {**job, '_export_panels': export_panels_only('summary.scope')}
    presentation = Presentation(BytesIO(export_scoring_powerpoint(job, result, TEMPLATE, environments=['Combined'])))
    slide = next(slide for slide in presentation.slides if any(
        shape.has_text_frame and shape.text_frame.text.replace('\n', ' ').startswith('How the measurements ran')
        for shape in slide.shapes))
    texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame]
    # The reference (the latest campaign), then the others, the newest first.
    assert 'CAMPAIGNS' in texts and '26-Q3' in texts
    assert '+2 campaigns: 26-Q2, 26-Q1' in texts
    script = (Path(__file__).resolve().parents[2] / 'src/web_interface/static/js/scoring/scoring.js').read_text(encoding='utf-8')
    assert "const otherCampaigns = scope.campaigns.filter(campaign => !latest.includes(campaign)).reverse();" in script
    # With NSA vs SA the reference is the latest NSA and the latest SA campaign.
    assert "[scope.campaigns.filter(campaign => !isSa(campaign)).at(-1), scope.campaigns.filter(isSa).at(-1)]" in script
    assert "otherCampaigns.length ? `+${otherCampaigns.length} campaign${otherCampaigns.length === 1 ? '' : 's'}: ${otherCampaigns.join(', ')}`" in script


def test_the_campaign_comparison_exports_the_focus_operators(national, monkeypatch):
    import src.modules.scoring.scoring_exports as exports
    job, result, _insights = national
    shown = []
    monkeypatch.setattr(exports, 'add_campaign_comparison_slides',
                        lambda _presentation, comparisons, **_options: shown.append(sorted({item['operator'] for item in comparisons})))
    # (The decks have only the Campaign Comparison.)
    job = {**job, '_export_panels': export_panels_only('tables.campaign_comparison')}
    groups = [{'canonical': 'Three UK', 'aliases': [], 'position': 0, 'color': '#000000', 'role': 'focus'},
              {'canonical': 'EE', 'aliases': [], 'position': 1, 'color': '#76B7B2', 'role': 'focus'}]
    export_scoring_powerpoint(job, result, TEMPLATE, groups, scorings=['best_network'], environments=['Combined'])
    # The Focus operators only, the reference (EE) included as it is one of them.
    assert shown and all(operators == ['EE', 'Three UK'] for operators in shown)
    shown.clear()
    export_scoring_powerpoint(job, result, TEMPLATE, scorings=['best_network'], environments=['Combined'])
    # Without Focus operators, every operator.
    assert shown and all(operators == ['EE', 'O2 UK', 'Three UK', 'Vodafone UK'] for operators in shown)


def test_the_biggest_levers_export_the_focus_operators(national, monkeypatch):
    import src.modules.scoring.scoring_exports as exports
    job, result, _insights = national
    shown = []
    monkeypatch.setattr(exports, 'add_levers_slides', lambda _presentation, levers, compared, **_options: shown.append(
        sorted({item['operator'] for item in levers if compared(item['operator'], item.get('label'))})))
    # (The decks have only the Biggest levers.)
    job = {**job, '_export_panels': export_panels_only('summary.levers')}
    groups = [{'canonical': 'Three UK', 'aliases': [], 'position': 0, 'color': '#000000', 'role': 'focus'}]
    export_scoring_powerpoint(job, result, TEMPLATE, groups, scorings=['best_network'], environments=['Combined'])
    assert shown and all(operators == ['Three UK'] for operators in shown)
    # The operators chosen on the page in the Summary.
    shown.clear()
    export_scoring_powerpoint({**job, '_operator_choices': {'summary-operators': ['O2 UK', 'Vodafone UK']}}, result, TEMPLATE, groups,
                              scorings=['best_network'], environments=['Combined'])
    assert shown and all(operators == ['O2 UK', 'Vodafone UK'] for operators in shown)


def test_the_route_of_where_to_act_is_drawn_as_the_routes_of_points_lost(national, monkeypatch) -> None:
    import src.modules.scoring.scoring_summary_slides as summary_slides
    from src.modules.scoring.scoring_act_slides import render_owner_route_map
    _job, _result, insights = national
    route = next(item for item in insights['route_focus'] if item['routes'])['routes'][0]
    calls = []
    original = summary_slides.render_stretch_map
    monkeypatch.setattr(summary_slides, 'render_stretch_map', lambda *args, **kwargs: calls.append(kwargs) or original(*args, **kwargs))
    from PIL import Image
    image = Image.open(BytesIO(render_owner_route_map(route, lambda _owner: '#4472C4', None)))
    # One map for both: its top stretches numbered, each owner as the ring of its circles, on a square for the slide.
    assert image.size == (1100, 1100)
    assert calls and calls[0]['ranked'] == route['top'] and calls[0]['measure'] == 'Points lost' and calls[0]['ring_color']
    script = (Path(__file__).resolve().parents[2] / 'src/web_interface/static/js/scoring/scoring.js').read_text(encoding='utf-8')
    # On the page: the same map, opened larger on a double-click, its stretches chosen in the table beside it, and the
    # operators of every view of the results in the order of the Operator Maps.
    assert "return makeStretchMap(route, '#64748b', [], {ranked: route.top, ringColor: ownerColor" in script
    assert "const routeMap = event.target.closest('svg.scoring-stretch-map');" in script
    assert 'function linkStretchTable(map, table, stretches) {' in script and 'body.append(linkStretchTable(map, stretchTable, route.top), side);' in script
    assert '.sort((left, right) => position(left?.operator) - position(right?.operator));' in script
    template = (Path(__file__).resolve().parents[2] / 'src/web_interface/templates/scoring.html').read_text(encoding='utf-8')
    assert '[data-scoring-theme="umlaut"] .scoring-insight-table th { background: #fff !important; color: #3f3f4c !important;' in template


def test_owners_take_their_colours_in_one_order_and_cards_without_a_breakdown_ask_to_recalculate() -> None:
    from src.modules.scoring.scoring_act_slides import owner_palette
    from src.modules.scoring.scoring_themes import THEMES, use_theme
    from src.modules.scoring.scoring_where_to_act import owner_cards, owner_order
    # The owners of the UK measurements first, Vendor B before Vendor A (their colours swapped), the others by name.
    assert owner_order(['Vendor A', 'Region X', 'Vendor B', 'VMO2 South', 'VMO2 North', '']) == [
        'VMO2 North', 'VMO2 South', 'Vendor B', 'Vendor A', 'Region X']
    with use_theme('ericsson'):
        color = owner_palette(['Vendor A', 'Vendor B', 'VMO2 North', 'VMO2 South'])
        categories = THEMES['ericsson']['categories']
        assert (color('Vendor B'), color('Vendor A'), color('Nobody')) == (categories[2], categories[3], '#9AA3AD')
    # Results calculated before the points of each owner were kept per City or route: no zeros, None.
    region = {'field': 'Region', 'operator': 'VF', 'label': 'VF', 'color': '#E60000', 'is_reference': False, 'environment': 'Combined',
              'context': {}, 'areas': [{'name': 'Vendor A', 'points': 5.0, 'share': 1.0}], 'total': 5.0}
    cards = owner_cards([region], {}, [], lambda _context: 1.0)[0]['cards']
    assert cards[0]['owner'] == 'Vendor A' and cards[0]['settings'] is None
    cards = owner_cards([{**region, 'city_losses': {'Vendor A': {'Leeds': 5.0}}}], {'Leeds': {'kind': 'place', 'setting': 'Cities'}},
                        [], lambda _context: 1.0)[0]['cards']
    assert cards[0]['settings'] == {'Cities': 5.0, 'Towns': 0.0, 'Roads and railways': 0.0}
