import json
import re
from io import BytesIO

import pandas as pd
import pytest

import src.DriveTestAnalyzer as core
from src.modules import cdr_reporting
from src.modules import design_comments as comments
from src.modules.ppt_designer import DesignDefinition

OPERATOR_CAMPAIGN = [['Operator'], ['Campaign']]


def rsrp_series(operator, campaign, samples, p10, p50, weak):
    return {'key': [operator, campaign], 'stats': {
        'n': samples, 'p10': p10, 'p50': p50, 'p90': p50 + 12, 'mean': p50, 'bucket_shares': [weak, .3, .3, .2, .2 - weak],
    }}


RSRP_CDF = {'type': 'cdf', 'metric': 'NR RSRP', 'dimensions': OPERATOR_CAMPAIGN, 'bucket_edges': [-110, -100, -90, -80], 'series': [
    rsrp_series('Vodafone', 'UK_Q2_2026', 18432, -111.9, -97.6, .094),
    rsrp_series('Vodafone', 'UK_Q3_2026', 20117, -108.3, -93.8, .051),
    rsrp_series('EE', 'UK_Q2_2026', 19000, -105.0, -90.4, .04),
    rsrp_series('EE', 'UK_Q3_2026', 19880, -104.6, -90.1, .032),
    rsrp_series('O2', 'UK_Q2_2026', 15000, -114.0, -100.2, .13),
    rsrp_series('O2', 'UK_Q3_2026', 15500, -115.0, -101.5, .118),
    rsrp_series('Three', 'UK_Q3_2026', 8, -95.0, -80.0, .01),
]}


def texts(charts, **options):
    return [item['text'] for item in comments.slide_comments(charts, **options)]


def test_cdf_comments_follow_the_focus_operator_against_the_leader_and_the_previous_campaign():
    written = texts([{'index': 0, 'title': 'NR RSRP', 'kpi': 'NR_RSRP', 'model': RSRP_CDF}], focus_operators=['Vodafone'])
    assert written == [
        'Vodafone median NR RSRP improves by 3.8 dB vs 26-Q2 (−97.6 → −93.8 dBm).',
        'EE leads in median NR RSRP (−90.1 dBm); Vodafone trails by 3.7 dB (−93.8 dBm); the gap narrows from 7.2 dB in 26-Q2.',
        'NR RSRP samples below −110 dBm: Vodafone 5.1% (−4.3 pp vs 26-Q2); highest: O2 (11.8%).',
        'O2 median NR RSRP degrades by 1.3 dB vs 26-Q2 (−100.2 → −101.5 dBm).',
    ]
    # Three has too few samples to lead, and the narrow "comments right" box takes three comments.
    assert not any(text.startswith('Three') for text in written)
    assert len(texts([{'index': 0, 'kpi': 'NR_RSRP', 'model': RSRP_CDF}], layout='Title + 1 rows + 1 columns + comments right')) == 3


def test_without_focus_operators_the_comments_follow_the_leader_and_skip_hidden_legend_items():
    written = texts([{'index': 0, 'kpi': 'NR_RSRP', 'model': RSRP_CDF, 'hidden': ['O2']}])
    assert written[0] == 'EE leads in median NR RSRP (−90.1 dBm), 3.7 dB ahead of Vodafone.'
    assert not any('O2' in text for text in written)


def test_bar_and_stacked_comments_read_their_values_and_class_shares():
    bars = {'type': 'mean_bar', 'metric': 'Mean Data Rate', 'aggregation': 'mean', 'dimensions': OPERATOR_CAMPAIGN, 'bars': [
        {'key': ['VF', '2026-Q2'], 'value': 152.0, 'samples': 900}, {'key': ['VF', '2026-Q3'], 'value': 180.0, 'samples': 950},
        {'key': ['EE', '2026-Q2'], 'value': 199.0, 'samples': 900}, {'key': ['EE', '2026-Q3'], 'value': 212.0, 'samples': 950},
    ]}
    assert texts([{'index': 0, 'kpi': 'Mean Data Rate', 'model': bars}], focus_operators=['VF'])[:2] == [
        'VF Mean Data Rate improves by 16% vs 26-Q2 (152 → 180).',
        'EE leads in Mean Data Rate (212); VF trails by 15% (180); the gap narrows from 24% in 26-Q2.',
    ]
    results = {'type': 'status_100', 'states': [{'name': 'Completed'}, {'name': 'Dropped'}, {'name': 'Failed'}],
               'dimensions': OPERATOR_CAMPAIGN, 'records': [
                   {'key': ['VF', '2026-Q2'], 'shares': [.974, .01, .016], 'samples': 2000},
                   {'key': ['VF', '2026-Q3'], 'shares': [.987, .005, .008], 'samples': 2100},
                   {'key': ['EE', '2026-Q3'], 'shares': [.989, .004, .007], 'samples': 2050}]}
    assert texts([{'index': 0, 'kpi': 'Test_Result', 'model': results}], focus_operators=['VF']) == [
        'VF share of Dropped + Failed falls from 2.6% to 1.3% vs 26-Q2 (−1.3 pp).',
        'VF is on par with EE in share of Dropped + Failed (1.3% vs 1.1%).',
    ]
    quality = {'type': 'status_100', 'states': [{'name': '< 3'}, {'name': '≥ 3'}], 'dimensions': OPERATOR_CAMPAIGN, 'records': [
        {'key': ['VF', '2026-Q2'], 'shares': [.079, .921], 'samples': 3000},
        {'key': ['VF', '2026-Q3'], 'shares': [.058, .942], 'samples': 3000}]}
    assert texts([{'index': 0, 'kpi': 'LQ', 'model': quality}], focus_operators=['VF']) == [
        'VF share of LQ ≥ 3 rises from 92.1% to 94.2% vs 26-Q2 (+2.1 pp).',
    ]


def test_unsupported_and_outdated_models():
    assert texts([{'index': 0, 'kpi': 'Latitude', 'model': {'type': 'map', 'series': []}}]) == []
    assert comments.needs_rebuild({'type': 'cdf', 'series': []})
    assert not comments.needs_rebuild({'type': 'cdf', 'series': [], 'dimensions': []})
    assert not comments.needs_rebuild({'type': 'table'})
    assert comments.kpi_semantics('Call_Setup_Time').direction == -1
    assert comments.kpi_semantics('Packet Delay Variation Score').direction == 1


def rates_cdr() -> bytes:
    """A Data CDR of the rates of A and B over two campaigns (one failed test of A in each)."""
    rows = ['Operator,Campaign,Mean_Data_Rate,Test_Result,Test_Name,Test_Start_Time']
    for campaign, rates in (('UK_Q2_2026', {'A': 40, 'B': 80}), ('UK_Q3_2026', {'A': 60, 'B': 82})):
        for operator, rate in rates.items():
            for sample in range(12):
                result = 'Failed' if sample == 0 and operator == 'A' else 'Completed'
                rows.append(f'{operator},{campaign},{rate + sample % 3},{result},HTTP DL,2026-09-{sample + 1:02d}')
    return '\n'.join(rows).encode()


def prepare_rates_design(client):
    """A Design of two slides (rates of A and B over two campaigns, then their results), prepared."""
    client.post('/login', data={'username': 'super', 'password': 'super123'})
    uploaded = client.post('/datasets-analysis/upload', data={'dataset_kinds': 'data'}, files={
        'dataset_files': ('rates.csv', BytesIO(rates_cdr()), 'text/csv'),
    })
    assert uploaded.status_code == 200, uploaded.text
    core.repository.add_report_template('Comments test', (
        'Slide,Slide tittle,Slide Subtittle,Layout,Chart Tittle,CDR source,KPI,Chart type,Filters,Rows Split,Columns Split,Legend,Legend Position\n'
        '1,Rates,,Title and 2 columns + Comments,Rate CDF,CDR-Data,Mean_Data_Rate,CDF Line,,Operator,Campaign,,Top\n'
        '1,Rates,,Title and 2 columns + Comments,Rate mean,CDR-Data,Mean_Data_Rate,Average Vertical Bars,,Operator,Campaign,,Top\n'
        '2,Results,,Title and 1 column + Comments,Results,CDR-Data,Test_Result,100% Stacked Vertical Bars,,Operator,Campaign,,Top\n'
    ).encode(), is_default=False)
    core.repository.replace_operator_mapping_group(None, 'A', [], '#E60000', 'focus')
    definition = DesignDefinition(name='Rates', template='Comments test', datasets={'data': [1]}).model_dump(mode='json')
    saved = client.put('/api/ppt-designer/rates', json=definition)
    assert saved.status_code == 200, saved.text
    prepared = client.post('/api/ppt-designer/prepare', json=definition)
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    return body


def test_generate_comments_reads_the_open_slide_and_records_app_events(client):
    body = prepare_rates_design(client)
    slide = body['slides'][0]

    generated = client.post('/api/ppt-designer/rates/comments/generate', json={
        'token': body['token'], 'slide': slide['number'],
        'charts': [{'index': chart['index'], 'hidden': [], 'shown': []} for chart in slide['charts']],
    })
    assert generated.status_code == 200, generated.text
    result = generated.json()
    assert result['comment_key'] == slide['comment_key']
    assert result['engine'] == 'rules'
    written = [item['text'] for item in result['suggestions']]
    assert written and all(re.search(r'\b[AB]\b', text) for text in written)
    assert any(text.startswith('A median Mean Data Rate improves by') for text in written)
    assert {item['chart_index'] for item in result['suggestions']} == {chart['index'] for chart in slide['charts']}
    model = client.get(f"/api/ppt-designer/chart/{body['token']}/{slide['charts'][0]['index']}").json()
    assert model['dimensions'] == [['Operator'], ['Campaign']]
    assert model['series'][0]['stats']['n'] == 12

    results = body['slides'][1]
    generated_results = client.post('/api/ppt-designer/rates/comments/generate', json={'token': body['token'], 'slide': results['number']})
    assert generated_results.status_code == 200, generated_results.text
    # One failure in 12 tests is not significantly different from none.
    assert [item['text'] for item in generated_results.json()['suggestions']] == [
        'A is on par with B in share of Failed (8.3% vs 0%).', 'A share of Failed is stable vs 26-Q2 (8.3%).',
    ]

    added = client.patch('/api/ppt-designer/rates/comments', json={
        'slide_comments': {slide['comment_key']: written[:2]},
        'generated_slide': slide['comment_key'], 'generated_added': 2, 'token': body['token'],
    })
    assert added.status_code == 200, added.text
    assert added.json()['slide_comments'] == {slide['comment_key']: written[:2]}
    meta = added.json()['slide_comment_meta'][slide['comment_key']]
    assert meta['generated'] == written[:2] and meta['engine'] == 'rules'
    assert meta['selection_signature'] == body['selection_signature']
    # A generated comment edited by hand is no longer generated.
    edited = client.patch('/api/ppt-designer/rates/comments', json={'slide_comments': {slide['comment_key']: ['Mine', written[1]]}})
    assert edited.json()['slide_comment_meta'][slide['comment_key']]['generated'] == [written[1]]
    events = {row['action']: json.loads(row['details']) for row in core.repository.list_logs()}
    assert events['generate_design_comments']['suggestions'] == len(written)
    assert events['generate_design_comments']['engine'] == 'rules'
    assert events['add_generated_design_comments'] == {
        'id': 'rates', 'name': 'Rates', 'slide': slide['comment_key'], 'added': 2, 'engine': 'rules', 'comments': 2,
    }

    expired = client.post('/api/ppt-designer/rates/comments/generate', json={'token': 'missing', 'slide': 1})
    assert expired.status_code == 410


def test_generated_comments_name_their_selection_alike_on_every_deployment_with_the_same_cdrs(client):
    """A Design transferred to a deployment where the same CDRs were uploaded on their own (other ids, upload and
    processing times) keeps its generated comments up to date; other CDRs, campaigns or filters make them out of date."""
    body = prepare_rates_design(client)
    definition = DesignDefinition(name='Rates', template='Comments test').model_dump(mode='json')
    first = client.post('/api/ppt-designer/prepare', json=definition).json()
    # The same CDR deleted and uploaded again, as on another deployment.
    assert client.post(f"/datasets-analysis/delete/{body['cdrs']['data'][0]['id']}", follow_redirects=False).status_code == 303
    again = client.post('/datasets-analysis/upload', data={'dataset_kinds': 'data'}, files={
        'dataset_files': ('rates.csv', BytesIO(rates_cdr()), 'text/csv'),
    })
    assert again.status_code == 200, again.text
    second = client.post('/api/ppt-designer/prepare', json=definition)
    assert second.status_code == 200, second.text
    assert second.json()['cdrs']['data'][0]['id'] != first['cdrs']['data'][0]['id']
    assert second.json()['selection_signature'] == first['selection_signature']

    from src.modules.ppt_designer import comments_selection_signature
    design = DesignDefinition.model_validate(definition)
    cdrs = {'data': [{'id': 7, 'name': 'rates.csv', 'stage': 'final', 'campaigns': ['26-Q2', '26-Q3']}]}
    signature = comments_selection_signature(design, cdrs, {'data': [{'id': 7, 'row_count': 48}]})
    assert signature == comments_selection_signature(
        design, {'data': [{'id': 31, 'name': 'Rates (copy).csv', 'stage': 'final', 'campaigns': ['26-Q2', '26-Q3']}]},
        {'data': [{'id': 31, 'row_count': 48, 'processed_at': '2026-10-29T10:00:00'}]})
    assert signature != comments_selection_signature(design, cdrs, {'data': [{'id': 7, 'row_count': 50}]})
    assert signature != comments_selection_signature(
        design, {'data': [{**cdrs['data'][0], 'campaigns': ['26-Q3']}]}, {'data': [{'id': 7, 'row_count': 48}]})
    filtered = design.model_copy(update={'filters': {'Operator': ['A']}})
    assert signature != comments_selection_signature(filtered, cdrs, {'data': [{'id': 7, 'row_count': 48}]})


def test_the_other_chart_types_vendors_and_slides_read_together():
    failures = {'type': 'failure_count', 'mode': 'flat', 'states': [{'name': 'Failed'}, {'name': 'Dropped'}],
                'dimensions': OPERATOR_CAMPAIGN, 'tests': [1500, 1450, 1400],
                'rows': [{'key': ['VF', '2026-Q2'], 'values': [30, 8]}, {'key': ['VF', '2026-Q3'], 'values': [14, 3]},
                         {'key': ['EE', '2026-Q3'], 'values': [12, 2]}]}
    assert texts([{'index': 0, 'kpi': 'Call_Status', 'model': failures}], focus_operators=['VF'])[0] == (
        'VF share of Failed + Dropped falls from 2.5% to 1.2% vs 26-Q2 (−1.4 pp).')
    scatter = {'type': 'scatter', 'x_label': 'LTE PCell RSRP Avg', 'y_label': 'Mean Data Rate', 'dimensions': OPERATOR_CAMPAIGN,
               'series': [{'name': 'VF · 2026-Q3', 'key': ['VF', '2026-Q3'], 'stats': {
                   'n': 800, 'spearman': 0.41, 'x_q25': -105.3, 'x_q75': -88.1, 'y_median_low': 35.2, 'y_median_high': 80.4}}]}
    assert texts([{'index': 0, 'kpi': 'Mean Data Rate vs LTE PCell RSRP Avg', 'model': scatter}], focus_operators=['VF']) == [
        'For VF, Mean Data Rate rises with LTE PCell RSRP Avg (Spearman ρ = 0.41): median 35.2 at or below −105.3 dBm '
        'vs 80.4 at or above −88.1 dBm.']
    classes = ['< -110', '-110 to -100', '-100 to -90', '-90 to -80', '-80+']
    coverage = {'type': 'map', 'colour_metric': 'NR RSRP', 'dimensions': [['Value Bucket']],
                'series': [{'name': name, 'key': [name], 'samples': samples}
                           for name, samples in zip(classes, [840, 2000, 3000, 2500, 1660])],
                'areas': {'dimension': 'City', 'rows': [
                    {'name': 'Manchester', 'counts': [386, 300, 200, 150, 164]},
                    {'name': 'London', 'counts': [200, 900, 1500, 1500, 900]},
                    {'name': 'Leeds', 'counts': [254, 800, 1300, 850, 596]}]}}
    assert texts([{'index': 0, 'kpi': 'Latitude vs Longitude vs NR_RSRP', 'model': coverage, 'subject': 'VF'}]) == [
        'VF: Manchester holds 46% of the samples with NR RSRP below −110 dBm while it has 12% of the mapped samples.',
        'VF: 8.4% of the mapped samples have NR RSRP below −110 dBm.']
    table = {'type': 'table', 'headers': ['City', 'MEAN(Mean_Data_Rate)'],
             'rows': [['London', '85.20'], ['Leeds', '40.10'], ['Birmingham', '61.00']]}
    assert texts([{'index': 0, 'kpi': 'Mean Data Rate', 'model': table}]) == [
        'MEAN(Mean_Data_Rate): highest London (85.2), lowest Leeds (40.1).']
    vendors = {'type': 'cdf', 'metric': 'NR SINR', 'dimensions': [['Operator_Vendor'], ['Operator'], ['Campaign']], 'series': [
        {'key': [vendor, 'VF', campaign], 'stats': {'n': 900, 'p10': 1, 'p50': median, 'p90': 20, 'mean': median}}
        for vendor, campaign, median in (('Ericsson', '2026-Q3', 11.2), ('Nokia', '2026-Q3', 9.6), ('Mixed', '2026-Q3', 4.0))]}
    assert texts([{'index': 0, 'kpi': 'NR_SINR', 'model': vendors}], focus_operators=['VF'])[0] == (
        'For VF, median NR SINR is 1.6 dB higher in Ericsson areas than in Nokia areas (11.2 vs 9.6 dB).')

    def medians(metric, values, operator=''):
        dimensions = [['Campaign']] if operator else OPERATOR_CAMPAIGN
        return {'type': 'cdf', 'metric': metric, 'operator': operator, 'dimensions': dimensions, 'series': [
            {'key': [campaign] if operator else [name, campaign], 'stats': {'n': 500, 'p10': value - 8, 'p50': value, 'p90': value + 8, 'mean': value}}
            for name, value in values.items() for campaign in ('2026-Q3',)]}

    radio = [{'index': 0, 'kpi': 'LTE_SINR', 'model': medians('LTE SINR', {'VF': 12.3, 'EE': 13.0, 'O2': 11.0})},
             {'index': 1, 'kpi': 'NR_SINR', 'model': medians('NR SINR', {'VF': 8.2, 'EE': 9.1, 'O2': 6.6})}]
    assert 'Median NR SINR stays 3.9–4.4 dB below LTE SINR for every operator.' in texts(radio, focus_operators=['VF'])
    per_operator = [{'index': index, 'kpi': 'NR_SINR', 'model': medians('NR SINR', {operator: value}, operator)}
                    for index, (operator, value) in enumerate({'VF': 10.2, 'EE': 12.1, 'O2': 8.0}.items())]
    assert texts(per_operator) == ['Median NR SINR in 26-Q3: EE 12.1, VF 10.2, O2 8 dB.']


def failures_only(campaigns=('26-Q2', '26-Q3')):
    """A Count Stacked Horizontal Bars chart filtered on Call_Status IN (Failed, Dropped): each bar holds as many tests
    as failures (CDR type and city in rows, operator and campaign in columns, as Voice failures per City)."""
    previous, latest = campaigns
    bars = [
        ('MultiRAB', 'London', 'VF', previous, [0, 1]), ('MultiRAB', 'London', 'VF', latest, [0, 1]),
        ('VoLTE', 'London', 'VF', previous, [2, 0]), ('VoLTE', 'London', 'VF', latest, [0, 1]),
        ('VoLTE', 'Cardiff', 'VF', latest, [2, 0]), ('VoLTE', 'London', 'Three', previous, [7, 1]),
        ('VoLTE', 'London', 'Three', latest, [5, 0]), ('VoLTE', 'Bristol', 'Three', previous, [3, 0]),
        ('VoLTE', 'London', 'O2', previous, [4, 1]), ('VoLTE', 'London', 'O2', latest, [4, 1]),
        ('WhatsApp', 'London', 'O2', latest, [2, 1]), ('VoLTE', 'London', 'EE', previous, [2, 0]),
        ('VoLTE', 'London', 'EE', latest, [0, 0]),
    ]
    return {'type': 'failure_count', 'mode': 'hierarchy', 'states': [{'name': 'Failed'}, {'name': 'Dropped'}],
            'dimensions': [['Call_Family'], ['G Level 4'], ['Operator'], ['Campaign']],
            'records': [{'key': [family, city, operator, campaign], 'counts': counts, 'tests': sum(counts)}
                        for family, city, operator, campaign, counts in bars]}


def test_failure_charts_of_failed_and_dropped_tests_only_are_commented_by_their_counts():
    from src.modules.comment_writers import validate_comments

    chart = {'index': 0, 'title': 'Voice failures per City', 'kpi': 'Call_Status', 'model': failures_only()}
    assert texts([chart], focus_operators=['VF']) == [
        'VF: failed and dropped calls stable vs 26-Q2 (4 vs 3).',
        'O2 has the most failed and dropped calls in 26-Q3 (8: 6 failed, 2 dropped), ahead of Three 5, VF 4 and EE 0.',
        'VF: its largest count in 26-Q3 is in VoLTE · Cardiff (2 of 4).',
        'Three and O2 in VoLTE · London have the largest count in 26-Q3 (5 each).',
    ]
    [facts] = comments.chart_facts(0, chart['title'], chart['kpi'], chart['model'])
    assert {
        'EE has no failed or dropped calls in 26-Q3.',
        'VoLTE has the most failed and dropped calls in 26-Q3 (13 of 17), then WhatsApp (3).',
        'London has the most failed and dropped calls in 26-Q3 (15 of 17), then Cardiff (2).',
    } < {finding.text for finding in comments.chart_findings(facts, ['VF'])}
    # A significant change is named; a local Flex campaign is never compared with one of the whole country.
    model = failures_only()
    model['records'] += [{'key': ['VoLTE', 'Leeds', 'VF', '26-Q3'], 'counts': [9, 2], 'tests': 11}]
    assert texts([{**chart, 'model': model}], focus_operators=['VF'])[0] == (
        'VF: 15 failed and dropped calls in 26-Q3 vs 3 in 26-Q2 (+12).')
    flex = failures_only(('26-Q2-Flex', '26-Q3'))
    assert not any('26-Q2' in text for text in texts([{**chart, 'model': flex}], focus_operators=['VF']))
    # The legend items hidden in the viewer are left out of the counts and never named.
    hidden = texts([{**chart, 'hidden': ['Dropped', 'EE']}], focus_operators=['VF'])
    assert hidden[1] == 'O2 has the most failed calls in 26-Q3 (6), ahead of Three 5 and VF 2.'
    assert not any('EE' in text or 'dropped' in text for text in hidden)
    # The LLM writers receive the totals and the bars with a count, and only their figures pass.
    brief = comments.slide_brief([chart], focus_operators=['VF'])
    [briefed] = brief['charts']
    assert briefed['family'] == 'count'
    assert {'labels': {'Operator': 'O2', 'Campaign': '26-Q3'}, 'value': 8.0, 'samples': None, 'shown': '8',
            'extra': {'Failed': 6, 'Dropped': 2}} in briefed['records']
    assert validate_comments(brief['rules_comments'], brief) == (brief['rules_comments'], [])
    kept, problems = validate_comments(['O2 leads with 9 failed and dropped calls in 26-Q3.'], brief)
    assert not kept and problems[0].startswith('Figures not in the facts (9)')


def test_scatter_series_take_their_rank_correlation_without_scipy():
    # Spearman is the Pearson correlation of the ranks, tied values sharing their mean rank, as scipy calculates it.
    x, y = pd.Series([1, 2, 2, 5, 9]), pd.Series([3, 1, 4, 4, 8])
    assert cdr_reporting._scatter_stats(x, y)['spearman'] == pytest.approx(7.25 / 9.5)
    assert cdr_reporting._scatter_stats(x, -x)['spearman'] == pytest.approx(-1)


def test_generate_all_slides_writes_every_slide_as_its_mode_says(client):
    body = prepare_rates_design(client)
    rates, results = body['slides']
    client.patch('/api/ppt-designer/rates/comments', json={'slide_comments': {results['comment_key']: ['Written by hand']}})

    def generate_all(mode):
        started = client.post('/api/ppt-designer/rates/comments/generate-all', json={'token': body['token'], 'mode': mode})
        assert started.status_code == 202, started.text
        job = client.get(f"/api/ppt-designer/comment-jobs/{started.json()['job_id']}")
        assert job.status_code == 200, job.text
        assert job.json()['state'] == 'ready'
        return job.json()['result']

    only_empty = generate_all('empty')
    assert (only_empty['slides'], only_empty['written'], only_empty['kept']) == (2, 1, 1)
    assert only_empty['slide_comments'][results['comment_key']] == ['Written by hand']
    generated = only_empty['slide_comment_meta'][rates['comment_key']]['generated']
    assert generated and generated == only_empty['slide_comments'][rates['comment_key']]
    keeping_mine = generate_all('generated')
    assert keeping_mine['slide_comments'][results['comment_key']][0] == 'Written by hand'
    assert len(keeping_mine['slide_comments'][results['comment_key']]) > 1
    every = generate_all('all')
    assert 'Written by hand' not in every['slide_comments'][results['comment_key']]
    saved = client.get('/api/ppt-designer').json()['rates']
    assert saved['slide_comments'] == every['slide_comments']
    events = [json.loads(row['details']) for row in core.repository.list_logs() if row['action'] == 'generate_all_design_comments']
    assert [event['mode'] for event in events] == ['all', 'generated', 'empty']


def test_auto_comments_fill_the_ppt_without_changing_the_design(client):
    import time

    from pptx import Presentation

    prepare_rates_design(client)
    stored = client.get('/api/ppt-designer').json()['rates']
    client.patch('/api/ppt-designer/rates/comments', json={'slide_comments': {}})
    payload = {**stored, 'slide_comments': {}}
    queued = client.post('/api/ppt-designer/rates/export-ppt', json={'definition': payload, 'auto_comments': 'empty'})
    assert queued.status_code == 202, queued.text
    job_id = queued.json()['job_id']
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        job = next(item for item in client.get('/api/ppt-designer/ppt-jobs').json()['jobs'] if item['id'] == job_id)
        if job['status'] in {'ready', 'failed'}:
            break
        time.sleep(0.1)
    assert job['status'] == 'ready', job
    with core.repository.connection() as connection:
        row = connection.execute('SELECT output_path, auto_comments FROM design_ppt_jobs WHERE id = ?', (job_id,)).fetchone()
    assert row['auto_comments'] == 'empty'
    commentary = [
        shape.text_frame.text for slide in Presentation(row['output_path']).slides for shape in slide.shapes
        if getattr(shape, 'is_placeholder', False) and shape.placeholder_format.idx == 10 and shape.text_frame.text.strip()
    ]
    assert commentary and any('A median Mean Data Rate improves by' in text for text in commentary)
    # The Design keeps its own comments.
    assert client.get('/api/ppt-designer').json()['rates']['slide_comments'] == {}
    assert any(row['action'] == 'auto_design_comments' for row in core.repository.list_logs())


def test_reporting_jobs_keep_the_auto_comments_of_each_design():
    from src.modules.report_tasks import normalize_definition

    definition = normalize_definition({'name': 'Weekly', 'designs': [
        {'design_id': 'd1', 'auto_comments': 'generated'}, {'design_id': 'd2'}, {'design_id': 'd3', 'auto_comments': 'every'},
    ]})
    assert [entry['auto_comments'] for entry in definition['designs']] == ['generated', 'off', 'off']
