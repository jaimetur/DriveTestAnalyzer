"""The part each Operator label of the Operator Maps plays in the whole workspace:

- **Focus**: the Focus operators of the Scoring exports (the operators of Where to act, the individual GAP comparisons,
  the Points Lost views… of the PowerPoint and Word), with every name of the CDRs the label stands for;
- **Exclude**: left out of every analysis, filter, chart and report, as if every Operator filter left it out
  (``-Lebara``), with every name of the CDRs it stands for.

A label with neither (**Include**, the default) is analysed as usual.
"""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

FOCUS = 'focus'
EXCLUDE = 'exclude'
MAPPING_ROLES = (FOCUS, EXCLUDE)


def normalize_mapping_role(value: Any) -> str:
    """``focus``, ``exclude`` or '' (no part) from a stored or submitted value."""
    text = str(value or '').strip().casefold()
    return text if text in MAPPING_ROLES else ''


def _groups_of(settings_or_groups: Any) -> list[dict[str, Any]]:
    """The Operator label groups of chart mapping settings, of a repository or given as such."""
    if isinstance(settings_or_groups, dict):
        groups = settings_or_groups.get('operator_mapping_groups')
    elif isinstance(settings_or_groups, (list, tuple)):
        groups = settings_or_groups
    else:
        getter = getattr(settings_or_groups, 'list_operator_mapping_groups', None)
        try:
            groups = getter() if callable(getter) else []
        except Exception:  # A repository without Operator Maps (or its workspace closed) gives no part to any operator.
            groups = []
    return [group for group in groups or [] if isinstance(group, dict)]


def labels_with_role(settings_or_groups: Any, role: str) -> list[str]:
    """The Operator labels with a part, in the order of the Operator Maps."""
    return [str(group.get('canonical') or '').strip() for group in _groups_of(settings_or_groups)
            if normalize_mapping_role(group.get('role')) == role and str(group.get('canonical') or '').strip()]


def names_with_role(settings_or_groups: Any, role: str) -> list[str]:
    """The Operator labels with a part and every name of the CDRs each one stands for."""
    names: dict[str, str] = {}
    for group in _groups_of(settings_or_groups):
        if normalize_mapping_role(group.get('role')) != role:
            continue
        aliases = group.get('aliases') if isinstance(group.get('aliases'), (list, tuple)) else []
        for name in [group.get('canonical'), *aliases]:
            text = str(name or '').strip()
            if text:
                names.setdefault(text.casefold(), text)
    return list(names.values())


def focus_operators(settings_or_groups: Any) -> list[str]:
    """The Focus operators of the workspace: their labels and the names of the CDRs they stand for."""
    return names_with_role(settings_or_groups, FOCUS)


def excluded_operators(settings_or_groups: Any) -> list[str]:
    """The operators left out of every analysis: their labels and the names of the CDRs they stand for."""
    return names_with_role(settings_or_groups, EXCLUDE)


def with_exclusions(values: Iterable[Any] | None, settings_or_groups: Any) -> list[str]:
    """An Operator filter that also leaves out the excluded operators (``-Lebara``; see value_patterns): All (no
    values) becomes every operator but them."""
    chosen = [str(value).strip() for value in values or [] if str(value or '').strip()]
    present = {value.casefold() for value in chosen}
    return chosen + [f'-{name}' for name in excluded_operators(settings_or_groups) if f'-{name}'.casefold() not in present]


def is_excluded(value: Any, excluded: Iterable[str]) -> bool:
    return str(value if value is not None else '').strip().casefold() in {str(name).strip().casefold() for name in excluded}


def drop_excluded_operators(frame: pd.DataFrame, excluded: Iterable[str], columns: Iterable[str] | None = None) -> pd.DataFrame:
    """The rows of a frame whose Operator is none of the excluded operators (names compared trimmed, whatever their
    case); ``columns`` are the Operator columns (every Operator column, whatever its spelling, without them)."""
    from src.modules.column_names import column_identity

    names = {str(name).strip().casefold() for name in excluded or [] if str(name or '').strip()}
    if not names or frame is None or frame.empty:
        return frame
    targets = [column for column in (columns if columns is not None else frame.columns)
               if column in frame.columns and (columns is not None or column_identity(column) == 'operator')]
    if not targets:
        return frame
    keep = pd.Series(True, index=frame.index)
    for column in targets:
        keep &= ~frame[column].astype('string').fillna('').str.strip().str.casefold().isin(names)
    return frame if bool(keep.all()) else frame[keep]
