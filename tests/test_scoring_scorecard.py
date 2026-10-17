"""The scorecard design of the Scoring and GAP tables (page, PowerPoint and Word), the export choices of a Saved
Filter and the compact Word reports."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document
from PIL import Image, ImageDraw
from pptx import Presentation
from pptx.oxml.ns import qn

import src.modules.pptx_to_docx as pptx_to_docx_module
from src.modules.scoring_exports import SECTION_TAG_PREFIX, export_scoring_powerpoint
from src.modules.scoring_pptx_scorecard import STYLES, drop_columns
from src.modules.scoring_themes import THEMES
from tests.scoring_synthetic import synthetic_result
from tests.test_scoring_exports import TEMPLATE

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCORING_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/scoring.js'
SCORING_TEMPLATE = PROJECT_ROOT / 'src/web_interface/templates/scoring.html'

# A small DOM with what the scorecard layout of the page uses.
FAKE_DOM = r"""
class TextNode { constructor(text) { this.tagName = '#text'; this.textContent = String(text); this.parentElement = null; this.children = []; } }
class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.parentElement = null; this.dataset = {};
    this.className = ''; this.title = ''; this.colSpan = 1; this.rowSpan = 1; this.scope = '';
    const styles = {};
    this.style = {backgroundColor: '', setProperty: (key, value) => { styles[key] = String(value); },
                  removeProperty: key => { delete styles[key]; if (key === 'background-color') this.style.backgroundColor = ''; },
                  getPropertyValue: key => styles[key] || ''};
    this.classList = {
      add: (...names) => { for (const name of names) if (!this.classList.contains(name)) this.className = `${this.className} ${name}`.trim(); },
      contains: name => this.className.split(/\s+/).includes(name),
    };
  }
  get childNodes() { return [...this.children]; }
  get textContent() { return this.children.map(child => child.textContent).join(''); }
  set textContent(value) { this.replaceChildren(new TextNode(value)); }
  detach(node) { if (node.parentElement) node.parentElement.children.splice(node.parentElement.children.indexOf(node), 1); node.parentElement = this; }
  append(...nodes) { for (const node of nodes) { this.detach(node); this.children.push(node); } }
  prepend(...nodes) { for (const node of nodes.reverse()) { this.detach(node); this.children.unshift(node); } }
  insertBefore(node, reference) { this.detach(node); const index = reference ? this.children.indexOf(reference) : -1;
    this.children.splice(index < 0 ? this.children.length : index, 0, node); }
  replaceChildren(...nodes) { for (const child of this.children) child.parentElement = null; this.children = []; this.append(...nodes); }
  remove() { if (this.parentElement) { this.parentElement.children.splice(this.parentElement.children.indexOf(this), 1); this.parentElement = null; } }
  querySelector(selector) { return all(this).slice(1).find(node => node.classList?.contains(selector.slice(1))) || null; }
  get rows() { return this.children.filter(node => node.tagName === 'TR'); }
  get cells() { return this.children.filter(node => node.tagName === 'TD' || node.tagName === 'TH'); }
  get tHead() { return this.children.find(node => node.tagName === 'THEAD') || null; }
  get tBodies() { return this.children.filter(node => node.tagName === 'TBODY'); }
  get tFoot() { return this.children.find(node => node.tagName === 'TFOOT') || null; }
}
function all(node) { return [node, ...(node.children || []).flatMap(all)]; }
const document = {createElement: tag => new Element(tag)};
function make(tag, text = '', options = {}) {
  const node = new Element(tag);
  if (text) node.textContent = text;
  for (const [key, value] of Object.entries(options)) {
    if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'background') node.style.backgroundColor = value;
    else node[key] = value;
  }
  return node;
}
function row(...cells) { const tr = make('tr'); tr.append(...cells); return tr; }
function describe(table) {
  const head = table.tHead.rows.map(tr => tr.cells.map(cell => [cell.textContent, cell.className, cell.colSpan, cell.rowSpan]));
  const body = table.tBodies[0].rows.map(tr => ({
    section: tr.classList.contains('scoring-section-row'),
    cells: tr.cells.map(cell => ({column: cell.dataset.column || '', text: cell.textContent, colSpan: cell.colSpan,
      badge: cell.querySelector('.scoring-kpi-badge')?.textContent || '', meta: cell.querySelector('.scoring-kpi-meta')?.textContent || '',
      tag: cell.querySelector('.scoring-kpi-category')?.textContent || '', name: cell.querySelector('.scoring-kpi-name')?.textContent || '',
      share: cell.style.getPropertyValue('--share'), tint: cell.style.getPropertyValue('--cell-tint'), background: cell.style.backgroundColor})),
  }));
  const foot = table.tFoot ? table.tFoot.rows.map(tr => tr.cells.map(cell => [cell.dataset.column || '', cell.textContent, cell.colSpan])) : [];
  return {className: table.className, head, body, foot};
}
"""


def _function_source(script: str, name: str) -> str:
    start = script.index(f'  function {name}(')
    end = script.index('\n  }', start) + len('\n  }')
    return script[start:end]


def _run_node(program: str) -> dict:
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for the scorecard checks.')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    helpers = '\n'.join(_function_source(script, name) for name in (
        'scorecardNumber', 'decorateScorecardLabel', 'decorateScorecardRow', 'applyScorecardLayout', 'markScorecardGroupEdges'))
    completed = subprocess.run([node, '-e', FAKE_DOM + helpers + program], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_scoring_tables_read_as_a_scorecard():
    result = _run_node(r"""
const table = make('table', '', {className: 'scoring-comparison-table'});
const thead = make('thead');
thead.append(
  row(make('th', 'CATEGORY', {rowSpan: 2, dataset: {column: 'category'}}), make('th', 'KPI', {rowSpan: 2, dataset: {column: 'kpi'}}),
      make('th', 'Type of KPI', {rowSpan: 2, dataset: {column: 'type'}}), make('th', 'Score weight (%)', {rowSpan: 2, dataset: {column: 'weight'}}),
      make('th', 'Max score', {rowSpan: 2, dataset: {column: 'maximum'}}),
      make('th', 'Score', {colSpan: 2, className: 'scoring-column-group scoring-score-group'})),
  row(make('th', 'EE', {className: 'scoring-operator-header', background: 'rgb(23, 160, 159)', dataset: {column: 'score'}}),
      make('th', 'O2', {className: 'scoring-operator-header', dataset: {column: 'score'}})));
const tbody = make('tbody');
const kpi = (category, name, type, weight, maximum, points, band, subtotal = false) => {
  const cells = [];
  if (category) cells.push(make('td', category.name, {className: 'scoring-category-cell', rowSpan: category.span, dataset: {column: 'category'}}));
  cells.push(make('td', name, {dataset: {column: 'kpi'}}));
  cells.push(make('td', type, {className: 'scoring-kpi-type-cell', dataset: {column: 'type', kpiType: type.toLowerCase() || 'neutral'}}));
  cells.push(make('td', weight, {dataset: {column: 'weight', numeric: 'true'}}), make('td', maximum, {dataset: {column: 'maximum', numeric: 'true'}}));
  for (const value of points) cells.push(make('td', value, {dataset: {column: 'score', numeric: 'true', band}, background: band ? '#DDEFD2' : ''}));
  const tr = row(...cells);
  if (subtotal) tr.classList.add('scoring-category-subtotal');
  return tr;
};
tbody.append(
  kpi({name: 'Voice', span: 3}, 'Call Setup', 'Reliable', '50.00', '500.00', ['400.00', '350.00'], 'High'),
  kpi(null, 'Drop Rate', 'Diff', '30.00', '300.00', ['150.00', '300.00'], 'Low'),
  kpi(null, 'Voice total', '—', '80.00', '800.00', ['550.00', '650.00'], '', true),
  kpi({name: 'Data', span: 2}, 'Throughput', 'Reliable', '20.00', '200.00', ['200.00', 'N/A*'], 'UltraHigh'),
  kpi(null, 'Data total', '—', '20.00', '200.00', ['200.00', 'N/A*'], '', true));
const tfoot = make('tfoot');
tfoot.append(row(make('th', 'Total', {dataset: {column: 'category'}}), make('td', 'Weighted score', {dataset: {column: 'kpi'}}),
  make('td', '—', {dataset: {column: 'type'}}), make('td', '100.00', {dataset: {column: 'weight'}}), make('td', '1000.00', {dataset: {column: 'maximum'}}),
  make('td', '750.00', {dataset: {column: 'score'}}), make('td', '650.00', {dataset: {column: 'score'}})));
table.append(thead, tbody, tfoot);
applyScorecardLayout(table);
process.stdout.write(JSON.stringify(describe(table)));
""")
    assert 'scoring-scorecard' in result['className']
    # The header starts with the operators: no Category, Type, Weight or Max columns, no lone Score group.
    assert [[cell[0] for cell in row] for row in result['head']] == [['KPI', 'EE', 'O2']]
    assert 'scoring-scorecard-corner' in result['head'][0][0][1] and result['head'][0][0][3] == 1
    # Each category opens a section with its subtotal; each KPI has its badge, weight and maximum.
    rows = result['body']
    assert [row['section'] for row in rows] == [True, False, False, True, False]
    labels = [row['cells'][0] for row in rows]
    assert [label['name'] for label in labels] == ['Voice', 'Call Setup', 'Drop Rate', 'Data', 'Throughput']
    assert [label['badge'] for label in labels] == ['', 'R', 'D', '', 'R']
    assert labels[1]['meta'] == '50.00% · 500.00 pts' and labels[0]['meta'] == '80.00% · 800.00 pts'
    assert all(len(row['cells']) == 3 for row in rows)
    # Every score keeps the share of its maximum and its band colour as a tint for the theme.
    call_setup = rows[1]['cells']
    assert (call_setup[1]['share'], call_setup[2]['share']) == ('0.800', '0.700')
    assert call_setup[1]['tint'] == '#DDEFD2' and call_setup[1]['background'] == ''
    assert rows[4]['cells'][2]['share'] == ''
    assert [cell[:2] for cell in result['foot'][0]] == [['kpi', 'Weighted score100.00% · 1000.00 pts'], ['score', '750.00'], ['score', '650.00']]


def test_gap_tables_get_sections_or_carry_the_category_of_each_kpi():
    result = _run_node(r"""
function gapTable(order) {
  const table = make('table', '', {className: 'scoring-comparison-table scoring-priority-table'});
  const thead = make('thead');
  thead.append(row(make('th', 'Category', {dataset: {column: 'category'}}), make('th', 'KPI', {dataset: {column: 'kpi'}}),
    make('th', 'Type of KPI', {dataset: {column: 'type'}}), make('th', 'VF − EE', {className: 'scoring-gap-header scoring-gap-operator-header', dataset: {column: 'gap'}})));
  const tbody = make('tbody');
  let previous = null;
  for (const [category, name, gap, span] of order) {
    const cells = [];
    if (category !== previous) cells.push(make('td', category, {className: 'scoring-category-cell', rowSpan: span, dataset: {column: 'category'}}));
    previous = category;
    cells.push(make('td', name, {dataset: {column: 'kpi'}}), make('td', 'Diff', {dataset: {column: 'type', kpiType: 'diff'}}),
      make('td', gap, {dataset: {column: 'gap', gap: gap.startsWith('−') ? 'loss' : 'gain'}, background: '#F4C7C7'}));
    tbody.append(row(...cells));
  }
  const tfoot = make('tfoot');
  tfoot.append(row(make('td', 'Total KPI GAP', {colSpan: 3}), make('td', '−1.00', {dataset: {column: 'gap'}})));
  table.append(thead, tbody, tfoot);
  applyScorecardLayout(table);
  return describe(table);
}
process.stdout.write(JSON.stringify({
  grouped: gapTable([['Voice', 'Call Setup', '−2.00', 2], ['Voice', 'Drop Rate', '+1.00', 2], ['Data', 'Throughput', '−0.50', 1]]),
  ordered: gapTable([['Voice', 'Call Setup', '−2.00', 1], ['Data', 'Throughput', '−0.50', 1], ['Voice', 'Drop Rate', '+1.00', 1]]),
}));
""")
    grouped = result['grouped']['body']
    assert [row['section'] for row in grouped] == [True, False, False, True, False]
    assert grouped[0]['cells'][0]['name'] == 'Voice' and grouped[0]['cells'][0]['meta'] == '2 KPIs'
    assert grouped[0]['cells'][0]['colSpan'] == 2 and grouped[3]['cells'][0]['meta'] == '1 KPI'
    assert grouped[1]['cells'][1]['tint'] == '#F4C7C7'
    # Ordered by GAP, the categories are apart: no sections, each KPI with its category.
    ordered = result['ordered']['body']
    assert not any(row['section'] for row in ordered)
    assert [row['cells'][0]['tag'] for row in ordered] == ['Voice', 'Data', 'Voice']
    assert result['ordered']['foot'][0][0] == ['kpi', 'Total KPI GAP', 1]


def test_every_theme_styles_the_scorecard_and_gaps_share_the_card_with_a_bar():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    for theme in THEMES:
        assert f'[data-scoring-theme="{theme}"] .scoring-comparison-table.scoring-scorecard' in template, theme
    # Every GAP is a card with a bar either side of zero, in the colours of the theme.
    assert re.search(r'td\[data-gap="gain"\]::after \{ left: 50%; background: var\(--sc-gain-bar\);', template)
    assert re.search(r'td\[data-gap="loss"\]::after \{ right: 50%; background: var\(--sc-loss-bar\);', template)
    # Ericsson fills each score as far as its share of the maximum; Midnight is the only dark theme.
    assert 'calc(var(--share, 0) * 100%), #f5f5f5 0)' in template
    assert THEMES['midnight']['surface'] == '#0F1726'
    for name, theme in THEMES.items():
        if name == 'midnight':
            continue
        red, green, blue = (int(theme['header'][index:index + 2], 16) for index in (1, 3, 5))
        assert name == 'netcheck' or .299 * red + .587 * green + .114 * blue > 140 or name in {'ericsson', 'vodafone'}, name
    # Heatmap is light everywhere: its headers and bands too.
    assert all(min(int(color[index:index + 2], 16) for index in (1, 3, 5)) > 190 for color in THEMES['heatmap']['bands'].values())
    assert set(STYLES) == set(THEMES)


def _slides_titled(deck, prefix):
    return [slide for slide in deck.slides if slide.shapes.title is not None
            and slide.shapes.title.text_frame.text.split('\n')[0].startswith(prefix)]


def test_powerpoint_tables_have_the_scorecard_design_of_the_theme():
    job, result = synthetic_result(levels=('Operator',))
    for theme in ('netcheck', 'ericsson', 'midnight'):
        deck = Presentation(BytesIO(export_scoring_powerpoint(job, result, TEMPLATE, theme=theme,
                                                              scorings=['best_network'], environments=['Combined'])))
        breakdown = _slides_titled(deck, 'Scoring Tables — Breakdown')[0]
        table = next(shape.table for shape in breakdown.shapes if shape.has_table and len(shape.table.columns) > 3)
        headers = [cell.text for cell in table.rows[0].cells]
        assert headers[0] == 'KPI' and not {'CATEGORY', 'Type of KPI', 'Score weight\n(%)', 'Max score'} & set(headers)
        labels = [row.cells[0].text for row in list(table.rows)[1:]]
        # A section per category (its subtotal first), then its KPIs with their badge, weight and maximum.
        assert labels[0].startswith('CLASSIC CALLS') and ' pts' in labels[0]
        assert labels[1].startswith(('R  ', 'D  ')) and labels[1].endswith(' pts')
        assert labels[-1].startswith('Weighted score')
        # The scores fill their cells as far as their share of the maximum.
        fills = [row.cells[1]._tc.tcPr.find(qn('a:gradFill')) for row in list(table.rows)[2:-1]]
        assert any(fill is not None for fill in fills), theme
        gap_slide = _slides_titled(deck, 'GAP Analysis — All vs')[0]
        gap_table = next(shape.table for shape in gap_slide.shapes if shape.has_table)
        assert gap_table.rows[0].cells[0].text == 'NetCheck KPIs'
        assert 'Type of KPI' not in [cell.text for cell in gap_table.rows[0].cells]
        assert gap_table.rows[1].cells[0].text.endswith('KPIs')
        # The cells are set apart by the lines of the theme, never a dark grid.
        borders = {line.get('val') for line in table._tbl.iter(qn('a:srgbClr')) if line.getparent().getparent().tag == qn('a:lnL')}
        assert '65717A' not in borders


def test_drop_columns_keeps_a_label_merged_across_them():
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[6])
    table = slide.shapes.add_table(2, 4, 0, 0, 4000000, 800000).table
    table.cell(1, 0).merge(table.cell(1, 2))
    table.cell(1, 0).text = 'Total KPI GAP'
    drop_columns(table, {0, 2})
    assert len(table.columns) == 2
    assert table.cell(1, 0).text == 'Total KPI GAP' and not table.cell(1, 0).is_merge_origin


def test_exports_keep_the_chosen_scorings_and_environments_and_name_their_sections():
    job, result = synthetic_result(levels=('Operator',))
    full = Presentation(BytesIO(export_scoring_powerpoint(job, result, TEMPLATE)))
    chosen = Presentation(BytesIO(export_scoring_powerpoint(job, result, TEMPLATE, scorings=['best_network'],
                                                            environments=['Combined'])))
    assert len(chosen.slides) < len(full.slides)
    titles = [slide.shapes.title.text_frame.text for slide in chosen.slides if slide.shapes.title is not None]
    assert not any('Most Reliable' in title for title in titles)
    sections = [str(slide._element.cSld.get('name')) for slide in chosen.slides]
    assert all(name.startswith(SECTION_TAG_PREFIX) for name in sections)
    names = list(dict.fromkeys(name[len(SECTION_TAG_PREFIX):] for name in sections))
    assert names == ['cover', 'summary', 'charts', 'tables', 'gap', 'points']
    with pytest.raises(ValueError, match='None of the selected environments'):
        export_scoring_powerpoint(job, result, TEMPLATE, environments=['Nowhere'])


def test_word_reports_merge_covers_and_pack_each_section(monkeypatch):
    job, result = synthetic_result(levels=('Operator',))
    content = export_scoring_powerpoint(job, result, TEMPLATE, scorings=['best_network'], environments=['Combined'])
    # The report cover takes the title of the first scoring under its own title.
    merged = Presentation(BytesIO(pptx_to_docx_module.merge_cover_slides(content)))
    original = Presentation(BytesIO(content))
    assert len(merged.slides) == len(original.slides) - 1
    cover_texts = [shape.text_frame.text for shape in merged.slides[0].shapes if shape.has_text_frame]
    assert 'Scoring & GAP Analysis' in cover_texts and 'Best Network Scoring' in cover_texts

    # A slide image keeps its blocks and loses its empty bands.
    image = Image.new('RGB', (400, 300), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 380, 60), fill='black')
    draw.rectangle((20, 250, 380, 270), fill='black')
    raw = BytesIO()
    image.save(raw, format='PNG')
    with Image.open(BytesIO(pptx_to_docx_module.compact_slide_image(raw.getvalue()))) as compact:
        assert compact.width == 400 and compact.height < 120

    # Portrait pages: the cover fills a page of its own without margins, then each section starts a new page with
    # as many of its slides as fit.
    sections = pptx_to_docx_module.slide_sections(merged)
    monkeypatch.setattr(pptx_to_docx_module, 'slide_images', lambda *_args, **_kwargs: [raw.getvalue()] * len(sections))
    document = Document(BytesIO(pptx_to_docx_module.pptx_to_docx(content, 'Scoring & GAP Analysis', pack_sections=True)))
    breaks = [bool(paragraph.paragraph_format.page_break_before) for paragraph in document.paragraphs]
    assert len(breaks) == len(sections) and len(document.sections) == 2
    cover_page, pages = document.sections
    assert cover_page.left_margin == cover_page.top_margin == 0 and pages.left_margin > 0
    assert pages.page_height > pages.page_width
    assert breaks[:2] == [False, False]
    # Every section starts a new page; within a section, a new page only once the page is full.
    changes = [index for index in range(2, len(sections)) if sections[index] != sections[index - 1]]
    assert all(breaks[index] for index in changes)
    for index in range(2, len(sections)):
        if breaks[index] and index not in changes:
            assert not any(breaks[index - offset] for offset in range(1, 5)), index
