"""The result of a Saved Scoring as served, built in a process of its own (see scoring_served_result, ticket #188).

Building the views of a large result keeps a processor busy for up to a minute: in the process of the application it
would slow down the requests of every other user meanwhile. The parent sends the inputs pickled on stdin; the process
leaves the result as served (JSON compressed with gzip) in the file it was given, or the error in its error file.
"""
from __future__ import annotations

import os
import pickle
import sys
import threading
import time
from pathlib import Path

# The exit code of a result whose views cannot be built (its message is in the error file).
VIEWS_ERROR = 3


def _end_with_the_application() -> None:
    """End this process when the application that started it ends (a restart, a deployment)."""
    parent = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != parent:
            os._exit(1)


def main() -> int:
    threading.Thread(target=_end_with_the_application, name='scoring-result-parent', daemon=True).start()
    payload = pickle.load(sys.stdin.buffer)
    from src.modules.cdr.column_names import use_campaign_map
    from src.modules.scoring.scoring_served_result import ResultViewsError, packed_payload, saved_scoring_payload
    try:
        with use_campaign_map(payload['campaign_map']):
            packed = packed_payload(saved_scoring_payload(payload['saved_scoring'], payload['operator_groups'],
                                                          payload['vendor_groups'], payload['fallback']))
    except ResultViewsError as exc:
        Path(payload['error_path']).write_text(str(exc), encoding='utf-8')
        return VIEWS_ERROR
    result = Path(payload['result_path'])
    writing = result.with_name(f'.writing-{result.name}')
    writing.write_bytes(packed)
    os.replace(writing, result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
