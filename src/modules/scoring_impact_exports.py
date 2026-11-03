"""The CSV and the PowerPoint of the Methodology Impact (see scoring_impact), panel by panel as the tab shows them. The deck is
composed like every Scoring document (bundle_report_templates.module_document); the workspace chooses its panels and their
operators in Scoring Export Panels.
"""
from __future__ import annotations

import csv
import math
import re
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Callable, Iterable

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_TICK_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from src.modules import report_structure
from src.modules.cdr_reporting import _named_slide_layout, _remove_all_slides, _set_structural_slide_text
from src.modules.operator_roles import focus_operators
from src.modules.scoring_export_panels import FOCUS_OPERATORS, normalize_export_panels
from src.modules.scoring_exports import _slide, _tag_slides, focus_matcher
from src.modules.scoring_impact_analysis import CAUSE_LABELS, CAUSES
from src.modules.scoring_impact_maps import MAP_FIELDS, MEASURES, impact_map, map_geometry
from src.modules.scoring_insight_slides import _box, _cell, _rgb, _table
from src.modules.scoring_summary_slides import (
    CONTENT_BOTTOM, CONTENT_TOP, GAIN_COLOR, INK, LOSS_COLOR, MAX_TABLE_ROWS, MUTED, STAKE_COLORS, _blend, _pages, _text,
)
from src.modules.scoring_themes import DEFAULT_THEME, themed, use_theme

COMBINED = 'Combined'
LEFT, WIDTH = .45, 12.43
TABLE_ROWS = 14
AREA_ROWS = MAX_TABLE_ROWS - 8
HEADER_FILL = '#E9ECEF'
NO_CHANGE = .005
# (The maps of the Points Lost per operator, with the measures of the panel.)
RELATIVE_MAP_FIELDS = ('City', 'Postal Code')
CAUSE_COLORS = {'weights': '#4472C4', 'rules': '#C55A11', 'new': GAIN_COLOR, 'removed': LOSS_COLOR}


def _number(value: Any, digits: int = 1) -> str:
    return 'N/A' if value is None else f'{value:,.{digits}f}'


def _signed(value: Any, digits: int = 2) -> str:
    if value is None:
        return 'N/A'
    return f'{abs(value):,.{digits}f}' if abs(value) < 10 ** -digits / 2 else f'{value:+,.{digits}f}'


def _environment_label(part: dict[str, Any], environment: str) -> str:
    return next((item['label'] for item in part['environments'] if item['name'] == environment), environment)


def impact_part(impact: dict[str, Any], scoring: str, environment: str) -> tuple[dict[str, Any], str, str]:
    """The panels of a scoring, its name and the environment to show (All Environments when it has not that one)."""
    scorings = impact['scorings']
    name = scoring if scoring in scorings else 'best_network' if 'best_network' in scorings else next(iter(scorings))
    part = scorings[name]
    names = [item['name'] for item in part['environments']]
    if environment in names:
        return part, name, environment
    return part, name, COMBINED if COMBINED in names else names[0]


# ----------------------------------------------------------------------------------------------------------------------
# CSV
# ----------------------------------------------------------------------------------------------------------------------

def export_impact_csv(impact: dict[str, Any], scoring: str = 'best_network', maps: dict[str, Any] | None = None) -> str:
    """Every value of the panels, one per row: the panel, environment, operator and item, before, after and their difference."""
    part, name, _environment = impact_part(impact, scoring, COMBINED)
    labels = {item['operator']: item['label'] for item in part['operators']}
    names = {item['name']: item['label'] for item in part['environments']}
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Panel', 'Environment', 'Operator', 'Level', 'Item', 'First methodology', 'Second methodology', 'Before', 'After', 'Difference'])
    first, second = impact['before']['profile_name'], impact['after']['profile_name']

    def row(panel: str, environment: str, operator: str, level: str, item: str, before: Any, after: Any, delta: Any) -> None:
        writer.writerow([panel, names.get(environment, environment), labels.get(operator, operator), level, item, first, second, before, after, delta])

    def write(panel: str, environment: str, cells: dict[str, Any], level: str, item: str) -> None:
        for operator, cell in cells.items():
            row(panel, environment, operator, level, item, cell.get('before'), cell.get('after'), cell.get('delta'))

    for kpi in part['changes']['kpis']:
        for detail in kpi['details']:
            writer.writerow(['What changed', detail.get('environment') or '', '', detail['label'], kpi['kpi'], first, second,
                             detail['before'], detail['after'], ''])
    for environment, entry in part['scoring'].items():
        write('Scoring', environment, entry['operators'], 'Total', 'Total')
    for environment, entry in part['competition'].items():
        for operator, value in entry['relative'].items():
            row('Against the mean of the operators', environment, operator, 'Total', 'Total', '', '', value)
        for operator, others in entry['matrix'].items():
            for other, step in others.items():
                row('Head to head', environment, operator, 'Against', labels.get(other, other), step['before'], step['after'], step['delta'])
    for environment, entry in part['drivers'].items():
        for operator, item in entry.items():
            for cause, value in item['causes'].items():
                row('Causes', environment, operator, 'Cause', CAUSE_LABELS[cause], '', '', value)
            for category, values in item['categories'].items():
                row('Causes', environment, operator, 'Category', category, '', '', values['delta'])
    for environment, entry in part['exposure'].items():
        for operator, item in entry['operators'].items():
            row('Exposure', environment, operator, 'Correlation', 'r', '', '', item['r'])
            row('Exposure', environment, operator, 'Points moved', 'Against the others', '', '', item['net'])
    for environment, rows in part['categories'].items():
        for item in rows:
            write('Category', environment, item['operators'], 'Category', item['category'])
    for environment, rows in part['kpis'].items():
        for item in rows:
            write('KPI', environment, item['operators'], item['category'], item['kpi'])
    for level, environments in part['areas'].items():
        for environment, rows in environments.items():
            for item in rows:
                write('Scoring of the area', environment, item['operators'], level, item['area'])
    for field, environments in (part.get('serving') or {}).items():
        for environment, rows in environments.items():
            for item in rows:
                write('Serving cells (National points lost)', environment, item['operators'], field, item['name'])
    for environment, entry in part['gap'].items():
        write('GAP', environment, entry['total'], 'Total', 'Total')
        for item in entry['categories']:
            write('GAP', environment, item['operators'], 'Category', item['category'])
        for item in entry['kpis']:
            write('GAP', environment, item['operators'], item['category'], item['kpi'])
    for environment, entry in part['points_lost'].items():
        write('Points Lost', environment, entry['operators'], 'Total', 'Total')
        for item in entry['categories']:
            write('Points Lost', environment, item['operators'], 'Category', item['category'])
        for item in entry['kpis']:
            write('Points Lost', environment, item['operators'], item['category'], item['kpi'])
    for item in (part.get('stability') or {}).get('campaigns') or []:
        for operator, value in (item.get('operators') or {}).items():
            row('On the tests of each campaign', COMBINED, operator, 'Campaign', item['label'], '', '', value)
    for field, environments in (((maps or {}).get('series') or {}).get(name) or {}).items():
        for environment, operators in environments.items():
            for operator, areas in operators.items():
                for area, (before, after) in areas.items():
                    row('Map (National points lost)', environment, operator, field, area, before, after, round(before - after, 3))
    return output.getvalue()


# ----------------------------------------------------------------------------------------------------------------------
# Drawing
# ----------------------------------------------------------------------------------------------------------------------

def _tone(delta: Any, inverse: bool = False) -> str:
    if delta is None or abs(delta) < NO_CHANGE:
        return MUTED
    return themed(GAIN_COLOR) if (delta > 0) != inverse else themed(LOSS_COLOR)


def _hex_channels(color: str) -> tuple[int, int, int]:
    text = color.lstrip('#')
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _heat(value: float | None, scale: float) -> str | None:
    """A fill from the loss colour to the gain colour; a root scale so the small differences show beside the large ones."""
    if value is None or not scale or abs(value) < NO_CHANGE:
        return None
    return _blend(themed(GAIN_COLOR) if value > 0 else themed(LOSS_COLOR), .14 + min(1.0, math.sqrt(abs(value) / scale)) * .76)


def _shift_table(slide, first_header: str, operators: list[dict[str, Any]], rows: list[dict[str, Any]], *, top: float, inverse: bool = False,
                 available: float | None = None, extra: str = '') -> float:
    """A table of a label and a cell per operator (its difference, the value before and after, and a bar either side of zero
    against the largest difference of the table). What it fills is returned."""
    available = available if available is not None else CONTENT_BOTTOM - .3 - top
    count = len(rows) + 1
    row_height = min(.62, max(.22, available / count))
    size = 11 if row_height >= .55 else 10 if row_height >= .42 else 9 if row_height >= .36 else 8 if row_height >= .28 else 7
    label_width = min(max(2.6, WIDTH - 1.55 * len(operators) - (1.3 if extra else 0)), 5.2)
    cell_width = (WIDTH - label_width - (1.3 if extra else 0)) / max(len(operators), 1)
    widths = [label_width, *([cell_width] * len(operators)), *([1.3] if extra else [])]
    shape, table = _table(slide, count, len(widths), LEFT, top, WIDTH, row_height, widths)
    shape.name = 'Scoring Impact Table'
    _cell(table.cell(0, 0), first_header, size=size, bold=True, fill=HEADER_FILL)
    for index, operator in enumerate(operators, start=1):
        _cell(table.cell(0, index), f"{operator['label']}{' (reference)' if operator.get('is_reference') else ''}", size=size, bold=True,
              fill=HEADER_FILL, align=PP_ALIGN.CENTER, color=operator.get('color') or INK)
    if extra:
        _cell(table.cell(0, len(widths) - 1), extra, size=size, bold=True, fill=HEADER_FILL, align=PP_ALIGN.CENTER)
    scale = max((abs(cell.get('delta') or 0) for row in rows for cell in row['cells'].values()), default=0.0)
    for line, row in enumerate(rows, start=1):
        _cell(table.cell(line, 0), str(row['label']), size=size, bold=bool(row.get('bold')), kpi_type=row.get('kpi_type') or '')
        table.cell(line, 0).text_frame.word_wrap = True
        for index, operator in enumerate(operators, start=1):
            cell = row['cells'].get(operator['operator'])
            if not cell or (cell.get('before') is None and cell.get('after') is None):
                _cell(table.cell(line, index), '—', size=size, align=PP_ALIGN.CENTER, color=MUTED)
                continue
            delta = cell.get('delta')
            before = 'none' if cell.get('before') is None else _number(cell.get('before'))
            after = 'none' if cell.get('after') is None else _number(cell.get('after'))
            flag = ' ⇄' if cell.get('flip') else ''
            _cell(table.cell(line, index), f'{_signed(delta)}{flag}   {before} → {after}', size=size, bold=True, align=PP_ALIGN.CENTER, color=_tone(delta, inverse))
        if extra:
            _cell(table.cell(line, len(widths) - 1), str(row.get('extra') or ''), size=size, align=PP_ALIGN.CENTER)
    # The bars under each value, over the table.
    for line, row in enumerate(rows, start=1):
        for index, operator in enumerate(operators, start=1):
            cell = row['cells'].get(operator['operator']) or {}
            delta = cell.get('delta')
            if not scale or delta is None or abs(delta) < NO_CHANGE:
                continue
            middle = LEFT + label_width + cell_width * (index - .5)
            reach = abs(delta) / scale * (cell_width / 2 - .06)
            bar = _box(slide, middle - reach if delta < 0 else middle, top + row_height * (line + 1) - .055, max(reach, .01), .035,
                       themed(GAIN_COLOR) if (delta > 0) != inverse else themed(LOSS_COLOR))
            bar.name = 'Scoring Impact Bar'
    return row_height * count


def _heat_table(slide, first_header: str, columns: list[dict[str, Any]], rows: list[dict[str, Any]], *, left: float = LEFT, top: float, width: float = WIDTH,
                available: float | None = None, digits: int = 2, scale: float | None = None) -> float:
    """A heatmap: rows by columns, each cell in the colour of its value (``value`` or None). What it fills is returned."""
    available = available if available is not None else CONTENT_BOTTOM - .3 - top
    count = len(rows) + 1
    row_height = min(.42, max(.2, available / count))
    size = 10 if row_height >= .36 else 9 if row_height >= .28 else 8 if row_height >= .24 else 7
    label_width = min(width * .34, 3.2) if len(columns) > 2 else width * .5
    cell_width = (width - label_width) / max(len(columns), 1)
    shape, table = _table(slide, count, len(columns) + 1, left, top, width, row_height, [label_width, *([cell_width] * len(columns))])
    shape.name = 'Scoring Impact Heatmap'
    _cell(table.cell(0, 0), first_header, size=size, bold=True, fill=HEADER_FILL)
    for index, column in enumerate(columns, start=1):
        _cell(table.cell(0, index), str(column['label']), size=max(size - 1, 6), bold=True, fill=HEADER_FILL, align=PP_ALIGN.CENTER, color=column.get('color') or INK)
        table.cell(0, index).text_frame.word_wrap = True
    peak = scale if scale is not None else max((abs(value) for row in rows for value in row['values'] if value is not None), default=0.0)
    for line, row in enumerate(rows, start=1):
        _cell(table.cell(line, 0), str(row['label']), size=size, bold=True)
        table.cell(line, 0).text_frame.word_wrap = True
        for index, value in enumerate(row['values'], start=1):
            if value is None:
                _cell(table.cell(line, index), '—', size=size, align=PP_ALIGN.CENTER, color=MUTED)
                continue
            _cell(table.cell(line, index), _signed(value, digits), size=size, bold=True, align=PP_ALIGN.CENTER, fill=_heat(value, peak) or '#F1F3F5', color=INK)
    return row_height * count


def _diverging_bars(slide, items: list[dict[str, Any]], *, left: float, top: float, width: float, height: float, label_width: float = 2.6, inverse: bool = False) -> None:
    """Bars either side of zero: a label, the bar and its value."""
    if not items:
        return
    row_height = min(.42, height / len(items))
    value_room = .75
    room = max((width - label_width - value_room * 2) / 2, .2)
    middle = left + label_width + value_room + room
    scale = max((abs(item['value'] or 0) for item in items), default=0.0) or 1.0
    axis = _box(slide, middle - .005, top, .01, row_height * len(items), '#C3CCD5')
    axis.name = 'Scoring Impact Axis'
    size = 11 if row_height >= .36 else 9 if row_height >= .26 else 8
    for index, item in enumerate(items):
        value = item['value'] or 0
        y = top + index * row_height
        _text(slide, str(item['label']), left, y, label_width - .08, row_height, size=size, bold=bool(item.get('color')), color=item.get('color') or INK, align=PP_ALIGN.RIGHT)
        reach = abs(value) / scale * room
        color = themed(GAIN_COLOR) if (value > 0) != inverse else themed(LOSS_COLOR)
        if abs(value) >= NO_CHANGE:
            bar = _box(slide, middle - reach if value < 0 else middle, y + row_height * .16, max(reach, .01), row_height * .68, color)
            bar.name = 'Scoring Impact Bar'
        if value < 0:
            _text(slide, _signed(value), middle - reach - value_room - .03, y, value_room, row_height, size=size, bold=True, color=_tone(value, inverse), align=PP_ALIGN.RIGHT)
        else:
            _text(slide, _signed(value), middle + reach + .03, y, value_room, row_height, size=size, bold=True, color=_tone(value, inverse))


def _note(slide, text: str) -> None:
    _text(slide, text, LEFT, CONTENT_BOTTOM - .27, WIDTH, .25, size=8, color=MUTED)


def _subtitle(impact: dict[str, Any], environment: str, part: dict[str, Any]) -> str:
    return ' · '.join([f"{impact['before']['profile_name']} → {impact['after']['profile_name']}",
                       f"Tests of {impact['after']['campaign_label']}", impact.get('nr_mode') or '', _environment_label(part, environment)])


def _cover(presentation, impact: dict[str, Any], part: dict[str, Any], scoring: str) -> None:
    layout = _named_slide_layout(presentation, 'Title Page')
    if layout is None:
        raise ValueError("The PowerPoint template needs a 'Title Page' layout for scoring exports.")
    slide = presentation.slides.add_slide(layout)
    _tag_slides(presentation, len(presentation.slides) - 1, 'cover')
    reference = next((item['label'] for item in part['operators'] if item.get('is_reference')), part.get('reference') or '')
    lines = [f"{impact['before']['profile_name']} → {impact['after']['profile_name']}",
             f"Tests of {impact['after']['campaign_label']} scored with both · {impact.get('nr_mode') or ''} · GAP reference: {reference}"]
    title = 'Methodology Impact' + (' — Most Reliable Network' if scoring == 'most_reliable' else '')
    _set_structural_slide_text(slide, title, '\n'.join(lines))


def _conclusions_slide(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str) -> None:
    items = part.get('conclusions') or []
    if not items:
        return
    for page in _pages(items, 9)[:2]:
        slide = _slide(presentation, 'Methodology Impact — What stands out', _subtitle(impact, environment, part))
        columns = 3
        rows = math.ceil(len(page) / columns)
        gap = .16
        width = (WIDTH - gap * (columns - 1)) / columns
        height = min(1.75, (CONTENT_BOTTOM - .1 - CONTENT_TOP - gap * (rows - 1)) / rows)
        for index, item in enumerate(page):
            left = LEFT + (index % columns) * (width + gap)
            top = CONTENT_TOP + (index // columns) * (height + gap)
            card = _box(slide, left, top, width, height, '#F6F8FA')
            card.name = 'Scoring Impact Conclusion'
            color = {'gain': themed(GAIN_COLOR), 'loss': themed(LOSS_COLOR), 'flat': MUTED}.get(item.get('tone'), themed('#1450A8'))
            rule = _box(slide, left, top, .06, height, color)
            rule.name = 'Scoring Impact Rule'
            _text(slide, str(item['title']).upper(), left + .15, top + .07, width - .2, .22, size=8, bold=True, color=MUTED)
            _text(slide, str(item['headline']), left + .15, top + .28, width - .2, .36, size=14, bold=True, color=INK)
            box = _text(slide, str(item['text']), left + .15, top + .68, width - .22, height - .7, size=9.5, color=INK)
            box.text_frame.word_wrap = True


def _changes_slides(presentation, impact: dict[str, Any], part: dict[str, Any]) -> None:
    changes = part['changes']
    subtitle = f"{impact['before']['profile_name']} → {impact['after']['profile_name']}"
    slide = _slide(presentation, 'Methodology Impact — What changed', subtitle)
    if changes.get('same'):
        _text(slide, 'Both methodologies are the same: nothing that scores a test changes between them.', LEFT, CONTENT_TOP + .2, WIDTH, .5, size=14, color=INK)
        return
    tiles = [(kind, label, changes['counts'].get(kind) or 0) for kind, label in (
        ('added', 'New KPIs'), ('removed', 'Removed KPIs'), ('points', 'Other points'), ('thresholds', 'Other thresholds'),
        ('calculation', 'Other formula or filters'), ('scoring', 'Other score mapping'), ('definition', 'Other definition'),
        ('unchanged', 'Unchanged KPIs'))]
    tiles = [item for item in tiles if item[2] or item[0] in ('added', 'removed', 'unchanged')]
    width = (WIDTH - .15 * (len(tiles) - 1)) / len(tiles)
    for index, (kind, label, count) in enumerate(tiles):
        left = LEFT + index * (width + .15)
        color = {'added': themed(GAIN_COLOR), 'removed': themed(LOSS_COLOR), 'unchanged': MUTED}.get(kind, themed('#1450A8'))
        rule = _box(slide, left, CONTENT_TOP, width, .05, color)
        rule.name = 'Scoring Impact Tile'
        _text(slide, f'{count:,}', left + .08, CONTENT_TOP + .06, width - .1, .45, size=20, bold=True, color=INK)
        _text(slide, label, left + .08, CONTENT_TOP + .5, width - .1, .3, size=9, color=MUTED)
    top = CONTENT_TOP + .95
    rows = changes['categories']
    row_height = min(.3, (CONTENT_BOTTOM - .35 - top) / (len(rows) + 1))
    size = 9 if row_height >= .26 else 8
    half = WIDTH * .46
    shape, table = _table(slide, len(rows) + 1, 4, LEFT, top, half, row_height, [half - 2.55, .95, .95, .65])
    shape.name = 'Scoring Impact Table'
    for column, text in enumerate(['Points of each category', impact['before']['profile_name'], impact['after']['profile_name'], 'Diff.']):
        _cell(table.cell(0, column), text, size=size - 1, bold=True, fill=HEADER_FILL, align=PP_ALIGN.LEFT if not column else PP_ALIGN.CENTER)
        table.cell(0, column).text_frame.word_wrap = True
    for line, row in enumerate(rows, start=1):
        _cell(table.cell(line, 0), str(row['category']), size=size)
        _cell(table.cell(line, 1), _number(row['before'], 1), size=size, align=PP_ALIGN.CENTER)
        _cell(table.cell(line, 2), _number(row['after'], 1), size=size, align=PP_ALIGN.CENTER)
        _cell(table.cell(line, 3), _signed(row['delta'], 1), size=size, bold=True, align=PP_ALIGN.CENTER, color=_tone(row['delta']))
    shifted = sorted((row for row in changes['kpis'] if abs(row['delta'] or 0) >= NO_CHANGE), key=lambda row: -(row['delta'] or 0))[:16]
    if shifted:
        left = LEFT + half + .25
        _text(slide, 'The points each KPI gains or loses', left, top - .02, WIDTH - half - .25, .25, size=10, bold=True, color=INK)
        _diverging_bars(slide, [{'label': row['kpi'], 'value': row['delta']} for row in shifted], left=left, top=top + .25, width=WIDTH - half - .25,
                        height=CONTENT_BOTTOM - .1 - top - .25, label_width=2.75)
    # The KPIs that change, with what changes in each one.
    kpis = changes['kpis']
    labels = changes.get('kinds') or {}

    def details(row: dict[str, Any]) -> str:
        groups: dict[tuple, list[str]] = {}
        for item in row['details']:
            groups.setdefault((item['label'], item['before'], item['after']), []).append(item.get('environment') or '')
        texts = []
        for (label, before, after), environments in groups.items():
            places = ', '.join(name for name in environments if name)
            short_before, short_after = before if len(before) <= 44 else f'{before[:42]}…', after if len(after) <= 44 else f'{after[:42]}…'
            texts.append(f"{label}{f' ({places})' if places else ''}: {short_before} → {short_after}")
        return '; '.join(texts)

    for page in _pages(kpis, TABLE_ROWS)[:4] if kpis else []:
        slide = _slide(presentation, 'Methodology Impact — The KPIs that change', subtitle)
        row_height = min(.36, (CONTENT_BOTTOM - .1 - CONTENT_TOP) / (len(page) + 1))
        size = 8 if row_height >= .3 else 7
        shape, table = _table(slide, len(page) + 1, 5, LEFT, CONTENT_TOP, WIDTH, row_height, [3.4, 1.6, 1.6, 1.1, WIDTH - 7.7])
        shape.name = 'Scoring Impact Table'
        for column, text in enumerate(['KPI', 'Category', 'What changes', 'Points', 'Changes']):
            _cell(table.cell(0, column), text, size=size, bold=True, fill=HEADER_FILL)
        for line, row in enumerate(page, start=1):
            _cell(table.cell(line, 0), str(row['kpi']), size=size, kpi_type=row.get('kpi_type') or '')
            _cell(table.cell(line, 1), str(row['category'] or ''), size=size)
            _cell(table.cell(line, 2), ', '.join(labels.get(kind, kind) for kind in row['kinds']), size=size,
                  color=themed(GAIN_COLOR) if row['status'] == 'added' else themed(LOSS_COLOR) if row['status'] == 'removed' else INK)
            _cell(table.cell(line, 3), f"{_number(row['before'], 2)} → {_number(row['after'], 2)}", size=size)
            _cell(table.cell(line, 4), details(row), size=max(size - 1, 6))
            for column in (0, 2, 4):
                table.cell(line, column).text_frame.word_wrap = True


def _scoring_slide(presentation, impact: dict[str, Any], part: dict[str, Any], operators: list[dict[str, Any]]) -> None:
    slide = _slide(presentation, 'Methodology Impact — Scoring per operator and environment',
                   f"{impact['before']['profile_name']} → {impact['after']['profile_name']} · Tests of {impact['after']['campaign_label']}")
    rows = []
    for item in part['environments']:
        entry = part['scoring'].get(item['name']) or {}
        rows.append({'label': f"{item['label']}  (maximum {_number(entry.get('max_after'), 0)})", 'bold': item['name'] == COMBINED,
                     'cells': entry.get('operators') or {}})
    filled = _shift_table(slide, 'Environment', operators, rows, top=CONTENT_TOP, available=3.6)
    combined = (part['scoring'].get(COMBINED) or {}).get('operators') or {}
    moves = [f"{item['label']}: {cell['rank_before']} → {cell['rank_after']}" for item in operators
             if (cell := combined.get(item['operator'])) and cell.get('rank_before') and cell.get('rank_after')]
    if moves:
        _text(slide, f"Position in All Environments: {' · '.join(moves)}", LEFT, CONTENT_TOP + filled + .12, WIDTH, .3, size=11, bold=True, color=INK)
    _note(slide, 'Each difference is the points of the operator with the second methodology minus those with the first one, on the same tests.')


def _competition_slide(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    data = (part.get('competition') or {}).get(environment)
    if not data:
        return
    shown = [item for item in operators if data['relative'].get(item['operator']) is not None]
    if len(shown) < 2:
        return
    slide = _slide(presentation, 'Methodology Impact — Who it favours and who it hurts', _subtitle(impact, environment, part))
    half = WIDTH * .47
    ordered = sorted(shown, key=lambda item: -data['relative'][item['operator']])
    _text(slide, f"Each operator against the mean of the operators ({_signed(data['mean'])})", LEFT, CONTENT_TOP, half, .25, size=10, bold=True, color=INK)
    _diverging_bars(slide, [{'label': item['label'], 'value': data['relative'][item['operator']], 'color': item.get('color') or INK} for item in ordered],
                    left=LEFT, top=CONTENT_TOP + .3, width=half, height=2.2, label_width=1.2)
    left = LEFT + half + .3
    width = WIDTH - half - .3
    _text(slide, 'Head to head: how much each row gains against each column', left, CONTENT_TOP, width, .25, size=10, bold=True, color=INK)
    _heat_table(slide, 'Against', [{'label': item['label'], 'color': item.get('color')} for item in shown],
                [{'label': first['label'], 'values': [((data['matrix'].get(first['operator']) or {}).get(second['operator']) or {}).get('delta') for second in shown]} for first in shown],
                left=left, top=CONTENT_TOP + .3, width=width, available=2.2)
    labels = {item['operator']: item['label'] for item in part['operators']}
    margins = data.get('margins') or []
    if margins:
        top = CONTENT_TOP + 2.85
        row_height = min(.32, (CONTENT_BOTTOM - .4 - top - .3) / (len(margins) + 1))
        _text(slide, 'The distance between one position and the next', LEFT, top, WIDTH, .25, size=10, bold=True, color=INK)
        shape, table = _table(slide, len(margins) + 1, 5, LEFT, top + .28, WIDTH, row_height, [WIDTH - 7.2, 1.8, 1.8, 1.8, 1.8])
        shape.name = 'Scoring Impact Table'
        for column, text in enumerate(['Operators', 'Distance before', 'Distance after', 'Change', 'Share of the distance']):
            _cell(table.cell(0, column), text, size=9, bold=True, fill=HEADER_FILL, align=PP_ALIGN.LEFT if not column else PP_ALIGN.CENTER)
        for line, step in enumerate(margins, start=1):
            _cell(table.cell(line, 0), f"{labels.get(step['operator'], step['operator'])} over {labels.get(step['next'], step['next'])}", size=9, bold=True)
            _cell(table.cell(line, 1), _number(step['before'], 2), size=9, align=PP_ALIGN.CENTER)
            _cell(table.cell(line, 2), _number(step['after'], 2), size=9, align=PP_ALIGN.CENTER)
            _cell(table.cell(line, 3), _signed(step['delta']), size=9, bold=True, align=PP_ALIGN.CENTER, color=_tone(step['delta']))
            _cell(table.cell(line, 4), 'N/A' if step.get('share') is None else f"{step['share'] * 100:,.1f}%", size=9, align=PP_ALIGN.CENTER)
    _note(slide, 'If the change moved every operator alike it would change nothing between them: this is what it changes. Share of the distance: how much of it the methodology gives or takes.')


def _drivers_slides(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    data = (part.get('drivers') or {}).get(environment)
    if not data:
        return
    shown = [item for item in operators if data.get(item['operator'])]
    if not shown:
        return
    slide = _slide(presentation, 'Methodology Impact — Why each operator moves', _subtitle(impact, environment, part))
    causes = [cause for cause in CAUSES if any(abs(data[item['operator']]['causes'].get(cause) or 0) >= NO_CHANGE for item in shown)]
    if causes:
        row_height = min(.5, 2.1 / len(shown))
        label_width, total_width = 1.6, 1.0
        room = (WIDTH - label_width - total_width) / 2
        middle = LEFT + label_width + room
        extent = max((max(sum(max(data[item['operator']]['causes'].get(cause) or 0, 0) for cause in causes),
                          -sum(min(data[item['operator']]['causes'].get(cause) or 0, 0) for cause in causes)) for item in shown), default=0.0) or 1.0
        axis = _box(slide, middle - .005, CONTENT_TOP, .01, row_height * len(shown), '#C3CCD5')
        axis.name = 'Scoring Impact Axis'
        for index, item in enumerate(shown):
            y = CONTENT_TOP + index * row_height
            entry = data[item['operator']]
            _text(slide, item['label'], LEFT, y + .04, label_width - .1, row_height, size=11, bold=True, color=item.get('color') or INK, align=PP_ALIGN.RIGHT)
            right, back = middle, middle
            for cause in causes:
                value = entry['causes'].get(cause) or 0
                if abs(value) < NO_CHANGE:
                    continue
                reach = abs(value) / extent * room
                x = right if value > 0 else back - reach
                bar = _box(slide, x, y + row_height * .14, max(reach, .01), row_height * .72, themed(CAUSE_COLORS[cause]))
                bar.name = 'Scoring Impact Cause'
                if reach > .55:
                    _text(slide, _signed(value), x, y + .03, reach, row_height, size=9, bold=True, color='#FFFFFF', align=PP_ALIGN.CENTER)
                if value > 0:
                    right += reach
                else:
                    back -= reach
            _text(slide, _signed(entry['total']), LEFT + WIDTH - total_width, y + .04, total_width, row_height, size=11, bold=True, color=_tone(entry['total']), align=PP_ALIGN.RIGHT)
        legend_top = CONTENT_TOP + row_height * len(shown) + .06
        x = LEFT + label_width
        for cause in causes:
            swatch = _box(slide, x, legend_top + .05, .14, .14, themed(CAUSE_COLORS[cause]))
            swatch.name = 'Scoring Impact Legend'
            _text(slide, CAUSE_LABELS[cause], x + .18, legend_top, 3.0, .25, size=9, color=INK)
            x += 3.1
    categories = list(dict.fromkeys(name for item in shown for name, value in data[item['operator']]['categories'].items() if abs(value['delta'] or 0) >= NO_CHANGE))
    if categories:
        top = CONTENT_TOP + min(.5, 2.1 / len(shown)) * len(shown) + .4
        _text(slide, 'Per category', LEFT, top, WIDTH, .25, size=10, bold=True, color=INK)
        _heat_table(slide, 'Operator', [{'label': name} for name in categories], [
            {'label': item['label'], 'values': [(data[item['operator']]['categories'].get(name) or {}).get('delta') for name in categories]} for item in shown],
            top=top + .27, available=CONTENT_BOTTOM - .32 - top - .27)
    _note(slide, 'Points moved between KPIs: what the operator gains or loses at the same score, because a KPI is worth other points. Other thresholds, formula or filters: what scores differently with its new maximum.')


def _exposure_slide(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    data = (part.get('exposure') or {}).get(environment)
    if not data or data.get('kpis', 0) < 3:
        return
    shown = [item for item in operators if (data['operators'].get(item['operator']) or {}).get('points')][:4]
    if not shown:
        return
    slide = _slide(presentation, 'Methodology Impact — With or against the strengths of each operator', _subtitle(impact, environment, part))
    gap = .2
    columns = 2 if len(shown) > 1 else 1
    rows = math.ceil(len(shown) / columns)
    width = (WIDTH - gap * (columns - 1)) / columns
    height = (CONTENT_BOTTOM - .35 - CONTENT_TOP - gap * (rows - 1)) / rows
    for index, item in enumerate(shown):
        entry = data['operators'][item['operator']]
        left = LEFT + (index % columns) * (width + gap)
        top = CONTENT_TOP + (index // columns) * (height + gap)
        reading = 'no correlation' if entry['r'] is None else f"r = {entry['r']:+.2f}"
        _text(slide, f"{item['label']} · {reading}", left, top, width, .25, size=10, bold=True, color=item.get('color') or INK)
        _scatter(slide, entry['points'], entry.get('fit') if entry['r'] is not None else None, left=left + .1, top=top + .27, width=width - .1, height=height - .3, color=item.get('color') or INK)
    _note(slide, f"Each dot is one of the {data['kpis']} KPIs with other points: right, the methodology gives it points; up, the operator beats the mean of the operators in it. A line that rises means the points go towards its strengths.")


def _scatter(slide, points: list[dict[str, Any]], fit: dict[str, float] | None, *, left: float, top: float, width: float, height: float, color: str) -> None:
    """Dots of two measures with the lines of zero and the straight line that fits them."""
    if not points:
        return
    xs, ys = [point['x'] for point in points], [point['y'] for point in points]
    def bounds(values: list[float]) -> tuple[float, float]:
        low, high = min(*values, 0.0), max(*values, 0.0)
        margin = max((high - low) * .08, NO_CHANGE)
        return low - margin, high + margin
    (min_x, max_x), (min_y, max_y) = bounds(xs), bounds(ys)
    def px(value: float) -> float:
        return left + (value - min_x) / (max_x - min_x) * width

    def py(value: float) -> float:
        return top + (max_y - value) / (max_y - min_y) * height
    for rectangle in ((px(0) - .004, top, .008, height), (left, py(0) - .004, width, .008)):
        line = _box(slide, *rectangle, '#C3CCD5')
        line.name = 'Scoring Impact Axis'
    if fit:
        first = max(min(fit['slope'] * min_x + fit['intercept'], max_y), min_y)
        second = max(min(fit['slope'] * max_x + fit['intercept'], max_y), min_y)
        connector = slide.shapes.add_connector(1, Inches(px(min_x)), Inches(py(first)), Inches(px(max_x)), Inches(py(second)))
        connector.line.color.rgb = _rgb(color)
        connector.line.width = Pt(1.25)
        connector.name = 'Scoring Impact Fit'
    size = .1
    for point in points:
        dot = _box(slide, px(point['x']) - size / 2, py(point['y']) - size / 2, size, size, color, shape=MSO_SHAPE.OVAL)
        dot.name = 'Scoring Impact Dot'
    _text(slide, _number(min_x, 1), left, top + height - .02, .8, .2, size=7, color=MUTED)
    _text(slide, _number(max_x, 1), left + width - .8, top + height - .02, .8, .2, size=7, color=MUTED, align=PP_ALIGN.RIGHT)
    _text(slide, _number(max_y, 1), left - .08, top - .03, .6, .2, size=7, color=MUTED)


def _paged_slides(presentation, title: str, subtitle: str, first_header: str, operators: list[dict[str, Any]], rows: list[dict[str, Any]],
                  note: str, *, inverse: bool = False, pages: int = 3, extra: str = '') -> None:
    for page in _pages(rows, TABLE_ROWS)[:pages] if rows else []:
        slide = _slide(presentation, title, subtitle)
        _shift_table(slide, first_header, operators, page, top=CONTENT_TOP, inverse=inverse, extra=extra)
        _note(slide, note)


def _kpi_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{'label': row['kpi'], 'kpi_type': row.get('kpi_type'), 'cells': row['operators']} for row in rows]


def _kpi_movers_slide(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    """The KPIs that move each operator most, up to four operators on a slide."""
    rows = part['kpis'].get(environment) or []
    shown = operators[:4]
    if not rows or not shown:
        return
    slide = _slide(presentation, 'Methodology Impact — The KPIs that move each operator most', _subtitle(impact, environment, part))
    gap = .25
    columns = 2 if len(shown) > 1 else 1
    lines = math.ceil(len(shown) / columns)
    width = (WIDTH - gap * (columns - 1)) / columns
    height = (CONTENT_BOTTOM - .1 - CONTENT_TOP - gap * (lines - 1)) / lines
    for index, item in enumerate(shown):
        moved = [{'label': row['kpi'], 'value': row['operators'][item['operator']]['delta']} for row in rows
                 if (row['operators'].get(item['operator']) or {}).get('delta') is not None and abs(row['operators'][item['operator']]['delta']) >= NO_CHANGE]
        moved = sorted(sorted(moved, key=lambda row: -abs(row['value']))[:8], key=lambda row: -row['value'])
        left = LEFT + (index % columns) * (width + gap)
        top = CONTENT_TOP + (index // columns) * (height + gap)
        _text(slide, item['label'], left, top, width, .25, size=11, bold=True, color=item.get('color') or INK)
        _diverging_bars(slide, moved, left=left, top=top + .27, width=width, height=height - .3, label_width=2.6)


def render_impact_map(payload: dict[str, Any], shapes: dict[str, Any], operator: str, scale: float, *, height: int = 1100) -> bytes:
    """PNG map of an operator, on a transparent background: each area in the colour of what it gains or loses, or each City and
    route with a size and a colour."""
    from PIL import Image, ImageDraw

    boundaries, outlines = shapes.get('boundaries') or {}, shapes.get('outlines') or []
    rows = {row['name']: row for row in payload.get('rows') or []}
    rings = [(name, ring) for name, polygons in boundaries.items() for ring in polygons if len(ring) > 2]
    points = [point for _name, ring in rings for point in ring] or [point for ring in outlines for point in ring]
    places = [row for row in rows.values() if row.get('place')]
    if not rings and not outlines:
        points = [[row['place']['longitude'], row['place']['latitude']] for row in places]
    if not points:
        image = Image.new('RGBA', (height // 2, height), (255, 255, 255, 0))
        output = BytesIO()
        image.save(output, format='PNG')
        return output.getvalue()
    west, east = min(point[0] for point in points), max(point[0] for point in points)
    south, north = min(point[1] for point in points), max(point[1] for point in points)
    ratio = math.cos(math.radians((south + north) / 2))
    margin = 12
    unit = (north - south) / (height - 2 * margin) or 1e-6
    width = max(int((east - west) * ratio / unit) + 2 * margin, 200)
    image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)

    def project(x: float, y: float) -> tuple[float, float]:
        return margin + (x - west) * ratio / unit, height - margin - (y - south) / unit

    gain, loss = _hex_channels(themed(GAIN_COLOR)), _hex_channels(themed(LOSS_COLOR))
    zero = (232, 235, 238)

    def fill(value: float | None) -> tuple[int, int, int]:
        if value is None or not scale or abs(value) < NO_CHANGE:
            return zero
        share = .14 + min(1.0, math.sqrt(abs(value) / scale)) * .86
        target = gain if value > 0 else loss
        return tuple(round(255 + (channel - 255) * share) for channel in target)

    for ring in outlines:
        if len(ring) > 2:
            draw.polygon([project(x, y) for x, y in ring], fill=zero, outline=(255, 255, 255))
    for name, ring in rings:
        cell = (rows.get(name) or {}).get('cells', {}).get(operator)
        draw.polygon([project(x, y) for x, y in ring], fill=fill(cell.get('value') if cell else None), outline=(255, 255, 255))
    if not rings:
        ordered = sorted((row for row in places if row['cells'].get(operator)), key=lambda row: abs(row['cells'][operator].get('value') or 0))
        for row in ordered:
            value = row['cells'][operator].get('value') or 0
            color = (*(gain if value > 0 else loss), 215) if abs(value) >= NO_CHANGE else (*zero, 255)
            size = math.sqrt(min(1.0, abs(value) / (scale or 1)))
            route = row['place'].get('route') or []
            if row['place'].get('kind') == 'route' and route:
                draw.line([project(lon, lat) for lat, lon in route], fill=color, width=int(5 + size * 16))
            else:
                x, y = project(row['place']['longitude'], row['place']['latitude'])
                radius = 6 + size * 34
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline=(255, 255, 255))
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def _map_scale(payload: dict[str, Any], operators: list[str]) -> float:
    values = sorted(abs(row['cells'][name]['value']) for row in payload['rows'] for name in operators
                    if (row['cells'].get(name) or {}).get('value'))
    return values[min(len(values) - 1, int(len(values) * .98))] if values else 1.0


def _map_slides(presentation, impact: dict[str, Any], part: dict[str, Any], maps: dict[str, Any] | None, scoring: str, environment: str, operators: list[dict[str, Any]]) -> None:
    """A slide per area with the map of each operator, up to four on a slide, and the areas that move most of each one."""
    if not maps:
        return
    for field in MAP_FIELDS:
        if not ((maps.get('series') or {}).get(scoring) or {}).get(field):
            continue
        for relative in ((False, True) if field in RELATIVE_MAP_FIELDS and len(part['operators']) > 1 else (False,)):
            payload = impact_map(maps, part, scoring, field, environment, 'national', relative)
            if not payload['rows'] or payload['shape'] == 'none':
                continue
            shapes = map_geometry(maps, field)
            shown = [item for item in operators if payload['analysis']['operators'].get(item['operator'])][:4]
            if not shown:
                continue
            scale = _map_scale(payload, [item['operator'] for item in shown])
            slide = _slide(presentation, f"Methodology Impact — {payload['label'][:1].upper()}{payload['label'][1:]} map{' against the other operators' if relative else ''}", _subtitle(impact, environment, part))
            width = (WIDTH - .15 * (len(shown) - 1)) / len(shown)
            list_height = 1.5
            height = CONTENT_BOTTOM - .32 - CONTENT_TOP - .28 - list_height
            for index, item in enumerate(shown):
                left = LEFT + index * (width + .15)
                _text(slide, item['label'], left, CONTENT_TOP, width, .25, size=11, bold=True, color=item.get('color') or INK)
                picture = render_impact_map(payload, shapes, item['operator'], scale)
                placed = slide.shapes.add_picture(BytesIO(picture), Inches(left), Inches(CONTENT_TOP + .27), height=Inches(height))
                if placed.width > Inches(width):
                    ratio = Inches(width) / placed.width
                    placed.width, placed.height = Inches(width), int(placed.height * ratio)
                placed.name = 'Scoring Impact Map'
                summary = payload['analysis']['operators'][item['operator']]
                lines = [*(f"{entry['name']}: {_signed(entry['value'])}" for entry in (summary.get('top') or [])[:3]),
                         *(f"{entry['name']}: {_signed(entry['value'])}" for entry in (summary.get('bottom') or [])[:3])]
                box = _text(slide, '\n'.join(lines), left, CONTENT_BOTTOM - .32 - list_height, width, list_height, size=8, color=INK)
                box.text_frame.word_wrap = True
            _note(slide, f"±{scale:,.2f} National points at the strongest colour; green: it loses fewer points with the second methodology, red: more. "
                         + ('Each operator against the mean of the operators in each area. ' if relative else 'They add up to the difference of the operator. ')
                         + (payload.get('attribution') or ''))


def _spread_slide(presentation, impact: dict[str, Any], part: dict[str, Any], maps: dict[str, Any] | None, scoring: str, environment: str, operators: list[dict[str, Any]]) -> None:
    """How the impact spreads among the areas of the first map: how many move, how concentrated, and whether the operators move together."""
    field = next((name for name in ('City', 'Region', 'Cluster') if (((maps or {}).get('series') or {}).get(scoring) or {}).get(name) or part['areas'].get(name)), None)
    if field is None:
        return
    measure = 'national' if (((maps or {}).get('series') or {}).get(scoring) or {}).get(field) else 'own'
    payload = impact_map(maps, part, scoring, field, environment, measure)
    analysis = payload['analysis']
    shown = [item for item in operators if analysis['operators'].get(item['operator'])]
    if not shown:
        return
    slide = _slide(presentation, f"Methodology Impact — How the impact spreads among the {payload['label']} areas", _subtitle(impact, environment, part))
    headers = ['Operator', 'Areas up', 'Areas down', 'Total', 'Typical spread', f"Top {analysis['operators'][shown[0]['operator']]['concentration_areas']} areas", 'Against the value before', 'Worst area', 'Best area']
    widths = [1.3, .75, .85, .8, .9, .85, 1.1, (WIDTH - 6.55) / 2, (WIDTH - 6.55) / 2]
    row_height = min(.38, 2.3 / (len(shown) + 1))
    shape, table = _table(slide, len(shown) + 1, len(headers), LEFT, CONTENT_TOP, WIDTH, row_height, widths)
    shape.name = 'Scoring Impact Table'
    for column, text in enumerate(headers):
        _cell(table.cell(0, column), text, size=8, bold=True, fill=HEADER_FILL, align=PP_ALIGN.LEFT if not column else PP_ALIGN.CENTER)
        table.cell(0, column).text_frame.word_wrap = True
    for line, item in enumerate(shown, start=1):
        entry = analysis['operators'][item['operator']]
        _cell(table.cell(line, 0), item['label'], size=9, bold=True, color=item.get('color') or INK)
        values = [_number(entry['up'], 0), _number(entry['down'], 0), _signed(entry['total']), _number(entry['deviation'], 3),
                  'N/A' if entry['concentration'] is None else f"{entry['concentration'] * 100:,.0f}%",
                  'N/A' if entry['r_before'] is None else f"r = {entry['r_before']:.2f}",
                  f"{entry['worst']['name']} ({_signed(entry['worst']['value'])})", f"{entry['best']['name']} ({_signed(entry['best']['value'])})"]
        for column, text in enumerate(values, start=1):
            _cell(table.cell(line, column), text, size=8, align=PP_ALIGN.CENTER)
            table.cell(line, column).text_frame.word_wrap = True
    top = CONTENT_TOP + row_height * (len(shown) + 1) + .2
    if len(shown) > 1:
        _text(slide, 'Do the operators move together in the same areas? (correlation)', LEFT, top, WIDTH, .25, size=10, bold=True, color=INK)
        _heat_table(slide, 'Correlation', [{'label': item['label'], 'color': item.get('color')} for item in shown], [
            {'label': first['label'], 'values': [None if first['operator'] == second['operator'] else (analysis['together'].get(first['operator']) or {}).get(second['operator']) for second in shown]}
            for first in shown], top=top + .27, available=CONTENT_BOTTOM - .35 - top - .27, scale=1.0)
    _note(slide, 'Near +1: the same areas move for both operators, so it comes from the tests of the area. Near 0: each operator moves in its own areas.')


def _area_category_slides(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    levels = list(part.get('area_categories') or {})
    if not levels:
        return
    level = levels[-1]
    rows = part['area_categories'][level].get(environment) or []
    for item in operators[:4]:
        name = item['operator']
        categories = [category for category in dict.fromkeys(key for row in rows for key in row['categories'])
                      if any(abs(row['categories'][category].get(name) or 0) >= NO_CHANGE for row in rows if category in row['categories'])]
        ranked = sorted(((max((abs(row['categories'].get(category, {}).get(name) or 0) for category in categories), default=0.0), row) for row in rows), key=lambda pair: -pair[0])
        ranked = [row for peak, row in ranked if peak >= NO_CHANGE][:TABLE_ROWS + 4]
        if not categories or not ranked:
            continue
        slide = _slide(presentation, f"Methodology Impact — Categories per {level}: {item['label']}", _subtitle(impact, environment, part))
        _heat_table(slide, level, [{'label': category} for category in categories],
                    [{'label': row['area'], 'values': [row['categories'].get(category, {}).get(name) for category in categories]} for row in ranked], top=CONTENT_TOP)
        _note(slide, 'The difference of each category in the scoring of each area, the areas that move most first.')


def _area_slides(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    labels = {item['operator']: item['label'] for item in part['operators']}
    for level, environments in (part.get('areas') or {}).items():
        rows = environments.get(environment) or []
        if not rows:
            continue

        def leader(row: dict[str, Any]) -> str:
            first, second = labels.get(row['leader_before'], row['leader_before']), labels.get(row['leader_after'], row['leader_after'])
            return second or '' if first == second else f'{first} → {second}'
        shown = [{'label': row['area'], 'bold': True, 'cells': row['operators'], 'extra': leader(row)} for row in rows[:AREA_ROWS]]
        swaps = sum(row['leader_before'] != row['leader_after'] for row in rows)
        note = (f"The {len(shown)} of {len(rows)} {level} areas that move most; the leader changes in {swaps}. "
                'Scored on the whole country; All Environments scales the environments measured in an area to the full maximum.')
        _paged_slides(presentation, f'Methodology Impact — Scoring per {level}', _subtitle(impact, environment, part), level, operators, shown, note, pages=1, extra='Leader')


def _serving_slides(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    fields = {'Vendor': 'Vendor of the serving cell', 'Site Type': 'Kind of site of the serving cell'}
    subtitle = _subtitle(impact, environment, part)
    for field, label in fields.items():
        rows = [row for row in ((part.get('serving') or {}).get(field) or {}).get(environment) or [] if row['peak'] >= NO_CHANGE]
        _paged_slides(presentation, f'Methodology Impact — {label}', subtitle, label, operators, [{'label': row['name'], 'bold': True, 'cells': row['operators']} for row in rows],
                      'What the operator gains (positive) or loses of its National scoring in the tests served by each one; beside it, the National points lost with each methodology.', pages=1)


def _gap_slides(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    gap = part['gap'].get(environment)
    if not gap:
        return
    compared = [item for item in operators if not item.get('is_reference')]
    if not compared:
        return
    reference = next((item['label'] for item in part['operators'] if item.get('is_reference')), part.get('reference') or '')
    rows = [{'label': 'Total GAP', 'bold': True, 'cells': gap['total']},
            *({'label': row['category'], 'cells': row['operators']} for row in gap['categories'])]
    note = 'Operator minus reference, before → after; the bar shows how much the GAP moves. ⇄: the operator changes side (ahead of the reference to behind it, or the other way round).'
    subtitle = _subtitle(impact, environment, part)
    _paged_slides(presentation, f'Methodology Impact — GAP against {reference}', subtitle, 'Category', compared, rows, note, pages=1)
    moved = [row for row in gap['kpis'] if row['peak'] >= NO_CHANGE]
    _paged_slides(presentation, f'Methodology Impact — KPIs whose GAP against {reference} moves most', subtitle, 'KPI', compared, _kpi_rows(moved), note, pages=1)


def _points_slides(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    lost = part['points_lost'].get(environment)
    if not lost:
        return
    subtitle = _subtitle(impact, environment, part)
    shown = [item for item in operators if lost['operators'].get(item['operator'])]
    if shown:
        slide = _slide(presentation, 'Methodology Impact — Points Lost', subtitle)
        kinds = [kind for kind in lost['kinds'] if any((lost['operators'][item['operator']]['parts_before'].get(kind['key']) or lost['operators'][item['operator']]['parts_after'].get(kind['key']))
                                                       for item in shown)]
        peak = max([1.0, *(value for item in shown for value in (lost['operators'][item['operator']]['before'] or 0, lost['operators'][item['operator']]['after'] or 0))])
        row_height = min(.82, (CONTENT_BOTTOM - .7 - CONTENT_TOP) / len(shown))
        label_width, total_width = 1.8, 2.3
        bar_width = WIDTH - label_width - total_width
        for index, item in enumerate(shown):
            top = CONTENT_TOP + index * row_height
            row = lost['operators'][item['operator']]
            _text(slide, item['label'], LEFT, top + .02, label_width - .1, row_height - .1, size=11, bold=True, color=item.get('color') or INK)
            for offset, parts in enumerate((row['parts_before'], row['parts_after'])):
                left = LEFT + label_width
                for kind in kinds:
                    value = parts.get(kind['key']) or 0
                    if value <= 0:
                        continue
                    width = value / peak * bar_width
                    segment = _box(slide, left, top + .03 + offset * (row_height * .4), max(width, .01), row_height * .36, themed(STAKE_COLORS[kind['key']]))
                    segment.name = 'Scoring Impact Stack'
                    if width > .45:
                        segment.text_frame.text = f'{value:,.0f}'
                        segment.text_frame.paragraphs[0].runs[0].font.size = Pt(8)
                        segment.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
                    left += width
            _text(slide, f"{_signed(row['delta'])}  ({_number(row['before'])} → {_number(row['after'])} lost)", LEFT + label_width + bar_width + .1, top + .05, total_width - .1, .4,
                  size=10, bold=True, color=_tone(row['delta'], True))
        legend_left = LEFT
        for kind in kinds:
            swatch = _box(slide, legend_left, CONTENT_BOTTOM - .57, .14, .14, themed(STAKE_COLORS[kind['key']]))
            swatch.name = 'Scoring Impact Legend'
            _text(slide, kind['label'], legend_left + .18, CONTENT_BOTTOM - .62, 2.6, .25, size=9, color=INK)
            legend_left += 2.9
        _note(slide, 'In each operator, the upper bar is the first methodology and the lower one the second. More points lost are shown in the colour of a loss.')
    note = 'More points lost are shown in the colour of a loss. The points lost of a KPI are its maximum minus the points scored, so they also move when the methodology gives it another maximum.'
    rows = [{'label': row['category'], 'cells': row['operators']} for row in lost['categories']]
    _paged_slides(presentation, 'Methodology Impact — Points lost per category', subtitle, 'Category', operators, rows, note, inverse=True, pages=1)
    moved = [row for row in lost['kpis'] if row['peak'] >= NO_CHANGE]
    _paged_slides(presentation, 'Methodology Impact — KPIs whose points lost move most', subtitle, 'KPI', operators, _kpi_rows(moved), note, inverse=True, pages=1)


def _stability_slide(presentation, impact: dict[str, Any], part: dict[str, Any], operators: list[dict[str, Any]]) -> None:
    data = part.get('stability') or {}
    campaigns = sorted((item for item in data.get('campaigns') or [] if item.get('comparable')), key=lambda item: _campaign_key(item['campaign']))
    left_out = [item for item in data.get('campaigns') or [] if not item.get('comparable')]
    if len(campaigns) < 2:
        return
    slide = _slide(presentation, 'Methodology Impact — The same change on the tests of other campaigns', f"{impact['before']['profile_name']} → {impact['after']['profile_name']} · All Environments")
    chart_data = CategoryChartData()
    chart_data.categories = [item['label'] for item in campaigns]
    for item in operators:
        chart_data.add_series(item['label'], [campaign['operators'].get(item['operator']) for campaign in campaigns])
    shape = slide.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(LEFT), Inches(CONTENT_TOP), Inches(WIDTH), Inches(3.0), chart_data)
    shape.name = 'Scoring Impact Campaigns'
    chart = shape.chart
    chart.has_title = False
    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    chart.font.size = Pt(10)
    chart.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    chart.value_axis.major_gridlines.format.line.color.rgb = _rgb('#E3E6E9')
    for series, item in zip(chart.plots[0].series, operators):
        color = _rgb(item.get('color') or INK)
        series.format.line.color.rgb = color
        series.format.line.width = Pt(2)
        series.smooth = False
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = color
    summary = data.get('summary') or {}
    rows = [item for item in operators if summary.get(item['operator'])]
    if rows:
        top = CONTENT_TOP + 3.1
        row_height = min(.27, (CONTENT_BOTTOM - .4 - top) / (len(rows) + 1))
        table_shape, table = _table(slide, len(rows) + 1, 6, LEFT, top, WIDTH, row_height, [WIDTH - 7.5, 1.5, 1.5, 1.5, 1.5, 1.5])
        table_shape.name = 'Scoring Impact Table'
        for column, text in enumerate(['Operator', 'Campaigns up', 'Campaigns down', 'Mean', 'From', 'To']):
            _cell(table.cell(0, column), text, size=9, bold=True, fill=HEADER_FILL, align=PP_ALIGN.LEFT if not column else PP_ALIGN.CENTER)
        for line, item in enumerate(rows, start=1):
            entry = summary[item['operator']]
            _cell(table.cell(line, 0), item['label'], size=9, bold=True, color=item.get('color') or INK)
            for column, text in enumerate([_number(entry['up'], 0), _number(entry['down'], 0), _signed(entry['mean']), _signed(entry['low']), _signed(entry['high'])], start=1):
                _cell(table.cell(line, column), text, size=9, align=PP_ALIGN.CENTER)
    missing = list(dict.fromkeys(name for item in left_out for name in item.get('missing') or []))
    _note(slide, 'What the methodology changes on the same tests of each campaign: not how the network changes between them.'
          + (f" {', '.join(item['label'] for item in left_out)} cannot be compared" + (f": no tests of {', '.join(missing[:3])}." if missing else '.') if left_out else ''))


def _campaign_key(value: str) -> tuple:
    from src.modules.column_names import campaign_sort_key
    return campaign_sort_key(value), value


def export_impact_powerpoint(impact: dict[str, Any], template_path: Path, operator_mapping_groups: list[dict[str, Any]] | None = None, *,
                             scoring: str = 'best_network', environment: str = COMBINED, operators: list[str] | None = None,
                             panels: Any = None, theme: str = DEFAULT_THEME, maps: dict[str, Any] | None = None) -> bytes:
    """The panels of the Methodology Impact that the workspace exports (Scoring Export Panels), with the operators chosen in the
    page (``operators``, every one without it) and, in the Focus Operators panels, its Focus operators."""
    if not template_path.is_file():
        raise ValueError('The configured CDR PowerPoint template is missing.')
    if not impact.get('scorings'):
        raise ValueError('Both campaigns are scored with the same methodology: there is no impact to export.')
    settings = normalize_export_panels(panels)['impact']
    part, name, shown_environment = impact_part(impact, scoring, environment)
    chosen = [item for item in part['operators'] if not operators or item['operator'] in operators] or part['operators']
    focus = focus_matcher(focus_operators(operator_mapping_groups or []), [item['operator'] for item in part['operators']])

    def of_panel(key: str) -> list[dict[str, Any]]:
        if settings[key]['operators'] != FOCUS_OPERATORS:
            return chosen
        return [item for item in chosen if focus(item['operator'], item['label'])] or chosen

    panels_in_order: list[tuple[str, Callable[[], None]]] = []
    with use_theme(theme):
        presentation = Presentation(template_path)
        _remove_all_slides(presentation)
        _cover(presentation, impact, part, name)
        _conclusions_slide(presentation, impact, part, shown_environment)
        subtitle = _subtitle(impact, shown_environment, part)

        def categories() -> None:
            rows = [{'label': row['category'], 'cells': row['operators']} for row in part['categories'].get(shown_environment) or []]
            total = (part['scoring'].get(shown_environment) or {}).get('operators') or {}
            _paged_slides(presentation, 'Methodology Impact — Per category', subtitle, 'Category', of_panel('categories'),
                          [*rows, {'label': 'Total', 'bold': True, 'cells': total}],
                          'The points of each category with both methodologies; the colour and bar show the difference.', pages=1)

        def kpis() -> None:
            rows = [row for row in part['kpis'].get(shown_environment) or [] if row.get('kinds') or row['peak'] >= NO_CHANGE]
            _kpi_movers_slide(presentation, impact, part, shown_environment, of_panel('kpis'))
            _paged_slides(presentation, 'Methodology Impact — KPIs affected', subtitle, 'KPI', of_panel('kpis'), _kpi_rows(rows),
                          'The KPIs that move most first. A KPI one methodology does not have counts none there.')

        panels_in_order = [
            ('changes', lambda: _changes_slides(presentation, impact, part)),
            ('scoring', lambda: _scoring_slide(presentation, impact, part, of_panel('scoring'))),
            ('competition', lambda: _competition_slide(presentation, impact, part, shown_environment, of_panel('competition'))),
            ('drivers', lambda: _drivers_slides(presentation, impact, part, shown_environment, of_panel('drivers'))),
            ('exposure', lambda: _exposure_slide(presentation, impact, part, shown_environment, of_panel('exposure'))),
            ('categories', categories), ('kpis', kpis),
            ('maps', lambda: _map_slides(presentation, impact, part, maps, name, shown_environment, of_panel('maps'))),
            ('spread', lambda: _spread_slide(presentation, impact, part, maps, name, shown_environment, of_panel('spread'))),
            ('area_categories', lambda: _area_category_slides(presentation, impact, part, shown_environment, of_panel('area_categories'))),
            ('areas', lambda: _area_slides(presentation, impact, part, shown_environment, of_panel('areas'))),
            ('serving', lambda: _serving_slides(presentation, impact, part, shown_environment, of_panel('serving'))),
            ('gap', lambda: _gap_slides(presentation, impact, part, shown_environment, of_panel('gap'))),
            ('points', lambda: _points_slides(presentation, impact, part, shown_environment, of_panel('points'))),
            ('stability', lambda: _stability_slide(presentation, impact, part, of_panel('stability'))),
        ]
        for key, add in panels_in_order:
            if settings[key]['exportable']:
                add()
        report_structure.finish(presentation)
        output = BytesIO()
        presentation.save(output)
    return output.getvalue()


def impact_filename(impact: dict[str, Any], stamp: Any, extension: str) -> str:
    text = (f"{stamp:%Y%m%d_%H%M%S} - Scoring & GAP Analysis - Methodology Impact - {impact.get('nr_mode') or ''} - "
            f"{impact['before']['profile_name']} vs {impact['after']['profile_name']} - {impact['after']['campaign_label']}")
    return f"{re.sub(r'[\\/:*?\"<>|]+', '-', text)[:200].rstrip(' .-')}.{extension}"


__all__ = ['MEASURES', 'export_impact_csv', 'export_impact_powerpoint', 'impact_filename', 'impact_part', 'render_impact_map']
