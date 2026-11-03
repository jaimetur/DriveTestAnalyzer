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
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from src.modules import report_structure
from src.modules.cdr_reporting import _named_slide_layout, _remove_all_slides, _set_structural_slide_text
from src.modules.operator_roles import focus_operators
from src.modules.scoring_export_panels import FOCUS_OPERATORS, normalize_export_panels
from src.modules.scoring_exports import _slide, _tag_slides, focus_matcher
from src.modules.scoring_impact_analysis import CAUSE_LABELS, CAUSES
from src.modules.scoring_impact_maps import MAP_FIELDS, MEASURES, impact_map, map_geometry
from src.modules.scoring_insight_slides import _box, _cell, _table
from src.modules.scoring_summary_slides import (
    CONTENT_BOTTOM, CONTENT_TOP, GAIN_COLOR, INK, LOSS_COLOR, MAX_TABLE_ROWS, MUTED, STAKE_COLORS, _pages, _text,
)
from src.modules.scoring_themes import DEFAULT_THEME, themed, use_theme

COMBINED = 'Combined'
LEFT, WIDTH = .45, 12.43
TABLE_ROWS = 14
AREA_ROWS = MAX_TABLE_ROWS - 8
HEADER_FILL = '#E9ECEF'
NO_CHANGE = .005
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
    for environment, entry in part['drivers'].items():
        for operator, item in entry.items():
            for cause, value in item['causes'].items():
                row('Causes', environment, operator, 'Cause', CAUSE_LABELS[cause], '', '', value)
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
    conclusions = part.get('conclusions') or {}
    facts = conclusions.get('facts') or []
    if not conclusions.get('headline'):
        return
    slide = _slide(presentation, 'Methodology Impact — What stands out', _subtitle(impact, environment, part))
    _text(slide, conclusions['headline'], LEFT, CONTENT_TOP, WIDTH, .5, size=20, bold=True, color=INK)
    columns = 3
    rows = max(math.ceil(len(facts) / columns), 1)
    gap = .16
    top = CONTENT_TOP + .65
    width = (WIDTH - gap * (columns - 1)) / columns
    height = min(1.1, (CONTENT_BOTTOM - .1 - top - gap * (rows - 1)) / rows)
    for index, fact in enumerate(facts):
        left = LEFT + (index % columns) * (width + gap)
        y = top + (index // columns) * (height + gap)
        card = _box(slide, left, y, width, height, '#F6F8FA')
        card.name = 'Scoring Impact Conclusion'
        color = {'gain': themed(GAIN_COLOR), 'loss': themed(LOSS_COLOR)}.get(fact.get('tone'), themed('#1450A8'))
        rule = _box(slide, left, y, .06, height, color)
        rule.name = 'Scoring Impact Rule'
        _text(slide, str(fact['title']).upper(), left + .15, y + .08, width - .2, .24, size=9, bold=True, color=MUTED)
        box = _text(slide, str(fact['text']), left + .15, y + .34, width - .22, height - .38, size=13, bold=True, color=INK)
        box.text_frame.word_wrap = True


def _changes_slides(presentation, impact: dict[str, Any], part: dict[str, Any]) -> None:
    changes = part['changes']
    subtitle = f"{impact['before']['profile_name']} → {impact['after']['profile_name']}"
    slide = _slide(presentation, 'Methodology Impact — What changed', subtitle)
    if changes.get('same'):
        _text(slide, 'Both methodologies are the same: nothing that scores a test changes between them.', LEFT, CONTENT_TOP + .2, WIDTH, .5, size=14, color=INK)
        return
    tiles = [(kind, label, changes['counts'].get(kind) or 0) for kind, label in (
        ('added', 'New KPIs'), ('removed', 'Removed KPIs'), ('points', 'Points changed'), ('thresholds', 'Thresholds changed'),
        ('calculation', 'Formula or filters changed'), ('scoring', 'Score mapping changed'), ('definition', 'Definition changed'),
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
        _diverging_bars(slide, [{'label': f"{row['category']} · {row['kpi']}", 'value': row['delta']} for row in shifted], left=left, top=top + .25, width=WIDTH - half - .25,
                        height=CONTENT_BOTTOM - .1 - top - .25, label_width=3.4)
    # The KPIs that change, with what changes in each one.
    kpis = changes['kpis']
    labels = changes.get('kinds') or {}

    def details(row: dict[str, Any], side: str) -> str:
        groups: dict[tuple, list[str]] = {}
        for item in row['details']:
            groups.setdefault((item['label'], item['before'], item['after']), []).append(item.get('environment') or '')
        texts = []
        for (label, *values), environments in groups.items():
            value = values[0 if side == 'before' else 1]
            places = ', '.join(name for name in environments if name)
            texts.append(f"{label}{f' ({places})' if places else ''}: {value if len(value) <= 60 else f'{value[:58]}…'}")
        return '; '.join(texts)

    first, second = impact['before']['profile_name'], impact['after']['profile_name']
    for page in _pages(kpis, TABLE_ROWS) if kpis else []:
        slide = _slide(presentation, 'Methodology Impact — The KPIs that change', subtitle)
        row_height = min(.36, (CONTENT_BOTTOM - .1 - CONTENT_TOP) / (len(page) + 1))
        size = 8 if row_height >= .3 else 7
        side_width = (WIDTH - 6.0) / 2
        shape, table = _table(slide, len(page) + 1, 6, LEFT, CONTENT_TOP, WIDTH, row_height, [2.7, 1.2, 1.0, 1.1, side_width, side_width])
        shape.name = 'Scoring Impact Table'
        for column, text in enumerate(['KPI', 'Category', 'What changes', 'Points', first, second]):
            _cell(table.cell(0, column), text, size=size, bold=True, fill=HEADER_FILL)
        for line, row in enumerate(page, start=1):
            _cell(table.cell(line, 0), str(row['kpi']), size=size, kpi_type=row.get('kpi_type') or '')
            _cell(table.cell(line, 1), str(row['category'] or ''), size=size)
            _cell(table.cell(line, 2), ', '.join(labels.get(kind, kind) for kind in row['kinds']), size=size,
                  color=themed(GAIN_COLOR) if row['status'] == 'added' else themed(LOSS_COLOR) if row['status'] == 'removed' else INK)
            _cell(table.cell(line, 3), f"{_number(row['before'], 2)} → {_number(row['after'], 2)}", size=size)
            _cell(table.cell(line, 4), 'Not in this methodology' if row['status'] == 'added' else details(row, 'before'), size=max(size - 1, 6))
            _cell(table.cell(line, 5), 'Not in this methodology' if row['status'] == 'removed' else details(row, 'after'), size=max(size - 1, 6))
            for column in (0, 1, 2, 4, 5):
                table.cell(line, column).text_frame.word_wrap = True


def _scoring_slide(presentation, impact: dict[str, Any], part: dict[str, Any], operators: list[dict[str, Any]]) -> None:
    slide = _slide(presentation, 'Methodology Impact — Scoring per operator and environment',
                   f"{impact['before']['profile_name']} → {impact['after']['profile_name']} · Tests of {impact['after']['campaign_label']}")
    combined = (part['scoring'].get(COMBINED) or {}).get('operators') or {}
    shown = sorted((item for item in operators if combined.get(item['operator'])), key=lambda item: combined[item['operator']].get('rank_after') or 99)[:8]
    top = CONTENT_TOP
    if shown:
        gap = .12
        width = (WIDTH - gap * (len(shown) - 1)) / len(shown)
        for index, item in enumerate(shown):
            cell = combined[item['operator']]
            left = LEFT + index * (width + gap)
            card = _box(slide, left, top, width, 1.25, '#F6F8FA')
            card.name = 'Scoring Impact Card'
            rule = _box(slide, left, top, width, .05, item.get('color') or INK)
            rule.name = 'Scoring Impact Rule'
            position = f"{cell['rank_before']} → {cell['rank_after']}" if cell.get('rank_before') != cell.get('rank_after') else str(cell.get('rank_after') or '')
            _text(slide, f"{item['label']}  ·  {position}", left + .07, top + .09, width - .1, .26, size=10, bold=True, color=item.get('color') or INK)
            _text(slide, _signed(cell.get('delta')), left + .07, top + .36, width - .1, .5, size=20, bold=True, color=_tone(cell.get('delta')))
            _text(slide, f"{_number(cell.get('before'))} → {_number(cell.get('after'))}", left + .07, top + .9, width - .1, .26, size=10, color=MUTED)
        top += 1.42
    rows = []
    for item in part['environments']:
        entry = part['scoring'].get(item['name']) or {}
        rows.append({'label': f"{item['label']}  (maximum {_number(entry.get('max_after'), 0)})", 'bold': item['name'] == COMBINED,
                     'cells': entry.get('operators') or {}})
    _shift_table(slide, 'Environment', operators, rows, top=top)
    _note(slide, 'Each difference is the points of the operator with the second methodology minus those with the first one, on the same tests.')


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
        row_height = min(.6, 3.6 / len(shown))
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
    _note(slide, 'Points moved between KPIs: what the operator gains or loses at the same score, because a KPI is worth other points. Other thresholds, formula or filters: what scores differently with its new maximum.')


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
        moved = [{'label': f"{row['category']} · {row['kpi']}", 'value': row['operators'][item['operator']]['delta']} for row in rows
                 if (row['operators'].get(item['operator']) or {}).get('delta') is not None and abs(row['operators'][item['operator']]['delta']) >= NO_CHANGE]
        moved = sorted(sorted(moved, key=lambda row: -abs(row['value']))[:8], key=lambda row: -row['value'])
        left = LEFT + (index % columns) * (width + gap)
        top = CONTENT_TOP + (index // columns) * (height + gap)
        _text(slide, item['label'], left, top, width, .25, size=11, bold=True, color=item.get('color') or INK)
        _diverging_bars(slide, moved, left=left, top=top + .27, width=width, height=height - .3, label_width=3.4)


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
        payload = impact_map(maps, part, scoring, field, environment, 'national')
        if not payload['rows'] or payload['shape'] == 'none':
            continue
        shapes = map_geometry(maps, field)
        shown = [item for item in operators if payload['analysis']['operators'].get(item['operator'])][:4]
        if not shown:
            continue
        scale = _map_scale(payload, [item['operator'] for item in shown])
        slide = _slide(presentation, f"Methodology Impact — {payload['label'][:1].upper()}{payload['label'][1:]} map", _subtitle(impact, environment, part))
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
                     + 'They add up to the difference of the operator. ' + (payload.get('attribution') or ''))


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


def _gap_slides(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    gap = part['gap'].get(environment)
    if not gap:
        return
    compared = [item for item in operators if not item.get('is_reference')]
    if not compared:
        return
    reference = next((item['label'] for item in part['operators'] if item.get('is_reference')), part.get('reference') or '')
    rows = [{'label': 'Total GAP', 'bold': True, 'cells': gap['total']},
            *({'label': row['category'], 'cells': row['operators']} for row in gap['categories'] if row['peak'] >= NO_CHANGE)]
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
    rows = [{'label': row['category'], 'cells': row['operators']} for row in lost['categories'] if row['peak'] >= NO_CHANGE]
    _paged_slides(presentation, 'Methodology Impact — Points lost per category', subtitle, 'Category', operators, rows, note, inverse=True, pages=1)
    moved = [row for row in lost['kpis'] if row['peak'] >= NO_CHANGE]
    _paged_slides(presentation, 'Methodology Impact — KPIs whose points lost move most', subtitle, 'KPI', operators, _kpi_rows(moved), note, inverse=True, pages=1)


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
            rows = [{'label': row['category'], 'cells': row['operators']} for row in part['categories'].get(shown_environment) or [] if row['peak'] >= NO_CHANGE]
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
            ('scoring', lambda: (_scoring_slide(presentation, impact, part, of_panel('scoring')), _drivers_slides(presentation, impact, part, shown_environment, of_panel('scoring')))),
            ('categories', categories), ('kpis', kpis),
            ('maps', lambda: _map_slides(presentation, impact, part, maps, name, shown_environment, of_panel('maps'))),
            ('areas', lambda: _area_slides(presentation, impact, part, shown_environment, of_panel('areas'))),
            ('gap', lambda: _gap_slides(presentation, impact, part, shown_environment, of_panel('gap'))),
            ('points', lambda: _points_slides(presentation, impact, part, shown_environment, of_panel('points'))),
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
