"""Readable App Events: what each event did and changed, from the details it records.

Events of changes record ``changes`` as ``{name: [before, after]}`` (see :func:`changed_values`); App Events shows every
event as one sentence (:func:`describe_app_event`), also those recorded before with only their final state.
"""
from __future__ import annotations

from typing import Any, Callable

MAX_LISTED_VALUES = 8
MAX_TEXT_LENGTH = 160
MAX_SENTENCE_LENGTH = 600
# Settings named as Admin names them, and words that read better in capitals in the names of the details.
_FIELD_NAMES = {'modules_profile': 'Modules Profile', 'workspace_groups': 'Workspace Groups', 'workspaces': 'Workspaces',
                'bug_id': 'ticket ID', 'bug_reports': 'tickets'}
# Actions that keep the name of a module's former name, read with its current one (Bugs Report is Ticket Center).
_ACTION_PREFIXES = (('bug_report_', 'ticket_'),)
# What an event of a version that recorded only the final state says about it.
_NOT_RECORDED = 'earlier versions did not record which {} changed'
_UPPER_WORDS = {'id': 'ID', 'ids': 'IDs', 'mb': 'MB', 'cdr': 'CDR', 'cdrs': 'CDRs', 'nq': 'NQ', 'rca': 'RCA', 'ppt': 'PPT',
                'url': 'URL', 'nr': 'NR', 'lte': 'LTE', 'smtp': 'SMTP'}


def _empty(value: Any) -> bool:
    return value is None or value == '' or value == [] or value == {}


def _comparable(value: Any) -> Any:
    """Lists compare without their order; a missing value equals an empty one."""
    if _empty(value):
        return None
    if isinstance(value, (list, tuple, set)):
        return sorted((str(item) for item in value))
    return value


def changed_values(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    """The values that differ between two states of the same thing, as ``{name: [before, after]}``. Nested settings
    are compared one by one, named ``parent.name``."""
    changes: dict[str, list[Any]] = {}
    for key in dict.fromkeys([*before, *after]):
        old, new = before.get(key), after.get(key)
        if isinstance(old, dict) or isinstance(new, dict):
            if isinstance(old, dict) and isinstance(new, dict) or _empty(old) or _empty(new):
                for name, values in changed_values(old if isinstance(old, dict) else {}, new if isinstance(new, dict) else {}).items():
                    changes[f'{key}.{name}'] = values
                continue
        if _comparable(old) != _comparable(new):
            changes[str(key)] = [old, new]
    return changes


def field_label(name: str) -> str:
    """``max_attachments_mb`` → ``max attachments MB``; ``module_labels.reporting.title`` → ``module labels reporting title``."""
    if name in _FIELD_NAMES:
        return _FIELD_NAMES[name]
    words = str(name).replace('.', ' ').replace('_', ' ').replace('-', ' ').split()
    return ' '.join(_UPPER_WORDS.get(word.casefold(), word) for word in words)


def action_label(action: str) -> str:
    """``update_user`` → ``Update user``; ``bug_report_created`` → ``Ticket created``."""
    for former, current in _ACTION_PREFIXES:
        if action.startswith(former):
            action = current + action[len(former):]
    text = field_label(action)
    return text[:1].upper() + text[1:]


def value_text(value: Any) -> str:
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if _empty(value):
        return 'none'
    if isinstance(value, (list, tuple, set)):
        items = [value_text(item) for item in value]
        shown = ', '.join(items[:MAX_LISTED_VALUES])
        return shown + (f' (+{len(items) - MAX_LISTED_VALUES} more)' if len(items) > MAX_LISTED_VALUES else '')
    if isinstance(value, dict):
        if {'value', 'label'} <= set(value):
            return value_text(value['label'] or value['value'])
        return '; '.join(f'{field_label(key)} {value_text(item)}' for key, item in value.items() if not _empty(item)) or 'none'
    text = str(value)
    return text if len(text) <= MAX_TEXT_LENGTH else text[:MAX_TEXT_LENGTH - 1] + '…'


def changes_text(changes: Any, labels: dict[str, str] | None = None) -> str:
    """``role user-viewer → user-editor; Workspace Groups +UK, −DE``; booleans named in ``labels`` read as that word or
    its opposite (``active`` → ``activated`` / ``deactivated``)."""
    if not isinstance(changes, dict):
        return ''
    parts = []
    for name, values in changes.items():
        old, new = (list(values) + [None, None])[:2] if isinstance(values, (list, tuple)) else (None, values)
        if labels and name in labels and isinstance(new, bool):
            on, off = labels[name].split('/')
            parts.append(on if new else off)
        elif isinstance(old, (list, tuple, set)) or isinstance(new, (list, tuple, set)):
            before, after = [str(item) for item in old or []], [str(item) for item in new or []]
            added, removed = [item for item in after if item not in before], [item for item in before if item not in after]
            parts.append(f'{field_label(name)} ' + (', '.join([*(f'+{item}' for item in added), *(f'−{item}' for item in removed)])
                                                     or f'{value_text(old)} → {value_text(new)}'))
        else:
            parts.append(f'{field_label(name)} {value_text(old)} → {value_text(new)}')
    return '; '.join(parts)


def fields_text(details: dict[str, Any], skip: tuple[str, ...] = ()) -> str:
    """``username ELUILEY, role user-editor, active yes``: every recorded value but the empty ones."""
    parts = []
    # Only the starred Saved Filters are kept: the others are named unsaved.
    starred = details.get('starred') if isinstance(details.get('starred'), bool) and 'saved_filter_id' in details else None
    for key, value in details.items():
        if key in skip or _empty(value) or (key == 'starred' and starred is not None):
            continue
        if key == 'saved_filter_id' and starred is not None:
            parts.append(f'saved filter ID {value} (favourite)' if starred else f'unsaved filter ID {value}')
        elif key == 'changes':
            parts.append(changes_text(value))
        else:
            parts.append(f'{field_label(key)} {value_text(value)}')
    return ', '.join(part for part in parts if part)


def _members(details: dict[str, Any]) -> str:
    """``users +ANA, −BOB``: the users added and removed, by name (by ID in events recorded before)."""
    def people(key: str) -> list[str]:
        return [str(name) for name in details.get(f'{key}_users') or []] or [
            f'user ID {item}' for item in details.get(f'{key}_user_ids') or []]
    items = [*(f'+{name}' for name in people('added')), *(f'−{name}' for name in people('removed'))]
    return f"users {', '.join(items)}" if items else ''


def _sentence(subject: str, parts: list[str], unchanged: str = 'saved with no changes') -> str:
    parts = [part for part in parts if part]
    return f"{subject}: {'; '.join(parts)}." if parts else f'{subject} {unchanged}.'


def _user(details: Any) -> str:
    return str(details.get('username') or details.get('user_id') or '') if isinstance(details, dict) else str(details)


def _account(details: dict[str, Any]) -> str:
    """``name Ana García, role user-editor, active, Modules Profile Analysts, Workspace Groups UK``."""
    name = ' '.join(str(part) for part in (details.get('first_name'), details.get('last_name')) if part)
    parts = [f'name {name}' if name else '', f"role {details['role']}" if details.get('role') else '',
             ('active' if details['active'] else 'inactive') if 'active' in details else '']
    parts += [f'{field_label(key)} {value_text(details[key])}' for key in ('modules_profile', 'workspace_groups', 'workspaces')
              if not _empty(details.get(key))]
    return ', '.join(part for part in parts if part)


def _update_user(details: dict[str, Any]) -> str:
    subject = f'User {_user(details)}'
    if 'changes' not in details:
        # Recorded by a version that kept only the account as it was saved: that is not what changed.
        state = _account(details)
        return f"{subject} saved{f' ({state})' if state else ''}; {_NOT_RECORDED.format('fields')}."
    parts = [changes_text(details['changes'], {'active': 'activated/deactivated'})]
    if details.get('password_changed'):
        parts.append('password changed')
    return _sentence(subject, parts)


def _create_user(details: Any) -> str:
    account = _account(details) if isinstance(details, dict) else ''
    return f"User {_user(details)} created" + (f': {account}.' if account else '.')


def _delete_user(details: dict[str, Any]) -> str:
    account = _account(details)
    return f"User {_user(details)} deleted" + (f' ({account}).' if account else '.')


_BULK_USER_ACTIONS = {
    'role': 'Role set to {value}', 'modules_profile': 'Modules Profile set to {value}',
    'add_workspace_group': 'Added to Workspace Group {value}', 'remove_workspace_group': 'Removed from Workspace Group {value}',
    'activate': 'Activated', 'deactivate': 'Deactivated',
}


def _bulk_update_users(details: dict[str, Any]) -> str:
    action = str(details.get('action') or '')
    text = _BULK_USER_ACTIONS.get(action, action_label(action or 'change')).format(value=value_text(details.get('value')))
    changes = details.get('changes')
    if action in {'role', 'modules_profile'}:
        # Each user with the value it had, when the event records it.
        users = ', '.join(f'{name} (was {value_text(values[0])})' for name, values in changes.items()) if (
            isinstance(changes, dict) and changes) else value_text(details.get('users'))
        sentence = f'{text} for {users}'
    else:
        sentence = f"{text}: {value_text(details.get('users'))}"
    if details.get('skipped'):
        sentence += f". Skipped: {value_text(details['skipped'])}"
    return sentence + '.'


def _named(kind: str, details: dict[str, Any], id_key: str) -> str:
    return f"{kind} {details.get('name') or details.get(id_key) or ''}".strip()


def _create_named(kind: str, id_key: str, fields: tuple[str, ...]) -> Callable[[dict[str, Any]], str]:
    def describe(details: dict[str, Any]) -> str:
        values = ', '.join(f'{field_label(key)} {value_text(details[key])}' for key in fields if not _empty(details.get(key)))
        return f"{_named(kind, details, id_key)} created" + (f' with {values}.' if values else '.')
    return describe


def _update_named(kind: str, id_key: str, fields: tuple[str, ...]) -> Callable[[dict[str, Any]], str]:
    def describe(details: dict[str, Any]) -> str:
        subject = _named(kind, details, id_key)
        if 'changes' not in details:
            # Recorded by a version that kept only what was saved: that is not what changed.
            values = '; '.join(part for part in (', '.join(
                f'{field_label(key)} {value_text(details[key])}' for key in fields if not _empty(details.get(key))), _members(details)) if part)
            return f"{subject} saved{f' ({values})' if values else ''}; {_NOT_RECORDED.format('fields')}."
        return _sentence(subject, [changes_text(details['changes']), _members(details)])
    return describe


def _settings(label: str) -> Callable[[dict[str, Any]], str]:
    def describe(details: dict[str, Any]) -> str:
        if 'changes' not in details:
            # Recorded by a version that kept only the settings as saved (the nested ones, such as every module's
            # labels, stay in the raw details): that is not what changed.
            values = fields_text(details, skip=tuple(key for key, value in details.items() if isinstance(value, dict)))
            return f"{label} saved{f' ({values})' if values else ''}; {_NOT_RECORDED.format('settings')}."
        return _sentence(label, [changes_text(details['changes']), 'password changed' if details.get('password_changed') else ''])
    return describe


def _login(details: dict[str, Any]) -> str:
    if details.get('success') is False or details.get('result') == 'failed':
        login = details.get('username') or ''
        reason = field_label(str(details.get('reason') or 'failed'))
        return f"Failed sign-in{f' as {login}' if login else ''} ({reason})" + (
            f" to workspace {details['workspace_id']}." if details.get('workspace_id') else '.')
    return 'Signed in' + (f" as {details['role']}" if details.get('role') else '') + (
        f" to workspace {details.get('workspace') or details.get('workspace_id')}." if details.get('workspace') or details.get('workspace_id') else '.')


def _mapping_assign(kind: str) -> Callable[[Any], str]:
    def describe(details: Any) -> str:
        if isinstance(details, dict) and isinstance(details.get('changes'), dict):
            changes = details['changes']
            return _sentence(f'{kind} Maps', [', '.join(
                f'{value} {value_text(values[0]) if values[0] else "unassigned"} → {value_text(values[1])}'
                for value, values in changes.items())])
        # Recorded before the changes were: every value with the label it was given.
        items = details.get('assignments') if isinstance(details, dict) else details
        return f"{kind} Maps assigned: " + ', '.join(
            f"{item.get('value')} → {item.get('label')}" for item in items or [] if isinstance(item, dict)) + '.'
    return describe


_DESCRIBERS: dict[str, Callable[[Any], str]] = {
    'operator_mapping_assign': _mapping_assign('Operator'),
    'vendor_mapping_assign': _mapping_assign('Vendor'),
    'login': _login,
    'logout': lambda details: 'Signed out.',
    'create_user': _create_user,
    'update_user': _update_user,
    'delete_user': _delete_user,
    'reset_user_password': lambda details: f'Password of user {_user(details)} reset.',
    'bulk_update_users': _bulk_update_users,
    'create_modules_profile': _create_named('Modules Profile', 'profile_id', ('modules', 'members')),
    'update_modules_profile': _update_named('Modules Profile', 'profile_id', ('modules',)),
    'set_default_modules_profile': lambda details: f"{_named('Modules Profile', details, 'profile_id')} made the default.",
    'delete_modules_profile': lambda details: f"{_named('Modules Profile', details, 'profile_id')} deleted.",
    'create_workspace_group': _create_named('Workspace Group', 'group_id', ('workspaces', 'workspace_ids', 'members')),
    'update_workspace_group': _update_named('Workspace Group', 'group_id', ('workspaces', 'workspace_ids')),
    'delete_workspace_group': lambda details: f"{_named('Workspace Group', details, 'group_id')} deleted.",
    'save_interface_settings': _settings('Interface Settings'),
    'save_application_configuration': _settings('Application configuration'),
    'save_email_delivery': _settings('Email delivery'),
    'save_scheduled_backup_settings': _settings('Scheduled backups'),
    'save_backup_selection': _settings('Backup selection'),
}


def describe_app_event(action: str, details: Any) -> str:
    """One readable sentence for an App Event: its own wording for the actions that have one, otherwise the action and
    every recorded value (``Delete saved filter: filter ID 9.``); plain-text details are already a sentence."""
    action = str(action or '')
    describer = _DESCRIBERS.get(action)
    if describer and (isinstance(details, (dict, list)) or action in {'create_user', 'logout'}):
        try:
            return describer(details)
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
    if isinstance(details, dict):
        values = fields_text(details)
        sentence = f'{action_label(action)}: {values}' if values else action_label(action)
    elif isinstance(details, list):
        sentence = f'{action_label(action)}: {value_text(details)}'
    else:
        return str(details or action_label(action))
    return (sentence if len(sentence) <= MAX_SENTENCE_LENGTH else sentence[:MAX_SENTENCE_LENGTH - 1] + '…') + '.'


# Where an App Event ran (its Executed by), as a key: ``module:<module>`` (the page a signed-in user acted from; an
# empty module when an earlier version did not record it), ``server:<kind>`` (work the server does on its own),
# ``remote:<server>`` (a transfer another server sent) or ``public:<page>`` (pages used without signing in).
SERVER_EVENT_KINDS = (('scheduler', 'Scheduler'), ('background', 'Background job'), ('idle', 'Idle task'), ('startup', 'Startup'))
# The pages of Ticket Center keep the key of Bugs Report, its former name.
PUBLIC_EVENT_PAGES = (('sign-in', 'Sign-in'), ('access-request', 'Access request'), ('bug-report', 'Ticket Center'), ('page', 'Page'))
_SERVER_ACTIONS = {
    'scheduler': {'reporting_scheduler_error'},
    'idle': {'precompute_dashboard_charts', 'prewarm_dashboard_cache', 'prewarm_dashboard_cache_failed', 'nq_calls_reindexed',
             'map_area_fill_failed'},
    'startup': {'recover_interrupted_background_jobs', 'recover_interrupted_saved_filters', 'recover_inconsistent_datasets',
                'resume_interrupted_dataset', 'migrate_app_event_users', 'nq_call_keys_upgraded'},
    'background': {'process_dataset', 'process_dataset_failed', 'analyze_dataset_failed', 'analyze_dataset_warning',
                   'map_dataset_vendors', 'map_dataset_vendors_failed', 'map_dataset_regions', 'map_dataset_regions_failed',
                   'vendor_mapping_skipped', 'clear_dataset_vendors', 'clear_dataset_vendors_failed', 'chart_set_rendering_completed',
                   'chart_set_rendering_warning', 'chart_set_published', 'chart_set_generation_failed', 'export_dashboard_ppt_failed',
                   'export_dashboard_ppt_warning', 'export_netcheck_cdr_report_failed', 'scoring_calculation_failed',
                   'sync_combined_cdr_tables_completed', 'sync_combined_cdr_tables_failed', 'reporting_job_run'},
}
_SERVER_ACTION_PREFIXES = (('scheduled_database_backup_', 'scheduler'),)
_REMOTE_ACTION_PREFIXES = ('incoming_server_transfer_', 'incoming_transfer_import_')
_PUBLIC_ACTIONS = {'access_request': 'access-request', 'access_change_request': 'access-request', 'login': 'sign-in',
                   'logout': 'sign-in'}
# The module of the events of earlier versions, which did not record the page they came from (by action, or its start).
_MODULE_ACTIONS = (
    ('non-qualified-calls', ('nq_',)),
    ('network-insights', ('network_insights_', 'export_network_insights_')),
    ('scoring', ('scoring_', 'save_scoring_', 'export_scoring_', 'import_scoring_', 'delete_scoring_')),
    ('bugs-report', ('bug_report_',)),
    ('ppt-dashboards', ('save_dashboard', 'delete_dashboard', 'rename_dashboard', 'export_dashboard_', 'download_dashboard_ppt',
                        'delete_all_dashboard_ppts', 'stop_dashboard_ppt_job', 'change_dashboard_template',
                        'update_dashboard_chart_template', 'interrupt_dashboard_preparation')),
    ('reporting', ('save_reporting_job', 'run_reporting_job', 'delete_reporting_job', 'download_reporting_job_')),
    ('builders', ('run_query_builder', 'save_query_builder', 'update_query_builder', 'delete_query_builder',
                  'export_query_builder_', 'cancel_query_builder_run')),
    ('admin', ('create_user', 'update_user', 'delete_user', 'bulk_update_users', 'reset_user_password', 'create_modules_profile',
               'update_modules_profile', 'update_module_profile', 'set_default_modules_profile', 'delete_modules_profile',
               'create_workspace_group', 'update_workspace_group', 'delete_workspace_group', 'update_user_group',
               'save_interface_settings', 'database_table_', 'cleanup_database', 'save_backup_selection',
               'save_scheduled_backup_settings', 'start_manual_database_', 'create_backup_directory', 'import_package_',
               'export_package_', 'download_export_package', 'accept_server_transfer', 'reject_server_transfer',
               'outgoing_server_transfer_', 'stop_outgoing_server_transfer', 'delete_recovered_transfer_package',
               'import_recovered_transfer_package', 'reset_application', 'admin_notices_seen', 'create_report_template',
               'save_report_template', 'delete_report_template', 'rename_report_template', 'duplicate_report_template',
               'import_report_template', 'export_report_template', 'activate_report_template', 'change_report_template_type',
               'copy_report_template_content')),
    ('config', ('operator_mapping_', 'vendor_mapping_', 'campaign_map', 'main_cities_save', 'save_workspace_calculated_dimensions',
                'export_workspace_calculated_dimensions', 'import_workspace_calculated_dimensions',
                'rematerialize_workspace_auto_calculated_fields', 'save_application_configuration', 'save_email_delivery',
                'email_delivery_test_', 'map_areas_', 'network_serving_networks_saved', 'network_spectrum_holdings_saved')),
    ('workspace', ('upload_dataset', 'cancel_dataset_upload', 'delete_dataset', 'rename_dataset', 'reprocess_dataset',
                   'retry_dataset', 'stop_dataset', 'reorder_datasets', 'update_dataset_', 'queue_dataset_mappings', 'queue_vendor_',
                   'queue_region_', 'stop_vendor_', 'stop_region_', 'create_workspace', 'open_workspace', 'close_workspace',
                   'delete_workspace', 'rename_workspace', 'duplicate_workspace', 'set_workspace_cdr_type', 'starter_content_')),
    ('ppt-reporting-old', ('generate_powerpoint_report', 'chart_set_generation_requested', 'export_netcheck_cdr_report',
                           'download_report_', 'delete_report_job', 'delete_report_chart', 'delete_all_report_', 'retry_report_',
                           'stop_report_')),
)


def app_event_origin(action: str, details: Any, stored: str = '', triggered_by: str = '') -> str:
    """Where an App Event ran: the server's own work and transfers by their action; otherwise the page it came from (as
    recorded with the event, or by its action for the events of earlier versions)."""
    action = str(action or '')
    details = details if isinstance(details, dict) else {}
    if action == 'reporting_job_run' and details.get('trigger') == 'schedule':
        return 'server:scheduler'
    for kind, actions in _SERVER_ACTIONS.items():
        if action in actions:
            return f'server:{kind}'
    for prefix, kind in _SERVER_ACTION_PREFIXES:
        if action.startswith(prefix):
            return f'server:{kind}'
    if action.startswith(_REMOTE_ACTION_PREFIXES):
        return f"remote:{details.get('source') or details.get('source_name') or 'another server'}"
    if action in _PUBLIC_ACTIONS:
        return f'public:{_PUBLIC_ACTIONS[action]}'
    # Background work of earlier versions said so in its details.
    if str(details.get('executed_by') or details.get('actioned_by') or '').strip().casefold() == 'system':
        return 'server:background'
    if stored:
        return stored
    for module, starts in _MODULE_ACTIONS:
        if action.startswith(starts):
            return f'module:{module}'
    return 'server:background' if str(triggered_by or '').casefold() == 'system' else 'module:'


def app_event_origin_parts(origin: str, module_titles: dict[str, str]) -> dict[str, Any]:
    """How App Events shows where an event ran: a name, a tag below it and the group it is listed in (0 server, 1 other
    servers, 2 public pages, 3 modules in their order)."""
    kind, _, value = str(origin or '').partition(':')
    if kind == 'server':
        tags = dict(SERVER_EVENT_KINDS)
        return {'name': 'Server', 'tag': tags.get(value, field_label(value)), 'group': 0,
                'order': [key for key, _ in SERVER_EVENT_KINDS].index(value) if value in tags else len(tags)}
    if kind == 'remote':
        return {'name': 'Remote server', 'tag': value or 'another server', 'group': 1, 'order': 0}
    if kind == 'public':
        pages = dict(PUBLIC_EVENT_PAGES)
        return {'name': 'Public', 'tag': pages.get(value, field_label(value)), 'group': 2,
                'order': [key for key, _ in PUBLIC_EVENT_PAGES].index(value) if value in pages else len(pages)}
    modules = list(module_titles)
    if value in module_titles:
        return {'name': module_titles[value], 'tag': 'module', 'group': 3, 'order': modules.index(value)}
    return {'name': 'Application', 'tag': 'not recorded', 'group': 3, 'order': len(modules)}
