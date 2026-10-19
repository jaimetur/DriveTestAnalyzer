from pathlib import Path
import re
import json
import shutil
import subprocess

import pytest

from src.modules.scoring_themes import THEMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCORING_TEMPLATE = PROJECT_ROOT / 'src/web_interface/templates/scoring.html'
SCORING_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/scoring.js'


def _function_source(script: str, name: str) -> str:
    marker = f'  function {name}('
    if marker not in script:
        marker = f'  async function {name}('
    start = script.index(marker)
    end = script.index('\n  }', start) + len('\n  }')
    return script[start:end]


def _constant_source(script: str, name: str) -> str:
    start = script.index(f'  const {name} =')
    end = script.index('\n  };', start) + len('\n  };')
    return script[start:end]


# The colour theme the functions of the page read: NetCheck, whose colours stay as the views write them.
THEME_PRELUDE = ('const activeTheme = ' + json.dumps({'id': 'netcheck', **THEMES['netcheck']}) + ';\n'
                 'const scoringThemes = [activeTheme];\n'
                 'const themedColor = (color) => color;\n'
                 'const hexChannels = (color) => [1, 3, 5].map((index) => Number.parseInt(color.slice(index, index + 2), 16));\n'
                 'const rgbaOf = (color, alpha) => `rgba(${hexChannels(color).join(",")},${alpha})`;\n'
                 # The contexts the checks run the page code in get the theme too.
                 '{ const vm = require("node:vm"); const createContext = vm.createContext;\n'
                 '  const bindings = {activeTheme, scoringThemes, themedColor, hexChannels, rgbaOf};\n'
                 '  vm.createContext = (context = {}, ...rest) => createContext(Object.assign(context, {...bindings, ...context}), ...rest); }\n')


def _run_node_json(program: str, payload: dict) -> dict:
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for scoring results state behavior checks.')
    completed = subprocess.run(
        [node, '-e', THEME_PRELUDE + program], input=json.dumps(payload), capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_results_environment_stays_visible_while_loading_and_exports_selected_scope():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    assert "let selectedEnvironment = restoredScoringViewState.environment || 'all';" in script
    assert "return ordered.length || combinedIsAvailable ? ['all', ...ordered] : [];" in script
    assert "selectedEnvironment === 'all'" in script
    assert "const combinedIsAvailable = tables.some(table => environmentOf(table) === 'Combined');" in script
    assert "? (combinedIsAvailable ? 'Combined' : null)" in script
    assert "actual[0]" not in script
    assert '&environment=${encodeURIComponent(selectedEnvironment || \'all\')}' in script
    assert 'All Environments' in script
    assert 'defaults to the first complete environment when all environments are incomplete' in template


def test_best_network_chart_keeps_its_intrinsic_width_on_narrow_cards():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    assert re.search(
        r'\.scoring-chart-svg\.scoring-best-network-bars\s*\{[^}]*min-width:\s*0;'
        r'[^}]*max-width:\s*none;[^}]*min-height:\s*0;', template,
    )
    assert "svg.style.minWidth = '0';" in script
    assert "svg.style.width = `${100 * width / visibleWidth}%`;" in script
    assert "svg.style.maxWidth = 'none';" in script
    assert "scroll.className = 'scoring-chart-scroll';" in script
    assert 'const baseHeight = 620;' in script
    assert 'const plotHeight = baseHeight - 72 - bottom;' in script
    assert 'const scale = scoringChartScale(maxAllocation, maxActual);' in script


def test_best_network_charts_start_scoring_charts_and_legacy_tab_migrates():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    assert 'data-result-tab="best-network"' not in template
    assert "const resultTabNames = new Set(['summary', 'charts', 'scoring', 'geographical-areas', 'trends', 'gap', 'points']);" in script
    assert "stored.result_tab === 'best-network' ? 'charts'" in script
    renderer = _function_source(script, 'renderBestNetworkChart')
    allocation_renderer = _function_source(script, 'renderCategoryAllocation')
    assert allocation_renderer.index("makeExpandableChartCard('Maximum score per environment & category'") >= 0
    assert "pane.insertBefore(layout, card)" in allocation_renderer
    assert renderer.index("makeExpandableChartCard(`${scoringLabel()} Scoring per Service`") < renderer.index(
        "makeExpandableChartCard('Maximum score per environment & service'"
    )
    assert "pane.insertBefore(layout, pane.querySelector(':scope > .scoring-best-network-layout, :scope > .scoring-chart-card'))" in renderer
    assert "renderBestNetworkChart(chartPane, scoreTables, hierarchyScoreTable, allScoreTables)" in script
    assert "renderCategoryAllocation(chartPane, scoreTables, hierarchyScoreTable, allScoreTables)" in script
    assert script.index('renderCategoryAllocation(chartPane,') < script.index('renderBestNetworkChart(chartPane,')
    assert '`${scoringLabel()} Scoring per Category`' in script
    assert "effectiveScoring() === 'most_reliable' ? 'Most Reliable Network' : 'Best Network'" in script
    assert 'Scoring per Category' in script

    payload = {
        'snippets': {
            'readScoringViewState': _function_source(script, 'readScoringViewState'),
        },
        'storageKey': 'drivetest-analyzer:scoring-view:test:workspace',
        'legacyState': {'result_tab': 'best-network'},
    }
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const values = new Map([[payload.storageKey, JSON.stringify(payload.legacyState)]]);
const context = {
  scoringViewStorageKey: payload.storageKey,
  resultTabNames: new Set(['scoring', 'gap', 'charts']),
  window: {sessionStorage: {getItem: key => values.get(key) ?? null}},
};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n') + '\nglobalThis.restored = readScoringViewState();', context);
process.stdout.write(JSON.stringify(context.restored));
"""
    result = _run_node_json(program, payload)
    assert result['resultTab'] == 'charts'


def test_scoring_table_value_row_is_hidden_outside_scoring_tab_without_changing_options():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    assert 'data-scoring-results-value-row' in template

    payload = {'snippet': _function_source(script, 'syncResultTableControls')}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const row = {hidden: false};
const context = {
  row,
  root: {querySelector: selector => selector === '[data-scoring-results-value-row]' ? row : null},
  activeResultTab: 'scoring',
  showKpiValuesToggle: {checked: true},
  showGapValuesToggle: {checked: false},
};
vm.createContext(context);
vm.runInContext(payload.snippet + `
const visibility = {};
for (const tab of ['scoring', 'gap', 'charts']) {
  activeResultTab = tab;
  syncResultTableControls();
  visibility[tab] = {hidden: row.hidden, options: [showKpiValuesToggle.checked, showGapValuesToggle.checked]};
}
globalThis.result = visibility;`, context);
process.stdout.write(JSON.stringify(context.result));
"""
    result = _run_node_json(program, payload)
    assert result == {
        'scoring': {'hidden': False, 'options': [True, False]},
        'gap': {'hidden': True, 'options': [True, False]},
        'charts': {'hidden': True, 'options': [True, False]},
    }


def test_incomplete_web_values_render_na_star_in_red_bold():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    payload = {
        'snippets': {
            'firstValue': _function_source(script, 'firstValue'),
            'formatMatrixNumber': _function_source(script, 'formatMatrixNumber'),
            'formatScoreCell': _function_source(script, 'formatScoreCell'),
            'formatRawKpiValue': _function_source(script, 'formatRawKpiValue'),
            'styleIncompleteValue': _function_source(script, 'styleIncompleteValue'),
        },
    }
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n') + `
const cases = [
  formatMatrixNumber(null),
  formatScoreCell({points: 12.345, complete: false}).text,
  formatRawKpiValue(null),
];
globalThis.results = cases.map(text => {
  const element = {textContent: text, style: {}};
  styleIncompleteValue(element);
  return {text, color: element.style.color, fill: element.style.fill, fontWeight: element.style.fontWeight};
});`, context);
process.stdout.write(JSON.stringify(context.results));
"""
    result = _run_node_json(program, payload)
    assert result == [
        {'text': 'N/A*', 'color': '#c62828', 'fill': '#c62828', 'fontWeight': '700'},
        {'text': '12.35*', 'color': '#c62828', 'fill': '#c62828', 'fontWeight': '700'},
        {'text': 'N/A*', 'color': '#c62828', 'fill': '#c62828', 'fontWeight': '700'},
    ]


def test_results_controls_are_grouped_with_icons_and_unique_environment_heading():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    from lxml import html
    tree = html.fromstring(template)
    shortcut_navs = tree.xpath('//nav[@aria-label="Scoring configuration sections"]')
    assert len(shortcut_navs) == 2
    for nav in shortcut_navs:
        kpi_shortcut = nav.xpath('./a[@data-config-shortcut="kpi"]')[0]
        assert kpi_shortcut.get('href') == '/workspace-config#scoring-methodology-environments'
        assert kpi_shortcut.xpath('./span')[0].text == 'Scoring Methodologies'
        # The Calculation toolbar generates a report from the selection; the Results toolbar exports the selected job.
        report = nav.xpath('following-sibling::div[@class="scoring-export-actions"]/a[@data-generate-report or @data-export-ppt]')
        assert report and report[0].xpath('./span')[0].text in {
            'Generate Scoring Report (PPT/Word)', 'Export Selected Scoring Report (PPT/Word)'}
        assert kpi_shortcut.xpath('./svg/path/@d') == [
            'M2 17h16M3 17V7h5v10M5 10h1M5 13h1M12 3l-2 14M16 3l2 14M14 4v2m0 3v2m0 3v2',
        ]
        # Only Methodology stays here: KPI Priorities is gone and the hierarchy lives in Split by.
        assert not nav.xpath('./a[@data-config-shortcut="gap"]')
        assert not nav.xpath('./a[@data-config-shortcut="hierarchy"]')
    labels = [link.xpath('./span')[0].text for link in tree.xpath('//div[@class="scoring-export-actions"]/a')]
    assert labels == ['Generate Scoring Report (PPT/Word)', 'Export Selected Scoring Report (PPT/Word)']
    # The former PowerPoint and Word buttons of the Calculation panel are gone.
    assert 'data-scoring-document-export' not in template
    hierarchy = tree.xpath('//a[@data-config-shortcut="hierarchy"]')
    # It opens a dialog on this page to order the application's aggregation hierarchy.
    assert len(hierarchy) == 1 and hierarchy[0].get('href') == '#' and hierarchy[0].get('data-scoring-hierarchy-open') is not None
    dialog = tree.xpath('//dialog[@data-scoring-hierarchy-dialog]')[0]
    assert 'shared by every workspace and methodology' in dialog.text_content()
    assert not dialog.xpath('.//*[@data-scoring-hierarchy-methodology]')
    # On the line of the Split by levels, at its right, with the note below the levels.
    panel = hierarchy[0].xpath('ancestor::div[@class="scoring-levels-row"]/parent::div')[0]
    assert panel.xpath('./div[@class="scoring-picker-head"]/strong')[0].text == 'Split by'
    assert panel.xpath('./p[contains(@class, "scoring-levels-note")]')[0].text == 'Operator is required.'
    header = re.search(r'<div class="scoring-results-head">(.*?)<div class="scoring-results-tabbed">', template, re.S)
    assert header
    markup = header.group(1)
    primary = re.search(r'<div class="scoring-results-primary">(.*?)</div>\s*<div class="scoring-results-tools">', markup, re.S)
    tools = re.search(r'<div class="scoring-results-tools">(.*)</div>\s*$', markup, re.S)
    assert primary and tools
    left_markup = primary.group(1)
    right_markup = tools.group(1)
    assert left_markup.index('data-result-environment-control') < left_markup.index('data-scoring-results-value-row')
    assert left_markup.index('data-show-kpi-values') < left_markup.index('data-show-gap-values')
    assert right_markup.index('data-config-shortcut="kpi"') < right_markup.index('data-export-ppt')
    assert 'data-export-scoring' not in right_markup and 'data-export-gap' not in right_markup
    for marker in ('data-config-shortcut="kpi"', 'data-export-ppt'):
        anchor = re.search(rf'<a\b[^>]*{re.escape(marker)}[^>]*>(.*?)</a>', right_markup, re.S)
        assert anchor and '<svg ' in anchor.group(1) and 'viewBox="0 0 20 20"' in anchor.group(1)
    assert re.search(r'<a\b[^>]*data-export-ppt[^>]*>.*?<span>Export Selected Scoring Report \(PPT/Word\)</span></a>', right_markup, re.S)
    # Export to CSV sits above the Scoring and GAP tables, in the GAP export colour.
    for pane, marker in (('scoring', 'data-export-scoring'), ('gap', 'data-export-gap')):
        toolbar = re.search(rf'<div class="scoring-table-export" data-table-export="{pane}">(.*?)</div>', template, re.S)
        assert toolbar and marker in toolbar.group(1) and '<span>Export to CSV</span>' in toolbar.group(1)
        assert template.index(f'data-result-pane="{pane}"') < template.index(f'data-table-export="{pane}"')
    assert '.scoring-table-export a {' in template and 'linear-gradient(135deg,#1688bb,#145584)' in template
    # The job selector takes the width the controls leave, not the width of the buttons row.
    assert '.scoring-results-head { display: grid; grid-template-columns: fit-content(38rem) minmax(0,1fr);' in template
    assert '.scoring-results-tools { grid-column: 2; grid-row: 1; display: flex; align-items: center; justify-content: flex-end; flex-wrap: nowrap;' in template
    assert '.scoring-results-config-shortcuts svg, .scoring-export-actions svg {' in template
    assert 'fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round;' in template
    assert '.scoring-results-config-shortcuts, .scoring-results-tools > .scoring-export-actions { justify-content: flex-end; }' in template

    payload = {
        'snippets': {
            'hierarchyDisplayValue': _function_source(script, 'hierarchyDisplayValue'),
            'appendContextHeader': _function_source(script, 'appendContextHeader'),
            'environmentLabel': _function_source(script, 'environmentLabel'),
            'humanizeKey': _function_source(script, 'humanizeKey'),
            'resultScope': _function_source(script, 'resultScope'),
            'appendResultScope': _function_source(script, 'appendResultScope'),
            'resultScopeFilters': 'const resultScopeFilters = {};',
        },
    }
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.className = ''; this.ownText = ''; this.dataset = {}; }
  set textContent(value) { this.ownText = String(value); this.children = []; }
  get textContent() { return this.ownText + this.children.map(child => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
}
const document = {createElement: tag => new Element(tag)};
const context = {document, Element, displayValue: value => String(value)};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n') + `
const results = [];
for (const [kind, title] of [['score', 'Scoring Tables'], ['gap', 'GAP Analysis'], ['charts', 'Scoring Charts']]) {
  const pane = new Element('section');
  appendContextHeader(pane, {context: {environment: 'DriveCity', campaign: '2026Q2', city: 'London'}}, kind, title);
  const heading = pane.children[0];
  results.push({
    title: heading.ownText,
    environmentChips: heading.children.filter(child => child.className.includes('scoring-environment-chip')).map(child => child.textContent),
    otherContextChips: pane.children.filter(child => child.className === 'scoring-context-chips')
      .flatMap(group => group.children.map(child => child.textContent)),
    pills: heading.children.filter(child => child.className.startsWith('scoring-scope-pill')).map(child => child.textContent),
  });
}
globalThis.result = results;`, context);
process.stdout.write(JSON.stringify(context.result));
"""
    result = _run_node_json(program, payload)
    assert [item['title'] for item in result] == ['Scoring Tables', 'GAP Analysis', 'Scoring Charts']
    assert all(item['environmentChips'] == ['Environment: Drive City'] for item in result)
    assert all('Environment:' not in ' '.join(item['otherContextChips']) for item in result)
    # The heading of the GAP tables is their title: it names their area, operators and vendors; Scoring Tables and
    # Charts name them in the title of each table and chart.
    assert [item['pills'] for item in result] == [[], ['City: London', 'All Operators', 'All Vendors'], []]


def test_category_allocation_donut_uses_configured_maxima_order_and_tooltips():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    names = (
        'formatChartNumber', 'maximumAllocationEnvironments', 'maximumAllocationCategories',
        'allocationEnvironmentLabel', 'allocationCategoryLabel', 'allocationIconPath', 'allocationSectorPath',
        'wrappedSvgLabelLines', 'safeHexColor', 'readableTextColor', 'makeMaximumAllocationDonut',
    )
    payload = {
        'snippets': {name: _function_source(script, name) for name in names},
        'configuration': {
            'scope': {'environments': {'DriveCity': {'total_points': 100}, 'UrbanRoad': {'total_points': 50}}},
            'metrics': [
                {'category': 'Calls', 'source_kind': 'voice', 'contexts': {
                    'DriveCity': {'max_points': 30}, 'UrbanRoad': {'max_points': 8},
                }},
                {'category': 'Connectivity', 'source_kind': 'data', 'contexts': {
                    'DriveCity': {'max_points': 50}, 'UrbanRoad': {'max_points': 10},
                }},
                {'category': 'Calls', 'source_kind': 'speech', 'contexts': {
                    'DriveCity': {'max_points': 20}, 'UrbanRoad': {'max_points': 7},
                }},
            ],
        },
    }
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor(tagName) { this.tagName = tagName; this.namespaceURI = 'svg'; this.attributes = {}; this.children = []; this.style = {}; this.textContent = ''; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  append(...nodes) { this.children.push(...nodes); this.textContent += nodes.map(node => node.textContent || '').join(''); }
}
const document = {createElementNS: (_namespace, tag) => new Element(tag)};
const helpers = `
function svgElement(svg, name, attributes = {}) {
  const node = document.createElementNS(svg.namespaceURI, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  return node;
}
function setChartTooltip(node, message) { node.setAttribute('data-chart-tooltip', String(message)); }
function formattedChartPoints(value) { return Number(value).toLocaleString(undefined, {maximumFractionDigits: 3}); }
function bestNetworkTotals(table) { return {allocation: table.allocation || {Voice: 0, Data: 0}}; }
`;
const context = {document, console, payload};
vm.createContext(context);
vm.runInContext(helpers + Object.values(payload.snippets).join('\n') + `
const selected = {context: {environment: 'Combined'}, rows: [
  {category: 'Calls', max_points: 30}, {category: 'Connectivity', max_points: 60},
  {category: 'Calls', max_points: 35}, {category: 'Ignored', max_points: 999, row_type: 'category'},
]};
const environments = maximumAllocationEnvironments(selected, [], payload.configuration);
const categories = maximumAllocationCategories(selected, environments, payload.configuration);
const chart = makeMaximumAllocationDonut(environments, categories);
const tinyChart = makeMaximumAllocationDonut([
  {name: 'Tiny', Voice: 1.4, Data: 0, color: '#176E77'},
  {name: 'Large', Voice: 98.6, Data: 0, color: '#E6A81D'},
], [
  {label: 'Tiny KPI', value: 1.4, color: '#C55A11'},
  {label: 'Large KPI', value: 98.6, color: '#7030A5'},
]);
const singleEnvironmentChart = makeMaximumAllocationDonut([
  {name: 'DriveCity', Voice: 100, Data: 0, color: '#176E77'},
]);
const walkConfiguration = {
  scope: {environments: {
    'Walk City': {total_points: 500}, 'Walk Connection Road': {total_points: 300}, 'Zero Walk': {total_points: 0},
  }},
  metrics: [
    {source_kind: 'voice', contexts: {
      'Walk City': {max_points: 300}, 'Walk Connection Road': {max_points: 200}, 'Zero Walk': {max_points: 0},
    }},
    {source_kind: 'data', contexts: {
      'Walk City': {max_points: 200}, 'Walk Connection Road': {max_points: 100}, 'Zero Walk': {max_points: 0},
    }},
  ],
};
const walkEnvironments = maximumAllocationEnvironments({context: {environment: 'Combined'}}, [], walkConfiguration);
const walkSingleEnvironment = maximumAllocationEnvironments({context: {environment: 'Walk City'}}, [], walkConfiguration);
const walkChart = makeMaximumAllocationDonut(walkEnvironments);
const walkSingleChart = makeMaximumAllocationDonut(walkSingleEnvironment);
const environmentIcons = svg => svg.children.filter(item => item.attributes['data-allocation-environment-icon'])
  .map(item => ({...item.attributes, tooltip: item.attributes['data-chart-tooltip']}));
const legendYValues = svg => svg.children.filter(item => item.tagName === 'text'
  && ['74', '94'].includes(item.attributes.x)).map(item => Number(item.attributes.y));
const walkIcons = environmentIcons(walkChart);
const walkSingleIcons = environmentIcons(walkSingleChart);
const unpackIcon = icon => {
  const [translation, scaleText] = icon.transform.split(' scale(');
  const [x, y] = translation.slice('translate('.length, -1).split(' ');
  const scale = Number(scaleText.slice(0, -1));
  const iconSize = 24 * scale;
  const centerX = Number(x) + iconSize / 2, centerY = Number(y) + iconSize / 2;
  return {label: icon['data-allocation-environment-icon'], path: icon.d, scale: Number(scale),
    centerX, centerY, iconSize, left: centerX - iconSize / 2, top: centerY - iconSize / 2,
    right: centerX + iconSize / 2, bottom: centerY + iconSize / 2,
    tooltip: icon.tooltip};
};
const fallback = maximumAllocationCategories(selected, [], {});
globalThis.result = {
  environments: environments.map(item => [item.name, item.Voice, item.Data]),
  categories: categories.map(item => [item.label, item.value]),
  fallback: fallback.map(item => [item.label, item.value]),
  viewBox: chart.attributes.viewBox,
  segmentTooltips: chart.children.filter(item => item.attributes['data-allocation-segment']).map(item => item.attributes['data-chart-tooltip']),
  segmentGeometry: chart.children.filter(item => item.attributes['data-allocation-segment'])
    .map(item => [item.attributes['data-allocation-segment'], item.attributes['data-allocation-radius'], item.attributes['data-allocation-center'], item.attributes.d]),
  percentageLabels: chart.children.filter(item => item.attributes['data-allocation-percentage']).map(item => ({
    value: item.attributes['data-allocation-percentage'], style: item.attributes.style,
    tooltip: item.attributes['data-chart-tooltip'],
  })),
  tinyPercentageLabels: tinyChart.children.filter(item => item.attributes['data-allocation-percentage'])
    .map(item => item.attributes['data-allocation-percentage']),
  singleEnvironmentPercentages: singleEnvironmentChart.children
    .filter(item => item.attributes['data-allocation-percentage']).map(item => item.attributes['data-allocation-percentage']),
      legend: chart.children.filter(item => item.tagName === 'text' && ['18', '74', '94'].includes(item.attributes.x)).map(item => ({
        text: item.children.length ? item.children.map(child => child.textContent).join('') : item.textContent,
        x: item.attributes.x, y: item.attributes.y, style: item.attributes.style,
        amountColor: item.children[1]?.attributes.fill,
      })),
  icons: chart.children.filter(item => item.tagName === 'path' && item.attributes.transform).map(item => item.attributes.d),
  representativeIcons: [allocationIconPath('Classic Calls'), allocationIconPath('WhatsApp Calls')],
  walkNames: walkEnvironments.map(item => item.name),
  walkIcons: walkIcons.map(unpackIcon), walkSingleIcons: walkSingleIcons.map(unpackIcon),
  walkViewBox: walkChart.attributes.viewBox, walkSingleViewBox: walkSingleChart.attributes.viewBox,
  walkLegendY: Math.min(...legendYValues(walkChart)), walkSingleLegendY: Math.min(...legendYValues(walkSingleChart)),
  walkLegendIconCount: walkChart.children.filter(item => item.tagName === 'path' && item.attributes.transform
    && !item.attributes['data-allocation-environment-icon']).length,
  expectedWalkPaths: [allocationIconPath('Walk City'), allocationIconPath('Walk Connection Road')],
};`, context);
process.stdout.write(JSON.stringify(context.result));
"""
    result = _run_node_json(program, payload)

    assert result['environments'] == [['DriveCity', 50, 50], ['UrbanRoad', 15, 10]]
    assert result['categories'] == [['Calls', 65], ['Connectivity', 60]]
    assert result['fallback'] == [['Calls', 65], ['Connectivity', 60]]
    assert result['viewBox'].startswith('0 0 460 ')
    assert [segment[:3] for segment in result['segmentGeometry']] == [
        ['Environments', '134.16', '230,230'], ['Environments', '134.16', '230,230'],
        ['KPI categories', '89.54079999999999', '230,230'], ['KPI categories', '89.54079999999999', '230,230'],
    ]
    assert all(segment[3].startswith('M ') and ' A ' in segment[3] and ' Z' in segment[3]
               for segment in result['segmentGeometry'])
    assert all('stroke-dasharray' not in segment[3] for segment in result['segmentGeometry'])
    assert [tooltip.splitlines()[0] for tooltip in result['segmentTooltips']] == [
        'Environments: DriveCity', 'Environments: UrbanRoad',
        'KPI categories: Calls', 'KPI categories: Connectivity',
    ]
    assert 'Maximum points: 100' in result['segmentTooltips'][0]
    assert [item['value'] for item in result['percentageLabels']] == ['80.0%', '20.0%', '52.0%', '48.0%']
    assert all(11 <= float(re.search(r'font-size:([\d.]+)px', item['style']).group(1)) <= 14
               and 'font-weight:700' in item['style'] for item in result['percentageLabels'])
    assert all(' of configured maximum' in item['tooltip'] for item in result['percentageLabels'])
    assert '1.4%' not in result['tinyPercentageLabels']
    assert {'98.6%'} <= set(result['tinyPercentageLabels'])
    assert result['singleEnvironmentPercentages'] == ['100.0%', '100.0%']
    assert result['walkNames'] == ['Walk City', 'Walk Connection Road']
    assert [icon['label'] for icon in result['walkIcons']] == result['walkNames']
    assert [icon['path'] for icon in result['walkIcons']] == result['expectedWalkPaths']
    assert len(result['walkSingleIcons']) == 1
    assert result['walkSingleIcons'][0]['label'] == 'Walk City'
    assert result['walkSingleIcons'][0]['path'] == result['expectedWalkPaths'][0]
    assert all(icon['iconSize'] == 42 and icon['scale'] == pytest.approx(42 / 24)
               for icon in [*result['walkIcons'], *result['walkSingleIcons']])
    for view_box, icons, legend_y in (
        (result['walkViewBox'], result['walkIcons'], result['walkLegendY']),
        (result['walkSingleViewBox'], result['walkSingleIcons'], result['walkSingleLegendY']),
    ):
        width, height = view_box.split()[2:]
        width, height = int(width), int(height)
        assert all(0 <= icon['left'] < icon['right'] <= width
                   and 0 <= icon['top'] < icon['bottom'] < height for icon in icons)
        assert max(icon['bottom'] for icon in icons) < legend_y
        assert all(legend_y >= 480 for _icon in icons)
        assert all(((icon['centerX'] - 230) ** 2 + (icon['centerY'] - 230) ** 2) ** .5
                   == pytest.approx(189)
                   for icon in icons)
    assert result['walkLegendIconCount'] > len(result['walkIcons'])
    assert all('Environment:' in icon['tooltip'] and 'Maximum points:' in icon['tooltip']
               for icon in result['walkIcons'])
    assert 'Walk Connection Road' in result['walkIcons'][1]['tooltip']
    assert result['walkSingleLegendY'] >= 480
    assert [item['text'] for item in result['legend']] == [
        'Total Points: 125 pts (100.0%)', 'Points per Environment:', 'Drive - City: 100 pts (80.0%)',
        'UrbanRoad: 25 pts (20.0%)', 'Points per KPI Category:', 'Calls: 65 pts (52.0%)',
        'Connectivity: 60 pts (48.0%)',
    ]
    assert result['legend'][0]['x'] == '74'
    assert [item['x'] for item in result['legend'][1:]] == ['18', '94', '94', '18', '94', '94']
    assert 'font-weight:700' in result['legend'][1]['style']
    assert 'font-weight:400' in result['legend'][2]['style']
    assert all(float(re.search(r'font-size:([\d.]+)px', item['style']).group(1)) <= 14 for item in result['legend'] if item['x'] != '18')
    assert all(item['amountColor'] == '#8A3D0A' for item in result['legend'] if item['x'] in {'74', '94'})
    assert len(set(result['representativeIcons'])) == 2


def test_scoring_chart_pairs_render_five_operator_two_category_views():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    names = (
        'firstValue', 'isReferenceOperator', 'operatorPresentation', 'safeHexColor',
        'scoringChartScale', 'configuredChartMaximum',
        'wrappedSvgLabelLines', 'fittedSvgLabelLines', 'setChartTooltip', 'formattedChartPoints',
        'chartEnvironmentName', 'categoryLegendGray', 'chartCategoryLegend', 'chartLegendTextWidth',
        'chartLegendRows', 'categoryLegendTextLines', 'categoryLegendTextColor',
        'formatChartNumber', 'stackedSegmentLabelSize', 'bestNetworkHorizontalGeometry',
        'fitBestNetworkChartWidth', 'makeSvgChart', 'makeBestNetworkBars', 'lightenHexColor',
        'hierarchyColumnOperator', 'hierarchyColumnIsReference', 'chartOperatorLegend',
        'makeExpandableChartCard', 'effectiveScoring', 'scoringLabel',
        'renderCharts', 'renderHierarchyCharts', 'svgElement', 'hierarchyChartColor',
        'hierarchyDisplayValue', 'hierarchyPathEntry', 'hierarchyPrefixKey', 'appendHierarchyAxisBands',
        'hierarchyPathValueLabel', 'hierarchyPathFullLabel', 'chartFitWidth', 'styleIncompleteValue',
        'resultScope', 'appendResultScope',
    )
    payload = {'snippets': {name: _function_source(script, name) for name in names}}
    payload['snippets']['resultScopeFilters'] = 'const resultScopeFilters = {};'
    # Zoom is attached in the browser; this test renders the charts only.
    payload['snippets']['zoomStubs'] = 'function enableMapZoom() {}\nfunction enableContentZoom() {}'
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.namespaceURI = 'http://www.w3.org/2000/svg';
    this.attributes = {};
    this.children = [];
    this.style = {};
    this.dataset = {};
    this.className = '';
    this.textContent = '';
    this.clientWidth = 1000;
    this.classList = {add: value => { this.className = `${this.className} ${value}`.trim(); }};
  }
  setAttribute(name, value) {
    this.attributes[name] = String(value);
    if (name === 'class') this.className = String(value);
    if (name === 'viewBox') {
      const [,, width, height] = String(value).split(/\s+/).map(Number);
      this.viewBox = {baseVal: {width, height}};
    }
  }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = [...nodes]; }
  addEventListener() {}
}
const document = {
  createElement: tag => new Element(tag),
  createElementNS: (_namespace, tag) => new Element(tag),
};
const operators = ['Vodafone', 'O2', 'Three', 'EE', 'TestNet'];
const palette = ['#da291c', '#0033a0', '#111111', '#17a09f', '#7851a9'];
const table = {
  title: 'Campaign 2026',
  context: {campaign: '2026Q2', environment: 'DriveCity'},
  operators,
  baseline_operator: 'EE',
  operator_styles: Object.fromEntries(operators.map((operator, index) => [operator, {
    label: operator, color: palette[index], position: index,
  }])),
};
table.chartRows = ['Voice', 'Data'].flatMap((category, categoryIndex) => operators.map((operator, operatorIndex) => ({
  category, operator, weighted_points: 20 + categoryIndex * 7 + operatorIndex, complete: true,
})));
const hierarchyColumns = operators.flatMap((operator, operatorIndex) => [1, 2].map(contextIndex => {
  const id = `${operator}-context-${contextIndex}`;
  table.operator_styles[id] = {label: id, color: palette[operatorIndex], position: operatorIndex};
  return {
    id, operator, label: `${operator} Context ${contextIndex}`, styleSource: table,
    path: [{level: 'Operator', value: operator}, {level: 'City', value: `${operator} Context ${contextIndex}`}],
  };
}));
function hierarchyRows(categories) {
  return categories.flatMap((category, categoryIndex) => hierarchyColumns.map((column, columnIndex) => ({
    category, operator: column.id,
    weighted_points: categoryIndex === 1 && columnIndex === 0 ? null : 8 + categoryIndex * 3 + columnIndex,
    complete: !(categoryIndex === 1 && columnIndex === 0),
  })));
}
function descendants(node) { return [node, ...(node.children || []).flatMap(descendants)]; }
function pane() {
  const value = new Element('div');
  value.classList.add = name => { value.className = `${value.className} ${name}`.trim(); };
  return value;
}
const context = {
  document,
  chartTooltip: {id: 'chart-tooltip'},
  scoreChartRows: tables => tables[0].chartRows,
  chartTableForRow: (_row, tables) => tables[0],
  rowText: (row, names) => {
    for (const name of names) if (row[name] !== undefined && row[name] !== null) return String(row[name]);
    return '';
  },
  appendComparisonSelector: (_pane, groups) => groups[0],
  appendContextHeader: () => {},
  contextLabel: () => 'Campaign 2026 · DriveCity',
  hierarchyColumnEntries: data => data.columns,
  hierarchyColumnOperator: column => column.operator,
  hierarchyColumnIsReference: column => column.operator === 'EE' && column.id.endsWith('context-1'),
  humanizeKey: key => key,
  environmentLabel: value => value,
  normalizeRows: () => [],
  scoreNumber: () => null,
};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n') + `
  globalThis.renderers = {renderCharts, renderHierarchyCharts, makeSvgChart, makeBestNetworkBars,
    chartLegendRows, bestNetworkHorizontalGeometry};`, context);
function inspect(target) {
  const svgs = descendants(target).filter(node => node.className === 'scoring-chart-svg');
  return svgs.map(svg => {
    const nodes = descendants(svg);
    const bars = nodes.filter(node => node.tagName === 'rect' && (node.attributes['data-chart-tooltip'] || '').includes('Weighted points:'));
    return {
      title: svg.attributes['aria-label'],
      operatorLegend: nodes.filter(node => node.className === 'scoring-chart-legend').map(node => node.textContent),
      categoryLegendSegments: nodes.filter(node => node.className === 'scoring-chart-category-legend-segment').length,
      scoredBars: bars.length,
      barFills: bars.map(node => node.attributes.fill),
      unavailable: nodes.filter(node => node.className === 'scoring-chart-unavailable' && node.textContent === 'N/A').length,
      viewBoxWidth: svg.viewBox.baseVal.width,
      widthStyle: svg.style.width || '',
      minWidthStyle: svg.style.minWidth || '',
    };
  });
}
const simplePane = pane();
context.renderers.renderCharts(simplePane, [], [table]);
const hierarchyPane = pane();
context.renderers.renderHierarchyCharts(hierarchyPane, {
  ...table, chartRows: hierarchyRows(['Voice', 'Data']), hierarchy_levels: ['Operator', 'City'], columns: hierarchyColumns,
});
const categories = ['Classic Calls', 'WhatsApp Calls', 'Multi RAB', 'Streaming', 'Web Browsing', 'Messaging', 'Upload'];
table.chartRows = categories.flatMap((category, categoryIndex) => operators.map((operator, operatorIndex) => ({
  category, operator, weighted_points: 10 + categoryIndex * 3 + operatorIndex, complete: true,
})));
const wideSimplePane = pane();
context.renderers.renderCharts(wideSimplePane, [], [table]);
const wideHierarchyPane = pane();
context.renderers.renderHierarchyCharts(wideHierarchyPane, {
  ...table, chartRows: hierarchyRows(categories), hierarchy_levels: ['Operator', 'City'], columns: hierarchyColumns,
});
function compareBestNetwork(count) {
  const names = Array.from({length: count}, (_, index) => `Operator ${index + 1}`);
  const styles = Object.fromEntries(names.map((name, index) => [name, {
    label: name, color: palette[index % palette.length], position: index,
  }]));
  const source = {...table, operators: names, operator_styles: styles, rows: [{max_points: 90}]};
  const rows = names.flatMap(operator => [
    {category: operator, series: 'Data', value: 99.5, complete: true},
    {category: operator, series: 'Voice', value: .5, complete: true},
  ]);
  const categorySvg = context.renderers.makeSvgChart('Best Network Scoring per Category', rows, source, {
    stacked: true, categoryOrder: names, seriesOrder: ['Data', 'Voice'],
    seriesStyles: {Data: {label: 'Data', color: '#555555'}, Voice: {label: 'Voice', color: '#c5c5c5'}},
    legendEntries: names.map((name, index) => ({label: name, color: palette[index % palette.length]})),
    categoryLegendEntries: [{label: 'Data', color: '#555555'}, {label: 'Voice', color: '#c5c5c5'}],
    segmentColor: (_operator, kind) => kind === 'Data' ? '#555555' : '#c5c5c5',
    operatorForCategory: operator => operator,
  });
  const serviceData = {
    operators: names, allocation: {Data: 90, Voice: 0},
    totals: Object.fromEntries(names.map(name => [name, {
      Data: {value: 99.5, complete: true}, Voice: {value: .5, complete: true},
    }])),
  };
  const serviceSvg = context.renderers.makeBestNetworkBars(source, serviceData);
  const geometry = context.renderers.bestNetworkHorizontalGeometry(count);
  const legendRows = context.renderers.chartLegendRows(names.map((name, index) => ({
    label: name, color: palette[index % palette.length],
  })), geometry.width, geometry.left, geometry.right, palette[0]);
  const expectedLegendStarts = legendRows.map(row => geometry.left
    + Math.max(0, (geometry.width - geometry.left - geometry.right - (row.width - 22)) / 2));
  const measure = svg => {
    const rects = svg.children.filter(node => node.tagName === 'rect'
      && (node.attributes['data-chart-tooltip'] || '').includes('Weighted points:'));
    const labels = svg.children.filter(node => node.className === 'scoring-best-network-segment');
    const totals = svg.children.filter(node => node.className.includes('scoring-chart-value'));
    const ticks = svg.children.filter(node => node.className === 'scoring-chart-tick').map(node => node.textContent);
    const legendLabels = svg.children.filter(node => node.className === 'scoring-chart-legend')
      .map(node => ({text: node.textContent, x: Number(node.attributes.x), y: Number(node.attributes.y)}));
    const sharedText = svg.children.filter(node => [
      'scoring-chart-axis-label', 'scoring-chart-tick', 'scoring-chart-operator-legend-title',
      'scoring-chart-legend', 'scoring-chart-category-legend-title', 'scoring-chart-category-legend-label',
    ].includes(node.className)).map(node => node.className).sort();
    return {
      viewBoxWidth: svg.viewBox.baseVal.width, widthStyle: svg.style.width,
      viewBoxHeight: svg.viewBox.baseVal.height, ticks,
      minWidthStyle: svg.style.minWidth,
      positions: rects.filter((_node, index) => index % 2 === 0).map(node => Number(node.attributes.x)),
      barWidths: [...new Set(rects.map(node => Number(node.attributes.width)))],
      labelTexts: labels.map(node => node.textContent),
      labelSizes: labels.map(node => node.style.fontSize),
      totals: totals.map(node => node.textContent), totalY: totals.map(node => Number(node.attributes.y)),
      barTop: Math.min(...rects.map(node => Number(node.attributes.y))), legendLabels,
      hasOperatorsHeading: svg.children.some(node => node.textContent === 'Operators'), sharedText,
    };
  };
  return {count, expectedLegendStarts, category: measure(categorySvg), service: measure(serviceSvg)};
}
const sharedGeometry = [5, 10, 14].map(compareBestNetwork);
process.stdout.write(JSON.stringify({
  simple: inspect(simplePane), hierarchy: inspect(hierarchyPane),
  wideSimple: inspect(wideSimplePane), wideHierarchy: inspect(wideHierarchyPane), palette,
  sharedGeometry,
}));
"""
    result = _run_node_json(program, payload)

    for charts in (result['simple'], result['hierarchy']):
        assert len(charts) == 2
        top, bottom = charts
        assert len(top['operatorLegend']) == 5
        assert len(bottom['operatorLegend']) == 5
        assert top['categoryLegendSegments'] == 2
        assert bottom['categoryLegendSegments'] == 0
        expected_bars = 10 if charts is result['simple'] else 19
        expected_missing = 0 if charts is result['simple'] else 1
        assert top['scoredBars'] == expected_bars
        assert bottom['scoredBars'] == expected_bars
        assert top['unavailable'] == 0
        assert bottom['unavailable'] == expected_missing
        assert set(bottom['barFills']) == set(result['palette'])
    for charts in (result['wideSimple'], result['wideHierarchy']):
        assert len(charts) == 2
        top, bottom = charts
        assert len(top['operatorLegend']) == 5
        assert len(bottom['operatorLegend']) == 5
        assert top['categoryLegendSegments'] == 7
        assert bottom['categoryLegendSegments'] == 0
        expected_bars = 35 if charts is result['wideSimple'] else 69
        expected_missing = 0 if charts is result['wideSimple'] else 1
        assert top['scoredBars'] == expected_bars
        assert bottom['scoredBars'] == expected_bars
        assert top['unavailable'] == 0
        assert bottom['unavailable'] == expected_missing
        assert set(bottom['barFills']) == set(result['palette'])
        if charts is result['wideHierarchy']:
            assert bottom['viewBoxWidth'] >= 7 * 10 * 70
            assert float(bottom['widthStyle'].removesuffix('%')) > 100
        else:
            assert bottom['viewBoxWidth'] <= 1000
            assert bottom['widthStyle'] == '100%'
        assert bottom['minWidthStyle'] == '0'

    for comparison in result['sharedGeometry']:
        assert comparison['count'] in {5, 10, 14}
        category, service = comparison['category'], comparison['service']
        assert category['viewBoxWidth'] == service['viewBoxWidth']
        assert category['widthStyle'] == service['widthStyle']
        assert category['minWidthStyle'] == service['minWidthStyle'] == '0'
        assert category['positions'] == service['positions']
        assert len(category['barWidths']) == len(service['barWidths']) == 1
        assert category['barWidths'] == service['barWidths']
        assert category['labelTexts'] == service['labelTexts']
        assert len(category['labelTexts']) == comparison['count']
        assert all(text == '99.5' for text in category['labelTexts'])
        assert category['labelSizes'] == service['labelSizes']
        assert all(float(size.removesuffix('px')) <= 22 for size in category['labelSizes'])
        assert category['totals'] == service['totals']
        assert all(value.endswith('.0') for value in category['totals'])
        assert category['ticks'] == service['ticks']
        assert 4 <= len(category['ticks']) <= 7
        assert all(value.isdigit() for value in category['ticks'])
        tick_steps = [int(left) - int(right) for left, right in zip(category['ticks'], category['ticks'][1:])]
        assert len(set(tick_steps)) == 1
        assert int(category['ticks'][0]) >= 100
        for view in (category, service):
            assert all(0 < total_y < view['barTop'] for total_y in view['totalY'])
            assert view['barTop'] < view['viewBoxHeight']
        assert [(item['text'], item['x']) for item in category['legendLabels']] == [
            (item['text'], item['x']) for item in service['legendLabels']
        ]
        assert not service['hasOperatorsHeading']
        for view in (category, service):
            legend_rows = {}
            for item in view['legendLabels']:
                legend_rows.setdefault(item['y'], []).append(item)
            row_starts = [entries[0]['x'] - 21 for entries in legend_rows.values()]
            assert row_starts == pytest.approx(comparison['expectedLegendStarts'])
        if comparison['count'] <= 10:
            assert category['widthStyle'] == service['widthStyle'] == '100%'
        else:
            assert float(category['widthStyle'].removesuffix('%')) > 100
        for shared_class in ('scoring-chart-axis-label', 'scoring-chart-tick', 'scoring-chart-legend',
                             'scoring-chart-category-legend-title', 'scoring-chart-category-legend-label'):
            assert shared_class in category['sharedText']
            assert shared_class in service['sharedText']


def test_reference_header_uses_operator_mapping_accent_without_yellow_marker():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    assert '.scoring-comparison-table th.scoring-operator-header { background: color-mix(in srgb, var(--operator-accent, #607d8b) 20%, #fff) !important; color: #263f4b !important; box-shadow: inset 0 3px var(--operator-accent, #607d8b); }' in template
    assert '.scoring-comparison-table th.scoring-reference-header' not in template
    assert '.scoring-comparison-table th.scoring-hierarchy-header.scoring-reference-header' not in template
    assert '.scoring-comparison-table th.scoring-gap-header { background: color-mix(in srgb, var(--st-gap-header) 30%, #fff) !important; color: var(--st-soft-header-text) !important; }' in template
    assert "function markReferenceHeader(header) {\n    header.classList.add('scoring-reference-header');" in script
    assert 'header.title = `${label} is the reference operator`;' in script


def test_operator_color_and_reference_markers_stay_on_operator_headers():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    assert '.scoring-comparison-table th.scoring-operator-header { background: color-mix(in srgb, var(--operator-accent, #607d8b) 20%, #fff) !important; color: #263f4b !important; box-shadow: inset 0 3px var(--operator-accent, #607d8b); }' in template
    assert 'border-bottom: 3px solid var(--operator-accent' not in template
    assert '.scoring-comparison-table th.scoring-reference-header' not in template
    assert '.scoring-comparison-table th.scoring-hierarchy-header.scoring-reference-header' not in template
    hierarchy_header_rule = re.search(
        r'\.scoring-comparison-table th\.scoring-hierarchy-header\s*\{([^}]*)\}', template,
    )
    assert hierarchy_header_rule and 'border-' not in hierarchy_header_rule.group(1)
    assert "String(entry.level).toLocaleLowerCase() === 'operator'" in script


def test_export_links_have_distinct_high_contrast_colors():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')

    assert re.search(r'\.scoring-results-tools a\[data-config-shortcut="kpi"\] \{ background: linear-gradient\(', template)
    # Both report buttons share the PowerPoint export colour.
    assert '.scoring-results-tools a:is([data-export-ppt], [data-generate-report]) { background: linear-gradient(' in template
    assert '.scoring-results-tools a[data-config-shortcut] { color: #fff;' in template
    # Both Export to CSV buttons share the GAP export colour.
    assert re.search(r'\.scoring-table-export a \{[^}]*background: linear-gradient\(135deg,#1688bb,#145584\)', template)


def test_gap_value_toggle_defaults_off_and_only_changes_scoring_tables():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    gap_toggle = re.search(r'<label class="scoring-kpi-values-toggle" data-show-gap-label>(.*?)</label>', template, re.S)
    assert gap_toggle
    assert 'data-show-gap-values' in gap_toggle.group(1)
    assert 'Show GAP values' in gap_toggle.group(1)
    assert 'checked' not in gap_toggle.group(1)
    assert "if (showGapValuesToggle) showGapValuesToggle.checked = restoredScoringViewState.showGapValues === true;" in script
    assert "function showGapValues() {\n    return Boolean(showGapValuesToggle?.checked);" in script
    assert "if (!showGapValues()) {\n      for (const [operatorIndex, operator] of operators.entries()) appendScore(operator, operatorIndex);\n      return;" in script
    assert "if (event.target === showGapValuesToggle) {\n      syncGapValueControls();\n      if (currentResults) renderResult(currentResults, selectedSavedFilter, ['scoring']);" in script
    assert "function renderTable(pane, source, emptyCopy, {hideGapColumns = false} = {})" in script
    assert "renderTable(gapPane, gapRows, 'No GAP rows are available for the selected baseline operator.');" in script
    assert "function appendScoringGapScale(pane, tableData) {\n    if (!showGapValues()) return;" in script
    assert script.count("label.textContent = showGapValues() && total.gap_label ? `Weighted score · ${total.gap_label}` : 'Weighted score';") == 2


def test_environment_selector_precedes_value_toggles_and_gap_layout_is_conditional():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    selector_row = re.search(r'<div class="scoring-results-selector-row"[^>]*>(.*?)</div>', template, re.S)
    value_row = re.search(r'<div class="scoring-results-value-row"[^>]*>(.*?)</div>', template, re.S)
    assert selector_row and value_row
    environment_index = selector_row.group(1).index('data-result-environment-control')
    assert 'data-scoring-table-mode' not in template
    assert template.index('data-scoring-results-selector-row') < template.index('data-show-kpi-values')
    assert 'data-scoring-gap-layout-control hidden' in template
    assert 'if (gapLayoutControl) gapLayoutControl.hidden = !showGapValues();' in script


def test_gap_value_choice_is_sent_only_to_powerpoint_export():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    # The PowerPoint and Word take the theme of the page too.
    assert "const gapOption = kind === 'ppt' ? `&show_gap_values=${showGapValues() ? 'true' : 'false'}&theme=${encodeURIComponent(activeTheme?.id || 'netcheck')}` : '';" in script
    assert "link.href = enabled ? `${exportBase}/${encodeURIComponent(savedFilterId)}/export/${kind}?${query}${gapOption}${scoringOption}` : '#';" in script
    assert "const scoringOption = kind !== 'ppt' && typeof effectiveScoring === 'function'" in script
    assert "const query = `table_mode=${encodeURIComponent(selectedTableMode())}&gap_layout=${encodeURIComponent(selectedGapLayout())}&environment=${encodeURIComponent(selectedEnvironment || 'all')}`;" in script


def test_export_selected_scoring_report_asks_for_scorings_environments_and_format():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    payload = {'snippets': {name: _function_source(script, name) for name in (
        'scoringExportChoices', 'scoringExportDialogHtml', 'scoringExportOperators', 'exportSelectedScoringReport')}}
    payload['snippets']['sections'] = re.search(r"const EXPORT_OPERATOR_SECTIONS = \[[^\]]*\];", script).group(0)
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const results = [];
(async () => {
  // Each case: the button chosen, the boxes the user changes and whether the Saved Filter has Most Reliable.
  const cases = [
    {choice: 'confirm', toggle: [], reliable: true},
    {choice: 'secondary', toggle: ['most_reliable', 'Combined', 'Drive - City'], reliable: true},
    {choice: 'confirm', toggle: ['best_network'], reliable: false},
    {choice: null, toggle: [], reliable: true},
    {choice: 'confirm', toggle: [], reliable: true, selections: [['summary-operators', '["VF","EE"]'], ['points-loss-colour', 'losses']]},
  ];
  for (const item of cases) {
    let downloaded = null;
    let dialog = null;
    let warning = null;
    let inputs = [];
    const context = {
      URL, chosenComparedOperators: () => [], window: {location: {href: 'https://example.test/scoring'}}, insightSelections: new Map(item.selections || []),
      environmentSelect: {options: [{value: 'all', textContent: 'All Environments'},
                                    {value: 'Drive - City', textContent: 'Drive - City'},
                                    {value: 'Drive - Roads', textContent: 'Drive - Roads'}]},
      currentResults: {scorings: item.reliable ? {most_reliable: {}} : {}},
      showConfirmDialog: async (message, options) => {
        dialog = {message, ...options};
        inputs = [...options.copyHtml.matchAll(/data-scoring-export-(\w+) value="([^"]*)"( checked)?( disabled)?/g)]
          .map(([, group, value, checked, disabled]) => ({group, value, checked: Boolean(checked), disabled: Boolean(disabled)}));
        for (const input of inputs) if (item.toggle.includes(input.value) && !input.disabled) input.checked = !input.checked;
        return item.choice;
      },
      document: {querySelectorAll: selector => inputs.filter(input => selector.includes(`data-scoring-export-${input.group}`))},
      showInfoDialog: message => { warning = message; },
      downloadScoringDocument: async (url, label) => { downloaded = {url, label}; },
    };
    vm.createContext(context);
    vm.runInContext(Object.values(payload.snippets).join('\n'), context);
    await vm.runInContext("exportSelectedScoringReport({href: 'https://example.test/scoring/saved-filters/7/export/ppt?environment=all'})", context);
    results.push({downloaded, warning, inputs, title: dialog?.title, labels: [dialog?.confirmLabel, dialog?.secondaryLabel]});
  }
  process.stdout.write(JSON.stringify(results));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    default, custom, nothing, cancelled, operators = _run_node_json(program, payload)
    # Best Network and All Environments are ticked; Most Reliable only when the Saved Filter has it.
    assert [(item['value'], item['checked'], item['disabled']) for item in default['inputs']] == [
        ('best_network', True, False), ('most_reliable', False, False), ('Combined', True, False),
        ('Drive - City', False, False), ('Drive - Roads', False, False)]
    assert default['title'] == 'Export Selected Scoring Report' and default['labels'] == ['PowerPoint', 'Word']
    assert default['downloaded'] == {
        'url': 'https://example.test/scoring/saved-filters/7/export/ppt?environment=all&scorings=best_network&environments=Combined',
        'label': 'PowerPoint'}
    assert custom['downloaded'] == {
        'url': 'https://example.test/scoring/saved-filters/7/export/word?environment=all&scorings=best_network'
               '&scorings=most_reliable&environments=Drive+-+City', 'label': 'Word'}
    assert ('most_reliable', False, True) in [(item['value'], item['checked'], item['disabled']) for item in nothing['inputs']]
    assert nothing['downloaded'] is None and 'Tick at least one scoring' in nothing['warning']
    assert cancelled['downloaded'] is None
    # The operators enabled in the sections of the page travel with the export (only the sections changed).
    assert operators['downloaded']['url'] == (
        'https://example.test/scoring/saved-filters/7/export/ppt?environment=all&scorings=best_network&environments=Combined'
        '&operators=%7B%22summary-operators%22%3A%5B%22VF%22%2C%22EE%22%5D%7D')


def test_generate_scoring_report_uses_the_calculation_selection():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    payload = {'snippets': {'generateScoringReport': _function_source(script, 'generateScoringReport')}}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const results = [];
(async () => {
  for (const datasetIds of [[], ['4', '5', '6']]) {
    let request = null;
    let warning = null;
    const context = {
      window: {ScoringReportEditor: {open: async () => ({action: 'word', configuration: {scenarios: [{name: 'National'}]}}),
                                     defaultConfiguration: defaults => ({scenarios: [], defaults})}},
      fetch: async () => ({ok: false}),
      chosenComparedOperators: () => ['VF'],
      calculationPayload: () => ({dataset_ids: datasetIds, nr_mode: 'SA', baseline_operator: 'EE', scoring_profile_id: 'netcheck',
                                  aggregation_levels: ['Operator', 'City'], context_filters: {City: ['Leeds']}}),
      selectedContextFilters: () => ({City: ['Leeds']}),
      contextFilterDefinitions: [], contextFilterSelects: new Map(), mainCities: [], operatorGroups: [],
      showInfoDialog: message => { warning = message; },
      downloadScoringDocument: async (url, label, init) => { request = {url, label, body: JSON.parse(init.body)}; },
    };
    vm.createContext(context);
    vm.runInContext(Object.values(payload.snippets).join('\\n'), context);
    await vm.runInContext('generateScoringReport()', context);
    results.push({request, warning});
  }
  process.stdout.write(JSON.stringify(results));
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    without_cdrs, with_cdrs = _run_node_json(program, payload)
    assert without_cdrs['request'] is None and 'Select the CDRs' in without_cdrs['warning']
    assert with_cdrs['request']['url'] == '/api/scoring/report/word' and with_cdrs['request']['label'] == 'Word'
    body = with_cdrs['request']['body']
    assert (body['dataset_ids'], body['nr_mode'], body['baseline_operator'], body['scoring_profile_id']) == (
        [4, 5, 6], 'SA', 'EE', 'netcheck')
    assert body['configuration'] == {'scenarios': [{'name': 'National'}]}


def test_scoring_tab_is_plural_and_subtotals_and_totals_share_category_background():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')

    assert re.search(r'data-result-tab="scoring"><svg [^>]*>.*?</svg><span>Scoring Tables</span></button>', template, re.S)
    assert 'data-result-tab="scoring">Scoring Table</button>' not in template
    assert re.search(
        r'\.scoring-comparison-table tbody tr\.scoring-category-subtotal > td,\s*'
        r'\.scoring-comparison-table tfoot tr > :is\(th, td\)\s*'
        r'\{\s*background-color:\s*color-mix\(in srgb, var\(--st-total\) 70%, #fff\)\s*!important;',
        template,
    )
    assert '.scoring-table-wrap tbody tr.scoring-total-row > td { background-color: color-mix(in srgb, var(--st-total) 55%, #fff);' in template


def test_render_warnings_hides_only_legacy_campaign_pooling_notice():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    renderer = re.search(r'function renderWarnings\(warnings\) \{(.*?)\n  \}', script, re.S)
    assert renderer
    body = renderer.group(1)

    assert "const legacyCampaignNotice = 'Campaigns are scored separately; the supplied Tableau Prep flow pools campaigns.';" in body
    assert "const visibleItems = items.filter(warning => (\n      (typeof warning === 'string' ? warning : displayValue(warning)) !== legacyCampaignNotice\n    ));" in body
    assert 'box.hidden = !visibleItems.length;' in body
    assert 'for (const warning of visibleItems)' in body
    assert 'items.splice' not in body


def test_calculation_notes_render_coverage_emphasis_in_one_card_above_result_tabs():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    renderer = _function_source(script, 'renderWarnings')
    note = (
        'VF_UK / Samsung / 2026-Q1: maximum achievable scoring 933.2645 of 1000 points. '
        'Affected environments and scoring ceilings: DriveCity: 933.2645 of 650 points.'
    )
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor(tagName) { this.tagName = tagName; this.children = []; this.hidden = false; this.className = ''; this._text = ''; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
}
const box = new Element('div');
const list = new Element('ul');
const root = {querySelector(selector) { return selector === '[data-warning-box]' ? box : list; }};
const document = {
  createElement(tagName) { return new Element(tagName); },
  createTextNode(value) { const node = new Element('#text'); node.textContent = value; return node; },
};
const renderWarnings = new Function('root', 'document', 'displayValue', payload.renderer + '\nreturn renderWarnings;')(
  root, document, value => String(value ?? ''));
renderWarnings([payload.note]);
process.stdout.write(JSON.stringify({
  hidden: box.hidden,
  noteText: list.children[0]?.textContent,
  emphasis: list.children[0]?.children.map(child => ({tag: child.tagName, className: child.className, text: child.textContent})),
}));
"""
    actual = _run_node_json(program, {'renderer': renderer, 'note': note})

    assert actual['hidden'] is False
    assert actual['noteText'] == note
    emphasis = [part for part in actual['emphasis'] if part['tag'] == 'strong']
    assert [part['text'] for part in emphasis] == [
        'maximum achievable scoring 933.2645 of 1000 points',
        '933.2645 of 650 points',
    ]
    assert all(part['className'] == 'scoring-warning-maximum' for part in emphasis)

    assert template.count('data-warning-box') == 1
    assert 'data-environment-warning' not in template
    assert template.index('data-warning-box') < template.index('<div class="scoring-results-tabbed">')
    assert '.scoring-warning-maximum { font-size: 1.15em; font-weight: 800; }' in template


def test_scoring_view_state_round_trips_filters_and_false_checkboxes():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    snippets = {
        name: _function_source(script, name)
        for name in ('readScoringViewState', 'persistScoringViewState', 'selectedTableMode', 'selectedGapLayout', 'showGapValues')
    }
    payload = {
        'snippets': snippets,
        'storageKey': 'drivetest-analyzer:scoring-view:jaime:workspace-a',
        'initial': {
            'saved_filter_id': 'savedFilter-17', 'result_tab': 'gap', 'scroll_y': 321,
            'environment': 'DriveCity', 'gap_layout': 'sideways',
            'show_kpi_values': False, 'show_gap_values': False,
        },
    }
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const values = new Map([[payload.storageKey, JSON.stringify(payload.initial)]]);
const context = {
  scoringViewStorageKey: payload.storageKey,
  resultTabNames: new Set(['scoring', 'gap', 'charts', 'best-network']),
  window: {scrollY: 777, sessionStorage: {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
  }},
  selectedSavedFilterId: null,
  activeResultTab: 'scoring',
  selectedEnvironment: 'all',
  gapLayoutSelect: {value: 'end'},
  showKpiValuesToggle: {checked: true},
  showGapValuesToggle: {checked: true},
};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n') + '\nglobalThis.restored = readScoringViewState();', context);
const restored = context.restored;
context.selectedSavedFilterId = restored.savedFilterId;
context.activeResultTab = restored.resultTab;
context.selectedEnvironment = restored.environment;
context.gapLayoutSelect.value = restored.gapLayout;
context.showKpiValuesToggle.checked = restored.showKpiValues;
context.showGapValuesToggle.checked = restored.showGapValues;
vm.runInContext('persistScoringViewState()', context);
process.stdout.write(JSON.stringify({restored, saved: JSON.parse(values.get(payload.storageKey))}));
"""
    result = _run_node_json(program, payload)

    assert 'tableMode' not in result['restored']
    assert result['restored']['gapLayout'] == 'end'
    assert result['restored']['showKpiValues'] is False
    assert result['restored']['showGapValues'] is False
    assert result['saved']['show_kpi_values'] is False
    assert result['saved']['show_gap_values'] is False
    assert 'table_mode' not in result['saved']
    assert result['saved']['gap_layout'] == 'end'
    assert result['saved']['environment'] == 'DriveCity'


def test_scoring_tables_render_both_summary_and_expanded_modes():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    payload = {'tableForMode': _function_source(script, 'tableForMode')}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {};
vm.createContext(context);
vm.runInContext(payload.tableForMode + `
  const fixture = {
    rows: [{name: 'legacy'}], total: {points: 99},
    category_rows: [{name: 'summary'}], category_total: {points: 40},
    expanded_rows: [{name: 'expanded'}], expanded_total: {points: 75},
  };
  globalThis.summary = tableForMode(fixture, 'summary');
  globalThis.expanded = tableForMode(fixture, 'expanded');`, context);
process.stdout.write(JSON.stringify({summary: context.summary, expanded: context.expanded}));
"""
    result = _run_node_json(program, payload)

    assert result['summary']['rows'] == [{'name': 'summary'}]
    assert result['summary']['total'] == {'points': 40}
    assert result['expanded']['rows'] == [{'name': 'expanded'}]
    assert result['expanded']['total'] == {'points': 75}
    assert 'data-scoring-table-mode' not in template
    assert "tableForMode(selected, 'summary')" in script
    assert "tableForMode(selected, 'expanded')" in script


def test_raw_kpi_columns_are_hidden_in_summary_and_shown_in_expanded():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    names = (
        'firstValue', 'isReferenceOperator', 'markReferenceHeader', 'operatorPresentation',
        'safeHexColor', 'readableTextColor', 'formatMatrixNumber', 'formatRawKpiValue',
        'formatScoreCell', 'createKpiTypeCell', 'addMatrixScoreCell', 'operatorValue',
        'appendScoreGapCells', 'showGapValues', 'selectedGapLayout', 'tableForMode',
        'appendMatrixTable', 'renderScoringViews', 'summaryOperatorColors', 'appendOperatorRankingLegend',
        'styleIncompleteValue',
        'applyGapCategoryRunColors', 'resultScope', 'appendResultScope',
    )
    payload = {'snippets': {name: _function_source(script, name) for name in names}}
    payload['snippets']['resultScopeFilters'] = 'const resultScopeFilters = {};'
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.style = {setProperty() {}};
    this.attributes = {};
    this.className = '';
    this.classList = {add: value => { this.className = `${this.className} ${value}`.trim(); }};
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = [...nodes]; }
  querySelectorAll() { return descendants(this).filter(node => node.className === "scoring-category-cell"); }
}
const document = {createElement: tag => new Element(tag)};
const table = {
  title: 'Campaign 2026', context: {campaign: '2026Q2'},
  operators: ['EE', 'O2'], baseline_operator: 'EE',
  operator_styles: {EE: {label: 'EE', color: '#17a09f'}, O2: {label: 'O2', color: '#0033a0'}},
  category_rows: [
    {row_type: 'category', category: 'Voice', kpi: 'Voice', weight_percent: 100, max_points: 1000, values: {EE: {points: 850, complete: true}, O2: {points: 770, complete: true}}},
  ],
  expanded_rows: [
    {row_type: 'kpi', category: 'Voice', kpi: 'Call Setup', kpi_code: 'call_setup', kpi_type: 'Reliable', weight_percent: 50, max_points: 500,
      values: {EE: {value: 12.345, points: 400, complete: true}, O2: {value: 67.891, points: 350, complete: true}}},
    {row_type: 'kpi', category: 'Voice', kpi: 'Drop Rate', kpi_code: 'drop_rate', kpi_type: 'Diff', weight_percent: 50, max_points: 500,
      values: {EE: {value: 1.2, points: 450, complete: true}, O2: {value: 2.3, points: 420, complete: true}}},
  ],
  category_total: {weight_percent: 100, max_points: 1000, values: {EE: {points: 850, complete: true}, O2: {points: 770, complete: false}}},
  expanded_total: {weight_percent: 100, max_points: 1000},
};
function descendants(node) { return [node, ...(node.children || []).flatMap(descendants)]; }
const context = {
  document,
  showKpiValuesToggle: {checked: true},
  gapLayoutSelect: {value: 'end'},
  showGapValuesToggle: {checked: false},
  scoringValueObservers: new Map(),
  disconnectScoringValueObservers: () => {},
  observeScoringValueCells: () => {},
  appendComparisonSelector: (_pane, tables) => tables[0],
  appendContextHeader: () => {},
  appendThresholdLegend: () => {},
  appendScoringGapScale: () => {},
  addMatrixGapCell: () => {},
  applyScorecardLayout: () => {},
};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n') + `
  globalThis.render = renderScoringViews;`, context);
const pane = new Element('div');
context.render(pane, [table]);
const sections = pane.children.filter(node => node.tagName === 'section');
function summarize(section) {
  const nodes = descendants(section);
  return {
    heading: nodes.find(node => node.className === 'scoring-table-section-title')?.textContent,
    valueGroups: nodes.filter(node => node.className.includes('scoring-kpi-value-group')).length,
    valueHeaders: nodes.filter(node => node.tagName === 'th' && node.className.includes('scoring-kpi-value-header')).length,
    ranks: nodes.filter(node => node.dataset.operatorRank).map(node => [node.dataset.operatorRank, node.style.backgroundColor]),
    rankingLegend: nodes.filter(node => node.className.includes('scoring-operator-ranking-legend')).length,
    rawCells: nodes.filter(node => node.tagName === 'td' && node.dataset.column === 'kpi-value').map(node => node.textContent),
  };
}
process.stdout.write(JSON.stringify(sections.map(summarize)));
"""
    results = _run_node_json(program, payload)

    assert [section['heading'] for section in results] == [
        'Scoring Tables — Summary', 'Scoring Tables — Breakdown',
    ]
    assert results[0]['valueGroups'] == 0
    assert results[0]['valueHeaders'] == 0
    assert results[0]['rawCells'] == []
    assert results[0]['ranks'] == [['best', '#C6EFCE'], ['worst', '#FFC7CE']] * 2
    assert results[0]['rankingLegend'] == 1
    assert results[1]['ranks'] == []
    assert results[1]['rankingLegend'] == 0
    assert results[1]['valueGroups'] == 1
    assert results[1]['valueHeaders'] == 2
    assert results[1]['rawCells'] == ['12.35', '67.89', '1.20', '2.30', 'N/A', 'N/A']
    assert script.count("tableData?._display_mode !== 'summary' && Boolean(showKpiValuesToggle?.checked)") == 2


def test_summary_ranking_uses_all_hierarchy_columns_and_keeps_tied_extremes():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    payload = {'summaryOperatorColors': _function_source(script, 'summaryOperatorColors'),
               'operatorValue': _function_source(script, 'operatorValue'),
               'firstValue': _function_source(script, 'firstValue')}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {};
vm.createContext(context);
vm.runInContext(Object.values(payload).join('\n') + `
  const columns = [
    {id: 'north-a'}, {id: 'north-b'}, {id: 'south-a'}, {id: 'south-b'}, {id: 'east-a'},
  ];
  const values = {
    'north-a': {points: 100}, 'north-b': {points: 90},
    'south-a': {points: 10}, 'south-b': {points: 100}, 'east-a': {points: null},
  };
  globalThis.result = [...summaryOperatorColors(values, columns).entries()];`, context);
process.stdout.write(JSON.stringify(context.result));
"""
    result = _run_node_json(program, payload)

    assert result == [['north-a', '#C6EFCE'], ['south-a', '#FFC7CE'], ['south-b', '#C6EFCE']]


def test_scoring_view_state_falls_back_to_all_when_saved_environment_is_unavailable():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    helpers_start = script.index('  const environmentOrder =')
    helpers_end = script.index('  function chartRowsForEnvironment', helpers_start)
    environment_helpers = script[helpers_start:helpers_end]
    payload = {'helpers': environment_helpers}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const select = {
  options: [], value: '',
  replaceChildren() { this.options = []; },
  append(option) { this.options.push(option); },
};
const context = {
  document: {createElement: () => ({value: '', textContent: ''})},
  selectedEnvironment: 'DriveConnectionroad',
  environmentSelect: select,
  environmentControl: {hidden: true},
  currentEffectiveEnvironment: null,
};
vm.createContext(context);
vm.runInContext(payload.helpers + `
  globalThis.result = syncResultEnvironment([
    {context: {environment: 'DriveCity'}},
    {context: {environment: 'Combined'}},
  ]);`, context);
process.stdout.write(JSON.stringify({
  selectedEnvironment: context.selectedEnvironment,
  effective: context.result.effective,
  unavailable: context.result.unavailable,
  options: select.options.map(option => option.value),
}));
"""
    result = _run_node_json(program, payload)

    assert result['selectedEnvironment'] == 'all'
    assert result['effective'] == 'Combined'
    assert result['unavailable'] is False
    assert result['options'] == ['all', 'DriveCity']


def test_scoring_job_title_and_cdr_summary_use_saved_filters_and_source_names():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    snippets = [
        _constant_source(script, 'valueOf'),
        _function_source(script, 'uniqueCatalogueValues'),
        _function_source(script, 'operatorGroupLabels'),
        _function_source(script, 'scoringVendorName'),
        _function_source(script, 'firstValue'),
        _function_source(script, 'formatDate'),
        _function_source(script, 'selectedContextFilters'),
        _function_source(script, 'savedSavedFilterValues'),
        _function_source(script, 'campaignLabels'),
        _function_source(script, 'hierarchyDisplayValue'),
        _function_source(script, 'insightCampaignKey'),
        _function_source(script, 'savedFilterCampaigns'),
        _function_source(script, 'savedFilterCardTitleSegments'),
        _function_source(script, 'savedFilterCardTitle'),
        _function_source(script, 'savedFilterCdrNames'),
        _function_source(script, 'savedFilterCdrSummary'),
    ]
    payload = {
        'snippets': snippets,
        'savedFilter': {
            'created_at': '2026-10-01T12:00:00Z', 'nr_mode': 'NSA',
            'dataset_names': ['data.csv', 'voice.csv', 'voice.csv'],
            'context_filters': {'Operator': [], 'Vendor': [], 'Region': [], 'City': [], 'Campaign': []},
            'resolved_context_filters': {
                'Operator': ['EE', 'EE', 'O2'], 'Vendor': ['Nokia'], 'Region': ['North'],
                'City': ['Leeds'], 'Campaign': ['UK_Q2_2026'],
            },
            'source_metadata': [{'campaign': 'UK_Q2_2026'}],
        },
    }
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {savedFilter: payload.savedFilter,
  operatorGroups: [],
  catalogueKeyByLevel: new Map([['Vendor', 'vendors']]),
  datasetCatalogues: new Map([['1', {vendors: ['Nokia']}], ['2', {vendors: ['Ericsson']}]]),
  contextFilterDefinitions: [{key: 'Vendor'}],
  isCampaignPreset: () => false, chosenCampaignPreset: () => '',
  contextFilterSelects: new Map([['Vendor', {options: [{value: 'Nokia'}, {value: 'Ericsson'}], selectedOptions: [{value: 'Nokia'}, {value: 'Ericsson'}]}]])};
vm.createContext(context);
vm.runInContext(payload.snippets.join('\n') + `
  globalThis.completeVendors = savedSavedFilterValues({dataset_ids: [1, 2], context_filters: {Vendor: ['Ericsson', 'Nokia']}}, 'Vendor');
  globalThis.subsetVendors = savedSavedFilterValues({dataset_ids: [1, 2], context_filters: {Vendor: ['Nokia']}}, 'Vendor');
  globalThis.submittedFilters = selectedContextFilters();
  globalThis.title = savedFilterCardTitle(savedFilter);
  globalThis.cdrSummary = savedFilterCdrSummary(savedFilter);
  globalThis.metadataCdrSummary = savedFilterCdrSummary({source_metadata: {data: {name: 'data.csv'}, voice: {name: 'voice.csv'}}});
  globalThis.partialVendors = savedSavedFilterValues({context_filters: {Vendor: ['Nokia']}, resolved_context_filters: {Vendor: ['Nokia', 'Ericsson']}}, 'Vendor');
  globalThis.legacyVendors = savedSavedFilterValues({resolved_context_filters: {Vendor: ['Ericsson']}}, 'Vendor');
  globalThis.fallbackTitle = savedFilterCardTitle({created_at: 'not-a-date', nr_mode: 'SA', dataset_ids: [1], source_metadata: [{campaigns: ['UK_Q3_2026']}]});`, context);
process.stdout.write(JSON.stringify({title: context.title, cdrSummary: context.cdrSummary,
  metadataCdrSummary: context.metadataCdrSummary, fallbackTitle: context.fallbackTitle,
  partialVendors: context.partialVendors, legacyVendors: context.legacyVendors,
  completeVendors: context.completeVendors, subsetVendors: context.subsetVendors, submittedFilters: context.submittedFilters}));
"""
    result = _run_node_json(program, payload)

    assert result['title'].split(' ● ')[1:] == [
        'NSA', 'All Regions', 'All Clusters', 'All Cities', 'All Operators', 'All Vendors', '2026-Q2',
    ]
    assert result['cdrSummary'] == 'data.csv, voice.csv'
    assert result['metadataCdrSummary'] == 'data.csv, voice.csv'
    assert result['completeVendors'] == []
    assert result['subsetVendors'] == ['Nokia']
    assert result['submittedFilters'] == {'Vendor': ['Nokia', 'Ericsson']}
    assert result['partialVendors'] == ['Nokia']
    assert result['legacyVendors'] == ['Ericsson']
    assert result['fallbackTitle'].split(' ● ')[1:] == [
        'SA', 'All Regions', 'All Clusters', 'All Cities', 'All Operators', 'All Vendors', '2026-Q3',
    ]


def test_kpi_value_cells_are_blank_for_category_subtotals_in_both_table_modes():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    assert script.count("cell.textContent = isCategoryRow ? '' : formatRawKpiValue(rawValue);") == 2
    assert script.count("const isCategoryRow = item?.row_type === 'category';") == 2


def test_allocation_donut_global_environment_rings_and_single_environment_radius():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    functions = '\n'.join(_function_source(script, name) for name in (
        'formatChartNumber', 'maximumAllocationEnvironments', 'allocationEnvironmentLabel', 'allocationCategoryLabel', 'allocationIconPath',
        'allocationSectorPath', 'wrappedSvgLabelLines', 'safeHexColor', 'readableTextColor', 'makeMaximumAllocationDonut',
    ))
    program = functions + """
const document = {createElementNS: () => ({attributes: {}, children: [],
  setAttribute(name, value) {this.attributes[name] = value;},
  append(...children) {this.children.push(...children);}})};
const svgElement = (svg, tag, attributes) => ({tag, attributes, children: [], textContent: '',
  setAttribute(name, value) {this.attributes[name] = value;},
  append(...children) {this.children.push(...children);}});
const setChartTooltip = () => {};
const formattedChartPoints = number => Number(number).toFixed(2);
const config = {scope: {environments: {DriveCity: {total_points: 650}, 'Drive Connecting Roads': {total_points: 350}}},
 metrics: [
 {source_kind: 'voice', contexts: {DriveCity: {max_points: 227.5}, 'Drive Connecting Roads': {max_points: 122.5}}},
 {source_kind: 'data', contexts: {DriveCity: {max_points: 422.5}, 'Drive Connecting Roads': {max_points: 227.5}}}]};
const all = maximumAllocationEnvironments({context: {environment: 'Combined'}}, [], config);
const single = maximumAllocationEnvironments({context: {environment: 'Drive Connecting Roads'}}, [], config);
const globalSvg = makeMaximumAllocationDonut(all);
const singleSvg = makeMaximumAllocationDonut(single);
const segments = svg => svg.children.filter(item => item.attributes?.['data-allocation-segment']).map(item => item.attributes);
const icons = svg => svg.children.filter(item => item.tag === 'path' && item.attributes?.transform);
const textContent = svg => svg.children.filter(item => item.tag === 'text').map(item => item.children?.length
  ? item.children.map(child => child.textContent || '').join('') : item.textContent || '').join('|');
console.log(JSON.stringify({all, single, global: segments(globalSvg), one: segments(singleSvg),
 icons: icons(globalSvg).length,
 globalText: textContent(globalSvg),
 singleText: textContent(singleSvg)}));
"""
    result = _run_node_json(program, {})
    assert len(result['global']) == 4  # Environment allocation plus one global Voice/Data ring.
    assert [item['fill'] for item in result['global'][:2]] == ['#176E77', '#E6A81D']
    assert [item['fill'] for item in result['global'][2:]] == ['#4472C4', '#7030A0']
    assert len(result['one']) == 3
    assert [item['fill'] for item in result['one']] == ['#E6A81D', '#4472C4', '#7030A0']
    assert result['one'][0]['data-allocation-radius'] == result['global'][0]['data-allocation-radius'] == pytest.approx(134.16)
    assert result['one'][0]['data-allocation-center'] == '230,230'
    assert result['one'][0]['d'].count(' A ') == 4
    assert [item['data-allocation-radius'] for item in result['one'][1:]] == pytest.approx([89.5408, 89.5408])
    assert result['global'][0]['data-allocation-radius'] > result['global'][2]['data-allocation-radius']
    assert len(result['single']) == 1 and result['single'][0]['color'] == '#E6A81D'
    assert result['icons'] == 7  # Five legend icons plus two exterior environment markers.
    assert '1000.00' in result['globalText']
    assert '350.00' in result['singleText']
    assert 'Drive - Connecting Roads:' in result['singleText']
    assert 'Global:' not in result['singleText']


def test_summary_operator_highlights_rank_all_columns_and_include_ties():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    names = ('firstValue', 'operatorValue', 'summaryOperatorColors')
    payload = {'snippets': {name: _function_source(script, name) for name in names}}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n') + `
  const columns = ['A', 'B', 'C', 'D', 'E', 'F'].map((id, index) => ({
    id, path: [{level: 'Operator', value: id}, {level: 'Region', value: index < 4 ? 'North' : 'South'}],
  }));
  const values = {A: {points: 10}, B: {points: 10}, C: {points: 2}, D: {points: 2},
    E: {points: 100}, F: {points: 50, complete: false}};
  globalThis.ranked = [...summaryOperatorColors(values, columns)];
  globalThis.equal = [...summaryOperatorColors({A: {points: 2}, B: {points: 2}}, [{id: 'A'}, {id: 'B'}])];
  globalThis.missing = [...summaryOperatorColors({A: {points: 0}, B: {points: null}, C: {points: 'bad'}},
    [{id: 'A'}, {id: 'B'}, {id: 'C'}])];
`, context);
process.stdout.write(JSON.stringify({ranked: context.ranked, equal: context.equal, missing: context.missing}));
"""
    result = _run_node_json(program, payload)
    assert dict(result['ranked']) == {
        'C': '#FFC7CE', 'D': '#FFC7CE', 'E': '#C6EFCE',
    }
    assert result['equal'] == []
    assert result['missing'] == []
    assert script.count('appendOperatorRankingLegend(summarySection);') == 2
    assert script.count('appendThresholdLegend(expandedSection,') == 2
    assert script.count('isSummary ? (summaryColors.get(') == 4


def test_scoring_category_cells_span_kpis_and_subtotal_in_both_renderers():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    names = (
        'firstValue', 'operatorValue', 'operatorPresentation', 'safeHexColor', 'readableTextColor',
        'formatMatrixNumber', 'createKpiTypeCell', 'showGapValues', 'selectedGapLayout',
        'appendScoreGapCells', 'hierarchyColumnEntries', 'hierarchyColumnIsReference',
        'appendMatrixTable', 'appendHierarchyMatrixTable', 'summaryOperatorColors',
        'styleIncompleteValue',
        'applyGapCategoryRunColors',
    )
    payload = {'snippets': {name: _function_source(script, name) for name in names}}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.style = {setProperty() {}};
    this.className = ''; this.classList = {add: value => { this.className += ` ${value}`; }}; }
  append(...nodes) { this.children.push(...nodes); }
  querySelectorAll() { return descendants(this).filter(node => node.className === "scoring-category-cell"); }
}
const context = {
  document: {createElement: tag => new Element(tag)}, showKpiValuesToggle: {checked: false},
  showGapValuesToggle: {checked: false}, gapLayoutSelect: {value: 'end'},
  observeScoringValueCells: () => {}, applyScorecardLayout: () => {},
  appendHierarchyHeaders: (thead, _data, _columns, definitions) => {
    const row = new Element('tr');
    for (const [label, column] of definitions) {
      const th = new Element('th'); th.textContent = label; th.dataset.column = column; row.append(th);
    }
    thead.append(row);
  },
};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n') + `
  globalThis.renderers = [appendMatrixTable, appendHierarchyMatrixTable];`, context);
const fixture = {_display_mode: 'expanded', operators: [], rows: [
  {category: 'Voice', kpi: 'Call Setup'}, {category: 'Voice', kpi: 'Drop Rate'},
  {category: 'Voice', kpi: 'Voice total', row_type: 'category'},
  {category: 'Data', kpi: 'Throughput'}, {category: 'Data', kpi: 'Data total', row_type: 'category'},
]};
function descendants(node) { return [node, ...node.children.flatMap(descendants)]; }
const result = context.renderers.map(render => {
  const pane = new Element('div'); render(pane, fixture); const nodes = descendants(pane);
  return {
    categories: nodes.filter(node => node.tagName === 'td' && node.dataset.column === 'category')
      .map(node => [node.textContent, node.rowSpan]),
    headers: nodes.filter(node => node.tagName === 'th' && ['category', 'kpi'].includes(node.dataset.column))
      .map(node => [node.textContent, node.dataset.column]),
    subtotals: nodes.filter(node => node.className.includes('scoring-category-subtotal'))
      .map(node => node.children.filter(child => child.dataset.column === 'kpi').map(child => child.textContent)),
  };
});
process.stdout.write(JSON.stringify(result));
"""
    for result in _run_node_json(program, payload):
        assert result['categories'] == [['Voice', 3], ['Data', 2]]
        assert result['headers'] == [['CATEGORY', 'category'], ['KPI', 'kpi']]
        assert result['subtotals'] == [['Voice total'], ['Data total']]


def test_calculation_match_controls_cover_pending_cache_and_stale_responses():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    payload = {'snippets': {
        name: _function_source(script, name)
        for name in ('calculationPayload', 'updateCalculationMatch')
    }}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const timers = [];
const messages = [];
const requests = [];
const shown = [];
const context = {
  calculationMatchKey: '', calculationMatchRevision: 0, calculationMatchTimer: null, calculationMatchRefresh: false,
  submittingCalculation: false, savedFiltersUrl: '/api/scoring/saved-filters', editingSavedFilter: null,
  calculateButton: {disabled: false}, recalculateButton: {disabled: false},
  selectedLevels: () => ['City'], selectedDatasetIds: () => [12, 14],
  scoringProfileSelect: {value: 'profile-a'}, nrFilter: {value: 'NSA'},
  baselineInput: {value: 'Operator A'}, selectedContextFilters: () => ({Region: ['North']}),
  areaSummaryPayload: () => null,
  chosenComparedOperators: () => [],
  // Calculate Scoring or Open Scoring, as each answer tells it.
  showCalculateAction: open => shown.push(open),
  normalizeStatus: savedFilter => savedFilter?.status || '', isActive: savedFilter => ['queued', 'processing'].includes(savedFilter?.status),
  setMessage: (text, kind = '') => messages.push({text, kind}),
  requestJson: (...args) => new Promise((resolve, reject) => requests.push({args, resolve, reject})),
  window: {
    setTimeout: callback => { timers.push(callback); return timers.length; },
    clearTimeout: () => {},
  },
};
vm.createContext(context);
vm.runInContext(Object.values(payload.snippets).join('\n'), context);
async function flush() { await new Promise(resolve => setImmediate(resolve)); }
async function main() {
  context.updateCalculationMatch(true);
  const pending = [context.calculateButton.disabled, context.recalculateButton.disabled];
  timers[0]();
  requests[0].resolve({saved_filter: null});
  await flush();
  const noMatch = [context.calculateButton.disabled, context.recalculateButton.disabled, messages.at(-1)?.text];

  context.calculationMatchKey = '';
  context.updateCalculationMatch(true);
  timers[1]();
  requests[1].resolve({saved_filter: {id: 8, status: 'completed', up_to_date: true}});
  await flush();
  const completed = [context.calculateButton.disabled, context.recalculateButton.disabled, shown.at(-1), messages.at(-1)?.text];

  context.calculationMatchKey = '';
  context.updateCalculationMatch(true);
  timers[2]();
  requests[2].resolve({saved_filter: {id: 9, status: 'queued'}});
  await flush();
  const active = [context.calculateButton.disabled, context.recalculateButton.disabled];

  // The savedFilter polling checks the same selection again without enabling or disabling the buttons meanwhile.
  context.calculateButton.disabled = false;
  context.calculationMatchRefresh = true;
  context.updateCalculationMatch(true);
  const refreshing = [context.calculateButton.disabled, context.recalculateButton.disabled, requests.length];
  timers.at(-1)();
  requests.at(-1).resolve({saved_filter: {id: 9, status: 'queued'}});
  await flush();
  const refreshed = [context.calculateButton.disabled, context.recalculateButton.disabled];
  timers.splice(3); requests.splice(3);

  context.calculationMatchKey = '';
  context.updateCalculationMatch(true);
  const staleRevision = context.calculationMatchRevision;
  timers[3]();
  context.baselineInput.value = 'Operator B';
  context.updateCalculationMatch(true);
  timers[4]();
  requests[4].resolve({saved_filter: null});
  await flush();
  const latestMessage = messages.at(-1)?.text;
  requests[3].resolve({saved_filter: {id: 10, status: 'completed'}});
  await flush();
  const staleResponseIgnored = context.calculationMatchRevision > staleRevision
    && context.calculateButton.disabled === false && context.recalculateButton.disabled === true
    && messages.at(-1)?.text === latestMessage;
  process.stdout.write(JSON.stringify({pending, noMatch, completed, active, refreshing, refreshed, staleResponseIgnored, shown,
    matchUrl: requests[0].args[0], matchPayload: JSON.parse(requests[0].args[1].body)}));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = _run_node_json(program, payload)
    assert result['pending'] == [True, True]
    assert result['noMatch'] == [False, True, 'Ready to calculate the scoring of these filters.']
    # Filters used before: Calculate opens them (calculated again when out of date), Recalculate calculates them again;
    # with their result up to date the button reads Open Scoring.
    assert result['completed'] == [False, False, True,
                                   'This selection is a Saved Filter with its result up to date: Open Scoring opens it, Recalculate calculates it again.']
    assert result['shown'][0] is False and True in result['shown']
    assert result['active'] == [True, True]
    assert result['refreshing'] == [False, True, 3] and result['refreshed'] == [True, True]
    assert result['staleResponseIgnored'] is True
    assert result['matchUrl'] == '/api/scoring/saved-filters/match'
    assert result['matchPayload'] == {
        'dataset_ids': [12, 14], 'aggregation_levels': ['Operator', 'City'],
        'scoring_profile_id': 'profile-a', 'nr_mode': 'NSA', 'baseline_operator': 'Operator A',
        'context_filters': {'Region': ['North']}, 'area_summary': None, 'compared_operators': [],
    }


def test_result_tabs_have_their_own_colours_on_a_panel_holding_every_result():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    from lxml import html
    tabbed = html.fromstring(template).xpath('//div[@class="scoring-results-tabbed"]')[0]
    tabs = tabbed.xpath('./div[@class="scoring-result-tabs"]/button')
    names = ['summary', 'charts', 'scoring', 'geographical-areas', 'trends', 'gap', 'points']
    assert [tab.get('data-result-tab') for tab in tabs] == names
    assert all(tab.xpath('./svg') for tab in tabs)
    # The seven result panes sit in one panel below the tabs, Summary shown first.
    panes = tabbed.xpath('./div[@class="scoring-result-panels"]/div[@role="tabpanel"]')
    assert [pane.get('data-result-pane') for pane in panes] == names
    assert panes[0].get('hidden') is None and all(pane.get('hidden') is not None for pane in panes[1:])
    for tab, colour in (('summary', '#0369a1'), ('scoring', '#0f766e'), ('geographical-areas', '#7c3aed'), ('trends', '#4d7c0f'),
                        ('gap', '#c2410c'), ('points', '#be123c')):
        assert f'.scoring-result-tab[data-result-tab="{tab}"] {{ --tab-color: {colour}; }}' in template
        assert f'.scoring-results-tabbed:has([data-result-tab="{tab}"][aria-selected="true"]) {{ --result-accent: {colour}; }}' in template


def test_kpi_gap_profile_and_points_lost_map_share_location_and_operators():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    controls = script[script.index('  function gapInsightControls(pane, items) {'):script.index('  function renderKpiGapProfiles(')]
    # One location, several operators: shared by both sections.
    assert "insightSelect('gap-insight-scope'" in controls
    # Locations by campaign are listed chronologically, the latest chosen by default.
    assert "scopes.sort(([, left], [, right]) => globalThis.campaignCompare(left.campaign, right.campaign));" in controls
    assert "let scope = (byCampaign ? scopes.at(-1) : scopes[0])?.[0] ?? '{}';" in controls
    assert "chip.dataset.gapInsightOperator = item.operator;" in controls
    profiles = script[script.index('  function renderKpiGapProfiles('):script.index('  // Points lost per area:')]
    assert 'gapInsightControls(pane, profiles)' in profiles and "inScope.filter(item => chosen.includes(item.operator))" in profiles
    maps = script[script.index('  function renderPointsLossMaps('):script.index("  // One operator's map with the note")]
    # The map adds the analysis per City, Region or Cluster; several operators show their maps side by side.
    assert 'gapInsightControls(pane, entries.map(' in maps
    # City, Region and Cluster are always listed; those without results are disabled.
    assert "insightSelect('points-loss-view', allViews.map(item => [item, item]), 'Maps per')" in maps
    assert "option.disabled = !views.includes(option.value);" in maps
    assert ".map(entry => pointsLossMapCard(entry, payload, savedFilterId, chosen.length > 1, mode));" in maps
    # The Focus operators are chosen by default (every operator without them), first in the choice.
    assert "if (!chosen.length) chosen = focusDefault(operators, {withReference: true});" in controls
    assert 'appendFocusChips(group, operators, makeChip);' in controls
    # Maps zoom with a dragged rectangle or the floating buttons, which hide as soon as the pointer leaves.
    zoom = script[script.index('  function addZoomToolbar(box, zoomIn, zoomOut, reset) {'):]
    assert "['+', 'Zoom in'" in zoom and "['−', 'Zoom out'" in zoom and "'Show the whole map'" in zoom
    assert "box.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse') hide(); });" in zoom
    assert "svg.addEventListener('pointerdown'" in zoom and "svg.addEventListener('pointerup', finish)" in zoom
    # The zoomed view keeps the map's proportions, so the map (and the table below it) keep their size.
    assert "const ratio = box.width > 0 && box.height > 0 ? box.width / box.height : original[2] / original[3];" in zoom
    # A wide chart that scrolls sideways is fitted to the visible width while zoomed, so the chosen area is centred there.
    assert "const scroller = svg.closest('.scoring-chart-scroll');" in zoom and "fitToVisibleBox(!whole);" in zoom
    # Toggling an operator keeps at least one; the GAP comparison follows a single operator and the reverse.
    assert "if (!chosen.length) return;\n      insightSelections.set('gap-insight-operators', JSON.stringify(chosen));" in script
    assert "if (hierarchyGapOperator.value.startsWith('operator:')) {\n        insightSelections.set('gap-insight-operators'" in script
    # The selections are kept on reload and reset when the page is opened again.
    assert "const insightSelections = new Map(pageReloaded ? Object.entries(restoredScoringViewState.insightSelections || {}) : []);" in script
    assert "insight_selections: typeof insightSelections === 'undefined' ? {} : Object.fromEntries(insightSelections)," in script
    program = _function_source(script, 'lossScopeLabel') + """
const hierarchyDisplayValue = item => item.value;
process.stdout.write(JSON.stringify([lossScopeLabel({city: 'London'}), lossScopeLabel({}), lossScopeLabel({region: 'North', campaign: '2026-Q2'})]));
"""
    assert _run_node_json(program, {}) == [
        {'title': 'City', 'value': 'London'}, {'title': 'Scope', 'value': ''},
        {'title': 'Region · Campaign', 'value': 'North · 2026-Q2'}]


def test_charts_maps_and_tables_open_larger_and_charts_zoom():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    # Every Scoring chart zooms like the maps; the zoom buttons do not open the larger view.
    assert "if (svg) enableMapZoom(card, svg);" in script
    assert "if (event.target.closest('.scoring-map-zoom')) return;" in script and 'else openExpandedChart(card);' in script
    # Maps and the tables of Scoring Tables and GAP Analysis open larger with a double click; charts and maps zoom there.
    assert "root.addEventListener('dblclick', event => {" in script
    assert "openExpandedView(map.querySelector('svg'), ['Points Lost Map', operator]" in script
    assert "openExpandedView(table, titleWithoutScope(heading) || 'Scoring table', meta, table, 'Table');" in script
    # The larger view keeps the pills of the title of its chart, map or table.
    # (Charts, maps, the route maps of Where to act and Points Lost, and tables.)
    assert script.count('appendExpandedScope(') == 5
    assert "if (copy.matches?.('svg')) enableMapZoom(holder, copy);" in script
    # Content that is not one SVG (such as the location cards) zooms by scaling it inside its box.
    assert "else enableContentZoom(card, scroll);" in script and "else if (!isTable) enableContentZoom(holder, holder);" in script
    # The larger view takes the whole screen but 5% on each side.
    assert 'width: 90vw; height: 90vh; height: 90dvh;' in template
    # On touch screens a tap shows the zoom buttons for a few seconds, until a tap elsewhere.
    toolbar = _function_source(script, 'addZoomToolbar')
    assert "box.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') show(); });" in toolbar
    assert 'hideTimer = window.setTimeout(hide, 5000);' in toolbar
    # Charts drawn again add no page listeners (which would keep the charts they replace in memory): one listener
    # for the page hides the buttons on a tap elsewhere.
    assert "document.addEventListener" not in toolbar
    assert "for (const toolbar of document.querySelectorAll('.scoring-map-zoom.is-visible')) {" in script
    # While the Points Lost Map is prepared, the light list of Saved Filters is checked, not the whole result.
    assert 'const list = await requestJson(savedFiltersUrl);' in script and 'current.updated_at !== loadedAt' in script


def test_the_calculation_message_stays_while_the_selected_job_calculates():
    script = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/scoring.js').read_text(encoding='utf-8')
    # The status of the selected CDRs and filters is kept while the job list refreshes every few seconds.
    assert "text = `${verb} the scoring of the selected CDRs and filters…`;" in script
    assert "const verb = recalculatingSavedFilters.has(String(savedFilterIdOf(existing))) ? 'Recalculating' : 'Calculating';" in script
    assert "} else if (selectionStatus.key && selectionStatus.key === JSON.stringify(calculationPayload())) {" in script
    assert 'already queued or running' not in script


def test_a_calculating_job_shows_an_animated_progress_bar_instead_of_placeholders():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    load_job = _function_source(script, 'loadSavedFilter')
    # The selected active job shows the bar at once and at every poll, never Loading… or the waiting message.
    assert 'if (isActive(savedFilter)) renderCalculating(savedFilter);' in load_job
    # The results of a saved job load under the same striped bar, across its whole width.
    assert 'else renderLoadingResults();' in load_job
    assert 'Loading Scoring Results…' in _function_source(script, 'renderLoadingResults')
    assert "} else if (isActive(record)) {" in load_job and 'renderCalculating(record);' in load_job
    calculating = _function_source(script, 'renderCalculating')
    assert 'Calculating Scoring…' in calculating and "current.forEach(update);" in calculating
    assert '@keyframes scoring-calculating-stripes' in template
    # The job polling checks the selection again without toggling the buttons.
    assert 'calculationMatchRefresh = true;' in _function_source(script, 'refreshSavedFilters')


@pytest.mark.skipif(not shutil.which('node'), reason='Node.js is required')
def test_scoring_jobs_show_their_calculation_time_or_elapsed_time():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    program = r'''
const valueOf = (savedFilter, keys, fallback) => keys.map(key => savedFilter[key]).find(value => value !== undefined && value !== null && value !== '') ?? fallback;
const isActive = savedFilter => ['queued', 'processing'].includes(savedFilter.status);
''' + _function_source(script, 'savedFilterDurationText') + r'''
const now = Date.parse('2026-10-09T18:00:00+02:00');
process.stdout.write(JSON.stringify([
  savedFilterDurationText({status: 'completed', started_at: '2026-10-09T17:58:35+02:00', finished_at: '2026-10-09T17:59:20+02:00'}, now),
  savedFilterDurationText({status: 'completed', started_at: '2026-10-09T17:55:00+02:00', finished_at: '2026-10-09T17:58:07+02:00'}, now),
  savedFilterDurationText({status: 'processing', started_at: '2026-10-09T16:40:00+02:00'}, now),
  savedFilterDurationText({status: 'queued', started_at: ''}, now),
  savedFilterDurationText({status: 'failed', started_at: '2026-10-09T17:55:00+02:00'}, now),
]));
'''
    assert _run_node_json(program, {}) == ['45 s', '3 min 07 s', '1 h 20 min', '', '']
    assert "durationMeta.textContent = isActive(savedFilter) ? 'Elapsed: ' : 'Calculation time: ';" in script


@pytest.mark.skipif(not shutil.which('node'), reason='Node.js is required')
def test_campaign_comparison_compares_the_chosen_baseline_and_campaign():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    render = _function_source(script, 'renderCampaignComparisons')
    assert "'Operator'" in render and "'Baseline campaign'" in render and "'Compared campaign'" in render
    assert "String(campaigns.length - 2)" in render and "String(campaigns.length - 1)" in render
    program = _function_source(script, 'campaignComparisonRows') + r'''
const comparison = {campaigns: ['25-Q4', '26-Q1', '26-Q2'], kpis: [
  {kpi_code: 'a', kpi: 'A', service: 'data', values: [{value: 1, points: 10}, {value: 2, points: 12}, {value: 3, points: 9}]},
  {kpi_code: 'b', kpi: 'B', service: 'voice', values: [{value: 4, points: 5}, null, {value: 6, points: 8}]},
]};
process.stdout.write(JSON.stringify([campaignComparisonRows(comparison, 0, 2), campaignComparisonRows(comparison, 1, 2)]));
'''
    first, second = json.loads(subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True).stdout)
    assert [(row['kpi_code'], row['delta']) for row in first['rows']] == [('a', -1), ('b', 3)]
    assert first['total_delta'] == 2
    # A KPI without points in one of the campaigns has no Δ and goes last.
    assert [(row['kpi_code'], row['delta']) for row in second['rows']] == [('a', -3), ('b', None)]
    assert second['total_delta'] == -3


@pytest.mark.skipif(not shutil.which('node'), reason='Node.js is required')
def test_scoring_jobs_show_their_scoring_trends():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    cards = _function_source(script, 'renderSavedFilters')
    # As the panel: the Geographical Areas (Breakdown and Separate cities), then the campaigns and time split of the Scoring Trends.
    assert "areaMeta.textContent = 'Geographical Areas: ';" in cards
    assert "trendMeta.append('Scoring Trends: Campaigns: ', trendValue, ' · Time split: ', timeValue);" in cards
    assert cards.index('areaMeta') < cards.index('trendMeta')
    # Each value in its own colour, after its label.
    assert "areaValue.className = `saved-filter-area-summary saved-filter-area-summary-${kind}`;" in cards
    program = _function_source(script, 'savedFilterAreaSummaryParts') + _function_source(script, 'savedFilterTimeSplit') + r'''
process.stdout.write(JSON.stringify([
  savedFilterAreaSummaryParts({area_summary: {time_split: 'Campaign', breakdown: 'Region', cities: ['London']}}),
  savedFilterAreaSummaryParts({area_summary: {time_split: 'All', breakdown: null, cities: ['London', 'Leeds']}}),
  savedFilterAreaSummaryParts({area_summary: {time_split: 'Campaign', breakdown: null, cities: [], campaigns: ['@all-campaigns']}}),
  savedFilterAreaSummaryParts({area_summary: null}),
  savedFilterTimeSplit({area_summary: {time_split: 'All'}}), savedFilterTimeSplit({}),
]));
'''
    shown = json.loads(subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True).stdout)
    # One saved without areas shows those it is calculated with: each Region and London.
    default = [['breakdown', 'Breakdown', 'Region'], ['cities', 'Separate cities', 'London']]
    assert shown == [default, [['breakdown', 'Breakdown', 'None'], ['cities', 'Separate cities', 'London, Leeds']], default, default,
                     'All selected CDRs', 'Campaign']


def test_the_scoring_trend_comes_before_the_national_and_areas():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    trends = _function_source(script, 'renderTrends')
    # The Scoring Trends tab: the Scoring Trend, then the National & Geographical Areas Trends; Geographical Areas keeps
    # the scoring per location.
    assert trends.index("insightItems(payload, 'campaign_trends', environment)") < trends.index(
        "insightItems(payload, 'area_summaries', environment)")
    assert "`${scoringLabel()} Trends — National & Geographical Areas`" in trends
    locations = _function_source(script, 'renderGeographicalAreas')
    assert "'area_summaries'" not in locations and "insightItems(payload, 'location_cards', environment)" in locations
    assert 'No Geographical Areas views: calculate the scoring again to see them per Region and for London' in locations
    # The titles of the area charts: National, the breakdown and the cities in their own colours.
    chart = _function_source(SCORING_SCRIPT.read_text(encoding='utf-8'), 'makeAreaTrendChart')
    assert "caption.className = `is-${areaCategory(area)}`;" in chart


def test_the_area_charts_take_the_height_of_the_table_and_tilt_crowded_labels():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    view = _function_source(script, 'makeAreaSummaryView')
    assert "new ResizeObserver(() => fitCharts()).observe(view)" in view
    assert "height = Math.max(170, Math.min(420, Math.round(available * 360 / chartWidth)));" in view
    chart = _function_source(script, 'makeAreaTrendChart')
    assert "const tilted = campaigns.length > 1 && labelWidth > spacing - 4;" in chart
    assert "transform: `rotate(-40 ${x(index)} ${labelY})`" in chart
    # Each chart enlarges alone with a double click, not the whole National & Areas card.
    assert 'figure.expandPart = () => {' in chart
    card = _function_source(script, 'makeExpandableChartCard')
    assert "map(element => element.closest?.('.scoring-expandable-part')).find(Boolean);" in card
    assert 'if (part?.expandPart) part.expandPart();' in card
    # The table beside the charts enlarges on its own too.
    assert 'tableWrap.expandPart = () => openExpandedView(' in _function_source(script, 'makeAreaSummaryView')
    assert "openExpandedView(large, `${scoringLabel()} — ${area.label}`, 'National & Geographical Areas Trends', figure, 'Area trend');" in chart



def test_an_opened_saved_filter_lists_only_its_cdrs_with_its_campaigns():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    program = f"""
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const uniqueCatalogueValues = values => [...new Set((values || []).map(String))];
const campaignLabelOf = value => ({{UK_Q2_2026: '26-Q2', UK_Q3_NSA_2026: '26-Q3'}})[value] || value;
const datasetCatalogues = new Map(Object.entries(payload.catalogues));
let pinnedCdrs = payload.pinned;
const selectedDatasetIds = () => payload.ids;
const selectedContextFilters = () => ({{Campaign: payload.campaigns}});
{_function_source(script, 'usedDatasetIds')}
process.stdout.write(JSON.stringify(usedDatasetIds()));
"""
    catalogues = {'1': {'campaigns': ['UK_Q2_2026']}, '2': {'campaigns': ['UK_Q3_NSA_2026']},
                  '3': {'campaigns': ['UK_Q3_NSA_2026']}, '4': {}}
    opened = {'ids': ['1', '2', '3', '4'], 'catalogues': catalogues, 'campaigns': ['UK_Q3_NSA_2026'], 'pinned': True}
    # The CDRs of other campaigns are not shown as used (a CDR without known campaigns stays).
    assert _run_node_json(program, opened) == ['2', '3', '4']
    # Its Campaign by its label too; without a Campaign filter, or with automatic CDRs, every CDR is used.
    assert _run_node_json(program, {**opened, 'campaigns': ['26-Q2']}) == ['1', '4']
    assert _run_node_json(program, {**opened, 'campaigns': []}) == ['1', '2', '3', '4']
    assert _run_node_json(program, {**opened, 'pinned': False}) == ['1', '2', '3', '4']


def test_saved_filters_are_edited_in_a_dialog_with_the_calculation_panel():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    # The pencil keeps Save Name and adds Edit Filters, which opens the Calculation panel in a dialog.
    assert "confirmLabel: 'Save Name'," in script and "secondaryLabel: 'Edit Filters'," in script
    assert '<dialog class="scoring-edit-dialog" data-saved-filter-edit-dialog' in template
    start = _function_source(script, 'startSavedFilterEdit')
    assert "restoreCalculationSelectionFromSavedFilter(savedFilter, {automaticCdrs: true});" in start
    assert 'editDialog.append(calculationPanel);' in start and 'editDialog.showModal();' in start
    stop = _function_source(script, 'stopSavedFilterEdit')
    assert 'editPanelPlaceholder.replaceWith(calculationPanel);' in stop
    assert 'applySavedCalculationSelection(before.selection);' in stop
    # Cancel Editing comes before Save Changes, both in place of Calculate Scoring and Recalculate.
    actions = template[template.index('data-recalculate-scoring'):]
    assert actions.index('data-saved-filter-edit-cancel') < actions.index('data-saved-filter-edit-save')
    assert '<span>Cancel Editing</span>' in actions and '<span>Save Changes</span>' in actions
    sync = _function_source(script, 'syncSavedFilterEditing')
    assert 'calculateButton.hidden = editing;' in sync and 'if (editCancelButton) editCancelButton.hidden = !editing;' in sync
    assert "createSavedFilter(false, {url: `${savedFiltersUrl}/${encodeURIComponent(savedFilterIdOf(savedFilter))}/edit`})" in script


def test_chart_and_table_titles_name_their_area_operators_and_vendors():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    payload = {'snippets': {'resultScope': _function_source(script, 'resultScope')}}
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {};
vm.createContext(context);
vm.runInContext('let resultScopeFilters = {};\nconst scoringVendorName = value => value.replace(/^(EE|O2 UK)_/, "");\n'
  + payload.snippets.resultScope + `
function scopeOf(filters, tableContext = null) {
  resultScopeFilters = filters;
  return resultScope(tableContext).map(item => item.label);
}
globalThis.scopes = [
  scopeOf({Region: [], City: [], Operator: [], Vendor: []}),
  scopeOf({City: ['London']}),
  scopeOf({City: ['Leeds', 'London']}),
  scopeOf({City: ['Bristol', 'Cardiff', 'Leeds']}),
  scopeOf({City: ['Bristol', 'Cardiff', 'Leeds', 'London', 'York']}),
  scopeOf({Region: ['Wales'], City: []}),
  scopeOf({Region: ['Wales'], Cluster: ['Cardiff Bay']}),
  scopeOf({City: ['Leeds', 'London']}, {city: 'Leeds', campaign: 'UK_Q2_2026'}),
  scopeOf({City: ['London']}, {region: 'London'}),
  scopeOf({}, {region: 'Wales', environment: 'Combined'}),
  scopeOf({Operator: ['EE'], Vendor: ['EE_Nokia', 'O2 UK_Nokia', 'O2 UK_Ericsson']}),
  scopeOf({Operator: ['EE', 'O2 UK', 'Three UK', 'Vodafone UK'], Vendor: ['EE_Nokia']}, {vendor: 'Samsung'}),
];
resultScopeFilters = {City: ['Bristol', 'Cardiff', 'Leeds', 'London', 'York']};
globalThis.tooltip = resultScope()[0].title;`, context);
process.stdout.write(JSON.stringify({scopes: context.scopes, tooltip: context.tooltip}));
"""
    result = _run_node_json(program, payload)
    everything = ['All Operators', 'All Vendors']
    assert result['scopes'] == [
        ['National', *everything], ['City: London', *everything], ['Cities: Leeds & London', *everything],
        ['Cities: Bristol, Cardiff & Leeds', *everything], ['Cities: Bristol, Cardiff & 3 more', *everything],
        ['Region: Wales', *everything], ['Cluster: Cardiff Bay', *everything], ['City: Leeds', *everything],
        ['City: London', *everything], ['Region: Wales', *everything],
        # Vendors are named without their operator, as on the Saved Filter cards.
        ['National', 'Operator: EE', 'Vendors: Nokia & Ericsson'],
        ['National', 'Operators: EE, O2 UK & 2 more', 'Vendor: Samsung'],
    ]
    # The tooltip of a shortened list names every value.
    assert result['tooltip'] == 'Cities: Bristol, Cardiff, Leeds, London, York'
    # The results take the filters of the Saved Filter they show.
    assert "resultScopeFilters = resultFilters && typeof resultFilters === 'object' ? resultFilters : {};" in script
    # Every chart and table title ends with its pills; the National & Areas card shows every area and has none.
    card = _function_source(script, 'makeExpandableChartCard')
    assert "const scope = context === false ? null : appendResultScope(heading, context);" in card
    assert "makeAreaSummaryView(summary), false));" in script
    assert "if (kind === 'gap' || kind === 'gap-summary') appendResultScope(heading, context);" in script
    for line in (
        'appendResultScope(summaryHeading, tableData.context);', 'appendResultScope(expandedHeading, tableData.context);',
        'appendResultScope(summaryHeading, selected?.context);', 'appendResultScope(expandedHeading, selected?.context);',
        'appendResultScope(heading, chosen.context);',
    ):
        assert script.count(line) == 1, line
    assert script.count('appendResultScope(heading, inScope[0]?.context);') == 3
    assert "pill.className = `scoring-scope-pill is-${item.kind}`;" in script
    for rule in ('.scoring-scope-pill { display: inline-flex;', '.scoring-scope-pill.is-operator {',
                 '.scoring-scope-pill.is-vendor {'):
        assert rule in template


def test_summary_sections_enable_the_reference_operator_by_default():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    calls = re.findall(r"insightOperatorChips\('([\w-]+)', [^)]*\)", script)
    summary = [call for call in re.findall(r"insightOperatorChips\('summary-operators', [^;]*\);", script)]
    # The Summary (standings, position and levers) chooses every operator, the reference included; the other sections
    # start with the operators compared with it.
    assert len(summary) == 3 and not any('compared: true' in call for call in summary)
    assert {'ranking-operators', 'gap-parts-operators', 'sites-operators'} <= set(calls)


def test_focus_operators_come_first_in_the_operator_choices_of_their_sections():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    app = (SCORING_SCRIPT.parent / 'app.js').read_text(encoding='utf-8')
    # The patterns of the page (valuePatterns), as app.js defines them.
    helper = app[app.index('const VALUE_EXCLUSION'):app.index('function setupCustomMultiSelects() {')]
    program = helper + r"""
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.classList = {add: name => { this.className = name; }}; }
  append(...children) { this.children.push(...children); }
}
const document = {createElement: tag => new Element(tag)};
let focus = ['VF*', 'three*'];
const chosenComparedOperators = () => focus;
""" + ''.join(_function_source(script, name) for name in ('focusMatcher', 'focusSplit', 'appendFocusOptions', 'focusDefault')) + r"""
const operators = [{operator: 'EE', label: 'EE', is_reference: true}, {operator: 'VMO2', label: 'VMO2'},
  {operator: 'VF SA', label: 'VF SA'}, {operator: 'Three', label: 'Three'}];
const select = new Element('select');
appendFocusOptions(select, operators.map(item => [`operator:${item.operator}`, item.label, item.operator, item.label]));
const groups = select.children.map(group => [group.label, group.dataset.dividerBefore || '', group.children.map(option => option.value)]);
const chosen = focusDefault(operators);
focus = ['Orange*'];
const none = [focusDefault(operators), appendFocusOptions(select, []) ?? focusSplit(operators).focused.length];
focus = [];
const all = focusDefault(operators);
// Exclusions: every operator but those they name.
focus = ['NOT vm*'];
const excluding = focusDefault(operators);
console.log(JSON.stringify({groups, chosen, none, all, excluding}));
"""
    result = _run_node_json(program, {})
    # The Focus operators first, under Focus, then a line before the other operators.
    assert result['groups'] == [['Focus', '', ['operator:VF SA', 'operator:Three']],
                                ['Other operators', 'true', ['operator:EE', 'operator:VMO2']]]
    # Their sections start with them; without Focus operators (or none of them in the results), every operator but the
    # reference.
    assert result['chosen'] == ['VF SA', 'Three']
    assert result['none'] == [['VMO2', 'VF SA', 'Three'], 0] and result['all'] == ['VMO2', 'VF SA', 'Three']
    assert result['excluding'] == ['VF SA', 'Three']
