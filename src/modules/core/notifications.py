"""The emails the tool sends on its own, through Email Delivery (an SMTP server or a Power Automate flow): the access
requests of the login page and the activation of their users, the password resets, and the updates of Ticket Center
for whoever reported a ticket (also of the tickets that mention it as #<number>).

Each email is recorded in App Events as sent or failed. Emails of Ticket Center go in the background, so a slow mail
server never slows a page down."""
from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable

from src.modules.core.email_delivery import email_delivery_settings, send_email
from src.modules.core.email_markdown import markdown_html

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='email-notifications')
# A ticket mentioned as #<number>, not inside a word, a web address or another number.
MENTION = re.compile(r'(?<![\w&/#])#([1-9][0-9]{0,8})(?!\w)')
# The text of a description or comment an email quotes; the ticket has the rest.
QUOTED_CHARACTERS = 3000
# The HTML of that text with its formats: a Power Automate flow request takes about 28 KB in all.
TEXT_HTML_LIMIT = 14_000
TICKET_EVENTS = {
    'created': 'opened', 'updated': 'updated', 'managed': 'updated', 'commented': 'new comment',
    'comment_edited': 'comment edited', 'comment_deleted': 'comment deleted', 'attachments_added': 'attachments added',
    'attachment_deleted': 'attachment deleted', 'deleted': 'deleted',
}


def submit(task: Callable[[], Any]) -> None:
    """Run a sending in the background (tests run it at once)."""
    _EXECUTOR.submit(task)


def html_to_text(markup: str) -> str:
    text = re.sub(r'<br\s*/?>|</p>|</li>|</tr>|</h\d>|</div>|</pre>', '\n', markup, flags=re.IGNORECASE)
    text = '\n'.join(line.rstrip() for line in html.unescape(re.sub(r'<[^>]+>', '', text)).replace('\xa0', ' ').split('\n'))
    return re.sub(r'\n{3,}', '\n\n', text).strip() + '\n'


def email_page(app_name: str, title: str, parts: Iterable[str], *, link: tuple[str, str] | None = None) -> str:
    """The HTML of an email of the tool: a title, its paragraphs, a button to open the page it is about and a footer."""
    button = (f'<p style="margin:20px 0"><a href="{html.escape(link[1], quote=True)}" style="background:#1E61A3;color:#ffffff;'
              f'padding:9px 16px;border-radius:6px;text-decoration:none;font-weight:bold">{html.escape(link[0])}</a></p>') if link else ''
    return ('<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#1f2933;line-height:1.45">'
            f'<p style="font-size:17px;font-weight:bold;margin:0 0 12px">{html.escape(title)}</p>'
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
    logged = {'kind': kind, 'subject': subject, 'recipients': recipients, 'cc': copied, 'transport': settings['transport'],
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


def ticket_email(app_name: str, ticket: dict[str, Any], event: str, actor_name: str, base_url: str, names: dict[str, str], *,
                 changes: dict[str, Any] | None = None, comment: str = '', files: Iterable[str] = (),
                 own_ticket: int | None = None, own_title: str = '', references: dict[int, str] | None = None) -> tuple[str, str]:
    """The subject and HTML of an email about ``ticket``; ``own_ticket`` is the ticket of the recipient it mentions, and
    ``references`` the title of each ticket its texts mention as #<number>."""
    from src.modules.ticket_center.ticket_center import FIELD_LABELS, PRIORITIES, STATUSES, TICKET_TYPES

    number, title = int(ticket['id']), str(ticket['title'])
    phrase = TICKET_EVENTS.get(event, 'updated')
    subject = f'Ticket #{number} {phrase}: {title}'
    did = {
        'created': 'opened this ticket', 'updated': 'edited this ticket', 'managed': 'changed this ticket',
        'commented': 'added a comment', 'comment_edited': 'edited a comment', 'comment_deleted': 'deleted a comment',
        'attachments_added': 'added attachments', 'attachment_deleted': 'deleted an attachment', 'deleted': 'deleted this ticket',
    }.get(event, 'updated this ticket')
    parts = [f'<p><strong>{html.escape(actor_name)}</strong> {did}.</p>']
    if own_ticket and own_ticket != number:
        parts.append(f'<p>This ticket mentions your ticket <strong>#{own_ticket}</strong>'
                     f'{f" ({html.escape(own_title)})" if own_title else ""}.</p>')
    status = STATUSES.get(str(ticket.get('status')), str(ticket.get('status') or ''))
    kind = TICKET_TYPES.get(str(ticket.get('ticket_type') or ''), '')
    priority = str(ticket.get('priority') or '')
    parts.append('<p style="color:#4b5563">' + ' · '.join(html.escape(item) for item in (
        f'Status: {status}', f'Priority: {priority} {PRIORITIES.get(priority, "")}'.strip(), f'Type: {kind}' if kind else '',
        f"Reported by: {names.get(str(ticket.get('created_by') or '').casefold(), ticket.get('created_by') or '')}") if item) + '</p>')
    rows = []
    for field, values in (changes or {}).items():
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
    if event == 'created' and ticket.get('description'):
        parts.append(text_block(_quoted(ticket['description']), base_url=base_url, tickets=references))
    if comment:
        parts.append(text_block(_quoted(comment), base_url=base_url, tickets=references))
    listed = [str(name) for name in files if str(name)]
    if listed:
        parts.append('<ul>' + ''.join(f'<li>{html.escape(name)}</li>' for name in listed) + '</ul>')
    link = None if event == 'deleted' or not base_url else (f'Open ticket #{number}', f'{base_url}/tickets/{number}')
    return subject, email_page(app_name, f'Ticket #{number}: {title}', parts, link=link)


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
        owners = ticket_recipients(repository, ticket, actor, include_actor=event == 'created')
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
            subject, body = ticket_email(app_name, ticket, event, names.get(str(actor).casefold(), str(actor)), base, names,
                                         changes=changes, comment=comment, files=listed, own_ticket=own_ticket, own_title=own_title,
                                         references=references)
            deliver(repository, kind='ticket', recipients=[address], subject=subject, html_body=body, actor=actor,
                    details={'ticket_id': int(ticket['id']), 'event': event, 'user': username.upper(),
                             'about_ticket': own_ticket}, switch='notify_tickets')
    except Exception as exc:  # Never let an email break the change it tells of.
        repository.try_add_log(actor or 'system', 'email_failed', json.dumps({
            'kind': 'ticket', 'ticket_id': ticket_id, 'event': event, 'error': str(exc)}, ensure_ascii=False))
