"""The chart types added after Tableau's Show Me: their models for the PPT Designer and Chart Builder.

Each chart type reads the rows ``catalog_chart_payload`` has filtered and grouped (its Rows and Columns as the
``__catalog_row_N`` / ``__catalog_column_N`` hierarchy) and returns the 1600 x 900 model ``canvas_charts.js`` paints,
in the viewer and in the PPT (a picture drawn by the same renderer). The template row keeps the chart type in
``Chart type`` and its settings among its Filters (``Whiskers = P10-P90``, ``Target = Previous campaign``…), as
Threshold, Buckets and Bin Size are kept.
"""
from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any, Callable

import numpy as np
import pandas as pd

# Chart type (as the template row writes it, case ignored) -> the kind of model it draws.
EXTENDED_CHART_TYPES: dict[str, str] = {
    "horizontal bars": "hbar",
    "dot plot": "dot",
    "bullet graph": "bullet",
    "highlight table": "table",
    "bar table": "table",
    "heat map": "heat_map",
    "pie": "pie",
    "donut": "pie",
    "lines": "lines",
    "dual lines": "lines",
    "areas": "areas",
    "100% stacked areas": "areas",
    "bars and line": "combo",
    "box plot": "box",
    "symbol map": "symbol_map",
    "filled map": "filled_map",
    "treemap": "treemap",
    "packed bubbles": "bubbles",
    "sankey": "sankey",
    "gantt": "gantt",
}
# The settings these chart types keep among the Filters of their row (besides Threshold, Buckets and Bin Size).
EXTENDED_CHART_SETTINGS = frozenset({"whiskers", "target", "datebin", "direction", "sort"})
# A date field grouped by a period of time on Rows or Columns, written as the period applied to it: DAY(Test_Start_Time).
DATE_BINS = ("hour", "day", "week", "month")
_DATE_BIN_PATTERN = re.compile(r"^\s*(hour|day|week|month)\s*\(\s*(.+?)\s*\)\s*$", re.I)
# Whiskers of a Box Plot: the percentiles they reach (P10-P90 by default), the extremes or 1.5 times the box.
WHISKERS = {"p10-p90": (10, 90), "p5-p95": (5, 95), "p25-p75": (25, 75), "min-max": (0, 100), "1.5 iqr": None}
# Five classes of a colour scale, worst to best (a KPI with a direction) or low to high (without one); the light ones
# fill the cells of a Highlight Table.
QUALITY_COLOURS = ("#D7263D", "#F08A24", "#F2C230", "#8BC34A", "#2E8B57")
QUALITY_LIGHT_COLOURS = ("#F6C9CC", "#FADDBF", "#FBEFC0", "#DDEFC6", "#C3E4CD")
SEQUENTIAL_COLOURS = ("#DCEAF7", "#B5D3EE", "#83B5E0", "#4F8FCB", "#2A6BB0")
SEQUENTIAL_LIGHT_COLOURS = ("#F1F6FC", "#E1ECF8", "#CCDFF2", "#B3CFEA", "#97BDE1")
# Colours of the nodes of a Sankey below its first level, and of series without a colour of their own.
NEUTRAL_COLOURS = ("#4E79A7", "#F28E2B", "#76B7B2", "#59A14F", "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC", "#E15759")
# Limits that keep a chart legible (and its model small).
MAX_CATEGORIES = 60
MAX_MAP_PANELS = 6
MAX_SYMBOLS = 600
MAX_TREEMAP_ITEMS = 400
MAX_BUBBLES = 150
MAX_SANKEY_NODES = 30
MAX_GANTT_LANES = 40


def _reporting():
    # cdr_reporting imports this module: its helpers are read when a model is built.
    from src.modules import cdr_reporting

    return cdr_reporting


def is_extended_chart_type(chart_type: str) -> bool:
    return str(chart_type or "").strip().casefold() in EXTENDED_CHART_TYPES


def date_bin_parts(name: str) -> tuple[str, str] | None:
    """The period and the field of a date field grouped by period (``DAY(Test_Start_Time)`` -> day, Test_Start_Time)."""
    match = _DATE_BIN_PATTERN.match(str(name or ""))
    return (match.group(1).casefold(), match.group(2).strip()) if match else None


def date_bin_labels(values: pd.Series, unit: str) -> pd.Series:
    """The period of each time, as text that sorts in time order: 2026-03-01 14:00, 2026-03-01, 2026-W09, 2026-03."""
    try:
        times = pd.to_datetime(values, errors="coerce", format="ISO8601")
    except (TypeError, ValueError):
        times = pd.to_datetime(values, errors="coerce")
    if unit == "week":
        calendar = times.dt.isocalendar()
        labels = calendar["year"].astype("string") + "-W" + calendar["week"].astype("string").str.zfill(2)
        return labels.where(times.notna())
    fmt = {"hour": "%Y-%m-%d %H:00", "day": "%Y-%m-%d", "month": "%Y-%m"}[unit]
    return times.dt.strftime(fmt).where(times.notna())


def date_bin_time(label: str, unit: str) -> float | None:
    """The start of a period written by date_bin_labels, in milliseconds since 1970 (for a time axis)."""
    text = str(label or "").strip()
    try:
        if unit == "week":
            moment = datetime.strptime(f"{text}-1", "%G-W%V-%u")
        elif unit == "month":
            moment = datetime.strptime(text, "%Y-%m")
        elif unit == "hour":
            moment = datetime.strptime(text, "%Y-%m-%d %H:%M")
        else:
            moment = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return (moment - datetime(1970, 1, 1)).total_seconds() * 1000


@dataclass
class Measure:
    """A measure of the chart: the field written on its Measure shelf, its column and its aggregation."""
    field: str
    column: str | None
    aggregation: str | None
    numeric: bool


@dataclass
class _Chart:
    data: pd.DataFrame
    entry: Any
    metric: str | None
    rows: list[str]
    columns: list[str]
    title: str
    multivendor: bool

    @property
    def chart_type(self) -> str:
        return self.entry.chart_type.strip().casefold()

    def setting(self, name: str) -> str:
        reporting = _reporting()
        for condition in reporting.parse_catalog_filters(self.entry.filters):
            if reporting._normalise_catalog_name(condition.column) == name:
                return ", ".join(condition.values).strip()
        return ""

    def measures(self) -> list[Measure]:
        reporting = _reporting()
        parts = [part for part in reporting.KPI_PARTS_SEPARATOR.split(str(self.entry.kpi or "")) if part.strip()]
        result = []
        for index, part in enumerate(parts):
            field, aggregation = reporting.parse_kpi_expression(part)
            column = self.metric if index == 0 and self.metric else (
                reporting._column(self.data, (field,)) or reporting._catalog_column(self.data, field, self.multivendor))
            numeric = bool(column) and column in self.data and pd.to_numeric(self.data[column], errors="coerce").notna().any()
            result.append(Measure(field, column, aggregation, numeric))
        return result

    def aggregation(self, measure: Measure, default_numeric: str = "mean") -> str:
        if measure.aggregation:
            return measure.aggregation
        return default_numeric if measure.numeric else "count"

    def empty(self, message: str = "No valid samples for this KPI and technology filter") -> dict[str, object]:
        reporting = _reporting()
        return {**reporting._chart_payload_base("empty", self.title, self.entry, self.data, self.metric), "message": message}

    def base(self, kind: str, legend: list[dict[str, object]], **extra: object) -> dict[str, object]:
        """The common model of a chart with the legend of what it draws (Format can hide it)."""
        reporting = _reporting()
        # A legend of more entries than a slide can read would take the room of the chart.
        legend = legend if len(legend) <= 2 * MAX_LEGEND_ITEMS else []
        model = reporting._chart_payload_base(kind, self.title, self.entry, self.data, self.metric, show_legend=False)
        model["legend"] = {
            "position": reporting.parse_legend_position(self.entry.legend_position) if legend else "none",
            "format": reporting.label_format_options(self.entry.legend_format),
            "line_markers": bool(extra.pop("line_markers", False)),
            "items": legend,
        }
        model["chart_type"] = self.entry.chart_type
        model.update(extra)
        return model

    def keys(self, columns: list[str]) -> list[tuple[str, ...]]:
        if not columns:
            return [()]
        reporting = _reporting()
        frame = self.data[columns].copy()
        frame.attrs = {}
        return [tuple(reporting._chart_payload_value(value) for value in key)
                for key in reporting._hierarchical_unique_keys(frame, columns)]

    def aggregate(self, column: str, columns: list[str], aggregation: str) -> tuple[dict[tuple[str, ...], float], dict[tuple[str, ...], int]]:
        """The aggregated value and the samples of each key of ``columns``."""
        reporting = _reporting()
        frame = self.data[[*columns, column]].copy()
        frame.attrs = self.data.attrs.copy()
        for item in columns:
            frame[item] = frame[item].map(reporting._chart_payload_value)
        values = reporting._aggregate_metric(frame, columns, column, aggregation)
        counts = reporting._aggregate_metric(frame, columns, column, "count")
        as_key = lambda key: (key if isinstance(key, tuple) else (key,)) if columns else ()
        if not columns:
            return ({(): float(values.iloc[0])} if len(values) and pd.notna(values.iloc[0]) else {},
                    {(): int(counts.iloc[0])} if len(counts) else {})
        return ({as_key(key): float(value) for key, value in values.items() if pd.notna(value)},
                {as_key(key): int(value) for key, value in counts.items()})

    def colours(self, keys: list[tuple[str, ...]], columns: list[str], *, line_chart: bool = False) -> dict[tuple[str, ...], str]:
        """The colour of each key: the Operator and Vendor colours of the workspace, else the series palette."""
        reporting = _reporting()
        if not columns or not keys or keys == [()]:
            return {key: NEUTRAL_COLOURS[0] for key in keys}
        found = reporting._series_colours(keys, columns, self.data, line_chart=line_chart)
        return {key: found.get(key) or NEUTRAL_COLOURS[index % len(NEUTRAL_COLOURS)] for index, key in enumerate(keys)}

    def dimensions(self, columns: list[str]) -> list[list[str]]:
        return _reporting()._payload_dimensions(self.data, columns)

    def declared(self, column: str) -> str:
        declared = self.data.attrs.get("catalogue_dimension_labels", {}).get(column, column)
        return " · ".join(str(item) for item in declared) if isinstance(declared, (tuple, list)) else str(declared)

    def time_axis(self, columns: list[str], keys: list[tuple[str, ...]]) -> dict[str, object] | None:
        """A time axis for keys whose last level is a date field grouped by period: the start of each period."""
        if len(columns) != 1:
            return None
        parts = date_bin_parts(self.declared(columns[-1]))
        if not parts:
            return None
        times = [date_bin_time(key[-1], parts[0]) for key in keys]
        if any(value is None for value in times):
            return None
        return {"unit": parts[0], "times": times}

    def direction(self, measure: Measure | None) -> int:
        """1 when a higher value is better, -1 when lower is, 0 when neither (a count…)."""
        value = self.setting("direction").casefold()
        if value.startswith("higher"):
            return 1
        if value.startswith("lower"):
            return -1
        if value.startswith("neutral"):
            return 0
        from src.modules.design_comments import kpi_semantics

        return kpi_semantics(measure.field if measure else self.title).direction

    def bucket_edges(self) -> list[float]:
        try:
            return list(_reporting()._catalog_bucket_edges(self.entry) or [])
        except ValueError:
            return []


def _decimals(aggregation: str) -> int:
    return 0 if aggregation in {"count", "countd"} else 2


def _label(key: tuple[str, ...]) -> str:
    return " · ".join(value for value in key if value != "(all)") or "(all)"


def _legend(items: list[tuple[str, str]]) -> list[dict[str, object]]:
    seen: dict[str, str] = {}
    for label, colour in items:
        seen.setdefault(str(label), colour)
    return [{"label": label, "colour": colour, "width": 2} for label, colour in seen.items()]


def _padded(low: float, high: float, *, zero: bool = False, pad: float = .06) -> list[float]:
    if zero:
        low, high = min(0.0, low), max(0.0, high)
    if low == high:
        return [low - 1, high + 1]
    span = high - low
    return [low if zero and low == 0 else low - span * pad, high if zero and high == 0 else high + span * pad]


def _axis(chart: _Chart, axis: str, low: float, high: float, *, zero: bool = False) -> list[float]:
    padded = _padded(low, high, zero=zero)
    return _reporting()._configured_axis_domain(chart.entry, axis, padded[0], padded[1])


def colour_scale(values: list[float], direction: int, edges: list[float], *, light: bool = False) -> tuple[Callable[[float], str], list[dict[str, object]]]:
    """The colour of a value and the legend of the scale: the five classes of Buckets when it has four limits (as the
    RF quality classes), else five equal ranges of the values; red to green for a KPI with a direction, blues
    without one."""
    reporting = _reporting()
    palette = (QUALITY_LIGHT_COLOURS if light else QUALITY_COLOURS) if direction else (
        SEQUENTIAL_LIGHT_COLOURS if light else SEQUENTIAL_COLOURS)
    # Low values first: a lower-is-better KPI is green at its lowest values.
    ordered = tuple(reversed(palette)) if direction < 0 else palette
    if len(edges) == 4:
        limits = list(edges)
        labels = reporting._explicit_bucket_labels(limits)
    else:
        # Five classes of as many values each (quintiles), so a few extreme values do not leave every other one in one
        # class; five equal ranges when the values are too few or too alike for them.
        finite = sorted(value for value in values if value is not None and math.isfinite(value))
        low, high = (finite[0], finite[-1]) if finite else (0.0, 1.0)
        if low == high:
            high = low + 1
        limits = [float(value) for value in np.percentile(finite, [20, 40, 60, 80])] if len(set(finite)) >= 5 else []
        if len(limits) != 4 or any(right <= left for left, right in zip([low, *limits], [*limits, high])):
            step = (high - low) / 5
            limits = [low + step * index for index in range(1, 5)]
        span = min(right - left for left, right in zip([low, *limits], [*limits, high]))
        digits = 0 if span >= 10 else 1 if span >= 1 else 2
        bounds = [low, *limits, high]
        labels = [f"{bounds[index]:.{digits}f} – {bounds[index + 1]:.{digits}f}" for index in range(5)]

    def colour(value: float) -> str:
        if value is None or not math.isfinite(value):
            return "#E9EDF0"
        index = sum(value >= limit for limit in limits)
        return ordered[index]

    return colour, [{"label": label, "colour": ordered[index], "width": 2} for index, label in enumerate(labels)]


# -- bars, dots and bullets --------------------------------------------------------------------------------------
def _matrix(chart: _Chart, measure: Measure, aggregation: str) -> dict[str, object]:
    rows, columns = chart.rows, chart.columns
    values, samples = chart.aggregate(measure.column, [*rows, *columns], aggregation)
    row_keys = [key for key in chart.keys(rows) if any((*key, *column) in values for column in chart.keys(columns))]
    column_keys = [key for key in chart.keys(columns) if any((*row, *key) in values for row in row_keys)]
    return {"values": values, "samples": samples, "row_keys": row_keys[:MAX_CATEGORIES], "column_keys": column_keys[:MAX_CATEGORIES]}


def _horizontal_bars(chart: _Chart) -> dict[str, object]:
    measure = chart.measures()[0]
    aggregation = chart.aggregation(measure)
    matrix = _matrix(chart, measure, aggregation)
    values, samples = matrix["values"], matrix["samples"]
    row_keys, column_keys = matrix["row_keys"], matrix["column_keys"]
    if not values or not row_keys:
        return chart.empty()
    order = chart.setting("sort").casefold()
    if order.startswith(("desc", "asc")) and chart.rows:
        best = lambda key: max((values.get((*key, *column), -math.inf) for column in column_keys), default=-math.inf)
        row_keys = sorted(row_keys, key=best, reverse=order.startswith("desc"))
    flat = [(*row, *column) for row in row_keys for column in column_keys if (*row, *column) in values]
    axes = [*chart.rows, *chart.columns]
    # The bars of a row take the colours of their Columns (one per Operator…), else of their row.
    by_column = chart.colours(column_keys, chart.columns) if chart.columns else {}
    by_row = {} if chart.columns else chart.colours(row_keys, chart.rows)
    colours = {key: by_column[key[len(chart.rows):]] if chart.columns else by_row[key[:len(chart.rows)]] for key in flat}
    legend = _legend([(_label(column), by_column[column]) for column in column_keys]) if chart.columns else []
    numbers = list(values.values())
    return chart.base(
        "hbar", legend,
        metric=measure.field.replace("_", " "), aggregation=aggregation, decimals=_decimals(aggregation),
        row_keys=[list(key) for key in row_keys], column_keys=[list(key) for key in column_keys],
        cells=[[values.get((*row, *column)) for column in column_keys] for row in row_keys],
        cell_colours=[[colours.get((*row, *column), NEUTRAL_COLOURS[0]) for column in column_keys] for row in row_keys],
        cell_samples=[[samples.get((*row, *column), 0) for column in column_keys] for row in row_keys],
        domain={"x": _axis(chart, "x", min(numbers), max(numbers), zero=True)},
        dimensions=chart.dimensions(axes),
        bars=[{"key": list(key), "value": values[key], "samples": samples.get(key, 0), "colour": colours[key],
               "legend": _label(key[len(chart.rows):]) if chart.columns else _label(key)} for key in flat],
    )


def _dot_plot(chart: _Chart) -> dict[str, object]:
    measure = chart.measures()[0]
    aggregation = chart.aggregation(measure)
    matrix = _matrix(chart, measure, aggregation)
    values, samples = matrix["values"], matrix["samples"]
    row_keys, column_keys = matrix["row_keys"], matrix["column_keys"]
    if not values or not row_keys:
        return chart.empty()
    colours = chart.colours(column_keys, chart.columns)
    numbers = list(values.values())
    axes = [*chart.rows, *chart.columns]
    return chart.base(
        "dot", _legend([(_label(key), colours[key]) for key in column_keys]) if chart.columns else [],
        metric=measure.field.replace("_", " "), aggregation=aggregation, decimals=_decimals(aggregation),
        row_keys=[list(key) for key in row_keys], column_keys=[list(key) for key in column_keys],
        cells=[[values.get((*row, *column)) for column in column_keys] for row in row_keys],
        cell_colours=[[colours[column] for column in column_keys] for _row in row_keys],
        cell_samples=[[samples.get((*row, *column), 0) for column in column_keys] for row in row_keys],
        domain={"x": _axis(chart, "x", min(numbers), max(numbers))},
        dimensions=chart.dimensions(axes),
        bars=[{"key": [*row, *column], "value": values[(*row, *column)], "samples": samples.get((*row, *column), 0),
               "legend": _label(column)} for row in row_keys for column in column_keys if (*row, *column) in values],
    )


def _campaign_level(chart: _Chart, axes: list[str]) -> int | None:
    reporting = _reporting()
    for index, column in enumerate(axes):
        if reporting._normalise_catalog_name(chart.declared(column)) == "campaign":
            return index
    return None


def _operator_level(chart: _Chart, axes: list[str]) -> int | None:
    reporting = _reporting()
    for index, column in enumerate(axes):
        if reporting._normalise_catalog_name(chart.declared(column)) in {"operator", "operatorvendor", "vendor"}:
            return index
    return None


def _bullet_graph(chart: _Chart) -> dict[str, object]:
    """One bullet per key of Rows and Columns: its value, its target (a number, the previous campaign, the best
    competitor or a second measure) and the classes of Buckets behind it."""
    measures = chart.measures()
    measure = measures[0]
    aggregation = chart.aggregation(measure)
    axes = [*chart.rows, *chart.columns]
    values, samples = chart.aggregate(measure.column, axes, aggregation)
    if not values:
        return chart.empty()
    keys = [key for key in chart.keys(axes) if key in values]
    direction = chart.direction(measure)
    higher = direction >= 0
    target_setting = chart.setting("target")
    targets: dict[tuple[str, ...], float] = {}
    target_label = ""
    shown = keys
    if len(measures) > 1 and measures[1].column:
        target_values, _counts = chart.aggregate(measures[1].column, axes, chart.aggregation(measures[1]))
        targets = {key: value for key, value in target_values.items()}
        target_label = measures[1].field.replace("_", " ")
    elif target_setting.casefold().startswith("previous"):
        level = _campaign_level(chart, axes)
        if level is not None:
            campaigns = list(dict.fromkeys(key[level] for key in keys))
            if len(campaigns) > 1:
                latest, previous = campaigns[-1], campaigns[-2]
                shown = [key for key in keys if key[level] == latest]
                for key in shown:
                    before = (*key[:level], previous, *key[level + 1:])
                    if before in values:
                        targets[key] = values[before]
                target_label = f"Previous campaign ({previous})"
    elif target_setting.casefold().startswith("best"):
        level = _operator_level(chart, axes)
        if level is not None:
            for key in keys:
                others = [value for other, value in values.items()
                          if other[level] != key[level] and other[:level] + other[level + 1:] == key[:level] + key[level + 1:]]
                if others:
                    targets[key] = max(others) if higher else min(others)
            target_label = "Best competitor"
    elif target_setting:
        try:
            fixed = float(target_setting)
        except ValueError:
            fixed = None
        if fixed is not None:
            targets = {key: fixed for key in keys}
            target_label = f"Target {fixed:g}"
    numbers = [values[key] for key in shown] + [targets[key] for key in shown if key in targets]
    edges = chart.bucket_edges()
    low, high = min(numbers), max(numbers)
    if edges:
        low, high = min(low, edges[0]), max(high, edges[-1])
    domain = _axis(chart, "x", low, high, zero=True)
    bands = []
    if edges:
        limits = [domain[0], *[edge for edge in edges if domain[0] < edge < domain[1]], domain[1]]
        greys = ("#D3D9DE", "#DFE4E8", "#E8ECEF", "#F0F3F5", "#F6F8F9")
        ordered = greys if higher else tuple(reversed(greys))
        bands = [{"low": low_edge, "high": high_edge, "colour": ordered[min(index, len(ordered) - 1)]}
                 for index, (low_edge, high_edge) in enumerate(zip(limits, limits[1:]))]
    colours = chart.colours(shown, axes)
    legend = [{"label": target_label, "colour": "#1F2D3A", "width": 4, "marker": "target"}] if target_label else []
    return chart.base(
        "bullet", legend,
        metric=measure.field.replace("_", " "), aggregation=aggregation, decimals=_decimals(aggregation),
        direction=direction, domain={"x": domain}, bands=bands, target_label=target_label,
        items=[{"key": list(key), "label": _label(key), "value": values[key], "target": targets.get(key),
                "samples": samples.get(key, 0), "colour": colours[key]} for key in shown[:MAX_CATEGORIES]],
        dimensions=chart.dimensions(axes),
        bars=[{"key": list(key), "value": values[key], "samples": samples.get(key, 0), "legend": _label(key)} for key in shown],
    )


# -- heat maps and coloured tables -------------------------------------------------------------------------------
def _heat_map(chart: _Chart) -> dict[str, object]:
    """Squares in a grid of Rows by Columns: coloured by the first measure and sized by the second (or the samples)."""
    measures = chart.measures()
    measure = measures[0]
    aggregation = chart.aggregation(measure)
    matrix = _matrix(chart, measure, aggregation)
    values, samples = matrix["values"], matrix["samples"]
    row_keys, column_keys = matrix["row_keys"], matrix["column_keys"]
    if not values:
        return chart.empty()
    sizes_source: dict[tuple[str, ...], float] = {key: float(count) for key, count in samples.items()}
    size_label = "Samples"
    if len(measures) > 1 and measures[1].column:
        sizes_source, _counts = chart.aggregate(measures[1].column, [*chart.rows, *chart.columns], chart.aggregation(measures[1], "sum"))
        size_label = measures[1].field.replace("_", " ")
    largest = max((abs(value) for value in sizes_source.values()), default=1.0) or 1.0
    direction = chart.direction(measure)
    colour, legend = colour_scale(list(values.values()), direction, chart.bucket_edges())
    cells = [[values.get((*row, *column)) for column in column_keys] for row in row_keys]
    return chart.base(
        "heat_map", legend,
        metric=measure.field.replace("_", " "), aggregation=aggregation, decimals=_decimals(aggregation), size_label=size_label,
        row_keys=[list(key) for key in row_keys], column_keys=[list(key) for key in column_keys],
        cells=cells,
        cell_colours=[[colour(value) if value is not None else "#E9EDF0" for value in row] for row in cells],
        cell_samples=[[samples.get((*row, *column), 0) for column in column_keys] for row in row_keys],
        sizes=[[math.sqrt(abs(sizes_source.get((*row, *column), 0.0)) / largest) for column in column_keys] for row in row_keys],
        dimensions=chart.dimensions([*chart.rows, *chart.columns]),
        bars=[{"key": [*row, *column], "value": values[(*row, *column)], "samples": samples.get((*row, *column), 0)}
              for row in row_keys for column in column_keys if (*row, *column) in values],
    )


def decorate_table(model: dict[str, object], chart_type: str, numbers: list[list[float | None]], metric: str, entry: Any) -> dict[str, object]:
    """A Highlight Table colours each value cell by its value; a Bar Table draws a bar in it, as long as the largest
    value of its column."""
    finite = [value for row in numbers for value in row if value is not None and math.isfinite(value)]
    if chart_type == "highlight table":
        from src.modules.design_comments import kpi_semantics

        setting = _Chart(pd.DataFrame(), entry, None, [], [], "", False).setting("direction").casefold()
        direction = 1 if setting.startswith("higher") else -1 if setting.startswith("lower") else 0 if setting.startswith("neutral") else kpi_semantics(metric).direction
        try:
            edges = list(_reporting()._catalog_bucket_edges(entry) or [])
        except ValueError:
            edges = []
        colour, legend = colour_scale(finite, direction, edges, light=True)
        model["cell_style"] = "highlight"
        model["cell_colours"] = [[colour(value) if value is not None else None for value in row] for row in numbers]
        model["legend"] = {**model.get("legend", {}), "items": legend,
                           "position": model.get("legend", {}).get("position") or "top"}
    else:
        columns = max((len(row) for row in numbers), default=0)
        extents = [max((abs(row[index]) for row in numbers if index < len(row) and row[index] is not None), default=0.0)
                   for index in range(columns)]
        model["cell_style"] = "bar"
        model["column_extents"] = extents
        model["bar_colour"] = "#A9C6E8"
    model["cell_numbers"] = numbers
    model["chart_type"] = entry.chart_type
    return model


# -- pies --------------------------------------------------------------------------------------------------------
def _pie(chart: _Chart) -> dict[str, object]:
    """A pie (or donut) for each key of Rows: the share of each value of a dimension measured, or of each key of
    Columns by the aggregated measure (its samples unless Sum or Count is chosen)."""
    reporting = _reporting()
    measure = chart.measures()[0]
    rows = chart.rows
    pies: list[dict[str, object]] = []
    slices: list[tuple[str, str]] = []
    records = []
    if not measure.numeric:
        state_data, states, colours = reporting._status_chart_categories(
            chart.data[[*rows, measure.column]].copy(), measure.column, quality=False, threshold=0.0)
        state_data = state_data.dropna(subset=["state"])
        if state_data.empty:
            return chart.empty()
        for column in rows:
            state_data[column] = state_data[column].map(reporting._chart_payload_value)
        counts = state_data.groupby([*rows, "state"], sort=False, dropna=False).size() if rows else state_data.groupby("state").size()
        colour_of = dict(zip(states, colours))
        slices = [(state, colour_of[state]) for state in states]
        for row in chart.keys(rows):
            row_counts = [int(counts.get((*row, state) if rows else state, 0)) for state in states]
            total = sum(row_counts)
            if not total:
                continue
            pies.append({"key": list(row), "label": _label(row), "total": total,
                         "slices": [{"name": state, "value": count, "share": count / total, "colour": colour_of[state]}
                                    for state, count in zip(states, row_counts) if count]})
            records.append({"key": list(row), "shares": [count / total for count in row_counts], "samples": total})
        state_names = list(states)
    else:
        aggregation = measure.aggregation if measure.aggregation in {"sum", "count", "countd"} else "count"
        values, _samples = chart.aggregate(measure.column, [*rows, *chart.columns], aggregation)
        column_keys = chart.keys(chart.columns)
        colours = chart.colours(column_keys, chart.columns)
        slices = [(_label(key), colours[key]) for key in column_keys]
        for row in chart.keys(rows):
            parts = [max(0.0, values.get((*row, *column), 0.0)) for column in column_keys]
            total = sum(parts)
            if not total:
                continue
            pies.append({"key": list(row), "label": _label(row), "total": total,
                         "slices": [{"name": _label(column), "value": value, "share": value / total, "colour": colours[column]}
                                    for column, value in zip(column_keys, parts) if value]})
            records.append({"key": list(row), "shares": [value / total for value in parts], "samples": int(total)})
        state_names = [_label(key) for key in column_keys]
    if not pies:
        return chart.empty()
    return chart.base(
        "pie", _legend(slices), donut=chart.chart_type == "donut", metric=measure.field.replace("_", " "),
        pies=pies[:24], states=[{"name": name, "colour": colour} for name, colour in slices],
        state_names=state_names, records=records, dimensions=chart.dimensions(rows),
    )


# -- lines, areas and bars with a line ---------------------------------------------------------------------------
def _x_axis(chart: _Chart, keys: list[tuple[str, ...]]) -> dict[str, object]:
    axis = {"x_keys": [list(key) for key in keys], "x_dimensions": chart.dimensions(chart.columns)}
    time = chart.time_axis(chart.columns, keys)
    if time:
        axis["x_time"] = time["times"]
        axis["x_unit"] = time["unit"]
    return axis


def _lines(chart: _Chart) -> dict[str, object]:
    """One line per key of Rows across the keys of Columns (a time axis when they are a date grouped by period);
    Dual Lines draws a second measure on its own axis, dashed."""
    measures = [item for item in chart.measures() if item.column]
    if not measures:
        return chart.empty()
    dual = chart.chart_type == "dual lines" and len(measures) > 1
    used = measures[:2] if dual else measures[:1]
    x_keys = chart.keys(chart.columns)
    row_keys = chart.keys(chart.rows)
    colours = chart.colours(row_keys, chart.rows, line_chart=True)
    series = []
    domains: list[list[float]] = []
    for axis_index, measure in enumerate(used):
        aggregation = chart.aggregation(measure)
        values, samples = chart.aggregate(measure.column, [*chart.rows, *chart.columns], aggregation)
        numbers = list(values.values())
        if not numbers:
            continue
        domains.append(_axis(chart, "y", min(numbers), max(numbers), zero=aggregation in {"count", "countd", "sum"}))
        for row in row_keys:
            points = [values.get((*row, *column)) for column in x_keys]
            if all(value is None for value in points):
                continue
            name = _label(row) if chart.rows else measure.field.replace("_", " ")
            if dual:
                name = f"{name} · {measure.field.replace('_', ' ')}" if chart.rows else measure.field.replace("_", " ")
            series.append({
                "key": list(row), "name": name, "colour": colours[row] if chart.rows else NEUTRAL_COLOURS[axis_index],
                "values": points, "samples": [samples.get((*row, *column), 0) for column in x_keys],
                "axis": axis_index, "dash": [10, 6] if axis_index else [], "width": 4,
                "metric": measure.field.replace("_", " "), "aggregation": aggregation,
            })
    if not series:
        return chart.empty()
    legend = [{"label": item["name"], "colour": item["colour"], "width": item["width"], "dash": item["dash"]} for item in series]
    first = used[0]
    return chart.base(
        "lines", legend if len(series) > 1 or dual else [], line_markers=True,
        metric=first.field.replace("_", " "), metric2=used[1].field.replace("_", " ") if dual else "",
        aggregation=chart.aggregation(first), decimals=_decimals(chart.aggregation(first)),
        domain={"y": domains[0], **({"y2": domains[1]} if dual and len(domains) > 1 else {})},
        series=series, dimensions=chart.dimensions([*chart.rows, *chart.columns]), **_x_axis(chart, x_keys),
        bars=[{"key": [*item["key"], *x_keys[index]], "value": value, "samples": item["samples"][index], "legend": item["name"]}
              for item in series if item["axis"] == 0 for index, value in enumerate(item["values"]) if value is not None],
    )


def _areas(chart: _Chart) -> dict[str, object]:
    """Stacked areas across the keys of Columns: one per value of a dimension measured (one chart per key of Rows), or
    one per key of Rows by the aggregated measure; 100% Stacked Areas draws the shares."""
    reporting = _reporting()
    measure = chart.measures()[0]
    percent = chart.chart_type == "100% stacked areas"
    x_keys = chart.keys(chart.columns)
    panes = []
    legend_items: list[tuple[str, str]] = []
    if not measure.numeric:
        state_data, states, colours = reporting._status_chart_categories(
            chart.data[[*chart.rows, *chart.columns, measure.column]].copy(), measure.column, quality=False, threshold=0.0)
        state_data = state_data.dropna(subset=["state"])
        if state_data.empty:
            return chart.empty()
        for column in [*chart.rows, *chart.columns]:
            state_data[column] = state_data[column].map(reporting._chart_payload_value)
        group = [*chart.rows, *chart.columns, "state"]
        counts = state_data.groupby(group, sort=False, dropna=False).size()
        legend_items = list(zip(states, colours))
        for row in chart.keys(chart.rows):
            series = []
            for state, colour in zip(states, colours):
                points = [float(counts.get((*row, *column, state), 0)) for column in x_keys]
                series.append({"key": [state], "name": state, "colour": colour, "values": points})
            totals = [sum(item["values"][index] for item in series) for index in range(len(x_keys))]
            if not any(totals):
                continue
            panes.append({"key": list(row), "label": _label(row) if chart.rows else "", "series": series, "totals": totals})
        aggregation = "count"
    else:
        aggregation = chart.aggregation(measure, "sum" if not percent else "sum")
        values, _samples = chart.aggregate(measure.column, [*chart.rows, *chart.columns], aggregation)
        row_keys = chart.keys(chart.rows)
        colours = chart.colours(row_keys, chart.rows)
        series = []
        for row in row_keys:
            points = [max(0.0, values.get((*row, *column), 0.0)) for column in x_keys]
            if any(points):
                series.append({"key": list(row), "name": _label(row) if chart.rows else measure.field.replace("_", " "),
                               "colour": colours[row], "values": points})
        legend_items = [(item["name"], item["colour"]) for item in series]
        if series:
            panes.append({"key": [], "label": "", "series": series,
                          "totals": [sum(item["values"][index] for item in series) for index in range(len(x_keys))]})
    if not panes:
        return chart.empty()
    highest = max(max(pane["totals"]) for pane in panes) or 1.0
    domain = reporting._configured_axis_domain(chart.entry, "y", 0.0, 1.0, percentage=True) if percent else _axis(chart, "y", 0.0, highest, zero=True)
    records = []
    for pane in panes:
        for index, column in enumerate(x_keys):
            total = pane["totals"][index]
            if total:
                records.append({"key": [*pane["key"], *column], "shares": [item["values"][index] / total for item in pane["series"]],
                                "samples": int(total)})
    return chart.base(
        "areas", _legend(legend_items), percent=percent, metric=measure.field.replace("_", " "),
        aggregation=aggregation, decimals=_decimals(aggregation), domain={"y": domain}, panes=panes[:12],
        states=[{"name": name, "colour": colour} for name, colour in legend_items], records=records,
        dimensions=chart.dimensions([*chart.rows, *chart.columns] if not measure.numeric else chart.columns), **_x_axis(chart, x_keys),
    )


def _bars_and_line(chart: _Chart) -> dict[str, object]:
    """Bars of the first measure (left axis) and a line of the second (right axis) across the keys of Columns; the keys
    of Rows group the bars side by side and draw one line each."""
    measures = [item for item in chart.measures() if item.column]
    if len(measures) < 2:
        return chart.empty("Bars and Line needs two measures: the bars, then the line")
    x_keys = chart.keys(chart.columns)
    row_keys = chart.keys(chart.rows)
    colours = chart.colours(row_keys, chart.rows)
    axes = [*chart.rows, *chart.columns]
    bar_measure, line_measure = measures[0], measures[1]
    bar_aggregation, line_aggregation = chart.aggregation(bar_measure), chart.aggregation(line_measure)
    bar_values, bar_samples = chart.aggregate(bar_measure.column, axes, bar_aggregation)
    line_values, line_samples = chart.aggregate(line_measure.column, axes, line_aggregation)
    if not bar_values and not line_values:
        return chart.empty()
    line_colour = "#1F2D3A"
    bars, lines = [], []
    for index, row in enumerate(row_keys):
        name = _label(row) if chart.rows else bar_measure.field.replace("_", " ")
        bar_colour = colours[row] if chart.rows else NEUTRAL_COLOURS[0]
        bars.append({"key": list(row), "name": name, "colour": bar_colour,
                     "values": [bar_values.get((*row, *column)) for column in x_keys],
                     "samples": [bar_samples.get((*row, *column), 0) for column in x_keys]})
        lines.append({"key": list(row), "name": f"{_label(row)} · {line_measure.field.replace('_', ' ')}" if chart.rows else line_measure.field.replace("_", " "),
                      "colour": _darker(bar_colour) if chart.rows else line_colour,
                      "values": [line_values.get((*row, *column)) for column in x_keys],
                      "samples": [line_samples.get((*row, *column), 0) for column in x_keys], "width": 4})
    bar_numbers = [value for value in bar_values.values()]
    line_numbers = [value for value in line_values.values()]
    legend = [*({"label": item["name"], "colour": item["colour"], "width": 2} for item in bars),
              *({"label": item["name"], "colour": item["colour"], "width": 4} for item in lines)]
    return chart.base(
        "combo", legend, line_markers=False,
        metric=bar_measure.field.replace("_", " "), metric2=line_measure.field.replace("_", " "),
        aggregation=bar_aggregation, aggregation2=line_aggregation,
        decimals=_decimals(bar_aggregation), decimals2=_decimals(line_aggregation),
        domain={"y": _axis(chart, "y", min(bar_numbers or [0.0]), max(bar_numbers or [1.0]), zero=True),
                "y2": _padded(min(line_numbers or [0.0]), max(line_numbers or [1.0]))},
        bar_series=bars, line_series=lines, dimensions=chart.dimensions(axes), **_x_axis(chart, x_keys),
        bars=[{"key": [*item["key"], *x_keys[index]], "value": value, "samples": item["samples"][index], "legend": item["name"]}
              for item in bars for index, value in enumerate(item["values"]) if value is not None],
    )


def _darker(colour: str, amount: float = .35) -> str:
    text = str(colour or "").lstrip("#")
    if len(text) != 6:
        return "#1F2D3A"
    channels = [int(text[index:index + 2], 16) for index in (0, 2, 4)]
    return "#" + "".join(f"{round(channel * (1 - amount)):02X}" for channel in channels)


# -- box plots ---------------------------------------------------------------------------------------------------
def _box_plot(chart: _Chart) -> dict[str, object]:
    """A box per key of Rows and Columns: its quartiles, its median and its whiskers (P10 to P90 unless Whiskers
    says otherwise), with the mean marked."""
    measure = chart.measures()[0]
    axes = [*chart.rows, *chart.columns]
    if not measure.column or not measure.numeric:
        return chart.empty("Box Plot needs a numeric measure")
    reporting = _reporting()
    frame = chart.data[[*axes, measure.column]].copy()
    frame[measure.column] = pd.to_numeric(frame[measure.column], errors="coerce")
    frame = frame.dropna(subset=[measure.column])
    if frame.empty:
        return chart.empty()
    for column in axes:
        frame[column] = frame[column].map(reporting._chart_payload_value)
    whisker_text = re.sub(r"\s+", " ", chart.setting("whiskers").casefold().replace("–", "-").replace("×", "")).strip()
    whisker_key = next((key for key in WHISKERS if key.replace(" ", "") == whisker_text.replace(" ", "")), "p10-p90")
    keys = [key for key in chart.keys(axes)]
    grouped = frame.groupby(axes, sort=False)[measure.column] if axes else None
    colours = chart.colours(keys, axes)
    boxes, series = [], []
    for key in keys[:MAX_CATEGORIES]:
        try:
            values = (grouped.get_group(key) if axes else frame[measure.column]).to_numpy(dtype=float)
        except KeyError:
            continue
        if not len(values):
            continue
        q1, median, q3 = (float(value) for value in np.percentile(values, [25, 50, 75]))
        if WHISKERS[whisker_key] is None:
            reach = 1.5 * (q3 - q1)
            inside = values[(values >= q1 - reach) & (values <= q3 + reach)]
            low, high = float(inside.min()), float(inside.max())
        else:
            low, high = (float(value) for value in np.percentile(values, list(WHISKERS[whisker_key])))
        p10, p90 = (float(value) for value in np.percentile(values, [10, 90]))
        boxes.append({"key": list(key), "label": _label(key), "low": low, "q1": q1, "median": median, "q3": q3, "high": high,
                      "mean": float(values.mean()), "n": int(len(values)), "colour": colours[key]})
        series.append({"key": list(key), "name": _label(key), "stats": {"n": int(len(values)), "mean": float(values.mean()),
                                                                          "p10": p10, "p50": median, "p90": p90}})
    if not boxes:
        return chart.empty()
    low = min(box["low"] for box in boxes)
    high = max(box["high"] for box in boxes)
    labels = {"p10-p90": "P10 – P90", "p5-p95": "P5 – P95", "p25-p75": "P25 – P75", "min-max": "Min – Max", "1.5 iqr": "1.5 × IQR"}
    return chart.base(
        "box", [], metric=measure.field.replace("_", " "), whiskers=labels[whisker_key],
        keys=[list(key) for key in keys], boxes=boxes, axis_columns=axes, domain={"y": _axis(chart, "y", low, high)},
        dimensions=chart.dimensions(axes), series=series,
    )


# -- maps --------------------------------------------------------------------------------------------------------
def _basemap(lon_low: float, lon_high: float, lat_low: float, lat_high: float) -> dict[str, object]:
    reporting = _reporting()
    lon_padding = max((lon_high - lon_low) * .06, .004)
    lat_padding = max((lat_high - lat_low) * .06, .004)
    zoom, tile_left, tile_top, tile_right, tile_bottom, top_left, bottom_right = reporting._osm_map_tile_geometry(
        lon_low - lon_padding, lon_high + lon_padding, lat_low - lat_padding, lat_high + lat_padding)
    return {
        "provider": "OpenStreetMap", "url_template": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors", "zoom": zoom,
        "tile_range": [tile_left, tile_top, tile_right, tile_bottom], "world_bounds": [*top_left, *bottom_right],
        "tile_size": reporting.OSM_TILE_SIZE,
    }


def _symbol_map(chart: _Chart) -> dict[str, object]:
    """A circle per place (each key of Rows, or squares of a grid without them) at the middle of its samples: as large
    as its samples, coloured by a third measure (its classes with Buckets) or one colour; one map per key of Columns."""
    reporting = _reporting()
    measures = chart.measures()
    if len(measures) < 2 or not measures[0].column or not measures[1].column:
        return chart.empty("Symbol Map needs a latitude and a longitude on Measure")
    latitude, longitude = measures[0].column, measures[1].column
    colour_measure = measures[2] if len(measures) > 2 and measures[2].column else None
    columns = [latitude, longitude, *chart.rows, *chart.columns, *([colour_measure.column] if colour_measure else [])]
    frame = chart.data[list(dict.fromkeys(columns))].copy()
    frame[latitude] = pd.to_numeric(frame[latitude], errors="coerce")
    frame[longitude] = pd.to_numeric(frame[longitude], errors="coerce")
    frame = frame.dropna(subset=[latitude, longitude])
    frame = frame[frame[latitude].between(-90, 90) & frame[longitude].between(-180, 180)]
    if frame.empty:
        return chart.empty("No valid map coordinates are available")
    for column in [*chart.rows, *chart.columns]:
        frame[column] = frame[column].map(reporting._chart_payload_value)
    place_columns = list(chart.rows)
    if not place_columns:
        # Without places, squares of a grid of about 30 by 30 over the samples.
        span = max(float(frame[longitude].max() - frame[longitude].min()), float(frame[latitude].max() - frame[latitude].min()), 1e-4)
        cell = span / 30
        frame["__symbol_cell"] = (np.floor(frame[latitude] / cell).astype(int).astype(str) + ":"
                                  + np.floor(frame[longitude] / cell).astype(int).astype(str))
        place_columns = ["__symbol_cell"]
    if colour_measure:
        frame[colour_measure.column] = pd.to_numeric(frame[colour_measure.column], errors="coerce")
    group_columns = [*chart.columns, *place_columns]
    aggregations = {latitude: "mean", longitude: "mean"}
    grouped = frame.groupby(group_columns, sort=False)
    table = grouped.agg(aggregations)
    table["__n"] = grouped.size()
    colour_aggregation = chart.aggregation(colour_measure) if colour_measure else None
    if colour_measure:
        method = {"mean": "mean", "median": "median", "sum": "sum", "min": "min", "max": "max", "count": "count", "countd": "nunique"}.get(colour_aggregation, "mean")
        table["__value"] = getattr(grouped[colour_measure.column], method)()
    table = table.reset_index()
    largest = max(int(table["__n"].max()), 1)
    if colour_measure:
        colour, legend = colour_scale([float(value) for value in table["__value"].dropna()], chart.direction(colour_measure), chart.bucket_edges())
    else:
        colour, legend = (lambda _value: "#2A6BB0"), []
    panels = []
    for column_key in chart.keys(chart.columns)[:MAX_MAP_PANELS]:
        rows = table
        for column, value in zip(chart.columns, column_key):
            rows = rows[rows[column] == value]
        if rows.empty:
            continue
        rows = rows.sort_values("__n", ascending=False).head(MAX_SYMBOLS)
        symbols = []
        for record in rows.itertuples(index=False):
            values = dict(zip(rows.columns, record))
            value = values.get("__value") if colour_measure else None
            place = tuple(str(values[column]) for column in place_columns)
            symbols.append({
                "label": _label(place) if chart.rows else "", "lat": float(values[latitude]), "lon": float(values[longitude]),
                "n": int(values["__n"]), "size": math.sqrt(int(values["__n"]) / largest),
                "value": None if value is None or pd.isna(value) else float(value),
                "colour": colour(float(value)) if value is not None and not pd.isna(value) else "#2A6BB0",
            })
        panels.append({"key": list(column_key), "label": _label(column_key) if chart.columns else "", "symbols": symbols})
    if not panels:
        return chart.empty("No valid map coordinates are available")
    lat_low, lat_high = float(frame[latitude].min()), float(frame[latitude].max())
    lon_low, lon_high = float(frame[longitude].min()), float(frame[longitude].max())
    return chart.base(
        "symbol_map", legend, panels=panels, basemap=_basemap(lon_low, lon_high, lat_low, lat_high),
        domain={"x": [lon_low, lon_high], "y": [lat_low, lat_high]},
        colour_metric=colour_measure.field.replace("_", " ") if colour_measure else "",
        aggregation=colour_aggregation or "count", place=" · ".join(chart.declared(column) for column in chart.rows) or "Grid",
        dimensions=chart.dimensions(chart.rows),
    )


@lru_cache(maxsize=16)
def _area_rings(database: str, country: str, signature: str) -> dict[str, list]:
    """The polygons of the Map Areas of a country: the workspace's own layer, else the ones shipped."""
    from src.modules import map_areas

    if database and signature:
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            try:
                row = connection.execute(f"SELECT boundaries FROM {map_areas.TABLE} WHERE country_code = ?", (country,)).fetchone()
            finally:
                connection.close()
        except sqlite3.Error:
            row = None
        if row and row[0]:
            return map_areas._unpack(row[0])
    return map_areas.bundled_rings(country)


def _filled_map(chart: _Chart) -> dict[str, object]:
    """Each Map Area coloured by the aggregated measure of its samples (the classes of Buckets, else five ranges); one map
    per key of Columns."""
    reporting = _reporting()
    measure = chart.measures()[0]
    area_column = reporting._column(chart.data, ("Map_Area",))
    country_column = reporting._column(chart.data, ("Map_Area_Country",))
    if not measure.column:
        return chart.empty()
    if not area_column:
        return chart.empty("The CDRs have no Map Areas yet: they are placed in the background")
    aggregation = chart.aggregation(measure)
    frame = chart.data[list(dict.fromkeys([area_column, *([country_column] if country_column else []), *chart.columns, measure.column]))].copy()
    frame = frame[frame[area_column].notna() & frame[area_column].astype(str).str.strip().ne("")]
    if frame.empty:
        return chart.empty("The CDRs have no Map Areas yet: they are placed in the background")
    for column in chart.columns:
        frame[column] = frame[column].map(reporting._chart_payload_value)
    frame.attrs = chart.data.attrs.copy()
    values = reporting._aggregate_metric(frame, [*chart.columns, area_column], measure.column, aggregation).dropna()
    samples = reporting._aggregate_metric(frame, [*chart.columns, area_column], measure.column, "count")
    if values.empty:
        return chart.empty()
    colour, legend = colour_scale([float(value) for value in values], chart.direction(measure), chart.bucket_edges())
    countries = (frame.groupby(area_column)[country_column].first().astype(str).to_dict() if country_column else {})
    settings = chart.data.attrs.get("map_areas") or {}
    database = str(settings.get("db") or "")
    layers = settings.get("layers") or {}
    used = set(str(name) for name in frame[area_column].astype(str).unique())
    polygons: dict[str, list] = {}
    for country in sorted(set(countries.values()) or {""}):
        if not country:
            continue
        rings = _area_rings(database, country, str(layers.get(country) or ""))
        for name, parts in rings.items():
            if name in used:
                polygons[name] = parts
    if not polygons:
        return chart.empty("No polygon of the Map Areas of these CDRs is available")
    panels = []
    for column_key in chart.keys(chart.columns)[:MAX_MAP_PANELS]:
        areas = []
        for key, value in values.items():
            key = key if isinstance(key, tuple) else (key,)
            if tuple(key[:len(chart.columns)]) != column_key:
                continue
            name = str(key[-1])
            if name not in polygons:
                continue
            areas.append({"name": name, "value": float(value), "n": int(samples.get(key if len(key) > 1 else key[0], 0)),
                          "colour": colour(float(value))})
        if areas:
            panels.append({"key": list(column_key), "label": _label(column_key) if chart.columns else "", "areas": areas})
    if not panels:
        return chart.empty()
    points = [point for parts in polygons.values() for ring in parts for point in ring]
    lons = [float(point[0]) for point in points]
    lats = [float(point[1]) for point in points]
    return chart.base(
        "filled_map", legend, panels=panels, polygons=polygons, metric=measure.field.replace("_", " "),
        aggregation=aggregation, decimals=_decimals(aggregation),
        basemap=_basemap(min(lons), max(lons), min(lats), max(lats)),
        domain={"x": [min(lons), max(lons)], "y": [min(lats), max(lats)]},
        dimensions=chart.dimensions(chart.columns),
    )


# -- treemaps, bubbles, Sankey and Gantt -------------------------------------------------------------------------
def _sized(chart: _Chart) -> tuple[Measure, str, Measure | None, str | None]:
    """What sizes the rectangles or bubbles (the samples, unless Sum or Count is chosen) and what colours them (a second
    measure, or the first one when it is averaged)."""
    measures = [item for item in chart.measures() if item.column]
    first = measures[0]
    size_aggregation = first.aggregation if first.aggregation in {"sum", "count", "countd"} else "count"
    colour_measure, colour_aggregation = None, None
    if len(measures) > 1:
        colour_measure, colour_aggregation = measures[1], chart.aggregation(measures[1])
    elif first.aggregation in {"mean", "median", "min", "max"} and first.numeric:
        colour_measure, colour_aggregation = first, first.aggregation
    return first, size_aggregation, colour_measure, colour_aggregation


def _colour_level(chart: _Chart, levels: list[str]) -> int:
    """The level whose values colour the items: an Operator or Vendor one (the colours of the workspace), else the first."""
    level = _operator_level(chart, levels)
    return 0 if level is None else level


MAX_LEGEND_ITEMS = 24


def _treemap(chart: _Chart) -> dict[str, object]:
    """Rectangles nested by the levels of Rows then Columns, as large as their samples (or the sum chosen) and coloured
    by their first level, or by a colour measure."""
    if not [item for item in chart.measures() if item.column]:
        return chart.empty()
    levels = [*chart.rows, *chart.columns]
    if not levels:
        return chart.empty("Treemap needs a field on Rows or Columns")
    size_measure, size_aggregation, colour_measure, colour_aggregation = _sized(chart)
    sizes, _samples = chart.aggregate(size_measure.column, levels, size_aggregation)
    colour_values = chart.aggregate(colour_measure.column, levels, colour_aggregation)[0] if colour_measure else {}
    leaves = [key for key in chart.keys(levels) if sizes.get(key, 0) > 0]
    leaves = sorted(leaves, key=lambda key: -sizes[key])[:MAX_TREEMAP_ITEMS]
    if not leaves:
        return chart.empty()
    level = _colour_level(chart, levels)
    first_keys = list(dict.fromkeys((key[level],) for key in leaves))
    first_colours = chart.colours(first_keys, levels[level:level + 1])
    if colour_measure:
        colour, legend = colour_scale(list(colour_values.values()), chart.direction(colour_measure), chart.bucket_edges())
    else:
        colour, legend = None, (_legend([(key[0], first_colours[key]) for key in first_keys]) if len(first_keys) <= MAX_LEGEND_ITEMS else [])

    def node(prefix: tuple[str, ...]) -> list[dict[str, object]]:
        depth = len(prefix)
        children: dict[str, list[tuple[str, ...]]] = {}
        for key in leaves:
            if key[:depth] == prefix:
                children.setdefault(key[depth], []).append(key)
        result = []
        for name, keys in children.items():
            value = sum(sizes[key] for key in keys)
            item: dict[str, object] = {"name": name, "value": value}
            if depth + 1 < len(levels):
                item["children"] = node((*prefix, name))
            else:
                key = (*prefix, name)
                tint = colour_values.get(key)
                item.update({"key": list(key), "colour_value": tint,
                             "colour": colour(tint) if colour and tint is not None else first_colours[(key[level],)]})
            result.append(item)
        return sorted(result, key=lambda item: -float(item["value"]))

    return chart.base(
        "treemap", legend, nodes=node(()), metric=size_measure.field.replace("_", " "), aggregation=size_aggregation,
        decimals=_decimals(size_aggregation), colour_metric=colour_measure.field.replace("_", " ") if colour_measure else "",
        colour_aggregation=colour_aggregation or "", levels=[chart.declared(column) for column in levels],
        dimensions=chart.dimensions(levels),
        records=[{"key": list(key), "value": sizes[key]} for key in leaves],
    )


def _packed_bubbles(chart: _Chart) -> dict[str, object]:
    """A bubble per key of Rows and Columns, as large as its samples (or the sum chosen), coloured by its first level
    or by a colour measure."""
    if not [item for item in chart.measures() if item.column]:
        return chart.empty()
    levels = [*chart.rows, *chart.columns]
    if not levels:
        return chart.empty("Packed Bubbles needs a field on Rows or Columns")
    size_measure, size_aggregation, colour_measure, colour_aggregation = _sized(chart)
    sizes, _samples = chart.aggregate(size_measure.column, levels, size_aggregation)
    colour_values = chart.aggregate(colour_measure.column, levels, colour_aggregation)[0] if colour_measure else {}
    keys = sorted([key for key in chart.keys(levels) if sizes.get(key, 0) > 0], key=lambda key: -sizes[key])[:MAX_BUBBLES]
    if not keys:
        return chart.empty()
    level = _colour_level(chart, levels)
    first_keys = list(dict.fromkeys((key[level],) for key in keys))
    first_colours = chart.colours(first_keys, levels[level:level + 1])
    if colour_measure:
        colour, legend = colour_scale(list(colour_values.values()), chart.direction(colour_measure), chart.bucket_edges())
    else:
        colour, legend = None, (_legend([(key[0], first_colours[key]) for key in first_keys])
                                if len(levels) > 1 and len(first_keys) <= MAX_LEGEND_ITEMS else [])
    return chart.base(
        "bubbles", legend, metric=size_measure.field.replace("_", " "), aggregation=size_aggregation,
        decimals=_decimals(size_aggregation), colour_metric=colour_measure.field.replace("_", " ") if colour_measure else "",
        bubbles=[{"key": list(key), "label": _label(key), "value": sizes[key], "colour_value": colour_values.get(key),
                  "colour": colour(colour_values[key]) if colour and colour_values.get(key) is not None else first_colours[(key[level],)]}
                 for key in keys],
        dimensions=chart.dimensions(levels), records=[{"key": list(key), "value": sizes[key]} for key in keys],
    )


def _sankey(chart: _Chart) -> dict[str, object]:
    """The flows of the samples between the values of two to five levels (Rows then Columns), as wide as their
    samples (or the sum chosen)."""
    reporting = _reporting()
    measures = [item for item in chart.measures() if item.column]
    levels = [*chart.rows, *chart.columns]
    if not measures or len(levels) < 2:
        return chart.empty("Sankey needs two to five fields on Rows and Columns")
    levels = levels[:5]
    measure = measures[0]
    aggregation = measure.aggregation if measure.aggregation in {"sum", "count", "countd"} else "count"
    frame = chart.data[[*levels, measure.column]].copy()
    for column in levels:
        frame[column] = frame[column].map(reporting._chart_payload_value)
    frame.attrs = chart.data.attrs.copy()
    nodes: list[list[dict[str, object]]] = []
    kept: list[set[str]] = []
    for index, column in enumerate(levels):
        totals = reporting._aggregate_metric(frame, [column], measure.column, aggregation)
        totals = totals[totals > 0].sort_values(ascending=False)
        names = [str(name) for name in totals.index[:MAX_SANKEY_NODES]]
        # The values left over are gathered as Other.
        if len(totals) > MAX_SANKEY_NODES:
            frame[column] = frame[column].where(frame[column].isin(names), "Other")
            names.append("Other")
        ordered = [key[0] for key in chart.keys([column]) if key[0] in names] + (["Other"] if "Other" in names else [])
        colours = chart.colours([(name,) for name in ordered], [column]) if index == 0 else {
            (name,): NEUTRAL_COLOURS[position % len(NEUTRAL_COLOURS)] for position, name in enumerate(ordered)}
        nodes.append([{"name": name, "colour": colours[(name,)]} for name in ordered])
        kept.append(set(ordered))
    links = []
    for index in range(len(levels) - 1):
        pair = levels[index:index + 2]
        flows = reporting._aggregate_metric(frame, pair, measure.column, aggregation)
        for (source, target), value in flows.items():
            if value > 0 and str(source) in kept[index] and str(target) in kept[index + 1]:
                links.append({"level": index, "source": str(source), "target": str(target), "value": float(value)})
    if not links:
        return chart.empty()
    for index, level in enumerate(nodes):
        for item in level:
            outgoing = sum(link["value"] for link in links if link["level"] == index and link["source"] == item["name"])
            incoming = sum(link["value"] for link in links if link["level"] == index - 1 and link["target"] == item["name"])
            item["value"] = max(outgoing, incoming)
        nodes[index] = [item for item in level if item["value"] > 0]
    return chart.base(
        "sankey", _legend([(item["name"], item["colour"]) for item in nodes[0]]),
        levels=[chart.declared(column) for column in levels], nodes=nodes, links=links,
        metric=measure.field.replace("_", " "), aggregation=aggregation, decimals=_decimals(aggregation),
        dimensions=chart.dimensions(levels),
    )


def _gantt(chart: _Chart) -> dict[str, object]:
    """A lane per key of Rows with a bar for each run of periods (Date Bin, a day by default) that has samples: from the
    first time to the last one (its end time when a second measure gives it); one colour per key of Columns."""
    reporting = _reporting()
    measures = [item for item in chart.measures() if item.column]
    if not measures:
        return chart.empty("Gantt needs a time on Measure (and its end time as a second measure)")
    unit = chart.setting("datebin").casefold() or "day"
    unit = unit if unit in DATE_BINS else "day"
    start_column = measures[0].column
    end_column = measures[1].column if len(measures) > 1 else None
    frame = chart.data[list(dict.fromkeys([start_column, *([end_column] if end_column else []), *chart.rows, *chart.columns]))].copy()
    frame["__start"] = pd.to_datetime(frame[start_column], errors="coerce", format="ISO8601")
    frame["__end"] = pd.to_datetime(frame[end_column], errors="coerce", format="ISO8601") if end_column else frame["__start"]
    frame["__end"] = frame["__end"].fillna(frame["__start"])
    frame = frame.dropna(subset=["__start"])
    if frame.empty:
        return chart.empty("No valid times on the measure of this Gantt")
    for column in [*chart.rows, *chart.columns]:
        frame[column] = frame[column].map(reporting._chart_payload_value)
    frame["__period"] = date_bin_labels(frame["__start"], unit)
    lanes_keys = chart.keys(chart.rows)[:MAX_GANTT_LANES]
    series_keys = chart.keys(chart.columns)
    colours = chart.colours(series_keys, chart.columns)
    group = [*chart.rows, *chart.columns, "__period"]
    table = frame.groupby(group, sort=False).agg(start=("__start", "min"), end=("__end", "max"), n=("__start", "size")).reset_index()
    # The longest step from one period to the next, in milliseconds.
    period_step = {"hour": 3600, "day": 86400, "week": 7 * 86400, "month": 31 * 86400}[unit] * 1000
    lanes = []
    for lane in lanes_keys:
        rows = table
        for column, value in zip(chart.rows, lane):
            rows = rows[rows[column] == value]
        segments = []
        for series in series_keys:
            selected = rows
            for column, value in zip(chart.columns, series):
                selected = selected[selected[column] == value]
            if selected.empty:
                continue
            periods = sorted((date_bin_time(label, unit), start, end, int(count))
                             for label, start, end, count in selected[["__period", "start", "end", "n"]].itertuples(index=False, name=None))
            run = None
            for period_time, start, end, count in periods:
                if period_time is None:
                    continue
                if run and period_time - run["period"] <= period_step * 1.01:
                    run.update(end=max(run["end"], end), n=run["n"] + count, period=period_time)
                else:
                    if run:
                        segments.append(run)
                    run = {"start": start, "end": end, "n": count, "period": period_time, "series": _label(series), "colour": colours[series]}
            if run:
                segments.append(run)
        if segments:
            lanes.append({"key": list(lane), "label": _label(lane), "segments": [
                {"start": item["start"].timestamp() * 1000, "end": max(item["end"], item["start"]).timestamp() * 1000,
                 "n": item["n"], "series": item["series"], "colour": item["colour"]} for item in segments]})
    if not lanes:
        return chart.empty()
    starts = [segment["start"] for lane in lanes for segment in lane["segments"]]
    ends = [segment["end"] for lane in lanes for segment in lane["segments"]]
    return chart.base(
        "gantt", _legend([(_label(key), colours[key]) for key in series_keys]) if chart.columns else [],
        lanes=lanes, unit=unit, domain={"x": [min(starts), max(ends) if max(ends) > min(starts) else min(starts) + 3600000]},
        metric=measures[0].field.replace("_", " "), dimensions=chart.dimensions(chart.rows),
    )


BUILDERS: dict[str, Callable[[_Chart], dict[str, object]]] = {
    "hbar": _horizontal_bars, "dot": _dot_plot, "bullet": _bullet_graph, "heat_map": _heat_map, "pie": _pie,
    "lines": _lines, "areas": _areas, "combo": _bars_and_line, "box": _box_plot, "symbol_map": _symbol_map,
    "filled_map": _filled_map, "treemap": _treemap, "bubbles": _packed_bubbles, "sankey": _sankey, "gantt": _gantt,
}


def extended_chart_payload(
    data: pd.DataFrame, entry: Any, metric: str | None, row_hierarchy: list[str], column_hierarchy: list[str],
    title: str, multivendor: bool = False,
) -> dict[str, object]:
    """The model of a chart of one of the chart types of this module (not Highlight and Bar Table, which the Table
    model draws, see decorate_table)."""
    chart = _Chart(data, entry, metric, list(row_hierarchy), list(column_hierarchy), title, multivendor)
    kind = EXTENDED_CHART_TYPES[chart.chart_type]
    if not chart.measures() or not chart.measures()[0].column:
        return chart.empty()
    return BUILDERS[kind](chart)
