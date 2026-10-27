"""The part each Operator label of the Operator Maps plays in the whole workspace:

- **Focus**: the Focus operators of the Scoring exports (the operators of Where to act, the individual GAP comparisons,
  the Points Lost views… of the PowerPoint and Word), with every name of the CDRs the label stands for;
- **Exclude**: left out of every analysis, filter, chart and report, as if every Operator filter left it out
  (``-Lebara``), with every name of the CDRs it stands for.

A label with neither (**Include**, the default) is analysed as usual.

Its **NR Modes** are those the operator has a network in (both by default): the rows of its CDRs of another NR Mode
(the SA CDRs of Three, which has no SA, whose tests run on LTE and EN-DC) are out of scope and left out of every analysis,
filter, chart and report, NQ Calls included.
"""
from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

FOCUS = 'focus'
EXCLUDE = 'exclude'
MAPPING_ROLES = (FOCUS, EXCLUDE)
NR_MODES = ('NSA', 'SA')


def normalize_mapping_role(value: Any) -> str:
    """``focus``, ``exclude`` or '' (no part) from a stored or submitted value."""
    text = str(value or '').strip().casefold()
    return text if text in MAPPING_ROLES else ''


def normalize_nr_modes(value: Any) -> list[str]:
    """The NR Modes in scope of a label, from a stored ('NSA'), submitted or listed value: [] for every NR Mode (the
    default, also for none or both), else the one it has."""
    items = value.replace(';', ',').split(',') if isinstance(value, str) else value if isinstance(value, (list, tuple, set)) else []
    chosen = {str(item or '').strip().upper() for item in items}
    modes = [mode for mode in NR_MODES if mode in chosen]
    return [] if len(modes) in {0, len(NR_MODES)} else modes


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


def out_of_scope_pairs(settings_or_groups: Any) -> list[dict[str, str]]:
    """The NR Mode and Operator label pairs out of scope (SA · Three): each NR Mode a label has no network in, in the
    order of the Operator Maps (the labels with the Role Exclude are left out in every NR Mode anyway)."""
    pairs = []
    for group in _groups_of(settings_or_groups):
        canonical = str(group.get('canonical') or '').strip()
        modes = normalize_nr_modes(group.get('nr_modes'))
        if canonical and modes and normalize_mapping_role(group.get('role')) != EXCLUDE:
            pairs += [{'nr_mode': mode, 'operator': canonical} for mode in NR_MODES if mode not in modes]
    return pairs


def out_of_scope_operators(settings_or_groups: Any, nr_mode: Any) -> list[str]:
    """The operators out of scope in an NR Mode: the labels without a network in it and every name of the CDRs each one
    stands for (none for a CDR without an NR Mode)."""
    mode = str(nr_mode or '').strip().upper()
    names: dict[str, str] = {}
    for group in _groups_of(settings_or_groups):
        modes = normalize_nr_modes(group.get('nr_modes'))
        if mode not in NR_MODES or not modes or mode in modes or normalize_mapping_role(group.get('role')) == EXCLUDE:
            continue
        aliases = group.get('aliases') if isinstance(group.get('aliases'), (list, tuple)) else []
        for name in [group.get('canonical'), *aliases]:
            text = str(name or '').strip()
            if text:
                names.setdefault(text.casefold(), text)
    return list(names.values())


def drop_out_of_scope_operators(frame: pd.DataFrame, settings_or_groups: Any, nr_mode: Any,
                                columns: Iterable[str] | None = None) -> pd.DataFrame:
    """The rows of a frame of the CDRs of one NR Mode without those of the operators out of scope in it (see
    ``drop_excluded_operators`` for ``columns``)."""
    return drop_excluded_operators(frame, out_of_scope_operators(settings_or_groups, nr_mode), columns)


def out_of_scope_sql(settings_or_groups: Any, nr_modes: dict[int, Any], operator_sql: str,
                     dataset_sql: str | None = None) -> tuple[str, list[Any]]:
    """An SQL condition that leaves out the rows of the operators out of scope in the NR Mode of their CDR ('1' when none
    is): ``operator_sql`` is the Operator expression and ``nr_modes`` the NR Mode of each CDR read. ``dataset_sql`` is the
    CDR id column of a table with the rows of several CDRs; without it the rows are those of the only CDR of
    ``nr_modes``."""
    expression = f"LOWER(TRIM(CAST(COALESCE({operator_sql}, '') AS TEXT)))"
    clauses: list[str] = []
    params: list[Any] = []
    for mode in NR_MODES:
        names = sorted({name.casefold() for name in out_of_scope_operators(settings_or_groups, mode)})
        dataset_ids = sorted(int(dataset_id) for dataset_id, value in nr_modes.items() if str(value or '').upper() == mode)
        if not names or not dataset_ids:
            continue
        condition = f"{expression} IN ({', '.join('?' for _ in names)})"
        if dataset_sql is None:
            clauses.append(f'NOT ({condition})')
            params += names
        else:
            clauses.append(f"NOT ({dataset_sql} IN ({', '.join('?' for _ in dataset_ids)}) AND {condition})")
            params += [*dataset_ids, *names]
    return (' AND '.join(clauses) or '1'), params


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
