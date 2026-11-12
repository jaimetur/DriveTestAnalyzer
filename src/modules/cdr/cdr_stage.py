"""Final, Weekly and Daily CDRs, and the CDRs that the combined CDR tables include.

A **Final** CDR is the consolidated file delivered after a measurement campaign;
**Weekly** and **Daily** CDRs arrive while the campaign runs, either incremental
(the calls of one week or day) or cumulative (every call so far). Every CDR has a
stage, suggested from its file name and chosen on upload.

The combined CDR tables (and the modules that read them) include each ready CDR
according to its ``in_combined`` choice:

* ``yes`` / ``no``: chosen by the user;
* ``auto``: Final CDRs are included; a Weekly or Daily CDR is included until an
  included Final CDR of the same type and NR Mode shares one of its campaigns or
  covers all its dates (its first and last call dates are within those of the Final
  CDR), until a newer Weekly or Daily CDR of the same type contains every one of its
  calls (a cumulative CDR replaces the previous ones), or, for a Daily CDR, until a
  Weekly CDR covers all its dates. A Flex CDR (a local campaign) never replaces a CDR
  that is not Flex, nor the other way round. A CDR whose dates only partly overlap
  those of an included Final CDR stays included, with the overlapping days in its
  reason.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from src.modules.cdr.column_names import column_identity

CDR_STAGES = ('final', 'weekly', 'daily')
CDR_STAGE_LABELS = {'final': 'Final', 'weekly': 'Weekly', 'daily': 'Daily'}
DEFAULT_CDR_STAGE = 'final'
CDR_STAGE_KINDS = frozenset({'data', 'voice', 'speech'})
IN_COMBINED_VALUES = ('auto', 'yes', 'no')
IN_COMBINED_LABELS = {'auto': 'Auto', 'yes': 'Yes', 'no': 'No'}

_FINAL_WORD = re.compile(r'(?<![a-z])final(?![a-z])')
_WEEKLY_WORDS = re.compile(r'(?<![a-z])(weekly|week|semanal|semana|wk)(?![a-z])')
_DAILY_WORDS = re.compile(r'(?<![a-z])(daily|diario|diaria|dia|day|incremental|cumulative|acumulado)(?![a-z])')
# yyyymmdd, yyyy-mm-dd, yyyy_mm_dd or yyyy.mm.dd.
_DATE = re.compile(r'(?<!\d)(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)')
_STATE_KEY = 'cdr_stage_facts'
_CONTAINMENT_KEY = 'cdr_daily_containment'
_START_COLUMNS = ('event_start_time', 'Call_Start_Time', 'Test_Start_Time')


def normalize_cdr_stage(value: object) -> str | None:
    """``final``, ``weekly`` or ``daily`` for a supported value (any case), otherwise ``None``."""
    text = str(value or '').strip().casefold()
    return text if text in CDR_STAGES else None


def normalize_in_combined(value: object) -> str | None:
    """``auto``, ``yes`` or ``no`` for a supported value (any case), otherwise ``None``."""
    text = str(value or '').strip().casefold()
    return text if text in IN_COMBINED_VALUES else None


def infer_cdr_stage(file_name: object) -> str:
    """Suggest whether a CDR is Final, Weekly or Daily from its file name.

    * ``final`` in the name → Final;
    * ``weekly``, ``week``, ``semanal``, ``semana``, ``wk`` → Weekly;
    * ``daily``, ``diario``, ``day``, ``incremental``, ``cumulative``… → Daily;
    * a date range (two different dates, for example ``20250903-20251011``) → Final;
    * a single date that is not the export stamp at the start of the name
      (``UK_Voice_CDR_20260921``) → Daily;
    * anything else → Final.
    """
    stem = Path(str(file_name or '')).stem
    spaced = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', stem).casefold()
    words = re.sub(r'[^a-z0-9]+', ' ', spaced)
    if _FINAL_WORD.search(words):
        return 'final'
    if _WEEKLY_WORDS.search(words):
        return 'weekly'
    if _DAILY_WORDS.search(words):
        return 'daily'
    dates = [(match.start(), ''.join(match.groups())) for match in _DATE.finditer(stem)]
    distinct = {value for _start, value in dates}
    if len(distinct) >= 2:
        return 'final'
    if len(distinct) == 1 and any(start > 0 for start, _value in dates):
        return 'daily'
    return DEFAULT_CDR_STAGE


def dataset_cdr_stage(dataset_kind: object, stage: object, file_name: object = '') -> str | None:
    """The stage of a dataset, or ``None`` for files that are not CDRs."""
    if str(dataset_kind or '').casefold() not in CDR_STAGE_KINDS:
        return None
    return normalize_cdr_stage(stage) or infer_cdr_stage(file_name)


def _row(dataset: Any, key: str, default: Any = None) -> Any:
    try:
        value = dataset[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def _revision(dataset: Any) -> str:
    return '|'.join(str(_row(dataset, key, '')) for key in ('updated_at', 'processed_at', 'row_count'))


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _table_columns(connection: Any, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info({_quote(table)})').fetchall()]


def _resolve(columns: list[str], *candidates: str) -> str | None:
    lookup = {column_identity(column): column for column in columns}
    return next((lookup[column_identity(candidate)] for candidate in candidates if column_identity(candidate) in lookup), None)


def _facts(repository: Any, datasets: list[Any]) -> dict[int, dict[str, Any]]:
    """The campaigns and the newest call date of every CDR, cached until it changes."""
    try:
        cached = json.loads(repository.get_workspace_state(_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        cached = {}
    cached = cached if isinstance(cached, dict) else {}
    facts: dict[int, dict[str, Any]] = {}
    changed = False
    with repository.connection() as connection:
        has_catalogues = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cdr_catalogues'").fetchone() is not None
        for dataset in datasets:
            dataset_id = int(dataset['id'])
            entry = cached.get(str(dataset_id))
            # Entries cached before the first call date was kept are read again.
            if isinstance(entry, dict) and entry.get('revision') == _revision(dataset) and 'first_date' in entry:
                facts[dataset_id] = entry
                continue
            table = f'dataset_rows_{dataset_id}'
            columns = _table_columns(connection, table)
            campaigns: list[str] = []
            row = connection.execute('SELECT campaigns_json FROM cdr_catalogues WHERE dataset_id = ?',
                                     (dataset_id,)).fetchone() if has_catalogues else None
            if row is not None and row['campaigns_json']:
                try:
                    campaigns = [str(value).strip() for value in json.loads(row['campaigns_json']) if str(value).strip()]
                except (TypeError, ValueError):
                    campaigns = []
            campaign_column = _resolve(columns, 'Campaign')
            if not campaigns and campaign_column:
                campaigns = [str(value[0]).strip() for value in connection.execute(
                    f'SELECT DISTINCT {_quote(campaign_column)} FROM {_quote(table)} '
                    f'WHERE TRIM(COALESCE({_quote(campaign_column)}, \'\')) <> \'\' LIMIT 1000').fetchall()]
            start_column = _resolve(columns, *_START_COLUMNS)
            data_date = first_date = ''
            if start_column:
                start = f"replace(substr(CAST({_quote(start_column)} AS TEXT), 1, 19), 'T', ' ')"
                first, last = connection.execute(
                    f"SELECT MIN(NULLIF({start}, '')), MAX({start}) FROM {_quote(table)}"
                ).fetchone()
                data_date, first_date = str(last or ''), str(first or '')
            entry = {'revision': _revision(dataset), 'campaigns': sorted(set(campaigns), key=str.casefold),
                     'data_date': data_date, 'first_date': first_date, 'has_join_id': bool(_resolve(columns, 'JOIN_ID'))}
            facts[dataset_id] = entry
            cached[str(dataset_id)] = entry
            changed = True
    known = {str(int(dataset['id'])) for dataset in datasets}
    if changed or set(cached) - known:
        repository.set_workspace_state(_STATE_KEY, json.dumps({key: value for key, value in cached.items() if key in known}))
    return facts


def cdr_data_dates(repository: Any) -> dict[int, str]:
    """The newest call date of every ready CDR (its "data date")."""
    datasets = [dataset for dataset in repository.list_datasets()
                if str(_row(dataset, 'status', '')) == 'ready' and str(_row(dataset, 'dataset_kind', '')).casefold() in CDR_STAGE_KINDS]
    return {dataset_id: str(entry.get('data_date') or '') for dataset_id, entry in _facts(repository, datasets).items()}


def _join_ids(connection: Any, dataset_id: int) -> set[str] | None:
    table = f'dataset_rows_{dataset_id}'
    column = _resolve(_table_columns(connection, table), 'JOIN_ID')
    if not column:
        return None
    return {str(row[0]).strip().casefold() for row in connection.execute(
        f'SELECT DISTINCT {_quote(column)} FROM {_quote(table)} WHERE TRIM(COALESCE({_quote(column)}, \'\')) <> \'\'')}


def _contained(repository: Any, older: Any, newer: Any, memo: dict[int, set[str] | None]) -> bool:
    """Whether every call (JOIN_ID) of an older Weekly or Daily CDR is in a newer one, cached per revision pair."""
    key = f"{int(older['id'])}:{int(newer['id'])}"
    signature = f'{_revision(older)}#{_revision(newer)}'
    try:
        cached = json.loads(repository.get_workspace_state(_CONTAINMENT_KEY) or '{}')
    except (TypeError, ValueError):
        cached = {}
    cached = cached if isinstance(cached, dict) else {}
    entry = cached.get(key)
    if isinstance(entry, dict) and entry.get('signature') == signature:
        return bool(entry.get('contained'))
    with repository.connection() as connection:
        for dataset_id in (int(older['id']), int(newer['id'])):
            if dataset_id not in memo:
                memo[dataset_id] = _join_ids(connection, dataset_id)
    older_ids, newer_ids = memo[int(older['id'])], memo[int(newer['id'])]
    contained = bool(older_ids) and newer_ids is not None and older_ids <= newer_ids
    cached[key] = {'signature': signature, 'contained': contained}
    repository.set_workspace_state(_CONTAINMENT_KEY, json.dumps(cached))
    return contained


# Within a block of remembered_inclusion (one request that resolves the CDRs of a Design several times), the inclusion of
# each workspace is worked out once.
_REMEMBERED_INCLUSION: ContextVar[dict[str, dict[int, dict[str, Any]]] | None] = ContextVar('remembered_inclusion', default=None)


@contextmanager
def remembered_inclusion() -> Iterator[None]:
    """Work out combined_inclusion once per workspace in the block (nested blocks share the outer one)."""
    if _REMEMBERED_INCLUSION.get() is not None:
        yield
        return
    token = _REMEMBERED_INCLUSION.set({})
    try:
        yield
    finally:
        _REMEMBERED_INCLUSION.reset(token)


def combined_inclusion(repository: Any) -> dict[int, dict[str, Any]]:
    """For every ready CDR: its stage, its combined mode and whether the combined tables include it, with the reason."""
    remembered = _REMEMBERED_INCLUSION.get()
    if remembered is None:
        return _combined_inclusion(repository)
    key = str(getattr(repository, 'db_path', ''))
    if key not in remembered:
        remembered[key] = _combined_inclusion(repository)
    return remembered[key]


_DAY = re.compile(r'\d{4}-\d{2}-\d{2}')


def _day(value: object) -> str:
    """The date (yyyy-mm-dd) of a call date, or '' when it has none."""
    text = str(value or '')[:10]
    return text if _DAY.fullmatch(text) else ''


def _date_range(item: dict[str, Any]) -> tuple[str, str] | None:
    first, last = _day(item.get('first_date')), _day(item.get('data_date'))
    return (first, last) if first and last and first <= last else None


def _covers(outer: dict[str, Any], inner: dict[str, Any]) -> bool:
    """Whether the dates of a CDR are all within those of another one (both with dates)."""
    outer_range, inner_range = _date_range(outer), _date_range(inner)
    return bool(outer_range and inner_range and outer_range[0] <= inner_range[0] and inner_range[1] <= outer_range[1])


def _overlap_days(first: dict[str, Any], second: dict[str, Any]) -> int:
    """How many days the dates of two CDRs share."""
    first_range, second_range = _date_range(first), _date_range(second)
    if not first_range or not second_range:
        return 0
    start, end = max(first_range[0], second_range[0]), min(first_range[1], second_range[1])
    if start > end:
        return 0
    return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1


def _short_range(item: dict[str, Any]) -> str:
    first, last = _date_range(item) or ('', '')
    return f'{first} to {last}' if first != last else first


def _combined_inclusion(repository: Any) -> dict[int, dict[str, Any]]:
    from src.modules.cdr.cdr_auto_selection import is_flex_cdr

    datasets = [dataset for dataset in repository.list_datasets()
                if str(_row(dataset, 'status', '')) == 'ready' and str(_row(dataset, 'dataset_kind', '')).casefold() in CDR_STAGE_KINDS]
    facts = _facts(repository, datasets)
    names = {int(dataset['id']): str(dataset['file_name']) for dataset in datasets}
    info: dict[int, dict[str, Any]] = {}
    for dataset in datasets:
        dataset_id = int(dataset['id'])
        stage = dataset_cdr_stage(dataset['dataset_kind'], _row(dataset, 'cdr_stage'), dataset['file_name']) or DEFAULT_CDR_STAGE
        choice = normalize_in_combined(_row(dataset, 'in_combined')) or 'auto'
        info[dataset_id] = {'stage': stage, 'in_combined': choice, 'kind': str(dataset['dataset_kind']).casefold(),
                            'nr_mode': str(_row(dataset, 'nr_mode', '') or '').upper(),
                            'campaigns': {campaign.casefold() for campaign in facts[dataset_id]['campaigns']},
                            'data_date': facts[dataset_id]['data_date'], 'first_date': facts[dataset_id].get('first_date') or '',
                            'flex': is_flex_cdr(facts[dataset_id]['campaigns'], _row(dataset, 'campaign', ''))}

    def manual(item: dict[str, Any]) -> bool | None:
        return {'yes': True, 'no': False}.get(item['in_combined'])

    def same_cdrs(item: dict[str, Any], other: dict[str, Any]) -> bool:
        """Whether one CDR can replace another: same type, NR Mode (or one without it) and Flex or not."""
        return (other['kind'] == item['kind'] and other['flex'] == item['flex']
                and (not item['nr_mode'] or not other['nr_mode'] or other['nr_mode'] == item['nr_mode']))

    finals = [dataset_id for dataset_id, item in info.items()
              if item['stage'] == 'final' and manual(item) is not False]
    by_id = {int(dataset['id']): dataset for dataset in datasets}
    for dataset_id, item in info.items():
        chosen = manual(item)
        if chosen is not None:
            item.update(included=chosen, reason='Included manually' if chosen else 'Excluded manually')
            continue
        if item['stage'] == 'final':
            item.update(included=True, reason='Final CDRs are always included')
            continue
        replacing = next((final_id for final_id in finals
                          if same_cdrs(item, info[final_id]) and item['campaigns'] & info[final_id]['campaigns']), None)
        if replacing is not None:
            item.update(included=False, reason=f'Replaced by the Final CDR {names[replacing]}', replaced_by=replacing)
            continue
        covering = next((final_id for final_id in finals if same_cdrs(item, info[final_id]) and _covers(info[final_id], item)), None)
        if covering is not None:
            item.update(included=False, replaced_by=covering,
                        reason=f'Its dates ({_short_range(item)}) are covered by the Final CDR {names[covering]}')
            continue
        item.update(included=True, reason='No Final CDR of its campaign yet')
    # A cumulative Weekly or Daily CDR contains every call of the previous ones of its campaign: only the newest stays.
    memo: dict[int, set[str] | None] = {}
    for dataset_id, item in info.items():
        if not item.get('included') or item['stage'] == 'final' or item['in_combined'] != 'auto':
            continue
        newer = sorted((other_id for other_id, other in info.items()
                        if other_id != dataset_id and other['stage'] != 'final' and other.get('included')
                        and other['kind'] == item['kind'] and other['nr_mode'] == item['nr_mode']
                        and (other['data_date'], other_id) > (item['data_date'], dataset_id)
                        and (not item['campaigns'] or item['campaigns'] & other['campaigns'])),
                       key=lambda other_id: (info[other_id]['data_date'], other_id), reverse=True)
        # The newest CDR (a cumulative one has every call so far) and every newer Weekly CDR (which holds
        # the calls of its week even when newer incremental Daily CDRs follow it).
        candidates = list(dict.fromkeys([*newer[:1], *(other_id for other_id in newer if info[other_id]['stage'] == 'weekly')]))
        container = next((other_id for other_id in candidates if _contained(repository, by_id[dataset_id], by_id[other_id], memo)), None)
        if container is not None:
            label = CDR_STAGE_LABELS[info[container]['stage']]
            item.update(included=False, reason=f'Every call is in the newer {label} CDR {names[container]}', replaced_by=container)
    # A Daily CDR whose dates a Weekly CDR covers (not one excluded by hand) holds no call the Weekly CDR has not.
    weeklies = [dataset_id for dataset_id, item in info.items() if item['stage'] == 'weekly' and manual(item) is not False]
    for dataset_id, item in info.items():
        if not item.get('included') or item['stage'] != 'daily' or item['in_combined'] != 'auto':
            continue
        covering = next((weekly_id for weekly_id in weeklies
                         if same_cdrs(item, info[weekly_id]) and _covers(info[weekly_id], item)), None)
        if covering is not None:
            item.update(included=False, replaced_by=covering,
                        reason=f'Its dates ({_short_range(item)}) are covered by the Weekly CDR {names[covering]}')
    # A Weekly or Daily CDR that stays with some days of an included Final CDR counts the calls of those days twice.
    included_finals = [dataset_id for dataset_id, item in info.items() if item['stage'] == 'final' and item.get('included')]
    for dataset_id, item in info.items():
        if not item.get('included') or item['stage'] == 'final':
            continue
        shared = max(((_overlap_days(item, info[final_id]), final_id) for final_id in included_finals
                      if same_cdrs(item, info[final_id])), default=(0, None))
        if shared[0]:
            days = 'day' if shared[0] == 1 else 'days'
            item.update(overlap_days=shared[0], overlaps=shared[1],
                        reason=f"{item['reason']}; {shared[0]} {days} of its dates are also in the Final CDR {names[shared[1]]}")
    for item in info.values():
        item['campaigns'] = sorted(item['campaigns'])
    return info


def combined_dataset_ids(repository: Any, kind: str | None = None) -> set[int]:
    """The ready CDRs (of one type, or of every type) that the combined tables include."""
    return {dataset_id for dataset_id, item in combined_inclusion(repository).items()
            if item['included'] and (kind is None or item['kind'] == kind)}
