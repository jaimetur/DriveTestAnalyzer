"""Admin notices: what a super-admin is told about after signing in and while signed in.

A dialog lists the access requests waiting for activation and the new tickets of Ticket Center (status New, reported
by someone else) the super-admin has not been told about yet; the pages ask for them with the poll of incoming transfer
offers (:func:`unseen_notice_ids`). Each super-admin is told about each one once: the items closed in the dialog, and
the tickets the super-admin opens, are kept in ``admin_notices_seen`` of the application database. An access request is
identified by its user and the time of the request, so a later request of the same user is told again; a ticket by its
``uid``.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Iterable

from src.modules.repository import Repository, local_now_iso

ACCESS_REQUEST = 'access_request'
TICKET = 'ticket'


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


def new_tickets(repository: Repository, username: str) -> list[dict[str, Any]]:
    """The tickets still New that someone other than ``username`` reported, the oldest first."""
    with repository.global_connection() as conn:
        rows = conn.execute(
            "SELECT id, uid, ticket_type, title, module, priority, created_by, created_at FROM tickets WHERE status = 'new' "
            'ORDER BY created_at, id'
        ).fetchall()
    return [{**dict(row), 'key': str(row['uid'])} for row in rows if str(row['created_by']).casefold() != username.strip().casefold()]


def _seen_keys(conn: Any, user_id: int) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {ACCESS_REQUEST: set(), TICKET: set()}
    for row in conn.execute('SELECT kind, item_key FROM admin_notices_seen WHERE user_id = ?', (user_id,)).fetchall():
        seen.setdefault(str(row['kind']), set()).add(str(row['item_key']))
    return seen


def unseen_notices(repository: Repository, username: str, *, include_tickets: bool = True) -> dict[str, list[dict[str, Any]]]:
    """The pending access requests and new tickets ``username`` has not been told about yet."""
    requests = pending_access_requests(repository)
    found = new_tickets(repository, username) if include_tickets else []
    with repository.global_connection() as conn:
        user_id = _user_id(conn, username)
        seen = _seen_keys(conn, user_id) if user_id is not None else {ACCESS_REQUEST: set(), TICKET: set()}
    return {
        'access_requests': [item for item in requests if item['key'] not in seen[ACCESS_REQUEST]],
        'tickets': [item for item in found if item['key'] not in seen[TICKET]],
    }


def unseen_notice_ids(repository: Repository, username: str, *, include_tickets: bool = True) -> dict[str, list[int]]:
    """The ids of the users with a pending access request and of the new tickets ``username`` has not been told
    about yet: one light query, for the pages that poll for them."""
    query = """
        SELECT 'access_requests' AS kind, u.id FROM users u
        WHERE u.active = 0 AND u.access_requested_at != '' AND NOT EXISTS (
            SELECT 1 FROM admin_notices_seen s WHERE s.user_id = :user_id AND s.kind = 'access_request'
            AND s.item_key = u.id || ':' || u.access_requested_at)
        UNION ALL
        SELECT 'tickets', t.id FROM tickets t
        WHERE :tickets AND t.status = 'new' AND lower(t.created_by) != lower(:username) AND NOT EXISTS (
            SELECT 1 FROM admin_notices_seen s WHERE s.user_id = :user_id AND s.kind = 'ticket' AND s.item_key = t.uid)
        ORDER BY 1, 2"""
    ids: dict[str, list[int]] = {'access_requests': [], 'tickets': []}
    try:
        with repository.global_connection() as conn:
            user_id = _user_id(conn, username)
            for row in conn.execute(query, {'user_id': user_id or 0, 'username': username.strip(), 'tickets': int(include_tickets)}):
                ids[str(row[0])].append(int(row[1]))
    except sqlite3.Error:
        # An application database being replaced (an import) has nothing to tell yet.
        return {'access_requests': [], 'tickets': []}
    return ids


def mark_seen(repository: Repository, username: str, *, access_requests: Iterable[str] = (),
              tickets: Iterable[str] = ()) -> dict[str, list[dict[str, Any]]]:
    """Record that ``username`` has been told about these access requests and tickets (by their keys), and forget
    those no longer pending or deleted. Returns the items recorded, among those that still exist."""
    pending = {item['key']: item for item in pending_access_requests(repository)}
    now = local_now_iso()
    with repository.global_connection() as conn:
        user_id = _user_id(conn, username)
        if user_id is None:
            return {'access_requests': [], 'tickets': []}
        found = {str(row['uid']): dict(row) for row in conn.execute('SELECT id, uid, title FROM tickets ORDER BY id').fetchall()}
        requested, reported = {str(key) for key in access_requests}, {str(key) for key in tickets}
        recorded = {
            'access_requests': [item for key, item in pending.items() if key in requested],
            'tickets': [ticket for uid, ticket in found.items() if uid in reported],
        }
        conn.executemany(
            'INSERT OR IGNORE INTO admin_notices_seen (user_id, kind, item_key, seen_at) VALUES (?, ?, ?, ?)',
            [(user_id, ACCESS_REQUEST, item['key'], now) for item in recorded['access_requests']]
            + [(user_id, TICKET, ticket['uid'], now) for ticket in recorded['tickets']],
        )
        seen = _seen_keys(conn, user_id)
        conn.executemany(
            'DELETE FROM admin_notices_seen WHERE user_id = ? AND kind = ? AND item_key = ?',
            [(user_id, ACCESS_REQUEST, key) for key in seen[ACCESS_REQUEST] - set(pending)]
            + [(user_id, TICKET, key) for key in seen[TICKET] - set(found)],
        )
    return recorded
