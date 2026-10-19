from pathlib import Path
from html.parser import HTMLParser

from tests.test_scoring_results_controls import _function_source, _run_node_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCORING_TEMPLATE = PROJECT_ROOT / 'src/web_interface/templates/scoring.html'
SCORING_SCRIPT = PROJECT_ROOT / 'src/web_interface/static/js/scoring.js'


class _ScoringMarkupParser(HTMLParser):
    _VOID_ELEMENTS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.elements = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.elements.append((tag, attributes, tuple(self.stack)))
        if tag not in self._VOID_ELEMENTS:
            self.stack.append((tag, attributes))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


def test_scoring_selection_loads_from_server_before_enabling_controls():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')

    assert "root.dataset.selectionUrl || '/api/scoring/selection'" in script
    assert 'data-selection-url="/api/scoring/selection"' in template
    assert "const body = await requestJson(selectionUrl);" in script
    # The selection comes back as it was left, with its Geographical Areas & Scoring Trends (always included).
    assert 'applySavedCalculationSelection(body.selection);' in script
    assert 'selectionPersisted = body.persisted !== false;' in script
    assert 'if (!selectionPersisted) {' in script
    assert 'await persistCalculationSelection({force: true});' in script
    assert "calculationPanel.inert = true;" in script
    assert "calculationPanel.inert = false;" in script
    assert 'Promise.all([loadCalculationSelection(), refreshSavedFilters()]).catch(() => {});' in script
    assert 'restoreOpenedSavedFilterTrends' not in script and 'data-scoring-area-enabled' not in script
    assert 'localStorage' not in script


def test_scoring_selection_roundtrips_explicit_empty_filters_and_methodology():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')

    assert "const selectionFieldOrder = ['Region', 'City', 'Operator', 'Vendor', 'Campaign'];" in script
    assert "context_filters: Object.fromEntries(selectionFieldOrder.map(key => [key, filters[key] || []]))" in script
    assert "scoring_profile_id: String(scoringProfileSelect?.value || activeProfileId)" in script
    assert "const requested = filters[key] ?? filters[key.toLowerCase()] ?? [];" in script
    assert "option.selected = !option.disabled && selected.has(option.value.toLocaleLowerCase())" in script
    assert '.scoring-note[data-kind="warning"]' in template


def test_scoring_calculation_panel_orders_nr_mode_campaign_cdrs_filters_and_gap_reference():
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')
    parser = _ScoringMarkupParser()
    parser.feed(template)
    elements = parser.elements

    assert 'Select NR Mode, Campaign, filters, Split by &amp; GAP reference' in template
    # NR Mode and Campaign choose the CDRs, listed read-only below them; the CDR checklist is hidden.
    assert template.index('data-nr-filter') < template.index('data-scoring-context-filter="Campaign"')
    assert template.index('data-scoring-context-filter="Campaign"') < template.index('data-scoring-auto-cdrs')
    assert template.index('data-scoring-auto-cdrs') < template.index('id="scoring-context-filters-title"')
    assert template.index('id="scoring-context-filters-title"') < template.index('<strong>Split by</strong>')
    # The GAP reference beside the Campaign.
    assert template.index('data-scoring-context-filter="Campaign"') < template.index('id="scoring-gap-reference-title"') < template.index(
        'data-scoring-auto-cdrs')
    assert 'data-scoring-select-datasets' not in template
    dataset_list = next(attrs for tag, attrs, _ancestors in elements if 'data-dataset-list' in attrs)
    assert 'hidden' in dataset_list
    # The Campaign is not repeated among the context filters.
    assert "{% for level in aggregation_levels if level != 'Campaign' %}" in template

    gap_select = next(
        (attrs, ancestors) for tag, attrs, ancestors in elements
        if tag == 'select' and 'data-baseline-operator' in attrs
    )
    assert any(
        ancestor_attrs.get('aria-labelledby') == 'scoring-gap-reference-title'
        for _tag, ancestor_attrs in gap_select[1]
    )


def test_server_chosen_cdrs_are_checked_unless_an_opened_saved_filter_keeps_its_own():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    functions = '\n'.join(_function_source(script, name) for name in (
        'applyAutoCdrResponse', 'calculationSelectionFromControls',
    ))
    program = r"""
let autoCdrs = {options: null, incomplete: []};
let pinnedCdrs = false;
const selectedAreaSummary = () => ({enabled: false});
const chosenComparedOperators = () => [];
const option = {hidden: false};
const datasetInputs = [1, 2, 3].map(id => ({value: String(id), checked: id === 3, closest: () => option}));
const selectedDatasetIds = () => datasetInputs.filter(input => input.checked).map(input => input.value);
const selectedLevels = () => ['Operator'];
const selectedContextFilters = () => ({Campaign: ['UK_Q2_2026']});
const selectionFieldOrder = ['Region', 'City', 'Operator', 'Vendor', 'Campaign'];
const nrFilter = {value: 'SA'};
const baselineInput = {value: 'EE'};
const scoringProfileSelect = {value: 'methodology-1'};
const activeProfileId = 'methodology-1';
""" + functions + r"""
applyAutoCdrResponse({dataset_ids: [1, 2], options: {Campaign: ['UK_Q2_2026']}, incomplete_campaigns: ['2026-Q3']});
const automatic = {ids: selectedDatasetIds(), selection: calculationSelectionFromControls(), incomplete: autoCdrs.incomplete};
pinnedCdrs = true;
applyAutoCdrResponse({dataset_ids: [3], options: {}});
process.stdout.write(JSON.stringify({automatic, pinned: {ids: selectedDatasetIds(), auto: calculationSelectionFromControls().auto_cdrs}}));
"""
    result = _run_node_json(program, {})
    assert result['automatic']['ids'] == ['1', '2']
    assert result['automatic']['incomplete'] == ['2026-Q3']
    assert result['automatic']['selection'] == {
        'dataset_ids': [1, 2], 'auto_cdrs': True, 'aggregation_levels': ['Operator'], 'nr_mode': 'SA',
        'baseline_operator': 'EE', 'scoring_profile_id': 'methodology-1',
        'context_filters': {'Region': [], 'City': [], 'Operator': [], 'Vendor': [], 'Campaign': ['UK_Q2_2026']},
        'area_summary': {'enabled': False}, 'compared_operators': [],
    }
    # An opened Saved Filter keeps its own CDRs while its filter lists are refreshed.
    assert result['pinned'] == {'ids': ['1', '2'], 'auto': False}


def test_dataset_name_date_parses_supported_dates_and_rejects_invalid_calendar_values():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    parser = _function_source(script, 'datasetNameDate')
    program = parser + r'''
const values = [
  ['cdr_20260817.csv', Date.UTC(2026, 7, 17)],
  ['cdr-20260817.csv', Date.UTC(2026, 7, 17)],
  ['cdr_17-08-2026.csv', Date.UTC(2026, 7, 17)],
  ['cdr-17082026.csv', Date.UTC(2026, 7, 17)],
  ['cdr_2026-Q3.csv', Date.UTC(2026, 6, 1)],
  ['cdr_Q3-2026.csv', Date.UTC(2026, 6, 1)],
  ['cdr_2024-02-29.csv', Date.UTC(2024, 1, 29)],
];
const parsed = values.map(([name]) => datasetNameDate(name));
const invalid = [
  'cdr_2025-02-29.csv', 'cdr_2026-13-01.csv', 'cdr_2026-00-01.csv',
  'cdr_2026-04-31.csv', 'cdr_2026-Q0.csv', 'cdr_Q5-2026.csv',
].map(name => datasetNameDate(name));
process.stdout.write(JSON.stringify({expected: values.map(([, timestamp]) => timestamp), parsed, invalid}));
'''

    result = _run_node_json(program, {})
    assert result['parsed'] == result['expected']
    assert all(value is None for value in result['invalid'])


def test_latest_dataset_fallback_prioritizes_filename_dates_then_upload_and_id_and_skips_hidden_nr():
    # Used only when the server cannot choose the CDRs (the saved selection cannot be loaded).
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    functions = '\n'.join(_function_source(script, name) for name in (
        'datasetNameDate', 'selectLatestDatasetForEachKind',
    ))
    program = r'''
const datasetInputs = [];
const datasetOptions = [];
const datasetKindOrder = ['data', 'voice', 'speech'];
function addDataset(kind, id, name, uploadedAt, nrMode = 'NSA') {
  const input = {value: String(id), checked: false};
  const option = {hidden: nrMode !== 'NSA', dataset: {
    datasetKind: kind, datasetName: name, uploadedAt, nrMode,
  }, querySelector: () => input};
  input.option = option;
  datasetInputs.push(input);
  datasetOptions.push(option);
}
addDataset('data', 1, 'cdr_2025-12-31.csv', '2026-12-01T00:00:00Z');
addDataset('data', 2, 'cdr_2026-03-01.csv', '2026-02-01T00:00:00Z');
addDataset('data', 3, 'cdr_2026-03-01.csv', '2026-02-01T00:00:00Z');
addDataset('data', 6, 'cdr_2026-03-01.csv', '2026-02-02T00:00:00Z');
addDataset('data', 4, 'cdr_2026-02-28.csv', '2026-03-01T00:00:00Z');
addDataset('data', 5, '', '2026-02-15T00:00:00Z');
addDataset('voice', 10, 'voice_invalid_date.csv', '2026-01-01T00:00:00Z');
addDataset('voice', 11, '', '2026-01-01T00:00:00Z');
addDataset('voice', 12, '', '2025-12-31T00:00:00Z');
addDataset('speech', 14, '', '');
addDataset('speech', 99, 'speech_2026-12-01.csv', '2026-12-01T00:00:00Z', 'SA');
''' + functions + r'''
const selectedIds = () => datasetInputs
  .filter(input => input.checked && !input.option.hidden).map(input => Number(input.value)).sort((a, b) => a - b);
selectLatestDatasetForEachKind(2);
const latestTwo = selectedIds();
selectLatestDatasetForEachKind(1);
const latestOne = selectedIds();
selectLatestDatasetForEachKind(3);
const latestThree = selectedIds();
process.stdout.write(JSON.stringify({latestTwo, latestOne, latestThree}));
'''

    result = _run_node_json(program, {})
    assert result['latestTwo'] == [3, 6, 10, 11, 14]
    assert result['latestOne'] == [6, 11, 14]
    assert result['latestThree'] == [2, 3, 6, 10, 11, 12, 14]


def test_scoring_selection_saves_are_debounced_serialized_and_flushed_on_navigation():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')

    assert 'function scheduleSelectionSave()' in script
    assert '}, 250);' in script
    assert 'selectionSaveChain = selectionSaveChain.catch(() => null).then(async () =>' in script
    assert 'if (!force && key === lastQueuedSelectionKey) return selectionSaveChain;' in script
    assert 'if (key === lastSavedSelectionKey || key === lastQueuedSelectionKey)' not in script
    assert 'client_id: selectionClientId, client_revision: clientRevision' in script
    assert "window.addEventListener('pagehide', flushSelectionSaveOnPageHide);" in script
    assert 'keepalive: true,' in script
    assert 'if (selectionPersisted && key === lastSavedSelectionKey && key === lastQueuedSelectionKey) return;' in script
    assert 'if (!selectionLoaded || restoringSelection || !selectionDirty) return;' in script


def test_job_selection_restoration_maps_job_fields_and_schedules_persistence():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    functions = '\n'.join(_function_source(script, name) for name in (
        'restoreCalculationSelectionFromSavedFilter', 'scheduleSelectionSave',
    ))
    program = r'''
let applied, persisted = false, timeoutDelay, timeoutCallback, autoRefresh = null;
let restoringSelection = false, selectionLoaded = true, selectionDirty = false, pinnedCdrs = false;
const isCampaignPreset = value => String(value).startsWith('@');
let selectionSaveTimer = null;
const applySavedCalculationSelection = selection => {applied = selection;};
const scheduleAutoCdrRefresh = options => {autoRefresh = options;};
const persistCalculationSelection = () => {persisted = true;};
const window = {
  clearTimeout: () => {},
  setTimeout: (callback, delay) => {timeoutCallback = callback; timeoutDelay = delay; return 42;},
};
''' + functions + r'''
restoreCalculationSelectionFromSavedFilter({
  dataset_ids: [12, '13'], aggregation_levels: ['City', 'Vendor'], levels: ['Legacy'],
  nr_mode: 'NR', baseline_operator: 'EE', scoring_profile_id: 'profile-7',
  context_filters: {Region: ['North'], City: [], Operator: ['EE'], Vendor: [], Campaign: ['Spring']},
});
const queued = {applied, selectionDirty, selectionSaveTimer, timeoutDelay, pinnedCdrs, autoRefresh};
timeoutCallback();
process.stdout.write(JSON.stringify({queued, persisted}));
'''
    result = _run_node_json(program, {})
    assert result['queued']['applied'] == {
        'dataset_ids': [12, '13'], 'aggregation_levels': ['City', 'Vendor'],
        'nr_mode': 'NR', 'baseline_operator': 'EE', 'scoring_profile_id': 'profile-7',
        'context_filters': {
            'Region': ['North'], 'City': [], 'Operator': ['EE'], 'Vendor': [], 'Campaign': ['Spring'],
        },
        # One saved without Geographical Areas & Scoring Trends takes those it is calculated with: each Region and London.
        'area_summary': {'enabled': True, 'breakdown': 'Region', 'cities': ['London'], 'time_split': 'Campaign', 'campaigns': []},
    }
    assert result['queued']['selectionDirty'] is True
    assert result['queued']['selectionSaveTimer'] == 42
    assert result['queued']['timeoutDelay'] == 250
    # The panel shows the CDRs of the Saved Filter, and the lists of its filters follow for its NR Mode and filters.
    assert result['queued']['pinnedCdrs'] is True
    assert result['queued']['autoRefresh'] == {'delay': 0}
    assert result['persisted'] is True


def test_job_selection_restoration_uses_legacy_levels_field():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    restore = _function_source(script, 'restoreCalculationSelectionFromSavedFilter')
    program = r'''
let applied, pinnedCdrs = false;
const applySavedCalculationSelection = selection => {applied = selection;};
const scheduleSelectionSave = () => {};
const scheduleAutoCdrRefresh = () => {};
''' + restore + r'''
restoreCalculationSelectionFromSavedFilter({dataset_ids: [5], levels: ['Operator', 'City']});
process.stdout.write(JSON.stringify(applied));
'''
    result = _run_node_json(program, {})
    assert result['aggregation_levels'] == ['Operator', 'City']
    assert result['dataset_ids'] == [5]
    assert result['context_filters'] == {}


def test_job_selection_restoration_clears_filters_on_actual_controls():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    apply_saved = _function_source(script, 'applySavedCalculationSelection')
    restore = _function_source(script, 'restoreCalculationSelectionFromSavedFilter')
    program = r'''
let restoringSelection = false, message = '', pinnedCdrs = false;
const scheduleAutoCdrRefresh = () => {};
const areaSummaryTimeSplit = null, areaSummaryBreakdown = null, areaSummaryCities = null, comparedOperatorsSelect = null;
const syncAreaSummary = () => {}, refreshAreaSummaryCities = () => {}, applyTrendCampaigns = () => {};
const selectionFieldOrder = ['Region', 'City'];
const nrFilter = {value: 'NSA', options: [{value: 'NSA'}, {value: 'NR'}]};
const datasetInput = {value: '8', checked: true, closest: () => ({hidden: false})};
const datasetInputs = [datasetInput];
const aggregationInputs = [
  {value: 'Operator', checked: true}, {value: 'City', checked: true}, {value: 'Region', checked: true},
];
const baselineInput = {value: 'EE', options: [{value: 'EE'}]};
const scoringProfileSelect = {value: 'profile-1'};
const activeProfileId = 'profile-1';
const scoringProfileById = new Map();
const applyNrFilter = () => {};
const updateSelection = () => {};
const applyProfileHierarchy = () => {};
const uniqueCatalogueValues = values => [...new Set(values.map(String))];
const filterSelect = values => ({
  options: values.map(value => ({value, disabled: false, selected: true})),
  dispatchEvent: () => {},
});
const contextFilterSelects = new Map([
  ['Region', filterSelect(['North'])], ['City', filterSelect(['Paris'])],
]);
const Event = class {constructor(type, options) {this.type = type; this.options = options;}};
const setMessage = text => {message = text;};
const scheduleSelectionSave = () => {};
''' + apply_saved + restore + r'''
restoreCalculationSelectionFromSavedFilter({dataset_ids: [], aggregation_levels: ['Operator'], context_filters: {}});
process.stdout.write(JSON.stringify({
  datasetChecked: datasetInput.checked,
  aggregationChecked: aggregationInputs.map(input => input.checked),
  filters: [...contextFilterSelects].map(([key, select]) => [key, select.options.map(option => option.selected)]),
  message,
}));
'''
    result = _run_node_json(program, {})
    assert result['datasetChecked'] is False
    assert result['aggregationChecked'] == [True, False, False]
    assert result['filters'] == [['Region', [False]], ['City', [False]]]
    assert result['message'] == ''


def test_only_explicit_job_list_selection_restores_saved_calculation_selection():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    handler_start = script.index("  for (const list of savedFilterLists) list.addEventListener('click', async event => {")
    handler_end = script.index("\n  root.addEventListener('click',", handler_start)
    job_list_handler = script[handler_start:handler_end]
    load_job = _function_source(script, 'loadSavedFilter')

    assert job_list_handler.count('restoreCalculationSelectionFromSavedFilter(savedFilter);') == 1
    assert 'await loadSavedFilter(savedFilter, true);' in job_list_handler
    assert 'restoreCalculationSelectionFromSavedFilter' not in load_job


def test_context_filters_keep_all_values_and_remembered_values_when_the_cdrs_change():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    refresh = _function_source(script, 'refreshContextFilterOptions')
    program = r'''
let selectedIds = ['sa'];
let autoCdrs = {options: null};
const datasetCatalogues = new Map([
  ['sa', {operators: ['VF', 'EE', 'VF-SA']}], ['nsa', {operators: ['VF', 'EE', 'VF-VoNR']}],
]);
const selectedDatasetIds = () => selectedIds;
const contextFilterDefinitions = [{key: 'Operator', catalogueKey: 'operators'}];
const uniqueCatalogueValues = values => [...new Set((values || []).map(String))];
const contextFilterOptions = (key, values) => values.map(value => ({value, label: value, color: ''}));
const scoringVendorName = value => value;
const mainCityIdentities = new Set();
const decorateOperatorOptions = () => {};
const refreshAreaSummaryCities = () => {}, refreshTrendCampaigns = () => {};
const campaignPresetLabels = {};
const isCampaignPreset = () => false;
const chosenCampaignPreset = () => '';
const document = {createElement: () => ({value: '', textContent: '', selected: false, disabled: false, dataset: {}, style: {}})};
const Event = class {constructor(type) {this.type = type;}};
const select = {
  options: [], dataset: {},
  get selectedOptions() { return this.options.filter(option => option.selected); },
  replaceChildren() { this.options = []; },
  append(option) { this.options.push(option); },
  dispatchEvent() {},
};
const contextFilterSelects = new Map([['Operator', select]]);
''' + refresh + r'''
const state = () => select.options.map(option => option.value + (option.selected ? '*' : '')).join(' ');
const log = [];
refreshContextFilterOptions();
select.options.forEach(option => { option.selected = true; });
for (const ids of [['nsa'], ['sa']]) { selectedIds = ids; refreshContextFilterOptions(); log.push(state()); }
select.options.forEach(option => { option.selected = option.value !== 'VF'; });
for (const ids of [['nsa'], ['sa']]) { selectedIds = ids; refreshContextFilterOptions(); log.push(state()); }
process.stdout.write(JSON.stringify(log));
'''
    assert _run_node_json(program, {}) == [
        # All values stays All values: the Operators the new CDRs add are checked too.
        'VF* EE* VF-VoNR*', 'VF* EE* VF-SA*',
        # A partial choice keeps the values the other CDRs do not have, for when they come back.
        'VF EE* VF-VoNR', 'VF EE* VF-SA*',
    ]


def test_included_area_summary_keeps_the_area_filters():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    template = SCORING_TEMPLATE.read_text(encoding='utf-8')

    # The summary is scored on the whole country: the Region, Cluster and City filters stay usable.
    assert 'data-scoring-area-filter-lock' not in template and 'is-area-locked' not in script
    assert 'Always the whole country: the Region, Cluster and City filters of the calculation do not apply to Geographical Areas and Scoring Trends.' in template


def test_an_opened_saved_filter_queued_again_keeps_its_progress_over_an_earlier_list():
    """Opening a Saved Filter whose CDRs changed queues it again; a list requested before that answer still reads it
    completed and must not show its old result or stop following its calculation."""
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    assert 'const calculatingSavedFilters = new Map();' in script
    assert 'if (isActive(record)) calculatingSavedFilters.set(id, {record, request: ++savedFilterRequests});' in script
    assert 'const request = ++savedFilterRequests;' in script
    assert 'if (calculating.request > request) return {...savedFilter, ...calculating.record};' in script
    assert 'const anyActive = savedFilters.some(isActive) || Boolean(selectedSavedFilter && isActive(selectedSavedFilter));' in script


def test_a_saved_filter_opened_from_the_saved_filters_panel_shows_its_results():
    script = SCORING_SCRIPT.read_text(encoding='utf-8')
    assert "const resultsPanel = root.querySelector('.scoring-results-panel');" in script
    assert "if (resultsPanel && typeof showSectionAtTop === 'function') showSectionAtTop(resultsPanel);" in script
    assert '    else showResults();' in script
    assert 'if (!fromDropdown && selectedSavedFilterId === savedFilterIdOf(savedFilter)) showResults();' in script
