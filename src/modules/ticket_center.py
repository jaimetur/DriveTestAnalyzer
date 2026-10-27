"""Ticket Center: the tickets of the bugs, improvements and new features users ask for in the tool.

Every ticket has a type (Bug, Improvement or New Feature) and keeps the version of the tool it was opened with, its
date, a priority from P1 (most urgent) to P5 and a status, with its screenshots and a timeline of comments and changes.
The tables live in the application database (``tickets``, ``ticket_comments`` and ``ticket_attachments``), so the
tickets are shared by every workspace. Each ticket, comment and screenshot has a ``uid`` that identifies it on any
server, so a Ticket Center package merges into another server without duplicating anything.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import PurePosixPath
from typing import Any, Iterable

from src.modules.repository import Repository, local_now_iso

# The kinds of ticket, chosen when it is opened (the tickets of before the types are bugs).
TICKET_TYPES: dict[str, str] = {'bug': 'Bug', 'improvement': 'Improvement', 'new_feature': 'New Feature'}
DEFAULT_TICKET_TYPE = 'bug'
# What each type is for, under its name in the New Ticket form.
TICKET_TYPE_HINTS: dict[str, str] = {
    'bug': 'Something does not work as it should',
    'improvement': 'Something that works could work better',
    'new_feature': 'Something the tool cannot do yet',
}
PRIORITIES: dict[str, str] = {'P1': 'Critical', 'P2': 'High', 'P3': 'Medium', 'P4': 'Low', 'P5': 'Trivial'}
DEFAULT_PRIORITY = 'P3'
STATUSES: dict[str, str] = {
    'new': 'New', 'in_progress': 'In Progress', 'waiting_info': 'Waiting for Info',
    'resolved': 'Resolved', 'closed': 'Closed', 'rejected': 'Rejected',
}
OPEN_STATUSES = frozenset({'new', 'in_progress', 'waiting_info'})
# The statuses of a ticket that was done (fixed, or finished): the dashboard counts them as resolved.
DONE_STATUSES = frozenset({'resolved', 'closed'})
# The order of the statuses in the dashboard: the open ones, then Rejected, Closed and Resolved, last before the totals.
DASHBOARD_STATUSES = ('new', 'in_progress', 'waiting_info', 'rejected', 'closed', 'resolved')
MAX_TITLE_LENGTH = 160
MAX_TEXT_LENGTH = 20_000
MAX_VERSION_LENGTH = 40
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_UPLOAD = 10
# Screenshots only: the formats a browser shows as an image, recognised by their first bytes (never SVG, which can
# carry scripts).
IMAGE_EXTENSIONS = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/gif': '.gif', 'image/webp': '.webp'}
# What the timeline names each field of a ticket after.
FIELD_LABELS = {
    'title': 'Title', 'description': 'Description', 'ticket_type': 'Type', 'module': 'Module', 'priority': 'Priority',
    'status': 'Status', 'assigned_to': 'Assigned to', 'created_by': 'Reported by', 'app_version': 'Opened with',
    'fixed_version': 'Fixed in version',
}
REPORTER_FIELDS = frozenset({'title', 'description', 'module', 'priority'})
# Super-admins also change the type of a ticket, who reported it, its module and the version it was opened with.
MANAGER_FIELDS = frozenset({'status', 'ticket_type', 'assigned_to', 'created_by', 'module', 'app_version', 'fixed_version'})
EXPORT_FORMAT = 'drivetest-analyzer-ticket-center'
EXPORT_VERSION = 1
ATTACHMENTS_ARCHIVE_DIR = 'ticket-center/attachments'
# A ticket mentioned in a description or comment as #<number>: rich_text.js links it when the ticket exists (it also
# leaves out a number written inside a word, a web address or code).
TICKET_REFERENCE = re.compile(r'#([1-9][0-9]{0,8})')
# The dashboard: tickets resolved in these last days, and created and resolved per period (Weekly by default) in its
# last periods: the name of its choice, its unit, how many it shows, and every how many of them the axis has a label.
RECENT_RESOLVED_DAYS = 30
TREND_PERIODS: dict[str, tuple[str, str, int, int]] = {
    'day': ('Daily', 'day', 30, 7), 'week': ('Weekly', 'week', 12, 3), 'month': ('Monthly', 'month', 12, 3),
    'quarter': ('Quarterly', 'quarter', 8, 2), 'year': ('Yearly', 'year', 5, 1),
}
DEFAULT_TREND_PERIOD = 'week'


# How to write a description or a comment, shown in grey while it is empty (and as it reads, in its editor); a new ticket
# shows the guide of its type. The texts are Markdown, shown and edited by rich_text.js.
_TEXT_RULES = ('> [!TIP]\n> Use the toolbar or write Markdown: `#` heading, `-` or `1.` list (Tab nests it), `**bold**`, '
               '`*italic*`, `> [!WARNING]` card. A line followed by a list is its title.')
TEXT_GUIDE = ('Problem\n- What you did and what happened\n  - A detail, indented under it\nExpected\n- What should have happened\n\n'
              + _TEXT_RULES)
TEXT_GUIDES: dict[str, str] = {
    'bug': TEXT_GUIDE,
    'improvement': ('Today\n- How it works now\n  - A detail, indented under it\nProposal\n- How it could work better, and why\n\n'
                    + _TEXT_RULES),
    'new_feature': ('Need\n- What you want to do and why\n  - A detail, indented under it\nProposal\n- How the tool could do it\n\n'
                    + _TEXT_RULES),
}


def image_content_type(content: bytes) -> str | None:
    """The image type of a screenshot from its first bytes, or None when it is not a supported image."""
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if content.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if content.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        return 'image/webp'
    return None


def screenshot_files(files: Iterable[tuple[str, bytes]]) -> list[dict[str, Any]]:
    """The screenshots of an upload, checked: images of at most 10 MB, and at most 10 at once."""
    screenshots = []
    for file_name, content in files:
        if not content:
            continue
        name = PurePosixPath(str(file_name or '').replace('\\', '/')).name.strip()[:200] or 'screenshot'
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f'"{name}" is larger than {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB.')
        content_type = image_content_type(content)
        if content_type is None:
            raise ValueError(f'"{name}" is not a PNG, JPEG, GIF or WebP image.')
        if '.' not in name:
            name += IMAGE_EXTENSIONS[content_type]
        screenshots.append({'file_name': name, 'content_type': content_type, 'content': content})
    if len(screenshots) > MAX_ATTACHMENTS_PER_UPLOAD:
        raise ValueError(f'Attach at most {MAX_ATTACHMENTS_PER_UPLOAD} screenshots at once.')
    return screenshots


def _text(value: object, maximum: int) -> str:
    return str(value or '').replace('\r\n', '\n').strip()[:maximum]


def _new_uid() -> str:
    return uuid.uuid4().hex


def _insert_attachments(conn: Any, ticket_id: int, comment_id: int | None, username: str,
                        screenshots: Iterable[dict[str, Any]], created_at: str) -> int:
    count = 0
    for screenshot in screenshots:
        conn.execute(
            'INSERT INTO ticket_attachments (uid, ticket_id, comment_id, file_name, content_type, size, content, uploaded_by, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (screenshot.get('uid') or _new_uid(), ticket_id, comment_id, screenshot['file_name'], screenshot['content_type'],
             len(screenshot['content']), screenshot['content'], username, created_at),
        )
        count += 1
    return count


def create_ticket(repository: Repository, *, title: str, description: str, module: str, priority: str, username: str,
               app_version: str, ticket_type: str, browser: str = '', screenshots: Iterable[dict[str, Any]] = ()) -> int:
    """Open a ticket of a type with the version of the tool and the date; returns its id."""
    title = _text(title, MAX_TITLE_LENGTH)
    if not title:
        raise ValueError('Give the ticket a title.')
    if ticket_type not in TICKET_TYPES:
        raise ValueError('Choose the type of the ticket: Bug, Improvement or New Feature.')
    if priority not in PRIORITIES:
        raise ValueError('Choose a priority from P1 to P5.')
    now = local_now_iso()
    with repository.global_connection() as conn:
        cursor = conn.execute(
            'INSERT INTO tickets (uid, ticket_type, title, description, module, priority, status, app_version, browser, created_by, '
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?)",
            (_new_uid(), ticket_type, title, _text(description, MAX_TEXT_LENGTH), _text(module, 60), priority,
             _text(app_version, MAX_VERSION_LENGTH), _text(browser, 400), username, now, now),
        )
        ticket_id = int(cursor.lastrowid)
        _insert_attachments(conn, ticket_id, None, username, screenshots, now)
    return ticket_id


def list_tickets(repository: Repository) -> list[dict[str, Any]]:
    """Every ticket, the latest activity first, with how many comments and screenshots it has."""
    with repository.global_connection() as conn:
        rows = conn.execute(
            "SELECT t.*, "
            "(SELECT COUNT(*) FROM ticket_comments c WHERE c.ticket_id = t.id AND c.kind = 'comment') AS comment_count, "
            "(SELECT COUNT(*) FROM ticket_attachments a WHERE a.ticket_id = t.id) AS attachment_count "
            'FROM tickets t ORDER BY t.updated_at DESC, t.id DESC'
        ).fetchall()
    return [dict(row) for row in rows]


def local_today() -> date:
    """Today, in the server's local timezone (that of the dates of the tickets)."""
    return date.fromisoformat(local_now_iso()[:10])


def _day(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or '')[:10])
    except ValueError:
        return None


def recently_resolved(ticket: dict[str, Any], today: date) -> bool:
    """Whether a ticket was resolved (or closed) in the last ``RECENT_RESOLVED_DAYS`` days, today included."""
    resolved = _day(ticket.get('resolved_at'))
    return str(ticket.get('status')) in DONE_STATUSES and resolved is not None and (today - resolved).days < RECENT_RESOLVED_DAYS


def _period_index(period: str, day: date) -> int:
    """The number of the period of ``TREND_PERIODS`` a day falls in; consecutive periods have consecutive numbers."""
    if period == 'day':
        return day.toordinal()
    if period == 'week':
        return (day.toordinal() - 1) // 7  # Weeks from Monday: the first day of the calendar is a Monday.
    if period == 'month':
        return day.year * 12 + day.month - 1
    if period == 'quarter':
        return day.year * 4 + (day.month - 1) // 3
    return day.year


def _period_start(period: str, index: int) -> date:
    """The first day of the period numbered ``index`` by ``_period_index``."""
    if period == 'day':
        return date.fromordinal(index)
    if period == 'week':
        return date.fromordinal(index * 7 + 1)
    if period == 'month':
        return date(index // 12, index % 12 + 1, 1)
    if period == 'quarter':
        return date(index // 4, index % 4 * 3 + 1, 1)
    return date(index, 1, 1)


def _period_names(period: str, start: date) -> tuple[str, str]:
    """The label of a period under its bars, and what its tooltip calls it."""
    day = f"{start.day} {start.strftime('%b')}"
    if period == 'day':
        return day, f"{start.strftime('%a')} {day}"
    if period == 'week':
        return day, f'Week of {day}'
    if period == 'month':
        return f"{start.strftime('%b')} {start.year}", f"{start.strftime('%B')} {start.year}"
    if period == 'quarter':
        label = f'Q{(start.month - 1) // 3 + 1} {start.year}'
        return label, label
    return str(start.year), str(start.year)


def ticket_trend(tickets: list[dict[str, Any]], today: date, period: str = DEFAULT_TREND_PERIOD) -> dict[str, Any]:
    """The tickets created and those resolved (or closed) in each of the last periods of ``period`` (a key of
    ``TREND_PERIODS``), the current one last, with the height of their bars and which of them the axis labels."""
    choice, unit, count, step = TREND_PERIODS[period]
    last = _period_index(period, today)
    periods = []
    for index in range(last - count + 1, last + 1):
        start = _period_start(period, index)
        label, name = _period_names(period, start)
        periods.append({'start': start, 'label': label, 'name': name, 'axis': (last - index) % step == 0, 'created': 0, 'resolved': 0})
    for ticket in tickets:
        for key, day in (('created', _day(ticket.get('created_at'))),
                         ('resolved', _day(ticket.get('resolved_at')) if ticket['status'] in DONE_STATUSES else None)):
            position = _period_index(period, day) - last + count - 1 if day is not None and day <= today else -1
            if position >= 0:
                periods[position][key] += 1
    peak = max([1, *(max(entry['created'], entry['resolved']) for entry in periods)])
    for entry in periods:
        entry['created_height'] = round(100 * entry['created'] / peak, 2)
        entry['resolved_height'] = round(100 * entry['resolved'] / peak, 2)
    return {
        'period': period, 'choice': choice, 'title': f'Created vs resolved per {unit}', 'note': f'Last {count} {unit}s',
        'periods': periods, 'peak': peak,
        'created': sum(entry['created'] for entry in periods), 'resolved': sum(entry['resolved'] for entry in periods),
    }


def ticket_dashboard(tickets: list[dict[str, Any]], *, username: str | None = None, today: date | None = None) -> dict[str, Any]:
    """What the dashboard of Ticket Center counts from the tickets of the list (with their ``module_title`` and
    ``module_color``): the open ones by status, those resolved lately and those of ``username``; every ticket by type
    and status; the open ones of each type by priority and of each module; the tickets created and resolved in each of
    the last days, weeks (from Monday), months, quarters and years; and the oldest open ticket."""
    today = today or local_today()
    open_tickets = [ticket for ticket in tickets if ticket['status'] in OPEN_STATUSES]
    mine = (username or '').casefold()
    kpis = {
        'open': len(open_tickets),
        **{status: sum(1 for ticket in open_tickets if ticket['status'] == status) for status in ('new', 'in_progress', 'waiting_info')},
        'resolved_recent': sum(1 for ticket in tickets if recently_resolved(ticket, today)),
        'mine_open': sum(1 for ticket in open_tickets if mine and str(ticket['created_by']).casefold() == mine),
    }
    by_type: dict[str, list[dict[str, Any]]] = {ticket_type: [] for ticket_type in TICKET_TYPES}
    for ticket in tickets:
        by_type.setdefault(str(ticket.get('ticket_type') or DEFAULT_TICKET_TYPE), []).append(ticket)
    types = []
    for ticket_type, label in TICKET_TYPES.items():
        rows = by_type.get(ticket_type, [])
        counts = {status: sum(1 for ticket in rows if ticket['status'] == status) for status in DASHBOARD_STATUSES}
        opened = [ticket for ticket in rows if ticket['status'] in OPEN_STATUSES]
        priorities = {priority: sum(1 for ticket in opened if ticket['priority'] == priority) for priority in PRIORITIES}
        types.append({
            'type': ticket_type, 'label': label, 'counts': counts, 'total': len(rows), 'open': len(opened),
            'segments': [{'status': status, 'label': STATUSES[status], 'count': count, 'share': round(100 * count / len(rows), 2)}
                         for status, count in counts.items() if count],
            'priorities': [{'priority': priority, 'label': PRIORITIES[priority], 'count': count} for priority, count in priorities.items()],
            'max_priority': max(priorities.values()),
        })
    modules: dict[str, dict[str, Any]] = {}
    for ticket in open_tickets:
        key = str(ticket.get('module') or '')
        entry = modules.setdefault(key, {'key': key, 'title': ticket.get('module_title') or 'General',
                                         'color': ticket.get('module_color') or '#5A6773', 'count': 0})
        entry['count'] += 1
    module_rows = sorted(modules.values(), key=lambda entry: (-entry['count'], str(entry['title']).casefold()))
    oldest =min(open_tickets, key=lambda ticket: (str(ticket['created_at']), int(ticket['id'])), default=None)
    oldest_day = _day(oldest['created_at']) if oldest else None
    return {
        'kpis': kpis, 'types': types,
        'statuses': [(status, STATUSES[status]) for status in DASHBOARD_STATUSES],
        'status_totals': {status: sum(entry['counts'][status] for entry in types) for status in DASHBOARD_STATUSES},
        'total': len(tickets), 'modules': module_rows, 'max_module': max([1, *(entry['count'] for entry in module_rows)]),
        'trends': [ticket_trend(tickets, today, period) for period in TREND_PERIODS], 'trend_period': DEFAULT_TREND_PERIOD,
        'oldest_open': {'id': oldest['id'], 'title': oldest['title'], 'ticket_type': oldest.get('ticket_type') or DEFAULT_TICKET_TYPE,
                        'days': (today - oldest_day).days if oldest_day else 0,
                        'created_date': str(oldest['created_at'])[:10]} if oldest else None,
    }


def get_ticket(repository: Repository, ticket_id: int) -> dict[str, Any] | None:
    """A ticket with its timeline (comments and changes, oldest first) and the screenshots of each entry."""
    with repository.global_connection() as conn:
        row = conn.execute('SELECT * FROM tickets WHERE id = ?', (int(ticket_id),)).fetchone()
        if row is None:
            return None
        comments = [dict(item) for item in conn.execute(
            'SELECT id, uid, username, kind, body, changes_json, created_at, edited_at FROM ticket_comments WHERE ticket_id = ? ORDER BY id',
            (int(ticket_id),),
        ).fetchall()]
        attachments = [dict(item) for item in conn.execute(
            'SELECT id, uid, comment_id, file_name, content_type, size, uploaded_by, created_at FROM ticket_attachments '
            'WHERE ticket_id = ? ORDER BY id', (int(ticket_id),),
        ).fetchall()]
    by_comment: dict[int | None, list[dict[str, Any]]] = {}
    for attachment in attachments:
        by_comment.setdefault(attachment['comment_id'], []).append(attachment)
    for comment in comments:
        try:
            changes = json.loads(comment.pop('changes_json') or '{}')
        except (TypeError, ValueError):
            changes = {}
        comment['changes'] = changes if isinstance(changes, dict) else {}
        comment['attachments'] = by_comment.get(comment['id'], [])
    return {**dict(row), 'comments': comments, 'attachments': by_comment.get(None, [])}


def ticket_titles(repository: Repository) -> dict[int, str]:
    """The title of every ticket by its number, the oldest first: the order a ticket page goes through outside the list."""
    with repository.global_connection() as conn:
        return {int(row['id']): str(row['title']) for row in conn.execute('SELECT id, title FROM tickets ORDER BY id').fetchall()}


def ticket_neighbours(order: list[int], ticket_id: int) -> dict[str, Any]:
    """The first, previous, next and last tickets of an order around one of its tickets (None where it cannot move:
    before the first one and after the last one), and its position in it."""
    index = order.index(int(ticket_id))
    before, after = index > 0, index < len(order) - 1
    return {
        'first': order[0] if before else None, 'previous': order[index - 1] if before else None,
        'next': order[index + 1] if after else None, 'last': order[-1] if after else None,
        'position': index + 1, 'total': len(order),
    }


def ticket_references(repository: Repository, texts: Iterable[object]) -> dict[str, Any]:
    """The references of rich_text.js for texts of tickets: #7 opens ticket 7, its title and status in the tooltip, when it
    exists (a number of no ticket stays text)."""
    numbers = {int(number) for text in texts for number in TICKET_REFERENCE.findall(str(text or ''))}
    titles: dict[str, str] = {}
    if numbers:
        with repository.global_connection() as conn:
            for row in conn.execute('SELECT id, title, status FROM tickets').fetchall():
                if int(row['id']) in numbers:
                    titles[str(row['id'])] = f"{row['title']} · {STATUSES.get(str(row['status']), str(row['status']))}"
    return {'href': '/tickets/{id}', 'titles': titles, 'help': 'A link to ticket 7, once the text is saved'}


def update_ticket(repository: Repository, ticket_id: int, username: str, values: dict[str, Any]) -> dict[str, list[str]]:
    """Change fields of a ticket, recording what changed in its timeline; returns the changes as {field: [old, new]}."""
    with repository.global_connection() as conn:
        row = conn.execute('SELECT * FROM tickets WHERE id = ?', (int(ticket_id),)).fetchone()
        if row is None:
            raise LookupError('The ticket does not exist.')
        changes: dict[str, list[str]] = {}
        for field, value in values.items():
            if field not in FIELD_LABELS:
                continue
            maximum = {'title': MAX_TITLE_LENGTH, 'description': MAX_TEXT_LENGTH, 'app_version': MAX_VERSION_LENGTH,
                       'fixed_version': MAX_VERSION_LENGTH}.get(field, 120)
            value = _text(value, maximum)
            if field == 'title' and not value:
                raise ValueError('Give the ticket a title.')
            if field == 'created_by' and not value:
                raise ValueError('Choose who reported the ticket.')
            if field == 'app_version' and not value:
                raise ValueError('Give the version the ticket was opened with.')
            if field == 'ticket_type' and value not in TICKET_TYPES:
                raise ValueError('Choose the type of the ticket: Bug, Improvement or New Feature.')
            if field == 'priority' and value not in PRIORITIES:
                raise ValueError('Choose a priority from P1 to P5.')
            if field == 'status' and value not in STATUSES:
                raise ValueError('Choose a valid status.')
            if value != str(row[field] or ''):
                changes[field] = [str(row[field] or ''), value]
        if not changes:
            return {}
        now = local_now_iso()
        assignments = {field: new for field, (_old, new) in changes.items()}
        if 'status' in changes:
            # The date a ticket was resolved, closed or rejected; reopening it clears that date.
            assignments['resolved_at'] = '' if changes['status'][1] in OPEN_STATUSES else (row['resolved_at'] or now)
        assignments['updated_at'] = now
        conn.execute(
            f"UPDATE tickets SET {', '.join(f'{field} = ?' for field in assignments)} WHERE id = ?",
            (*assignments.values(), int(ticket_id)),
        )
        conn.execute(
            "INSERT INTO ticket_comments (uid, ticket_id, username, kind, body, changes_json, created_at) VALUES (?, ?, ?, 'change', '', ?, ?)",
            (_new_uid(), int(ticket_id), username, json.dumps(changes, ensure_ascii=False), now),
        )
    return changes


def ticket_date(value: object) -> datetime:
    """A date of a ticket as the Manage form gives it (``2026-10-20T15:35``, also with seconds or an offset); without an
    offset it is the time of the server on that day."""
    text = str(value or '').strip().replace(' ', 'T', 1)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError('Give the dates of the ticket as YYYY-MM-DD HH:MM.') from exc
    return moment.astimezone() if moment.tzinfo is None else moment


def _moment(value: object) -> datetime | None:
    try:
        return ticket_date(value) if str(value or '').strip() else None
    except ValueError:
        return None


def _minute(moment: datetime | None) -> str:
    return moment.strftime('%Y-%m-%dT%H:%M') if moment else ''


def set_ticket_dates(repository: Repository, ticket_id: int, opened: object = None,
                     resolved: object = None) -> dict[str, list[str]]:
    """Move the opening and the resolution of a ticket to other dates (such as a ticket recorded after the work it
    describes), with its timeline. The change that set its current status and the comment just before it (its
    resolution) follow the Resolved date; the entries before them that fall before the Opened date or after the Resolved
    date follow the Opened date; the others (those between both, and those after the resolution) keep theirs, and every
    entry stays in its order. A date given to the minute it already has changes nothing. Returns the changes as
    {field: [old, new]}; the timeline records none of them."""
    with repository.global_connection() as conn:
        row = conn.execute('SELECT status, created_at, resolved_at FROM tickets WHERE id = ?', (int(ticket_id),)).fetchone()
        if row is None:
            raise LookupError('The ticket does not exist.')
        old_opened, old_resolved = _moment(row['created_at']), _moment(row['resolved_at'])
        new_opened = ticket_date(opened) if str(opened or '').strip() else old_opened
        new_resolved = old_resolved
        if str(resolved or '').strip():
            if row['status'] in OPEN_STATUSES:
                raise ValueError('Only a resolved, closed or rejected ticket has a Resolved date.')
            new_resolved = ticket_date(resolved)
        if _minute(new_opened) == _minute(old_opened):
            new_opened = old_opened
        if _minute(new_resolved) == _minute(old_resolved):
            new_resolved = old_resolved
        if new_opened == old_opened and new_resolved == old_resolved:
            return {}
        if new_opened and new_resolved and new_resolved < new_opened:
            raise ValueError('The Resolved date cannot be before the Opened date.')
        opening_shift = new_opened - old_opened if new_opened and old_opened else timedelta()
        resolution_shift = new_resolved - old_resolved if new_resolved and old_resolved else timedelta()
        entries = [dict(entry) for entry in conn.execute(
            'SELECT id, kind, changes_json, created_at FROM ticket_comments WHERE ticket_id = ? ORDER BY id', (int(ticket_id),),
        ).fetchall()]
        # The resolution: the latest change to a status that is not open, and the comment just before it.
        resolution: set[int] = set()
        if row['status'] not in OPEN_STATUSES:
            for index in range(len(entries) - 1, -1, -1):
                try:
                    status_change = json.loads(entries[index]['changes_json'] or '{}').get('status')
                except (TypeError, ValueError, AttributeError):
                    status_change = None
                if entries[index]['kind'] == 'change' and isinstance(status_change, list) and status_change[-1] not in OPEN_STATUSES:
                    resolution.add(entries[index]['id'])
                    if index and entries[index - 1]['kind'] == 'comment':
                        resolution.add(entries[index - 1]['id'])
                    break
        moved: dict[int, datetime] = {}
        previous: datetime | None = None
        def outside(moment: datetime) -> bool:
            return bool((new_opened and moment < new_opened) or (new_resolved and moment > new_resolved))

        for entry in entries:
            moment = _moment(entry['created_at'])
            if moment is None:
                continue
            if entry['id'] in resolution:
                target = moment + resolution_shift
                # (One written within the minute before it shows the minute of the Resolved date, as its change.)
                minute = new_resolved.replace(second=0, microsecond=0) if new_resolved and resolution_shift else None
                if minute and minute - timedelta(minutes=1) <= target < minute:
                    target = minute
            elif outside(moment) and (not resolution or entry['id'] < min(resolution)):
                target = moment + opening_shift
            else:
                target = moment
            # The timeline lists its entries in their order: none goes before the one before it.
            if previous and target < previous:
                target = previous + timedelta(seconds=1)
            previous = target
            if target != moment:
                moved[entry['id']] = target
        changes: dict[str, list[str]] = {}
        assignments: dict[str, str] = {}
        # Each date is written in the time of the server on its own day (as it was then, summer or winter time).
        def stamp(moment: datetime) -> str:
            return moment.astimezone().isoformat(timespec='microseconds')

        if new_opened != old_opened:
            assignments['created_at'] = stamp(new_opened)
            changes['created_at'] = [str(row['created_at'] or ''), assignments['created_at']]
        if new_resolved != old_resolved:
            assignments['resolved_at'] = stamp(new_resolved)
            changes['resolved_at'] = [str(row['resolved_at'] or ''), assignments['resolved_at']]
        for entry_id, moment in moved.items():
            conn.execute('UPDATE ticket_comments SET created_at = ? WHERE id = ?', (stamp(moment), entry_id))
        # The screenshots of a comment keep its date; those of the ticket itself, its opening.
        for attachment in conn.execute('SELECT id, comment_id, created_at FROM ticket_attachments WHERE ticket_id = ?',
                                       (int(ticket_id),)).fetchall():
            moment = _moment(attachment['created_at'])
            if attachment['comment_id'] is not None and attachment['comment_id'] in moved:
                target = moved[attachment['comment_id']]
            elif attachment['comment_id'] is None and moment and outside(moment):
                target = max(moment + opening_shift, new_opened) if new_opened else moment + opening_shift
            else:
                continue
            conn.execute('UPDATE ticket_attachments SET created_at = ? WHERE id = ?', (stamp(target), attachment['id']))
        # Its last update: the latest of its dates and of its timeline.
        latest = max([moment for moment in (new_opened, new_resolved) if moment]
                     + [moved.get(entry['id']) or _moment(entry['created_at']) for entry in entries if _moment(entry['created_at'])])
        assignments['updated_at'] = stamp(latest)
        conn.execute(f"UPDATE tickets SET {', '.join(f'{field} = ?' for field in assignments)} WHERE id = ?",
                     (*assignments.values(), int(ticket_id)))
    return changes


def add_comment(repository: Repository, ticket_id: int, username: str, body: str,
                screenshots: Iterable[dict[str, Any]] = ()) -> int:
    """Add a comment, with its screenshots, to the timeline of a ticket; returns its id."""
    body = _text(body, MAX_TEXT_LENGTH)
    screenshots = list(screenshots)
    if not body and not screenshots:
        raise ValueError('Write a comment or attach a screenshot.')
    now = local_now_iso()
    with repository.global_connection() as conn:
        if conn.execute('SELECT 1 FROM tickets WHERE id = ?', (int(ticket_id),)).fetchone() is None:
            raise LookupError('The ticket does not exist.')
        cursor = conn.execute(
            "INSERT INTO ticket_comments (uid, ticket_id, username, kind, body, created_at) VALUES (?, ?, ?, 'comment', ?, ?)",
            (_new_uid(), int(ticket_id), username, body, now),
        )
        comment_id = int(cursor.lastrowid)
        _insert_attachments(conn, int(ticket_id), comment_id, username, screenshots, now)
        conn.execute('UPDATE tickets SET updated_at = ? WHERE id = ?', (now, int(ticket_id)))
    return comment_id


def get_comment(repository: Repository, comment_id: int) -> dict[str, Any] | None:
    with repository.global_connection() as conn:
        row = conn.execute('SELECT * FROM ticket_comments WHERE id = ?', (int(comment_id),)).fetchone()
    return dict(row) if row else None


def edit_comment(repository: Repository, comment_id: int, body: str) -> None:
    body = _text(body, MAX_TEXT_LENGTH)
    if not body:
        raise ValueError('Write the comment, or delete it.')
    with repository.global_connection() as conn:
        conn.execute("UPDATE ticket_comments SET body = ?, edited_at = ? WHERE id = ? AND kind = 'comment'",
                     (body, local_now_iso(), int(comment_id)))


def delete_comment(repository: Repository, comment_id: int) -> None:
    """Delete a comment and its screenshots."""
    with repository.global_connection() as conn:
        conn.execute('DELETE FROM ticket_attachments WHERE comment_id = ?', (int(comment_id),))
        conn.execute("DELETE FROM ticket_comments WHERE id = ? AND kind = 'comment'", (int(comment_id),))


def add_attachments(repository: Repository, ticket_id: int, username: str, screenshots: Iterable[dict[str, Any]]) -> int:
    """Add screenshots to a ticket itself; returns how many."""
    now = local_now_iso()
    with repository.global_connection() as conn:
        if conn.execute('SELECT 1 FROM tickets WHERE id = ?', (int(ticket_id),)).fetchone() is None:
            raise LookupError('The ticket does not exist.')
        count = _insert_attachments(conn, int(ticket_id), None, username, screenshots, now)
        if count:
            conn.execute('UPDATE tickets SET updated_at = ? WHERE id = ?', (now, int(ticket_id)))
    return count


def get_attachment(repository: Repository, attachment_id: int, *, with_content: bool = True) -> dict[str, Any] | None:
    columns = '*' if with_content else 'id, uid, ticket_id, comment_id, file_name, content_type, size, uploaded_by, created_at'
    with repository.global_connection() as conn:
        row = conn.execute(f'SELECT {columns} FROM ticket_attachments WHERE id = ?', (int(attachment_id),)).fetchone()
    return dict(row) if row else None


def delete_attachment(repository: Repository, attachment_id: int) -> None:
    with repository.global_connection() as conn:
        conn.execute('DELETE FROM ticket_attachments WHERE id = ?', (int(attachment_id),))


def delete_ticket(repository: Repository, ticket_id: int) -> None:
    """Delete a ticket with its timeline and screenshots."""
    with repository.global_connection() as conn:
        conn.execute('DELETE FROM ticket_attachments WHERE ticket_id = ?', (int(ticket_id),))
        conn.execute('DELETE FROM ticket_comments WHERE ticket_id = ?', (int(ticket_id),))
        conn.execute('DELETE FROM tickets WHERE id = ?', (int(ticket_id),))


def _attachment_archive_path(attachment: dict[str, Any]) -> str:
    return f"{ATTACHMENTS_ARCHIVE_DIR}/{attachment['uid']}{IMAGE_EXTENSIONS.get(str(attachment['content_type']), '')}"


def ticket_center_payload(repository: Repository, *, screenshots: bool = True) -> tuple[dict[str, Any], dict[str, bytes]]:
    """The Ticket Center package: every ticket with its type and timeline in one JSON document, and each screenshot as
    a file (its archive path → its content; none without ``screenshots``, which only the document needs)."""
    files: dict[str, bytes] = {}
    columns = '*' if screenshots else 'id, uid, ticket_id, comment_id, file_name, content_type, size, uploaded_by, created_at'
    with repository.global_connection() as conn:
        rows = [dict(row) for row in conn.execute('SELECT * FROM tickets ORDER BY id').fetchall()]
        comments = [dict(row) for row in conn.execute('SELECT * FROM ticket_comments ORDER BY id').fetchall()]
        attachments = [dict(row) for row in conn.execute(f'SELECT {columns} FROM ticket_attachments ORDER BY id').fetchall()]
    comment_uids = {comment['id']: comment['uid'] for comment in comments}
    tickets = {}
    for row in rows:
        ticket_id = row.pop('id')
        tickets[ticket_id] = {**row, 'comments': [], 'attachments': []}
    for comment in comments:
        ticket = tickets.get(comment['ticket_id'])
        if ticket is None:
            continue
        try:
            changes = json.loads(comment['changes_json'] or '{}')
        except (TypeError, ValueError):
            changes = {}
        ticket['comments'].append({key: comment[key] for key in ('uid', 'username', 'kind', 'body', 'created_at', 'edited_at')}
                                  | {'changes': changes if isinstance(changes, dict) else {}})
    for attachment in attachments:
        ticket = tickets.get(attachment['ticket_id'])
        if ticket is None:
            continue
        path = _attachment_archive_path(attachment)
        if screenshots:
            files[path] = bytes(attachment['content'])
        ticket['attachments'].append({
            'uid': attachment['uid'], 'comment_uid': comment_uids.get(attachment['comment_id']) if attachment['comment_id'] else None,
            'file_name': attachment['file_name'], 'content_type': attachment['content_type'], 'size': attachment['size'],
            'uploaded_by': attachment['uploaded_by'], 'created_at': attachment['created_at'], 'path': path,
        })
    return {'format': EXPORT_FORMAT, 'version': EXPORT_VERSION, 'tickets': list(tickets.values())}, files


def merge_ticket_center(repository: Repository, payload: object, files: dict[str, bytes]) -> dict[str, int]:
    """Merge a Ticket Center package: the tickets, comments and screenshots this server does not have are added, and a
    ticket or comment changed later on the other server takes its newer content. Nothing here is deleted; a ticket
    without a valid type is a bug."""
    if not isinstance(payload, dict) or payload.get('format') != EXPORT_FORMAT or not isinstance(payload.get('tickets'), list):
        raise ValueError('The Ticket Center file is not valid.')
    summary = {'created': 0, 'updated': 0, 'comments': 0, 'screenshots': 0}
    fields = ('ticket_type', 'title', 'description', 'module', 'priority', 'status', 'app_version', 'fixed_version', 'browser',
              'created_by', 'assigned_to', 'created_at', 'updated_at', 'resolved_at')
    with repository.global_connection() as conn:
        for ticket in payload['tickets']:
            if not isinstance(ticket, dict) or not str(ticket.get('uid') or '').strip() or not str(ticket.get('title') or '').strip():
                continue
            values = {field: str(ticket.get(field) or '') for field in fields}
            if values['ticket_type'] not in TICKET_TYPES:
                values['ticket_type'] = DEFAULT_TICKET_TYPE
            if values['priority'] not in PRIORITIES:
                values['priority'] = DEFAULT_PRIORITY
            if values['status'] not in STATUSES:
                values['status'] = 'new'
            values['created_by'] = values['created_by'] or 'import'
            values['created_at'] = values['created_at'] or local_now_iso()
            values['updated_at'] = values['updated_at'] or values['created_at']
            existing = conn.execute('SELECT id, updated_at FROM tickets WHERE uid = ?', (str(ticket['uid']),)).fetchone()
            if existing is None:
                cursor = conn.execute(
                    f"INSERT INTO tickets (uid, {', '.join(fields)}) VALUES (?, {', '.join('?' for _ in fields)})",
                    (str(ticket['uid']), *values.values()),
                )
                ticket_id = int(cursor.lastrowid)
                summary['created'] += 1
            else:
                ticket_id = int(existing['id'])
                if values['updated_at'] > str(existing['updated_at'] or ''):
                    conn.execute(f"UPDATE tickets SET {', '.join(f'{field} = ?' for field in fields)} WHERE id = ?",
                                 (*values.values(), ticket_id))
                    summary['updated'] += 1
            comment_ids: dict[str, int] = {}
            for comment in ticket.get('comments') if isinstance(ticket.get('comments'), list) else []:
                if not isinstance(comment, dict) or not str(comment.get('uid') or '').strip():
                    continue
                uid = str(comment['uid'])
                kind = 'change' if comment.get('kind') == 'change' else 'comment'
                changes = comment.get('changes') if isinstance(comment.get('changes'), dict) else {}
                local = conn.execute('SELECT id, edited_at FROM ticket_comments WHERE uid = ?', (uid,)).fetchone()
                if local is None:
                    cursor = conn.execute(
                        'INSERT INTO ticket_comments (uid, ticket_id, username, kind, body, changes_json, created_at, edited_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (uid, ticket_id, str(comment.get('username') or 'import'), kind, str(comment.get('body') or ''),
                         json.dumps(changes, ensure_ascii=False), str(comment.get('created_at') or values['created_at']),
                         str(comment.get('edited_at') or '')),
                    )
                    comment_ids[uid] = int(cursor.lastrowid)
                    summary['comments'] += kind == 'comment'
                else:
                    comment_ids[uid] = int(local['id'])
                    if str(comment.get('edited_at') or '') > str(local['edited_at'] or ''):
                        conn.execute('UPDATE ticket_comments SET body = ?, edited_at = ? WHERE id = ?',
                                     (str(comment.get('body') or ''), str(comment.get('edited_at') or ''), int(local['id'])))
            for attachment in ticket.get('attachments') if isinstance(ticket.get('attachments'), list) else []:
                if not isinstance(attachment, dict) or not str(attachment.get('uid') or '').strip():
                    continue
                if conn.execute('SELECT 1 FROM ticket_attachments WHERE uid = ?', (str(attachment['uid']),)).fetchone():
                    continue
                content = files.get(str(attachment.get('path') or ''))
                content_type = image_content_type(content) if content else None
                if content_type is None:
                    continue
                comment_uid = str(attachment.get('comment_uid') or '')
                comment_id = comment_ids.get(comment_uid) if comment_uid else None
                if comment_uid and comment_id is None:
                    continue
                _insert_attachments(conn, ticket_id, comment_id, str(attachment.get('uploaded_by') or 'import'), [{
                    'uid': str(attachment['uid']), 'file_name': str(attachment.get('file_name') or 'screenshot')[:200],
                    'content_type': content_type, 'content': content,
                }], str(attachment.get('created_at') or values['created_at']))
                summary['screenshots'] += 1
    return summary
