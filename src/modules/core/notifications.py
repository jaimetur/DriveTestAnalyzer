"""The emails the tool sends on its own, through Email Delivery (an SMTP server or a Power Automate flow): the access
requests of the login page and the activation of their users, the password resets, and the updates of Ticket Center
for whoever reported a ticket (also of the tickets that mention it as #<number>).

Each email is recorded in App Events as sent or failed. Emails of Ticket Center go in the background, so a slow mail
server never slows a page down, and the changes of a ticket made one after another reach each recipient in one email."""
from __future__ import annotations

import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from src.modules.core.email_delivery import EVERY_TICKET_KEY, email_delivery_settings, send_email, subject_line
from src.modules.core.email_markdown import markdown_html

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='email-notifications')
# A ticket mentioned as #<number>, not inside a word, a web address or another number.
MENTION = re.compile(r'(?<![\w&/#])#([1-9][0-9]{0,8})(?!\w)')
# The text of a description or comment an email quotes; the ticket has the rest.
QUOTED_CHARACTERS = 3000
# The HTML of that text with its formats: a Power Automate flow request takes about 28 KB in all.
TEXT_HTML_LIMIT = 14_000
# What happened to a ticket, as the title of its email says it (the subject is the same for every email of a ticket),
# each in its colour.
TICKET_ACTIONS = {
    'created': 'New Ticket', 'updated': 'Ticket Updated', 'managed': 'Ticket Updated', 'commented': 'New Comment',
    'comment_edited': 'Comment Edited', 'comment_deleted': 'Comment Deleted', 'attachments_added': 'New Attachments',
    'attachment_deleted': 'Attachment Deleted', 'deleted': 'Ticket Deleted',
}
# A change of status says the new one (Reopened when a done or rejected ticket opens again).
STATUS_ACTIONS = {'new': 'Back to New', 'in_progress': 'In Progress', 'waiting_info': 'Waiting for Info', 'resolved': 'Resolved',
                  'closed': 'Closed', 'rejected': 'Rejected'}
# The changes of a ticket made one after another reach each recipient in one email: it goes once no change came for
# this long, and never later than the most after the first one (0 sends each change at once).
TICKET_EMAIL_WAIT_SECONDS = 60
TICKET_EMAIL_MAX_WAIT_SECONDS = 600
# Above this HTML, the changes waiting go in one email each (a Power Automate flow request takes about 28 KB).
TICKET_DIGEST_HTML_LIMIT = 22_000
ACTION_COLOURS = {
    'New Ticket': '#1E61A3', 'New Comment': '#0F766E', 'Ticket Updated': '#B45309', 'Comment Edited': '#B45309',
    'New Attachments': '#B45309', 'In Progress': '#2563EB', 'Waiting for Info': '#B45309', 'Back to New': '#2563EB',
    'Resolved': '#15803D', 'Closed': '#4B5563', 'Reopened': '#C2410C', 'Rejected': '#B42318', 'Comment Deleted': '#B42318',
    'Attachment Deleted': '#B42318', 'Ticket Deleted': '#B42318',
}


# How often a user is emailed of the NQ calls and of its tickets, each chosen apart in Email preferences (ticket #194),
# and when the summaries go (local time of the server): every hour, every day at 17:00 or every Friday at 17:00.
EMAIL_FREQUENCIES = {'immediate': 'Immediately', 'hourly': 'Every hour', 'daily': 'Daily at 17:00',
                     'weekly': 'Weekly on Friday at 17:00', 'off': 'Never'}
SUMMARY_HOUR = 17
SUMMARY_WEEKDAY = 4  # Friday
SUMMARY_NAMES = {'hourly': 'Hourly', 'daily': 'Daily', 'weekly': 'Weekly'}
SUMMARY_PERIODS = {'hourly': 'the last hour', 'daily': 'the last day', 'weekly': 'the last week'}
# The tickets are emailed at once unless the user chooses otherwise.
TICKET_DEFAULT_FREQUENCY = 'immediate'
# The changes of the tickets waiting for the summaries of their recipients (application database).
TICKET_QUEUE_TABLE = 'ticket_email_queue'
TICKET_QUEUE_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {TICKET_QUEUE_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    ticket_id INTEGER NOT NULL,
    own_ticket INTEGER NOT NULL,
    own_title TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    ticket_json TEXT NOT NULL,
    change_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{TICKET_QUEUE_TABLE}_username ON {TICKET_QUEUE_TABLE}(username);
"""


def chosen_frequency(value: object, default: str) -> str:
    """The frequency a user chose, else ``default``."""
    return str(value) if str(value or '') in EMAIL_FREQUENCIES else default


def last_summary_time(frequency: str, now: datetime) -> datetime:
    """The latest time a summary of ``frequency`` was due at or before ``now`` (aware, local time): the changes made before
    it go in that summary."""
    if frequency == 'hourly':
        return now.replace(minute=0, second=0, microsecond=0)
    if frequency in {'daily', 'weekly'}:
        due = now.replace(hour=SUMMARY_HOUR, minute=0, second=0, microsecond=0)
        if due > now:
            due -= timedelta(days=1)
        if frequency == 'weekly':
            due -= timedelta(days=(due.weekday() - SUMMARY_WEEKDAY) % 7)
        return due
    return now


def due_before(frequency: str, now: datetime) -> str:
    """The time (UTC, as the queues store it) before which the changes waiting go in the summary of ``frequency``."""
    return last_summary_time(frequency, now).astimezone(timezone.utc).isoformat(timespec='seconds')


def queued_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


# The changes of a ticket waiting to be emailed, by (address of the recipient in lower case, ticket number).
_PENDING: dict[tuple[str, int], dict[str, Any]] = {}
_PENDING_LOCK = threading.Lock()


def submit(task: Callable[[], Any]) -> None:
    """Run a sending in the background (tests run it at once)."""
    _EXECUTOR.submit(task)


def html_to_text(markup: str) -> str:
    # The cells of a row stay apart (a label and its value: 'User EABCDEF').
    text = re.sub(r'</t[dh]>', ' ', markup, flags=re.IGNORECASE)
    text = re.sub(r'<br\s*/?>|</p>|</li>|</tr>|</h\d>|</div>|</pre>', '\n', text, flags=re.IGNORECASE)
    text = '\n'.join(line.rstrip() for line in html.unescape(re.sub(r'<[^>]+>', '', text)).replace('\xa0', ' ').split('\n'))
    return re.sub(r'\n{3,}', '\n\n', text).strip() + '\n'


def action_label(action: str) -> str:
    return f'<span style="color:{ACTION_COLOURS.get(action, "#1E61A3")}">{html.escape(action)}</span>'


def button(label: str, url: str) -> str:
    """A button of an email that opens ``url``."""
    return (f'<p style="margin:20px 0"><a href="{html.escape(url, quote=True)}" style="background:#1E61A3;color:#ffffff;'
            f'padding:9px 16px;border-radius:6px;text-decoration:none;font-weight:bold">{html.escape(label)}</a></p>')


def callout(label: str, markup: str, *, colour: str = '#1E61A3', background: str = '#EEF5FC') -> str:
    """A box of an email that stands out from its paragraphs: a short label in capitals over its text (HTML), with a line
    of its colour on the left. A table, which every mail client draws as it is (Outlook too)."""
    return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;margin:14px 0">'
            f'<tr><td style="background:{background};border-left:4px solid {colour};padding:11px 14px">'
            f'<p style="margin:0 0 4px;font-size:11px;font-weight:bold;letter-spacing:1px;text-transform:uppercase;color:{colour}">'
            f'{html.escape(label)}</p><p style="margin:0">{markup}</p></td></tr></table>')


def details_table(rows: Iterable[tuple[str, str]], *, title: str = '') -> str:
    """The details of an email as a table of labels and values (HTML), one per row, under a ``title`` in capitals."""
    cells = ''.join(
        '<tr><td style="padding:8px 14px 8px 0;border-top:1px solid #e5e9ee;color:#6b7280;white-space:nowrap;vertical-align:top">'
        f'{html.escape(label)}</td><td style="padding:8px 0;border-top:1px solid #e5e9ee;vertical-align:top;overflow-wrap:anywhere">'
        f'{value}</td></tr>' for label, value in rows)
    heading = (f'<p style="margin:22px 0 6px;font-size:11px;font-weight:bold;letter-spacing:1px;text-transform:uppercase;color:#6b7280">'
               f'{html.escape(title)}</p>') if title else ''
    return (heading + '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;font-size:14px;border-bottom:1px solid #e5e9ee">{cells}</table>')


def email_page(app_name: str, title: str, parts: Iterable[str], *, link: tuple[str, str] | None = None,
               action: str | Iterable[str] = '') -> str:
    """The HTML of an email of the tool: a title, its paragraphs, a button to open the page it is about and a footer.
    ``action`` (what happened, such as New Comment; or several, one after another) leads the title, larger and in its
    colour."""
    link_button = button(*link) if link else ''
    actions = [action] if isinstance(action, str) else list(action)
    actions = [item for item in actions if item]
    heading = (f'<p style="font-size:21px;line-height:1.3;font-weight:bold;margin:0 0 12px">'
               + '<span style="color:#9ca3af">, </span>'.join(action_label(item) for item in actions)
               + f'<span style="color:#9ca3af"> · </span>{html.escape(title)}</p>') if actions else (
        f'<p style="font-size:17px;font-weight:bold;margin:0 0 12px">{html.escape(title)}</p>')
    return ('<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#1f2933;line-height:1.45">'
            + heading
            + ''.join(parts) + link_button +
            f'<p style="color:#6b7280;font-size:12px;margin-top:24px">Sent automatically by {html.escape(app_name)}.</p>'
            '</body></html>')


def text_block(text: str, *, base_url: str = '', tickets: dict[int, str] | None = None) -> str:
    """A text of Ticket Center (a description, a comment) as the ticket shows it: its Markdown with its formats, its
    #<number> of the ``tickets`` linked to them; line by line as it was written when its formats would not fit a flow."""
    markup = markdown_html(text, base_url=base_url, tickets=tickets)
    if len(markup) > TEXT_HTML_LIMIT:
        markup = '<br>'.join(html.escape(line) for line in str(text).splitlines())
    return ('<div style="border:1px solid #dde3e9;border-radius:8px;padding:10px 14px;margin:10px 0;color:#23394a;'
            f'line-height:1.55;overflow-wrap:anywhere">{markup}</div>')


def deliver(repository: Any, *, kind: str, recipients: list[str], subject: str, html_body: str, cc: Iterable[str] = (),
            reply_to: str = '', actor: str = '', details: dict[str, Any] | None = None, background: bool = True,
            switch: str = '', thread: str = '') -> bool:
    """Send one email when Email Delivery is configured (and its ``switch`` is on), recording it in App Events.

    In the background it returns whether it was queued; otherwise whether it was sent."""
    settings = email_delivery_settings(repository, include_password=True)
    if not settings['configured'] or not recipients or (switch and not settings.get(switch)):
        return False
    copied = [address for address in dict.fromkeys(cc) if address and address not in recipients]
    logged = {'kind': kind, 'subject': subject_line(subject), 'recipients': recipients, 'cc': copied, 'transport': settings['transport'],
              **(details or {})}

    def send() -> bool:
        try:
            send_email(settings, recipients, subject, html_to_text(html_body), html_body, cc=copied, reply_to=reply_to, kind=kind,
                       thread=thread)
        except Exception as exc:  # The error is recorded as it is: the action that sent it already succeeded.
            repository.try_add_log(actor or 'system', 'email_failed', json.dumps({**logged, 'error': str(exc)}, ensure_ascii=False))
            return False
        repository.try_add_log(actor or 'system', 'email_sent', json.dumps(logged, ensure_ascii=False))
        return True

    if background:
        submit(send)
        return True
    return send()


def people_names(repository: Any) -> dict[str, str]:
    """The name of every account by its username in lower case (its username when it has no name)."""
    names = {}
    for row in repository.list_users():
        name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
        names[str(row['username']).casefold()] = name or str(row['username'])
    return names


# -- Ticket Center -----------------------------------------------------------------------------------------------------
def mentioned_tickets(texts: Iterable[object]) -> list[int]:
    return list(dict.fromkeys(int(number) for text in texts for number in MENTION.findall(str(text or ''))))


def _quoted(text: object) -> str:
    text = str(text or '').strip()
    return text if len(text) <= QUOTED_CHARACTERS else text[:QUOTED_CHARACTERS].rstrip() + ' …'


def ticket_recipients(repository: Any, ticket: dict[str, Any], *, every_ticket: Iterable[str] = ()) -> dict[str, int]:
    """Who an update of ``ticket`` is told to, by username in lower case: its reporter, whoever commented it, the users
    ``every_ticket`` names, and the reporters of the tickets its description and comments mention; each with the ticket
    of theirs it is about. Who made the update is told too: its own changes and comments are emailed to it as well."""
    from src.modules.ticket_center.ticket_center import get_ticket

    number = int(ticket['id'])
    comments = [comment for comment in ticket.get('comments') or [] if comment.get('kind') == 'comment']
    owners: dict[str, int] = {str(ticket['created_by']).casefold(): number}
    for username in (*(comment.get('username') for comment in comments), *every_ticket):
        if str(username or '').strip():
            owners.setdefault(str(username).casefold(), number)
    texts = [ticket.get('description'), *(comment.get('body') for comment in comments)]
    for number in mentioned_tickets(texts):
        if number == int(ticket['id']):
            continue
        mentioned = get_ticket(repository, number)
        if mentioned:
            owners.setdefault(str(mentioned['created_by']).casefold(), number)
    return owners


def _change_text(field: str, value: object, names: dict[str, str]) -> str:
    from src.modules.ticket_center.ticket_center import PRIORITIES, STATUSES, TICKET_TYPES

    value = str(value or '')
    if field == 'status':
        return STATUSES.get(value, value)
    if field == 'ticket_type':
        return TICKET_TYPES.get(value, value)
    if field == 'priority':
        return f'{value} · {PRIORITIES.get(value, "")}' if value else ''
    if field in {'assigned_to', 'created_by'}:
        return names.get(value.casefold(), value) if value else 'Nobody'
    if field in {'app_version', 'fixed_version'}:
        return f'v{value}' if value else ''
    if field == 'module':
        return value or 'General'
    return value


TICKET_DID = {
    'created': 'opened this ticket', 'updated': 'edited this ticket', 'managed': 'changed this ticket',
    'commented': 'added a comment', 'comment_edited': 'edited a comment', 'comment_deleted': 'deleted a comment',
    'attachments_added': 'added attachments', 'attachment_deleted': 'deleted an attachment', 'deleted': 'deleted this ticket',
}


def _ticket_state_parts(ticket: dict[str, Any], names: dict[str, str], own_ticket: int | None, own_title: str) -> list[str]:
    """The ticket of the recipient it mentions, and the status, priority, type and reporter of ``ticket``."""
    from src.modules.ticket_center.ticket_center import PRIORITIES, STATUSES, TICKET_TYPES

    parts = []
    if own_ticket and own_ticket != int(ticket['id']):
        parts.append(f'<p>This ticket mentions your ticket <strong>#{own_ticket}</strong>'
                     f'{f" ({html.escape(own_title)})" if own_title else ""}.</p>')
    status = STATUSES.get(str(ticket.get('status')), str(ticket.get('status') or ''))
    kind = TICKET_TYPES.get(str(ticket.get('ticket_type') or ''), '')
    priority = str(ticket.get('priority') or '')
    parts.append('<p style="color:#4b5563">' + ' · '.join(html.escape(item) for item in (
        f'Status: {status}', f'Priority: {priority} {PRIORITIES.get(priority, "")}'.strip(), f'Type: {kind}' if kind else '',
        f"Reported by: {names.get(str(ticket.get('created_by') or '').casefold(), ticket.get('created_by') or '')}") if item) + '</p>')
    return parts


def _change_parts(change: dict[str, Any], base_url: str, names: dict[str, str]) -> tuple[str, list[str]]:
    """Who made a ``change`` and what it did (as a sentence), and its details: the fields it changed, the description of a
    new ticket, the comment and the files."""
    from src.modules.ticket_center.ticket_center import FIELD_LABELS

    did = f"<strong>{html.escape(change['actor_name'])}</strong> {TICKET_DID.get(change['event'], 'updated this ticket')}."
    parts, rows = [], []
    for field, values in (change.get('changes') or {}).items():
        if not isinstance(values, (list, tuple)) or len(values) != 2:
            continue
        label = FIELD_LABELS.get(field, field.replace('_', ' ').capitalize())
        if field == 'description':
            rows.append(f'<tr><td style="padding:3px 12px 3px 0;color:#6b7280">{html.escape(label)}</td><td colspan="2">changed</td></tr>')
            continue
        before, after = (_change_text(field, value, names) for value in values)
        rows.append(f'<tr><td style="padding:3px 12px 3px 0;color:#6b7280">{html.escape(label)}</td>'
                    f'<td style="padding:3px 8px 3px 0;text-decoration:line-through;color:#9ca3af">{html.escape(before)}</td>'
                    f'<td style="padding:3px 0"><strong>{html.escape(after)}</strong></td></tr>')
    if rows:
        parts.append('<table style="border-collapse:collapse;font-size:14px">' + ''.join(rows) + '</table>')
    for text in (change.get('description') if change['event'] == 'created' else '', change.get('comment')):
        if text:
            parts.append(text_block(_quoted(text), base_url=base_url, tickets=change.get('references')))
    listed = [str(name) for name in change.get('files') or () if str(name)]
    if listed:
        parts.append('<ul>' + ''.join(f'<li>{html.escape(name)}</li>' for name in listed) + '</ul>')
    return did, parts


def ticket_email(app_name: str, ticket: dict[str, Any], event: str, actor_name: str, base_url: str, names: dict[str, str], *,
                 changes: dict[str, Any] | None = None, comment: str = '', files: Iterable[str] = (),
                 own_ticket: int | None = None, own_title: str = '', references: dict[int, str] | None = None) -> tuple[str, str]:
    """The subject and HTML of an email about ``ticket``; ``own_ticket`` is the ticket of the recipient it mentions, and
    ``references`` the title of each ticket its texts mention as #<number>."""
    change = {'event': event, 'actor_name': actor_name, 'changes': changes, 'comment': comment, 'files': list(files),
              'references': references, 'description': ticket.get('description')}
    return ticket_changes_email(app_name, ticket, [change], base_url, names, own_ticket=own_ticket, own_title=own_title)


def ticket_changes_email(app_name: str, ticket: dict[str, Any], changes: list[dict[str, Any]], base_url: str,
                         names: dict[str, str], *, own_ticket: int | None = None, own_title: str = '') -> tuple[str, str]:
    """The subject and HTML of one email about the ``changes`` of ``ticket`` made one after another (``ticket`` as the last
    one left it): what happened, in its colour, leads the title, and each change after the state of the ticket."""
    subject, parts, link, actions = _ticket_changes_parts(ticket, changes, base_url, names, own_ticket=own_ticket, own_title=own_title)
    return subject, email_page(app_name, subject, parts, link=link, action=actions)


def _ticket_changes_parts(ticket: dict[str, Any], changes: list[dict[str, Any]], base_url: str, names: dict[str, str], *,
                          own_ticket: int | None = None, own_title: str = '') -> tuple[str, list[str], tuple[str, str] | None, list[str]]:
    """The subject, the paragraphs, the link and what happened of the email of the ``changes`` of ``ticket``."""
    number, title = int(ticket['id']), str(ticket['title'])
    # One subject for every email of a ticket; the title says what happened.
    subject = f'Ticket #{number}: {title}'
    actions = [ticket_action(change['event'], change.get('changes')) for change in changes]
    state = _ticket_state_parts(ticket, names, own_ticket, own_title)
    if len(changes) == 1:
        did, details = _change_parts(changes[0], base_url, names)
        parts = [f'<p>{did}</p>', *state, *details]
    else:
        parts = list(state)
        for action, change in zip(actions, changes):
            did, details = _change_parts(change, base_url, names)
            parts.append(f'<div style="border-left:3px solid {ACTION_COLOURS.get(action, "#1E61A3")};padding:2px 0 2px 12px;'
                         f'margin:16px 0"><p style="margin:0 0 6px"><strong>{action_label(action)}</strong>'
                         f'<span style="color:#9ca3af"> · </span>{did}</p>' + ''.join(details) + '</div>')
    deleted = any(change['event'] == 'deleted' for change in changes)
    link = None if deleted or not base_url else (f'Open ticket #{number}', f'{base_url}/tickets/{number}')
    return subject, parts, link, list(dict.fromkeys(actions))


def ticket_action(event: str, changes: dict[str, Any] | None = None) -> str:
    """What happened to a ticket, as the title of its email says it: a change of status by its new status."""
    from src.modules.ticket_center.ticket_center import DONE_STATUSES, OPEN_STATUSES

    status = (changes or {}).get('status')
    if event in {'updated', 'managed'} and isinstance(status, (list, tuple)) and len(status) == 2 and status[0] != status[1]:
        before, after = (str(value or '') for value in status)
        if after in OPEN_STATUSES and before in {*DONE_STATUSES, 'rejected'}:
            return 'Reopened'
        return STATUS_ACTIONS.get(after, 'Ticket Updated')
    return TICKET_ACTIONS.get(event, 'Ticket Updated')


def notify_ticket(repository: Any, app_name: str, ticket_id: int, actor: str, event: str, base_url: str, *,
                  ticket: dict[str, Any] | None = None, changes: dict[str, Any] | None = None, comment: str = '',
                  files: Iterable[str] = ()) -> None:
    """Tell the reporter of a ticket, whoever commented it, the users of Email Every Ticket To and the reporters of the tickets
    it mentions of a change, whoever made it (the reporter of a new ticket gets its confirmation). ``base_url`` is the address of the tool for its link; ``ticket`` is
    the one deleted, when it no longer exists."""
    from src.modules.ticket_center.ticket_center import get_ticket

    try:
        settings = email_delivery_settings(repository)
        if not settings['configured'] or not settings.get('notify_tickets'):
            return
        ticket = ticket or get_ticket(repository, ticket_id)
        if not ticket:
            return
        # Who made the change is told of it too (the reporter of a new ticket gets its confirmation).
        owners = ticket_recipients(repository, ticket, every_ticket=settings.get(EVERY_TICKET_KEY) or [])
        emails = repository.user_emails(owners)
        if not emails:
            return
        names = people_names(repository)
        preferences = repository.email_preferences(owners)
        base = str(base_url or '').rstrip('/')
        listed = list(files)
        references = {}
        for number in mentioned_tickets([ticket.get('description') if event == 'created' else '', comment]):
            mentioned = ticket if number == int(ticket['id']) else get_ticket(repository, number)
            if mentioned:
                references[number] = str(mentioned['title'])
        for username, own_ticket in owners.items():
            address = emails.get(username)
            if not address:
                continue
            own_title = ''
            if own_ticket != int(ticket['id']):
                mentioned = get_ticket(repository, own_ticket)
                own_title = str(mentioned['title']) if mentioned else ''
            change = {'event': event, 'actor_name': names.get(str(actor).casefold(), str(actor)), 'changes': changes,
                      'comment': comment, 'files': listed, 'references': references, 'description': ticket.get('description'),
                      'actor': actor}
            # At once (the default), in the summary the user chose (ticket #194) or never.
            frequency = chosen_frequency((preferences.get(username) or {}).get('ticket_frequency'), TICKET_DEFAULT_FREQUENCY)
            if frequency == 'off':
                continue
            if frequency != 'immediate':
                queue_ticket_summary(repository, username, ticket, change, base_url=base, own_ticket=own_ticket, own_title=own_title)
                continue
            queue_ticket_email(repository, app_name, address, username, ticket, change, base_url=base, names=names,
                               own_ticket=own_ticket, own_title=own_title)
    except Exception as exc:  # Never let an email break the change it tells of.
        repository.try_add_log(actor or 'system', 'email_failed', json.dumps({
            'kind': 'ticket', 'ticket_id': ticket_id, 'event': event, 'error': str(exc)}, ensure_ascii=False))


def queue_ticket_email(repository: Any, app_name: str, address: str, username: str, ticket: dict[str, Any],
                       change: dict[str, Any], *, base_url: str, names: dict[str, str], own_ticket: int,
                       own_title: str = '') -> None:
    """Email ``change`` of ``ticket`` to ``address`` together with the changes of the ticket that come after it: the email
    goes once no change came for TICKET_EMAIL_WAIT_SECONDS, at most TICKET_EMAIL_MAX_WAIT_SECONDS after the first one."""
    key = (address.casefold(), int(ticket['id']))
    now = time.monotonic()
    with _PENDING_LOCK:
        pending = _PENDING.get(key)
        if pending is None:
            pending = _PENDING[key] = {'first': now, 'changes': []}
        elif pending.get('timer'):
            pending['timer'].cancel()
        pending.update(repository=repository, app_name=app_name, address=address, username=username, ticket=ticket,
                       base_url=base_url, names=names, own_ticket=own_ticket, own_title=own_title, token=object())
        pending['changes'].append(change)
        token, pending['timer'] = pending['token'], None
        if TICKET_EMAIL_WAIT_SECONDS > 0:
            wait = min(TICKET_EMAIL_WAIT_SECONDS, max(0.0, pending['first'] + TICKET_EMAIL_MAX_WAIT_SECONDS - now))
            pending['timer'] = threading.Timer(wait, _send_ticket_email, args=(key, token))
            pending['timer'].daemon = True
            pending['timer'].start()
            return
    submit(lambda: _send_ticket_email(key, token))


def _send_ticket_email(key: tuple[str, int], token: object | None) -> None:
    """Send the changes waiting for ``key`` in one email (one each when they would not fit a flow); ``token`` is the one
    of the last change queued (None sends them whatever came after)."""
    with _PENDING_LOCK:
        pending = _PENDING.get(key)
        if not pending or (token is not None and pending.get('token') is not token):
            return
        _PENDING.pop(key)
        if pending.get('timer'):
            pending['timer'].cancel()
    repository, changes, ticket = pending['repository'], pending['changes'], pending['ticket']
    try:
        args = (pending['app_name'], ticket)
        options = {'own_ticket': pending['own_ticket'], 'own_title': pending['own_title']}
        subject, body = ticket_changes_email(*args, changes, pending['base_url'], pending['names'], **options)
        groups = [changes]
        if len(changes) > 1 and len(body.encode()) > TICKET_DIGEST_HTML_LIMIT:
            groups = [[change] for change in changes]
        for group in groups:
            if group is not changes:
                subject, body = ticket_changes_email(*args, group, pending['base_url'], pending['names'], **options)
            events = [change['event'] for change in group]
            details = {'ticket_id': int(ticket['id']), 'event': events[-1], 'user': str(pending['username']).upper(),
                       'about_ticket': pending['own_ticket'], **({'events': events} if len(events) > 1 else {})}
            # Every email of a ticket in one conversation of the mail clients.
            deliver(repository, kind='ticket', recipients=[pending['address']], subject=subject, html_body=body,
                    actor=str(group[-1].get('actor') or ''), details=details, switch='notify_tickets', background=False,
                    thread=f"ticket-{int(ticket['id'])}")
    except Exception as exc:  # Never let an email break the thread that sends it.
        repository.try_add_log(str(changes[-1].get('actor') or 'system'), 'email_failed', json.dumps({
            'kind': 'ticket', 'ticket_id': key[1], 'events': [change['event'] for change in changes], 'error': str(exc)},
            ensure_ascii=False))


def flush_ticket_emails() -> None:
    """Send at once every email of Ticket Center still waiting for changes that may come (when the tool stops)."""
    with _PENDING_LOCK:
        keys = list(_PENDING)
    for key in keys:
        _send_ticket_email(key, None)


def queue_ticket_summary(repository: Any, username: str, ticket: dict[str, Any], change: dict[str, Any], *, base_url: str,
                         own_ticket: int, own_title: str = '') -> None:
    """Keep a change of ``ticket`` for the summary of ``username`` (ticket #194)."""
    with repository.global_connection() as conn:
        conn.executescript(TICKET_QUEUE_SCHEMA)
        conn.execute(f'INSERT INTO {TICKET_QUEUE_TABLE} (username, ticket_id, own_ticket, own_title, base_url, ticket_json, '
                     'change_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                     (username, int(ticket['id']), int(own_ticket), own_title, base_url, json.dumps(ticket, ensure_ascii=False, default=str),
                      json.dumps(change, ensure_ascii=False, default=str), queued_at()))


def _queued_change(text: str) -> dict[str, Any]:
    change = json.loads(text)
    # The titles of the tickets a text mentions, by number (JSON keeps the numbers as text).
    change['references'] = {int(number): title for number, title in (change.get('references') or {}).items()}
    return change


def ticket_summary_email(app_name: str, frequency: str, tickets: list[dict[str, Any]], base_url: str,
                         names: dict[str, str]) -> tuple[str, str]:
    """The subject and HTML of the summary of the tickets changed since the previous one: each ticket with its changes,
    one after another, after its state as the last one left it."""
    period = SUMMARY_PERIODS.get(frequency, 'the last period')
    count = 'this ticket' if len(tickets) == 1 else f'{len(tickets)} tickets'
    parts = [f'<p>The changes of {period} in {count}.</p>']
    actions: list[str] = []
    for item in tickets:
        subject, ticket_parts, link, ticket_actions = _ticket_changes_parts(
            item['ticket'], item['changes'], base_url, names, own_ticket=item['own_ticket'], own_title=item['own_title'])
        actions += ticket_actions
        heading = html.escape(subject)
        if link:
            heading = f'<a href="{html.escape(link[1], quote=True)}" style="color:#1E61A3">{heading}</a>'
        parts.append(f'<p style="margin:26px 0 6px;font-size:16px;font-weight:bold;border-top:1px solid #e5e9ee;padding-top:14px">'
                     f'{heading}</p>' + ''.join(ticket_parts))
    name = SUMMARY_NAMES.get(frequency, 'Tickets')
    title = f"{name} summary · {len(tickets)} ticket{'s' if len(tickets) != 1 else ''}"
    subject = f"Tickets - {name} summary - {len(tickets)} ticket{'s' if len(tickets) != 1 else ''}"
    link = ('Open Ticket Center', f'{base_url}/tickets') if base_url else None
    return subject, email_page(app_name, title, parts, link=link, action=list(dict.fromkeys(actions)))


def send_due_ticket_summaries(repository: Any, app_name: str, now: datetime | None = None) -> int:
    """Email each user the summary of its tickets whose time has come (every hour, day or Friday at 17:00, as it chose);
    how many emails were sent. A summary too large for a flow goes as one email per ticket. A user's changes wait while
    the email cannot be sent (they all go at once when it chose Immediately since), and are dropped once it chose Never, has no address or ticket emails are
    switched off."""
    now = (now or datetime.now()).astimezone()
    settings = email_delivery_settings(repository)
    with repository.global_connection() as conn:
        conn.executescript(TICKET_QUEUE_SCHEMA)
        rows = [dict(row) for row in conn.execute(f'SELECT * FROM {TICKET_QUEUE_TABLE} ORDER BY id').fetchall()]
    if not rows or not settings['configured']:
        return 0
    if not settings.get('notify_tickets'):
        _drop_ticket_rows(repository, [row['id'] for row in rows])
        return 0
    by_user: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_user.setdefault(row['username'], []).append(row)
    preferences = repository.email_preferences(by_user)
    emails = repository.user_emails(by_user)
    names = people_names(repository)
    sent = 0
    for username, user_rows in by_user.items():
        frequency = chosen_frequency((preferences.get(username) or {}).get('ticket_frequency'), TICKET_DEFAULT_FREQUENCY)
        address = emails.get(username)
        if frequency == 'off' or not address:
            _drop_ticket_rows(repository, [row['id'] for row in user_rows])
            continue
        ready = [row for row in user_rows if row['created_at'] <= due_before(frequency, now)]
        if not ready:
            continue
        tickets: dict[int, dict[str, Any]] = {}
        for row in ready:
            item = tickets.setdefault(int(row['ticket_id']), {'changes': [], 'own_ticket': int(row['own_ticket']),
                                                              'own_title': row['own_title']})
            item['ticket'] = json.loads(row['ticket_json'])
            item['changes'].append(_queued_change(row['change_json']))
        base = str(ready[-1]['base_url'] or '').rstrip('/')
        subject, body = ticket_summary_email(app_name, frequency, list(tickets.values()), base, names)
        emails_of = [(subject, body, list(tickets))]
        if len(tickets) > 1 and len(body.encode()) > TICKET_DIGEST_HTML_LIMIT:
            emails_of = [(*ticket_summary_email(app_name, frequency, [item], base, names), [number]) for number, item in tickets.items()]
        for subject, body, numbers in emails_of:
            delivered = deliver(repository, kind='ticket_summary', recipients=[address], subject=subject, html_body=body,
                                actor='system', details={'user': username.upper(), 'frequency': frequency, 'tickets': numbers,
                                                         'changes': sum(len(tickets[number]['changes']) for number in numbers)},
                                switch='notify_tickets', background=False)
            if delivered:
                sent += 1
                _drop_ticket_rows(repository, [row['id'] for row in ready if int(row['ticket_id']) in numbers])
    return sent


def _drop_ticket_rows(repository: Any, ids: list[int]) -> None:
    if ids:
        with repository.global_connection() as conn:
            conn.executemany(f'DELETE FROM {TICKET_QUEUE_TABLE} WHERE id = ?', [(identifier,) for identifier in ids])
