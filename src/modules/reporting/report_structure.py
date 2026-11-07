"""The covers and transitions of the PowerPoint reports, alike in every module.

A report starts with its cover; its transitions open each part of it (a module of a Bundle Report Template, a scenario, a
scoring, an environment, a Design or a transition of its PPT Template). Every cover has one size of title and
subtitle and every transition another, smaller one, whatever the module; the subtitle starts right below the room of
two title lines, so a long title wraps into it. Each transition shows its counter above the title: 01, 02… for the first
level and 2.1, 2.1.1… below it.

A module marks each of its transitions with its level (``mark``), kept in the slide (the name of the box of its counter),
so a Bundle Report Template that copies the slides of a module can move them one or two levels down (``shift``) before
``finish`` writes every counter and size.
"""
from __future__ import annotations

from typing import Any

from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches, Pt

COUNTER_PREFIX = 'Transition number · level '
SUBTITLE_NAME = 'Transition subtitle'
COVER_TITLE_PT, COVER_SUBTITLE_PT = 54, 24
TRANSITION_TITLE_PT, TRANSITION_SUBTITLE_PT, COUNTER_PT = 40, 20, 48
TITLE_LEFT, TITLE_TOP, RIGHT_MARGIN = Inches(0.52), Inches(2.32), Inches(0.52)
# The room of two title lines: the subtitle starts below it.
TWO_TITLE_LINES = {'cover': Inches(1.95), 'transition': Inches(1.45)}
COUNTER_HEIGHT, COUNTER_GAP = Inches(0.95), Inches(1.02)
SUBTITLE_HEIGHT = Inches(0.8)


def _counter(slide: Any) -> Any:
    return next((shape for shape in slide.shapes if str(shape.name).startswith(COUNTER_PREFIX)), None)


def _title(slide: Any) -> Any:
    return next((shape for shape in slide.placeholders if shape.placeholder_format.type in {1, 3} and shape.has_text_frame),
                None)


def mark(slide: Any, level: int) -> None:
    """Make the slide a transition of ``level`` (1 for the first level), its counter written by ``finish``."""
    counter = _counter(slide)
    if counter is None:
        counter = slide.shapes.add_textbox(TITLE_LEFT, TITLE_TOP - COUNTER_GAP, Inches(4), COUNTER_HEIGHT)
    counter.name = f'{COUNTER_PREFIX}{max(1, int(level))}'


def level(slide: Any) -> int | None:
    """The level of a transition, or None for any other slide."""
    counter = _counter(slide)
    if counter is None:
        return None
    try:
        return max(1, int(str(counter.name)[len(COUNTER_PREFIX):]))
    except ValueError:
        return 1


def shift(slide: Any, by: int) -> None:
    """A transition ``by`` levels down (a module's transitions inside a Bundle Report Template)."""
    current = level(slide)
    if current is not None:
        mark(slide, current + by)


def _place(slide: Any, kind: str, width: int) -> None:
    """The title at its place and sizes, and the subtitle right below the room of two title lines: the subtitle
    placeholder moved there, or the subtitle written under the title taken out into its own box."""
    title = _title(slide)
    if title is None:
        return
    title_pt = COVER_TITLE_PT if kind == 'cover' else TRANSITION_TITLE_PT
    subtitle_pt = COVER_SUBTITLE_PT if kind == 'cover' else TRANSITION_SUBTITLE_PT
    room = TWO_TITLE_LINES[kind]
    frame = title.text_frame
    paragraphs = list(frame.paragraphs)
    extra = '\n'.join(''.join(run.text for run in paragraph.runs) for paragraph in paragraphs[1:]).strip()
    for paragraph in paragraphs[1:]:
        paragraph._p.getparent().remove(paragraph._p)
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.TOP
    for paragraph in frame.paragraphs:
        paragraph.font.size = Pt(title_pt)
        for run in paragraph.runs:
            run.font.size = Pt(title_pt)
    # A placeholder placed by its layout gets its whole geometry written: one value alone would leave it no width.
    title.left, title.top, title.width, title.height = TITLE_LEFT, TITLE_TOP, width - TITLE_LEFT - RIGHT_MARGIN, room
    subtitle = next((shape for shape in slide.placeholders if shape.placeholder_format.type == 4 and shape.has_text_frame),
                    None) or next((shape for shape in slide.shapes if shape.name == SUBTITLE_NAME), None)
    if subtitle is None and extra:
        subtitle = slide.shapes.add_textbox(TITLE_LEFT, TITLE_TOP + room, title.width, SUBTITLE_HEIGHT)
        subtitle.name = SUBTITLE_NAME
        sub_frame = subtitle.text_frame
        sub_frame.margin_left = frame.margin_left
        sub_frame.margin_top = sub_frame.margin_bottom = 0
        run = sub_frame.paragraphs[0].add_run()
        run.text = extra
        run.font.color.theme_color = MSO_THEME_COLOR.ACCENT_4
    if subtitle is None:
        return
    height = subtitle.height or SUBTITLE_HEIGHT
    subtitle.left, subtitle.top, subtitle.width, subtitle.height = TITLE_LEFT, TITLE_TOP + room, title.width, height
    subtitle.text_frame.word_wrap = True
    subtitle.text_frame.vertical_anchor = MSO_ANCHOR.TOP
    for paragraph in subtitle.text_frame.paragraphs:
        paragraph.font.size = Pt(subtitle_pt)
        for run in paragraph.runs:
            run.font.size = Pt(subtitle_pt)


def _write_counter(slide: Any, label: str) -> None:
    counter = _counter(slide)
    counter.left, counter.top, counter.width, counter.height = TITLE_LEFT, TITLE_TOP - COUNTER_GAP, Inches(4), COUNTER_HEIGHT
    frame = counter.text_frame
    frame.clear()
    title = _title(slide)
    frame.margin_left = title.text_frame.margin_left if title is not None else 0
    frame.margin_top = frame.margin_bottom = 0
    frame.word_wrap = False
    run = frame.paragraphs[0].add_run()
    run.text = label
    run.font.size, run.font.bold = Pt(COUNTER_PT), True
    run.font.color.theme_color = MSO_THEME_COLOR.BACKGROUND_1


def label(counters: list[int]) -> str:
    """01, 02… for the first level; 2.1, 2.1.1… below it."""
    return f'{counters[0]:02d}' if len(counters) == 1 else '.'.join(str(value) for value in counters)


class Counter:
    """The counters of the transitions of a report, in order: ``next(level)`` gives the label of the next one."""

    def __init__(self) -> None:
        self.counters: list[int] = []

    def next(self, current: int) -> str:
        self.counters = self.counters[:current]
        while len(self.counters) < current:
            self.counters.append(0)
        self.counters[current - 1] += 1
        # A level below one the report does not have (a transition of a Design without its cover) counts from 1.
        return label([value or 1 for value in self.counters])


def _run_sizes(element: Any) -> list[int]:
    """The sizes (hundredths of a point) of the runs with text in an element of a slide."""
    from pptx.oxml.ns import qn

    sizes = []
    for run in element.iter(qn('a:r')):
        properties = run.find(qn('a:rPr'))
        if run.findtext(qn('a:t')) and properties is not None and properties.get('sz'):
            sizes.append(int(properties.get('sz')))
    return sizes


def size_empty_table_paragraphs(presentation: Any) -> None:
    """Give every paragraph without text of a table cell the size of the text of its row (of its table when the row has
    none), never more than half the height of the row. PowerPoint draws a paragraph without text at the size of its
    end-of-paragraph properties, 18 pt when it has none, which makes its row taller than declared and moves away from
    their rows the bars and labels placed over the empty cells of a table."""
    from pptx.oxml.ns import qn

    for slide in presentation.slides:
        for table in slide.shapes._spTree.iter(qn('a:tbl')):
            table_sizes = None
            for row in table.findall(qn('a:tr')):
                empty = []
                for paragraph in row.iter(qn('a:p')):
                    properties = paragraph.find(qn('a:endParaRPr'))
                    if not any(text.text for text in paragraph.iter(qn('a:t'))) and (properties is None or not properties.get('sz')):
                        empty.append(paragraph)
                if not empty:
                    continue
                if table_sizes is None:
                    table_sizes = _run_sizes(table)
                # Half the height of the row (127 EMU a hundredth of a point), at least 1 pt.
                size = min(min(_run_sizes(row) or table_sizes or [900]), max(100, int(row.get('h', '0')) // 127 // 2))
                for paragraph in empty:
                    properties = paragraph.find(qn('a:endParaRPr'))
                    if properties is None:
                        properties = paragraph.makeelement(qn('a:endParaRPr'), {})
                        paragraph.append(properties)
                    properties.set('sz', str(size))


# The style python-pptx gives every shape it adds (lnRef, fillRef, effectRef): the line, fill and effect of the theme.
PPTX_SHAPE_STYLE = ('1', '3', '2')
SVG_BLIP = '{http://schemas.microsoft.com/office/drawing/2016/SVG/main}svgBlip'
# The width (pixels) of the PNG drawn from an SVG picture.
SVG_FALLBACK_WIDTH = 1200


def drop_theme_shadows(presentation: Any) -> None:
    """Take the shadow of the theme off the shapes the modules draw. python-pptx gives every shape it adds the second
    effect of the theme through its style, a drop shadow in the Ericsson templates, which the iPhone and Mac previews
    draw as boxes in the first accent colour of the theme away from their shapes. Shapes with effects of their own and
    those of the templates (another style) keep theirs."""
    from pptx.oxml.ns import qn

    for slide in presentation.slides:
        for shape in slide.shapes._spTree.iter(qn('p:sp')):
            style, properties = shape.find(qn('p:style')), shape.find(qn('p:spPr'))
            if style is None or properties is None:
                continue
            references = tuple(None if (reference := style.find(qn(f'a:{name}'))) is None else reference.get('idx')
                               for name in ('lnRef', 'fillRef', 'effectRef'))
            if references == PPTX_SHAPE_STYLE and properties.find(qn('a:effectLst')) is None \
                    and properties.find(qn('a:effectDag')) is None:
                properties.get_or_add_effectLst()


def _svg_png(svg: bytes) -> bytes | None:
    """A PNG of an SVG, SVG_FALLBACK_WIDTH pixels wide with its transparency, or None when it cannot be drawn."""
    try:
        import pymupdf

        with pymupdf.open(stream=svg, filetype='svg') as document:
            page = document[0]
            zoom = max(1.0, SVG_FALLBACK_WIDTH / max(page.rect.width, 1.0))
            return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True).tobytes('png')
    except Exception:  # noqa: BLE001 - a picture that cannot be drawn keeps only its SVG
        return None


def add_svg_fallbacks(presentation: Any) -> None:
    """Give every picture of the slides, layouts and masters that has only an SVG (the operators' logo of the
    templates) a PNG of it, as PowerPoint does when it inserts one: the iPhone and Mac previews, which do not draw SVG,
    show an empty frame without it."""
    from io import BytesIO

    from pptx.opc.constants import CONTENT_TYPE, RELATIONSHIP_TYPE
    from pptx.oxml.ns import qn

    kinds = {CONTENT_TYPE.PML_SLIDE, CONTENT_TYPE.PML_SLIDE_LAYOUT, CONTENT_TYPE.PML_SLIDE_MASTER}
    package = presentation.part.package
    images: dict[str, Any] = {}
    for part in list(package.iter_parts()):
        if part.content_type not in kinds:
            continue
        for blip in part._element.iter(qn('a:blip')):
            svg = next(blip.iter(SVG_BLIP), None)
            if svg is None or blip.get(qn('r:embed')) or blip.get(qn('r:link')) or svg.get(qn('r:embed')) not in part.rels:
                continue
            svg_part = part.related_part(svg.get(qn('r:embed')))
            name = str(svg_part.partname)
            if name not in images:
                png = _svg_png(svg_part.blob)
                images[name] = package.get_or_add_image_part(BytesIO(png)) if png else None
            if images[name] is not None:
                blip.set(qn('r:embed'), part.relate_to(images[name], RELATIONSHIP_TYPE.IMAGE))


CHART_URI = 'http://schemas.openxmlformats.org/drawingml/2006/chart'


def _transform(element: Any) -> Any:
    """The a:xfrm (p:xfrm of a graphic frame) that places a shape of a group, or None."""
    from pptx.oxml.ns import qn

    if element.tag == qn('p:graphicFrame'):
        return element.find(qn('p:xfrm'))
    properties = element.find(qn('p:grpSpPr' if element.tag == qn('p:grpSp') else 'p:spPr'))
    return None if properties is None else properties.find(qn('a:xfrm'))


def _is_chart(element: Any) -> bool:
    from pptx.oxml.ns import qn

    return element.tag == qn('p:graphicFrame') and any(data.get('uri') == CHART_URI for data in element.iter(qn('a:graphicData')))


def _take_out_charts(group: Any) -> None:
    """Put the charts of ``group`` (and the shapes under them) right before it, where the group shows them; the shapes
    above them stay in the group, which keeps its place (an empty group goes)."""
    from pptx.oxml.ns import qn

    frame = group.find(qn('p:grpSpPr')).find(qn('a:xfrm'))
    offset, size = frame.find(qn('a:off')), frame.find(qn('a:ext'))
    child_offset, child_size = frame.find(qn('a:chOff')), frame.find(qn('a:chExt'))
    scale_x = int(size.get('cx')) / int(child_size.get('cx')) if int(child_size.get('cx') or 0) else 1.0
    scale_y = int(size.get('cy')) / int(child_size.get('cy')) if int(child_size.get('cy') or 0) else 1.0
    children = [item for item in group if item.tag not in (qn('p:nvGrpSpPr'), qn('p:grpSpPr'))]
    last_chart = max(index for index, child in enumerate(children) if _is_chart(child))
    parent = group.getparent()
    for child in children[:last_chart + 1]:
        transform = _transform(child)
        if transform is not None and transform.find(qn('a:off')) is not None and transform.find(qn('a:ext')) is not None:
            place, extent = transform.find(qn('a:off')), transform.find(qn('a:ext'))
            place.set('x', str(round(int(offset.get('x')) + (int(place.get('x')) - int(child_offset.get('x'))) * scale_x)))
            place.set('y', str(round(int(offset.get('y')) + (int(place.get('y')) - int(child_offset.get('y'))) * scale_y)))
            extent.set('cx', str(round(int(extent.get('cx')) * scale_x)))
            extent.set('cy', str(round(int(extent.get('cy')) * scale_y)))
        parent.insert(parent.index(group), child)
    if len(children) == last_chart + 1:
        parent.remove(group)


def ungroup_charts(presentation: Any) -> None:
    """Take the charts of the slides out of their groups: the iPhone and Mac previews place a chart of a group in the
    units of the file instead of points, far outside its slide, and show the slide without it (the bars of the Scoring
    charts). Each chart goes right before its group, where the group shows it, with the shapes of the group under it;
    the shapes above it (keys, grids, labels) stay grouped. Groups that are rotated or flipped keep their charts."""
    from pptx.oxml.ns import qn

    for slide in presentation.slides:
        kept: list[Any] = []
        while True:
            # A chart moves out of one group at a time, so a chart of a group in a group moves out of both.
            group = next((group for group in slide.shapes._spTree.iter(qn('p:grpSp'))
                          if not any(group is item for item in kept) and any(_is_chart(child) for child in group)), None)
            if group is None:
                break
            frame = group.find(qn('p:grpSpPr')).find(qn('a:xfrm'))
            if frame is None or frame.get('rot') not in (None, '0') or frame.get('flipH') in ('1', 'true') \
                    or frame.get('flipV') in ('1', 'true') or any(frame.find(qn(f'a:{name}')) is None
                                                                  for name in ('off', 'ext', 'chOff', 'chExt')):
                kept.append(group)
                continue
            _take_out_charts(group)


def finish(presentation: Any) -> None:
    """Write the counter of every transition, in order, and give the cover and the transitions their sizes and places.
    The cover is the first slide when it is a cover layout and no transition. The paragraphs without text of the
    tables keep the size of their text (size_empty_table_paragraphs). The slides of a dark theme turn their content dark
    (theme_dark). The shapes the modules draw lose the shadow of the theme (drop_theme_shadows) and the SVG pictures get
    a PNG (add_svg_fallbacks) and the charts leave their groups (ungroup_charts), so the iPhone and Mac previews draw the
    slides as PowerPoint does."""
    from src.modules.reporting.pptx_compose import is_cover

    width = presentation.slide_width
    counter = Counter()
    for index, slide in enumerate(presentation.slides):
        current = level(slide)
        if current is None:
            if index == 0 and is_cover(slide):
                _place(slide, 'cover', width)
            continue
        _write_counter(slide, counter.next(current))
        _place(slide, 'transition', width)
    size_empty_table_paragraphs(presentation)
    # The content of the slides of a dark theme (Midnight) on their dark background.
    from src.modules.reporting.theme_dark import darken_presentation
    darken_presentation(presentation)
    drop_theme_shadows(presentation)
    add_svg_fallbacks(presentation)
    ungroup_charts(presentation)
