"""The Points Lost Map of one methodology drawn in a process of its own (see saved_filters._points_loss_of).

The application keeps answering while the rows of the tests are read and mapped, a stop ends the process at once, and
its memory is given back when it ends. The parent sends the inputs pickled on stdin; the process reports its progress
on stdout (one line per step, after ``MESSAGE``) and leaves the map pickled in the file it was given.
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import threading
import time
import traceback
from pathlib import Path

MESSAGE = '\x1epoints-loss\x1e'


def _send(message: dict) -> None:
    sys.stdout.write(MESSAGE + json.dumps(message) + '\n')
    sys.stdout.flush()


def _end_with_the_application() -> None:
    """End this process when the application that started it ends (a restart, a deployment)."""
    parent = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != parent:
            os._exit(1)


def main() -> int:
    threading.Thread(target=_end_with_the_application, name='points-loss-parent', daemon=True).start()
    payload = pickle.load(sys.stdin.buffer)
    try:
        from src.modules import saved_filters
        from src.modules.repository import Repository

        repository = Repository(Path(payload['db_path']), Path(payload['global_db_path']),
                                Path(payload['registry_db_path']) if payload['registry_db_path'] else None)
        points_loss = saved_filters.draw_points_loss(
            repository, payload['saved_filter'], payload['sources'], payload['configuration'],
            payload['context_filters'], saved_filters._scoring_engine(),
            lambda value, step: _send({'progress': float(value), 'step': str(step)}))
        with open(payload['result_path'], 'wb') as handle:
            pickle.dump(points_loss, handle, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:  # The parent shows the error of the map.
        traceback.print_exc()
        _send({'error': str(exc) or type(exc).__name__})
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
