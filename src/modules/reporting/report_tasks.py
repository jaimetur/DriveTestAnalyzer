"""Reporting: the schedule of each report and its runs (History).

A report (a favourite of ``bundle_report_templates``) has at most one schedule (``report_tasks``): whether it is generated
on its own and when, its formats and whom it is emailed to. Each generation, by hand or scheduled, is a run
(``report_task_runs``) that writes its files to its own folder and, when email is on, sends them with a body that describes
each file and its filters.

Schedules belong to a workspace; a run of a workspace that is not the active one is generated in a worker process.
"""

import calendar
import hashlib
import html
import json
import math
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Event, Lock, Thread, local
from typing import Any, Callable
from urllib.parse import urlencode

from src.branding import canonical_format
from src.modules.mapping.value_maps import ValueMapper
from src.modules.cdr.cdr_auto_selection import (
    ALL_CAMPAIGNS, CAMPAIGN_PRESET_LABELS, LATEST_CAMPAIGN, SINGLE_CAMPAIGN_PRESETS, campaign_presets, one_campaign, campaign_values, cdr_campaigns, complete_campaign_cdrs, describe_cdrs,
    resolve_campaign_filter, resolve_cdrs, sort_campaigns,
)
from src.modules.cdr.column_names import compact_campaign_value
from src.modules.cdr.nr_mode import DEFAULT_NR_MODE, NSA_VS_SA, normalize_scoring_nr_mode, nr_mode_label
from src.modules.scoring.scoring_reports import NR_CHARTS, NR_CHARTS_LABELS, NR_LAYOUT_LABELS, NR_LAYOUTS
from src.modules.core.output_layout import REPORTING_JOBS_FOLDER, module_output_dir
from src.modules.core.email_delivery import DEFAULT_LINK_DAYS, WEBHOOK_MAX_BYTES, webhook_payload
from src.modules.scoring.scoring_themes import DEFAULT_THEME, normalize_theme, themes_payload

REPORT_TASKS_TABLE = 'report_tasks'
REPORT_TASK_RUNS_TABLE = 'report_task_runs'
REPORT_FORMATS = ('powerpoint', 'word')
SCHEDULE_MODES = ('manual', 'once', 'daily', 'weekly', 'monthly')
WEEKDAY_NAMES = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
# CDR Analysis artifacts: the global aggregation of the charts and the CDF comparison, one choice each.
CDR_ANALYSIS_AGGREGATIONS = {
    'all': 'Auto', 'operator': 'Operator', 'operator_vendor': 'Operator_Vendor', 'vendor_operator': 'Vendor_Operator',
    'vendor': 'Vendor',
    'market': 'Market', 'region': 'Region', 'cluster': 'Cluster', 'city': 'City',
}
CDR_ANALYSIS_CDF_GROUPINGS = {'all': 'Single CDF', **{key: label for key, label in CDR_ANALYSIS_AGGREGATIONS.items() if key != 'all'}}
# Network Insights filter names and the CDR Analysis dimension each one filters.
CDR_ANALYSIS_FILTER_DIMENSIONS = {
    'operators': 'operator', 'operator_vendors': 'operator_vendor', 'vendor_operators': 'vendor_operator', 'vendors': 'vendor',
    'regions': 'region',
    'clusters': 'cluster', 'cities': 'city', 'campaigns': 'campaign',
}
RUN_FINAL_STATUSES = ('sent', 'completed', 'partial', 'failed', 'stopped')
# Waiting, generating, or finishing the step it is on after a user stopped it.
RUN_ACTIVE_STATUSES = ('queued', 'running', 'stopping')
# The runs Rerun starts again from the beginning.
RUN_RERUN_STATUSES = ('failed', 'stopped')
DESIGN_JOB_TIMEOUT_SECONDS = 3 * 60 * 60
SCHEDULER_INTERVAL_SECONDS = 30
INTERRUPTED_RUN_MESSAGE = 'The run was interrupted by an application restart.'
# A run interrupted by application restarts goes on from the step it was on, up to this many times.
MAX_RUN_RESUMES = 3
MODULE_LABELS = {
    'dataset_analysis': 'CDR Analysis', 'network_insights': 'Network Insights',
    'designs': 'PPT Designs', 'scoring': 'Scoring',
}
# The feature a user needs to include each kind of artifact in a Reporting Job.
MODULE_FEATURES = {
    'dataset_analysis': 'datasets-analysis', 'network_insights': 'network-insights',
    'designs': 'ppt-designer', 'scoring': 'scoring',
}
# Artifacts of other modules (for example Non-Qualified Calls) register here:
# key -> {'label', 'feature', 'formats', 'generate', 'filters', 'settings', 'values'}.
# ``generate(config, folder, stamp, user)`` returns artifact dictionaries; the
# config's ``options`` holds the chosen ``filters`` and ``settings``.
ARTIFACT_PROVIDERS: dict[str, dict[str, Any]] = {}
# The artifacts of jobs saved when Bundle Report Templates had a former name (Complete Reports, then briefly Reporting
# Jobs Templates and Bundle Reports Templates), and the key that replaced each.
LEGACY_PROVIDER_KEYS = {'complete_report': 'bundle_report_template', 'reporting_jobs_template': 'bundle_report_template',
                        'bundle_reports_template': 'bundle_report_template'}


def _current_artifact_modules(artifacts: Any) -> Any:
    """The artifacts of a run, those of the PPT Designs generated before PPT Designer (module dashboards) included."""
    if not isinstance(artifacts, list):
        return artifacts
    return [{**item, 'module': 'designs'} if isinstance(item, dict) and item.get('module') == 'dashboards' else item for item in artifacts]


def _current_provider_keys(definition: Any) -> bool:
    """Give in place the artifacts of a job saved with a former key their current key; returns whether any changed."""
    modules = definition.get('modules') if isinstance(definition, dict) else None
    if not isinstance(modules, dict) or not any(key in LEGACY_PROVIDER_KEYS for key in modules):
        return False
    definition['modules'] = {LEGACY_PROVIDER_KEYS.get(key, key): config for key, config in modules.items()
                             if not (key in LEGACY_PROVIDER_KEYS and LEGACY_PROVIDER_KEYS[key] in modules)}
    return True


def register_report_artifact_provider(
    key: str, label: str, feature: str, generate, formats: tuple[str, ...] = ('powerpoint',), *,
    filters: tuple[tuple[str, str], ...] = (), settings: tuple[dict[str, Any], ...] = (), values=None,
) -> None:
    """Let a module add its own reports to Reporting Jobs.

    ``filters`` are (key, label) multi-value filters whose choices ``values(user)``
    returns; ``settings`` are single choices: {'key', 'label', 'choices', 'default'}.
    """
    ARTIFACT_PROVIDERS[key] = {'label': label, 'feature': feature, 'formats': tuple(formats), 'generate': generate,
                               'filters': tuple(filters), 'settings': tuple(settings), 'values': values}
FORMAT_LABELS = {'powerpoint': 'PPT', 'word': 'Word', 'excel': 'Excel'}

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {REPORT_TASKS_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    definition_json TEXT NOT NULL DEFAULT '{{}}',
    send_email INTEGER NOT NULL DEFAULT 1,
    recipients_json TEXT NOT NULL DEFAULT '[]',
    schedule_json TEXT NOT NULL DEFAULT '{{}}',
    enabled INTEGER NOT NULL DEFAULT 1,
    next_run_at TEXT,
    last_run_id INTEGER,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS {REPORT_TASK_RUNS_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL,
    task_name TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    send_email INTEGER NOT NULL DEFAULT 0,
    recipients_json TEXT NOT NULL DEFAULT '[]',
    email_status TEXT NOT NULL DEFAULT '',
    artifacts_json TEXT NOT NULL DEFAULT '[]',
    output_dir TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    control_json TEXT NOT NULL DEFAULT '{{}}'
);
CREATE INDEX IF NOT EXISTS idx_report_task_runs_task ON {REPORT_TASK_RUNS_TABLE}(task_id, id);
"""


def now_local() -> datetime:
    return datetime.now().astimezone()


# The databases whose Reporting Jobs are already the schedules of their reports (see _reports_own_their_schedules),
# once per process.
_LEGACY_JOBS_STORED: set[str] = set()
_LEGACY_JOBS_LOCK = Lock()


def _reports_own_their_schedules(connection: Any) -> dict[str, Any]:
    """Reporting Jobs became the schedule of their report (Reporting: one place for the content, ticket #95). Once per
    workspace: the jobs that generate one report become its schedule, named after it (a report generated by several
    keeps the one that is scheduled or emails, else the first, and the runs of the others); the jobs of artifacts
    designed in the job, of every favourite or of a report that no longer exists are deleted with their runs. Returns
    what changed: {'kept', 'merged', 'deleted', 'folders'}."""
    from src.modules.reporting.bundle_report_templates import BUNDLE_REPORT_TEMPLATES_TABLE

    has_reports = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                                     (BUNDLE_REPORT_TEMPLATES_TABLE,)).fetchone() is not None
    reports = {str(row[0]): str(row[1]) for row in connection.execute(
        f'SELECT id, name FROM {BUNDLE_REPORT_TEMPLATES_TABLE}').fetchall()} if has_reports else {}
    changes: dict[str, Any] = {'kept': [], 'merged': [], 'deleted': [], 'folders': []}
    by_report: dict[str, list[tuple[Any, dict[str, Any]]]] = {}
    rows = connection.execute(f'SELECT * FROM {REPORT_TASKS_TABLE} ORDER BY position, id').fetchall()
    for row in rows:
        try:
            definition = json.loads(row['definition_json'] or '{}')
        except json.JSONDecodeError:
            definition = {}
        definition = definition if isinstance(definition, dict) else {}
        _current_provider_keys(definition)
        favourite_id = _chosen_favourites(definition)[0] if based_on_favourite(definition) else ''
        if favourite_id and (favourite_id in reports or not has_reports):
            by_report.setdefault(favourite_id, []).append((row, definition))
            continue
        changes['deleted'].append({'id': int(row['id']), 'name': str(row['name'])})

    def delete(task_id: int) -> None:
        changes['folders'] += [str(item[0]) for item in connection.execute(
            f'SELECT output_dir FROM {REPORT_TASK_RUNS_TABLE} WHERE task_id = ?', (task_id,)).fetchall() if item[0]]
        connection.execute(f'DELETE FROM {REPORT_TASK_RUNS_TABLE} WHERE task_id = ?', (task_id,))
        connection.execute(f'DELETE FROM {REPORT_TASKS_TABLE} WHERE id = ?', (task_id,))

    for item in changes['deleted']:
        delete(item['id'])
    for favourite_id, jobs in by_report.items():
        # The one that runs on its own or emails, else the first of the jobs table.
        kept, definition = next(((row, definition) for row, definition in jobs
                                 if row['send_email'] or json.loads(row['schedule_json'] or '{}').get('mode', 'manual') != 'manual'),
                                jobs[0])
        formats = ((definition.get('modules') or {}).get('bundle_report_template') or {}).get('formats') or ['powerpoint']
        name = reports.get(favourite_id) or str(kept['name'])
        connection.execute(f'UPDATE {REPORT_TASKS_TABLE} SET name = ?, definition_json = ? WHERE id = ?',
                           (name[:160], json.dumps(report_definition(favourite_id, formats), ensure_ascii=False), kept['id']))
        changes['kept'].append({'id': int(kept['id']), 'report': name})
        for row, _definition in jobs:
            if row['id'] != kept['id']:
                # Its runs stay in History, as runs of the report.
                connection.execute(f'UPDATE {REPORT_TASK_RUNS_TABLE} SET task_id = ? WHERE task_id = ?', (kept['id'], row['id']))
                connection.execute(f'DELETE FROM {REPORT_TASKS_TABLE} WHERE id = ?', (row['id'],))
                changes['merged'].append({'id': int(row['id']), 'name': str(row['name']), 'into': int(kept['id'])})
    return changes


def ensure_report_task_tables(task_repository: Any) -> None:
    with task_repository.connection() as connection:
        connection.executescript(SCHEMA)
        database = str(getattr(task_repository, 'db_path', ''))
        changes = None
        # How a run is carried on (see execute_run); runs saved before it have none.
        if 'control_json' not in {row[1] for row in connection.execute(f'PRAGMA table_info({REPORT_TASK_RUNS_TABLE})')}:
            try:
                connection.execute(f"ALTER TABLE {REPORT_TASK_RUNS_TABLE} ADD COLUMN control_json TEXT NOT NULL DEFAULT '{{}}'")
            except sqlite3.OperationalError:  # Added meanwhile by another request.
                pass
        # The order of the jobs table (dragged by the users); jobs saved before it keep their alphabetical order.
        if 'position' not in {row[1] for row in connection.execute(f'PRAGMA table_info({REPORT_TASKS_TABLE})')}:
            try:
                connection.execute(f'ALTER TABLE {REPORT_TASKS_TABLE} ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
            except sqlite3.OperationalError:  # Added meanwhile by another request.
                pass
            ids = [row[0] for row in connection.execute(f'SELECT id FROM {REPORT_TASKS_TABLE} ORDER BY name COLLATE NOCASE, id')]
            connection.executemany(f'UPDATE {REPORT_TASKS_TABLE} SET position = ? WHERE id = ?',
                                   [(index, task_id) for index, task_id in enumerate(ids, 1)])
        with _LEGACY_JOBS_LOCK:
            if database not in _LEGACY_JOBS_STORED:
                changes = _reports_own_their_schedules(connection)
                _LEGACY_JOBS_STORED.add(database)
    if changes and (changes['deleted'] or changes['merged']):
        for folder in changes['folders']:
            if REPORTING_JOBS_FOLDER in Path(folder).parts:
                shutil.rmtree(folder, ignore_errors=True)
        task_repository.try_add_log('system', 'reporting_jobs_became_report_schedules', json.dumps(
            {key: changes[key] for key in ('kept', 'merged', 'deleted')}, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Definitions and schedules
# ---------------------------------------------------------------------------
def _ids(values: Any) -> list[int]:
    return list(dict.fromkeys(int(value) for value in values or [] if str(value).strip().lstrip('-').isdigit()))


def _strings(values: Any) -> list[str]:
    if isinstance(values, str):
        values = [values]
    return list(dict.fromkeys(str(value).strip() for value in values or [] if str(value).strip()))


def _formats(values: Any) -> list[str]:
    selected = [value for value in _strings(values) if value in REPORT_FORMATS]
    return selected or ['powerpoint']


def _date_text(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f'Invalid date: {text}.') from exc


CDR_ANALYSIS_KINDS = {'data': 'CDR Data', 'voice': 'CDR Voice', 'speech': 'CDR Speech'}


def normalize_definition(raw: Any) -> dict[str, Any]:
    """What the schedule of a report generates: the report (the bundle_report_template artifact with its one favourite,
    see bundle_report_templates) and its formats; raises ValueError when there is none."""
    raw = raw if isinstance(raw, dict) else {}
    definition: dict[str, Any] = {
        # Artifacts of modules registered in ARTIFACT_PROVIDERS.
        'modules': {},
        'theme': normalize_theme(str(raw.get('theme') or '').strip() or DEFAULT_THEME),
    }
    for key, config in (raw.get('modules') or {}).items() if isinstance(raw.get('modules'), dict) else ():
        key = LEGACY_PROVIDER_KEYS.get(key, key)
        provider = ARTIFACT_PROVIDERS.get(key)
        if provider and isinstance(config, dict) and config.get('enabled'):
            formats = [value for value in _strings(config.get('formats')) if value in provider['formats']] or [provider['formats'][0]]
            definition['modules'][key] = {'enabled': True, 'formats': formats,
                                          'options': config.get('options') if isinstance(config.get('options'), dict) else {}}
    if not definition['modules']:
        raise ValueError('Choose the report to generate.')
    return definition


def normalize_schedule(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get('mode') if raw.get('mode') in SCHEDULE_MODES else 'manual'
    time_text = str(raw.get('time') or '08:00').strip()
    if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', time_text):
        raise ValueError('Enter the time as HH:MM.')
    schedule: dict[str, Any] = {'mode': mode, 'time': time_text}
    if mode == 'once':
        schedule['date'] = _date_text(raw.get('date'))
        if not schedule['date']:
            raise ValueError('Choose the date of the single execution.')
    if mode == 'weekly':
        schedule['weekdays'] = sorted({int(day) for day in raw.get('weekdays') or [] if str(day).isdigit() and 0 <= int(day) <= 6})
        if not schedule['weekdays']:
            raise ValueError('Choose at least one weekday.')
    if mode == 'monthly':
        day = int(raw.get('day_of_month') or 1)
        if not 1 <= day <= 31:
            raise ValueError('The day of the month must be between 1 and 31.')
        schedule['day_of_month'] = day
    return schedule


def next_run_after(schedule: dict[str, Any], after: datetime) -> datetime | None:
    """Next execution strictly after ``after`` (an aware local datetime), or None."""
    mode = schedule.get('mode')
    hour, minute = (int(part) for part in str(schedule.get('time') or '08:00').split(':'))
    tz = after.tzinfo

    def at(day: date) -> datetime:
        return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)

    if mode == 'once':
        candidate = at(date.fromisoformat(schedule['date']))
        return candidate if candidate > after else None
    if mode == 'daily':
        candidate = at(after.date())
        return candidate if candidate > after else at(after.date() + timedelta(days=1))
    if mode == 'weekly':
        for offset in range(0, 8):
            day = after.date() + timedelta(days=offset)
            if day.weekday() in schedule.get('weekdays', []) and at(day) > after:
                return at(day)
        return None
    if mode == 'monthly':
        year, month = after.year, after.month
        for _ in range(0, 13):
            day = min(int(schedule.get('day_of_month') or 1), calendar.monthrange(year, month)[1])
            candidate = at(date(year, month, day))
            if candidate > after:
                return candidate
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return None


def used_modules(definition: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(module, label, required feature) for every kind of artifact a definition includes."""
    used = []
    for key in definition.get('modules') or {}:
        provider = ARTIFACT_PROVIDERS.get(key)
        used.append((key, provider['label'] if provider else key, provider['feature'] if provider else key))
    return used


def recurrence_label(schedule: dict[str, Any]) -> str:
    mode, at_time = schedule.get('mode'), schedule.get('time') or '08:00'
    if mode == 'once':
        return f"Once · {schedule.get('date')} {at_time}"
    if mode == 'daily':
        return f'Daily · {at_time}'
    if mode == 'weekly':
        days = ', '.join(WEEKDAY_NAMES[day][:3] for day in schedule.get('weekdays', []))
        return f'Weekly · {days} · {at_time}'
    if mode == 'monthly':
        return f"Monthly · day {schedule.get('day_of_month')} · {at_time}"
    return 'Manual only'


def _chosen_favourites(definition: dict[str, Any]) -> list[str]:
    """The IDs of the favourite Bundle Report Templates a job generates (none: every favourite)."""
    report = (definition.get('modules') or {}).get('bundle_report_template') or {}
    return [str(value) for value in ((report.get('options') or {}).get('filters') or {}).get('favourites') or []]


def based_on_favourite(definition: dict[str, Any]) -> bool:
    """Whether a job only generates one favourite Bundle Report Template (made from a favourite in the Job Editor)."""
    report = (definition.get('modules') or {}).get('bundle_report_template') or {}
    others = (bool((definition.get('dataset_analysis') or {}).get('enabled')) or any(definition.get(key) for key in ('network_insights', 'designs', 'scoring'))
              or any(key != 'bundle_report_template' and (module or {}).get('enabled') for key, module in (definition.get('modules') or {}).items()))
    return bool(report.get('enabled')) and len(_chosen_favourites(definition)) == 1 and not others


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _loads(value: Any, default: Any) -> Any:
    try:
        decoded = json.loads(str(value or ''))
    except (TypeError, ValueError):
        return default
    return decoded if isinstance(decoded, type(default)) else default


def task_from_row(row: sqlite3.Row) -> dict[str, Any]:
    definition = _loads(row['definition_json'], {})
    try:
        # Stored definitions are read through the current model.
        definition = normalize_definition(definition)
    except (ValueError, TypeError):
        pass
    schedule = _loads(row['schedule_json'], {'mode': 'manual', 'time': '08:00'})
    return {
        'id': int(row['id']), 'name': str(row['name']), 'definition': definition,
        'send_email': bool(row['send_email']), 'recipients': _loads(row['recipients_json'], []),
        'schedule': schedule, 'recurrence': recurrence_label(schedule), 'enabled': bool(row['enabled']),
        'next_run_at': row['next_run_at'], 'last_run_id': row['last_run_id'],
        'created_by': str(row['created_by']), 'created_at': str(row['created_at']), 'updated_at': str(row['updated_at']),
        'position': int(row['position']) if 'position' in row.keys() else 0,
    }


def run_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'id': int(row['id']), 'task_id': int(row['task_id']), 'task_name': str(row['task_name']),
        'trigger': str(row['trigger']), 'status': str(row['status']), 'progress': int(row['progress'] or 0),
        'message': str(row['message'] or ''), 'requested_by': str(row['requested_by']),
        'created_at': str(row['created_at']), 'started_at': row['started_at'], 'finished_at': row['finished_at'],
        'send_email': bool(row['send_email']), 'recipients': _loads(row['recipients_json'], []),
        'email_status': str(row['email_status'] or ''), 'artifacts': _current_artifact_modules(_loads(row['artifacts_json'], [])),
        'output_dir': str(row['output_dir'] or ''), 'error': str(row['last_error'] or ''),
        'control': _loads(row['control_json'], {}) if 'control_json' in row.keys() else {},
    }


def list_tasks(task_repository: Any) -> list[dict[str, Any]]:
    ensure_report_task_tables(task_repository)
    with task_repository.connection() as connection:
        rows = connection.execute(f'SELECT * FROM {REPORT_TASKS_TABLE} ORDER BY position, name COLLATE NOCASE, id').fetchall()
    return [task_from_row(row) for row in rows]


def get_task(task_repository: Any, task_id: int) -> dict[str, Any] | None:
    ensure_report_task_tables(task_repository)
    with task_repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {REPORT_TASKS_TABLE} WHERE id = ?', (task_id,)).fetchone()
    return task_from_row(row) if row else None


def save_task(task_repository: Any, task_id: int | None, payload: dict[str, Any], username: str,
              *, parse_recipients, invalid_recipients, reassign_owner: bool = False) -> dict[str, Any]:
    """Create or update a Reporting Job after validating every field.

    A new job belongs to ``username``; an updated one keeps its owner unless ``reassign_owner`` is set.
    """
    name = str(payload.get('name') or '').strip()
    if not name:
        raise ValueError('Enter a name for the report.')
    definition = normalize_definition(payload.get('definition'))
    schedule = normalize_schedule(payload.get('schedule'))
    send_email = bool(payload.get('send_email'))
    recipients = parse_recipients(payload.get('recipients'))
    if send_email:
        if not recipients:
            raise ValueError('Add at least one email recipient or disable email delivery.')
        if invalid := invalid_recipients(recipients):
            raise ValueError(f"Invalid email recipients: {', '.join(invalid)}.")
    enabled = bool(payload.get('enabled', True))
    next_run = next_run_after(schedule, now_local()) if enabled else None
    if schedule['mode'] == 'once' and next_run is None:
        raise ValueError('The single execution must be in the future.')
    now = now_local().isoformat()
    values = (name[:160], json.dumps(definition, ensure_ascii=False), int(send_email), json.dumps(recipients),
              json.dumps(schedule), int(enabled), next_run.isoformat() if next_run else None)
    ensure_report_task_tables(task_repository)
    with task_repository.connection() as connection:
        if task_id is None:
            # A new job goes to the end of the jobs table.
            task_id = int(connection.execute(
                f'INSERT INTO {REPORT_TASKS_TABLE} (name, definition_json, send_email, recipients_json, schedule_json, enabled, next_run_at, '
                f'created_by, created_at, updated_at, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '
                f'(SELECT COALESCE(MAX(position), 0) + 1 FROM {REPORT_TASKS_TABLE}))',
                (*values, username, now, now),
            ).lastrowid)
        elif connection.execute(
            f'UPDATE {REPORT_TASKS_TABLE} SET name = ?, definition_json = ?, send_email = ?, recipients_json = ?, schedule_json = ?, '
            'enabled = ?, next_run_at = ?, updated_at = ? WHERE id = ?', (*values, now, task_id),
        ).rowcount == 0:
            raise ValueError('The schedule of the report no longer exists.')
        if reassign_owner:
            connection.execute(f'UPDATE {REPORT_TASKS_TABLE} SET created_by = ? WHERE id = ?', (username, task_id))
    return get_task(task_repository, task_id)


def rename_definition_values(task_repository: Any, transform: Callable[[dict[str, Any]], dict[str, Any]],
                             write: bool = True) -> int:
    """Apply ``transform`` to every Reporting Job definition (a renamed Operator or Vendor); returns how many changed.

    A changed job is saved again, so a Job Editor draft of its previous version is not restored. Without
    ``write`` the jobs are only counted.
    """
    ensure_report_task_tables(task_repository)
    changed = 0
    now = now_local().isoformat()
    with task_repository.connection() as connection:
        for row in connection.execute(f'SELECT id, definition_json FROM {REPORT_TASKS_TABLE}').fetchall():
            try:
                definition = json.loads(row['definition_json'] or '{}')
            except (TypeError, ValueError):
                continue
            renamed = transform(definition)
            if renamed != definition and not write:
                changed += 1
            elif renamed != definition:
                connection.execute(f'UPDATE {REPORT_TASKS_TABLE} SET definition_json = ?, updated_at = ? WHERE id = ?',
                                   (json.dumps(renamed, ensure_ascii=False), now, row['id']))
                changed += 1
    return changed


def delete_task(task_repository: Any, task_id: int) -> list[str]:
    """Delete a Reporting Job and its runs; returns the run folders to remove."""
    ensure_report_task_tables(task_repository)
    with task_repository.connection() as connection:
        folders = [str(row['output_dir']) for row in connection.execute(
            f'SELECT output_dir FROM {REPORT_TASK_RUNS_TABLE} WHERE task_id = ?', (task_id,)).fetchall() if row['output_dir']]
        if connection.execute(f'DELETE FROM {REPORT_TASKS_TABLE} WHERE id = ?', (task_id,)).rowcount == 0:
            raise ValueError('The schedule of the report no longer exists.')
        connection.execute(f'DELETE FROM {REPORT_TASK_RUNS_TABLE} WHERE task_id = ?', (task_id,))
    return folders


def list_runs(task_repository: Any, task_id: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
    ensure_report_task_tables(task_repository)
    query = f'SELECT * FROM {REPORT_TASK_RUNS_TABLE}' + (' WHERE task_id = ?' if task_id is not None else '') + ' ORDER BY id DESC LIMIT ?'
    with task_repository.connection() as connection:
        rows = connection.execute(query, ((task_id, limit) if task_id is not None else (limit,))).fetchall()
    return [run_from_row(row) for row in rows]


def get_run(task_repository: Any, run_id: int) -> dict[str, Any] | None:
    ensure_report_task_tables(task_repository)
    with task_repository.connection() as connection:
        row = connection.execute(f'SELECT * FROM {REPORT_TASK_RUNS_TABLE} WHERE id = ?', (run_id,)).fetchone()
    return run_from_row(row) if row else None


def update_run(task_repository: Any, run_id: int, **changes: Any) -> None:
    if not changes:
        return
    columns = {'artifacts': 'artifacts_json', 'recipients': 'recipients_json', 'error': 'last_error', 'control': 'control_json'}
    assignments, values = [], []
    for key, value in changes.items():
        column = columns.get(key, key)
        if column in {'artifacts_json', 'recipients_json', 'control_json'} and not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        assignments.append(f'{column} = ?')
        values.append(value)
    with task_repository.connection() as connection:
        connection.execute(f'UPDATE {REPORT_TASK_RUNS_TABLE} SET {", ".join(assignments)} WHERE id = ?', (*values, run_id))


def create_run(task_repository: Any, task: dict[str, Any], trigger: str, username: str) -> int:
    with task_repository.connection() as connection:
        run_id = int(connection.execute(
            f'INSERT INTO {REPORT_TASK_RUNS_TABLE} (task_id, task_name, trigger, status, message, requested_by, created_at, send_email, recipients_json) '
            "VALUES (?, ?, ?, 'queued', 'Waiting to start', ?, ?, ?, ?)",
            (task['id'], task['name'], trigger, username, now_local().isoformat(), int(task['send_email']), json.dumps(task['recipients'])),
        ).lastrowid)
        connection.execute(f'UPDATE {REPORT_TASKS_TABLE} SET last_run_id = ? WHERE id = ?', (run_id, task['id']))
    return run_id


def claim_due_tasks(task_repository: Any, now: datetime) -> list[dict[str, Any]]:
    """Advance every due job to its next execution and return the jobs to run once each."""
    ensure_report_task_tables(task_repository)
    due = []
    with task_repository.connection() as connection:
        rows = connection.execute(
            f'SELECT * FROM {REPORT_TASKS_TABLE} WHERE enabled = 1 AND next_run_at IS NOT NULL').fetchall()
        for row in rows:
            try:
                scheduled = datetime.fromisoformat(str(row['next_run_at']))
            except ValueError:
                continue
            if scheduled > now:
                continue
            task = task_from_row(row)
            # Missed executions collapse into this single run.
            following = next_run_after(task['schedule'], now)
            claimed = connection.execute(
                f'UPDATE {REPORT_TASKS_TABLE} SET next_run_at = ? WHERE id = ? AND next_run_at = ?',
                (following.isoformat() if following else None, task['id'], row['next_run_at']),
            ).rowcount
            if claimed:
                due.append(task)
    return due


# The control of a run as a JSON object: how it is carried on, where a restart interrupted it (the timestamp and folder
# of its artifacts, a signature of its steps and how many it finished), how many restarts it went on after and who
# stopped it.
_CONTROL = "COALESCE(NULLIF(control_json, ''), '{}')"


def claim_run(task_repository: Any, run_id: int) -> bool:
    """Start a queued run; False when it is no longer queued (a user stopped it meanwhile)."""
    with task_repository.connection() as connection:
        return bool(connection.execute(
            f"UPDATE {REPORT_TASK_RUNS_TABLE} SET status = 'running', message = 'Generating artifacts', progress = 1 "
            "WHERE id = ? AND status = 'queued'", (run_id,)).rowcount)


def request_stop(task_repository: Any, run_id: int, username: str) -> str | None:
    """Stop a queued run at once, or have a running one stop after the step it is on; the status it was in, or None
    when it was neither."""
    for _attempt in range(3):
        run = get_run(task_repository, run_id)
        if run is None or run['status'] not in {'queued', 'running'}:
            return None
        with task_repository.connection() as connection:
            if run['status'] == 'queued':
                changed = connection.execute(
                    f"UPDATE {REPORT_TASK_RUNS_TABLE} SET status = 'stopped', message = ?, finished_at = ?, "
                    f"control_json = json_set({_CONTROL}, '$.stopped_by', ?) WHERE id = ? AND status = 'queued'",
                    (f'Stopped by {username} before it started', now_local().isoformat(), username, run_id)).rowcount
            else:
                changed = connection.execute(
                    f"UPDATE {REPORT_TASK_RUNS_TABLE} SET status = 'stopping', control_json = json_set({_CONTROL}, '$.stopped_by', ?) "
                    "WHERE id = ? AND status = 'running'", (username, run_id)).rowcount
        if changed:
            return run['status']
    return None


def update_run_control(task_repository: Any, run_id: int, artifacts: list[dict[str, Any]] | None = None, **values: Any) -> None:
    """Set keys of the control of a run, keeping the others (such as who stopped it meanwhile), and its artifacts in the
    same write when given (the artifacts of the steps it finished)."""
    paths = ', '.join("?, json(?)" for _ in values)
    with task_repository.connection() as connection:
        connection.execute(
            f"UPDATE {REPORT_TASK_RUNS_TABLE} SET control_json = json_set({_CONTROL}, {paths})"
            + (', artifacts_json = ?' if artifacts is not None else '') + ' WHERE id = ?',
            (*[part for key, value in values.items() for part in (f'$.{key}', json.dumps(value))],
             *([json.dumps(artifacts, ensure_ascii=False)] if artifacts is not None else []), run_id))


def reset_run(task_repository: Any, run: dict[str, Any], task: dict[str, Any], username: str) -> bool:
    """Queue a failed or stopped run again as a new manual run of its job; False when it is in another status."""
    with task_repository.connection() as connection:
        changed = connection.execute(
            f"UPDATE {REPORT_TASK_RUNS_TABLE} SET task_name = ?, trigger = 'manual', status = 'queued', progress = 0, "
            "message = 'Waiting to start', requested_by = ?, created_at = ?, started_at = NULL, finished_at = NULL, send_email = ?, "
            "recipients_json = ?, email_status = '', artifacts_json = '[]', output_dir = '', last_error = '', control_json = '{}' "
            f"WHERE id = ? AND status IN ({', '.join('?' for _ in RUN_RERUN_STATUSES)})",
            (task['name'], username, now_local().isoformat(), int(task['send_email']), json.dumps(task['recipients']),
             run['id'], *RUN_RERUN_STATUSES)).rowcount
        if changed:
            connection.execute(f'UPDATE {REPORT_TASKS_TABLE} SET last_run_id = ? WHERE id = ?', (run['id'], task['id']))
    return bool(changed)


def interrupted_runs(task_repository: Any, active_run_ids: set[int]) -> list[dict[str, Any]]:
    """The runs left waiting, running or stopping by the previous process: those it was running first."""
    ensure_report_task_tables(task_repository)
    with task_repository.connection() as connection:
        rows = connection.execute(
            f"SELECT * FROM {REPORT_TASK_RUNS_TABLE} WHERE status IN ({', '.join('?' for _ in RUN_ACTIVE_STATUSES)}) "
            "ORDER BY status = 'queued', id", RUN_ACTIVE_STATUSES).fetchall()
    return [run for run in map(run_from_row, rows) if run['id'] not in active_run_ids]


class RunStopped(BaseException):
    """Raised in a Reporting Job run that a user stopped. A BaseException (as asyncio's CancelledError), so the steps
    that report their own failures as failed artifacts (``except Exception``) let it through."""


# The run the thread is generating, so that long steps can stop it (see check_run_stopped).
_RUN_CONTEXT = local()


def check_run_stopped(at_once: bool = False) -> None:
    """Raise RunStopped in the thread of a Reporting Job run that a user stopped (or deleted); nothing elsewhere.

    Long steps call it while they work or wait; it reads the run at most once a second, unless ``at_once``.
    """
    current = getattr(_RUN_CONTEXT, 'run', None)
    if current is None or (not at_once and time.monotonic() - current['checked'] < 1):
        return
    current['checked'] = time.monotonic()
    run = get_run(current['repository'], current['run_id'])
    if run is None or run['status'] == 'stopping':
        raise RunStopped()


def report_step_progress(percent: float, message: str = '') -> None:
    """Move the progress of the Reporting Job run of this thread within the share of the step it is on (``percent`` of
    the step, 0 to 100) and say what the step is doing; nothing elsewhere. It writes the run at most once a second."""
    current = getattr(_RUN_CONTEXT, 'run', None)
    if current is None or not current.get('step') or time.monotonic() - current.get('reported', 0.0) < 1:
        return
    current['reported'] = time.monotonic()
    start, share, label = current['step']
    update_run(current['repository'], current['run_id'], message=f'{label}: {message}' if message else label,
               progress=max(1, min(94, round(start + share * max(0.0, min(100.0, float(percent))) / 100))))


def export_tasks_document(task_repository: Any) -> bytes:
    """The schedules of the reports (the Reporting Jobs element of the exports): each names its report, so the workspace
    that receives it finds its own. The reports travel as an element of their own (Bundle Report Template Favourites)."""
    tasks = list_tasks(task_repository)
    from src.modules.reporting.bundle_report_templates import list_favourites
    favourite_names = {str(item['id']): item['name'] for item in list_favourites(task_repository)}
    chosen = {value for task in tasks for value in _chosen_favourites(task['definition'])}
    from src.modules.core.transfer_identities import REPORTING_JOBS, portable_identities
    uids = portable_identities(task_repository, REPORTING_JOBS, [str(task['id']) for task in tasks])
    document = {
        'format': 'drivetest-analyzer-reporting-jobs', 'version': 2,
        'favourite_names': {value: favourite_names[value] for value in sorted(chosen) if value in favourite_names},
        'reporting_jobs': [{**{key: task[key] for key in ('name', 'definition', 'send_email', 'recipients', 'schedule', 'enabled', 'created_by')},
                            'uid': uids[str(task['id'])]} for task in tasks],
    }
    return json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')


def _remap_favourites(definition: dict[str, Any], source_names: dict[str, str], destination: dict[str, str]) -> dict[str, Any]:
    """A schedule of another workspace with the ID of the report of the same name here (the name when there is none, so
    it is not imported)."""
    chosen = _chosen_favourites(definition)
    if not chosen:
        return definition

    def mapped_value(value: str) -> str:
        name = source_names.get(value) or (None if value.isdigit() else value)
        return value if name is None else destination.get(name.casefold(), name)

    mapped = list(dict.fromkeys(mapped_value(value) for value in chosen))
    definition = json.loads(json.dumps(definition))
    definition['modules']['bundle_report_template'].setdefault('options', {}).setdefault('filters', {})['favourites'] = mapped
    return definition


def imported_jobs(task_repository: Any, document: dict[str, Any]) -> list[tuple[int, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    """The schedules of an exported document as this workspace saves them (also for the preview of an import): each with
    its position in the document, its item, its definition pointing at the report of the same name here and its
    schedule (a past single execution becomes manual). Those of a report this workspace does not have, and the jobs of
    artifacts designed in the job (removed with the Job Editor), are left out."""
    from src.modules.reporting.bundle_report_templates import list_favourites
    favourite_names = {str(key): str(value) for key, value in (document.get('favourite_names') or {}).items()}
    favourites_here = {item['name'].casefold(): str(item['id']) for item in list_favourites(task_repository)}
    jobs = []
    for index, item in enumerate(document.get('reporting_jobs') or []):
        if not isinstance(item, dict):
            continue
        schedule = dict(item.get('schedule') or {})
        if schedule.get('mode') == 'once' and next_run_after(normalize_schedule(schedule), now_local()) is None:
            schedule['mode'] = 'manual'  # A past single execution cannot be scheduled again.
        definition = json.loads(json.dumps(item.get('definition') or {}))
        _current_provider_keys(definition)  # Exported when Bundle Report Templates had a former name.
        definition = _remap_favourites(definition, favourite_names, favourites_here)
        if not based_on_favourite(definition) or _chosen_favourites(definition)[0] not in favourites_here.values():
            continue
        jobs.append((index, item, definition, schedule))
    return jobs


def import_tasks_document(
    task_repository: Any, content: bytes | str, username: str, *, parse_recipients, invalid_recipients,
    user_exists: Callable[[str], bool] = lambda _name: False, summary: list[str] | None = None,
) -> int:
    """Give the reports of this workspace the schedules of an exported document (each replaces the schedule of the
    report of the same name); ``summary`` receives those left out because this workspace has no such report.

    Schedules run with the feature access of their owner, so each keeps the owner it had on the source server when that
    user exists here; otherwise it belongs to ``username``, the user who imports it.
    """
    document = json.loads(content)
    if not isinstance(document, dict) or canonical_format(document.get('format')) != 'drivetest-analyzer-reporting-jobs':
        raise ValueError('The file is not a DriveTest Analyzer Report Schedules export.')
    from src.modules.core.transfer_identities import REPORTING_JOBS, set_identities
    from src.modules.reporting.bundle_report_templates import list_favourites
    names = {str(item['id']): item['name'] for item in list_favourites(task_repository)}
    imported_uids: dict[str, str] = {}
    imported = 0
    jobs = imported_jobs(task_repository, document)
    for _index, item, definition, schedule in jobs:
        favourite_id = _chosen_favourites(definition)[0]
        source_owner = str(item.get('created_by') or '').strip()
        owner = source_owner if source_owner and user_exists(source_owner) else username
        current = report_task(task_repository, favourite_id)
        task = save_task(task_repository, current['id'] if current else None,
                         {**item, 'name': names[favourite_id], 'definition': definition, 'schedule': schedule}, owner,
                         parse_recipients=parse_recipients, invalid_recipients=invalid_recipients, reassign_owner=True)
        imported_uids[str(task['id'])] = str(item.get('uid') or '')
        imported += 1
    set_identities(task_repository, REPORTING_JOBS, imported_uids)
    left_out = len([item for item in document.get('reporting_jobs') or [] if isinstance(item, dict)]) - len(jobs)
    if summary is not None and left_out > 0:
        summary.append(f'{left_out} schedule{"s" if left_out != 1 else ""} left out: this workspace has no report of '
                       f'{"their names" if left_out != 1 else "its name"}, or they generated artifacts designed in the job.')
    return imported


# ---------------------------------------------------------------------------
# The schedule of each report in its Report Definition (Import / Export / Transfer and backups)
# ---------------------------------------------------------------------------
def _report_formats(formats: Any) -> list[str]:
    chosen = [value for value in formats if value in REPORT_FORMATS] if isinstance(formats, list) else []
    return chosen or ['powerpoint']


def schedule_entries(task_repository: Any) -> dict[str, dict[str, Any]]:
    """The schedule of each report as its Report Definition carries it, by the favourite ID of the report: when it is
    generated (``recurrence``), its formats, whether it is generated on its own (``enabled``), its email, its owner and
    its identity (the reports without one carry none)."""
    from src.modules.core.transfer_identities import REPORTING_JOBS, portable_identities

    tasks = report_tasks_by_favourite(task_repository)
    uids = portable_identities(task_repository, REPORTING_JOBS, [str(task['id']) for task in tasks.values()])
    return {favourite_id: {
        'recurrence': task['schedule'],
        'formats': _report_formats(((task['definition'].get('modules') or {}).get('bundle_report_template') or {}).get('formats')),
        'enabled': bool(task['enabled']), 'send_email': bool(task['send_email']), 'recipients': list(task['recipients'] or []),
        'created_by': task['created_by'], 'uid': uids[str(task['id'])],
    } for favourite_id, task in tasks.items()}


def imported_schedule_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """The schedule a Report Definition carries as its import saves it (a past single execution becomes manual), for the
    preview of an import."""
    recurrence = dict(entry.get('recurrence') or {})
    try:
        recurrence = normalize_schedule(recurrence)
        if recurrence['mode'] == 'once' and next_run_after(recurrence, now_local()) is None:
            recurrence['mode'] = 'manual'
    except ValueError:  # The import refuses it then; the preview shows it as the package has it.
        pass
    return {**entry, 'recurrence': recurrence, 'formats': _report_formats(entry.get('formats'))}


def schedules_document(saved: list[tuple[dict[str, Any], int]]) -> dict[str, Any] | None:
    """The schedules of the Report Definitions of a document, as a Report Schedules document that gives each one to the
    report it was saved as here (``saved``: each entry with the ID of its report), for import_tasks_document; ``None``
    when they carry none."""
    jobs = [{'name': str(entry.get('name') or ''), 'definition': report_definition(favourite_id, entry['schedule'].get('formats')),
             'schedule': entry['schedule'].get('recurrence') or {}, 'enabled': bool(entry['schedule'].get('enabled', True)),
             'send_email': bool(entry['schedule'].get('send_email')), 'recipients': entry['schedule'].get('recipients') or [],
             'created_by': str(entry['schedule'].get('created_by') or ''), 'uid': str(entry['schedule'].get('uid') or '')}
            for entry, favourite_id in saved if isinstance(entry.get('schedule'), dict)]
    return {'format': 'drivetest-analyzer-reporting-jobs', 'version': 2, 'favourite_names': {}, 'reporting_jobs': jobs} if jobs else None


def _recurrence_text(recurrence: Any) -> str:
    """When a schedule generates its report, as the preview of an import tells it (``Weekly · Mon · 08:00``)."""
    recurrence = recurrence if isinstance(recurrence, dict) else {}
    if recurrence.get('mode') not in SCHEDULE_MODES or recurrence.get('mode') == 'manual':
        return 'Only with Generate'
    try:
        return recurrence_label(recurrence)
    except (IndexError, TypeError):  # Not a schedule the import saves: told as the package has it.
        return json.dumps(recurrence, ensure_ascii=False, sort_keys=True)


def schedule_changes(before: Any, after: Any) -> list[str]:
    """What changes in the schedule of a report, as the preview of an import tells it (its identity is no change)."""
    from src.modules.core.import_changes import describe_changes

    def values(entry: Any) -> dict[str, Any]:
        entry = entry if isinstance(entry, dict) else {}
        return {'recurrence': _recurrence_text(entry['recurrence']) if entry.get('recurrence') else None,
                'formats': [{'powerpoint': 'PowerPoint', 'word': 'Word'}.get(value, value) for value in entry.get('formats') or []] or None,
                **{key: entry.get(key) for key in ('enabled', 'send_email', 'recipients', 'created_by') if key in entry}}

    old, new = values(before), values(after)
    if not isinstance(after, dict):
        return []
    if not isinstance(before, dict):
        return [f'Schedule: {new["recurrence"] or "Only with Generate"}']
    labels = {'recurrence': 'Recurrence', 'formats': 'Formats', 'enabled': 'Generate on its own', 'send_email': 'Email it',
              'recipients': 'Recipients', 'created_by': 'Owner'}
    return [f'Schedule · {change}' for change in describe_changes(old, new, labels)]


# ---------------------------------------------------------------------------
# The schedule of each report
# ---------------------------------------------------------------------------
def report_definition(favourite_id: int | str, formats: list[str] | None = None) -> dict[str, Any]:
    """What the schedule of a report generates: the report (the bundle_report_template artifact) in ``formats``."""
    chosen = [value for value in formats or [] if value in REPORT_FORMATS] or ['powerpoint']
    return {'modules': {'bundle_report_template': {'enabled': True, 'formats': chosen,
                                                   'options': {'filters': {'favourites': [str(favourite_id)]}}}}}


def report_favourite_id(task: dict[str, Any]) -> str:
    """The report a schedule generates (its favourite ID), or '' for one that generates no single report."""
    return _chosen_favourites(task['definition'])[0] if based_on_favourite(task['definition']) else ''


def report_tasks_by_favourite(task_repository: Any) -> dict[str, dict[str, Any]]:
    """The schedule of each report, by its favourite ID."""
    found: dict[str, dict[str, Any]] = {}
    for task in list_tasks(task_repository):
        favourite_id = report_favourite_id(task)
        if favourite_id and favourite_id not in found:
            found[favourite_id] = task
    return found


def report_task(task_repository: Any, favourite_id: int | str) -> dict[str, Any] | None:
    return report_tasks_by_favourite(task_repository).get(str(favourite_id))


def save_report_schedule(task_repository: Any, favourite_id: int | str, name: str, payload: dict[str, Any], username: str,
                         *, parse_recipients, invalid_recipients) -> dict[str, Any]:
    """Give a report its schedule: whether it is generated on its own and when, its formats and whom it is emailed to.
    A report has one schedule; a new one belongs to ``username``."""
    current = report_task(task_repository, favourite_id)
    formats = [value for value in payload.get('formats') or [] if value in REPORT_FORMATS] or ['powerpoint', 'word']
    return save_task(task_repository, current['id'] if current else None, {
        'name': name, 'definition': report_definition(favourite_id, formats),
        'schedule': payload.get('schedule') or {'mode': 'manual', 'time': '08:00'},
        'enabled': bool(payload.get('enabled', True)), 'send_email': bool(payload.get('send_email')),
        'recipients': payload.get('recipients') or [],
    }, username, parse_recipients=parse_recipients, invalid_recipients=invalid_recipients)


def rename_report_task(task_repository: Any, favourite_id: int | str, name: str) -> None:
    """A renamed report renames its schedule (and the runs keep the name they had)."""
    task = report_task(task_repository, favourite_id)
    if task is not None and task['name'] != name[:160]:
        with task_repository.connection() as connection:
            connection.execute(f'UPDATE {REPORT_TASKS_TABLE} SET name = ?, updated_at = ? WHERE id = ?',
                               (name[:160], now_local().isoformat(), task['id']))


def delete_report_task(task_repository: Any, favourite_id: int | str) -> list[str]:
    """A deleted report takes its schedule and runs with it; returns the run folders to remove."""
    task = report_task(task_repository, favourite_id)
    return delete_task(task_repository, task['id']) if task is not None else []


# ---------------------------------------------------------------------------
# Email body
# ---------------------------------------------------------------------------
def email_subject(task_name: str, started: datetime) -> str:
    return f'{task_name} · {started.strftime("%Y-%m-%d %H:%M")}'


def _size_text(size: Any) -> str:
    size = int(size or 0)
    return f'{size / 1024 / 1024:.1f} MB' if size >= 1024 * 1024 else f'{max(size, 1) / 1024:.0f} KB'


# The format of each file of a report email, named and coloured as its application, so that the PowerPoint and the Word
# version of the same report do not look like the same file twice.
EMAIL_FILE_FORMATS = {
    '.pptx': ('PowerPoint', '#C43E1C'), '.docx': ('Word', '#185ABD'), '.xlsx': ('Excel', '#107C41'),
    '.csv': ('CSV', '#107C41'), '.pdf': ('PDF', '#B30B00'), '.zip': ('ZIP', '#5B6770'), '.json': ('JSON', '#5B6770'),
}
# The light tint of each colour, for the card of the file.
EMAIL_FORMAT_TINTS = {'#C43E1C': '#FBEDE8', '#185ABD': '#E8EFFA', '#107C41': '#E6F3EC', '#B30B00': '#FBE9E7', '#5B6770': '#F0F2F3'}


def email_file_format(file_name: str) -> tuple[str, str]:
    """The name and colour of the format of a file of a report email (its extension when it is not a known one)."""
    suffix = Path(str(file_name or '')).suffix.casefold()
    return EMAIL_FILE_FORMATS.get(suffix, (suffix.lstrip('.').upper() or 'File', '#5B6770'))


def previewed_formats(folder: Path) -> dict[str, str]:
    """The files of a run whose report has a preview, with the format the viewer opens them in (none without a preview)."""
    try:
        report = json.loads((Path(folder) / '.report' / 'report.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    formats = report.get('formats') if isinstance(report, dict) else None
    return {str(shown['file_name']): str(export_format) for export_format, shown in (formats or {}).items()
            if isinstance(shown, dict) and shown.get('file_name') and int(shown.get('previews') or 0) > 0}


def email_bodies(task_name: str, started: datetime, artifacts: list[dict[str, Any]], app_name: str, *,
                 links: dict[str, str] | None = None, attached: bool = True, link_days: int = 0,
                 details: bool = True, cards: bool = True, views: dict[str, str] | None = None) -> tuple[str, str]:
    """Plain-text and HTML bodies listing each artifact, its content and its filters: attached, or with its download link
    (valid ``link_days``) and, for the files of a report with a preview, the link that opens it online (``views``). With
    ``cards``, each file is a card under a heading of its format, in the colour of its application; without them (an email
    that must be shorter), a list with the format before each title."""
    links, views = links or {}, views or {}
    ready = [item for item in artifacts if item.get('status') == 'ready']
    failed = [item for item in artifacts if item.get('status') != 'ready']
    heading = f'Attached artifacts ({len(ready)})' if attached else f'Artifacts ({len(ready)})'
    text = [f'{task_name}', f'Generated by {app_name} on {started.strftime("%Y-%m-%d %H:%M %Z").strip()}.', '']
    parts = [f'<p><strong>{html.escape(task_name)}</strong><br>Generated by {html.escape(app_name)} on '
             f'{html.escape(started.strftime("%Y-%m-%d %H:%M %Z").strip())}.</p>']
    if links:
        # (Both links ask to sign in to the tool.)
        action = 'viewed online or downloaded' if views else 'downloaded'
        note = (f'Each file can also be {action} from its link for {link_days} days, signing in to {app_name}.' if attached else
                f'Sign in to {app_name} to {"view each file online or download it" if views else "download each file"} '
                f'from its link, valid for {link_days} days.')
        text += [note, '']
        parts.append(f'<p>{html.escape(note)}</p>')
    text.append(f'{heading}:')
    parts.append(f'<p><strong>{heading}</strong></p>' + ('' if cards else '<ol>'))
    for item in ready:
        # The format of each file, its title (what it is, from which module) and its file, its download link and size,
        # then its content.
        link, view = links.get(item['file_name']), views.get(item['file_name'])
        size = _size_text(item.get('size'))
        file_format, colour = email_file_format(item['file_name'])
        text += ['', f"[{file_format}] {item['title']}", f"    {item['file_name']} ({size})"] + (
            [f'    View online: {view}'] if view else []) + ([f'    Download {file_format}: {link}'] if link else [])
        lines = item.get('details') or [] if details else []
        text.extend(f'    {line}' for line in lines)
        listed = f"<ul>{''.join(f'<li>{html.escape(line)}</li>' for line in lines)}</ul>" if lines else ''
        download = ((f'<a href="{html.escape(view, quote=True)}"><strong>View online</strong></a> · ' if view else '')
                    + (f'<a href="{html.escape(link, quote=True)}"><strong>Download {html.escape(file_format)}</strong></a> · '
                       if link else ''))
        title = f"<strong>{html.escape(item['title'])}</strong><br><code>{html.escape(item['file_name'])}</code>"
        if cards:
            # The format on the heading of the card, with View Online, the download link and the size on its right; a
            # table, which every mail client colours, Outlook included.
            pill = (f'display:inline-block;background:#ffffff;color:{colour};padding:2px 10px;border-radius:10px;'
                    'font-weight:bold;text-decoration:none')
            button = ((f'<a href="{html.escape(view, quote=True)}" style="{pill}">View Online</a> ' if view else '')
                      + (f'<a href="{html.escape(link, quote=True)}" style="{pill}">Download</a> · ' if link else ''))
            parts.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:'
                         f'collapse;margin:0 0 14px;border:1px solid {colour}"><tr><td style="background:{colour};padding:6px 12px">'
                         f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td style="color:#ffffff;'
                         f'font-size:15px;font-weight:bold">{html.escape(file_format)}</td><td align="right" style="color:#ffffff;'
                         f'font-size:13px;white-space:nowrap">{button}{size}</td></tr></table></td></tr><tr><td style="background:'
                         f'{EMAIL_FORMAT_TINTS.get(colour, "#F0F2F3")};padding:10px 12px">{title}{listed}</td></tr></table>')
            continue
        badge = (f'<span style="display:inline-block;padding:1px 8px;margin-right:6px;border-radius:10px;background:{colour};'
                 f'color:#ffffff;font-size:12px;font-weight:bold">{html.escape(file_format)}</span>')
        parts.append(f'<li style="margin-bottom:12px">{badge}{title} ({download}{size}){listed}</li>')
    parts.append('' if cards else '</ol>')
    if failed:
        text += ['', f'Not generated ({len(failed)}):'] + [f"- {item['title']}: {item.get('error') or 'failed'}" for item in failed]
        parts.append(f'<p><strong>Not generated ({len(failed)})</strong></p><ul>' + ''.join(
            f"<li>{html.escape(item['title'])}: {html.escape(item.get('error') or 'failed')}</li>" for item in failed) + '</ul>')
    return '\n'.join(text) + '\n', '<html><body style="font-family:Arial,sans-serif;font-size:14px">' + ''.join(parts) + '</body></html>'


def safe_file_name(value: str) -> str:
    """A portable file name of at most 150 characters that keeps its extension."""
    cleaned = re.sub(r'\s+', ' ', re.sub(r'[\\/:*?"<>|\x00-\x1f]+', ' ', value)).strip()
    suffix = Path(cleaned).suffix if re.fullmatch(r'\.[A-Za-z0-9]{1,5}', Path(cleaned).suffix or '') else ''
    stem = cleaned[:len(cleaned) - len(suffix)] if suffix else cleaned
    return (stem[:150 - len(suffix)].rstrip(' .-') or 'artifact') + suffix


_LEADING_STAMP = re.compile(r'^\s*\d{8}_\d{6}\s*-\s*')


def artifact_path(folder: Path, stamp: str, module: str, name: str, suffix: str) -> Path:
    """``<yyyymmdd_hhmmss> - <Module> - <Report name><suffix>``, unique in ``folder``.

    The report name drops its own leading timestamps and module name, so a
    PPT Design or Scoring PPT does not repeat them.
    """
    report = str(name or '').strip()
    while _LEADING_STAMP.match(report):
        report = _LEADING_STAMP.sub('', report, count=1)
    report = re.sub(rf'^\s*{re.escape(module)}\s*(?:-\s*|$)', '', report, flags=re.IGNORECASE).strip(' -')
    base = f'{stamp} - {module}' + (f' - {report}' if report else '')
    candidate, copy = folder / safe_file_name(f'{base}{suffix}'), 2
    while candidate.exists():
        candidate, copy = folder / safe_file_name(f'{base} ({copy}){suffix}'), copy + 1
    return candidate


def run_stamp(run: dict[str, Any]) -> str:
    """The yyyymmdd_hhmmss timestamp of a run, as in its artifact names."""
    match = re.match(r'(\d{8}_\d{6})', Path(str(run.get('output_dir') or '')).name)
    if match:
        return match.group(1)
    for key in ('started_at', 'created_at'):
        try:
            return datetime.fromisoformat(str(run.get(key))).strftime('%Y%m%d_%H%M%S')
        except (TypeError, ValueError):
            continue
    return now_local().strftime('%Y%m%d_%H%M%S')


def zip_artifacts(run: dict[str, Any]) -> BytesIO:
    buffer = BytesIO()
    folder = Path(run['output_dir'])
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for item in run['artifacts']:
            path = folder / str(item.get('file_name') or '')
            if item.get('status') == 'ready' and path.is_file():
                archive.write(path, path.name)
    buffer.seek(0)
    return buffer


def zip_runs_artifacts(runs: list[dict[str, Any]]) -> Any:
    """The artifacts of several runs in one ZIP, each run in a folder named after its time and its job; written to a
    temporary file (rewound), as large as the artifacts are."""
    output = tempfile.TemporaryFile()
    folders: set[str] = set()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for run in runs:
            folder_name = safe_file_name(f"{run_stamp(run)} - {run['task_name']}")
            if folder_name in folders:
                folder_name = f"{folder_name} (run {run['id']})"
            folders.add(folder_name)
            folder = Path(run['output_dir'])
            for item in run['artifacts']:
                path = folder / str(item.get('file_name') or '')
                if item.get('status') == 'ready' and path.is_file():
                    archive.write(path, f'{folder_name}/{path.name}')
    output.seek(0)
    return output


# ---------------------------------------------------------------------------
# Execution and routes
# ---------------------------------------------------------------------------
def install_report_task_routes(core: Any) -> None:
    from fastapi import Depends, HTTPException, Query, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
    from pydantic import BaseModel, Field

    app = core.app
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='reporting-jobs')
    # Runs of workspaces other than the active one each use their own worker process.
    worker_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='reporting-workers')
    # (workspace database, run ID): run IDs are only unique within a workspace.
    active_runs: set[tuple[str, int]] = set()
    active_lock = Lock()
    recovered_databases: set[str] = set()


    def reporting_repository(user):
        if not core.active_workspace:
            raise HTTPException(409, 'Open a workspace before using Reporting.')
        core.require_workspace_access(user, core.active_workspace.id)
        return core.Repository(core.active_workspace.database_path, global_db_path=core.repository.global_db_path,
                               workspace_registry_db_path=core.workspace_registry.registry_path)

    def reporting_user(user=Depends(core.current_user)):
        return user

    def editor_user(user=Depends(core.current_user)):
        if user.role not in {'user-editor', 'admin', 'super-admin'}:
            raise HTTPException(403, 'Editor access is required to change reports and their runs.')
        return user

    def run_user(username: str):
        record = core.repository.get_user(username)
        return core.SessionUser(username=username, role=record.role if record else 'user-editor')

    def output_root() -> Path:
        return module_output_dir(core.settings.output_dir, REPORTING_JOBS_FOLDER)

    def file_links(folder: Path, ready: list[dict[str, Any]], owner: str, settings: dict[str, Any],
                   run_id: int | None = None) -> tuple[dict[str, str], dict[str, str]]:
        """The download link of each file of a run, and the link that opens it online when its report has a preview (both
        ask to sign in, valid the days of Email Delivery); none without the Public address of the server of Application
        Runtime. Each link names the file, its run and the workspace of the run."""
        base = str(core.runtime_configuration().get('public_address') or '').rstrip('/')
        if not base:
            return {}, {}
        seconds = int(settings.get('link_days') or DEFAULT_LINK_DAYS) * 86400
        workspace = core.active_workspace.id if core.active_workspace else ''
        tokens = {item['file_name']: core.sign_link(core.repository, {
            'k': 'report-file', 'p': f"{folder.name}/{item['file_name']}", 'o': owner, 'w': workspace,
            **({'r': int(run_id)} if run_id else {})}, seconds=seconds) for item in ready}
        previewed = previewed_formats(folder) if run_id and workspace else {}
        return ({name: f'{base}/reporting/files/{token}' for name, token in tokens.items()},
                {name: f'{base}/reporting/view/{token}' for name, token in tokens.items() if name in previewed})

    def email_run(task: dict[str, Any], started: datetime, folder: Path, artifacts: list[dict[str, Any]],
                  run_id: int | None = None) -> str:
        """Email the artifacts of a run; returns its status. Through SMTP they are attached while they fit the size limit;
        otherwise, and always through a Power Automate flow, the email gives a download link of each one, which works while
        the run is kept and the link is valid, and the link that opens it online when its report has a preview."""
        settings = core.email_delivery_settings(core.repository, include_password=True)
        ready = [item for item in artifacts if item['status'] == 'ready']
        links, views = file_links(folder, ready, task['created_by'], settings, run_id)
        webhook = settings['transport'] == 'webhook'
        total = sum((folder / item['file_name']).stat().st_size for item in ready)
        attach = not webhook and (total <= int(settings['max_attachments_mb']) * 1024 * 1024 or not links)
        if webhook and not links:
            raise RuntimeError('Set the Public address of the server in Application Runtime: a Power Automate flow sends links '
                               'to the files, not attachments.')
        subject = email_subject(task['name'], started)
        for details, cards in ((True, True), (False, True), (False, False)):
            text, body = email_bodies(task['name'], started, artifacts, core.__app_name__, links=links, attached=attach,
                                      link_days=settings['link_days'], details=details, cards=cards, views=views)
            # (A flow request takes about 28 KB: without the filters of each file when they do not fit, then without the
            # cards.)
            if not webhook or not cards or len(json.dumps(webhook_payload(
                    settings, task['recipients'], subject, body, kind='report'), ensure_ascii=False).encode()) <= WEBHOOK_MAX_BYTES:
                break
        core.send_email(settings, task['recipients'], subject, text, body,
                        [(item['file_name'], folder / item['file_name']) for item in ready] if attach else [],
                        kind='report')
        return f"Sent to {', '.join(task['recipients'])} ({'attached' if attach else 'as links'})"


    def generate_provider(key, provider, config, folder, stamp, user) -> list[dict[str, Any]]:
        try:
            return list(provider['generate'](config, folder, stamp, user))
        except Exception as exc:
            return [failed_artifact(key, provider['label'], exc)]

    def ready_artifact(module, title, path: Path, details: list[str]) -> dict[str, Any]:
        return {'module': module, 'title': title, 'file_name': path.name, 'size': path.stat().st_size,
                'status': 'ready', 'details': [line for line in details if line]}

    def failed_artifact(module, title, error) -> dict[str, Any]:
        return {'module': module, 'title': title, 'file_name': '', 'size': 0, 'status': 'failed', 'error': str(error)}

    def execute_run(database_path: str, run_id: int) -> None:
        task_repository = core.Repository(Path(database_path), global_db_path=core.repository.global_db_path,
                                          workspace_registry_db_path=core.workspace_registry.registry_path)
        run = get_run(task_repository, run_id)
        task = get_task(task_repository, run['task_id']) if run else None
        artifacts: list[dict[str, Any]] = []
        steps: list[tuple[str, Any]] = []
        done = 0
        try:
            # (A run stopped while it waited does not start.)
            if run is None or task is None or not claim_run(task_repository, run_id):
                return
            _RUN_CONTEXT.run = {'repository': task_repository, 'run_id': run_id, 'checked': 0.0}
            if not core.active_workspace or Path(core.active_workspace.database_path).resolve() != Path(database_path).resolve():
                raise RuntimeError('The workspace of the report is no longer the active workspace.')
            # A run started from the page is generated as the user who started it; a scheduled one as the owner of the
            # schedule.
            owner = run['requested_by'] if run['trigger'] == 'manual' and run['requested_by'] else task['created_by']
            definition, user = task['definition'], run_user(owner)
            # Artifacts of modules the user can no longer use are reported, not generated.
            allowed = {module: core.user_has_feature(user, feature) for module, _label, feature in used_modules(definition)}
            for module, label, feature in used_modules(definition):
                if not allowed[module]:
                    steps.append((label, lambda module=module, label=label: [failed_artifact(module, label, f'{owner} no longer has access to {label}.')]))
            definition = {**definition, 'modules': {key: value for key, value in (definition.get('modules') or {}).items() if allowed.get(key)}}
            # Generate the report again without the sections kept by earlier exports (Generate with Reuse unchecked).
            reuse = run['control'].get('reuse', True) is not False
            for key, config in (definition.get('modules') or {}).items():
                provider = ARTIFACT_PROVIDERS.get(key)
                if provider is None:
                    steps.append((key, lambda key=key: [failed_artifact(key, key, 'This module no longer provides Reporting artifacts.')]))
                else:
                    steps.append((provider['label'], lambda provider=provider, config=config, key=key: generate_provider(key, provider, {**config, 'reuse': reuse}, folder, stamp, user)))
            # A run interrupted by a restart goes on in its folder after the last step it finished, unless its job (or what
            # its owner may generate) changed meanwhile; otherwise it starts again.
            signature = hashlib.sha256(json.dumps([definition, [label for label, _step in steps]], sort_keys=True,
                                                  default=str).encode()).hexdigest()
            control, previous = run['control'], Path(run['output_dir']) if run['output_dir'] else None
            if control.get('signature') == signature and control.get('stamp') and previous and previous.is_dir() and run['started_at']:
                started, stamp, folder = datetime.fromisoformat(run['started_at']), str(control['stamp']), previous
                done, artifacts = int(control.get('done') or 0), list(run['artifacts'])
                # (What the interrupted step left half written goes.)
                kept = {item.get('file_name') for item in artifacts}
                for path in folder.iterdir():
                    if path.name not in kept:
                        shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
            else:
                if previous:
                    remove_run_folders([str(previous)])
                started = now_local()
                stamp = started.strftime('%Y%m%d_%H%M%S')
                folder = output_root() / f"{stamp} - {safe_file_name(task['name'])} - run {run_id}"
                folder.mkdir(parents=True, exist_ok=True)
            update_run(task_repository, run_id, started_at=started.isoformat(), output_dir=str(folder), artifacts=artifacts)
            update_run_control(task_repository, run_id, stamp=stamp, signature=signature, done=done)
            for index, (label, step) in enumerate(steps):
                if index < done:
                    continue
                check_run_stopped(at_once=True)
                message = f'Generating {label} ({index + 1}/{len(steps)})'
                update_run(task_repository, run_id, message=message, progress=max(1, round(index * 90 / max(len(steps), 1))))
                # A long step moves the progress within its share (report_step_progress).
                _RUN_CONTEXT.run['step'] = (index * 90 / max(len(steps), 1), 90 / max(len(steps), 1), message)
                artifacts.extend(step())
                done = index + 1
                update_run_control(task_repository, run_id, artifacts=artifacts, done=done)
            check_run_stopped(at_once=True)
            # A file listed as ready must still exist when the run ends; otherwise it failed.
            for item in artifacts:
                if item['status'] == 'ready' and not (folder / item['file_name']).is_file():
                    item.update(status='failed', file_name='', size=0, error='The file was not kept after it was generated.')
            ready = [item for item in artifacts if item['status'] == 'ready']
            email_status, error = '', ''
            if task['send_email'] and ready:
                update_run(task_repository, run_id, message='Sending the email', progress=95)
                try:
                    email_status = email_run(task, started, folder, artifacts, run_id)
                except Exception as exc:
                    email_status, error = 'Not sent', f'Email delivery failed: {exc}'
            elif task['send_email']:
                email_status = 'Not sent: no artifact was generated'
            failed = [item for item in artifacts if item['status'] != 'ready']
            if not ready:
                status = 'failed'
                error = error or '; '.join(f"{item['title']}: {item.get('error')}" for item in failed) or 'No artifact was generated.'
            elif error:
                status = 'failed'
            elif failed:
                status = 'partial'
            else:
                status = 'sent' if task['send_email'] else 'completed'
            message = {'sent': 'Artifacts generated and emailed', 'completed': 'Artifacts generated',
                       'partial': f'{len(failed)} of {len(artifacts)} artifacts failed', 'failed': 'The run failed'}[status]
            update_run(task_repository, run_id, status=status, message=message, progress=100, email_status=email_status,
                       error=error, finished_at=now_local().isoformat(), artifacts=artifacts)
            # The trigger tells App Events whether the scheduler or a user started the run.
            task_repository.try_add_log(task['created_by'], 'reporting_job_run', json.dumps({
                'task_id': task['id'], 'run_id': run_id, 'status': status, 'artifacts': len(ready), 'email': email_status,
                'trigger': run['trigger'],
            }))
        except RunStopped:
            # What it generated before it was stopped is kept; no email is sent.
            stopped_by = ((get_run(task_repository, run_id) or {}).get('control') or {}).get('stopped_by') or 'a user'
            update_run(task_repository, run_id, status='stopped', message=f'Stopped by {stopped_by} after {done} of {len(steps)} steps',
                       finished_at=now_local().isoformat(), artifacts=artifacts)
            task_repository.try_add_log(task['created_by'], 'reporting_job_run', json.dumps({
                'task_id': task['id'], 'run_id': run_id, 'status': 'stopped', 'stopped_by': stopped_by, 'steps_done': done,
                'steps': len(steps), 'artifacts': len([item for item in artifacts if item.get('status') == 'ready']),
                'trigger': run['trigger'],
            }))
        except Exception as exc:
            update_run(task_repository, run_id, status='failed', message='The run failed', progress=100,
                       error=str(exc), finished_at=now_local().isoformat())
        finally:
            _RUN_CONTEXT.run = None
            with active_lock:
                active_runs.discard((str(Path(database_path).resolve()), run_id))

    def run_in_worker(workspace_id: str, database: str, run_id: int) -> None:
        """Run a job of a workspace that is not open in this process, without opening it for users."""
        import os
        import subprocess
        import sys

        try:
            command = [sys.executable, '-m', 'src.report_worker', '--workspace-id', workspace_id, '--run-id', str(run_id),
                       '--parent-pid', str(os.getpid()), '--global-db', str(core.repository.global_db_path),
                       '--workspace-registry-db', str(core.workspace_registry.registry_path)]
            exit_code = subprocess.run(command, cwd=core.PROJECT_ROOT, check=False).returncode
            task_repository = core.Repository(Path(database), global_db_path=core.repository.global_db_path,
                                              workspace_registry_db_path=core.workspace_registry.registry_path)
            run = get_run(task_repository, run_id)
            if run and run['status'] == 'stopping':
                update_run(task_repository, run_id, status='stopped', finished_at=now_local().isoformat(),
                           message=f"Stopped by {run['control'].get('stopped_by') or 'a user'}")
            elif run and run['status'] in {'queued', 'running'}:
                update_run(task_repository, run_id, status='failed', message='The run failed', progress=100,
                           error=f'The Reporting worker stopped unexpectedly (exit code {exit_code}).',
                           finished_at=now_local().isoformat())
        finally:
            with active_lock:
                active_runs.discard((database, run_id))

    def enqueue_run(task_repository, run_id: int, workspace_id: str | None = None) -> None:
        """Generate a queued run: in this process for the active workspace, otherwise in a worker process."""
        database = str(Path(task_repository.db_path).resolve())
        with active_lock:
            active_runs.add((database, run_id))
        active = core.active_workspace
        if workspace_id and not (active and str(Path(active.database_path).resolve()) == database):
            worker_executor.submit(run_in_worker, workspace_id, database, run_id)
        else:
            executor.submit(execute_run, database, run_id)

    def start_run(task_repository, task: dict[str, Any], trigger: str, username: str, workspace_id: str | None = None,
                  control: dict[str, Any] | None = None) -> int:
        run_id = create_run(task_repository, task, trigger, username)
        if control:
            update_run_control(task_repository, run_id, **control)
        enqueue_run(task_repository, run_id, workspace_id)
        return run_id

    def resume_interrupted_runs(task_repository, workspace_id: str) -> None:
        """After a restart, the runs the previous process left go on from the step they were on (those it was stopping
        end as stopped), unless restarts interrupted them too many times already."""
        database = str(Path(task_repository.db_path).resolve())
        with active_lock:
            running = {run_id for run_database, run_id in active_runs if run_database == database}
        for run in interrupted_runs(task_repository, running):
            control, now = run['control'], now_local().isoformat()
            details = {'run_id': run['id'], 'task_id': run['task_id'], 'name': run['task_name'], 'status': run['status'],
                       'steps_done': int(control.get('done') or 0), 'restarts': int(control.get('restarts') or 0)}
            if run['status'] == 'stopping':
                update_run(task_repository, run['id'], status='stopped', finished_at=now,
                           message=f"Stopped by {control.get('stopped_by') or 'a user'}")
                task_repository.try_add_log('system', 'stop_interrupted_reporting_job_run', json.dumps(details, ensure_ascii=False))
            elif (job_gone := get_task(task_repository, run['task_id']) is None) or details['restarts'] >= MAX_RUN_RESUMES:
                error = (INTERRUPTED_RUN_MESSAGE if job_gone else
                         f'The run was interrupted by {details["restarts"] + 1} application restarts, so it is not resumed again.')
                update_run(task_repository, run['id'], status='failed', message='The run failed', progress=100, error=error,
                           finished_at=now)
                task_repository.try_add_log('system', 'fail_interrupted_reporting_job_run', json.dumps(
                    {**details, 'error': error}, ensure_ascii=False))
            else:
                update_run(task_repository, run['id'], status='queued', message='Resuming after an application restart')
                update_run_control(task_repository, run['id'], restarts=details['restarts'] + 1)
                enqueue_run(task_repository, run['id'], workspace_id)
                task_repository.try_add_log('system', 'resume_reporting_job_run', json.dumps(details, ensure_ascii=False))

    def run_due_tasks(now: datetime | None = None) -> list[int]:
        """Start every due job of every workspace, open or not; returns the new run IDs."""
        started = []
        workspaces = list(core.workspace_registry.list())
        if core.active_workspace and all(item.id != core.active_workspace.id for item in workspaces):
            workspaces.append(core.active_workspace)
        for workspace in workspaces:
            if getattr(workspace, 'status', 'ready') not in {'ready', '', None} or not Path(workspace.database_path).is_file():
                continue
            task_repository = core.Repository(workspace.database_path, global_db_path=core.repository.global_db_path,
                                              workspace_registry_db_path=core.workspace_registry.registry_path)
            database = str(Path(task_repository.db_path).resolve())
            if database not in recovered_databases:
                resume_interrupted_runs(task_repository, workspace.id)
                recovered_databases.add(database)
            started += [start_run(task_repository, task, 'schedule', task['created_by'], workspace.id)
                        for task in claim_due_tasks(task_repository, now or now_local())]
        return started

    def scheduler_loop(stop_event: Event) -> None:
        while not stop_event.wait(SCHEDULER_INTERVAL_SECONDS):
            try:
                run_due_tasks()
            except Exception as exc:  # The scheduler keeps running after a failed check.
                core.repository.try_add_log('system', 'reporting_scheduler_error', json.dumps({'error': str(exc)}))

    core.register_report_artifact_provider = register_report_artifact_provider
    core.report_task_scheduler_loop = scheduler_loop
    core.run_due_report_tasks = run_due_tasks
    core.execute_report_run = execute_run
    core.start_report_run = start_run

    # -- options ------------------------------------------------------------
    catalogue_backfills: set[str] = set()
    catalogue_backfills_lock = Lock()


    # -- routes -------------------------------------------------------------
    @app.get('/reporting', response_class=HTMLResponse)
    def reporting_jobs_page(request: Request, user=Depends(reporting_user)):
        reporting_repository(user)
        return core.render_template(request, 'report_jobs.html', {'user': user})

    # -- options of the report editor -----------------------------------------------------------------
    catalogue_backfills: set[str] = set()
    catalogue_backfills_lock = Lock()

    def complete_catalogues_in_background(task_repository, dataset_ids: list[int]) -> bool:
        """Start (once per workspace) rebuilding incomplete CDR catalogues; True while some are pending."""
        missing = task_repository.missing_cdr_catalogue_ids(dataset_ids)
        if not missing:
            return False
        key = str(task_repository.db_path)
        with catalogue_backfills_lock:
            if key in catalogue_backfills:
                return True
            catalogue_backfills.add(key)

        def run() -> None:
            try:
                core.backfill_cdr_catalogues(missing, task_repository)
            except Exception as exc:  # The next editor opening tries again.
                print(f'Unable to complete the CDR catalogues: {exc}', flush=True)
            finally:
                with catalogue_backfills_lock:
                    catalogue_backfills.discard(key)

        Thread(target=run, name='reporting-catalogue-backfill', daemon=True).start()
        return True

    @app.get('/api/reporting/options')
    def reporting_options(user=Depends(reporting_user)):
        """What the report editor lists: the filter values of the CDRs (with their Operator and Vendor Maps labels), the
        campaigns of each NR Mode, the Main Cities, the methodologies, the themes and the CDR Analysis metrics."""
        task_repository = reporting_repository(user)
        datasets = [
            {'id': int(row['id']), 'kind': str(row['dataset_kind'])}
            for row in task_repository.list_datasets()
            if row['status'] == 'ready' and str(row['dataset_kind']) in {'data', 'voice', 'speech'}
        ]
        try:
            profiles = task_repository.get_scoring_profiles()
            methodologies = [{'id': profile['id'], 'name': profile.get('name') or profile['id']} for profile in profiles['profiles']]
        except ValueError:
            methodologies = []
        # Filter values come from the cached catalogues; incomplete ones are rebuilt in the background (it can take
        # minutes for large CDRs) and the editor says so instead of waiting.
        catalogues_pending = complete_catalogues_in_background(task_repository, [item['id'] for item in datasets])
        values = task_repository.cdr_catalogue_values()
        mapper = ValueMapper.from_repository(task_repository)
        return {
            'values': {'Operator': mapper.values('operator', values.get('operators', [])),
                       'Operator_Vendor': mapper.values('operator_vendor', values.get('vendors', [])),
                       'Vendor_Operator': mapper.values('vendor_operator', values.get('vendor_operators', [])),
                       'Vendor': mapper.values('vendor', values.get('vendors_only', [])),
                       'Region': values.get('regions', []), 'Cluster': values.get('clusters', []),
                       'City': values.get('cities', []), 'Campaign': values.get('campaigns', [])},
            'catalogues_pending': catalogues_pending,
            'main_cities': list(task_repository.list_main_cities()),
            'methodologies': methodologies,
            'scoring_themes': themes_payload()['themes'],
            'campaigns': {nr_mode: campaign_values(task_repository, nr_mode) for nr_mode in ('NSA', 'SA', NSA_VS_SA)},
            'campaign_presets': CAMPAIGN_PRESET_LABELS,
            'single_campaign_presets': list(SINGLE_CAMPAIGN_PRESETS),
            'cdr_metrics': {kind: list(dict.fromkeys(
                metric for dataset in datasets if dataset['kind'] == kind
                for metric in core.analysis_metric_columns(task_repository.list_dataset_row_columns(dataset['id']), kind)
            )) for kind in CDR_ANALYSIS_KINDS},
            'cdr_kinds': CDR_ANALYSIS_KINDS,
            'cdr_aggregations': CDR_ANALYSIS_AGGREGATIONS, 'cdr_cdf_groupings': CDR_ANALYSIS_CDF_GROUPINGS,
            'email_configured': bool(core.email_delivery_settings(core.repository).get('configured')),
            'timezone': now_local().strftime('%Z (UTC%z)'),
        }

    @app.get('/api/reporting/state')
    def reporting_jobs_state(user=Depends(reporting_user)):
        """The reports, each with what it includes, its schedule and its last run, and the runs of History."""
        from src.modules.reporting.bundle_report_templates import list_favourites, report_labels, report_stars
        task_repository = reporting_repository(user)
        runs = list_runs(task_repository, limit=200)
        runs_by_id = {run['id']: run for run in runs}
        tasks = report_tasks_by_favourite(task_repository)
        # History links only the files that still exist, and shows how much its artifacts take.
        for run in runs:
            folder = Path(run['output_dir']) if run.get('output_dir') else None
            run['artifacts_size'] = 0
            for item in run['artifacts']:
                if item.get('status') == 'ready':
                    path = folder / item['file_name'] if folder and item.get('file_name') else None
                    try:
                        item['size'] = path.stat().st_size if path is not None and path.is_file() else 0
                    except OSError:
                        item['size'] = 0
                    item['available'] = bool(item['size']) or bool(path is not None and path.is_file())
                    run['artifacts_size'] += item['size']
            run['has_preview'] = bool(folder and (folder / '.report' / 'report.json').is_file())
        report_of_task = {task['id']: favourite_id for favourite_id, task in tasks.items()}
        reports = []
        stars = report_stars(task_repository, user.username)
        for item in list_favourites(task_repository):
            task = tasks.get(str(item['id']))
            last = None
            if task and task['last_run_id']:
                last = runs_by_id.get(task['last_run_id']) or get_run(task_repository, task['last_run_id'])
            formats = ((task or {}).get('definition', {}).get('modules', {}).get('bundle_report_template') or {}).get('formats')
            reports.append({
                'id': item['id'], 'name': item['name'], 'created_by': item['created_by'], 'updated_at': item['updated_at'],
                'labels': report_labels(item['definition']), 'starred': item['id'] in stars,
                'schedule': {
                    'enabled': task['enabled'] if task else True, 'schedule': task['schedule'] if task else {'mode': 'manual', 'time': '08:00'},
                    'recurrence': task['recurrence'] if task else recurrence_label({'mode': 'manual'}),
                    'next_run_at': task['next_run_at'] if task else None,
                    'formats': formats or ['powerpoint', 'word'], 'send_email': bool(task and task['send_email']),
                    'recipients': task['recipients'] if task else [], 'owner': task['created_by'] if task else '',
                },
                'last_run': last,
            })
        for run in runs:
            run['report_id'] = int(report_of_task[run['task_id']]) if run['task_id'] in report_of_task else None
        return {
            'reports': reports, 'runs': runs, 'can_edit': user.role in {'user-editor', 'admin', 'super-admin'},
            'workspace_id': core.active_workspace.id if core.active_workspace else '',
        }

    class RunIdsPayload(BaseModel):
        ids: list[int] = Field(default_factory=list)

    def remove_run_folders(folders: list[str]) -> None:
        root = output_root().resolve()
        for folder in folders:
            path = Path(folder).resolve()
            if root in path.parents:
                shutil.rmtree(path, ignore_errors=True)

    core.remove_report_run_folders = remove_run_folders

    def run_or_404(task_repository, run_id):
        run = get_run(task_repository, run_id)
        if run is None:
            raise HTTPException(404, 'Reporting run not found.')
        return run

    @app.get('/api/reporting/runs/download')
    def reporting_jobs_download_runs(ids: list[int] = Query(default=[]), user=Depends(reporting_user)):
        """The artifacts of the checked runs in one ZIP, each run in its folder (the Download of the checked jobs or runs)."""
        task_repository = reporting_repository(user)
        runs = [run for run in (get_run(task_repository, run_id) for run_id in dict.fromkeys(ids)) if run is not None and any(
            item.get('status') == 'ready' and (Path(run['output_dir']) / str(item.get('file_name') or '')).is_file()
            for item in run['artifacts'])]
        if not runs:
            raise HTTPException(404, 'The selected runs have no artifacts to download.')
        output = zip_runs_artifacts(runs)
        task_repository.try_add_log(user.username, 'download_reporting_job_runs', json.dumps({
            'run_ids': [run['id'] for run in runs], 'names': [run['task_name'] for run in runs],
        }, ensure_ascii=False))

        def chunks():
            with output:
                while chunk := output.read(1024 * 1024):
                    yield chunk
        name = safe_file_name(f"{datetime.now().strftime('%Y%m%d_%H%M%S')} - Reporting - {len(runs)} runs")
        return StreamingResponse(chunks(), media_type='application/zip',
                                 headers={'Content-Disposition': f'attachment; filename="{name}.zip"'})

    @app.get('/api/reporting/runs/{run_id}/download')
    def reporting_jobs_download_run(run_id: int, user=Depends(reporting_user)):
        task_repository = reporting_repository(user)
        run = run_or_404(task_repository, run_id)
        ready = [item for item in run['artifacts'] if item.get('status') == 'ready' and (Path(run['output_dir']) / item['file_name']).is_file()]
        if not ready:
            raise HTTPException(404, 'This run has no artifacts to download.')
        name = safe_file_name(f"{run_stamp(run)} - Reporting - {run['task_name']}")
        task_repository.try_add_log(user.username, 'download_reporting_job_run', json.dumps({
            'run_id': run_id, 'name': run['task_name'], 'artifacts': len(ready),
        }))
        return StreamingResponse(zip_artifacts(run), media_type='application/zip',
                                 headers={'Content-Disposition': f'attachment; filename="{name}.zip"'})

    def link_page(message: str, status_code: int = 200, *, actions: tuple[tuple[str, str], ...] = (), refresh: str = '') -> HTMLResponse:
        """The small page a link of a report email shows instead of its file or report."""
        buttons = ''.join(f'<a href="{html.escape(href, quote=True)}" style="display:inline-block;margin:0 .5rem .5rem 0;padding:.5rem 1rem;'
                          f'border-radius:999px;background:#1f5f3a;color:#fff;font-weight:bold;text-decoration:none">{html.escape(label)}</a>'
                          for label, href in actions)
        meta = f'<meta http-equiv="refresh" content="1;url={html.escape(refresh, quote=True)}">' if refresh else ''
        return HTMLResponse(f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, '
                            f'initial-scale=1">{meta}<title>{html.escape(core.__app_name__)}</title></head><body style="font-family:'
                            f'Arial,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;color:#1f2933"><p>{html.escape(message)}'
                            f'</p><p>{buttons}</p></body></html>', status_code=status_code)

    def email_link(request: Request, token: str):
        """The file, run, workspace and owner of a link of a report email, and the user who opened it: a page to show
        instead when the link is no longer valid, or a redirection to sign in first (then back to the link)."""
        payload = core.read_link(core.repository, token, 'report-file')
        if payload is None:
            return None, None, link_page('This link has expired or is not valid: ask for the report again, or open it from '
                                         'Reporting.', 410, actions=(('Open Reporting', '/reporting'),))
        user = core.optional_user(request)
        if user is None:
            back = f'{request.url.path}?after_sign_in=1' if request.url.path.startswith('/reporting/files/') else request.url.path
            return None, None, RedirectResponse('/login?' + urlencode({'next': back}), status_code=303)
        workspace = str(payload.get('w') or '')
        if workspace and user.role != 'super-admin' and not core.repository.user_has_workspace_access(user.username, workspace):
            core.repository.try_add_log(user.username, 'report_email_link_denied', json.dumps({
                'file': Path(str(payload.get('p') or '')).name, 'workspace_id': workspace, 'reason': 'workspace_access',
            }, ensure_ascii=False))
            return None, None, link_page('You do not have access to the workspace of this report: ask an administrator for it.', 403)
        return payload, user, None

    @app.get('/reporting/files/{token}')
    def reporting_jobs_file_link(token: str, request: Request, after_sign_in: bool = False):
        """A file of a report from the link of its email, while the link is valid and the run is kept: for a user signed in
        with access to the workspace of the report (the link asks to sign in first), recorded in App Events."""
        payload, user, answer = email_link(request, token)
        if answer is not None:
            return answer
        root = output_root().resolve()
        path = (root / str(payload.get('p') or '')).resolve()
        if root not in path.parents or not path.is_file():
            return link_page('This file is no longer kept on the server.', 404, actions=(('Open Reporting', '/reporting'),))
        if after_sign_in:
            # Back from signing in: a page that starts the download (a download alone would leave the sign-in page shown).
            return link_page(f'Downloading {path.name}…', actions=(('Download again', request.url.path), ('Open Reporting', '/reporting')),
                             refresh=request.url.path)
        workspace = str(payload.get('w') or '')
        core.repository.try_add_log(user.username, 'download_reporting_file_link', json.dumps({
            'file': path.name, 'run_folder': path.parent.name, **({'run_id': payload['r']} if payload.get('r') else {}),
            **({'workspace_id': workspace} if workspace else {}), 'report_owner': str(payload.get('o') or ''),
        }, ensure_ascii=False))
        return FileResponse(path, filename=path.name)

    @app.get('/reporting/view/{token}')
    def reporting_jobs_view_link(token: str, request: Request):
        """View Online of a file of a report email: the report of its run in the slide viewer of Reporting, in the format of
        the file, for a user signed in with access to its workspace, which opens when another one is open. Recorded in App
        Events."""
        payload, user, answer = email_link(request, token)
        if answer is not None:
            return answer
        workspace, run_id, file_name = str(payload.get('w') or ''), int(payload.get('r') or 0), Path(str(payload.get('p') or '')).name
        if not workspace or not run_id:
            return link_page('This link does not open a report online.', 404, actions=(('Open Reporting', '/reporting'),))
        if not core.active_workspace or core.active_workspace.id != workspace:
            try:
                opened = core.activate_workspace(workspace)
            except Exception as exc:  # A workspace that is gone or busy: said as it is.
                return link_page(f'The workspace of this report cannot be opened: {exc}', 409)
            core.repository.try_add_log(user.username, 'open_workspace', json.dumps({
                'workspace': opened.id, 'name': opened.name, 'via': 'report email link',
            }, ensure_ascii=False))
        task_repository = reporting_repository(user)
        run = get_run(task_repository, run_id)
        folder = Path(run['output_dir']) if run and run.get('output_dir') else None
        # (The run of the link, not another one that took its number after it was deleted.)
        if folder is not None and folder.name != Path(str(payload.get('p') or '')).parent.name:
            folder = None
        export_format = previewed_formats(folder).get(file_name) if folder else None
        if run is None or folder is None or not export_format:
            return link_page('This report is no longer kept on the server.', 404, actions=(('Open Reporting', '/reporting'),))
        task_repository.try_add_log(user.username, 'view_reporting_file_link', json.dumps({
            'run_id': run_id, 'name': run['task_name'], 'file': file_name, 'format': export_format, 'workspace_id': workspace,
            'report_owner': str(payload.get('o') or ''),
        }, ensure_ascii=False))
        return RedirectResponse('/reporting?' + urlencode({'report_run': run_id, 'format': export_format}), status_code=303)

    @app.get('/api/reporting/recipients')
    def reporting_recipients(user=Depends(editor_user)):
        """The active users of the tool with an email address, to add them to the recipients of a report: their name and
        whether they can open its links (Reporting in their Modules Profile and access to the open workspace)."""
        workspace = core.active_workspace.id if core.active_workspace else ''
        people = []
        for row in core.repository.list_users():
            email = str(row['email'] or '').strip()
            if not row['active'] or not email:
                continue
            account = core.SessionUser(username=row['username'], role=row['role'])
            name = ' '.join(str(part).strip() for part in (row['first_name'], row['last_name']) if str(part or '').strip())
            opens = core.user_has_feature(account, 'reporting') and (
                row['role'] == 'super-admin' or not workspace or core.repository.user_has_workspace_access(row['username'], workspace))
            people.append({'username': row['username'], 'name': name or row['username'], 'email': email, 'can_open': bool(opens)})
        people.sort(key=lambda item: (item['name'].casefold(), item['username'].casefold()))
        return {'users': people, 'workspace': core.active_workspace.name if core.active_workspace else ''}

    @app.get('/api/reporting/runs/{run_id}/artifacts/{index}')
    def reporting_jobs_download_artifact(run_id: int, index: int, user=Depends(reporting_user)):
        task_repository = reporting_repository(user)
        run = run_or_404(task_repository, run_id)
        if not 0 <= index < len(run['artifacts']) or run['artifacts'][index].get('status') != 'ready':
            raise HTTPException(404, 'Artifact not found.')
        path = Path(run['output_dir']) / run['artifacts'][index]['file_name']
        if not path.is_file():
            raise HTTPException(404, 'The artifact file is no longer available.')
        task_repository.try_add_log(user.username, 'download_reporting_job_artifact', json.dumps({
            'run_id': run_id, 'name': run['task_name'], 'file': path.name,
        }))
        return FileResponse(path, filename=path.name)

    def delete_run(task_repository, run, user) -> None:
        with task_repository.connection() as connection:
            connection.execute(f'DELETE FROM {REPORT_TASK_RUNS_TABLE} WHERE id = ?', (run['id'],))
        if run['output_dir']:
            remove_run_folders([run['output_dir']])
        task_repository.try_add_log(user.username, 'delete_reporting_job_run', json.dumps({
            'run_id': run['id'], 'name': run['task_name'], 'status': run['status'],
        }, ensure_ascii=False))

    @app.delete('/api/reporting/runs/{run_id}')
    def reporting_jobs_delete_run(run_id: int, user=Depends(editor_user)):
        task_repository = reporting_repository(user)
        run = run_or_404(task_repository, run_id)
        if run['status'] in RUN_ACTIVE_STATUSES:
            raise HTTPException(409, 'Stop the run or wait for it to finish before deleting it.')
        delete_run(task_repository, run, user)
        return JSONResponse({'deleted': run_id})

    def checked_runs(task_repository, ids: list[int]) -> list[dict[str, Any]]:
        return [run for run in (get_run(task_repository, int(run_id)) for run_id in dict.fromkeys(ids)) if run is not None]

    @app.post('/api/reporting/runs/delete')
    def reporting_jobs_delete_runs(payload: RunIdsPayload, user=Depends(editor_user)):
        """Delete the checked runs that are not waiting or running, with their artifacts."""
        task_repository = reporting_repository(user)
        deleted, skipped = [], []
        for run in checked_runs(task_repository, payload.ids):
            if run['status'] in RUN_ACTIVE_STATUSES:
                skipped.append(run['id'])
                continue
            delete_run(task_repository, run, user)
            deleted.append(run['id'])
        return {'deleted': deleted, 'skipped': skipped}

    @app.post('/api/reporting/runs/stop')
    def reporting_jobs_stop_runs(payload: RunIdsPayload, user=Depends(reporting_user)):
        """Stop the checked runs: a queued one at once, a running one after the step it is on. Editors stop any run;
        the other users the reports they generated themselves."""
        task_repository = reporting_repository(user)
        editor = user.role in {'user-editor', 'admin', 'super-admin'}
        stopped, stopping, skipped = [], [], []
        for run in checked_runs(task_repository, payload.ids):
            if not editor and run['requested_by'] != user.username:
                skipped.append(run['id'])
                continue
            previous = request_stop(task_repository, run['id'], user.username)
            if previous is None:
                skipped.append(run['id'])
                continue
            (stopped if previous == 'queued' else stopping).append(run['id'])
            task_repository.try_add_log(user.username, 'stop_reporting_job_run', json.dumps({
                'run_id': run['id'], 'task_id': run['task_id'], 'name': run['task_name'], 'status': previous,
                'outcome': 'stopped before it started' if previous == 'queued' else 'stops after the step it is on',
                'step': run['message'],
            }, ensure_ascii=False))
        return {'stopped': stopped, 'stopping': stopping, 'skipped': skipped}

    @app.post('/api/reporting/runs/rerun')
    def reporting_jobs_rerun_runs(payload: RunIdsPayload, user=Depends(editor_user)):
        """Run the checked failed or stopped runs again from the beginning, each in its own row, with what its job
        generates now; what they generated before goes."""
        task_repository = reporting_repository(user)
        rerun, skipped = [], []
        for run in checked_runs(task_repository, payload.ids):
            task = get_task(task_repository, run['task_id'])
            if task is None or run['status'] not in RUN_RERUN_STATUSES or not reset_run(task_repository, run, task, user.username):
                skipped.append(run['id'])
                continue
            if run['output_dir']:
                remove_run_folders([run['output_dir']])
            enqueue_run(task_repository, run['id'])
            rerun.append(run['id'])
            task_repository.try_add_log(user.username, 'rerun_reporting_job_run', json.dumps({
                'run_id': run['id'], 'task_id': task['id'], 'name': task['name'], 'previous_status': run['status'],
                'previous_error': run['error'] or run['message'], 'previous_trigger': run['trigger'],
            }, ensure_ascii=False))
        return {'rerun': rerun, 'skipped': skipped}
