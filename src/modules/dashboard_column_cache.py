"""Per-CDR column cache for Dashboard chart reads.

Each combined CDR table is cached per dataset and per SQL expression, in table
row order. Any Dashboard universe (CDRs, dates and filter values) and either
comparison mode can then be assembled in memory without querying SQLite.

Columns are stored compactly and reassembled with the same type inference as
``pandas.read_sql_query`` applies to the combined result rows, so an assembled
frame is identical to the frame SQLite would have returned for the same rows.
"""
from __future__ import annotations

import hashlib
import os
import pickle
import re
import shutil
import sqlite3
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from pandas._libs import lib
from pandas.core.internals.construction import convert_object_array

from src.modules import cdr_store

CACHE_FORMAT_VERSION = 1
ROWID = '__cache_rowid'
ORDER_DATE = '__cache_order_date'
# The expression of the combined tables' (dataset_id, event date) index.
ORDER_DATE_SQL = 'date(CAST("event_start_time" AS TEXT))'
# Expressions fetched by one SQLite query when a CDR segment is built.
BUILD_BATCH_SIZE = 24
ORDER_MODES = ('dataset_rowid', 'dataset_date_rowid', 'rowid')

_TOKEN_PATTERN = re.compile(r"'(?:[^']|'')*'|\"((?:[^\"]|\"\")*)\"")


def quote_identifier(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


@dataclass(frozen=True)
class CacheSource:
    """One physical combined CDR table, read directly or through a union branch.

    ``projection`` maps the branch aliases of an RF union to their physical SQL,
    so expressions over aliases are cached by their physical meaning and shared
    whatever other CDR types the union contains.
    """

    kind: str
    table: str
    projection: tuple[tuple[str, str], ...] = ()
    has_event_time: bool = True

    def physical(self, expression: str) -> str:
        """Rewrite an expression over branch aliases into physical table SQL."""
        if not self.projection:
            return expression
        aliases = dict(self.projection)

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name is None:
                return match.group(0)
            alias = name.replace('""', '"')
            return f'({aliases[alias]})' if alias in aliases else match.group(0)

        return _TOKEN_PATTERN.sub(replace, expression)


@dataclass(frozen=True)
class Segment:
    """The rows of one CDR inside one combined table, at one data revision."""

    source: CacheSource
    dataset_id: int
    version: str


@dataclass(frozen=True)
class SelectionTerms:
    """Row predicates of a Dashboard universe, evaluated on cached expressions.

    ``values`` holds ``(expression, allowed)`` pairs: the expression's text value
    must be one of ``allowed``; a ``None`` expression selects no row. ``date``
    holds ``(expression, low, high)`` ISO date bounds. ``excluded_sheets`` keeps
    rows whose sheet is NULL or not excluded, and each ``(expression, excluded)``
    pair of ``excluded_values`` rows whose value is NULL or not excluded (such as
    the operators the Operator Maps exclude). Each ``(dataset ids, expression,
    excluded)`` of ``dataset_excluded_values`` does the same on the rows of those
    CDRs alone (the operators out of scope in their NR Mode).
    """

    values: tuple[tuple[str | None, frozenset[str]], ...] = ()
    date: tuple[str | None, str | None, str | None] | None = None
    excluded_sheets: tuple[str, frozenset[str]] | None = None
    excluded_values: tuple[tuple[str, frozenset[str]], ...] = ()
    dataset_excluded_values: tuple[tuple[frozenset[int], str, frozenset[str]], ...] = ()

    def expressions(self) -> list[str]:
        result = [expression for expression, _allowed in self.values if expression]
        if self.date and self.date[0]:
            result.append(self.date[0])
        if self.excluded_sheets:
            result.append(self.excluded_sheets[0])
        result.extend(expression for expression, _excluded in self.excluded_values)
        result.extend(expression for _datasets, expression, _excluded in self.dataset_excluded_values)
        return result


class StaleSegment(RuntimeError):
    """A cached segment no longer matches the rows SQLite returns."""


# ---------------------------------------------------------------------------
# Compact column parts
#
# A part is a tuple whose first item is its kind:
#   ('none', length)                  every value is NULL
#   ('float', float64)                REAL values or NULL (NaN marks NULL)
#   ('int', int64)                    INTEGER values, no NULL
#   ('intnull', int64, null_mask)     INTEGER values and NULL
#   ('str', int32 codes, categories)  TEXT values or NULL (code -1)
#   ('object', object array)          anything else, kept as returned
# ---------------------------------------------------------------------------

def encode_values(values: np.ndarray) -> tuple:
    """Encode one column of SQLite values without losing their Python types."""
    values = np.asarray(values, dtype=object)
    length = len(values)
    inferred = lib.infer_dtype(values, skipna=True)
    if inferred == 'empty':
        return ('none', length)
    if inferred == 'floating' and all(value is None or type(value) is float for value in values):
        return ('float', np.asarray(lib.maybe_convert_objects(values, try_float=True), dtype=np.float64))
    if inferred == 'integer' and all(value is None or type(value) is int for value in values):
        nulls = np.fromiter((value is None for value in values), dtype=bool, count=length)
        try:
            present = np.array(values[~nulls].tolist(), dtype=np.int64)
        except OverflowError:
            return ('object', values)
        if not nulls.any():
            return ('int', present)
        integers = np.zeros(length, dtype=np.int64)
        integers[~nulls] = present
        return ('intnull', integers, nulls)
    if inferred == 'string' and all(value is None or type(value) is str for value in values):
        codes, categories = pd.factorize(values)
        return ('str', codes.astype(np.int32), np.asarray(categories, dtype=object))
    return ('object', values)


def encode_by_codes(values: Sequence[Any], codes: np.ndarray) -> tuple:
    """``encode_values`` of ``values`` taken at ``codes`` (each row the code of its value), from the distinct ``values``
    alone: the same kinds, codes and categories, without going through each row."""
    if not len(codes) or not np.bincount(codes, minlength=len(values)).all():
        # Rows that show only some of the values: the kinds follow those they show.
        return encode_values(np.asarray(values, dtype=object)[codes] if len(codes) else np.empty(0, dtype=object))
    part = encode_values(np.asarray(values, dtype=object))
    kind = part[0]
    if kind == 'none':
        return ('none', len(codes))
    if kind in {'float', 'int'}:
        return (kind, part[1][codes])
    if kind == 'intnull':
        return ('intnull', part[1][codes], part[2][codes])
    if kind == 'str':
        # The categories in the order the rows show them first, as pd.factorize gives them over the rows (-1: NULL).
        rows = part[1][codes]
        present = rows >= 0
        if not present.any():
            return ('str', np.full(len(rows), -1, dtype=np.int32), np.asarray([], dtype=object))
        shown, first_row, inverse = np.unique(rows[present], return_index=True, return_inverse=True)
        order = np.argsort(first_row, kind='stable')
        renumbered = np.empty(len(shown), dtype=np.int32)
        renumbered[order] = np.arange(len(shown), dtype=np.int32)
        result = np.full(len(rows), -1, dtype=np.int32)
        result[present] = renumbered[inverse.reshape(-1)]
        return ('str', result, np.asarray(part[2][shown[order]], dtype=object))
    return ('object', np.asarray(values, dtype=object)[codes])


def part_length(part: tuple) -> int:
    return int(part[1]) if part[0] == 'none' else len(part[1])


def part_nbytes(part: tuple) -> int:
    if part[0] == 'none':
        return 64
    if part[0] == 'object':
        return len(part[1]) * 64
    size = sum(item.nbytes for item in part[1:] if isinstance(item, np.ndarray) and item.dtype != object)
    if part[0] == 'str':
        size += sum(len(str(value)) + 56 for value in part[2])
    return size + 64


def _subset_kind(part: tuple, positions: np.ndarray) -> str | None:
    if not len(positions):
        return None
    kind = part[0]
    if kind == 'float':
        return 'none' if np.isnan(part[1][positions]).all() else 'float'
    if kind == 'intnull':
        nulls = part[2][positions]
        return 'none' if nulls.all() else ('intnull' if nulls.any() else 'int')
    if kind == 'str':
        return 'none' if (part[1][positions] < 0).all() else 'str'
    return kind


def decode_objects(part: tuple, positions: np.ndarray) -> np.ndarray:
    """Return the selected values as the Python objects SQLite returned."""
    kind = part[0]
    if kind == 'none':
        return np.full(len(positions), None, dtype=object)
    if kind == 'float':
        values = part[1][positions]
        result = values.astype(object)
        result[np.isnan(values)] = None
        return result
    if kind == 'int':
        return part[1][positions].astype(object)
    if kind == 'intnull':
        result = part[1][positions].astype(object)
        result[part[2][positions]] = None
        return result
    if kind == 'str':
        codes = part[1][positions]
        missing = codes < 0
        if not len(part[2]):
            return np.full(len(positions), None, dtype=object)
        result = part[2].take(np.where(missing, 0, codes)).astype(object)
        result[missing] = None
        return result
    return np.asarray(part[1], dtype=object)[positions]


def assemble_column(pieces: Sequence[tuple[tuple, np.ndarray]]) -> np.ndarray:
    """Concatenate selected values with ``read_sql_query``'s type inference."""
    pieces = [(part, positions) for part, positions in pieces if len(positions)]
    total = sum(len(positions) for _part, positions in pieces)
    kinds = {_subset_kind(part, positions) for part, positions in pieces}
    if kinds == {'none'}:
        return np.full(total, None, dtype=object)
    numeric = {'float', 'int', 'intnull'}
    if kinds == {'int'}:
        return np.concatenate([part[1][positions] for part, positions in pieces])
    if kinds and kinds <= numeric | {'none'}:
        arrays = []
        for part, positions in pieces:
            kind = part[0]
            if kind == 'float':
                arrays.append(part[1][positions])
            elif kind in {'int', 'intnull'}:
                values = part[1][positions].astype(np.float64)
                if kind == 'intnull':
                    values[part[2][positions]] = np.nan
                arrays.append(values)
            else:
                arrays.append(np.full(len(positions), np.nan))
        return np.concatenate(arrays)
    objects = np.concatenate([decode_objects(part, positions) for part, positions in pieces]) if pieces else np.empty(0, dtype=object)
    if kinds and kinds <= {'str', 'none'}:
        return objects
    return convert_object_array([objects], dtype=None, coerce_float=True, dtype_backend='numpy')[0]


def frame_from_columns(columns: Sequence[str], arrays: Sequence[np.ndarray], rows: int) -> pd.DataFrame:
    """Build the frame exactly like ``pandas.read_sql_query`` does."""
    if not rows:
        return pd.DataFrame(columns=list(columns))
    frame = pd.DataFrame(dict(zip(range(len(columns)), arrays)))
    frame.columns = list(columns)
    return frame


def match_values(part: tuple, allowed: frozenset[str]) -> np.ndarray:
    """Rows whose text value is one of ``allowed``; NULL never matches."""
    if part[0] == 'str':
        accepted = np.fromiter((value in allowed for value in part[2]), dtype=bool, count=len(part[2]))
        codes = part[1]
        return np.where(codes >= 0, accepted[np.maximum(codes, 0)] if len(accepted) else False, False)
    if part[0] == 'none':
        return np.zeros(part_length(part), dtype=bool)
    values = decode_objects(part, np.arange(part_length(part)))
    return np.fromiter((value is not None and str(value) in allowed for value in values), dtype=bool, count=len(values))


def match_range(part: tuple, low: str | None, high: str | None) -> np.ndarray:
    """Rows whose text value lies within inclusive bounds; NULL never matches."""
    def accepted(value) -> bool:
        if value is None:
            return False
        text = str(value)
        return (low is None or text >= low) and (high is None or text <= high)

    if part[0] == 'str':
        allowed = np.fromiter((accepted(value) for value in part[2]), dtype=bool, count=len(part[2]))
        codes = part[1]
        return np.where(codes >= 0, allowed[np.maximum(codes, 0)] if len(allowed) else False, False)
    if part[0] == 'none':
        return np.zeros(part_length(part), dtype=bool)
    values = decode_objects(part, np.arange(part_length(part)))
    return np.fromiter((accepted(value) for value in values), dtype=bool, count=len(values))


def keep_sheets(part: tuple, excluded: frozenset[str]) -> np.ndarray:
    """``sheet IS NULL OR normalized sheet NOT IN excluded``."""
    if part[0] == 'str':
        rejected = np.fromiter((value in excluded for value in part[2]), dtype=bool, count=len(part[2]))
        codes = part[1]
        return np.where(codes >= 0, ~rejected[np.maximum(codes, 0)] if len(rejected) else True, True)
    if part[0] == 'none':
        return np.ones(part_length(part), dtype=bool)
    values = decode_objects(part, np.arange(part_length(part)))
    return np.fromiter((value is None or str(value) not in excluded for value in values), dtype=bool, count=len(values))


def _date_ranks(part: tuple) -> np.ndarray:
    """Rank event dates in index order (NULL first, then ascending text)."""
    if part[0] == 'str':
        categories = part[2]
        order = np.argsort(np.asarray([str(value) for value in categories], dtype=object), kind='stable')
        ranks = np.empty(len(categories), dtype=np.int64)
        ranks[order] = np.arange(len(categories))
        codes = part[1]
        return np.where(codes >= 0, ranks[np.maximum(codes, 0)] if len(ranks) else -1, -1)
    if part[0] == 'none':
        return np.full(part_length(part), -1, dtype=np.int64)
    values = decode_objects(part, np.arange(part_length(part)))
    texts = sorted({str(value) for value in values if value is not None})
    lookup = {text: rank for rank, text in enumerate(texts)}
    return np.fromiter((-1 if value is None else lookup[str(value)] for value in values), dtype=np.int64, count=len(values))


# ---------------------------------------------------------------------------
# Cache storage
# ---------------------------------------------------------------------------

@dataclass
class _Memory:
    budget: int
    parts: OrderedDict = field(default_factory=OrderedDict)
    size: int = 0


class ColumnCache:
    """Memory cache of per-CDR expression columns, also kept on disk with ``persist``."""

    def __init__(self, root: Path, *, memory_bytes: int, disk_bytes: int, persist: bool = True):
        self.root = Path(root) / f'v{CACHE_FORMAT_VERSION}'
        self.disk_bytes = disk_bytes
        self.persist = persist
        self._memory = _Memory(memory_bytes)
        self._lock = threading.RLock()
        self._segment_locks: dict[tuple, threading.Lock] = {}
        self._writes = 0

    # -- paths --------------------------------------------------------------
    def _dataset_dir(self, source: CacheSource, dataset_id: int) -> Path:
        return self.root / re.sub(r'[^A-Za-z0-9_.-]', '_', source.table) / str(int(dataset_id))

    def _segment_dir(self, segment: Segment) -> Path:
        version = hashlib.sha256(segment.version.encode()).hexdigest()[:24]
        return self._dataset_dir(segment.source, segment.dataset_id) / version

    @staticmethod
    def _part_name(expression: str) -> str:
        return hashlib.sha256(expression.encode()).hexdigest()[:32] + '.pkl'

    # -- memory -------------------------------------------------------------
    def _remember(self, key: str, part: tuple) -> None:
        with self._lock:
            memory = self._memory
            previous = memory.parts.pop(key, None)
            if previous is not None:
                memory.size -= part_nbytes(previous)
            memory.parts[key] = part
            memory.size += part_nbytes(part)
            while memory.size > memory.budget and len(memory.parts) > 1:
                _old_key, old_part = memory.parts.popitem(last=False)
                memory.size -= part_nbytes(old_part)

    def _recall(self, key: str) -> tuple | None:
        with self._lock:
            part = self._memory.parts.get(key)
            if part is not None:
                self._memory.parts.move_to_end(key)
            return part

    def forget(self) -> None:
        with self._lock:
            self._memory.parts.clear()
            self._memory.size = 0

    # -- disk ---------------------------------------------------------------
    def _read_part(self, path: Path, expression: str, *, remember: bool = True) -> tuple | None:
        key = str(path)
        part = self._recall(key)
        if part is not None or not self.persist:
            return part
        try:
            payload = pickle.loads(path.read_bytes())
            # Recently used CDRs are the last ones removed by the disk budget.
            os.utime(path)
        except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ValueError):
            return None
        if not isinstance(payload, tuple) or len(payload) != 3 or payload[0] != CACHE_FORMAT_VERSION or payload[1] != expression:
            return None
        part = payload[2]
        if remember:
            self._remember(key, part)
        return part

    def _write_part(self, path: Path, expression: str, part: tuple, *, remember: bool = True) -> None:
        if remember or not self.persist:
            self._remember(str(path), part)
        if not self.persist:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f'{path.name}.{uuid4().hex}.tmp')
            temporary.write_bytes(pickle.dumps((CACHE_FORMAT_VERSION, expression, part), protocol=pickle.HIGHEST_PROTOCOL))
            temporary.replace(path)
        except OSError:
            return
        self._writes += 1
        if self._writes % 64 == 0:
            self.prune()

    def _stored(self, path: Path) -> bool:
        """Whether a part is kept (on disk with ``persist``, else in memory)."""
        if not self.persist:
            with self._lock:
                return str(path) in self._memory.parts
        return path.is_file()

    def prune(self) -> None:
        """Keep the cache within its disk budget, removing the oldest CDRs first."""
        if not self.persist or not self.root.is_dir():
            return
        segments = []
        total = 0
        for directory in self.root.glob('*/*/*'):
            if not directory.is_dir():
                continue
            files = list(directory.glob('*.pkl'))
            size = sum(path.stat().st_size for path in files if path.exists())
            stamp = max((path.stat().st_mtime for path in files if path.exists()), default=0.0)
            segments.append((stamp, size, directory))
            total += size
        for _stamp, size, directory in sorted(segments, key=lambda item: item[0]):
            if total <= self.disk_bytes:
                break
            shutil.rmtree(directory, ignore_errors=True)
            total -= size

    def _discard_other_versions(self, segment: Segment) -> None:
        current = self._segment_dir(segment)
        parent = current.parent
        if not self.persist:
            # The columns of the other versions of the CDR leave memory.
            prefix, kept = f'{parent}{os.sep}', f'{current}{os.sep}'
            with self._lock:
                for key in [key for key in self._memory.parts if key.startswith(prefix) and not key.startswith(kept)]:
                    self._memory.size -= part_nbytes(self._memory.parts.pop(key))
            return
        if not parent.is_dir():
            return
        for directory in parent.iterdir():
            if directory != current and directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)

    def invalidate(self, segment: Segment) -> None:
        directory = self._segment_dir(segment)
        prefix = str(directory)
        with self._lock:
            for key in [key for key in self._memory.parts if key.startswith(prefix)]:
                self._memory.size -= part_nbytes(self._memory.parts.pop(key))
        if self.persist:
            shutil.rmtree(directory, ignore_errors=True)

    # -- segments -----------------------------------------------------------
    def _segment_lock(self, segment: Segment) -> threading.Lock:
        key = (segment.source.table, segment.dataset_id, segment.version)
        with self._lock:
            return self._segment_locks.setdefault(key, threading.Lock())

    def segment_parts(
        self,
        connect: Callable[[], sqlite3.Connection],
        segment: Segment,
        expressions: Iterable[str],
        prefetch: Iterable[str] = (),
    ) -> dict[str, tuple]:
        """Return the parts of physical expressions for one CDR, building missing ones.

        ``prefetch`` expressions are built together with missing ones, so a later
        Dashboard filter change finds them without another SQLite read.
        """
        wanted = list(dict.fromkeys([ROWID, ORDER_DATE, *expressions]))
        directory = self._segment_dir(segment)
        with self._segment_lock(segment):
            parts: dict[str, tuple] = {}
            missing = []
            for expression in wanted:
                part = self._read_part(directory / self._part_name(expression), expression)
                if part is None:
                    missing.append(expression)
                else:
                    parts[expression] = part
            if missing:
                extra = [expression for expression in dict.fromkeys(prefetch)
                         if expression not in parts and expression not in missing
                         and not self._stored(directory / self._part_name(expression))]
                if ROWID in missing:
                    self._discard_other_versions(segment)
                built = self._build(connect, segment, [*missing, *extra], parts.get(ROWID))
                for expression, part in built.items():
                    self._write_part(directory / self._part_name(expression), expression, part)
                parts.update({expression: built[expression] for expression in missing})
            lengths = {part_length(part) for part in parts.values()}
            if len(lengths) > 1:
                raise StaleSegment(f'Cached columns of dataset {segment.dataset_id} are misaligned.')
            return parts

    def built_parts(
        self, segment: Segment, expressions: Iterable[str],
        builder: Callable[[Segment, list[str]], dict[str, tuple] | None],
    ) -> dict[str, tuple] | None:
        """The parts of physical expressions for one CDR from ``builder`` (the columnar copy of the CDR), kept in memory
        only; None when the builder cannot give them."""
        wanted = list(dict.fromkeys([ROWID, ORDER_DATE, *expressions]))
        prefix = f'copy\0{segment.source.table}\0{segment.dataset_id}\0{segment.version}\0'
        with self._segment_lock(segment):
            parts = {expression: part for expression in wanted if (part := self._recall(prefix + expression)) is not None}
            missing = [expression for expression in wanted if expression not in parts]
            if missing:
                built = builder(segment, [expression for expression in missing if expression not in {ROWID, ORDER_DATE}])
                if built is None:
                    return None
                for expression, part in built.items():
                    self._remember(prefix + expression, part)
                parts.update({expression: built[expression] for expression in missing})
            if len({part_length(part) for part in parts.values()}) > 1:
                raise StaleSegment(f'Columns of dataset {segment.dataset_id} are misaligned.')
            return parts

    def ensure(
        self,
        connect: Callable[[], sqlite3.Connection],
        segment: Segment,
        expressions: Iterable[str],
        prefetch: Iterable[str] = (),
    ) -> bool:
        """Build a CDR's missing expressions on disk only; return whether any was built.

        Background warming uses it, so it never evicts the columns of the
        universes in use from memory.
        """
        if not self.persist:
            return False
        directory = self._segment_dir(segment)
        wanted = list(dict.fromkeys([ROWID, ORDER_DATE, *expressions, *prefetch]))
        with self._segment_lock(segment):
            missing = [expression for expression in wanted if not (directory / self._part_name(expression)).is_file()]
            if not missing:
                return False
            rowids = None
            if ROWID not in missing:
                rowids = self._read_part(directory / self._part_name(ROWID), ROWID, remember=False)
            if rowids is None:
                self._discard_other_versions(segment)
                missing = list(dict.fromkeys([ROWID, *missing]))
            built = self._build(connect, segment, missing, rowids)
            for expression, part in built.items():
                self._write_part(directory / self._part_name(expression), expression, part, remember=False)
            return True

    def _build(
        self, connect: Callable[[], sqlite3.Connection], segment: Segment,
        expressions: list[str], rowids: tuple | None,
    ) -> dict[str, tuple]:
        source = segment.source
        table = quote_identifier(source.table)
        values = [expression for expression in expressions if expression not in {ROWID, ORDER_DATE}]
        include_order = ROWID in expressions or ORDER_DATE in expressions or rowids is None
        batches = [values[start:start + BUILD_BATCH_SIZE] for start in range(0, len(values), BUILD_BATCH_SIZE)] or [[]]
        built: dict[str, tuple] = {}
        connection = connect()
        try:
            for batch_index, batch in enumerate(batches):
                order_date = ORDER_DATE_SQL if source.has_event_time else 'NULL'
                select = ['rowid', order_date, *(source.physical(expression) for expression in batch)]
                with cdr_store.combined_scope([int(segment.dataset_id)]):
                    rows = connection.execute(
                        f'SELECT {", ".join(select)} FROM {table} WHERE "dataset_id" = ? ORDER BY rowid',
                        (int(segment.dataset_id),),
                    ).fetchall()
                content = lib.to_object_array_tuples(rows) if rows else np.empty((0, len(select)), dtype=object)
                fetched_rowids = encode_values(np.ascontiguousarray(content[:, 0]))
                reference = rowids or built.get(ROWID)
                if reference is not None and not _same_part(reference, fetched_rowids):
                    raise StaleSegment(f'The rows of dataset {segment.dataset_id} changed while caching.')
                if batch_index == 0 and include_order:
                    built[ROWID] = fetched_rowids
                    built[ORDER_DATE] = encode_values(np.ascontiguousarray(content[:, 1]))
                for offset, expression in enumerate(batch, start=2):
                    built[expression] = encode_values(np.ascontiguousarray(content[:, offset]))
        finally:
            connection.close()
        return built


def _same_part(left: tuple, right: tuple) -> bool:
    if part_length(left) != part_length(right):
        return False
    if left[0] != right[0]:
        return False
    if left[0] == 'none':
        return True
    return np.array_equal(left[1], right[1])


# ---------------------------------------------------------------------------
# Frame assembly
# ---------------------------------------------------------------------------

def read_frame(
    cache: ColumnCache,
    connect: Callable[[], sqlite3.Connection],
    segments: Sequence[Segment],
    columns: Sequence[tuple[str, str]],
    terms: SelectionTerms,
    order: str,
    prefetch: Callable[[CacheSource], Iterable[str]] | None = None,
    builder: Callable[[Segment, list[str]], dict[str, tuple] | None] | None = None,
    weighted: bool = False,
) -> pd.DataFrame:
    """Assemble the frame SQLite would return for the selection, in ``order``; ``weighted``, each distinct row once (where
    it is first) with the number of its rows in ``WEIGHT_COLUMN`` (see weighted_rows).

    With ``builder`` the parts of each CDR come from its columnar copy (see build_from_copies), and from SQLite only
    when the builder cannot give them.

    ``columns`` holds ``(output name, expression)`` pairs over each source's
    column namespace. ``order`` is ``dataset_rowid`` (CDRs ascending, then table
    order), ``dataset_date_rowid`` (CDRs, event date, table order) or ``rowid``
    (table order across the CDRs of each source). Sources keep their given order.
    """
    if order not in ORDER_MODES:
        raise ValueError(f'Unsupported row order: {order}')
    names = [name for name, _expression in columns]
    per_column: list[list[tuple[tuple, np.ndarray]]] = [[] for _ in columns]
    groups: list[list[tuple[np.ndarray, np.ndarray]]] = []
    current_table = None
    for segment in segments:
        source = segment.source
        physical_columns = [source.physical(expression) for _name, expression in columns]
        physical_terms = [source.physical(expression) for expression in terms.expressions()]
        parts = cache.built_parts(segment, [*physical_columns, *physical_terms], builder) if builder else None
        if parts is None:
            extra = [source.physical(expression) for expression in (prefetch(source) if prefetch else ())]
            parts = cache.segment_parts(connect, segment, [*physical_columns, *physical_terms], extra)
        positions = np.flatnonzero(selection_mask(parts, source, terms, segment.dataset_id))
        if order == 'dataset_date_rowid' and len(positions):
            ranks = _date_ranks(parts[ORDER_DATE])[positions]
            positions = positions[np.argsort(ranks, kind='stable')]
        for index, expression in enumerate(physical_columns):
            per_column[index].append((parts[expression], positions))
        rowids = parts[ROWID][1][positions] if parts[ROWID][0] in {'int', 'intnull'} else np.asarray(
            [int(value) for value in decode_objects(parts[ROWID], positions)], dtype=np.int64,
        )
        if source.table != current_table:
            groups.append([])
            current_table = source.table
        groups[-1].append((positions, rowids))
    total = sum(len(positions) for group in groups for positions, _rowids in group)
    arrays = [assemble_column(pieces) for pieces in per_column] if total else []
    if total and order == 'rowid':
        permutation = []
        offset = 0
        for group in groups:
            rowids = np.concatenate([item[1] for item in group]) if group else np.empty(0, dtype=np.int64)
            permutation.append(offset + np.argsort(rowids, kind='stable'))
            offset += len(rowids)
        permutation = np.concatenate(permutation)
        arrays = [array[permutation] for array in arrays]
    if weighted:
        first_rows, weights = weighted_rows(arrays, total)
        frame = frame_from_columns(names, [array[first_rows] for array in arrays], len(first_rows))
        frame[WEIGHT_COLUMN] = weights
        return frame
    return frame_from_columns(names, arrays, total)


# The column of a weighted frame (read_frame) with the number of rows each of its rows stands for.
WEIGHT_COLUMN = '__catalog_weight'


def _ordered_positions(segments: Sequence[Segment], selected: Sequence[tuple[np.ndarray, np.ndarray]],
                       order: str) -> list[np.ndarray]:
    """The place in the frame read_frame gives of each selected row of each CDR (``selected``: its positions, in the
    order read_frame takes them, and their combined row ids)."""
    places = []
    offset = 0
    for positions, _rowids in selected:
        places.append(np.arange(offset, offset + len(positions), dtype=np.int64))
        offset += len(positions)
    if order != 'rowid':
        return places
    # Table order across the CDRs of each combined table (see read_frame).
    start = 0
    current_table = None
    group: list[int] = []
    for index, segment in enumerate([*segments, None]):
        table = segment.source.table if segment is not None else None
        if group and table != current_table:
            rowids = np.concatenate([selected[item][1] for item in group])
            permutation = np.argsort(rowids, kind='stable')
            place = np.empty(len(rowids), dtype=np.int64)
            place[permutation] = np.arange(start, start + len(rowids), dtype=np.int64)
            cursor = 0
            for item in group:
                places[item] = place[cursor:cursor + len(selected[item][1])]
                cursor += len(selected[item][1])
            start += len(rowids)
            group = []
        current_table = table
        if segment is not None:
            group.append(index)
    return places


def read_grouped_frame(
    cache: ColumnCache,
    database_path: str | Path,
    segments: Sequence[Segment],
    columns: Sequence[tuple[str, str]],
    terms: SelectionTerms,
    order: str,
    builder: Callable[[Segment, list[str]], dict[str, tuple] | None],
    weighted: bool = True,
) -> pd.DataFrame | None:
    """The frame ``read_frame`` gives (``weighted``: its weighted frame), read by DuckDB from the columnar copies of the
    CDRs: the rows the universe selects (its predicates evaluated on the cached parts, as read_frame does), weighted
    grouped by the columns of each copy and the groups of the CDRs merged. None when a CDR has no copy that holds it as
    it is, or a column is no plain column of the combined table (read_frame then reads them)."""
    import duckdb
    from src.modules.column_names import column_identity

    names = [name for name, _expression in columns]
    bare = []
    for _name, expression in columns:
        inner = expression.strip()
        if not (inner.startswith('"') and inner.endswith('"')):
            return None
        bare.append(inner[1:-1].replace('""', '"'))
    if not segments:
        return None
    root = cdr_store.store_root(database_path)
    fresh = cdr_store.fresh_copies(database_path, [segment.dataset_id for segment in segments])
    if any(int(segment.dataset_id) not in fresh for segment in segments):
        return None
    database = f'file:{Path(str(database_path)).resolve()}?mode=ro'
    selected: list[tuple[np.ndarray, np.ndarray]] = []
    copy_rows: list[np.ndarray] = []
    with sqlite3.connect(database, uri=True, timeout=30) as connection:
        combined_columns: dict[str, set[str]] = {}
        for segment in segments:
            source = segment.source
            if source.table not in combined_columns:
                combined_columns[source.table] = {str(row[1]).casefold() for row in connection.execute(
                    f'PRAGMA table_info({quote_identifier(source.table)})')}
            if any(name.casefold() not in combined_columns[source.table] for name in bare):
                return None
            physical_terms = [source.physical(expression) for expression in terms.expressions()]
            parts = cache.built_parts(segment, physical_terms, builder)
            if parts is None:
                return None
            positions = np.flatnonzero(selection_mask(parts, source, terms, segment.dataset_id))
            if order == 'dataset_date_rowid' and len(positions):
                ranks = _date_ranks(parts[ORDER_DATE])[positions]
                positions = positions[np.argsort(ranks, kind='stable')]
            combined_rowids, source_rows = _row_map(connection, database_path, segment)
            if parts[ROWID][0] not in {'int', 'intnull'} or len(combined_rowids) != part_length(parts[ROWID]) \
                    or not np.array_equal(parts[ROWID][1], combined_rowids):
                return None
            selected.append((positions, combined_rowids[positions]))
            copy_rows.append(source_rows[positions])
    places = _ordered_positions(segments, selected, order)
    pieces: list[list[tuple[tuple, np.ndarray]]] = [[] for _ in names]
    weights, firsts = [], []
    duck = duckdb.connect()
    try:
        for segment, rows, place in zip(segments, copy_rows, places):
            if not len(rows):
                continue
            manifest = cdr_store.read_manifest(cdr_store.manifest_file(root, segment.source.kind, int(segment.dataset_id)))
            types = {**dict(manifest['columns']), cdr_store.ROWID: 'BIGINT', cdr_store.DATASET_ID: 'BIGINT',
                     cdr_store.NR_MODE: 'VARCHAR'}
            by_identity = {column_identity(column): column for column, _type in manifest['columns']}
            copy_columns = []
            for name in bare:
                identity = column_identity(name)
                copy_columns.append(cdr_store.DATASET_ID if identity == 'datasetid' else cdr_store.ROWID if identity == 'sourcerowid'
                                    else cdr_store.NR_MODE if identity == 'nrmode' and identity not in by_identity
                                    else by_identity.get(identity))
            present = list(dict.fromkeys(column for column in copy_columns if column))
            stored = cdr_store.stored_parts(present, types)
            duck.register('selected_rows', pd.DataFrame({'rowid': rows.astype(np.int64), 'place': place}))
            keys = ', '.join(f'p.{cdr_store.quote(column)}' for column in stored)
            files = cdr_store._sql_text(cdr_store.cdr_parts(root, segment.source.kind, int(segment.dataset_id)))
            if weighted:
                grouped = duck.execute(
                    f'SELECT {keys}{", " if keys else ""}COUNT(*) AS "__weight", MIN(s.place) AS "__first" '
                    f'FROM read_parquet({files}) p JOIN selected_rows s ON p.{cdr_store.quote(cdr_store.ROWID)} = s.rowid'
                    f'{" GROUP BY " + keys if keys else ""}').df()
            else:
                grouped = duck.execute(
                    f'SELECT {keys}{", " if keys else ""}1 AS "__weight", s.place AS "__first" '
                    f'FROM read_parquet({files}) p JOIN selected_rows s ON p.{cdr_store.quote(cdr_store.ROWID)} = s.rowid '
                    'ORDER BY s.place').df()
            duck.unregister('selected_rows')
            values = cdr_store.copy_values(grouped, present, types)
            length = len(grouped)
            identity_order = np.arange(length)
            for index, column in enumerate(copy_columns):
                pieces[index].append((_typed_part(values[column], identity_order) if column else ('none', length), identity_order))
            weights.append(grouped['__weight'].to_numpy(dtype=np.int64))
            firsts.append(grouped['__first'].to_numpy(dtype=np.int64))
    finally:
        duck.close()
    if not weights:
        frame = frame_from_columns(names, [], 0)
        if weighted:
            frame[WEIGHT_COLUMN] = np.empty(0, dtype=np.int64)
        return frame
    arrays = [assemble_column(column_pieces) for column_pieces in pieces]
    weight, first = np.concatenate(weights), np.concatenate(firsts)
    if not weighted:
        permutation = np.argsort(first, kind='stable')
        return frame_from_columns(names, [array[permutation] for array in arrays], len(permutation))
    # The same distinct row of several CDRs: one row, where it is first, with all its rows.
    key = np.zeros(len(weight), dtype=np.int64)
    for array in arrays:
        codes = _value_codes(array)
        key = pd.factorize(key * (int(codes.max()) + 1) + codes)[0]
    by_first = np.argsort(first, kind='stable')
    _distinct, at, group_of = np.unique(key[by_first], return_index=True, return_inverse=True)
    representatives = by_first[at]
    totals = np.bincount(group_of.reshape(-1), weights=weight[by_first], minlength=len(at)).astype(np.int64)
    shown = np.argsort(first[representatives], kind='stable')
    frame = frame_from_columns(names, [array[representatives[shown]] for array in arrays], len(shown))
    frame[WEIGHT_COLUMN] = totals[shown]
    return frame


def expand_weighted_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """The rows of a weighted frame (read_frame), each as many times as it stands for, without its weight."""
    weights = frame[WEIGHT_COLUMN].to_numpy(dtype=np.int64)
    expanded = frame.drop(columns=WEIGHT_COLUMN).take(np.repeat(np.arange(len(frame)), weights))
    expanded.index = pd.RangeIndex(len(expanded))
    return expanded


def _value_codes(array: np.ndarray) -> np.ndarray:
    """A code for each value of a column, the same for equal values only: reals by their bits (0.0 and -0.0, and each NaN
    apart), Python values by their type too (1 and 1.0 and True apart)."""
    if array.dtype.kind == 'f':
        return pd.factorize(np.ascontiguousarray(array, dtype=np.float64).view(np.int64))[0]
    if array.dtype.kind in 'iub':
        return pd.factorize(array)[0]
    if lib.infer_dtype(array, skipna=True) in {'string', 'empty'}:
        # Text hashed in C; each kind of missing value (None, NaN…) apart, by its type.
        codes = pd.factorize(array)[0]
        missing = np.flatnonzero(codes < 0)
        if len(missing):
            kinds: dict[type, int] = {}
            codes[missing] = [-1 - kinds.setdefault(type(value), len(kinds)) for value in array[missing]]
        return codes - int(codes.min())
    known: dict[tuple, int] = {}
    codes = np.empty(len(array), dtype=np.int64)
    for row, value in enumerate(array):
        key = (type(value), repr(value)) if isinstance(value, float) else (type(value), value)
        codes[row] = known.setdefault(key, len(known))
    return codes


def weighted_rows(arrays: Sequence[np.ndarray], length: int) -> tuple[np.ndarray, np.ndarray]:
    """The position of the first row of each distinct row of the columns ``arrays``, in their order, and how many rows
    each stands for."""
    if not length:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    key = np.zeros(length, dtype=np.int64)
    for array in arrays:
        codes = _value_codes(array)
        key = pd.factorize(key * (int(codes.max()) + 1) + codes)[0]
    _distinct, first_rows, inverse = np.unique(key, return_index=True, return_inverse=True)
    counts = np.bincount(inverse.reshape(-1), minlength=len(first_rows))
    order = np.argsort(first_rows, kind='stable')
    return first_rows[order], counts[order].astype(np.int64)


def selection_mask(parts: dict[str, tuple], source: CacheSource, terms: SelectionTerms,
                   dataset_id: int | None = None) -> np.ndarray:
    """Rows of one CDR segment (of ``dataset_id``) that satisfy the universe's predicates."""
    mask = np.ones(part_length(parts[ROWID]), dtype=bool)
    for expression, allowed in terms.values:
        if expression is None:
            mask[:] = False
        else:
            mask &= match_values(parts[source.physical(expression)], allowed)
    if terms.date:
        expression, low, high = terms.date
        if expression is None:
            mask[:] = False
        else:
            mask &= match_range(parts[source.physical(expression)], low, high)
    if terms.excluded_sheets:
        expression, excluded = terms.excluded_sheets
        mask &= keep_sheets(parts[source.physical(expression)], excluded)
    for expression, excluded in terms.excluded_values:
        mask &= keep_sheets(parts[source.physical(expression)], excluded)
    for datasets, expression, excluded in terms.dataset_excluded_values:
        if dataset_id in datasets:
            mask &= keep_sheets(parts[source.physical(expression)], excluded)
    return mask


def count_rows(
    cache: ColumnCache,
    connect: Callable[[], sqlite3.Connection],
    segments: Sequence[Segment],
    universe: SelectionTerms,
    selection: SelectionTerms,
    prefetch: Callable[[CacheSource], Iterable[str]] | None = None,
    builder: Callable[[Segment, list[str]], dict[str, tuple] | None] | None = None,
) -> tuple[int, int]:
    """Count the universe rows and those that also satisfy the selection (with ``builder``, from the columnar copies of
    the CDRs, as read_frame)."""
    universe_rows = selected_rows = 0
    for segment in segments:
        source = segment.source
        expressions = [source.physical(expression) for expression in (*universe.expressions(), *selection.expressions())]
        parts = cache.built_parts(segment, expressions, builder) if builder else None
        if parts is None:
            extra = [source.physical(expression) for expression in (prefetch(source) if prefetch else ())]
            parts = cache.segment_parts(connect, segment, expressions, extra)
        universe_mask = selection_mask(parts, source, universe, segment.dataset_id)
        universe_rows += int(universe_mask.sum())
        selected_rows += int((universe_mask & selection_mask(parts, source, selection, segment.dataset_id)).sum())
    return universe_rows, selected_rows


def default_memory_bytes() -> int:
    return int(os.environ.get('DRIVETEST_ANALYZER_COLUMN_CACHE_MEMORY_MB') or 1024) * 1024 ** 2


def default_disk_bytes() -> int:
    return int(os.environ.get('DRIVETEST_ANALYZER_COLUMN_CACHE_DISK_MB') or 8192) * 1024 ** 2


# ---------------------------------------------------------------------------
# Parts from the columnar copies of the CDRs


def _typed_part(raw: tuple[str, Any], order: np.ndarray) -> tuple:
    """The part ``encode_values`` makes of a column of SQLite values, from a column of a copy (see cdr_store._raw) in the
    rows of ``order``, without going through each value: reals, integers, or text as codes and categories."""
    tag, values = raw
    if tag == 'text':
        # Strings and None only: their codes and categories, as encode_values gives them.
        strings = np.asarray(values, dtype=object)[order]
        if not len(strings) or pd.isna(strings).all():
            return ('none', len(order))
        codes, categories = pd.factorize(strings)
        return ('str', codes.astype(np.int32), np.asarray(categories, dtype=object))
    if tag == 'real':
        array = np.asarray(values, dtype=np.float64)[order]
        missing = np.isnan(array)
        if missing.all():
            return ('none', len(order))
        if not missing.any():
            return ('float', array)
        # Reals with a missing value are kept as objects, as encode_values keeps them.
        objects = array.astype(object)
        objects[missing] = None
        return encode_values(objects)
    if tag == 'int':
        mask = values.isna().to_numpy()[order]
        if mask.all():
            return ('none', len(order))
        integers = values.fillna(0).astype('int64').to_numpy()[order]
        return ('intnull', integers, mask) if mask.any() else ('int', integers)
    return encode_values(np.asarray(values, dtype=object)[order])


# The combined row ids of the rows of each CDR and the CDR row each is, by workspace, combined table, CDR and data
# revision: the latest ones, kept in memory (a few MB each).
_ROW_MAPS: OrderedDict[tuple, tuple[np.ndarray, np.ndarray]] = OrderedDict()
_ROW_MAPS_GUARD = threading.Lock()
ROW_MAPS_KEPT = 64


def _row_map(connection: sqlite3.Connection, database_path: str | Path, segment: Segment) -> tuple[np.ndarray, np.ndarray]:
    """The combined row ids of the rows of one CDR in a combined table, in their order, and the CDR row each is."""
    source, dataset_id = segment.source, int(segment.dataset_id)
    key = (str(Path(str(database_path)).resolve()), source.table, dataset_id, segment.version)
    with _ROW_MAPS_GUARD:
        if key in _ROW_MAPS:
            _ROW_MAPS.move_to_end(key)
            return _ROW_MAPS[key]
    if source.kind in cdr_store.combined_shadows(connection):
        # An emptied combined table: the CDR row of each of its rows, in its order (see cdr_store).
        rows, keys = (f'FROM {cdr_store.COMBINED_ROWS_TABLE} WHERE kind = ? AND dataset_id = ?', (source.kind, dataset_id))
        combined_id, source_row = 'row_id', 'source_row_id'
    else:
        rows, keys = (f'FROM {quote_identifier(source.table)} WHERE "dataset_id" = ?', (dataset_id,))
        combined_id, source_row = 'rowid', '"source_row_id"'
    count, first, last, low, high, nulls = connection.execute(
        f'SELECT COUNT(*), MIN({combined_id}), MAX({combined_id}), MIN({combined_id} - {source_row}), '
        f'MAX({combined_id} - {source_row}), COUNT(*) - COUNT({source_row}) {rows}', keys).fetchone()
    if count and not nulls and last - first + 1 == count and low == high:
        # Its rows follow each other, each the CDR row a fixed distance before it (as a CDR is usually combined).
        combined_rowids = np.arange(first, last + 1, dtype=np.int64)
        found = (combined_rowids, combined_rowids - low)
    else:
        cursor = connection.execute(f'SELECT {combined_id}, {source_row} {rows} ORDER BY {combined_id}', keys)
        pairs = np.fromiter((value for row in cursor for value in row), dtype=np.int64).reshape(-1, 2)
        found = (pairs[:, 0].copy(), pairs[:, 1].copy())
    with _ROW_MAPS_GUARD:
        _ROW_MAPS[key] = found
        while len(_ROW_MAPS) > ROW_MAPS_KEPT:
            _ROW_MAPS.popitem(last=False)
    return found


def build_from_copies(database_path: str | Path, segment: Segment, expressions: Sequence[str]) -> dict[str, tuple] | None:
    """The parts ``ColumnCache._build`` reads from a combined table for one CDR, from the columnar copy of the CDR: the
    combined row ids of its rows, their event date and each expression. A bare column is read from the copy (the column
    of the CDR with the same identity). An expression of one column is evaluated by SQLite once for each value of the
    column, an expression of several columns on a table in memory with the columns it reads. None when the combined
    table and the copy do not hold the same rows, or an expression names no column of the combined table."""
    from src.modules.column_names import column_identity

    source = segment.source
    dataset_id = int(segment.dataset_id)
    database = f'file:{Path(str(database_path)).resolve()}?mode=ro'
    with sqlite3.connect(database, uri=True, timeout=30) as connection:
        try:
            combined_rowids, source_rows = _row_map(connection, database_path, segment)
        except (TypeError, ValueError):
            # A row without a CDR row (NULL source_row_id) is read from the combined table.
            return None
        combined = {str(row[1]).casefold() for row in connection.execute(f'PRAGMA table_info({quote_identifier(source.table)})')}
    manifest = cdr_store.read_manifest(cdr_store.manifest_file(cdr_store.store_root(database_path), source.kind, dataset_id))
    if manifest is None or len(combined_rowids) != int(manifest['rows']):
        return None
    by_identity = {column_identity(column): column for column, _type in manifest['columns']}

    def copy_column(name: str) -> str | None:
        """The column of the copy a combined column reads (its own values, or what the copy adds)."""
        identity = column_identity(name)
        if identity == 'datasetid':
            return cdr_store.DATASET_ID
        if identity == 'sourcerowid':
            return cdr_store.ROWID
        if identity == 'nrmode' and identity not in by_identity:
            return cdr_store.NR_MODE
        return by_identity.get(identity)

    def referenced(expression: str) -> list[str]:
        return list(dict.fromkeys(match.group(1).replace('""', '"') for match in _TOKEN_PATTERN.finditer(expression)
                                  if match.group(1) is not None))

    def bare(expression: str, name: str) -> bool:
        """Whether an expression is the column alone, maybe in parentheses (as the RF union projections give it)."""
        inner = expression.strip()
        while inner.startswith('(') and inner.endswith(')'):
            inner = inner[1:-1].strip()
        return inner == quote_identifier(name)

    order_date = ORDER_DATE_SQL if source.has_event_time else None
    wanted_expressions = list(dict.fromkeys([*expressions, *([order_date] if order_date else [])]))
    names = list(dict.fromkeys(name for expression in wanted_expressions for name in referenced(expression)))
    # A quoted name that is no column of the combined table is a string for SQLite: such an expression is read there.
    if any(name.casefold() not in combined for name in names):
        return None
    columns = {name: copy_column(name) for name in names}
    raw, _length = cdr_store._raw(database_path, source.kind, dataset_id,
                                  list(dict.fromkeys([cdr_store.ROWID, *(column for column in columns.values() if column)])))
    # The copy holds the rows of the CDR in row id order: the place of each CDR row of the combined rows.
    copy_rowids = np.asarray(raw[cdr_store.ROWID][1], dtype=np.int64)
    order = np.searchsorted(copy_rowids, source_rows)
    if len(order) and (order.max() >= len(copy_rowids) or not np.array_equal(copy_rowids[order], source_rows)):
        return None
    length = len(combined_rowids)
    missing = ('object', np.full(length, None, dtype=object))

    decoded: dict[str, np.ndarray] = {}

    def column_values(name: str) -> np.ndarray:
        """The Python values of a combined column for the rows of the CDR, in combined order."""
        if name not in decoded:
            column = columns[name]
            decoded[name] = cdr_store._python_values(raw[column])[order] if column else np.full(length, None, dtype=object)
        return decoded[name]

    distinct: dict[str, tuple[np.ndarray, list[Any]]] = {}

    def distinct_values(name: str) -> tuple[np.ndarray, list[Any]]:
        """The code of each row and the distinct values (with their Python types) of a combined column."""
        if name not in distinct:
            values = column_values(name)
            column = columns[name]
            if column is None or raw[column][0] in {'text', 'int'}:
                # One type (or None): the values themselves tell them apart.
                codes, uniques = pd.factorize(values, use_na_sentinel=False)
                uniques = [None if value is None or value != value else value for value in uniques]
            else:
                keys = np.fromiter(((type(value).__name__, value) for value in values), dtype=object, count=length)
                codes, unique_keys = pd.factorize(keys, use_na_sentinel=False)
                uniques = [key[1] for key in unique_keys]
            distinct[name] = (codes, uniques)
        return distinct[name]

    built = {ROWID: encode_values(combined_rowids.astype(object))}
    results: dict[str, tuple] = {}
    several: list[str] = []
    for expression in wanted_expressions:
        names_of = referenced(expression)
        if len(names_of) == 1 and bare(expression, names_of[0]):
            column = columns[names_of[0]]
            results[expression] = _typed_part(raw[column], order) if column else encode_values(missing[1])
        elif len(names_of) == 1:
            # SQLite evaluates the expression once for each distinct value (with its Python type) of the column.
            codes, uniques = distinct_values(names_of[0])
            memory = sqlite3.connect(':memory:')
            try:
                memory.execute(f'CREATE TABLE {quote_identifier(source.table)} ("__memory_rowid" INTEGER PRIMARY KEY, '
                               f'{quote_identifier(names_of[0])})')
                memory.executemany(f'INSERT INTO {quote_identifier(source.table)} VALUES (?, ?)', enumerate(uniques))
                evaluated = [row[0] for row in memory.execute(
                    f'SELECT {expression} FROM {quote_identifier(source.table)} ORDER BY "__memory_rowid"').fetchall()]
            finally:
                memory.close()
            results[expression] = encode_by_codes(evaluated, codes)
        else:
            several.append(expression)
    if several:
        several_names = list(dict.fromkeys(name for expression in several for name in referenced(expression)))
        memory = sqlite3.connect(':memory:')
        try:
            memory.execute(f'CREATE TABLE {quote_identifier(source.table)} ("__memory_rowid" INTEGER PRIMARY KEY'
                           + ''.join(f', {quote_identifier(name)}' for name in several_names) + ')')
            memory.executemany(f'INSERT INTO {quote_identifier(source.table)} VALUES ({", ".join("?" * (len(several_names) + 1))})',
                               zip(range(length), *(column_values(name) for name in several_names)))
            rows = memory.execute(f'SELECT {", ".join(several)} FROM {quote_identifier(source.table)} '
                                  'ORDER BY "__memory_rowid"').fetchall()
        finally:
            memory.close()
        content = lib.to_object_array_tuples(rows) if rows else np.empty((0, len(several)), dtype=object)
        for index, expression in enumerate(several):
            results[expression] = encode_values(np.ascontiguousarray(content[:, index]))
    built.update({expression: results[expression] for expression in expressions})
    built[ORDER_DATE] = results[order_date] if order_date else encode_values(np.full(length, None, dtype=object))
    return built
