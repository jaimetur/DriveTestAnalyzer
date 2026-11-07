"""The tools of the AI Assistant that read what the modules show: the Summary of Scoring & GAP Analysis, the analyses of
Network Insights and the charts of the PPT Designer Designs.

Each one reads through the functions its module uses for its page (the Scoring views of a selection, the stored
analysis of Network Insights, the facts the Auto comments of PPT Designer read), so the assistant comments on the same
figures the user sees. Their results are compacted for the engine: no colours, maps or coordinates, rounded figures and
the longest lists cut.
"""
from __future__ import annotations

import math
from typing import Any

from src.modules.assistant.assistant_tools import ToolContext, ToolError, _strings

MAX_LIST_ITEMS = 15
MAX_DEPTH = 10
# What a compacted result never carries: how the page draws it, and where (maps, coordinates, geometry).
DRAWING_KEYS = frozenset({
    'colour', 'colours', 'color', 'colors', 'column_colours', 'operator_colours', 'style', 'styles', 'width', 'widths',
    'dash', 'dash_groups', 'line_widths', 'icon', 'maps', 'map', 'map_operator', 'grid', 'cells_map', 'polygons',
    'geometry', 'geojson', 'coordinates', 'latitude', 'longitude', 'lat', 'lon', 'lng', 'bounds', 'center', 'path', 'paths',
    'action_parts', 'deep_dive', 'links', 'link', 'url', 'background', 'svg', 'png', 'image', 'images', 'markers', 'shape',
})


def compact(document: Any, *, depth: int = 0, list_items: int = MAX_LIST_ITEMS, drop: frozenset[str] = DRAWING_KEYS) -> Any:
    """A result the engine can read: the drawing keys left out, the floats rounded and the lists cut (with how many
    items they had)."""
    if isinstance(document, float):
        return None if math.isnan(document) or math.isinf(document) else round(document, 2)
    if isinstance(document, dict):
        if depth >= MAX_DEPTH:
            return '…'
        return {key: compact(value, depth=depth + 1, list_items=list_items, drop=drop) for key, value in document.items()
                if str(key).casefold() not in drop and value not in (None, '', [], {})}
    if isinstance(document, (list, tuple)):
        if depth >= MAX_DEPTH:
            return f'{len(document)} items'
        items = [compact(value, depth=depth + 1, list_items=list_items, drop=drop) for value in list(document)[:list_items]]
        if len(document) > list_items:
            items.append(f'… {len(document) - list_items} more')
        return items
    return document


# -- the Summary of Scoring & GAP Analysis -------------------------------------------------------------------------------

# The parts of the Summary of the scoring that the insights detail gives, in the order of the page.
SCORING_INSIGHTS = ('campaign_scope', 'standings', 'gap_parts', 'levers', 'points_at_stake', 'campaign_comparisons',
                    'campaign_trends', 'act_plans', 'owner_cards', 'place_rankings', 'location_cards', 'location_rankings',
                    'vendor_losses', 'ran_vendor_losses', 'site_type_losses', 'sites_to_review', 'route_focus')


def _one_environment(items: list[Any]) -> list[Any]:
    """The items of All environments (Combined) when a part has them, else those of every environment."""
    combined = [item for item in items if isinstance(item, dict) and item.get('environment') == 'Combined']
    return combined or items


def _only(item: Any, only: dict[str, list[str]] | None) -> Any:
    """An item of the Summary kept to the operators ``only`` names (None when it is about another operator)."""
    names = {value.casefold() for value in (only or {}).get('Operator') or []}
    if not names or not isinstance(item, dict):
        return item
    if item.get('operator') and str(item['operator']).casefold() not in names:
        return None
    if isinstance(item.get('operators'), list):
        item = {**item, 'operators': [entry for entry in item['operators'] if not isinstance(entry, dict)
                                      or str(entry.get('operator') or '').casefold() in names]}
    return item


def scoring_insights(repository: Any, result: dict[str, Any], selection: dict[str, Any],
                     only: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """The Summary of Scoring & GAP Analysis of a calculated selection, as its page builds it: where each operator
    stands, the GAP by parts, the levers, the points at stake, the campaign comparisons and trends, and Where to act."""
    from src.modules.scoring.scoring_views import build_scoring_views

    job = {'levels': selection.get('levels') or [], 'baseline_operator': selection.get('baseline_operator') or '',
           'nr_mode': selection.get('nr_mode') or ''}
    try:
        configuration = repository.get_scoring_configuration()
    except Exception:  # noqa: BLE001 - the result carries its own configuration
        configuration = None
    try:
        views = build_scoring_views(job, result, repository.list_operator_mapping_groups(), configuration,
                                    vendor_mapping_groups=repository.list_vendor_mapping_groups())
    except ValueError as exc:
        return {'note': f'The Summary could not be built: {exc}'}
    insights = views.get('insights') or {}
    summary: dict[str, Any] = {}
    for part in SCORING_INSIGHTS:
        value = insights.get(part)
        if isinstance(value, list):
            value = [kept for item in _one_environment(value) if (kept := _only(item, only)) is not None]
        if value not in (None, '', [], {}):
            summary[part] = compact(value, list_items=10)
    summary['note'] = ('The Summary of the scoring as its page shows it, for All environments where it has them: '
                       'standings (rank, points, gap to the leader and to the reference), gap_parts (the GAP to the '
                       'reference by Data and Voice reliability and quality), levers (the KPIs that change the GAP most), '
                       'points_at_stake (the points lost by failed tests, tests below the minimum or par, and quality), '
                       'campaign comparisons and trends, and act_plans (Where to act).')
    return summary


# -- Network Insights ----------------------------------------------------------------------------------------------------

NI_GROUPS = ('operator', 'vendor', 'region', 'cluster', 'city', 'environment', 'campaign')
NI_PARTS = {
    'rf': 'the RSRP and SINR of every group (median, P10, P90, share under the coverage and interference thresholds, '
          'their classes, observed sites and cells) and its change against the previous campaign',
    'findings': 'the Key Findings: six benchmark views of the Data tests with their headlines',
    'spectrum': 'the observed and licensed spectrum of each operator',
    'bandwidth': 'the bands and bandwidths of the Data tests and their primary bandwidth ladders',
    'interactivity': 'latency and interactivity per group',
    'nr_bands': 'the NR quality of each carrier per group',
    'serving': 'the serving cells against the Network Inventories (distance, overshooting)',
}
DEFAULT_NI_PARTS = ('rf', 'findings')
# Network Insights also leaves out the curves of its charts: the figures of every group are in its tables.
NI_DROP = DRAWING_KEYS | {'charts', 'curves', 'cdf', 'points', 'series'}


def _ni_part(analysis: dict[str, Any], part: str) -> Any:
    if part == 'rf':
        return [{'technology': (section.get('overview') or [{}])[0].get('technology') if section.get('overview') else '',
                 'comparison': section.get('comparison'), 'groups': section.get('overview') or []}
                for section in analysis.get('sections') or []]
    if part == 'findings':
        findings = analysis.get('findings') or {}
        return {'campaigns': findings.get('campaigns'), 'tests': findings.get('tests'), 'groups': findings.get('groups'),
                'views': findings.get('views') or []}
    if part in {'spectrum', 'bandwidth'}:
        spectrum = analysis.get('spectrum') or {}
        if part == 'bandwidth':
            return spectrum.get('bandwidth') or {}
        return {'observed': spectrum.get('observed') or [], 'licensed': spectrum.get('licensed') or []}
    return analysis.get(part)


def network_insights(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    reader = context.services.get('network_insights')
    if reader is None:
        raise ToolError('Network Insights is not available in this workspace.')
    parts = [value.casefold() for value in _strings(arguments.get('parts'))] or list(DEFAULT_NI_PARTS)
    unknown = [part for part in parts if part not in NI_PARTS]
    if unknown:
        raise ToolError(f'parts takes {", ".join(NI_PARTS)}.')
    groups = [value.casefold() for value in _strings(arguments.get('group'))] or ['operator', 'campaign']
    if any(group not in NI_GROUPS for group in groups):
        raise ToolError(f'group takes {", ".join(NI_GROUPS)}.')
    technology = str(arguments.get('technology') or 'lte_nr').strip().casefold().replace('+', '_')
    if technology not in {'lte', 'nr', 'lte_nr'}:
        raise ToolError('technology is lte, nr or lte_nr.')
    nr_mode = str(arguments.get('nr_mode') or 'NSA').strip().upper()
    if nr_mode not in {'NSA', 'SA'}:
        raise ToolError('nr_mode is NSA or SA.')
    campaigns = [{'latest': '@latest-campaign', 'previous': '@previous-campaign'}.get(value.casefold(), value)
                 for value in _strings(arguments.get('campaigns'))] or ['@latest-campaign']
    selection = {'nr_mode': nr_mode, 'technology': technology, 'group': groups, 'campaigns': campaigns,
                 **{field: _strings(arguments.get(field)) for field in ('operators', 'vendors', 'regions', 'clusters', 'cities',
                                                                         'environments') if _strings(arguments.get(field))}}
    context.progress('Analysing the network (Network Insights)')
    try:
        read = reader(selection)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    analysis = read['analysis']
    chosen = read['selection']
    found: dict[str, Any] = {
        'selection': {key: chosen.get(key) for key in ('nr_mode', 'technology', 'group', 'campaigns', 'operators', 'vendors',
                                                       'regions', 'clusters', 'cities', 'environments') if chosen.get(key)},
        'cdrs': sum(len(ids) for ids in (chosen.get('datasets') or {}).values()),
        'group_label': analysis.get('group_label'), 'technology': analysis.get('technology_label'),
    }
    for part in parts:
        found[part] = compact(_ni_part(analysis, part), list_items=12, drop=NI_DROP)
    if analysis.get('warnings'):
        found['warnings'] = analysis['warnings'][:8]
    if analysis.get('missing_inventory_operators'):
        found['operators_without_inventory'] = analysis['missing_inventory_operators']
    found['parts_available'] = {part: text for part, text in NI_PARTS.items() if part not in parts}
    return found


# -- PPT Designer ----------------------------------------------------------------------------------------------------------

MAX_DESIGN_SLIDES = 4


def ppt_designs(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    outline = context.services.get('design_outline')
    if outline is None:
        raise ToolError('PPT Designer is not available in this workspace.')
    design = str(arguments.get('design') or '').strip()
    try:
        found = outline(design or None)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    if not design:
        found['note'] = 'The Designs in the order of the library (the first one is the first Design).'
    else:
        found['note'] = 'Every slide with its charts; read the facts of the charts of some slides with ppt_design_charts.'
    return compact(found, list_items=60)


def ppt_design_charts(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    reader = context.services.get('design_charts')
    if reader is None:
        raise ToolError('PPT Designer is not available in this workspace.')
    design = str(arguments.get('design') or '').strip()
    if not design:
        raise ToolError('design is the id or the name of a Design (see ppt_designs).')
    slides = []
    for value in arguments.get('slides') or []:
        try:
            slides.append(int(value))
        except (TypeError, ValueError) as exc:
            raise ToolError('slides lists slide numbers.') from exc
    if not slides:
        raise ToolError('slides lists the numbers of the slides to read (see ppt_designs), at most '
                        f'{MAX_DESIGN_SLIDES}.')
    if len(slides) > MAX_DESIGN_SLIDES:
        raise ToolError(f'Read at most {MAX_DESIGN_SLIDES} slides at a time.')
    context.progress('Preparing the Design and its charts (PPT Designer)')
    try:
        found = reader(design, slides)
    except (ValueError, RuntimeError) as exc:
        raise ToolError(str(exc)) from exc
    found['note'] = ('The facts of each chart as the Auto comments of PPT Designer read them: each record is a group of '
                     'the chart (its labels) with its value, samples and how the comments write it ("shown"); '
                     '"better" says whether higher or lower is better; rules_comments are the comments the rules write '
                     'for the slide.')
    return compact(found, list_items=40)
