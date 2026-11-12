"""What is read from a workspace, kept while the workspace stays as it was.

A read that takes long (the calls of some filters, the values a filter offers) gives the same result until something
is written to the workspace database, so its result is kept and given again while this process has written nothing to
the database and the day is the same. Nothing is kept for longer than ``KEPT_SECONDS``: some results depend on the time
of day (the calls stalled for some days), and what another process writes (a CDR being processed) is not seen.
"""
from __future__ import annotations

import copy
import json
import time
from collections import OrderedDict
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from src.modules.core.repository import workspace_data_stamp

KEPT_SECONDS = 300.0
KEPT_RESULTS = 384

_kept: OrderedDict[tuple[str, str, str], tuple[Any, float, Any]] = OrderedDict()
_guard = Lock()


def data_stamp(repository: Any) -> tuple[Any, ...]:
    """The state of what a read of the workspace depends on: its database as this process wrote it, and the day."""
    return (workspace_data_stamp(repository.db_path), date.today().toordinal())


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
