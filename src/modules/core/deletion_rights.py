"""Who deletes what the users of a workspace share: admins and super-admins delete everything, the other roles only
what they created (PPT Designer, PPT Templates, Scoring Saved Filters and Methodologies, the favourites of the
Scoring report editor, Reporting Jobs and Bundle Report Template favourites).

The items whose table has no creator of their own keep it in the workspace settings, by kind. Those created before it
was kept, or by the application (``system``), belong to the super-admin every deployment starts with
(UNKNOWN_CREATOR_OWNER, see assign_unknown_creators), so only admins and super-admins delete them.

PPT Designs and PPT Templates go further (can_change_owned): one created by an admin or a super-admin is changed and
deleted only by the user who created it and by super-admins, never by another admin.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from src.modules.core.repository import DEFAULT_ACCOUNT_USERNAMES

DELETION_ROLES = frozenset({'admin', 'super-admin'})
CREATORS_STATE_PREFIX = 'creators:'
PPT_DESIGNER = 'ppt-designer'
SCORING_REPORT_CONFIGURATIONS = 'scoring-report-configurations'
SCORING_METHODOLOGIES = 'scoring-methodologies'
# Auto-calculated Fields keep who created them for Import / Export and Transfer only: anyone who edits them deletes them.
AUTO_CALCULATED_FIELDS = 'auto-calculated-fields'
# The items without a known creator, or created by the application, belong to the super-admin every deployment starts
# with (``super``), whether or not the account still exists.
UNKNOWN_CREATOR_OWNER = DEFAULT_ACCOUNT_USERNAMES[0]
UNKNOWN_CREATORS = frozenset({'', 'system'})
# The PPT Designs and PPT Templates of these roles are changed only by the user who created them and by super-admins.
PROTECTED_CREATOR_ROLES = frozenset({'admin', 'super-admin'})


def _is_creator(user: Any, created_by: Any) -> bool:
    creator = str(created_by or '').strip()
    return bool(creator) and creator.casefold() == str(getattr(user, 'username', '') or '').casefold()


def can_delete(user: Any, created_by: Any) -> bool:
    """Whether the user deletes an item created by ``created_by``."""
    return getattr(user, 'role', '') in DELETION_ROLES or _is_creator(user, created_by)


def deletion_refusal(label: str, names: list[str] | None = None) -> str:
    """Why a user cannot delete one item (``label``) or several (``names``)."""
    detail = f' ({", ".join(names)})' if names else ''
    return f'Only admins and super-admins, or the user who created it, can delete this {label}{detail}.'


def owner_of(created_by: Any) -> str:
    """Who an item belongs to: its creator, or UNKNOWN_CREATOR_OWNER when it has none or the application created it."""
    creator = str(created_by or '').strip()
    return UNKNOWN_CREATOR_OWNER if _unknown(creator) else creator


def creator_role(repository: Any, created_by: Any) -> str:
    """The role of the account an item belongs to (owner_of); '' when that account is no longer in the deployment, except
    UNKNOWN_CREATOR_OWNER, which is always the super-admin every deployment starts with."""
    owner = owner_of(created_by)
    try:
        record = repository.get_user(owner)
    except (sqlite3.Error, AttributeError):
        record = None
    if record is not None:
        return str(record.role or '')
    return 'super-admin' if owner.casefold() == UNKNOWN_CREATOR_OWNER else ''


def can_change_owned(user: Any, created_by: Any, repository: Any) -> bool:
    """Whether the user changes (or deletes) a PPT Design or PPT Template created by ``created_by``: its creator and
    super-admins always; admins also those of user-editors and of accounts no longer in the deployment, never those of
    another admin or super-admin (nor those without a known creator, see owner_of); the other roles only their own."""
    role = getattr(user, 'role', '')
    if role == 'super-admin' or _is_creator(user, created_by):
        return True
    return role == 'admin' and creator_role(repository, created_by) not in PROTECTED_CREATOR_ROLES


def change_refusal(label: str, created_by: Any, repository: Any, action: str = 'change') -> str:
    """Why a user cannot ``action`` (change, delete…) a PPT Design or PPT Template (``label``) created by ``created_by``."""
    role = creator_role(repository, created_by)
    if role == 'super-admin':
        return f'Only super-admins can {action} this {label}.'
    if role in PROTECTED_CREATOR_ROLES:
        return f'Only {owner_of(created_by)}, who created it, and super-admins can {action} this {label}.'
    return f'Only admins and super-admins, or the user who created it, can {action} this {label}.'


def _key(item_id: Any) -> str:
    return str(item_id).strip().casefold()


def creators(repository: Any, kind: str) -> dict[str, str]:
    """The creator of each item of a kind, by its id (or name), as the workspace keeps them."""
    try:
        stored = json.loads(repository.get_workspace_state(CREATORS_STATE_PREFIX + kind) or '{}')
    except (TypeError, ValueError):
        return {}
    return {str(key): str(value) for key, value in stored.items() if str(value).strip()} if isinstance(stored, dict) else {}


def creator_of(repository: Any, kind: str, item_id: Any) -> str:
    return creators(repository, kind).get(_key(item_id), '')


def _store(repository: Any, kind: str, values: dict[str, str]) -> None:
    repository.set_workspace_state(CREATORS_STATE_PREFIX + kind, json.dumps(values, ensure_ascii=False))


def record_creator(repository: Any, kind: str, item_id: Any, username: str) -> None:
    """Keep who created a new item; an item that has a creator keeps it."""
    values = creators(repository, kind)
    if _key(item_id) not in values and str(username or '').strip():
        values[_key(item_id)] = str(username).strip()
        _store(repository, kind, values)


def set_creator(repository: Any, kind: str, item_id: Any, username: str) -> None:
    """Give an item the creator an import decides (see transfer_identities.imported_creator)."""
    values = creators(repository, kind)
    if str(username or '').strip() and values.get(_key(item_id)) != str(username).strip():
        values[_key(item_id)] = str(username).strip()
        _store(repository, kind, values)


def move_creator(repository: Any, kind: str, item_id: Any, new_item_id: Any) -> None:
    """An item kept by its name keeps its creator when it is renamed."""
    values = creators(repository, kind)
    if _key(item_id) != _key(new_item_id) and _key(item_id) in values:
        values[_key(new_item_id)] = values.pop(_key(item_id))
        _store(repository, kind, values)


def forget_creator(repository: Any, kind: str, item_id: Any) -> None:
    values = creators(repository, kind)
    if values.pop(_key(item_id), None) is not None:
        _store(repository, kind, values)


def _unknown(creator: Any) -> bool:
    return str(creator or '').strip().casefold() in UNKNOWN_CREATORS


def _assign_kept_creators(repository: Any, kind: str, item_ids: list[Any], owner: str) -> int:
    values = creators(repository, kind)
    missing = [_key(item_id) for item_id in item_ids if _unknown(values.get(_key(item_id)))]
    if missing:
        values.update(dict.fromkeys(missing, owner))
        _store(repository, kind, values)
    return len(missing)


def assign_unknown_creators(repository: Any) -> dict[str, int]:
    """Give the items of the open workspace without a known creator, or created by the application, to the
    UNKNOWN_CREATOR_OWNER account; returns how many of each kind changed."""
    from src.modules.reporting.bundle_report_templates import BUNDLE_REPORT_TEMPLATES_TABLE, ensure_tables
    from src.modules.ppt_designer.ppt_designer import LEGACY_STATE_KEY, STATE_KEY
    from src.modules.reporting.report_tasks import REPORT_TASKS_TABLE, ensure_report_task_tables
    from src.modules.core.repository import SCORING_CONFIGURATION_STATE_KEY
    from src.modules.scoring.saved_filters import SAVED_FILTERS_TABLE
    from src.modules.scoring.scoring_reports import load_report_state

    owner = UNKNOWN_CREATOR_OWNER
    changed: dict[str, int] = {}
    ensure_report_task_tables(repository)
    ensure_tables(repository)
    unknown = "TRIM(COALESCE(created_by, '')) = '' OR LOWER(TRIM(created_by)) = 'system'"
    with repository.connection() as connection:
        for kind, table in (('saved_filters', SAVED_FILTERS_TABLE), ('reporting_jobs', REPORT_TASKS_TABLE),
                            ('bundle_report_template_favourites', BUNDLE_REPORT_TEMPLATES_TABLE),
                            ('ppt_templates', 'report_templates')):
            changed[kind] = connection.execute(f'UPDATE {table} SET created_by = ? WHERE {unknown}', (owner,)).rowcount
    try:
        designs = json.loads(repository.get_workspace_state(STATE_KEY) or repository.get_workspace_state(LEGACY_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        designs = {}
    changed['ppt_designer'] = _assign_kept_creators(repository, PPT_DESIGNER, list(designs) if isinstance(designs, dict) else [], owner)
    changed['scoring_report_configurations'] = _assign_kept_creators(
        repository, SCORING_REPORT_CONFIGURATIONS, [item['name'] for item in load_report_state(repository)['configurations']], owner)
    try:
        profiles = repository.get_scoring_profiles()['profiles'] if repository.get_workspace_state(SCORING_CONFIGURATION_STATE_KEY) else []
    except ValueError:
        profiles = []
    changed['scoring_methodologies'] = _assign_kept_creators(repository, SCORING_METHODOLOGIES, [profile['id'] for profile in profiles], owner)
    return {kind: count for kind, count in changed.items() if count}
