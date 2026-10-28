"""What an import changed in an element (Import / Export and Transfer): the items of the package it added, those whose
values it changed (and what changed) and those it left as they were.

An element is read as its export document before and after the import. Each item of the package is found in the
document after the import (by its identity, then by its name), and that one in the document before (by its key in the
workspace, its identity, then its name): an item only after the import is new, and one whose values differ is
updated. Items only the workspace has are not counted, and neither are the values that say when or in which order an
item was saved, or how often it was used.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

# Values that say when, by whom or in which order an item was saved (or how often it was used), not what it is.
IGNORED_FIELDS = frozenset({'uid', 'id', 'created_at', 'updated_at', 'updated_by', 'position', 'use_count', 'last_used_at',
                            'version'})
# Values inside the values of an item (the rows of a list, the entries of a section) that only say when or by whom
# they were saved, which an import writes again when it saves them (the Map Areas, the personal NQ table layouts).
NESTED_IGNORED_FIELDS = frozenset({'created_at', 'updated_at', 'updated_by', 'last_used_at', 'use_count'})
# Values told as changed without telling them.
SENSITIVE_FIELDS = frozenset({'password_hash'})
FIELD_LABELS = {
    'password_hash': 'Password', 'query_sql': 'SQL', 'is_default': 'Default', 'default': 'Default', 'created_by': 'Creator',
    'assigned_to': 'Assignee', 'cdrs': 'CDRs', 'nr_mode': 'NR Mode', 'access_requested_at': 'Access Request',
    'send_email': 'Send Email', 'scoring_profile_id': 'Scoring Methodology', 'context_filters': 'Filters',
    'area_summary': 'Geographical Areas & Scoring Trends', 'operator_mappings': 'Operator Maps',
    'operator_name_comments': 'Comments of the Operator Names', 'vendor_mappings': 'Vendor Maps',
    'rca_result': 'RCA Result', 'prioritization': 'NQ Prioritization',
}
_ACRONYMS = {'sql', 'nr', 'cdr', 'cdrs', 'id', 'ids', 'ppt', 'nq', 'url', 'ni', 'sa', 'nsa', 'gap', 'kpi', 'kpis', 'csv', 'rca'}
# A value is told (before → after) when it is this short.
SHORT_VALUE_LENGTH = 60
# The values added to or removed from a list are told by name up to this many.
LISTED_VALUES = 6
# The elements whose updated items also tell each value before and after (the follow-up of the Non-Qualified Calls), how
# long a value they tell and how many items they tell so (the summary of a large import stays light).
DETAILED_ELEMENTS = frozenset({'nq-call-tracking'})
DETAIL_LENGTH = 2000
DETAILED_ITEMS = 300


@dataclass
class Item:
    """An item of an element as its export document has it: its name, its values, its identity (``uid``), what else
    finds it (``match``: its name without case unless given) and its key in the workspace (``key``) when it keeps it
    through the import."""
    name: str
    values: dict[str, Any]
    uid: str = ''
    match: str = ''
    key: str = ''

    def __post_init__(self) -> None:
        self.match = self.match or ' '.join(str(self.name).split()).casefold()


@dataclass
class Changes:
    """What an import did to the items of the package: the names of the new ones, the name and changes of the updated
    ones (with, for the elements told in detail, each value before and after, in ``details`` beside them) and how many were
    left as they were."""
    new: list[str] = field(default_factory=list)
    updated: list[tuple[str, list[str]]] = field(default_factory=list)
    unchanged: int = 0
    details: list[list[dict[str, str]]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.new) + len(self.updated) + self.unchanged

    def add(self, other: 'Changes') -> 'Changes':
        self.new += other.new
        self.updated += other.updated
        self.unchanged += other.unchanged
        self.details += other.details
        return self

    def update(self, name: str, described: list[str], details: list[dict[str, str]] | None = None) -> None:
        """An updated item with its changes (and its details, when told)."""
        self.updated.append((name, described))
        self.details.append(details or [])


def field_label(key: str, labels: dict[str, str] | None = None) -> str:
    """How a value is named in the completion message: ``modules_profile`` → ``Modules Profile``."""
    if labels and key in labels:
        return labels[key]
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    words = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(key)).replace('_', ' ').replace('-', ' ').split()
    return ' '.join(word.upper() if word.casefold() in _ACRONYMS else word[:1].upper() + word[1:] for word in words) or str(key)


def _short(value: Any) -> str | None:
    """A value as the completion message tells it, or ``None`` when it is too long to tell."""
    if value is None or value == '':
        return '(empty)'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str) and len(value) <= SHORT_VALUE_LENGTH and '\n' not in value:
        return value
    return None


def _comparable(value: Any) -> Any:
    """A value without the values inside it that only say when or by whom they were saved."""
    if isinstance(value, dict):
        return {key: _comparable(item) for key, item in value.items() if key not in NESTED_IGNORED_FIELDS}
    if isinstance(value, list):
        return [_comparable(item) for item in value]
    return value


def _canonical(value: Any) -> str:
    return json.dumps(_comparable(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def list_change(label: str, old: list[Any], new: list[Any]) -> str:
    """What changed in a list: its items with an identity new, edited or removed, or else the values added and removed."""
    def by_uid(items: list[Any]) -> dict[str, Any] | None:
        if not all(isinstance(item, dict) and str(item.get('uid') or '') for item in items):
            return None
        return {str(item['uid']): item for item in items}

    before, after = by_uid(old), by_uid(new)
    if before is not None and after is not None:
        counts = [(sum(uid not in before for uid in after), 'new'),
                  (sum(uid in before and _canonical(before[uid]) != _canonical(item) for uid, item in after.items()), 'edited'),
                  (sum(uid not in after for uid in before), 'removed')]
        parts = [f'{count} {word}' for count, word in counts if count]
        return f'{label}: {", ".join(parts)}' if parts else f'{label}: new order'
    old_counts, new_counts = Counter(_canonical(item) for item in old), Counter(_canonical(item) for item in new)
    added, removed = list((new_counts - old_counts).elements()), list((old_counts - new_counts).elements())
    if not added and not removed:
        return f'{label}: new order'
    values = [json.loads(item) for item in [*added, *removed]]
    if len(values) <= LISTED_VALUES and all(isinstance(value, str) and _short(value) for value in values):
        # As App Events tell them: ``Workspace Groups: +UK, −DE``.
        return f'{label}: ' + ', '.join([*(f'+{json.loads(item)}' for item in added), *(f'−{json.loads(item)}' for item in removed)])
    parts = [f'{len(added)} added' if added else '', f'{len(removed)} removed' if removed else '']
    return f'{label}: {", ".join(part for part in parts if part)}'


def describe_changes(before: dict[str, Any], after: dict[str, Any], labels: dict[str, str] | None = None) -> list[str]:
    """The values of an item that differ after the import, each as ``Label`` or ``Label: before → after``."""
    changes = []
    for key in dict.fromkeys([*before, *after]):
        if key in IGNORED_FIELDS:
            continue
        old, new = before.get(key), after.get(key)
        if _canonical(old if old is not None else '') == _canonical(new if new is not None else ''):
            continue
        label = field_label(key, labels)
        old_text, new_text = _short(old), _short(new)
        if key in SENSITIVE_FIELDS:
            changes.append(label)
        elif old_text is not None and new_text is not None:
            changes.append(f'{label}: {old_text} → {new_text}')
        elif isinstance(old if old is not None else [], list) and isinstance(new if new is not None else [], list):
            changes.append(list_change(label, old or [], new or []))
        else:
            changes.append(label)
    return changes


def _detail_text(value: Any) -> str:
    """A value as the details of a change tell it, whole up to a length (a comment as its author and text)."""
    if value is None or value == '' or value == []:
        return ''
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, dict) and 'body' in value:
        author = str(value.get('created_by') or '')
        value = f"{author}: {value.get('body') or ''}" if author else str(value.get('body') or '')
    elif not isinstance(value, str):
        value = json.dumps(_comparable(value), ensure_ascii=False, sort_keys=True, default=str)
    return value if len(value) <= DETAIL_LENGTH else value[:DETAIL_LENGTH] + '…'


def describe_details(before: dict[str, Any], after: dict[str, Any], labels: dict[str, str] | None = None) -> list[dict[str, str]]:
    """The values of an item that differ after the import, each as ``{label, before, after}`` with the whole values (the
    entries of a list with an identity, such as the comments, one by one: new, edited or removed)."""
    details = []
    for key in dict.fromkeys([*before, *after]):
        if key in IGNORED_FIELDS:
            continue
        old, new = before.get(key), after.get(key)
        if _canonical(old if old is not None else '') == _canonical(new if new is not None else ''):
            continue
        label = field_label(key, labels)
        if key in SENSITIVE_FIELDS:
            details.append({'label': label, 'before': '', 'after': 'Changed'})
            continue
        entries = lambda value: ({str(item['uid']): item for item in value}  # noqa: E731
                                 if isinstance(value, list) and all(isinstance(item, dict) and item.get('uid') for item in value) else None)
        was, now = entries(old or []), entries(new or [])
        if was is not None and now is not None:
            details += [{'label': f'{label} · new', 'before': '', 'after': _detail_text(item)} for uid, item in now.items() if uid not in was]
            details += [{'label': f'{label} · edited', 'before': _detail_text(was[uid]), 'after': _detail_text(item)}
                        for uid, item in now.items() if uid in was and _canonical(was[uid]) != _canonical(item)]
            details += [{'label': f'{label} · removed', 'before': _detail_text(item), 'after': ''} for uid, item in was.items() if uid not in now]
            continue
        details.append({'label': label, 'before': _detail_text(old), 'after': _detail_text(new)})
    return details


def _pairs(left: list[Item], right: list[Item], attributes: Iterable[str]) -> dict[int, int]:
    """Each item of ``left`` with the item of ``right`` it is (by their positions), found by each attribute in turn."""
    pairs: dict[int, int] = {}
    taken: set[int] = set()
    for attribute in attributes:
        positions: dict[str, list[int]] = {}
        for position, item in enumerate(right):
            if position not in taken and getattr(item, attribute):
                positions.setdefault(getattr(item, attribute), []).append(position)
        for position, item in enumerate(left):
            value = getattr(item, attribute)
            if position in pairs or not value:
                continue
            found = next((candidate for candidate in positions.get(value, ()) if candidate not in taken), None)
            if found is not None:
                pairs[position] = found
                taken.add(found)
    return pairs


def compare(package: list[Item], before: list[Item], after: list[Item], labels: dict[str, str] | None = None,
            detailed: bool = False) -> Changes:
    """What the import of the ``package`` items did, from the items of the element before and after it (``detailed``: with
    each value of the updated items before and after)."""
    touched = _pairs(package, after, ('uid', 'match'))
    previous = _pairs(after, before, ('key', 'uid', 'match'))
    changes = Changes()
    for position in sorted(set(touched.values())):
        item = after[position]
        if position not in previous:
            changes.new.append(item.name)
            continue
        described = describe_changes(before[previous[position]].values, item.values, labels)
        if described:
            changes.update(item.name, described, describe_details(before[previous[position]].values, item.values, labels)
                           if detailed and len(changes.updated) < DETAILED_ITEMS else None)
        else:
            changes.unchanged += 1
    return changes


def predict(package: list[Item], before: list[Item], labels: dict[str, str] | None = None, adjust=None,
            detailed: bool = False) -> Changes:
    """What importing the ``package`` items would do to the items of a workspace (``before``), for the preview of an
    import: each item replaces the one it finds (by its identity, then its name) with the values it carries, keeping
    those it does not carry, or is added. ``adjust(values, previous)`` gives the values of an item as the import would
    save them over the values it had (``{}`` for a new one)."""
    pairs = _pairs(package, before, ('uid', 'match'))
    changes = Changes()
    for position, item in enumerate(package):
        if position not in pairs:
            changes.new.append(item.name)
            continue
        previous = before[pairs[position]].values
        values = {**previous, **(adjust(dict(item.values), previous) if adjust else item.values)}
        described = describe_changes(previous, values, labels)
        if described:
            changes.update(item.name, described, describe_details(previous, values, labels)
                           if detailed and len(changes.updated) < DETAILED_ITEMS else None)
        else:
            changes.unchanged += 1
    return changes


def removed(before: list[Item], after: list[Item]) -> list[str]:
    """The names of the items of ``before`` that are not ``after`` (found by their key, their identity, then their
    name): those an import that replaces the whole element would remove."""
    kept = set(_pairs(after, before, ('key', 'uid', 'match')).values())
    return [item.name for position, item in enumerate(before) if position not in kept]


def compare_settings(name: str, before: dict[str, Any], after: dict[str, Any], labels: dict[str, str] | None = None,
                     described: list[str] | None = None) -> Changes:
    """What the import did to the settings of an element (``described`` tells their changes when given)."""
    described = describe_changes(before, after, labels) if described is None else described
    return Changes(updated=[(name, described)], details=[[]]) if described else Changes(unchanged=1)


def counted(count: int, singular: str, plural: str | None = None) -> str:
    """``1 workspace``, ``2 workspaces``."""
    return f'{count} {singular if count == 1 else plural or singular + "s"}'


def joined(parts: Iterable[str]) -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    parts = [part for part in parts if part]
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1] if parts else ''


def breakdown(changes: Changes) -> str:
    """``2 new, 1 updated and 29 unchanged`` (only the counts that are not zero)."""
    return joined([f'{len(changes.new)} new' if changes.new else '', f'{len(changes.updated)} updated' if changes.updated else '',
                   f'{changes.unchanged} unchanged' if changes.unchanged else ''])


def settings_breakdown(changes: Changes) -> str:
    """What the import did to the settings of the workspaces: ``updated``, ``unchanged`` or ``updated in 1 and
    unchanged in 2``."""
    if changes.count == 1:
        return 'updated' if changes.updated else 'unchanged'
    return joined([f'updated in {len(changes.updated)}' if changes.updated else '',
                   f'unchanged in {changes.unchanged}' if changes.unchanged else ''])


def _documents(value: Any, key: str) -> list[dict[str, Any]]:
    items = value.get(key) if isinstance(value, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def named_items(entries: Iterable[dict[str, Any]], name_key: str = 'name') -> list[Item]:
    """The items of a list of an export document, each with its ``uid``."""
    return [Item(name=str(entry.get(name_key) or ''), values=entry, uid=str(entry.get('uid') or ''))
            for entry in entries if str(entry.get(name_key) or '').strip()]


def users_access_items(document: Any) -> dict[str, list[Item]]:
    """The users, Modules Profiles and Workspace Groups of a Users & Access document."""
    return {'users': named_items(_documents(document, 'users'), 'username'),
            'modules_profiles': named_items(_documents(document, 'modules_profiles')),
            'workspace_groups': named_items(_documents(document, 'workspace_groups'))}


def ticket_items(document: Any) -> list[Item]:
    """The tickets of a Ticket Center document, with their comments and screenshots (not the changes of their fields,
    which their values tell)."""
    items = []
    for ticket in _documents(document, 'tickets'):
        if not str(ticket.get('uid') or '').strip():
            continue
        values = {key: value for key, value in ticket.items() if key not in {'comments', 'attachments'}}
        values['comments'] = [comment for comment in ticket.get('comments') or []
                              if isinstance(comment, dict) and comment.get('kind') != 'change']
        values['screenshots'] = [{key: value for key, value in attachment.items() if key != 'path'}
                                 for attachment in ticket.get('attachments') or [] if isinstance(attachment, dict)]
        items.append(Item(name=str(ticket.get('title') or ''), values=values, uid=str(ticket['uid'])))
    return items


def design_items(document: Any) -> list[Item]:
    """The PPT Designs of a PPT Designs document, found by their identity, then by their name. Those of a document of
    before, with an NR Mode of their own and of their template, as an import reads them (report_template_modes)."""
    from src.modules.report_template_modes import migrate_designs_state

    from src.modules.ppt_naming import renamed_design

    # A document of before PPT Designer keeps them as Dashboards.
    designs = document.get('designs', document.get('dashboards')) if isinstance(document, dict) else None
    designs = {key: renamed_design(value) for key, value in designs.items()} if isinstance(designs, dict) else designs
    designs, _changed = migrate_designs_state(designs) if isinstance(designs, dict) else ({}, False)
    identities = document.get('identities') if isinstance(document.get('identities'), dict) else {}
    creators = document.get('creators') if isinstance(document.get('creators'), dict) else {}
    return [Item(name=str(definition.get('name') or key), key=str(key), uid=str(identities.get(key) or key),
                 match=' '.join(str(definition.get('name') or '').split()).casefold(),
                 values={**definition, 'created_by': str(creators.get(key) or '')})
            for key, definition in designs.items() if isinstance(definition, dict)]


def methodology_items(document: Any) -> list[Item]:
    """The Scoring & GAP Analysis Methodologies of a document (of this or an earlier version)."""
    from src.modules.scoring_config import unwrap_scoring_profiles_payload

    try:
        collection = unwrap_scoring_profiles_payload(document)
    except (TypeError, ValueError):
        collection = None
    identities = document.get('identities') if isinstance(document, dict) and isinstance(document.get('identities'), dict) else {}
    creators = document.get('created_by') if isinstance(document, dict) and isinstance(document.get('created_by'), dict) else {}
    return [Item(name=str(profile.get('name') or ''), key=str(profile['id']), uid=str(identities.get(profile['id']) or profile['id']),
                 values={**profile, 'created_by': str(creators.get(profile['id']) or '')})
            for profile in (collection or {}).get('profiles') or [] if isinstance(profile, dict) and profile.get('id')]


def report_configuration_items(document: Any) -> list[Item]:
    """The Scoring & GAP Report Templates of a document (of this or an earlier version)."""
    from src.modules.scoring_reports import unwrap_report_configurations_document

    try:
        configurations = unwrap_report_configurations_document(document)['configurations']
    except (TypeError, ValueError, KeyError):
        configurations = []
    details = {str(item.get('name') or '').strip()[:80].casefold(): item for item in _documents(document, 'configurations')}
    items = []
    for configuration in configurations:
        detail = details.get(str(configuration['name']).casefold(), {})
        items.append(Item(name=str(configuration['name']), uid=str(detail.get('uid') or ''),
                          values={**configuration, 'created_by': str(detail.get('created_by') or '')}))
    return items


def _campaign_choice(entry: dict[str, Any]) -> bool:
    """Whether a Saved Filter has a Campaign choice (Latest 2 campaigns…): it stands for the CDRs of each workspace,
    so the CDRs its document names (those of the workspace that exported it) are not part of what it selects."""
    from src.modules.cdr_auto_selection import campaign_presets

    context_filters = entry.get('context_filters')
    return bool(campaign_presets(context_filters.get('Campaign') if isinstance(context_filters, dict) else None))


def _selection_key(entry: dict[str, Any]) -> str:
    """What a Saved Filter selects (its CDRs by file, unless it has a Campaign choice, and its selection), which finds
    it whatever its name."""
    cdrs = [] if _campaign_choice(entry) else sorted(
        str(ref.get('sha256') or '') for ref in entry.get('cdrs') or [] if isinstance(ref, dict))
    selection = {key: entry.get(key) for key in ('nr_mode', 'levels', 'baseline_operator', 'context_filters',
                                                  'scoring_profile_id', 'area_summary')}
    return hashlib.sha256(_canonical({**selection, 'cdrs': cdrs}).encode('utf-8')).hexdigest()


def favourites_filter_items(document: Any) -> list[Item]:
    """The Favourites Filters of a Saved Filters document, found by what they select, then by their name. Those with a
    Campaign choice are compared without their CDRs, as the import takes those the choice stands for here."""
    return [Item(name=str(entry.get('name') or ''), uid=_selection_key(entry),
                 values={key: value for key, value in entry.items() if key != 'cdrs'} if _campaign_choice(entry) else entry)
            for entry in _documents(document, 'saved_filters')]


def auto_calculated_field_items(definitions: Any) -> list[Item]:
    return named_items(item for item in definitions or [] if isinstance(item, dict)) if isinstance(definitions, list) else []


def nq_call_items(document: Any) -> list[Item]:
    """The Non-Qualified Calls of a tracking document with their follow-up, field values, comments and RCA result,
    found by their JOIN_ID and service (whatever way their key is computed), then by their key."""
    calls = {str(item.get('call_key') or ''): item for item in _documents(document, 'calls')}
    by_join_id: dict[str, list[str]] = {}
    for key, call in calls.items():
        by_join_id.setdefault(str(call.get('join_id') or ''), []).append(key)
    labels = {str(item.get('key') or ''): str(item.get('label') or '') for item in _documents(document, 'fields')}
    values: dict[str, dict[str, Any]] = {}
    for row in _documents(document, 'tracking'):
        values.setdefault(str(row.get('call_key') or ''), {}).update(
            {key: row.get(key) for key in ('status', 'status_mode', 'team', 'assignee', 'root_domain', 'root_category', 'root_cause')})
    for row in _documents(document, 'field_values'):
        field_key = str(row.get('field_key') or '')
        values.setdefault(str(row.get('call_key') or ''), {})[labels.get(field_key) or field_key] = row.get('value')
    for row in _documents(document, 'comments'):
        values.setdefault(str(row.get('call_key') or ''), {}).setdefault('comments', []).append(
            {key: value for key, value in row.items() if key != 'call_key'})
    for row in _documents(document, 'rca_results'):
        join_id = str(row.get('join_id') or '')
        for key in by_join_id.get(join_id) or [f'join:{join_id}']:
            values.setdefault(key, {})['rca_result'] = row.get('values_json')
    items = []
    for key, call_values in values.items():
        if not key:
            continue
        call = calls.get(key, {})
        join_id = str(call.get('join_id') or (key[5:] if key.startswith('join:') else ''))
        service = str(call.get('service') or '')
        uid = '|'.join([service, join_id, str(call.get('sample_id') or '')]) if join_id else ''
        items.append(Item(name=f'{join_id} ({service})' if join_id and service else join_id or key, values=call_values,
                          uid=uid, match=key))
    return items


def report_template_items(rows: Any) -> list[Item]:
    """The PPT Templates of a workspace (or a package) as ``{name, uid, content, is_default, created_by}``, found by
    their identity, then by their name."""
    items = []
    for row in rows if isinstance(rows, list) else []:
        name, uid = str(row.get('name') or ''), str(row.get('uid') or '')
        items.append(Item(name=name, uid=uid, match=name.casefold(),
                          values={key: row[key] for key in ('content', 'is_default', 'created_by') if key in row}))
    return items


def settings_values(document: Any) -> dict[str, Any]:
    """The settings of a document: its sections, without its format and version."""
    return {key: value for key, value in document.items() if key not in {'format', 'version'}} if isinstance(document, dict) else {}


# The items of the export document of each element of a workspace (those of the settings elements are their sections).
ELEMENT_ITEMS = {
    'designs': design_items,
    'ppt-templates': report_template_items,
    'scoring-configuration': methodology_items,
    'auto-calculated-fields': auto_calculated_field_items,
    'query-builder-queries': lambda document: named_items(_documents(document, 'queries')),
    'network-insights-favourites': lambda document: named_items(_documents(document, 'favourites')),
    'bundle-report-template-favourites': lambda document: named_items(_documents(document, 'favourites')),
    'scoring-favourites-filters': favourites_filter_items,
    'scoring-report-templates': report_configuration_items,
    'scoring-excluded-calls': lambda document: named_items(_documents(document, 'lists')),
    'reporting-jobs': lambda document: named_items(_documents(document, 'reporting_jobs')),
    'nq-call-tracking': nq_call_items,
}
# How the completion message names the items of each element: one, several, and what comes before their count.
ELEMENT_NAMES = {
    'designs': ('PPT Design', 'PPT Designs', ''),
    'ppt-templates': ('PPT Template', 'PPT Templates', ''),
    'scoring-configuration': ('Scoring & GAP Analysis Methodology', 'Scoring & GAP Analysis Methodologies', ''),
    'auto-calculated-fields': ('auto-calculated field', 'auto-calculated fields', ''),
    'query-builder-queries': ('Query Builder query', 'Query Builder queries', ''),
    'network-insights-favourites': ('Network Insights Favourite', 'Network Insights Favourites', ''),
    'bundle-report-template-favourites': ('Bundle Report Template Favourite', 'Bundle Report Template Favourites', ''),
    'scoring-favourites-filters': ('Scoring & GAP Favourites Filter', 'Scoring & GAP Favourites Filters', ''),
    'scoring-report-templates': ('Scoring & GAP Report Template', 'Scoring & GAP Report Templates', ''),
    'scoring-excluded-calls': ('list of Scoring Excluded Calls', 'lists of Scoring Excluded Calls', ''),
    'reporting-jobs': ('Reporting Job', 'Reporting Jobs', ''),
    'nq-call-tracking': ('Non-Qualified Call', 'Non-Qualified Calls', 'the follow-up of '),
}
# The settings elements: as the completion message names them, as the title of their changes names them, and the
# labels of their sections.
SETTINGS_ELEMENTS = {
    'mappings-reference-data': ('Mappings & Reference Data', 'Mappings & Reference Data', {'cdr_field_dictionary': 'CDR Field Dictionary'}),
    'main-cities': ('Main Cities', 'Main Cities', {'cities': 'Main Cities'}),
    'scoring-export-panels': ('the Scoring Export Panels', 'Scoring Export Panels', {}),
    'nq-calls-configuration': ('the NQ Calls Configuration', 'NQ Calls Configuration', {}),
}
# The labels of the values of the items of some elements.
ELEMENT_LABELS = {
    'ppt-templates': {'content': 'Content'},
    'scoring-excluded-calls': {'calls': 'Calls'},
}


def element_items(kind: str, document: Any) -> list[Item]:
    """The items of the export document of an element (none for a document it cannot read)."""
    try:
        return ELEMENT_ITEMS[kind](document)
    except (AttributeError, KeyError, TypeError, ValueError):
        return []
