from __future__ import annotations

import hashlib
import hmac
import math
import os
import secrets
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic


@dataclass(slots=True)
class SessionUser:
    username: str
    role: str
    session_marker: str = field(default_factory=lambda: secrets.token_urlsafe(12))


# Passwords are kept as scrypt hashes: ``scrypt$<log2 N>$<r>$<p>$<salt>$<hash>``. The work of each guess (2**15 by default,
# about 32 MB and a tenth of a second) is what makes a copy of the users table slow to try passwords against; the tests
# lower it (DTA_PASSWORD_HASH_LOG_N, set in tests/conftest.py). The hashes of earlier versions (``<salt>$<sha256>``, one
# round) are still accepted, and replaced by a scrypt one the next time their user signs in (see password_needs_rehash).
SCRYPT_LOG_N = max(4, min(20, int(os.environ.get('DTA_PASSWORD_HASH_LOG_N') or 15)))
SCRYPT_R = 8
SCRYPT_P = 1


def _scrypt(password: str, salt: bytes, log_n: int, r: int, p: int) -> str:
    return hashlib.scrypt(password.encode(), salt=salt, n=2 ** log_n, r=r, p=p, maxmem=256 * 1024 * 1024, dklen=32).hex()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${SCRYPT_LOG_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${_scrypt(password, salt, SCRYPT_LOG_N, SCRYPT_R, SCRYPT_P)}"


def verify_password(password: str, stored_hash: str) -> bool:
    # A malformed stored hash can never match; reject it instead of raising.
    stored = str(stored_hash or "")
    if stored.startswith('scrypt$'):
        try:
            _name, log_n, r, p, salt, expected = stored.split('$')
            if not 4 <= int(log_n) <= 20 or not 1 <= int(r) <= 32 or not 1 <= int(p) <= 16:
                return False
            current = _scrypt(password, bytes.fromhex(salt), int(log_n), int(r), int(p))
        except (ValueError, MemoryError):
            return False
        return hmac.compare_digest(current, expected)
    salt, separator, expected = stored.partition("$")
    if not separator:
        return False
    current = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return hmac.compare_digest(current, expected)


def password_needs_rehash(stored_hash: str) -> bool:
    """Whether a stored hash is one of an earlier version, or of a lower cost than this deployment asks for."""
    stored = str(stored_hash or "")
    if not stored.startswith('scrypt$'):
        return True
    try:
        return int(stored.split('$')[1]) < SCRYPT_LOG_N
    except (IndexError, ValueError):
        return True


class AttemptLimiter:
    """Slows down the guessing of a secret: after ``allowed`` failures in a row for a key (a username), the next tries
    wait, twice as long after each further failure, up to ``longest`` seconds. A success, or ``forget`` seconds without
    failures, starts over. Kept in memory: a restart forgives everybody."""

    def __init__(self, allowed: int = 5, first_wait: float = 30.0, longest: float = 300.0, forget: float = 1800.0) -> None:
        self.allowed, self.first_wait, self.longest, self.forget = allowed, first_wait, longest, forget
        self._failures: dict[str, tuple[int, float, float]] = {}
        self._lock = Lock()

    def wait_seconds(self, key: str) -> int:
        """The seconds a key must still wait before its next try (0: it may try now)."""
        now = monotonic()
        with self._lock:
            count, last, until = self._failures.get(key.casefold(), (0, 0.0, 0.0))
            if count and now - last > self.forget:
                self._failures.pop(key.casefold(), None)
                return 0
            return max(0, math.ceil(until - now))

    def failed(self, key: str) -> None:
        now = monotonic()
        with self._lock:
            count, last, _until = self._failures.get(key.casefold(), (0, 0.0, 0.0))
            count = 1 if count and now - last > self.forget else count + 1
            wait = min(self.longest, self.first_wait * 2 ** (count - self.allowed)) if count >= self.allowed else 0.0
            self._failures[key.casefold()] = (count, now, now + wait)
            if len(self._failures) > 10000:  # Tries with made-up usernames must not grow it without end.
                for stale in sorted(self._failures, key=lambda item: self._failures[item][1])[:5000]:
                    self._failures.pop(stale, None)

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key.casefold(), None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()
