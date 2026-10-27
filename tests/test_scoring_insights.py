"""NetCheck-style scoring insights: location cards, KPI GAP profiles, trends and campaign comparisons."""
from __future__ import annotations

from io import BytesIO

import pytest
from pptx import Presentation

from src.modules.column_names import compact_campaign_value
from src.modules.scoring_exports import export_scoring_powerpoint
from src.modules.scoring_views import build_scoring_views
from tests.scoring_synthetic import CITIES, most_reliable_result, synthetic_result
from tests.test_scoring_exports import TEMPLATE


def _insights(levels=('Operator', 'City', 'Campaign'), **kwargs):
    job, result = synthetic_result(levels=levels, **kwargs)
    return job, result, build_scoring_views(job, result)['insights']


def _combined(items):
    return [item for item in items if item['environment'] == 'Combined']


def test_location_cards_scale_each_city_to_the_full_maximum():
    _job, result, insights = _insights(levels=('Operator', 'City'))
    groups = _combined(insights['location_cards'])
    assert len(groups) == 1
    group = groups[0]
    assert group['level'] == 'City'
    assert [card['label'] for card in group['cards']] == sorted(CITIES)
    assert group['maximum'] == pytest.approx(1000)
    assert group['max_voice'] + group['max_data'] == pytest.approx(1000)
    london = next(card for card in group['cards'] if card['label'] == 'London')
    ee = next(item for item in london['operators'] if item['operator'] == 'EE')
    expected = next(row for row in result['totals'] if row['city'] == 'London' and row['operator'] == 'EE'
                    and row['environment'] == 'Combined' and row['category'] == 'Overall')
    assert ee['total'] == pytest.approx(expected['weighted_points'])
    assert ee['voice'] + ee['data'] == pytest.approx(ee['total'])


def test_location_cards_need_two_to_twelve_locations():
    _job, _result, insights = _insights(levels=('Operator', 'City'), cities=('London',))
    assert insights['location_cards'] == []
    many = tuple(f'City {index}' for index in range(13))
    _job, _result, insights = _insights(levels=('Operator', 'City'), cities=many)
    assert insights['location_cards'] == []


def test_location_cards_scale_a_city_measured_in_one_environment():
    job, result = synthetic_result(levels=('Operator', 'City'), cities=('London', 'Leeds'))
    result['scoring'] = [row for row in result['scoring']
                         if not (row['city'] == 'London' and row['environment'] == 'DriveConnectionroad')]
    insights = build_scoring_views(job, result)['insights']
    group = _combined(insights['location_cards'])[0]
    london = next(card for card in group['cards'] if card['label'] == 'London')
    ee = next(item for item in london['operators'] if item['operator'] == 'EE')
    city_points = sum(row['weighted_points'] for row in result['scoring']
                      if row['city'] == 'London' and row['operator'] == 'EE' and row['environment'] == 'DriveCity')
    assert group['scaled'] is True
    assert ee['total'] == pytest.approx(city_points * 1000 / 650)


def test_campaign_trend_needs_two_campaigns():
    _job, _result, insights = _insights(campaigns=('2026-Q2',))
    assert insights['campaign_trends'] == []
    _job, _result, insights = _insights(campaigns=('2026-Q1', '2026-Q2'))
    assert _combined(insights['campaign_trends'])[0]['campaigns'] == ['26-Q1', '26-Q2']
    _job, _result, insights = _insights()
    trends = _combined(insights['campaign_trends'])
    assert len(trends) == len(CITIES)
    assert trends[0]['campaigns'] == ['25-Q2', '25-Q3', '25-Q4', '26-Q1', '26-Q2']
    assert {series['operator'] for series in trends[0]['series']} == {'EE', 'O2 UK', 'Three UK', 'Vodafone UK'}


def test_campaign_comparison_subtracts_the_previous_campaign():
    _job, result, insights = _insights(campaigns=('2026-Q1', '2026-Q2'))
    comparison = next(item for item in _combined(insights['campaign_comparisons'])
                      if item['operator'] == 'EE' and 'London' in item['title'])
    assert (comparison['previous_campaign'], comparison['latest_campaign']) == ('26-Q1', '26-Q2')
    deltas = [row['delta'] for row in comparison['rows']]
    assert deltas == sorted(deltas)
    assert comparison['total_delta'] == pytest.approx(sum(deltas))

    def total(campaign):
        return next(row['weighted_points'] for row in result['totals']
                    if row['city'] == 'London' and row['operator'] == 'EE' and row['campaign'] == campaign
                    and row['environment'] == 'Combined' and row['category'] == 'Overall')
    assert comparison['total_delta'] == pytest.approx(total('2026-Q2') - total('2026-Q1'))


def test_campaign_comparison_keeps_every_campaign_to_compare_any_two():
    _job, result, insights = _insights()
    comparison = next(item for item in _combined(insights['campaign_comparisons'])
                      if item['operator'] == 'EE' and 'London' in item['title'])
    assert comparison['campaigns'] == ['25-Q2', '25-Q3', '25-Q4', '26-Q1', '26-Q2']
    # The points of each KPI in every campaign add up to the scoring of that campaign (named as the charts show it).

    def total(campaign):
        return next(row['weighted_points'] for row in result['totals']
                    if row['city'] == 'London' and row['operator'] == 'EE' and compact_campaign_value(row['campaign']) == campaign
                    and row['environment'] == 'Combined' and row['category'] == 'Overall')
    for index, campaign in enumerate(comparison['campaigns']):
        points = sum(kpi['values'][index]['points'] for kpi in comparison['kpis'] if kpi['values'][index])
        assert points == pytest.approx(total(campaign))
    # The latest and previous campaigns give the rows of the default comparison.
    latest = {row['kpi_code']: row['delta'] for row in comparison['rows']}
    for kpi in comparison['kpis']:
        before, after = kpi['values'][-2], kpi['values'][-1]
        if before and after:
            assert latest[kpi['kpi_code']] == pytest.approx(after['points'] - before['points'])
    # One methodology for every campaign: no category changed, and every KPI is compared on its own.
    assert comparison['changed_categories'] == []
    assert {row['kind'] for row in comparison['rows']} == {'kpi'}


def _video_kpis():
    """The KPIs of ticket #5: 26-Q3 splits the Video Stream points of YouTube with the new TikTok KPIs."""
    def kpi(code, name, category, service, before, after, maxima):
        return {'kpi_code': code, 'kpi': name, 'category': category, 'service': service, 'max_points': maxima,
                'values': [None if before is None else {'value': before[0], 'points': before[1]},
                           None if after is None else {'value': after[0], 'points': after[1]}]}
    return [
        kpi('K28', 'YOUTUBE SUCCESS RATIO', 'VIDEO STREAM', 'Data', (99.70, 79.86), (99.72, 52.04), [83.2, 54.08]),
        kpi('K30', 'YOUTUBE IRRITATING EXPERIENCE', 'VIDEO STREAM', 'Data', (0.23, 40.85), (0.71, 25.51), [41.6, 27.04]),
        kpi('K33', 'TIK TOK SUCCESS RATIO', 'VIDEO STREAM', 'Data', None, (99.85, 28.54), [None, 29.12]),
        kpi('K35', 'TIK TOK IRRITATING EXPERIENCE', 'VIDEO STREAM', 'Data', None, (0.15, 14.39), [None, 14.56]),
        kpi('K1', 'CALL SUCCESS RATIO', 'CLASSIC CALLS', 'Voice', (99.63, 108.84), (99.76, 110.33), [113.0, 113.0]),
        kpi('K2', 'CALL SETUP TIME', 'CLASSIC CALLS', 'Voice', (1.91, 12.57), (1.95, 12.50), [13.0, 13.0]),
        # Measured in the latest campaign only, with the same methodology: no Δ, as before.
        kpi('K7', 'WHATSAPP CALL SUCCESS RATIO', 'WHATSAPP CALLS', 'Voice', None, (99.0, 80.0), [86.0, 86.0]),
    ]


def test_campaign_comparison_compares_a_category_whose_methodology_changed_as_a_whole():
    from src.modules.scoring_insights import comparison_rows
    compared = comparison_rows(_video_kpis(), 0, 1)
    rows = compared['rows']
    assert compared['changed_categories'] == ['VIDEO STREAM']
    # The category row (YouTube and TikTok together) and its KPIs, which have no Δ of their own.
    category = next(index for index, row in enumerate(rows) if row['kind'] == 'category')
    video = rows[category]
    assert (video['kpi'], video['service']) == ('VIDEO STREAM', 'Data')
    assert video['previous_points'] == pytest.approx(79.86 + 40.85)
    assert video['latest_points'] == pytest.approx(52.04 + 25.51 + 28.54 + 14.39)
    assert video['delta'] == pytest.approx(video['latest_points'] - video['previous_points'])
    members = rows[category + 1:category + 5]
    assert [row['kpi_code'] for row in members] == ['K28', 'K30', 'K33', 'K35']
    assert all(row['in_category'] and row['delta'] is None for row in members)
    assert members[0]['previous_points'] == 79.86 and members[2]['previous_points'] is None
    # The other categories are compared KPI by KPI, from the largest loss; the KPI without a Δ goes last.
    deltas = [(row.get('kpi_code') or row['kpi'], row['delta']) for row in rows if not row.get('in_category')]
    assert [code for code, _delta in deltas] == ['VIDEO STREAM', 'K2', 'K1', 'K7']
    assert deltas[-1][1] is None
    # The Scoring Points Gap adds up the Δ shown: the change of the whole score but for the KPI measured once.
    assert compared['total_delta'] == pytest.approx(sum(delta for _code, delta in deltas if delta is not None))
    assert compared['total_delta'] == pytest.approx(video['delta'] + (110.33 - 108.84) + (12.50 - 12.57))
    # Compared the other way round, the category still is.
    assert comparison_rows(_video_kpis(), 1, 0)['changed_categories'] == ['VIDEO STREAM']


def test_campaign_comparison_without_maximum_points_compares_every_kpi_on_its_own():
    from src.modules.scoring_insights import comparison_rows
    kpis = [{key: value for key, value in kpi.items() if key != 'max_points'} for kpi in _video_kpis()]
    compared = comparison_rows(kpis, 0, 1)
    assert compared['changed_categories'] == []
    assert {row['kind'] for row in compared['rows']} == {'kpi'}
    assert compared['total_delta'] == pytest.approx(sum(row['delta'] for row in compared['rows'] if row['delta'] is not None))


def test_campaign_comparison_names_the_methodologies_of_a_result_by_campaign():
    import copy

    from src.modules import scoring
    from src.modules.saved_filters import AGGREGATION_CONTRACT_VERSION
    from src.modules.scoring_config import validate_scoring_profiles
    from src.modules.scoring_insights import comparison_note
    from src.modules.scoring_methodologies import merge_results, methodology_groups
    from tests.scoring_fixtures import scoring_configuration
    from tests.test_scoring_history import _rows

    first = scoring_configuration()
    # The later methodology gives 35% of the YouTube success points to a TikTok KPI of the same category.
    second = copy.deepcopy(first)
    youtube = next(metric for metric in second['metrics'] if metric['code'] == 'K28')
    tiktok = copy.deepcopy(youtube)
    tiktok.update({'code': 'K33', 'kpi': 'TIK TOK VIDEO STREAMING SUCCESS RATIO [%]'})
    for name, context in youtube['contexts'].items():
        tiktok['contexts'][name]['max_points'] = context['max_points'] * .35
        context['max_points'] *= .65
    second['metrics'].append(tiktok)
    profiles = validate_scoring_profiles({'active_profile_id': 'netcheck-2026', 'profiles': [
        {'id': 'netcheck-2026', 'name': 'NetCheck 2026', 'configuration': first, 'campaigns': {'to': '2026-Q2'}},
        {'id': 'netcheck-2026-q3', 'name': 'NetCheck 2026-Q3', 'configuration': second, 'campaigns': {'from': '2026-Q3'}},
    ]})
    parts = []
    for (group, campaign), seed in zip(zip(methodology_groups(profiles, ['2026-Q2', '2026-Q3']), ('2026-Q2', '2026-Q3')),
                                       (3, 5)):
        frames = {kind: _rows(kind, seed).assign(Campaign=campaign) for kind in ('data', 'voice', 'speech')}
        parts.append((group, scoring.calculate_scoring(frames, ['Operator', 'Campaign'], baseline_operator='EE',
                                                       configuration=group['configuration'])))
    views = build_scoring_views({'levels': ['Operator', 'Campaign'],
                                 'aggregation_contract_version': AGGREGATION_CONTRACT_VERSION}, merge_results(parts))
    comparison = next(item for item in _combined(views['insights']['campaign_comparisons']) if item['operator'] == 'EE')
    assert comparison['methodologies'] == ['NetCheck 2026', 'NetCheck 2026-Q3']
    assert (comparison['previous_methodology'], comparison['latest_methodology']) == ('NetCheck 2026', 'NetCheck 2026-Q3')
    assert comparison['changed_categories'] == ['VIDEO STREAM']
    video = next(row for row in comparison['rows'] if row['kind'] == 'category')
    kpis = {kpi['kpi_code']: kpi for kpi in comparison['kpis']}
    assert kpis['K33']['max_points'][0] is None and kpis['K33']['max_points'][1] > 0
    assert kpis['K28']['max_points'][1] == pytest.approx(kpis['K28']['max_points'][0] * .65)
    assert video['latest_points'] == pytest.approx(sum(
        kpis[code]['values'][1]['points'] for code in ('K28', 'K29', 'K30', 'K33') if kpis[code]['values'][1]))
    # Every KPI measured in both campaigns: the gap is the change of the whole score, TikTok included.
    assert comparison['total_delta'] == pytest.approx(
        sum(kpi['values'][1]['points'] for kpi in comparison['kpis'] if kpi['values'][1])
        - sum(kpi['values'][0]['points'] for kpi in comparison['kpis'] if kpi['values'][0]))
    assert comparison_note(comparison) == (
        'VIDEO STREAM: the methodology changed between 26-Q2 (NetCheck 2026) and 26-Q3 (NetCheck 2026-Q3), so the '
        'category is compared as a whole and its KPIs have no Δ of their own.')


def test_campaign_comparison_slides_show_a_category_whose_methodology_changed():
    from pptx.util import Inches

    from src.modules.scoring_insight_slides import add_campaign_comparison_slides
    from src.modules.scoring_insights import comparison_rows
    presentation = Presentation(TEMPLATE)
    comparison = {'operator': 'EE', 'label': 'EE', 'color': '#009A9A', 'title': '',
                  'previous_campaign': '26-Q2', 'latest_campaign': '26-Q3',
                  'previous_methodology': 'NetCheck 2026', 'latest_methodology': 'NetCheck 2026-Q3',
                  **comparison_rows(_video_kpis(), 0, 1)}

    def new_slide(presentation, _title, _subtitle):
        slide = presentation.slides.add_slide(presentation.slide_layouts[-1])
        slide.shapes.add_textbox(Inches(0), Inches(0), Inches(1), Inches(1))
        return slide
    add_campaign_comparison_slides(presentation, [comparison], scoring_label='Best Network', subtitle='', new_slide=new_slide)
    table = next(shape.table for shape in presentation.slides[-1].shapes if shape.name == 'Scoring Campaign Comparison Table')
    lines = [[cell.text for cell in row.cells] for row in table.rows]
    video = next(line for line in lines if line[1] == 'VIDEO STREAM · methodology changed')
    delta = next(row['delta'] for row in comparison['rows'] if row['kind'] == 'category')
    assert video[2].strip() == video[4].strip() == '' and video[6] == f'{delta:,.2f}'
    assert next(line for line in lines if line[1] == 'TIK TOK SUCCESS RATIO')[6] == '—'
    assert lines[-2][-1] == f"{comparison['total_delta']:+,.2f}"
    assert lines[-1][0].startswith('VIDEO STREAM: the methodology changed between 26-Q2 (NetCheck 2026) and 26-Q3')


def test_kpi_gap_profiles_rank_points_lost_and_reference_gaps():
    _job, _result, insights = _insights(levels=('Operator',))
    profile = next(item for item in _combined(insights['kpi_gap_profiles']) if item['operator'] == 'Three UK')
    assert profile['reference'] == 'EE'
    assert profile['columns'] == ['DriveCity', 'DriveConnectionroad']
    lost = [row['total_gap_to_maximum'] for row in profile['to_maximum']]
    assert lost == sorted(lost, reverse=True) and min(lost) >= 0
    gaps = [row['total_gap_to_reference'] for row in profile['to_reference']]
    assert gaps == sorted(gaps)
    row = profile['to_maximum'][0]
    assert row['total_gap_to_maximum'] == pytest.approx(sum(row['gap_to_maximum'].values()))
    # Every KPI carries its type, so the tables mark the Reliable KPIs (those of the Most Reliable scoring) and the Diff ones.
    assert {item['kpi_code'] for item in profile['to_maximum'] if item['kpi_type'] == 'Reliable'} == {
        'K1', 'K4', 'K7', 'K8', 'K12', 'K14', 'K16', 'K21', 'K27', 'K28'}
    assert all(item['kpi_type'] in ('Reliable', 'Diff') for item in profile['to_maximum'])
    assert 'underline_most_reliable' not in profile


def test_kpi_gap_profiles_count_in_the_points_of_a_scaled_combined():
    from src.modules.scoring import apply_environment_scaling

    job, result = synthetic_result(levels=('Operator',))
    # Without Connecting Roads results in any series, All Environments scales Drive - City up to the full maximum.
    result['scoring'] = [row for row in result['scoring'] if row['environment'] != 'DriveConnectionroad']
    result.pop('environment_scaling')
    apply_environment_scaling(result, 'EE')
    assert result['environment_scaling']['scaled_environments'] == ['DriveConnectionroad']
    insights = build_scoring_views(job, result)['insights']
    stake = {item['operator']: item for item in _combined(insights['points_at_stake'])[0]['operators']}
    for profile in _combined(insights['kpi_gap_profiles']):
        assert profile['columns'] == ['DriveCity']
        # The points lost per KPI add up to those of Where the points go, the GAP to the reference to its points.
        lost = sum(row['total_gap_to_maximum'] for row in profile['to_maximum'])
        assert lost == pytest.approx(stake[profile['operator']]['lost'])
        if profile['operator'] != profile['reference']:
            gap = sum(row['total_gap_to_reference'] for row in profile['to_reference'])
            assert gap == pytest.approx(stake[profile['operator']]['points'] - stake[profile['reference']]['points'])
    # Drive - City alone keeps its own points.
    city = next(item for item in insights['kpi_gap_profiles'] if item['environment'] == 'DriveCity')
    assert sum(row['total_gap_to_maximum'] for row in city['to_maximum']) == pytest.approx(
        stake[city['operator']]['lost'] * 650 / 1000)


def test_most_reliable_insights_use_its_points():
    job, result = synthetic_result(levels=('Operator', 'City'))
    reliable = most_reliable_result(result, 'EE')
    insights = build_scoring_views(job, reliable)['insights']
    group = _combined(insights['location_cards'])[0]
    assert group['maximum'] == pytest.approx(1000)
    assert (group['max_voice'], group['max_data']) == (pytest.approx(350), pytest.approx(650))
    profile = _combined(insights['kpi_gap_profiles'])[0]
    assert len(profile['to_maximum']) == 10
    assert all(item['kpi_type'] == 'Reliable' for item in profile['to_maximum'])


def test_powerpoint_adds_the_insight_slides_to_all_environments():
    job, result = synthetic_result()
    presentation = Presentation(BytesIO(export_scoring_powerpoint(job, result, TEMPLATE)))
    titles = [slide.shapes.title.text_frame.text if slide.shapes.title is not None else '' for slide in presentation.slides]
    first = [title.split('\n')[0] for title in titles]
    for heading in ('Best Network Scoring per City', 'Best Network Scoring Trend', 'Best Network Campaign Comparison',
                    'Most Reliable Network Scoring per City', 'Most Reliable Network Scoring Trend'):
        assert heading in first
    # The KPI GAP Profile shows the compared operators two by two.
    assert any(title.startswith('KPI GAP Profile — ') and 'Three UK' in title and title.endswith(' vs EE') for title in first)
    # Only All Environments gets them, and the cards only for the latest campaign.
    insight_titles = [title for title in titles if 'Scoring per City' in title or 'Profile' in title]
    # All Environments subtitles name only the scoring (and the context), never an environment.
    assert all('Drive - ' not in title for title in insight_titles)
    assert sum(1 for title in first if title == 'Best Network Scoring per City') == 1
    cards = next(slide for slide, title in zip(presentation.slides, first) if title == 'Best Network Scoring per City')
    charts = [shape for shape in cards.shapes if shape.name.startswith('Scoring Location Chart')]
    assert len(charts) == len(CITIES)
    # The cards show the operator labels as mapped, never shortened.
    assert set(charts[0].chart.plots[0].categories) == {'EE', 'O2 UK', 'Three UK', 'Vodafone UK'}
    assert next(shape for shape in cards.shapes if shape.name == 'Scoring Location Cards Note').text_frame.text.count(
        '1,000 points') == 1


def test_profile_bars_line_up_with_their_rows():
    job, result = synthetic_result(levels=('Operator',))
    presentation = Presentation(BytesIO(export_scoring_powerpoint(job, result, TEMPLATE)))
    slides = [(slide, slide.shapes.title.text_frame.text.split('\n')[0]) for slide in presentation.slides
              if slide.shapes.title is not None]
    profiles = [slide for slide, title in slides if title.startswith('KPI GAP Profile')]
    # The KPI GAP Profile shows the GAP to the reference of two compared operators per slide, never the reference.
    assert profiles and all(' vs EE' in title for slide, title in slides if slide in profiles)
    assert all(not title.endswith('(reference)') for _slide, title in slides)
    assert [shape.name for shape in profiles[0].shapes if shape.name.startswith('Scoring KPI GAP')].count(
        'Scoring KPI GAP Reference Table') == 2
    assert not any(shape.name == 'Scoring KPI GAP Maximum Table' for slide in profiles for shape in slide.shapes)
    # The points lost against the maximum are in Points Lost, the reference operator included.
    lost = [(slide, title) for slide, title in slides if title.startswith('Points lost per KPI')]
    assert lost and any('EE' in title for _slide, title in lost)
    slide = lost[0][0]
    table_shape = next(shape for shape in slide.shapes if shape.name == 'Scoring KPI GAP Maximum Table')
    table = table_shape.table
    first_row_top = table_shape.top + table.rows[0].height + table.rows[1].height
    bars = sorted((shape for shape in slide.shapes if shape.name == 'Scoring GAP Bar' and shape.left < table_shape.left
                   + table_shape.width), key=lambda shape: shape.top)
    # The first row is a category, with its subtotal; its first KPI has the first bar.
    assert bars and bars[0].top > first_row_top + table.rows[2].height
    assert bars[0].top < first_row_top + table.rows[2].height + table.rows[3].height
    note = next(shape for shape in slide.shapes if shape.name == 'Scoring KPI GAP Profile Note')
    assert note.top > table_shape.top + sum(row.height for row in table.rows)
    bold = [run.text for run in note.text_frame.paragraphs[0].runs if run.font.bold]
    operator = lost[0][1].removeprefix('Points lost per KPI — ').split(' & ')[0]
    assert bold[0] == operator and any('Best Network points' in text for text in bold)


def test_kpi_gap_profile_slides_cover_every_selected_city():
    from src.modules.scoring_insight_slides import MAX_PROFILE_SCOPES, _block_profiles

    cities = ['Belfast', 'Bristol', 'Cardiff', 'Edinburgh', 'Leeds', 'London', 'Sheffield']
    profiles = [{'operator': operator, 'reference': 'EE', 'context': {'city': city}}
                for city in cities for operator in ('VF', 'EE', '3')]
    kept = _block_profiles(profiles)
    # One profile per city and compared operator, the reference included (with its Gap to Maximum only).
    assert [(item['context']['city'], item['operator']) for item in kept] == [
        (city, operator) for city in cities for operator in ('VF', 'EE', '3')]
    assert MAX_PROFILE_SCOPES == 12


@pytest.mark.parametrize(('code', 'kpi_type', 'formula', 'kind'), [
    ('K1', 'Reliable', '100 * SUM(Call_Status == "Completed") / COUNT(Call_Status)', 'not_completed'),
    ('K12', 'Reliable', '100 * SUM(CONTAINS(Test_Result, "Completed")) / COUNT(Test_Result)', 'not_completed'),
    # Multi RAB is a Diff KPI, but its transfers that did not succeed did not complete.
    ('K11', 'Diff', '100 * SUM(Test_Status == "Successful") / COUNT(Call_Status)', 'not_completed'),
    ('K4', 'Reliable', '100 * SUM(LQ <= 1.6) / COUNT(Session_Type)', 'below_minimum'),
    ('K16', 'Reliable', '100 * COUNT(Mean_Data_Rate > 2) / COUNT(Mean_Data_Rate)', 'below_minimum'),
    # Disturbed and impaired calls completed: below the threshold, not a call that did not complete.
    ('K6', 'Diff', '100 * SUM(Call_Status == "Completed" AND Disturbed_and_Impaired_Call == "Yes") / COUNT(Call_Status)', 'below_par'),
    ('K17', 'Diff', '100 * COUNT(Mean_Data_Rate > 5) / COUNT(Mean_Data_Rate)', 'below_par'),
    ('K2', 'Diff', 'AVG(Call_Setup_Time)', 'quality'),
    ('K20', 'Diff', 'PCT90(Mean_Data_Rate)', 'quality'),
    ('K31', 'Diff', '100 * SUM(totalpacketlost) / SUM(Packets_Sent)', 'quality'),
])
def test_each_kpi_loses_its_points_in_one_kind(code, kpi_type, formula, kind):
    from src.modules.scoring_insights import loss_kind

    assert loss_kind({'kpi_code': code, 'kpi_type': kpi_type, 'kpi': code}, {code: formula}) == kind


def test_where_the_points_go_says_what_each_kind_counts():
    _job, _result, insights = _insights(levels=('Operator',))
    stake = _combined(insights['points_at_stake'])[0]
    kinds = {kind['key']: kind for kind in stake['kinds']}
    assert kinds['not_completed']['label'] == 'Not completed (NQ)' and 'Non-Qualified Calls' in kinds['not_completed']['description']
    assert kinds['below_minimum']['label'] == 'Below the minimum'
    # The KPIs of the methodology each kind holds, without their units, once each.
    every = [name for kind in stake['kinds'] for name in kind['kpis']]
    assert every and len(every) == len(set(every)) and not any(name.endswith(']') for name in every)
    for row in stake['operators']:
        assert sum(row['parts'].values()) == pytest.approx(row['lost'])
