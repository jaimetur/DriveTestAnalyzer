"""Generated comments of PPT Dashboard slides: the facts of the charts of a slide, their findings and their sentences.

The comments are written from the models the viewer draws (the same filters, splits, hidden values and Operator Maps),
never from pixels: a CDF or histogram gives the exact median, tail percentiles and class shares of each series, the
average and median bars their value and samples, and the 100%, threshold and distribution stacked bars the share of
each class. The findings compare the latest campaign with the previous one and each operator with the leader, from the
point of view of the Focus operators of the Operator Maps, and name a group only with enough samples. The rules engine
writes them offline; the LLM writers added later receive the same facts and fall back to these sentences.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.modules.cdr_reporting import _outcome_kind
from src.modules.column_names import campaign_sort_key, column_identity, compact_campaign_value
from src.modules.network_insights_findings import _join

ENGINE_RULES = 'rules'
ENGINES = (ENGINE_RULES,)
# A group needs this many samples for a comment to name it (as the Key Findings of Network Insights).
MIN_GROUP_SAMPLES = 10
# Comments written for one slide; the narrow box of the "comments right" layouts holds fewer.
MAX_SLIDE_COMMENTS = 4
MAX_NARROW_SLIDE_COMMENTS = 3
# Focus operators commented in each group of a chart, whose comments come before those of the other operators.
MAX_FOCUS_SUBJECTS = 2
FOCUS_BONUS = 1.5
# Chart models the rules can read (CDF Line, Multi KPI CDF, histograms, 100%, threshold and distribution stacked bars,
# average and median bars).
SUPPORTED_MODEL_TYPES = frozenset({'cdf', 'multi_cdf', 'mean_bar', 'status_100', 'distribution'})
OPERATOR_DIMENSIONS = frozenset({'operator', 'subscriber', 'operatorvendor'})
CAMPAIGN_DIMENSIONS = frozenset({'campaign'})
THRESHOLD_STATE = re.compile(r'^\s*(<|≥|>=)\s*(-?\d+(?:\.\d+)?)\s*$')


@dataclass(frozen=True)
class KpiSemantics:
    """How the comments read one KPI: its unit, whether higher is better and the smallest change that matters."""
    name: str
    unit: str = ''
    direction: int = 0  # 1 higher is better, -1 lower is better, 0 unknown
    step: float | None = None  # smallest absolute change that matters; otherwise ``relative``
    relative: float = 0.05
    digits: int | None = None


# Matched in order on the KPI name (case and underscores ignored): pattern, unit, direction, step, digits.
SEMANTIC_RULES: tuple[tuple[str, str, int, float | None, int | None], ...] = (
    (r'score', '', 1, None, 2),
    (r'rsrp', 'dBm', 1, 1.0, 1),
    (r'rsrq', 'dB', 1, 0.5, 1),
    (r'sinr|snr', 'dB', 1, 1.0, 1),
    (r'\blq\b|\bmos\b|polqa', '', 1, 0.1, 2),
    (r'error|loss|bler|drop|fail', '', -1, None, None),
    (r'duration|time|rtt|latency|delay|jitter|ttfp', '', -1, None, None),
    (r'data rate|throughput|tput|bitrate|speed|bandwidth|\bbw\b|\brbs?\b', '', 1, None, None),
)
UNIT_TOKENS = ((r'\bmhz\b', 'MHz'), (r'\bmbps\b|\bmbit', 'Mbps'), (r'\bkbps\b|\bkbit', 'kbps'), (r'\bms\b', 'ms'))


def kpi_semantics(metric: str) -> KpiSemantics:
    """The semantics of a KPI from its name (NR_RSRP, Mean Data Rate, Call_Setup_Time…); unknown KPIs stay neutral."""
    name = re.sub(r'\s+', ' ', str(metric or '').replace('_', ' ')).strip()
    folded = name.casefold()
    for pattern, unit, direction, step, digits in SEMANTIC_RULES:
        if re.search(pattern, folded):
            break
    else:
        unit, direction, step, digits = '', 0, None, None
    if not unit:
        unit = next((label for token, label in UNIT_TOKENS if re.search(token, folded)), '')
    return KpiSemantics(name or 'value', unit, direction, step, digits=digits)


@dataclass
class Record:
    """One series, bar or stacked bar of a chart: its labels by dimension, its compared value and samples."""
    labels: dict[str, str]
    value: float
    samples: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChartFacts:
    """What one chart shows, ready to be compared: ``stat`` charts compare a statistic (median, mean) of a KPI,
    ``share`` charts the share of one class (failures, a threshold, a bucket)."""
    chart_index: int
    title: str
    family: str
    semantics: KpiSemantics
    statistic: str
    records: list[Record]
    direction: int
    bucket_edges: list[float] = field(default_factory=list)


@dataclass
class Finding:
    text: str
    score: float
    kind: str


def needs_rebuild(model: dict[str, Any]) -> bool:
    """Whether a cached chart model predates the facts of the generated comments (its dimensions and statistics)."""
    kind = model.get('type')
    if kind == 'multi_cdf':
        return any('dimensions' not in panel for panel in model.get('panels') or [])
    return kind in SUPPORTED_MODEL_TYPES and 'dimensions' not in model


def _format(value: float, digits: int | None = None) -> str:
    """A figure as the comments write it: a true minus sign, thousands separators and no trailing zeros."""
    if digits is None:
        magnitude = abs(value)
        digits = 0 if magnitude >= 100 else 1 if magnitude >= 10 else 2
    text = f'{value:,.{digits}f}'
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return '0' if text in {'-0', ''} else text.replace('-', '−')


def _with_unit(text: str, semantics: KpiSemantics, *, difference: bool = False) -> str:
    """A figure with its unit; a difference of dBm values is in dB."""
    unit = 'dB' if difference and semantics.unit == 'dBm' else semantics.unit
    return f'{text} {unit}' if unit else text


def _percent(share: float) -> str:
    return f'{_format(share * 100, 1)}%'


def _points(delta: float) -> str:
    text = _format(abs(delta) * 100, 1)
    return f'{"+" if delta > 0 else "−" if delta < 0 else "±"}{text} pp'


def _campaign(value: str) -> str:
    return compact_campaign_value(value) or str(value)


def _hidden(labels: dict[str, str], hidden: set[str], shown: set[str]) -> bool:
    """Whether the viewer hides a record: one of its values (or of their " · " levels) is a hidden legend item."""
    for value in labels.values():
        if value in shown:
            continue
        if value in hidden or any(part in hidden and part not in shown for part in value.split(' · ')):
            return True
    return False


def _labels(key: Iterable[Any], dimensions: list[list[str]]) -> dict[str, str]:
    """The values of a model key by template dimension (a level of several dimensions joins its values with " · ")."""
    labels: dict[str, str] = {}
    for value, names in zip(key, dimensions):
        names = [name for name in names if name and not name.startswith('__')]
        text = str(value)
        if not names or text == '(all)':
            continue
        parts = text.split(' · ') if len(names) > 1 else [text]
        if len(parts) != len(names):
            labels[' × '.join(names)] = text
            continue
        labels.update(zip(names, parts))
    return labels


def _stat_facts(chart_index: int, title: str, model: dict[str, Any], hidden: set[str], shown: set[str]) -> ChartFacts | None:
    """A CDF or histogram: the median of each visible series, with its tail percentiles and class shares."""
    semantics = kpi_semantics(model.get('metric') or title)
    dimensions = model.get('dimensions') or []
    operator = str(model.get('operator') or '')
    records = []
    for series in model.get('series') or []:
        stats = series.get('stats') or {}
        if 'p50' not in stats:
            continue
        labels = _labels(series.get('key') or [], dimensions)
        if operator and not any(column_identity(name) in OPERATOR_DIMENSIONS for name in labels):
            labels = {'Operator': operator, **labels}
        if _hidden(labels, hidden, shown):
            continue
        records.append(Record(labels, float(stats['p50']), int(stats.get('n') or 0), {
            'p10': stats.get('p10'), 'p90': stats.get('p90'), 'mean': stats.get('mean'),
            'bucket_shares': stats.get('bucket_shares') or [],
        }))
    if not records:
        return None
    return ChartFacts(chart_index, title, 'stat', semantics, 'median', records, semantics.direction,
                      [float(edge) for edge in model.get('bucket_edges') or []])


def _bar_facts(chart_index: int, title: str, model: dict[str, Any], hidden: set[str], shown: set[str]) -> ChartFacts | None:
    """Average or median bars: the value and samples of each visible bar."""
    aggregation = str(model.get('aggregation') or 'mean')
    if aggregation not in {'mean', 'median'}:
        return None
    semantics = kpi_semantics(model.get('metric') or title)
    dimensions = model.get('dimensions') or []
    records = []
    for bar in model.get('bars') or []:
        labels = _labels(bar.get('key') or [], dimensions)
        if bar.get('value') is None or _hidden(labels, hidden, shown):
            continue
        samples = bar.get('samples')
        records.append(Record(labels, float(bar['value']), int(samples) if samples is not None else None))
    if not records:
        return None
    return ChartFacts(chart_index, title, 'stat', semantics, aggregation, records, semantics.direction)


def _share_target(states: list[str], kpi: KpiSemantics, records: list[tuple[dict[str, str], list[float], int]],
                  hidden: set[str]) -> tuple[list[int], str, int] | None:
    """The class a stacked chart is read by: the share reaching a threshold, the failures, or else its largest class."""
    visible = [index for index, state in enumerate(states) if state not in hidden]
    if not visible:
        return None
    thresholds = {index: THRESHOLD_STATE.match(states[index]) for index in visible}
    below = [index for index, match in thresholds.items() if match and match.group(1) == '<']
    above = [index for index, match in thresholds.items() if match and match.group(1) != '<']
    if below and above:
        threshold = thresholds[above[0]].group(2)
        if kpi.direction < 0:
            return below, f'{kpi.name} < {threshold}', 1
        return above, f'{kpi.name} ≥ {threshold}', 1 if kpi.direction > 0 else 0
    failures = [index for index in visible if _outcome_kind(states[index]) == 'failure']
    if failures:
        return failures, ' + '.join(states[index] for index in failures), -1
    totals = {index: sum(shares[index] for _labels_, shares, _samples in records if index < len(shares)) for index in visible}
    largest = max(totals, key=totals.get)
    return [largest], states[largest], 0


def _share_facts(chart_index: int, title: str, model: dict[str, Any], kpi_name: str,
                 hidden: set[str], shown: set[str]) -> ChartFacts | None:
    """100%, threshold and distribution stacked bars: the share of the class that reads the chart in each bar."""
    kpi = kpi_semantics(kpi_name or title)
    dimensions = model.get('dimensions') or []
    if model.get('type') == 'distribution':
        states = [str(bucket.get('name') or '') for bucket in model.get('buckets') or []]
        rows = [
            (_labels(key, dimensions), list(shares), int(samples))
            for key, shares, samples in zip(model.get('keys') or [], model.get('cells') or [], model.get('samples') or [])
        ]
    else:
        states = [str(state.get('name') or '') for state in model.get('states') or []]
        rows = [(_labels(record.get('key') or [], dimensions), list(record.get('shares') or []), int(record.get('samples') or 0))
                for record in model.get('records') or []]
    rows = [row for row in rows if not _hidden(row[0], hidden, shown)]
    if not states or not rows:
        return None
    if model.get('type') == 'distribution' and kpi.direction:
        # Buckets go from the lowest values to the highest: the worst class is the first or the last one.
        visible = [index for index, state in enumerate(states) if state not in hidden]
        if not visible:
            return None
        worst = visible[0] if kpi.direction > 0 else visible[-1]
        target = ([worst], states[worst], -1)
    else:
        target = _share_target(states, kpi, rows, hidden)
    if target is None:
        return None
    indexes, label, direction = target
    records = [
        Record(labels, sum(shares[index] for index in indexes if index < len(shares)), samples)
        for labels, shares, samples in rows
    ]
    semantics = KpiSemantics(label, '', direction)
    return ChartFacts(chart_index, title, 'share', semantics, label, records, direction)


def chart_facts(chart_index: int, title: str, kpi: str, model: dict[str, Any],
                hidden: Iterable[str] = (), shown: Iterable[str] = ()) -> list[ChartFacts]:
    """The facts of one chart model (a Multi KPI CDF gives one per KPI); none for the charts the rules cannot read."""
    hidden_items, shown_items = {str(item) for item in hidden}, {str(item) for item in shown}
    kind = model.get('type')
    title = str(title or model.get('title') or '')
    if kind == 'cdf':
        facts = _stat_facts(chart_index, title, model, hidden_items, shown_items)
        return [facts] if facts else []
    if kind == 'multi_cdf':
        return [facts for panel in model.get('panels') or []
                if (facts := _stat_facts(chart_index, str(panel.get('title') or title), panel, hidden_items, shown_items))]
    if kind == 'mean_bar':
        facts = _bar_facts(chart_index, title, model, hidden_items, shown_items)
        return [facts] if facts else []
    if kind in {'status_100', 'distribution'}:
        facts = _share_facts(chart_index, title, model, kpi, hidden_items, shown_items)
        return [facts] if facts else []
    return []


def _roles(records: list[Record]) -> tuple[str | None, str | None, list[str]]:
    """The Operator and Campaign dimensions of a chart and the other ones (its groups: Test_Name, G_Level_4…)."""
    names = list(dict.fromkeys(name for record in records for name in record.labels))
    operator = next((name for name in names if column_identity(name) in OPERATOR_DIMENSIONS), None)
    campaign = next((name for name in names if column_identity(name) in CAMPAIGN_DIMENSIONS), None)
    return operator, campaign, [name for name in names if name not in {operator, campaign}]


def _eligible(record: Record | None) -> bool:
    return record is not None and (record.samples is None or record.samples >= MIN_GROUP_SAMPLES)


def _meaningful(facts: ChartFacts, first: Record, second: Record) -> bool:
    """Whether two values differ enough to be named: a practical minimum, and for shares also a significance test."""
    delta = second.value - first.value
    if facts.family == 'share':
        if abs(delta) < 0.01:
            return False
        if first.samples and second.samples:
            pooled = (first.value * first.samples + second.value * second.samples) / (first.samples + second.samples)
            spread = math.sqrt(max(pooled * (1 - pooled), 1e-12) * (1 / first.samples + 1 / second.samples))
            return abs(delta) / spread >= 1.96
        return True
    if facts.semantics.step is not None:
        return abs(delta) >= facts.semantics.step
    return abs(delta) >= facts.semantics.relative * max(abs(first.value), abs(second.value), 1e-9)


def _figure(facts: ChartFacts, value: float, unit: bool = True) -> str:
    if facts.family == 'share':
        return _percent(value)
    text = _format(value, facts.semantics.digits)
    return _with_unit(text, facts.semantics) if unit else text


def _gap_size(facts: ChartFacts, first: float, second: float) -> float:
    """How far apart two values are, in the measure the comments write: an absolute difference for shares and dB-like
    KPIs, a fraction of the larger value otherwise."""
    if facts.family == 'share' or facts.semantics.step is not None:
        return abs(second - first)
    return abs(second - first) / max(abs(first), abs(second), 1e-9)


def _gap(facts: ChartFacts, first: float, second: float) -> str:
    """How far apart two values are: points for shares, the unit for dB-like KPIs, a percentage otherwise."""
    size = _gap_size(facts, first, second)
    if facts.family == 'share':
        return _points(size).lstrip('+')
    if facts.semantics.step is not None:
        return _with_unit(_format(size, facts.semantics.digits), facts.semantics, difference=True)
    return f'{_format(size * 100, 0)}%'


def _subject(facts: ChartFacts, operator: str) -> str:
    if facts.family == 'share':
        return f'{operator} share of {facts.statistic}' if operator else f'Share of {facts.statistic}'
    # A KPI already named by its statistic (the mean of Mean Data Rate, the median of Interactivity RTT Median) does not
    # name it twice.
    words = r'\b(mean|avg|average)\b' if facts.statistic == 'mean' else rf'\b{re.escape(facts.statistic)}\b'
    named = re.search(words, facts.semantics.name, re.I)
    metric = facts.semantics.name if named else f'{facts.statistic} {facts.semantics.name}'
    return f'{operator} {metric}' if operator else metric[:1].upper() + metric[1:]


def _change(facts: ChartFacts, operator: str, latest: Record, previous: Record, previous_campaign: str) -> Finding:
    """The change of one operator since the previous campaign."""
    subject = _subject(facts, operator)
    delta = latest.value - previous.value
    if not _meaningful(facts, previous, latest):
        return Finding(f'{subject} is stable vs {previous_campaign} ({_figure(facts, latest.value)}).', 1.2, 'stable')
    if facts.family == 'share':
        verb = 'rises' if delta > 0 else 'falls'
        text = (f'{subject} {verb} from {_figure(facts, previous.value)} to {_figure(facts, latest.value)} '
                f'vs {previous_campaign} ({_points(delta)}).')
        threshold = 0.01
    else:
        if facts.direction:
            verb = 'improves' if delta * facts.direction > 0 else 'degrades'
        else:
            verb = 'rises' if delta > 0 else 'falls'
        text = (f'{subject} {verb} by {_gap(facts, previous.value, latest.value)} vs {previous_campaign} '
                f'({_figure(facts, previous.value, unit=False)} → {_figure(facts, latest.value)}).')
        threshold = facts.semantics.step or facts.semantics.relative * max(abs(previous.value), 1e-9)
    return Finding(text, 3 + min(abs(delta) / max(threshold, 1e-12), 3), 'change')


def _ranked(facts: ChartFacts, records: dict[str, Record]) -> list[str]:
    """Operators from the best to the worst (the highest first when the KPI has no better side)."""
    direction = facts.direction or 1
    return sorted(records, key=lambda operator: -records[operator].value * direction)


def _position(facts: ChartFacts, operator: str, latest: dict[str, Record], previous: dict[str, Record],
              previous_campaign: str | None) -> Finding | None:
    """Where one operator stands against the leader (or how far it leads the next one)."""
    ranking = _ranked(facts, latest)
    if len(ranking) < 2 or operator not in latest:
        return None
    best = ranking[0]
    value = latest[operator].value
    lead_word = 'leads' if facts.direction else 'is highest'
    if facts.family == 'share':
        side = 'highest' if facts.direction >= 0 else 'lowest'
        other = ranking[1] if operator == best else best
        if not _meaningful(facts, latest[other], latest[operator]):
            return Finding(f'{operator} is on par with {other} in share of {facts.statistic} '
                           f'({_figure(facts, value)} vs {_figure(facts, latest[other].value)}).', 1.6, 'position')
        if operator == best:
            return Finding(f'{operator} has the {side} share of {facts.statistic} ({_figure(facts, value)}); '
                           f'next: {other} ({_figure(facts, latest[other].value)}).', 2.4, 'position')
        return Finding(f'{best} has the {side} share of {facts.statistic} ({_figure(facts, latest[best].value)}) '
                       f'vs {_figure(facts, value)} for {operator}.', 2.2, 'position')
    statistic = f'the {facts.statistic}'
    if operator == best:
        second = ranking[1]
        if not _meaningful(facts, latest[second], latest[operator]):
            return Finding(f'{operator} and {second} are on par at {statistic} ({_figure(facts, value, unit=False)} vs '
                           f'{_figure(facts, latest[second].value)}).', 1.6, 'position')
        return Finding(f'{operator} {lead_word} at {statistic} ({_figure(facts, value)}), '
                       f'{_gap(facts, latest[second].value, value)} ahead of {second}.', 2.6, 'position')
    best_value = latest[best].value
    if not _meaningful(facts, latest[best], latest[operator]):
        return Finding(f'{operator} is on par with {best} at {statistic} ({_figure(facts, value, unit=False)} vs '
                       f'{_figure(facts, best_value)}).', 1.8, 'position')
    text = (f'{best} {lead_word} at {statistic} ({_figure(facts, best_value)}); {operator} trails by '
            f'{_gap(facts, value, best_value)} ({_figure(facts, value)})')
    if previous_campaign and operator in previous and best in previous:
        before = _gap_size(facts, previous[operator].value, previous[best].value)
        after = _gap_size(facts, value, best_value)
        minimum = 0.01 if facts.family == 'share' else facts.semantics.step or facts.semantics.relative
        if abs(after - before) >= minimum:
            trend = 'narrows' if after < before else 'widens'
            text += (f'; the gap {trend} from {_gap(facts, previous[operator].value, previous[best].value)} '
                     f'in {previous_campaign}')
    return Finding(text + '.', 2.4, 'position')


def _tail(facts: ChartFacts, operator: str, latest: dict[str, Record], previous: dict[str, Record],
          previous_campaign: str | None) -> Finding | None:
    """The weak tail of a distribution: the share in its worst class, or else its P10 (P90 when lower is better)."""
    if facts.family != 'stat' or not facts.direction or operator not in latest:
        return None
    unit = facts.semantics
    if facts.bucket_edges:
        position = 0 if facts.direction > 0 else len(facts.bucket_edges)
        edge = facts.bucket_edges[0] if facts.direction > 0 else facts.bucket_edges[-1]
        label = (f'below {_with_unit(_format(edge, unit.digits), unit)}' if facts.direction > 0
                 else f'at or above {_with_unit(_format(edge, unit.digits), unit)}')

        def share(record: Record) -> float | None:
            shares = record.extra.get('bucket_shares') or []
            return float(shares[position]) if position < len(shares) else None

        value = share(latest[operator])
        if value is None:
            return None
        text = f'Samples {label}: {f"{operator} " if operator else ""}{_percent(value)}'
        before = share(previous[operator]) if previous_campaign and operator in previous else None
        if before is not None:
            text += f' ({_points(value - before)} vs {previous_campaign})'
        shares = {name: share(record) for name, record in latest.items()}
        worst = max((name for name in shares if shares[name] is not None), key=lambda name: shares[name])
        if worst != operator:
            text += f'; highest: {worst} ({_percent(shares[worst])})'
        return Finding(text + '.', 2.0, 'tail')
    percentile = 'p10' if facts.direction > 0 else 'p90'
    values = {name: record.extra.get(percentile) for name, record in latest.items() if record.extra.get(percentile) is not None}
    if operator not in values or len(values) < 2:
        return None
    best = max(values, key=lambda name: values[name] * facts.direction)
    label = percentile.upper()
    if best == operator:
        return Finding(f'{operator} also has the best tail ({label} {_figure(facts, values[operator])}).', 1.4, 'tail')
    return Finding(f'Tail ({label}): {operator} {_figure(facts, values[operator], unit=False)} vs '
                   f'{best} {_figure(facts, values[best])}.', 1.8, 'tail')


def chart_findings(facts: ChartFacts, focus_operators: Iterable[str] = ()) -> list[Finding]:
    """The findings of one chart, group by group: the change of the Focus operators (or of the leader) since the
    previous campaign, their position against the leader, the weak tail, the largest move of the others and the
    groups with too few samples to be named."""
    focus = {str(name).strip().casefold() for name in focus_operators if str(name or '').strip()}
    operator_key, campaign_key, context_keys = _roles(facts.records)
    groups: dict[tuple[str, ...], list[Record]] = {}
    for record in facts.records:
        groups.setdefault(tuple(record.labels.get(name, '') for name in context_keys), []).append(record)
    findings: list[Finding] = []
    for context, records in groups.items():
        prefix = ' · '.join(value for value in context if value)
        prefix = f'{prefix}: ' if prefix else ''
        campaigns = sorted({record.labels[campaign_key] for record in records if campaign_key in record.labels},
                           key=campaign_sort_key) if campaign_key else []
        latest_campaign = campaigns[-1] if campaigns else None
        previous_campaign = campaigns[-2] if len(campaigns) > 1 else None

        def by_operator(campaign: str | None) -> dict[str, Record]:
            return {
                (record.labels.get(operator_key, '') if operator_key else ''): record
                for record in records
                if campaign is None or record.labels.get(campaign_key) == campaign
            }

        latest_all = by_operator(latest_campaign)
        previous_all = by_operator(previous_campaign) if previous_campaign else {}
        latest = {name: record for name, record in latest_all.items() if _eligible(record)}
        previous = {name: record for name, record in previous_all.items() if _eligible(record)}
        if not latest:
            continue
        shown_previous = _campaign(previous_campaign) if previous_campaign else None
        subjects = [name for name in latest if name.casefold() in focus][:MAX_FOCUS_SUBJECTS]
        bonus = FOCUS_BONUS if subjects else 0.0
        if not subjects:
            subjects = _ranked(facts, latest)[:1]
        group_findings: list[Finding] = []
        for operator in subjects:
            found = []
            if previous_campaign and operator in previous:
                found.append(_change(facts, operator, latest[operator], previous[operator], shown_previous))
            if operator_key and (position := _position(facts, operator, latest, previous, shown_previous)):
                found.append(position)
            if tail := _tail(facts, operator, latest, previous, shown_previous):
                found.append(tail)
            group_findings.extend(Finding(finding.text, finding.score + bonus, finding.kind) for finding in found)
        if previous_campaign and operator_key:
            movers = [
                (abs(latest[name].value - previous[name].value), name) for name in latest
                if name not in subjects and name in previous and _meaningful(facts, previous[name], latest[name])
            ]
            if movers:
                _magnitude, mover = max(movers)
                change = _change(facts, mover, latest[mover], previous[mover], shown_previous)
                group_findings.append(Finding(change.text, min(change.score, 3) - 1.2, 'mover'))
        few = [name for name, record in latest_all.items() if name and not _eligible(record)]
        if few:
            counts = _join([f'{name} ({latest_all[name].samples})' for name in few])
            group_findings.append(Finding(f'Too few samples to compare {counts}: indicative results only.', 0.6, 'samples'))
        findings.extend(Finding(prefix + finding.text, finding.score, finding.kind) for finding in group_findings)
    return findings


def comment_limit(layout: str) -> int:
    return MAX_NARROW_SLIDE_COMMENTS if re.search(r'\bcomments\s+right\b', str(layout or ''), re.I) else MAX_SLIDE_COMMENTS


def slide_comments(charts: Iterable[dict[str, Any]], *, focus_operators: Iterable[str] = (), layout: str = '',
                   engine: str = ENGINE_RULES) -> list[dict[str, Any]]:
    """The comments of one slide from its visible charts.

    Each chart is ``{'index', 'title', 'kpi', 'model', 'hidden', 'shown'}``. Every chart gets its best comment first,
    then the best remaining ones fill the slide up to its limit, each comment once.
    """
    if engine not in ENGINES:
        raise ValueError(f'Unknown comment engine: {engine}.')
    focus = list(focus_operators)
    ranked: list[list[tuple[Finding, dict[str, Any]]]] = []
    for chart in charts:
        findings = []
        for facts in chart_facts(int(chart['index']), str(chart.get('title') or ''), str(chart.get('kpi') or ''),
                                 chart.get('model') or {}, chart.get('hidden') or (), chart.get('shown') or ()):
            findings.extend((finding, {'chart_index': facts.chart_index, 'chart_title': facts.title})
                            for finding in chart_findings(facts, focus))
        if findings:
            ranked.append(sorted(findings, key=lambda item: -item[0].score))
    limit = comment_limit(layout)
    chosen: list[tuple[Finding, dict[str, Any]]] = []
    seen: set[str] = set()

    def take(item: tuple[Finding, dict[str, Any]]) -> None:
        if len(chosen) < limit and item[0].text not in seen:
            seen.add(item[0].text)
            chosen.append(item)

    for findings in sorted(ranked, key=lambda items: -items[0][0].score):
        take(findings[0])
    for item in sorted((item for findings in ranked for item in findings[1:]), key=lambda item: -item[0].score):
        take(item)
    return [{'text': finding.text, 'kind': finding.kind, **source} for finding, source in chosen]
