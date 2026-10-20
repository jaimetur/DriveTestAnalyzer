"""Who deletes what the users of a workspace share: admins and super-admins delete everything, the other roles only
what they created (PPT Dashboards, PPT Templates, Scoring Saved Filters and Methodologies, the favourites of the
Scoring report editor, Reporting Jobs and Bundle Report Template favourites).

The items whose table has no creator of their own keep it in the workspace settings, by kind. Those created before it
was kept, or by the application (``system``), belong to the UNKNOWN_CREATOR_OWNER account once it exists (see
assign_unknown_creators); until then only admins and super-admins delete them.
"""
from __future__ import annotations

import json
from typing import Any

DELETION_ROLES = frozenset({'admin', 'super-admin'})
CREATORS_STATE_PREFIX = 'creators:'
PPT_DASHBOARDS = 'ppt-dashboards'
SCORING_REPORT_CONFIGURATIONS = 'scoring-report-configurations'
SCORING_METHODOLOGIES = 'scoring-methodologies'
# The account that the items without a known creator, or created by the application, are assigned to.
UNKNOWN_CREATOR_OWNER = 'EJAITUR'
UNKNOWN_CREATORS = frozenset({'', 'system'})


def can_delete(user: Any, created_by: Any) -> bool:
    """Whether the user deletes an item created by ``created_by``."""
    if getattr(user, 'role', '') in DELETION_ROLES:
        return True
    creator = str(created_by or '').strip()
    return bool(creator) and creator.casefold() == str(getattr(user, 'username', '') or '').casefold()


def deletion_refusal(label: str, names: list[str] | None = None) -> str:
    """Why a user cannot delete one item (``label``) or several (``names``)."""
    detail = f' ({", ".join(names)})' if names else ''
    return f'Only admins and super-admins, or the user who created it, can delete this {label}{detail}.'


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
    UNKNOWN_CREATOR_OWNER account, when it exists; returns how many of each kind changed."""
    from src.modules.bundle_report_templates import BUNDLE_REPORT_TEMPLATES_TABLE, ensure_tables
    from src.modules.ppt_dashboards import LEGACY_STATE_KEY, STATE_KEY
    from src.modules.report_tasks import REPORT_TASKS_TABLE, ensure_report_task_tables
    from src.modules.repository import SCORING_CONFIGURATION_STATE_KEY
    from src.modules.saved_filters import SAVED_FILTERS_TABLE
    from src.modules.scoring_reports import load_report_state

    account = repository.get_user(UNKNOWN_CREATOR_OWNER)
    if account is None:
        return {}
    owner = account.username
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
        dashboards = json.loads(repository.get_workspace_state(STATE_KEY) or repository.get_workspace_state(LEGACY_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        dashboards = {}
    changed['ppt_dashboards'] = _assign_kept_creators(repository, PPT_DASHBOARDS, list(dashboards) if isinstance(dashboards, dict) else [], owner)
    changed['scoring_report_configurations'] = _assign_kept_creators(
        repository, SCORING_REPORT_CONFIGURATIONS, [item['name'] for item in load_report_state(repository)['configurations']], owner)
    try:
        profiles = repository.get_scoring_profiles()['profiles'] if repository.get_workspace_state(SCORING_CONFIGURATION_STATE_KEY) else []
    except ValueError:
        profiles = []
    changed['scoring_methodologies'] = _assign_kept_creators(repository, SCORING_METHODOLOGIES, [profile['id'] for profile in profiles], owner)
    return {kind: count for kind, count in changed.items() if count}
