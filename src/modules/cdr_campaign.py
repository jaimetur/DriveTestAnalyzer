"""The Campaign of a CDR dataset: its year and quarter, such as ``2026-Q2``.

Every CDR shows its campaign in the Datasets cards of Workspace (its NSA or SA mode is the
NR Mode column). While the user has not chosen one, it is suggested from the file name: the
quarter (``Q2``) and the year (``2026``, or the dates of the name, such as ``20260512``). A
CDR whose name has no quarter or year has no campaign until the user writes one.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.modules.nr_mode import NR_MODE_DATASET_KINDS

CAMPAIGN_DATASET_KINDS = NR_MODE_DATASET_KINDS
CAMPAIGN_FORMAT_HINT = 'YYYY-Qn (for example 2026-Q2)'

_QUARTER = re.compile(r'(?<![a-z0-9])q\s*[_\- ]?([1-4])(?!\d)', re.IGNORECASE)
_YEAR = re.compile(r'(?<!\d)((?:19|20)\d{2})(?!\d)')
# yyyymmdd, yyyy-mm-dd, yyyy_mm_dd or yyyy.mm.dd.
_DATE = re.compile(r'(?<!\d)(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)')


def _year_of_dates(stem: str, quarter: int) -> str:
    """The year of the dates of a name: the first date in the quarter, else the first measurement date.

    ``20260105_UK Q4 CDR 20251110-20251209`` was exported in 2026 for the Q4 2025 campaign.
    """
    dates = [(match.start(), match.group(1), int(match.group(2))) for match in _DATE.finditer(stem)]
    in_quarter = [year for _start, year, month in dates if (month - 1) // 3 + 1 == quarter]
    measured = [year for start, year, _month in dates if start > 0]
    return next(iter(in_quarter or measured or [year for _start, year, _month in dates]), '')


def infer_campaign(file_name: object) -> str:
    """Suggest the campaign of a CDR from its file name, or ``''`` when the name has no quarter or year.

    ``NetCheck_UK_CDR_Data_2026_Q2_SA.xlsx`` → ``2026-Q2``;
    ``20260623 Final Data CDR UK Q2 20260512 - 20260613.xlsx`` → ``2026-Q2``.
    """
    stem = Path(str(file_name or '')).stem
    quarter_match = _QUARTER.search(stem)
    if not quarter_match:
        return ''
    quarter = int(quarter_match.group(1))
    year_match = _YEAR.search(stem)
    year = year_match.group(1) if year_match else _year_of_dates(stem, quarter)
    return f'{year}-Q{quarter}' if year else ''


def normalize_campaign(value: object) -> str:
    """The campaign a user writes, as ``YYYY-Qn``; ``''`` when blank, ValueError when it has no year and quarter.

    Any spelling with a year and a quarter is accepted (``2026 q2``, ``UK_Q2_2026_SA``); an NSA or SA
    in it is left out, since the NR Mode of the CDR tells it.
    """
    text = str(value or '').strip()
    if not text:
        return ''
    quarter = _QUARTER.search(text)
    year = _YEAR.search(text)
    if not quarter or not year:
        raise ValueError(f'Enter the campaign as {CAMPAIGN_FORMAT_HINT}, or leave it blank.')
    return f'{year.group(1)}-Q{quarter.group(1)}'


def dataset_campaign(dataset_kind: object, campaign: object, file_name: object = '') -> str | None:
    """The campaign of a CDR: chosen by the user (blank included), else suggested; ``None`` for other files."""
    if str(dataset_kind or '').casefold() not in CAMPAIGN_DATASET_KINDS:
        return None
    if campaign is None:
        return infer_campaign(file_name)
    try:
        return normalize_campaign(campaign)
    except ValueError:
        return str(campaign).strip()
