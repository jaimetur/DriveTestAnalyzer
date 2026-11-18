"""Saved scoring savedScoring cards select the results shown in the embedded dropdown."""
import re

import pytest

from tests.scoring.test_scoring_results_controls import (
    SCORING_SCRIPT, SCORING_TEMPLATE, _constant_source, _function_source, _run_node_json,
)


def test_job_dropdown_is_inside_results_header_and_constrained_to_button_column():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    header = template.split('<div class="scoring-results-head">', 1)[1].split(
        '<div class="scoring-result-tabs"', 1,
    )[0]
    # One selector, in the strip of Scoring & GAP Analysis (Showing), plus the list of the Favourite Scorings panel.
    assert template.count('data-saved-scoring-list') == 2
    assert template.count('data-saved-scoring-selector>') == 1
    strip = header.split('data-scoring-config-strip', 1)[1].split('data-scoring-config-pills', 1)[0]
    assert 'Showing' in strip and 'data-saved-scoring-selector' in strip
    assert 'data-selected-saved-scoring-card' in strip and 'data-saved-scoring-list' in strip
    assert '.saved-scoring-picker .saved-scoring-list { max-height: min(28rem,55vh); overscroll-behavior: contain; }' in template
    assert template.index('class="panel scoring-results-panel"') < template.index('class="panel collapsible-panel saved-scorings-panel"')
    # The two main buttons come first, the strip next and the view and reports after it.
    assert header.index('data-scoring-main-favourites') < header.index('data-saved-scoring-selector') < header.index('class="scoring-results-tools"')
    assert '<summary class="saved-scoring-item"' in header
    assert re.search(r'\.saved-scoring-selector\s*\{[^}]*grid-column: 2;[^}]*grid-row: 2;'
                     r'[^}]*justify-self: end;[^}]*width: 100%;[^}]*min-width: 0;'
                     r'[^}]*contain: inline-size;', template)
    assert '.scoring-strip-top .saved-scoring-selector { grid-column: auto; grid-row: auto; justify-self: auto; flex: 1 1 26rem; width: auto; }' in template
    assert '.scoring-results-panel { position: relative; z-index: 2; overflow: visible; }' in template
    assert '.saved-scoring-item-top strong { flex: 1 1 auto; min-width: 0; font-size: .83rem; white-space: normal; overflow-wrap: anywhere; }' in template


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
// Without app.js every user deletes the Saved Scorings (the server still checks it).
const window = {};
const countBadge = new Element('span');
const historyCountBadge = new Element('span');
const root = {querySelectorAll: () => [countBadge, historyCountBadge]};
const savedScoringList = new Element('div'), historyList = new Element('div'), selectedSavedScoringCard = new Element('span');
// The selected card of the selector of the Calculation panel, a copy of the first one.
const otherSelectedCard = new Element('span');
const selectedSavedScoringCards = [selectedSavedScoringCard, otherSelectedCard];
const savedScoringLists = [savedScoringList, historyList];
const savedScorings = [
  {id: '20', status: 'completed', label: 'Latest savedScoring', baseline_operator: 'EE', scoring_profile_name: 'Profile A', pinned: true, position: 1,
    scope: {dimension: 'city', text: 'London', title: 'City: London'}},
  {id: '15', status: 'processing', label: 'Earlier savedScoring', baseline_operator: 'O2', scoring_profile_name: 'Profile B', pinned: true, position: 2,
    nr_mode: 'NSA+SA'},
];
let draggedSavedScoringRow = null, savedScoringsRenderPending = false;
const savedScoringPanelList = null, canReorderSavedScorings = false;
let selectedSavedScoringId = '20';
const sortedSavedScorings = savedScorings => savedScorings;
const savedScoringIdOf = savedScoring => savedScoring.id;
const normalizeStatus = savedScoring => savedScoring.status;
const savedScoringCardTitleSegments = savedScoring => [{dimension: 'neutral', value: savedScoring.label}];
const savedScoringCardTitle = savedScoring => savedScoring.label;
const savedScoringScopes = savedScoring => (savedScoring.scope ? [savedScoring.scope] : []);
const valueOf = (savedScoring, keys, fallback) => keys.map(key => savedScoring[key]).find(value => value !== undefined) ?? fallback;
const savedScoringLevels = () => 'Operator';
const savedScoringCdrNames = () => ['Example CDR.xlsx'];
const savedScoringCdrSummary = () => 'Example CDR.xlsx';
const isActive = savedScoring => savedScoring.status === 'processing';
const progressValue = () => 40;
const deletingSavedScoringIds = new Set();
const syncSavedScoringsBulk = () => {};
let selectionUnmatched = false;
// No Filter Navigator is open.
const navigatorDialog = null;
const unfoldedSavedScorings = new Map();
let selectedSavedScoringUnfolded = false;
''' + _function_source(script, 'unfoldedSavedScoringIds') + _function_source(script, 'savedScoringTrendCampaigns') + _function_source(script, 'savedScoringAreaSummaryParts') + _function_source(script, 'savedScoringTimeSplit') + _function_source(script, 'savedScoringDurationText') + _function_source(script, 'syncSavedScoringLists') + _function_source(script, 'renderSavedScorings') + _function_source(script, 'unmatchedSelectionNotice') + r'''
renderSavedScorings();
const latest = selectedSavedScoringCard.textContent;
const copied = [otherSelectedCard.textContent === latest, otherSelectedCard.classList.contains('is-folded'),
  otherSelectedCard.children[0] !== selectedSavedScoringCard.children[0]];
const cardOf = row => row.children.find(child => child.dataset.savedScoringId);
const useOf = row => row.children.find(child => child.className.split(' ').includes('saved-scoring-use'));
const deleteOf = row => row.children.find(child => child.className === 'saved-scoring-actions').children.at(-1);
const tabsOf = row => row.children.find(child => child.className === 'saved-scoring-tabs');
const scopeOf = row => tabsOf(row)?.children.find(child => child.className === 'saved-scoring-scope');
const modeOf = row => tabsOf(row)?.children.find(child => child.className === 'saved-scoring-mode');
// Each card is folded, with its name (its ID without one) and Use Filter on its right (In Use on the one in use), and the
// label of the only field it filters on top of it, before the card.
const cards = savedScoringList.children.map(row => ({id: cardOf(row).dataset.savedScoringId,
  selected: cardOf(row).attributes['aria-current'], expanded: cardOf(row).attributes['aria-expanded'],
  name: cardOf(row).children[0].textContent, use: useOf(row).dataset.savedScoringUse ?? null, useLabel: useOf(row).textContent,
  deleteId: deleteOf(row).dataset.deleteSavedScoringId,
  scope: scopeOf(row) ? [scopeOf(row).dataset.dimension, scopeOf(row).textContent, scopeOf(row).title, row.children.indexOf(tabsOf(row)),
    row.classList.contains('has-scope')] : null,
  mode: modeOf(row) ? [modeOf(row).dataset.nrMode, modeOf(row).textContent, modeOf(row).title] : null}));
const separateCopy = selectedSavedScoringCard.children[0] !== cardOf(savedScoringList.children[0]).children[0];
// The selected card has no fold arrow, and no name when the Saved Scoring has none.
const selectedHasHead = selectedSavedScoringCard.children.some(child => child.className === 'saved-scoring-head');
const selectedScope = selectedSavedScoringCard.children.some(child => child.className === 'saved-scoring-tabs');
// The selected card is folded, with Details first among its buttons.
const selectedFolded = [selectedSavedScoringCard.classList.contains('is-folded'),
  selectedSavedScoringCard.children.at(-1).children[0].dataset.savedScoringDetails,
  selectedSavedScoringCard.children.at(-1).children[0].attributes['aria-expanded']];
const historyMatches = historyList.children.every((row, index) => {
  const original = savedScoringList.children[index];
  return row.textContent === original.textContent
    && cardOf(row).dataset.savedScoringId === cardOf(original).dataset.savedScoringId
    && cardOf(row).attributes['aria-current'] === cardOf(original).attributes['aria-current']
    && useOf(row).dataset.savedScoringUse === useOf(original).dataset.savedScoringUse
    && deleteOf(row).dataset.deleteSavedScoringId === deleteOf(original).dataset.deleteSavedScoringId
    && scopeOf(row)?.textContent === scopeOf(original)?.textContent;
});
// A card unfolded in one list stays unfolded there when the lists are drawn again, and folded in the other.
unfoldedSavedScoringIds(historyList).add('15');
renderSavedScorings();
const unfolded = [savedScoringList, historyList].map(list => list.children.map(row => [
  row.classList.contains('is-expanded'), cardOf(row).attributes['aria-expanded']]));
unfoldedSavedScoringIds(historyList).clear();
const historyCounts = [countBadge.textContent, historyCountBadge.textContent];
selectedSavedScoringId = '15';
renderSavedScorings();
const earlier = selectedSavedScoringCard.textContent;
// In Use follows the Saved Scoring in use.
const earlierUse = savedScoringList.children.map(row => useOf(row).textContent);
// Unstarred, the opened Saved Scoring leaves the lists but stays in the selected card.
savedScorings[1].pinned = false;
renderSavedScorings();
const unstarred = {listed: savedScoringList.children.map(row => cardOf(row).dataset.savedScoringId),
  card: selectedSavedScoringCard.textContent, counts: [countBadge.textContent, historyCountBadge.textContent]};
// A selection that is no Saved Scoring: the card asks to choose a Favourite Scoring or to calculate it.
selectionUnmatched = true;
renderSavedScorings();
const unmatchedCard = selectedSavedScoringCard.textContent;
const unmatchedFolded = selectedSavedScoringCard.classList.contains('is-folded');
selectionUnmatched = false;
savedScorings.length = 0;
renderSavedScorings();
process.stdout.write(JSON.stringify({latest, copied, earlier, earlierUse, cards, separateCopy, selectedHasHead, selectedScope, selectedFolded, historyMatches, unfolded, historyCounts,
  unstarred, unmatchedCard, unmatchedFolded, emptyHistory: historyList.textContent, empty: selectedSavedScoringCard.textContent}));
'''
    result = _run_node_json(program, {})
    assert 'Latest savedScoring' in result['latest'] and 'Profile A' in result['latest']
    assert result['copied'] == [True, True, True]
    assert 'Earlier savedScoring' in result['earlier'] and 'Profile B' in result['earlier']
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
    assert result['historyCounts'] == ['2 Favourite Scorings', '2 Favourite Scorings']
    assert result['unstarred']['listed'] == ['20'] and 'Earlier savedScoring' in result['unstarred']['card']
    assert result['unstarred']['counts'] == ['1 Favourite Scoring', '1 Favourite Scoring']
    assert 'No Saved Scoring matches the configuration' in result['unmatchedCard']
    assert 'Calculate Scoring' in result['unmatchedCard'] and 'Earlier savedScoring' not in result['unmatchedCard']
    assert 'No Favourite Scorings yet' in result['emptyHistory']
    assert result['empty'] == 'No Saved Scorings yet'


def test_card_label_names_the_only_field_a_saved_scoring_filters():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    snippets = [
        _constant_source(script, 'valueOf'),
        _function_source(script, 'uniqueCatalogueValues'),
        _function_source(script, 'scoringVendorName'),
        _function_source(script, 'firstValue'),
        _function_source(script, 'savedSavedScoringValues'),
        _function_source(script, 'savedScoringScopes'),
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
    savedScoringScopes({context_filters: empty}),
    savedScoringScopes({context_filters: {...empty, City: ['London']}}),
    savedScoringScopes({context_filters: {...empty, Region: ['Vendor A']}}),
    savedScoringScopes({context_filters: {...empty, City: ['Leeds', 'London']}}),
    savedScoringScopes({context_filters: {...empty, Region: ['Vendor A'], City: ['London']}}),
    // Every Region of its CDRs is no filter.
    savedScoringScopes({dataset_ids: [1], context_filters: {...empty, Region: ['Vendor A', 'Vendor B']}}),
    // The operators or vendors after the areas (Nationwide without them).
    savedScoringScopes({context_filters: {...empty, Operator: ['-Three']}}),
    savedScoringScopes({context_filters: {...empty, Operator: ['-Three'], City: ['London']}}),
  ];`, context);
process.stdout.write(JSON.stringify(context.scopes));
"""
    scopes = _run_node_json(program, {'snippets': snippets})
    assert [[[scope['dimension'], scope['text']] for scope in labels] for labels in scopes] == [
        [['all', 'Nationwide']], [['city', 'London']], [['region', 'Vendor A']], [['city', 'Leeds, London']],
        [['region', 'Vendor A'], ['city', 'London']], [['all', 'Nationwide']],
        [['all', 'Nationwide'], ['operator', '-Three']], [['city', 'London'], ['operator', '-Three']],
    ]
    assert scopes[2][0]['title'] == 'Region: Vendor A'
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    for dimension in ('all', 'region', 'cluster', 'city', 'operator', 'vendor'):
        assert f'.saved-scoring-scope[data-dimension="{dimension}"]' in template
    # The selected card folds and unfolds with Details, without opening the dropdown.
    assert "const details = event.target.closest('[data-saved-scoring-details]');" in script
    assert '.selected-saved-scoring.is-folded > :not(.saved-scoring-tabs):not(.saved-scoring-name):not(.saved-scoring-item-top):not(.saved-scoring-actions)' in template
    # Beside it, the NR Mode of the Saved Scoring as an outlined tab.
    assert '.saved-scoring-mode[data-nr-mode="sa"] { border-color: #be185d; color: #be185d; }' in template


@pytest.mark.parametrize('list_index', [0, 1])
def test_choosing_job_from_either_list_loads_selected_results(list_index):
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    start = script.index("  async function savedScoringAction(event) {")
    end = script.index("\n  root.addEventListener('click',", start)
    program = r'''
let loaded, persisted = false, focused = false, deleted, restored;
const handlers = [];
const savedScoringLists = [0, 1].map(() => ({addEventListener: (_name, callback) => {handlers.push(callback);}}));
const savedScorings = [{id: '20'}, {id: '15'}];
const savedScoringIdOf = savedScoring => savedScoring.id;
let userSelectedSavedScoring = false, selectedSavedScoringId = '20', selectedSavedScoring = savedScorings[0];
const root = {querySelector: () => ({scrollIntoView: () => {focused = true;}})};
const savedScoringSelector = {open: true, contains: () => LIST_INDEX === 0, querySelector: () => ({focus: () => {focused = true;}})};
const savedScoringSelectors = [{open: true, contains: () => false}, savedScoringSelector];
const persistScoringViewState = () => {persisted = true;};
const restoreCalculationSelectionFromSavedScoring = savedScoring => {restored = savedScoring.id;};
let unmatched = true;
const showUnmatchedSelection = value => {unmatched = value;};
let editingSavedScoring = null;
const stopSavedScoringEdit = () => { editingSavedScoring = null; };
const loadSavedScoring = async (savedScoring, force) => {loaded = {id: savedScoring.id, force};};
const deleteSavedScoring = id => {deleted = id;};
const savedScoringsUrl = '/api/scoring/saved-scorings';
const used = [];
const requestJson = (url, options) => { used.push([url, options.method]); return Promise.resolve({}); };
let refreshed = 0;
const refreshSavedScorings = async () => { refreshed += 1; };
const unfoldedSavedScorings = new Map();
''' + _function_source(script, 'unfoldedSavedScoringIds') + f'\nconst LIST_INDEX = {list_index};\n' + script[start:end] + f'\nconst handler = handlers[{list_index}];\n' + r'''
(async () => {
  // A click on the card folds or unfolds it, without opening it.
  const row = {classes: new Set(), classList: {toggle(name, force) { if (force) row.classes.add(name); else row.classes.delete(name); }}};
  const card = {dataset: {savedScoringId: '15'}, attributes: {}, closest: () => row, setAttribute(key, value) { card.attributes[key] = value; }};
  const cardClick = {target: {closest: selector => (selector === '[data-saved-scoring-id]' ? card : null)}};
  await handler(cardClick);
  const unfoldedOnce = [row.classes.has('is-expanded'), card.attributes['aria-expanded'], loaded === undefined];
  await handler(cardClick);
  const foldedAgain = [row.classes.has('is-expanded'), card.attributes['aria-expanded']];
  // Use Filter opens it.
  await handler({target: {closest: selector => selector === '[data-saved-scoring-use]' ? {dataset: {savedScoringUse: '15'}} : null}});
  const selection = {loaded, persisted, focused, open: savedScoringSelectors.some(selector => selector.open), selectedSavedScoringId, userSelectedSavedScoring, restored,
    unmatched};
  loaded = null;
  await handler({target: {closest: selector => selector === '[data-delete-saved-scoring-id]' ? {dataset: {deleteSavedScoringId: '20'}} : null}});
  await new Promise(resolve => setTimeout(resolve));
  process.stdout.write(JSON.stringify({unfoldedOnce, foldedAgain, selection, deleted, loaded, used, refreshed}));
})();
'''
    result = _run_node_json(program, {})
    assert result['unfoldedOnce'] == [True, 'true', True] and result['foldedAgain'] == [False, 'false']
    assert result['selection'] == {
        'loaded': {'id': '15', 'force': True}, 'persisted': True, 'focused': True,
        'open': False, 'selectedSavedScoringId': '15', 'userSelectedSavedScoring': True, 'restored': '15',
        # Opened, its selection is a Saved Scoring again: its card and results show.
        'unmatched': False,
    }
    assert result['deleted'] == '20' and result['loaded'] is None
    # Opening it with Use Filter counts as a use.
    assert result['used'] == [['/api/scoring/saved-scorings/15/use', 'POST']] and result['refreshed'] == 1


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
const exportBase = '/scoring/saved-scorings';
const selectedTableMode = () => 'expanded';
const selectedGapLayout = () => 'end';
const selectedEnvironment = 'all';
const showGapValues = () => false;
const gapKpiOrder = 'all';
let selectionUnmatched = false;
''' + _function_source(script, 'setExportLinks') + r'''
setExportLinks('21', false);
const unavailable = links.map(link => ({hidden: link.hidden, disabled: link.attributes['aria-disabled'], tabIndex: link.tabIndex, href: link.href}));
setExportLinks('21', true);
const available = links.map(link => ({hidden: link.hidden, disabled: link.attributes['aria-disabled'], tabIndex: link.tabIndex, href: link.href}));
setExportLinks('', false);
const reset = links.map(link => link.attributes['aria-disabled']);
// The scoring shown stays exportable with changes not calculated yet (its results stay in sight).
selectionUnmatched = true;
setExportLinks('21', true);
const unmatched = links.map(link => link.attributes['aria-disabled']);
process.stdout.write(JSON.stringify({unavailable, available, reset, unmatched}));
'''
    result = _run_node_json(program, {})
    assert all(link == {'hidden': False, 'disabled': 'true', 'tabIndex': -1, 'href': '#'}
               for link in result['unavailable'])
    assert all(link['hidden'] is False and link['disabled'] == 'false' and link['tabIndex'] == 0
               and link['href'].startswith('/scoring/saved-scorings/21/export/') for link in result['available'])
    # Only the PowerPoint and Word take the KPI order of the GAP tables and the KPI GAP Profile.
    assert ['gap_kpi_order=all' in link['href'] for link in result['available']] == [False, False, True]
    assert result['reset'] == ['true', 'true', 'true']
    assert result['unmatched'] == ['false', 'false', 'false']


def test_reload_opens_scoring_dimmed_at_the_saved_position_until_it_is_drawn():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    restore = (SCORING_SCRIPT.parents[1] / 'core' / 'page_restore.js').read_text(encoding='utf-8')
    styles = (SCORING_SCRIPT.parents[2] / 'css' / 'core' / 'app.css').read_text(encoding='utf-8')
    # Before the page is drawn, with the same key as scoring.js: the page dimmed under a gradient with a notice.
    early = template.split('{% block content %}', 1)[1].split('<style>', 1)[0]
    assert "js/core/page_restore.js" in early and "window.PageRestore.keyOf('scoring-view'," in early
    assert "notice: 'Loading Scoring & GAP Analysis where you left it…'" in early
    assert "'drivetest-analyzer', 'scoring-view',\n    encodeURIComponent(document.body.dataset.authenticatedUser || 'anonymous')," in script
    assert "const keyOf = (view, workspaceId) => ['drivetest-analyzer', view," in restore
    assert "window.history.scrollRestoration = 'manual';" in restore and "overlay.className = `page-restore-overlay" in restore
    # Opened at the saved position, as tall as it needs, until the content reaches it.
    assert 'document.documentElement.style.minHeight = `${top + window.innerHeight}px`;' in restore and 'window.scrollTo(0, top);' in restore
    assert '.page-restore-overlay {' in styles and 'position: fixed; inset: 0;' in styles.split('.page-restore-overlay {', 1)[1].split('}', 1)[0]
    assert 'linear-gradient(' in styles.split('.page-restore-overlay::before {', 1)[1].split('}', 1)[0]
    # It goes once the page is at the position (or the user takes over), and at the end of the restoration.
    follow = restore.split('  function follow(', 1)[1].split('\n  }\n', 1)[0]
    assert 'if ((maximum >= target && !reading) || interacted) document.querySelector(NOTICE)?.remove();' in follow
    assert 'const pageHeight = document.body.scrollHeight;' in follow and "document.documentElement.style.minHeight = '';" in follow
    assert 'window.PageRestore.follow(target, {onDone: () => {' in script
    # Only a reload (or Back and Forward, or the module opened again from the bar at the bottom of a phone) returns
    # there: opening the module otherwise starts at its top.
    reopened_or_reloaded = ("(window.pageReopened === true\n    || ['reload', 'back_forward'].includes("
                            "window.performance.getEntriesByType?.('navigation')?.[0]?.type));")
    assert reopened_or_reloaded in restore
    assert ("&& (window.pageReopened === true || ['reload', 'back_forward'].includes("
            "window.performance.getEntriesByType?.('navigation')?.[0]?.type));") in script
    # What was in view when the page was left shows as it was, in a frame without scripts, under the gradient.
    assert "window.sessionStorage.getItem(`${key}:snapshot`)" in restore and "frame.setAttribute('sandbox', 'allow-same-origin');" in restore
    assert 'frame.contentWindow.scrollTo(0, snapshot.scroll_y);' in restore
    capture = restore.split('  function snapshot() {', 1)[1].split('\n  function keepSnapshot(', 1)[0]
    assert "['SCRIPT', 'NOSCRIPT', 'TEMPLATE', 'IFRAME'].includes(tag)" in capture and 'if (box.bottom < 0 || box.top > viewportHeight) {' in capture
    assert "window.sessionStorage.setItem(snapshotKey, JSON.stringify({scroll_y: Math.round(window.scrollY), width: window.innerWidth, html}));" in restore
    assert "window.PageRestore.keepSnapshot(scoringViewStorageKey," in script
    assert '--page-restore-accent: #226849;' in styles and 'border-left: 5px solid var(--page-restore-accent);' in styles

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
    styles = (SCORING_TEMPLATE.parents[1] / 'static/css/core/app.css').read_text(encoding='utf-8')
    assert 'background: #e3f0fc; color: #1f5f9e;' in styles.split('.element-image-button {', 1)[1].split('}', 1)[0]
    # The one of the whole card in a more intense blue.
    assert '.element-image-button[data-image-level="card"] { border-color: #1f6fc0; background: #2f86dc; color: #fff; }' in styles


def test_cdrs_used_show_four_cdrs_of_each_type_before_they_scroll():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    # Measured on the fourth CDR shown (whatever lines its name takes), whenever they are drawn again or the panel changes
    # width; four or fewer, as tall as they are.
    assert 'function fitAutoCdrLists() {' in script
    assert "const bottom = items[3].getBoundingClientRect().bottom - list.getBoundingClientRect().top + list.scrollTop;" in script
    assert "list.style.maxHeight = 'none';" in script
    assert 'new MutationObserver(fitAutoCdrLists).observe(autoCdrGroups, {childList: true, subtree: true});' in script


def test_move_up_and_down_move_the_checked_favourite_scorings_one_place():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    bulk = template.split('data-saved-scorings-bulk', 1)[1].split('</div>', 1)[0]
    # Move Up and Move Down come before Use newer CDRs.
    assert bulk.index('data-saved-scorings-move="up"') < bulk.index('data-saved-scorings-move="down"') \
        < bulk.index('data-saved-scorings-use-newer')
    # The bar stays at the top while the panel is scrolled, and the moved cards light up where they land.
    assert '.saved-scorings-bulk { position: sticky; top: calc(var(--module-tabs-offset, 0px) + var(--section-top-offset, 0px));' in template
    assert '.saved-scorings-panel .saved-scoring-row.is-moved .saved-scoring-item { animation: saved-scoring-moved' in template
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    assert "root.querySelector('[data-saved-scorings-bulk]')].filter(Boolean);" in script
    assert "rows.forEach(row => row.classList.add('is-moved'));" in script
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {checkedSavedScoringIds: new Set()};
vm.createContext(context);
vm.runInContext(payload.snippets.join('\n') + `
  const order = ['1', '2', '3', '4', '5'];
  const move = (checked, step) => { checkedSavedScoringIds.clear(); checked.forEach(id => checkedSavedScoringIds.add(id)); return movedSavedScoringOrder(order, step); };
  globalThis.orders = [
    move(['3'], -1), move(['3'], 1), move(['2', '3'], -1), move(['1', '3'], -1), move(['5'], 1), move(['2', '4'], 1),
  ];`, context);
process.stdout.write(JSON.stringify(context.orders));
"""
    orders = _run_node_json(program, {'snippets': [_function_source(script, 'movedSavedScoringOrder')]})
    assert orders == [
        ['1', '3', '2', '4', '5'], ['1', '2', '4', '3', '5'], ['2', '3', '1', '4', '5'],
        # The first one cannot go up and the last one cannot go down; the others still move.
        ['1', '3', '2', '4', '5'], ['1', '2', '3', '4', '5'], ['1', '3', '2', '5', '4'],
    ]


def test_filter_navigator_opens_from_the_favourites_panel_and_both_selectors():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    # The tree button of the selector sits in its summary, beside the selected card; the panel has it beside its title.
    for selector in template.split('<details class="saved-scoring-selector" data-saved-scoring-selector>')[1:]:
        summary = selector.split('</summary>', 1)[0]
        assert 'data-selected-saved-scoring-card' in summary and 'data-saved-scoring-navigator-open' in summary
    panel = template.split('<details class="panel collapsible-panel saved-scorings-panel" data-panel-state-key="scoring:favourite-scorings" data-saved-scorings-panel>', 1)[1].split('data-saved-scorings-bulk', 1)[0]
    assert 'data-saved-scoring-navigator-open' in panel and 'Filter Navigator' in panel
    # The selector, the panel, the Favourite Scorings main button, the step of the start guide and the name of the
    # scoring shown.
    assert template.count('data-saved-scoring-navigator-open') == 5
    dialog = template.split('<dialog class="saved-scoring-navigator"', 1)[1].split('</dialog>', 1)[0]
    for marker in ('data-saved-scoring-navigator-search', 'role="tree"', 'data-saved-scoring-navigator-tree',
                   'data-saved-scoring-navigator-count', 'data-saved-scoring-navigator-close', 'data-saved-scoring-navigator-manage'):
        assert marker in dialog
    assert '.saved-scoring-selector > summary { display: grid; grid-template-columns: minmax(0,1fr) auto auto;' in template
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    # Choosing a Favourite Scoring uses it as Use Filter on its card does, and App Events say where it was chosen.
    assert "useSavedScoring(savedScoring, {fromDropdown: origin, source: 'navigator'});" in script
    assert "await useSavedScoring(savedScoring, {fromDropdown: savedScoringSelectors.find(selector => selector.contains(button))});" in script
    # A click on the selected card opens the Filter Navigator, not the dropdown.
    assert 'openSavedScoringNavigator(selector);' in script


def test_filter_navigator_search_finds_every_word_and_keeps_words_typed_together():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {};
vm.createContext(context);
vm.runInContext(payload.snippets.join('\n') + `
  const entry = (id, texts) => { const phrases = texts.map(savedScoringNavigatorWords); return {id, phrases, words: phrases.flat()}; };
  const entries = [
    entry('1', ['Latest Campaign - London', 'London', 'NSA', 'Latest campaign', '2026-Q3']),
    entry('2', ['Latest 2 Campaigns - SA - London', 'London', 'SA', 'Latest 2 campaigns', '2026-Q2 2026-Q3']),
    entry('3', ['Latest Campaign - SA - Manchester', 'Manchester', 'SA', 'Latest campaign', '2026-Q3']),
    entry('4', ['Latest 2 Campaigns - NSA vs SA - Manchester', 'Manchester', 'NSA vs SA', 'Latest 2 campaigns', '2026-Q2']),
    entry('5', ['Prévisión São Paulo', 'Nationwide', 'NSA', 'Previous campaign', '2026-Q2']),
  ];
  const find = query => savedScoringNavigatorFound(entries, query).map(item => item.id);
  globalThis.results = {
    words: savedScoringNavigatorWords('Latest 2 Campaigns - NSA vs SA (São Paulo)'),
    latestCamp: find('latest camp'), latestCam: find('latest cam'), latest: find('LATEST'), latest2: find('latest 2'),
    scattered: find('man sa lat 2'), reversed: find('camp latest'), sa: find('sa'), nsa: find('nsa'),
    year: find('2026'), number: find('20'), accents: find('sao prevision'), none: find('glasgow'), empty: find(''),
  };`, context);
process.stdout.write(JSON.stringify(context.results));
"""
    names = ('savedScoringNavigatorWords', 'savedScoringNavigatorWordMatches', 'savedScoringNavigatorMatches',
             'savedScoringNavigatorFound')
    results = _run_node_json(program, {'snippets': [_function_source(script, name) for name in names]})
    assert results['words'] == ['latest', '2', 'campaigns', 'nsa', 'vs', 'sa', 'sao', 'paulo']
    # Words typed together stay together when a Favourite Scoring has them together; otherwise they are found anywhere.
    assert results['latestCamp'] == results['latestCam'] == ['1', '3']
    assert results['latest'] == ['1', '2', '3', '4'] and results['latest2'] == ['2', '4']
    assert results['scattered'] == ['4'] and results['reversed'] == ['1', '2', '3', '4']
    # A word typed is the start of a word (sa is not NSA, but São without its accent), a number of one or two digits a
    # whole word.
    assert results['sa'] == ['2', '3', '4', '5'] and results['nsa'] == ['1', '4', '5']
    assert results['year'] == ['1', '2', '3', '4', '5'] and results['number'] == []
    assert results['accents'] == ['5'] and results['none'] == [] and len(results['empty']) == 5


def test_filter_navigator_tree_groups_by_area_and_nr_mode_and_tells_alike_leaves_apart():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    program = r"""
const vm = require('node:vm');
const payload = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const context = {};
vm.createContext(context);
vm.runInContext(payload.snippets.join('\n') + `
  const details = (operator, reference) => [['operator', 'Operator', operator], ['vendor', 'Vendor', 'All Vendors'],
    ['', 'GAP Reference', reference], ['', 'CDRs', 'Q3 CDRs']];
  const entry = (id, area, mode, campaign, campaigns, operator = 'All Operators', reference = 'EE') => ({
    id, areaKey: area, areas: [{text: area}], mode, modeLabel: mode === 'NSA+SA' ? 'NSA vs SA' : mode,
    modeKey: area + '#' + mode, campaign, campaigns, details: details(operator, reference), distinct: []});
  const entries = [
    entry('1', 'London', 'SA', 'Latest campaign', ['2026-Q3']),
    entry('2', 'Nationwide', 'NSA', 'Latest campaign', ['2026-Q3']),
    entry('3', 'London', 'NSA+SA', 'Latest campaign', ['2026-Q3']),
    entry('4', 'London', 'NSA', 'Latest campaign', ['2026-Q3']),
    entry('5', 'London', 'NSA', 'Latest campaign', ['2026-Q3'], 'EE'),
    entry('6', 'London', 'NSA', 'Latest campaign', ['2026-Q3'], 'All Operators', 'BT'),
    entry('7', 'London', 'NSA', 'Latest 2 campaigns', ['2026-Q2', '2026-Q3']),
    entry('8', 'London', 'NSA', 'Latest campaign', ['2026-Q2']),
    entry('9', 'Nationwide', 'NSA', 'Latest campaign', ['2026-Q3']),
  ];
  const tree = savedScoringNavigatorTree(entries);
  globalThis.results = {
    areas: tree.map(area => area.key),
    modes: tree.map(area => area.modes.map(mode => mode.mode + ':' + mode.entries.map(item => item.id).join(','))),
    distinct: Object.fromEntries(entries.map(item => [item.id, item.distinct.map(detail => detail[1] + ': ' + detail[2])])),
  };`, context);
process.stdout.write(JSON.stringify(context.results));
"""
    results = _run_node_json(program, {'snippets': [_function_source(script, 'savedScoringNavigatorTree')]})
    # Areas in the order of the list, NR Modes NSA, SA, NSA vs SA, Favourite Scorings in the order of the list.
    assert results['areas'] == ['London', 'Nationwide']
    assert results['modes'] == [['NSA:4,5,6,7,8', 'SA:1', 'NSA+SA:3'], ['NSA:2,9']]
    # Alike leaves show what tells them apart (their Filter ID when nothing does); the others show nothing.
    assert results['distinct'] == {
        '1': [], '3': [], '7': [], '8': [],
        '4': ['Operator: All Operators', 'GAP Reference: EE'], '5': ['Operator: EE', 'GAP Reference: EE'],
        '6': ['Operator: All Operators', 'GAP Reference: BT'], '2': ['Filter ID: 2'], '9': ['Filter ID: 9'],
    }
