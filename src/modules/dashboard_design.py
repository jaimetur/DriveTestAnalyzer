"""The Design of a PPT Template and the overrides of a Dashboard (Dashboard Designer, ticket #26).

A **Design** is the structured form of a template that the Designer edits::

    {"version": 1,
     "parameters": [{"id", "name", "type": "values" | "number" | "text", "field", "multiple", "default",
                     "min", "max", "step", "description"}],
     "slides": [{"id", "kind": "content" | "title" | "transition" | "end", "title", "subtitle", "layout",
                 "optional", "chart_type" (structural slides), "options": {...},
                 "elements": [{"id", "kind": "chart", "place", <the chart columns>, "style": {...}}]}]}

It lives in the template CSV itself: every row keeps its element and slide ids, and what the columns cannot hold, in
its ``Format`` cell (a JSON object), so every path that copies a template (Table view, import, export, transfer,
backup, restore) carries its Design unchanged. A template without Format cells reads with positional ids until the
Designer gives it ids of its own (``with_slide_ids``; the repository completes them on every write of a template
that has them, ``report_layouts.csv_with_slide_ids``).

A Dashboard inherits the Design of its template live and keeps only its **overrides**, by id::

    {"version": 1,
     "slides": {slide id: {property: {"value", "base"}}},        # base: the template value when it was overridden
     "elements": {element id: {property: {"value", "base"}}},
     "filters": {element id: {"add": [conditions], "remove": [conditions]}},
     "hidden_slides": [slide ids], "shown_optional": [slide ids], "hidden_elements": [element ids],
     "local_slides": [{"after": slide id or "", "slide": {...}}],
     "local_elements": {template slide id: [{...}]}}

so a template change reaches every Dashboard that did not change that same thing.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import replace
from typing import Any, Iterable

from src.modules.cdr_reporting import CatalogEntry, catalogue_csv, entry_dynamic_fields
from src.modules.report_layouts import canonical_layout_name, slides_format_cell as format_cell, slide_item_id as new_id

SLIDES_VERSION = 1
OVERRIDES_VERSION = 1
# The chart columns of a row as properties of its element (CatalogEntry field names).
ELEMENT_FIELDS = (
    'chart_title', 'cdr_source', 'kpi', 'chart_type', 'filters', 'rows_split', 'columns_split', 'legend',
    'legend_position', 'legend_format', 'label_position', 'label_format', 'axis_x_range', 'axis_y_range',
    'exclude_null_empty', 'exclude_zero', 'dynamic_rows_field', 'dynamic_columns_field',
)
SLIDE_FIELDS = ('title', 'subtitle', 'layout')
# Properties a Dashboard can override besides the columns.
SLIDE_OVERRIDABLE = (*SLIDE_FIELDS, 'options')
ELEMENT_OVERRIDABLE = tuple(field for field in ELEMENT_FIELDS if field != 'filters') + ('place', 'style', 'kind', 'content', 'kpi_card', 'repeat')
STRUCTURAL_KINDS = {'title slide': 'title', 'transition slide': 'transition', 'end slide': 'end'}
STRUCTURAL_CHART_TYPES = {'title': 'Title Slide', 'transition': 'Transition Slide', 'end': 'End Slide'}
ELEMENT_KINDS = ('chart', 'kpi', 'text', 'image')
# The Chart type of the row of each kind of element other than a chart.
KIND_CHART_TYPES = {'kpi': 'KPI Card', 'text': 'Text Box', 'image': 'Image'}
PARAMETER_TYPES = ('values', 'number', 'text')
# The fields a Dashboard writes in the titles and text boxes of its slides from its own selection (``{Cities}``: the
# Cities it is filtered by, or All Cities), as the Designer offers them.
SELECTION_TOKENS = ('Dashboard', 'Scope', 'Campaigns', 'Operators', 'Vendors', 'Regions', 'Clusters', 'Cities')
# Tokens the slides resolve (report_template_modes and the selection): parameters cannot take their names.
RESERVED_TOKENS = {'nr mode', 'nr mode name', 'dates', *(token.casefold() for token in SELECTION_TOKENS)}
TOKEN_PATTERN = re.compile(r'\{([^{}]+)\}')
FILTER_SEPARATOR = re.compile(r';|[\r\n]+')


def row_format(entry: CatalogEntry) -> dict[str, Any]:
    """The Format cell of a template row as a dict (empty for a row without one)."""
    try:
        data = json.loads(entry.format) if entry.format else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def copied_entry(entry: CatalogEntry) -> CatalogEntry:
    """A row copied into another template: its format without the ids and parameters of the template it came from
    (it takes ids of its own there)."""
    data = {key: value for key, value in row_format(entry).items() if key not in {'id', 'slide', 'parameters'}}
    return replace(entry, format=format_cell(data))


def has_slide_ids(entries: Iterable[CatalogEntry]) -> bool:
    return any(row_format(entry).get('slide') for entry in entries)


def _slide_groups(entries: list[CatalogEntry]) -> list[tuple[int, list[tuple[int, CatalogEntry]]]]:
    """The rows of each slide (with their row index), slides in their number order and rows in their order."""
    groups: dict[int, list[tuple[int, CatalogEntry]]] = {}
    for index, entry in enumerate(entries):
        groups.setdefault(entry.slide, []).append((index, entry))
    return sorted(groups.items())


def with_slide_ids(entries: list[CatalogEntry]) -> list[CatalogEntry]:
    """The rows of a template, each with a slide id and (chart rows) an element id of its own.

    Rows keep the ids they have; a missing id takes the positional one the template was read with until then
    (``slides_from_entries``), so what a Dashboard overrode keeps its id, and one already taken (a copied row) a new one.
    All rows of a slide share the slide id of its first row that has one.
    """
    result = list(entries)
    groups = _slide_groups(entries)
    taken = {str(row_format(entry).get(key)) for entry in entries for key in ('slide', 'id') if row_format(entry).get(key)}
    seen_slides: set[str] = set()
    seen_elements: set[str] = set()

    def free(candidate: str, prefix: str) -> str:
        identifier = candidate if candidate not in taken else new_id(prefix)
        taken.add(identifier)
        return identifier

    for number, rows in groups:
        slide_id = next((str(row_format(entry)['slide']) for _index, entry in rows
                         if row_format(entry).get('slide') and str(row_format(entry)['slide']) not in seen_slides), '')
        slide_id = slide_id or free(f's{number}', 's')
        seen_slides.add(slide_id)
        for position, (index, entry) in enumerate(rows):
            data = row_format(entry)
            data['slide'] = slide_id
            if entry.structural_type:
                data.pop('id', None)
            else:
                element_id = str(data.get('id') or '')
                if element_id in seen_elements:
                    element_id = new_id('e')
                elif not element_id:
                    element_id = free(f'{slide_id}e{position + 1}', 'e')
                data['id'] = element_id
                seen_elements.add(element_id)
            result[index] = replace(entry, format=format_cell(data))
    return result


# ---------------------------------------------------------------------------
# Template rows <-> Design
# ---------------------------------------------------------------------------

def _element_from_entry(entry: CatalogEntry, data: dict[str, Any], element_id: str, place: int) -> dict[str, Any]:
    kind = data.get('kind') or next((key for key, chart_type in KIND_CHART_TYPES.items()
                                     if chart_type.casefold() == entry.chart_type.casefold()), 'chart')
    element = {'id': element_id, 'kind': kind, 'place': data.get('place', place)}
    if data.get('kpi'):
        element['kpi_card'] = data['kpi']
    if data.get('repeat'):
        element['repeat'] = data['repeat']
    for field in ELEMENT_FIELDS:
        element[field] = getattr(entry, field)
    rows_field, columns_field = entry_dynamic_fields(entry)
    element['dynamic_rows_field'], element['dynamic_columns_field'] = rows_field, columns_field
    if data.get('style'):
        element['style'] = data['style']
    if data.get('content') is not None:
        element['content'] = data['content']
    return element


def slides_from_entries(entries: list[CatalogEntry]) -> dict[str, Any]:
    """The Design of a template from its rows (as written: no NR Mode applied).

    Rows without ids get positional ones (``s<slide>`` and ``s<slide>e<n>``), the same every time the same CSV is
    read, until ``with_slide_ids`` gives them ids of their own.
    """
    parameters: list[dict[str, Any]] = []
    slides: list[dict[str, Any]] = []
    for number, rows in _slide_groups(entries):
        first = rows[0][1]
        if not parameters:
            for _index, entry in rows:
                if isinstance(row_format(entry).get('parameters'), list):
                    parameters = [dict(item) for item in row_format(entry)['parameters'] if isinstance(item, dict)]
                    break
        slide_id = str(next((row_format(entry).get('slide') for _index, entry in rows if row_format(entry).get('slide')), '')
                       or f's{number}')
        options = next((row_format(entry).get('slide_options') for _index, entry in rows
                        if isinstance(row_format(entry).get('slide_options'), dict)), None) or {}
        structural = first.structural_type
        slide = {
            'id': slide_id,
            'kind': STRUCTURAL_KINDS.get(structural or '', 'content'),
            'title': first.slide_title,
            'subtitle': first.slide_subtitle,
            'layout': canonical_layout_name(first.layout),
            'optional': bool(options.get('optional')),
            'elements': [],
        }
        if structural:
            slide['chart_type'] = first.chart_type
            if first.legend_position:
                # Written in some templates on their structural rows: kept so the CSV reads back the same.
                slide['legend_position'] = first.legend_position
        extra_options = {key: value for key, value in options.items() if key != 'optional'}
        if extra_options:
            slide['options'] = extra_options
        if not structural:
            for position, (_index, entry) in enumerate(rows):
                data = row_format(entry)
                element_id = str(data.get('id') or f'{slide_id}e{position + 1}')
                slide['elements'].append(_element_from_entry(entry, data, element_id, position))
        slides.append(slide)
    return {'version': SLIDES_VERSION, 'parameters': parameters, 'slides': slides}


def _entry_format(slide: dict[str, Any], element: dict[str, Any] | None, *, first_row: bool, template_first_row: bool,
                  parameters: list[dict[str, Any]], position: int) -> str:
    data: dict[str, Any] = {'slide': slide['id']}
    if element is not None:
        data['id'] = element['id']
        if (element.get('kind') or 'chart') != 'chart':
            data['kind'] = element['kind']
        if element.get('place', position) != position:
            data['place'] = element['place']
        if element.get('style'):
            data['style'] = element['style']
        if element.get('content') is not None:
            data['content'] = element['content']
        if element.get('kpi_card'):
            data['kpi'] = element['kpi_card']
        if element.get('repeat'):
            data['repeat'] = element['repeat']
    if first_row:
        options = dict(slide.get('options') or {})
        if slide.get('optional'):
            options['optional'] = True
        if options:
            data['slide_options'] = options
    if template_first_row and parameters:
        data['parameters'] = parameters
    return format_cell(data)


def entries_from_slides(slide_set: dict[str, Any], *, include_hidden: bool = False) -> list[CatalogEntry]:
    """The template rows of a Design (slides numbered from 1 in their order, elements in the order of their place).

    Slides marked hidden or optional-off (a resolved Dashboard Design) are left out unless ``include_hidden``.
    """
    entries: list[CatalogEntry] = []
    parameters = list(slide_set.get('parameters') or [])
    number = 0
    for slide in slide_set.get('slides') or []:
        if not include_hidden and (slide.get('hidden') or slide.get('optional_off')):
            continue
        number += 1
        base = dict(slide=number, slide_title=slide.get('title') or '', slide_subtitle=slide.get('subtitle') or '',
                    layout=canonical_layout_name(slide.get('layout') or ''))
        kind = slide.get('kind') or 'content'
        if kind in STRUCTURAL_CHART_TYPES:
            entries.append(CatalogEntry(
                **base, chart_title='', cdr_source='', kpi='', chart_type=slide.get('chart_type') or STRUCTURAL_CHART_TYPES[kind],
                legend='', filters='', rows_split='', columns_split='', legend_position=slide.get('legend_position') or '',
                format=_entry_format(slide, None, first_row=True, template_first_row=not entries,
                                     parameters=parameters, position=0),
            ))
            continue
        elements = [element for element in slide.get('elements') or [] if include_hidden or not element.get('hidden')]
        elements = sorted(enumerate(elements), key=lambda item: (_place(item[1], item[0]), item[0]))
        for position, (_original, element) in enumerate(elements):
            values = {field: element.get(field, '' if field not in {'exclude_null_empty', 'exclude_zero'} else False)
                      for field in ELEMENT_FIELDS}
            values['legend_position'] = values['legend_position'] or ''
            if (element.get('kind') or 'chart') in KIND_CHART_TYPES:
                values['chart_type'] = KIND_CHART_TYPES[element['kind']]
            entries.append(CatalogEntry(
                **base, **values,
                format=_entry_format(slide, element, first_row=position == 0, template_first_row=not entries,
                                     parameters=parameters, position=position),
            ))
    return entries


def _place(element: dict[str, Any], default: int) -> int:
    try:
        return int(element.get('place', default))
    except (TypeError, ValueError):
        return default


def slides_csv(slide_set: dict[str, Any]) -> bytes:
    """The CSV of a Design (its Table view and export): the columns plus the Format column."""
    return catalogue_csv(entries_from_slides(slide_set, include_hidden=True))


def slides_without_elements(slide_set: dict[str, Any]) -> list[str]:
    """Content slides with no element: a template row needs at least one element per content slide."""
    return [slide.get('title') or slide['id'] for slide in slide_set.get('slides') or []
            if (slide.get('kind') or 'content') == 'content' and not slide.get('elements')]


# ---------------------------------------------------------------------------
# Overrides of a Dashboard
# ---------------------------------------------------------------------------

def empty_overrides() -> dict[str, Any]:
    return {'version': OVERRIDES_VERSION, 'slides': {}, 'elements': {}, 'filters': {}, 'hidden_slides': [],
            'shown_optional': [], 'hidden_elements': [], 'local_slides': [], 'local_elements': {}}


def normalized_overrides(overrides: dict[str, Any] | None) -> dict[str, Any]:
    result = empty_overrides()
    for key, value in (overrides or {}).items():
        if key in result and isinstance(value, type(result[key])):
            result[key] = copy.deepcopy(value)
    return result


def has_overrides(overrides: dict[str, Any] | None) -> bool:
    data = normalized_overrides(overrides)
    return any(value for key, value in data.items() if key != 'version')


def filter_conditions(filters: str) -> list[str]:
    """The conditions of a Filters value (separated by semicolons or lines), spacing normalized."""
    return [re.sub(r'\s+', ' ', part.strip()) for part in FILTER_SEPARATOR.split(filters or '') if part.strip()]


def join_conditions(conditions: Iterable[str]) -> str:
    return '; '.join(conditions)


def _condition_key(condition: str) -> str:
    return re.sub(r'\s+', ' ', condition.strip()).casefold()


def apply_filter_override(filters: str, change: dict[str, Any] | None) -> str:
    if not change:
        return filters
    removed = {_condition_key(item) for item in change.get('remove') or []}
    kept = [condition for condition in filter_conditions(filters) if _condition_key(condition) not in removed]
    present = {_condition_key(condition) for condition in kept}
    added = [condition for condition in (filter_conditions(join_conditions(change.get('add') or [])))
             if _condition_key(condition) not in present]
    return join_conditions(kept + added) if (removed or added) else filters


def resolve_slides(template: dict[str, Any], overrides: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """The Design a Dashboard shows: its template with its overrides, and a report of them.

    Hidden template slides and optional slides left off stay in the result, marked ``hidden`` / ``optional_off``
    (the Designer shows them greyed; ``entries_from_slides`` leaves them out). Every overridden slide and element
    lists its overridden properties in ``overridden``; the report lists the overrides whose slide or element the
    template no longer has (``dropped``) and those whose template value changed since (``template_changed``).
    """
    data = normalized_overrides(overrides)
    slide_set = copy.deepcopy(template)
    template_slides = {slide['id']: slide for slide in template.get('slides') or []}
    template_elements = {element['id']: (slide['id'], element)
                         for slide in template.get('slides') or [] for element in slide.get('elements') or []}
    dropped: list[dict[str, str]] = []
    changed: list[dict[str, Any]] = []
    hidden_slides = set(data['hidden_slides'])
    shown_optional = set(data['shown_optional'])
    hidden_elements = set(data['hidden_elements'])
    for slide in slide_set.get('slides') or []:
        slide['origin'] = 'template'
        if slide['id'] in hidden_slides:
            slide['hidden'] = True
        if slide.get('optional') and slide['id'] not in shown_optional:
            slide['optional_off'] = True
        for name, override in (data['slides'].get(slide['id']) or {}).items():
            if name not in SLIDE_OVERRIDABLE or not isinstance(override, dict):
                continue
            current = slide.get(name)
            if 'base' in override and override['base'] != current:
                changed.append({'slide': slide['id'], 'property': name, 'base': override['base'], 'template': current,
                                'value': override.get('value')})
            slide[name] = copy.deepcopy(override.get('value'))
            slide.setdefault('overridden', []).append(name)
        for element in slide.get('elements') or []:
            element['origin'] = 'template'
            if element['id'] in hidden_elements:
                element['hidden'] = True
            for name, override in (data['elements'].get(element['id']) or {}).items():
                if name not in ELEMENT_OVERRIDABLE or not isinstance(override, dict):
                    continue
                current = element.get(name)
                if 'base' in override and override['base'] != current:
                    changed.append({'element': element['id'], 'property': name, 'base': override['base'],
                                    'template': current, 'value': override.get('value')})
                element[name] = copy.deepcopy(override.get('value'))
                element.setdefault('overridden', []).append(name)
            if change := data['filters'].get(element['id']):
                element['filters'] = apply_filter_override(element.get('filters') or '', change)
                element.setdefault('overridden', []).append('filters')
        for local in data['local_elements'].get(slide['id']) or []:
            if isinstance(local, dict) and local.get('id'):
                slide.setdefault('elements', []).append({**copy.deepcopy(local), 'origin': 'dashboard'})
    for slide_id in list(data['slides']) + list(data['local_elements']) + list(hidden_slides) + list(shown_optional):
        if slide_id not in template_slides:
            dropped.append({'slide': slide_id})
    for element_id in list(data['elements']) + list(data['filters']) + list(hidden_elements):
        if element_id not in template_elements:
            dropped.append({'element': element_id})
    slides = slide_set.get('slides') or []
    template_order = [slide['id'] for slide in template.get('slides') or []]
    for local in data['local_slides']:
        if not isinstance(local, dict) or not isinstance(local.get('slide'), dict):
            continue
        slide = {**copy.deepcopy(local['slide']), 'origin': 'dashboard'}
        for element in slide.get('elements') or []:
            element['origin'] = 'dashboard'
        after = str(local.get('after') or '')
        ids = [item['id'] for item in slides]
        if not after:
            slides.insert(0, slide)
        elif after in ids:
            slides.insert(ids.index(after) + 1, slide)
        elif after in template_order:
            # Its anchor is left out here: after the nearest earlier template slide that is in the Design.
            earlier = [item for item in template_order[:template_order.index(after)] if item in ids]
            slides.insert(ids.index(earlier[-1]) + 1 if earlier else 0, slide)
        else:
            dropped.append({'anchor': after, 'slide': slide['id']})
            slides.append(slide)
    slide_set['slides'] = slides
    # Keep each report entry once (an id can be listed by several kinds of override).
    unique_dropped = [dict(item) for item in {json.dumps(item, sort_keys=True): item for item in dropped}.values()]
    return slide_set, {'dropped': unique_dropped, 'template_changed': changed}


def _comparable(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True)) if value is not None else None


def overrides_between(template: dict[str, Any], edited: dict[str, Any],
                      previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """The overrides that turn a template Design into the Design a Dashboard edited.

    ``edited`` is a resolved Design (``resolve_slides``) after the edits of This Dashboard scope: template slides keep
    their order (only Dashboard slides move), hidden template slides keep ``hidden`` and optional ones left off
    ``optional_off``. An override keeps the template value it was made on (``base``) while its value does not change,
    so a later template change still shows as *Template changed*.
    """
    before = normalized_overrides(previous)
    result = empty_overrides()
    template_slides = {slide['id']: slide for slide in template.get('slides') or []}
    template_elements = {element['id']: slide['id']
                         for slide in template.get('slides') or [] for element in slide.get('elements') or []}
    previous_id = ''
    for slide in edited.get('slides') or []:
        slide_id = str(slide.get('id') or '')
        if slide_id in template_slides:
            original = template_slides[slide_id]
            if slide.get('hidden'):
                result['hidden_slides'].append(slide_id)
            if original.get('optional') and not slide.get('optional_off'):
                result['shown_optional'].append(slide_id)
            for name in SLIDE_OVERRIDABLE:
                value, base = _comparable(slide.get(name)), _comparable(original.get(name))
                if value == base or (name == 'options' and not value and not base):
                    continue
                prior = (before['slides'].get(slide_id) or {}).get(name) or {}
                kept_base = prior.get('base', base) if _comparable(prior.get('value')) == value else base
                result['slides'].setdefault(slide_id, {})[name] = {'value': value, 'base': kept_base}
            edited_ids = set()
            for element in slide.get('elements') or []:
                element_id = str(element.get('id') or '')
                if template_elements.get(element_id) == slide_id:
                    edited_ids.add(element_id)
                    template_element = next(item for item in original.get('elements') or [] if item['id'] == element_id)
                    if element.get('hidden'):
                        result['hidden_elements'].append(element_id)
                    for name in ELEMENT_OVERRIDABLE:
                        value, base = _comparable(element.get(name)), _comparable(template_element.get(name))
                        if value == base or (name in {'style', 'content', 'kpi_card', 'repeat'} and not value and not base):
                            continue
                        prior = (before['elements'].get(element_id) or {}).get(name) or {}
                        kept_base = prior.get('base', base) if _comparable(prior.get('value')) == value else base
                        result['elements'].setdefault(element_id, {})[name] = {'value': value, 'base': kept_base}
                    edited_conditions = filter_conditions(element.get('filters') or '')
                    template_conditions = filter_conditions(template_element.get('filters') or '')
                    edited_keys = {_condition_key(item) for item in edited_conditions}
                    template_keys = {_condition_key(item) for item in template_conditions}
                    added = [item for item in edited_conditions if _condition_key(item) not in template_keys]
                    removed = [item for item in template_conditions if _condition_key(item) not in edited_keys]
                    if added or removed:
                        result['filters'][element_id] = {'add': added, 'remove': removed}
                elif not element.get('hidden'):
                    local = _clean_element(element)
                    if element_id in template_elements or not element_id:
                        local['id'] = new_id('e')
                    result['local_elements'].setdefault(slide_id, []).append(local)
            for template_element in original.get('elements') or []:
                if template_element['id'] not in edited_ids:
                    result['hidden_elements'].append(template_element['id'])
        elif not slide.get('hidden'):
            local = _clean_slide(slide)
            if not slide_id:
                local['id'] = new_id('s')
            result['local_slides'].append({'after': previous_id, 'slide': local})
        previous_id = slide_id or previous_id
    # A template slide the edited Design does not have at all is left out of the Dashboard as a hidden one.
    edited_ids = {str(slide.get('id') or '') for slide in edited.get('slides') or []}
    result['hidden_slides'].extend(slide_id for slide_id in template_slides if slide_id not in edited_ids)
    result['hidden_slides'] = list(dict.fromkeys(result['hidden_slides']))
    result['hidden_elements'] = list(dict.fromkeys(result['hidden_elements']))
    return result


def _clean_element(element: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in element.items()
            if key not in {'origin', 'overridden', 'hidden', 'template_changed'}}


def _clean_slide(slide: dict[str, Any]) -> dict[str, Any]:
    cleaned = {key: copy.deepcopy(value) for key, value in slide.items()
               if key not in {'origin', 'overridden', 'hidden', 'optional_off', 'template_changed', 'elements'}}
    cleaned['elements'] = [_clean_element(element) for element in slide.get('elements') or [] if not element.get('hidden')]
    return cleaned


def template_slides_of(resolved: dict[str, Any]) -> dict[str, Any]:
    """A resolved Design as a template of its own (Save as template, Detach): what it shows, without the marks."""
    slide_set = {'version': SLIDES_VERSION, 'parameters': copy.deepcopy(resolved.get('parameters') or []), 'slides': []}
    for slide in resolved.get('slides') or []:
        if slide.get('hidden') or slide.get('optional_off'):
            continue
        cleaned = _clean_slide(slide)
        slide_set['slides'].append(cleaned)
    return slide_set


def overrides_summary(overrides: dict[str, Any] | None) -> dict[str, int]:
    """How many overrides of each kind (App Events, Differences panel)."""
    data = normalized_overrides(overrides)
    return {
        'slide_properties': sum(len(item) for item in data['slides'].values()),
        'element_properties': sum(len(item) for item in data['elements'].values()),
        'chart_filters': len(data['filters']),
        'hidden_slides': len(data['hidden_slides']),
        'shown_optional_slides': len(data['shown_optional']),
        'hidden_elements': len(data['hidden_elements']),
        'local_slides': len(data['local_slides']),
        'local_elements': sum(len(item) for item in data['local_elements'].values()),
    }


def drop_override(overrides: dict[str, Any] | None, *, slide: str = '', element: str = '', name: str = '') -> dict[str, Any]:
    """Reset to template: the overrides without that of a slide or element (one property, or all of them)."""
    data = normalized_overrides(overrides)
    if slide:
        if name:
            (data['slides'].get(slide) or {}).pop(name, None)
            if not data['slides'].get(slide):
                data['slides'].pop(slide, None)
        else:
            data['slides'].pop(slide, None)
            data['hidden_slides'] = [item for item in data['hidden_slides'] if item != slide]
            data['local_elements'].pop(slide, None)
    if element:
        if name == 'filters':
            data['filters'].pop(element, None)
        elif name:
            (data['elements'].get(element) or {}).pop(name, None)
            if not data['elements'].get(element):
                data['elements'].pop(element, None)
        else:
            data['elements'].pop(element, None)
            data['filters'].pop(element, None)
            data['hidden_elements'] = [item for item in data['hidden_elements'] if item != element]
    return data


def keep_overrides(overrides: dict[str, Any] | None, template: dict[str, Any]) -> dict[str, Any]:
    """Keep mine: every override flagged *Template changed* takes the current template value as its base."""
    data = normalized_overrides(overrides)
    slides = {slide['id']: slide for slide in template.get('slides') or []}
    elements = {element['id']: element for slide in template.get('slides') or [] for element in slide.get('elements') or []}
    for slide_id, properties in data['slides'].items():
        for name, override in properties.items():
            if slide_id in slides:
                override['base'] = _comparable(slides[slide_id].get(name))
    for element_id, properties in data['elements'].items():
        for name, override in properties.items():
            if element_id in elements:
                override['base'] = _comparable(elements[element_id].get(name))
    return data


def without_dropped(overrides: dict[str, Any] | None, template: dict[str, Any]) -> dict[str, Any]:
    """The overrides whose slide or element the template still has (a Dashboard saved after the template deleted one)."""
    data = normalized_overrides(overrides)
    slides = {slide['id'] for slide in template.get('slides') or []}
    elements = {element['id'] for slide in template.get('slides') or [] for element in slide.get('elements') or []}
    data['slides'] = {key: value for key, value in data['slides'].items() if key in slides}
    data['local_elements'] = {key: value for key, value in data['local_elements'].items() if key in slides}
    data['hidden_slides'] = [item for item in data['hidden_slides'] if item in slides]
    data['shown_optional'] = [item for item in data['shown_optional'] if item in slides]
    data['elements'] = {key: value for key, value in data['elements'].items() if key in elements}
    data['filters'] = {key: value for key, value in data['filters'].items() if key in elements}
    data['hidden_elements'] = [item for item in data['hidden_elements'] if item in elements]
    return data


# ---------------------------------------------------------------------------
# Template parameters
# ---------------------------------------------------------------------------

def validate_parameters(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Template parameters checked and completed (ids, types); raises ValueError naming the first problem."""
    cleaned: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in parameters or []:
        if not isinstance(item, dict):
            raise ValueError('Each parameter must be an object.')
        name = str(item.get('name') or '').strip()
        if not name or '{' in name or '}' in name:
            raise ValueError('Each parameter needs a name without braces.')
        if name.casefold() in RESERVED_TOKENS:
            raise ValueError(f"'{name}' is a built-in token: choose another parameter name.")
        if name.casefold() in names:
            raise ValueError(f"Two parameters are named '{name}'.")
        names.add(name.casefold())
        kind = str(item.get('type') or 'values')
        if kind not in PARAMETER_TYPES:
            raise ValueError(f"Parameter '{name}' has an unknown type.")
        parameter = {'id': str(item.get('id') or new_id('p')), 'name': name, 'type': kind,
                     'description': str(item.get('description') or '')}
        if kind == 'values':
            field = str(item.get('field') or '').strip()
            if not field:
                raise ValueError(f"Parameter '{name}' needs the field whose values it chooses.")
            default = item.get('default')
            parameter.update(field=field, multiple=bool(item.get('multiple', True)),
                             default=[str(value) for value in default] if isinstance(default, list) else None)
        elif kind == 'number':
            for key in ('default', 'min', 'max', 'step'):
                value = item.get(key)
                if value in (None, ''):
                    parameter[key] = None
                    continue
                try:
                    parameter[key] = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Parameter '{name}': {key} must be a number.") from exc
        else:
            parameter['default'] = str(item.get('default') or '')
        cleaned.append(parameter)
    return cleaned


def parameter_value(parameter: dict[str, Any], values: dict[str, Any] | None) -> Any:
    """The value a Dashboard gives a parameter (its default when it gives none). ``None``: All values."""
    values = values or {}
    if parameter['id'] in values:
        return values[parameter['id']]
    return parameter.get('default')


def _number_text(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else repr(number)


def _parameter_text(parameter: dict[str, Any], value: Any) -> str:
    if parameter['type'] == 'values':
        return ', '.join(str(item) for item in value) if isinstance(value, list) and value else 'All'
    if parameter['type'] == 'number':
        return _number_text(value) if value not in (None, '') else ''
    return str(value or '')


def _replace_tokens(text: str, replacements: dict[str, str]) -> str:
    if not text or '{' not in text:
        return text
    return TOKEN_PATTERN.sub(lambda match: replacements.get(match.group(1).strip().casefold(), match.group(0)), text)


def parameter_uses(slide_set: dict[str, Any], name: str) -> list[str]:
    """Where a Design names a parameter (``{name}``): slide and element titles, filters and settings."""
    key = name.strip().casefold()
    uses = []
    for number, slide in enumerate(slide_set.get('slides') or [], start=1):
        for field in ('title', 'subtitle'):
            if any(match.strip().casefold() == key for match in TOKEN_PATTERN.findall(str(slide.get(field) or ''))):
                uses.append(f'Slide {number} {field}')
        for element in slide.get('elements') or []:
            for field in (*ELEMENT_FIELDS, 'content'):
                text = json.dumps(element.get(field)) if field == 'content' else str(element.get(field) or '')
                if any(match.strip().casefold() == key for match in TOKEN_PATTERN.findall(text)):
                    uses.append(f"Slide {number} · {element.get('chart_title') or element['id']} · {field}")
    return uses


def rename_parameter(slide_set: dict[str, Any], previous: str, name: str) -> dict[str, Any]:
    """The Design with every ``{previous}`` written ``{name}``."""
    replacements = {previous.strip().casefold(): '{' + name + '}'}
    result = copy.deepcopy(slide_set)
    for slide in result.get('slides') or []:
        for field in ('title', 'subtitle'):
            slide[field] = _replace_tokens(slide.get(field) or '', replacements)
        for element in slide.get('elements') or []:
            for field in ELEMENT_FIELDS:
                if isinstance(element.get(field), str):
                    element[field] = _replace_tokens(element[field], replacements)
            if element.get('content') is not None:
                element['content'] = json.loads(_replace_tokens(json.dumps(element['content']), replacements))
    return result


# The columns of a row whose text names fields of the Dashboard (its titles), besides the text of a text box.
TITLE_FIELDS = ('slide_title', 'slide_subtitle', 'chart_title')


def _with_text_content(entry: CatalogEntry, texts: dict[str, str]) -> CatalogEntry:
    """A text box row with the tokens of its text replaced."""
    if entry.chart_type.casefold() != KIND_CHART_TYPES['text'].casefold() or '{' not in entry.format:
        return entry
    data = row_format(entry)
    content = data.get('content')
    if not isinstance(content, dict) or '{' not in str(content.get('text') or ''):
        return entry
    data['content'] = {**content, 'text': _replace_tokens(str(content['text']), texts)}
    return replace(entry, format=format_cell(data))


def used_tokens(entries: Iterable[CatalogEntry]) -> set[str]:
    """The tokens (lower case) the titles and text boxes of some rows name."""
    found: set[str] = set()
    for entry in entries:
        texts = [getattr(entry, field) for field in TITLE_FIELDS]
        if entry.chart_type.casefold() == KIND_CHART_TYPES['text'].casefold():
            content = row_format(entry).get('content')
            texts.append(str(content.get('text') or '') if isinstance(content, dict) else '')
        found.update(match.strip().casefold() for text in texts if '{' in text for match in TOKEN_PATTERN.findall(text))
    return found


def apply_tokens(entries: list[CatalogEntry], texts: dict[str, str], *, titles: bool = True) -> list[CatalogEntry]:
    """The rows with the tokens of their titles (unless ``titles`` is False) and text boxes written (``texts``:
    lower-case token -> text)."""
    if not texts:
        return entries
    result = []
    for entry in entries:
        changes = {field: _replace_tokens(getattr(entry, field), texts) for field in TITLE_FIELDS
                   if titles and '{' in getattr(entry, field)}
        result.append(_with_text_content(replace(entry, **changes) if changes else entry, texts))
    return result


def apply_parameters(entries: list[CatalogEntry], parameters: list[dict[str, Any]],
                     values: dict[str, Any] | None) -> list[CatalogEntry]:
    """The rows with the parameters replaced by the values of a Dashboard.

    A filter condition naming a field-values parameter set to All is left out; elsewhere the values are written as a
    comma-separated list (``City IN ({City})`` -> ``City IN (London, Leeds)``) and All as ``All`` in texts.
    """
    if not parameters:
        return entries
    texts: dict[str, str] = {}
    all_values: set[str] = set()
    for parameter in parameters:
        value = parameter_value(parameter, values)
        key = parameter['name'].casefold()
        texts[key] = _parameter_text(parameter, value)
        if parameter['type'] == 'values' and not (isinstance(value, list) and value):
            all_values.add(key)

    def resolve_filters(filters: str) -> str:
        if '{' not in filters:
            return filters
        kept = [condition for condition in filter_conditions(filters)
                if not any(match.strip().casefold() in all_values for match in TOKEN_PATTERN.findall(condition))]
        return join_conditions(_replace_tokens(condition, texts) for condition in kept)

    result = []
    for entry in entries:
        changes = {field: _replace_tokens(getattr(entry, field), texts)
                   for field in ('slide_title', 'slide_subtitle', 'chart_title', 'axis_x_range', 'axis_y_range')
                   if '{' in getattr(entry, field)}
        if '{' in entry.filters:
            changes['filters'] = resolve_filters(entry.filters)
        result.append(_with_text_content(replace(entry, **changes) if changes else entry, texts))
    return result


def slides_summary(slide_set: dict[str, Any]) -> dict[str, int]:
    slides = slide_set.get('slides') or []
    return {'slides': len(slides), 'elements': sum(len(slide.get('elements') or []) for slide in slides),
            'parameters': len(slide_set.get('parameters') or [])}
