"""PowerPoint and Word summaries of a Network Insights analysis."""
from __future__ import annotations

import re
from collections.abc import Callable
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Inches as DocxInches, Pt as DocxPt, RGBColor as DocxRGBColor
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from PIL import Image
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx import Presentation
from pptx.util import Inches, Pt

from src.modules.exports import MUTED, ORANGE, _add_textbox
from src.utils.fonts import load_image_font

# Renders a Canvas chart model to PNG bytes at the requested pixel size.
ChartRenderer = Callable[[dict[str, Any], int, int], bytes]

TABLE_ROWS_PER_SLIDE = 12


def _number(value: Any, digits: int = 1, suffix: str = '') -> str:
    if value is None or value == '':
        return '—'
    if isinstance(value, (int, float)):
        return f'{value:,.{digits}f}{suffix}' if isinstance(value, float) else f'{value:,}{suffix}'
    return str(value)


def _signed(value: Any, suffix: str = '') -> str:
    return '—' if value is None else f'{value:+.1f}{suffix}'


def summary_selection_lines(selection: dict[str, Any]) -> list[str]:
    """Readable lines describing the analysed CDRs, grouping and filters."""
    lines = [
        *([f"NR Mode: {selection['nr_mode']}"] if selection.get('nr_mode') else []),
        f"Technology: {selection.get('technology_label') or selection.get('technology') or 'LTE'}",
        f"Grouping: {selection.get('group_label') or 'Operator → Campaign'}",
    ]
    technology = selection.get('technology') or 'lte'
    for radio, label, coverage, interference in (('lte', 'LTE', 'coverage_threshold', 'interference_threshold'),
                                                  ('nr', 'NR', 'nr_coverage_threshold', 'nr_interference_threshold')):
        if technology in {radio, 'lte_nr'} and selection.get(coverage) is not None:
            lines.append(f"{label} thresholds: low coverage below {selection.get(coverage)} dBm RSRP, "
                         f"high interference below {selection.get(interference)} dB SINR")
    for label, key in (('Operators', 'operators'), ('Operator_Vendor', 'operator_vendors'), ('Vendors', 'vendors'),
                       ('Campaigns', 'campaigns'), ('Regions', 'regions'), ('Clusters', 'clusters'), ('Cities', 'cities'),
                       ('Environments', 'environments')):
        values = selection.get(key) or []
        lines.append(f"{label}: {', '.join(values) if values else 'All'}")
    datasets = selection.get('dataset_names') or []
    lines.append(f"CDRs ({len(datasets)}): {', '.join(datasets) if datasets else 'All ready CDRs'}")
    return lines


def scope_labels(selection: dict[str, Any] | None, environments: bool = True) -> list[str]:
    """The area, operators, vendors and (when chosen) environments a chart or table shows, as the pills of the page: the
    City, Cluster or Region filters, the most specific first, else National; All Operators and All Vendors without a
    filter. A long list keeps its first two names and counts the others."""
    selection = selection or {}

    def values(key: str) -> list[str]:
        return list(dict.fromkeys(str(value).strip() for value in selection.get(key) or [] if str(value or '').strip()))

    def label(items: list[str], level: str, plural: str) -> str:
        shown = [*items[:2], f'{len(items) - 2} more'] if len(items) > 3 else items
        names = f"{', '.join(shown[:-1])} & {shown[-1]}" if len(shown) > 1 else shown[0]
        return f'{plural if len(items) > 1 else level}: {names}'

    area = next((label(values(key), level, plural) for key, level, plural in
                 (('cities', 'City', 'Cities'), ('clusters', 'Cluster', 'Clusters'), ('regions', 'Region', 'Regions')) if values(key)), 'National')
    labels = [area, label(values('operators'), 'Operator', 'Operators') if values('operators') else 'All Operators',
              label(values('vendors'), 'Vendor', 'Vendors') if values('vendors') else 'All Vendors']
    if environments and values('environments'):
        labels.append(label(values('environments'), 'Environment', 'Environments'))
    return labels


def scope_text(selection: dict[str, Any] | None, environments: bool = True) -> str:
    return ' · '.join(scope_labels(selection, environments))


# The tables of the whole inventory (no filter) and of the inventory after the selection's filters (no environment).
WHOLE_INVENTORY_TITLES = ('Network Snapshot', 'Network Deployment', 'Cluster Sites Density · Inventory', 'Licensed Spectrum',
                          'Spectrum · Deployed')
FILTERED_INVENTORY_TITLES = ('Spectrum · NR sites by duplex mode',)


def scope_for(title: str, selection: dict[str, Any] | None) -> str:
    """The scope named under a slide or section title: the filters of the analysis for the measurements, those that
    describe the inventory for the NR sites by duplex mode, and none for the panels of the whole inventory."""
    if title.startswith(WHOLE_INVENTORY_TITLES):
        return scope_text({}, environments=False)
    return scope_text(selection, environments=not title.startswith(FILTERED_INVENTORY_TITLES))


def technology_sections(analysis: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(title suffix, section) per technology; LTE+NR exports LTE and NR separately."""
    sections = analysis.get('sections') or [analysis]
    if len(sections) == 1:
        return [('', sections[0])]
    return [(f" · {section.get('technology_label') or section.get('technology')}", section) for section in sections]


def hotspot_table(rows: list[dict[str, Any]], unit: str, limit: int = 10) -> tuple[list[str], list[list[str]]]:
    columns = ['City', 'Region', 'Samples', f'Mean ({unit})', 'Share below threshold', 'Latitude', 'Longitude']
    return columns, [
        [row.get('city') or '—', row.get('region') or '—', _number(row.get('samples'), 0), _number(row.get('mean')),
         _number(row.get('bad_share'), suffix='%'), f"{row.get('latitude')}", f"{row.get('longitude')}"]
        for row in rows[:limit]
    ]


def spectrum_tables(analysis: dict[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    spectrum = analysis.get('spectrum') or {}
    observed = [
        [row.get('operator') or '', row.get('technology') or '', row.get('band') or '', row.get('band_class') or '',
         _number(row.get('share'), suffix='%'), _number(row.get('samples'), 0), _number(row.get('typical_bandwidth_mhz'), 0, ' MHz')]
        for row in spectrum.get('observed') or []
    ]
    licensed = [
        [row.get('operator') or '', _number(row.get('Low')), _number(row.get('Mid')), _number(row.get('High (TDD)')), _number(row.get('total'))]
        for row in spectrum.get('licensed') or []
    ]
    tables = []
    if observed:
        tables.append(('Observed Spectrum', ['Group', 'Technology', 'Band', 'Class', 'Share', 'Samples', 'Typical bandwidth'], observed))
    if licensed:
        tables.append(('Licensed Spectrum (MHz)', ['Operator', 'Low', 'Mid', 'High (TDD)', 'Total'], licensed))
    return tables


def _bandwidth_view(analysis: dict[str, Any], scope: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    bandwidth = (analysis.get('spectrum') or {}).get('bandwidth') or {}
    view = (bandwidth.get('scopes') or {}).get(scope) or {}
    return bandwidth, view, str((bandwidth.get('scope_labels') or {}).get(scope) or scope)


def _megahertz(value: Any) -> str:
    return f'{float(value):g} MHz'


def bandwidth_tables(analysis: dict[str, Any], scope: str = 'download') -> list[tuple[str, list[str], list[list[str]]]]:
    """Bandwidth per band and total bandwidth (LTE + 5G) per group and environment, as on the page."""
    bandwidth, view, label = _bandwidth_view(analysis, scope)
    group = analysis.get('group_label') or 'Group'
    tables = []
    bands = view.get('bands') or []
    widths = sorted({width for row in bands for width in row.get('bandwidths') or {}}, key=float)
    rows = [[row['operator'], row['technology'], row['band'], row.get('duplex') or '—', _number(row['samples'], 0),
             *[(f"{row['bandwidths'][width]:,} ({row['bandwidths'][width] / row['samples'] * 100:.0f}%)"
                if row['bandwidths'].get(width) else '—') for width in widths],
             _number(row['unknown'], 0) if row.get('unknown') else '—',
             _megahertz(row['typical_bandwidth_mhz']) if row.get('typical_bandwidth_mhz') else '—'] for row in bands]
    if rows:
        tables.append((f'Spectrum · Bandwidth per band ({label})',
                       [group, 'Technology', 'Band', 'Duplex', 'Samples', *[_megahertz(width) for width in widths], 'Unknown', 'Typical'], rows))
    classes = bandwidth.get('classes') or []
    ladders = view.get('ladders') or {}
    rows = [[cell['column'], cell['environment'], _number(cell['known'], 0), *[_number(share, 1, '%') for share in cell['shares']],
             _number(cell.get('wide_share'), 1, '%'), _number(cell['narrow_share'], 1, '%'),
             _megahertz(cell['median_mhz']) if cell.get('median_mhz') is not None else '—']
            for cell in ladders.get('cells') or [] if cell.get('known')]
    if rows:
        tables.append((f'Spectrum · Total bandwidth, LTE and 5G ({label})',
                       [bandwidth.get('column_label') or 'Group', 'Environment', 'Tests', *[item['label'] for item in classes],
                        f"At {bandwidth.get('wide_from_mhz', 100):g} MHz+", f"Below {bandwidth.get('narrow_below_mhz', 25):g} MHz", 'Median'], rows))
    return tables


def bandwidth_title(analysis: dict[str, Any]) -> str:
    """The title of the total bandwidth chart, as on the page."""
    return str((_bandwidth_view(analysis, 'download')[0]).get('title') or 'Total bandwidth: LTE and 5G together')


def bandwidth_caption(analysis: dict[str, Any], scope: str = 'download') -> str:
    """The line under the title of the total bandwidth ladders, as on the page: what the ladders and their number show and
    the group with the most tests under 25 MHz in each environment."""
    bandwidth, view, _label = _bandwidth_view(analysis, scope)
    narrow = f"{bandwidth.get('narrow_below_mhz', 25):g}"
    tests = 'download tests' if scope == 'download' else 'CDR Data tests'
    highlights = (view.get('ladders') or {}).get('highlights') or []
    wide = f"{bandwidth.get('wide_from_mhz', 100):g}"
    text = (f'Each ladder splits the {tests} with a known bandwidth by their total width (LTE + 5G), widest at the bottom; '
            f'the number beside it is the share under {narrow} MHz (dark red) and the one below it the share at {wide} MHz or more.')
    if highlights:
        text += f" Most under {narrow} MHz: " + '; '.join(
            f"{item['environment']}, {item['column']} ({item['narrow_share']:.0f}%)" for item in highlights) + '.'
    return text


def bandwidth_ladder_image(analysis: dict[str, Any], scope: str = 'download') -> BytesIO | None:
    """The total bandwidth ladders of the page as a PNG: per group (column) and environment (row), one block per
    bandwidth class, widest at the bottom, as wide as the class midpoint and as tall as its share of the tests."""
    from PIL import ImageDraw

    bandwidth, view, _label = _bandwidth_view(analysis, scope)
    ladders = view.get('ladders') or {}
    cells = {(cell['column'], cell['environment']): cell for cell in ladders.get('cells') or []}
    if not any(cell.get('known') for cell in cells.values()):
        return None
    classes = bandwidth.get('classes') or []
    columns, rows = ladders.get('columns') or [], ladders.get('environments') or []
    label_width, column_width, header, row_height, legend_height = 340, 420, 80, 360, 112
    title_font, text_font, small_font = load_image_font(30, bold=True), load_image_font(28, bold=True), load_image_font(26)
    figure_font, wide_font = load_image_font(21, bold=True), load_image_font(21)
    wide = f"{bandwidth.get('wide_from_mhz', 100):g}"
    widest = max(item['width'] for item in classes)
    # The legend flows over as many lines as the chart width needs (at least 1,400 px wide).
    width = int(max(label_width + len(columns) * column_width, 1400))
    legend, cursor, line = [], label_width, 0
    for item in classes:
        size = small_font.getlength(item['label']) if hasattr(small_font, 'getlength') else 12 * len(item['label'])
        if cursor + size + 44 > width - 24 and cursor > label_width:
            cursor, line = label_width, line + 1
        legend.append((item, cursor, line))
        cursor += size + 76
    height = header + len(rows) * row_height + legend_height + line * 48
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    for index, column in enumerate(columns):
        centre = label_width + index * column_width + column_width / 2
        draw.text((centre, header - 28), str(column), fill=bandwidth.get('column_colours', {}).get(column) or '#312E81',
                  font=title_font, anchor='ms')
    for row_index, row in enumerate(rows):
        top = header + row_index * row_height
        base, plot = top + row_height - 64, row_height - 110
        # The largest share at 100 MHz or more of the row is in bold, as in benchmark slides.
        known = [cells[(column, row)] for column in columns if cells.get((column, row), {}).get('known')]
        most_wide = max((cell.get('wide_share') or 0 for cell in known), default=None) if len(known) > 1 else None
        draw.text((24, top + row_height / 2), str(row), fill='#1F2433', font=text_font, anchor='lm')
        if row_index:
            draw.line([(0, top), (width, top)], fill='#EEF0FF', width=4)
        for index, column in enumerate(columns):
            centre = label_width + index * column_width + column_width / 2
            span = column_width - 56
            draw.line([(centre - span / 2, base), (centre + span / 2, base)], fill='#C7CBF7', width=2)
            cell = cells.get((column, row))
            if not cell or not cell.get('known'):
                draw.text((centre, base - 24), 'No bandwidth' if cell else 'No tests', fill='#8A8FB5', font=small_font, anchor='ms')
                continue
            # The figure stands right of the narrow blocks (up to 40–59 MHz), level with the top of the ladder.
            cursor, narrow_top = float(base), float(base)
            narrow_right = centre + classes[-3]['width'] / widest * span / 2 if len(classes) >= 3 else centre
            for class_index, item in enumerate(classes):
                block_width = item['width'] / widest * span
                block_height = cell['shares'][class_index] / 100 * plot
                cursor -= block_height
                if class_index == len(classes) - 1:
                    narrow_top = cursor
                if block_height > 0:
                    draw.rectangle([(centre - block_width / 2, cursor), (centre + block_width / 2, cursor + block_height)], fill=item['colour'])
            draw.text((narrow_right + 10, narrow_top), f"{cell['narrow_share']:.0f}%", fill='#1F2433', font=figure_font, anchor='lt')
            is_most = most_wide is not None and (cell.get('wide_share') or 0) == most_wide
            draw.text((centre, base + 34), f"{cell.get('wide_share') or 0:.0f}% at {wide} MHz+", fill='#1F2433' if is_most else '#3B4060',
                      font=figure_font if is_most else wide_font, anchor='mm')
    legend_top = header + len(rows) * row_height + 44
    draw.text((24, legend_top), 'Width, MHz (LTE + 5G)', fill='#1F2433', font=text_font, anchor='lm')
    for item, left, line in legend:
        top = legend_top + line * 48
        draw.rectangle([(left, top - 16), (left + 32, top + 16)], fill=item['colour'])
        draw.text((left + 44, top), item['label'], fill='#3B4060', font=small_font, anchor='lm')
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


def nr_duplex_table(deployment: dict[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    """The NR sites by duplex mode of the inventory snapshot, logical and physical."""
    payload = deployment.get('nr_duplex') or {}
    rows = [[row['operator'], *[_number(row[key], 0) for key in ('sites', 'tdd_sites', 'fdd_sites', 'both_sites', 'tdd_only_sites',
                                                                  'fdd_only_sites', 'physical_sites', 'physical_tdd_sites', 'physical_fdd_sites')]]
            for row in payload.get('rows') or []]
    if not rows:
        return []
    radius = _number(payload.get('radius_m'), 0)
    return [('Spectrum · NR sites by duplex mode', ['Network', 'Sites with NR', 'NR TDD', 'NR FDD', 'TDD and FDD', 'TDD only', 'FDD only',
                                                   f'Physical sites (within {radius} m)', 'Physical NR TDD', 'Physical NR FDD'], rows)]


def deployment_tables(deployment: dict[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    if 'groupings' in deployment:
        return [table for grouping in deployment['groupings'] for table in deployment_tables(grouping)]
    tables = []
    for inventory in deployment.get('inventories') or []:
        rows = [[row['group'], _number(row['sites'], 0), _number(row['cells'], 0)] for row in inventory.get('rows') or []]
        totals = inventory.get('totals') or {}
        if totals:
            rows.append(['Total', _number(totals.get('sites'), 0), _number(totals.get('cells'), 0)])
        if rows:
            tables.append((f"Network Deployment · {deployment.get('group_label') or 'All'} · {inventory.get('operator')} ({inventory.get('file_name')})",
                           [deployment.get('group_label') or 'Group', 'Sites', 'Cells'], rows))
    return tables


def cluster_sites_tables(analysis: dict[str, Any], deployment: dict[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    """Export both data sources independently of the panel's selected view."""
    observed = [[row.get('operator') or '', _number(row.get('observed_enodebs'), 0),
                 _number(row.get('observed_cells'), 0), _number(row.get('samples'), 0),
                 _number(row['samples'] / row['observed_enodebs']) if row.get('observed_enodebs') else '—']
                for _suffix, section in technology_sections(analysis) for row in _labelled_rows(analysis, section)]
    inventory = [[row['operator'], _number(row['sites'], 0), _number(row['cells'], 0)]
                 for row in (deployment.get('cluster_inventories') or {}).get('rows') or []]
    tables = []
    if observed:
        tables.append(('Cluster Sites Density · Observed Sites/Cells',
                       ['Group', 'Observed eNodeBs', 'Observed cells', 'Samples', 'Samples per eNodeB'], observed))
    if inventory:
        tables.append(('Cluster Sites Density · Inventory Sites/Cells',
                       ['Operator', 'Inventory sites', 'Inventory cells'], inventory))
    return tables


def serving_tables(analysis: dict[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    """Serving Cells and 5G Availability, as on the page."""
    serving = analysis.get('serving') or {}
    if not serving:
        return []
    group = analysis.get('group_label') or 'Group'
    overshoot = _number(serving.get('overshoot_km'))
    tables = [('Serving Cells · Distance and overshooting', [group, 'Samples', 'Serving cell found', 'Median km', 'P90 km', f'Overshooting > {overshoot} km', 'Hosted by another network'],
               [[row['operator'], _number(row['samples'], 0), _number(row['matched_share'], 1, '%'), _number(row['median_km'], 2),
                 _number(row['p90_km'], 2), _number(row['overshoot_share'], 1, '%'), _number(row['hosted_elsewhere_share'], 1, '%')]
                for row in serving.get('summary') or []])]
    for key, title, label in (('by_band', 'By serving band', 'Band'), ('by_vendor', 'By RAN vendor', 'Vendor'),
                              ('by_network', 'By serving network', 'Serving Network'), ('by_host', 'By host network', 'Host Network')):
        rows = [[row['operator'], row['value'], _number(row['samples'], 0), _number(row['median_km'], 2), _number(row['overshoot_share'], 1, '%')]
                for row in serving.get(key) or []]
        if rows:
            tables.append((f'Serving Cells · {title}', [group, label, 'Samples', 'Median km', 'Overshooting'], rows))
    cells = [[row['operator'], row['cell'], row['site'], row['band'], row['vendor'], f"{row['network']} → {row['host']}",
              _number(row['samples_beyond'], 0), _number(row['samples'], 0), _number(row['median_km'], 2), _number(row['max_km'], 2)]
             for row in serving.get('overshooting_cells') or []]
    if cells:
        tables.append(('Serving Cells · Overshooting cells', [group, 'Cell', 'Site', 'Band', 'Vendor', 'Network → Host', 'Samples beyond',
                                                               'Samples served', 'Median km', 'Max km'], cells))
    leg = serving.get('nr_leg') or {}
    rows = [[row['operator'], _number(row['with_nr_pci'], 0), _number(row['found_share'], 1, '%'), _number(row['anchor_site_share'], 1, '%'),
             _number(row['only_candidate_share'], 1, '%'), _number(row['nearest_share'], 1, '%'), _number(row['median_km'], 2),
             _number(row['p90_km'], 2), ', '.join(f"{item['vendor']} {_number(item['share'], 0, '%')}" for item in row.get('vendors') or []) or '—']
            for row in leg.get('rows') or []]
    if rows:
        tables.append(('Serving Cells · NR cell of the NSA samples', [group, 'Samples with NR PCI', 'NR cell found', 'On the anchor site',
                                                                      'Only candidate nearby', 'Nearest of several', 'Median km', 'P90 km',
                                                                      'NR vendors'], rows))
    rows = [[row['operator'], row['value'], _number(row['samples'], 0), _number(row['median_km'], 2), _number(row['overshoot_share'], 1, '%')]
            for row in leg.get('by_vendor') or []]
    if rows:
        tables.append(('Serving Cells · By NR vendor (NSA)', [group, 'NR vendor', 'Samples', 'Median km', 'Overshooting'], rows))
    rows = [[row['operator'], row['technology'], row['mimo'], ', '.join(row.get('modes') or []) or '—',
             _number(row['samples'], 0), _number(row['mean_rank'], 2), _number(row['rank2_share'], 1, '%'),
             _number(row['mean_layers'], 2), _number(row['rank_use'], 1, '%')] for row in serving.get('mimo') or []]
    if rows:
        tables.append(('Serving Cells · MIMO: inventory TX antennas and reported rank', [group, 'Technology', 'TX antennas', 'Inventory field',
                                                                                         'Samples', 'Mean rank', 'Rank 2+', 'Mean max layers',
                                                                                         'Rank use'], rows))
    nr = serving.get('nr_availability') or {}
    leg_columns = any('nr_found_share' in row for row in nr.get('rows') or [])
    rows = [[row['operator'], _number(row['anchored'], 0), _number(row['on_nr_sites'], 0), _number(row['without_nr_on_nr_sites'], 0),
             _number(row['gap_share'], 1, '%'), _number(row['without_nr_elsewhere_share'], 1, '%'),
             *([_number(row.get('nr_found_share'), 1, '%'), _number(row.get('nr_on_anchor_share'), 1, '%'), _number(row.get('nr_median_km'), 2)]
               if leg_columns else [])] for row in nr.get('rows') or []]
    if rows:
        tables.append(('5G Availability', [group, 'Samples on LTE cells', 'On sites with NR', 'Without NR there', 'NR gap on 5G sites',
                                           'Without NR on other sites', *(['NR cell found', 'NR on the anchor site', 'Median km to the NR site']
                                                                          if leg_columns else [])], rows))
    sites = [[row['operator'], row['site'], row['vendor'], _number(row['samples_without_nr'], 0), _number(row['samples'], 0)]
             for row in nr.get('sites') or []]
    if sites:
        tables.append(('5G Availability · Sites with the most samples without NR', [group, 'Site', 'Vendor', 'Samples without NR', 'Samples anchored'], sites))
    sites = [[row['operator'], row['site'], row['vendor'], _number(row['samples'], 0), _number(row['from_anchor_share'], 1, '%'),
              _number(row['median_km'], 2)] for row in nr.get('nr_sites') or []]
    if sites:
        tables.append(('5G Availability · NR sites serving the most NSA samples', [group, 'NR site', 'Vendor', 'Samples', 'From the anchor site',
                                                                                   'Median km'], sites))
    return tables


def cell_status_tables(analysis: dict[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    """The flagged cells of the inventory snapshot around the weak areas of every technology section and group."""
    tables = []
    for suffix, section in technology_sections(analysis):
        maps = section.get('maps') or {}
        for group in maps.get('groups') or [maps]:
            status = group.get('cell_status') or {}
            rows = [[row['site'], f"{row['network']} → {row['host']}", row['vendor'], row['summary'], 'Yes' if row['on_air'] else 'No',
                     f"{str(row['area_kind']).title()} · {row['area']}", _number(row['distance_km'], 2)] for row in status.get('rows') or []]
            if rows:
                name = str(group.get('operator') or '')
                tables.append((f'Cell status near the weak areas{suffix}' + (f' · {name}' if name else ''),
                               ['Site', 'Network → Host', 'Vendor', 'Flagged cells', 'On air', 'Nearest weak area', 'Distance km'], rows))
    return tables


def serving_visuals(analysis: dict[str, Any], render: ChartRenderer) -> list[tuple[str, BytesIO | None, str, Any]]:
    serving = analysis.get('serving') or {}
    if not serving or not serving.get('distance_cdf'):
        return []
    image, note = _render_image(render, serving['distance_cdf'])
    return [('Distance to the serving site', image, note, None)]


def snapshot_tables(deployment: dict[str, Any]) -> list[tuple[str, list[str], list[list[str]]]]:
    """Network Snapshot, deployed spectrum and density of the inventory snapshot."""
    snapshot = deployment.get('snapshot') or {}
    if not snapshot.get('selection'):
        return []
    tables = [('Network Snapshot', ['Network', 'Snapshot date', 'Inventory', 'Sites', 'Cells', 'LTE cells', 'NR cells'],
               [[item['operator'], item['snapshot_date'], item['file_name'], _number(item['sites'], 0), _number(item['cells'], 0),
                 _number((item.get('technologies') or {}).get('LTE'), 0), _number((item.get('technologies') or {}).get('NR'), 0)]
                for item in snapshot['selection']])]
    matrix = snapshot.get('host_matrix') or {}
    if matrix.get('owners'):
        tables.append(('Network Snapshot · Owner network × host network (in-service cells)', ['Owner \\ Host', *matrix['hosts']],
                       [[owner, *[_number(matrix['cells'].get(f'{owner}|{host}'), 0) if matrix['cells'].get(f'{owner}|{host}') else '—'
                                  for host in matrix['hosts']]] for owner in matrix['owners']]))
    quality = [[row['operator'], _number(row['cells'], 0), _number(row['not_in_service'], 0), _number(row['locked_or_disabled'], 0),
                _number(row['without_position'], 0), _number(row['without_azimuth'], 0), _number(row['without_band'], 0),
                _number(row['without_vendor'], 0), _number(row['duplicate_identities'], 0)] for row in snapshot.get('quality') or []]
    if quality:
        tables.append(('Network Snapshot · Inventory quality', ['Network', 'Cells', 'Not in service', 'Locked / disabled', 'Without position',
                                                                 'Without azimuth', 'Without band', 'Without vendor', 'Duplicate identities'], quality))
    spectrum = [[row['operator'], row['technology'], row['band'], row.get('band_class') or '—', _number(row['sites'], 0), _number(row['cells'], 0),
                 _number(row['carriers'], 0), _number(row['typical_bandwidth_mhz'], 0, ' MHz') if row.get('typical_bandwidth_mhz') else '—',
                 _number(row['deployed_mhz'], 0) if row.get('deployed_mhz') else '—'] for row in snapshot.get('spectrum') or []]
    if spectrum:
        tables.append(('Spectrum · Deployed in the inventory snapshot', ['Network', 'Technology', 'Band', 'Class', 'Sites', 'Cells', 'Carriers',
                                                                          'Typical bandwidth', 'Deployed MHz'], spectrum))
    density = snapshot.get('density') or {}
    dimension = 'cluster' if density.get('cluster') else 'region' if density.get('region') else ''
    if dimension:
        tables.append((f'Cluster Sites Density · Inventory snapshot per {dimension.title()}', [dimension.title(), 'Network', 'Sites', 'Sites with NR', 'Area km²',
                                                                                                'Sites per km²', 'Median inter-site km', 'P90 inter-site km'],
                       [[row['area'], row['operator'], _number(row['sites'], 0), _number(row['nr_sites'], 0),
                         _number(row['area_km2'], 0) if row.get('area_km2') else '—', _number(row['sites_per_km2'], 3) if row.get('sites_per_km2') else '—',
                         _number(row['median_isd_km'], 2), _number(row['p90_isd_km'], 2)] for row in density[dimension]]))
    return tables


def _labelled_rows(analysis: dict[str, Any], section: dict[str, Any]) -> list[dict[str, Any]]:
    rows = section.get('rf_rows') or []
    if len(analysis.get('sections') or []) < 2:
        return rows
    return [{**row, 'operator': f"{row.get('operator') or ''} · {section.get('technology_label') or ''}"} for row in rows]


def _render_image(render: ChartRenderer, payload: Any, width: int = 1600, height: int = 900) -> tuple[BytesIO | None, str]:
    if not isinstance(payload, dict):
        return None, 'No chart for this selection.'
    try:
        image = BytesIO(render(payload, width, height))
        with Image.open(image) as raster:
            raster.verify()
        image.seek(0)
        return image, ''
    except Exception as exc:  # A chart that cannot be drawn must not drop the whole summary.
        return None, f'The chart could not be rendered: {exc}'


def _section_visuals(section: dict[str, Any], render: ChartRenderer) -> tuple[list[tuple[str, BytesIO | None, str, Any]], list[tuple[str, list[tuple[str, BytesIO | None, str, Any]]]]]:
    """The RF Quality CDFs (RSRP | SINR) and, for every group, its maps (Coverage | Interference) with the areas table
    shown under each map, as the page lays them out. Panels are (caption, PNG or None, note, table or None)."""
    charts = section.get('charts') or {}
    maps = section.get('maps') or {}
    label = section.get('technology_label') or ''
    cdfs = [('', *_render_image(render, payload), None) for payload in (charts.get('rsrp_cdf'), charts.get('sinr_cdf')) if isinstance(payload, dict)]
    groups = []
    for group in maps.get('groups') or [maps]:
        panels = [
            (caption, *_render_image(render, group.get(key)), area_table(group.get(hotspots) or [], unit))
            for caption, key, hotspots, unit in (
                (f'{label} Coverage (mean RSRP per grid square)'.strip(), 'coverage', 'coverage_hotspots', 'dBm'),
                (f'{label} Interference (mean SINR per grid square)'.strip(), 'interference', 'interference_hotspots', 'dB'),
            ) if isinstance(group.get(key), dict)
        ]
        if panels:
            groups.append((str(group.get('operator') or ''), panels))
    return cdfs, groups


def deployment_table_groups(deployment: dict[str, Any]) -> list[tuple[str, list[tuple[str, list[str], list[list[str]]]]]]:
    """One group per Network Deployment view with each operator's inventory side by side (Vodafone, then Three)."""
    if 'groupings' in deployment:
        return [group for grouping in deployment['groupings'] for group in deployment_table_groups(grouping)]
    panels = []
    for inventory in deployment.get('inventories') or []:
        source = inventory.get('rows') or []
        maximum = max((int(row['cells'] or 0) for row in source), default=0) or 1
        # As on the page, a bar shows each group's cells against the largest group.
        rows = [[row['group'], _number(row['sites'], 0), _number(row['cells'], 0), share_bar(int(row['cells'] or 0) / maximum)]
                for row in source]
        totals = inventory.get('totals') or {}
        if totals:
            rows.append(['Total', _number(totals.get('sites'), 0), _number(totals.get('cells'), 0), ''])
        if rows:
            panels.append((f"{inventory.get('operator')} ({inventory.get('file_name')})", [deployment.get('group_label') or 'Group', 'Sites', 'Cells', ''], rows))
    return [(f"Network Deployment · {deployment.get('group_label') or 'All'}", panels)] if panels else []


SHARE_BAR_BLOCKS = 10
SHARE_BAR_FILL = '4F46E5'


def share_bar(share: float) -> str:
    """A text bar: filled blocks for the share, light blocks for the rest of the track."""
    filled = max(1 if share > 0 else 0, round(max(0.0, min(1.0, share)) * SHARE_BAR_BLOCKS))
    return '\u2588' * filled + '\u2591' * (SHARE_BAR_BLOCKS - filled)


def _is_share_bar(text: str) -> bool:
    return bool(text) and set(text) <= {'\u2588', '\u2591'} and '\u2591' in text or (bool(text) and set(text) == {'\u2588'} and len(text) == SHARE_BAR_BLOCKS)


CLASS_BAR_COLUMNS = ('RSRP classes', 'SINR classes')
OVERVIEW_CARD_FIELDS = (
    ('Median RSRP', 'rsrp_median', ' dBm', 'rsrp_median', ' dB'), ('Low coverage', 'low_coverage_share', '%', 'low_coverage_share', ' pp'),
    ('Median SINR', 'sinr_median', ' dB', 'sinr_median', ' dB'), ('High interference', 'high_interference_share', '%', 'high_interference_share', ' pp'),
    ('Observed eNodeBs', 'observed_enodebs', '', '', ''), ('Samples', 'samples', '', '', ''),
)


def overview_cards(analysis: dict[str, Any], section: dict[str, Any]) -> list[dict[str, Any]]:
    """The Overview cards of one technology: title, colour and the six main indicators."""
    colours = analysis.get('colours') or {}
    cards = []
    for row in section.get('overview') or section.get('rf_rows') or []:
        deltas = row.get('deltas') or {}
        values = []
        for label, key, unit, delta_key, delta_unit in OVERVIEW_CARD_FIELDS:
            digits = 0 if key in {'observed_enodebs', 'samples'} else 1
            text = _number(row.get(key), digits, unit)
            if delta_key and deltas.get(delta_key) is not None:
                text += f' ({_signed(deltas.get(delta_key), delta_unit)})'
            values.append((label, text))
        cards.append({'title': str(row.get('operator') or ''), 'colour': colours.get(row.get('operator')) or '#6D46A8', 'values': values})
    return cards


def rf_quality_table(section: dict[str, Any], colours: dict[str, str] | None = None) -> tuple[list[str], list[list[str]], list[tuple]]:
    """The table under the RF Quality CDFs; the class columns are drawn as coloured bars from the returned classes."""
    label = section.get('technology_label') or ''
    columns = ['Group', 'Samples', f'{label} RSRP samples'.strip(), 'Median RSRP', 'P10 RSRP', 'Low coverage', 'RSRP classes',
               'Median SINR', 'P10 SINR', 'High interference', 'SINR classes']
    rows, bars = [], []
    for row in section.get('rf_rows') or section.get('overview') or []:
        rows.append([str(row.get('operator') or ''), _number(row.get('samples'), 0), _number(row.get('rsrp_samples', row.get('samples')), 0),
                     _number(row.get('rsrp_median'), suffix=' dBm'), _number(row.get('rsrp_p10'), suffix=' dBm'),
                     _number(row.get('low_coverage_share'), suffix='%'), '',
                     _number(row.get('sinr_median'), suffix=' dB'), _number(row.get('sinr_p10'), suffix=' dB'),
                     _number(row.get('high_interference_share'), suffix='%'), ''])
        # The third item is the group's colour, drawn as a swatch before its name as on the page.
        bars.append((row.get('rsrp_classes') or [], row.get('sinr_classes') or [], (colours or {}).get(row.get('operator'))))
    return columns, rows, bars


def area_table(rows: list[dict[str, Any]], unit: str, limit: int = 8) -> tuple[list[str], list[list[str]]]:
    """The compact areas table shown under each map: Area, Region, Samples, Mean and share Below the threshold."""
    return ['Area', 'Region', 'Samples', 'Mean', 'Below'], [
        [row.get('city') or '—', row.get('region') or '—', _number(row.get('samples'), 0), _number(row.get('mean'), suffix=f' {unit}'),
         _number(row.get('bad_share'), suffix='%')]
        for row in rows[:limit]
    ]


CLASS_BAR_BLOCKS = 12
CLASS_BAR_BLOCK = '\u2588'


def class_bar_segments(classes: list[dict[str, Any]], blocks: int = CLASS_BAR_BLOCKS) -> list[tuple[int, str]]:
    """Split a bar of ``blocks`` characters between the quality classes in proportion to their shares.

    The bar is written as coloured block characters inside the table cell, so it always stays in its row.
    """
    shares = [(float(item.get('share') or 0), str(item.get('colour') or '#999999')) for item in classes]
    total = sum(share for share, _colour in shares)
    if total <= 0:
        return []
    exact = [share / total * blocks for share, _colour in shares]
    counts = [int(value) for value in exact]
    for index in sorted(range(len(exact)), key=lambda item: exact[item] - counts[item], reverse=True)[:blocks - sum(counts)]:
        counts[index] += 1
    return [(count, colour) for count, (_share, colour) in zip(counts, shares, strict=False) if count]

def _single_line(value: Any) -> str:
    """Keep table values intact while removing explicit line-break characters."""
    return ' '.join(str(value).splitlines())


def _column_text_widths(columns: list[str], rows: list[list[str]]) -> list[float]:
    """Estimate text widths in points at 1 pt, reserving space for font substitution."""
    normal, bold = load_image_font(100), load_image_font(100, bold=True)
    return [max(float(bold.getlength(_single_line(label))),
                max((float(normal.getlength(_single_line(row[index]))) for row in rows), default=0)) / 100 * 1.15
            for index, label in enumerate(columns)]


def _table_geometry(columns: list[str], rows: list[list[str]], width: float, maximum_font: float = 10) -> tuple[list[float], float]:
    measured = _column_text_widths(columns, rows)
    padding = 0.14 * 72
    font = min(maximum_font, (width * 72 - padding * len(columns)) / max(sum(measured), 1))
    font = max(1, font)
    required = [length * font + padding for length in measured]
    scale = width / sum(required)
    return [value * scale for value in required], font


def _ppt_table_parts(columns: list[str], rows: list[list[str]], width: float):
    """Repeat the identity column if a wide comparison needs multiple metric panels."""
    measured = _column_text_widths(columns, rows)
    indices, parts = [0], []
    for index in range(1, len(columns)):
        proposed = [*indices, index]
        if len(indices) > 1 and sum(measured[item] * 8 + 0.14 * 72 for item in proposed) > width * 72:
            parts.append(indices)
            indices = [0]
        indices.append(index)
    parts.append(indices)
    return [([columns[index] for index in part], [[row[index] for index in part] for row in rows]) for part in parts]


# Tables follow the page: a light teal header, light lavender alternate rows, thin lines and right-aligned numbers.
TABLE_HEADER_FILL = 'D9EEF1'
TABLE_HEADER_TEXT = '16505A'
TABLE_ODD_FILL = 'F7F7FF'
TABLE_EVEN_FILL = 'FFFFFF'
TABLE_TEXT = '1F2433'
TABLE_LINE = 'E3E8F5'
NUMERIC_TEXT = re.compile(r'^[\s+\-−]?[\d.,]+\s*(%|pp|dB|dBm|MHz| d|\s)*$|^[—–-]$')


def _numeric_columns(rows: list[list[str]], count: int) -> set[int]:
    """Columns whose values are all numbers (counts, shares, dB…), which are aligned right as on the page."""
    return {index for index in range(1, count)
            if rows and all(NUMERIC_TEXT.match(str(row[index]).strip() or '—') for row in rows if index < len(row))}


def _ppt_cell_line(cell, colour: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    # DrawingML expects the cell lines before the cell fill.
    for position, side in enumerate(('a:lnL', 'a:lnR', 'a:lnT', 'a:lnB')):
        existing = properties.find(qn(side))
        if existing is not None:
            properties.remove(existing)
        line = OxmlElement(side)
        line.set('w', '6350')
        fill = OxmlElement('a:solidFill')
        colour_element = OxmlElement('a:srgbClr')
        colour_element.set('val', colour)
        fill.append(colour_element)
        line.append(fill)
        properties.insert(position, line)


def _add_table(slide, columns: list[str], rows: list[list[str]], left: float, top: float, width: float,
               *, row_height: float = 0.32, maximum_font: float = 10):
    shape = slide.shapes.add_table(len(rows) + 1, len(columns), Inches(left), Inches(top), Inches(width), Inches(row_height * (len(rows) + 1)))
    table = shape.table
    widths, font_size = _table_geometry(columns, rows, width, maximum_font)
    for index, column_width in enumerate(widths):
        table.columns[index].width = Inches(column_width)
    numeric = _numeric_columns(rows, len(columns))
    # The template's banded style is replaced by the colours of the page.
    table.first_row = table.horz_banding = False
    for row_index, values in enumerate([columns, *rows]):
        fill = TABLE_HEADER_FILL if row_index == 0 else (TABLE_ODD_FILL if row_index % 2 else TABLE_EVEN_FILL)
        for column, value in enumerate(values):
            cell = table.cell(row_index, column)
            cell.text = _single_line(value)
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.text_frame.word_wrap = False
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(fill)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            _ppt_cell_line(cell, TABLE_LINE)
            for paragraph in cell.text_frame.paragraphs:
                paragraph.space_before = paragraph.space_after = Pt(0)
                paragraph.alignment = PP_ALIGN.RIGHT if column in numeric else PP_ALIGN.LEFT
                for run in paragraph.runs:
                    run.font.size = Pt(font_size)
                    run.font.bold = row_index == 0
                    run.font.color.rgb = RGBColor.from_string(
                        TABLE_HEADER_TEXT if row_index == 0 else SHARE_BAR_FILL if _is_share_bar(str(value)) else TABLE_TEXT)
    for row in table.rows:
        row.height = Inches(row_height)
    return table


def _content_frame(slide) -> tuple[float, float, float, float]:
    layout = slide.slide_layout
    shapes = [shape for shape in layout.placeholders if shape.placeholder_format.type not in {1, 3, 4}]
    shape = max(shapes, key=lambda item: item.width * item.height)
    return tuple(value / 914400 for value in (shape.left, shape.top, shape.width, shape.height))


def _slide(presentation: Presentation, title: str, subtitle: str = ''):
    from src.modules.cdr_reporting import _named_slide_layout, _remove_template_chart_placeholders, _set_slide_header

    layout = _named_slide_layout(presentation, 'Title + 1 rows + 1 columns')
    if layout is None:
        raise ValueError('The Dashboard template requires the Title + 1 rows + 1 columns layout.')
    slide = presentation.slides.add_slide(layout)
    _set_slide_header(slide, title, subtitle)
    _remove_template_chart_placeholders(slide)
    for placeholder in slide.placeholders:
        if placeholder.has_text_frame:
            placeholder.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    return slide


def _table_slides(presentation: Presentation, title: str, columns: list[str], rows: list[list[str]], subtitle: str = '') -> None:
    from src.modules.cdr_reporting import _named_slide_layout

    layout = _named_slide_layout(presentation, 'Title + 1 rows + 1 columns')
    content = max((shape for shape in layout.placeholders if shape.placeholder_format.type not in {1, 3, 4}),
                  key=lambda shape: shape.width * shape.height)
    parts = _ppt_table_parts(columns, rows, content.width / 914400)
    for part_index, (part_columns, part_rows) in enumerate(parts, start=1):
        pages = [part_rows[index:index + TABLE_ROWS_PER_SLIDE] for index in range(0, len(part_rows), TABLE_ROWS_PER_SLIDE)] or [[]]
        for page_number, page in enumerate(pages, start=1):
            page_title = title + (f' · Part {part_index}/{len(parts)}' if len(parts) > 1 else '')
            if len(pages) > 1:
                page_title += f' · {page_number}/{len(pages)}'
            slide = _slide(presentation, page_title, subtitle)
            left, top, width, _height = _content_frame(slide)
            if page:
                _add_table(slide, part_columns, page, left, top, width)
            else:
                _add_textbox(slide, left, top, width, 0.3, 'No data for this selection.', size=12, color=MUTED)


PANEL_GAP = 0.3


def _panel_frames(left: float, width: float, count: int) -> list[tuple[float, float]]:
    panel_width = (width - PANEL_GAP * (count - 1)) / count
    return [(left + index * (panel_width + PANEL_GAP), panel_width) for index in range(count)]


def _paired_table_slides(presentation: Presentation, title: str, panels: list[tuple[str, list[str], list[list[str]]]], subtitle: str = '') -> None:
    """Tables side by side on the same slides, as the page shows them; long tables continue on more slides."""
    if len(panels) == 1 and not panels[0][0]:
        _table_slides(presentation, title, panels[0][1], panels[0][2], subtitle)
        return
    page_count = max(1, *((len(rows) + TABLE_ROWS_PER_SLIDE - 1) // TABLE_ROWS_PER_SLIDE for _caption, _columns, rows in panels))
    for page_number in range(page_count):
        slide = _slide(presentation, title + (f' · {page_number + 1}/{page_count}' if page_count > 1 else ''), subtitle)
        left, top, width, _height = _content_frame(slide)
        for (caption, columns, rows), (panel_left, panel_width) in zip(panels, _panel_frames(left, width, len(panels)), strict=False):
            page = rows[page_number * TABLE_ROWS_PER_SLIDE:(page_number + 1) * TABLE_ROWS_PER_SLIDE]
            _add_textbox(slide, panel_left, top, panel_width, 0.3, caption, size=12, bold=True)
            if page:
                _add_table(slide, columns, page, panel_left, top + 0.4, panel_width)
            elif page_number == 0:
                _add_textbox(slide, panel_left, top + 0.4, panel_width, 0.3, 'No data for this selection.', size=11, color=MUTED)


def _overview_slides(presentation: Presentation, title: str, cards: list[dict[str, Any]], per_row: int = 4, rows_per_slide: int = 2,
                     subtitle: str = '') -> None:
    """The Overview cards of the page: one card per group with its colour and six indicators."""
    per_slide = per_row * rows_per_slide
    pages = [cards[index:index + per_slide] for index in range(0, len(cards), per_slide)] or [[]]
    for page_number, page in enumerate(pages, start=1):
        slide = _slide(presentation, title + (f' · {page_number}/{len(pages)}' if len(pages) > 1 else ''), subtitle)
        left, top, width, height = _content_frame(slide)
        card_width = (width - PANEL_GAP * (per_row - 1)) / per_row
        card_height = (height - PANEL_GAP * (rows_per_slide - 1)) / rows_per_slide
        for index, card in enumerate(page):
            card_left = left + (index % per_row) * (card_width + PANEL_GAP)
            card_top = top + (index // per_row) * (card_height + PANEL_GAP)
            colour = RGBColor.from_string(card['colour'].lstrip('#').upper())
            box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(card_left), Inches(card_top), Inches(card_width), Inches(card_height))
            box.adjustments[0] = 0.06
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            box.line.color.rgb = RGBColor(0xD9, 0xDE, 0xEA)
            strip = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(card_left + 0.08), Inches(card_top), Inches(card_width - 0.16), Inches(0.06))
            strip.fill.solid()
            strip.fill.fore_color.rgb = colour
            strip.line.fill.background()
            heading = slide.shapes.add_textbox(Inches(card_left + 0.15), Inches(card_top + 0.12), Inches(card_width - 0.3), Inches(0.35))
            run = heading.text_frame.paragraphs[0].add_run()
            run.text = card['title']
            run.font.size, run.font.bold, run.font.color.rgb = Pt(13), True, colour
            cell_width = (card_width - 0.3) / 2
            cell_height = (card_height - 0.55) / 3
            for value_index, (label, value) in enumerate(card['values']):
                box_left = card_left + 0.15 + (value_index % 2) * cell_width
                box_top = card_top + 0.5 + (value_index // 2) * cell_height
                frame = slide.shapes.add_textbox(Inches(box_left), Inches(box_top), Inches(cell_width), Inches(cell_height)).text_frame
                frame.word_wrap = True
                caption = frame.paragraphs[0].add_run()
                caption.text = label.upper()
                caption.font.size, caption.font.bold, caption.font.color.rgb = Pt(7), True, RGBColor(0x5B, 0x63, 0x77)
                figure = frame.add_paragraph().add_run()
                figure.text = value
                figure.font.size, figure.font.bold, figure.font.color.rgb = Pt(10), True, RGBColor(0x1F, 0x24, 0x33)


def _add_picture(slide, image: BytesIO, left: float, top: float, width: float, height: float) -> float:
    """Fit a PNG in a box, centred horizontally at its top; return the picture height."""
    with Image.open(image) as raster:
        ratio = raster.width / raster.height
    image.seek(0)
    picture_width = min(width, height * ratio)
    picture_height = picture_width / ratio
    slide.shapes.add_picture(image, Inches(left + (width - picture_width) / 2), Inches(top), width=Inches(picture_width), height=Inches(picture_height))
    return picture_height


def _add_bar_table(slide, columns: list[str], rows: list[list[str]], bars: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]],
                   left: float, top: float, width: float, row_height: float) -> None:
    filler = CLASS_BAR_BLOCK * CLASS_BAR_BLOCKS
    sized = [[filler if columns[index] in CLASS_BAR_COLUMNS else value for index, value in enumerate(row)] for row in rows]
    table = _add_table(slide, columns, sized, left, top, width, row_height=row_height, maximum_font=9)
    for bar_index, column_name in enumerate(CLASS_BAR_COLUMNS):
        column = columns.index(column_name)
        for row_index, classes in enumerate(bars, start=1):
            paragraph = table.cell(row_index, column).text_frame.paragraphs[0]
            size = paragraph.runs[0].font.size if paragraph.runs else Pt(8)
            for run in list(paragraph.runs):
                run._r.getparent().remove(run._r)
            for count, colour in class_bar_segments(classes[bar_index]):
                run = paragraph.add_run()
                run.text = CLASS_BAR_BLOCK * count
                run.font.size = size
                run.font.color.rgb = RGBColor.from_string(colour.lstrip('#').upper())
    for row_index, classes in enumerate(bars, start=1):
        colour = classes[2] if len(classes) > 2 else None
        if colour and re.fullmatch(r'#[0-9A-Fa-f]{6}', str(colour)):
            paragraph = table.cell(row_index, 0).text_frame.paragraphs[0]
            first = paragraph.runs[0] if paragraph.runs else None
            swatch = paragraph.add_run()
            swatch.text = '\u25A0 '
            swatch.font.size = first.font.size if first is not None else Pt(9)
            swatch.font.color.rgb = RGBColor.from_string(str(colour).lstrip('#').upper())
            if first is not None:
                first._r.addprevious(swatch._r)

def _visual_slides(presentation: Presentation, title: str, panels: list[tuple[str, BytesIO | None, str, Any]],
                   below: tuple[list[str], list[list[str]], list[Any]] | None = None, subtitle: str = '') -> None:
    """Charts side by side as on the page, each with an optional table under it (the map areas), or one table
    under all of them (RF Quality with its class bars). Rows that do not fit continue on further slides."""
    row_height = 0.24
    slide = _slide(presentation, title, subtitle)
    left, top, width, height = _content_frame(slide)
    has_tables = below is not None or any(table for *_rest, table in panels)
    image_height = height * (0.52 if has_tables else 1) - 0.35
    remaining_rows = []
    for (caption, image, note, table), (panel_left, panel_width) in zip(panels, _panel_frames(left, width, len(panels)), strict=False):
        cursor = top
        if caption:
            _add_textbox(slide, panel_left, cursor, panel_width, 0.3, caption, size=12, bold=True)
            cursor += 0.35
        if image is None:
            _add_textbox(slide, panel_left, cursor, panel_width, 0.6, note, size=12, color=ORANGE)
            cursor += image_height
        else:
            cursor += _add_picture(slide, image, panel_left, cursor, panel_width, image_height)
        if table:
            columns, rows = table
            if rows:
                _add_table(slide, columns, rows, panel_left, cursor + 0.1, panel_width, row_height=row_height, maximum_font=9)
            else:
                _add_textbox(slide, panel_left, cursor + 0.1, panel_width, 0.3, 'No area falls below the threshold.', size=11, color=MUTED)
    if below is None:
        return
    columns, rows, bars = below
    row_height = 0.3
    table_top = top + 0.35 + image_height + 0.1
    fit = max(1, int((top + height - table_top) / row_height) - 1)
    first, rest = (rows[:fit], bars[:fit]), (rows[fit:], bars[fit:])
    if first[0]:
        _add_bar_table(slide, columns, first[0], first[1], left, table_top, width, row_height)
    per_slide = max(1, int(height / row_height) - 1)
    pages = [(rest[0][index:index + per_slide], rest[1][index:index + per_slide]) for index in range(0, len(rest[0]), per_slide)]
    for page_number, (page_rows, page_bars) in enumerate(pages, start=2):
        continuation = _slide(presentation, f'{title} · {page_number}/{len(pages) + 1}', subtitle)
        left, top, width, _height = _content_frame(continuation)
        _add_bar_table(continuation, columns, page_rows, page_bars, left, top, width, row_height)


def export_network_insights_powerpoint(destination: Path, analysis: dict[str, Any], deployment: dict[str, Any],
                                       selection: dict[str, Any], render: ChartRenderer, template: Path | None = None) -> Path:
    from src.config import settings
    from src.modules.cdr_reporting import _named_slide_layout, _remove_all_slides, _set_structural_slide_text

    presentation = Presentation(template or settings.powerpoint_templates_dir / 'Template_01.pptx')
    _remove_all_slides(presentation)
    cover = presentation.slides.add_slide(_named_slide_layout(presentation, 'Title Page'))
    _set_structural_slide_text(cover, 'Summary Network Insights', 'DriveTest Analyzer')
    from src.modules.exports import remove_empty_placeholders
    remove_empty_placeholders(cover)
    selection_slide = _slide(presentation, 'Analysis Selection')
    left, top, width, height = _content_frame(selection_slide)
    shape = selection_slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    shape.text_frame.word_wrap = True
    shape.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    for index, line in enumerate(summary_selection_lines(selection)):
        paragraph = shape.text_frame.paragraphs[0] if index == 0 else shape.text_frame.add_paragraph()
        paragraph.text = line
        paragraph.font.size = Pt(15)
    sections = technology_sections(analysis)
    visuals = [(suffix, section, *_section_visuals(section, render)) for suffix, section in sections]
    # Every slide names under its title the area, operators, vendors and environments it shows (see scope_for).
    measured = scope_text(selection)
    # Sections follow the order of the page: Overview, maps, RF Quality, Serving Cells, Network Deployment, Cluster Sites
    # Density, Spectrum.
    for suffix, section in sections:
        _overview_slides(presentation, f'Overview{suffix}', overview_cards(analysis, section), subtitle=measured)
    for suffix, _section, _cdfs, groups in visuals:
        for group, panels in groups:
            _visual_slides(presentation, f'Coverage & Interference Maps{suffix}' + (f' · {group}' if group else ''), panels, subtitle=measured)
    for title, columns, rows in cell_status_tables(analysis):
        _table_slides(presentation, title, columns, rows, measured)
    for suffix, section, cdfs, _groups in visuals:
        if cdfs:
            _visual_slides(presentation, f'RF Quality{suffix}', cdfs, rf_quality_table(section, analysis.get('colours')), subtitle=measured)
    serving = serving_tables(analysis)
    distance = serving_visuals(analysis, render)
    if distance and serving:
        # The distance CDF with the summary of each group under it.
        _visual_slides(presentation, 'Serving Cells', [(caption, image, note, (serving[0][1], serving[0][2])) for caption, image, note, _table in distance],
                       subtitle=measured)
    for title, columns, rows in serving[1:] if distance else serving:
        _table_slides(presentation, title, columns, rows, measured)
    for title, columns, rows in [table for table in snapshot_tables(deployment) if not table[0].startswith(('Spectrum', 'Cluster'))]:
        _table_slides(presentation, title, columns, rows, scope_for(title, selection))
    for title, panels in deployment_table_groups(deployment):
        _paired_table_slides(presentation, title, panels, scope_for(title, selection))
    for title, columns, rows in [*cluster_sites_tables(analysis, deployment),
                                 *[table for table in snapshot_tables(deployment) if table[0].startswith('Cluster')],
                                 *spectrum_tables(analysis), *[table for table in snapshot_tables(deployment) if table[0].startswith('Spectrum')],
                                 *nr_duplex_table(deployment)]:
        _table_slides(presentation, title, columns, rows, scope_for(title, selection))
    ladder = bandwidth_ladder_image(analysis)
    for title, columns, rows in bandwidth_tables(analysis):
        # The total bandwidth ladders, then their figures.
        if title.startswith('Spectrum · Total bandwidth') and ladder is not None:
            # As a benchmark slide: the chart title, with its scope and the line that explains it under it.
            _visual_slides(presentation, bandwidth_title(analysis), [('', ladder, '', None)],
                           subtitle=f'{measured}\n{bandwidth_caption(analysis)}')
        _table_slides(presentation, title, columns, rows, measured)
    warnings = analysis.get('warnings') or []
    if warnings:
        slide = _slide(presentation, 'Analysis Notes')
        left, top, width, height = _content_frame(slide)
        shape = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        shape.text_frame.text = '\n'.join(str(warning) for warning in warnings)
        shape.text_frame.word_wrap = True
        shape.text_frame.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE
    closing = _named_slide_layout(presentation, 'Black logo end slide')
    if closing is not None:
        _set_structural_slide_text(presentation.slides.add_slide(closing), '', '')
    presentation.save(destination)
    return destination


def _docx_table(document: Document, columns: list[str], rows: list[list[str]], width: float | None = None):
    table = document.add_table(rows=1, cols=len(columns))
    table.autofit = False
    _docx_table_lines(table)
    numeric = _numeric_columns(rows, len(columns))
    section = document.sections[-1]
    if width is None:
        width = (section.page_width - section.left_margin - section.right_margin) / 914400
    widths, font = _table_geometry(columns, rows, width, maximum_font=9)
    for index, value in enumerate(widths):
        table.columns[index].width = DocxInches(value)
    for row_index, values in enumerate([columns, *rows]):
        row = table.rows[0] if row_index == 0 else table.add_row()
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        if row_index == 0:
            row._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
        for index, value in enumerate(values):
            cell = row.cells[index]
            cell.width = DocxInches(widths[index])
            cell.text = _single_line(value)
            properties = cell._tc.get_or_add_tcPr()
            properties.append(OxmlElement('w:noWrap'))
            margins = OxmlElement('w:tcMar')
            for side in ('top', 'bottom', 'left', 'right'):
                item = OxmlElement(f'w:{side}')
                item.set(qn('w:w'), '72' if side in {'left', 'right'} else '36')
                item.set(qn('w:type'), 'dxa')
                margins.append(item)
            properties.append(margins)
            shading = OxmlElement('w:shd')
            shading.set(qn('w:val'), 'clear')
            shading.set(qn('w:color'), 'auto')
            shading.set(qn('w:fill'), TABLE_HEADER_FILL if row_index == 0 else (TABLE_ODD_FILL if row_index % 2 else TABLE_EVEN_FILL))
            properties.append(shading)
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_before = paragraph.paragraph_format.space_after = DocxPt(0)
                paragraph.paragraph_format.line_spacing = 1
                if index in numeric:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                for run in paragraph.runs:
                    run.font.name = 'Arial'
                    run.font.size = DocxPt(font)
                    run.bold = row_index == 0
                    run.font.color.rgb = DocxRGBColor.from_string(
                        TABLE_HEADER_TEXT if row_index == 0 else SHARE_BAR_FILL if _is_share_bar(str(value)) else TABLE_TEXT)
    return table


def _docx_table_lines(table) -> None:
    """Thin light lines around and inside the table, as on the page."""
    properties = table._tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        border = OxmlElement(f'w:{side}')
        border.set(qn('w:val'), 'single')
        border.set(qn('w:sz'), '4')
        border.set(qn('w:space'), '0')
        border.set(qn('w:color'), TABLE_LINE)
        borders.append(border)
    properties.append(borders)


DOCX_COLUMN_GAP = 0.3


def _docx_columns(document: Document, count: int) -> float:
    """Continue on a new continuous section with ``count`` columns; return each column's width in inches."""
    section = document.add_section(WD_SECTION.CONTINUOUS)
    columns = section._sectPr.find(qn('w:cols'))
    if columns is None:
        columns = OxmlElement('w:cols')
        section._sectPr.append(columns)
    columns.set(qn('w:num'), str(count))
    columns.set(qn('w:space'), str(int(DOCX_COLUMN_GAP * 1440)))
    usable = (section.page_width - section.left_margin - section.right_margin) / 914400
    return (usable - DOCX_COLUMN_GAP * (count - 1)) / count


def _docx_section_heading(document: Document, title: str, scope: str = '') -> None:
    """Every section of the summary starts on a new page, as each one has its own slide in PowerPoint, with the area,
    operators, vendors and environments it shows under its title."""
    heading = document.add_heading(title, level=1)
    heading.paragraph_format.page_break_before = True
    if scope:
        run = document.add_paragraph().add_run(scope)
        run.bold = True
        run.font.size = DocxPt(9)
        run.font.color.rgb = DocxRGBColor(0x24, 0x5A, 0x96)


def _docx_side_by_side(document: Document, title: str, panels: list[tuple[str, Any]], add_panel: Callable[[Any, float], None],
                       *, new_page: bool = True, scope: str = '') -> None:
    """A heading on a new page, then the panels side by side in two columns (Coverage | Interference, Vodafone | Three)."""
    _docx_section_heading(document, title, scope)
    width = _docx_columns(document, len(panels)) if len(panels) > 1 else None
    for index, (caption, content) in enumerate(panels):
        paragraph = document.add_paragraph() if caption or index else None
        if index and width is not None:
            # The column break opens the caption, so both panels start at the same height.
            paragraph.add_run().add_break(WD_BREAK.COLUMN)
        if caption:
            paragraph.add_run(caption).bold = True
        add_panel(content, width)
    if width is not None:
        _docx_columns(document, 1)


def _docx_overview_cards(document: Document, cards: list[dict[str, Any]], per_row: int = 4) -> None:
    """The Overview cards as a grid: each cell holds a group's coloured title and its six indicators."""
    if not cards:
        document.add_paragraph('No data for this selection.')
        return
    table = document.add_table(rows=(len(cards) + per_row - 1) // per_row, cols=per_row)
    table.style = 'Table Grid'
    for index, card in enumerate(cards):
        cell = table.cell(index // per_row, index % per_row)
        title = cell.paragraphs[0].add_run(card['title'])
        title.bold = True
        title.font.size = DocxPt(11)
        title.font.color.rgb = DocxRGBColor.from_string(card['colour'].lstrip('#').upper())
        for label, value in card['values']:
            paragraph = cell.add_paragraph()
            paragraph.paragraph_format.space_after = DocxPt(0)
            caption = paragraph.add_run(f'{label}: ')
            caption.font.size = DocxPt(8)
            caption.font.color.rgb = DocxRGBColor(0x5B, 0x63, 0x77)
            figure = paragraph.add_run(value)
            figure.bold = True
            figure.font.size = DocxPt(9)


def _docx_bar_table(document: Document, columns: list[str], rows: list[list[str]], bars: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]) -> None:
    """The RF Quality table with the RSRP and SINR classes drawn as coloured bars in their cells."""
    filler = CLASS_BAR_BLOCK * CLASS_BAR_BLOCKS
    sized = [[filler if columns[index] in CLASS_BAR_COLUMNS else value for index, value in enumerate(row)] for row in rows]
    table = _docx_table(document, columns, sized)
    for bar_index, column_name in enumerate(CLASS_BAR_COLUMNS):
        column = columns.index(column_name)
        for row_index, classes in enumerate(bars, start=1):
            paragraph = table.cell(row_index, column).paragraphs[0]
            size = paragraph.runs[0].font.size if paragraph.runs else DocxPt(8)
            for run in list(paragraph.runs):
                run._r.getparent().remove(run._r)
            for count, colour in class_bar_segments(classes[bar_index]):
                run = paragraph.add_run(CLASS_BAR_BLOCK * count)
                run.font.size = size
                run.font.name = 'Arial'
                run.font.color.rgb = DocxRGBColor.from_string(colour.lstrip('#').upper())
    for row_index, classes in enumerate(bars, start=1):
        colour = classes[2] if len(classes) > 2 else None
        if colour and re.fullmatch(r'#[0-9A-Fa-f]{6}', str(colour)):
            paragraph = table.cell(row_index, 0).paragraphs[0]
            first = paragraph.runs[0] if paragraph.runs else None
            swatch = paragraph.add_run('\u25A0 ')
            swatch.font.size = first.font.size if first is not None else DocxPt(8)
            swatch.font.color.rgb = DocxRGBColor.from_string(str(colour).lstrip('#').upper())
            if first is not None:
                first._r.addprevious(swatch._r)

def export_network_insights_word(destination: Path, analysis: dict[str, Any], deployment: dict[str, Any],
                                 selection: dict[str, Any], render: ChartRenderer) -> Path:
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = DocxInches(11.69), DocxInches(8.27)
    section.left_margin = section.right_margin = DocxInches(0.6)
    section.top_margin = section.bottom_margin = DocxInches(0.6)
    tables = [*(rf_quality_table(section)[:2] for _suffix, section in technology_sections(analysis)),
              *(hotspot_table((section.get('maps') or {}).get(key) or [], unit) for _suffix, section in technology_sections(analysis)
                for key, unit in [('coverage_hotspots', 'dBm'), ('interference_hotspots', 'dB')]),
              *((columns, rows) for _title, columns, rows in [*spectrum_tables(analysis), *deployment_tables(deployment), *cluster_sites_tables(analysis, deployment),
                                                              *bandwidth_tables(analysis), *nr_duplex_table(deployment)])]
    needed = max((sum(length * 9 + 0.14 * 72 for length in _column_text_widths(columns, rows)) / 72
                  for columns, rows in tables), default=0)
    if needed > 10.49:
        section.page_width = DocxInches(max(16.54, min(22, needed + 1.2)))
        section.page_height = DocxInches(11.69)
    document.add_heading('DriveTest Analyzer · Summary Network Insights', level=0)
    for line in summary_selection_lines(selection):
        document.add_paragraph(line, style='List Bullet')
    for warning in analysis.get('warnings') or []:
        document.add_paragraph(f'Warning: {warning}')
    def add_image(content: tuple[BytesIO | None, str, Any], width: float | None) -> None:
        image, note, table = content
        if image is None:
            document.add_paragraph(note)
        else:
            document.add_picture(image, width=DocxInches(width or 6.3))
        if table is not None:
            add_table(table, width)

    def add_table(content: tuple[list[str], list[list[str]]], width: float | None) -> None:
        columns, rows = content
        if rows:
            _docx_table(document, columns, rows, width)
        else:
            document.add_paragraph('No data for this selection.')

    sections = technology_sections(analysis)
    visuals = [(suffix, section, *_section_visuals(section, render)) for suffix, section in sections]
    # Sections follow the order of the page: Overview, maps, RF Quality, Serving Cells, Network Deployment, Cluster Sites
    # Density, Spectrum.
    for suffix, section in sections:
        _docx_section_heading(document, f'Overview{suffix}', scope_text(selection))
        _docx_overview_cards(document, overview_cards(analysis, section))
    for suffix, _section, _cdfs, groups in visuals:
        for group, panels in groups:
            _docx_side_by_side(document, f'Coverage & Interference Maps{suffix}' + (f' · {group}' if group else ''),
                               [(caption, (image, note, table)) for caption, image, note, table in panels], add_image, new_page=True,
                               scope=scope_text(selection))
    for title, columns, rows in cell_status_tables(analysis):
        _docx_section_heading(document, title, scope_for(title, selection))
        _docx_table(document, columns, rows)
    for suffix, section, cdfs, _groups in visuals:
        if cdfs:
            _docx_side_by_side(document, f'RF Quality{suffix}', [(caption, (image, note, None)) for caption, image, note, _table in cdfs], add_image, new_page=True,
                               scope=scope_text(selection))
            columns, rows, bars = rf_quality_table(section, analysis.get('colours'))
            if rows:
                _docx_bar_table(document, columns, rows, bars)
    distance = serving_visuals(analysis, render)
    if distance:
        _docx_side_by_side(document, 'Serving Cells', [(caption, (image, note, None)) for caption, image, note, _table in distance], add_image, new_page=True,
                           scope=scope_text(selection))
    snapshot = snapshot_tables(deployment)
    for title, columns, rows in [*serving_tables(analysis), *[table for table in snapshot if not table[0].startswith(('Spectrum', 'Cluster'))]]:
        _docx_section_heading(document, title, scope_for(title, selection))
        _docx_table(document, columns, rows)
    for title, panels in deployment_table_groups(deployment):
        _docx_side_by_side(document, title, [(caption, (columns, rows)) for caption, columns, rows in panels], add_table,
                           scope=scope_for(title, selection))
    ladder = bandwidth_ladder_image(analysis)
    for title, columns, rows in [*cluster_sites_tables(analysis, deployment), *[table for table in snapshot if table[0].startswith('Cluster')],
                                 *spectrum_tables(analysis), *[table for table in snapshot if table[0].startswith('Spectrum')],
                                 *nr_duplex_table(deployment), *bandwidth_tables(analysis)]:
        if title.startswith('Spectrum · Total bandwidth') and ladder is not None:
            # The chart on a page of its own under its title and the line that explains its figures, then its figures.
            _docx_section_heading(document, bandwidth_title(analysis), scope_text(selection))
            page = document.sections[-1]
            caption = document.add_paragraph().add_run(bandwidth_caption(analysis))
            caption.font.color.rgb = DocxRGBColor(0xA8, 0x40, 0x4D)
            document.add_picture(ladder, width=DocxInches(min(10.0, (page.page_width - page.left_margin - page.right_margin) / 914400)))
        _docx_section_heading(document, title, scope_for(title, selection))
        _docx_table(document, columns, rows)
    document.save(destination)
    return destination

