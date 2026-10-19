"""Renaming an Operator or a Vendor in the Operator Maps or Vendor Maps renames it in every saved filter: the Reporting
Jobs, the workspace settings that keep filters, the Saved Filters of Scoring & GAP Analysis (their GAP reference and
filters) and the favourites of the Bundle Report Templates and Network Insights.

Saved filters keep the mapped labels (see ``value_maps``), so a renamed label would no longer match
and the filters would silently drop it. Only values of Operator, Operator_Vendor, Vendor_Operator and
Vendor fields change, and only when they are the renamed label: ``<Operator>``, ``<Operator>_<Vendor>``,
``<Vendor>_<Operator>`` or ``<Operator> - All``. Campaign filters keep the full campaign value, which a
Campaign Map only shows differently, so they never need renaming.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode

# Filter keys and the kind of value they hold.
KEY_KINDS = {
    'operator': 'operator', 'operators': 'operator', 'baseline_operator': 'operator', 'map_operator': 'operator',
    'operator_vendor': 'operator_vendor', 'operator_vendors': 'operator_vendor',
    'vendor_operator': 'vendor_operator', 'vendor_operators': 'vendor_operator',
    'vendor': 'vendor', 'vendors': 'vendor', 'vendors_only': 'vendor',
}
# Workspace settings that keep filters: saved Scoring report configurations, the Scoring calculation,
# the Non-Qualified Calls filters and the Dashboards. CDR Analysis keeps the filters of each CDR as a query string.
FILTER_STATE_KEYS = (
    'scoring_report_configurations', 'scoring_calculation_selection_v1', 'nq_calls_filters',
    'ppt_dashboards_v2', 'ppt_dashboard_sets_v1',
)
CDR_ANALYSIS_STATE_KEY = 'datasets_analysis_selection_v1'
_ALL_SUFFIX = re.compile(r'^(?P<name>.+?)\s+- All(?: Vendors)?$', re.IGNORECASE)


def key_kind(key: Any) -> str | None:
    return KEY_KINDS.get(re.sub(r'[^a-z0-9]+', '_', str(key).casefold()).strip('_'))


def _labels(mapping_settings: dict[str, Any], mapping_type: str, extra: tuple[str, ...]) -> list[str]:
    labels = {str(label).strip() for group in mapping_settings.get(f'{mapping_type}_mapping_groups') or []
              for label in [group.get('canonical'), *(group.get('aliases') or [])] if str(label or '').strip()}
    labels.update(label for label in extra if label)
    # The longest first, so VF_SA_Ericsson is VF_SA's and not VF's.
    return sorted(labels, key=len, reverse=True)


def value_renamer(mapping_type: str, old_name: str, new_name: str,
                  mapping_settings: dict[str, Any]) -> Callable[[str, str], str]:
    """``rename(kind, value)``: the value with the renamed Operator or Vendor label."""
    old, new = str(old_name).strip(), str(new_name).strip()
    old_key = old.casefold()
    names = (old, new)
    operators = _labels(mapping_settings, 'operator', names if mapping_type == 'operator' else ())
    vendors = _labels(mapping_settings, 'vendor', names if mapping_type == 'vendor' else ())

    def rename(kind: str, value: str) -> str:
        text = value.strip()
        folded = text.casefold()
        if not old or not new or old == new or not text:
            return value
        operator_only = _ALL_SUFFIX.match(text)
        if operator_only:
            renamed = mapping_type == 'operator' and operator_only['name'].strip().casefold() == old_key
            return f'{new} - All' if renamed else value
        if kind == mapping_type:
            return new if folded == old_key else value
        if kind == 'operator_vendor':
            operator = next((label for label in operators if folded.startswith(f'{label.casefold()}_')), None)
            vendor = text[len(operator) + 1:] if operator else ''
        elif kind == 'vendor_operator':
            operator = next((label for label in operators if len(folded) > len(label) + 1
                             and folded.endswith(f'_{label.casefold()}')), None)
            vendor = text[:len(text) - len(operator) - 1] if operator else ''
        else:
            return value
        if not operator or not vendor:
            return value
        if mapping_type == 'operator' and operator.casefold() == old_key:
            operator = new
        elif mapping_type == 'vendor' and vendor.casefold() == old_key and any(
                label.casefold() == old_key for label in vendors):
            vendor = new
        else:
            return value
        return f'{operator}_{vendor}' if kind == 'operator_vendor' else f'{vendor}_{operator}'

    return rename


def rename_in_document(document: Any, rename: Callable[[str, str], str], kind: str | None = None) -> Any:
    """A copy of a JSON document with the values of its Operator and Vendor filters renamed."""
    if isinstance(document, dict):
        return {key: rename_in_document(item, rename, key_kind(key)) for key, item in document.items()}
    if isinstance(document, list):
        return [rename_in_document(item, rename, kind) for item in document]
    if isinstance(document, str) and kind:
        return rename(kind, document)
    return document


def rename_in_query(query: str, rename: Callable[[str, str], str]) -> str:
    """A CDR Analysis query string (``operator=VF&vendor=Ericsson``) with its filter values renamed."""
    pairs = parse_qsl(query, keep_blank_values=True)
    renamed = [(key, rename(kind, value) if (kind := key_kind(key)) else value) for key, value in pairs]
    return urlencode(renamed) if renamed != pairs else query


def rename_saved_filters(repository: Any, mapping_type: str, old_name: str, new_name: str,
                         mapping_settings: dict[str, Any], write: bool = True) -> int:
    """Rename an Operator or Vendor in the Reporting Jobs and workspace settings; returns how many changed.

    Without ``write`` nothing is saved: it counts the Reporting Jobs and saved filters that use the label.
    """
    from src.modules.report_tasks import rename_definition_values

    rename = value_renamer(mapping_type, old_name, new_name, mapping_settings)
    changed = rename_definition_values(repository, lambda definition: rename_in_document(definition, rename), write)
    changed += rename_scoring_saved_filters(repository, rename, write)
    changed += rename_favourites(repository, rename, write)
    for state_key in FILTER_STATE_KEYS:
        stored = repository.get_workspace_state(state_key)
        if not stored:
            continue
        try:
            document = json.loads(stored)
        except (TypeError, ValueError):
            continue
        renamed = rename_in_document(document, rename)
        if renamed != document:
            if write:
                repository.set_workspace_state(state_key, json.dumps(renamed, ensure_ascii=False))
            changed += 1
    try:
        selection = json.loads(repository.get_workspace_state(CDR_ANALYSIS_STATE_KEY) or '{}')
    except (TypeError, ValueError):
        selection = {}
    queries = selection.get('queries') if isinstance(selection, dict) else None
    if isinstance(queries, dict):
        renamed_queries = {key: rename_in_query(str(value), rename) for key, value in queries.items()}
        if renamed_queries != queries:
            if write:
                repository.set_workspace_state(CDR_ANALYSIS_STATE_KEY, json.dumps({**selection, 'queries': renamed_queries}))
            changed += 1
    return changed


def rename_scoring_saved_filters(repository: Any, rename: Callable[[str, str], str], write: bool = True) -> int:
    """The Saved Filters of Scoring & GAP Analysis with the renamed label in their GAP reference and filters, and the
    selection they are found by again; returns how many changed. A Saved Filter whose renamed selection is that of
    another one keeps its own. Their results are calculated again when opened (the Operator Maps changed)."""
    from src.modules.cdr_auto_selection import campaign_presets
    from src.modules.saved_filters import SAVED_FILTERS_TABLE, saved_filter_key

    def selection_key(row: Any, baseline: str, snapshot: dict[str, Any]) -> str:
        filters = snapshot.get('context_filters') or {}
        ids = [] if campaign_presets(filters.get('Campaign') or []) else json.loads(row['dataset_ids_json'] or '[]')
        return saved_filter_key(ids, json.loads(row['levels_json'] or '[]'), row['nr_mode'], baseline, filters,
                                str(snapshot.get('scoring_profile_id') or ''), snapshot.get('area_summary'))

    changed = 0
    with repository.connection() as connection:
        try:
            rows = connection.execute(f'SELECT id, selection_key, baseline_operator, source_metadata_json, levels_json, nr_mode, '
                                      f'dataset_ids_json FROM {SAVED_FILTERS_TABLE}').fetchall()
        except sqlite3.OperationalError:
            return 0
        keys = {row['selection_key'] for row in rows}
        for row in rows:
            try:
                snapshot = json.loads(row['source_metadata_json'] or '{}')
            except (TypeError, ValueError):
                continue
            if not isinstance(snapshot, dict):
                continue
            # Only their filters: the metadata of their CDRs keeps the names of the CDRs.
            renamed = {**snapshot, **{name: rename_in_document(snapshot[name], rename)
                                      for name in ('context_filters', 'resolved_context_filters') if name in snapshot}}
            baseline = rename('operator', str(row['baseline_operator'] or ''))
            if renamed == snapshot and baseline == row['baseline_operator']:
                continue
            key = row['selection_key']
            # (A Saved Filter saved with another form of selection keeps the one it has.)
            if selection_key(row, str(row['baseline_operator'] or ''), snapshot) == key:
                key = selection_key(row, baseline, renamed)
                if key != row['selection_key'] and key in keys:
                    continue
            changed += 1
            if write:
                connection.execute(f'UPDATE {SAVED_FILTERS_TABLE} SET selection_key = ?, baseline_operator = ?, '
                                   'source_metadata_json = ? WHERE id = ?',
                                   (key, baseline, json.dumps(renamed, ensure_ascii=False, separators=(',', ':')), row['id']))
                keys.discard(row['selection_key'])
                keys.add(key)
    return changed


def rename_favourites(repository: Any, rename: Callable[[str, str], str], write: bool = True) -> int:
    """The favourite Bundle Report Templates and Network Insights Analysis Selections with the renamed label in their
    filters (and GAP reference); returns how many changed."""
    from src.modules import bundle_report_templates, network_insights_favourites

    def page_selection(document: Any) -> Any:
        """A Network Insights selection keeps the controls of the page by their ID (ni-operators, ni-map-operator…)."""
        if not isinstance(document, dict):
            return document
        return {**document, **{section: {key: rename_in_document(value, rename, key_kind(str(key).removeprefix('ni-')))
                                         for key, value in document[section].items()}
                               for section in ('controls', 'filters') if isinstance(document.get(section), dict)}}

    changed = 0
    for ensure, table, column, transform in (
            (bundle_report_templates.ensure_tables, bundle_report_templates.BUNDLE_REPORT_TEMPLATES_TABLE, 'definition_json',
             lambda document: rename_in_document(document, rename)),
            (network_insights_favourites.ensure_tables, network_insights_favourites.FAVOURITES_TABLE, 'selection_json',
             page_selection)):
        try:
            ensure(repository)
        except (AttributeError, sqlite3.Error):
            continue
        with repository.connection() as connection:
            for row in connection.execute(f'SELECT id, {column} FROM {table}').fetchall():
                try:
                    document = json.loads(row[column] or '{}')
                except (TypeError, ValueError):
                    continue
                renamed = transform(document)
                if renamed == document:
                    continue
                changed += 1
                if write:
                    connection.execute(f'UPDATE {table} SET {column} = ? WHERE id = ?',
                                       (json.dumps(renamed, ensure_ascii=False), row['id']))
    return changed


def count_saved_filters(repository: Any, mapping_type: str, label: str, mapping_settings: dict[str, Any]) -> int:
    """How many Reporting Jobs and saved filters use an Operator or Vendor label (nothing is changed)."""
    return rename_saved_filters(repository, mapping_type, label, f'{label}\u0000', mapping_settings, write=False)
