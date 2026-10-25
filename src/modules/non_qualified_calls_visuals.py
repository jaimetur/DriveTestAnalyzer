"""Non-Qualified Calls report panels drawn like the page: KPI cards, breakdown bars, donuts, timeline and workload.

Each panel is a PNG that fills the content area of a slide (and a landscape Word page), so PowerPoint and Word
show the Executive Summary and the Progress View with the look of the web page.
"""

from __future__ import annotations

import colorsys
import math
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from PIL import Image, ImageColor, ImageDraw

from src.utils.fonts import load_image_font

DPI = 200
PANEL_WIDTH = 12.28
PANEL_HEIGHT = 4.75
DARK = '#7d1238'
TEXT = '#3d1824'
MUTED = '#8a6b76'
BORDER = '#f0c4d3'
TRACK = '#f3dfe6'
RASPBERRY = '#b0234f'
PALETTE = ['#b0234f', '#0f6f7d', '#e08a1e', '#6a63c9', '#2e8b57', '#245a96', '#b85b20', '#7b8790', '#5b6b2e', '#c8365f']
KPI_COLORS = {'total': '#b0234f', 'open': '#d14a68', 'closed': '#2e8b57', 'attended': '#e08a1e', 'team': '#0f6f7d',
              'commented': '#6a63c9'}
SERVICE_LABELS = {'voice': 'Voice', 'speech': 'Speech', 'data': 'Data'}
# A phase field with more values goes on a panel of its own, its values in columns.
WIDE_PHASE_VALUES = 12


def series_colours(count: int) -> list[str]:
    """The palette in order, then hues spread by the golden angle, so that no two values of a long list share a colour."""
    colours = PALETTE[:count]
    for index in range(len(PALETTE), count):
        red, green, blue = colorsys.hls_to_rgb((index * 0.381966) % 1, 0.36 if index % 2 else 0.47, 0.5)
        colours.append(f'#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}')
    return colours


def _px(inches: float) -> int:
    return round(inches * DPI)


def _font(points: float, bold: bool = False):
    return load_image_font(max(1, round(points * DPI / 72)), bold=bold)


def _number(value: Any) -> str:
    return f'{int(value or 0):,}'


def _share(count: int, total: int) -> str:
    return f'{count * 100 / total:.0f}%' if total else '0%'


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: float) -> str:
    """Shorten a label with an ellipsis so it never runs into the next element."""
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + '…', font=font) > width:
        text = text[:-1]
    return text.rstrip() + '…'


class Panel:
    """A white canvas in inches; cards are placed with inch coordinates."""

    def __init__(self, width: float = PANEL_WIDTH, height: float = PANEL_HEIGHT) -> None:
        self.width, self.height = width, height
        self.image = Image.new('RGB', (_px(width), _px(height)), 'white')
        self.draw = ImageDraw.Draw(self.image)

    def card(self, left: float, top: float, width: float, height: float, accent: str | None = None) -> None:
        box = [_px(left), _px(top), _px(left + width), _px(top + height)]
        self.draw.rounded_rectangle(box, radius=_px(0.12), fill='white', outline=BORDER, width=max(2, _px(0.012)))
        if accent:
            self.draw.rounded_rectangle([box[0], box[1], box[2], box[1] + _px(0.07)], radius=_px(0.035), fill=accent)

    def text(self, left: float, top: float, value: str, points: float, *, bold: bool = False, color: str = TEXT,
             width: float | None = None, anchor: str = 'la') -> None:
        font = _font(points, bold)
        if width is not None:
            value = _fit(self.draw, value, font, _px(width))
        self.draw.text((_px(left), _px(top)), value, font=font, fill=color, anchor=anchor)

    def png(self) -> BytesIO:
        output = BytesIO()
        self.image.save(output, 'PNG', dpi=(DPI, DPI))
        output.seek(0)
        return output


def _kpi_row(panel: Panel, cards: list[tuple[str, str, str, str]], top: float, height: float, *, compact: bool = False) -> None:
    gap = 0.15 if compact else 0.18
    width = (panel.width - gap * (len(cards) - 1)) / len(cards)
    for index, (label, value, note, kind) in enumerate(cards):
        left = index * (width + gap)
        # A card names its colour or is coloured as its kind.
        panel.card(left, top, width, height, kind if kind.startswith('#') else KPI_COLORS.get(kind, RASPBERRY))
        if compact:
            panel.text(left + 0.14, top + 0.15, label.upper(), 7.5, bold=True, color=MUTED, width=width - 0.26)
            panel.text(left + 0.14, top + 0.3, value, 16, bold=True, color=DARK, width=width - 0.26)
            panel.text(left + 0.14, top + height - 0.22, note, 7.5, color=MUTED, width=width - 0.26)
            continue
        panel.text(left + 0.16, top + 0.2, label.upper(), 8.5, bold=True, color=MUTED, width=width - 0.3)
        panel.text(left + 0.16, top + 0.42, value, 22, bold=True, color=DARK, width=width - 0.3)
        panel.text(left + 0.16, top + height - 0.3, note, 8.5, color=MUTED, width=width - 0.3)


def _bar_card(panel: Panel, left: float, top: float, width: float, height: float, title: str,
              items: list[tuple[str, int, str]], *, label_above: bool = False, compact: bool = False) -> None:
    """A breakdown card: a bar per value, longest first, as in the Executive Summary of the page.

    ``compact`` cards (the one-slide Executive Summary) use smaller text and rows.
    """
    panel.card(left, top, width, height)
    title_size, label_size, pad = (9.5, 7.5, 0.12) if compact else (12, 9, 0.18)
    panel.text(left + pad, top + (0.12 if compact else 0.16), title, title_size, bold=True, color=DARK, width=width - 2 * pad)
    row = (0.34 if label_above else 0.235) if compact else (0.42 if label_above else 0.3)
    first = 0.46 if compact else 0.58
    rows = max(1, int((height - first + row / 2) / row))
    shown = items[:rows]
    if not shown:
        panel.text(left + pad, top + first, 'No calls.', label_size, color=MUTED)
        return
    maximum = max(1, *(count for _label, count, _color in shown))
    label_width = 0 if label_above else min(1.6, width * (0.42 if compact else 0.38))
    count_width = 0.42 if compact else 0.6
    gap = 0.06 if compact else 0.1
    thickness = 0.045 if compact else 0.06
    for index, (label, count, color) in enumerate(shown):
        y = top + first + index * row
        track_left = left + pad + label_width + (0 if label_above else gap)
        track_width = width - 2 * pad - label_width - (0 if label_above else gap) - count_width
        if label_above:
            panel.text(left + pad, y - 0.08, label, label_size - 0.5, bold=True, color=TEXT, width=width - 2 * pad)
            y += 0.14 if compact else 0.16
        else:
            panel.text(left + pad, y, label, label_size, bold=True, color=TEXT, width=label_width, anchor='lm')
        bar_top, bar_bottom = _px(y - thickness), _px(y + thickness)
        panel.draw.rounded_rectangle([_px(track_left), bar_top, _px(track_left + track_width), bar_bottom], radius=_px(thickness), fill=TRACK)
        fill = max(0.05, track_width * count / maximum)
        panel.draw.rounded_rectangle([_px(track_left), bar_top, _px(track_left + fill), bar_bottom], radius=_px(thickness), fill=color or RASPBERRY)
        panel.text(left + width - pad, y, _number(count), label_size, bold=True, color=DARK, anchor='rm')


def _donut_card(panel: Panel, left: float, top: float, width: float, height: float, title: str,
                items: list[tuple[str, int, str]]) -> None:
    """A donut with the total in its centre and a legend with each value's count and share."""
    panel.card(left, top, width, height)
    panel.text(left + 0.16, top + 0.14, title, 11, bold=True, color=DARK, width=width - 0.3)
    total = sum(count for _label, count, _color in items)
    # The donut sits under the title and its legend below it, using the whole width of the card.
    size = min(width - 0.6, (height - 0.55) * 0.5)
    cx, cy = left + width / 2, top + 0.5 + size / 2
    box = [_px(cx - size / 2), _px(cy - size / 2), _px(cx + size / 2), _px(cy + size / 2)]
    thickness = _px(size * 0.17)
    panel.draw.ellipse(box, outline=TRACK, width=thickness)
    start = -90.0
    for _label, count, color in items:
        if not total or not count:
            continue
        sweep = count / total * 360
        panel.draw.arc(box, start, start + sweep + 0.4, fill=color, width=thickness)
        start += sweep
    panel.text(cx, cy, _number(total), 13, bold=True, color=DARK, anchor='mm')
    legend_top = top + 0.62 + size
    row = 0.24
    shown = items[:max(1, int((top + height - 0.1 - legend_top) / row))]
    for index, (label, count, color) in enumerate(shown):
        y = legend_top + index * row
        panel.draw.rounded_rectangle([_px(left + 0.16), _px(y - 0.06), _px(left + 0.28), _px(y + 0.06)], radius=_px(0.03), fill=color)
        value = f'{_number(count)} · {_share(count, total)}'
        value_width = panel.draw.textlength(value, font=_font(8)) / DPI
        panel.text(left + 0.36, y, label, 8.5, bold=True, color=TEXT, width=width - 0.62 - value_width, anchor='lm')
        panel.text(left + width - 0.16, y, value, 8, color=MUTED, anchor='rm')

def campaign_label(value: str) -> str:
    """A campaign as every chart and table shows it (UK_Q2_SA_2026 reads 2026-Q2-SA)."""
    from src.modules.column_names import compact_campaign_value

    return compact_campaign_value(value) or value


def _items(distribution: dict[str, Any], colours: dict[tuple[str, str], str]) -> list[tuple[str, int, str]]:
    field = distribution.get('field') or ''
    empty = 'Unassigned' if field in {'team', 'assignee'} else 'Not classified'
    items = []
    for index, item in enumerate(distribution.get('items') or []):
        value = str(item.get('value') or '')
        shown = SERVICE_LABELS.get(value, value) if field == 'service' else campaign_label(value) if field == 'campaign' else value
        label = item.get('label') or shown or empty
        colour = item.get('color') or colours.get((field, value)) or PALETTE[index % len(PALETTE)]
        items.append((str(label), int(item.get('count') or 0), colour))
    return items


def _option_colours(options: dict[str, Any]) -> dict[tuple[str, str], str]:
    colours = {('status', item['name']): item['color'] for item in options.get('statuses') or [] if item.get('color')}
    colours.update({('team', item['name']): item['color'] for item in options.get('teams') or [] if item.get('color')})
    # The root domains in their colours, from the Root Cause Analysis of the report.
    domains = [item for stats in options.get('root_causes') or [] for item in stats.get('domains') or []]
    colours.update({('root_domain', item['value']): item['color'] for item in domains if item.get('color')})
    return colours


def executive_summary_panels(summary: dict[str, Any], breakdowns: list[dict[str, Any]], options: dict[str, Any]) -> list[tuple[str, BytesIO]]:
    """The Executive Summary on one slide: the indicator cards above and every breakdown in a grid of two rows."""
    total = int(summary.get('total') or 0)
    colours = _option_colours(options)
    cards = [
        ('Non-Qualified Calls', _number(total), 'Calls and tests that did not complete', 'total'),
        ('Open', _number(summary.get('open')), f"{_share(summary.get('open') or 0, total)} still under follow-up", 'open'),
        ('Closed', _number(summary.get('closed')), f"{_share(summary.get('closed') or 0, total)} resolved or not applicable", 'closed'),
        ('Attended', _number(summary.get('attended')), f"{_share(summary.get('attended') or 0, total)} followed up or commented", 'attended'),
        ('With Team', _number(summary.get('with_team')), f"{_share(summary.get('with_team') or 0, total)} have a responsible team", 'team'),
        ('Commented', _number(summary.get('commented')), f"{_share(summary.get('commented') or 0, total)} have comments", 'commented'),
    ]
    panel = Panel()
    kpi_height = 0.82
    _kpi_row(panel, cards, 0, kpi_height, compact=True)
    shown = breakdowns[:12]
    if shown:
        gap = 0.15
        rows = 1 if len(shown) <= 4 else 2
        columns = -(-len(shown) // rows)
        top = kpi_height + gap
        width = (panel.width - gap * (columns - 1)) / columns
        height = (panel.height - top - gap * (rows - 1)) / rows
        for index, breakdown in enumerate(shown):
            row, column = divmod(index, columns)
            _bar_card(panel, column * (width + gap), top + row * (height + gap), width, height, breakdown['label'],
                      _items(breakdown, colours), compact=True)
    return [('Executive Summary', panel.png())]


def _bar_row(panel: Panel, breakdowns: list[dict[str, Any]], colours: dict[tuple[str, str], str], top: float, height: float) -> None:
    if not breakdowns:
        return
    gap = 0.18
    width = (panel.width - gap * 2) / 3
    for index, breakdown in enumerate(breakdowns):
        _bar_card(panel, index * (width + gap), top, width, height, breakdown['label'], _items(breakdown, colours))


def _days(value: Any) -> str:
    return '—' if value is None else f'{float(value):.1f} d'


def progress_title(granularity_label: str, subtitle: str) -> SlideTitle:
    """The title of a Progress View slide: the period of its timeline in bold, and what the slide shows in its subtitle."""
    period = {'Week': 'Weekly', 'Month': 'Monthly', 'Quarter': 'Quarterly', 'Year': 'Yearly'}.get(granularity_label, granularity_label)
    return SlideTitle('Progress View', period, subtitle)


def progress_view_panels(progress: dict[str, Any], options: dict[str, Any], granularity_label: str) -> list[tuple[SlideTitle, BytesIO]]:
    """The Progress View: indicator cards and donuts, the timeline, then age and workload."""
    summary = progress.get('summary') or {}
    total = int(summary.get('total') or 0)
    colours = _option_colours(options)
    cards = [
        ('Attended', _number(summary.get('attended')), f"{_share(summary.get('attended') or 0, total)} have a follow-up", 'open'),
        ('Not Attended', _number(summary.get('not_attended')), 'No change or comment yet', 'total'),
        ('Closure Rate', f"{float(summary.get('closure_rate') or 0):.1f}%", f"{_number(summary.get('closed'))} of {_number(total)} closed", 'closed'),
        ('First Follow-up', _days(summary.get('avg_days_to_first_follow_up')), 'Average from the call', 'team'),
        ('Time to Close', _days(summary.get('avg_days_to_close')), 'Average from the call', 'commented'),
        ('Activity', _number((summary.get('comments') or 0) + (summary.get('changes') or 0)),
         f"{_number(summary.get('comments'))} comments · {_number(summary.get('changes'))} changes", ''),
    ]
    panels = []
    first = Panel()
    _kpi_row(first, cards, 0, 1.25)
    distributions = progress.get('distributions') or []
    gap = 0.18
    width = (first.width - gap * (len(distributions) - 1)) / max(1, len(distributions))
    for index, distribution in enumerate(distributions):
        _donut_card(first, index * (width + gap), 1.45, width, first.height - 1.45, distribution['label'], _items(distribution, colours))
    panels.append((progress_title(granularity_label, 'Follow-up Overview'), first.png()))
    timeline = _timeline_panel(progress.get('periods') or [], granularity_label)
    if timeline is not None:
        panels.append((progress_title(granularity_label, f'Progress per {granularity_label}'), timeline))
    work = Panel()
    third = (work.width - gap * 2) / 3
    _bar_card(work, 0, 0, third, work.height, 'Age of Open Calls',
              [(str(item['value']), int(item['count']), RASPBERRY) for item in progress.get('aging') or []])
    _workload_card(work, third + gap, 0, third, work.height, 'Team Workload', progress.get('teams') or [])
    _workload_card(work, 2 * (third + gap), 0, third, work.height, 'Assignee Workload', progress.get('assignees') or [])
    panels.append((progress_title(granularity_label, 'Age and Workload'), work.png()))
    return panels


def _workload_card(panel: Panel, left: float, top: float, width: float, height: float, title: str, rows: list[dict[str, Any]]) -> None:
    """Open and closed calls per team or assignee as stacked bars."""
    panel.card(left, top, width, height)
    panel.text(left + 0.18, top + 0.16, title, 12, bold=True, color=DARK)
    legend_x = left + width - 0.18
    for label, colour in (('Closed', '#2e8b57'), ('Open', RASPBERRY)):
        text_width = panel.draw.textlength(label, font=_font(8)) / DPI
        panel.text(legend_x, top + 0.2, label, 8, color=MUTED, anchor='ra')
        legend_x -= text_width + 0.05
        panel.draw.rounded_rectangle([_px(legend_x - 0.12), _px(top + 0.21), _px(legend_x), _px(top + 0.33)], radius=_px(0.03), fill=colour)
        legend_x -= 0.25
    shown = rows[:max(1, int((height - 0.6) / 0.3))]
    if not shown:
        panel.text(left + 0.18, top + 0.6, 'No calls.', 9, color=MUTED)
        return
    maximum = max(1, *(int(row['total']) for row in shown))
    label_width = min(1.4, width * 0.36)
    track_left = left + 0.28 + label_width
    track_width = width - 0.46 - label_width - 0.75
    for index, row in enumerate(shown):
        y = top + 0.62 + index * 0.3
        panel.text(left + 0.18, y, str(row['name']), 9, bold=True, color=TEXT, width=label_width, anchor='lm')
        open_width = track_width * int(row['open']) / maximum
        closed_width = track_width * int(row['closed']) / maximum
        bar_top, bar_bottom = _px(y - 0.06), _px(y + 0.06)
        panel.draw.rounded_rectangle([_px(track_left), bar_top, _px(track_left + track_width), bar_bottom], radius=_px(0.06), fill=TRACK)
        if open_width:
            panel.draw.rounded_rectangle([_px(track_left), bar_top, _px(track_left + max(open_width, 0.05)), bar_bottom], radius=_px(0.06), fill=RASPBERRY)
        if closed_width:
            start = track_left + open_width
            panel.draw.rounded_rectangle([_px(start), bar_top, _px(start + max(closed_width, 0.05)), bar_bottom], radius=_px(0.06), fill='#2e8b57')
        panel.text(left + width - 0.18, y, f"{_number(row['open'])} / {_number(row['closed'])}", 8.5, bold=True, color=DARK, anchor='rm')


def _timeline_panel(periods: list[dict[str, Any]], granularity_label: str) -> BytesIO | None:
    """Detected, attended and closed calls per period as bars, with the open backlog as a line, like the page."""
    shown = periods[-24:]
    if not shown:
        return None
    panel = Panel()
    panel.card(0, 0, panel.width, panel.height)
    panel.text(0.2, 0.16, f'Progress per {granularity_label}', 12, bold=True, color=DARK)
    series = [('detected', 'Detected', '#8a6b76'), ('attended', 'Attended', '#e08a1e'), ('closed', 'Closed', '#2e8b57')]
    legend_x = 3.2
    for _key, label, colour in [*series, ('open_backlog', 'Open backlog', '#b0234f')]:
        panel.draw.rounded_rectangle([_px(legend_x), _px(0.22), _px(legend_x + 0.14), _px(0.36)], radius=_px(0.03), fill=colour)
        panel.text(legend_x + 0.2, 0.2, label, 9, color=TEXT)
        legend_x += 0.4 + panel.draw.textlength(label, font=_font(9)) / DPI
    left, right, top, bottom = 0.75, panel.width - 0.25, 0.65, panel.height - 0.5
    maximum = max(1, *(max(int(period.get(key) or 0) for key, _label, _colour in series) for period in shown),
                  *(int(period.get('open_backlog') or 0) for period in shown))
    step = 10 ** max(0, int(math.log10(maximum)) - 1)
    maximum = math.ceil(maximum / step / 4) * step * 4 if maximum > 4 else 4
    for share in (0, 0.25, 0.5, 0.75, 1):
        y = bottom - (bottom - top) * share
        panel.draw.line([_px(left), _px(y), _px(right), _px(y)], fill='#efe3e8', width=2)
        panel.text(left - 0.08, y, _number(round(maximum * share)), 8, color=MUTED, anchor='rm')
    slot = (right - left) / len(shown)
    bar = min(0.22, (slot - 0.1) / len(series))
    points = []
    for index, period in enumerate(shown):
        start = left + index * slot + (slot - bar * len(series)) / 2
        for position, (key, _label, colour) in enumerate(series):
            value = int(period.get(key) or 0)
            height = (bottom - top) * value / maximum
            if height > 0:
                x = start + position * bar
                panel.draw.rounded_rectangle([_px(x), _px(bottom - height), _px(x + bar - 0.03), _px(bottom)], radius=_px(0.02), fill=colour)
        centre = left + index * slot + slot / 2
        points.append((_px(centre), _px(bottom - (bottom - top) * int(period.get('open_backlog') or 0) / maximum)))
        panel.text(centre, bottom + 0.1, str(period.get('period') or ''), 8, color=MUTED, anchor='ma', width=max(0.5, slot))
    if len(points) > 1:
        panel.draw.line(points, fill='#b0234f', width=_px(0.03), joint='curve')
    for x, y in points:
        radius = _px(0.04)
        panel.draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill='#b0234f', outline='white', width=2)
    return panel.png()


TABLE_MIN_ROW = 0.22
# The heading above a table and the space below its last row, in its card.
TABLE_HEAD = 0.6
TABLE_FOOT = 0.15


def _table_card(panel: Panel, top: float, height: float, heading: str, columns: list[str], rows: list[list[str]],
                total: int, row_height: float, head: float = TABLE_HEAD, *, left: float = 0.0, width: float | None = None,
                numeric: set[int] | None = None) -> None:
    """One detail table in its card (the width of the panel unless given): raspberry header, alternate rows and muted zeros;
    the ``numeric`` columns (every one but the first unless given) are aligned to the right."""
    numeric = set(range(1, len(columns))) if numeric is None else numeric
    width = panel.width - left if width is None else width
    panel.card(left, top, width, height)
    panel.text(left + 0.2, top + 0.14, heading, 12, bold=True, color=DARK)
    if len(rows) < total:
        panel.text(left + width - 0.2, top + 0.16, f'First {len(rows)} of {total}', 9.5, bold=True, color=MUTED, anchor='ra')
    left, right, top = left + 0.2, left + width - 0.2, top + head
    size = min(8.5, row_height * 72 * 0.5)
    header_font, body_font = _font(size, True), _font(size)
    widths = []
    for index, column in enumerate(columns):
        longest = max([panel.draw.textlength(column, font=header_font),
                       *(panel.draw.textlength(str(row[index]), font=body_font) for row in rows)]) / DPI
        widths.append(longest + 0.24)
    scale = (right - left) / max(sum(widths), 0.1)
    widths = [width * scale for width in widths]
    panel.draw.rounded_rectangle([_px(left), _px(top), _px(right), _px(top + row_height)], radius=_px(0.06), fill='#fcedf2')
    x = left
    for index, column in enumerate(columns):
        right_aligned = index in numeric
        panel.text(x + widths[index] - 0.12 if right_aligned else x + 0.12, top + row_height / 2, column, size,
                   bold=True, color=DARK, width=widths[index] - 0.18, anchor='rm' if right_aligned else 'lm')
        x += widths[index]
    if not rows:
        panel.text(left + 0.12, top + row_height * 1.6, 'No data for this selection.', 9, color=MUTED, anchor='lm')
    for row_index, row in enumerate(rows):
        y = top + row_height * (row_index + 1)
        if row_index % 2:
            panel.draw.rectangle([_px(left), _px(y), _px(right), _px(y + row_height)], fill='#fff7fa')
        panel.draw.line([_px(left), _px(y + row_height), _px(right), _px(y + row_height)], fill='#f6e3ea', width=2)
        x = left
        for index, value in enumerate(row):
            text = str(value)
            muted = text in {'0', '—', ''}
            right_aligned = index in numeric
            panel.text(x + widths[index] - 0.12 if right_aligned else x + 0.12, y + row_height / 2, text, size,
                       bold=index == 0, color=MUTED if muted else TEXT, width=widths[index] - 0.18,
                       anchor='rm' if right_aligned else 'lm')
            x += widths[index]


def table_panels(title: str, columns: list[str], rows: list[list[str]], rows_per_panel: int = 13,
                 single: bool = False, numeric: set[int] | None = None) -> list[tuple[str, BytesIO]]:
    """A detail table drawn like the page's tables: raspberry header, alternate rows and muted zeros.

    A long table takes several slides; with ``single`` it keeps to one: its rows get closer, and the
    last ones are left out when they still do not fit.
    """
    total = len(rows)
    if single:
        rows = rows[:max(1, int((PANEL_HEIGHT - TABLE_HEAD - TABLE_FOOT) / TABLE_MIN_ROW) - 1)]
    pages = ([rows] if single else [rows[index:index + rows_per_panel] for index in range(0, len(rows), rows_per_panel)]) or [[]]
    panels = []
    for number, page in enumerate(pages, start=1):
        # The card is as tall as its rows, so a short table does not leave an empty slide-sized card.
        panel = Panel(height=min(PANEL_HEIGHT, TABLE_HEAD + 0.3 * (max(1, len(page)) + 1) + 0.2))
        row_height = min(0.3, (panel.height - TABLE_HEAD - TABLE_FOOT) / (len(page) + 1))
        _table_card(panel, 0, panel.height, title.split(' · ', 1)[-1], columns, page, total if single else len(page), row_height,
                    numeric=numeric)
        panels.append((title + (f' · {number}/{len(pages)}' if len(pages) > 1 else ''), panel.png()))
    return panels


def _readable(color: str) -> str:
    """Dark text on a light colour and white on a dark one, as in the bars of the page."""
    red, green, blue = ImageColor.getrgb(color)[:3]
    return DARK if (0.299 * red + 0.587 * green + 0.114 * blue) / 255 > 0.62 else 'white'


def _stack_card(panel: Panel, left: float, top: float, width: float, height: float, title: str,
                rows: list[dict[str, Any]], columns: list[str], colours: dict[str, str]) -> None:
    """A bar per group split in the colours of its root domains, with their legend above and its total at the end.

    Every group is drawn: when they are many, the bars get thinner.
    """
    panel.card(left, top, width, height)
    pad = 0.18
    panel.text(left + pad, top + 0.16, title, 12, bold=True, color=DARK, width=width - 2 * pad)
    first = _domain_legend(panel, left + pad, top + 0.66, width - 2 * pad, columns, colours) + 0.22
    if not rows:
        panel.text(left + pad, first + 0.12, 'No data for this selection.', 9, color=MUTED, anchor='lm')
        return
    row = min(0.42, (top + height - 0.12 - first) / len(rows))
    size = min(9, row * 72 * 0.55)
    label_width = min(1.5, width * 0.24)
    track_left = left + pad + label_width + 0.1
    track_width = width - 2 * pad - label_width - 0.1 - 0.7
    thickness = max(0.04, min(0.24, row * 0.6))
    inner = min(7.5, thickness * 72 * 0.6)
    for index, group in enumerate(rows):
        y = first + row * (index + 0.5)
        panel.text(left + pad, y, group['name'], size, bold=True, color=TEXT, width=label_width, anchor='lm')
        bar = Image.new('RGB', (_px(track_width), max(1, _px(thickness))), TRACK)
        draw = ImageDraw.Draw(bar)
        total = max(1, int(group.get('total') or 0))
        labels, x = [], 0.0
        for column in columns:
            count = int(group['counts'].get(column) or 0)
            if not count:
                continue
            part = track_width * count / total
            colour = colours.get(column, RASPBERRY)
            draw.rectangle([_px(x), 0, _px(x + part), bar.height], fill=colour)
            if x > 0:
                draw.line([_px(x), 0, _px(x), bar.height], fill='white', width=2)
            # As in the page, a part shows its calls when it is wide enough for them.
            if inner >= 5 and panel.draw.textlength(_number(count), font=_font(inner, True)) / DPI + 0.1 <= part:
                labels.append((_number(count), track_left + x + part / 2, _readable(colour)))
            x += part
        mask = Image.new('L', bar.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, bar.width - 1, bar.height - 1], radius=bar.height // 2, fill=255)
        panel.image.paste(bar, (_px(track_left), _px(y - thickness / 2)), mask)
        for value, centre, ink in labels:
            panel.text(centre, y, value, inner, bold=True, color=ink, anchor='mm')
        panel.text(left + width - pad, y, _number(group.get('total')), size, bold=True, color=DARK, anchor='rm')


def _domain_legend(panel: Panel, left: float, top: float, width: float, columns: list[str], colours: dict[str, str]) -> float:
    """The root domains in their colours, on as many lines as they need; the centre of the last line."""
    x, y = left, top
    for column in columns:
        item_width = 0.2 + panel.draw.textlength(column, font=_font(8.5, True)) / DPI
        if x > left and x + item_width > left + width:
            x, y = left, y + 0.24
        panel.draw.rounded_rectangle([_px(x), _px(y - 0.06), _px(x + 0.12), _px(y + 0.06)], radius=_px(0.03),
                                     fill=colours.get(column, RASPBERRY))
        panel.text(x + 0.17, y, column, 8.5, bold=True, color=MUTED, anchor='lm')
        x += item_width + 0.22
    return y


def _value_donut(panel: Panel, cx: float, cy: float, size: float, items: list[tuple[int, str]], total: int) -> None:
    """A donut with the total in its centre and, on each slice long enough for them, its calls."""
    box = [_px(cx - size / 2), _px(cy - size / 2), _px(cx + size / 2), _px(cy + size / 2)]
    band = size * 0.24
    panel.draw.ellipse(box, outline=TRACK, width=_px(band))
    radius = size / 2 - band / 2
    points = min(9, band * 72 * 0.45)
    start = -90.0
    labels = []
    for count, colour in items:
        if not total or not count:
            continue
        sweep = count / total * 360
        panel.draw.arc(box, start, start + sweep + 0.4, fill=colour, width=_px(band))
        if start > -90:
            angle = math.radians(start)
            panel.draw.line([_px(cx + (radius - band / 2) * math.cos(angle)), _px(cy + (radius - band / 2) * math.sin(angle)),
                             _px(cx + (radius + band / 2) * math.cos(angle)), _px(cy + (radius + band / 2) * math.sin(angle))],
                            fill='white', width=3)
        value = _number(count)
        if radius * math.radians(sweep) >= panel.draw.textlength(value, font=_font(points, True)) / DPI + 0.08:
            middle = math.radians(start + sweep / 2)
            labels.append((value, cx + radius * math.cos(middle), cy + radius * math.sin(middle), _readable(colour)))
        start += sweep
    for value, x, y, ink in labels:
        panel.text(x, y, value, points, bold=True, color=ink, anchor='mm')
    panel.text(cx, cy, _number(total), min(15, size * 72 * 0.11), bold=True, color=DARK, anchor='mm')


def domain_donuts_panel(stats: dict[str, Any]) -> BytesIO | None:
    """The Root Domains by Call Type and NSA vs SA: a donut per group under the legend of the domains they share."""
    colours = {item['value']: item.get('color') or RASPBERRY for item in stats.get('domains') or []}
    columns = list(stats.get('columns') or [])
    groups = [(heading, rows) for heading, rows in (('Root Domains by Call Type', stats.get('call_types') or []),
                                                    ('NSA vs SA', stats.get('nr_modes') or [])) if rows]
    if not groups:
        return None
    panel = Panel()
    top = _domain_legend(panel, 0.1, 0.12, panel.width - 0.2, columns, colours) + 0.22
    gap = 0.18
    # The groups share the width by their number of donuts, so every donut gets the same room.
    unit = (panel.width - gap * (len(groups) - 1)) / sum(len(rows) for _heading, rows in groups)
    height = panel.height - top
    left = 0.0
    for heading, rows in groups:
        width = unit * len(rows)
        panel.card(left, top, width, height)
        panel.text(left + 0.18, top + 0.16, heading, 12, bold=True, color=DARK, width=width - 0.36)
        slot = (width - 0.2) / len(rows)
        size = min(slot - 0.3, height - 1.0)
        # Each donut right below its name, both in the middle of the card under its heading.
        cy = top + 0.5 + (height - 0.5 - size - 0.4) / 2 + 0.4 + size / 2
        for index, row in enumerate(rows):
            cx = left + 0.1 + slot * (index + 0.5)
            panel.text(cx, cy - size / 2 - 0.24, f"{row['name']} · {_number(row['total'])} calls", 10, bold=True, color=DARK,
                       width=slot - 0.1, anchor='mm')
            items = [(int(row['counts'].get(name) or 0), colours.get(name, RASPBERRY)) for name in columns]
            _value_donut(panel, cx, cy, size, items, int(row.get('total') or 0))
        left += width + gap
    return panel.png()


def technology_panel(stats: dict[str, Any]) -> BytesIO:
    """The Root Domains by Technology: a bar per technology split by root domain, every one of them (thinner when they are many)."""
    colours = {item['value']: item.get('color') or RASPBERRY for item in stats.get('domains') or []}
    panel = Panel()
    _stack_card(panel, 0, 0, panel.width, panel.height, 'Root Domains by Technology', stats.get('technologies') or [],
                list(stats.get('columns') or []), colours)
    return panel.png()


# The source of the root causes counted, named in the titles unless it is the decision of the analysts.
ROOT_SOURCE_TITLES = {'netcheck': 'NetCheck RCA', 'script': 'Ericsson RCA', 'dta': 'DT Analyzer RCA', 'analysts': 'Analysts'}


@dataclass(frozen=True)
class SlideTitle:
    """A slide title that ends in a part in bold, with a subtitle below it; as text, all of it."""
    text: str
    bold: str = ''
    subtitle: str = ''

    @property
    def heading(self) -> str:
        return ' · '.join(part for part in (self.text, self.bold) if part)

    def __str__(self) -> str:
        return ' · '.join(part for part in (self.heading, self.subtitle) if part)


def _provider(stats: dict[str, Any]) -> tuple[str, str]:
    """The provider of the CDRs and its RCA (NetCheck and the NetCheck RCA unless the statistics name another)."""
    provider = stats.get('provider') or {}
    return str(provider.get('name') or 'NetCheck'), str(provider.get('rca') or ROOT_SOURCE_TITLES['netcheck'])


def source_title(stats: dict[str, Any], default: str = '') -> str:
    """The title of the root cause source of the statistics, the RCA of the CDR named after its provider."""
    source = str(stats.get('source') or '')
    return _provider(stats)[1] if source == 'netcheck' else ROOT_SOURCE_TITLES.get(source, default)


def root_cause_title(stats: dict[str, Any], subtitle: str = '') -> SlideTitle:
    """The title of the Root Cause Analysis of one source (the RCA of the CDR, such as the NetCheck RCA, the Ericsson
    RCA, the DT Analyzer RCA or the analysts), in bold."""
    return SlideTitle('Root Cause Analysis', source_title(stats, 'Analysts'), subtitle)


def root_cause_panels(stats: dict[str, Any]) -> list[tuple[SlideTitle, BytesIO]]:
    """The Root Cause Analysis: the calls per domain, category and cause, and the root domains of each call type and NR mode."""
    summary = stats.get('summary') or {}
    total = int(summary.get('total') or 0)
    title = root_cause_title(stats)
    source = source_title(stats)
    if source and stats.get('source') != 'analysts':
        cards = [
            ('Calls', _number(total), 'Selected Non-Qualified Calls', 'total'),
            ('With a Root Cause', _number(summary.get('labelled')),
             f"{_share(summary.get('labelled') or 0, total)} mapped onto the catalog by the {source}", 'closed'),
            ('Not Classified', _number(summary.get('unclassified')),
             f"{_share(summary.get('unclassified') or 0, total)} without a root cause from the {source}", 'open'),
        ]
    else:
        cards = [
            ('Calls', _number(total), 'Selected Non-Qualified Calls', 'total'),
            ('Labelled', _number(summary.get('labelled')), f"{_share(summary.get('labelled') or 0, total)} have a root cause", 'closed'),
            ('Suggested', _number(summary.get('suggested')),
             'Counted with their suggested root cause' if stats.get('include_suggestions') else 'Not counted', 'team'),
            ('Not Classified', _number(summary.get('unclassified')), f"{_share(summary.get('unclassified') or 0, total)} without a root cause", 'open'),
        ]
    first = Panel()
    _kpi_row(first, cards, 0, 1.25)
    gap = 0.18
    third = (first.width - 2 * gap) / 3
    _bar_card(first, 0, 1.45, third, first.height - 1.45, 'By Root Domain',
              [(item['value'], int(item['count']), item.get('color') or RASPBERRY) for item in stats.get('domains') or []])
    _bar_card(first, third + gap, 1.45, third, first.height - 1.45, 'By Root Category',
              [(f"{item['domain']} · {item['category']}", int(item['count']), item.get('color') or RASPBERRY)
               for item in stats.get('categories') or []])
    _bar_card(first, 2 * (third + gap), 1.45, third, first.height - 1.45, 'By Root Cause',
              [(f"{item['domain']} · {item['cause']}", int(item['count']), item.get('color') or RASPBERRY)
               for item in stats.get('causes') or []])
    panels = [(title, first.png())]
    donuts = domain_donuts_panel(stats)
    if donuts is not None:
        panels.append((root_cause_title(stats, 'Root Domains by Call Type and NSA vs SA'), donuts))
    return panels


def _heat(rate: float | None, highest: float) -> tuple[str, str]:
    """The fill and text colours of an NQ rate, in pastel: soft mint for none, dusty rose for the highest of the matrix."""
    if rate is None:
        return '#f7f2f4', MUTED
    share = 0.0 if highest <= 0 else min(1.0, rate / highest)
    low, high = (0xEE, 0xF6, 0xEF), (0xEB, 0x95, 0xAA)
    mid = (0xFB, 0xE0, 0xBD)
    if share < 0.5:
        start, end, step = low, mid, share * 2
    else:
        start, end, step = mid, high, (share - 0.5) * 2
    rgb = tuple(round(a + (b - a) * step) for a, b in zip(start, end))
    luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
    return '#%02x%02x%02x' % rgb, ('#ffffff' if luminance < 0.55 else TEXT)


RATE_ROW = 0.5
RATE_CELL = 0.8
RATE_LABEL = 1.35
RATE_GROUP_GAP = 0.06
# The line above the table with the overall NQ rate of the selection.
RATE_OVERALL = 0.3
# Below this share of the full row height or cell width, the table takes a second slide.
RATE_DENSE = 0.5


def _fit_size(draw: ImageDraw.ImageDraw, text: str, points: float, bold: bool, width: float) -> float:
    """The largest size up to ``points`` at which a figure fits its cell, as figures must never be cut."""
    length = draw.textlength(text, font=_font(points, bold)) / DPI
    return points if length <= width else max(4.0, points * width / length)


def _rate_shape(campaigns: list[str], groups: int, services: int, width: float, height: float) -> tuple[float, float, float]:
    """The row height and cell width of the NQ rate table, and how close they are to their full size (1 when they are)."""
    header = 1.8 if services > 1 else 1
    row = min(RATE_ROW, (height - 0.4 - RATE_OVERALL) / (len(campaigns) + 1 + header))
    cell = (width - 0.4 - RATE_LABEL - RATE_GROUP_GAP * (groups - 1)) / (groups * services)
    return row, cell, min(row / RATE_ROW, cell / RATE_CELL)


def _gradient_box(panel: Panel, box: tuple[float, float, float, float], start: str, end: str, radius: float) -> None:
    """A rounded box filled with a diagonal gradient from ``start`` (top left) to ``end`` (bottom right)."""
    left, top, right, bottom = (_px(value) for value in box)
    width, height = max(1, right - left), max(1, bottom - top)
    first, last = ImageColor.getrgb(start)[:3], ImageColor.getrgb(end)[:3]
    # Each pixel takes the colour of its share of the diagonal, x + y.
    span = max(1, width + height - 2)
    shade = Image.new('L', (width, height))
    shade.putdata([round(255 * (column + row) / span) for row in range(height) for column in range(width)])
    fill = Image.merge('RGB', [band.point(lambda value, a=a, b=b: round(a + (b - a) * value / 255))
                               for band, a, b in zip((shade, shade, shade), first, last)])
    mask = Image.new('L', (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, height - 1], radius=_px(radius), fill=255)
    panel.image.paste(fill, (left, top), mask)


def _rate_table(matrices: list[dict[str, Any]], campaigns: list[str], operators: list[str], with_total: bool) -> BytesIO:
    """The NQ rate of each campaign under each operator, with one column per service and their total below it."""
    groups = [*operators, *(['Total'] if with_total else [])]
    services = len(matrices)
    row, cell_width, _score = _rate_shape(campaigns, len(groups), services, PANEL_WIDTH, PANEL_HEIGHT)
    double = services > 1
    head_rows = 1.8 if double else 1
    # As tall as its rows, so a short table does not leave an empty slide-sized card.
    panel = Panel(height=min(PANEL_HEIGHT, 0.4 + RATE_OVERALL + row * (len(campaigns) + 1 + head_rows)))
    panel.card(0, 0, panel.width, panel.height)
    # The overall NQ rate of the selection: every service, operator and campaign.
    overall = next((matrix for matrix in matrices if matrix['service'] == 'all'), matrices[0])['total']
    share = f"{overall['rate']:.1f}%" if overall['rate'] is not None else '—'
    panel.text(panel.width - 0.2, 0.2 + RATE_OVERALL / 2,
               f"Overall {share} · {_number(overall['nq'])} NQ calls of {_number(overall['total'])} calls", 10, bold=True,
               color=RASPBERRY, anchor='rm')
    left, top = 0.2, 0.2 + RATE_OVERALL
    head_size = min(9, row * 72 * 0.45)
    rate_size = min(10.5, row * 72 * 0.4)
    calls_size = min(7.5, row * 72 * 0.28)
    highest = {matrix['service']: max([cell['rate'] for line in matrix['cells'].values() for cell in line.values()
                                       if cell['rate'] is not None] or [0]) for matrix in matrices}
    group_width = cell_width * services

    def group_left(index: int) -> float:
        return left + RATE_LABEL + index * (group_width + RATE_GROUP_GAP)

    panel.text(left + 0.12, top + row * head_rows / 2, 'Campaign', head_size, bold=True, color=DARK, anchor='lm')
    colours = next((matrix.get('operator_colors') or {} for matrix in matrices if matrix['service'] == 'all'), {})
    for index, group in enumerate(groups):
        x = group_left(index)
        box = (x + 0.02, top, x + group_width - 0.02, top + row)
        if group == 'Total':
            # The Total of every operator in the fuchsia of the Overall card of the page.
            _gradient_box(panel, box, DARK, '#e0507a', 0.06)
        else:
            panel.draw.rounded_rectangle([_px(value) for value in box], radius=_px(0.06), fill='#fcedf2')
        if colours.get(group):
            panel.draw.rounded_rectangle([_px(x + 0.08), _px(top + row - 0.07), _px(x + group_width - 0.08), _px(top + row - 0.035)],
                                         radius=_px(0.02), fill=colours[group])
        panel.text(x + group_width / 2, top + row / 2, group, head_size, bold=True, color='white' if group == 'Total' else DARK,
                   width=group_width - 0.1, anchor='mm')
        if double:
            for position, matrix in enumerate(matrices):
                # The services as named in the tabs of the page (All services adds them up), smaller when they do not fit.
                label = matrix['label']
                panel.text(x + cell_width * (position + 0.5), top + row * 1.4, label,
                           _fit_size(panel.draw, label, head_size * 0.9, True, cell_width - 0.08), bold=True,
                           color=DARK if matrix['service'] == 'all' else MUTED, anchor='mm')

    def draw_cell(x: float, y: float, service: str, cell: dict[str, Any] | None, bold: bool) -> None:
        rate = cell['rate'] if cell else None
        fill, ink = _heat(rate, highest[service])
        pad = min(0.03, row * 0.06)
        panel.draw.rounded_rectangle([_px(x + pad), _px(y + pad), _px(x + cell_width - pad), _px(y + row - pad)],
                                     radius=_px(0.05), fill=fill)
        if cell is None:
            panel.text(x + cell_width / 2, y + row / 2, '—', rate_size * 0.86, color=MUTED, anchor='mm')
            return
        share = f'{rate:.1f}%' if rate is not None else '—'
        calls = f"{_number(cell['nq'])}/{_number(cell['total'])}"
        both = calls_size >= 5
        panel.text(x + cell_width / 2, y + row * (0.38 if both else 0.5), share,
                   _fit_size(panel.draw, share, rate_size, True, cell_width - 0.08), bold=True, color=ink, anchor='mm')
        if both:
            panel.text(x + cell_width / 2, y + row * 0.74, calls, _fit_size(panel.draw, calls, calls_size, bold, cell_width - 0.08),
                       bold=bold, color=ink, anchor='mm')

    for row_index, campaign in enumerate([*campaigns, 'Total']):
        y = top + row * (head_rows + row_index)
        is_total = campaign == 'Total'
        panel.text(left + 0.12, y + row / 2, campaign if is_total else campaign_label(campaign), head_size,
                   bold=True, color=DARK if is_total else TEXT, width=RATE_LABEL - 0.16, anchor='lm')
        for index, group in enumerate(groups):
            for position, matrix in enumerate(matrices):
                if is_total:
                    cell = matrix['total'] if group == 'Total' else matrix['operator_totals'].get(group)
                elif group == 'Total':
                    cell = matrix['campaign_totals'].get(campaign)
                else:
                    cell = matrix['cells'].get(campaign, {}).get(group)
                draw_cell(group_left(index) + cell_width * position, y, matrix['service'], cell,
                          is_total or group == 'Total' or matrix['service'] == 'all')
    return panel.png()


def rate_panels(rates: dict[str, Any]) -> list[tuple[str, BytesIO]]:
    """The NQ rate of each campaign and operator in one table, every service under each operator.

    The table takes one slide, or two when the operators or campaigns are many: then the operators,
    or the campaigns, are split between both.
    """
    matrices = [matrix for matrix in rates.get('matrices') or [] if matrix['campaigns'] and matrix['operators']]
    if not matrices:
        return []
    # "All services" holds every campaign and operator of the selection, in their order.
    widest = next((matrix for matrix in matrices if matrix['service'] == 'all'), matrices[0])
    campaigns, operators = list(widest['campaigns']), list(widest['operators'])
    title = 'NQ Rate by Campaign and Operator'

    def score(page: tuple[list[str], list[str], bool]) -> float:
        return _rate_shape(page[0], len(page[1]) + page[2], len(matrices), PANEL_WIDTH, PANEL_HEIGHT)[2]

    pages = [(campaigns, operators, True)]
    if score(pages[0]) < RATE_DENSE and (len(operators) > 1 or len(campaigns) > 1):
        half = (len(operators) + 1) // 2
        middle = (len(campaigns) + 1) // 2
        splits = [split for split in (
            [(campaigns, operators[:half], False), (campaigns, operators[half:], True)] if len(operators) > 1 else None,
            [(campaigns[:middle], operators, True), (campaigns[middle:], operators, True)] if len(campaigns) > 1 else None,
        ) if split]
        pages = max(splits, key=lambda split: min(score(page) for page in split))
    return [(f'{title} · {number}/{len(pages)}' if len(pages) > 1 else title, _rate_table(matrices, *page))
            for number, page in enumerate(pages, start=1)]


def _dashes(panel: Panel, start: tuple[float, float], end: tuple[float, float], colour: str = BORDER) -> None:
    """A dashed straight line, as the dashed borders of the page."""
    (x0, y0), (x1, y1) = start, end
    length = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(length / 0.1))
    for step in range(steps):
        a, b = step / steps, min(1.0, (step + 0.55) / steps)
        panel.draw.line([_px(x0 + (x1 - x0) * a), _px(y0 + (y1 - y0) * a), _px(x0 + (x1 - x0) * b), _px(y0 + (y1 - y0) * b)],
                        fill=colour, width=max(2, _px(0.01)))


def _dashed_frame(panel: Panel, left: float, top: float, width: float, height: float, colour: str) -> None:
    """A rounded frame of dashes: the Open frame around the phase statuses."""
    radius = 0.14
    _dashes(panel, (left + radius, top), (left + width - radius, top), colour)
    _dashes(panel, (left + radius, top + height), (left + width - radius, top + height), colour)
    _dashes(panel, (left, top + radius), (left, top + height - radius), colour)
    _dashes(panel, (left + width, top + radius), (left + width, top + height - radius), colour)
    for cx, cy, angle in ((left + radius, top + radius, 180), (left + width - radius, top + radius, 270),
                          (left + width - radius, top + height - radius, 0), (left + radius, top + height - radius, 90)):
        panel.draw.arc([_px(cx - radius), _px(cy - radius), _px(cx + radius), _px(cy + radius)], angle, angle + 90,
                       fill=colour, width=max(2, _px(0.01)))


def _pill(panel: Panel, x: float, y: float, text: str, points: float, fill: str, ink: str) -> float:
    """A rounded pill centred on ``y``; its width."""
    width = panel.draw.textlength(text, font=_font(points, True)) / DPI + 0.14
    height = points / 72 * 1.55
    panel.draw.rounded_rectangle([_px(x), _px(y - height / 2), _px(x + width), _px(y + height / 2)], radius=_px(height / 2), fill=fill)
    panel.text(x + 0.07, y, text, points, bold=True, color=ink, anchor='lm')
    return width


# The fields the Status Rules read besides those of the catalog.
RULE_FIELD_LABELS = {'@attended': 'Attended', '@team': 'Team', '@assignee': 'Assignee', '@root_category': 'Root Category',
                     '@root_cause': 'Root Cause'}


def _rule_tokens(status: str, lifecycle: dict[str, Any]) -> list[list[tuple[str, str, str]]]:
    """The Status Rules that set a status as tokens, as the page shows them: Rule N, the field and its values in their colours."""
    fields = lifecycle.get('rule_fields') or {}
    rules = []
    for number, rule in enumerate(lifecycle.get('rules') or [], start=1):
        if rule.get('status') != status:
            continue
        tokens: list[tuple[str, str, str]] = [('pill', f'Rule {number}', '#fcedf2')]
        for position, condition in enumerate(rule.get('conditions') or []):
            field = str(condition.get('field') or '')
            if position:
                tokens.append(('text', '+', MUTED))
            if field == '@attended':
                tokens.append(('text', 'Not attended' if 'No' in (condition.get('values') or []) and condition.get('op') == 'in'
                               else 'Attended', MUTED))
                continue
            tokens.append(('text', (fields.get(field) or {}).get('label') or RULE_FIELD_LABELS.get(field, field), MUTED))
            if condition.get('op') in {'empty', 'not_empty'}:
                tokens.append(('text', 'EMPTY' if condition['op'] == 'empty' else 'SET', DARK))
                continue
            if condition.get('op') == 'not_in':
                tokens.append(('text', 'NOT', DARK))
            colours = (fields.get(field) or {}).get('colors') or {}
            tokens.extend(('pill', str(value), colours.get(value) or '#b8c0c6') for value in condition.get('values') or [])
        rules.append(tokens)
    return rules


def _rule_layout(panel: Panel, left: float, top: float, width: float, rules: list[list[tuple[str, str, str]]],
                 points: float) -> tuple[list[tuple[str, str, str, float, float]], float]:
    """Where each token of the rules goes (wrapping within ``width``), and the bottom of the last line."""
    line = points / 72 * 2.2
    placed = []
    y = top
    for tokens in rules:
        x = left
        for kind, value, colour in tokens:
            needed = panel.draw.textlength(value, font=_font(points, True)) / DPI + (0.14 if kind == 'pill' else 0)
            if x > left and x + needed > left + width:
                x, y = left + 0.12, y + line
            placed.append((kind, value, colour, x, y))
            x += needed + 0.05
        y += line * 1.2
    return placed, y - line * 0.7


def _rule_lines(panel: Panel, left: float, top: float, width: float, bottom: float, status: str,
                lifecycle: dict[str, Any]) -> None:
    """The Status Rules that set a status, as large as they fit in the card down to ``bottom``."""
    rules = _rule_tokens(status, lifecycle)
    if not rules:
        if status == (lifecycle.get('pipeline') or [{}])[0].get('status'):
            panel.text(left, top, 'When no rule applies', 7, color=MUTED, anchor='lm')
        return
    for points in (7, 6.5, 6, 5.5, 5, 4.5):
        placed, end = _rule_layout(panel, left, top, width, rules, points)
        if end <= bottom:
            break
    for kind, value, colour, x, y in placed:
        if y > bottom:
            break
        if kind == 'pill':
            _pill(panel, x, y, value, points, colour, DARK if colour == '#fcedf2' else _readable(colour))
        else:
            panel.text(x, y, value, points, bold=True, color=colour, anchor='lm')


def _pipeline_panel(lifecycle: dict[str, Any]) -> BytesIO:
    """The indicators and the NQ Call Status pipeline of the page: the calls not attended, Open (the phase statuses, its
    total being theirs) and the closed statuses, each card with its calls, share and age and the rules that set it."""
    total = int(lifecycle.get('total') or 0)
    pipeline = lifecycle.get('pipeline') or []
    closed = sum(item['count'] for item in pipeline if item.get('closed'))
    open_names = list(lifecycle.get('open_statuses') or [])
    open_total = int(lifecycle.get('open', total - closed) or 0)
    modes = lifecycle.get('modes') or {}
    waiting = lifecycle.get('not_attended')
    panel = Panel()
    _kpi_row(panel, [
        ('Calls', _number(total), 'Selected Non-Qualified Calls', 'total'),
        ('Automatic Status', _number(modes.get('auto', 0)), f"{_share(modes.get('auto', 0), total)} follow the Status Rules", 'team'),
        ('Status by Hand', _number(modes.get('manual', 0)), f"{_share(modes.get('manual', 0), total)} chosen by an analyst", 'commented'),
        *([(waiting['status'], _number(waiting['count']), f"{_share(waiting['count'], total)} not followed up yet",
            waiting.get('color') or '#9aa5ad')] if waiting else []),
        ('Open', _number(open_total), f'{_share(open_total, total)} attended and not closed', 'open'),
        ('Closed', _number(closed), f'{_share(closed, total)} closed', 'closed'),
        ('Stalled', _number(lifecycle.get('stalled_total', 0)), f"Open, no change for {lifecycle.get('stalled_days', 14)}+ days", 'attended'),
    ], 0, 0.95, compact=True)
    steps = [*(item for item in pipeline if not item.get('closed')), *(item for item in pipeline if item.get('closed'))]
    # The bar with the share of each status.
    x, bar_top = 0.0, 1.12
    for item in steps:
        width = panel.width * item['count'] / max(1, total)
        if width > 0:
            panel.draw.rectangle([_px(x), _px(bar_top), _px(x + width), _px(bar_top + 0.09)], fill=item.get('color') or '#b8c0c6')
        x += width
    # The cards: as wide as one another, with arrows between them and the Open frame around the phase statuses.
    arrow, pad, card_top, card_bottom = 0.32, 0.12, 1.62, panel.height - 0.16
    grouped = [item for item in steps if item['status'] in open_names]
    arrows = (len(steps) - 1) - max(0, len([item for item in steps if item.get('closed')]) - 1)
    width = (panel.width - arrows * arrow - (2 * pad if grouped else 0)
             - 0.08 * max(0, len([item for item in steps if item.get('closed')]) - 1)) / max(1, len(steps))
    head_top, rules_top = card_top + 0.2, card_top + 1.05
    x = 0.0
    frame_left = None
    for index, item in enumerate(steps):
        in_group = item['status'] in open_names
        previous = steps[index - 1] if index else None
        if previous is not None:
            if item.get('closed') and previous.get('closed'):
                x += 0.08
            else:
                if previous['status'] in open_names and not in_group:
                    x += pad
                # The arrow to the closed statuses is green, as the page's.
                panel.text(x + arrow / 2, (card_top + card_bottom) / 2, '→', 13, bold=True,
                           color='#2e8b57' if item.get('closed') else MUTED, anchor='mm')
                x += arrow
        if in_group and frame_left is None:
            frame_left = x
            x += pad
        panel.card(x, card_top, width, card_bottom - card_top, item.get('color') or '#b8c0c6')
        if item.get('closed'):
            panel.draw.rounded_rectangle([_px(x + 0.01), _px(card_top + 0.08), _px(x + width - 0.01), _px(card_bottom - 0.01)],
                                         radius=_px(0.1), fill='#f7fbf8')
        inner = width - 0.28
        panel.text(x + 0.14, head_top, str(item['status']).upper(), 7.5, bold=True, color=MUTED, width=inner)
        panel.text(x + 0.14, head_top + 0.2, _number(item['count']), 18, bold=True, color=DARK, width=inner)
        age = '' if item.get('avg_age_days') is None else f" · {item['avg_age_days']} d old on average"
        panel.text(x + 0.14, head_top + 0.62, f"{_share(item['count'], total)}{age}", 7.5, color=MUTED, width=inner)
        _dashes(panel, (x + 0.14, rules_top), (x + width - 0.14, rules_top))
        _rule_lines(panel, x + 0.14, rules_top + 0.2, inner, card_bottom - 0.14, item['status'], lifecycle)
        x += width
        if in_group and (index + 1 == len(steps) or steps[index + 1]['status'] not in open_names):
            right = x + pad
            _dashed_frame(panel, frame_left, card_top - 0.24, right - frame_left, card_bottom - card_top + 0.36, RASPBERRY)
            label = f"{_share(open_total, total)} · attended and not closed: {' + '.join(open_names)}"
            label_width = min(right - frame_left - 0.4, 0.95 + panel.draw.textlength(label, font=_font(7.5)) / DPI)
            panel.draw.rounded_rectangle([_px(frame_left + 0.2), _px(card_top - 0.38), _px(frame_left + 0.2 + label_width),
                                          _px(card_top - 0.1)], radius=_px(0.14), fill='white', outline=RASPBERRY,
                                         width=max(2, _px(0.01)))
            panel.text(frame_left + 0.32, card_top - 0.24, 'OPEN', 7.5, bold=True, color=MUTED, anchor='lm')
            panel.text(frame_left + 0.68, card_top - 0.24, _number(open_total), 10, bold=True, color=DARK, anchor='lm')
            panel.text(frame_left + 0.68 + panel.draw.textlength(_number(open_total), font=_font(10, True)) / DPI + 0.1,
                       card_top - 0.24, label, 7.5, color=MUTED, width=label_width - 0.95, anchor='lm')
            frame_left = None
    return panel.png()


def _phase_head(panel: Panel, left: float, width: float, section: dict[str, Any], key: str, title: str, base: int,
                total: int) -> float:
    """The card of a phase field with its section tag, its title and how many calls have a value; returns where its bar goes."""
    colour = section.get('color') or RASPBERRY
    panel.card(left, 0, width, panel.height, colour)
    inner = width - 0.24
    panel.draw.ellipse([_px(left + 0.12), _px(0.2), _px(left + 0.2), _px(0.28)], fill=colour)
    panel.text(left + 0.25, 0.24, str(section.get('label') or key.title()), 7, bold=True, color=MUTED, width=inner - 0.13,
               anchor='lm')
    panel.text(left + 0.12, 0.36, title, 9, bold=True, color=DARK, width=inner)
    if base == total:
        return 0.62
    panel.text(left + 0.12, 0.62, f'{_number(base)} of {_number(total)} with a value', 6.5, bold=True, color=MUTED, width=inner)
    return 0.8


def _phase_bar(panel: Panel, left: float, y: float, width: float, items: list[tuple[str, int, str]], base: int) -> None:
    x = left
    for _label, count, colour in items:
        part = width * count / max(1, base)
        if part > 0:
            panel.draw.rectangle([_px(x), _px(y), _px(x + part), _px(y + 0.07)], fill=colour)
        x += part


def _phase_value(panel: Panel, left: float, y: float, width: float, label: str, count: int, colour: str, base: int) -> None:
    """A value of a phase field: its colour, its name, its calls and its share."""
    panel.draw.rounded_rectangle([_px(left), _px(y - 0.045), _px(left + 0.09), _px(y + 0.045)], radius=_px(0.02), fill=colour)
    share = _share(count, base)
    share_width = panel.draw.textlength(share, font=_font(6.5)) / DPI
    count_width = panel.draw.textlength(_number(count), font=_font(6.5, True)) / DPI
    panel.text(left + 0.14, y, label, 6.5, bold=True, color=TEXT, width=width - 0.3 - share_width - count_width - 0.08, anchor='lm')
    panel.text(left + width - share_width - 0.06, y, _number(count), 6.5, bold=True, color=DARK, anchor='rm')
    panel.text(left + width, y, share, 6.5, color=MUTED, anchor='rm')


def _phases_panels(lifecycle: dict[str, Any], sections: dict[str, dict[str, Any]]) -> list[tuple[str, BytesIO]]:
    """The phase cards of the page: RCA Identification and each list field of the Analysis, Implementation and Planning
    sections in one row, with the share of each value (of the calls with a value, unless Empty is shown); a field with more
    than WIDE_PHASE_VALUES values on a panel of its own, its values in columns from the most frequent."""
    total = int(lifecycle.get('total') or 0)
    cards = []
    if lifecycle.get('rca'):
        cards.append(('rca', 'RCA Identification', [('Identified', lifecycle['rca'].get('identified', 0), '#2e8b57'),
                                                    ('Not identified', lifecycle['rca'].get('not_identified', 0), '#e7dde1')], total,
                      False))
    for phase in lifecycle.get('phases') or []:
        items = [(item['value'], int(item['count']), item.get('color') or '#d9cfd3') for item in phase.get('items') or []]
        wide = len(items) > WIDE_PHASE_VALUES
        if wide:
            items.sort(key=lambda item: -item[1])
        if phase.get('empty'):
            items.append(('Empty', int(phase['empty']), '#e7dde1'))
        base = total if phase.get('empty') else sum(count for _label, count, _colour in items)
        cards.append((phase.get('section') or '', phase['label'], items, base, wide))
    panels = []
    row = 0.21
    narrow = [card for card in cards if not card[4]]
    if narrow:
        panel = Panel()
        gap = 0.1
        width = (panel.width - gap * (len(narrow) - 1)) / len(narrow)
        for index, (key, title, items, base, _wide) in enumerate(narrow):
            left = index * (width + gap)
            y = _phase_head(panel, left, width, sections.get(key) or {}, key, title, base, total)
            _phase_bar(panel, left + 0.12, y, width - 0.24, items, base)
            y += 0.24
            for label, count, colour in items[:max(0, int((panel.height - 0.1 - y) / row))]:
                _phase_value(panel, left + 0.12, y, width - 0.24, label, count, colour, base)
                y += row
        panels.append(('Phases', panel.png()))
    for key, title, items, base, _wide in (card for card in cards if card[4]):
        # As many columns of values as fit 2 inches each, more when the panel is not tall enough for them.
        top = 1.04 if base != total else 0.86
        fit = int((PANEL_HEIGHT - 0.1 - top) / row)
        inner = PANEL_WIDTH - 0.24
        columns = max(int(inner / 2.0), math.ceil(len(items) / fit))
        rows = math.ceil(len(items) / columns)
        panel = Panel(height=min(PANEL_HEIGHT, top + rows * row + 0.1))
        y = _phase_head(panel, 0, panel.width, sections.get(key) or {}, key, title, base, total)
        _phase_bar(panel, 0.12, y, inner, items, base)
        y += 0.24
        column = (inner - 0.3 * (columns - 1)) / columns
        for index, (label, count, colour) in enumerate(items):
            _phase_value(panel, 0.12 + (index // rows) * (column + 0.3), y + (index % rows) * row, column, label, count, colour, base)
        panels.append((title, panel.png()))
    return panels


def lifecycle_title(subtitle: str) -> SlideTitle:
    """The title of the Lifecycle & Phases slides, with what each one shows in its subtitle."""
    return SlideTitle('Lifecycle & Phases', '', subtitle)


def lifecycle_panels(lifecycle: dict[str, Any], sections: list[dict[str, Any]] | None = None) -> list[tuple[SlideTitle, BytesIO]]:
    """The Lifecycle & Phases of the page: its indicators and NQ Call Status pipeline with the rules of each status, the
    phase cards, the time in each status and the most frequent moves, and the stalled open calls."""
    if not int(lifecycle.get('total') or 0):
        return []
    panels = [(lifecycle_title('NQ Call Status Pipeline'), _pipeline_panel(lifecycle))]
    panels += [(lifecycle_title(subtitle), image) for subtitle, image in
               _phases_panels(lifecycle, {str(item.get('key')): item for item in sections or []})]
    times = [[item['status'], f"{item['avg_days']:.1f}", _number(item['moves'])] for item in lifecycle.get('time_in_status') or []]
    moves = [[item['from'], item['to'], _number(item['count'])] for item in lifecycle.get('moves') or []]
    rows = max(len(times), len(moves), 1)
    panel = Panel(height=min(PANEL_HEIGHT, TABLE_HEAD + 0.3 * (rows + 1) + 0.2))
    row_height = min(0.3, (panel.height - TABLE_HEAD - TABLE_FOOT) / (rows + 1))
    half = (panel.width - 0.18) / 2
    _table_card(panel, 0, panel.height, 'Time in Each Status', ['Status', 'Average Days', 'Calls Moved Out'], times, len(times),
                row_height, left=0, width=half)
    _table_card(panel, 0, panel.height, 'Most Frequent Moves', ['From', 'To', 'Times'], moves, len(moves), row_height,
                left=half + 0.18, width=half, numeric={2})
    panels.append((lifecycle_title('Time in Each Status and Most Frequent Moves'), panel.png()))
    stalled = [[item['status'], item.get('operator') or '—', campaign_label(item.get('campaign') or '') or '—', item.get('city') or '—',
                _number(item['days']), 'Yes' if item.get('followed_up') else 'Not yet'] for item in lifecycle.get('stalled') or []]
    heading = f"Stalled Open Calls, no change for {lifecycle.get('stalled_days', 14)}+ days ({_number(lifecycle.get('stalled_total', 0))})"
    panels += [(lifecycle_title(heading), image) for _title, image in
               table_panels(heading, ['Status', 'Operator', 'Campaign', 'City', 'Days Without Change', 'Followed Up'], stalled,
                            single=True, numeric={4})]
    return panels


def _domain_tag(panel: Panel, left: float, y: float, domains: list[dict[str, Any]], size: float = 7) -> None:
    """The root domain of a category in a small tag of its colour: the main one and how many more."""
    text = domains[0]['domain'] + (f' +{len(domains) - 1}' if len(domains) > 1 else '')
    colour = domains[0].get('color') or '#b8c0c6'
    width = _tag_width(panel, domains, size)
    half = size / 72 * 0.75
    panel.draw.rounded_rectangle([_px(left), _px(y - half), _px(left + width), _px(y + half)], radius=_px(0.03), fill=colour)
    panel.text(left + width / 2, y, text, size, bold=True, color=_readable(colour), anchor='mm')


def _tag_width(panel: Panel, domains: list[dict[str, Any]], size: float = 7) -> float:
    if not domains:
        return 0.0
    text = domains[0]['domain'] + (f' +{len(domains) - 1}' if len(domains) > 1 else '')
    return panel.draw.textlength(text, font=_font(size, True)) / DPI + 0.1


Line = tuple[bool, str, int, list[dict[str, Any]], str]
# The heading and row height of a compact bar section.
COMPACT_HEAD = 0.52
COMPACT_ROW = 0.15


def _bar_section(panel: Panel, left: float, top: float, width: float, bottom: float, title: str, note: str,
                 lines: list[Line], *, compact: bool = False) -> float:
    """A titled list of bars in a card, as in the page: each main row (a domain or category, with the root domain of a
    category in a tag) and the rows below it indented; the first ones that fit above ``bottom``. Where the list ends.

    ``compact`` sections (two in a card) use a smaller heading and closer rows."""
    pad = 0.16
    title_size, note_size, note_y, first, row, main_size, sub_size = ((9.5, 7, 0.36, COMPACT_HEAD, COMPACT_ROW, 8, 7) if compact
                                                                       else (11, 7.5, 0.47, 0.68, 0.2, 8.5, 7.5))
    panel.text(left + pad, top + 0.12, title, title_size, bold=True, color=DARK, width=width - 2 * pad)
    panel.text(left + pad, top + note_y, note, note_size, color=MUTED, width=width - 2 * pad, anchor='lm')
    first += top
    if not lines:
        panel.text(left + pad, first + 0.1, 'No calls.', main_size, color=MUTED, anchor='lm')
        return first + 0.25
    shown = lines[:max(1, int((bottom - first) / row))]
    if len(shown) < len(lines):
        panel.text(left + width - pad, top + 0.14, f'First {len(shown)} of {len(lines)} rows', 7, bold=True, color=MUTED, anchor='ra')
    highest = max(1, *(count for main, _label, count, _domains, _colour in lines if main))
    label_width = width * 0.56
    track_left = left + pad + label_width + 0.08
    track_width = width - 2 * pad - label_width - 0.08 - 0.45
    for index, (main, label, count, domains, colour) in enumerate(shown):
        y = first + row * (index + 0.5)
        indent = 0.0 if main else 0.16
        size = main_size if main else sub_size
        font = _font(size, main)
        # The name as long as the tag of its domain leaves room for.
        tag_size = 6.5 if compact else 7
        tag = _tag_width(panel, domains, tag_size)
        name = _fit(panel.draw, label, font, _px(label_width - indent - (tag + 0.06 if tag else 0)))
        panel.text(left + pad + indent, y, name, size, bold=main, color=TEXT if main else MUTED, anchor='lm')
        if tag:
            _domain_tag(panel, left + pad + indent + panel.draw.textlength(name, font=font) / DPI + 0.06, y, domains, tag_size)
        thickness = (0.04 if compact else 0.05) if main else 0.032
        panel.draw.rounded_rectangle([_px(track_left), _px(y - thickness), _px(track_left + track_width), _px(y + thickness)],
                                     radius=_px(thickness), fill=TRACK)
        fill = max(0.05, track_width * count / highest)
        panel.draw.rounded_rectangle([_px(track_left), _px(y - thickness), _px(track_left + fill), _px(y + thickness)],
                                     radius=_px(thickness), fill=colour or (RASPBERRY if main else '#d97a96'))
        panel.text(left + width - pad, y, _number(count), size, bold=True, color=DARK, anchor='rm')
    return first + row * len(shown)


def _category_lines(groups: list[dict[str, Any]], unnamed: str) -> list[Line]:
    """Each category with the root domains of its calls, and its causes below it; ``unnamed`` names the calls without one."""
    lines: list[Line] = []
    for group in groups:
        name = unnamed if group['category'] == '—' else group['category']
        lines.append((True, name, int(group['count']), group.get('domains') or [], ''))
        lines.extend((False, 'No cause' if cause['cause'] == '—' else cause['cause'], int(cause['count']), [], '')
                     for cause in group.get('causes') or [])
    return lines


def rca_insight_panels(insights: dict[str, Any]) -> list[tuple[str | SlideTitle, BytesIO]]:
    """The root cause sources compared as in the page (the DT Analyzer RCA, the NetCheck RCA, the Ericsson RCA and
    the analysts): the root domains and catalog categories of each source under the calls each one covers, then its own
    categories and causes under how each RCA agrees with the analysts and with the other RCAs."""
    coverage = insights.get('coverage') or {}
    total = int(coverage.get('total') or 0)
    if not total:
        return []
    agreement = insights.get('agreement') or {}
    provider_rca = _provider(insights)[1]

    def covered(label: str, source: str, kind: str) -> tuple[str, str, str, str]:
        return label, _number(coverage.get(source)), f"{_share(int(coverage.get(source) or 0), total)} of the calls", kind

    def rate(label: str, other: str, name: str, kind: str) -> tuple[str, str, str, str]:
        # The first source names the card and the other one its note, so that every name fits.
        item = agreement.get(name) or {}
        value = item.get('rate')
        return (label, f'{value:.0f}%' if value is not None else '—',
                f"↔ {other} · {_number(item.get('agree'))} of {_number(item.get('compared'))}", kind)

    def indicators(cards: list[tuple[str, str, str, str]]) -> Panel:
        panel = Panel()
        _kpi_row(panel, cards, 0, 0.75, compact=True)
        return panel

    # As in the page, the DT Analyzer RCA first: the calls each source covers, then how each RCA agrees with the
    # analysts and with the other RCAs.
    coverage_cards = [
        ('Calls', _number(total), 'Selected Non-Qualified Calls', 'total'), covered('DT Analyzer RCA', 'dta', '#8e24aa'),
        covered(provider_rca, 'netcheck', 'attended'), covered('Ericsson RCA', 'script', 'team'), covered('Selected Cause', 'selected', 'closed'),
    ]
    agreement_cards = [
        rate('Selected Cause', 'DT Analyzer RCA', 'selected_dta', 'commented'), rate('Selected Cause', provider_rca, 'selected_netcheck', 'commented'),
        rate('Selected Cause', 'Ericsson RCA', 'selected_script', 'commented'), rate('DT Analyzer RCA', provider_rca, 'netcheck_dta', 'open'),
        rate('DT Analyzer RCA', 'Ericsson RCA', 'script_dta', 'open'), rate(provider_rca, 'Ericsson RCA', 'netcheck_script', 'open'),
    ]

    domains = insights.get('domains') or {}
    mapped = insights.get('mapped') or {}
    hierarchies = insights.get('hierarchies') or {}
    gap, top = 0.15, 0.87
    # As in the page: under the indicators, the root domains of each source and its categories in the catalog, the first
    # categories that fit; then, under the agreement indicators, its own categories and causes.
    catalog = indicators(coverage_cards)
    width = (catalog.width - 3 * gap) / 4
    # The root domains and the catalog categories of a source in two cards, one below the other as in the page: the
    # domain cards as tall as the longest of them, so the category cards start at the same height.
    longest = max([len(domains.get(source) or []) for source in ('dta', 'netcheck', 'script', 'selected')] + [1])
    middle = top + COMPACT_HEAD + COMPACT_ROW * longest + 0.05
    for index, (name, source, unnamed, notes) in enumerate((
            ('DT Analyzer RCA', 'dta', 'No category',
             ('The root domains it finds from the data of the CDR', 'The Root Categories it finds from the data of the CDR')),
            (provider_rca, 'netcheck', 'No catalog category',
             ('Its categories translated onto the root domains of the catalog', 'Its categories translated onto the Root Cause Catalog')),
            ('Ericsson RCA', 'script', 'No catalog category',
             ('Its categories translated onto the root domains of the catalog', 'Its categories translated onto the Root Cause Catalog')),
            ('Selected', 'selected', 'No category',
             ('The root domain of the category the analysts chose', 'The Root Category the analysts chose')))):
        left = index * (width + gap)
        arrow = ' → ' if source != 'selected' else ' '
        catalog.card(left, top, width, middle - top)
        _bar_section(catalog, left, top, width, middle, f'{name}{arrow}Root Domain', notes[0],
                     [(True, item['domain'], int(item['count']), [], item.get('color') or RASPBERRY) for item in domains.get(source) or []],
                     compact=True)
        catalog.card(left, middle + 0.08, width, catalog.height - middle - 0.08)
        _bar_section(catalog, left, middle + 0.08, width, catalog.height - 0.04, f'{name}{arrow}Root Category', notes[1],
                     _category_lines(mapped.get(source) or [], unnamed), compact=True)
    sources = indicators(agreement_cards)
    # (Titled as the cards above them: the source → Root Cause, and Selected Root Cause.)
    for index, (title, note, source) in enumerate((('DT Analyzer RCA → Root Cause', 'Root Category → Root Cause it finds', 'dta'),
                                                   (f'{provider_rca} → Root Cause', 'Failure Category → Subcategory of the CDR', 'netcheck'),
                                                   ('Ericsson RCA → Root Cause', 'Suggested Category → Cause of the Ericsson RCA', 'script'),
                                                   ('Selected Root Cause', 'Root Category → Root Cause the analysts chose', 'selected'))):
        left = index * (width + gap)
        sources.card(left, top, width, sources.height - top)
        _bar_section(sources, left, top, width, sources.height - 0.08, title, note,
                     _category_lines(hierarchies.get(source) or [], 'No category'))
    return [(SlideTitle('Root Cause Sources', subtitle='Root Domains and Categories in the Root Cause Catalog'), catalog.png()),
            (SlideTitle('Root Cause Sources', subtitle='Categories and Causes of Each RCA'), sources.png())]
