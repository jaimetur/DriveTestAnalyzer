"""The content of the slides of a dark theme (Midnight) on their dark background.

The builders of the themed modules draw their tables, cards, panels and charts for white slides: white and light grey
fills, pastel cells, dark text and rules. A slide that theme_titles.paint_slide gave a dark background (the ``slide``
colour of a dark theme) turns them dark when its deck is finished (report_structure.finish): white and light neutral
fills take the cards and alternate rows of the theme, pastel fills a dark shade of their own hue, dark text the light
ink of the theme (or a light shade of its own hue) and light rules the theme's border. Saturated colours (operators,
vendors, score bands, headers) and white text stay as they are, and dark text on a fill that stays light is kept. The
native charts of a slide get the same treatment. Doing it twice leaves the slide as it is.
"""
from __future__ import annotations

import colorsys
from typing import Any

from pptx.dml.color import RGBColor

from src.modules.scoring_themes import THEMES

A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
C_NS = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
TEXT_PARTS = {'rPr', 'defRPr', 'endParaRPr'}
LINE_PARTS = {'ln', 'lnL', 'lnR', 'lnT', 'lnB', 'lnTlToBr', 'lnBlToTr'}
SKIPPED_PARTS = {'effectLst', 'blipFill'}


def _channels(colour: str) -> tuple[float, float, float]:
    text = colour.lstrip('#')
    return tuple(int(text[index:index + 2], 16) / 255 for index in (0, 2, 4))


def _hex(channels: tuple[float, float, float]) -> str:
    return ''.join(f'{round(max(0.0, min(1.0, value)) * 255):02X}' for value in channels)


def _luminance(colour: str) -> float:
    red, green, blue = _channels(colour)
    return .299 * red + .587 * green + .114 * blue


def _describe(colour: str) -> tuple[float, float, float, bool]:
    """Hue, lightness and saturation of a colour, and whether it is a neutral (a white, grey or black)."""
    red, green, blue = _channels(colour)
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    return hue, lightness, saturation, max(red, green, blue) - min(red, green, blue) < .1


def _shade(hue: float, lightness: float, saturation: float) -> str:
    return _hex(colorsys.hls_to_rgb(hue, lightness, saturation))


def dark_theme_of(slide: Any) -> dict[str, Any] | None:
    """The dark theme whose slide colour is the background of ``slide``, if any."""
    background = slide._element.find(f'.//{{http://schemas.openxmlformats.org/presentationml/2006/main}}bg')
    if background is None:
        return None
    colour = background.find(f'.//{{{A_NS}}}srgbClr')
    if colour is None:
        return None
    value = f"#{str(colour.get('val') or '').upper()}"
    return next((theme for theme in THEMES.values() if str(theme.get('slide') or '').upper() == value and value != '#FFFFFF'),
                None)


class _Palette:
    def __init__(self, theme: dict[str, Any]):
        self.slide = theme['slide'].lstrip('#').upper()
        self.surface = theme['surface'].lstrip('#').upper()
        self.row_alt = theme['row_alt'].lstrip('#').upper()
        self.border = theme['border'].lstrip('#').upper()
        self.ink = theme['ink'].lstrip('#').upper()
        self.rule = theme['muted'].lstrip('#').upper()

    def fill(self, colour: str) -> str:
        hue, lightness, saturation, neutral = _describe(colour)
        if neutral and lightness >= .95:
            return self.surface
        if neutral and lightness >= .8:
            return self.row_alt
        if lightness >= .78:
            # A pastel (a score band, a tinted panel): a dark shade of its own hue.
            return _shade(hue, .19, min(.55, saturation))
        if neutral and lightness >= .55:
            # A light grey track or bar behind a value.
            return self.border
        return colour

    def text(self, colour: str) -> str:
        hue, lightness, saturation, neutral = _describe(colour)
        if neutral and lightness <= .55:
            return self.ink
        if lightness <= .45:
            return _shade(hue, .75, saturation)
        return colour

    def line(self, colour: str) -> str:
        hue, lightness, saturation, neutral = _describe(colour)
        if colour.upper() == 'FFFFFF':
            # The white gaps between the cells: gaps of the slide.
            return self.slide
        if neutral and lightness >= .6:
            return self.border
        if neutral and lightness <= .3:
            return self.rule
        if lightness >= .78:
            return _shade(hue, .3, min(.55, saturation))
        return colour


def _kind(element: Any, root: Any) -> str | None:
    """Whether a colour is the colour of a text, a line or a fill, by the parts it sits in (None: leave it)."""
    node = element.getparent()
    while node is not None and node is not root:
        name = node.tag.rsplit('}', 1)[-1]
        if name in SKIPPED_PARTS:
            return None
        if name in TEXT_PARTS:
            return 'text'
        if name in LINE_PARTS:
            return 'line'
        node = node.getparent()
    return 'fill'


def _container_fill(run: Any, root: Any) -> str | None:
    """The fill of the cell or shape a run of text sits in."""
    node = run.getparent()
    while node is not None and node is not root:
        name = node.tag.rsplit('}', 1)[-1]
        if name in {'tc', 'sp'}:
            properties = node.find(f'{{{A_NS}}}tcPr') if name == 'tc' else node.find(
                '{http://schemas.openxmlformats.org/presentationml/2006/main}spPr')
            fill = properties.find(f'{{{A_NS}}}solidFill/{{{A_NS}}}srgbClr') if properties is not None else None
            return str(fill.get('val')) if fill is not None else None
        node = node.getparent()
    return None


def _darken_tree(root: Any, palette: _Palette) -> None:
    colours = list(root.iter(f'{{{A_NS}}}srgbClr'))
    # Fills and lines first, so a text knows the final fill under it.
    for element in colours:
        kind = _kind(element, root)
        value = str(element.get('val') or '').upper()
        if kind in {'fill', 'line'} and len(value) == 6:
            element.set('val', palette.fill(value) if kind == 'fill' else palette.line(value))
    for element in colours:
        if _kind(element, root) != 'text':
            continue
        value = str(element.get('val') or '').upper()
        if len(value) != 6:
            continue
        container = _container_fill(element, root)
        if container is not None and _luminance(container) > .6:
            continue
        element.set('val', palette.text(value))
    # A text without a colour of its own takes the ink, unless it sits on a light fill.
    for run in root.iter(f'{{{A_NS}}}r'):
        properties = run.find(f'{{{A_NS}}}rPr')
        if properties is not None and any(properties.find(f'{{{A_NS}}}{name}') is not None
                                          for name in ('solidFill', 'gradFill', 'noFill', 'pattFill')):
            continue
        container = _container_fill(run, root)
        if container is not None and _luminance(container) > .6:
            continue
        if properties is None:
            properties = run.makeelement(f'{{{A_NS}}}rPr', {})
            run.insert(0, properties)
        fill = properties.makeelement(f'{{{A_NS}}}solidFill', {})
        fill.append(fill.makeelement(f'{{{A_NS}}}srgbClr', {'val': palette.ink}))
        # The fill comes first among the properties of a run (before its fonts).
        properties.insert(0, fill)


def _charts(shapes: Any) -> Any:
    """The native charts among ``shapes``, those in groups too."""
    for shape in shapes:
        if getattr(shape, 'shape_type', None) == 6:
            yield from _charts(shape.shapes)
        elif getattr(shape, 'has_chart', False) and shape.has_chart:
            yield shape.chart


def darken_slide(slide: Any, theme: dict[str, Any]) -> None:
    """Turn the content of a dark slide dark (see the module docstring)."""
    palette = _Palette(theme)
    _darken_tree(slide.shapes._spTree, palette)
    for chart in _charts(slide.shapes):
        _darken_tree(chart._chartSpace, palette)
        chart.font.color.rgb = RGBColor.from_string(palette.ink)


def darken_presentation(presentation: Any) -> int:
    """Turn dark the content of every slide with the dark background of a theme; returns how many."""
    count = 0
    for slide in presentation.slides:
        theme = dark_theme_of(slide)
        if theme is not None:
            darken_slide(slide, theme)
            count += 1
    return count
