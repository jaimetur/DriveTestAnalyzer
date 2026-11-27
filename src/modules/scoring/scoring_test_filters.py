"""The Test Name and Test Type filters of Scoring & GAP Analysis (ticket #207).

They leave tests out of a scoring (or keep only some) without changing the CDRs, as the other Context Filters do:

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
    # The columns each one is read from: the first the CDR has.
    'Test_Name': {'columns': ('Test_Name',), 'kinds': ('data',), 'label': 'Test Name'},
    'Test_Type': {'columns': ('Type_of_Test', 'Session_Type'), 'kinds': ('data', 'voice', 'speech'), 'label': 'Test Type'},
}
TEST_FILTER_FIELDS = tuple(TEST_FILTERS)


def filters_kind(field: str, kind: str) -> bool:
    """Whether a test filter applies to the CDRs of ``kind`` (any other filter applies to every CDR)."""
    spec = TEST_FILTERS.get(field)
    return spec is None or str(kind).casefold() in spec['kinds']


def scoring_test_filter_options(repository: Any, cdrs: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """The values each test filter lists among ``cdrs`` (rows with ``id`` and ``kind``), in alphabetical order."""
    from src.modules.cdr import cdr_store

    found: dict[str, dict[str, str]] = {field: {} for field in TEST_FILTERS}
    for cdr in cdrs:
        dataset_id, kind = int(cdr['id']), str(cdr.get('kind') or '').casefold()
        for field, spec in TEST_FILTERS.items():
            if kind not in spec['kinds']:
                continue
            column = next((resolved for candidate in spec['columns']
                           if (resolved := repository.resolve_dataset_row_column_name(dataset_id, candidate)) is not None), None)
            if column is None:
                continue
            values = cdr_store.distinct_texts(repository.db_path, kind, dataset_id, column)
            if values is None:
                # (Not copied yet: from the rows of its table.)
                values = repository.list_distinct_dataset_row_values(dataset_id, column, limit=None)
            for value in values:
                found[field].setdefault(value.casefold(), value)
    return {field: sorted(values.values(), key=lambda value: (value.casefold(), value)) for field, values in found.items()}
