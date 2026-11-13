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
_FIELD_NAMES = {'modules_profile': 'Modules Profile', 'workspace_groups': 'Workspace Groups', 'workspaces': 'Workspaces'}
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
    """``update_user`` → ``Update user``."""
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
    """``username EUSER01, role user-editor, active yes``: every recorded value but the empty ones."""
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
    """``name User A, role user-editor, active, Modules Profile Analysts, Workspace Groups UK``."""
    name = ' '.join(str(part) for part in (details.get('first_name'), details.get('last_name')) if part)
    parts = [f'name {name}' if name else '', f"email {details['email']}" if details.get('email') else '',
             f"role {details['role']}" if details.get('role') else '',
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


def _application_started(details: dict[str, Any]) -> str:
    workspace = details.get('active_workspace') or details.get('active_workspace_id')
    parts = [
        f'active workspace {workspace}' if workspace else 'no active workspace',
        f"ready in {details['ready_in_seconds']} s" if details.get('ready_in_seconds') is not None else '',
        f"address {details['host']}:{details['port']}" if details.get('host') and details.get('port') else '',
        f"Python {details['python']}" if details.get('python') else '',
        f"platform {details['platform']}" if details.get('platform') else '',
        f"PID {details['pid']}" if details.get('pid') else '',
    ]
    error = str(details.get('error') or '').strip().rstrip('.')
    return ('Application started' + (f" (version {details['version']})" if details.get('version') else '')
            + f": {', '.join(part for part in parts if part)}." + (f' {error}.' if error else ''))


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


def _name_comments(details: Any) -> str:
    changes = details.get('changes') if isinstance(details, dict) else None
    if not isinstance(changes, dict):
        return 'Comments of the Operator names saved.'
    return _sentence('Comments of the Operator names', [', '.join(
        f'{name} {value_text(values[0])} → {value_text(values[1])}' for name, values in changes.items()
        if isinstance(values, (list, tuple)) and len(values) == 2)])


_EMAIL_KINDS = {'ticket': 'Ticket Center email', 'access_request': 'Access request email', 'access_granted': 'Access granted email',
                'password_reset': 'Password reset email', 'report': 'Reporting email', 'test': 'Test email'}


def _email(sent: bool) -> Callable[[Any], str]:
    """An email of the tool, sent or failed: its kind, subject and recipients (and why it failed)."""
    def describe(details: Any) -> str:
        kind = _EMAIL_KINDS.get(str(details.get('kind') or ''), 'Email')
        recipients = ', '.join(str(item) for item in [*(details.get('recipients') or []), *(details.get('cc') or [])])
        text = f"{kind} \"{details.get('subject') or ''}\" {'sent to' if sent else 'not sent to'} {recipients or 'nobody'}"
        return f"{text}: {details.get('error')}." if not sent and details.get('error') else f'{text}.'
    return describe


_DEMO_SIGN_OUT_REASONS = {
    'no_page_open': 'at once (no page open)', 'warning_time_over': 'after the warning time', 'saved_changes': 'once its changes were saved',
    'signed_out_by_user': 'with Sign out now', 'pages_closed': 'after its pages were closed',
}


def _demo_users(details: dict[str, Any]) -> str:
    users = ', '.join(str(user) for user in details.get('users') or []) or 'nobody else'
    return f"{users}{' (and every super-admin)' if details.get('super_admins_always') else ''}"


def _demo_mode_changed(details: dict[str, Any]) -> str:
    return _sentence('Demo Mode', [changes_text(details.get('changes') or {}, {
        'expected_end': 'Expected end', 'remind_at': 'Reminder', 'message': 'Message', 'users': 'Users with access',
        'keep_super_admins': 'Every super-admin keeps access'})])


# -- NQ Analysis Center ------------------------------------------------------------------------------------------------

def _nq_call(details: dict[str, Any]) -> str:
    """``NQ call JOIN_ID 0xA1 (EE, UK_Q3_2026, Voice, NSA)``: the call an event touched, by its key when it has no JOIN_ID."""
    if not isinstance(details, dict):
        return 'NQ call'
    about = ', '.join(str(details[key]) for key in ('operator', 'campaign', 'call_type', 'nr_mode') if details.get(key))
    name = f"JOIN_ID {details['join_id']}" if details.get('join_id') else f"key {details.get('call_key') or '?'}"
    return f'NQ call {name}' + (f' ({about})' if about else '')


def _nq_filters(filters: Any) -> str:
    if not isinstance(filters, dict) or not filters:
        return 'no filter'
    return '; '.join(f'{field_label(name)} {value_text(value)}' for name, value in filters.items())


def _quoted(text: Any) -> str:
    return f'"{value_text(text)}"' if text else 'an empty text'


def _nq_moves(changes: Any) -> str:
    """``Status New → Under Planning; Team none → Ops``: each value a call changed, from what to what."""
    if not isinstance(changes, dict):
        return ''
    parts = []
    for name, values in changes.items():
        if isinstance(values, (list, tuple)) and len(values) == 2 and not isinstance(values[0], (list, dict)):
            parts.append(f"{name} {value_text(values[0]) if values[0] not in (None, '') else 'none'} → "
                         f"{value_text(values[1]) if values[1] not in (None, '') else 'none'}")
        else:
            parts.append(f'{name} {value_text(values)}')
    return '; '.join(parts)


def _nq_call_update(details: dict[str, Any]) -> str:
    moves = _nq_moves(details.get('changes'))
    return (f'{_nq_call(details)} changed: {moves}.' if moves
            else f"{_nq_call(details)} changed ({value_text(details.get('fields'))}).")


def _nq_bulk_update(details: dict[str, Any]) -> str:
    text = f"{details.get('changed')} of {details.get('selected')} selected NQ calls changed"
    moves = '; '.join(f'{name}: {value_text(values)}' for name, values in (details.get('changes') or {}).items())
    text += f': {moves}' if moves else f" ({value_text(details.get('fields'))})"
    return text + (f". JOIN_IDs {value_text(details['join_ids'])}." if details.get('join_ids') else '.')


def _nq_l3_maps(details: dict[str, Any]) -> str:
    scope = details.get('scope') or ''
    found = (f"{details.get('calls', 0)} NQ calls, {details.get('sessions', 0)} sessions of Layer3 Logs shown as "
             f"{details.get('mode') or 'points'} at zoom {details.get('zoom')}")
    layers = f"layers {value_text(details.get('layers'))}" + (f", grid of {details['grid']}" if details.get('grid') else '')
    extra = ', '.join(f'{details[key]} {label}' for key, label in (('routes', 'routes'), ('sites', 'sites'), ('tests', 'RSRP / SINR samples'))
                      if details.get(key))
    took = f" ({details['seconds']} s)" if details.get('seconds') is not None else ''
    if scope == 'calls around a call':
        return (f"Map of the NQ call JOIN_ID {details.get('around_join_id') or '?'}: Layer3 Logs of the "
                f"{details.get('nq_calls_around', 0)} NQ calls around it read ({layers}; {details.get('sessions', 0)} sessions){took}.")
    if scope == 'map of a site':
        site = details.get('site') if isinstance(details.get('site'), dict) else {}
        about = ', '.join(f'{label} {site[key]}' for key, label in (('network', 'network'), ('operator', 'operator'), ('campaign', 'campaign'),
                                                                     ('radius_km', 'radius km'), ('opened_from', 'opened from')) if site.get(key))
        placed = ('' if 'site_in_inventory' not in details else
                  '; placed by the inventory' if details['site_in_inventory'] else '; not in the inventory')
        return (f"Map of the site {site.get('site_id') or '?'} shown in NQ Maps ({about}): {details.get('nq_calls_of_the_site', 0)} NQ calls "
                f"of the site{placed}; {found}; {layers}" + (f'; {extra}' if extra else '') + f'{took}.')
    return (f"NQ Maps shown for {_nq_filters(details.get('filters'))}: {found}; {layers}" + (f'; {extra}' if extra else '') + f'{took}.')


def _nq_failed(subject: str) -> Callable[[dict[str, Any]], str]:
    def describe(details: dict[str, Any]) -> str:
        return f"{subject(details)} failed: {details.get('error') or 'unknown error'}."
    return describe


def _nq_export(kind: str) -> Callable[[dict[str, Any]], str]:
    def describe(details: dict[str, Any]) -> str:
        options = (f", by {details['granularity']}" if details.get('granularity') else '') + (
            '' if details.get('include_suggestions') is not False else ', without the suggested root causes')
        return f"{kind} exported to {details.get('file')} ({_nq_filters(details.get('filters'))}{options})."
    return describe


_NQ_DESCRIBERS: dict[str, Callable[[Any], str]] = {
    'nq_page_opened': lambda details: f"Non-Qualified Calls opened (workspace {details.get('workspace')}).",
    'nq_calls_listed': lambda details: (
        f"NQ calls listed with {_nq_filters(details.get('filters'))} (sorted by {details.get('sort')}, page {details.get('page')} of "
        f"{details.get('page_size')} calls" + (f", to show the call {details['located_call']}" if details.get('located_call') else '') + ').'),
    'nq_calls_scope_only': lambda details: f"NQ Calls in Scope Only switched {'on' if details.get('in_scope') else 'off'}.",
    'nq_call_opened': lambda details: f"{_nq_call(details)} opened" + (
        f": {', '.join(f'{name} {details[name]}' for name in ('status', 'team', 'analyst') if details.get(name))}."
        if any(details.get(name) for name in ('status', 'team', 'analyst')) else '.'),
    'nq_call_update': _nq_call_update,
    'nq_calls_bulk_update': _nq_bulk_update,
    'nq_comment_add': lambda details: f"Comment added to the {_nq_call(details)}: {_quoted(details.get('text'))}.",
    'nq_comment_edit': lambda details: (
        f"Comment {details.get('comment_id')}" + (f" of {details['author']}" if details.get('author') else '')
        + (f" on the {_nq_call(details)}" if details.get('call_key') else '') + ' edited'
        + (f": {_quoted(details.get('before'))} → {_quoted(details.get('text'))}." if 'text' in details else '.')),
    'nq_comment_delete': lambda details: (
        f"Comment {details.get('comment_id')}" + (f" of {details['author']}" if details.get('author') else '')
        + (f" on the {_nq_call(details)}" if details.get('call_key') else '') + ' deleted'
        + (f": {_quoted(details.get('text'))}." if 'text' in details else '.')),
    'nq_call_map': lambda details: (
        f"Map of the area of the {_nq_call(details)} opened: radius {details.get('radius_km')} km"
        f"{' (of its groups)' if details.get('radius_of_the_groups') else ''}, tests {details.get('tests')}, campaigns "
        f"{value_text(details.get('selected_campaigns'))}; {details.get('sites', 0)} sites, {details.get('nq_calls_around', 0)} NQ calls and "
        f"{details.get('tests_around', 0)} tests around" + (f"; to check: {value_text(details['to_check'])}" if details.get('to_check') else '')
        + (f"; worth a look: {value_text(details['worth_a_look'])}" if details.get('worth_a_look') else '')
        + (f" ({details['seconds']} s)." if details.get('seconds') is not None else '.')),
    'nq_call_map_failed': _nq_failed(lambda details: f"Map of the area of the {_nq_call(details)}"),
    'nq_call_l3_layers': lambda details: (
        f"Layer3 Logs of the {_nq_call(details)} read for its map: "
        + (f"UEs {value_text(details.get('ues'))}, {sum((details.get('points') or {}).values())} points"
           if details.get('ues') else 'no session of the call') + (f" ({details['seconds']} s)." if details.get('seconds') is not None else '.')),
    'nq_call_l3_layers_failed': _nq_failed(lambda details: f"Layer3 Logs of the {_nq_call(details)}"),
    'nq_call_l3_record_viewed': lambda details: (
        f"Record of the Layer3 Logs of the {_nq_call(details)} viewed (CDR {details.get('dataset_id')}, row {details.get('row')}"
        + ''.join(f", {name} {details[name]}" for name in ('time', 'event', 'message') if details.get(name)) + ').'),
    'nq_l3_maps': _nq_l3_maps,
    'nq_l3_maps_failed': _nq_failed(lambda details: f"NQ Maps for {_nq_filters(details.get('filters'))} at zoom {details.get('zoom')}"),
    'nq_queue_take': lambda details: (
        f"{details.get('taken')} of {details.get('selected')} selected NQ calls of the queues taken as their analyst"
        + (f" (team {details['team']})" if details.get('team') else '')
        + (f": JOIN_IDs {value_text(details['join_ids'])}" if details.get('join_ids') else '')
        + (f"; skipped {value_text(details['skipped'])}" if details.get('skipped') else '') + '.'),
    'nq_queue_assign': lambda details: (
        f"{details.get('changed')} of {details.get('selected')} selected NQ calls of the queues assigned ({value_text(details.get('changes'))})"
        + (f": JOIN_IDs {value_text(details['join_ids'])}" if details.get('join_ids') else '')
        + (f"; skipped {value_text(details['skipped'])}" if details.get('skipped') else '') + '.'),
    'nq_prioritization_recalculate': lambda details: 'NQ Prioritization asked to be calculated again (in the background).',
    'nq_prioritization_defaults': lambda details: f"NQ Prioritization Rules restored to their defaults (strategy {details.get('strategy')}).",
    'nq_calls_reindex_queued': lambda details: 'NQ calls of every CDR asked to be indexed again (in the background).',
    'nq_catalog_export': lambda details: f"NQ Analysis Center catalog exported to {details.get('file')}.",
    'nq_catalog_import': lambda details: f"NQ Analysis Center catalog imported from {details.get('file')}.",
    'nq_catalog_import_preview': lambda details: f"NQ Analysis Center catalog file {details.get('file')} previewed before importing it.",
    'nq_template_download': lambda details: f"Template of the {details.get('template')} downloaded ({details.get('file')}).",
    'nq_rca_import_preview': lambda details: (
        f"Ericsson RCA results file {details.get('file')} previewed: {details.get('rows')} rows, {details.get('matched')} matching an NQ call, "
        f"{details.get('new')} new" + (f"; not in the Root Cause Catalog: {value_text(details['unmapped'])}" if details.get('unmapped') else '') + '.'),
    'nq_rca_import': lambda details: (
        f"Ericsson RCA results imported from {details.get('file')}: {details.get('rows')} rows, {details.get('matched')} matching an NQ call"
        + (', replacing the previous results' if details.get('replace') else '')
        + (f"; added to the Root Cause Catalog: {value_text(details['added_to_catalog'])}" if details.get('added_to_catalog') else '') + '.'),
    'nq_analyses_import_preview': lambda details: (
        f"Analyses file {details.get('file')} of the previous tool previewed before importing it"
        + (' (overwriting the values the calls have)' if details.get('overwrite') else '') + '.'),
    'nq_calls_export': _nq_export('NQ calls'),
    'nq_summary_export_powerpoint': _nq_export('Executive Summary, Progress Status and Root Cause Analysis (PowerPoint)'),
    'nq_summary_export_word': _nq_export('Executive Summary, Progress Status and Root Cause Analysis (Word)'),
    'nq_map_levels_saved': lambda details: f"Map Levels saved: {value_text(details.get('changes'))}.",
    'nq_dta_rca_calculated': lambda details: f"DT Analyzer RCA calculated again for {details.get('rows')} rows after its rules were saved.",
}


_DESCRIBERS: dict[str, Callable[[Any], str]] = {
    'demo_mode_started': lambda details: (f"Demo Mode started until {details.get('expected_end')}, with access for "
                                          f"{_demo_users(details)}."),
    'demo_mode_changed': _demo_mode_changed,
    'demo_mode_extended': lambda details: (f"Demo Mode extended by {details.get('extended_by_minutes')} minutes, until "
                                           f"{(details.get('changes') or {}).get('expected_end', ['', ''])[1]}."),
    'demo_mode_reminder_postponed': lambda details: (f"Demo Mode reminder postponed until "
                                                     f"{(details.get('changes') or {}).get('remind_at', ['', ''])[1]}."),
    'demo_mode_ended': lambda details: (f"Demo Mode ended (started by {details.get('started_by')} at {details.get('started_at')}, "
                                        f"expected end {details.get('expected_end')})."),
    'demo_mode_user_warned': lambda details: (f"Warned that {details.get('started_by')} started Demo Mode and signed out "
                                              f"soon{'' if details.get('page_open') else ' (no page open)'}."),
    'demo_mode_user_signed_out': lambda details: (
        f"Signed out by Demo Mode {_DEMO_SIGN_OUT_REASONS.get(str(details.get('reason')), str(details.get('reason')))}"
        f"{' (unsaved: ' + ', '.join(details['unsaved_changes_before_leaving']) + ')' if details.get('unsaved_changes_before_leaving') else ''}."),
    'demo_mode_sign_in_refused': lambda details: f"Sign-in refused: Demo Mode started by {details.get('started_by')} is on.",
    'demo_mode_change_refused': lambda details: (f"{details.get('method')} {details.get('path')} refused: the user is being "
                                                 'signed out by Demo Mode.'),
    'email_sent': _email(True),
    'email_failed': _email(False),
    'change_email': lambda details: _sentence('Email address', [
        f"{value_text(details['changes']['email'][0]) or 'none'} → {value_text(details['changes']['email'][1]) or 'none'}"]),
    'password_reset_requested': lambda details: f"Link to choose a new password emailed to {details.get('email')}.",
    'password_reset': lambda details: 'Password changed with the link of a password reset email.',
    'download_reporting_file_link': lambda details: (
        f"{details.get('file')} of a report{' (run ' + str(details['run_id']) + ')' if details.get('run_id') else ''} downloaded "
        'from the link of its email.'),
    'view_reporting_file_link': lambda details: (
        f"{details.get('file')} of the report {details.get('name')} (run {details.get('run_id')}) viewed online from the link of its "
        'email.'),
    'report_email_link_denied': lambda details: (
        f"Link of a report email to {details.get('file')} refused: no access to the workspace of the report."),
    'operator_mapping_assign': _mapping_assign('Operator'),
    'operator_name_comments': _name_comments,
    'vendor_mapping_assign': _mapping_assign('Vendor'),
    'application_started': _application_started,
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
    **_NQ_DESCRIBERS,
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
PUBLIC_EVENT_PAGES = (('sign-in', 'Sign-in'), ('access-request', 'Access request'), ('ticket-center', 'Ticket Center'), ('page', 'Page'))
_SERVER_ACTIONS = {
    'scheduler': {'reporting_scheduler_error'},
    'idle': {'precompute_design_charts', 'prewarm_design_cache', 'prewarm_design_cache_failed', 'nq_calls_reindexed',
             'map_area_fill_failed'},
    'startup': {'application_started', 'recover_interrupted_background_jobs', 'recover_interrupted_saved_filters',
                'recover_inconsistent_datasets', 'resume_interrupted_dataset', 'migrate_app_event_users', 'nq_call_keys_upgraded',
                'assign_unknown_creators', 'assign_unknown_creators_failed', 'resume_reporting_job_run',
                'stop_interrupted_reporting_job_run', 'fail_interrupted_reporting_job_run', 'workspace_cache_folders_moved',
                'retired_report_jobs_dropped', 'reporting_jobs_became_report_schedules'},
    'background': {'process_dataset', 'process_dataset_failed', 'l3_dt_logs_processed', 'analyze_dataset_failed', 'analyze_dataset_warning',
                   'map_dataset_vendors', 'map_dataset_vendors_failed', 'map_dataset_regions', 'map_dataset_regions_failed',
                   'vendor_mapping_skipped', 'clear_dataset_vendors', 'clear_dataset_vendors_failed', 'chart_set_rendering_completed',
                   'chart_set_rendering_warning', 'chart_set_published', 'chart_set_generation_failed', 'export_design_ppt_failed',
                   'export_design_ppt_warning', 'export_netcheck_cdr_report_failed', 'scoring_calculation_failed',
                   'sync_combined_cdr_tables_completed', 'sync_combined_cdr_tables_failed', 'reporting_job_run',
                   'generate_presentations', 'generate_presentations_failed', 'email_sent', 'email_failed'},
}
_SERVER_ACTION_PREFIXES = (('scheduled_database_backup_', 'scheduler'),)
_REMOTE_ACTION_PREFIXES = ('incoming_server_transfer_', 'incoming_transfer_import_', 'incoming_transfer_request_')
_PUBLIC_ACTIONS = {'access_request': 'access-request', 'access_change_request': 'access-request', 'login': 'sign-in',
                   'logout': 'sign-in', 'password_reset_requested': 'sign-in', 'password_reset': 'sign-in',
                   'download_reporting_file_link': 'page', 'demo_mode_sign_in_refused': 'sign-in'}
# The module of the events of earlier versions, which did not record the page they came from (by action, or its start).
_MODULE_ACTIONS = (
    ('non-qualified-calls', ('nq_',)),
    ('network-insights', ('network_insights_', 'export_network_insights_')),
    ('scoring', ('scoring_', 'save_scoring_', 'export_scoring_', 'import_scoring_', 'delete_scoring_')),
    ('ticket-center', ('ticket_',)),
    ('assistant', ('assistant_',)),
    ('ppt-designer', ('save_design', 'delete_design', 'rename_design', 'export_design_', 'download_design_ppt',
                        'delete_all_design_ppts', 'stop_design_ppt_job', 'change_design_template',
                        'update_design_chart_template', 'interrupt_design_preparation')),
    ('reporting', ('save_reporting_job', 'run_reporting_job', 'delete_reporting_job', 'download_reporting_job_',
                   'rerun_reporting_job_run', 'stop_reporting_job_run', 'bundle_report_templates_design_nr_modes',
                   'bundle_report_template_')),
    ('builders', ('run_query_builder', 'save_query_builder', 'update_query_builder', 'delete_query_builder',
                  'export_query_builder_', 'cancel_query_builder_run')),
    ('admin', ('create_user', 'update_user', 'delete_user', 'bulk_update_users', 'reset_user_password', 'create_modules_profile',
               'update_modules_profile', 'update_module_profile', 'set_default_modules_profile', 'delete_modules_profile',
               'create_workspace_group', 'update_workspace_group', 'delete_workspace_group', 'update_user_group',
               'save_interface_settings', 'database_table_', 'cleanup_database', 'save_backup_selection',
               'save_scheduled_backup_settings', 'start_manual_database_', 'create_backup_directory', 'import_package_',
               'export_package_', 'download_export_package', 'accept_server_transfer', 'reject_server_transfer',
               'outgoing_server_transfer_', 'stop_outgoing_server_transfer', 'delete_recovered_transfer_package',
               'accept_transfer_request', 'reject_transfer_request', 'outgoing_transfer_request_',
               'import_recovered_transfer_package', 'reset_application', 'admin_notices_seen', 'create_report_template',
               'save_report_template', 'delete_report_template', 'rename_report_template', 'duplicate_report_template',
               'import_report_template', 'export_report_template', 'activate_report_template', 'change_report_template_type',
               'copy_report_template_content', 'report_templates_nr_mode_merged')),
    ('config', ('operator_mapping_', 'vendor_mapping_', 'campaign_map', 'main_cities_save', 'save_workspace_calculated_dimensions',
                'export_workspace_calculated_dimensions', 'import_workspace_calculated_dimensions',
                'rematerialize_workspace_auto_calculated_fields', 'save_auto_calculated_field', 'delete_auto_calculated_field',
                'reorder_auto_calculated_fields', 'auto_calculated_field_values_failed', 'save_application_configuration',
                'save_email_delivery', 'email_delivery_test_', 'map_areas_', 'network_serving_networks_saved',
                'network_spectrum_holdings_saved', 'cdr_field_dictionary_')),
    ('workspace', ('upload_dataset', 'cancel_dataset_upload', 'delete_dataset', 'rename_dataset', 'reprocess_dataset', 'l3_dt_logs_',
                   'retry_dataset', 'stop_dataset', 'reorder_datasets', 'update_dataset_', 'queue_dataset_mappings', 'queue_vendor_',
                   'queue_region_', 'stop_vendor_', 'stop_region_', 'create_workspace', 'open_workspace', 'close_workspace',
                   'delete_workspace', 'rename_workspace', 'duplicate_workspace', 'set_workspace_cdr_type', 'starter_content_')),
    # PPT Reporting (old), a module the tool no longer has: its events stay in App Events under its name (RETIRED_MODULES).
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
