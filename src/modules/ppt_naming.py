"""Stored names of the modules renamed to PPT Designer and PPT Reporting (old).

E2E Dashboards became PPT Dashboards, and PPT Dashboards became PPT Designer, whose Dashboards are called Designs;
Reporting (old) became PPT Reporting (old). The Designs of each workspace, their PPT jobs, drafts and pictures, their
App Events and the Interface Settings of the main modules are stored under the module names, so they are renamed once
in the application database and in every workspace database (also one restored or transferred from a server that still
used the former names).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

MODULE_KEYS = {'e2e-dashboards': 'ppt-designer', 'ppt-dashboards': 'ppt-designer', 'reporting-old': 'ppt-reporting-old'}
# Former titles of the modules, also E2E Reporting (Reporting (old) before 0.6.0), stored by Interface Settings.
MODULE_TITLES = {'E2E Dashboards': 'PPT Designer', 'PPT Dashboards': 'PPT Designer', 'PPT Dashboard': 'PPT Designer', 'Dashboards': 'Designer',
                 'Reporting (old)': 'PPT Reporting (old)', 'E2E Reporting': 'PPT Reporting (old)'}
# In order: a workspace of E2E Dashboards takes the PPT Dashboards names, then those of PPT Designer.
WORKSPACE_STATE_PREFIXES = (('e2e_dashboard', 'ppt_dashboard'), ('ppt_dashboard', 'ppt_design'))
WORKSPACE_STATE_KEYS = {
    'creators:ppt-dashboards': 'creators:ppt-designer', 'identities:ppt-dashboards': 'identities:ppt-designer',
    'bundle_report_template_dashboard_nr_modes_v1': 'bundle_report_template_design_nr_modes_v1',
    'dashboard_selection_cache_version': 'design_selection_cache_version', 'dashboard_date_bounds_v1': 'design_date_bounds_v1',
}
DESIGNS_STATE_KEY = 'ppt_designs_v2'
# The fields of a Design that named its slides "design" while it was a Dashboard.
DESIGN_FIELDS = {'design': 'own_slides', 'design_overrides': 'slide_overrides'}
# Tables (and their columns) of the Designs.
WORKSPACE_TABLES = (
    ('dashboard_ppt_jobs', 'design_ppt_jobs', {'dashboard_id': 'design_id', 'dashboard_name': 'design_name'}),
    ('dashboard_design_drafts', 'design_drafts', {'dashboard_id': 'design_id'}),
    ('dashboard_design_images', 'design_images', {}),
)
# A cache rebuilt when it is empty: the former one is dropped.
DROPPED_TABLES = ('dashboard_filter_selections',)
# App Events whose action did not become the plain rename of dashboard into design.
EVENT_ACTIONS = {
    'dashboard_design_saved': 'design_slides_saved', 'dashboard_design_detached': 'design_detached',
    'dashboard_design_draft_discarded': 'design_draft_discarded', 'dashboard_design_image_uploaded': 'design_image_uploaded',
    'report_template_design_ids_assigned': 'report_template_slide_ids_assigned', 'ppt_dashboards_theme_changed': 'ppt_designer_theme_changed',
}
EVENT_DETAIL_KEYS = ('dashboard_id', 'dashboard_name', 'unchecked_dashboards', 'renamed_dashboards', 'detached_dashboards', 'dropped_design',
                     'design_overrides')


def renamed_detail_key(key: str) -> str:
    """The name of a field of App Events details after the rename."""
    if key == 'dropped_design':
        return 'dropped_slide_overrides'
    if key == 'design_overrides':
        return 'slide_overrides'
    return key.replace('dashboards', 'designs').replace('dashboard', 'design')


def renamed_event_action(action: str) -> str:
    """The action of an App Event of PPT Dashboards as PPT Designer records it."""
    if action in EVENT_ACTIONS:
        return EVENT_ACTIONS[action]
    if 'dashboard' not in action or 'dashboard_analytic' in action:
        return action
    return action.replace('ppt_dashboards', 'ppt_designer').replace('dashboards', 'designs').replace('dashboard', 'design')


def renamed_design(definition: Any) -> Any:
    """A Design (formerly a Dashboard) with the fields of its slides under their current names."""
    if not isinstance(definition, dict) or not any(key in definition for key in DESIGN_FIELDS):
        return definition
    renamed = {}
    for key, value in definition.items():
        current = DESIGN_FIELDS.get(key, key)
        if key in DESIGN_FIELDS and current in definition:
            continue
        renamed[current] = value
    return renamed


def _renamed_modules(document: Any) -> tuple[Any, bool]:
    """The settings of every module under its new key, with the former titles and tab icons renamed."""
    if not isinstance(document, dict):
        return document, False
    renamed = {}
    for key, value in document.items():
        new_key = MODULE_KEYS.get(key, key)
        if new_key in MODULE_KEYS.values() and isinstance(value, dict):
            value = {**value}
            for field in ('title', 'short_title', 'nav_title'):
                if value.get(field) in MODULE_TITLES:
                    value[field] = MODULE_TITLES[value[field]]
            if value.get('tab_icon') in MODULE_KEYS:
                value['tab_icon'] = MODULE_KEYS[value['tab_icon']]
        if key in MODULE_KEYS or new_key not in renamed:
            renamed[new_key] = value
    return renamed, renamed != document


def migrate_application_state(repository: Any, state_keys: tuple[str, ...]) -> None:
    """Rename the modules in the stored Interface Settings."""
    for state_key in state_keys:
        raw = repository.get_application_state(state_key)
        try:
            document = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            continue
        renamed, changed = _renamed_modules(document)
        if changed:
            repository.set_application_state(state_key, json.dumps(renamed, sort_keys=True))


def migrate_workspace_database(database_path: Path) -> None:
    """Rename the Designs state, tables and App Events of a workspace database."""
    if not Path(database_path).is_file():
        return
    with sqlite3.connect(database_path, timeout=30) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'workspace_state'").fetchone():
            return
        for old, new in WORKSPACE_STATE_PREFIXES:
            rows = connection.execute('SELECT key FROM workspace_state WHERE key LIKE ?', (f'{old}%',)).fetchall()
            for (key,) in rows:
                target = new + key[len(old):]
                if connection.execute('SELECT 1 FROM workspace_state WHERE key = ?', (target,)).fetchone():
                    connection.execute('DELETE FROM workspace_state WHERE key = ?', (key,))
                else:
                    connection.execute('UPDATE workspace_state SET key = ? WHERE key = ?', (target, key))
        for old, new in WORKSPACE_STATE_KEYS.items():
            if connection.execute('SELECT 1 FROM workspace_state WHERE key = ?', (new,)).fetchone():
                connection.execute('DELETE FROM workspace_state WHERE key = ?', (old,))
            else:
                connection.execute('UPDATE workspace_state SET key = ? WHERE key = ?', (new, old))
        row = connection.execute('SELECT value FROM workspace_state WHERE key = ?', (DESIGNS_STATE_KEY,)).fetchone()
        try:
            designs = json.loads(row[0]) if row and row[0] else None
        except (TypeError, ValueError):
            designs = None
        if isinstance(designs, dict):
            renamed = {key: renamed_design(value) for key, value in designs.items()}
            if renamed != designs:
                connection.execute('UPDATE workspace_state SET value = ? WHERE key = ?', (json.dumps(renamed), DESIGNS_STATE_KEY))
        tables = {str(item[0]) for item in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        for former, current, columns in WORKSPACE_TABLES:
            if former not in tables:
                continue
            if current in tables and not connection.execute(f'SELECT 1 FROM {current} LIMIT 1').fetchone():
                connection.execute(f'DROP TABLE {current}')
                tables.discard(current)
            if current in tables:
                continue
            connection.execute(f'ALTER TABLE {former} RENAME TO {current}')
            tables.add(current)
            existing = {str(item[1]) for item in connection.execute(f'PRAGMA table_info({current})').fetchall()}
            for old, new in columns.items():
                if old in existing and new not in existing:
                    connection.execute(f'ALTER TABLE {current} RENAME COLUMN {old} TO {new}')
        for table in DROPPED_TABLES:
            if table in tables:
                connection.execute(f'DROP TABLE {table}')
        if 'audit_logs' in tables:
            _rename_events(connection)


def _rename_events(connection: sqlite3.Connection) -> None:
    """The App Events of PPT Dashboards take the actions, details and pages of PPT Designer."""
    rows = connection.execute("SELECT rowid, action, details FROM audit_logs WHERE action LIKE '%dashboard%' OR details LIKE '%dashboard%' "
                              "OR details LIKE '%design_overrides%' OR details LIKE '%dropped_design%'").fetchall()
    for rowid, action, details in rows:
        new_action = renamed_event_action(str(action or ''))
        new_details = details
        if isinstance(details, str):
            for key in EVENT_DETAIL_KEYS:
                new_details = new_details.replace(f'"{key}"', f'"{renamed_detail_key(key)}"')
        if new_action != action or new_details != details:
            connection.execute('UPDATE audit_logs SET action = ?, details = ? WHERE rowid = ?', (new_action, new_details, rowid))
    if 'origin' in {str(item[1]) for item in connection.execute('PRAGMA table_info(audit_logs)').fetchall()}:
        connection.execute("UPDATE audit_logs SET origin = 'module:ppt-designer' WHERE origin IN ('module:ppt-dashboards', 'module:e2e-dashboards')")


def migrate_application_database(connection: sqlite3.Connection) -> None:
    """The module of PPT Designer, formerly PPT Dashboards, in the Modules Profiles, the tickets, the scheduled backups
    and the chart renderer of the application database."""
    tables = {str(item[0]) for item in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    if 'modules_profiles' in tables:
        for row in connection.execute('SELECT id, modules_json FROM modules_profiles WHERE modules_json LIKE ?', ('%"ppt-dashboards"%',)).fetchall():
            connection.execute('UPDATE modules_profiles SET modules_json = ? WHERE id = ?',
                               (str(row[1]).replace('"ppt-dashboards"', '"ppt-designer"'), int(row[0])))
    if 'tickets' in tables and 'module' in {str(item[1]) for item in connection.execute('PRAGMA table_info(tickets)').fetchall()}:
        connection.execute("UPDATE tickets SET module = 'ppt-designer' WHERE module IN ('ppt-dashboards', 'e2e-dashboards')")
    if 'application_state' in tables:
        connection.execute("UPDATE application_state SET value = replace(value, '\"dashboards\"', '\"designs\"') "
                           "WHERE key = 'recurring_database_backup' AND value LIKE '%\"dashboards\"%'")
        connection.execute("UPDATE application_state SET value = replace(value, '\"dashboard-canvas\"', '\"canvas\"') "
                           "WHERE key = 'runtime_configuration_v1' AND value LIKE '%\"dashboard-canvas\"%'")
