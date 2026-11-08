"""Pictures of the charts that Apple's preview draws wrongly, kept in the deck as the alternative of each chart.

The preview of the iPhone, iPad and Mac (Quick Look, also in Mail and Files) and Keynote draw the native charts with
an engine of their own, which ignores part of them: pies and doughnuts lose their colours and rings, multi-level
categories lose their levels, stacked series with several series get a wrong scale, and hidden axes and deleted legend
entries are shown. It also leaves out the tables (and charts) of a group, such as the category labels and keys drawn
around the Scoring charts. Each of those charts and groups is wrapped in an mc:AlternateContent whose Choice (the chart
or group) requires the chart extensions of Office 2016 (cx1) and whose Fallback is a picture of it drawn by
LibreOffice. PowerPoint (and LibreOffice) understand cx1 and show and edit the chart or group, never the picture;
Apple's preview does not, so it shows the picture.

The picture fills a rectangle (a:blipFill of a p:sp) instead of being a p:pic: Apple's preview gives the p:pic of a
Fallback the picture of another slide (always the same ones for the same deck), but draws the fill of each shape right.
It draws a fill at the size of its pixels (one pixel a point), so the picture has the size of the chart in points.
The Word version and the previews of the application are made from the deck without the pictures."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any, Callable

MC_NAMESPACE = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
# The chart extensions of Office 2016 (chartex), understood by PowerPoint and LibreOffice but not by Apple's preview.
CX1_NAMESPACE = 'http://schemas.microsoft.com/office/drawing/2015/9/8/chartex'
CHART_URI = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
# The pictures are drawn at 72 dpi: Apple's preview draws a fill one pixel a point (see the module).
PICTURE_ZOOM = 1.0

_PIE = re.compile(rb'<c:(?:pie|pie3D|doughnut|ofPie)Chart\b')
_MULTI_LEVEL = re.compile(rb'<c:multiLvlStrRef\b')
_HIDDEN_LABELS = re.compile(rb'<c:tickLblPos val="none"')
_AXIS = re.compile(rb'<c:(?:valAx|catAx|dateAx|serAx)>(.*?)</c:(?:valAx|catAx|dateAx|serAx)>', re.S)
# (A c:delete without val is true.)
_DELETED = re.compile(rb'<c:delete(?:\s*/>|\s+val="(?:1|true)")')
_LEGEND_ENTRY = re.compile(rb'<c:legendEntry>(.*?)</c:legendEntry>', re.S)
_STACKED_PLOT = re.compile(rb'<c:(barChart|areaChart|lineChart)>(.*?)</c:\1>', re.S)
_STACKED = re.compile(rb'<c:grouping val="stacked"')


def misdrawn_by_apple(chart_xml: bytes) -> bool:
    """Whether Apple's preview draws the chart of ``chart_xml`` (its chart part) wrongly."""
    if _PIE.search(chart_xml) or _MULTI_LEVEL.search(chart_xml) or _HIDDEN_LABELS.search(chart_xml):
        return True
    if any(_DELETED.search(axis.group(1)) for axis in _AXIS.finditer(chart_xml)):
        return True
    if any(_DELETED.search(entry.group(1)) for entry in _LEGEND_ENTRY.finditer(chart_xml)):
        return True
    # Stacked series get the scale of their sum many times over (one stacked series is drawn right).
    return any(_STACKED.search(plot.group(2)) and plot.group(2).count(b'<c:ser>') > 1
               for plot in _STACKED_PLOT.finditer(chart_xml))


def _qn(tag: str) -> str:
    from pptx.oxml.ns import qn

    return qn(tag)


def _is_chart(element: Any) -> bool:
    if element.tag != _qn('p:graphicFrame'):
        return False
    data = element.find('.//' + _qn('a:graphicData'))
    return data is not None and data.get('uri') == CHART_URI


def _transform(element: Any) -> Any:
    """The xfrm that places a chart or a group."""
    if element.tag == _qn('p:graphicFrame'):
        return element.find(_qn('p:xfrm'))
    properties = element.find(_qn('p:grpSpPr'))
    return None if properties is None else properties.find(_qn('a:xfrm'))


def _drawings(slide: Any) -> list[Any]:
    """The charts and groups placed right on the slide, in their order (a group that is rotated or flipped, or has no
    place, left out)."""
    found = []
    for child in slide.shapes._spTree:
        if not _is_chart(child) and child.tag != _qn('p:grpSp'):
            continue
        transform = _transform(child)
        if transform is None or transform.find(_qn('a:off')) is None or transform.find(_qn('a:ext')) is None \
                or transform.get('rot') not in (None, '0') or transform.get('flipH') in ('1', 'true') \
                or transform.get('flipV') in ('1', 'true'):
            continue
        found.append(child)
    return found


def _chart_xml(slide: Any, frame: Any) -> bytes | None:
    chart = frame.find('.//' + _qn('c:chart'))
    relationship = chart.get(_qn('r:id')) if chart is not None else None
    if not relationship or relationship not in slide.part.rels:
        return None
    return slide.part.related_part(relationship).blob


def _misdrawn(slide: Any, element: Any) -> bool:
    """Whether Apple's preview draws the chart or group ``element`` wrongly: a group with a table or chart."""
    if element.tag == _qn('p:grpSp'):
        return element.find('.//' + _qn('p:graphicFrame')) is not None
    xml = _chart_xml(slide, element)
    return xml is not None and misdrawn_by_apple(xml)


def _frame(element: Any) -> tuple[int, int, int, int]:
    transform = _transform(element)
    offset, extent = transform.find(_qn('a:off')), transform.find(_qn('a:ext'))
    return int(offset.get('x')), int(offset.get('y')), int(extent.get('cx')), int(extent.get('cy'))


def misdrawn_charts(content: bytes) -> dict[int, list[int]]:
    """The charts and groups of the deck ``content`` that Apple's preview draws wrongly: their positions among the
    charts and groups placed right on each slide (_drawings), by slide index."""
    from pptx import Presentation

    found: dict[int, list[int]] = {}
    for index, slide in enumerate(Presentation(BytesIO(content)).slides):
        positions = [position for position, element in enumerate(_drawings(slide)) if _misdrawn(slide, element)]
        if positions:
            found[index] = positions
    return found


def _chart_deck(content: bytes, charts: dict[int, list[int]], turn: int, colour: str) -> tuple[bytes, list[tuple[int, Any]]]:
    """The deck with the slides that have a turn-th chart or group to draw, each holding only that one on a
    ``colour`` background, and those slides with its place."""
    from lxml import etree
    from pptx import Presentation

    deck = Presentation(BytesIO(content))
    ids = deck.slides._sldIdLst
    kept = []
    for index, (slide, slide_id) in enumerate(zip(list(deck.slides), list(ids))):
        positions = charts.get(index) or []
        if len(positions) <= turn:
            deck.part.drop_rel(slide_id.rId)
            ids.remove(slide_id)
            continue
        chart = _drawings(slide)[positions[turn]]
        tree = slide.shapes._spTree
        for child in list(tree)[2:]:
            if child is not chart:
                tree.remove(child)
        # Without the shapes of the layout and master, on a plain background.
        slide._element.set('showMasterSp', '0')
        common = slide._element.cSld
        for background in common.findall(_qn('p:bg')):
            common.remove(background)
        background = etree.Element(_qn('p:bg'))
        common.insert(0, background)
        properties = etree.SubElement(background, _qn('p:bgPr'))
        fill = etree.SubElement(properties, _qn('a:solidFill'))
        etree.SubElement(fill, _qn('a:srgbClr')).set('val', colour)
        etree.SubElement(properties, _qn('a:effectLst'))
        kept.append((index, _frame(chart)))
    output = BytesIO()
    deck.save(output)
    return output.getvalue(), kept


def _crops(pdf: bytes, kept: list[tuple[int, Any]], width: int) -> list[Any]:
    """The region of each chart or group on its page of ``pdf``, as an RGB array of floats."""
    import numpy as np
    import pymupdf

    images = []
    with pymupdf.open(stream=pdf, filetype='pdf') as document:
        for page, (_index, (left, top, wide, high)) in zip(document, kept):
            scale = page.rect.width / width
            clip = pymupdf.Rect(left * scale, top * scale, (left + wide) * scale, (top + high) * scale)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(PICTURE_ZOOM, PICTURE_ZOOM), clip=clip, alpha=False)
            images.append(np.frombuffer(pixmap.samples, dtype=np.uint8)
                          .reshape(pixmap.height, pixmap.width, pixmap.n)[..., :3].astype(np.float32))
    return images


def _transparent_png(on_white: Any, on_black: Any) -> bytes:
    """The picture of a chart or group with its transparency, from it drawn on white and on black."""
    import numpy as np
    from PIL import Image

    if on_white.shape != on_black.shape:
        height, wide = min(on_white.shape[0], on_black.shape[0]), min(on_white.shape[1], on_black.shape[1])
        on_white, on_black = on_white[:height, :wide], on_black[:height, :wide]
    # What lets the background through is as light on white as it is dark on black.
    alpha = np.clip(255 - (on_white - on_black).mean(axis=2), 0, 255)
    colour = np.where(alpha[..., None] > 0, on_black * 255 / np.maximum(alpha[..., None], 1), 0)
    picture = np.dstack([np.clip(colour, 0, 255), alpha]).astype(np.uint8)
    output = BytesIO()
    Image.fromarray(picture, 'RGBA').save(output, 'PNG', optimize=True)
    return output.getvalue()


def chart_pictures(content: bytes, charts: dict[int, list[int]]) -> dict[tuple[int, int], bytes] | None:
    """The pictures of ``charts`` (the charts and groups as misdrawn_charts gives them) drawn by LibreOffice, by
    (slide index, position); None when LibreOffice is not available."""
    from pptx import Presentation

    from src.modules.reporting.pptx_to_docx import document_pdf

    width = Presentation(BytesIO(content)).slide_width
    pictures: dict[tuple[int, int], bytes] = {}
    # One deck for the first chart of each slide, another one for the second chart, and so on.
    for turn in range(max((len(positions) for positions in charts.values()), default=0)):
        (white, kept), (black, _kept) = _chart_deck(content, charts, turn, 'FFFFFF'), _chart_deck(content, charts, turn, '000000')
        with ThreadPoolExecutor(max_workers=2) as pool:
            on_white, on_black = pool.map(lambda deck: document_pdf(deck, 'pptx'), (white, black))
        if on_white is None or on_black is None:
            return None
        for (index, _place), white_image, black_image in zip(kept, _crops(on_white, kept, width), _crops(on_black, kept, width)):
            pictures[(index, charts[index][turn])] = _transparent_png(white_image, black_image)
    return pictures


def _wrap(slide: Any, frame: Any, picture: bytes) -> None:
    """Put the chart or group ``frame`` in the Choice of an mc:AlternateContent whose Fallback is a rectangle in its
    place filled with ``picture``."""
    from lxml import etree

    _image_part, relationship = slide.part.get_or_add_image_part(BytesIO(picture))
    properties = frame.find(_qn('p:nvGraphicFramePr' if frame.tag == _qn('p:graphicFrame') else 'p:nvGrpSpPr')).find(_qn('p:cNvPr'))
    left, top, wide, high = _frame(frame)
    alternate = etree.Element(f'{{{MC_NAMESPACE}}}AlternateContent', nsmap={'mc': MC_NAMESPACE})
    choice = etree.SubElement(alternate, f'{{{MC_NAMESPACE}}}Choice', nsmap={'cx1': CX1_NAMESPACE})
    choice.set('Requires', 'cx1')
    fallback = etree.SubElement(alternate, f'{{{MC_NAMESPACE}}}Fallback')
    frame.addprevious(alternate)
    choice.append(frame)
    shape = etree.SubElement(fallback, _qn('p:sp'))
    names = etree.SubElement(shape, _qn('p:nvSpPr'))
    name = etree.SubElement(names, _qn('p:cNvPr'))
    name.set('id', properties.get('id'))
    name.set('name', properties.get('name') or 'Chart')
    etree.SubElement(names, _qn('p:cNvSpPr'))
    etree.SubElement(names, _qn('p:nvPr'))
    shape_properties = etree.SubElement(shape, _qn('p:spPr'))
    transform = etree.SubElement(shape_properties, _qn('a:xfrm'))
    offset = etree.SubElement(transform, _qn('a:off'))
    offset.set('x', str(left))
    offset.set('y', str(top))
    extent = etree.SubElement(transform, _qn('a:ext'))
    extent.set('cx', str(wide))
    extent.set('cy', str(high))
    etree.SubElement(etree.SubElement(shape_properties, _qn('a:prstGeom'), prst='rect'), _qn('a:avLst'))
    fill = etree.SubElement(shape_properties, _qn('a:blipFill'))
    etree.SubElement(fill, _qn('a:blip')).set(_qn('r:embed'), relationship)
    etree.SubElement(etree.SubElement(fill, _qn('a:stretch')), _qn('a:fillRect'))
    etree.SubElement(etree.SubElement(shape_properties, _qn('a:ln')), _qn('a:noFill'))


def add_chart_pictures(content: bytes, progress: Callable[[str], None] = lambda _message: None) -> tuple[bytes, int, int]:
    """The deck ``content`` with a picture of each chart and group that Apple's preview draws wrongly, as their
    alternative (see the module), how many got one and how many needed one; the deck as it was when none needs one or
    LibreOffice is not available."""
    from pptx import Presentation

    charts = misdrawn_charts(content)
    total = sum(len(positions) for positions in charts.values())
    if not total:
        return content, 0, 0
    progress(f'Drawing {total} chart{"s" if total != 1 else ""} for the iPhone preview')
    pictures = chart_pictures(content, charts)
    if not pictures:
        return content, 0, total
    deck = Presentation(BytesIO(content))
    for index, slide in enumerate(deck.slides):
        frames = _drawings(slide)
        for position in charts.get(index) or []:
            picture = pictures.get((index, position))
            if picture is not None:
                _wrap(slide, frames[position], picture)
    output = BytesIO()
    deck.save(output)
    return output.getvalue(), len(pictures), total
