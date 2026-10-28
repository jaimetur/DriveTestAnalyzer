"""Canonical report layout names shared by storage, imports and rendering."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any
from uuid import uuid4

DYNAMIC_LAYOUTS = tuple(
    f"Title + {axes}" + (f" + comments {comments}" if comments else "")
    for axes in ('2 rows + dynamic columns', 'dynamic rows + 2 columns', 'dynamic rows + dynamic columns')
    for comments in ('', 'down', 'right')
)


def dynamic_layout_axes(layout: str) -> tuple[bool, bool]:
    canonical = canonical_layout_name(layout).lower()
    return 'dynamic rows' in canonical, 'dynamic columns' in canonical


# Counts written as words: renaming the Operator label 3 to Three once turned "3 columns" into "Three columns" in the
# Report Templates (see rename_chart_mapping_template_references), and those templates keep their grid.
_COUNT_WORDS = {word: number for number, word in enumerate(
    ('zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven', 'twelve'))}
_COUNT = r"(\d+|" + "|".join(_COUNT_WORDS) + r")"


def _count(value: str) -> int:
    return int(value) if value.isdigit() else _COUNT_WORDS[value.casefold()]


def grid_layout_name(rows: int, columns: int, comments: str = "") -> str:
    return f"Title + {rows} rows + {columns} columns" + (f" + comments {comments}" if comments else "")


def canonical_layout_name(value: str) -> str:
    """Translate historic grid names without changing internal structural layouts."""
    name = value.strip()
    dynamic = re.fullmatch(r"(?:Title\s*\+\s*)?(2 rows \+ dynamic columns|2 columns \+ dynamic rows|dynamic rows \+ 2 columns|dynamic rows \+ dynamic columns)(?:(?:,| \+) comments (down|right))?", name, re.I)
    if dynamic:
        direction, comments = dynamic.groups()
        direction = direction.lower()
        axes = direction if direction != "2 columns + dynamic rows" else "dynamic rows + 2 columns"
        return f"Title + {axes}" + (f" + comments {comments.lower()}" if comments else "")
    canonical = re.fullmatch(rf"Title \+ {_COUNT} rows \+ {_COUNT} columns(?: \+ comments (down|right))?", name, re.I)
    if canonical:
        rows, columns, comments = canonical.groups()
        return grid_layout_name(_count(rows), _count(columns), (comments or "").lower())
    old = re.fullmatch(r"Title and (\d+) (rows?|columns?)(?: and (\d+) (rows?|columns?))?(?: \((.*?)\))?(?: \+ Comments(?: (down|right))?)?", name, re.I)
    if old:
        first, direction, second, other, variant, comments = old.groups()
        rows, columns = (int(first), 1) if direction.lower().startswith('row') else (1, int(first))
        if second:
            if other.lower().startswith('row'):
                rows = int(second)
            else:
                columns = int(second)
        if variant and 'rows' in variant.lower():
            rows = 2
        return grid_layout_name(rows, columns, (comments or 'down').lower() if '+ comments' in name.lower() else '')
    return name


def compact_grid_layout(layout: str) -> bool:
    """Grids with three or more rows or four or more columns have small cells.

    Their chart titles are drawn outside the chart image at a readable size.
    """
    match = re.fullmatch(r"Title \+ (\d+) rows \+ (\d+) columns(?: \+ comments (?:down|right))?", canonical_layout_name(layout or ''))
    return bool(match) and (int(match.group(1)) >= 3 or int(match.group(2)) >= 4)


def selectable_layout_name(value: str) -> bool:
    return value in {'Title Page', 'Title Only', 'Transition', 'Black logo end slide', *DYNAMIC_LAYOUTS} or bool(re.fullmatch(
        r"Title \+ [1-9]\d* rows \+ [1-9]\d* columns(?: \+ comments (?:down|right))?", value,
    ))


def normalize_catalog_layouts(content: bytes) -> bytes:
    """Normalize layout names and extend recognized template schemas without losing values."""
    try:
        text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        if 'Layout' not in headers:
            return content
        rows = list(reader)
        if any(None in row for row in rows):
            return content
        changed = False
        # Former column names: CDR Source is Source Dataset; Rows and Column Aggregation are Rows and Columns Split.
        for legacy, current in (('CDR source', 'Source Dataset'), ('CDR Source', 'Source Dataset'),
                                ('Rows Aggregation', 'Rows Split'), ('Column Aggregation', 'Columns Split')):
            if legacy in headers:
                headers[headers.index(legacy)] = current
                for row in rows:
                    row[current] = row.pop(legacy)
                changed = True
        base_headers = ['Slide', 'Slide Tittle', 'Slide Subtittle', 'Layout', 'Chart Tittle', 'Source Dataset', 'KPI', 'Chart type', 'Filters', 'Rows Split', 'Columns Split', 'Legend', 'Legend Position']
        optional_headers = ['Legend Format', 'Label Position', 'Label Format', 'Axis X Range', 'Axis Y Range', 'Exclude Null/Empty', 'Exclude Zero', 'Dynamic Rows Field', 'Dynamic Columns Field']
        if 'Dynamic Field' in headers:
            position = headers.index('Dynamic Field')
            headers[position:position + 1] = ['Dynamic Rows Field', 'Dynamic Columns Field']
            for row in rows:
                legacy = row.pop('Dynamic Field') or ''
                dynamic_rows, dynamic_columns = dynamic_layout_axes(row.get('Layout') or '')
                row['Dynamic Rows Field'] = legacy if dynamic_rows else ''
                row['Dynamic Columns Field'] = legacy if dynamic_columns else ''
            changed = True
        non_dynamic_headers = [header for header in headers if header not in {'Dynamic Rows Field', 'Dynamic Columns Field'}]
        # The Format column (the Design beyond the columns, see design_slides) stays last.
        if set(base_headers).issubset(non_dynamic_headers) and all(header in base_headers + optional_headers + ['Format'] for header in headers):
            complete_headers = (base_headers[:4] + ['Dynamic Rows Field', 'Dynamic Columns Field'] + base_headers[4:] + optional_headers[:-2]
                                + (['Format'] if 'Format' in headers else []))
            if headers != complete_headers:
                headers = complete_headers
                for row in rows:
                    for header in optional_headers:
                        row.setdefault(header, '')
                changed = True
        for row in rows:
            old = row.get('Layout') or ''
            new = canonical_layout_name(old)
            if old != new:
                row['Layout'] = new
                changed = True
        if not changed:
            return content
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode('utf-8')
    except (UnicodeDecodeError, csv.Error):
        return content


# Template fields that name aggregation dimensions, and the filter field.
VENDOR_AGGREGATION_FIELDS = (
    'Rows Split', 'Columns Split', 'Legend', 'Dynamic Rows Field', 'Dynamic Columns Field', 'Dynamic Field',
    'Grouping', 'Grouping_Rows', 'Grouping_Columns',
)
_VENDOR_ONLY_NAME = re.compile(r'(?<![\w])vendor[ _]*only(?![\w])', re.IGNORECASE)
_VENDOR_NAME = re.compile(r'(?<![\w])vendor(?![\w])', re.IGNORECASE)


def rename_template_vendor_fields(content: bytes) -> bytes:
    """Convert a template written before the Operator_Vendor field to the current names.

    Aggregations, legends and dynamic fields named Vendor grouped by the
    operator-specific vendor, now Operator_Vendor; Vendor_Only is now Vendor.
    Vendor filters already selected the vendor alone and keep the name Vendor.
    """
    try:
        text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        rows = list(reader)
        if any(None in row for row in rows):
            return content
        changed = False
        for row in rows:
            for header in headers:
                value = row.get(header) or ''
                if header in VENDOR_AGGREGATION_FIELDS:
                    renamed = _VENDOR_ONLY_NAME.sub('\x00', value)
                    renamed = _VENDOR_NAME.sub('Operator_Vendor', renamed).replace('\x00', 'Vendor')
                elif header == 'Filters':
                    renamed = re.sub(r'(^|[;\r\n]\s*)vendor[ _]*only(?=\s*(?:NOT\s+CONTAINS|NOT\s+IN|CONTAINS|IN|[<>=!]))',
                                     r'\1Vendor', value, flags=re.IGNORECASE)
                else:
                    continue
                if renamed != value:
                    row[header] = renamed
                    changed = True
        if not changed:
            return content
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=headers, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode('utf-8')
    except (UnicodeDecodeError, csv.Error):
        return content


# The slides of a template (stable slide and element ids, see design_slides) in its Format column.

def slide_item_id(prefix: str) -> str:
    return f'{prefix}{uuid4().hex[:10]}'


def slides_format_cell(data: dict[str, Any]) -> str:
    cleaned = {key: value for key, value in data.items() if value not in (None, '', [], {})}
    return json.dumps(cleaned, ensure_ascii=False, sort_keys=True, separators=(',', ':')) if cleaned else ''


def csv_with_slide_ids(content: bytes) -> bytes:
    """A template CSV written with a Format column, with every row's ids completed (as ``design_slides.with_slide_ids``).

    Works on the raw rows, so an incomplete template (the editor can keep one) is never refused here; a CSV without a
    Format column, or with no slide id in it, is returned as it is.
    """
    try:
        text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        headers = list(reader.fieldnames or [])
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        return content
    if 'Format' not in headers or 'Slide' not in headers or any(None in row for row in rows):
        return content
    parsed: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row.get('Format') or '{}') or {}
        except ValueError:
            return content
        parsed.append(data if isinstance(data, dict) else {})
    if not any(data.get('slide') for data in parsed):
        return content
    groups: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(str(row.get('Slide') or '').strip(), []).append(index)
    seen_slides: set[str] = set()
    seen_elements: set[str] = set()
    changed = False
    structural = {'title slide', 'transition slide', 'end slide'}
    for indexes in groups.values():
        slide_id = next((str(parsed[index]['slide']) for index in indexes
                         if parsed[index].get('slide') and str(parsed[index]['slide']) not in seen_slides), '') or slide_item_id('s')
        seen_slides.add(slide_id)
        for index in indexes:
            data = parsed[index]
            if data.get('slide') != slide_id:
                data['slide'] = slide_id
                changed = True
            if str(rows[index].get('Chart type') or '').strip().casefold() in structural:
                continue
            element_id = str(data.get('id') or '')
            if not element_id or element_id in seen_elements:
                data['id'] = element_id = slide_item_id('e')
                changed = True
            seen_elements.add(element_id)
    if not changed:
        return content
    for row, data in zip(rows, parsed, strict=True):
        row['Format'] = slides_format_cell(data)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')
