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
from typing import Any, Callable, Iterable

from src.modules.core.email_delivery import OWN_TICKET_CHANGES_KEY, email_delivery_settings, send_email, subject_line
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
TICKET_EMAIL_WAIT_SECONDS = 120
TICKET_EMAIL_MAX_WAIT_SECONDS = 600
# Above this HTML, the changes waiting go in one email each (a Power Automate flow request takes about 28 KB).
TICKET_DIGEST_HTML_LIMIT = 22_000
ACTION_COLOURS = {
    'New Ticket': '#1E61A3', 'New Comment': '#0F766E', 'Ticket Updated': '#B45309', 'Comment Edited': '#B45309',
    'New Attachments': '#B45309', 'In Progress': '#2563EB', 'Waiting for Info': '#B45309', 'Back to New': '#2563EB',
    'Resolved': '#15803D', 'Closed': '#4B5563', 'Reopened': '#C2410C', 'Rejected': '#B42318', 'Comment Deleted': '#B42318',
    'Attachment Deleted': '#B42318', 'Ticket Deleted': '#B42318',
}


# The changes of a ticket waiting to be emailed, by (address of the recipient in lower case, ticket number).
_PENDING: dict[tuple[str, int], dict[str, Any]] = {}
_PENDING_LOCK = threading.Lock()


def submit(task: Callable[[], Any]) -> None:
    """Run a sending in the background (tests run it at once)."""
    _EXECUTOR.submit(task)


def html_to_text(markup: str) -> str:
    text = re.sub(r'<br\s*/?>|</p>|</li>|</tr>|</h\d>|</div>|</pre>', '\n', markup, flags=re.IGNORECASE)
    text = '\n'.join(line.rstrip() for line in html.unescape(re.sub(r'<[^>]+>', '', text)).replace('\xa0', ' ').split('\n'))
    return re.sub(r'\n{3,}', '\n\n', text).strip() + '\n'


def action_label(action: str) -> str:
    return f'<span style="color:{ACTION_COLOURS.get(action, "#1E61A3")}">{html.escape(action)}</span>'


def email_page(app_name: str, title: str, parts: Iterable[str], *, link: tuple[str, str] | None = None,
               action: str | Iterable[str] = '') -> str:
    """The HTML of an email of the tool: a title, its paragraphs, a button to open the page it is about and a footer.
    ``action`` (what happened, such as New Comment; or several, one after another) leads the title, larger and in its
    colour."""
    button = (f'<p style="margin:20px 0"><a href="{html.escape(link[1], quote=True)}" style="background:#1E61A3;color:#ffffff;'
              f'padding:9px 16px;border-radius:6px;text-decoration:none;font-weight:bold">{html.escape(link[0])}</a></p>') if link else ''
    actions = [action] if isinstance(action, str) else list(action)
    actions = [item for item in actions if item]
    heading = (f'<p style="font-size:21px;line-height:1.3;font-weight:bold;margin:0 0 12px">'
               + '<span style="color:#9ca3af">, </span>'.join(action_label(item) for item in actions)
               + f'<span style="color:#9ca3af"> · </span>{html.escape(title)}</p>') if actions else (
        f'<p style="font-size:17px;font-weight:bold;margin:0 0 12px">{html.escape(title)}</p>')
    return ('<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#1f2933;line-height:1.45">'
            + heading
            + ''.join(parts) + button +
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
            switch: str = '') -> bool:
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
            send_email(settings, recipients, subject, html_to_text(html_body), html_body, cc=copied, reply_to=reply_to, kind=kind)
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


def ticket_recipients(repository: Any, ticket: dict[str, Any], actor: str, *, include_actor: bool = False) -> dict[str, int]:
    """Who an update of ``ticket`` is told to, by username in lower case: its reporter, and the reporters of the tickets
    its description and comments mention; each with the ticket of theirs it is about. Who made the update is left out,
    unless ``include_actor`` (the reporter of a new ticket gets its confirmation)."""
    from src.modules.ticket_center.ticket_center import get_ticket

    owners: dict[str, int] = {str(ticket['created_by']).casefold(): int(ticket['id'])}
    texts = [ticket.get('description'), *(comment.get('body') for comment in ticket.get('comments') or [] if comment.get('kind') == 'comment')]
    for number in mentioned_tickets(texts):
        if number == int(ticket['id']):
            continue
        mentioned = get_ticket(repository, number)
        if mentioned:
            owners.setdefault(str(mentioned['created_by']).casefold(), number)
    if not include_actor:
        owners.pop(str(actor).casefold(), None)
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
    return subject, email_page(app_name, f'Ticket #{number}: {title}', parts, link=link, action=list(dict.fromkeys(actions)))


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
    """Tell the reporter of a ticket, and the reporters of the tickets it mentions, of a change made by someone else (the
    reporter of a new ticket also gets its confirmation). ``base_url`` is the address of the tool for its link; ``ticket`` is
    the one deleted, when it no longer exists."""
    from src.modules.ticket_center.ticket_center import get_ticket

    try:
        settings = email_delivery_settings(repository)
        if not settings['configured'] or not settings.get('notify_tickets'):
            return
        ticket = ticket or get_ticket(repository, ticket_id)
        if not ticket:
            return
        # Nobody is told of their own changes, except the users Email Delivery names (the reporter of a new ticket always
        # gets its confirmation).
        told_of_own = {str(name).casefold() for name in settings.get(OWN_TICKET_CHANGES_KEY) or []}
        owners = ticket_recipients(repository, ticket, actor,
                                   include_actor=event == 'created' or str(actor).casefold() in told_of_own)
        emails = repository.user_emails(owners)
        if not emails:
            return
        names = people_names(repository)
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
            deliver(repository, kind='ticket', recipients=[pending['address']], subject=subject, html_body=body,
                    actor=str(group[-1].get('actor') or ''), details=details, switch='notify_tickets', background=False)
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
