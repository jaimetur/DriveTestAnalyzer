"""Report Templates and PPT Designer without an NR Mode of their own.

A Report Template serves the CDRs of any NR Mode: the Design that uses it chooses the NR Mode as part of its
selection (NSA, SA or both, NSA & SA), and the titles of the template name it with the tokens ``{NR Mode}`` (NSA, SA or
NSA & SA) and ``{NR Mode Name}`` (Non-Standalone, Standalone or Non-Standalone & Standalone). Each row of the combined
CDR tables keeps the NR Mode of its CDR in the NR Mode field: a chart keeps one NR Mode with a filter (NR Mode IN (SA)),
and splits or colours its series by it (``entry_for_nr_mode``).

Templates and Designs were kept per NR Mode before, most of them as an NSA and an SA copy of the same template that
only told the mode apart in a title. ``merge_mode_templates`` turns each such pair into one template with the tokens,
both when a workspace is migrated and when a package or backup of before is imported, and returns how the old
templates are known now, so the Designs and jobs that named them follow (``migrate_designs_state``).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from src.modules.column_names import column_identity
from src.modules.nr_mode import DEFAULT_NR_MODE, NR_MODES, NSA_VS_SA, normalize_nr_mode, normalize_scoring_nr_mode, nr_modes_of

NR_MODE_TOKEN = '{NR Mode}'
NR_MODE_NAME_TOKEN = '{NR Mode Name}'
# What each token reads as in each NR Mode.
NR_MODE_TOKEN_VALUES = {
    'NSA': {NR_MODE_TOKEN: 'NSA', NR_MODE_NAME_TOKEN: 'Non-Standalone'},
    'SA': {NR_MODE_TOKEN: 'SA', NR_MODE_NAME_TOKEN: 'Standalone'},
    NSA_VS_SA: {NR_MODE_TOKEN: 'NSA & SA', NR_MODE_NAME_TOKEN: 'Non-Standalone & Standalone'},
}
# The NR Mode a Design reads, as its selectors and file names show it.
DESIGN_NR_MODE_LABELS = {'NSA': 'NSA', 'SA': 'SA', NSA_VS_SA: 'NSA & SA'}
NR_MODE_SPLIT_FIELD = 'NR Mode'
# The chart types whose Columns are the horizontal axis of their lines or areas.
LINE_AXIS_CHART_TYPES = frozenset({'lines', 'dual lines', 'areas', '100% stacked areas', 'bars and line'})
_TOKEN_PATTERN = re.compile(r'\{\s*NR\s*Mode(\s+Name)?\s*\}', re.IGNORECASE)
# The workspace setting that keeps how the templates of each NR Mode are known since they were merged, so a Design
# or a package of before still finds its template: {"renames": {"nsa|NSA - X": "X"}, "uids": {old uid: new uid}}.
TEMPLATE_MODE_MERGE_STATE_KEY = 'report_template_nr_mode_merge_v1'
# The columns of a template row whose text may name the NR Mode (a merge only tells the modes apart in them).
_TITLE_COLUMNS = frozenset({'slidetittle', 'slidesubtittle', 'charttittle', 'slidetitle', 'slidesubtitle', 'charttitle'})
_MODE_WORDS = {
    'NSA': ((re.compile(r'\bNon[- ]?Standalone\b', re.IGNORECASE), NR_MODE_NAME_TOKEN), (re.compile(r'\bNSA\b'), NR_MODE_TOKEN)),
    'SA': ((re.compile(r'(?<!Non-)(?<!Non )\bStandalone\b', re.IGNORECASE), NR_MODE_NAME_TOKEN), (re.compile(r'\bSA\b'), NR_MODE_TOKEN)),
}
_NAME_PREFIX = re.compile(r'^\s*(NSA|SA)\s*[-–—_:]\s*(.+?)\s*$', re.IGNORECASE)
_NAME_SUFFIX = re.compile(r'^\s*(.+?)\s*(?:[-–—_]\s*(NSA|SA)|\(\s*(NSA|SA)\s*\))\s*$', re.IGNORECASE)


def design_nr_mode_value(value: object) -> str:
    """The NR Mode of the CDRs a Design reads: NSA, SA or NSA+SA (both, NSA & SA); NSA when none is given."""
    text = str(value or '').strip()
    if text.replace(' ', '').upper() in {'NSA&SA', 'NSAANDSA'}:
        return NSA_VS_SA
    return normalize_scoring_nr_mode(text) or DEFAULT_NR_MODE


def render_nr_mode_tokens(text: str, nr_mode: object) -> str:
    """A template text with its NR Mode tokens written for an NR Mode (NSA when none is given)."""
    if not text or '{' not in text:
        return text
    values = NR_MODE_TOKEN_VALUES[design_nr_mode_value(nr_mode)]
    return _TOKEN_PATTERN.sub(lambda match: values[NR_MODE_NAME_TOKEN if match.group(1) else NR_MODE_TOKEN], text)


def chart_filter_nr_modes(entry: Any) -> tuple[str, ...]:
    """The NR Modes the Filters of a chart row keep (NR Mode IN (SA), NR Mode = NSA, NR Mode NOT IN (SA))."""
    from src.modules.cdr_reporting import parse_catalog_filters

    modes = set(NR_MODES)
    try:
        conditions = parse_catalog_filters(str(getattr(entry, 'filters', '') or ''))
    except ValueError:
        return tuple(NR_MODES)
    for condition in conditions:
        if column_identity(condition.column) != column_identity(NR_MODE_SPLIT_FIELD):
            continue
        values = {normalize_nr_mode(value) for value in condition.values} - {None}
        if condition.operator in {'IN', '='}:
            modes &= values
        elif condition.operator in {'NOT IN', '!='}:
            modes -= values
    return tuple(mode for mode in NR_MODES if mode in modes)


def chart_fields(entry: Any) -> list[str]:
    """The CDR fields a chart row reads: its KPI, filters, splits, legend and dynamic fields (not NR Mode, which every
    row has)."""
    from src.modules.cdr_reporting import (
        CHART_SETTING_FILTERS, _legend_dimensions, catalog_kpi_fields, entry_dynamic_fields, parse_catalog_filters,
        parse_catalog_grouping,
    )
    from src.modules.chart_types import date_bin_parts

    try:
        fields = [*catalog_kpi_fields(entry.kpi), *parse_catalog_grouping(entry.rows_split).dimensions,
                  *parse_catalog_grouping(entry.columns_split).dimensions, *_legend_dimensions(entry.legend),
                  *(condition.column for condition in parse_catalog_filters(entry.filters)), *entry_dynamic_fields(entry)]
    except ValueError:
        return []
    skipped = {*CHART_SETTING_FILTERS, column_identity(NR_MODE_SPLIT_FIELD)}
    # A date field grouped by a period (DAY(Test_Start_Time)) reads the date field.
    fields = [date_bin_parts(field)[1] if date_bin_parts(field) else field for field in fields]
    return list(dict.fromkeys(field for field in fields if str(field).strip() and column_identity(field) not in skipped))


def missing_nr_mode_fields(entry: Any, fields_by_mode: Mapping[str, set[str]], nr_mode: object = NSA_VS_SA) -> dict[str, list[str]]:
    """The fields of a chart that the CDRs of an NR Mode it shows do not have while those of the other one do, by that
    NR Mode: the chart has no samples of it. ``fields_by_mode``: the field identities of the CDRs of each NR Mode."""
    if not entry.source_kind or entry.source_kind == 'all' or entry.structural_type:
        return {}
    read = nr_modes_of(design_nr_mode_value(nr_mode))
    missing: dict[str, list[str]] = {}
    for mode in chart_filter_nr_modes(entry):
        others = [fields_by_mode.get(other) for other in NR_MODES if other != mode]
        if mode not in read or mode not in fields_by_mode or not any(others):
            continue
        absent = [field for field in chart_fields(entry) if column_identity(field) not in fields_by_mode[mode]
                  and any(column_identity(field) in fields for fields in others if fields)]
        if absent:
            missing[mode] = absent
    return missing


def missing_nr_mode_note(missing: Mapping[str, list[str]]) -> str:
    """What a chart says when the CDRs of an NR Mode lack some of its fields."""
    return ' '.join(f"The {mode} CDRs have no {', '.join(fields)}: no {mode} samples." for mode, fields in missing.items())


def _names_field(value: str, names: set[str]) -> bool:
    return any(column_identity(part) in names for part in re.split(r'\s*×\s*|\s+\bx\b\s+|,|/', value or '') if part.strip())


def entry_for_nr_mode(entry: Any, nr_mode: object) -> Any:
    """A chart row of a template as a Design that reads the CDRs of an NR Mode (NSA, SA or NSA+SA) shows it.

    Its slide titles name the NR Mode of the Design and its chart title the NR Modes the chart shows (those its
    filters keep, NR Mode IN (SA)). A chart that shows both NR Modes and tells them apart neither by NR Mode nor by
    Campaign (whose SA campaigns name the mode) gets the NR Mode as the last level of the split that holds its legend
    (of Rows for lines and areas, whose Columns are their axis), and of its legend: the NSA and SA tests of an operator
    are never added together.
    """
    from dataclasses import replace

    from src.modules.cdr_reporting import _legend_dimensions, entry_dynamic_fields, parse_catalog_grouping

    design_mode = design_nr_mode_value(nr_mode)
    shown = [mode for mode in chart_filter_nr_modes(entry) if mode in (NR_MODES if design_mode == NSA_VS_SA else (design_mode,))]
    chart_mode = NSA_VS_SA if len(shown) > 1 else (shown[0] if shown else design_mode)
    changes: dict[str, Any] = {
        'slide_title': render_nr_mode_tokens(entry.slide_title, design_mode),
        'slide_subtitle': render_nr_mode_tokens(entry.slide_subtitle, design_mode),
        'chart_title': render_nr_mode_tokens(entry.chart_title, chart_mode),
    }
    if len(shown) > 1 and entry.source_kind and not entry.structural_type:
        names = {column_identity(NR_MODE_SPLIT_FIELD), column_identity('Campaign')}
        told_apart = any(_names_field(value, names) for value in (
            entry.rows_split, entry.columns_split, entry.legend, *entry_dynamic_fields(entry)))
        legend = _legend_dimensions(entry.legend)
        legend_keys = {column_identity(value) for value in legend}
        rows = parse_catalog_grouping(entry.rows_split).dimensions
        columns = parse_catalog_grouping(entry.columns_split).dimensions
        axis = next((name for name, dimensions in (('columns_split', columns), ('rows_split', rows))
                     if legend_keys & {column_identity(value) for value in dimensions}), None)
        axis = axis or ('columns_split' if columns else 'rows_split' if rows else None)
        # The Columns of a line or an area are its horizontal axis: the NR Mode gives them their series instead.
        if axis and entry.chart_type.strip().casefold() in LINE_AXIS_CHART_TYPES:
            axis = 'rows_split'
        if not told_apart and axis:
            changes[axis] = ' × '.join([*(columns if axis == 'columns_split' else rows), NR_MODE_SPLIT_FIELD])
            if legend:
                changes['legend'] = ', '.join([*legend, NR_MODE_SPLIT_FIELD])
    return replace(entry, **changes)


def _tokenized(text: str, nr_mode: str) -> str:
    for pattern, token in _MODE_WORDS[nr_mode]:
        text = pattern.sub(token, text)
    return text


def _without_tokens(text: str) -> str:
    return ' '.join(_TOKEN_PATTERN.sub(' ', text).split())


def merged_title(nsa_text: str, sa_text: str) -> str | None:
    """The title that reads as each one in its NR Mode, or None when they differ in more than the words naming it.

    A title only one mode names (RF Quality Analysis and SA RF Quality Analysis) takes the token in both.
    """
    if nsa_text == sa_text:
        return nsa_text
    candidates = [candidate for candidate in (_tokenized(sa_text, 'SA'), _tokenized(nsa_text, 'NSA'))
                  if _TOKEN_PATTERN.search(candidate)]
    for candidate in candidates:
        if render_nr_mode_tokens(candidate, 'NSA') == nsa_text and render_nr_mode_tokens(candidate, 'SA') == sa_text:
            return candidate
    for candidate in candidates:
        if render_nr_mode_tokens(candidate, 'SA') == sa_text and _without_tokens(candidate) == ' '.join(nsa_text.split()):
            return candidate
        if render_nr_mode_tokens(candidate, 'NSA') == nsa_text and _without_tokens(candidate) == ' '.join(sa_text.split()):
            return candidate
    return None


def _csv_rows(content: bytes | str) -> list[list[str]] | None:
    try:
        text = content.decode('utf-8-sig') if isinstance(content, bytes) else content
        return list(csv.reader(io.StringIO(text)))
    except (UnicodeDecodeError, csv.Error):
        return None


def merged_template_content(nsa_content: bytes, sa_content: bytes) -> bytes | None:
    """One template for an NSA and an SA template that only differ in the titles naming the mode, else None."""
    nsa_rows, sa_rows = _csv_rows(nsa_content), _csv_rows(sa_content)
    if not nsa_rows or not sa_rows or len(nsa_rows) != len(sa_rows) or nsa_rows[0] != sa_rows[0]:
        return None
    header = nsa_rows[0]
    title_columns = {index for index, name in enumerate(header) if re.sub(r'[^a-z]', '', name.casefold()) in _TITLE_COLUMNS}
    merged: list[list[str]] = [header]
    for nsa_row, sa_row in zip(nsa_rows[1:], sa_rows[1:], strict=True):
        if len(nsa_row) != len(sa_row):
            return None
        row = []
        for index, (nsa_cell, sa_cell) in enumerate(zip(nsa_row, sa_row, strict=True)):
            if nsa_cell == sa_cell:
                row.append(nsa_cell)
                continue
            cell = merged_title(nsa_cell, sa_cell) if index in title_columns else None
            if cell is None:
                return None
            row.append(cell)
        merged.append(row)
    output = io.StringIO(newline='')
    csv.writer(output, lineterminator='\n').writerows(merged)
    return output.getvalue().encode('utf-8')


def template_base_name(name: str, nr_mode: str) -> str:
    """The name of a template without the NR Mode it names (NSA - X, X (SA), X - SA), when it is its own mode."""
    match = _NAME_PREFIX.match(name)
    if match and match.group(1).upper() == nr_mode:
        return match.group(2).strip()
    match = _NAME_SUFFIX.match(name)
    if match and (match.group(2) or match.group(3) or '').upper() == nr_mode:
        return match.group(1).strip()
    return name.strip()


@dataclass
class TemplateMerge:
    """The templates of a workspace or package without NR Mode, and how the templates of before are known now."""
    templates: list[dict[str, Any]] = field(default_factory=list)
    # (technology, old name) -> name now, for every template whose name changed.
    renames: dict[tuple[str, str], str] = field(default_factory=dict)
    # Every old uid -> its uid now (the SA template of a merged pair takes the NSA one).
    uids: dict[str, str] = field(default_factory=dict)
    # (NSA name, SA name, merged name) of each merged pair.
    merged: list[tuple[str, str, str]] = field(default_factory=list)

    def state(self) -> dict[str, Any]:
        return {'renames': {f'{technology}|{name}': new for (technology, name), new in self.renames.items()},
                'uids': dict(self.uids)}


def _unique(name: str, taken: set[str]) -> str:
    candidate, number = name, 2
    while candidate.casefold() in taken:
        candidate = f'{name} ({number})'
        number += 1
    taken.add(candidate.casefold())
    return candidate


def merge_mode_templates(templates: Iterable[Mapping[str, Any]]) -> TemplateMerge:
    """Turn the templates of each NR Mode (dicts with technology, name, content and optionally uid, is_default,
    created_by, created_at, updated_at, updated_by) into templates without NR Mode.

    An NSA and an SA template whose names only differ in the mode they name (NSA - X and SA - X) and whose contents only
    differ in the titles naming it become one template X with the NR Mode tokens, keeping the identity, creator and
    creation of the NSA one. The others keep their name, an SA one that has the name of an NSA one taking " (SA)".
    """
    rows = [dict(row) for row in templates]
    by_mode = {mode: [row for row in rows if str(row.get('technology') or '').casefold() == mode] for mode in ('nsa', 'sa')}
    result = TemplateMerge()
    paired: set[int] = set()
    taken: set[str] = set()
    merged_rows: list[tuple[dict[str, Any], dict[str, Any] | None, bytes | None]] = []
    for nsa in by_mode['nsa']:
        base = template_base_name(str(nsa['name']), 'NSA')
        partner = next((sa for sa in by_mode['sa'] if id(sa) not in paired
                        and template_base_name(str(sa['name']), 'SA').casefold() == base.casefold()), None)
        content = merged_template_content(bytes(nsa.get('content') or b''), bytes(partner.get('content') or b'')) \
            if partner is not None else None
        if partner is not None and content is not None:
            paired.add(id(partner))
            merged_rows.append((nsa, partner, content))
        else:
            merged_rows.append((nsa, None, None))
    merged_rows += [(sa, None, None) for sa in by_mode['sa'] if id(sa) not in paired]
    # Names of the merged pairs first, then those kept as they are, then the SA ones that need " (SA)".
    names: dict[int, str] = {}
    for index, (row, partner, _content) in enumerate(merged_rows):
        if partner is not None:
            base = template_base_name(str(row['name']), 'NSA')
            names[index] = _unique(base, taken)
    for index, (row, partner, _content) in enumerate(merged_rows):
        if partner is None and str(row['name']).casefold() not in taken:
            names[index] = str(row['name'])
            taken.add(names[index].casefold())
    for index, (row, partner, _content) in enumerate(merged_rows):
        if index not in names:
            names[index] = _unique(f"{row['name']} ({str(row.get('technology') or '').upper()})", taken)
    # One default template: the NSA default one, else the SA one.
    default_index = next((index for mode in ('nsa', 'sa') for index, (row, partner, _content) in enumerate(merged_rows)
                          if any(item is not None and item.get('is_default') and str(item.get('technology') or '').casefold() == mode
                                 for item in (row, partner))), None)
    for index, (row, partner, content) in enumerate(merged_rows):
        name = names[index]
        template = {
            'name': name, 'content': content if content is not None else bytes(row.get('content') or b''),
            'is_default': index == default_index, 'uid': str(row.get('uid') or ''),
            'created_by': str(row.get('created_by') or ''), 'created_at': row.get('created_at'),
            'updated_at': max((str(item.get('updated_at') or '') for item in (row, partner) if item), default='') or row.get('updated_at'),
            'updated_by': str(((partner if partner and str(partner.get('updated_at') or '') > str(row.get('updated_at') or '') else row)
                               .get('updated_by')) or ''),
        }
        result.templates.append(template)
        for item in (row, partner):
            if item is None:
                continue
            technology = str(item.get('technology') or '').casefold()
            if str(item['name']) != name:
                result.renames[(technology, str(item['name']))] = name
            if item.get('uid') and template['uid'] and str(item['uid']) != template['uid']:
                result.uids[str(item['uid'])] = template['uid']
        if partner is not None:
            result.merged.append((str(row['name']), str(partner['name']), name))
    return result


def merge_state(value: object) -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """The renames and uids a workspace keeps since its templates were merged (see TemplateMerge.state)."""
    if not isinstance(value, Mapping):
        return {}, {}
    renames = {}
    for key, name in (value.get('renames') or {}).items():
        technology, _separator, old = str(key).partition('|')
        renames[(technology.casefold(), old)] = str(name)
    return renames, {str(old): str(new) for old, new in (value.get('uids') or {}).items()}


def migrate_design_definition(definition: Any, renames: Mapping[tuple[str, str], str] | None = None,
                                 uids: Mapping[str, str] | None = None) -> Any:
    """A Design saved with an NR Mode of its own and of its template (technology, template_technology): its NR Mode
    is now part of its selection (nr_mode) and its template is the one its template is known as now."""
    if not isinstance(definition, dict) or not ({'technology', 'template_technology'} & set(definition)):
        return definition
    updated = dict(definition)
    technology = updated.pop('technology', None)
    template_technology = updated.pop('template_technology', None)
    mode = normalize_nr_mode(updated.get('nr_mode')) or normalize_nr_mode(technology) \
        or normalize_nr_mode(template_technology) or DEFAULT_NR_MODE
    updated['nr_mode'] = mode
    library = str(template_technology or technology or mode).casefold()
    template = str(updated.get('template') or '')
    if renames and (library, template) in renames:
        updated['template'] = renames[(library, template)]
    if uids and str(updated.get('template_uid') or '') in uids:
        updated['template_uid'] = uids[str(updated['template_uid'])]
    return updated


def migrate_designs_state(designs: Mapping[str, Any], renames: Mapping[tuple[str, str], str] | None = None,
                             uids: Mapping[str, str] | None = None) -> tuple[dict[str, Any], bool]:
    """Every Design of a workspace or package without an NR Mode of its own (migrate_design_definition), their
    names unique as they are now in every NR Mode: an SA Design named as an NSA one takes " (SA)"."""
    migrated = {key: migrate_design_definition(value, renames, uids) for key, value in designs.items()}
    changed = migrated != dict(designs)
    taken: set[str] = set()
    for key in sorted(migrated, key=lambda item: (str((migrated[item] or {}).get('nr_mode') if isinstance(migrated[item], dict) else ''), str(item))):
        definition = migrated[key]
        if not isinstance(definition, dict) or not str(definition.get('name') or '').strip():
            continue
        name = str(definition['name']).strip()
        if name.casefold() in taken:
            migrated[key] = {**definition, 'name': _unique(f"{name} ({definition.get('nr_mode') or DEFAULT_NR_MODE})", taken)}
            changed = True
        else:
            taken.add(name.casefold())
    return migrated, changed
