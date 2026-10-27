"""Report Templates and PPT Dashboards without an NR Mode of their own.

A Report Template serves the CDRs of any NR Mode: the Dashboard that uses it chooses the NR Mode as part of its
selection, and the titles of the template name it with the tokens ``{NR Mode}`` (NSA or SA) and ``{NR Mode Name}``
(Non-Standalone or Standalone).

Templates and Dashboards were kept per NR Mode before, most of them as an NSA and an SA copy of the same template that
only told the mode apart in a title. ``merge_mode_templates`` turns each such pair into one template with the tokens,
both when a workspace is migrated and when a package or backup of before is imported, and returns how the old
templates are known now, so the Dashboards and jobs that named them follow (``migrate_dashboards_state``).
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from src.modules.nr_mode import DEFAULT_NR_MODE, normalize_nr_mode

NR_MODE_TOKEN = '{NR Mode}'
NR_MODE_NAME_TOKEN = '{NR Mode Name}'
# What each token reads as in each NR Mode.
NR_MODE_TOKEN_VALUES = {
    'NSA': {NR_MODE_TOKEN: 'NSA', NR_MODE_NAME_TOKEN: 'Non-Standalone'},
    'SA': {NR_MODE_TOKEN: 'SA', NR_MODE_NAME_TOKEN: 'Standalone'},
}
_TOKEN_PATTERN = re.compile(r'\{\s*NR\s*Mode(\s+Name)?\s*\}', re.IGNORECASE)
# The workspace setting that keeps how the templates of each NR Mode are known since they were merged, so a Dashboard
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


def render_nr_mode_tokens(text: str, nr_mode: object) -> str:
    """A template text with its NR Mode tokens written for an NR Mode (NSA when none is given)."""
    if not text or '{' not in text:
        return text
    values = NR_MODE_TOKEN_VALUES[normalize_nr_mode(nr_mode) or DEFAULT_NR_MODE]
    return _TOKEN_PATTERN.sub(lambda match: values[NR_MODE_NAME_TOKEN if match.group(1) else NR_MODE_TOKEN], text)


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


def migrate_dashboard_definition(definition: Any, renames: Mapping[tuple[str, str], str] | None = None,
                                 uids: Mapping[str, str] | None = None) -> Any:
    """A Dashboard saved with an NR Mode of its own and of its template (technology, template_technology): its NR Mode
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


def migrate_dashboards_state(dashboards: Mapping[str, Any], renames: Mapping[tuple[str, str], str] | None = None,
                             uids: Mapping[str, str] | None = None) -> tuple[dict[str, Any], bool]:
    """Every Dashboard of a workspace or package without an NR Mode of its own (migrate_dashboard_definition), their
    names unique as they are now in every NR Mode: an SA Dashboard named as an NSA one takes " (SA)"."""
    migrated = {key: migrate_dashboard_definition(value, renames, uids) for key, value in dashboards.items()}
    changed = migrated != dict(dashboards)
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
