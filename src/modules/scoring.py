"""Source-grounded NetCheck 2026Q2 KPI aggregation and ranking points."""
from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from typing import Iterable

import numpy as np
import pandas as pd

from src.modules.column_names import campaign_sort_key, column_identity, resolve_column_name
from src.modules.nr_mode import (
    NR_MODE_COLUMN, SAME_OPERATOR_NSA, SAME_OPERATOR_NSA_LABEL, campaign_nr_mode, campaign_pair_key, campaign_with_nr_mode,
)
from src.modules.scoring_vendors import scoring_vendor_group
from src.modules import scoring_points_loss as points_loss
from src.modules.scoring_config import (
    configuration_hash,
    MOST_RELIABLE_SCORING,
    most_reliable_configuration,
    SUPPORTED_MAPPING_METHODS,
    _is_legacy_two_environment_configuration,
    validate_scoring_configuration,
)

# Semantic engine version only. Configuration identity is added to job versions
# after the workspace snapshot has been supplied explicitly.
METHOD_VERSION = 'campaign-gap-global-kpi-v7'
AGGREGATION_CONTRACT_VERSION = 2
# Time splits of the Campaign level: each test falls in the period of its start time.
TIME_SPLITS = ('Daily', 'Weekly', 'Monthly', 'Quarterly', 'Yearly')
START_TIME_COLUMNS = ('Event_Start_Time', 'Call_Start_Time', 'Test_Start_Time')
_SHARED = ['Operator', 'Campaign', 'G_Level_1', 'G_Level_2']
_INCOMPLETE_COVERAGE_WARNING = (
    'Incomplete KPI or environment coverage: partial points are shown without renormalizing weights; '
    'a complete benchmark score is unavailable.'
)
_LEVEL_SOURCE_ALIASES = {
    'Region': ('Region', 'G_Level_2'),
    'City': ('City', 'G_Level_4'),
    'Cluster': ('Cluster',),
}
_FIELDS = {
    'data': ['Test_Name', 'Test_Result', 'Mean_Data_Rate', 'Transfer_Duration', 'Type_of_Test',
             'http_Browser_Transferred_Bytes', 'http_Browser_1MB_Reached_Duration',
             'VideoStream_Time_to_First_Picture', 'Irritating_Video_Playout', 'Packets_Lost',
             'Packets_Discarded', 'Packets_Corrupted', 'Packets_Not_Sent', 'Packets_Sent',
             'Interactivity_RTT_Median'],
    'voice': ['Session_Type', 'Call_Status', 'Call_Setup_Time', 'Disturbed_and_Impaired_Call', 'Test_Status'],
    'speech': ['Session_Type', 'LQ'],
}


def normalize_time_split(value: object) -> str | None:
    """Daily, Weekly, Monthly, Quarterly or Yearly; None splits the Campaign level by campaign."""
    text = str(value or '').strip().casefold()
    return next((name for name in TIME_SPLITS if name.casefold() == text), None)


def period_labels(values: pd.Series, time_split: str) -> pd.Series:
    """The period of each start time: 2026-07-15, 2026-W07 (ISO week), 2026-07, 2026-Q3 or 2026."""
    times = pd.to_datetime(values, errors='coerce', format='mixed')
    if time_split == 'Daily':
        labels = times.dt.strftime('%Y-%m-%d')
    elif time_split == 'Weekly':
        weeks = times.dt.isocalendar()
        labels = weeks['year'].astype('string') + '-W' + weeks['week'].astype('string').str.zfill(2)
    elif time_split == 'Monthly':
        labels = times.dt.strftime('%Y-%m')
    elif time_split == 'Quarterly':
        labels = times.dt.year.astype('Int64').astype('string') + '-Q' + times.dt.quarter.astype('Int64').astype('string')
    else:
        labels = times.dt.year.astype('Int64').astype('string')
    return labels.astype(object).where(times.notna(), None)


def required_input_columns(kind: str, levels: Iterable[str] = ()) -> list[str]:
    """Return projected source fields, using the application's shared aliases."""
    fields = _SHARED + _FIELDS.get(kind, [])
    for level in levels:
        identity = column_identity(level)
        field = 'Dataset_Kind' if identity in {'datasettype', 'datasetkind'} else ('Vendor' if identity == 'ranvendor' else level)
        if field not in fields:
            fields = fields + [field]
    return list(dict.fromkeys(fields))


def load_input_columns(kind: str, levels: Iterable[str] = ()) -> list[str]:
    """Columns read from the CDR rows: the scoring fields plus the areas and coordinates of the points-lost map and the
    start time of the tests (for the dates of the measurements)."""
    return list(dict.fromkeys([*required_input_columns(kind, levels), *points_loss.source_columns(kind),
                               *START_TIME_COLUMNS]))


def window_of_days(days: Iterable[Any]) -> dict | None:
    """The first and last day of the measurements and the number of days with tests."""
    days = sorted({str(day)[:10] for day in days if day is not None and str(day).strip()})
    return {'first': days[0], 'last': days[-1], 'days': len(days)} if days else None


def test_window(frames: dict[str, pd.DataFrame]) -> dict | None:
    """The dates of the measurements of the CDR rows, from the start time of their tests."""
    days: set[str] = set()
    for source in frames.values():
        start = next((column for name in START_TIME_COLUMNS
                      if (column := resolve_column_name(source.columns, name)) is not None), None)
        if start is None:
            continue
        times = pd.to_datetime(source[start], errors='coerce', format='mixed')
        days.update(times.dropna().dt.strftime('%Y-%m-%d').unique().tolist())
    return window_of_days(days)


def _required_configuration(configuration: dict | None) -> dict:
    if configuration is None:
        raise ValueError('A scoring configuration is required. Import the Scoring & GAP Analysis Methodologies before calculating scoring.')
    return validate_scoring_configuration(configuration)


def method_version_for_configuration(configuration: dict) -> str:
    """Return a calculation version bound to every scoring setting."""
    snapshot = _required_configuration(configuration)
    hashed_configuration = configuration if _is_legacy_two_environment_configuration(configuration) else snapshot
    return f"{snapshot['version']}-{METHOD_VERSION}-{configuration_hash(hashed_configuration)[:16]}"


def interpolate_score(
    value: float, thresholds: dict, ultra: float | None = None,
    score_mapping: dict | None = None, mapping_method: str = 'piecewise_linear',
) -> float:
    """Apply the selected piecewise mapping between configurable score anchors."""
    if not isinstance(mapping_method, str) or mapping_method not in SUPPORTED_MAPPING_METHODS:
        raise ValueError(f'Unsupported scoring mapping method: {mapping_method!r}.')

    def map_fraction(fraction: float) -> float:
        if mapping_method == 'piecewise_quadratic':
            return fraction * fraction
        if mapping_method == 'piecewise_smoothstep':
            return fraction * fraction * (3 - 2 * fraction)
        return fraction

    specification = thresholds.get('ultra')
    if isinstance(specification, dict) and specification.get('rule') == 'fixed':
        ultra = specification['value']
    elif isinstance(specification, (int, float)) and not isinstance(specification, bool):
        ultra = float(specification)
    has_ultra = specification is not None and ultra is not None
    mapping = score_mapping or {
        'low_score': 0.0, 'medium_score': 0.8,
        'high_score': 0.95 if has_ultra else 1.0, 'ultra_score': 1.0,
    }
    anchors = [(thresholds['low'], mapping['low_score']),
               (thresholds['medium'], mapping['medium_score']),
               (thresholds['high'], mapping['high_score'])]
    # A dynamic best value can be inside the fixed thresholds. Excel's nested
    # IF evaluates the Low/Medium/High branches before its final Ultra branch.
    sign = 1 if thresholds['high'] >= thresholds['low'] else -1
    normalized = [(sign * x, y) for x, y in anchors]
    x = sign * value
    if x <= normalized[0][0]:
        return float(mapping['low_score'])
    for (left, low_score), (right, high_score) in zip(normalized, normalized[1:]):
        if x <= right:
            if right == left:
                return float(high_score)
            return low_score + map_fraction((x - left) / (right - left)) * (high_score - low_score)
    if not has_ultra:
        return float(mapping['high_score'])
    high = normalized[-1][0]
    upper = sign * ultra
    if upper <= high or x >= upper:
        return float(mapping['ultra_score'])
    if upper == high:
        return float(mapping['ultra_score'])
    return mapping['high_score'] + map_fraction((x - high) / (upper - high)) * (mapping['ultra_score'] - mapping['high_score'])


def _numeric(frame: pd.DataFrame, field: str) -> pd.Series:
    return pd.to_numeric(frame[field], errors='coerce').replace([float('inf'), -float('inf')], float('nan'))


def _filter(frame: pd.DataFrame, filters: dict) -> pd.DataFrame:
    for field, rule in filters.items():
        if field.endswith(' contains'):
            field = field.removesuffix(' contains')
            if isinstance(rule, list):
                for fragment in rule:
                    frame = frame[frame[field].astype('string').str.contains(fragment, regex=False, na=False)]
            elif isinstance(rule, str):
                contains = re.fullmatch(r'contains ([^\r\n]{1,256})', rule)
                if not contains:
                    raise ValueError(f'Unsupported scoring filter: {field} contains {rule}')
                frame = frame[frame[field].astype('string').str.contains(contains.group(1), regex=False, na=False)]
            else:
                raise ValueError(f'Unsupported scoring filter: {field} contains {rule}')
        elif isinstance(rule, list):
            frame = frame[frame[field].isin(rule)]
        elif isinstance(rule, str):
            contains = re.fullmatch(r'contains ([^\r\n]{1,256})', rule)
            numeric_threshold = re.fullmatch(
                r'>= ([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)', rule,
            )
            if contains:
                frame = frame[frame[field].astype('string').str.contains(contains.group(1), regex=False, na=False)]
            elif numeric_threshold and math.isfinite(float(numeric_threshold.group(1))):
                frame = frame[_numeric(frame, field) >= float(numeric_threshold.group(1))]
            else:
                raise ValueError(f'Unsupported scoring filter: {field} {rule}')
        else:
            raise ValueError(f'Unsupported scoring filter: {field} {rule}')
    return frame


def _prefiltered_metrics(frame: pd.DataFrame, metrics: list[dict]) -> list[dict]:
    """The KPIs of a frame with their filters applied once to all its rows: each one filters its groups by a column
    of the rows it keeps (the filters only look at each row), instead of testing them again in every group."""
    prepared = []
    for metric in metrics:
        filters = metric['calculation']['filters']
        if not filters:
            prepared.append(metric)
            continue
        column = f"__kpi_rows_{metric['code']}"
        try:
            frame[column] = frame.index.isin(_filter(frame, filters).index)
        except (KeyError, ValueError, TypeError):
            prepared.append(metric)  # Its groups report the error, as before.
            continue
        prepared.append({**metric, 'calculation': {**metric['calculation'], 'filters': {column: [True]}}})
    return prepared


def _condition(frame: pd.DataFrame, expression: str) -> pd.Series:
    if ' AND ' in expression:
        left, right = expression.split(' AND ', 1)
        return _condition(frame, left) & _condition(frame, right)
    contains = re.fullmatch(r'CONTAINS\((\w+), "([^"]+)"\)', expression)
    if contains:
        return frame[contains[1]].astype('string').str.contains(contains[2], regex=False, na=False)
    if expression.endswith(' IS NOT NULL'):
        return frame[expression.removesuffix(' IS NOT NULL')].notna()
    comparison = re.fullmatch(r'(\w+) (==|<=|>=|>) (.+)', expression)
    if not comparison:
        raise ValueError(f'Unsupported scoring condition: {expression}')
    field, operator, literal = comparison.groups()
    series = frame[field] if literal.startswith('"') else _numeric(frame, field)
    value = literal.strip('"') if literal.startswith('"') else float(literal)
    return {'==': series.eq, '<=': series.le, '>=': series.ge, '>': series.gt}[operator](value).fillna(False)


def _is_condition_expression(expression: str) -> bool:
    return bool(
        ' AND ' in expression
        or re.fullmatch(r'CONTAINS\(\w+, "[^\"]+"\)', expression)
        or expression.endswith(' IS NOT NULL')
        or re.fullmatch(r'\w+ (?:==|<=|>=|>) .+', expression)
    )


def _aggregate_term(frame: pd.DataFrame, operation: str, expression: str) -> tuple[float | None, int]:
    expression = expression.strip()
    if _is_condition_expression(expression):
        matches = _condition(frame, expression)
        return float(matches.sum()), int(matches.sum())
    if operation == 'COUNT':
        count = int(frame[expression].notna().sum())
        return float(count), count
    values = _numeric(frame, expression).dropna()
    if values.empty:
        return None, 0
    if operation == 'SUM':
        return float(values.sum()), len(values)
    if operation == 'AVG':
        return float(values.mean()), len(values)
    if operation == 'MEDIAN':
        return float(values.median()), len(values)
    if operation == 'PCT90':
        return float(values.quantile(.9, interpolation='linear')), len(values)
    raise ValueError(f'Unsupported scoring aggregate: {operation}')


def _aggregate(frame: pd.DataFrame, metric: dict) -> tuple[float | None, int]:
    calculation = metric['calculation']
    frame = _filter(frame, calculation['filters'])
    formula = calculation['formula']
    if formula == '100 * SUM(totalpacketlost) / SUM(Packets_Sent)':
        sent = _numeric(frame, 'Packets_Sent')
        denominator = sent.sum(min_count=1)
        packet_loss_fields = ['Packets_Lost', 'Packets_Discarded', 'Packets_Corrupted', 'Packets_Not_Sent']
        packet_components = []
        for field in packet_loss_fields:
            values = _numeric(frame, field) if field in frame.columns else pd.Series(0.0, index=frame.index)
            values = values.fillna(0)
            packet_components.append(values.map(math.trunc) if field == 'Packets_Corrupted' else values)
        lost = sum(packet_components)
        return (float(100 * lost.sum() / denominator), int(sent.notna().sum())) if denominator > 0 else (None, 0)
    ratio = re.fullmatch(r'(100 \* )?(SUM|COUNT)\((.+)\) / (SUM|COUNT)\((\w+)\)', formula)
    if ratio:
        multiplier, numerator_operation, expression, denominator_operation, denominator_field = ratio.groups()
        numerator, _numerator_count = _aggregate_term(frame, numerator_operation, expression)
        denominator, count = _aggregate_term(frame, denominator_operation, denominator_field)
        if numerator is None or denominator is None or denominator == 0:
            return None, 0
        return float((100 if multiplier else 1) * numerator / denominator), count
    aggregate = re.fullmatch(r'(AVG|MEDIAN|PCT90|SUM|COUNT)\((.+)\)', formula)
    if aggregate:
        operation, expression = aggregate.groups()
        return _aggregate_term(frame, operation, expression)
    raise ValueError(f'Unsupported scoring formula: {formula}')


def _key_name(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', value.casefold()).strip('_')


@lru_cache(maxsize=4096)
def _operator_identity(value: str) -> str:
    identity = column_identity(value)
    if identity.endswith('uk'):
        identity = identity[:-2]
    return 'ee' if identity in {'ee', 'everythingeverywhere'} else identity


@lru_cache(maxsize=256)
def _baseline_identities(baseline_operator: str, baseline_aliases: tuple[str, ...]) -> frozenset[str]:
    aliases = {str(baseline_operator), *(str(alias) for alias in baseline_aliases)}
    return frozenset(_operator_identity(alias) for alias in aliases if alias.strip())


def _is_baseline(value: str, baseline_operator: str, baseline_aliases: Iterable[str]) -> bool:
    return _operator_identity(str(value)) in _baseline_identities(str(baseline_operator), tuple(baseline_aliases))


def _prepared_frames(frames: dict[str, pd.DataFrame], dimensions: list[str], config: dict, operator_mappings: dict[str, str],
                     map_areas, time_split: str | None, campaign_selected: bool, warnings: list[str]):
    """Each source with the grouping fields, the map location and the environment of its tests, and which of its
    rows can be scored."""
    for kind, source in frames.items():
        if kind not in _FIELDS or source.empty:
            continue
        frame = pd.DataFrame(index=source.index)
        for field in required_input_columns(kind, dimensions):
            aliases = _LEVEL_SOURCE_ALIASES.get(field, (field,))
            resolved = next((
                column for alias in aliases
                if (column := resolve_column_name(source.columns, alias)) is not None
            ), None)
            if resolved:
                frame[field] = source[resolved]
        for field in ('Operator', 'Campaign', 'Vendor', *dimensions):
            if field in frame and isinstance(frame[field].dtype, pd.CategoricalDtype):
                # The fields the groups are made of hold their values themselves (None for no value), as the rows of a
                # CDR read row by row give them (see saved_filters._load_source_frames).
                frame[field] = frame[field].astype(object).where(frame[field].notna(), None)
        if 'Vendor' in frame:
            vendor_operators = [*operator_mappings, *operator_mappings.values()]
            if 'Operator' in frame:
                vendor_operators.extend(frame['Operator'].dropna().unique())
            vendor_labels = {
                value: scoring_vendor_group(value, vendor_operators)
                for value in frame['Vendor'].dropna().unique()
            }
            frame['Vendor'] = frame['Vendor'].map(vendor_labels).fillna('All')
        if operator_mappings and 'Operator' in frame:
            operators = frame['Operator']
            # Each operator name once, not every row.
            names = {value: operator_mappings.get(str(value).strip().casefold(), str(value).strip())
                     for value in operators.dropna().unique()}
            frame['Operator'] = operators.astype(object).map(names).where(operators.notna(), operators.astype(object))
        if not campaign_selected:
            frame['Campaign'] = None
        elif time_split:
            start = next((column for name in START_TIME_COLUMNS
                          if (column := resolve_column_name(source.columns, name)) is not None), None)
            if start is None:
                warnings.append(f'{kind.title()}: no test start time; its rows cannot be split by {time_split.lower()} period.')
                frame['Campaign'] = None
            else:
                frame['Campaign'] = period_labels(source[start].astype(object), time_split)
                if NR_MODE_COLUMN in source:
                    # NSA vs SA: the NSA and SA tests of a period stay apart (2026-W07 and 2026-W07 SA).
                    frame['Campaign'] = [campaign_with_nr_mode(period, mode) for period, mode
                                         in zip(frame['Campaign'], source[NR_MODE_COLUMN])]
        if 'Dataset Type' in dimensions:
            frame['Dataset Type'] = kind.title()
        missing_group = [field for field in _SHARED + [d for d in dimensions if d != 'Dataset Type'] if field not in frame]
        if missing_group:
            warnings.append(f'{kind.title()}: missing grouping columns: {", ".join(missing_group)}; no scores calculated.')
            continue
        points_loss.attach_location(frame, source, kind, resolve_column_name, map_areas)
        frame['environment'] = None
        environment_masks = {}
        for environment, context in config['scope']['environments'].items():
            filters = context['source_filters']
            mask = frame['G_Level_1'] == filters['G_Level_1']
            if 'G_Level_2' in filters:
                mask &= frame['G_Level_2'] == filters['G_Level_2']
            environment_masks[environment] = mask
            frame.loc[mask, 'environment'] = environment
        # Preserve one pooled copy per source row, while remembering every
        # matching selector so overlapping configured environments cannot
        # inflate a global raw KPI.
        environment_names = list(environment_masks)
        environment_match_arrays = [
            mask.fillna(False).to_numpy(dtype=bool) for mask in environment_masks.values()
        ]
        # Each combination of environments once, not every row.
        matched = np.zeros(len(frame), dtype=np.int64)
        for bit, matches in enumerate(environment_match_arrays):
            matched |= matches.astype(np.int64) << bit
        combinations = {int(code): tuple(name for bit, name in enumerate(environment_names) if int(code) >> bit & 1)
                        for code in np.unique(matched)}
        frame['__matched_environments'] = pd.Series(matched, index=frame.index).map(combinations)
        valid = frame['environment'].notna() & frame['Operator'].notna()
        if campaign_selected:
            valid &= frame['Campaign'].notna()
        if (~valid).any():
            missing_context = 'environment, operator or campaign' if campaign_selected else 'environment or operator'
            warnings.append(f'{kind.title()}: {int((~valid).sum())} rows have unsupported or missing {missing_context} and were excluded.')
        yield kind, frame, valid


def calculate_scoring(
    frames: dict[str, pd.DataFrame], levels: Iterable[str] = ('Operator',),
    baseline_operator: str = 'EE', configuration: dict | None = None,
    baseline_aliases: Iterable[str] = (),
    operator_mappings: dict[str, str] | None = None,
    map_areas=None,
    time_split: str | None = None,
) -> dict:
    """Calculate KPI scores at the selected dimensions without reallocating missing weights.

    ``map_areas`` (a ``map_areas.AreaIndex``) places the tests in the map areas of their country.
    ``time_split`` (Daily, Weekly, Monthly, Quarterly or Yearly) splits the Campaign level by the
    period of each test's start time instead of by campaign.
    """
    config = _required_configuration(configuration)
    metrics = config['metrics']
    baseline_aliases = list(dict.fromkeys(
        [str(baseline_operator), *(str(alias).strip() for alias in baseline_aliases if str(alias).strip())]
    ))
    dimensions = []
    for level in levels:
        identity = column_identity(level)
        canonical = {'operator': 'Operator', 'region': 'Region', 'cluster': 'Cluster', 'city': 'City', 'vendor': 'Vendor',
                     'ranvendor': 'Vendor', 'campaign': 'Campaign',
                     'datasettype': 'Dataset Type', 'datasetkind': 'Dataset Type'}.get(identity)
        if canonical is None:
            raise ValueError(f'Unsupported scoring level: {level}')
        if canonical not in dimensions:
            dimensions.append(canonical)
    if 'Operator' not in dimensions:
        dimensions.append('Operator')
    campaign_selected = 'Campaign' in dimensions
    group_fields = list(dict.fromkeys(['Campaign', *dimensions, 'environment']))
    keys = [_key_name(field) for field in group_fields]
    warnings = []
    rows = []
    global_kpis = []
    # Where each KPI loses its points: area shares of the tests that cause the loss.
    loss_shares: list[dict] = []
    # The tests of each group per Vendor and Site Type of their serving cell.
    serving_tests: list[dict] = []
    test_counts: list[dict] = []
    geometry = points_loss.AreaGeometry()
    if map_areas is None:
        from src.modules.map_areas import area_index
        map_areas = area_index(None)
    normalized_operator_mappings = {
        str(alias).strip().casefold(): str(canonical).strip()
        for alias, canonical in (operator_mappings or {}).items()
        if str(alias).strip() and str(canonical).strip()
    }
    campaign_values: dict[str, str] = {}
    for source in frames.values():
        campaign_column = resolve_column_name(source.columns, 'Campaign')
        if campaign_column is None:
            continue
        for value in source[campaign_column].dropna().tolist():
            campaign = str(value).strip()
            if campaign:
                campaign_values.setdefault(campaign.casefold(), campaign)
    for missing_kind in _FIELDS.keys() - frames.keys():
        warnings.append(f'{missing_kind.title()} source is missing; full benchmark coverage is unavailable.')
    time_split = normalize_time_split(time_split) if campaign_selected else None
    for kind, frame, valid in _prepared_frames(frames, dimensions, config, normalized_operator_mappings, map_areas,
                                               time_split, campaign_selected, warnings):
        for values, group in frame[valid].groupby(group_fields, dropna=False, sort=False):
            metadata = dict(zip(keys, values))
            metadata = {key: (None if pd.isna(value) else value) for key, value in metadata.items()}
            # The tests of each group, for how the measurements ran.
            test_counts.append({**metadata, 'kind': kind, 'tests': int(len(group))})
            for metric in (m for m in metrics if m['source_kind'] == kind):
                try:
                    value, count = _aggregate(group, metric)
                except KeyError as error:
                    value, count = None, 0
                    warnings.append(f'{kind.title()}: {metric["code"]} requires missing column {error.args[0]}.')
                context = metric['contexts'][metadata['environment']]
                rows.append({**metadata, 'kpi_code': metric['code'], 'kpi': metric['kpi'], 'category': metric['category'],
                             'dataset_type': kind.title(), 'kpi_type': metric.get('kpi_type'),
                             'unit': metric.get('unit'), 'value': value, 'sample_count': count, 'score': None,
                             'weighted_points': None, 'max_points': context['max_points']})
        # Where each KPI loses its points, for every group at once.
        shares, served = _points_loss_entries(kind, frame, valid, group_fields, keys,
                                              [m for m in metrics if m['source_kind'] == kind])
        loss_shares.extend(shares)
        serving_tests.extend(served)
        geometry.add(frame[valid])
        global_valid = frame['__matched_environments'].map(bool) & frame['Operator'].notna()
        if campaign_selected:
            global_valid &= frame['Campaign'].notna()
        global_group_fields = [field for field in group_fields if field != 'environment']
        global_keys = [_key_name(field) for field in global_group_fields]
        for values, group in frame[global_valid].groupby(global_group_fields, dropna=False, sort=False):
            metadata = dict(zip(global_keys, values if isinstance(values, tuple) else (values,)))
            metadata = {key: (None if pd.isna(value) else value) for key, value in metadata.items()}
            for metric in (m for m in metrics if m['source_kind'] == kind):
                try:
                    value, count = _aggregate(group, metric)
                except KeyError as error:
                    value, count = None, 0
                    warnings.append(f'{kind.title()}: {metric["code"]} requires missing column {error.args[0]}.')
                expected_environments = [
                    name for name in config['scope']['environments'] if name in metric['contexts']
                ]
                covered_environments = []
                for environment in expected_environments:
                    environment_group = group[group['__matched_environments'].map(lambda names: environment in names)]
                    try:
                        environment_value, _ = _aggregate(environment_group, metric)
                    except KeyError:
                        environment_value = None
                    if environment_value is not None:
                        covered_environments.append(environment)
                missing_environments = [name for name in expected_environments if name not in covered_environments]
                global_kpis.append({**metadata, 'environment': 'All Environments', 'kpi_code': metric['code'],
                                    'kpi': metric['kpi'], 'category': metric['category'],
                                    'dataset_type': kind.title(), 'kpi_type': metric.get('kpi_type'),
                                    'unit': metric.get('unit'), 'value': value, 'sample_count': count,
                                    'complete_coverage': value is not None and not missing_environments,
                                    'missing_environments': missing_environments})
    result = finish_scoring(
        rows, global_kpis, keys=keys, dimensions=dimensions, config=config, baseline_operator=baseline_operator,
        baseline_aliases=baseline_aliases, warnings=warnings, campaigns=campaign_values.values(),
        points_loss_document={'version': 3, **geometry.document(), 'map_areas': geometry.map_areas(map_areas),
                              'shares': loss_shares, 'serving_tests': serving_tests},
    )
    window = test_window(frames)
    if window:
        result['test_window'] = window
    result['test_counts'] = test_counts
    return result


_RATIO_FORMULA = re.compile(r'(100 \* )?(SUM|COUNT)\((.+)\) / (SUM|COUNT)\((\w+)\)')
_TERM_FORMULA = re.compile(r'(AVG|MEDIAN|PCT90|SUM|COUNT)\((.+)\)')


def _floats(series: pd.Series) -> np.ndarray:
    return series.to_numpy(dtype=float, na_value=np.nan)


def _filter_mask(frame: pd.DataFrame, filters: dict) -> np.ndarray:
    """The rows ``_filter`` keeps, as a mask (only the filtered columns are copied; text columns are filtered once per
    distinct combination of their values, as the filters look at each row alone)."""
    mask = np.zeros(len(frame), dtype=bool)
    if not filters:
        mask[:] = True
        return mask
    narrow = frame[list(dict.fromkeys(field.removesuffix(' contains') for field in filters))].reset_index(drop=True)
    distinct = points_loss._distinct(narrow) if _all_categorical(narrow) else None
    if distinct is not None:
        rows, codes = distinct
        kept = np.zeros(len(rows), dtype=bool)
        kept[_filter(rows.reset_index(drop=True), filters).index.to_numpy()] = True
        return kept[codes]
    mask[_filter(narrow, filters).index.to_numpy()] = True
    return mask


_CONDITION_FIELDS = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def _all_categorical(frame: pd.DataFrame) -> bool:
    """Whether every column is a Categorical (text read from the columnar copies, few distinct values)."""
    return all(isinstance(dtype, pd.CategoricalDtype) for dtype in frame.dtypes)


def _row_condition(frame: pd.DataFrame, expression: str) -> pd.Series:
    """``_condition`` of every row, once per distinct combination of the text columns it reads (it looks at each row
    alone)."""
    fields = [field for field in dict.fromkeys(_CONDITION_FIELDS.findall(expression)) if field in frame.columns]
    distinct = points_loss._distinct(frame[fields]) if fields and _all_categorical(frame[fields]) else None
    if distinct is None:
        return _condition(frame, expression)
    rows, codes = distinct
    result = _condition(rows.reset_index(drop=True), expression)
    return pd.Series(result.to_numpy()[codes], index=frame.index)


def _valued_groups(frame: pd.DataFrame, selected: np.ndarray, codes: np.ndarray, groups: int, formula: str) -> np.ndarray:
    """The scoring groups where a KPI has a value (``_aggregate`` of their rows is not None). A missing column raises
    KeyError, as in every group."""
    def with_rows(present: np.ndarray) -> np.ndarray:
        return np.bincount(codes[selected & present], minlength=groups) > 0

    def sums(values: np.ndarray) -> np.ndarray:
        present = selected & ~np.isnan(values)
        return np.bincount(codes[present], weights=values[present], minlength=groups)

    def term(operation: str, expression: str) -> np.ndarray:
        expression = expression.strip()
        if _is_condition_expression(expression):
            _condition(frame.iloc[:0], expression)
            return np.ones(groups, dtype=bool)
        if operation == 'COUNT':
            frame[expression]
            return np.ones(groups, dtype=bool)
        return with_rows(_numeric(frame, expression).notna().to_numpy())

    if formula == points_loss.PACKET_LOSS_FORMULA:
        sent = _floats(_numeric(frame, 'Packets_Sent'))
        return with_rows(~np.isnan(sent)) & (sums(sent) > 0)
    ratio = _RATIO_FORMULA.fullmatch(formula)
    if ratio:
        _multiplier, numerator_operation, expression, denominator_operation, denominator = ratio.groups()
        valued = term(numerator_operation, expression)
        if denominator_operation == 'COUNT':
            return valued & with_rows(frame[denominator].notna().to_numpy())
        values = _floats(_numeric(frame, denominator))
        return valued & with_rows(~np.isnan(values)) & (sums(values) != 0)
    aggregate = _TERM_FORMULA.fullmatch(formula)
    if aggregate:
        return term(*aggregate.groups())
    raise ValueError(f'Unsupported scoring formula: {formula}')


def _loss_weights(frame: pd.DataFrame, selected: np.ndarray, metric: dict, environments: pd.Series) -> np.ndarray:
    """``points_loss.test_weights`` of every row at once, each with the thresholds of its environment."""
    formula = metric['calculation']['formula']
    higher_is_better = metric['direction'] == 'higher_is_better'
    weights = np.zeros(len(frame))
    if not selected.any():
        return weights
    if formula == points_loss.PACKET_LOSS_FORMULA:
        lost = sum((points_loss._numeric(frame, field).fillna(0) if field in frame else 0)
                   for field in points_loss.LOST_PACKET_FIELDS)
        if isinstance(lost, pd.Series):
            weights[selected] = _floats(lost.clip(lower=0))[selected]
        return weights
    ratio = points_loss._RATIO.fullmatch(formula)
    if ratio:
        denominator = ratio.group(5)
        counted = selected & frame[denominator].notna().to_numpy() if denominator in frame else selected
        try:
            matches = _row_condition(frame, ratio.group(3).strip()).astype(bool).to_numpy()
        except (KeyError, ValueError):
            weights[counted] = 1.0
            return weights
        # Higher-is-better ratios lose points on the tests that miss the condition, the others on those that meet it.
        weights[counted] = (~matches if higher_is_better else matches)[counted]
        return weights
    aggregate = points_loss._AGGREGATE.fullmatch(formula)
    if aggregate and aggregate.group(2) in frame:
        highs = {name: context['thresholds'].get('high') for name, context in metric['contexts'].items()}
        numeric = {name: float(high) for name, high in highs.items() if isinstance(high, (int, float))}
        with_target = selected & environments.isin(list(numeric)).to_numpy()
        targets = _floats(environments.map(numeric))
        values = _floats(points_loss._numeric(frame, aggregate.group(2)))
        shortfall = (targets - values) if higher_is_better else (values - targets)
        shortfall = np.where(np.isnan(shortfall), 0.0, np.maximum(shortfall, 0.0))
        weights[with_target] = shortfall[with_target]
        weights[selected & ~with_target] = 1.0
        return weights
    weights[selected] = 1.0
    return weights


def _points_loss_entries_by_group(kind: str, rows: pd.DataFrame, group_fields: list[str], keys: list[str],
                                  metrics: list[dict]) -> tuple[list[dict], list[dict]]:
    """``_points_loss_entries`` group by group, for the rows without the areas of the map."""
    loss_shares, serving_tests = [], []
    for values, group in rows.groupby(group_fields, dropna=False, sort=False):
        metadata = {key: (None if pd.isna(value) else value) for key, value in zip(keys, values)}
        for metric in metrics:
            try:
                value, _count = _aggregate(group, metric)
            except KeyError:
                continue
            if value is None:
                continue
            context = metric['contexts'][metadata['environment']]
            try:
                weights = points_loss.test_weights(group, metric, context['thresholds'], _condition, _filter)
            except (KeyError, ValueError, TypeError):
                weights = None
            shares = points_loss.area_shares(group, weights) if weights is not None else {}
            if shares:
                loss_shares.append({**metadata, 'kpi_code': metric['code'], 'areas': shares,
                                    'weight': round(float(weights.sum()), 4), 'tests': points_loss.counts_tests(metric)})
        served = points_loss.serving_counts(group, areas=kind != 'speech')
        if served:
            serving_tests.append({**metadata, 'counts': served})
    return loss_shares, serving_tests


def _points_loss_entries(kind: str, frame: pd.DataFrame, valid: pd.Series, group_fields: list[str], keys: list[str],
                         metrics: list[dict], progress=None) -> tuple[list[dict], list[dict]]:
    """Where each scoring group of a CDR type loses the points of each KPI (``points_loss.test_weights`` and
    ``area_shares``) and who serves its tests (``serving_counts``), for every group at once.

    Each KPI weighs every test once, and the weights of each group and area are summed in the order of its rows, as
    group by group, so the shares are the same. ``progress(share, step)`` follows the KPIs (share from 0 to 1).
    """
    from pandas.core.sorting import nargsort

    rows = frame[valid]
    if rows.empty:
        return [], []
    if not any(points_loss.SHARE_COLUMN.format(field) in rows for field in points_loss.MAP_FIELDS):
        return _points_loss_entries_by_group(kind, rows, group_fields, keys, metrics)
    codes = rows.groupby(group_fields, dropna=False, sort=False).ngroup().to_numpy().astype(np.int64)
    groups = int(codes.max()) + 1
    order = np.argsort(codes, kind='stable')
    sizes = np.bincount(codes, minlength=groups)
    ends = np.cumsum(sizes)
    starts = ends - sizes
    metadata = [{key: (None if pd.isna(value) else value) for key, value in zip(keys, values)}
                for values in rows[group_fields].iloc[order[starts]].itertuples(index=False, name=None)]
    categories = {}
    for field in points_loss.SHARE_FIELDS:
        column = points_loss.SHARE_COLUMN.format(field)
        if column in rows:
            category = rows[column].cat
            categories[field] = (category.codes.to_numpy().astype(np.int64), list(category.categories))
    environments = rows['environment']
    # The cells of each area field (a group and an area): their keys, sorted, and the cell of every row.
    field_keys = {}
    for field, (category_codes, names) in categories.items():
        unique, _rows, inverse = points_loss.unique_keys(codes * len(names) + category_codes, groups * len(names))
        field_keys[field] = (unique, inverse)

    def field_cells(field: str, lost: np.ndarray, weights: np.ndarray):
        # The weight of each group in each area, added in the order of the rows (as area_shares).
        unique, cell_of = field_keys[field]
        size = len(categories[field][1])
        totals = np.bincount(cell_of[lost], weights=weights, minlength=len(unique))
        kept = np.flatnonzero(totals)
        return (unique[kept] % size, totals[kept],
                np.searchsorted(unique[kept] // size, np.arange(groups + 1)))

    def pair_cells(cell_keys: np.ndarray, weights: np.ndarray, span: int):
        # The weight of each group in each pair of areas, summed as pandas sums them (as area_shares).
        by_cell = pd.Series(weights).groupby(cell_keys).sum()
        unique, totals = by_cell.index.to_numpy(dtype=np.int64), by_cell.to_numpy()
        return unique % span, totals, np.searchsorted(unique // span, np.arange(groups + 1))

    masks: dict[str, np.ndarray] = {}
    found: list[dict[int, dict]] = []
    for index, metric in enumerate(metrics):
        if progress is not None:
            progress(index / max(1, len(metrics)), f'Mapping the {kind.title()} tests: KPI {index + 1} of {len(metrics)}')
        filters = metric['calculation']['filters']
        try:
            # Many KPIs share their filters.
            mask_key = json.dumps(filters, sort_keys=True, default=str)
            if mask_key not in masks:
                masks[mask_key] = _filter_mask(rows, filters)
            selected = masks[mask_key]
            valued = _valued_groups(rows, selected, codes, groups, metric['calculation']['formula'])
        except KeyError:
            found.append({})
            continue
        entries: dict[int, dict] = {}
        found.append(entries)
        valued_groups = np.flatnonzero(valued).tolist()
        if not valued_groups:
            continue
        thresholds = {group: metric['contexts'][metadata[group]['environment']]['thresholds'] for group in valued_groups}
        try:
            weights = _loss_weights(rows, selected, metric, environments)
        except (KeyError, ValueError, TypeError):
            # As each group would: its own error, or none for its rows.
            for group in valued_groups:
                group_rows = rows.iloc[order[starts[group]:ends[group]]]
                try:
                    group_weights = points_loss.test_weights(group_rows, metric, thresholds[group], _condition, _filter)
                except (KeyError, ValueError, TypeError):
                    continue
                shares = points_loss.area_shares(group_rows, group_weights)
                if shares:
                    entries[group] = {**metadata[group], 'kpi_code': metric['code'], 'areas': shares,
                                      'weight': round(float(group_weights.sum()), 4),
                                      'tests': points_loss.counts_tests(metric)}
            continue
        ordered_weights = weights[order]
        lost = np.flatnonzero(weights > 0)
        lost_groups, lost_weights = codes[lost], weights[lost]
        by_field = [(field, names, *field_cells(field, lost, lost_weights)) for field, (_codes, names) in categories.items()]
        by_pair = []
        for pair_field, first, second in points_loss.PAIR_FIELDS:
            if first in categories and second in categories:
                (first_codes, firsts), (second_codes, seconds) = categories[first], categories[second]
                span = len(firsts) * len(seconds)
                pairs = first_codes[lost] * len(seconds) + second_codes[lost]
                by_pair.append((pair_field, firsts, seconds, *pair_cells(lost_groups * span + pairs, lost_weights, span)))
        tests = points_loss.counts_tests(metric)
        for group in valued_groups:
            total = float(ordered_weights[starts[group]:ends[group]].sum())
            if total <= 0:
                continue
            shares = {}
            for field, names, positions, totals, bounds in by_field:
                low, high = bounds[group], bounds[group + 1]
                field_shares = {str(names[position]): round(value / total, 6) for position, value
                                in zip(positions[low:high].tolist(), totals[low:high].tolist()) if value > 0}
                if field == points_loss.STRETCH:
                    # Tests off the routes have no stretch.
                    field_shares.pop(points_loss.NOT_SPECIFIED, None)
                if field in points_loss.SERVING_FIELDS:
                    field_shares = points_loss._capped_shares(field_shares, field)
                if field_shares:
                    shares[field] = field_shares
            for pair_field, firsts, seconds, positions, totals, bounds in by_pair:
                low, high = bounds[group], bounds[group + 1]
                pair_shares = {
                    f'{firsts[pair // len(seconds)]}{points_loss.CITY_AREA_SEPARATOR}{seconds[pair % len(seconds)]}':
                        round(value / total, 6)
                    for pair, value in zip(positions[low:high].tolist(), totals[low:high].tolist()) if value > 0}
                if pair_field in (points_loss.VENDOR_CITY, points_loss.REGION_CITY):
                    pair_shares = {pair: share for pair, share in pair_shares.items()
                                   if not pair.startswith(points_loss.NOT_SPECIFIED + points_loss.CITY_AREA_SEPARATOR)}
                if pair_shares:
                    shares[pair_field] = pair_shares
            if shares:
                entries[group] = {**metadata[group], 'kpi_code': metric['code'], 'areas': shares,
                                  'weight': round(total, 4), 'tests': tests}
    loss_shares = [entry for group in range(groups) for entries in found if (entry := entries.get(group)) is not None]
    # The tests of each group per Vendor, Site Type and area, ordered as value_counts orders them.
    served = [{} for _group in range(groups)]
    for field in (points_loss.VENDOR, points_loss.SITE_TYPE, *(points_loss.AREA_FIELDS if kind != 'speech' else ())):
        if field not in categories:
            continue
        category_codes, names = categories[field]
        unique, cell_of = field_keys[field]
        counts = np.bincount(cell_of, minlength=len(unique))
        bounds = np.searchsorted(unique // len(names), np.arange(groups + 1))
        for group in range(groups):
            found, found_counts = unique[bounds[group]:bounds[group + 1]] % len(names), counts[bounds[group]:bounds[group + 1]]
            if len(np.unique(found_counts)) == len(found_counts):
                # Counts that all differ have one order (by count); ties are ordered as value_counts orders them.
                order = found[np.argsort(-found_counts, kind='stable')]
                served[group][field] = {str(names[position]): int(count)
                                        for position, count in zip(order.tolist(), np.sort(found_counts)[::-1].tolist())}
                continue
            vector = np.zeros(len(names), dtype=np.int64)
            vector[found] = found_counts
            served[group][field] = {str(names[position]): int(vector[position])
                                    for position in nargsort(vector, kind='quicksort', ascending=False) if vector[position]}
    serving_tests = [{**metadata[group], 'counts': served[group]} for group in range(groups) if served[group]]
    return loss_shares, serving_tests


def calculate_points_loss(
    frames: dict[str, pd.DataFrame], levels: Iterable[str] = ('Operator',), configuration: dict | None = None,
    operator_mappings: dict[str, str] | None = None, map_areas=None, time_split: str | None = None,
    progress_callback=None,
) -> dict:
    """The Points Lost Map of a scoring, as ``calculate_scoring`` places it, without calculating the scores.

    It reads the same rows but skips what only the scores need (the All Environments KPIs and the scoring of each
    KPI), so a result calculated from the Scoring History gets its map in a fraction of the time.
    ``progress_callback(share, step)`` follows the KPIs mapped (share from 0 to 1), CDR type by CDR type.
    """
    config = _required_configuration(configuration)
    dimensions = []
    for level in levels:
        canonical = {'operator': 'Operator', 'region': 'Region', 'cluster': 'Cluster', 'city': 'City', 'vendor': 'Vendor',
                     'ranvendor': 'Vendor', 'campaign': 'Campaign', 'datasettype': 'Dataset Type',
                     'datasetkind': 'Dataset Type'}.get(column_identity(level))
        if canonical is None:
            raise ValueError(f'Unsupported scoring level: {level}')
        if canonical not in dimensions:
            dimensions.append(canonical)
    if 'Operator' not in dimensions:
        dimensions.append('Operator')
    campaign_selected = 'Campaign' in dimensions
    group_fields = list(dict.fromkeys(['Campaign', *dimensions, 'environment']))
    keys = [_key_name(field) for field in group_fields]
    if map_areas is None:
        from src.modules.map_areas import area_index
        map_areas = area_index(None)
    mappings = {str(alias).strip().casefold(): str(canonical).strip()
                for alias, canonical in (operator_mappings or {}).items() if str(alias).strip() and str(canonical).strip()}
    time_split = normalize_time_split(time_split) if campaign_selected else None
    geometry = points_loss.AreaGeometry()
    loss_shares: list[dict] = []
    serving_tests: list[dict] = []
    kinds = max(1, len(frames))
    for kind_index, (kind, frame, valid) in enumerate(_prepared_frames(frames, dimensions, config, mappings, map_areas,
                                                                        time_split, campaign_selected, [])):
        step = ((lambda share, detail, kind_index=kind_index: progress_callback((kind_index + share) / kinds, detail))
                if progress_callback else None)
        shares, served = _points_loss_entries(kind, frame, valid, group_fields, keys,
                                              [m for m in config['metrics'] if m['source_kind'] == kind], step)
        loss_shares.extend(shares)
        serving_tests.extend(served)
        geometry.add(frame[valid])
    return {'version': 3, **geometry.document(), 'map_areas': geometry.map_areas(map_areas), 'shares': loss_shares,
            'serving_tests': serving_tests}


def finish_scoring(
    rows: list[dict], global_kpis: list[dict], *, keys: list[str], dimensions: list[str], config: dict,
    baseline_operator: str, baseline_aliases: list[str], warnings: list[str], campaigns: Iterable[str],
    points_loss_document: dict | None,
) -> dict:
    """Score the KPI rows (their values and sample counts at each group) and build the result: totals, GAPs and
    environment scaling. Shared by the calculation from the CDR rows and the one from the Scoring History."""
    metric_by_code = {metric['code']: metric for metric in config['metrics']}
    for row in rows:
        if row['value'] is None:
            continue
        metric = metric_by_code[row['kpi_code']]
        metric_context = metric['contexts'][row['environment']]
        thresholds = metric_context['thresholds']
        ultra = thresholds.get('ultra')
        if isinstance(ultra, dict) and ultra['rule'] in {'best_min', 'best_max'}:
            peers = [r['value'] for r in rows if r['kpi_code'] == row['kpi_code'] and r['value'] is not None
                     and all(r.get(key) == row.get(key) for key in keys if key != 'operator')]
            ultra_value = min(peers) if ultra['rule'] == 'best_min' else max(peers)
        else:
            ultra_value = None
        row['score'] = interpolate_score(
            row['value'], thresholds, ultra_value, metric_context['score_mapping'],
            metric.get('mapping_method', config['interpolation'].get('method', 'piecewise_linear')),
        )
        row['weighted_points'] = row['score'] * row['max_points']
    totals = _totals(rows, keys, config)
    # Scaling is information, not a coverage problem: it is shown apart from the warnings.
    notices = scaling_warnings(totals)
    if any(not row['complete_coverage'] for row in totals):
        warnings.append(_INCOMPLETE_COVERAGE_WARNING)
    gap = _gap_rows(rows, keys, baseline_operator, baseline_aliases, warnings)
    gap_totals = _gap_totals(totals, keys, baseline_operator, baseline_aliases)
    return {'scoring': rows, 'global_kpis': global_kpis,
            'points_loss': points_loss_document,
            'totals': totals, 'charts': [dict(row) for row in totals], 'gap': gap,
            'gap_totals': gap_totals, 'warnings': list(dict.fromkeys(warnings)), 'notices': notices,
            'environment_scaling': environment_scaling(totals),
            'aggregation_levels': dimensions,
            'aggregation_contract_version': AGGREGATION_CONTRACT_VERSION,
            'campaigns': sorted(campaigns, key=lambda value: (campaign_sort_key(value), value)),
            'method_version': method_version_for_configuration(config), 'configuration': config,
            'configuration_hash': configuration_hash(config), 'gap_direction': 'operator_minus_reference',
            'baseline_aliases': baseline_aliases}


def _gap_rows(rows: list[dict], keys: list[str], baseline_operator: str, baseline_aliases: list[str],
              warnings: list[str]) -> list[dict]:
    gap = []
    references = _reference_index(rows, 'kpi_code', keys, baseline_operator, baseline_aliases)
    for row in rows:
        if _is_reference(row, baseline_operator, baseline_aliases):
            continue
        baseline = _reference_for(row, references, 'kpi_code', keys, baseline_operator)
        if baseline is None:
            reference = SAME_OPERATOR_NSA_LABEL if baseline_operator == SAME_OPERATOR_NSA else baseline_operator
            warnings.append(f'Baseline {reference} is unavailable for one or more comparison groups.')
        elif baseline['weighted_points'] is not None and row['weighted_points'] is not None:
            gap.append({**{key: row.get(key) for key in keys}, 'dataset_type': row['dataset_type'], 'kpi': row['kpi'],
                        'kpi_code': row['kpi_code'], 'category': row['category'], 'kpi_type': row['kpi_type'],
                        'baseline_operator': baseline_operator,
                        'baseline_actual_operator': baseline['operator'], 'baseline_points': baseline['weighted_points'], 'operator_points': row['weighted_points'],
                        'gap_points': row['weighted_points'] - baseline['weighted_points']})
    return gap


def most_reliable_result(result: dict, baseline_operator: str = 'EE', configuration: dict | None = None) -> dict | None:
    """The Most Reliable Network scoring of a saved result, or None when its methodology has none.

    Most Reliable rates a subset of the KPIs with its own maximum points and the same
    thresholds, so it reuses the saved KPI measurements and scores: no CDR is read
    again, and every job whose methodology snapshot has Most Reliable points shows it.
    """
    if not isinstance(result, dict):
        return None
    groups = result.get('methodology_groups')
    if isinstance(groups, list) and len(groups) > 1:
        # Scored By campaign: each campaign with the Most Reliable points of its own methodology.
        from src.modules.scoring_methodologies import merge_results, split_result
        parts = []
        for group in groups:
            reliable = most_reliable_result(split_result(result, group), baseline_operator, group['configuration'])
            if reliable is not None:
                parts.append(({**group, 'configuration': reliable['configuration']}, reliable))
        if not parts:
            return None
        merged = merge_results(parts)
        return {**merged, 'configuration_hash': configuration_hash(merged['configuration']),
                'scoring_kind': MOST_RELIABLE_SCORING}
    rows = result.get('scoring')
    snapshot = result.get('configuration') or configuration
    if not isinstance(rows, list) or not isinstance(snapshot, dict):
        return None
    try:
        config = most_reliable_configuration(snapshot)
        if config is None:
            return None
        dimensions = list(result.get('aggregation_levels') or ['Operator'])
        if 'Operator' not in dimensions:
            dimensions.append('Operator')
        keys = [_key_name(field) for field in dict.fromkeys(['Campaign', *dimensions, 'environment'])]
        metrics = {metric['code']: metric for metric in config['metrics']}
        reliable_rows = []
        for row in rows:
            metric = metrics.get(row.get('kpi_code'))
            context = metric['contexts'].get(row.get('environment')) if metric else None
            if context is None:
                continue
            maximum = context['max_points']
            score = row.get('score')
            reliable_rows.append({**row, 'max_points': maximum,
                                  'weighted_points': score * maximum if score is not None else None})
        totals = _totals(reliable_rows, keys, config)
    except (KeyError, TypeError, ValueError):
        return None
    aliases = list(result.get('baseline_aliases') or [baseline_operator])
    # Keep the calculation warnings, except those about KPIs outside the Most Reliable scoring.
    warnings = [warning for warning in result.get('warnings') or [] if warning != _INCOMPLETE_COVERAGE_WARNING
                and not ((match := re.fullmatch(r'\w+: (\S+) requires missing column .+', str(warning)))
                         and match.group(1) not in metrics)]
    if any(not row['complete_coverage'] for row in totals):
        warnings.append(_INCOMPLETE_COVERAGE_WARNING)
    gap = _gap_rows(reliable_rows, keys, baseline_operator, aliases, [])
    reliable = {}
    # The calculations of the National & Geographical Areas Trends and of the Geographical views rate the same KPI subset.
    for key in ('area_summary', 'geographical'):
        if key in result:
            from src.modules.scoring_area_summary import most_reliable_area_summary
            reliable[key] = most_reliable_area_summary(
                result[key], lambda item: most_reliable_result(item, baseline_operator, snapshot),
            )
    return {**result, **reliable, 'scoring': reliable_rows,
            'global_kpis': [row for row in result.get('global_kpis') or [] if row.get('kpi_code') in metrics],
            'totals': totals, 'charts': [dict(row) for row in totals], 'gap': gap,
            'gap_totals': _gap_totals(totals, keys, baseline_operator, aliases),
            'warnings': warnings, 'notices': scaling_warnings(totals),
            'environment_scaling': environment_scaling(totals),
            'configuration': config, 'configuration_hash': configuration_hash(config),
            'scoring_kind': MOST_RELIABLE_SCORING}


def _is_reference(row, baseline_operator, baseline_aliases) -> bool:
    """Whether a row is a reference of the GAP: one of the reference operator or, with Same operator in NSA (NSA vs SA),
    one of an NSA campaign."""
    if baseline_operator == SAME_OPERATOR_NSA:
        return campaign_nr_mode(row.get('campaign')) == 'NSA'
    return _is_baseline(str(row['operator']), baseline_operator, baseline_aliases)


def _reference_group(row, identity, keys, baseline_operator: str = '') -> tuple:
    if baseline_operator == SAME_OPERATOR_NSA:
        # The same operator in the NSA campaign of the same quarter or period.
        return (row[identity], _operator_identity(str(row['operator'])), campaign_pair_key(row.get('campaign')),
                *(row.get(key) for key in keys if key not in {'operator', 'vendor', 'campaign'}))
    return (row[identity], *(row.get(key) for key in keys if key not in {'operator', 'vendor'}))


def _reference_index(records, identity, keys, baseline_operator, baseline_aliases) -> dict[tuple, list[dict]]:
    """The rows of the reference operator by comparison group (the identity and the keys other than operator and
    vendor), so each row finds its reference without going through every row."""
    index: dict[tuple, list[dict]] = {}
    for other in records:
        if _is_reference(other, baseline_operator, baseline_aliases):
            index.setdefault(_reference_group(other, identity, keys, baseline_operator), []).append(other)
    return index


def _reference_for(row, references, identity, keys, baseline_operator: str = ''):
    candidates = references.get(_reference_group(row, identity, keys, baseline_operator), [])
    exact = next((other for other in candidates if other.get('vendor') == row.get('vendor')), None)
    return exact if exact is not None else next((other for other in candidates if other.get('vendor') == 'All'), None)


def _gap_totals(totals: list[dict], keys: list[str], baseline_operator: str, baseline_aliases: list[str]) -> list[dict]:
    gap_totals = []
    references = _reference_index(totals, 'category', keys, baseline_operator, baseline_aliases)
    for row in totals:
        if _is_reference(row, baseline_operator, baseline_aliases):
            continue
        baseline = _reference_for(row, references, 'category', keys, baseline_operator)
        if baseline is not None:
            complete = baseline['complete_coverage'] and row['complete_coverage']
            gap_totals.append({**{key: row.get(key) for key in keys}, 'category': row['category'],
                               'baseline_operator': baseline_operator, 'baseline_actual_operator': baseline['operator'],
                               'baseline_points': baseline['weighted_points'], 'operator_points': row['weighted_points'],
                               'gap_points': row['weighted_points'] - baseline['weighted_points'] if complete else None,
                               'complete_coverage': complete})
    return gap_totals


def environment_scaling(totals: list[dict]) -> dict | None:
    """The environments scaled out of the Combined scores, if any, and the factor applied."""
    row = next((row for row in totals if row.get('environment') == 'Combined' and row.get('category') == 'Overall'
                and row.get('scaled_environments')), None)
    if row is None:
        return None
    return {'scaled_environments': row['scaled_environments'], 'environments_with_results': row['environments_with_results'],
            'scale_factor': row.get('scale_factor')}


def apply_environment_scaling(result: dict, baseline_operator: str = 'EE') -> dict:
    """Scale the Combined scores of a result saved before scaling existed.

    The totals are rebuilt from the saved KPI scores, so opening an earlier job
    shows environments without results scaled, without calculating it again.
    """
    if not isinstance(result, dict) or 'environment_scaling' in result:
        return result
    rows = result.get('scoring')
    configuration = result.get('configuration')
    if not isinstance(rows, list) or not rows or not isinstance(configuration, dict):
        return result
    try:
        config = _required_configuration(configuration)
        dimensions = list(result.get('aggregation_levels') or ['Operator'])
        if 'Operator' not in dimensions:
            dimensions.append('Operator')
        keys = [_key_name(field) for field in dict.fromkeys(['Campaign', *dimensions, 'environment'])]
        totals = _totals(rows, keys, config)
    except (KeyError, TypeError, ValueError):
        return result
    scaling = environment_scaling(totals)
    result['environment_scaling'] = scaling
    if scaling is None:
        return result
    aliases = list(result.get('baseline_aliases') or [baseline_operator])
    result['totals'] = totals
    result['charts'] = [dict(row) for row in totals]
    result['gap_totals'] = _gap_totals(totals, keys, baseline_operator, aliases)
    result['notices'] = scaling_warnings(totals)
    return result


def _totals(rows: list[dict], keys: list[str], configuration: dict) -> list[dict]:
    config = _required_configuration(configuration)
    metrics = config['metrics']
    environments = config['scope']['environments']
    grouped = {}
    for row in rows:
        grouped.setdefault(tuple(row.get(key) for key in keys), []).append(row)
    totals = []
    categories = list(dict.fromkeys(metric['category'] for metric in metrics)) + ['Overall']
    for group, members in grouped.items():
        metadata = dict(zip(keys, group))
        for category in categories:
            expected = [m for m in metrics
                        if ('dataset_type' not in keys or m['source_kind'].title() == metadata['dataset_type'])
                        and (category == 'Overall' or m['category'] == category)
                        and m['contexts'][metadata['environment']]['max_points'] > 0]
            if not expected:
                zero_weight_metrics = [m for m in metrics
                                       if ('dataset_type' not in keys or m['source_kind'].title() == metadata['dataset_type'])
                                       and (category == 'Overall' or m['category'] == category)]
                if not zero_weight_metrics:
                    continue
            selected = [row for row in members if category == 'Overall' or row['category'] == category]
            active_codes = {metric['code'] for metric in expected}
            selected_active = [row for row in selected if row['kpi_code'] in active_codes]
            maximum = sum(m['contexts'][metadata['environment']]['max_points'] for m in expected)
            totals.append(_summary({**metadata, 'category': category}, selected, maximum,
                                   len(selected_active) == len(expected) and all(row['score'] is not None for row in selected_active)))
    combined = {}
    base_keys = [key for key in keys if key != 'environment'] + ['category']
    for row in totals:
        combined.setdefault(tuple(row.get(key) for key in base_keys), []).append(row)
    active_environments = [
        name for name in environments
        if environments[name].get('total_points', 0) > 0
    ]
    # Filters can leave an environment without results in every series of the
    # calculation (one City is only Drive - City, for example). The Combined
    # scores then scale the environments with results to the full maximum, the
    # same way for every series. An environment measured in any series is never
    # scaled: series without it keep their partial score and its notes.
    measured = {row.get('environment') for row in rows if row.get('value') is not None}
    with_results = [name for name in active_environments if name in measured]
    scaled_out = [name for name in active_environments if name not in measured] if with_results else []
    included = with_results if scaled_out else active_environments
    for group, members in combined.items():
        metadata = dict(zip(base_keys, group))
        expected = [m for m in metrics
                    if ('dataset_type' not in keys or m['source_kind'].title() == metadata['dataset_type'])
                    and (metadata['category'] == 'Overall' or m['category'] == metadata['category'])
                    and sum(m['contexts'][name]['max_points'] for name in active_environments
                            if name in m['contexts']) > 0]

        def maximum_of(names: list[str]) -> float:
            return sum(sum(m['contexts'][name]['max_points'] for name in names if name in m['contexts']) for m in expected)

        maximum = maximum_of(active_environments)
        active_members = [row for row in members if row.get('environment') in included]
        reached = maximum_of(included)
        complete = (len(active_members) == len(included) and reached > 0
                    and all(row['complete_coverage'] for row in active_members))
        summary = _summary({**metadata, 'environment': 'Combined'}, active_members, maximum, complete, summary=True)
        if scaled_out and reached > 0:
            factor = maximum / reached
            summary.update({
                'unscaled_points': summary['weighted_points'], 'unscaled_max_points': reached,
                'scale_factor': factor, 'scaled_environments': scaled_out, 'environments_with_results': with_results,
            })
            for key in ('weighted_points', 'total_points', 'available_points'):
                summary[key] *= factor
            summary['score'] = summary['weighted_points'] / maximum if complete and maximum > 0 else None
        elif scaled_out:
            summary.update({'scaled_environments': scaled_out, 'environments_with_results': with_results})
        totals.append(summary)
    return totals


def _number_text(value: float) -> str:
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def scaling_warnings(totals: list[dict]) -> list[str]:
    """Explain the Combined scores scaled because environments have no results in any series."""
    row = next((row for row in totals if row.get('environment') == 'Combined' and row.get('category') == 'Overall'
                and row.get('scaled_environments')), None)
    if row is None:
        return []
    missing = ', '.join(row['scaled_environments'])
    verb = 'has' if len(row['scaled_environments']) == 1 else 'have'
    if not row.get('scale_factor'):
        return [f'{missing} {verb} no results in any series with the selected filters, and the environments with results '
                f'have no points, so the Combined scores cannot be scaled.']
    return [f"Scaled to the maximum scoring: {missing} {verb} no results in any series with the selected filters, so the "
            f"Combined scores use {', '.join(row['environments_with_results'])} "
            f"({_number_text(row['unscaled_max_points'])} points) scaled ×{row['scale_factor']:.3f} "
            f"to the full {_number_text(row['max_points'])} points."]


def _summary(metadata: dict, members: list[dict], maximum: float, complete: bool, summary: bool = False) -> dict:
    points = sum(row['weighted_points'] or 0 for row in members)
    available = sum(row['available_points'] if summary else (row['max_points'] if row['score'] is not None else 0)
                    for row in members)
    return {**metadata, 'weighted_points': points, 'total_points': points, 'max_points': maximum,
            'available_points': available, 'score': points / maximum if complete and maximum > 0 else None,
            'complete_coverage': complete, 'sample_count': sum(row['sample_count'] for row in members)}
