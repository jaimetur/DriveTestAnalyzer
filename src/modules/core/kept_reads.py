"""What is read from a workspace, kept while the workspace stays as it was.

A read that takes long (the calls of some filters, the values a filter offers) gives the same result until something
is written to the workspace database, so its result is kept and given again while the database, the application
database (the users) and the day are the same. Nothing is kept for longer than ``KEPT_SECONDS``: some results depend on
the time of day (the calls stalled for some days).
"""
from __future__ import annotations

import copy
import json
import os
import time
from collections import OrderedDict
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from src.modules.core.repository import workspace_data_stamp

KEPT_SECONDS = 600.0
KEPT_RESULTS = 384

_kept: OrderedDict[tuple[str, str, str], tuple[Any, float, Any]] = OrderedDict()
_guard = Lock()


def _file_stamp(path: Any) -> tuple[Any, ...]:
    found = []
    for name in (str(path), f'{path}-wal'):
        try:
            stat = os.stat(name)
            found.append((stat.st_ino, stat.st_size, stat.st_mtime_ns))
        except OSError:
            found.append(None)
    return tuple(found)


def data_stamp(repository: Any) -> tuple[Any, ...]:
    """The state of what a read of the workspace depends on: its database, the application database and the day."""
    global_path = getattr(repository, 'global_db_path', None)
    return (workspace_data_stamp(repository.db_path), _file_stamp(global_path) if global_path else None, date.today().toordinal())


def kept(repository: Any, name: str, key: Any, read: Callable[[], Any], *, copied: bool = True) -> Any:
    """The result of ``read`` for ``key``: the one kept while the workspace has not changed, else read now and kept.

    A result is given as a copy of its own (``copied``), so whoever changes it changes nobody else's; leave the copy out
    only for results nobody changes (bytes, tuples)."""
    if getattr(repository, 'db_path', None) is None:
        return read()
    entry = (str(Path(str(repository.db_path)).resolve()), name, json.dumps(key, sort_keys=True, default=str))
    # The stamp is read before the data: a result read while something was being written is never given later.
    stamp = data_stamp(repository)
    now = time.monotonic()
    with _guard:
        found = _kept.get(entry)
        if found is not None and found[0] == stamp and now - found[1] < KEPT_SECONDS:
            _kept.move_to_end(entry)
            return copy.deepcopy(found[2]) if copied else found[2]
    result = read()
    with _guard:
        _kept[entry] = (stamp, now, result)
        _kept.move_to_end(entry)
        while len(_kept) > KEPT_RESULTS:
            _kept.popitem(last=False)
    return copy.deepcopy(result) if copied else result


def forget() -> None:
    """Forget every kept result."""
    with _guard:
        _kept.clear()
