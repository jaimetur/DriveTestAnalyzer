"""Slide titles that fit their placeholder on one line.

A title measured with the metrics of a real font (Arial, as wide as the fonts LibreOffice uses for the template's
Ericsson Hilda when it is not installed, so the Word versions of the reports wrap no title either) is made smaller
when it would not fit on one line, so a second line never covers the subtitle or the content under it.
"""
from functools import lru_cache
from math import floor
from typing import Any

from pptx.util import Pt

from src.utils.fonts import load_image_font

TITLE_FONT_PT = 40
TITLE_MIN_FONT_PT = 18
_MEASURE_SIZE = 100
_DEFAULT_INSET_EMU = 91440


@lru_cache(maxsize=4)
def _font(bold: bool) -> Any:
    return load_image_font(_MEASURE_SIZE, bold=bold)


def text_width_pt(text: str, size_pt: float, bold: bool = False) -> float:
    """The width of ``text`` in points at ``size_pt``."""
    font = _font(bool(bold))
    try:
        width = font.getlength(text)
    except AttributeError:  # Pillow without getlength.
        width = font.getsize(text)[0]
    return width * size_pt / _MEASURE_SIZE


def fit_paragraph_on_one_line(shape: Any, paragraph: Any, default_size: float = TITLE_FONT_PT,
                              minimum: float = TITLE_MIN_FONT_PT, margin: float = 0.96) -> float | None:
    """Make the runs of ``paragraph`` smaller when the paragraph is wider than ``shape`` (less its insets); returns
    the size they get, or None when they already fit. Runs without a size of their own count at ``default_size``."""
    runs = [run for run in paragraph.runs if run.text]
    if not runs or shape.width is None:
        return None
    frame = shape.text_frame
    insets = ((frame.margin_left if frame.margin_left is not None else _DEFAULT_INSET_EMU)
              + (frame.margin_right if frame.margin_right is not None else _DEFAULT_INSET_EMU))
    available = (int(shape.width) - int(insets)) / 12700 * margin
    fallback = paragraph.font.size.pt if paragraph.font.size is not None else default_size
    sizes = [run.font.size.pt if run.font.size is not None else fallback for run in runs]
    # A run in capitals (cap="all", such as the NetCheck titles) is measured in capitals.
    texts = [run.text.upper() if run.font._rPr.get('cap') == 'all' else run.text for run in runs]
    width = sum(text_width_pt(text, size, bool(run.font.bold)) for text, run, size in zip(texts, runs, sizes))
    if width <= available:
        return None
    factor = available / width
    fitted = None
    for run, size in zip(runs, sizes):
        fitted = max(minimum, floor(size * factor * 2) / 2)
        run.font.size = Pt(fitted)
    return fitted


def fit_slide_title(slide: Any, default_size: float = TITLE_FONT_PT) -> float | None:
    """Fit the title of ``slide`` (the first paragraph of its title placeholder) on one line."""
    shape = next((item for item in slide.placeholders if item.placeholder_format.type in {1, 3} and item.has_text_frame), None)
    if shape is None or not shape.text_frame.paragraphs:
        return None
    return fit_paragraph_on_one_line(shape, shape.text_frame.paragraphs[0], default_size)
