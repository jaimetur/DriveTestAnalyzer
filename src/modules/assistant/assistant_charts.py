"""The charts of the answers of the AI Assistant.

An answer can show charts beside its tables. The engine never gives the figures of a chart: it names the data the
server holds and how to draw it. A chart comes from a scoring result of the scoring tool (S1: the points of each group,
per environment or category, the GAP to the reference, their trend over the campaigns or the KPIs that lose most points,
as Scoring & GAP Analysis draws them, in the colours of the Operator Maps), from a chart of a PPT Design read with
ppt_design_charts (G1: the model its viewer draws, unchanged), from a query result (R1) or from a table of the answer
(T1, whose figures the validator of the answers checks), or from a chart of an earlier answer of the conversation (P1),
drawn again with another style without calculating anything.

The engine can also style a chart: the colour, line width and dash of its series (named whole or by a part of their
name, such as a campaign), the place of its legend and the titles of its axes. The style is applied to the model, so
the page draws it as given.

Every chart is a model of the chart painter of PPT Designer and Network Insights (static/js/core/canvas_charts.js), so
the page draws it with the same look, values on hover, zoom and legend.
"""
from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from typing import Any

SCORING_VIEWS = ('points', 'environments', 'categories', 'gap', 'trend', 'kpis')
CHART_TYPES = ('bar', 'hbar', 'line', 'pie')
MAX_CHARTS = 4
MAX_BARS = 160
MAX_SERIES = 24
MAX_PIE_SLICES = 24
MAX_KPI_GROUPS = 6
KPIS_PER_GROUP = 8
# A chart of a Design (a map with its samples) can be large: one over this size is not kept with the answer.
MAX_MODEL_CHARS = 2_500_000
PALETTE = ('#14867D', '#DF7A45', '#5A82AA', '#8B63B1', '#B49A32', '#E15759', '#59A14F', '#76B7B2', '#EDC948', '#9C755F')
DEFAULT_COLOUR = '#365F91'
SPEC_KEYS = ('title', 'source', 'view', 'type', 'x', 'y', 'series', 'styles', 'legend', 'x_title', 'y_title')
SOURCE = re.compile(r'^\s*([SGRTP])(\d{1,3})\s*$', re.IGNORECASE)
DASHES = {'solid': [], 'dashed': [10, 6], 'dotted': [2, 5]}
LEGEND_POSITIONS = ('top', 'bottom', 'left', 'right', 'none')
MAX_STYLES = 24
MAX_LINE_WIDTH = 14
# The CSS names of colours the engine may use besides #RRGGBB.
COLOUR_NAMES = {'black': '#000000', 'white': '#FFFFFF', 'red': '#E60000', 'green': '#2E9E44', 'blue': '#1F5FBF',
                'yellow': '#F2C200', 'orange': '#F28C00', 'purple': '#7B2D8E', 'pink': '#E05297', 'grey': '#7F7F7F',
                'gray': '#7F7F7F', 'brown': '#8B5A2B', 'cyan': '#00A3C4', 'teal': '#14867D', 'navy': '#1B2A5E',
                'magenta': '#C2187A', 'darkblue': '#0B3C8C', 'lightblue': '#7CB9E8', 'darkgreen': '#1E6B30',
                'lightgreen': '#8BD17C', 'darkred': '#8B0000'}
SCORING_KEYS = ('campaign', 'vendor', 'region', 'cluster', 'city', 'dataset_type', 'operator')
LEVEL_LABELS = {'campaign': 'Campaign', 'vendor': 'Vendor', 'region': 'Region', 'cluster': 'Cluster', 'city': 'City',
                'dataset_type': 'Dataset Type', 'operator': 'Operator'}

SPEC_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': {'type': 'string'}, 'source': {'type': 'string'}, 'view': {'type': 'string'}, 'type': {'type': 'string'},
        'x': {'type': 'array', 'items': {'type': 'string'}}, 'y': {'type': 'array', 'items': {'type': 'string'}},
        'series': {'type': 'string'},
        'styles': {'type': 'array', 'items': {
            'type': 'object', 'properties': {
                'series': {'type': 'string'}, 'colour': {'type': 'string'}, 'width': {'type': 'number'},
                'dash': {'type': 'string'}},
            'required': ['series', 'colour', 'width', 'dash'], 'additionalProperties': False}},
        'legend': {'type': 'string'}, 'x_title': {'type': 'string'}, 'y_title': {'type': 'string'},
    },
    'required': list(SPEC_KEYS),
    'additionalProperties': False,
}

PROMPT = '''Charts:
- When the user asks for a chart, a graph or a plot, or when a chart shows the answer better than a table (the points of
  several operators, a trend over campaigns), add it in "charts". Never say that you cannot draw charts.
- You never give the figures of a chart: its "source" names data the tools gave in this question. S1 is the scoring
  result with that scoring_id: "view" is points (the total points of each group), environments, categories, gap (the
  GAP to the reference operator; call scoring with detail gap), trend (the points of each operator over the campaigns:
  two or more campaigns) or kpis (the KPIs that lose most points; call scoring with detail kpis). G1 is the chart of a
  PPT Design with that chart_id (from ppt_design_charts): it is drawn exactly as the Design draws it. R1 is a query
  result. T1 is the first table of your answer (T2 the second).
- For R and T sources give "type" (bar, hbar, line or pie), "x" (the columns of the categories, the outer one first,
  for example ["Campaign"] for a line over campaigns), "y" (the columns of the values) and, for one line or bar series
  per value of a column, "series" (for example "Operator"). Leave the fields a source does not use empty.
- A chart has a short "title" in the language of the question. Write about what it shows in the answer, without
  copying every value of it: the user sees the chart.
- Style a chart when the user asks (a thicker line, another colour, a dashed line, where the legend goes, the axis
  titles): "styles" lists {"series": a series name, or a part of the names such as a campaign or an operator, every
  series when empty; "colour": "#RRGGBB" or a colour name, empty to keep it; "width": the line width, 1 to 14 (the
  default is 4), 0 to keep it; "dash": solid, dashed or dotted, empty to keep it}. "legend" is top, bottom, left, right
  or none; "x_title" and "y_title" rename the axes. Leave them empty otherwise. Never say a chart cannot be styled.
- The charts drawn earlier in the conversation have ids P1, P2… (see the conversation so far): to show one again with
  another style or title, use it as "source" with the new styles, without calling the tools again.'''


class ChartError(ValueError):
    """A chart of an answer cannot be drawn: the engine is told why."""


# -- helpers ------------------------------------------------------------------------------------------------------------

def _number(value: Any) -> float | None:
    """A figure of a cell: 1,234.5, 1.234,5, 921,81, 76.4 % and −3 alike (None for anything else)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return None if isinstance(value, float) and (math.isnan(value) or math.isinf(value)) else float(value)
    text = re.sub(r'[\s  %*]', '', str(value)).replace('−', '-')
    if not text or not re.fullmatch(r'[+-]?[\d.,]*\d[\d.,]*', text):
        return None
    if ',' in text and '.' in text:
        text = text.replace(',', '') if text.rfind('.') > text.rfind(',') else text.replace('.', '').replace(',', '.')
    elif ',' in text:
        text = text.replace(',', '') if re.fullmatch(r'[+-]?\d{1,3}(,\d{3})+', text) else text.replace(',', '.')
    elif text.count('.') > 1:
        text = text.replace('.', '')
    try:
        return float(text)
    except ValueError:
        return None


def _key(values: Any) -> list[str]:
    return [str(value) for value in (values if isinstance(values, (list, tuple)) else [values])]


def operator_colours(groups: list[dict[str, Any]]) -> dict[str, tuple[str, int]]:
    """The colour and position of every name of an operator of the Operator Maps (its aliases too), as Scoring draws it."""
    styles: dict[str, tuple[str, int]] = {}
    for index, group in enumerate(groups or []):
        canonical = str(group.get('canonical') or '').strip()
        if not canonical:
            continue
        colour = str(group.get('color') or '')
        colour = colour.upper() if re.fullmatch(r'#[0-9a-fA-F]{6}', colour) else DEFAULT_COLOUR
        try:
            position = int(group.get('position', index))
        except (TypeError, ValueError):
            position = index
        for name in (canonical, *(str(alias) for alias in group.get('aliases') or [])):
            if name.strip():
                styles[name.strip().casefold()] = (colour, position)
    return styles


class Colours:
    """The colour of each series: an operator keeps its colour of the Operator Maps, anything else takes the next
    colour of the palette."""

    def __init__(self, operators: dict[str, tuple[str, int]]) -> None:
        self.operators, self.assigned = operators, {}
        names = sorted(operators, key=len, reverse=True)
        # An operator inside a longer name (EE UK_Q3_NSA_2026), its longest name first.
        self.pattern = re.compile('|'.join(rf'(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])' for name in names)) if names else None

    def operator_in(self, name: str) -> str | None:
        text = str(name).strip().casefold()
        if text in self.operators:
            return text
        match = self.pattern.search(text) if self.pattern else None
        return match.group(0) if match else None

    def of(self, name: str) -> str:
        operator = self.operator_in(name)
        if operator:
            return self.operators[operator][0]
        if name not in self.assigned:
            self.assigned[name] = PALETTE[len(self.assigned) % len(PALETTE)]
        return self.assigned[name]

    def for_key(self, key: list[str]) -> str:
        """A bar named by several values: the colour of its operator, else of its last value."""
        operator = next((value for value in key if self.operator_in(value)), None)
        return self.of(operator if operator is not None else key[-1] if key else '')

    def position(self, name: str) -> int:
        style = self.operators.get(str(name).strip().casefold())
        return style[1] if style else 10_000


def _nice_top(value: float) -> float:
    if value <= 0:
        return 1.0
    magnitude = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * magnitude:
            return step * magnitude
    return 10 * magnitude


def _domain(values: list[float], top: float | None = None) -> list[float]:
    low, high = min([0.0, *values]), max([0.0, *values])
    if top is not None and top >= high:
        high = top
    else:
        high = high * 1.08 if high > 0 else 0.0
    low = low * 1.08 if low < 0 else 0.0
    if high == low:
        high = low + 1
    return [round(low, 4), round(high, 4)]


def _legend(items: list[tuple[str, str]], position: str = 'top', lines: bool = False) -> dict[str, Any]:
    unique = list(dict.fromkeys(items))
    return {'position': position if len(unique) > 1 else 'none', 'line_markers': lines,
            'items': [{'label': label, 'colour': colour} for label, colour in unique]}


def bar_model(title: str, metric: str, bars: list[tuple[list[str], float, str, str]], dimensions: list[str],
              top: float | None = None) -> dict[str, Any]:
    """Vertical bars: each one with its key (outer value first), value, colour and legend name."""
    if not bars:
        raise ChartError('The chart has no values to draw.')
    if len(bars) > MAX_BARS:
        raise ChartError(f'The chart would have {len(bars)} bars: at most {MAX_BARS}; split or filter less.')
    return {
        'renderer': 'assistant', 'type': 'mean_bar', 'title': title, 'metric': metric, 'aggregation': 'sum',
        'axis_columns': dimensions, 'dimensions': [[name] for name in dimensions],
        'domain': {'y': _domain([value for _key, value, _colour, _legend in bars], top)},
        'bars': [{'key': key, 'value': value, 'colour': colour, 'legend': legend} for key, value, colour, legend in bars],
        'legend': _legend([(legend, colour) for _key, _value, colour, legend in bars]),
    }


def hbar_model(title: str, metric: str, rows: list[list[str]], columns: list[str], cells: list[list[float | None]],
               colours: list[list[str]], dimensions: list[str]) -> dict[str, Any]:
    """Horizontal bars: a band per row (its key), a bar per column of the band."""
    if not rows:
        raise ChartError('The chart has no values to draw.')
    if len(rows) * max(len(columns), 1) > MAX_BARS:
        raise ChartError(f'The chart would have more than {MAX_BARS} bars; split or filter less.')
    values = [value for row in cells for value in row if value is not None]
    legend = [(column, colours[0][index]) for index, column in enumerate(columns)] if len(columns) > 1 else []
    return {
        'renderer': 'assistant', 'type': 'hbar', 'title': title, 'metric': metric, 'value_title': metric,
        'aggregation': 'sum', 'decimals': 2,
        'row_keys': rows, 'column_keys': [[column] for column in columns], 'cells': cells, 'cell_colours': colours,
        'dimensions': [[name] for name in dimensions], 'domain': {'x': _domain(values)},
        'legend': _legend(legend, 'top'),
    }


def line_model(title: str, metric: str, x_keys: list[list[str]], series: list[tuple[str, list[float | None], str]],
               dimensions: list[str], domain: list[float] | None = None,
               dashes: dict[str, list[int]] | None = None) -> dict[str, Any]:
    if not x_keys or not series:
        raise ChartError('The chart has no values to draw.')
    if len(series) > MAX_SERIES:
        raise ChartError(f'The chart would have {len(series)} lines: at most {MAX_SERIES}.')
    values = [value for _name, line, _colour in series for value in line if value is not None]
    if domain is None:
        low, high = min(values), max(values)
        pad = (high - low) * .15 or abs(high) * .1 or 1
        bottom = 0.0 if low >= 0 and low - pad <= 0 else low - pad
        domain = [round(bottom, 4), round(high + pad, 4)]
    dashes = dashes or {}
    legend = _legend([(name, colour) for name, _line, colour in series], 'top', lines=True)
    for item in legend['items']:
        item.update(width=4, dash=dashes.get(item['label'], []))
    return {
        'renderer': 'assistant', 'type': 'lines', 'title': title, 'metric': metric, 'value_title': metric,
        'aggregation': 'sum', 'x_keys': x_keys, 'dimensions': [[name] for name in dimensions], 'domain': {'y': domain},
        'series': [{'name': name, 'key': [name], 'values': line, 'colour': colour, 'width': 4, 'dash': dashes.get(name, []),
                    'aggregation': 'sum'} for name, line, colour in series],
        'legend': legend,
    }


def pie_model(title: str, metric: str, pies: list[tuple[str, list[tuple[str, float, str]]]]) -> dict[str, Any]:
    drawn = []
    for label, slices in pies:
        kept = [(name, value, colour) for name, value, colour in slices if value > 0]
        if len(kept) > MAX_PIE_SLICES:
            raise ChartError(f'A pie would have {len(kept)} slices: at most {MAX_PIE_SLICES}.')
        total = sum(value for _name, value, _colour in kept)
        if total <= 0:
            continue
        drawn.append({'label': label, 'key': [label] if label != '(all)' else [], 'total': total, 'slices': [
            {'name': name, 'value': value, 'share': value / total, 'colour': colour} for name, value, colour in kept]})
    if not drawn:
        raise ChartError('A pie needs positive values.')
    legend = [(name, colour) for pie in drawn for name, colour in ((item['name'], item['colour']) for item in pie['slices'])]
    return {'renderer': 'assistant', 'type': 'pie', 'title': title, 'metric': metric, 'pies': drawn,
            'legend': {**_legend(legend, 'right'), 'position': 'right'}}


# -- the data of the tools ----------------------------------------------------------------------------------------------

def register_scoring(cache: dict[str, Any], result: dict[str, Any], selection: dict[str, Any],
                     only: dict[str, list[str]] | None) -> str:
    """Keep a result of the scoring tool for the charts of the answer: its id (S1, S2…)."""
    results = cache.setdefault('scoring_results', {})
    scoring_id = f'S{len(results) + 1}'
    results[scoring_id] = {'result': result, 'selection': selection, 'only': only or {}}
    return scoring_id


def register_design_charts(cache: dict[str, Any], found: dict[str, Any]) -> None:
    """Give every chart of a reading of ppt_design_charts its id (G1, G2…), keeping its model for the answer: the models
    leave the result the engine receives."""
    models = found.pop('chart_models', None) or {}
    charts = cache.setdefault('design_charts', {})
    for slide in found.get('slides') or []:
        if not isinstance(slide, dict):
            continue
        for chart in slide.get('charts') or []:
            model = models.get(chart.get('index')) if isinstance(chart, dict) else None
            if not isinstance(model, dict):
                continue
            # A chart read again keeps its id.
            chart_id = next((key for key, value in charts.items()
                             if (value['design_id'], value['index']) == (found.get('design'), chart.get('index'))), None)
            if chart_id is None:
                chart_id = f'G{len(charts) + 1}'
            charts[chart_id] = {'model': model, 'design_id': found.get('design'), 'index': chart.get('index'),
                                'design': found.get('name'), 'slide': slide.get('slide'), 'title': chart.get('title')}
            chart['chart_id'] = chart_id


def _shown(row: dict[str, Any], only: dict[str, list[str]]) -> bool:
    for level, values in (only or {}).items():
        key = level.casefold().replace(' ', '_')
        if str(row.get(key) or '').casefold() not in {value.casefold() for value in values}:
            return False
    return True


def _campaign_order(name: str) -> tuple[str, str]:
    from src.modules.cdr.column_names import campaign_parts
    year, quarter, _mode = campaign_parts(str(name))
    return (f'{year}-{quarter}' if year and quarter else str(name), str(name))


def scoring_chart(stored: dict[str, Any], view: str, chart_type: str, title: str, colours: Colours) -> dict[str, Any]:
    """A chart of a scoring result, as Scoring & GAP Analysis draws its own: bars in the colours of the operators."""
    result, only = stored['result'], stored['only']
    view = (view or 'points').strip().casefold()
    if view not in SCORING_VIEWS:
        raise ChartError(f'view of a scoring chart is one of {", ".join(SCORING_VIEWS)}.')
    totals = [row for row in result.get('totals') or [] if _shown(row, only)]
    levels = [key for key in SCORING_KEYS if any(row.get(key) is not None for row in totals)]
    if view == 'trend':
        return _scoring_trend(totals, levels, title, colours)
    if view == 'kpis':
        return _scoring_kpis(result, levels, only, title, colours)
    if view == 'gap':
        rows = [row for row in result.get('gap_totals') or [] if row.get('category') == 'Overall'
                and row.get('environment', 'Combined') == 'Combined' and _shown(row, only)]
        if not rows:
            raise ChartError('This scoring result has no GAP: call scoring with detail ["gap"].')
        reference = stored['selection'].get('baseline_operator') or ''
        bars = _scoring_bars(rows, levels, 'gap_points', colours)
        if not bars:
            raise ChartError(f'The reference operator {reference} has no points in this result: call scoring with '
                             'another reference_operator.')
        return _bars_or_hbar(chart_type, title or f'GAP to {reference}', f'GAP to {reference} (points)', bars,
                             [LEVEL_LABELS[key] for key in levels])
    if view == 'points':
        rows = [row for row in totals if row.get('environment') == 'Combined' and row.get('category') == 'Overall']
        outer: list[str] = []
    elif view == 'environments':
        rows = [row for row in totals if row.get('category') == 'Overall' and row.get('environment') != 'Combined']
        outer = ['environment']
    else:
        rows = [row for row in totals if row.get('environment') == 'Combined' and row.get('category') != 'Overall']
        outer = ['category']
    if not rows:
        raise ChartError(f'This scoring result has no points per {view}.')
    bars = _scoring_bars(rows, outer + levels, 'total_points', colours)
    top = max((float(row.get('max_points') or 0) for row in rows), default=0.0) or None
    labels = [{'environment': 'Environment', 'category': 'Category'}.get(key) or LEVEL_LABELS[key] for key in outer + levels]
    campaigns = ', '.join(stored['selection'].get('campaigns') or [])
    return _bars_or_hbar(chart_type, title or f'Scoring points – {campaigns}', 'Points', bars, labels, top)


def _row_points(row: dict[str, Any], field: str) -> float | None:
    value = row.get(field)
    if value is None and field == 'total_points':
        value = row.get('weighted_points')
    return _number(value)


def _scoring_bars(rows: list[dict[str, Any]], keys: list[str], field: str, colours: Colours) -> list[tuple[list[str], float, str, str]]:
    """The bars of the rows of a scoring result in the order of the module: the outer levels as they come, the operators
    in the order of the Operator Maps."""
    first: dict[str, int] = {}
    for row in rows:
        for key in keys:
            first.setdefault(f'{key}:{row.get(key)}', len(first))

    def order(row: dict[str, Any]) -> tuple:
        parts = []
        for key in keys:
            value = row.get(key)
            if key == 'operator':
                parts.append((colours.position(str(value)), str(value).casefold()))
            elif key == 'campaign':
                parts.append(_campaign_order(str(value)))
            else:
                parts.append((first[f'{key}:{value}'], ''))
        return tuple(parts)

    bars = []
    for row in sorted(rows, key=order):
        value = _row_points(row, field)
        if value is None:
            continue
        key = [str(row.get(name)) for name in keys]
        operator = str(row.get('operator') or key[-1])
        bars.append((key, round(value, 2), colours.of(operator), operator))
    return bars


def _bars_or_hbar(chart_type: str, title: str, metric: str, bars: list[tuple[list[str], float, str, str]],
                  dimensions: list[str], top: float | None = None) -> dict[str, Any]:
    if (chart_type or '').casefold() != 'hbar':
        return bar_model(title, metric, bars, dimensions, top)
    rows = [key for key, _value, _colour, _legend in bars]
    model = hbar_model(title, metric, rows, [metric], [[value] for _key, value, _colour, _legend in bars],
                       [[colour] for _key, _value, colour, _legend in bars], dimensions)
    model['legend'] = _legend([(legend, colour) for _key, _value, colour, legend in bars])
    return model


def _scoring_trend(totals: list[dict[str, Any]], levels: list[str], title: str, colours: Colours) -> dict[str, Any]:
    rows = [row for row in totals if row.get('environment') == 'Combined' and row.get('category') == 'Overall']
    campaigns = sorted({str(row.get('campaign')) for row in rows if row.get('campaign') is not None}, key=_campaign_order)
    if len(campaigns) < 2:
        raise ChartError('A trend needs the points of two or more campaigns: call scoring with several campaigns '
                         '(latest 2, latest 4, all).')
    others = [key for key in levels if key not in {'campaign', 'operator'}]
    series: dict[str, dict[str, Any]] = {}
    for row in rows:
        operator = str(row.get('operator'))
        name = ' · '.join([*(str(row.get(key)) for key in others), operator])
        entry = series.setdefault(name, {'operator': operator, 'values': {}, 'order': (
            *(str(row.get(key)) for key in others), colours.position(operator), operator.casefold())})
        entry['values'][str(row.get('campaign'))] = _row_points(row, 'total_points')
    lines = [(name, [None if entry['values'].get(campaign) is None else round(entry['values'][campaign], 2)
                     for campaign in campaigns], colours.of(entry['operator']))
             for name, entry in sorted(series.items(), key=lambda item: item[1]['order'])]
    return line_model(title or 'Scoring points by campaign', 'Points', [[campaign] for campaign in campaigns], lines, ['Campaign'])


def _scoring_kpis(result: dict[str, Any], levels: list[str], only: dict[str, list[str]], title: str,
                  colours: Colours) -> dict[str, Any]:
    groups: dict[tuple, dict[str, dict[str, Any]]] = {}
    for row in result.get('scoring') or []:
        if not _shown(row, only):
            continue
        group = tuple(str(row.get(key)) for key in levels)
        entry = groups.setdefault(group, {}).setdefault(str(row.get('kpi')), {'max': 0.0, 'points': 0.0})
        entry['max'] += float(_number(row.get('max_points')) or 0)
        entry['points'] += float(_number(row.get('weighted_points')) or 0)
    if not groups:
        raise ChartError('This scoring result has no KPIs.')
    if len(groups) > MAX_KPI_GROUPS:
        raise ChartError(f'The KPIs of {len(groups)} groups are too many for one chart: use "only" in scoring '
                         f'(at most {MAX_KPI_GROUPS} groups).')
    operator_index = levels.index('operator') if 'operator' in levels else -1
    rows, cells, cell_colours = [], [], []
    for group in sorted(groups, key=lambda item: (colours.position(item[operator_index]) if operator_index >= 0 else 0, item)):
        lost = sorted(((kpi, entry['max'] - entry['points']) for kpi, entry in groups[group].items()),
                      key=lambda item: -item[1])[:KPIS_PER_GROUP]
        colour = colours.of(group[operator_index]) if operator_index >= 0 else colours.of(' · '.join(group))
        for kpi, value in lost:
            rows.append([*(group if len(groups) > 1 else ()), kpi])
            cells.append([round(value, 2)])
            cell_colours.append([colour])
    dimensions = [*([LEVEL_LABELS[key] for key in levels] if len(groups) > 1 else []), 'KPI']
    return hbar_model(title or 'KPIs that lose most points', 'Points lost', rows, ['Points lost'], cells, cell_colours, dimensions)


# -- tables and query results -------------------------------------------------------------------------------------------

def _column(columns: list[str], name: str, what: str) -> int:
    wanted = str(name or '').strip().casefold()
    for index, column in enumerate(columns):
        if str(column).strip().casefold() == wanted:
            return index
    raise ChartError(f'{what} "{name}" is not a column of the data ({", ".join(columns[:20])}).')


def table_chart(columns: list[str], rows: list[list[Any]], spec: dict[str, Any], title: str, colours: Colours) -> dict[str, Any]:
    """A chart of the rows of a table or a query result: the categories of ``x``, the values of ``y`` and a series per
    value of ``series`` (or per column of ``y``)."""
    chart_type = str(spec.get('type') or 'bar').strip().casefold()
    if chart_type not in CHART_TYPES:
        raise ChartError(f'type is one of {", ".join(CHART_TYPES)}.')
    if not columns or not rows:
        raise ChartError('The data of the chart has no rows.')
    numeric = [index for index in range(len(columns)) if any(_number(row[index]) is not None for row in rows if index < len(row))
               and all(_number(row[index]) is not None or str(row[index] or '').strip() == '' for row in rows if index < len(row))]
    series_index = _column(columns, spec['series'], 'series') if str(spec.get('series') or '').strip() else None
    x = [_column(columns, name, 'x') for name in spec.get('x') or [] if str(name).strip()]
    y = [_column(columns, name, 'y') for name in spec.get('y') or [] if str(name).strip()]
    if not y:
        y = [index for index in numeric if index not in x and index != series_index][:1]
    if not y:
        raise ChartError('Give in "y" the column of the values.')
    if not x:
        x = [index for index in range(len(columns)) if index not in y and index != series_index][:1]
    if not x and chart_type != 'pie':
        raise ChartError('Give in "x" the column of the categories.')
    if series_index is not None and len(y) > 1:
        raise ChartError('Give one column in "y" when "series" splits the values.')
    dimensions = [str(columns[index]) for index in x]
    metric = str(columns[y[0]]) if len(y) == 1 else ''
    title = title or (f'{metric} by {", ".join(dimensions)}' if metric else ', '.join(str(columns[index]) for index in y))

    def cell(row: list[Any], index: int) -> Any:
        return row[index] if index < len(row) else None

    # The categories in the order of the rows, each value of a series in its order too.
    categories: list[list[str]] = []
    series_names: list[str] = []
    values: dict[tuple[tuple[str, ...], str], float] = {}
    for row in rows:
        category = [str(cell(row, index) if cell(row, index) is not None else '') for index in x]
        if category not in categories:
            categories.append(category)
        if series_index is not None:
            name = str(cell(row, series_index) or '')
            pairs = [(name, cell(row, y[0]))]
        else:
            pairs = [(str(columns[index]), cell(row, index)) for index in y]
        for name, value in pairs:
            number = _number(value)
            if name not in series_names:
                series_names.append(name)
            if number is not None:
                values[(tuple(category), name)] = values.get((tuple(category), name), 0.0) + number
    if not values:
        raise ChartError(f'The column {columns[y[0]]} has no figures.')
    split = series_index is not None or len(y) > 1
    if chart_type == 'line':
        lines = [(name, [None if (tuple(category), name) not in values else round(values[(tuple(category), name)], 4)
                         for category in categories], colours.of(name)) for name in series_names]
        if not split:
            lines = [(metric or lines[0][0], lines[0][1], colours.for_key([metric]))]
        return line_model(title, metric, categories, lines, dimensions, dashes=operator_dashes([name for name, _line, _colour in lines], colours))
    if chart_type == 'pie':
        pies = []
        for name in series_names:
            slices = [(' · '.join(category) or name, values[(tuple(category), name)], colours.for_key(category))
                      for category in categories if (tuple(category), name) in values]
            pies.append((name if split else '(all)', slices))
        return pie_model(title, metric, pies)
    if chart_type == 'hbar':
        names = series_names if split else [metric]
        cells = [[None if (tuple(category), name) not in values else round(values[(tuple(category), name)], 4)
                  for name in (series_names if split else series_names[:1])] for category in categories]
        cell_colours = [[colours.of(name) if split else colours.for_key(category) for name in names] for category in categories]
        model = hbar_model(title, metric, categories, names, cells, cell_colours, dimensions)
        if not split:
            model['legend'] = _legend([(category[-1], colours.for_key(category)) for category in categories
                                       if category[-1].strip().casefold() in colours.operators])
        return model
    bars = []
    for category in categories:
        for name in series_names:
            if (tuple(category), name) not in values:
                continue
            key = [*category, name] if split else category
            colour = colours.of(name) if split else colours.for_key(category)
            legend = name if split else next((value for value in category if value.strip().casefold() in colours.operators),
                                             category[-1] if category else name)
            bars.append((key, round(values[(tuple(category), name)], 4), colour, legend))
    model = bar_model(title, metric, bars, dimensions + ([str(columns[series_index])] if series_index is not None else
                                                          ['Value'] if len(y) > 1 else []))
    if not split and not any(value.strip().casefold() in colours.operators for category in categories for value in category):
        model['legend'] = _legend([])
    return model


# -- the charts of an answer --------------------------------------------------------------------------------------------

def operator_dashes(names: list[str], colours: Colours) -> dict[str, list[int]]:
    """The lines of one operator share its colour: the one of its latest campaign is solid, the earlier ones dashed, then
    dotted."""
    by_operator: dict[str, list[str]] = {}
    for name in names:
        operator = colours.operator_in(name)
        if operator:
            by_operator.setdefault(operator, []).append(name)
    dashes = {}
    for group in by_operator.values():
        if len(group) < 2:
            continue
        for position, name in enumerate(sorted(group, key=_campaign_order, reverse=True)):
            dashes[name] = DASHES[('solid', 'dashed', 'dotted')[min(position, 2)]]
    return dashes


def _colour(value: str) -> str:
    text = re.sub(r'\s+', '', str(value or '')).casefold()
    if not text:
        return ''
    if re.fullmatch(r'#?[0-9a-f]{6}', text):
        return '#' + text.lstrip('#').upper()
    if re.fullmatch(r'#?[0-9a-f]{3}', text):
        return '#' + ''.join(character * 2 for character in text.lstrip('#')).upper()
    if text in COLOUR_NAMES:
        return COLOUR_NAMES[text]
    raise ChartError(f'colour "{value}" is not #RRGGBB nor one of {", ".join(sorted(COLOUR_NAMES))}.')


def _series_names(model: dict[str, Any]) -> list[str]:
    """The names of the series of a model, as its legend and its tooltips show them."""
    names = [str(item.get('label')) for item in (model.get('legend') or {}).get('items') or [] if item.get('label') is not None]
    names += [str(item.get('name') if item.get('name') is not None else item.get('legend_name') or '')
              for item in model.get('series') or [] if isinstance(item, dict)]
    names += [str(item.get('legend') or '') for item in model.get('bars') or [] if isinstance(item, dict)]
    names += [str(slice_.get('name') or '') for pie in model.get('pies') or [] for slice_ in pie.get('slices') or []]
    names += [str(key[-1]) for key in model.get('column_keys') or [] if key]
    if model.get('type') == 'hbar':
        names += [str(key[-1]) for key in model.get('row_keys') or [] if key]
    return [name for name in dict.fromkeys(names) if name]


def _matching(names: list[str], wanted: str) -> list[str]:
    """The series a style names: all when empty, the one with that name, else those whose name holds it."""
    text = str(wanted or '').strip().casefold()
    if not text:
        return names
    exact = [name for name in names if name.casefold() == text]
    return exact or [name for name in names if text in name.casefold()]


def apply_styles(model: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """The model with the styles of a request: colour, line width and dash of its series, place of its legend, titles of
    its axes."""
    styles = spec.get('styles') or []
    legend = str(spec.get('legend') or '').strip().casefold()
    x_title, y_title = str(spec.get('x_title') or '').strip(), str(spec.get('y_title') or '').strip()
    if not styles and not legend and not x_title and not y_title:
        return model
    names = _series_names(model)
    for style in styles:
        chosen = set(_matching(names, style.get('series')))
        if not chosen:
            raise ChartError(f'No series of the chart is named "{style.get("series")}": its series are '
                             f'{", ".join(names[:24]) or "none"}.')
        colour = _colour(style.get('colour'))
        try:
            width = float(style.get('width') or 0)
        except (TypeError, ValueError):
            width = 0.0
        width = min(max(width, 0.0), MAX_LINE_WIDTH)
        dash = str(style.get('dash') or '').strip().casefold()
        if dash and dash not in DASHES:
            raise ChartError(f'dash is one of {", ".join(DASHES)}.')

        def paint(item: dict[str, Any], *, line: bool = True) -> None:
            if colour:
                item['colour'] = colour
            if line and width:
                item['width'] = width
            if line and dash:
                item['dash'] = DASHES[dash]

        for item in (model.get('legend') or {}).get('items') or []:
            if str(item.get('label')) in chosen:
                paint(item)
        for item in model.get('series') or []:
            if isinstance(item, dict) and str(item.get('name') if item.get('name') is not None else item.get('legend_name') or '') in chosen:
                paint(item)
        for item in model.get('bars') or []:
            if isinstance(item, dict) and (str(item.get('legend') or '') in chosen or any(str(part) in chosen for part in item.get('key') or [])):
                paint(item, line=False)
        for pie in model.get('pies') or []:
            for item in pie.get('slices') or []:
                if str(item.get('name') or '') in chosen:
                    paint(item, line=False)
        if colour and model.get('cell_colours'):
            rows, columns = model.get('row_keys') or [], model.get('column_keys') or []
            for row_index, row in enumerate(model['cell_colours']):
                for column_index in range(len(row)):
                    row_key = [str(part) for part in (rows[row_index] if row_index < len(rows) else [])]
                    column_key = [str(part) for part in (columns[column_index] if column_index < len(columns) else [])]
                    if any(part in chosen for part in (*row_key, *column_key)):
                        row[column_index] = colour
    if legend:
        if legend not in LEGEND_POSITIONS:
            raise ChartError(f'legend is one of {", ".join(LEGEND_POSITIONS)}.')
        model.setdefault('legend', {'items': []})['position'] = legend
    if (x_title or y_title) and model.get('renderer') == 'assistant':
        # The charts drawn here: the horizontal axis and the vertical one, where the chart has a title for them.
        kind = model.get('type')
        places = {'lines': ('category_title', 'value_title'), 'hbar': ('value_title', None), 'mean_bar': (None, 'metric'),
                  'pie': (None, None)}.get(kind, (None, None))
        for title, place, axis in ((x_title, places[0], 'x'), (y_title, places[1], 'y')):
            if title and place is None:
                raise ChartError(f'A {kind} chart has no title on its {axis} axis: leave {axis}_title empty.')
            if title:
                model[place] = title
    elif x_title or y_title:
        # A chart of a Design takes them as the Format of PPT Designer gives them.
        axes = model.setdefault('format_overrides', {}).setdefault('axes', {})
        if x_title:
            axes.setdefault('x', {})['title'] = x_title
        if y_title:
            axes.setdefault('y', {})['title'] = y_title
    return model


def clean_specs(value: Any) -> list[dict[str, Any]]:
    """The chart requests of a step, every field a string (or a list of strings)."""
    specs = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        spec = {key: str(item.get(key) or '').strip()[:200]
                for key in ('title', 'source', 'view', 'type', 'series', 'legend', 'x_title', 'y_title')}
        spec['styles'] = [{'series': str(style.get('series') or '').strip()[:200], 'colour': str(style.get('colour') or '').strip()[:40],
                           'width': style.get('width') or 0, 'dash': str(style.get('dash') or '').strip()[:20]}
                          for style in item.get('styles') or [] if isinstance(style, dict)][:MAX_STYLES]
        for key in ('x', 'y'):
            raw = item.get(key)
            spec[key] = [str(part).strip()[:200] for part in (raw if isinstance(raw, list) else [raw] if raw else [])
                         if str(part or '').strip()][:4]
        if spec['source']:
            specs.append(spec)
    return specs[:MAX_CHARTS]


def build_chart(spec: dict[str, Any], cache: dict[str, Any], tables: list[dict[str, Any]], colours: Colours,
                relabel: Callable[[Any], Any] = lambda document: document) -> dict[str, Any]:
    """The model of one chart of an answer (its names real: ``spec`` and ``tables`` are given as the page shows them;
    ``relabel`` writes the campaigns of the data of the tools as the page shows them)."""
    match = SOURCE.match(spec.get('source') or '')
    if not match:
        raise ChartError(f'source "{spec.get("source")}" is not S1, G1, R1, T1 or P1.')
    kind, number = match.group(1).upper(), int(match.group(2))
    source = f'{kind}{number}'
    title = spec.get('title') or ''
    if kind == 'S':
        stored = (cache.get('scoring_results') or {}).get(source)
        if stored is None:
            raise ChartError(f'There is no scoring result {source} in this question: call scoring first.')
        model = scoring_chart(stored, spec.get('view') or 'points', spec.get('type') or 'bar', title, colours)
    elif kind == 'G':
        stored = (cache.get('design_charts') or {}).get(source)
        if stored is None:
            raise ChartError(f'There is no Design chart {source} in this question: read it with ppt_design_charts first.')
        model = json.loads(json.dumps(stored['model']))
        if title:
            model['title'] = title
    elif kind == 'P':
        stored = (cache.get('previous_charts') or {}).get(source)
        if stored is None:
            raise ChartError(f'There is no chart {source} earlier in this conversation.')
        model = json.loads(json.dumps(stored['model']))
        if title:
            model['title'] = title
    elif kind == 'R':
        stored = (cache.get('query_results') or {}).get(source)
        if stored is None:
            raise ChartError(f'There is no query result {source} in this question.')
        model = table_chart([str(column) for column in stored['columns']], [list(row) for row in stored['rows']], spec, title, colours)
    else:
        if not 1 <= number <= len(tables):
            raise ChartError(f'The answer has no table {source}.')
        table = tables[number - 1]
        model = table_chart([str(column) for column in table.get('columns') or []], [list(row) for row in table.get('rows') or []],
                            spec, title or str(table.get('title') or ''), colours)
    if kind in {'S', 'R'}:
        model = relabel(model)
    model = apply_styles(model, spec)
    size = len(json.dumps(model, ensure_ascii=False, default=str))
    if size > MAX_MODEL_CHARS:
        raise ChartError(f'The chart {source} is too large to show in the chat ({size // 1_000_000} MB); open it in its module.')
    origin = (f'{stored.get("design")} · slide {stored.get("slide")}' if kind == 'G' else
              str(stored.get('origin') or '') if kind == 'P' else '')
    style = {key: spec[key] for key in ('styles', 'legend', 'x_title', 'y_title') if spec.get(key)}
    return {'title': str(model.get('title') or title), 'source': source, 'view': spec.get('view') or '',
            'type': spec.get('type') or '', 'model': model, **({'origin': origin} if origin else {}),
            **({'style': style} if style else {})}


def build_charts(specs: list[dict[str, Any]], cache: dict[str, Any], tables: list[dict[str, Any]],
                 operators: dict[str, tuple[str, int]],
                 relabel: Callable[[Any], Any] = lambda document: document) -> tuple[list[dict[str, Any]], list[str]]:
    """The charts of an answer and the problems of those that cannot be drawn."""
    colours = Colours(operators)
    charts, problems = [], []
    for spec in specs:
        try:
            charts.append(build_chart(spec, cache, tables, colours, relabel))
        except ChartError as exc:
            problems.append(f'{spec.get("source")}: {exc}')
    return charts, problems
