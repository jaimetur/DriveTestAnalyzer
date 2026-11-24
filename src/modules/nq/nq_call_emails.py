"""Emails of the follow-up of the Non-Qualified Calls (ticket #187).

The Analyst and the Reviewer of a call (ticket #199), and the users of Email Every NQ Call Change To, are told when every
field of the analysts of the call is filled, when one of its key fields changes (its NQ Call Status, the status of a phase,
its Analyst, Reviewer, Root Domain, Root Category, Root Cause or Initial Classification) and when somebody comments on it:
one email per recipient for each change (a bulk change or a copy to a group lists its calls in one email), with the
follow-up of each call, what changed, the new comments, the fields filled by section and those still empty, and a link
that opens the call.

Each user chooses how often (ticket #194): at once, or in a summary every hour, every day at 17:00 or every Friday at
17:00 (the default is the daily summary), or never; and whether it is told of its own changes too (not by default). The
changes waiting for a summary are kept in ``nq_email_queue`` (application database), so a restart loses none; a summary
tells of each call once, with each status from its value before the first change to its value after the last one.
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any, Iterable

from src.modules.core import notifications
from src.modules.core.email_delivery import EVERY_NQ_CALL_KEY, email_delivery_settings

# A call of more is listed by its JOIN_ID only: an email stays readable (and under the size a flow accepts).
DETAILED_CALLS = 10
LISTED_CALLS = 200

# How often a user is emailed of the NQ calls (ticket #194), and when the summaries go (local time of the server).
FREQUENCIES = notifications.EMAIL_FREQUENCIES
DEFAULT_FREQUENCY = 'daily'
SUMMARY_NAMES = notifications.SUMMARY_NAMES
last_summary_time = notifications.last_summary_time
QUEUE_TABLE = 'nq_email_queue'
QUEUE_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {QUEUE_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    workspace TEXT NOT NULL,
    call_key TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    event_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{QUEUE_TABLE}_username ON {QUEUE_TABLE}(username);
"""


def frequency_of(preference: dict[str, Any] | None) -> str:
    """The frequency a user chose for the NQ calls, else the default (a daily summary)."""
    return notifications.chosen_frequency((preference or {}).get('nq_frequency'), DEFAULT_FREQUENCY)


def call_events(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]], report: dict[str, dict[str, list[str]]],
                labels: dict[str, str], watched: Iterable[str]) -> dict[str, dict[str, Any]]:
    """The calls to tell of, by call: those whose analyst fields were all filled by the change (``completed``) and those whose
    NQ Call Status or the status of a phase changed (``changes``: label, before, after). ``watched`` are the keys of the
    report of those statuses (``status``, ``field:<key>``)."""
    watched = set(watched)
    events: dict[str, dict[str, Any]] = {}
    for key, state in after.items():
        changes = [(labels.get(name, name), old, new) for name, (old, new) in (report.get(key) or {}).items()
                   if name in watched and old != new]
        completed = bool(state['complete'] and not (before.get(key) or {}).get('complete'))
        if changes or completed:
            events[key] = {'state': state, 'changes': changes, 'completed': completed}
    return events


def comment_events(state: dict[str, Any], author: str, body: str, created_at: str = '') -> dict[str, dict[str, Any]]:
    """The event of a new comment on a call (ticket #199): its follow-up and the comment."""
    return {state['call_key']: {'state': state, 'changes': [], 'completed': False,
                                'comments': [{'author': str(author or ''), 'body': str(body or ''), 'created_at': str(created_at or '')}]}}


def recipients_of(events: dict[str, dict[str, Any]], every: Iterable[str]) -> dict[str, list[str]]:
    """The calls each recipient (username in lower case) is told of: its Analyst and its Reviewer (an Analyst without an
    account has no address and is told of none), and the users of every change."""
    everyone = [str(name).casefold() for name in every if str(name).strip()]
    told: dict[str, list[str]] = {}
    for key, event in events.items():
        for username in [str(event['state'].get('analyst') or '').casefold(), str(event['state'].get('reviewer') or '').casefold(),
                         *everyone]:
            if username:
                told.setdefault(username, [])
                if key not in told[username]:
                    told[username].append(key)
    return told


# The width of the labels of every table of an email, so the values of all its tables line up.
LABEL_WIDTH = '40%'
HEADING_COLOUR = '#1E61A3'


def _table(rows: list[tuple[str, str]], title: str, colour: str = '') -> str:
    """A table of labels and values (HTML) under a heading in the colour of its section, a band of that colour on its
    left; every table has the same label column, so the values of the email line up."""
    colour = colour or HEADING_COLOUR
    heading = (f'<p style="margin:22px 0 6px;padding:5px 10px;border-left:4px solid {colour};background:{colour}14;font-size:12px;'
               f'font-weight:bold;letter-spacing:1px;text-transform:uppercase;color:{colour}">{html.escape(title)}</p>')
    cells = ''.join(
        f'<tr><td width="{LABEL_WIDTH}" style="width:{LABEL_WIDTH};padding:7px 14px 7px 10px;border-top:1px solid #e5e9ee;color:#6b7280;'
        f'vertical-align:top">{html.escape(label)}</td><td style="padding:7px 0;border-top:1px solid #e5e9ee;vertical-align:top;'
        f'overflow-wrap:anywhere">{value}</td></tr>' for label, value in rows)
    return (heading + '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;table-layout:fixed;width:100%;font-size:14px;border-bottom:1px solid #e5e9ee">{cells}</table>')


def _call_title(state: dict[str, Any]) -> str:
    parts = [state.get('join_id') or state['call_key'], state.get('operator'), state.get('campaign'),
             str(state.get('service') or '').title()]
    return ' · '.join(part for part in parts if part)


def _call_part(event: dict[str, Any], base_url: str, names: dict[str, str], *, detailed: bool) -> str:
    state = event['state']
    link = f"{base_url}/non-qualified-calls#call={state['call_key']}" if base_url else ''
    title = html.escape(_call_title(state))
    heading = (f'<p style="margin:22px 0 4px;font-size:16px;font-weight:bold">'
               + (f'<a href="{html.escape(link, quote=True)}" style="color:#1E61A3">{title}</a>' if link else title) + '</p>')
    total = len(state['filled']) + len(state['missing'])
    progress = f"{len(state['filled'])}/{total} analyst fields filled" + (' · Complete' if state['complete'] else '')
    what = []
    if event['completed']:
        what.append(notifications.callout('Every field filled', 'Every field of the analysts of this call has a value.',
                                          colour='#2E8B57', background='#EEF8F1'))
    for comment in event.get('comments') or []:
        author = names.get(str(comment.get('author') or '').casefold(), str(comment.get('author') or ''))
        text = html.escape(str(comment.get('body') or '')).replace('\n', '<br>')
        when = str(comment.get('created_at') or '').replace('T', ' ')[:16]
        what.append(_table([('By', html.escape(author or '—') + (f' · {html.escape(when)}' if when else '')), ('Comment', text)],
                           'New comment', '#1E61A3'))
    if event['changes']:
        what.append(_table(
            [(label, f'{html.escape(old or "—")} → <strong>{html.escape(new or "—")}</strong>') for label, old, new in event['changes']],
            'What changed', '#B0234F'))
    person = lambda username: html.escape(names.get(str(username).casefold(), str(username)) if username else '—')  # noqa: E731
    follow = _table([
        ('NQ Call Status', html.escape(state['status'] or '—')), ('Team', html.escape(state['team'] or '—')),
        ('Analyst', person(state['analyst'])), ('Reviewer', person(state['reviewer'])),
        ('Root Category', html.escape(state['root_category'] or '—')), ('Root Cause', html.escape(state['root_cause'] or '—')),
        ('Started', html.escape(str(state.get('start_time') or '').replace('T', ' ')[:19] or '—')),
        ('Analyst fields', html.escape(progress))], 'Follow-up')
    parts = [heading, *what, follow]
    colours = state.get('section_colors') or {}
    if detailed:
        by_section: dict[str, list[tuple[str, str]]] = {}
        for section, label, value in state['filled']:
            by_section.setdefault(section, []).append((label, value))
        for section, rows in by_section.items():
            parts.append(_table([(label, html.escape(value)) for label, value in rows], f'Filled · {section}', colours.get(section, '')))
        if state['missing']:
            missing: dict[str, list[str]] = {}
            for section, label in state['missing']:
                missing.setdefault(section, []).append(label)
            parts.append(_table([(section, html.escape(', '.join(labels))) for section, labels in missing.items()], 'Still empty', '#C2410C'))
    return ''.join(parts)


def call_thread(workspace: str, call_key: str) -> str:
    """The conversation of the emails of one call, so mail clients (Outlook too) put them together."""
    return f'nq-call-{workspace}-{call_key}'


def _actions(events: dict[str, dict[str, Any]], keys: list[str]) -> list[str]:
    """What happened to some calls, for the title of their email."""
    found = [('Completed', any(events[key]['completed'] for key in keys)), ('Changed', any(events[key]['changes'] for key in keys)),
             ('New comment', any(events[key].get('comments') for key in keys))]
    return [name for name, happened in found if happened]


def call_email(app_name: str, workspace: str, actor_name: str, events: dict[str, dict[str, Any]], keys: list[str], base_url: str,
               names: dict[str, str]) -> tuple[str, str]:
    """The subject and HTML of the email of some calls of a change. The email of one call keeps the same subject for
    every change (what happened leads its title), so its emails are one conversation."""
    shown = keys[:LISTED_CALLS]
    actions = _actions(events, shown)
    if len(shown) == 1:
        title = _call_title(events[shown[0]]['state'])
    else:
        title = f'{len(keys)} NQ calls'
    only_comments = all(not events[key]['changes'] and not events[key]['completed'] for key in shown)
    intro = (f'<p>{html.escape(actor_name)} {"commented on" if only_comments else "changed"} '
             f'{"this NQ call" if len(keys) == 1 else f"{len(keys)} NQ calls"} of the workspace <strong>{html.escape(workspace)}</strong>.</p>')
    parts = [intro, *(_call_part(events[key], base_url, names, detailed=index < DETAILED_CALLS) for index, key in enumerate(shown))]
    if len(keys) > len(shown):
        parts.append(f'<p>And {len(keys) - len(shown)} more calls.</p>')
    link = ('Open the call', f"{base_url}/non-qualified-calls#call={shown[0]}") if base_url and len(shown) == 1 else (
        ('Open Non-Qualified Calls', f'{base_url}/non-qualified-calls') if base_url else None)
    subject = (f'NQ Call {title} ({workspace})' if len(shown) == 1
               else f"NQ Calls - {' & '.join(actions) or 'Changed'} - {title} ({workspace})")
    return subject, notifications.email_page(app_name, title, parts, link=link, action=actions)


def notify_call_changes(app_repository: Any, app_name: str, workspace: str, actor: str, events: dict[str, dict[str, Any]],
                        base_url: str) -> int:
    """Email the reviewer of each call of ``events`` and the users of Email Every NQ Call Change To; how many emails were
    queued. Never fails the change it tells of: a failure is recorded in App Events."""
    if not events:
        return 0
    try:
        settings = email_delivery_settings(app_repository)
        if not settings['configured'] or not settings.get('notify_nq_calls'):
            return 0
        told = recipients_of(events, settings.get(EVERY_NQ_CALL_KEY) or [])
        emails = app_repository.user_emails(told)
        preferences = app_repository.email_preferences(told)
        names = notifications.people_names(app_repository)
        actor_name = names.get(str(actor).casefold(), str(actor))
        base = str(base_url or '').rstrip('/')
        sent = 0
        waiting: dict[str, list[str]] = {}
        for username, keys in told.items():
            address = emails.get(username)
            preference = preferences.get(username) or {}
            frequency = frequency_of(preference)
            # Nobody is told of its own changes unless it asked to be; a user who chose Never is told of none.
            if not address or frequency == 'off' or (username == str(actor).casefold() and not preference.get('nq_own_changes')):
                continue
            if frequency != 'immediate':
                waiting[username] = keys
                continue
            subject, body = call_email(app_name, workspace, actor_name, events, keys, base, names)
            notifications.deliver(app_repository, kind='nq_call', recipients=[address], subject=subject, html_body=body, actor=actor,
                                  details={'workspace': workspace, 'recipient': username, 'calls': len(keys),
                                           'join_ids': [events[key]['state'].get('join_id') or key for key in keys[:20]]},
                                  switch='notify_nq_calls', thread=call_thread(workspace, keys[0]) if len(keys) == 1 else '')
            sent += 1
        if waiting:
            queue_for_summaries(app_repository, workspace, actor, base, events, waiting)
        return sent
    except Exception as exc:  # noqa: BLE001 - an email never breaks the change it tells of.
        app_repository.try_add_log(actor or 'system', 'email_failed', json.dumps(
            {'kind': 'nq_call', 'workspace': workspace, 'calls': len(events), 'error': str(exc)}, ensure_ascii=False))
        return 0


def _queue_connection(app_repository: Any):
    """The application database, where the changes wait for their summaries."""
    return app_repository.global_connection()


def queue_for_summaries(app_repository: Any, workspace: str, actor: str, base_url: str, events: dict[str, dict[str, Any]],
                        waiting: dict[str, list[str]]) -> int:
    """Keep the changes of ``events`` for the summaries of the users of ``waiting`` (username: call keys)."""
    now = notifications.queued_at()
    rows = [(username, workspace, key, str(actor or ''), base_url,
             json.dumps({'state': events[key]['state'], 'changes': events[key]['changes'], 'completed': events[key]['completed'],
                         'comments': events[key].get('comments') or []},
                        ensure_ascii=False, default=str), now)
            for username, keys in waiting.items() for key in keys]
    with _queue_connection(app_repository) as conn:
        conn.executescript(QUEUE_SCHEMA)
        conn.executemany(f'INSERT INTO {QUEUE_TABLE} (username, workspace, call_key, actor, base_url, event_json, created_at) '
                         'VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
    return len(rows)


def merge_events(rows: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """The calls of some queued changes (oldest first), each told once: its latest follow-up, each status from its value
    before the first change to its value after the last one (left out when it came back), and completed when it was
    completed and still is; with the users who made the changes."""
    merged: dict[str, dict[str, Any]] = {}
    actors: list[str] = []
    for row in rows:
        event = json.loads(row['event_json'])
        if row['actor'] and row['actor'] not in actors:
            actors.append(row['actor'])
        current = merged.setdefault(row['call_key'], {'state': event['state'], 'changes': {}, 'completed': False, 'comments': []})
        current['comments'].extend(event.get('comments') or [])
        current['state'] = event['state']
        current['completed'] = current['completed'] or bool(event.get('completed'))
        for label, old, new in event.get('changes') or []:
            if label in current['changes']:
                current['changes'][label][1] = new
            else:
                current['changes'][label] = [old, new]
    calls = {}
    for key, event in merged.items():
        changes = [(label, old, new) for label, (old, new) in event['changes'].items() if old != new]
        completed = event['completed'] and bool(event['state'].get('complete'))
        if changes or completed or event['comments']:
            calls[key] = {'state': event['state'], 'changes': changes, 'completed': completed, 'comments': event['comments']}
    return calls, actors


def summary_email(app_name: str, workspace: str, frequency: str, events: dict[str, dict[str, Any]], actors: list[str],
                  base_url: str, names: dict[str, str]) -> tuple[str, str]:
    """The subject and HTML of the summary of the NQ calls changed since the previous one."""
    keys = list(events)
    shown = keys[:LISTED_CALLS]
    period = notifications.SUMMARY_PERIODS.get(frequency, 'the last period')
    people = ', '.join(html.escape(names.get(str(actor).casefold(), str(actor))) for actor in actors) or 'the analysts'
    count = 'this NQ call' if len(keys) == 1 else f'{len(keys)} NQ calls'
    intro = (f'<p>The changes of {period} in {count} of the workspace <strong>{html.escape(workspace)}</strong>, made by {people}: '
             'each status from its value before the first change to its value after the last one.</p>')
    parts = [intro, *(_call_part(events[key], base_url, names, detailed=index < DETAILED_CALLS) for index, key in enumerate(shown))]
    if len(keys) > len(shown):
        parts.append(f'<p>And {len(keys) - len(shown)} more calls.</p>')
    actions = _actions(events, keys)
    title = f"{SUMMARY_NAMES.get(frequency, 'NQ')} summary · {len(keys)} NQ call{'s' if len(keys) != 1 else ''}"
    link = (('Open the call', f'{base_url}/non-qualified-calls#call={shown[0]}') if len(shown) == 1 else
            ('Open Non-Qualified Calls', f'{base_url}/non-qualified-calls')) if base_url else None
    subject = f"NQ Calls - {SUMMARY_NAMES.get(frequency, 'NQ')} summary - {len(keys)} call{'s' if len(keys) != 1 else ''} ({workspace})"
    return subject, notifications.email_page(app_name, title, parts, link=link, action=actions)


def send_due_summaries(app_repository: Any, app_name: str, now: datetime | None = None) -> int:
    """Email each user the summary of the NQ calls whose time has come (every hour, day or Friday at 17:00, as it chose);
    how many summaries were sent. A user's changes wait while the email cannot be sent, and are dropped once it chose
    Never, has no address or NQ call emails are switched off."""
    now = (now or datetime.now()).astimezone()
    settings = email_delivery_settings(app_repository)
    with _queue_connection(app_repository) as conn:
        conn.executescript(QUEUE_SCHEMA)
        rows = [dict(row) for row in conn.execute(f'SELECT * FROM {QUEUE_TABLE} ORDER BY id').fetchall()]
    if not rows or not settings['configured']:
        return 0
    if not settings.get('notify_nq_calls'):
        _drop(app_repository, [row['id'] for row in rows])
        return 0
    by_user: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_user.setdefault(row['username'], []).append(row)
    preferences = app_repository.email_preferences(by_user)
    emails = app_repository.user_emails(by_user)
    names = notifications.people_names(app_repository)
    sent = 0
    for username, user_rows in by_user.items():
        frequency = frequency_of(preferences.get(username))
        address = emails.get(username)
        if frequency == 'off' or not address:
            _drop(app_repository, [row['id'] for row in user_rows])
            continue
        due = notifications.due_before(frequency, now)
        ready = [row for row in user_rows if row['created_at'] <= due]
        by_workspace: dict[str, list[dict[str, Any]]] = {}
        for row in ready:
            by_workspace.setdefault(row['workspace'], []).append(row)
        for workspace, workspace_rows in by_workspace.items():
            events, actors = merge_events(workspace_rows)
            ids = [row['id'] for row in workspace_rows]
            if not events:
                _drop(app_repository, ids)
                continue
            base = str(workspace_rows[-1]['base_url'] or '').rstrip('/')
            subject, body = summary_email(app_name, workspace, frequency, events, actors, base, names)
            delivered = notifications.deliver(
                app_repository, kind='nq_call_summary', recipients=[address], subject=subject, html_body=body, actor='system',
                details={'workspace': workspace, 'recipient': username, 'frequency': frequency, 'calls': len(events),
                         'changes': len(workspace_rows), 'join_ids': [event['state'].get('join_id') or key for key, event in list(events.items())[:20]]},
                switch='notify_nq_calls', background=False)
            if delivered:
                _drop(app_repository, ids)
                sent += 1
    return sent


def _drop(app_repository: Any, ids: list[int]) -> None:
    if ids:
        with _queue_connection(app_repository) as conn:
            conn.executemany(f'DELETE FROM {QUEUE_TABLE} WHERE id = ?', [(identifier,) for identifier in ids])
