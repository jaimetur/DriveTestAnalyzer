"""5G NR Mode (NSA/SA) classification for CDR datasets."""

from __future__ import annotations

import re
from pathlib import Path

NR_MODES = ('NSA', 'SA')
DEFAULT_NR_MODE = 'NSA'
NR_MODE_DATASET_KINDS = frozenset({'data', 'voice', 'speech'})
# Scoring & GAP Analysis also compares both NR Modes: the NSA and SA CDRs of the chosen campaigns, each campaign with
# its NR Mode (so the NSA and SA tests of an operator are never added together).
NSA_VS_SA = 'NSA+SA'
SCORING_NR_MODES = (*NR_MODES, NSA_VS_SA)
NR_MODE_LABELS = {'NSA': 'NSA', 'SA': 'SA', NSA_VS_SA: 'NSA vs SA'}
# The loaded CDR rows of an NSA vs SA calculation keep the NR Mode of their CDR in this column.
NR_MODE_COLUMN = '__nr_mode'

_NSA_TOKEN = re.compile(r'(?:5g|g)?nsa')
_SA_TOKEN = re.compile(r'(?:5g|g)?sa')
# The NR Mode a campaign names (UK_Q3_SA_2026, 2026-Q3-SA), as the Campaign Maps read it.
_CAMPAIGN_MODE = re.compile(r'(?:^|(?<=[_\- ]))(NSA|SA)(?=$|[_\- ])', re.IGNORECASE)


def normalize_nr_mode(value: object) -> str | None:
    """Return ``NSA`` or ``SA`` for a supported value, otherwise ``None``."""
    text = str(value or '').strip().upper()
    return text if text in NR_MODES else None


def normalize_scoring_nr_mode(value: object) -> str | None:
    """Return ``NSA``, ``SA`` or ``NSA+SA`` (NSA vs SA) for a supported value, otherwise ``None``."""
    text = re.sub(r'\s+', '', str(value or '')).upper()
    if text in {'NSA+SA', 'NSAVSSA', 'NSA/SA', 'SA+NSA', 'BOTH'}:
        return NSA_VS_SA
    return normalize_nr_mode(text)


def nr_modes_of(value: object) -> tuple[str, ...]:
    """The NR Modes of the CDRs a Scoring NR Mode uses: both for NSA vs SA."""
    mode = normalize_scoring_nr_mode(value)
    return NR_MODES if mode == NSA_VS_SA else ((mode,) if mode else ())


def nr_mode_label(value: object) -> str:
    """How an NR Mode reads (NSA vs SA for both)."""
    mode = normalize_scoring_nr_mode(value)
    return NR_MODE_LABELS[mode] if mode else str(value or '').strip()


def campaign_with_nr_mode(value: object, nr_mode: object) -> object:
    """A campaign of a CDR as an NSA vs SA calculation scores it: naming the NR Mode of the CDR.

    A campaign that names it (UK_Q3_SA_2026 of an SA CDR) and one without a mode of an NSA CDR (UK_Q2_2026, as the
    Campaign Maps read NSA campaigns) stay as they are; an SA CDR's campaign without a mode gets it (UK_Q2_2026 SA), and
    one naming the other mode takes the mode of its CDR, so the NSA and SA tests of a campaign are never scored together.
    """
    mode = normalize_nr_mode(nr_mode)
    if mode is None or value is None:
        return value
    text = str(value).strip()
    if not text or text.casefold() in {'<na>', 'nan', 'nat', 'none'}:
        return value
    match = _CAMPAIGN_MODE.search(text)
    named = match.group(1).upper() if match else None
    if named == mode or (named is None and mode == 'NSA'):
        return value
    if named is None:
        return f'{text} {mode}'
    return f'{text[:match.start(1)]}{mode}{text[match.end(1):]}'


def infer_nr_mode(file_name: object) -> str:
    """Suggest the NR Mode of a CDR from its file name.

    ``SA`` is suggested only when the name explicitly identifies Standalone
    (for example ``UK_Q2_2026_SA_Data.csv``, ``5G SA`` or ``Standalone``).
    Names that mention NSA/Non-Standalone, or nothing at all, default to NSA.
    """
    stem = Path(str(file_name or '')).stem
    # Split camel-case words (``DataSA`` -> ``Data SA``) before lower-casing.
    spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', stem)
    normalized = re.sub(r'[^a-z0-9]+', ' ', spaced.casefold())
    tokens = normalized.split()
    compact = ''.join(tokens)
    if 'nonstandalone' in compact or any(_NSA_TOKEN.fullmatch(token) for token in tokens):
        return 'NSA'
    if 'standalone' in compact or any(_SA_TOKEN.fullmatch(token) for token in tokens):
        return 'SA'
    return DEFAULT_NR_MODE


def dataset_nr_mode(dataset_kind: object, nr_mode: object, file_name: object = '') -> str | None:
    """Return the effective NR Mode of a dataset, or ``None`` for non-CDR files."""
    if str(dataset_kind or '').casefold() not in NR_MODE_DATASET_KINDS:
        return None
    return normalize_nr_mode(nr_mode) or infer_nr_mode(file_name)
