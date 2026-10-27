"""Generated comments of PPT Dashboard slides: the facts of the charts of a slide, their findings and their sentences.

The comments are written from the models the viewer draws (the same filters, splits, hidden values and Operator Maps),
never from pixels: a CDF or histogram gives the exact median, tail percentiles and class shares of each series, the
average and median bars their value and samples, the 100%, threshold and distribution stacked bars and the failure
counts the share of each class, a scatter the rank correlation of its two measures, a map the share of its weakest class
and where it gathers, and a table its highest and lowest rows. The findings compare the latest campaign with the
previous one, each operator with the leader, in Multivendor the vendors of each operator and, with the NR Mode in a
split, each operator in SA with itself in NSA, from the point of view of the Focus operators of the Operator Maps, and
name a group only with enough samples; charts of one slide are also read together (LTE against NR, SA against NSA, one
operator per chart). The rules engine writes them offline; the LLM writers receive the same facts and fall back to these
sentences.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from src.modules.cdr_reporting import _outcome_kind, _range_bucket_sort_key
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
# Chart models the rules can read: every chart type of the PPT Templates.
SUPPORTED_MODEL_TYPES = frozenset({
    'cdf', 'multi_cdf', 'mean_bar', 'status_100', 'distribution', 'failure_count', 'scatter', 'map', 'table',
})
# Models that carry the dimensions of their keys (tables are read from their cells).
DIMENSIONED_MODEL_TYPES = SUPPORTED_MODEL_TYPES - {'multi_cdf', 'table'}
OPERATOR_DIMENSIONS = frozenset({'operator', 'subscriber'})
VENDOR_DIMENSIONS = frozenset({'operatorvendor', 'vendor'})
CAMPAIGN_DIMENSIONS = frozenset({'campaign'})
NR_MODE_DIMENSIONS = frozenset({'nrmode'})
# The NR Mode a chart title names (CDF_SA, DL Throughput NSA).
NR_MODE_TITLE_TOKENS = re.compile(r'(?:^|[^A-Za-z])(NSA|SA)(?![A-Za-z])')
BUCKET_DIMENSIONS = frozenset({'valuebucket', 'ratebucket'})
# Vendor groups that are not a vendor (multivendor comparisons leave them out of the vendor comments).
NOT_VENDORS = frozenset({'mixed', 'other', 'others', 'unknown', '(blank)', ''})
TECHNOLOGY_TOKENS = re.compile(r'\b(lte|nr|4g|5g)\b', re.I)
# A scatter names a relation from this rank correlation, and calls it weak below WEAK_CORRELATION.
STRONG_CORRELATION = 0.3
WEAK_CORRELATION = 0.1
MIN_RELATION_SAMPLES = 30
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
    # Relations (scatter), maps and tables: what the family needs besides its records.
    extra: dict[str, Any] = field(default_factory=dict)


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
    return kind in DIMENSIONED_MODEL_TYPES and 'dimensions' not in model


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


def _bucket_bounds(name: str) -> tuple[float | None, float | None] | None:
    """The range of a class named as the charts name them (``< -110``, ``-110 to -100``, ``20+``, ``below-110``,
    ``Above``); None for a name that is not a range."""
    text = str(name or '').strip()
    number = r'-?\d+(?:\.\d+)?'
    if match := re.fullmatch(rf'below\s*({number})', text, re.I):
        return None, float(match.group(1))
    if text.casefold() == 'above':
        return float('inf'), None
    if match := re.fullmatch(rf'<\s*({number})', text):
        return None, float(match.group(1))
    if match := re.fullmatch(rf'({number})(?:-| to )({number})', text):
        return float(match.group(1)), float(match.group(2))
    if match := re.fullmatch(rf'({number})\s*\+', text):
        return float(match.group(1)), None
    return None


def _bucket_order(names: list[str]) -> list[int] | None:
    """The classes from the lowest values to the highest, or None when one of them is not a range."""
    keys = []
    for name in names:
        bounds = _bucket_bounds(name)
        if bounds is None:
            return None
        low, high = bounds
        keys.append((high if low is None else low, 0 if low is None else 1 if high is not None else 2))
    return sorted(range(len(names)), key=lambda index: keys[index])


def _bucket_phrase(name: str, kpi: KpiSemantics) -> str:
    """A class as the comments read it: ``NR RSRP below −110 dBm``, ``Mean Data Rate 5 to 20``."""
    bounds = _bucket_bounds(name)
    if bounds is None:
        return f'{kpi.name} in {name}'
    low, high = bounds
    if low is None:
        return f'{kpi.name} below {_with_unit(_format(high, kpi.digits), kpi)}'
    if high is None:
        return f'{kpi.name} in the top class' if math.isinf(low) else f'{kpi.name} at or above {_with_unit(_format(low, kpi.digits), kpi)}'
    return f'{kpi.name} {_format(low, kpi.digits)} to {_with_unit(_format(high, kpi.digits), kpi)}'


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
    order = _bucket_order(states) if model.get('type') == 'distribution' and kpi.direction else None
    if order:
        # Buckets are read from the lowest values to the highest: the worst class is the first or the last one.
        visible = [index for index in order if states[index] not in hidden]
        if not visible:
            return None
        worst = visible[0] if kpi.direction > 0 else visible[-1]
        target = ([worst], _bucket_phrase(states[worst], kpi), -1)
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


def _failure_facts(chart_index: int, title: str, model: dict[str, Any], hidden: set[str], shown: set[str]) -> ChartFacts | None:
    """Count Stacked Horizontal Bars: the share of failed and dropped tests of each bar among all its tests."""
    states = [str(state.get('name') or '') for state in model.get('states') or []] or ['Failed', 'Dropped']
    counted = [index for index, state in enumerate(states) if state not in hidden]
    dimensions = model.get('dimensions') or []
    if model.get('mode') == 'hierarchy':
        rows = [(record.get('key') or [], record.get('counts') or [], record.get('tests') or 0)
                for record in model.get('records') or []]
    else:
        rows = [(row.get('key') or [], row.get('values') or [], tests)
                for row, tests in zip(model.get('rows') or [], model.get('tests') or [])]
    records = []
    for key, counts, tests in rows:
        labels = _labels(key, dimensions)
        if not tests or _hidden(labels, hidden, shown):
            continue
        failures = sum(int(counts[index]) for index in counted if index < len(counts))
        records.append(Record(labels, failures / int(tests), int(tests), {'failures': failures}))
    if not records or not counted:
        return None
    label = ' + '.join(states[index] for index in counted)
    return ChartFacts(chart_index, title, 'share', KpiSemantics(label, '', -1), label, records, -1)


def _relation_facts(chart_index: int, title: str, model: dict[str, Any], hidden: set[str], shown: set[str]) -> ChartFacts | None:
    """Scatter: the rank correlation of each visible series and its KPI in the lowest and highest quarter of the other
    measure."""
    y_kpi = kpi_semantics(model.get('y_label') or title)
    x_kpi = kpi_semantics(model.get('x_label') or '')
    dimensions = model.get('dimensions') or []
    records = []
    for series in model.get('series') or []:
        stats = series.get('stats') or {}
        labels = _labels(series.get('key') or [], dimensions)
        if stats.get('spearman') is None or _hidden(labels, hidden, shown) or str(series.get('name')) in hidden:
            continue
        records.append(Record(labels, float(stats['spearman']), int(stats.get('n') or 0), stats))
    if not records:
        return None
    return ChartFacts(chart_index, title, 'relation', y_kpi, 'Spearman ρ', records, 0, extra={'x': x_kpi})


def _map_facts(chart_index: int, title: str, model: dict[str, Any], hidden: set[str], shown: set[str]) -> ChartFacts | None:
    """Map: the share of the weakest class of its colour measure and the areas where it gathers."""
    kpi = kpi_semantics(model.get('colour_metric') or '')
    series = [item for item in model.get('series') or [] if str(item.get('name')) not in hidden]
    names = [str((item.get('key') or [item.get('name')])[-1]) for item in series]
    order = _bucket_order(names) if kpi.direction else None
    total = sum(int(item.get('samples') or 0) for item in series)
    if not order or not total:
        return None
    worst = order[0] if kpi.direction > 0 else order[-1]
    records = [Record({'Class': name}, int(item.get('samples') or 0) / total, int(item.get('samples') or 0))
               for name, item in zip(names, series)]
    all_names = [str((item.get('key') or [item.get('name')])[-1]) for item in model.get('series') or []]
    areas = model.get('areas') or {}
    return ChartFacts(chart_index, title, 'map', kpi, _bucket_phrase(names[worst], kpi), records, -1, extra={
        'worst': worst, 'total': total, 'areas': areas,
        'worst_position': all_names.index(names[worst]) if names[worst] in all_names else None,
    })


def _number_cell(value: Any) -> float | None:
    text = str(value or '').replace(',', '').replace('%', '').strip()
    try:
        return float(text)
    except ValueError:
        return None


def _table_facts(chart_index: int, title: str, kpi: str, model: dict[str, Any], hidden: set[str]) -> ChartFacts | None:
    """Table: the highest and lowest rows of each numeric column."""
    headers = [str(header) for header in model.get('headers') or []]
    rows = [row for row in model.get('rows') or [] if row]
    dimensions = int(model.get('row_dimension_count') or 1)
    if len(headers) <= dimensions or len(rows) < 2:
        return None
    records = []
    for row in rows:
        label = ' · '.join(str(cell) for cell in row[:dimensions] if str(cell))
        if label in hidden or any(str(cell) in hidden for cell in row[:dimensions]):
            continue
        values = {headers[index]: number for index in range(dimensions, min(len(row), len(headers)))
                  if (number := _number_cell(row[index])) is not None}
        if values:
            records.append(Record({'Row': label}, 0.0, None, {'values': values,
                                                               'percent': any('%' in str(cell) for cell in row[dimensions:])}))
    if len(records) < 2:
        return None
    columns = [header for header in headers[dimensions:] if sum(header in record.extra['values'] for record in records) >= 2]
    return ChartFacts(chart_index, title, 'table', kpi_semantics(kpi or title), 'value', records, 0, extra={'columns': columns[:3]})


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
    readers = {
        'failure_count': lambda: _failure_facts(chart_index, title, model, hidden_items, shown_items),
        'scatter': lambda: _relation_facts(chart_index, title, model, hidden_items, shown_items),
        'map': lambda: _map_facts(chart_index, title, model, hidden_items, shown_items),
        'table': lambda: _table_facts(chart_index, title, kpi, model, hidden_items),
    }
    facts = readers[kind]() if kind in readers else None
    return [facts] if facts else []


def _roles(records: list[Record]) -> tuple[str | None, str | None, str | None, list[str]]:
    """The Operator, Campaign and Vendor dimensions of a chart and the groups it is read in (the other dimensions, such
    as Test_Name or G_Level_4, and the Vendor). Without Operator, the Vendor of a vendor-only comparison is the
    subject of the comments."""
    names = list(dict.fromkeys(name for record in records for name in record.labels))
    operator = next((name for name in names if column_identity(name) in OPERATOR_DIMENSIONS), None)
    vendor = next((name for name in names if column_identity(name) in VENDOR_DIMENSIONS), None)
    campaign = next((name for name in names if column_identity(name) in CAMPAIGN_DIMENSIONS), None)
    if operator is None and vendor is not None:
        operator, vendor = vendor, None
    return operator, campaign, vendor, [name for name in names if name not in {operator, campaign}]


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


def _metric(facts: ChartFacts) -> str:
    """The statistic and KPI as a sentence names them inside it: ``median NR RSRP``, ``Mean Data Rate``."""
    subject = _subject(facts, '')
    return subject if subject == facts.semantics.name else subject[:1].lower() + subject[1:]


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
    metric = _metric(facts)
    lead = f'leads in {metric}' if facts.direction else f'has the highest {metric}'
    if operator == best:
        second = ranking[1]
        if not _meaningful(facts, latest[second], latest[operator]):
            return Finding(f'{operator} and {second} are on par in {metric} ({_figure(facts, value, unit=False)} vs '
                           f'{_figure(facts, latest[second].value)}).', 1.6, 'position')
        return Finding(f'{operator} {lead} ({_figure(facts, value)}), '
                       f'{_gap(facts, latest[second].value, value)} ahead of {second}.', 2.6, 'position')
    best_value = latest[best].value
    if not _meaningful(facts, latest[best], latest[operator]):
        return Finding(f'{operator} is on par with {best} in {metric} ({_figure(facts, value, unit=False)} vs '
                       f'{_figure(facts, best_value)}).', 1.8, 'position')
    text = (f'{best} {lead} ({_figure(facts, best_value)}); {operator} trails by '
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
        text = f'{unit.name} samples {label}: {f"{operator} " if operator else ""}{_percent(value)}'
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
        return Finding(f'{operator} also has the best {unit.name} tail ({label} {_figure(facts, values[operator])}).', 1.4, 'tail')
    return Finding(f'{unit.name} tail ({label}): {operator} {_figure(facts, values[operator], unit=False)} vs '
                   f'{best} {_figure(facts, values[best])}.', 1.8, 'tail')


def _latest_campaign(records: list[Record], campaign_key: str | None) -> str | None:
    campaigns = sorted({record.labels[campaign_key] for record in records if campaign_key in record.labels},
                       key=campaign_sort_key) if campaign_key else []
    return campaigns[-1] if campaigns else None


def _vendor_findings(facts: ChartFacts, focus: set[str], operator_key: str, campaign_key: str | None,
                     vendor_key: str, context_keys: list[str]) -> list[Finding]:
    """Multivendor: for the same operator, how its vendor areas compare at the latest campaign."""
    latest_campaign = _latest_campaign(facts.records, campaign_key)
    others = [name for name in context_keys if name != vendor_key]
    groups: dict[tuple[str, ...], dict[str, Record]] = {}
    for record in facts.records:
        vendor = record.labels.get(vendor_key, '')
        if (latest_campaign and record.labels.get(campaign_key) != latest_campaign) or vendor.casefold() in NOT_VENDORS:
            continue
        if _eligible(record):
            key = (record.labels.get(operator_key, ''), *(record.labels.get(name, '') for name in others))
            groups.setdefault(key, {})[vendor] = record
    findings = []
    for (operator, *context), vendors in groups.items():
        if len(vendors) < 2 or (focus and operator.casefold() not in focus):
            continue
        ranked = _ranked(facts, vendors)
        best, worst = ranked[0], ranked[-1]
        if not _meaningful(facts, vendors[worst], vendors[best]):
            continue
        higher, lower = (best, worst) if vendors[best].value >= vendors[worst].value else (worst, best)
        prefix = ' · '.join(value for value in context if value)
        what = f'the share of {facts.statistic}' if facts.family == 'share' else _metric(facts)
        text = (f'{prefix + ": " if prefix else ""}For {operator}, {what} is {_gap(facts, vendors[lower].value, vendors[higher].value)} '
                f'higher in {higher} areas than in {lower} areas ({_figure(facts, vendors[higher].value, unit=False)} vs '
                f'{_figure(facts, vendors[lower].value)}).')
        findings.append(Finding(text, 2.3 + (FOCUS_BONUS if focus else 0.0), 'vendor'))
    return findings


def _nr_mode_comparison(facts: ChartFacts, nsa: dict[str, Record], sa: dict[str, Record], focus: set[str],
                        prefix: str = '') -> list[Finding]:
    """Each operator in SA against itself in NSA (the latest campaign of each NR Mode): one sentence when SA is on the
    same side for every operator, else the Focus operators (or the largest gap)."""
    common = [name for name in sa if name in nsa]
    if not common:
        return []

    def higher(name: str) -> bool:
        return sa[name].value > nsa[name].value

    if len(common) > 1 and all(_meaningful(facts, nsa[name], sa[name]) for name in common) and len({higher(name) for name in common}) == 1:
        side = 'higher' if higher(common[0]) else 'lower'
        if facts.direction:
            side = 'better' if (sa[common[0]].value - nsa[common[0]].value) * facts.direction > 0 else 'worse'
        return [Finding(f'{prefix}{_subject(facts, "")} is {side} in SA than in NSA for every operator.', 2.6, 'nr_mode')]
    subjects = [name for name in common if name.casefold() in focus][:MAX_FOCUS_SUBJECTS]
    subjects = subjects or [max(common, key=lambda name: _gap_size(facts, nsa[name].value, sa[name].value))]
    findings = []
    for name in subjects:
        figures = f'({_figure(facts, sa[name].value, unit=False)} vs {_figure(facts, nsa[name].value)})'
        if not _meaningful(facts, nsa[name], sa[name]):
            if name.casefold() in focus:
                findings.append(Finding(f'{prefix}{_subject(facts, name)} is similar in SA and NSA {figures}.', 1.4, 'nr_mode'))
            continue
        findings.append(Finding(
            f'{prefix}{_subject(facts, name)} is {_gap(facts, nsa[name].value, sa[name].value)} '
            f'{"higher" if higher(name) else "lower"} in SA than in NSA {figures}.',
            2.4 + (FOCUS_BONUS if name.casefold() in focus else 0.0), 'nr_mode'))
    return findings


def _nr_mode_findings(facts: ChartFacts, focus: set[str], operator_key: str, campaign_key: str | None,
                      mode_key: str, context_keys: list[str]) -> list[Finding]:
    """A chart split by NR Mode: each operator in SA against itself in NSA, group by group."""
    others = [name for name in context_keys if name != mode_key]
    groups: dict[tuple[str, ...], dict[str, list[Record]]] = {}
    for record in facts.records:
        mode = str(record.labels.get(mode_key, '')).strip().upper()
        if mode in {'NSA', 'SA'}:
            groups.setdefault(tuple(record.labels.get(name, '') for name in others), {}).setdefault(mode, []).append(record)
    findings = []
    for context, by_mode in groups.items():
        if set(by_mode) != {'NSA', 'SA'}:
            continue
        latest = {}
        for mode, records in by_mode.items():
            campaign = _latest_campaign(records, campaign_key)
            latest[mode] = {record.labels.get(operator_key, ''): record for record in records
                            if _eligible(record) and (campaign is None or record.labels.get(campaign_key) == campaign)}
        prefix = ' · '.join(value for value in context if value)
        findings.extend(_nr_mode_comparison(facts, latest['NSA'], latest['SA'], focus, f'{prefix}: ' if prefix else ''))
    return findings


def _relation_findings(facts: ChartFacts, focus: set[str]) -> list[Finding]:
    """Scatter: how strongly the KPI follows the other measure for the Focus operators (or the largest series)."""
    operator_key, campaign_key, _vendor, context_keys = _roles(facts.records)
    latest_campaign = _latest_campaign(facts.records, campaign_key)
    records = [record for record in facts.records
               if (not latest_campaign or record.labels.get(campaign_key) == latest_campaign)
               and (record.samples or 0) >= MIN_RELATION_SAMPLES]
    subjects = [record for record in records if operator_key and record.labels.get(operator_key, '').casefold() in focus]
    bonus = FOCUS_BONUS if subjects else 0.0
    subjects = (subjects or sorted(records, key=lambda record: -(record.samples or 0))[:1])[:MAX_FOCUS_SUBJECTS]
    x_kpi: KpiSemantics = facts.extra['x']
    findings = []
    for record in subjects:
        rho = record.value
        name = record.labels.get(operator_key, '') if operator_key else ''
        context = ' · '.join(record.labels.get(key, '') for key in context_keys if record.labels.get(key))
        who = f'For {" · ".join(part for part in (name, context) if part)}, ' if name or context else ''
        metric = facts.semantics.name if who else facts.semantics.name[:1].upper() + facts.semantics.name[1:]
        if abs(rho) >= STRONG_CORRELATION and 'x_q25' in record.extra:
            stats = record.extra
            text = (f'{who}{metric} {"rises" if rho > 0 else "falls"} with {x_kpi.name} (Spearman ρ = {_format(rho, 2)}): '
                    f'median {_with_unit(_format(stats["y_median_low"], facts.semantics.digits), facts.semantics)} at or below '
                    f'{_with_unit(_format(stats["x_q25"], x_kpi.digits), x_kpi)} vs '
                    f'{_with_unit(_format(stats["y_median_high"], facts.semantics.digits), facts.semantics)} at or above '
                    f'{_with_unit(_format(stats["x_q75"], x_kpi.digits), x_kpi)}.')
            findings.append(Finding(text, 2.0 + abs(rho) + bonus, 'relation'))
        elif abs(rho) < WEAK_CORRELATION:
            findings.append(Finding(f'{who}{metric} barely follows {x_kpi.name} (Spearman ρ = {_format(rho, 2)}).',
                                    1.0 + bonus, 'relation'))
    return findings


def _map_findings(facts: ChartFacts) -> list[Finding]:
    """Map: the share of the weakest class and the area that holds more of it than its share of the route."""
    worst = facts.records[facts.extra['worst']]
    findings = [Finding(f'{_percent(worst.value)} of the mapped samples have {facts.statistic}.', 2.0, 'map')]
    areas = facts.extra.get('areas') or {}
    position = facts.extra.get('worst_position')
    rows = areas.get('rows') or []
    totals = {row['name']: sum(row['counts']) for row in rows}
    route = sum(totals.values())
    worst_total = sum(row['counts'][position] for row in rows) if position is not None else 0
    if position is not None and route and worst_total >= MIN_GROUP_SAMPLES:
        candidates = []
        for row in rows:
            if row['name'] == '(blank)' or row['counts'][position] < MIN_GROUP_SAMPLES:
                continue
            held, weight = row['counts'][position] / worst_total, totals[row['name']] / route
            if held >= 1.3 * weight:
                candidates.append((held - weight, row['name'], held, weight))
        if candidates:
            _excess, area, held, weight = max(candidates)
            findings.append(Finding(f'{area} holds {_percent(held)} of the samples with {facts.statistic} while it has '
                                    f'{_percent(weight)} of the mapped samples.', 2.4, 'map'))
    return findings


def _table_findings(facts: ChartFacts) -> list[Finding]:
    """Table: the highest and lowest rows of its first numeric columns."""
    findings = []
    for position, column in enumerate(facts.extra['columns']):
        values = {record.labels['Row']: record.extra['values'][column] for record in facts.records
                  if column in record.extra['values']}
        if len(set(values.values())) < 2:
            continue
        high, low = max(values, key=values.get), min(values, key=values.get)
        percent = any(record.extra['percent'] for record in facts.records)
        shown = (lambda value: f'{_format(value, 1)}%') if percent else (lambda value: _format(value))
        findings.append(Finding(f'{column}: highest {high} ({shown(values[high])}), lowest {low} ({shown(values[low])}).',
                                1.4 - position * 0.2, 'table'))
    return findings


def chart_findings(facts: ChartFacts, focus_operators: Iterable[str] = ()) -> list[Finding]:
    """The findings of one chart, group by group: the change of the Focus operators (or of the leader) since the
    previous campaign, their position against the leader, the weak tail, the largest move of the others, the vendors
    of each operator and the groups with too few samples to be named."""
    focus = {str(name).strip().casefold() for name in focus_operators if str(name or '').strip()}
    if facts.family == 'relation':
        return _relation_findings(facts, focus)
    if facts.family == 'map':
        return _map_findings(facts)
    if facts.family == 'table':
        return _table_findings(facts)
    operator_key, campaign_key, vendor_key, context_keys = _roles(facts.records)
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
    if vendor_key and operator_key:
        findings.extend(_vendor_findings(facts, focus, operator_key, campaign_key, vendor_key, context_keys))
    mode_key = next((name for name in context_keys if column_identity(name) in NR_MODE_DIMENSIONS), None)
    if mode_key and operator_key:
        findings.extend(_nr_mode_findings(facts, focus, operator_key, campaign_key, mode_key, context_keys))
    return findings


def _latest_by_operator(facts: ChartFacts) -> tuple[dict[str, Record], str | None]:
    """The eligible records of the latest campaign by operator, for charts read only by Operator (and Campaign)."""
    operator_key, campaign_key, _vendor, context_keys = _roles(facts.records)
    if not operator_key or context_keys:
        return {}, None
    latest_campaign = _latest_campaign(facts.records, campaign_key)
    return {
        record.labels[operator_key]: record for record in facts.records
        if operator_key in record.labels and _eligible(record)
        and (latest_campaign is None or record.labels.get(campaign_key) == latest_campaign)
    }, latest_campaign


def _technology(name: str) -> str | None:
    tokens = {token.casefold() for token in TECHNOLOGY_TOKENS.findall(name)}
    if tokens & {'nr', '5g'} and not tokens & {'lte', '4g'}:
        return 'NR'
    if tokens & {'lte', '4g'} and not tokens & {'nr', '5g'}:
        return 'LTE'
    return None


def _title_nr_mode(title: str) -> str | None:
    """The NR Mode a chart title names alone (CDF_SA, DL Throughput NSA), if any."""
    modes = {mode.upper() for mode in NR_MODE_TITLE_TOKENS.findall(title or '')}
    return next(iter(modes)) if len(modes) == 1 else None


def slide_findings(slide_facts: list[ChartFacts], focus_operators: Iterable[str] = ()) -> list[Finding]:
    """What the charts of one slide say together: NR against LTE and SA against NSA for the same KPI, and the operators
    of a slide that gives each operator its own chart."""
    focus = {str(name).strip().casefold() for name in focus_operators if str(name or '').strip()}
    stats = [facts for facts in slide_facts if facts.family == 'stat']
    findings: list[Finding] = []
    for nsa in slide_facts:
        for sa in slide_facts:
            if (_title_nr_mode(nsa.title) != 'NSA' or _title_nr_mode(sa.title) != 'SA' or nsa.family != sa.family
                    or nsa.family not in {'stat', 'share'} or nsa.statistic != sa.statistic
                    or nsa.semantics.name != sa.semantics.name):
                continue
            nsa_values, _campaign_ = _latest_by_operator(nsa)
            sa_values, _campaign_ = _latest_by_operator(sa)
            findings.extend(_nr_mode_comparison(sa, nsa_values, sa_values, focus))
    for lte in stats:
        for nr in stats:
            if (_technology(lte.semantics.name) != 'LTE' or _technology(nr.semantics.name) != 'NR'
                    or lte.statistic != nr.statistic or lte.semantics.unit != nr.semantics.unit
                    or TECHNOLOGY_TOKENS.sub('', lte.semantics.name).split() != TECHNOLOGY_TOKENS.sub('', nr.semantics.name).split()):
                continue
            lte_values, _campaign_ = _latest_by_operator(lte)
            nr_values, _campaign_ = _latest_by_operator(nr)
            common = [name for name in nr_values if name in lte_values]
            if not common:
                continue
            meaningful = [_meaningful(nr, lte_values[name], nr_values[name]) for name in common]
            signs = {nr_values[name].value > lte_values[name].value for name in common}
            gaps = [_gap_size(nr, lte_values[name].value, nr_values[name].value) for name in common]
            side = 'above' if signs == {True} else 'below'
            if len(common) > 1 and all(meaningful) and len(signs) == 1:
                low, high = min(gaps), max(gaps)
                shown = (lambda value: _format(value * 100, 0)) if nr.semantics.step is None else (lambda value: _format(value, nr.semantics.digits))
                unit = '%' if nr.semantics.step is None else f' {"dB" if nr.semantics.unit == "dBm" else nr.semantics.unit}'.rstrip()
                span = shown(low) if shown(low) == shown(high) else f'{shown(low)}–{shown(high)}'
                findings.append(Finding(f'{_subject(nr, "")} stays {span}{unit} {side} {lte.semantics.name} for every operator.',
                                        2.6, 'synthesis'))
                continue
            for name in [name for name in common if name.casefold() in focus][:MAX_FOCUS_SUBJECTS]:
                if not _meaningful(nr, lte_values[name], nr_values[name]):
                    continue
                higher = nr_values[name].value > lte_values[name].value
                findings.append(Finding(
                    f'{_subject(nr, name)} is {_gap(nr, lte_values[name].value, nr_values[name].value)} '
                    f'{"above" if higher else "below"} {lte.semantics.name} ({_figure(nr, nr_values[name].value, unit=False)} vs '
                    f'{_figure(nr, lte_values[name].value)}).', 2.2 + FOCUS_BONUS, 'synthesis'))
    by_metric: dict[tuple[str, str], list[tuple[str, Record, str | None]]] = {}
    for facts in stats:
        values, latest_campaign = _latest_by_operator(facts)
        if len(values) == 1:
            name, record = next(iter(values.items()))
            by_metric.setdefault((facts.semantics.name, facts.statistic), []).append((name, record, latest_campaign))
    for (metric, statistic), items in by_metric.items():
        operators = {name for name, _record, _campaign_ in items}
        if len(items) < 2 or len(operators) != len(items):
            continue
        facts = next(item for item in stats if item.semantics.name == metric and item.statistic == statistic)
        ranked = sorted(items, key=lambda item: -item[1].value * (facts.direction or 1))
        campaigns = {campaign for _name, _record, campaign in items if campaign}
        when = f' in {_campaign(next(iter(campaigns)))}' if len(campaigns) == 1 else ''
        values = ', '.join(f'{name} {_figure(facts, record.value, unit=False)}' for name, record, _campaign_ in ranked)
        findings.append(Finding(f'{_subject(facts, "")}{when}: {_with_unit(values, facts.semantics)}.', 2.1, 'synthesis'))
    return findings


def comment_limit(layout: str) -> int:
    return MAX_NARROW_SLIDE_COMMENTS if re.search(r'\bcomments\s+right\b', str(layout or ''), re.I) else MAX_SLIDE_COMMENTS


def slide_comments(charts: Iterable[dict[str, Any]], *, focus_operators: Iterable[str] = (), layout: str = '',
                   engine: str = ENGINE_RULES) -> list[dict[str, Any]]:
    """The comments of one slide from its visible charts.

    Each chart is ``{'index', 'title', 'kpi', 'model', 'hidden', 'shown', 'subject'}`` (``subject``: the value of a
    dynamic grid card, such as its Operator). Every chart gets its best comment first, then the best remaining ones,
    with those that read the charts together, fill the slide up to its limit, each comment once.
    """
    if engine not in ENGINES:
        raise ValueError(f'Unknown comment engine: {engine}.')
    focus = list(focus_operators)
    ranked: list[list[tuple[Finding, dict[str, Any]]]] = []
    every_fact: list[ChartFacts] = []
    for chart in charts:
        findings = []
        subject = str(chart.get('subject') or '')
        for facts in chart_facts(int(chart['index']), str(chart.get('title') or ''), str(chart.get('kpi') or ''),
                                 chart.get('model') or {}, chart.get('hidden') or (), chart.get('shown') or ()):
            every_fact.append(facts)
            for finding in chart_findings(facts, focus):
                text = finding.text
                if subject and facts.family in {'map', 'table'}:
                    text = f'{subject}: {text}'
                findings.append((Finding(text, finding.score, finding.kind),
                                 {'chart_index': facts.chart_index, 'chart_title': facts.title}))
        if findings:
            ranked.append(sorted(findings, key=lambda item: -item[0].score))
    together = [(finding, {'chart_index': None, 'chart_title': ''}) for finding in slide_findings(every_fact, focus)]
    if together:
        ranked.append(sorted(together, key=lambda item: -item[0].score))
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


def _brief_number(value: Any) -> Any:
    return round(value, 4) if isinstance(value, float) else value


def slide_brief(charts: Iterable[dict[str, Any]], *, focus_operators: Iterable[str] = (), layout: str = '') -> dict[str, Any]:
    """What an LLM writer receives for one slide: the facts of its charts (each value also as the comments write it),
    the rules comments as a draft, the Focus operators, the hidden legend items and how many comments it may write."""
    charts = list(charts)
    focus = [str(name) for name in focus_operators if str(name or '').strip()]
    briefed, hidden = [], set()
    for chart in charts:
        hidden.update(str(item) for item in chart.get('hidden') or ())
        for facts in chart_facts(int(chart['index']), str(chart.get('title') or ''), str(chart.get('kpi') or ''),
                                 chart.get('model') or {}, chart.get('hidden') or (), chart.get('shown') or ()):
            records = []
            for record in facts.records[:60]:
                extra = {key: ([_brief_number(item) for item in value] if isinstance(value, list) else _brief_number(value))
                         for key, value in record.extra.items() if isinstance(value, (int, float, list))}
                shown = (_percent(record.value) if facts.family in {'share', 'map'} else
                         _format(record.value, 2) if facts.family == 'relation' else
                         '' if facts.family == 'table' else _figure(facts, record.value))
                records.append({'labels': record.labels, 'value': _brief_number(record.value), 'samples': record.samples,
                                'shown': shown, 'extra': extra})
            briefed.append({
                'index': facts.chart_index, 'title': facts.title, 'kpi': str(chart.get('kpi') or ''), 'metric': facts.semantics.name,
                'family': facts.family, 'statistic': facts.statistic, 'unit': facts.semantics.unit,
                'better': {1: 'higher', -1: 'lower'}.get(facts.direction, 'unknown'), 'bucket_edges': facts.bucket_edges,
                'subject': str(chart.get('subject') or ''), 'records': records,
            })
    rules = slide_comments(charts, focus_operators=focus, layout=layout)
    return {
        'limit': comment_limit(layout), 'focus_operators': focus, 'hidden': sorted(hidden), 'charts': briefed,
        'rules_comments': [item['text'] for item in rules], 'rules': rules,
    }
