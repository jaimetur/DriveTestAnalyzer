import pytest
from pptx.enum.text import PP_ALIGN

from src.modules.scoring_pptx_scorecard import STYLES
from tests.test_scoring_exports import _export, _result


@pytest.mark.parametrize('levels', [('Operator',), ('Operator', 'Region', 'Campaign')])
@pytest.mark.parametrize('operators', [('EE', 'O2 UK'), ('EE', 'O2 UK', 'Three UK')])
def test_priority_arrow_is_only_on_individual_gap_slides(levels, operators):
    result = _result(operators=operators)
    if len(levels) > 1:
        result.update({'aggregation_contract_version': 2, 'aggregation_levels': list(levels)})
    presentation = _export(result, levels=levels)
    combined = individual = 0
    for slide in presentation.slides:
        title = slide.shapes.title.text
        assert all('Environment:' not in paragraph.text
                   for paragraph in slide.shapes.title.text_frame.paragraphs[1:])
        if not title.startswith('GAP Analysis'):
            continue
        all_operators = title.startswith('GAP Analysis — All vs ')
        combined += all_operators
        individual += not all_operators
        for name in ('GAP KPI Priority Arrow', 'GAP KPI Priority Label'):
            assert sum(shape.name == name for shape in slide.shapes) == (0 if all_operators else 1)
        assert any(shape.name.startswith('GAP Color Scale Segment ') for shape in slide.shapes)
        table_shape = next(shape for shape in slide.shapes if shape.has_table)
        table = table_shape.table
        # The results hold one Region and one Campaign: levels with a single value are left out,
        # so every table has the single-level header.
        header_rows = 1
        metrics = result['configuration']['metrics']
        categories = list(dict.fromkeys(metric['category'] for metric in metrics))
        section_cells = [row.cells[0] for row in list(table.rows)[header_rows:-1] if row.cells[0].text.endswith(('KPI', 'KPIs'))]
        # KPI rows (and, when the categories stay together, a section per category) end with the Total KPI GAP.
        assert len(table.rows) == header_rows + len(metrics) + len(section_cells) + 1
        assert table.cell(len(table.rows) - 1, 0).text == 'Total KPI GAP'
        labels = [row.cells[0].text for row in list(table.rows)[header_rows:-1]]
        assert not any(label.lower().endswith(' total') for label in labels)
        assert any('Average KPI GAP:' in shape.text
                   for shape in slide.shapes if shape.has_text_frame) == (not all_operators)
        if section_cells:
            # Every category opens a section in the colour of the theme's sections.
            assert all_operators
            assert [cell.text.split('   ')[0] for cell in section_cells] == categories
            assert {str(cell.fill.fore_color.rgb).upper() for cell in section_cells} == {STYLES['netcheck']['section'].lstrip('#')}
        else:
            # Ordered by GAP, each KPI carries its category.
            assert all(label.split(' · ')[0].title() in {category.title() for category in categories} for label in labels)
        scale_heading = next(shape for shape in slide.shapes
                             if shape.has_text_frame and shape.text == 'GAP color scale')
        assert table_shape.top + table_shape.height < scale_heading.top
        if not all_operators:
            label = next(shape for shape in slide.shapes if shape.name == 'GAP KPI Priority Label')
            arrow = next(shape for shape in slide.shapes if shape.name == 'GAP KPI Priority Arrow')
            assert arrow.top > label.top + label.height
            assert arrow.top + arrow.height == table_shape.top + table_shape.height
        for cell in section_cells:
            for paragraph in cell.text_frame.paragraphs:
                assert paragraph.alignment == PP_ALIGN.LEFT
                assert paragraph.runs and paragraph.runs[0].font.bold
    assert combined == 1
    assert individual == len(operators) - 1
