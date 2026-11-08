from io import BytesIO

from lxml import etree
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.oxml.ns import qn
from pptx.util import Inches

from src.modules.reporting import bundle_report_templates, chart_pictures
from src.modules.reporting.chart_pictures import add_chart_pictures, misdrawn_by_apple, misdrawn_charts

MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'


def _chart_xml(plot: str, axes: str = '', legend: str = '') -> bytes:
    return (f'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart><c:plotArea>'
            f'{plot}{axes}</c:plotArea>{legend}</c:chart></c:chartSpace>').encode()


def test_only_the_charts_apples_preview_draws_wrongly_get_a_picture():
    column = '<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:ser></c:ser><c:ser></c:ser></c:barChart>'
    shown_axes = '<c:catAx><c:delete val="0"/><c:tickLblPos val="nextTo"/></c:catAx><c:valAx><c:delete val="0"/></c:valAx>'
    assert not misdrawn_by_apple(_chart_xml(column, shown_axes))
    assert not misdrawn_by_apple(_chart_xml('<c:lineChart><c:grouping val="standard"/><c:ser></c:ser><c:ser></c:ser></c:lineChart>'))
    # One stacked series is drawn right; several get a wrong scale.
    assert not misdrawn_by_apple(_chart_xml('<c:barChart><c:grouping val="stacked"/><c:ser></c:ser></c:barChart>'))
    assert misdrawn_by_apple(_chart_xml('<c:barChart><c:grouping val="stacked"/><c:ser></c:ser><c:ser></c:ser></c:barChart>'))
    assert misdrawn_by_apple(_chart_xml('<c:doughnutChart><c:ser></c:ser></c:doughnutChart>'))
    assert misdrawn_by_apple(_chart_xml('<c:pieChart><c:ser></c:ser></c:pieChart>'))
    assert misdrawn_by_apple(_chart_xml(column.replace('<c:ser></c:ser>', '<c:ser><c:cat><c:multiLvlStrRef/></c:cat></c:ser>', 1)))
    assert misdrawn_by_apple(_chart_xml(column, '<c:valAx><c:tickLblPos val="none"/></c:valAx>'))
    # A hidden axis (a c:delete without val is true) and a deleted legend entry are shown by that preview.
    assert misdrawn_by_apple(_chart_xml(column, '<c:valAx><c:delete/></c:valAx>'))
    assert misdrawn_by_apple(_chart_xml(column, '<c:catAx><c:delete val="1"/></c:catAx>'))
    assert misdrawn_by_apple(_chart_xml(column, shown_axes, '<c:legend><c:legendEntry><c:idx val="1"/><c:delete val="1"/></c:legendEntry></c:legend>'))


def _deck() -> bytes:
    """A doughnut (drawn wrongly), a clustered column (drawn right), and a group with a table, on one slide."""
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    data = CategoryChartData()
    data.categories = ['A', 'B']
    data.add_series('S1', [1, 2])
    slide.shapes.add_chart(XL_CHART_TYPE.DOUGHNUT, Inches(0.5), Inches(0.5), Inches(4), Inches(3), data)
    slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(5), Inches(0.5), Inches(4), Inches(3), data)
    table = slide.shapes.add_table(2, 2, Inches(0.5), Inches(4), Inches(4), Inches(1))
    group = slide.shapes.add_group_shape()
    group._element.append(table._element)
    group.shapes.add_textbox(Inches(5), Inches(4), Inches(2), Inches(1)).text_frame.text = 'Key'
    output = BytesIO()
    deck.save(output)
    return output.getvalue()


def _png(width: int, height: int) -> bytes:
    output = BytesIO()
    Image.new('RGBA', (width, height), (10, 20, 30, 255)).save(output, 'PNG')
    return output.getvalue()


def test_a_picture_is_the_fallback_of_each_misdrawn_chart_and_group_and_powerpoint_keeps_the_chart(monkeypatch):
    content = _deck()
    # The doughnut and the group with a table, not the clustered column.
    assert misdrawn_charts(content) == {0: [0, 2]}
    asked = []

    def pictures(deck: bytes, charts: dict) -> dict:
        asked.append(charts)
        return {(index, position): _png(72, 54) for index, positions in charts.items() for position in positions}

    # (LibreOffice draws the pictures: here they are given.)
    monkeypatch.setattr(chart_pictures, 'chart_pictures', pictures)
    result, drawn, needed = add_chart_pictures(content)
    assert (drawn, needed) == (2, 2) and asked == [{0: [0, 2]}]
    slide = Presentation(BytesIO(result)).slides[0]
    tree = slide.shapes._spTree
    alternates = tree.findall(f'{{{MC}}}AlternateContent')
    assert len(alternates) == 2
    # The clustered column stays on the slide as it was.
    assert [frame for frame in tree.findall(qn('p:graphicFrame'))
            if frame.find('.//' + qn('c:chart')) is not None] and len(tree.findall(qn('p:grpSp'))) == 0
    for alternate, kind in zip(alternates, (qn('p:graphicFrame'), qn('p:grpSp'))):
        choice, fallback = alternate.find(f'{{{MC}}}Choice'), alternate.find(f'{{{MC}}}Fallback')
        # PowerPoint and LibreOffice understand cx1 and keep the chart or group; Apple's preview takes the picture.
        assert choice.get('Requires') == 'cx1' and choice.nsmap['cx1'] == chart_pictures.CX1_NAMESPACE
        (kept,) = list(choice)
        assert kept.tag == kind
        (rectangle,) = list(fallback)
        # A rectangle filled with the picture (not a p:pic, which that preview mixes up between slides), in its place.
        assert rectangle.tag == qn('p:sp')
        blip = rectangle.find('.//' + qn('a:blipFill')).find(qn('a:blip'))
        assert slide.part.related_part(blip.get(qn('r:embed'))).content_type == 'image/png'
        place = rectangle.find(qn('p:spPr')).find(qn('a:xfrm'))
        assert chart_pictures._frame(kept) == (int(place.find(qn('a:off')).get('x')), int(place.find(qn('a:off')).get('y')),
                                               int(place.find(qn('a:ext')).get('cx')), int(place.find(qn('a:ext')).get('cy')))
    # The chart of the doughnut keeps its part (PowerPoint still edits it).
    chart = alternates[0].find('.//' + qn('c:chart'))
    assert slide.part.related_part(chart.get(qn('r:id'))).content_type.endswith('drawingml.chart+xml')
    assert b'doughnutChart' in slide.part.related_part(chart.get(qn('r:id'))).blob
    etree.fromstring(etree.tostring(slide._element))


def test_without_libreoffice_or_misdrawn_charts_the_deck_does_not_change(monkeypatch):
    content = _deck()
    monkeypatch.setattr(chart_pictures, 'chart_pictures', lambda deck, charts: None)
    assert add_chart_pictures(content) == (content, 0, 2)
    deck = Presentation(BytesIO(content))
    for shape in list(deck.slides[0].shapes):
        if shape.name.startswith('Chart 1') or shape.shape_type == 6:
            shape._element.getparent().remove(shape._element)
    output = BytesIO()
    deck.save(output)
    assert misdrawn_charts(output.getvalue()) == {}
    assert add_chart_pictures(output.getvalue()) == (output.getvalue(), 0, 0)


def test_bundle_report_templates_keep_the_chart_pictures_option_and_reuse_the_pictures(tmp_path, monkeypatch):
    assert bundle_report_templates.normalize_definition({})['chart_pictures'] is False
    definition = bundle_report_templates.normalize_definition({'chart_pictures': True})
    assert definition['chart_pictures'] is True
    assert bundle_report_templates.normalize_definition({'chart_pictures': 'yes'})['chart_pictures'] is False
    # App Events record it with what the report includes.
    assert bundle_report_templates.definition_summary(definition)['chart_pictures'] is True

    calls = []

    def add(content: bytes, progress) -> tuple[bytes, int, int]:
        calls.append(content)
        return content + b'-pictures', 3, 3

    monkeypatch.setattr(chart_pictures, 'add_chart_pictures', add)
    bundle_report_templates.document_folder(tmp_path, 'key').mkdir(parents=True)
    messages, warnings = [], []
    progress = lambda percent, message: messages.append(message)  # noqa: E731
    first = bundle_report_templates._with_chart_pictures(b'deck', tmp_path, 'key', False, progress, warnings)
    # An export that reuses the composed document reuses its pictures; a new document draws them again.
    again = bundle_report_templates._with_chart_pictures(b'deck', tmp_path, 'key', True, progress, warnings)
    recomposed = bundle_report_templates._with_chart_pictures(b'other', tmp_path, 'key', False, progress, warnings)
    assert (first, again, recomposed) == (b'deck-pictures', b'deck-pictures', b'other-pictures')
    assert calls == [b'deck', b'other'] and not warnings
    assert 'Using the charts drawn for the iPhone preview' in messages

    monkeypatch.setattr(chart_pictures, 'add_chart_pictures', lambda content, progress: (content, 0, 4))
    assert bundle_report_templates._with_chart_pictures(b'deck', None, None, False, progress, warnings) == b'deck'
    assert warnings == ['LibreOffice is not available: the charts have no pictures for the iPhone preview.']
