"""Demo Mode: the platform kept for the users of a demo while it lasts.

An admin or a super-admin starts it from the user menu of the app bar with the expected end of the demo, a message for
the other users and the users who keep access: the one who starts it always does and, when an admin starts it (or
changes its users), every super-admin too. Everybody else is signed out and cannot sign in until it ends:

- A user with a page open (its pages poll :meth:`DemoMode.heartbeat` and tell their unsaved changes) is warned first and
  signed out within :data:`SIGN_OUT_GRACE_SECONDS`; one with unsaved changes is asked to save them and is signed out as
  soon as they are saved (or discarded), however long that takes. Meanwhile the pages start no new edits and, once a
  user has nothing left to save, the server refuses its changes (:meth:`DemoMode.refuses_changes`).
- A user with a session but no page open is signed out at once.
- The sign-in page refuses the users without access and says why and until when.

Demo Mode never ends by itself: at the expected end the user who started it (or, while that user has no page open, the
other admins and super-admins with access) is asked to extend it or end it.

The demo itself (who started it, until when, the message and the users) is kept in ``application_state`` so it
outlives a restart; who is being signed out, and the pages open, are only kept in memory: after a restart a user without
access is warned again on its next request. It is not transferable (no export, transfer or backup carries it): it only
describes what the server is doing now.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

STATE_KEY = 'demo_mode'
# A user without unsaved changes is signed out at most this long after being warned.
SIGN_OUT_GRACE_SECONDS = 300
# A page polls every 20 seconds (every 5 while its user is being signed out): one not heard of for longer is closed.
PAGE_OPEN_SECONDS = 60
# A user being signed out whose pages were all closed (with unsaved changes or not) is signed out.
PAGE_CLOSED_SECONDS = 90
# The demo is read again from the database this often (each request asks whether one is on).
STATE_CACHE_SECONDS = 5.0
EXTEND_MINUTES = (5, 15, 30, 45, 60)
MAX_MESSAGE_LENGTH = 1000
MAX_UNSAVED_ITEMS = 20
DEFAULT_MESSAGE = ('DriveTest Analyzer is being used for a live demo right now. To keep the demo running smoothly, the '
                   'platform is unavailable while it lasts. Thanks for your patience: you can sign in again as soon as the '
                   'demo is over.')
MANAGER_ROLES = frozenset({'admin', 'super-admin'})


class DemoModeError(ValueError):
    """A request Demo Mode refuses (shown to the user as it is)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec='seconds')


def _parse_moment(value: Any) -> datetime:
    """An ISO date and time sent by a page (with its offset, or UTC when it has none)."""
    try:
        moment = datetime.fromisoformat(str(value or '').strip().replace('Z', '+00:00'))
    except ValueError as exc:
        raise DemoModeError('Choose a valid expected end of the demo.') from exc
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _fold(username: Any) -> str:
    return str(username or '').strip().casefold()


@dataclass
class _Page:
    username: str
    seen: float
    unsaved: list[str] = field(default_factory=list)


@dataclass
class _Departure:
    """A user without access being signed out."""
    username: str
    warned: float
    deadline: float
    had_unsaved: bool = False
    unsaved: list[str] = field(default_factory=list)
    # Whether a page of the user told its unsaved changes since the warning.
    reported: bool = False


class DemoMode:
    """The Demo Mode of one server.

    ``users`` gives the accounts (rows with username, role, active, first_name, last_name), ``session_usernames`` the
    usernames with a login session, ``end_sessions`` signs a user out of every browser and ``log`` writes an App Event
    (username, action, details).
    """

    def __init__(self, *, load: Callable[[], str | None], save: Callable[[str], None], users: Callable[[], Iterable[Any]],
                 session_usernames: Callable[[], Iterable[str]], end_sessions: Callable[[str], None],
                 log: Callable[[str, str, dict[str, Any]], None], clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = _now) -> None:
        self._load, self._save, self._users = load, save, users
        self._session_usernames, self._end_sessions, self._log = session_usernames, end_sessions, log
        self._clock, self._now = clock, now
        self._lock = threading.RLock()
        self._state: dict[str, Any] | None = None
        self._loaded: float | None = None
        self._pages: dict[tuple[str, str], _Page] = {}
        self._departures: dict[str, _Departure] = {}
        self._signed_out: list[str] = []

    # -- the demo -------------------------------------------------------------------------------------------------
    def state(self) -> dict[str, Any] | None:
        """The demo in progress, or None."""
        with self._lock:
            if self._loaded is None or self._clock() - self._loaded >= STATE_CACHE_SECONDS:
                try:
                    stored = json.loads(self._load() or 'null')
                except Exception:  # (A busy or missing database keeps what was known.)
                    return self._state
                self._state = stored if isinstance(stored, dict) and stored.get('active') else None
                self._loaded = self._clock()
            return self._state

    def forget(self) -> None:
        """Forget what is kept in memory (another database was opened, or the tests start again)."""
        with self._lock:
            self._state, self._loaded = None, None
            self._pages.clear()
            self._departures.clear()
            self._signed_out.clear()

    @property
    def active(self) -> bool:
        return self.state() is not None

    def _store(self, state: dict[str, Any] | None) -> None:
        self._save(json.dumps(state or {'active': False}, sort_keys=True))
        self._state, self._loaded = state, self._clock()

    def _roles(self) -> dict[str, tuple[str, str]]:
        """The active accounts: username in lower case → (username, role)."""
        return {_fold(row['username']): (str(row['username']), str(row['role'])) for row in self._users() if row['active']}

    def is_allowed(self, username: str, role: str) -> bool:
        """Whether a user keeps access (always, without a demo)."""
        state = self.state()
        if state is None:
            return True
        folded = _fold(username)
        if folded == _fold(state['started_by']) or folded in {_fold(name) for name in state['users']}:
            return True
        return role == 'super-admin' and bool(state.get('keep_super_admins'))

    def can_manage(self, username: str, role: str) -> bool:
        """Whether a user may change or end the demo: an admin or super-admin who keeps access."""
        return role in MANAGER_ROLES and self.active and self.is_allowed(username, role)

    def _allowed_users(self, chosen: Iterable[Any], actor: str, actor_role: str) -> tuple[list[str], bool]:
        accounts = self._roles()
        users = {_fold(actor): accounts.get(_fold(actor), (actor, actor_role))[0]}
        for name in chosen or []:
            account = accounts.get(_fold(name))
            if account:
                users[_fold(name)] = account[0]
        keep_super_admins = actor_role != 'super-admin'
        if keep_super_admins:
            users.update({key: name for key, (name, role) in accounts.items() if role == 'super-admin'})
        return sorted(users.values(), key=str.casefold), keep_super_admins

    def _expected_end(self, value: Any) -> datetime:
        moment = _parse_moment(value)
        if moment <= self._now():
            raise DemoModeError('The expected end of the demo must be later than now.')
        if moment > self._now() + timedelta(days=7):
            raise DemoModeError('The expected end of the demo must be within the next seven days.')
        return moment

    @staticmethod
    def _message(value: Any) -> str:
        message = str(value if value is not None else DEFAULT_MESSAGE).strip()
        return message[:MAX_MESSAGE_LENGTH] or DEFAULT_MESSAGE

    def start(self, actor: str, actor_role: str, *, expected_end: Any, message: Any, users: Iterable[Any]) -> dict[str, Any]:
        if actor_role not in MANAGER_ROLES:
            raise DemoModeError('Only admins and super-admins can start Demo Mode.')
        with self._lock:
            if self.active:
                raise DemoModeError('Demo Mode is already on.')
            end = self._expected_end(expected_end)
            allowed, keep_super_admins = self._allowed_users(users, actor, actor_role)
            state = {
                'active': True, 'started_by': actor, 'started_by_role': actor_role, 'started_at': _iso(self._now()),
                'expected_end': _iso(end), 'remind_at': '', 'message': self._message(message), 'users': allowed,
                'keep_super_admins': keep_super_admins,
            }
            self._store(state)
            self._departures.clear()
            self._log(actor, 'demo_mode_started', {
                'expected_end': state['expected_end'], 'users': allowed, 'super_admins_always': keep_super_admins,
                'message': state['message'],
            })
            self._warn_everybody()
            return state

    def update(self, actor: str, actor_role: str, *, expected_end: Any = None, message: Any = None,
               users: Iterable[Any] | None = None, extend_minutes: Any = None, remind_minutes: Any = None) -> dict[str, Any]:
        with self._lock:
            state = self.state()
            if state is None:
                raise DemoModeError('Demo Mode is not on.')
            if not self.can_manage(actor, actor_role):
                raise DemoModeError('Only the admins and super-admins of the demo can change it.')
            changes: dict[str, list[Any]] = {}
            new = dict(state)
            if extend_minutes is not None:
                minutes = int(extend_minutes)
                if minutes not in EXTEND_MINUTES:
                    raise DemoModeError('Extend the demo by 5, 15, 30, 45 or 60 minutes.')
                base = max(self._now(), _parse_moment(state['expected_end']))
                new['expected_end'], new['remind_at'] = _iso(base + timedelta(minutes=minutes)), ''
            elif expected_end is not None:
                new['expected_end'], new['remind_at'] = _iso(self._expected_end(expected_end)), ''
            if remind_minutes is not None:
                minutes = max(1, min(int(remind_minutes), 60))
                new['remind_at'] = _iso(self._now() + timedelta(minutes=minutes))
            if message is not None:
                new['message'] = self._message(message)
            if users is not None:
                chosen = list(users) + [state['started_by']]
                # (An admin changing the users keeps every super-admin; a super-admin chooses them.)
                new['users'], new['keep_super_admins'] = self._allowed_users(chosen, actor, actor_role)
            for key in ('expected_end', 'remind_at', 'message', 'users', 'keep_super_admins'):
                if new.get(key) != state.get(key):
                    changes[key] = [state.get(key), new.get(key)]
            if not changes:
                return state
            self._store(new)
            action = ('demo_mode_extended' if extend_minutes is not None
                      else 'demo_mode_reminder_postponed' if remind_minutes is not None and set(changes) == {'remind_at'}
                      else 'demo_mode_changed')
            details: dict[str, Any] = {'changes': changes}
            if extend_minutes is not None:
                details['extended_by_minutes'] = int(extend_minutes)
            self._log(actor, action, details)
            if 'users' in changes or 'keep_super_admins' in changes:
                for folded in [key for key, departure in self._departures.items()
                               if self.is_allowed(departure.username, self._roles().get(key, ('', ''))[1])]:
                    self._departures.pop(folded, None)
                self._warn_everybody()
            return new

    def end(self, actor: str, actor_role: str) -> None:
        with self._lock:
            state = self.state()
            if state is None:
                return
            if not self.can_manage(actor, actor_role):
                raise DemoModeError('Only the admins and super-admins of the demo can end it.')
            self._store(None)
            still = sorted(departure.username for departure in self._departures.values())
            self._departures.clear()
            self._log(actor, 'demo_mode_ended', {
                'started_by': state['started_by'], 'started_at': state['started_at'], 'expected_end': state['expected_end'],
                'ended_at': _iso(self._now()), 'users_still_saving': still,
            })

    # -- the users being signed out ------------------------------------------------------------------------------
    def _page_open(self, folded: str, *, within: float = PAGE_OPEN_SECONDS) -> bool:
        now = self._clock()
        return any(page.username == folded and now - page.seen <= within for page in self._pages.values())

    def _unsaved(self, folded: str) -> list[str]:
        now = self._clock()
        items: list[str] = []
        for page in self._pages.values():
            if page.username == folded and now - page.seen <= PAGE_CLOSED_SECONDS:
                items.extend(item for item in page.unsaved if item not in items)
        return items

    def _depart(self, username: str, folded: str) -> _Departure:
        departure = self._departures.get(folded)
        if departure is None:
            now = self._clock()
            departure = _Departure(username=username, warned=now, deadline=now + SIGN_OUT_GRACE_SECONDS)
            self._departures[folded] = departure
            self._log(username, 'demo_mode_user_warned', {'started_by': self.state()['started_by'],
                                                         'page_open': self._page_open(folded)})
        return departure

    def _sign_out(self, folded: str, reason: str) -> None:
        departure = self._departures.pop(folded, None)
        username = departure.username if departure else folded
        self._end_sessions(username)
        for key in [key for key, page in self._pages.items() if page.username == folded]:
            self._pages.pop(key, None)
        self._signed_out.append(folded)
        del self._signed_out[:-200]
        details: dict[str, Any] = {'reason': reason}
        if departure:
            details['seconds_after_warning'] = round(self._clock() - departure.warned)
            if departure.had_unsaved:
                details['unsaved_changes_before_leaving'] = departure.unsaved
        self._log(username, 'demo_mode_user_signed_out', details)

    def _warn_everybody(self) -> None:
        """Every signed-in user without access: those with a page open are warned, the others signed out at once."""
        accounts = self._roles()
        for username in {_fold(name): name for name in self._session_usernames()}.values():
            folded = _fold(username)
            name, role = accounts.get(folded, (username, ''))
            if self.is_allowed(name, role) or folded in self._departures:
                continue
            if self._page_open(folded):
                self._depart(name, folded)
            else:
                self._departures[folded] = _Departure(username=name, warned=self._clock(), deadline=self._clock())
                self._sign_out(folded, 'no_page_open')

    def sweep(self) -> None:
        """Sign out those whose time is up and whose pages were closed."""
        with self._lock:
            if not self.active:
                return
            now = self._clock()
            for folded, departure in list(self._departures.items()):
                if not self._page_open(folded, within=PAGE_CLOSED_SECONDS) and now - departure.warned >= PAGE_CLOSED_SECONDS:
                    self._sign_out(folded, 'pages_closed')
                elif not self._unsaved(folded) and now >= departure.deadline:
                    self._sign_out(folded, 'saved_changes' if departure.had_unsaved else 'warning_time_over')

    def refuses_changes(self, username: str, role: str) -> bool:
        """Whether a request of a user that changes something is refused: a user being signed out with nothing left to
        save (one that still has unsaved changes saves them)."""
        with self._lock:
            if not self.active or self.is_allowed(username, role):
                return False
            folded = _fold(username)
            departure = self._depart(username, folded)
            return departure.reported and not self._unsaved(folded)

    def check_request(self, username: str, role: str) -> bool:
        """Called on each request of a signed-in user: False when the user has just been signed out (a user without a
        page open, or whose time is over)."""
        with self._lock:
            if not self.active or self.is_allowed(username, role):
                return True
            folded = _fold(username)
            departure = self._departures.get(folded)
            if departure is None:
                self._depart(username, folded)
                return True
            if not self._unsaved(folded) and self._clock() >= departure.deadline:
                self._sign_out(folded, 'saved_changes' if departure.had_unsaved else 'warning_time_over')
                return False
            return True

    # -- the pages ------------------------------------------------------------------------------------------------
    def heartbeat(self, username: str, role: str, *, session: str, tab: Any, unsaved: Iterable[Any] = (),
                  leave: bool = False) -> dict[str, Any]:
        """What a page is told when it polls: the demo and, for a user without access, whether to save and when it is
        signed out; for those who manage the demo, who is still being signed out and whether its time is up."""
        folded = _fold(username)
        items = [str(item).strip()[:200] for item in list(unsaved or [])[:MAX_UNSAVED_ITEMS] if str(item or '').strip()]
        with self._lock:
            self._pages[(session, str(tab or '')[:64])] = _Page(username=folded, seen=self._clock(), unsaved=items)
            if len(self._pages) > 5000:
                cutoff = self._clock() - PAGE_CLOSED_SECONDS
                self._pages = {key: page for key, page in self._pages.items() if page.seen >= cutoff}
            self.sweep()
            state = self.state()
            if state is None:
                return {'active': False}
            reply: dict[str, Any] = {'active': True, **self.public_info()}
            if not self.is_allowed(username, role):
                departure = self._depart(username, folded)
                departure.reported = True
                pending = self._unsaved(folded)
                if pending:
                    departure.had_unsaved = True
                    departure.unsaved = pending
                if not pending and (leave or departure.had_unsaved or self._clock() >= departure.deadline):
                    reason = 'signed_out_by_user' if leave and not departure.had_unsaved else (
                        'saved_changes' if departure.had_unsaved else 'warning_time_over')
                    self._sign_out(folded, reason)
                    return {**reply, 'signed_out': True}
                reply['leaving'] = {
                    'unsaved': pending,
                    'seconds_left': None if pending else max(0, round(departure.deadline - self._clock())),
                }
                return reply
            if self.can_manage(username, role):
                reply['manage'] = True
                reply['departures'] = [
                    {'username': departure.username, 'unsaved': self._unsaved(key),
                     'seconds_left': None if self._unsaved(key) else max(0, round(departure.deadline - self._clock()))}
                    for key, departure in sorted(self._departures.items())
                ]
                reply['time_up'] = self._time_up_for(folded)
                reply['extend_minutes'] = list(EXTEND_MINUTES)
            return reply

    def _time_up_for(self, folded: str) -> bool:
        state = self.state()
        now = self._now()
        if state is None or now < _parse_moment(state['expected_end']):
            return False
        if state.get('remind_at') and now < _parse_moment(state['remind_at']):
            return False
        starter = _fold(state['started_by'])
        return folded == starter or not self._page_open(starter)

    def public_info(self) -> dict[str, Any]:
        """What anybody (the sign-in page too) is told about the demo in progress."""
        state = self.state()
        if state is None:
            return {'active': False}
        return {'active': True, 'started_by': state['started_by'], 'started_at': state['started_at'],
                'expected_end': state['expected_end'], 'message': state['message'],
                'overdue': self._now() >= _parse_moment(state['expected_end'])}

    def users_overview(self, actor: str, actor_role: str) -> list[dict[str, Any]]:
        """The accounts for the dialog of the demo: whether each keeps access, can be left out, has a page open and
        unsaved changes."""
        state = self.state()
        with self._lock:
            rows = []
            for row in self._users():
                if not row['active']:
                    continue
                username, role = str(row['username']), str(row['role'])
                folded = _fold(username)
                is_actor = folded == _fold(actor)
                is_starter = bool(state) and folded == _fold(state['started_by'])
                locked = is_actor or is_starter or (role == 'super-admin' and actor_role != 'super-admin')
                selected = (self.is_allowed(username, role) if state else (locked or role == 'super-admin'))
                rows.append({
                    'username': username, 'role': role,
                    'name': ' '.join(part for part in (str(row['first_name'] or '').strip(), str(row['last_name'] or '').strip()) if part),
                    'selected': bool(selected or locked), 'locked': locked, 'you': is_actor, 'started': is_starter,
                    'online': self._page_open(folded), 'unsaved': self._unsaved(folded),
                })
            return sorted(rows, key=lambda item: (not item['you'], not item['locked'], item['username'].casefold()))

    def was_signed_out(self, username: str) -> bool:
        return _fold(username) in self._signed_out
