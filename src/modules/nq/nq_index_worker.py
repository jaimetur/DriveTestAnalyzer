"""The reading of some CDRs of a Non-Qualified Calls indexing, in a process of its own (see
non_qualified_calls._read_cdrs_apart).

Several of these processes read the CDRs of an indexing at once, at a low priority so the application keeps the
processor for its users. The parent sends the inputs pickled on stdin; the process leaves what it read of each CDR
(non_qualified_calls._dataset_calls) pickled in its own file of the folder it was given, and says so on stdout (one
line per CDR, after ``MESSAGE``, with its fingerprint: non_qualified_calls._index_fingerprint).
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

MESSAGE = '\x1enq-index\x1e'


def _send(message: dict) -> None:
    sys.stdout.write(MESSAGE + json.dumps(message) + '\n')
    sys.stdout.flush()


def _end_with_the_application() -> None:
    """End this process when the application that started it ends (a restart, a deployment, a stop)."""
    parent = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != parent:
            os._exit(1)


def main() -> int:
    threading.Thread(target=_end_with_the_application, name='nq-index-parent', daemon=True).start()
    try:
        os.nice(10)
    except OSError:
        pass
    payload = pickle.load(sys.stdin.buffer)
    try:
        from src.modules.cdr import cdr_store
        from src.modules.core.repository import Repository
        from src.modules.nq import non_qualified_calls as nq

        # The copies are only read here: their upkeep belongs to the application.
        cdr_store.AUTOMATIC = False
        repository = Repository(Path(payload['db_path']), Path(payload['global_db_path']),
                                Path(payload['registry_db_path']) if payload['registry_db_path'] else None)
        folder = Path(payload['folder'])
        with repository.connection() as connection:
            for dataset in payload['datasets']:
                content = nq._dataset_calls(connection, dataset, tuple(payload['cdr_columns']), payload['profile'],
                                            payload['sample_radio'])
                result = folder / f"cdr-{int(dataset['id'])}.pickle"
                temporary = result.with_suffix('.tmp')
                with open(temporary, 'wb') as handle:
                    pickle.dump(content, handle, protocol=pickle.HIGHEST_PROTOCOL)
                temporary.replace(result)
                # Its fingerprint, worked out here while the other processes read theirs.
                _send({'dataset_id': int(dataset['id']), 'fingerprint': nq._index_fingerprint(content)})
    except Exception as exc:  # The parent reads the CDRs left in its own process.
        traceback.print_exc()
        _send({'error': str(exc) or type(exc).__name__})
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
