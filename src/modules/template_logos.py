"""The logos of the report template on light slides.

The dark layouts of the template (covers, transitions and Title Only) draw the operators' logo and the Ericsson logo
in white themselves, so it stands out on their background. A slide that paints a light background over one of them
(such as the Scoring & GAP Analysis slides, built on Title Only) shows the dark logos of the slide master instead.
"""
import copy
from typing import Any

R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P_NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'
# The shapes the dark layouts draw instead of the logos of the slide master.
WHITE_LOGO_SHAPES = frozenset({'Logo (white)', 'Operators logo'})
# The Ericsson mark drawn in outline on the red of the covers and transitions, not on a light slide.
WATERMARK_PREFIX = 'Ericsson watermark'


def _copy_to_slide(shape: Any, owner: Any, slide: Any, position: int) -> None:
    element = copy.deepcopy(shape._element)
    for node in element.iter():
        for attribute, value in list(node.attrib.items()):
            if attribute.startswith(f'{{{R_NS}}}') and value in owner.rels:
                relationship = owner.rels[value]
                node.set(attribute, slide.part.relate_to(relationship.target_part, relationship.reltype))
    shape_id = slide.shapes._next_shape_id
    for properties in element.iter(f'{{{P_NS}}}cNvPr'):
        properties.set('id', str(shape_id))
        shape_id += 1
    slide.shapes._spTree.insert(position, element)


def use_dark_logos(slide: Any) -> bool:
    """Show the master's dark logos on ``slide`` (with a light background) when its layout draws the white ones;
    returns whether the slide changed. The other shapes of the layout, such as its footer, stay (not the Ericsson mark
    of the red background)."""
    layout = slide.slide_layout
    if slide._element.get('showMasterSp') == '0' or not any(shape.name in WHITE_LOGO_SHAPES for shape in layout.shapes):
        return False
    slide._element.set('showMasterSp', '0')
    # Behind the content of the slide, as the layout and master draw them.
    position = 2
    for owner, shapes in ((layout.slide_master.part, layout.slide_master.shapes), (layout.part, layout.shapes)):
        for shape in shapes:
            if shape.is_placeholder or shape.name in WHITE_LOGO_SHAPES or str(shape.name).startswith(WATERMARK_PREFIX):
                continue
            _copy_to_slide(shape, owner, slide, position)
            position += 1
    return True
