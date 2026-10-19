"""Patterns among the values of a filter (the Operator filters and the Focus operators), resolved each time the filter is
used, so they also take the values that appear later:

- ``*`` stands for any characters, whatever the case: ``VF*`` takes VF, VF SA, VF VoNR…;
- a value that starts with ``-`` (or ``Not``) leaves out what it names: ``-Lebara`` is every value but Lebara, ``-Leb*``
  every value but those that start with Leb, and ``VF*`` with ``-VF SM`` every VF variant but VF SM.

A pattern is saved as such (and travels with its filter in exports, transfers and backups).
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Callable, Iterable

import pandas as pd

_EXCLUSION = re.compile(r'^\s*(?:-|not\s+)', re.IGNORECASE)


def is_exclusion(value: Any) -> bool:
    return bool(_EXCLUSION.match(str(value or ''))) and bool(excluded(value))


def excluded(value: Any) -> str:
    """What an exclusion (-Lebara, Not Lebara) leaves out."""
    return _EXCLUSION.sub('', str(value or '')).strip()


def is_pattern(value: Any) -> bool:
    """Whether a value of a filter is a pattern (with * or an exclusion) rather than a value compared as it is."""
    return '*' in str(value or '') or is_exclusion(value)


@lru_cache(maxsize=512)
def pattern_regex(value: str) -> re.Pattern:
    """A value or a pattern with * as a regular expression that matches a whole value, whatever its case."""
    return re.compile('.*'.join(re.escape(part) for part in str(value).strip().split('*')), re.IGNORECASE)


def _sql_like(value: str) -> str:
    escaped = str(value).strip().lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return escaped.replace('*', '%')


def sql_condition(column_text: str, values: Iterable[Any]) -> tuple[str, list[str]]:
    """The SQL condition that a lower-case text expression is one of some values, among which patterns (``LIKE`` with
    ``ESCAPE '\\'``) and exclusions; ``('1 = 1', [])`` without values."""
    texts = [str(value).strip() for value in values or [] if str(value or '').strip()]

    def any_of(items: list[str]) -> tuple[str, list[str]]:
        plain = [item.lower() for item in items if '*' not in item]
        likes = [_sql_like(item) for item in items if '*' in item]
        parts = [f"{column_text} IN ({', '.join('?' for _ in plain)})"] if plain else []
        parts.extend(f"{column_text} LIKE ? ESCAPE '\\'" for _ in likes)
        return (parts[0] if len(parts) == 1 else f"({' OR '.join(parts)})"), [*plain, *likes]

    included = [text for text in texts if not is_exclusion(text)]
    left_out = [excluded(text) for text in texts if is_exclusion(text)]
    clauses, params = [], []
    if included:
        clause, values_params = any_of(included)
        clauses.append(clause)
        params.extend(values_params)
    if left_out:
        clause, values_params = any_of(left_out)
        clauses.append(f"NOT COALESCE({clause}, 0)")
        params.extend(values_params)
    if not clauses:
        return '1 = 1', []
    return (clauses[0] if len(clauses) == 1 else f"({' AND '.join(clauses)})"), params


class ValueSet:
    """The values of a filter, compared trimmed and whatever their case, among which patterns: a value is in it when it
    is one of the values or matches one of the patterns (every value without them) and no exclusion leaves it out."""

    def __init__(self, values: Iterable[Any], normalize: Callable[[str], str] = str.casefold) -> None:
        texts = [str(value).strip() for value in values or [] if str(value or '').strip()]
        self.normalize = normalize
        included = [text for text in texts if not is_exclusion(text)]
        left_out = [excluded(text) for text in texts if is_exclusion(text)]
        self.values = {normalize(text) for text in included if '*' not in text}
        self.patterns = [pattern_regex(text) for text in included if '*' in text]
        self.excluded_values = {normalize(text) for text in left_out if '*' not in text}
        self.excluded_patterns = [pattern_regex(text) for text in left_out if '*' in text]

    def _included(self, text: str) -> bool:
        return self.normalize(text) in self.values or any(pattern.fullmatch(text) for pattern in self.patterns)

    def _excluded(self, text: str) -> bool:
        return self.normalize(text) in self.excluded_values or any(pattern.fullmatch(text) for pattern in self.excluded_patterns)

    @property
    def includes(self) -> bool:
        return bool(self.values or self.patterns)

    def __contains__(self, value: Any) -> bool:
        text = str(value if value is not None else '').strip()
        return (not self.includes or self._included(text)) and not self._excluded(text)

    def __bool__(self) -> bool:
        return bool(self.values or self.patterns or self.excluded_values or self.excluded_patterns)

    def __iter__(self):
        # The values chosen as such (patterns and exclusions are only matched).
        return iter(self.values)

    def accepts(self, names: Iterable[Any]) -> bool:
        """Whether a value known by several names (its label and the spellings of the CDRs) is taken: none of them is
        left out and, with values or patterns, one of them is among them."""
        texts = [str(name).strip() for name in names if name is not None and str(name).strip()]
        if any(self._excluded(text) for text in texts):
            return False
        return not self.includes or any(self._included(text) for text in texts)

    def intersects(self, candidates: Iterable[Any]) -> bool:
        return self.accepts(candidates)

    def excludes(self, names: Iterable[Any]) -> bool:
        """Whether an exclusion leaves out one of the names of a value."""
        return any(self._excluded(str(name).strip()) for name in names if name is not None and str(name).strip())

    def mask(self, series: pd.Series) -> pd.Series:
        """Which values of a column it takes."""
        text = series.astype('string').fillna('').str.strip()
        normalized = text.map(self.normalize)
        mask = pd.Series(not self.includes, index=series.index)
        if self.includes:
            mask = normalized.isin(self.values)
            for pattern in self.patterns:
                mask |= text.str.fullmatch(pattern.pattern, flags=re.IGNORECASE, na=False)
        left_out = normalized.isin(self.excluded_values)
        for pattern in self.excluded_patterns:
            left_out |= text.str.fullmatch(pattern.pattern, flags=re.IGNORECASE, na=False)
        return (mask & ~left_out).astype(bool)


def expand(values: Iterable[Any], available: Iterable[Any]) -> list[str]:
    """The values of a filter with its patterns replaced by the available values they take (an exclusion by every
    available value it does not leave out); a pattern that takes none is kept, so the filter still takes no value
    instead of every value."""
    choices = [str(value).strip() for value in available or [] if str(value or '').strip()]
    texts = [str(value).strip() for value in values or [] if str(value or '').strip()]
    if not any(is_pattern(text) for text in texts):
        return list(dict.fromkeys(texts))
    chosen = ValueSet(texts)
    taken = [choice for choice in choices if choice in chosen]
    return list(dict.fromkeys(taken or [text for text in texts if is_pattern(text)]))
