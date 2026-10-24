"""The Umlaut CDR exports: how their workbooks are laid out and the columns the tool derives from them.

Umlaut delivers one workbook per service (Voice_M2M_Calls, Voice_M2M_SQ_Samples, HTTP_File_DL, Ping...), named
``<Benchmark>_<Service>_<export date>``, with a Statistics sheet and one data sheet per measured operator
(``client<N>_<Operator>``). Every column keeps its Umlaut name; the tool adds a few it needs:

- ``Campaign``: the benchmark of the file name (``WindTre_Vendor_Benchmark_2025_Round1``) when the CDR has none.
- ``Test_Key``: the test of each row, its Filename, Task Name and start time (the Sequence of a call is shared by the
  data tests run at the same time).
- ``ECI``: the LTE cells of the row (eNodeB × 256 + Cell ID) where it started and ended, as ``start->end``.

Voice and Speech workbooks list the two sides of each call one after the other, so some headers (Sequence, Filename,
Route Name...) appear once per side: the repeated header takes the side of its block (``Side2 Sequence``).
The All_Data and All_Voice workbooks summarise the service workbooks and are not CDRs of their own.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src.modules.column_names import resolve_column_name

# A header of one side of a call ("Side1 Call Type", "Side 2 Meta Status").
SIDE_HEADER_PATTERN = r'^side\s*\d+\b'
# The words of the summary workbooks in their file name.
SUMMARY_NAME_WORDS = ('all data', 'all voice')
# The first word of the service in an export file name, and the export date that ends it.
_SERVICE_WORDS = frozenset({'voice', 'conversational', 'http', 'https', 'interactivity', 'youtube', 'ping', 'dns', 'all'})
_EXPORT_DATE = re.compile(r'[_\s-]*\d{4}-\d{2}-\d{2}(?:[_\s-]+\d{2}-\d{2}-\d{2})?$')

# Where each row starts: the call, the ping, the DNS lookup, the speech sample, else the network access of the test.
START_TIME_COLUMNS = ('Session TA Start', 'Ping TA Start', 'DNS TA Start', 'POLQA Sample TA Start', 'Network Access TA Start')
# The LTE cell (eNodeB, Cell ID) where each row starts and ends: the call setup and end of the A side, the speech sample,
# then the service access of a data test (each service names it its own way).
START_CELL_COLUMNS = (
    ('Side1 Call Setup latest available eNodeB/RNC', 'Side1 Call Setup latest available Sector/Cell ID'),
    ('Side1 Sample Start eNodeB/RNC', 'Side1 Sample Start Sector/Cell ID'),
    ('Service Access RNC/eNodeB Start', 'Service Access Cell ID/Sector ID Start'),
    ('Service Access RNC/eNodeB Start', 'Service Access Cell ID/Sector Start'),
    ('Catalog/App Start Session RNC/eNodeB Start', 'Catalog/App Start Session Cell ID/Sector Start'),
    ('Ping RNC/eNodeB Start', 'Ping Cell ID/Sector Start'),
    ('Network Access RNC/eNodeB Start', 'Network Access Cell ID/ Sector Start'),
    ('DNS Resolution RNC/eNodeB Start', 'DNS Resolution Cell ID/Sector Start'),
)
END_CELL_COLUMNS = (
    ('Side1 Call End eNodeB/RNC', 'Side1 Call End Sector/Cell ID'),
    ('Side1 Sample End eNodeB/RNC', 'Side1 Sample End Sector/Cell ID'),
    ('Session RNC/eNodeB End', 'Session Cell ID/Sector End'),
    ('Video Session RNC/ eNodeB End', 'Video Session Cell ID/Sector End'),
)
# An LTE cell inside its eNodeB is 0 to 255; a larger Cell ID belongs to a 2G or 3G cell.
_LTE_CELLS_PER_ENODEB = 256


def is_summary_file(file_name: object) -> bool:
    """Whether a file is one of the summary workbooks (All_Data, All_Voice) rather than a service CDR."""
    words = ' '.join(re.split(r'[^a-z0-9]+', Path(str(file_name or '')).stem.casefold()))
    return any(f' {word} ' in f' {words} ' for word in SUMMARY_NAME_WORDS)


def export_campaign(file_name: object) -> str:
    """The benchmark of an export file name: the words before its service (empty when it names no service)."""
    stem = _EXPORT_DATE.sub('', Path(str(file_name or '')).stem)
    tokens = [token for token in re.split(r'_+', stem) if token]
    for index, token in enumerate(tokens):
        if index and token.casefold() in _SERVICE_WORDS:
            return '_'.join(tokens[:index])
    return ''


def _first_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    return next((resolved for name in candidates if (resolved := resolve_column_name(columns, name))), None)


def _text(series: pd.Series) -> pd.Series:
    values = series.astype(object).where(series.notna(), '')
    return values.map(lambda value: format(value, '.0f') if isinstance(value, float) and value.is_integer() else str(value).strip())


def _cells(dataset: pd.DataFrame, pairs: tuple[tuple[str, str], ...]) -> pd.Series:
    """The ECI of every row from the first pair of columns that has it."""
    columns = list(dataset.columns)
    cells = pd.Series('', index=dataset.index, dtype=object)
    for enodeb_name, cell_name in pairs:
        enodeb_column, cell_column = resolve_column_name(columns, enodeb_name), resolve_column_name(columns, cell_name)
        if not enodeb_column or not cell_column:
            continue
        enodeb = pd.to_numeric(dataset[enodeb_column], errors='coerce')
        cell = pd.to_numeric(dataset[cell_column], errors='coerce')
        valid = enodeb.gt(0) & cell.ge(0) & cell.lt(_LTE_CELLS_PER_ENODEB) & enodeb.mod(1).eq(0) & cell.mod(1).eq(0)
        eci = (enodeb * _LTE_CELLS_PER_ENODEB + cell).where(valid)
        found = eci.map(lambda value: '' if pd.isna(value) else str(int(value)))
        cells = cells.where(cells.ne(''), found)
    return cells


def derive_columns(dataset: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Add Campaign (when the CDR has none), Test_Key and ECI to the rows of one Umlaut CDR."""
    columns = list(dataset.columns)
    campaign_column = resolve_column_name(columns, 'Campaign')
    if campaign_column is None or not dataset[campaign_column].notna().any():
        campaign = export_campaign(file_name)
        dataset[campaign_column or 'Campaign'] = campaign or pd.NA
    parts = [_text(dataset[column]) for column in (
        _first_column(columns, ('Filename',)), _first_column(columns, ('Task Name',)), _first_column(columns, START_TIME_COLUMNS),
    ) if column]
    if parts:
        key = parts[0]
        for part in parts[1:]:
            key = key + '|' + part
        dataset['Test_Key'] = key.where(key.str.strip('|').ne(''), pd.NA)
    start, end = _cells(dataset, START_CELL_COLUMNS), _cells(dataset, END_CELL_COLUMNS)
    if start.ne('').any() or end.ne('').any():
        chain = [
            '->'.join(dict.fromkeys(cell for cell in pair if cell)) for pair in zip(start, end, strict=True)
        ]
        dataset['ECI'] = pd.Series(chain, index=dataset.index, dtype=object).where(lambda values: values.ne(''), pd.NA)
    return dataset
