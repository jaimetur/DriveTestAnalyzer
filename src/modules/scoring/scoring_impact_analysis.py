"""What the Methodology Impact says in plain words (see scoring_impact): why each operator moves and what stands out, from what the
same tests score with two methodologies. Every figure here comes from the methodology alone, never from the network.
"""
from __future__ import annotations

import math
from typing import Any

COMBINED = 'Combined'
CAUSES = ('weights', 'rules', 'new', 'removed')
CAUSE_LABELS = {'weights': 'Points moved between KPIs', 'rules': 'Other thresholds, formula or filters', 'new': 'New KPIs', 'removed': 'Removed KPIs'}
# Below this a difference is no change.
MATERIAL = .05
_DIGITS = 4


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _rounded(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else round(number, _DIGITS) + 0.0


def _causes_of(row: dict[str, Any], cell: dict[str, Any]) -> dict[str, float]:
    """What moves the points of a KPI for an operator: with the same score, the points the methodology gives it or takes from
    it, then what scores differently with its new maximum; a KPI one methodology does not score is new or removed."""
    maximum_before, maximum_after = _number(row.get('max_before')) or 0.0, _number(row.get('max_after')) or 0.0
    before, after = _number(cell.get('before')), _number(cell.get('after'))
    if maximum_before <= 0:
        return {'new': after or 0.0}
    if maximum_after <= 0:
        return {'removed': -(before or 0.0)}
    if before is None or after is None:
        return {}
    weights = (maximum_after - maximum_before) * before / maximum_before
    return {'weights': weights, 'rules': after - before - weights}


def drivers_part(kpis: dict[str, list[dict[str, Any]]], environments: list[str], operators: list[str]) -> dict[str, Any]:
    """Why each operator moves in each environment: its difference per cause."""
    part = {}
    for environment in environments:
        rows_of_operators = {}
        for name in operators:
            causes = dict.fromkeys(CAUSES, 0.0)
            measured = False
            for row in kpis.get(environment) or []:
                cell = (row.get('operators') or {}).get(name)
                if not cell:
                    continue
                for cause, value in _causes_of(row, cell).items():
                    measured = True
                    causes[cause] += value
            if measured:
                rows_of_operators[name] = {'total': _rounded(sum(causes.values())), 'causes': {key: _rounded(value) for key, value in causes.items()}}
        part[environment] = rows_of_operators
    return part


def _signed(value: float | None, digits: int = 2) -> str:
    return 'N/A' if value is None else f'{abs(value):,.{digits}f}' if abs(value) < 10 ** -digits / 2 else f'{value:+,.{digits}f}'


def _listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}" if names else ''


def conclusions(part: dict[str, Any], labels: dict[str, str], areas: dict[str, Any] | None = None) -> dict[str, Any]:
    """What stands out in All Environments: one headline and a few short facts, to read at a glance and to present."""
    def label(name: str) -> str:
        return labels.get(name, name)

    environment = COMBINED if COMBINED in part['scoring'] else next(iter(part['scoring']), None)
    if environment is None:
        return {'headline': '', 'facts': []}
    cells = part['scoring'][environment]['operators']
    moved = {name: cell['delta'] for name, cell in cells.items() if cell.get('delta') is not None}
    if not moved:
        return {'headline': '', 'facts': []}
    largest = max(abs(value) for value in moved.values())
    maximum = part['scoring'][environment].get('max_after') or 0
    facts: list[dict[str, str]] = []
    if largest < MATERIAL:
        headline = 'The scoring of every operator stays the same'
    else:
        low, high = min(moved.values()), max(moved.values())
        headline = (f'The scoring moves between {_signed(low)} and {_signed(high)} points of {maximum:,.0f}' if low != high
                    else f'The scoring moves {_signed(high)} points of {maximum:,.0f}')
        gains = sorted((name for name, value in moved.items() if value >= MATERIAL), key=lambda name: -moved[name])
        losses = sorted((name for name, value in moved.items() if value <= -MATERIAL), key=lambda name: moved[name])
        if gains:
            facts.append({'kind': 'gains', 'tone': 'gain', 'title': 'Who gains', 'text': _listed([f'{label(name)} ({_signed(moved[name])})' for name in gains])})
        if losses:
            facts.append({'kind': 'losses', 'tone': 'loss', 'title': 'Who loses', 'text': _listed([f'{label(name)} ({_signed(moved[name])})' for name in losses])})
    changed = [name for name, cell in cells.items() if cell.get('rank_before') and cell.get('rank_after') and cell['rank_before'] != cell['rank_after']]
    facts.append({'kind': 'positions', 'tone': 'loss' if changed else 'neutral', 'title': 'Positions',
                  'text': ('; '.join(f"{label(name)} goes from {cells[name]['rank_before']} to {cells[name]['rank_after']}" for name in changed)
                           if changed else 'No operator changes position')})
    flips = [name for name, cell in ((part['gap'].get(environment) or {}).get('total') or {}).items() if cell.get('flip')]
    if flips:
        facts.append({'kind': 'flips', 'tone': 'loss', 'title': f"Against {label(part['reference'])}", 'text': f'{_listed([label(name) for name in flips])} changes side'})
    categories = [row for row in part['categories'].get(environment) or [] if row['peak'] >= MATERIAL]
    if categories:
        top = max(categories, key=lambda row: row['peak'])
        facts.append({'kind': 'category', 'tone': 'neutral', 'title': 'Category that moves most', 'text': f"{top['category']}: up to {top['peak']:,.1f} points"})
    kpis = [row for row in part['kpis'].get(environment) or [] if row['peak'] >= MATERIAL]
    if kpis:
        facts.append({'kind': 'kpi', 'tone': 'neutral', 'title': 'KPI that moves most', 'text': f"{kpis[0]['kpi']} of {kpis[0]['category']}: up to {kpis[0]['peak']:,.1f} points"})
    where = (areas or {}).get('operators') or {}
    hit = [(name, item['worst']) for name, item in where.items() if item.get('worst') and item['worst']['value'] <= -MATERIAL]
    if hit:
        name, worst = min(hit, key=lambda entry: entry[1]['value'])
        facts.append({'kind': 'where', 'tone': 'loss', 'title': 'Where it hits most', 'text': f"{label(name)} in {worst['name']} ({_signed(worst['value'])})"})
    swaps = [(level, sum(row['leader_before'] != row['leader_after'] for row in rows.get(environment) or []), len(rows.get(environment) or []))
             for level, rows in part['areas'].items()]
    swaps = [item for item in swaps if item[1]]
    if swaps:
        level, count, total = swaps[-1]
        facts.append({'kind': 'leaders', 'tone': 'neutral', 'title': 'New leaders', 'text': f'In {count} of {total} {level} areas'})
    return {'headline': headline, 'facts': facts}
