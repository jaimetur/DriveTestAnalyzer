"""Calculations that Saved Filters share, kept in the cache folder of the workspace (``.cache/scoring``): the National &
Geographical Areas Trends and the Points Lost Map of each methodology. Another Saved Filter with the same CDRs,
methodology and options (or the same one calculated again) reads them instead of calculating them again.

The key of each one holds everything it depends on (the revision of its CDRs, the methodology, the options, the
Operator Maps, the Map Areas and the code of the scoring modules), so any change calculates it again. The most
recently used ones are kept, up to ``MAX_BYTES`` (compressed) per workspace.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

from src.modules import workspace_cache

CACHE_VERSION = 1
MAX_BYTES = 1024 ** 3
# The modules whose code calculates what is kept: a change in any of them calculates it again.
CODE_MODULES = ('saved_filters', 'scoring', 'scoring_area_summary', 'scoring_history', 'scoring_methodologies',
                'scoring_points_loss', 'scoring_vendors', 'map_areas', 'map_area_columns')
_prune_lock = threading.Lock()
_code_version: str | None = None


def code_version() -> str:
    global _code_version
    if _code_version is None:
        digest = hashlib.sha256()
        for name in CODE_MODULES:
            try:
                digest.update((Path(__file__).parent / f'{name}.py').read_bytes())
            except OSError:
                digest.update(name.encode('utf-8'))
        _code_version = digest.hexdigest()
    return _code_version


def key_of(payload: Any) -> str:
    return hashlib.sha256(json.dumps([CACHE_VERSION, code_version(), payload], sort_keys=True, default=str,
                                     ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def _folder(repository: Any, kind: str) -> Path | None:
    db_path = getattr(repository, 'db_path', None)
    return workspace_cache.of_database(db_path, workspace_cache.SCORING) / kind if db_path else None


def read(repository: Any, kind: str, key: str) -> Any | None:
    """The calculation kept with this key, or None."""
    folder = _folder(repository, kind)
    if folder is None:
        return None
    path = folder / f'{key}.json.gz'
    try:
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            value = json.load(handle)
    except (OSError, EOFError, ValueError):
        return None
    try:
        os.utime(path)  # The most recently used are kept.
    except OSError:
        pass
    return value


def write(repository: Any, kind: str, key: str, value: Any) -> None:
    """Keep a calculation (JSON values only); a failure to write only leaves it out."""
    folder = _folder(repository, kind)
    if folder is None:
        return
    temporary = folder / f'.{key}.{os.getpid()}.{threading.get_ident()}.tmp'
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with gzip.open(temporary, 'wt', encoding='utf-8', compresslevel=3) as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        os.replace(temporary, folder / f'{key}.json.gz')
    except (OSError, TypeError, ValueError):
        temporary.unlink(missing_ok=True)
        return
    _prune(folder.parent)


def _prune(root: Path) -> None:
    """Delete the least recently used calculations beyond ``MAX_BYTES``."""
    with _prune_lock:
        try:
            files = [(path.stat().st_mtime, path.stat().st_size, path) for path in root.glob('*/*.json.gz')]
        except OSError:
            return
        total = sum(size for _mtime, size, _path in files)
        for _mtime, size, path in sorted(files):
            if total <= MAX_BYTES:
                break
            path.unlink(missing_ok=True)
            total -= size
