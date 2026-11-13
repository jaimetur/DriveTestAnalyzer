"""What the actions of the NQ Analysis Center record in App Events: which calls they touched (by JOIN_ID, operator and
campaign, not only by their internal key), the filters they ran with and what each change made of the values it changed,
so App Events tells what a user did (see app_event_details for the sentence each event reads as)."""
from __future__ import annotations

import json
import threading
from typing import Any, Iterable

from src.modules.core.app_event_details import changed_values, changes_text

# At most this many calls, values or filters are named in one event (the counts are always complete).
LISTED = 50
TEXT_LENGTH = 300


def short_text(value: Any, limit: int = TEXT_LENGTH) -> str:
    """A text on one line, cut at ``limit`` characters (comments are recorded as their start)."""
    text = ' '.join(str(value or '').split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def call_identities(repository: Any, call_keys: Iterable[str], table: str = 'nq_calls') -> dict[str, dict[str, str]]:
    """The JOIN_ID, operator, campaign, call type and NR Mode of each call (or Speech sample), as its latest CDR gives them."""
    keys = [str(key) for key in dict.fromkeys(call_keys) if str(key)][:LISTED]
    if not keys:
        return {}
    marks = ', '.join('?' for _ in keys)
    identities: dict[str, dict[str, str]] = {}
    try:
        with repository.connection() as connection:
            rows = connection.execute(
                f'SELECT call_key, sample_key, join_id, operator, campaign, service, nr_mode FROM {table} '
                f'WHERE call_key IN ({marks}) OR sample_key IN ({marks}) ORDER BY dataset_id', [*keys, *keys]).fetchall()
    except Exception:  # noqa: BLE001 - App Events names the call by its key when the index cannot be read.
        return {}
    wanted = set(keys)
    for row in rows:
        key = str(row['sample_key']) if str(row['sample_key'] or '') in wanted else str(row['call_key'])
        identities[key] = {name: str(row[name] or '') for name in ('join_id', 'operator', 'campaign', 'service', 'nr_mode')}
    # The operator as the module shows it: its label of the Operator Maps.
    try:
        from src.modules.mapping.value_maps import ValueMapper, field_kind

        mapper = ValueMapper.from_settings(repository.chart_mapping_settings())
        for identity in identities.values():
            identity['operator'] = str(mapper.map(field_kind('operator'), identity['operator']) or identity['operator'])
    except Exception:  # noqa: BLE001 - without the Operator Maps the event keeps the operator of the CDR.
        pass
    return identities


def call_identity(repository: Any, call_key: str) -> dict[str, str]:
    """``{'call_key', 'join_id', 'operator', 'campaign', 'call_type', 'nr_mode'}`` of one call, for its event."""
    found = call_identities(repository, [call_key]).get(str(call_key), {})
    return {'call_key': str(call_key), 'join_id': found.get('join_id', ''), 'operator': found.get('operator', ''),
            'campaign': found.get('campaign', ''), 'call_type': found.get('service', ''), 'nr_mode': found.get('nr_mode', '')}


def join_ids(repository: Any, call_keys: Iterable[str]) -> list[str]:
    """The JOIN_ID of each call (its key when it has none), the first ``LISTED`` of them."""
    keys = [str(key) for key in dict.fromkeys(call_keys) if str(key)][:LISTED]
    identities = call_identities(repository, keys)
    return [identities.get(key, {}).get('join_id') or key for key in keys]


def filters_summary(filters: Any) -> dict[str, Any]:
    """The filters that hold a value, each with its first values."""
    if not isinstance(filters, dict):
        return {}
    summary: dict[str, Any] = {}
    for name, value in filters.items():
        if value is None or value == '' or value == [] or value == {} or value is False:
            continue
        if isinstance(value, (list, tuple, set)):
            values = [short_text(item, 80) for item in value]
            summary[str(name)] = values[:10] + ([f'+{len(values) - 10} more'] if len(values) > 10 else [])
        elif isinstance(value, dict):
            summary[str(name)] = short_text(json.dumps(value, ensure_ascii=False, sort_keys=True), 200)
        else:
            summary[str(name)] = short_text(value, 120)
    return summary


def value_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    """``{name: [before, after]}`` of the values that differ."""
    return changed_values(before or {}, after or {})


def named_list_changes(kind: str, before: list[dict[str, Any]], after: list[dict[str, Any]], attributes: Iterable[str] = (),
                       renamed: dict[str, str] | None = None) -> list[str]:
    """What changed in a list of named items (statuses, teams, sections, root causes…): those added, removed and renamed,
    and the attributes that changed, one text each (``status Pending added``, ``team Ops members +ANA``)."""
    renamed = {str(old).casefold(): str(new) for old, new in (renamed or {}).items() if str(old) != str(new)}
    old_items = {str(item.get('name', '')).casefold(): item for item in before or [] if isinstance(item, dict)}
    new_items = {str(item.get('name', '')).casefold(): item for item in after or [] if isinstance(item, dict)}
    targets = {new.casefold(): old for old, new in renamed.items()}
    parts: list[str] = []
    for key, item in new_items.items():
        previous_key = targets.get(key, key)
        previous = old_items.get(previous_key)
        name = str(item.get('name', ''))
        if previous is None:
            parts.append(f'{kind} {name} added')
            continue
        if previous_key != key:
            parts.append(f"{kind} {previous.get('name')} renamed to {name}")
        changes = changed_values({attribute: previous.get(attribute) for attribute in attributes},
                                 {attribute: item.get(attribute) for attribute in attributes})
        if changes:
            parts.append(f'{kind} {name} {changes_text(changes)}')
    used = {targets.get(key, key) for key in new_items}
    parts.extend(f"{kind} {item.get('name')} removed" for key, item in old_items.items() if key not in used)
    return parts


def changes_sentence(subject: str, parts: list[str]) -> str:
    """``Subject: part; part.``, or ``Subject (no change).``"""
    parts = [part for part in parts if part]
    shown = parts[:LISTED] + ([f'{len(parts) - LISTED} more changes'] if len(parts) > LISTED else [])
    return f"{subject}: {'; '.join(shown)}." if shown else f'{subject} (no change).'


class RepeatedReads:
    """The reads App Events already recorded for each user: the same read again (the same map moved or zoomed, the same
    list read again after a change) is not recorded twice in a row."""

    def __init__(self) -> None:
        self._last: dict[tuple[str, str, str], str] = {}
        self._lock = threading.Lock()

    def first(self, repository: Any, username: str, scope: str, signature: Any) -> bool:
        """Whether this read differs from the last one recorded for the user and the scope (and remember it)."""
        key = (str(getattr(repository, 'db_path', '')), str(username).casefold(), scope)
        text = json.dumps(signature, sort_keys=True, default=str, ensure_ascii=False)
        with self._lock:
            if self._last.get(key) == text:
                return False
            self._last[key] = text
            return True

    def forget(self, repository: Any, username: str) -> None:
        """Record the next reads of the user again (the page was opened again)."""
        database, user = str(getattr(repository, 'db_path', '')), str(username).casefold()
        with self._lock:
            for key in [key for key in self._last if key[:2] == (database, user)]:
                del self._last[key]


REPEATED_READS = RepeatedReads()
