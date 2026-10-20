from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import re

import pytest
from pptx.chart.data import CategoryChartData
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_DATA_LABEL_POSITION, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.util import Inches

from src.modules.scoring_exports import (
    _add_chart_hierarchy_grid, _charts, _cell, _format_chart, _format_stacked_segment_labels, _header_foreground,
    _hierarchy_chart_color, _stacked_chart_pages, export_scoring_powerpoint,
)
from src.modules.scoring_pptx_scorecard import STYLES
from src.modules.scoring_themes import THEMES, blend
from src.modules.scoring_views import THRESHOLD_COLORS, _hierarchy_display_value, build_scoring_views
from tests.scoring_fixtures import scoring_configuration


ROOT = Path(__file__).parents[1]
TEMPLATE = ROOT / 'assets/powerpoint-templates/Template_VodafoneThree.pptx'
METRICS = scoring_configuration()['metrics']
OPERATORS = ('Vodafone UK', 'O2 UK', 'Three UK', 'EE')
MAPPED_OPERATOR_ORDER = ('EE', 'Three UK', 'O2 UK', 'Vodafone UK')
MAPPED_OPERATOR_COLORS = {
    'EE': '#12AB34',
    'Three UK': '#3456AB',
    'O2 UK': '#AB3456',
    'Vodafone UK': '#56AB12',
}
VOICE_CATEGORIES = {'CLASSIC CALLS', 'WHATSAPP CALLS', 'MULTI RAB'}
WARNINGS = ['Speech CDR missing from this comparison.', 'Incomplete campaign coverage.']
CATEGORY_SUBTOTAL_FILL = 'E3E6E7'


def _score_for(operator, index, code):
    if code == 'K5':
        return {'Vodafone UK': 0.50, 'O2 UK': 0.85, 'Three UK': 0.97, 'EE': 1.00}.get(operator, 0.90)
    if operator == 'EE':
        return 0.80
    if operator == 'Three UK':
        return 0.90
    if operator == 'Vodafone UK':
        return 0.40 if index % 2 == 0 else 0.90
    if operator == 'O2 UK':
        return 0.50 if index % 2 == 0 else 0.95
    return 0.90


def _result(operators=OPERATORS, *, missing=(), peer_score=None, warnings=None):
    rows = []
    for index, metric in enumerate(METRICS):
        maximum = metric['contexts']['DriveCity']['max_points']
        for operator in operators:
            if (operator, metric['code']) in missing:
                continue
            score = peer_score(operator, index, metric) if peer_score else _score_for(
                operator, index, metric['code'],
            )
            rows.append({
                'campaign': 'UK_Q2_2026',
                'region': 'North',
                'operator': operator,
                'environment': 'DriveCity',
                'dataset_type': metric['source_kind'].title(),
                'kpi_code': metric['code'],
                'category': metric['category'],
                'kpi': metric['kpi'],
                'kpi_type': metric['kpi_type'],
                'value': score * 100,
                'score': score,
                'weighted_points': maximum * score,
                'max_points': maximum,
                'sample_count': 100,
                'complete': True,
            })
    totals = []
    for operator in operators:
        points = sum(row['weighted_points'] for row in rows if row['operator'] == operator)
        totals.append({
            'campaign': 'UK_Q2_2026', 'region': 'North', 'operator': operator,
            'environment': 'DriveCity', 'category': 'Overall',
            'weighted_points': points, 'max_points': 650,
        })
    return {
        'scoring': rows,
        'totals': totals,
        'warnings': list(WARNINGS if warnings is None else warnings),
        'configuration': scoring_configuration(),
    }


def _mapping_groups(order=MAPPED_OPERATOR_ORDER, colors=MAPPED_OPERATOR_COLORS):
    return [
        {'canonical': operator, 'aliases': [], 'position': position, 'color': colors[operator]}
        for position, operator in enumerate(order)
    ]


def _export(result, *, levels=('Operator',), baseline='EE', operator_mapping_groups=None,
            job_fields=None, environment='DriveCity', split_charts=True):
    job = {
        'aggregation_levels': list(levels),
        'nr_mode': 'NSA',
        'baseline_operator': baseline,
        'campaigns': ['UK_Q2_2026'],
        'configuration': scoring_configuration(),
    }
    job.update(job_fields or {})
    # Drawn in NetCheck, the theme whose colours these tests assert (Ericsson is the default of the users).
    output = export_scoring_powerpoint(
        job, result, TEMPLATE, operator_mapping_groups=operator_mapping_groups,
        environment=environment, split_charts=split_charts, theme='netcheck',
    )
    return Presentation(BytesIO(output))


def _table_shapes(presentation):
    return [shape.table for slide in presentation.slides for shape in slide.shapes if shape.has_table]


def _comparison_matrices(presentation):
    return [
        table for table in _table_shapes(presentation)
        # The Scoring tables start with their KPI (or Category, in a Summary) column and end with the weighted score.
        if len(table.rows) >= 3 and table.cell(0, 0).text.strip() in {'KPI', 'Category'}
        and table.cell(len(table.rows) - 1, 0).text.startswith('Weighted score')
    ]


def _normalized_headers(table):
    return [re.sub(r'\s+', ' ', table.cell(0, column).text).strip() for column in range(len(table.columns))]


def _operator_columns(table):
    headers = _normalized_headers(table)
    gap_start = next((index for index, label in enumerate(headers) if label.startswith('GAP ')), len(headers))
    # The scorecard has a single KPI (or Category) column before the operators.
    return {headers[index]: index for index in range(1, gap_start)}


def _rgb(cell):
    """The colour of a cell: its solid fill, or the first colour of the bar that fills it."""
    properties = cell._tc.tcPr
    gradient = properties.find(qn('a:gradFill')) if properties is not None else None
    if gradient is not None:
        return gradient.find(qn('a:gsLst'))[0][0].get('val')
    return str(cell.fill.fore_color.rgb)


def _label_name(text):
    """The KPI or category of a scorecard label, without its category tag, type badge, weight and maximum."""
    head, _separator, rest = text.partition(' · ')
    if rest and head.isupper() and '   ' not in head:
        text = rest
    if text[:3] in {'R  ', 'D  '}:
        text = text[3:]
    return text.split('   ')[0]


SECTION_FILL = STYLES['netcheck']['section'].lstrip('#')
TOTAL_FILL = STYLES['netcheck']['total'].lstrip('#')


def _slide_text(slide):
    pieces = []
    for shape in _nested_shapes(slide.shapes):
        if shape.has_text_frame:
            pieces.append(shape.text)
        elif shape.has_table:
            pieces.extend(cell.text for row in shape.table.rows for cell in row.cells)
    return '\n'.join(pieces)


def _nested_shapes(shapes):
    for shape in shapes:
        yield shape
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _nested_shapes(shape.shapes)


def _charts_on_slide(slide):
    return [shape.chart for shape in _nested_shapes(slide.shapes) if shape.has_chart]


def _series_color(series):
    return str(series.format.fill.fore_color.rgb).upper()


def _voice_tint(color: str) -> str:
    channels = [int(color.lstrip('#')[index:index + 2], 16) for index in (0, 2, 4)]
    return '{:02X}{:02X}{:02X}'.format(
        *(round(channel + (255 - channel) * .45) for channel in channels)
    )


def _assert_sparse_series_values(series, expected_values):
    actual_values = list(series.values)
    assert len(actual_values) == len(expected_values)
    for actual, expected in zip(actual_values, expected_values):
        if expected is None:
            assert actual is None
        else:
            assert actual == pytest.approx(expected)


def _assert_gray_category_row(table, row_index):
    """A category section: the whole row in the colour of the theme's sections."""
    assert all(_rgb(table.cell(row_index, column)).upper() == SECTION_FILL for column in range(len(table.columns)))


def _section_rows(table, start=1):
    """The rows that open a category: their label in bold (a KPI label starts with its type badge)."""
    def opens_section(cell):
        runs = cell.text_frame.paragraphs[0].runs
        return bool(runs) and bool(runs[0].font.bold) and runs[0].text.strip() not in {'R', 'D'}
    return [index for index in range(start, len(table.rows) - 1) if opens_section(table.cell(index, 0))]


def _assert_row_matches_category_fill(table, row_index, expected_fill):
    category_fill = _rgb(table.cell(row_index, 0)).upper()
    assert category_fill == expected_fill
    assert all(_rgb(table.cell(row_index, column)).upper() == category_fill
               for column in range(len(table.columns)))


def test_table_cell_border_markup_is_unique_and_schema_ordered_when_reused():
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    table = slide.shapes.add_table(1, 1, Inches(1), Inches(1), Inches(2), Inches(1)).table
    cell = table.cell(0, 0)
    _cell(cell, 'first')
    _cell(cell, 'second', color='#E6F0F7')
    properties = cell._tc.get_or_add_tcPr()
    tags = [child.tag.rsplit('}', 1)[-1] for child in properties]
    for edge in ('lnL', 'lnR', 'lnT', 'lnB'):
        assert tags.count(edge) == 1
    fill_index = next(index for index, tag in enumerate(tags) if tag.endswith('Fill'))
    assert [tags.index(edge) for edge in ('lnL', 'lnR', 'lnT', 'lnB')] == [0, 1, 2, 3]
    assert fill_index > tags.index('lnB')


def test_incomplete_ppt_table_values_are_na_star_red_and_bold():
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    table = slide.shapes.add_table(1, 2, Inches(1), Inches(1), Inches(3), Inches(1)).table

    _cell(table.cell(0, 0), 'N/A')
    _cell(table.cell(0, 1), '-1.25*')

    for cell, expected in zip(table.rows[0].cells, ('N/A*', '-1.25*')):
        assert cell.text == expected
        paragraph = cell.text_frame.paragraphs[0]
        assert paragraph.font.bold
        assert str(paragraph.font.color.rgb) == 'C62828'


def _assert_category_shade_bar(chart_group, chart_shape, categories):
    keys = [shape for shape in chart_group.shapes
            if shape.name == 'Scoring Chart Category Shade Key' and shape.has_table]
    assert len(keys) == 1
    key = keys[0]
    cells = list(key.table.rows[0].cells)
    assert [cell.text for cell in cells] == categories
    assert [str(cell.fill.fore_color.rgb).upper() for cell in cells] == [
        _hierarchy_chart_color('#606060', index, len(categories)).lstrip('#').upper()
        for index in range(len(categories))
    ]
    assert key.left == chart_shape.left
    assert key.width == chart_shape.width
    assert key.top >= chart_shape.top + chart_shape.height
    assert chart_group.top + chart_group.height >= key.top + key.height


def _assert_chart_hierarchy_grid(slide, group, chart_shape,
                                 levels={'Operator', 'Region', 'Campaign'}):
    grid = next(shape for shape in group.shapes if shape.name == 'Scoring Chart Aggregation Grid')
    assert grid.left == chart_shape.left + Inches(.55)
    assert grid.width == chart_shape.width - Inches(.75)
    assert grid.top == chart_shape.top + chart_shape.height
    assert len(grid.table.rows) == len(levels)
    assert chart_shape.chart.category_axis.tick_label_position == XL_TICK_LABEL_POSITION.NONE
    assert chart_shape.chart.value_axis.tick_label_position == XL_TICK_LABEL_POSITION.NONE
    plot_layouts = chart_shape.chart._chartSpace.xpath('.//c:plotArea/c:layout/c:manualLayout')
    assert len(plot_layouts) == 1
    layout_modes = {name: plot_layouts[0].xpath(f'./c:{name}/@val')[0]
                    for name in ('xMode', 'yMode', 'wMode', 'hMode')}
    assert layout_modes == {'xMode': 'edge', 'yMode': 'edge', 'wMode': 'factor', 'hMode': 'factor'}
    axis_labels = [shape for shape in group.shapes if shape.name == 'Scoring Chart Value Axis Tick']
    tick_values = [float(label.text) for label in axis_labels]
    assert tick_values and tick_values[0] == 0
    assert tick_values == sorted(set(tick_values))
    for label in axis_labels:
        assert label.left >= chart_shape.left
        assert label.left + label.width <= chart_shape.left + Inches(.55)
        assert chart_shape.top <= label.top
        assert label.top + label.height <= chart_shape.top + chart_shape.height + Inches(.11)
    level_labels = [shape.text for shape in slide.shapes
                    if shape.name.startswith('Scoring Chart Aggregation Level ')]
    assert {label.removeprefix('Scoring Chart Aggregation Level ').removesuffix(' (0)')
            for label in level_labels} == levels


def test_stacked_chart_pagination_preserves_root_groups_and_leaf_values():
    columns = [
        {'id': f'{operator}-{index}', 'operator': operator,
         'path': [{'level': 'Operator', 'value': operator}, {'level': 'Campaign', 'value': str(index)}]}
        for operator, count in (('O2 UK', 4), ('Three UK', 4), ('EE', 4),
                                ('Vodafone UK', 4), ('Other', 4))
        for index in range(count)
    ]
    values = {column['id']: {'points': index * 10.0} for index, column in enumerate(columns, 1)}
    matrix = {
        'operators': ['O2 UK', 'Three UK', 'EE', 'Vodafone UK', 'Other'], 'hierarchy_columns': columns,
        'total': {'values': values, 'max_points': 999.0},
    }

    pages = _stacked_chart_pages(matrix, limit=12)

    assert len(pages) == 2
    assert all(len(page['hierarchy_columns']) <= 12 for page in pages)
    assert {column['id'] for page in pages for column in page['hierarchy_columns']} == {
        column['id'] for column in columns
    }
    assert sum(len(page['hierarchy_columns']) for page in pages) == len(columns)
    original_positions = {column['id']: index for index, column in enumerate(columns)}
    assert all([original_positions[column['id']] for column in page['hierarchy_columns']] ==
               sorted(original_positions[column['id']] for column in page['hierarchy_columns'])
               for page in pages)
    assert set(pages[0]['operators']) == {'Three UK', 'EE', 'Vodafone UK'}
    assert set(pages[1]['operators']) == {'O2 UK', 'Other'}
    assert [page['_stacked_chart_page'] for page in pages] == ['Page 1 of 2', 'Page 2 of 2']
    assert {page['_stacked_chart_maximum'] for page in pages} == {200.0}


def test_stacked_chart_pagination_keeps_each_city_together_when_city_comes_before_operator():
    def columns_of(cities, operators, campaigns):
        return [
            {'id': f'{city}-{operator}-{campaign}', 'operator': operator,
             'path': [{'level': 'City', 'value': city}, {'level': 'Operator', 'value': operator},
                      {'level': 'Campaign', 'value': campaign}]}
            for city in cities for operator in operators for campaign in campaigns
        ]

    def matrix_of(columns):
        values = {column['id']: {'points': float(index)} for index, column in enumerate(columns, 1)}
        return {'operators': list(dict.fromkeys(column['operator'] for column in columns)), 'hierarchy_columns': columns,
                'total': {'values': values, 'max_points': 999.0}}

    operators = ['O2 UK', 'Three UK', 'EE', 'Vodafone UK']
    columns = columns_of(['London', 'Manchester', 'Leeds'], operators, ['2026Q1', '2026Q2'])
    pages = _stacked_chart_pages(matrix_of(columns))

    # Whole cities on each slide, in the order of the hierarchy: never one operator across every city.
    assert [[column['id'] for column in page['hierarchy_columns']] for page in pages] == [
        [column['id'] for column in columns[:16]], [column['id'] for column in columns[16:]],
    ]
    assert all(set(page['operators']) == set(operators) for page in pages)
    assert [page['_stacked_chart_page'] for page in pages] == ['Page 1 of 2', 'Page 2 of 2']

    # A city with more columns than a slide holds is divided by its operators.
    columns = columns_of(['London'], operators, ['2026Q1', '2026Q2', '2026Q3', '2026Q4', '2027Q1', '2027Q2'])
    pages = _stacked_chart_pages(matrix_of(columns))
    assert [page['operators'] for page in pages] == [operators[:3], operators[3:]]
    assert [column['id'] for page in pages for column in page['hierarchy_columns']] == [column['id'] for column in columns]


def test_dense_hierarchy_powerpoint_can_keep_all_chart_leaves_on_one_slide():
    campaigns = [f'UK_Q{index}_2026' for index in range(1, 7)]
    base = _result()
    scoring_rows = [
        {**row, 'campaign': campaign}
        for campaign in campaigns
        for row in base['scoring']
    ]
    result = {**base, 'scoring': scoring_rows}
    job_fields = {
        'aggregation_contract_version': 2,
        'aggregation_levels': ['Operator', 'Campaign'],
        'campaigns': campaigns,
    }

    presentation = _export(
        result, levels=('Operator', 'Campaign'), job_fields=job_fields, split_charts=False,
    )

    titles = [slide.shapes.title.text.split('\n')[0] for slide in presentation.slides]
    service_slides = [slide for slide, title in zip(presentation.slides, titles)
                      if title == 'Best Network Scoring per Service']
    category_slides = [slide for slide, title in zip(presentation.slides, titles)
                       if title == 'Best Network Scoring per Category']
    assert len(service_slides) == 1
    assert len(category_slides) == 1
    assert all('Page ' not in slide.shapes.title.text for slide in service_slides + category_slides)
    service_chart = _charts_on_slide(service_slides[0])[0]
    assert len(service_chart.plots[0].categories.flattened_labels) == 24
    category_chart = _charts_on_slide(category_slides[0])[0]
    assert len(category_chart.plots[0].categories.flattened_labels) == 24
    assert len({path[-1] for path in category_chart.plots[0].categories.flattened_labels}) == len(campaigns)
    comparison_slides = [slide for slide in presentation.slides
                         if slide.shapes.title.text.split('\n')[0] == 'Best Network Scoring per Category (Breakdown)']
    assert len(comparison_slides) == 1
    comparison_chart = _charts_on_slide(comparison_slides[0])[0]
    comparison_paths = comparison_chart.plots[0].categories.flattened_labels
    expected_categories = {row['category'] for row in scoring_rows}
    assert len(comparison_paths) == 24 * len(expected_categories)
    assert {path[0] for path in comparison_paths} == expected_categories
    assert len(comparison_chart.series) == len(OPERATORS)
    assert {series.name for series in comparison_chart.series} == set(OPERATORS)
    for series in comparison_chart.series:
        expected_values = []
        for category, operator, campaign in comparison_paths:
            if operator != series.name:
                expected_values.append(None)
                continue
            matching = [row['weighted_points'] for row in scoring_rows
                        if row['category'] == category and row['operator'] == operator
                        and _hierarchy_display_value({'level': 'Campaign', 'value': row['campaign']}) == campaign]
            expected_values.append(sum(matching) if matching else None)
        _assert_sparse_series_values(series, expected_values)


@pytest.mark.parametrize(('category_count', 'split_charts', 'expected_slides'), [
    (12, True, 1), (13, True, 2), (13, False, 1),
])
def test_simple_category_charts_split_by_category_groups_above_fifty_bars(
    category_count, split_charts, expected_slides,
):
    result = _result()
    configuration = scoring_configuration()
    categories = [f'Category {index}' for index in range(category_count)]
    for index, metric in enumerate(configuration['metrics']):
        metric['category'] = categories[index % category_count]
    category_by_code = {metric['code']: metric['category'] for metric in configuration['metrics']}
    for row in result['scoring']:
        row['category'] = category_by_code[row['kpi_code']]
    result['configuration'] = configuration

    presentation = _export(
        result, job_fields={'configuration': configuration}, split_charts=split_charts,
    )

    category_slides = [slide for slide in presentation.slides
                       if slide.shapes.title.text.split('\n')[0] == 'Best Network Scoring per Category (Breakdown)']
    assert len(category_slides) == expected_slides
    charts = [_charts_on_slide(slide)[0] for slide in category_slides]
    observed_categories = [category.label for chart in charts for category in chart.plots[0].categories]
    assert observed_categories == categories
    if category_count == 12:
        assert len(charts[0].plots[0].categories) * len(OPERATORS) == 48
    elif split_charts:
        # 52 bars do not fit one slide: two balanced pages.
        assert [len(chart.plots[0].categories) * len(OPERATORS) for chart in charts] == [28, 24]
        assert ['Page 1 of 2' in _slide_text(slide) for slide in category_slides] == [True, False]
        assert 'Page 2 of 2' in _slide_text(category_slides[1])
    else:
        assert len(charts[0].plots[0].categories) * len(OPERATORS) == 52


@pytest.mark.parametrize(('bar_count', 'has_data_labels', 'number_format'), [
    (40, True, '0.0'), (41, True, '0'), (70, True, '0'), (71, False, '0'),
])
def test_simple_category_chart_label_thresholds_and_dense_number_format(
    bar_count, has_data_labels, number_format,
):
    operators = ['EE']
    matrix = {
        'operators': operators,
        'operator_styles': {'EE': {'color': '#345678', 'label': 'EE'}},
        'context': {'environment': 'DriveCity'},
        'coverage_note': '',
        '_split_charts': False,
        'rows': [
            {'category': f'Category {index}', 'values': {'EE': {'points': float(index + 1)}}}
            for index in range(bar_count)
        ],
    }
    presentation = Presentation(TEMPLATE)

    _charts(presentation, [matrix])

    chart = _charts_on_slide(presentation.slides[-1])[0]
    assert len(chart.plots[0].categories) == bar_count
    assert chart.plots[0].has_data_labels is has_data_labels
    if has_data_labels:
        assert chart.plots[0].data_labels.number_format == number_format
    else:
        assert chart.plots[0]._element.dLbls is None


@pytest.mark.parametrize(('campaign_count', 'operator_count', 'has_data_labels'), [
    (35, 2, True), (36, 2, False),
])
def test_hierarchy_category_comparison_hides_labels_only_above_sixty_bars(
    campaign_count, operator_count, has_data_labels,
):
    campaigns = [f'UK_Q{index}_2026' for index in range(1, campaign_count + 1)]
    operators = ('EE', 'Three UK')[:operator_count]
    base = _result(operators=operators)
    final_campaign = campaigns[-1]
    result = {
        **base,
        'scoring': [{**row, 'campaign': campaign}
                    for campaign in campaigns for row in base['scoring']
                    if not (campaign_count == 36 and campaign == final_campaign
                            and row['operator'] == 'Three UK')],
    }
    job_fields = {
        'aggregation_contract_version': 2,
        'aggregation_levels': ['Operator', 'Campaign'],
        'campaigns': campaigns,
    }

    presentation = _export(
        result, levels=('Operator', 'Campaign'), job_fields=job_fields,
    )

    category_slides = [slide for slide in presentation.slides
                       if slide.shapes.title.text.split('\n')[0] == 'Best Network Scoring per Category (Breakdown)']
    assert len(category_slides) == len({row['category'] for row in result['scoring']})
    for slide in category_slides:
        chart = _charts_on_slide(slide)[0]
        leaf_count = campaign_count * operator_count - (1 if campaign_count == 36 else 0)
        assert len(chart.plots[0].categories.flattened_labels) == leaf_count
        assert chart.plots[0].has_data_labels is has_data_labels
        if has_data_labels:
            assert chart.plots[0].data_labels.number_format == '0'
        else:
            assert chart.plots[0]._element.dLbls is None


def test_stacked_segment_labels_contrast_and_hide_segments_below_four_percent():
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    data = CategoryChartData()
    data.categories = ['Campaign']
    data.add_series('Dark', [3])
    data.add_series('Light', [97])
    data.add_series('Total', [100])
    chart = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_STACKED, Inches(1), Inches(1), Inches(4), Inches(3), data,
    ).chart
    chart.series[0].format.fill.solid()
    chart.series[0].format.fill.fore_color.rgb = RGBColor.from_string('000000')
    chart.series[1].format.fill.solid()
    chart.series[1].format.fill.fore_color.rgb = RGBColor.from_string('FFFFFF')
    _format_chart(chart, maximum=100, labels=XL_DATA_LABEL_POSITION.CENTER)

    _format_stacked_segment_labels(chart)

    assert chart.plots[0].gap_width == 45
    series = chart._chartSpace.xpath('.//c:barChart/c:ser')
    assert series[0].xpath('./c:dLbls/c:dLbl/c:delete/@val') == ['1']
    assert series[1].xpath('./c:dLbls/c:dLbl/c:delete/@val') == []
    for element, fill in zip(series[:2], ('000000', 'FFFFFF')):
        actual = element.xpath('./c:dLbls/c:txPr//a:defRPr/a:solidFill/a:srgbClr/@val')
        assert actual and set(actual) == {_header_foreground(fill).lstrip('#')}


def test_narrow_chart_hierarchy_grid_wraps_campaign_quarter_without_losing_hyphen():
    columns = [
        {'id': f'leaf-{index}', 'operator': 'EE', 'path': [
            {'level': 'Operator', 'value': 'EE'},
            {'level': 'Region', 'value': (
                'A' if index < 6 else
                'North Region with an exceptionally extended descriptive regional grouping label '
                'that wraps to multiple lines' if index < 9 else 'B'
            )},
            {'level': 'Campaign', 'value': f'2026-Q{index % 4 + 1}'},
        ]}
        for index in range(12)
    ]
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    data = CategoryChartData()
    data.categories = [column['id'] for column in columns]
    data.add_series('EE', list(range(len(columns))))
    chart_shape = slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_STACKED, Inches(.65), Inches(1.75), Inches(3.2), Inches(4.25), data,
    )
    _format_chart(chart_shape.chart, maximum=12, labels=XL_DATA_LABEL_POSITION.CENTER)

    grid = _add_chart_hierarchy_grid(slide, chart_shape, columns)

    assert grid is not None
    assert grid.top == chart_shape.top + chart_shape.height
    campaign_labels = [cell.text for cell in grid.table.rows[0].cells]
    assert [label.replace('\n', '') for label in campaign_labels] == [
        f'2026-Q{index % 4 + 1}' for index in range(12)
    ]
    assert all('\n' in label and label.splitlines()[0].endswith('-') for label in campaign_labels)
    assert grid.table.rows[1].height > Inches(.3)
    region_caption = next(shape for shape in slide.shapes
                          if shape.name == 'Scoring Chart Aggregation Level Region')
    assert region_caption.top == grid.top + grid.table.rows[0].height
    assert region_caption.height == grid.table.rows[1].height
    assert region_caption.text_frame.vertical_anchor == MSO_ANCHOR.MIDDLE
    for row in grid.table.rows:
        visible_cell_sizes = {
            cell.text_frame.paragraphs[0].font.size.pt
            for cell in row.cells if cell.text.strip()
        }
        assert len(visible_cell_sizes) == 1


def _legend_visible_series_names(chart):
    deleted = {
        int(entry.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}idx').get('val'))
        for entry in chart._chartSpace.xpath('.//c:legend/c:legendEntry')
        if entry.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}delete').get('val') == '1'
    }
    return [series.name for index, series in enumerate(chart.series) if index not in deleted]


def _slide_with_table(presentation, headers):
    expected = [label.casefold() for label in headers]
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_table and [cell.text.strip().casefold() for cell in shape.table.rows[0].cells] == expected:
                return slide, shape.table
    raise AssertionError(f'No slide has the expected table header: {headers!r}')


def test_powerpoint_exports_one_reference_style_scoring_matrix_with_signed_gaps_and_notes():
    result = _result(missing={('O2 UK', 'K1')})
    groups = _mapping_groups()
    views = build_scoring_views(
        {'levels': ['Operator'], 'baseline_operator': 'EE'},
        result,
        operator_mapping_groups=groups,
    )
    assert len(views['score_tables'][0]['rows']) == 32  # Totals without KPI codes are not a 33rd metric.
    presentation = _export(result, operator_mapping_groups=groups)
    source = Presentation(TEMPLATE)
    matrices = _comparison_matrices(presentation)

    assert presentation.slide_width == source.slide_width
    assert presentation.slide_height == source.slide_height
    assert len(matrices) == 2
    # The scorecard: a Category (Summary) or KPI (Breakdown) column, then the operators; no Weight or Max columns.
    assert _normalized_headers(matrices[0])[:2] == ['Category', 'EE']
    assert _rgb(matrices[0].cell(0, 0)) == STYLES['netcheck']['header'].lstrip('#')
    table = matrices[-1]
    headers = _normalized_headers(table)
    assert headers[0] == 'KPI'
    assert not {'CATEGORY', 'Type of KPI', 'Score weight (%)', 'Max score'} & set(headers)
    operator_columns = _operator_columns(table)
    assert list(operator_columns) == list(MAPPED_OPERATOR_ORDER)
    gap_columns = [index for index, header in enumerate(headers) if header.startswith('GAP ')]
    assert len(gap_columns) == 3
    display_rows = views['score_tables'][0]['expanded_rows']
    assert len(table.rows) == len(display_rows) + 2
    assert len(table.columns) == 8
    # Each category opens a section with its subtotal, then its KPIs, each with its type, weight and maximum.
    expected_labels = []
    for category in dict.fromkeys(row['category'] for row in display_rows):
        expected_labels.append(category)
        expected_labels.extend(row['kpi'] for row in display_rows
                               if row['category'] == category and row.get('row_type') != 'category')
    labels = [table.cell(row, 0).text for row in range(1, len(table.rows) - 1)]
    assert [_label_name(label) for label in labels] == expected_labels
    assert all(label.endswith(' pts') for label in labels)
    assert all(table.cell(row, 0).text not in OPERATORS for row in range(1, 33))
    sections = _section_rows(table)
    assert [_label_name(table.cell(row, 0).text) for row in sections] == list(dict.fromkeys(row['category'] for row in display_rows))
    for row_index in sections:
        _assert_gray_category_row(table, row_index)

    total_row = len(table.rows) - 1
    # The weighted total names the weight and maximum of the environment (65% of the 1,000 points).
    assert table.cell(total_row, 0).text.startswith('Weighted score')
    assert table.cell(total_row, 0).text.endswith('65.00% · 650.00 pts')
    for scoring_matrix in matrices:
        assert _rgb(scoring_matrix.cell(len(scoring_matrix.rows) - 1, 0)) == TOTAL_FILL

    # The operators are on strips in the colours of the workspace mappings (as in the NetCheck reports); the GAP
    # headers stay light.
    assert {operator: _rgb(table.cell(0, column)) for operator, column in operator_columns.items()} == {
        operator: color.lstrip('#').upper() for operator, color in MAPPED_OPERATOR_COLORS.items()}
    assert all(_rgb(table.cell(0, column)) == STYLES['netcheck']['header'].lstrip('#') for column in gap_columns)

    signed_gaps = [
        float(table.cell(row, column).text)
        for row in range(1, 33) for column in gap_columns
        if not table.cell(row, column).text.startswith('N/A')
    ]
    assert any(value > 0 for value in signed_gaps)
    assert any(value < 0 for value in signed_gaps)

    row_of, section = {}, None
    for row in range(1, len(table.rows) - 1):
        name = _label_name(table.cell(row, 0).text)
        if row in sections:
            section = name
        else:
            row_of[(section, name)] = row
    k1, k5 = (next(metric for metric in display_rows if metric.get('kpi_code') == code) for code in ('K1', 'K5'))
    c5_index = row_of[(k1['category'], k1['kpi'])]
    missing_cell = table.cell(c5_index, operator_columns['O2 UK'])
    assert missing_cell.text == 'N/A*'
    missing_paragraph = missing_cell.text_frame.paragraphs[0]
    assert str(missing_paragraph.font.color.rgb) == 'C62828'
    assert missing_paragraph.font.bold

    c9_index = row_of[(k5['category'], k5['kpi'])]
    expected_bands = {'Vodafone UK': 'Low', 'O2 UK': 'Medium', 'Three UK': 'High', 'EE': 'UltraHigh'}
    # Each score fills its cell in the colour of its band (NetCheck: soft cards with a bar).
    for operator, band in expected_bands.items():
        expected = blend(STYLES['netcheck']['card'], THEMES['netcheck']['band_strong'][band], STYLES['netcheck']['bar_mix'])
        assert _rgb(table.cell(c9_index, operator_columns[operator])) == expected.lstrip('#')

    gap_slide, gap_table = next(
        (slide, shape.table) for slide in presentation.slides for shape in slide.shapes
        if shape.has_table and len(shape.table.columns) == 2
        and _normalized_headers(shape.table)[0] == 'NetCheck KPIs'
    )
    expected_gap_table = views['gap_tables'][0]
    assert gap_slide.shapes.title.text.split('\n')[0] == 'GAP Analysis — Three UK vs EE'
    title_runs = gap_slide.shapes.title.text_frame.paragraphs[0].runs
    # What tells consecutive slides apart is in bold, in the colour of the rest of the title.
    assert [(run.text, run.font.bold) for run in title_runs] == [('GAP Analysis — ', False), ('Three UK vs EE', True)]
    assert {str(run.font.color.rgb) for run in title_runs} == {'1450A8'}
    assert 'Environment:' not in gap_slide.shapes.title.text
    expected_gap_rows = [row for row in expected_gap_table['expanded_rows']
                         if row.get('row_type') != 'category'
                         and row['kpi'].casefold() != 'average kpi gap']
    assert all(not row['kpi'].casefold().endswith(' total') for row in expected_gap_rows)
    # Header, one row per KPI and the closing Total KPI GAP row.
    assert len(gap_table.rows) == len(expected_gap_rows) + 2
    assert gap_table.cell(len(gap_table.rows) - 1, 0).text == 'Total KPI GAP'
    # Ordered by GAP, each KPI carries its category and type.
    gap_labels = [gap_table.cell(row, 0).text for row in range(1, len(gap_table.rows) - 1)]
    assert [_label_name(label) for label in gap_labels] == [row['kpi'] for row in expected_gap_rows]
    assert [label.split(' · ')[0] for label in gap_labels] == [row['category'].upper() for row in expected_gap_rows]
    assert [float(gap_table.cell(row, 1).text) for row in range(1, len(gap_table.rows) - 1)] == pytest.approx(
        [row['gap_points'] for row in expected_gap_rows], abs=.0051,
    )
    assert _rgb(gap_table.cell(0, 1)) == MAPPED_OPERATOR_COLORS[expected_gap_table['operator']].lstrip('#')
    assert _rgb(gap_table.cell(0, 0)) == STYLES['netcheck']['header'].lstrip('#')
    reliable = next(label for label, row in zip(gap_labels, expected_gap_rows) if row['kpi_type'] == 'Reliable')
    assert ' · R  ' in reliable

    titles = [slide.shapes.title.text.split('\n')[0] for slide in presentation.slides]
    assert titles[:2] == ['Scoring & GAP Analysis', 'Drive - City']
    # The Summary opens the block with How the measurements ran, before the scoring charts.
    start = titles.index('Best Network Scoring per Service')
    assert titles[2] == 'How the measurements ran' and 'Best Network — Standings' in titles[3:start]
    assert titles[start:start + 2] == [
        'Best Network Scoring per Service', 'Best Network Scoring per Category',
    ]
    category_chart_slides = [slide for slide in presentation.slides
                              if slide.shapes.title.text.split('\n')[0] == 'Best Network Scoring per Category (Breakdown)']
    # 7 categories × 4 operators = 28 bars stay on one slide.
    assert len(category_chart_slides) == 1
    assert len(_charts_on_slide(category_chart_slides[0])[0].plots[0].categories) == 7
    assert 'Page 1 of' not in _slide_text(category_chart_slides[0])
    assert titles[start + 3:start + 5] == ['Scoring Tables — Summary', 'Scoring Tables — Breakdown']
    gap_start = titles.index('GAP Analysis — All vs EE')
    # The subtitle names the area of the table (the Region of its context), its operators and its vendors.
    assert presentation.slides[gap_start].shapes.title.text.split('\n')[1] == \
        'Best Network — Drive - City · Region: North · All Operators · All Vendors'
    # The GAP tables are followed by the GAP by part and the KPI GAP Profiles, and Points Lost ends the block.
    assert all(title.startswith(('GAP Analysis', 'GAP by part', 'KPI GAP Profile', 'Points Lost', 'Points lost per KPI'))
               for title in titles[gap_start:])
    assert titles.index('GAP by part — vs EE') < next(index for index, title in enumerate(titles) if title.startswith('KPI GAP Profile')) \
        < titles.index('Points Lost — where the points go')
    for slide in presentation.slides:
        if slide.shapes.title.text.startswith('GAP Analysis') and any(shape.has_table for shape in slide.shapes):
            assert sum(shape.name.startswith('GAP Color Scale Segment ') for shape in slide.shapes) == 24
            assert 'GAP color scale' in _slide_text(slide)
            expected_arrows = 0 if slide.shapes.title.text.startswith('GAP Analysis — All vs ') else 1
            assert sum(shape.name == 'GAP KPI Priority Arrow' for shape in slide.shapes) == expected_arrows
            assert sum(shape.name == 'GAP KPI Priority Label' for shape in slide.shapes) == expected_arrows
    assert sum(title.startswith('GAP Analysis') for title in titles[gap_start:]) == 4
    intro_slides = [presentation.slides[index] for index in range(2)]
    assert [slide.slide_layout.name for slide in intro_slides] == ['Title Page', 'Title Page']
    cover_text = _slide_text(presentation.slides[0]).replace('\x0b', '\n')
    transition_text = _slide_text(presentation.slides[1]).replace('\x0b', '\n')
    expected_filter_text = 'Campaigns: 2026-Q2\nSplit by: Operator\nOperator: All Operators\nVendor: All Vendors\nRegion: All Regions\nCity: All Cities'
    for text in (cover_text, transition_text):
        assert 'Non-Standalone' in text and expected_filter_text in text

    summary_view = views['gap_summary_tables'][0]
    summary_slide, summary_table = _slide_with_table(
        presentation, ['NetCheck KPIs', *[f'{operator} − EE' for operator in summary_view['operators']]],
    )
    assert presentation.slides.index(summary_slide) == gap_start
    summary_gap_rows = [row for row in summary_view['expanded_rows']
                        if row.get('row_type') != 'category'
                        and row['kpi'].casefold() != 'average kpi gap']
    assert all(not row['kpi'].casefold().endswith(' total') for row in summary_gap_rows)
    categories = list(dict.fromkeys(row['category'] for row in summary_gap_rows))
    # A section per category, its KPIs and the closing Total KPI GAP.
    assert len(summary_table.rows) == len(summary_gap_rows) + len(categories) + 2
    assert summary_table.cell(len(summary_table.rows) - 1, 0).text == 'Total KPI GAP'
    assert len(summary_table.columns) == len(summary_view['operators']) + 1
    sections = _section_rows(summary_table)
    assert [_label_name(summary_table.cell(row, 0).text) for row in sections] == categories
    kpi_rows = [row for row in range(1, len(summary_table.rows) - 1) if row not in sections]
    assert [_label_name(summary_table.cell(row, 0).text) for row in kpi_rows] == [row['kpi'] for row in summary_gap_rows]
    for row_index, row in zip(kpi_rows, summary_gap_rows):
        for operator_index, operator in enumerate(summary_view['operators'], 1):
            expected = row['gaps'][operator]
            cell = summary_table.cell(row_index, operator_index)
            if expected is None:
                assert cell.text == 'N/A*'
                assert cell.text_frame.paragraphs[0].runs[0].font.bold
                assert str(cell.text_frame.paragraphs[0].runs[0].font.color.rgb) == 'C62828'
            else:
                assert float(cell.text) == pytest.approx(expected, abs=.0051)
                # A GAP is a bar from the middle: to the left when behind (red), to the right when ahead (green).
                gradient = cell._tc.tcPr.find(qn('a:gradFill'))
                if expected and gradient is not None:
                    stops = [(int(stop.get('pos')), stop[0].get('val')) for stop in gradient.find(qn('a:gsLst'))]
                    coloured = [position for position, color in stops if color != 'FFFFFF']
                    assert (min(coloured) >= 50000) if expected > 0 else (max(coloured) <= 50000)
    assert 'Average KPI GAP' not in _slide_text(summary_slide)

    # The scoring charts, without the chart of Points Lost (where the points go).
    chart_shapes = [chart for slide in presentation.slides if not slide.shapes.title.text.startswith('Points Lost')
                    for chart in _charts_on_slide(slide)]
    # One Breakdown slide (28 bars) instead of two.
    assert len(chart_shapes) == 7
    best_network_chart = chart_shapes[0]
    assert best_network_chart.chart_type == XL_CHART_TYPE.COLUMN_STACKED
    best_service_slide = next(slide for slide in presentation.slides
                              if slide.shapes.title.text.split('\n')[0] == 'Best Network Scoring per Service')
    best_service_group = next(shape for shape in best_service_slide.shapes
                              if shape.name == 'Scoring Best Network Service Chart')
    best_service_chart_shape = next(shape for shape in best_service_group.shapes if shape.has_chart)
    assert best_service_chart_shape.chart.category_axis.tick_label_position == XL_TICK_LABEL_POSITION.NEXT_TO_AXIS
    assert not any(shape.name == 'Scoring Chart Aggregation Grid' for shape in best_service_group.shapes)
    assert not any(shape.name == 'Scoring Chart Value Axis Tick' for shape in best_service_group.shapes)
    assert best_network_chart.has_legend
    assert best_network_chart.plots[0].data_labels.font.name == 'Arial'
    assert best_network_chart.plots[0].data_labels.font.size.pt == 9
    assert best_network_chart.category_axis._element.xpath('./c:noMultiLvlLbl/@val') == ['1']
    assert best_network_chart.category_axis._element.xpath('./c:majorTickMark/@val') == ['none']
    assert best_network_chart._chartSpace.xpath('.//c:lineChart/c:dLbls/c:txPr//a:defRPr/@sz') == ['1200']
    assert best_network_chart.legend.position == XL_LEGEND_POSITION.TOP
    best_series = {series.name: series for series in best_network_chart.series}
    metric_by_code = {metric['code']: metric for metric in result['configuration']['metrics']}
    family_source_kinds = {'Voice': {'voice', 'speech'}, 'Data': {'data'}}
    for operator_index, operator in enumerate(MAPPED_OPERATOR_ORDER):
        voice_series = best_series[f'Voice · {operator}']
        data_series = best_series[operator]
        for family, series in (('Voice', voice_series), ('Data', data_series)):
            expected_points = sum(
                row['weighted_points'] for row in result['scoring']
                if row['operator'] == operator
                and metric_by_code[row['kpi_code']]['source_kind'] in family_source_kinds[family]
            )
            expected_values = [None] * len(MAPPED_OPERATOR_ORDER)
            expected_values[operator_index] = expected_points
            _assert_sparse_series_values(series, expected_values)
        assert _series_color(voice_series) == _voice_tint(MAPPED_OPERATOR_COLORS[operator])
        assert _series_color(data_series) == MAPPED_OPERATOR_COLORS[operator].lstrip('#').upper()
    total_series = best_series['Total']
    assert list(total_series.values) == pytest.approx([
        sum(row['weighted_points'] for row in result['scoring'] if row['operator'] == operator)
        for operator in MAPPED_OPERATOR_ORDER
    ])
    assert _legend_visible_series_names(best_network_chart) == list(MAPPED_OPERATOR_ORDER)
    line_plot = best_network_chart._chartSpace.chart.plotArea.find('{http://schemas.openxmlformats.org/drawingml/2006/chart}lineChart')
    assert line_plot.find('.//{http://schemas.openxmlformats.org/drawingml/2006/chart}dLblPos').get('val') == 't'
    assert line_plot.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}noFill') is not None
    assert chart_shapes[1].chart_type == XL_CHART_TYPE.DOUGHNUT
    environment_donut = chart_shapes[1]
    assert [category.label for category in environment_donut.plots[0].categories] == ['DriveCity']
    assert list(environment_donut.series[0].values) == pytest.approx([650.0])
    donut = chart_shapes[2]
    assert [category.label for category in donut.plots[0].categories] == ['Voice', 'Data']
    expected_family_maximums = [
        sum(metric['contexts']['DriveCity']['max_points']
            for metric in result['configuration']['metrics']
            if metric['source_kind'] in family_source_kinds[family])
        for family in ('Voice', 'Data')
    ]
    assert list(donut.series[0].values) == pytest.approx(expected_family_maximums)
    assert donut.plots[0].vary_by_categories
    assert [str(point.format.fill.fore_color.rgb) for point in donut.series[0].points] == [
        '4472C4', '7030A0',
    ]
    best_network_slide = next(slide for slide in presentation.slides
                              if slide.shapes.title.text.split('\n')[0] == 'Best Network Scoring per Service')
    best_network_text = _slide_text(best_network_slide)
    assert '650.00' in best_network_text and 'pts' in best_network_text
    assert 'Configured maximum' not in best_network_text
    assert 'Available totals:' not in best_network_text
    assert 'Voice: lighter operator color' not in best_network_text
    stacked_chart = chart_shapes[3]
    assert stacked_chart.chart_type == XL_CHART_TYPE.COLUMN_STACKED
    flat_category_slide = next(slide for slide in presentation.slides
                               if slide.shapes.title.text.split('\n')[0] == 'Best Network Scoring per Category')
    flat_category_group = next(shape for shape in flat_category_slide.shapes
                               if shape.name == 'Scoring Stacked Operator Chart')
    flat_category_chart_shape = next(shape for shape in flat_category_group.shapes if shape.has_chart)
    assert flat_category_chart_shape.chart.category_axis.tick_label_position == XL_TICK_LABEL_POSITION.NEXT_TO_AXIS
    assert not any(shape.name == 'Scoring Chart Aggregation Grid' for shape in flat_category_group.shapes)
    assert not any(shape.name == 'Scoring Chart Value Axis Tick' for shape in flat_category_group.shapes)
    assert _legend_visible_series_names(stacked_chart) == list(MAPPED_OPERATOR_ORDER)
    assert stacked_chart.plots[0].categories.depth == 1
    assert len([shape for slide in presentation.slides for shape in _nested_shapes(slide.shapes)
                if shape.name == 'Scoring Chart Category Shade Key']) == 1
    chart = chart_shapes[6]
    assert chart.chart_type == XL_CHART_TYPE.COLUMN_CLUSTERED
    assert chart.plots[0].gap_width == 140
    assert chart.plots[0].overlap == -20
    assert chart.legend.font.size.pt == 10
    categories = [category.label for category in chart.plots[0].categories]
    # Every category on one Breakdown slide (they need fewer than 50 bars).
    assert categories == list(dict.fromkeys(metric['category'] for metric in METRICS))
    assert [series.name for series in chart.series] == list(MAPPED_OPERATOR_ORDER)
    for series in chart.series:
        expected = [sum(row['weighted_points'] for row in result['scoring']
                        if row['operator'] == series.name and row['category'] == category) for category in categories]
        assert list(series.values) == pytest.approx(expected)
        assert str(series.format.fill.fore_color.rgb) == MAPPED_OPERATOR_COLORS[series.name].lstrip('#')
    assert chart.plots[0].has_data_labels
    assert chart.legend.position == XL_LEGEND_POSITION.TOP
    assert chart.legend.include_in_layout is False
    assert chart.value_axis.maximum_scale > max(value for series in chart.series for value in series.values if value is not None)
    flat_chart_slide = next(slide for slide, title in zip(presentation.slides, titles)
                            if title == 'Best Network Scoring per Category')
    flat_chart_group = next(shape for shape in flat_chart_slide.shapes
                            if shape.name == 'Scoring Stacked Operator Chart')
    flat_chart_shape = next(shape for shape in flat_chart_group.shapes if shape.has_chart)
    _assert_category_shade_bar(
        flat_chart_group, flat_chart_shape,
        list(dict.fromkeys(metric['category'] for metric in METRICS)),
    )
    clustered_slide = next(slide for slide, title in zip(presentation.slides, titles)
                           if title == 'Best Network Scoring per Category (Breakdown)')
    assert not any(shape.name == 'Scoring Chart Category Shade Key' for shape in _nested_shapes(clustered_slide.shapes))
    subtitle = clustered_slide.shapes.title.text_frame.paragraphs[1]
    assert str(clustered_slide.shapes.title.text_frame.paragraphs[0].font.color.rgb) == '1450A8'
    assert subtitle.font.size.pt == 14
    assert str(subtitle.font.color.rgb) == '245A96'
    category_environment_donut = chart_shapes[4]
    assert [category.label for category in category_environment_donut.plots[0].categories] == ['DriveCity']
    category_donut = chart_shapes[5]
    assert category_donut.chart_type == XL_CHART_TYPE.DOUGHNUT
    expected_category_maximums = {}
    for row in views['score_tables'][0]['rows']:
        expected_category_maximums[row['category']] = (
            expected_category_maximums.get(row['category'], 0) + row['max_points']
        )
    assert [category.label for category in category_donut.plots[0].categories] == [
        category.title() for category in expected_category_maximums
    ]
    assert list(category_donut.series[0].values) == pytest.approx(list(expected_category_maximums.values()))
    assert [str(point.format.fill.fore_color.rgb) for point in category_donut.series[0].points] == [
        color for color in ('4472C4', '7030A0', 'C55A11', '5B9BD5', 'A64D79', '548235', 'D65F8D')
    ]
    total_line = stacked_chart._chartSpace.xpath('.//c:lineChart/c:ser')[0]
    assert total_line.xpath('.//c:tx//c:v')[0].text == 'TOTAL SCORE'
    assert stacked_chart._chartSpace.xpath('.//c:lineChart/c:dLbls/c:dLblPos/@val') == ['t']
    assert stacked_chart._chartSpace.xpath('.//c:lineChart/c:dLbls/c:txPr//a:defRPr/@b') == ['1']
    reference_bottom = table.cell(0, operator_columns['EE'])._tc.get_or_add_tcPr().find('{http://schemas.openxmlformats.org/drawingml/2006/main}lnB')
    metadata_bottom = table.cell(0, 0)._tc.get_or_add_tcPr().find('{http://schemas.openxmlformats.org/drawingml/2006/main}lnB')
    assert reference_bottom.get('w') == metadata_bottom.get('w')
    assert reference_bottom.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr').get('val') == metadata_bottom.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}srgbClr').get('val')

    assert '2026-Q2' in '\n'.join(_slide_text(slide) for slide in presentation.slides)
    visible = '\n'.join(_slide_text(slide) for slide in presentation.slides)
    assert all(warning not in visible for warning in WARNINGS)
    assert all(all(warning in slide.notes_slide.notes_text_frame.text for warning in WARNINGS)
               for slide in presentation.slides)


def test_powerpoint_keeps_many_operators_in_one_comparison_table():
    peers = [f'Network {index:02}' for index in range(36)]
    operators = peers + ['EE']
    mapped_order = list(reversed(peers)) + ['EE']
    colors = {name: f'#{index + 1:06X}' for index, name in enumerate(mapped_order)}
    groups = _mapping_groups(mapped_order, colors)
    result = _result(
        operators,
        peer_score=lambda operator, _index, _metric: 0.80 if operator == 'EE' else 0.90,
        warnings=[],
    )
    presentation = _export(result, operator_mapping_groups=groups)
    matrices = _comparison_matrices(presentation)

    assert len(matrices) == 2
    counts = Counter()
    for table in matrices:
        operator_columns = _operator_columns(table)
        assert len(operator_columns) == len(operators)
        assert 'EE' in operator_columns
        expected_row_count = (len(METRICS) + len({metric['category'] for metric in METRICS}) + 2
                             if table is matrices[-1] else len({metric['category'] for metric in METRICS}) + 2)
        assert len(table.rows) == expected_row_count
        assert {operator: _rgb(table.cell(0, column)) for operator, column in operator_columns.items()} == {
            operator: colors[operator].lstrip('#').upper() for operator in operator_columns
        }
        counts.update(operator_columns.keys())
    assert counts['EE'] == len(matrices)
    assert {name for name in counts if name != 'EE'} == set(peers)
    assert all(counts[name] == 2 for name in peers)
    for table in matrices:
        assert [name for name in _operator_columns(table) if name != 'EE'] == [
            name for name in mapped_order if name != 'EE'
        ]
    charts = [shape.chart for slide in presentation.slides for shape in _nested_shapes(slide.shapes) if shape.has_chart]
    scoring_charts = [chart for chart in charts if chart.chart_type == XL_CHART_TYPE.COLUMN_CLUSTERED]
    assert len(scoring_charts) == len({metric['category'] for metric in METRICS})
    assert all(len(chart.plots[0].categories) == 1 for chart in scoring_charts)
    for chart in scoring_charts:
        assert [series.name for series in chart.series] == mapped_order
        assert {series.name: str(series.format.fill.fore_color.rgb) for series in chart.series} == {
            operator: colors[operator].lstrip('#').upper() for operator in mapped_order}


def test_powerpoint_empty_result_stays_readable_and_keeps_warnings_in_notes():
    empty_warning = 'No source data was available for this job.'
    presentation = _export(
        {'scoring': [], 'totals': [], 'warnings': [empty_warning]}, environment='all',
    )
    visible = '\n'.join(_slide_text(slide) for slide in presentation.slides)

    assert 'No scoring measurements are available' in visible
    assert empty_warning not in visible
    assert not _comparison_matrices(presentation)
    assert not any(shape.has_chart for slide in presentation.slides for shape in _nested_shapes(slide.shapes))
    assert all(empty_warning in slide.notes_slide.notes_text_frame.text for slide in presentation.slides)


def test_cover_campaigns_prefer_scored_contexts_and_include_context_filters():
    result = _result()
    job_fields = {
        'campaigns': ['Wrong_source_campaign'],
        'source_metadata': [{'campaigns': ['Wrong_source_campaign']}],
        'nr_mode': 'SA',
        'aggregation_levels': ['Operator', 'City'],
        'context_filters': [{'column': 'City', 'operator': '=', 'value': 'London'}],
    }
    presentation = _export(result, levels=('Operator',), job_fields=job_fields)
    for slide in (presentation.slides[index] for index in range(2)):
        text = _slide_text(slide).replace('\x0b', '\n')
        assert 'Standalone' in text and 'Split by: Operator, City' in text
        assert 'City: London' in text
        assert 'Campaigns: 2026-Q2' in text
        assert 'Wrong_source_campaign' not in text


def test_intro_slides_show_all_canonical_scope_filters_without_overlapping_campaigns():
    from src.modules import report_structure
    job_fields = {
        'context_filters': {
            'Region': ['North', 'South'],
            'City': [],
            'Operator': ['O2 UK'],
            'Vendor': [],
            'Campaign': ['UK_Q2_2026', 'UK_Q3_2026'],
        },
    }
    presentation = _export(_result(), job_fields=job_fields)
    for index in (0, 1):
        slide = presentation.slides[index]
        text = _slide_text(slide)
        assert 'Region: North, South' in text
        assert 'City: All Cities' in text
        assert 'Operator: O2 UK' in text
        assert 'Vendor: All Vendors' in text
        assert 'Campaign: UK_Q2_2026, UK_Q3_2026' not in text
        assert 'Campaigns: 2026-Q2' in text
        assert slide.slide_layout.name == 'Title Page'
        # The NR Mode is the subtitle, right below the room of two title lines (the cover's larger than a transition's).
        subtitle_shape = next(shape for shape in slide.placeholders if shape.placeholder_format.type == 4)
        title_shape = slide.shapes.title
        kind = 'cover' if index == 0 else 'transition'
        assert subtitle_shape.text == 'Non-Standalone'
        assert title_shape.top == report_structure.TITLE_TOP
        assert subtitle_shape.top == title_shape.top + report_structure.TWO_TITLE_LINES[kind]
        assert title_shape.text_frame.paragraphs[0].runs[0].font.size.pt == (54 if index == 0 else 40)
        assert subtitle_shape.text_frame.paragraphs[0].runs[0].font.size.pt == (24 if index == 0 else 20)
        assert subtitle_shape.text_frame.paragraphs[0]._p.xpath('./a:pPr/a:buNone')
        # The Campaigns, then the Split by and each filter, under the line of the layout.
        filters_shape = next(shape for shape in slide.shapes if shape.name == 'Scoring Aggregations and Filters')
        assert filters_shape.top > Inches(5.77) and filters_shape.top + filters_shape.height <= Inches(7.5)
        ordered_labels = ['Campaigns: 2026-Q2', 'Split by: Operator', 'Operator: O2 UK', 'Vendor: All Vendors',
                          'Region: North, South', 'City: All Cities']
        assert [line for line in filters_shape.text.splitlines()] == [label for label in ordered_labels] or \
            [filters_shape.text.index(label) for label in ordered_labels] == sorted(filters_shape.text.index(label) for label in ordered_labels)
        # Labels white, values yellow.
        first = filters_shape.text_frame.paragraphs[0].runs
        assert str(first[0].font.color.rgb) == 'FFFFFF' and str(first[1].font.color.rgb) == 'FFC700'
    # The cover has no counter; the Best Network block opens as the first transition.
    assert report_structure.level(presentation.slides[0]) is None
    assert report_structure.level(presentation.slides[1]) == 1
    counter = next(shape for shape in presentation.slides[1].shapes if shape.name.startswith(report_structure.COUNTER_PREFIX))
    assert counter.text == '01' and counter.top < presentation.slides[1].shapes.title.top


def test_intro_dimension_lines_keep_requested_order_independent_of_hierarchy_configuration():
    fields = ['Campaign', 'City', 'Vendor', 'Operator', 'Region']
    job_fields = {
        'aggregation_hierarchy': fields,
        'context_filters': {
            'Operator': ['O2 UK'], 'Vendor': ['Telefonica'], 'Region': ['North'],
            'City': ['London'], 'Campaign': ['UK_Q2_2026'],
        },
    }
    presentation = _export(_result(), job_fields=job_fields)
    expected = [
        'Split by: Operator', 'Operator: O2 UK', 'Vendor: Telefonica',
        'Region: North', 'City: London',
    ]
    for index in (0, 1):
        text = _slide_text(presentation.slides[index]).replace('\x0b', '\n')
        assert [text.index(label) for label in expected] == sorted(
            text.index(label) for label in expected
        )


def test_multilevel_hierarchy_export_uses_editable_nested_tables_and_one_chart_per_environment():
    base_result = _result()
    contexts = [
        ('North', 'UK_Q2_2026', False),
        ('North', 'UK_Q3_2026', False),
        ('South', 'UK_Q2_2026', False),
        ('South', 'UK_Q3_2026', True),
    ]
    scoring_rows = []
    for region, campaign, omit_baseline in contexts:
        for row in base_result['scoring']:
            if omit_baseline and row['operator'] == 'EE':
                continue
            scoring_rows.append({**row, 'region': region, 'campaign': campaign})
    result = {
        'aggregation_contract_version': 2,
        'aggregation_levels': ['Operator', 'Region', 'Campaign'],
        'scoring': scoring_rows,
        'totals': [],
        'configuration': scoring_configuration(),
        'warnings': [],
    }
    presentation = _export(
        result,
        operator_mapping_groups=_mapping_groups(),
        job_fields={
            'aggregation_contract_version': 2,
            'aggregation_levels': ['Operator', 'Region', 'Campaign'],
            'campaigns': ['UK_Q2_2026', 'UK_Q3_2026'],
        },
    )
    titles = [slide.shapes.title.text.split('\n')[0] for slide in presentation.slides]
    expected_category_count = len({metric['category'] for metric in result['configuration']['metrics']})
    assert titles.count('Best Network Scoring per Category') == 1
    assert titles.count('Best Network Scoring per Service') == 1
    # Up to 50 bars per Breakdown slide, in as few slides as possible.
    from src.modules.scoring_exports import BREAKDOWN_BARS_PER_SLIDE, _breakdown_pages
    breakdown_slides = [slide for slide, title in zip(presentation.slides, titles)
                        if title == 'Best Network Scoring per Category (Breakdown)']
    bars = [len(_charts_on_slide(slide)[0].plots[0].categories) for slide in breakdown_slides]
    assert all(count <= BREAKDOWN_BARS_PER_SLIDE for count in bars)
    assert len(breakdown_slides) == len(_breakdown_pages(list(range(expected_category_count)), sum(bars) // expected_category_count))
    category_comparison_slide = next(slide for slide, title in zip(presentation.slides, titles)
                                     if title == 'Best Network Scoring per Category (Breakdown)')
    category_comparison_chart = _charts_on_slide(category_comparison_slide)[0]
    assert category_comparison_chart.plots[0].gap_width == 120
    assert category_comparison_chart.plots[0].overlap == 100
    # Value labels fit the width of each bar (4–10pt), so a Breakdown slide with more bars has smaller ones.
    assert 4 <= category_comparison_chart.plots[0].data_labels.font.size.pt <= 10
    assert category_comparison_chart.category_axis.tick_labels.font.size.pt == 9
    assert category_comparison_chart.legend.font.size.pt == 11
    category_subtitle = category_comparison_slide.shapes.title.text_frame.paragraphs[1]
    assert str(category_comparison_slide.shapes.title.text_frame.paragraphs[0].font.color.rgb) == '1450A8'
    assert category_subtitle.font.size.pt == 14
    assert str(category_subtitle.font.color.rgb) == '245A96'
    best_network_slide = next(slide for slide, title in zip(presentation.slides, titles)
                              if title == 'Best Network Scoring per Service')
    assert best_network_slide.shapes.title.text == \
        'Best Network Scoring per Service\nBest Network — Drive - City · National · All Operators · All Vendors'
    assert str(best_network_slide.shapes.title.text_frame.paragraphs[0].font.color.rgb) == '1450A8'
    assert best_network_slide.shapes.title.text_frame.paragraphs[1].font.size.pt == 14
    best_network_chart, environment_donut, donut = _charts_on_slide(best_network_slide)
    best_network_categories = best_network_chart.plots[0].categories
    assert best_network_categories.depth == 3
    best_paths = best_network_categories.flattened_labels
    page_operators = list(dict.fromkeys(path[0] for path in best_paths))
    assert ('EE', 'North', '2026-Q2') in best_paths
    hierarchy_text = '\n'.join(
        line for line in _slide_text(best_network_slide).splitlines()
        if not (line.startswith(('Drive - City: ', 'Drive - Connecting Roads: ')) and ' pts (' in line)
    )
    assert not re.search(r'\b(?:Operator|Vendor|Region|City|Campaign):', hierarchy_text)
    metric_by_code = {metric['code']: metric for metric in result['configuration']['metrics']}
    family_source_kinds = {'Voice': {'voice', 'speech'}, 'Data': {'data'}}
    best_series = {series.name: series for series in best_network_chart.series}
    for operator in page_operators:
        for family in ('Voice', 'Data'):
            series = best_series[f'Voice · {operator}' if family == 'Voice' else operator]
            expected = []
            for path in best_paths:
                if path[0] != operator:
                    expected.append(None)
                    continue
                matching = [
                    row for row in scoring_rows
                    if row['operator'] == operator and row['region'] == path[1]
                    and _hierarchy_display_value({'level': 'Campaign', 'value': row['campaign']}) == path[2]
                    and metric_by_code[row['kpi_code']]['source_kind'] in family_source_kinds[family]
                ]
                expected.append(sum(row['weighted_points'] for row in matching) if matching else None)
            _assert_sparse_series_values(series, expected)
            expected_color = MAPPED_OPERATOR_COLORS[operator].lstrip('#').upper()
            if family == 'Voice':
                expected_color = _voice_tint(MAPPED_OPERATOR_COLORS[operator])
            assert _series_color(series) == expected_color
    expected_best_total = []
    for path in best_paths:
        matching = [row for row in scoring_rows if row['operator'] == path[0]
                    and row['region'] == path[1] and _hierarchy_display_value({'level': 'Campaign', 'value': row['campaign']}) == path[2]]
        expected_best_total.append(sum(row['weighted_points'] for row in matching) if matching else None)
    _assert_sparse_series_values(best_series['Total'], expected_best_total)
    assert _legend_visible_series_names(best_network_chart) == page_operators
    assert best_network_chart.legend.position == XL_LEGEND_POSITION.TOP
    assert best_network_chart._chartSpace.xpath('.//c:barChart/c:ser/c:dPt') == []
    service_slides = [slide for slide, title in zip(presentation.slides, titles)
                      if title == 'Best Network Scoring per Service']
    all_leaf_paths = {
        (row['operator'], row['region'],
         _hierarchy_display_value({'level': 'Campaign', 'value': row['campaign']}))
        for row in scoring_rows
    }
    observed_service_paths = []
    for page_slide in service_slides:
        page_chart = _charts_on_slide(page_slide)[0]
        page_paths = page_chart.plots[0].categories.flattened_labels
        page_operators = list(dict.fromkeys(path[0] for path in page_paths))
        assert len(page_paths) <= 20
        assert _legend_visible_series_names(page_chart) == page_operators
        service_group = next(shape for shape in page_slide.shapes
                             if shape.name == 'Scoring Best Network Service Chart')
        service_chart_shape = next(shape for shape in service_group.shapes if shape.has_chart)
        _assert_chart_hierarchy_grid(page_slide, service_group, service_chart_shape)
        observed_service_paths.extend(tuple(path) for path in page_paths)
    assert set(observed_service_paths) == all_leaf_paths
    assert len(observed_service_paths) == len(all_leaf_paths)

    expected_family_maximums = [
        sum(metric['contexts']['DriveCity']['max_points']
            for metric in result['configuration']['metrics']
            if metric['source_kind'] in family_source_kinds[family])
        for family in ('Voice', 'Data')
    ]
    assert [category.label for category in environment_donut.plots[0].categories] == ['DriveCity']
    assert list(environment_donut.series[0].values) == pytest.approx([650.0])
    assert [category.label for category in donut.plots[0].categories] == ['Voice', 'Data']
    assert list(donut.series[0].values) == pytest.approx(expected_family_maximums)
    assert 'Drive - City' in _slide_text(best_network_slide)
    for family, maximum in zip(('Voice', 'Data'), expected_family_maximums, strict=True):
        compact_maximum = f'{maximum:.3f}'.rstrip('0').rstrip('.')
        assert f'{family}: {compact_maximum} pts' in _slide_text(best_network_slide)
    assert [str(point.format.fill.fore_color.rgb) for point in donut.series[0].points] == [
        '4472C4', '7030A0',
    ]
    best_network_text = _slide_text(best_network_slide)
    assert '650.00' in best_network_text and 'pts' in best_network_text
    assert 'Configured maximum' not in best_network_text
    assert 'Available totals:' not in best_network_text
    assert 'Voice: lighter operator color' not in best_network_text

    chart_slides = [slide for slide, title in zip(presentation.slides, titles)
                    if title == 'Best Network Scoring per Category']
    observed_leaf_paths = []
    for page_slide in chart_slides:
        page_chart_group = next(shape for shape in page_slide.shapes
                                if shape.name == 'Scoring Chart With Category Key')
        page_chart_shape = next(shape for shape in page_chart_group.shapes if shape.has_chart)
        page_chart = page_chart_shape.chart
        page_paths = page_chart.plots[0].categories.flattened_labels
        page_operators = list(dict.fromkeys(path[0] for path in page_paths))
        assert len(page_paths) <= 20
        assert _legend_visible_series_names(page_chart) == page_operators
        _assert_chart_hierarchy_grid(page_slide, page_chart_group, page_chart_shape)
        if len(chart_slides) > 1:
            assert any('Page ' in shape.text for shape in page_slide.shapes if shape.has_text_frame)
        else:
            assert not any('Page ' in shape.text for shape in page_slide.shapes if shape.has_text_frame)
        observed_leaf_paths.extend(tuple(path) for path in page_paths)
    assert set(observed_leaf_paths) == all_leaf_paths
    assert len(observed_leaf_paths) == len(all_leaf_paths)

    chart_slide = chart_slides[0]
    assert chart_slide.shapes.title.text == \
        'Best Network Scoring per Category\nBest Network — Drive - City · National · All Operators · All Vendors'
    chart_group = next(shape for shape in chart_slide.shapes
                       if shape.name == 'Scoring Chart With Category Key')
    chart_shape = next(shape for shape in chart_group.shapes if shape.has_chart)
    chart = chart_shape.chart
    assert chart.has_legend
    assert chart.legend.position == XL_LEGEND_POSITION.TOP
    assert chart.legend.include_in_layout is False
    chart_categories = chart.plots[0].categories
    assert chart_categories.depth == 3
    chart_paths = chart_categories.flattened_labels
    page_operators = list(dict.fromkeys(path[0] for path in chart_paths))
    assert ('EE', 'North', '2026-Q2') in chart_paths
    assert all(not re.search(r'\b(?:Operator|Vendor|Region|City|Campaign):', label)
               for path in chart_paths for label in path)
    categories = list(dict.fromkeys(row['category'] for row in scoring_rows))
    chart_series = {series.name: series for series in chart.plots[0].series}
    for operator in page_operators:
        for category_index, category in enumerate(categories):
            name = operator if category_index == 0 else f'{operator} · {category}'
            series = chart_series[name]
            expected = []
            for path in chart_paths:
                if path[0] != operator:
                    expected.append(None)
                    continue
                matching = [
                    row for row in scoring_rows
                    if row['operator'] == operator and row['region'] == path[1]
                    and _hierarchy_display_value({'level': 'Campaign', 'value': row['campaign']}) == path[2] and row['category'] == category
                ]
                expected.append(sum(row['weighted_points'] for row in matching) if matching else None)
            _assert_sparse_series_values(series, expected)
            expected_color = _hierarchy_chart_color(
                MAPPED_OPERATOR_COLORS[operator], category_index, len(categories),
            ).lstrip('#').upper()
            assert _series_color(series) == expected_color
    assert _legend_visible_series_names(chart) == page_operators
    assert chart._chartSpace.xpath('.//c:barChart/c:ser/c:dPt') == []
    stacked_totals = [
        sum(series.values[index] or 0 for series in chart.plots[0].series)
        for index in range(len(chart.plots[0].series[0].values))
    ]
    assert chart.value_axis.maximum_scale >= max(stacked_totals)
    for index, path in enumerate(chart_paths):
        expected_total = sum(
            row['weighted_points'] for row in scoring_rows
            if row['operator'] == path[0] and row['region'] == path[1] and _hierarchy_display_value({'level': 'Campaign', 'value': row['campaign']}) == path[2]
        )
        assert stacked_totals[index] == pytest.approx(expected_total)
    assert not chart._chartSpace.xpath('.//a:ln//a:srgbClr[@val="FFFF00"]')
    assert not best_network_chart._chartSpace.xpath('.//a:ln//a:srgbClr[@val="FFFF00"]')
    assert not any(shape.name == 'Hierarchy Operator Legend' for shape in chart_slide.shapes)
    _assert_category_shade_bar(chart_group, chart_shape, categories)
    comparison_slides = [slide for slide, title in zip(presentation.slides, titles)
                         if title == 'Best Network Scoring per Category (Breakdown)']
    observed_paths_by_category = {category: [] for category in categories}
    expected_paths_by_category = {
        category: {
            (category, row['operator'], row['region'],
             _hierarchy_display_value({'level': 'Campaign', 'value': row['campaign']}))
            for row in scoring_rows if row['category'] == category
        }
        for category in categories
    }
    for page_slide in comparison_slides:
        page_group = next(shape for shape in page_slide.shapes
                          if shape.name == 'Scoring Hierarchy Category Comparison Chart')
        page_chart_shape = next(shape for shape in page_group.shapes if shape.has_chart)
        page_chart = page_chart_shape.chart
        page_paths = page_chart.plots[0].categories.flattened_labels
        page_operators = list(dict.fromkeys(path[1] for path in page_paths))
        # A Breakdown slide holds as many whole categories as fit in 50 bars; each bar's path starts with its category.
        page_categories = list(dict.fromkeys(path[0] for path in page_paths))
        assert set(page_categories) <= set(categories)
        assert len(page_paths) == len(all_leaf_paths) * len(page_categories) <= 50
        assert page_chart.plots[0].overlap == 100
        assert 4 <= page_chart.plots[0].data_labels.font.size.pt <= 10
        assert page_chart.category_axis.tick_labels.font.size.pt == 9
        assert _legend_visible_series_names(page_chart) == page_operators
        _assert_chart_hierarchy_grid(
            page_slide, page_group, page_chart_shape,
            levels={'Category', 'Operator', 'Region', 'Campaign'},
        )
        for series in page_chart.series:
            expected_values = []
            for path in page_paths:
                if path[1] != series.name:
                    expected_values.append(None)
                    continue
                matching = [row for row in scoring_rows
                            if row['category'] == path[0] and row['operator'] == series.name
                            and row['region'] == path[2]
                            and _hierarchy_display_value({'level': 'Campaign', 'value': row['campaign']}) == path[3]]
                expected_values.append(sum(row['weighted_points'] for row in matching) if matching else None)
            _assert_sparse_series_values(series, expected_values)
        for path in page_paths:
            observed_paths_by_category[path[0]].append(tuple(path))
    assert {category: set(paths) for category, paths in observed_paths_by_category.items()} == \
        expected_paths_by_category
    assert all(len(paths) == len(expected_paths_by_category[category])
               for category, paths in observed_paths_by_category.items())
    assert len([shape for shape in chart_slide.shapes if shape.has_chart
                and shape.chart.chart_type == XL_CHART_TYPE.DOUGHNUT]) == 2
    hierarchy_total_line = chart._chartSpace.xpath('.//c:lineChart/c:ser')[0]
    assert hierarchy_total_line.xpath('.//c:tx//c:v')[0].text == 'TOTAL SCORE'
    assert chart._chartSpace.xpath('.//c:lineChart/c:dLbls/c:dLblPos/@val') == ['t']
    assert chart._chartSpace.xpath('.//c:lineChart/c:dLbls/c:txPr//a:defRPr/@b') == ['1']
    score_slides = [slide for slide, title in zip(presentation.slides, titles) if title.startswith('Scoring Tables —')]
    gap_slides = [slide for slide, title in zip(presentation.slides, titles)
                  if title.startswith('GAP Analysis —')]
    assert score_slides and gap_slides
    assert len(score_slides) == 2
    score_table_shape = next(shape for shape in score_slides[-1].shapes if shape.has_table)
    score_table = score_table_shape.table
    # The header (the Score and GAP groups and the levels), a section per category with its KPIs and the total; no
    # Category, Type, Weight or Max columns.
    header_rows = 4
    assert len(score_table.rows) == header_rows + len(METRICS) + len({metric['category'] for metric in METRICS}) + 1
    assert len(score_table.columns) == 1 + 15 + 12
    export_views = build_scoring_views(
        {
            'aggregation_contract_version': 2,
            'aggregation_levels': ['Operator', 'Region', 'Campaign'],
            'baseline_operator': 'EE',
            'campaigns': ['UK_Q2_2026', 'UK_Q3_2026'],
            'configuration': scoring_configuration(),
        },
        result,
        operator_mapping_groups=_mapping_groups(),
    )
    sections = _section_rows(score_table, header_rows)
    expected_categories = list(dict.fromkeys(row['category'] for row in export_views['hierarchy_score_tables'][0]['expanded_rows']))
    assert [_label_name(score_table.cell(row, 0).text) for row in sections] == expected_categories
    for row_index in sections:
        _assert_gray_category_row(score_table, row_index)
    assert _rgb(score_table.cell(len(score_table.rows) - 1, 0)) == TOTAL_FILL
    for row in list(score_table.rows)[header_rows:]:
        for cell in list(row.cells)[1:]:
            runs = cell.text_frame.paragraphs[0].runs
            assert not runs or runs[0].font.size.pt <= row.height.pt
    summary_main_table = next(shape for shape in score_slides[0].shapes
                              if shape.has_table and len(shape.table.columns) > 1)
    summary_legend = [shape for shape in score_slides[0].shapes
                      if shape.has_table and len(shape.table.columns) == 1
                      and shape.table.cell(0, 0).text in {'Best operator', 'Worst operator'}]
    assert len(summary_legend) == 2
    assert all(shape.left >= Inches(10) for shape in summary_legend)
    assert all(shape.top + shape.height <= summary_main_table.top for shape in summary_legend)
    assert all(shape.left + shape.width <= presentation.slide_width for shape in summary_legend)
    breakdown_legend = [shape for shape in score_slides[-1].shapes
                        if shape.has_table and len(shape.table.columns) == 1
                        and shape.table.cell(0, 0).text in THRESHOLD_COLORS]
    assert len(breakdown_legend) == len(export_views['threshold_legend'])
    assert abs((breakdown_legend[-1].left + breakdown_legend[-1].width)
               - (score_table_shape.left + score_table_shape.width)) <= 20
    all_gap_slides = [slide for slide, title in zip(presentation.slides, titles)
                      if title == 'GAP Analysis — All vs EE']
    individual_gap_slides = [
        slide for slide, title in zip(presentation.slides, titles)
        if title.startswith('GAP Analysis —') and title != 'GAP Analysis — All vs EE'
    ]
    assert max(presentation.slides.index(slide) for slide in all_gap_slides) < min(
        presentation.slides.index(slide) for slide in individual_gap_slides
    )
    assert len(all_gap_slides) == 1
    all_gap_tables = [next(shape.table for shape in slide.shapes if shape.has_table)
                      for slide in all_gap_slides]
    hierarchy_gap_rows = [row for row in export_views['hierarchy_gap_tables'][0]['expanded_rows']
                          if row.get('row_type') != 'category'
                          and row['kpi'].casefold() != 'average kpi gap']
    assert all(not row['kpi'].casefold().endswith(' total') for row in hierarchy_gap_rows)
    # Three header rows (Operator, Region and Campaign: the repeated GAP row is gone), a section per category with its
    # KPIs and the Total KPI GAP; the KPI column only.
    gap_header_rows = 3
    gap_categories = list(dict.fromkeys(row['category'] for row in hierarchy_gap_rows))
    assert len(all_gap_tables[0].rows) == gap_header_rows + len(METRICS) + len(gap_categories) + 1
    assert len(all_gap_tables[0].columns) == 1 + 3 * len(contexts)
    for table in all_gap_tables:
        assert table.cell(len(table.rows) - 1, 0).text == 'Total KPI GAP'
        sections = _section_rows(table, gap_header_rows)
        assert [_label_name(table.cell(row, 0).text) for row in sections] == gap_categories
        assert [_label_name(table.cell(row_index, 0).text) for row_index in range(gap_header_rows, len(table.rows) - 1)
                if row_index not in sections] == [row['kpi'] for row in hierarchy_gap_rows]
    assert not any(cell.text == 'EE' for table in all_gap_tables
                   for row in table.rows for cell in row.cells)
    assert len(individual_gap_slides) == 3
    expected_gap_kpis = {metric['kpi'] for metric in METRICS}
    for slide in individual_gap_slides:
        operator_gap_table = next(shape.table for shape in slide.shapes if shape.has_table)
        # Ordered by GAP: no sections, each KPI with its category.
        assert len(operator_gap_table.rows) == gap_header_rows + len(METRICS) + 1
        assert len(operator_gap_table.columns) == 1 + len(contexts)
        operator_gap_kpis = [_label_name(operator_gap_table.cell(row_index, 0).text)
                             for row_index in range(gap_header_rows, len(operator_gap_table.rows) - 1)]
        assert len(operator_gap_kpis) == len(METRICS)
        assert set(operator_gap_kpis) == expected_gap_kpis
        assert all(not kpi.casefold().endswith(' total') for kpi in operator_gap_kpis)
        assert all(kpi.casefold() != 'average kpi gap' for kpi in operator_gap_kpis)
        header_text = '\n'.join(cell.text for row in list(operator_gap_table.rows)[:gap_header_rows] for cell in row.cells)
        assert 'North' in header_text and 'South' in header_text
        assert '2026-Q2' in header_text and '2026-Q3' in header_text
        assert not re.search(r'\b(?:Operator|Vendor|Region|City|Campaign):', header_text)
        assert 'GAP' not in header_text.split('\n')
    assert any(_charts_on_slide(slide) for slide, title in zip(presentation.slides, titles)
               if title == 'Best Network Scoring per Category')
    assert any(
        cell.is_merge_origin and cell.span_width > 1 and cell.text in MAPPED_OPERATOR_ORDER
        for slide in score_slides
        for shape in slide.shapes if shape.has_table
        for row in shape.table.rows
        for cell in row.cells
    )
    assert all(any(shape.has_table for shape in slide.shapes) for slide in score_slides + gap_slides)
    assert all('Average KPI GAP' not in _slide_text(slide) for slide in all_gap_slides)
    assert all('Average KPI GAP:' in _slide_text(slide) for slide in individual_gap_slides)
    hierarchy_text = '\n'.join(_slide_text(slide) for slide in score_slides + gap_slides)
    assert '2026-Q2' in hierarchy_text
    assert 'UK_Q2_2026' not in hierarchy_text
    assert 'South' in hierarchy_text
    assert not re.search(r'\b(?:Operator|Vendor|Region|City|Campaign):', hierarchy_text)


def test_unselected_campaign_stays_metadata_without_becoming_a_hierarchy_header():
    result = _result()
    result['aggregation_contract_version'] = 2
    result['aggregation_levels'] = ['Operator', 'Region']
    result['campaigns'] = ['UK_Q2_2026']
    for row in result['scoring']:
        row['campaign'] = None
    job_fields = {
        'aggregation_contract_version': 2,
        'aggregation_levels': ['Operator', 'Region'],
        'campaigns': ['UK_Q2_2026'],
    }
    job = {
        'aggregation_contract_version': 2,
        'aggregation_levels': ['Operator', 'Region'],
        'baseline_operator': 'EE',
        'configuration': scoring_configuration(),
        **job_fields,
    }
    views = build_scoring_views(job, result, _mapping_groups())
    matrix = views['hierarchy_score_tables'][0]
    assert matrix['context'] == {'environment': 'DriveCity'}
    assert all('Campaign' not in {item['level'] for item in column['path']}
               for column in matrix['hierarchy_columns'])

    presentation = _export(result, operator_mapping_groups=_mapping_groups(), job_fields=job_fields)
    intro_text = '\n'.join(_slide_text(presentation.slides[index]) for index in (0, 1))
    assert 'Campaigns: 2026-Q2' in intro_text


@pytest.mark.parametrize('hierarchy', [False, True])
def test_content_slide_subtitles_match_environment_transition(hierarchy):
    result = _result()
    fields = {'aggregation_contract_version': 2} if hierarchy else {}
    if hierarchy:
        result['aggregation_contract_version'] = 2
    presentation = _export(result, job_fields=fields, environment='all')
    environment_title = None
    for slide in list(presentation.slides)[1:]:
        title = slide.shapes.title.text.split('\n')[0]
        if slide.slide_layout.name == 'Title Page':
            environment_title = title
        else:
            # The subtitle names the scoring, and the environment unless it is All Environments.
            expected = ('Best Network' if environment_title == 'All Environments'
                        else f'Best Network — {environment_title}')
            # Insight slides add their context (City, Campaign…) after it.
            assert slide.shapes.title.text_frame.paragraphs[1].text.startswith(expected)
    assert environment_title == 'Drive - City'


@pytest.mark.parametrize('values, expected, total, color', [
    ([-4, -2, None], '-3.00', '-6.00', 'CC2424'),
    ([2, 4, None], '3.00', '6.00', '228B22'),
    ([-2, 2], '0.00', '0.00', '263746'),
    ([None], 'N/A', 'N/A', '263746'),
    ([-4, float('nan'), float('inf')], '-4.00', '-4.00', 'CC2424'),
])
def test_individual_gap_side_note_average_total_and_color(values, expected, total, color):
    from src.modules.scoring_exports import _add_individual_gap_notes, _slide

    presentation = Presentation(TEMPLATE)
    slide = _slide(presentation, 'GAP Analysis', 'Drive - City')
    _add_individual_gap_notes(slide, {'note': 'Comparison explanation.'},
                              [{'gap_points': value} for value in values])
    paragraph = slide.shapes[-1].text_frame.paragraphs[2]
    assert paragraph.text == f'Average KPI GAP: {expected} points'
    assert str(paragraph.runs[1].font.color.rgb) == color
    assert paragraph.runs[1].font.bold
    total_paragraph = slide.shapes[-1].text_frame.paragraphs[4]
    assert total_paragraph.text == f'Average total KPI GAP: {total} points'
    assert str(total_paragraph.runs[1].font.color.rgb) == color
    assert total_paragraph.runs[1].font.bold


def test_individual_gap_side_note_hierarchy_mean_marks_partial_coverage():
    from src.modules.scoring_exports import _add_individual_gap_notes, _slide

    presentation = Presentation(TEMPLATE)
    slide = _slide(presentation, 'GAP Analysis', 'All Environments')
    matrix = {'note': 'Partial coverage.', 'hierarchy_columns': [{'id': 'a'}, {'id': 'b'}]}
    rows = [
        {'gaps': {'a': -2, 'b': None}, 'gap_partial': {'a': True}},
        {'gaps': {'a': -4, 'b': 3}},
    ]
    _add_individual_gap_notes(slide, matrix, rows)
    assert 'Average KPI GAP: -1.00* points' in _slide_text(slide)
    assert 'Average total KPI GAP: -1.50* points' in _slide_text(slide)


def test_gap_total_footer_sums_columns_and_marks_missing_contributions():
    from src.modules.scoring_exports import _add_gap_total_row, _slide

    presentation = Presentation(TEMPLATE)
    slide = _slide(presentation, 'GAP Analysis', 'Drive - City')
    table = slide.shapes.add_table(4, 6, 0, 0, 6000000, 3000000).table
    rows = [
        {'gaps': {'q1': -4, 'q2': 2, 'missing': None}},
        {'gaps': {'q1': -2, 'q2': None, 'missing': None}},
    ]
    _add_gap_total_row(table, rows, ['q1', 'q2', 'missing'], size=9)
    assert table.cell(3, 0).text == 'Total KPI GAP'
    assert [table.cell(3, col).text for col in (3, 4, 5)] == ['-6.00', '2.00*', 'N/A*']


def test_saved_environment_display_name_replaces_historical_name_in_ppt():
    configuration = scoring_configuration()
    configuration['scope']['environments']['DriveCity']['display_name'] = 'Drive - City QA'
    presentation = _export(_result(), job_fields={'configuration': configuration})
    slides = list(presentation.slides)
    content = [slide for slide in slides if slide.slide_layout.name != 'Title Page']
    assert content
    for slide in content:
        assert slide.shapes.title.text_frame.paragraphs[1].text.startswith(('Best Network — Drive - City QA', 'Best Network'))
    assert any('Drive - City QA' in _slide_text(slide) for slide in slides)


def test_powerpoint_shows_environment_scaling_in_orange_and_in_the_allocation_donut():
    from src.modules.scoring import apply_environment_scaling

    result = _result()
    result.setdefault('configuration', scoring_configuration())
    result.setdefault('aggregation_levels', ['Operator'])
    result.pop('environment_scaling', None)
    apply_environment_scaling(result, 'EE')
    assert result['environment_scaling']['scaled_environments'] == ['DriveConnectionroad']
    presentation = _export(result, environment='Combined')
    notices = [shape for slide in presentation.slides for shape in slide.shapes if shape.name == 'Scoring Scaling Notice']
    assert notices and 'DriveConnectionroad has no results in any series' in notices[0].text_frame.text
    assert str(notices[0].text_frame.paragraphs[0].font.color.rgb) == 'FF8C1A'
    struck = [run for slide in presentation.slides for shape in slide.shapes if shape.has_text_frame
              for paragraph in shape.text_frame.paragraphs for run in paragraph.runs
              if run._r.rPr is not None and run._r.rPr.get('strike') == 'sngStrike']
    assert {run.text.strip() for run in struck} >= {'650 pts', '350 pts'}


def test_slides_name_the_area_operators_and_vendors_of_their_tables_as_the_web_titles(monkeypatch):
    from docx import Document

    import src.modules.pptx_to_docx as pptx_to_docx_module
    from src.modules.scoring_insight_slides import scoring_scope_labels

    filters = {'Region': [], 'City': ['Bristol', 'Cardiff', 'Leeds', 'London'], 'Operator': ['EE', 'O2 UK'],
               'Vendor': ['EE_Nokia', 'O2 UK_Ericsson']}
    presentation = _export(_result(), operator_mapping_groups=_mapping_groups(), job_fields={'context_filters': filters})
    subtitles = {}
    for slide in presentation.slides:
        paragraphs = slide.shapes.title.text_frame.paragraphs if slide.shapes.title else []
        if len(paragraphs) > 1:
            subtitles.setdefault(paragraphs[0].text, paragraphs[1])
    scope = 'Cities: Bristol, Cardiff & 2 more · Operators: EE & O2 UK · Vendors: Nokia & Ericsson'
    for title in ('Best Network Scoring per Service', 'Scoring Tables — Summary', 'GAP Analysis — All vs EE'):
        assert subtitles[title].text == f'Best Network — Drive - City · {scope}', title
    # The KPI GAP Profile names its location after them; a longer subtitle is smaller so it keeps one line.
    profile = subtitles[next(title for title in subtitles if title.startswith('KPI GAP Profile'))]
    assert profile.text == f'Best Network — Drive - City · {scope} · Region: North · Campaign: 2026-Q2'
    assert 8 <= profile.runs[0].font.size.pt < 14
    assert subtitles['Best Network Scoring per Service'].runs[0].font.size.pt < 14

    # The same rule as the web: the context first, then the filters, the most specific area first; the values the
    # slide names from its context are not repeated.
    assert scoring_scope_labels(None, {}) == ['National', 'All Operators', 'All Vendors']
    assert scoring_scope_labels({'region': 'North'}, {'City': ['London']}, omit_context=True) == [
        'City: London', 'All Operators', 'All Vendors']
    assert scoring_scope_labels({'city': 'London', 'campaign': 'UK_Q2_2026'}, {'City': ['Leeds', 'London']},
                                omit_context=True) == ['All Operators', 'All Vendors']
    assert scoring_scope_labels({'vendor': 'Nokia'}, {'Vendor': ['EE_Nokia', 'EE_Ericsson']}, ['EE'],
                                omit_context=True) == ['National', 'All Operators']
    assert scoring_scope_labels(None, [{'column': 'Region', 'value': ['Wales', 'North West']}]) == [
        'Regions: Wales & North West', 'All Operators', 'All Vendors']

    # The Word version keeps them: the slide images with LibreOffice, the slide headings without it.
    monkeypatch.setattr(pptx_to_docx_module, 'slide_images', lambda *_args, **_kwargs: None)
    output = BytesIO()
    presentation.save(output)
    document = Document(BytesIO(pptx_to_docx_module.pptx_to_docx(output.getvalue(), 'Scoring & GAP Analysis')))
    assert any(paragraph.text == f'Best Network Scoring per Service Best Network — Drive - City · {scope}'
               for paragraph in document.paragraphs)
