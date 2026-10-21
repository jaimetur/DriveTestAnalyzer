"""The panels of Scoring & GAP Analysis that its PowerPoint and Word documents can include, and the operators each one
exports: every operator, or the Focus operators of the Operator Maps (see operator_roles).

Each workspace chooses them in Workspace Config (Scoring Export Panels): a panel that is not Exportable is left out of
every Scoring document (the Saved Filter exports, the scoring reports, Reporting Jobs and Bundle Report Templates) and
of the editors of their content. A document can still show every operator in the Focus Operators panels (``Export All
Operators in Focus panels``). The settings travel as the Scoring Export Panels element of Import / Export, transfers and
backups.
"""
from __future__ import annotations

import copy
import json
from typing import Any

EXPORT_PANELS_STATE_KEY = 'scoring_export_panels'
EXPORT_PANELS_FORMAT = 'drivetest-analyzer-scoring-export-panels'
EXPORT_PANELS_VERSION = 1
ALL_OPERATORS = 'all'
FOCUS_OPERATORS = 'focus'
OPERATOR_MODES = ((ALL_OPERATORS, 'All Operators'), (FOCUS_OPERATORS, 'Focus Operators'))
# The panels of each results tab, in the order of the page, with the operators they export by default.
EXPORT_PANELS: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...] = (
    ('summary', 'Summary', (
        ('scope', 'How the measurements ran', ALL_OPERATORS),
        ('act', 'Where to act', FOCUS_OPERATORS),
        ('owners', 'Where to act, by performance owner', FOCUS_OPERATORS),
        ('standings', 'Standings: where each operator stands', ALL_OPERATORS),
        ('position', 'Position per environment and service', ALL_OPERATORS),
        ('levers', 'Biggest levers against the reference', FOCUS_OPERATORS),
        ('places', 'Cities, Towns, Roads and Railways ranked', FOCUS_OPERATORS),
        ('route', 'The route that loses most: where the points are', FOCUS_OPERATORS))),
    ('charts', 'Scoring Charts', (
        ('service', 'Scoring per Service', ALL_OPERATORS),
        ('category', 'Scoring per Category', ALL_OPERATORS),
        ('breakdown', 'Scoring per Category (Breakdown)', ALL_OPERATORS))),
    ('tables', 'Scoring Tables', (
        ('summary', 'Category table', ALL_OPERATORS),
        ('breakdown', 'Breakdown table', ALL_OPERATORS),
        ('campaign_comparison', 'Campaign comparison (two latest campaigns)', FOCUS_OPERATORS))),
    ('geographical_areas', 'Geographical Areas', (
        ('cards', 'Scoring Nationwide and per City / Cluster / Region cards', ALL_OPERATORS),
        ('ranking', 'Geographical Areas ranked', FOCUS_OPERATORS),
        ('versus', 'Each operator against the reference per geographical area', FOCUS_OPERATORS))),
    ('trends', 'Scoring Trends', (
        ('trend', 'Scoring Trend (two campaigns or more)', ALL_OPERATORS),
        ('areas', 'National & Geographical Areas Trends', ALL_OPERATORS))),
    ('gap', 'GAP Analysis', (
        ('all_operators', 'Table comparing all the chosen operators', ALL_OPERATORS),
        ('individual', 'Individual tables against the reference', FOCUS_OPERATORS),
        ('parts', 'GAP by part over the campaigns', FOCUS_OPERATORS),
        ('profile', 'KPI GAP Profile', FOCUS_OPERATORS))),
    ('points', 'Points Lost', (
        ('stake', 'Where the points go', ALL_OPERATORS),
        ('kpis', 'Points lost per KPI', FOCUS_OPERATORS),
        ('map', 'Points lost per City / Region map, by points and per 1,000 tests', FOCUS_OPERATORS),
        ('vendors', 'Points lost per Vendor', FOCUS_OPERATORS),
        ('site_types', 'Points lost per kind of site', FOCUS_OPERATORS),
        ('sites', 'Sites to review', FOCUS_OPERATORS),
        ('stretches', 'Route stretches', FOCUS_OPERATORS))),
)


def default_export_panels() -> dict[str, dict[str, dict[str, Any]]]:
    """Every panel exportable, with the operators of its default."""
    return {group: {key: {'exportable': True, 'operators': mode} for key, _label, mode in panels}
            for group, _title, panels in EXPORT_PANELS}


def normalize_export_panels(raw: Any) -> dict[str, dict[str, dict[str, Any]]]:
    """The settings of every panel; panels and values it lacks (or does not know) take their default."""
    panels = default_export_panels()
    raw = raw.get('panels', raw) if isinstance(raw, dict) else {}
    for group, values in panels.items():
        supplied = raw.get(group) if isinstance(raw.get(group), dict) else {}
        for key, setting in values.items():
            item = supplied.get(key) if isinstance(supplied.get(key), dict) else {}
            if 'exportable' in item:
                setting['exportable'] = bool(item['exportable'])
            if item.get('operators') in {ALL_OPERATORS, FOCUS_OPERATORS}:
                setting['operators'] = item['operators']
    return panels


def export_panels_document(panels: Any) -> dict[str, Any]:
    """The portable form of the settings: the Scoring Export Panels element of Import / Export, transfers and backups."""
    return {'format': EXPORT_PANELS_FORMAT, 'version': EXPORT_PANELS_VERSION, 'panels': normalize_export_panels(panels)}


def unwrap_export_panels_document(document: Any) -> dict[str, dict[str, dict[str, Any]]]:
    if not isinstance(document, dict) or document.get('format') != EXPORT_PANELS_FORMAT:
        raise ValueError('This file is not a Scoring Export Panels document.')
    if document.get('version') != EXPORT_PANELS_VERSION:
        raise ValueError('Unsupported Scoring Export Panels version.')
    if not isinstance(document.get('panels'), dict):
        raise ValueError('The Scoring Export Panels document has no panels.')
    return normalize_export_panels(document['panels'])


def load_export_panels(repository) -> dict[str, dict[str, dict[str, Any]]]:
    raw = repository.get_workspace_state(EXPORT_PANELS_STATE_KEY)
    if not raw:
        return default_export_panels()
    try:
        return normalize_export_panels(json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default_export_panels()


def save_export_panels(repository, raw: Any) -> dict[str, dict[str, dict[str, Any]]]:
    panels = normalize_export_panels(raw)
    repository.set_workspace_state(EXPORT_PANELS_STATE_KEY, json.dumps({'panels': panels}, separators=(',', ':')))
    return panels


def export_panel_catalogue(panels: Any = None) -> list[dict[str, Any]]:
    """The panels of each tab with their labels, default and current settings (for Workspace Config and the editors)."""
    current = normalize_export_panels(panels)
    return [{'key': group, 'title': title, 'panels': [
        {'key': key, 'label': label, 'default': mode, **copy.deepcopy(current[group][key])}
        for key, label, mode in items]} for group, title, items in EXPORT_PANELS]


def export_panel_changes(before: Any, after: Any) -> list[str]:
    """The panels whose settings changed, as App Events describe them."""
    old, new = normalize_export_panels(before), normalize_export_panels(after)
    labels = {(group, key): f'{title} > {label}' for group, title, items in EXPORT_PANELS for key, label, _mode in items}
    names = dict(OPERATOR_MODES)
    changes = []
    for (group, key), label in labels.items():
        was, now = old[group][key], new[group][key]
        if was['exportable'] != now['exportable']:
            changes.append(f"{label}: {'exportable' if now['exportable'] else 'not exportable'}")
        if was['operators'] != now['operators']:
            changes.append(f"{label}: {names[now['operators']]}")
    return changes


def exportable_options(options: dict | None, panels: Any) -> dict | None:
    """The content options of a scoring with the panels that are not exportable left out; None (every panel) stays None
    when every panel is exportable."""
    from src.modules.scoring_exports import _option

    panels = normalize_export_panels(panels)
    if options is None and all(setting['exportable'] for values in panels.values() for setting in values.values()):
        return None
    merged = copy.deepcopy(options) if isinstance(options, dict) else {}
    for group, values in panels.items():
        merged[group] = {**(merged.get(group) if isinstance(merged.get(group), dict) else {}),
                         **{key: _option(options, group, key) and setting['exportable'] for key, setting in values.items()}}
    return merged
