"""Network Insights: radio quality, observed sites, spectrum and deployment.

The analysis reads the per-sample radio fields already present in the CDRs
(RSRP, SINR, serving cells, frequencies and coordinates) together with the
workspace's Operator mappings, the cell inventories uploaded as Vendor
mapping datasets and the licensed spectrum holdings configured in Workspace
Config. Every function below is free of web-framework dependencies so it can
be tested directly.
"""
# Postponed annotations are deliberately not enabled: FastAPI must resolve the
# request models and parameters declared inside install_network_insights_routes.
import csv
import io
import math
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import chain
from typing import Any, Callable, Iterable
from uuid import uuid4

import numpy as np
import pandas as pd

from src.modules.cell_identity import nr_cell_bits, nr_gnodeb
from src.modules.column_names import campaign_sort_key, column_identity, compact_campaign_value, operator_vendor_filter_values, vendor_filter_values
from src.modules.mapping_order import swap_operator_vendor, swap_vendor_operator
from src.modules.value_maps import ValueMapper, field_kind
from src.modules.cdr_auto_selection import (
    CAMPAIGN_PRESET_LABELS, SINGLE_CAMPAIGN_PRESETS, campaign_presets, candidate_cdrs, describe_cdrs, one_campaign,
    resolve_campaign_filter, resolve_cdrs,
)
from src.modules.cdr_environments import ENVIRONMENTS, environment_class, environment_order
from src.modules.cdr_field_profiles import NETCHECK_PROFILE, CdrFieldProfile, workspace_field_profile
from src.modules.cdr_facets import cascading_options, stored_facets
from src.modules.value_patterns import ValueSet, is_pattern
from src.modules.operator_roles import drop_excluded_operators, excluded_operators
from src.modules.mapping_order import dimension_order_key, operator_order_key, vendor_order_key
from src.modules.output_layout import NETWORK_INSIGHTS_FOLDER, module_output_dir
from src.modules import inventory_insights as ii
from src.modules import network_insights_favourites as ni_favourites
from src.modules.network_insights_findings import findings_payload, mode_of_test
from src.modules.scoring_themes import THEMES, dashboard_chart_style, load_user_theme, normalize_theme, save_user_theme, themes_payload, use_theme
from src.modules.network_inventory import dataset_revision, effective_snapshot_date, ensure_inventory_cells, network_family
from src.modules.network_inventory import inventory_datasets as snapshot_datasets
from src.modules.serving_cells import load_serving_networks, serving_families


NETWORK_INSIGHTS_KINDS = ('data', 'voice', 'speech')
# Bump when the normalised samples or the analysis payload change shape.
SAMPLES_CACHE_VERSION = 10
ANALYSIS_CACHE_VERSION = 30
# Analyses kept in the workspace cache (each a few MB) and in memory, to show them again without calculating them.
ANALYSES_KEPT = 500
ANALYSES_IN_MEMORY = 24
INVENTORY_CACHE_VERSION = 4
OBSERVED_CACHE_VERSION = 9
# Columns of the Observed Sites/Cells (from CDRs) tables.
OBSERVED_COLUMNS = (
    'Operator', 'Vendor', 'Region', 'Cluster', 'City', 'Technology', 'Site_ID', 'Cell_ID', 'Band',
    'CDR_Types', 'Campaigns', 'Samples', 'Latitude', 'Longitude', 'RSRP_Mean', 'SINR_Mean',
)
SPECTRUM_HOLDINGS_STATE_KEY = 'network_spectrum_holdings'
# The colour theme each user chose here is kept apart from that of Scoring (see scoring_themes.load_user_theme).
THEME_MODULE = 'network_insights'

# Each logical radio field lists, per CDR type, the source columns that carry it in priority order (those of NetCheck
# CDRs; every CDR type lists its own, see cdr_field_profiles). Voice uses the measuring (A) side.
RF_FIELD_ALIASES: dict[str, dict[str, tuple[str, ...]]] = NETCHECK_PROFILE.rf_field_aliases
DIMENSION_ALIASES = NETCHECK_PROFILE.dimension_aliases
GROUPINGS = {'operator': 'Operator', 'vendor': 'Vendor', 'region': 'Region', 'cluster': 'Cluster', 'city': 'City',
             'environment': 'Environment', 'kind': 'CDR type', 'technology': 'Technology', 'campaign': 'Campaign'}
TECHNOLOGIES = {'lte': 'LTE', 'nr': 'NR', 'lte_nr': 'LTE+NR'}

# Default classification bands. Thresholds are user-adjustable in the module;
# these defaults follow common drive-test reporting practice.
# LTE RSRP/SINR and NR SS-RSRP/SS-SINR use different reference signals, so
# each technology has its own thresholds.
DEFAULT_COVERAGE_THRESHOLD = -110.0
DEFAULT_INTERFERENCE_THRESHOLD = 0.0
DEFAULT_NR_COVERAGE_THRESHOLD = -115.0
DEFAULT_NR_INTERFERENCE_THRESHOLD = -3.0
RSRP_CLASSES = (
    ('Excellent', -80.0, '#2E8B57'),
    ('Good', -90.0, '#8BC34A'),
    ('Fair', -100.0, '#F2C230'),
    ('Poor', -110.0, '#F08A24'),
    ('Very poor', float('-inf'), '#D7263D'),
)
SINR_CLASSES = (
    ('Excellent', 20.0, '#2E8B57'),
    ('Good', 13.0, '#8BC34A'),
    ('Fair', 5.0, '#F2C230'),
    ('Poor', 0.0, '#F08A24'),
    ('Bad', float('-inf'), '#D7263D'),
)
OPERATOR_FALLBACK_COLOURS = ('#6D46A8', '#0B7A75', '#D9480F', '#1C7ED6', '#C2255C', '#5C940D', '#E67700', '#495057')
SERIES_DASHES = ([], [12, 8], [3, 6], [16, 6, 3, 6])

# 3GPP downlink EARFCN ranges (TS 36.101) and NR band centre frequencies used
# to classify the spectrum each sample was served on.
LTE_EARFCN_BANDS = (
    (1, 0, 599), (3, 1200, 1949), (7, 2750, 3449), (8, 3450, 3799), (20, 6150, 6449),
    (28, 9210, 9659), (32, 9920, 10359), (38, 37750, 38249), (40, 38650, 39649),
    (41, 39650, 41589), (42, 41590, 43589), (43, 43590, 45589),
)
BAND_CATALOGUE: dict[str, tuple[int, str]] = {
    'B1': (2100, 'FDD'), 'B3': (1800, 'FDD'), 'B7': (2600, 'FDD'), 'B8': (900, 'FDD'), 'B20': (800, 'FDD'),
    'B28': (700, 'FDD'), 'B32': (1500, 'SDL'), 'B38': (2600, 'TDD'), 'B40': (2300, 'TDD'), 'B41': (2500, 'TDD'),
    'B42': (3500, 'TDD'), 'B43': (3700, 'TDD'),
    'n1': (2100, 'FDD'), 'n3': (1800, 'FDD'), 'n7': (2600, 'FDD'), 'n8': (900, 'FDD'), 'n20': (800, 'FDD'),
    'n28': (700, 'FDD'), 'n38': (2600, 'TDD'), 'n40': (2300, 'TDD'), 'n41': (2500, 'TDD'), 'n77': (3700, 'TDD'),
    'n78': (3500, 'TDD'), 'n258': (26000, 'TDD'),
}
BAND_CLASSES = ('Low', 'Mid', 'High (TDD)')
SPECTRUM_DUPLEX_VALUES = ('FDD', 'TDD', 'SDL')

# SA CDRs write NR serving cells as [5G NR n78, TAC, NCI, ARFCN].
_TRACE_TOKEN = re.compile(r'\[\s*(?:5G\s+)?(LTE E-UTRA|NR|UMTS|GSM)[^,\]]*?\s(?:n?(\d+))?\s*,\s*([^,\]]*)\s*,\s*([^,\]]*)\s*,\s*([^,\]]*)\]', re.I)
_NUMBER = re.compile(r'-?\d+(?:\.\d+)?')


def band_class(band: str) -> str:
    """Return Low, Mid or High (TDD) for an LTE (``B3``) or NR (``n78``) band."""
    details = BAND_CATALOGUE.get(str(band).strip())
    if not details:
        return ''
    frequency, duplex = details
    if frequency < 1000:
        return 'Low'
    if duplex == 'TDD':
        return 'High (TDD)'
    return 'Mid'


def lte_band_for_earfcn(value: object) -> str:
    """Map an LTE downlink EARFCN to its band label, for example ``B3``."""
    try:
        earfcn = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return ''
    for band, low, high in LTE_EARFCN_BANDS:
        if low <= earfcn <= high:
            return f'B{band}'
    return ''


def sequence_values(value: object) -> list[str]:
    """Split ``[a]->[b]`` or ``a->b`` sequences into their values."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    text = str(value).strip()
    if not text or text.casefold() in {'nan', 'none', '<na>'}:
        return []
    return [part.strip(' []') for part in text.split('->') if part.strip(' []')]


def lte_enodeb_from_eci(value: object) -> int | None:
    """Return the physical eNodeB of an LTE E-UTRAN Cell Identity (ECI // 256)."""
    try:
        eci = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    # Smaller identities are 2G/3G cell IDs, which carry no eNodeB.
    return eci // 256 if eci > 65535 else None


def parse_cell_trace(value: object) -> list[dict[str, Any]]:
    """Parse ``[LTE E-UTRA 7, TAC, ECI, EARFCN]->[...]`` serving-cell traces."""
    cells = []
    for match in _TRACE_TOKEN.finditer(str(value or '')):
        technology, band_number, _area, cell, channel = match.groups()
        technology = technology.upper()
        band = ''
        if technology.startswith('LTE'):
            band = f'B{band_number}' if band_number else lte_band_for_earfcn(channel)
        cells.append({'technology': 'LTE' if technology.startswith('LTE') else technology, 'band': band,
                      'cell': str(cell).strip(), 'channel': str(channel).strip()})
    return cells


def nr_band_label(value: object) -> str:
    """Return ``n78`` for ``NR BAND 78`` (first band of a sequence)."""
    for item in sequence_values(value):
        number = re.search(r'(\d+)', item)
        if number:
            return f'n{number.group(1)}'
    return ''


def enodeb_label(value: object) -> str:
    """Normalise Speech eNodeB identifiers such as ``L 601983``."""
    for item in sequence_values(value):
        number = re.search(r'(\d+)', item)
        if number:
            return number.group(1)
    return ''


_RANK_SHARE = re.compile(r'Rank\s*([1-4])\s*:\s*(\d+(?:\.\d+)?)', re.I)


def rank_shares(value: object) -> tuple[float, float, float, float] | None:
    """The time share (%) at rank 1 to 4 of a ``([Rank1: 69.57],[Rank2: 30.43],…)`` Rank Index, or ``None``."""
    shares = [0.0, 0.0, 0.0, 0.0]
    for rank, share in _RANK_SHARE.findall(str(value or '')):
        shares[int(rank) - 1] += float(share)
    total = sum(shares)
    if total <= 0:
        return None
    return tuple(round(share / total * 100, 2) for share in shares)


def mean_rank(shares: tuple[float, ...] | None) -> float:
    """The mean rank of a time share per rank."""
    return sum((index + 1) * share for index, share in enumerate(shares)) / 100 if shares else math.nan


def first_integer(value: object) -> float:
    """The first whole number of a ``[163]->[338]`` sequence (the first NR PCI or ARFCN), else NaN."""
    for item in sequence_values(value):
        number = re.fullmatch(r'\d+(?:\.0+)?', item.strip())
        if number:
            return float(int(float(item)))
    return math.nan


def classify(value: float, classes: tuple[tuple[str, float, str], ...]) -> tuple[str, str]:
    """Return the (label, colour) of the first class whose lower bound is reached."""
    for label, lower, colour in classes:
        if value >= lower:
            return label, colour
    return classes[-1][0], classes[-1][2]


def resolve_source_columns(available: Iterable[str], kind: str, profile: CdrFieldProfile = NETCHECK_PROFILE) -> dict[str, str]:
    """Pick, for one CDR type, the source column carrying each logical field (the columns of the field profile)."""
    lookup = {column_identity(column): str(column) for column in available}
    resolved: dict[str, str] = {}
    for field, aliases in profile.dimension_aliases.items():
        column = next((lookup[column_identity(alias)] for alias in aliases if column_identity(alias) in lookup), None)
        if column:
            resolved[field] = column
    for field, by_kind in profile.rf_field_aliases.items():
        column = next((lookup[column_identity(alias)] for alias in by_kind.get(kind, ()) if column_identity(alias) in lookup), None)
        if column:
            resolved[field] = column
    return resolved


def normalise_samples(frame: pd.DataFrame, kind: str, columns: dict[str, str]) -> pd.DataFrame:
    """Return one tidy row per CDR sample with the logical radio fields."""
    result = pd.DataFrame(index=frame.index)
    result['kind'] = kind.title()
    for field in ('operator', 'operator_vendor', 'vendor', 'campaign', 'region', 'cluster', 'city'):
        source = columns.get(field)
        values = frame[source] if source in frame.columns else pd.Series('', index=frame.index)
        result[field] = values.fillna('').astype(str).str.strip()
    campaigns = {value: compact_campaign_value(value) or value for value in pd.unique(result['campaign'])}
    result['campaign'] = result['campaign'].map(campaigns)
    groups = [{'canonical': name} for name in pd.unique(result['operator']) if name]
    swapped = {value: swap_operator_vendor(value, groups) for value in pd.unique(result['operator_vendor'])}
    result['vendor_operator'] = result['operator_vendor'].map(swapped)
    for field in ('latitude', 'longitude', 'lte_rsrp', 'nr_rsrp', 'lte_sinr', 'nr_sinr', 'lte_bandwidth', 'nr_bandwidth',
                  'lte_aggregated_bandwidth', 'mean_data_rate', 'rtt_median', 'packets_lost', 'packets_sent', 'jitter',
                  'nr_time', 'test_duration'):
        source = columns.get(field)
        result[field] = pd.to_numeric(frame[source], errors='coerce') if source in frame.columns else math.nan
    for field in ('test_result', 'type_of_test', 'serving_network', 'serving_host', 'serving_scenario'):
        source = columns.get(field)
        values = frame[source] if source in frame.columns else pd.Series('', index=frame.index)
        result[field] = values.fillna('').astype(str).str.strip()
    # The kind of the site that served each sample: its network, "on" the host network when another one hosts it, NNS
    # sites apart (as the Points Lost of Scoring).
    owner, host = result['serving_network'], result['serving_host']
    kinds = owner.where(~((host != '') & (host.str.casefold() != owner.str.casefold())), owner + ' on ' + host)
    kinds = kinds.where(result['serving_scenario'].str.casefold() != 'nns', 'NNS · ' + kinds)
    result['site_type'] = kinds.where(owner != '', '')
    # Cities, Towns or Roads and railways, from the most detailed environment level of each test.
    environments = pd.Series('', index=frame.index, dtype=object)
    for field in ('environment', 'environment_route'):
        source = columns.get(field)
        if source in frame.columns:
            values = frame[source].astype(object).where(frame[source].notna(), '')
            classes = values.map({value: environment_class(value) for value in pd.unique(values)})
            environments = environments.where(environments != '', classes)
    result['environment'] = environments
    mode_source = columns.get('mode')
    if mode_source in frame.columns:
        modes = frame[mode_source].astype(object).where(frame[mode_source].notna(), '')
        result['mode'] = modes.map({value: mode_of_test(value) for value in pd.unique(modes)})
    else:
        result['mode'] = ''
    test_source = columns.get('test_name')
    if test_source in frame.columns:
        names = frame[test_source].astype(object).where(frame[test_source].notna(), '')
        result['download'] = names.map({name: bool(DOWNLOAD_TEST.search(str(name))) for name in pd.unique(names)}).astype(bool)
    else:
        result['download'] = False
    # Values outside physical ranges are measurement placeholders.
    for field, low, high in (('lte_rsrp', -160, -20), ('nr_rsrp', -160, -20), ('lte_sinr', -30, 50), ('nr_sinr', -30, 50)):
        result.loc[(result[field] < low) | (result[field] > high), field] = math.nan
    result.loc[(result['latitude'].abs() > 90) | (result['latitude'] == 0), 'latitude'] = math.nan
    result.loc[(result['longitude'].abs() > 180) | (result['longitude'] == 0), 'longitude'] = math.nan

    # Traces repeat heavily across samples: parse each distinct value once.
    def parsed_column(field: str, parser) -> pd.Series:
        source = columns.get(field)
        if source not in frame.columns:
            return pd.Series([None] * len(frame), index=frame.index, dtype=object)
        values = frame[source].astype(object).where(frame[source].notna(), '')
        cache = {value: parser(value) for value in pd.unique(values)}
        return values.map(cache)

    def trace_cells(value: object) -> tuple[tuple[str, ...], tuple[str, ...], str, str]:
        cells, enodebs, band = [], [], ''
        nr_cells = []
        for cell in parse_cell_trace(value):
            if cell['technology'] == 'NR':
                nr_cells.append(cell['cell'])
                continue
            if cell['technology'] != 'LTE':
                continue
            band = band or cell['band']
            cells.append(cell['cell'])
            enodeb = lte_enodeb_from_eci(cell['cell'])
            if enodeb is not None:
                enodebs.append(str(enodeb))
        if not cells and nr_cells:
            # SA samples are served by NR cells only: their nodes are gNodeBs (NCI / 16384).
            cells = nr_cells
            enodebs = [f'gNB {node}' for node in map(nr_gnodeb, nr_cells) if node is not None]
            return tuple(dict.fromkeys(cells)), tuple(dict.fromkeys(enodebs)), band, 'NR'
        return tuple(dict.fromkeys(cells)), tuple(dict.fromkeys(enodebs)), band, 'LTE' if cells else ''

    def id_cells(value: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
        cells = tuple(dict.fromkeys(sequence_values(value)))
        enodebs = tuple(dict.fromkeys(str(item) for item in map(lte_enodeb_from_eci, cells) if item is not None))
        return cells, enodebs

    traces = parsed_column('cell_trace', trace_cells)
    ids = parsed_column('cell_ids', id_cells)
    speech_enodebs = parsed_column('enodeb_id', enodeb_label)
    earfcn_bands = parsed_column('earfcn', lambda value: lte_band_for_earfcn((sequence_values(value) or [''])[0]))
    cells_column, enodebs_column, bands_column, technologies_column = [], [], [], []
    for trace, identified, speech_enodeb, earfcn_band in zip(traces, ids, speech_enodebs, earfcn_bands, strict=True):
        cells, enodebs, band, cell_technology = trace if trace else ((), (), '', '')
        if not cells and identified:
            cells, enodebs = identified
            cell_technology = ''
        if speech_enodeb:
            enodebs = (speech_enodeb,)
        # Tuples are shared with the parse cache, keeping memory flat.
        cells_column.append(cells)
        enodebs_column.append(enodebs)
        bands_column.append(band or earfcn_band or '')
        technologies_column.append(cell_technology)
    result['cells'] = cells_column
    result['enodebs'] = enodebs_column
    # LTE or NR when the serving-cell trace says so; empty for bare Cell IDs.
    result['cells_technology'] = technologies_column
    result['lte_band'] = bands_column
    nr_source = columns.get('nr_band')
    result['nr_band'] = frame[nr_source].map(nr_band_label) if nr_source in frame.columns else ''
    # The first NR PCI and SSB NR-ARFCN identify the NR cell of NSA samples (see inventory_insights.nsa_nr_cells).
    for field in ('nr_pci', 'nr_arfcn'):
        result[field] = parsed_column(field, first_integer).astype(float)
    result.loc[~result['nr_pci'].between(0, 1007), 'nr_pci'] = math.nan
    for technology in ('lte', 'nr'):
        shares = parsed_column(f'{technology}_rank', rank_shares)
        result[f'{technology}_rank_shares'] = shares
        result[f'{technology}_rank'] = shares.map(mean_rank).astype(float)
    layers = columns.get('nr_layers')
    result['nr_layers'] = math.nan
    if layers in frame.columns:
        result['nr_layers'] = pd.to_numeric(frame[layers], errors='coerce').where(lambda values: values.between(1, 8))
    return result.reset_index(drop=True)


def _quantile(values: pd.Series, q: float) -> float | None:
    return round(float(values.quantile(q)), 2) if len(values) else None


def _share(mask: pd.Series) -> float | None:
    return round(float(mask.mean()) * 100, 1) if len(mask) else None


def rf_summary(
    samples: pd.DataFrame, technology: str, group: str | None,
    coverage_threshold: float, interference_threshold: float,
) -> list[dict[str, Any]]:
    """Summarise RSRP/SINR and observed sites per Operator (and group)."""
    rsrp, sinr = f'{technology}_rsrp', f'{technology}_sinr'
    keys = ['operator', *([group] if group else [])]
    rows = []
    for key, part in samples.groupby(keys, sort=False, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        rsrp_values = part[rsrp].dropna()
        sinr_values = part[sinr].dropna()
        enodebs = set(chain.from_iterable(part['enodebs']))
        cells = set(chain.from_iterable(part['cells']))
        rows.append({
            'operator': key[0], 'group': key[1] if group else '',
            'samples': int(len(part)),
            'rsrp_samples': int(len(rsrp_values)),
            'rsrp_mean': round(float(rsrp_values.mean()), 2) if len(rsrp_values) else None,
            'rsrp_median': _quantile(rsrp_values, .5), 'rsrp_p10': _quantile(rsrp_values, .1), 'rsrp_p90': _quantile(rsrp_values, .9),
            'low_coverage_share': _share(rsrp_values < coverage_threshold),
            'rsrp_classes': class_distribution(rsrp_values, RSRP_CLASSES),
            'sinr_samples': int(len(sinr_values)),
            'sinr_mean': round(float(sinr_values.mean()), 2) if len(sinr_values) else None,
            'sinr_median': _quantile(sinr_values, .5), 'sinr_p10': _quantile(sinr_values, .1), 'sinr_p90': _quantile(sinr_values, .9),
            'high_interference_share': _share(sinr_values < interference_threshold),
            'sinr_classes': class_distribution(sinr_values, SINR_CLASSES),
            'observed_enodebs': len(enodebs), 'observed_cells': len(cells),
        })
    return rows


def class_distribution(values: pd.Series, classes: tuple[tuple[str, float, str], ...]) -> list[dict[str, Any]]:
    """Return the share of samples in each quality class, best first."""
    if not len(values):
        return []
    numbers = values.to_numpy(dtype=float)
    # Each value belongs to the first class whose lower bound it reaches.
    remaining = np.ones(len(numbers), dtype=bool)
    shares = []
    for label, lower, colour in classes:
        reached = remaining & (numbers >= lower) if not math.isinf(lower) else remaining
        shares.append({'label': label, 'colour': colour, 'share': round(int(reached.sum()) / len(numbers) * 100, 1)})
        remaining &= ~reached
    return shares


def operator_colours(operators: Iterable[str], mapping_groups: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Use the workspace Operator Map colours, with a stable fallback palette."""
    configured = {
        str(group.get('canonical') or '').strip().casefold(): str(group.get('color') or '').strip()
        for group in mapping_groups or []
    }
    colours = {}
    for index, operator in enumerate(dict.fromkeys(operators)):
        colour = configured.get(str(operator).casefold())
        colours[operator] = colour if re.fullmatch(r'#[0-9a-fA-F]{6}', colour or '') else OPERATOR_FALLBACK_COLOURS[index % len(OPERATOR_FALLBACK_COLOURS)]
    return colours


def cdf_payload(
    samples: pd.DataFrame, value_column: str, group: str | None, title: str, metric_label: str,
    colours: dict[str, str], *, points: int = 120, dash_groups: dict[str, str] | None = None,
    widths: dict[str, int] | None = None, order_key: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Build a Canvas CDF model (one curve per Operator and group).

    ``dash_groups`` maps each Operator label to its secondary grouping value,
    so curves sharing an Operator colour use a different line style per value.
    ``widths`` maps each label to its line width (newer campaigns are thicker).
    ``order_key`` orders the curves by their Operator label (see ``mapping_order``).
    """
    dash_values = sorted(set(dash_groups.values()), key=str.casefold) if dash_groups else []
    series = []
    legend = []
    keys = ['operator', *([group] if group else [])]
    lows, highs = [], []
    group_values = list(dict.fromkeys(samples[group])) if group else []
    grouped = [(key if isinstance(key, tuple) else (key,), part) for key, part in samples.groupby(keys, sort=False, dropna=False)]
    if order_key:
        grouped.sort(key=lambda item: order_key(str(item[0][0])))
    ordered_values = []
    for key, part in grouped:
        values = part[value_column].dropna().sort_values()
        if values.empty:
            continue
        ordered_values.append(values.to_numpy(dtype=float))
        quantiles = [index / (points - 1) for index in range(points)]
        x = [round(float(value), 2) for value in np.quantile(values.to_numpy(dtype=float), quantiles)]
        lows.append(x[0]); highs.append(x[-1])
        name = ' · '.join(str(item) for item in key if str(item))
        if group:
            dash = SERIES_DASHES[group_values.index(key[1]) % len(SERIES_DASHES)]
        elif dash_groups and key[0] in dash_groups:
            dash = SERIES_DASHES[dash_values.index(dash_groups[key[0]]) % len(SERIES_DASHES)]
        else:
            dash = []
        colour = colours.get(key[0], OPERATOR_FALLBACK_COLOURS[0])
        width = (widths or {}).get(key[0], 3)
        series.append({'name': name, 'colour': colour, 'width': width, 'dash': dash, 'x': x, 'y': quantiles})
        legend.append({'label': name, 'colour': colour, 'width': width, 'dash': dash})
    domain_x = [min(lows), max(highs)] if lows else [0, 1]
    if lows:
        # As in CDR Analysis: the axis ends where most curves have passed 99% and converged, instead of stretching to
        # the last outlier; every curve stops there at its cumulative share.
        from src.modules.cdr_reporting import _cdf_terminal_x_maximum

        high = _cdf_terminal_x_maximum([values.tolist() for values in ordered_values], domain_x[0], domain_x[1])
        if domain_x[0] < high < domain_x[1]:
            for item, values in zip(series, ordered_values, strict=True):
                kept = [(x_value, y_value) for x_value, y_value in zip(item['x'], item['y'], strict=True) if x_value < high]
                kept.append((round(high, 2), float(np.searchsorted(values, high, side='right')) / len(values)))
                item['x'], item['y'] = [point[0] for point in kept], [point[1] for point in kept]
            domain_x = [domain_x[0], high]
    if domain_x[0] == domain_x[1]:
        domain_x = [domain_x[0] - 1, domain_x[1] + 1]
    return {
        'renderer': 'catalog-v2', 'width': 1600, 'height': 900, 'type': 'cdf' if series else 'empty',
        'title': title, 'metric': metric_label,
        'message': 'No samples are available for this selection.',
        'legend': {'position': 'right', 'line_markers': True, 'items': legend},
        'label_position': '', 'label_format': {}, 'legend_format': {},
        'axis_ranges': {'x': [None, None], 'y': [None, None]},
        'domain': {'x': domain_x, 'y': [0, 1]},
        'series': series,
    }


def campaign_line_widths(campaigns: dict[str, str], families: dict[str, str]) -> dict[str, int]:
    """Line width per label: the latest campaign of each Operator/Vendor is the thickest.

    Like the PPT Dashboard CDFs, two campaigns use widths 1 and 4 and longer
    histories thin out by one per older campaign.
    """
    from src.modules.cdr_reporting import _campaign_sort_key

    by_family: dict[str, set[str]] = {}
    for label, campaign in campaigns.items():
        if campaign:
            by_family.setdefault(families.get(label, ''), set()).add(campaign)
    ranks: dict[str, dict[str, int]] = {}
    for family, values in by_family.items():
        ordered = sorted(values, key=_campaign_sort_key)
        if len(ordered) == 2:
            ranks[family] = {ordered[0]: 1, ordered[1]: 4}
        else:
            ranks[family] = {campaign: max(1, 4 - index) for index, campaign in enumerate(reversed(ordered))}
    return {label: ranks.get(families.get(label, ''), {}).get(campaign, 3) for label, campaign in campaigns.items()}


def grid_cells(
    samples: pd.DataFrame, value_column: str, threshold: float, grid_metres: float, min_samples: int,
) -> tuple[pd.DataFrame, float]:
    """Aggregate samples into square grid cells; coarsen very dense grids."""
    located = samples.dropna(subset=['latitude', 'longitude', value_column])
    if located.empty:
        return pd.DataFrame(), grid_metres
    effective = max(25.0, float(grid_metres))
    reference_latitude = math.radians(float(located['latitude'].median()))
    while True:
        latitude_step = effective / 111_320
        longitude_step = effective / (111_320 * max(math.cos(reference_latitude), 0.2))
        frame = located.assign(
            row=(located['latitude'] / latitude_step).round().astype('int64'),
            column=(located['longitude'] / longitude_step).round().astype('int64'),
            bad=located[value_column] < threshold,
        )
        cells = frame.groupby(['row', 'column'], sort=False).agg(
            samples=(value_column, 'size'), mean=(value_column, 'mean'), bad_share=('bad', 'mean'),
        ).reset_index()
        cells = cells.loc[cells['samples'] >= max(1, int(min_samples))]
        # The most frequent City and Region of each grid cell.
        for field in ('city', 'region'):
            counts = frame.groupby(['row', 'column', field], sort=False).size().reset_index(name='count')
            counts = counts.sort_values('count', ascending=False, kind='stable').drop_duplicates(['row', 'column'])
            cells = cells.merge(counts[['row', 'column', field]], on=['row', 'column'], how='left')
            cells[field] = cells[field].fillna('')
        cells = cells.loc[cells['samples'] >= max(1, int(min_samples))]
        if len(cells) <= 12_000 or effective >= 5_000:
            break
        effective *= 2
    cells['latitude'] = cells['row'] * latitude_step
    cells['longitude'] = cells['column'] * longitude_step
    cells['bad_share'] = (cells['bad_share'] * 100).round(1)
    cells['mean'] = cells['mean'].round(2)
    return cells.reset_index(drop=True), effective


def hotspots(cells: pd.DataFrame, limit: int = 25) -> list[dict[str, Any]]:
    """Rank grid cells by how many samples fall below the threshold."""
    if cells.empty:
        return []
    ranked = cells.assign(weight=cells['samples'] * cells['bad_share']).loc[cells['bad_share'] >= 50]
    ranked = ranked.sort_values(['weight', 'bad_share'], ascending=False).head(limit)
    return [
        {
            'latitude': round(float(row.latitude), 6), 'longitude': round(float(row.longitude), 6),
            'samples': int(row.samples), 'mean': float(row.mean), 'bad_share': float(row.bad_share),
            'city': str(row.city), 'region': str(row.region),
        }
        for row in ranked.itertuples()
    ]


def map_payload(
    cells: pd.DataFrame, classes: tuple[tuple[str, float, str], ...], title: str, unit: str,
    geometry: Any,
) -> dict[str, Any]:
    """Build a Canvas map model with one coloured series per quality class."""
    if cells.empty:
        return {'renderer': 'catalog-v2', 'width': 1600, 'height': 900, 'type': 'empty', 'title': title,
                'message': 'No located samples are available for this selection.'}
    series = []
    for index, (label, lower, colour) in enumerate(classes):
        upper = classes[index - 1][1] if index else None
        if math.isinf(lower):
            name = f'{label} (< {upper:g} {unit})'
        elif upper is None:
            name = f'{label} (≥ {lower:g} {unit})'
        else:
            name = f'{label} ({lower:g} to {upper:g} {unit})'
        mask = cells['mean'] >= lower
        if upper is not None:
            mask &= cells['mean'] < upper
        part = cells.loc[mask]
        series.append({'name': name, 'colour': colour, 'points': [
            [round(float(longitude), 6), round(float(latitude), 6)]
            for longitude, latitude in zip(part['longitude'], part['latitude'], strict=True)
        ]})
    lon_low, lon_high = float(cells['longitude'].min()), float(cells['longitude'].max())
    lat_low, lat_high = float(cells['latitude'].min()), float(cells['latitude'].max())
    lon_padding = max((lon_high - lon_low) * .06, .004)
    lat_padding = max((lat_high - lat_low) * .06, .004)
    zoom, tile_left, tile_top, tile_right, tile_bottom, top_left, bottom_right = geometry(
        lon_low - lon_padding, lon_high + lon_padding, lat_low - lat_padding, lat_high + lat_padding,
    )
    return {
        'renderer': 'catalog-v2', 'width': 1600, 'height': 900, 'type': 'map', 'title': title,
        'legend': {'position': 'right', 'line_markers': False, 'items': [
            {'label': item['name'], 'colour': item['colour']} for item in series
        ]},
        'label_position': 'None', 'label_format': {}, 'legend_format': {},
        'axis_ranges': {'x': [None, None], 'y': [None, None]},
        'x_label': 'Longitude', 'y_label': 'Latitude', 'axis_labels': False, 'point_radius': 6, 'point_shape': 'square',
        'domain': {'x': [lon_low, lon_high], 'y': [lat_low, lat_high]},
        'basemap': {
            'provider': 'OpenStreetMap', 'url_template': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            'attribution': '© OpenStreetMap contributors', 'zoom': zoom,
            'tile_range': [tile_left, tile_top, tile_right, tile_bottom],
            'world_bounds': [*top_left, *bottom_right], 'tile_size': 256,
        },
        'series': series,
    }


def observed_spectrum(samples: pd.DataFrame) -> list[dict[str, Any]]:
    """Share of samples served on each band, with the typical DL bandwidth."""
    rows = []
    for technology, band_column, bandwidth_column in (('LTE', 'lte_band', 'lte_bandwidth'), ('NR', 'nr_band', 'nr_bandwidth')):
        located = samples.loc[samples[band_column].astype(str) != '']
        for operator, part in located.groupby('operator', sort=False):
            total = len(part)
            for band, band_part in part.groupby(band_column, sort=False):
                bandwidths = band_part[bandwidth_column].dropna()
                rows.append({
                    'operator': operator, 'technology': technology, 'band': band,
                    'band_class': band_class(band),
                    'frequency_mhz': BAND_CATALOGUE.get(band, (None, ''))[0],
                    'duplex': BAND_CATALOGUE.get(band, (None, ''))[1],
                    'share': round(len(band_part) / total * 100, 1),
                    'samples': int(len(band_part)),
                    'typical_bandwidth_mhz': float(bandwidths.mode().iloc[0]) if len(bandwidths) else None,
                })
    order = {name: index for index, name in enumerate(BAND_CATALOGUE)}
    return sorted(rows, key=lambda row: (row['operator'], row['technology'], order.get(row['band'], 999)))


# Download tests carry DL in their name (FDTT HTTP DL MT, FDFS HTTPS DL ST); uploads, pings and browsing do not.
DOWNLOAD_TEST = re.compile(r'(?<![A-Za-z0-9])DL(?![A-Za-z0-9])', re.I)
# The primary downlink bandwidth of a test, LTE and NR together, in the classes of benchmark reports, widest first:
# (label, lower MHz, upper MHz, colour, block width). A block is as wide as its class midpoint.
BANDWIDTH_CLASSES = (
    ('200+ MHz', 200.0, None, '#1E6B3A', 225.0),
    ('140–199 MHz', 140.0, 200.0, '#3E9455', 169.5),
    ('100–139 MHz', 100.0, 140.0, '#8CC68A', 119.5),
    ('60–99 MHz', 60.0, 100.0, '#F2C66D', 79.5),
    ('40–59 MHz', 40.0, 60.0, '#EE9E4E', 49.5),
    ('25–39 MHz', 25.0, 40.0, '#E2685A', 32.0),
    ('Under 25 MHz', 0.0, 25.0, '#B5132B', 12.5),
)
NARROW_BANDWIDTH_MHZ = 25.0
# The share of tests with this primary bandwidth or more is labelled under each ladder.
WIDE_BANDWIDTH_MHZ = 100.0
# The title the primary bandwidth chart carries on the page and in the summaries: the CDRs report the bandwidth of the
# NR primary cell only, so it is not the total bandwidth of the test.
BANDWIDTH_LADDER_TITLE = 'Primary bandwidth of each test: LTE + NR'
BANDWIDTH_SCOPES = {'download': 'Download tests', 'all': 'All Data tests'}
ALL_ENVIRONMENTS = 'All environments'


def total_bandwidth(samples: pd.DataFrame) -> pd.Series:
    """The primary DL bandwidth of each test, LTE and NR together (MHz); NaN when the test reports neither.

    LTE is the mean bandwidth of the test over its aggregated carriers (else its PCell bandwidth) rounded up to 5 MHz,
    as the Reporting field LTE DL Aggregated BW (MHz); NR is the bandwidth of its NR PCell, since the CDRs do not
    report the bandwidth of the NR secondary carriers.
    """
    def positive(field: str) -> pd.Series:
        values = samples[field] if field in samples else pd.Series(math.nan, index=samples.index)
        return pd.to_numeric(values, errors='coerce').where(lambda series: series > 0)

    lte = positive('lte_aggregated_bandwidth')
    lte = np.ceil(lte.where(lte.notna(), positive('lte_bandwidth')) / 5) * 5
    nr = positive('nr_bandwidth')
    return (lte.fillna(0) + nr.fillna(0)).where(lte.notna() | nr.notna())


def bandwidth_classes(totals: pd.Series) -> pd.Series:
    """The position in :data:`BANDWIDTH_CLASSES` of each known primary bandwidth."""
    values = totals.dropna().to_numpy(dtype=float)
    positions = np.full(len(values), len(BANDWIDTH_CLASSES) - 1)
    for index in range(len(BANDWIDTH_CLASSES) - 2, -1, -1):
        positions[values >= BANDWIDTH_CLASSES[index][1]] = index
    return pd.Series(positions, index=totals.dropna().index)


def bandwidth_ladders(samples: pd.DataFrame, columns: pd.Series, column_order: list[str]) -> dict[str, Any]:
    """The share of tests in each total-bandwidth class per group (column) and environment (row).

    Tests without an environment are left out when some tests have one; without any, every test is one row.
    """
    totals = total_bandwidth(samples)
    environments = samples['environment'].fillna('').astype(str) if 'environment' in samples else pd.Series('', index=samples.index)
    rows = sorted({value for value in environments if value}, key=environment_order)
    without_environment = int((environments == '').sum()) if rows else 0
    if not rows:
        rows, environments = [ALL_ENVIRONMENTS], pd.Series(ALL_ENVIRONMENTS, index=samples.index)
    positions = bandwidth_classes(totals)
    cells = []
    for column in column_order:
        in_column = columns == column
        for row in rows:
            part = totals.loc[in_column & (environments == row)]
            if not len(part):
                continue
            known = part.dropna()
            counts = np.bincount(positions.loc[known.index].to_numpy(dtype=int), minlength=len(BANDWIDTH_CLASSES))
            cells.append({
                'column': column, 'environment': row, 'tests': int(len(part)), 'known': int(len(known)),
                'counts': [int(count) for count in counts],
                'shares': [round(int(count) / len(known) * 100, 1) if len(known) else 0.0 for count in counts],
                'narrow_share': round(float((known < NARROW_BANDWIDTH_MHZ).mean()) * 100, 1) if len(known) else None,
                'wide_share': round(float((known >= WIDE_BANDWIDTH_MHZ).mean()) * 100, 1) if len(known) else None,
                'median_mhz': round(float(known.median()), 1) if len(known) else None,
            })
    # The group with the largest share under 25 MHz in each environment, when there are groups to compare.
    highlights = []
    for row in rows:
        known = [cell for cell in cells if cell['environment'] == row and cell['known']]
        if len(known) > 1:
            worst = max(known, key=lambda cell: cell['narrow_share'])
            highlights.append({'environment': row, 'column': worst['column'], 'narrow_share': worst['narrow_share']})
    return {
        'columns': [column for column in column_order if any(cell['column'] == column for cell in cells)],
        'environments': rows, 'cells': cells, 'tests': int(len(samples)), 'unknown': int(totals.loc[environments.isin(rows)].isna().sum()),
        'without_environment': without_environment, 'highlights': highlights,
    }


# A test failed when its result is not completed, and was slow at this speed (Mbit/s) or less.
SLOW_DOWNLOAD_MBPS = 5.0
# Per location: the places with the most download tests, each with enough tests in some group.
MAX_STRIP_LOCATIONS = 25
MIN_STRIP_TESTS = 15
# The ladders per kind of serving site or RAN Vendor keep the combinations with enough tests of a known bandwidth.
MIN_SPLIT_LADDER_TESTS = 20
MAX_SPLIT_LADDER_COLUMNS = 12


def failed_tests(samples: pd.DataFrame) -> pd.Series:
    """Whether each CDR Data test failed (its result is known and not completed)."""
    results = samples['test_result'].fillna('').astype(str) if 'test_result' in samples else pd.Series('', index=samples.index)
    return (results != '') & ~results.str.casefold().str.contains('complet')


def split_columns(samples: pd.DataFrame, columns: pd.Series, column_order: list[str], field: str) -> tuple[pd.Series, list[str]]:
    """The groups of the ladders split by a field of the serving cell (the kind of site or the RAN Vendor): each group and
    value with enough tests of a known bandwidth, the groups in their order and their values by tests."""
    values = samples[field].fillna('').astype(str) if field in samples else pd.Series('', index=samples.index)
    known = total_bandwidth(samples).notna() & (values != '') & ~values.str.casefold().isin({'unknown', 'n/a'})
    combined = (columns.loc[samples.index].astype(str) + ' · ' + values).where(known, '')
    counts = combined[combined != ''].value_counts()
    kept = [name for name, count in counts.items() if count >= MIN_SPLIT_LADDER_TESTS]
    position = {column: index for index, column in enumerate(column_order)}
    order = sorted(kept, key=lambda name: (position.get(name.rsplit(' · ', 1)[0], 999), -int(counts[name]), name))
    return combined, order[:MAX_SPLIT_LADDER_COLUMNS]


def location_strips(tests: pd.DataFrame, columns: pd.Series, column_order: list[str]) -> dict[str, Any]:
    """The download tests of every City (the most measured ones) per group: the share of tests under 25 MHz in total
    (of those with a known bandwidth) and the share that failed or reached 5 Mbit/s or less."""
    cities = tests['city'].fillna('').astype(str) if 'city' in tests else pd.Series('', index=tests.index)
    if cities.eq('').all() or tests.empty:
        return {'cities': [], 'rows': []}
    totals = total_bandwidth(tests)
    failed = failed_tests(tests)
    rates = pd.to_numeric(tests['mean_data_rate'], errors='coerce') if 'mean_data_rate' in tests else pd.Series(math.nan, index=tests.index)
    slow = failed | (rates <= SLOW_DOWNLOAD_MBPS)
    judged = failed | rates.notna()
    group_of = columns.loc[tests.index].astype(str)
    frame = pd.DataFrame({'city': cities, 'group': group_of, 'narrow': (totals < NARROW_BANDWIDTH_MHZ).where(totals.notna()),
                          'slow': slow.where(judged)})
    frame = frame[frame['city'] != '']
    order = frame['city'].value_counts()
    leading = frame.groupby(['city', 'group']).size().groupby('city').max()
    shown = [city for city in order.index if leading.get(city, 0) >= MIN_STRIP_TESTS][:MAX_STRIP_LOCATIONS]
    rows = []
    for column in column_order:
        part = frame[(frame['group'] == column) & frame['city'].isin(shown)]
        if part.empty:
            continue
        cells = {}
        for city, group in part.groupby('city'):
            narrow, slowed = group['narrow'].dropna(), group['slow'].dropna()
            cells[city] = {'tests': int(len(group)),
                           'narrow_share': round(float(narrow.mean()) * 100, 1) if len(narrow) else None,
                           'slow_share': round(float(slowed.mean()) * 100, 1) if len(slowed) else None,
                           'known': int(len(narrow)), 'judged': int(len(slowed))}
        rows.append({'column': column, 'cells': cells})
    return {'cities': shown, 'rows': rows, 'min_tests': MIN_STRIP_TESTS, 'slow_mbps': SLOW_DOWNLOAD_MBPS,
            'narrow_below_mhz': NARROW_BANDWIDTH_MHZ}


INTERACTIVITY_MEASURES = (
    ('failed', 'Failed tests, %', False), ('rtt_median', 'Round trip, median (ms)', False),
    ('rtt_p90', 'Round trip, slowest tenth P90 (ms)', False), ('loss_share', 'Tests with packet loss, %', False),
    ('jitter', 'Jitter, median (ms)', False),
)


def interactivity_detail(samples: pd.DataFrame, columns: pd.Series, column_order: list[str]) -> dict[str, Any]:
    """The gaming and video chat (interactivity) tests of each group in every environment and in all of them: their
    failures, round trip (median and slowest tenth of the per-test medians), the share with packet loss and the median
    jitter, each ranked among the groups of the environment (1 is the best: lowest)."""
    kinds = samples['type_of_test'].fillna('').astype(str).str.casefold() if 'type_of_test' in samples else pd.Series('', index=samples.index)
    tests = samples.loc[samples['kind'].eq('Data') & kinds.str.contains('interactiv')]
    if tests.empty:
        return {'measures': [], 'environments': [], 'cells': []}
    named = tests['environment'].fillna('').astype(str)
    known = sorted((value for value in pd.unique(named) if value), key=environment_order)
    # Each environment, then every test (also those without an environment) unless a single environment holds them all.
    scopes = [(environment, named == environment) for environment in known]
    if len(known) != 1 or named.eq('').any():
        scopes.append((ALL_ENVIRONMENTS, pd.Series(True, index=tests.index)))
    rows = [environment for environment, _mask in scopes]
    failed = failed_tests(tests)
    cells = []
    for environment, mask in scopes:
        values: dict[str, dict[str, float | None]] = {}
        for column in column_order:
            part = tests.loc[(columns.loc[tests.index] == column) & mask]
            if part.empty:
                continue
            passed = part.loc[~failed.loc[part.index]]
            rtt = pd.to_numeric(passed['rtt_median'], errors='coerce').dropna()
            lost = pd.to_numeric(passed['packets_lost'], errors='coerce')
            jitter = pd.to_numeric(passed['jitter'], errors='coerce').dropna()
            values[column] = {
                'tests': int(len(part)),
                'failed': round(float(failed.loc[part.index].mean()) * 100, 1),
                'rtt_median': round(float(rtt.median()), 1) if len(rtt) else None,
                'rtt_p90': round(float(rtt.quantile(.9)), 1) if len(rtt) else None,
                'loss_share': round(float((lost.dropna() > 0).mean()) * 100, 1) if lost.notna().any() else None,
                'jitter': round(float(jitter.median()), 1) if len(jitter) else None,
            }
        for key, _label, _higher in INTERACTIVITY_MEASURES:
            known = {column: entry[key] for column, entry in values.items() if entry[key] is not None}
            for column, value in known.items():
                values[column][f'{key}_rank'] = 1 + sum(1 for other in known.values() if other < value - 1e-9)
                values[column][f'{key}_of'] = len(known)
        cells.extend({'column': column, 'environment': environment, **entry} for column, entry in values.items())
    return {'measures': [{'key': key, 'label': label} for key, label, _higher in INTERACTIVITY_MEASURES],
            'environments': rows, 'columns': [column for column in column_order if any(cell['column'] == column for cell in cells)],
            'cells': cells}


def nr_band_quality(samples: pd.DataFrame, columns: pd.Series, column_order: list[str]) -> list[dict[str, Any]]:
    """The NR samples of each group per NR band (carrier): their share of the group, median RSRP and SINR and the
    share in each RSRP and SINR class, so the carriers that reach a lower quality stand out."""
    bands = samples['nr_band'].fillna('').astype(str) if 'nr_band' in samples else pd.Series('', index=samples.index)
    measured = samples.loc[(bands != '') & (samples['nr_rsrp'].notna() | samples['nr_sinr'].notna())]
    rows = []
    for column in column_order:
        group = measured.loc[columns.loc[measured.index] == column]
        if group.empty:
            continue
        for band, part in group.groupby(bands.loc[group.index], sort=False):
            rsrp, sinr = part['nr_rsrp'].dropna(), part['nr_sinr'].dropna()
            rows.append({
                'column': column, 'band': band, 'samples': int(len(part)), 'share': round(len(part) / len(group) * 100, 1),
                'rsrp_median': _quantile(rsrp, .5), 'sinr_median': _quantile(sinr, .5),
                'rsrp_classes': class_distribution(rsrp, RSRP_CLASSES), 'sinr_classes': class_distribution(sinr, SINR_CLASSES),
            })
    position = {column: index for index, column in enumerate(column_order)}
    return sorted(rows, key=lambda row: (position.get(row['column'], 999), -row['samples']))


# Bandwidth per band shows a bandwidth column only where it holds a real share of a band: a column with no samples, or
# with under this share of the known samples of every band, is left out (its samples go to Other), unless it is the
# only bandwidth of a band.
LOW_BANDWIDTH_SHARE = 3.0


def shown_bandwidths(bands: list[dict[str, Any]]) -> list[str]:
    """The bandwidth columns of Bandwidth per band, narrowest first (see ``LOW_BANDWIDTH_SHARE``)."""
    shown = set()
    for row in bands:
        counts = {width: count for width, count in (row.get('bandwidths') or {}).items() if count}
        known = sum(counts.values())
        for width, count in counts.items():
            if len(counts) == 1 or count / known * 100 >= LOW_BANDWIDTH_SHARE:
                shown.add(width)
    return sorted(shown, key=float)


def band_bandwidths(samples: pd.DataFrame) -> list[dict[str, Any]]:
    """The samples of each serving band per DL bandwidth of its primary carrier (LTE PCell or NR PCell)."""
    rows = []
    for technology, band_column, bandwidth_column in (('LTE', 'lte_band', 'lte_bandwidth'), ('NR', 'nr_band', 'nr_bandwidth')):
        located = samples.loc[samples[band_column].astype(str) != '']
        for (operator, band), part in located.groupby(['operator', band_column], sort=False):
            widths = pd.to_numeric(part[bandwidth_column], errors='coerce')
            widths = widths.where(widths > 0).dropna().round(1)
            counts = widths.value_counts().sort_index()
            rows.append({
                'operator': operator, 'technology': technology, 'band': band,
                'duplex': BAND_CATALOGUE.get(band, (None, ''))[1], 'frequency_mhz': BAND_CATALOGUE.get(band, (None, ''))[0],
                'samples': int(len(part)), 'unknown': int(len(part) - len(widths)),
                'bandwidths': {f'{width:g}': int(count) for width, count in counts.items()},
                'typical_bandwidth_mhz': float(widths.mode().iloc[0]) if len(widths) else None,
            })
    return rows


def normalise_spectrum_holdings(rows: Iterable[Any]) -> list[dict[str, Any]]:
    """Validate licensed spectrum rows (Operator, band, duplex, class, MHz)."""
    result = []
    for index, row in enumerate(rows or [], start=1):
        if not isinstance(row, dict):
            raise ValueError(f'Spectrum holding {index} is invalid.')
        operator = str(row.get('operator') or '').strip()
        band = str(row.get('band') or '').strip()
        if not operator or not band:
            raise ValueError(f'Spectrum holding {index} needs an Operator and a band.')
        duplex = str(row.get('duplex') or BAND_CATALOGUE.get(band, (0, 'FDD'))[1] or 'FDD').strip().upper()
        if duplex not in SPECTRUM_DUPLEX_VALUES:
            raise ValueError(f'Spectrum holding {index} has an unsupported duplex mode "{duplex}".')
        klass = str(row.get('band_class') or band_class(band) or '').strip()
        klass = next((item for item in BAND_CLASSES if item.casefold() == klass.casefold()), '')
        if not klass:
            raise ValueError(f'Spectrum holding {index} needs a band class: Low, Mid or High (TDD).')
        try:
            bandwidth = float(str(row.get('bandwidth_mhz')).strip())
        except (TypeError, ValueError):
            raise ValueError(f'Spectrum holding {index} needs a bandwidth in MHz.') from None
        if not math.isfinite(bandwidth) or bandwidth <= 0:
            raise ValueError(f'Spectrum holding {index} needs a positive bandwidth in MHz.')
        result.append({
            'operator': operator, 'band': band, 'duplex': duplex, 'band_class': klass,
            'bandwidth_mhz': round(bandwidth, 3), 'notes': str(row.get('notes') or '').strip(),
        })
    return result


SPECTRUM_CSV_HEADER = ('Operator', 'Band', 'Duplex', 'Band Class', 'Bandwidth MHz', 'Notes')


def parse_spectrum_csv(text: str) -> list[dict[str, Any]]:
    """Read ``Operator,Band,Duplex,Band Class,Bandwidth MHz,Notes`` rows.

    Comma, semicolon and tab separators are accepted, so rows pasted from a
    spreadsheet work as well.
    """
    import csv
    from io import StringIO

    text = str(text or '').strip()
    if not text:
        return []
    header = text.splitlines()[0]
    delimiter = '\t' if '\t' in header else ';' if header.count(';') > header.count(',') else ','
    reader = csv.DictReader(StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError('Paste a CSV with an Operator,Band,Duplex,Band Class,Bandwidth MHz,Notes header.')
    columns = {column_identity(name): name for name in reader.fieldnames}

    def value(row: dict[str, Any], *names: str) -> str:
        return next((str(row.get(columns[column_identity(name)]) or '') for name in names if column_identity(name) in columns), '')

    return normalise_spectrum_holdings([
        {
            'operator': value(row, 'Operator'), 'band': value(row, 'Band'), 'duplex': value(row, 'Duplex'),
            'band_class': value(row, 'Band Class', 'Class'),
            'bandwidth_mhz': value(row, 'Bandwidth MHz', 'Bandwidth', 'MHz'), 'notes': value(row, 'Notes'),
        }
        for row in reader if any(str(item or '').strip() for item in row.values())
    ])


def spectrum_holdings_csv(holdings: list[dict[str, Any]]) -> str:
    """Write holdings with the header accepted by :func:`parse_spectrum_csv`."""
    import csv
    from io import StringIO

    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(SPECTRUM_CSV_HEADER)
    for row in holdings:
        writer.writerow([row['operator'], row['band'], row['duplex'], row['band_class'], f"{row['bandwidth_mhz']:g}", row.get('notes', '')])
    return buffer.getvalue()


def licensed_spectrum_summary(holdings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate licensed MHz per Operator and band class."""
    totals: dict[str, dict[str, float]] = {}
    for row in holdings:
        operator_totals = totals.setdefault(row['operator'], dict.fromkeys(BAND_CLASSES, 0.0))
        operator_totals[row['band_class']] = operator_totals.get(row['band_class'], 0.0) + float(row['bandwidth_mhz'])
    return [
        {'operator': operator, **{klass: round(values.get(klass, 0.0), 3) for klass in BAND_CLASSES},
         'total': round(sum(values.values()), 3)}
        for operator, values in totals.items()
    ]


# Cell inventories arrive as Vendor mapping datasets; their columns differ by
# operator and sheet, so each logical field lists the accepted headers.
INVENTORY_FIELDS = {
    'site': ('Site_ID', 'Site ID', 'eNBId', 'eNodeB ID', 'MBNL_ID'),
    'cell': ('CId___ECI', 'CELL_NAME', 'Cell Name', 'cellId', 'Cell ID', 'Cid__ECI', 'GCID', 'ECI', 'Cell_ID', 'Global CI'),
    'scenario': ('eMOCNScenario',),
    'network': ('Network',),
    'host_network': ('Host Network',),
    'vendor': ('OP_Vendor', 'OP/ Vendor', 'Vendor'),
    'region': ('Region', 'UK "Regional"'),
    'subregion': ('Subregion',),
    'cluster': ('Cluster', 'Cluster Name', 'Engineering Polygon', 'Regional Optimisation Polygon'),
    'site_type': ('Site_Type', 'Site Type'),
    'band': ('Band', 'Frequency Band'),
}
# The grouped Network Deployment views of the PowerPoint and Word summaries (from the inventory snapshot).
SUMMARY_DEPLOYMENT_GROUPS = ('host_network', 'vendor', 'technology', 'band', 'emocn', 'site_type', 'region', 'subregion', 'cluster', 'status')
DEPLOYMENT_GROUPINGS = {
    'scenario': 'eMOCN Scenario', 'host_network': 'Host Network', 'network': 'Network', 'vendor': 'RAN Vendor',
    'region': 'Region', 'subregion': 'Subregion', 'cluster': 'Cluster', 'site_type': 'Site Type', 'band': 'Band',
}
# How the NR sites by duplex mode of the inventory snapshot can be split ('' counts them per owner network only).
NR_DUPLEX_SPLITS = {'': 'Owner network', 'region': 'Region', 'cluster': 'Cluster', 'city': 'City', 'vendor': 'RAN Vendor',
                    'host_network': 'Host Network'}


# ---------------------------------------------------------------------------
# Inventory (Vendor mapping datasets)
# ---------------------------------------------------------------------------
INVENTORY_DATASET_KINDS = {'mapping_vodafone': 'Vodafone', 'mapping_three': 'Three'}


INVENTORY_KEY_COLUMNS = ('Operator', 'Operator_Vendor', 'Vendor', 'Region', 'Cluster', 'City', 'Technology')
# Source vendor of an inventory, and the vendor alone stored by earlier versions.
INVENTORY_DETAIL_ALIASES = {
    'Operator': ('Operator',),
    'Source_Vendor': ('Vendor', 'OP_Vendor', 'OP/ Vendor'),
    'Vendor_Only': ('Vendor_Only',),
    'Region': ('Region', 'UK "Regional"'),
    'City': ('City', 'Beacon2Town', 'Town', 'Major Town and Cities v3/BUA'),
    'Technology': ('Technology', 'RAT', 'Source_Sheet'),
    'Cluster': ('Cluster', 'Cluster Name', 'Engineering Polygon', 'Regional Optimisation Polygon'),
}


INVENTORY_COORDINATES = {
    'longitude': ('Longitude', 'Long', 'Lon', 'Site Longitude', 'Site_Longitude'),
    'latitude': ('Latitude', 'Lat', 'Site Latitude', 'Site_Latitude'),
    'easting': ('Easting', 'Site Easting', 'Site_Easting'),
    'northing': ('Northing', 'Site Northing', 'Site_Northing'),
}


def inventory_polygon_sources(repository) -> tuple:
    """Identify ready boundary inputs and their revisions for spatial cache invalidation."""
    sources = []
    for row in repository.list_datasets():
        if row['status'] == 'ready' and row['dataset_kind'] in {'regions', 'clusters'}:
            path = Path(str(row['stored_path']))
            sources.append((row['dataset_kind'], int(row['id']), str(row['updated_at'] or ''),
                            str(path), path.stat().st_mtime_ns))
    return tuple(sorted(sources, key=lambda item: item[1], reverse=True))


@lru_cache(maxsize=4)
def inventory_polygon_lookup(sources: tuple):
    """Index imported polygons in WGS84; newest uploads take precedence on overlaps."""
    from src.modules.geospatial import _column, _read_region_mapping, _region_field
    from shapely import STRtree

    lookups = {}
    for dimension, kind in [('Region', 'regions'), ('Cluster', 'clusters')]:
        geometries, names = [], []
        for source_kind, _identifier, _revision, path, _mtime in sources:
            if source_kind != kind:
                continue
            boundaries = _read_region_mapping(Path(path), dimension).to_crs('EPSG:4326')
            field = _region_field(boundaries.columns) if dimension == 'Region' else next(
                found for candidate in ('Cluster', 'Cluster_ID', 'Cluster_Name', 'ClusterName', 'Name')
                if (found := _column(boundaries.columns, candidate)))
            for geometry, name in zip(boundaries.geometry, boundaries[field]):
                if geometry is not None and not geometry.is_empty:
                    geometries.append(geometry)
                    names.append(str(name).strip())
        if geometries:
            lookups[dimension] = (STRtree(geometries), names)
    return lookups


def register_inventory_polygon_mapping(repository, connection) -> None:
    """Resolve inventory coordinates to imported boundary names without changing source rows."""
    sources = inventory_polygon_sources(repository)
    lookups = inventory_polygon_lookup(sources) if sources else {}
    projected_to_wgs84 = None

    @lru_cache(maxsize=65536)
    def mapped_name(dimension, longitude, latitude, easting, northing, original):
        nonlocal projected_to_wgs84
        if dimension not in lookups:
            return original

        def numeric(value):
            try:
                result = float(str(value).strip().replace(',', '.'))
                return result if math.isfinite(result) else None
            except (TypeError, ValueError):
                return None

        lon, lat = numeric(longitude), numeric(latitude)
        if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            east, north = numeric(easting), numeric(northing)
            if east is None or north is None:
                return ''
            if projected_to_wgs84 is None:
                from pyproj import Transformer
                projected_to_wgs84 = Transformer.from_crs('EPSG:27700', 'EPSG:4326', always_xy=True)
            lon, lat = projected_to_wgs84.transform(east, north)
        from shapely.geometry import Point
        tree, names = lookups[dimension]
        matches = tree.query(Point(lon, lat), predicate='intersects')
        return names[min(matches)] if len(matches) else ''

    connection.create_function('inventory_polygon_name', 6, mapped_name, deterministic=True)


def inventory_coordinate_expressions(columns, quote) -> list[str]:
    lookup = {column_identity(column): column for column in columns}
    values = []
    for aliases in INVENTORY_COORDINATES.values():
        fields = list(dict.fromkeys(lookup[column_identity(alias)] for alias in aliases if column_identity(alias) in lookup))
        parts = [f"NULLIF(TRIM(CAST({quote(field)} AS TEXT)), '')" for field in fields]
        values.append(f"COALESCE({', '.join(parts)}, '')" if parts else "''")
    return values


OPERATOR_FAMILIES = (
    {'vf', 'vodafone', 'vodafoneuk'}, {'3', 'three', 'threeuk', 'h3g', 'h3guk'},
    {'o2', 'o2uk', 'telefonica'}, {'ee', 'everythingeverywhere'},
)


def operator_family(name: object) -> str:
    """One identity for every spelling of the same operator (Vodafone, VF, Vodafone UK...)."""
    identity = re.sub(r'[^a-z0-9]+', '', str(name or '').casefold())
    return next((f'family{index}' for index, family in enumerate(OPERATOR_FAMILIES) if identity in family), identity)


SAMPLE_FILTERS = (
    ('operator', 'operators'), ('operator_vendor', 'operator_vendors'), ('vendor_operator', 'vendor_operators'),
    ('vendor', 'vendors'), ('region', 'regions'),
    ('cluster', 'clusters'), ('city', 'cities'), ('environment', 'environments'), ('campaign', 'campaigns'),
)


def filter_samples(samples: pd.DataFrame, request: Any) -> pd.DataFrame:
    """Samples matching the Common Selection filters."""
    filtered = samples
    operators = samples['operator'].dropna().unique() if 'operator' in samples else []
    for field, key in SAMPLE_FILTERS:
        values = list(getattr(request, key, None) or [])
        if field == 'vendor':
            values = vendor_filter_values(values, operators)
        elif field in {'operator_vendor', 'vendor_operator'}:
            values = operator_vendor_filter_values(values, operators)
        # Patterns (VF*) take every value they match (see value_patterns).
        wanted = ValueSet(values)
        if wanted and field in filtered:
            filtered = filtered.loc[wanted.mask(filtered[field])]
    return filtered


def inventory_filter_normalizer(repository):
    """Comparable form of an inventory filter value: mapped Operator and Vendor, casefolded."""
    from src.modules.column_names import vendor_filter_value

    mappings = repository.chart_mapping_settings()
    operator_maps = {str(key).casefold(): str(value) for key, value in mappings.get('operator_mappings', {}).items()}
    vendor_maps = {str(key).casefold(): str(value) for key, value in mappings.get('vendor_mappings', {}).items()}
    operator_names = [*operator_maps, *operator_maps.values(), 'Vodafone', 'Vodafone UK', 'VFUK', 'VF', 'Three', '3UK', '3']

    @lru_cache(maxsize=4096)
    def filter_value(value, field):
        text = str(value or '').strip()
        if field == 'Operator':
            text = operator_maps.get(text.casefold(), text)
        elif field == 'Vendor':
            text = vendor_filter_value(text, operator_names)
            text = vendor_maps.get(text.casefold(), text)
        elif field == 'Operator_Vendor':
            # CDRs write Vodafone_Ericsson and inventories Vodafone UK_Ericsson:
            # compare the operator family and the mapped vendor.
            all_vendors = re.search(r'\s+- All(?: Vendors)?$', text, flags=re.IGNORECASE)
            base = re.sub(r'\s+- All(?: Vendors)?$', '', text, flags=re.IGNORECASE)
            prefix, _separator, vendor = base.partition('_')
            vendor = '' if all_vendors else vendor_maps.get(vendor.strip().casefold(), vendor.strip())
            return f"{operator_family(operator_maps.get(prefix.strip().casefold(), prefix))}|{vendor.casefold()}"
        return text.casefold()

    return filter_value


def prepare_inventory_query(repository, connection, datasets: list[dict[str, Any]], selection: dict[str, Any],
                            apply_filters: bool = True):
    """Align complete inventories without changing stored source fields or row multiplicity.

    Without ``apply_filters`` the query returns every row of every inventory.
    """
    from functools import lru_cache
    from src.modules.column_names import vendor_filter_value

    quote = repository._quote_identifier
    mappings = repository.chart_mapping_settings()
    operator_maps = {str(key).casefold(): str(value) for key, value in mappings.get('operator_mappings', {}).items()}
    vendor_maps = {str(key).casefold(): str(value) for key, value in mappings.get('vendor_mappings', {}).items()}
    operator_names = [*operator_maps, *operator_maps.values(), 'Vodafone', 'Vodafone UK', 'VFUK', 'VF', 'Three', '3UK', '3']

    @lru_cache(maxsize=1024)
    def operator_value(value, fallback):
        text = str(value or fallback).strip()
        return operator_maps.get(text.casefold(), text)

    @lru_cache(maxsize=1024)
    def vendor_value(raw, only, operator):
        text = str(raw or '').strip()
        vendor = vendor_filter_value(text, operator_names) or str(only or '').strip()
        if not vendor:
            return ''
        return f'{operator}_{vendor}'

    @lru_cache(maxsize=1024)
    def vendor_only_value(raw, only):
        return str(only or '').strip() or vendor_filter_value(raw, operator_names)

    @lru_cache(maxsize=1024)
    def technology_value(value):
        text = str(value or '').strip()
        return {'4g': 'LTE', 'lte': 'LTE', '5g': 'NR', 'nr': 'NR'}.get(text.casefold(), text)

    filter_value = inventory_filter_normalizer(repository)

    @lru_cache(maxsize=4096)
    def cell_value(value):
        text = str(value or '').strip()
        if re.fullmatch(r'\d+(?:\.0+)?', text):
            return str(int(text.split('.')[0]))
        if re.fullmatch(r'0x[0-9a-f]+', text, re.I):
            return str(int(text, 16))
        return text

    connection.create_function('inventory_cell', 1, cell_value, deterministic=True)
    connection.create_function('inventory_operator', 2, operator_value, deterministic=True)
    connection.create_function('inventory_vendor', 3, vendor_value, deterministic=True)
    connection.create_function('inventory_vendor_only', 2, vendor_only_value, deterministic=True)
    connection.create_function('inventory_technology', 1, technology_value, deterministic=True)
    connection.create_function('inventory_filter', 2, filter_value, deterministic=True)
    register_inventory_polygon_mapping(repository, connection)
    schemas = {row['id']: repository.list_dataset_row_columns(row['id']) for row in datasets}
    source_columns = list(dict.fromkeys(column for row in datasets for column in schemas[row['id']]))
    columns = [*INVENTORY_KEY_COLUMNS, 'Source_Dataset_ID', 'Source_Dataset_Name']
    source_names = {}
    used = {column.casefold() for column in columns} | {'__inventory_cell_id', '__inventory_source_row'}
    for source in source_columns:
        name = f'Source_{source}' if column_identity(source) in {column_identity(key) for key in INVENTORY_KEY_COLUMNS} else source
        while name.casefold() in used:
            name = f'Source_{name}'
        source_names[source] = name
        used.add(name.casefold())
        columns.append(name)

    selects = []
    for dataset in datasets:
        available = schemas[dataset['id']]
        lookup = {column_identity(column): column for column in available}

        def expression(aliases):
            fields = list(dict.fromkeys(lookup[column_identity(alias)] for alias in aliases if column_identity(alias) in lookup))
            if not fields:
                return "''"
            parts = [f"NULLIF(TRIM(CAST({quote(field)} AS TEXT)), '')" for field in fields]
            return f"COALESCE({', '.join(parts)}, '')"

        fallback = str(dataset['operator']).replace("'", "''")
        operator = f"inventory_operator({expression(INVENTORY_DETAIL_ALIASES['Operator'])}, '{fallback}')"
        raw_vendor = expression(INVENTORY_DETAIL_ALIASES['Source_Vendor'])
        only = expression(INVENTORY_DETAIL_ALIASES['Vendor_Only'])
        normalized = {
            'Operator': operator,
            'Operator_Vendor': f'inventory_vendor({raw_vendor}, {only}, {operator})',
            'Vendor': f'inventory_vendor_only({raw_vendor}, {only})',
            'Region': expression(INVENTORY_DETAIL_ALIASES['Region']),
            'City': expression(INVENTORY_DETAIL_ALIASES['City']),
            'Technology': f"COALESCE(NULLIF(inventory_technology({expression(('Technology', 'RAT'))}), ''), CASE LOWER({expression(('Source_Sheet',))}) WHEN '4g' THEN 'LTE' WHEN '5g' THEN 'NR' ELSE '' END)",
            'Cluster': expression(INVENTORY_DETAIL_ALIASES['Cluster']),
        }
        coordinates = ', '.join(inventory_coordinate_expressions(available, quote))
        for dimension in ('Region', 'Cluster'):
            normalized[dimension] = f"inventory_polygon_name('{dimension}', {coordinates}, {normalized[dimension]})"
        # Three's ECI mapping format identifies LTE cells even without a Technology header.
        if dataset['kind'] == 'mapping_three' and any(column_identity(col) in {'cideci', 'eci'} for col in available):
            normalized['Technology'] = f"COALESCE(NULLIF({normalized['Technology']}, ''), 'LTE')"
        cell = expression(('GCID', 'CId___ECI', 'Cid__ECI', 'ECI', 'Cell_ID', 'Global CI'))
        if cell == "''":
            # The Cell ID the cell broadcasts, or the Local Cell ID without it (see cell_identity).
            local = expression(('Cell ID', 'cellId', 'Local Cell ID'))
            enodeb = expression(('eNodeB ID', 'eNBId'))
            gnodeb = expression(('gNodeB ID',))
            cell = f"CASE WHEN {local} = '' THEN NULL WHEN {normalized['Technology']} = 'NR' AND {gnodeb} != '' THEN CAST({gnodeb} AS INTEGER) * {1 << nr_cell_bits()} + CAST({local} AS INTEGER) WHEN {normalized['Technology']} = 'LTE' AND {enodeb} != '' THEN CAST({enodeb} AS INTEGER) * 256 + CAST({local} AS INTEGER) END"
        values = [f'{value} AS {quote(field)}' for field, value in normalized.items()]
        values.extend([f'inventory_cell({cell}) AS __Inventory_Cell_ID', 'rowid AS __Inventory_Source_Row'])
        filename = str(dataset['file_name']).replace("'", "''")
        values.extend([f"{int(dataset['id'])} AS Source_Dataset_ID", f"'{filename}' AS Source_Dataset_Name"])
        values.extend(f"{quote(source) if source in available else 'NULL'} AS {quote(source_names[source])}" for source in source_columns)
        selects.append(f"SELECT {', '.join(values)} FROM {quote(repository.dataset_rows_table_name(dataset['id']))}")
    if not selects:
        return '', [], columns
    if not apply_filters:
        return 'SELECT * FROM (' + ' UNION ALL '.join(selects) + ')', [], columns
    predicates, parameters = [], []
    for field, key in [('Operator', 'operators'), ('Operator_Vendor', 'operator_vendors'), ('Vendor', 'vendors'),
                       ('Region', 'regions'), ('Cluster', 'clusters'), ('City', 'cities')]:
        values = list(dict.fromkeys(filter_value(value, field) for value in selection.get(key, []) if str(value).strip()))
        if values:
            predicates.append(f"inventory_filter({quote(field)}, '{field}') IN ({', '.join('?' for _ in values)})")
            parameters.extend(values)
    technology = selection.get('technology', 'lte')
    technologies = ['LTE', 'NR'] if technology == 'lte_nr' else ['NR'] if technology == 'nr' else ['LTE']
    predicates.append(f"Technology IN ({', '.join('?' for _ in technologies)})")
    parameters.extend(technologies)
    query = 'SELECT * FROM (' + ' UNION ALL '.join(selects) + ')'
    if predicates:
        query += ' WHERE ' + ' AND '.join(predicates)
    return query, parameters, columns


def inventory_expression(columns: Iterable[str], field: str, quote) -> str | None:
    """SQL expression returning the first non-empty inventory column value."""
    lookup = {column_identity(column): column for column in columns}
    present = [lookup[column_identity(alias)] for alias in INVENTORY_FIELDS[field] if column_identity(alias) in lookup]
    if not present:
        return None
    parts = [f"NULLIF(TRIM(CAST({quote(column)} AS TEXT)), '')" for column in dict.fromkeys(present)]
    return parts[0] if len(parts) == 1 else f"COALESCE({', '.join(parts)})"


def inventory_projection(task_repository: Any, dataset: dict[str, Any]) -> pd.DataFrame:
    """Read only distinct identifiers and grouping fields from an inventory."""
    dataset_id = int(dataset['id'])
    columns = task_repository.list_dataset_row_columns(dataset_id)
    quote = task_repository._quote_identifier
    expressions = {field: inventory_expression(columns, field, quote) for field in INVENTORY_FIELDS}
    if not expressions['site']:
        return pd.DataFrame()
    coordinates = ', '.join(inventory_coordinate_expressions(columns, quote))
    polygon_kinds = {source[0] for source in inventory_polygon_sources(task_repository)}
    for field, dimension in [('region', 'Region'), ('cluster', 'Cluster')]:
        if not expressions[field] and ('regions' if field == 'region' else 'clusters') not in polygon_kinds:
            continue
        original = expressions[field] or "''"
        expressions[field] = f"inventory_polygon_name('{dimension}', {coordinates}, {original})"
    selected = ', '.join(f'{expression} AS {quote(field)}'
                         for field, expression in expressions.items() if expression)
    table = quote(task_repository.dataset_rows_table_name(dataset_id))
    with task_repository.connection() as connection:
        register_inventory_polygon_mapping(task_repository, connection)
        return pd.read_sql_query(
            f"SELECT DISTINCT {selected} FROM {table} WHERE {expressions['site']} IS NOT NULL", connection)


def inventory_summary(task_repository: Any, dataset: dict[str, Any], group: str | None,
                      *, frame: pd.DataFrame | None = None) -> dict[str, Any]:
    """Count distinct sites and cells using a reusable narrow inventory frame."""
    if frame is None:
        frame = inventory_projection(task_repository, dataset)
    if 'site' not in frame.columns:
        return {'available_groups': [], 'rows': [], 'totals': None}
    available_groups = [key for key in DEPLOYMENT_GROUPINGS if key in frame.columns]
    grouped = frame.assign(_group=frame[group].replace('', pd.NA).fillna('Not set') if group in available_groups else 'All')
    counts = grouped.groupby('_group', sort=False)['site'].nunique().rename('sites').to_frame()
    counts['cells'] = grouped.groupby('_group', sort=False)['cell'].nunique() if 'cell' in frame.columns else 0
    counts = counts.reset_index().sort_values(['sites', '_group'], ascending=[False, True])
    return {
        'available_groups': available_groups,
        'rows': [{'group': str(row['_group']), 'sites': int(row['sites']), 'cells': int(row['cells'])}
                 for row in counts.to_dict('records')],
        'totals': {'sites': int(frame['site'].nunique()),
                   'cells': int(frame['cell'].nunique()) if 'cell' in frame.columns else 0},
    }


# ---------------------------------------------------------------------------
# Web routes
# ---------------------------------------------------------------------------
def install_network_insights_routes(core: Any) -> None:
    """Register the Network Insights page and its JSON API."""
    import hashlib
    import json
    from collections import OrderedDict
    import logging
    from pathlib import Path
    from threading import Lock, Thread

    from urllib.parse import urlencode

    from fastapi import Depends, Form, HTTPException, Query, Request
    from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
    from pydantic import BaseModel, Field

    from src.modules.cdr_reporting import _osm_map_tile_geometry

    app = core.app
    sample_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
    sample_cache_lock = Lock()
    analysis_cache: OrderedDict[str, bytes] = OrderedDict()
    analysis_cache_lock = Lock()
    inventory_cache: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
    inventory_cache_lock = Lock()

    class AnalysisRequest(BaseModel):
        nr_mode: str = 'NSA'
        datasets: dict[str, list[int]] = Field(default_factory=dict)
        technology: str = 'lte'
        group: list[str] | str = Field(default_factory=lambda: ['operator', 'campaign'])
        operators: list[str] = Field(default_factory=list)
        operator_vendors: list[str] = Field(default_factory=list)
        vendor_operators: list[str] = Field(default_factory=list)
        vendors: list[str] = Field(default_factory=list)
        campaigns: list[str] = Field(default_factory=list)
        regions: list[str] = Field(default_factory=list)
        clusters: list[str] = Field(default_factory=list)
        cities: list[str] = Field(default_factory=list)
        # Cities, Towns or Roads and railways (see cdr_environments).
        environments: list[str] = Field(default_factory=list)
        # LTE thresholds; NR SS-RSRP/SS-SINR have their own.
        coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD
        interference_threshold: float = DEFAULT_INTERFERENCE_THRESHOLD
        nr_coverage_threshold: float = DEFAULT_NR_COVERAGE_THRESHOLD
        nr_interference_threshold: float = DEFAULT_NR_INTERFERENCE_THRESHOLD
        grid_metres: float = 250
        min_samples: int = 3
        map_operator: str = ''
        # Summaries draw the maps of every group, not only the one shown on the page.
        map_all_groups: bool = False
        # The inventory snapshot ('' uses the newest one of every network) and the serving-cell thresholds.
        snapshot: str = ''
        overshoot_km: float = 5.0

    class SpectrumRequest(BaseModel):
        holdings: list[dict[str, Any]] = Field(default_factory=list)

    def insights_user(user=Depends(core.current_user)):
        if not core.active_workspace:
            raise HTTPException(400, 'Open a workspace before using Network Insights.')
        if user.role != 'super-admin' and not core.repository.user_has_workspace_access(user.username, core.active_workspace.id):
            raise HTTPException(403, 'You do not have access to the active workspace.')
        return user

    def editor_user(user=Depends(insights_user)):
        if user.role not in {'user-editor', 'admin', 'super-admin'}:
            raise HTTPException(403, 'Editor access required.')
        return user

    def bound_repository():
        return core.Repository(Path(core.repository.db_path), core.repository.global_db_path)

    def ready_cdrs(task_repository) -> list[dict[str, Any]]:
        rows = []
        for row in task_repository.list_datasets():
            if row['status'] != 'ready' or row['dataset_kind'] not in NETWORK_INSIGHTS_KINDS:
                continue
            item = dict(row)
            rows.append({
                'id': int(item['id']), 'kind': item['dataset_kind'], 'file_name': str(item['file_name']),
                'nr_mode': core.dataset_nr_mode(item['dataset_kind'], item.get('nr_mode'), item['file_name']),
                'cdr_stage': core.dataset_cdr_stage(item['dataset_kind'], item.get('cdr_stage'), item['file_name']),
                'row_count': int(item.get('row_count') or 0),
                'updated_at': str(item.get('updated_at') or item.get('processed_at') or ''),
            })
        return sorted(rows, key=lambda row: row['id'], reverse=True)

    def inventory_datasets(task_repository) -> list[dict[str, Any]]:
        return [
            {'id': int(row['id']), 'kind': row['dataset_kind'], 'operator': INVENTORY_DATASET_KINDS[row['dataset_kind']],
             'file_name': str(row['file_name']), 'updated_at': str(row['updated_at'] or '')}
            for row in task_repository.list_datasets()
            if row['status'] == 'ready' and row['dataset_kind'] in INVENTORY_DATASET_KINDS
        ]

    def cluster_datasets_ready(task_repository) -> bool:
        return any(row['status'] == 'ready' and row['dataset_kind'] == 'clusters'
                   for row in task_repository.list_datasets())

    def cluster_grouping_available(task_repository) -> bool:
        if cluster_datasets_ready(task_repository):
            return True
        return any(inventory_expression(task_repository.list_dataset_row_columns(dataset['id']), 'cluster',
                                        task_repository._quote_identifier)
                   for dataset in inventory_datasets(task_repository))

    def require_cluster_dataset(group: str, task_repository) -> None:
        if group == 'cluster' and not cluster_grouping_available(task_repository):
            raise HTTPException(400, 'Import Clusters polygons or an inventory with a Cluster field to group deployment by Cluster.')

    def cache_directory(task_repository) -> Path:
        """Workspace folder for Network Insights caches that survive restarts."""
        folder = Path(task_repository.db_path).resolve().parent / '.network-insights-cache'
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def write_cache_file(folder: Path, name: str, payload: bytes, keep: int, pattern: str) -> None:
        """Write atomically and keep only the newest files of one kind."""
        temporary = folder / f'.{name}.{uuid4().hex}.tmp'
        temporary.write_bytes(payload)
        temporary.replace(folder / name)
        for stale in sorted(folder.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)[keep:]:
            stale.unlink(missing_ok=True)

    def with_auto_cdrs(task_repository, request):
        """The selection with its CDRs: those of its NR Mode and Campaigns (see ``cdr_auto_selection``).

        The CDRs the combined CDR tables include (the Final CDR of each campaign, else its newest Weekly or
        Daily CDRs, or the In Combined? choice of Workspace) of the NR Mode and of the chosen campaigns (every
        campaign without one). A selection that names its own CDRs keeps them.
        """
        request = with_latest_campaigns(task_repository, request)
        if any(request.datasets.get(kind) for kind in NETWORK_INSIGHTS_KINDS):
            return request
        chosen = resolve_cdrs(task_repository, request.nr_mode, request.campaigns, NETWORK_INSIGHTS_KINDS)
        return request.model_copy(update={'datasets': chosen})

    def with_latest_campaigns(task_repository, request):
        """The selection with its one campaign (``one_campaign``: Latest campaign without one, the newest one of several)
        and Latest campaign or Previous campaign replaced by that campaign of its NR Mode now, as the samples show it
        (2026-Q2); every campaign when the NR Mode has none. A selection that names its own CDRs, without campaigns,
        keeps every campaign of them."""
        if request.campaigns or not any(request.datasets.get(kind) for kind in NETWORK_INSIGHTS_KINDS):
            request = request.model_copy(update={'campaigns': one_campaign(request.campaigns)})
        if not campaign_presets(request.campaigns):
            return request
        campaigns = resolve_campaign_filter(task_repository, request.nr_mode, request.campaigns, NETWORK_INSIGHTS_KINDS)
        labels = list(dict.fromkeys(compact_campaign_value(value) or value for value in campaigns))
        return request.model_copy(update={'campaigns': labels})

    def samples_key(task_repository, datasets: dict[str, list[int]]) -> tuple[str, dict[str, list[int]]]:
        """Identity of the normalised samples: CDR revisions and Operator mappings."""
        available = {row['id']: row for row in ready_cdrs(task_repository)}
        selected = {
            kind: [int(dataset_id) for dataset_id in datasets.get(kind, []) if int(dataset_id) in available and available[int(dataset_id)]['kind'] == kind]
            for kind in NETWORK_INSIGHTS_KINDS
        }
        if not any(selected.values()):
            raise HTTPException(400, 'Select at least one ready CDR.')
        fingerprint = json.dumps({
            'version': SAMPLES_CACHE_VERSION,
            'database': str(Path(task_repository.db_path).resolve()),
            'datasets': {kind: [(dataset_id, available[dataset_id]['updated_at']) for dataset_id in ids] for kind, ids in selected.items()},
            'mappings': {key: value for key, value in task_repository.chart_mapping_settings().items()
                         if key in {'operator_mappings', 'vendor_mappings'}},
            'excluded_operators': excluded_operators(task_repository),
        }, sort_keys=True, default=str)
        return hashlib.sha256(fingerprint.encode()).hexdigest(), selected

    def load_samples(task_repository, datasets: dict[str, list[int]]) -> pd.DataFrame:
        key, selected = samples_key(task_repository, datasets)
        with sample_cache_lock:
            cached = sample_cache.get(key)
            if cached is not None:
                sample_cache.move_to_end(key)
                return cached
        # Each CDR's samples are stored on their own, so adding or removing a
        # CDR from the selection only reads the CDRs not analysed before.
        revisions = {row['id']: row['updated_at'] for row in ready_cdrs(task_repository)}
        # The samples hold mapped Operators and Vendors: a change of either map reads them again.
        settings = task_repository.chart_mapping_settings()
        mappings = {'operator': settings.get('operator_mappings'), 'vendor': settings.get('vendor_mappings')}
        pairs = [(kind, dataset_id) for kind, ids in selected.items() for dataset_id in ids]
        # CDRs not read before are read in parallel; SQLite reads release the GIL.
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(pairs)))) as executor:
            frames = list(executor.map(
                lambda pair: dataset_samples(task_repository, pair[0], pair[1], revisions.get(pair[1]), mappings), pairs))
        frames = [frame for frame in frames if not frame.empty]
        samples = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if 'operator' in samples.columns:
            # The operators the Operator Maps exclude are left out of every analysis (the samples of each CDR keep them).
            samples = drop_excluded_operators(samples, excluded_operators(settings), columns=['operator']).reset_index(drop=True)
        with sample_cache_lock:
            sample_cache[key] = samples
            while len(sample_cache) > 3:
                sample_cache.popitem(last=False)
        return samples

    dataset_sample_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()

    def dataset_samples(task_repository, kind: str, dataset_id: int, revision: Any, mappings: Any) -> pd.DataFrame:
        """Normalised samples of one CDR, kept in memory and on disk until it or the Operator mappings change."""
        key = hashlib.sha256(json.dumps({
            'version': SAMPLES_CACHE_VERSION, 'database': str(Path(task_repository.db_path).resolve()),
            'dataset': dataset_id, 'kind': kind, 'revision': revision, 'mappings': mappings,
        }, sort_keys=True, default=str).encode()).hexdigest()
        with sample_cache_lock:
            cached = dataset_sample_cache.get(key)
            if cached is not None:
                dataset_sample_cache.move_to_end(key)
                return cached
        folder = cache_directory(task_repository)
        stored = folder / f'samples-cdr-{key}.pkl'
        samples = None
        if stored.is_file():
            try:
                samples = pd.read_pickle(stored)
                stored.touch()
            except Exception:
                stored.unlink(missing_ok=True)
        if samples is None:
            samples = read_samples(task_repository, {kind: [dataset_id]})
            buffer = io.BytesIO()
            samples.to_pickle(buffer, protocol=5)
            write_cache_file(folder, stored.name, buffer.getvalue(), keep=24, pattern='samples-cdr-*.pkl')
            # Samples of whole selections were stored before samples per CDR.
            for legacy in folder.glob('samples-*.pkl'):
                if not legacy.name.startswith('samples-cdr-'):
                    legacy.unlink(missing_ok=True)
        with sample_cache_lock:
            dataset_sample_cache[key] = samples
            while len(dataset_sample_cache) > 12:
                dataset_sample_cache.popitem(last=False)
        return samples

    def read_samples(task_repository, selected: dict[str, list[int]]) -> pd.DataFrame:
        frames = []
        mapping_settings = task_repository.chart_mapping_settings()
        profile = workspace_field_profile(task_repository)
        for kind, ids in selected.items():
            if not ids:
                continue
            source_columns: set[str] = set()
            for dataset_id in ids:
                source_columns.update(task_repository.list_dataset_row_columns(dataset_id))
            columns = resolve_source_columns(source_columns, kind, profile)
            requested = list(dict.fromkeys(columns.values()))
            for dataset_id in ids:
                task_repository.copy_dataset_rows_to_reporting(dataset_id, kind, requested)
            frame = task_repository.load_reporting_rows(kind, ids, requested)
            if frame.empty:
                continue
            if 'source_sheet' in columns and columns['source_sheet'] in frame.columns:
                sheets = frame[columns['source_sheet']].fillna('').astype(str).str.strip().str.casefold()
                frame = frame.loc[~sheets.isin(core.CDR_IGNORED_SHEET_KEYS)].copy()
            frame = core.apply_operator_mappings(frame, mapping_settings.get('operator_mappings') or {})
            frame.attrs.update(mapping_settings)
            frame = core.normalise_operator_aliases(frame)
            frames.append(normalise_samples(frame, kind, columns))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # -- favourite Analysis Selections (see network_insights_favourites) --------------------------------------------
    class FavouritePayload(BaseModel):
        name: str = ''
        selection: dict[str, Any] = Field(default_factory=dict)

    def log_favourite(task_repository, user, action: str, details: dict[str, Any]) -> None:
        task_repository.try_add_log(user.username, action, json.dumps(details, ensure_ascii=False))

    @app.get('/api/network-insights/favourites')
    def network_insights_favourites(user=Depends(insights_user)):
        return {'favourites': ni_favourites.list_favourites(bound_repository())}

    @app.post('/api/network-insights/favourites')
    def network_insights_favourite_create(payload: FavouritePayload, user=Depends(editor_user)):
        task_repository = bound_repository()
        try:
            favourite = ni_favourites.save_favourite(task_repository, None, payload.name, payload.selection, user.username)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        log_favourite(task_repository, user, 'network_insights_favourite_saved',
                      {'id': favourite['id'], 'name': favourite['name'], 'created': True, 'selection': favourite['selection']})
        return {'favourite': favourite, 'favourites': ni_favourites.list_favourites(task_repository)}

    @app.put('/api/network-insights/favourites/{favourite_id}')
    def network_insights_favourite_update(favourite_id: int, payload: FavouritePayload, user=Depends(editor_user)):
        task_repository = bound_repository()
        try:
            favourite = ni_favourites.save_favourite(task_repository, favourite_id, payload.name, payload.selection, user.username)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        log_favourite(task_repository, user, 'network_insights_favourite_saved',
                      {'id': favourite['id'], 'name': favourite['name'], 'created': False, 'selection': favourite['selection']})
        return {'favourite': favourite, 'favourites': ni_favourites.list_favourites(task_repository)}

    @app.post('/api/network-insights/favourites/{favourite_id}/rename')
    def network_insights_favourite_rename(favourite_id: int, payload: FavouritePayload, user=Depends(editor_user)):
        """Rename a favourite, keeping the selection it saved (not the changes of the panel)."""
        task_repository = bound_repository()
        try:
            favourite, previous = ni_favourites.rename_favourite(task_repository, favourite_id, payload.name, user.username)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        log_favourite(task_repository, user, 'network_insights_favourite_renamed',
                      {'id': favourite['id'], 'name': favourite['name'], 'previous': previous})
        return {'favourite': favourite, 'favourites': ni_favourites.list_favourites(task_repository)}

    @app.delete('/api/network-insights/favourites/{favourite_id}')
    def network_insights_favourite_delete(favourite_id: int, user=Depends(editor_user)):
        task_repository = bound_repository()
        favourite = ni_favourites.delete_favourite(task_repository, favourite_id)
        if favourite is None:
            raise HTTPException(404, 'The favourite Analysis Selection no longer exists.')
        log_favourite(task_repository, user, 'network_insights_favourite_deleted', {'id': favourite_id, 'name': favourite['name']})
        return {'favourites': ni_favourites.list_favourites(task_repository)}

    @app.post('/api/network-insights/favourites/{favourite_id}/open')
    def network_insights_favourite_open(favourite_id: int, user=Depends(insights_user)):
        """Record that a favourite was opened (App Events) and return it."""
        task_repository = bound_repository()
        favourite = ni_favourites.get_favourite(task_repository, favourite_id)
        if favourite is None:
            raise HTTPException(404, 'The favourite Analysis Selection no longer exists.')
        log_favourite(task_repository, user, 'network_insights_favourite_opened', {'id': favourite_id, 'name': favourite['name']})
        return {'favourite': favourite}

    @app.get('/network-insights', response_class=HTMLResponse)
    def network_insights_page(request: Request, user=Depends(insights_user)):
        task_repository = bound_repository()
        holdings = load_spectrum_holdings(task_repository)
        warm_snapshots(task_repository)
        return core.render_template(request, 'network_insights.html', {
            'user': user,
            'network_insights_config': {
                'selection_storage_key': f'network-insights:selection:{core.active_workspace.id}:{user.username}',
                # The Analysis Selections saved as favourites in this workspace, and whether this account saves them.
                'favourites': ni_favourites.list_favourites(task_repository),
                'can_edit': user.role in {'user-editor', 'admin', 'super-admin'},
                # Latest campaign and Previous campaign, first in Campaigns (one campaign): those of the NR Mode each time.
                # [value, label] pairs in their order (the page JSON sorts object keys).
                'campaign_presets': [[value, CAMPAIGN_PRESET_LABELS[value]] for value in SINGLE_CAMPAIGN_PRESETS],
                'datasets': ready_cdrs(task_repository),
                'inventories': inventory_datasets(task_repository),
                # Every inventory is a snapshot of the network on its date (see network_inventory).
                'snapshots': [{'dataset_id': int(row['id']), 'file_name': str(row['file_name']), 'kind': str(row['dataset_kind']),
                               'snapshot_date': effective_snapshot_date(row)} for row in sorted(
                    snapshot_datasets(task_repository), key=lambda row: (effective_snapshot_date(row), int(row['id'])), reverse=True)],
                'inventory_dimensions': ii.DEPLOYMENT_DIMENSIONS,
                'deployment_groups': DEPLOYMENT_GROUPINGS,
                'clusters_available': cluster_grouping_available(task_repository),
                'groupings': GROUPINGS,
                'main_cities': task_repository.list_main_cities(),
                'technologies': TECHNOLOGIES,
                'coverage_threshold': DEFAULT_COVERAGE_THRESHOLD,
                'interference_threshold': DEFAULT_INTERFERENCE_THRESHOLD,
                'nr_coverage_threshold': DEFAULT_NR_COVERAGE_THRESHOLD,
                'nr_interference_threshold': DEFAULT_NR_INTERFERENCE_THRESHOLD,
                'rsrp_classes': [{'label': label, 'lower': None if math.isinf(lower) else lower, 'colour': colour} for label, lower, colour in RSRP_CLASSES],
                'sinr_classes': [{'label': label, 'lower': None if math.isinf(lower) else lower, 'colour': colour} for label, lower, colour in SINR_CLASSES],
                'spectrum_holdings': holdings,
                'spectrum_summary': licensed_spectrum_summary(holdings),
                'band_classes': BAND_CLASSES,
                'bandwidth_scopes': BANDWIDTH_SCOPES,
                'bandwidth_title': BANDWIDTH_LADDER_TITLE,
                'nr_duplex_splits': NR_DUPLEX_SPLITS,
                'can_edit': user.role in {'user-editor', 'admin', 'super-admin'},
                # The colour themes of Scoring & GAP Analysis, for the charts, tables and exports (see scoring_themes).
                'themes': themes_payload()['themes'],
                'theme': load_user_theme(task_repository, user.username, THEME_MODULE),
                # The font and colours of each theme for the CDFs and maps (dashboard_charts.js).
                'chart_styles': {key: dashboard_chart_style(key) for key in THEMES},
            },
        })

    class ThemeRequest(BaseModel):
        theme: str

    @app.get('/api/network-insights/theme')
    def network_insights_theme(user=Depends(insights_user)):
        """The colour theme the user chose for the Network Insights charts, tables and exports in this workspace."""
        return {'theme': load_user_theme(bound_repository(), user.username, THEME_MODULE)}

    @app.put('/api/network-insights/theme')
    def network_insights_theme_save(payload: ThemeRequest, user=Depends(insights_user)):
        if payload.theme.strip().casefold() not in THEMES:
            raise HTTPException(400, f'Unknown theme: {payload.theme}.')
        task_repository = bound_repository()
        previous = load_user_theme(task_repository, user.username, THEME_MODULE)
        theme = save_user_theme(task_repository, user.username, payload.theme, THEME_MODULE)
        if theme != previous:
            task_repository.try_add_log(user.username, 'network_insights_theme_changed',
                                        json.dumps({'theme': theme, 'previous': previous}))
        return {'theme': theme}

    @app.post('/api/network-insights/filter-options')
    def network_insights_filter_options(request: AnalysisRequest, vendor_only: bool = False, user=Depends(insights_user)):
        """The values of every filter among every CDR of the NR Mode, each filter those the other filters leave.

        Read from the CDR Filter Facets (never the CDR rows), Operators and Vendors with their Maps labels and the
        Campaigns as the Campaign Maps show them. ``vendor_only`` returns only the vendor fields.
        """
        task_repository = bound_repository()
        request = with_latest_campaigns(task_repository, request)
        dataset_ids = [row['id'] for row in candidate_cdrs(task_repository, request.nr_mode, NETWORK_INSIGHTS_KINDS)]
        selections = {'Operator': request.operators, 'Operator_Vendor': request.operator_vendors,
                      'Vendor_Operator': request.vendor_operators, 'Vendor': request.vendors, 'Region': request.regions,
                      'Cluster': request.clusters, 'City': request.cities, 'Environment': request.environments,
                      'Campaign': request.campaigns}
        names = {'Operator': 'operators', 'Operator_Vendor': 'operator_vendors', 'Vendor_Operator': 'vendor_operators',
                 'Vendor': 'vendors', 'Region': 'regions', 'Cluster': 'clusters', 'City': 'cities',
                 'Environment': 'environments', 'Campaign': 'campaigns'}
        fields = ['Operator_Vendor', 'Vendor_Operator', 'Vendor'] if vendor_only else list(names)
        # CDRs whose combinations are still being read offer their catalogue meanwhile: the page asks again.
        _found, pending = stored_facets(task_repository, dataset_ids)
        options = cascading_options(task_repository, dataset_ids, selections, fields)
        if 'Environment' in options:
            options['Environment'] = sorted(options['Environment'], key=environment_order)
        if 'Campaign' in options:
            # The samples carry each campaign as the Campaign Maps show it (2026-Q2).
            options['Campaign'] = sorted({compact_campaign_value(value) or value for value in options['Campaign']}, key=campaign_sort_key)
        chosen = resolve_cdrs(task_repository, request.nr_mode, request.campaigns, NETWORK_INSIGHTS_KINDS)
        return {'options': {names[field]: values for field, values in options.items()},
                'cdrs': describe_cdrs(task_repository, chosen), 'pending': bool(pending)}

    def analysis_key(task_repository, request: AnalysisRequest) -> str:
        """Identity of an analysis: its request and every input it reads."""
        samples, _selected = samples_key(task_repository, request.datasets)
        inputs = {
            'version': ANALYSIS_CACHE_VERSION, 'samples': samples, 'request': request.model_dump(),
            'mapping_groups': task_repository.list_operator_mapping_groups(),
            # The site and sector colours of the maps come from the Vendor Maps.
            'vendor_mapping_groups': task_repository.list_vendor_mapping_groups(),
            'holdings': load_spectrum_holdings(task_repository),
            'inventories': [(row['id'], row['updated_at']) for row in inventory_datasets(task_repository)],
            'snapshots': [(row['id'], dataset_revision(row), effective_snapshot_date(row)) for row in snapshot_datasets(task_repository)],
            'serving_networks': load_serving_networks(task_repository),
        }
        return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()

    @app.post('/api/network-insights/analysis')
    def network_insights_analysis(request: AnalysisRequest, cached_only: bool = Query(False), user=Depends(insights_user)):
        # Repeating an analysis with the same CDRs and filters returns the
        # stored result instead of recalculating it, also after a restart.
        # ``cached_only`` answers 204 instead of calculating a missing result.
        task_repository = bound_repository()
        request = with_auto_cdrs(task_repository, request)
        cached = stored_analysis(task_repository, request, calculate=False)
        if cached is None and cached_only:
            return Response(status_code=204)
        if not cached_only:
            task_repository.try_add_log(user.username, 'network_insights_analysis', json.dumps({
                'datasets': sum(len(ids) for ids in request.datasets.values()), 'technology': request.technology,
                'stored_result': cached is not None,
            }))
        if cached is None:
            cached = stored_analysis(task_repository, request)
        return Response(cached, media_type='application/json')

    def stored_analysis(task_repository, request: AnalysisRequest, calculate: bool = True) -> bytes | None:
        """The stored result of an analysis (kept in memory and in the workspace cache, also after a restart), or its
        new result stored for the next time; None when it is not stored and ``calculate`` is False."""
        key = analysis_key(task_repository, request)
        with analysis_cache_lock:
            cached = analysis_cache.get(key)
            if cached is not None:
                analysis_cache.move_to_end(key)
        folder = cache_directory(task_repository)
        stored = folder / f'analysis-{key}.json'
        if cached is None and stored.is_file():
            cached = stored.read_bytes()
            stored.touch()
        if cached is None and not calculate:
            return None
        if cached is None:
            cached = json.dumps(run_analysis(request), ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
            # Every analysis made is kept (the newest 500, a few MB each) to show it again at once.
            write_cache_file(folder, stored.name, cached, keep=ANALYSES_KEPT, pattern='analysis-*.json')
        with analysis_cache_lock:
            analysis_cache[key] = cached
            while len(analysis_cache) > ANALYSES_IN_MEMORY:
                analysis_cache.popitem(last=False)
        return cached

    def technology_thresholds(request: AnalysisRequest, radio: str) -> tuple[float, float]:
        if radio == 'nr':
            return request.nr_coverage_threshold, request.nr_interference_threshold
        return request.coverage_threshold, request.interference_threshold

    def run_analysis(request: AnalysisRequest) -> dict[str, Any]:
        technology = request.technology if request.technology in TECHNOLOGIES else 'lte'
        requested_groups = [request.group] if isinstance(request.group, str) else request.group
        # Operator can only be left out when Vendor groups the samples instead.
        if 'vendor' not in requested_groups:
            requested_groups = ['operator', *requested_groups]
        # LTE+NR never pools the technologies: LTE RSRP/SINR and NR SS-RSRP/SS-SINR
        # use different reference signals, so each one gets its own section.
        groups = [field for field in GROUPINGS if field != 'technology' and field in requested_groups]
        group_label = ' → '.join(GROUPINGS[field] for field in groups) or 'All samples'
        task_repository = bound_repository()
        samples = load_samples(task_repository, request.datasets)
        if samples.empty:
            raise HTTPException(400, 'The selected CDRs have no samples.')
        options = {
            'operators': [value for value in dict.fromkeys(samples['operator']) if value],
            'operator_vendors': sorted({value for value in samples['operator_vendor'] if value}, key=str.casefold),
            'vendor_operators': sorted({value for value in samples['vendor_operator'] if value}, key=str.casefold),
            'vendors': sorted({value for value in samples['vendor'] if value}, key=str.casefold),
            'regions': sorted({value for value in samples['region'] if value}, key=str.casefold),
            'clusters': sorted({value for value in samples['cluster'] if value}, key=str.casefold),
            'cities': sorted({value for value in samples['city'] if value}, key=str.casefold),
            'environments': sorted({value for value in samples['environment'] if value}, key=environment_order),
            'campaigns': sorted({value for value in samples['campaign'] if value}, key=campaign_sort_key),
        }
        filtered = filter_samples(samples, request)
        if filtered.empty:
            raise HTTPException(400, 'No samples match the selected filters.')
        filtered = filtered.copy()
        original_operators = filtered['operator'].copy()
        operator_mappings = {str(key).casefold(): str(value)
                             for key, value in task_repository.list_operator_mappings().items()}
        inventoried_operators = {operator_mappings.get(dataset['operator'].casefold(), dataset['operator'])
                                for dataset in inventory_datasets(task_repository)}
        missing_inventory_operators = sorted(
            {str(operator) for operator in original_operators if str(operator).strip()} - inventoried_operators,
            key=lambda operator: operator_order_key(operator, task_repository.list_operator_mapping_groups()),
        )
        # The inventory cell that served each sample, in the selected snapshot of the networks allowed to serve it.
        serving_state = serving_analysis_state(task_repository, filtered, original_operators, request.snapshot)
        if serving_state is not None:
            missing_inventory_operators = [operator for operator in missing_inventory_operators
                                           if network_family(operator) not in serving_state['families']]
        # Site/cell identifiers remain scoped by their source operator when
        # operators are pooled; each group already has one operator otherwise.
        if 'operator' not in groups:
            for field in ('enodebs', 'cells'):
                filtered[field] = [tuple(f'{operator}:{value}' for value in values)
                                   for operator, values in zip(original_operators, filtered[field], strict=True)]
        if groups:
            grouping_values = filtered[groups].fillna('').astype(str)
            labels = grouping_values[groups[0]].replace('', '(Empty)')
            for field in groups[1:]:
                labels = labels.str.cat(grouping_values[field].replace('', '(Empty)'), sep=' · ')
        else:
            labels = pd.Series('All samples', index=filtered.index)
        filtered['operator'] = labels
        # Curves share their Operator/Vendor colour. Campaigns differ by line
        # width (the latest is the thickest) and other groups by line style.
        family_field = groups[0] if groups and groups[0] in {'operator', 'vendor'} else None
        secondary = [field for field in groups if field not in {family_field, 'campaign'}]
        dash_groups = None
        if family_field and secondary:
            secondary_values = filtered[secondary].fillna('').astype(str)
            secondary_labels = secondary_values[secondary[0]]
            for field in secondary[1:]:
                secondary_labels = secondary_labels.str.cat(secondary_values[field], sep=' · ')
            dash_groups = dict(zip(labels, secondary_labels, strict=True))
        widths = None
        if 'campaign' in groups:
            family_values = original_operators if family_field == 'operator' else filtered[family_field] if family_field else None
            families = dict(zip(labels, family_values.fillna('').astype(str), strict=True)) if family_values is not None else {}
            widths = campaign_line_widths(dict(zip(labels, filtered['campaign'].fillna('').astype(str), strict=True)), families)
        mapping_groups = task_repository.list_operator_mapping_groups()
        vendor_mapping_groups = task_repository.list_vendor_mapping_groups()

        def ordered_by(fields: list[str]) -> Callable[[str], tuple[Any, ...]]:
            def order(label: str) -> tuple[Any, ...]:
                """Groups in Operator Map and Vendor Map order, environments as listed, one grouping field after another."""
                parts = str(label).split(' · ')
                return tuple(
                    ((0, environment_order(part), part.casefold()) if field == 'environment' else None)
                    or dimension_order_key(field, part, mapping_groups, vendor_mapping_groups) or (0, 0, part.casefold())
                    for field, part in zip(fields, parts)
                ) if fields and len(parts) == len(fields) else ((1, 0, str(label).casefold()),)
            return order

        group_order = ordered_by(groups)
        # The groups of the views with the environments as rows (the primary bandwidth, Latency & Interactivity): the
        # grouping fields other than the environment.
        column_groups = [field for field in groups if field != 'environment']
        if column_groups:
            # (The values before the Operator column became the group labels.)
            column_parts = grouping_values[column_groups]
            group_columns = column_parts[column_groups[0]].replace('', '(Empty)')
            for field in column_groups[1:]:
                group_columns = group_columns.str.cat(column_parts[field].replace('', '(Empty)'), sep=' · ')
        else:
            group_columns = pd.Series('All samples', index=filtered.index)
        group_column_order = sorted(pd.unique(group_columns), key=ordered_by(column_groups))

        if 'operator' in groups:
            source_colours = operator_colours(original_operators, mapping_groups)
            colours = {label: source_colours[operator]
                       for label, operator in zip(labels, original_operators, strict=True)}
        else:
            colours = operator_colours(filtered['operator'], [])
        campaigns = [value for value in options['campaigns'] if value in set(filtered['campaign'])]
        radios = ('lte', 'nr') if technology == 'lte_nr' else (technology,)
        warnings = []

        def technology_section(radio: str) -> dict[str, Any]:
            label = TECHNOLOGIES[radio]
            coverage_threshold, interference_threshold = technology_thresholds(request, radio)
            rsrp, sinr = f'{radio}_rsrp', f'{radio}_sinr'
            frame = filtered
            if technology == 'lte_nr':
                frame = filtered.loc[filtered[[rsrp, sinr]].notna().any(axis=1)]
            if not frame[rsrp].notna().any():
                warnings.append(f'The selected CDRs carry no {label} RSRP samples.')
            overview = rf_summary(frame, radio, None, coverage_threshold, interference_threshold)
            overview.sort(key=lambda row: group_order(row['operator']))
            comparison = None
            if len(campaigns) >= 2 and 'campaign' not in groups:
                previous, latest = campaigns[-2], campaigns[-1]
                by_campaign = {
                    (row['operator'], row['group']): row
                    for row in rf_summary(frame.loc[frame['campaign'].isin([previous, latest])], radio, 'campaign',
                                          coverage_threshold, interference_threshold)
                }
                for row in overview:
                    before, after = by_campaign.get((row['operator'], previous)), by_campaign.get((row['operator'], latest))
                    row['deltas'] = {
                        metric: (round(after[metric] - before[metric], 2) if before and after and after[metric] is not None and before[metric] is not None else None)
                        for metric in ('rsrp_median', 'low_coverage_share', 'sinr_median', 'high_interference_share')
                    }
                comparison = {'previous': previous, 'latest': latest}
            for row in overview:
                row['technology'] = label
            map_operators = [row['operator'] for row in overview]
            map_operator = request.map_operator if request.map_operator in map_operators else (map_operators[0] if map_operators else '')
            def group_maps(operator: str) -> dict[str, Any]:
                operator_samples = frame.loc[frame['operator'] == operator]
                coverage_cells, coverage_grid = grid_cells(operator_samples, rsrp, coverage_threshold, request.grid_metres, request.min_samples)
                interference_cells, interference_grid = grid_cells(operator_samples, sinr, interference_threshold, request.grid_metres, request.min_samples)
                maps = {
                    'operator': operator,
                    'coverage': map_payload(coverage_cells, RSRP_CLASSES, f'{operator} · Mean {label} RSRP per {coverage_grid:g} m grid', 'dBm', _osm_map_tile_geometry),
                    'coverage_hotspots': hotspots(coverage_cells), 'coverage_grid_metres': coverage_grid,
                    'interference': map_payload(interference_cells, SINR_CLASSES, f'{operator} · Mean {label} SINR per {interference_grid:g} m grid', 'dB', _osm_map_tile_geometry),
                    'interference_hotspots': hotspots(interference_cells), 'interference_grid_metres': interference_grid,
                }
                if serving_state is not None:
                    # The sites of the networks serving this group around its weakest and most interfered areas,
                    # drawn as one wedge per cell in the colour of its vendor.
                    families = {family for source in pd.unique(original_operators.loc[operator_samples.index])
                                for family in serving_families(source, serving_state['config'])}
                    centres = [(row['longitude'], row['latitude']) for row in maps['coverage_hotspots'][:25] + maps['interference_hotspots'][:25]]
                    overlay = ii.sector_overlay(serving_state['cells'], families, centres,
                                                vendor_colours=ii.configured_vendor_colours(vendor_mapping_groups))
                    for kind in ('coverage', 'interference'):
                        if maps[kind].get('type') != 'map':
                            continue
                        # A zoomed map loads the sites of these networks wherever it shows (see map-sites).
                        maps[kind]['sector_source'] = {'families': sorted(families), 'snapshot': str(request.snapshot or '')}
                        if overlay['sectors']:
                            maps[kind]['sectors'] = overlay['sectors']
                            maps[kind]['legend']['items'] = [*maps[kind]['legend']['items'], *overlay['legend']]
                    # Locked, halted, disabled, planned and in-progress cells of the snapshot around the same areas.
                    areas = [{**row, 'kind': kind} for kind in ('coverage', 'interference') for row in maps[f'{kind}_hotspots'][:25]]
                    maps['cell_status'] = {
                        **ii.cell_status_near_areas(serving_state['cells'], families, areas, family_labels=serving_state['labels']),
                        'snapshot_dates': sorted({serving_state['snapshot_dates'][family] for family in families
                                                  if serving_state['snapshot_dates'].get(family)}),
                    }
                return maps

            selected_maps = group_maps(map_operator)
            return {
                'technology': radio, 'technology_label': label,
                'coverage_threshold': coverage_threshold, 'interference_threshold': interference_threshold,
                'overview': overview, 'rf_rows': overview, 'comparison': comparison,
                'charts': {
                    'rsrp_cdf': cdf_payload(frame, rsrp, None, f'{label} RSRP', 'RSRP (dBm)', colours, dash_groups=dash_groups, widths=widths, order_key=group_order),
                    'sinr_cdf': cdf_payload(frame, sinr, None, f'{label} SINR', 'SINR (dB)', colours, dash_groups=dash_groups, widths=widths, order_key=group_order),
                },
                'maps': {
                    **selected_maps, 'operators': map_operators,
                    **({'groups': [selected_maps if operator == map_operator else group_maps(operator) for operator in map_operators]}
                       if request.map_all_groups else {}),
                },
            }

        def bandwidth_payload() -> dict[str, Any]:
            """Samples per band and bandwidth, and the primary bandwidth (LTE + NR) of the CDR Data tests per group
            and environment, for the download tests and for every test."""
            # The environment makes the rows of the primary bandwidth, so the columns are the other grouping fields.
            columns, column_order = group_columns, group_column_order
            band_order = {name: index for index, name in enumerate(BAND_CATALOGUE)}
            data = filtered['kind'].eq('Data')
            scopes = {}
            for scope in BANDWIDTH_SCOPES:
                tests = filtered.loc[data & (filtered['download'].astype(bool) if scope == 'download' else True)]
                bands = sorted(band_bandwidths(tests), key=lambda row: (group_order(row['operator']), row['technology'],
                                                                        band_order.get(row['band'], 999), row['band']))
                split_ladders = {}
                for name, field in (('site_type', 'site_type'), ('vendor', 'vendor')):
                    split, order = split_columns(tests, columns, column_order, field)
                    if order:
                        split_ladders[name] = bandwidth_ladders(tests, split, order)
                scopes[scope] = {'tests': int(len(tests)), 'bands': bands,
                                 'ladders': bandwidth_ladders(tests, columns.loc[tests.index], column_order),
                                 'split_ladders': split_ladders,
                                 'locations': location_strips(tests, columns, column_order)}
            return {
                'classes': [{'label': label, 'lower': lower, 'upper': upper, 'colour': colour, 'width': width}
                            for label, lower, upper, colour, width in BANDWIDTH_CLASSES],
                'title': BANDWIDTH_LADDER_TITLE, 'narrow_below_mhz': NARROW_BANDWIDTH_MHZ, 'wide_from_mhz': WIDE_BANDWIDTH_MHZ,
                'scopes': scopes,
                'scope_labels': BANDWIDTH_SCOPES,
                'column_label': ' → '.join(GROUPINGS[field] for field in column_groups) or 'All samples',
                'column_colours': {column: colours.get(label, '') for column, label in
                                   pd.DataFrame({'column': columns, 'label': labels}).drop_duplicates('column').itertuples(index=False)},
            }

        def findings_section() -> dict[str, Any]:
            """Key Findings: six benchmark views of the Data tests, the groups without the environment as columns. A
            split by Campaign compares the groups of the latest campaign, as benchmark reports do."""
            fields = [field for field in column_groups if field != 'campaign']
            frame = filtered
            campaign = ''
            if 'campaign' in column_groups and campaigns:
                campaign = campaigns[-1]
                frame = filtered.loc[filtered['campaign'] == campaign]
            if fields:
                parts = grouping_values.loc[frame.index, fields]
                columns = parts[fields[0]].replace('', '(Empty)')
                for field in fields[1:]:
                    columns = columns.str.cat(parts[field].replace('', '(Empty)'), sep=' · ')
            else:
                columns = pd.Series('All samples', index=frame.index)
            order = sorted(pd.unique(columns), key=ordered_by(fields))
            column_colours = {column: colours.get(label, '') for column, label in
                              pd.DataFrame({'column': columns, 'label': labels.loc[frame.index]}).drop_duplicates('column')
                              .itertuples(index=False)}
            # The campaigns the views compare (the latest one with a split by Campaign), for their footnotes.
            return {**findings_payload(frame, columns, order, column_colours), 'campaign': campaign,
                    'campaigns': [campaign] if campaign else campaigns}

        sections = [technology_section(radio) for radio in radios]
        if filtered[['latitude', 'longitude']].dropna().empty:
            warnings.append('The selected CDRs carry no sample coordinates, so maps are unavailable.')
        holdings = load_spectrum_holdings(task_repository)
        rows = [row for section in sections for row in section['overview']]
        first = sections[0]
        return {
            'technology': technology, 'technology_label': TECHNOLOGIES[technology],
            'group': groups, 'group_label': group_label,
            'options': options, 'comparison': first['comparison'],
            # Every technology section in order; LTE+NR has one for LTE and one for NR.
            'sections': sections,
            'overview': rows,
            'rf_rows': rows,
            'missing_inventory_operators': missing_inventory_operators,
            'charts': first['charts'],
            'maps': first['maps'],
            'spectrum': {
                'observed': sorted(observed_spectrum(filtered), key=lambda row: group_order(row['operator'])),
                'licensed': sorted(licensed_spectrum_summary(holdings), key=lambda row: operator_order_key(row['operator'], mapping_groups)),
                'bandwidth': bandwidth_payload(),
            },
            'findings': findings_section(),
            # Latency & Interactivity, and the NR quality of each carrier (RF Quality), per group.
            'interactivity': interactivity_detail(filtered, group_columns, group_column_order),
            'nr_bands': nr_band_quality(filtered, group_columns, group_column_order),
            'colours': colours,
            'warnings': warnings,
            'serving': serving_payload(serving_state, filtered, labels, colours, group_order, request.overshoot_km,
                                       vendor_groups=vendor_mapping_groups, operator_groups=mapping_groups),
        }

    def family_operator_labels(task_repository) -> dict[str, str]:
        """Network family → the Operator Maps name it is shown as.

        The group that holds the plain name of the network (Vodafone UK, Three, O2) wins over the groups of tests
        in another mode (Vodafone SM, VF SA), then the shortest name.
        """
        base_names = {'vodafone': {'vodafone', 'vodafoneuk', 'vf', 'vfuk'}, 'three': {'3', 'three', 'threeuk', '3uk', 'h3g'},
                      'o2': {'o2', 'o2uk', 'telefonica'}, 'ee': {'ee', 'eeuk'}}
        best: dict[str, tuple[int, int, str]] = {}
        for group in task_repository.list_operator_mapping_groups():
            canonical = str(group.get('canonical') or '').strip()
            values = [canonical, *(group.get('aliases') or [])]
            identities = {re.sub(r'[^a-z0-9]+', '', str(value).casefold()) for value in values}
            for family in {network_family(value) for value in values} - {''}:
                rank = (0 if identities & base_names.get(family, set()) else 1, len(canonical), canonical)
                if canonical and (family not in best or rank < best[family]):
                    best[family] = rank
        return {family: rank[2] for family, rank in best.items()}

    def serving_analysis_state(task_repository, samples: pd.DataFrame, operators: pd.Series, choice: str) -> dict[str, Any] | None:
        snapshots = ensure_inventory_cells(task_repository)
        selection = ii.snapshot_choice(snapshots, choice)
        if not selection or samples.empty:
            return None
        cells = ii.load_cells(task_repository, selection)
        config = load_serving_networks(task_repository)
        serving = ii.serving_cells(samples, operators, cells, config, float(config['max_distance_km']))
        # The NR cell of the NSA samples, from their NR PCI and band/SSB frequency around the LTE anchor.
        nr_leg = ii.nsa_nr_cells(samples, operators, serving, cells, config, float(config['max_distance_km']))
        dates = {int(item['dataset_id']): str(item['snapshot_date']) for item in snapshots}
        return {'cells': cells, 'serving': serving, 'nr_leg': nr_leg, 'families': set(selection), 'selection': selection, 'config': config,
                'labels': family_operator_labels(task_repository), 'max_distance_km': config['max_distance_km'],
                'snapshot_dates': {family: dates.get(int(dataset_id), '') for family, dataset_id in selection.items()}}

    def serving_payload(state, samples: pd.DataFrame, labels: pd.Series, colours: dict[str, str], order_key, overshoot_km: float,
                        vendor_groups: list[dict[str, Any]] | None = None, operator_groups: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
        if state is None:
            return None
        serving = state['serving']
        order = sorted(dict.fromkeys(labels), key=order_key)
        summary = ii.serving_summary(samples, serving, labels, overshoot_km)
        summary.sort(key=lambda row: order_key(row['operator']))
        distances = pd.DataFrame({'operator': labels.to_numpy(), 'distance': serving['distance_km'].to_numpy(dtype=float)})
        family_labels = state['labels']
        name = lambda value: ii.family_label(str(value), family_labels) if isinstance(value, str) else value
        named = serving.assign(network_family=serving['network_family'].map(name), host_family=serving['host_family'].map(name))
        sites = ii.site_positions(state['cells'])
        nr_leg = state['nr_leg']
        by_label = lambda rows: sorted(rows, key=lambda row: order_key(row['operator']))
        # The NR leg shaped as serving cells, to break it down by NR vendor like the serving cells.
        nr_serving = pd.DataFrame({'matched': nr_leg['nr_matched'].astype(bool), 'distance_km': nr_leg['nr_distance_km'],
                                   'nr_vendor': nr_leg['nr_vendor'].fillna('')}, index=nr_leg.index)
        return {
            'max_distance_km': state['max_distance_km'], 'overshoot_km': overshoot_km,
            'summary': summary,
            'by_band': ii.serving_breakdown(serving, labels, 'band_3gpp', overshoot_km),
            'by_vendor': ii.serving_breakdown(serving, labels, 'vendor', overshoot_km),
            'by_host': ii.serving_breakdown(named, labels, 'host_family', overshoot_km),
            'by_network': ii.serving_breakdown(named, labels, 'network_family', overshoot_km),
            'overshooting_cells': ii.overshooting_cells(samples.assign(operator=labels.to_numpy()), serving, overshoot_km, family_labels=family_labels),
            'nr_availability': (lambda nr: {**nr, 'rows': by_label(nr['rows'])})(
                ii.nr_availability(samples.assign(operator=labels.to_numpy()), serving, labels, sites, nr_leg=nr_leg)),
            'nr_leg': {'rows': by_label(ii.nr_leg_summary(nr_leg, labels)),
                       'by_vendor': ii.serving_breakdown(nr_serving, labels, 'nr_vendor', overshoot_km)},
            'mimo': sorted(ii.mimo_breakdown(samples, serving, nr_leg, labels),
                           key=lambda row: (order_key(row['operator']), row['technology'], row['tx_antennas'] is None, row['tx_antennas'] or 0)),
            'distance_cdf': cdf_payload(distances.dropna(), 'distance', None, 'Distance to the serving site', 'Distance (km)',
                                        colours, order_key=order_key),
            **vendor_distance_payload(serving, vendor_groups, operator_groups),
            'order': order,
        }

    def vendor_distance_payload(serving: pd.DataFrame, vendor_groups, operator_groups) -> dict[str, Any]:
        """The distance to the serving site per RAN vendor of the serving cell, every group together: its CDF in the
        Vendor Maps colours and order, with the P10, P50 and P90 of each vendor."""
        matched = serving.loc[serving['matched'].astype(bool) & serving['vendor'].fillna('').astype(str).ne('')]
        frame = pd.DataFrame({'operator': matched['vendor'].astype(str).to_numpy(), 'distance': matched['distance_km'].to_numpy(dtype=float)}).dropna()
        configured = ii.configured_vendor_colours(vendor_groups)
        vendors = sorted(pd.unique(frame['operator']), key=lambda vendor: vendor_order_key(vendor, vendor_groups, operator_groups))
        rank = {vendor: index for index, vendor in enumerate(vendors)}
        colours = {vendor: ii.vendor_colour(vendor, configured) for vendor in vendors}
        rows = []
        for vendor in vendors:
            values = frame.loc[frame['operator'] == vendor, 'distance']
            rows.append({'operator': vendor, 'samples': int(len(values)), 'p10_km': round(float(values.quantile(.1)), 3),
                         'median_km': round(float(values.median()), 3), 'p90_km': round(float(values.quantile(.9)), 3)})
        return {
            'vendor_distance_cdf': cdf_payload(frame, 'distance', None, 'Distance to the serving site by RAN vendor', 'Distance (km)',
                                               colours, order_key=lambda vendor: rank.get(vendor, len(rank))),
            'vendor_distances': rows, 'vendor_colours': colours,
        }

    class SnapshotRequest(BaseModel):
        snapshot: str = ''
        group: str = 'host_network'
        in_service_only: bool = True
        technology: str = ''
        # Another snapshot to compare with (its dataset ID), for the networks both describe.
        compare: str = ''

    snapshot_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
    snapshot_cache_lock = Lock()
    snapshot_warming = Lock()

    def snapshot_file(task_repository, name: str) -> Path:
        return cache_directory(task_repository) / f'snapshot-{name}.json'

    def read_snapshot_file(task_repository, name: str) -> dict[str, Any] | None:
        """A snapshot payload stored by an earlier run, also after a restart (see snapshot_payload)."""
        stored = snapshot_file(task_repository, name)
        if not stored.is_file():
            return None
        try:
            payload = json.loads(stored.read_bytes())
        except (OSError, ValueError):
            stored.unlink(missing_ok=True)
            return None
        stored.touch()
        return payload

    def write_snapshot_file(task_repository, name: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'),
                          default=lambda value: value.item() if hasattr(value, 'item') else str(value)).encode('utf-8')
        write_cache_file(cache_directory(task_repository), snapshot_file(task_repository, name).name, data, keep=120, pattern='snapshot-*.json')

    def warm_snapshots(task_repository) -> None:
        """Prepare, in the background, the payload of the newest snapshots and of every single snapshot, so switching
        the Inventory snapshot shows at once; what is already stored is only read."""
        if not snapshot_warming.acquire(blocking=False):
            return

        def run() -> None:
            try:
                for choice in ['', *(str(int(row['id'])) for row in snapshot_datasets(task_repository))]:
                    snapshot_payload(task_repository, choice)
            except Exception as exc:  # Warming is a convenience: a failure only leaves the work for the request.
                logging.getLogger(__name__).warning('Network Insights snapshot warm-up stopped: %s', exc)
            finally:
                snapshot_warming.release()

        Thread(target=run, name='network-insights-snapshots', daemon=True).start()

    def polygon_names(task_repository, longitude: pd.Series, latitude: pd.Series, dimension: str) -> pd.Series | None:
        """The imported Region or Cluster polygon of each position (newest upload first), or None without polygons."""
        sources = inventory_polygon_sources(task_repository)
        lookups = inventory_polygon_lookup(sources) if sources else {}
        if dimension not in lookups:
            return None
        from shapely import points
        tree, names = lookups[dimension]
        located = longitude.notna() & latitude.notna()
        result = pd.Series('', index=longitude.index, dtype=object)
        if located.any():
            geometries = points(np.c_[longitude[located].to_numpy(dtype=float), latitude[located].to_numpy(dtype=float)])
            source, target = tree.query(geometries, predicate='intersects')
            best = pd.Series(target, index=source).groupby(level=0).min()
            located_index = longitude.index[located]
            result.loc[located_index[best.index]] = [names[position] for position in best.to_numpy()]
        return result

    @lru_cache(maxsize=4)
    def polygon_areas(sources: tuple, dimension: str) -> dict[str, float]:
        """km² of each imported Region or Cluster name (equal-area projection)."""
        from src.modules.geospatial import _column, _read_region_mapping, _region_field
        kind = 'regions' if dimension == 'Region' else 'clusters'
        areas: dict[str, float] = {}
        for source_kind, _identifier, _revision, path, _mtime in sources:
            if source_kind != kind:
                continue
            boundaries = _read_region_mapping(Path(path), dimension)
            field = _region_field(boundaries.columns) if dimension == 'Region' else next(
                found for candidate in ('Cluster', 'Cluster_ID', 'Cluster_Name', 'ClusterName', 'Name')
                if (found := _column(boundaries.columns, candidate)))
            projected = boundaries.to_crs('EPSG:6933')
            for name, area in zip(projected[field].astype(str).str.strip(), projected.geometry.area / 1e6):
                areas.setdefault(name, float(area))
        return areas

    def snapshot_payload(task_repository, choice: str = '', group: str = 'host_network', in_service_only: bool = True,
                         technology: str = '') -> dict[str, Any]:
        """Deployment, host networks, deployed spectrum, density and quality of the selected inventory snapshot.

        What does not depend on the grouping is cached apart, so switching the grouping only counts the cells again.
        """
        snapshots = ensure_inventory_cells(task_repository)
        labels = family_operator_labels(task_repository)
        overview = ii.snapshot_overview(task_repository, choice, labels)
        selection = {item['family']: item['dataset_id'] for item in overview['selection']}
        group = group if group in ii.DEPLOYMENT_DIMENSIONS else 'host_network'
        technology = technology if technology in {'LTE', 'NR'} else ''
        sources = inventory_polygon_sources(task_repository)
        base_key = hashlib.sha256(json.dumps([str(task_repository.db_path), snapshots, overview['selection'], in_service_only,
                                              sources, labels], sort_keys=True, default=str).encode()).hexdigest()
        key = f'{base_key}:{group}:{technology}'
        with snapshot_cache_lock:
            cached = snapshot_cache.get(key)
            base = snapshot_cache.get(base_key)
        # Payloads computed before, also before a restart, are read from the workspace cache folder.
        if cached is None and (cached := read_snapshot_file(task_repository, hashlib.sha256(key.encode()).hexdigest())) is not None:
            with snapshot_cache_lock:
                snapshot_cache[key] = cached
        if cached is not None:
            return with_network_colours(task_repository, cached)
        if base is None and (base := read_snapshot_file(task_repository, f'base-{base_key}')) is not None:
            with snapshot_cache_lock:
                snapshot_cache[base_key] = base
        cells = ii.load_cells(task_repository, selection)
        if base is None:
            sites = ii.site_positions(cells, in_service_only=False)
            # The imported polygon of every site, once: every cell takes the name of its site.
            site_names = {}
            for dimension in ('Region', 'Cluster'):
                names = polygon_names(task_repository, sites['longitude'], sites['latitude'], dimension) if len(sites) else None
                if names is not None:
                    site_names[dimension.lower()] = dict(zip(sites['site_key'], names, strict=True))
            in_service_sites = ii.site_positions(cells) if in_service_only else sites
            density = {}
            for dimension in ('cluster', 'region'):
                if dimension in site_names:
                    names = in_service_sites['site_key'].map(site_names[dimension]).fillna('')
                    density[dimension] = ii.density_rows(in_service_sites, dimension.title(), names, polygon_areas(sources, dimension.title()), labels)
                elif len(in_service_sites) and dimension in in_service_sites:
                    density[dimension] = ii.density_rows(in_service_sites, dimension.title(), in_service_sites[dimension].fillna(''), {}, labels)
            base = {
                'site_names': site_names,
                'host_matrix': ii.host_matrix(cells, in_service_only, labels),
                'spectrum': [{**row, 'band_class': band_class(row['band'])} for row in ii.deployed_spectrum(cells, labels)],
                'quality': ii.inventory_quality(cells, labels),
                'density': density,
            }
            with snapshot_cache_lock:
                snapshot_cache[base_key] = base
            write_snapshot_file(task_repository, f'base-{base_key}', base)

        def value_names(field: str, frame: pd.DataFrame) -> pd.Series:
            if field in {'region', 'cluster'} and field in base['site_names']:
                return frame['site_key'].map(base['site_names'][field]).fillna('')
            if field in {'host_network', 'network'}:
                column = 'host_family' if field == 'host_network' else 'network_family'
                names = {value: ii.family_label(value, labels) for value in pd.unique(frame[column])}
                return frame[column].map(names)
            return frame['band_3gpp'] if field == 'band' else frame[field].astype(str)

        payload = {
            **overview, 'group': group, 'group_label': ii.DEPLOYMENT_DIMENSIONS[group], 'dimensions': ii.DEPLOYMENT_DIMENSIONS,
            'in_service_only': in_service_only, 'technology': technology,
            'deployment': ii.deployment_tables(cells, group, in_service_only, technology, labels, value_names),
            **{name: base[name] for name in ('host_matrix', 'spectrum', 'quality', 'density')},
            'polygons': sorted({source[0] for source in sources}),
        }
        with snapshot_cache_lock:
            snapshot_cache[key] = payload
            while len(snapshot_cache) > 40:
                snapshot_cache.popitem(last=False)
        write_snapshot_file(task_repository, hashlib.sha256(key.encode()).hexdigest(), payload)
        return with_network_colours(task_repository, payload)

    def with_network_colours(task_repository, payload: dict[str, Any]) -> dict[str, Any]:
        """The snapshot payload with its networks in the order and colours of the Operator Maps (read each time, so a
        new order or colour shows without rebuilding the snapshot)."""
        groups = task_repository.list_operator_mapping_groups()
        rank = lambda name: operator_order_key(name, groups)
        by_network = lambda rows: sorted(rows, key=lambda row: rank(row['operator']))
        names = {row['operator'] for rows in payload.get('density', {}).values() for row in rows}
        names |= {row['operator'] for key in ('quality', 'spectrum', 'selection', 'deployment') for row in payload.get(key, [])}
        matrix = payload.get('host_matrix') or {}
        names |= set(matrix.get('owners', [])) | set(matrix.get('hosts', []))
        order = sorted(names, key=rank)
        ordered = {**payload, **{key: by_network(payload[key]) for key in ('quality', 'spectrum', 'selection', 'deployment') if key in payload}}
        if matrix:
            ordered['host_matrix'] = {**matrix, 'owners': sorted(matrix.get('owners', []), key=rank), 'hosts': sorted(matrix.get('hosts', []), key=rank)}
        ordered['density'] = {dimension: by_network(rows) for dimension, rows in payload.get('density', {}).items()}
        return {**ordered, 'network_order': order, 'colours': operator_colours(order, groups)}

    class MapSitesRequest(BaseModel):
        snapshot: str = ''
        families: list[str] = []
        # The map view: west, south, east and north (degrees).
        bbox: list[float] = []

    @app.post('/api/network-insights/map-sites')
    def network_insights_map_sites(request: MapSitesRequest, user=Depends(insights_user)):
        """The inventory sites of the networks serving a map group inside the view of a zoomed map, with their
        sectors. Only close views (up to 2° across) load sites; moving around a map changes nothing, so it is not
        an App Event."""
        if len(request.bbox) != 4 or not all(math.isfinite(value) for value in request.bbox):
            raise HTTPException(422, 'The map view needs its west, south, east and north limits.')
        west, south, east, north = request.bbox
        if east <= west or north <= south:
            raise HTTPException(422, 'The map view needs its west, south, east and north limits.')
        if east - west > 2 or north - south > 2:
            return {'sectors': [], 'legend': [], 'too_wide': True}
        task_repository = bound_repository()
        selection = ii.snapshot_choice(ensure_inventory_cells(task_repository), request.snapshot)
        families = [family for family in request.families if family in selection]
        if not families:
            return {'sectors': [], 'legend': []}
        cells = ii.load_cells(task_repository, selection)
        return ii.sector_overlay(cells, families, [], limit_sites=800, bbox=(west, south, east, north),
                                 vendor_colours=ii.configured_vendor_colours(task_repository.list_vendor_mapping_groups()))

    @app.post('/api/network-insights/snapshot')
    def network_insights_snapshot(request: SnapshotRequest, user=Depends(insights_user)):
        """Deployment, host networks, deployed spectrum, density and quality of the selected inventory snapshot."""
        task_repository = bound_repository()
        payload = snapshot_payload(task_repository, request.snapshot, request.group, request.in_service_only, request.technology)
        comparison = None
        if str(request.compare or '').strip():
            try:
                compare_id = int(request.compare)
            except ValueError as exc:
                raise HTTPException(422, 'Choose a snapshot to compare with.') from exc
            other = next((item for item in ensure_inventory_cells(task_repository) if item['dataset_id'] == compare_id), None)
            if other is None:
                raise HTTPException(404, 'The snapshot to compare with is not available.')
            labels = family_operator_labels(task_repository)
            selection = {item['family']: item['dataset_id'] for item in payload['selection']}
            current = ii.load_cells(task_repository, selection)
            before = ii.load_cells(task_repository, {family: compare_id for family in other['families'] if family})
            groups = task_repository.list_operator_mapping_groups()
            comparison = {'dataset_id': compare_id, 'file_name': other['file_name'], 'snapshot_date': other['snapshot_date'],
                          'networks': sorted(ii.compare_snapshots(current, before, labels), key=lambda row: operator_order_key(row['operator'], groups))}
        task_repository.try_add_log(user.username, 'network_insights_snapshot', json.dumps({
            'snapshot': request.snapshot, 'group': payload['group'], 'in_service_only': request.in_service_only,
            'technology': payload['technology'], 'compare': request.compare}))
        return {**payload, 'comparison': comparison}

    class NrDuplexRequest(AnalysisRequest):
        split: str = ''

    nr_duplex_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
    site_names_cache: OrderedDict[str, dict[str, str]] = OrderedDict()
    nr_duplex_lock = Lock()

    def remembered(cache: OrderedDict, key: str, build, keep: int):
        with nr_duplex_lock:
            if key in cache:
                cache.move_to_end(key)
                return cache[key]
        value = build()
        with nr_duplex_lock:
            cache[key] = value
            while len(cache) > keep:
                cache.popitem(last=False)
        return value

    def inventory_site_names(task_repository, cells: pd.DataFrame, selection_key: str, dimension: str) -> dict[str, str]:
        """Site key → its imported Region or Cluster polygon, else the Region or Cluster field of its inventory."""
        def build() -> dict[str, str]:
            sites = ii.site_positions(cells, in_service_only=False)
            names = polygon_names(task_repository, sites['longitude'], sites['latitude'], dimension.title()) if len(sites) else None
            if names is None:
                fields = cells.loc[cells[dimension] != '', ['site_key', dimension]].drop_duplicates('site_key')
                return dict(zip(fields['site_key'], fields[dimension], strict=True))
            return {key: name for key, name in zip(sites['site_key'], names, strict=True) if name}
        return remembered(site_names_cache, f'{selection_key}:{dimension}', build, keep=8)

    def nr_duplex_payload(task_repository, request: NrDuplexRequest) -> dict[str, Any]:
        """The NR sites by duplex mode of the inventory snapshot, after the Operators, Operator_Vendor, Vendors,
        Regions, Clusters and Cities filters (Campaigns, NR Mode and Environments describe the measurements)."""
        snapshots = ensure_inventory_cells(task_repository)
        labels = family_operator_labels(task_repository)
        overview = ii.snapshot_overview(task_repository, request.snapshot, labels)
        selection = {item['family']: item['dataset_id'] for item in overview['selection']}
        split = request.split if request.split in NR_DUPLEX_SPLITS else ''
        filters = {key: sorted({str(value).strip() for value in getattr(request, key) if str(value).strip()})
                   for key in ('operators', 'operator_vendors', 'vendors', 'regions', 'clusters', 'cities')}
        sources = inventory_polygon_sources(task_repository)
        selection_key = hashlib.sha256(json.dumps([str(task_repository.db_path), snapshots, selection, sources],
                                                  sort_keys=True, default=str).encode()).hexdigest()
        key = hashlib.sha256(json.dumps([selection_key, labels, split, filters, task_repository.chart_mapping_settings()],
                                        sort_keys=True, default=str).encode()).hexdigest()

        def build() -> dict[str, Any]:
            cells = ii.load_cells(task_repository, selection)
            keep = pd.Series(True, index=cells.index)
            missing = []
            if filters['operators']:
                families = {network_family(operator) for operator in filters['operators']}
                missing = [operator for operator in filters['operators'] if network_family(operator) not in selection]
                keep &= cells['network_family'].isin(families)
            normalise = inventory_filter_normalizer(task_repository)
            if filters['vendors']:
                wanted = {normalise(value, 'Vendor') for value in filters['vendors']}
                vendors = {value: normalise(value, 'Vendor') for value in pd.unique(cells['vendor'])}
                keep &= cells['vendor'].map(vendors).isin(wanted)
            if filters['operator_vendors']:
                # Operator_Vendor pairs: the operator family and the mapped vendor; "- All" pairs keep every vendor.
                pairs = [normalise(value, 'Operator_Vendor').partition('|') for value in filters['operator_vendors']]
                identities = {pair: normalise(f'{ii.family_label(pair[0], labels)}_{pair[1]}', 'Operator_Vendor').partition('|')
                              for pair in set(zip(cells['network_family'], cells['vendor']))}
                accepted = {pair for pair, (family, _sep, vendor) in identities.items()
                            if any(family == chosen and (not chosen_vendor or vendor == chosen_vendor) for chosen, _s, chosen_vendor in pairs)}
                keep &= pd.Series(list(zip(cells['network_family'], cells['vendor'])), index=cells.index).isin(accepted)
            if filters['cities']:
                keep &= cells['city'].str.casefold().isin({value.casefold() for value in filters['cities']})
            for dimension, values in (('region', filters['regions']), ('cluster', filters['clusters'])):
                if values:
                    names = inventory_site_names(task_repository, cells, selection_key, dimension)
                    keep &= cells['site_key'].map(names).fillna('').str.casefold().isin({value.casefold() for value in values})
            chosen = cells.loc[keep]
            areas = None
            if split in {'region', 'cluster'}:
                areas = inventory_site_names(task_repository, cells, selection_key, split)
            elif split:
                nr = chosen.loc[chosen['is_nr'] & chosen['in_service']]
                field = 'host_family' if split == 'host_network' else split
                first = nr.loc[nr[field] != ''].drop_duplicates('site_key')
                areas = dict(zip(first['site_key'], first[field].map(lambda value: ii.family_label(value, labels))
                                 if split == 'host_network' else first[field], strict=True))
            duplex = {band: details[1] for band, details in BAND_CATALOGUE.items() if band.startswith('n')}
            groups = task_repository.list_operator_mapping_groups()
            rows = ii.nr_duplex_sites(chosen, duplex, labels, areas)
            area_rank = {area: index for index, area in enumerate(dict.fromkeys(row['area'] for row in rows))}
            rows.sort(key=lambda row: (area_rank[row['area']], row['all_networks'], operator_order_key(row['operator'], groups)))
            return {
                'split': split, 'split_label': NR_DUPLEX_SPLITS[split], 'rows': rows, 'radius_m': ii.PHYSICAL_SITE_RADIUS_M,
                'selection': overview['selection'], 'filters': {name: len(values) for name, values in filters.items() if values},
                'missing_operators': missing, 'colours': operator_colours([row['operator'] for row in rows if not row['all_networks']], groups),
            }

        return remembered(nr_duplex_cache, key, build, keep=16)

    @app.post('/api/network-insights/nr-duplex-sites')
    def network_insights_nr_duplex_sites(request: NrDuplexRequest, user=Depends(insights_user)):
        """In-service sites with NR TDD and NR FDD of the inventory snapshot, logical and physical."""
        task_repository = bound_repository()
        payload = nr_duplex_payload(task_repository, request)
        task_repository.try_add_log(user.username, 'network_insights_nr_duplex_sites', json.dumps({
            'snapshot': request.snapshot, 'split': payload['split'], 'filters': payload['filters'], 'rows': len(payload['rows'])}))
        return payload

    # ------------------------------------------------------------------
    # Sites/Cells tables: complete inventories or cells observed in CDRs
    # ------------------------------------------------------------------
    class SitesRequest(AnalysisRequest):
        source: str = 'inventory'
        operator: str = ''
        page: int = 0
        column: str = ''
        search: str = ''
        # Excel-style column filters: column -> accepted values ('' is blank).
        filters: dict[str, list[str]] = Field(default_factory=dict)

    site_tables_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
    site_tables_lock = Lock()

    def remember(key: str, build) -> dict[str, Any]:
        with site_tables_lock:
            cached = site_tables_cache.get(key)
            if cached is not None:
                site_tables_cache.move_to_end(key)
                return cached
        value = build()
        with site_tables_lock:
            site_tables_cache[key] = value
            while len(site_tables_cache) > 8:
                site_tables_cache.popitem(last=False)
        return value

    def operator_labels(task_repository) -> dict[str, str]:
        """Mapped operator -> inventory label (Vodafone, Three) of the uploaded inventories."""
        mappings = {str(key).casefold(): str(value) for key, value in task_repository.list_operator_mappings().items()}
        return {mappings.get(row['operator'].casefold(), row['operator']): row['operator']
                for row in inventory_datasets(task_repository)}

    def inventory_index(task_repository) -> dict[str, Any]:
        """Normalised key fields of every inventory row, built once per inventory revision.

        Pages, filters and value lists read this index; only the visible rows
        are read back from the stored inventories.
        """
        datasets = inventory_datasets(task_repository)
        signature = json.dumps([INVENTORY_CACHE_VERSION, str(Path(task_repository.db_path).resolve()),
                                [(row['id'], inventory_revision(task_repository, row)) for row in datasets],
                                task_repository.chart_mapping_settings(), inventory_polygon_sources(task_repository)],
                               sort_keys=True, default=str)
        digest = hashlib.sha256(signature.encode()).hexdigest()

        def build() -> dict[str, Any]:
            folder = cache_directory(task_repository)
            stored = folder / f'inventory-index-{digest}.pkl'
            if stored.is_file():
                try:
                    stored.touch()
                    return pd.read_pickle(stored)
                except Exception:
                    stored.unlink(missing_ok=True)
            with task_repository.connection() as connection:
                query, parameters, columns = prepare_inventory_query(task_repository, connection, datasets, {}, apply_filters=False)
                quote = task_repository._quote_identifier
                keys = [*INVENTORY_KEY_COLUMNS, 'Source_Dataset_ID', '__Inventory_Source_Row']
                frame = pd.read_sql_query(
                    f"SELECT {', '.join(quote(column) for column in keys)} FROM ({query})", connection, params=parameters,
                ) if query else pd.DataFrame(columns=keys)
            for column in INVENTORY_KEY_COLUMNS:
                frame[column] = frame[column].fillna('').astype(str)
            frame = frame.sort_values(['Source_Dataset_ID', '__Inventory_Source_Row'], kind='stable').reset_index(drop=True)
            index = {'frame': frame, 'columns': columns,
                     'names': {int(row['id']): str(row['file_name']) for row in datasets},
                     'sources': source_column_map(task_repository, datasets)}
            buffer = io.BytesIO()
            pd.to_pickle(index, buffer, protocol=5)
            write_cache_file(folder, stored.name, buffer.getvalue(), keep=3, pattern='inventory-index-*.pkl')
            return index

        return remember(f'inventory-index:{digest}', build)

    def source_column_map(task_repository, datasets) -> dict[str, dict[int, str]]:
        """Displayed column -> stored column per inventory, as in the combined query."""
        schemas = {int(row['id']): task_repository.list_dataset_row_columns(row['id']) for row in datasets}
        source_columns = list(dict.fromkeys(column for columns in schemas.values() for column in columns))
        used = {column.casefold() for column in [*INVENTORY_KEY_COLUMNS, 'Source_Dataset_ID', 'Source_Dataset_Name']}
        used |= {'__inventory_cell_id', '__inventory_source_row'}
        mapping: dict[str, dict[int, str]] = {}
        for source in source_columns:
            name = f'Source_{source}' if column_identity(source) in {column_identity(key) for key in INVENTORY_KEY_COLUMNS} else source
            while name.casefold() in used:
                name = f'Source_{name}'
            used.add(name.casefold())
            mapping[name] = {dataset_id: source for dataset_id, columns in schemas.items() if source in columns}
        return mapping

    def selected_inventory(task_repository, request: SitesRequest) -> tuple[dict[str, Any], pd.DataFrame]:
        """Inventory index rows matching the Analysis Selection (Operator, Vendor, Region, City, Technology)."""
        index = inventory_index(task_repository)
        frame = index['frame']
        normalise = inventory_filter_normalizer(task_repository)
        mask = pd.Series(True, index=frame.index)
        operator_groups = [{'canonical': name} for name in pd.unique(frame['Operator']) if name] if 'Operator' in frame else []
        operator_vendors = [*request.operator_vendors,
                            *(swap_vendor_operator(value, operator_groups) for value in request.vendor_operators)]
        for field, values in (('Operator', request.operators), ('Operator_Vendor', operator_vendors),
                              ('Vendor', request.vendors), ('Region', request.regions),
                              ('Cluster', request.clusters), ('City', request.cities)):
            if any(is_pattern(value) for value in values):
                # Patterns (VF*, -Lebara; see value_patterns).
                mask &= ValueSet(values).mask(frame[field].astype(str))
                continue
            wanted = {normalise(value, field) for value in values if str(value).strip()}
            if wanted:
                keys = {value: normalise(value, field) for value in pd.unique(frame[field])}
                mask &= frame[field].map(keys).isin(wanted)
        excluded = excluded_operators(task_repository)
        if excluded and 'Operator' in frame:
            # The operators the Operator Maps exclude are left out whatever the selection.
            left_out = {normalise(name, 'Operator') for name in excluded} | {name.casefold() for name in excluded}
            keys = {value: normalise(value, 'Operator') for value in pd.unique(frame['Operator'])}
            mask &= ~(frame['Operator'].map(keys).isin(left_out)
                      | frame['Operator'].astype(str).str.strip().str.casefold().isin(left_out))
        technologies = ['LTE', 'NR'] if request.technology == 'lte_nr' else ['NR'] if request.technology == 'nr' else ['LTE']
        mask &= frame['Technology'].isin(technologies)
        return index, frame.loc[mask]

    def observed_cells(task_repository, request: SitesRequest) -> dict[str, Any]:
        """One row per LTE cell (or site without cell identity) observed in the selected CDRs."""
        request = with_auto_cdrs(task_repository, request)
        samples_identity, _selected = samples_key(task_repository, request.datasets)
        selection = {key: value for key, value in request.model_dump().items()
                     if key in {'operators', 'operator_vendors', 'vendor_operators', 'vendors', 'campaigns', 'regions', 'clusters', 'cities', 'technology'}}
        digest = hashlib.sha256(json.dumps([OBSERVED_CACHE_VERSION, samples_identity, selection,
                                            inventory_polygon_sources(task_repository)], sort_keys=True, default=str).encode()).hexdigest()

        def build() -> dict[str, Any]:
            samples = load_samples(task_repository, request.datasets)
            filtered = filter_samples(samples, request)
            columns = list(OBSERVED_COLUMNS)
            if 'cells_technology' in filtered:
                # SA samples are served by NR cells (their traces say so); the others by LTE cells.
                is_nr = filtered['cells_technology'].eq('NR')
                filtered = filtered.loc[is_nr] if request.technology == 'nr' else filtered if request.technology == 'lte_nr' else filtered.loc[~is_nr]
            elif request.technology == 'nr':
                filtered = filtered.iloc[0:0]
            if filtered.empty:
                return {'frame': pd.DataFrame(columns=columns), 'columns': columns}
            fields = ['operator', 'vendor', 'region', 'city', 'campaign', 'kind', 'lte_band', 'latitude', 'longitude', 'lte_rsrp', 'lte_sinr',
                      *(['cells_technology'] if 'cells_technology' in filtered else [])]
            with_cells = filtered.loc[filtered['cells'].map(len) > 0, [*fields, 'cells']].explode('cells').rename(columns={'cells': 'cell'})
            sites_only = filtered.loc[(filtered['cells'].map(len) == 0) & (filtered['enodebs'].map(len) > 0), [*fields, 'enodebs']]
            sites_only = sites_only.explode('enodebs').rename(columns={'enodebs': 'site'})
            sites_only['cell'] = ''
            sites = {value: (str(enodeb) if (enodeb := lte_enodeb_from_eci(value)) is not None else '') for value in pd.unique(with_cells['cell'])}
            with_cells['site'] = with_cells['cell'].map(sites)
            if 'cells_technology' in with_cells:
                nr_rows = with_cells['cells_technology'].eq('NR')
                nodes = {value: (f'gNB {node}' if (node := nr_gnodeb(value)) is not None else '') for value in pd.unique(with_cells.loc[nr_rows, 'cell'])}
                with_cells.loc[nr_rows, 'site'] = with_cells.loc[nr_rows, 'cell'].map(nodes)
            rows = pd.concat([with_cells, sites_only], ignore_index=True)
            rows = rows.loc[(rows['cell'] != '') | (rows['site'] != '')]
            if rows.empty:
                return {'frame': pd.DataFrame(columns=columns), 'columns': columns}
            keys = ['operator', 'site', 'cell']
            # Vectorised per-cell aggregation: blanks become missing so 'first'
            # takes the first non-empty value of each cell.
            for field in ('vendor', 'region', 'city', 'lte_band'):
                rows[field] = rows[field].replace('', pd.NA)
            if 'cells_technology' not in rows:
                rows['cells_technology'] = 'LTE'
            rows['cells_technology'] = rows['cells_technology'].replace('', 'LTE')
            grouped = rows.groupby(keys, sort=True, dropna=False).agg(
                Technology=('cells_technology', 'first'),
                Vendor=('vendor', 'first'), Region=('region', 'first'), City=('city', 'first'), Band=('lte_band', 'first'),
                Samples=('kind', 'size'), Latitude=('latitude', 'mean'), Longitude=('longitude', 'mean'),
                RSRP_Mean=('lte_rsrp', 'mean'), SINR_Mean=('lte_sinr', 'mean'),
            )
            codes = {key: position for position, key in enumerate(grouped.index)}
            for name, field in (('CDR_Types', 'kind'), ('Campaigns', 'campaign')):
                # One linear pass instead of a Python call per cell.
                distinct = rows.loc[rows[field] != '', [*keys, field]].drop_duplicates().sort_values(field)
                values: list[list[str]] = [[] for _ in range(len(grouped))]
                for key, value in zip(zip(*(distinct[column] for column in keys)), distinct[field]):
                    values[codes[key]].append(str(value))
                grouped[name] = [', '.join(items) for items in values]
            grouped = grouped.reset_index().rename(columns={'operator': 'Operator', 'site': 'Site_ID', 'cell': 'Cell_ID'})
            for field in ('Vendor', 'Region', 'City', 'Band'):
                grouped[field] = grouped[field].astype(object).where(grouped[field].notna(), '')
            for column in ('Latitude', 'Longitude'):
                grouped[column] = grouped[column].round(6)
            for column in ('RSRP_Mean', 'SINR_Mean'):
                grouped[column] = grouped[column].round(2)
            grouped['Cluster'] = observed_clusters(task_repository, grouped)
            return {'frame': grouped[columns].reset_index(drop=True), 'columns': columns}

        def stored_build() -> dict[str, Any]:
            folder = cache_directory(task_repository)
            stored = folder / f'observed-{digest}.pkl'
            if stored.is_file():
                try:
                    stored.touch()
                    return pd.read_pickle(stored)
                except Exception:
                    stored.unlink(missing_ok=True)
            result = build()
            buffer = io.BytesIO()
            pd.to_pickle(result, buffer, protocol=5)
            write_cache_file(folder, stored.name, buffer.getvalue(), keep=12, pattern='observed-*.pkl')
            return result

        return remember(f'observed:{digest}', stored_build)

    def observed_clusters(task_repository, frame: pd.DataFrame) -> pd.Series:
        """Cluster of each observed cell's mean position, when Clusters polygons are imported."""
        sources = inventory_polygon_sources(task_repository)
        lookups = inventory_polygon_lookup(sources) if sources else {}
        if 'Cluster' not in lookups or frame.empty:
            return pd.Series('', index=frame.index)
        import shapely

        tree, names = lookups['Cluster']
        located = frame['Longitude'].notna() & frame['Latitude'].notna()
        result = pd.Series('', index=frame.index, dtype=object)
        if not located.any():
            return result
        # One bulk spatial query; the first matching polygon names each cell.
        points = shapely.points(frame.loc[located, 'Longitude'].to_numpy(), frame.loc[located, 'Latitude'].to_numpy())
        inputs, matches = tree.query(points, predicate='intersects')
        first: dict[int, int] = {}
        for position, match in zip(inputs.tolist(), matches.tolist()):
            first.setdefault(position, match)
        positions = frame.index[located]
        result.loc[positions] = [names[first[position]] if position in first else '' for position in range(len(positions))]
        return result

    def table_operators(task_repository, request: SitesRequest, frame: pd.DataFrame) -> dict[str, str]:
        """Operators with a table: those of the uploaded inventories, otherwise the CDR operators."""
        labels = operator_labels(task_repository)
        if not labels and request.source == 'observed':
            labels = {value: value for value in pd.unique(frame['Operator']) if str(value).strip()}
        mappings = {str(key).casefold(): str(value) for key, value in task_repository.list_operator_mappings().items()}
        # Patterns (VF*, Not Lebara) are matched as they are (see value_patterns).
        wanted = ValueSet(value if is_pattern(value) else mappings.get(value.casefold(), value)
                          for value in request.operators if str(value).strip())
        groups = task_repository.list_operator_mapping_groups()
        return {operator: label for operator, label in sorted(labels.items(), key=lambda item: operator_order_key(item[1], groups))
                if not wanted or wanted.accepts([operator, label])}

    def text_values(series: pd.Series) -> pd.Series:
        """Values as filters compare them: text, with blanks as ''."""
        values = series.astype(object).where(series.notna(), '')
        return values.map(lambda value: '' if value is None else (str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)).strip())

    def source_rowids(task_repository, index, column: str, values: list[str]) -> dict[int, set[int]]:
        """Inventory rows whose stored column holds one of the values, per inventory."""
        quote = task_repository._quote_identifier
        wanted = [str(value) for value in values]
        rowids: dict[int, set[int]] = {}
        with task_repository.connection() as connection:
            for dataset_id in index['names']:
                stored = index['sources'].get(column, {}).get(dataset_id)
                table = quote(task_repository.dataset_rows_table_name(dataset_id))
                if stored is None:
                    # An inventory without the column has it blank in every row.
                    rowids[dataset_id] = ({int(row[0]) for row in connection.execute(f'SELECT rowid FROM {table}')}
                                          if '' in wanted else set())
                    continue
                text = f"TRIM(COALESCE(CAST({quote(stored)} AS TEXT), ''))"
                placeholders = ', '.join('?' for _ in wanted)
                rows = connection.execute(f'SELECT rowid FROM {table} WHERE {text} IN ({placeholders})', wanted).fetchall()
                rowids[dataset_id] = {int(row[0]) for row in rows}
        return rowids

    def apply_column_filters(task_repository, request: SitesRequest, index, frame: pd.DataFrame, skip: str = '') -> pd.DataFrame:
        for column, values in request.filters.items():
            if column == skip or values is None:
                continue
            accepted = {str(value) for value in values}
            if column in frame.columns and not column.startswith('__'):
                frame = frame.loc[text_values(frame[column]).isin(accepted)]
            elif request.source == 'inventory' and column == 'Source_Dataset_Name':
                names = {dataset_id for dataset_id, name in index['names'].items() if name in accepted}
                frame = frame.loc[frame['Source_Dataset_ID'].isin(names)]
            elif request.source == 'inventory' and column in index['sources']:
                rowids = source_rowids(task_repository, index, column, sorted(accepted))
                keys = set((dataset_id, rowid) for dataset_id, ids in rowids.items() for rowid in ids)
                pairs = pd.Series(list(zip(frame['Source_Dataset_ID'].astype(int), frame['__Inventory_Source_Row'].astype(int))), index=frame.index)
                frame = frame.loc[pairs.isin(keys)]
        return frame

    def table_frame(task_repository, request: SitesRequest, skip_filter: str = '') -> tuple[dict[str, Any], pd.DataFrame, list[str]]:
        """Rows of one Sites/Cells table after the Analysis Selection and column filters."""
        if request.source == 'observed':
            observed = observed_cells(task_repository, request)
            index, frame, columns = observed, observed['frame'], observed['columns']
        else:
            index, frame = selected_inventory(task_repository, request)
            columns = index['columns']
        if request.operator:
            frame = frame.loc[frame['Operator'] == request.operator]
        return index, apply_column_filters(task_repository, request, index, frame, skip_filter), columns

    def inventory_rows(task_repository, index, frame: pd.DataFrame, columns: list[str]) -> list[list[Any]]:
        """Complete rows of the given index entries, in index order."""
        quote = task_repository._quote_identifier
        stored: dict[tuple[int, int], dict[str, Any]] = {}
        with task_repository.connection() as connection:
            for dataset_id, part in frame.groupby('Source_Dataset_ID', sort=False):
                dataset_id = int(dataset_id)
                table = quote(task_repository.dataset_rows_table_name(dataset_id))
                fields = {name: sources[dataset_id] for name, sources in index['sources'].items() if dataset_id in sources}
                rowids = [int(value) for value in part['__Inventory_Source_Row']]
                for start in range(0, len(rowids), 500):
                    chunk = rowids[start:start + 500]
                    select = ', '.join(['rowid', *(quote(source) for source in fields.values())])
                    for row in connection.execute(f"SELECT {select} FROM {table} WHERE rowid IN ({', '.join('?' for _ in chunk)})", chunk):
                        stored[(dataset_id, int(row[0]))] = dict(zip(fields, row[1:]))
        rows = []
        for record in frame.to_dict('records'):
            dataset_id, rowid = int(record['Source_Dataset_ID']), int(record['__Inventory_Source_Row'])
            values = stored.get((dataset_id, rowid), {})
            row = []
            for column in columns:
                if column == 'Source_Dataset_Name':
                    row.append(index['names'].get(dataset_id, ''))
                elif column in record and not column.startswith('__'):
                    row.append(record[column])
                else:
                    row.append(values.get(column))
            rows.append(row)
        return rows

    def table_page(task_repository, request: SitesRequest, label: str = '') -> dict[str, Any]:
        index, frame, columns = table_frame(task_repository, request)
        total = len(frame)
        page = min(max(request.page, 0), max(0, (total - 1) // 50))
        visible = frame.iloc[page * 50:(page + 1) * 50]
        if request.source == 'inventory':
            rows = inventory_rows(task_repository, index, visible, columns)
            key_columns = list(INVENTORY_KEY_COLUMNS)
        else:
            rows = visible.astype(object).where(visible.notna(), None).values.tolist()
            key_columns = ['Operator', 'Site_ID', 'Cell_ID']
        return {'operator': request.operator, 'operator_label': label or request.operator, 'source': request.source,
                'columns': columns, 'key_columns': key_columns, 'rows': rows, 'total_rows': total, 'page': page,
                'page_size': 50, 'filters': {column: values for column, values in request.filters.items() if values is not None}}

    def table_suffix(labels: list[str]) -> str:
        """CSV suffix: _VF for Vodafone, _3 for Three and _VF_3 for both."""
        codes = []
        for label in labels:
            text = str(label).strip()
            code = {'vodafone': 'VF', 'vf': 'VF', 'vf_uk': 'VF', 'three': '3', '3': '3', '3uk': '3'}.get(text.casefold())
            codes.append(code or re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_'))
        ordered = sorted(dict.fromkeys(code for code in codes if code), key=lambda code: (code != 'VF', code != '3', code))
        return ('_' + '_'.join(ordered)) if ordered else ''

    @app.post('/api/network-insights/sites/tables')
    def network_insights_site_tables(request: SitesRequest, user=Depends(insights_user)):
        task_repository = bound_repository()
        _index, frame, _columns = table_frame(task_repository, SitesRequest(**{**request.model_dump(), 'operator': '', 'filters': {}}))
        labels = table_operators(task_repository, request, frame)
        tables = [table_page(task_repository, SitesRequest(**{**request.model_dump(), 'operator': operator, 'page': 0, 'filters': {}}), label)
                  for operator, label in labels.items()]
        return {'source': request.source, 'tables': tables}

    @app.post('/api/network-insights/sites/page')
    def network_insights_site_page(request: SitesRequest, user=Depends(insights_user)):
        task_repository = bound_repository()
        labels = operator_labels(task_repository)
        return table_page(task_repository, request, labels.get(request.operator, request.operator))

    @app.post('/api/network-insights/sites/values')
    def network_insights_site_values(request: SitesRequest, user=Depends(insights_user)):
        """Values of one column under every other filter, for its Excel-style filter."""
        task_repository = bound_repository()
        index, frame, columns = table_frame(task_repository, request, skip_filter=request.column)
        if request.column not in columns:
            raise HTTPException(400, 'Choose a column of the table.')
        if request.source == 'inventory' and request.column not in frame.columns and request.column != 'Source_Dataset_Name':
            counts = Counter()
            quote = task_repository._quote_identifier
            with task_repository.connection() as connection:
                for dataset_id, part in frame.groupby('Source_Dataset_ID', sort=False):
                    stored = index['sources'].get(request.column, {}).get(int(dataset_id))
                    if stored is None:
                        counts[''] += len(part)
                        continue
                    table = quote(task_repository.dataset_rows_table_name(int(dataset_id)))
                    rowids = json.dumps([int(value) for value in part['__Inventory_Source_Row']])
                    text = f"TRIM(COALESCE(CAST({quote(stored)} AS TEXT), ''))"
                    for value, count in connection.execute(
                        f'SELECT {text}, COUNT(*) FROM {table} WHERE rowid IN (SELECT value FROM json_each(?)) GROUP BY 1', [rowids],
                    ):
                        counts[str(value)] += int(count)
        elif request.column == 'Source_Dataset_Name':
            counts = Counter({index['names'].get(int(key), ''): int(value) for key, value in frame['Source_Dataset_ID'].value_counts().items()})
        else:
            counts = Counter(text_values(frame[request.column]).value_counts().to_dict())
        search = request.search.strip().casefold()
        values = sorted((value for value in counts if not search or search in value.casefold()), key=lambda value: (value == '', value.casefold()))
        return {'column': request.column, 'values': [{'value': value, 'count': counts[value]} for value in values[:2000]],
                'truncated': len(values) > 2000, 'selected': request.filters.get(request.column)}

    @app.post('/api/network-insights/sites/export')
    def network_insights_site_export(request: SitesRequest, user=Depends(insights_user)):
        from tempfile import NamedTemporaryFile

        from fastapi.responses import FileResponse
        from starlette.background import BackgroundTask

        task_repository = bound_repository()
        index, frame, columns = table_frame(task_repository, request)
        labels = operator_labels(task_repository) or {value: value for value in pd.unique(frame['Operator'])}
        included = [request.operator] if request.operator else list(dict.fromkeys(str(value) for value in frame['Operator']))
        suffix = table_suffix([labels.get(operator, operator) for operator in included] or list(labels.values()))
        name = ('cdr-observed-sites-cells' if request.source == 'observed' else 'site-cell-inventory') + f'{suffix}.csv'
        with NamedTemporaryFile(mode='w', newline='', encoding='utf-8', suffix='.csv', delete=False) as output:
            destination = Path(output.name)
            try:
                writer = csv.writer(output)
                writer.writerow(columns)
                for start in range(0, len(frame), 5000):
                    chunk = frame.iloc[start:start + 5000]
                    rows = (inventory_rows(task_repository, index, chunk, columns) if request.source == 'inventory'
                            else chunk.astype(object).where(chunk.notna(), None).values.tolist())
                    writer.writerows(['' if value is None else value for value in row] for row in rows)
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        source = 'observed' if request.source == 'observed' else 'inventory'
        task_repository.try_add_log(user.username, f'export_network_insights_{source}_sites', json.dumps({
            'file': name, 'rows': len(frame),
        }))
        return FileResponse(destination, media_type='text/csv', filename=name,
                            background=BackgroundTask(destination.unlink, missing_ok=True))

    # Earlier routes of the complete inventory tables answer through the same tables.
    @app.post('/api/network-insights/inventory/tables')
    def network_insights_inventory_tables(request: AnalysisRequest, user=Depends(insights_user)):
        tables = network_insights_site_tables(SitesRequest(**request.model_dump(), source='inventory'), user)['tables']
        return {'inventories': tables}

    @app.post('/api/network-insights/inventory')
    def network_insights_combined_inventory(request: AnalysisRequest, page: int = Query(0, ge=0),
                                          operator: str = '', user=Depends(insights_user)):
        return network_insights_site_page(SitesRequest(**request.model_dump(), source='inventory', page=page, operator=operator), user)

    @app.post('/api/network-insights/inventory/export')
    def network_insights_combined_inventory_export(request: AnalysisRequest, operator: str = '', user=Depends(insights_user)):
        return network_insights_site_export(SitesRequest(**request.model_dump(), source='inventory', operator=operator), user)

    def inventory_records(task_repository, dataset: dict[str, Any], page: int = 0) -> dict[str, Any]:
        """Read a bounded page without discarding inventory columns or unmatched rows."""
        columns = task_repository.list_dataset_row_columns(dataset['id'])
        total = task_repository.dataset_row_count(dataset['id'])
        page = min(page, max(0, (total - 1) // 50))
        frame, total, _values = task_repository.load_dataset_preview_page(
            dataset['id'], columns, {}, page, 50,
        )
        return {**dataset, 'columns': columns, 'rows': json.loads(frame.to_json(orient='values', double_precision=15)),
                'total_rows': total, 'page': page, 'page_size': 50}

    @app.get('/api/network-insights/inventory/{dataset_id}')
    def network_insights_inventory(dataset_id: int, page: int = Query(0, ge=0),
                                   download: bool = False, user=Depends(insights_user)):
        task_repository = bound_repository()
        dataset = next((row for row in inventory_datasets(task_repository) if row['id'] == dataset_id), None)
        if dataset is None:
            raise HTTPException(404, 'Ready Vodafone or Three inventory not found in the active workspace.')
        if download:
            columns = task_repository.list_dataset_row_columns(dataset_id)
            task_repository.try_add_log(user.username, 'export_network_insights_inventory', json.dumps({
                'dataset_id': dataset_id, 'operator': dataset['operator'],
            }))
            return StreamingResponse(
                task_repository.stream_dataset_preview_csv(dataset_id, columns, {}),
                media_type='text/csv',
                headers={'Content-Disposition': f'attachment; filename="site-inventory{table_suffix([dataset["operator"]])}.csv"'},
            )
        return inventory_records(task_repository, dataset, page)

    @app.get('/api/network-insights/deployment/{dataset_id}/export')
    def network_insights_deployment_export(dataset_id: int, group: str = 'scenario', user=Depends(insights_user)):
        if group not in DEPLOYMENT_GROUPINGS:
            raise HTTPException(400, 'Choose a supported network deployment grouping.')
        task_repository = bound_repository()
        require_cluster_dataset(group, task_repository)
        dataset = next((row for row in inventory_datasets(task_repository) if row['id'] == dataset_id), None)
        if dataset is None:
            raise HTTPException(404, 'Ready Vodafone or Three inventory not found in the active workspace.')
        summary = inventory_summary(task_repository, dataset, group)
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow([DEPLOYMENT_GROUPINGS[group] if group in summary['available_groups'] else 'Inventory',
                         'Sites', 'Cells'])
        writer.writerows((row['group'], row['sites'], row['cells']) for row in summary['rows'])
        task_repository.try_add_log(user.username, 'export_network_insights_deployment', json.dumps({
            'group': group, 'dataset_id': dataset_id, 'operator': dataset['operator'],
        }))
        return StreamingResponse(
            iter([output.getvalue()]), media_type='text/csv',
            headers={'Content-Disposition': f'attachment; filename="network-deployment-{group}{table_suffix([dataset["operator"]])}.csv"'},
        )

    @app.get('/api/network-insights/deployment/export-all')
    def network_insights_deployment_export_all(group: str = 'scenario', user=Depends(insights_user)):
        if group not in DEPLOYMENT_GROUPINGS:
            raise HTTPException(400, 'Choose a supported network deployment grouping.')
        deployment = deployment_summary(group)
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['Operator', 'Source_Dataset_ID', 'Source_Dataset_Name', DEPLOYMENT_GROUPINGS[group], 'Sites', 'Cells'])
        for inventory in deployment['inventories']:
            writer.writerows((inventory['operator'], inventory['id'], inventory['file_name'],
                              row['group'], row['sites'], row['cells']) for row in inventory['rows'])
        suffix = table_suffix([inventory['operator'] for inventory in deployment['inventories']])
        bound_repository().try_add_log(user.username, 'export_network_insights_deployment', json.dumps({
            'group': group, 'operators': [inventory['operator'] for inventory in deployment['inventories']],
        }))
        return StreamingResponse(iter([output.getvalue()]), media_type='text/csv',
                                 headers={'Content-Disposition': f'attachment; filename="network-deployment-{group}{suffix}.csv"'})

    @app.get('/api/network-insights/deployment')
    def network_insights_deployment(group: str = 'scenario', user=Depends(insights_user)):
        return deployment_summary(group)

    def inventory_revision(task_repository, dataset: dict[str, Any]) -> tuple:
        """Profile revision plus row count and last row, so any row change refreshes caches."""
        table = task_repository._quote_identifier(task_repository.dataset_rows_table_name(dataset['id']))
        try:
            with task_repository.connection() as connection:
                count, last = connection.execute(f'SELECT COUNT(*), MAX(rowid) FROM {table}').fetchone()
        except sqlite3.OperationalError:
            count, last = 0, 0
        columns = tuple(task_repository.list_dataset_row_columns(dataset['id']))
        return dataset['updated_at'], int(count or 0), int(last or 0), columns

    def cached_inventory_projection(task_repository, dataset: dict[str, Any]) -> dict[str, Any]:
        """An inventory's identifiers and grouping fields, kept in memory and on disk."""
        key = (str(Path(task_repository.db_path).resolve()), dataset['id'],
               dataset['file_name'], inventory_revision(task_repository, dataset), inventory_polygon_sources(task_repository))
        with inventory_cache_lock:
            cached = inventory_cache.get(key)
            if cached is not None:
                inventory_cache.move_to_end(key)
                return cached
        folder = cache_directory(task_repository)
        digest = hashlib.sha256(json.dumps([INVENTORY_CACHE_VERSION, *key], default=str).encode()).hexdigest()
        stored = folder / f'inventory-{digest}.pkl'
        frame = None
        if stored.is_file():
            try:
                frame = pd.read_pickle(stored)
                stored.touch()
            except Exception:
                stored.unlink(missing_ok=True)
        if frame is None:
            frame = inventory_projection(task_repository, dataset)
            buffer = io.BytesIO()
            frame.to_pickle(buffer, protocol=5)
            write_cache_file(folder, stored.name, buffer.getvalue(), keep=8, pattern='inventory-*.pkl')
        with inventory_cache_lock:
            cached = inventory_cache.setdefault(key, {'frame': frame, 'summaries': {}})
            inventory_cache.move_to_end(key)
            while len(inventory_cache) > 6:
                inventory_cache.popitem(last=False)
        return cached

    def deployment_summary(group: str = 'scenario') -> dict[str, Any]:
        task_repository = bound_repository()
        require_cluster_dataset(group, task_repository)
        results = []
        for dataset in inventory_datasets(task_repository):
            if group == 'inventory':
                results.append(inventory_records(task_repository, dataset))
                continue
            cached = cached_inventory_projection(task_repository, dataset)
            with inventory_cache_lock:
                grouping = group if group in DEPLOYMENT_GROUPINGS else None
                if grouping not in cached['summaries']:
                    cached['summaries'][grouping] = inventory_summary(
                        task_repository, dataset, grouping, frame=cached['frame'])
                summary = cached['summaries'][grouping]
            results.append({**dataset, **summary})
        return {'group': group, 'group_label': DEPLOYMENT_GROUPINGS.get(group, 'All'), 'inventories': results}

    def cluster_inventory_summary() -> dict[str, Any]:
        """Count inventory identifiers per operator, deduplicating overlapping uploads."""
        task_repository = bound_repository()
        frames: dict[str, list[pd.DataFrame]] = {}
        for dataset in inventory_datasets(task_repository):
            frames.setdefault(dataset['operator'], []).append(cached_inventory_projection(task_repository, dataset)['frame'])
        rows = []
        groups = task_repository.list_operator_mapping_groups()
        for operator, sources in sorted(frames.items(), key=lambda item: operator_order_key(item[0], groups)):
            frame = pd.concat(sources, ignore_index=True)
            totals = inventory_summary(task_repository, {}, None, frame=frame)['totals']
            if totals:
                rows.append({'operator': operator, **totals})
        return {'rows': rows}

    @app.get('/api/network-insights/cluster-inventories')
    def network_insights_cluster_inventories(user=Depends(insights_user)):
        return cluster_inventory_summary()

    def write_summary(selection: dict[str, Any], export_kind: str, destination: Path,
                      components: list[str] | None = None, compose: bool = True, theme: str | None = None) -> dict[str, Any]:
        """Write the Summary Network Insights (PowerPoint or Word) for a saved or current selection.

        Without CDRs of its own, a selection analyses those of its NR Mode and Campaigns. ``components`` keeps only
        those charts and tables in the PowerPoint. Both formats are composed as the Network Insights section of a
        Bundle Report Template; without ``compose`` (the Bundle Report Template itself), the PowerPoint is the deck of the module.
        ``theme`` (else that of the selection, else NetCheck) colours its charts and tables. Returns the selection
        description used in the document.
        """
        with use_theme(normalize_theme(theme or (selection or {}).get('theme'))):
            return write_themed_summary(selection, export_kind, destination, components, compose)

    def write_themed_summary(selection: dict[str, Any], export_kind: str, destination: Path,
                             components: list[str] | None, compose: bool) -> dict[str, Any]:
        from src.modules.cdr_reporting import _render_dashboard_payload
        from src.modules.bundle_report_templates import module_document
        from src.modules.network_insights_export import export_network_insights_powerpoint

        task_repository = bound_repository()
        available = ready_cdrs(task_repository)
        request = summary_request(task_repository, selection)
        # An analysis already made with the same selection and inputs is used as it is.
        analysis = json.loads(stored_analysis(task_repository, request))
        names = {row['id']: row['file_name'] for row in available}
        description = {
            **request.model_dump(), 'technology_label': analysis['technology_label'], 'group_label': analysis['group_label'],
            'nr_mode': str((selection or {}).get('nr_mode') or '').upper(),
            'dataset_names': [names[dataset_id] for kind in NETWORK_INSIGHTS_KINDS for dataset_id in request.datasets.get(kind, []) if dataset_id in names],
        }
        # As on the page, the grouped Network Deployment views come from the inventory snapshot.
        snapshot = snapshot_payload(task_repository, request.snapshot)
        groupings = []
        for group in SUMMARY_DEPLOYMENT_GROUPS:
            grouped = snapshot_payload(task_repository, request.snapshot, group)
            # Each table is named after its network and the date of its snapshot (not its long file name).
            sources = {item['family']: str(item['snapshot_date'] or item['file_name']) for item in grouped['selection']}
            groupings.append({'group': group, 'group_label': grouped['group_label'], 'inventories': [
                {'operator': table['operator'], 'file_name': sources.get(table['family'], ''), 'rows': table['rows'], 'totals': table['totals']}
                for table in grouped['deployment']]})
        deployment = {'groupings': groupings, 'cluster_inventories': cluster_inventory_summary(), 'snapshot': snapshot,
                      'nr_duplex': nr_duplex_payload(task_repository, NrDuplexRequest.model_validate(request.model_dump()))}
        # The CDFs and maps in the font and colours of the theme (on the dark cards of a dark theme).
        chart_style = dashboard_chart_style()
        render = lambda payload, width, height: _render_dashboard_payload({**payload, 'style': chart_style}, width=width, height=height)[0]
        chosen = {} if components is None else {'components': components}
        if not compose:
            export_network_insights_powerpoint(destination, analysis, deployment, description, render, **chosen)
            return description
        # The deck of the module has its own name, so it never replaces a document written next to it.
        deck = destination.with_name(f'.{destination.stem}.{uuid4().hex}.pptx')
        try:
            export_network_insights_powerpoint(deck, analysis, deployment, description, render, **chosen)
            destination.write_bytes(module_document('network_insights', deck.read_bytes(), export_kind, 'Network Insights'))
        finally:
            deck.unlink(missing_ok=True)
        return description

    def summary_request(task_repository, selection: dict[str, Any]) -> AnalysisRequest:
        """The analysis of a summary: the selection with its CDRs, drawing the maps of every group."""
        request = with_auto_cdrs(task_repository, AnalysisRequest.model_validate(selection or {}))
        request.map_all_groups = True
        return request

    def summary_key(selection: dict[str, Any]) -> str:
        """Identity of the summary of a selection: its analysis and every input it reads (such as the CDRs and the
        inventory), so a Bundle Report Template knows when its Network Insights section is still the same."""
        task_repository = bound_repository()
        return analysis_key(task_repository, summary_request(task_repository, selection))

    core.write_network_insights_summary = write_summary
    core.network_insights_summary_key = summary_key

    @app.post('/api/network-insights/export/{export_kind}')
    def network_insights_export(export_kind: str, request: AnalysisRequest, theme: str = Query(''), user=Depends(insights_user)):
        from datetime import datetime

        from fastapi.responses import FileResponse

        if export_kind not in {'word', 'powerpoint'}:
            raise HTTPException(404, 'Unsupported export type.')
        suffix = 'docx' if export_kind == 'word' else 'pptx'
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        destination = core.safe_join(module_output_dir(core.settings.output_dir, NETWORK_INSIGHTS_FOLDER, create=True),
                                     f'{stamp}_summary_network_insights.{suffix}')
        # The theme of the page, else the one the user chose last.
        theme = normalize_theme(theme) if theme else load_user_theme(bound_repository(), user.username, THEME_MODULE)
        try:
            write_summary(request.model_dump(), export_kind, destination, theme=theme)
        except HTTPException:
            raise
        except Exception as exc:
            # The reason reaches the page's error dialog and the server console.
            import traceback
            traceback.print_exc()
            raise HTTPException(500, f'The {export_kind} export failed: {exc}') from exc
        core.repository.try_add_log(user.username, f'export_network_insights_{export_kind}',
                                    json.dumps({'file': destination.name, 'theme': theme}))
        media_type = ('application/vnd.openxmlformats-officedocument.wordprocessingml.document' if export_kind == 'word'
                      else 'application/vnd.openxmlformats-officedocument.presentationml.presentation')
        return FileResponse(destination, filename=f'{stamp} - Network Insights - Summary.{suffix}', media_type=media_type)

    @app.get('/api/network-insights/spectrum')
    def network_insights_spectrum(user=Depends(insights_user)):
        holdings = load_spectrum_holdings(bound_repository())
        return {'holdings': holdings, 'summary': licensed_spectrum_summary(holdings)}

    @app.put('/api/network-insights/spectrum')
    def network_insights_spectrum_save(request: SpectrumRequest, user=Depends(editor_user)):
        try:
            holdings = normalise_spectrum_holdings(request.holdings)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        task_repository = bound_repository()
        save_spectrum_holdings(task_repository, holdings)
        task_repository.try_add_log(user.username, 'network_spectrum_holdings_saved', json.dumps({'rows': len(holdings)}))
        return {'holdings': holdings, 'summary': licensed_spectrum_summary(holdings)}

    @app.post('/workspace-config/spectrum-holdings/save')
    def workspace_spectrum_holdings_save(holdings_csv: str = Form(''), user=Depends(core.config_editor_user)):
        def redirect(key: str, message: str) -> RedirectResponse:
            return RedirectResponse(f'/workspace-config?{urlencode({key: message})}#spectrum-holdings', status_code=303)

        if not core.active_workspace:
            return redirect('spectrum_holdings_error', 'Open a workspace before editing Spectrum Holdings.')
        try:
            holdings = parse_spectrum_csv(holdings_csv)
        except ValueError as exc:
            return redirect('spectrum_holdings_error', str(exc))
        task_repository = bound_repository()
        save_spectrum_holdings(task_repository, holdings)
        task_repository.try_add_log(user.username, 'network_spectrum_holdings_saved', json.dumps({'rows': len(holdings)}))
        return redirect('spectrum_holdings_notice', f'Spectrum Holdings saved ({len(holdings)} rows).')


def load_spectrum_holdings(task_repository: Any) -> list[dict[str, Any]]:
    """Return the validated licensed spectrum holdings of a workspace."""
    import json

    try:
        rows = json.loads(task_repository.get_workspace_state(SPECTRUM_HOLDINGS_STATE_KEY) or '[]')
        return normalise_spectrum_holdings(rows if isinstance(rows, list) else [])
    except (TypeError, ValueError):
        return []


def save_spectrum_holdings(task_repository: Any, holdings: list[dict[str, Any]]) -> None:
    import json

    task_repository.set_workspace_state(SPECTRUM_HOLDINGS_STATE_KEY, json.dumps(normalise_spectrum_holdings(holdings), ensure_ascii=False))
