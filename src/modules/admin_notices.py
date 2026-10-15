"""Admin notices: what a super-admin is told about after signing in.

A dialog lists the access requests waiting for activation and the new bug reports (status New, reported by someone
else) the super-admin has not been told about yet. Each super-admin is told about each one once: the items closed in
the dialog, and the bug reports the super-admin opens, are kept in ``admin_notices_seen`` of the application database.
An access request is identified by its user and the time of the request, so a later request of the same user is told
again; a bug report by its ``uid``.
"""
from __future__ import annotations

from typing import Any, Iterable

from src.modules.repository import Repository, local_now_iso

ACCESS_REQUEST = 'access_request'
BUG_REPORT = 'bug_report'


def _user_id(conn: Any, username: str) -> int | None:
    row = conn.execute('SELECT id FROM users WHERE username = ? COLLATE NOCASE', (username.strip(),)).fetchone()
    return int(row['id']) if row else None


def pending_access_requests(repository: Repository) -> list[dict[str, Any]]:
    """The users waiting for an administrator to activate them after an access request, the oldest request first."""
    requests = [{
        'key': f"{int(row['id'])}:{row['access_requested_at']}", 'user_id': int(row['id']), 'username': str(row['username']),
        'name': ' '.join(part for part in (str(row['first_name'] or '').strip(), str(row['last_name'] or '').strip()) if part),
        'role': str(row['role']), 'requested_at': str(row['access_requested_at']),
    } for row in repository.list_users() if not row['active'] and row['access_requested_at']]
    return sorted(requests, key=lambda item: (item['requested_at'], item['user_id']))


def new_bug_reports(repository: Repository, username: str) -> list[dict[str, Any]]:
    """The bug reports still New that someone other than ``username`` reported, the oldest first."""
    with repository.global_connection() as conn:
        rows = conn.execute(
            "SELECT id, uid, title, module, priority, created_by, created_at FROM bug_reports WHERE status = 'new' ORDER BY created_at, id"
        ).fetchall()
    return [{**dict(row), 'key': str(row['uid'])} for row in rows if str(row['created_by']).casefold() != username.strip().casefold()]


def _seen_keys(conn: Any, user_id: int) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {ACCESS_REQUEST: set(), BUG_REPORT: set()}
    for row in conn.execute('SELECT kind, item_key FROM admin_notices_seen WHERE user_id = ?', (user_id,)).fetchall():
        seen.setdefault(str(row['kind']), set()).add(str(row['item_key']))
    return seen


def unseen_notices(repository: Repository, username: str, *, include_bug_reports: bool = True) -> dict[str, list[dict[str, Any]]]:
    """The pending access requests and new bug reports ``username`` has not been told about yet."""
    requests = pending_access_requests(repository)
    bugs = new_bug_reports(repository, username) if include_bug_reports else []
    with repository.global_connection() as conn:
        user_id = _user_id(conn, username)
        seen = _seen_keys(conn, user_id) if user_id is not None else {ACCESS_REQUEST: set(), BUG_REPORT: set()}
    return {
        'access_requests': [item for item in requests if item['key'] not in seen[ACCESS_REQUEST]],
        'bug_reports': [item for item in bugs if item['key'] not in seen[BUG_REPORT]],
    }


def mark_seen(repository: Repository, username: str, *, access_requests: Iterable[str] = (),
              bug_reports: Iterable[str] = ()) -> dict[str, list[dict[str, Any]]]:
    """Record that ``username`` has been told about these access requests and bug reports (by their keys), and forget
    those no longer pending or deleted. Returns the items recorded, among those that still exist."""
    pending = {item['key']: item for item in pending_access_requests(repository)}
    now = local_now_iso()
    with repository.global_connection() as conn:
        user_id = _user_id(conn, username)
        if user_id is None:
            return {'access_requests': [], 'bug_reports': []}
        bugs = {str(row['uid']): dict(row) for row in conn.execute('SELECT id, uid, title FROM bug_reports ORDER BY id').fetchall()}
        requested, reported = {str(key) for key in access_requests}, {str(key) for key in bug_reports}
        recorded = {
            'access_requests': [item for key, item in pending.items() if key in requested],
            'bug_reports': [bug for uid, bug in bugs.items() if uid in reported],
        }
        conn.executemany(
            'INSERT OR IGNORE INTO admin_notices_seen (user_id, kind, item_key, seen_at) VALUES (?, ?, ?, ?)',
            [(user_id, ACCESS_REQUEST, item['key'], now) for item in recorded['access_requests']]
            + [(user_id, BUG_REPORT, bug['uid'], now) for bug in recorded['bug_reports']],
        )
        seen = _seen_keys(conn, user_id)
        conn.executemany(
            'DELETE FROM admin_notices_seen WHERE user_id = ? AND kind = ? AND item_key = ?',
            [(user_id, ACCESS_REQUEST, key) for key in seen[ACCESS_REQUEST] - set(pending)]
            + [(user_id, BUG_REPORT, key) for key in seen[BUG_REPORT] - set(bugs)],
        )
    return recorded
