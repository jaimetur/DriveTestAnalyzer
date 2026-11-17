import pytest
from pptx import Presentation
from pptx.util import Inches
from src.modules.scoring.scoring_exports import _merge_category_cells

from src.modules.scoring.scoring_exports import _hierarchy_gap_projection


def _column(column_id, operator, *, is_reference=False):
    return {
        'id': column_id,
        'operator': operator,
        'is_reference': is_reference,
        'context': {},
    }


def _kpi(code, category, peer_gap):
    return {
        'row_type': 'kpi',
        'kpi_code': code,
        'category': category,
        'gaps': {'EE': None, 'O2 UK': peer_gap, 'Three UK': peer_gap},
        'gap_colors': {},
    }


def _subtotal(category, peer_gap):
    return {
        'row_type': 'category',
        'kpi_code': '',
        'category': category,
        'gaps': {'EE': None, 'O2 UK': peer_gap, 'Three UK': peer_gap},
        'gap_colors': {},
    }


def _matrix(rows, *, table_mode='expanded'):
    return {
        'operators': ['EE', 'O2 UK', 'Three UK'],
        'operator_styles': {'EE': {}, 'O2 UK': {}, 'Three UK': {}},
        'rows': rows,
        'total': {'gaps': {'EE': None, 'O2 UK': 2.0}},
        'table_mode': table_mode,
    }


def test_combined_hierarchy_projection_preserves_definition_order():
    source_rows = [
        _kpi('KPI-A', 'Category A', 1.0),
        _kpi('KPI-B', 'Category B', 5.0),
        _kpi('KPI-C', 'Category A', 4.0),
    ]
    projected = _hierarchy_gap_projection(
        _matrix(source_rows),
        [
            _column('EE', 'EE', is_reference=True),
            _column('O2 UK', 'O2 UK'),
            _column('Three UK', 'Three UK'),
        ],
    )

    assert [row['kpi_code'] for row in projected['rows']] == ['KPI-A', 'KPI-B', 'KPI-C']


def test_individual_expanded_projection_reranks_kpis_and_omits_subtotals():
    source_rows = [
        _kpi('KPI-A1', 'Category A', 1.0),
        _kpi('KPI-B1', 'Category B', 5.0),
        _kpi('KPI-A2', 'Category A', 4.0),
        _subtotal('Category A', 2.5),
        _subtotal('Category B', 5.0),
    ]
    projected = _hierarchy_gap_projection(
        _matrix(source_rows),
        [_column('EE', 'EE', is_reference=True), _column('O2 UK', 'O2 UK')],
    )

    assert [(row['row_type'], row['kpi_code'] or row['category']) for row in projected['rows']] == [
        ('kpi', 'KPI-A1'),
        ('kpi', 'KPI-A2'),
        ('kpi', 'KPI-B1'),
    ]


def test_individual_projection_orders_kpis_within_each_category_by_default():
    source_rows = [
        _kpi('KPI-A1', 'Category A', 3.0),
        _kpi('KPI-B1', 'Category B', -5.0),
        _kpi('KPI-A2', 'Category A', -1.0),
        _kpi('KPI-B2', 'Category B', 2.0),
    ]
    columns = [_column('EE', 'EE', is_reference=True), _column('O2 UK', 'O2 UK')]

    within = _hierarchy_gap_projection(_matrix(source_rows), columns)
    across = _hierarchy_gap_projection(_matrix(source_rows), columns, 'all')

    # Within each category: the categories keep their order, each one's KPIs lowest GAP first.
    assert [row['kpi_code'] for row in within['rows']] == ['KPI-A2', 'KPI-A1', 'KPI-B1', 'KPI-B2']
    assert within['gap_kpi_order'] == 'category'
    # Across all categories: one list, lowest GAP first.
    assert [row['kpi_code'] for row in across['rows']] == ['KPI-B1', 'KPI-A2', 'KPI-B2', 'KPI-A1']
    assert across['gap_kpi_order'] == 'all'


def test_combined_projection_across_all_categories_orders_by_mean_gap():
    rows = [
        {**_kpi('KPI-A', 'Category A', 0.0), 'gaps': {'EE': None, 'O2 UK': 1.0, 'Three UK': 1.0}},
        {**_kpi('KPI-B', 'Category B', 0.0), 'gaps': {'EE': None, 'O2 UK': -6.0, 'Three UK': 2.0}},
        {**_kpi('KPI-C', 'Category A', 0.0), 'gaps': {'EE': None, 'O2 UK': -1.0, 'Three UK': -1.0}},
    ]
    projected = _hierarchy_gap_projection(
        _matrix(rows),
        [_column('EE', 'EE', is_reference=True), _column('O2 UK', 'O2 UK'), _column('Three UK', 'Three UK')],
        'all',
    )

    # Means: KPI-B -2, KPI-C -1, KPI-A +1.
    assert [row['kpi_code'] for row in projected['rows']] == ['KPI-B', 'KPI-C', 'KPI-A']


def test_profile_rows_across_all_categories_list_every_kpi_lowest_gap_first():
    from src.modules.scoring.scoring_insight_slides import _profile_rows

    def kpi(code, category, gap):
        return {'kpi': code, 'service': 'Voice', 'category': category, 'gap_to_reference': {},
                'total_gap_to_reference': gap}

    profile = {'to_reference': [kpi('K1', 'Calls', -1.0), kpi('K2', 'Calls', -4.0), kpi('K3', 'Video', -3.0)]}

    within = _profile_rows(profile, 'reference')
    across = _profile_rows(profile, 'reference', 'all')

    assert [(line, row.get('kpi') or row['category']) for line, row in within] == [
        ('group', 'Calls'), ('kpi', 'K1'), ('kpi', 'K2'), ('group', 'Video'), ('kpi', 'K3')]
    assert [(line, row['kpi']) for line, row in across] == [('kpi', 'K2'), ('kpi', 'K3'), ('kpi', 'K1')]


def test_individual_summary_projection_sorts_by_numeric_signed_gap_ascending():
    source_rows = [
        _kpi('KPI-NEGATIVE', 'Category A', -2.0),
        _kpi('KPI-TEN', 'Category B', 10.0),
        _kpi('KPI-ONE', 'Category C', 1.0),
    ]
    projected = _hierarchy_gap_projection(
        _matrix(source_rows, table_mode='summary'),
        [_column('EE', 'EE', is_reference=True), _column('O2 UK', 'O2 UK')],
    )

    assert [row['kpi_code'] for row in projected['rows']] == [
        'KPI-NEGATIVE', 'KPI-ONE', 'KPI-TEN',
    ]




@pytest.mark.parametrize('include_subtotals', [False, True])
def test_category_merge_includes_only_adjacent_subtotal_when_enabled(include_subtotals):
    rows = [
        _kpi('K1', 'Category A', -3),
        _kpi('K2', 'Category A', -2),
        _subtotal('Category A', -2.5),
        _kpi('K3', 'Category B', -1),
        _kpi('K4', 'Category A', 0),
    ]
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    table = slide.shapes.add_table(6, 2, Inches(1), Inches(1), Inches(5), Inches(3)).table
    _merge_category_cells(table, rows, 1, include_subtotals=include_subtotals)
    assert table.cell(1, 0).is_merge_origin
    assert table.cell(2, 0).is_spanned
    assert table.cell(3, 0).is_spanned is include_subtotals
    assert not table.cell(4, 0).is_spanned
    assert not table.cell(5, 0).is_spanned
    assert table.cell(1, 0).text == 'Category A'
