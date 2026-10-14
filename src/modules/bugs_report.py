"""Bugs Report: the tickets of the bugs users find in the tool.

Every ticket keeps the version of the tool it was opened with, its date, a priority from P1 (most urgent) to P5 and
a status, with its screenshots and a timeline of comments and changes. The tables live in the application database
(``bug_reports``, ``bug_report_comments`` and ``bug_report_attachments``), so the tickets are shared by every
workspace. Each ticket, comment and screenshot has a ``uid`` that identifies it on any server, so a Bugs Report
package merges into another server without duplicating anything.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import PurePosixPath
from typing import Any, Iterable

from markupsafe import Markup, escape

from src.modules.repository import Repository, local_now_iso

PRIORITIES: dict[str, str] = {'P1': 'Critical', 'P2': 'High', 'P3': 'Medium', 'P4': 'Low', 'P5': 'Trivial'}
DEFAULT_PRIORITY = 'P3'
STATUSES: dict[str, str] = {
    'new': 'New', 'in_progress': 'In Progress', 'waiting_info': 'Waiting for Info',
    'resolved': 'Resolved', 'closed': 'Closed', 'rejected': 'Rejected',
}
OPEN_STATUSES = frozenset({'new', 'in_progress', 'waiting_info'})
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
    'title': 'Title', 'description': 'Description', 'module': 'Module', 'priority': 'Priority', 'status': 'Status',
    'assigned_to': 'Assigned to', 'fixed_version': 'Fixed in version',
}
REPORTER_FIELDS = frozenset({'title', 'description', 'module', 'priority'})
MANAGER_FIELDS = frozenset({'status', 'assigned_to', 'fixed_version'})
EXPORT_FORMAT = 'drivetest-analyzer-bugs-report'
EXPORT_VERSION = 1
ATTACHMENTS_ARCHIVE_DIR = 'bugs-report/attachments'


_BULLET = re.compile(r'^[-*·•]\s+')
_DIVIDER = re.compile(r'^[-=_*]{3,}\s*(.*?)\s*[-=_*]{3,}$|^[-=_*]{3,}$')
MAX_HEADING_LENGTH = 80
# How to write a description or a comment, shown in grey while it is empty.
TEXT_GUIDE = ('Problem:\n- What you did and what happened\n  - A detail, indented under it\nExpected:\n- What should have happened\n\n'
              'Lines starting with -, * or · are bullets; a line ending with : is a title; other lines are paragraphs.')


def rich_text_html(text: object) -> Markup:
    """A description or comment as its page shows it.

    A line starting with -, *, · or • is a bullet, nested under the bullet above it as deep as it is indented (with
    spaces or tabs); an indented line without a marker goes on in the bullet above it. A short line ending with a colon
    is a heading (and a bullet ending with one, a heading of the bullets below it); a line of dashes (----- Text -----)
    is a divider with its text. Every other line is part of a paragraph, and an empty line ends it.
    """
    parts: list[str] = []
    indents: list[int] = []
    paragraph: list[str] = []

    def end_paragraph() -> None:
        if paragraph:
            parts.append(f"<p>{'<br>'.join(paragraph)}</p>")
            paragraph.clear()

    def end_lists() -> None:
        while indents:
            parts.append('</li></ul>')
            indents.pop()

    for raw in str(text or '').replace('\r\n', '\n').split('\n'):
        indent = len(re.match(r'\s*', raw.expandtabs(4)).group(0))
        line = raw.strip()
        if not line:
            end_paragraph()
            end_lists()
            continue
        bullet = _BULLET.match(line)
        if bullet:
            end_paragraph()
            while indents and indent < indents[-1]:
                parts.append('</li></ul>')
                indents.pop()
            if indents and indent == indents[-1]:
                parts.append('</li>')
            else:
                parts.append('<ul>')
                indents.append(indent)
            item = line[bullet.end():]
            content = escape(item)
            parts.append(f'<li><span class="bug-text-heading">{content}</span>' if item.endswith(':') else f'<li>{content}')
            continue
        if indents and indent > 0:
            parts.append(f'<br>{escape(line)}')
            continue
        end_lists()
        divider = _DIVIDER.match(line)
        if divider:
            end_paragraph()
            parts.append(f'<p class="bug-text-divider">{escape(divider.group(1) or "")}</p>')
        elif line.endswith(':') and len(line) <= MAX_HEADING_LENGTH:
            end_paragraph()
            parts.append(f'<p class="bug-text-heading">{escape(line)}</p>')
        else:
            paragraph.append(str(escape(line)))
    end_paragraph()
    end_lists()
    return Markup(''.join(parts))


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


def _insert_attachments(conn: Any, bug_id: int, comment_id: int | None, username: str,
                        screenshots: Iterable[dict[str, Any]], created_at: str) -> int:
    count = 0
    for screenshot in screenshots:
        conn.execute(
            'INSERT INTO bug_report_attachments (uid, bug_id, comment_id, file_name, content_type, size, content, uploaded_by, created_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (screenshot.get('uid') or _new_uid(), bug_id, comment_id, screenshot['file_name'], screenshot['content_type'],
             len(screenshot['content']), screenshot['content'], username, created_at),
        )
        count += 1
    return count


def create_bug(repository: Repository, *, title: str, description: str, module: str, priority: str, username: str,
               app_version: str, browser: str = '', screenshots: Iterable[dict[str, Any]] = ()) -> int:
    """Open a ticket with the version of the tool and the date; returns its id."""
    title = _text(title, MAX_TITLE_LENGTH)
    if not title:
        raise ValueError('Give the bug a title.')
    if priority not in PRIORITIES:
        raise ValueError('Choose a priority from P1 to P5.')
    now = local_now_iso()
    with repository.global_connection() as conn:
        cursor = conn.execute(
            'INSERT INTO bug_reports (uid, title, description, module, priority, status, app_version, browser, created_by, created_at, updated_at) '
            "VALUES (?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?)",
            (_new_uid(), title, _text(description, MAX_TEXT_LENGTH), _text(module, 60), priority,
             _text(app_version, MAX_VERSION_LENGTH), _text(browser, 400), username, now, now),
        )
        bug_id = int(cursor.lastrowid)
        _insert_attachments(conn, bug_id, None, username, screenshots, now)
    return bug_id


def list_bugs(repository: Repository) -> list[dict[str, Any]]:
    """Every ticket, the latest activity first, with how many comments and screenshots it has."""
    with repository.global_connection() as conn:
        rows = conn.execute(
            "SELECT b.*, "
            "(SELECT COUNT(*) FROM bug_report_comments c WHERE c.bug_id = b.id AND c.kind = 'comment') AS comment_count, "
            "(SELECT COUNT(*) FROM bug_report_attachments a WHERE a.bug_id = b.id) AS attachment_count "
            'FROM bug_reports b ORDER BY b.updated_at DESC, b.id DESC'
        ).fetchall()
    return [dict(row) for row in rows]


def get_bug(repository: Repository, bug_id: int) -> dict[str, Any] | None:
    """A ticket with its timeline (comments and changes, oldest first) and the screenshots of each entry."""
    with repository.global_connection() as conn:
        row = conn.execute('SELECT * FROM bug_reports WHERE id = ?', (int(bug_id),)).fetchone()
        if row is None:
            return None
        comments = [dict(item) for item in conn.execute(
            'SELECT id, uid, username, kind, body, changes_json, created_at, edited_at FROM bug_report_comments WHERE bug_id = ? ORDER BY id',
            (int(bug_id),),
        ).fetchall()]
        attachments = [dict(item) for item in conn.execute(
            'SELECT id, uid, comment_id, file_name, content_type, size, uploaded_by, created_at FROM bug_report_attachments '
            'WHERE bug_id = ? ORDER BY id', (int(bug_id),),
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


def update_bug(repository: Repository, bug_id: int, username: str, values: dict[str, Any]) -> dict[str, list[str]]:
    """Change fields of a ticket, recording what changed in its timeline; returns the changes as {field: [old, new]}."""
    with repository.global_connection() as conn:
        row = conn.execute('SELECT * FROM bug_reports WHERE id = ?', (int(bug_id),)).fetchone()
        if row is None:
            raise LookupError('The bug report does not exist.')
        changes: dict[str, list[str]] = {}
        for field, value in values.items():
            if field not in FIELD_LABELS:
                continue
            maximum = MAX_TITLE_LENGTH if field == 'title' else MAX_TEXT_LENGTH if field == 'description' else 120
            value = _text(value, maximum)
            if field == 'title' and not value:
                raise ValueError('Give the bug a title.')
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
            f"UPDATE bug_reports SET {', '.join(f'{field} = ?' for field in assignments)} WHERE id = ?",
            (*assignments.values(), int(bug_id)),
        )
        conn.execute(
            "INSERT INTO bug_report_comments (uid, bug_id, username, kind, body, changes_json, created_at) VALUES (?, ?, ?, 'change', '', ?, ?)",
            (_new_uid(), int(bug_id), username, json.dumps(changes, ensure_ascii=False), now),
        )
    return changes


def add_comment(repository: Repository, bug_id: int, username: str, body: str,
                screenshots: Iterable[dict[str, Any]] = ()) -> int:
    """Add a comment, with its screenshots, to the timeline of a ticket; returns its id."""
    body = _text(body, MAX_TEXT_LENGTH)
    screenshots = list(screenshots)
    if not body and not screenshots:
        raise ValueError('Write a comment or attach a screenshot.')
    now = local_now_iso()
    with repository.global_connection() as conn:
        if conn.execute('SELECT 1 FROM bug_reports WHERE id = ?', (int(bug_id),)).fetchone() is None:
            raise LookupError('The bug report does not exist.')
        cursor = conn.execute(
            "INSERT INTO bug_report_comments (uid, bug_id, username, kind, body, created_at) VALUES (?, ?, ?, 'comment', ?, ?)",
            (_new_uid(), int(bug_id), username, body, now),
        )
        comment_id = int(cursor.lastrowid)
        _insert_attachments(conn, int(bug_id), comment_id, username, screenshots, now)
        conn.execute('UPDATE bug_reports SET updated_at = ? WHERE id = ?', (now, int(bug_id)))
    return comment_id


def get_comment(repository: Repository, comment_id: int) -> dict[str, Any] | None:
    with repository.global_connection() as conn:
        row = conn.execute('SELECT * FROM bug_report_comments WHERE id = ?', (int(comment_id),)).fetchone()
    return dict(row) if row else None


def edit_comment(repository: Repository, comment_id: int, body: str) -> None:
    body = _text(body, MAX_TEXT_LENGTH)
    if not body:
        raise ValueError('Write the comment, or delete it.')
    with repository.global_connection() as conn:
        conn.execute("UPDATE bug_report_comments SET body = ?, edited_at = ? WHERE id = ? AND kind = 'comment'",
                     (body, local_now_iso(), int(comment_id)))


def delete_comment(repository: Repository, comment_id: int) -> None:
    """Delete a comment and its screenshots."""
    with repository.global_connection() as conn:
        conn.execute('DELETE FROM bug_report_attachments WHERE comment_id = ?', (int(comment_id),))
        conn.execute("DELETE FROM bug_report_comments WHERE id = ? AND kind = 'comment'", (int(comment_id),))


def add_attachments(repository: Repository, bug_id: int, username: str, screenshots: Iterable[dict[str, Any]]) -> int:
    """Add screenshots to a ticket itself; returns how many."""
    now = local_now_iso()
    with repository.global_connection() as conn:
        if conn.execute('SELECT 1 FROM bug_reports WHERE id = ?', (int(bug_id),)).fetchone() is None:
            raise LookupError('The bug report does not exist.')
        count = _insert_attachments(conn, int(bug_id), None, username, screenshots, now)
        if count:
            conn.execute('UPDATE bug_reports SET updated_at = ? WHERE id = ?', (now, int(bug_id)))
    return count


def get_attachment(repository: Repository, attachment_id: int, *, with_content: bool = True) -> dict[str, Any] | None:
    columns = '*' if with_content else 'id, uid, bug_id, comment_id, file_name, content_type, size, uploaded_by, created_at'
    with repository.global_connection() as conn:
        row = conn.execute(f'SELECT {columns} FROM bug_report_attachments WHERE id = ?', (int(attachment_id),)).fetchone()
    return dict(row) if row else None


def delete_attachment(repository: Repository, attachment_id: int) -> None:
    with repository.global_connection() as conn:
        conn.execute('DELETE FROM bug_report_attachments WHERE id = ?', (int(attachment_id),))


def delete_bug(repository: Repository, bug_id: int) -> None:
    """Delete a ticket with its timeline and screenshots."""
    with repository.global_connection() as conn:
        conn.execute('DELETE FROM bug_report_attachments WHERE bug_id = ?', (int(bug_id),))
        conn.execute('DELETE FROM bug_report_comments WHERE bug_id = ?', (int(bug_id),))
        conn.execute('DELETE FROM bug_reports WHERE id = ?', (int(bug_id),))


def _attachment_archive_path(attachment: dict[str, Any]) -> str:
    return f"{ATTACHMENTS_ARCHIVE_DIR}/{attachment['uid']}{IMAGE_EXTENSIONS.get(str(attachment['content_type']), '')}"


def bugs_report_payload(repository: Repository) -> tuple[dict[str, Any], dict[str, bytes]]:
    """The Bugs Report package: every ticket with its timeline in one JSON document, and each screenshot as a file
    (its archive path → its content)."""
    files: dict[str, bytes] = {}
    with repository.global_connection() as conn:
        bugs = [dict(row) for row in conn.execute('SELECT * FROM bug_reports ORDER BY id').fetchall()]
        comments = [dict(row) for row in conn.execute('SELECT * FROM bug_report_comments ORDER BY id').fetchall()]
        attachments = [dict(row) for row in conn.execute('SELECT * FROM bug_report_attachments ORDER BY id').fetchall()]
    comment_uids = {comment['id']: comment['uid'] for comment in comments}
    tickets = {}
    for bug in bugs:
        bug_id = bug.pop('id')
        tickets[bug_id] = {**bug, 'comments': [], 'attachments': []}
    for comment in comments:
        ticket = tickets.get(comment['bug_id'])
        if ticket is None:
            continue
        try:
            changes = json.loads(comment['changes_json'] or '{}')
        except (TypeError, ValueError):
            changes = {}
        ticket['comments'].append({key: comment[key] for key in ('uid', 'username', 'kind', 'body', 'created_at', 'edited_at')}
                                  | {'changes': changes if isinstance(changes, dict) else {}})
    for attachment in attachments:
        ticket = tickets.get(attachment['bug_id'])
        if ticket is None:
            continue
        path = _attachment_archive_path(attachment)
        files[path] = bytes(attachment['content'])
        ticket['attachments'].append({
            'uid': attachment['uid'], 'comment_uid': comment_uids.get(attachment['comment_id']) if attachment['comment_id'] else None,
            'file_name': attachment['file_name'], 'content_type': attachment['content_type'], 'size': attachment['size'],
            'uploaded_by': attachment['uploaded_by'], 'created_at': attachment['created_at'], 'path': path,
        })
    return {'format': EXPORT_FORMAT, 'version': EXPORT_VERSION, 'bug_reports': list(tickets.values())}, files


def merge_bugs_report(repository: Repository, payload: object, files: dict[str, bytes]) -> dict[str, int]:
    """Merge a Bugs Report package: the tickets, comments and screenshots this server does not have are added, and a
    ticket or comment changed later on the other server takes its newer content. Nothing here is deleted."""
    if not isinstance(payload, dict) or payload.get('format') != EXPORT_FORMAT or not isinstance(payload.get('bug_reports'), list):
        raise ValueError('The Bugs Report file is not valid.')
    summary = {'created': 0, 'updated': 0, 'comments': 0, 'screenshots': 0}
    fields = ('title', 'description', 'module', 'priority', 'status', 'app_version', 'fixed_version', 'browser',
              'created_by', 'assigned_to', 'created_at', 'updated_at', 'resolved_at')
    with repository.global_connection() as conn:
        for ticket in payload['bug_reports']:
            if not isinstance(ticket, dict) or not str(ticket.get('uid') or '').strip() or not str(ticket.get('title') or '').strip():
                continue
            values = {field: str(ticket.get(field) or '') for field in fields}
            if values['priority'] not in PRIORITIES:
                values['priority'] = DEFAULT_PRIORITY
            if values['status'] not in STATUSES:
                values['status'] = 'new'
            values['created_by'] = values['created_by'] or 'import'
            values['created_at'] = values['created_at'] or local_now_iso()
            values['updated_at'] = values['updated_at'] or values['created_at']
            existing = conn.execute('SELECT id, updated_at FROM bug_reports WHERE uid = ?', (str(ticket['uid']),)).fetchone()
            if existing is None:
                cursor = conn.execute(
                    f"INSERT INTO bug_reports (uid, {', '.join(fields)}) VALUES (?, {', '.join('?' for _ in fields)})",
                    (str(ticket['uid']), *values.values()),
                )
                bug_id = int(cursor.lastrowid)
                summary['created'] += 1
            else:
                bug_id = int(existing['id'])
                if values['updated_at'] > str(existing['updated_at'] or ''):
                    conn.execute(f"UPDATE bug_reports SET {', '.join(f'{field} = ?' for field in fields)} WHERE id = ?",
                                 (*values.values(), bug_id))
                    summary['updated'] += 1
            comment_ids: dict[str, int] = {}
            for comment in ticket.get('comments') if isinstance(ticket.get('comments'), list) else []:
                if not isinstance(comment, dict) or not str(comment.get('uid') or '').strip():
                    continue
                uid = str(comment['uid'])
                kind = 'change' if comment.get('kind') == 'change' else 'comment'
                changes = comment.get('changes') if isinstance(comment.get('changes'), dict) else {}
                local = conn.execute('SELECT id, edited_at FROM bug_report_comments WHERE uid = ?', (uid,)).fetchone()
                if local is None:
                    cursor = conn.execute(
                        'INSERT INTO bug_report_comments (uid, bug_id, username, kind, body, changes_json, created_at, edited_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                        (uid, bug_id, str(comment.get('username') or 'import'), kind, str(comment.get('body') or ''),
                         json.dumps(changes, ensure_ascii=False), str(comment.get('created_at') or values['created_at']),
                         str(comment.get('edited_at') or '')),
                    )
                    comment_ids[uid] = int(cursor.lastrowid)
                    summary['comments'] += kind == 'comment'
                else:
                    comment_ids[uid] = int(local['id'])
                    if str(comment.get('edited_at') or '') > str(local['edited_at'] or ''):
                        conn.execute('UPDATE bug_report_comments SET body = ?, edited_at = ? WHERE id = ?',
                                     (str(comment.get('body') or ''), str(comment.get('edited_at') or ''), int(local['id'])))
            for attachment in ticket.get('attachments') if isinstance(ticket.get('attachments'), list) else []:
                if not isinstance(attachment, dict) or not str(attachment.get('uid') or '').strip():
                    continue
                if conn.execute('SELECT 1 FROM bug_report_attachments WHERE uid = ?', (str(attachment['uid']),)).fetchone():
                    continue
                content = files.get(str(attachment.get('path') or ''))
                content_type = image_content_type(content) if content else None
                if content_type is None:
                    continue
                comment_uid = str(attachment.get('comment_uid') or '')
                comment_id = comment_ids.get(comment_uid) if comment_uid else None
                if comment_uid and comment_id is None:
                    continue
                _insert_attachments(conn, bug_id, comment_id, str(attachment.get('uploaded_by') or 'import'), [{
                    'uid': str(attachment['uid']), 'file_name': str(attachment.get('file_name') or 'screenshot')[:200],
                    'content_type': content_type, 'content': content,
                }], str(attachment.get('created_at') or values['created_at']))
                summary['screenshots'] += 1
    return summary
