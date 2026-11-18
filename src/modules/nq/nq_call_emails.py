"""Emails of the follow-up of the Non-Qualified Calls (ticket #187).

The reviewer of a call, and the users of Email Every NQ Call Change To, are told when every field of the analysts of the
call is filled and when its NQ Call Status or the status of one of its phases changes: one email per recipient for each
change (a bulk change or a copy to a group lists its calls in one email), with the follow-up of each call, what changed,
the fields filled by section and those still empty, and a link that opens the call.
"""
from __future__ import annotations

import html
import json
from typing import Any, Iterable

from src.modules.core import notifications
from src.modules.core.email_delivery import EVERY_NQ_CALL_KEY, email_delivery_settings

# A call of more is listed by its JOIN_ID only: an email stays readable (and under the size a flow accepts).
DETAILED_CALLS = 10
LISTED_CALLS = 200


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


def recipients_of(events: dict[str, dict[str, Any]], every: Iterable[str]) -> dict[str, list[str]]:
    """The calls each recipient (username in lower case) is told of: its reviewer, and the users of every change."""
    everyone = [str(name).casefold() for name in every if str(name).strip()]
    told: dict[str, list[str]] = {}
    for key, event in events.items():
        for username in [str(event['state'].get('reviewer') or '').casefold(), *everyone]:
            if username:
                told.setdefault(username, [])
                if key not in told[username]:
                    told[username].append(key)
    return told


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
    if event['changes']:
        what.append(notifications.details_table(
            [(label, f'{html.escape(old or "—")} → <strong>{html.escape(new or "—")}</strong>') for label, old, new in event['changes']],
            title='What changed'))
    person = lambda username: html.escape(names.get(str(username).casefold(), str(username)) if username else '—')  # noqa: E731
    follow = notifications.details_table([
        ('NQ Call Status', html.escape(state['status'] or '—')), ('Team', html.escape(state['team'] or '—')),
        ('Analyst', person(state['analyst'])), ('Reviewer', person(state['reviewer'])),
        ('Root Category', html.escape(state['root_category'] or '—')), ('Root Cause', html.escape(state['root_cause'] or '—')),
        ('Started', html.escape(str(state.get('start_time') or '').replace('T', ' ')[:19] or '—')),
        ('Analyst fields', html.escape(progress))], title='Follow-up')
    parts = [heading, *what, follow]
    if detailed:
        by_section: dict[str, list[tuple[str, str]]] = {}
        for section, label, value in state['filled']:
            by_section.setdefault(section, []).append((label, value))
        for section, rows in by_section.items():
            parts.append(notifications.details_table([(label, html.escape(value)) for label, value in rows], title=f'Filled · {section}'))
        if state['missing']:
            missing: dict[str, list[str]] = {}
            for section, label in state['missing']:
                missing.setdefault(section, []).append(label)
            parts.append(notifications.details_table([(section, html.escape(', '.join(labels))) for section, labels in missing.items()],
                                                     title='Still empty'))
    return ''.join(parts)


def call_email(app_name: str, workspace: str, actor_name: str, events: dict[str, dict[str, Any]], keys: list[str], base_url: str,
               names: dict[str, str]) -> tuple[str, str]:
    """The subject and HTML of the email of some calls of a change."""
    shown = keys[:LISTED_CALLS]
    completed = sum(1 for key in shown if events[key]['completed'])
    changed = sum(1 for key in shown if events[key]['changes'])
    actions = [*(['Completed'] if completed else []), *(['Status changed'] if changed else [])]
    if len(shown) == 1:
        title = _call_title(events[shown[0]]['state'])
    else:
        title = f'{len(keys)} NQ calls'
    intro = (f'<p>{html.escape(actor_name)} changed {"this NQ call" if len(keys) == 1 else f"{len(keys)} NQ calls"} of the '
             f'workspace <strong>{html.escape(workspace)}</strong>.</p>')
    parts = [intro, *(_call_part(events[key], base_url, names, detailed=index < DETAILED_CALLS) for index, key in enumerate(shown))]
    if len(keys) > len(shown):
        parts.append(f'<p>And {len(keys) - len(shown)} more calls.</p>')
    link = ('Open the call', f"{base_url}/non-qualified-calls#call={shown[0]}") if base_url and len(shown) == 1 else (
        ('Open Non-Qualified Calls', f'{base_url}/non-qualified-calls') if base_url else None)
    subject = f"NQ Calls - {' & '.join(actions) or 'Changed'} - {title} ({workspace})"
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
        names = notifications.people_names(app_repository)
        actor_name = names.get(str(actor).casefold(), str(actor))
        base = str(base_url or '').rstrip('/')
        sent = 0
        for username, keys in told.items():
            address = emails.get(username)
            if not address:
                continue
            subject, body = call_email(app_name, workspace, actor_name, events, keys, base, names)
            notifications.deliver(app_repository, kind='nq_call', recipients=[address], subject=subject, html_body=body, actor=actor,
                                  details={'workspace': workspace, 'recipient': username, 'calls': len(keys),
                                           'join_ids': [events[key]['state'].get('join_id') or key for key in keys[:20]]},
                                  switch='notify_nq_calls')
            sent += 1
        return sent
    except Exception as exc:  # noqa: BLE001 - an email never breaks the change it tells of.
        app_repository.try_add_log(actor or 'system', 'email_failed', json.dumps(
            {'kind': 'nq_call', 'workspace': workspace, 'calls': len(events), 'error': str(exc)}, ensure_ascii=False))
        return 0
