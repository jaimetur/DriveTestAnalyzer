import json
import re
from io import BytesIO

import src.DriveTestAnalyzer as core
from src.modules import dashboard_comments as comments
from src.modules.ppt_dashboards import DashboardDefinition

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
        'Vodafone median NR RSRP improves by 3.8 dB vs 2026-Q2 (−97.6 → −93.8 dBm).',
        'EE leads at the median (−90.1 dBm); Vodafone trails by 3.7 dB (−93.8 dBm); the gap narrows from 7.2 dB in 2026-Q2.',
        'Samples below −110 dBm: Vodafone 5.1% (−4.3 pp vs 2026-Q2); highest: O2 (11.8%).',
        'O2 median NR RSRP degrades by 1.3 dB vs 2026-Q2 (−100.2 → −101.5 dBm).',
    ]
    # Three has too few samples to lead, and the narrow "comments right" box takes three comments.
    assert not any(text.startswith('Three') for text in written)
    assert len(texts([{'index': 0, 'kpi': 'NR_RSRP', 'model': RSRP_CDF}], layout='Title + 1 rows + 1 columns + comments right')) == 3


def test_without_focus_operators_the_comments_follow_the_leader_and_skip_hidden_legend_items():
    written = texts([{'index': 0, 'kpi': 'NR_RSRP', 'model': RSRP_CDF, 'hidden': ['O2']}])
    assert written[0] == 'EE leads at the median (−90.1 dBm), 3.7 dB ahead of Vodafone.'
    assert not any('O2' in text for text in written)


def test_bar_and_stacked_comments_read_their_values_and_class_shares():
    bars = {'type': 'mean_bar', 'metric': 'Mean Data Rate', 'aggregation': 'mean', 'dimensions': OPERATOR_CAMPAIGN, 'bars': [
        {'key': ['VF', '2026-Q2'], 'value': 152.0, 'samples': 900}, {'key': ['VF', '2026-Q3'], 'value': 180.0, 'samples': 950},
        {'key': ['EE', '2026-Q2'], 'value': 199.0, 'samples': 900}, {'key': ['EE', '2026-Q3'], 'value': 212.0, 'samples': 950},
    ]}
    assert texts([{'index': 0, 'kpi': 'Mean Data Rate', 'model': bars}], focus_operators=['VF'])[:2] == [
        'VF Mean Data Rate improves by 16% vs 2026-Q2 (152 → 180).',
        'EE leads at the mean (212); VF trails by 15% (180); the gap narrows from 24% in 2026-Q2.',
    ]
    results = {'type': 'status_100', 'states': [{'name': 'Completed'}, {'name': 'Dropped'}, {'name': 'Failed'}],
               'dimensions': OPERATOR_CAMPAIGN, 'records': [
                   {'key': ['VF', '2026-Q2'], 'shares': [.974, .01, .016], 'samples': 2000},
                   {'key': ['VF', '2026-Q3'], 'shares': [.987, .005, .008], 'samples': 2100},
                   {'key': ['EE', '2026-Q3'], 'shares': [.989, .004, .007], 'samples': 2050}]}
    assert texts([{'index': 0, 'kpi': 'Test_Result', 'model': results}], focus_operators=['VF']) == [
        'VF share of Dropped + Failed falls from 2.6% to 1.3% vs 2026-Q2 (−1.3 pp).',
        'VF is on par with EE in share of Dropped + Failed (1.3% vs 1.1%).',
    ]
    quality = {'type': 'status_100', 'states': [{'name': '< 3'}, {'name': '≥ 3'}], 'dimensions': OPERATOR_CAMPAIGN, 'records': [
        {'key': ['VF', '2026-Q2'], 'shares': [.079, .921], 'samples': 3000},
        {'key': ['VF', '2026-Q3'], 'shares': [.058, .942], 'samples': 3000}]}
    assert texts([{'index': 0, 'kpi': 'LQ', 'model': quality}], focus_operators=['VF']) == [
        'VF share of LQ ≥ 3 rises from 92.1% to 94.2% vs 2026-Q2 (+2.1 pp).',
    ]


def test_unsupported_and_outdated_models():
    assert texts([{'index': 0, 'kpi': 'Latitude', 'model': {'type': 'map', 'series': []}}]) == []
    assert comments.needs_rebuild({'type': 'cdf', 'series': []})
    assert not comments.needs_rebuild({'type': 'cdf', 'series': [], 'dimensions': []})
    assert not comments.needs_rebuild({'type': 'table'})
    assert comments.kpi_semantics('Call_Setup_Time').direction == -1
    assert comments.kpi_semantics('Packet Delay Variation Score').direction == 1


def test_generate_comments_reads_the_open_slide_and_records_app_events(client):
    client.post('/login', data={'username': 'super', 'password': 'super123'})
    rows = ['Operator,Campaign,Mean_Data_Rate,Test_Result,Test_Name,Test_Start_Time']
    for campaign, rates in (('UK_Q2_2026', {'A': 40, 'B': 80}), ('UK_Q3_2026', {'A': 60, 'B': 82})):
        for operator, rate in rates.items():
            for sample in range(12):
                result = 'Failed' if sample == 0 and operator == 'A' else 'Completed'
                rows.append(f'{operator},{campaign},{rate + sample % 3},{result},HTTP DL,2026-09-{sample + 1:02d}')
    uploaded = client.post('/datasets-analysis/upload', data={'dataset_kinds': 'data'}, files={
        'dataset_files': ('rates.csv', BytesIO('\n'.join(rows).encode()), 'text/csv'),
    })
    assert uploaded.status_code == 200, uploaded.text
    core.repository.add_report_template('nsa', 'Comments test', (
        'Slide,Slide tittle,Slide Subtittle,Layout,Chart Tittle,CDR source,KPI,Chart type,Filters,Rows Split,Columns Split,Legend,Legend Position\n'
        '1,Rates,,Title and 2 columns + Comments,Rate CDF,CDR-Data,Mean_Data_Rate,CDF Line,,Operator,Campaign,,Top\n'
        '1,Rates,,Title and 2 columns + Comments,Rate mean,CDR-Data,Mean_Data_Rate,Average Vertical Bars,,Operator,Campaign,,Top\n'
        '2,Results,,Title and 1 column + Comments,Results,CDR-Data,Test_Result,100% Stacked Vertical Bars,,Operator,Campaign,,Top\n'
    ).encode(), is_default=False)
    core.repository.replace_operator_mapping_group(None, 'A', [], '#E60000', 'focus')
    definition = DashboardDefinition(name='Rates', template='Comments test', datasets={'data': [1]}).model_dump(mode='json')
    saved = client.put('/api/ppt-dashboards/rates', json=definition)
    assert saved.status_code == 200, saved.text
    prepared = client.post('/api/ppt-dashboards/prepare', json=definition)
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    slide = body['slides'][0]

    generated = client.post('/api/ppt-dashboards/rates/comments/generate', json={
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
    model = client.get(f"/api/ppt-dashboards/chart/{body['token']}/{slide['charts'][0]['index']}").json()
    assert model['dimensions'] == [['Operator'], ['Campaign']]
    assert model['series'][0]['stats']['n'] == 12

    results = body['slides'][1]
    generated_results = client.post('/api/ppt-dashboards/rates/comments/generate', json={'token': body['token'], 'slide': results['number']})
    assert generated_results.status_code == 200, generated_results.text
    # One failure in 12 tests is not significantly different from none.
    assert [item['text'] for item in generated_results.json()['suggestions']] == [
        'A is on par with B in share of Failed (8.3% vs 0%).', 'A share of Failed is stable vs 2026-Q2 (8.3%).',
    ]

    added = client.patch('/api/ppt-dashboards/rates/comments', json={
        'slide_comments': {slide['comment_key']: written[:2]},
        'generated_slide': slide['comment_key'], 'generated_added': 2,
    })
    assert added.status_code == 200, added.text
    assert added.json()['slide_comments'] == {slide['comment_key']: written[:2]}
    events = {row['action']: json.loads(row['details']) for row in core.repository.list_logs()}
    assert events['generate_dashboard_comments']['suggestions'] == len(written)
    assert events['generate_dashboard_comments']['engine'] == 'rules'
    assert events['add_generated_dashboard_comments'] == {
        'id': 'rates', 'name': 'Rates', 'slide': slide['comment_key'], 'added': 2, 'comments': 2,
    }

    expired = client.post('/api/ppt-dashboards/rates/comments/generate', json={'token': 'missing', 'slide': 1})
    assert expired.status_code == 410
