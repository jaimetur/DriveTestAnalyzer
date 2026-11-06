"""The free space of a disk, counting what macOS frees on demand."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Asks macOS for the space available for important writes, which counts what it frees on demand.
MACOS_IMPORTANT_CAPACITY_SCRIPT = (
    'function run(argv) { ObjC.import("Foundation"); const value = Ref(); '
    '$.NSURL.fileURLWithPath(argv[0]).getResourceValueForKeyError(value, $.NSURLVolumeAvailableCapacityForImportantUsageKey, null); '
    'return String(ObjC.unwrap(value[0])); }'
)


def available_disk_space(path: Path) -> int:
    """The bytes a backup or a copy can use in ``path``: on macOS also what the system frees on demand (local Time
    Machine snapshots, caches), as its storage settings show it; elsewhere what the file system reports free."""
    free = shutil.disk_usage(path).free
    if sys.platform == 'darwin':
        try:
            result = subprocess.run(['/usr/bin/osascript', '-l', 'JavaScript', '-e', MACOS_IMPORTANT_CAPACITY_SCRIPT, str(path)],
                                    capture_output=True, text=True, timeout=15, check=True)
            return max(free, int(float(result.stdout.strip())))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return free
