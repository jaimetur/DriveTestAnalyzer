"""Results the tests compute once per run and every test process (pytest-xdist worker) reuses.

Synthetic Scoring results take tens of seconds to calculate: the first process that needs one calculates it and keeps it
in a file of the run, the others wait for it and read it. Each call returns its own copy, so a test that changes it does
not change it for the others.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import pickle
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(tempfile.gettempdir()) / 'drivetest-analyzer-test-results'
# Runs older than this are removed when a run starts using the folder.
_KEEP_SECONDS = 6 * 3600
_LOADED: dict[str, bytes] = {}


def _run_folder() -> Path:
    run = os.environ.get('PYTEST_XDIST_TESTRUNUID') or f'process-{os.getpid()}'
    folder = _ROOT / run
    if not folder.is_dir():
        folder.mkdir(parents=True, exist_ok=True)
        for old in _ROOT.iterdir():
            try:
                if old != folder and time.time() - old.stat().st_mtime > _KEEP_SECONDS:
                    shutil.rmtree(old, ignore_errors=True)
            except OSError:
                pass
    return folder


def shared_result(name: str, compute: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """``compute(*args, **kwargs)``, calculated once per run for every test process, as a copy of its own."""
    key = hashlib.sha256(repr((name, args, sorted(kwargs.items()))).encode()).hexdigest()[:32]
    if key not in _LOADED:
        folder = _run_folder()
        path = folder / f'{key}.pickle'
        with (folder / f'{key}.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if path.is_file():
                data = path.read_bytes()
            else:
                data = pickle.dumps(compute(*args, **kwargs), protocol=pickle.HIGHEST_PROTOCOL)
                partial = path.with_suffix('.partial')
                partial.write_bytes(data)
                partial.replace(path)
        _LOADED[key] = data
    return pickle.loads(_LOADED[key])
