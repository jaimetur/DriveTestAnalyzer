"""The CSV and the PowerPoint of the Methodology Impact (see scoring_impact), panel by panel as the tab shows them. The deck is
composed like every Scoring document (bundle_report_templates.module_document); the workspace chooses its panels and their
operators in Scoring Export Panels.
"""
from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Callable, Iterable

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Pt

from src.modules import report_structure
from src.modules.cdr_reporting import _named_slide_layout, _remove_all_slides, _set_structural_slide_text
from src.modules.scoring_export_panels import FOCUS_OPERATORS, normalize_export_panels
from src.modules.scoring_exports import _slide, _tag_slides, focus_matcher
from src.modules.scoring_insight_slides import _box, _cell, _table
from src.modules.scoring_summary_slides import (
    CONTENT_BOTTOM, CONTENT_TOP, GAIN_COLOR, INK, LOSS_COLOR, MAX_TABLE_ROWS, MUTED, STAKE_COLORS, _pages, _text,
)
from src.modules.scoring_themes import DEFAULT_THEME, themed, use_theme
from src.modules.operator_roles import focus_operators

COMBINED = 'Combined'
LEFT, WIDTH = .45, 12.43
TABLE_ROWS = 14
AREA_ROWS = MAX_TABLE_ROWS - 8
HEADER_FILL = '#E9ECEF'
NO_CHANGE = .005


def _number(value: Any, digits: int = 1) -> str:
    return 'N/A' if value is None else f'{value:,.{digits}f}'


def _signed(value: Any, digits: int = 2) -> str:
    if value is None:
        return 'N/A'
    return f'{abs(value):,.{digits}f}' if abs(value) < 10 ** -digits / 2 else f'{value:+,.{digits}f}'


def _environment_label(part: dict[str, Any], environment: str) -> str:
    return next((item['label'] for item in part['environments'] if item['name'] == environment), environment)


def impact_part(impact: dict[str, Any], scoring: str, environment: str) -> tuple[dict[str, Any], str]:
    """The panels of a scoring and the environment to show (All Environments when it has not that one)."""
    scorings = impact['scorings']
    part = scorings.get(scoring) or scorings.get('best_network') or next(iter(scorings.values()))
    names = [item['name'] for item in part['environments']]
    if environment in names:
        return part, environment
    return part, COMBINED if COMBINED in names else names[0]


# ----------------------------------------------------------------------------------------------------------------------
# CSV
# ----------------------------------------------------------------------------------------------------------------------

def export_impact_csv(impact: dict[str, Any], scoring: str = 'best_network') -> str:
    """Every value of the panels, one per row: the panel, environment, operator and item, before, after and their difference."""
    part, _environment = impact_part(impact, scoring, COMBINED)
    labels = {item['operator']: item['label'] for item in part['operators']}
    names = {item['name']: item['label'] for item in part['environments']}
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Panel', 'Environment', 'Operator', 'Level', 'Item', 'First methodology', 'Second methodology', 'Before', 'After', 'Difference'])
    first, second = impact['before']['profile_name'], impact['after']['profile_name']

    def write(panel: str, environment: str, cells: dict[str, Any], level: str, item: str) -> None:
        for operator, cell in cells.items():
            writer.writerow([panel, names.get(environment, environment), labels.get(operator, operator), level, item, first, second,
                             cell.get('before'), cell.get('after'), cell.get('delta')])

    for row in part['changes']['kpis']:
        for detail in row['details']:
            writer.writerow(['What changed', detail.get('environment') or '', '', detail['label'], row['kpi'], first, second,
                             detail['before'], detail['after'], ''])
    for environment, entry in part['scoring'].items():
        write('Scoring', environment, entry['operators'], 'Total', 'Total')
    for environment, rows in part['categories'].items():
        for row in rows:
            write('Category', environment, row['operators'], 'Category', row['category'])
    for environment, rows in part['kpis'].items():
        for row in rows:
            write('KPI', environment, row['operators'], row['category'], row['kpi'])
    for level, environments in part['areas'].items():
        for environment, rows in environments.items():
            for row in rows:
                write('Geographical area', environment, row['operators'], level, row['area'])
    for environment, entry in part['gap'].items():
        write('GAP', environment, entry['total'], 'Total', 'Total')
        for row in entry['categories']:
            write('GAP', environment, row['operators'], 'Category', row['category'])
        for row in entry['kpis']:
            write('GAP', environment, row['operators'], row['category'], row['kpi'])
    for environment, entry in part['points_lost'].items():
        write('Points Lost', environment, entry['operators'], 'Total', 'Total')
        for row in entry['categories']:
            write('Points Lost', environment, row['operators'], 'Category', row['category'])
        for row in entry['kpis']:
            write('Points Lost', environment, row['operators'], row['category'], row['kpi'])
    if part.get('bridge') and impact.get('earlier'):
        earlier = impact['earlier']['campaign_label']
        for environment, rows in part['bridge'].items():
            for operator, row in rows.items():
                writer.writerow(['Network and methodology', names.get(environment, environment), labels.get(operator, operator), earlier,
                                 impact['after']['campaign_label'], first, second, row['earlier'], row['latest'], row['total']])
                writer.writerow(['Network and methodology', names.get(environment, environment), labels.get(operator, operator), 'The network changed',
                                 '', first, second, '', '', row['network']])
                writer.writerow(['Network and methodology', names.get(environment, environment), labels.get(operator, operator), 'The methodology changed',
                                 '', first, second, '', '', row['methodology']])
    return output.getvalue()


# ----------------------------------------------------------------------------------------------------------------------
# PowerPoint
# ----------------------------------------------------------------------------------------------------------------------

def _tone(delta: Any, inverse: bool = False) -> str:
    if delta is None or abs(delta) < NO_CHANGE:
        return MUTED
    return themed(GAIN_COLOR) if (delta > 0) != inverse else themed(LOSS_COLOR)


def _shift_table(slide, first_header: str, operators: list[dict[str, Any]], rows: list[dict[str, Any]], *, top: float, inverse: bool = False,
                 available: float | None = None, extra: str = '') -> float:
    """A table of a label and a cell per operator (its difference, the value before and after, and a bar either side of zero
    against the largest difference of the table). What it fills is returned."""
    available = available if available is not None else CONTENT_BOTTOM - .3 - top
    count = len(rows) + 1
    row_height = min(.62, max(.22, available / count))
    size = 11 if row_height >= .55 else 10 if row_height >= .42 else 9 if row_height >= .36 else 8 if row_height >= .28 else 7
    label_width = max(2.6, WIDTH - 1.55 * len(operators) - (1.3 if extra else 0))
    label_width = min(label_width, 5.2)
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
             f"Tests of {impact['after']['campaign_label']} · {impact.get('nr_mode') or ''} · GAP reference: {reference}"]
    if impact.get('earlier'):
        lines.append(f"From {impact['earlier']['campaign_label']} to {impact['after']['campaign_label']}")
    title = 'Methodology Impact' + (' — Most Reliable Network' if scoring == 'most_reliable' else '')
    _set_structural_slide_text(slide, title, '\n'.join(lines))


def _takeaways_slide(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str) -> None:
    notes = [*part.get('takeaways', []), *impact.get('notes', [])]
    if not notes:
        return
    slide = _slide(presentation, 'Methodology Impact — What stands out', _subtitle(impact, environment, part))
    top = CONTENT_TOP + .1
    for text in notes[:8]:
        marker = _box(slide, LEFT, top + .06, .09, .09, themed('#1450A8'))
        marker.name = 'Scoring Impact Marker'
        _text(slide, text, LEFT + .22, top - .02, WIDTH - .3, .5, size=14, color=INK)
        top += .62


def _changes_slides(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str) -> None:
    changes = part['changes']
    subtitle = f"{impact['before']['profile_name']} → {impact['after']['profile_name']}"
    if impact.get('same_methodology') or changes.get('same'):
        slide = _slide(presentation, 'Methodology Impact — What changed', subtitle)
        _text(slide, f"Both campaigns are scored with {impact['before']['profile_name']}: the methodology does not change between them."
              if impact.get('same_methodology') else 'Both methodologies are the same: nothing that scores a test changes between them.',
              LEFT, CONTENT_TOP + .2, WIDTH, .5, size=14, color=INK)
        return
    slide = _slide(presentation, 'Methodology Impact — What changed', subtitle)
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
    shape, table = _table(slide, len(rows) + 1, 4, LEFT, top, WIDTH, row_height, [WIDTH - 4.5, 1.5, 1.5, 1.5])
    shape.name = 'Scoring Impact Table'
    for column, text in enumerate(['Points of each category', impact['before']['profile_name'], impact['after']['profile_name'], 'Difference']):
        _cell(table.cell(0, column), text, size=size, bold=True, fill=HEADER_FILL, align=PP_ALIGN.LEFT if not column else PP_ALIGN.CENTER)
    for line, row in enumerate(rows, start=1):
        _cell(table.cell(line, 0), str(row['category']), size=size)
        _cell(table.cell(line, 1), _number(row['before'], 2), size=size, align=PP_ALIGN.CENTER)
        _cell(table.cell(line, 2), _number(row['after'], 2), size=size, align=PP_ALIGN.CENTER)
        _cell(table.cell(line, 3), _signed(row['delta']), size=size, bold=True, align=PP_ALIGN.CENTER, color=_tone(row['delta']))
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
        top = CONTENT_TOP
        row_height = min(.36, (CONTENT_BOTTOM - .1 - top) / (len(page) + 1))
        size = 8 if row_height >= .3 else 7
        widths = [3.4, 1.6, 1.6, 1.1, WIDTH - 7.7]
        shape, table = _table(slide, len(page) + 1, 5, LEFT, top, WIDTH, row_height, widths)
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


def _bridge_slide(presentation, impact: dict[str, Any], part: dict[str, Any], environment: str, operators: list[dict[str, Any]]) -> None:
    rows = (part.get('bridge') or {}).get(environment)
    if not rows or not impact.get('earlier'):
        return
    earlier, latest = impact['earlier']['campaign_label'], impact['after']['campaign_label']
    slide = _slide(presentation, f'Methodology Impact — From {earlier} to {latest}', _subtitle(impact, environment, part))
    shown = [item for item in operators if rows.get(item['operator'])]
    widths = [2.6, 2.0, (WIDTH - 8.2) / 2 + .9, (WIDTH - 8.2) / 2 + .9, 2.0]
    widths.append(WIDTH - sum(widths))
    row_height = min(.5, (CONTENT_BOTTOM - .4 - CONTENT_TOP) / (len(shown) + 1))
    shape, table = _table(slide, len(shown) + 1, 6, LEFT, CONTENT_TOP, WIDTH, row_height, widths)
    shape.name = 'Scoring Impact Table'
    headers = ['Operator', f"{earlier} ({impact['before']['profile_name']})", 'The network changed', 'The methodology changed',
               f"{latest} ({impact['after']['profile_name']})", 'Total']
    for column, text in enumerate(headers):
        _cell(table.cell(0, column), text, size=9, bold=True, fill=HEADER_FILL, align=PP_ALIGN.LEFT if not column else PP_ALIGN.CENTER)
        table.cell(0, column).text_frame.word_wrap = True
    scale = max((abs(rows[item['operator']].get(field) or 0) for item in shown for field in ('network', 'methodology')), default=0.0)
    for line, item in enumerate(shown, start=1):
        row = rows[item['operator']]
        _cell(table.cell(line, 0), item['label'], size=10, bold=True, color=item.get('color') or INK)
        _cell(table.cell(line, 1), _number(row['earlier']), size=10, align=PP_ALIGN.CENTER)
        _cell(table.cell(line, 2), _signed(row['network']), size=10, bold=True, align=PP_ALIGN.CENTER, color=_tone(row['network']))
        _cell(table.cell(line, 3), _signed(row['methodology']), size=10, bold=True, align=PP_ALIGN.CENTER, color=_tone(row['methodology']))
        _cell(table.cell(line, 4), _number(row['latest']), size=10, align=PP_ALIGN.CENTER)
        _cell(table.cell(line, 5), _signed(row['total']), size=10, bold=True, align=PP_ALIGN.CENTER, color=_tone(row['total']))
        for column, field in ((2, 'network'), (3, 'methodology')):
            delta = row.get(field)
            if not scale or delta is None or abs(delta) < NO_CHANGE:
                continue
            middle = LEFT + sum(widths[:column]) + widths[column] / 2
            reach = abs(delta) / scale * (widths[column] / 2 - .08)
            bar = _box(slide, middle - reach if delta < 0 else middle, CONTENT_TOP + row_height * (line + 1) - .07, max(reach, .01), .045,
                       themed(GAIN_COLOR) if delta > 0 else themed(LOSS_COLOR))
            bar.name = 'Scoring Impact Bar'
    _note(slide, f"The network: {latest} scored with {impact['before']['profile_name']} minus {earlier} as it was scored. "
                 f"The methodology: {latest} with {impact['after']['profile_name']} minus the same tests with {impact['before']['profile_name']}.")


def _paged_slides(presentation, title: str, subtitle: str, first_header: str, operators: list[dict[str, Any]], rows: list[dict[str, Any]],
                  note: str, *, inverse: bool = False, pages: int = 3, extra: str = '') -> None:
    for page in _pages(rows, TABLE_ROWS)[:pages] if rows else []:
        slide = _slide(presentation, title, subtitle)
        _shift_table(slide, first_header, operators, page, top=CONTENT_TOP, inverse=inverse, extra=extra)
        _note(slide, note)


def _kpi_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{'label': row['kpi'], 'kpi_type': row.get('kpi_type'), 'cells': row['operators']} for row in rows]


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
        _paged_slides(presentation, f'Methodology Impact — Per {level}', _subtitle(impact, environment, part), level, operators, shown, note, pages=1, extra='Leader')


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


def export_impact_powerpoint(impact: dict[str, Any], template_path: Path, operator_mapping_groups: list[dict[str, Any]] | None = None, *,
                             scoring: str = 'best_network', environment: str = COMBINED, operators: list[str] | None = None,
                             panels: Any = None, theme: str = DEFAULT_THEME) -> bytes:
    """The panels of the Methodology Impact that the workspace exports (Scoring Export Panels), with the operators chosen in the
    page (``operators``, every one without it) and, in the Focus Operators panels, its Focus operators."""
    if not template_path.is_file():
        raise ValueError('The configured CDR PowerPoint template is missing.')
    settings = normalize_export_panels(panels)['impact']
    part, shown_environment = impact_part(impact, scoring, environment)
    chosen = [item for item in part['operators'] if not operators or item['operator'] in operators] or part['operators']
    focus = focus_matcher(focus_operators(operator_mapping_groups or []), [item['operator'] for item in part['operators']])

    def of_panel(key: str) -> list[dict[str, Any]]:
        if settings[key]['operators'] != FOCUS_OPERATORS:
            return chosen
        return [item for item in chosen if focus(item['operator'], item['label'])] or chosen

    def wanted(key: str) -> bool:
        return settings[key]['exportable']

    with use_theme(theme):
        presentation = Presentation(template_path)
        _remove_all_slides(presentation)
        _cover(presentation, impact, part, scoring)
        _takeaways_slide(presentation, impact, part, shown_environment)
        if wanted('changes'):
            _changes_slides(presentation, impact, part, shown_environment)
        if wanted('scoring'):
            _scoring_slide(presentation, impact, part, of_panel('scoring'))
        if wanted('bridge'):
            _bridge_slide(presentation, impact, part, shown_environment, of_panel('bridge'))
        subtitle = _subtitle(impact, shown_environment, part)
        if wanted('categories'):
            rows = [{'label': row['category'], 'cells': row['operators']} for row in part['categories'].get(shown_environment) or []]
            total = (part['scoring'].get(shown_environment) or {}).get('operators') or {}
            _paged_slides(presentation, 'Methodology Impact — Per category', subtitle, 'Category', of_panel('categories'),
                          [*rows, {'label': 'Total', 'bold': True, 'cells': total}],
                          'The points of each category with both methodologies; the colour and bar show the difference.', pages=1)
        if wanted('kpis'):
            rows = [row for row in part['kpis'].get(shown_environment) or [] if row.get('kinds') or row['peak'] >= NO_CHANGE]
            _paged_slides(presentation, 'Methodology Impact — KPIs affected', subtitle, 'KPI', of_panel('kpis'), _kpi_rows(rows),
                          'The KPIs that move most first. A KPI one methodology does not have counts none there.')
        if wanted('areas'):
            _area_slides(presentation, impact, part, shown_environment, of_panel('areas'))
        if wanted('gap'):
            _gap_slides(presentation, impact, part, shown_environment, of_panel('gap'))
        if wanted('points'):
            _points_slides(presentation, impact, part, shown_environment, of_panel('points'))
        report_structure.finish(presentation)
        output = BytesIO()
        presentation.save(output)
    return output.getvalue()


def impact_filename(impact: dict[str, Any], stamp: Any, extension: str) -> str:
    import re
    text = (f"{stamp:%Y%m%d_%H%M%S} - Scoring & GAP Analysis - Methodology Impact - {impact.get('nr_mode') or ''} - "
            f"{impact['before']['profile_name']} vs {impact['after']['profile_name']} - {impact['after']['campaign_label']}")
    return f"{re.sub(r'[\\/:*?\"<>|]+', '-', text)[:200].rstrip(' .-')}.{extension}"
