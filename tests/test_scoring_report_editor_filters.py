"""Filters of the Scoring report editor: All, Main Cities, Select All / None and their summaries."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/scoring_report_editor.js').read_text(encoding='utf-8')

# A minimal DOM: elements with children, inputs that toggle on click and fire their change listeners.
DOM = r'''
class Element {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this.className = '';
    this.textContent = ''; this.hidden = false; this.checked = false; this.disabled = false; this.title = ''; this.classList = {add: name => { this.className += ` ${name}`; }}; }
  append(...nodes) { this.children.push(...nodes); }
  prepend(...nodes) { this.children.unshift(...nodes); }
  setAttribute() {}
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  dispatch(type) { (this.listeners[type] || []).forEach(listener => listener({target: this})); }
  click() { if (this.tagName === 'INPUT') { this.checked = !this.checked; this.dispatch('change'); } else this.dispatch('click'); }
  descendants() { return this.children.flatMap(child => [child, ...(child.descendants ? child.descendants() : [])]); }
  querySelector(selector) { return this.descendants().find(node => node.tagName === selector.toUpperCase()) || null; }
  get text() { return [this.textContent, ...this.children.map(child => child.text || '')].join(''); }
}
globalThis.document = {createElement: tag => new Element(tag), querySelectorAll: () => []};
'''


def _function(name: str) -> str:
    start = SCRIPT.index(f'  function {name}(')
    end = SCRIPT.index('\n  }\n', start) + 4
    return SCRIPT[start:end]


@pytest.mark.skipif(not shutil.which('node'), reason='Node.js is required')
def test_filters_keep_values_editable_check_main_cities_and_count_the_selection():
    el_start = SCRIPT.index('  const el = (tag, className, text) => {')
    el_end = SCRIPT.index('  };\n', el_start) + 5
    program = DOM + SCRIPT[el_start:el_end] + "const campaignField = () => false;\n" + _function('checkbox') + _function('checklist') + r'''
const result = {};
const saved = [];
const preset = {label: 'Main Cities', checked: false, values: ['belfast', 'Leeds', 'London'], onChange: checked => saved.push(['main', checked])};
const picker = checklist('City', ['Bangor', 'Belfast', 'Cardiff', 'Leeds'], [], values => saved.push(values), {preset, allOption: true});
const list = picker.children[1];
const rows = list.children.filter(node => node.tagName === 'LABEL');
const box = text => rows.find(row => row.text === text).querySelector('input');
const values = ['Bangor', 'Belfast', 'Cardiff', 'Leeds'];
const state = () => ({summary: picker.children[0].textContent, all: box('All').checked, main: box('Main Cities').checked,
  checked: values.filter(value => box(value).checked), disabled: values.filter(value => box(value).disabled)});
result.initial = state();
box('Main Cities').click(); result.mainCities = state();
box('Leeds').click(); result.afterUncheckingLeeds = state();
const toggle = list.children.find(node => node.tagName === 'BUTTON');
toggle.click(); result.selectAll = state();
toggle.click(); result.selectNone = state();
box('Bangor').click(); box('Cardiff').click(); result.twoValues = state();
result.saved = saved.slice(-1)[0];
console.log(JSON.stringify(result));
'''
    completed = subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    # All keeps the values checked and editable.
    assert result['initial'] == {'summary': 'City: All', 'all': True, 'main': False, 'checked': ['Bangor', 'Belfast', 'Cardiff', 'Leeds'], 'disabled': []}
    # Main Cities checks the workspace main cities found in the CDRs and shows their number.
    assert result['mainCities'] == {'summary': 'City: Main Cities (2/4)', 'all': False, 'main': True, 'checked': ['Belfast', 'Leeds'], 'disabled': []}
    # Editing a value starts from what is shown: the preset becomes an explicit selection.
    assert result['afterUncheckingLeeds'] == {'summary': 'City: Belfast', 'all': False, 'main': False, 'checked': ['Belfast'], 'disabled': []}
    assert result['selectAll']['all'] is True and result['selectAll']['checked'] == ['Bangor', 'Belfast', 'Cardiff', 'Leeds']
    assert result['selectNone'] == {'summary': 'City: All', 'all': False, 'main': False, 'checked': [], 'disabled': []}
    assert result['twoValues']['summary'] == 'City: 2/4 selected'
    assert result['saved'] == ['Bangor', 'Cardiff']


def test_choosing_a_configuration_loads_it_and_unsaved_changes_ask_first():
    # No Load or Default buttons: the selector loads what is chosen, Default included.
    assert "button('Load'" not in SCRIPT and "button('Default'" not in SCRIPT
    assert "saved.addEventListener('change'" in SCRIPT
    assert "choices: [['cancel', 'Cancel'], ['discard', 'Discard changes', 'danger-button'], ['save', 'Save as…', 'primary-button']]" in SCRIPT
    # Every toolbar button has its icon; the JSON buttons share one colour and Delete is red.
    for kind in ('save', 'delete', 'export', 'import'):
        assert f"{kind}: '<path" in SCRIPT
    css = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/css/app.css').read_text(encoding='utf-8')
    assert '.scoring-report-tool:is(.is-export, .is-import)' in css
    assert '.scoring-report-tool.is-delete { border-color: #c62828; background: #c62828;' in css


def test_the_selector_shows_the_configuration_whose_scenarios_are_shown():
    assert "const openedName = String(state.name || '');" in SCRIPT
    assert "const {syncTheme: _syncTheme, ...chosen} = state;" in SCRIPT
    assert "close({configuration: {...clone(chosen), ...(chosenName ? {name: chosenName} : {})}, action});" in SCRIPT
    # Named configurations keep only their scenarios, theme and Export All Operators in Focus panels.
    assert "configuration: {scenarios: state.scenarios, theme: state.theme,\n              all_operators: state.all_operators}" in SCRIPT
    assert "state.all_operators = Boolean(item.configuration?.all_operators);" in SCRIPT
    # Only the panels the workspace exports (Workspace Config > Scoring Export Panels), those of the Focus operators tagged.
    assert "api('/api/scoring/export-panels').then((payload) => {" in SCRIPT
    assert "const shown = options.filter(([key]) => !name || exportable(name, key));" in SCRIPT
    assert "if (name && focusPanel(name, key)) {" in SCRIPT
    # The selector follows the content: the saved configuration with the same scenarios, or none.
    assert "saved.replaceChildren(el('option', '', '<Not saved configuration>'));" in SCRIPT
    assert "current = matchingConfiguration();" in SCRIPT
    assert "const hasUnsavedChanges = () => !matchingConfiguration();" in SCRIPT
    assert "list.addEventListener('input', refreshDifferences);" in SCRIPT


def test_reporting_artifacts_show_the_cdrs_of_their_automatic_choice_and_tabs_sit_on_their_panel():
    root = Path(__file__).resolve().parents[1]
    script = (root / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    # Every artifact lists the CDRs its Campaigns choose now.
    # A Design of NSA & SA resolves the Latest choices among the campaigns of each NR Mode (each_nr_mode).
    assert "const result = await api('/api/reporting/auto-cdrs', {method: 'POST', body: JSON.stringify({nr_mode: nrModeOf(), campaigns: value(), complete, each_nr_mode: eachNrMode})});" in script
    css = (root / 'src/web_interface/static/css/report_jobs.css').read_text(encoding='utf-8')
    assert 'border-radius: 10px 10px 0 0;' in css and 'margin: .3rem 0 -1rem;' in css
    assert 'margin-bottom: -1px; padding: .62rem 1.15rem .6rem;' in css
    # Module artifacts (Non-Qualified Calls) sit inside #rj-providers and join the tabs as well.
    assert '.report-jobs :is(.rj-artifact-tabs ~ .rj-card, .rj-artifact-tabs ~ #rj-providers > .rj-card)[data-rj-module] { margin-top: 0;' in css


def test_reporting_artifacts_choose_their_cdrs_by_campaign():
    script = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/report_jobs.js').read_text(encoding='utf-8')
    assert 'Every ready' not in script
    # CDR Analysis chooses its CDRs from its NR Mode and Campaigns too: no CDR list is left.
    assert 'function datasetPicker(' not in script and 'NEWEST_COMPLETE_TEXT' not in script
    assert "const daCampaigns = campaignPicker(() => daNrMode.value, dataset.campaigns || [], {compact: true});" in script
    assert "$('rj-da-scope').replaceChildren(field('NR Mode', daNrMode), daCampaigns.field);" in script
    # Designs, Scoring and Network Insights choose their Campaigns (Latest campaign, Latest 2 campaigns or chosen ones)
    # in one list right after NR Mode, with the CDRs they choose below that row.
    assert "campaigns = name ? campaignPicker(() => nrMode.value, saved || [], {onChange: () => scheduleLoad(), eachNrMode: true}) : null;" in script
    assert "head.append(field('NR Mode', nrMode), campaignSlot, field('PPT Design', design)" in script
    assert "head.append(field('NR Mode', nrMode), campaigns.field, field('GAP reference operator', baseline)" in script
    assert "head.append(field('NR Mode', nrMode), campaigns.field, field('Technology', technology)" in script
    # (Network Insights chooses one Campaign; the other entries several, with the Latest choices first.)
    assert "picker = single ? singlePicker(listed(), chosen)\n        : multiPicker('Campaigns', listed(), chosen, {exclusive: presets," in script
    assert "const campaigns = campaignPicker(() => nrMode.value, entry.campaigns || [], {complete: true});" in script
    assert "const campaigns = campaignPicker(() => nrMode.value, selection.campaigns || [], {compact: true, single: true});" in script
    # CDR Analysis, the entries of Designs, Scoring and Network Insights, and the Design whose filter values are loaded.
    assert script.count('auto_cdrs: true') == 5
    assert 'function datasetsByKind(' not in script


@pytest.mark.skipif(not shutil.which('node'), reason='Node.js is required')
def test_settings_that_differ_between_scenarios_are_highlighted_in_every_scenario():
    program = _function('settingValue') + _function('markDifferences') + r'''
const options = (enabled = true) => ({enabled, environments: 'all', charts: {service: true}, tables: {kpi_values: false},
  gap: {profile: true}});
const scenario = (filters, levels, mostReliable = true) => ({context_filters: filters, main_cities: false, aggregation_levels: levels,
  scorings: {best_network: options(), most_reliable: options(mostReliable)}});
const scenarios = [scenario({}, ['Operator', 'Campaign']), scenario({City: ['London']}, ['Operator', 'City', 'Campaign']),
  scenario({}, ['Operator', 'Campaign'], false)];
const keys = ['filter:City', 'filter:Region', 'level:City', 'level:Campaign', 'scoring:best_network:charts:service',
  'scoring:most_reliable:enabled', 'scoring:most_reliable:environments', 'scoring:best_network:gap:profile'];
const nodes = scenarios.flatMap((_item, index) => keys.map(key => {
  const classes = new Set();
  return {index, dataset: {diffKey: key}, classes, classList: {toggle: (name, on) => (on ? classes.add(name) : classes.delete(name))},
    closest: () => ({dataset: {scenarioIndex: String(index)}})};
}));
const list = {querySelectorAll: () => nodes};
const highlighted = () => scenarios.map((_item, index) => nodes.filter(node => node.index === index && node.classes.has('is-scenario-diff'))
  .map(node => node.dataset.diffKey));
markDifferences(list, scenarios);
const result = {differences: highlighted()};
scenarios[0].scorings.best_network.charts.service = false;
markDifferences(list, scenarios);
result.afterChange = highlighted()[2];
markDifferences(list, scenarios.slice(0, 1));
result.single = highlighted()[0];
console.log(JSON.stringify(result));
'''
    completed = subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    # The City filter and level and the left-out Most Reliable scoring differ: they are highlighted in every scenario
    # where they apply (a left-out scoring has no environments to compare).
    assert result['differences'] == [
        ['filter:City', 'level:City', 'scoring:most_reliable:enabled'],
        ['filter:City', 'level:City', 'scoring:most_reliable:enabled'],
        ['filter:City', 'level:City', 'scoring:most_reliable:enabled'],
    ]
    # A changed option is highlighted at once, also in the scenarios that kept it.
    assert 'scoring:best_network:charts:service' in result['afterChange']
    # A single scenario has nothing to compare.
    assert result['single'] == []


@pytest.mark.skipif(not shutil.which('node'), reason='Node.js is required')
def test_the_area_summary_keeps_the_area_filters():
    constants_start = SCRIPT.index('  const LEVELS = ')
    constants_end = SCRIPT.index('  const clone = ')
    el_start = SCRIPT.index('  const el = (tag, className, text) => {')
    el_end = SCRIPT.index('  };\n', el_start) + 5
    program = DOM + r'''
Element.prototype.insertAdjacentHTML = function () {};
Element.prototype.querySelector = function (selector) {
  return this.descendants().find(node => node.tagName === selector.toUpperCase()) || null;
};
Element.prototype.dataset = undefined;
const createElement = globalThis.document.createElement;
globalThis.document.createElement = tag => Object.assign(createElement(tag), {dataset: {}, style: {}, value: ''});
''' + SCRIPT[constants_start:constants_end] + "const clone = (value) => JSON.parse(JSON.stringify(value));\n" \
        + SCRIPT[el_start:el_end] + "const campaignField = () => false;\n" + ''.join(
            _function(name) for name in ('completeOptions', 'defaultOptions', 'defaultScenario', 'checkbox', 'checklist', 'optionGroup',
                                         'settingValue', 'scoringPanel', 'scenarioCard')) + r'''
const scenario = defaultScenario({operators: ['EE', '3']});
scenario.area_summary.enabled = false;
scenario.context_filters.Region = ['Vendor A'];
const state = {scenarios: [scenario]};
const context = {filterOptions: {City: ['Leeds', 'London'], Region: ['Vendor A']}, mainCities: ['Leeds'], operators: ['EE', '3']};
const card = scenarioCard(state, 0, context, () => {});
const nodes = card.descendants();
const picker = label => nodes.find(node => node.tagName === 'SUMMARY' && node.textContent.startsWith(label));
const details = label => nodes.find(node => node.tagName === 'DETAILS' && node.children[0] === picker(label));
const labelled = text => nodes.find(node => node.tagName === 'LABEL' && node.text === text).querySelector('input');
const selects = nodes.filter(node => node.tagName === 'SELECT');
const [breakdown, trendChoice, time] = selects;
const result = {defaults: defaultScenario().area_summary, scenarioTime: 'time_split' in defaultScenario(),
  cities: picker('Separate cities:').textContent, tables: scenario.scorings.best_network.tables.area_summary, time: time.value,
  // Saved unchecked: included now, with the area filters as they are (it is scored on the whole country).
  after: {region: details('Region:').dataset.disabled, cities: details('Separate cities:').dataset.disabled,
    breakdown: breakdown.disabled, time: time.disabled, filters: scenario.context_filters, enabled: scenario.area_summary.enabled,
    summary: picker('Region:').textContent},
  legends: nodes.filter(node => node.tagName === 'LEGEND').map(node => node.textContent),
  none: [...breakdown.children].find(option => option.value === 'None').disabled};
// The time split belongs to the summary: Split by keeps Campaign.
time.value = 'Weekly'; time.dispatch('change');
result.weekly = {levels: scenario.aggregation_levels, split: scenario.area_summary.time_split,
  value: settingValue(scenario, 'area:time_split')};
result.disabledValue = settingValue({...scenario, area_summary: {...scenario.area_summary, enabled: false}}, 'area:time_split');
// The campaigns of the Scoring Trends: the scenario's by default, an automatic choice or chosen campaigns.
result.trends = {choice: trendChoice.value, campaigns: [...scenario.area_summary.campaigns],
  legend: nodes.some(node => node.tagName === 'LEGEND' && node.textContent === 'Scoring Trends')};
trendChoice.value = '@latest-2-campaigns'; trendChoice.dispatch('change');
result.trends.preset = [...scenario.area_summary.campaigns];
console.log(JSON.stringify(result));
'''
    completed = subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    # By default the summary breaks the country down by Region, shows London apart and splits by campaign.
    assert result['defaults'] == {'enabled': True, 'time_split': 'Campaign', 'breakdown': 'Region', 'cities': ['London'],
                                  'main_cities': False, 'campaigns': ['@all-campaigns']}
    assert result['scenarioTime'] is False and result['time'] == 'Campaign'
    assert result['cities'] == 'Separate cities: London' and 'tables' not in result
    # Always included, in two subpanels; the area filters stay as they are. None needs Separate cities (London here).
    assert result['after'] == {'breakdown': False, 'time': False, 'filters': {'Region': ['Vendor A']},
                               'enabled': True, 'summary': 'Region: Vendor A'}
    start = result['legends'].index('Geographical Areas & Scoring Trends')
    assert result['legends'][start:start + 3] == ['Geographical Areas & Scoring Trends', 'Geographical Areas', 'Scoring Trends']
    assert result['none'] is False
    assert result['weekly'] == {'levels': ['Operator', 'Campaign'], 'split': 'Weekly', 'value': 'Weekly'}
    assert 'disabledValue' not in result
    # The campaigns of the Scoring Trends are All available campaigns by default.
    assert result['trends'] == {'choice': '@all-campaigns', 'campaigns': ['@all-campaigns'], 'legend': True,
                                'preset': ['@latest-2-campaigns']}


@pytest.mark.skipif(not shutil.which('node'), reason='Node.js is required')
def test_operator_patterns_are_kept_and_listed_first_in_the_report_scenarios():
    app = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/app.js').read_text(encoding='utf-8')
    # The patterns of the page (valuePatterns), as app.js defines them.
    helper = app[app.index('const VALUE_EXCLUSION'):app.index('function setupCustomMultiSelects() {')]
    el_start = SCRIPT.index('  const el = (tag, className, text) => {')
    el_end = SCRIPT.index('  };\n', el_start) + 5
    program = DOM + helper + SCRIPT[el_start:el_end] + "const campaignField = () => false;\nconst completeOptions = () => {};\n" \
        + _function('checkbox') + _function('checklist') + _function('operatorCanonicalizer') + r'''
// A configuration keeps its patterns (resolved when the report is generated), not the operators the CDRs no longer have.
const loaded = operatorCanonicalizer([]).configuration({scenarios: [{context_filters: {Operator: ['Not Lebara', 'VF*', 'Gone', 'EE']}, scorings: {}}]},
  {filterOperators: ['EE', 'VF']});
const picker = checklist('Operator', ['EE', 'VF', 'Lebara'], ['Not Lebara'], () => {}, {allOption: true, patterns: true});
const rows = picker.children[1].children.filter(node => node.tagName === 'LABEL');
console.log(JSON.stringify({kept: loaded.scenarios[0].context_filters.Operator, summary: picker.children[0].textContent,
  first: rows.slice(0, 2).map(row => [row.text, row.className.trim()])}));
'''
    completed = subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    assert result['kept'] == ['Not Lebara', 'VF*', 'EE']
    assert result['summary'] == 'Operator: Not Lebara'
    # The pattern comes first, tagged by what it does, before the All row and the operators.
    assert result['first'][0] == ['Not Lebaraexcept', 'scoring-report-check scoring-report-pattern']


def test_the_report_of_the_page_takes_the_filters_of_its_calculation_panel():
    page = (Path(__file__).resolve().parents[1] / 'src/web_interface/static/js/scoring.js').read_text(encoding='utf-8')
    # The scenarios of the page report choose only their content: no filters, Split by or Geographical Areas & Scoring
    # Trends in the editor, which the request takes from the Calculation panel.
    assert "themes: scoringThemes, theme: activeTheme?.id || 'netcheck', pageScope: true}," in page
    assert "context_filters: selection.context_filters, aggregation_levels: selection.aggregation_levels," in page
    assert "if (context.pageScope) {" in SCRIPT
    # One report: no saved configurations, theme or JSON files, and no other scenarios.
    assert "state.scenarios = state.scenarios.slice(0, 1);" in SCRIPT
    assert "if (!context.pageScope) header.append(toolbar);" in SCRIPT
    assert "dialog.append(header, list, ...(context.pageScope ? [] : [add]), footer);" in SCRIPT
