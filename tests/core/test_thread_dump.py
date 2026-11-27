"""SIGUSR1 writes what every thread does and who holds the write lock of each workspace (server blocked, 2026-11-27)."""
from __future__ import annotations

import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(not hasattr(signal, 'SIGUSR1'), reason='SIGUSR1 is not available on this platform')
def test_sigusr1_writes_each_thread_and_the_owner_of_a_workspace_write_lock(tmp_path):
    # (In a process of its own: the signal is answered in the main thread, which the test workers do not run in.)
    script = textwrap.dedent(f"""
        import os, signal, threading, time
        from pathlib import Path
        from src.modules.core import thread_dump
        from src.modules.core.repository import workspace_write_lock

        folder = Path({str(tmp_path)!r})
        held, release = threading.Event(), threading.Event()

        def writer():
            with workspace_write_lock(folder / 'blocked.db'):
                held.set()
                release.wait(10)

        assert thread_dump.install(folder)
        threading.Thread(target=writer, name='writer-that-blocks', daemon=True).start()
        assert held.wait(5)
        os.kill(os.getpid(), signal.SIGUSR1)
        deadline = time.monotonic() + 5
        while not list((folder / 'diagnostics').glob('thread-dump-*.txt')) and time.monotonic() < deadline:
            time.sleep(0.05)
        release.set()
    """)
    done = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    [dump] = list((tmp_path / 'diagnostics').glob('thread-dump-*.txt'))
    text = dump.read_text(encoding='utf-8')
    assert f"{(tmp_path / 'blocked.db').resolve()}: thread writer-that-blocks" in text
    # The thread that holds it first, with where it waits.
    assert text.index('Thread writer-that-blocks') < text.index('Thread MainThread')
    assert 'holds a workspace write lock' in text and 'release.wait(10)' in text
    # Also in the server log.
    assert 'Thread dump of DriveTest Analyzer' in done.stderr and 'Thread dump written to' in done.stderr


def test_install_needs_the_main_thread():
    import threading

    from src.modules.core import thread_dump

    results = []
    worker = threading.Thread(target=lambda: results.append(thread_dump.install(None)))
    worker.start()
    worker.join(5)
    assert results == [False]
    assert 'Workspace write locks held:' in thread_dump.dump_text()
