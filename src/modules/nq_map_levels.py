"""The Map Levels of the Non-Qualified Calls of a workspace: the levels the maps colour each measure by.

The map of a call and NQ Maps colour the RSRP and SINR of the samples of the CDRs and of the Layer3 Logs, and the RSRQ
and the UE Tx Power of the logs, by levels: each a name, the lowest value it takes (``lower``; the last level takes
every value below the one above it) and a colour, the best level first for RSRP, RSRQ and SINR and the highest power
first for UE Tx Power. The defaults are the levels of Network Insights for RSRP (with Extremely poor below −120 dBm) and
SINR, the ranges of the KMZ files in the six RSRP levels for RSRQ and the ranges of the KMZ files for UE Tx Power; admins
and super-admins change them in the NQ Analysis Configuration (Map Levels), and they travel with the NQ Calls
Configuration (export, transfers, backup and restore).
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

STATE_KEY = 'nq_map_levels'
# The measures, in the order of the dialog: their name and unit.
MEASURES = {'rsrp': ('RSRP', 'dBm'), 'rsrq': ('RSRQ', 'dB'), 'sinr': ('SINR', 'dB'), 'tx': ('UE Tx Power', 'dBm')}
MIN_LEVELS, MAX_LEVELS = 2, 10
MAX_LABEL = 40
# Below the Very poor RSRP of Network Insights, the level the Layer3 Logs draw too (their legend starts at −120 dBm).
RSRP_FLOOR_CLASS = ('Extremely poor', -120.0, '#8B0A1A')
# The levels of the RSRQ of the Layer3 Logs: the ranges of the legend of their KMZ files, named and coloured as those of
# the RSRP (its six levels: Good joins the two ranges from −14 to −10 dB of the KMZ files).
RSRQ_CLASSES = (
    ('Excellent', -10.0, '#2E8B57'),
    ('Good', -14.0, '#8BC34A'),
    ('Fair', -16.0, '#F2C230'),
    ('Poor', -20.0, '#F08A24'),
    ('Very poor', -24.0, '#D7263D'),
    ('Extremely poor', float('-inf'), '#8B0A1A'),
)
# The UE Tx Power of the KMZ files, the higher the worse (named by their range alone).
TX_CLASSES = (
    ('', 24.0, '#8B0000'), ('', 22.0, '#FF0000'), ('', 15.0, '#FF8C00'), ('', 5.0, '#FFE600'), ('', 0.0, '#90EE64'),
    ('', -10.0, '#00BFFF'), ('', float('-inf'), '#0000FF'),
)
COLOUR = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _levels(classes: Any) -> list[dict[str, Any]]:
    return [{'label': label, 'lower': None if math.isinf(lower) else lower, 'colour': colour.upper()} for label, lower, colour in classes]


def default_levels() -> dict[str, list[dict[str, Any]]]:
    """The levels of a workspace that has not changed them."""
    from src.modules.network_insights import RSRP_CLASSES, SINR_CLASSES

    floor_label, floor, floor_colour = RSRP_FLOOR_CLASS
    rsrp = [(label, floor if math.isinf(lower) else lower, colour) for label, lower, colour in RSRP_CLASSES]
    rsrp.append((floor_label, float('-inf'), floor_colour))
    return {'rsrp': _levels(rsrp), 'rsrq': _levels(RSRQ_CLASSES), 'sinr': _levels(SINR_CLASSES), 'tx': _levels(TX_CLASSES)}


def normalize_measure(measure: str, levels: Any) -> list[dict[str, Any]]:
    """The levels of a measure, checked: from 2 to 10, each a name (up to 40 characters, empty for its range alone), a
    colour and a lower bound below that of the level above it, the last one without any."""
    name = MEASURES[measure][0]
    if not isinstance(levels, list) or not MIN_LEVELS <= len(levels) <= MAX_LEVELS:
        raise ValueError(f'{name} needs from {MIN_LEVELS} to {MAX_LEVELS} levels.')
    found = []
    for index, level in enumerate(levels):
        if not isinstance(level, dict):
            raise ValueError(f'Level {index + 1} of {name} is not valid.')
        label = re.sub(r'\s+', ' ', str(level.get('label') or '')).strip()
        if len(label) > MAX_LABEL:
            raise ValueError(f'The name of level {index + 1} of {name} is longer than {MAX_LABEL} characters.')
        colour = str(level.get('colour') or '').strip()
        if not COLOUR.match(colour):
            raise ValueError(f'Choose the colour of level {index + 1} of {name} ({label or "without a name"}).')
        last = index == len(levels) - 1
        lower = None
        if not last:
            try:
                lower = float(level.get('lower'))
            except (TypeError, ValueError):
                raise ValueError(f'Give the lowest value of level {index + 1} of {name} ({label or "without a name"}).') from None
            if not math.isfinite(lower) or abs(lower) > 1000:
                raise ValueError(f'The lowest value of level {index + 1} of {name} is not valid.')
            if found and lower >= found[-1]['lower']:
                raise ValueError(f'Each level of {name} starts below the one above it: level {index + 1} starts at {lower:g}, '
                                 f'level {index} at {found[-1]["lower"]:g}.')
        found.append({'label': label, 'lower': lower, 'colour': colour.upper()})
    return found


def normalize_levels(levels: Any, base: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Every measure: those given, checked, and the others from ``base`` (the defaults)."""
    given = levels if isinstance(levels, dict) else {}
    result = dict(base or default_levels())
    for measure in MEASURES:
        if measure in given:
            result[measure] = normalize_measure(measure, given[measure])
    return result


def load_levels(task_repository: Any) -> dict[str, list[dict[str, Any]]]:
    """The levels of the workspace: those it changed, the defaults for the others (also when one stored is not valid)."""
    try:
        stored = json.loads(task_repository.get_workspace_state(STATE_KEY) or '{}')
    except (TypeError, ValueError):
        stored = {}
    return normalize_levels_safe(stored)


def store_levels(task_repository: Any, levels: dict[str, list[dict[str, Any]]]) -> None:
    """Keep only the measures that are not their defaults, so that a workspace that did not change one follows its defaults."""
    defaults = default_levels()
    changed = {measure: items for measure, items in levels.items() if measure in MEASURES and items != defaults[measure]}
    task_repository.set_workspace_state(STATE_KEY, json.dumps(changed, ensure_ascii=False))


def level_text(levels: list[dict[str, Any]], index: int, unit: str = '') -> str:
    """``Good (−90 to −80 dBm)``: a level as the legends write it (its range alone when it has no name)."""
    level, upper = levels[index], levels[index - 1]['lower'] if index else None
    number = lambda value: f'{value:g}'  # noqa: E731
    span = (f'< {number(upper)}' if level['lower'] is None else f'≥ {number(level["lower"])}' if upper is None
            else f'{number(level["lower"])} to {number(upper)}') + (f' {unit}' if unit else '')
    return f"{level['label']} ({span})" if level['label'] else span


def changes(old: Any, new: Any) -> list[str]:
    """What changes from the levels ``old`` to ``new``: each measure changed with all its levels."""
    was, now = normalize_levels_safe(old), normalize_levels_safe(new)
    lines = []
    for measure, (name, unit) in MEASURES.items():
        if was[measure] != now[measure]:
            texts = [f"{level_text(now[measure], index, unit)} {level['colour']}" for index, level in enumerate(now[measure])]
            lines.append(f"{name}: {', '.join(texts)}")
    return lines


def merged_levels(current: dict[str, list[dict[str, Any]]], incoming: Any) -> dict[str, list[dict[str, Any]]]:
    """The levels ``current`` with the measures of ``incoming`` that are valid (those of a package, measure by measure)."""
    result = dict(current)
    for measure in MEASURES:
        if isinstance(incoming, dict) and measure in incoming:
            try:
                result[measure] = normalize_measure(measure, incoming[measure])
            except ValueError:
                pass
    return result


def normalize_levels_safe(levels: Any) -> dict[str, list[dict[str, Any]]]:
    """The levels given, a measure that is not valid (or not given) taking its defaults."""
    return merged_levels(default_levels(), levels)


def save_levels(task_repository: Any, levels: Any) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """Save the levels of the workspace (every measure given; the others keep theirs) and tell what changed."""
    before = load_levels(task_repository)
    after = normalize_levels(levels, before)
    store_levels(task_repository, after)
    return after, changes(before, after)


def payload(task_repository: Any) -> dict[str, Any]:
    """The levels of the workspace, the defaults and the measures, for the Map Levels dialog."""
    return {'levels': load_levels(task_repository), 'defaults': default_levels(),
            'measures': [{'key': key, 'label': label, 'unit': unit} for key, (label, unit) in MEASURES.items()]}
