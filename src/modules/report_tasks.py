"""Reporting: scheduled report jobs that collect artifacts and email them.

A Reporting Job (``report_tasks``) selects artifacts — CDR Analysis,
Network Insights, Dashboard PPTs and Scoring PPTs — plus optional email
recipients and a schedule. Each execution (``report_task_runs``) writes its
artifacts to its own folder and, when email is enabled, sends them as attachments
with a body that describes every artifact and its filters.

Jobs belong to a workspace and only run while it is the active workspace: the
artifact generators read the active workspace. A run that falls due while
another workspace is active runs as soon as its workspace becomes active again.
"""

import calendar
import html
import json
import math
import re
import shutil
import sqlite3
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Callable

from src.branding import canonical_format
from src.modules.value_maps import ValueMapper
from src.modules.cdr_auto_selection import (
    CAMPAIGN_PRESET_LABELS, LATEST_CAMPAIGN, campaign_presets, campaign_values, cdr_campaigns, complete_campaign_cdrs, describe_cdrs,
    resolve_campaign_filter, resolve_cdrs, sort_campaigns,
)
from src.modules.column_names import compact_campaign_value
from src.modules.nr_mode import NSA_VS_SA, normalize_scoring_nr_mode, nr_mode_label
from src.modules.output_layout import REPORTING_JOBS_FOLDER, module_output_dir
from src.modules.scoring_themes import DEFAULT_THEME, normalize_theme, themes_payload

REPORT_TASKS_TABLE = 'report_tasks'
REPORT_TASK_RUNS_TABLE = 'report_task_runs'
REPORT_FORMATS = ('powerpoint', 'word')
SCHEDULE_MODES = ('manual', 'once', 'daily', 'weekly', 'monthly')
WEEKDAY_NAMES = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
NETWORK_FILTER_FIELDS = ('operators', 'operator_vendors', 'vendor_operators', 'vendors', 'campaigns', 'regions', 'clusters', 'cities')
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
RUN_FINAL_STATUSES = ('sent', 'completed', 'partial', 'failed')
DASHBOARD_JOB_TIMEOUT_SECONDS = 3 * 60 * 60
SCHEDULER_INTERVAL_SECONDS = 30
INTERRUPTED_RUN_MESSAGE = 'The run was interrupted by an application restart.'
MODULE_LABELS = {
    'dataset_analysis': 'CDR Analysis', 'network_insights': 'Network Insights',
    'dashboards': 'Dashboards', 'scoring': 'Scoring',
}
# The feature a user needs to include each kind of artifact in a Reporting Job.
MODULE_FEATURES = {
    'dataset_analysis': 'datasets-analysis', 'network_insights': 'network-insights',
    'dashboards': 'ppt-dashboards', 'scoring': 'scoring',
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
    last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_report_task_runs_task ON {REPORT_TASK_RUNS_TABLE}(task_id, id);
"""


def now_local() -> datetime:
    return datetime.now().astimezone()


# The databases whose jobs already store their one theme and current artifact keys (see _store_legacy_jobs), once per
# process.
_LEGACY_JOBS_STORED: set[str] = set()
_LEGACY_JOBS_LOCK = Lock()


def _store_legacy_jobs(connection: Any) -> None:
    """Jobs saved before every job had one theme store it: the default theme (Ericsson) for those without one, and the
    themes their Network Insights and Scoring artifacts had are dropped (the theme of the job colours them). Jobs saved
    when Bundle Report Templates had a former name store their current artifact key."""
    for job_id, raw in connection.execute(f'SELECT id, definition_json FROM {REPORT_TASKS_TABLE}').fetchall():
        try:
            definition = json.loads(raw or '{}')
        except json.JSONDecodeError:
            continue
        if not isinstance(definition, dict):
            continue
        changed = _current_provider_keys(definition)
        if not str(definition.get('theme') or '').strip():
            definition['theme'] = DEFAULT_THEME
            changed = True
        network = definition.get('network_insights')
        for entry in (network if isinstance(network, list) else [network]):
            if isinstance(entry, dict) and 'theme' in entry:
                entry.pop('theme')
                changed = True
        for entry in definition.get('scoring') or []:
            report = entry.get('report') if isinstance(entry, dict) else None
            if isinstance(report, dict) and 'theme' in report:
                report.pop('theme')
                changed = True
        if changed:
            connection.execute(f'UPDATE {REPORT_TASKS_TABLE} SET definition_json = ? WHERE id = ?', (json.dumps(definition, ensure_ascii=False), job_id))


def ensure_report_task_tables(task_repository: Any) -> None:
    with task_repository.connection() as connection:
        connection.executescript(SCHEMA)
        database = str(getattr(task_repository, 'db_path', ''))
        with _LEGACY_JOBS_LOCK:
            if database not in _LEGACY_JOBS_STORED:
                _store_legacy_jobs(connection)
                _LEGACY_JOBS_STORED.add(database)
        # The order of the jobs table (dragged by the users); jobs saved before it keep their alphabetical order.
        if 'position' not in {row[1] for row in connection.execute(f'PRAGMA table_info({REPORT_TASKS_TABLE})')}:
            try:
                connection.execute(f'ALTER TABLE {REPORT_TASKS_TABLE} ADD COLUMN position INTEGER NOT NULL DEFAULT 0')
            except sqlite3.OperationalError:  # Added meanwhile by another request.
                return
            ids = [row[0] for row in connection.execute(f'SELECT id FROM {REPORT_TASKS_TABLE} ORDER BY name COLLATE NOCASE, id')]
            connection.executemany(f'UPDATE {REPORT_TASKS_TABLE} SET position = ? WHERE id = ?',
                                   [(index, task_id) for index, task_id in enumerate(ids, 1)])


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


CDR_SELECTIONS = ('newest', 'all_complete')


def _cdr_selection(entry: dict[str, Any], legacy: str) -> str:
    """The automatic CDR choice used when no CDR is selected by hand: the newest complete set of Data,
    Voice and Speech CDRs or every complete set, chosen again at each run. `legacy` is the choice of
    jobs saved before it existed."""
    value = entry.get('cdr_selection')
    return value if value in CDR_SELECTIONS else legacy


def _network_entries(value: Any) -> list[dict[str, Any]]:
    """Network Insights entries; jobs saved with a single selection keep it as one entry."""
    if isinstance(value, dict):
        return [value] if value.get('enabled') else []
    return [entry for entry in value or [] if isinstance(entry, dict)]


def _network_entry(entry: dict[str, Any]) -> dict[str, Any]:
    selection = entry.get('selection') if isinstance(entry.get('selection'), dict) else {}
    auto_cdrs = bool(entry.get('auto_cdrs'))
    return {
        'label': str(entry.get('label') or '').strip()[:120],
        'formats': _formats(entry.get('formats')),
        # The CDRs of the NR Mode and Campaigns at each run (auto_cdrs); entries saved before chose them by hand
        # or with an automatic choice, and take the campaigns of that choice (see migrate_auto_cdrs).
        'auto_cdrs': auto_cdrs,
        'cdr_selection': '' if auto_cdrs else _cdr_selection(entry, 'all_complete'),
        'selection': {
            'nr_mode': 'SA' if str(selection.get('nr_mode') or '').upper() == 'SA' else 'NSA',
            'datasets': {} if auto_cdrs else _datasets_by_kind(selection.get('datasets')),
            'technology': selection.get('technology') if selection.get('technology') in {'lte', 'nr', 'lte_nr'} else 'lte',
            'group': _network_groups(selection.get('group')),
            **{field: _strings(selection.get(field)) for field in NETWORK_FILTER_FIELDS},
            **_network_thresholds(selection),
            'grid_metres': float(selection.get('grid_metres', 250) or 250),
        },
    }


def network_entry_name(entry: dict[str, Any]) -> str:
    """Name of a Network Insights entry: its label, or NR Mode and technology."""
    selection = entry.get('selection') or {}
    technology = {'lte': 'LTE', 'nr': 'NR', 'lte_nr': 'LTE+NR'}.get(selection.get('technology'), 'LTE')
    return entry.get('label') or f"{selection.get('nr_mode') or 'NSA'} {technology}"


def _network_thresholds(selection: dict[str, Any]) -> dict[str, float]:
    """LTE and NR thresholds of a Network Insights selection.

    Jobs saved before NR had its own thresholds keep their single pair for
    NR-only analyses.
    """
    def number(key: str, default: float) -> float:
        try:
            value = float(selection.get(key))
        except (TypeError, ValueError):
            return default
        return value if math.isfinite(value) else default

    legacy_nr = selection.get('technology') == 'nr' and 'nr_coverage_threshold' not in selection
    return {
        'coverage_threshold': number('coverage_threshold', -110.0),
        'interference_threshold': number('interference_threshold', 0.0),
        'nr_coverage_threshold': number('coverage_threshold' if legacy_nr else 'nr_coverage_threshold', -115.0),
        'nr_interference_threshold': number('interference_threshold' if legacy_nr else 'nr_interference_threshold', -3.0),
    }


def _datasets_by_kind(value: Any) -> dict[str, list[int]]:
    if not isinstance(value, dict):
        return {}
    return {str(kind): _ids(ids) for kind, ids in value.items() if _ids(ids)}


def _scoring_report(value: Any) -> dict[str, Any]:
    """The scenarios and content of a Scoring artifact's report, which every Scoring artifact needs."""
    from src.modules.scoring_reports import normalize_report_configuration
    if not isinstance(value, dict) or not value.get('scenarios'):
        raise ValueError('Configure the report content of every Scoring artifact.')
    return normalize_report_configuration(value)


def scoring_entry_name(entry: dict[str, Any]) -> str:
    """The artifact name: its label, or the NR Mode and the report scenarios."""
    scenarios = ', '.join(scenario['name'] for scenario in (entry.get('report') or {}).get('scenarios') or [])
    return entry.get('label') or ' '.join(part for part in (nr_mode_label(entry.get('nr_mode', 'NSA')), scenarios) if part)


def _date_text(value: Any) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f'Invalid date: {text}.') from exc


CDR_ANALYSIS_KINDS = {'data': 'CDR Data', 'voice': 'CDR Voice', 'speech': 'CDR Speech'}


def _cdr_analysis_metrics(value: Any) -> dict[str, list[str]]:
    value = value if isinstance(value, dict) else {}
    return {kind: metrics for kind in CDR_ANALYSIS_KINDS if (metrics := _strings(value.get(kind)))}


def _network_groups(value: Any) -> list[str]:
    """Network Insights grouping: Operator is always included unless Vendor groups the samples."""
    groups = _strings(value) or ['operator', 'campaign']
    return groups if 'operator' in groups or 'vendor' in groups else ['operator', *groups]


def _choice(value: Any, choices: dict[str, str], default: str) -> str:
    text = str(value or '').strip()
    return text if text in choices else default


def normalize_definition(raw: Any) -> dict[str, Any]:
    """Validate a Reporting Job artifact selection; raises ValueError when nothing is selected."""
    raw = raw if isinstance(raw, dict) else {}
    dataset_analysis = raw.get('dataset_analysis') if isinstance(raw.get('dataset_analysis'), dict) else {}
    analysis_auto_cdrs = bool(dataset_analysis.get('auto_cdrs'))
    definition: dict[str, Any] = {
        'dataset_analysis': {
            'enabled': bool(dataset_analysis.get('enabled')),
            'formats': _formats(dataset_analysis.get('formats')),
            # The CDRs of the NR Mode and Campaigns at each run (auto_cdrs), as the other artifacts; jobs saved
            # before chose CDRs by hand or with an automatic choice in each NR Mode (see migrate_auto_cdrs).
            'auto_cdrs': analysis_auto_cdrs,
            'nr_mode': 'SA' if str(dataset_analysis.get('nr_mode') or '').upper() == 'SA' else 'NSA',
            'campaigns': _strings(dataset_analysis.get('campaigns')),
            'dataset_ids': [] if analysis_auto_cdrs else _ids(dataset_analysis.get('dataset_ids')),
            'cdr_selection': '' if analysis_auto_cdrs else _cdr_selection(dataset_analysis, 'all_complete'),
            # The same filters as Network Insights; empty filters include every value.
            'filters': {field: values for field in NETWORK_FILTER_FIELDS
                        if (values := _strings((dataset_analysis.get('filters') or {}).get(field)))},
            # The metrics of each CDR type; an empty or missing list includes every metric.
            'metrics': _cdr_analysis_metrics(dataset_analysis.get('metrics')),
            'aggregation': _choice(dataset_analysis.get('aggregation'), CDR_ANALYSIS_AGGREGATIONS, 'all'),
            'cdf_grouping': _choice(dataset_analysis.get('cdf_grouping'), CDR_ANALYSIS_CDF_GROUPINGS, 'operator'),
        },
        # One Network Insights per entry, each with its own selection.
        'network_insights': [_network_entry(entry) for entry in _network_entries(raw.get('network_insights'))],
        'dashboards': [],
        'scoring': [],
        # Artifacts of modules registered in ARTIFACT_PROVIDERS.
        'modules': {},
        # The one colour theme of the job, read by every artifact that supports themes (CDR Analysis, Network Insights,
        # Scoring & GAP Analysis, PPT Dashboards and Bundle Report Templates); jobs without one take the default theme.
        'theme': normalize_theme(str(raw.get('theme') or '').strip() or DEFAULT_THEME),
    }
    for key, config in (raw.get('modules') or {}).items() if isinstance(raw.get('modules'), dict) else ():
        key = LEGACY_PROVIDER_KEYS.get(key, key)
        provider = ARTIFACT_PROVIDERS.get(key)
        if provider and isinstance(config, dict) and config.get('enabled'):
            formats = [value for value in _strings(config.get('formats')) if value in provider['formats']] or [provider['formats'][0]]
            if not any(value in {'powerpoint', 'word'} for value in formats) and any(value in {'powerpoint', 'word'} for value in provider['formats']):
                # Excel holds the details; a document (PowerPoint or Word) is always generated with it.
                formats.insert(0, next(value for value in provider['formats'] if value in {'powerpoint', 'word'}))
            definition['modules'][key] = {'enabled': True, 'formats': formats,
                                          'options': config.get('options') if isinstance(config.get('options'), dict) else {}}
    # Dashboards and Scoring entries carry every option of their own module;
    # each run generates a new PPT with them.
    for entry in raw.get('dashboards') or []:
        if not isinstance(entry, dict) or not str(entry.get('dashboard_id') or '').strip():
            continue
        auto_cdrs = bool(entry.get('auto_cdrs'))
        definition['dashboards'].append({
            'dashboard_id': str(entry['dashboard_id']).strip(), 'label': str(entry.get('label') or '').strip()[:120],
            'scope': entry.get('scope') if entry.get('scope') in {'single', 'multivendor'} else 'single',
            'vendor_comparison': entry.get('vendor_comparison') if entry.get('vendor_comparison') in {'operator_vendor', 'vendor_only'} else 'operator_vendor',
            # The CDRs of the Dashboard's NR Mode and of the Campaign filter at each run (auto_cdrs); entries saved
            # before chose them by hand or with an automatic choice (see migrate_auto_cdrs).
            'auto_cdrs': auto_cdrs,
            'datasets': {} if auto_cdrs else _datasets_by_kind(entry.get('datasets')),
            'cdr_selection': '' if auto_cdrs else (entry['cdr_selection'] if entry.get('cdr_selection') in CDR_SELECTIONS
                                                   else 'all_complete' if entry.get('all_datasets') else ''),
            'date_from': _date_text(entry.get('date_from')), 'date_to': _date_text(entry.get('date_to')),
            'filters': {str(field): _strings(values) for field, values in (entry.get('filters') or {}).items()
                        if str(field).strip() and _strings(values)} if isinstance(entry.get('filters'), dict) else {},
        })
    for entry in raw.get('scoring') or []:
        if not isinstance(entry, dict):
            continue
        # NSA vs SA scores the NSA and SA CDRs of the campaigns side by side.
        nr_mode = normalize_scoring_nr_mode(entry.get('nr_mode')) or 'NSA'
        auto_cdrs = bool(entry.get('auto_cdrs'))
        definition['scoring'].append({
            'label': str(entry.get('label') or '').strip()[:120],
            'nr_mode': nr_mode,
            # The campaigns of the calculation (Latest campaign, Latest 2 campaigns or chosen ones; none is every
            # campaign with Data, Voice and Speech CDRs), whose CDRs are chosen at each run (auto_cdrs). Entries
            # saved before chose CDRs by hand or with an automatic choice (see migrate_auto_cdrs).
            'auto_cdrs': auto_cdrs,
            'campaigns': _strings(entry.get('campaigns')),
            'dataset_ids': [] if auto_cdrs else _ids(entry.get('dataset_ids')),
            'cdr_selection': '' if auto_cdrs else _cdr_selection(entry, 'newest'),
            'scoring_profile_id': str(entry.get('scoring_profile_id') or '').strip(),
            'baseline_operator': str(entry.get('baseline_operator') or 'EE').strip() or 'EE',
            # PowerPoint and/or Word; jobs saved before Word was offered keep PowerPoint.
            'formats': [value for value in _formats(entry.get('formats')) if value in {'powerpoint', 'word'}] or ['powerpoint'],
            # Scenarios (filters and aggregation) and content of the report.
            # The theme is that of the job (see execute_run).
            'report': {key: value for key, value in _scoring_report(entry.get('report')).items() if key != 'theme'},
        })
    if not (definition['dataset_analysis']['enabled'] or definition['network_insights']
            or definition['dashboards'] or definition['scoring'] or definition['modules']):
        raise ValueError('Select at least one artifact for the Reporting Job.')
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
    if (definition.get('dataset_analysis') or {}).get('enabled'):
        used.append(('dataset_analysis', MODULE_LABELS['dataset_analysis'], MODULE_FEATURES['dataset_analysis']))
    for module in ('network_insights', 'dashboards', 'scoring'):
        if definition.get(module):
            used.append((module, MODULE_LABELS[module], MODULE_FEATURES[module]))
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


def _favourite_items(config: dict[str, Any], favourite_names: dict[str, str] | None) -> list[str]:
    """The favourite Bundle Report Templates a Bundle Report Template artifact generates (every one when it chooses none). One that
    no longer exists is named as the job keeps it (by its name, or its ID for those deleted before)."""
    chosen = [str(value) for value in ((config.get('options') or {}).get('filters') or {}).get('favourites') or []]
    return [(favourite_names or {}).get(value) or (f'Favourite {value}' if value.isdigit() else value) for value in chosen] or ['Every favourite']


def artifact_groups(definition: dict[str, Any], dashboard_names: dict[str, str] | None = None,
                    favourite_names: dict[str, str] | None = None,
                    favourite_contents: dict[str, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    """The artifacts of a job by module: [{'module', 'items'}], each item an entry name with its formats.

    The jobs table lists a module once and, when it has several entries, its entries indented below it. The Complete
    Report also has 'contents', one per item: the sections of that favourite with their sub-modules, and 'missing',
    whether that favourite no longer exists (known when ``favourite_names`` is given).
    """
    def formats(values: list[str] | None, default: str = 'powerpoint') -> str:
        return f"({'/'.join(FORMAT_LABELS.get(value, value) for value in values or [default])})"

    groups: list[dict[str, Any]] = []
    section = definition.get('dataset_analysis') or {}
    if section.get('enabled'):
        groups.append({'module': 'CDR Analysis', 'items': [formats(section.get('formats'))]})
    network = [f"{network_entry_name(entry)} {formats(entry.get('formats'))}" for entry in definition.get('network_insights') or []]
    if network:
        groups.append({'module': 'Network Insights', 'items': network})
    dashboards = [f"{entry.get('label') or (dashboard_names or {}).get(entry.get('dashboard_id', ''), entry.get('dashboard_id', ''))} (PPT)"
                  for entry in definition.get('dashboards') or []]
    if dashboards:
        groups.append({'module': 'PPT Dashboards', 'items': dashboards})
    scoring = [f"{scoring_entry_name(entry)} {formats(entry.get('formats'))}" for entry in definition.get('scoring') or []]
    if scoring:
        groups.append({'module': 'Scoring & GAP Analysis', 'items': scoring})
    for key, config in (definition.get('modules') or {}).items():
        provider = ARTIFACT_PROVIDERS.get(key)
        if key == 'bundle_report_template':
            chosen = _chosen_favourites(definition)
            items = [f'{name} {formats(config.get("formats"))}' for name in _favourite_items(config, favourite_names)]
            groups.append({'module': provider['label'] if provider else key, 'items': items,
                           'contents': [(favourite_contents or {}).get(value, []) for value in chosen] or [[]],
                           'missing': [favourite_names is not None and value not in favourite_names for value in chosen] or [False]})
            continue
        groups.append({'module': provider['label'] if provider else key, 'items': [formats(config.get('formats'))]})
    return groups


def based_on_favourite(definition: dict[str, Any]) -> bool:
    """Whether a job only generates one favourite Bundle Report Template (made from a favourite in the Job Editor)."""
    report = (definition.get('modules') or {}).get('bundle_report_template') or {}
    others = (bool((definition.get('dataset_analysis') or {}).get('enabled')) or any(definition.get(key) for key in ('network_insights', 'dashboards', 'scoring'))
              or any(key != 'bundle_report_template' and (module or {}).get('enabled') for key, module in (definition.get('modules') or {}).items()))
    return bool(report.get('enabled')) and len(_chosen_favourites(definition)) == 1 and not others


def artifact_labels(definition: dict[str, Any], dashboard_names: dict[str, str] | None = None,
                    favourite_names: dict[str, str] | None = None) -> list[str]:
    labels = []
    section = definition.get('dataset_analysis') or {}
    if section.get('enabled'):
        labels.append(f"{MODULE_LABELS['dataset_analysis']} ({'/'.join(FORMAT_LABELS[value] for value in section.get('formats') or [])})")
    for entry in definition.get('network_insights') or []:
        labels.append(f"{MODULE_LABELS['network_insights']} · {network_entry_name(entry)} ({'/'.join(FORMAT_LABELS[value] for value in entry.get('formats') or [])})")
    dashboards = definition.get('dashboards') or []
    if dashboards:
        names = ', '.join(entry.get('label') or (dashboard_names or {}).get(entry.get('dashboard_id', ''), entry.get('dashboard_id', '')) for entry in dashboards)
        labels.append(f'Dashboards: {len(dashboards)} PPT ({names})')
    scoring = definition.get('scoring') or []
    if scoring:
        for entry in scoring:
            name = scoring_entry_name(entry)
            formats = '/'.join(FORMAT_LABELS[value] for value in entry.get('formats') or ['powerpoint'])
            labels.append(f"{MODULE_LABELS['scoring']} · {name} ({formats})")
    for key, config in (definition.get('modules') or {}).items():
        provider = ARTIFACT_PROVIDERS.get(key)
        named = f" · {', '.join(_favourite_items(config, favourite_names))}" if key == 'bundle_report_template' else ''
        labels.append(f"{provider['label'] if provider else key}{named} ({'/'.join(FORMAT_LABELS.get(value, value) for value in config.get('formats') or [])})")
    return labels


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
        'artifacts': artifact_labels(definition),
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
        'email_status': str(row['email_status'] or ''), 'artifacts': _loads(row['artifacts_json'], []),
        'output_dir': str(row['output_dir'] or ''), 'error': str(row['last_error'] or ''),
    }


def list_tasks(task_repository: Any) -> list[dict[str, Any]]:
    ensure_report_task_tables(task_repository)
    with task_repository.connection() as connection:
        rows = connection.execute(f'SELECT * FROM {REPORT_TASKS_TABLE} ORDER BY position, name COLLATE NOCASE, id').fetchall()
    return [task_from_row(row) for row in rows]


def reorder_tasks(task_repository: Any, task_ids: list[int]) -> list[dict[str, Any]]:
    """Put the jobs in the order of ``task_ids``; the jobs it does not name follow in their current order."""
    ensure_report_task_tables(task_repository)
    with task_repository.connection() as connection:
        current = [int(row[0]) for row in connection.execute(f'SELECT id FROM {REPORT_TASKS_TABLE} ORDER BY position, name COLLATE NOCASE, id')]
        chosen = [task_id for task_id in dict.fromkeys(int(value) for value in task_ids) if task_id in current]
        order = chosen + [task_id for task_id in current if task_id not in chosen]
        connection.executemany(f'UPDATE {REPORT_TASKS_TABLE} SET position = ? WHERE id = ?',
                               [(index, task_id) for index, task_id in enumerate(order, 1)])
    return list_tasks(task_repository)


def favourite_jobs(task_repository: Any, favourite_id: int) -> dict[str, list[str]]:
    """The names of the jobs based on a favourite Bundle Report Template and of the other jobs that generate it."""
    value, jobs = str(favourite_id), {'based_on': [], 'others': []}
    for task in list_tasks(task_repository):
        if value in _chosen_favourites(task['definition']):
            jobs['based_on' if based_on_favourite(task['definition']) else 'others'].append(task['name'])
    return jobs


def rename_favourite_jobs(task_repository: Any, favourite_id: int, old_name: str, name: str) -> list[dict[str, Any]]:
    """A renamed favourite Bundle Report Template renames the jobs based on it that have its former name (a job from a
    favourite takes its name); returns them: [{'id', 'name', 'old_name'}]."""
    value, renamed = str(favourite_id), []
    if old_name == name:
        return renamed
    now = now_local().isoformat()
    for task in list_tasks(task_repository):
        if (task['name'].casefold() == old_name.casefold() and based_on_favourite(task['definition'])
                and _chosen_favourites(task['definition']) == [value]):
            with task_repository.connection() as connection:
                connection.execute(f'UPDATE {REPORT_TASKS_TABLE} SET name = ?, updated_at = ? WHERE id = ?', (name[:160], now, task['id']))
            renamed.append({'id': task['id'], 'name': name[:160], 'old_name': task['name']})
    return renamed


def forget_favourite(task_repository: Any, favourite_id: int, name: str) -> list[dict[str, Any]]:
    """A deleted favourite Bundle Report Template in the jobs that generate it: they name it from now on (the jobs table says
    it no longer exists, and an empty list would generate every favourite), and those based on it are disabled.
    Returns those jobs: [{'id', 'name', 'disabled'}]."""
    value = str(favourite_id)
    # A name of digits would read as the ID of another favourite: the ID stays.
    kept = value if str(name).isdigit() else str(name)
    changed = []
    now = now_local().isoformat()
    for task in list_tasks(task_repository):
        if value not in _chosen_favourites(task['definition']):
            continue
        definition = json.loads(json.dumps(task['definition']))
        filters = definition['modules']['bundle_report_template'].setdefault('options', {}).setdefault('filters', {})
        filters['favourites'] = list(dict.fromkeys(kept if item == value else item for item in _chosen_favourites(definition)))
        disabled = based_on_favourite(definition) and task['enabled']
        with task_repository.connection() as connection:
            connection.execute(
                f'UPDATE {REPORT_TASKS_TABLE} SET definition_json = ?, enabled = ?, next_run_at = ?, updated_at = ? WHERE id = ?',
                (json.dumps(definition, ensure_ascii=False), 0 if disabled else int(task['enabled']),
                 None if disabled else task['next_run_at'], now, task['id']))
        changed.append({'id': task['id'], 'name': task['name'], 'disabled': disabled})
    return changed


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
        raise ValueError('Enter a name for the Reporting Job.')
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
            raise ValueError('Reporting Job not found.')
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
            raise ValueError('Reporting Job not found.')
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
    columns = {'artifacts': 'artifacts_json', 'recipients': 'recipients_json', 'error': 'last_error'}
    assignments, values = [], []
    for key, value in changes.items():
        column = columns.get(key, key)
        if column in {'artifacts_json', 'recipients_json'} and not isinstance(value, str):
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


def fail_interrupted_runs(task_repository: Any, active_run_ids: set[int]) -> None:
    ensure_report_task_tables(task_repository)
    now = now_local().isoformat()
    with task_repository.connection() as connection:
        for row in connection.execute(
            f"SELECT id FROM {REPORT_TASK_RUNS_TABLE} WHERE status IN ('queued', 'running')").fetchall():
            if int(row['id']) not in active_run_ids:
                connection.execute(
                    f"UPDATE {REPORT_TASK_RUNS_TABLE} SET status = 'failed', message = ?, last_error = ?, finished_at = ? WHERE id = ?",
                    (INTERRUPTED_RUN_MESSAGE, INTERRUPTED_RUN_MESSAGE, now, int(row['id'])),
                )


# ---------------------------------------------------------------------------
# Transfer (export/import, workspace transfers, backup/restore)
# ---------------------------------------------------------------------------
def _definition_dataset_ids(definition: dict[str, Any]) -> set[int]:
    ids = set(definition.get('dataset_analysis', {}).get('dataset_ids') or [])
    for entry in definition.get('network_insights') or []:
        ids.update(value for values in ((entry.get('selection') or {}).get('datasets') or {}).values() for value in values)
    for entry in definition.get('scoring') or []:
        ids.update(entry.get('dataset_ids') or [])
    return {int(value) for value in ids}


def _remap_dataset_ids(definition: dict[str, Any], mapping: dict[int, int]) -> dict[str, Any]:
    """Point dataset references at the destination workspace; unknown datasets are dropped."""
    remap = lambda values: [mapping[int(value)] for value in values or [] if int(value) in mapping]
    definition = json.loads(json.dumps(definition))
    if definition.get('dataset_analysis', {}).get('dataset_ids'):
        definition['dataset_analysis']['dataset_ids'] = remap(definition['dataset_analysis']['dataset_ids'])
    definition['network_insights'] = _network_entries(definition.get('network_insights'))
    for entry in definition['network_insights']:
        selection = entry.get('selection') or {}
        if selection.get('datasets'):
            selection['datasets'] = {kind: remap(values) for kind, values in selection['datasets'].items() if remap(values)}
    for entry in definition.get('scoring') or []:
        if entry.get('dataset_ids'):
            entry['dataset_ids'] = remap(entry['dataset_ids'])
    return definition


def export_tasks_document(task_repository: Any) -> bytes:
    """Portable Reporting Jobs; dataset references also carry their file names. The favourite Bundle Report Templates travel
    as an element of their own (Bundle Report Template Favourites)."""
    tasks = list_tasks(task_repository)
    names = {int(row['id']): str(row['file_name']) for row in task_repository.list_datasets()}
    used = set().union(*(_definition_dataset_ids(task['definition']) for task in tasks)) if tasks else set()
    # The favourite Bundle Report Templates a job generates are named, so the workspace that receives it finds its own.
    from src.modules.bundle_report_templates import list_favourites
    favourite_names = {str(item['id']): item['name'] for item in list_favourites(task_repository)}
    chosen = {value for task in tasks for value in _chosen_favourites(task['definition'])}
    document = {
        'format': 'drivetest-analyzer-reporting-jobs', 'version': 1,
        'dataset_names': {str(dataset_id): names[dataset_id] for dataset_id in sorted(used) if dataset_id in names},
        'favourite_names': {value: favourite_names[value] for value in sorted(chosen) if value in favourite_names},
        # In the order of the jobs table, which ``position`` keeps.
        'reporting_jobs': [{key: task[key] for key in ('name', 'definition', 'send_email', 'recipients', 'schedule', 'enabled', 'created_by', 'position')}
                           for task in tasks],
    }
    return json.dumps(document, ensure_ascii=False, indent=2).encode('utf-8')


def _remap_favourites(definition: dict[str, Any], source_names: dict[str, str], destination: dict[str, str]) -> dict[str, Any]:
    """A job of another workspace with the IDs of the favourite Bundle Report Templates of the same name here. A favourite not
    found here is kept by its name (an empty list would generate every favourite; the run reports that it has none to
    generate) and documents that do not name them keep their IDs."""
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


def import_tasks_document(
    task_repository: Any, content: bytes | str, username: str, *, parse_recipients, invalid_recipients,
    user_exists: Callable[[str], bool] = lambda _name: False,
) -> int:
    """Add or replace (by name) the Reporting Jobs of an exported document.

    Jobs run with the feature access of their owner, so each job keeps the owner
    it had on the source server when that user exists here; otherwise it belongs
    to ``username``, the user who imports it.
    """
    document = json.loads(content)
    if not isinstance(document, dict) or canonical_format(document.get('format')) != 'drivetest-analyzer-reporting-jobs':
        raise ValueError('The file is not a DriveTest Analyzer Reporting Jobs export.')
    # Datasets are matched by file name, since IDs differ between workspaces.
    source_names = {int(key): str(value) for key, value in (document.get('dataset_names') or {}).items() if str(key).isdigit()}
    destination = {}
    for row in task_repository.list_datasets():
        destination.setdefault(str(row['file_name']).casefold(), int(row['id']))
    mapping = {source_id: destination[name.casefold()] for source_id, name in source_names.items() if name.casefold() in destination}
    existing = {task['name'].casefold(): task['id'] for task in list_tasks(task_repository)}
    # Favourite Bundle Report Templates are matched by name too (they are imported before the jobs, as their own element).
    from src.modules.bundle_report_templates import list_favourites
    favourite_names = {str(key): str(value) for key, value in (document.get('favourite_names') or {}).items()}
    favourites_here = {item['name'].casefold(): str(item['id']) for item in list_favourites(task_repository)}
    imported, ordered = 0, []
    for index, item in enumerate(document.get('reporting_jobs') or []):
        if not isinstance(item, dict):
            continue
        schedule = dict(item.get('schedule') or {})
        if schedule.get('mode') == 'once' and next_run_after(normalize_schedule(schedule), now_local()) is None:
            schedule['mode'] = 'manual'  # A past single execution cannot be scheduled again.
        definition = json.loads(json.dumps(item.get('definition') or {}))
        _current_provider_keys(definition)  # Jobs exported when Bundle Report Templates had a former name.
        definition = _remap_favourites(_remap_dataset_ids(definition, mapping), favourite_names, favourites_here)
        source_owner = str(item.get('created_by') or '').strip()
        owner = source_owner if source_owner and user_exists(source_owner) else username
        task = save_task(task_repository, existing.get(str(item.get('name') or '').strip().casefold()),
                         {**item, 'definition': definition, 'schedule': schedule}, owner,
                         parse_recipients=parse_recipients, invalid_recipients=invalid_recipients, reassign_owner=True)
        if isinstance(item.get('position'), int):
            ordered.append((item['position'], index, task['id']))
        imported += 1
    if ordered:
        # The jobs keep the order they had in their workspace, before the jobs only this one has (documents made before
        # the order leave new jobs at the end).
        reorder_tasks(task_repository, [task_id for _position, _index, task_id in sorted(ordered)])
    if document.get('complete_reports'):
        # Documents that carried the favourite Bundle Report Templates with the Reporting Jobs: their Dashboards are found here
        # by their name.
        from src.modules.bundle_report_templates import import_entries, workspace_dashboards
        import_entries(task_repository, document['complete_reports'], username, workspace_dashboards(task_repository))
    return imported


# ---------------------------------------------------------------------------
# Email body
# ---------------------------------------------------------------------------
def email_subject(task_name: str, started: datetime) -> str:
    return f'{task_name} · {started.strftime("%Y-%m-%d %H:%M")}'


def email_bodies(task_name: str, started: datetime, artifacts: list[dict[str, Any]], app_name: str) -> tuple[str, str]:
    """Plain-text and HTML bodies listing each artifact, its content and its filters."""
    attached = [item for item in artifacts if item.get('status') == 'ready']
    failed = [item for item in artifacts if item.get('status') != 'ready']
    text = [f'{task_name}', f'Generated by {app_name} on {started.strftime("%Y-%m-%d %H:%M %Z").strip()}.', '',
            f'Attached artifacts ({len(attached)}):']
    parts = [f'<p><strong>{html.escape(task_name)}</strong><br>Generated by {html.escape(app_name)} on '
             f'{html.escape(started.strftime("%Y-%m-%d %H:%M %Z").strip())}.</p>',
             f'<p><strong>Attached artifacts ({len(attached)})</strong></p><ol>']
    for item in attached:
        text.append(f"- {item['file_name']} — {item['title']}")
        text.extend(f'    {line}' for line in item.get('details') or [])
        details = ''.join(f'<li>{html.escape(line)}</li>' for line in item.get('details') or [])
        parts.append(f"<li><strong>{html.escape(item['title'])}</strong> · <code>{html.escape(item['file_name'])}</code>"
                     f"{f'<ul>{details}</ul>' if details else ''}</li>")
    parts.append('</ol>')
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
    Dashboard or Scoring PPT does not repeat them.
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


# ---------------------------------------------------------------------------
# Execution and routes
# ---------------------------------------------------------------------------
def install_report_task_routes(core: Any) -> None:
    from fastapi import Depends, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
    from pydantic import BaseModel, Field

    app = core.app
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='reporting-jobs')
    # Runs of workspaces other than the active one each use their own worker process.
    worker_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='reporting-workers')
    # (workspace database, run ID): run IDs are only unique within a workspace.
    active_runs: set[tuple[str, int]] = set()
    active_lock = Lock()
    recovered_databases: set[str] = set()

    class ReportTaskPayload(BaseModel):
        name: str = ''
        definition: dict[str, Any] = Field(default_factory=dict)
        send_email: bool = False
        recipients: list[str] | str = Field(default_factory=list)
        schedule: dict[str, Any] = Field(default_factory=dict)
        enabled: bool = True

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
            raise HTTPException(403, 'Editor access is required to change Reporting Jobs.')
        return user

    def run_user(username: str):
        record = core.repository.get_user(username)
        return core.SessionUser(username=username, role=record.role if record else 'user-editor')

    def output_root() -> Path:
        return module_output_dir(core.settings.output_dir, REPORTING_JOBS_FOLDER)

    # -- artifact generators ------------------------------------------------
    def dataset_names(task_repository) -> dict[int, str]:
        return {int(row['id']): str(row['file_name']) for row in task_repository.list_datasets()}

    def generate_dataset_analysis(section, folder, stamp, username, names, task_repository) -> list[dict[str, Any]]:
        artifacts = []
        try:
            if section.get('auto_cdrs'):
                # The CDRs of the NR Mode and Campaigns now (Latest campaign and Latest 2 campaigns, the newest ones).
                nr_mode = section.get('nr_mode') or 'NSA'
                dataset_ids = [dataset_id for ids in resolve_cdrs(task_repository, nr_mode, section.get('campaigns') or []).values()
                               for dataset_id in ids]
                if not dataset_ids:
                    raise RuntimeError(f'There is no ready {nr_mode} CDR of the chosen campaigns in the combined CDR tables.')
            else:
                dataset_ids = section['dataset_ids'] or automatic_cdrs_every_mode(task_repository, section.get('cdr_selection') or 'all_complete')
        except (RuntimeError, ValueError) as exc:
            return [failed_artifact('dataset_analysis', 'CDR Analysis', exc)]
        for export_kind in section['formats']:
            suffix = 'docx' if export_kind == 'word' else 'pptx'
            title = f"CDR Analysis ({FORMAT_LABELS[export_kind]})"
            destination = artifact_path(folder, stamp, 'CDR Analysis', '', f'.{suffix}')
            try:
                filters = {CDR_ANALYSIS_FILTER_DIMENSIONS[field]: values for field, values in (section.get('filters') or {}).items()
                           if field in CDR_ANALYSIS_FILTER_DIMENSIONS}
                _path, reports, errors = core.write_dataset_summary(
                    dataset_ids, export_kind, destination, username, filters=filters,
                    metrics=section.get('metrics') or None, aggregation=section.get('aggregation') or 'all',
                    cdf_grouping=section.get('cdf_grouping') or 'operator', theme=section.get('theme') or None,
                )
                filter_text = '; '.join(f"{CDR_ANALYSIS_AGGREGATIONS.get(dimension, dimension.title())}: {', '.join(values)}"
                                        for dimension, values in filters.items()) or 'none'
                details = [f"Datasets ({len(reports)}): {', '.join(report['dataset_name'] for report in reports)}",
                           *[f"Metrics ({label}): {', '.join(section['metrics'][kind]) if (section.get('metrics') or {}).get(kind) else 'every metric'}"
                             for kind, label in CDR_ANALYSIS_KINDS.items()],
                           f"Filters: {filter_text}",
                           f"Global comparison: {CDR_ANALYSIS_AGGREGATIONS[section.get('aggregation') or 'all']} · "
                           f"Global CDF comparison: {CDR_ANALYSIS_CDF_GROUPINGS[section.get('cdf_grouping') or 'operator']}",
                           *[f'Skipped: {error}' for error in errors]]
                artifacts.append(ready_artifact('dataset_analysis', title, destination, details))
            except Exception as exc:
                artifacts.append(failed_artifact('dataset_analysis', title, exc))
        return artifacts

    def generate_network_insights(section, folder, stamp, index=1, task_repository=None) -> list[dict[str, Any]]:
        from src.modules.network_insights_export import summary_selection_lines

        artifacts = []
        name = network_entry_name(section)
        selection = section['selection']
        if section.get('auto_cdrs') and task_repository is not None:
            # Latest campaign and Latest 2 campaigns are the newest campaigns now; the CDRs follow them.
            campaigns = selection.get('campaigns') or []
            if campaign_presets(campaigns):
                resolved = resolve_campaign_filter(task_repository, selection['nr_mode'], campaigns)
                campaigns = sort_campaigns({compact_campaign_value(value) or value for value in resolved})
            selection = {**selection, 'campaigns': campaigns, 'datasets': {}}
        elif not any(selection.get('datasets', {}).values()) and task_repository is not None:
            try:
                selection = {**selection, 'datasets': cdrs_by_kind(task_repository, automatic_cdrs(
                    task_repository, selection['nr_mode'], section.get('cdr_selection') or 'all_complete'))}
            except (RuntimeError, ValueError) as exc:
                return [failed_artifact('network_insights', f'Network Insights · {name}', exc)]
        for export_kind in section['formats']:
            suffix = 'docx' if export_kind == 'word' else 'pptx'
            title = f"Network Insights · {name} ({FORMAT_LABELS[export_kind]})"
            destination = artifact_path(folder, stamp, 'Network Insights', name, f'.{suffix}')
            try:
                description = core.write_network_insights_summary(selection, export_kind, destination, theme=section.get('theme'))
                artifacts.append(ready_artifact('network_insights', title, destination, summary_selection_lines(description)))
            except Exception as exc:
                artifacts.append(failed_artifact('network_insights', title, getattr(exc, 'detail', exc)))
        return artifacts

    def wait_for_dashboard_job(task_repository, job_id, run_id) -> Any:
        tools = core.dashboard_reporting
        deadline = time.monotonic() + DASHBOARD_JOB_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            row = tools.job(task_repository, job_id)
            if row is None:
                raise RuntimeError('The Dashboard PPT job was deleted.')
            if str(row['status']) == 'ready':
                return row
            if str(row['status']) in {'failed', 'stopped'}:
                raise RuntimeError(str(row['last_error'] or f"The Dashboard PPT job {row['status']}."))
            update_run(task_repository, run_id, message=f"Waiting for Dashboard PPT job {job_id} ({int(row['progress'] or 0)}%)")
            time.sleep(3)
        raise RuntimeError('The Dashboard PPT job did not finish within three hours.')

    def dashboard_details(serialized: dict[str, Any]) -> list[str]:
        cover = serialized.get('cover') or {}
        lines = [f"Template: {serialized.get('template') or '—'} · {serialized.get('nr_mode')} · {serialized.get('scope')}"]
        for label, key in (('Campaigns', 'campaigns'), ('Regions', 'regions'), ('Cities', 'cities')):
            if cover.get(key):
                value = cover[key]
                lines.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
        lines.extend(str(item) for item in serialized.get('filters') or [])
        return lines

    def dashboard_definition(stored: dict[str, Any], entry: dict[str, Any], task_repository=None) -> dict[str, Any]:
        """The saved Dashboard with the artifact's Scope, CDRs, dates and filters."""
        definition = dict(stored)
        if entry.get('auto_cdrs'):
            # The CDRs of the Dashboard's NR Mode and of the entry's Campaign filter, chosen when it is generated.
            definition.pop('datasets', None)
            definition.update({
                'scope': entry['scope'], 'vendor_comparison': entry['vendor_comparison'], 'auto_cdrs': True,
                'date_from': entry.get('date_from') or 'Oldest', 'date_to': entry.get('date_to') or 'Newest',
                'filters': dict(entry.get('filters') or {}),
            })
            return definition
        if entry.get('cdr_selection') in CDR_SELECTIONS and task_repository is not None:
            nr_mode = 'SA' if str(stored.get('technology') or 'nsa').upper() == 'SA' else 'NSA'
            entry = {**entry, 'datasets': cdrs_by_kind(task_repository, automatic_cdrs(task_repository, nr_mode, entry['cdr_selection']))}
        definition.update({
            'scope': entry['scope'], 'vendor_comparison': entry['vendor_comparison'],
            'date_from': entry.get('date_from') or 'Oldest', 'date_to': entry.get('date_to') or 'Newest',
            'filters': dict(entry.get('filters') or {}),
        })
        if entry.get('datasets'):
            definition['datasets'] = entry['datasets']
        return definition

    def generate_dashboard(entry, task_repository, folder, stamp, user, run_id) -> dict[str, Any]:
        tools = core.dashboard_reporting
        stored = tools.list_dashboards(task_repository).get(entry['dashboard_id'])
        title = f"Dashboard · {entry.get('label') or (stored or {}).get('name') or entry['dashboard_id']}"
        try:
            if not isinstance(stored, dict):
                raise RuntimeError('The Dashboard no longer exists.')
            update_run(task_repository, run_id, message=f'Generating {title}')
            job_id = tools.queue_export(entry['dashboard_id'], user, dashboard_definition(stored, entry, task_repository),
                                        theme=entry.get('theme') or None)
            row = wait_for_dashboard_job(task_repository, job_id, run_id)
            source = Path(str(row['output_path']))
            # Dashboard PPT names start with their own generation time, which is dropped.
            destination = artifact_path(folder, stamp, 'PPT Dashboards', entry.get('label') or source.stem, source.suffix)
            shutil.copy2(source, destination)
            return ready_artifact('dashboards', title, destination, dashboard_details(tools.serialize_job(row)))
        except Exception as exc:
            return failed_artifact('dashboards', title, getattr(exc, 'detail', exc))

    def scoring_details(job: dict[str, Any], entry: dict[str, Any], names: dict[int, str]) -> list[str]:
        scenarios = [scenario['name'] for scenario in (entry.get('report') or {}).get('scenarios') or []]
        return [f"NR Mode: {nr_mode_label(job.get('nr_mode')) or '—'}",
                f"CDRs: {', '.join(names.get(int(value), str(value)) for value in job.get('dataset_ids') or []) or '—'}",
                f"GAP reference: {job.get('baseline_operator') or entry.get('baseline_operator') or 'EE'}",
                f"Report scenarios: {', '.join(scenarios) or '—'}"]

    def campaigns_of_cdrs(task_repository, dataset_ids, compact: bool = False) -> list[str]:
        values = sort_campaigns(value for values in cdr_campaigns(task_repository, dataset_ids).values() for value in values)
        return sort_campaigns({compact_campaign_value(value) or value for value in values}) if compact else values

    def migrate_auto_cdrs(definition: dict[str, Any], task_repository) -> dict[str, Any]:
        """A job saved when its CDRs were chosen by hand or by an automatic choice chooses them by Campaign.

        The newest complete set becomes Latest campaign, every complete set every campaign, and CDRs chosen by
        hand the campaigns they hold; a Dashboard that used its own CDRs keeps its Campaign filter. Non-Qualified
        Calls take the NR Mode and the campaigns of the CDRs of their CDRs filter.
        """
        migrated = json.loads(json.dumps(definition))
        analysis = migrated.get('dataset_analysis')
        if isinstance(analysis, dict) and not analysis.get('auto_cdrs'):
            # CDR Analysis: the NR Mode of its CDRs (NSA when they mix both) and their campaigns, or the campaigns of
            # its Campaign filter, which now chooses the CDRs.
            ids = analysis.get('dataset_ids') or []
            filters = dict(analysis.get('filters') or {})
            modes = [row['nr_mode'] for row in resolve_cdr_rows(task_repository, ids)] if ids else []
            analysis['nr_mode'] = 'SA' if modes and modes.count('SA') > modes.count('NSA') else 'NSA'
            analysis['campaigns'] = (filters.pop('campaigns', None) or (campaigns_of_cdrs(task_repository, ids, compact=True) if ids
                                     else [] if analysis.get('cdr_selection', 'all_complete') == 'all_complete' else [LATEST_CAMPAIGN]))
            analysis.update(filters=filters, dataset_ids=[], cdr_selection='', auto_cdrs=True)
        tools = getattr(core, 'dashboard_reporting', None)
        stored_dashboards = tools.list_dashboards(task_repository) if tools is not None and migrated.get('dashboards') else {}
        for entry in migrated.get('dashboards') or []:
            if entry.get('auto_cdrs'):
                continue
            filters = dict(entry.get('filters') or {})
            if not any(str(field).casefold() == 'campaign' for field in filters):
                ids = [value for values in (entry.get('datasets') or {}).values() for value in values]
                stored = stored_dashboards.get(entry.get('dashboard_id')) or {}
                campaigns = ([LATEST_CAMPAIGN] if entry.get('cdr_selection') == 'newest'
                             else [] if entry.get('cdr_selection') == 'all_complete'
                             else campaigns_of_cdrs(task_repository, ids) if ids
                             else next((values for field, values in (stored.get('filters') or {}).items() if str(field).casefold() == 'campaign'), []))
                if campaigns:
                    filters['Campaign'] = list(campaigns)
            entry.update(filters=filters, datasets={}, cdr_selection='', auto_cdrs=True)
        for entry in migrated.get('scoring') or []:
            if entry.get('auto_cdrs'):
                continue
            ids = entry.get('dataset_ids') or []
            entry['campaigns'] = (campaigns_of_cdrs(task_repository, ids) if ids
                                  else [] if entry.get('cdr_selection') == 'all_complete' else [LATEST_CAMPAIGN])
            entry.update(dataset_ids=[], cdr_selection='', auto_cdrs=True)
        for entry in migrated.get('network_insights') or []:
            if entry.get('auto_cdrs'):
                continue
            selection = entry.setdefault('selection', {})
            ids = [value for values in (selection.get('datasets') or {}).values() for value in values]
            if not selection.get('campaigns'):
                selection['campaigns'] = (campaigns_of_cdrs(task_repository, ids, compact=True) if ids
                                          else [] if entry.get('cdr_selection', 'all_complete') == 'all_complete' else [LATEST_CAMPAIGN])
            selection['datasets'] = {}
            entry.update(cdr_selection='', auto_cdrs=True)
        nq = ((migrated.get('modules') or {}).get('non_qualified_calls') or {}).get('options') or {}
        nq_filters = nq.get('filters') if isinstance(nq.get('filters'), dict) else {}
        if nq_filters.get('datasets'):
            ids = [int(value) for value in nq_filters.pop('datasets') if str(value).isdigit()]
            modes = {row['nr_mode'] for row in (resolve_cdr_rows(task_repository, ids))}
            nq_filters.setdefault('nr_mode', sorted(mode for mode in modes if mode))
            nq_filters.setdefault('campaign', campaigns_of_cdrs(task_repository, ids))
            nq_filters = {key: values for key, values in nq_filters.items() if values}
            nq['filters'] = nq_filters
        return migrated

    def resolve_cdr_rows(task_repository, ids) -> list[dict[str, Any]]:
        wanted = {int(value) for value in ids}
        return [{'id': int(row['id']), 'nr_mode': core.dataset_nr_mode(row['dataset_kind'], row['nr_mode'], row['file_name'])}
                for row in task_repository.list_datasets() if int(row['id']) in wanted]

    def scoring_cdrs(task_repository, entry: dict[str, Any]) -> list[int]:
        """The CDRs of a Scoring artifact now: those of its campaigns, each campaign with Data, Voice and Speech CDRs."""
        nr_mode = entry.get('nr_mode') or 'NSA'
        campaigns = scoring_campaigns(task_repository, nr_mode, entry.get('campaigns') or [])
        dataset_ids, incomplete = complete_campaign_cdrs(task_repository, nr_mode, campaigns)
        if not dataset_ids:
            missing = f" ({', '.join(incomplete)} lack a CDR type)" if incomplete else ''
            raise RuntimeError(f'There is no campaign with Data, Voice and Speech {nr_mode_label(nr_mode)} CDRs to score{missing}.')
        return dataset_ids

    def scoring_campaigns(task_repository, nr_mode: str, campaigns: list[str]) -> list[str]:
        """The campaigns a Scoring Campaign filter chooses now: with NSA vs SA a Latest choice stands for quarters, each
        with its NSA and SA campaigns, as in Scoring & GAP Analysis."""
        if normalize_scoring_nr_mode(nr_mode) == NSA_VS_SA:
            from src.modules.scoring_selection import expand_scoring_campaigns
            return expand_scoring_campaigns(task_repository, nr_mode, campaigns)
        return resolve_campaign_filter(task_repository, nr_mode, campaigns)

    def automatic_cdrs(task_repository, nr_mode: str, selection: str) -> list[int]:
        """The CDRs an automatic choice selects now: the newest complete set or every complete set of the NR Mode."""
        if selection == 'all_complete':
            return core.select_all_complete_cdrs(task_repository, nr_mode)
        included = core.combined_dataset_ids(task_repository)
        candidates = [row for row in task_repository.list_datasets()
                      if row['status'] == 'ready' and str(row['dataset_kind']) in {'data', 'voice', 'speech'}
                      and int(row['id']) in included
                      and core.dataset_nr_mode(row['dataset_kind'], row['nr_mode'], row['file_name']) == nr_mode]
        if not candidates:
            raise RuntimeError(f"There are no ready {nr_mode} CDRs.")
        newest = max(candidates, key=lambda row: int(row['id']))
        return core.select_latest_companion_cdrs(task_repository, int(newest['id']))

    def automatic_cdrs_every_mode(task_repository, selection: str) -> list[int]:
        """The CDRs an automatic choice selects now in NSA and in SA, for artifacts without an NR Mode."""
        chosen: list[int] = []
        errors = []
        for nr_mode in ('NSA', 'SA'):
            try:
                chosen.extend(automatic_cdrs(task_repository, nr_mode, selection))
            except (RuntimeError, ValueError) as exc:
                errors.append(str(exc))
        if not chosen:
            raise RuntimeError(' '.join(errors) or 'There are no complete sets of Data, Voice and Speech CDRs.')
        return chosen

    def cdrs_by_kind(task_repository, dataset_ids: list[int]) -> dict[str, list[int]]:
        kinds = {int(row['id']): str(row['dataset_kind']) for row in task_repository.list_datasets()}
        grouped: dict[str, list[int]] = {}
        for dataset_id in dataset_ids:
            if kinds.get(int(dataset_id)) in {'data', 'voice', 'speech'}:
                grouped.setdefault(kinds[int(dataset_id)], []).append(int(dataset_id))
        return grouped

    def automatic_cdr_preview(task_repository) -> dict[str, dict[str, list[int]]]:
        """The CDRs each automatic choice would select now, per NR Mode (none when it cannot choose)."""
        preview: dict[str, dict[str, list[int]]] = {}
        for nr_mode in ('NSA', 'SA'):
            preview[nr_mode] = {}
            for selection in ('newest', 'all_complete'):
                try:
                    preview[nr_mode][selection] = [int(value) for value in automatic_cdrs(task_repository, nr_mode, selection)]
                except (RuntimeError, ValueError):
                    preview[nr_mode][selection] = []
        return preview

    def generate_scoring(entry, task_repository, folder, stamp, username, names, run_id) -> dict[str, Any]:
        title = f"Scoring · {scoring_entry_name(entry)}"
        try:
            dataset_ids = scoring_cdrs(task_repository, entry) if entry.get('auto_cdrs') else entry.get('dataset_ids') or automatic_cdrs(
                task_repository, entry['nr_mode'], entry.get('cdr_selection') or 'newest')
            report = entry['report']
            update_run(task_repository, run_id, message=f'Calculating {title}')
            base = {'dataset_ids': dataset_ids, 'nr_mode': entry['nr_mode'],
                    'baseline_operator': entry.get('baseline_operator') or 'EE',
                    'scoring_profile_id': entry.get('scoring_profile_id') or None}
            content, filename, export_job = core.build_scoring_report_document(task_repository, base, report, username)
            artifacts = []
            for export_format in entry.get('formats') or ['powerpoint']:
                suffix = '.docx' if export_format == 'word' else '.pptx'
                destination = artifact_path(folder, stamp, 'Scoring & GAP Analysis', entry.get('label') or Path(filename).stem, suffix)
                # Composed as the Scoring section of a Bundle Report Template (PowerPoint and Word alike).
                from src.modules.bundle_report_templates import module_document
                destination.write_bytes(module_document('scoring', content, export_format, 'Scoring & GAP Analysis',
                                                        theme=report.get('theme')))
                artifacts.append(ready_artifact('scoring', f"{title} ({FORMAT_LABELS[export_format]})", destination,
                                                scoring_details(export_job, entry, names)))
            return artifacts
        except Exception as exc:
            return [failed_artifact('scoring', title, exc)]

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
        try:
            if run is None or task is None:
                return
            started = now_local()
            stamp = started.strftime('%Y%m%d_%H%M%S')
            folder = output_root() / f"{stamp} - {safe_file_name(task['name'])} - run {run_id}"
            folder.mkdir(parents=True, exist_ok=True)
            update_run(task_repository, run_id, status='running', started_at=started.isoformat(), output_dir=str(folder),
                       message='Generating artifacts', progress=1)
            if not core.active_workspace or Path(core.active_workspace.database_path).resolve() != Path(database_path).resolve():
                raise RuntimeError('The Reporting Job workspace is no longer the active workspace.')
            definition, user = migrate_auto_cdrs(task['definition'], task_repository), run_user(task['created_by'])
            names = dataset_names(task_repository)
            steps: list[tuple[str, Any]] = []
            # Artifacts of modules the job owner can no longer use are reported, not generated.
            allowed = {module: core.user_has_feature(user, feature) for module, _label, feature in used_modules(definition)}
            for module, label, feature in used_modules(definition):
                if not allowed[module]:
                    steps.append((label, lambda module=module, label=label: [failed_artifact(module, label, f'{task["created_by"]} no longer has access to {label}.')]))
            definition = {**definition,
                          **{module: ({'enabled': False} if module == 'dataset_analysis' else [])
                             for module, permitted in allowed.items() if not permitted and module in MODULE_FEATURES},
                          'modules': {key: value for key, value in (definition.get('modules') or {}).items() if allowed.get(key)}}
            # The theme of the job colours every artifact that supports themes, also the favourite Bundle Report Templates it
            # generates (it prevails over theirs).
            theme = normalize_theme(definition.get('theme') or DEFAULT_THEME)
            if theme:
                definition = {
                    **definition,
                    'dataset_analysis': {**(definition.get('dataset_analysis') or {}), 'theme': theme},
                    'network_insights': [{**entry, 'theme': theme} for entry in definition.get('network_insights') or []],
                    'dashboards': [{**entry, 'theme': theme} for entry in definition.get('dashboards') or []],
                    'scoring': [{**entry, 'report': {**(entry.get('report') or {}), 'theme': theme}} for entry in definition.get('scoring') or []],
                    'modules': {key: {**config, 'theme': theme} for key, config in (definition.get('modules') or {}).items()},
                }
            if definition.get('dataset_analysis', {}).get('enabled'):
                steps.append(('CDR Analysis', lambda: generate_dataset_analysis(definition['dataset_analysis'], folder, stamp, user.username, names, task_repository)))
            for index, entry in enumerate(definition.get('network_insights') or [], start=1):
                steps.append(('Network Insights', lambda entry=entry, index=index: generate_network_insights(entry, folder, stamp, index, task_repository)))
            for entry in definition.get('dashboards') or []:
                steps.append(('Dashboard', lambda entry=entry: [generate_dashboard(entry, task_repository, folder, stamp, user, run_id)]))
            for entry in definition.get('scoring') or []:
                steps.append(('Scoring', lambda entry=entry: generate_scoring(entry, task_repository, folder, stamp, user.username, names, run_id)))
            for key, config in (definition.get('modules') or {}).items():
                provider = ARTIFACT_PROVIDERS.get(key)
                if provider is None:
                    steps.append((key, lambda key=key: [failed_artifact(key, key, 'This module no longer provides Reporting artifacts.')]))
                else:
                    steps.append((provider['label'], lambda provider=provider, config=config, key=key: generate_provider(key, provider, config, folder, stamp, user)))
            artifacts: list[dict[str, Any]] = []
            for index, (label, step) in enumerate(steps):
                update_run(task_repository, run_id, message=f'Generating {label} ({index + 1}/{len(steps)})',
                           progress=max(1, round(index * 90 / max(len(steps), 1))))
                artifacts.extend(step())
                update_run(task_repository, run_id, artifacts=artifacts)
            # A file listed as ready must still exist when the run ends; otherwise it failed.
            for item in artifacts:
                if item['status'] == 'ready' and not (folder / item['file_name']).is_file():
                    item.update(status='failed', file_name='', size=0, error='The file was not kept after it was generated.')
            ready = [item for item in artifacts if item['status'] == 'ready']
            email_status, error = '', ''
            if task['send_email'] and ready:
                update_run(task_repository, run_id, message='Sending the email', progress=95)
                try:
                    settings = core.email_delivery_settings(core.repository, include_password=True)
                    text, body = email_bodies(task['name'], started, artifacts, core.__app_name__)
                    core.send_email(settings, task['recipients'], email_subject(task['name'], started), text, body,
                                    [(item['file_name'], folder / item['file_name']) for item in ready])
                    email_status = f"Sent to {', '.join(task['recipients'])}"
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
        except Exception as exc:
            update_run(task_repository, run_id, status='failed', message='The run failed', progress=100,
                       error=str(exc), finished_at=now_local().isoformat())
        finally:
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
            if run and run['status'] in {'queued', 'running'}:
                update_run(task_repository, run_id, status='failed', message='The run failed', progress=100,
                           error=f'The Reporting worker stopped unexpectedly (exit code {exit_code}).',
                           finished_at=now_local().isoformat())
        finally:
            with active_lock:
                active_runs.discard((database, run_id))

    def start_run(task_repository, task: dict[str, Any], trigger: str, username: str, workspace_id: str | None = None) -> int:
        run_id = create_run(task_repository, task, trigger, username)
        database = str(Path(task_repository.db_path).resolve())
        with active_lock:
            active_runs.add((database, run_id))
        active = core.active_workspace
        if workspace_id and not (active and str(Path(active.database_path).resolve()) == database):
            worker_executor.submit(run_in_worker, workspace_id, database, run_id)
        else:
            executor.submit(execute_run, database, run_id)
        return run_id

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
                with active_lock:
                    running = {run_id for run_database, run_id in active_runs if run_database == database}
                fail_interrupted_runs(task_repository, running)
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

    # -- options ------------------------------------------------------------
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

    def reporting_options(task_repository, user) -> dict[str, Any]:
        from src.modules.ppt_dashboards import ADAPTATIVE_FILTER_FIELDS

        datasets = [
            {'id': int(row['id']), 'file_name': str(row['file_name']), 'kind': str(row['dataset_kind']),
             'nr_mode': core.dataset_nr_mode(row['dataset_kind'], row['nr_mode'], row['file_name'])}
            for row in task_repository.list_datasets()
            if row['status'] == 'ready' and str(row['dataset_kind']) in {'data', 'voice', 'speech'}
        ]
        datasets.sort(key=lambda item: item['id'], reverse=True)
        tools = getattr(core, 'dashboard_reporting', None)
        dashboards = []
        if tools is not None:
            for dashboard_id, stored in tools.list_dashboards(task_repository).items():
                if not isinstance(stored, dict):
                    continue
                dashboards.append({
                    'id': dashboard_id, 'name': str(stored.get('name') or dashboard_id),
                    'template': str(stored.get('template') or ''), 'scope': str(stored.get('scope') or 'single'),
                    'vendor_comparison': str(stored.get('vendor_comparison') or 'operator_vendor'),
                    'technology': str(stored.get('technology') or 'nsa'), 'datasets': stored.get('datasets') or {},
                    'filters': stored.get('filters') or {}, 'custom_fields': stored.get('custom_fields') or [],
                    'date_from': str(stored.get('date_from') or ''), 'date_to': str(stored.get('date_to') or ''),
                })
        dashboards.sort(key=lambda item: item['name'].casefold())
        try:
            profiles = task_repository.get_scoring_profiles()
            methodologies = [{'id': profile['id'], 'name': profile.get('name') or profile['id']} for profile in profiles['profiles']]
            active_methodology = profiles['active_profile_id']
        except ValueError:
            methodologies, active_methodology = [], ''
        # Filter values come from the cached catalogues; incomplete ones are rebuilt in the background
        # (it can take minutes for large CDRs) and the editor says so instead of waiting.
        catalogues_pending = complete_catalogues_in_background(task_repository, [item['id'] for item in datasets])
        catalogue = task_repository.cdr_catalogue_values()
        # Operators and Vendors with their Operator and Vendor Maps labels, as every module shows them.
        mapper = ValueMapper.from_repository(task_repository)

        def mapped(values: dict[str, Any]) -> dict[str, list[Any]]:
            return {'Operator': mapper.values('operator', values.get('operators', [])),
                    'Operator_Vendor': mapper.values('operator_vendor', values.get('vendors', [])),
                    'Vendor_Operator': mapper.values('vendor_operator', values.get('vendor_operators', [])),
                    'Vendor': mapper.values('vendor', values.get('vendors_only', [])),
                    'Region': values.get('regions', []), 'Cluster': values.get('clusters', []),
                    'City': values.get('cities', []), 'Campaign': values.get('campaigns', [])}

        return {
            'allowed_modules': {module: core.user_has_feature(user, feature) for module, feature in MODULE_FEATURES.items()},
            'providers': [provider_options(key, provider, user)
                          for key, provider in ARTIFACT_PROVIDERS.items() if core.user_has_feature(user, provider['feature'])],
            'datasets': datasets, 'dashboards': dashboards,
            'dashboard_filter_fields': list(ADAPTATIVE_FILTER_FIELDS),
            'main_cities': list(task_repository.list_main_cities()),
            # The Scoring report editor shows and saves Operators with their Operator Maps label.
            'operator_groups': [{'canonical': group['canonical'], 'aliases': group['aliases']}
                                for group in task_repository.list_operator_mapping_groups()],
            'methodologies': methodologies, 'active_methodology': active_methodology,
            # The colour themes the Scoring report editor offers (see scoring_themes).
            'scoring_themes': themes_payload()['themes'],
            # The default theme of the application, that of a new artifact.
            'default_theme': themes_payload()['default'],
            # The CDRs the automatic choices of CDR Analysis select now, per NR Mode (they choose again at each run).
            'automatic_cdrs': automatic_cdr_preview(task_repository),
            # The campaigns of the CDRs of each NR Mode, and the choices that follow the newest ones.
            'campaigns': {nr_mode: campaign_values(task_repository, nr_mode) for nr_mode in ('NSA', 'SA', NSA_VS_SA)},
            'campaign_presets': CAMPAIGN_PRESET_LABELS,
            'values': mapped(catalogue),
            # The filter values of each CDR, so every entry lists only the values of the CDRs it uses.
            'values_by_dataset': {
                dataset_id: mapped(catalogue_values)
                for dataset_id, catalogue_values in task_repository.cdr_catalogues_by_dataset([item['id'] for item in datasets]).items()
            },
            'catalogues_pending': catalogues_pending,
            'formats': list(REPORT_FORMATS),
            # CDR Analysis: the metrics of the ready CDRs, and its aggregation and CDF comparison choices.
            'cdr_metrics': {kind: list(dict.fromkeys(
                metric for dataset in datasets if dataset['kind'] == kind
                for metric in core.analysis_metric_columns(task_repository.list_dataset_row_columns(dataset['id']), kind)
            )) for kind in CDR_ANALYSIS_KINDS},
            'cdr_kinds': CDR_ANALYSIS_KINDS,
            'cdr_aggregations': CDR_ANALYSIS_AGGREGATIONS, 'cdr_cdf_groupings': CDR_ANALYSIS_CDF_GROUPINGS,
            'network_groupings': {'operator': 'Operator', 'vendor': 'Vendor', 'region': 'Region', 'cluster': 'Cluster', 'city': 'City',
                                  'environment': 'Environment', 'kind': 'CDR type', 'campaign': 'Campaign'},
            'technologies': {'lte': 'LTE', 'nr': 'NR', 'lte_nr': 'LTE+NR'},
            'email_configured': bool(core.email_delivery_settings(core.repository).get('configured')),
            'timezone': now_local().strftime('%Z (UTC%z)'),
        }

    def provider_options(key, provider, user) -> dict[str, Any]:
        values = {}
        if callable(provider.get('values')):
            try:
                values = provider['values'](user) or {}
            except Exception:  # noqa: BLE001 - a provider without values still offers its formats.
                values = {}
        return {'key': key, 'label': provider['label'], 'formats': list(provider['formats']),
                'filters': [{'key': name, 'label': text} for name, text in provider.get('filters') or ()],
                'settings': list(provider.get('settings') or ()), 'values': values}

    def serialize_task(task, runs_by_id, dashboard_names, favourite_names=None, favourite_contents=None) -> dict[str, Any]:
        last = runs_by_id.get(task['last_run_id']) if task['last_run_id'] else None
        return {**task, 'artifacts': artifact_labels(task['definition'], dashboard_names, favourite_names),
                'artifact_groups': artifact_groups(task['definition'], dashboard_names, favourite_names, favourite_contents),
                'based_on': 'favourite' if based_on_favourite(task['definition']) else 'artifacts', 'last_run': last}

    # -- routes -------------------------------------------------------------
    @app.get('/reporting', response_class=HTMLResponse)
    def reporting_jobs_page(request: Request, user=Depends(reporting_user)):
        reporting_repository(user)
        return core.render_template(request, 'report_jobs.html', {'user': user})

    @app.get('/api/reporting/state')
    def reporting_jobs_state(user=Depends(reporting_user)):
        task_repository = reporting_repository(user)
        runs = list_runs(task_repository, limit=200)
        runs_by_id = {run['id']: run for run in runs}
        missing = [task['last_run_id'] for task in list_tasks(task_repository) if task['last_run_id'] and task['last_run_id'] not in runs_by_id]
        for run_id in missing:
            if (run := get_run(task_repository, run_id)) is not None:
                runs_by_id[run_id] = run
        tools = getattr(core, 'dashboard_reporting', None)
        dashboard_names = {str(key): str(value.get('name') or key) for key, value in tools.list_dashboards(task_repository).items()
                           if isinstance(value, dict)} if tools is not None else {}
        # The jobs that generate favourite Bundle Report Templates name them and list what each one includes.
        try:
            from src.modules.bundle_report_templates import favourite_contents as contents_of, list_favourites
            favourites = list_favourites(task_repository)
            favourite_names = {str(item['id']): item['name'] for item in favourites}
            favourite_contents = {str(item['id']): contents_of(item['definition'], dashboard_names) for item in favourites}
        except Exception:  # noqa: BLE001 - without them the jobs still list their artifacts.
            favourite_names, favourite_contents = {}, {}
        # Run History links only the files that still exist, and shows how much its artifacts take.
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
        # Jobs saved when CDRs were chosen by hand open with the campaigns of those CDRs.
        tasks = [{**task, 'definition': migrate_auto_cdrs(task['definition'], task_repository)} for task in list_tasks(task_repository)]
        return {
            'tasks': [serialize_task(task, runs_by_id, dashboard_names, favourite_names, favourite_contents) for task in tasks],
            'runs': runs, 'can_edit': user.role in {'user-editor', 'admin', 'super-admin'},
            'workspace_id': core.active_workspace.id if core.active_workspace else '',
        }

    @app.get('/api/reporting/options')
    def reporting_jobs_options(user=Depends(reporting_user)):
        return reporting_options(reporting_repository(user), user)

    @app.post('/api/reporting/auto-cdrs')
    def reporting_auto_cdrs(payload: dict[str, Any], user=Depends(reporting_user)):
        """The CDRs an entry uses now for its NR Mode and campaigns (``complete``: each campaign with every CDR type)."""
        task_repository = reporting_repository(user)
        nr_mode = normalize_scoring_nr_mode(payload.get('nr_mode')) or 'NSA'
        if nr_mode == NSA_VS_SA and not payload.get('complete'):
            nr_mode = 'NSA'
        campaigns = (scoring_campaigns(task_repository, nr_mode, _strings(payload.get('campaigns'))) if payload.get('complete')
                     else resolve_campaign_filter(task_repository, nr_mode, _strings(payload.get('campaigns'))))
        if payload.get('complete'):
            ids, incomplete = complete_campaign_cdrs(task_repository, nr_mode, campaigns)
            kinds = {int(row['id']): str(row['dataset_kind']) for row in task_repository.list_datasets()}
            chosen = {kind: [dataset_id for dataset_id in ids if kinds.get(dataset_id) == kind] for kind in ('data', 'voice', 'speech')}
        else:
            chosen, incomplete = resolve_cdrs(task_repository, nr_mode, campaigns), []
        names = dataset_names(task_repository)
        return {'campaigns': campaigns, 'incomplete_campaigns': incomplete,
                'cdrs': {kind: [names.get(dataset_id, str(dataset_id)) for dataset_id in ids] for kind, ids in chosen.items()},
                # Each CDR with its stage and campaigns, as the modules list them.
                'cdr_rows': describe_cdrs(task_repository, chosen)}

    def save_route(task_id, payload, user):
        task_repository = reporting_repository(user)
        try:
            definition = normalize_definition(payload.definition)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        # A Reporting Job only includes artifacts of the modules its author can use.
        forbidden = [label for _module, label, feature in used_modules(definition) if not core.user_has_feature(user, feature)]
        if forbidden:
            raise HTTPException(403, f"Your account cannot include artifacts of: {', '.join(forbidden)}.")
        try:
            task = save_task(task_repository, task_id, payload.model_dump(), user.username,
                             parse_recipients=core.parse_recipients, invalid_recipients=core.invalid_recipients)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        task_repository.try_add_log(user.username, 'save_reporting_job', json.dumps({'task_id': task['id'], 'name': task['name']}))
        return {'task': task}

    @app.post('/api/reporting/tasks')
    def reporting_jobs_create(payload: ReportTaskPayload, user=Depends(editor_user)):
        return save_route(None, payload, user)

    @app.put('/api/reporting/tasks/{task_id}')
    def reporting_jobs_update(task_id: int, payload: ReportTaskPayload, user=Depends(editor_user)):
        return save_route(task_id, payload, user)

    @app.post('/api/reporting/tasks/{task_id}/duplicate')
    def reporting_jobs_duplicate(task_id: int, user=Depends(editor_user)):
        task_repository = reporting_repository(user)
        task = get_task(task_repository, task_id)
        if task is None:
            raise HTTPException(404, 'Reporting Job not found.')
        names = {item['name'].casefold() for item in list_tasks(task_repository)}
        name, copy = f"{task['name']} (copy)", 2
        while name.casefold() in names:
            name, copy = f"{task['name']} (copy {copy})", copy + 1
        schedule = task['schedule'] if task['schedule'].get('mode') != 'once' or next_run_after(task['schedule'], now_local()) else {**task['schedule'], 'mode': 'manual'}
        payload = ReportTaskPayload(name=name, definition=task['definition'], send_email=task['send_email'],
                                    recipients=task['recipients'], schedule=schedule, enabled=False)
        result = save_route(None, payload, user)
        # The copy follows the job it copies.
        order = [item['id'] for item in list_tasks(task_repository) if item['id'] != result['task']['id']]
        order.insert(order.index(task_id) + 1 if task_id in order else len(order), result['task']['id'])
        reorder_tasks(task_repository, order)
        return result

    class OrderPayload(BaseModel):
        ids: list[int] = Field(default_factory=list)

    @app.post('/api/reporting/tasks/order')
    def reporting_jobs_order(payload: OrderPayload, user=Depends(editor_user)):
        task_repository = reporting_repository(user)
        tasks = reorder_tasks(task_repository, payload.ids)
        task_repository.try_add_log(user.username, 'reorder_reporting_jobs', json.dumps({'order': [task['name'] for task in tasks]}, ensure_ascii=False))
        return {'order': [task['id'] for task in tasks]}

    @app.delete('/api/reporting/tasks/{task_id}')
    def reporting_jobs_delete(task_id: int, user=Depends(editor_user)):
        task_repository = reporting_repository(user)
        try:
            folders = delete_task(task_repository, task_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        root = output_root().resolve()
        for folder in folders:
            path = Path(folder).resolve()
            if root in path.parents:
                shutil.rmtree(path, ignore_errors=True)
        task_repository.try_add_log(user.username, 'delete_reporting_job', json.dumps({'task_id': task_id}))
        return {'deleted': task_id}

    @app.post('/api/reporting/tasks/{task_id}/run')
    def reporting_jobs_run_now(task_id: int, user=Depends(editor_user)):
        task_repository = reporting_repository(user)
        task = get_task(task_repository, task_id)
        if task is None:
            raise HTTPException(404, 'Reporting Job not found.')
        run_id = start_run(task_repository, task, 'manual', user.username)
        task_repository.try_add_log(user.username, 'run_reporting_job', json.dumps({'task_id': task_id, 'run_id': run_id}))
        return {'run_id': run_id}

    @app.post('/api/reporting/tasks/{task_id}/enabled')
    async def reporting_jobs_enable(task_id: int, request: Request, user=Depends(editor_user)):
        body = await request.json()
        task_repository = reporting_repository(user)
        task = get_task(task_repository, task_id)
        if task is None:
            raise HTTPException(404, 'Reporting Job not found.')
        payload = ReportTaskPayload(name=task['name'], definition=task['definition'], send_email=task['send_email'],
                                    recipients=task['recipients'], schedule=task['schedule'], enabled=bool(body.get('enabled')))
        return save_route(task_id, payload, user)

    def run_or_404(task_repository, run_id):
        run = get_run(task_repository, run_id)
        if run is None:
            raise HTTPException(404, 'Reporting run not found.')
        return run

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

    @app.delete('/api/reporting/runs/{run_id}')
    def reporting_jobs_delete_run(run_id: int, user=Depends(editor_user)):
        task_repository = reporting_repository(user)
        run = run_or_404(task_repository, run_id)
        if run['status'] in {'queued', 'running'}:
            raise HTTPException(409, 'Wait for the run to finish before deleting it.')
        with task_repository.connection() as connection:
            connection.execute(f'DELETE FROM {REPORT_TASK_RUNS_TABLE} WHERE id = ?', (run_id,))
        path = Path(run['output_dir']).resolve() if run['output_dir'] else None
        if path and output_root().resolve() in path.parents:
            shutil.rmtree(path, ignore_errors=True)
        task_repository.try_add_log(user.username, 'delete_reporting_job_run', json.dumps({
            'run_id': run_id, 'name': run['task_name'],
        }))
        return JSONResponse({'deleted': run_id})
