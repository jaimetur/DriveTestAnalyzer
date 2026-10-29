"""The preparations of the PPT Designs and the models of their charts, kept in the workspace folder
(``.ppt-designer-cache``) so a restart restores them instead of working them out again.

Each one is a gzip file named after its key, which changes with what it was made from (the CDRs and their revisions,
the selection, the template and format, the mappings and the renderer), so any change works it out again. A file is
written to a temporary file and then renamed, so a file under its final name is always complete; one that cannot be read
(cut by a crash or a full disk) is deleted and worked out again. The most recently used are kept, up to ``MAX_MB`` per
workspace (``DRIVETEST_ANALYZER_PPT_CHART_CACHE_MB``), and what nothing has used for ``UNUSED_DAYS`` days goes.

A cache: left out of backups, exports and transfers, moved with its workspace when it is renamed, deleted with it, and
emptied by Clear workspace cache (the folder is set aside at once and deleted in the background).
"""
from __future__ import annotations

import gzip
import json
import os
import shutil
import sqlite3
import threading
import time
import zlib
from contextlib import closing
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

CACHE_FOLDER = '.ppt-designer-cache'
# A folder set aside by Clear workspace cache, deleted in the background (and when the workspace opens, if the
# deletion was cut short).
TRASH_PREFIX = f'{CACHE_FOLDER}.removing-'
MAX_MB = 1024
UNUSED_DAYS = 30
# The unused files and the temporary files left by a write cut short are looked for again after this many seconds.
RESCAN_SECONDS = 24 * 60 * 60
STALE_TEMPORARY_SECONDS = 60 * 60
# A file read or found again is marked as used at most this often (its modification time).
TOUCH_SECONDS = 60 * 60
# The tables of the workspace database that held them in earlier versions.
DATABASE_TABLES = ('design_chart_models', 'design_preview_manifests')

_lock = threading.Lock()
# What each cache folder holds (path -> (last use, size)), read once and then kept up to date.
_indexes: dict[str, dict[str, Any]] = {}


def limit_bytes() -> int:
    try:
        megabytes = float(os.environ.get('DRIVETEST_ANALYZER_PPT_CHART_CACHE_MB') or MAX_MB)
    except ValueError:
        megabytes = MAX_MB
    return int(max(0.0, megabytes) * 1024 * 1024)


def root_of(workspace: str | Path) -> Path:
    """The cache folder of a workspace, given its database."""
    return Path(workspace).resolve().parent / CACHE_FOLDER


def chart_path(workspace: str | Path, key: str) -> Path:
    return root_of(workspace) / 'charts' / key[:2] / f'{key}.json.gz'


def preparation_key(version: int, design_id: str, fingerprint: str) -> str:
    return sha256(f'{version}:{design_id}:{fingerprint}'.encode()).hexdigest()


def _design_folder(workspace: str | Path, design_id: str) -> Path:
    return root_of(workspace) / 'preparations' / sha256(design_id.encode()).hexdigest()[:32]


def preparation_path(workspace: str | Path, design_id: str, key: str) -> Path:
    return _design_folder(workspace, design_id) / f'{key}.json.gz'


def _index(root: Path) -> dict[str, Any]:
    """The index of a cache folder (with the lock held): read again when it is new or old."""
    index = _indexes.get(str(root))
    if index is not None and time.time() - index['scanned'] < RESCAN_SECONDS:
        return index
    now = time.time()
    files: dict[str, tuple[float, int]] = {}
    if root.is_dir():
        for folder, _folders, names in os.walk(root):
            for name in names:
                path = os.path.join(folder, name)
                try:
                    stat = os.stat(path)
                    if name.endswith('.tmp'):
                        # Left by a write cut short (a crash, a full disk).
                        if now - stat.st_mtime > STALE_TEMPORARY_SECONDS:
                            os.unlink(path)
                    elif not name.endswith('.json.gz') or now - stat.st_mtime > UNUSED_DAYS * 86400:
                        os.unlink(path)
                    else:
                        files[path] = (stat.st_mtime, stat.st_size)
                except OSError:
                    continue
    index = {'scanned': now, 'files': files, 'total': sum(size for _mtime, size in files.values())}
    _indexes[str(root)] = index
    return index


def _noted(path: Path, size: int | None) -> None:
    """Note a file written (with its size), used again (``size`` None) or removed (``size`` -1)."""
    root = next((parent for parent in path.parents if parent.name == CACHE_FOLDER), None)
    if root is None:
        return
    with _lock:
        index = _indexes.get(str(root))
        if index is None:
            return
        previous = index['files'].pop(str(path), None)
        if previous:
            index['total'] -= previous[1]
        if size is None and previous:
            size = previous[1]
        if size is not None and size >= 0:
            index['files'][str(path)] = (time.time(), size)
            index['total'] += size


def _prune(root: Path) -> None:
    """Delete the least recently used files beyond the size kept, down to nine tenths of it."""
    limit = limit_bytes()
    with _lock:
        index = _index(root)
        if index['total'] <= limit:
            return
        for path, (_mtime, size) in sorted(index['files'].items(), key=lambda item: item[1][0]):
            if index['total'] <= limit * 0.9:
                break
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError:
                continue
            del index['files'][path]
            index['total'] -= size


def _touch(path: Path, mtime: float) -> None:
    if time.time() - mtime > TOUCH_SECONDS:
        try:
            os.utime(path)
        except OSError:
            return
        _noted(path, None)


def read(path: Path) -> dict | None:
    """The value kept in ``path``, or None; a file that cannot be read is deleted."""
    try:
        mtime = path.stat().st_mtime
        with gzip.open(path, 'rb') as handle:
            value = json.loads(handle.read())
    except FileNotFoundError:
        return None
    except (OSError, EOFError, ValueError, zlib.error):
        forget(path)
        return None
    if not isinstance(value, dict):
        forget(path)
        return None
    _touch(path, mtime)
    return value


def exists(path: Path) -> bool:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    _touch(path, mtime)
    return True


def write(path: Path, value: Any) -> bool:
    """Keep a value (JSON values only): written whole under a temporary name, then renamed. Returns whether it was
    kept; a failure (a full disk) only leaves it out."""
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(temporary, 'wb', compresslevel=6) as handle:
            handle.write(json.dumps(value, separators=(',', ':'), default=str).encode())
        size = temporary.stat().st_size
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError):
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    root = next(parent for parent in path.parents if parent.name == CACHE_FOLDER)
    with _lock:
        _index(root)
    _noted(path, size)
    _prune(root)
    return True


def forget(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return
    _noted(path, -1)


def has_preparation(workspace: str | Path, design_id: str) -> bool:
    try:
        return any(_design_folder(workspace, design_id).glob('*.json.gz'))
    except OSError:
        return False


def usage(workspace: str | Path) -> tuple[int, int]:
    """The files kept for a workspace and their size in bytes."""
    root = root_of(workspace)
    with _lock:
        index = _index(root)
        return len(index['files']), index['total']


def trash_folders(workspace_root: Path) -> list[Path]:
    try:
        return sorted(path for path in workspace_root.glob(f'{TRASH_PREFIX}*') if path.is_dir())
    except OSError:
        return []


def clear(workspace: str | Path) -> Path | None:
    """Empty the cache of a workspace at once: its folder is set aside (returned) for the caller to delete."""
    root = root_of(workspace)
    with _lock:
        _indexes.pop(str(root), None)
        if not root.exists():
            return None
        trash = root.with_name(f'{TRASH_PREFIX}{uuid4().hex[:12]}')
        try:
            os.replace(root, trash)
        except OSError:
            shutil.rmtree(root, ignore_errors=True)
            return None
    return trash


def move_database_rows(database_path: str | Path, preparation_name: Callable[[dict], str | None]) -> dict[str, int]:
    """Move what earlier versions kept in the workspace database to the cache folder and drop their tables.
    ``preparation_name`` gives the key of a preparation (None leaves it out). Returns what was moved."""
    moved = {'charts': 0, 'preparations': 0, 'bytes': 0}
    with closing(sqlite3.connect(database_path, timeout=30)) as connection:
        tables = {row[0] for row in connection.execute(
            f"SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({', '.join('?' for _ in DATABASE_TABLES)})",
            DATABASE_TABLES,
        )}
        if not tables:
            return moved

        def rows(query: str):
            for row in connection.execute(query):
                try:
                    yield row[0], json.loads(zlib.decompress(row[1]))
                except (zlib.error, ValueError, TypeError):
                    continue

        if 'design_chart_models' in tables:
            for key, value in rows('SELECT cache_key, model FROM design_chart_models'):
                path = chart_path(database_path, key)
                if isinstance(value, dict) and write(path, value):
                    moved['charts'] += 1
                    moved['bytes'] += path.stat().st_size
        if 'design_preview_manifests' in tables:
            for _key, value in rows('SELECT cache_key, manifest FROM design_preview_manifests'):
                key = preparation_name(value) if isinstance(value, dict) else None
                path = preparation_path(database_path, str(value.get('design_id') or ''), key) if key else None
                if path is not None and write(path, value):
                    moved['preparations'] += 1
                    moved['bytes'] += path.stat().st_size
        with connection:
            for table in DATABASE_TABLES:
                connection.execute(f'DROP TABLE IF EXISTS {table}')
    return moved
