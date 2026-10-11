"""Saved scoring previousFilter cards select the results shown in the embedded dropdown."""
import re

import pytest

from tests.test_scoring_results_controls import (
    SCORING_SCRIPT, SCORING_TEMPLATE, _function_source, _run_node_json,
)


def test_job_dropdown_is_inside_results_header_and_constrained_to_button_column():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    header = template.split('<div class="scoring-results-head">', 1)[1].split(
        '<div class="scoring-result-tabs"', 1,
    )[0]
    assert template.count('data-previous-filter-list') == 2
    assert template.index('class="panel scoring-results-panel"') < template.index('class="panel scoring-previous-filters-panel"')
    assert header.index('class="scoring-results-tools"') < header.index('data-scoring-previous-filter-selector')
    assert '<summary class="scoring-previous-filter-item"' in header
    assert 'data-selected-previous-filter-card' in header and 'data-previous-filter-list' in header
    assert re.search(r'\.scoring-previous-filter-selector\s*\{[^}]*grid-column: 2;[^}]*grid-row: 2;'
                     r'[^}]*justify-self: end;[^}]*width: 100%;[^}]*min-width: 0;'
                     r'[^}]*contain: inline-size;', template)
    assert '.scoring-results-panel { position: relative; z-index: 2; overflow: visible; }' in template
    assert '.scoring-previous-filter-item-top strong { flex: 1 1 auto; min-width: 0; font-size: .83rem; white-space: normal; overflow-wrap: anywhere; }' in template


def test_job_dropdown_selected_card_tracks_selection_and_retains_job_actions():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    program = r'''
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.style = {}; }
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.text = ''; this.children = children; }
  setAttribute(key, value) { this.attributes[key] = value; }
  cloneNode() {
    const copy = new Element(this.tag);
    copy.text = this.text; copy.dataset = {...this.dataset}; copy.attributes = {...this.attributes};
    copy.children = this.children.map(child => child.cloneNode(true));
    return copy;
  }
}
const document = {createElement: tag => new Element(tag)};
const countBadge = new Element('span');
const historyCountBadge = new Element('span');
const root = {querySelectorAll: () => [countBadge, historyCountBadge]};
const previousFilterList = new Element('div'), historyList = new Element('div'), selectedPreviousFilterCard = new Element('span');
const previousFilterLists = [previousFilterList, historyList];
const previousFilters = [
  {id: '20', status: 'completed', label: 'Latest previousFilter', baseline_operator: 'EE', scoring_profile_name: 'Profile A'},
  {id: '15', status: 'processing', label: 'Earlier previousFilter', baseline_operator: 'O2', scoring_profile_name: 'Profile B'},
];
let selectedPreviousFilterId = '20';
const sortedPreviousFilters = previousFilters => previousFilters;
const previousFilterIdOf = previousFilter => previousFilter.id;
const normalizeStatus = previousFilter => previousFilter.status;
const previousFilterCardTitleSegments = previousFilter => [{dimension: 'neutral', value: previousFilter.label}];
const previousFilterCardTitle = previousFilter => previousFilter.label;
const valueOf = (previousFilter, keys, fallback) => keys.map(key => previousFilter[key]).find(value => value !== undefined) ?? fallback;
const previousFilterLevels = () => 'Operator';
const previousFilterCdrNames = () => ['Example CDR.xlsx'];
const previousFilterCdrSummary = () => 'Example CDR.xlsx';
const isActive = previousFilter => previousFilter.status === 'processing';
const progressValue = () => 40;
const deletingPreviousFilterIds = new Set();
''' + _function_source(script, 'previousFilterAreaSummaryText') + _function_source(script, 'previousFilterDurationText') + _function_source(script, 'syncPreviousFilterLists') + _function_source(script, 'renderPreviousFilters') + r'''
renderPreviousFilters();
const latest = selectedPreviousFilterCard.textContent;
const cards = previousFilterList.children.map(row => ({id: row.children[0].dataset.previousFilterId,
  selected: row.children[0].attributes['aria-current'], deleteId: row.children[1].children.at(-1).dataset.deletePreviousFilterId}));
const separateCopy = selectedPreviousFilterCard.children[0] !== previousFilterList.children[0].children[0].children[0];
const historyMatches = historyList.children.every((row, index) => {
  const original = previousFilterList.children[index];
  return row.textContent === original.textContent
    && row.children[0].dataset.previousFilterId === original.children[0].dataset.previousFilterId
    && row.children[0].attributes['aria-current'] === original.children[0].attributes['aria-current']
    && row.children[1].children.at(-1).dataset.deletePreviousFilterId === original.children[1].children.at(-1).dataset.deletePreviousFilterId;
});
const historyCounts = [countBadge.textContent, historyCountBadge.textContent];
selectedPreviousFilterId = '15';
renderPreviousFilters();
const earlier = selectedPreviousFilterCard.textContent;
previousFilters.length = 0;
renderPreviousFilters();
process.stdout.write(JSON.stringify({latest, earlier, cards, separateCopy, historyMatches, historyCounts, emptyHistory: historyList.textContent, empty: selectedPreviousFilterCard.textContent}));
'''
    result = _run_node_json(program, {})
    assert 'Latest previousFilter' in result['latest'] and 'Profile A' in result['latest']
    assert 'Earlier previousFilter' in result['earlier'] and 'Profile B' in result['earlier']
    assert 'processing' in result['earlier']
    assert 'Example CDR.xlsx' not in result['earlier']
    assert '1 CDR' in result['earlier']
    assert result['cards'] == [
        {'id': '20', 'selected': 'true', 'deleteId': '20'},
        {'id': '15', 'selected': 'false', 'deleteId': '15'},
    ]
    assert result['separateCopy'] and result['historyMatches']
    assert result['historyCounts'] == ['2 filters', '2 filters']
    assert 'No scoring has been calculated in this workspace yet' in result['emptyHistory']
    assert result['empty'] == 'No previous filters yet'


@pytest.mark.parametrize('list_index', [0, 1])
def test_choosing_job_from_either_list_loads_selected_results(list_index):
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    start = script.index("  async function previousFilterAction(event) {")
    end = script.index("\n  root.addEventListener('click',", start)
    program = r'''
let loaded, persisted = false, focused = false, deleted, restored;
const handlers = [];
const previousFilterLists = [0, 1].map(() => ({addEventListener: (_name, callback) => {handlers.push(callback);}}));
const previousFilters = [{id: '20'}, {id: '15'}];
const previousFilterIdOf = previousFilter => previousFilter.id;
let userSelectedPreviousFilter = false, selectedPreviousFilterId = '20', selectedPreviousFilter = previousFilters[0];
const root = {querySelector: () => ({scrollIntoView: () => {focused = true;}})};
const previousFilterSelector = {open: true, contains: () => LIST_INDEX === 0, querySelector: () => ({focus: () => {focused = true;}})};
const persistScoringViewState = () => {persisted = true;};
const restoreCalculationSelectionFromPreviousFilter = previousFilter => {restored = previousFilter.id;};
const loadPreviousFilter = async (previousFilter, force) => {loaded = {id: previousFilter.id, force};};
const deletePreviousFilter = id => {deleted = id;};
''' + f'\nconst LIST_INDEX = {list_index};\n' + script[start:end] + f'\nconst handler = handlers[{list_index}];\n' + r'''
(async () => {
  await handler({target: {closest: selector => selector === '[data-previous-filter-id]' ? {dataset: {previousFilterId: '15'}} : null}});
  const selection = {loaded, persisted, focused, open: previousFilterSelector.open, selectedPreviousFilterId, userSelectedPreviousFilter, restored};
  loaded = null;
  await handler({target: {closest: selector => selector === '[data-delete-previous-filter-id]' ? {dataset: {deletePreviousFilterId: '20'}} : null}});
  process.stdout.write(JSON.stringify({selection, deleted, loaded}));
})();
'''
    result = _run_node_json(program, {})
    assert result['selection'] == {
        'loaded': {'id': '15', 'force': True}, 'persisted': True, 'focused': True,
        'open': False, 'selectedPreviousFilterId': '15', 'userSelectedPreviousFilter': True, 'restored': '15',
    }
    assert result['deleted'] == '20' and result['loaded'] is None


def test_export_actions_remain_visible_and_disabled_until_results_are_available():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    for kind in ('scoring', 'gap', 'ppt'):
        assert f'data-export-{kind} aria-disabled="true" tabindex="-1"' in template
        assert f'data-export-{kind} hidden' not in template
    program = r'''
const links = ['scoring', 'gap', 'ppt'].map(() => ({hidden: true, attributes: {},
  setAttribute(key, value) {this.attributes[key] = value;}}));
// The CSV links sit above their tables; Export Report (PPT/Word) is in both toolbars.
const exportLinks = {scoring: links[0], gap: links[1], ppt: [links[2]]};
const exportBase = '/scoring/previous-filters';
const selectedTableMode = () => 'expanded';
const selectedGapLayout = () => 'end';
const selectedEnvironment = 'all';
const showGapValues = () => false;
''' + _function_source(script, 'setExportLinks') + r'''
setExportLinks('21', false);
const unavailable = links.map(link => ({hidden: link.hidden, disabled: link.attributes['aria-disabled'], tabIndex: link.tabIndex, href: link.href}));
setExportLinks('21', true);
const available = links.map(link => ({hidden: link.hidden, disabled: link.attributes['aria-disabled'], tabIndex: link.tabIndex, href: link.href}));
setExportLinks('', false);
const reset = links.map(link => link.attributes['aria-disabled']);
process.stdout.write(JSON.stringify({unavailable, available, reset}));
'''
    result = _run_node_json(program, {})
    assert all(link == {'hidden': False, 'disabled': 'true', 'tabIndex': -1, 'href': '#'}
               for link in result['unavailable'])
    assert all(link['hidden'] is False and link['disabled'] == 'false' and link['tabIndex'] == 0
               and link['href'].startswith('/scoring/previous-filters/21/export/') for link in result['available'])
    assert result['reset'] == ['true', 'true', 'true']
