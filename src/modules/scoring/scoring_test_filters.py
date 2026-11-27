"""The Test, Test Name and Test Type filters of Scoring & GAP Analysis (ticket #207).

They leave tests out of a scoring (or keep only some) without changing the CDRs, as the other Context Filters do:

- **Test** is the Test Type and the Test Name of each test joined (``VideoStreaming › TikTok``), so a name of two tests of
  different types (TikTok in VideoStreaming, tiktok in httpBrowser) is left out of one of them only; the calls and speech
  samples by their Test Type alone (``MultiRAB CALL``);
- **Test Name** (``Test_Name``) names the Data tests only: the Voice and Speech CDRs keep it for the data session of a
  MultiRAB call, so it does not filter them (they are scored as they are, whatever the filter);
- **Test Type** (``Type_of_Test``, else ``Session_Type``, which holds the same values) is the type of every test:
  httpBrowser, httpTransfer, ICMP Ping… of the Data tests and CALL, MultiRAB CALL, WhatsApp CALL of the calls and speech
  samples.

They are not aggregation levels, they do not narrow the lists of the other filters (nor these the lists of them), and a
Saved Scoring keeps them only when used. Their values come from the CDRs of the NR Mode, read once from each columnar copy.
"""
from __future__ import annotations

from typing import Any, Iterable

TEST_FILTERS = {
    # The columns each one is read from: the first the CDR has (Test: its Test Type, then joined to the name of the Data
    # tests).
    'Test': {'columns': ('Type_of_Test', 'Session_Type'), 'name_columns': ('Test_Name',), 'name_kinds': ('data',),
             'kinds': ('data', 'voice', 'speech'), 'label': 'Test'},
    'Test_Name': {'columns': ('Test_Name',), 'kinds': ('data',), 'label': 'Test Name'},
    'Test_Type': {'columns': ('Type_of_Test', 'Session_Type'), 'kinds': ('data', 'voice', 'speech'), 'label': 'Test Type'},
}
TEST_FILTER_FIELDS = tuple(TEST_FILTERS)


def filters_kind(field: str, kind: str) -> bool:
    """Whether a test filter applies to the CDRs of ``kind`` (any other filter applies to every CDR)."""
    spec = TEST_FILTERS.get(field)
    return spec is None or str(kind).casefold() in spec['kinds']


def _first_column(repository: Any, dataset_id: int, candidates: Iterable[str]) -> str | None:
    return next((resolved for candidate in candidates
                 if (resolved := repository.resolve_dataset_row_column_name(dataset_id, candidate)) is not None), None)


def row_filter(repository: Any, dataset_id: int, kind: str, field: str) -> str | None:
    """The key a test filter takes among the filters of the rows of a CDR (see Repository.dataset_rows_plan): its column,
    or for Test the columns it joins; None when the CDR has no such column."""
    from src.modules.cdr.value_patterns import COMBINED_FILTER_PREFIX

    spec = TEST_FILTERS[field]
    column = _first_column(repository, dataset_id, spec['columns'])
    if column is None or field != 'Test':
        return column
    name = _first_column(repository, dataset_id, spec['name_columns']) if str(kind).casefold() in spec['name_kinds'] else None
    return COMBINED_FILTER_PREFIX + '|'.join(item for item in (column, name) if item)


def scoring_test_filter_options(repository: Any, cdrs: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """The values each test filter lists among ``cdrs`` (rows with ``id`` and ``kind``), in alphabetical order."""
    from src.modules.cdr import cdr_store

    from src.modules.cdr.value_patterns import COMBINED_FILTER_SEPARATOR

    found: dict[str, dict[str, str]] = {field: {} for field in TEST_FILTERS}
    for cdr in cdrs:
        dataset_id, kind = int(cdr['id']), str(cdr.get('kind') or '').casefold()
        for field, spec in TEST_FILTERS.items():
            if kind not in spec['kinds']:
                continue
            column = _first_column(repository, dataset_id, spec['columns'])
            if column is None:
                continue
            if field == 'Test':
                name = _first_column(repository, dataset_id, spec['name_columns']) if kind in spec['name_kinds'] else None
                pairs = cdr_store.distinct_combinations(repository.db_path, kind, dataset_id, [column, *([name] if name else [])])
                if pairs is None:
                    # (Not copied yet: from the rows of its table.)
                    frame = repository.load_dataset_rows(dataset_id, [column, *([name] if name else [])], {})
                    pairs = [tuple('' if value is None or value != value else str(value).strip() for value in row)
                             for row in frame.drop_duplicates().itertuples(index=False)]
                for pair in pairs:
                    value = COMBINED_FILTER_SEPARATOR.join(part for part in pair if part) if pair and pair[0] else ''
                    if value:
                        found[field].setdefault(value.casefold(), value)
                continue
            values = cdr_store.distinct_texts(repository.db_path, kind, dataset_id, column)
            if values is None:
                # (Not copied yet: from the rows of its table.)
                values = repository.list_distinct_dataset_row_values(dataset_id, column, limit=None)
            for value in values:
                found[field].setdefault(value.casefold(), value)
    return {field: sorted(values.values(), key=lambda value: (value.casefold(), value)) for field, values in found.items()}
