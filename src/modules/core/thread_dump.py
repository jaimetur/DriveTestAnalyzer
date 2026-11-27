"""What every thread of the server is doing, on demand, to find what blocks it (a workspace nobody can write to).

- ``kill -USR1 <pid>`` (in Docker: ``docker exec drivetest-analyzer kill -USR1 1``) writes the stack of every thread,
  by its name, and which thread holds the write lock of each workspace, to the server log and to
  ``<data>/diagnostics/thread-dump-<date>.txt`` (the newest 20 are kept). It runs in the main thread, which answers
  while the event loop runs.
- ``kill -USR2 <pid>`` writes the stacks with ``faulthandler`` to the server log: it works even when the main thread is
  blocked too, without the thread names and the lock owners.

Nothing else changes: the server keeps running as it was.
"""
from __future__ import annotations

import faulthandler
import re
import signal
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

DUMPS_FOLDER = 'diagnostics'
DUMPS_KEPT = 20
_OWNER = re.compile(r'owner=(\d+)')
_folder: Path | None = None


def lock_owners() -> list[tuple[str, int | None, int]]:
    """Each workspace write lock held: the workspace database, the ident of the thread that holds it and its count."""
    from src.modules.core.repository import _WORKSPACE_WRITE_LOCKS, _WORKSPACE_WRITE_LOCKS_GUARD

    with _WORKSPACE_WRITE_LOCKS_GUARD:
        locks = list(_WORKSPACE_WRITE_LOCKS.items())
    held = []
    for database, lock in locks:
        text = repr(lock)
        if text.startswith('<locked'):
            owner = _OWNER.search(text)
            count = re.search(r'count=(\d+)', text)
            held.append((database, int(owner.group(1)) if owner else None, int(count.group(1)) if count else 1))
    return held


def dump_text() -> str:
    """The workspace write locks held, then the stack of every thread (the threads that hold a lock first)."""
    names = {thread.ident: thread for thread in threading.enumerate()}
    frames = sys._current_frames()
    owners = lock_owners()
    holding = {owner for _database, owner, _count in owners}
    lines = [f'Thread dump of DriveTest Analyzer at {datetime.now().astimezone().isoformat(timespec="seconds")} '
             f'({len(frames)} threads)', '', 'Workspace write locks held:']
    for database, owner, count in owners:
        thread = names.get(owner)
        lines.append(f'- {database}: thread {thread.name if thread else "unknown"} ({owner}), held {count} time(s)')
    if not owners:
        lines.append('- none')
    for ident, frame in sorted(frames.items(), key=lambda item: (item[0] not in holding, str(getattr(names.get(item[0]), 'name', '')))):
        thread = names.get(ident)
        name = thread.name if thread else 'unknown'
        flags = ', holds a workspace write lock' if ident in holding else ''
        lines += ['', f'Thread {name} ({ident}{", daemon" if thread is not None and thread.daemon else ""}{flags}):',
                  *(line.rstrip('\n') for line in traceback.format_stack(frame))]
    return '\n'.join(lines) + '\n'


def write_dump(*_args: Any) -> Path | None:
    """Write a dump to the server log and, when a folder is set, to a file of its own (the newest DUMPS_KEPT kept)."""
    text = dump_text()
    sys.stderr.write(text)
    sys.stderr.flush()
    if _folder is None:
        return None
    try:
        _folder.mkdir(parents=True, exist_ok=True)
        path = _folder / f'thread-dump-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}.txt'
        path.write_text(text, encoding='utf-8')
        for old in sorted(_folder.glob('thread-dump-*.txt'))[:-DUMPS_KEPT]:
            old.unlink(missing_ok=True)
        sys.stderr.write(f'Thread dump written to {path}\n')
        return path
    except OSError as exc:
        sys.stderr.write(f'The thread dump could not be written to {_folder}: {exc}\n')
        return None


def install(data_dir: Path | str | None) -> bool:
    """Answer SIGUSR1 and SIGUSR2 with a dump (see the module); whether they were installed (not on Windows, and only
    from the main thread)."""
    global _folder
    if not hasattr(signal, 'SIGUSR1') or threading.current_thread() is not threading.main_thread():
        return False
    _folder = Path(data_dir) / DUMPS_FOLDER if data_dir else None
    signal.signal(signal.SIGUSR1, write_dump)
    faulthandler.register(signal.SIGUSR2, all_threads=True, chain=False)
    return True
