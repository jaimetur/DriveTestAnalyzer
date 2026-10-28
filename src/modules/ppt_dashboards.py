"""Workspace dashboard definitions and shared-table, template-driven previews."""
from __future__ import annotations

import json
import html
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from collections import OrderedDict, defaultdict
from contextlib import contextmanager, nullcontext
from itertools import count
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from time import monotonic
from pathlib import Path
from threading import Condition, Event, Lock, RLock, Thread
from types import SimpleNamespace
from typing import Any, Literal
from uuid import uuid4

import pandas as pd
from src.modules.column_names import campaign_sort_key, column_identity, compact_campaign_value, sort_vendor_values, vendor_filter_column, vendor_filter_value, vendor_filter_values, vendor_match_values
from src.modules import report_structure
from src.modules.deletion_rights import (
    PPT_DASHBOARDS, can_delete, creator_of, creators, deletion_refusal, forget_creator, record_creator,
)
from src.modules.scoring_themes import THEMES, dashboard_chart_style, load_user_theme, normalize_theme, save_user_theme, themes_payload, use_theme
from src.modules.theme_titles import style_title
from src.modules.value_maps import ValueMapper, field_kind
from src.modules.cdr_auto_selection import (
    LATEST_CAMPAIGN, LATEST_TWO_CAMPAIGNS, campaign_identity, campaign_presets, campaign_values, cdr_campaigns, candidate_cdrs, describe_cdrs,
    latest_campaigns, resolve_campaign_filter, resolve_cdrs, sort_campaigns,
)
from src.modules.cdr_facets import FILTER_FIELDS as CASCADING_FILTER_FIELDS, cascading_options
from src.modules.nr_mode import NR_MODE_FIELD, NR_MODES, NSA_VS_SA, dataset_nr_mode, nr_modes_of
from src.modules.report_template_modes import (
    DASHBOARD_NR_MODE_LABELS, chart_filter_nr_modes, dashboard_nr_mode_value, entry_for_nr_mode, migrate_dashboard_definition,
    missing_nr_mode_fields, missing_nr_mode_note,
)
from src.modules.output_layout import DASHBOARDS_FOLDER, module_output_dir
from fastapi import BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field, model_validator
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.util import Inches, Pt
from starlette.background import BackgroundTask

from src.modules.cdr_reporting import (
    BOTH_NR_MODES_ATTR, _catalog_spec, _clear_commentary, _clear_end_slide, _layout_chart_frames, _legend_dimensions, _named_slide_layout,
    _remove_all_slides, _remove_template_chart_placeholders, _render_dashboard_payload,
    _set_commentary, _set_slide_header, _set_structural_slide_text, catalog_chart_payload,
    catalog_kpi_fields, expand_dynamic_layouts, entry_dynamic_fields, dynamic_chart_title, _normalise_operator_label, _normalise_vendor, prepare_multivendor_catalog_entry,
    ensure_vendor_group, normalise_operator_aliases, parse_catalog_filters,
    parse_catalog_grouping,
    prepare_catalog_chart_preview_frame, render_catalog_chart_preview, render_unavailable_source_chart,
    split_calculated_dimension_aliases, chart_title_parts, _select_dynamic_chart_frame,
)
from src.modules.report_layouts import canonical_layout_name, compact_grid_layout, grid_layout_name

from src.modules import cdr_store
from src.modules.dashboard_column_cache import (
    CacheSource, ColumnCache, Segment, SelectionTerms, StaleSegment, build_from_copies, count_rows, default_memory_bytes,
    read_frame,
)
from src.modules.rf_catalog_source import RF_CATALOG_FIELDS, rf_source_columns, rf_union_source
from src.modules.repository import Repository
from src.modules.cdr_report_filenames import build_cdr_report_filename
from src.modules.runtime_config import ignore_event_time_filtering
from src.modules.ingestion import apply_operator_mappings
from src.modules.value_patterns import ValueSet, is_pattern
from src.modules.operator_roles import (
    drop_excluded_operators, excluded_operators, focus_operators, out_of_scope_operators, out_of_scope_pairs,
)
from src.modules import comment_writers, dashboard_comments

KINDS = ('data', 'voice', 'speech')


def existing_dataset_selection(definition: Any, dataset_kinds: dict[int, str]) -> Any:
    """A Dashboard without the CDRs that are not in its workspace with their type (deleted, or from another workspace).

    When none of its chosen CDRs is left, the Dashboard uses the latest CDRs again, like a Dashboard without CDRs.
    """
    if not isinstance(definition, dict) or not isinstance(definition.get('datasets'), dict):
        return definition
    stored = definition['datasets']
    kept: dict[str, list] = {}
    for kind, ids in stored.items():
        values = ids if isinstance(ids, list) else []
        kept[kind] = [value for value in values if _dataset_id(value) is not None and dataset_kinds.get(_dataset_id(value)) == kind]
    if all(kept.get(kind) == (ids if isinstance(ids, list) else []) for kind, ids in stored.items()):
        return definition
    if any(kept.values()):
        return {**definition, 'datasets': kept}
    return {key: value for key, value in definition.items() if key != 'datasets'}


def _dataset_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
STATE_KEY = 'ppt_dashboards_v2'
LEGACY_STATE_KEY = 'ppt_dashboard_sets_v1'
DEFAULT_FILTERS_MIGRATION_KEY = 'ppt_dashboard_default_filters_v6'
# The Main Cities choice of a City filter: the Main Cities of the workspace whenever the Dashboard is used, so a change
# of the Main Cities in Workspace Config reaches the Dashboards saved with it.
MAIN_CITIES = '@main-cities'
# Dashboards saved before kept the Main Cities of that moment: once per workspace, a City filter of exactly the current
# Main Cities becomes the Main Cities choice.
MAIN_CITIES_MIGRATION_KEY = 'ppt_dashboard_main_cities_reference_v1'
DASHBOARD_PPT_JOBS_TABLE = 'dashboard_ppt_jobs'
# The colour theme of PPT Dashboards: per user in each workspace, as in the other themed modules.
DASHBOARD_THEME_MODULE = 'ppt_dashboards'


def dashboard_viewer_tokens(theme_name: str) -> dict[str, str]:
    """The CSS variables of the Dashboard viewer in a theme, set on the viewer and changed at once with the theme: the
    slide title and subtitle in the theme's title style (as on the content slides of the Dashboard PPTs, the part that
    tells the slide apart in its focus style) and the chart cards in its rules."""
    from src.modules.scoring_themes import get_theme
    from src.modules.theme_titles import title_style
    theme = get_theme(theme_name)
    style = title_style(theme)
    family = lambda name: f'"{name}", {theme["font"]}' if name else theme['font']
    weight = lambda bold: '700' if bold else '400'
    return {'--ds-title-font': family(style.get('font')), '--ds-title-color': style['color'],
            '--ds-title-weight': weight(style.get('bold')), '--ds-title-transform': 'uppercase' if style.get('caps') else 'none',
            '--ds-title-style': 'italic' if style.get('italic') else 'normal',
            '--ds-title-focus-font': family(style.get('focus_font') or style.get('font')),
            '--ds-title-focus-color': style['focus_color'], '--ds-title-focus-weight': weight(style.get('focus_bold', style.get('bold'))),
            '--ds-title-focus-style': 'italic' if style.get('focus_italic', style.get('italic')) else 'normal',
            '--ds-subtitle-font': family(style.get('subtitle_font') or style.get('font')),
            '--ds-subtitle-color': style['subtitle_color'], '--ds-subtitle-weight': weight(style.get('subtitle_bold')),
            '--ds-subtitle-style': 'italic' if style.get('subtitle_italic') else 'normal',
            '--ds-card-line': theme['line'], '--ds-accent': theme['title_accent']}


class DashboardDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    template: str = Field(min_length=1)
    # The NR Mode of the CDRs the Dashboard reads, part of its selection: its template serves any NR Mode. NSA+SA
    # (NSA & SA) reads the CDRs of both, whose rows keep the NR Mode of their CDR.
    nr_mode: Literal['NSA', 'SA', 'NSA+SA'] = 'NSA'
    # With NSA & SA, the Campaign filter of the SA CDRs (the Campaign filter chooses the NSA ones); empty, the
    # Campaign filter chooses both. Each has its Latest presets, resolved in its own NR Mode.
    sa_campaigns: list[str] = Field(default_factory=list)
    scope: Literal['single', 'multivendor'] = 'single'
    vendor_comparison: Literal['operator_vendor', 'vendor_only'] = 'operator_vendor'
    datasets: dict[str, list[int]] = Field(default_factory=dict)
    filters: dict[str, list[str]] = Field(default_factory=dict)
    custom_fields: list[str] = Field(default_factory=list)
    hidden_filters: list[str] = Field(default_factory=list)
    slide_comments: dict[str, list[str]] = Field(default_factory=dict)
    # Per slide, the comments added from Generate comments: {'generated': [their texts], 'engine', 'model',
    # 'generated_at', 'generated_by', 'selection': the selection (campaigns, filters and CDRs) they were written for}.
    slide_comment_meta: dict[str, dict[str, Any]] = Field(default_factory=dict)
    date_from: date | Literal['Oldest'] | None = 'Oldest'
    date_to: date | Literal['Newest'] | None = 'Newest'
    # The CDRs follow the NR Mode and the Campaign filter (see ``cdr_auto_selection``); Dashboards saved
    # before (without it) chose their CDRs by hand and are migrated once (``migrate_auto_cdrs``).
    auto_cdrs: bool = False

    @model_validator(mode='before')
    @classmethod
    def without_template_nr_mode(cls, value: Any) -> Any:
        """A Dashboard saved, exported or sent with the NR Mode of before (technology, template_technology)."""
        if isinstance(value, dict):
            value = migrate_dashboard_definition(value)
            if isinstance(value, dict) and value.get('nr_mode') is not None:
                value = {**value, 'nr_mode': dashboard_nr_mode_value(value['nr_mode'])}
        return value


class DashboardThemeRequest(BaseModel):
    theme: str


AUTO_COMMENT_MODES = ('off', 'empty', 'generated', 'all')


class DashboardPptExportRequest(BaseModel):
    definition: DashboardDefinition | None = None
    # Auto comments: write generated comments into the PPT (not into the Dashboard) on the slides without comments,
    # in place of the generated ones or in place of every comment.
    auto_comments: Literal['off', 'empty', 'generated', 'all'] = 'off'
    # Their writer (empty: the default one of Super Admin).
    auto_comments_engine: str = ''
    preparation_token: str | None = None
    # Legend entries hidden in the viewer: {"dashboard": {label: hidden},
    # "charts": {chart key: {label: hidden}}}; the PPT shows them hidden too.
    legend_visibility: dict[str, object] | None = None
    selected_operators: list[str] | None = None
    selected_vendors: list[str] | None = None
    selected_regions: list[str] | None = None
    selected_cities: list[str] | None = None


class DashboardFilterOptionsRequest(BaseModel):
    definition: DashboardDefinition
    field: str = Field(min_length=1, max_length=255)


class DashboardFilterOptionsBatchRequest(BaseModel):
    definition: DashboardDefinition
    fields: list[str] = Field(min_length=1, max_length=64)


class DashboardChartFilterPreviewRequest(BaseModel):
    filters: str = ''
    chart_title: str | None = None
    cdr_source: str | None = None
    dataset_ids: list[int] | str | None = None
    kpi: str | None = None
    chart_type: str | None = None
    rows_split: str | None = None
    columns_split: str | None = None
    legend: str | None = None
    legend_position: str | None = None
    legend_format: str | None = None
    axis_x_range: str | None = None
    axis_y_range: str | None = None
    label_position: str | None = None
    label_format: str | None = None
    exclude_null_empty: str | bool | None = None
    exclude_zero: str | bool | None = None
    dynamic_rows_field: str | None = None
    dynamic_columns_field: str | None = None
    dynamic_field: str | None = None


class DashboardComments(BaseModel):
    slide_comments: dict[str, list[str]] = Field(default_factory=dict)
    # Comments added from the generated suggestions of one slide: their slide, texts (as added, after any edit),
    # engine and model, and the preparation they were generated from (its selection marks them out of date later).
    generated_slide: str = ''
    generated_added: int = Field(default=0, ge=0)
    generated_texts: list[str] = Field(default_factory=list)
    generated_engine: str = ''
    generated_model: str = ''
    token: str = ''


class GeneratedCommentChart(BaseModel):
    index: int
    hidden: list[str] = Field(default_factory=list)
    shown: list[str] = Field(default_factory=list)


class GenerateComments(BaseModel):
    token: str
    slide: int
    # The writer: rules, kiro_cli or claude (empty: the default one of Super Admin).
    engine: str = ''
    # The charts the viewer shows on the slide, with the legend items hidden and shown on each one.
    charts: list[GeneratedCommentChart] = Field(default_factory=list)


class GeneratedCommentSlide(BaseModel):
    number: int
    charts: list[GeneratedCommentChart] = Field(default_factory=list)


class GenerateAllComments(BaseModel):
    token: str
    # empty: only the slides without comments; generated: in place of the generated comments, keeping those written by
    # hand; all: in place of every comment.
    mode: Literal['empty', 'generated', 'all'] = 'empty'
    engine: str = ''
    # The slides the viewer shows (a dynamic grid can hide some cards); every content slide when none is given.
    slides: list[GeneratedCommentSlide] = Field(default_factory=list)


class DashboardName(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class DashboardTemplateSelection(BaseModel):
    nr_mode: Literal['NSA', 'SA', 'NSA+SA'] = 'NSA'
    template: str = Field(min_length=1)

    @model_validator(mode='before')
    @classmethod
    def without_template_nr_mode(cls, value: Any) -> Any:
        if isinstance(value, dict):
            mode = value.get('nr_mode', value.get('technology'))
            value = {**{key: item for key, item in value.items() if key != 'technology'},
                     'nr_mode': dashboard_nr_mode_value(mode)}
        return value


def identity(value):
    return column_identity(value)


def template_uids(task_repository) -> dict[str, str]:
    """The identity of each PPT Template of a workspace by name."""
    return task_repository.report_template_uids()


def follow_template_identities(dashboards: dict, templates: dict[str, str]) -> dict:
    """The Dashboards with the identity (``template_uid``) of their PPT Template: one whose template was renamed since,
    here or by an import, takes its current name, and one without it (saved before, or imported) takes that of the
    template it names."""
    by_uid = {uid: name for name, uid in templates.items() if uid}
    followed = {}
    for dashboard_id, definition in dashboards.items():
        if isinstance(definition, dict) and definition.get('template'):
            current = by_uid.get(str(definition.get('template_uid') or ''))
            if current:
                if current != definition['template']:
                    definition = {**definition, 'template': current}
            elif templates.get(str(definition['template'])):
                definition = {**definition, 'template_uid': templates[str(definition['template'])]}
        followed[dashboard_id] = definition
    return followed


def rename_template_in_dashboards(dashboards: dict, previous_template: str, template: str) -> list[str]:
    """The Dashboards that use a renamed template take its new name, and their names follow it; returns their IDs."""
    changed: list[str] = []
    for dashboard_id, raw_definition in dashboards.items():
        if not isinstance(raw_definition, dict) or str(raw_definition.get('template') or '') != previous_template:
            continue
        updated = dict(raw_definition)
        updated['template'] = template
        name = str(updated.get('name') or '')
        updated['name'] = re.sub(re.escape(previous_template), template, name, flags=re.IGNORECASE)
        dashboards[dashboard_id] = updated
        changed.append(dashboard_id)
    return changed


def dashboard_nr_mode(definition) -> str:
    """Return the NR Mode (``NSA``, ``SA`` or ``NSA+SA``) of the CDRs a Dashboard definition reads."""
    if isinstance(definition, dict):
        value = definition.get('nr_mode') or definition.get('technology') or definition.get('template_technology')
    else:
        value = getattr(definition, 'nr_mode', None)
    return dashboard_nr_mode_value(value)


# The options of the Campaign filter of the SA CDRs of an NSA & SA Dashboard (its ``sa_campaigns``).
SA_CAMPAIGN_FIELD = 'SA Campaign'


def entry_uses_nr_mode(entry) -> bool:
    """Whether a chart row filters, splits or labels its series by the NR Mode field."""
    key = identity(NR_MODE_FIELD)
    fields = [*re.split(r'\s*×\s*|\s+\bx\b\s+|,|/', f'{entry.rows_split} × {entry.columns_split} × {entry.legend}'),
              *entry_dynamic_fields(entry)]
    return any(identity(field) == key for field in fields if str(field).strip()) or 'nrmode' in identity(entry.filters or '')


def chart_nr_mode_unread(entry, definition) -> str:
    """Why a chart of one NR Mode shows nothing in a Dashboard that does not read it (empty when it reads it)."""
    modes = chart_filter_nr_modes(entry)
    read = nr_modes_of(dashboard_nr_mode(definition))
    if not entry.source_kind or entry.structural_type or any(mode in read for mode in modes):
        return ''
    return (f"This chart shows the {' & '.join(modes) or 'CDRs of no NR Mode'} CDRs and the Dashboard reads the "
            f"{DASHBOARD_NR_MODE_LABELS[dashboard_nr_mode(definition)]} ones: choose NR Mode NSA & SA to show it.")


def dataset_matches_nr_mode(dataset, nr_mode) -> bool:
    """Whether a serialized CDR belongs to the requested NR Mode (either one for NSA & SA)."""
    mode = dataset_nr_mode(dataset.get('dataset_kind'), dataset.get('nr_mode'), dataset.get('file_name'))
    return mode is None or mode in nr_modes_of(dashboard_nr_mode_value(nr_mode))


FILTER_COLUMNS = {
    'Market': ('market',), 'Operator': ('operator',), 'Operator_Vendor': ('Operator_Vendor',), 'Vendor': ('Vendor',),
    # Vendor_Operator is Operator_Vendor the other way round: it reads that column (see mapped_filter_options).
    'Vendor_Operator': ('Operator_Vendor',),
    'Region': ('Region', 'G_Level_2', 'G Level 2'), 'Cluster': ('Cluster',),
    'City': ('City', 'G_Level_4', 'G Level 4'), 'Campaign': ('Campaign', 'campaign'),
    'Session Type': ('session_type',),
    'RAT': ('RAT_A', 'RAT', 'Sample_RAT_A'),
    'Call Status': ('Call_Status', 'call_status', 'status'),
}
# The CDR catalogue (repository.cdr_catalogue_values) whose spellings a pattern of a filter is matched against.
PATTERN_CATALOGUE_FIELDS = {
    identity('Operator'): 'operators', identity('Vendor'): 'vendors_only', identity('Operator_Vendor'): 'vendors',
    identity('Vendor_Operator'): 'vendor_operators', identity('Region'): 'regions', identity('Cluster'): 'clusters',
    identity('City'): 'cities', identity('Campaign'): 'campaigns',
}
ADAPTATIVE_FILTER_FIELDS = (
    'Operator', 'Operator_Vendor', 'Vendor_Operator', 'Vendor', 'Market', 'Region', 'Cluster', 'City', 'Campaign', 'RAT',
    'Session Type', 'Call Status',
)
DASHBOARD_RENDER_CACHE_VERSION = 22
DASHBOARD_SELECTION_CACHE_VERSION = 18
# Pre-cached universes: every CDR plus the latest 1..N CDRs of each type.
DASHBOARD_WARMUP_LATEST_COUNTS = 4
# Only the most recently used Dashboard snapshots keep their chart frames in
# memory; older snapshots rebuild them on demand from the combined tables.
DASHBOARD_FRAME_CACHE_SNAPSHOTS = max(1, int(os.environ.get('DRIVETEST_ANALYZER_DASHBOARD_FRAME_CACHE_SNAPSHOTS') or 3))
# Grouped compact reads for eligible charts; 0 restores complete reads.
DASHBOARD_COMPACT_READS = os.environ.get('DRIVETEST_ANALYZER_COMPACT_READS', '1') != '0'
# Per-CDR column cache: any universe or comparison mode is assembled from it in
# memory; 0 restores SQLite reads for every chart.
DASHBOARD_COLUMN_CACHE = os.environ.get('DRIVETEST_ANALYZER_COLUMN_CACHE', '1') != '0'
# Source reads persisted beside the workspace so other sessions, restarts and
# exports reuse them. Very large complete reads are not persisted.
DASHBOARD_FRAME_CACHE_VERSION = 1
# Dashboard source reads: larger page cache, memory-mapped I/O and a sequential
# scan when the selected CDRs hold at least this share of a combined table.
DASHBOARD_READ_CACHE_KIB = 262_144
DASHBOARD_READ_MMAP_BYTES = 2 * 1024 ** 3
DASHBOARD_SEQUENTIAL_SCAN_SHARE = 0.2
DASHBOARD_FRAME_DISK_LIMIT = 400
DASHBOARD_FRAME_DISK_MAX_CELLS = 20_000_000
DASHBOARD_SELECTION_CACHE_LIMIT = 128
DASHBOARD_PROFILE_SELECTION_THRESHOLD = 100_000
DASHBOARD_CHART_MODEL_CACHE_VERSION = 19
DASHBOARD_CHART_MODEL_DISK_LIMIT = 500
DASHBOARD_CHART_RENDER_WORKERS = max(1, min(2, (os.cpu_count() or 2) - 1))
DASHBOARD_PREVIEW_MANIFEST_VERSION = 9
DASHBOARD_DATE_BOUNDS_CACHE_VERSION = 1


def dashboard_cache_dir(workspace: str | Path) -> Path:
    return Path(workspace).parent / '.dashboard-data-cache'


def frame_cache_dir(workspace: str | Path) -> Path:
    return dashboard_cache_dir(workspace) / 'frames'


def canvas_model_cache_dir(workspace: str | Path) -> Path:
    return dashboard_cache_dir(workspace) / 'charts-canvas'


def column_cache_dir(workspace: str | Path) -> Path:
    return dashboard_cache_dir(workspace) / 'columns'


def pil_chart_cache_dir(workspace: str | Path) -> Path:
    return dashboard_cache_dir(workspace) / 'charts-pil'


def preview_manifest_cache_dir(workspace: str | Path) -> Path:
    return dashboard_cache_dir(workspace) / 'dashboard-previews'


# Template "filters" that configure a chart instead of selecting rows.
CHART_SETTING_FILTERS = frozenset({'threshold', 'buckets', 'binsize', 'classcolours', 'histogramoperator'})
# Chart types whose models only depend on the multiset of rows, so SQLite can
# group identical rows and the loader expands them back before charting.
COMPACT_READ_CHART_TYPES = frozenset({
    'cdf line', 'histogram line', 'histogram bars', 'average vertical bars', 'median vertical bars',
    'distribution stacked vertical bars', 'threshold stacked vertical bars',
    '100% stacked vertical bars', 'count stacked horizontal bars',
})
# Fields the chart pipeline always consults and fields derived from the measure.
COMPACT_READ_IMPLICIT_FIELDS = ('Operator', 'operator', 'Campaign', 'period', 'Period', 'Quarter')
COMPACT_READ_DERIVED_FIELDS = frozenset({'ratebucket', 'valuebucket'})
COMPACT_READ_VENDOR_FIELDS = frozenset({'vendor', 'vendoronly', 'vendorv3', 'operatorvendor', 'opvendor'})


def resolve_filter_column(frame, field):
    field = vendor_filter_column(field)
    columns = {identity(column): column for column in frame.columns}
    aliases = next((values for label, values in FILTER_COLUMNS.items() if identity(label) == identity(field)), (field,))
    candidates = [columns[identity(alias)] for alias in aliases if identity(alias) in columns]
    return next((
        column for column in candidates
        if frame[column].fillna('').astype(str).str.strip().ne('').any()
    ), candidates[0] if candidates else None)


def filter_value_series(frame, field):
    """Resolve geographic aliases per row, skipping empty higher-priority values."""
    field = vendor_filter_column(field)
    columns = {identity(column): column for column in frame.columns}
    aliases = next((values for label, values in FILTER_COLUMNS.items() if identity(label) == identity(field)), (field,))
    candidates = [columns[identity(alias)] for alias in aliases if identity(alias) in columns]
    if not candidates:
        return None
    values = frame[candidates[0]].fillna('').astype(str)
    if identity(field) in {identity('City'), identity('Region')}:
        for column in candidates[1:]:
            empty = values.str.strip().eq('')
            if not empty.any():
                break
            values = values.where(~empty, frame[column].fillna('').astype(str))
    return values


def filter_mask(frame, definition, exclude=None):
    """Filter row indices so adaptive facets never copy complete, wide CDR tables."""
    columns = {identity(column): column for column in frame.columns}
    mask = pd.Series(True, index=frame.index)
    for field, values in definition.filters.items():
        if identity(field) == identity(exclude):
            continue
        field_values = filter_value_series(frame, field)
        if field_values is None:
            return pd.Series(False, index=frame.index)
        if identity(vendor_filter_column(field)) in {'vendor', 'operatorvendor'}:
            values = vendor_match_values(field, values, frame.attrs.get('operator_mappings', {}))
        # Patterns (VF*, Not Lebara) take every value they match (see value_patterns); an explicit empty selection none.
        chosen = ValueSet(values)
        mask &= chosen.mask(field_values.astype(str)) if chosen else pd.Series(False, index=frame.index)
    concrete_from = definition.date_from if isinstance(definition.date_from, date) and not ignore_event_time_filtering() else None
    concrete_to = definition.date_to if isinstance(definition.date_to, date) and not ignore_event_time_filtering() else None
    if concrete_from or concrete_to:
        time_column = next((columns[key] for key in ('eventstarttime', 'teststarttime', 'timestamp', 'datetime', 'date') if key in columns), None)
        if time_column is None:
            return pd.Series(False, index=frame.index)
        times = pd.to_datetime(frame[time_column], errors='coerce', utc=True, format='mixed')
        if concrete_from:
            mask &= times >= pd.Timestamp(concrete_from, tz='UTC')
        if concrete_to:
            mask &= times < pd.Timestamp(concrete_to + timedelta(days=1), tz='UTC')
    return mask


def filter_frame(frame, definition, exclude=None):
    """Apply selections, including explicit empty selections and missing fields."""
    if not definition.filters and not isinstance(definition.date_from, date) and not isinstance(definition.date_to, date):
        return frame
    return frame.loc[filter_mask(frame, definition, exclude)]



def dynamic_chart_values(entry) -> list[list[str]]:
    """Dynamic values of a grid card, each with its displayed form.

    Vendor grids display operator-only values as "<Operator> - All", so
    both forms identify the card when a value is hidden in a legend or axis.
    """
    values = [str(value) for value in (entry.dynamic_row_value, entry.dynamic_column_value) if value is not None]
    if not values and entry.dynamic_value is not None:
        values = [str(entry.dynamic_value)]
    label, _title = chart_title_parts(entry)
    displayed = label.split(' / ') if len(values) > 1 else [label]
    if len(displayed) != len(values):
        displayed = values
    return [list(dict.fromkeys(item for item in pair if item)) for pair in zip(values, displayed)]


def legend_value_hidden(hidden, shown, value: str) -> bool:
    """Whether a label is hidden by itself or by any of its " · " levels.

    Mirrors the Canvas renderer so the viewer, the PPT and its viewer agree.
    """
    hidden, shown = set(hidden), set(shown)
    return value not in shown and any(
        part in hidden and part not in shown for part in (value, *value.split(' · '))
    )


def dynamic_card_hidden(values: list[list[str]], hidden, shown) -> bool:
    """A dynamic grid card disappears when any of its dynamic values is hidden."""
    return any(legend_value_hidden(hidden, shown, value) for candidates in values for value in candidates)


GRID_LAYOUT_PATTERN = re.compile(r'Title \+ (\d+) rows \+ (\d+) columns(?: \+ comments (down|right))?')


def reflowed_dynamic_grid(layout: str, hidden_cards: list[bool]) -> tuple[str, list[int | None]] | None:
    """Close the rows and columns of hidden dynamic grid cards.

    Returns the smaller grid layout ('' when every card is hidden) and, per
    card in row-major order, its new cell or None when hidden. Returns None
    when nothing is hidden or the slide is not a complete grid.
    """
    match = GRID_LAYOUT_PATTERN.fullmatch(canonical_layout_name(layout or ''))
    if not match or not any(hidden_cards):
        return None
    rows, columns, comments = int(match.group(1)), int(match.group(2)), match.group(3) or ''
    if rows * columns != len(hidden_cards):
        return None
    visible_rows = [row for row in range(rows) if not all(hidden_cards[row * columns:(row + 1) * columns])]
    visible_columns = [column for column in range(columns) if not all(hidden_cards[column::columns])]
    cells = [
        None if hidden else visible_rows.index(card // columns) * len(visible_columns) + visible_columns.index(card % columns)
        for card, hidden in enumerate(hidden_cards)
    ]
    return (grid_layout_name(len(visible_rows), len(visible_columns), comments) if visible_rows else ''), cells


def normalized_frame_positions(frames) -> list[list[float]]:
    """Chart frames as percentages of their combined bounds, as the viewer lays them out."""
    if not frames:
        return []
    left, top = min(frame[0] for frame in frames), min(frame[1] for frame in frames)
    width = max(frame[0] + frame[2] for frame in frames) - left
    height = max(frame[1] + frame[3] for frame in frames) - top
    return [[(x - left) / width * 100, (y - top) / height * 100, w / width * 100, h / height * 100] for x, y, w, h in frames]


@dataclass
class Snapshot:
    workspace: str
    owner: str
    entries: list
    frames: dict
    multivendor: bool
    definition: DashboardDefinition
    dimensions: tuple
    selection_id: int
    selection_key: str
    payload: dict[str, object]
    chart_frames: dict[int, pd.DataFrame] = field(default_factory=dict)
    filtered_frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    chart_payloads: dict[int, dict[str, object]] = field(default_factory=dict)
    frame_locks: dict[str, RLock] = field(default_factory=dict)
    cancelled: object = None
    # Operator/Vendor mapping fingerprint the cached frames were built with.
    mapping_key: str = ''
    # Last time a user opened one of its charts; background warm-ups leave it at 0.
    viewed_at: float = 0.0
    # Selected CDR rows and combined source per chart source kind; they do not
    # change while the prepared universe is open.
    sources: dict[str, tuple] = field(default_factory=dict)


def install_dashboard_routes(core):
    app = core.app
    lock = RLock()
    snapshots = OrderedDict()
    images = OrderedDict()
    direct_preparation_tasks: dict[str, dict] = {}
    direct_preparation_results: OrderedDict[str, dict] = OrderedDict()
    initialized_ppt_job_databases: set[str] = set()
    dashboard_ppt_runs: dict[tuple[str, int], str] = {}
    dashboard_ppt_data_tokens: dict[tuple[str, int, str], str] = {}
    # Dashboard background work (pre-caching of the standard universes and,
    # while the application is idle, chart models and CDR columns) runs on one
    # low-priority thread, never on the shared application scheduler. It
    # handles one Dashboard at a time in creation order, and any foreground
    # Dashboard preparation or PPT export pauses it until it ends.
    dashboard_warmup_condition = Condition(lock)
    dashboard_warmup_queue: dict[tuple[str, str], dict[str, object]] = {}
    dashboard_warmup_checked: set[tuple[str, str]] = set()
    dashboard_warmup_cancellations: dict[tuple[str, str], dict[str, object]] = {}
    dashboard_warmup_running: dict[str, object] = {'key': None, 'thread': None, 'phase': ''}
    dashboard_chart_requests: set[tuple[str, str]] = set()
    dashboard_foreground_work: dict[str, int] = {}
    dashboard_warmup_sequence = count()
    dashboard_status_cache: dict[tuple[str, str], tuple[str, int, int]] = {}
    # Universes that cannot be prepared (for example a Vendor Comparison over
    # CDRs with a single Vendor) are skipped until the workspace data changes.
    dashboard_warmup_unavailable: dict[tuple[str, str], set[str]] = {}
    dashboard_status_shared_signature: dict[str, str] = {}
    interactive_chart_preview_jobs: OrderedDict[str, dict] = OrderedDict()
    # Jobs writing the comments of every slide of a Dashboard (Generate comments → All slides).
    comment_jobs: OrderedDict[str, dict] = OrderedDict()
    # Kiro Briefs prepared for download (the facts of every slide of a Dashboard).
    comment_briefs: OrderedDict[str, dict] = OrderedDict()
    dashboard_work_gate = Lock()

    def workspace_key():
        if not core.active_workspace:
            raise HTTPException(400, 'Open a workspace before using PPT Dashboards.')
        return str(Path(core.repository.db_path).resolve())

    def dashboard_user(user=Depends(core.current_user)):
        if core.active_workspace and user.role != 'super-admin' and not core.repository.user_has_workspace_access(user.username, core.active_workspace.id):
            raise HTTPException(403, 'You do not have access to the active workspace.')
        return user

    def dashboard_editor_user(user=Depends(dashboard_user)):
        if user.role not in {'user-editor', 'admin', 'super-admin'}:
            raise HTTPException(403, 'Editor access required.')
        return user

    def bound_repository():
        return Repository(Path(workspace_key()), core.repository.global_db_path)

    def ensure_dashboard_ppt_jobs(task_repository):
        database_key = str(Path(task_repository.db_path).resolve())
        with lock:
            first_check = database_key not in initialized_ppt_job_databases
            initialized_ppt_job_databases.add(database_key)
        with task_repository.connection() as connection:
            connection.execute(f'''CREATE TABLE IF NOT EXISTS {DASHBOARD_PPT_JOBS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dashboard_id TEXT NOT NULL,
                dashboard_name TEXT NOT NULL,
                template_name TEXT NOT NULL,
                nr_mode TEXT NOT NULL DEFAULT 'nsa',
                scope TEXT NOT NULL DEFAULT 'single',
                regions_json TEXT NOT NULL DEFAULT '[]',
                selections_json TEXT NOT NULL DEFAULT '{{}}',
                filters_json TEXT NOT NULL DEFAULT '[]',
                legend_visibility_json TEXT NOT NULL DEFAULT '{{}}',
                output_file TEXT NOT NULL,
                output_path TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                progress INTEGER NOT NULL DEFAULT 0,
                slide_count INTEGER NOT NULL DEFAULT 0,
                chart_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                finished_at TEXT
            )''')
            columns = {str(row['name']) for row in connection.execute(
                f'PRAGMA table_info({DASHBOARD_PPT_JOBS_TABLE})'
            ).fetchall()}
            if 'vendor_comparison' not in columns:
                connection.execute(f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN vendor_comparison TEXT NOT NULL DEFAULT 'operator_vendor'")
            if 'scope' not in columns:
                connection.execute(
                    f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN scope TEXT NOT NULL DEFAULT 'single'"
                )
            if 'nr_mode' not in columns:
                connection.execute(
                    f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN nr_mode TEXT NOT NULL DEFAULT 'nsa'"
                )
            if 'filters_json' not in columns:
                connection.execute(
                    f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN filters_json TEXT NOT NULL DEFAULT '[]'"
                )
            if 'regions_json' not in columns:
                connection.execute(
                    f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN regions_json TEXT NOT NULL DEFAULT '[]'"
                )
            if 'selections_json' not in columns:
                connection.execute(
                    f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN selections_json TEXT NOT NULL DEFAULT '{{}}'"
                )
            if 'started_at' not in columns:
                connection.execute(
                    f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN started_at TEXT"
                )
            if 'legend_visibility_json' not in columns:
                connection.execute(
                    f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN legend_visibility_json TEXT NOT NULL DEFAULT '{{}}'"
                )
            if 'auto_comments' not in columns:
                connection.execute(f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN auto_comments TEXT NOT NULL DEFAULT 'off'")
            if 'auto_comments_engine' not in columns:
                connection.execute(f"ALTER TABLE {DASHBOARD_PPT_JOBS_TABLE} ADD COLUMN auto_comments_engine TEXT NOT NULL DEFAULT ''")
            if first_check:
                connection.execute(
                    f'''UPDATE {DASHBOARD_PPT_JOBS_TABLE}
                        SET status = 'failed', progress = 100,
                            last_error = 'Dashboard export was interrupted by an application restart.',
                            finished_at = ?
                        WHERE status IN ('queued', 'processing')''',
                    (datetime.now(timezone.utc).isoformat(),),
                )

    def dashboard_ppt_job(task_repository, job_id):
        ensure_dashboard_ppt_jobs(task_repository)
        with task_repository.connection() as connection:
            return connection.execute(
                f'SELECT * FROM {DASHBOARD_PPT_JOBS_TABLE} WHERE id = ?', (job_id,),
            ).fetchone()

    def update_dashboard_ppt_job(task_repository, job_id, **changes):
        if not changes:
            return
        assignments = ', '.join(f'{key} = ?' for key in changes)
        with task_repository.connection() as connection:
            connection.execute(
                f'UPDATE {DASHBOARD_PPT_JOBS_TABLE} SET {assignments} WHERE id = ?',
                (*changes.values(), job_id),
            )

    def normalized_legend_visibility(value) -> dict[str, dict]:
        """Keep a bounded {"dashboard": {label: hidden}, "charts": {key: {label: hidden}}} state."""
        def states(raw) -> dict[str, bool]:
            if not isinstance(raw, dict):
                return {}
            return {str(label)[:300]: bool(hidden) for label, hidden in list(raw.items())[:2000]}

        value = value if isinstance(value, dict) else {}
        charts = value.get('charts') if isinstance(value.get('charts'), dict) else {}
        return {
            'dashboard': states(value.get('dashboard')),
            'charts': {str(key)[:600]: states(raw) for key, raw in list(charts.items())[:2000] if states(raw)},
        }

    def chart_legend_keys(entries) -> dict[int, str]:
        """Stable chart keys (slide, title, occurrence) shared by the viewer and the PPT."""
        keys = {}
        occurrences: dict[tuple[int, str], int] = defaultdict(int)
        for index, entry in sorted(enumerate(entries), key=lambda item: (item[1].slide, item[0])):
            if entry.structural_type:
                continue
            title = str(entry.chart_title or '')
            occurrence = occurrences[(entry.slide, title)]
            occurrences[(entry.slide, title)] += 1
            keys[index] = f'{entry.slide}|{title}|{occurrence}'
        return keys

    def chart_legend_lists(visibility, chart_key) -> tuple[list[str], list[str]]:
        """Hidden and explicitly shown legend labels or values of one chart.

        The chart's own choices come first, then the Dashboard-wide ones. The
        renderer hides every series, row or column with a hidden value at any
        aggregation level, exactly as the viewer does.
        """
        chart_states = visibility.get('charts', {}).get(chart_key, {}) if chart_key else {}
        hidden = [label for label, value in chart_states.items() if value]
        shown = [label for label, value in chart_states.items() if not value]
        for label, value in visibility.get('dashboard', {}).items():
            if label not in chart_states:
                (hidden if value else shown).append(label)
        return hidden, shown

    def dashboard_filter_lines(definition: dict, task_repository, selection_labels: dict[str, str] | None = None) -> list[str]:
        lines = []
        for kind in KINDS:
            datasets = dashboard_datasets(definition, kind, task_repository)
            names = [str(dataset.get('file_name') or dataset.get('display_name') or dataset.get('id')) for dataset in datasets]
            if names:
                lines.append(f'CDR {kind.title()}: {", ".join(names)}')
        date_from = '' if ignore_event_time_filtering() else str(definition.get('date_from') or '').strip()
        date_to = '' if ignore_event_time_filtering() else str(definition.get('date_to') or '').strip()
        if date_from and date_to:
            lines.append(f'Date: {date_from} to {date_to}')
        elif date_from:
            lines.append(f'Date from: {date_from}')
        elif date_to:
            lines.append(f'Date to: {date_to}')
        filters = definition.get('filters')
        if not isinstance(filters, dict):
            filters = {}
        if selection_labels is not None:
            # The Campaigns line already reads "Campaign: …" or "Campaigns: …".
            if selection_labels.get('Campaign'):
                lines.append(selection_labels['Campaign'])
            for field in ('Operator', 'Vendor', 'Region', 'City'):
                if selection_labels.get(field):
                    lines.append(f'{field}: {selection_labels[field]}')
        for field, values in filters.items():
            if selection_labels is not None and identity(field) in {'campaign', 'operator', 'vendor', 'vendoronly', 'region', 'city'}:
                continue
            if isinstance(values, (list, tuple, set)):
                selected = [str(value).strip() for value in values if str(value).strip()]
            elif str(values).strip():
                selected = [str(values).strip()]
            else:
                selected = []
            if selected:
                label = vendor_filter_column(field) if identity(vendor_filter_column(field)) in {'vendor', 'operatorvendor'} else re.sub(r'[_-]+', ' ', str(field)).strip().title() or 'Filter'
                lines.append(f'{label}: {", ".join(selected)}')
        return lines

    def dashboard_ppt_job_filters_with_all_selections(filters: list[str]) -> list[str]:
        """Show All Operators and All Vendors for jobs that stored no such line.

        Jobs that recorded their Region or City selection omitted Operator and
        Vendor when nothing specific was selected; that means every value.
        """
        fields = [str(line).partition(':')[0].strip() for line in filters]
        geography = next((index for index, field in enumerate(fields) if field in {'Region', 'City'}), None)
        if geography is None:
            return filters
        missing = [
            f'{field}: {label}'
            for field, label in (('Operator', 'All Operators'), ('Vendor', 'All Vendors'))
            if field not in fields
        ]
        return [*filters[:geography], *missing, *filters[geography:]]

    def serialize_dashboard_ppt_job(row):
        output_path = Path(str(row['output_path'] or ''))
        output_file = str(row['output_file'] or '')
        timestamp_match = re.match(r'^(\d{8}_\d{6})', output_file)
        charts_dir = output_path.parent / 'dashboard-charts'
        ready = str(row['status']) == 'ready' and output_path.is_file()
        charts_ready = ready and (charts_dir / 'manifest.json').is_file()
        job_id = int(row['id'])
        duration = None
        if row['finished_at'] and row['started_at']:
            try:
                duration = max(0, (
                    datetime.fromisoformat(str(row['finished_at']))
                    - datetime.fromisoformat(str(row['started_at']))
                ).total_seconds())
            except ValueError:
                pass
        try:
            filters = json.loads(str(row['filters_json'] or '[]'))
            filters = [str(item) for item in filters if str(item).strip()] if isinstance(filters, list) else []
        except (TypeError, json.JSONDecodeError):
            filters = []
        filters = dashboard_ppt_job_filters_with_all_selections(filters)
        if str(row['scope']) == 'multivendor':
            filters.append('Vendor comparison: ' + ('Vendor' if row['vendor_comparison'] == 'vendor_only' else 'Operator_Vendor'))
        cover = dashboard_ppt_job_cover(row, {})
        if charts_ready and (not cover['regions'] or not cover['cities']):
            try:
                manifest = json.loads((charts_dir / 'manifest.json').read_text(encoding='utf-8'))
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            else:
                cover = dashboard_ppt_job_cover(row, manifest if isinstance(manifest, dict) else {})
        return {
            'id': job_id, 'dashboard_id': str(row['dashboard_id']),
            'dashboard_name': str(row['dashboard_name']),
            'timestamp': timestamp_match.group(1) if timestamp_match else '',
            'template': str(row['template_name'] or ''),
            'nr_mode': str(row['nr_mode'] or 'nsa').upper(),
            'scope': 'Multivendor Comparison' if str(row['scope'] or '').casefold() == 'multivendor' else 'Operator Comparison',
            'cover': cover,
            'filters': filters,
            'generated_by': str(row['created_by']),
            'date': core._local_report_date(row['created_at']).replace(' ', '\n', 1),
            'status': str(row['status']), 'progress': int(row['progress'] or 0),
            'duration_seconds': duration,
            'slides': int(row['slide_count'] or 0), 'charts': int(row['chart_count'] or 0),
            'error': str(row['last_error'] or ''),
            'download_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/download' if ready else None,
            'charts_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/charts' if charts_ready else None,
            'charts_api_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/charts.json' if charts_ready else None,
            'charts_download_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/charts.zip' if charts_ready else None,
            'retry_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/retry' if str(row['status']) in {'ready', 'failed', 'stopped'} else None,
            'stop_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/stop' if str(row['status']) in {'queued', 'processing'} else None,
            'delete_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/delete',
        }

    def dashboard_preview_fingerprint(raw_definition, task_repository):
        """Include the current Report Template content in the prepared-preview identity."""
        definition = DashboardDefinition.model_validate(
            runtime_dashboard_definition(raw_definition, task_repository)
        )
        template_content = task_repository.report_template_content(definition.template)
        material = {
            'definition': definition.model_dump(mode='json'),
            'template_content': sha256(template_content).hexdigest(),
            'chart_mappings': task_repository.chart_mapping_settings(),
        }
        return sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()

    def dashboard_export_snapshot(dashboard_id, raw_definition, task_repository):
        workspace = str(Path(task_repository.db_path).resolve())
        definition = DashboardDefinition.model_validate(
            runtime_dashboard_definition(raw_definition, task_repository)
        )
        preview = restore_matching_preview_manifest(workspace, dashboard_id, definition)
        snapshot = snapshots.get(str(preview.get('token') or '')) if preview else None
        if snapshot is None:
            raise ValueError('The Dashboard dataset is not prepared.')
        return validate_dashboard_export_snapshot(snapshot, task_repository)

    def validate_dashboard_export_snapshot(snapshot, task_repository):
        selected_sources(snapshot.definition, task_repository)
        return snapshot

    def dashboard_chart_render_size(placement) -> tuple[int, int]:
        """Return a placeholder-ratio Canvas size with one unchanged logical axis."""
        _left, _top, width, height = placement
        frame_ratio = float(width) / float(height)
        if frame_ratio >= 1600 / 900:
            return min(4096, max(320, round(900 * frame_ratio))), 900
        return 1600, min(4096, max(240, round(1600 / frame_ratio)))

    def dashboard_ppt_scope_label(scope: str) -> str:
        """Return the human-readable scope used on Dashboard PPT covers."""
        return 'Multivendor Comparison' if str(scope).casefold() == 'multivendor' else 'Operator Comparison'

    def values_present_in_cdrs(values: list[str], available: list[str]) -> list[str]:
        """Keep only values that exist in the selected CDRs.

        Saved filters can hold values of other CDRs (for example an NSA-only
        Operator in an SA Dashboard). When none of the values exist, the
        selection is kept so it never reads as an unrestricted "All".
        """
        present = {str(value).strip().casefold() for value in available if str(value).strip()}
        if not present:
            return values
        kept = [value for value in values if str(value).strip().casefold() in present]
        return kept or values

    def dashboard_ppt_selection_values(
        filters: dict, field: str, requested: list[str], available: list[str],
    ) -> list[str]:
        configured = next((values for key, values in filters.items() if identity(vendor_filter_column(key)) == identity(vendor_filter_column(field))), None)
        values = configured if configured is not None else requested or available
        if isinstance(values, (list, tuple, set)):
            values = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
        else:
            values = [str(values).strip()] if str(values).strip() else []
        return values_present_in_cdrs(values, available)

    def dashboard_ppt_selection_label(
        field: str, values: list[str], available: list[str], alternatives: tuple[list[str], ...] = (),
    ) -> str:
        # "All" means the selection covers every value of the CDR catalogue or
        # of the Dashboard's own filter options (which a saved "select every
        # value" filter comes from), ignoring case and surrounding spaces.
        selected = {str(value).strip().casefold() for value in values if str(value).strip()}
        field = vendor_filter_column(field) if identity(vendor_filter_column(field)) == 'vendor' else field
        all_label = {'Operator': 'All Operators', 'Vendor': 'All Vendors', 'Region': 'All Regions', 'City': 'All Cities'}[field]
        # No specific Operator or Vendor means the export is not restricted
        # by them. Region and City stay blank so covers and file names only
        # name geography the CDRs actually provide.
        if not selected and field in {'Operator', 'Vendor'}:
            return all_label
        candidates = [available, *alternatives]
        if selected and any(
            candidate and selected >= {str(value).strip().casefold() for value in candidate if str(value).strip()}
            for candidate in candidates
        ):
            return all_label
        return ', '.join(values)

    def dashboard_ppt_cover_label(field: str, label: str, count: int) -> str:
        if not label or label.startswith('All '):
            return label
        singular, plural = {'Region': ('Region', 'Regions'), 'City': ('City', 'Cities')}[field]
        return f'{singular if count == 1 else plural}: {label}'

    def dashboard_ppt_job_cover(row, manifest: dict) -> dict[str, str]:
        """Return a PPT job's cover lines, rebuilding them for older jobs."""
        cover = manifest.get('cover')
        if isinstance(cover, dict):
            return {key: str(cover.get(key) or '') for key in ('campaigns', 'scope', 'regions', 'cities')}
        try:
            lines = json.loads(str(row['filters_json'] or '[]'))
        except (TypeError, ValueError, json.JSONDecodeError):
            lines = []
        labels = {}
        for line in lines if isinstance(lines, list) else []:
            field, _separator, value = str(line).partition(': ')
            if field in {'Region', 'City'} and value:
                labels[field] = value
        return {
            'campaigns': '',
            'scope': dashboard_ppt_scope_label(str(row['scope'] or 'single')),
            'regions': dashboard_ppt_cover_label('Region', labels.get('Region', ''), len(labels.get('Region', '').split(', '))),
            'cities': dashboard_ppt_cover_label('City', labels.get('City', ''), len(labels.get('City', '').split(', '))),
        }

    def add_dashboard_ppt_cover_geography(
        slide, campaigns: str, scope: str, regions: str, cities: str, slide_height: int,
    ) -> None:
        """Place the cover Campaigns above the decorative line and the Scope and geography below it."""
        title = next((shape for shape in slide.placeholders if shape.placeholder_format.type in {1, 3}), None)
        subtitle = next((shape for shape in slide.placeholders if shape.placeholder_format.type == 4), None)
        # At the left of the title once report_structure.finish places the cover.
        left = report_structure.TITLE_LEFT
        width = title.width if title is not None else Inches(11)
        margin_left = title.text_frame.margin_left if title is not None else 0
        anchor = subtitle or title
        anchor_bottom = anchor.top + anchor.height if anchor is not None else None

        def add_line(name: str, value: str, color: RGBColor, size: int, top: int, height: int) -> None:
            box = slide.shapes.add_textbox(left, top, width, height)
            box.name = f'dashboard-ppt-{name}'
            box.text_frame.margin_left = margin_left
            box.text_frame.margin_top = 0
            box.text_frame.margin_bottom = 0
            box.text_frame.word_wrap = True
            box.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
            paragraph = box.text_frame.paragraphs[0]
            # White on the red of the cover: the label bold, its values regular.
            label, separator, rest = value.partition(': ')
            for text, bold in ((label + separator, True), (rest, False)) if separator else ((value, True),):
                if not text:
                    continue
                run = paragraph.add_run()
                run.text = text
                run.font.size = Pt(size)
                run.font.bold = bold
                run.font.color.rgb = color

        # Like the Dashboard viewer, Scope, Regions and Cities follow the
        # template's decorative line under the subtitle.
        white = RGBColor(255, 255, 255)
        details = [
            (name, value, white)
            for name, value in (('scope', scope), ('region', regions), ('city', cities))
            if value
        ]
        first_top = (
            anchor_bottom + Inches(0.29) if anchor_bottom is not None
            else slide_height - Inches(0.35 + 0.38 * len(details))
        )
        first_top = min(first_top, slide_height - Inches(0.4 + 0.38 * len(details)))
        if campaigns:
            # The larger Campaigns line sits right above the decorative
            # line. Title and subtitle move up just enough to make room for it.
            campaign_height = Inches(0.42)
            separator = next((
                shape for shape in slide.slide_layout.shapes
                if shape.shape_type == MSO_SHAPE_TYPE.LINE and anchor_bottom is not None
                and anchor_bottom - Inches(0.1) <= shape.top <= first_top
            ), None)
            if separator is not None:
                campaign_top = separator.top - Inches(0.06) - campaign_height
                shift = max(0, anchor_bottom + Inches(0.04) - campaign_top)
                for placeholder in (title, subtitle):
                    if placeholder is not None and shift:
                        placeholder.left, placeholder.top, placeholder.width, placeholder.height = (
                            placeholder.left, placeholder.top - shift, placeholder.width, placeholder.height,
                        )
            else:
                campaign_top = anchor_bottom + Inches(0.06) if anchor_bottom is not None else first_top
                first_top = max(first_top, campaign_top + campaign_height + Inches(0.08))
            add_line('campaigns', campaigns, white, 20, campaign_top, campaign_height)
        for index, (name, value, color) in enumerate(details):
            add_line(name, value, color, 16, first_top + Inches(0.38 * index), Inches(0.34))

    def add_dashboard_cell_title(slide, entry, placement):
        """Write a small-cell chart title as slide text and return the remaining chart frame."""
        from pptx.dml.color import RGBColor
        from pptx.util import Emu, Pt

        left, top, width, height = placement
        size = 10 if width >= Emu(2_400_000) else 9
        title_height = min(int(height * .3), int(Pt(size) * 2.6))
        box = slide.shapes.add_textbox(left, top, width, title_height)
        box.name = 'Chart Title'
        frame = box.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = Pt(2)
        frame.margin_top = frame.margin_bottom = 0
        label, base = chart_title_parts(entry)
        paragraph = frame.paragraphs[0]
        for text, bold in ((label, True), ((' · ' if label else '') + base, False)):
            if not text:
                continue
            run = paragraph.add_run()
            run.text = text
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = RGBColor(0x1D, 0x33, 0x45)
        return left, top + title_height, width, height - title_height

    def add_dashboard_chart_picture(slide, png: bytes, placement) -> None:
        """Fill a same-ratio chart placeholder without PowerPoint cropping or distortion."""
        left, top, width, height = placement
        slide.shapes.add_picture(BytesIO(png), left, top, width, height)

    def ensure_export_universe_cached(task_repository, workspace, dashboard_id, definition, user, *, cancelled, progress):
        """Persist the pre-cached universe behind an export when it is missing."""
        with lock:
            saved = read_dashboards(task_repository).get(dashboard_id)
        if not isinstance(saved, dict):
            return
        universe = DashboardDefinition.model_validate(runtime_dashboard_definition(saved, task_repository))
        universe.datasets = {kind: list(ids) for kind, ids in definition.datasets.items()}
        universe.scope = definition.scope
        universe.date_from, universe.date_to = 'Oldest', 'Newest'
        if restore_matching_preview_manifest(workspace, dashboard_id, universe, materialize=False) is not None:
            return
        try:
            with dashboard_work_gate:
                preview = build_preview(universe, user, workspace=workspace, cancelled=cancelled, progress=progress)
        except HTTPException:
            # The export's own preparation reports an invalid selection.
            return
        with lock:
            snapshot = snapshots.get(preview['token'])
        if snapshot is not None:
            persist_preview_manifest(
                workspace, dashboard_id,
                dashboard_preview_fingerprint(snapshot.definition.model_dump(mode='json'), task_repository),
                preview['token'],
            )

    def auto_slide_comments(snapshot, chart_entries, models, legend_visibility, legend_keys, layout, task_repository,
                            engine: str, username: str) -> tuple[list[str], str]:
        """The comments the writer of a PPT job writes for one of its slides from the chart models of the job, and the
        writer that wrote them (the rules when the LLM writer fails)."""
        charts = []
        for index, entry in chart_entries:
            model = models.get(index)
            if not model or model.get('type') not in dashboard_comments.SUPPORTED_MODEL_TYPES:
                continue
            hidden, shown = chart_legend_lists(legend_visibility, legend_keys.get(index))
            charts.append({
                'index': index, 'title': entry.chart_title or entry.slide_title, 'kpi': entry.kpi, 'model': model,
                'hidden': hidden, 'shown': shown,
                'subject': ' · '.join(value for value in (entry.dynamic_row_value, entry.dynamic_column_value) if value),
            })
        if not charts:
            return [], dashboard_comments.ENGINE_RULES
        suggestions, written = write_slide_comments(charts, layout or '', task_repository, engine, username)
        return [item['text'] for item in suggestions], written['engine']

    def merge_auto_comments(comments: list[str], automatic: list[str], mode: str, generated: list[str]) -> list[str]:
        """The comments of a PPT slide with its Auto comments: only on a slide without comments (``empty``), in place of
        the comments generated before, keeping those written by hand (``generated``), or in place of every comment
        (``all``). A slide the rules have nothing to say about keeps its comments."""
        if not automatic or (mode == 'empty' and comments):
            return comments
        manual = [text for text in comments if text not in set(generated)] if mode == 'generated' else []
        return [*manual, *[text for text in automatic if text not in manual]][:50]

    def render_dashboard_ppt_job(
        job_id, run_token, task_repository, snapshot, definition, user,
        destination, dashboard_id, preview_fingerprint, cover_regions, cover_cities, cover_campaigns='', theme=None,
    ):
        run_key = (str(Path(task_repository.db_path).resolve()), job_id)
        # The colour theme of the titles of the content slides and of the charts: that of the report generating the PPT
        # (a Bundle Report Template or a Reporting Job), else the one the user chose for PPT Dashboards.
        theme = normalize_theme(theme) if theme else load_user_theme(task_repository, user.username, DASHBOARD_THEME_MODULE)
        chart_style = dashboard_chart_style(theme)

        def run_is_active():
            with lock:
                if dashboard_ppt_runs.get(run_key) != run_token:
                    return False
            current = dashboard_ppt_job(task_repository, job_id)
            return current is not None and str(current['status']) in {'queued', 'processing'}

        try:
            if not run_is_active():
                return
            # The preparation step already marked the job as started.
            update_dashboard_ppt_job(task_repository, job_id, status='processing')
            if snapshot is None:
                update_dashboard_ppt_job(
                    task_repository, job_id, progress=1, last_error='',
                )

                def preparation_progress(percent, _detail):
                    if run_is_active():
                        update_dashboard_ppt_job(
                            task_repository, job_id,
                            # Preparation is visible without dominating the
                            # progress bar; the following Canvas rendering
                            # phase has a known model count and owns most of it.
                            progress=max(12, min(24, 12 + round(percent * 0.12))),
                        )

                workspace = str(Path(task_repository.db_path).resolve())
                with foreground_dashboard_work(workspace):
                    # Pre-cache the chosen CDR universe (the saved Dashboard
                    # filters over all dates) before applying the export's own
                    # selections, exactly as the automatic warm-up would.
                    ensure_export_universe_cached(
                        task_repository, workspace, dashboard_id, definition, user,
                        cancelled=lambda: not run_is_active(),
                        progress=lambda percent, _detail: run_is_active() and update_dashboard_ppt_job(
                            task_repository, job_id, progress=max(1, min(12, 1 + round(percent * 0.11))),
                        ),
                    )
                    preview = restore_matching_preview_manifest(workspace, dashboard_id, definition)
                    if preview is None:
                        with dashboard_work_gate:
                            preview = build_preview(
                                definition, user, workspace=workspace,
                                cancelled=lambda: not run_is_active(), progress=preparation_progress,
                            )
                token = str(preview['token'])
                with lock:
                    snapshot = snapshots.get(token)
                    dashboard_ppt_data_tokens[(
                        str(Path(task_repository.db_path).resolve()), job_id, user.username,
                    )] = token
                if snapshot is None:
                    raise RuntimeError('The refreshed Dashboard snapshot could not be created.')
                persist_preview_manifest(
                    str(Path(task_repository.db_path).resolve()), dashboard_id,
                    dashboard_preview_fingerprint(
                        snapshot.definition.model_dump(mode='json'), task_repository,
                    ), token,
                )
                snapshot = validate_dashboard_export_snapshot(snapshot, task_repository)
            update_dashboard_ppt_job(task_repository, job_id, progress=24, last_error='')
            with lock:
                snapshot_token = next((
                    token for token, candidate in snapshots.items() if candidate is snapshot
                ), '')
            if not snapshot_token:
                raise RuntimeError('The prepared Dashboard snapshot has expired.')
            indexes = [
                index for index, entry in enumerate(snapshot.entries)
                if dashboard_datasets(snapshot.definition, entry.source_kind, task_repository)
            ]
            chart_model_errors: dict[int, str] = {}
            job_row = dashboard_ppt_job(task_repository, job_id)
            auto_mode = str(job_row['auto_comments'] or 'off') if job_row is not None else 'off'
            auto_engine = comment_writers.resolve_engine(
                core.repository, str(job_row['auto_comments_engine'] or '') if job_row is not None else '',
            )
            auto_engines: set[str] = set()
            auto_models: dict[int, dict] = {}
            auto_written: dict[str, list[str]] = {}
            for position, index in enumerate(indexes):
                if not run_is_active():
                    return
                model_progress_start = 25 + round(position * 65 / max(len(indexes), 1))
                model_progress_end = 25 + round((position + 1) * 65 / max(len(indexes), 1))
                update_dashboard_ppt_job(
                    task_repository, job_id,
                    progress=model_progress_start, last_error='',
                )
                model_finished = Event()

                def pulse_canvas_progress():
                    # A single Canvas model can take much longer than the
                    # others.  It has no internal callback, so advance only
                    # within its known model slice while it is genuinely
                    # running; completion still owns the final increment.
                    elapsed_seconds = 0
                    while not model_finished.wait(1):
                        elapsed_seconds += 1
                        span = max(0, model_progress_end - model_progress_start - 1)
                        fraction = min(0.9, elapsed_seconds / 18)
                        progress = model_progress_start + round(span * fraction)
                        if run_is_active():
                            try:
                                update_dashboard_ppt_job(task_repository, job_id, progress=progress, last_error='')
                            except sqlite3.Error:
                                # Progress is advisory.  A transient SQLite
                                # writer contention must never affect the
                                # Canvas model or cause the PPT job to fail.
                                pass

                pulse = Thread(target=pulse_canvas_progress, name=f'dashboard-ppt-model-progress-{job_id}', daemon=True)
                pulse.start()
                try:
                    try:
                        model = chart_model(
                            snapshot_token, index, user,
                            expected_workspace=str(Path(task_repository.db_path).resolve()),
                        )
                        if auto_mode != 'off' and dashboard_comments.needs_rebuild(model):
                            # Auto comments read the facts a model cached before them lacks.
                            model = chart_model(
                                snapshot_token, index, user,
                                expected_workspace=str(Path(task_repository.db_path).resolve()), force=True,
                            )
                        auto_models[index] = model
                    except (HTTPException, ValueError) as exc:
                        # A template can legitimately contain a chart for a
                        # field absent from one selected CDR type.  Retain a
                        # visible placeholder for that chart instead of
                        # discarding the complete PPT job.
                        chart_model_errors[index] = str(getattr(exc, 'detail', exc))
                finally:
                    model_finished.set()
                    pulse.join(timeout=0.1)
                update_dashboard_ppt_job(
                    task_repository, job_id,
                    progress=model_progress_end, last_error='',
                )
            update_dashboard_ppt_job(task_repository, job_id, progress=90, last_error='')
            presentation = Presentation(core.settings.powerpoint_template)
            _remove_all_slides(presentation)
            # Legend entries hidden in the viewer stay hidden in the PPT charts.
            job_row = dashboard_ppt_job(task_repository, job_id)
            try:
                legend_visibility = normalized_legend_visibility(json.loads(str(job_row['legend_visibility_json'] or '{}')))
            except (KeyError, IndexError, TypeError, ValueError):
                legend_visibility = normalized_legend_visibility({})
            legend_keys = chart_legend_keys(snapshot.entries)
            grouped = defaultdict(list)
            for index, entry in enumerate(snapshot.entries):
                grouped[entry.slide].append((index, entry))
            # Dynamic grid cards whose value is hidden leave the slide and the
            # remaining cards fill a smaller grid, exactly as in the viewer; a
            # slide whose cards are all hidden is left out.
            hidden_entries: set[int] = set()
            reflowed_layouts: dict[int, str] = {}
            reflowed_cells: dict[int, dict[int, int]] = {}
            for slide_number, slide_entries in grouped.items():
                cards = [(index, entry) for index, entry in slide_entries if not entry.structural_type]
                hidden_cards = []
                for index, entry in cards:
                    values = dynamic_chart_values(entry)
                    hidden_cards.append(bool(values) and dynamic_card_hidden(
                        values, *chart_legend_lists(legend_visibility, legend_keys.get(index)),
                    ))
                reflow = reflowed_dynamic_grid(slide_entries[0][1].layout, hidden_cards)
                if reflow is None:
                    continue
                reflowed_layouts[slide_number], cells = reflow
                hidden_entries.update(index for (index, _entry), cell in zip(cards, cells) if cell is None)
                reflowed_cells[slide_number] = {
                    index: cell for (index, _entry), cell in zip(cards, cells) if cell is not None
                }
            charts_dir = destination.parent / 'dashboard-charts'
            charts_dir.mkdir(parents=True, exist_ok=True)
            manifest = []
            focus_rows = {
                entry_index: (_entry.template_index if _entry.template_index is not None else editor_index)
                for editor_index, (entry_index, _entry) in enumerate(
                    sorted(enumerate(snapshot.entries), key=lambda item: (item[1].slide, item[0]))
                )
            }
            chart_total = sum(
                1 for entries in grouped.values() for index, entry in entries
                if index not in hidden_entries
                and entry.source_kind and dashboard_datasets(snapshot.definition, entry.source_kind, task_repository)
            )
            rendered = 0
            for slide_number in sorted(grouped):
                if not run_is_active():
                    return
                slide_entries = grouped[slide_number]
                header = slide_entries[0][1]
                _comment_key, comments = dashboard_slide_comments(
                    snapshot.definition, [entry for _index, entry in slide_entries],
                )
                if header.structural_type:
                    layout = _named_slide_layout(presentation, header.layout or 'Title Page')
                    if layout is None:
                        raise ValueError(f"Slide {slide_number}: layout '{header.layout}' is unavailable.")
                    slide = presentation.slides.add_slide(layout)
                    if header.structural_type == 'end slide':
                        _clear_end_slide(slide)
                        continue
                    is_cover = header.structural_type == 'title slide' and slide_number == min(grouped)
                    _set_structural_slide_text(slide, header.slide_title, header.slide_subtitle)
                    if is_cover:
                        add_dashboard_ppt_cover_geography(
                            slide, cover_campaigns, dashboard_ppt_scope_label(snapshot.definition.scope),
                            cover_regions, cover_cities, presentation.slide_height,
                        )
                    else:
                        # The other title and transition rows open the parts of the Dashboard: 01, 02…
                        report_structure.mark(slide, 1)
                    _set_commentary(slide, comments)
                    continue
                chart_entries = [
                    (index, entry) for index, entry in slide_entries
                    if index not in hidden_entries
                    and entry.source_kind and dashboard_datasets(snapshot.definition, entry.source_kind, task_repository)
                ]
                if not chart_entries:
                    continue
                layout_name = reflowed_layouts.get(slide_number) or header.layout
                layout = _named_slide_layout(presentation, layout_name)
                placements = _layout_chart_frames(layout)
                if layout is None or len(placements) < len(chart_entries):
                    raise ValueError(f'Slide {slide_number}: the PowerPoint layout has insufficient chart placeholders.')
                if slide_number in reflowed_cells:
                    placements = [placements[reflowed_cells[slide_number][index]] for index, _entry in chart_entries]
                slide = presentation.slides.add_slide(layout)
                _set_slide_header(slide, header.slide_title, header.slide_subtitle)
                with use_theme(theme):
                    style_title(slide)
                if auto_mode != 'off':
                    comment_key = dashboard_slide_comment_key([entry for _index, entry in slide_entries])
                    automatic, writer = auto_slide_comments(
                        snapshot, chart_entries, auto_models, legend_visibility, legend_keys, layout_name, task_repository,
                        auto_engine, user.username,
                    )
                    auto_engines.add(writer)
                    merged = merge_auto_comments(comments, automatic, auto_mode,
                                                 (snapshot.definition.slide_comment_meta.get(comment_key) or {}).get('generated') or [])
                    if merged != comments:
                        comments = merged
                        auto_written[comment_key] = merged
                _clear_commentary(slide)
                _set_commentary(slide, comments)
                _remove_template_chart_placeholders(slide)
                compact_titles = compact_grid_layout(layout_name)
                for chart_number, ((index, entry), placement) in enumerate(zip(chart_entries, placements, strict=False), 1):
                    if not run_is_active():
                        return
                    if compact_titles:
                        # Small grid cells: a readable text title above a title-less chart image.
                        placement = add_dashboard_cell_title(slide, entry, placement)
                    update_dashboard_ppt_job(
                        task_repository, job_id,
                        progress=91 + round(rendered * 4 / max(chart_total, 1)), chart_count=rendered,
                    )
                    render_width, render_height = dashboard_chart_render_size(placement)
                    chart_error = chart_model_errors.get(index)
                    payload = None
                    if chart_error:
                        png = render_unavailable_source_chart(
                            entry, f'Chart unavailable: {chart_error}',
                            width=render_width, height=render_height,
                        )
                        hover_targets = []
                    else:
                        try:
                            model_path = canvas_model_path(snapshot, entry)
                            payload = {**json.loads(model_path.read_text(encoding='utf-8')), 'style': chart_style}
                            if compact_titles:
                                payload = {**payload, 'hide_title': True}
                            hidden_items, shown_items = chart_legend_lists(legend_visibility, legend_keys.get(index))
                            if hidden_items:
                                payload = {**payload, 'hidden_legend_items': hidden_items, 'shown_legend_items': shown_items}
                            png, hover_targets = _render_dashboard_payload(
                                payload, width=render_width, height=render_height,
                            )
                        except Exception as exc:
                            # A renderer defect in one chart must not discard
                            # every other slide in an otherwise valid export.
                            chart_error = f'Chart rendering failed: {exc}'
                            chart_model_errors[index] = chart_error
                            png = render_unavailable_source_chart(
                                entry, chart_error, width=render_width, height=render_height,
                            )
                            hover_targets = []
                    if not run_is_active():
                        return
                    file_name = f'slide-{slide_number:03d}-chart-{chart_number:02d}.png'
                    hover_file = f'slide-{slide_number:03d}-chart-{chart_number:02d}.hover.json'
                    model_file = f'slide-{slide_number:03d}-chart-{chart_number:02d}.model.json'
                    (charts_dir / file_name).write_bytes(png)
                    (charts_dir / hover_file).write_text(
                        json.dumps(hover_targets, ensure_ascii=False), encoding='utf-8',
                    )
                    if payload is not None:
                        (charts_dir / model_file).write_text(
                            json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8',
                        )
                    add_dashboard_chart_picture(slide, png, placement)
                    manifest.append({
                        'slide': slide_number, 'title': entry.chart_title or header.slide_title,
                        'source': entry.cdr_source, 'chart_type': entry.chart_type,
                        'entry_index': index, 'focus_row': focus_rows[index],
                        'file': file_name, 'hover_file': hover_file,
                        'model_file': model_file if payload is not None else '', 'error': chart_error,
                    })
                    rendered += 1
                    update_dashboard_ppt_job(
                        task_repository, job_id,
                        progress=91 + round(rendered * 4 / max(chart_total, 1)), chart_count=rendered,
                    )
            if not run_is_active():
                return
            viewer_slides = []
            for slide in snapshot.payload.get('slides', []):
                number = slide.get('number')
                if number not in reflowed_layouts:
                    viewer_slides.append(slide)
                    continue
                layout_name = reflowed_layouts[number]
                if not layout_name:
                    continue
                positions = normalized_frame_positions(_layout_chart_frames(_named_slide_layout(presentation, layout_name)))
                charts = []
                for chart in slide.get('charts', []):
                    cell = reflowed_cells[number].get(chart.get('index'))
                    if cell is None:
                        continue
                    charts.append({**chart, 'position': positions[cell]} if cell < len(positions) else dict(chart))
                viewer_slides.append({
                    **slide, 'layout': layout_name, 'compact_titles': compact_grid_layout(layout_name), 'charts': charts,
                })
            (charts_dir / 'manifest.json').write_text(
                json.dumps({
                    'generate_tooltips': True,
                    'dashboard_id': dashboard_id,
                    'preview_fingerprint': preview_fingerprint,
                    # The job's viewer shows the comments of the PPT, Auto comments included.
                    'definition': {**snapshot.definition.model_dump(mode='json'), 'slide_comments': {
                        **snapshot.definition.slide_comments, **auto_written,
                    }},
                    # Keep the exact viewer slide structure alongside the
                    # immutable PNG/Canvas assets so a completed PPT job can
                    # later be opened as its own Dashboard snapshot.
                    'slides': viewer_slides,
                    'charts': manifest,
                    # The exact cover lines, so the job's viewer snapshot shows
                    # the same Campaigns, Scope, Regions and Cities as the PPT cover.
                    'cover': {
                        'campaigns': cover_campaigns,
                        'scope': dashboard_ppt_scope_label(snapshot.definition.scope),
                        'regions': cover_regions, 'cities': cover_cities,
                    },
                }, ensure_ascii=False),
                encoding='utf-8',
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            update_dashboard_ppt_job(task_repository, job_id, progress=96, chart_count=rendered)
            report_structure.finish(presentation)
            presentation.save(destination)
            if auto_mode != 'off':
                task_repository.add_log(user.username, 'auto_dashboard_comments', json.dumps({
                    'dashboard_id': dashboard_id, 'job_id': job_id, 'mode': auto_mode, 'requested_engine': auto_engine,
                    'engines': sorted(auto_engines), 'slides_written': len(auto_written),
                }))
            if not run_is_active():
                shutil.rmtree(destination.parent, ignore_errors=True)
                return
            update_dashboard_ppt_job(
                task_repository, job_id, status='ready', progress=100,
                slide_count=len(presentation.slides), chart_count=rendered,
                finished_at=datetime.now(timezone.utc).isoformat(),
            )
            if chart_model_errors:
                task_repository.add_log(user.username, 'export_dashboard_ppt_warning', json.dumps({
                    'dashboard_id': dashboard_id, 'job_id': job_id,
                    'placeholder_charts': [
                        {'slide': snapshot.entries[index].slide, 'error': error}
                        for index, error in chart_model_errors.items()
                    ],
                }, ensure_ascii=False))
        except Exception as exc:
            if run_is_active():
                update_dashboard_ppt_job(
                    task_repository, job_id, status='failed', progress=100, last_error=str(exc),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                task_repository.add_log(user.username, 'export_dashboard_ppt_failed', json.dumps({
                    'dashboard_id': dashboard_id, 'job_id': job_id, 'error': str(exc),
                }, ensure_ascii=False))

    def city_filter_key(filters) -> str | None:
        return next((field for field in filters if identity(field) == identity('City')), None)

    def with_main_cities(filters, task_repository):
        """Filters whose City holds the Main Cities choice, with the Main Cities of the workspace now (every city when
        the workspace has none)."""
        key = city_filter_key(filters)
        values = list(filters.get(key) or []) if key else []
        if MAIN_CITIES not in values:
            return filters
        cities = list(dict.fromkeys([*(value for value in values if value != MAIN_CITIES), *task_repository.list_main_cities()]))
        if cities:
            filters[key] = cities
        else:
            filters.pop(key)
        return filters

    def main_cities_reference(definition, main_cities):
        """A Dashboard whose City filter is exactly the Main Cities (saved before as their names) with the Main Cities choice."""
        if not isinstance(definition, dict) or not main_cities:
            return definition
        filters = dict(definition.get('filters') or {})
        key = city_filter_key(filters)
        values = [str(value) for value in filters.get(key) or []] if key else []
        if not values or {value.casefold() for value in values} != {city.casefold() for city in main_cities}:
            return definition
        filters[key] = [MAIN_CITIES]
        return {**definition, 'filters': filters}

    def read_dashboards(task_repository):
        stored = task_repository.get_workspace_state(STATE_KEY)
        if stored is None:
            stored = task_repository.get_workspace_state(LEGACY_STATE_KEY)
        if stored is None:
            return {}
        dashboards = json.loads(stored or '{}')
        if not isinstance(dashboards, dict):
            return dashboards
        reset_defaults = task_repository.get_workspace_state(DEFAULT_FILTERS_MIGRATION_KEY) != '1'
        try:
            dataset_kinds = {int(row['id']): str(row['dataset_kind'] or '') for row in task_repository.list_datasets()}
        except (AttributeError, sqlite3.Error):
            dataset_kinds = None
        try:
            template_renames, template_uids_now = task_repository.report_template_merge_state()
        except (AttributeError, sqlite3.Error):
            template_renames, template_uids_now = {}, {}
        # Dashboards of before kept an NR Mode of their own and of their template: it is now part of their selection.
        migrated = {
            dashboard_id: migrate_auto_cdrs(normalize_dashboard_filters(
                migrate_dashboard_definition(
                    definition if dataset_kinds is None else existing_dataset_selection(definition, dataset_kinds),
                    template_renames, template_uids_now),
                reset_defaults=reset_defaults,
            ), task_repository)
            for dashboard_id, definition in dashboards.items()
        }
        reference_main_cities = task_repository.get_workspace_state(MAIN_CITIES_MIGRATION_KEY) != '1'
        if reference_main_cities:
            main_cities = task_repository.list_main_cities()
            migrated = {dashboard_id: main_cities_reference(definition, main_cities) for dashboard_id, definition in migrated.items()}
        # Each Dashboard refers to its PPT Template by its identity, so a renamed template is still its template.
        try:
            migrated = follow_template_identities(migrated, template_uids(task_repository))
        except (AttributeError, sqlite3.Error):
            pass
        if migrated != dashboards or reset_defaults or task_repository.get_workspace_state(STATE_KEY) is None:
            task_repository.set_workspace_state(STATE_KEY, json.dumps(migrated))
        if reset_defaults:
            task_repository.set_workspace_state(DEFAULT_FILTERS_MIGRATION_KEY, '1')
        if reference_main_cities:
            task_repository.set_workspace_state(MAIN_CITIES_MIGRATION_KEY, '1')
        return migrated

    def dashboard_slide_comment_key(entries) -> str:
        """Return a position-independent identity for one template slide."""
        signature = [
            {
                'title': entry.slide_title,
                'subtitle': entry.slide_subtitle,
                'layout': entry.layout,
                'structural_type': entry.structural_type or '',
                'chart_title': entry.chart_title,
            }
            for entry in entries
        ]
        encoded = json.dumps(signature, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return f"slide:{sha256(encoded.encode('utf-8')).hexdigest()[:24]}"

    def dashboard_slide_comments(definition: DashboardDefinition, entries) -> tuple[str, list[str]]:
        """Read stable comments while retaining numeric keys from older Dashboards."""
        key = dashboard_slide_comment_key(entries)
        legacy_key = str(entries[0].slide) if entries else ''
        comments = definition.slide_comments.get(key, definition.slide_comments.get(legacy_key, []))
        return key, list(comments or [])

    def rendered_slides(entries, nr_mode) -> dict[str, list]:
        """The chart rows of each slide of a template as a Dashboard of an NR Mode shows them (its comments are kept by
        the titles it shows)."""
        slides: dict[str, list] = defaultdict(list)
        for entry in entries:
            slides[str(entry.slide)].append(entry_for_nr_mode(entry, nr_mode))
        return slides

    def reconcile_template_slide_comments(
        template_name: str, old_entries, new_entries,
        task_repository=None,
    ) -> int:
        """Move comments from legacy/numeric keys to matching stable slide keys."""
        if not old_entries:
            return 0
        # Titles written alike before and after (tokens included) read alike in every NR Mode: the Dashboards need not
        # be read.
        old_raw: dict[str, list] = defaultdict(list)
        new_raw: dict[str, list] = defaultdict(list)
        for entries, slides in ((old_entries, old_raw), (new_entries, new_raw)):
            for entry in entries:
                slides[str(entry.slide)].append(entry)
        if {slide: dashboard_slide_comment_key(entries) for slide, entries in old_raw.items()} == {
                slide: dashboard_slide_comment_key(entries) for slide, entries in new_raw.items()}:
            return 0
        changed = 0
        with lock:
            source_repository = task_repository or bound_repository()
            dashboards = read_dashboards(source_repository)
            for raw_definition in dashboards.values():
                if str(raw_definition.get('template') or '') != template_name:
                    continue
                nr_mode = dashboard_nr_mode(raw_definition)
                old_slides, new_slides = rendered_slides(old_entries, nr_mode), rendered_slides(new_entries, nr_mode)
                available_keys = {dashboard_slide_comment_key(entries) for entries in new_slides.values()}
                if {
                    slide: dashboard_slide_comment_key(entries) for slide, entries in old_slides.items()
                } == {
                    slide: dashboard_slide_comment_key(entries) for slide, entries in new_slides.items()
                }:
                    continue
                original = raw_definition.get('slide_comments') or {}
                migrated = {
                    key: list(values)
                    for key, values in original.items()
                    if key.startswith('slide:') and key in available_keys and values
                }
                for legacy_number, entries in old_slides.items():
                    key = dashboard_slide_comment_key(entries)
                    values = original.get(key, original.get(legacy_number, []))
                    if key in available_keys and values:
                        migrated[key] = list(values)
                original_meta = raw_definition.get('slide_comment_meta') or {}
                migrated_meta = {key: value for key, value in original_meta.items() if key in migrated and key in available_keys}
                for legacy_number, entries in old_slides.items():
                    key = dashboard_slide_comment_key(entries)
                    if key in migrated and key not in migrated_meta and key in original_meta:
                        migrated_meta[key] = original_meta[key]
                if migrated != original or migrated_meta != original_meta:
                    raw_definition['slide_comments'] = migrated
                    raw_definition['slide_comment_meta'] = migrated_meta
                    changed += 1
            if changed:
                source_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
        return changed

    def normalize_dashboard_filters(definition, *, reset_defaults=False):
        """Migrate retired filters and apply the current defaults once per workspace."""
        if not isinstance(definition, dict):
            return definition
        normalized = dict(definition)
        # Scope, source CDRs and dates are stored independently from filters so
        # a Dashboard can restore an explicitly saved Dataset Universe.
        filters = normalized.get('filters')
        retired_filter_keys = {identity('Technology'), identity('Zone')}
        migrated_filters = {}
        region_values = []
        for field, values in (filters.items() if isinstance(filters, dict) else []):
            field_key = identity(field)
            if field_key == identity('Zone'):
                region_values.extend(values or [])
            elif field_key == identity('Region'):
                region_values = list(values or []) + region_values
            elif field_key not in retired_filter_keys:
                migrated_filters[vendor_filter_column(field)] = values
        if region_values:
            migrated_filters['Region'] = list(dict.fromkeys(region_values))
        normalized['filters'] = migrated_filters
        custom_fields = normalized.get('custom_fields')
        normalized['custom_fields'] = [
            vendor_filter_column(field) for field in custom_fields or []
            if identity(field) not in retired_filter_keys and identity(field) != identity('Region')
        ]
        default_keys = {identity(field) for field in ADAPTATIVE_FILTER_FIELDS}
        hidden_filters = normalized.get('hidden_filters')
        normalized['hidden_filters'] = [
            vendor_filter_column(field) for field in hidden_filters or []
            if identity(field) not in retired_filter_keys
            and (not reset_defaults or identity(vendor_filter_column(field)) not in default_keys)
        ]
        return normalized

    def default_campaign_filter(definition) -> list[str]:
        """The Campaign of a new Dashboard: its newest two campaigns, or the newest one for Operator_Vendor."""
        multivendor = definition.get('scope') == 'multivendor' and definition.get('vendor_comparison', 'operator_vendor') == 'operator_vendor'
        return [LATEST_CAMPAIGN if multivendor else LATEST_TWO_CAMPAIGNS]

    def campaign_filter_key(filters) -> str | None:
        return next((field for field in filters if identity(field) == identity('Campaign')), None)

    def follow_nr_mode_campaigns(updated: dict, previous_nr_mode: str, nr_mode: str) -> None:
        """The Campaign filters of a Dashboard whose NR Mode changes: the campaigns of an NR Mode it keeps reading stay
        (the Campaign filter chooses the NSA CDRs and SA Campaign the SA ones with NSA & SA), the others take the newest
        campaigns of the new NR Mode."""
        filters = dict(updated.get('filters') or {})
        key = campaign_filter_key(filters)
        current = list(filters.pop(key) or []) if key else []
        by_mode = {'NSA': current if previous_nr_mode in ('NSA', NSA_VS_SA) else [],
                   'SA': (list(updated.get('sa_campaigns') or []) or current) if previous_nr_mode == NSA_VS_SA
                   else current if previous_nr_mode == 'SA' else []}
        default = default_campaign_filter(updated)
        if nr_mode == NSA_VS_SA:
            filters['Campaign'] = by_mode['NSA'] or default
            updated['sa_campaigns'] = by_mode['SA'] or default
        else:
            filters['Campaign'] = by_mode.get(nr_mode) or default
            updated['sa_campaigns'] = []
        updated['filters'] = filters

    def migrate_auto_cdrs(definition, task_repository):
        """A Dashboard saved when its CDRs were chosen by hand chooses them by Campaign.

        Its saved CDRs become the campaigns they hold, unless it already restricted the Campaign; a
        Dashboard without saved CDRs (which used the newest ones) takes Latest 2 campaigns, or Latest
        campaign for Multivendor Operator_Vendor, as its saved CDRs did.
        """
        if not isinstance(definition, dict) or definition.get('auto_cdrs'):
            return definition
        migrated = dict(definition)
        filters = dict(migrated.get('filters') or {})
        if campaign_filter_key(filters) is None:
            datasets = migrated.get('datasets') if isinstance(migrated.get('datasets'), dict) else {}
            ids = [int(value) for values in datasets.values() for value in (values or []) if str(value).lstrip('-').isdigit()]
            campaigns = sort_campaigns(value for values in cdr_campaigns(task_repository, ids).values() for value in values) if ids else []
            filters['Campaign'] = campaigns or default_campaign_filter(migrated)
        migrated['filters'] = filters
        migrated.pop('datasets', None)
        migrated['auto_cdrs'] = True
        return migrated

    def runtime_dashboard_definition(definition, task_repository):
        """A Dashboard definition with its CDRs: those of its NR Mode and Campaign filter.

        The CDRs are those the combined CDR tables include (the Final CDR of each campaign, else its
        newest Weekly or Daily CDRs, or the In Combined? choice of Workspace), of the Dashboard's NR
        Mode and of the campaigns of its Campaign filter (every campaign without one). Latest campaign
        and Latest 2 campaigns are replaced by the newest campaigns now.
        """
        effective = migrate_auto_cdrs(normalize_dashboard_filters(definition), task_repository)
        effective.setdefault('scope', 'single')
        nr_mode = dashboard_nr_mode(effective)
        filters = with_main_cities(dict(effective.get('filters') or {}), task_repository)
        key = campaign_filter_key(filters)
        campaigns = list(filters.get(key) or []) if key else []
        if nr_mode == NSA_VS_SA:
            # NSA & SA: the CDRs of each NR Mode, chosen by its own Campaign filter (the SA one, or the Campaign one).
            sa_campaigns = [str(value) for value in effective.get('sa_campaigns') or [] if str(value).strip()] or campaigns
            by_mode = {'NSA': resolve_campaign_filter(task_repository, 'NSA', campaigns),
                       'SA': resolve_campaign_filter(task_repository, 'SA', sa_campaigns)}
            datasets = {kind: [] for kind in KINDS}
            for mode, mode_campaigns in by_mode.items():
                for kind, ids in resolve_cdrs(task_repository, mode, mode_campaigns, KINDS).items():
                    datasets.setdefault(kind, []).extend(ids)
            effective['datasets'] = datasets
            # Their campaigns, unless an NR Mode takes every campaign (its CDRs are already chosen).
            campaigns = sort_campaigns({*by_mode['NSA'], *by_mode['SA']}) if all(by_mode.values()) else []
            if campaigns:
                filters[key or 'Campaign'] = campaigns
            elif key:
                filters.pop(key)
            key = campaign_filter_key(filters)
        else:
            if key and campaign_presets(campaigns):
                campaigns = resolve_campaign_filter(task_repository, nr_mode, campaigns)
                if campaigns:
                    filters[key] = campaigns
                else:
                    # CDRs without campaigns: every CDR of the NR Mode.
                    filters.pop(key)
            effective['datasets'] = resolve_cdrs(task_repository, nr_mode, campaigns, KINDS)
        if key and campaigns:
            # CDRs that hold only chosen campaigns need no Campaign predicate on their rows: the selection
            # stays a complete, unfiltered universe whose counts and options are known.
            ids = [dataset_id for values in effective['datasets'].values() for dataset_id in values]
            held = {campaign_identity(value) for values in cdr_campaigns(task_repository, ids).values() for value in values}
            if held and held <= {campaign_identity(value) for value in campaigns}:
                filters.pop(key)
        effective['filters'] = filters
        effective.setdefault('date_from', 'Oldest')
        effective.setdefault('date_to', 'Newest')
        return effective

    def auto_cdr_definition(definition: DashboardDefinition, task_repository) -> DashboardDefinition:
        """A Dashboard sent by the browser with the CDRs of its NR Mode and Campaign filter."""
        return DashboardDefinition.model_validate(runtime_dashboard_definition(definition.model_dump(mode='json'), task_repository))

    def automatic_scope_universe(definition: DashboardDefinition, task_repository) -> DashboardDefinition:
        """The Dashboard of a library PPT export, with automatic dates."""
        raw_definition = definition.model_dump(mode='json')
        for field in ('date_from', 'date_to'):
            raw_definition.pop(field, None)
        return DashboardDefinition.model_validate(runtime_dashboard_definition(raw_definition, task_repository))

    def cascading_dashboard_options(options, definition, task_repository):
        """The Operator, Vendor, Region, Cluster, City and Campaign lists of every CDR of the NR Mode.

        Each lists only the values the other filters leave, read from the CDR Filter Facets (never the
        CDR rows); the other filters keep the values of the Dashboard's CDRs.
        """
        raw = definition.model_dump(mode='json') if hasattr(definition, 'model_dump') else dict(definition)
        nr_mode = dashboard_nr_mode(raw)
        candidates = [row['id'] for row in candidate_cdrs(task_repository, nr_mode)]
        # The Campaign lists every campaign of the NR Mode; the other filters, the values of the CDRs it chooses.
        resolved = [int(value) for values in (raw.get('datasets') or {}).values() for value in values]
        filters = raw.get('filters') or {}
        fields = [field for field in options if field in CASCADING_FILTER_FIELDS] or list(CASCADING_FILTER_FIELDS)
        cascading = {}
        if 'Campaign' in fields and nr_mode == NSA_VS_SA:
            # NSA & SA: the Campaign filter lists the campaigns of the NSA CDRs and SA Campaign those of the SA ones.
            for mode, field in (('NSA', 'Campaign'), ('SA', SA_CAMPAIGN_FIELD)):
                ids = [row['id'] for row in candidate_cdrs(task_repository, mode)]
                cascading[field] = cascading_options(task_repository, ids, filters, ['Campaign']).get('Campaign', [])
        elif 'Campaign' in fields:
            cascading.update(cascading_options(task_repository, candidates, filters, ['Campaign']))
        if others := [field for field in fields if field != 'Campaign']:
            cascading.update(cascading_options(task_repository, resolved or candidates, filters, others))
        return {**options, **cascading}

    def catalogue(definition, task_repository=None):
        """The chart rows of a Dashboard's template, their titles naming the NR Mode it reads."""
        task_repository = task_repository or core.repository
        rows = task_repository.list_report_templates()
        row = next((row for row in rows if row['name'] == definition.template), None)
        if row is None:
            raise HTTPException(400, 'The selected template is no longer available.')
        try:
            return core.load_template_catalogue(bytes(row['content']), task_repository=task_repository,
                                                nr_mode=dashboard_nr_mode(definition))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    def validate(definition, task_repository=None):
        if not definition.name.strip():
            raise HTTPException(400, 'Enter a Dashboard name.')
        if (
            not ignore_event_time_filtering()
            and isinstance(definition.date_from, date)
            and isinstance(definition.date_to, date)
            and definition.date_from > definition.date_to
        ):
            raise HTTPException(400, 'The start date must not follow the end date.')
        if set(definition.datasets) - set(KINDS):
            raise HTTPException(400, 'Unsupported dataset type.')
        entries = catalogue(definition, task_repository)
        return entries

    def add_dynamic_grid_metadata(payload, entries, deck=None) -> None:
        """Add each grid card's dynamic values and the smaller grids it can reflow to.

        Hiding a dynamic value removes its grid row or column; the viewer lays
        the remaining cards out on the same smaller grid the PPT export uses.
        """
        grids = set()
        for slide in payload.get('slides', []):
            for chart in slide.get('charts', []):
                index = chart.get('index')
                values = dynamic_chart_values(entries[index]) if isinstance(index, int) and 0 <= index < len(entries) else []
                if values:
                    chart['dynamic_values'] = values
            grid = GRID_LAYOUT_PATTERN.fullmatch(canonical_layout_name(slide.get('layout') or ''))
            if grid and any(chart.get('dynamic_values') for chart in slide.get('charts', [])):
                grids.add((int(grid.group(1)), int(grid.group(2)), grid.group(3) or ''))
        names = {
            grid_layout_name(rows, columns, comments)
            for row_limit, column_limit, comments in grids
            for rows in range(1, row_limit + 1) for columns in range(1, column_limit + 1)
        }
        if names and deck is None:
            deck = Presentation(core.settings.powerpoint_template)
        payload['grid_layouts'] = {
            name: normalized_frame_positions(_layout_chart_frames(_named_slide_layout(deck, name)))
            for name in sorted(names)
        }

    def expand_dashboard_layouts(entries, definition, options, task_repository):
        effective_entries = [prepare_multivendor_catalog_entry(entry, definition.vendor_comparison) if definition.scope == "multivendor" else entry for entry in entries]
        dynamic_fields = {field for entry in effective_entries for field in entry_dynamic_fields(entry) if field}
        mappings = task_repository.chart_mapping_settings()['operator_mappings']
        values_by_field = {}
        for field in dynamic_fields:
            vendor_mappings = task_repository.chart_mapping_settings()['vendor_mappings']
            normalize = ((lambda value: _normalise_operator_label(value, mappings)) if identity(field) == 'operator' else
                         (lambda value: _normalise_vendor(value, mappings, vendor_mappings)) if identity(field) in {'vendor', 'vendoronly', 'operatorvendor'} else str)
            raw_values = next((values for key, values in options.items() if identity(key) == identity(field)), [])
            values = {normalize(value) for value in raw_values if str(value).strip()}
            selected_values = next((items for key, items in definition.filters.items() if identity(key) == identity(field)), [])
            if selected_values:
                values &= {normalize(value) for value in selected_values}
            if definition.scope == 'multivendor' and definition.vendor_comparison != 'vendor_only' and identity(field) in {'operatorvendor', 'vendor'}:
                values = {value for value in values if not any(term in value.casefold() for term in ('mixed', 'other'))}
            values_by_field[field] = sorted(values, key=str.casefold)
        vendor_families = {}
        if definition.scope == 'multivendor' and definition.vendor_comparison == 'operator_vendor':
            settings = task_repository.chart_mapping_settings()
            with task_repository.connection() as connection:
                for kind, ids in definition.datasets.items():
                    if not ids:
                        continue
                    columns = task_repository.list_reporting_row_columns(kind)
                    vendor_column = resolve_sql_column(columns, 'Operator_Vendor')
                    family_column = resolve_sql_column(columns, 'Vendor')
                    if not vendor_column or not family_column:
                        continue
                    quote = task_repository._quote_identifier
                    rows = connection.execute(
                        f'SELECT DISTINCT {quote(vendor_column)}, {quote(family_column)} FROM {quote(task_repository.reporting_rows_table_name(kind))} '
                        f'WHERE dataset_id IN ({", ".join("?" for _ in ids)})', ids,
                    ).fetchall()
                    for vendor, family in rows:
                        if vendor and family:
                            vendor_families[_normalise_vendor(vendor, mappings, settings['vendor_mappings'])] = str(family)
        chart_mapping_settings = task_repository.chart_mapping_settings()
        return expand_dynamic_layouts(entries, values_by_field, multivendor=definition.scope == 'multivendor',
                                      operator_mappings=mappings, vendor_mappings=chart_mapping_settings['vendor_mappings'], vendor_comparison=definition.vendor_comparison, vendor_families=vendor_families,
                                      mapping_groups=chart_mapping_settings)

    @app.get('/ppt-dashboards', response_class=HTMLResponse)
    def page(request: Request, user=Depends(dashboard_user)):
        workspace = workspace_key()
        with lock:
            dashboards = read_dashboards(bound_repository())
        # Start cache preparation as soon as the PPT Dashboards module opens.
        # It must not depend on the browser opening a Dashboard or its filters.
        for dashboard_id, raw_definition in dashboards.items():
            if isinstance(raw_definition, dict):
                schedule_dashboard_warmup(workspace, dashboard_id, raw_definition, user.username)
        ready = [core.serialize_dataset_row(row) for row in core.repository.list_datasets() if row['status'] == 'ready']
        core.backfill_cdr_catalogues(row['id'] for row in ready if row.get('dataset_kind') in KINDS)
        catalogue = core.repository.cdr_catalogue_values(
            row['id'] for row in ready if row.get('dataset_kind') in KINDS
        )
        return core.render_template(request, 'ppt_dashboards.html', {
            'user': user, 'dashboard_datasets': {kind: [row for row in ready if row.get('dataset_kind') == kind] for kind in KINDS},
            # Any template serves the CDRs of any NR Mode.
            'dashboard_templates': [{'name': row['name'], 'identifier': row['identifier'], 'active': row['active']}
                                    for row in core.report_catalogue_options()],
            'dashboard_workspace_id': core.active_workspace.id,
            'calculated_dimensions': core.calculated_dimensions_json(core.load_workspace_calculated_dimensions()),
            'dashboard_filter_fields': ADAPTATIVE_FILTER_FIELDS,
            'dashboard_filter_aliases': {
                field: list(aliases) for field, aliases in FILTER_COLUMNS.items() if len(aliases) > 1
            },
            'dashboard_ignore_event_time_filtering': ignore_event_time_filtering(),
            'dashboard_multivendor_available': len(catalogue['vendors']) >= 2,
            'dashboard_main_cities': core.repository.list_main_cities(),
            # The colour theme of the charts and slide titles of the viewer and of the Dashboard PPTs.
            'dashboard_themes': themes_payload()['themes'],
            'dashboard_theme': load_user_theme(bound_repository(), user.username, DASHBOARD_THEME_MODULE),
            'dashboard_chart_styles': {key: dashboard_chart_style(key) for key in THEMES},
            'dashboard_viewer_tokens': {key: dashboard_viewer_tokens(key) for key in THEMES},
        })

    @app.get('/api/ppt-dashboards/theme')
    def dashboard_theme(user=Depends(dashboard_user)):
        """The colour theme the user chose for the PPT Dashboards charts and slide titles in this workspace."""
        theme = load_user_theme(bound_repository(), user.username, DASHBOARD_THEME_MODULE)
        return {'theme': theme, 'style': dashboard_chart_style(theme)}

    @app.put('/api/ppt-dashboards/theme')
    def dashboard_theme_save(payload: DashboardThemeRequest, user=Depends(dashboard_user)):
        if payload.theme.strip().casefold() not in THEMES:
            raise HTTPException(400, f'Unknown theme: {payload.theme}.')
        task_repository = bound_repository()
        previous = load_user_theme(task_repository, user.username, DASHBOARD_THEME_MODULE)
        theme = save_user_theme(task_repository, user.username, payload.theme, DASHBOARD_THEME_MODULE)
        if theme != previous:
            task_repository.try_add_log(user.username, 'ppt_dashboards_theme_changed', json.dumps({'theme': theme, 'previous': previous}))
        return {'theme': theme, 'style': dashboard_chart_style(theme)}

    @app.get('/api/ppt-dashboards')
    def list_dashboards(user=Depends(dashboard_user)):
        workspace = workspace_key()
        with lock:
            task_repository = bound_repository()
            dashboards = read_dashboards(task_repository)
            known = creators(task_repository, PPT_DASHBOARDS)
        # Covers existing Dashboards created before automatic warm-up was
        # introduced.  The scheduler de-duplicates each Dashboard per process.
        for dashboard_id, raw_definition in dashboards.items():
            if isinstance(raw_definition, dict):
                schedule_dashboard_warmup(workspace, dashboard_id, raw_definition, user.username)
        # Each Dashboard with who created it: only they, admins and super-admins delete it.
        return JSONResponse(
                {dashboard_id: {**definition, 'created_by': known.get(str(dashboard_id).casefold(), '')}
                 if isinstance(definition, dict) else definition for dashboard_id, definition in dashboards.items()},
            headers={'Cache-Control': 'no-store, max-age=0, must-revalidate'},
        )

    @app.get('/api/ppt-dashboards/{dashboard_id}/export')
    def export_dashboard_definition(dashboard_id: str, user=Depends(dashboard_user)):
        """Create the same Dashboard archive accepted by Admin Import."""
        task_repository = bound_repository()
        with lock:
            definition = read_dashboards(task_repository).get(dashboard_id)
        if not isinstance(definition, dict):
            raise HTTPException(404, 'Dashboard not found.')
        workspace = core.active_workspace
        workspace_name = str(workspace.name if workspace else 'Workspace')
        archive_path = f'workspaces/{workspace_name}/dashboards/dashboards.json'
        payload = json.dumps({
            'format': 'drivetest-analyzer-dashboards', 'version': 1,
            'dashboards': {dashboard_id: definition},
        }, ensure_ascii=False, indent=2).encode('utf-8')
        temporary = tempfile.NamedTemporaryFile(prefix='dashboard-export-', suffix='.zip', delete=False)
        temporary.close()
        archive = Path(temporary.name)
        try:
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
                bundle.writestr('manifest.json', json.dumps({
                    'format': 'drivetest-analyzer-export', 'version': 1, 'kind': 'dashboards',
                    'components': ['workspace_components'], 'workspace_components': ['dashboards'],
                    'source_workspace': {'id': workspace.id, 'name': workspace_name} if workspace else {},
                    'archive_path': archive_path,
                }, indent=2, sort_keys=True))
                bundle.writestr(archive_path, payload)
        except Exception:
            archive.unlink(missing_ok=True)
            raise
        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', str(definition.get('name') or dashboard_id)).strip('._') or 'Dashboard'
        task_repository.try_add_log(user.username, 'export_dashboard_definition', json.dumps({
            'id': dashboard_id, 'name': str(definition.get('name') or ''),
        }))
        return FileResponse(
            archive, filename=f'{safe_name}_dashboard.zip', media_type='application/zip',
            background=BackgroundTask(archive.unlink, missing_ok=True),
        )

    def dashboard_ppt_output_dir(task_repository) -> Path:
        return module_output_dir(Path(task_repository.db_path).parent / 'output', DASHBOARDS_FOLDER)

    def remove_dashboard_ppt_job_folder(task_repository, output_path) -> None:
        """Delete one job folder, never anything outside the Dashboard output root."""
        text = str(output_path or '').strip()
        if not text:
            return
        folder = Path(text).parent.resolve()
        root = dashboard_ppt_output_dir(task_repository).resolve()
        if folder == root or root not in folder.parents:
            return
        shutil.rmtree(folder, ignore_errors=True)

    def dashboard_ppt_campaign_suffix(campaigns: list[str]) -> str:
        """Return ``2026-Q1_vs_2026-Q2`` for exports that compare several Campaigns."""
        return '_vs_'.join(campaigns) if len(campaigns) > 1 else ''

    def dashboard_ppt_unique_output(
        task_repository, export_time, nr_mode_label, dashboard_name, scope_label, zone_label, job_id=None,
        campaign_suffix='',
    ):
        """Return a unique ``timestamp - NR Mode - Dashboard - Scope - Regions - Campaigns`` file and folder."""
        for offset in range(60):
            output_file = build_cdr_report_filename(
                export_time + timedelta(seconds=offset), nr_mode_label, dashboard_name,
                scope_label, zone_label, campaign_suffix,
            )
            job_dir = dashboard_ppt_output_dir(task_repository) / Path(output_file).stem
            with task_repository.connection() as connection:
                already_queued = connection.execute(
                    f'SELECT 1 FROM {DASHBOARD_PPT_JOBS_TABLE} WHERE output_file = ? AND id IS NOT ? LIMIT 1',
                    (output_file, job_id),
                ).fetchone()
            if not already_queued and not job_dir.exists():
                return output_file, job_dir / output_file
        raise HTTPException(503, 'No unique PowerPoint filename is available for this export.')

    def queue_dashboard_ppt_export(
        dashboard_id, user, *, reuse_job_id=None, export_definition: DashboardDefinition | None = None,
        preparation_token: str | None = None, selected_operators: list[str] | None = None,
        selected_vendors: list[str] | None = None, selected_regions: list[str] | None = None,
        selected_cities: list[str] | None = None, legend_visibility: dict | None = None, theme: str | None = None,
        auto_comments: str | None = None, auto_comments_engine: str | None = None,
    ):
        """Create the export job immediately; all preparation runs in the background job (``theme``: the colour theme
        of a report generating it, else the user's PPT Dashboards theme; ``auto_comments``: the Auto comments mode, kept
        by a relaunched job when None)."""
        task_repository = bound_repository()
        workspace = workspace_key()
        # Preparation and pre-caching never block an export: the queued job
        # waits for the shared Dashboard work slot and pre-caches its universe.
        with lock:
            stored_definition = read_dashboards(task_repository).get(dashboard_id)
        if not isinstance(stored_definition, dict):
            raise HTTPException(404, 'Dashboard not found.')
        raw_definition = export_definition.model_dump(mode='json') if export_definition is not None else dict(stored_definition)
        if dashboard_nr_mode(raw_definition) != dashboard_nr_mode(stored_definition):
            # The comments of a Dashboard were written for the CDRs of its own NR Mode: generated in another one (by a
            # Reporting Job or a Bundle Report Template), its slides go without them, unless auto comments write them.
            raw_definition = {**raw_definition, 'slide_comments': {}, 'slide_comment_meta': {}}
        explicit_selections = {
            field: list(dict.fromkeys(str(value).strip() for value in selected if str(value).strip()))
            for field, selected in (
                ('Operator', selected_operators), ('Vendor', selected_vendors),
                ('Region', selected_regions), ('City', selected_cities),
            ) if selected is not None
        }
        # An active snapshot supplied by the viewer is only looked up in memory.
        snapshot = None
        if preparation_token and not explicit_selections:
            with lock:
                candidate = snapshots.get(preparation_token)
            if (
                candidate is not None
                and candidate.workspace == workspace
                and candidate.owner in {user.username, '*'}
                and (export_definition is None or candidate.definition.scope == export_definition.scope and candidate.definition.vendor_comparison == export_definition.vendor_comparison)
            ):
                snapshot = candidate
        dashboard_name = str(raw_definition.get('name') or dashboard_id)
        nr_mode = dashboard_nr_mode(raw_definition)
        # The file names the NR Mode the Dashboard reads (NSA & SA for both).
        nr_mode_label = DASHBOARD_NR_MODE_LABELS[nr_mode]
        scope = 'multivendor' if str(raw_definition.get('scope') or 'single') == 'multivendor' else 'single'
        export_time = datetime.now()
        ensure_dashboard_ppt_jobs(task_repository)
        # A provisional, always valid output path; the background job adds the
        # selected Regions once it has resolved them.
        output_file, destination = dashboard_ppt_unique_output(
            task_repository, export_time, nr_mode_label, dashboard_name, dashboard_ppt_scope_label(scope), '', reuse_job_id,
        )
        common = {
            'dashboard_name': dashboard_name, 'template_name': str(raw_definition.get('template') or ''),
            'nr_mode': nr_mode.casefold(), 'scope': scope, 'filters_json': '[]',
            'output_file': output_file, 'output_path': str(destination),
            'vendor_comparison': raw_definition.get('vendor_comparison') or 'operator_vendor',
        }
        if reuse_job_id is None:
            with task_repository.connection() as connection:
                cursor = connection.execute(
                    f'''INSERT INTO {DASHBOARD_PPT_JOBS_TABLE} (
                        dashboard_id, dashboard_name, template_name, nr_mode, scope, regions_json, selections_json, filters_json, output_file, output_path,
                        created_by, created_at, status, progress
                    ) VALUES (?, ?, ?, ?, ?, '[]', '{{}}', ?, ?, ?, ?, ?, 'queued', 0)''',
                    (
                        dashboard_id, common['dashboard_name'], common['template_name'], common['nr_mode'], common['scope'],
                        common['filters_json'], output_file, str(destination), user.username,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                job_id = int(cursor.lastrowid)
            update_dashboard_ppt_job(task_repository, job_id, vendor_comparison=common['vendor_comparison'])
            previous_output = ''
        else:
            job_id = int(reuse_job_id)
            previous_output = str(dashboard_ppt_job(task_repository, job_id)['output_path'] or '')
            update_dashboard_ppt_job(
                task_repository, job_id, **common, created_at=datetime.now(timezone.utc).isoformat(),
                status='queued', progress=0, slide_count=0, chart_count=0,
                last_error='', started_at=None, finished_at=None,
            )
        if auto_comments is not None:
            update_dashboard_ppt_job(task_repository, job_id,
                                     auto_comments=auto_comments if auto_comments in AUTO_COMMENT_MODES else 'off',
                                     auto_comments_engine=str(auto_comments_engine or ''))
        if legend_visibility is not None:
            # A relaunched job keeps the legend state it was created with.
            update_dashboard_ppt_job(
                task_repository, job_id,
                legend_visibility_json=json.dumps(normalized_legend_visibility(legend_visibility), ensure_ascii=False),
            )
        run_token = uuid4().hex
        with lock:
            dashboard_ppt_runs[(str(Path(task_repository.db_path).resolve()), job_id)] = run_token
            snapshot_token = next((token for token, value in snapshots.items() if value is snapshot), '')
            if snapshot_token:
                dashboard_ppt_data_tokens[(str(Path(task_repository.db_path).resolve()), job_id, user.username)] = snapshot_token
        core.submit_background_task(
            prepare_and_render_dashboard_ppt_job,
            job_id, run_token, task_repository, user, dashboard_id, raw_definition,
            explicit_selections, snapshot, export_time, previous_output, theme,
        )
        task_repository.add_log(user.username, 'export_dashboard_ppt', json.dumps({
            'dashboard_id': dashboard_id, 'job_id': job_id, 'output': str(destination),
            'auto_comments': str(dashboard_ppt_job(task_repository, job_id)['auto_comments'] or 'off'),
            'theme': normalize_theme(theme) if theme else load_user_theme(task_repository, user.username, DASHBOARD_THEME_MODULE),
        }))
        return job_id

    def stop_reporting_dashboard_job(task_repository, job_id) -> None:
        """Stop the Dashboard PPT job a Reporting Job run waits for, when the run is stopped."""
        row = dashboard_ppt_job(task_repository, job_id)
        if row is not None and str(row['status']) in {'queued', 'processing'}:
            update_dashboard_ppt_job(task_repository, job_id, status='stopped', finished_at=datetime.now(timezone.utc).isoformat())

    # Reporting Jobs and Bundle Report Templates generate Dashboard PPTs through the PPT jobs.
    core.dashboard_reporting = SimpleNamespace(
        definition_model=DashboardDefinition,
        list_dashboards=lambda task_repository: read_dashboards(task_repository),
        queue_export=lambda dashboard_id, user, definition=None, theme=None, auto_comments=None, auto_comments_engine=None: queue_dashboard_ppt_export(
            dashboard_id, user, export_definition=DashboardDefinition.model_validate(definition) if definition is not None else None,
            theme=theme, auto_comments=auto_comments, auto_comments_engine=auto_comments_engine,
        ),
        job=dashboard_ppt_job,
        serialize_job=lambda row: serialize_dashboard_ppt_job(row),
        stop_job=stop_reporting_dashboard_job,
    )

    def prepare_and_render_dashboard_ppt_job(
        job_id, run_token, task_repository, user, dashboard_id, raw_definition,
        explicit_selections, snapshot, export_time, previous_output, theme=None,
    ):
        """Resolve the export universe, labels and file name, then render the PPT."""
        run_key = (str(Path(task_repository.db_path).resolve()), job_id)
        with lock:
            if dashboard_ppt_runs.get(run_key) != run_token:
                return
        try:
            update_dashboard_ppt_job(
                task_repository, job_id, status='processing', progress=1,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            if previous_output:
                remove_dashboard_ppt_job_folder(task_repository, previous_output)
            # The CDRs of its NR Mode and Campaign filter, chosen now.
            raw_definition = runtime_dashboard_definition(dict(raw_definition), task_repository)
            if explicit_selections:
                raw_filters = dict(raw_definition.get('filters') or {})
                for field, selected in explicit_selections.items():
                    for existing in list(raw_filters):
                        if identity(vendor_filter_column(existing)) == identity(vendor_filter_column(field)):
                            del raw_filters[existing]
                    if selected:
                        raw_filters[field] = selected
                raw_definition['filters'] = raw_filters
            snapshot_definition = DashboardDefinition.model_validate(raw_definition)
            # A reused snapshot carries resolved calendar dates; the job Filters
            # column keeps the requested (possibly symbolic) range either way.
            requested_dates = {key: raw_definition.get(key) for key in ('date_from', 'date_to')}
            if snapshot is not None:
                try:
                    snapshot = validate_dashboard_export_snapshot(snapshot, task_repository)
                    raw_definition = snapshot.definition.model_dump(mode='json')
                except (ValueError, HTTPException):
                    snapshot = None
            dashboard_name = str(raw_definition.get('name') or dashboard_id)
            preview_fingerprint = dashboard_preview_fingerprint(raw_definition, task_repository)
            selected_by_kind = selected_sources(snapshot_definition, task_repository)
            catalogue = dashboard_geography_catalogue(snapshot_definition, selected_by_kind, task_repository)
            # Available values come only from the selected CDRs, never from
            # the Dashboard's saved filters.
            profile_options = profile_filter_options(
                unfiltered_definition(snapshot_definition), [], selected_by_kind,
                ['Operator', 'Region', 'City'], task_repository,
            )
            available = {
                'Operator': profile_options['Operator'], 'Vendor': catalogue['vendors'],
                'Region': catalogue['regions'], 'City': catalogue['cities'],
            }
            requested = {field: explicit_selections.get(field, []) for field in ('Operator', 'Vendor', 'Region', 'City')}
            filters = raw_definition.get('filters') or {}
            selections = {
                field: dashboard_ppt_selection_values(filters, field, requested[field], values)
                for field, values in available.items()
            }
            selection_labels = {
                field: dashboard_ppt_selection_label(
                    field, selections[field], values,
                    # Dialog selections are chosen from the catalogue; only saved
                    # Dashboard filters come from the filter options.
                    (profile_options[field],) if field in {'Region', 'City'} and field not in explicit_selections else (),
                )
                for field, values in available.items()
            }
            campaigns = dashboard_campaign_values(snapshot_definition, selected_by_kind, task_repository)[0]
            cover_campaigns = dashboard_campaigns_label(campaigns)
            filters_json = json.dumps(dashboard_filter_lines(
                {**raw_definition, **requested_dates}, task_repository,
                {**selection_labels, 'Campaign': cover_campaigns},
            ), ensure_ascii=False)
            selected_regions, selected_cities = selections['Region'], selections['City']
            region_label, city_label = selection_labels['Region'], selection_labels['City']
            cover_regions = dashboard_ppt_cover_label('Region', region_label, len(selected_regions))
            cover_cities = dashboard_ppt_cover_label('City', city_label, len(selected_cities))
            zone_label = region_label if region_label == 'All Regions' else ' + '.join(selected_regions)
            output_file, destination = dashboard_ppt_unique_output(
                task_repository, export_time, DASHBOARD_NR_MODE_LABELS[dashboard_nr_mode(raw_definition)], dashboard_name,
                dashboard_ppt_scope_label(raw_definition.get('scope') or 'single'), zone_label, job_id,
                dashboard_ppt_campaign_suffix(campaigns),
            )
            update_dashboard_ppt_job(
                task_repository, job_id, regions_json=json.dumps(selected_regions, ensure_ascii=False),
                selections_json=json.dumps(selections, ensure_ascii=False), filters_json=filters_json,
                output_file=output_file, output_path=str(destination),
            )
        except Exception as exc:
            with lock:
                active = dashboard_ppt_runs.get(run_key) == run_token
            if active:
                detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                update_dashboard_ppt_job(
                    task_repository, job_id, status='failed', last_error=str(detail),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
            return
        render_dashboard_ppt_job(
            job_id, run_token, task_repository, snapshot, snapshot_definition, user, destination,
            dashboard_id, preview_fingerprint, cover_regions, cover_cities, cover_campaigns, theme,
        )

    @app.post('/api/ppt-dashboards/{dashboard_id}/export-ppt')
    def export_dashboard_ppt(
        dashboard_id: str, request: DashboardPptExportRequest | None = None,
        user=Depends(dashboard_user),
    ):
        job_id = queue_dashboard_ppt_export(
            dashboard_id, user,
            export_definition=request.definition if request else None,
            preparation_token=request.preparation_token if request else None,
            selected_operators=request.selected_operators if request else None,
            selected_vendors=request.selected_vendors if request else None,
            selected_regions=request.selected_regions if request else None,
            selected_cities=request.selected_cities if request else None,
            legend_visibility=request.legend_visibility if request else None,
            auto_comments=request.auto_comments if request else None,
            auto_comments_engine=request.auto_comments_engine if request else None,
        )
        return JSONResponse({'job_id': job_id, 'status': 'queued'}, status_code=202)

    @app.get('/api/ppt-dashboards/ppt-jobs')
    def dashboard_ppt_jobs(user=Depends(dashboard_user)):
        task_repository = bound_repository()
        ensure_dashboard_ppt_jobs(task_repository)
        with task_repository.connection() as connection:
            rows = connection.execute(
                # Newest first: a relaunched job takes the date of its relaunch and moves to the top.
                f'SELECT * FROM {DASHBOARD_PPT_JOBS_TABLE} ORDER BY created_at DESC, id DESC LIMIT 100'
            ).fetchall()
        return {'jobs': [serialize_dashboard_ppt_job(row) for row in rows]}

    @app.get('/api/ppt-dashboards/ppt-jobs/{job_id}/download')
    def download_dashboard_ppt(job_id: int, user=Depends(dashboard_user)):
        task_repository = bound_repository()
        row = dashboard_ppt_job(task_repository, job_id)
        path = Path(str(row['output_path'])) if row else None
        if row is None or str(row['status']) != 'ready' or not path.is_file():
            raise HTTPException(404, 'Dashboard PowerPoint is not available.')
        task_repository.try_add_log(user.username, 'download_dashboard_ppt', json.dumps({'job_id': job_id, 'file': path.name}))
        return FileResponse(
            path, filename=path.name,
            media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        )

    @app.get('/api/ppt-dashboards/ppt-jobs/{job_id}/charts')
    def open_dashboard_ppt_charts(job_id: int, user=Depends(dashboard_user)):
        row = dashboard_ppt_job(bound_repository(), job_id)
        if row is None:
            raise HTTPException(404, 'Dashboard charts are not available.')
        charts_dir = Path(str(row['output_path'])).parent / 'dashboard-charts'
        try:
            manifest = json.loads((charts_dir / 'manifest.json').read_text(encoding='utf-8'))
        except (AttributeError, OSError, json.JSONDecodeError):
            raise HTTPException(404, 'Dashboard charts are not available.')
        cards = ''.join(
            f'<article><h2>{html.escape(str(item.get("title") or "Chart"))}</h2>'
            f'<img src="/api/ppt-dashboards/ppt-jobs/{job_id}/charts/{html.escape(str(item.get("file") or ""))}" alt=""></article>'
            for item in manifest.get('charts', []) if isinstance(item, dict)
        )
        return HTMLResponse(
            '<!doctype html><html><head><title>Dashboard charts</title><style>'
            'body{font-family:Arial;margin:24px;background:#f5f2f8}article{margin:0 0 24px;padding:16px;background:white;border-radius:12px}'
            'img{display:block;width:100%;height:auto}h2{font-size:18px}</style></head><body>' + cards + '</body></html>'
        )

    @app.get('/api/ppt-dashboards/ppt-jobs/{job_id}/charts.json')
    def dashboard_ppt_charts_manifest(job_id: int, user=Depends(dashboard_user)):
        row = dashboard_ppt_job(bound_repository(), job_id)
        if row is None:
            raise HTTPException(404, 'Dashboard charts are not available.')
        charts_dir = Path(str(row['output_path'])).parent / 'dashboard-charts'
        try:
            manifest = json.loads((charts_dir / 'manifest.json').read_text(encoding='utf-8'))
        except (AttributeError, OSError, json.JSONDecodeError):
            raise HTTPException(404, 'Dashboard charts are not available.')
        charts = []
        definition_available = isinstance(manifest.get('definition'), dict)
        fallback_focus_rows = []
        if any(not isinstance(item.get('focus_row'), int) for item in manifest.get('charts', []) if isinstance(item, dict)):
            try:
                definition = DashboardDefinition(
                    name=str(row['dashboard_name']), template=str(row['template_name']),
                    nr_mode=dashboard_nr_mode_value(row['nr_mode']),
                    scope='multivendor' if str(row['scope']).casefold() == 'multivendor' else 'single',
                )
                entries = validate(definition, bound_repository())
                focus_by_index = {
                    entry_index: editor_index
                    for editor_index, (entry_index, _entry) in enumerate(
                        sorted(enumerate(entries), key=lambda value: (value[1].slide, value[0]))
                    )
                }
                unused = set(range(len(entries)))
                for item in manifest.get('charts', []):
                    matched = next((
                        entry_index for entry_index, entry in enumerate(entries)
                        if entry_index in unused
                        and entry.slide == int(item.get('slide') or 0)
                        and str(entry.chart_title or entry.slide_title) == str(item.get('title') or '')
                        and str(entry.cdr_source) == str(item.get('source') or '')
                        and str(entry.chart_type) == str(item.get('chart_type') or '')
                    ), None)
                    fallback_focus_rows.append(focus_by_index.get(matched) if matched is not None else None)
                    if matched is not None:
                        unused.discard(matched)
            except (TypeError, ValueError):
                fallback_focus_rows = []
        for chart_index, item in enumerate(manifest.get('charts', [])):
            if not isinstance(item, dict):
                continue
            chart_file = str(item.get('file') or '')
            if not re.fullmatch(r'slide-\d+-chart-\d+\.png', chart_file):
                continue
            model_file = str(item.get('model_file') or '')
            model_available = bool(
                re.fullmatch(r'slide-\d+-chart-\d+\.model\.json', model_file)
                and (charts_dir / model_file).is_file()
            )
            charts.append({
                'index': len(charts),
                'entry_index': int(item['entry_index']) if isinstance(item.get('entry_index'), int) else None,
                'slide': int(item.get('slide') or 0),
                'title': str(item.get('title') or 'Chart'),
                'source': str(item.get('source') or ''),
                'chart_type': str(item.get('chart_type') or ''),
                'focus_row': int(item['focus_row']) if isinstance(item.get('focus_row'), int) else (
                    fallback_focus_rows[chart_index] if chart_index < len(fallback_focus_rows) else None
                ),
                'image_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/charts/{chart_file}',
                'payload_url': f'/api/ppt-dashboards/ppt-jobs/{job_id}/chart-models/{model_file}' if model_available else None,
                'data_url': f'/ppt-jobs/{job_id}/data/{chart_index}' if definition_available and isinstance(item.get('entry_index'), int) else None,
            })
        chart_by_entry = {
            int(chart['entry_index']): chart for chart in charts
            if isinstance(chart.get('entry_index'), int)
        }
        slides = []
        for source_slide in manifest.get('slides', []):
            if not isinstance(source_slide, dict):
                continue
            slide = {
                key: source_slide.get(key) for key in ('number', 'title', 'subtitle', 'layout', 'structural_type')
            }
            slide['charts'] = []
            for source_chart in source_slide.get('charts', []):
                if not isinstance(source_chart, dict):
                    continue
                entry_index = source_chart.get('index')
                chart = chart_by_entry.get(entry_index)
                if chart is None:
                    continue
                slide['charts'].append({**source_chart, **chart, 'available': bool(chart.get('payload_url'))})
            slides.append(slide)
        # Older PPT jobs did not retain their viewer slide structure. They can
        # still be opened as simple slide groups when Canvas models are present.
        if not slides:
            grouped = defaultdict(list)
            for chart in charts:
                grouped[int(chart.get('slide') or 0)].append({**chart, 'available': bool(chart.get('payload_url'))})
            slides = [
                {'number': number, 'title': f'Slide {number}', 'subtitle': '', 'layout': '', 'structural_type': '', 'charts': items}
                for number, items in sorted(grouped.items())
            ]
        return {
            'job': serialize_dashboard_ppt_job(row),
            'generate_tooltips': bool(manifest.get('generate_tooltips')),
            'charts': charts,
            'definition': manifest.get('definition') if definition_available else None,
            'cover': dashboard_ppt_job_cover(row, manifest),
            'slides': slides,
            'viewer_available': bool(slides) and any(
                chart.get('available') for slide in slides for chart in slide.get('charts', [])
            ),
        }

    @app.get('/api/ppt-dashboards/ppt-jobs/{job_id}/charts/{chart_index}/filter-context')
    def dashboard_ppt_chart_filter_context(
        job_id: int, chart_index: int, prepare: bool = False, user=Depends(dashboard_user),
    ):
        """Load PPT chart metadata immediately and restore its data only on demand."""
        task_repository = bound_repository()
        row = dashboard_ppt_job(task_repository, job_id)
        charts_dir = Path(str(row['output_path'])).parent / 'dashboard-charts' if row else None
        try:
            manifest = json.loads((charts_dir / 'manifest.json').read_text(encoding='utf-8'))
            definition = DashboardDefinition.model_validate(manifest['definition'])
            entry_index = int(manifest['charts'][chart_index]['entry_index'])
            entry = validate(definition, task_repository)[entry_index]
        except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(404, 'Chart filters are not available for this PowerPoint Job.')
        workspace = str(Path(task_repository.db_path).resolve())
        token = ''
        if prepare:
            preview = restore_preview_manifest(
                workspace, str(manifest.get('dashboard_id') or row['dashboard_id']),
                str(manifest.get('preview_fingerprint') or ''),
            ) or build_preview(definition, user, workspace=workspace)
            token = str(preview['token'])
        hidden = {identity('dataset_id'), identity('source_row_id')}
        datasets_by_source = {f'cdr-{kind}': [] for kind in KINDS}
        columns_by_source = {f'cdr-{kind}': [] for kind in KINDS}
        for dataset in task_repository.list_datasets():
            kind = str(dataset['dataset_kind'] or '').casefold()
            if kind in KINDS and dataset['status'] == 'ready':
                datasets_by_source[f'cdr-{kind}'].append({'value': str(dataset['id']), 'label': str(dataset['file_name'])})
                columns_by_source[f'cdr-{kind}'].extend(
                    str(column) for column in task_repository.list_dataset_row_columns(int(dataset['id']))
                )
        for source, source_columns in columns_by_source.items():
            columns_by_source[source] = sorted({
                column for column in source_columns if identity(column) not in hidden
            }, key=str.casefold)
        columns = columns_by_source.get(f'cdr-{entry.source_kind}', [])
        datasets_by_source['cdr-all'] = [row for source in KINDS for row in datasets_by_source[f'cdr-{source}']]
        columns_by_source['cdr-all'] = sorted({*rf_union_source(task_repository, [kind for kind in KINDS if dashboard_datasets(definition, kind, task_repository)])[1]}, key=str.casefold)
        if entry.source_kind == 'all':
            columns = columns_by_source['cdr-all']
        template_available = user.role in {'user-editor', 'admin', 'super-admin'} and any(
            str(item['name']) == definition.template
            for item in task_repository.list_report_templates()
        )
        return JSONResponse({
            'token': token, 'chart_index': entry_index, 'cdr_source': entry.cdr_source,
            'chart_type': entry.chart_type, 'chart_title': entry.chart_title, 'kpi': entry.kpi,
            'dataset_ids': [str(row['id']) for row in dashboard_datasets(definition, entry.source_kind, task_repository)],
            'filters': entry.filters, 'rows_split': entry.rows_split,
            'columns_split': entry.columns_split, 'legend': entry.legend,
            'legend_position': entry.legend_position,
            'legend_format': entry.legend_format,
            'axis_x_range': entry.axis_x_range, 'axis_y_range': entry.axis_y_range,
            'label_position': entry.label_position,
            'label_format': entry.label_format,
            'exclude_null_empty': entry.exclude_null_empty, 'exclude_zero': entry.exclude_zero, 'dynamic_rows_field': entry_dynamic_fields(entry)[0], 'dynamic_columns_field': entry_dynamic_fields(entry)[1],
            'template_available': template_available, 'datasets_by_source': datasets_by_source,
            'columns_by_source': columns_by_source, 'columns': columns,
        })

    @app.get('/api/ppt-dashboards/ppt-jobs/{job_id}/chart-models/{model_file}')
    def dashboard_ppt_chart_model(job_id: int, model_file: str, user=Depends(dashboard_user)):
        if not re.fullmatch(r'slide-\d+-chart-\d+\.model\.json', model_file):
            raise HTTPException(404, 'Chart model not found.')
        row = dashboard_ppt_job(bound_repository(), job_id)
        path = Path(str(row['output_path'])).parent / 'dashboard-charts' / model_file if row else None
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (AttributeError, OSError, json.JSONDecodeError):
            raise HTTPException(404, 'Chart model not found.')
        return JSONResponse(payload)

    @app.get('/api/ppt-dashboards/ppt-jobs/{job_id}/data/{chart_index}')
    def dashboard_ppt_chart_data(
        job_id: int, chart_index: int, page: int = 0, download: bool = False,
        column_filters: str = '', include_filter_values: bool = False, filter_column: str = '',
        user=Depends(dashboard_user),
    ):
        task_repository = bound_repository()
        row = dashboard_ppt_job(task_repository, job_id)
        charts_dir = Path(str(row['output_path'])).parent / 'dashboard-charts' if row else None
        try:
            manifest = json.loads((charts_dir / 'manifest.json').read_text(encoding='utf-8'))
            chart = manifest['charts'][chart_index]
            definition = DashboardDefinition.model_validate(manifest['definition'])
            entry_index = int(chart['entry_index'])
        except (AttributeError, IndexError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(404, 'The filtered dataset is not available for this PowerPoint Job.')
        workspace = str(Path(task_repository.db_path).resolve())
        token_key = (workspace, job_id, user.username)
        with lock:
            token = dashboard_ppt_data_tokens.get(token_key)
            cached_snapshot = snapshots.get(token) if token else None
        if cached_snapshot is None:
            preview = restore_preview_manifest(
                workspace,
                str(manifest.get('dashboard_id') or row['dashboard_id']),
                str(manifest.get('preview_fingerprint') or ''),
            )
            if preview is None:
                preview = build_preview(definition, user, workspace=workspace)
            token = str(preview['token'])
            with lock:
                dashboard_ppt_data_tokens[token_key] = token
        snapshot, entry, _ = snapshot_chart(
            token, entry_index, user, include_frame=False, expected_workspace=workspace,
        )
        filter_column = vendor_filter_column(filter_column) if filter_column else ''
        selected_column_filters = {vendor_filter_column(key): values for key, values in parse_chart_column_filters(column_filters).items()}
        if not download:
            projected_page = reporting_chart_data_page(
                snapshot, entry, page, selected_column_filters, include_filter_values, filter_column,
            )
            if projected_page is not None:
                visible, total, chart_total, filter_values = projected_page
                return {
                    'columns': list(visible.columns),
                    'rows': visible.fillna('').astype(str).values.tolist(),
                    'total': total, 'chart_total': chart_total,
                    'filter_values': filter_values, 'page': max(page, 0),
                    'column_classes': chart_dataset_column_classes(snapshot, entry, visible.columns),
                    'column_metadata': chart_dataset_column_metadata(snapshot, entry, visible.columns),
                    'page_size': 100, 'unfiltered_total': chart_total,
                }
        _, _, frame = snapshot_chart(token, entry_index, user, expected_workspace=workspace, complete=True)
        frame = unique_chart_dataset_rows(snapshot, entry, frame)
        chart_total = len(frame)
        values_frame = apply_chart_column_filters(
            frame, {column: values for column, values in selected_column_filters.items() if identity(column) != identity(filter_column)},
        )
        available_filter_values = chart_dataset_filter_values(values_frame) if filter_column else {}
        filter_values = next(
            (values for column, values in available_filter_values.items() if identity(column) == identity(filter_column)), []
        ) if filter_column else (chart_dataset_filter_values(frame) if include_filter_values else {})
        frame = apply_chart_column_filters(frame, selected_column_filters)
        if download:
            task_repository.try_add_log(user.username, 'export_dashboard_chart_data_csv', json.dumps({
                'job_id': job_id, 'chart_index': chart_index, 'rows': len(frame),
            }))
            return Response(
                frame.to_csv(index=False), media_type='text/csv',
                headers={'Content-Disposition': 'attachment; filename="dashboard-chart-data.csv"'},
            )
        page = max(page, 0)
        visible = frame.iloc[page * 100:(page + 1) * 100].fillna('').astype(str)
        return {
            'columns': list(visible.columns), 'rows': visible.values.tolist(),
            'total': len(frame), 'chart_total': chart_total,
            'filter_values': filter_values, 'page': page,
            'column_classes': chart_dataset_column_classes(snapshot, entry, visible.columns),
            'column_metadata': chart_dataset_column_metadata(snapshot, entry, visible.columns),
            'page_size': 100, 'unfiltered_total': chart_total,
        }

    @app.get('/api/ppt-dashboards/ppt-jobs/{job_id}/charts/{chart_file}')
    def dashboard_ppt_chart(job_id: int, chart_file: str, user=Depends(dashboard_user)):
        if not re.fullmatch(r'slide-\d+-chart-\d+\.png', chart_file):
            raise HTTPException(404, 'Chart not found.')
        row = dashboard_ppt_job(bound_repository(), job_id)
        path = Path(str(row['output_path'])).parent / 'dashboard-charts' / chart_file if row else None
        if path is None or not path.is_file():
            raise HTTPException(404, 'Chart not found.')
        return FileResponse(path, media_type='image/png')

    @app.get('/api/ppt-dashboards/ppt-jobs/{job_id}/charts.zip')
    def download_dashboard_ppt_charts(job_id: int, user=Depends(dashboard_user)):
        task_repository = bound_repository()
        row = dashboard_ppt_job(task_repository, job_id)
        charts_dir = Path(str(row['output_path'])).parent / 'dashboard-charts' if row else None
        if charts_dir is None or not (charts_dir / 'manifest.json').is_file():
            raise HTTPException(404, 'Dashboard charts are not available.')
        task_repository.try_add_log(user.username, 'download_dashboard_ppt_charts', json.dumps({'job_id': job_id}))
        temporary = tempfile.NamedTemporaryFile(prefix='dashboard-ppt-charts-', suffix='.zip', delete=False)
        temporary.close()
        archive = Path(temporary.name)
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            for path in charts_dir.glob('*.png'):
                bundle.write(path, path.name)
        return FileResponse(
            archive, filename=f'{Path(str(row["output_file"])).stem}_charts.zip',
            media_type='application/zip', background=BackgroundTask(archive.unlink, missing_ok=True),
        )

    @app.post('/api/ppt-dashboards/ppt-jobs/{job_id}/stop')
    def stop_dashboard_ppt(job_id: int, user=Depends(dashboard_user)):
        task_repository = bound_repository()
        row = dashboard_ppt_job(task_repository, job_id)
        if row is None or str(row['status']) not in {'queued', 'processing'}:
            raise HTTPException(409, 'Only queued or processing Dashboard exports can be stopped.')
        update_dashboard_ppt_job(
            task_repository, job_id, status='stopped',
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        task_repository.try_add_log(user.username, 'stop_dashboard_ppt_job', json.dumps({'job_id': job_id}))
        return {'stopped': job_id}

    @app.post('/api/ppt-dashboards/ppt-jobs/{job_id}/retry')
    def retry_dashboard_ppt(job_id: int, user=Depends(dashboard_user)):
        task_repository = bound_repository()
        row = dashboard_ppt_job(task_repository, job_id)
        if row is None or str(row['status']) not in {'ready', 'failed', 'stopped'}:
            raise HTTPException(409, 'This Dashboard export cannot be relaunched.')
        try:
            saved_selections = json.loads(str(row['selections_json'] or '{}'))
        except (TypeError, json.JSONDecodeError):
            saved_selections = {}
        if not isinstance(saved_selections, dict):
            saved_selections = {}
        try:
            manifest_path = Path(str(row['output_path'])).parent / 'dashboard-charts' / 'manifest.json'
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            retry_definition = DashboardDefinition.model_validate(manifest['definition'])
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            # Failed or stopped Jobs may not have reached manifest creation.
            # Preserve at least their recorded Scope while rebuilding the
            # current saved Dashboard universe.
            raw_definition = read_dashboards(task_repository).get(str(row['dashboard_id']))
            if not isinstance(raw_definition, dict):
                raise HTTPException(404, 'Dashboard not found.')
            raw_definition = dict(raw_definition)
            raw_definition['scope'] = (
                'multivendor' if str(row['scope'] or '').casefold() == 'multivendor' else 'single'
            )
            if saved_selections:
                raw_definition['filters'] = {
                    **(raw_definition.get('filters') or {}),
                    **{field: values for field, values in saved_selections.items() if isinstance(values, list)},
                }
            retry_definition = DashboardDefinition.model_validate(
                runtime_dashboard_definition(raw_definition, task_repository)
            )
        try:
            selected_regions = json.loads(str(row['regions_json'] or '[]'))
        except (TypeError, json.JSONDecodeError):
            selected_regions = []
        retry_definition.vendor_comparison = str(row['vendor_comparison'] or 'operator_vendor')
        queue_dashboard_ppt_export(
            str(row['dashboard_id']), user, reuse_job_id=job_id,
            export_definition=retry_definition,
            selected_operators=saved_selections.get('Operator') if isinstance(saved_selections.get('Operator'), list) else None,
            selected_vendors=saved_selections.get('Vendor', saved_selections.get('Vendor_Only')),
            selected_regions=saved_selections.get('Region') if isinstance(saved_selections.get('Region'), list) else selected_regions,
            selected_cities=saved_selections.get('City') if isinstance(saved_selections.get('City'), list) else None,
        )
        return JSONResponse({'job_id': job_id, 'status': 'queued'}, status_code=202)

    @app.post('/api/ppt-dashboards/ppt-jobs/delete-all')
    def delete_all_dashboard_ppts(user=Depends(dashboard_editor_user)):
        task_repository = bound_repository()
        ensure_dashboard_ppt_jobs(task_repository)
        with task_repository.connection() as connection:
            rows = connection.execute(
                f'SELECT id, output_path FROM {DASHBOARD_PPT_JOBS_TABLE}'
            ).fetchall()
            connection.execute(f'DELETE FROM {DASHBOARD_PPT_JOBS_TABLE}')
        database_key = str(Path(task_repository.db_path).resolve())
        with lock:
            for row in rows:
                dashboard_ppt_runs.pop((database_key, int(row['id'])), None)
        for row in rows:
            remove_dashboard_ppt_job_folder(task_repository, row['output_path'])
        task_repository.add_log(user.username, 'delete_all_dashboard_ppts', json.dumps({'count': len(rows)}))
        return {'deleted': len(rows)}

    @app.post('/api/ppt-dashboards/ppt-jobs/{job_id}/delete')
    def delete_dashboard_ppt(job_id: int, user=Depends(dashboard_editor_user)):
        task_repository = bound_repository()
        row = dashboard_ppt_job(task_repository, job_id)
        if row is None:
            raise HTTPException(404, 'Dashboard export job not found.')
        if str(row['status']) in {'queued', 'processing'}:
            raise HTTPException(409, 'A running Dashboard export cannot be deleted.')
        remove_dashboard_ppt_job_folder(task_repository, row['output_path'])
        with task_repository.connection() as connection:
            connection.execute(f'DELETE FROM {DASHBOARD_PPT_JOBS_TABLE} WHERE id = ?', (job_id,))
        task_repository.try_add_log(user.username, 'delete_dashboard_ppt', json.dumps({
            'job_id': job_id, 'file': str(row['output_file'] or ''),
        }))
        return {'deleted': job_id}

    def ensure_unique_dashboard_name(dashboards, dashboard_id, name) -> None:
        """Dashboard names are unique in a workspace, whatever the NR Mode each one reads."""
        if any(
            key != dashboard_id and isinstance(item, dict)
            and str(item.get('name') or '').strip().casefold() == str(name).strip().casefold()
            for key, item in dashboards.items()
        ):
            raise HTTPException(409, 'A Dashboard with this name already exists.')

    @app.put('/api/ppt-dashboards/{dashboard_id}')
    def save_dashboard(dashboard_id: str, definition: DashboardDefinition, user=Depends(dashboard_editor_user)):
        workspace = workspace_key()
        with lock:
            task_repository = bound_repository()
            validate(definition, task_repository)
            dashboards = read_dashboards(task_repository)
            ensure_unique_dashboard_name(dashboards, dashboard_id, definition.name)
            created = dashboard_id not in dashboards
            definition.name = definition.name.strip()
            saved_definition = migrate_auto_cdrs(normalize_dashboard_filters(definition.model_dump(mode='json')), task_repository)
            # The CDRs are chosen from the NR Mode and Campaign each time: they are not saved.
            saved_definition.pop('datasets', None)
            saved_definition['slide_comment_meta'] = comment_meta(
                saved_definition.get('slide_comment_meta'), saved_definition.get('slide_comments') or {},
            )
            saved_definition = follow_template_identities({dashboard_id: saved_definition}, template_uids(task_repository))[dashboard_id]
            dashboards[dashboard_id] = saved_definition
            task_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
            if created:
                record_creator(task_repository, PPT_DASHBOARDS, dashboard_id, user.username)
            creator = creator_of(task_repository, PPT_DASHBOARDS, dashboard_id)
            task_repository.add_log(user.username, 'save_dashboard', json.dumps({
                'id': dashboard_id, 'name': definition.name, 'nr_mode': definition.nr_mode, 'template': definition.template,
            }))
        # Saving a Dashboard may change template filters, so refresh its three
        # canonical automatic universes even when it was warmed previously.
        schedule_dashboard_warmup(workspace, dashboard_id, saved_definition, user.username, force=True)
        # As the list gives it, with who created it: the page compares it with the Dashboard it has open.
        return {'id': dashboard_id, 'definition': {**saved_definition, 'created_by': creator}}

    @app.patch('/api/ppt-dashboards/{dashboard_id}/name')
    def rename_dashboard(dashboard_id: str, payload: DashboardName, user=Depends(dashboard_editor_user)):
        name = payload.name.strip()
        if not name:
            raise HTTPException(400, 'Enter a Dashboard name.')
        with lock:
            task_repository = bound_repository()
            dashboards = read_dashboards(task_repository)
            if dashboard_id not in dashboards:
                raise HTTPException(404, 'Dashboard not found.')
            ensure_unique_dashboard_name(dashboards, dashboard_id, name)
            dashboards[dashboard_id]['name'] = name
            task_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
            task_repository.add_log(user.username, 'rename_dashboard', json.dumps({'id': dashboard_id, 'name': name}))
        return {'id': dashboard_id, 'name': name}

    @app.patch('/api/ppt-dashboards/{dashboard_id}/template')
    def change_dashboard_template(
        dashboard_id: str, payload: DashboardTemplateSelection, user=Depends(dashboard_editor_user),
    ):
        """Change the NR Mode of the CDRs and the template while retaining the saved filters.

        The saved CDR universe is kept when the NR Mode is unchanged. A new NR
        Mode selects the latest CDRs of that mode instead: the campaigns of the
        other NR Mode do not apply. Any template serves any NR Mode.
        """
        workspace = workspace_key()
        with lock:
            task_repository = bound_repository()
            dashboards = read_dashboards(task_repository)
            current = dashboards.get(dashboard_id)
            if current is None:
                raise HTTPException(404, 'Dashboard not found.')
            updated = dict(current)
            previous_nr_mode, previous_template = dashboard_nr_mode(current), str(current.get('template') or '')
            nr_mode_changed = previous_nr_mode != payload.nr_mode
            updated['nr_mode'] = payload.nr_mode
            updated['template'] = payload.template
            if nr_mode_changed:
                # The campaigns of the other NR Mode do not apply: the newest ones of the new NR Mode do.
                updated.pop('datasets', None)
                follow_nr_mode_campaigns(updated, previous_nr_mode, payload.nr_mode)
                updated['auto_cdrs'] = True
            definition = DashboardDefinition.model_validate(updated)
            validate(definition, task_repository)
            saved_definition = migrate_auto_cdrs(normalize_dashboard_filters(definition.model_dump(mode='json')), task_repository)
            saved_definition.pop('datasets', None)
            saved_definition = follow_template_identities({dashboard_id: saved_definition}, template_uids(task_repository))[dashboard_id]
            dashboards[dashboard_id] = saved_definition
            task_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
            task_repository.add_log(user.username, 'change_dashboard_template', json.dumps({
                'id': dashboard_id, 'name': definition.name,
                'nr_mode': payload.nr_mode, 'previous_nr_mode': previous_nr_mode,
                'template': payload.template, 'previous_template': previous_template,
            }))
        # Template and NR Mode belong to the preview fingerprint, so every old
        # report/chart snapshot becomes ineligible and a fresh warm-up is queued.
        schedule_dashboard_warmup(workspace, dashboard_id, saved_definition, user.username, force=True)
        return {'id': dashboard_id, 'definition': saved_definition, 'invalidated': True}

    @app.delete('/api/ppt-dashboards/{dashboard_id}')
    def delete_dashboard(dashboard_id: str, user=Depends(dashboard_editor_user)):
        with lock:
            task_repository = bound_repository()
            dashboards = read_dashboards(task_repository)
            if dashboard_id not in dashboards:
                raise HTTPException(404, 'Dashboard not found.')
            if not can_delete(user, creator_of(task_repository, PPT_DASHBOARDS, dashboard_id)):
                raise HTTPException(403, deletion_refusal('Dashboard'))
            del dashboards[dashboard_id]
            task_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
            forget_creator(task_repository, PPT_DASHBOARDS, dashboard_id)
            task_repository.add_log(user.username, 'delete_dashboard', json.dumps({'id': dashboard_id}))
        return {'deleted': True}

    @app.patch('/api/ppt-dashboards/{dashboard_id}/comments')
    def save_dashboard_comments(dashboard_id: str, payload: DashboardComments, user=Depends(dashboard_editor_user)):
        with lock:
            task_repository = bound_repository()
            dashboards = read_dashboards(task_repository)
            if dashboard_id not in dashboards:
                raise HTTPException(404, 'Dashboard not found.')
            comments = {
                str(slide): [str(comment).strip() for comment in values if str(comment).strip()][:50]
                for slide, values in payload.slide_comments.items()
            }
            saved = {slide: values for slide, values in comments.items() if values}
            dashboards[dashboard_id]['slide_comments'] = saved
            meta = comment_meta(dashboards[dashboard_id].get('slide_comment_meta'), saved)
            if payload.generated_added and payload.generated_slide:
                snapshot = snapshots.get(payload.token) if payload.token else None
                present = set(saved.get(payload.generated_slide, []))
                added = [text for text in (str(item).strip() for item in payload.generated_texts) if text in present]
                if not payload.generated_texts:
                    # Without their texts, the comments just added are the last ones of the slide.
                    added = saved.get(payload.generated_slide, [])[-payload.generated_added:]
                previous = (meta.get(payload.generated_slide) or {}).get('generated') or []
                meta[payload.generated_slide] = {
                    'generated': list(dict.fromkeys([*previous, *added])),
                    'engine': payload.generated_engine or dashboard_comments.ENGINE_RULES,
                    'model': payload.generated_model, 'generated_at': datetime.now(timezone.utc).isoformat(),
                    'generated_by': user.username,
                    'selection': snapshot.selection_key if snapshot is not None and snapshot.workspace == workspace_key() else '',
                }
            dashboards[dashboard_id]['slide_comment_meta'] = meta
            task_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
            task_repository.add_log(user.username, 'save_dashboard_comments', json.dumps({'id': dashboard_id}))
            if payload.generated_added and payload.generated_slide:
                task_repository.add_log(user.username, 'add_generated_dashboard_comments', json.dumps({
                    'id': dashboard_id, 'name': dashboards[dashboard_id].get('name', ''), 'slide': payload.generated_slide,
                    'added': payload.generated_added, 'engine': payload.generated_engine or dashboard_comments.ENGINE_RULES,
                    'comments': len(saved.get(payload.generated_slide, [])),
                }))
        return {'slide_comments': saved, 'slide_comment_meta': meta}

    def comment_meta(meta, comments) -> dict[str, dict]:
        """The generated-comment metadata that still applies: a generated comment edited or removed by hand is no longer
        generated, and a slide without generated comments has none."""
        kept = {}
        for slide, info in (meta or {}).items():
            if not isinstance(info, dict):
                continue
            present = set(comments.get(slide, []))
            generated = [text for text in info.get('generated') or [] if text in present]
            if generated:
                kept[slide] = {**info, 'generated': generated}
        return kept

    def comment_snapshot(token: str, user):
        with lock:
            snapshot = snapshots.get(token)
        if snapshot is None or snapshot.workspace != workspace_key() or snapshot.owner not in {user.username, '*'}:
            raise HTTPException(410, 'Dashboard preview expired. Refresh the Dashboard.')
        return snapshot

    def slide_comment_charts(token: str, snapshot, slide: dict, requested, user) -> tuple[list[dict], list[str]]:
        """The charts of a slide the comments read, with the legend items the viewer hides on each one, and the
        titles of those they cannot read."""
        available = {int(chart['index']): chart for chart in slide.get('charts', []) if chart.get('available')}
        requested = requested or [GeneratedCommentChart(index=index) for index in available]
        charts, skipped = [], []
        for chart in requested:
            if chart.index not in available:
                continue
            model = chart_model(token, chart.index, user)
            if dashboard_comments.needs_rebuild(model):
                # A model cached before the comments read their facts is calculated again once.
                model = chart_model(token, chart.index, user, force=True)
            entry = snapshot.entries[chart.index]
            if model.get('type') == 'empty':
                continue
            if model.get('type') not in dashboard_comments.SUPPORTED_MODEL_TYPES:
                skipped.append(entry.chart_title or entry.chart_type)
                continue
            charts.append({
                'index': chart.index, 'title': entry.chart_title or entry.slide_title, 'kpi': entry.kpi,
                'model': model, 'hidden': chart.hidden, 'shown': chart.shown,
                # The value of a dynamic grid card (its Operator, Vendor…) names what its map or table shows.
                'subject': ' · '.join(value for value in (entry.dynamic_row_value, entry.dynamic_column_value) if value),
            })
        return charts, skipped

    def write_slide_comments(charts: list[dict], layout: str, task_repository, engine: str, username: str) -> tuple[list[dict], dict]:
        """The comments of one slide by its writer: the rules, or an LLM writer that rewrites their facts (checked
        against them; the rules comments when it fails). Returns them and what wrote them."""
        brief = dashboard_comments.slide_brief(charts, focus_operators=focus_operators(task_repository), layout=layout or '')
        if engine not in comment_writers.SERVER_ENGINES:
            return brief['rules'], {'engine': dashboard_comments.ENGINE_RULES, 'model': '', 'warning': '', 'problems': []}
        written = comment_writers.write_comments(engine, brief, repository=core.repository,
                                                 config_dir=core.application_config_dir, username=username)
        if written['engine'] == dashboard_comments.ENGINE_RULES:
            return brief['rules'], written
        return [{'text': item, 'kind': written['engine'], 'chart_index': None, 'chart_title': ''} for item in written['texts']], written

    @app.post('/api/ppt-dashboards/{dashboard_id}/comments/generate')
    def generate_dashboard_comments(dashboard_id: str, payload: GenerateComments, user=Depends(dashboard_editor_user)):
        """Suggest the comments of one slide from the charts the viewer shows; nothing is saved until they are added."""
        started = monotonic()
        task_repository = bound_repository()
        name = read_dashboards(task_repository).get(dashboard_id, {}).get('name')
        if name is None:
            raise HTTPException(404, 'Dashboard not found.')
        snapshot = comment_snapshot(payload.token, user)
        slide = next((item for item in snapshot.payload.get('slides', []) if item.get('number') == payload.slide), None)
        if slide is None:
            raise HTTPException(404, 'Slide not found.')
        engine = comment_writers.resolve_engine(core.repository, payload.engine)
        try:
            charts, skipped = slide_comment_charts(payload.token, snapshot, slide, payload.charts, user)
            suggestions, written = write_slide_comments(charts, slide.get('layout') or '', task_repository, engine, user.username)
        except HTTPException:
            raise
        except Exception as exc:
            task_repository.add_log(user.username, 'generate_dashboard_comments_failed', json.dumps({
                'id': dashboard_id, 'name': name, 'slide': payload.slide, 'error': str(exc),
            }))
            raise HTTPException(500, f'The comments of this slide could not be generated: {exc}') from exc
        task_repository.add_log(user.username, 'generate_dashboard_comments', json.dumps({
            'id': dashboard_id, 'name': name, 'slide': payload.slide, 'comment_key': slide.get('comment_key', ''),
            'requested_engine': engine, 'engine': written['engine'], 'model': written.get('model', ''),
            'charts': len(charts), 'skipped_charts': skipped, 'suggestions': len(suggestions),
            **{key: written[key] for key in ('input_tokens', 'output_tokens') if key in written},
            'left_out': written.get('problems', []), 'warning': written.get('warning', ''),
            'duration_ms': round((monotonic() - started) * 1000),
        }))
        return {
            'comment_key': slide.get('comment_key', ''), 'engine': written['engine'], 'model': written.get('model', ''),
            'suggestions': suggestions, 'skipped': skipped, 'warning': written.get('warning', ''),
        }

    @app.get('/api/ppt-dashboards/comment-engines')
    def dashboard_comment_engines(user=Depends(dashboard_user)):
        """The writers a user can choose (Rules and those Super Admin enabled), the default one, and whether the
        Kiro Brief is enabled."""
        return comment_writers.available_engines(core.repository)

    def apply_generated_comments(definition: dict, written: dict[str, list[str]], mode: str, legacy: dict[str, str],
                                 info: dict, writers: dict[str, dict] | None = None) -> dict[str, int]:
        """Write the generated comments of several slides into a Dashboard definition: on the slides without comments
        (``empty``), in place of the generated ones keeping those written by hand (``generated``), or in place of every
        comment (``all``). Returns how many slides were written, kept and left without comments."""
        comments = dict(definition.get('slide_comments') or {})
        meta = comment_meta(definition.get('slide_comment_meta'), comments)
        counts = {'written': 0, 'kept': 0, 'empty': 0, 'comments': 0}
        for key, texts in written.items():
            current = list(comments.get(key, comments.get(legacy.get(key, ''), [])))
            if not texts:
                counts['empty'] += 1
                continue
            if mode == 'empty' and current:
                counts['kept'] += 1
                continue
            generated = set((meta.get(key) or {}).get('generated') or [])
            manual = [text for text in current if text not in generated] if mode == 'generated' else []
            comments[key] = [*manual, *[text for text in texts if text not in manual]][:50]
            comments.pop(legacy.get(key, ''), None)
            meta[key] = {**info, **((writers or {}).get(key) or {}), 'generated': [text for text in texts if text in comments[key]]}
            counts['written'] += 1
            counts['comments'] += len(meta[key]['generated'])
        definition['slide_comments'] = {key: values for key, values in comments.items() if values}
        definition['slide_comment_meta'] = comment_meta(meta, definition['slide_comments'])
        return counts

    def run_dashboard_comment_job(job_id: str, dashboard_id: str, payload: GenerateAllComments, user, workspace: str) -> None:
        """Generate the comments of every slide of a Dashboard and write them as its mode says."""
        started = monotonic()
        task_repository = Repository(Path(workspace), core.repository.global_db_path)

        def update(**changes):
            with lock:
                job = comment_jobs.get(job_id)
                if job is not None:
                    job.update(changes)

        try:
            snapshot = comment_snapshot(payload.token, user) if workspace == workspace_key() else None
            if snapshot is None:
                raise HTTPException(410, 'Dashboard preview expired. Refresh the Dashboard.')
            requested = {item.number: item for item in payload.slides}
            slides = [slide for slide in snapshot.payload.get('slides', [])
                      if not slide.get('structural_type') and (not requested or slide.get('number') in requested)]
            written: dict[str, list[str]] = {}
            writers: dict[str, dict] = {}
            legacy: dict[str, str] = {}
            skipped: list[str] = []
            warnings: list[str] = []
            engine = comment_writers.resolve_engine(core.repository, payload.engine)
            for position, slide in enumerate(slides, 1):
                spec = requested.get(slide.get('number'))
                charts, not_read = slide_comment_charts(payload.token, snapshot, slide, spec.charts if spec else [], user)
                skipped.extend(not_read)
                key = str(slide.get('comment_key') or slide.get('number'))
                suggestions, info_written = (write_slide_comments(charts, slide.get('layout') or '', task_repository, engine, user.username)
                                             if charts else ([], {'engine': dashboard_comments.ENGINE_RULES, 'model': ''}))
                written[key] = [item['text'] for item in suggestions]
                writers[key] = {'engine': info_written['engine'], 'model': info_written.get('model', '')}
                if info_written.get('warning'):
                    warnings.append(info_written['warning'])
                legacy[key] = str(slide.get('number'))
                update(done=position)
            with lock:
                dashboards = read_dashboards(task_repository)
                if dashboard_id not in dashboards:
                    raise HTTPException(404, 'Dashboard not found.')
                info = {
                    'engine': dashboard_comments.ENGINE_RULES, 'model': '',
                    'generated_at': datetime.now(timezone.utc).isoformat(), 'generated_by': user.username,
                    'selection': snapshot.selection_key,
                }
                counts = apply_generated_comments(dashboards[dashboard_id], written, payload.mode, legacy, info, writers)
                task_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
                definition = dashboards[dashboard_id]
            task_repository.add_log(user.username, 'generate_all_dashboard_comments', json.dumps({
                'id': dashboard_id, 'name': definition.get('name', ''), 'mode': payload.mode, 'requested_engine': engine,
                'engines': sorted({item['engine'] for item in writers.values()}), 'warnings': sorted(set(warnings))[:5],
                'slides': len(slides), **counts,
                'skipped_charts': sorted(set(skipped)), 'duration_ms': round((monotonic() - started) * 1000),
            }))
            update(state='ready', result={
                **counts, 'slides': len(slides), 'warnings': sorted(set(warnings))[:5],
                'slide_comments': definition.get('slide_comments', {}),
                'slide_comment_meta': definition.get('slide_comment_meta', {}),
            })
        except HTTPException as exc:
            update(state='failed', status=exc.status_code, detail=str(exc.detail))
        except Exception as exc:
            task_repository.add_log(user.username, 'generate_all_dashboard_comments_failed', json.dumps({
                'id': dashboard_id, 'mode': payload.mode, 'error': str(exc),
            }))
            update(state='failed', status=500, detail=f'The comments of this Dashboard could not be generated: {exc}')

    @app.post('/api/ppt-dashboards/{dashboard_id}/comments/generate-all')
    def generate_all_dashboard_comments(
        dashboard_id: str, payload: GenerateAllComments, background_tasks: BackgroundTasks, user=Depends(dashboard_editor_user),
    ):
        """Start writing the comments of every slide of a Dashboard; the page follows the job until it is done."""
        task_repository = bound_repository()
        if dashboard_id not in read_dashboards(task_repository):
            raise HTTPException(404, 'Dashboard not found.')
        snapshot = comment_snapshot(payload.token, user)
        total = sum(1 for slide in snapshot.payload.get('slides', []) if not slide.get('structural_type')
                    and (not payload.slides or slide.get('number') in {item.number for item in payload.slides}))
        job_id = uuid4().hex
        with lock:
            comment_jobs[job_id] = {
                'state': 'processing', 'owner': user.username, 'workspace': workspace_key(), 'done': 0, 'total': total,
            }
            while len(comment_jobs) > 16:
                removable = next((key for key, value in comment_jobs.items() if value.get('state') != 'processing'), None)
                if removable is None:
                    break
                comment_jobs.pop(removable, None)
        background_tasks.add_task(run_dashboard_comment_job, job_id, dashboard_id, payload, user, workspace_key())
        return JSONResponse({'state': 'processing', 'job_id': job_id, 'done': 0, 'total': total}, status_code=202)

    def run_kiro_brief_job(job_id: str, dashboard_id: str, payload: GenerateAllComments, user, workspace: str) -> None:
        """Read the facts of every slide for the Kiro Brief: Kiro IDE writes the comments from them."""
        task_repository = Repository(Path(workspace), core.repository.global_db_path)

        def update(**changes):
            with lock:
                job = comment_jobs.get(job_id)
                if job is not None:
                    job.update(changes)

        try:
            snapshot = comment_snapshot(payload.token, user) if workspace == workspace_key() else None
            if snapshot is None:
                raise HTTPException(410, 'Dashboard preview expired. Refresh the Dashboard.')
            requested = {item.number: item for item in payload.slides}
            slides = [slide for slide in snapshot.payload.get('slides', [])
                      if not slide.get('structural_type') and (not requested or slide.get('number') in requested)]
            focus = focus_operators(task_repository)
            briefed = []
            for position, slide in enumerate(slides, 1):
                spec = requested.get(slide.get('number'))
                charts, _skipped = slide_comment_charts(payload.token, snapshot, slide, spec.charts if spec else [], user)
                if charts:
                    brief = dashboard_comments.slide_brief(charts, focus_operators=focus, layout=slide.get('layout') or '')
                    brief.pop('rules', None)
                    briefed.append({'comment_key': str(slide.get('comment_key') or slide.get('number')), 'number': slide.get('number'),
                                    'title': slide.get('title', ''), 'subtitle': slide.get('subtitle', ''), 'layout': slide.get('layout', ''),
                                    **brief})
                update(done=position)
            name = read_dashboards(task_repository).get(dashboard_id, {}).get('name', dashboard_id)
            brief_id = uuid4().hex
            with lock:
                comment_briefs[brief_id] = {
                    'owner': user.username, 'workspace': workspace, 'dashboard_id': dashboard_id, 'name': name,
                    'selection': snapshot.selection_key, 'slides': briefed,
                    'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                }
                while len(comment_briefs) > 16:
                    comment_briefs.popitem(last=False)
            task_repository.add_log(user.username, 'export_kiro_comment_brief', json.dumps({
                'id': dashboard_id, 'name': name, 'slides': len(briefed),
            }))
            update(state='ready', result={'brief_id': brief_id, 'slides': len(briefed)})
        except HTTPException as exc:
            update(state='failed', status=exc.status_code, detail=str(exc.detail))
        except Exception as exc:
            update(state='failed', status=500, detail=f'The Kiro Brief could not be prepared: {exc}')

    @app.post('/api/ppt-dashboards/{dashboard_id}/comments/kiro-brief')
    def start_kiro_brief(dashboard_id: str, payload: GenerateAllComments, background_tasks: BackgroundTasks,
                         user=Depends(dashboard_editor_user)):
        """Start reading the facts of every slide for the Kiro Brief; the page downloads it when the job is done."""
        if not comment_writers.available_engines(core.repository)['kiro_brief']:
            raise HTTPException(403, 'Super Admin has not enabled the Kiro Brief.')
        if dashboard_id not in read_dashboards(bound_repository()):
            raise HTTPException(404, 'Dashboard not found.')
        snapshot = comment_snapshot(payload.token, user)
        total = sum(1 for slide in snapshot.payload.get('slides', []) if not slide.get('structural_type'))
        job_id = uuid4().hex
        with lock:
            comment_jobs[job_id] = {'state': 'processing', 'owner': user.username, 'workspace': workspace_key(), 'done': 0, 'total': total}
        background_tasks.add_task(run_kiro_brief_job, job_id, dashboard_id, payload, user, workspace_key())
        return JSONResponse({'state': 'processing', 'job_id': job_id, 'done': 0, 'total': total}, status_code=202)

    @app.get('/api/ppt-dashboards/comment-briefs/{brief_id}.zip')
    def download_kiro_brief(brief_id: str, user=Depends(dashboard_user)):
        with lock:
            brief = comment_briefs.get(brief_id)
        if brief is None or brief['owner'] != user.username or brief['workspace'] != workspace_key():
            raise HTTPException(404, 'Kiro Brief not found: prepare it again.')
        content = comment_writers.kiro_brief_archive(brief)
        name = re.sub(r'[^\w.-]+', '_', f"Kiro brief - {brief['name']}").strip('_')
        return Response(content, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{name}.zip"'})

    @app.post('/api/ppt-dashboards/{dashboard_id}/comments/kiro-import')
    async def import_kiro_comments(
        dashboard_id: str, files: list[UploadFile] = File(...), mode: str = Form('empty'), user=Depends(dashboard_editor_user),
    ):
        """Check the comments Kiro IDE wrote from a Kiro Brief against its facts and write those that keep to them."""
        if mode not in {'empty', 'generated', 'all'}:
            raise HTTPException(400, 'Choose which comments the imported ones replace.')
        uploads = [(upload.filename or '', await upload.read()) for upload in files]
        task_repository = bound_repository()
        try:
            comments_document, facts_document = comment_writers.read_kiro_import(uploads)
            written, problems = comment_writers.check_kiro_comments(comments_document, facts_document)
        except ValueError as exc:
            task_repository.add_log(user.username, 'import_kiro_comments_failed', json.dumps({'id': dashboard_id, 'error': str(exc)}))
            raise HTTPException(400, str(exc)) from exc
        with lock:
            dashboards = read_dashboards(task_repository)
            if dashboard_id not in dashboards:
                raise HTTPException(404, 'Dashboard not found.')
            legacy = {str(slide.get('comment_key')): str(slide.get('number')) for slide in facts_document.get('slides') or []}
            info = {'engine': comment_writers.ENGINE_KIRO_BRIEF, 'model': '', 'generated_by': user.username,
                    'generated_at': datetime.now(timezone.utc).isoformat(), 'selection': str(facts_document.get('selection') or '')}
            counts = apply_generated_comments(dashboards[dashboard_id], written, mode, legacy, info)
            task_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
            definition = dashboards[dashboard_id]
        task_repository.add_log(user.username, 'import_kiro_comments', json.dumps({
            'id': dashboard_id, 'name': definition.get('name', ''), 'mode': mode, 'slides': len(written), **counts,
            'left_out': len(problems), 'problems': problems[:5],
        }))
        return {**counts, 'slides': len(written), 'left_out': len(problems), 'problems': problems[:5],
                'slide_comments': definition.get('slide_comments', {}), 'slide_comment_meta': definition.get('slide_comment_meta', {})}

    @app.get('/api/ppt-dashboards/comment-jobs/{job_id}')
    def dashboard_comment_job(job_id: str, user=Depends(dashboard_user)):
        with lock:
            job = comment_jobs.get(job_id)
            if job is None or job.get('owner') != user.username or job.get('workspace') != workspace_key():
                raise HTTPException(404, 'Comment job not found.')
            result = dict(job)
        if result.get('state') == 'failed':
            raise HTTPException(int(result.get('status') or 500), str(result.get('detail') or 'The comments could not be generated.'))
        return JSONResponse({key: result.get(key) for key in ('state', 'done', 'total', 'result')}, headers={'Cache-Control': 'no-store'})

    def dashboard_datasets(definition, kind, task_repository):
        """Return the selected CDRs of one kind that match the Dashboard's NR Mode."""
        if kind == 'all':
            return [row for source in KINDS for row in dashboard_datasets(definition, source, task_repository)]
        datasets = definition.get('datasets', {}) if isinstance(definition, dict) else definition.datasets
        nr_mode = dashboard_nr_mode(definition)
        return [
            row for row in core._optional_reporting_datasets(list((datasets or {}).get(kind, [])), kind, task_repository)
            # A Dashboard only analyses CDRs of its own NR Mode.
            if dataset_matches_nr_mode(row, nr_mode)
        ]

    def selected_sources(definition, task_repository):
        selected_by_kind = {}
        for kind in KINDS:
            selected = dashboard_datasets(definition, kind, task_repository)
            if definition.scope == 'multivendor' and any(not row.get('vendor_mapping_applied') for row in selected):
                raise HTTPException(400, 'Map Vendors for every selected CDR before using Multivendor Comparison.')
            if selected:
                selected_by_kind[kind] = selected
        if not selected_by_kind:
            raise HTTPException(400, f'No ready {definition.nr_mode} CDR is in the combined CDR tables for the chosen Campaign.')
        if definition.scope == 'multivendor':
            selected_ids = [int(row['id']) for rows in selected_by_kind.values() for row in rows]
            if len(task_repository.cdr_catalogue_values(selected_ids)['vendors']) < 2:
                raise HTTPException(400, 'Vendor Comparison requires at least two distinct Vendors in the selected CDRs.')
        return selected_by_kind

    def is_complete_unfiltered_universe(definition, selected_by_kind, task_repository, date_bounds):
        """Whether the selection exactly matches every row in each combined CDR table."""
        if definition.filters:
            return False
        if not ignore_event_time_filtering() and date_bounds and (
            str(definition.date_from) != date_bounds['min']
            or str(definition.date_to) != date_bounds['max']
        ):
            return False
        included = core.combined_dataset_ids(task_repository)
        for kind, selected in selected_by_kind.items():
            selected_ids = {int(row['id']) for row in selected}
            ready_ids = {
                int(row['id']) for row in task_repository.list_datasets()
                if row['status'] == 'ready' and str(row['dataset_kind'] or '').casefold() == kind
                and int(row['id']) in included
            }
            if selected_ids != ready_ids:
                return False
        return bool(selected_by_kind)

    def resolve_sql_column(columns, field):
        lookup = {identity(column): column for column in columns}
        if identity(field) == 'vendor' and 'vendor' in lookup:
            return lookup['vendor']
        aliases = next((values for label, values in FILTER_COLUMNS.items() if identity(label) == identity(field)), (field,))
        return next((lookup[identity(alias)] for alias in aliases if identity(alias) in lookup), None)

    def filter_sql_value_expression(task_repository, columns, field):
        """Return a text value expression with row-level fallback aliases."""
        field = vendor_filter_column(field)
        lookup = {identity(column): column for column in columns}
        aliases = next((values for label, values in FILTER_COLUMNS.items() if identity(label) == identity(field)), (field,))
        resolved = list(dict.fromkeys(
            lookup[identity(alias)] for alias in aliases if identity(alias) in lookup
        ))
        if not resolved:
            return None
        quote = task_repository._quote_identifier
        if identity(field) in {identity('City'), identity('Region')}:
            candidates = ', '.join(
                f"NULLIF(TRIM(CAST({quote(column)} AS TEXT)), '')" for column in resolved
            )
            return f"COALESCE({candidates}, '')"
        return f"COALESCE(CAST({quote(resolved[0])} AS TEXT), '')"

    def filter_sql_normalized_expression(task_repository, columns, field):
        """Return an indexed normalized expression when one physical column owns the filter."""
        field = vendor_filter_column(field)
        lookup = {identity(column): column for column in columns}
        aliases = next((values for label, values in FILTER_COLUMNS.items() if identity(label) == identity(field)), (field,))
        resolved = list(dict.fromkeys(
            lookup[identity(alias)] for alias in aliases if identity(alias) in lookup
        ))
        if not resolved:
            return None
        quote = task_repository._quote_identifier
        if len(resolved) == 1:
            return f"LOWER(TRIM(CAST({quote(resolved[0])} AS TEXT)))"
        value_expression = filter_sql_value_expression(task_repository, columns, field)
        return f"LOWER(TRIM({value_expression}))" if value_expression is not None else None

    def pattern_filter_values(task_repository, mapper, field_name, values, catalogue):
        """The CDR spellings a filter with patterns (VF*, -Three) takes: those of the CDR catalogues whose spelling or
        Operator / Vendor Maps label it accepts (see value_patterns), so -Three also leaves out the 3 of the CDRs. A
        filter whose patterns take no known spelling keeps them: it then takes no value instead of every value."""
        field = vendor_filter_column(field_name)
        source = PATTERN_CATALOGUE_FIELDS.get(identity(field))
        kind = field_kind(field)
        if source and catalogue.get(source) is None:
            catalogue[source] = task_repository.cdr_catalogue_values().get(source, [])
        chosen = ValueSet(values)
        taken = [value for value in catalogue.get(source) or [] if chosen.accepts([value, mapper.map(kind, value)])]
        return taken or [value for value in values if is_pattern(value)]

    def selection_filter_terms(task_repository, columns, definition, exclude=None):
        """Return each user-selected Dashboard filter as (normalized SQL or None, values).

        A ``None`` expression selects no row. SQLite queries and the per-CDR
        column cache both evaluate these terms, so they always agree.
        """
        terms = []
        excluded = identity(exclude) if exclude else ''
        mapper = ValueMapper.from_repository(task_repository)
        catalogue = {}
        for field_name, values in definition.filters.items():
            # Patterns (VF*, -Three) become the spellings they take: these terms compare values as they are.
            if any(is_pattern(value) for value in values or []):
                values = pattern_filter_values(task_repository, mapper, field_name, values, catalogue)
            if identity(vendor_filter_column(field_name)) in {'vendor', 'operatorvendor'}:
                values = vendor_match_values(field_name, values, task_repository.list_operator_mappings())
            # Operators and Vendors are chosen with their mapped labels: match every source spelling.
            kind = field_kind(vendor_filter_column(field_name))
            if kind == 'vendor_operator' and values:
                values = mapper.sources('operator_vendor', mapper.operator_vendors(values))
            elif kind and values:
                values = mapper.sources(kind, values)
            if identity(field_name) == excluded:
                continue
            normalized_expression = filter_sql_normalized_expression(
                task_repository, columns, field_name,
            )
            if normalized_expression is None or not values:
                terms.append((None, ()))
                continue
            terms.append((normalized_expression, tuple(str(value).strip().lower() for value in values)))
        return terms

    def selection_filter_where(task_repository, columns, definition, exclude=None):
        """Build only the user-selected Dashboard filter predicates."""
        clauses, params = [], []
        for normalized_expression, values in selection_filter_terms(task_repository, columns, definition, exclude):
            if normalized_expression is None:
                clauses.append('0')
                continue
            value_placeholders = ', '.join('?' for _ in values)
            clauses.append(f"{normalized_expression} IN ({value_placeholders})")
            params.extend(values)
        return ' AND '.join(f'({clause})' for clause in clauses) or '1', params

    def selection_date_expression(task_repository, columns):
        date_column = next((resolve_sql_column(columns, candidate) for candidate in ('event_start_time', 'Test_Start_Time', 'Timestamp', 'Date') if resolve_sql_column(columns, candidate)), None)
        return f"date(CAST({task_repository._quote_identifier(date_column)} AS TEXT))" if date_column else None

    def selection_date_term(task_repository, columns, definition):
        """Return the universe's (event-date SQL or None, low, high) bounds, if any."""
        concrete_from = definition.date_from if isinstance(definition.date_from, date) and not ignore_event_time_filtering() else None
        concrete_to = definition.date_to if isinstance(definition.date_to, date) and not ignore_event_time_filtering() else None
        if not concrete_from and not concrete_to:
            return None
        return (
            selection_date_expression(task_repository, columns),
            concrete_from.isoformat() if concrete_from else None,
            concrete_to.isoformat() if concrete_to else None,
        )

    def selection_sheet_term(task_repository, columns):
        """Return the (source sheet column, ignored sheet keys) exclusion, if any."""
        source_sheet = resolve_sql_column(columns, 'source_sheet')
        if source_sheet and core.CDR_IGNORED_SHEET_KEYS:
            return task_repository._quote_identifier(source_sheet), sorted(core.CDR_IGNORED_SHEET_KEYS)
        return None

    def selection_where(
        task_repository, kind, dataset_ids, definition, exclude=None, *, columns=None, include_dataset_scope=True,
    ):
        columns = columns or task_repository.list_reporting_row_columns(kind)
        clauses = []
        params = []
        if include_dataset_scope:
            placeholders = ', '.join('?' for _ in dataset_ids)
            clauses.append(f"dataset_id IN ({placeholders})")
            params.extend(int(dataset_id) for dataset_id in dataset_ids)
        filter_where, filter_params = selection_filter_where(
            task_repository, columns, definition, exclude=exclude,
        )
        if filter_where != '1':
            clauses.append(filter_where)
            params.extend(filter_params)
        for operator_expression, excluded_names in selection_excluded_operators(task_repository, columns):
            # The operators the Operator Maps exclude are left out of every Dashboard.
            clauses.append(f"NOT COALESCE({operator_expression} IN ({', '.join('?' for _ in excluded_names)}), 0)")
            params.extend(sorted(excluded_names))
        for mode_datasets, operator_expression, excluded_names in selection_out_of_scope_operators(task_repository, columns):
            # And those out of scope in the NR Mode of each CDR (the NR Modes of the Operator Maps).
            clauses.append(f"NOT COALESCE(dataset_id IN ({', '.join('?' for _ in mode_datasets)}) "
                           f"AND {operator_expression} IN ({', '.join('?' for _ in excluded_names)}), 0)")
            params.extend([*sorted(mode_datasets), *sorted(excluded_names)])
        date_term = selection_date_term(task_repository, columns, definition)
        if date_term is not None:
            date_expression, low, high = date_term
            if date_expression is None:
                clauses.append('0')
            else:
                if low:
                    clauses.append(f"{date_expression} >= date(?)")
                    params.append(low)
                if high:
                    clauses.append(f"{date_expression} <= date(?)")
                    params.append(high)
        sheet_term = selection_sheet_term(task_repository, columns)
        if sheet_term is not None:
            source_sheet, ignored = sheet_term
            clauses.append(f"({source_sheet} IS NULL OR LOWER(TRIM(CAST({source_sheet} AS TEXT))) NOT IN ({', '.join('?' for _ in ignored)}))")
            params.extend(ignored)
        return ' AND '.join(f'({clause})' for clause in clauses) or '1', params

    def selection_cache_terms(task_repository, columns, definition):
        """The universe's row predicates for the per-CDR column cache."""
        date_term = selection_date_term(task_repository, columns, definition)
        sheet_term = selection_sheet_term(task_repository, columns)
        return SelectionTerms(
            values=tuple(
                (expression, frozenset(values))
                for expression, values in selection_filter_terms(task_repository, columns, definition)
            ),
            date=date_term,
            excluded_sheets=(
                (f'LOWER(TRIM(CAST({sheet_term[0]} AS TEXT)))', frozenset(sheet_term[1])) if sheet_term else None
            ),
            excluded_values=selection_excluded_operators(task_repository, columns),
            dataset_excluded_values=selection_out_of_scope_operators(task_repository, columns),
        )

    def selection_excluded_operators(task_repository, columns):
        """The (normalized Operator SQL, excluded names) term of the operators the Operator Maps exclude, if any."""
        names = excluded_operators(task_repository)
        expression = filter_sql_normalized_expression(task_repository, columns, 'Operator') if names else None
        return ((expression, frozenset(name.lower() for name in names)),) if expression is not None else ()

    def selection_out_of_scope_operators(task_repository, columns):
        """The (CDRs of an NR Mode, normalized Operator SQL, names) terms of the operators out of scope in each NR Mode
        (the NR Modes of the Operator Maps), if any."""
        groups = task_repository.list_operator_mapping_groups()
        if not out_of_scope_pairs(groups):
            return ()
        expression = filter_sql_normalized_expression(task_repository, columns, 'Operator')
        if expression is None:
            return ()
        modes = task_repository.ready_cdr_nr_modes()
        terms = []
        for mode in NR_MODES:
            names = frozenset(name.lower() for name in out_of_scope_operators(groups, mode))
            datasets = frozenset(dataset_id for dataset_id, value in modes.items() if value == mode)
            if names and datasets:
                terms.append((datasets, expression, names))
        return tuple(terms)

    def dashboard_combined_requested_columns(definition, dimensions, kind):
        default_filter_keys = {identity(field) for field in ADAPTATIVE_FILTER_FIELDS}
        # The combined-table contract owns fixed preview columns, Default
        # Filter aliases and saved-template KPI fields. Some of those aliases
        # are alternatives, so comparing the whole contract with one physical
        # CDR schema would report false missing columns forever. Dashboard
        # preparation only owns genuinely Dashboard-specific extensions.
        candidates = {
            field for field in definition.custom_fields
            if identity(field) not in default_filter_keys
        }
        candidates.update(
            field for field in definition.filters
            if identity(field) not in default_filter_keys
        )
        dimensions_by_name = {identity(dimension.name): dimension for dimension in dimensions}
        return {
            field for field in candidates
            if (
                identity(field) not in dimensions_by_name
                or f'cdr-{kind}' in dimensions_by_name[identity(field)].sources
            )
        }

    def dashboard_combined_columns_missing(definition, task_repository, dimensions, selected_by_kind):
        """Whether opening this Dashboard must add a genuinely new source column."""
        for kind in selected_by_kind:
            requested = dashboard_combined_requested_columns(definition, dimensions, kind)
            current = {identity(column) for column in task_repository.list_reporting_row_columns(kind)}
            if not {identity(column) for column in requested}.issubset(current):
                return True
        return False

    def ensure_combined_filter_columns(
        definition, task_repository, dimensions, selected_by_kind, chart_entries=None,
    ):
        selected_dimension_keys = {identity(name) for name in definition.custom_fields}
        active_dimensions = tuple(
            dimension for dimension in dimensions if identity(dimension.name) in selected_dimension_keys
        )
        for kind in selected_by_kind:
            requested = dashboard_combined_requested_columns(definition, dimensions, kind)
            if chart_entries:
                requested.update(core.reporting_query_columns(
                    kind, chart_entries, definition.scope == 'multivendor',
                ))
            current = {identity(column) for column in task_repository.list_reporting_row_columns(kind)}
            if {identity(column) for column in requested}.issubset(current):
                continue
            rows_changed = columns_changed = False
            included = core.combined_dataset_ids(task_repository, kind)
            all_ready_sources = [
                row for row in task_repository.list_datasets()
                if row['status'] == 'ready' and str(row['dataset_kind'] or '').casefold() == kind
                and int(row['id']) in included
            ]
            for row in all_ready_sources:
                # A newly requested Dashboard-specific column belongs to the
                # shared source, not merely the currently selected universe.
                # Future dataset selections can therefore stay SQL-only.
                change = task_repository.copy_dataset_rows_to_reporting(
                    row['id'], kind, sorted(requested, key=str.casefold),
                )
                rows_changed = rows_changed or change == 'rows'
                columns_changed = columns_changed or change == 'columns'
            current = {identity(column) for column in task_repository.list_reporting_row_columns(kind)}
            missing_dimensions = tuple(
                dimension for dimension in active_dimensions
                if f'cdr-{kind}' in dimension.sources and identity(dimension.name) not in current
            )
            if missing_dimensions:
                core._incremental_auto_field_table_update(
                    task_repository, task_repository.reporting_rows_table_name(kind),
                    f'cdr-{kind}', (), missing_dimensions, {},
                )
                columns_changed = True
            if rows_changed or columns_changed:
                # Filling new columns keeps prepared Dashboard universes valid;
                # only reinserted rows advance their cache revision.
                core.mark_combined_reporting_updated(task_repository, kind, rows_changed=rows_changed)

    def persistent_selection_key(definition, task_repository, dimensions, selected_by_kind):
        versions = {
            kind: sorted([
                (row['id'], row.get('updated_at'), row.get('processed_at'), row.get('normalization_version'), row.get('row_count'))
                for row in selected
            ], key=lambda row: row[0])
            for kind, selected in selected_by_kind.items()
        }
        revisions = {kind: task_repository.get_workspace_state(f'combined_reporting_updated_{kind}') for kind in selected_by_kind}
        selection_definition = {
            # Named as the selections of before were cached, which stay valid.
            'technology': definition.nr_mode.casefold(),
            'datasets': {
                kind: sorted(set(dataset_ids))
                for kind, dataset_ids in definition.datasets.items()
            },
            'filters': {
                field: sorted(set(values))
                for field, values in definition.filters.items()
            },
            'custom_fields': sorted(set(definition.custom_fields), key=str.casefold),
            'hidden_filters': sorted(set(definition.hidden_filters), key=str.casefold),
            'date_from': definition.date_from,
            'date_to': definition.date_to,
        }
        payload = {
            # Scope changes only how charts group the already selected rows.
            # Keep that presentation setting out of the selection cache key.
            'schema': DASHBOARD_SELECTION_CACHE_VERSION,
            'definition': selection_definition,
            'versions': versions,
            'combined_revisions': revisions,
            'dimensions': core.calculated_dimensions_json(dimensions),
        }
        return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    def selected_date_bounds(task_repository, selected_by_kind, progress=None):
        """Return the inclusive calendar bounds across the selected source datasets."""
        if callable(progress):
            progress(45, 'Checking cached Dataset Universe date limits')
        sources = {}
        for kind, selected in selected_by_kind.items():
            columns = task_repository.list_reporting_row_columns(kind)
            date_column = next((
                resolve_sql_column(columns, candidate)
                for candidate in ('event_start_time', 'Test_Start_Time', 'Timestamp', 'Date')
                if resolve_sql_column(columns, candidate)
            ), None)
            sources[kind] = {
                'datasets': sorted((
                    row['id'], row.get('updated_at'), row.get('processed_at'),
                    row.get('normalization_version'), row.get('row_count'),
                ) for row in selected),
                'revision': task_repository.get_workspace_state(f'combined_reporting_updated_{kind}'),
                'date_column': date_column,
            }
        cache_signature = sha256(json.dumps({
            'schema': DASHBOARD_DATE_BOUNDS_CACHE_VERSION, 'sources': sources,
        }, sort_keys=True, default=str).encode()).hexdigest()
        cache_state_key = f'dashboard_date_bounds_v{DASHBOARD_DATE_BOUNDS_CACHE_VERSION}'
        try:
            cached_bounds = json.loads(task_repository.get_workspace_state(cache_state_key) or '{}')
            if not isinstance(cached_bounds, dict):
                cached_bounds = {}
            if cache_signature in cached_bounds:
                if callable(progress):
                    progress(52, 'Restoring cached Dataset Universe date limits')
                return cached_bounds[cache_signature]
        except (TypeError, ValueError, json.JSONDecodeError):
            cached_bounds = {}
        lower = upper = None
        if callable(progress):
            progress(48, 'Reading Dataset Universe date limits from the combined CDR tables')
        with task_repository.connection() as connection:
            for kind, selected in selected_by_kind.items():
                date_column = sources[kind]['date_column']
                if not date_column:
                    continue
                dataset_ids = [int(row['id']) for row in selected]
                placeholders = ', '.join('?' for _ in dataset_ids)
                table = task_repository._quote_identifier(task_repository.reporting_rows_table_name(kind))
                column = task_repository._quote_identifier(date_column)
                row = connection.execute(
                    f'SELECT MIN(date({column})) AS first_date, MAX(date({column})) AS last_date '
                    f'FROM {table} WHERE dataset_id IN ({placeholders})', dataset_ids,
                ).fetchone()
                for value, is_lower in ((row['first_date'], True), (row['last_date'], False)):
                    try:
                        parsed = date.fromisoformat(str(value)) if value else None
                    except ValueError:
                        parsed = None
                    if parsed is not None and (lower is None or parsed < lower) and is_lower:
                        lower = parsed
                    if parsed is not None and (upper is None or parsed > upper) and not is_lower:
                        upper = parsed
        bounds = None if lower is None or upper is None else {'min': lower.isoformat(), 'max': upper.isoformat()}
        # This result is immutable while the selected datasets and their
        # combined-table revisions are unchanged.  Persist a small bounded
        # map so restarting the server does not repeat a full date scan just
        # to validate a Dashboard preview manifest.
        cached_bounds[cache_signature] = bounds
        if len(cached_bounds) > 128:
            cached_bounds = dict(list(cached_bounds.items())[-128:])
        task_repository.set_workspace_state(cache_state_key, json.dumps(cached_bounds, separators=(',', ':')))
        if callable(progress):
            progress(52, 'Caching Dataset Universe date limits')
        return bounds

    def apply_selected_date_bounds(definition, bounds):
        if not bounds:
            return
        lower, upper = date.fromisoformat(bounds['min']), date.fromisoformat(bounds['max'])
        definition.date_from = lower if definition.date_from == 'Oldest' or definition.date_from is None or not lower <= definition.date_from <= upper else definition.date_from
        definition.date_to = upper if definition.date_to == 'Newest' or definition.date_to is None or not lower <= definition.date_to <= upper else definition.date_to

    def combined_filter_options(
        definition, selected_by_kind, fields, task_repository, connection,
    ):
        """Calculate every adaptive facet with one combined-table scan per CDR kind."""
        options = {field_name: set() for field_name in fields}
        active_filter_keys = {identity(field_name) for field_name in definition.filters}
        facet_groups: dict[str | None, list[str]] = {None: []}
        for field_name in fields:
            excluded = field_name if identity(field_name) in active_filter_keys else None
            facet_groups.setdefault(excluded, []).append(field_name)
        for kind, selected in selected_by_kind.items():
            columns = task_repository.list_reporting_row_columns(kind)
            available = {
                field_name: filter_sql_value_expression(task_repository, columns, field_name)
                for field_name in fields
            }
            available = {
                field_name: expression for field_name, expression in available.items()
                if expression is not None
            }
            if not available:
                continue
            table = task_repository._quote_identifier(task_repository.reporting_rows_table_name(kind))
            base_definition = definition.model_copy(deep=True)
            base_definition.filters = {}
            base_where, base_params = selection_where(
                task_repository, kind, [int(row['id']) for row in selected],
                base_definition, columns=columns,
            )
            match_columns, match_parameters, group_aliases = [], [], {}
            for group_index, (excluded, _group_fields) in enumerate(facet_groups.items()):
                alias = f'facet_match_{group_index}'
                predicate, predicate_params = selection_filter_where(
                    task_repository, columns, definition, exclude=excluded,
                )
                match_columns.append(f'({predicate}) AS {alias}')
                match_parameters.extend(predicate_params)
                group_aliases[excluded] = alias
            aggregates = []
            field_order = []
            for field_name in fields:
                expression = available.get(field_name)
                if expression is None:
                    continue
                excluded = field_name if identity(field_name) in active_filter_keys else None
                aggregates.append(
                    f'json_group_array(DISTINCT {expression}) '
                    f'FILTER (WHERE {group_aliases[excluded]}) AS facet_{len(field_order)}'
                )
                field_order.append(field_name)
            query = (
                f'WITH scoped AS (SELECT * FROM {table} WHERE {base_where}), '
                f'matched AS (SELECT *, {", ".join(match_columns)} FROM scoped) '
                f'SELECT {", ".join(aggregates)} FROM matched'
            )
            row = connection.execute(query, [*base_params, *match_parameters]).fetchone()
            for index, field_name in enumerate(field_order):
                encoded_values = row[f'facet_{index}'] if row else '[]'
                options[field_name].update(
                    str(value) for value in json.loads(encoded_values or '[]') if value is not None
                )
        return {field_name: sorted(values, key=str.casefold) for field_name, values in options.items()}

    def profile_filter_options(definition, dimensions, selected_by_kind, fields, task_repository, checkpoint=None):
        """Load large-dashboard facet values from selected CDR profiles.

        ``checkpoint`` runs between fields, so a background preparation stops
        promptly when a user-requested preparation is waiting.
        """
        options = {field_name: set() for field_name in fields}
        incomplete_fields = set()
        dataset_ids = [int(dataset['id']) for selected in selected_by_kind.values() for dataset in selected]
        vendor_catalogues = task_repository.cdr_catalogues_by_dataset(dataset_ids)
        missing_vendor_catalogues = set(task_repository.missing_cdr_vendor_only_ids(dataset_ids))
        missing_cluster_catalogues = set(task_repository.missing_cdr_cluster_ids(dataset_ids))
        for selected in selected_by_kind.values():
            for dataset in selected:
                try:
                    stored = dataset.get('filter_options') or json.loads(dataset.get('filter_options_json') or '{}')
                except (TypeError, json.JSONDecodeError):
                    stored = {}
                lookup = {identity(column): values for column, values in stored.items()} if isinstance(stored, dict) else {}
                # One schema read per CDR instead of one per field and alias.
                dataset_columns = set(task_repository.list_dataset_row_columns(int(dataset['id'])))
                for field_name in fields:
                    if callable(checkpoint):
                        checkpoint()
                    if identity(field_name) in {identity('Vendor'), identity('Vendor_Only')} and int(dataset['id']) not in missing_vendor_catalogues:
                        options[field_name].update(vendor_catalogues.get(int(dataset['id']), {}).get('vendors_only', []))
                        continue
                    if identity(field_name) in {identity('Operator_Vendor'), identity('OP_Vendor')} and int(dataset['id']) in vendor_catalogues:
                        options[field_name].update(vendor_catalogues.get(int(dataset['id']), {}).get('vendors', []))
                        continue
                    if identity(field_name) == identity('Cluster') and int(dataset['id']) not in missing_cluster_catalogues:
                        options[field_name].update(vendor_catalogues.get(int(dataset['id']), {}).get('clusters', []))
                        continue
                    aliases = next((values for label, values in FILTER_COLUMNS.items() if identity(label) == identity(field_name)), (field_name,))
                    resolved = next((
                        column for alias in aliases
                        if dataset_columns and (column := task_repository._resolve_dataset_row_column_name(dataset_columns, alias))
                    ), None)
                    if resolved is None:
                        continue
                    lookup_keys = list(dict.fromkeys([
                        identity(resolved), identity(vendor_filter_column(field_name)),
                        *(identity(alias) for alias in aliases),
                    ]))
                    values = next((lookup[key] for key in lookup_keys if isinstance(lookup.get(key), list)), None)
                    if not isinstance(values, list):
                        incomplete_fields.add(field_name)
                        continue
                    if len(values) >= 50:
                        values = dataset_distinct_values(task_repository, dataset, resolved)
                    options[field_name].update(str(value) for value in values if value is not None)
        dimensions_by_name = {identity(dimension.name): dimension for dimension in dimensions}
        for field_name in fields:
            dimension = dimensions_by_name.get(identity(field_name))
            if dimension:
                incomplete_fields.discard(field_name)
                options[field_name].update(str(rule.value) for rule in dimension.rules if str(rule.value).strip())
                if str(dimension.default).strip():
                    options[field_name].add(str(dimension.default))
            # Saved filter values are not options by themselves: only values the
            # selected CDRs (or calculated dimensions) provide are offered.
        missing_fields = [
            field_name for field_name in fields
            if not options[field_name] or field_name in incomplete_fields
        ]
        if missing_fields:
            # Older upload profiles do not contain every Dashboard facet. Read
            # only the missing catalogues from the narrow combined tables. An
            # adaptive facet must ignore its own current restriction so users
            # can see and select values outside the saved selection.
            with task_repository.connection() as connection:
                queried = combined_filter_options(
                    definition, selected_by_kind, missing_fields, task_repository, connection,
                )
            for field_name, values in queried.items():
                options[field_name].update(values)
        return {field_name: sorted(values, key=str.casefold) for field_name, values in options.items()}

    def materialize_selection(
        definition, task_repository, dimensions, selected_by_kind, fields, *,
        use_profile_options=False, known_full_row_counts=None, progress=None, checkpoint=None,
    ):
        cache_key = persistent_selection_key(definition, task_repository, dimensions, selected_by_kind)
        estimated_rows = sum(sum(int(row.get('row_count') or 0) for row in selected) for selected in selected_by_kind.values())
        use_profile_options = use_profile_options or estimated_rows > DASHBOARD_PROFILE_SELECTION_THRESHOLD
        if callable(progress):
            progress(55, 'Checking the filtered Dashboard selection cache')
        # Dashboard preparation is already serialized by dashboard_work_gate.
        # Do not retain the shared task-registry lock while SQLite counts or
        # facet queries run: progress polling needs that lock to report the
        # exact live phase during a potentially long combined-table scan.
        with task_repository.connection() as connection:
            cached = connection.execute(
                'SELECT id, options_json, row_counts_json, universe_row_counts_json FROM dashboard_filter_selections WHERE cache_key = ?',
                (cache_key,),
            ).fetchone()
            if cached:
                options = json.loads(cached['options_json'])
                missing_fields = [field for field in fields if field not in options]
                if missing_fields:
                    options.update(combined_filter_options(
                        definition, selected_by_kind, missing_fields, task_repository, connection,
                    ))
                    connection.execute('UPDATE dashboard_filter_selections SET options_json = ? WHERE id = ?',
                                       (json.dumps(options), cached['id']))
                if callable(progress):
                    progress(78, 'Restoring cached row counts and filter options')
                connection.execute('UPDATE dashboard_filter_selections SET last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?', (cached['id'],))
                return (
                    int(cached['id']), cache_key,
                    options, json.loads(cached['row_counts_json']),
                    json.loads(cached['universe_row_counts_json']), True,
                )
            known_counts = known_full_row_counts if isinstance(known_full_row_counts, dict) else None
            if callable(progress):
                progress(
                    62,
                    'Using materialized combined CDR row counts for the complete Dataset Universe'
                    if known_counts is not None else 'Counting reduced and filtered Universe rows in the combined CDR tables',
                )
            row_counts = dict(known_counts or {})
            universe_row_counts = dict(known_counts or {})
            selected_groups = list(selected_by_kind.items())
            for group_index, (kind, selected) in enumerate(selected_groups):
                if known_counts is not None:
                    continue
                if callable(progress):
                    progress(
                        62 + round(group_index * 6 / max(len(selected_groups), 1)),
                        f'Counting Filtered Universe CDR-{kind.title()} rows in the combined table',
                    )
                dataset_ids = [int(row['id']) for row in selected]
                columns = task_repository.list_reporting_row_columns(kind)
                cached_counts = cached_selection_counts(task_repository, kind, selected, definition, columns)
                if cached_counts is not None:
                    universe_row_counts[kind], row_counts[kind] = cached_counts
                    continue
                universe_definition = definition.model_copy(deep=True)
                universe_definition.filters = {}
                universe_where, universe_params = selection_where(
                    task_repository, kind, dataset_ids, universe_definition, columns=columns,
                )
                filtered_where, filtered_params = selection_filter_where(
                    task_repository, columns, definition,
                )
                table = task_repository._quote_identifier(task_repository.reporting_rows_table_name(kind))
                counts = connection.execute(
                    f'''SELECT COUNT(*) AS universe_count,
                               SUM(CASE WHEN {filtered_where} THEN 1 ELSE 0 END) AS filtered_count
                        FROM {table} WHERE {universe_where}''',
                    [*filtered_params, *universe_params],
                ).fetchone()
                universe_row_counts[kind] = int(counts['universe_count'] or 0)
                row_counts[kind] = int(counts['filtered_count'] or 0)
            # A full, unfiltered CDR selection can use its upload-time profile
            # catalogue. This avoids wide DISTINCT scans while row counts and
            # chart previews remain exact from the combined reporting tables.
            if use_profile_options:
                if callable(progress):
                    progress(70, 'Loading filter options from Dataset profiles')
                options = profile_filter_options(
                    definition, dimensions, selected_by_kind, fields, task_repository, checkpoint=checkpoint,
                )
            else:
                if callable(progress):
                    progress(70, 'Calculating adaptive filter options in one pass per CDR table')
                options = combined_filter_options(
                    definition, selected_by_kind, fields, task_repository, connection,
                )
            # Expensive counts and facet scans above are read-only. Start the
            # coordinated Workspace write transaction only once their final
            # cache payload is ready.
            if callable(progress):
                progress(78, 'Caching filtered row counts and filter options')
            # Another process (for example a Reporting worker) may have cached
            # the same selection meanwhile; keep a single row per cache key.
            connection.execute(
                'INSERT INTO dashboard_filter_selections '
                '(cache_key, options_json, row_counts_json, universe_row_counts_json) VALUES (?, ?, ?, ?) '
                'ON CONFLICT(cache_key) DO UPDATE SET options_json = excluded.options_json, '
                'row_counts_json = excluded.row_counts_json, universe_row_counts_json = excluded.universe_row_counts_json',
                (cache_key, json.dumps(options), json.dumps(row_counts), json.dumps(universe_row_counts)),
            )
            selection_id = int(connection.execute(
                'SELECT id FROM dashboard_filter_selections WHERE cache_key = ?', (cache_key,)).fetchone()['id'])
            stale = connection.execute(
                'SELECT id FROM dashboard_filter_selections ORDER BY last_accessed_at DESC, id DESC LIMIT -1 OFFSET ?',
                (DASHBOARD_SELECTION_CACHE_LIMIT,),
            ).fetchall()
            for row in stale:
                connection.execute('DELETE FROM dashboard_filter_selections WHERE id = ?', (row['id'],))
            return selection_id, cache_key, options, row_counts, universe_row_counts, True

    def mapped_values(field, values, mapper):
        """The values of one filter with their Operator and Vendor Maps labels (Vendor_Operator from Operator_Vendor)."""
        kind = field_kind(vendor_filter_column(field))
        if kind == 'vendor_operator':
            return mapper.values('vendor_operator', mapper.vendor_operators(mapper.values('operator_vendor', values)))
        return mapper.values(kind, values) if kind else values

    def mapped_filter_options(options, task_repository):
        """Operator, Vendor, Operator_Vendor and Vendor_Operator values with their Operator and Vendor Maps labels."""
        mapper = ValueMapper.from_repository(task_repository)
        return {field: mapped_values(field, values, mapper) for field, values in options.items()}

    def load_filter_options_batch(definition, field_names, task_repository):
        """Load several unrestricted filter catalogues of the selected CDRs at once.

        Values come from the CDR upload profiles; only fields missing from
        them are read from the combined tables, in one pass per CDR table.
        """
        fields = list(dict.fromkeys(str(field).strip() for field in field_names if str(field).strip()))
        validate(definition, task_repository)
        dimensions = core.load_repository_calculated_dimensions(task_repository)
        selected_by_kind = selected_sources(definition, task_repository)
        requested_definition = unfiltered_definition(definition).model_copy(deep=True)
        for field in fields:
            known_default = any(identity(field) == identity(item) for item in ADAPTATIVE_FILTER_FIELDS)
            if not known_default and not any(identity(field) == identity(item) for item in requested_definition.custom_fields):
                requested_definition.custom_fields.append(field)
        ensure_combined_filter_columns(requested_definition, task_repository, dimensions, selected_by_kind)
        options = mapped_filter_options(
            profile_filter_options(requested_definition, dimensions, selected_by_kind, fields, task_repository), task_repository,
        )
        return {field: [str(value) for value in options.get(field, [])] for field in fields}

    def load_filter_options(definition, field_name, task_repository):
        """Load one adaptive filter catalogue without preparing Dashboard charts."""
        field_name = field_name.strip()
        validate(definition, task_repository)
        dimensions = core.load_repository_calculated_dimensions(task_repository)
        selected_by_kind = selected_sources(definition, task_repository)
        requested_definition = definition.model_copy(deep=True)
        known_default = any(identity(field_name) == identity(field) for field in ADAPTATIVE_FILTER_FIELDS)
        if not known_default and not any(identity(field_name) == identity(field) for field in requested_definition.custom_fields):
            requested_definition.custom_fields.append(field_name)
        ensure_combined_filter_columns(requested_definition, task_repository, dimensions, selected_by_kind)
        apply_selected_date_bounds(requested_definition, selected_date_bounds(task_repository, selected_by_kind))
        values = set()
        resolved = False
        with task_repository.connection() as connection:
            for kind, selected in selected_by_kind.items():
                columns = task_repository.list_reporting_row_columns(kind)
                value_expression = filter_sql_value_expression(task_repository, columns, field_name)
                if value_expression is None:
                    continue
                resolved = True
                where, params = selection_where(
                    task_repository, kind, [int(row['id']) for row in selected],
                    requested_definition, exclude=field_name, columns=columns,
                )
                table = task_repository._quote_identifier(task_repository.reporting_rows_table_name(kind))
                rows = connection.execute(
                    f'SELECT DISTINCT {value_expression} AS value '
                    f'FROM {table} WHERE {where}', params,
                ).fetchall()
                values.update(str(row['value']) for row in rows)
        if not resolved:
            raise HTTPException(400, f'The selected CDRs do not contain the {field_name} field.')
        if field_kind(vendor_filter_column(field_name)):
            return mapped_values(field_name, values, ValueMapper.from_repository(task_repository))
        return sorted(values, key=str.casefold)

    def unfiltered_definition(definition):
        """Return the Dashboard without its filters, to read the values its CDRs provide."""
        return definition.model_copy(update={'filters': {}})

    def dashboard_geography_catalogue(definition, selected_by_kind, task_repository) -> dict[str, list[str]]:
        """Return Vendor, Region and City values of the selected CDRs.

        Values come from the per-CDR catalogue. A Region or City catalogue can
        be empty when the CDR stores that field under another alias, so the
        Dashboard's own filter values (which resolve those aliases) complete it.
        """
        selected_ids = [int(row['id']) for rows in selected_by_kind.values() for row in rows]
        if not selected_ids:
            return {'vendors': [], 'regions': [], 'cities': []}
        core.backfill_cdr_catalogues(selected_ids, task_repository)
        catalogue = dict(task_repository.cdr_catalogue_values(selected_ids))
        cached = task_repository.cdr_catalogues_by_dataset(selected_ids)
        catalogue['vendors'] = sort_vendor_values({value for item in cached.values() for value in (item.get('vendors_only') or [])})
        missing = [(field, key) for field, key in (('Region', 'regions'), ('City', 'cities')) if not catalogue.get(key)]
        if missing:
            fallback = profile_filter_options(
                unfiltered_definition(definition), [], selected_by_kind, [field for field, _key in missing], task_repository,
            )
            for field, key in missing:
                catalogue[key] = sorted(
                    {str(value).strip() for value in fallback.get(field) or [] if str(value).strip()},
                    key=str.casefold,
                )
        return catalogue

    campaign_backfills: set[tuple[str, int]] = set()

    def schedule_campaign_backfill(dataset_ids: list[int], task_repository) -> None:
        """Read missing CDR Campaigns once in the background; the viewer polls for them."""
        database = str(Path(task_repository.db_path).resolve())
        with lock:
            pending = [dataset_id for dataset_id in dataset_ids if (database, dataset_id) not in campaign_backfills]
            campaign_backfills.update((database, dataset_id) for dataset_id in pending)
        if not pending:
            return

        def run() -> None:
            try:
                core.backfill_cdr_campaigns(pending, task_repository)
            finally:
                with lock:
                    campaign_backfills.difference_update((database, dataset_id) for dataset_id in pending)

        Thread(target=run, name='dashboard-campaign-backfill', daemon=True).start()

    def dashboard_campaign_values(
        definition, selected_by_kind, task_repository, *, wait: bool = True,
    ) -> tuple[list[str], bool]:
        """Return the compact Campaigns (for example ``2026-Q2`` or ``2026-Q2-SA``) behind a Dashboard.

        A Campaign filter limits them to its values; otherwise every Campaign of
        the selected CDRs is read from their cached catalogue. CDRs catalogued
        before Campaigns were cached are read once: immediately when ``wait``
        is set, otherwise in the background, reporting that some are pending.
        """
        filters = definition.filters if isinstance(definition.filters, dict) else {}
        configured = next((values for key, values in filters.items() if identity(key) == identity('Campaign')), None)
        if isinstance(configured, str):
            configured = [configured]
        configured = [str(value).strip() for value in configured or [] if str(value).strip()]
        dataset_ids = [int(row['id']) for rows in selected_by_kind.values() for row in rows]
        pending = False
        if dataset_ids:
            core.backfill_cdr_catalogues(dataset_ids, task_repository)
            missing = task_repository.missing_cdr_campaign_ids(dataset_ids)
            if missing and wait:
                core.backfill_cdr_campaigns(missing, task_repository)
            elif missing:
                schedule_campaign_backfill(missing, task_repository)
                pending = True
        available = task_repository.cdr_catalogue_values(dataset_ids)['campaigns'] if dataset_ids else []
        # A Campaign filter only names the Campaigns its CDRs actually contain.
        values = values_present_in_cdrs(configured, available) if configured else available
        labels = {compact_campaign_value(value) for value in values}
        return sorted((label for label in labels if label), key=campaign_sort_key), pending

    def dashboard_campaigns_label(campaigns: list[str]) -> str:
        if not campaigns:
            return ''
        return f"{'Campaign' if len(campaigns) == 1 else 'Campaigns'}: {', '.join(campaigns)}"

    def load_dashboard_geography_options(definition, task_repository) -> dict[str, list[str]]:
        """Load Vendor and geography catalogues from the per-CDR persisted cache."""
        validate(definition, task_repository)
        selected_by_kind = selected_sources(definition, task_repository)
        options = dashboard_geography_catalogue(definition, selected_by_kind, task_repository)
        operators = profile_filter_options(
            unfiltered_definition(definition), [], selected_by_kind, ['Operator'], task_repository,
        )['Operator']
        campaigns, campaigns_pending = dashboard_campaign_values(
            definition, selected_by_kind, task_repository, wait=False,
        )
        mapper = ValueMapper.from_repository(task_repository)
        return {
            'campaigns': campaigns,
            'campaigns_pending': campaigns_pending,
            'operators': mapper.values('operator', operators),
            'vendors': mapper.values('vendor', options['vendors']),
            'regions': options['regions'],
            'cities': options['cities'],
        }

    def build_preview(definition, user, *, workspace: str | None = None, cancelled=None, progress=None):
        def ensure_not_cancelled():
            if callable(cancelled) and cancelled():
                raise RuntimeError('Dashboard preparation cancelled.')

        def report(percent, detail):
            # Every progress step is also a cancellation point.
            ensure_not_cancelled()
            if callable(progress):
                progress(percent, detail)

        workspace = workspace or workspace_key()
        report(5, 'Validating the Dashboard template and selected source datasets')
        ensure_not_cancelled()
        task_repository = Repository(Path(workspace), core.repository.global_db_path)
        entries = validate(definition, task_repository)
        dimensions = core.load_repository_calculated_dimensions(task_repository)
        selected_by_kind = selected_sources(definition, task_repository)
        if any(entry.source_kind == 'all' for entry in entries):
            # A virtual source needs the physical RF fields of every selected
            # CDR type, including templates added after CDR ingestion.
            for kind, datasets in selected_by_kind.items():
                for dataset in datasets:
                    available = task_repository.list_dataset_row_columns(int(dataset['id']))
                    requested = [column for column in available if identity(column) in {identity(field) for field in rf_source_columns(kind)}]
                    task_repository.copy_dataset_rows_to_reporting(int(dataset['id']), kind, requested)
        if any(any(entry_dynamic_fields(entry)) or entry_uses_nr_mode(entry) for entry in entries):
            ensure_combined_filter_columns(definition, task_repository, dimensions, selected_by_kind, chart_entries=entries)
        selected_source_rows = {
            kind: sum(int(dataset.get('row_count') or 0) for dataset in selected)
            for kind, selected in selected_by_kind.items()
        }
        if dashboard_combined_columns_missing(definition, task_repository, dimensions, selected_by_kind):
            report(20, 'Adding new Dashboard-specific fields to the combined CDR tables')
            ensure_combined_filter_columns(definition, task_repository, dimensions, selected_by_kind)
        ensure_not_cancelled()
        date_bounds = selected_date_bounds(task_repository, selected_by_kind, progress=report)
        apply_selected_date_bounds(definition, date_bounds)
        selected_dataset_ids = {dataset_id for ids in definition.datasets.values() for dataset_id in ids}
        available_fields = {column for dataset_id in selected_dataset_ids for column in task_repository.list_dataset_row_columns(dataset_id)}
        available_fields.update(dimension.name for dimension in dimensions)
        hidden_filter_keys = {identity(field) for field in definition.hidden_filters}
        fields = {field for field in ADAPTATIVE_FILTER_FIELDS if identity(field) not in hidden_filter_keys}
        fields.update(definition.custom_fields)
        fields.update(field for entry in entries for field in entry_dynamic_fields(prepare_multivendor_catalog_entry(entry, definition.vendor_comparison) if definition.scope == "multivendor" else entry) if field)
        fields = sorted(fields, key=str.casefold)
        use_profile_options = bool(
            date_bounds
            and not definition.filters
            and str(definition.date_from) == date_bounds['min']
            and str(definition.date_to) == date_bounds['max']
        )
        complete_unfiltered_universe = is_complete_unfiltered_universe(
            definition, selected_by_kind, task_repository, date_bounds,
        )
        selection_id, selection_key, options, row_counts, universe_rows, rows_exact = materialize_selection(
            definition, task_repository, dimensions, selected_by_kind, fields,
            use_profile_options=use_profile_options,
            known_full_row_counts=selected_source_rows if complete_unfiltered_universe else None,
            progress=report, checkpoint=ensure_not_cancelled,
        )
        report(82, 'Preparing the Dashboard slide structure and chart positions')
        slides = OrderedDict()
        entries = expand_dashboard_layouts(entries, definition, options, task_repository)
        slide_entries_by_number: dict[int, list] = defaultdict(list)
        for entry in entries:
            slide_entries_by_number[entry.slide].append(entry)
        deck = Presentation(core.settings.powerpoint_template)
        fields_by_mode: dict[str, dict[str, set[str]]] = {}
        for editor_index, (index, entry) in enumerate(sorted(enumerate(entries), key=lambda item: (item[1].slide, item[0]))):
            editor_index = entry.template_index if entry.template_index is not None else editor_index
            slide = slides.setdefault(entry.slide, {
                'number': entry.slide,
                'comment_key': dashboard_slide_comment_key(slide_entries_by_number[entry.slide]),
                'title': entry.slide_title,
                'subtitle': entry.slide_subtitle,
                'layout': entry.layout,
                'structural_type': entry.structural_type or '',
                'compact_titles': compact_grid_layout(entry.layout),
                'charts': [],
                'focus_row': editor_index,
            })
            if not entry.structural_type:
                title_label, title_base = chart_title_parts(entry)
                chart = {
                    'index': index, 'title': entry.chart_title, 'title_label': title_label, 'title_base': title_base,
                    'source': entry.source_kind,
                    'cdr_source': entry.cdr_source, 'chart_type': entry.chart_type,
                    'available': bool(selected_by_kind) if entry.source_kind == 'all' else entry.source_kind in selected_by_kind, 'focus_row': editor_index,
                }
                if unread := chart_nr_mode_unread(entry, definition):
                    # A chart of one NR Mode (NR Mode IN (SA)) in a Dashboard that reads the other one.
                    chart.update(available=False, unavailable=unread)
                elif dashboard_nr_mode(definition) == NSA_VS_SA and entry.source_kind in selected_by_kind:
                    # A field only the CDRs of one NR Mode have: the chart says which NR Mode has no samples.
                    if entry.source_kind not in fields_by_mode:
                        fields_by_mode[entry.source_kind] = core.cdr_fields_by_nr_mode(
                            task_repository, entry.source_kind, [int(row['id']) for row in selected_by_kind[entry.source_kind]])
                    if missing := missing_nr_mode_fields(entry, fields_by_mode[entry.source_kind], NSA_VS_SA):
                        chart['nr_mode_note'] = missing_nr_mode_note(missing)
                slide['charts'].append(chart)
        for slide in slides.values():
            positions = normalized_frame_positions(_layout_chart_frames(_named_slide_layout(deck, slide['layout'])))
            if positions and len(positions) >= len(slide['charts']):
                for chart, position in zip(slide['charts'], positions):
                    chart['position'] = position
        token = uuid4().hex
        payload = {
            'slides': list(slides.values()),
            'options': cascading_dashboard_options(mapped_filter_options(options, task_repository), definition, task_repository),
            # The CDRs the Dashboard uses, chosen from its NR Mode and Campaign.
            'cdrs': describe_cdrs(task_repository, {kind: [int(row['id']) for row in rows] for kind, rows in selected_by_kind.items()}),
            'filter_fields': list(ADAPTATIVE_FILTER_FIELDS),
            'available_fields': sorted(available_fields, key=str.casefold),
            'rows': row_counts,
            'universe_rows': universe_rows,
            'rows_exact': rows_exact,
            'date_bounds': date_bounds,
            # The selection behind the slides: generated comments written for another one are out of date.
            'selection_key': selection_key,
        }
        add_dynamic_grid_metadata(payload, entries, deck)
        with lock:
            snapshots[token] = Snapshot(
                workspace, user.username, entries, {}, definition.scope == 'multivendor',
                definition.model_copy(deep=True), tuple(dimensions), selection_id, selection_key, payload,
                cancelled=cancelled,
            )
            # Keep recent explicitly prepared snapshots lightweight enough for
            # users to switch between them without rebuilding their filters.
            while len(snapshots) > 128:
                snapshots.popitem(last=False)
        ensure_not_cancelled()
        report(90, 'Dashboard selection and slide structure are ready')
        return {**payload, 'token': token}

    def preview_manifest_path(workspace: str, dashboard_id: str, fingerprint: str) -> Path:
        cache_key = sha256(
            f'{DASHBOARD_PREVIEW_MANIFEST_VERSION}:{dashboard_id}:{fingerprint}'.encode()
        ).hexdigest()
        return preview_manifest_cache_dir(workspace) / f'{cache_key}.json'

    def persist_preview_manifest(
        workspace: str,
        dashboard_id: str,
        fingerprint: str,
        token: str,
    ) -> None:
        with lock:
            snapshot = snapshots.get(token)
            if snapshot is None:
                return
            manifest = {
                'version': DASHBOARD_PREVIEW_MANIFEST_VERSION,
                'dashboard_id': dashboard_id,
                'fingerprint': fingerprint,
                'definition': snapshot.definition.model_dump(mode='json'),
                'selection_id': snapshot.selection_id,
                'selection_key': snapshot.selection_key,
                'payload': snapshot.payload,
            }
        manifest_path = preview_manifest_path(workspace, dashboard_id, fingerprint)
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = manifest_path.with_suffix(f'.{uuid4().hex}.tmp')
            temporary.write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8')
            temporary.replace(manifest_path)
            core.invalidate_workspace_size_cache(Path(workspace).parent)
        except OSError:
            pass

    def restore_preview_manifest(
        workspace: str,
        dashboard_id: str,
        fingerprint: str,
        *,
        materialize: bool = True,
        manifest: dict | None = None,
    ) -> dict | None:
        manifest_path = preview_manifest_path(workspace, dashboard_id, fingerprint)
        try:
            if manifest is None:
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if (
                manifest.get('version') != DASHBOARD_PREVIEW_MANIFEST_VERSION
                or manifest.get('dashboard_id') != dashboard_id
                or manifest.get('fingerprint') != fingerprint
            ):
                return None
            definition = DashboardDefinition.model_validate(manifest['definition'])
            task_repository = Repository(Path(workspace), core.repository.global_db_path)
            entries = validate(definition, task_repository)
            dimensions = core.load_repository_calculated_dimensions(task_repository)
            selected_by_kind = selected_sources(definition, task_repository)
            selection_key = persistent_selection_key(definition, task_repository, dimensions, selected_by_kind)
            if selection_key != manifest.get('selection_key'):
                return None
            selection_id = int(manifest['selection_id'])
            with task_repository.connection() as connection:
                selection = connection.execute(
                    'SELECT id FROM dashboard_filter_selections WHERE id = ? AND cache_key = ?',
                    (selection_id, selection_key),
                ).fetchone()
            if selection is None:
                return None
            payload = manifest['payload']
            entries = expand_dashboard_layouts(entries, definition, payload.get('options', {}), task_repository)
            if not isinstance(payload, dict) or not isinstance(payload.get('slides'), list):
                return None
            if 'grid_layouts' not in payload:
                # Universes prepared by earlier versions gain the dynamic grid
                # metadata without being prepared again.
                add_dynamic_grid_metadata(payload, entries)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, sqlite3.Error):
            return None
        if not materialize:
            return dict(payload)
        definition_dump = definition.model_dump(mode='json')
        with lock:
            # Reopening the same cached universe reuses its live snapshot (and
            # any chart frames it already holds) instead of adding a copy.
            for existing_token, existing in reversed(snapshots.items()):
                if (
                    existing.workspace == workspace and existing.owner == '*'
                    and existing.selection_key == selection_key
                    and existing.selection_id == selection_id
                    and existing.definition.model_dump(mode='json') == definition_dump
                ):
                    snapshots.move_to_end(existing_token)
                    return {**existing.payload, 'token': existing_token}
        token = uuid4().hex
        with lock:
            snapshots[token] = Snapshot(
                workspace, '*', entries, {}, definition.scope == 'multivendor',
                definition, tuple(dimensions), selection_id, selection_key,
                payload,
            )
            while len(snapshots) > 128:
                snapshots.popitem(last=False)
        return {**payload, 'token': token}

    def preview_cache_identity(definition):
        """Return the parts of a Dashboard definition that affect its prepared data."""
        identity_definition = definition.model_dump(mode='json')
        identity_definition.pop('name', None)
        identity_definition.pop('slide_comments', None)
        identity_definition.pop('slide_comment_meta', None)
        identity_definition['datasets'] = {
            kind: sorted(set(dataset_ids))
            for kind, dataset_ids in identity_definition.get('datasets', {}).items()
            if dataset_ids
        }
        return identity_definition

    def restore_matching_preview_manifest(
        workspace: str, dashboard_id: str, definition: DashboardDefinition, *, materialize: bool = True,
    ):
        """Restore a persistent preview by definition, including non-default session universes."""
        task_repository = Repository(Path(workspace), core.repository.global_db_path)
        requested = definition.model_copy(deep=True)
        try:
            apply_selected_date_bounds(requested, selected_date_bounds(
                task_repository, selected_sources(requested, task_repository),
            ))
            requested_fingerprint = dashboard_preview_fingerprint(
                requested.model_dump(mode='json'), task_repository,
            )
            requested_identity = preview_cache_identity(requested)
            # Manifests are stored under a path derived from their fingerprint,
            # so the matching manifest is read directly instead of scanning
            # (and parsing) every cached manifest in the workspace.
            manifest_path = preview_manifest_path(workspace, dashboard_id, requested_fingerprint)
            if not manifest_path.is_file():
                return None
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            stored_definition = DashboardDefinition.model_validate(manifest['definition'])
            if preview_cache_identity(stored_definition) != requested_identity:
                return None
            return restore_preview_manifest(
                workspace, dashboard_id, requested_fingerprint, materialize=materialize, manifest=manifest,
            )
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, sqlite3.Error):
            return None

    def dashboard_warmup_definitions(raw_definition: dict, task_repository: Repository) -> list[DashboardDefinition]:
        """Return the automatic, date-unrestricted universes pre-cached for a Dashboard.

        The universes are every campaign plus the newest one, two, three and four campaigns of the
        Dashboard's NR Mode (their CDRs chosen as always), skipping those that repeat an earlier one.
        """
        base = runtime_dashboard_definition(raw_definition, task_repository)
        nr_mode = dashboard_nr_mode(base)
        campaigns = campaign_values(task_repository, nr_mode)
        filters = {field: values for field, values in (base.get('filters') or {}).items() if identity(field) != identity('Campaign')}
        variants = [None, *(latest_campaigns(campaigns, count) for count in range(1, DASHBOARD_WARMUP_LATEST_COUNTS + 1))]
        definitions = []
        seen = set()
        for chosen in variants:
            datasets = resolve_cdrs(task_repository, nr_mode, chosen or [], KINDS)
            if not any(datasets.values()):
                continue
            signature = json.dumps({kind: sorted(ids) for kind, ids in datasets.items()}, sort_keys=True)
            if signature in seen:
                continue
            seen.add(signature)
            definition = DashboardDefinition.model_validate({
                **base, 'filters': {**filters, **({'Campaign': chosen} if chosen else {})}, 'datasets': datasets,
            })
            # Oldest/Newest deliberately keeps this cache valid for the full
            # automatic date range instead of pinning it to today's bounds.
            definition.date_from = 'Oldest'
            definition.date_to = 'Newest'
            definitions.append(definition)
        return definitions

    def dashboard_creation_rank(workspace: str, dashboard_id: str) -> int:
        """Position of a Dashboard in creation order (the saved library order)."""
        try:
            stored = json.loads(
                Repository(Path(workspace), core.repository.global_db_path).get_workspace_state(STATE_KEY) or '{}'
            )
        except (OSError, sqlite3.Error, TypeError, ValueError):
            stored = {}
        identifiers = list(stored) if isinstance(stored, dict) else []
        return identifiers.index(dashboard_id) if dashboard_id in identifiers else len(identifiers)

    def warmup_priority(key, entry) -> tuple:
        # One Dashboard at a time, in creation order.
        return (int(entry.get('rank') or 0), int(entry.get('sequence') or 0))

    def warmup_should_yield(key) -> bool:
        """Whether the running warm-up must pause for more important work."""
        state = dashboard_warmup_cancellations.get(key) or {}
        if state.get('requested') or core.APP_SHUTTING_DOWN.is_set():
            return True
        return bool(dashboard_foreground_work.get(key[0]))

    @contextmanager
    def foreground_dashboard_work(workspace: str):
        """Pause the warm-up while a user-requested preparation or export runs."""
        with dashboard_warmup_condition:
            dashboard_foreground_work[workspace] = dashboard_foreground_work.get(workspace, 0) + 1
        try:
            yield
        finally:
            with dashboard_warmup_condition:
                remaining = dashboard_foreground_work.get(workspace, 1) - 1
                if remaining > 0:
                    dashboard_foreground_work[workspace] = remaining
                else:
                    dashboard_foreground_work.pop(workspace, None)
                dashboard_warmup_condition.notify_all()

    def schedule_dashboard_warmup(
        workspace: str, dashboard_id: str, raw_definition: dict, username: str, *,
        force: bool = False, charts: bool = False,
    ) -> None:
        """Queue a Dashboard's background work without delaying an interactive open.

        Missing standard universes are prepared whenever needed. ``charts``
        also builds its chart models in every comparison mode, and caches its
        columns for the other CDRs, the next time the application is idle.
        """
        key = (workspace, dashboard_id)
        with dashboard_warmup_condition:
            if not force and not charts and key in dashboard_warmup_checked:
                return
            if force:
                dashboard_warmup_checked.discard(key)
            queued = dashboard_warmup_queue.get(key)
            running = dashboard_warmup_running['key'] == key
            if queued is not None and not force:
                queued['charts'] = bool(queued.get('charts') or charts)
                return
            if running and not force:
                if charts:
                    dashboard_chart_requests.add(key)
                return
            dashboard_warmup_queue[key] = {
                'definition': dict(raw_definition), 'username': username,
                'sequence': queued['sequence'] if queued else next(dashboard_warmup_sequence),
                'rank': dashboard_creation_rank(workspace, dashboard_id),
                'universes': True,
                'charts': bool(charts or (queued and queued.get('charts'))),
            }
            state = dashboard_warmup_cancellations.setdefault(key, {
                'requested': False, 'completed': 0, 'total': 0, 'active': False,
            })
            if running:
                # Restart with the changed definition after the current universe.
                state['requested'] = True
            ensure_warmup_worker()
            dashboard_warmup_condition.notify_all()

    def ensure_warmup_worker() -> None:
        thread = dashboard_warmup_running.get('thread')
        if isinstance(thread, Thread) and thread.is_alive():
            return
        thread = Thread(target=warmup_worker, name='dashboard-cache-warmup', daemon=True)
        dashboard_warmup_running['thread'] = thread
        thread.start()

    def next_warmup_item():
        """Return the next runnable warm-up, waiting while none is runnable."""
        with dashboard_warmup_condition:
            while not core.APP_SHUTTING_DOWN.is_set():
                # Chart models wait for an idle application and for their workspace to be open (they are
                # interrupted in any other); universes do not.
                open_workspace = str(Path(core.repository.db_path).resolve()) if core.active_workspace else ''
                runnable = [
                    (warmup_priority(key, entry), key) for key, entry in dashboard_warmup_queue.items()
                    if not dashboard_foreground_work.get(key[0])
                    and (entry.get('universes', True) or (key[0] == open_workspace and not application_in_use()))
                ]
                if runnable:
                    _priority, key = min(runnable)
                    entry = dashboard_warmup_queue.pop(key)
                    state = dashboard_warmup_cancellations.setdefault(key, {
                        'requested': False, 'completed': 0, 'total': 0, 'active': False,
                    })
                    state.update(requested=False, active=True)
                    dashboard_warmup_running['key'] = key
                    return key, entry, state
                dashboard_warmup_condition.wait(timeout=1.0)
        return None

    def warmup_worker() -> None:
        while not core.APP_SHUTTING_DOWN.is_set():
            item = next_warmup_item()
            if item is None:
                return
            key, entry, state = item
            finished = False
            charts_pending = bool(entry.get('charts'))
            try:
                finished = run_dashboard_warmup(key, entry, state) if entry.get('universes', True) else True
                with lock:
                    charts_pending = charts_pending or key in dashboard_chart_requests
                    dashboard_chart_requests.discard(key)
                if finished and charts_pending and not application_in_use():
                    dashboard_warmup_running['phase'] = 'charts'
                    try:
                        charts_pending = not run_dashboard_charts(key, entry)
                    finally:
                        dashboard_warmup_running['phase'] = ''
            except Exception as exc:
                # Automatic cache work must never make saving or listing a
                # Dashboard fail, but its failure is still auditable.
                finished = True
                charts_pending = False
                try:
                    Repository(Path(key[0]), core.repository.global_db_path).add_log(
                        str(entry.get('username') or 'system'), 'prewarm_dashboard_cache_failed',
                        json.dumps({'dashboard_id': key[1], 'error': str(exc)}),
                    )
                except Exception:
                    pass
            finally:
                with dashboard_warmup_condition:
                    dashboard_warmup_running['key'] = None
                    state['active'] = False
                    if key in dashboard_warmup_queue:
                        # A newer definition was scheduled while this ran.
                        queued = dashboard_warmup_queue[key]
                        queued['charts'] = bool(queued.get('charts') or charts_pending)
                    elif finished:
                        dashboard_warmup_checked.add(key)
                        dashboard_warmup_cancellations.pop(key, None)
                        if charts_pending:
                            # Resume the chart models during the next idle period.
                            dashboard_warmup_queue[key] = {**entry, 'universes': False, 'charts': True}
                    else:
                        # Paused for more important work: resume later from the
                        # first universe that still lacks a persisted cache.
                        dashboard_warmup_queue[key] = {**entry, 'charts': charts_pending}
                    dashboard_warmup_condition.notify_all()

    def warmup_universe_identity(definition) -> str:
        return json.dumps(preview_cache_identity(definition), sort_keys=True, default=str)

    def run_dashboard_warmup(key, entry, state) -> bool:
        """Pre-cache every standard universe; return False when it must resume later."""
        workspace, dashboard_id = key
        username = str(entry.get('username') or 'system')

        def must_yield() -> bool:
            with lock:
                return warmup_should_yield(key)

        task_repository = Repository(Path(workspace), core.repository.global_db_path)
        definitions = dashboard_warmup_definitions(dict(entry['definition']), task_repository)
        state['total'] = len(definitions)
        warmed = 0
        for index, definition in enumerate(definitions, start=1):
            if must_yield():
                return False
            if restore_matching_preview_manifest(workspace, dashboard_id, definition, materialize=False) is not None:
                state['completed'] = index
                continue
            # Share the heavy-work gate with foreground preparations and
            # exports, but never wait on it while they have priority.
            while not dashboard_work_gate.acquire(timeout=0.2):
                if must_yield():
                    return False
            try:
                if must_yield():
                    return False
                preview = build_preview(
                    definition, SimpleNamespace(username=username), workspace=workspace,
                    cancelled=must_yield,
                )
            except HTTPException:
                # The universe is not valid for this Dashboard; do not retry it.
                with lock:
                    dashboard_warmup_unavailable.setdefault(key, set()).add(warmup_universe_identity(definition))
                state['completed'] = index
                continue
            except RuntimeError:
                if must_yield():
                    return False
                raise
            finally:
                dashboard_work_gate.release()
            with lock:
                snapshot = snapshots.get(preview['token'])
            if snapshot is not None:
                persist_preview_manifest(
                    workspace, dashboard_id,
                    dashboard_preview_fingerprint(snapshot.definition.model_dump(mode='json'), task_repository),
                    preview['token'],
                )
                warmed += 1
            state['completed'] = index
        if warmed:
            task_repository.add_log(username, 'prewarm_dashboard_cache', json.dumps({
                'dashboard_id': dashboard_id, 'universes': warmed,
            }))
        return True

    def warm_idle_dashboard_caches() -> None:
        """Queue every Dashboard's background work after a quiet application period."""
        workspace = workspace_key()
        with lock:
            dashboards = read_dashboards(bound_repository())
        for dashboard_id, raw_definition in dashboards.items():
            if isinstance(raw_definition, dict):
                schedule_dashboard_warmup(workspace, dashboard_id, raw_definition, 'system', charts=True)

    def application_in_use() -> bool:
        return core.application_idle_seconds() < core.IDLE_DASHBOARD_WARMUP_SECONDS

    def dashboard_comparison_modes(raw_definition: dict) -> list[tuple[str, str]]:
        """The saved comparison mode first, then Operator and both Vendor Comparisons."""
        saved = (
            'multivendor' if raw_definition.get('scope') == 'multivendor' else 'single',
            'vendor_only' if raw_definition.get('vendor_comparison') == 'vendor_only' else 'operator_vendor',
        )
        return list(dict.fromkeys([
            saved, ('single', saved[1]), ('multivendor', 'vendor_only'), ('multivendor', 'operator_vendor'),
        ]))

    def run_dashboard_charts(key, entry) -> bool:
        """Build a Dashboard's chart models in every comparison mode while the application is idle.

        The default universe is built as Operator Comparison and as Vendor
        Comparison with Vendor and with Operator_Vendor identities. The
        columns its charts read are then cached for every other CDR, so changing
        CDRs, dates, filters or the mode reuses them. Returns False when the
        application is used before the work ends; finished charts are kept.
        """
        workspace, dashboard_id = key
        system_user = SimpleNamespace(username='system', role='super-admin')
        task_repository = Repository(Path(workspace), core.repository.global_db_path)
        raw_definition = dict(entry['definition'])

        def interrupted() -> bool:
            return application_in_use() or workspace != workspace_key() or core.APP_SHUTTING_DOWN.is_set()

        built = []
        for scope, vendor_comparison in dashboard_comparison_modes(raw_definition):
            if interrupted():
                return False
            try:
                definition = DashboardDefinition.model_validate(runtime_dashboard_definition(
                    {**raw_definition, 'scope': scope, 'vendor_comparison': vendor_comparison}, task_repository,
                ))
                payload = restore_matching_preview_manifest(workspace, dashboard_id, definition)
                if payload is None:
                    with dashboard_work_gate:
                        payload = build_preview(definition, system_user, workspace=workspace, cancelled=interrupted)
                    with lock:
                        snapshot = snapshots.get(payload['token'])
                    if snapshot is not None:
                        persist_preview_manifest(
                            workspace, dashboard_id,
                            dashboard_preview_fingerprint(snapshot.definition.model_dump(mode='json'), task_repository),
                            payload['token'],
                        )
                with lock:
                    snapshot = snapshots.get(payload['token'])
                if snapshot is None:
                    continue
                for index, chart_entry in enumerate(snapshot.entries):
                    if not chart_entry.source_kind or canvas_model_path(snapshot, chart_entry).is_file():
                        continue
                    if interrupted():
                        return False
                    chart_model(payload['token'], index, system_user, expected_workspace=workspace)
                built.append(snapshot)
            except (HTTPException, RuntimeError):
                # Unavailable modes (for example without mapped Vendors) and
                # preparations interrupted by a user are skipped.
                if interrupted():
                    return False
        task_repository.add_log('system', 'precompute_dashboard_charts', json.dumps({
            'dashboard_id': dashboard_id, 'modes': len(built),
        }))
        return True

    def warm_idle_dashboard_caches_and_charts() -> None:
        warm_idle_dashboard_caches()

    core.register_idle_dashboard_warmup(warm_idle_dashboard_caches_and_charts)

    def run_direct_preparation(preparation_id, definition, dashboard_id, workspace, user, cancellation):
        """Prepare one requested Dashboard universe and return its preview payload."""
        task_repository = Repository(Path(workspace), core.repository.global_db_path)

        def preparation_cancelled():
            return bool(cancellation['requested'])

        def update_preparation_progress(percent, detail):
            with lock:
                task = direct_preparation_tasks.get(preparation_id)
                if task is not None:
                    task.update(progress=percent, detail=detail)

        with foreground_dashboard_work(workspace):
            gate_acquired = False
            while not gate_acquired:
                if cancellation['requested']:
                    raise RuntimeError('Dashboard preparation cancelled.')
                gate_acquired = dashboard_work_gate.acquire(timeout=0.2)
            try:
                with lock:
                    task = direct_preparation_tasks.get(preparation_id)
                    if task is not None:
                        if cancellation['requested']:
                            raise RuntimeError('Dashboard preparation cancelled.')
                        task.update(
                            status='processing',
                            started_at=datetime.now(timezone.utc).timestamp(),
                            progress=1,
                            detail='Starting the Dashboard preparation worker',
                        )
                preview = build_preview(
                    definition, user, workspace=workspace, cancelled=preparation_cancelled,
                    progress=update_preparation_progress,
                )
            finally:
                dashboard_work_gate.release()
        if dashboard_id:
            update_preparation_progress(94, 'Saving the reusable Dashboard preparation cache')
            with lock:
                prepared_snapshot = snapshots.get(preview['token'])
            if prepared_snapshot is None:
                raise RuntimeError('The prepared Dashboard snapshot has expired.')
            persist_preview_manifest(
                workspace,
                dashboard_id,
                dashboard_preview_fingerprint(
                    prepared_snapshot.definition.model_dump(mode='json'), task_repository,
                ),
                preview['token'],
            )
        update_preparation_progress(100, 'Dashboard dataset and filters are ready')
        return preview

    def remember_preparation_result(preparation_id, workspace, username, result) -> None:
        with lock:
            direct_preparation_results[preparation_id] = {
                **result, 'workspace': workspace, 'owner': username,
            }
            while len(direct_preparation_results) > 256:
                direct_preparation_results.popitem(last=False)

    @app.post('/api/ppt-dashboards/prepare')
    def prepare(
        definition: DashboardDefinition,
        dashboard_id: str | None = None,
        rendering_only: bool = False,
        preparation_id: str | None = None,
        use_scope_universe: bool = False,
        background: bool = False,
        user=Depends(dashboard_user),
    ):
        """Prepare a Dashboard universe.

        With ``background=1`` the request returns immediately (202) and the
        browser polls ``/preparation-progress/{id}``. Long preparations on slow
        servers therefore never exceed reverse-proxy response timeouts.
        """
        definition = (automatic_scope_universe if use_scope_universe else auto_cdr_definition)(definition, bound_repository())
        preparation_id = preparation_id or f'dashboard-preparation:{uuid4().hex}'
        workspace = workspace_key()
        cancellation = {'requested': False}
        with lock:
            # A newer request from the same user supersedes that user's
            # earlier preparation; other users' preparations are unaffected.
            for task_id, task in direct_preparation_tasks.items():
                if task_id == preparation_id or task.get('workspace') != workspace or task.get('owner') != user.username:
                    continue
                existing_cancellation = task.get('cancellation')
                if isinstance(existing_cancellation, dict):
                    existing_cancellation['requested'] = True
            direct_preparation_results.pop(preparation_id, None)
            direct_preparation_tasks[preparation_id] = {
                'id': preparation_id, 'workspace': workspace, 'name': definition.name,
                'dashboard_id': dashboard_id, 'owner': user.username,
                'rendering_only': rendering_only, 'cancellation': cancellation,
                'status': 'queued', 'queued_at': datetime.now(timezone.utc).timestamp(),
                'started_at': None,
                'progress': 0, 'detail': 'Waiting for an available Dashboard preparation slot',
            }

        def execute():
            try:
                return run_direct_preparation(preparation_id, definition, dashboard_id, workspace, user, cancellation)
            except HTTPException:
                raise
            except (ValueError, KeyError) as exc:
                raise HTTPException(400, str(exc)) from exc
            except RuntimeError as exc:
                if cancellation['requested']:
                    raise HTTPException(409, 'Dashboard preparation was interrupted.') from exc
                raise
            finally:
                with lock:
                    direct_preparation_tasks.pop(preparation_id, None)

        if not background:
            return execute()

        def execute_in_background():
            try:
                preview = execute()
                result = {'status': 'completed', 'token': str(preview['token'])}
            except HTTPException as exc:
                result = {'status': 'failed', 'code': exc.status_code, 'detail': str(exc.detail)}
            except Exception as exc:
                result = {'status': 'failed', 'code': 500, 'detail': f'Dashboard preparation failed: {exc}'}
            remember_preparation_result(preparation_id, workspace, user.username, result)

        Thread(target=execute_in_background, name='dashboard-preparation', daemon=True).start()
        return JSONResponse({'preparation_id': preparation_id, 'status': 'queued'}, status_code=202)

    @app.post('/api/ppt-dashboards/filter-options')
    def filter_options(request: DashboardFilterOptionsRequest, user=Depends(dashboard_user)):
        try:
            task_repository = bound_repository()
            definition = auto_cdr_definition(request.definition, task_repository)
            values = load_filter_options(definition, request.field, task_repository)
            if request.field.strip() in CASCADING_FILTER_FIELDS:
                values = cascading_dashboard_options({request.field.strip(): values}, definition, task_repository)[request.field.strip()]
            return {'field': request.field.strip(), 'values': values}
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/ppt-dashboards/filter-options/batch')
    def filter_options_batch(request: DashboardFilterOptionsBatchRequest, user=Depends(dashboard_user)):
        """Return the values the selected CDRs offer for several filters in one request."""
        try:
            task_repository = bound_repository()
            definition = auto_cdr_definition(request.definition, task_repository)
            options = load_filter_options_batch(definition, request.fields, task_repository)
            return {'options': cascading_dashboard_options(options, definition, task_repository)}
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/ppt-dashboards/auto-cdrs')
    def dashboard_auto_cdrs(definition: DashboardDefinition, user=Depends(dashboard_user)):
        """The CDRs a Dashboard selection uses now and the lists of its Campaign, Operator, Vendor, Region, Cluster and City.

        Chosen from its NR Mode and Campaign and read from the CDR Filter Facets, without preparing the Dashboard
        or reading CDR rows, so the CDRs and these filters follow every change before it is applied.
        """
        try:
            task_repository = bound_repository()
            resolved = auto_cdr_definition(definition, task_repository)
            options = cascading_dashboard_options({field: [] for field in CASCADING_FILTER_FIELDS}, resolved, task_repository)
            return {'options': options, 'cdrs': describe_cdrs(task_repository, resolved.datasets)}
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post('/api/ppt-dashboards/geography-options')
    def geography_options(definition: DashboardDefinition, user=Depends(dashboard_user)):
        try:
            task_repository = bound_repository()
            # The values of the CDRs of the chosen campaigns (the campaigns and those CDRs come from /auto-cdrs).
            return load_dashboard_geography_options(auto_cdr_definition(definition, task_repository), task_repository)
        except (ValueError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get('/api/ppt-dashboards/prepared/{token}')
    def prepared_preview(token: str, user=Depends(dashboard_user)):
        with lock:
            snapshot = snapshots.get(token)
            if snapshot is None or snapshot.workspace != workspace_key() or snapshot.owner not in {user.username, '*'}:
                raise HTTPException(410, 'Dashboard preview expired. Refresh the Dashboard.')
            return {**snapshot.payload, 'token': token}

    @app.get('/api/ppt-dashboards/preparation-progress/{preparation_id}')
    def preparation_progress(preparation_id: str, user=Depends(dashboard_user)):
        workspace = workspace_key()
        with lock:
            task = direct_preparation_tasks.get(preparation_id)
            if task is None:
                result = direct_preparation_results.get(preparation_id)
                if result is not None and result.get('workspace') == workspace and result.get('owner') == user.username:
                    # A finished background preparation reports its outcome;
                    # the browser loads a completed preview with /prepared.
                    return {
                        key: value for key, value in result.items() if key not in {'workspace', 'owner'}
                    } | {'progress': 100 if result.get('status') == 'completed' else 0}
            if task is None or task.get('workspace') != workspace:
                raise HTTPException(404, 'Dashboard preparation is no longer active.')
            return {
                'progress': task.get('progress', 0),
                'detail': task.get('detail') or 'Preparing Dashboard dataset',
                'status': task.get('status', 'processing'),
            }

    def prefetched_dashboard_response(dashboard_id: str, definition: DashboardDefinition, user):
        workspace = workspace_key()
        restored = restore_matching_preview_manifest(workspace, dashboard_id, definition)
        if restored is not None:
            return restored
        raise HTTPException(409, 'Dashboard preparation is required.')

    @app.get('/api/ppt-dashboards/prefetched/{dashboard_id}')
    def prefetched_dashboard(dashboard_id: str, user=Depends(dashboard_user)):
        task_repository = bound_repository()
        with lock:
            raw_definition = read_dashboards(task_repository).get(dashboard_id)
            if not isinstance(raw_definition, dict):
                raise HTTPException(404, 'Dashboard not found.')
            definition = DashboardDefinition.model_validate(runtime_dashboard_definition(raw_definition, task_repository))
        return prefetched_dashboard_response(dashboard_id, definition, user)

    @app.post('/api/ppt-dashboards/prefetched/{dashboard_id}')
    def prefetched_dashboard_for_definition(
        dashboard_id: str,
        definition: DashboardDefinition,
        use_scope_universe: bool = False,
        user=Depends(dashboard_user),
    ):
        task_repository = bound_repository()
        with lock:
            if dashboard_id not in read_dashboards(task_repository):
                raise HTTPException(404, 'Dashboard not found.')
        definition = (automatic_scope_universe if use_scope_universe else auto_cdr_definition)(definition, task_repository)
        return prefetched_dashboard_response(dashboard_id, definition, user)

    def reporting_source(snapshot, kind, task_repository):
        """Return the shared combined CDR table used directly by Dashboard queries."""
        selected = dashboard_datasets(snapshot.definition, kind, task_repository)
        if not selected:
            raise HTTPException(400, 'Unavailable source type: select a matching CDR dataset.')
        if kind == 'all':
            table, columns = rf_union_source(task_repository, [source for source in KINDS if dashboard_datasets(snapshot.definition, source, task_repository)])
            return Path(snapshot.workspace), table, columns
        columns = task_repository.list_reporting_row_columns(kind)
        if not columns:
            raise ValueError(f'The selected {kind.title()} CDRs have no materialised reporting columns.')
        return Path(snapshot.workspace), task_repository.reporting_rows_table_name(kind), columns

    def chart_query_columns(entry, multivendor):
        reported = core.reporting_query_columns(entry.source_kind, [entry], multivendor)
        explicit = set(catalog_kpi_fields(entry.kpi))
        explicit.update(field for field in entry_dynamic_fields(entry) if field)
        explicit.update(_legend_dimensions(entry.legend))
        explicit.update(parse_catalog_grouping(entry.rows_split).dimensions)
        explicit.update(parse_catalog_grouping(entry.columns_split).dimensions)
        explicit.update(condition.column for condition in parse_catalog_filters(entry.filters))
        for dimension in entry.calculated_dimensions:
            explicit.update(dimension.default_from)
            for rule in dimension.rules:
                for condition in rule.conditions:
                    explicit.update(split_calculated_dimension_aliases(condition.column))
        selected = list(reported)
        selected.extend(('dataset_id', 'source_row_id', 'Vendor'))
        # RF companions use the same source selection. A stable projection of
        # all radio fields lets RSRP/SINR and LTE/NR share the raw-frame cache,
        # rather than rereading millions of observations for each measure.
        radio_columns = (set(RF_CATALOG_FIELDS) if entry.source_kind == 'all'
                         else rf_source_columns(entry.source_kind))
        radio_identities = {identity(column) for column in radio_columns}
        if any(identity(column) in radio_identities for column in catalog_kpi_fields(entry.kpi)):
            selected.extend(radio_columns)
            return sorted(set(selected), key=lambda column: (identity(column), column))
        return list(dict.fromkeys(selected))

    def chart_filter_sql(entry, columns, multivendor, task_repository):
        """Push safe physical template filters into SQLite before DataFrame creation."""
        clauses = []
        parameters = []
        complete = True
        quote = lambda value: '"' + str(value).replace('"', '""') + '"'
        for condition in parse_catalog_filters(entry.filters):
            normalized = identity(condition.column)
            if normalized in {'threshold', 'buckets', 'binsize', 'classcolours', 'histogramoperator'}:
                continue
            if multivendor and normalized in {'operator', 'operatorvendor', 'vendorv3'}:
                complete = False
                continue
            column = next((
                resolve_sql_column(columns, candidate.strip())
                for candidate in split_calculated_dimension_aliases(condition.column)
                if resolve_sql_column(columns, candidate.strip())
            ), None)
            if not column:
                complete = False
                continue
            values = [str(value) for value in condition.values]
            if normalized == 'vendor':
                mappings = task_repository.list_operator_mappings()
                values = vendor_filter_values(values, mappings)
            if normalized == 'operator':
                workspace_mappings = task_repository.list_operator_mappings()
                canonical_values = {
                    workspace_mappings.get(value.strip().casefold(), value.strip()).casefold()
                    for value in values
                }
                values = list(dict.fromkeys([
                    *values,
                    *(
                        source for source, canonical in workspace_mappings.items()
                        if canonical.casefold() in canonical_values
                    ),
                    *(
                        canonical for canonical in workspace_mappings.values()
                        if canonical.casefold() in canonical_values
                    ),
                ]))
            selected = (
                f"COALESCE(CAST({quote(column)} AS TEXT), '') COLLATE NOCASE"
                if '' in values
                else f'{quote(column)} COLLATE NOCASE'
            )
            if normalized in {'operatorvendor', 'vendorv3'} and condition.operator not in {'CONTAINS', 'NOT CONTAINS'}:
                complete = False
                continue
            if condition.operator in {'=', '!='} and len(values) > 1:
                placeholders = ', '.join('?' for _value in values)
                expression = f'{selected} IN ({placeholders})'
                clauses.append(f'NOT ({expression})' if condition.operator == '!=' else expression)
                parameters.extend(values)
            elif condition.operator in {'=', '!='}:
                clauses.append(f'{selected} {condition.operator} ?')
                parameters.append(values[0])
            elif condition.operator in {'IN', 'NOT IN'}:
                placeholders = ', '.join('?' for _value in values)
                expression = f'{selected} IN ({placeholders})'
                clauses.append(f'NOT ({expression})' if condition.operator == 'NOT IN' else expression)
                parameters.extend(values)
            elif condition.operator in {'CONTAINS', 'NOT CONTAINS'}:
                checks = [f'instr(LOWER(COALESCE(CAST({quote(column)} AS TEXT), \'\')), LOWER(?)) > 0' for _value in values]
                expression = f'({" OR ".join(checks)})'
                clauses.append(f'NOT {expression}' if condition.operator == 'NOT CONTAINS' else expression)
                parameters.extend(values)
            else:
                complete = False
        return ' AND '.join(clauses), parameters, complete

    def chart_aggregation_columns(entry, columns, multivendor, filters_applied):
        """Return physical dimensions that SQLite can aggregate without changing chart semantics."""
        if (
            multivendor
            or not filters_applied
            or entry.calculated_dimensions
            or entry.chart_type.casefold() != '100% stacked vertical bars'
        ):
            return None
        requested = [
            *parse_catalog_grouping(entry.rows_split).dimensions,
            *parse_catalog_grouping(entry.columns_split).dimensions,
            *catalog_kpi_fields(entry.kpi),
        ]
        resolved = [resolve_sql_column(columns, name) for name in requested]
        if any(column is None for column in resolved):
            return None
        return list(dict.fromkeys(resolved))

    def reporting_read_connection(database_path):
        """Read connection with a larger page cache and memory-mapped I/O."""
        connection = sqlite3.connect(database_path, timeout=120.0)
        connection.execute(f'PRAGMA cache_size=-{DASHBOARD_READ_CACHE_KIB}')
        connection.execute(f'PRAGMA mmap_size={DASHBOARD_READ_MMAP_BYTES}')
        return connection

    def selection_share(database_path, table, where, parameters) -> float:
        """Share of a table's rows matched by the dataset part of a selection."""
        connection = sqlite3.connect(database_path, timeout=120.0)
        try:
            dataset_clause = re.match(r'\s*\(?(dataset_id IN \([?, ]+\))', where)
            if not dataset_clause:
                return 0.0
            count = dataset_clause.group(1).count('?')
            selected = connection.execute(
                f'SELECT count(*) FROM "{table}" WHERE {dataset_clause.group(1)}', list(parameters)[:count],
            ).fetchone()[0]
            total = connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            return selected / total if total else 0.0
        except sqlite3.Error:
            return 0.0
        finally:
            connection.close()

    def sequential_scan_source(database_path, branch, where, parameters):
        match = re.search(r'FROM "(reporting_rows_[a-z]+)"$', branch)
        if match and selection_share(database_path, match.group(1), where, parameters) >= DASHBOARD_SEQUENTIAL_SCAN_SHARE:
            return branch + ' NOT INDEXED'
        return branch

    def sequential_scan_table(database_path, table_name, where, parameters):
        if selection_share(database_path, table_name, where, parameters) >= DASHBOARD_SEQUENTIAL_SCAN_SHARE:
            return '"' + str(table_name).replace('"', '""') + '" NOT INDEXED'
        return table_name

    def read_cached_frame(cache_path):
        if cache_path is None or not cache_path.is_file():
            return None
        try:
            frame = pd.read_pickle(cache_path)
            cache_path.touch()
            return frame
        except Exception:
            cache_path.unlink(missing_ok=True)
            return None

    def write_cached_frame(cache_path, frame):
        """Persist a source read atomically and keep the newest files only."""
        if cache_path is None or frame.size > DASHBOARD_FRAME_DISK_MAX_CELLS:
            return
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(f'.{uuid4().hex}.tmp')
            frame.to_pickle(temporary)
            temporary.replace(cache_path)
            cached = sorted(cache_path.parent.glob('*.pkl'), key=lambda path: path.stat().st_mtime, reverse=True)
            for stale in cached[DASHBOARD_FRAME_DISK_LIMIT:]:
                stale.unlink(missing_ok=True)
        except OSError:
            pass

    def compact_chart_columns(entry, source_columns, multivendor):
        """Return the only physical columns a chart reads, or None when unknown.

        Charts referencing calculated or semantic fields keep the complete read.
        Order-independent chart types read these columns grouped; the others
        read them ungrouped, in the same row order as the complete read.
        Vendor Comparisons also read the Operator and Vendor identities their
        comparison groups are built from.
        """
        by_identity = defaultdict(list)
        for column in source_columns:
            by_identity[identity(column)].append(column)
        calculated = {identity(dimension.name) for dimension in entry.calculated_dimensions}
        referenced = [
            *catalog_kpi_fields(entry.kpi),
            *(field for field in entry_dynamic_fields(entry) if field),
            *_legend_dimensions(entry.legend),
            *parse_catalog_grouping(entry.rows_split).dimensions,
            *parse_catalog_grouping(entry.columns_split).dimensions,
            *(condition.column for condition in parse_catalog_filters(entry.filters)
              if identity(condition.column) not in CHART_SETTING_FILTERS),
        ]
        selected = []
        for name in referenced:
            key = identity(name)
            if key in calculated:
                return None
            if key in by_identity:
                selected.extend(by_identity[key])
            elif key not in COMPACT_READ_DERIVED_FIELDS:
                return None
        if multivendor or any(identity(name) in COMPACT_READ_VENDOR_FIELDS for name in referenced):
            for key in COMPACT_READ_VENDOR_FIELDS:
                selected.extend(by_identity.get(key, []))
        if multivendor:
            for key in ('operator', 'subscriber'):
                selected.extend(by_identity.get(key, []))
        for name in COMPACT_READ_IMPLICIT_FIELDS:
            selected.extend(by_identity.get(identity(name), []))
        return sorted(set(selected), key=lambda column: (identity(column), column))

    def load_reporting_frame(
        database_path, table_name, source_columns, requested_columns, where, parameters,
        aggregation_columns=None, expand_groups=False, cache_path=None,
    ):
        lookup = {identity(column): column for column in source_columns}
        selected_columns = []
        for requested in aggregation_columns or requested_columns:
            actual = lookup.get(identity(requested))
            if actual and actual not in selected_columns:
                selected_columns.append(actual)
        if not selected_columns:
            return pd.DataFrame()
        cached = read_cached_frame(cache_path)
        if cached is not None:
            return expand_grouped_rows(cached) if expand_groups and not aggregation_columns else cached
        quote = lambda column: '"' + str(column).replace('"', '""') + '"'
        select_clause = ", ".join(quote(column) for column in selected_columns)
        if aggregation_columns:
            select_clause += ', COUNT(*) AS "__catalog_weight"'
        elif expand_groups:
            # Identical rows travel once with their count and are expanded
            # below, so the chart receives exactly the same rows.
            select_clause += ', COUNT(*) AS "__catalog_rows"'
        group_by = f' GROUP BY {", ".join(quote(column) for column in selected_columns)}' if aggregation_columns or expand_groups else ''
        branches = getattr(table_name, 'branches', ())
        if expand_groups and not aggregation_columns:
            # Grouped reads do not depend on row order: when the selection
            # covers much of a table, a sequential scan avoids random row lookups.
            branches = tuple(sequential_scan_source(database_path, branch, where, parameters) for branch in branches) if branches else ()
            if not branches and not table_name.startswith('('):
                table_name = sequential_scan_table(database_path, table_name, where, parameters)
        if branches:
            # Filter each CDR type separately: SQLite flattens each simple
            # subquery, uses the dataset index and computes only the needed columns.
            query = ' UNION ALL '.join(f'SELECT {select_clause} FROM ({branch}) WHERE {where}{group_by}' for branch in branches)
            parameters = list(parameters) * len(branches)
            if aggregation_columns:
                columns_text = ", ".join(quote(column) for column in selected_columns)
                query = (f'SELECT {columns_text}, SUM("__catalog_weight") AS "__catalog_weight" '
                         f'FROM ({query}) GROUP BY {columns_text}')
        else:
            source = table_name if table_name.startswith('(') or table_name.endswith(' NOT INDEXED') else quote(table_name)
            query = f'SELECT {select_clause} FROM {source} WHERE {where}{group_by}'
        connection = reporting_read_connection(database_path)
        try:
            frame = pd.read_sql_query(query, connection, params=parameters)
        finally:
            connection.close()
        write_cached_frame(cache_path, frame)
        return expand_grouped_rows(frame) if expand_groups and not aggregation_columns else frame

    def expand_grouped_rows(frame):
        """Repeat each grouped row by its count, restoring every source row."""
        frame = frame.copy()
        counts = frame.pop('__catalog_rows').to_numpy()
        return frame.loc[frame.index.repeat(counts)].reset_index(drop=True)

    column_caches: dict[str, ColumnCache] = {}
    column_cache_prefetch: OrderedDict = OrderedDict()

    def workspace_column_cache(workspace) -> ColumnCache:
        """The active workspace's per-CDR column cache; other workspaces release theirs."""
        key = str(Path(workspace).resolve())
        with lock:
            cache = column_caches.get(key)
            if cache is None:
                for other in list(column_caches):
                    column_caches.pop(other).forget()
                # In memory only: the columns of the CDRs come from their columnar copies (see build_from_copies).
                cache = column_caches[key] = ColumnCache(
                    column_cache_dir(workspace), memory_bytes=default_memory_bytes(), disk_bytes=0, persist=False,
                )
            return cache

    def forget_column_caches() -> None:
        with lock:
            for cache in column_caches.values():
                cache.forget()

    def plain_reporting_query(table_name, selected_columns, where, parameters):
        """The ungrouped query ``load_reporting_frame`` runs for these columns."""
        quote = lambda column: '"' + str(column).replace('"', '""') + '"'
        select_clause = ", ".join(quote(column) for column in selected_columns)
        branches = getattr(table_name, 'branches', ())
        if branches:
            query = ' UNION ALL '.join(f'SELECT {select_clause} FROM ({branch}) WHERE {where}' for branch in branches)
            return query, list(parameters) * len(branches)
        source = table_name if table_name.startswith('(') else quote(table_name)
        return f'SELECT {select_clause} FROM {source} WHERE {where}', list(parameters)

    planned_row_orders: OrderedDict = OrderedDict()

    def planned_row_order(database_path, query, parameters):
        """The row order of SQLite's plan for a query, when the column cache reproduces it.

        Searching a per-dataset index visits the CDRs in ascending order and,
        within each, the event date (date index) and table order; a full scan
        returns table order. Charts whose rows follow any other plan keep
        reading from SQLite, so their row order never changes.
        """
        key = (str(database_path), query, tuple(parameters))
        with lock:
            if key in planned_row_orders:
                planned_row_orders.move_to_end(key)
                return planned_row_orders[key]
        order = sqlite_plan_row_order(database_path, query, parameters)
        with lock:
            planned_row_orders[key] = order
            while len(planned_row_orders) > 512:
                planned_row_orders.popitem(last=False)
        return order

    def sqlite_plan_row_order(database_path, query, parameters):
        connection = reporting_read_connection(database_path)
        try:
            plan = [str(row[3]) for row in connection.execute(f'EXPLAIN QUERY PLAN {query}', parameters).fetchall()]
        except sqlite3.Error:
            return None
        finally:
            connection.close()
        modes = set()
        for detail in plan:
            if detail in {'COMPOUND QUERY', 'LEFT-MOST SUBQUERY', 'UNION ALL'}:
                continue
            match = re.fullmatch(r'SEARCH (reporting_rows_[a-z]+) USING INDEX (\S+) \(dataset_id=\?(?: AND .*)?\)', detail)
            if match and match.group(2) == f'idx_{match.group(1)}_dataset_event_time_date':
                modes.add('dataset_date_rowid')
            elif match and match.group(2) == f'idx_{match.group(1)}_dataset_id_rows':
                modes.add('dataset_rowid')
            elif re.fullmatch(r'SCAN reporting_rows_[a-z]+', detail):
                modes.add('rowid')
            else:
                return None
        return modes.pop() if len(modes) == 1 else None

    def cache_prefetch_expressions(task_repository, columns, definition):
        """Filter expressions cached with every CDR, so later filter changes skip SQLite."""
        fields = tuple(dict.fromkeys((*ADAPTATIVE_FILTER_FIELDS, 'Vendor', *definition.custom_fields)))
        key = (tuple(columns), fields)
        with lock:
            cached = column_cache_prefetch.get(key)
            if cached is not None:
                column_cache_prefetch.move_to_end(key)
                return cached
        expressions = [filter_sql_normalized_expression(task_repository, columns, field) for field in fields]
        expressions.append(selection_date_expression(task_repository, columns))
        sheet_term = selection_sheet_term(task_repository, columns)
        if sheet_term:
            expressions.append(f'LOWER(TRIM(CAST({sheet_term[0]} AS TEXT)))')
        result = tuple(dict.fromkeys(expression for expression in expressions if expression))
        with lock:
            column_cache_prefetch[key] = result
            while len(column_cache_prefetch) > 64:
                column_cache_prefetch.popitem(last=False)
        return result

    def column_cache_sources(task_repository, kind, table_name, definition, rows_by_kind=None):
        """Return (source, selected CDR rows) for each combined table behind a chart source."""
        projections = getattr(table_name, 'branch_projections', ())
        sources = projections or ((kind, str(table_name), ()),)
        result = []
        for source_kind, table, projection in sources:
            physical = task_repository.list_reporting_row_columns(source_kind)
            source = CacheSource(
                source_kind, table, tuple(projection),
                has_event_time=any(str(column).casefold() == 'event_start_time' for column in physical),
            )
            rows = rows_by_kind.get(source_kind, []) if rows_by_kind is not None else dashboard_datasets(definition, source_kind, task_repository)
            result.append((source, rows))
        return result

    def column_cache_segments(task_repository, kind, table_name, definition, rows_by_kind=None):
        """Cache segments of the selected CDRs, keyed by their data revision."""
        dimensions = sha256(json.dumps(
            task_repository.list_calculated_dimensions(), sort_keys=True, default=str,
        ).encode()).hexdigest()
        segments = []
        for source, rows in column_cache_sources(task_repository, kind, table_name, definition, rows_by_kind):
            # Same revision contract as every Dashboard cache: the CDR version,
            # its combined table's row and column revisions and the calculated
            # dimensions, so a cached column is never stale.
            revision = [
                task_repository.get_workspace_state(f'combined_reporting_updated_{source.kind}'),
                task_repository.get_workspace_state(f'combined_reporting_columns_updated_{source.kind}'),
                dimensions,
            ]
            for row in sorted(rows, key=lambda item: int(item['id'])):
                version = json.dumps([
                    row.get('updated_at'), row.get('processed_at'), row.get('normalization_version'),
                    row.get('row_count'), *revision,
                ], default=str)
                segments.append(Segment(source, int(row['id']), version))
        return segments

    def cached_selection_counts(task_repository, kind, selected, definition, columns):
        """Universe and filtered row counts of one CDR type, from the column cache.

        They equal the SQLite counts: the universe is the selected CDRs within
        the dates and sheets, and the filtered rows also match every filter.
        """
        if not DASHBOARD_COLUMN_CACHE or not selected:
            return None
        universe_definition = definition.model_copy(deep=True)
        universe_definition.filters = {}
        universe = selection_cache_terms(task_repository, columns, universe_definition)
        selection = selection_cache_terms(task_repository, columns, definition)
        database_path = Path(task_repository.db_path)
        segments = column_cache_segments(
            task_repository, kind, task_repository.reporting_rows_table_name(kind), definition, {kind: selected},
        )
        prefetch = cache_prefetch_expressions(task_repository, columns, definition)
        cache = workspace_column_cache(database_path)
        connect = lambda: reporting_read_connection(database_path)
        builder = copies_builder(task_repository, segments)
        for _attempt in range(2):
            try:
                return count_rows(cache, connect, segments, universe, selection, prefetch=lambda _source: prefetch,
                                  builder=builder)
            except StaleSegment:
                for segment in segments:
                    cache.invalidate(segment)
            except (sqlite3.Error, OSError, ValueError, KeyError):
                return None
        return None

    distinct_value_memo: OrderedDict = OrderedDict()

    def dataset_distinct_values(task_repository, dataset, column):
        """Every distinct value of one CDR column, kept in memory per CDR version.

        The scan of a CDR's own rows only depends on that CDR, so a changed
        Dashboard filter reuses it instead of reading the CDR again.
        """
        version = [dataset.get('id'), dataset.get('updated_at'), dataset.get('processed_at'),
                   dataset.get('normalization_version'), dataset.get('row_count'), column]
        key = (str(task_repository.db_path), sha256(json.dumps(version, default=str).encode()).hexdigest())
        with lock:
            if key in distinct_value_memo:
                distinct_value_memo.move_to_end(key)
                return list(distinct_value_memo[key])
        values = task_repository.list_distinct_dataset_row_values(int(dataset['id']), column, limit=None)
        with lock:
            distinct_value_memo[key] = list(values)
            while len(distinct_value_memo) > 512:
                distinct_value_memo.popitem(last=False)
        return list(values)

    def copies_builder(task_repository, segments):
        """The builder of the columns of ``segments`` from the columnar copies of their CDRs, in memory only, when every
        copy holds its CDR as it is (see build_from_copies); None otherwise."""
        dataset_ids = {segment.dataset_id for segment in segments}
        if not dataset_ids or not dataset_ids <= cdr_store.fresh_copies(task_repository.db_path, dataset_ids):
            return None
        return lambda segment, expressions: build_from_copies(task_repository.db_path, segment, expressions)

    def column_cache_frame(snapshot, kind, task_repository, database_path, table_name, source_columns,
                           requested_columns, terms, order, rows_by_kind=None):
        """Assemble a chart's source rows from the per-CDR column cache."""
        lookup = {identity(column): column for column in source_columns}
        selected_columns = []
        for requested in requested_columns:
            actual = lookup.get(identity(requested))
            if actual and actual not in selected_columns:
                selected_columns.append(actual)
        if not selected_columns:
            return pd.DataFrame()
        quote = task_repository._quote_identifier
        segments = column_cache_segments(task_repository, kind, table_name, snapshot.definition, rows_by_kind)
        prefetch = cache_prefetch_expressions(task_repository, source_columns, snapshot.definition)
        cache = workspace_column_cache(snapshot.workspace)
        connect = lambda: reporting_read_connection(database_path)
        builder = copies_builder(task_repository, segments)
        for _attempt in range(2):
            try:
                return read_frame(
                    cache, connect, segments, [(column, quote(column)) for column in selected_columns],
                    terms, order, prefetch=lambda _source: prefetch, builder=builder,
                )
            except StaleSegment:
                # Rows changed under an unchanged revision: rebuild the CDRs.
                for segment in segments:
                    cache.invalidate(segment)
        raise StaleSegment('The selected CDR rows keep changing.')

    def parse_chart_column_filters(encoded):
        try:
            payload = json.loads(encoded or '{}')
        except (TypeError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(column): [str(value) for value in values]
            for column, values in payload.items()
            if isinstance(values, list)
        }

    def chart_dataset_filter_values(frame):
        return {
            str(column): sorted(
                {'' if pd.isna(value) else str(value) for value in frame[column]},
                key=lambda value: value.casefold(),
            )
            for column in frame.columns
        }

    def chart_dataset_column_classes(snapshot, entry, columns):
        task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
        datasets = []
        for dataset_id in [row['id'] for row in dashboard_datasets(snapshot.definition, entry.source_kind, task_repository)]:
            dataset = task_repository.get_dataset(int(dataset_id))
            if dataset:
                datasets.append(core.serialize_dataset_row(dataset))
        return core._chart_preview_column_classes(columns, datasets, task_repository)

    def chart_dataset_column_metadata(snapshot, entry, columns):
        task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
        datasets = []
        for dataset_id in [row['id'] for row in dashboard_datasets(snapshot.definition, entry.source_kind, task_repository)]:
            dataset = task_repository.get_dataset(int(dataset_id))
            if dataset:
                datasets.append(core.serialize_dataset_row(dataset))
        return core._chart_preview_column_metadata(
            columns, datasets, entry.source_kind, task_repository,
        )

    def apply_chart_column_filters(frame, column_filters):
        result = frame
        lookup = {identity(column): column for column in frame.columns}
        for requested, values in column_filters.items():
            column = lookup.get(identity(vendor_filter_column(requested)))
            if column is None or not values:
                return result.iloc[0:0]
            if identity(vendor_filter_column(requested)) in {'vendor', 'operatorvendor'}:
                values = vendor_match_values(requested, values, frame.attrs.get('operator_mappings', {}))
            accepted = {str(value).strip().casefold() for value in values}
            result = result.loc[
                result[column].map(
                    lambda value: '' if pd.isna(value) else str(value).strip().casefold()
                ).isin(accepted)
            ]
        return result

    def chart_row_universe(snapshot, entry, selected=None):
        """Return the strongest known upper bound for one chart's source rows."""
        if selected is None:
            task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
            selected = dashboard_datasets(snapshot.definition, entry.source_kind, task_repository)
        limits = []
        source_total = sum(int(row.get('row_count') or 0) for row in selected)
        if source_total:
            limits.append(source_total)
        filtered_rows = (snapshot.payload.get('rows') or {}).get(entry.source_kind)
        if filtered_rows is not None:
            limits.append(max(0, int(filtered_rows)))
        return min(limits) if limits else 0

    def reporting_chart_data_page(
        snapshot, entry, page, column_filters=None, include_filter_values=False, filter_column='',
    ):
        """Read one exact chart-data page without rebuilding its full DataFrame."""
        spec = _catalog_spec(entry)
        if entry.source_kind == 'all' or spec.get('operators'):
            return None
        # This SQL-only pagination path reads physical CDR values. Chart frames
        # intentionally replace Operator aliases (and their derived Subscriber
        # and Vendor presentation labels) in memory, so using the SQL values
        # for the dropdown would make a visible canonical value impossible to
        # select. Use the shared mapped frame whenever such a column is shown.
        if any(
            identity(column) in {'operator', 'subscriber', 'vendor', 'vendoronly', 'operatorvendor'}
            for column in chart_query_columns(entry, snapshot.multivendor)
        ):
            return None
        task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
        selected = dashboard_datasets(snapshot.definition, entry.source_kind, task_repository)
        database_path, table_name, source_columns = reporting_source(
            snapshot, entry.source_kind, task_repository,
        )
        where, parameters = selection_where(
            task_repository, entry.source_kind, [int(row['id']) for row in selected], snapshot.definition,
            columns=source_columns,
        )
        source_filters = (
            (spec.get('sessions'), ('Session_Type', 'session_type', 'Test_Name', 'Test_Type')),
            (spec.get('tests'), ('Test_Name', 'test_name', 'Type_of_Test', 'Test_Type')),
            (spec.get('directions'), ('Direction', 'direction', 'Call_Direction')),
            ((spec.get('city_scope'),) if spec.get('city_scope') else None, ('city', 'City', 'G_Level_1', 'G_Level_2')),
        )
        for values, candidates in source_filters:
            if not values:
                continue
            column = next((resolve_sql_column(source_columns, name) for name in candidates if resolve_sql_column(source_columns, name)), None)
            if not column:
                continue
            expression = ' OR '.join(
                f'LOWER(COALESCE(CAST({task_repository._quote_identifier(column)} AS TEXT), \'\')) LIKE ?'
                for _value in values
            )
            where = f'({where}) AND ({expression})'
            parameters.extend(f'%{str(value).casefold()}%' for value in values)
        template_where, template_parameters, filters_applied = chart_filter_sql(
            entry, source_columns, snapshot.multivendor, task_repository,
        )
        if not filters_applied:
            return None
        if template_where:
            where = f'({where}) AND ({template_where})'
            parameters.extend(template_parameters)
        lookup = {identity(column): column for column in source_columns}
        selected_columns = []
        for requested in chart_query_columns(entry, snapshot.multivendor):
            actual = lookup.get(identity(requested))
            if actual and actual not in selected_columns:
                selected_columns.append(actual)
        dataset_column = lookup.get(identity('dataset_id'))
        source_row_column = lookup.get(identity('source_row_id'))
        if not selected_columns or not dataset_column or not source_row_column:
            return None
        quote = lambda column: '"' + str(column).replace('"', '""') + '"'
        identity_columns = f'{quote(dataset_column)}, {quote(source_row_column)}'
        page = max(0, int(page))
        connection = sqlite3.connect(database_path, timeout=120.0)
        try:
            chart_total = int(connection.execute(
                f'SELECT COUNT(*) FROM ('
                f'SELECT 1 FROM {quote(table_name)} WHERE {where} GROUP BY {identity_columns}'
                f')',
                parameters,
            ).fetchone()[0])
            chart_total = min(chart_total, chart_row_universe(snapshot, entry, selected))
            filter_values = {}
            if include_filter_values:
                values_query = ', '.join(
                    f'json_group_array(DISTINCT COALESCE(CAST({quote(column)} AS TEXT), \'\')) AS filter_{index}'
                    for index, column in enumerate(selected_columns)
                )
                values_row = connection.execute(
                    f'SELECT {values_query} FROM {quote(table_name)} WHERE {where}', parameters,
                ).fetchone()
                filter_values = {
                    column: sorted(
                        (str(value) for value in json.loads(values_row[index] or '[]')),
                        key=lambda value: value.casefold(),
                    )
                    for index, column in enumerate(selected_columns)
                }
            if filter_column:
                requested_filter_column = lookup.get(identity(filter_column))
                if requested_filter_column:
                    values_where = where
                    values_parameters = list(parameters)
                    for requested, values in (column_filters or {}).items():
                        if identity(requested) == identity(filter_column):
                            continue
                        column = lookup.get(identity(requested))
                        if column is None or not values:
                            values_where = f'({values_where}) AND 0'
                            continue
                        placeholders = ', '.join('?' for _value in values)
                        values_where = (
                            f'({values_where}) AND '
                            f'LOWER(TRIM(COALESCE(CAST({quote(column)} AS TEXT), \'\'))) IN ({placeholders})'
                        )
                        values_parameters.extend(str(value).strip().lower() for value in values)
                    filter_values = sorted(
                        (
                            str(row[0]) for row in connection.execute(
                                f'SELECT DISTINCT COALESCE(CAST({quote(requested_filter_column)} AS TEXT), \'\') '
                                f'FROM {quote(table_name)} WHERE {values_where}',
                                values_parameters,
                            )
                        ),
                        key=str.casefold,
                    )
            filtered_where = where
            filtered_parameters = list(parameters)
            for requested, values in (column_filters or {}).items():
                column = lookup.get(identity(requested))
                if column is None or not values:
                    filtered_where = f'({filtered_where}) AND 0'
                    continue
                placeholders = ', '.join('?' for _value in values)
                filtered_where = (
                    f'({filtered_where}) AND '
                    f'LOWER(TRIM(COALESCE(CAST({quote(column)} AS TEXT), \'\'))) IN ({placeholders})'
                )
                filtered_parameters.extend(str(value).strip().lower() for value in values)
            total = chart_total
            if column_filters:
                total = int(connection.execute(
                    f'SELECT COUNT(*) FROM ('
                    f'SELECT 1 FROM {quote(table_name)} WHERE {filtered_where} GROUP BY {identity_columns}'
                    f')',
                    filtered_parameters,
                ).fetchone()[0])
                total = min(total, chart_total)
            page_size = min(100, max(0, total - page * 100))
            query = (
                f'SELECT {", ".join(quote(column) for column in selected_columns)} '
                f'FROM {quote(table_name)} WHERE {filtered_where} GROUP BY {identity_columns} '
                f'ORDER BY {identity_columns} LIMIT ? OFFSET ?'
            )
            visible = pd.read_sql_query(
                query, connection, params=(*filtered_parameters, page_size, page * 100),
            )
        finally:
            connection.close()
        if snapshot.multivendor:
            visible = ensure_vendor_group(visible)
        mapping_settings = task_repository.chart_mapping_settings()
        operator_mappings = mapping_settings['operator_mappings']
        visible = apply_operator_mappings(visible, operator_mappings)
        visible = drop_excluded_operators(visible, excluded_operators(mapping_settings))
        visible.attrs.update(mapping_settings)
        visible = normalise_operator_aliases(visible)
        return visible, total, chart_total, filter_values

    def unique_chart_dataset_rows(snapshot, entry, frame):
        """Keep one preview row per source row and never exceed its filtered CDR universe."""
        lookup = {identity(column): column for column in frame.columns}
        identity_columns = [
            lookup[key] for key in (identity('dataset_id'), identity('source_row_id')) if key in lookup
        ]
        result = frame.drop_duplicates(subset=identity_columns, keep='first') if identity_columns else frame
        universe = chart_row_universe(snapshot, entry)
        return result.iloc[:universe] if len(result) > universe else result

    def release_idle_snapshot_frames() -> None:
        """Bound chart-frame memory to the most recently used snapshots.

        Every snapshot keeps its lightweight payload, but only the latest few
        keep their pandas frames; older ones rebuild them on demand. Without
        this bound, many opened universes could exhaust server memory.
        """
        with lock:
            # Snapshots a user is viewing keep their frames first, so background
            # warm-ups of other Dashboards cannot evict the open Dashboard and
            # force every remaining chart to reread its CDR rows.
            ordered = list(snapshots.values())
            viewed = sorted((item for item in ordered if item.viewed_at), key=lambda item: item.viewed_at)
            unviewed = [item for item in ordered if not item.viewed_at]
            recent = [*viewed[-DASHBOARD_FRAME_CACHE_SNAPSHOTS:], *unviewed[-1:]]
            for snapshot in ordered:
                if any(snapshot is item for item in recent):
                    continue
                if snapshot.frames or snapshot.filtered_frames or snapshot.chart_frames:
                    snapshot.frames.clear()
                    snapshot.filtered_frames.clear()
                    snapshot.chart_frames.clear()
                    snapshot.frame_locks.clear()

    def snapshot_chart(token, index, user, *, include_frame=True, expected_workspace: str | None = None, complete=False):
        """Return a chart's snapshot, entry and prepared rows.

        ``complete`` returns every source column, as the chart dataset views
        need, instead of the compact grouped read used to build chart models.
        """
        frame_key = ('complete', index) if complete else index
        with lock:
            snapshot = snapshots.get(token)
            if snapshot is not None:
                snapshots.move_to_end(token)
        if snapshot is None or snapshot.workspace != (expected_workspace or workspace_key()) or snapshot.owner not in {user.username, '*'}:
            raise HTTPException(410, 'Dashboard preview expired. Refresh the Dashboard.')
        if index < 0 or index >= len(snapshot.entries):
            raise HTTPException(404, 'Chart not found.')
        entry = snapshot.entries[index]
        if not include_frame:
            return snapshot, entry, None
        with lock:
            frame = snapshot.chart_frames.get(frame_key)
        if frame is None:
            task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
            with lock:
                source = snapshot.sources.get(entry.source_kind)
            if source is None:
                rows_by_kind = {
                    kind: dashboard_datasets(snapshot.definition, kind, task_repository)
                    for kind in (KINDS if entry.source_kind == 'all' else (entry.source_kind,))
                }
                source = (rows_by_kind, *reporting_source(snapshot, entry.source_kind, task_repository))
                with lock:
                    snapshot.sources[entry.source_kind] = source
            rows_by_kind, database_path, table_name, source_columns = source
            selected = [row for rows in rows_by_kind.values() for row in rows]
            where, parameters = selection_where(
                task_repository, entry.source_kind, [int(row['id']) for row in selected], snapshot.definition,
                columns=source_columns,
            )
            requested_columns = chart_query_columns(entry, snapshot.multivendor)
            template_where, template_parameters, template_filters_applied = chart_filter_sql(
                entry, source_columns, snapshot.multivendor, task_repository,
            )
            if entry.source_kind == 'all':
                # Every RF chart over the combined CDR types then shares one
                # loaded frame; its own filters are applied in memory below.
                template_where, template_parameters, template_filters_applied = '', [], False
            if template_where:
                where = f'({where}) AND ({template_where})'
                parameters.extend(template_parameters)
            aggregation_columns = chart_aggregation_columns(
                entry, source_columns, snapshot.multivendor, template_filters_applied,
            )
            compact_columns = None if complete or aggregation_columns or not DASHBOARD_COMPACT_READS else compact_chart_columns(
                entry, source_columns, snapshot.multivendor,
            )
            grouped_read = bool(compact_columns) and entry.chart_type.casefold() in COMPACT_READ_CHART_TYPES
            if compact_columns and not grouped_read:
                # Row order matters (for example map point order): keep the
                # complete read's filters and order, only with fewer columns.
                requested_columns = compact_columns
            elif compact_columns:
                # Template filters run in memory on the compact rows, so charts
                # reading the same fields share one grouped read.
                where, parameters = selection_where(
                    task_repository, entry.source_kind, [int(row['id']) for row in selected], snapshot.definition,
                    columns=source_columns,
                )
                template_filters_applied = False
                requested_columns = compact_columns
            # Key on the physical columns actually read: requested names that do
            # not exist in the source (such as Bin Size) do not change the frame.
            source_lookup = {identity(column): column for column in source_columns}
            read_columns = sorted({
                source_lookup[identity(column)] for column in (aggregation_columns or requested_columns)
                if identity(column) in source_lookup
            })
            # The per-CDR column cache returns the rows SQLite would return for
            # any universe or comparison mode. Order-independent charts take them
            # in table order; the others only when the column cache reproduces
            # SQLite's plan order, so no chart's row order changes.
            cache_order = None
            if DASHBOARD_COLUMN_CACHE and not aggregation_columns:
                ordered_columns = list(dict.fromkeys(
                    source_lookup[identity(column)] for column in requested_columns if identity(column) in source_lookup
                ))
                if ordered_columns:
                    # A chart and its data table view then share one frame.
                    cache_order = planned_row_order(
                        database_path, *plain_reporting_query(table_name, ordered_columns, where, parameters),
                    )
                if cache_order is None and not complete and entry.chart_type.casefold() in COMPACT_READ_CHART_TYPES:
                    cache_order = 'dataset_rowid'
            cache_terms = None
            if cache_order:
                # Template filters then run in memory on the cached rows.
                template_filters_applied = False
                cache_terms = selection_cache_terms(task_repository, source_columns, snapshot.definition)
                selection_identity = {
                    'datasets': sorted(int(row['id']) for row in selected),
                    'values': [[expression, sorted(values)] for expression, values in cache_terms.values],
                    'date': cache_terms.date,
                    'sheets': [cache_terms.excluded_sheets[0], sorted(cache_terms.excluded_sheets[1])] if cache_terms.excluded_sheets else None,
                    'excluded': [[expression, sorted(values)] for expression, values in cache_terms.excluded_values],
                    **({'out_of_scope': [[sorted(datasets), expression, sorted(values)]
                                         for datasets, expression, values in cache_terms.dataset_excluded_values]}
                       if cache_terms.dataset_excluded_values else {}),
                    'order': cache_order,
                }
            else:
                selection_identity = {'where': where, 'parameters': parameters}
            raw_key = sha256(json.dumps({
                'kind': entry.source_kind, 'columns': read_columns, **selection_identity,
                'aggregation_columns': aggregation_columns, 'compact': grouped_read and not cache_order,
                'chart_mappings': task_repository.chart_mapping_settings(),
            }, sort_keys=True, default=str).encode()).hexdigest()
            with lock:
                raw_frame = snapshot.frames.get(raw_key)
                frame_lock = snapshot.frame_locks.setdefault(raw_key, RLock())
            if raw_frame is None:
                with frame_lock:
                    with lock:
                        raw_frame = snapshot.frames.get(raw_key)
                    if raw_frame is None:
                        if cache_order:
                            try:
                                raw_frame = column_cache_frame(
                                    snapshot, entry.source_kind, task_repository, database_path, table_name,
                                    source_columns, requested_columns, cache_terms, cache_order, rows_by_kind,
                                )
                            except (sqlite3.Error, StaleSegment, OSError, ValueError, KeyError):
                                # SQLite remains the source of truth; its rows are
                                # filtered again in memory, which changes nothing.
                                raw_frame = load_reporting_frame(
                                    database_path, table_name, source_columns, requested_columns, where, parameters,
                                    aggregation_columns, expand_groups=grouped_read,
                                )
                        else:
                            # The selection key fingerprints the CDR versions and
                            # combined-table revisions, like the chart-model cache.
                            cache_path = frame_cache_dir(snapshot.workspace) / (sha256(
                                f'{DASHBOARD_FRAME_CACHE_VERSION}:{snapshot.selection_key}:{raw_key}'.encode()
                            ).hexdigest() + '.pkl') if snapshot.selection_key else None
                            raw_frame = load_reporting_frame(
                                database_path, table_name, source_columns, requested_columns, where, parameters,
                                aggregation_columns, expand_groups=grouped_read, cache_path=cache_path,
                            )
                        if snapshot.multivendor:
                            raw_frame = ensure_vendor_group(raw_frame)
                        mapping_settings = task_repository.chart_mapping_settings()
                        operator_mappings = mapping_settings['operator_mappings']
                        raw_frame = apply_operator_mappings(raw_frame, operator_mappings)
                        # The operators the Operator Maps exclude are left out of every Dashboard.
                        raw_frame = drop_excluded_operators(raw_frame, excluded_operators(mapping_settings))
                        raw_frame.attrs.update(mapping_settings)
                        # NSA & SA: its campaigns that name SA are drawn as SA series (see _sa_series_keys).
                        raw_frame.attrs[BOTH_NR_MODES_ATTR] = dashboard_nr_mode(snapshot.definition) == NSA_VS_SA
                        raw_frame = normalise_operator_aliases(raw_frame)
                        raw_frame.attrs['operator_aliases_normalized'] = True
                        with lock:
                            snapshot.frames[raw_key] = raw_frame
            # A CDF and its companion Average/Median chart normally use the
            # same source, KPI and template filters. Share that expensive
            # filtering pass while keeping each chart's aggregation and visual
            # model independent.
            # Cells of a dynamic grid share one filtered frame; each cell then
            # keeps only its own row/column values, which is a pure row filter.
            dynamic_cell = any(value is not None for value in (entry.dynamic_row_value, entry.dynamic_column_value, entry.dynamic_value))
            base_entry = replace(entry, dynamic_row_value=None, dynamic_column_value=None, dynamic_value=None) if dynamic_cell else entry
            # The filtered rows depend only on what the filtering pipeline reads:
            # source, effective filters (chart-setting pseudo filters such as Bin
            # Size are ignored there), calculated fields, the measured column and
            # the exclusion flags. Chart types sharing them (a CDF and its
            # histogram, classes or thresholds) reuse one filtering pass.
            filter_spec = _catalog_spec(base_entry)
            effective_filters = tuple(
                condition for condition in parse_catalog_filters(base_entry.filters)
                if identity(condition.column) not in CHART_SETTING_FILTERS
            )
            filtered_key = sha256(repr((
                raw_key, entry.cdr_source, effective_filters, filter_spec.get('metric'),
                entry.exclude_null_empty, entry.exclude_zero,
                (filter_spec.get('kind'), filter_spec.get('x_metric'), filter_spec.get('colour_metric'))
                if entry.exclude_null_empty or entry.exclude_zero else None,
                entry.calculated_dimensions, snapshot.multivendor, entry.vendor_comparison, entry_dynamic_fields(entry),
            )).encode()).hexdigest()
            with lock:
                prepared_frame = snapshot.filtered_frames.get(filtered_key)
                filter_lock = snapshot.frame_locks.setdefault(f'filtered:{filtered_key}', RLock())
            if prepared_frame is None:
                with filter_lock:
                    with lock:
                        prepared_frame = snapshot.filtered_frames.get(filtered_key)
                    if prepared_frame is None:
                        try:
                            prepared_frame = prepare_catalog_chart_preview_frame(
                                raw_frame, base_entry, multivendor=snapshot.multivendor,
                                template_filters_applied=template_filters_applied,
                            )[0]
                        except ValueError as exc:
                            raise HTTPException(400, str(exc)) from exc
                        with lock:
                            prepared_frame = snapshot.filtered_frames.setdefault(filtered_key, prepared_frame)
            if dynamic_cell:
                render_entry = prepare_multivendor_catalog_entry(entry) if snapshot.multivendor else entry
                prepared_frame = _select_dynamic_chart_frame(prepared_frame, render_entry)
            with lock:
                frame = snapshot.chart_frames.setdefault(frame_key, prepared_frame)
            release_idle_snapshot_frames()
        return snapshot, entry, frame

    def chart_model(
        token: str,
        index: int,
        user,
        *,
        expected_workspace: str | None = None,
        force: bool = False,
    ):
        snapshot, entry, _ = snapshot_chart(token, index, user, include_frame=False, expected_workspace=expected_workspace)
        model_path = canvas_model_path(snapshot, entry)
        model_dir = model_path.parent
        mapping_key = sha256(json.dumps(
            Repository(Path(snapshot.workspace), core.repository.global_db_path).chart_mapping_settings(),
            sort_keys=True,
        ).encode()).hexdigest()
        if force:
            with lock:
                snapshot.chart_payloads.pop(index, None)
                # The prepared frame carries the mapping aliases, ordering and
                # theme colours that existed when it was first built. Dropping
                # only the Canvas payload would immediately rebuild it from
                # that stale frame after an Admin mapping change.
                snapshot.chart_frames.pop(index, None)
                snapshot.chart_frames.pop(('complete', index), None)
                # Filtered/raw frames are mapping-dependent too, but reloading
                # them re-reads every CDR row of the chart's type. Drop them
                # only when the workspace mappings changed since they were
                # built (or when that is unknown).
                if snapshot.mapping_key != mapping_key:
                    snapshot.frames.clear()
                    snapshot.filtered_frames.clear()
                    snapshot.frame_locks.clear()
            model_path.unlink(missing_ok=True)
        with lock:
            snapshot.mapping_key = snapshot.mapping_key or mapping_key
            if force:
                snapshot.mapping_key = mapping_key
        with lock:
            payload = snapshot.chart_payloads.get(index)
        if payload is None and model_path.is_file():
            try:
                payload = json.loads(model_path.read_text(encoding='utf-8'))
                model_path.touch()
            except (OSError, json.JSONDecodeError):
                model_path.unlink(missing_ok=True)
                payload = None
        if payload is None:
            snapshot, entry, frame = snapshot_chart(token, index, user, expected_workspace=expected_workspace)
            payload = catalog_chart_payload(
                frame, entry, multivendor=snapshot.multivendor, prefiltered=True,
            )
            with lock:
                payload = snapshot.chart_payloads.setdefault(index, payload)
            try:
                if callable(snapshot.cancelled) and snapshot.cancelled():
                    return payload
                model_dir.mkdir(parents=True, exist_ok=True)
                temporary = model_path.with_suffix(f'.{uuid4().hex}.tmp')
                temporary.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
                if callable(snapshot.cancelled) and snapshot.cancelled():
                    temporary.unlink(missing_ok=True)
                    return payload
                temporary.replace(model_path)
                cached_models = sorted(model_dir.glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
                for stale in cached_models[DASHBOARD_CHART_MODEL_DISK_LIMIT:]:
                    stale.unlink(missing_ok=True)
                core.invalidate_workspace_size_cache(Path(snapshot.workspace).parent)
            except OSError:
                pass
        with lock:
            snapshot.chart_payloads.setdefault(index, payload)
        return payload

    def canvas_model_path(snapshot, entry, operator_mapping_key: str | None = None) -> Path:
        """Return the persistent Canvas-model location for one chart entry."""
        entry_key = sha256(repr(entry).encode()).hexdigest()
        if operator_mapping_key is None:
            task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
            operator_mapping_key = sha256(json.dumps(
                task_repository.chart_mapping_settings(), sort_keys=True,
            ).encode()).hexdigest()
        filename = sha256(
            f'{DASHBOARD_CHART_MODEL_CACHE_VERSION}:{snapshot.selection_key}:{snapshot.definition.scope}:'
            f'{entry_key}:{operator_mapping_key}'.encode()
        ).hexdigest()
        return canvas_model_cache_dir(snapshot.workspace) / f'{filename}.json'

    visible_chart_condition = Condition(Lock())
    visible_chart_requests: dict[str, int] = {}

    def chart_model_ready(snapshot, index) -> bool:
        """Whether a chart model can be served without calculating it."""
        with lock:
            if index in snapshot.chart_payloads:
                return True
        try:
            return 0 <= index < len(snapshot.entries) and canvas_model_path(snapshot, snapshot.entries[index]).is_file()
        except (OSError, sqlite3.Error):
            return False

    @contextmanager
    def visible_chart_work(workspace: str):
        with visible_chart_condition:
            visible_chart_requests[workspace] = visible_chart_requests.get(workspace, 0) + 1
        try:
            yield
        finally:
            with visible_chart_condition:
                visible_chart_requests[workspace] = max(0, visible_chart_requests.get(workspace, 1) - 1)
                visible_chart_condition.notify_all()

    def wait_for_visible_charts(workspace: str) -> None:
        """Hold a preload while the charts of the open slide are being calculated."""
        with visible_chart_condition:
            while visible_chart_requests.get(workspace, 0) and not core.APP_SHUTTING_DOWN.is_set():
                visible_chart_condition.wait(timeout=0.5)

    @app.get('/api/ppt-dashboards/chart/{token}/{index}')
    def interactive_chart(token: str, index: int, priority: str = 'high', user=Depends(dashboard_user)):
        with lock:
            snapshot = snapshots.get(token)
            if snapshot is not None:
                snapshot.viewed_at = monotonic()
        workspace = workspace_key()
        preload = priority == 'low'
        if preload and snapshot is not None and not chart_model_ready(snapshot, index):
            # Preloaded neighbours wait for the slide the user is looking at.
            wait_for_visible_charts(workspace)
        # Background warm-ups pause while the open Dashboard builds a chart.
        with foreground_dashboard_work(workspace), (nullcontext() if preload else visible_chart_work(workspace)):
            payload = chart_model(token, index, user)
        # The server already maintains a bounded persistent model cache. A
        # second browser cache can outlive a renderer change or an explicit
        # Dashboard refresh and reintroduce an obsolete ordering/model.
        return JSONResponse(payload, headers={'Cache-Control': 'no-store'})

    @app.post('/api/ppt-dashboards/chart/{token}/{index}/refresh')
    def refresh_interactive_chart(token: str, index: int, user=Depends(dashboard_user)):
        """Invalidate and rebuild only the requested Canvas chart model."""
        payload = chart_model(token, index, user, force=True)
        return JSONResponse(payload, headers={'Cache-Control': 'no-store'})

    @app.post('/api/ppt-dashboards/charts/{token}/refresh')
    def refresh_interactive_charts(token: str, user=Depends(dashboard_user)):
        """Invalidate and rebuild every available Canvas model in a Dashboard snapshot."""
        with lock:
            snapshot = snapshots.get(token)
        workspace = workspace_key()
        if snapshot is None or snapshot.workspace != workspace or snapshot.owner not in {user.username, '*'}:
            raise HTTPException(410, 'Dashboard preview expired. Refresh the Dashboard.')
        indexes = list(dict.fromkeys(
            int(chart['index'])
            for slide in snapshot.payload.get('slides', [])
            for chart in slide.get('charts', [])
            if chart.get('available')
        ))
        with ThreadPoolExecutor(
            max_workers=DASHBOARD_CHART_RENDER_WORKERS,
            thread_name_prefix='ppt-dashboard-refresh',
        ) as chart_executor:
            futures = [
                chart_executor.submit(
                    chart_model, token, index, user, expected_workspace=workspace, force=True,
                )
                for index in indexes
            ]
            for future in as_completed(futures):
                future.result()
        core.invalidate_workspace_size_cache(Path(workspace).parent)
        return {'refreshed': len(indexes)}

    @app.get('/api/ppt-dashboards/chart/{token}/{index}/filter-context')
    def interactive_chart_filter_context(token: str, index: int, user=Depends(dashboard_user)):
        """Return filter fields available to an expanded Dashboard chart."""
        snapshot, entry, _ = snapshot_chart(token, index, user, include_frame=False)
        task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
        _database_path, _table_name, columns = reporting_source(snapshot, entry.source_kind, task_repository)
        hidden = {identity('dataset_id'), identity('source_row_id')}
        datasets_by_source = {f'cdr-{kind}': [] for kind in KINDS}
        columns_by_source = {f'cdr-{kind}': [] for kind in KINDS}
        for row in task_repository.list_datasets():
            kind = str(row['dataset_kind'] or '').casefold()
            if kind in KINDS and row['status'] == 'ready':
                datasets_by_source[f'cdr-{kind}'].append({
                    'value': str(row['id']), 'label': str(row['file_name']),
                })
                columns_by_source[f'cdr-{kind}'].extend(
                    str(column) for column in task_repository.list_dataset_row_columns(int(row['id']))
                )
        for source, source_columns in columns_by_source.items():
            columns_by_source[source] = sorted({
                column for column in source_columns if identity(column) not in hidden
            }, key=str.casefold)
        datasets_by_source['cdr-all'] = [row for kind in KINDS for row in datasets_by_source[f'cdr-{kind}']]
        columns_by_source['cdr-all'] = [str(column) for column in columns if identity(column) not in hidden]
        template_available = user.role in {'user-editor', 'admin', 'super-admin'} and any(
            str(row['name']) == snapshot.definition.template
            for row in task_repository.list_report_templates()
        )
        return JSONResponse({
            'cdr_source': entry.cdr_source,
            'chart_type': entry.chart_type,
            'chart_title': entry.chart_title,
            'kpi': entry.kpi,
            'dataset_ids': [str(row['id']) for row in dashboard_datasets(snapshot.definition, entry.source_kind, task_repository)],
            'filters': entry.filters,
            'rows_split': entry.rows_split,
            'columns_split': entry.columns_split,
            'legend': entry.legend,
            'legend_position': entry.legend_position,
            'legend_format': entry.legend_format,
            'axis_x_range': entry.axis_x_range, 'axis_y_range': entry.axis_y_range,
            'label_position': entry.label_position,
            'label_format': entry.label_format,
            'exclude_null_empty': entry.exclude_null_empty, 'exclude_zero': entry.exclude_zero, 'dynamic_rows_field': entry_dynamic_fields(entry)[0], 'dynamic_columns_field': entry_dynamic_fields(entry)[1],
            'template_available': template_available,
            'datasets_by_source': datasets_by_source, 'columns_by_source': columns_by_source,
            'columns': columns_by_source.get(f'cdr-{entry.source_kind}', [str(column) for column in columns if identity(column) not in hidden]),
        })

    def build_interactive_chart_filter_preview(
        token: str,
        index: int,
        request: DashboardChartFilterPreviewRequest,
        user,
    ):
        """Build one expanded chart with temporary, unsaved template filters."""
        snapshot, entry, _ = snapshot_chart(token, index, user, include_frame=False)
        changes = {
            key: value for key, value in request.model_dump().items()
            if value is not None and key in {
                'filters', 'chart_title', 'cdr_source', 'kpi', 'chart_type', 'rows_split',
                'columns_split', 'legend', 'legend_position', 'legend_format', 'axis_x_range', 'axis_y_range', 'label_position', 'label_format', 'exclude_null_empty', 'exclude_zero', 'dynamic_rows_field', 'dynamic_columns_field', 'dynamic_field',
            }
        }
        # The template owns these required chart attributes. Custom dropdowns
        # can briefly report an empty value while their available fields are
        # being rebuilt, which must not erase the template KPI/source/type.
        for key in ('cdr_source', 'kpi', 'chart_type'):
            if not str(changes.get(key, '')).strip():
                changes.pop(key, None)
        if 'label_position' in changes:
            try:
                changes['label_position'] = core.parse_label_position(str(changes['label_position']))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        if 'label_format' in changes:
            try:
                changes['label_format'] = core.parse_label_format(str(changes['label_format']))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        if 'legend_format' in changes:
            try:
                changes['legend_format'] = core.parse_label_format(str(changes['legend_format']))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        for key, label in (('exclude_null_empty', 'Exclude Null/Empty'), ('exclude_zero', 'Exclude Zero')):
            if key in changes:
                try:
                    changes[key] = core.parse_template_boolean(changes[key], label)
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
        preview_entry = replace(entry, **changes)
        try:
            core.parse_axis_range(preview_entry.axis_x_range, 'x')
            core.parse_axis_range(preview_entry.axis_y_range, 'y')
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if not preview_entry.source_kind:
            raise HTTPException(400, 'Select a valid CDR type.')
        task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
        preview_definition = snapshot.definition.model_copy(deep=True)
        if request.dataset_ids is not None:
            values = request.dataset_ids if isinstance(request.dataset_ids, list) else str(request.dataset_ids).split(',')
            try:
                ids = list(dict.fromkeys(int(str(value).strip()) for value in values if str(value).strip()))
                if preview_entry.source_kind == 'all':
                    for kind in KINDS:
                        preview_definition.datasets[kind] = [value for value in ids if (task_repository.get_dataset(value) and str(task_repository.get_dataset(value)['dataset_kind']).casefold() == kind)]
                else:
                    preview_definition.datasets[preview_entry.source_kind] = ids
            except ValueError as exc:
                raise HTTPException(400, 'Selected datasets must have valid identifiers.') from exc
        # An expanded chart may introduce any available field. Materialize it
        # in the shared combined table before querying that table directly.
        preview_snapshot = replace(
            snapshot, entries=[preview_entry], definition=preview_definition,
            frames={}, chart_frames={}, filtered_frames={}, chart_payloads={}, frame_locks={},
        )
        selected = dashboard_datasets(preview_definition, preview_entry.source_kind, task_repository)
        ensure_combined_filter_columns(
            preview_definition, task_repository, snapshot.dimensions,
            selected_sources(preview_definition, task_repository), [preview_entry],
        )
        database_path, table_name, source_columns = reporting_source(
            preview_snapshot, preview_entry.source_kind, task_repository,
        )
        where, parameters = selection_where(
            task_repository, preview_entry.source_kind, [int(row['id']) for row in selected],
            preview_definition, columns=source_columns,
        )
        requested_columns = chart_query_columns(preview_entry, snapshot.multivendor)
        template_where, template_parameters, template_filters_applied = chart_filter_sql(
            preview_entry, source_columns, snapshot.multivendor, task_repository,
        )
        if template_where:
            where = f'({where}) AND ({template_where})'
            parameters.extend(template_parameters)
        aggregation_columns = chart_aggregation_columns(
            preview_entry, source_columns, snapshot.multivendor, template_filters_applied,
        )
        raw_frame = load_reporting_frame(
            database_path, table_name, source_columns, requested_columns, where, parameters,
            aggregation_columns,
        )
        if snapshot.multivendor:
            raw_frame = ensure_vendor_group(raw_frame)
        mapping_settings = task_repository.chart_mapping_settings()
        operator_mappings = mapping_settings['operator_mappings']
        raw_frame = apply_operator_mappings(raw_frame, operator_mappings)
        raw_frame = drop_excluded_operators(raw_frame, excluded_operators(mapping_settings))
        raw_frame.attrs.update(mapping_settings)
        raw_frame = normalise_operator_aliases(raw_frame)
        raw_frame.attrs['operator_aliases_normalized'] = True
        try:
            frame, _ = prepare_catalog_chart_preview_frame(
                raw_frame, preview_entry, multivendor=snapshot.multivendor,
                template_filters_applied=template_filters_applied,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return catalog_chart_payload(
            frame, preview_entry, multivendor=snapshot.multivendor, prefiltered=True,
        )

    def run_interactive_chart_filter_preview(
        job_id: str,
        token: str,
        index: int,
        request: DashboardChartFilterPreviewRequest,
        user,
    ) -> None:
        """Finish a potentially slow preview without holding a proxy request open."""
        try:
            payload = build_interactive_chart_filter_preview(token, index, request, user)
            result = {'state': 'ready', 'payload': payload}
        except HTTPException as exc:
            result = {'state': 'failed', 'status': exc.status_code, 'detail': str(exc.detail)}
        except Exception as exc:
            result = {'state': 'failed', 'status': 500, 'detail': str(exc)}
        with lock:
            job = interactive_chart_preview_jobs.get(job_id)
            if job is not None:
                job.update(result)

    @app.post('/api/ppt-dashboards/chart/{token}/{index}/filter-preview')
    def interactive_chart_filter_preview(
        token: str,
        index: int,
        request: DashboardChartFilterPreviewRequest,
        background_tasks: BackgroundTasks,
        background: bool = False,
        user=Depends(dashboard_user),
    ):
        """Render one temporary chart, optionally outside the proxy request."""
        if not background:
            return JSONResponse(
                build_interactive_chart_filter_preview(token, index, request, user),
                headers={'Cache-Control': 'no-store'},
            )
        # Validate access before returning a job identifier. The worker repeats
        # the check so an expired snapshot still becomes an actionable error.
        snapshot_chart(token, index, user, include_frame=False)
        job_id = uuid4().hex
        with lock:
            interactive_chart_preview_jobs[job_id] = {
                'state': 'processing', 'owner': user.username, 'workspace': workspace_key(),
            }
            while len(interactive_chart_preview_jobs) > 32:
                removable = next((
                    key for key, value in interactive_chart_preview_jobs.items()
                    if value.get('state') != 'processing'
                ), None)
                if removable is None:
                    break
                interactive_chart_preview_jobs.pop(removable, None)
        background_tasks.add_task(
            run_interactive_chart_filter_preview, job_id, token, index, request, user,
        )
        return JSONResponse(
            {'state': 'processing', 'job_id': job_id}, status_code=202,
            headers={'Cache-Control': 'no-store'},
        )

    @app.get('/api/ppt-dashboards/chart-preview-jobs/{job_id}')
    def interactive_chart_filter_preview_status(job_id: str, user=Depends(dashboard_user)):
        """Return a temporary Chart Definition preview once its query completes."""
        with lock:
            job = interactive_chart_preview_jobs.get(job_id)
            if (
                job is None
                or job.get('owner') != user.username
                or job.get('workspace') != workspace_key()
            ):
                raise HTTPException(404, 'Chart preview job not found.')
            result = dict(job)
        if result.get('state') == 'processing':
            return JSONResponse(
                {'state': 'processing', 'job_id': job_id}, status_code=202,
                headers={'Cache-Control': 'no-store'},
            )
        if result.get('state') == 'failed':
            raise HTTPException(int(result.get('status') or 500), str(result.get('detail') or 'Unable to render chart preview.'))
        return JSONResponse(result['payload'], headers={'Cache-Control': 'no-store'})

    @app.post('/api/ppt-dashboards/chart/{token}/{index}/update-template')
    def update_interactive_chart_template(
        token: str,
        index: int,
        request: DashboardChartFilterPreviewRequest,
        user=Depends(dashboard_editor_user),
    ):
        """Persist the expanded Chart Definition into its source template row."""
        snapshot, _entry, _ = snapshot_chart(token, index, user, include_frame=False)
        task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
        template_name, nr_mode = snapshot.definition.template, dashboard_nr_mode(snapshot.definition)
        template = next((
            row for row in task_repository.list_report_templates()
            if str(row['name']) == template_name
        ), None)
        if template is None:
            raise HTTPException(404, 'The Report Template used by this chart is no longer available.')
        # The template as written (its titles may name the NR Mode with tokens, which the Dashboard shows resolved).
        try:
            entries = core.load_template_catalogue(bytes(template['content']), task_repository=task_repository)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        source_index = _entry.template_index if _entry.template_index is not None else index
        if source_index >= len(entries):
            raise HTTPException(404, 'The chart row is no longer available in the Report Template.')
        changes = {
            key: value for key, value in request.model_dump().items()
            if value is not None and key in {
                'filters', 'chart_title', 'cdr_source', 'kpi', 'chart_type', 'rows_split',
                'columns_split', 'legend', 'legend_position', 'legend_format', 'axis_x_range', 'axis_y_range', 'label_position', 'label_format', 'exclude_null_empty', 'exclude_zero', 'dynamic_rows_field', 'dynamic_columns_field', 'dynamic_field',
            }
        }
        for key in ('cdr_source', 'kpi', 'chart_type'):
            if not str(changes.get(key, '')).strip():
                changes.pop(key, None)
        if 'label_position' in changes:
            try:
                changes['label_position'] = core.parse_label_position(str(changes['label_position']))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        if 'label_format' in changes:
            try:
                changes['label_format'] = core.parse_label_format(str(changes['label_format']))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        if 'legend_format' in changes:
            try:
                changes['legend_format'] = core.parse_label_format(str(changes['legend_format']))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        for key, label in (('exclude_null_empty', 'Exclude Null/Empty'), ('exclude_zero', 'Exclude Zero')):
            if key in changes:
                try:
                    changes[key] = core.parse_template_boolean(changes[key], label)
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
        if changes.get("chart_title") in {_entry.chart_title, entry_for_nr_mode(entries[source_index], nr_mode).chart_title}:
            # The title as the chart shows it (dynamic values, the NR Mode resolved): the template keeps its own.
            changes["chart_title"] = entries[source_index].chart_title
        for field in ('dynamic_rows_field', 'dynamic_columns_field', 'dynamic_field', 'rows_split', 'columns_split', 'legend'):
            if field in changes and changes[field] == getattr(_entry, field):
                changes[field] = getattr(entries[source_index], field)
        updated_entry = replace(entries[source_index], **changes)
        try:
            core.parse_axis_range(updated_entry.axis_x_range, 'x')
            core.parse_axis_range(updated_entry.axis_y_range, 'y')
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        entries[source_index] = updated_entry
        try:
            task_repository.set_report_template_content(
                template_name, core.catalogue_csv(entries), updated_by=user.username,
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(503, f'Unable to update the Report Template: {exc}') from exc
        # Keep every live view of this Report Template consistent with the row
        # just persisted. The Dashboard viewer, an expanded chart and a
        # restored/PPT chart can legitimately use different snapshot tokens;
        # updating only the request's snapshot makes another one reopen the
        # previous Chart Definition even though the CSV was saved correctly.
        with lock:
            matching_snapshots = [
                candidate for candidate in snapshots.values()
                if (
                    candidate.workspace == snapshot.workspace
                    and candidate.definition.template == template_name
                )
            ]
            for candidate in matching_snapshots:
                for chart_index, current in enumerate(candidate.entries):
                    current_source = current.template_index if current.template_index is not None else chart_index
                    if current_source != source_index:
                        continue
                    candidate_mode = dashboard_nr_mode(candidate.definition)
                    shown_update = entry_for_nr_mode(updated_entry, candidate_mode)
                    effective_update = (prepare_multivendor_catalog_entry(shown_update, candidate.definition.vendor_comparison)
                                        if candidate.multivendor else shown_update)
                    replacement = replace(
                        effective_update, slide=current.slide, layout=current.layout, template_index=current.template_index,
                        dynamic_value=current.dynamic_value,
                        dynamic_row_value=current.dynamic_row_value, dynamic_column_value=current.dynamic_column_value,
                    )
                    replacement = replace(replacement, chart_title=dynamic_chart_title(replacement))
                    candidate.entries[chart_index] = replacement
                    candidate.chart_frames.pop(chart_index, None)
                    candidate.chart_frames.pop(('complete', chart_index), None)
                    candidate.chart_payloads.pop(chart_index, None)
                    candidate.filtered_frames.clear()
                    for slide in candidate.payload.get('slides', []):
                        for chart in slide.get('charts', []):
                            if chart.get('index') == chart_index:
                                chart.update({'title': replacement.chart_title, 'source': replacement.source_kind,
                                              'cdr_source': replacement.cdr_source, 'chart_type': replacement.chart_type})
        task_repository.add_log(user.username, 'update_dashboard_chart_template', json.dumps({
            'template': template_name, 'nr_mode': nr_mode, 'chart_index': index,
        }))
        return {
            'template': template_name, 'chart_index': index,
            'synced_snapshots': len(matching_snapshots),
            'updated_at': str(next((
                row['updated_at'] for row in task_repository.list_report_templates()
                if str(row['name']) == template_name
            ), '')),
        }

    def dashboard_status_signature(workspace, raw_definition, task_repository, shared) -> str:
        """Fingerprint every input that can change a Dashboard's cached universes."""
        definition = raw_definition if isinstance(raw_definition, dict) else {}
        template = str(definition.get('template') or '')
        template_key = template
        if template_key not in shared['templates']:
            try:
                content = task_repository.report_template_content(template)
                shared['templates'][template_key] = sha256(content).hexdigest()
            except Exception:
                shared['templates'][template_key] = ''
        return sha256(json.dumps({
            # The identity of the template is not an input: its content is.
            'definition': {key: value for key, value in definition.items() if key != 'template_uid'},
            'template': shared['templates'][template_key],
            'shared': shared['signature'],
        }, sort_keys=True, default=str).encode()).hexdigest()

    def dashboard_status_shared_state(workspace, task_repository) -> dict:
        datasets = [
            (row['id'], row['status'], row['dataset_kind'], row['nr_mode'], row['updated_at'], row['processed_at'])
            for row in task_repository.list_datasets()
        ]
        manifest_dir = preview_manifest_cache_dir(workspace)
        try:
            manifests_changed = manifest_dir.stat().st_mtime_ns
        except OSError:
            manifests_changed = 0
        data_signature = sha256(json.dumps({
            'datasets': datasets,
            'revisions': {kind: task_repository.get_workspace_state(f'combined_reporting_updated_{kind}') for kind in KINDS},
            'dimension_definitions': core.calculated_dimensions_json(core.load_repository_calculated_dimensions(task_repository)),
            'mappings': task_repository.chart_mapping_settings(),
        }, sort_keys=True, default=str).encode()).hexdigest()
        # New manifests change cached results but not the data behind them.
        signature = sha256(f'{data_signature}:{manifests_changed}'.encode()).hexdigest()
        return {'signature': signature, 'data_signature': data_signature, 'templates': {}}

    dashboard_chart_model_paths: dict[tuple[str, str], tuple[str, list[Path]]] = {}

    def default_universe_chart_progress(workspace, dashboard_id, raw_definition, task_repository, data_signature):
        """Rendered and total charts of a Dashboard's default universe in its saved mode.

        The expected model files are resolved once per definition and cache
        signature (which changes with the data and the prepared universes);
        each status poll then only checks which of them exist.
        """
        key = (workspace, dashboard_id)
        signature = sha256(f'{json.dumps(raw_definition, sort_keys=True, default=str)}:{data_signature}'.encode()).hexdigest()
        with lock:
            cached = dashboard_chart_model_paths.get(key)
        if cached is None or cached[0] != signature:
            paths = None
            definition = DashboardDefinition.model_validate(runtime_dashboard_definition(raw_definition, task_repository))
            payload = restore_matching_preview_manifest(workspace, dashboard_id, definition)
            with lock:
                snapshot = snapshots.get(payload['token']) if payload else None
            if snapshot is not None:
                mapping_key = sha256(json.dumps(task_repository.chart_mapping_settings(), sort_keys=True).encode()).hexdigest()
                indexes = sorted({
                    int(chart['index']) for slide in payload.get('slides', []) for chart in slide.get('charts', [])
                    if chart.get('available')
                })
                paths = [canvas_model_path(snapshot, snapshot.entries[index], mapping_key) for index in indexes]
            # An unprepared default universe is remembered too, until the
            # signature changes, so polling never repeats the lookup.
            cached = (signature, paths)
            with lock:
                dashboard_chart_model_paths[key] = cached
        paths = cached[1]
        if paths is None:
            return None
        return sum(path.is_file() for path in paths), len(paths)

    def dashboard_status_payload(requested_definitions=None, username='system', active_dashboard_id=None):
        """Return pre-caching states and keep every standard universe queued."""
        workspace = workspace_key()
        task_repository = Repository(Path(workspace), core.repository.global_db_path)
        dashboards = read_dashboards(task_repository)
        result = {}
        with lock:
            direct_jobs = {}
            for dashboard_id in dashboards:
                direct_jobs[dashboard_id] = next((
                    dict(task) for task in direct_preparation_tasks.values()
                    if task.get('workspace') == workspace and task.get('dashboard_id') == dashboard_id
                ), None)
        try:
            shared = dashboard_status_shared_state(workspace, task_repository)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            shared = {'signature': uuid4().hex, 'data_signature': '', 'templates': {}}
        with lock:
            if shared['data_signature'] and dashboard_status_shared_signature.get(workspace) != shared['data_signature']:
                # Data, mappings or caches changed: re-check every Dashboard and
                # retry universes that were previously unavailable.
                dashboard_status_shared_signature[workspace] = shared['data_signature']
                for stale_key in [key for key in dashboard_warmup_unavailable if key[0] == workspace]:
                    dashboard_warmup_unavailable.pop(stale_key, None)
                dashboard_warmup_checked.difference_update(
                    {key for key in dashboard_warmup_checked if key[0] == workspace}
                )
        for dashboard_id, raw_definition in dashboards.items():
            direct_job = direct_jobs.get(dashboard_id)
            if direct_job is not None:
                rendering_only = bool(direct_job.get('rendering_only'))
                result[dashboard_id] = {
                    'state': 'rendering' if rendering_only else 'loading-data',
                    'label': 'Rendering' if rendering_only else 'Loading data',
                }
                continue
            key = (workspace, dashboard_id)
            signature = dashboard_status_signature(workspace, raw_definition, task_repository, shared)
            with lock:
                cached = dashboard_status_cache.get(key)
            if cached is not None and cached[0] == signature:
                total, prepared_count = cached[1], cached[2]
            else:
                try:
                    definitions = dashboard_warmup_definitions(raw_definition, task_repository)
                    with lock:
                        unavailable = set(dashboard_warmup_unavailable.get(key, set()))
                    prepared_count = sum(
                        warmup_universe_identity(definition) in unavailable
                        or restore_matching_preview_manifest(
                            workspace, dashboard_id, definition, materialize=False,
                        ) is not None
                        for definition in definitions
                    )
                    total = len(definitions)
                except (HTTPException, KeyError, OSError, sqlite3.Error, TypeError, ValueError):
                    total, prepared_count = 0, 0
                with lock:
                    dashboard_status_cache[key] = (signature, total, prepared_count)
            if total and prepared_count == total:
                try:
                    progress = default_universe_chart_progress(
                        workspace, dashboard_id, raw_definition, task_repository, shared['signature'],
                    )
                except (HTTPException, KeyError, OSError, sqlite3.Error, TypeError, ValueError, IndexError):
                    progress = None
                with lock:
                    rendering = dashboard_warmup_running['key'] == key and dashboard_warmup_running.get('phase') == 'charts'
                counts = f' {progress[0]}/{progress[1]}' if progress else ''
                if progress is not None and progress[0] >= progress[1]:
                    result[dashboard_id] = {
                        'state': 'ready', 'label': 'Ready', 'detail': f'Data cached and all {progress[1]} charts rendered',
                    }
                elif rendering:
                    result[dashboard_id] = {
                        'state': 'rendering', 'label': f'Rendering Charts{counts}',
                        'detail': 'Data cached; the remaining charts are rendering in the background',
                    }
                else:
                    # The default universe's charts are not rendered yet (or
                    # that universe is not prepared yet).
                    result[dashboard_id] = {
                        'state': 'charts-queued', 'label': f'Data Cached · Charts{counts}',
                        'detail': 'Data cached; charts render when viewed or while the application is idle',
                    }
                continue
            if not total:
                result[dashboard_id] = {'state': 'data-needed', 'label': 'Data needed'}
                continue
            # Status polling only queues a missing warm-up; it never restarts a
            # queued or running one, nor repeats a finished check (a changed
            # workspace signature above clears those checks).
            schedule_dashboard_warmup(workspace, dashboard_id, raw_definition, username)
            with lock:
                warmup = dict(dashboard_warmup_cancellations.get(key) or {})
            completed = max(int(warmup.get('completed') or 0), prepared_count)
            total = int(warmup.get('total') or total)
            current = min(completed + 1, total)
            label = f'Pre-Caching Universe {current}/{total}'
            if not warmup.get('active'):
                label += ' · Waiting'
            result[dashboard_id] = {'state': 'loading-data', 'label': label}
        return JSONResponse(result, headers={'Cache-Control': 'no-store, max-age=0, must-revalidate'})

    @app.get('/api/ppt-dashboards/statuses')
    def dashboard_statuses(active_dashboard_id: str | None = None, user=Depends(dashboard_user)):
        return dashboard_status_payload(username=user.username, active_dashboard_id=active_dashboard_id)

    @app.post('/api/ppt-dashboards/statuses')
    def dashboard_statuses_for_session(
        definitions: dict[str, DashboardDefinition], active_dashboard_id: str | None = None,
        user=Depends(dashboard_user),
    ):
        """Report pre-caching states; the open Dashboard is pre-cached first."""
        return dashboard_status_payload(definitions, username=user.username, active_dashboard_id=active_dashboard_id)

    def cancel_workspace_dashboard_tasks(workspace: str | Path) -> list:
        """Cancel explicitly requested Dashboard preparation for a workspace."""
        database_path = str(Path(workspace).resolve())
        with lock:
            for task in direct_preparation_tasks.values():
                if task.get('workspace') == database_path:
                    cancellation = task.get('cancellation')
                    if isinstance(cancellation, dict):
                        cancellation['requested'] = True
            stale_tokens = [token for token, snapshot in snapshots.items() if snapshot.workspace == database_path]
            for token in stale_tokens:
                snapshots.pop(token, None)
            # Closing a workspace drops its queued pre-caching and stops the
            # running one at its next checkpoint.
            for key in [key for key in dashboard_warmup_queue if key[0] == database_path]:
                dashboard_warmup_queue.pop(key, None)
            for key, state in dashboard_warmup_cancellations.items():
                if key[0] == database_path:
                    state['requested'] = True
            dashboard_warmup_condition.notify_all()
            column_cache = column_caches.pop(database_path, None)
        if column_cache is not None:
            column_cache.forget()
        return []

    def invalidate_workspace_chart_models(workspace: str | Path) -> None:
        """Rebuild open Dashboard charts after a mapping colour/order change."""
        database_path = str(Path(workspace).resolve())
        with lock:
            for snapshot in snapshots.values():
                if snapshot.workspace != database_path:
                    continue
                # Raw/filtered frames retain the mapping aliases and their
                # grouping order. Keep the prepared selection and slide token,
                # but rebuild all mapping-dependent chart data and Canvas
                # payloads on the next request.
                snapshot.frames.clear()
                snapshot.filtered_frames.clear()
                snapshot.chart_frames.clear()
                snapshot.chart_payloads.clear()
                snapshot.frame_locks.clear()

    def dashboard_task_payloads(workspace):
        database_path = str(workspace.database_path.resolve())
        with lock:
            direct_tasks = [
                task for task in direct_preparation_tasks.values()
                if task['workspace'] == database_path
                and not bool((task.get('cancellation') or {}).get('requested'))
            ]
            return [{
                'id': task['id'],
                'dashboard_name': task['name'],
                'label': (
                    'Waiting to render Dashboard Charts' if task.get('rendering_only') else 'Waiting to prepare Dashboard dataset'
                ) if task.get('status') == 'queued' else (
                    'Rendering Dashboard Charts' if task.get('rendering_only') else 'Preparing Dashboard dataset'
                ),
                'detail': (
                    'Rendering charts with the current Dashboard scope'
                    if task.get('rendering_only')
                    else str(task.get('detail') or 'Building filtered Dashboard selection')
                ),
                'status': task.get('status', 'processing'),
                'queued_at': task.get('queued_at'),
                'started_at': task.get('started_at'),
                'progress': task.get('progress', 0),
                'stop_task_id': f'dashboard-prepare:{task["id"]}',
                'stop_url': f'/api/background-tasks/{workspace.id}/stop',
            } for task in direct_tasks]

    def stop_dashboard_task(workspace_path, task_id):
        database_path = str(Path(workspace_path).resolve())
        stopped = False
        with lock:
            direct = direct_preparation_tasks.get(task_id)
            if direct and direct.get('workspace') == database_path:
                cancellation = direct.get('cancellation')
                if isinstance(cancellation, dict):
                    cancellation['requested'] = True
                    stopped = True
        return stopped

    def rename_template_dashboards(previous_template: str, template: str, username: str) -> int:
        """Keep Dashboard template references and display names aligned after a template rename."""
        workspace = workspace_key()
        with lock:
            task_repository = bound_repository()
            dashboards = read_dashboards(task_repository)
            changed = [(dashboard_id, dashboards[dashboard_id])
                       for dashboard_id in rename_template_in_dashboards(dashboards, previous_template, template)]
            if changed:
                task_repository.set_workspace_state(STATE_KEY, json.dumps(dashboards))
                task_repository.add_log(username, 'rename_dashboard_template_references', json.dumps({
                    'previous_template': previous_template,
                    'template': template, 'dashboards': len(changed),
                }))
        for dashboard_id, definition in changed:
            schedule_dashboard_warmup(workspace, dashboard_id, definition, username, force=True)
        return len(changed)

    core.ppt_dashboard_tasks = dashboard_task_payloads
    core.ppt_dashboard_cancel_workspace_tasks = cancel_workspace_dashboard_tasks
    core.ppt_dashboard_invalidate_chart_models = invalidate_workspace_chart_models
    core.ppt_dashboard_stop_task = stop_dashboard_task
    core.ppt_dashboard_rename_template_references = rename_template_dashboards
    core.ppt_dashboard_reconcile_template_slide_comments = reconcile_template_slide_comments

    @app.get('/api/ppt-dashboards/preview/{token}/{index}.png')
    def chart(token: str, index: int, user=Depends(dashboard_user)):
        snapshot, entry, _ = snapshot_chart(token, index, user, include_frame=False)
        entry_key = sha256(repr(entry).encode()).hexdigest()
        task_repository = Repository(Path(snapshot.workspace), core.repository.global_db_path)
        operator_mapping_key = sha256(json.dumps(
            task_repository.chart_mapping_settings(), sort_keys=True,
        ).encode()).hexdigest()
        key = (snapshot.selection_key, snapshot.definition.scope, entry_key, operator_mapping_key)
        cache_dir = pil_chart_cache_dir(snapshot.workspace)
        cache_path = cache_dir / sha256(
            f'{DASHBOARD_RENDER_CACHE_VERSION}:{snapshot.selection_key}:{snapshot.definition.scope}:'
            f'{entry_key}:{operator_mapping_key}'.encode()
        ).hexdigest()
        cache_path = cache_path.with_suffix('.png')
        # PIL chart renderers have no shared global canvas. Let browser image
        # requests for the same slide render concurrently instead of placing
        # every chart behind one process-wide lock; only cache mutation needs
        # synchronization.
        with lock:
            png = images.get(key)
        if png is None and cache_path.is_file():
            try:
                png = cache_path.read_bytes()
                cache_path.touch()
            except OSError:
                png = None
        if png is None:
            _, _, frame = snapshot_chart(token, index, user)
            try:
                rendered = render_catalog_chart_preview(frame, entry, multivendor=snapshot.multivendor, prefiltered=True)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            with lock:
                png = images.setdefault(key, rendered)
                images[key] = png
                while len(images) > 100:
                    images.popitem(last=False)
            try:
                cache_dir.mkdir(parents=True, exist_ok=True)
                temporary = cache_path.with_suffix(f'.{uuid4().hex}.tmp')
                temporary.write_bytes(png)
                temporary.replace(cache_path)
                cached_files = sorted(cache_dir.glob('*.png'), key=lambda path: path.stat().st_mtime, reverse=True)
                for stale in cached_files[200:]:
                    stale.unlink(missing_ok=True)
            except OSError:
                pass
        # The same Dashboard token can be explicitly refreshed. Never let a
        # browser keep a previously rendered chart image for an hour after the
        # server has rebuilt its model or mapping-dependent frame.
        return Response(png, media_type='image/png', headers={'Cache-Control': 'no-store, max-age=0, must-revalidate'})

    @app.get('/api/ppt-dashboards/data/{token}/{index}')
    def chart_data(
        token: str, index: int, page: int = 0, download: bool = False,
        column_filters: str = '', include_filter_values: bool = False, filter_column: str = '',
        user=Depends(dashboard_user),
    ):
        snapshot, entry, _ = snapshot_chart(token, index, user, include_frame=False)
        filter_column = vendor_filter_column(filter_column) if filter_column else ''
        selected_column_filters = {vendor_filter_column(key): values for key, values in parse_chart_column_filters(column_filters).items()}
        if not download:
            projected_page = reporting_chart_data_page(
                snapshot, entry, page, selected_column_filters, include_filter_values, filter_column,
            )
            if projected_page is not None:
                visible, total, chart_total, filter_values = projected_page
                return {
                    'columns': list(visible.columns),
                    'rows': visible.fillna('').astype(str).values.tolist(),
                    'total': total, 'chart_total': chart_total,
                    'filter_values': filter_values, 'page': max(page, 0),
                    'column_classes': chart_dataset_column_classes(snapshot, entry, visible.columns),
                    'column_metadata': chart_dataset_column_metadata(snapshot, entry, visible.columns),
                    'page_size': 100, 'unfiltered_total': chart_total,
                }
        _, _, frame = snapshot_chart(token, index, user, complete=True)
        frame = unique_chart_dataset_rows(snapshot, entry, frame)
        chart_total = len(frame)
        values_frame = apply_chart_column_filters(
            frame, {column: values for column, values in selected_column_filters.items() if identity(column) != identity(filter_column)},
        )
        available_filter_values = chart_dataset_filter_values(values_frame) if filter_column else {}
        filter_values = next(
            (values for column, values in available_filter_values.items() if identity(column) == identity(filter_column)), []
        ) if filter_column else (chart_dataset_filter_values(frame) if include_filter_values else {})
        frame = apply_chart_column_filters(frame, selected_column_filters)
        if download:
            bound_repository().try_add_log(user.username, 'export_dashboard_chart_data_csv', json.dumps({
                'dashboard': snapshot.definition.name, 'chart_index': index, 'rows': len(frame),
            }))
            return Response(frame.to_csv(index=False), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="dashboard-chart-data.csv"'})
        page = max(page, 0)
        visible = frame.iloc[page*100:(page+1)*100].fillna('').astype(str)
        return {
            'columns': list(visible.columns), 'rows': visible.values.tolist(),
            'total': len(frame), 'chart_total': chart_total,
            'filter_values': filter_values, 'page': page,
            'column_classes': chart_dataset_column_classes(snapshot, entry, visible.columns),
            'column_metadata': chart_dataset_column_metadata(snapshot, entry, visible.columns),
            'page_size': 100, 'unfiltered_total': chart_total,
        }
