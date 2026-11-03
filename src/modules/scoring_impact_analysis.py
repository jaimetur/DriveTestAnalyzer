"""The analysis of the Methodology Impact (see scoring_impact): from what the same tests score with two methodologies, who is
affected more than the others, why, whether the change goes with or against the strengths of each operator, how stable it is
and what stands out to present. Every figure here comes from the methodology alone, never from the network.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

COMBINED = 'Combined'
CAUSES = ('weights', 'rules', 'new', 'removed')
CAUSE_LABELS = {'weights': 'Points moved between KPIs', 'rules': 'Other thresholds, formula or filters', 'new': 'New KPIs',
                'removed': 'Removed KPIs'}
# Below this a difference is no change, and a correlation of fewer KPIs or areas says nothing.
MATERIAL = .05
MIN_CORRELATION_POINTS = 5
STRONG_CORRELATION = .5
_DIGITS = 4


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _rounded(value: Any) -> float | None:
    number = _number(value)
    return None if number is None else round(number, _DIGITS) + 0.0


def pearson(first: Iterable[float], second: Iterable[float]) -> float | None:
    """The correlation of two series of the same length, None when one of them does not vary."""
    xs, ys = list(first), list(second)
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    across = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    spread_x, spread_y = sum((x - mean_x) ** 2 for x in xs), sum((y - mean_y) ** 2 for y in ys)
    if spread_x <= 1e-12 or spread_y <= 1e-12:
        return None
    return max(-1.0, min(1.0, across / math.sqrt(spread_x * spread_y)))


def linear_fit(first: Iterable[float], second: Iterable[float]) -> dict[str, float] | None:
    """The straight line that fits two series: y = slope * x + intercept."""
    xs, ys = list(first), list(second)
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread <= 1e-12:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / spread
    return {'slope': _rounded(slope), 'intercept': _rounded(mean_y - slope * mean_x)}


def quantile(ordered: list[float], share: float) -> float | None:
    """A quantile of sorted values, between their neighbours."""
    if not ordered:
        return None
    position = (len(ordered) - 1) * share
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def strength_words(value: float | None) -> str:
    """How strong a correlation reads."""
    size = abs(value or 0)
    return 'strong' if size >= .7 else 'moderate' if size >= STRONG_CORRELATION else 'weak' if size >= .3 else 'no clear'


def competition_part(scoring: dict[str, Any], environments: list[str], operators: list[str]) -> dict[str, Any]:
    """Who the change favours against the others, in each environment: each operator against the mean of the operators, each
    pair of operators head to head, and the distance of each operator to the next one."""
    part = {}
    for environment in environments:
        cells = (scoring.get(environment) or {}).get('operators') or {}
        measured = [name for name in operators if (cells.get(name) or {}).get('delta') is not None]
        mean = sum(cells[name]['delta'] for name in measured) / len(measured) if measured else 0.0
        matrix: dict[str, dict[str, Any]] = {}
        for first in measured:
            matrix[first] = {}
            for second in measured:
                if first != second:
                    before, after = cells[first]['before'] - cells[second]['before'], cells[first]['after'] - cells[second]['after']
                    matrix[first][second] = {'before': _rounded(before), 'after': _rounded(after), 'delta': _rounded(after - before)}
        ordered = sorted(measured, key=lambda name: cells[name].get('rank_after') or 99)
        margins = []
        for upper, lower in zip(ordered, ordered[1:]):
            step = matrix[upper][lower]
            margins.append({'operator': upper, 'next': lower, **step,
                            # How much of the distance before the change the methodology gives or takes.
                            'share': _rounded(abs(step['delta']) / abs(step['before'])) if step['before'] else None})
        before_points = [cells[name]['before'] for name in measured]
        after_points = [cells[name]['after'] for name in measured]
        part[environment] = {
            'mean': _rounded(mean), 'relative': {name: _rounded(cells[name]['delta'] - mean) for name in measured},
            'matrix': matrix, 'margins': margins,
            'spread_before': _rounded(max(before_points) - min(before_points)) if measured else None,
            'spread_after': _rounded(max(after_points) - min(after_points)) if measured else None,
        }
    return part


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
    """Why each operator moves in each environment: its difference per cause and per category, each with its causes."""
    part = {}
    for environment in environments:
        rows_of_operators = {}
        for name in operators:
            causes = dict.fromkeys(CAUSES, 0.0)
            categories: dict[str, dict[str, Any]] = {}
            measured = False
            for row in kpis.get(environment) or []:
                cell = (row.get('operators') or {}).get(name)
                if not cell:
                    continue
                split = _causes_of(row, cell)
                category = categories.setdefault(str(row.get('category') or ''), {'delta': 0.0, 'causes': dict.fromkeys(CAUSES, 0.0)})
                for cause, value in split.items():
                    measured = True
                    causes[cause] += value
                    category['delta'] += value
                    category['causes'][cause] += value
            if measured:
                rows_of_operators[name] = {
                    'total': _rounded(sum(causes.values())), 'causes': {key: _rounded(value) for key, value in causes.items()},
                    'categories': {key: {'delta': _rounded(value['delta']), 'causes': {cause: _rounded(amount) for cause, amount in value['causes'].items()}}
                                   for key, value in categories.items()},
                }
        part[environment] = rows_of_operators
    return part


def exposure_part(kpis: dict[str, list[dict[str, Any]]], environments: list[str], operators: list[str]) -> dict[str, Any]:
    """Whether the points the methodology moves go with or against the strengths of each operator: per KPI with other points,
    what it gains or loses (x) against how much the operator beats the mean of the operators in it (y, in percentage points of
    its maximum), with their correlation and straight line."""
    part = {}
    for environment in environments:
        rows = [row for row in kpis.get(environment) or []
                if abs((_number(row.get('max_after')) or 0.0) - (_number(row.get('max_before')) or 0.0)) > 1e-6]
        strengths: list[tuple[dict[str, Any], dict[str, float]]] = []
        for row in rows:
            maximum_before, maximum_after = _number(row.get('max_before')) or 0.0, _number(row.get('max_after')) or 0.0
            scores = {}
            for name in operators:
                cell = (row.get('operators') or {}).get(name) or {}
                points, maximum = (cell.get('before'), maximum_before) if maximum_before > 0 else (cell.get('after'), maximum_after)
                if _number(points) is not None and maximum > 0:
                    scores[name] = float(points) / maximum * 100
            if scores:
                mean = sum(scores.values()) / len(scores)
                strengths.append((row, {name: value - mean for name, value in scores.items()}))
        operators_part = {}
        for name in operators:
            points = [{'code': row['code'], 'kpi': row.get('kpi'), 'category': row.get('category'),
                       'x': _rounded((_number(row.get('max_after')) or 0.0) - (_number(row.get('max_before')) or 0.0)),
                       'y': _rounded(values[name])} for row, values in strengths if name in values]
            xs, ys = [point['x'] for point in points], [point['y'] for point in points]
            correlation = pearson(xs, ys)
            operators_part[name] = {
                'points': points, 'r': _rounded(correlation), 'fit': linear_fit(xs, ys),
                # What moving the points gives the operator against the mean of the operators, at its score.
                'net': _rounded(sum(x * y for x, y in zip(xs, ys)) / 100),
            }
        part[environment] = {'kpis': len(strengths), 'operators': operators_part}
    return part


def stability_part(campaigns: list[dict[str, Any]], operators: list[str]) -> dict[str, Any]:
    """The same change on the tests of other campaigns (``campaigns``: label, comparable, differences per operator): whether each
    operator moves the same way in all of them. Only the campaigns with the KPIs of both methodologies measured count."""
    comparable = [item for item in campaigns if item.get('comparable')]
    summary = {}
    for name in operators:
        values = [item['operators'][name] for item in comparable if (item.get('operators') or {}).get(name) is not None]
        if not values:
            continue
        summary[name] = {'campaigns': len(values), 'up': sum(value >= MATERIAL for value in values),
                         'down': sum(value <= -MATERIAL for value in values), 'mean': _rounded(sum(values) / len(values)),
                         'low': _rounded(min(values)), 'high': _rounded(max(values))}
    return {'campaigns': campaigns, 'summary': summary}


def _signed(value: float | None, digits: int = 2) -> str:
    return 'N/A' if value is None else f'{abs(value):,.{digits}f}' if abs(value) < 10 ** -digits / 2 else f'{value:+,.{digits}f}'


def _listed(names: list[str]) -> str:
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}" if names else ''


def conclusions(part: dict[str, Any], labels: dict[str, str], areas: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """What stands out in All Environments, to present: each conclusion with its title, its headline figure and what it says."""
    def label(name: str) -> str:
        return labels.get(name, name)

    environment = COMBINED if COMBINED in part['scoring'] else (next(iter(part['scoring']), None))
    if environment is None:
        return []
    items: list[dict[str, Any]] = []
    cells = part['scoring'][environment]['operators']
    moved = {name: cell['delta'] for name, cell in cells.items() if cell.get('delta') is not None}
    if not moved:
        return items
    largest = max(abs(value) for value in moved.values())
    if largest < MATERIAL:
        items.append({'kind': 'size', 'title': 'Size of the impact', 'headline': 'No change', 'tone': 'flat',
                      'text': 'The scoring of every operator stays the same in All Environments.'})
    else:
        best, worst = max(moved, key=moved.get), min(moved, key=moved.get)
        items.append({'kind': 'size', 'title': 'Size of the impact', 'headline': f'{_signed(moved[worst])} to {_signed(moved[best])}', 'tone': 'neutral',
                      'text': f"The methodology moves the scoring between {_signed(moved[worst])} points ({label(worst)}) and {_signed(moved[best])} points ({label(best)}) "
                              f"of {part['scoring'][environment].get('max_after') or 0:,.0f}."})
    competition = part['competition'].get(environment) or {}
    relative = competition.get('relative') or {}
    if relative and largest >= MATERIAL and len(relative) > 1:
        favoured = sorted((name for name, value in relative.items() if value >= MATERIAL), key=lambda name: -relative[name])
        harmed = sorted((name for name, value in relative.items() if value <= -MATERIAL), key=lambda name: relative[name])
        parts = []
        if harmed:
            parts.append(f"{_listed([f'{label(name)} ({_signed(relative[name])})' for name in harmed])} {'come' if len(harmed) > 1 else 'comes'} out worse")
        if favoured:
            parts.append(f"{_listed([f'{label(name)} ({_signed(relative[name])})' for name in favoured])} {'come' if len(favoured) > 1 else 'comes'} out better")
        if parts:
            items.append({'kind': 'relative', 'title': 'Who it affects most', 'tone': 'loss' if harmed else 'gain',
                          'headline': label(harmed[0]) if harmed else label(favoured[0]),
                          'text': f"Against the mean of the operators ({_signed(competition.get('mean'))}), {' and '.join(parts)}: this is what changes between them."})
        pairs = [(first, second, step['delta']) for first, others in (competition.get('matrix') or {}).items() for second, step in others.items()]
        if pairs:
            first, second, delta = max(pairs, key=lambda item: item[2])
            if delta >= MATERIAL:
                items.append({'kind': 'head', 'title': 'Largest shift between two operators', 'headline': _signed(delta), 'tone': 'neutral',
                              'text': f'{label(first)} gains {delta:,.2f} points against {label(second)}.'})
    changed = [name for name, cell in cells.items() if cell.get('rank_before') and cell.get('rank_after') and cell['rank_before'] != cell['rank_after']]
    if changed:
        items.append({'kind': 'positions', 'title': 'Positions', 'headline': f'{len(changed)} change', 'tone': 'loss',
                      'text': 'The positions change: ' + ', '.join(f"{label(name)} from {cells[name]['rank_before']} to {cells[name]['rank_after']}" for name in changed) + '.'})
    elif competition.get('margins'):
        closest = min(competition['margins'], key=lambda step: abs(step['after'] or 0))
        items.append({'kind': 'positions', 'title': 'Positions', 'headline': 'No change', 'tone': 'flat',
                      'text': f"No operator changes position. The closest are {label(closest['operator'])} and {label(closest['next'])}, "
                              f"{closest['before']:,.1f} points apart before and {closest['after']:,.1f} after."})
    flips = [name for name, cell in ((part['gap'].get(environment) or {}).get('total') or {}).items() if cell.get('flip')]
    if flips:
        items.append({'kind': 'flips', 'title': 'Against the reference', 'headline': f'{len(flips)} change side', 'tone': 'loss',
                      'text': f"{_listed([label(name) for name in flips])} goes from ahead of {label(part['reference'])} to behind it, or the other way round."})
    drivers = part['drivers'].get(environment) or {}
    if drivers and largest >= MATERIAL:
        name = max(drivers, key=lambda key: abs(drivers[key]['total'] or 0))
        causes = {cause: value for cause, value in drivers[name]['causes'].items() if abs(value or 0) >= MATERIAL}
        if causes:
            text = ', '.join(f'{CAUSE_LABELS[cause]} {_signed(value)}' for cause, value in sorted(causes.items(), key=lambda item: -abs(item[1])))
            top = max(causes, key=lambda cause: abs(causes[cause]))
            items.append({'kind': 'cause', 'title': 'What causes it', 'headline': CAUSE_LABELS[top], 'tone': 'neutral',
                          'text': f"For {label(name)}, the operator that moves most ({_signed(drivers[name]['total'])}): {text}."})
    exposure = ((part['exposure'].get(environment) or {}).get('operators')) or {}
    correlated = {name: item for name, item in exposure.items() if item.get('r') is not None and len(item.get('points') or []) >= MIN_CORRELATION_POINTS
                  and abs(item['r']) >= STRONG_CORRELATION}
    if correlated:
        name = max(correlated, key=lambda key: abs(correlated[key]['r']))
        value = correlated[name]['r']
        items.append({'kind': 'exposure', 'title': 'With or against its strengths', 'headline': f'r = {value:+.2f}', 'tone': 'gain' if value > 0 else 'loss',
                      'text': f"The points the methodology moves go {'towards' if value > 0 else 'away from'} the KPIs where {label(name)} beats the mean of the operators "
                              f"({strength_words(value)} correlation over {len(correlated[name]['points'])} KPIs)."})
    categories = [row for row in part['categories'].get(environment) or [] if row['peak'] >= MATERIAL]
    if categories:
        top = max(categories, key=lambda row: row['peak'])
        items.append({'kind': 'category', 'title': 'Category that moves most', 'headline': str(top['category']), 'tone': 'neutral',
                      'text': f"Up to {top['peak']:,.1f} points for an operator."})
    kpis = [row for row in part['kpis'].get(environment) or [] if row['peak'] >= MATERIAL]
    if kpis:
        items.append({'kind': 'kpi', 'title': 'KPI that moves most', 'headline': str(kpis[0]['kpi']), 'tone': 'neutral',
                      'text': f"Up to {kpis[0]['peak']:,.1f} points for an operator."})
    where = (areas or {}).get('operators') or {}
    if where:
        hit = [(name, item) for name, item in where.items() if item.get('worst') and item['worst']['value'] <= -MATERIAL]
        if hit:
            name, item = min(hit, key=lambda entry: entry[1]['worst']['value'])
            items.append({'kind': 'where', 'title': 'Where it hits most', 'headline': str(item['worst']['name']), 'tone': 'loss',
                          'text': f"{label(name)} loses {abs(item['worst']['value']):,.2f} National points in {item['worst']['name']}. "
                                  f"{(item.get('concentration') or 0) * 100:,.0f}% of its movement is in {item.get('concentration_areas')} of its {item.get('count')} {(areas or {}).get('field', 'City')} areas."})
    swaps = [(level, sum(row['leader_before'] != row['leader_after'] for row in rows_by_environment.get(environment) or []), len(rows_by_environment.get(environment) or []))
             for level, rows_by_environment in part['areas'].items()]
    swaps = [item for item in swaps if item[1]]
    if swaps:
        level, count, total = swaps[-1]
        items.append({'kind': 'leaders', 'title': 'New leaders', 'headline': f'{count} of {total}', 'tone': 'neutral',
                      'text': f'The leader changes in {count} of {total} {level} areas.'})
    serving = (part.get('serving') or {}).get('Vendor', {}).get(environment) or []
    if serving and largest >= MATERIAL:
        rows = [(row['name'], name, cell['delta']) for row in serving for name, cell in row['operators'].items() if cell.get('delta') is not None]
        if rows:
            vendor, name, delta = max(rows, key=lambda item: abs(item[2]))
            if abs(delta) >= MATERIAL:
                items.append({'kind': 'vendor', 'title': 'Vendor of the serving cells', 'headline': str(vendor), 'tone': 'gain' if delta > 0 else 'loss',
                              'text': f'The largest move falls on the tests of {label(name)} served by {vendor}: {_signed(delta)} National points.'})
    stability = (part.get('stability') or {}).get('summary') or {}
    usable = [item for item in stability.values() if item['campaigns'] >= 2]
    if usable:
        total = max(item['campaigns'] for item in usable)
        steady = [name for name, item in stability.items() if item['campaigns'] >= 2 and (item['up'] == item['campaigns'] or item['down'] == item['campaigns'])]
        items.append({'kind': 'stability', 'title': 'Is it stable?', 'headline': f'{total} campaigns', 'tone': 'neutral',
                      'text': (f"On the tests of {total} campaigns, {_listed([label(name) for name in steady])} always moves the same way."
                               if steady else f'On the tests of {total} campaigns, no operator always moves the same way.')})
    return items
