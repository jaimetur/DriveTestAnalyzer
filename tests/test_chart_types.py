"""The chart types added after Tableau's Show Me (ticket #46): their models, settings, time periods and readers."""
from __future__ import annotations

import json
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.modules.cdr_reporting import (
    CHART_SETTING_FILTERS, CHART_TYPES, CatalogEntry, _design_hits_to_hover_targets, catalog_chart_hover_targets,
    catalog_chart_payload, render_catalog_chart_preview,
)
from src.modules.chart_types import EXTENDED_CHART_TYPES, date_bin_labels, date_bin_parts, date_bin_time
from src.modules.design_comments import slide_comments
from src.modules.report_template_modes import chart_fields


def cdrs(rows: int = 2400, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    operators = rng.choice(['EE', 'O2', 'Vodafone', 'Three'], rows)
    cities = rng.choice(['London', 'Leeds', 'Cardiff', 'Glasgow City'], rows)
    latitude = {'London': 51.5, 'Leeds': 53.8, 'Cardiff': 51.48, 'Glasgow City': 55.86}
    longitude = {'London': -0.12, 'Leeds': -1.55, 'Cardiff': -3.18, 'Glasgow City': -4.25}
    start = pd.Timestamp('2026-03-01') + pd.to_timedelta(rng.integers(0, 40 * 86400, rows), unit='s')
    frame = pd.DataFrame({
        'Operator': operators, 'City': cities,
        'Campaign': rng.choice(['UK_Q1_2026', 'UK_Q2_2026', 'UK_Q3_2026'], rows),
        'Test_Result': rng.choice(['Completed', 'Completed', 'Completed', 'Failed', 'Dropped'], rows),
        'RAT': rng.choice(['NR', 'LTE', 'LTE-CA'], rows),
        'Mean_Data_Rate': rng.gamma(2.0, 60.0, rows),
        'NR_SINR_Avg': rng.normal(10, 6, rows),
        'Test_Start_Latitude': [latitude[city] + rng.normal(0, .05) for city in cities],
        'Test_Start_Longitude': [longitude[city] + rng.normal(0, .05) for city in cities],
        'Test_Start_Time': start.strftime('%Y-%m-%d %H:%M:%S.%f'),
        'Test_End_Time': (start + pd.to_timedelta(rng.integers(30, 600, rows), unit='s')).strftime('%Y-%m-%d %H:%M:%S.%f'),
        'Map_Area': cities, 'Map_Area_Country': 'GBR', 'Test_ID': np.arange(rows),
    })
    frame.attrs['operator_aliases_normalized'] = True
    return frame


def chart(chart_type: str, kpi: str, rows: str = '', columns: str = '', filters: str = '') -> CatalogEntry:
    return CatalogEntry(slide=1, slide_title='Slide', slide_subtitle='', layout='One Chart', chart_title=chart_type,
                        cdr_source='CDR-Data', kpi=kpi, chart_type=chart_type, legend='', filters=filters,
                        rows_split=rows, columns_split=columns)


CASES = [
    ('Horizontal Bars', 'Mean_Data_Rate', 'City', 'Operator', 'Sort = Descending', 'hbar'),
    ('Dot Plot', 'MEDIAN(Mean_Data_Rate)', 'City', 'Operator', '', 'dot'),
    ('Bullet Graph', 'Mean_Data_Rate', 'Operator', 'Campaign', 'Target = Previous campaign; Buckets = 50, 100, 150, 200', 'bullet'),
    ('Highlight Table', 'Mean_Data_Rate', 'City', 'Operator', '', 'table'),
    ('Bar Table', 'COUNT(Test_ID)', 'City', 'Operator', '', 'table'),
    ('Heat Map', 'NR_SINR_Avg', 'City', 'Operator', '', 'heat_map'),
    ('Pie', 'Test_Result', 'Operator', '', '', 'pie'),
    ('Donut', 'COUNT(Test_ID)', '', 'Operator', '', 'pie'),
    ('Lines', 'Mean_Data_Rate', 'Operator', 'Campaign', '', 'lines'),
    ('Dual Lines', 'Mean_Data_Rate | NR_SINR_Avg', '', 'DAY(Test_Start_Time)', '', 'lines'),
    ('Areas', 'RAT', '', 'Campaign', '', 'areas'),
    ('100% Stacked Areas', 'RAT', 'Operator', 'Campaign', '', 'areas'),
    ('Bars and Line', 'COUNT(Test_ID) | Mean_Data_Rate', 'Operator', 'Campaign', '', 'combo'),
    ('Box Plot', 'Mean_Data_Rate', 'Operator', 'Campaign', '', 'box'),
    ('Symbol Map', 'Test_Start_Latitude vs Test_Start_Longitude vs Mean_Data_Rate', 'City', '', 'Buckets = 50, 100, 150, 200', 'symbol_map'),
    ('Filled Map', 'Mean_Data_Rate', '', 'Operator', '', 'filled_map'),
    ('Treemap', 'COUNT(Test_ID) | Mean_Data_Rate', 'Operator', 'City', '', 'treemap'),
    ('Packed Bubbles', 'COUNT(Test_ID)', 'City', 'Operator', '', 'bubbles'),
    ('Sankey', 'COUNT(Test_ID)', 'Operator × RAT', 'Test_Result', '', 'sankey'),
    ('Gantt', 'Test_Start_Time vs Test_End_Time', 'City', 'Operator', 'Date Bin = Day', 'gantt'),
]


def test_every_tableau_chart_type_is_a_supported_chart_type() -> None:
    assert {case[0].casefold() for case in CASES} == set(EXTENDED_CHART_TYPES)
    assert set(EXTENDED_CHART_TYPES) <= CHART_TYPES
    assert {'whiskers', 'target', 'datebin', 'direction', 'sort'} <= CHART_SETTING_FILTERS


@pytest.mark.parametrize(('chart_type', 'kpi', 'rows', 'columns', 'filters', 'kind'), CASES, ids=[case[0] for case in CASES])
def test_each_chart_type_builds_its_model(chart_type, kpi, rows, columns, filters, kind) -> None:
    model = catalog_chart_payload(cdrs(), chart(chart_type, kpi, rows, columns, filters), prefiltered=True)

    assert model['type'] == kind
    assert model['title'] == chart_type
    json.dumps(model, allow_nan=False)


def test_horizontal_bars_aggregate_each_row_and_colour_each_column() -> None:
    frame = cdrs()
    model = catalog_chart_payload(frame, chart('Horizontal Bars', 'MEDIAN(Mean_Data_Rate)', 'City', 'Operator', 'Sort = Descending'), prefiltered=True)

    expected = frame.groupby(['City', 'Operator'])['Mean_Data_Rate'].median()
    row_keys, column_keys = model['row_keys'], model['column_keys']
    for row, cells in zip(row_keys, model['cells']):
        for column, value in zip(column_keys, cells):
            assert value == pytest.approx(expected[(row[0], column[0])])
    # The rows run from the largest bar to the smallest, and each Operator keeps one colour in every row.
    largest = [max(cells) for cells in model['cells']]
    assert largest == sorted(largest, reverse=True)
    assert all(len({row[index] for row in model['cell_colours']}) == 1 for index in range(len(column_keys)))
    assert [item['label'] for item in model['legend']['items']] == [key[0] for key in column_keys]


def test_box_plot_whiskers_reach_p10_and_p90_unless_set() -> None:
    frame = cdrs()
    model = catalog_chart_payload(frame, chart('Box Plot', 'Mean_Data_Rate', 'Operator'), prefiltered=True)
    values = frame.loc[frame['Operator'] == 'EE', 'Mean_Data_Rate'].to_numpy()
    box = next(item for item in model['boxes'] if item['key'] == ['EE'])

    assert model['whiskers'] == 'P10 – P90'
    assert box['low'] == pytest.approx(np.percentile(values, 10))
    assert box['high'] == pytest.approx(np.percentile(values, 90))
    assert box['median'] == pytest.approx(np.median(values))
    # A setting configures the chart: it keeps every sample.
    iqr = catalog_chart_payload(frame, chart('Box Plot', 'Mean_Data_Rate', 'Operator', '', 'Whiskers = 1.5 IQR'), prefiltered=True)
    assert iqr['whiskers'] == '1.5 × IQR'
    assert sum(item['n'] for item in iqr['boxes']) == len(frame)


def test_bullet_graph_compares_the_latest_campaign_with_the_previous_one() -> None:
    frame = cdrs()
    model = catalog_chart_payload(frame, chart('Bullet Graph', 'Mean_Data_Rate', 'Operator', 'Campaign', 'Target = Previous campaign'), prefiltered=True)
    means = frame.groupby(['Operator', 'Campaign'])['Mean_Data_Rate'].mean()

    assert {item['key'][1] for item in model['items']} == {'26-Q3'}
    for item in model['items']:
        assert item['value'] == pytest.approx(means[(item['key'][0], 'UK_Q3_2026')])
        assert item['target'] == pytest.approx(means[(item['key'][0], 'UK_Q2_2026')])
    assert model['target_label'] == 'Previous campaign (26-Q2)'


def test_highlight_and_bar_tables_keep_the_table_and_add_their_cells() -> None:
    frame = cdrs()
    highlight = catalog_chart_payload(frame, chart('Highlight Table', 'Mean_Data_Rate', 'City', 'Operator'), prefiltered=True)
    bars = catalog_chart_payload(frame, chart('Bar Table', 'COUNT(Test_ID)', 'City', 'Operator'), prefiltered=True)

    assert highlight['cell_style'] == 'highlight' and len(highlight['legend']['items']) == 5
    assert len(highlight['cell_colours']) == len(highlight['rows'])
    assert all(colour for row in highlight['cell_colours'] for colour in row)
    assert bars['cell_style'] == 'bar'
    counts = frame.groupby(['City', 'Operator']).size()
    assert bars['column_extents'] == [float(counts.xs(operator, level='Operator').max()) for operator in ['EE', 'O2', 'Three', 'Vodafone']]


def test_a_time_grouped_by_a_period_sorts_in_time_and_draws_a_time_axis() -> None:
    assert date_bin_parts('DAY(Test_Start_Time)') == ('day', 'Test_Start_Time')
    assert date_bin_parts('week ( Test_Start_Time )') == ('week', 'Test_Start_Time')
    assert date_bin_parts('Test_Start_Time') is None
    labels = date_bin_labels(pd.Series(['2026-03-02 10:15:00.5', '2026-12-31 23:59:59', 'bad']), 'week')
    assert labels.tolist()[:2] == ['2026-W10', '2026-W53'] and pd.isna(labels.iloc[2])
    assert date_bin_time('2026-W10', 'week') == pd.Timestamp('2026-03-02').timestamp() * 1000

    model = catalog_chart_payload(cdrs(), chart('Lines', 'Mean_Data_Rate', 'Operator', 'WEEK(Test_Start_Time)'), prefiltered=True)
    weeks = [key[0] for key in model['x_keys']]
    assert weeks == sorted(weeks) and model['x_unit'] == 'week'
    assert model['x_time'] == sorted(model['x_time'])
    # The fields a chart reads name the field of a period.
    assert 'Test_Start_Time' in chart_fields(chart('Lines', 'Mean_Data_Rate', 'Operator', 'DAY(Test_Start_Time)'))


def test_pies_share_the_values_of_a_dimension_by_row() -> None:
    frame = cdrs()
    model = catalog_chart_payload(frame, chart('Donut', 'Test_Result', 'Operator'), prefiltered=True)

    assert model['donut'] is True
    for pie in model['pies']:
        rows = frame[frame['Operator'] == pie['key'][0]]
        assert pie['total'] == len(rows)
        assert sum(slice_['share'] for slice_ in pie['slices']) == pytest.approx(1)
        assert next(item for item in pie['slices'] if item['name'] == 'Failed')['value'] == int((rows['Test_Result'] == 'Failed').sum())


def test_sankey_flows_keep_every_sample_between_levels() -> None:
    frame = cdrs()
    model = catalog_chart_payload(frame, chart('Sankey', 'COUNT(Test_ID)', 'Operator × RAT', 'Test_Result'), prefiltered=True)

    first = [link for link in model['links'] if link['level'] == 0]
    second = [link for link in model['links'] if link['level'] == 1]
    assert sum(link['value'] for link in first) == len(frame) == sum(link['value'] for link in second)
    assert model['levels'] == ['Operator', 'RAT', 'Test_Result']


def test_gantt_joins_the_days_with_samples_of_each_lane() -> None:
    frame = cdrs()
    model = catalog_chart_payload(frame, chart('Gantt', 'Test_Start_Time vs Test_End_Time', 'City'), prefiltered=True)

    assert model['unit'] == 'day'
    for lane in model['lanes']:
        rows = frame[frame['City'] == lane['key'][0]]
        assert sum(segment['n'] for segment in lane['segments']) == len(rows)
        assert all(segment['end'] >= segment['start'] for segment in lane['segments'])


def test_filled_map_colours_the_map_areas_with_their_polygons() -> None:
    model = catalog_chart_payload(cdrs(), chart('Filled Map', 'Mean_Data_Rate', '', 'Operator'), prefiltered=True)

    assert [panel['label'] for panel in model['panels']] == ['EE', 'O2', 'Three', 'Vodafone']
    names = {area['name'] for panel in model['panels'] for area in panel['areas']}
    assert names and names <= set(model['polygons'])
    assert len(model['legend']['items']) == 5


def test_the_new_chart_types_are_drawn_by_the_canvas_renderer_only() -> None:
    entry = chart('Pie', 'Test_Result', 'Operator')
    with patch('src.modules.cdr_reporting._render_canvas_payload_png', return_value=b'canvas-png') as render:
        assert render_catalog_chart_preview(cdrs(), entry, prefiltered=True, renderer='pil') == b'canvas-png'
    assert render.call_args.args[0]['type'] == 'pie'
    assert catalog_chart_hover_targets(cdrs(), entry, prefiltered=True) == []


def test_bubbles_slices_and_areas_become_boxes_of_the_png_viewer() -> None:
    targets = _design_hits_to_hover_targets([
        {'kind': 'circle', 'x': 100, 'y': 50, 'radius': 10, 'label': 'London', 'series': 'Count', 'value': '12'},
        {'kind': 'polygon', 'points': [{'x': 0, 'y': 0}, {'x': 30, 'y': 5}, {'x': 10, 'y': 40}], 'label': 'Leeds', 'value': '3'},
    ])

    assert [(item['x'], item['y'], item['width'], item['height']) for item in targets] == [(90, 40, 20, 20), (0, 0, 30, 40)]
    assert [item['label'] for item in targets] == ['London', 'Leeds']


def test_generated_comments_read_the_new_chart_types() -> None:
    frame = cdrs()
    for chart_type, kpi, rows, columns in [('Horizontal Bars', 'Mean_Data_Rate', 'City', 'Operator'),
                                           ('Box Plot', 'Mean_Data_Rate', 'Operator', 'Campaign'),
                                           ('100% Stacked Areas', 'Test_Result', 'Operator', 'Campaign')]:
        model = catalog_chart_payload(frame, chart(chart_type, kpi, rows, columns), prefiltered=True)
        comments = slide_comments([{'index': 0, 'title': chart_type, 'kpi': kpi, 'model': model}], focus_operators=['EE'])
        assert comments, chart_type


def test_a_numeric_axis_of_lines_keeps_its_numeric_order() -> None:
    frame = cdrs()
    frame['Hour'] = np.arange(len(frame)) % 11 + 8
    model = catalog_chart_payload(frame, chart('Lines', 'MEDIAN(Mean_Data_Rate)', 'Operator', 'Hour'))
    assert [key[0] for key in model['x_keys']] == [str(hour) for hour in range(8, 19)]


def test_filters_read_a_missing_value_as_blank_and_tables_head_their_rows_with_their_fields() -> None:
    frame = cdrs()
    frame.loc[frame.index[:300], 'City'] = None
    model = catalog_chart_payload(frame, chart('Table', 'Mean_Data_Rate', 'City', 'Operator', 'City != (blank)'))
    assert model['headers'][0] == 'City'
    assert sorted(row[0] for row in model['rows']) == ['Cardiff', 'Glasgow City', 'Leeds', 'London']
    blank = catalog_chart_payload(frame, chart('Table', 'Mean_Data_Rate', 'City', 'Operator', 'City = (blank)'))
    assert [row[0] for row in blank['rows']] == ['(blank)']


def test_kpi_cards_keep_their_shape_in_a_frame_of_any_proportions() -> None:
    cards = [{'label': operator, 'value': 100 + index, 'delta': 1, 'improves': True, 'n': 10, 'campaign': 'Q3',
              'trend': [90, 95, 100 + index], 'trend_labels': ['Q1', 'Q3']} for index, operator in enumerate(['EE', 'O2', 'Three', 'VF'])]
    model = {'type': 'kpi', 'title': 'KPI', 'metric': 'Rate', 'cards': cards}
    # A landscape frame keeps one row of four cards; a tall one stacks them, as wide as the frame.
    _png, wide = render_catalog_chart_preview_hits(model, 1600, 900)
    assert len({hit['y'] for hit in wide}) == 1 and len({hit['x'] for hit in wide}) == 4
    _png, tall = render_catalog_chart_preview_hits(model, 1600, 3333)
    assert len({hit['x'] for hit in tall}) == 1 and len({hit['y'] for hit in tall}) == 4
    assert all(hit['width'] > 1400 for hit in tall)


def render_catalog_chart_preview_hits(model: dict, width: int, height: int) -> tuple[bytes, list[dict]]:
    from src.modules.cdr_reporting import _render_canvas_payload
    return _render_canvas_payload(model, width=width, height=height)
