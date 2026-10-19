"""Operator, Vendor and Campaign values found in the CDRs and the label the workspace maps give them.

The Operator Maps and Vendor Maps start from the values of the ready CDRs of the workspace: each
detected value is assigned to one label, and a label that stands for several detected values merges
them in every filter, table, chart and report. A value no map assigns keeps its own name and is
reported as unassigned until it is assigned. Campaigns follow the Campaign Maps pattern: a campaign
without a year and quarter and without an exception is unassigned.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterable

from src.modules.column_names import campaign_parts, campaign_sort_key, format_campaign

KINDS = ('operator', 'vendor', 'campaign')
KIND_TITLES = {'operator': 'Operators', 'vendor': 'Vendors', 'campaign': 'Campaigns'}
# The cached CDR catalogue field holding each kind of value.
CATALOGUE_FIELDS = {'operator': 'operators', 'vendor': 'vendors_only', 'campaign': 'campaigns'}
_ALL_SUFFIX = re.compile(r'\s+- All(?: Vendors)?$', re.IGNORECASE)
# The comments of the Operator names of the CDRs (what each one holds, as a reminder), ``{name: comment}``.
NAME_COMMENTS_STATE_KEY = 'operator_name_comments'
MAX_NAME_COMMENT_LENGTH = 1000


def detected_values(catalogues: dict[int, dict[str, list[str]]], dataset_names: dict[int, str],
                    operator_mappings: dict[str, str] | None = None) -> dict[str, dict[str, list[str]]]:
    """``{kind: {value: [CDR names]}}`` for the Operators, Vendors and Campaigns of the CDRs.

    Values differing only in case are one value. Vendors leave out the operator-only identities
    (``<Operator> - All`` and Operator names), which are not Vendors.
    """
    found: dict[str, dict[str, tuple[str, list[str]]]] = {kind: {} for kind in KINDS}
    for dataset_id, catalogue in catalogues.items():
        name = dataset_names.get(dataset_id) or f'CDR {dataset_id}'
        for kind, field in CATALOGUE_FIELDS.items():
            for value in catalogue.get(field) or []:
                text = str(value).strip()
                if not text:
                    continue
                entry = found[kind].setdefault(text.casefold(), (text, []))
                if name not in entry[1]:
                    entry[1].append(name)
    operators = {*found['operator'], *(str(key).casefold() for key in (operator_mappings or {})),
                 *(str(value).casefold() for value in (operator_mappings or {}).values())}
    found['vendor'] = {key: entry for key, entry in found['vendor'].items()
                       if key not in operators and not _ALL_SUFFIX.search(entry[0])}
    return {kind: {value: sorted(names, key=str.casefold) for value, names in entries.values()}
            for kind, entries in found.items()}


def value_campaigns(catalogues: dict[int, dict[str, list[str]]], nr_modes: dict[int, str | None],
                    campaign_map: dict | None = None, field: str = 'operators') -> dict[str, list[str]]:
    """``{value (casefolded): ['26-Q2 (NSA)', …]}``: the campaigns, as the Campaign Maps show them, with the NR Mode of
    their CDR, where each value of the CDRs appears.

    Two names with one label are only added up as one where they coincide: in the same campaign and NR Mode (the NSA
    and SA tests of a campaign are never scored together). A CDR without campaigns counts as one campaign of its own.
    """
    found: dict[str, set[tuple[str, str]]] = {}
    # Each label in the order of the campaigns it stands for (a label such as 26-Q2 has no full year to order by).
    orders: dict[str, tuple] = {'': (-2, -2, -2, -2, '')}
    for dataset_id, catalogue in catalogues.items():
        mode = str(nr_modes.get(dataset_id) or '')
        labels = set()
        for value in catalogue.get('campaigns') or []:
            if str(value).strip():
                label = format_campaign(value, campaign_map)
                labels.add(label)
                orders.setdefault(label, campaign_sort_key(value, campaign_map))
        keys = {(label, mode) for label in labels or {''}}
        for value in catalogue.get(field) or []:
            text = str(value).strip()
            if text:
                found.setdefault(text.casefold(), set()).update(keys)

    def order(key: tuple[str, str]) -> tuple:
        return (orders[key[0]], key[1])

    def name(key: tuple[str, str]) -> str:
        label = key[0] or 'No campaign'
        return f'{label} ({key[1]})' if key[1] else label

    return {value: [name(key) for key in sorted(keys, key=order)] for value, keys in found.items()}


def coinciding_values(values: Iterable[str], campaigns: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    """The values that coincide with another one in a campaign and NR Mode (see ``value_campaigns``), in their order,
    and the campaigns where they coincide."""
    values = list(values)
    keys = {value: list(dict.fromkeys(campaigns.get(value.casefold()) or [])) for value in values}
    counts: dict[str, int] = {}
    for value in values:
        for key in keys[value]:
            counts[key] = counts.get(key, 0) + 1
    shared = [key for key in dict.fromkeys(key for value in values for key in keys[value]) if counts[key] >= 2]
    return [value for value in values if any(counts[key] >= 2 for key in keys[value])], shared



def normalize_name_comments(value: Any) -> dict[str, str]:
    """The comments of some names, without blanks (a name keeps the first spelling given, compared without case)."""
    if not isinstance(value, dict):
        raise ValueError('The comments of the Operator names must be an object of name: comment.')
    comments: dict[str, str] = {}
    seen: set[str] = set()
    for name, comment in value.items():
        name, text = str(name or '').strip(), str(comment or '').strip()[:MAX_NAME_COMMENT_LENGTH]
        if name and text and name.casefold() not in seen:
            seen.add(name.casefold())
            comments[name] = text
    return comments


def load_name_comments(repository: Any) -> dict[str, str]:
    """The comments of the Operator names of the workspace."""
    try:
        return normalize_name_comments(json.loads(repository.get_workspace_state(NAME_COMMENTS_STATE_KEY) or '{}'))
    except (TypeError, ValueError):
        return {}


def save_name_comments(repository: Any, comments: dict[str, str]) -> None:
    repository.set_workspace_state(NAME_COMMENTS_STATE_KEY, json.dumps(normalize_name_comments(comments), ensure_ascii=False))


def comment_changes(stored: dict[str, str], submitted: Iterable[tuple[str, str]]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """The comments after saving those of some names (a blank one removes it) and ``{name: [before, after]}`` of those
    that change; the comments of the other names are kept."""
    comments = dict(stored)
    changes: dict[str, list[str]] = {}
    for name, comment in submitted:
        name, text = str(name or '').strip(), str(comment or '').strip()[:MAX_NAME_COMMENT_LENGTH]
        if not name:
            continue
        key = next((existing for existing in comments if existing.casefold() == name.casefold()), None)
        before = comments.get(key, '') if key else ''
        if before == text:
            continue
        changes[key or name] = [before, text]
        if key:
            del comments[key]
        if text:
            comments[key or name] = text
    return comments, changes

def campaign_assignment(value: str, campaign_map: dict) -> tuple[str, bool]:
    """The label of a campaign and whether the Campaign Map assigns it (an exception or a year and quarter)."""
    label = format_campaign(value, campaign_map)
    if any(value.casefold() in {source.casefold() for source in item['sources']}
           or value.casefold() == item['label'].casefold() for item in campaign_map.get('exceptions') or []):
        return label, True
    year, quarter, _mode = campaign_parts(value)
    return label, bool(year and quarter)


def assignment_rows(kind: str, detected: dict[str, list[str]], mappings: dict[str, str],
                    campaign_map: dict | None = None,
                    campaigns: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """One row per detected value: its CDRs, label, whether it is assigned and the values merged with it.

    With ``campaigns`` (see ``value_campaigns``) each row also has its ``campaigns`` and a value is merged only with the
    values of its label that coincide with it in a campaign and NR Mode (``merged_in``); the others only share the label
    (``shares_label_with``).
    Unassigned values come first, then by label and value.
    """
    rows = []
    for value, cdrs in detected.items():
        if kind == 'campaign':
            label, assigned = campaign_assignment(value, campaign_map or {})
        else:
            mapped = mappings.get(value.casefold())
            label, assigned = (mapped, True) if mapped else (value, False)
        rows.append({'value': value, 'cdrs': cdrs, 'label': label, 'assigned': assigned,
                     # The canonical label of its own group: renaming the group changes it.
                     'canonical': assigned and kind != 'campaign' and label.casefold() == value.casefold()})
    members: dict[str, list[str]] = {}
    for row in rows:
        if row['assigned']:
            members.setdefault(row['label'].casefold(), []).append(row['value'])
    for row in rows:
        group = members.get(row['label'].casefold(), []) if row['assigned'] else []
        others = sorted((value for value in group if value != row['value']), key=str.casefold)
        if campaigns is None:
            row['merged_with'] = others
            continue
        own = row['campaigns'] = campaigns.get(row['value'].casefold()) or []
        row['merged_with'] = [value for value in others if set(own) & set(campaigns.get(value.casefold()) or [])]
        row['merged_in'] = [key for key in own if any(key in (campaigns.get(value.casefold()) or [])
                                                      for value in row['merged_with'])]
        row['shares_label_with'] = [value for value in others if value not in row['merged_with']]
    return sorted(rows, key=lambda row: (row['assigned'], row['label'].casefold(), row['value'].casefold()))


def unassigned_values(rows_by_kind: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    """The unassigned values of each kind (only the kinds that have some)."""
    result = {kind: sorted((row['value'] for row in rows if not row['assigned']), key=str.casefold)
              for kind, rows in rows_by_kind.items()}
    return {kind: values for kind, values in result.items() if values}


def assignment_effects(
    kind: str, assignments: Iterable[tuple[str, str | None]], detected: Iterable[str], mappings: dict[str, str],
    canonical_labels: Iterable[str], rename: tuple[str, str] | None = None,
    saved_filters: Callable[[str], int] | None = None, campaigns: dict[str, list[str]] | None = None,
) -> dict[str, list[Any]]:
    """What saving some assignments does, to confirm it first.

    ``assignments`` are ``(source value, label)`` pairs; a ``None`` label leaves the value unassigned.
    ``rename`` is the ``(old, new)`` canonical label of a group saved under another name. The result lists:

    - ``merges``: labels that would stand for two or more detected values, other than they already do; with
      ``campaigns`` (see ``value_campaigns``) only the values that coincide in a campaign and NR Mode, and where;
    - ``moved``: values leaving their label, with how many saved filters use that label (and so stop
      including the value);
    - ``underscores``: new Operator or Vendor labels with ``_``, the Operator_Vendor separator.
    """
    detected = list(detected)
    canonical_labels = [str(label) for label in canonical_labels]
    current = {str(source).casefold(): str(label) for source, label in mappings.items()}
    old_name, new_name = rename or ('', '')

    def renamed(label: str | None) -> str | None:
        return new_name if label and old_name and label.casefold() == old_name.casefold() else label

    before = {source: renamed(label) for source, label in current.items()}
    after = dict(before)
    existing = {label.casefold(): label for label in canonical_labels}
    if rename:
        existing.pop(old_name.casefold(), None)
        existing[new_name.casefold()] = new_name
    changes: list[tuple[str, str | None]] = []
    for source, label in assignments:
        source = str(source).strip()
        label = str(label).strip() if label is not None else None
        if not source:
            continue
        label = existing.get(label.casefold(), label) if label else None
        changes.append((source, label))
        if label:
            after[source.casefold()] = label
        else:
            after.pop(source.casefold(), None)

    def members(mapping: dict[str, str | None], label: str) -> list[str]:
        values = sorted((value for value in detected if (mapping.get(value.casefold()) or '').casefold() == label.casefold()),
                        key=str.casefold)
        return values if campaigns is None else coinciding_values(values, campaigns)[0]

    merges, seen = [], set()
    for _source, label in changes:
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        values = members(after, label)
        if len(values) >= 2 and values != members(before, label):
            merges.append({'label': label, 'values': values} if campaigns is None
                          else {'label': label, 'values': values, 'campaigns': coinciding_values(values, campaigns)[1]})
    moved = []
    for source, label in changes:
        previous = current.get(source.casefold())
        if not previous or previous.casefold() == source.casefold():
            continue
        if label and (renamed(previous) or '').casefold() == label.casefold():
            continue
        moved.append({'value': source, 'from': previous, 'to': label,
                      'filters': saved_filters(previous) if saved_filters else 0})
    underscores = []
    if kind in {'operator', 'vendor'}:
        underscores = sorted({label for _source, label in changes
                              if label and '_' in label and label.casefold() not in {
                                  value.casefold() for value in canonical_labels}}, key=str.casefold)
    return {'merges': merges, 'moved': moved, 'underscores': underscores}
