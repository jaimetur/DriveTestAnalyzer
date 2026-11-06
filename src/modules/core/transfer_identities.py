"""The identity of the items a workspace shares with other servers (Import / Export and Transfer), so that an item
renamed on one server replaces its copy on the other instead of adding a second one, and who each imported item
belongs to.

Each item keeps a portable ``uid`` that travels with it. An import finds the item of the workspace first by that uid
(then it takes the name of the package: a rename), then by its name (then it takes the uid of the package, so a
later rename on the other server is found too), and otherwise adds it. The items whose table has no uid of their own
keep it in the workspace settings, by kind, as the creators of deletion_rights.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Iterable
from uuid import uuid4

IDENTITIES_STATE_PREFIX = 'identities:'
PPT_DESIGNER = 'ppt-designer'
QUERY_BUILDER_QUERIES = 'query-builder-queries'
NETWORK_INSIGHTS_FAVOURITES = 'network-insights-favourites'
BUNDLE_REPORT_TEMPLATE_FAVOURITES = 'bundle-report-template-favourites'
SCORING_REPORT_CONFIGURATIONS = 'scoring-report-configurations'
AUTO_CALCULATED_FIELDS = 'auto-calculated-fields'
SCORING_METHODOLOGIES = 'scoring-methodologies'
REPORTING_JOBS = 'reporting-jobs'


def _key(item_key: Any) -> str:
    return str(item_key).strip().casefold()


def identities(repository: Any, kind: str) -> dict[str, str]:
    """The uid of each item of a kind, by its id (or name), as the workspace keeps them."""
    try:
        stored = json.loads(repository.get_workspace_state(IDENTITIES_STATE_PREFIX + kind) or '{}')
    except (TypeError, ValueError):
        return {}
    return {str(key): str(value) for key, value in stored.items() if str(value).strip()} if isinstance(stored, dict) else {}


def _store(repository: Any, kind: str, values: dict[str, str]) -> None:
    repository.set_workspace_state(IDENTITIES_STATE_PREFIX + kind, json.dumps(values, ensure_ascii=False))


def portable_identities(repository: Any, kind: str, item_keys: Iterable[Any],
                        default: Callable[[str], str] | None = None) -> dict[str, str]:
    """The uid of each of the given items (by their key as given), giving one to those that have none: ``default`` of
    their key (a PPT Design ID is already unique) or a new one, kept from then on."""
    values = identities(repository, kind)
    result: dict[str, str] = {}
    changed = False
    for item_key in item_keys:
        key = _key(item_key)
        if not values.get(key):
            values[key] = (default(str(item_key)) if default else '') or uuid4().hex
            changed = True
        result[str(item_key)] = values[key]
    if changed:
        _store(repository, kind, values)
    return result


def set_identities(repository: Any, kind: str, values: dict[Any, str]) -> None:
    """Give items the uid of the package that matched them."""
    stored = identities(repository, kind)
    updated = {**stored, **{_key(key): str(uid) for key, uid in values.items() if str(uid or '').strip()}}
    if updated != stored:
        _store(repository, kind, updated)


def move_identity(repository: Any, kind: str, old_key: Any, new_key: Any) -> None:
    """An item keyed by its name keeps its uid when it is renamed."""
    values = identities(repository, kind)
    if _key(old_key) != _key(new_key) and _key(old_key) in values:
        values[_key(new_key)] = values.pop(_key(old_key))
        _store(repository, kind, values)


def forget_identities(repository: Any, kind: str, item_keys: Iterable[Any]) -> None:
    values = identities(repository, kind)
    removed = [key for key in (_key(item_key) for item_key in item_keys) if key in values]
    for key in removed:
        values.pop(key)
    if removed:
        _store(repository, kind, values)


def unique_name(name: str, taken: Iterable[str], max_length: int = 120,
                normalize: Callable[[str], str] = str.casefold) -> str:
    """``name``, or ``name (2)``, ``name (3)``… when another item has it (names compared by ``normalize``)."""
    used = {normalize(str(value)) for value in taken}
    if normalize(name) not in used:
        return name
    number = 2
    while True:
        suffix = f' ({number})'
        candidate = name[:max_length - len(suffix)].rstrip() + suffix
        if normalize(candidate) not in used:
            return candidate
        number += 1


class ItemMatcher:
    """Find the item of the workspace that an imported item replaces.

    ``items`` are those of the workspace as ``(key, name, uid)`` or ``(key, name, uid, group)``, where ``group``
    separates the items whose names may repeat. Each
    item of the workspace is replaced by one imported item at most. ``renamed`` lists ``(old name, new name)`` and
    ``conflicts`` ``(name, name given)`` of the items whose name another item already had. Names are compared by
    ``normalize`` (without case by default).
    """

    def __init__(self, items: Iterable[tuple[Any, ...]], *, max_length: int = 120,
                 normalize: Callable[[str], str] = str.casefold) -> None:
        self.max_length = max_length
        self.normalize = normalize
        # Each item: [key (None for those the import adds), name, uid, group, used].
        self._items: list[list[Any]] = [
            [entry[0], str(entry[1] or ''), str(entry[2] or ''), str(entry[3]) if len(entry) > 3 else '', False]
            for entry in items
        ]
        self.renamed: list[tuple[str, str]] = []
        self.conflicts: list[tuple[str, str]] = []

    def _name_for(self, name: str, group: str, item: list[Any] | None) -> str:
        if not name.strip():
            return name
        return unique_name(name, [other[1] for other in self._items if other[3] == group and other is not item],
                           self.max_length, self.normalize)

    def match(self, uid: Any, name: str, group: Any = '') -> tuple[Any, str]:
        """The key of the item it replaces (``None`` for a new one) and the name it takes."""
        uid, name, group = str(uid or '').strip(), str(name or ''), str(group or '')
        free = [item for item in self._items if item[0] is not None and not item[4] and item[3] == group]
        item = next((candidate for candidate in free if uid and candidate[2] == uid), None) or next(
            (candidate for candidate in free if name.strip() and self.normalize(candidate[1]) == self.normalize(name)), None)
        if item is None:
            final = self._name_for(name, group, None)
            if final != name:
                self.conflicts.append((name, final))
            self._items.append([None, final, uid, group, True])
            return None, final
        final = name
        if self.normalize(item[1]) != self.normalize(name):
            final = self._name_for(name, group, item)
            if self.normalize(final) == self.normalize(item[1]):
                # Its new name is still another item's: it keeps the name it was given before.
                final = item[1]
            else:
                if final != name:
                    self.conflicts.append((name, final))
                self.renamed.append((item[1], final))
        item[1], item[4] = final, True
        if uid:
            item[2] = uid
        return item[0], final

    def summary(self) -> list[str]:
        """The renamed items and the names another item had, as the completion message lists them."""
        return ([f'"{old}" renamed "{new}"' for old, new in self.renamed]
                + [f'"{name}" kept as "{given}" because another item has its name' for name, given in self.conflicts])


def imported_creator(package_creator: Any, local_creator: Any, accepting_user: str,
                     user_exists: Callable[[str], bool]) -> str:
    """Who an imported item belongs to: its creator on the server of the package when that user exists (and is
    active) here, otherwise the user who accepts the transfer (or imports the package). A package that does not say
    who created the item (one of an earlier version, or an item of the application, ``system``) leaves the creator it
    has here, or gives a new one to that user."""
    creator = str(package_creator or '').strip()
    if creator and creator.casefold() != 'system':
        return creator if user_exists(creator) else accepting_user
    return str(local_creator or '').strip() or accepting_user
