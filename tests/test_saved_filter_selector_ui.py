"""Saved scoring savedFilter cards select the results shown in the embedded dropdown."""
import re

import pytest

from tests.test_scoring_results_controls import (
    SCORING_SCRIPT, SCORING_TEMPLATE, _constant_source, _function_source, _run_node_json,
)


def test_job_dropdown_is_inside_results_header_and_constrained_to_button_column():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    header = template.split('<div class="scoring-results-head">', 1)[1].split(
        '<div class="scoring-result-tabs"', 1,
    )[0]
    assert template.count('data-saved-filter-list') == 3
    # The same selector is on top of the Calculation panel, beside its title, and its list scrolls on its own.
    calculation_head = template.split('<article class="panel scoring-controls"', 1)[1].split('data-saved-filter-editing', 1)[0]
    assert 'class="scoring-start-tip"' in calculation_head and 'data-saved-filter-selector' in calculation_head
    assert 'grid-template-areas: "title meta" "tip selector";' in template
    assert 'data-selected-saved-filter-card' in calculation_head and 'data-saved-filter-list' in calculation_head
    assert '.saved-filter-picker .saved-filter-list { max-height: min(28rem,55vh); overscroll-behavior: contain; }' in template
    assert template.index('class="panel scoring-results-panel"') < template.index('class="panel saved-filters-panel"')
    assert header.index('class="scoring-results-tools"') < header.index('data-saved-filter-selector')
    assert '<summary class="saved-filter-item"' in header
    assert 'data-selected-saved-filter-card' in header and 'data-saved-filter-list' in header
    assert re.search(r'\.saved-filter-selector\s*\{[^}]*grid-column: 2;[^}]*grid-row: 2;'
                     r'[^}]*justify-self: end;[^}]*width: 100%;[^}]*min-width: 0;'
                     r'[^}]*contain: inline-size;', template)
    assert '.scoring-results-panel { position: relative; z-index: 2; overflow: visible; }' in template
    assert '.saved-filter-item-top strong { flex: 1 1 auto; min-width: 0; font-size: .83rem; white-space: normal; overflow-wrap: anywhere; }' in template


def test_job_dropdown_selected_card_tracks_selection_and_retains_job_actions():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    program = r'''
class Element {
  constructor(tag) {
    this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; this.style = {}; this.className = '';
    const element = this;
    this.classList = {
      contains: name => element.className.split(' ').includes(name),
      add: name => { if (!element.className.split(' ').includes(name)) element.className = `${element.className} ${name}`.trim(); },
      toggle: (name, force) => {
        const names = element.className.split(' ').filter(item => item && item !== name);
        element.className = [...names, ...(force ? [name] : [])].join(' ');
      },
    };
  }
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return (this.text || '') + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.text = ''; this.children = children; }
  get childNodes() { return this.children; }
  get childElementCount() { return this.children.filter(child => typeof child !== 'string').length; }
  setAttribute(key, value) { this.attributes[key] = value; }
  querySelectorAll(selector) {
    const name = selector.slice(1);
    return this.children.flatMap(child => (typeof child === 'string' ? [] : [
      ...(child.classList.contains(name) ? [child] : []), ...child.querySelectorAll(selector)]));
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  cloneNode() {
    const copy = new Element(this.tag);
    copy.text = this.text; copy.dataset = {...this.dataset}; copy.attributes = {...this.attributes}; copy.className = this.className;
    copy.children = this.children.map(child => (typeof child === 'string' ? child : child.cloneNode(true)));
    return copy;
  }
}
const document = {createElement: tag => new Element(tag)};
const countBadge = new Element('span');
const historyCountBadge = new Element('span');
const root = {querySelectorAll: () => [countBadge, historyCountBadge]};
const savedFilterList = new Element('div'), historyList = new Element('div'), selectedSavedFilterCard = new Element('span');
// The selected card of the selector of the Calculation panel, a copy of the first one.
const otherSelectedCard = new Element('span');
const selectedSavedFilterCards = [selectedSavedFilterCard, otherSelectedCard];
const savedFilterLists = [savedFilterList, historyList];
const savedFilters = [
  {id: '20', status: 'completed', label: 'Latest savedFilter', baseline_operator: 'EE', scoring_profile_name: 'Profile A', pinned: true, position: 1,
    scope: {dimension: 'city', text: 'London', title: 'City: London'}},
  {id: '15', status: 'processing', label: 'Earlier savedFilter', baseline_operator: 'O2', scoring_profile_name: 'Profile B', pinned: true, position: 2,
    nr_mode: 'NSA+SA'},
];
let draggedSavedFilterRow = null, savedFiltersRenderPending = false;
const savedFilterPanelList = null, canReorderSavedFilters = false;
let selectedSavedFilterId = '20';
const sortedSavedFilters = savedFilters => savedFilters;
const savedFilterIdOf = savedFilter => savedFilter.id;
const normalizeStatus = savedFilter => savedFilter.status;
const savedFilterCardTitleSegments = savedFilter => [{dimension: 'neutral', value: savedFilter.label}];
const savedFilterCardTitle = savedFilter => savedFilter.label;
const savedFilterScope = savedFilter => savedFilter.scope || null;
const valueOf = (savedFilter, keys, fallback) => keys.map(key => savedFilter[key]).find(value => value !== undefined) ?? fallback;
const savedFilterLevels = () => 'Operator';
const savedFilterCdrNames = () => ['Example CDR.xlsx'];
const savedFilterCdrSummary = () => 'Example CDR.xlsx';
const isActive = savedFilter => savedFilter.status === 'processing';
const progressValue = () => 40;
const deletingSavedFilterIds = new Set();
const syncSavedFiltersBulk = () => {};
let selectionUnmatched = false, scoringClosed = false;
const closeScoringButton = {disabled: true};
const unfoldedSavedFilters = new Map();
let selectedSavedFilterUnfolded = false;
''' + _function_source(script, 'unfoldedSavedFilterIds') + _function_source(script, 'savedFilterTrendCampaigns') + _function_source(script, 'savedFilterAreaSummaryParts') + _function_source(script, 'savedFilterTimeSplit') + _function_source(script, 'savedFilterDurationText') + _function_source(script, 'syncSavedFilterLists') + _function_source(script, 'renderSavedFilters') + _function_source(script, 'unmatchedSelectionNotice') + r'''
renderSavedFilters();
const latest = selectedSavedFilterCard.textContent;
const copied = [otherSelectedCard.textContent === latest, otherSelectedCard.classList.contains('is-folded'),
  otherSelectedCard.children[0] !== selectedSavedFilterCard.children[0]];
// Close Scoring closes the Saved Filter shown.
const closeEnabled = !closeScoringButton.disabled;
const cardOf = row => row.children.find(child => child.dataset.savedFilterId);
const useOf = row => row.children.find(child => child.className.split(' ').includes('saved-filter-use'));
const deleteOf = row => row.children.find(child => child.className === 'saved-filter-actions').children.at(-1);
const tabsOf = row => row.children.find(child => child.className === 'saved-filter-tabs');
const scopeOf = row => tabsOf(row)?.children.find(child => child.className === 'saved-filter-scope');
const modeOf = row => tabsOf(row)?.children.find(child => child.className === 'saved-filter-mode');
// Each card is folded, with its name (its ID without one) and Use Filter on its right (In Use on the one in use), and the
// label of the only field it filters on top of it, before the card.
const cards = savedFilterList.children.map(row => ({id: cardOf(row).dataset.savedFilterId,
  selected: cardOf(row).attributes['aria-current'], expanded: cardOf(row).attributes['aria-expanded'],
  name: cardOf(row).children[0].textContent, use: useOf(row).dataset.savedFilterUse ?? null, useLabel: useOf(row).textContent,
  deleteId: deleteOf(row).dataset.deleteSavedFilterId,
  scope: scopeOf(row) ? [scopeOf(row).dataset.dimension, scopeOf(row).textContent, scopeOf(row).title, row.children.indexOf(tabsOf(row)),
    row.classList.contains('has-scope')] : null,
  mode: modeOf(row) ? [modeOf(row).dataset.nrMode, modeOf(row).textContent, modeOf(row).title] : null}));
const separateCopy = selectedSavedFilterCard.children[0] !== cardOf(savedFilterList.children[0]).children[0];
// The selected card has no fold arrow, and no name when the Saved Filter has none.
const selectedHasHead = selectedSavedFilterCard.children.some(child => child.className === 'saved-filter-head');
const selectedScope = selectedSavedFilterCard.children.some(child => child.className === 'saved-filter-tabs');
// The selected card is folded, with Details first among its buttons.
const selectedFolded = [selectedSavedFilterCard.classList.contains('is-folded'),
  selectedSavedFilterCard.children.at(-1).children[0].dataset.savedFilterDetails,
  selectedSavedFilterCard.children.at(-1).children[0].attributes['aria-expanded']];
const historyMatches = historyList.children.every((row, index) => {
  const original = savedFilterList.children[index];
  return row.textContent === original.textContent
    && cardOf(row).dataset.savedFilterId === cardOf(original).dataset.savedFilterId
    && cardOf(row).attributes['aria-current'] === cardOf(original).attributes['aria-current']
    && useOf(row).dataset.savedFilterUse === useOf(original).dataset.savedFilterUse
    && deleteOf(row).dataset.deleteSavedFilterId === deleteOf(original).dataset.deleteSavedFilterId
    && scopeOf(row)?.textContent === scopeOf(original)?.textContent;
});
// A card unfolded in one list stays unfolded there when the lists are drawn again, and folded in the other.
unfoldedSavedFilterIds(historyList).add('15');
renderSavedFilters();
const unfolded = [savedFilterList, historyList].map(list => list.children.map(row => [
  row.classList.contains('is-expanded'), cardOf(row).attributes['aria-expanded']]));
unfoldedSavedFilterIds(historyList).clear();
const historyCounts = [countBadge.textContent, historyCountBadge.textContent];
selectedSavedFilterId = '15';
renderSavedFilters();
const earlier = selectedSavedFilterCard.textContent;
// In Use follows the Saved Filter in use.
const earlierUse = savedFilterList.children.map(row => useOf(row).textContent);
// Unstarred, the opened Saved Filter leaves the lists but stays in the selected card.
savedFilters[1].pinned = false;
renderSavedFilters();
const unstarred = {listed: savedFilterList.children.map(row => cardOf(row).dataset.savedFilterId),
  card: selectedSavedFilterCard.textContent, counts: [countBadge.textContent, historyCountBadge.textContent]};
// A selection that is no Saved Filter: the card asks to choose a Favourites Filter or to calculate it.
selectionUnmatched = true;
renderSavedFilters();
const unmatchedCard = selectedSavedFilterCard.textContent;
const unmatchedFolded = selectedSavedFilterCard.classList.contains('is-folded');
selectionUnmatched = false;
// Closed, no scoring is open: the card says so and Close Scoring is disabled.
scoringClosed = true;
renderSavedFilters();
const closed = {card: selectedSavedFilterCard.textContent, closeDisabled: closeScoringButton.disabled};
scoringClosed = false;
savedFilters.length = 0;
renderSavedFilters();
process.stdout.write(JSON.stringify({latest, copied, earlier, earlierUse, cards, separateCopy, selectedHasHead, selectedScope, selectedFolded, historyMatches, unfolded, historyCounts,
  unstarred, unmatchedCard, unmatchedFolded, closeEnabled, closed, emptyHistory: historyList.textContent, empty: selectedSavedFilterCard.textContent}));
'''
    result = _run_node_json(program, {})
    assert 'Latest savedFilter' in result['latest'] and 'Profile A' in result['latest']
    assert result['copied'] == [True, True, True]
    assert 'Earlier savedFilter' in result['earlier'] and 'Profile B' in result['earlier']
    assert 'processing' in result['earlier']
    assert 'Example CDR.xlsx' not in result['earlier']
    assert '1 CDR' in result['earlier']
    assert result['cards'] == [
        {'id': '20', 'selected': 'true', 'expanded': 'false', 'name': 'Filter ID: 20', 'use': None, 'useLabel': 'In Use',
         'deleteId': '20', 'scope': ['city', 'London', 'City: London', 0, True], 'mode': None},
        {'id': '15', 'selected': 'false', 'expanded': 'false', 'name': 'Filter ID: 15', 'use': '15', 'useLabel': 'Use Filter',
         'deleteId': '15', 'scope': None, 'mode': ['nsa-vs-sa', 'NSA vs SA', 'NR Mode: NSA vs SA']},
    ]
    assert result['earlierUse'] == ['Use Filter', 'In Use']
    # The label is on top of the selected card too.
    assert result['selectedScope'] is True
    assert result['separateCopy'] and result['historyMatches'] and not result['selectedHasHead']
    assert result['selectedFolded'] == [True, '20', 'false'] and result['unmatchedFolded'] is False
    assert 'Filter ID: 20Latest' not in result['latest']
    assert result['unfolded'] == [[[False, 'false'], [False, 'false']], [[False, 'false'], [True, 'true']]]
    assert result['historyCounts'] == ['2 Favourites Filters', '2 Favourites Filters']
    assert result['unstarred']['listed'] == ['20'] and 'Earlier savedFilter' in result['unstarred']['card']
    assert result['unstarred']['counts'] == ['1 Favourites Filter', '1 Favourites Filter']
    assert "No Saved Filter matches the Calculation panel's filters" in result['unmatchedCard']
    assert 'Calculate Scoring' in result['unmatchedCard'] and 'Earlier savedFilter' not in result['unmatchedCard']
    assert result['closeEnabled'] is True
    assert result['closed']['card'].startswith('No scoring is open') and result['closed']['closeDisabled'] is True
    assert 'No Favourites Filters yet' in result['emptyHistory']
    assert result['empty'] == 'No Saved Filters yet'


def test_card_label_names_the_only_field_a_saved_filter_filters():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    snippets = [
        _constant_source(script, 'valueOf'),
        _function_source(script, 'uniqueCatalogueValues'),
        _function_source(script, 'scoringVendorName'),
        _function_source(script, 'firstValue'),
        _function_source(script, 'savedSavedFilterValues'),
        _function_source(script, 'savedFilterScope'),
    ]
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {operatorGroups: [], catalogueKeyByLevel: new Map([['Region', 'regions']]),
  datasetCatalogues: new Map([['1', {regions: ['Vendor A', 'Vendor B']}]])};
vm.createContext(context);
vm.runInContext(payload.snippets.join('\n') + `
  const empty = {Region: [], Cluster: [], City: [], Operator: [], Vendor: [], Campaign: ['@latest-campaign']};
  globalThis.scopes = [
    savedFilterScope({context_filters: empty}),
    savedFilterScope({context_filters: {...empty, City: ['London']}}),
    savedFilterScope({context_filters: {...empty, Region: ['Vendor A']}}),
    savedFilterScope({context_filters: {...empty, City: ['Leeds', 'London']}}),
    savedFilterScope({context_filters: {...empty, Region: ['Vendor A'], City: ['London']}}),
    // Every Region of its CDRs is no filter.
    savedFilterScope({dataset_ids: [1], context_filters: {...empty, Region: ['Vendor A', 'Vendor B']}}),
  ];`, context);
process.stdout.write(JSON.stringify(context.scopes));
"""
    scopes = _run_node_json(program, {'snippets': snippets})
    assert [scope and [scope['dimension'], scope['text']] for scope in scopes] == [
        ['all', 'All'], ['city', 'London'], ['region', 'Vendor A'], ['city', 'Leeds, London'], None, ['all', 'All'],
    ]
    assert scopes[2]['title'] == 'Region: Vendor A'
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    for dimension in ('all', 'region', 'cluster', 'city', 'operator', 'vendor'):
        assert f'.saved-filter-scope[data-dimension="{dimension}"]' in template
    # The selected card folds and unfolds with Details, without opening the dropdown.
    assert "const details = event.target.closest('[data-saved-filter-details]');" in script
    assert '.selected-saved-filter.is-folded > :not(.saved-filter-tabs):not(.saved-filter-name):not(.saved-filter-item-top):not(.saved-filter-actions)' in template
    # Beside it, the NR Mode of the Saved Filter as an outlined tab.
    assert '.saved-filter-mode[data-nr-mode="sa"] { border-color: #be185d; color: #be185d; }' in template


@pytest.mark.parametrize('list_index', [0, 1])
def test_choosing_job_from_either_list_loads_selected_results(list_index):
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    start = script.index("  async function savedFilterAction(event) {")
    end = script.index("\n  root.addEventListener('click',", start)
    program = r'''
let loaded, persisted = false, focused = false, deleted, restored;
const handlers = [];
const savedFilterLists = [0, 1].map(() => ({addEventListener: (_name, callback) => {handlers.push(callback);}}));
const savedFilters = [{id: '20'}, {id: '15'}];
const savedFilterIdOf = savedFilter => savedFilter.id;
let userSelectedSavedFilter = false, selectedSavedFilterId = '20', selectedSavedFilter = savedFilters[0];
const root = {querySelector: () => ({scrollIntoView: () => {focused = true;}})};
const savedFilterSelector = {open: true, contains: () => LIST_INDEX === 0, querySelector: () => ({focus: () => {focused = true;}})};
const savedFilterSelectors = [{open: true, contains: () => false}, savedFilterSelector];
const persistScoringViewState = () => {persisted = true;};
const restoreCalculationSelectionFromSavedFilter = savedFilter => {restored = savedFilter.id;};
let unmatched = true, reopened = false;
const showUnmatchedSelection = value => {unmatched = value;};
const reopenScoring = () => {reopened = true;};
let editingSavedFilter = null;
const stopSavedFilterEdit = () => { editingSavedFilter = null; };
const loadSavedFilter = async (savedFilter, force) => {loaded = {id: savedFilter.id, force};};
const deleteSavedFilter = id => {deleted = id;};
const savedFiltersUrl = '/api/scoring/saved-filters';
const used = [];
const requestJson = (url, options) => { used.push([url, options.method]); return Promise.resolve({}); };
let refreshed = 0;
const refreshSavedFilters = async () => { refreshed += 1; };
const unfoldedSavedFilters = new Map();
''' + _function_source(script, 'unfoldedSavedFilterIds') + f'\nconst LIST_INDEX = {list_index};\n' + script[start:end] + f'\nconst handler = handlers[{list_index}];\n' + r'''
(async () => {
  // A click on the card folds or unfolds it, without opening it.
  const row = {classes: new Set(), classList: {toggle(name, force) { if (force) row.classes.add(name); else row.classes.delete(name); }}};
  const card = {dataset: {savedFilterId: '15'}, attributes: {}, closest: () => row, setAttribute(key, value) { card.attributes[key] = value; }};
  const cardClick = {target: {closest: selector => (selector === '[data-saved-filter-id]' ? card : null)}};
  await handler(cardClick);
  const unfoldedOnce = [row.classes.has('is-expanded'), card.attributes['aria-expanded'], loaded === undefined];
  await handler(cardClick);
  const foldedAgain = [row.classes.has('is-expanded'), card.attributes['aria-expanded']];
  // Use Filter opens it.
  await handler({target: {closest: selector => selector === '[data-saved-filter-use]' ? {dataset: {savedFilterUse: '15'}} : null}});
  const selection = {loaded, persisted, focused, open: savedFilterSelectors.some(selector => selector.open), selectedSavedFilterId, userSelectedSavedFilter, restored,
    unmatched, reopened};
  loaded = null;
  await handler({target: {closest: selector => selector === '[data-delete-saved-filter-id]' ? {dataset: {deleteSavedFilterId: '20'}} : null}});
  await new Promise(resolve => setTimeout(resolve));
  process.stdout.write(JSON.stringify({unfoldedOnce, foldedAgain, selection, deleted, loaded, used, refreshed}));
})();
'''
    result = _run_node_json(program, {})
    assert result['unfoldedOnce'] == [True, 'true', True] and result['foldedAgain'] == [False, 'false']
    assert result['selection'] == {
        'loaded': {'id': '15', 'force': True}, 'persisted': True, 'focused': True,
        'open': False, 'selectedSavedFilterId': '15', 'userSelectedSavedFilter': True, 'restored': '15',
        # Opened, its selection is a Saved Filter again: its card and results show, also after Close Scoring.
        'unmatched': False, 'reopened': True,
    }
    assert result['deleted'] == '20' and result['loaded'] is None
    # Opening it with Use Filter counts as a use.
    assert result['used'] == [['/api/scoring/saved-filters/15/use', 'POST']] and result['refreshed'] == 1


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
const exportBase = '/scoring/saved-filters';
const selectedTableMode = () => 'expanded';
const selectedGapLayout = () => 'end';
const selectedEnvironment = 'all';
const showGapValues = () => false;
let selectionUnmatched = false;
''' + _function_source(script, 'setExportLinks') + r'''
setExportLinks('21', false);
const unavailable = links.map(link => ({hidden: link.hidden, disabled: link.attributes['aria-disabled'], tabIndex: link.tabIndex, href: link.href}));
setExportLinks('21', true);
const available = links.map(link => ({hidden: link.hidden, disabled: link.attributes['aria-disabled'], tabIndex: link.tabIndex, href: link.href}));
setExportLinks('', false);
const reset = links.map(link => link.attributes['aria-disabled']);
// The results hidden by a selection that is no Saved Filter are not exported either.
selectionUnmatched = true;
setExportLinks('21', true);
const unmatched = links.map(link => link.attributes['aria-disabled']);
process.stdout.write(JSON.stringify({unavailable, available, reset, unmatched}));
'''
    result = _run_node_json(program, {})
    assert all(link == {'hidden': False, 'disabled': 'true', 'tabIndex': -1, 'href': '#'}
               for link in result['unavailable'])
    assert all(link['hidden'] is False and link['disabled'] == 'false' and link['tabIndex'] == 0
               and link['href'].startswith('/scoring/saved-filters/21/export/') for link in result['available'])
    assert result['reset'] == ['true', 'true', 'true']
    assert result['unmatched'] == ['true', 'true', 'true']


def test_reload_opens_scoring_dimmed_at_the_saved_position_until_it_is_drawn():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    # Before the page is drawn, with the same key as scoring.js: the page dimmed under a gradient with a notice.
    early = template.split('{% block content %}', 1)[1].split('<style>', 1)[0]
    assert "'drivetest-analyzer', 'scoring-view'" in early and "window.history.scrollRestoration = 'manual';" in early
    assert "'drivetest-analyzer', 'scoring-view',\n    encodeURIComponent(document.body.dataset.authenticatedUser || 'anonymous')," in script
    assert "overlay.className = 'scoring-restore-overlay';" in early
    # Opened at the saved position, as tall as it needs, until the content reaches it.
    assert 'document.documentElement.style.minHeight = `${top + window.innerHeight}px`;' in early and 'window.scrollTo(0, top);' in early
    assert "notice.textContent = 'Loading Scoring & GAP Analysis where you left it…';" in early
    assert '.scoring-restore-overlay { position: fixed; inset: 0;' in template
    assert 'linear-gradient(' in template.split('.scoring-restore-overlay::before {', 1)[1].split('}', 1)[0]
    # It goes once the page is at the position (or the user takes over), and at the end of the restoration.
    restore = script.split('  function restoreScoringViewScroll() {', 1)[1].split('\n  }\n', 1)[0]
    assert "if (maximum >= target || interacted) document.querySelector('[data-scoring-restore-notice]')?.remove();" in restore
    assert 'const pageHeight = document.body.scrollHeight;' in restore and "document.documentElement.style.minHeight = '';" in restore
    # Only a reload (or Back and Forward) returns there: opening the module starts at its top.
    assert "if (window.location.hash || !['reload', 'back_forward'].includes(navigation)) return;" in early
    assert "&& ['reload', 'back_forward'].includes(window.performance.getEntriesByType?.('navigation')?.[0]?.type);" in script
    # What was in view when the page was left shows as it was, in a frame without scripts, under the gradient.
    assert "window.sessionStorage.getItem(`${key}:snapshot`)" in early and "frame.setAttribute('sandbox', 'allow-same-origin');" in early
    assert 'frame.contentWindow.scrollTo(0, snapshot.scroll_y);' in early
    capture = script.split('  function scoringPageSnapshot() {', 1)[1].split("\n  window.addEventListener('pagehide'", 1)[0]
    assert "['SCRIPT', 'NOSCRIPT', 'TEMPLATE', 'IFRAME'].includes(tag)" in capture and 'if (box.bottom < 0 || box.top > viewportHeight) {' in capture
    assert "window.sessionStorage.setItem(key, JSON.stringify({scroll_y: Math.round(window.scrollY), width: window.innerWidth, html}));" in script
    assert '.scoring-restore-notice { position: relative; z-index: 2;' in template and 'border-left: 5px solid #226849;' in template


def test_result_tabs_stay_at_the_top_while_the_results_are_scrolled():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    # Under the bar of the sections, within the results only; held there, drawn on the colour of the panel.
    assert '.scoring-result-tabs { position: sticky; top: calc(var(--module-tabs-offset, 0px) + var(--section-top-offset, 0px)); z-index: 6; }' in template
    assert '.scoring-result-tabs.is-stuck::before {' in template
    assert "bar.classList.toggle('is-stuck', box.height > 0 && start < top - 1 && box.top <= top + 1);" in script
    # A tab chosen while the results are scrolled opens at its start.
    assert 'if (start < top) window.scrollBy({top: start - top, behavior: \'auto\'});' in script
    # The button that downloads a chart as an image stays below it, in light blue.
    assert 'tabs?.height ? tabs.bottom + 3 : 0);' in script
    assert 'background: #e3f0fc; color: #1f5f9e;' in template.split('.scoring-image-download {', 1)[1].split('}', 1)[0]
    # The one of the whole card in a more intense blue.
    assert '.scoring-image-download[data-image-level="card"] { border-color: #1f6fc0; background: #2f86dc; color: #fff; }' in template


def test_cdrs_used_show_four_cdrs_of_each_type_before_they_scroll():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    # Measured on the fourth CDR shown (whatever lines its name takes), whenever they are drawn again or the panel changes
    # width; four or fewer, as tall as they are.
    assert 'function fitAutoCdrLists() {' in script
    assert "const bottom = items[3].getBoundingClientRect().bottom - list.getBoundingClientRect().top + list.scrollTop;" in script
    assert "list.style.maxHeight = 'none';" in script
    assert 'new MutationObserver(fitAutoCdrLists).observe(autoCdrGroups, {childList: true, subtree: true});' in script


def test_move_up_and_down_move_the_checked_favourites_filters_one_place():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    bulk = template.split('data-saved-filters-bulk', 1)[1].split('</div>', 1)[0]
    # Move Up and Move Down come before Use newer CDRs.
    assert bulk.index('data-saved-filters-move="up"') < bulk.index('data-saved-filters-move="down"') \
        < bulk.index('data-saved-filters-use-newer')
    # The bar stays at the top while the panel is scrolled, and the moved cards light up where they land.
    assert '.saved-filters-bulk { position: sticky; top: calc(var(--module-tabs-offset, 0px) + var(--section-top-offset, 0px));' in template
    assert '.saved-filters-panel .saved-filter-row.is-moved .saved-filter-item { animation: saved-filter-moved' in template
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    assert "root.querySelector('[data-saved-filters-bulk]')].filter(Boolean);" in script
    assert "rows.forEach(row => row.classList.add('is-moved'));" in script
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {checkedSavedFilterIds: new Set()};
vm.createContext(context);
vm.runInContext(payload.snippets.join('\n') + `
  const order = ['1', '2', '3', '4', '5'];
  const move = (checked, step) => { checkedSavedFilterIds.clear(); checked.forEach(id => checkedSavedFilterIds.add(id)); return movedSavedFilterOrder(order, step); };
  globalThis.orders = [
    move(['3'], -1), move(['3'], 1), move(['2', '3'], -1), move(['1', '3'], -1), move(['5'], 1), move(['2', '4'], 1),
  ];`, context);
process.stdout.write(JSON.stringify(context.orders));
"""
    orders = _run_node_json(program, {'snippets': [_function_source(script, 'movedSavedFilterOrder')]})
    assert orders == [
        ['1', '3', '2', '4', '5'], ['1', '2', '4', '3', '5'], ['2', '3', '1', '4', '5'],
        # The first one cannot go up and the last one cannot go down; the others still move.
        ['1', '3', '2', '4', '5'], ['1', '2', '3', '4', '5'], ['1', '3', '2', '5', '4'],
    ]
