(() => {
  const root = document.querySelector('[data-scoring-workspace]');
  if (!root) return;
  // Export to CSV sits above the Scoring and GAP tables; the panes are redrawn, so it is kept here
  // and placed back at the top of its pane after each drawing.
  const tableExports = {
    scoring: root.querySelector('[data-table-export="scoring"]'),
    gap: root.querySelector('[data-table-export="gap"]'),
  };
  const exportLinks = {
    scoring: tableExports.scoring?.querySelector('[data-export-scoring]'),
    gap: tableExports.gap?.querySelector('[data-export-gap]'),
    // Export Report (PPT/Word) is in the Calculation and the Results toolbars.
    ppt: [...root.querySelectorAll('[data-export-ppt]')],
  };

  const chartTooltip = document.createElement('div');
  chartTooltip.className = 'scoring-chart-tooltip';
  chartTooltip.id = 'scoring-chart-tooltip';
  chartTooltip.setAttribute('role', 'tooltip');
  chartTooltip.hidden = true;
  root.append(chartTooltip);
  let chartTooltipTarget = null;

  function chartTooltipAnchor(target) {
    const anchor = target?.closest?.('[data-chart-tooltip]')
      || target?.closest?.('[aria-label], [title]');
    return anchor && root.contains(anchor)
      && !anchor.matches('svg')
      && (anchor.hasAttribute('data-chart-tooltip') || anchor.closest('.scoring-chart-svg')) ? anchor : null;
  }

  function chartTooltipText(anchor) {
    return String(anchor?.getAttribute('data-chart-tooltip')
      || anchor?.getAttribute('aria-label')
      || anchor?.getAttribute('title')
      || anchor?.querySelector('title')?.textContent
      || '').trim();
  }

  function positionChartTooltip(event, anchor = chartTooltipTarget) {
    const text = chartTooltipText(anchor);
    if (!text) {
      chartTooltip.hidden = true;
      chartTooltipTarget = null;
      return;
    }
    chartTooltipTarget = anchor;
    chartTooltip.textContent = text;
    chartTooltip.hidden = false;
    const bounds = chartTooltip.getBoundingClientRect();
    const anchorBounds = anchor.getBoundingClientRect();
    const clientX = Number.isFinite(event?.clientX) ? event.clientX : anchorBounds.left + anchorBounds.width / 2;
    const clientY = Number.isFinite(event?.clientY) ? event.clientY : anchorBounds.top + anchorBounds.height / 2;
    const left = Math.max(8, Math.min(window.innerWidth - bounds.width - 8, clientX + 14));
    const top = Math.max(8, Math.min(window.innerHeight - bounds.height - 8, clientY + 14));
    chartTooltip.style.left = `${left}px`;
    chartTooltip.style.top = `${top}px`;
  }

  root.addEventListener('pointerover', event => {
    if (event.pointerType === 'touch') return;
    const anchor = chartTooltipAnchor(event.target);
    if (anchor) positionChartTooltip(event, anchor);
  });
  root.addEventListener('pointermove', event => {
    if (chartTooltipTarget && event.pointerType !== 'touch') positionChartTooltip(event);
  });
  root.addEventListener('pointerout', event => {
    if (!chartTooltipTarget) return;
    const nextAnchor = chartTooltipAnchor(event.relatedTarget);
    if (nextAnchor === chartTooltipTarget) return;
    chartTooltip.hidden = true;
    chartTooltipTarget = null;
  });
  root.addEventListener('focusin', event => {
    const anchor = chartTooltipAnchor(event.target);
    if (anchor) positionChartTooltip(null, anchor);
  });
  root.addEventListener('focusout', event => {
    if (chartTooltipTarget && !chartTooltipTarget.contains(event.relatedTarget)) {
      chartTooltip.hidden = true;
      chartTooltipTarget = null;
    }
  });

  // The colour themes of the charts and tables (see scoring_themes.py), NetCheck by default. The views are written in
  // the NetCheck colours: themedColor translates each one, and every shade of the GAP scale, into the chosen theme.
  const scoringThemeData = (() => {
    try { return JSON.parse(document.getElementById('scoring-themes-data')?.textContent || '{}'); } catch { return {}; }
  })();
  const scoringThemes = Array.isArray(scoringThemeData.themes) ? scoringThemeData.themes : [];
  const netcheckTheme = scoringThemes.find(theme => theme.id === 'netcheck') || scoringThemes[0] || null;
  const themeSources = new Map((scoringThemeData.sources || []).map(([color, token, position]) => [String(color).toUpperCase(), [token, position]]));
  let activeTheme = scoringThemes.find(theme => theme.id === root.dataset.scoringTheme) || netcheckTheme || {};
  const themeSelect = root.querySelector('[data-scoring-theme-select]');
  const hexChannels = color => [1, 3, 5].map(index => Number.parseInt(color.slice(index, index + 2), 16));
  const blendHex = (start, end, amount) => `#${hexChannels(start).map((value, index) => Math.round(value + (hexChannels(end)[index] - value)
    * Math.max(0, Math.min(1, amount))).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
  // How far a colour lies from white towards ``end``, when it lies on that blend.
  function gradientAmount(color, end, start = '#FFFFFF') {
    const low = hexChannels(start), high = hexChannels(end), value = hexChannels(color);
    const spans = high.map((channel, index) => channel - low[index]);
    const axis = spans.reduce((best, span, index) => (Math.abs(span) > Math.abs(spans[best]) ? index : best), 0);
    if (!spans[axis]) return null;
    const amount = (value[axis] - low[axis]) / spans[axis];
    if (!(amount > 0 && amount <= 1)) return null;
    return spans.every((span, index) => Math.abs(low[index] + span * amount - value[index]) <= 2.5) ? amount : null;
  }
  function themedColor(color) {
    const text = String(color || '').trim();
    const key = /^#?[0-9a-f]{6}$/i.test(text) ? `#${text.replace('#', '').toUpperCase()}` : null;
    if (!key || !activeTheme || !netcheckTheme || activeTheme.id === netcheckTheme.id) return color;
    const source = themeSources.get(key);
    if (source) {
      const [token, position] = source;
      const value = position === null || position === undefined ? activeTheme[token]
        : token === 'bands' ? activeTheme.bands?.[position] : activeTheme[token]?.[position];
      if (value) return value;
    }
    for (const token of ['gap_negative', 'gap_positive']) {
      const amount = gradientAmount(key, netcheckTheme[token], netcheckTheme.gap_neutral);
      if (amount !== null) return blendHex(activeTheme.gap_neutral, activeTheme[token], amount);
    }
    return color;
  }
  const rgbaOf = (color, alpha) => `rgba(${hexChannels(color).join(',')},${alpha})`;
  // The share of the largest GAP of its table a GAP cell holds (0 to 1), read from the NetCheck shade the views give it.
  function gapShare(color) {
    const text = String(color || '').trim();
    if (!netcheckTheme || !/^#?[0-9a-f]{6}$/i.test(text)) return 0;
    const key = `#${text.replace('#', '').toUpperCase()}`;
    for (const token of ['gap_negative', 'gap_positive']) {
      const amount = gradientAmount(key, netcheckTheme[token], netcheckTheme.gap_neutral);
      if (amount !== null) return Math.min(1, amount / .85);
    }
    return 0;
  }
  const themeStyleTokens = {
    title: 'title', accent: 'accent', header: 'header', 'header-text': 'header_text', 'soft-header': 'soft_header',
    'soft-header-text': 'soft_header_text', weight: 'weight', maximum: 'maximum', 'gap-header': 'gap_header', group: 'group',
    'group-alt': 'group_alt', font: 'font', 'number-font': 'number_font', surface: 'surface', ink: 'ink', muted: 'muted', line: 'line',
    category: 'category', total: 'total', 'row-alt': 'row_alt', border: 'border', best: 'best', worst: 'worst', loss: 'loss',
    gain: 'gain', 'loss-text': 'loss_text', 'gain-text': 'gain_text', voice: 'voice', data: 'data',
    'kpi-reliable': 'kpi_reliable', 'kpi-diff': 'kpi_diff', 'gap-negative': 'gap_negative', 'gap-positive': 'gap_positive',
  };
  function applyThemeStyles() {
    for (const [name, token] of Object.entries(themeStyleTokens)) {
      if (activeTheme?.[token]) root.style.setProperty(`--st-${name}`, activeTheme[token]);
    }
    // The strong colour of each score band: the dot, bar or tile of the themes that do not fill the cells.
    for (const [band, color] of Object.entries(activeTheme?.band_strong || {})) root.style.setProperty(`--st-band-${band.toLowerCase()}`, color);
    root.dataset.scoringTheme = activeTheme?.id || 'netcheck';
  }
  applyThemeStyles();

  const savedFiltersUrl = root.dataset.savedFiltersUrl || '/api/scoring/saved-filters';
  const selectionUrl = root.dataset.selectionUrl || '/api/scoring/selection';
  const exportBase = root.dataset.exportBase || '/scoring/saved-filters';
  const requestedSavedFilterId = new URLSearchParams(window.location.search).get('saved_filter_id');
  const requestedSavedFilterIdPending = {value: requestedSavedFilterId};
  const scoringViewStorageKey = [
    'drivetest-analyzer', 'scoring-view',
    encodeURIComponent(document.body.dataset.authenticatedUser || 'anonymous'),
    encodeURIComponent(root.dataset.scoringWorkspaceId || 'unknown'),
  ].join(':');
  const resultTabNames = new Set(['summary', 'charts', 'scoring', 'geographical-areas', 'trends', 'gap', 'points']);
  function readScoringViewState() {
    try {
      const stored = JSON.parse(window.sessionStorage.getItem(scoringViewStorageKey) || 'null');
      if (!stored || typeof stored !== 'object' || Array.isArray(stored)) return {};
      return {
        savedFilterId: typeof stored.saved_filter_id === 'string' && stored.saved_filter_id ? stored.saved_filter_id : null,
        // Close Scoring left no scoring open.
        closed: stored.closed === true,
        // (Tabs saved by earlier versions: Best Network is Scoring Charts, Locations is Geographical Areas.)
        resultTab: stored.result_tab === 'best-network' ? 'charts' : stored.result_tab === 'locations' ? 'geographical-areas'
          : resultTabNames.has(stored.result_tab) ? stored.result_tab : null,
        scrollY: Number.isFinite(stored.scroll_y) && stored.scroll_y >= 0 ? stored.scroll_y : null,
        environment: typeof stored.environment === 'string' && stored.environment ? stored.environment : 'all',
        scoring: stored.scoring === 'most_reliable' ? 'most_reliable' : 'best_network',
        showKpiValues: stored.show_kpi_values === true,
        showGapValues: stored.show_gap_values === true,
        gapLayout: ['end', 'adjacent'].includes(stored.gap_layout) ? stored.gap_layout : 'end',
        nrLayout: stored.nr_layout === 'grouped' ? 'grouped' : 'interleaved',
        // NSA and SA share the charts by default (nr_charts of earlier versions kept the former default, separate).
        nrCharts: stored.nr_charts_view === 'separate' ? 'separate' : 'same',
        gapComparisons: stored.gap_comparisons && typeof stored.gap_comparisons === 'object'
          && !Array.isArray(stored.gap_comparisons)
          ? Object.fromEntries(Object.entries(stored.gap_comparisons).filter(([, value]) => (
            value === 'all' || (typeof value === 'string' && value.startsWith('operator:')
              && value.length > 'operator:'.length)
          ))) : {},
        insightSelections: stored.insight_selections && typeof stored.insight_selections === 'object'
          && !Array.isArray(stored.insight_selections)
          ? Object.fromEntries(Object.entries(stored.insight_selections).filter(([, value]) => typeof value === 'string')) : {},
      };
    } catch (_error) {
      return {};
    }
  }
  const restoredScoringViewState = readScoringViewState();
  // A section chosen in a menu (#section-… or a Scoring Results tab) opens the page there instead, and only a reload (or
  // Back and Forward) returns to the saved position: opening the module starts at its top.
  let scoringViewScrollRestorePending = Number.isFinite(restoredScoringViewState.scrollY) && !window.location.hash
    && ['reload', 'back_forward'].includes(window.performance.getEntriesByType?.('navigation')?.[0]?.type);
  let scoringViewScrollRestoreStarted = false;
  let scoringViewScrollRestoring = false;
  // The page restores its own position, once its results are drawn.
  if (scoringViewScrollRestorePending && 'scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
  let scoringViewSaveTimer = null;
  function persistScoringViewState() {
    try {
      window.sessionStorage.setItem(scoringViewStorageKey, JSON.stringify({
        saved_filter_id: selectedSavedFilterId,
        closed: typeof scoringClosed !== 'undefined' && scoringClosed,
        result_tab: activeResultTab,
        // While the saved position is restored, the page is still growing: keep the saved one.
        scroll_y: typeof scoringViewScrollRestoring !== 'undefined' && (scoringViewScrollRestorePending || scoringViewScrollRestoring)
          ? restoredScoringViewState.scrollY : window.scrollY,
        environment: selectedEnvironment,
        scoring: typeof selectedScoring === 'undefined' ? 'best_network' : selectedScoring,
        show_kpi_values: Boolean(showKpiValuesToggle?.checked),
        show_gap_values: showGapValues(),
        gap_layout: selectedGapLayout(),
        nr_layout: typeof selectedNrLayout === 'undefined' ? 'interleaved' : selectedNrLayout,
        nr_charts_view: typeof selectedNrCharts === 'undefined' ? 'same' : selectedNrCharts,
        gap_comparisons: typeof gapComparisonSelections === 'undefined'
          ? {} : Object.fromEntries(gapComparisonSelections),
        // Location, operators and analysis of the KPI GAP Profile and Points Lost Map, and the other insight selectors.
        insight_selections: typeof insightSelections === 'undefined' ? {} : Object.fromEntries(insightSelections),
      }));
    } catch (_error) {
      // View state is optional when browser session storage is unavailable.
    }
  }
  function restoreScoringViewScroll() {
    if (!scoringViewScrollRestorePending || scoringViewScrollRestoreStarted) return;
    scoringViewScrollRestoreStarted = true;
    scoringViewScrollRestorePending = false;
    const target = restoredScoringViewState.scrollY;
    scoringViewScrollRestoring = true;
    // The maps are drawn a moment after the results: the page is followed as it grows (page_restore.js).
    window.PageRestore.follow(target, {onDone: () => {
      scoringViewScrollRestoring = false;
      persistScoringViewState();
    }});
  }
  window.addEventListener('scroll', () => {
    if (scoringViewSaveTimer !== null) window.clearTimeout(scoringViewSaveTimer);
    scoringViewSaveTimer = window.setTimeout(() => {
      scoringViewSaveTimer = null;
      persistScoringViewState();
    }, 120);
  }, {passive: true});
  window.addEventListener('pagehide', persistScoringViewState);

  // The tab bar of the results stays at the top while they are scrolled (scoring.html), and so does the bar of Select all
  // to Delete while the Favourites Filters are: marked then, to draw them with the colour of the panel behind them.
  const resultTabsBar = root.querySelector('.scoring-result-tabs');
  const stickyBars = [resultTabsBar, root.querySelector('[data-saved-filters-bulk]')].filter(Boolean);
  let resultTabsFrame = 0;
  function syncResultTabsStuck() {
    resultTabsFrame = 0;
    for (const bar of stickyBars) {
      const top = parseFloat(getComputedStyle(bar).top) || 0;
      const box = bar.getBoundingClientRect();
      const start = bar.parentElement.getBoundingClientRect().top;
      bar.classList.toggle('is-stuck', box.height > 0 && start < top - 1 && box.top <= top + 1);
    }
  }
  window.addEventListener('scroll', () => {
    if (!resultTabsFrame) resultTabsFrame = window.requestAnimationFrame(syncResultTabsStuck);
  }, {passive: true});

  // What is in view when the page is left, shown dimmed while a reload returns there (page_restore.js); not while the page
  // is still returning to a saved position.
  window.addEventListener('pagehide', () => window.PageRestore.keepSnapshot(scoringViewStorageKey,
    scoringViewScrollRestorePending || scoringViewScrollRestoring));
  const nrFilter = root.querySelector('[data-nr-filter]');
  // The NR Mode that scores the NSA and SA CDRs side by side.
  const nsaVsSa = 'NSA+SA';
  const datasetOptions = [...root.querySelectorAll('[data-dataset-option]')];
  const datasetInputs = [...root.querySelectorAll('[data-dataset-id]')];
  const datasetKindOrder = ['data', 'voice', 'speech'];
  const datasetKindLabels = {data: 'Data', voice: 'Voice', speech: 'Speech'};
  // NR Mode and Campaign choose the CDRs of the calculation: the server answers with them (those the combined CDR
  // tables include for the campaigns) and with the values each context filter offers among every CDR of the NR
  // Mode, each filter those the other filters leave. A Saved Filter opened in the panel keeps its own CDRs until
  // the NR Mode or a filter changes.
  const autoCdrsUrl = root.dataset.cdrSelectionUrl || '/api/scoring/cdr-selection';
  const autoCdrSection = root.querySelector('[data-scoring-auto-cdrs]');
  const autoCdrSource = root.querySelector('[data-auto-cdrs-source]');
  const autoCdrReset = root.querySelector('[data-auto-cdrs-reset]');
  // Each type of the CDRs used shows four CDRs before it scrolls (three in the other modules), whatever lines their names
  // take, and is only as tall as fewer ones: measured whenever the CDRs are drawn again or the panel changes width.
  const autoCdrGroups = root.querySelector('[data-auto-cdr-groups]');
  function fitAutoCdrLists() {
    for (const list of autoCdrGroups?.querySelectorAll('.auto-cdr-list') || []) {
      const items = [...list.children].filter(item => item.getClientRects().length);
      if (items.length <= 4) {
        list.style.maxHeight = 'none';
        continue;
      }
      const bottom = items[3].getBoundingClientRect().bottom - list.getBoundingClientRect().top + list.scrollTop;
      if (bottom > 0) list.style.maxHeight = `${Math.ceil(bottom) + 2}px`;
    }
  }
  if (autoCdrGroups) {
    if (typeof MutationObserver === 'function') new MutationObserver(fitAutoCdrLists).observe(autoCdrGroups, {childList: true, subtree: true});
    if (typeof ResizeObserver === 'function') new ResizeObserver(fitAutoCdrLists).observe(autoCdrGroups);
  }
  let autoCdrs = {options: null, incomplete: []};
  // The filter values of a selection restored (a Saved Filter used or edited, or an edit cancelled), kept in the lists until
  // the CDRs and the lists of its NR Mode and filters arrive: until then the lists still belong to the selection before
  // it (or are empty), and its values, its automatic Campaign choice included, would be lost and saved without them.
  let restoredContextValues = null;
  let pinnedCdrs = false;
  let autoCdrRevision = 0;
  let autoCdrTimer = null;
  const scoringConfigElement = root.querySelector('[data-scoring-config]');
  const scoringProfileSelect = root.querySelector('[data-scoring-profile]');
  let scoringConfig = {};
  try {
    scoringConfig = JSON.parse(scoringConfigElement?.textContent || '{}');
  } catch {
    scoringConfig = {};
  }
  const defaultHierarchy = ['Operator', 'Vendor', 'Region', 'Cluster', 'City', 'Campaign'];
  const catalogueKeyByLevel = new Map([
    ['Operator', 'operators'], ['Vendor', 'vendors'], ['Region', 'regions'], ['Cluster', 'clusters'],
    ['City', 'cities'], ['Campaign', 'campaigns'],
  ]);
  // Hierarchies saved before Cluster existed get it right after Region.
  const completeHierarchy = hierarchy => (hierarchy.includes('Cluster') ? hierarchy
    : hierarchy.flatMap(level => (level === 'Region' ? ['Region', 'Cluster'] : [level])));
  const validHierarchy = hierarchy => {
    const levels = Array.isArray(hierarchy) ? completeHierarchy(hierarchy.map(String)) : [];
    return levels.length === defaultHierarchy.length && new Set(levels).size === defaultHierarchy.length
      && levels.every(level => catalogueKeyByLevel.has(level)) ? levels : null;
  };
  const scoringProfiles = (Array.isArray(scoringConfig.scoring_profiles) ? scoringConfig.scoring_profiles : [])
    .filter(profile => profile && typeof profile.id === 'string' && typeof profile.name === 'string');
  const scoringProfileById = new Map(scoringProfiles.map(profile => [profile.id, profile]));
  // By campaign: each campaign scored with the methodology whose campaigns include it.
  if (scoringProfiles.length) scoringProfileById.set('by-campaign', {id: 'by-campaign', name: 'each campaign with its methodology'});
  const activeProfileId = String(scoringConfig.active_profile_id || '');
  // The aggregation hierarchy is an application setting shared by every workspace and methodology.
  let currentHierarchy = [...(validHierarchy(scoringConfig.aggregation_hierarchy) || defaultHierarchy)];
  // Operator_Vendor and Vendor_Operator precede Vendor; they filter but are not aggregation levels.
  const filterCatalogueKeys = new Map([...catalogueKeyByLevel, ['Operator_Vendor', 'operator_vendors'], ['Vendor_Operator', 'vendor_operators']]);
  const contextFilterKeys = hierarchy => hierarchy.flatMap(key => (key === 'Vendor' ? ['Operator_Vendor', 'Vendor_Operator', 'Vendor'] : [key]));
  let contextFilterDefinitions = contextFilterKeys(currentHierarchy)
    .map(key => ({key, catalogueKey: filterCatalogueKeys.get(key)}));
  const contextFilterSelects = new Map(contextFilterDefinitions.map(({key}) => [
    key, root.querySelector(`[data-scoring-context-filter="${key}"]`),
  ]));
  const mainCities = [...new Set((Array.isArray(scoringConfig.main_cities) ? scoringConfig.main_cities : [])
    .map(value => String(value ?? '').trim()).filter(Boolean))];
  const mainCityIdentities = new Set(mainCities.map(city => city.toLocaleLowerCase()));
  const operatorGroups = (Array.isArray(scoringConfig.operator_groups) ? scoringConfig.operator_groups : [])
    .filter(group => group && typeof group === 'object' && String(group.canonical || '').trim());
  // The Focus operators of the workspace: the labels with the Focus role in the Operator Maps and the names of the CDRs
  // they stand for. The PowerPoint and Word focus on them in Where to act, the locations ranked, the individual GAP
  // tables, the GAP by part, the KPI GAP Profile and the Points Lost views; the page shows every operator, them first.
  const focusOperatorNames = operatorGroups.filter(group => String(group.role || '').toLocaleLowerCase() === 'focus')
    .flatMap(operatorGroupLabels);
  const datasetCatalogues = new Map(datasetOptions.map(option => {
    let catalogue = {};
    try {
      catalogue = JSON.parse(option.dataset.catalogue || '{}');
    } catch {
      catalogue = {};
    }
    return [String(option.querySelector('[data-dataset-id]')?.value || ''), catalogue];
  }));
  const aggregationInputs = [...root.querySelectorAll('[data-aggregation-level]')];
  const aggregationInputByLevel = new Map(aggregationInputs.map(input => [input.value, input]));
  const contextFilterGrid = root.querySelector('[data-scoring-context-filters]');
  const aggregationLevelsContainer = root.querySelector('[data-aggregation-levels]');
  const baselineInput = root.querySelector('[data-baseline-operator]');
  const calculateButton = root.querySelector('[data-calculate-scoring]');
  const recalculateButton = root.querySelector('[data-recalculate-scoring]');
  const calculationPanel = root.querySelector('.scoring-controls');
  // A Saved Filter edited from its pencil: the panel, moved into a dialog, shows its selection with automatic CDRs, and
  // Save Changes gives it the selection of the panel.
  const editDialog = root.querySelector('[data-saved-filter-edit-dialog]');
  const editBanner = root.querySelector('[data-saved-filter-editing]');
  const editTitle = root.querySelector('[data-saved-filter-editing-title]');
  const editText = root.querySelector('[data-saved-filter-editing-text]');
  const editTextDefault = editText?.textContent || '';
  const editSaveButton = root.querySelector('[data-saved-filter-edit-save]');
  const editSaveLabel = editSaveButton?.querySelector('span') || null;
  const editCancelButton = root.querySelector('[data-saved-filter-edit-cancel]');
  const closeScoringButton = root.querySelector('[data-close-scoring]');
  let editingSavedFilter = null;
  // The selection of the panel before the editing (given back when it is cancelled) and the place of the panel.
  let selectionBeforeEdit = null;
  let editPanelPlaceholder = null;
  // The Geographical Areas & Scoring Trends of the calculation, always included: the Breakdown and Separate cities of both
  // tabs, and the time split and campaigns of the trends.
  const areaSummaryPanel = root.querySelector('[data-scoring-area-summary]');
  // Main Cities among the Separate cities: kept as such and resolved when the scoring is calculated.
  const MAIN_CITIES_TOKEN = '@main-cities';
  const MAIN_CITIES_LABEL = 'Main Cities';
  const areaSummaryTimeSplit = root.querySelector('[data-scoring-area-time-split]');
  const areaSummaryBreakdown = root.querySelector('[data-scoring-area-breakdown]');
  const areaSummaryCities = root.querySelector('[data-scoring-area-cities]');
  // The campaigns of the Scoring Trends tab, whatever the Campaign filter of the rest of the scoring.
  const trendCampaigns = root.querySelector('[data-scoring-trend-campaigns]');
  const message = root.querySelector('[data-scoring-message]');
  const savedFilterLists = [...root.querySelectorAll('[data-saved-filter-list]')];
  const savedFilterPanelList = savedFilterLists.find(list => list.closest('.saved-filters-panel')) || null;
  const canReorderSavedFilters = document.body.dataset.authenticatedRole !== 'user-viewer';
  let draggedSavedFilterRow = null;
  // The Saved Filters checked in the Saved Filters panel, to update them together with Use newer CDRs or delete them.
  const checkedSavedFilterIds = new Set();
  const savedFiltersBulk = root.querySelector('[data-saved-filters-bulk]');
  const savedFiltersSelectAll = root.querySelector('[data-saved-filters-select-all]');
  const savedFiltersUseNewer = root.querySelector('[data-saved-filters-use-newer]');
  const savedFiltersDelete = root.querySelector('[data-saved-filters-delete]');
  const savedFiltersMove = [...root.querySelectorAll('[data-saved-filters-move]')];
  // The orders of the Saved Filters are saved one after the other, so the last move is the one kept.
  let savedFilterOrderRequest = Promise.resolve();
  let updatingSavedFiltersCdrs = false;
  let deletingCheckedSavedFilters = false;
  let savedFiltersRenderPending = false;
  const savedFilterList = savedFilterLists[0];
  // The Saved Filter selectors of the module, on top of the Calculation panel and of Scoring & GAP Results: the selected
  // card of the first one is drawn and the others are its copies.
  const savedFilterSelectors = [...root.querySelectorAll('[data-saved-filter-selector]')];
  // The Filter Navigator: the Favourites Filters as a tree (Area → NR Mode → Campaign) with a search, opened from the
  // Favourites Filters panel and from the button of each selector. The branches opened stay open while the page is open;
  // while searching, every branch with a match is open but the ones closed meanwhile.
  const navigatorDialog = root.querySelector('[data-saved-filter-navigator]');
  const navigatorTree = navigatorDialog?.querySelector('[data-saved-filter-navigator-tree]') || null;
  const navigatorSearch = navigatorDialog?.querySelector('[data-saved-filter-navigator-search]') || null;
  const navigatorCount = navigatorDialog?.querySelector('[data-saved-filter-navigator-count]') || null;
  const navigatorExpanded = new Set();
  const navigatorSearchCollapsed = new Set();
  // The selector the Filter Navigator was opened from (null: the Favourites Filters panel).
  let navigatorOrigin = null;
  const selectedSavedFilterCards = [...root.querySelectorAll('[data-selected-saved-filter-card]')];
  const selectedSavedFilterCard = selectedSavedFilterCards[0];
  const resultsTabbed = root.querySelector('.scoring-results-tabbed');
  const resultNotesStack = root.querySelector('.scoring-notes-stack');
  const environmentControl = root.querySelector('[data-result-environment-control]');
  const environmentSelect = root.querySelector('[data-result-environment]');
  const scoringKindControl = root.querySelector('[data-result-scoring-control]');
  // NSA vs SA: each panel of NSA then the same panel of SA (interleaved), or every panel of NSA then every one of SA.
  const nrLayoutControl = root.querySelector('[data-result-nr-layout-control]');
  const nrLayoutSelect = root.querySelector('[data-result-nr-layout]');
  // NSA vs SA: the Scoring Charts and Scoring Trends of each NR Mode apart (separate charts) or together (the same chart).
  const nrChartsControl = root.querySelector('[data-result-nr-charts-control]');
  const nrChartsSelect = root.querySelector('[data-result-nr-charts]');
  const scoringKindSelect = root.querySelector('[data-result-scoring]');
  const chartPane = root.querySelector('[data-result-pane="charts"]');
  const chartOverlay = root.querySelector('[data-scoring-chart-overlay]');
  const chartDialog = root.querySelector('[data-scoring-chart-dialog]');
  const expandedChart = root.querySelector('[data-scoring-expanded-chart]');
  const expandedChartTitle = root.querySelector('[data-scoring-chart-title]');
  const expandedChartMeta = root.querySelector('[data-scoring-chart-meta]');
  const expandedChartClose = root.querySelector('[data-scoring-chart-close]');
  const showKpiValuesToggle = root.querySelector('[data-show-kpi-values]');
  const showGapValuesToggle = root.querySelector('[data-show-gap-values]');
  const gapLayoutSelect = root.querySelector('[data-scoring-gap-layout]');
  const gapLayoutControl = root.querySelector('[data-scoring-gap-layout-control]');
  if (showKpiValuesToggle) showKpiValuesToggle.checked = restoredScoringViewState.showKpiValues === true;
  if (showGapValuesToggle) showGapValuesToggle.checked = restoredScoringViewState.showGapValues === true;
  if (gapLayoutSelect) gapLayoutSelect.value = restoredScoringViewState.gapLayout || 'end';
  const resultPanes = [...root.querySelectorAll('[data-result-pane]')];
  const resultCache = new Map();
  const contextSelections = new Map();
  const gapComparisonSelections = new Map(Object.entries(restoredScoringViewState.gapComparisons || {}));
  const scoringValueObservers = new Map();
  const deletedSavedFilterIds = new Set();
  const deletingSavedFilterIds = new Set();
  let savedFilters = [];
  let calculationMatchKey = '';
  // Set by the Saved Filter polling: check the same selection again without disabling the buttons meanwhile.
  let calculationMatchRefresh = false;
  // A check of the selection is on its way; a refresh meanwhile waits for its answer and checks again after it.
  let calculationMatchPending = false;
  let calculationMatchRecheck = false;
  // The selection of the Calculation panel is no Saved Filter: the results of the opened one are not shown with it.
  let selectionUnmatched = false;
  // The name of the copy while a Saved Filter is duplicated (null while it is edited, or neither).
  let duplicateName = null;
  // Close Scoring: no Saved Filter is open (none opens on its own) until one is opened or calculated.
  let scoringClosed = Boolean(restoredScoringViewState.closed) && !requestedSavedFilterId;
  // The status of the selected CDRs and filters (calculating, recalculating, already calculated or ready) stays
  // while the Saved Filter list refreshes every few seconds; Saved Filters submitted with Recalculate say so.
  let selectionStatus = {key: '', text: '', kind: ''};
  const recalculatingSavedFilters = new Set();
  let calculationMatchRevision = 0;
  let calculationMatchTimer = null;
  let submittingCalculation = false;
  let selectedSavedFilterId = restoredScoringViewState.savedFilterId;
  let selectedSavedFilter = null;
  // Whether the selected card of the Scoring Results dropdown shows every detail (Details); folded at first.
  let selectedSavedFilterUnfolded = false;
  let selectedEnvironment = restoredScoringViewState.environment || 'all';
  // Best Network or Most Reliable: both scorings share the Saved Filter, its filters and its aggregation.
  let selectedScoring = restoredScoringViewState.scoring || 'best_network';
  let selectedNrLayout = restoredScoringViewState.nrLayout || 'interleaved';
  if (nrLayoutSelect) nrLayoutSelect.value = selectedNrLayout;
  let selectedNrCharts = restoredScoringViewState.nrCharts || 'same';
  if (nrChartsSelect) nrChartsSelect.value = selectedNrCharts;
  let currentEffectiveEnvironment = null;
  let environmentDefaultSavedFilterId = null;
  let currentResults = null;
  let currentResultsSavedFilterId = null;
  // The filters of the Saved Filter whose results are shown, for the area, operators and vendors in the chart and
  // table titles.
  let resultScopeFilters = {};
  // Reloading the page keeps the selected results tab; opening the page again
  // from another page always starts on Summary.
  const pageReloaded = (() => {
    try { return performance.getEntriesByType('navigation')[0]?.type === 'reload'; } catch { return false; }
  })();
  let activeResultTab = (pageReloaded && restoredScoringViewState.resultTab) || 'summary';
  // Insight selections (such as the KPI GAP Profile and Points Lost Map location and operators) are kept
  // when the page is reloaded; opening the page again starts from the defaults.
  const insightSelections = new Map(pageReloaded ? Object.entries(restoredScoringViewState.insightSelections || {}) : []);
  const showResultTab = name => {
    activeResultTab = name;
    for (const tab of root.querySelectorAll('[data-result-tab]')) {
      const selected = tab.dataset.resultTab === name;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    }
    for (const pane of root.querySelectorAll('[data-result-pane]')) pane.hidden = pane.dataset.resultPane !== name;
  };
  showResultTab(activeResultTab);
  let chartFocusReturn = null;
  let previousBodyOverflow = '';
  let userSelectedSavedFilter = Boolean(selectedSavedFilterId);
  let refreshInFlight = false;
  let timer = null;
  // Opening a Saved Filter whose CDRs or methodology changed queues it again. A list of Saved Filters requested before
  // that answer still reads it completed: the calculating state it answered is kept over such a list, so its old result
  // is not shown and its progress keeps being followed.
  let savedFilterRequests = 0;
  const calculatingSavedFilters = new Map();
  let selectionLoaded = false;
  let selectionPersisted = false;
  let selectionDirty = false;
  let restoringSelection = false;
  let selectionSaveTimer = null;
  let selectionRevision = 0;
  let lastSavedSelectionKey = '';
  let lastQueuedSelectionKey = '';
  let selectionSaveChain = Promise.resolve();
  const selectionClientId = window.crypto?.randomUUID?.()
    || `scoring-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const selectionFieldOrder = ['Region', 'City', 'Operator', 'Vendor', 'Campaign'];

  const valueOf = (object, keys, fallback = '') => {
    if (!object || typeof object !== 'object') return fallback;
    for (const key of keys) {
      if (object[key] !== undefined && object[key] !== null && object[key] !== '') return object[key];
    }
    return fallback;
  };
  const savedFilterIdOf = savedFilter => String(valueOf(savedFilter, ['id'], ''));
  const normalizeStatus = savedFilter => {
    const raw = String(valueOf(savedFilter, ['status', 'state'], 'queued')).toLowerCase();
    if (['done', 'success', 'succeeded', 'complete', 'completed', 'finished', 'ready'].includes(raw)) return 'completed';
    if (['error', 'failure', 'failed', 'cancelled', 'canceled', 'stopped'].includes(raw)) return 'failed';
    if (['processing', 'running', 'in_progress', 'in-progress'].includes(raw)) return 'processing';
    if (['queued', 'pending', 'created'].includes(raw)) return 'queued';
    return raw.replaceAll('_', ' ') || 'queued';
  };
  const isActive = savedFilter => ['queued', 'processing'].includes(normalizeStatus(savedFilter));
  const isComplete = savedFilter => normalizeStatus(savedFilter) === 'completed';
  const selectedLevels = () => currentHierarchy.filter(level => aggregationInputByLevel.get(level)?.checked);
  const selectedDatasetIds = () => datasetInputs.filter(input => input.checked && !input.closest('[data-dataset-option]')?.hidden).map(input => input.value);

  function uniqueCatalogueValues(values) {
    return [...new Set((Array.isArray(values) ? values : [])
      .map(value => String(value ?? '').trim()).filter(Boolean))];
  }

  function operatorGroupLabels(group) {
    const canonical = String(group.canonical || '').trim();
    return [canonical, ...(Array.isArray(group.aliases) ? group.aliases : [])]
      .map(value => String(value ?? '').trim()).filter(Boolean);
  }

  function canonicalOperatorName(value) {
    const raw = String(value ?? '').trim();
    const identity = raw.toLocaleLowerCase();
    const group = operatorGroups.find(item => operatorGroupLabels(item).some(alias => alias.toLocaleLowerCase() === identity));
    return group ? String(group.canonical).trim() : raw;
  }

  function scoringVendorName(value) {
    const raw = String(value ?? '').replace(/\s+- All(?: Vendors)?$/i, '').trim();
    const operators = uniqueCatalogueValues([
      ...operatorGroups.flatMap(operatorGroupLabels),
      ...[...datasetCatalogues.values()].flatMap(catalogue => catalogue.operators || []),
    ]).sort((left, right) => right.length - left.length);
    if (operators.some(operator => operator.toLocaleLowerCase() === raw.toLocaleLowerCase())) return raw;
    const prefix = operators.find(operator => raw.toLocaleLowerCase().startsWith(`${operator.toLocaleLowerCase()}_`));
    return prefix ? raw.slice(prefix.length + 1) : raw;
  }

  function contextFilterOptions(key, catalogueValues) {
    if (key === 'Vendor' || key === 'Operator_Vendor' || key === 'Vendor_Operator') {
      return (window.vendorOnlyFilterChoices?.(key, catalogueValues) || catalogueValues.map(value => ({value, label: value})))
        .map(choice => ({...choice, color: ''}));
    }
    if (key === 'Campaign') {
      // Shown as everywhere (2026-Q2-SA) and in chronological order; the filter keeps the full value.
      return catalogueValues.map(value => ({value, label: hierarchyDisplayValue({level: 'Campaign', value}), color: ''}))
        .sort((left, right) => insightCampaignKey(left.value) - insightCampaignKey(right.value) || left.label.localeCompare(right.label));
    }
    if (key !== 'Operator') {
      return catalogueValues.map(value => ({value, label: value, color: ''}))
        .sort((left, right) => left.label.localeCompare(right.label, undefined, {sensitivity: 'base'}));
    }
    const availableByIdentity = new Map(catalogueValues.map(value => [value.toLocaleLowerCase(), value]));
    const mapped = new Set();
    const options = [];
    for (const group of operatorGroups) {
      const canonical = String(group.canonical || '').trim();
      const aliases = operatorGroupLabels(group);
      const matches = aliases.some(alias => availableByIdentity.has(alias.toLocaleLowerCase()));
      if (!matches) continue;
      aliases.forEach(alias => mapped.add(alias.toLocaleLowerCase()));
      options.push({value: canonical, label: canonical, color: String(group.color || '')});
    }
    const unknown = catalogueValues.filter(value => !mapped.has(value.toLocaleLowerCase()))
      .map(value => ({value, label: value, color: ''}))
      .sort((left, right) => left.label.localeCompare(right.label, undefined, {sensitivity: 'base'}));
    return [...options, ...unknown];
  }

  function decorateOperatorOptions(select) {
    const shell = select?.nextElementSibling;
    if (!shell?.matches('.multiselect-shell')) return;
    for (const label of shell.querySelectorAll('.multiselect-option')) {
      const value = label.querySelector('[data-option-value]')?.getAttribute('data-option-value');
      const option = [...(select.options || [])].find(item => item.value === value);
      const color = option?.dataset.operatorColor || '';
      label.classList.toggle('scoring-operator-option', Boolean(color));
      if (color) label.style.setProperty('--scoring-operator-color', color);
      else label.style.removeProperty('--scoring-operator-color');
    }
  }

  // Latest campaign, Latest 2, 3 and 4 campaigns, Previous campaign (the one before the latest) and All available
  // campaigns, first in Campaign: each stands alone and stands for campaigns with Data, Voice and Speech CDRs; the panel
  // keeps the choice and a calculation uses its campaigns.
  const campaignPresetLabels = {'@latest-campaign': 'Latest campaign', '@latest-2-campaigns': 'Latest 2 campaigns',
    '@latest-3-campaigns': 'Latest 3 campaigns', '@latest-4-campaigns': 'Latest 4 campaigns',
    '@previous-campaign': 'Previous campaign', '@all-campaigns': 'All available campaigns'};
  const isCampaignPreset = value => Object.prototype.hasOwnProperty.call(campaignPresetLabels, value);
  const chosenCampaignPreset = select => [...(select?.selectedOptions || [])].map(option => option.value).find(isCampaignPreset) || '';

  function refreshContextFilterOptions() {
    const selectedIds = new Set(selectedDatasetIds());
    for (const {key, catalogueKey} of contextFilterDefinitions) {
      const select = contextFilterSelects.get(key);
      if (!select) continue;
      const identity = value => key === 'Vendor' ? scoringVendorName(value) : value;
      const restored = restoredContextValues?.get(key) || [];
      const restoredValues = restored.filter(value => !isCampaignPreset(value));
      const preset = key === 'Campaign' ? (chosenCampaignPreset(select) || restored.find(isCampaignPreset) || '') : '';
      const selectedValues = new Set([...select.selectedOptions].map(option => identity(option.value)).filter(value => value && !isCampaignPreset(value)));
      restoredValues.forEach(value => selectedValues.add(identity(value)));
      // Values chosen while they were in the CDRs (another NR Mode or CDR choice) come back with them.
      let remembered = [];
      try { remembered = JSON.parse(select.dataset.scoringRememberedValues || '[]'); } catch (_error) { remembered = []; }
      remembered.forEach(value => selectedValues.add(value));
      // Every value checked (All values) keeps every value checked, also the values the new CDRs add; a list made with the
      // values of a restored selection holds only them, so they are not every value.
      const enabledBefore = [...select.options].filter(option => !option.disabled && option.value && !isCampaignPreset(option.value));
      const allSelected = !preset && !restored.length && !select.dataset.scoringRestoredList && enabledBefore.length > 0
        && enabledBefore.every(option => option.selected);
      if (restored.length) select.dataset.scoringRestoredList = 'true';
      else delete select.dataset.scoringRestoredList;
      const rawValues = [];
      if (autoCdrs.options && Array.isArray(autoCdrs.options[key])) {
        rawValues.push(...uniqueCatalogueValues(autoCdrs.options[key]));
      } else {
        for (const datasetId of selectedIds) {
          const values = datasetCatalogues.get(String(datasetId))?.[catalogueKey];
          rawValues.push(...uniqueCatalogueValues(values));
        }
      }
      const nextOptions = contextFilterOptions(key, [...new Set([...rawValues, ...restoredValues])]);
      const presetCities = key === 'City'
        ? nextOptions.filter(option => mainCityIdentities.has(option.value.trim().toLocaleLowerCase())).map(option => option.value) : [];
      const signature = JSON.stringify({
        options: nextOptions.map(option => [option.value, option.label, option.color]),
        presetCities, preset,
      });
      if (select.dataset.scoringCatalogueSignature === signature) continue;
      select.dataset.scoringCatalogueSignature = signature;
      if (key === 'City') {
        select.dataset.multiselectPresetLabel = 'Main Cities';
        select.dataset.multiselectPresetValues = presetCities.join('|');
      }
      select.replaceChildren();
      if (!nextOptions.length && !(preset && restored.length)) {
        const empty = document.createElement('option');
        empty.value = '';
        empty.disabled = true;
        empty.textContent = 'No values';
        select.append(empty);
      } else {
        if (key === 'Campaign') {
          for (const [value, label] of Object.entries(campaignPresetLabels)) {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            option.selected = value === preset;
            option.dataset.campaignPreset = 'true';
            option.dataset.optionClass = 'campaign-preset';
            select.append(option);
          }
        }
        for (const [index, entry] of nextOptions.entries()) {
          const option = document.createElement('option');
          option.value = entry.value;
          option.textContent = entry.label;
          option.selected = !preset && (allSelected || selectedValues.has(identity(entry.value)));
          if (key === 'Campaign' && index === 0) option.dataset.dividerBefore = 'true';
          if (entry.color) {
            option.dataset.operatorColor = entry.color;
            option.style.color = entry.color;
          }
          select.append(option);
        }
      }
      const available = new Set(nextOptions.map(entry => identity(entry.value)));
      select.dataset.scoringRememberedValues = JSON.stringify(allSelected ? [] : [...selectedValues].filter(value => !available.has(value)));
      select.dispatchEvent(new Event('multiselect:options-updated'));
      if (key === 'Operator') decorateOperatorOptions(select);
    }
    refreshAreaSummaryCities(selectedIds);
    refreshTrendCampaigns();
  }

  // The campaigns of the Scoring Trends are those of the Campaign filter (with its automatic choices), plus those chosen
  // before.
  function refreshTrendCampaigns() {
    const campaignSelect = contextFilterSelects.get('Campaign');
    if (!trendCampaigns || !campaignSelect) return;
    const chosen = [...trendCampaigns.selectedOptions].map(option => option.value).filter(Boolean);
    const options = [...campaignSelect.options].filter(option => option.value && !isCampaignPreset(option.value))
      .map(option => [option.value, option.textContent]);
    const known = new Set(options.map(([value]) => value.toLocaleLowerCase()));
    chosen.filter(value => !isCampaignPreset(value) && !known.has(value.toLocaleLowerCase()))
      .forEach(value => options.push([value, hierarchyDisplayValue({level: 'Campaign', value})]));
    const signature = JSON.stringify({options, chosen});
    if (trendCampaigns.dataset.scoringCatalogueSignature === signature) return;
    trendCampaigns.dataset.scoringCatalogueSignature = signature;
    const selected = new Set(chosen.map(value => value.toLocaleLowerCase()));
    const preset = chosen.find(isCampaignPreset) || '';
    const entries = [];
    for (const [value, label] of Object.entries(campaignPresetLabels)) {
      const option = new Option(label, value, false, value === preset);
      option.dataset.campaignPreset = 'true';
      option.dataset.optionClass = 'campaign-preset';
      entries.push(option);
    }
    options.forEach(([value, label], index) => {
      const option = new Option(label, value, false, !preset && selected.has(value.toLocaleLowerCase()));
      if (index === 0) option.dataset.dividerBefore = 'true';
      entries.push(option);
    });
    trendCampaigns.replaceChildren(...entries);
    trendCampaigns.dispatchEvent(new Event('multiselect:options-updated'));
  }

  // An automatic choice (Latest 2 campaigns…) stands alone; empty, the trends follow the Campaign filter.
  function selectedTrendCampaigns() {
    if (!trendCampaigns) return [];
    const preset = chosenCampaignPreset(trendCampaigns);
    return preset ? [preset] : [...trendCampaigns.selectedOptions].map(option => option.value).filter(Boolean);
  }

  function applyTrendCampaigns(values) {
    if (!trendCampaigns) return;
    const campaigns = (Array.isArray(values) ? values : []).map(String).filter(Boolean);
    const known = new Set([...trendCampaigns.options].map(option => option.value.toLocaleLowerCase()));
    for (const value of campaigns) {
      if (!known.has(value.toLocaleLowerCase())) {
        trendCampaigns.append(new Option(campaignPresetLabels[value] || hierarchyDisplayValue({level: 'Campaign', value}), value));
      }
    }
    const wanted = new Set(campaigns.map(value => value.toLocaleLowerCase()));
    for (const option of trendCampaigns.options) option.selected = wanted.has(option.value.toLocaleLowerCase());
    delete trendCampaigns.dataset.scoringCatalogueSignature;
    refreshTrendCampaigns();
    trendCampaigns.dispatchEvent(new Event('multiselect:options-updated'));
  }

  // The separate cities: Main Cities first (kept as such, the Main Cities of the workspace when the scoring is
  // calculated), then the cities of the selected CDRs, plus the cities chosen before.
  function refreshAreaSummaryCities(selectedIds = new Set(selectedDatasetIds())) {
    if (!areaSummaryCities) return;
    const chosen = [...areaSummaryCities.selectedOptions].map(option => option.value).filter(Boolean);
    const catalogueKey = filterCatalogueKeys.get('City');
    const values = [];
    for (const datasetId of selectedIds) values.push(...uniqueCatalogueValues(datasetCatalogues.get(String(datasetId))?.[catalogueKey]));
    const known = new Set([MAIN_CITIES_TOKEN, ...values].map(value => value.toLocaleLowerCase()));
    const options = [MAIN_CITIES_TOKEN, ...contextFilterOptions('City', [...new Set(values)]).map(entry => entry.value),
      ...chosen.filter(value => !known.has(value.toLocaleLowerCase()))];
    const signature = JSON.stringify({options, chosen, disabled: areaSummaryCities.disabled});
    if (areaSummaryCities.dataset.scoringCatalogueSignature === signature) return;
    areaSummaryCities.dataset.scoringCatalogueSignature = signature;
    delete areaSummaryCities.dataset.multiselectPresetLabel;
    delete areaSummaryCities.dataset.multiselectPresetValues;
    const selected = new Set(chosen.map(value => value.toLocaleLowerCase()));
    areaSummaryCities.replaceChildren(...options.map(value => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = value === MAIN_CITIES_TOKEN ? MAIN_CITIES_LABEL : value;
      if (value === MAIN_CITIES_TOKEN) option.title = 'The Main Cities of the workspace each time the scoring is calculated';
      option.selected = selected.has(value.toLocaleLowerCase());
      return option;
    }));
    areaSummaryCities.dispatchEvent(new Event('multiselect:options-updated'));
  }

  function chosenAreaCities() {
    return areaSummaryCities ? [...areaSummaryCities.selectedOptions].map(option => option.value).filter(Boolean) : [];
  }

  function selectedAreaSummary() {
    return {
      enabled: true,
      time_split: String(areaSummaryTimeSplit?.value || 'Campaign'),
      breakdown: String(areaSummaryBreakdown?.value || 'Region'),
      cities: chosenAreaCities().filter(value => value !== MAIN_CITIES_TOKEN),
      main_cities: chosenAreaCities().includes(MAIN_CITIES_TOKEN),
      campaigns: selectedTrendCampaigns(),
    };
  }

  // Without a Breakdown the Separate cities are the only areas: None is offered only with some of them, and the Breakdown
  // goes back to Region when the last one is left out.
  function syncAreaSummary() {
    if (!areaSummaryPanel || !areaSummaryBreakdown) return;
    const cities = areaSummaryCities ? [...areaSummaryCities.selectedOptions].filter(option => option.value).length : 0;
    const none = [...areaSummaryBreakdown.options].find(option => option.value === 'None');
    if (none) {
      none.disabled = !cities;
      none.title = cities ? '' : 'Choose a Separate city first';
    }
    if (!cities && areaSummaryBreakdown.value === 'None') areaSummaryBreakdown.value = 'Region';
  }

  function applyHierarchy(hierarchy) {
    const ordered = validHierarchy(hierarchy);
    if (!ordered) return false;
    const selected = new Set(aggregationInputs.filter(input => input.checked).map(input => input.value));
    currentHierarchy = ordered;
    contextFilterDefinitions = contextFilterKeys(ordered).map(key => ({key, catalogueKey: filterCatalogueKeys.get(key)}));
    for (const {key} of contextFilterDefinitions) {
      if (key === 'Campaign') continue;
      const filterLabel = contextFilterSelects.get(key)?.closest('label');
      if (filterLabel && contextFilterGrid) contextFilterGrid.append(filterLabel);
    }
    for (const level of ordered) {
      const input = aggregationInputByLevel.get(level);
      const levelLabel = input?.closest('label');
      if (levelLabel && aggregationLevelsContainer) aggregationLevelsContainer.append(levelLabel);
      if (input) input.checked = level === 'Operator' || selected.has(level);
    }
    updateSelection();
    return true;
  }

  // The application's aggregation hierarchy is ordered in a dialog of this page.
  const hierarchyDialog = root.querySelector('[data-scoring-hierarchy-dialog]');
  const hierarchyList = hierarchyDialog?.querySelector('[data-scoring-hierarchy-list]');
  const hierarchyStatus = hierarchyDialog?.querySelector('[data-scoring-hierarchy-status]');
  const canEditHierarchy = hierarchyDialog?.dataset.canEdit === 'true';
  let hierarchyDraft = [];

  function renderHierarchyDraft() {
    hierarchyList.replaceChildren(...hierarchyDraft.map((level, index) => {
      const item = document.createElement('li');
      const label = document.createElement('span');
      label.textContent = level === 'Operator' ? 'Operator (required)' : level;
      item.append(label);
      if (canEditHierarchy) {
        for (const [text, offset, title] of [['↑', -1, 'Move up'], ['↓', 1, 'Move down']]) {
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = text;
          button.title = title;
          button.setAttribute('aria-label', `${title}: ${level}`);
          button.disabled = index + offset < 0 || index + offset >= hierarchyDraft.length;
          button.addEventListener('click', () => {
            [hierarchyDraft[index], hierarchyDraft[index + offset]] = [hierarchyDraft[index + offset], hierarchyDraft[index]];
            renderHierarchyDraft();
          });
          item.append(button);
        }
      }
      return item;
    }));
  }

  function openHierarchyDialog() {
    if (!hierarchyDialog) return;
    hierarchyDraft = [...currentHierarchy];
    hierarchyStatus.textContent = '';
    hierarchyStatus.dataset.tone = '';
    renderHierarchyDraft();
    hierarchyDialog.showModal();
  }

  hierarchyDialog?.querySelector('[data-scoring-hierarchy-cancel]')?.addEventListener('click', () => hierarchyDialog.close());
  hierarchyDialog?.querySelector('[data-scoring-hierarchy-form]')?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const save = hierarchyDialog.querySelector('[data-scoring-hierarchy-save]');
    if (!save || !canEditHierarchy) return;
    save.disabled = true;
    try {
      const response = await fetch('/api/scoring/aggregation-hierarchy', {
        method: 'PUT', credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({levels: hierarchyDraft}),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The aggregation hierarchy could not be saved.');
      applyHierarchy(validHierarchy(payload.aggregation_hierarchy) || [...hierarchyDraft]);
      scheduleSelectionSave();
      hierarchyDialog.close();
      setMessage('Aggregation hierarchy saved.', 'success');
    } catch (error) {
      hierarchyStatus.textContent = error.message;
      hierarchyStatus.dataset.tone = 'error';
    } finally {
      save.disabled = false;
    }
  });
  root.querySelector('[data-scoring-hierarchy-open]')?.addEventListener('click', (event) => {
    event.preventDefault();
    openHierarchyDialog();
  });

  // The context filters: a Latest campaign choice as it is (keepPresets, the saved panel) or as its campaigns now
  // (a calculation).
  function selectedContextFilters({keepPresets = false} = {}) {
    return Object.fromEntries(contextFilterDefinitions.map(({key}) => {
      const select = contextFilterSelects.get(key);
      const preset = key === 'Campaign' ? chosenCampaignPreset(select) : '';
      if (preset) return [key, keepPresets ? [preset] : [...(autoCdrs.presets?.[preset] || [])]];
      const values = select ? [...select.selectedOptions]
        .filter(option => !option.disabled && option.value && !isCampaignPreset(option.value))
        .map(option => String(option.value)) : [];
      const available = select ? [...select.options].filter(option => !option.disabled && option.value && !isCampaignPreset(option.value)) : [];
      // Every value checked is no restriction, but for a list made with the values of a restored selection.
      return [key, key !== 'Vendor' && available.length && values.length === available.length && !select.dataset.scoringRestoredList
        ? [] : values];
    }));
  }

  function calculationSelectionFromControls() {
    const levels = [...new Set(selectedLevels())];
    if (!levels.includes('Operator')) levels.unshift('Operator');
    const filters = selectedContextFilters({keepPresets: true});
    return {
      dataset_ids: selectedDatasetIds().map(value => Number(value)).filter(Number.isFinite),
      auto_cdrs: !pinnedCdrs,
      aggregation_levels: levels,
      nr_mode: String(nrFilter?.value || 'NSA'),
      baseline_operator: String(baselineInput?.value || ''),
      scoring_profile_id: String(scoringProfileSelect?.value || activeProfileId),
      context_filters: Object.fromEntries(selectionFieldOrder.map(key => [key, filters[key] || []])),
      area_summary: selectedAreaSummary(),
    };
  }

  // Whether an operator (by its name or label) is a Focus operator, whatever the case (every operator without them, or
  // when none of ``operators`` is one of them).
  function focusMatcher(operators = []) {
    const chosen = globalThis.valuePatterns.set(focusOperatorNames);
    const matches = (...names) => chosen.accepts(...names);
    if (!chosen.size || (operators.length && !operators.some(name => matches(name)))) return () => true;
    return matches;
  }

  // The Focus operators among ``items`` (each with its ``operator`` and ``label``) and the others; none are Focus
  // operators when they are every operator or none of them.
  function focusSplit(items) {
    const isFocus = focusMatcher(items.map(item => item.operator));
    const focused = focusOperatorNames.length ? items.filter(item => isFocus(item.operator, item.label)) : [];
    return focused.length && focused.length < items.length
      ? {focused, others: items.filter(item => !focused.includes(item))} : {focused: [], others: items};
  }

  // The options of a choice of operators ([value, text, operator, label]), the Focus operators first under a Focus operators heading,
  // with a line before the others.
  function appendFocusOptions(select, entries) {
    const option = ([value, text]) => Object.assign(document.createElement('option'), {value, textContent: text});
    const {focused, others} = focusSplit(entries.map(entry => ({operator: entry[2], label: entry[3], entry})));
    if (!focused.length) {
      select.append(...entries.map(option));
      return;
    }
    const focusGroup = Object.assign(document.createElement('optgroup'), {label: 'Focus operators'});
    focusGroup.append(...focused.map(item => option(item.entry)));
    const otherGroup = Object.assign(document.createElement('optgroup'), {label: 'Other operators'});
    otherGroup.dataset.dividerBefore = 'true';
    otherGroup.append(...others.map(item => option(item.entry)));
    select.append(focusGroup, otherGroup);
  }

  // The chips of a choice of operators in two subpanels: the Focus operators above, under their Focus operators label,
  // and the others below, under an Other operators label of another colour.
  function appendFocusChips(group, operators, makeChip) {
    const {focused, others} = focusSplit(operators);
    if (!focused.length) {
      group.append(...operators.map(makeChip));
      return;
    }
    group.classList.add('has-focus-operators');
    const subpanel = (kind, label, items) => {
      const panel = document.createElement('div');
      panel.className = `scoring-${kind}-operators`;
      const chips = document.createElement('span');
      chips.className = 'scoring-operator-chips';
      chips.append(...items.map(makeChip));
      panel.append(Object.assign(document.createElement('span'), {className: `scoring-${kind}-tag`, textContent: label}), chips);
      return panel;
    };
    group.append(subpanel('focus', 'Focus operators', focused), subpanel('other', 'Other operators', others));
  }

  // The operators the buttons of a section start with: its Focus operators, else every operator.
  function focusChosen(operators) {
    const {focused} = focusSplit(operators);
    return (focused.length ? focused : operators).map(item => item.operator);
  }

  // The operators a choice of the sections the Focus operators choose starts with: the Focus operators (else every
  // operator but the reference, else every operator).
  function focusDefault(operators, {withReference = false} = {}) {
    const {focused} = focusSplit(operators);
    const candidates = withReference ? operators : operators.filter(item => !item.is_reference);
    const chosen = focused.filter(item => withReference || !item.is_reference);
    return (chosen.length ? chosen : candidates.length ? candidates : operators).map(item => item.operator);
  }

  function calculationSelectionKey(selection) {
    const filters = selection?.context_filters && typeof selection.context_filters === 'object'
      ? selection.context_filters : {};
    const normalizedFilters = Object.fromEntries(selectionFieldOrder.map(key => [key,
      uniqueCatalogueValues(filters[key] ?? filters[key.toLowerCase()] ?? [])
        .sort((left, right) => left.localeCompare(right, undefined, {sensitivity: 'base'})),
    ]));
    return JSON.stringify({
      dataset_ids: (Array.isArray(selection?.dataset_ids) ? selection.dataset_ids : []).map(String).sort((left, right) => Number(left) - Number(right)),
      aggregation_levels: Array.isArray(selection?.aggregation_levels) ? selection.aggregation_levels.map(String) : [],
      nr_mode: String(selection?.nr_mode || ''),
      baseline_operator: String(selection?.baseline_operator || ''),
      scoring_profile_id: String(selection?.scoring_profile_id || ''),
      context_filters: normalizedFilters,
      area_summary: (({enabled, time_split: timeSplit, breakdown, cities, campaigns} = {}) => ({
        enabled: Boolean(enabled), time_split: String(timeSplit || 'Campaign'), breakdown: String(breakdown || 'Region'),
        cities: (Array.isArray(cities) ? cities : []).map(String), campaigns: (Array.isArray(campaigns) ? campaigns : []).map(String),
      }))(selection?.area_summary || {}),
    });
  }

  function selectionWarnings(body) {
    const warnings = Array.isArray(body?.warnings) ? body.warnings.map(String).filter(Boolean) : [];
    if (warnings.length) setMessage(warnings.join(' '), 'warning');
  }

  function persistCalculationSelection({keepalive = false, force = false} = {}) {
    if (!selectionLoaded || restoringSelection) return Promise.resolve(null);
    const selection = calculationSelectionFromControls();
    const key = calculationSelectionKey(selection);
    if (!force && key === lastQueuedSelectionKey) return selectionSaveChain;
    lastQueuedSelectionKey = key;
    const clientRevision = ++selectionRevision;
    selectionSaveChain = selectionSaveChain.catch(() => null).then(async () => {
      const body = await requestJson(selectionUrl, {
        method: 'PUT',
        body: JSON.stringify({selection, client_id: selectionClientId, client_revision: clientRevision}),
        keepalive,
      });
      const savedSelection = body.selection || selection;
      const savedKey = calculationSelectionKey(savedSelection);
      if (lastQueuedSelectionKey === key) {
        if (savedKey !== key) {
          restoringSelection = true;
          applySavedCalculationSelection(savedSelection);
          restoringSelection = false;
        }
        lastSavedSelectionKey = savedKey;
        lastQueuedSelectionKey = savedKey;
        selectionPersisted = true;
        selectionDirty = calculationSelectionKey(calculationSelectionFromControls()) !== savedKey;
      }
      selectionWarnings(body);
      if (savedKey !== key && !(Array.isArray(body.warnings) && body.warnings.length)) {
        setMessage('Some scoring selection values were normalized by the workspace. Review the selected filters before calculating.', 'warning');
      }
      if (body.accepted === false && calculationSelectionKey(calculationSelectionFromControls()) !== savedKey) {
        scheduleSelectionSave();
      }
      return body;
    }).catch(error => {
      if (lastQueuedSelectionKey === key) lastQueuedSelectionKey = '';
      setMessage(`The latest scoring selection could not be saved: ${error.message}`, 'warning');
      return null;
    });
    return selectionSaveChain;
  }

  function scheduleSelectionSave() {
    if (!selectionLoaded || restoringSelection) return;
    selectionDirty = true;
    if (selectionSaveTimer !== null) window.clearTimeout(selectionSaveTimer);
    selectionSaveTimer = window.setTimeout(() => {
      selectionSaveTimer = null;
      persistCalculationSelection();
    }, 250);
  }

  function applySavedCalculationSelection(selection) {
    restoringSelection = true;
    try {
      const requestedMode = String(selection?.nr_mode || 'NSA');
      if ([...(nrFilter?.options || [])].some(option => option.value === requestedMode)) nrFilter.value = requestedMode;
      applyNrFilter(false);

      const datasetIds = new Set((Array.isArray(selection?.dataset_ids) ? selection.dataset_ids : []).map(String));
      for (const input of datasetInputs) {
        const option = input.closest('[data-dataset-option]');
        input.checked = datasetIds.has(String(input.value)) && !option?.hidden;
      }
      updateSelection();

      const profileId = String(selection?.scoring_profile_id || activeProfileId);
      const profile = scoringProfileById.get(profileId);
      if (profile) scoringProfileSelect.value = profile.id;
      const levels = new Set((Array.isArray(selection?.aggregation_levels) ? selection.aggregation_levels : []).map(String));
      for (const input of aggregationInputs) input.checked = input.value === 'Operator' || levels.has(input.value);

      const baseline = String(selection?.baseline_operator || '');
      if (baseline && [...(baselineInput?.options || [])].some(option => option.value.toLocaleLowerCase() === baseline.toLocaleLowerCase())) {
        baselineInput.value = [...baselineInput.options].find(option => option.value.toLocaleLowerCase() === baseline.toLocaleLowerCase()).value;
      }
      updateSelection();
      const filters = selection?.context_filters && typeof selection.context_filters === 'object' ? selection.context_filters : {};
      const unavailableFilters = [];
      for (const key of selectionFieldOrder) {
        const select = contextFilterSelects.get(key);
        if (!select) continue;
        const requested = filters[key] ?? filters[key.toLowerCase()] ?? [];
        const requestedValues = uniqueCatalogueValues(Array.isArray(requested) ? requested : [requested]);
        const available = new Set([...select.options].filter(option => !option.disabled).map(option => option.value.toLocaleLowerCase()));
        const unavailable = requestedValues.filter(value => !available.has(value.toLocaleLowerCase()));
        if (unavailable.length) {
          // The lists of the filters follow the restored NR Mode and filters: the saved values are kept until they
          // arrive, and those the CDRs no longer have are told then.
          for (const value of unavailable) {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = key === 'Campaign' ? hierarchyDisplayValue({level: 'Campaign', value}) : value;
            select.append(option);
          }
          [...select.options].filter(option => option.disabled && !option.value).forEach(option => option.remove());
          delete select.dataset.scoringCatalogueSignature;
        }
        const selected = new Set(requestedValues.map(value => value.toLocaleLowerCase()));
        for (const option of select.options) option.selected = !option.disabled && selected.has(option.value.toLocaleLowerCase());
        select.removeAttribute?.('data-scoring-remembered-values');
        select.dispatchEvent(new Event('change', {bubbles: true}));
      }
      const summary = selection?.area_summary && typeof selection.area_summary === 'object' ? selection.area_summary : {};
      if (areaSummaryTimeSplit && [...areaSummaryTimeSplit.options].some(option => option.value === summary.time_split)) {
        areaSummaryTimeSplit.value = summary.time_split;
      }
      if (areaSummaryBreakdown && [...areaSummaryBreakdown.options].some(option => option.value === summary.breakdown)) {
        areaSummaryBreakdown.value = summary.breakdown;
      }
      if (areaSummaryCities && Array.isArray(summary.cities)) {
        const cities = [...(summary.main_cities ? [MAIN_CITIES_TOKEN] : []), ...summary.cities.map(String)];
        const known = new Set([...areaSummaryCities.options].map(option => option.value.toLocaleLowerCase()));
        for (const city of cities) {
          if (known.has(city.toLocaleLowerCase())) continue;
          const option = document.createElement('option');
          option.value = city;
          option.textContent = city;
          areaSummaryCities.append(option);
        }
        const wanted = new Set(cities.map(city => city.toLocaleLowerCase()));
        for (const option of areaSummaryCities.options) option.selected = wanted.has(option.value.toLocaleLowerCase());
        delete areaSummaryCities.dataset.scoringCatalogueSignature;
        refreshAreaSummaryCities();
      }
      applyTrendCampaigns(summary.campaigns);
      syncAreaSummary();
      updateSelection();
      if (unavailableFilters.length) {
        setMessage(`Some saved context filter values are no longer available: ${unavailableFilters.join(' · ')}. Review the selection before calculating.`, 'warning');
      }
    } finally {
      restoringSelection = false;
    }
  }

  // The panel shows the CDRs of the Saved Filter (or, with automaticCdrs, those of its NR Mode and Campaign); the lists
  // of its filters follow for its NR Mode and filters.
  // The filter values of a selection about to be restored, kept in the lists until those of its NR Mode and filters
  // arrive (see restoredContextValues).
  function keepRestoredContextValues(contextFilters) {
    const filters = contextFilters && typeof contextFilters === 'object' ? contextFilters : {};
    restoredContextValues = new Map([...contextFilterSelects.keys()].map(key => {
      const requested = filters[key] ?? filters[key.toLowerCase()] ?? [];
      return [key, uniqueCatalogueValues(Array.isArray(requested) ? requested : [requested])];
    }));
  }

  function restoreCalculationSelectionFromSavedFilter(savedFilter, {automaticCdrs = false} = {}) {
    // A Saved Filter with an automatic Campaign choice follows the campaigns and CDRs it stands for now.
    const campaignChoice = Object.entries(savedFilter.context_filters || {})
      .some(([key, values]) => key.toLowerCase() === 'campaign' && (Array.isArray(values) ? values : [values]).some(isCampaignPreset));
    pinnedCdrs = !automaticCdrs && !campaignChoice;
    keepRestoredContextValues(savedFilter.context_filters);
    applySavedCalculationSelection({
      dataset_ids: savedFilter.dataset_ids || [],
      aggregation_levels: savedFilter.aggregation_levels || savedFilter.levels || [],
      nr_mode: savedFilter.nr_mode,
      baseline_operator: savedFilter.baseline_operator,
      scoring_profile_id: savedFilter.scoring_profile_id,
      context_filters: savedFilter.context_filters || {},
      // Its Geographical Areas & Scoring Trends (Region and London for one saved without them).
      area_summary: savedFilter.area_summary && (savedFilter.area_summary.breakdown || (savedFilter.area_summary.cities || []).length
        || savedFilter.area_summary.main_cities)
        ? {...savedFilter.area_summary, breakdown: savedFilter.area_summary.breakdown || 'None', campaigns: savedFilter.area_summary.campaigns || [],
          enabled: true}
        : {enabled: true, breakdown: 'Region', cities: ['London'], time_split: savedFilter.area_summary?.time_split || 'Campaign',
          campaigns: savedFilter.area_summary?.campaigns || []},
    });
    scheduleSelectionSave();
    scheduleAutoCdrRefresh({delay: 0});
  }

  function autoCdrFilters() {
    const filters = {};
    for (const [key, select] of contextFilterSelects) {
      if (!select) continue;
      const preset = key === 'Campaign' ? chosenCampaignPreset(select) : '';
      if (preset) { filters[key] = [preset]; continue; }
      const enabled = [...select.options].filter(option => !option.disabled && option.value && !isCampaignPreset(option.value));
      const values = enabled.filter(option => option.selected).map(option => String(option.value));
      // Every value checked is no restriction, but for a list made with the values of a restored selection.
      filters[key] = values.length && values.length === enabled.length && !select.dataset.scoringRestoredList ? [] : values;
    }
    return filters;
  }

  function requestAutoCdrs(nrMode, filters, {defaultCampaign = false} = {}) {
    return requestJson(autoCdrsUrl, {
      method: 'POST',
      body: JSON.stringify({nr_mode: nrMode, context_filters: filters || {}, default_campaign: defaultCampaign}),
    });
  }

  // The lists of the filters, and (unless a Saved Filter keeps its own) the CDRs the server chose.
  function applyAutoCdrResponse(body) {
    autoCdrs = {
      options: body?.options && typeof body.options === 'object' ? body.options : {},
      incomplete: Array.isArray(body?.incomplete_campaigns) ? body.incomplete_campaigns.map(String) : [],
      presets: body?.campaign_presets && typeof body.campaign_presets === 'object' ? body.campaign_presets : {},
    };
    if (pinnedCdrs) return;
    const ids = new Set((Array.isArray(body?.dataset_ids) ? body.dataset_ids : []).map(String));
    for (const input of datasetInputs) input.checked = ids.has(String(input.value)) && !input.closest('[data-dataset-option]')?.hidden;
  }

  function setFilterValues(key, values) {
    const select = contextFilterSelects.get(key);
    if (!select) return;
    const wanted = new Set((values || []).map(value => String(value).toLocaleLowerCase()));
    for (const option of select.options) option.selected = !option.disabled && wanted.has(option.value.toLocaleLowerCase());
    select.removeAttribute('data-scoring-remembered-values');
    select.dispatchEvent(new Event('multiselect:options-updated'));
  }

  // Asks the server again for the CDRs and the filter lists after a change of the NR Mode or of a filter.
  // With defaultCampaign the newest campaign with Data, Voice and Speech CDRs of the NR Mode is chosen.
  function scheduleAutoCdrRefresh({defaultCampaign = false, delay = 150} = {}) {
    window.clearTimeout(autoCdrTimer);
    const revision = ++autoCdrRevision;
    autoCdrSection?.setAttribute('aria-busy', 'true');
    // The CDRs shown stay, dimmed, until the server chooses them again.
    globalThis.renderAutoCdrList?.(root.querySelector('[data-auto-cdr-groups]'), null, {loading: true});
    autoCdrTimer = window.setTimeout(async () => {
      try {
        const filters = autoCdrFilters();
        const body = await requestAutoCdrs(String(nrFilter?.value || 'NSA'), filters, {defaultCampaign});
        if (revision !== autoCdrRevision) return;
        applyAutoCdrResponse(body);
        // The lists of the restored selection have arrived.
        restoredContextValues = null;
        if (defaultCampaign) {
          refreshContextFilterOptions();
          setFilterValues('Campaign', body.campaign_selection || []);
        }
        // Chosen values that no CDR of the NR Mode has any longer (with the other filters) leave the selection.
        const lost = Object.entries(defaultCampaign ? {} : filters).flatMap(([key, values]) => {
          const offered = new Set((autoCdrs.options?.[key] || []).map(value => String(value).toLocaleLowerCase()));
          const missing = values.filter(value => !isCampaignPreset(value) && !offered.has(String(value).toLocaleLowerCase()));
          return missing.length && Array.isArray(autoCdrs.options?.[key]) ? [`${key}: ${missing.join(', ')}`] : [];
        });
        updateSelection();
        scheduleSelectionSave();
        if (lost.length) setMessage(`Some chosen filter values are not in the CDRs of this NR Mode with the other filters: ${lost.join(' · ')}. Review the selection before calculating.`, 'warning');
      } catch (error) {
        if (revision === autoCdrRevision) setMessage(`The CDRs of this NR Mode and Campaign could not be chosen: ${error.message}`, 'error');
      } finally {
        if (revision === autoCdrRevision) autoCdrSection?.removeAttribute('aria-busy');
      }
    }, delay);
  }

  function campaignLabelOf(value) {
    return hierarchyDisplayValue({level: 'Campaign', value});
  }

  // The CDRs of the selection that carry its campaigns: an opened Saved Filter can keep CDRs of other campaigns, whose
  // rows its Campaign filter leaves out, and they are not shown as used.
  function usedDatasetIds() {
    const ids = selectedDatasetIds();
    const campaigns = pinnedCdrs ? selectedContextFilters().Campaign || [] : [];
    if (!campaigns.length) return ids;
    const keys = value => [String(value).trim().toLocaleLowerCase(), String(campaignLabelOf(value)).trim().toLocaleLowerCase()];
    const wanted = new Set(campaigns.flatMap(keys));
    return ids.filter(id => {
      const values = uniqueCatalogueValues(datasetCatalogues.get(String(id))?.campaigns);
      return !values.length || values.some(value => keys(value).some(key => wanted.has(key)));
    });
  }

  // The CDRs the calculation uses, read-only by type, with their stage and campaigns.
  function renderAutoCdrs() {
    if (!autoCdrSection) return;
    const checked = new Set(usedDatasetIds().map(String));
    const cdrs = Object.fromEntries(datasetKindOrder.map(kind => [kind, datasetOptions
      .filter(option => String(option.dataset.datasetKind || '').toLowerCase() === kind
        && checked.has(String(option.querySelector('[data-dataset-id]')?.value || '')))
      .map(option => {
        const id = String(option.querySelector('[data-dataset-id]')?.value || '');
        return {id, name: option.dataset.datasetName || `CDR ${id}`, stage: String(option.dataset.cdrStage || 'final'),
          campaigns: [...new Set(uniqueCatalogueValues(datasetCatalogues.get(id)?.campaigns).map(campaignLabelOf))]};
      })]));
    // The CDRs by type, as every module lists them (dimmed while the server chooses them again).
    globalThis.renderAutoCdrList?.(root.querySelector('[data-auto-cdr-groups]'), autoCdrs.options ? cdrs : null, {loading: !autoCdrs.options});
    if (autoCdrSource) {
      autoCdrSource.textContent = pinnedCdrs ? 'CDRs of the opened Saved Filter' : 'Chosen automatically';
      autoCdrSource.dataset.source = pinnedCdrs ? 'saved' : 'auto';
    }
    if (autoCdrReset) autoCdrReset.hidden = !pinnedCdrs;
    let warning = autoCdrSection.querySelector('[data-auto-cdrs-warning]');
    const incomplete = pinnedCdrs ? [] : autoCdrs.incomplete;
    if (incomplete.length && !warning) {
      warning = document.createElement('p');
      warning.className = 'scoring-auto-cdrs-warning';
      warning.dataset.autoCdrsWarning = '';
      autoCdrSection.append(warning);
    }
    if (warning) {
      warning.hidden = !incomplete.length;
      warning.textContent = incomplete.length
        ? `Left out, without Data, Voice and Speech CDRs: ${incomplete.map(campaignLabelOf).join(', ')}.` : '';
    }
  }

  autoCdrReset?.addEventListener('click', () => {
    pinnedCdrs = false;
    scheduleAutoCdrRefresh({delay: 0});
  });

  async function loadCalculationSelection() {
    if (calculationPanel) {
      calculationPanel.inert = true;
      calculationPanel.setAttribute('aria-busy', 'true');
    }
    try {
      const body = await requestJson(selectionUrl);
      if (!body.selection || typeof body.selection !== 'object') throw new Error('The saved scoring selection is unavailable.');
      pinnedCdrs = body.selection.auto_cdrs === false;
      try {
        applyAutoCdrResponse(await requestAutoCdrs(String(body.selection.nr_mode || 'NSA'), body.selection.context_filters || {}));
      } catch (_error) {
        autoCdrs = {options: null, incomplete: []};
      }
      applySavedCalculationSelection(body.selection);
      const appliedKey = calculationSelectionKey(calculationSelectionFromControls());
      selectionPersisted = body.persisted !== false;
      lastSavedSelectionKey = selectionPersisted ? appliedKey : '';
      lastQueuedSelectionKey = selectionPersisted ? appliedKey : '';
      selectionLoaded = true;
      const initialWarnings = Array.isArray(body.warnings) ? body.warnings.map(String).filter(Boolean) : [];
      if (!selectionPersisted) {
        selectionDirty = true;
        await persistCalculationSelection({force: true});
      }
      selectionWarnings({warnings: initialWarnings});
    } catch (error) {
      applyNrFilter(true);
      selectionLoaded = true;
      selectionPersisted = false;
      selectionDirty = false;
      lastSavedSelectionKey = '';
      lastQueuedSelectionKey = '';
      setMessage(`Saved scoring selections could not be loaded. Current defaults are shown: ${error.message}`, 'warning');
    } finally {
      if (calculationPanel) {
        calculationPanel.inert = false;
        calculationPanel.removeAttribute('aria-busy');
      }
    }
  }

  function flushSelectionSaveOnPageHide() {
    if (selectionSaveTimer !== null) window.clearTimeout(selectionSaveTimer);
    selectionSaveTimer = null;
    if (!selectionLoaded || restoringSelection || !selectionDirty) return;
    const selection = calculationSelectionFromControls();
    const key = calculationSelectionKey(selection);
    if (selectionPersisted && key === lastSavedSelectionKey && key === lastQueuedSelectionKey) return;
    const clientRevision = ++selectionRevision;
    lastQueuedSelectionKey = key;
    fetch(selectionUrl, {
      method: 'PUT',
      credentials: 'same-origin',
      keepalive: true,
      headers: {Accept: 'application/json', 'Content-Type': 'application/json'},
      body: JSON.stringify({selection, client_id: selectionClientId, client_revision: clientRevision}),
    }).catch(() => {});
  }

  function contextFilterSummary(savedFilter) {
    const filters = savedFilter?.context_filters && typeof savedFilter.context_filters === 'object'
      ? savedFilter.context_filters : {};
    const entries = contextFilterDefinitions.flatMap(({key}) => {
      const values = filters[key] ?? filters[key.toLowerCase()];
      const normalized = uniqueCatalogueValues(Array.isArray(values) ? values : (values ? [values] : []));
      return normalized.length ? [`${key}: ${normalized.join(', ')}`] : [];
    });
    return entries.length ? entries.join(' · ') : 'All values';
  }

  function setMessage(text, kind = '') {
    if (!message) return;
    message.textContent = text;
    message.dataset.kind = kind;
  }

  function calculationPayload() {
    const levels = [...new Set(selectedLevels())];
    if (!levels.includes('Operator')) levels.unshift('Operator');
    return {
      dataset_ids: selectedDatasetIds(),
      aggregation_levels: levels,
      scoring_profile_id: scoringProfileSelect?.value || undefined,
      nr_mode: nrFilter.value || 'NSA',
      baseline_operator: baselineInput.value.trim(),
      // An automatic Campaign choice (Latest campaign…) is sent as such: the Saved Filter keeps it and resolves it when
      // it is calculated.
      context_filters: selectedContextFilters({keepPresets: true}),
      area_summary: areaSummaryPayload(),
    };
  }

  // The Geographical Areas & Scoring Trends of the calculation (always included): the Breakdown, the Separate cities and
  // Main Cities (kept as such), the time split and the campaigns of the trends when they have some.
  function areaSummaryPayload() {
    const summary = selectedAreaSummary();
    return {time_split: summary.time_split, breakdown: summary.breakdown, cities: summary.cities,
      ...(summary.main_cities ? {main_cities: true} : {}), ...(summary.campaigns.length ? {campaigns: summary.campaigns} : {})};
  }

  // Calculate Scoring, or Open Scoring (a folder open) when the selection is a Saved Filter with its result up to date.
  const CALCULATE_ICON = calculateButton?.querySelector('svg')?.outerHTML || '';
  const OPEN_ICON = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" '
    + 'stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M2.5 15.5v-10a1 1 0 0 1 1-1h4l1.8 1.8H15a1 1 0 0 1 1 1V8.5"/>'
    + '<path d="M2.5 15.5 4.8 9.2a1 1 0 0 1 .94-.7H17.6a.6.6 0 0 1 .57.8l-2 5.6a1 1 0 0 1-.94.6H2.5z"/></svg>';
  function showCalculateAction(open) {
    const action = open ? 'open' : 'calculate';
    if (!calculateButton || (calculateButton.dataset.action || 'calculate') === action) return;
    calculateButton.dataset.action = action;
    calculateButton.innerHTML = `${open ? OPEN_ICON : CALCULATE_ICON}<span>${open ? 'Open Scoring' : 'Calculate Scoring'}</span>`;
    calculateButton.title = open ? 'Open the Saved Filter of this selection with its result' : '';
  }

  function updateCalculationMatch(ready) {
    if (submittingCalculation) return;
    const payload = calculationPayload();
    const key = ready ? JSON.stringify(payload) : '';
    const refresh = calculationMatchRefresh && key === calculationMatchKey;
    calculationMatchRefresh = false;
    // Discarding the pending answer would leave both buttons disabled whenever the check is slower than the polling.
    if (refresh && calculationMatchPending) {
      calculationMatchRecheck = true;
      return;
    }
    if (key && key === calculationMatchKey && !refresh) return;
    calculationMatchKey = key;
    const revision = ++calculationMatchRevision;
    window.clearTimeout(calculationMatchTimer);
    calculationMatchPending = false;
    calculationMatchRecheck = false;
    // A new selection waits for its answer with both buttons disabled; a refresh keeps them as they are.
    if (!refresh) {
      calculateButton.disabled = true;
      recalculateButton.disabled = true;
    }
    if (!ready || !payload.baseline_operator) {
      showCalculateAction(false);
      return;
    }
    calculationMatchPending = true;
    calculationMatchTimer = window.setTimeout(async () => {
      try {
        const response = await requestJson(`${savedFiltersUrl}/match`, {method: 'POST', body: JSON.stringify(payload)});
        if (revision !== calculationMatchRevision || submittingCalculation) return;
        // The selection was used before: Calculate opens its Saved Filter (calculated again when its CDRs or
        // methodology changed), Recalculate calculates it again anyway.
        const existing = response.saved_filter;
        calculateButton.disabled = Boolean(existing) && isActive(existing);
        recalculateButton.disabled = !existing || isActive(existing);
        let text = 'Ready to calculate the scoring of these filters.';
        let kind = '';
        if (existing && isActive(existing)) {
          const verb = recalculatingSavedFilters.has(String(savedFilterIdOf(existing))) ? 'Recalculating' : 'Calculating';
          text = `${verb} the scoring of the selected CDRs and filters…`;
          kind = 'busy';
        } else if (existing?.up_to_date) {
          text = 'This selection is a Saved Filter with its result up to date: Open Scoring opens it, Recalculate calculates it again.';
        } else if (existing) {
          text = 'This selection is a Saved Filter: Calculate updates its result with the current CDRs and methodology.';
        }
        if (editingSavedFilter && duplicateName !== null) {
          // Save as New Filter saves a selection that is no Saved Filter yet.
          const copiedId = String(savedFilterIdOf(editingSavedFilter));
          text = !existing ? 'Save as New Filter saves this selection as a new Favourites Filter and calculates it.'
            : String(savedFilterIdOf(existing)) === copiedId ? 'This is still the selection of the Saved Filter being duplicated: change it to save the copy.'
            : `Saved Filter ${savedFilterIdOf(existing)} already has this selection: change it to save the copy.`;
          kind = '';
          if (editSaveButton) editSaveButton.disabled = Boolean(existing);
        } else if (editingSavedFilter) {
          // Save Changes gives the selection to the Saved Filter being edited.
          const editedId = String(savedFilterIdOf(editingSavedFilter));
          text = !existing ? 'Save Changes gives this selection to the Saved Filter and calculates it again.'
            : String(savedFilterIdOf(existing)) === editedId ? 'This is the selection of the Saved Filter being edited.'
            : `Saved Filter ${savedFilterIdOf(existing)} has this selection: Save Changes merges it into the one being edited.`;
          kind = '';
        }
        showCalculateAction(Boolean(existing?.up_to_date) && !isActive(existing) && !editingSavedFilter);
        showUnmatchedSelection(!existing && !editingSavedFilter);
        selectionStatus = {key, text, kind};
        setMessage(text, kind);
      } catch (error) {
        if (revision === calculationMatchRevision && !submittingCalculation) {
          setMessage(error.message || 'Unable to check the Saved Filters.', 'error');
        }
      } finally {
        if (revision === calculationMatchRevision) {
          calculationMatchPending = false;
          if (calculationMatchRecheck) {
            calculationMatchRecheck = false;
            calculationMatchRefresh = true;
            updateCalculationMatch(true);
          }
        }
      }
    }, 180);
  }

  // A selection that is no Saved Filter hides the results of the opened one (they belong to other filters) and its
  // card, which asks instead to choose a Favourites Filter or to calculate the selection; they come back with a
  // selection that is a Saved Filter, or when one is opened or calculated.
  function showUnmatchedSelection(unmatched) {
    if (selectionUnmatched === unmatched) return;
    selectionUnmatched = unmatched;
    syncResultsShown();
  }

  // The results and the selected card show while a scoring is open whose selection is that of the Calculation panel.
  function syncResultsShown() {
    const hidden = selectionUnmatched || scoringClosed;
    if (resultsTabbed) resultsTabbed.hidden = hidden;
    if (resultNotesStack) resultNotesStack.hidden = hidden;
    for (const selector of savedFilterSelectors) selector.classList.toggle('is-unmatched', hidden);
    setExportLinks(currentResultsSavedFilterId || '', Boolean(currentResultsSavedFilterId));
    renderSavedFilters();
  }

  // Close Scoring: the Saved Filter shown is closed (it stays saved) and the card asks to open or calculate one.
  function closeScoring() {
    if (!selectedSavedFilterId || editingSavedFilter) return;
    // Recorded in App Events, as opening one from its card.
    requestJson(`${savedFiltersUrl}/${encodeURIComponent(selectedSavedFilterId)}/close`, {method: 'POST'})
      .catch(() => { /* Closing does not depend on it. */ });
    scoringClosed = true;
    selectedSavedFilterId = null;
    selectedSavedFilter = null;
    userSelectedSavedFilter = false;
    currentResults = null;
    currentResultsSavedFilterId = null;
    renderNoResult('No scoring is open.');
    syncResultsShown();
    persistScoringViewState();
  }

  // Opening or calculating a Saved Filter opens the scoring again.
  function reopenScoring() {
    if (!scoringClosed) return;
    scoringClosed = false;
    syncResultsShown();
  }

  function unmatchedSelectionNotice() {
    const notice = document.createElement('span');
    notice.className = 'saved-filter-unmatched';
    const title = document.createElement('strong');
    title.textContent = scoringClosed ? 'No scoring is open' : "No Saved Filter matches the Calculation panel's filters";
    const text = document.createElement('span');
    text.textContent = scoringClosed
      ? 'Choose a Favourites Filter saved before, or calculate or open the scoring of the filters above.'
      : 'Choose a Favourites Filter saved before, or calculate a new scoring with the filters above (Calculate Scoring).';
    notice.append(title, text);
    return notice;
  }

  function updateSelection() {
    refreshContextFilterOptions();
    renderAutoCdrs();
    const selectedCount = usedDatasetIds().length;
    const visibleCount = datasetOptions.filter(option => !option.hidden).length;
    const missingKinds = [];
    const unavailableKinds = [];
    for (const kind of datasetKindOrder) {
      const kindOptions = datasetOptions.filter(option => !option.hidden && String(option.dataset.datasetKind || '').toLowerCase() === kind);
      const kindSelected = kindOptions.filter(option => option.querySelector('[data-dataset-id]')?.checked).length;
      const count = root.querySelector(`[data-kind-count="${kind}"]`);
      const empty = root.querySelector(`[data-dataset-group="${kind}"] [data-kind-empty]`);
      if (count) count.textContent = `${kindOptions.length} available${kindSelected ? ` · ${kindSelected} selected` : ''}`;
      if (empty) {
        empty.hidden = kindOptions.length > 0;
        empty.textContent = `No ready ${datasetKindLabels[kind]} CDR datasets are available for this NR Mode.`;
      }
      if (!kindSelected) missingKinds.push(kind);
      if (!kindOptions.length) unavailableKinds.push(kind);
    }
    const selectedBadge = root.querySelector('[data-selected-count]');
    const visibleBadge = root.querySelector('[data-visible-count]');
    if (selectedBadge) selectedBadge.textContent = `${selectedCount} CDR${selectedCount === 1 ? '' : 's'} used`;
    if (visibleBadge) visibleBadge.textContent = `${visibleCount} available`;
    const configurationError = root.dataset.configurationError || '';
    const ready = missingKinds.length === 0 && !configurationError;
    if (editSaveButton) editSaveButton.disabled = !ready || submittingCalculation;
    updateCalculationMatch(ready);
    if (configurationError) {
      setMessage(`${configurationError} Open Workspace Config → Scoring KPI Configuration.`, 'error');
    } else if (!ready) {
      const missingLabels = missingKinds.map(kind => datasetKindLabels[kind]);
      const unavailableLabels = unavailableKinds.map(kind => datasetKindLabels[kind]);
      const status = unavailableLabels.length
        ? `No ready ${unavailableLabels.join(', ')} CDR datasets are available for this NR Mode. `
        : '';
      setMessage(autoCdrs.options === null && !pinnedCdrs ? 'Choosing the CDRs of the NR Mode and Campaign…'
        : `${status}The chosen campaigns have no ${missingLabels.join(', ')} CDR: choose a campaign with Data, Voice and Speech CDRs.`);
    } else if (selectionStatus.key && selectionStatus.key === JSON.stringify(calculationPayload())) {
      setMessage(selectionStatus.text, selectionStatus.kind);
    } else if (message.dataset.kind !== 'error' && message.dataset.kind !== 'success') {
      setMessage(`${selectedCount} CDR${selectedCount === 1 ? '' : 's'} used across Data, Voice and Speech. Results are always split by Operator.`);
    }
  }

  function datasetNameDate(name) {
    const text = String(name || '');
    const dateValue = (year, month, day) => {
      const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
      return date.getUTCFullYear() === Number(year) && date.getUTCMonth() === Number(month) - 1
        && date.getUTCDate() === Number(day) ? date.getTime() : NaN;
    };
    const formats = [
      {pattern: /(?:^|\D)((?:19|20)\d{2})[-_. ]?(\d{2})[-_. ]?(\d{2})(?!\d)/g, yearFirst: true},
      {pattern: /(?:^|\D)(\d{2})[-_. ]?(\d{2})[-_. ]?((?:19|20)\d{2})(?!\d)/g, yearFirst: false},
    ];
    for (const {pattern, yearFirst} of formats) {
      for (const match of text.matchAll(pattern)) {
        const timestamp = yearFirst ? dateValue(match[1], match[2], match[3]) : dateValue(match[3], match[2], match[1]);
        if (Number.isFinite(timestamp)) return timestamp;
      }
    }
    const yearQuarter = text.match(/(?:^|\D)((?:19|20)\d{2})[-_. ]*Q([1-4])(?!\d)/i);
    if (yearQuarter) return dateValue(yearQuarter[1], (Number(yearQuarter[2]) - 1) * 3 + 1, 1);
    const quarterYear = text.match(/(?:^|[^a-z0-9])Q([1-4])[-_. ]*((?:19|20)\d{2})(?!\d)/i);
    if (quarterYear) return dateValue(quarterYear[2], (Number(quarterYear[1]) - 1) * 3 + 1, 1);
    return NaN;
  }

  function selectLatestDatasetForEachKind(count = 1) {
    for (const input of datasetInputs) input.checked = false;
    for (const kind of datasetKindOrder) {
      const candidates = datasetOptions.filter(option => !option.hidden && String(option.dataset.datasetKind || '').toLowerCase() === kind);
      candidates.sort((left, right) => {
        const leftUploaded = Date.parse(left.dataset.uploadedAt || '');
        const rightUploaded = Date.parse(right.dataset.uploadedAt || '');
        const leftNameDate = datasetNameDate(left.dataset.datasetName);
        const rightNameDate = datasetNameDate(right.dataset.datasetName);
        const leftDate = Number.isFinite(leftNameDate) ? leftNameDate : leftUploaded;
        const rightDate = Number.isFinite(rightNameDate) ? rightNameDate : rightUploaded;
        if (Number.isFinite(leftDate) && Number.isFinite(rightDate) && leftDate !== rightDate) return rightDate - leftDate;
        if (Number.isFinite(leftDate) !== Number.isFinite(rightDate)) return Number.isFinite(leftDate) ? -1 : 1;
        const leftHasUploadDate = Number.isFinite(leftUploaded);
        const rightHasUploadDate = Number.isFinite(rightUploaded);
        if (leftHasUploadDate && rightHasUploadDate && leftUploaded !== rightUploaded) return rightUploaded - leftUploaded;
        if (leftHasUploadDate !== rightHasUploadDate) return leftHasUploadDate ? -1 : 1;
        const leftId = Number(left.querySelector('[data-dataset-id]')?.value || 0);
        const rightId = Number(right.querySelector('[data-dataset-id]')?.value || 0);
        return rightId - leftId;
      });
      for (const option of candidates.slice(0, count)) {
        const input = option.querySelector('[data-dataset-id]');
        if (input) input.checked = true;
      }
    }
  }

  function applyNrFilter(selectLatest = false) {
    const mode = nrFilter.value;
    // NSA vs SA uses the CDRs of both NR Modes and is always split by Campaign (each campaign with its NR Mode).
    const modes = mode === nsaVsSa ? ['NSA', 'SA'] : [mode];
    const campaignLevel = aggregationInputByLevel.get('Campaign');
    if (campaignLevel) {
      if (mode === nsaVsSa) campaignLevel.checked = true;
      campaignLevel.disabled = mode === nsaVsSa;
      campaignLevel.closest('label')?.classList.toggle('is-required', mode === nsaVsSa);
      campaignLevel.closest('label').title = mode === nsaVsSa ? 'NSA vs SA is always split by Campaign: each campaign with its NR Mode' : '';
    }
    // Same operator in NSA (each operator in SA compared with itself in NSA) is a GAP reference of NSA vs SA only.
    const sameOperator = baselineInput?.querySelector('[data-nsa-vs-sa-reference]');
    if (sameOperator) {
      sameOperator.hidden = sameOperator.disabled = mode !== nsaVsSa;
      if (mode !== nsaVsSa && baselineInput.value === sameOperator.value) {
        baselineInput.value = [...baselineInput.options].find(option => option.value.toLocaleLowerCase() === 'ee')?.value
          || baselineInput.options[0].value;
      }
    }
    const allPeriods = areaSummaryTimeSplit && [...areaSummaryTimeSplit.options].find(option => option.value === 'All');
    if (allPeriods) {
      allPeriods.disabled = mode === nsaVsSa;
      if (mode === nsaVsSa && areaSummaryTimeSplit.value === 'All') areaSummaryTimeSplit.value = 'Campaign';
    }
    for (const option of datasetOptions) {
      const matches = !mode || modes.includes(option.dataset.nrMode);
      option.hidden = !matches;
      if (!matches) {
        const checkbox = option.querySelector('[data-dataset-id]');
        if (checkbox) checkbox.checked = false;
      }
    }
    if (selectLatest) selectLatestDatasetForEachKind();
    updateSelection();
  }

  function formatDate(value) {
    if (!value) return 'Date unavailable';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'});
  }

  function savedFilterSummary(savedFilter) {
    const names = valueOf(savedFilter, ['dataset_names', 'cdr_names', 'campaigns'], null);
    if (Array.isArray(names) && names.length) return names.join(', ');
    const ids = valueOf(savedFilter, ['dataset_ids', 'cdr_ids'], []);
    const count = Array.isArray(ids) ? ids.length : Number(valueOf(savedFilter, ['dataset_count'], 0));
    const campaign = valueOf(savedFilter, ['campaign', 'campaign_name', 'campaigns'], '');
    return [campaign || `${count || 'Selected'} CDR${count === 1 ? '' : 's'}`].filter(Boolean).join('');
  }

  function savedFilterCdrNames(savedFilter) {
    let names = valueOf(savedFilter, ['dataset_names', 'cdr_names', 'source_names'], null);
    if (!Array.isArray(names) || !names.length) {
      const metadata = savedFilter?.source_metadata;
      const entries = Array.isArray(metadata) ? metadata : (metadata && typeof metadata === 'object' ? Object.values(metadata) : []);
      names = entries.map(entry => firstValue(entry, ['name', 'dataset_name', 'cdr_name'], '')).filter(Boolean);
    }
    return Array.isArray(names) ? uniqueCatalogueValues(names) : [];
  }

  function savedFilterCdrSummary(savedFilter) {
    const names = savedFilterCdrNames(savedFilter);
    if (names.length) return names.join(', ');
    const ids = valueOf(savedFilter, ['dataset_ids', 'cdr_ids'], []);
    const count = Array.isArray(ids) ? ids.length : Number(valueOf(savedFilter, ['dataset_count'], 0));
    return `${count || 'Selected'} CDR${count === 1 ? '' : 's'}`;
  }

  function savedSavedFilterValues(savedFilter, key) {
    for (const filters of [savedFilter?.context_filters, savedFilter?.resolved_context_filters]) {
      if (!filters || typeof filters !== 'object') continue;
      const value = firstValue(filters, [key], null);
      if (value === null || value === undefined) continue;
      const rawValues = Array.isArray(value) ? value : [value];
      const values = uniqueCatalogueValues(key === 'Vendor' ? rawValues.map(scoringVendorName) : rawValues);
      const datasetIds = valueOf(savedFilter, ['dataset_ids', 'cdr_ids'], []);
      const catalogueKey = catalogueKeyByLevel.get(key);
      if (values.length && Array.isArray(datasetIds) && datasetIds.length
          && datasetIds.every(id => Array.isArray(datasetCatalogues.get(String(id))?.[catalogueKey]))) {
        const available = new Set(datasetIds.flatMap(id => datasetCatalogues.get(String(id))[catalogueKey])
          .map(item => String(key === 'Vendor' ? scoringVendorName(item) : item).trim().toLocaleLowerCase()).filter(Boolean));
        const selected = new Set(values.map(item => item.toLocaleLowerCase()));
        if (available.size && available.size === selected.size && [...available].every(item => selected.has(item))) return [];
      }
      return values;
    }
    return [];
  }

  function savedFilterCardTitleSegments(savedFilter) {
    const filterValue = (key, fallback) => savedSavedFilterValues(savedFilter, key).join(', ') || fallback;
    const campaignFilter = savedSavedFilterValues(savedFilter, 'Campaign');
    const campaigns = campaignFilter.length
      ? [...new Set(campaignFilter.map(value => hierarchyDisplayValue({level: 'Campaign', value})))]
        .sort((left, right) => insightCampaignKey(left) - insightCampaignKey(right) || left.localeCompare(right))
      : savedFilterCampaigns(savedFilter).filter(value => value !== 'Unspecified');
    let campaignValue = campaigns.length ? campaigns.join(', ') : 'All Campaigns';
    // An automatic choice (All available campaigns…) is shown as such, with the campaigns it stood for last time.
    const choice = campaignFilter.find(isCampaignPreset);
    if (choice) {
      const resolved = [...new Set((Array.isArray(savedFilter?.resolved_campaigns) ? savedFilter.resolved_campaigns : [])
        .map(value => hierarchyDisplayValue({level: 'Campaign', value})))]
        .sort((left, right) => insightCampaignKey(left) - insightCampaignKey(right) || left.localeCompare(right));
      campaignValue = resolved.length ? `${campaignPresetLabels[choice]} (${resolved.join(', ')})` : campaignPresetLabels[choice];
    }
    return [
      {dimension: 'neutral', value: formatDate(valueOf(savedFilter, ['last_used_at', 'created_at'], ''))},
      // (NSA vs SA reads so.)
      {dimension: 'nr-mode', value: (mode => (mode === 'NSA+SA' ? 'NSA vs SA' : mode))(valueOf(savedFilter, ['nr_mode'], 'All NR Modes'))},
      {dimension: 'region', value: filterValue('Region', 'All Regions')},
      {dimension: 'cluster', value: filterValue('Cluster', 'All Clusters')},
      {dimension: 'city', value: filterValue('City', 'All Cities')},
      {dimension: 'operator', value: filterValue('Operator', 'All Operators')},
      {dimension: 'vendor', value: filterValue('Vendor', 'All Vendors')},
      {dimension: 'campaign', value: campaignValue},
    ];
  }

  function savedFilterCardTitle(savedFilter) {
    return savedFilterCardTitleSegments(savedFilter).map(segment => segment.value).join(' ● ');
  }

  // The labels on top of the card of a Saved Filter, each with the values of a field in its colour: first the Region,
  // Cluster or City it filters (Nationwide when it filters none of them), then the Operator or Vendor it filters (its
  // Campaign and NR Mode aside).
  function savedFilterScopes(savedFilter) {
    const filtered = levels => levels.map(level => ({level, values: savedSavedFilterValues(savedFilter, level)}))
      .filter(item => item.values.length)
      .map(({level, values}) => ({dimension: level.toLowerCase(), text: values.join(', '), title: `${level}: ${values.join(', ')}`}));
    const areas = filtered(['Region', 'Cluster', 'City']);
    return [...(areas.length ? areas : [{dimension: 'all', text: 'Nationwide', title: 'No Region, Cluster or City is filtered'}]),
      ...filtered(['Operator', 'Vendor'])];
  }

  function campaignLabels(value) {
    const values = Array.isArray(value) ? value : [value];
    return values.flatMap(item => {
      if (typeof item === 'string') return item.trim() ? [item.trim()] : [];
      if (!item || typeof item !== 'object') return [];
      return campaignLabels(firstValue(item, ['campaigns', 'campaign'], null));
    });
  }

  function savedFilterCampaigns(savedFilter) {
    let campaigns = campaignLabels(savedFilter?.campaigns);
    if (!campaigns.length) campaigns = campaignLabels(valueOf(savedFilter, ['campaign', 'campaign_name'], null));
    if (!campaigns.length) {
      const metadata = savedFilter?.source_metadata;
      const entries = Array.isArray(metadata) ? metadata : (metadata && typeof metadata === 'object' ? Object.values(metadata) : []);
      campaigns = entries.flatMap(entry => campaignLabels(entry));
    }
    // Shown as everywhere (2026-Q2-SA), in chronological order.
    const unique = [...new Set(campaigns.map(value => hierarchyDisplayValue({level: 'Campaign', value})))]
      .sort((left, right) => insightCampaignKey(left) - insightCampaignKey(right) || left.localeCompare(right));
    return unique.length ? unique : ['Unspecified'];
  }

  function savedFilterLevels(savedFilter) {
    const levels = valueOf(savedFilter, ['aggregation_levels', 'levels'], []);
    return Array.isArray(levels) ? (levels.length ? levels.join(' → ') : 'Operator') : String(levels || 'Operator');
  }

  // The campaigns of the Scoring Trends of a Saved Filter: those of its trends (an automatic choice with the campaigns it
  // stood for last time), else those of the Saved Filter.
  function savedFilterTrendCampaigns(savedFilter) {
    const display = values => [...new Set(values.map(value => hierarchyDisplayValue({level: 'Campaign', value})))]
      .sort((left, right) => insightCampaignKey(left) - insightCampaignKey(right) || left.localeCompare(right));
    const own = (Array.isArray(savedFilter?.area_summary?.campaigns) ? savedFilter.area_summary.campaigns : []).filter(Boolean);
    if (!own.length) return savedFilterCardTitleSegments(savedFilter).find(segment => segment.dimension === 'campaign')?.value || 'All Campaigns';
    const resolved = display(Array.isArray(savedFilter?.trend_campaigns) ? savedFilter.trend_campaigns : []);
    const choice = own.find(isCampaignPreset);
    if (choice) return resolved.length ? `${campaignPresetLabels[choice]} (${resolved.join(', ')})` : campaignPresetLabels[choice];
    return display(own).join(', ');
  }

  // The Geographical Areas of a Saved Filter as [kind, label, value] triples: its Breakdown and Separate cities (each Region
  // and London for one saved without them, as it is calculated).
  function savedFilterAreaSummaryParts(savedFilter) {
    const summary = savedFilter?.area_summary && typeof savedFilter.area_summary === 'object' ? savedFilter.area_summary : {};
    let cities = [...(summary.main_cities ? ['Main Cities'] : []), ...(Array.isArray(summary.cities) ? summary.cities : []).filter(Boolean)];
    let breakdown = summary.breakdown && summary.breakdown !== 'None' ? summary.breakdown : null;
    if (!breakdown && !cities.length) [breakdown, cities] = ['Region', ['London']];
    return [['breakdown', 'Breakdown', breakdown || 'None'], ['cities', 'Separate cities', cities.length ? cities.join(', ') : 'None']];
  }

  // The time split of the National & Geographical Areas Trends of a Saved Filter.
  function savedFilterTimeSplit(savedFilter) {
    const split = savedFilter?.area_summary?.time_split;
    return {All: 'All selected CDRs'}[split] || split || 'Campaign';
  }

  // The calculation time of a Saved Filter (start to finish), or its elapsed time while it runs.
  function savedFilterDurationText(savedFilter, now = Date.now()) {
    const started = Date.parse(valueOf(savedFilter, ['started_at'], '') || '');
    if (!Number.isFinite(started)) return '';
    const finished = Date.parse(valueOf(savedFilter, ['finished_at'], '') || '');
    const end = Number.isFinite(finished) ? finished : (isActive(savedFilter) ? now : NaN);
    if (!Number.isFinite(end)) return '';
    const seconds = Math.max(0, Math.round((end - started) / 1000));
    if (seconds < 60) return `${seconds} s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, '0')} s`;
    return `${Math.floor(seconds / 3600)} h ${String(Math.floor((seconds % 3600) / 60)).padStart(2, '0')} min`;
  }

  function progressValue(savedFilter) {
    const raw = Number(valueOf(savedFilter, ['progress', 'progress_percent', 'percentage'], 0));
    if (!Number.isFinite(raw)) return 0;
    return Math.max(0, Math.min(100, raw <= 1 ? raw * 100 : raw));
  }

  // The pinned Saved Filters first, then the latest used.
  // The starred Saved Filters in their place (opening one does not move it; they are moved by dragging them), then the
  // others, the latest used first.
  function sortedSavedFilters(records) {
    const place = record => (record.pinned && Number.isFinite(Number(record.position)) && record.position !== null
      ? Number(record.position) : Infinity);
    return [...records].sort((left, right) => {
      const leftDate = new Date(valueOf(left, ['last_used_at', 'created_at'], 0)).getTime() || 0;
      const rightDate = new Date(valueOf(right, ['last_used_at', 'created_at'], 0)).getTime() || 0;
      return Number(Boolean(right.pinned)) - Number(Boolean(left.pinned))
        || (place(left) === place(right) ? 0 : place(left) < place(right) ? -1 : 1)
        || rightDate - leftDate || Number(right.id || 0) - Number(left.id || 0);
    });
  }

  // The Saved Filters unfolded in a list (the Saved Filters panel or the dropdown of the Scoring Results); folded at first.
  const unfoldedSavedFilters = new Map();
  function unfoldedSavedFilterIds(list) {
    if (!unfoldedSavedFilters.has(list)) unfoldedSavedFilters.set(list, new Set());
    return unfoldedSavedFilters.get(list);
  }

  function syncSavedFilterLists() {
    for (const list of savedFilterLists.slice(1)) {
      list.replaceChildren(...Array.from(savedFilterList.children, row => row.cloneNode(true)));
    }
    // In the Saved Filters panel the starred Saved Filters are moved by dragging the tab on the side of their card.
    if (savedFilterPanelList && canReorderSavedFilters) {
      for (const row of savedFilterPanelList.querySelectorAll('.saved-filter-row')) {
        const handle = document.createElement('span');
        handle.className = 'saved-filter-drag-handle';
        handle.dataset.savedFilterDragHandle = '';
        handle.title = 'Drag to move this Saved Filter in the list';
        handle.setAttribute('aria-hidden', 'true');
        row.classList.add('is-reorderable');
        row.prepend(handle);
      }
    }
    if (savedFilterPanelList) {
      for (const row of savedFilterPanelList.querySelectorAll('.saved-filter-row')) {
        const id = row.dataset.savedFilterRow;
        const check = document.createElement('label');
        check.className = 'saved-filter-check';
        check.title = 'Select this Saved Filter';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.dataset.savedFilterCheck = id;
        input.checked = checkedSavedFilterIds.has(id);
        input.setAttribute('aria-label', `Select Saved Filter ${id}`);
        check.append(input);
        // On top of the tab on the left of the card (the drag tab, when the card can be moved).
        row.classList.add('is-checkable');
        row.prepend(check);
      }
    }
    // Each list keeps the Saved Filters unfolded in it.
    for (const list of savedFilterLists) {
      const unfolded = unfoldedSavedFilterIds(list);
      for (const row of list.querySelectorAll('.saved-filter-row')) {
        const open = unfolded.has(row.dataset.savedFilterRow);
        row.classList.toggle('is-expanded', open);
        row.querySelector('.saved-filter-item')?.setAttribute('aria-expanded', String(open));
      }
    }
    syncSavedFiltersBulk();
  }

  // The Select all box and the Use newer CDRs button on top of the Saved Filters panel, for the checked Saved Filters.
  function syncSavedFiltersBulk() {
    if (!savedFiltersBulk) return;
    const listed = savedFilters.filter(savedFilter => savedFilter.pinned).map(savedFilterIdOf);
    for (const id of [...checkedSavedFilterIds]) if (!listed.includes(id)) checkedSavedFilterIds.delete(id);
    savedFiltersBulk.hidden = !listed.length;
    savedFiltersSelectAll.checked = listed.length > 0 && checkedSavedFilterIds.size === listed.length;
    savedFiltersSelectAll.indeterminate = checkedSavedFilterIds.size > 0 && checkedSavedFilterIds.size < listed.length;
    const order = starredSavedFilterOrder();
    for (const button of savedFiltersMove) {
      // Readers cannot move Saved Filters; a button is off when no checked Saved Filter can move that way.
      button.hidden = !canReorderSavedFilters;
      const step = button.dataset.savedFiltersMove === 'up' ? -1 : 1;
      button.disabled = deletingCheckedSavedFilters || movedSavedFilterOrder(order, step).join() === order.join();
    }
    // (Readers only have Use newer CDRs, without the separators around it.)
    savedFiltersBulk.querySelectorAll('.bulk-toolbar-separator').forEach(separator => { separator.hidden = !canReorderSavedFilters; });
    const withNewer = savedFiltersWithNewerCdrs();
    savedFiltersUseNewer.textContent = withNewer.length ? `Use newer CDRs (${withNewer.length})` : 'Use newer CDRs';
    savedFiltersUseNewer.disabled = updatingSavedFiltersCdrs || !withNewer.length;
    if (savedFiltersDelete) {
      // Readers cannot delete Saved Filters.
      savedFiltersDelete.hidden = !canReorderSavedFilters;
      savedFiltersDelete.textContent = checkedSavedFilterIds.size ? `Delete (${checkedSavedFilterIds.size})` : 'Delete';
      savedFiltersDelete.disabled = deletingCheckedSavedFilters || updatingSavedFiltersCdrs || !checkedSavedFilterIds.size;
    }
  }

  function savedFiltersWithNewerCdrs() {
    return savedFilters.filter(savedFilter => checkedSavedFilterIds.has(savedFilterIdOf(savedFilter))
      && (savedFilter.newer_cdrs || []).length && !isActive(savedFilter));
  }

  // The starred Saved Filters in the order of their list.
  function starredSavedFilterOrder() {
    return sortedSavedFilters(savedFilters).filter(savedFilter => savedFilter.pinned).map(savedFilterIdOf);
  }

  // The order of the starred Saved Filters with each checked one a place up (step -1) or down (step 1): a checked one
  // trades places with the unchecked one next to it, so checked ones side by side move together and stop at the end.
  function movedSavedFilterOrder(order, step) {
    const moved = [...order];
    const indexes = moved.map((_, index) => index);
    for (const index of step < 0 ? indexes.slice(1) : indexes.slice(0, -1).reverse()) {
      if (checkedSavedFilterIds.has(moved[index]) && !checkedSavedFilterIds.has(moved[index + step])) {
        [moved[index], moved[index + step]] = [moved[index + step], moved[index]];
      }
    }
    return moved;
  }

  if (savedFilterPanelList && savedFiltersBulk) {
    savedFilterPanelList.addEventListener('change', event => {
      const input = event.target instanceof Element ? event.target.closest('[data-saved-filter-check]') : null;
      if (!input) return;
      if (input.checked) checkedSavedFilterIds.add(input.dataset.savedFilterCheck);
      else checkedSavedFilterIds.delete(input.dataset.savedFilterCheck);
      syncSavedFiltersBulk();
    });
    savedFiltersSelectAll.addEventListener('change', () => {
      checkedSavedFilterIds.clear();
      if (savedFiltersSelectAll.checked) {
        savedFilters.filter(savedFilter => savedFilter.pinned).forEach(savedFilter => checkedSavedFilterIds.add(savedFilterIdOf(savedFilter)));
      }
      for (const input of savedFilterPanelList.querySelectorAll('[data-saved-filter-check]')) {
        input.checked = checkedSavedFilterIds.has(input.dataset.savedFilterCheck);
      }
      syncSavedFiltersBulk();
    });
    // Move Up and Move Down move the checked Saved Filters one place in the list, as dragging them would.
    for (const button of savedFiltersMove) {
      button.addEventListener('click', () => {
        const step = button.dataset.savedFiltersMove === 'up' ? -1 : 1;
        const order = movedSavedFilterOrder(starredSavedFilterOrder(), step);
        saveSavedFilterOrder(order);
        // The moved cards light up where they land, and the one that leads the way stays in view below this bar, which
        // stays at the top while the panel is scrolled.
        const rows = [...savedFilterPanelList.querySelectorAll('.saved-filter-row')]
          .filter(row => checkedSavedFilterIds.has(row.dataset.savedFilterRow));
        rows.forEach(row => row.classList.add('is-moved'));
        const leading = step < 0 ? rows[0] : rows[rows.length - 1];
        if (leading) {
          const clear = (parseFloat(getComputedStyle(savedFiltersBulk).top) || 0) + savedFiltersBulk.offsetHeight + 12;
          const box = leading.getBoundingClientRect();
          if (box.top < clear) window.scrollBy({top: box.top - clear, behavior: 'auto'});
          else if (box.bottom > window.innerHeight - 12) window.scrollBy({top: box.bottom - window.innerHeight + 12, behavior: 'auto'});
        }
      });
    }
    // Each checked Saved Filter with newer CDRs is updated with them and calculated again in the background; the one
    // being looked at stays open.
    savedFiltersUseNewer.addEventListener('click', async () => {
      const targets = savedFiltersWithNewerCdrs();
      if (!targets.length) return;
      updatingSavedFiltersCdrs = true;
      syncSavedFiltersBulk();
      setMessage(`Updating ${targets.length} Saved Filter${targets.length === 1 ? '' : 's'} with the newer CDRs…`, 'busy');
      const failures = [];
      for (const savedFilter of targets) {
        const id = savedFilterIdOf(savedFilter);
        try {
          await requestJson(`${savedFiltersUrl}/${encodeURIComponent(id)}/use-newer-cdrs`, {
            method: 'POST', body: JSON.stringify({select: false}),
          });
          resultCache.delete(id);
        } catch (error) {
          failures.push(`${savedFilter.name || `Filter ID ${id}`}: ${error.message}`);
        }
      }
      updatingSavedFiltersCdrs = false;
      const updated = targets.length - failures.length;
      if (failures.length) setMessage(`Updated ${updated} of ${targets.length} Saved Filters. ${failures.join(' ')}`, 'error');
      else setMessage(`${updated} Saved Filter${updated === 1 ? '' : 's'} updated with the newer CDRs and queued to calculate again.`, 'success');
      await refreshSavedFilters();
    });
    // The checked Saved Filters are deleted together, after one confirmation, with their results.
    savedFiltersDelete?.addEventListener('click', async () => {
      const targets = savedFilters.filter(savedFilter => checkedSavedFilterIds.has(savedFilterIdOf(savedFilter)));
      if (!targets.length || deletingCheckedSavedFilters) return;
      const count = targets.length;
      const active = targets.filter(isActive).length;
      const copy = `Delete ${count} Saved Filter${count === 1 ? '' : 's'} and ${count === 1 ? 'its result' : 'their results'}?`
        + `${active ? ` The pending result of ${active} of them will be discarded.` : ''} The CDRs and the Scoring History stay.`;
      const accepted = typeof showConfirmDialog === 'function'
        ? await showConfirmDialog(copy, {title: `Delete ${count} Saved Filter${count === 1 ? '' : 's'}`, confirmLabel: 'Delete'})
        : window.confirm(copy);
      if (!accepted) return;
      deletingCheckedSavedFilters = true;
      syncSavedFiltersBulk();
      setMessage(`Deleting ${count} Saved Filter${count === 1 ? '' : 's'}…`, 'busy');
      try {
        const body = await requestJson(`${savedFiltersUrl}/delete`, {
          method: 'POST', body: JSON.stringify({ids: targets.map(savedFilter => Number(savedFilterIdOf(savedFilter)))}),
        });
        const deleted = new Set((body?.deleted || []).map(String));
        deleted.forEach(id => { deletedSavedFilterIds.add(id); resultCache.delete(id); checkedSavedFilterIds.delete(id); });
        savedFilters = savedFilters.filter(record => !deleted.has(savedFilterIdOf(record)));
        calculationMatchKey = '';
        if (editingSavedFilter && deleted.has(savedFilterIdOf(editingSavedFilter))) stopSavedFilterEdit();
        updateSelection();
        if (deleted.has(selectedSavedFilterId)) {
          selectedSavedFilterId = null;
          selectedSavedFilter = null;
          currentResults = null;
          currentResultsSavedFilterId = null;
          userSelectedSavedFilter = false;
          renderNoResult('Calculate a scoring or choose Saved Filters to see their results.');
        }
        const missing = (body?.missing || []).length;
        setMessage(`${deleted.size} Saved Filter${deleted.size === 1 ? '' : 's'} and ${deleted.size === 1 ? 'its result' : 'their results'} deleted.`
          + (missing ? ` ${missing} no longer existed.` : ''), 'success');
      } catch (error) {
        setMessage(error.message || 'The Saved Filters could not be deleted.', 'error');
      } finally {
        deletingCheckedSavedFilters = false;
        renderSavedFilters();
      }
      await refreshSavedFilters();
    });
  }

  // Dragging a starred Saved Filter in the Saved Filters panel (or Move Up and Move Down, which give the ``order``) moves
  // it in the list; its place is saved for every user of the workspace.
  async function saveSavedFilterOrder(order = [...savedFilterPanelList.querySelectorAll('.saved-filter-row')].map(row => row.dataset.savedFilterRow)) {
    const previous = sortedSavedFilters(savedFilters).filter(savedFilter => savedFilter.pinned).map(savedFilterIdOf);
    if (order.join() === previous.join()) return;
    order.forEach((id, index) => {
      const record = savedFilters.find(savedFilter => savedFilterIdOf(savedFilter) === id);
      if (record) record.position = index + 1;
    });
    renderSavedFilters();
    const request = savedFilterOrderRequest.then(() => requestJson(`${savedFiltersUrl}/order`, {
      method: 'POST', body: JSON.stringify({filter_ids: order.map(Number)}),
    }));
    savedFilterOrderRequest = request.catch(() => {});
    try {
      await request;
    } catch (error) {
      setMessage(error.message || 'The order of the Saved Filters could not be saved.', 'error');
      refreshSavedFilters();
    }
  }
  if (savedFilterPanelList && canReorderSavedFilters) {
    // Only the tab makes its card draggable, so the rest of the card is clicked to open the Saved Filter.
    savedFilterPanelList.addEventListener('pointerdown', event => {
      const handle = event.target instanceof Element ? event.target.closest('[data-saved-filter-drag-handle]') : null;
      if (handle) handle.closest('.saved-filter-row').draggable = true;
    });
    savedFilterPanelList.addEventListener('pointerup', () => {
      if (draggedSavedFilterRow) return;
      for (const row of savedFilterPanelList.querySelectorAll('.saved-filter-row[draggable="true"]')) row.draggable = false;
    });
    savedFilterPanelList.addEventListener('dragstart', event => {
      const row = event.target instanceof Element ? event.target.closest('.saved-filter-row[draggable="true"]') : null;
      if (!row) return;
      draggedSavedFilterRow = row;
      row.classList.add('is-dragging');
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', row.dataset.savedFilterRow || '');
    });
    // While a card is dragged, a horizontal line shows where it will go; it moves there when it is dropped.
    const dropLine = document.createElement('div');
    dropLine.className = 'saved-filter-drop-line';
    dropLine.setAttribute('aria-hidden', 'true');
    let dropBefore;
    const hideDropLine = () => {
      dropLine.remove();
      dropBefore = undefined;
    };
    savedFilterPanelList.addEventListener('dragover', event => {
      if (!draggedSavedFilterRow) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      const row = event.target instanceof Element ? event.target.closest('.saved-filter-row') : null;
      if (!row) return;
      const box = row.getBoundingClientRect();
      // The card it would go before (none: the end of the list); the line itself is the last child of the list.
      const nextRow = element => (element.nextElementSibling === dropLine ? null : element.nextElementSibling);
      const target = event.clientY > box.top + box.height / 2 ? nextRow(row) : row;
      // Dropped next to itself, the card stays where it is: no line.
      if (row === draggedSavedFilterRow || target === draggedSavedFilterRow || target === nextRow(draggedSavedFilterRow)) {
        hideDropLine();
        return;
      }
      if (target === dropBefore && dropLine.isConnected) return;
      dropBefore = target;
      const rows = [...savedFilterPanelList.querySelectorAll('.saved-filter-row')];
      const gap = parseFloat(getComputedStyle(savedFilterPanelList).rowGap) || 0;
      const listBox = savedFilterPanelList.getBoundingClientRect();
      const edge = target
        ? target.getBoundingClientRect().top - gap / 2
        : rows[rows.length - 1].getBoundingClientRect().bottom + gap / 2;
      dropLine.style.top = `${edge - listBox.top + savedFilterPanelList.scrollTop}px`;
      if (!dropLine.isConnected) savedFilterPanelList.append(dropLine);
    });
    savedFilterPanelList.addEventListener('dragleave', event => {
      if (draggedSavedFilterRow && !savedFilterPanelList.contains(event.relatedTarget)) hideDropLine();
    });
    savedFilterPanelList.addEventListener('drop', event => {
      if (!draggedSavedFilterRow) return;
      event.preventDefault();
      if (dropLine.isConnected) savedFilterPanelList.insertBefore(draggedSavedFilterRow, dropBefore || dropLine);
      hideDropLine();
    });
    savedFilterPanelList.addEventListener('dragend', () => {
      hideDropLine();
      if (!draggedSavedFilterRow) return;
      draggedSavedFilterRow.classList.remove('is-dragging');
      draggedSavedFilterRow.draggable = false;
      draggedSavedFilterRow = null;
      const pending = savedFiltersRenderPending;
      savedFiltersRenderPending = false;
      saveSavedFilterOrder();
      if (pending) renderSavedFilters();
    });
  }

  // The Saved Filters panel shows ten Saved Filters before it scrolls, and is only as tall as fewer ones.
  function fitSavedFilterPanels() {
    const inView = 10;
    for (const list of [savedFilterPanelList].filter(Boolean)) {
      const items = list.querySelectorAll(':scope > .saved-filter-item');
      if (items.length <= inView) {
        list.style.maxHeight = 'none';
        continue;
      }
      const tenth = items[inView - 1].getBoundingClientRect();
      if (!tenth.height) continue;
      const bottom = tenth.bottom - list.getBoundingClientRect().top + list.scrollTop + (parseFloat(getComputedStyle(list).paddingBottom) || 0);
      list.style.maxHeight = `${Math.ceil(bottom) + 2}px`;
    }
  }
  // The ten are measured whenever the Saved Filters are drawn again and, narrower or wider, change height.
  if (typeof MutationObserver === 'function') {
    for (const list of [savedFilterPanelList].filter(Boolean)) new MutationObserver(fitSavedFilterPanels).observe(list, {childList: true});
  }
  let savedFilterPanelWidth = 0;
  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(entries => {
      const width = Math.round(entries[0]?.contentRect.width || 0);
      if (width && width !== savedFilterPanelWidth) {
        savedFilterPanelWidth = width;
        fitSavedFilterPanels();
      }
    }).observe(savedFilterPanelList || savedFilterList);
  }

  function renderSavedFilters() {
    // A list being dragged is drawn again once it is dropped.
    if (draggedSavedFilterRow) {
      savedFiltersRenderPending = true;
      return;
    }
    const ordered = sortedSavedFilters(savedFilters);
    // The lists hold the starred Saved Filters only; the one opened without a star shows in the selected card, where it
    // can be starred.
    const starred = ordered.filter(savedFilter => savedFilter.pinned);
    for (const countBadge of root.querySelectorAll('[data-saved-filter-count]')) {
      countBadge.textContent = `${starred.length} Favourites Filter${starred.length === 1 ? '' : 's'}`;
    }
    savedFilterList.replaceChildren();
    selectedSavedFilterCard.textContent = ordered.length ? 'Select a Saved Filter' : 'No Saved Filters yet';
    let selectedCardShown = false;
    if (!starred.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No Favourites Filters yet: star (☆) a scoring to keep its filters here.';
      savedFilterList.append(empty);
    }
    for (const savedFilter of ordered) {
      const id = savedFilterIdOf(savedFilter);
      const status = normalizeStatus(savedFilter);
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'saved-filter-item';
      button.dataset.savedFilterId = id;
      button.setAttribute('aria-current', String(id === selectedSavedFilterId));
      // The card folds and unfolds the details of the Saved Filter; Use Filter, on the right of its name, opens it.
      button.setAttribute('aria-expanded', 'false');
      button.title = 'Show or hide the details of this Saved Filter';
      // The name given to the Saved Filter, above its filters (its ID when it has none), after the fold arrow.
      const head = document.createElement('span');
      head.className = 'saved-filter-head';
      const chevron = document.createElement('span');
      chevron.className = 'saved-filter-chevron';
      chevron.setAttribute('aria-hidden', 'true');
      const name = document.createElement('span');
      name.className = savedFilter.name ? 'saved-filter-name' : 'saved-filter-name is-unnamed';
      name.textContent = savedFilter.name || `Filter ID: ${id}`;
      head.append(chevron, name);
      button.append(head);
      const top = document.createElement('span');
      top.className = 'saved-filter-item-top';
      const title = document.createElement('strong');
      const titleSegments = savedFilterCardTitleSegments(savedFilter);
      titleSegments.forEach((segment, index) => {
        if (index) {
          const separator = document.createElement('span');
          separator.className = 'saved-filter-title-separator';
          separator.dataset.dimension = 'neutral';
          separator.textContent = ' ● ';
          title.append(separator);
        }
        const value = document.createElement('span');
        value.className = `saved-filter-title-segment saved-filter-title-${segment.dimension}`;
        value.dataset.dimension = segment.dimension;
        value.textContent = segment.value;
        title.append(value);
      });
      title.setAttribute('aria-label', savedFilterCardTitle(savedFilter));
      title.title = savedFilterCardTitle(savedFilter);
      const statusBadge = document.createElement('span');
      statusBadge.className = 'scoring-status';
      statusBadge.dataset.status = status;
      // Imported filters are calculated when they are first opened.
      statusBadge.textContent = status === 'saved' ? 'not calculated' : status;
      top.append(title, statusBadge);
      button.append(top);
      const aggregation = document.createElement('span');
      aggregation.className = 'saved-filter-aggregation';
      const aggregationLabel = document.createElement('span');
      aggregationLabel.textContent = 'Split by:';
      const aggregationLevels = document.createElement('strong');
      aggregationLevels.textContent = savedFilterLevels(savedFilter);
      aggregation.append(aggregationLabel, aggregationLevels);
      const meta = document.createElement('span');
      meta.className = 'saved-filter-meta';
      const baseline = valueOf(savedFilter, ['baseline_operator'], 'EE');
      meta.textContent = 'GAP Reference: ';
      const referenceValue = document.createElement('strong');
      referenceValue.className = 'saved-filter-reference';
      referenceValue.textContent = baseline === '@same-operator-nsa' ? 'Same operator in NSA' : baseline;
      meta.append(referenceValue);
      // Its Geographical Areas & Scoring Trends, as in the panel: the Breakdown and Separate cities of both tabs, then the
      // campaigns and time split of the trends, each value in its own colour.
      const areaMeta = document.createElement('span');
      areaMeta.className = 'saved-filter-meta';
      areaMeta.textContent = 'Geographical Areas: ';
      savedFilterAreaSummaryParts(savedFilter).forEach(([kind, label, value], index) => {
        const areaValue = document.createElement('strong');
        areaValue.className = `saved-filter-area-summary saved-filter-area-summary-${kind}`;
        areaValue.textContent = value;
        areaMeta.append(`${index ? ' · ' : ''}${label}: `, areaValue);
      });
      const trendMeta = document.createElement('span');
      trendMeta.className = 'saved-filter-meta';
      const trendValue = document.createElement('strong');
      trendValue.className = 'saved-filter-area-summary saved-filter-area-summary-campaigns';
      trendValue.textContent = savedFilterTrendCampaigns(savedFilter);
      const timeValue = document.createElement('strong');
      timeValue.className = 'saved-filter-area-summary saved-filter-area-summary-time';
      timeValue.textContent = savedFilterTimeSplit(savedFilter);
      trendMeta.append('Scoring Trends: Campaigns: ', trendValue, ' · Time split: ', timeValue);
      const cdrNames = savedFilterCdrNames(savedFilter);
      const cdrButton = document.createElement('button');
      cdrButton.type = 'button';
      cdrButton.className = 'saved-filter-cdrs';
      cdrButton.dataset.savedFilterCdrs = id;
      const cdrCount = cdrNames.length || (savedFilter.dataset_ids || []).length;
      cdrButton.textContent = cdrCount ? `${cdrCount} CDR${cdrCount === 1 ? '' : 's'}` : 'Selected CDRs';
      cdrButton.title = cdrNames.length ? cdrNames.join('\n') : savedFilterCdrSummary(savedFilter);
      cdrButton.setAttribute('aria-label', `Show the CDRs of Saved Filter ${id}`);
      const profileName = valueOf(savedFilter, ['scoring_profile_name', 'profile_name'], '');
      let profileMeta = null;
      if (profileName) {
        profileMeta = document.createElement('span');
        profileMeta.className = 'saved-filter-meta';
        profileMeta.textContent = 'Scoring Methodology: ';
        const profileValue = document.createElement('strong');
        profileValue.className = 'saved-filter-profile';
        // By campaign (NetCheck 2026: 2026-Q1, 2026-Q2 · …): By campaign is the pill, followed by the methodologies,
        // with the campaigns of each one in their own colour.
        const byCampaign = /^By campaign \((.*)\)$/.exec(profileName);
        profileValue.textContent = byCampaign ? 'By campaign' : profileName;
        profileMeta.append(profileValue);
        if (byCampaign) {
          const detail = document.createElement('span');
          detail.className = 'saved-filter-profile-detail';
          detail.append(' (');
          byCampaign[1].split(' · ').forEach((part, index) => {
            if (index) detail.append(' · ');
            const split = part.lastIndexOf(': ');
            if (split < 0) {
              detail.append(part);
              return;
            }
            const campaigns = document.createElement('span');
            campaigns.className = 'saved-filter-profile-campaigns';
            // Each campaign as the workspace Campaign Maps name it.
            campaigns.textContent = part.slice(split + 2).split(', ')
              .map(value => hierarchyDisplayValue({level: 'Campaign', value})).join(', ');
            detail.append(part.slice(0, split + 2), campaigns);
          });
          detail.append(')');
          profileMeta.append(detail);
        }
      }
      // The Split by, the GAP reference, the methodology, then the Geographical Areas and the Scoring Trends.
      button.append(...[aggregation, meta, profileMeta, areaMeta, trendMeta].filter(Boolean));
      const duration = savedFilterDurationText(savedFilter);
      if (duration) {
        // How long the calculation took, or has taken so far while it runs.
        const durationMeta = document.createElement('span');
        durationMeta.className = 'saved-filter-meta';
        durationMeta.textContent = isActive(savedFilter) ? 'Elapsed: ' : 'Calculation time: ';
        const durationValue = document.createElement('strong');
        durationValue.className = 'saved-filter-duration';
        durationValue.textContent = duration;
        durationMeta.append(durationValue);
        button.append(durationMeta);
      }
      if (isActive(savedFilter)) {
        const progress = document.createElement('span');
        progress.className = 'saved-filter-progress';
        progress.setAttribute('aria-label', `Calculation ${progressValue(savedFilter)} percent complete`);
        const bar = document.createElement('span');
        bar.style.width = `${progressValue(savedFilter)}%`;
        progress.append(bar);
        button.append(progress);
      }
      // How many times it has been used (calculated or opened) and calculated, on one line.
      const times = count => `${count} time${count === 1 ? '' : 's'}`;
      const uses = Number(savedFilter.use_count || 1);
      const calculations = Number(savedFilter.calculation_count || 0);
      const useMeta = document.createElement('span');
      useMeta.className = 'saved-filter-meta';
      const useValue = document.createElement('strong');
      useValue.className = 'saved-filter-uses';
      useValue.textContent = times(uses);
      const calculationValue = document.createElement('strong');
      calculationValue.className = 'saved-filter-calculations';
      calculationValue.textContent = times(calculations);
      const calculationLabel = document.createElement('span');
      calculationLabel.textContent = ' · Calculated: ';
      useMeta.textContent = 'Used: ';
      useMeta.append(useValue, calculationLabel, calculationValue);
      button.append(useMeta);
      const missing = Array.isArray(savedFilter.missing_cdrs) ? savedFilter.missing_cdrs.filter(Boolean) : [];
      if (missing.length) {
        // Filters imported from another workspace wait until their CDRs are processed here.
        const waiting = document.createElement('span');
        waiting.className = 'saved-filter-meta saved-filter-waiting';
        waiting.textContent = `Waiting for its CDRs: ${missing.join(', ')}`;
        button.append(waiting);
      }
      const newer = Array.isArray(savedFilter.newer_cdrs) ? savedFilter.newer_cdrs : [];
      if (newer.length) {
        // A Final CDR (or a newer cumulative one) replaces some of its CDRs.
        const notice = document.createElement('span');
        notice.className = 'saved-filter-meta saved-filter-newer';
        notice.textContent = `Newer CDRs available: ${newer.map(item => `${item.replaced_by_name} replaces ${item.name}`).join('; ')}`;
        button.append(notice);
      }
      const error = valueOf(savedFilter, ['error', 'error_message', 'last_error'], '');
      if (status === 'failed' && error) {
        const detail = document.createElement('span');
        detail.className = 'saved-filter-meta';
        detail.textContent = error;
        button.append(detail);
      }
      const row = document.createElement('div');
      row.className = 'saved-filter-row';
      const actions = document.createElement('span');
      actions.className = 'saved-filter-actions';
      if (newer.length) {
        const useNewer = document.createElement('button');
        useNewer.type = 'button';
        useNewer.className = 'saved-filter-use-newer';
        useNewer.dataset.savedFilterNewer = id;
        useNewer.textContent = 'Use newer CDRs';
        useNewer.title = 'Update this Saved Filter with the newer CDRs and calculate it again';
        actions.append(useNewer);
      }
      const pin = document.createElement('button');
      pin.type = 'button';
      pin.className = 'saved-filter-pin';
      pin.dataset.savedFilterPin = id;
      pin.textContent = savedFilter.pinned ? '★' : '☆';
      pin.title = savedFilter.pinned ? 'Unstar this Saved Filter: it leaves the list and goes when another one is calculated or opened'
        : 'Star this Saved Filter to keep it in the list of Saved Filters (first; drag it to move it)';
      pin.setAttribute('aria-label', `${savedFilter.pinned ? 'Unpin' : 'Pin'} Saved Filter ${id}`);
      pin.setAttribute('aria-pressed', String(Boolean(savedFilter.pinned)));
      // Only admins, super-admins and the user who starred it unstar it.
      if (savedFilter.pinned && !(window.canDeleteShared?.(savedFilter.created_by) ?? true)) {
        pin.disabled = true;
        pin.title = 'Only admins and super-admins, or the user who starred it, can unstar this Saved Filter';
      }
      // The identifier of the Saved Filter (as App Events name it), before its buttons.
      const idBadge = document.createElement('span');
      idBadge.className = 'saved-filter-id';
      idBadge.textContent = `Filter ID: ${id}`;
      idBadge.title = `Saved Filter ID ${id}`;
      const rename = document.createElement('button');
      rename.type = 'button';
      rename.className = 'saved-filter-rename';
      rename.dataset.savedFilterRename = id;
      rename.textContent = '✎';
      rename.title = 'Edit this Saved Filter: its name or its filters';
      rename.setAttribute('aria-label', `Edit Saved Filter ${id}`);
      const duplicate = document.createElement('button');
      duplicate.type = 'button';
      duplicate.className = 'saved-filter-duplicate';
      duplicate.dataset.savedFilterDuplicate = id;
      duplicate.textContent = '⧉';
      duplicate.title = 'Duplicate this Saved Filter: change the filters of a copy and save it as a new Favourites Filter';
      duplicate.setAttribute('aria-label', `Duplicate Saved Filter ${id}`);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'saved-filter-delete';
      remove.dataset.deleteSavedFilterId = id;
      remove.textContent = '×';
      remove.title = 'Delete this Saved Filter and its result';
      remove.setAttribute('aria-label', `Delete Saved Filter ${id}`);
      // Only admins, super-admins and the user who created it delete it.
      const deletable = window.canDeleteShared?.(savedFilter.created_by) ?? true;
      remove.disabled = deletingSavedFilterIds.has(id) || !deletable;
      if (!deletable) remove.title = window.sharedDeleteRefusal('Saved Filter');
      actions.append(cdrButton, idBadge, rename, duplicate, pin, remove);
      // Use Filter makes it the Saved Filter of the module and opens its Scoring; the one in use (selected at the top of
      // the module, with its results shown) has the In Use label instead.
      const inUse = id === selectedSavedFilterId && !selectionUnmatched && !scoringClosed;
      const use = document.createElement(inUse ? 'span' : 'button');
      if (inUse) {
        use.className = 'saved-filter-use saved-filter-in-use';
        use.textContent = 'In Use';
        use.title = 'This Saved Filter is the one selected at the top of the module';
      } else {
        use.type = 'button';
        use.className = 'saved-filter-use';
        use.dataset.savedFilterUse = id;
        use.textContent = 'Use Filter';
        use.title = 'Open the Scoring of this Saved Filter: it becomes the Saved Filter selected at the top of the module';
        use.setAttribute('aria-label', `Use Saved Filter ${id}`);
      }
      // On top of its card: the areas it filters (or Nationwide), then the operators or vendors, and its NR Mode.
      const tabs = document.createElement('span');
      tabs.className = 'saved-filter-tabs';
      for (const scope of savedFilterScopes(savedFilter)) {
        const scopeLabel = document.createElement('span');
        scopeLabel.className = 'saved-filter-scope';
        scopeLabel.dataset.dimension = scope.dimension;
        scopeLabel.textContent = scope.text;
        scopeLabel.title = scope.title;
        tabs.append(scopeLabel);
      }
      const nrMode = String(valueOf(savedFilter, ['nr_mode'], '') || '');
      if (nrMode) {
        const modeLabel = document.createElement('span');
        modeLabel.className = 'saved-filter-mode';
        modeLabel.dataset.nrMode = nrMode === 'NSA+SA' ? 'nsa-vs-sa' : nrMode.toLowerCase();
        modeLabel.title = `NR Mode: ${nrMode === 'NSA+SA' ? 'NSA vs SA' : nrMode}`;
        if (nrMode === 'NSA+SA') {
          for (const [part, mode] of [['NSA', 'nsa'], [' vs ', ''], ['SA', 'sa']]) {
            const piece = document.createElement('span');
            if (mode) piece.dataset.nrMode = mode;
            piece.textContent = part;
            modeLabel.append(piece);
          }
        } else modeLabel.textContent = nrMode;
        tabs.append(modeLabel);
      }
      if (tabs.childElementCount) {
        row.classList.add('has-scope');
        row.append(tabs);
      }
      row.append(button, use, actions);
      row.dataset.savedFilterRow = id;
      if (savedFilter.pinned) savedFilterList.append(row);
      if (id === selectedSavedFilterId) {
        // The selected card of the Scoring Results dropdown, with its CDRs, name and pin buttons (deleting is done in the
        // lists): its name without the fold arrow, and none when it has no name. Folded, it shows its name, the line of
        // its filters and its buttons; Details, before them, unfolds the rest without opening the dropdown.
        const selectedActions = document.createElement('span');
        selectedActions.className = 'saved-filter-actions';
        const details = document.createElement('button');
        details.type = 'button';
        details.className = 'saved-filter-details';
        details.dataset.savedFilterDetails = id;
        details.textContent = 'Details';
        details.title = 'Show or hide the details of this Saved Filter';
        details.setAttribute('aria-expanded', String(selectedSavedFilterUnfolded));
        selectedActions.append(details, ...Array.from(actions.children, child => child.cloneNode(true))
          .filter(child => !child.dataset?.deleteSavedFilterId));
        // Its label on top, as in the lists.
        const cardParts = [tabs.childElementCount ? tabs : null,
          ...Array.from(button.children, child => (child === head ? (savedFilter.name ? name : null) : child))];
        selectedSavedFilterCard.replaceChildren(...cardParts.filter(Boolean).map(child => child.cloneNode(true)), selectedActions);
        selectedCardShown = true;
      }
    }
    if (selectionUnmatched || scoringClosed) {
      selectedSavedFilterCard.replaceChildren(unmatchedSelectionNotice());
      selectedCardShown = false;
    }
    selectedSavedFilterCard.classList.toggle('is-folded', selectedCardShown && !selectedSavedFilterUnfolded);
    // The other selectors show the same card.
    for (const card of selectedSavedFilterCards.slice(1)) {
      card.replaceChildren(...Array.from(selectedSavedFilterCard.childNodes, node => node.cloneNode(true)));
      card.classList.toggle('is-folded', selectedCardShown && !selectedSavedFilterUnfolded);
    }
    // Close Scoring closes the Saved Filter shown, when there is one.
    if (closeScoringButton) closeScoringButton.disabled = scoringClosed || !selectedSavedFilterId;
    syncSavedFilterLists();
    // An open Filter Navigator follows the Favourites Filters (their status, a new one, one deleted).
    if (navigatorDialog?.open) renderSavedFilterNavigator();
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: {Accept: 'application/json', ...(options.body ? {'Content-Type': 'application/json'} : {})},
      ...options,
    });
    const body = response.headers.get('content-type')?.includes('application/json') ? await response.json() : null;
    if (!response.ok) throw new Error(body?.detail || body?.error || `Scoring request failed (HTTP ${response.status}).`);
    return body || {};
  }

  function selectedTableMode() {
    return 'expanded';
  }

  function selectedGapLayout() {
    return gapLayoutSelect?.value === 'adjacent' ? 'adjacent' : 'end';
  }

  function showGapValues() {
    return Boolean(showGapValuesToggle?.checked);
  }

  function syncResultTableControls() {
    const controls = root.querySelector('[data-scoring-results-value-row]');
    if (controls) controls.hidden = activeResultTab !== 'scoring';
  }

  function syncGapValueControls() {
    if (gapLayoutControl) gapLayoutControl.hidden = !showGapValues();
  }

  function appendScoreGapCells(operators, nonBaseline, layout, appendScore, appendGap) {
    if (!showGapValues()) {
      for (const [operatorIndex, operator] of operators.entries()) appendScore(operator, operatorIndex);
      return;
    }
    if (layout === 'adjacent') {
      for (const [operatorIndex, operator] of operators.entries()) {
        appendScore(operator, operatorIndex);
        if (nonBaseline.includes(operator)) appendGap(operator);
      }
      return;
    }
    for (const [operatorIndex, operator] of operators.entries()) appendScore(operator, operatorIndex);
    for (const operator of nonBaseline) appendGap(operator);
  }

  function tableForSelectedMode(tableData) {
    return tableForMode(tableData, selectedTableMode());
  }

  function tableForMode(tableData, mode) {
    if (!tableData || typeof tableData !== 'object') return tableData;
    const rowsKey = mode === 'summary' ? 'category_rows' : 'expanded_rows';
    const totalKey = mode === 'summary' ? 'category_total' : 'expanded_total';
    if (!Array.isArray(tableData[rowsKey])) return tableData;
    const isGapKpiTable = Array.isArray(tableData.rows)
      && (typeof tableData.operator === 'string'
        || tableData.rows.some(row => row?.gaps && !row?.values));
    const total = tableData[totalKey] && typeof tableData[totalKey] === 'object'
      ? tableData[totalKey] : tableData.total;
    return {
      ...tableData,
      _display_mode: mode,
      rows: mode === 'summary' && isGapKpiTable ? tableData.rows : tableData[rowsKey],
      total,
      ...(total && Object.hasOwn(total, 'gap_points') ? {total_gap_points: total.gap_points} : {}),
      ...(total && Object.hasOwn(total, 'gap_partial') ? {total_gap_partial: total.gap_partial} : {}),
      ...(total && Object.hasOwn(total, 'gap_environments') ? {total_gap_environments: total.gap_environments} : {}),
    };
  }

  function effectiveScoring(payload = typeof currentResults === 'undefined' ? null : currentResults) {
    const requested = typeof selectedScoring === 'undefined' ? 'best_network' : selectedScoring;
    return requested === 'most_reliable' && payload?.scorings?.most_reliable ? 'most_reliable' : 'best_network';
  }

  function scoringLabel() {
    return effectiveScoring() === 'most_reliable' ? 'Most Reliable Network' : 'Best Network';
  }

  // The selected scoring's results, in the shape of a Best Network payload.
  function activeScoringPayload(payload = currentResults) {
    if (!payload || effectiveScoring(payload) !== 'most_reliable') return payload;
    const reliable = payload.scorings.most_reliable;
    return {
      ...payload, views: reliable.views || {}, configuration: reliable.configuration,
      notices: reliable.notices || [], warnings: reliable.warnings || [], coverage_notes: reliable.coverage_notes || {},
      environment_scaling: reliable.environment_scaling || null, totals: reliable.totals || [],
      charts: reliable.totals || [], gap_totals: reliable.gap_totals || [], scoring: [], gap: [],
    };
  }

  function activeScoringConfiguration() {
    return effectiveScoring() === 'most_reliable'
      ? activeScoringPayload()?.configuration || {}
      : selectedSavedFilter?.configuration || currentResults?.configuration || {};
  }

  function syncResultScoring(payload) {
    if (!scoringKindControl || !scoringKindSelect) return;
    const available = Boolean(payload?.scorings?.most_reliable);
    scoringKindControl.hidden = !available;
    scoringKindSelect.disabled = !available;
    scoringKindSelect.value = effectiveScoring(payload);
  }

  function setExportLinks(savedFilterId, enabled) {
    // The results hidden by a selection that is no Saved Filter (or closed) are not exported either.
    enabled = enabled && !selectionUnmatched && !(typeof scoringClosed !== 'undefined' && scoringClosed);
    for (const [kind, link] of Object.entries(exportLinks).flatMap(([name, links]) => [links].flat().map(item => [name, item]))) {
      if (!link) continue;
      link.hidden = false;
      link.setAttribute('aria-disabled', String(!enabled));
      link.tabIndex = enabled ? 0 : -1;
      const query = `table_mode=${encodeURIComponent(selectedTableMode())}&gap_layout=${encodeURIComponent(selectedGapLayout())}&environment=${encodeURIComponent(selectedEnvironment || 'all')}`;
      const gapOption = kind === 'ppt' ? `&show_gap_values=${showGapValues() ? 'true' : 'false'}&theme=${encodeURIComponent(activeTheme?.id || 'netcheck')}` : '';
      // CSV files carry the selected scoring; PowerPoint and Word carry both scorings.
      const scoringOption = kind !== 'ppt' && typeof effectiveScoring === 'function'
        && effectiveScoring() === 'most_reliable' ? '&scoring=most_reliable' : '';
      link.href = enabled ? `${exportBase}/${encodeURIComponent(savedFilterId)}/export/${kind}?${query}${gapOption}${scoringOption}` : '#';
    }
  }

  // A progress dialog stays open while the document is generated, then the browser downloads it.
  // Generate Scoring Report (Calculation panel) opens the report editor, which only chooses the content of the report
  // (its scorings, environments and sections): it takes the CDRs, NR Mode, filters, Split by, Geographical Areas &
  // Scoring Trends, GAP reference, methodology and theme of the page.
  async function generateScoringReport() {
    if (!window.ScoringReportEditor) return;
    const selection = calculationPayload();
    if (!selection.dataset_ids.length) {
      const message = 'Select the CDRs of the report in the Calculation panel.';
      if (typeof showInfoDialog === 'function') showInfoDialog(message, {tone: 'warning', title: 'No CDRs selected'});
      else window.alert(message);
      return;
    }
    const filterOptions = Object.fromEntries(contextFilterDefinitions.map(({key}) => [key,
      [...(contextFilterSelects.get(key)?.options || [])].filter(option => option.value && !option.disabled).map(option => option.value)]));
    const defaults = {
      // The report scenarios filter the CDRs of the panel: its campaigns as they are now.
      filters: selectedContextFilters(), levels: selection.aggregation_levels || ['Operator'],
      mainCities: false, operators: filterOptions.Operator || [],
    };
    let state = null;
    try {
      const response = await fetch('/api/scoring/report-configurations', {credentials: 'same-origin'});
      if (response.ok) state = await response.json();
    } catch (_error) {
      state = null;
    }
    const choice = await window.ScoringReportEditor.open({
      title: 'Scoring & GAP Analysis report',
      configuration: state?.last || window.ScoringReportEditor.defaultConfiguration(defaults),
      context: {filterOptions, operators: filterOptions.Operator || [], mainCities, defaults, operatorGroups,
        themes: scoringThemes, theme: activeTheme?.id || 'netcheck', pageScope: true},
      actions: [['word', 'Generate Word'], ['ppt', 'Generate PowerPoint']],
    });
    if (!choice) return;
    // NSA vs SA: the document shows each NR Mode as the results of the page do (NSA vs SA and NSA & SA charts).
    const nrViews = selection.nr_mode === 'NSA+SA' && typeof selectedNrLayout !== 'undefined'
      ? {nr_layout: selectedNrLayout, nr_charts: selectedNrCharts} : {};
    await downloadScoringDocument(`/api/scoring/report/${choice.action}`,
      choice.action === 'word' ? 'Word' : 'PowerPoint', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          configuration: choice.configuration, split_charts: true, dataset_ids: selection.dataset_ids.map(Number),
          // Every scenario takes the filters, Split by and Geographical Areas & Scoring Trends of the Calculation panel.
          context_filters: selection.context_filters, aggregation_levels: selection.aggregation_levels,
          area_summary: selection.area_summary,
          nr_mode: selection.nr_mode, baseline_operator: selection.baseline_operator,
          scoring_profile_id: selection.scoring_profile_id || null, ...nrViews,
        }),
      });
  }

  // Export Selected Scoring Report (Results panel) exports the selected Saved Filter as it was calculated (its
  // CDRs, Split by levels and filters): it only asks for PowerPoint or Word.
  // The scorings and environments the export offers: Best Network and All Environments are ticked; Most Reliable only
  // when the Saved Filter has it, and each environment of its results.
  function scoringExportChoices() {
    const mostReliable = currentResults ? Boolean(currentResults?.scorings?.most_reliable) : true;
    const environments = [...(environmentSelect?.options || [])]
      .filter(option => option.value && option.value !== 'all')
      .map(option => ({value: option.value, label: option.textContent.trim() || option.value}));
    return {mostReliable, environments};
  }

  function scoringExportDialogHtml(message, {mostReliable, environments}) {
    const escape = value => String(value ?? '').replace(/[&<>'"]/g, character => (
      {'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[character]));
    const box = (group, value, label, checked, disabled = false, note = '') => `<label class="scoring-export-choice">`
      + `<input type="checkbox" data-scoring-export-${group} value="${escape(value)}"${checked ? ' checked' : ''}${disabled ? ' disabled' : ''}>`
      + `<span>${escape(label)}${note ? ` <small>${escape(note)}</small>` : ''}</span></label>`;
    return `<p>${escape(message)}</p>`
      + '<fieldset class="scoring-export-choices"><legend>Scorings</legend>'
      + box('scoring', 'best_network', 'Best Network', true)
      + box('scoring', 'most_reliable', 'Most Reliable', false, !mostReliable, mostReliable ? '' : '(not calculated for this Saved Filter)')
      + '</fieldset><fieldset class="scoring-export-choices"><legend>Environments</legend>'
      + box('environment', 'Combined', 'All Environments', true, false, '(all the environments combined)')
      + environments.map(environment => box('environment', environment.value, environment.label, false)).join('')
      // The panels that export the Focus operators (Workspace Config > Scoring Export Panels) can show every operator.
      + '</fieldset><fieldset class="scoring-export-choices"><legend>Operators</legend>'
      + box('all-operators', 'true', 'Export All Operators in Focus panels', false, false, '(every operator in the Focus Operators panels)')
      + '</fieldset>';
  }

  // The sections whose operators the page chooses with its chips, as the export names them.
  // (The route that loses most and the Campaign Comparison always export the operators of their panel.)
  const EXPORT_OPERATOR_SECTIONS = ['summary-operators', 'places-operators', 'ranking-operators', 'gap-parts-operators', 'gap-insight-operators',
    'vendor_losses-operators', 'site_type_losses-operators', 'sites-operators', 'stretches-operators'];

  // The operators chosen in each section ({section: [operators]}); a section never changed is left out, so the export
  // uses its default (as the page does).
  function scoringExportOperators() {
    const chosen = {};
    for (const section of EXPORT_OPERATOR_SECTIONS) {
      let stored = null;
      try { stored = JSON.parse(insightSelections.get(section) || 'null'); } catch (_error) { stored = null; }
      if (Array.isArray(stored) && stored.length) chosen[section] = stored.map(String);
    }
    // The operators enabled or disabled in any section, for the sections never drawn.
    const choices = Object.entries(operatorChoices());
    if (choices.length) {
      chosen._enabled = choices.filter(([, enabled]) => enabled === true).map(([name]) => String(name));
      chosen._disabled = choices.filter(([, enabled]) => enabled === false).map(([name]) => String(name));
    }
    // The operator of Where to act, its owners and places.
    const actOperator = insightSelections.get('act-operator');
    if (actOperator) chosen['act-operator'] = [String(actOperator)];
    return chosen;
  }

  async function exportSelectedScoringReport(link) {
    const message = 'Export the selected scoring report with the CDRs, Split by levels and filters it was calculated with. '
      + 'Choose the scorings and the environments to include.';
    const choices = scoringExportChoices();
    const choice = typeof showConfirmDialog === 'function'
      ? await showConfirmDialog(message, {
        title: 'Export Selected Scoring Report', confirmLabel: 'PowerPoint', secondaryLabel: 'Word', cancelLabel: 'Cancel',
        variant: 'document-format', copyHtml: scoringExportDialogHtml(message, choices),
      })
      : 'confirm';
    if (choice !== 'confirm' && choice !== 'secondary') return;
    const ticked = group => [...document.querySelectorAll(`input[data-scoring-export-${group}]`)]
      .filter(input => input.checked && !input.disabled).map(input => input.value);
    const scorings = typeof showConfirmDialog === 'function' ? ticked('scoring') : ['best_network'];
    const environments = typeof showConfirmDialog === 'function' ? ticked('environment') : ['Combined'];
    if (!scorings.length || !environments.length) {
      const warning = `Tick at least one ${scorings.length ? 'environment' : 'scoring'} to export.`;
      if (typeof showInfoDialog === 'function') showInfoDialog(warning, {title: 'Nothing to export'});
      else window.alert(warning);
      return;
    }
    const url = new URL(link.href, window.location.href);
    if (choice === 'secondary') url.pathname = url.pathname.replace(/\/export\/ppt$/, '/export/word');
    for (const scoring of scorings) url.searchParams.append('scorings', scoring);
    for (const environment of environments) url.searchParams.append('environments', environment);
    if (typeof showConfirmDialog === 'function' && ticked('all-operators').length) url.searchParams.set('all_operators', 'true');
    // The operators enabled in each section of the page: the document shows the same ones.
    const operators = scoringExportOperators();
    if (Object.keys(operators).length) url.searchParams.set('operators', JSON.stringify(operators));
    // NSA vs SA results: the document shows each NR Mode as the page does (NSA vs SA and NSA & SA charts).
    if (typeof nrLayoutControl !== 'undefined' && nrLayoutControl && !nrLayoutControl.hidden) {
      url.searchParams.set('nr_layout', selectedNrLayout);
      url.searchParams.set('nr_charts', selectedNrCharts);
    }
    await downloadScoringDocument(url.href, choice === 'secondary' ? 'Word' : 'PowerPoint');
  }

  async function downloadScoringDocument(href, label, init = {}) {
    globalThis.showLoadingOverlay?.(`Preparing the ${label} document`,
      `Preparing the Scoring & GAP Analysis ${label} of the selected Saved Filter with its tables and charts. The document downloads when it is ready.`);
    try {
      const response = await fetch(href, {credentials: 'same-origin', ...init});
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(typeof payload.detail === 'string' ? payload.detail : `The ${label} export failed.`);
      }
      const disposition = response.headers.get('Content-Disposition') || '';
      const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
      const plain = /filename="([^"]+)"/i.exec(disposition)?.[1];
      const name = encoded ? decodeURIComponent(encoded) : plain || `Scoring & GAP Analysis.${label === 'Word' ? 'docx' : 'pptx'}`;
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = name;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      globalThis.hideLoadingOverlay?.();
      if (typeof showInfoDialog === 'function') showInfoDialog(error.message, {tone: 'error', title: 'The document could not be generated'});
      else window.alert(error.message);
    } finally {
      globalThis.hideLoadingOverlay?.();
    }
  }

  function normalizeRows(data) {
    if (Array.isArray(data)) return data.filter(row => row && typeof row === 'object');
    if (data && Array.isArray(data.rows)) return data.rows.filter(row => row && typeof row === 'object');
    if (data && Array.isArray(data.data)) return data.data.filter(row => row && typeof row === 'object');
    if (data && Array.isArray(data.tables)) return data.tables.flatMap(table => normalizeRows(table));
    return [];
  }

  function humanizeKey(key) {
    return String(key).replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (typeof value === 'number' && Number.isFinite(value)) return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, {maximumFractionDigits: 3});
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  function renderTable(pane, source, emptyCopy, {hideGapColumns = false} = {}) {
    pane.replaceChildren();
    const rows = normalizeRows(source);
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = emptyCopy;
      pane.append(empty);
      return;
    }
    const columns = [...new Set(rows.flatMap(row => Object.keys(row)))].filter(column => (
      !hideGapColumns || showGapValues() || !String(column).toLocaleLowerCase().includes('gap')
    ));
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-table-wrap';
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    for (const column of columns) {
      const th = document.createElement('th');
      th.scope = 'col';
      const isKpiType = ['kpi_type', 'type_of_kpi'].includes(String(column).toLocaleLowerCase());
      th.textContent = isKpiType ? 'Type of KPI' : humanizeKey(column);
      if (isKpiType) th.dataset.column = 'type';
      headerRow.append(th);
    }
    thead.append(headerRow);
    const tbody = document.createElement('tbody');
    for (const row of rows) {
      const tr = document.createElement('tr');
      if (['category', 'total'].includes(String(row?.row_type || '').toLocaleLowerCase())) tr.classList.add('scoring-total-row');
      for (const column of columns) {
        const isKpiType = ['kpi_type', 'type_of_kpi'].includes(String(column).toLocaleLowerCase());
        if (isKpiType) {
          tr.append(createKpiTypeCell(row[column], ['category', 'total'].includes(String(row.row_type || '').toLocaleLowerCase())));
          continue;
        }
        const td = document.createElement('td');
        const value = row[column];
        td.textContent = displayValue(value);
        if (typeof value === 'number' && Number.isFinite(value)) td.dataset.numeric = 'true';
        tr.append(td);
      }
      tbody.append(tr);
    }
    table.append(thead, tbody);
    wrapper.append(table);
    pane.append(wrapper);
  }

  function firstValue(object, names, fallback = null) {
    if (!object || typeof object !== 'object') return fallback;
    for (const name of names) {
      if (Object.prototype.hasOwnProperty.call(object, name) && object[name] !== undefined && object[name] !== '') return object[name];
      const key = Object.keys(object).find(candidate => candidate.toLowerCase() === name.toLowerCase());
      if (key && object[key] !== undefined && object[key] !== '') return object[key];
    }
    return fallback;
  }

  function comparisonIdentity(table, kind) {
    const context = table?.context && typeof table.context === 'object'
      ? Object.fromEntries(Object.entries(table.context).sort(([left], [right]) => left.localeCompare(right)))
      : {};
    return JSON.stringify([kind, table?.title || '', context, table?.operator || '']);
  }

  function gapComparisonIdentity(table, kind) {
    return JSON.stringify([selectedSavedFilterId || currentResultsSavedFilterId || '', kind, comparisonIdentity(table, kind)]);
  }

  function comparisonLabel(table, kind) {
    const context = contextLabel(table?.context);
    if (kind === 'gap' && table?.operator) {
      const operator = operatorPresentation(table, table.operator).label;
      const baseline = operatorPresentation(table, table.baseline_operator || '').label;
      return `${context || 'Overall scope'} · ${operator} vs ${baseline}`;
    }
    return String(table?.title || context || 'Overall scope');
  }

  function contextLabel(context, {environmentPrefix = true} = {}) {
    if (!context || typeof context !== 'object') return '';
    const preferred = ['campaign', 'region', 'cluster', 'city', 'vendor', 'dataset_type', 'environment'];
    const entries = preferred.filter(key => context[key] !== null && context[key] !== undefined && context[key] !== '')
      .map(key => [key, key === 'environment' ? environmentLabel(String(context[key]))
        : key === 'campaign' ? hierarchyDisplayValue({level: 'Campaign', value: context[key]}) : context[key]]);
    for (const [key, value] of Object.entries(context)) {
      if (!preferred.includes(key) && value !== null && value !== undefined && value !== '') entries.push([key, key === 'environment' ? environmentLabel(String(value)) : value]);
    }
    return entries.map(([key, value]) => key === 'environment' && !environmentPrefix
      ? String(value) : `${humanizeKey(key)}: ${value}`).join(' · ');
  }

  function appendContextHeader(pane, table, kind, titlePrefix = '') {
    const heading = document.createElement('h4');
    heading.className = 'scoring-context-heading';
    heading.textContent = titlePrefix || (kind === 'gap' || kind === 'gap-summary' ? 'GAP Analysis' : 'Scoring Tables');
    const context = table?.context && typeof table.context === 'object' ? table.context : {};
    const environment = context.environment;
    if (environment !== null && environment !== undefined && environment !== '') {
      const separator = document.createElement('span');
      separator.className = 'scoring-context-separator';
      separator.ariaHidden = 'true';
      separator.textContent = '—';
      const environmentChip = document.createElement('span');
      environmentChip.className = 'scoring-context-chip scoring-environment-chip';
      environmentChip.textContent = `Environment: ${environmentLabel(String(environment))}`;
      heading.append(separator, environmentChip);
    }
    if (kind === 'gap' || kind === 'gap-summary') appendResultScope(heading, context);
    pane.append(heading);

    const preferred = ['campaign', 'region', 'cluster', 'city', 'vendor', 'dataset_type', 'environment'];
    const entries = preferred.filter(key => key !== 'environment' && context[key] !== null && context[key] !== undefined && context[key] !== '')
      .map(key => [key, key === 'environment' ? environmentLabel(String(context[key]))
        : key === 'campaign' ? hierarchyDisplayValue({level: 'Campaign', value: context[key]}) : context[key]]);
    for (const [key, value] of Object.entries(context)) {
      if (!preferred.includes(key) && value !== null && value !== undefined && value !== '') entries.push([key, key === 'environment' ? environmentLabel(String(value)) : value]);
    }
    if (entries.length) {
      const chips = document.createElement('div');
      chips.className = 'scoring-context-chips';
      for (const [key, value] of entries) {
        const chip = document.createElement('span');
        chip.className = 'scoring-context-chip';
        chip.textContent = `${humanizeKey(key)}: ${value}`;
        chips.append(chip);
      }
      pane.append(chips);
    }
    const note = table?.coverage_note ?? table?.note ?? '';
    if (note) {
      const coverage = document.createElement('p');
      coverage.className = 'scoring-context-note';
      coverage.textContent = typeof note === 'string' ? note : displayValue(note);
      pane.append(coverage);
    }
  }

  function appendComparisonSelector(pane, tables, kind, contextSource = 'tables') {
    const savedSelection = contextSelections.get(kind);
    let selected = tables.find(table => comparisonIdentity(table, kind) === savedSelection) || tables[0];
    if (tables.length > 1) {
      const controls = document.createElement('div');
      controls.className = 'scoring-comparison-controls';
      const label = document.createElement('label');
      label.textContent = kind === 'gap' ? 'Comparison context and operator' : 'Comparison context';
      const select = document.createElement('select');
      select.dataset.comparisonContext = '';
      select.dataset.contextKind = kind;
      select.dataset.contextSource = contextSource;
      for (const [index, table] of tables.entries()) {
        const option = document.createElement('option');
        option.value = String(index);
        option.textContent = comparisonLabel(table, kind);
        option.dataset.contextIdentity = comparisonIdentity(table, kind);
        option.selected = table === selected;
        select.append(option);
      }
      label.append(select);
      controls.append(label);
      pane.append(controls);
    }
    if (selected) contextSelections.set(kind, comparisonIdentity(selected, kind));
    return selected;
  }

  function operatorValue(values, operator) {
    return firstValue(values, [operator], null);
  }

  function isReferenceOperator(table, rawName) {
    const baseline = String(table?.baseline_operator || '');
    return Boolean(baseline && String(rawName).toLowerCase() === baseline.toLowerCase());
  }

  function markReferenceHeader(header) {
    header.classList.add('scoring-reference-header');
    const label = header.textContent.trim();
    header.setAttribute('aria-label', `${label}, reference operator`);
    header.title = `${label} is the reference operator`;
  }

  function operatorPresentation(operatorStyles, rawName) {
    const styles = operatorStyles?.operator_styles && typeof operatorStyles.operator_styles === 'object'
      ? operatorStyles.operator_styles
      : operatorStyles;
    const configured = firstValue(styles, [rawName], null);
    if (!configured || typeof configured !== 'object') return {label: String(rawName), color: '', position: null};
    const position = Number(firstValue(configured, ['position'], Number.NaN));
    return {
      label: String(firstValue(configured, ['label', 'canonical'], rawName)),
      color: safeHexColor(firstValue(configured, ['color'], '')),
      position: Number.isFinite(position) ? position : null,
    };
  }

  function readableTextColor(background) {
    const color = safeHexColor(background);
    if (!color) return '';
    const red = Number.parseInt(color.slice(1, 3), 16);
    const green = Number.parseInt(color.slice(3, 5), 16);
    const blue = Number.parseInt(color.slice(5, 7), 16);
    const luminance = (red * 299 + green * 587 + blue * 114) / 1000;
    return luminance > 155 ? '#203744' : '#ffffff';
  }

  function formatMatrixNumber(value, signed = false) {
    if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) return 'N/A*';
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 'N/A*';
    if (signed && numeric > 0) return `+${numeric.toFixed(2)}`;
    if (signed && numeric < 0) return `−${Math.abs(numeric).toFixed(2)}`;
    return numeric.toFixed(2);
  }

  function formatScoreCell(cell) {
    if (!cell || typeof cell !== 'object') return {text: 'N/A*', complete: false};
    // A KPI the methodology of the campaign does not have (By campaign).
    if (cell.not_applicable) return {text: 'N/A', complete: true};
    const points = firstValue(cell, ['points', 'weighted_points', 'weighted_score'], null);
    const complete = firstValue(cell, ['complete', 'complete_coverage'], false) === true;
    if (points === null || points === undefined || (typeof points === 'string' && points.trim() === '')) return {text: 'N/A*', complete: false};
    const numeric = Number(points);
    if (!Number.isFinite(numeric)) return {text: 'N/A*', complete: false};
    return {text: `${numeric.toFixed(2)}${complete ? '' : '*'}`, complete};
  }

  function formatRawKpiValue(value) {
    if (value === null || value === undefined || (typeof value === 'string' && value.trim() === '')) return 'N/A*';
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    return String(value);
  }

  function createKpiTypeCell(value, neutral = false) {
    const cell = document.createElement('td');
    cell.className = 'scoring-kpi-type-cell';
    cell.dataset.column = 'type';
    const rawType = String(value ?? '').trim();
    const normalized = rawType.toLocaleLowerCase();
    if (neutral) {
      cell.textContent = '—';
      cell.dataset.kpiType = 'neutral';
    } else if (normalized === 'reliable' || normalized === 'diff') {
      cell.textContent = rawType;
      cell.dataset.kpiType = normalized;
    } else {
      cell.textContent = rawType && normalized !== 'unknown' ? rawType : 'Not classified';
      cell.dataset.kpiType = 'neutral';
    }
    return cell;
  }

  function fitScoringValueCells(table) {
    if (!table?.isConnected) return;
    const measurement = document.createElement('canvas').getContext('2d');
    if (!measurement) return;
    for (const cell of table.querySelectorAll('tbody td[data-numeric="true"], tfoot td[data-numeric="true"]')) {
      cell.style.fontSize = '';
      const styles = window.getComputedStyle(cell);
      const fontSize = Number.parseFloat(styles.fontSize);
      const available = cell.clientWidth - Number.parseFloat(styles.paddingLeft) - Number.parseFloat(styles.paddingRight);
      if (!Number.isFinite(fontSize) || available <= 0) continue;
      measurement.font = styles.font;
      const contentWidth = measurement.measureText(cell.textContent.trim()).width;
      if (contentWidth <= 0 || available <= contentWidth * 1.05) continue;
      // How much larger than their font the values may grow to fill their cells depends on the theme.
      const scale = Math.min(Number(activeTheme?.value_scale) || 1.65, available / (contentWidth * 1.05));
      cell.style.fontSize = `${Math.round(fontSize * scale * 10) / 10}px`;
    }
  }

  function observeScoringValueCells(table, wrapper) {
    if (typeof ResizeObserver !== 'function') {
      window.requestAnimationFrame(() => fitScoringValueCells(table));
      return;
    }
    const observer = new ResizeObserver(() => window.requestAnimationFrame(() => fitScoringValueCells(table)));
    scoringValueObservers.set(wrapper, observer);
    observer.observe(wrapper);
  }

  function disconnectScoringValueObservers(pane) {
    for (const [wrapper, observer] of scoringValueObservers) {
      if (!pane.contains(wrapper)) continue;
      observer.disconnect();
      scoringValueObservers.delete(wrapper);
    }
  }

  function safeHexColor(value) {
    const color = String(value ?? '').trim();
    return /^#[0-9a-f]{6}$/i.test(color) ? color : '';
  }

  function appendThresholdLegend(pane, legend) {
    if (!Array.isArray(legend) || !legend.length) return;
    const container = document.createElement('div');
    container.className = 'scoring-threshold-legend';
    const title = document.createElement('strong');
    title.textContent = 'KPI score bands';
    container.append(title);
    for (const entry of legend) {
      const color = safeHexColor(entry?.color);
      const label = String(entry?.band || entry?.label || 'Not classified');
      const item = document.createElement('span');
      item.className = 'scoring-legend-item';
      const swatch = document.createElement('span');
      swatch.className = 'scoring-legend-swatch';
      // The themes draw the swatch of a band as its cells (scoring.html).
      swatch.dataset.band = label;
      if (color) swatch.style.backgroundColor = themedColor(color);
      swatch.setAttribute('aria-hidden', 'true');
      const copy = document.createElement('span');
      copy.className = 'scoring-legend-copy';
      const band = document.createElement('strong');
      band.textContent = label;
      copy.append(band);
      const definition = entry?.definition ?? entry?.description ?? entry?.range ?? '';
      if (definition) {
        const detail = document.createElement('small');
        detail.textContent = String(definition);
        copy.append(detail);
        item.title = String(definition);
      }
      item.append(swatch, copy);
      container.append(item);
    }
    pane.append(container);
  }

  function appendOperatorRankingLegend(pane) {
    const container = document.createElement('div');
    container.className = 'scoring-threshold-legend scoring-operator-ranking-legend';
    for (const [label, color] of [['Best operator', activeTheme.best || '#C6EFCE'], ['Worst operator', activeTheme.worst || '#FFC7CE']]) {
      const item = document.createElement('span');
      item.className = 'scoring-legend-item';
      const swatch = document.createElement('span');
      swatch.className = 'scoring-legend-swatch';
      swatch.style.backgroundColor = color;
      swatch.setAttribute('aria-hidden', 'true');
      const copy = document.createElement('strong');
      copy.textContent = label;
      item.append(swatch, copy);
      container.append(item);
    }
    pane.append(container);
  }

  function summaryOperatorColors(values, columns) {
    const entries = [];
    for (const column of columns) {
      const cell = operatorValue(values, column.id);
      const points = firstValue(cell, ['points', 'weighted_points', 'weighted_score'], null);
      if (points === null || points === undefined || (typeof points === 'string' && !points.trim())) continue;
      const numeric = Number(points);
      if (!Number.isFinite(numeric)) continue;
      entries.push({id: column.id, points: numeric});
    }
    const colors = new Map();
    if (entries.length >= 2) {
      const maximum = Math.max(...entries.map(entry => entry.points));
      const minimum = Math.min(...entries.map(entry => entry.points));
      for (const entry of maximum === minimum ? [] : entries) {
        if (entry.points === maximum) colors.set(entry.id, activeTheme.best || '#C6EFCE');
        else if (entry.points === minimum) colors.set(entry.id, activeTheme.worst || '#FFC7CE');
      }
    }
    return colors;
  }

  function appendScoringGapScale(pane, tableData) {
    if (!showGapValues()) return;
    const maximum = Number(tableData?.gap_scale_max);
    if (!Number.isFinite(maximum) || maximum <= 0) return;
    const colors = tableData?.gap_scale_colors && typeof tableData.gap_scale_colors === 'object' ? tableData.gap_scale_colors : {};
    const negativeColor = themedColor(safeHexColor(firstValue(colors, ['loss', 'negative'], '')));
    const neutralColor = themedColor(safeHexColor(firstValue(colors, ['zero', 'neutral'], '')));
    const positiveColor = themedColor(safeHexColor(firstValue(colors, ['advantage', 'positive'], '')));
    const container = document.createElement('div');
    container.className = 'scoring-gap-scale';
    const label = document.createElement('span');
    label.textContent = 'GAP color scale';
    if (negativeColor && neutralColor && positiveColor) {
      const bar = document.createElement('span');
      bar.className = 'scoring-gap-scale-bar';
      bar.style.background = `linear-gradient(90deg, ${negativeColor}, ${neutralColor} 50%, ${positiveColor})`;
      bar.setAttribute('aria-hidden', 'true');
      container.append(label, bar);
    } else {
      container.append(label);
    }
    const scale = document.createElement('span');
    scale.textContent = `Context scale: −${maximum.toFixed(2)} (operator trails) · 0 · +${maximum.toFixed(2)} (operator leads)`;
    container.append(scale);
    pane.append(container);
  }

  function appendPriorityGapScale(pane, tableData, rows) {
    const maximum = Number(tableData?.gap_scale_max);
    if (!Number.isFinite(maximum) || maximum <= 0 || !rows.length) return;
    const colors = tableData?.gap_scale_colors && typeof tableData.gap_scale_colors === 'object' ? tableData.gap_scale_colors : {};
    const neutralColor = themedColor(safeHexColor(firstValue(colors, ['zero', 'neutral'], '')));
    const positiveColor = themedColor(safeHexColor(firstValue(colors, ['advantage', 'positive'], '')));
    const negativeColor = themedColor(safeHexColor(firstValue(colors, ['loss', 'negative'], '')));
    const container = document.createElement('div');
    container.className = 'scoring-gap-scale scoring-gap-scale-positive';
    const label = document.createElement('span');
    label.textContent = 'GAP color scale';
    container.append(label);
    if (neutralColor && positiveColor && negativeColor) {
      const bar = document.createElement('span');
      bar.className = 'scoring-gap-scale-bar';
      bar.style.background = `linear-gradient(90deg, ${negativeColor}, ${neutralColor} 50%, ${positiveColor})`;
      bar.setAttribute('aria-hidden', 'true');
      container.append(bar);
    }
    const scale = document.createElement('span');
    scale.textContent = `−${maximum.toFixed(2)} (operator trails) · 0 · +${maximum.toFixed(2)} (operator leads)`;
    container.append(scale);
    pane.append(container);
  }

  function styleIncompleteValue(element) {
    if (element.textContent === 'N/A') element.textContent = 'N/A*';
    if (!element.textContent.endsWith('*')) return;
    element.style.color = '#c62828';
    element.style.fill = '#c62828';
    element.style.fontWeight = '700';
  }

  function addMatrixScoreCell(row, cell, className = '', isTotal = false, summaryColor = null) {
    const td = document.createElement('td');
    td.dataset.numeric = 'true';
    td.dataset.column = 'score';
    const formatted = formatScoreCell(cell);
    td.textContent = formatted.text;
    if (className) td.className = className;
    styleIncompleteValue(td);
    const band = firstValue(cell, ['threshold_band', 'band'], '');
    const color = themedColor(safeHexColor(firstValue(cell, ['color', 'threshold_color'], '')));
    if (!isTotal && color) td.style.backgroundColor = color;
    if (!isTotal && band) {
      td.classList.add('scoring-band-cell');
      td.dataset.band = band;
    }
    if (isTotal && !formatted.complete) {
      td.classList.add('scoring-total-partial');
      td.style.backgroundColor = '#e6e9ea';
    }
    const score = firstValue(cell, ['score', 'score_fraction'], null);
    const scoreNumber = score === null || score === undefined || (typeof score === 'string' && score.trim() === '') ? Number.NaN : Number(score);
    const scoreLabel = Number.isFinite(scoreNumber)
      ? `KPI score ${((scoreNumber <= 1 ? scoreNumber * 100 : scoreNumber)).toFixed(2)}%.`
      : '';
    const bandLabel = band ? `Band: ${band}. ` : '';
    if (!formatted.complete) {
      td.title = isTotal
        ? 'Partial total: KPI or environment coverage is incomplete. This is not a full score.'
        : `Partial score: expected KPI or environment coverage is incomplete. This is not a full score. ${bandLabel}${scoreLabel}`.trim();
    } else if (band || scoreLabel) {
      td.title = `${bandLabel}${scoreLabel}`.trim();
    }
    if (summaryColor !== null) {
      td.style.backgroundColor = summaryColor;
      if (summaryColor) td.dataset.operatorRank = summaryColor === (activeTheme.best || '#C6EFCE') ? 'best' : 'worst';
    }
    row.append(td);
  }

  function partialGapCoverage(partial, environments) {
    if (!partial) return '';
    const names = uniqueCatalogueValues(Array.isArray(environments) ? environments : []);
    return names.length
      ? `Partial GAP coverage: the arithmetic comparison is based only on ${names.join(', ')}.`
      : 'Partial GAP coverage: the arithmetic comparison uses only the available weighted environments.';
  }

  function addMatrixGapCell(row, value, color = '', partial = false, environments = []) {
    const td = document.createElement('td');
    td.dataset.numeric = 'true';
    td.dataset.column = 'gap';
    const numeric = value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
    td.textContent = `${formatMatrixNumber(value, true)}${partial && numeric ? '*' : ''}`;
    styleIncompleteValue(td);
    const safeColor = themedColor(safeHexColor(color));
    if (safeColor) td.style.backgroundColor = safeColor;
    const partialNote = partialGapCoverage(partial, environments);
    if (partialNote) td.title = partialNote;
    if (numeric) {
      const numericValue = Number(value);
      const direction = numericValue > 0
        ? 'Positive GAP: the compared operator scores higher than the baseline for this KPI.'
        : numericValue < 0 ? 'Negative GAP: the compared operator scores lower than the baseline for this KPI.' : 'No GAP difference from the baseline.';
      td.title = [direction, partialNote].filter(Boolean).join(' ');
      if (numericValue > 0) {
        td.className = 'scoring-gap-gain';
      } else if (numericValue < 0) {
        td.className = 'scoring-gap-loss';
      }
      const share = gapShare(color);
      td.dataset.gap = numericValue > 0 ? 'gain' : numericValue < 0 ? 'loss' : 'zero';
      td.style.setProperty('--gap-share', share.toFixed(3));
      if (share >= .45) td.dataset.gapStrong = 'true';
    } else {
      td.dataset.gap = 'none';
    }
    row.append(td);
  }

  function appendGapTotals(table, rows, columnIds) {
    const footer = document.createElement('tfoot');
    const row = document.createElement('tr');
    row.className = 'scoring-total-row';
    row.style.fontWeight = '700';
    const label = document.createElement('td');
    label.colSpan = 3;
    label.textContent = 'Total KPI GAP';
    label.style.backgroundColor = themedColor('#D7E0E5');
    row.append(label);
    for (const columnId of columnIds) {
      const values = rows.map(item => columnId === null ? item?.gap_points : item?.gaps?.[columnId]);
      const valid = values.filter(value => value !== null && value !== undefined && value !== ''
        && Number.isFinite(Number(value))).map(Number);
      const partial = valid.length < values.length || rows.some(item => columnId === null
        ? item?.gap_partial === true : item?.gap_partial?.[columnId] === true);
      addMatrixGapCell(row, valid.length ? valid.reduce((sum, value) => sum + value, 0) : null,
        '#D7E0E5', partial);
      row.lastElementChild.title = 'Sum of available KPI GAP points in this column.'
        + (partial ? ' Incomplete coverage: some KPI contributions are missing or partial.' : '');
    }
    footer.append(row);
    table.append(footer);
  }

  // ``latestValuesForRow`` (the GAPs of the latest campaign) orders first; ``valuesForRow`` (every GAP shown) breaks
  // the ties and orders the KPIs without a GAP in the latest campaign, which go after the others.
  function orderGapRows(rows, valuesForRow, sortByGap = true, latestValuesForRow = null) {
    const gapMean = (item, valuesOf) => {
      const values = valuesOf(item)
        .filter(value => value !== null && value !== undefined
          && typeof value !== 'boolean' && String(value).trim() !== '')
        .map(Number).filter(Number.isFinite);
      return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    };
    const compare = (left, right) => {
      for (const valuesOf of [latestValuesForRow, valuesForRow].filter(Boolean)) {
        const leftGap = gapMean(left, valuesOf);
        const rightGap = gapMean(right, valuesOf);
        if (leftGap === null && rightGap === null) continue;
        if (leftGap === null) return 1;
        if (rightGap === null) return -1;
        if (leftGap !== rightGap) return leftGap - rightGap;
      }
      return 0;
    };
    const kpis = rows.filter(item => item?.row_type !== 'category');
    if (sortByGap) kpis.sort(compare);
    return kpis;
  }

  // The hierarchy columns of the latest campaign (all of them when they have one campaign or none).
  function latestCampaignColumns(columns) {
    const campaign = column => (Array.isArray(column?.path) ? column.path : []).find(item => item?.level === 'Campaign')?.value;
    const campaigns = [...new Set(columns.map(campaign).filter(value => value !== undefined && value !== null && value !== ''))];
    if (campaigns.length <= 1) return columns;
    const latest = campaigns.reduce((best, value) => (insightCampaignKey(value) > insightCampaignKey(best) ? value : best));
    return columns.filter(column => campaign(column) === latest);
  }

  function applyGapCategoryRunColors(tbody) {
    // The category runs alternate two shades of the group colour of the theme.
    const colors = [activeTheme.group || '#edf3f8', activeTheme.group_alt || '#e3ecf3'];
    [...tbody.querySelectorAll('td.scoring-category-cell')].forEach((cell, index) => {
      cell.style.setProperty('--run-color', colors[index % colors.length]);
    });
  }

  function appendGapOrderNotice(parent, sortByGap = true) {
    if (!sortByGap) return;
    const notice = document.createElement('p');
    notice.className = 'scoring-priority-order-notice';
    const text = document.createElement('strong');
    text.textContent = sortByGap === 'latest' ? 'KPIs are ordered by GAP in the latest campaign, from lowest to highest.'
      : 'KPIs are ordered by GAP, from lowest to highest.';
    notice.append(text);
    parent.append(notice);
  }

  function appendGapScaleAside(parent, tableData, rows, sortByGap = true) {
    parent.style.display = 'flex';
    parent.style.alignItems = 'center';
    parent.style.flexWrap = 'wrap';
    parent.style.gap = '.55rem 1rem';
    parent.style.marginBottom = '.55rem';
    const explanation = parent.querySelector('.scoring-context-note');
    if (explanation) {
      explanation.style.flex = '1 1 30rem';
      explanation.style.margin = '0';
    }
    const aside = document.createElement('div');
    aside.className = 'scoring-gap-info-aside';
    aside.style.display = 'flex';
    aside.style.flexDirection = 'column';
    aside.style.alignItems = 'flex-end';
    aside.style.gap = '.15rem';
    aside.style.marginLeft = 'auto';
    appendGapOrderNotice(aside, sortByGap);
    const notice = aside.querySelector('.scoring-priority-order-notice');
    if (notice) notice.style.cssText = 'margin: 0; text-align: right;';
    appendPriorityGapScale(aside, tableData, rows);
    const scale = aside.querySelector('.scoring-gap-scale');
    if (scale) scale.style.cssText = 'margin: 0; justify-content: flex-end;';
    parent.append(aside);
  }

  function scorecardNumber(text) {
    const number = Number.parseFloat(String(text ?? '').replace('−', '-').replace(/[^0-9.+-]/g, ''));
    return Number.isFinite(number) ? number : null;
  }

  // The KPI cell of the scorecard: the badge of its type, its name and, quietly, its weight and maximum.
  function decorateScorecardLabel(cell, {type = '', typeLabel = '', weight = '', maximum = '', category = ''} = {}) {
    const name = document.createElement('span');
    name.className = 'scoring-kpi-name';
    name.textContent = cell.textContent.trim();
    cell.replaceChildren();
    cell.classList.add('scoring-kpi-label');
    if (category) {
      const tag = document.createElement('span');
      tag.className = 'scoring-kpi-category';
      tag.textContent = category;
      cell.append(tag);
    }
    if (type === 'reliable' || type === 'diff') {
      const badge = document.createElement('span');
      badge.className = 'scoring-kpi-badge';
      badge.dataset.kpiType = type;
      badge.textContent = type === 'reliable' ? 'R' : 'D';
      badge.title = `${typeLabel || type} KPI`;
      cell.append(badge);
    }
    cell.append(name);
    const meta = [weight && weight !== 'N/A*' ? `${weight}%` : '', maximum && maximum !== 'N/A*' ? `${maximum} pts` : '']
      .filter(Boolean).join(' · ');
    if (meta) {
      const detail = document.createElement('span');
      detail.className = 'scoring-kpi-meta';
      detail.textContent = meta;
      cell.append(detail);
    }
    const description = [typeLabel && typeLabel !== '—' ? `${typeLabel} KPI` : '', weight && weight !== 'N/A*' ? `weight ${weight}%` : '',
      maximum && maximum !== 'N/A*' ? `maximum ${maximum} points` : ''].filter(Boolean).join(' · ');
    if (description) cell.title = [cell.title, description].filter(Boolean).join(' — ');
  }

  // A row of the scorecard: the type, weight and maximum move into the KPI cell, and every score keeps the share of
  // its maximum (the bar or tile the theme draws) and every score and GAP its colour (the tint the theme may use).
  function decorateScorecardRow(row) {
    const cells = [...row.cells];
    const column = name => cells.find(cell => cell.dataset.column === name);
    const type = column('type');
    const weight = column('weight');
    const maximum = column('maximum');
    let label = column('kpi');
    if (!label) {
      label = cells.find(cell => !cell.dataset.column || cell.dataset.column === 'category');
      if (!label) return;
      label.dataset.column = 'kpi';
    }
    const info = {
      type: type?.dataset.kpiType || '',
      typeLabel: type?.textContent.trim() || '',
      weight: weight?.textContent.trim() || '',
      maximum: maximum?.textContent.trim() || '',
    };
    for (const cell of [type, weight, maximum, column('category')]) {
      if (cell && cell !== label) cell.remove();
    }
    label.colSpan = 1;
    label.style.removeProperty('background-color');
    decorateScorecardLabel(label, info);
    const maximumPoints = scorecardNumber(info.maximum);
    for (const cell of [...row.cells]) {
      if (cell.dataset.column !== 'score' && cell.dataset.column !== 'gap') continue;
      const tint = cell.style.backgroundColor;
      if (tint) {
        cell.style.setProperty('--cell-tint', tint);
        cell.style.removeProperty('background-color');
      }
      const points = scorecardNumber(cell.textContent);
      if (cell.dataset.column === 'score' && points !== null && maximumPoints) {
        cell.style.setProperty('--share', Math.max(0, Math.min(1, points / maximumPoints)).toFixed(3));
      }
      // The figure of a GAP with a bar in a span of its own, so the themes that draw the bar behind it can set it
      // beside the zero line, on the side the bar leaves free.
      if ((cell.dataset.gap === 'gain' || cell.dataset.gap === 'loss') && !cell.querySelector('.scoring-gap-figure')) {
        const figure = document.createElement('span');
        figure.className = 'scoring-gap-figure';
        figure.dataset.figure = cell.textContent;
        figure.append(...cell.childNodes);
        cell.append(figure);
      }
    }
  }

  // The tables of Scoring Tables and GAP Analysis read as a scorecard: no Category, Type, Weight or Max columns, each
  // category opens its own section (its subtotal, when the table has one) and the header starts with the operators.
  // When the KPIs are ordered by GAP, their categories are no longer together, so each KPI carries its category.
  function applyScorecardLayout(table) {
    if (!table?.tHead) return;
    table.classList.add('scoring-scorecard');
    const head = table.tHead;
    let corner = null;
    for (const row of [...head.rows]) {
      for (const cell of [...row.cells]) {
        if (cell.dataset.column === 'kpi' && !corner) corner = cell;
        else if (['category', 'type', 'weight', 'maximum'].includes(cell.dataset.column)) cell.remove();
      }
    }
    if (corner) {
      corner.textContent = corner.textContent.trim() === 'CATEGORY' ? 'Category' : corner.textContent.trim();
      corner.classList.add('scoring-scorecard-corner');
    }
    // A lone Score group says nothing the operators below it do not: the header starts with the operators.
    const first = head.rows[0];
    const groups = first ? [...first.cells].filter(cell => cell.classList.contains('scoring-column-group')) : [];
    if (corner && head.rows.length > 1 && groups.length === 1 && groups[0].classList.contains('scoring-score-group')) {
      groups[0].remove();
      corner.rowSpan = Math.max(1, corner.rowSpan - 1);
      head.rows[1].prepend(corner);
      if (!first.cells.length) first.remove();
    }
    for (const row of head.rows) {
      for (const cell of row.cells) {
        if (!cell.classList.contains('scoring-operator-header') && !cell.classList.contains('scoring-gap-operator-header')) continue;
        cell.style.removeProperty('background-color');
        cell.style.removeProperty('color');
        const chip = document.createElement('span');
        chip.className = 'scoring-operator-chip';
        chip.append(...cell.childNodes);
        cell.append(chip);
      }
    }

    const body = table.tBodies[0];
    const runs = [];
    for (const row of body ? [...body.rows] : []) {
      const categoryCell = [...row.cells].find(cell => cell.dataset.column === 'category');
      if (categoryCell) {
        runs.push({category: categoryCell.textContent.trim(), rows: []});
        categoryCell.remove();
      }
      runs.at(-1)?.rows.push(row);
      decorateScorecardRow(row);
    }
    for (const row of table.tFoot ? [...table.tFoot.rows] : []) decorateScorecardRow(row);
    const width = Math.max(1, ...[...(body?.rows || [])].map(row => [...row.cells].reduce((sum, cell) => sum + (cell.colSpan || 1), 0)));
    const grouped = new Set(runs.map(run => run.category)).size === runs.length;
    for (const run of runs) {
      if (!grouped) {
        for (const row of run.rows) {
          const label = [...row.cells].find(cell => cell.dataset.column === 'kpi');
          if (!label) continue;
          const tag = document.createElement('span');
          tag.className = 'scoring-kpi-category';
          tag.textContent = run.category;
          label.prepend(tag);
        }
        continue;
      }
      let section = run.rows.find(row => row.classList.contains('scoring-category-subtotal'));
      if (section) {
        const name = [...section.cells].find(cell => cell.dataset.column === 'kpi')?.querySelector('.scoring-kpi-name');
        if (name) name.textContent = run.category;
      } else {
        section = document.createElement('tr');
        const cell = document.createElement('th');
        cell.scope = 'rowgroup';
        cell.colSpan = width;
        cell.dataset.column = 'kpi';
        cell.className = 'scoring-kpi-label';
        const name = document.createElement('span');
        name.className = 'scoring-kpi-name';
        name.textContent = run.category;
        const count = document.createElement('span');
        count.className = 'scoring-kpi-meta';
        const kpis = run.rows.length;
        count.textContent = `${kpis} KPI${kpis === 1 ? '' : 's'}`;
        cell.append(name, count);
        section.append(cell);
      }
      body.insertBefore(section, run.rows[0]);
      section.classList.add('scoring-section-row');
      section.dataset.category = run.category;
    }
    markScorecardGroupEdges(table);
  }

  // The first column of each operator (major) and of each group below it, such as a route, city or campaign (minor), in
  // the header and the body, so the themes can set the groups apart; the labels of the groups below the operators
  // (data-group-header) are ruled across their columns, so each one shows where it ends.
  function markScorecardGroupEdges(table) {
    const occupied = [];
    const edges = new Map();
    [...table.tHead.rows].forEach((row, rowIndex) => {
      occupied[rowIndex] ||= [];
      let column = 0;
      for (const cell of row.cells) {
        while (occupied[rowIndex][column]) column += 1;
        const span = cell.colSpan || 1;
        const major = cell.classList.contains('scoring-operator-header') || cell.classList.contains('scoring-gap-operator-header')
          || cell.classList.contains('scoring-column-group');
        if (major || span > 1) {
          if (column > 0) edges.set(column, major || edges.get(column) === 'major' ? 'major' : 'minor');
          cell.dataset.groupEdge = column > 0 ? edges.get(column) : major ? 'major' : 'minor';
          if (!major) cell.dataset.groupHeader = '';
        } else if (column > 0 && edges.has(column)) {
          cell.dataset.groupEdge = edges.get(column);
        }
        for (let rowOffset = 0; rowOffset < (cell.rowSpan || 1); rowOffset += 1) {
          occupied[rowIndex + rowOffset] ||= [];
          for (let columnOffset = 0; columnOffset < span; columnOffset += 1) occupied[rowIndex + rowOffset][column + columnOffset] = true;
        }
        column += span;
      }
    });
    for (const row of [...table.tBodies[0]?.rows || [], ...table.tFoot?.rows || []]) {
      let column = 0;
      for (const cell of row.cells) {
        const edge = edges.get(column);
        if (edge && cell.colSpan === 1) cell.dataset.groupEdge = edge;
        column += cell.colSpan || 1;
      }
    }
  }

  function appendMatrixTable(pane, tableData) {
    const isSummary = tableData?._display_mode === 'summary';
    const rows = Array.isArray(tableData?.rows) ? tableData.rows : [];
    const operators = Array.isArray(tableData?.operators) ? tableData.operators.map(String) : [];
    const baseline = String(tableData?.baseline_operator || '');
    const baselineLabel = operatorPresentation(tableData, baseline).label;
    const nonBaseline = operators.filter(operator => !isReferenceOperator(tableData, operator));
    const showGaps = showGapValues();
    const gapLayout = showGaps ? selectedGapLayout() : 'end';
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-matrix-wrap';
    const table = document.createElement('table');
    table.className = 'scoring-comparison-table';
    const thead = document.createElement('thead');
    const header = document.createElement('tr');
    for (const [columnIndex, title] of [...(!isSummary ? ['CATEGORY'] : []), isSummary ? 'CATEGORY' : 'KPI', ...(!isSummary ? ['Type of KPI'] : []), 'Score weight (%)', 'Max score'].entries()) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.rowSpan = 2;
      th.dataset.column = columnIndex === 0 && !isSummary ? 'category'
        : ({CATEGORY: 'kpi', KPI: 'kpi', 'Type of KPI': 'type', 'Score weight (%)': 'weight', 'Max score': 'maximum'})[title];
      th.textContent = title;
      if (title === 'Score weight (%)') th.className = 'scoring-weight-header';
      if (title === 'Max score') th.className = 'scoring-maximum-header';
      header.append(th);
    }
    const showKpiValues = tableData?._display_mode !== 'summary' && Boolean(showKpiValuesToggle?.checked);
    if (showKpiValues && operators.length) {
      const group = document.createElement('th');
      group.scope = 'colgroup';
      group.colSpan = operators.length;
      group.className = 'scoring-column-group scoring-kpi-value-group';
      group.textContent = 'KPI Value';
      header.append(group);
    }
    if (operators.length && gapLayout === 'end') {
      const group = document.createElement('th');
      group.scope = 'colgroup';
      group.colSpan = operators.length;
      group.className = 'scoring-column-group scoring-score-group';
      group.textContent = 'Score';
      header.append(group);
    }
    if (gapLayout === 'adjacent') {
      for (const operator of operators) {
        const presentation = operatorPresentation(tableData, operator);
        const isCompared = nonBaseline.includes(operator);
        const group = document.createElement('th');
        group.scope = 'colgroup';
        group.colSpan = isCompared ? 2 : 1;
        group.className = `scoring-column-group ${isCompared ? 'scoring-adjacent-group' : 'scoring-score-group'}`;
        group.textContent = `${presentation.label} · ${isCompared ? 'Score / GAP' : 'Score'}`;
        header.append(group);
      }
    } else if (showGaps && nonBaseline.length) {
      const group = document.createElement('th');
      group.scope = 'colgroup';
      group.colSpan = nonBaseline.length;
      group.className = 'scoring-column-group scoring-gap-group';
      group.textContent = 'GAP';
      header.append(group);
    }
    const operatorHeader = document.createElement('tr');
    if (showKpiValues) {
      for (const operator of operators) {
        const presentation = operatorPresentation(tableData, operator);
        const th = document.createElement('th');
        th.scope = 'col';
        th.className = 'scoring-kpi-value-header';
        th.dataset.column = 'kpi-value';
        th.textContent = presentation.label;
        th.title = `Raw KPI measurement for ${presentation.label} (${operator}); units are shown when provided by the KPI definition.`;
        if (presentation.color) {
          th.style.backgroundColor = presentation.color;
          th.style.color = readableTextColor(presentation.color);
        }
        if (isReferenceOperator(tableData, operator)) markReferenceHeader(th);
        operatorHeader.append(th);
      }
    }
    const appendScoreHeader = (operator, index) => {
      const th = document.createElement('th');
      th.scope = 'col';
      th.dataset.column = 'score';
      const presentation = operatorPresentation(tableData, operator);
      th.textContent = gapLayout === 'adjacent' ? 'Score' : presentation.label;
      const operatorTone = operator.toLowerCase().replace(/[^a-z0-9]+/g, '-');
      th.className = `scoring-operator-header scoring-tone-${index % 5} scoring-operator-${operatorTone}`;
      th.title = `${presentation.label} (${operator}) weighted KPI points`;
      if (presentation.color) {
        th.style.backgroundColor = presentation.color;
        th.style.color = readableTextColor(presentation.color);
        th.style.setProperty('--operator-accent', presentation.color);
        th.style.setProperty('--operator-text', readableTextColor(presentation.color));
      }
      if (isReferenceOperator(tableData, operator)) markReferenceHeader(th);
      operatorHeader.append(th);
    };
    const appendGapHeader = operator => {
      const th = document.createElement('th');
      th.scope = 'col';
      th.className = 'scoring-gap-header';
      th.dataset.column = 'gap';
      const operatorLabel = operatorPresentation(tableData, operator).label;
      th.textContent = gapLayout === 'adjacent' ? 'GAP' : `${operatorLabel} − ${baselineLabel}`;
      th.title = `${operator} weighted points minus baseline ${baseline} weighted points`;
      operatorHeader.append(th);
    };
    if (gapLayout === 'adjacent') {
      operators.forEach((operator, index) => {
        appendScoreHeader(operator, index);
        if (showGaps && nonBaseline.includes(operator)) appendGapHeader(operator);
      });
    } else {
      operators.forEach(appendScoreHeader);
      if (showGaps) nonBaseline.forEach(appendGapHeader);
    }
    thead.append(header, operatorHeader);

    const tbody = document.createElement('tbody');
    const categoryRuns = new Map();
    for (let index = 0; index < rows.length; index += 1) {
      const category = String(rows[index]?.category || 'Other');
      if (index > 0 && String(rows[index - 1]?.category || 'Other') === category) continue;
      let span = 1;
      while (index + span < rows.length && String(rows[index + span]?.category || 'Other') === category) span += 1;
      categoryRuns.set(index, {category, span});
    }
    rows.forEach((item, index) => {
      const tr = document.createElement('tr');
      if (item?.row_type === 'category') {
        tr.classList.add('scoring-category-subtotal');
        tr.style.fontWeight = '700';
      }
      const run = categoryRuns.get(index);
      if (run && !isSummary) {
        const category = document.createElement('td');
        category.className = 'scoring-category-cell';
        category.rowSpan = run.span;
        category.textContent = run.category;
        category.dataset.column = 'category';
        tr.append(category);
      }
      const kpi = document.createElement('td');
      kpi.dataset.column = 'kpi';
      kpi.textContent = String(item?.kpi || item?.kpi_code || 'N/A');
      kpi.title = String(item?.kpi_code || item?.kpi || '');
      tr.append(kpi);
      if (!isSummary) tr.append(createKpiTypeCell(item?.kpi_type, item?.row_type === 'category'));

      const weight = document.createElement('td');
      weight.dataset.numeric = 'true';
      weight.dataset.column = 'weight';
      weight.textContent = formatMatrixNumber(item?.weight_percent);
      styleIncompleteValue(weight);
      tr.append(weight);
      const maximum = document.createElement('td');
      maximum.dataset.numeric = 'true';
      maximum.dataset.column = 'maximum';
      maximum.textContent = formatMatrixNumber(item?.max_points);
      styleIncompleteValue(maximum);
      tr.append(maximum);

      const values = item?.values && typeof item.values === 'object' ? item.values : {};
      const summaryColors = isSummary ? summaryOperatorColors(values, operators.map(id => ({id}))) : new Map();
      if (showKpiValues) {
        for (const operator of operators) {
          const cell = document.createElement('td');
          cell.dataset.column = 'kpi-value';
          const operatorCell = operatorValue(values, operator);
          const isCategoryRow = item?.row_type === 'category';
          const rawValue = !isCategoryRow && operatorCell && typeof operatorCell === 'object'
            ? firstValue(operatorCell, ['value', 'raw_value', 'kpi_value'], null) : null;
          const presentation = operatorPresentation(tableData, operator);
          const unit = firstValue(item, ['unit', 'units', 'measurement_unit'], '');
          cell.className = 'scoring-kpi-value-cell';
          cell.textContent = isCategoryRow ? '' : formatRawKpiValue(rawValue);
          styleIncompleteValue(cell);
          cell.dataset.numeric = 'true';
          cell.title = isCategoryRow ? ''
            : `Raw ${item?.kpi || item?.kpi_code || 'KPI'} measurement for ${presentation.label}${unit ? ` (${unit})` : ''}: ${formatRawKpiValue(rawValue)}`;
          tr.append(cell);
        }
      }
      const gaps = item?.gaps && typeof item.gaps === 'object' ? item.gaps : {};
      const gapColors = item?.gap_colors && typeof item.gap_colors === 'object' ? item.gap_colors : {};
      const gapPartial = item?.gap_partial && typeof item.gap_partial === 'object' ? item.gap_partial : {};
      const gapEnvironments = item?.gap_environments && typeof item.gap_environments === 'object' ? item.gap_environments : {};
      appendScoreGapCells(operators, nonBaseline, gapLayout,
        (operator, operatorIndex) => addMatrixScoreCell(
          tr, operatorValue(values, operator), `scoring-tone-${operatorIndex % 5}`, item?.row_type === 'category',
          isSummary ? (summaryColors.get(operator) || '') : null,
        ),
        operator => addMatrixGapCell(tr, firstValue(gaps, [operator], null), firstValue(gapColors, [operator], ''),
          firstValue(gapPartial, [operator], false), firstValue(gapEnvironments, [operator], [])),
      );
      tbody.append(tr);
    });

    if (!isSummary) applyGapCategoryRunColors(tbody);
    table.append(thead, tbody);
    const total = tableData?.total;
    if (total && typeof total === 'object') {
      const tfoot = document.createElement('tfoot');
      const row = document.createElement('tr');
      const category = document.createElement('th');
      category.scope = 'row';
      category.dataset.column = 'category';
      category.textContent = 'Total';
      if (!isSummary) row.append(category);
      const label = document.createElement('td');
      label.dataset.column = 'kpi';
      label.textContent = showGapValues() && total.gap_label ? `Weighted score · ${total.gap_label}` : 'Weighted score';
      row.append(label);
      if (!isSummary) row.append(createKpiTypeCell('', true));
      const weight = document.createElement('td');
      weight.dataset.numeric = 'true';
      weight.dataset.column = 'weight';
      weight.textContent = formatMatrixNumber(firstValue(total, ['weight_percent'], 100));
      styleIncompleteValue(weight);
      row.append(weight);
      const maximum = document.createElement('td');
      maximum.dataset.numeric = 'true';
      maximum.dataset.column = 'maximum';
      maximum.textContent = formatMatrixNumber(firstValue(total, ['max_points'], null));
      styleIncompleteValue(maximum);
      row.append(maximum);
      const values = total.values && typeof total.values === 'object' ? total.values : {};
      const summaryColors = isSummary ? summaryOperatorColors(values, operators.map(id => ({id}))) : new Map();
      if (showKpiValues) {
        operators.forEach(() => {
          const cell = document.createElement('td');
          cell.className = 'scoring-kpi-value-cell';
          cell.dataset.column = 'kpi-value';
          cell.dataset.numeric = 'true';
          cell.textContent = 'N/A';
          cell.title = 'A single raw KPI measurement does not apply to the weighted total.';
          row.append(cell);
        });
      }
      const gaps = total.gaps && typeof total.gaps === 'object' ? total.gaps : {};
      const gapColors = total.gap_colors && typeof total.gap_colors === 'object' ? total.gap_colors : {};
      const gapPartial = total.gap_partial && typeof total.gap_partial === 'object' ? total.gap_partial : {};
      const gapEnvironments = total.gap_environments && typeof total.gap_environments === 'object' ? total.gap_environments : {};
      appendScoreGapCells(operators, nonBaseline, gapLayout,
        operator => addMatrixScoreCell(row, operatorValue(values, operator), '', true, isSummary ? (summaryColors.get(operator) || '') : null),
        operator => addMatrixGapCell(row, firstValue(gaps, [operator], null), firstValue(gapColors, [operator], ''),
          firstValue(gapPartial, [operator], false), firstValue(gapEnvironments, [operator], [])),
      );
      tfoot.append(row);
      table.append(tfoot);
    }
    applyScorecardLayout(table);
    wrapper.append(table);
    pane.append(wrapper);
    observeScoringValueCells(table, wrapper);
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No KPI rows are available for this comparison context.';
      pane.append(empty);
    }
  }

  function hierarchyColumnEntries(tableData, styleSource = tableData, includeReference = true) {
    const sourceColumns = Array.isArray(tableData?.hierarchy_columns) && tableData.hierarchy_columns.length
      ? tableData.hierarchy_columns
      : (Array.isArray(styleSource?.hierarchy_columns) ? styleSource.hierarchy_columns : []);
    const byId = new Map(sourceColumns.map(column => [String(column?.id ?? ''), column]));
    const ids = Array.isArray(tableData?.operators) ? tableData.operators.map(String) : sourceColumns.map(column => String(column?.id ?? ''));
    const columns = ids.map((id, index) => ({...(byId.get(id) || {}), id, styleSource, sourceIndex: index}));
    columns.sort((left, right) => {
      const leftStyle = firstValue(styleSource?.operator_styles || {}, [left.id], {});
      const rightStyle = firstValue(styleSource?.operator_styles || {}, [right.id], {});
      const leftPosition = Number(firstValue(leftStyle, ['position'], left.sourceIndex));
      const rightPosition = Number(firstValue(rightStyle, ['position'], right.sourceIndex));
      return leftPosition - rightPosition || left.sourceIndex - right.sourceIndex;
    });
    return columns.filter(column => includeReference || !hierarchyColumnIsReference(column));
  }

  function hierarchyColumnIsReference(column) {
    const style = firstValue(column?.styleSource?.operator_styles || {}, [column?.id], {});
    return column?.is_reference === true || style?.is_reference === true
      || (column?.operator && isReferenceOperator(column.styleSource, column.operator));
  }

  function hierarchyColumnOperator(column) {
    const style = firstValue(column?.styleSource?.operator_styles || {}, [column?.id], {});
    return String(column?.operator || style?.operator || column?.id || '');
  }

  function hierarchyLevelNames(tableData, columns) {
    const configured = Array.isArray(tableData?.hierarchy_levels) ? tableData.hierarchy_levels.map(String) : [];
    if (configured.length) return configured;
    for (const column of columns) {
      if (Array.isArray(column?.path) && column.path.length) return column.path.map(item => String(item?.level || 'Level'));
    }
    return [];
  }

  // Campaigns as the workspace Campaign Maps show them (campaign_labels.js); without it,
  // the default map: 2026-Q2, 2026-Q2-NSA or 2026-Q2-SA.
  function hierarchyDisplayValue(entry) {
    const text = String(entry?.value ?? 'Not specified');
    if (entry?.level !== 'Campaign') return text;
    if (typeof globalThis.campaignLabel === 'function') return globalThis.campaignLabel(text) || text;
    const year = text.match(/(?<!\d)((?:19|20)\d{2})(?!\d)/)?.[1];
    const quarter = text.match(/(?:^|[^A-Z0-9])Q\s*[_\- ]?([1-4])(?=$|[^0-9])/i)?.[1];
    const mode = (text.match(/(?:^|[_\- ])(NSA|SA)(?=$|[_\- ])/i)?.[1] || '').toUpperCase();
    return year && quarter ? `${year}-Q${quarter}${mode ? `-${mode}` : ''}` : text;
  }

  function hierarchyPathEntry(column, depth, levels) {
    const path = Array.isArray(column?.path) ? column.path : [];
    const expectedLevel = levels[depth] || '';
    const entry = path.find(item => String(item?.level || '') === expectedLevel) || path[depth] || {};
    return {
      level: String(entry?.level || expectedLevel || `Level ${depth + 1}`),
      value: hierarchyDisplayValue(entry),
      rawValue: String(entry?.value ?? ''),
    };
  }

  function hierarchyPathValueLabel(column) {
    const path = Array.isArray(column?.path) ? column.path : [];
    return path.map(entry => {
      const value = hierarchyDisplayValue(entry).trim();
      return value || 'Not specified';
    }).join(' · ');
  }

  function hierarchyPathFullLabel(column) {
    const path = Array.isArray(column?.path) ? column.path : [];
    return String(path.length ? path.map(entry => {
      const level = String(entry?.level || 'Level');
      const value = hierarchyDisplayValue(entry).trim() || 'Not specified';
      return `${level}: ${value}`;
    }).join(' · ') : column?.label || '');
  }

  // The label of a band of the hierarchy axis across ``width`` at ``size``: up to two lines, shortened when they do not
  // fit (``whole`` false).
  function hierarchyBandLabelLayout(value, width, size = 14) {
    const lines = fittedSvgLabelLines(String(value), Math.max(1, Math.min(34, Math.floor((width - 6) / (size * .6)))), 2);
    return {size, lines, whole: !lines.some(line => line.endsWith('…'))};
  }

  // The rows of the hierarchy axis under the bars, the deepest level first: the bands of the bars with the same values
  // down to that level, with their labels, all of a row at one size. A row shows them across at the largest size, from
  // 14px down to 9px, at which every one fits whole, unless turned 90° (as wide as its narrowest band, 6px to 13px)
  // they are larger or that size does not exist: the row then turns all of them and is as tall as its longest label
  // (32px to 96px).
  function hierarchyAxisRows(categories, levels, columnsById, categoryStarts, step, left) {
    const rows = [];
    for (let rowIndex = 0; rowIndex < levels.length; rowIndex += 1) {
      const depth = levels.length - rowIndex - 1;
      const groups = [];
      let start = 0;
      while (start < categories.length) {
        const firstColumn = columnsById.get(String(categories[start]));
        const prefix = firstColumn ? hierarchyPrefixKey(firstColumn, depth, levels) : JSON.stringify(['missing', categories[start]]);
        let end = start + 1;
        while (end < categories.length) {
          const column = columnsById.get(String(categories[end]));
          const key = column ? hierarchyPrefixKey(column, depth, levels) : JSON.stringify(['missing', categories[end]]);
          if (key !== prefix) break;
          end += 1;
        }
        const firstStart = categoryStarts.get(String(categories[start]));
        const lastStart = categoryStarts.get(String(categories[end - 1]));
        const x1 = firstStart ?? left + start * step;
        const x2 = (lastStart ?? left + (end - 1) * step) + step;
        const entry = firstColumn ? hierarchyPathEntry(firstColumn, depth, levels) : {level: levels[depth], value: ''};
        const value = entry.value || 'Not specified';
        groups.push({x1, x2, entry, value, firstColumn});
        start = end;
      }
      const size = Math.max(6, Math.min(13, Math.floor(Math.min(...groups.map(group => group.x2 - group.x1)) * .8)));
      let acrossSize = 14;
      while (acrossSize >= 9 && !groups.every(group => hierarchyBandLabelLayout(group.value, group.x2 - group.x1, acrossSize).whole)) {
        acrossSize -= 1;
      }
      if (acrossSize >= 9 && acrossSize >= size) {
        for (const group of groups) group.layout = hierarchyBandLabelLayout(group.value, group.x2 - group.x1, acrossSize);
        rows.push({groups, height: 32, rotated: false});
        continue;
      }
      const longest = Math.max(...groups.map(group => String(group.value).length));
      const height = Math.max(32, Math.min(96, Math.ceil(longest * size * .6 + 12)));
      const characters = Math.max(1, Math.floor((height - 8) / (size * .6)));
      for (const group of groups) group.layout = {size, lines: fittedSvgLabelLines(group.value, characters, 1), whole: true};
      rows.push({groups, height, rotated: true});
    }
    return {rows, height: rows.reduce((sum, row) => sum + row.height, 0)};
  }

  function appendHierarchyAxisBands(svg, categories, levels, columnsById, categoryStarts, step, baselineY, left, right) {
    if (!levels.length || !categories.length) return;
    const {rows, height} = hierarchyAxisRows(categories, levels, columnsById, categoryStarts, step, left);
    const top = baselineY + 16;
    const width = Math.max(0, right - left);
    svg.append(svgElement(svg, 'rect', {x: left, y: top, width, height, fill: '#ffffff'}));
    const lastCategoryStart = categoryStarts.get(String(categories[categories.length - 1]));
    const lastX = (lastCategoryStart ?? left + (categories.length - 1) * step) + step;
    let y = top;
    rows.forEach((row, rowIndex) => {
      const rowHeight = row.height;
      if (rowIndex % 2) svg.append(svgElement(svg, 'rect', {x: left, y, width, height: rowHeight, fill: '#f6f8f8'}));
      svg.append(svgElement(svg, 'line', {x1: left, x2: right, y1: y + rowHeight, y2: y + rowHeight, stroke: '#cbd6d9', 'stroke-width': 1}));
      for (const {x1, x2, entry, value, firstColumn, layout} of row.groups) {
        const centerX = x1 + (x2 - x1) / 2;
        const centerY = y + rowHeight / 2;
        const label = svgElement(svg, 'text', {
          x: centerX,
          y: row.rotated ? centerY : centerY + (layout.lines.length > 1 ? -4 : 5) * layout.size / 14,
          'text-anchor': 'middle',
          class: 'scoring-chart-hierarchy-label',
          'aria-label': `${entry.level}: ${value}`,
        });
        if (layout.size !== 14) label.style.fontSize = `${layout.size}px`;
        if (row.rotated) {
          label.setAttribute('dominant-baseline', 'central');
          label.setAttribute('transform', `rotate(-90 ${centerX} ${centerY})`);
        }
        label.setAttribute('fill', '#334b58');
        label.setAttribute('pointer-events', 'auto');
        layout.lines.forEach((line, lineIndex) => {
          const span = svgElement(svg, 'tspan', {x: centerX, dy: lineIndex ? String(Math.round(layout.size * 15 / 14)) : '0'});
          span.textContent = line;
          label.append(span);
        });
        setChartTooltip(label, firstColumn ? hierarchyPathFullLabel(firstColumn) : `${entry.level}: ${value}`);
        svg.append(label);
        svg.append(svgElement(svg, 'line', {x1, x2: x1, y1: y, y2: y + rowHeight, stroke: '#cbd6d9', 'stroke-width': 1}));
      }
      svg.append(svgElement(svg, 'line', {x1: lastX, x2: lastX, y1: y, y2: y + rowHeight, stroke: '#cbd6d9', 'stroke-width': 1}));
      y += rowHeight;
    });
  }

  function hierarchyPrefixKey(column, depth, levels) {
    return JSON.stringify(Array.from({length: depth + 1}, (_, index) => {
      const entry = hierarchyPathEntry(column, index, levels);
      return [entry.level, entry.rawValue];
    }));
  }

  // The group of a chart bar, with a gap between groups: the first level before Operator in the hierarchy whose value
  // changes between the bars (each City when City comes before Operator), otherwise its operator.
  function hierarchyChartGroupKey(columns, levels) {
    const operatorDepth = levels.indexOf('Operator');
    const depth = levels.slice(0, Math.max(0, operatorDepth)).findIndex((_level, index) => new Set(
      columns.map(column => hierarchyPathEntry(column, index, levels).rawValue),
    ).size > 1);
    return column => (column && depth >= 0 ? hierarchyPrefixKey(column, depth, levels) : hierarchyColumnOperator(column));
  }

  function appendHierarchyHeaders(thead, tableData, columns, fixedHeadings, blocks, gapBaseline = null) {
    const levels = hierarchyLevelNames(tableData, columns);
    const depth = Math.max(levels.length, ...columns.map(column => Array.isArray(column.path) ? column.path.length : 0));
    const headerLevels = levels.length ? levels : Array.from({length: depth}, (_, index) => `Level ${index + 1}`);
    const firstRow = document.createElement('tr');
    for (const [title, key, className = ''] of fixedHeadings) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.rowSpan = depth + (gapBaseline ? 0 : 1);
      th.dataset.column = key;
      th.textContent = title;
      if (className) th.className = className;
      firstRow.append(th);
    }
    for (const block of gapBaseline ? [] : blocks) {
      if (!block.columns.length) continue;
      const th = document.createElement('th');
      th.scope = 'colgroup';
      th.colSpan = block.columns.length;
      th.className = `scoring-column-group ${block.className || ''}`.trim();
      th.textContent = block.label;
      firstRow.append(th);
    }
    if (!gapBaseline) thead.append(firstRow);

    for (let depthIndex = 0; depthIndex < depth; depthIndex += 1) {
      const row = gapBaseline && depthIndex === 0 ? firstRow : document.createElement('tr');
      for (const block of blocks) {
        if (!block.columns.length) continue;
        let start = 0;
        while (start < block.columns.length) {
          const key = hierarchyPrefixKey(block.columns[start], depthIndex, headerLevels);
          let end = start + 1;
          while (end < block.columns.length && hierarchyPrefixKey(block.columns[end], depthIndex, headerLevels) === key) end += 1;
          const groupedColumns = block.columns.slice(start, end);
          const entry = hierarchyPathEntry(groupedColumns[0], depthIndex, headerLevels);
          const th = document.createElement('th');
          th.scope = groupedColumns.length > 1 ? 'colgroup' : 'col';
          th.colSpan = groupedColumns.length;
          th.className = `scoring-hierarchy-header ${block.headerClass || ''}`.trim();
          th.dataset.column = block.column || 'hierarchy';
          th.dataset.hierarchyLevel = entry.level;
          th.dataset.hierarchyDepth = String(depthIndex);
          th.textContent = entry.value || 'Not specified';
          th.title = `${entry.level}: ${entry.value || 'Not specified'}`;
          th.setAttribute('aria-label', `${entry.level}: ${entry.value || 'Not specified'}`);
          if (String(entry.level).toLocaleLowerCase() === 'operator') {
            th.classList.add('scoring-operator-header');
            const column = groupedColumns[0];
            const presentation = operatorPresentation(column.styleSource, column.id);
            const fullLabel = hierarchyPathFullLabel(column) || presentation.label || th.textContent;
            th.title = fullLabel;
            th.setAttribute('aria-label', fullLabel);
            if (presentation.color) {
              th.style.setProperty('--operator-accent', presentation.color);
              th.style.setProperty('--operator-text', categoryLegendTextColor(presentation.color));
            }
            if (gapBaseline) {
              th.textContent = `${canonicalOperatorName(entry.value) || entry.value} − ${gapBaseline}`;
              th.classList.add('scoring-gap-operator-header');
              th.style.setProperty('--operator-text', categoryLegendTextColor(presentation.color));
            }
            if (hierarchyColumnIsReference(column)) {
              markReferenceHeader(th);
              th.title = `${fullLabel} is the reference operator`;
            }
          }
          row.append(th);
          start = end;
        }
      }
      thead.append(row);
    }
    return {levels: headerLevels, depth};
  }

  function appendHierarchyMatrixTable(pane, tableData) {
    const isSummary = tableData?._display_mode === 'summary';
    const rows = Array.isArray(tableData?.rows) ? tableData.rows : [];
    const allColumns = hierarchyColumnEntries(tableData);
    const nonBaseline = allColumns.filter(column => !hierarchyColumnIsReference(column));
    const showKpiValues = tableData?._display_mode !== 'summary' && Boolean(showKpiValuesToggle?.checked);
    const showGaps = showGapValues();
    const gapLayout = showGaps ? selectedGapLayout() : 'end';
    const blocks = [
      ...(showKpiValues ? [{label: 'KPI Value', className: 'scoring-kpi-value-group', headerClass: 'scoring-kpi-value-header', column: 'kpi-value', columns: allColumns}] : []),
      ...(gapLayout === 'adjacent'
        ? allColumns.flatMap(column => [
          {label: 'Score', className: 'scoring-score-group', headerClass: 'scoring-score-header', column: 'score', columns: [column]},
          ...(showGaps && !hierarchyColumnIsReference(column)
            ? [{label: 'GAP', className: 'scoring-gap-group', headerClass: 'scoring-gap-header', column: 'gap', columns: [column]}]
            : []),
        ])
        : [
          {label: 'Score', className: 'scoring-score-group', headerClass: 'scoring-score-header', column: 'score', columns: allColumns},
          ...(showGaps ? [{label: 'GAP', className: 'scoring-gap-group', headerClass: 'scoring-gap-header', column: 'gap', columns: nonBaseline}] : []),
        ]),
    ];
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-matrix-wrap';
    const table = document.createElement('table');
    table.className = 'scoring-comparison-table scoring-hierarchy-table';
    const thead = document.createElement('thead');
    appendHierarchyHeaders(thead, tableData, allColumns, [
      ...(!isSummary ? [['CATEGORY', 'category']] : []), [isSummary ? 'CATEGORY' : 'KPI', 'kpi'],
      ...(!isSummary ? [['Type of KPI', 'type']] : []),
      ['Score weight (%)', 'weight', 'scoring-weight-header'], ['Max score', 'maximum', 'scoring-maximum-header'],
    ], blocks);
    const tbody = document.createElement('tbody');
    for (let index = 0; index < rows.length; index += 1) {
      const item = rows[index];
      const row = document.createElement('tr');
      if (item?.row_type === 'category') {
        row.classList.add('scoring-category-subtotal');
        row.style.fontWeight = '700';
      }
      const category = String(item?.category || 'Other');
      if (!isSummary && (index === 0 || String(rows[index - 1]?.category || 'Other') !== category)) {
        let span = 1;
        while (index + span < rows.length && String(rows[index + span]?.category || 'Other') === category) span += 1;
        const categoryCell = document.createElement('td');
        categoryCell.className = 'scoring-category-cell';
        categoryCell.rowSpan = span;
        categoryCell.textContent = category;
        categoryCell.dataset.column = 'category';
        row.append(categoryCell);
      }
      const kpi = document.createElement('td');
      kpi.dataset.column = 'kpi';
      kpi.textContent = String(item?.kpi || item?.kpi_code || 'N/A');
      kpi.title = String(item?.kpi_code || item?.kpi || '');
      row.append(kpi);
      if (!isSummary) row.append(createKpiTypeCell(item?.kpi_type, item?.row_type === 'category'));
      const weight = document.createElement('td');
      weight.dataset.numeric = 'true';
      weight.dataset.column = 'weight';
      weight.textContent = formatMatrixNumber(item?.weight_percent);
      styleIncompleteValue(weight);
      row.append(weight);
      const maximum = document.createElement('td');
      maximum.dataset.numeric = 'true';
      maximum.dataset.column = 'maximum';
      maximum.textContent = formatMatrixNumber(item?.max_points);
      styleIncompleteValue(maximum);
      row.append(maximum);
      const values = item?.values && typeof item.values === 'object' ? item.values : {};
      const summaryColors = isSummary ? summaryOperatorColors(values, allColumns) : new Map();
      if (showKpiValues) {
        for (const column of allColumns) {
          const cell = document.createElement('td');
          const operatorCell = operatorValue(values, column.id);
          const isCategoryRow = item?.row_type === 'category';
          const rawValue = !isCategoryRow && operatorCell && typeof operatorCell === 'object'
            ? firstValue(operatorCell, ['value', 'raw_value', 'kpi_value'], null) : null;
          const presentation = operatorPresentation(column.styleSource, column.id);
          const unit = firstValue(item, ['unit', 'units', 'measurement_unit'], '');
          cell.className = 'scoring-kpi-value-cell';
          cell.dataset.column = 'kpi-value';
          cell.textContent = isCategoryRow ? '' : formatRawKpiValue(rawValue);
          styleIncompleteValue(cell);
          cell.dataset.numeric = 'true';
          cell.title = isCategoryRow ? ''
            : `Raw ${item?.kpi || item?.kpi_code || 'KPI'} measurement for ${presentation.label}${unit ? ` (${unit})` : ''}: ${formatRawKpiValue(rawValue)}`;
          row.append(cell);
        }
      }
      const gaps = item?.gaps && typeof item.gaps === 'object' ? item.gaps : {};
      const gapColors = item?.gap_colors && typeof item.gap_colors === 'object' ? item.gap_colors : {};
      const gapPartial = item?.gap_partial && typeof item.gap_partial === 'object' ? item.gap_partial : {};
      const gapEnvironments = item?.gap_environments && typeof item.gap_environments === 'object' ? item.gap_environments : {};
      appendScoreGapCells(allColumns, nonBaseline, gapLayout,
        (column, columnIndex) => addMatrixScoreCell(
          row, operatorValue(values, column.id), `scoring-tone-${columnIndex % 5}`, item?.row_type === 'category',
          isSummary ? (summaryColors.get(column.id) || '') : null,
        ),
        column => addMatrixGapCell(row, firstValue(gaps, [column.id], null), firstValue(gapColors, [column.id], ''),
          firstValue(gapPartial, [column.id], false), firstValue(gapEnvironments, [column.id], [])),
      );
      tbody.append(row);
    }
    if (!isSummary) applyGapCategoryRunColors(tbody);
    table.append(thead, tbody);
    const total = tableData?.total;
    if (total && typeof total === 'object') {
      const tfoot = document.createElement('tfoot');
      const row = document.createElement('tr');
      const category = document.createElement('th');
      category.scope = 'row';
      category.dataset.column = 'category';
      category.textContent = 'Total';
      if (!isSummary) row.append(category);
      const label = document.createElement('td');
      label.dataset.column = 'kpi';
      label.textContent = showGapValues() && total.gap_label ? `Weighted score · ${total.gap_label}` : 'Weighted score';
      row.append(label);
      if (!isSummary) row.append(createKpiTypeCell('', true));
      const weight = document.createElement('td');
      weight.dataset.numeric = 'true';
      weight.dataset.column = 'weight';
      weight.textContent = formatMatrixNumber(firstValue(total, ['weight_percent'], 100));
      styleIncompleteValue(weight);
      row.append(weight);
      const maximum = document.createElement('td');
      maximum.dataset.numeric = 'true';
      maximum.dataset.column = 'maximum';
      maximum.textContent = formatMatrixNumber(firstValue(total, ['max_points'], null));
      styleIncompleteValue(maximum);
      row.append(maximum);
      const values = total.values && typeof total.values === 'object' ? total.values : {};
      const summaryColors = isSummary ? summaryOperatorColors(values, allColumns) : new Map();
      if (showKpiValues) {
        allColumns.forEach(() => {
          const cell = document.createElement('td');
          cell.className = 'scoring-kpi-value-cell';
          cell.dataset.column = 'kpi-value';
          cell.dataset.numeric = 'true';
          cell.textContent = 'N/A';
          cell.title = 'A single raw KPI measurement does not apply to the weighted total.';
          row.append(cell);
        });
      }
      const gaps = total.gaps && typeof total.gaps === 'object' ? total.gaps : {};
      const gapColors = total.gap_colors && typeof total.gap_colors === 'object' ? total.gap_colors : {};
      const gapPartial = total.gap_partial && typeof total.gap_partial === 'object' ? total.gap_partial : {};
      const gapEnvironments = total.gap_environments && typeof total.gap_environments === 'object' ? total.gap_environments : {};
      appendScoreGapCells(allColumns, nonBaseline, gapLayout,
        column => addMatrixScoreCell(row, operatorValue(values, column.id), '', true, isSummary ? (summaryColors.get(column.id) || '') : null),
        column => addMatrixGapCell(row, firstValue(gaps, [column.id], null), firstValue(gapColors, [column.id], ''),
          firstValue(gapPartial, [column.id], false), firstValue(gapEnvironments, [column.id], [])),
      );
      tfoot.append(row);
      table.append(tfoot);
    }
    applyScorecardLayout(table);
    wrapper.append(table);
    pane.append(wrapper);
    observeScoringValueCells(table, wrapper);
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No KPI rows are available for this hierarchy.';
      pane.append(empty);
    }
  }

  function renderHierarchyScoringViews(pane, tableData, thresholdLegend = []) {
    disconnectScoringValueObservers(pane);
    pane.replaceChildren();
    if (!tableData) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No hierarchical scoring table is available for this environment.';
      pane.append(empty);
      return;
    }
    appendContextHeader(pane, tableData, 'score', 'Scoring Tables');
    appendScoringGapScale(pane, tableData);
    const summarySection = document.createElement('section');
    summarySection.className = 'scoring-table-mode-section';
    const summaryHeading = document.createElement('h4');
    summaryHeading.className = 'scoring-table-section-title';
    summaryHeading.textContent = 'Scoring Tables — Summary';
    appendResultScope(summaryHeading, tableData.context);
    summarySection.append(summaryHeading);
    appendOperatorRankingLegend(summarySection);
    appendHierarchyMatrixTable(summarySection, tableForMode(tableData, 'summary'));
    pane.append(summarySection);
    const expandedSection = document.createElement('section');
    expandedSection.className = 'scoring-table-mode-section';
    const expandedHeading = document.createElement('h4');
    expandedHeading.className = 'scoring-table-section-title';
    expandedHeading.textContent = 'Scoring Tables — Breakdown';
    appendResultScope(expandedHeading, tableData.context);
    expandedSection.append(expandedHeading);
    appendThresholdLegend(expandedSection, thresholdLegend.length ? thresholdLegend : tableData?.threshold_legend);
    appendHierarchyMatrixTable(expandedSection, tableForMode(tableData, 'expanded'));
    pane.append(expandedSection);
  }

  function renderHierarchyGapViews(pane, tableData, scoreTable) {
    disconnectScoringValueObservers(pane);
    pane.replaceChildren();
    if (!tableData) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No hierarchical GAP table is available for this environment.';
      pane.append(empty);
      return;
    }
    const styleSource = scoreTable || tableData;
    const baselineRaw = String(tableData.baseline_operator || 'the reference operator');
    const baseline = canonicalOperatorName(baselineRaw) || baselineRaw;
    const allColumns = hierarchyColumnEntries(tableData, styleSource, false)
      .filter(column => !hierarchyColumnIsReference(column)
        && hierarchyColumnOperator(column).toLocaleLowerCase() !== baseline.toLocaleLowerCase());
    const operators = [...new Set(allColumns.map(hierarchyColumnOperator).filter(Boolean))];
    const comparisonStateKey = gapComparisonIdentity(tableData, 'hierarchy-gap');
    let comparison = gapComparisonSelections.get(comparisonStateKey) || 'all';
    const selectedOperator = comparison.startsWith('operator:') ? comparison.slice('operator:'.length) : null;
    if (selectedOperator && !operators.includes(selectedOperator)) comparison = 'all';
    gapComparisonSelections.set(comparisonStateKey, comparison);
    const columns = comparison === 'all'
      ? allColumns
      : allColumns.filter(column => hierarchyColumnOperator(column) === selectedOperator);
    const sortByGap = comparison !== 'all';
    // One operator: its KPIs ordered by their GAP in the latest campaign.
    const latestColumns = latestCampaignColumns(columns);
    const rows = orderGapRows(Array.isArray(tableData.rows) ? tableData.rows : [],
      item => columns.map(column => firstValue(item?.gaps || {}, [column.id], null)), sortByGap,
      item => latestColumns.map(column => firstValue(item?.gaps || {}, [column.id], null)));
    const comparisonLabel = comparison === 'all' ? `All vs ${baseline}` : `${selectedOperator} vs ${baseline}`;
    const scaleRows = rows.flatMap(item => columns.map(column => ({gap_points: firstValue(item?.gaps || {}, [column.id], null)})))
      .filter(item => item.gap_points !== null && item.gap_points !== undefined && Number.isFinite(Number(item.gap_points)));
    appendContextHeader(pane, tableData, 'gap', 'GAP Analysis');
    if (operators.length) {
      const controls = document.createElement('div');
      controls.className = 'scoring-comparison-controls scoring-gap-comparison-controls';
      const label = document.createElement('label');
      label.textContent = 'GAP comparison';
      const select = document.createElement('select');
      select.dataset.hierarchyGapOperator = '';
      select.dataset.hierarchyGapStateKey = comparisonStateKey;
      select.setAttribute('aria-label', 'Choose all operators or one operator to compare with the reference');
      const allOption = document.createElement('option');
      allOption.value = 'all';
      allOption.textContent = `All vs ${baseline}`;
      allOption.selected = comparison === 'all';
      select.append(allOption);
      appendFocusOptions(select, operators.map(operator => [`operator:${operator}`, `${operator} vs ${baseline}`, operator, operator]));
      select.value = comparison;
      label.append(select);
      controls.append(label);
      pane.append(controls);
    }
    const note = document.createElement('p');
    note.className = 'scoring-context-note';
    note.textContent = `KPI GAP compares ${comparison === 'all' ? 'each hierarchy leaf' : selectedOperator} with ${baseline} at the same context.`;
    const gapInfo = document.createElement('div');
    gapInfo.className = 'scoring-gap-info';
    gapInfo.append(note);
    pane.append(gapInfo);
    if (!columns.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No operators can be compared with the selected reference operator.';
      pane.append(empty);
      return;
    }
    appendGapScaleAside(gapInfo, tableData, scaleRows, sortByGap && (latestColumns.length < columns.length ? 'latest' : true));

    const blocks = [{label: comparisonLabel, className: 'scoring-gap-group', headerClass: 'scoring-gap-header', column: 'gap', columns}];
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-matrix-wrap';
    const table = document.createElement('table');
    table.className = 'scoring-comparison-table scoring-priority-table scoring-gap-summary-table scoring-hierarchy-table';
    const thead = document.createElement('thead');
    appendHierarchyHeaders(thead, styleSource, columns, [
      ['Category', 'category'], ['KPI', 'kpi'], ['Type of KPI', 'type'],
    ], blocks, baseline);
    const tbody = document.createElement('tbody');
    for (let index = 0; index < rows.length; index += 1) {
      const item = rows[index];
      const row = document.createElement('tr');
      if (item?.row_type === 'category') {
        row.classList.add('scoring-category-subtotal');
        row.style.fontWeight = '700';
      }
      const category = String(item?.category ?? '');
      const previous = rows[index - 1];
      const startsCategoryRun = index === 0
        || String(previous?.category ?? '') !== category;
      if (startsCategoryRun) {
        let span = 1;
        while (index + span < rows.length
          && String(rows[index + span]?.category ?? '') === category) span += 1;
        const categoryCell = document.createElement('td');
        categoryCell.className = 'scoring-category-cell';
        categoryCell.dataset.column = 'category';
        categoryCell.rowSpan = span;
        categoryCell.textContent = category || 'Unclassified';
        row.append(categoryCell);
      }
      const kpiCell = document.createElement('td');
      kpiCell.dataset.column = 'kpi';
      kpiCell.textContent = String(item?.kpi || item?.kpi_code || 'N/A');
      kpiCell.title = String(item?.kpi_code || item?.kpi || '');
      row.append(kpiCell);
      row.append(createKpiTypeCell(item?.kpi_type, item?.row_type === 'category'));
      const gaps = item?.gaps && typeof item.gaps === 'object' ? item.gaps : {};
      const gapColors = item?.gap_colors && typeof item.gap_colors === 'object' ? item.gap_colors : {};
      const gapPartial = item?.gap_partial && typeof item.gap_partial === 'object' ? item.gap_partial : {};
      const gapEnvironments = item?.gap_environments && typeof item.gap_environments === 'object' ? item.gap_environments : {};
      for (const column of columns) addMatrixGapCell(row, firstValue(gaps, [column.id], null), firstValue(gapColors, [column.id], ''),
        firstValue(gapPartial, [column.id], false), firstValue(gapEnvironments, [column.id], []));
      tbody.append(row);
    }
    applyGapCategoryRunColors(tbody);
    table.append(thead, tbody);
    appendGapTotals(table, rows, columns.map(column => column.id));
    applyScorecardLayout(table);
    wrapper.append(table);
    pane.append(wrapper);
    observeScoringValueCells(table, wrapper);
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No KPI rows are available for this hierarchy comparison.';
      pane.append(empty);
    }
  }

  function renderScoringViews(pane, tables, thresholdLegend = []) {
    disconnectScoringValueObservers(pane);
    pane.replaceChildren();
    if (!tables.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No scoring comparison tables are available for this Saved Filter.';
      pane.append(empty);
      return;
    }
    const selected = appendComparisonSelector(pane, tables, 'score');
    appendContextHeader(pane, selected, 'score', 'Scoring Tables');
    appendScoringGapScale(pane, selected);
    const summarySection = document.createElement('section');
    summarySection.className = 'scoring-table-mode-section';
    const summaryHeading = document.createElement('h4');
    summaryHeading.className = 'scoring-table-section-title';
    summaryHeading.textContent = 'Scoring Tables — Summary';
    appendResultScope(summaryHeading, selected?.context);
    summarySection.append(summaryHeading);
    appendOperatorRankingLegend(summarySection);
    appendMatrixTable(summarySection, tableForMode(selected, 'summary'));
    pane.append(summarySection);
    const expandedSection = document.createElement('section');
    expandedSection.className = 'scoring-table-mode-section';
    const expandedHeading = document.createElement('h4');
    expandedHeading.className = 'scoring-table-section-title';
    expandedHeading.textContent = 'Scoring Tables — Breakdown';
    appendResultScope(expandedHeading, selected?.context);
    expandedSection.append(expandedHeading);
    appendThresholdLegend(expandedSection, thresholdLegend.length ? thresholdLegend : selected?.threshold_legend);
    appendMatrixTable(expandedSection, tableForMode(selected, 'expanded'));
    pane.append(expandedSection);
  }

  function renderGapViews(pane, tables) {
    disconnectScoringValueObservers(pane);
    pane.replaceChildren();
    if (!tables.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No GAP comparison tables are available for this Saved Filter.';
      pane.append(empty);
      return;
    }
    const selected = appendComparisonSelector(pane, tables, 'gap');
    appendContextHeader(pane, selected, 'gap');
    const baselineRaw = String(selected?.baseline_operator || 'the baseline');
    const operatorRaw = String(selected?.operator || 'this operator');
    const baseline = operatorPresentation(selected, baselineRaw).label;
    const operator = operatorPresentation(selected, operatorRaw).label;
    const rows = orderGapRows((Array.isArray(selected?.rows) ? selected.rows : []).filter(row => (
      row?.row_type === 'category' || row?.row_type === 'kpi'
      || (row?.gap_points !== null && row?.gap_points !== undefined && String(row.gap_points).trim() !== '' && Number.isFinite(Number(row.gap_points)))
    )), item => [item?.gap_points]);
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = `No comparable signed KPI GAPs were found for ${operator} against ${baseline} in this comparison context.`;
      pane.append(empty);
      return;
    }
    const gapInfo = document.createElement('div');
    gapInfo.className = 'scoring-gap-info';
    appendGapScaleAside(gapInfo, selected, rows);
    pane.append(gapInfo);
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-matrix-wrap';
    const table = document.createElement('table');
    table.className = 'scoring-comparison-table scoring-priority-table';
    const thead = document.createElement('thead');
    const header = document.createElement('tr');
    for (const [title, key] of [['Category', 'category'], ['KPI', 'kpi'], ['Type of KPI', 'type'], [`GAP (${operator} − ${baseline})`, 'gap']]) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = title;
      th.dataset.column = key;
      if (key === 'gap') th.className = 'scoring-gap-header';
      header.append(th);
    }
    thead.append(header);
    const tbody = document.createElement('tbody');
    const categoryRuns = new Map();
    for (let index = 0; index < rows.length; index += 1) {
      const item = rows[index];
      const category = String(item?.category ?? 'N/A');
      const previous = rows[index - 1];
      const startsCategoryRun = index === 0
        || String(previous?.category ?? 'N/A') !== category;
      if (!startsCategoryRun) continue;
      let span = 1;
      while (index + span < rows.length
        && String(rows[index + span]?.category ?? 'N/A') === category) span += 1;
      categoryRuns.set(index, {category, span});
    }
    rows.forEach((item, index) => {
      const row = document.createElement('tr');
      if (item?.row_type === 'category') {
        row.classList.add('scoring-category-subtotal');
        row.style.fontWeight = '700';
      }
      for (const [value, key] of [[item.category, 'category'], [item.kpi || item.kpi_code, 'kpi'], [item.kpi_type, 'type'], [item.gap_points, 'gap']]) {
        if (key === 'category') {
          const categoryRun = categoryRuns.get(index);
          if (!categoryRun) continue;
          const cell = document.createElement('td');
          cell.dataset.column = 'category';
          cell.rowSpan = categoryRun.span;
          cell.textContent = categoryRun.category;
          row.append(cell);
          continue;
        }
        if (key === 'type') {
          row.append(createKpiTypeCell(value, item?.row_type === 'category'));
          continue;
        }
        const cell = document.createElement('td');
        cell.dataset.column = key;
        if (key === 'gap') {
          cell.dataset.numeric = 'true';
          const partial = item?.gap_partial === true;
          const numericGap = value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
          cell.textContent = `${formatMatrixNumber(value, true)}${partial && numericGap ? '*' : ''}`;
          styleIncompleteValue(cell);
          cell.title = [
            'Signed GAP: compared operator weighted points minus baseline weighted points. Positive means the compared operator leads.',
            partialGapCoverage(partial, item?.gap_environments),
          ].filter(Boolean).join(' ');
          const color = safeHexColor(item?.gap_color);
          if (color) cell.style.backgroundColor = themedColor(color);
          if (Number(value) > 0) cell.classList.add('scoring-gap-gain');
          if (Number(value) < 0) cell.classList.add('scoring-gap-loss');
          cell.dataset.gap = !numericGap ? 'none' : Number(value) > 0 ? 'gain' : Number(value) < 0 ? 'loss' : 'zero';
          cell.style.setProperty('--gap-share', gapShare(color).toFixed(3));
        } else {
          cell.textContent = value === null || value === undefined || value === '' ? 'N/A' : String(value);
          if (key === 'kpi') cell.title = String(item.kpi_code || item.kpi || '');
        }
        row.append(cell);
      }
      tbody.append(row);
    });
    applyGapCategoryRunColors(tbody);
    table.append(thead, tbody);
    appendGapTotals(table, rows, [null]);
    applyScorecardLayout(table);
    wrapper.append(table);
    pane.append(wrapper);
    observeScoringValueCells(table, wrapper);
  }

  function renderGapSummaryViews(pane, tables) {
    disconnectScoringValueObservers(pane);
    pane.replaceChildren();
    if (!tables.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No GAP summary tables are available for this environment.';
      pane.append(empty);
      return;
    }
    const selected = appendComparisonSelector(pane, tables, 'gap-summary');
    if (!selected) return;

    const baselineRaw = String(selected.baseline_operator || '');
    const baseline = operatorPresentation(selected, baselineRaw || 'the reference operator').label;
    const operators = (Array.isArray(selected.operators) ? selected.operators : [])
      .map(String)
      .filter(operator => operator.toLowerCase() !== baselineRaw.toLowerCase());
    const comparisonStateKey = gapComparisonIdentity(selected, `gap-summary:${baselineRaw}`);
    let comparison = gapComparisonSelections.get(comparisonStateKey) || 'all';
    const selectedOperator = comparison.startsWith('operator:') ? comparison.slice('operator:'.length) : null;
    if (selectedOperator && !operators.includes(selectedOperator)) comparison = 'all';
    gapComparisonSelections.set(comparisonStateKey, comparison);

    const controls = document.createElement('div');
    controls.className = 'scoring-comparison-controls scoring-gap-comparison-controls';
    const label = document.createElement('label');
    label.textContent = 'GAP comparison';
    const select = document.createElement('select');
    select.dataset.gapSummaryOperator = '';
    select.dataset.gapSummaryStateKey = comparisonStateKey;
    select.setAttribute('aria-label', 'Choose all operators or one operator to compare with the reference');
    const allOption = document.createElement('option');
    allOption.value = 'all';
    allOption.textContent = `All vs ${baseline}`;
    allOption.selected = comparison === 'all';
    select.append(allOption);
    appendFocusOptions(select, operators.map(operator => {
      const presentation = operatorPresentation(selected, operator);
      return [`operator:${operator}`, `${presentation.label} vs ${baseline}`, operator, presentation.label];
    }));
    select.value = comparison;
    label.append(select);
    controls.append(label);
    pane.append(controls);

    appendContextHeader(pane, selected, 'gap-summary');
    const gapNote = document.createElement('p');
    gapNote.className = 'scoring-context-note';
    gapNote.textContent = `KPI GAP = compared operator weighted points minus ${baseline} weighted points for each KPI.`;
    const gapInfo = document.createElement('div');
    gapInfo.className = 'scoring-gap-info';
    gapInfo.append(gapNote);
    pane.append(gapInfo);

    const comparisons = comparison === 'all'
      ? operators
      : operators.filter(operator => `operator:${operator}` === comparison);
    const sortByGap = comparison !== 'all';
    const rows = orderGapRows(Array.isArray(selected.rows) ? selected.rows : [],
      item => comparisons.map(operator => firstValue(item?.gaps || {}, [operator], null)), sortByGap);
    appendGapScaleAside(gapInfo, selected, rows, comparison !== 'all');
    if (!comparisons.length || !rows.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = comparisons.length ? 'No KPI rows are available for this comparison context.' : 'No operators can be compared with the selected reference operator.';
      pane.append(empty);
      return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-matrix-wrap';
    const table = document.createElement('table');
    table.className = 'scoring-comparison-table scoring-priority-table scoring-gap-summary-table';
    const thead = document.createElement('thead');
    const header = document.createElement('tr');
    for (const [title, key] of [['Category', 'category'], ['KPI', 'kpi'], ['Type of KPI', 'type']]) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = title;
      th.dataset.column = key;
      header.append(th);
    }
    for (const operator of comparisons) {
      const presentation = operatorPresentation(selected, operator);
      const th = document.createElement('th');
      th.scope = 'col';
      th.className = 'scoring-gap-header scoring-gap-operator-header';
      th.dataset.column = 'gap';
      th.textContent = `${presentation.label} − ${baseline}`;
      th.title = `${operator} weighted score minus reference ${baselineRaw} weighted score`;
      if (presentation.color) th.style.setProperty('--operator-accent', presentation.color);
      th.style.setProperty('--operator-text', categoryLegendTextColor(presentation.color));
      header.append(th);
    }
    thead.append(header);

    const tbody = document.createElement('tbody');
    for (let index = 0; index < rows.length; index += 1) {
      const item = rows[index];
      const row = document.createElement('tr');
      if (item?.row_type === 'category') {
        row.classList.add('scoring-category-subtotal');
        row.style.fontWeight = '700';
      }
      const category = String(item?.category ?? '');
      const previous = rows[index - 1];
      const startsCategoryRun = index === 0
        || String(previous?.category ?? '') !== category;
      if (startsCategoryRun) {
        let span = 1;
        while (index + span < rows.length
          && String(rows[index + span]?.category ?? '') === category) span += 1;
        const categoryCell = document.createElement('td');
        categoryCell.className = 'scoring-category-cell';
        categoryCell.dataset.column = 'category';
        categoryCell.rowSpan = span;
        categoryCell.textContent = category || 'Unclassified';
        row.append(categoryCell);
      }
      const kpiCell = document.createElement('td');
      kpiCell.dataset.column = 'kpi';
      kpiCell.textContent = String(item?.kpi || item?.kpi_code || 'N/A');
      kpiCell.title = String(item?.kpi_code || item?.kpi || '');
      row.append(kpiCell);
      row.append(createKpiTypeCell(item?.kpi_type, item?.row_type === 'category'));

      const gaps = item?.gaps && typeof item.gaps === 'object' ? item.gaps : {};
      const gapColors = item?.gap_colors && typeof item.gap_colors === 'object' ? item.gap_colors : {};
      const gapPartial = item?.gap_partial && typeof item.gap_partial === 'object' ? item.gap_partial : {};
      const gapEnvironments = item?.gap_environments && typeof item.gap_environments === 'object' ? item.gap_environments : {};
      for (const operator of comparisons) addMatrixGapCell(row, firstValue(gaps, [operator], null), firstValue(gapColors, [operator], ''),
        firstValue(gapPartial, [operator], false), firstValue(gapEnvironments, [operator], []));
      tbody.append(row);
    }
    applyGapCategoryRunColors(tbody);
    table.append(thead, tbody);
    appendGapTotals(table, rows, comparisons);
    applyScorecardLayout(table);
    wrapper.append(table);
    pane.append(wrapper);
    observeScoringValueCells(table, wrapper);
  }

  function findKey(row, candidates) {
    const entries = Object.keys(row || {});
    for (const candidate of candidates) {
      const found = entries.find(key => key.toLowerCase() === candidate.toLowerCase());
      if (found) return found;
    }
    return null;
  }

  function rowText(row, candidates) {
    const key = findKey(row, candidates);
    return key ? String(row[key] ?? '') : '';
  }

  function scoreNumber(row) {
    const key = findKey(row, ['weighted_points', 'weighted_score', 'score', 'total_score', 'scoring', 'points']);
    if (!key) return null;
    if (row[key] === null || row[key] === undefined || String(row[key]).trim() === '') return null;
    const value = Number(row[key]);
    return Number.isFinite(value) ? {key, value} : null;
  }

  function aggregationValue(row, level) {
    const aliases = {
      'Dataset Type': ['dataset_type', 'cdr_type', 'dataset_kind', 'kind'],
      'Vendor': ['vendor', 'ran_vendor', 'manufacturer'],
      'Region': ['region', 'region_name'],
      'City': ['city', 'city_name'],
      'Operator': ['operator', 'operator_name', 'mno'],
    };
    const candidates = [level, ...(aliases[level] || [])];
    const key = findKey(row, candidates);
    return key ? String(row[key] ?? '') : '';
  }

  function wrappedSvgLabelLines(value, maxLength = 22, maxLines = 2) {
    const lines = [];
    let current = '';
    for (const word of String(value).split(/\s+/)) {
      const candidate = current ? `${current} ${word}` : word;
      if (candidate.length > maxLength && current) {
        lines.push(current);
        current = word;
      } else current = candidate;
    }
    if (current) lines.push(current);
    if (lines.length > maxLines) {
      const last = `${lines.slice(maxLines - 1).join(' ').slice(0, maxLength - 1)}…`;
      lines.splice(maxLines - 1, lines.length - maxLines + 1, last);
    }
    return lines;
  }

  function fittedSvgLabelLines(value, maxLength, maxLines = 2) {
    // Identifiers such as UK_Q2_SA_2026 have no spaces: also break after "_", "-" and "/", and shorten what
    // still does not fit so a label never runs into the neighbouring cells.
    const tokens = String(value).match(/\s+|[^\s_\-/]+[_\-/]*|[_\-/]+/g) || [];
    const lines = [];
    let current = '';
    for (const token of tokens) {
      if (/^\s+$/.test(token)) {
        if (current) current += ' ';
        continue;
      }
      if (current && `${current}${token}`.trimEnd().length > maxLength) {
        lines.push(current);
        current = '';
      }
      current += token;
    }
    if (current.trim()) lines.push(current);
    if (lines.length > maxLines) lines.splice(maxLines - 1, lines.length, lines.slice(maxLines - 1).join(''));
    return lines.map(line => line.trimEnd()).map(line => (
      line.length > maxLength ? `${line.slice(0, Math.max(1, maxLength - 1)).trimEnd()}…` : line));
  }

  function setChartTooltip(element, message, focusable = false) {
    const text = String(message || '').trim();
    if (!text) return element;
    element.setAttribute('data-chart-tooltip', text);
    element.setAttribute('aria-label', text);
    element.setAttribute('aria-describedby', chartTooltip.id);
    if (focusable) element.setAttribute('tabindex', '0');
    return element;
  }

  function formatChartNumber(value, options = {}) {
    return Number(value).toLocaleString('en-US', {useGrouping: false, ...options});
  }

  function formattedChartPoints(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? formatChartNumber(numeric, {maximumFractionDigits: 3}) : 'N/A';
  }

  function chartEnvironmentName(tableData) {
    const environment = String(tableData?.context?.environment || '');
    return environment ? environmentLabel(environment) : '';
  }

  function categoryLegendGray(index, count) {
    const channel = Math.round(58 + 168 * Math.max(0, index) / Math.max(1, count - 1));
    return `#${channel.toString(16).padStart(2, '0').repeat(3)}`;
  }

  let chartLegendMeasureContext = null;

  function chartLegendTextWidth(label) {
    try {
      if (!chartLegendMeasureContext) chartLegendMeasureContext = document.createElement('canvas').getContext('2d');
      if (chartLegendMeasureContext) {
        chartLegendMeasureContext.font = '750 15px "IBM Plex Sans", "Segoe UI", sans-serif';
        return chartLegendMeasureContext.measureText(label).width;
      }
    } catch (_error) {
      // Canvas measurement is optional in test and restricted browser contexts.
    }
    return label.length * 8;
  }

  function chartLegendRows(entries, width, left, right, fallbackColor) {
    const rows = [];
    for (const entry of entries) {
      const label = String(entry?.label || '');
      const entryWidth = 14 + 7 + chartLegendTextWidth(label) + 22;
      let row = rows[rows.length - 1];
      if (!row || (row.width + entryWidth > width - left - right && row.entries.length)) {
        row = {width: 0, entries: []};
        rows.push(row);
      }
      row.entries.push({...entry, label, entryWidth, color: safeHexColor(entry?.color) || fallbackColor});
      row.width += entryWidth;
    }
    return rows;
  }

  function categoryLegendTextLines(value, maxLength, maxLines = 2) {
    const lines = [];
    let current = '';
    for (let word of String(value).trim().split(/\s+/).filter(Boolean)) {
      while (word.length > maxLength) {
        if (current) {
          lines.push(current);
          current = '';
        }
        lines.push(word.slice(0, maxLength));
        word = word.slice(maxLength);
      }
      if (!word) continue;
      const candidate = current ? `${current} ${word}` : word;
      if (candidate.length > maxLength && current) {
        lines.push(current);
        current = word;
      } else {
        current = candidate;
      }
    }
    if (current) lines.push(current);
    if (lines.length > maxLines) {
      const remainder = lines.slice(maxLines - 1).join(' ');
      lines.splice(maxLines - 1, lines.length - maxLines + 1,
        remainder.length > maxLength ? `${remainder.slice(0, maxLength - 1).trimEnd()}…` : remainder);
    }
    return lines;
  }

  function categoryLegendTextColor(background) {
    const color = safeHexColor(background);
    if (!color) return '#203744';
    const channels = [1, 3, 5].map(offset => Number.parseInt(color.slice(offset, offset + 2), 16) / 255);
    const linear = channels.map(channel => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4);
    const luminance = .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
    const whiteContrast = 1.05 / (luminance + .05);
    const darkContrast = (luminance + .05) / .085;
    return darkContrast >= whiteContrast ? '#203744' : '#ffffff';
  }

  // The label of a segment of a stacked bar, never larger than ``maximum`` (below the total over the bar): across it
  // (down to 9px), else turned 90° when the segment is tall enough, else across it at 8px; none when it fits neither
  // way ({size: 0}).
  function stackedSegmentLabelLayout(label, width, height, maximum = 22) {
    const across = Math.floor(Math.min(maximum, (width - 8) / (label.length * .68), (height - 5) / 1.2));
    if (across >= 9) return {size: across, rotated: false};
    const turned = Math.floor(Math.min(maximum, (height - 8) / (label.length * .68), (width - 5) / 1.2));
    if (turned >= 9) return {size: turned, rotated: true};
    return across >= 8 ? {size: across, rotated: false} : {size: 0, rotated: false};
  }

  // Places a segment label at the centre of its segment, turned 90° when the layout says so.
  function placeSegmentLabel(label, centerX, centerY, layout) {
    label.setAttribute('x', String(centerX));
    label.setAttribute('text-anchor', 'middle');
    if (layout.rotated) {
      label.setAttribute('y', String(centerY));
      label.setAttribute('dominant-baseline', 'central');
      label.setAttribute('transform', `rotate(-90 ${centerX} ${centerY})`);
    } else {
      label.setAttribute('y', String(centerY + layout.size * .34));
    }
    label.style.fontSize = `${layout.size}px`;
  }

  function scoringChartScale(configuredMax, actualMax) {
    const rawTarget = Math.max(0, Number(configuredMax) || 0, Number(actualMax) || 0);
    const nearestInteger = Math.round(rawTarget);
    const target = Math.abs(rawTarget - nearestInteger) <= 1e-9 * Math.max(1, rawTarget)
      ? nearestInteger : rawTarget;
    if (!target) return {maximum: 5, intervals: 5};
    const exact = [];
    if (Number.isInteger(target)) {
      for (let intervals = 3; intervals <= 6; intervals += 1) {
        if (target % intervals !== 0) continue;
        const step = target / intervals;
        const trailingZeros = (String(step).match(/0*$/) || [''])[0].length;
        exact.push({maximum: target, intervals, trailingZeros});
      }
    }
    if (exact.length) {
      exact.sort((left, right) => right.trailingZeros - left.trailingZeros
        || Math.abs(left.intervals - 5) - Math.abs(right.intervals - 5));
      return exact[0];
    }
    const unit = 10 ** Math.max(0, Math.floor(Math.log10(target / 5)) - 1);
    const candidates = Array.from({length: 4}, (_, index) => {
      const intervals = index + 3;
      const step = Math.ceil(target / intervals / unit) * unit;
      return {maximum: step * intervals, intervals};
    });
    candidates.sort((left, right) => left.maximum - right.maximum
      || Math.abs(left.intervals - 5) - Math.abs(right.intervals - 5));
    return candidates[0];
  }

  function configuredChartMaximum(tableData) {
    return (Array.isArray(tableData?.rows) ? tableData.rows : []).reduce((sum, row) => {
      const points = Number(row?.max_points);
      return sum + (Number.isFinite(points) ? points : 0);
    }, 0);
  }

  // Every bar is drawn in the width of ten, so the chart fits its card at the height it has with ten bars and never
  // scrolls sideways: more bars are narrower (their totals and labels smaller or turned 90°), and the gaps between their
  // groups (``groupGap`` at most) shrink to fit them too.
  function bestNetworkHorizontalGeometry(count, groupTransitions = 0, groupGap = 0) {
    const left = 110, right = 36;
    const width = Math.max(980, Math.min(count, 10) * 85 + 128);
    const inner = width - left - right;
    const gap = groupTransitions ? Math.min(groupGap, inner * .2 / groupTransitions) : 0;
    const step = Math.max(1, (inner - groupTransitions * gap) / Math.max(count, 1));
    return {width, left, right, step, barWidth: Math.min(120, step * .7), groupGap: gap};
  }

  // The chart takes the width of its card (see bestNetworkHorizontalGeometry).
  function fitBestNetworkChartWidth(svg) {
    svg.style.width = '100%';
    svg.style.minWidth = '0';
  }

  // The total over a bar: across (up to its 26px) when the bar is wide enough for it at 11px, else turned 90°, reading
  // upwards from the top of the bar, as wide as the bar, so the totals of narrow bars do not run into each other.
  function barTotalLayout(text, step) {
    const fits = Math.floor(step * .94 / Math.max(1, String(text).length * .6)) >= 11;
    return fits ? {size: bestNetworkTotalSize(text, step), rotated: false}
      : {size: Math.max(7, Math.min(16, Math.floor(step * .9))), rotated: true};
  }

  function placeBarTotal(label, centerX, barTop, step, offset) {
    const layout = barTotalLayout(label.textContent, step);
    label.setAttribute('x', String(centerX));
    if (!layout.rotated) {
      label.setAttribute('y', String(barTop - offset));
      if (layout.size < 26) label.style.fontSize = `${layout.size}px`;
      return;
    }
    const y = barTop - 6;
    label.setAttribute('y', String(y));
    label.setAttribute('text-anchor', 'start');
    label.setAttribute('dominant-baseline', 'central');
    label.setAttribute('transform', `rotate(-90 ${centerX} ${y})`);
    label.style.fontSize = `${layout.size}px`;
  }

  // The largest size of the labels inside the bars, a little smaller than the totals over them: 70% of a total across,
  // 85% of a total turned 90° (the labels then turn too when they do not fit across).
  function barSegmentLabelMaximum(step) {
    const total = barTotalLayout('000.0', step);
    return Math.floor(total.size * (total.rotated ? .85 : .7));
  }

  // The size of the total over a bar, smaller than its 26px when the bar is too narrow for it (``step``: the width of a
  // bar and its gap).
  function bestNetworkTotalSize(text, step) {
    return Math.max(11, Math.min(26, Math.floor(step * .94 / Math.max(1, String(text).length * .6))));
  }

  function makeSvgChart(title, rows, operatorTable, options = {}) {
    const stacked = Boolean(options.stacked);
    const categories = Array.isArray(options.categoryOrder)
      ? [...new Set([...options.categoryOrder.map(String), ...rows.map(row => String(row.category))])]
      : [...new Set(rows.map(row => row.category))];
    const presentSeries = new Set(rows.map(row => row.series));
    const mappedOrder = Array.isArray(operatorTable?.operators) ? operatorTable.operators.map(String) : [];
    const requestedSeriesOrder = Array.isArray(options.seriesOrder) ? options.seriesOrder.map(String) : mappedOrder;
    const series = [...requestedSeriesOrder.filter(name => presentSeries.has(name)),
      ...[...presentSeries].filter(name => !requestedSeriesOrder.includes(name)).sort((left, right) => left.localeCompare(right))];
    const hierarchyColumns = Array.isArray(options.hierarchyColumns)
      ? options.hierarchyColumns
      : Object.values(options.hierarchyColumns || {});
    const hierarchyColumnsById = new Map(hierarchyColumns.map(column => [String(column?.id ?? ''), column]));
    const requestedHierarchyLevels = Array.isArray(options.hierarchyLevels) ? options.hierarchyLevels.map(String) : [];
    // A level with the same value under every bar (a single campaign, for example) adds nothing to the axis;
    // the bar tooltips keep the complete hierarchy path.
    const varyingHierarchyLevels = requestedHierarchyLevels.filter((level, depth) => new Set(
      hierarchyColumns.map(column => hierarchyPathEntry(column, depth, requestedHierarchyLevels).rawValue),
    ).size > 1);
    const hierarchyLevels = varyingHierarchyLevels.length ? varyingHierarchyLevels : requestedHierarchyLevels.slice(0, 1);
    const hasHierarchyAxis = hierarchyLevels.length > 0 && hierarchyColumnsById.size > 0;
    const groupKeys = categories.map(category => String(options.groupKeyForCategory?.(category) || ''));
    const groupTransitions = stacked && hasHierarchyAxis
      ? groupKeys.slice(1).filter((key, index) => key && groupKeys[index] && key !== groupKeys[index]).length : 0;
    const categoryGroupGap = stacked && hasHierarchyAxis ? Math.max(0, Number(options.categoryGroupGap) || 14) : 0;
    const bestNetworkGeometry = stacked
      ? bestNetworkHorizontalGeometry(categories.length, groupTransitions, categoryGroupGap) : null;
    const requestedChartWidth = Number(options.fitWidth);
    // A Breakdown with a hierarchy fits the width of its card too (``fitWidth``, else 1180), its bars narrower.
    const clusteredHierarchyWidth = !stacked && hasHierarchyAxis
      ? Math.min(categories.length * (series.length * 84 + 28) + 138, Number.isFinite(requestedChartWidth) && requestedChartWidth > 0
        ? Math.max(720, Math.floor(requestedChartWidth)) : 1180) : 0;
    const width = bestNetworkGeometry?.width || clusteredHierarchyWidth || (Number.isFinite(requestedChartWidth) && requestedChartWidth > 0
      ? Math.max(720, Math.floor(requestedChartWidth))
      : Math.max(1180, categories.length * Math.max(168, series.length * 38 + 22) + 150));
    const baseHeight = 700;
    const left = bestNetworkGeometry?.left ?? 110, right = bestNetworkGeometry?.right ?? 28;
    const maxValue = stacked
      ? Math.max(0, ...categories.map(category => series.reduce((sum, seriesName) => {
        const row = rows.find(candidate => String(candidate.category) === String(category) && String(candidate.series) === seriesName);
        const value = row?.value === null || row?.value === undefined || String(row.value).trim() === '' ? Number.NaN : Number(row.value);
        return sum + (Number.isFinite(value) ? Math.max(0, value) : 0);
      }, 0)))
      : Math.max(0, ...rows.map(row => Number(row.value)).filter(Number.isFinite));
    const scale = scoringChartScale(stacked ? configuredChartMaximum(operatorTable) : 0, maxValue);
    const scaleMaximum = scale.maximum;
    const step = bestNetworkGeometry?.step ?? Math.max(1, (width - left - right) / Math.max(categories.length, 1));
    const groupGap = bestNetworkGeometry ? bestNetworkGeometry.groupGap : categoryGroupGap;
    const categoryStarts = new Map();
    let categoryCursor = left;
    categories.forEach((category, index) => {
      if (index && groupKeys[index] && groupKeys[index - 1] && groupKeys[index] !== groupKeys[index - 1]) categoryCursor += groupGap;
      categoryStarts.set(String(category), categoryCursor);
      categoryCursor += step;
    });
    // The rows of the hierarchy axis take the room their labels need (turned 90° when they do not fit across); every
    // category of a Breakdown has the same bands.
    let axisBandsHeight = 0;
    if (hasHierarchyAxis && stacked) {
      axisBandsHeight = hierarchyAxisRows(categories, hierarchyLevels, hierarchyColumnsById, categoryStarts, step, left).height;
    } else if (hasHierarchyAxis && categories.length) {
      const slotWidth = step * .86 / Math.max(series.length, 1);
      const groupStart = left + step * .07;
      const starts = new Map(series.map((name, index) => [name, groupStart + index * slotWidth]));
      axisBandsHeight = hierarchyAxisRows(series, hierarchyLevels, hierarchyColumnsById, starts, slotWidth, groupStart).height;
    }
    const baseBottom = Math.max(150, 80 + axisBandsHeight);
    const fallbackColors = ['#14867d', '#df7a45', '#5a82aa', '#8b63b1', '#b49a32'];
    const presentations = new Map(series.map((name, index) => {
      const presentation = options.seriesStyles?.[name] || operatorPresentation(operatorTable, name);
      return [name, {...presentation, chartColor: presentation.color || fallbackColors[index % fallbackColors.length]}];
    }));
    const legendEntries = Array.isArray(options.legendEntries)
      ? options.legendEntries
      : series.map(name => ({label: presentations.get(name).label, color: presentations.get(name).chartColor, title: name}));
    const legendRows = chartLegendRows(legendEntries, width, left, right, fallbackColors[0]);
    const categoryLegendEntries = Array.isArray(options.categoryLegendEntries) ? options.categoryLegendEntries : [];
    const categoryLegendHeight = categoryLegendEntries.length ? 76 : 0;
    const height = baseHeight + categoryLegendHeight;
    const top = Math.max(76, 42 + legendRows.length * 20);
    const chartHeight = baseHeight - top - baseBottom;
    const axisTop = top + 36;
    const axisHeight = chartHeight - 36;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('class', 'scoring-chart-svg');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', title);
    if (stacked) fitBestNetworkChartWidth(svg);

    legendRows.forEach((row, rowIndex) => {
      let x = stacked ? left + Math.max(0, (width - left - right - (row.width - 22)) / 2) : left;
      for (const entry of row.entries) {
        const color = entry.color;
        const swatch = document.createElementNS(svg.namespaceURI, 'rect');
        swatch.setAttribute('x', String(x)); swatch.setAttribute('y', String(25 + rowIndex * 20)); swatch.setAttribute('width', '14'); swatch.setAttribute('height', '14');
        swatch.setAttribute('rx', '3'); swatch.setAttribute('fill', color);
        const legend = document.createElementNS(svg.namespaceURI, 'text');
        legend.setAttribute('x', String(x + 21)); legend.setAttribute('y', String(37 + rowIndex * 20));
        legend.setAttribute('class', 'scoring-chart-legend');
        legend.textContent = entry.label;
        setChartTooltip(swatch, String(entry.title || entry.label), true);
        setChartTooltip(legend, String(entry.title || entry.label), true);
        svg.append(swatch, legend);
        x += entry.entryWidth;
      }
    });

    const baselineY = axisTop + axisHeight;
    for (let tickIndex = 0; tickIndex <= scale.intervals; tickIndex += 1) {
      const value = scaleMaximum * (scale.intervals - tickIndex) / scale.intervals;
      const y = axisTop + axisHeight * tickIndex / scale.intervals;
      const grid = document.createElementNS(svg.namespaceURI, 'line');
      grid.setAttribute('x1', String(left)); grid.setAttribute('x2', String(width - right));
      grid.setAttribute('y1', String(y)); grid.setAttribute('y2', String(y));
      grid.setAttribute('stroke', tickIndex === scale.intervals ? '#aeb9bd' : '#e1e7e8');
      if (tickIndex !== scale.intervals) grid.setAttribute('stroke-dasharray', '4 5');
      const tick = document.createElementNS(svg.namespaceURI, 'text');
      tick.setAttribute('x', String(left - 12)); tick.setAttribute('y', String(y + 4));
      tick.setAttribute('text-anchor', 'end'); tick.setAttribute('class', 'scoring-chart-tick');
      tick.textContent = formatChartNumber(Math.round(value), {maximumFractionDigits: 0});
      svg.append(grid, tick);
    }
    const axisLabel = document.createElementNS(svg.namespaceURI, 'text');
    axisLabel.setAttribute('x', '22'); axisLabel.setAttribute('y', String(axisTop + axisHeight / 2));
    axisLabel.setAttribute('text-anchor', 'middle'); axisLabel.setAttribute('class', 'scoring-chart-axis-label');
    axisLabel.setAttribute('transform', `rotate(-90 22 ${axisTop + axisHeight / 2})`);
    axisLabel.textContent = options.axisLabel || 'Weighted score (points)';
    svg.append(axisLabel);
    if (stacked && hasHierarchyAxis) {
      appendHierarchyAxisBands(svg, categories, hierarchyLevels, hierarchyColumnsById, categoryStarts, step, baselineY, left, width - right);
    }

    categories.forEach((category, categoryIndex) => {
      if (stacked) {
        const barWidth = bestNetworkGeometry.barWidth;
        const categoryStart = categoryStarts.get(String(category)) ?? left + step * categoryIndex;
        const x = categoryStart + (step - barWidth) / 2;
        let stackY = baselineY;
        let hasValue = false;
        let complete = true;
        let total = 0;
        for (const [seriesIndex, seriesName] of series.entries()) {
          const row = rows.find(candidate => String(candidate.category) === String(category) && String(candidate.series) === seriesName);
          if (!row) continue;
          const numeric = row.value === null || row.value === undefined || String(row.value).trim() === '' ? Number.NaN : Number(row.value);
          if (!Number.isFinite(numeric)) {
            complete = false;
            continue;
          }
          hasValue = true;
          total += numeric;
          complete = complete && row.complete !== false;
          const segmentHeight = Math.max(0, numeric / scaleMaximum * axisHeight);
          const segmentY = stackY - segmentHeight;
          const configuredSegmentColor = typeof options.segmentColor === 'function'
            ? safeHexColor(options.segmentColor(category, seriesName, seriesIndex, row)) : '';
          const color = configuredSegmentColor || presentations.get(seriesName).chartColor;
          const rect = document.createElementNS(svg.namespaceURI, 'rect');
          rect.setAttribute('x', String(x)); rect.setAttribute('y', String(segmentY));
          rect.setAttribute('width', String(barWidth)); rect.setAttribute('height', String(Math.max(0, segmentHeight)));
          rect.setAttribute('fill', color);
          if (hasHierarchyAxis) {
            rect.setAttribute('stroke', '#ffffff');
            rect.setAttribute('stroke-width', '.5');
          }
          const visibleCategory = options.categoryLabels?.[category] || category;
          const fullCategory = options.categoryTooltips?.[category] || visibleCategory;
          const hierarchyColumn = hierarchyColumnsById.get(String(category));
          const operatorName = hierarchyColumn
            ? String(hierarchyColumn.operator || firstValue(hierarchyColumn.styleSource, ['operator'], '') || '')
            : String(options.operatorForCategory?.(category) || '');
          const tooltipParts = [
            `KPI category: ${seriesName}`,
            hasHierarchyAxis ? `Hierarchy: ${fullCategory}` : `Category: ${fullCategory}`,
            operatorName ? `Operator: ${operatorPresentation(operatorTable, operatorName).label}` : '',
            chartEnvironmentName(operatorTable) ? `Environment: ${chartEnvironmentName(operatorTable)}` : '',
            `Weighted points: ${formattedChartPoints(numeric)}`,
            row.complete === false ? 'Coverage: incomplete' : '',
          ].filter(Boolean);
          setChartTooltip(rect, tooltipParts.join('\n'), true);
          svg.append(rect);
          const segmentText = formatChartNumber(numeric, {minimumFractionDigits: 1, maximumFractionDigits: 1});
          const layout = stackedSegmentLabelLayout(segmentText, barWidth, segmentHeight, barSegmentLabelMaximum(step));
          if (layout.size) {
            const segmentLabel = document.createElementNS(svg.namespaceURI, 'text');
            segmentLabel.setAttribute('class', 'scoring-best-network-segment');
            placeSegmentLabel(segmentLabel, x + barWidth / 2, segmentY + segmentHeight / 2, layout);
            segmentLabel.style.fill = categoryLegendTextColor(color);
          styleIncompleteValue(segmentLabel);
            segmentLabel.textContent = segmentText;
            setChartTooltip(segmentLabel, tooltipParts.join('\n'));
            svg.append(segmentLabel);
          }
          stackY = segmentY;
        }
        if (!hasValue) {
          const unavailable = document.createElementNS(svg.namespaceURI, 'text');
          unavailable.setAttribute('x', String(x + barWidth / 2));
          unavailable.setAttribute('y', String(baselineY - 7));
          unavailable.setAttribute('text-anchor', 'middle');
          unavailable.setAttribute('class', 'scoring-chart-unavailable');
          unavailable.textContent = 'N/A';
          const hierarchyColumn = hierarchyColumnsById.get(String(category));
          const operatorName = hierarchyColumn
            ? String(hierarchyColumn.operator || '') : String(options.operatorForCategory?.(category) || '');
          setChartTooltip(unavailable, [
            'KPI categories total: unavailable because coverage is incomplete',
            options.categoryTooltips?.[category] ? `Hierarchy: ${options.categoryTooltips[category]}` : '',
            operatorName ? `Operator: ${operatorPresentation(operatorTable, operatorName).label}` : '',
            chartEnvironmentName(operatorTable) ? `Environment: ${chartEnvironmentName(operatorTable)}` : '',
          ].filter(Boolean).join('\n'), true);
          svg.append(unavailable);
        } else {
          const totalLabel = document.createElementNS(svg.namespaceURI, 'text');
          totalLabel.setAttribute('text-anchor', 'middle');
          totalLabel.setAttribute('class', 'scoring-chart-value scoring-best-network-total');
          totalLabel.textContent = `${formatChartNumber(total, {minimumFractionDigits: 1, maximumFractionDigits: 1})}${complete ? '' : '*'}`;
          placeBarTotal(totalLabel, x + barWidth / 2, stackY, step, 10);
          styleIncompleteValue(totalLabel);
          const hierarchyColumn = hierarchyColumnsById.get(String(category));
          const operatorName = hierarchyColumn
            ? String(hierarchyColumn.operator || firstValue(hierarchyColumn.styleSource, ['operator'], '') || '')
            : String(options.operatorForCategory?.(category) || '');
          setChartTooltip(totalLabel, [
            `KPI categories total: ${formattedChartPoints(total)}`,
            hasHierarchyAxis && options.categoryTooltips?.[category] ? `Hierarchy: ${options.categoryTooltips[category]}` : '',
            operatorName ? `Operator: ${operatorPresentation(operatorTable, operatorName).label}` : '',
            chartEnvironmentName(operatorTable) ? `Environment: ${chartEnvironmentName(operatorTable)}` : '',
            complete ? 'Coverage: complete' : 'Coverage: incomplete',
          ].filter(Boolean).join('\n'), true);
          svg.append(totalLabel);
        }
      } else {
      const groupWidth = step * .86;
      const slotWidth = groupWidth / Math.max(series.length, 1);
      const barWidth = Math.min(48, slotWidth * .64);
      const groupStart = left + step * categoryIndex + (step - groupWidth) / 2;
      if (hasHierarchyAxis) {
        const starts = new Map(series.map((name, index) => [name, groupStart + index * slotWidth]));
        appendHierarchyAxisBands(svg, series, hierarchyLevels, hierarchyColumnsById, starts, slotWidth,
          baselineY, groupStart, groupStart + groupWidth);
      }
      series.forEach((seriesName, seriesIndex) => {
        const row = rows.find(candidate => candidate.category === category && candidate.series === seriesName);
        if (!row) return;
        const x = groupStart + slotWidth * seriesIndex + (slotWidth - barWidth) / 2;
        if (row.value === null || row.value === undefined || !Number.isFinite(Number(row.value))) {
          const unavailable = svgElement(svg, 'text', {x: x + barWidth / 2, y: baselineY - 7, 'text-anchor': 'middle', class: 'scoring-chart-unavailable'});
          unavailable.textContent = 'N/A';
          const fullCategory = options.categoryTooltips?.[category] || options.categoryLabels?.[category] || category;
          setChartTooltip(unavailable, [
            `Category: ${fullCategory}`,
            options.seriesTooltips?.[seriesName] || `${mappedOrder.includes(seriesName) ? 'Operator' : 'Series'}: ${presentations.get(seriesName).label}`,
            chartEnvironmentName(operatorTable) ? `Environment: ${chartEnvironmentName(operatorTable)}` : '',
            'Weighted points: unavailable because coverage is incomplete',
          ].filter(Boolean).join('\n'), true);
          svg.append(unavailable);
          return;
        }
        const barHeight = Math.max(0, row.value / scaleMaximum * axisHeight);
        const barTop = baselineY - barHeight;
        const color = presentations.get(seriesName).chartColor;
        const rect = document.createElementNS(svg.namespaceURI, 'rect');
        rect.setAttribute('x', String(x)); rect.setAttribute('y', String(barTop));
        rect.setAttribute('width', String(barWidth)); rect.setAttribute('height', String(Math.max(0, barHeight)));
        rect.setAttribute('rx', '4'); rect.setAttribute('fill', color);
        const fullCategory = options.categoryTooltips?.[category] || options.categoryLabels?.[category] || category;
        const isOperatorSeries = mappedOrder.includes(seriesName);
        const tooltipParts = [
          `Category: ${fullCategory}`,
          options.seriesTooltips?.[seriesName] || `${isOperatorSeries ? 'Operator' : 'Series'}: ${presentations.get(seriesName).label}`,
          chartEnvironmentName(operatorTable) ? `Environment: ${chartEnvironmentName(operatorTable)}` : '',
          `Weighted points: ${formattedChartPoints(row.value)}`,
          row.complete === false ? 'Coverage: incomplete' : '',
        ].filter(Boolean);
        setChartTooltip(rect, tooltipParts.join('\n'), true);
        const value = document.createElementNS(svg.namespaceURI, 'text');
        value.setAttribute('x', String(x + barWidth / 2));
        value.setAttribute('text-anchor', 'middle'); value.setAttribute('class', 'scoring-chart-value');
        value.textContent = `${formatChartNumber(row.value, {maximumFractionDigits: Number.isInteger(row.value) ? 0 : 2})}${row.complete === false ? '*' : ''}`;
        // Every other value a row higher, each has the width of two bars: smaller up to 9px, then turned 90° above its
        // bar, as wide as the bar; under 6px it is left to the tooltip of the bar.
        const valueSize = Math.floor(Math.min(15, (slotWidth * 2 - 4) / Math.max(1, value.textContent.length * .6)));
        if (valueSize >= 9) {
          value.setAttribute('y', String(Math.max(top + 14, barTop - 7 - (seriesIndex % 2) * 22)));
          if (valueSize < 15) value.style.fontSize = `${valueSize}px`;
        } else {
          const valueY = barTop - 5;
          value.setAttribute('y', String(valueY));
          value.setAttribute('text-anchor', 'start');
          value.setAttribute('dominant-baseline', 'central');
          value.setAttribute('transform', `rotate(-90 ${x + barWidth / 2} ${valueY})`);
          value.style.fontSize = `${Math.min(12, Math.floor(slotWidth * .9))}px`;
        }
        styleIncompleteValue(value);
        setChartTooltip(value, tooltipParts.join('\n'));
        svg.append(rect);
        if (valueSize >= 9 || slotWidth >= 6) svg.append(value);
      });
      }
      if (!hasHierarchyAxis || !stacked) {
        const lines = [];
        const visibleCategory = options.categoryLabels?.[category] || category;
        const fullCategory = options.categoryTooltips?.[category] || visibleCategory;
        // The categories of a Breakdown with a hierarchy share the width of the card: shortened to their width.
        lines.push(...(!stacked && hasHierarchyAxis
          ? fittedSvgLabelLines(visibleCategory, Math.max(4, Math.min(22, Math.floor((step - 8) / 9))), 2)
          : wrappedSvgLabelLines(visibleCategory, stacked ? 24 : 22, stacked ? 4 : 2)));
        const label = document.createElementNS(svg.namespaceURI, 'text');
        const categoryStart = categoryStarts.get(String(category)) ?? left + step * categoryIndex;
        const labelX = categoryStart + step / 2;
        label.setAttribute('x', String(labelX)); label.setAttribute('y', String(baselineY + 24 + (hasHierarchyAxis ? axisBandsHeight + 16 : 0)));
        label.setAttribute('text-anchor', 'middle'); label.setAttribute('class', 'scoring-chart-category');
        lines.forEach((line, lineIndex) => {
          const span = document.createElementNS(svg.namespaceURI, 'tspan');
          span.setAttribute('x', String(labelX)); span.setAttribute('dy', lineIndex ? '1.15em' : '0');
          span.textContent = line;
          label.append(span);
        });
        setChartTooltip(label, [
          `Category: ${fullCategory}`,
          chartEnvironmentName(operatorTable) ? `Environment: ${chartEnvironmentName(operatorTable)}` : '',
        ].filter(Boolean).join('\n'), true);
        svg.append(label);
      }
    });
    if (categoryLegendEntries.length) {
      svg.append(svgElement(svg, 'line', {
        x1: left, x2: width - right, y1: baseHeight + 3, y2: baseHeight + 3,
        stroke: '#d6dddf', 'stroke-width': 1,
      }));
      const legendTitle = svgElement(svg, 'text', {
        x: left, y: baseHeight + 17, class: 'scoring-chart-category-legend-title',
      });
      legendTitle.textContent = 'KPI categories';
      svg.append(legendTitle);
      const bandX = left;
      const bandY = baseHeight + 25;
      const bandWidth = width - left - right;
      const bandHeight = 40;
      const segmentWidth = bandWidth / categoryLegendEntries.length;
      categoryLegendEntries.forEach((entry, index) => {
        const x = bandX + segmentWidth * index;
        const fill = safeHexColor(entry?.color) || '#777777';
        const labelText = String(entry?.label || '');
        const tooltip = String(entry?.title || labelText);
        const segment = svgElement(svg, 'rect', {
          x, y: bandY, width: segmentWidth, height: bandHeight,
          fill, stroke: '#ffffff', 'stroke-width': 1,
          class: 'scoring-chart-category-legend-segment',
        });
        setChartTooltip(segment, tooltip, true);
        svg.append(segment);
        const fontSize = segmentWidth < 72 ? 10 : 12;
        const maxLength = Math.max(3, Math.floor((segmentWidth - 12) / (fontSize * .62)));
        const lines = categoryLegendTextLines(labelText, maxLength, 2);
        const label = svgElement(svg, 'text', {
          x: x + segmentWidth / 2,
          y: bandY + (bandHeight - lines.length * 14) / 2 + 11,
          'text-anchor': 'middle',
          class: 'scoring-chart-category-legend-label',
        });
        label.style.fontSize = `${fontSize}px`;
        label.style.fill = categoryLegendTextColor(fill);
        lines.forEach((line, lineIndex) => {
          const span = svgElement(svg, 'tspan', {
            x: x + segmentWidth / 2,
            dy: lineIndex ? 14 : 0,
          });
          span.textContent = line;
          label.append(span);
        });
        setChartTooltip(label, tooltip, true);
        svg.append(label);
      });
    }
    return svg;
  }

  function chartTableForRow(row, scoreTables) {
    return scoreTables.find(table => comparisonScopeFields.every(field => String(firstValue(table.context || {}, [field], '') ?? '')
      === String(firstValue(row, [field], '') ?? '')));
  }

  function scoreChartRows(scoreTables) {
    const chartRows = [];
    for (const table of scoreTables) {
      const operators = Array.isArray(table?.operators) ? table.operators.map(String) : [];
      const grouped = new Map();
      for (const item of Array.isArray(table?.rows) ? table.rows : []) {
        const category = String(item?.category || 'Other');
        if (!grouped.has(category)) grouped.set(category, new Map());
        const byOperator = grouped.get(category);
        for (const operator of operators) {
          if (!byOperator.has(operator)) byOperator.set(operator, {points: 0, hasPoints: false, complete: true, count: 0});
          const aggregate = byOperator.get(operator);
          aggregate.count += 1;
          const cell = operatorValue(item?.values || {}, operator);
          const rawPoints = cell && typeof cell === 'object' ? firstValue(cell, ['points', 'weighted_points'], null) : null;
          const points = rawPoints === null || rawPoints === undefined || String(rawPoints).trim() === '' ? Number.NaN : Number(rawPoints);
          if (Number.isFinite(points)) {
            aggregate.points += points;
            aggregate.hasPoints = true;
          }
          if (!cell || cell.complete !== true || !Number.isFinite(points)) aggregate.complete = false;
        }
      }
      for (const [category, byOperator] of grouped) {
        for (const operator of operators) {
          const aggregate = byOperator.get(operator);
          const value = aggregate?.hasPoints ? aggregate.points : null;
          chartRows.push({
            ...(table.context || {}),
            category,
            operator,
            weighted_points: value,
            complete: Boolean(aggregate?.count && aggregate.complete),
          });
        }
      }
    }
    return chartRows;
  }

  function chartOperatorLegend(operatorTable, operators) {
    const fallbackColors = ['#14867d', '#df7a45', '#5a82aa', '#8b63b1', '#b49a32'];
    const colors = new Map();
    const entries = operators.map((operator, index) => {
      const presentation = operatorPresentation(operatorTable, operator);
      const style = firstValue(operatorTable?.operator_styles || {}, [operator], {});
      const isReference = style?.is_reference === true || isReferenceOperator(operatorTable, operator);
      const color = presentation.color || fallbackColors[index % fallbackColors.length];
      colors.set(String(operator), color);
      return {
        label: `${presentation.label}${isReference ? ' (Reference)' : ''}`,
        color,
        title: `${presentation.label}${isReference ? ' is the reference operator.' : ''} Bar segments show KPI category shades; hover a bar for category and score details.`,
      };
    });
    return {colors, entries};
  }

  function chartCategoryLegend(categories, description = 'Grayscale key') {
    return categories.map((category, index) => ({
      label: category,
      color: categoryLegendGray(index, categories.length),
      title: `${category}. ${description} ${index + 1} identifies this KPI category.`,
    }));
  }

  function chartFitWidth(pane) {
    const width = Number(pane?.getBoundingClientRect?.().width || pane?.clientWidth || 0);
    return Number.isFinite(width) && width > 0 ? Math.max(720, width - 56) : null;
  }

  // What a chart or a table shows, so that a copied one still tells it: its area (for example City: London), then
  // its operators and vendors. Each is the value of its context (the City, Cluster or Region, the most specific
  // first), else the filters of the Saved Filter, else National, All Operators or All Vendors. A long list keeps its
  // first two names and counts the others; the tooltip lists them all.
  function resultScope(context = null) {
    const find = key => {
      for (const source of [context, resultScopeFilters]) {
        const value = source?.[key] ?? source?.[key.toLowerCase()];
        const values = (Array.isArray(value) ? value : [value]).map(item => String(item ?? '').trim()).filter(Boolean);
        if (values.length) return [...new Set(key === 'Vendor' ? values.map(scoringVendorName) : values)];
      }
      return [];
    };
    const pill = (values, level, plural) => {
      const name = values.length > 1 ? plural : level;
      const shown = values.length > 3 ? [...values.slice(0, 2), `${values.length - 2} more`] : values;
      const list = shown.length > 1 ? `${shown.slice(0, -1).join(', ')} & ${shown.at(-1)}` : shown[0];
      return {label: `${name}: ${list}`, title: `${name}: ${values.join(', ')}`};
    };
    let area = null;
    for (const [level, plural] of [['City', 'Cities'], ['Cluster', 'Clusters'], ['Region', 'Regions']]) {
      const values = find(level);
      if (values.length) {
        area = pill(values, level, plural);
        break;
      }
    }
    const operators = find('Operator');
    const vendors = find('Vendor');
    return [
      {kind: 'area', ...(area || {label: 'National', title: 'National: no City, Cluster or Region filter'})},
      {kind: 'operator', ...(operators.length ? pill(operators, 'Operator', 'Operators')
        : {label: 'All Operators', title: 'All Operators: no Operator filter'})},
      {kind: 'vendor', ...(vendors.length ? pill(vendors, 'Vendor', 'Vendors')
        : {label: 'All Vendors', title: 'All Vendors: no Vendor filter'})},
    ];
  }

  // Ends a chart or table title with the pills of its area, operators and vendors; the title alone is kept for its
  // larger view.
  function appendResultScope(heading, context = null) {
    const scope = resultScope(context);
    heading.dataset.title = heading.textContent.trim();
    for (const item of scope) {
      const pill = document.createElement('span');
      pill.className = `scoring-scope-pill is-${item.kind}`;
      pill.textContent = item.label;
      pill.title = item.title;
      heading.append(pill);
    }
    return scope;
  }

  // The larger view of a chart, map or table shows the pills of its title too.
  function appendExpandedScope(heading) {
    if (!heading || !expandedChartTitle || !chartOverlay || chartOverlay.hidden) return;
    for (const pill of heading.querySelectorAll(':scope > .scoring-scope-pill')) expandedChartTitle.append(pill.cloneNode(true));
  }

  function titleWithoutScope(heading) {
    return heading?.dataset.title || heading?.textContent?.trim() || '';
  }

  // ``context`` is the context of the chart's table, for its area, operators and vendors; false leaves them out (the
  // National & Geographical Areas card shows every area).
  function makeExpandableChartCard(title, meta, chart, context = null) {
    const card = document.createElement('article');
    card.className = 'scoring-chart-card';
    card.tabIndex = 0;
    card.setAttribute('role', 'button');
    const heading = document.createElement('h4');
    heading.textContent = title;
    const scope = context === false ? null : appendResultScope(heading, context);
    heading.title = scope ? [title, ...scope.map(item => item.title)].join(' — ') : title;
    const label = scope ? `${title} — ${scope.map(item => item.label).join(' · ')}` : title;
    card.setAttribute('aria-label', `${label}. Double-click or press Enter to enlarge.`);
    card.dataset.chartMeta = meta || '';
    const scroll = document.createElement('div');
    scroll.className = 'scoring-chart-scroll';
    scroll.append(chart);
    card.append(heading, scroll);
    // Charts zoom like the maps: a dragged rectangle or the floating buttons.
    const svg = chart?.matches?.('svg[viewBox]') ? chart : chart?.querySelector?.('svg.scoring-chart-svg');
    if (svg) enableMapZoom(card, svg);
    else enableContentZoom(card, scroll);
    card.addEventListener('dblclick', event => {
      if (event.target.closest('.scoring-map-zoom')) return;
      // The zoom captures the pointer, so the part under it (a National & Geographical Areas trend or table) is found by its
      // position: it enlarges alone.
      const part = document.elementsFromPoint(event.clientX, event.clientY)
        .map(element => element.closest?.('.scoring-expandable-part')).find(Boolean);
      if (part?.expandPart) part.expandPart();
      else openExpandedChart(card);
    });
    card.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        openExpandedChart(card);
      }
    });
    return card;
  }

  function renderCharts(pane, source, scoreTables) {
    pane.replaceChildren();
    const rows = scoreTables.length
      ? scoreChartRows(scoreTables).map(row => ({row, score: {value: row.weighted_points}}))
      : normalizeRows(source).map(row => ({row, score: scoreNumber(row)})).filter(entry => entry.score);
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No chart rows are available for this Saved Filter.';
      pane.append(empty);
      return;
    }
    const dimensionFields = ['campaign', 'region', 'cluster', 'city', 'vendor', 'dataset_type', 'environment'];
    const groups = new Map();
    for (const entry of rows) {
      const row = entry.row;
      const dimensions = dimensionFields.map(field => [field, rowText(row, [field])]).filter(([, value]) => value);
      const groupKey = JSON.stringify(dimensions);
      const rowContext = Object.fromEntries(dimensions);
      const operatorTable = chartTableForRow(row, scoreTables);
      const title = operatorTable?.title || (dimensions.length ? dimensions.map(([field, value]) => `${humanizeKey(field)}: ${value}`).join(' · ') : 'Overall scope');
      const category = rowText(row, ['category']) || 'Overall';
      const series = rowText(row, ['operator', 'operator_name', 'mno']) || 'Score';
      if (!groups.has(groupKey)) groups.set(groupKey, {title, context: operatorTable?.context || rowContext, rows: [], operatorTable});
      groups.get(groupKey).rows.push({category, series, value: entry.score.value, complete: row.complete !== false});
    }
    const selected = appendComparisonSelector(pane, [...groups.values()], 'score', 'chart');
    appendContextHeader(pane, selected, 'score', 'Scoring Charts');
    const categories = [...new Set(selected.rows.map(row => String(row.category)))];
    const operators = Array.isArray(selected.operatorTable?.operators)
      ? selected.operatorTable.operators.map(String)
      : [...new Set(selected.rows.map(row => String(row.series)))];
    const {colors: operatorColors, entries: operatorLegend} = chartOperatorLegend(selected.operatorTable, operators);
    const categoryLegendEntries = chartCategoryLegend(categories);
    const operatorLabels = Object.fromEntries(operators.map(operator => [
      operator, operatorPresentation(selected.operatorTable, operator).label,
    ]));
    const stackedRows = selected.rows.map(row => ({
      ...row,
      category: String(row.series),
      series: String(row.category),
    }));
    const categorySeriesStyles = Object.fromEntries(categories.map(category => [category, {label: category}]));
    const stackedChart = makeSvgChart(`${scoringLabel()} Scoring per Category`, stackedRows, selected.operatorTable, {
      stacked: true,
      categoryOrder: operators,
      categoryLabels: operatorLabels,
      categoryTooltips: operatorLabels,
      seriesOrder: categories,
      seriesStyles: categorySeriesStyles,
      legendEntries: operatorLegend,
      categoryLegendEntries,
      operatorForCategory: operator => operator,
      segmentColor: (operator, _category, categoryIndex) => hierarchyChartColor(
        operatorColors.get(operator) || '#365F91', categoryIndex, categories.length,
      ),
    });
    stackedChart.style.minWidth = '0';
    pane.append(makeExpandableChartCard(`${scoringLabel()} Scoring per Category`, contextLabel(selected.context, {environmentPrefix: false}), stackedChart, selected.context));
    const clusteredChart = makeSvgChart(`${scoringLabel()} Scoring per Category (Breakdown)`, selected.rows, selected.operatorTable, {
      legendEntries: operatorLegend,
      fitWidth: chartFitWidth(pane),
    });
    clusteredChart.style.minWidth = '0';
    clusteredChart.style.width = '100%';
    pane.append(makeExpandableChartCard(
      `${scoringLabel()} Scoring per Category (Breakdown)`, contextLabel(selected.context, {environmentPrefix: false}), clusteredChart,
      selected.context,
    ));
    pane.classList.add('scoring-chart-grid');
  }

  function renderHierarchyCharts(pane, tableData) {
    pane.replaceChildren();
    if (!tableData) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No hierarchical chart is available for this environment.';
      pane.append(empty);
      return;
    }
    const columns = hierarchyColumnEntries(tableData);
    const sourceRows = scoreChartRows([tableData]);
    const rows = sourceRows.map(row => ({
      category: String(row.operator),
      series: String(row.category),
      value: row.weighted_points,
      complete: row.complete,
    }));
    if (!rows.length || !columns.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No chart rows are available for this hierarchy.';
      pane.append(empty);
      return;
    }
    const categoryLabels = Object.fromEntries(columns.map(column => [
      column.id,
      hierarchyPathValueLabel(column) || operatorPresentation(column.styleSource, column.id).label,
    ]));
    const categoryTooltips = Object.fromEntries(columns.map(column => [
      column.id,
      hierarchyPathFullLabel(column) || operatorPresentation(column.styleSource, column.id).label,
    ]));
    const kpiCategories = [...new Set(sourceRows.map(row => String(row.category)))];
    const operatorLegend = [];
    const seenOperators = new Set();
    const operatorColors = new Map();
    for (const column of columns) {
      const style = firstValue(tableData?.operator_styles || {}, [column.id], {});
      const operator = String(column.operator || style.operator || operatorPresentation(column.styleSource, column.id).label);
      const presentation = operatorPresentation(column.styleSource, column.id);
      const color = operatorColors.get(operator) || presentation.color
        || ['#14867d', '#df7a45', '#5a82aa', '#8b63b1'][operatorColors.size % 4];
      operatorColors.set(operator, color);
      if (seenOperators.has(operator)) continue;
      seenOperators.add(operator);
      operatorLegend.push({
        label: `${operator}${style.is_reference === true || column.is_reference === true ? ' (Reference)' : ''}`,
        color,
        title: `${operator}${style.is_reference === true || column.is_reference === true ? ' is the reference operator.' : ''} Segment shades identify KPI categories; hover a segment for its category and score.`,
      });
    }
    const categoryLegend = kpiCategories.map((category, index) => ({
      label: category,
      color: categoryLegendGray(index, kpiCategories.length),
      title: `${category}. Grayscale key ${index + 1} identifies this KPI category across operator-specific segment shades.`,
    }));
    const seriesStyles = Object.fromEntries(kpiCategories.map(category => [category, {label: category}]));
    appendContextHeader(pane, tableData, 'score', 'Scoring Charts');
    const chartGroupKey = hierarchyChartGroupKey(columns, hierarchyLevelNames(tableData, columns));
    const chart = makeSvgChart(`${scoringLabel()} Scoring per Category`, rows, tableData, {
      stacked: true,
      categoryOrder: columns.map(column => column.id),
      categoryLabels,
      categoryTooltips,
      hierarchyLevels: tableData.hierarchy_levels,
      hierarchyColumns: columns,
      groupKeyForCategory: leafId => chartGroupKey(columns.find(column => column.id === leafId)),
      categoryGroupGap: 14,
      seriesOrder: kpiCategories,
      seriesStyles,
      legendEntries: operatorLegend,
      categoryLegendEntries: categoryLegend,
      operatorForCategory: leafId => hierarchyColumnOperator(columns.find(column => column.id === leafId)),
      segmentColor: (leafId, _category, categoryIndex) => {
        const column = columns.find(item => item.id === leafId);
        const operator = String(column?.operator || firstValue(tableData?.operator_styles || {}, [leafId], {}).operator || '');
        return hierarchyChartColor(operatorColors.get(operator) || '#365F91', categoryIndex, kpiCategories.length);
      },
      axisLabel: 'Weighted score points',
    });
    chart.style.minWidth = '0';
    pane.append(makeExpandableChartCard(
      `${scoringLabel()} Scoring per Category`, contextLabel(tableData.context, {environmentPrefix: false}), chart, tableData.context,
    ));
    const clusteredRows = sourceRows.map(row => ({
      category: String(row.category),
      series: String(row.operator),
      value: row.weighted_points,
      complete: row.complete,
    }));
    const clusteredSeriesStyles = {};
    const clusteredSeriesTooltips = {};
    const clusteredLegend = operatorLegend.map(entry => ({
      ...entry,
      title: `${entry.label} uses its mapped operator color; separate bars show hierarchy contexts.`,
    }));
    for (const column of columns) {
      const operator = hierarchyColumnOperator(column);
      const operatorLabel = operatorPresentation(tableData, operator).label;
      const isReference = hierarchyColumnIsReference(column);
      const pathLabel = hierarchyPathValueLabel(column) || operatorLabel;
      const pathTooltip = hierarchyPathFullLabel(column) || pathLabel;
      const color = operatorColors.get(operator) || '#365F91';
      clusteredSeriesStyles[column.id] = {label: pathLabel, color};
      clusteredSeriesTooltips[column.id] = `Operator: ${operatorLabel}${isReference ? ' (Reference)' : ''}\nHierarchy: ${pathTooltip}`;
    }
    const clusteredChart = makeSvgChart(`${scoringLabel()} Scoring per Category (Breakdown)`, clusteredRows, tableData, {
      categoryOrder: kpiCategories,
      seriesOrder: columns.map(column => column.id),
      seriesStyles: clusteredSeriesStyles,
      seriesTooltips: clusteredSeriesTooltips,
      legendEntries: clusteredLegend,
      hierarchyLevels: tableData.hierarchy_levels,
      hierarchyColumns: columns,
      fitWidth: chartFitWidth(pane),
    });
    // It takes the width of its card, never wider (see makeSvgChart).
    clusteredChart.style.minWidth = '0';
    clusteredChart.style.width = '100%';
    clusteredChart.style.maxWidth = 'none';
    pane.append(makeExpandableChartCard(
      `${scoringLabel()} Scoring per Category (Breakdown)`, contextLabel(tableData.context, {environmentPrefix: false}), clusteredChart,
      tableData.context,
    ));
    pane.classList.add('scoring-chart-grid');
  }

  function bestNetworkKind(item) {
    const sourceKind = String(firstValue(item, ['source_kind', 'sourceKind'], '')).toLowerCase();
    if (sourceKind === 'voice' || sourceKind === 'speech') return 'Voice';
    if (sourceKind === 'data') return 'Data';
    const category = String(item?.category || '').trim().toUpperCase().replace(/[^A-Z0-9]+/g, ' ');
    return ['CLASSIC CALLS', 'WHATSAPP CALLS', 'MULTI RAB'].includes(category) ? 'Voice' : 'Data';
  }

  function bestNetworkTotals(tableData) {
    const operators = Array.isArray(tableData?.operators) ? tableData.operators.map(String) : [];
    const rows = Array.isArray(tableData?.rows) ? tableData.rows : [];
    const kinds = ['Voice', 'Data'];
    const allocation = {Voice: 0, Data: 0};
    const totals = Object.fromEntries(operators.map(operator => [operator, Object.fromEntries(kinds.map(kind => [kind, {points: 0, hasPoints: false, complete: true, rows: 0}]))]));
    for (const item of rows) {
      const kind = bestNetworkKind(item);
      const maxPoints = Number(item?.max_points);
      if (Number.isFinite(maxPoints)) allocation[kind] += maxPoints;
      for (const operator of operators) {
        const target = totals[operator][kind];
        target.rows += 1;
        const cell = operatorValue(item?.values || {}, operator);
        const rawPoints = cell && typeof cell === 'object' ? firstValue(cell, ['points', 'weighted_points'], null) : null;
        const points = rawPoints === null || rawPoints === undefined || String(rawPoints).trim() === '' ? Number.NaN : Number(rawPoints);
        if (Number.isFinite(points)) {
          target.points += points;
          target.hasPoints = true;
        }
        if (!cell || cell.complete !== true || !Number.isFinite(points)) target.complete = false;
      }
    }
    for (const operator of operators) {
      for (const kind of kinds) {
        const target = totals[operator][kind];
        target.value = target.hasPoints ? target.points : null;
        target.complete = target.rows > 0 && target.complete;
      }
    }
    return {operators, rows, allocation, totals};
  }

  function svgElement(svg, name, attributes = {}) {
    const node = document.createElementNS(svg.namespaceURI, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    return node;
  }

  function lightenHexColor(color, amount = .58) {
    const safe = safeHexColor(color);
    if (!safe) return '#a9cfca';
    const channels = [1, 3, 5].map(offset => Number.parseInt(safe.slice(offset, offset + 2), 16));
    return `#${channels.map(channel => Math.round(channel + (255 - channel) * amount).toString(16).padStart(2, '0')).join('')}`;
  }

  function hierarchyChartColor(color, categoryIndex, categoryCount = 7) {
    const safe = safeHexColor(color) || '#365F91';
    const tint = .72 * Math.max(0, categoryIndex) / Math.max(1, categoryCount - 1);
    const channels = [1, 3, 5].map(offset => Number.parseInt(safe.slice(offset, offset + 2), 16));
    return `#${channels.map(channel => Math.round(channel + (255 - channel) * tint).toString(16).padStart(2, '0')).join('')}`;
  }

  function makeBestNetworkBars(tableData, data) {
    const hierarchyLevels = Array.isArray(tableData?.hierarchy_levels) ? tableData.hierarchy_levels.map(String) : [];
    const hierarchyColumns = Array.isArray(tableData?.hierarchy_columns) ? tableData.hierarchy_columns : [];
    const hierarchyColumnsById = new Map(hierarchyColumns.map(column => [String(column?.id ?? ''), column]));
    const hasHierarchyAxis = hierarchyLevels.length > 0 && hierarchyColumnsById.size > 0;
    const groupKey = hierarchyChartGroupKey(hierarchyColumns, hierarchyLevels);
    const groupKeys = data.operators.map(operator => groupKey(hierarchyColumnsById.get(operator)));
    const groupTransitions = hasHierarchyAxis
      ? groupKeys.slice(1).filter((key, index) => key && groupKeys[index] && key !== groupKeys[index]).length : 0;
    const categoryGroupGap = hasHierarchyAxis ? 14 : 0;
    const geometry = bestNetworkHorizontalGeometry(data.operators.length, groupTransitions, categoryGroupGap);
    const {width, left, right, step, barWidth, groupGap} = geometry;
    const fallbackColors = ['#14867d', '#df7a45', '#5a82aa', '#8b63b1'];
    const barColors = new Map(data.operators.map((operator, index) => {
      const mapped = operatorPresentation(tableData, operator);
      const hierarchyColumn = hierarchyColumnsById.get(operator);
      return [operator, {
        label: hierarchyColumn ? hierarchyPathValueLabel(hierarchyColumn) : mapped.label,
        fullLabel: hierarchyColumn ? hierarchyPathFullLabel(hierarchyColumn) : mapped.label,
        color: mapped.color || fallbackColors[index % fallbackColors.length],
      }];
    }));
    const legendByOperator = new Map();
    data.operators.forEach((operator, index) => {
      const column = hierarchyColumnsById.get(operator);
      const operatorName = hasHierarchyAxis ? hierarchyColumnOperator(column) : operator;
      if (!operatorName || legendByOperator.has(operatorName.toLocaleLowerCase())) return;
      const mapped = operatorPresentation(tableData, operatorName);
      const leafStyle = firstValue(tableData?.operator_styles || {}, [operator], {});
      const positionValue = mapped.position ?? Number(firstValue(leafStyle, ['position'], Number.NaN));
      const isReference = hierarchyColumnIsReference(column) || isReferenceOperator(tableData, operatorName);
      const label = `${mapped.label || barColors.get(operator)?.label || operatorName}${isReference ? ' (Reference)' : ''}`;
      legendByOperator.set(operatorName.toLocaleLowerCase(), {
        label,
        color: mapped.color || barColors.get(operator)?.color || fallbackColors[index % fallbackColors.length],
        title: `${hasHierarchyAxis ? `Operator: ${operatorName}` : `Operator: ${mapped.label || operatorName}`}${isReference ? ' (Reference)' : ''}. Data uses the mapped color; Voice uses a lighter tint.`,
        position: Number.isFinite(positionValue) ? positionValue : Number.POSITIVE_INFINITY,
        sourceIndex: index,
      });
    });
    const operatorLegendEntries = [...legendByOperator.values()].sort((leftEntry, rightEntry) => (
      leftEntry.position - rightEntry.position || leftEntry.sourceIndex - rightEntry.sourceIndex
    ));
    const operatorLegendRows = chartLegendRows(operatorLegendEntries, width, left, right, fallbackColors[0]);
    const baseHeight = 620;
    const top = Math.max(72, 45 + operatorLegendRows.length * 20);
    const chartHeight = baseHeight + Math.max(0, top - 72);
    const height = chartHeight + 76;
    const categoryStarts = new Map();
    let categoryCursor = left;
    data.operators.forEach((operator, index) => {
      if (index && groupKeys[index] && groupKeys[index - 1] && groupKeys[index] !== groupKeys[index - 1]) categoryCursor += groupGap;
      categoryStarts.set(operator, categoryCursor);
      categoryCursor += step;
    });
    // The rows of the hierarchy axis take the room their labels need (turned 90° when they do not fit across).
    const bottom = Math.max(124, 32 + (hasHierarchyAxis
      ? hierarchyAxisRows(data.operators, hierarchyLevels, hierarchyColumnsById, categoryStarts, step, left).height : 0));
    const plotHeight = baseHeight - 72 - bottom;
    const maxAllocation = data.allocation.Voice + data.allocation.Data;
    const maxActual = Math.max(0, ...data.operators.map(operator => ['Voice', 'Data'].reduce((sum, kind) => sum + (data.totals[operator][kind].value ?? 0), 0)));
    const scale = scoringChartScale(maxAllocation, maxActual);
    const scaleMaximum = scale.maximum;
    const axisTop = top + 36;
    const axisHeight = plotHeight - 36;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('class', 'scoring-chart-svg scoring-best-network-bars');
    fitBestNetworkChartWidth(svg);
    svg.style.maxWidth = 'none';
    svg.style.minHeight = '0';
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${scoringLabel()} Scoring per Service`);
    if (operatorLegendRows.length) {
      operatorLegendRows.forEach((row, rowIndex) => {
        let x = left + Math.max(0, (width - left - right - (row.width - 22)) / 2);
        for (const entry of row.entries) {
          const y = 23 + rowIndex * 20;
          const swatch = svgElement(svg, 'rect', {x, y, width: 14, height: 14, rx: 3, fill: entry.color});
          const label = svgElement(svg, 'text', {x: x + 21, y: y + 12, class: 'scoring-chart-legend'});
          label.textContent = entry.label;
          setChartTooltip(swatch, String(entry.title || entry.label), true);
          setChartTooltip(label, String(entry.title || entry.label), true);
          svg.append(swatch, label);
          x += entry.entryWidth;
        }
      });
    }
    const baselineY = axisTop + axisHeight;
    for (let tickIndex = 0; tickIndex <= scale.intervals; tickIndex += 1) {
      const value = scaleMaximum * (scale.intervals - tickIndex) / scale.intervals;
      const y = axisTop + axisHeight * tickIndex / scale.intervals;
      svg.append(svgElement(svg, 'line', {x1: left, x2: width - right, y1: y, y2: y, stroke: tickIndex === scale.intervals ? '#aeb9bd' : '#e1e7e8', ...(tickIndex === scale.intervals ? {} : {'stroke-dasharray': '4 5'})}));
      const tick = svgElement(svg, 'text', {x: left - 12, y: y + 4, 'text-anchor': 'end', class: 'scoring-chart-tick'});
      tick.textContent = formatChartNumber(Math.round(value), {maximumFractionDigits: 0});
      svg.append(tick);
    }
    const axis = svgElement(svg, 'text', {x: 22, y: axisTop + axisHeight / 2, 'text-anchor': 'middle', class: 'scoring-chart-axis-label', transform: `rotate(-90 22 ${axisTop + axisHeight / 2})`});
    axis.textContent = 'Weighted score (points)';
    svg.append(axis);
    if (hasHierarchyAxis) {
      appendHierarchyAxisBands(svg, data.operators, hierarchyLevels, hierarchyColumnsById, categoryStarts, step, baselineY, left, width - right);
    }
    data.operators.forEach((operator, index) => {
      const presentation = barColors.get(operator);
      const x = (categoryStarts.get(operator) ?? left + step * index) + (step - barWidth) / 2;
      let stackY = baselineY;
      let totalPoints = 0;
      let hasPoints = false;
      let complete = true;
      for (const kind of ['Data', 'Voice']) {
        const cell = data.totals[operator][kind];
        if (cell.value === null) {
          complete = false;
          continue;
        }
        hasPoints = true;
        totalPoints += cell.value;
        complete = complete && cell.complete;
        const segmentHeight = Math.max(0, cell.value / scaleMaximum * axisHeight);
        const segmentY = stackY - segmentHeight;
        const color = kind === 'Data' ? presentation.color : lightenHexColor(presentation.color);
        const rect = svgElement(svg, 'rect', {x, y: segmentY, width: barWidth, height: segmentHeight, ...(hasHierarchyAxis ? {} : {rx: 3}), fill: color});
        const hierarchyText = hasHierarchyAxis ? `Hierarchy: ${presentation.fullLabel}` : `Operator: ${presentation.fullLabel}`;
        const segmentTooltip = [
          hierarchyText,
          `Series: ${kind}`,
          chartEnvironmentName(tableData) ? `Environment: ${chartEnvironmentName(tableData)}` : '',
          `Weighted points: ${formattedChartPoints(cell.value)}`,
          cell.complete ? 'Coverage: complete' : 'Coverage: incomplete',
        ].filter(Boolean).join('\n');
        setChartTooltip(rect, segmentTooltip, true);
        svg.append(rect);
        const segmentText = `${formatChartNumber(cell.value, {minimumFractionDigits: 1, maximumFractionDigits: 1})}${cell.complete ? '' : '*'}`;
        const layout = stackedSegmentLabelLayout(segmentText, barWidth, segmentHeight, barSegmentLabelMaximum(geometry.step));
        if (layout.size) {
          const segmentLabel = svgElement(svg, 'text', {class: 'scoring-best-network-segment'});
          placeSegmentLabel(segmentLabel, x + barWidth / 2, segmentY + segmentHeight / 2, layout);
          segmentLabel.textContent = segmentText;
          segmentLabel.style.fill = categoryLegendTextColor(color);
          styleIncompleteValue(segmentLabel);
          setChartTooltip(segmentLabel, segmentTooltip);
          svg.append(segmentLabel);
        }
        stackY = segmentY;
      }
      const totalLabel = svgElement(svg, 'text', {'text-anchor': 'middle', class: 'scoring-chart-value scoring-best-network-total'});
      totalLabel.textContent = hasPoints ? `${formatChartNumber(totalPoints, {minimumFractionDigits: 1, maximumFractionDigits: 1})}${complete ? '' : '*'}` : 'N/A';
      placeBarTotal(totalLabel, x + barWidth / 2, stackY, geometry.step, 12);
      styleIncompleteValue(totalLabel);
      setChartTooltip(totalLabel, [
        hasHierarchyAxis ? `Hierarchy: ${presentation.fullLabel}` : `Operator: ${presentation.fullLabel}`,
        'Voice and Data total',
        chartEnvironmentName(tableData) ? `Environment: ${chartEnvironmentName(tableData)}` : '',
        `Weighted points: ${hasPoints ? formattedChartPoints(totalPoints) : 'unavailable'}`,
        complete ? 'Coverage: complete' : 'Coverage: incomplete; displayed points are not renormalized',
      ].filter(Boolean).join('\n'), true);
      svg.append(totalLabel);
      if (!hasHierarchyAxis) {
        const operatorLabel = svgElement(svg, 'text', {x: x + barWidth / 2, y: baselineY + 28, 'text-anchor': 'middle', class: 'scoring-chart-category'});
        const labelLines = wrappedSvgLabelLines(presentation.label, 24, 1);
        labelLines.forEach((line, lineIndex) => {
          const span = svgElement(svg, 'tspan', {x: x + barWidth / 2, dy: lineIndex ? '1.15em' : '0'});
          span.textContent = line;
          operatorLabel.append(span);
        });
        setChartTooltip(operatorLabel, [
          `Operator: ${presentation.fullLabel}`,
          chartEnvironmentName(tableData) ? `Environment: ${chartEnvironmentName(tableData)}` : '',
        ].filter(Boolean).join('\n'));
        svg.append(operatorLabel);
      }
    });
    svg.append(svgElement(svg, 'line', {x1: left, x2: width - right, y1: chartHeight + 3, y2: chartHeight + 3, stroke: '#d6dddf', 'stroke-width': 1}));
    const serviceLegendTitle = svgElement(svg, 'text', {x: left, y: chartHeight + 17, class: 'scoring-chart-category-legend-title'});
    serviceLegendTitle.textContent = 'Service types';
    svg.append(serviceLegendTitle);
    const bandWidth = width - left - right;
    for (const [index, label, color] of [[0, 'Data', '#555555'], [1, 'Voice', '#c5c5c5']]) {
      const segmentWidth = bandWidth / 2;
      const segment = svgElement(svg, 'rect', {x: left + index * segmentWidth, y: chartHeight + 25, width: segmentWidth, height: 40, fill: color, stroke: '#ffffff', 'stroke-width': 1});
      const text = svgElement(svg, 'text', {x: left + (index + .5) * segmentWidth, y: chartHeight + 50, 'text-anchor': 'middle', class: 'scoring-chart-category-legend-label'});
      text.textContent = label;
      text.style.fill = categoryLegendTextColor(color);
      svg.append(segment, text);
    }
    return svg;
  }

  function maximumAllocationEnvironments(tableData, allTables, configuration = {}) {
    const requested = String(tableData?.context?.environment || 'Combined');
    const combined = ['combined', 'all', 'all environments'].includes(requested.toLowerCase());
    const environments = new Map();
    const configured = configuration?.scope?.environments || {};
    for (const [name, details] of Object.entries(configured)) {
      if (!(Number(details?.total_points) > 0)) continue;
      const allocation = {Voice: 0, Data: 0};
      for (const metric of configuration.metrics || []) {
        const points = Number(metric?.contexts?.[name]?.max_points);
        if (!Number.isFinite(points) || points <= 0) continue;
        const kind = String(metric.source_kind || metric.calculation?.source_kind || '').toLowerCase();
        if (['voice', 'speech'].includes(kind)) allocation.Voice += points;
        else if (kind === 'data') allocation.Data += points;
      }
      environments.set(name, {name, ...allocation});
    }
    if (!environments.size) {
      for (const table of allTables || []) {
        const name = String(table?.context?.environment || '');
        if (!name || ['combined', 'all', 'all environments'].includes(name.toLowerCase()) || environments.has(name)) continue;
        environments.set(name, {name, ...bestNetworkTotals(table).allocation});
      }
    }
    const palette = activeTheme.environments || ['#176E77', '#E6A81D', '#C55A11', '#5B9BD5', '#A64D79'];
    const allocations = [...environments.values()].map((item, index) => ({...item, color: palette[index % palette.length]}))
      .filter(item => combined || item.name.toLowerCase() === requested.toLowerCase());
    if (!allocations.length) return [{name: requested, ...bestNetworkTotals(tableData).allocation, color: palette[0]}];
    // Environments without results in any series give their points to the others,
    // in proportion, as the Combined scores do; the configured points stay visible.
    const results = typeof currentResults === 'undefined' ? null : activeScoringPayload(currentResults);
    const scaled = new Set(combined ? results?.environment_scaling?.scaled_environments || [] : []);
    const total = allocations.reduce((sum, item) => sum + item.Voice + item.Data, 0);
    const kept = allocations.filter(item => !scaled.has(item.name)).reduce((sum, item) => sum + item.Voice + item.Data, 0);
    if (!scaled.size || !(kept > 0)) return allocations;
    return allocations.map(item => {
      const factor = scaled.has(item.name) ? 0 : total / kept;
      return {...item, factor, original: {Voice: item.Voice, Data: item.Data}, Voice: item.Voice * factor, Data: item.Data * factor};
    });
  }

  function maximumAllocationCategories(tableData, environments, configuration = {}) {
    const totals = new Map();
    const originals = new Map();
    for (const metric of configuration.metrics || []) {
      const category = String(metric.category || 'Other');
      let original = 0;
      const points = environments.reduce((sum, environment) => {
        const value = Number(metric?.contexts?.[environment.name]?.max_points);
        const configured = Number.isFinite(value) && value > 0 ? value : 0;
        original += configured;
        return sum + configured * (environment.factor ?? 1);
      }, 0);
      if (original > 0) {
        totals.set(category, (totals.get(category) || 0) + points);
        originals.set(category, (originals.get(category) || 0) + original);
      }
    }
    if (!totals.size) {
      for (const row of tableData?.rows || []) {
        if (row.row_type === 'category') continue;
        const points = Number(row.max_points);
        const category = String(row.category || 'Other');
        if (Number.isFinite(points) && points > 0) totals.set(category, (totals.get(category) || 0) + points);
      }
    }
    const palette = activeTheme.categories || ['#4472C4', '#7030A0', '#C55A11', '#5B9BD5', '#A64D79', '#548235', '#D65F8D', '#8064A2'];
    return [...totals].map(([label, value], index) => ({label, value, original: originals.get(label), color: palette[index % palette.length]}));
  }

  function allocationIconPath(kind) {
    if (/whatsapp/i.test(kind)) return 'M3 4h18v13H9l-6 4ZM8 7h3l1 3-2 1 3 3 1-2 3 1v3c-4 1-10-5-9-9Z';
    if (/classic|calls/i.test(kind)) return 'M6 3h4l2 5-3 2c2 4 3 5 7 7l2-3 5 2v4c-1 3-5 2-8 0C7 16 2 7 6 3Z';
    if (/multi.*rab/i.test(kind)) return 'M12 3v18M5 21l7-18 7 18M4 7a11 11 0 0 1 16 0M7 10a7 7 0 0 1 10 0';
    if (/transfer/i.test(kind)) return 'M7 3v17m-4-4 4 4 4-4M17 21V4m-4 4 4-4 4 4';
    if (/brows/i.test(kind)) return 'M2 4h20v16H2ZM2 8h20M5 6h1m2 0h1m2 0h1M8 12l-3 2 3 2m8-4 3 2-3 2';
    if (/video/i.test(kind)) return 'M3 4h18v16H3ZM9 8l7 4-7 4Z';
    if (/interactivity/i.test(kind)) return 'M2 12h4l3-8 5 16 3-8h5';
    if (kind === 'Category') return 'M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3ZM14 14h7v7h-7Z';
    if (kind === 'Voice') return 'M6 3h4l2 5-3 2c2 4 3 5 7 7l2-3 5 2v4c-1 3-5 2-8 0C7 16 2 7 6 3Z';
    if (kind === 'Data') return 'M7 3h10v18H7ZM10 7h10m-3-3 3 3-3 3M14 16H4m3-3-3 3 3 3';
    if (/city/i.test(kind)) return 'M3 21V7h7v14M10 21V3h10v18M1 21h22M6 10v2m0 3v2m8-10h3m-3 4h3m-3 4h3';
    if (/road/i.test(kind)) return 'M5 21 9 3m10 18L15 3M12 3v3m0 3v3m0 3v3m0 2v1';
    return 'M12 22s8-8 8-13a8 8 0 0 0-16 0c0 5 8 13 8 13ZM12 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z';
  }

  function allocationEnvironmentLabel(name) {
    const savedLabel = typeof currentResults === 'undefined' ? null
      : currentResults?.configuration?.scope?.environments?.[name]?.display_name;
    if (savedLabel) return String(savedLabel);
    const normalized = String(name).replace(/[\s_-]/g, '').toLowerCase();
    if (normalized === 'drivecity') return 'Drive - City';
    if (['driveroad', 'driveconnectionroad', 'driveconnectingroads'].includes(normalized)) return 'Drive - Connecting Roads';
    return String(name);
  }

  function allocationCategoryLabel(name) {
    return String(name).toLowerCase().replace(/\b[a-z]/g, letter => letter.toUpperCase());
  }

  function allocationSectorPath(cx, cy, outerRadius, innerRadius, startAngle, endAngle) {
    const point = (radius, angle) => [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
    const span = endAngle - startAngle;
    const [ox, oy] = point(outerRadius, startAngle);
    const [ix, iy] = point(innerRadius, startAngle);
    if (span >= Math.PI * 2 - .000001) {
      const [omx, omy] = point(outerRadius, startAngle + Math.PI);
      const [imx, imy] = point(innerRadius, startAngle + Math.PI);
      return `M ${ox} ${oy} A ${outerRadius} ${outerRadius} 0 1 1 ${omx} ${omy} A ${outerRadius} ${outerRadius} 0 1 1 ${ox} ${oy} L ${ix} ${iy} A ${innerRadius} ${innerRadius} 0 1 0 ${imx} ${imy} A ${innerRadius} ${innerRadius} 0 1 0 ${ix} ${iy} Z`;
    }
    const [ex, ey] = point(outerRadius, endAngle);
    const [iex, iey] = point(innerRadius, endAngle);
    const largeArc = span > Math.PI ? 1 : 0;
    return `M ${ox} ${oy} A ${outerRadius} ${outerRadius} 0 ${largeArc} 1 ${ex} ${ey} L ${iex} ${iey} A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${ix} ${iy} Z`;
  }

  function makeMaximumAllocationDonut(environments, categories = null) {
    // Voice and Data take the first two colours of the categories of the theme.
    const voiceColor = activeTheme.categories?.[0] || '#4472C4';
    const dataColor = activeTheme.categories?.[1] || '#7030A0';
    const combined = environments.length > 1;
    const total = environments.reduce((sum, item) => sum + item.Voice + item.Data, 0);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const voiceTotal = environments.reduce((sum, item) => sum + item.Voice, 0);
    const dataTotal = environments.reduce((sum, item) => sum + item.Data, 0);
    const legendItems = [];
    const addLegend = (label, color, value, iconKind, global = false, original = value) => {
      const percentage = total > 0 ? value / total * 100 : 0;
      const amount = `${formattedChartPoints(value)} pts (${percentage.toFixed(1)}%)`;
      // Points moved by scaling show the configured points struck through before them.
      const struck = Number.isFinite(original) && Math.abs(original - value) > .005 ? `${formattedChartPoints(original)} pts` : '';
      const text = `${label}: ${struck ? `${struck} ` : ''}${amount}`;
      legendItems.push({color, iconKind, global, label, amount, struck, lines: [text],
        fontSize: Math.min(14, 304 / Math.max(1, text.length * .55))});
    };
    const originalOf = (item, key) => (item.original ? item.original[key] : item[key]);
    if (combined) addLegend('Total Points', '#465565', total, 'Global', true);
    legendItems.push({heading: 'Points per Environment:'});
    environments.forEach(item => addLegend(allocationEnvironmentLabel(item.name), item.color, item.Voice + item.Data, item.name,
      false, originalOf(item, 'Voice') + originalOf(item, 'Data')));
    legendItems.push({heading: categories ? 'Points per KPI Category:' : 'Points per Service:'});
    if (categories) categories.forEach(item => addLegend(allocationCategoryLabel(item.label), item.color, item.value, item.label, false, item.original ?? item.value));
    else {
      addLegend('Voice', voiceColor, voiceTotal, 'Voice', false, environments.reduce((sum, item) => sum + originalOf(item, 'Voice'), 0));
      addLegend('Data', dataColor, dataTotal, 'Data', false, environments.reduce((sum, item) => sum + originalOf(item, 'Data'), 0));
    }
    const height = 480 + legendItems.reduce((sum, item) => sum + (item.heading ? 30 : item.lines.length * 22 + 8), 0) + 18;
    svg.setAttribute('viewBox', `0 0 460 ${height}`);
    svg.setAttribute('class', 'scoring-chart-svg scoring-allocation-donut');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', categories ? 'Maximum score by environment and category'
      : 'Maximum score by environment, Voice and Data');
    const cx = 230;
    const cy = 230;
    const outerRadius = 156;
    const outerHoleRadius = outerRadius * .72;
    const ringGap = 2;
    const innerOuterRadius = outerHoleRadius - ringGap;
    const innerHoleRadius = innerOuterRadius - outerHoleRadius * (1 - .63);
    const ringBounds = [
      {outer: outerRadius, inner: outerHoleRadius},
      {outer: innerOuterRadius, inner: innerHoleRadius},
    ];
    const familyRing = {name: categories ? 'KPI categories' : combined ? 'Global Voice/Data' : environments[0].name, segments: categories || [
      {label: 'Voice', value: voiceTotal, color: voiceColor},
      {label: 'Data', value: dataTotal, color: dataColor},
    ]};
    const rings = [{name: 'Environments', segments: environments.map(item => ({
      label: item.name, value: item.Voice + item.Data, color: item.color,
    }))}, familyRing];
    rings.forEach((ring, index) => {
      const {outer, inner} = ringBounds[index];
      const radius = (outer + inner) / 2;
      const ringTotal = ring.segments.reduce((sum, segment) => sum + segment.value, 0);
      let angle = -Math.PI / 2;
      ring.segments.forEach(segment => {
        const span = ringTotal > 0 ? Math.PI * 2 * segment.value / ringTotal : 0;
        if (span <= 0) return;
        const mark = svgElement(svg, 'path', {
          d: allocationSectorPath(cx, cy, outer, inner, angle, angle + span),
          fill: segment.color, stroke: 'none', 'data-allocation-segment': ring.name,
          'data-allocation-radius': radius, 'data-allocation-center': `${cx},${cy}`,
        });
        setChartTooltip(mark, `${ring.name}: ${segment.label}\nMaximum points: ${formattedChartPoints(segment.value)}\nShare of configured maximum: ${(ringTotal > 0 ? segment.value / ringTotal * 100 : 0).toFixed(1)}%`, true);
        svg.append(mark);
        if (index === 0) {
          const middle = angle + span / 2;
          const iconSize = 42;
          const iconRadius = outerRadius + 12 + iconSize / 2;
          const iconX = cx + iconRadius * Math.cos(middle);
          const iconY = cy + iconRadius * Math.sin(middle);
          const icon = svgElement(svg, 'path', {
            d: allocationIconPath(segment.label), fill: 'none', stroke: segment.color,
            'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
            transform: `translate(${iconX - iconSize / 2} ${iconY - iconSize / 2}) scale(${iconSize / 24})`,
            'data-allocation-environment-icon': segment.label,
          });
          setChartTooltip(icon, `Environment: ${allocationEnvironmentLabel(segment.label)}\nMaximum points: ${formattedChartPoints(segment.value)}`, true);
          svg.append(icon);
        }
        const percentage = segment.value / ringTotal * 100;
        const percentageLabel = `${percentage.toFixed(1)}%`;
        const middle = angle + span / 2;
        const centerX = radius * Math.cos(middle);
        const centerY = radius * Math.sin(middle);
        const fontSize = [14, 13, 12, 11].find((size) => {
          const halfWidth = percentageLabel.length * size * .65 / 2;
          const halfHeight = size * .6;
          const nearestRadius = Math.hypot(Math.max(Math.abs(centerX) - halfWidth, 0),
            Math.max(Math.abs(centerY) - halfHeight, 0));
          return nearestRadius >= inner + 2
            && [-halfWidth, halfWidth].every((dx) => [-halfHeight, halfHeight].every((dy) => {
            const cornerX = centerX + dx;
            const cornerY = centerY + dy;
            const cornerRadius = Math.hypot(cornerX, cornerY);
            const angleOffset = Math.atan2(Math.sin(Math.atan2(cornerY, cornerX) - middle),
              Math.cos(Math.atan2(cornerY, cornerX) - middle));
            return cornerRadius >= inner + 2 && cornerRadius <= outer - 2
              && Math.abs(angleOffset) <= span / 2 - 2 / radius;
          }));
        });
        if (fontSize) {
          const label = svgElement(svg, 'text', {
            x: cx + radius * Math.cos(middle), y: cy + radius * Math.sin(middle),
            'text-anchor': 'middle', 'dominant-baseline': 'central',
            style: `font-size:${fontSize}px;font-weight:700;fill:${readableTextColor(segment.color)}`,
            'data-allocation-percentage': percentageLabel,
          });
          label.textContent = percentageLabel;
          setChartTooltip(label, `${ring.name}: ${segment.label}\n${percentageLabel} of configured maximum`);
          svg.append(label);
        }
        angle += span;
      });
    });
    const center = svgElement(svg, 'text', {x: cx, y: cy - 4, 'text-anchor': 'middle', class: 'scoring-allocation-total'});
    center.textContent = formatChartNumber(total, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    const innerRadius = innerHoleRadius;
    center.setAttribute('style', `font-size:${Math.min(31, (innerRadius * 2 - 12) / (center.textContent.length * .65))}px`);
    const unit = svgElement(svg, 'text', {x: cx, y: cy + 20, 'text-anchor': 'middle', class: 'scoring-allocation-unit'});
    unit.textContent = 'max points';
    setChartTooltip(center, `Total configured maximum\nMaximum points: ${formattedChartPoints(total)}`);
    svg.append(center, unit);
    let legendY = 480;
    legendItems.forEach(item => {
      if (item.heading) {
        const heading = svgElement(svg, 'text', {x: 18, y: legendY, style: 'font-size:14px;font-weight:700'});
        heading.textContent = item.heading;
        svg.append(heading);
        legendY += 30;
        return;
      }
      const indent = item.global ? 0 : 20;
      const icon = svgElement(svg, 'path', {d: allocationIconPath(item.iconKind), fill: 'none', stroke: item.color,
        'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
        transform: `translate(${18 + indent} ${legendY - 18}) scale(.85)`});
      const swatch = svgElement(svg, 'rect', {x: 48 + indent, y: legendY - 13, width: 14, height: 14, rx: 2, fill: item.color});
      const text = svgElement(svg, 'text', {x: 74 + indent, y: legendY,
        style: `font-size:${item.fontSize}px;font-weight:${item.global ? 700 : 400}`});
      const label = svgElement(svg, 'tspan');
      label.textContent = `${item.label}: `;
      const amount = svgElement(svg, 'tspan', {dx: 3, fill: '#8A3D0A', style: 'fill:#8A3D0A'});
      amount.textContent = item.amount;
      text.append(label);
      if (item.struck) {
        const struck = svgElement(svg, 'tspan', {dx: 3, fill: '#7A8691', 'text-decoration': 'line-through', style: 'fill:#7A8691;text-decoration:line-through'});
        struck.textContent = item.struck;
        text.append(struck);
      }
      text.append(amount);
      setChartTooltip(text, item.lines.join(' '));
      svg.append(icon, swatch, text);
      legendY += item.lines.length * 22 + 8;
    });
    return svg;
  }

  function renderCategoryAllocation(pane, scoreTables, hierarchyTable, allTables) {
    const card = pane.querySelector(':scope > .scoring-chart-card');
    const selected = hierarchyTable
      || scoreTables.find(table => comparisonIdentity(table, 'score') === contextSelections.get('score'))
      || scoreTables[0];
    if (!card || !selected) return;
    const configuration = activeScoringConfiguration();
    const allocations = maximumAllocationEnvironments(selected, allTables, configuration);
    const categories = maximumAllocationCategories(selected, allocations, configuration);
    if (!categories.length) return;
    const layout = document.createElement('div');
    layout.className = 'scoring-best-network-layout';
    pane.insertBefore(layout, card);
    layout.append(card, makeExpandableChartCard('Maximum score per environment & category',
      contextLabel(selected.context, {environmentPrefix: false}), makeMaximumAllocationDonut(allocations, categories),
      selected.context));
  }

  function renderBestNetworkChart(pane, scoreTables, hierarchyTable = null, allTables = scoreTables) {
    if (!hierarchyTable && !scoreTables.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = `No ${scoringLabel()} chart is available for this environment.`;
      pane.append(empty);
      return;
    }
    const selected = hierarchyTable
      || scoreTables.find(table => comparisonIdentity(table, 'score') === contextSelections.get('score'))
      || scoreTables[0];
    const data = bestNetworkTotals(selected);
    if (!data.operators.length || !data.rows.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No operator points are available for this comparison context.';
      pane.append(empty);
      return;
    }
    const layout = document.createElement('div');
    layout.className = 'scoring-best-network-layout';
    const meta = contextLabel(selected.context, {environmentPrefix: false});
    const bars = makeBestNetworkBars(selected, data);
    layout.append(makeExpandableChartCard(`${scoringLabel()} Scoring per Service`, meta, bars, selected.context));
    const configuration = activeScoringConfiguration();
    const allocations = maximumAllocationEnvironments(selected, allTables, configuration);
    const donut = makeMaximumAllocationDonut(allocations);
    layout.append(makeExpandableChartCard('Maximum score per environment & service', meta, donut, selected.context));
    pane.insertBefore(layout, pane.querySelector(':scope > .scoring-best-network-layout, :scope > .scoring-chart-card'));
  }

  function openExpandedChart(card) {
    if (!card) return;
    // The chart itself, or the whole content of cards made of several parts (such as the location cards).
    const source = card.querySelector('.scoring-chart-svg')
      || card.querySelector('.scoring-chart-scroll')?.firstElementChild;
    const heading = card.querySelector('h4');
    openExpandedView(source, titleWithoutScope(heading) || 'Scoring chart',
      card.dataset.chartMeta || (selectedEnvironment ? environmentLabel(selectedEnvironment) : ''), card);
    appendExpandedScope(heading);
  }

  // A larger view of one chart, map or table, taking the whole screen but 5% on each side.
  // Charts and maps zoom there too.
  function openExpandedView(source, title, meta, focusReturn, kind = 'Scoring chart') {
    if (!source || !chartOverlay || !expandedChart) return;
    chartFocusReturn = focusReturn || null;
    const kindLabel = chartOverlay.querySelector('[data-scoring-chart-kind]');
    if (kindLabel) kindLabel.textContent = kind;
    expandedChartTitle.textContent = title;
    expandedChartMeta.textContent = meta || '';
    const copy = source.cloneNode(true);
    copy.querySelectorAll?.('.scoring-map-zoom, .scoring-map-zoom-rect').forEach(node => node.remove());
    if (copy.style) copy.style.minWidth = '0';
    if (copy.matches?.('svg')) {
      // A chart takes the whole view, however wide it is on the page (or however it is zoomed there).
      narrowChart(copy, 1);
      Object.assign(copy.style, {width: '', height: ''});
      delete copy.dataset.zoomFitted;
    }
    const isTable = copy.matches?.('table, .scoring-insight-table-wrap, .table-wrap') || false;
    expandedChart.classList.toggle('is-table', isTable);
    // A new holder each time, so the zoom of an earlier view does not stay attached.
    const holder = document.createElement('div');
    holder.className = 'scoring-expanded-holder';
    holder.append(copy);
    expandedChart.replaceChildren(holder);
    if (copy.matches?.('svg')) enableMapZoom(holder, copy);
    else if (!isTable) enableContentZoom(holder, holder);
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    chartOverlay.hidden = false;
    expandedChartClose?.focus();
  }

  function closeExpandedChart() {
    if (!chartOverlay || chartOverlay.hidden) return;
    chartOverlay.hidden = true;
    expandedChart.replaceChildren();
    document.body.style.overflow = previousBodyOverflow;
    if (chartFocusReturn?.isConnected) chartFocusReturn.focus();
    chartFocusReturn = null;
  }

  // Insights of the selected scoring (where each operator stands, location cards and rankings, scoring trends, KPI GAP
  // profiles, campaign comparisons and Points Lost), as in the PowerPoint and Word exports. Losses and GAPs behind the
  // reference are red and gains green; Voice points are amber and Data points teal.
  let insightVoiceColor = activeTheme.voice || '#F2A900';
  let insightDataColor = activeTheme.data || '#0E6B66';
  let insightLossColor = activeTheme.loss || '#e8414f';
  let insightGainColor = activeTheme.gain || '#4ca65a';
  const insightFallbackColors = ['#E60000', '#0B6E8F', '#7A3DB8', '#00A3AD', '#F2A900', '#4CA65A', '#8C564B', '#5B6770'];
  // The position of an operator: green for the first, light green for the second, light red in between, red for the last.
  let insightRankColors = activeTheme.ranks || ['#2f8a3e', '#7cbf73', '#f0868e', '#e8414f'];

  // The position of each operator in the Operator Maps (as the operator columns of the Scoring tables carry it).
  const mappedOperatorPositions = new WeakMap();
  function mappedOperatorPosition(payload) {
    if (!payload || typeof payload !== 'object') return () => 0;
    if (!mappedOperatorPositions.has(payload)) {
      const positions = new Map();
      for (const table of payload.views?.score_tables || []) {
        (table?.operators || []).forEach((operator, index) => {
          const position = Number(table.operator_styles?.[operator]?.position ?? index);
          const name = String(operator);
          if (!positions.has(name) || position < positions.get(name)) positions.set(name, position);
        });
      }
      mappedOperatorPositions.set(payload, positions);
    }
    const positions = mappedOperatorPositions.get(payload);
    return operator => positions.get(String(operator ?? '')) ?? Number.MAX_SAFE_INTEGER;
  }

  // The insights of a kind for the environment, their operators in the order of the Operator Maps, so every operator
  // selector and list of the results follows it.
  function insightItems(payload, kind, environment) {
    const items = payload?.views?.insights?.[kind];
    const position = mappedOperatorPosition(payload);
    return (Array.isArray(items) ? items : []).filter(item => item?.environment === environment)
      .sort((left, right) => position(left?.operator) - position(right?.operator));
  }

  function insightNumber(value, digits = 0) {
    return Number.isFinite(Number(value)) && value !== null
      ? Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : 'N/A';
  }

  // Chronological order; in a quarter, the plain campaign first, then NSA, then SA.
  function insightCampaignKey(value) {
    if (typeof globalThis.campaignSortKey === 'function') {
      const [year, quarter, rank, exception] = globalThis.campaignSortKey(value);
      return year < 0 ? exception - 1e6 : year * 100000 + quarter * 10000 + rank * 100 + exception;
    }
    const match = hierarchyDisplayValue({level: 'Campaign', value}).match(/^((?:19|20)\d{2})-Q([1-4])(?:-(NSA|SA))?$/);
    return match ? Number(match[1]) * 100 + Number(match[2]) * 10 + ({NSA: 1, SA: 2}[match[3]] || 0) : Number.NEGATIVE_INFINITY;
  }

  function insightContextLabel(context) {
    const names = {vendor: 'Vendor', region: 'Region', cluster: 'Cluster', city: 'City', campaign: 'Campaign'};
    return Object.entries(names).filter(([field]) => context?.[field] !== undefined && context?.[field] !== null && context?.[field] !== '')
      .map(([field, label]) => `${label}: ${field === 'campaign' ? hierarchyDisplayValue({level: 'Campaign', value: context[field]}) : context[field]}`)
      .join(' · ');
  }

  // With ``focus`` the options are operators ([operator, label]): the Focus operators come first (see appendFocusOptions).
  function insightSelect(key, options, label, fallback = options[0]?.[0], {focus = false} = {}) {
    const wrapper = document.createElement('label');
    wrapper.className = 'scoring-environment-filter scoring-insight-select';
    wrapper.append(document.createTextNode(label));
    const select = document.createElement('select');
    select.dataset.insightSelect = key;
    if (focus) {
      appendFocusOptions(select, options.map(([value, text]) => [value, text, value, text]));
    } else {
      for (const [value, text] of options) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = text;
        select.append(option);
      }
    }
    const stored = insightSelections.get(key);
    select.value = options.some(([value]) => value === stored) ? stored : fallback ?? '';
    wrapper.append(select);
    return {wrapper, value: select.value};
  }

  // The rank of each value (1 for the highest; equal values share their rank).
  function insightRanks(values) {
    return values.map(value => 1 + values.filter(other => other > value + 1e-9).length);
  }

  // A card per City, Cluster or Region: its operators from the highest score, each a bar of its Data points followed by
  // its Voice points (in the Data and Voice colours of the theme), with its total and, behind the first, its distance to it.
  // ``wide``: the card of the whole country (Nationwide), across the panel (``width``, its width in pixels) with larger
  // bars and text.
  function makeLocationCardChart(card, maximum, {wide = false, width: wideWidth = 1000} = {}) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const operators = [...(card.operators || [])].sort((left, right) => right.total - left.total);
    const ranks = insightRanks(operators.map(item => item.total));
    const k = wide ? 1.45 : 1;
    const width = wide ? Math.max(480, wideWidth) : 320, rowHeight = 30 * k, top = 4 * k, labelWidth = 96 * k, valueWidth = 78 * k;
    const height = top + operators.length * rowHeight + 4 * k;
    const plot = width - labelWidth - valueWidth;
    const scale = value => Math.max(0, Number(value) || 0) / (Number(maximum) || 1) * plot;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('class', 'scoring-location-card-chart');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${card.label}: ${operators.map(item => `${item.label} ${insightNumber(item.total)}`).join(', ')}`);
    const leader = operators[0]?.total ?? 0;
    operators.forEach((item, index) => {
      const y = top + index * rowHeight;
      const color = safeHexColor(item.color) || insightFallbackColors[index % insightFallbackColors.length];
      const group = svgElement(svg, 'g');
      setChartTooltip(group, `${item.label}: ${insightNumber(item.total, 1)} points (Data ${insightNumber(item.data, 1)}, Voice ${insightNumber(item.voice, 1)})${item.complete ? '' : ' — incomplete coverage'}`, true);
      const badge = svgElement(svg, 'circle', {cx: 9 * k, cy: y + 15 * k, r: 8 * k, fill: ranks[index] === 1 ? color : '#ffffff', stroke: color, 'stroke-width': 1.5 * k});
      const rank = svgElement(svg, 'text', {x: 9 * k, y: y + 18.5 * k, 'text-anchor': 'middle', 'font-size': 9.5 * k, 'font-weight': 800,
        fill: ranks[index] === 1 ? readableTextColor(color) : color});
      rank.textContent = String(ranks[index]);
      const label = svgElement(svg, 'text', {x: 22 * k, y: y + 19 * k, 'font-size': 11.5 * k, 'font-weight': 700, fill: '#263746'});
      label.textContent = String(item.label ?? '').length > 13 ? `${String(item.label).slice(0, 12)}…` : String(item.label ?? '');
      const dataWidth = scale(item.data), voiceWidth = scale(item.voice);
      group.append(badge, rank, label,
        svgElement(svg, 'rect', {x: labelWidth, y: y + 7 * k, width: Math.max(0, dataWidth), height: 16 * k, fill: insightDataColor}),
        svgElement(svg, 'rect', {x: labelWidth + dataWidth, y: y + 7 * k, width: Math.max(0, voiceWidth), height: 16 * k, fill: insightVoiceColor}));
      const total = svgElement(svg, 'text', {x: labelWidth + dataWidth + voiceWidth + 5 * k, y: y + 19 * k, 'font-size': 11.5 * k, 'font-weight': 800, fill: '#17232d'});
      total.textContent = `${insightNumber(item.total)}${item.complete ? '' : '*'}`;
      group.append(total);
      if (index) {
        const behind = svgElement(svg, 'tspan', {dx: 4 * k, 'font-size': 9.5 * k, 'font-weight': 600, fill: '#7a8a96'});
        behind.textContent = insightNumber(item.total - leader, 1).replace('-', '−');
        total.append(behind);
      }
      svg.append(group);
    });
    return svg;
  }

  function makeLocationCardsView(group) {
    const wrapper = document.createElement('div');
    const plural = {City: 'cities', Cluster: 'clusters', Region: 'regions'}[group.level] || 'locations';
    const national = group.level === 'National';
    const note = document.createElement('p');
    note.className = `scoring-insight-note scoring-location-note${national ? ' is-national' : ''}`;
    note.append(national ? `The ${scoringLabel()} scoring of the whole country, from its highest score: `
      : `The ${scoringLabel()} scoring of the selected ${plural}, each from its highest score: `);
    const maximum = document.createElement('strong');
    maximum.textContent = `${insightNumber(group.maximum)} points`;
    note.append(maximum, ` at most (Voice ${insightNumber(group.max_voice)} · Data ${insightNumber(group.max_data)})`,
      group.scaled ? ', the environments measured in each one scaled to them, so they compare with the overall scoring.' : '.');
    // The card of the whole country goes across the panel, its bars and text larger.
    const layout = document.createElement('div');
    layout.className = `scoring-location-cards${national ? ' is-national' : ''}`;
    for (const card of group.cards || []) {
      const article = document.createElement('article');
      article.className = `scoring-location-card${national ? ' is-national' : ''}`;
      const heading = document.createElement('h5');
      heading.textContent = String(card.label);
      if (!national) {
        article.append(heading, makeLocationCardChart(card, group.maximum));
      } else {
        // Drawn at the width of the panel, so its bars fill it and its text keeps its size; again when it changes.
        const chartBox = document.createElement('div');
        let drawnWidth = 0;
        const draw = () => {
          const available = Math.round(chartBox.clientWidth);
          if (!available || Math.abs(available - drawnWidth) < 3) return;
          drawnWidth = available;
          chartBox.replaceChildren(makeLocationCardChart(card, group.maximum, {wide: true, width: available}));
        };
        chartBox.append(makeLocationCardChart(card, group.maximum, {wide: true}));
        article.append(heading, chartBox);
        requestAnimationFrame(draw);
        if (typeof ResizeObserver === 'function') new ResizeObserver(draw).observe(chartBox);
      }
      layout.append(article);
    }
    const legend = document.createElement('div');
    legend.className = `scoring-location-legend${national ? ' is-national' : ''}`;
    legend.innerHTML = '<span><i class="is-data"></i>Data</span><span><i class="is-voice"></i>Voice</span><span><b>1</b> Position in the location</span>';
    wrapper.append(note, layout, legend);
    return wrapper;
  }

  // The scoring of each operator in every campaign: a line per operator ending in its name and latest score, the latest
  // campaign shaded.
  function makeTrendChart(trend) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const width = 980, height = 360, left = 56, right = 170, top = 18, bottom = 40;
    const values = trend.series.flatMap(series => series.points).filter(value => Number.isFinite(Number(value)) && value !== null);
    const minimum = Math.max(0, Math.floor((Math.min(...values) - 25) / 50) * 50);
    const maximum = Number(trend.maximum) || Math.max(...values);
    const count = trend.campaigns.length;
    const x = index => left + (width - left - right) * (count > 1 ? index / (count - 1) : .5);
    const y = value => top + (height - top - bottom) * (1 - (value - minimum) / Math.max(1, maximum - minimum));
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('class', 'scoring-trend-chart');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${scoringLabel()} scoring trend`);
    const step = count > 1 ? (width - left - right) / (count - 1) : width - left - right;
    svg.append(svgElement(svg, 'rect', {x: x(count - 1) - step / 2, y: top, width: step / 2 + 14, height: height - top - bottom, fill: '#f1f5f9'}));
    const gridStep = [25, 50, 100, 200, 250].find(item => (maximum - minimum) / item <= 8) || 500;
    for (let value = minimum; value <= maximum + .001; value += gridStep) {
      svg.append(svgElement(svg, 'line', {x1: left, x2: width - right + 14, y1: y(value), y2: y(value), stroke: '#e6eaee', 'stroke-dasharray': value === minimum ? '' : '3 4'}));
      const label = svgElement(svg, 'text', {x: left - 8, y: y(value) + 4, 'text-anchor': 'end', 'font-size': 11, fill: '#6b7a85'});
      label.textContent = insightNumber(value);
      svg.append(label);
    }
    trend.campaigns.forEach((campaign, index) => {
      const label = svgElement(svg, 'text', {x: x(index), y: height - bottom + 22, 'text-anchor': 'middle', 'font-size': 12,
        'font-weight': index === count - 1 ? 800 : 500, fill: '#263746'});
      label.textContent = campaign;
      svg.append(label);
    });
    const ends = [];
    trend.series.forEach((series, seriesIndex) => {
      const color = safeHexColor(series.color) || insightFallbackColors[seriesIndex % insightFallbackColors.length];
      const points = series.points.map((value, index) => (value === null || value === undefined ? null : [x(index), y(value), value]));
      const path = points.filter(Boolean).map(([px, py], index) => `${index ? 'L' : 'M'}${px},${py}`).join(' ');
      // (NSA & SA in the same chart: the SA line of each operator is dashed.)
      svg.append(svgElement(svg, 'path', {d: path, fill: 'none', stroke: color, 'stroke-width': series.is_reference ? 3 : 2.25,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round', ...(series.dashed ? {'stroke-dasharray': '7 5'} : {})}));
      const last = points.reduce((found, point, index) => (point ? index : found), -1);
      points.forEach((point, index) => {
        if (!point) return;
        const marker = svgElement(svg, 'circle', {cx: point[0], cy: point[1], r: index === last ? 5 : 3,
          fill: index === last ? color : '#ffffff', stroke: color, 'stroke-width': 1.75});
        setChartTooltip(marker, `${series.label} · ${trend.campaigns[index]}: ${insightNumber(point[2], 1)} points`, true);
        svg.append(marker);
      });
      if (last >= 0) ends.push({y: points[last][1], text: `${series.label} ${insightNumber(points[last][2])}`, color});
    });
    // The names at the end of the lines, moved apart so they never overlap.
    ends.sort((first, second) => first.y - second.y);
    for (let index = 1; index < ends.length; index += 1) ends[index].y = Math.max(ends[index].y, ends[index - 1].y + 15);
    for (const end of ends) {
      const label = svgElement(svg, 'text', {x: x(count - 1) + 16, y: end.y + 4, 'font-size': 12, 'font-weight': 800, fill: end.color});
      label.textContent = end.text;
      svg.append(label);
    }
    return svg;
  }

  // The National & Geographical Areas Trends: each operator's score per area, its change from the previous campaign or
  // period and its GAP to the reference, with a trend chart per area on the same scale.
  function makeAreaSummaryView(summary) {
    const view = document.createElement('div');
    view.className = 'scoring-area-summary-view';
    // Campaigns as the Campaign Maps show them; periods (2026-W07, 2026-07…) as they are.
    const period = value => (typeof globalThis.campaignLabel === 'function' ? globalThis.campaignLabel(value) || value : value);
    const signed = value => (value === null || value === undefined ? '—'
      : `${Number(value) > 0 ? '+' : ''}${insightNumber(value, 1)}`);
    const tone = value => (value === null || value === undefined || Math.abs(Number(value)) < .05 ? ''
      : Number(value) > 0 ? 'scoring-area-gain' : 'scoring-area-loss');
    const headers = ['Area', 'Operator', summary.latest_campaign ? `Score ${period(summary.latest_campaign)}` : 'Score'];
    if (summary.previous_campaign) headers.push(`Δ vs ${period(summary.previous_campaign)}`);
    headers.push(`Δ vs ${summary.reference_label || 'reference'}`);
    const rows = [];
    // Each area is a band of rows: its first row starts it, and every other area is shaded.
    const rowClasses = [];
    const unmeasured = [];
    // National, the Regions or Clusters, then the cities, a thick rule between them.
    let previousCategory = null;
    areaChartOrder(summary.areas || []).forEach((area, areaIndex) => {
      const measured = area.measured !== false;
      const category = areaCategory(area);
      const newCategory = previousCategory !== null && category !== previousCategory;
      previousCategory = category;
      if (!measured) unmeasured.push(area.label);
      area.rows.forEach((item, index) => {
        const color = safeHexColor(item.color);
        const missing = measured ? '' : `Not measured in ${period(summary.latest_campaign)}`;
        const cells = [
          {text: index ? '' : area.label, title: index ? '' : missing,
            className: `scoring-area-name is-${category}${measured ? '' : ' is-unmeasured'}`},
          {text: item.label, style: color ? {color} : {},
            className: `scoring-area-operator${item.is_reference ? ' scoring-area-reference' : ''}`},
          {text: item.points === null || item.points === undefined ? '—' : `${insightNumber(item.points, 1)}${item.complete ? '' : '*'}`,
            style: color ? {color} : {}, className: 'scoring-area-score',
            title: missing || (item.complete ? '' : 'Incomplete KPI coverage')},
        ];
        if (summary.previous_campaign) cells.push({text: signed(item.delta), className: tone(item.delta)});
        cells.push(item.is_reference ? '' : {text: signed(item.gap), className: tone(item.gap)});
        rows.push(cells);
        rowClasses.push(`${index ? '' : 'is-area-start'}${!index && newCategory ? ' is-category-start' : ''}${areaIndex % 2 ? ' is-area-shaded' : ''}`.trim());
      });
    });
    const tableWrap = document.createElement('div');
    tableWrap.className = 'scoring-insight-table-wrap scoring-expandable-part';
    // The table enlarges on its own with a double click, as each chart does.
    tableWrap.title = 'Double-click to enlarge this table';
    tableWrap.expandPart = () => openExpandedView(tableWrap.querySelector('table'), `${scoringLabel()} Trends — National & Geographical Areas`,
      'National & Geographical Areas Trends table', tableWrap, 'Table');
    const table = insightTable(headers, rows, {className: 'scoring-area-summary-table'});
    [...table.tBodies[0].rows].forEach((row, index) => { if (rowClasses[index]) row.className = rowClasses[index]; });
    tableWrap.append(table);
    if (unmeasured.length) {
      const missingNote = document.createElement('p');
      missingNote.className = 'scoring-note scoring-area-missing';
      missingNote.textContent = `${unmeasured.join(', ')}: not measured in ${period(summary.latest_campaign)}; `
        + 'the charts show the earlier campaigns.';
      tableWrap.append(missingNote);
    }
    view.append(tableWrap);
    const campaigns = (Array.isArray(summary.campaigns) ? summary.campaigns : []).map(period);
    if (campaigns.length >= 2) {
      const values = (summary.areas || []).flatMap(area => area.rows.flatMap(item => item.trend))
        .filter(value => value !== null && value !== undefined && Number.isFinite(Number(value))).map(Number);
      const spread = Math.max(...values) - Math.min(...values);
      const padding = Math.max(1, spread * .15);
      const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find(unit => unit * 5 >= spread + 2 * padding) || 1000;
      const low = Math.floor((Math.min(...values) - padding) / step) * step;
      const high = Math.ceil((Math.max(...values) + padding) / step) * step;
      const grid = document.createElement('div');
      grid.className = 'scoring-area-trend-grid';
      const chartAreas = areaChartOrder(summary.areas || []);
      let chartHeight = 170;
      const drawCharts = () => grid.replaceChildren(
        ...chartAreas.map(area => makeAreaTrendChart(area, campaigns, low, high, step, chartHeight)));
      drawCharts();
      view.append(grid);
      // Beside the table, the charts grow to take its height (never shorter than their usual size).
      const fitCharts = () => {
        const first = grid.firstElementChild;
        if (!view.isConnected || !first) return;
        const chartWidth = first.querySelector('svg')?.getBoundingClientRect().width || 0;
        if (!chartWidth) return;
        let height = 170;
        if (getComputedStyle(view).gridTemplateColumns.split(' ').length > 1) {
          const chartRows = Math.ceil(chartAreas.length / 2);
          const gap = parseFloat(getComputedStyle(grid).rowGap) || 0;
          const caption = first.querySelector('figcaption')?.getBoundingClientRect().height || 0;
          const available = (tableWrap.getBoundingClientRect().height - gap * (chartRows - 1)) / chartRows - caption;
          height = Math.max(170, Math.min(420, Math.round(available * 360 / chartWidth)));
        }
        if (Math.abs(height - chartHeight) < 6) return;
        chartHeight = height;
        drawCharts();
      };
      if (typeof ResizeObserver === 'function') new ResizeObserver(() => fitCharts()).observe(view);
    }
    const note = document.createElement('p');
    note.className = 'scoring-note';
    note.textContent = `Each area is scored with its own measurements, as the National scoring is: the area scores are not shares `
      + `of the National points. Maximum scoring: ${insightNumber(summary.maximum)} points`
      + `${summary.scaled ? ' (environments without measurements in an area are scaled)' : ''}.`;
    view.append(note);
    return view;
  }

  // National, the Regions or Clusters of the breakdown, then the cities: each its own colour, in this order.
  function areaCategory(area) {
    return area.kind === 'National' ? 'national' : area.kind === 'City' ? 'city' : 'breakdown';
  }

  function areaChartOrder(areas) {
    const rank = {national: 0, breakdown: 1, city: 2};
    return [...areas].sort((left, right) => rank[areaCategory(left)] - rank[areaCategory(right)]);
  }

  function makeAreaTrendChart(area, campaigns, low, high, step, height = 170) {
    const figure = document.createElement('figure');
    figure.className = 'scoring-area-trend';
    const caption = document.createElement('figcaption');
    // National, the areas of the breakdown and the cities each have their own colour.
    caption.className = `is-${areaCategory(area)}`;
    caption.textContent = area.label;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const width = 360, right = 34, top = 10;
    // Campaign or period labels that do not fit side by side are tilted, with room for them below the axis and,
    // for the first one, on the left.
    const spacing = (width - 42 - right) / Math.max(1, campaigns.length - 1);
    const labelWidth = Math.max(0, ...campaigns.map(campaign => String(campaign).length)) * 5.1;
    const tilted = campaigns.length > 1 && labelWidth > spacing - 4;
    const angle = Math.PI * 40 / 180;
    const left = tilted ? Math.max(42, Math.round(labelWidth * Math.cos(angle)) + 4) : 42;
    const bottom = tilted ? Math.round(16 + labelWidth * Math.sin(angle)) : 26;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${area.label} scoring trend`);
    const x = index => left + (width - left - right) * (campaigns.length > 1 ? index / (campaigns.length - 1) : .5);
    const y = value => top + (height - top - bottom) * (1 - (value - low) / Math.max(1, high - low));
    for (let value = low; value <= high + .001; value += step) {
      svg.append(svgElement(svg, 'line', {x1: left, x2: width - right, y1: y(value), y2: y(value), stroke: '#e3e6e9'}));
      const label = svgElement(svg, 'text', {x: left - 6, y: y(value) + 3, 'text-anchor': 'end', 'font-size': 9, fill: '#4a5b65'});
      label.textContent = insightNumber(value);
      svg.append(label);
    }
    campaigns.forEach((campaign, index) => {
      const labelY = height - bottom + 13;
      const label = svgElement(svg, 'text', tilted
        ? {x: x(index), y: labelY, 'text-anchor': 'end', 'font-size': 9, fill: '#263746', transform: `rotate(-40 ${x(index)} ${labelY})`}
        : {x: x(index), y: height - 8, 'text-anchor': 'middle', 'font-size': 9, fill: '#263746'});
      label.textContent = campaign;
      svg.append(label);
    });
    area.rows.forEach((item, seriesIndex) => {
      const color = safeHexColor(item.color) || insightFallbackColors[seriesIndex % insightFallbackColors.length];
      const points = item.trend.map((value, index) => (value === null || value === undefined ? null : [x(index), y(Number(value)), value]));
      const path = points.filter(Boolean).map(([px, py], index) => `${index ? 'L' : 'M'}${px},${py}`).join(' ');
      svg.append(svgElement(svg, 'path', {d: path, fill: 'none', stroke: color, 'stroke-width': 2,
        ...(item.dashed ? {'stroke-dasharray': '5 4'} : {})}));
      points.forEach((point, index) => {
        if (!point) return;
        const marker = svgElement(svg, 'circle', {cx: point[0], cy: point[1], r: 3.2, fill: item.dashed ? '#ffffff' : color,
          stroke: color, 'stroke-width': item.dashed ? 1.5 : 0});
        setChartTooltip(marker, `${item.label} · ${campaigns[index]}: ${insightNumber(point[2], 1)} points`, true);
        svg.append(marker);
      });
      const last = points.filter(Boolean).at(-1);
      if (last) {
        const label = svgElement(svg, 'text', {x: last[0] + 5, y: last[1] + 3, 'font-size': 9, 'font-weight': 700, fill: color});
        label.textContent = insightNumber(last[2]);
        svg.append(label);
      }
    });
    figure.append(caption, svg);
    // Each chart enlarges on its own with a double click (not the whole National & Geographical Areas card).
    figure.title = 'Double-click to enlarge this chart';
    figure.classList.add('scoring-expandable-part');
    figure.expandPart = () => {
      const large = makeAreaTrendChart(area, campaigns, low, high, step, Math.max(height, 240)).querySelector('svg');
      openExpandedView(large, `${scoringLabel()} — ${area.label}`, 'National & Geographical Areas Trends', figure, 'Area trend');
    };
    return figure;
  }

  // ---- Scoring Trends ----------------------------------------------------------------------------------------------
  // The Scoring Trend, then the National & Geographical Areas Trends, of the campaigns of the Scoring Trends of the calculation (those
  // of the scoring without campaigns of their own).
  function renderTrends(pane, payload, environment) {
    pane.replaceChildren();
    if (!environment) return;
    const trends = insightItems(payload, 'campaign_trends', environment);
    if (trends.length) {
      const {wrapper, value} = insightSelect('trend', trends.map((trend, index) => [String(index), trend.title || 'All series']), 'Series');
      const trend = trends[Number(value)] || trends[0];
      const card = makeExpandableChartCard(`${scoringLabel()} Scoring Trend`,
        [environmentLabel(environment), trend.title].filter(Boolean).join(' · '), makeTrendChart(trend));
      if (trends.length > 1) card.insertBefore(wrapper, card.children[1]);
      if (trend.series.some(series => series.nr_mode)) card.append(nrModeLinesNote());
      pane.append(card);
    }
    for (const summary of insightItems(payload, 'area_summaries', environment)) {
      const split = summary.time_split === 'All' ? 'All selected CDRs' : summary.time_split === 'Campaign' ? 'Per campaign'
        : `${summary.time_split} periods`;
      const card = makeExpandableChartCard(`${scoringLabel()} Trends — National & Geographical Areas`,
        [environmentLabel(environment), `Time split: ${split}`].filter(Boolean).join(' · '), makeAreaSummaryView(summary), false);
      if ((summary.areas || []).some(area => area.rows.some(item => item.nr_mode))) card.append(nrModeLinesNote(true));
      pane.append(card);
    }
    if (!pane.children.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No Scoring Trends are available: a trend needs two campaigns or more. Choose the campaigns of the '
        + 'Scoring Trends (and include the National & Geographical Areas Trends) in the Scoring Calculation panel.';
      pane.append(empty);
    }
  }

  // NSA & SA in the same chart: how the lines of each NR Mode read.
  function nrModeLinesNote(areas = false) {
    return insightParagraph('scoring-insight-note', nrModeTag('NSA'), 'solid lines · ', nrModeTag('SA'),
      `dashed lines: each quarter is one point for both NR Modes${areas ? '; each row scores the latest campaign of its NR Mode and its change from the previous one of that NR Mode' : ''}.`);
  }

  // A KPI name whose comparison, threshold and unit stay together when it wraps: FDTT DL THROUGHPUT / > 5Mbit/s [%].
  function kpiNameText(text) {
    return String(text).replace(/([<>≤≥=]+)\s+(?=\S)/g, '$1\u00A0').replace(/\s+(\[[^\]]*\])\s*$/, '\u00A0$1');
  }

  // A table of the insights; ``total`` (the cells of a row) closes it in its footer, styled as the total row of the
  // Score and GAP tables in each theme.
  function insightTable(headers, rows, {className = '', total = null} = {}) {
    const table = document.createElement('table');
    table.className = `scoring-insight-table ${className}`.trim();
    const head = table.createTHead().insertRow();
    for (const header of headers) {
      const cell = document.createElement('th');
      cell.textContent = header;
      head.append(cell);
    }
    const body = table.createTBody();
    const footer = total ? table.createTFoot() : null;
    for (const [section, cells] of [...rows.map(cells => [body, cells]), ...(footer ? [[footer, total]] : [])]) {
      const row = section.insertRow();
      for (const content of cells) {
        const cell = row.insertCell();
        if (content instanceof Node) cell.append(content);
        else if (content && typeof content === 'object') {
          cell.textContent = content.text ?? '';
          if (content.colSpan) cell.colSpan = content.colSpan;
          if (content.kpiType) {
            // A KPI starts with the R or D badge of its type, as in the Score and GAP tables. Its name wraps beside the
            // badge, and its threshold and unit (> 5Mbit/s [%]) never break apart, so a unit never stands alone on a line.
            const type = String(content.kpiType).trim().toLocaleLowerCase();
            const name = document.createElement('span');
            name.className = 'scoring-kpi-name';
            name.textContent = kpiNameText(content.text ?? '');
            cell.replaceChildren(name);
            if (type === 'reliable' || type === 'diff') {
              const badge = document.createElement('span');
              badge.className = 'scoring-kpi-badge';
              badge.dataset.kpiType = type;
              badge.textContent = type === 'reliable' ? 'R' : 'D';
              badge.title = `${content.kpiType} KPI`;
              const label = document.createElement('span');
              label.className = 'scoring-kpi-name-row';
              label.append(badge, name);
              cell.replaceChildren(label);
            }
          }
          if (content.title) cell.title = content.title;
          if (content.className) cell.className = content.className;
          if (content.style) Object.assign(cell.style, content.style);
          if (content.bar) {
            // A data bar under the value: the colour fading to white, as in the NetCheck tables.
            const bar = document.createElement('span');
            bar.className = 'scoring-insight-databar';
            bar.style.width = `calc((100% - .3rem) * ${content.bar.ratio})`;
            if (content.bar.side) {
              bar.classList.add(`is-${content.bar.side}`);
              bar.style.width = `calc((50% - .15rem) * ${content.bar.ratio})`;
              if (content.bar.side === 'left') Object.assign(bar.style, {left: 'auto', right: '50%'});
              else bar.style.left = '50%';
            }
            bar.style.setProperty('--databar-color', content.bar.color);
            const text = document.createElement('span');
            text.className = 'scoring-insight-databar-value';
            text.textContent = cell.textContent;
            // A GAP keeps room for its figure on either side of the middle line (see the styles of is-left and is-right).
            if (content.bar.side) text.dataset.figure = text.textContent;
            cell.replaceChildren(bar, text);
          }
        } else cell.textContent = content ?? '';
      }
    }
    // The header of a column of numbers is right-aligned like its values, so each column visibly ends where its
    // header does.
    for (const [index, cell] of [...head.cells].entries()) {
      const numeric = [...body.rows].some(row => row.cells[index]?.matches('.scoring-insight-number, .scoring-insight-bar-cell'));
      cell.classList.toggle('is-numeric', numeric);
    }
    return table;
  }

  function gapBarCell(value, scale, {loss = false, total = false} = {}) {
    const cell = {text: insightNumber(value, 2),
      className: `scoring-insight-bar-cell${total ? ' scoring-insight-total' : ''}${loss ? '' : ' is-signed'}`};
    if (value === null || value === undefined || !Number(value) || !scale) return cell;
    // A GAP grows from the middle of its cell: to the left when the operator is behind, to the right when it is ahead.
    // Points lost always grow from the left.
    cell.bar = {ratio: Math.min(1, Math.abs(value) / scale), color: loss || value < 0 ? insightLossColor : insightGainColor,
      side: loss ? '' : value < 0 ? 'left' : 'right'};
    return cell;
  }

  // A figure of the total row of an insight table: bold, a GAP (``signed``) in the colour of its sign.
  function insightTotalCell(value, {digits = 2, signed = false, suffix = ''} = {}) {
    const number = Number(value);
    const known = value !== null && value !== undefined && Number.isFinite(number);
    const sign = known && signed ? (number < 0 ? ' is-loss' : number > 0 ? ' is-gain' : '') : '';
    return {text: known ? `${signed && number > 0 ? '+' : ''}${insightNumber(number, digits)}${suffix}` : '—',
      className: `scoring-insight-number scoring-insight-total${sign}`};
  }

  function insightTotalLabel(text = 'Total', colSpan = 1) {
    return {text, colSpan, className: 'scoring-insight-total-label'};
  }

  // The KPIs of an operator grouped by their category (the categories that lose most first), each with its points lost
  // against the maximum or its GAP to the reference per environment and in total, with a bar in every column.
  function profileTable(profile, kind) {
    const rows = kind === 'maximum' ? profile.to_maximum : profile.to_reference;
    const totalKey = kind === 'maximum' ? 'total_gap_to_maximum' : 'total_gap_to_reference';
    const valueKey = kind === 'maximum' ? 'gap_to_maximum' : 'gap_to_reference';
    const columnScale = values => Math.max(0, ...values.map(value => Math.abs(Number(value) || 0)));
    const scale = columnScale(rows.map(row => row[totalKey]));
    const scales = Object.fromEntries(profile.columns.map(name => [name, columnScale(rows.map(row => row[valueKey]?.[name]))]));
    const groups = new Map();
    for (const row of rows) {
      const key = `${row.service}|${row.category}`;
      if (!groups.has(key)) groups.set(key, {service: row.service, category: row.category, rows: [], total: 0});
      const group = groups.get(key);
      group.rows.push(row);
      group.total += Number(row[totalKey]) || 0;
    }
    const ordered = [...groups.values()].sort((left, right) => (kind === 'maximum' ? right.total - left.total : left.total - right.total));
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-insight-table-wrap';
    const banner = document.createElement('div');
    banner.className = 'scoring-insight-banner';
    const bannerColor = safeHexColor(profile.color);
    if (bannerColor) banner.style.setProperty('--banner-color', bannerColor);
    const name = document.createElement('strong');
    name.textContent = profile.label;
    banner.append(name, kind === 'maximum' ? ' · points lost per KPI' : ` · GAP to ${profile.reference_label} per KPI`);
    const tableRows = [];
    for (const group of ordered) {
      tableRows.push([{text: `${group.category} · ${group.service}`, className: 'scoring-insight-group'},
        ...profile.columns.map(column => ({text: insightNumber(group.rows.reduce((sum, row) => sum + (Number(row[valueKey]?.[column]) || 0), 0), 2),
          className: 'scoring-insight-number scoring-insight-group'})),
        {text: insightNumber(group.total, 2), className: 'scoring-insight-number scoring-insight-group scoring-insight-total'}]);
      for (const row of group.rows) {
        tableRows.push([{text: row.kpi, className: 'scoring-insight-kpi', kpiType: row.kpi_type},
          ...profile.columns.map(column => gapBarCell(row[valueKey]?.[column], scales[column], {loss: kind === 'maximum'})),
          gapBarCell(row[totalKey], scale, {loss: kind === 'maximum', total: true})]);
      }
    }
    // The total of every column: the points the operator loses, or its GAP to the reference, in each environment and in all.
    const total = [insightTotalLabel(kind === 'maximum' ? 'Total points lost' : 'Total KPI GAP'),
      ...profile.columns.map(column => insightTotalCell(rows.reduce((sum, row) => sum + (Number(row[valueKey]?.[column]) || 0), 0),
        {signed: kind !== 'maximum'})),
      insightTotalCell(rows.reduce((sum, row) => sum + (Number(row[totalKey]) || 0), 0), {signed: kind !== 'maximum'})];
    wrapper.append(banner, insightTable(['KPI', ...profile.columns.map(column => environmentLabel(column)), 'Total'], tableRows,
      {className: 'scoring-profile-table', total}));
    return wrapper;
  }

  // The KPI GAP Profile and the Points Lost Map share their location (for example City: London) and
  // operators: choosing them in one section chooses them in the other. Several operators can be chosen.
  function gapInsightControls(pane, items) {
    const scopeKey = item => JSON.stringify(item.context || {});
    const controls = document.createElement('div');
    controls.className = 'scoring-loss-controls';
    const scopes = [...new Map(items.map(item => [scopeKey(item), item.context || {}])).entries()];
    // Locations by campaign are listed chronologically (in the order of the Campaign Maps), the latest chosen by default.
    const byCampaign = scopes.length > 1 && scopes.every(([, context]) => context.campaign) && typeof globalThis.campaignCompare === 'function';
    if (byCampaign) scopes.sort(([, left], [, right]) => globalThis.campaignCompare(left.campaign, right.campaign));
    let scope = (byCampaign ? scopes.at(-1) : scopes[0])?.[0] ?? '{}';
    if (scopes.length > 1) {
      const {wrapper, value} = insightSelect('gap-insight-scope', scopes.map(([key, context]) => [key, lossScopeLabel(context).value]),
        lossScopeLabel(scopes[0][1]).title, scope);
      controls.append(wrapper);
      scope = value;
    }
    const inScope = items.filter(item => scopeKey(item) === scope);
    const operators = [...new Map(inScope.map(item => [item.operator, item])).values()];
    // By default every operator is chosen. An operator offered after the choice was saved starts chosen too;
    // choices saved before the reference operator was offered did not include it.
    let stored = null;
    let offered = null;
    try { stored = JSON.parse(insightSelections.get('gap-insight-operators') || 'null'); } catch (_error) { stored = null; }
    try { offered = JSON.parse(insightSelections.get('gap-insight-operators-offered') || 'null'); } catch (_error) { offered = null; }
    const names = operators.map(item => item.operator);
    const isReference = item => item.is_reference === true || (item.reference !== undefined && item.operator === item.reference);
    const newlyOffered = item => offered === '*' ? false : Array.isArray(offered) ? !offered.includes(item.operator) : isReference(item);
    let chosen = Array.isArray(stored)
      ? [...new Set([...stored.filter(operator => names.includes(operator)), ...operators.filter(newlyOffered).map(item => item.operator)])]
      : [];
    // Without a choice, the Focus operators (every operator without them), as the PowerPoint and Word.
    if (!chosen.length) chosen = focusChosen(operators);
    chosen = withOperatorChoices('gap-insight-operators', names, chosen);
    const group = document.createElement('div');
    group.className = 'scoring-environment-filter scoring-loss-operators';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', 'Operators');
    group.append(document.createTextNode('Operators: '));
    const makeChip = item => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'scoring-loss-operator';
      chip.dataset.gapInsightOperator = item.operator;
      chip.dataset.gapInsightOperators = JSON.stringify(chosen);
      chip.dataset.gapInsightOffered = JSON.stringify(names);
      chip.setAttribute('aria-pressed', String(chosen.includes(item.operator)));
      chip.textContent = item.label;
      // Clicking an operator disables or enables it; one operator always stays enabled.
      chip.title = !chosen.includes(item.operator) ? `Click to enable ${item.label}`
        : chosen.length > 1 ? `Click to disable ${item.label}` : `${item.label} is the only enabled operator: click another one to enable it too`;
      const color = safeHexColor(item.color);
      if (color) chip.style.setProperty('--operator-color', color);
      return chip;
    };
    appendFocusChips(group, operators, makeChip);
    controls.append(group);
    return {controls, inScope, chosen};
  }

  // The KPI GAP Profile (GAP Analysis): each compared operator's GAP to the reference per KPI. The points each operator
  // loses per KPI against the maximum are in Points Lost (see renderPointsPerKpi).
  function renderKpiGapProfiles(pane, payload, environment) {
    if (!environment) return;
    const profiles = insightItems(payload, 'kpi_gap_profiles', environment);
    if (!profiles.length) return;
    const section = document.createElement('section');
    section.className = 'scoring-insight-section scoring-result-card scoring-gap-profile-card';
    const heading = document.createElement('h4');
    heading.className = 'scoring-table-section-title';
    heading.textContent = 'KPI GAP Profile';
    const {controls, inScope, chosen} = gapInsightControls(pane, profiles);
    appendResultScope(heading, inScope[0]?.context);
    section.append(heading, controls);
    const grid = document.createElement('div');
    grid.className = 'scoring-insight-pair';
    const shown = inScope.filter(item => chosen.includes(item.operator) && item.operator !== item.reference);
    for (const profile of shown) grid.append(profileTable(profile, 'reference'));
    section.append(grid);
    if (!shown.length) {
      section.append(insightParagraph('scoring-insight-note', 'Choose an operator other than the reference to see its GAP to it per KPI.'));
    } else {
      const note = document.createElement('p');
      note.className = 'scoring-insight-note';
      shown.forEach((profile, index) => {
        const gap = profile.to_reference.reduce((sum, row) => sum + (Number(row.total_gap_to_reference) || 0), 0);
        note.append(index ? '; ' : '', insightStrong(profile.label, safeHexColor(profile.color)), ' is ',
          insightStrong(`${gap >= 0 ? '+' : ''}${insightNumber(gap, 2)} points`), ` against ${profile.reference_label}`);
      });
      note.append('. The GAP of a KPI is the points of the operator minus those of the reference; each category sums its KPIs, the categories furthest behind first.');
      section.append(note);
    }
    pane.append(section);
  }

  // Points lost per KPI (Points Lost): the points each operator, the reference included, loses against the maximum of
  // every KPI. It shares the location and operators of the KPI GAP Profile and the Points Lost Map.
  function renderPointsPerKpi(pane, payload, environment) {
    if (!environment) return;
    const profiles = insightItems(payload, 'kpi_gap_profiles', environment);
    if (!profiles.length) return;
    const section = document.createElement('section');
    section.className = 'scoring-insight-section scoring-result-card scoring-points-kpi-card';
    const heading = document.createElement('h4');
    heading.className = 'scoring-table-section-title';
    heading.textContent = 'Points lost per KPI';
    const {controls, inScope, chosen} = gapInsightControls(pane, profiles);
    appendResultScope(heading, inScope[0]?.context);
    section.append(heading, controls);
    const grid = document.createElement('div');
    grid.className = 'scoring-insight-pair';
    const shown = inScope.filter(item => chosen.includes(item.operator));
    for (const profile of shown) grid.append(profileTable(profile, 'maximum'));
    const note = document.createElement('p');
    note.className = 'scoring-insight-note';
    shown.forEach((profile, index) => {
      const lost = profile.to_maximum.reduce((sum, row) => sum + (Number(row.total_gap_to_maximum) || 0), 0);
      note.append(index ? '; ' : '', insightStrong(profile.label, safeHexColor(profile.color)), ' loses ',
        insightStrong(`${insightNumber(lost, 2)} ${scoringLabel()} points`));
    });
    note.append('. The points lost of a KPI are its maximum minus the points scored; each category sums its KPIs, the categories that lose most first.');
    section.append(grid, note);
    pane.append(section);
  }

  // The operators enabled or disabled with the buttons of any section ({operator: true|false}): every section with
  // operator buttons applies them over its own choice, so after a click in one section every section shows its
  // operators as that one does (also those drawn later and the PowerPoint and Word).
  function operatorChoices() {
    try {
      const stored = JSON.parse(insightSelections.get('operator-choices') || 'null');
      return stored && typeof stored === 'object' && !Array.isArray(stored) ? stored : {};
    } catch (_error) {
      return {};
    }
  }

  function setOperatorChoices(states) {
    insightSelections.set('operator-choices', JSON.stringify({...operatorChoices(), ...states}));
    // The KPI GAP Profile and the Points Lost Map stop following the GAP comparison.
    insightSelections.delete('gap-insight-follows-comparison');
  }

  // The choice of a section (``key``, its operators ``names``) with the operators enabled or disabled in any section;
  // one always stays enabled. A changed choice is kept as the section's own, as the export takes it.
  function withOperatorChoices(key, names, chosen) {
    if (key === 'gap-insight-operators' && insightSelections.get('gap-insight-follows-comparison') === 'true') return chosen;
    const choices = operatorChoices();
    const next = names.filter(name => typeof choices[name] === 'boolean' ? choices[name] : chosen.includes(name));
    if (!next.length || (next.length === chosen.length && next.every(name => chosen.includes(name)))) return chosen;
    insightSelections.set(key, JSON.stringify(next));
    if (key === 'gap-insight-operators') insightSelections.set('gap-insight-operators-offered', JSON.stringify(names));
    return next;
  }

  // Choosing the operators of a section: its Focus operators are chosen by default (every operator without them), the
  // Focus operators and the others in subpanels of their own; clicking one enables or disables it there and in every other section (see
  // operatorChoices), and one always stays enabled.
  function insightOperatorChips(key, items) {
    const operators = [...new Map(items.map(item => [item.operator, item])).values()];
    const names = operators.map(item => item.operator);
    let stored = null;
    try { stored = JSON.parse(insightSelections.get(key) || 'null'); } catch (_error) { stored = null; }
    let chosen = Array.isArray(stored) ? stored.filter(name => names.includes(name)) : [];
    // The Focus operators by default (every operator without them), as the PowerPoint and Word.
    if (!chosen.length) chosen = focusChosen(operators);
    chosen = withOperatorChoices(key, names, chosen);
    const group = document.createElement('div');
    group.className = 'scoring-environment-filter scoring-loss-operators';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', 'Operators');
    group.append(document.createTextNode('Operators: '));
    const makeChip = item => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'scoring-loss-operator';
      chip.dataset.insightChipKey = key;
      chip.dataset.insightChip = item.operator;
      chip.dataset.insightChosen = JSON.stringify(chosen);
      chip.setAttribute('aria-pressed', String(chosen.includes(item.operator)));
      chip.textContent = item.label + (item.is_reference ? ' (reference)' : '');
      chip.title = !chosen.includes(item.operator) ? `Click to enable ${item.label}`
        : chosen.length > 1 ? `Click to disable ${item.label}` : `${item.label} is the only enabled operator: click another one to enable it too`;
      const color = safeHexColor(item.color);
      if (color) chip.style.setProperty('--operator-color', color);
      return chip;
    };
    appendFocusChips(group, operators, makeChip);
    return {control: group, chosen};
  }

  // The scope of a section when the results have several (for example City: London or Vendor: Nokia), the first one by
  // default; ``items`` carry their context.
  function insightScopeControl(key, items, {withCampaign = false} = {}) {
    const keyOf = item => JSON.stringify(Object.fromEntries(Object.entries(item.context || {})
      .filter(([field]) => withCampaign || field !== 'campaign').sort()));
    const scopes = [...new Map(items.map(item => [keyOf(item), item.context || {}])).entries()];
    if (scopes.length <= 1) return {control: null, inScope: items, context: scopes[0]?.[1] || {}};
    const label = context => lossScopeLabel(Object.fromEntries(Object.entries(context).filter(([field]) => withCampaign || field !== 'campaign')));
    // Scopes by campaign are listed chronologically, the latest chosen by default.
    const byCampaign = withCampaign && scopes.every(([, context]) => context.campaign) && typeof globalThis.campaignCompare === 'function';
    if (byCampaign) scopes.sort(([, left], [, right]) => globalThis.campaignCompare(left.campaign, right.campaign) || 0);
    const latestOf = context => scopes.filter(([, other]) => sameScope(other, context)).at(-1)?.[0];
    const {wrapper, value} = insightSelect(key, scopes.map(([scope, context]) => [scope, label(context).value || 'All']),
      label(scopes[0][1]).title || 'Scope', byCampaign ? latestOf(scopes[0][1]) : scopes[0][0]);
    return {control: wrapper, inScope: items.filter(item => keyOf(item) === value), context: (scopes.find(([scope]) => scope === value) || scopes[0])[1]};
  }

  function insightSection(pane, title, className, context = null) {
    const section = document.createElement('section');
    section.className = `scoring-insight-section scoring-result-card ${className}`.trim();
    const heading = document.createElement('h4');
    heading.className = 'scoring-table-section-title';
    heading.textContent = title;
    appendResultScope(heading, context);
    section.append(heading);
    pane.append(section);
    return section;
  }

  function insightControls(...controls) {
    const box = document.createElement('div');
    box.className = 'scoring-loss-controls';
    box.append(...controls.filter(Boolean));
    return box;
  }

  function insightParagraph(className, ...parts) {
    const paragraph = document.createElement('p');
    paragraph.className = className;
    paragraph.append(...parts.map(part => (part instanceof Node ? part : document.createTextNode(String(part)))));
    return paragraph;
  }

  function insightStrong(text, color = null) {
    const element = document.createElement('strong');
    element.textContent = text;
    if (color) element.style.color = color;
    return element;
  }

  const signedPoints = (value, digits = 1) => (value === null || value === undefined ? '—'
    : `${Number(value) > 0 ? '+' : ''}${insightNumber(value, digits)}`.replace('-', '−'));
  const ordinalText = number => `${number}${number % 100 >= 11 && number % 100 <= 13 ? 'th' : ({1: 'st', 2: 'nd', 3: 'rd'}[number % 10] || 'th')}`;
  const toneClass = value => (value === null || value === undefined || Math.abs(Number(value)) < .05 ? ''
    : Number(value) > 0 ? 'is-gain' : 'is-loss');

  // A diverging bar for a value between −scale and +scale: red to the left (behind), green to the right (ahead).
  function divergingBar(value, scale, {label = true, digits = 1} = {}) {
    const box = document.createElement('span');
    box.className = 'scoring-diverging';
    const track = document.createElement('span');
    track.className = 'scoring-diverging-track';
    const bar = document.createElement('i');
    const share = scale ? Math.min(1, Math.abs(Number(value) || 0) / scale) * 50 : 0;
    bar.style.width = `${share}%`;
    bar.style.left = Number(value) < 0 ? `${50 - share}%` : '50%';
    bar.className = Number(value) < 0 ? 'is-loss' : 'is-gain';
    track.append(bar);
    box.append(track);
    if (label) {
      const text = document.createElement('b');
      text.textContent = signedPoints(value, digits);
      text.className = toneClass(value);
      box.append(text);
    }
    return box;
  }

  // ---- Summary: where each operator stands -------------------------------------------------------------------------
  function renderSummary(pane, payload, environment) {
    pane.replaceChildren();
    if (!environment) return;
    const standings = insightItems(payload, 'standings', environment);
    if (!standings.length) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No summary is available for this environment.';
      pane.append(empty);
    }
    // How the measurements ran, Where to act and Where to act by performance owner come first; the places ranked and the
    // route that loses most follow the standings, positions and levers.
    // (The parts of NSA vs SA leave How the measurements ran to the whole result, above them.)
    const scope = payload.nr_mode_part ? null : insightItems(payload, 'campaign_scope', environment)[0];
    if (scope) {
      const section = insightSection(pane, 'How the measurements ran', 'scoring-scope-card', false);
      section.append(makeCampaignScope(scope));
    }
    const later = document.createDocumentFragment();
    renderWhereToAct(pane, payload, environment, later);
    const {control: scopeControl, inScope, context} = insightScopeControl('summary-scope', standings);
    const standing = inScope[0];
    if (standing) {
      const operators = standing.operators.map(item => ({...item}));
      // The Summary shows every operator by default, the reference included.
      const {control: chips, chosen} = insightOperatorChips('summary-operators', operators);
      const section = insightSection(pane, `Where each operator stands${standing.campaign ? ` — ${standing.campaign}` : ''}`,
        'scoring-standings-card', context);
      section.append(insightControls(scopeControl, chips));
      section.append(makeStandingsLeaderboard(standing));
      for (const row of operators.filter(item => chosen.includes(item.operator))) section.append(makeStandingTiles(standing, row));
    }
    const matrices = insightItems(payload, 'position_matrices', environment).filter(item => !context || sameScope(item.context, context));
    if (matrices.length) {
      const matrix = matrices[0];
      const {control: chips, chosen} = insightOperatorChips('summary-operators', matrix.operators);
      const section = insightSection(pane, `Position in every environment and service${matrix.campaign ? ` — ${matrix.campaign}` : ''}`,
        'scoring-position-card', matrix.context);
      section.append(insightControls(chips));
      const grid = document.createElement('div');
      grid.className = 'scoring-position-grid';
      for (const style of matrix.operators.filter(item => chosen.includes(item.operator))) grid.append(makePositionMatrix(matrix, style));
      section.append(grid, insightParagraph('scoring-insight-note',
        'Each tile is the position of the operator among those measured and its share of the points available; the bar under it, the points it missed there of those available (missed / available). ',
        'All Environments scales the environments measured to the full maximum, as the scoring per location does.'));
    }
    const levers = insightItems(payload, 'levers', environment).filter(item => !context || sameScope(item.context, context));
    if (levers.length) {
      const {control: chips, chosen} = insightOperatorChips('summary-operators', levers);
      const section = insightSection(pane, 'Biggest levers: the KPIs where matching the reference wins most points', 'scoring-levers-card',
        levers[0].context);
      section.append(insightControls(chips));
      const grid = document.createElement('div');
      grid.className = 'scoring-insight-pair';
      for (const item of levers.filter(entry => chosen.includes(entry.operator))) grid.append(makeLeversTable(item));
      section.append(grid);
    }
    pane.append(later);
  }

  // How the measurements of both NR Modes of NSA vs SA ran, above the Summary of each NR Mode: the latest NSA and SA
  // campaigns stand out among the campaigns.
  function renderSummaryScope(pane, payload, environment) {
    pane.replaceChildren();
    const scope = environment ? insightItems(payload, 'campaign_scope', environment)[0] : null;
    if (!scope) return;
    // The tests of the latest campaign of each NR Mode.
    const testScopes = (Array.isArray(payload.nr_mode_parts) ? payload.nr_mode_parts : [])
      .map(part => ({mode: part.nr_mode, scope: insightItems(activeScoringPayload(part), 'campaign_scope', environment)[0]}))
      .filter(item => item.scope);
    const section = insightSection(pane, 'How the measurements ran', 'scoring-scope-card', false);
    section.append(makeCampaignScope(scope, {nrModes: true, testScopes}));
  }

  // One operator chosen with buttons, the Focus operators and the others in subpanels of their own (as the operator
  // buttons of the other sections): clicking one shows it.
  function insightOperatorPicker(key, items, fallback) {
    const operators = [...new Map(items.map(item => [item.operator, item])).values()];
    const stored = insightSelections.get(key);
    const value = operators.some(item => item.operator === stored) ? stored : (fallback ?? operators[0]?.operator);
    const group = document.createElement('div');
    group.className = 'scoring-environment-filter scoring-loss-operators';
    group.setAttribute('role', 'radiogroup');
    group.setAttribute('aria-label', 'Operator');
    group.append(document.createTextNode('Operator: '));
    const makeChip = item => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'scoring-loss-operator';
      chip.dataset.insightPick = key;
      chip.dataset.insightPickOperator = item.operator;
      const label = item.label || item.operator;
      chip.setAttribute('role', 'radio');
      chip.setAttribute('aria-checked', String(item.operator === value));
      chip.setAttribute('aria-pressed', String(item.operator === value));
      chip.textContent = label;
      chip.title = item.operator === value ? `${label} is shown` : `Click to show ${label}`;
      const color = safeHexColor(item.color);
      if (color) chip.style.setProperty('--operator-color', color);
      return chip;
    };
    appendFocusChips(group, operators, makeChip);
    return {control: group, value};
  }

  // ---- Summary: where to act (see scoring_where_to_act.py) --------------------------------------------------------
  // The plan of an operator, its performance owners, its Cities, Towns, Roads and Railways ranked and the route that
  // loses most, for the operator chosen (the first compared operator by default); the places ranked and the route go
  // to ``later`` (after the standings, positions and levers of the Summary).
  function renderWhereToAct(pane, payload, environment, later = pane) {
    const views = ['act_plans', 'owner_cards', 'place_rankings', 'route_focus'].map(key => insightItems(payload, key, environment));
    const [plans, cards, places, routes] = views;
    const all = views.flat();
    if (!all.length) return;
    // The first Focus operator by default (else the first operator compared with the reference).
    const fallback = focusDefault([...new Map(all.map(item => [item.operator, item])).values()])[0];
    const {control: operatorControl, value: operator} = insightOperatorPicker('act-operator', all, fallback);
    // Each performance owner keeps one colour of the categories of the theme on every view and in the exports, in the
    // order of the owners of the results (scoring_where_to_act.owner_order).
    const ownerOrder = payload?.views?.insights?.owner_order;
    const owners = Array.isArray(ownerOrder) && ownerOrder.length ? ownerOrder.map(String) : [...new Set([...cards.flatMap(item => item.cards.map(card => card.owner)),
      ...places.flatMap(item => item.groups.flatMap(group => group.rows.flatMap(row => row.owners.map(owner => owner.name)))),
      ...routes.flatMap(item => item.routes.flatMap(route => route.owners.filter(owner => !owner.unidentified).map(owner => owner.name)))])].sort();
    const palette = activeTheme?.categories || ['#4472C4', '#7030A0', '#C55A11', '#5B9BD5', '#A64D79', '#548235'];
    const ownerColor = name => (owners.includes(name) ? palette[owners.indexOf(name) % palette.length] : '#9aa3ad');
    const pill = (name, text = name) => {
      const element = document.createElement('span');
      element.className = 'scoring-owner-pill';
      element.style.setProperty('--owner-color', ownerColor(name));
      element.textContent = text;
      return element;
    };
    let controlsShown = false;
    const controls = (...extra) => {
      const box = insightControls(controlsShown ? null : operatorControl, ...extra);
      controlsShown = true;
      return box;
    };
    const plan = plans.find(item => item.operator === operator);
    if (plan) {
      const section = insightSection(pane, `Where to act — ${plan.label}`, 'scoring-act-card', plan.context);
      section.append(controls(), insightParagraph('scoring-act-headline', plan.headline));
      const list = document.createElement('div');
      list.className = 'scoring-act-list';
      // The columns, as on the slides: the theme and its points, what to do and the view of the results to open.
      const header = document.createElement('div');
      header.className = 'scoring-act-row scoring-act-header';
      for (const [text, title] of [['Theme', 'Where the points lost are'], ['What to do', 'The KPIs or places that lose most, with their points of the scoring'],
        ['Deep-dive', 'The view of the results that shows it in detail']]) {
        const cell = document.createElement('span');
        cell.textContent = text;
        cell.title = title;
        header.append(cell);
      }
      list.append(header);
      const stripes = activeTheme?.categories || palette;
      plan.rows.forEach((row, index) => {
        const item = document.createElement('div');
        item.className = 'scoring-act-row';
        item.style.setProperty('--act-color', stripes[index % stripes.length]);
        const theme = document.createElement('div');
        theme.className = 'scoring-act-theme';
        // The points of the scoring stand out in the loss colour of the theme.
        const figure = value => {
          const element = document.createElement('strong');
          element.className = 'scoring-act-figure';
          element.textContent = value;
          return element;
        };
        theme.append(insightStrong(row.theme), row.points === null || row.points === undefined
          ? insightParagraph('scoring-act-points', 'Within the points above')
          : insightParagraph('scoring-act-points', figure(`${insightNumber(row.points, 1)} points`), ' lost'));
        const action = row.action_parts?.length ? row.action_parts.map(part => (part.points ? figure(part.text) : part.text)) : [row.action];
        // Each view of the Deep-dive opens its section of the Points Lost tab.
        const deepDive = insightParagraph('scoring-act-deep-dive');
        if (row.deep_dive_links?.length) {
          deepDive.append('Points Lost: ');
          row.deep_dive_links.forEach((link, linkIndex) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'scoring-act-link';
            button.textContent = link.label;
            button.title = `Open ${link.label} in Points Lost`;
            button.addEventListener('click', () => openPointsLostSection(link.section));
            deepDive.append(linkIndex ? '; ' : '', button);
          });
        } else deepDive.append(row.deep_dive);
        item.append(theme, insightParagraph('scoring-act-action', ...action), deepDive);
        list.append(item);
      });
      section.append(list, insightParagraph('scoring-insight-note', 'Points lost: the points of the scoring lost against the maximum of each KPI ',
        '(GAP Analysis compares with the reference instead), each place counting by its share of the tests (national estimates). ',
        'Sites to review and route stretches are within the points above.'));
    }
    const ownerItem = cards.find(item => item.operator === operator);
    if (ownerItem) {
      const section = insightSection(pane, `Where to act, by performance owner — ${ownerItem.label}`, 'scoring-owner-card', ownerItem.context);
      section.append(controls(), insightParagraph('scoring-act-headline', "Each performance owner's points lost, what drives them and where they are"));
      const grid = document.createElement('div');
      grid.className = 'scoring-owner-grid';
      const peak = Math.max(0.01, ...ownerItem.cards.flatMap(card => Object.values(card.settings || {})));
      for (const card of ownerItem.cards) {
        const box = document.createElement('article');
        box.className = 'scoring-owner';
        box.style.setProperty('--owner-color', ownerColor(card.owner));
        const head = document.createElement('header');
        const points = document.createElement('b');
        points.textContent = insightNumber(card.points, 1);
        head.append(insightStrong(card.owner), document.createElement('br'), points, document.createTextNode(' National points lost'));
        const facts = document.createElement('div');
        facts.className = 'scoring-owner-facts';
        const fact = (label, text) => { if (text) facts.append(insightParagraph('', insightStrong(`${label}: `), text)); };
        fact('Main issue', card.main);
        fact('Biggest areas', card.areas.map(area => `${area.name} (${area.setting.toLowerCase()}) ${insightNumber(area.points, 1)}`).join(', '));
        fact('High sites', card.high_sites.length ? `${card.high_sites.length} (${[...new Set(card.high_sites.map(site => site.city).filter(Boolean))].join('; ')})` : 'none');
        const where = document.createElement('div');
        where.className = 'scoring-owner-where';
        where.append(insightParagraph('scoring-owner-where-title', 'Where its points are'));
        // Results calculated before the points of each owner were kept per City or route have none.
        if (!card.settings) where.append(insightParagraph('scoring-insight-note', 'Recalculate the Saved Filter (Scoring Calculation) to see them.'));
        for (const [setting, value] of Object.entries(card.settings || {})) {
          const row = document.createElement('div');
          const bar = document.createElement('i');
          bar.style.width = `${Math.max(value > 0 ? 2 : 0, value / peak * 100)}%`;
          const track = document.createElement('span');
          track.append(bar);
          row.append(document.createTextNode(setting), track, insightStrong(insightNumber(value, 1)));
          where.append(row);
        }
        box.append(head, facts, where);
        grid.append(box);
      }
      section.append(grid, insightParagraph('scoring-insight-note', 'Performance owner: the Region of the tests (such as Vendor A, Vendor B, VMO2 North or VMO2 South). ',
        'Points lost: the National points of the scoring lost against the maximum in its tests (each place by its share of the tests), not the own score of its Region (see the National & Geographical Areas Trends in Scoring Trends). ',
        `High site: ${insightNumber(1, 0)}+ point lost and losses on the same site in an earlier campaign.${ownerItem.unidentified > .05 ? ` ${insightNumber(ownerItem.unidentified, 1)} points have no Region.` : ''}`));
    }
    // The Cities, Towns, Roads and Railways ranked, for every operator chosen with operator buttons of their own (as the
    // other sections, the Focus operators by default), whatever the operator of Where to act: a table per operator.
    if (places.length) {
      const {control: placeChips, chosen: placesChosen} = insightOperatorChips('places-operators', places);
      const rankings = places.filter(item => placesChosen.includes(item.operator));
      const peak = Math.max(0.01, ...rankings.flatMap(item => item.groups.flatMap(group => group.rows.map(row => row.lost))));
      const band = value => (value >= 85 ? activeTheme?.band_strong?.High || '#6AA84F' : value >= 75 ? activeTheme?.band_strong?.Medium || '#E8A33D'
        : activeTheme?.band_strong?.Low || '#E06666');
      const owner = row => {
        const box = document.createElement('span');
        box.className = 'scoring-owner-pills';
        for (const item of row.owners) box.append(pill(item.name, `${item.name} ${insightNumber(item.share, 0)}%`));
        return box;
      };
      const share = value => (value === null || value === undefined ? '—'
        : {text: `${insightNumber(value, 0)}%`, className: 'scoring-insight-bar-cell', bar: {ratio: Math.min(1, value / 100), color: band(value)}});
      const titles = [...new Set(rankings.flatMap(item => item.groups.map(group => group.title)))];
      for (const title of titles) {
        const entries = rankings.map(ranking => [ranking, ranking.groups.find(group => group.title === title)]).filter(([, group]) => group);
        const section = insightSection(later, title, 'scoring-places-card', entries[0][0].context);
        section.append(insightControls(placeChips.cloneNode(true)));
        for (const [ranking, group] of entries) {
          const wrap = document.createElement('div');
          wrap.className = 'scoring-insight-table-wrap';
          const banner = document.createElement('div');
          banner.className = 'scoring-insight-banner';
          const color = safeHexColor(ranking.color);
          if (color) banner.style.setProperty('--banner-color', color);
          banner.append(insightStrong(ranking.label), ` · ${group.headline}`);
          wrap.append(banner, insightTable(['Place', 'Owner', 'Points %', `vs ${ranking.previous_campaign || 'previous'}`, 'Voice %', 'Data %', 'Points lost'],
            group.rows.map(row => [
              `${row.location}${row.note ? ` ${row.note}` : ''}`, owner(row), share(row.percent),
              {text: row.delta === null || row.delta === undefined ? '–' : signedPoints(row.delta, 0), className: `scoring-insight-number ${toneClass(row.delta)}`},
              share(row.voice_percent), share(row.data_percent),
              {text: insightNumber(row.lost, 1), className: 'scoring-insight-bar-cell scoring-stake-cell', bar: {ratio: row.lost / peak, color: activeTheme?.ink || '#475569'}},
            ]), {className: 'scoring-places-table'}));
          section.append(wrap);
        }
        section.append(insightParagraph('scoring-insight-note', 'Colour: 85% or more in the High colour, 75–85% Medium, under 75% Low. ',
          'vs previous: change in Points % since the previous campaign (–: not measured then). Points lost: one bar scale on every ranking.'));
      }
    }
    // The route that loses most, for every operator chosen with operator buttons of its own (as the other sections, the
    // Focus operators by default), whatever the operator of Where to act; the Route among those of the chosen operators.
    if (routes.length) {
      const {control: routeChips, chosen: routeChosen} = insightOperatorChips('route-operators', routes);
      const shown = routes.filter(item => routeChosen.includes(item.operator));
      const totals = new Map();
      for (const item of shown) for (const entry of item.routes) totals.set(entry.route, (totals.get(entry.route) || 0) + entry.points);
      const routeOptions = [...totals].sort((left, right) => right[1] - left[1]).map(([name, points]) => [name, `${name} (${insightNumber(points, 1)})`]);
      const {wrapper: routeControl, value: chosenRoute} = insightSelect('act-route', routeOptions, 'Route');
      const routeName = totals.has(chosenRoute) ? chosenRoute : routeOptions[0]?.[0];
      const section = insightSection(later, `${routeName}: where the points are`, 'scoring-route-card', (shown[0] || routes[0]).context);
      section.append(insightControls(routeChips, routeControl));
      for (const focus of shown) {
        const card = document.createElement('div');
        card.className = 'scoring-route-operator';
        const banner = document.createElement('div');
        banner.className = 'scoring-insight-banner';
        const color = safeHexColor(focus.color);
        if (color) banner.style.setProperty('--banner-color', color);
        const route = focus.routes.find(item => item.route === routeName);
        banner.append(insightStrong(focus.label), route ? ` · ${insightNumber(route.points, 1)} points lost on ${route.route}` : '');
        card.append(banner);
        section.append(card);
        if (!route) {
          card.append(insightParagraph('scoring-insight-note', `${routeName} is not among the routes where ${focus.label} loses most points.`));
          continue;
        }
        card.append(insightParagraph('scoring-act-headline', route.headline));
        const body = document.createElement('div');
        body.className = 'scoring-route-focus';
        const map = makeOwnerRouteMap(route, ownerColor);
        const side = document.createElement('div');
        side.className = 'scoring-route-side';
        const ownerPeak = Math.max(0.01, ...route.owners.map(item => item.points));
        side.append(insightParagraph('scoring-route-table-title', 'Points lost by owner'),
          insightTable(['Owner', 'Share of tests', 'Points'], route.owners.map(item => [
            pill(item.name), item.tests_share === null || item.tests_share === undefined ? '–' : {text: `${insightNumber(item.tests_share, 0)}%`, className: 'scoring-insight-number'},
            gapBarCell(item.points, ownerPeak, {loss: true, total: true})])),
          insightParagraph('scoring-route-table-title', `The ${route.top.length} stretches with the most points`));
        const stretchTable = insightTable(['#', 'Stretch', 'Points', 'Main owner'], route.top.map((row, index) => [
          {text: String(index + 1), className: 'scoring-insight-number'}, row.label, gapBarCell(row.points, route.top[0]?.points || 1, {loss: true, total: true}),
          row.region ? pill(row.region) : '—']));
        side.append(stretchTable);
        body.append(linkStretchTable(map, stretchTable, route.top), side);
        card.append(body);
        if (route.review) card.append(insightParagraph('scoring-act-review', insightStrong('Please review: '), route.review));
      }
      section.append(insightParagraph('scoring-insight-note', 'A stretch gathers the tests of the route within about 20 km, named after the nearest city of the measurements; ',
        'circle area and colour (yellow to red): points lost; its ring: the colour of its owner.'));
    }
  }

  // The Points Lost tab at one of its sections (a Deep-dive of Where to act): Points lost per KPI, Sites to review or the
  // Connecting Roads stretches, kept at the top while the tab is drawn.
  const pointsLostSections = {'points-kpi': '.scoring-points-kpi-card', sites: '.scoring-sites-card', stretches: '.scoring-stretches-card'};
  function openPointsLostSection(section) {
    root.querySelector('[data-result-tab="points"]')?.click();
    const find = () => root.querySelector(`[data-result-pane="points"] ${pointsLostSections[section] || ''}`);
    let tries = 0;
    const show = () => {
      const target = find();
      // A section drawn once its data arrives (the sites and the stretches) is waited for a few seconds.
      if (!target) {
        if ((tries += 1) < 50) window.setTimeout(show, 100);
        return;
      }
      if (typeof showSectionAtTop === 'function') {
        showSectionAtTop(target);
        keepSectionInView(target, find);
      } else target.scrollIntoView({block: 'start'});
    };
    window.setTimeout(show, 0);
  }

  // The map of a route of Where to act, drawn as the map of the Points Lost routes (makeStretchMap): its stretches with the
  // most points lost numbered, and the owner of each stretch as the ring of its circle.
  function makeOwnerRouteMap(route, ownerColor) {
    if (![...(route.path || []), ...route.all_stretches].length) return document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    return makeStretchMap(route, '#64748b', [], {ranked: route.top, ringColor: ownerColor, measure: 'points lost',
      className: 'scoring-stretch-map scoring-owner-route-map'});
  }

  function sameScope(left, right) {
    const clean = context => JSON.stringify(Object.fromEntries(Object.entries(context || {}).filter(([field]) => field !== 'campaign').sort()));
    return clean(left) === clean(right);
  }

  function makeStandingsLeaderboard(standing) {
    const list = document.createElement('div');
    list.className = 'scoring-leaderboard';
    for (const row of standing.operators) {
      const color = safeHexColor(row.color) || '#475569';
      const item = document.createElement('div');
      item.className = `scoring-leaderboard-row${row.is_reference ? ' is-reference' : ''}`;
      const rank = insightStrong(ordinalText(row.rank));
      rank.className = 'scoring-leaderboard-rank';
      rank.style.setProperty('--operator-color', color);
      const name = insightStrong(`${row.label}${row.is_reference ? ' (reference)' : ''}`);
      name.className = 'scoring-leaderboard-name';
      const bar = document.createElement('span');
      bar.className = 'scoring-leaderboard-bar';
      const data = document.createElement('i');
      data.style.width = `${Math.max(0, row.data) / standing.maximum * 100}%`;
      data.style.background = insightDataColor;
      const voice = document.createElement('i');
      voice.style.width = `${Math.max(0, row.voice) / standing.maximum * 100}%`;
      voice.style.background = insightVoiceColor;
      bar.append(data, voice);
      bar.title = `${row.label}: Data ${insightNumber(row.data, 1)} · Voice ${insightNumber(row.voice, 1)}`;
      const total = insightStrong(`${insightNumber(row.total, 1)}${row.complete ? '' : '*'}`);
      total.className = 'scoring-leaderboard-total';
      const delta = document.createElement('span');
      delta.className = `scoring-leaderboard-delta ${toneClass(row.delta)}`;
      delta.textContent = row.delta === null || row.delta === undefined ? '' : `${signedPoints(row.delta)} vs ${standing.previous_campaign}`;
      item.append(rank, name, bar, total, delta);
      list.append(item);
    }
    // The colours of Data and Voice in the theme, as small swatches in the note.
    const swatch = color => Object.assign(document.createElement('i'), {className: 'scoring-note-swatch', style: `background:${color}`});
    const legend = insightParagraph('scoring-insight-note', swatch(insightDataColor), ' Data\u2003', swatch(insightVoiceColor),
      ` Voice\u2003·\u2003Points of ${insightNumber(standing.maximum)}`);
    const box = document.createElement('div');
    box.append(list, legend);
    return box;
  }

  function makeStandingTiles(standing, row) {
    const color = safeHexColor(row.color) || '#475569';
    const box = document.createElement('div');
    box.className = 'scoring-standing';
    box.style.setProperty('--operator-color', color);
    const tile = (label, value, detail, tone = '') => {
      const element = document.createElement('div');
      element.className = `scoring-standing-tile ${tone}`.trim();
      element.append(insightParagraph('scoring-standing-label', label), insightParagraph(`scoring-standing-value ${tone}`.trim(), value),
        insightParagraph('scoring-standing-detail', detail));
      return element;
    };
    const tiles = document.createElement('div');
    tiles.className = 'scoring-standing-tiles';
    tiles.append(tile(row.label, insightNumber(row.total, 1), `${ordinalText(row.rank)} of ${row.of} · of ${insightNumber(standing.maximum)} points`));
    if (row.gap_to_reference !== null && row.gap_to_reference !== undefined) {
      tiles.append(tile(`GAP to ${standing.reference_label}`, signedPoints(row.gap_to_reference),
        `Data ${signedPoints(row.data_gap)} · Voice ${signedPoints(row.voice_gap)}`, toneClass(row.gap_to_reference)));
    }
    // The operators around it, unless one of them is the reference, whose GAP is already shown.
    const shownReference = row.gap_to_reference !== null && row.gap_to_reference !== undefined;
    if (row.rank > 1 && !(shownReference && row.above_label === standing.reference_label)) {
      tiles.append(tile(`Behind ${row.above_label}`, signedPoints(row.gap_to_above), `${signedPoints(row.gap_to_leader)} to the leader`, 'is-loss'));
    }
    if (row.below_label && !(shownReference && row.below_label === standing.reference_label)) {
      tiles.append(tile(`Ahead of ${row.below_label}`, signedPoints(row.lead_over_below), row.rank === 1 ? 'Leader' : 'Lead to defend', 'is-gain'));
    }
    if (row.rank === 1 && shownReference && row.below_label === standing.reference_label) {
      tiles.append(tile('Position', 'Leader', `${signedPoints(row.lead_over_below)} over ${row.below_label}`, 'is-gain'));
    }
    const parts = Object.entries(row.parts || {});
    const partsBox = document.createElement('div');
    partsBox.className = 'scoring-standing-parts';
    if (parts.length && row.gap_to_reference !== null && row.gap_to_reference !== undefined) {
      const scale = Math.max(...parts.map(([, value]) => Math.abs(value)), 1);
      partsBox.append(insightParagraph('scoring-standing-label', `GAP to ${standing.reference_label} by part`));
      for (const [name, value] of parts) {
        const line = document.createElement('div');
        line.className = 'scoring-standing-part';
        line.append(insightParagraph('', name), divergingBar(value, scale));
        partsBox.append(line);
      }
    }
    box.append(tiles, partsBox, insightParagraph('scoring-standing-takeaway', row.takeaway));
    return box;
  }

  function makePositionMatrix(matrix, style) {
    const color = safeHexColor(style.color) || '#475569';
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-position';
    const title = insightStrong(style.label, color);
    title.className = 'scoring-position-title';
    const table = document.createElement('table');
    table.className = 'scoring-position-table';
    const services = ['Voice', 'Data', 'Overall'].filter(service => matrix.rows.some(row => row.cells[service]));
    const head = table.createTHead().insertRow();
    for (const text of ['', ...services]) head.append(Object.assign(document.createElement('th'), {textContent: text}));
    const body = table.createTBody();
    for (const row of matrix.rows) {
      const line = body.insertRow();
      if (row.environment === 'Combined') line.className = 'is-combined';
      line.append(Object.assign(document.createElement('th'), {textContent: row.environment === 'Combined' ? 'All Environments' : environmentLabel(row.environment)}));
      for (const service of services) {
        const cell = line.insertCell();
        const value = row.cells[service]?.[style.operator];
        if (!value) { cell.textContent = '—'; continue; }
        const rankIndex = value.rank === 1 ? 0 : value.rank === value.of ? 3 : value.rank === 2 ? 1 : 2;
        const tile = document.createElement('span');
        tile.className = 'scoring-position-tile';
        tile.style.setProperty('--rank-color', insightRankColors[rankIndex]);
        tile.textContent = `${ordinalText(value.rank)} · ${insightNumber(value.percent, 0)}%`;
        const missed = document.createElement('span');
        missed.className = 'scoring-position-missed';
        const bar = document.createElement('i');
        bar.style.width = `${Math.min(100, value.missed / Math.max(1, value.maximum) * 100)}%`;
        missed.append(bar, document.createTextNode(`${insightNumber(value.missed, 1)} / ${insightNumber(value.maximum, 0)}`));
        cell.title = `${style.label} · ${environmentLabel(row.environment)} · ${service}: ${ordinalText(value.rank)} of ${value.of}, ${insightNumber(value.points, 1)} of ${insightNumber(value.maximum, 1)} points`;
        cell.append(tile, missed);
      }
    }
    wrapper.append(title, table);
    return wrapper;
  }

  function makeLeversTable(item) {
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-insight-table-wrap';
    const banner = document.createElement('div');
    banner.className = 'scoring-insight-banner';
    const color = safeHexColor(item.color);
    if (color) banner.style.setProperty('--banner-color', color);
    banner.append(insightStrong(item.label), ` · ${insightNumber(-item.total_behind, 1)} points behind ${item.reference_label} in ${item.count} KPIs`);
    const scale = Math.max(...item.levers.map(row => Math.abs(row.gap)), 0);
    wrapper.append(banner, insightTable(['KPI', item.label, item.reference_label, 'Points to win'], item.levers.map(row => [
      {text: `${row.kpi} · ${row.category}`, title: `${row.service} · ${row.category}`},
      {text: insightNumber(row.value, 2), className: 'scoring-insight-number'},
      {text: insightNumber(row.reference_value, 2), className: 'scoring-insight-number'},
      {...gapBarCell(-row.gap, scale, {loss: true, total: true}), text: insightNumber(-row.gap, 2)},
    ])));
    return wrapper;
  }

  function makeCampaignScope(scope, {nrModes = false, testScopes = []} = {}) {
    const box = document.createElement('div');
    box.className = 'scoring-scope';
    // A detail given as a list has a line per item (each environment with its points).
    const tile = (label, value, detail) => {
      const element = document.createElement('div');
      element.className = 'scoring-scope-tile';
      const lines = Array.isArray(detail) ? detail : [detail];
      element.append(insightParagraph('scoring-standing-label', label), insightParagraph('scoring-scope-value', value),
        ...lines.map(line => insightParagraph('scoring-standing-detail', line)));
      return element;
    };
    const tiles = document.createElement('div');
    tiles.className = 'scoring-scope-tiles';
    const window_ = scope.window;
    // Below the reference (the latest campaign; with NSA vs SA, the latest NSA and SA campaigns), the other campaigns
    // analysed, the newest first.
    const isSa = campaign => /(^|[_\- ])SA($|[_\- ])/i.test(String(campaign || ''));
    const latest = nrModes
      ? [scope.campaigns.filter(campaign => !isSa(campaign)).at(-1), scope.campaigns.filter(isSa).at(-1)].filter(Boolean)
      : [scope.latest_campaign].filter(Boolean);
    const otherCampaigns = scope.campaigns.filter(campaign => !latest.includes(campaign)).reverse();
    tiles.append(tile('Campaigns', latest.join(' · ') || '—', otherCampaigns.length ? `+${otherCampaigns.length} campaign${otherCampaigns.length === 1 ? '' : 's'}: ${otherCampaigns.join(', ')}` : (latest.length > 1 ? 'One campaign each' : 'One campaign')));
    if (window_) tiles.append(tile('Measurements', `${window_.first} → ${window_.last}`, `${window_.days} days with tests`));
    if (scope.places) tiles.append(tile('Places', `${scope.places.cities} cities`, `${scope.places.routes} Connecting Roads routes`));
    const environments = scope.environments.filter(item => item.max_points > 0);
    tiles.append(tile('Environments', `${environments.length}`, environments.map(item => `${item.label} ${insightNumber(item.max_points)} pts`)));
    box.append(tiles);
    // The tests of the latest campaign (with NSA vs SA, of the latest campaign of each NR Mode, each tagged).
    for (const {mode, scope: source} of testScopes.length ? testScopes : [{mode: null, scope}]) {
      const kinds = ['data', 'voice', 'speech'];
      const names = [...new Set(Object.values(source.tests || {}).flatMap(byKind => Object.values(byKind).flatMap(byEnvironment => Object.keys(byEnvironment))))];
      const rows = source.operators.filter(style => source.tests?.[style.operator]).map(style => [
        {text: style.label, style: {color: safeHexColor(style.color) || '#263746', fontWeight: 800}},
        ...kinds.flatMap(kind => names.map(name => ({text: insightNumber(source.tests[style.operator]?.[kind]?.[name] || 0), className: 'scoring-insight-number'}))),
      ]);
      if (!rows.length) continue;
      const table = insightTable(['Operator', ...kinds.flatMap(kind => names.map(name => `${{data: 'Data tests', voice: 'Calls', speech: 'Speech samples'}[kind]} · ${shortEnvironmentLabel(name)}`))], rows);
      const wrap = document.createElement('div');
      wrap.className = 'scoring-insight-table-wrap';
      wrap.append(table);
      box.append(insightParagraph('scoring-insight-note', ...(mode ? [nrModeTag(mode)] : []), `Tests of each operator in ${(source.tests_campaign !== undefined ? source.tests_campaign : source.latest_campaign) || 'the measurements'}: the CDR Data tests, the Voice calls and the Speech samples scored in each environment.`), wrap);
    }
    return box;
  }

  // ---- Geographical Areas ------------------------------------------------------------------------------------------
  // A calculation split by no Region, Cluster or City shows each Region and London (calculated with it).
  // The levels of the Geographical Areas from the largest to the smallest: the whole country, then Region, Cluster and City.
  const GEOGRAPHICAL_LEVEL_ORDER = {National: 0, Region: 1, Cluster: 2, City: 3};
  const geographicalLevelRank = level => GEOGRAPHICAL_LEVEL_ORDER[level] ?? 4;

  function renderGeographicalAreas(pane, payload, environment) {
    pane.replaceChildren();
    if (!environment) return;
    let groups = [...insightItems(payload, 'location_cards', environment)]
      .sort((left, right) => geographicalLevelRank(left.level) - geographicalLevelRank(right.level));
    const campaigns = [...new Set(groups.map(group => group.campaign).filter(Boolean))];
    if (campaigns.length > 1) {
      const latest = campaigns.sort((left, right) => insightCampaignKey(left) - insightCampaignKey(right)).at(-1);
      groups = groups.filter(group => !group.campaign || group.campaign === latest);
    }
    for (const group of groups) {
      // The scoring Nationwide (the card of the whole country) comes first, then each Region, Cluster and City.
      pane.append(makeExpandableChartCard(group.level === 'National' ? `${scoringLabel()} Scoring Nationwide` : `${scoringLabel()} Scoring per ${group.level}`,
        [environmentLabel(environment), group.title].filter(Boolean).join(' · '), makeLocationCardsView(group)));
    }
    const rankings = insightItems(payload, 'location_rankings', environment);
    if (rankings.length) {
      // From the largest level to the smallest (Region, Cluster, City), the largest chosen by default.
      const levels = [...new Set(rankings.map(item => item.level))]
        .sort((left, right) => geographicalLevelRank(left) - geographicalLevelRank(right));
      const {wrapper: levelControl, value: storedLevel} = insightSelect('ranking-level', levels.map(level => [level, level]), 'Geographical Areas');
      const level = levels.includes(storedLevel) ? storedLevel : levels[0];
      const ofLevel = rankings.filter(item => item.level === level);
      const titles = [...new Set(ofLevel.map(item => item.title || ''))];
      const {wrapper: groupControl, value: storedGroup} = insightSelect('ranking-group', titles.map(title => [title, title || 'All']), 'Group');
      const title = titles.includes(storedGroup) ? storedGroup : titles[0];
      const inGroup = ofLevel.filter(item => (item.title || '') === title);
      const {control: chips, chosen} = insightOperatorChips('ranking-operators', inGroup);
      const words = locationWords(level, inGroup.flatMap(item => item.rows));
      const section = insightSection(pane, `${words.title} ranked${inGroup[0]?.campaign ? ` — ${inGroup[0].campaign}` : ''}`, 'scoring-ranking-card', inGroup[0]?.context);
      section.append(insightControls(levels.length > 1 ? levelControl : null, titles.length > 1 ? groupControl : null, chips));
      for (const item of inGroup.filter(entry => chosen.includes(entry.operator))) section.append(makeRankingTable(item));
      section.append(insightParagraph('scoring-insight-note', `Points %: the share of the points available in each ${words.one} (its environments scaled to the full maximum); `,
        'Δ: the change since the previous campaign in points of percentage; the bar of Points lost shares one scale per table.'));
      const versus = inGroup.filter(entry => chosen.includes(entry.operator) && !entry.is_reference && entry.rows.some(row => row.gap !== null));
      if (versus.length) {
        const compare = insightSection(pane, `Each operator against ${versus[0].reference_label} per ${words.one}`, 'scoring-versus-card', versus[0].context);
        for (const item of versus) compare.append(makeVersusTable(item));
        compare.append(insightParagraph('scoring-insight-note', `The GAP in points of percentage of the points available: to the left the operator trails ${versus[0].reference_label}, to the right it is ahead.`));
      }
    }
    if (!pane.children.length) {
      // The location views split the scoring by location: without one in the Split by there is nothing to show.
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No Geographical Areas views: calculate the scoring again to see them per Region and for London '
        + '(results calculated before them do not have them), or add Region, Cluster or City to the Split by. '
        + 'The National & Geographical Areas Trends are in the Scoring Trends tab.';
      pane.append(empty);
    }
  }

  // The words of a level of the Geographical Areas (Region, Cluster or City), for the titles, headers and notes of its
  // tables: the City level names the Connecting Roads routes too when its rows have them.
  function locationWords(level, rows = []) {
    if (level === 'City' && rows.some(row => row.kind === 'route')) {
      return {name: 'City', one: 'city or route', many: 'cities and routes', title: 'Cities and routes'};
    }
    return {
      Region: {name: 'Region', one: 'region', many: 'regions', title: 'Regions'},
      Cluster: {name: 'Cluster', one: 'cluster', many: 'clusters', title: 'Clusters'},
      City: {name: 'City', one: 'city', many: 'cities', title: 'Cities'},
    }[level] || {name: 'Location', one: 'location', many: 'locations', title: 'Locations'};
  }

  function makeRankingTable(item) {
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-insight-table-wrap';
    const banner = document.createElement('div');
    banner.className = 'scoring-insight-banner';
    const color = safeHexColor(item.color);
    if (color) banner.style.setProperty('--banner-color', color);
    const lost = item.rows.reduce((sum, row) => sum + row.lost, 0);
    const words = locationWords(item.level, item.rows);
    banner.append(insightStrong(item.label), ` · ${item.rows.length} ${words.many}${item.title ? ` · ${item.title}` : ''}`);
    const peak = Math.max(...item.rows.map(row => row.lost), 0);
    const hasVendors = item.rows.some(row => row.vendors?.length);
    const rows = item.rows.map((row, index) => [
      {text: String(index + 1), className: 'scoring-insight-number'},
      {text: `${row.location}${row.kind === 'route' ? ' (route)' : ''}`, className: 'scoring-insight-kpi'},
      ...(hasVendors ? [{text: (row.vendors || []).map(vendor => `${vendor.name} ${insightNumber(vendor.share, 0)}%`).join(' · '), className: 'scoring-ranking-vendors'}] : []),
      {text: `${insightNumber(row.percent, 1)}%${row.complete ? '' : '*'}`, className: 'scoring-insight-number scoring-insight-total',
        bar: {ratio: Math.min(1, row.percent / 100), color: color || '#475569'}},
      {text: signedPoints(row.delta), className: `scoring-insight-number ${toneClass(row.delta)}`},
      {text: row.voice_percent === null ? '—' : `${insightNumber(row.voice_percent, 1)}%`, className: 'scoring-insight-number'},
      {text: row.data_percent === null ? '—' : `${insightNumber(row.data_percent, 1)}%`, className: 'scoring-insight-number'},
      gapBarCell(row.lost, peak, {loss: true}),
    ]);
    const table = insightTable(['#', words.name, ...(hasVendors ? ['Vendors (share of tests)'] : []), 'Points %',
      item.previous_campaign ? `Δ vs ${item.previous_campaign}` : 'Δ', 'Voice %', 'Data %', 'Points lost'], rows, {className: 'scoring-ranking-table'});
    table.querySelectorAll('td.scoring-insight-total').forEach(cell => cell.classList.add('scoring-insight-bar-cell'));
    wrapper.append(banner, table, insightParagraph('scoring-insight-note', `${item.label} loses ${insightNumber(lost, 1)} points in these ${words.many}, scaled to ${insightNumber(item.rows[0]?.maximum || 0)} each.`));
    return wrapper;
  }

  function makeVersusTable(item) {
    const wrapper = document.createElement('div');
    wrapper.className = 'scoring-insight-table-wrap';
    const banner = document.createElement('div');
    banner.className = 'scoring-insight-banner';
    const color = safeHexColor(item.color);
    if (color) banner.style.setProperty('--banner-color', color);
    banner.append(insightStrong(item.label), ` minus ${item.reference_label}`);
    const rows = item.rows.filter(row => row.gap !== null).sort((left, right) => left.gap - right.gap);
    const scale = Math.max(...rows.flatMap(row => [row.gap, row.voice_gap, row.data_gap].map(value => Math.abs(Number(value) || 0))), 1);
    wrapper.append(banner, insightTable([locationWords(item.level, item.rows).name, 'Points %', 'Voice %', 'Data %', item.label, item.reference_label],
      rows.map(row => [row.location, divergingBar(row.gap, scale), divergingBar(row.voice_gap, scale), divergingBar(row.data_gap, scale),
        {text: `${insightNumber(row.percent, 1)}%`, className: 'scoring-insight-number'},
        {text: `${insightNumber(row.reference_percent, 1)}%`, className: 'scoring-insight-number'}]), {className: 'scoring-versus-table'}));
    return wrapper;
  }

  // ---- GAP Analysis: the GAP of each part of the scoring over the campaigns ----------------------------------------
  function renderGapParts(pane, payload, environment) {
    const items = insightItems(payload, 'gap_parts', environment);
    if (!items.length) return;
    const {control: scopeControl, inScope, context} = insightScopeControl('gap-parts-scope', items);
    const {control: chips, chosen} = insightOperatorChips('gap-parts-operators', inScope);
    const byReliability = inScope[0]?.by_reliability;
    const section = insightSection(pane, 'GAP by part of the scoring over the campaigns', 'scoring-gap-parts-card', context);
    section.append(insightControls(scopeControl, chips));
    const grid = document.createElement('div');
    // Two tables a row at most, so their campaigns and Latest bars fit.
    grid.className = 'scoring-insight-pair scoring-gap-parts-grid';
    for (const item of inScope.filter(entry => chosen.includes(entry.operator))) {
      const wrapper = document.createElement('div');
      wrapper.className = 'scoring-insight-table-wrap';
      const banner = document.createElement('div');
      banner.className = 'scoring-insight-banner';
      const color = safeHexColor(item.color);
      if (color) banner.style.setProperty('--banner-color', color);
      banner.append(insightStrong(item.label), ` minus ${item.reference_label}`);
      const values = [...item.parts.flatMap(part => part.values), ...item.totals].filter(value => value !== null && value !== undefined);
      const scale = Math.max(...values.map(value => Math.abs(value)), 1);
      const latest = item.campaigns.length - 1;
      const cell = (value, index, total = false) => {
        if (value === null || value === undefined) return {text: '—', className: 'scoring-insight-number'};
        const alpha = Math.min(1, Math.abs(value) / scale) * .55;
        return {text: signedPoints(value), className: `scoring-insight-number${total ? ' scoring-insight-total' : ''}${index === latest ? ' is-latest' : ''}`,
          style: {background: rgbaOf(value < 0 ? insightLossColor : insightGainColor, alpha)}};
      };
      const headers = ['Part', ...item.campaigns.map(campaign => campaign || 'GAP'), ...(item.campaigns.length > 1 ? ['Latest'] : [])];
      const rows = item.parts.map(part => [part.label, ...part.values.map((value, index) => cell(value, index)),
        ...(item.campaigns.length > 1 ? [divergingBar(part.values[latest], scale)] : [])]);
      const total = [insightTotalLabel(), ...item.totals.map((value, index) => cell(value, index, true)),
        ...(item.campaigns.length > 1 ? [divergingBar(item.totals[latest], scale)] : [])];
      wrapper.append(banner, insightTable(headers, rows, {className: 'scoring-gap-parts-table', total}));
      grid.append(wrapper);
    }
    section.append(grid, insightParagraph('scoring-insight-note', byReliability
      ? 'Reliability: the KPIs typed Reliable (calls and tests that complete, POLQA below 1.6, throughput above 2 or 1 Mbit/s); quality: the others (speeds, times, speech quality and the higher thresholds). '
      : 'Each part is a category of KPIs. ', 'The total is the GAP of the whole scoring; red: behind the reference, green: ahead.'));
  }

  // ---- Points Lost --------------------------------------------------------------------------------------------------
  function renderPointsLost(pane, payload, environment, savedFilterId) {
    pane.replaceChildren();
    if (!environment) return;
    renderPointsAtStake(pane, payload, environment);
    renderPointsPerKpi(pane, payload, environment);
    renderPointsLossMaps(pane, payload, environment, savedFilterId);
    const pending = payload.points_loss_pending;
    renderServingLosses(pane, payload, environment, 'vendor_losses', 'Points lost per Vendor of the serving cell', 'Vendor', pending);
    renderServingLosses(pane, payload, environment, 'site_type_losses', 'Points lost per kind of serving site', 'Kind of site', pending);
    renderSitesToReview(pane, payload, environment, pending);
    renderRouteStretches(pane, payload, environment, pending);
    if (!pane.childElementCount) {
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = 'No points lost are available for this environment.';
      pane.append(empty);
    }
  }

  function renderPointsAtStake(pane, payload, environment) {
    const items = insightItems(payload, 'points_at_stake', environment);
    if (!items.length) return;
    const {control: scopeControl, inScope, context} = insightScopeControl('stake-scope', items);
    const item = inScope[0];
    const section = insightSection(pane, `Where the points go${item.campaign ? ` — ${item.campaign}` : ''}`, 'scoring-stake-card', context);
    section.append(insightControls(scopeControl));
    // The kinds that hold KPIs or points (Most Reliable scores only the Reliable KPIs).
    const kinds = item.kinds.filter(kind => (kind.kpis || [null]).length || item.operators.some(row => row.parts[kind.key]));
    const [notCompletedColour, minimumColour, belowColour, qualityColour] = activeTheme.stake || ['#6e1222', '#a51c30', '#e8414f', '#f4a3aa'];
    const colours = {not_completed: notCompletedColour, below_minimum: minimumColour, below_par: belowColour, quality: qualityColour};
    const peak = Math.max(...item.operators.map(row => row.lost), 1);
    const list = document.createElement('div');
    list.className = 'scoring-stake';
    for (const row of item.operators) {
      const line = document.createElement('div');
      line.className = 'scoring-stake-row';
      const name = insightStrong(`${row.label}${row.is_reference ? ' (reference)' : ''}`, safeHexColor(row.color));
      const bar = document.createElement('span');
      bar.className = 'scoring-stake-bar';
      for (const kind of kinds) {
        const segment = document.createElement('i');
        segment.style.width = `${row.parts[kind.key] / peak * 100}%`;
        segment.style.background = colours[kind.key];
        segment.title = `${kind.label}: ${insightNumber(row.parts[kind.key], 1)} points${(row.kpis?.[kind.key] || []).length
          ? `\n${row.kpis[kind.key].map(kpi => `${kpi.kpi} (${kpi.service}): ${insightNumber(kpi.lost, 1)}`).join('\n')}` : ''}`;
        if (row.parts[kind.key] / peak > .08) segment.textContent = insightNumber(row.parts[kind.key], 0);
        bar.append(segment);
      }
      const total = insightStrong(`${insightNumber(row.lost, 1)} lost`);
      total.className = 'scoring-stake-total';
      line.append(name, bar, total);
      list.append(line);
    }
    const legend = document.createElement('div');
    legend.className = 'scoring-location-legend';
    legend.innerHTML = kinds.map(kind => `<span><i style="background:${colours[kind.key]}"></i>${kind.label}</span>`).join('');
    const table = insightTable(['Operator', ...kinds.map(kind => kind.label), 'Points lost', 'Points'], item.operators.map(row => [
      {text: row.label, style: {color: safeHexColor(row.color) || '#263746', fontWeight: 800}},
      ...kinds.map(kind => ({text: insightNumber(row.parts[kind.key], 1), className: 'scoring-insight-number',
        title: (row.kpis?.[kind.key] || []).map(kpi => `${kpi.kpi}: ${insightNumber(kpi.lost, 1)}`).join('\n')})),
      {text: insightNumber(row.lost, 1), className: 'scoring-insight-number scoring-insight-total'},
      {text: insightNumber(row.points, 1), className: 'scoring-insight-number'}]));
    const wrap = document.createElement('div');
    wrap.className = 'scoring-insight-table-wrap';
    wrap.append(table);
    // What each kind counts and the KPIs of the methodology it holds, each kind in its colour as in the bars (dark text
    // on the light colours).
    const textOn = colour => {
      const [red, green, blue] = [1, 3, 5].map(index => parseInt(String(colour).slice(index, index + 2), 16) / 255);
      return .2126 * red + .7152 * green + .0722 * blue > .55 ? '#17232d' : '#fff';
    };
    const definitions = insightTable(['Kind of loss', 'What it counts', 'KPIs'], kinds.map(kind => [
      {text: kind.label, className: 'scoring-loss-kind-label',
        style: {background: colours[kind.key], color: textOn(colours[kind.key]), fontWeight: 800}},
      {text: kind.description || '', className: 'scoring-loss-kind-text'},
      {text: (kind.kpis || []).join(', ') || '—', className: 'scoring-loss-kind-text'}]));
    const definitionsWrap = document.createElement('div');
    definitionsWrap.className = 'scoring-insight-table-wrap scoring-loss-kinds';
    definitionsWrap.append(definitions);
    section.append(list, legend, wrap, definitionsWrap, insightParagraph('scoring-insight-note',
      'Each KPI loses its points in one kind. Hover a bar for the KPIs that lose most.'));
  }

  function servingNotice(section, pending) {
    section.append(insightParagraph('scoring-insight-note', pending ? 'Preparing the Points Lost of the tests…'
      : 'Calculate the scoring again to share its points lost among the Vendors, kinds of site, sites and route stretches of the cells that served the tests (the CDRs need the serving cells of the Vendor Mapping).'));
  }

  function renderServingLosses(pane, payload, environment, kind, title, column, pending) {
    const items = insightItems(payload, kind, environment);
    const maps = insightItems(payload, 'points_loss_maps', environment);
    if (!items.length) {
      if (kind === 'vendor_losses' && (maps.length || pending)) servingNotice(insightSection(pane, title, 'scoring-serving-card'), pending);
      return;
    }
    const {control: scopeControl, inScope, context} = insightScopeControl(`${kind}-scope`, items, {withCampaign: true});
    const {control: chips, chosen} = insightOperatorChips(`${kind}-operators`, inScope);
    const section = insightSection(pane, title, 'scoring-serving-card', context);
    section.append(insightControls(scopeControl, chips));
    const grid = document.createElement('div');
    grid.className = 'scoring-insight-pair';
    for (const item of inScope.filter(entry => chosen.includes(entry.operator))) {
      const wrapper = document.createElement('div');
      wrapper.className = 'scoring-insight-table-wrap';
      const banner = document.createElement('div');
      banner.className = 'scoring-insight-banner';
      const color = safeHexColor(item.color);
      if (color) banner.style.setProperty('--banner-color', color);
      banner.append(insightStrong(item.label), ` · ${insightNumber(item.total, 1)} points lost`);
      const peak = Math.max(...item.rows.map(row => row.points), 0);
      const withTests = item.has_tests;
      const withCities = kind === 'vendor_losses' && item.rows.some(row => row.cities?.length);
      const withEnvironments = item.rows.some(row => row.environments?.length);
      const sum = field => item.rows.reduce((total, row) => total + (Number(row[field]) || 0), 0);
      const total = [insightTotalLabel(), insightTotalCell(sum('points'), {digits: 1}), insightTotalCell(sum('share'), {digits: 1, suffix: '%'}),
        ...(withTests ? [insightTotalCell(item.rows.some(row => row.tests_share !== null) ? sum('tests_share') : null, {digits: 1, suffix: '%'})] : []),
        ...(withEnvironments ? [''] : []), ...(withCities ? [''] : [])];
      wrapper.append(banner, insightTable([column, 'Points lost', 'Share of points', ...(withTests ? ['Share of tests'] : []),
        ...(withEnvironments ? ['Where'] : []), ...(withCities ? ['Cities and routes that lose most'] : [])], item.rows.map(row => [
        {text: row.name, className: row.identified ? 'scoring-insight-kpi' : 'scoring-insight-kpi is-muted'},
        gapBarCell(row.points, peak, {loss: true, total: true}),
        {text: `${insightNumber(row.share, 1)}%`, className: 'scoring-insight-number'},
        ...(withTests ? [{text: row.tests_share === null ? '—' : `${insightNumber(row.tests_share, 1)}%`,
          className: `scoring-insight-number ${row.tests_share !== null && row.share > row.tests_share * 1.25 && row.share - row.tests_share > 3 ? 'is-loss' : ''}`,
          title: 'Share of the tests of the operator served by it'}] : []),
        ...(withEnvironments ? [{text: (row.environments || []).map(name => shortEnvironmentLabel(name)).join(', '), className: 'scoring-loss-environment'}] : []),
        ...(withCities ? [(row.cities || []).map(city => `${city.name} ${insightNumber(city.points, 1)}`).join(' · ')] : []),
      ]), {total}));
      grid.append(wrapper);
    }
    section.append(grid, insightParagraph('scoring-insight-note', kind === 'vendor_losses'
      ? 'Each test belongs to the RAN Vendor of the cell that served its start (Not identified: no serving cell in the inventories). In red, a share of the points lost well above the share of the tests.'
      : 'The kind of each serving site: the network that owns it and, when another network hosts its RAN, "on" that network (Beacon, MORAN); NNS sites apart. In red, a share of the points lost well above the share of the tests.'));
  }

  function renderSitesToReview(pane, payload, environment, pending) {
    const items = insightItems(payload, 'sites_to_review', environment);
    // The operators none of whose serving cells is in the cell inventories have no site to review: a note says so.
    const unidentified = insightItems(payload, 'sites_unidentified', environment);
    if (!items.length && !unidentified.length) return;
    const {control: scopeControl, inScope, context} = insightScopeControl('sites-scope', items.length ? items : unidentified);
    const scopeKey = value => JSON.stringify(Object.fromEntries(Object.entries(value || {}).filter(([field]) => field !== 'campaign').sort()));
    const without = unidentified.filter(item => scopeKey(item.context) === scopeKey(context));
    const listed = items.length ? inScope : [];
    const {control: chips, chosen} = listed.length ? insightOperatorChips('sites-operators', listed) : {control: null, chosen: []};
    const campaign = (listed[0] || without[0])?.campaign;
    const section = insightSection(pane, `Sites to review${campaign ? ` — ${campaign}` : ''}`, 'scoring-sites-card', context);
    section.append(insightControls(scopeControl, chips));
    if (without.length) {
      section.append(insightParagraph('scoring-insight-note scoring-sites-unidentified', without.map(item => `${item.label}: none of the cells `
        + `that served its tests is in the cell inventories, so its ${insightNumber(item.unidentified, 1)} points lost cannot be `
        + 'assigned to sites (add its cells to the inventories of Workspace Config and process its CDRs again).').join(' ')));
    }
    for (const item of listed.filter(entry => chosen.includes(entry.operator))) {
      const wrapper = document.createElement('div');
      wrapper.className = 'scoring-insight-table-wrap';
      const banner = document.createElement('div');
      banner.className = 'scoring-insight-banner';
      const color = safeHexColor(item.color);
      if (color) banner.style.setProperty('--banner-color', color);
      const high = item.rows.filter(row => row.priority === 'High').length;
      banner.append(insightStrong(item.label), ` · ${item.rows.length} sites hold ${insightNumber(item.listed_points, 1)} of ${insightNumber(item.total, 1)} points lost · ${high} High`);
      const peak = Math.max(...item.rows.map(row => row.points), 0);
      // The total of the sites listed (the banner gives the points lost of the operator in all).
      const total = [insightTotalLabel(`Total of the ${item.rows.length} sites`, 5),
        insightTotalCell(item.rows.reduce((sum, row) => sum + (Number(row.points) || 0), 0), {digits: 1}),
        insightTotalCell(item.rows.reduce((sum, row) => sum + (Number(row.failures) || 0), 0), {digits: 0}),
        ...item.earlier_campaigns.map((_campaign, index) => insightTotalCell(
          item.rows.reduce((sum, row) => sum + (Number(row.history[index]?.points) || 0), 0), {digits: 1}))];
      wrapper.append(banner, insightTable(['Priority', 'Site', 'Network', 'Vendor', 'City or route', 'Points lost', 'Failed tests',
        ...item.earlier_campaigns.map(campaign => `${campaign} points`)], item.rows.map(row => [
        {text: row.priority, className: `scoring-priority is-${row.priority.toLowerCase()}`},
        {text: row.site, className: 'scoring-insight-kpi'}, row.network || '—', row.vendor || '—', row.city || '—',
        gapBarCell(row.points, peak, {loss: true, total: true}),
        {text: row.failures ? insightNumber(row.failures, 0) : '—', className: 'scoring-insight-number'},
        ...row.history.map(entry => ({text: entry.points ? insightNumber(entry.points, 1) : '—', className: 'scoring-insight-number'})),
      ]), {total}));
      section.append(wrapper);
    }
    if (!listed.length) return;
    section.append(insightParagraph('scoring-insight-note', `High: ${insightNumber(listed[0].priority_points, 0)}+ points lost and losses on the same site in an earlier campaign; Medium: one of the two; Low: neither. `,
      'Failed tests: the calls and tests that missed the Reliable KPIs (not completed, or completed below the minimum). Please review their cells: configuration, alarms and changes on the days of the measurements.'));
  }

  function renderRouteStretches(pane, payload, environment, pending) {
    const items = insightItems(payload, 'route_stretches', environment);
    if (!items.length) return;
    const {control: scopeControl, inScope, context} = insightScopeControl('stretches-scope', items, {withCampaign: true});
    // Every chosen operator at once, as the sections above: the stretches of each one on the route chosen.
    const {control: chips, chosen} = insightOperatorChips('stretches-operators', inScope);
    const shown = inScope.filter(item => chosen.includes(item.operator));
    // The routes of those operators, the route where they lose most first.
    const totals = new Map();
    for (const item of shown) for (const route of item.routes) totals.set(route.route, (totals.get(route.route) || 0) + route.points);
    const routes = [...totals].sort((left, right) => right[1] - left[1]).map(([name, points]) => [name, `${name} (${insightNumber(points, 1)})`]);
    const {wrapper: routeControl, value: storedRoute} = insightSelect('stretches-route', routes, 'Route');
    const routeName = totals.has(storedRoute) ? storedRoute : routes[0]?.[0];
    const section = insightSection(pane, 'Connecting Roads: where along each route the points are', 'scoring-stretches-card', context);
    // The Route below the Campaign, the operators beside them.
    const selectors = document.createElement('div');
    selectors.className = 'scoring-stacked-selectors';
    selectors.append(...[scopeControl, routeControl].filter(Boolean));
    section.append(insightControls(selectors, chips));
    const grid = document.createElement('div');
    grid.className = `scoring-insight-pair scoring-stretches-grid${shown.length > 1 ? ' is-multiple' : ''}`;
    for (const item of shown) {
      const color = safeHexColor(item.color) || '#7c3aed';
      const card = document.createElement('div');
      card.className = 'scoring-stretches-operator';
      const banner = document.createElement('div');
      banner.className = 'scoring-insight-banner';
      banner.style.setProperty('--banner-color', color);
      const route = item.routes.find(entry => entry.route === routeName);
      if (!route) {
        banner.append(insightStrong(item.label));
        card.append(banner, insightParagraph('scoring-insight-note', `${routeName} is not among the routes where ${item.label} loses most points.`));
        grid.append(card);
        continue;
      }
      banner.append(insightStrong(item.label), ` · ${insightNumber(route.points, 1)} points lost on ${route.route}`);
      const body = document.createElement('div');
      body.className = 'scoring-stretches';
      const peak = Math.max(...route.stretches.map(row => row.points), 0);
      const table = insightTable(['#', 'Stretch', 'Points lost', 'Main Vendor'], route.stretches.map((row, index) => [
        {text: String(index + 1), className: 'scoring-insight-number'}, row.label, gapBarCell(row.points, peak, {loss: true, total: true}), row.vendor || '—']),
      {total: [insightTotalLabel(`Total of the ${route.stretches.length} stretches`, 2),
        insightTotalCell(route.stretches.reduce((sum, row) => sum + (Number(row.points) || 0), 0), {digits: 1}), '']});
      body.append(linkStretchTable(makeStretchMap(route, color, payload?.views?.insights?.points_loss_background || []), table, route.stretches));
      const wrap = document.createElement('div');
      wrap.className = 'scoring-insight-table-wrap';
      wrap.append(insightParagraph('scoring-insight-note', 'The stretches with most of them:'), table);
      body.append(wrap);
      card.append(banner, body);
      grid.append(card);
    }
    section.append(grid, insightParagraph('scoring-insight-note', 'A stretch gathers the tests of the route within about 20 km, named after the nearest city of the measurements; circle area and colour (yellow to red): points lost.'));
  }


  // The colour of a stretch by its share of the points of the stretch that loses most: from the third colour of the
  // quality scale of the theme (yellow, little lost) through its second (orange) to its first (red, the most lost), as
  // in the exports (scoring_summary_slides.stretch_colour).
  function stretchColour(share) {
    const scale = activeTheme.scale || ['#C9483F', '#E8A060', '#F2D06B'];
    const value = Math.max(0, Math.min(1, share));
    return value <= .5 ? blendHex(scale[2], scale[1], value * 2) : blendHex(scale[1], scale[0], (value - .5) * 2);
  }

  // The map of a route: the map areas as the land (else the other tests in grey), the route in the colour of the
  // operator, the measured cities around it named, and a circle per stretch whose area and colour (yellow to red, on
  // the scale of the theme) tell its points lost; the stretches that lose most (ranked) are numbered and named after
  // their nearest city. With ringColor, each circle is ringed in the colour of the owner of its stretch (Where to act).
  function makeStretchMap(route, color, background, {ranked = route.stretches, ringColor = null, measure = 'points lost',
    className = 'scoring-stretch-map'} = {}) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const width = 560, height = 460, margin = 30;
    const points = [...(route.path || []), ...route.all_stretches.map(([lat, lon]) => [lat, lon])];
    const latitudes = points.map(point => point[0]), longitudes = points.map(point => point[1]);
    // The route fills the map, with room around it for the cities near it and the names of its stretches.
    const padLat = Math.max(.1, (Math.max(...latitudes) - Math.min(...latitudes)) * .25);
    const padLon = Math.max(.18, (Math.max(...longitudes) - Math.min(...longitudes)) * .25);
    const south = Math.min(...latitudes) - padLat, north = Math.max(...latitudes) + padLat;
    const west = Math.min(...longitudes) - padLon, east = Math.max(...longitudes) + padLon;
    const factor = Math.cos((south + north) / 2 * Math.PI / 180);
    const unit = Math.max((east - west) * factor / (width - 2 * margin), (north - south) / (height - 2 * margin)) || 1;
    const offsetX = (width - (east - west) * factor / unit) / 2, offsetY = (height - (north - south) / unit) / 2;
    const project = (lat, lon) => [offsetX + (lon - west) * factor / unit, height - offsetY - (lat - south) / unit];
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('class', className);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', `${route.route}: ${measure} along the route${ringColor ? ' by owner' : ''}`);
    svg.append(svgElement(svg, 'rect', {x: 0, y: 0, width, height, rx: 10, fill: '#e9eef3'}));
    const land = svgElement(svg, 'g', {});
    svg.append(land);
    const tests = svgElement(svg, 'g', {});
    svg.append(tests);
    for (const [lat, lon] of background) {
      if (lat < south || lat > north || lon < west || lon > east) continue;
      const [x, y] = project(lat, lon);
      tests.append(svgElement(svg, 'circle', {cx: x, cy: y, r: 1.4, fill: '#d5dbe2'}));
    }
    // The map areas (ITL3 in the UK) as the land under the route, once loaded: they replace the other tests.
    if (currentResultsSavedFilterId) {
      renderLoads.push(lossBoundaries(currentResultsSavedFilterId, 'Area').then(({boundaries}) => {
        let drawn = false;
        for (const rings of Object.values(boundaries || {})) {
          for (const ring of rings) {
            if (!ring.some(([lon, lat]) => lat >= south && lat <= north && lon >= west && lon <= east)) continue;
            land.append(svgElement(svg, 'path', {d: `M${ring.map(([lon, lat]) => project(lat, lon).map(value => value.toFixed(1)).join(',')).join('L')}Z`,
              fill: '#ffffff', stroke: '#d5dde5', 'stroke-width': .8}));
            drawn = true;
          }
        }
        if (drawn) tests.remove();
      }));
    }
    // The tests of the route (a sample of their positions) in the colour of the operator.
    for (const [lat, lon] of route.path || []) {
      const [x, y] = project(lat, lon);
      svg.append(svgElement(svg, 'circle', {cx: x, cy: y, r: 2.2, fill: blendHex(color, '#FFFFFF', .35)}));
    }
    // The measured cities around the route on the map.
    const cities = (route.landmarks || []).filter(place => place.latitude >= south && place.latitude <= north
      && place.longitude >= west && place.longitude <= east).map(place => [...project(place.latitude, place.longitude), place.name]);
    for (const [x, y] of cities) svg.append(svgElement(svg, 'circle', {cx: x, cy: y, r: 3.5, fill: '#1c1c28', stroke: '#ffffff', 'stroke-width': 1.2}));
    const peak = Math.max(...route.all_stretches.map(item => item[2]), 0) || 1;
    const top = new Map(ranked.map((row, index) => [`${row.latitude},${row.longitude}`, [index + 1, row]]));
    const names = [];
    for (const [lat, lon, points, owner] of [...route.all_stretches].sort((left, right) => left[2] - right[2])) {
      const [x, y] = project(lat, lon);
      const share = Math.sqrt(points / peak);
      const radius = 4 + 20 * share;
      const fill = stretchColour(share);
      const circle = svgElement(svg, 'circle', {cx: x, cy: y, r: radius, fill, 'fill-opacity': .9,
        stroke: ringColor && owner ? ringColor(owner) : '#ffffff', 'stroke-width': ringColor && owner ? 3 : 1.5, 'data-stretch': `${lat},${lon}`});
      const ranked = top.get(`${lat},${lon}`);
      setChartTooltip(circle, `${ranked ? `${ranked[1].label} · ` : ''}${ringColor ? `${owner || 'No Region'} · ` : ''}${insightNumber(points, 2)} ${measure}`, true);
      svg.append(circle);
      if (ranked) {
        const [red, green, blue] = hexChannels(fill);
        const label = svgElement(svg, 'text', {x, y: y + 4, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 800,
          fill: .299 * red + .587 * green + .114 * blue > 160 ? '#1c1c28' : '#ffffff'});
        label.textContent = String(ranked[0]);
        svg.append(label);
        names.push([x, y, radius, ranked[0], ranked[1].label || '']);
      }
    }
    // The names on the map, above the circles: the cities first, always named (where their name covers no other city,
    // else beside their dot, inside the map), then the nearest city of each numbered stretch (the most lost first), each
    // beside its point where it covers no number or name placed before it, else left out (the list beside the map
    // names every stretch).
    const circles = names.map(([x, y, radius]) => [x - radius, y - radius, x + radius, y + radius]);
    const taken = [];
    const overlaps = (box, others) => others.some(other => box[0] < other[2] && other[0] < box[2] && box[1] < other[3] && other[1] < box[3]);
    const placeName = (x, y, gap, text, size, weight, city = false) => {
      const textWidth = text.length * size * .56;
      const candidates = [[x + gap, y + size * .35, 'start'], [x - gap, y + size * .35, 'end'], [x, y - gap - 1, 'middle'],
        [x, y + gap + size * .85, 'middle'], [x + gap, y - gap, 'start'], [x - gap, y - gap, 'end'],
        [x + gap, y + gap + size * .7, 'start'], [x - gap, y + gap + size * .7, 'end']];
      const boxOf = ([left, baseline, anchor]) => {
        const start = anchor === 'start' ? left : anchor === 'end' ? left - textWidth : left - textWidth / 2;
        return [start - 2, baseline - size, start + textWidth + 2, baseline + 3];
      };
      const inside = box => box[0] >= 4 && box[2] <= width - 4 && box[1] >= 4 && box[3] <= height - 30;
      // Clear of the circles first; a city that has no such place may cover a circle rather than go unnamed.
      const fits = (candidate, clearOfCircles) => {
        const box = boxOf(candidate);
        return inside(box) && !overlaps(box, taken) && (!clearOfCircles || !overlaps(box, circles));
      };
      let place = candidates.find(candidate => fits(candidate, true)) || (city ? candidates.find(candidate => fits(candidate, false)) : null);
      if (!place && city) {
        // Beside its dot, moved inside the map.
        const box = boxOf(candidates[0]);
        const shift = Math.min(0, width - 4 - box[2]);
        place = [candidates[0][0] + shift, Math.max(size + 4, Math.min(height - 33, candidates[0][1])), 'start'];
      }
      if (!place) return;
      taken.push(boxOf(place));
      const label = svgElement(svg, 'text', {x: place[0], y: place[1], 'text-anchor': place[2], 'font-size': size, 'font-weight': weight,
        fill: '#1c1c28', stroke: '#ffffff', 'stroke-width': 3, 'paint-order': 'stroke'});
      label.textContent = text;
      svg.append(label);
    };
    for (const [x, y, name] of cities) {
      // A city under a numbered circle is named beyond it.
      const reach = Math.max(6, ...names.filter(([cx, cy, radius]) => Math.hypot(x - cx, y - cy) < radius)
        .map(([cx, cy, radius]) => radius + Math.hypot(x - cx, y - cy) + 3));
      placeName(x, y, reach, name, 12.5, 800, true);
    }
    for (const [x, y, radius, , text] of names.sort((left, right) => left[3] - right[3])) if (text) placeName(x, y, radius + 4, text, 10.5, 600);
    // The scale of the colours: little lost to the most lost.
    const gradientId = `scoring-stretch-scale-${Math.random().toString(36).slice(2, 8)}`;
    const gradient = svgElement(svg, 'linearGradient', {id: gradientId});
    [0, .5, 1].forEach(offset => gradient.append(svgElement(svg, 'stop', {offset, 'stop-color': stretchColour(offset)})));
    svg.append(gradient);
    svg.append(svgElement(svg, 'rect', {x: margin, y: height - 18, width: 120, height: 7, rx: 3.5, fill: `url(#${gradientId})`}));
    const scaleLabel = svgElement(svg, 'text', {x: margin, y: height - 23, 'font-size': 10, fill: '#475569'});
    scaleLabel.textContent = measure[0].toUpperCase() + measure.slice(1);
    const scaleMax = svgElement(svg, 'text', {x: margin + 126, y: height - 12, 'font-size': 10, fill: '#475569'});
    scaleMax.textContent = `up to ${insightNumber(peak, 1)}`;
    svg.append(scaleLabel, scaleMax);
    // The stretch chosen in the table beside the map (linkStretchTable): the map zooms in on it and rings it; without a
    // stretch, it shows the whole route again.
    let view = [0, 0, width, height];
    const animateView = target => {
      const from = [...view];
      const start = performance.now();
      const step = now => {
        const progress = Math.min(1, (now - start) / 350), eased = 1 - (1 - progress) ** 3;
        view = from.map((value, index) => value + (target[index] - value) * eased);
        svg.setAttribute('viewBox', view.map(value => value.toFixed(1)).join(' '));
        if (progress < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
    svg.focusStretch = (latitude = null, longitude = null) => {
      svg.querySelectorAll('circle.is-focused').forEach(node => node.classList.remove('is-focused'));
      if (latitude === null || longitude === null) {
        animateView([0, 0, width, height]);
        return;
      }
      const [x, y] = project(latitude, longitude);
      const zoomWidth = width / 2.2, zoomHeight = height / 2.2;
      animateView([Math.max(0, Math.min(width - zoomWidth, x - zoomWidth / 2)), Math.max(0, Math.min(height - zoomHeight, y - zoomHeight / 2)),
        zoomWidth, zoomHeight]);
      svg.querySelector(`circle[data-stretch="${latitude},${longitude}"]`)?.classList.add('is-focused');
    };
    return svg;
  }

  // The table of the stretches beside a route map: choosing a stretch (a click, Enter or Space) shows it on the map, zoomed
  // in and ringed; choosing it again, or Whole route on the map, shows the whole route again. Returns the map in its frame.
  function linkStretchTable(map, table, stretches) {
    const frame = document.createElement('div');
    frame.className = 'scoring-route-map-frame';
    const reset = document.createElement('button');
    reset.type = 'button';
    reset.className = 'scoring-route-map-reset';
    reset.textContent = 'Whole route';
    reset.hidden = true;
    frame.append(map, reset);
    const rows = [...(table.tBodies[0]?.rows || [])];
    let chosen = null;
    const choose = index => {
      chosen = index === chosen ? null : index;
      rows.forEach((row, rowIndex) => {
        row.classList.toggle('is-chosen', rowIndex === chosen);
        row.setAttribute('aria-pressed', String(rowIndex === chosen));
      });
      const stretch = chosen === null ? null : stretches[chosen];
      map.focusStretch?.(stretch?.latitude ?? null, stretch?.longitude ?? null);
      reset.hidden = chosen === null;
    };
    rows.forEach((row, index) => {
      if (!Number.isFinite(Number(stretches[index]?.latitude))) return;
      row.classList.add('scoring-stretch-row');
      row.tabIndex = 0;
      row.setAttribute('role', 'button');
      row.setAttribute('aria-pressed', 'false');
      row.title = 'Show this stretch on the map (choose it again for the whole route)';
      row.addEventListener('click', () => choose(index));
      row.addEventListener('keydown', event => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        choose(index);
      });
    });
    reset.addEventListener('click', () => { if (chosen !== null) choose(chosen); });
    return frame;
  }

  // Points lost per area: the map areas (the ITL3 areas in the UK, the workspace's Map Areas elsewhere,
  // or the workspace Clusters and Regions) coloured by the points lost, and the cities, routes or
  // clusters that lose most.
  const lossBoundaryCache = new Map();
  let lossLow = activeTheme.loss_ramp ? hexChannels(activeTheme.loss_ramp[0]) : [249, 214, 92];
  let lossHigh = activeTheme.loss_ramp ? hexChannels(activeTheme.loss_ramp[1]) : [200, 16, 46];
  const maxLossBars = 30;

  function lossColor(ratio) {
    const value = Math.max(0, Math.min(1, Number(ratio) || 0));
    return `rgb(${lossLow.map((low, index) => Math.round(low + (lossHigh[index] - low) * value)).join(',')})`;
  }

  // The areas without points lost and the borders between areas, in the colours of the theme's panels.
  function lossMapNeutral() {
    const surface = hexChannels(activeTheme?.surface || '#FFFFFF');
    const ink = hexChannels(activeTheme?.ink || '#1F2A37');
    return {zero: `rgb(${surface.map((value, index) => Math.round(value + (ink[index] - value) * .08)).join(',')})`,
      border: activeTheme?.surface || '#FFFFFF'};
  }

  function lossBoundaries(savedFilterId, field) {
    const key = `${savedFilterId}:${field}`;
    if (!lossBoundaryCache.has(key)) {
      lossBoundaryCache.set(key, requestJson(`${savedFiltersUrl}/${encodeURIComponent(savedFilterId)}/boundaries/${encodeURIComponent(field)}`)
        .then(body => ({boundaries: body?.boundaries || {}, outlines: body?.background || []}))
        .catch(() => ({boundaries: {}, outlines: []})));
    }
    return lossBoundaryCache.get(key);
  }

  function lossMapSvg(boundaries, values, areas, background, describe = null, outlines = []) {
    const svgNs = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNs, 'svg');
    svg.classList.add('scoring-loss-map-svg');
    const rings = Object.entries(boundaries).flatMap(([name, polygons]) => polygons.map(ring => [name, ring]));
    const points = rings.length ? rings.flatMap(([, ring]) => ring)
      : [...background.map(([lat, lon]) => [lon, lat]), ...areas.filter(area => area.latitude !== null && area.latitude !== undefined)
        .map(area => [area.longitude, area.latitude])];
    if (!points.length) return svg;
    const xs = points.map(point => point[0]);
    const ys = points.map(point => point[1]);
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const scaleX = Math.cos((minY + maxY) / 2 * Math.PI / 180);
    const height = 600;
    const unit = (maxY - minY) / (height - 20) || 1e-6;
    const width = Math.max(200, (maxX - minX) * scaleX / unit + 20);
    svg.setAttribute('viewBox', `0 0 ${width.toFixed(0)} ${height}`);
    const project = (x, y) => [10 + (x - minX) * scaleX / unit, height - 10 - (y - minY) / unit];
    const positive = Object.values(values).filter(value => value > 0);
    const low = positive.length ? Math.min(...positive) : 0;
    const span = (positive.length ? Math.max(...positive) : 0) - low;
    const tooltip = (element, name, value) => {
      const title = document.createElementNS(svgNs, 'title');
      title.textContent = describe ? describe(name, value) : `${name}: ${insightNumber(value, 2)} points lost`;
      element.append(title);
    };
    if (rings.length) {
      // The outlines of the countries, in grey under their areas.
      for (const ring of outlines) {
        const path = document.createElementNS(svgNs, 'path');
        path.setAttribute('d', `M${ring.map(([x, y]) => project(x, y).map(value => value.toFixed(1)).join(',')).join('L')}Z`);
        path.setAttribute('class', 'scoring-loss-map-outline');
        svg.append(path);
      }
      for (const [name, ring] of rings) {
        const path = document.createElementNS(svgNs, 'path');
        path.setAttribute('d', `M${ring.map(([x, y]) => project(x, y).map(value => value.toFixed(1)).join(',')).join('L')}Z`);
        const value = values[name] || 0;
        const neutral = lossMapNeutral();
        path.setAttribute('fill', value > 0 ? lossColor(span ? (value - low) / span : 1) : neutral.zero);
        path.dataset.area = name;
        path.dataset.value = String(value);
        path.setAttribute('stroke', neutral.border);
        path.setAttribute('stroke-width', '.6');
        tooltip(path, name, value);
        svg.append(path);
      }
      return svg;
    }
    for (const [lat, lon] of background) {
      const [x, y] = project(lon, lat);
      const dot = document.createElementNS(svgNs, 'circle');
      Object.entries({cx: x.toFixed(1), cy: y.toFixed(1), r: 1.4, fill: '#d6dce2'}).forEach(([key, value]) => dot.setAttribute(key, value));
      svg.append(dot);
    }
    const peak = Math.max(0, ...areas.map(area => area.points)) || 1;
    for (const area of [...areas].sort((a, b) => a.points - b.points)) {
      const color = lossColor(area.points / peak);
      const spots = area.kind === 'route' && area.route?.length ? area.route.map(([lat, lon]) => [lon, lat, 3])
        : area.latitude !== null && area.latitude !== undefined ? [[area.longitude, area.latitude, 4 + 16 * Math.sqrt(area.points / peak)]] : [];
      for (const [lon, lat, radius] of spots) {
        const [x, y] = project(lon, lat);
        const circle = document.createElementNS(svgNs, 'circle');
        Object.entries({cx: x.toFixed(1), cy: y.toFixed(1), r: radius.toFixed(1), fill: color, stroke: '#fff'})
          .forEach(([key, value]) => circle.setAttribute(key, value));
        circle.dataset.area = area.name;
        tooltip(circle, area.name, area.points);
        svg.append(circle);
      }
    }
    return svg;
  }

  // The location (for example a City) of a points-lost map, shown in its selector.
  function lossScopeLabel(context) {
    const names = {vendor: 'Vendor', region: 'Region', cluster: 'Cluster', city: 'City', campaign: 'Campaign'};
    const fields = Object.keys(names).filter(field => context?.[field] !== undefined && context?.[field] !== null && context?.[field] !== '');
    return {
      title: fields.map(field => names[field]).join(' · ') || 'Scope',
      value: fields.map(field => (field === 'campaign' ? hierarchyDisplayValue({level: 'Campaign', value: context[field]}) : String(context[field]))).join(' · '),
    };
  }

  // Points Lost Map: choose the location (for example London), the operators (their maps side by
  // side) and the analysis per City, Region or Cluster.
  function renderPointsLossMaps(pane, payload, environment, savedFilterId) {
    if (!environment || !savedFilterId) return;
    if (payload.points_loss_pending) {
      // Calculated from the Scoring History: the map follows once the rows of the tests are read.
      const section = document.createElement('section');
      section.className = 'scoring-insight-section scoring-result-card scoring-loss-maps-card';
      const heading = document.createElement('h4');
      heading.className = 'scoring-table-section-title';
      heading.textContent = 'Points Lost Map';
      appendResultScope(heading);
      const waiting = document.createElement('div');
      waiting.className = 'scoring-calculating is-loading';
      waiting.setAttribute('role', 'status');
      waiting.innerHTML = '<p class="scoring-calculating-title">Preparing the Points Lost Map…</p>'
        + '<div class="scoring-calculating-bar" role="progressbar" aria-label="Preparing the Points Lost Map">'
        + '<span class="scoring-calculating-fill" style="width: 100%"></span></div>'
        + '<p class="scoring-calculating-detail">The scores come from the Scoring History; the map reads the rows of the tests.</p>';
      section.append(heading, waiting);
      pane.append(section);
      return;
    }
    const maps = insightItems(payload, 'points_loss_maps', environment);
    if (!maps.length) return;
    const seriesKey = item => `${item.operator}|${JSON.stringify(item.context)}`;
    const layers = new Map(maps.filter(item => item.field === 'Area').map(item => [seriesKey(item), item]));
    const entries = [];
    for (const item of maps) {
      if (item.field === 'City') entries.push({ranking: item, layer: layers.get(seriesKey(item)) || null, title: 'City'});
      else if (['Cluster', 'Region'].includes(item.field)) entries.push({ranking: item, layer: item, title: item.field});
    }
    if (!entries.length) return;
    const section = document.createElement('section');
    section.className = 'scoring-insight-section scoring-result-card scoring-loss-maps-card';
    const heading = document.createElement('h4');
    heading.className = 'scoring-table-section-title';
    heading.textContent = 'Points Lost Map';
    // Location and operators are shared with the KPI GAP Profile; then the analysis per City, Region or Cluster.
    const {controls, inScope, chosen} = gapInsightControls(pane, entries.map(entry => ({...entry.ranking, entry})));
    appendResultScope(heading, inScope[0]?.context);
    // Maps per and Colour areas by below the location (such as the Campaign), the operators beside them.
    const selectors = document.createElement('div');
    selectors.className = 'scoring-stacked-selectors';
    const scopeControl = controls.querySelector(':scope > .scoring-insight-select');
    if (scopeControl) {
      scopeControl.replaceWith(selectors);
      selectors.append(scopeControl);
    } else {
      controls.prepend(selectors);
    }
    const allViews = ['City', 'Region', 'Cluster'];
    const views = allViews.filter(view => inScope.some(item => item.entry.title === view));
    const {wrapper: viewControl, value: storedView} = insightSelect('points-loss-view', allViews.map(item => [item, item]), 'Maps per');
    const view = views.includes(storedView) ? storedView : views[0];
    const viewSelect = viewControl.querySelector('select');
    viewSelect.value = view;
    for (const option of viewSelect.options) {
      option.disabled = !views.includes(option.value);
      if (option.disabled) option.title = `These results have no ${option.value} data`;
    }
    selectors.append(viewControl);
    const candidates = inScope.filter(item => item.entry.title === view).map(item => item.entry);
    // Rank the places by their National points lost or by the points they lose per 1,000 of their tests, so a place does
    // not rank high only because it was measured more (results calculated before keep no tests per place).
    const counted = candidates.find(entry => entry.ranking.rate_tests);
    const rated = candidates.some(entry => entry.ranking.areas.some(area => area.rate !== null && area.rate !== undefined));
    const {wrapper: rankControl, value: storedRank} = insightSelect('points-loss-rank',
      [['points', 'National points lost'], ['rate', 'Points lost per 1,000 tests']], 'Rank by');
    const rank = rated && storedRank === 'rate' ? 'rate' : 'points';
    const rankSelect = rankControl.querySelector('select');
    rankSelect.value = rank;
    if (!rated) {
      rankSelect.options[1].disabled = true;
      rankSelect.options[1].title = counted ? `No place has ${insightNumber(counted.ranking.rate_minimum, 0)} tests or more`
        : 'Calculate the scoring again to count the tests of each place';
    }
    selectors.append(rankControl);
    // Per City on map areas, one choice for every map: the points of the city or route that loses most among those
    // measured in each area (the default), or the real points lost there by the city or route that loses most there.
    // The colours of the areas never change with the chosen rows or areas, and changing the choice keeps them chosen.
    let mode = 'top';
    let modeSelect = null;
    if (view === 'City' && candidates.some(entry => entry.layer)) {
      const real = candidates.some(entry => entry.ranking.areas.some(area => Object.keys(area.area_losses || {}).length));
      const modeControl = document.createElement('label');
      modeControl.className = 'scoring-environment-filter scoring-insight-select';
      modeControl.append(document.createTextNode('Colour areas by'));
      modeSelect = document.createElement('select');
      modeSelect.dataset.lossColourMode = '';
      for (const [value, text] of [['top', 'Points of the city or route that loses most in each area'],
        ['losses', 'Points lost in each area by the city or route that loses most there']]) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = text;
        modeSelect.append(option);
      }
      mode = real && rank === 'points' && insightSelections.get('points-loss-colour') === 'losses' ? 'losses' : 'top';
      modeSelect.value = mode;
      if (!real || rank === 'rate') {
        modeSelect.options[1].disabled = true;
        modeSelect.options[1].title = rank === 'rate' ? 'The points lost per 1,000 tests colour each area by its city or route'
          : 'Calculate the scoring again to keep the points each city or route loses in each area';
      }
      if (rank === 'rate') modeSelect.options[0].textContent = 'Points per 1,000 tests of the city or route that loses most in each area';
      modeControl.append(modeSelect);
      selectors.append(modeControl);
    }
    const grid = document.createElement('div');
    grid.className = `scoring-loss-map-grid${chosen.length > 1 ? ' is-multiple' : ''}`;
    const cards = candidates.filter(item => chosen.includes(item.ranking.operator))
      .map(entry => pointsLossMapCard(entry, payload, savedFilterId, chosen.length > 1, mode, rank));
    grid.append(...cards);
    modeSelect?.addEventListener('change', () => {
      insightSelections.set('points-loss-colour', modeSelect.value);
      persistScoringViewState();
      cards.forEach(card => card.setColourMode?.(modeSelect.value));
    });
    section.append(heading, controls);
    // Tests in a country without map areas: the whole country is one area until its areas are added and the filters calculated again.
    const unmapped = view === 'City' ? candidates.find(entry => entry.layer?.unmapped_countries?.length)?.layer.unmapped_countries || [] : [];
    if (unmapped.length) {
      const warning = document.createElement('p');
      warning.className = 'scoring-insight-note scoring-loss-unmapped';
      warning.textContent = `${unmapped.map(item => item.name).join(', ')} ${unmapped.length > 1 ? 'are' : 'is'} shown as a whole country: add the Map Areas of `
        + `${unmapped.length > 1 ? 'these countries' : 'this country'} in Workspace Config and calculate the scoring again to see ${unmapped.length > 1 ? 'their' : 'its'} areas.`;
      section.append(warning);
    }
    section.append(grid);
    pane.append(section);
  }

  // One operator's map with the note and the ranking of the areas where it loses most points.
  function pointsLossMapCard(entry, payload, savedFilterId, compact, mode = 'top', rank = 'points') {
    const {ranking, layer} = entry;
    // Per 1,000 tests: the places with enough tests by the points they lose per 1,000 of their tests; ``points`` holds
    // that rate (the map and the bars follow it) and ``national`` their National points lost.
    const perTests = rank === 'rate' && Boolean(ranking.rate_tests);
    const areas = perTests ? ranking.areas.filter(area => area.rate !== null && area.rate !== undefined)
      .map(area => ({...area, points: area.rate, national: area.points})).sort((left, right) => right.points - left.points)
      : ranking.areas;
    const sameLayer = !layer || layer === ranking || layer.field === ranking.field;
    const card = document.createElement('article');
    card.className = 'scoring-loss-map-card';
    // The operator of the column, large and in its colour.
    const title = document.createElement('h5');
    title.className = 'scoring-loss-map-operator';
    title.textContent = ranking.label;
    const bars = areas.filter(area => area.name !== 'Not specified').slice(0, maxLossBars);
    const listed = bars.reduce((sum, area) => sum + (area.national ?? area.points), 0);
    const note = document.createElement('p');
    note.className = 'scoring-insight-note';
    const operator = document.createElement('strong');
    operator.textContent = ranking.label;
    const color = safeHexColor(ranking.color);
    if (color) { operator.style.color = color; title.style.color = color; }
    const listedText = document.createElement('strong');
    listedText.textContent = `The ${bars.length} ${entry.title === 'City' ? 'cities and routes' : `${entry.title.toLowerCase()}s`} listed`;
    const byRows = layer && layer.field === 'Area' && ranking.field === 'City';
    const realData = byRows && ranking.areas.some(area => Object.keys(area.area_losses || {}).length);
    const areaLabel = layer?.area_label || 'area';
    // The points lost and the share of the listed rows are bold, as in the KPI GAP Profile note.
    const bold = text => {
      const element = document.createElement('strong');
      element.textContent = text;
      return element;
    };
    const total = () => ['(', bold(`${insightNumber(ranking.total, 1)} ${scoringLabel()} points`),
      ' of its National score lost in total; hover an area to see them). '];
    // The points of the operator's National score lost in the tests of each place (they add up to its National loss), not
    // the score of each place on its own tests, which the National & Geographical Areas Trends show.
    const writeNote = colourMode => {
      note.replaceChildren();
      if (perTests) {
        note.append(byRows ? `The map colours each ${areaLabel} by the National points `
          : `The map colours each ${entry.title.toLowerCase()} by the National points `, operator,
        byRows ? ' loses per 1,000 tests in the city or route that loses most per 1,000 tests among those measured in it '
          : ' loses per 1,000 of its tests ', ...total());
        note.append(listedText, ` (those with ${insightNumber(ranking.rate_minimum, 0)} tests or more) rank by the points lost per 1,000 of their Voice calls and Data tests, so a place does not rank high only because it was measured more; they hold `,
          bold(`${ranking.total ? Math.round(listed / ranking.total * 100) : 0}%`), ' of the points lost. ',
          bold('National points'), ': the part of the National loss in the tests of each place, not its own score (see the National & Geographical Areas Trends in Scoring Trends).');
        return;
      }
      if (byRows && colourMode === 'losses' && realData) {
        note.append(`The map colours each ${areaLabel} by the National points lost in it by the city or route of `, operator,
          ' that loses most there ', ...total());
      } else if (byRows) {
        note.append(`The map colours each ${areaLabel} by the National points `, operator,
          ' loses in the city or route that loses most among those measured in it ', ...total());
      } else {
        note.append('The map shows where ', operator, ` loses its National ${scoringLabel()} points (`, bold(insightNumber(ranking.total, 1)), ' in total). ');
      }
      note.append(listedText, ' account for ', bold(`${ranking.total ? Math.round(listed / ranking.total * 100) : 0}%`), ' of them. ',
        bold('National points'), ': the part of the National loss in the tests of each place, not its own score (see the National & Geographical Areas Trends in Scoring Trends).');
    };
    writeNote(mode);
    const content = document.createElement('div');
    content.className = `scoring-loss-map${compact ? ' is-compact' : ''}`;
    const mapBox = document.createElement('div');
    mapBox.className = 'scoring-loss-map-figure';
    mapBox.textContent = 'Loading map…';
    const peak = Math.max(0, ...bars.map(area => area.points));
    // All environments: beside each city or route, the environments where it loses points (most first).
    // Regions and Clusters hold tests of every environment, so they leave the column out.
    const withEnvironments = entry.title === 'City' && bars.some(area => area.environments?.length);
    // Both figures of each place: the bar on the one it is ranked by.
    const rated = Boolean(ranking.rate_tests);
    const rateCell = area => ({text: area.rate === null || area.rate === undefined ? '—' : insightNumber(area.rate, 2),
      className: 'scoring-insight-number', title: `${insightNumber(area.tests || 0, 0)} tests`});
    const nationalOf = area => area.national ?? area.points;
    const tested = bars.reduce((sum, area) => sum + (Number(area.tests) || 0), 0);
    const table = insightTable(['Area', ...(withEnvironments ? ['Type'] : []), 'National points lost',
      ...(rated ? ['Per 1,000 tests'] : []), 'Share'], bars.map(area => [area.name,
      ...(withEnvironments ? [{text: (area.environments || []).map(name => shortEnvironmentLabel(name)).join(', '),
        title: (area.environments || []).map(name => environmentLabel(name)).join(', '),
        className: 'scoring-loss-environment'}] : []),
      perTests ? {text: insightNumber(area.national, 2), className: 'scoring-insight-number'} : gapBarCell(area.points, peak, {loss: true, total: true}),
      ...(rated ? [perTests ? {...gapBarCell(area.points, peak, {loss: true, total: true}), title: `${insightNumber(area.tests || 0, 0)} tests`} : rateCell(area)] : []),
      {text: `${insightNumber(area.share * 100, 1)}%`, className: 'scoring-insight-number'}]),
    {total: [insightTotalLabel(`Total of the ${bars.length} listed`, withEnvironments ? 2 : 1),
      insightTotalCell(bars.reduce((sum, area) => sum + (Number(nationalOf(area)) || 0), 0), {digits: 2}),
      ...(rated ? [insightTotalCell(tested ? bars.reduce((sum, area) => sum + (Number(area.tests) ? Number(nationalOf(area)) || 0 : 0), 0) / tested * 1000 : null, {digits: 2})] : []),
      insightTotalCell(bars.reduce((sum, area) => sum + (Number(area.share) || 0), 0) * 100, {digits: 1, suffix: '%'})]});
    const tableBox = document.createElement('div');
    tableBox.className = 'scoring-insight-table-wrap';
    tableBox.append(table);
    const hint = document.createElement('p');
    hint.className = 'scoring-loss-map-hint';
    hint.textContent = 'Click a row or an area to show it alone; Ctrl/⌘-click adds more, Shift+click chooses the rows in between and Shift+drag selects several areas. Click it again or Esc to show all.';
    content.append(mapBox, tableBox);
    card.append(title, note, content, hint);
    const values = Object.fromEntries((sameLayer ? areas : layer.areas).filter(area => area.name !== 'Not specified')
      .map(area => [area.name, area.points]));
    const rows = [...table.querySelectorAll('tbody tr')];
    rows.forEach((row, index) => {
      row.dataset.area = bars[index]?.name || '';
      row.dataset.points = String(bars[index]?.points || 0);
    });
    renderLoads.push((layer ? lossBoundaries(savedFilterId, layer.field) : Promise.resolve({boundaries: {}, outlines: []})).then(({boundaries, outlines}) => {
      // Each colouring: each city or route with its map areas (the share of its tests in each, or the points it
      // loses in each one) and the colour of every area.
      const colourings = {};
      const unit = perTests ? 'points lost per 1,000 tests' : 'points lost';
      for (const colourMode of byRows ? (realData && !perTests ? ['top', 'losses'] : ['top']) : ['top']) {
        const real = colourMode === 'losses';
        const links = lossAreaLinks({...ranking, areas}, layer, real);
        const rowAreas = byRows ? lossRowValues(areas, links, real) : null;
        const describe = name => {
          if (!rowAreas) return `${name}: ${insightNumber(values[name] || 0, 2)} ${unit}`;
          const lines = rowAreas.rows[name] || [];
          const lost = values[name] && !perTests ? ` (${insightNumber(values[name], 2)} points lost in this area)` : '';
          return lines.length ? `${name}${lost}\n${lines.slice(0, 4).map(([row, points]) => `${row}: ${insightNumber(points, 2)} ${unit}${real ? ' here' : ''}`).join('\n')}`
            : `${name}: no listed city or route`;
        };
        colourings[colourMode] = {links, values: rowAreas ? rowAreas.values : values, describe};
      }
      const current = colourings[mode] || colourings.top;
      const svg = lossMapSvg(layer ? boundaries : {}, current.values, areas,
        payload?.views?.insights?.points_loss_background || [], (name) => current.describe(name), outlines);
      mapBox.replaceChildren(svg);
      const select = lossMapSelection(card, svg, rows, current.links);
      select.zoom = enableMapZoom(mapBox, svg, select);
      // Changing the colouring keeps the chosen rows or areas, so both colourings compare easily.
      card.setColourMode = colourMode => {
        const next = colourings[colourMode] || colourings.top;
        writeNote(colourings[colourMode] ? colourMode : 'top');
        select.recolour(next.values, next.describe, next.links);
      };
    }));
    return card;
  }

  // The map areas of each listed City, route, Region or Cluster: the points it loses in each one (real), or the
  // share of its tests in each one, leaving out areas with a few stray tests (under 2% of them).
  function lossAreaLinks(ranking, layer, real) {
    const links = new Map();
    for (const area of ranking.areas) {
      if (!layer || layer.field === ranking.field) { links.set(area.name, {[area.name]: area.points}); continue; }
      if (real) {
        const losses = Object.entries(area.area_losses || {}).filter(([, points]) => points > 0);
        if (losses.length) links.set(area.name, Object.fromEntries(losses));
        continue;
      }
      const shares = area.area_tests || {};
      const total = Object.values(shares).reduce((sum, value) => sum + value, 0);
      if (total <= 0) continue;
      const kept = Object.entries(shares).filter(([, value]) => value / total >= .02);
      const used = kept.length ? kept : [Object.entries(shares).sort((left, right) => right[1] - left[1])[0]];
      const sum = used.reduce((count, [, value]) => count + value, 0);
      links.set(area.name, Object.fromEntries(used.map(([name, value]) => [name, value / sum])));
    }
    return links;
  }

  // Each map area with the largest loss of one city or route in it (its real points lost there, or its total
  // points when the area holds its tests), and every one measured there.
  function lossRowValues(areas, links, real) {
    const values = {};
    const rows = {};
    for (const area of areas) {
      if (area.name === 'Not specified') continue;
      for (const [name, lost] of Object.entries(links.get(area.name) || {})) {
        const points = real ? lost : area.points;
        values[name] = Math.max(values[name] || 0, points);
        (rows[name] ||= []).push([area.name, points]);
      }
    }
    Object.values(rows).forEach(list => list.sort((left, right) => right[1] - left[1]));
    return {values, rows};
  }

  // Choosing rows of the ranking shows their areas alone on the map, and choosing areas on the map
  // (a click, or Shift and a dragged rectangle) leaves the rows of those areas lit in the ranking.
  // Every area keeps its colour: choosing only dims the areas (and rows) left out.
  function lossMapSelection(card, svg, rows, initialLinks) {
    let links = initialLinks;
    const marks = [...svg.querySelectorAll('[data-area]')];
    const chosenRows = new Set();
    const chosenAreas = new Set();
    const refresh = () => {
      if (chosenRows.size) {
        const lit = new Set();
        for (const row of chosenRows) Object.keys(links.get(row) || {}).forEach(area => lit.add(area));
        marks.forEach(mark => mark.classList.toggle('is-dimmed', !lit.has(mark.dataset.area)));
      } else {
        marks.forEach(mark => mark.classList.toggle('is-dimmed', chosenAreas.size > 0 && !chosenAreas.has(mark.dataset.area)));
      }
      const lit = row => (chosenRows.size ? chosenRows.has(row)
        : !chosenAreas.size || Object.keys(links.get(row) || {}).some(area => chosenAreas.has(area)));
      rows.forEach(row => {
        row.classList.toggle('is-selected', chosenRows.has(row.dataset.area));
        row.classList.toggle('is-dimmed', !lit(row.dataset.area));
      });
      card.classList.toggle('has-loss-selection', chosenRows.size > 0 || chosenAreas.size > 0);
      // The map centres and zooms on the chosen rows' areas, and shows it all again without them.
      if (chosenRows.size) {
        const boxes = marks.filter(mark => !mark.classList.contains('is-dimmed')).map(mark => mark.getBBox());
        if (boxes.length && selection.zoom) {
          const x = Math.min(...boxes.map(box => box.x)), y = Math.min(...boxes.map(box => box.y));
          const width = Math.max(...boxes.map(box => box.x + box.width)) - x, height = Math.max(...boxes.map(box => box.y + box.height)) - y;
          selection.zoom.fit({x, y, width, height});
          zoomedToRows = true;
        }
      } else if (zoomedToRows) {
        selection.zoom?.reset();
        zoomedToRows = false;
      }
    };
    let zoomedToRows = false;
    // The row a Shift+click range starts from.
    let anchor = null;
    const choose = (set, other, names, add) => {
      other.clear();
      if (!add) {
        const same = names.length === set.size && names.every(name => set.has(name));
        set.clear();
        if (same) { refresh(); return; }
      }
      for (const name of names) {
        if (add && set.has(name) && names.length === 1) set.delete(name); else set.add(name);
      }
      refresh();
    };
    for (const row of rows) {
      row.classList.add('is-selectable');
      // Shift+click chooses every row from the last one clicked; Ctrl/⌘ keeps the rows already chosen.
      row.addEventListener('mousedown', event => { if (event.shiftKey) event.preventDefault(); });
      row.addEventListener('click', event => {
        const index = rows.indexOf(row);
        if (event.shiftKey && anchor !== null) {
          const range = rows.slice(Math.min(anchor, index), Math.max(anchor, index) + 1).map(item => item.dataset.area);
          chosenAreas.clear();
          if (!(event.ctrlKey || event.metaKey)) chosenRows.clear();
          range.forEach(name => chosenRows.add(name));
          refresh();
          return;
        }
        anchor = index;
        choose(chosenRows, chosenAreas, [row.dataset.area], event.ctrlKey || event.metaKey);
      });
    }
    card.tabIndex = -1;
    card.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      chosenRows.clear();
      chosenAreas.clear();
      refresh();
    });
    const selection = {
      zoom: null,
      // Another colouring: the areas take its colours and links, and the chosen rows or areas stay chosen.
      recolour(values, describe, nextLinks) {
        const positive = Object.values(values).filter(value => value > 0);
        const low = positive.length ? Math.min(...positive) : 0;
        const span = (positive.length ? Math.max(...positive) : 0) - low;
        marks.forEach(mark => {
          const value = values[mark.dataset.area] || 0;
          mark.setAttribute('fill', value > 0 ? lossColor(span ? (value - low) / span : 1) : lossMapNeutral().zero);
          mark.dataset.value = String(value);
          const title = mark.querySelector('title');
          if (title) title.textContent = describe(mark.dataset.area, value);
        });
        links = nextLinks;
        refresh();
      },
      // A click on an area chooses it; a click outside every area shows all.
      onClick(element, event) {
        const name = element?.closest?.('[data-area]')?.dataset.area;
        if (!name) { chosenRows.clear(); chosenAreas.clear(); refresh(); return; }
        choose(chosenAreas, chosenRows, [name], event.ctrlKey || event.metaKey);
        card.focus({preventScroll: true});
      },
      // Shift and a dragged rectangle choose every area it touches.
      onSelect([x, y, width, height], event) {
        const names = [...new Set(marks.filter(mark => {
          const box = mark.getBBox();
          return box.x < x + width && box.x + box.width > x && box.y < y + height && box.y + box.height > y;
        }).map(mark => mark.dataset.area))];
        choose(chosenAreas, chosenRows, names, event.ctrlKey || event.metaKey);
        card.focus({preventScroll: true});
      },
    };
    return selection;
  }

  // The floating zoom buttons (zoom in, zoom out, whole view), shown while the pointer is over the box.
  function addZoomToolbar(box, zoomIn, zoomOut, reset, wholeTitle = 'Show the whole map') {
    const toolbar = document.createElement('div');
    toolbar.className = 'scoring-map-zoom';
    for (const [text, title, action] of [['+', 'Zoom in', zoomIn], ['−', 'Zoom out', zoomOut], ['⤢', wholeTitle, reset]]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = text;
      button.title = title;
      button.setAttribute('aria-label', title);
      button.addEventListener('click', event => { event.stopPropagation(); action(); });
      toolbar.append(button);
    }
    box.append(toolbar);
    let hideTimer = 0;
    const show = () => { window.clearTimeout(hideTimer); toolbar.classList.add('is-visible'); };
    const hide = () => { window.clearTimeout(hideTimer); toolbar.classList.remove('is-visible'); };
    // With a mouse the buttons show while the pointer is over the chart or map.
    box.addEventListener('pointerenter', event => { if (event.pointerType === 'mouse') show(); });
    box.addEventListener('pointerleave', event => { if (event.pointerType === 'mouse') hide(); });
    // On touch screens a tap shows them: they stay a few seconds after the last tap, or until a tap elsewhere.
    box.addEventListener('pointerup', event => {
      if (event.pointerType === 'mouse') return;
      show();
      hideTimer = window.setTimeout(hide, 5000);
    });
  }

  // A tap elsewhere hides the zoom buttons shown by a tap. One listener for the page: charts drawn again do not keep
  // listeners of their own (which would keep the charts they replace in memory).
  document.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse') return;
    for (const toolbar of document.querySelectorAll('.scoring-map-zoom.is-visible')) {
      if (!toolbar.parentElement?.contains(event.target)) toolbar.classList.remove('is-visible');
    }
  });

  // Floating buttons at the top right corner of the chart, map, table or panel of the results under the pointer (on
  // touch screens, of the one tapped) download it as a PNG image, as it is shown, or copy it to the clipboard as a
  // screenshot (image_buttons.js): those of the whole card and, when it holds several, those of the chart or table under
  // the pointer; also in the larger view of a chart, map or table. App Events records each one with the Saved Filter.
  // (The tables beside the map of a route have no wrapper of their own, and its map is in a frame.)
  const IMAGE_TABLES = '.scoring-insight-table-wrap, .scoring-matrix-wrap, .scoring-table-wrap, .scoring-position, .scoring-route-side > .scoring-insight-table';
  const IMAGE_CHARTS = '.scoring-chart-card, .scoring-loss-map-card, .scoring-expandable-part, .scoring-route-map-frame';
  // (The panels of the results tabs, as the themes frame them, are cards too.)
  const IMAGE_TARGETS = `${IMAGE_TABLES}, ${IMAGE_CHARTS}, .scoring-result-card, .scoring-table-mode-section,
    .scoring-best-network-layout, .scoring-insight-section, .scoring-expanded-holder`;
  const IMAGE_TITLES = ':scope > :is(h4, h5, .scoring-insight-banner, .scoring-position-title, figcaption)';
  // The zoom buttons are left out of the image.
  const IMAGE_EXCLUDED = '.scoring-map-zoom, .scoring-map-zoom-rect, .scoring-content-zoom-rect';

  // Its own title, after the title of the card it is part of (``Points Lost Map — EE``); a table beside the map of a route
  // has its title just above it, and the larger view the title of its header.
  function imageTitle(target) {
    if (target.matches('.scoring-expanded-holder')) {
      return [...(expandedChartTitle?.childNodes || [])].filter(node => node.nodeType === Node.TEXT_NODE)
        .map(node => node.textContent).join('').trim();
    }
    const caption = target.previousElementSibling?.matches('.scoring-route-table-title') ? target.previousElementSibling : null;
    const titleOf = element => (element === target && caption
      ? caption.textContent.trim() : titleWithoutScope(element?.querySelector(IMAGE_TITLES)));
    const card = target.parentElement?.closest('.scoring-chart-card, .scoring-result-card, .scoring-table-mode-section');
    // (A panel of several charts without a title of its own: the first title inside it.)
    const inner = titleWithoutScope(target.querySelector(':is(h4, h5, figcaption)'));
    return [...new Set([card ? titleOf(card) : '', titleOf(target)].filter(Boolean))].join(' — ') || inner;
  }

  window.attachImageButtons?.({
    root, targets: IMAGE_TARGETS, within: '[data-result-pane], [data-scoring-chart-overlay]',
    tables: `${IMAGE_TABLES}, .scoring-expanded-holder:has(table)`, charts: `${IMAGE_CHARTS}, .scoring-expanded-holder`,
    exclude: IMAGE_EXCLUDED, obstacles: '.scoring-map-zoom', title: imageTitle, fallbackName: 'Scoring',
    // Below the floating section bar and the tab bar of the results.
    topInset: () => {
      const tabs = root.querySelector('.scoring-result-tabs')?.getBoundingClientRect();
      return Math.max(0, document.querySelector('.section-bar')?.getBoundingClientRect().bottom || 0, tabs?.height ? tabs.bottom + 3 : 0);
    },
    fileName: (target, title) => window.imageFileName([title, selectedEnvironment ? environmentLabel(selectedEnvironment) : ''], 'Scoring'),
    details: target => {
      const tab = root.querySelector(`[data-result-tab="${activeResultTab}"]`)?.textContent.trim() || activeResultTab || '';
      return {
        saved_filter_id: Number(currentResultsSavedFilterId) || null,
        tab: target.matches('.scoring-expanded-holder') ? `${tab} (larger view)` : tab,
        environment: selectedEnvironment ? environmentLabel(selectedEnvironment) : '', theme: activeTheme?.id || '',
      };
    },
    record: details => window.recordImageExport('/api/scoring/image-export', details),
  });

  // Zoom for content that is not one SVG (such as the location cards): the content is scaled inside
  // its box, which keeps its size; a dragged rectangle or the floating buttons zoom it.
  function enableContentZoom(box, viewport) {
    const content = viewport.firstElementChild;
    if (!content) return;
    viewport.classList.add('scoring-content-zoom');
    let scale = 1, x = 0, y = 0;
    const render = () => {
      content.style.transformOrigin = '0 0';
      content.style.transform = scale === 1 ? '' : `translate(${x}px, ${y}px) scale(${scale})`;
      viewport.classList.toggle('is-zoomed', scale !== 1);
    };
    const reset = () => { scale = 1; x = 0; y = 0; render(); };
    // Keep the scaled content covering the box.
    const clamp = () => {
      x = Math.min(0, Math.max(viewport.clientWidth - content.offsetWidth * scale, x));
      y = Math.min(0, Math.max(viewport.clientHeight - content.offsetHeight * scale, y));
    };
    const zoomTo = (next, centerX, centerY) => {
      if (next <= 1.001) { reset(); return; }
      scale = Math.min(8, next);
      x = viewport.clientWidth / 2 - centerX * scale;
      y = viewport.clientHeight / 2 - centerY * scale;
      clamp();
      render();
    };
    const center = () => [(viewport.clientWidth / 2 - x) / scale, (viewport.clientHeight / 2 - y) / scale];
    addZoomToolbar(box, () => zoomTo(scale / .6, ...center()), () => zoomTo(scale * .6, ...center()), reset);
    const local = event => {
      const bounds = viewport.getBoundingClientRect();
      return {x: event.clientX - bounds.left + viewport.scrollLeft, y: event.clientY - bounds.top + viewport.scrollTop};
    };
    let start = null;
    let rectangle = null;
    viewport.addEventListener('pointerdown', event => {
      if (event.button !== 0 || event.target.closest('.scoring-map-zoom')) return;
      start = local(event);
      rectangle = document.createElement('div');
      rectangle.className = 'scoring-content-zoom-rect';
      viewport.append(rectangle);
      viewport.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    viewport.addEventListener('pointermove', event => {
      if (!start || !rectangle) return;
      const point = local(event);
      Object.assign(rectangle.style, {
        left: `${Math.min(start.x, point.x)}px`, top: `${Math.min(start.y, point.y)}px`,
        width: `${Math.abs(point.x - start.x)}px`, height: `${Math.abs(point.y - start.y)}px`,
      });
    });
    viewport.addEventListener('pointerup', event => {
      if (!start || !rectangle) return;
      const point = local(event);
      rectangle.remove();
      const width = Math.abs(point.x - start.x), height = Math.abs(point.y - start.y);
      // A click (or a tiny rectangle) does not zoom; the rectangle is measured in unscaled content units.
      if (width > viewport.clientWidth * .02 && height > viewport.clientHeight * .02) {
        const left = (Math.min(start.x, point.x) - x) / scale, top = (Math.min(start.y, point.y) - y) / scale;
        zoomTo(scale * Math.min(viewport.clientWidth / width, viewport.clientHeight / height),
          left + width / scale / 2, top + height / scale / 2);
      }
      start = null;
      rectangle = null;
    });
    viewport.addEventListener('pointercancel', () => { rectangle?.remove(); start = null; rectangle = null; });
  }

  // A chart wider than its card (which then scrolls sideways) starts fitted to the width of the card, keeping its height,
  // when its bars keep at least this share of their width; otherwise it keeps its size and zooms out to the card by steps.
  const CHART_MIN_FIT_SCALE = .75;
  const CHART_WIDTH_STEP = .75;

  // A chart narrowed by its zoom keeps its height: only its width shrinks (``factor``: its width over its own; 1 gives
  // it back its proportions), its texts keep their shape and its lines their thickness.
  function narrowChart(svg, factor) {
    const narrowed = factor < .995;
    if (!narrowed && !('narrowAspect' in svg.dataset)) return;
    const [, , width, height] = (svg.dataset.zoomOriginal || svg.getAttribute('viewBox') || '').split(/\s+/).map(Number);
    if (narrowed && !(width > 0 && height > 0)) return;
    if (!('narrowAspect' in svg.dataset)) svg.dataset.narrowAspect = svg.getAttribute('preserveAspectRatio') || '';
    for (const text of svg.querySelectorAll('text')) {
      if (!('narrowTransform' in text.dataset)) text.dataset.narrowTransform = text.getAttribute('transform') || '';
      const own = text.dataset.narrowTransform;
      if (!narrowed) {
        if (own) text.setAttribute('transform', own);
        else text.removeAttribute('transform');
        continue;
      }
      // Each text widens back around its anchor (its x and y, where its own transform puts them).
      let x = parseFloat(text.getAttribute('x')) || 0;
      let y = parseFloat(text.getAttribute('y')) || 0;
      if (own) {
        text.setAttribute('transform', own);
        const matrix = text.transform?.baseVal?.consolidate?.()?.matrix;
        if (matrix) [x, y] = [matrix.a * x + matrix.c * y + matrix.e, matrix.b * x + matrix.d * y + matrix.f];
      }
      text.setAttribute('transform', `translate(${x} ${y}) scale(${(1 / factor).toFixed(4)} 1) translate(${-x} ${-y}) ${own}`.trim());
    }
    for (const shape of svg.querySelectorAll('line, path, polyline, rect')) {
      if (narrowed) shape.setAttribute('vector-effect', 'non-scaling-stroke');
      else shape.removeAttribute('vector-effect');
    }
    if (narrowed) {
      svg.setAttribute('preserveAspectRatio', 'none');
      svg.style.aspectRatio = `${(width * factor).toFixed(2)} / ${height}`;
    } else {
      if (svg.dataset.narrowAspect) svg.setAttribute('preserveAspectRatio', svg.dataset.narrowAspect);
      else svg.removeAttribute('preserveAspectRatio');
      svg.style.aspectRatio = '';
      delete svg.dataset.narrowAspect;
    }
  }

  // Map zoom: drag a rectangle with the mouse to zoom into it, or use the floating buttons shown
  // while the pointer is over the map (they hide as soon as it leaves).
  function enableMapZoom(box, svg, {onClick = null, onSelect = null} = {}) {
    // The whole view, kept on the element so a copy (the enlarged view) zooms out to it as well.
    svg.dataset.zoomOriginal ||= svg.getAttribute('viewBox') || '';
    const original = svg.dataset.zoomOriginal.split(/\s+/).map(Number);
    if (original.length !== 4 || original.some(value => !Number.isFinite(value))) return;
    let view = (svg.getAttribute('viewBox') || '').split(/\s+/).map(Number);
    if (view.length !== 4 || view.some(value => !Number.isFinite(value))) view = [...original];
    // A wide chart that scrolls sideways is fitted to the visible width (keeping its height) while zoomed,
    // so the chosen area is centred in what is visible; the whole view gives it back its size.
    const scroller = svg.closest('.scoring-chart-scroll');
    // Its width (a share of the card's): zooming out narrows it down to the card's, zooming in widens it back to its
    // own size and then zooms into it.
    const naturalWidth = scroller && String(svg.style.width || '').endsWith('%') ? parseFloat(svg.style.width) : 100;
    const widens = Number.isFinite(naturalWidth) && naturalWidth > 100.5;
    let widthPercent = widens ? naturalWidth : 100;
    const setWidth = percent => {
      if (!widens) return;
      const centre = scroller.scrollWidth ? (scroller.scrollLeft + scroller.clientWidth / 2) / scroller.scrollWidth : 0;
      widthPercent = Math.min(naturalWidth, Math.max(100, percent));
      svg.style.width = `${Number(widthPercent.toFixed(2))}%`;
      // Narrowed, it keeps its height: only its width shrinks.
      const narrowed = widthPercent < naturalWidth - .5;
      svg.style.minHeight = narrowed ? '0' : '';
      narrowChart(svg, narrowed ? widthPercent / naturalWidth : 1);
      scroller.scrollLeft = Math.max(0, centre * scroller.scrollWidth - scroller.clientWidth / 2);
    };
    if (widens && 100 / naturalWidth >= CHART_MIN_FIT_SCALE) setWidth(100);
    const fitToVisibleBox = zoomed => {
      if (!scroller) return;
      if (zoomed && !svg.dataset.zoomFitted) {
        svg.dataset.zoomFitted = JSON.stringify([svg.style.width, svg.style.minWidth, svg.style.height]);
        const height = svg.getBoundingClientRect().height;
        Object.assign(svg.style, {width: `${scroller.clientWidth}px`, minWidth: '0', height: `${height}px`});
        scroller.scrollLeft = 0;
      } else if (!zoomed && svg.dataset.zoomFitted) {
        const [width, minWidth, height] = JSON.parse(svg.dataset.zoomFitted);
        Object.assign(svg.style, {width, minWidth, height});
        delete svg.dataset.zoomFitted;
      }
    };
    const apply = next => {
      let [x, y, width, height] = next;
      const whole = width >= original[2] && height >= original[3];
      // An area of a narrowed chart is zoomed into at its own width.
      if (!whole && widthPercent < naturalWidth - .5) setWidth(naturalWidth);
      fitToVisibleBox(!whole);
      // The zoomed view takes the proportions of the box the chart or map is shown in (so its size, and what
      // follows it, do not change): the shorter side grows around the centre of the chosen area.
      const box = svg.getBoundingClientRect();
      const ratio = box.width > 0 && box.height > 0 ? box.width / box.height : original[2] / original[3];
      if (width / height > ratio) {
        const grown = width / ratio;
        y -= (grown - height) / 2;
        height = grown;
      } else {
        const grown = height * ratio;
        x -= (grown - width) / 2;
        width = grown;
      }
      // Never further out than the whole map, and always inside it.
      if (width >= original[2] || height >= original[3]) {
        view = [...original];
        fitToVisibleBox(false);
      } else {
        x = Math.min(Math.max(x, original[0]), original[0] + original[2] - width);
        y = Math.min(Math.max(y, original[1]), original[1] + original[3] - height);
        view = [x, y, width, height];
      }
      svg.setAttribute('viewBox', view.map(value => value.toFixed(2)).join(' '));
    };
    const scaleAround = factor => {
      const [x, y, width, height] = view;
      const centerX = x + width / 2, centerY = y + height / 2;
      apply([centerX - width * factor / 2, centerY - height * factor / 2, width * factor, height * factor]);
    };
    const whole = () => view[2] >= original[2] && view[3] >= original[3];
    addZoomToolbar(box,
      () => (whole() && widthPercent < naturalWidth - .5 ? setWidth(widthPercent / CHART_WIDTH_STEP) : scaleAround(.6)),
      () => (whole() ? setWidth(widthPercent * CHART_WIDTH_STEP) : scaleAround(1 / .6)),
      () => { apply([...original]); setWidth(100); },
      widens ? 'Show the whole chart' : 'Show the whole map');
    const toSvg = event => {
      const point = svg.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      const matrix = svg.getScreenCTM();
      return matrix ? point.matrixTransform(matrix.inverse()) : point;
    };
    let start = null;
    let rectangle = null;
    svg.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      start = toSvg(event);
      rectangle = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rectangle.setAttribute('class', `scoring-map-zoom-rect${event.shiftKey && onSelect ? ' is-selecting' : ''}`);
      svg.append(rectangle);
      svg.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    svg.addEventListener('pointermove', event => {
      if (!start || !rectangle) return;
      const point = toSvg(event);
      rectangle.setAttribute('x', Math.min(start.x, point.x));
      rectangle.setAttribute('y', Math.min(start.y, point.y));
      rectangle.setAttribute('width', Math.abs(point.x - start.x));
      rectangle.setAttribute('height', Math.abs(point.y - start.y));
    });
    const finish = event => {
      if (!start || !rectangle) return;
      const point = toSvg(event);
      rectangle.remove();
      const width = Math.abs(point.x - start.x), height = Math.abs(point.y - start.y);
      // A click (or a tiny rectangle) does not zoom; with Shift the rectangle chooses areas instead.
      const area = [Math.min(start.x, point.x), Math.min(start.y, point.y), width, height];
      if (width > view[2] * .02 && height > view[3] * .02) {
        if (event.shiftKey && onSelect) onSelect(area, event); else apply(area);
      } else if (onClick) {
        onClick(document.elementFromPoint(event.clientX, event.clientY), event);
      }
      start = null;
      rectangle = null;
    };
    svg.addEventListener('pointerup', finish);
    svg.addEventListener('pointercancel', () => { rectangle?.remove(); start = null; rectangle = null; });
    return {
      // Centres an area of the map with a margin, never closer than a twelfth of the whole map.
      fit({x, y, width, height}) {
        const grownWidth = Math.max(width * 1.3, original[2] / 12), grownHeight = Math.max(height * 1.3, original[3] / 12);
        apply([x + width / 2 - grownWidth / 2, y + height / 2 - grownHeight / 2, grownWidth, grownHeight]);
      },
      reset: () => apply([...original]),
    };
  }

  function renderCampaignComparisons(pane, payload, environment) {
    if (!environment) return;
    const comparisons = insightItems(payload, 'campaign_comparisons', environment);
    if (!comparisons.length) return;
    const section = document.createElement('section');
    section.className = 'scoring-insight-section';
    const heading = document.createElement('h4');
    heading.className = 'scoring-table-section-title';
    heading.textContent = 'Campaign Comparison';
    // Choose the operator with its buttons (the first Focus operator by default) and its group when it has several, the
    // baseline campaign and the campaign compared with it: by default the previous and the latest campaigns.
    const fallback = focusDefault([...new Map(comparisons.map(item => [item.operator, item])).values()], {withReference: true})[0];
    const {control: operatorControl, value: operator} = insightOperatorPicker('campaign-comparison-operator', comparisons, fallback);
    const groups = comparisons.filter(item => item.operator === operator);
    let groupWrapper = null;
    let chosen = groups[0] || comparisons[0];
    if (groups.length > 1) {
      const {wrapper, value} = insightSelect('campaign-comparison-group', groups.map((item, index) => [String(index), item.title || 'All']), 'Group');
      groupWrapper = wrapper;
      chosen = groups[Number(value)] || groups[0];
    }
    appendResultScope(heading, chosen.context);
    const campaigns = Array.isArray(chosen.campaigns) && chosen.campaigns.length >= 2 ? chosen.campaigns
      : [chosen.previous_campaign, chosen.latest_campaign];
    const campaignOptions = campaigns.map((campaign, index) => [String(index), campaign]);
    const {wrapper: baselineWrapper, value: baselineValue} = insightSelect(
      'campaign-comparison-baseline', campaignOptions, 'Baseline campaign', String(campaigns.length - 2));
    const {wrapper: targetWrapper, value: targetValue} = insightSelect(
      'campaign-comparison-target', campaignOptions, 'Compared campaign', String(campaigns.length - 1));
    const baseline = Number(baselineValue), target = Number(targetValue);
    const comparison = {previous_campaign: campaigns[baseline], latest_campaign: campaigns[target],
      previous_methodology: chosen.methodologies?.[baseline], latest_methodology: chosen.methodologies?.[target],
      ...campaignComparisonRows(chosen, baseline, target)};
    const scale = Math.max(0, ...comparison.rows.map(row => Math.abs(Number(row.delta) || 0)));
    const deltaCell = delta => {
      const cell = {text: insightNumber(delta, 2), className: 'scoring-insight-number scoring-insight-delta'};
      if (delta === null || delta === undefined || !scale || !delta) return cell;
      const alpha = Math.min(1, Math.abs(delta) / scale) * .75;
      cell.style = {background: rgbaOf(delta < 0 ? insightLossColor : insightGainColor, alpha)};
      return cell;
    };
    // A category whose methodology changed is one row with the points of all its KPIs, which follow it without a Δ.
    const comparisonRow = row => {
      if (row.kind === 'category') {
        const group = 'scoring-insight-number scoring-insight-group';
        return [{text: row.service.toUpperCase(), className: 'scoring-insight-group'},
          {text: `${row.kpi} · methodology changed`, className: 'scoring-insight-group',
            title: 'The methodology of this category changed between the two campaigns: its KPIs are compared together.'},
          {text: '', className: group}, {text: insightNumber(row.previous_points, 2), className: group},
          {text: '', className: group}, {text: insightNumber(row.latest_points, 2), className: group}, deltaCell(row.delta)];
      }
      return [row.service.toUpperCase(), row.in_category ? {text: row.kpi, className: 'scoring-insight-kpi'} : row.kpi,
        {text: insightNumber(row.previous_value, 2), className: 'scoring-insight-number'},
        {text: insightNumber(row.previous_points, 2), className: 'scoring-insight-number'},
        {text: insightNumber(row.latest_value, 2), className: 'scoring-insight-number'},
        {text: insightNumber(row.latest_points, 2), className: 'scoring-insight-number'},
        row.in_category ? {text: '—', className: 'scoring-insight-number is-muted'} : deltaCell(row.delta)];
    };
    const table = insightTable(
      ['Service', 'KPI', `${comparison.previous_campaign} KPI value`, `${comparison.previous_campaign} Points`,
        `${comparison.latest_campaign} KPI value`, `${comparison.latest_campaign} Points`, 'Δ Points'],
      comparison.rows.map(comparisonRow),
    );
    const total = document.createElement('p');
    total.className = 'scoring-insight-total';
    const value_ = document.createElement('strong');
    value_.textContent = `${comparison.total_delta >= 0 ? '+' : ''}${insightNumber(comparison.total_delta, 2)}`;
    value_.className = comparison.total_delta < 0 ? 'scoring-insight-loss' : 'scoring-insight-gain';
    total.append('Scoring Points Gap: ', value_);
    const body = document.createElement('div');
    body.className = 'scoring-insight-compare';
    body.append(table, total);
    const note = campaignComparisonNote(comparison);
    if (note) body.append(insightParagraph('scoring-insight-note', note));
    const controls = document.createElement('div');
    controls.className = 'scoring-loss-controls';
    controls.append(...[operatorControl, groupWrapper, baselineWrapper, targetWrapper].filter(Boolean));
    section.append(heading, controls, body);
    pane.append(section);
  }

  // The rows of a Campaign Comparison between two of its campaigns (by position), as comparison_rows builds them
  // (scoring_insights): each KPI with its value and points in both, and the points of the compared campaign minus
  // those of the baseline. A category whose methodology changed between them (a KPI added, removed or with other
  // maximum points) is compared as a whole: a category row with the points of all its KPIs and their Δ, followed by
  // its KPIs without a Δ of their own. From the largest loss (those without a Δ last); the Scoring Points Gap adds
  // up the Δ shown.
  function campaignComparisonRows(comparison, baseline, target) {
    if (!Array.isArray(comparison.kpis) || !Array.isArray(comparison.campaigns)) {
      return {rows: comparison.rows || [], total_delta: comparison.total_delta,
        changed_categories: comparison.changed_categories || []};
    }
    const sameMaximum = 1e-6;
    const maximum = (kpi, index) => (Array.isArray(kpi.max_points) ? Number(kpi.max_points[index]) || 0 : 0);
    const keyOf = kpi => JSON.stringify([kpi.service || '', kpi.category || '']);
    const categories = new Map();
    for (const kpi of comparison.kpis) {
      if (!categories.has(keyOf(kpi))) categories.set(keyOf(kpi), []);
      categories.get(keyOf(kpi)).push(kpi);
    }
    // (Without the maximum points of each campaign, as saved before, every KPI is compared on its own.)
    const grouped = new Map([...categories].filter(([, members]) => members.some(kpi => (
      Array.isArray(kpi.max_points) && Math.abs(maximum(kpi, baseline) - maximum(kpi, target)) > sameMaximum)))
      .map(([key]) => [key, []]));
    const items = [];
    for (const kpi of comparison.kpis) {
      const before = kpi.values?.[baseline] || {}, after = kpi.values?.[target] || {};
      const beforePoints = before.points ?? null, afterPoints = after.points ?? null;
      if (beforePoints === null && afterPoints === null) continue;
      const row = {
        kind: 'kpi', kpi_code: kpi.kpi_code, kpi: kpi.kpi, category: kpi.category, service: kpi.service || '',
        previous_value: before.value ?? null, previous_points: beforePoints,
        latest_value: after.value ?? null, latest_points: afterPoints,
        delta: beforePoints !== null && afterPoints !== null ? afterPoints - beforePoints : null,
      };
      if (grouped.has(keyOf(kpi))) grouped.get(keyOf(kpi)).push({...row, delta: null, in_category: true});
      else items.push({delta: row.delta, rows: [row]});
    }
    // No points: none to compare when the campaign's methodology scores the category, else none to have.
    const categoryPoints = (members, field, index, key) => {
      const points = members.map(row => row[field]).filter(value => value !== null);
      if (points.length) return points.reduce((sum, value) => sum + value, 0);
      return categories.get(key).reduce((sum, kpi) => sum + maximum(kpi, index), 0) > sameMaximum ? null : 0;
    };
    for (const [key, members] of grouped) {
      if (!members.length) continue;
      const [service, category] = JSON.parse(key);
      const before = categoryPoints(members, 'previous_points', baseline, key);
      const after = categoryPoints(members, 'latest_points', target, key);
      const delta = before !== null && after !== null ? after - before : null;
      items.push({delta, rows: [{
        kind: 'category', kpi_code: null, kpi: category, category, service, previous_value: null,
        previous_points: before, latest_value: null, latest_points: after, delta,
      }, ...members]});
    }
    items.sort((left, right) => (left.delta === null) - (right.delta === null) || (left.delta ?? 0) - (right.delta ?? 0));
    return {
      rows: items.flatMap(item => item.rows),
      total_delta: items.reduce((sum, item) => sum + (item.delta ?? 0), 0),
      changed_categories: [...grouped].filter(([, members]) => members.length).map(([key]) => JSON.parse(key)[1]),
    };
  }

  // What a Campaign Comparison says under its table when categories changed methodology between its campaigns
  // (as comparison_note of scoring_insights).
  function campaignComparisonNote(comparison) {
    const names = (comparison.changed_categories || []).filter(Boolean).map(String);
    if (!names.length) return '';
    const campaign = field => {
      const methodology = comparison[`${field}_methodology`];
      return `${comparison[`${field}_campaign`]}${methodology ? ` (${methodology})` : ''}`;
    };
    const listed = names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
    const subject = names.length === 1 ? 'the category is' : 'each category is';
    return `${listed}: the methodology changed between ${campaign('previous')} and ${campaign('latest')}, so ${subject} `
      + 'compared as a whole and its KPIs have no Δ of their own.';
  }

  function renderNotices(notices) {
    const box = root.querySelector('[data-notice-box]');
    const list = root.querySelector('[data-notice-list]');
    if (!box || !list) return;
    // (Results saved before the methodologies told a shared notice once repeat it.)
    const items = [...new Set((Array.isArray(notices) ? notices : []).map(String).filter(Boolean))];
    list.replaceChildren(...items.map(text => Object.assign(document.createElement('li'), {textContent: text})));
    box.hidden = !items.length;
  }

  function renderWarnings(warnings) {
    const box = root.querySelector('[data-warning-box]');
    const list = root.querySelector('[data-warning-list]');
    const items = Array.isArray(warnings) ? warnings : (warnings ? [warnings] : []);
    const legacyCampaignNotice = 'Campaigns are scored separately; the supplied Tableau Prep flow pools campaigns.';
    const visibleItems = items.filter(warning => (
      (typeof warning === 'string' ? warning : displayValue(warning)) !== legacyCampaignNotice
    ));
    list.replaceChildren();
    box.hidden = !visibleItems.length;
    for (const warning of visibleItems) {
      const item = document.createElement('li');
      const message = typeof warning === 'string' ? warning : displayValue(warning);
      const maximumPattern = /(?:maximum achievable scoring )?[0-9]+(?:\.[0-9]+)? of [0-9]+(?:\.[0-9]+)? points/g;
      let offset = 0;
      for (const match of message.matchAll(maximumPattern)) {
        item.append(document.createTextNode(message.slice(offset, match.index)));
        const maximum = document.createElement('strong');
        maximum.className = 'scoring-warning-maximum';
        maximum.textContent = match[0];
        item.append(maximum);
        offset = match.index + match[0].length;
      }
      item.append(document.createTextNode(message.slice(offset)));
      list.append(item);
    }
  }

  const environmentOrder = ['DriveCity', 'DriveConnectionroad', 'Walk', 'Combined'];
  const comparisonScopeFields = ['campaign', 'region', 'cluster', 'city', 'vendor', 'dataset_type'];

  function environmentOf(table) {
    return String(table?.context?.environment ?? table?.environment ?? '');
  }

  function scopeIdentity(context) {
    return JSON.stringify(comparisonScopeFields.map(field => [field, String(firstValue(context, [field], '') ?? '')]));
  }

  function availableScoreEnvironments(tables) {
    const available = new Set();
    for (const table of tables) {
      const environment = environmentOf(table);
      if (!environment || environment === 'Combined') continue;
      available.add(environment);
    }
    const combinedIsAvailable = tables.some(table => environmentOf(table) === 'Combined');
    const ordered = [...available].sort((left, right) => {
      const leftIndex = environmentOrder.indexOf(left);
      const rightIndex = environmentOrder.indexOf(right);
      return (leftIndex < 0 ? environmentOrder.length : leftIndex) - (rightIndex < 0 ? environmentOrder.length : rightIndex) || left.localeCompare(right);
    });
    return ordered.length || combinedIsAvailable ? ['all', ...ordered] : [];
  }

  // The short name of an environment for narrow columns: the last word after its last " - "
  // ("Drive - Connecting Roads" reads Roads and "Drive - City" City).
  function shortEnvironmentLabel(environment) {
    const label = environmentLabel(environment);
    return label.split(' - ').pop().trim().split(/\s+/).pop() || label;
  }

  function environmentLabel(environment) {
    if (environment === 'all' || environment === 'Combined') return 'All Environments';
    const savedLabel = typeof currentResults === 'undefined' ? null
      : currentResults?.configuration?.scope?.environments?.[environment]?.display_name;
    if (savedLabel) return String(savedLabel);
    if (environment === 'DriveCity') return 'Drive City';
    if (environment === 'DriveConnectionroad') return 'Drive Connection Road';
    if (environment === 'Walk') return 'Walk';
    return environment;
  }

  function scoringCoverageTotals(payload, environment) {
    const totals = Array.isArray(payload?.totals) ? payload.totals : [];
    const matching = totals.filter(row => String(row.environment || '') === environment && Number(row.max_points) > 0);
    const overall = matching.filter(row => row.category === 'Overall');
    return overall.length ? overall : matching;
  }

  function scoringEnvironmentIsComplete(payload, tables, environment) {
    const totals = scoringCoverageTotals(payload, environment);
    if (totals.length) return totals.every(row => row.complete_coverage === true);
    const matching = tables.filter(table => environmentOf(table) === environment
      && (table.total?.max_points === undefined || Number(table.total.max_points) > 0));
    const values = matching.flatMap(table => Object.values(table.total?.values || {}))
      .filter(cell => cell.points !== null && cell.points !== undefined);
    return values.length > 0 && values.every(cell => cell.complete === true);
  }

  function scoringCoverageWarnings(payload, savedFilter, environment, {concise = false} = {}) {
    const genericNotice = 'Incomplete KPI or environment coverage: partial points are shown without renormalizing weights; a complete benchmark score is unavailable.';
    const warnings = Array.isArray(payload?.warnings) ? payload.warnings : (payload?.warnings ? [payload.warnings] : []);
    const totals = scoringCoverageTotals(payload, environment);
    if (!totals.length) return warnings;
    const visible = warnings.filter(warning => warning !== genericNotice);
    const detailedNotes = payload?.coverage_notes?.[environment];
    if (Array.isArray(detailedNotes)) return [...visible, ...detailedNotes];
    const incomplete = totals.filter(row => row.complete_coverage === false);
    if (!incomplete.length) return visible;
    const required = Object.entries(payload.configuration?.scope?.environments || {})
      .filter(([, config]) => Number(config.total_points) > 0).map(([name]) => name);
    const missing = new Set();
    const partial = new Set();
    if (environment === 'Combined') {
      for (const total of incomplete) {
        for (const name of required) {
          const contribution = scoringCoverageTotals(payload, name).find(row => row.operator === total.operator
            && comparisonScopeFields.every(field => String(row[field] ?? '') === String(total[field] ?? '')));
          if (!contribution) missing.add(name);
          else if (contribution.complete_coverage === false) partial.add(name);
        }
      }
    }
    if (concise) {
      const label = name => ['DriveConnectionroad', 'Drive Connecting Roads'].includes(name)
        ? 'Drive - Connecting Roads' : environmentLabel(name);
      const names = [...missing].map(label);
      let message = names.length
        ? `Selected Environment has incomplete coverage because ${names.length === 1 ? 'one of its Environments' : 'some of its Environments'} (${names.join(', ')}) ${names.length === 1 ? 'has' : 'have'} no data with the selected filters.`
        : 'Selected Environment has incomplete coverage because required KPI data is missing with the selected filters.';
      if (partial.size) message += ` Incomplete KPI data in: ${[...partial].map(label).join(', ')}.`;
      visible.push(message);
      return visible;
    }
    let message = `${environmentLabel(environment)} has incomplete coverage in ${incomplete.length} of ${totals.length} scoring groups (operator and selected Split by levels).`;
    if (missing.size) message += ` Missing weighted environments in one or more groups: ${[...missing].map(environmentLabel).join(', ')}.`;
    if (partial.size) message += ` Environments with missing valid KPI measurements: ${[...partial].map(environmentLabel).join(', ')}.`;
    if (!missing.size && !partial.size) message += ' One or more required KPI measurements are missing or have no valid samples.';
    const available = incomplete.map(row => Number(row.available_points)).filter(Number.isFinite);
    const maximum = incomplete.map(row => Number(row.max_points)).filter(Number.isFinite);
    const range = values => {
      const low = Math.min(...values), high = Math.max(...values);
      return low === high ? formatChartNumber(low) : `${formatChartNumber(low)}–${formatChartNumber(high)}`;
    };
    if (available.length && maximum.length) message += ` Available maximum points: ${range(available)} of ${range(maximum)}; these are scoring weights, not earned scores.`;
    const cities = savedFilter?.context_filters?.City || [];
    if (missing.size && Array.isArray(cities) && cities.length) {
      message += ` The saved City filter is ${cities.join(', ')}. Only matching City names are included; road routes with different City names are excluded.`;
    }
    if (environment === 'Combined' && (payload.aggregation_levels || savedFilter?.aggregation_levels || []).includes('City')) {
      message += ' City is a Split by level: cities and road routes are scored separately, and environment coverage is checked within each group.';
    }
    message += ' Available points keep their original weights; missing contributions are not scaled up to a complete benchmark.';
    visible.push(message);
    return visible;
  }

  function syncResultEnvironment(tables, {payload = {}, applyCoverageDefault = false} = {}) {
    const environments = availableScoreEnvironments(tables);
    if (!environments.length) {
      currentEffectiveEnvironment = null;
      environmentSelect.disabled = true;
      environmentControl.hidden = false;
      return {environments, effective: null, unavailable: false};
    }
    if (!environments.includes(selectedEnvironment)) {
      selectedEnvironment = 'all';
    }
    if (applyCoverageDefault && !scoringEnvironmentIsComplete(payload, tables, 'Combined')
        && (selectedEnvironment === 'all' || !scoringEnvironmentIsComplete(payload, tables, selectedEnvironment))) {
      const completeEnvironment = environments.find(environment => environment !== 'all'
        && scoringEnvironmentIsComplete(payload, tables, environment));
      if (completeEnvironment) selectedEnvironment = completeEnvironment;
    }
    const currentOptions = [...environmentSelect.options].map(option => option.value);
    if (JSON.stringify(currentOptions) !== JSON.stringify(environments)) {
      environmentSelect.replaceChildren();
      for (const environment of environments) {
        const option = document.createElement('option');
        option.value = environment;
        option.textContent = environment === 'all' ? 'All Environments'
          : String(payload.configuration?.scope?.environments?.[environment]?.display_name || environment);
        environmentSelect.append(option);
      }
    }
    environmentSelect.value = selectedEnvironment;
    environmentSelect.disabled = false;
    environmentControl.hidden = false;
    const combinedIsAvailable = tables.some(table => environmentOf(table) === 'Combined');
    const effective = selectedEnvironment === 'all'
      ? (combinedIsAvailable ? 'Combined' : null)
      : selectedEnvironment;
    currentEffectiveEnvironment = effective;
    return {environments, effective, unavailable: selectedEnvironment === 'all' && !combinedIsAvailable};
  }

  function chartRowsForEnvironment(source, scoreTables, effectiveEnvironment) {
    const rows = normalizeRows(source);
    if (!scoreTables.length) return rows;
    return rows.filter(row => {
      if (String(firstValue(row, ['environment'], '')) !== effectiveEnvironment) return false;
      return scoreTables.some(table => environmentOf(table) === effectiveEnvironment
        && comparisonScopeFields.every(field => String(firstValue(table.context || {}, [field], '') ?? '')
          === String(firstValue(row, [field], '') ?? '')));
    });
  }

  // The content a render draws a moment later (the polygons of the Points Lost Maps).
  let renderLoads = [];

  // Drawing the results again (another operator, environment or option) keeps the card being looked at
  // where it was on the screen: each pane keeps its height until its maps are drawn, and the page
  // scrolls by what the cards above that card grew or shrank.
  function setScoringTheme(id) {
    const theme = scoringThemes.find(item => item.id === id);
    if (!theme || theme.id === activeTheme?.id) return;
    activeTheme = theme;
    applyThemeStyles();
    insightVoiceColor = theme.voice;
    insightDataColor = theme.data;
    insightLossColor = theme.loss;
    insightGainColor = theme.gain;
    insightRankColors = theme.ranks;
    lossLow = hexChannels(theme.loss_ramp[0]);
    lossHigh = hexChannels(theme.loss_ramp[1]);
    // The other tabs are drawn again, in the new theme, when they are opened.
    if (currentResults) renderResult(currentResults, selectedSavedFilter);
    if (currentResultsSavedFilterId) setExportLinks(currentResultsSavedFilterId, true);
    document.dispatchEvent(new CustomEvent('scoring-theme-change', {detail: {theme: theme.id}}));
    fetch('/api/scoring/theme', {
      method: 'PUT', credentials: 'same-origin', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({theme: theme.id}),
    }).catch(() => {});
  }

  function renderResult(savedPayload, savedFilter, panesToRender = [activeResultTab]) {
    const held = panesToRender.map(name => root.querySelector(`[data-result-pane="${name}"]`))
      .filter(pane => pane && pane.childElementCount && pane.offsetHeight).map(pane => [pane, pane.offsetHeight]);
    // The card of the panes that fills most of the window, by its pane, position and class.
    let anchor = null;
    let visible = 0;
    for (const [pane] of held) {
      [...pane.children].forEach((node, index) => {
        const box = node.getBoundingClientRect();
        const shown = Math.min(box.bottom, window.innerHeight) - Math.max(box.top, 0);
        if (shown > visible) {
          visible = shown;
          anchor = {pane, index, className: node.className, top: box.top + window.scrollY};
        }
      });
    }
    // Scrolling by hand (or the position restored after a reload) wins over the card kept in place.
    let interacted = false;
    const stop = () => { interacted = true; };
    const interactions = ['wheel', 'touchstart', 'keydown', 'pointerdown'];
    const keepAnchor = () => {
      const node = anchor && anchor.pane.children[anchor.index];
      if (interacted || scoringViewScrollRestorePending || scoringViewScrollRestoring || !node || node.className !== anchor.className) return;
      // What the content above the card grew or shrank (its place in the page, not on the screen).
      const top = node.getBoundingClientRect().top + window.scrollY;
      window.scrollBy({left: 0, top: top - anchor.top, behavior: 'auto'});
      anchor.top = top;
    };
    held.forEach(([pane, height]) => { pane.style.minHeight = `${height}px`; });
    renderLoads = [];
    try {
      renderResultParts(savedPayload, savedFilter, panesToRender);
    } finally {
      if (held.length) {
        keepAnchor();
        interactions.forEach(type => window.addEventListener(type, stop, {passive: true}));
        Promise.allSettled(renderLoads).then(() => window.requestAnimationFrame(() => {
          held.forEach(([pane]) => { pane.style.minHeight = ''; });
          keepAnchor();
          interactions.forEach(type => window.removeEventListener(type, stop));
        }));
      }
    }
  }

  // NSA vs SA: every tab shows the results of each NR Mode on its own, NSA then SA, as an NSA and an SA calculation
  // show them; How the measurements ran (both NR Modes) comes first in the Summary, and the GAP of Same operator in NSA
  // (SA minus NSA) stays one comparison of both. The page keeps the whole result (its warnings, exports and choices).
  function renderResultParts(savedPayload, savedFilter, panesToRender) {
    const parts = Array.isArray(savedPayload?.nr_mode_parts) ? savedPayload.nr_mode_parts : [];
    if (nrLayoutControl) nrLayoutControl.hidden = parts.length < 2;
    if (nrChartsControl) nrChartsControl.hidden = parts.length < 2;
    if (parts.length < 2) {
      renderResultContent(savedPayload, savedFilter, panesToRender);
      return;
    }
    const sameOperator = String((savedFilter || savedPayload.saved_filter || {}).baseline_operator || '') === '@same-operator-nsa';
    // NSA & SA in the same chart: the Scoring Charts of the whole result (each operator with its NSA and SA bars) and the
    // Scoring Trends with the NSA and SA lines on one axis of quarters.
    const together = selectedNrCharts === 'same';
    const whole = panesToRender.filter(name => (sameOperator && name === 'gap') || (together && name === 'charts'));
    const merged = together ? panesToRender.filter(name => name === 'trends') : [];
    const split = panesToRender.filter(name => !whole.includes(name) && !merged.includes(name));
    const bodies = new Map(parts.map(part => [part.nr_mode, new Map()]));
    let scopeHost = null;
    for (const name of split) {
      const pane = root.querySelector(`[data-result-pane="${name}"]`);
      if (!pane) continue;
      const sections = parts.map(part => {
        const section = document.createElement('section');
        section.className = `scoring-nr-mode-part scoring-nr-mode-${String(part.nr_mode).toLowerCase()}`;
        const heading = document.createElement('h3');
        heading.className = 'scoring-nr-mode-title';
        heading.textContent = part.nr_mode === 'SA' ? 'SA · Standalone' : 'NSA · Non-Standalone';
        const body = document.createElement('div');
        body.className = 'scoring-nr-mode-body';
        section.append(heading, body);
        bodies.get(part.nr_mode).set(name, body);
        return section;
      });
      if (name === 'summary') {
        // (Its cards are styled as those of the panes.)
        scopeHost = document.createElement('div');
        scopeHost.className = 'scoring-nr-mode-body scoring-nr-mode-scope';
      }
      pane.replaceChildren(...(scopeHost && name === 'summary' ? [scopeHost] : []), ...sections);
    }
    for (const part of parts) {
      const partBodies = bodies.get(part.nr_mode);
      renderResultContent({...part, nr_mode_part: part.nr_mode}, savedFilter, split, name => partBodies.get(name));
    }
    if (selectedNrLayout !== 'grouped') {
      // Each panel of NSA then the same panel of SA, each tagged with its NR Mode, their filters once above them.
      for (const name of split) {
        const pane = root.querySelector(`[data-result-pane="${name}"]`);
        if (!pane) continue;
        const [nsa, sa] = parts.map(part => [...(bodies.get(part.nr_mode).get(name)?.children || [])]);
        const pairs = new Map();
        const blocks = interleaveNrModeBlocks(nsa, sa, pairs);
        // The headings and notes of the tab (not cards) the same for NSA and SA are shown once, without a pill.
        const cards = '.scoring-table-mode-section, .scoring-best-network-layout, .scoring-chart-card, .scoring-insight-section, .scoring-result-card';
        const common = new Set();
        for (const [nsaBlock, saBlock] of [...pairs]) {
          if (nsaBlock.matches(cards) || nsaBlock.textContent.trim() !== saBlock.textContent.trim()) continue;
          common.add(nsaBlock);
          pairs.delete(nsaBlock);
          blocks.splice(blocks.indexOf(saBlock), 1);
        }
        nsa.filter(block => !common.has(block)).forEach(block => tagNrModeBlock(block, parts[0].nr_mode));
        sa.filter(block => blocks.includes(block)).forEach(block => tagNrModeBlock(block, parts[1].nr_mode));
        for (const [nsaBlock, saBlock] of pairs) {
          const bar = shareNrModeControls(nsaBlock, saBlock);
          if (bar) blocks.splice(blocks.indexOf(nsaBlock), 0, bar);
        }
        pane.replaceChildren(...(scopeHost && name === 'summary' ? [scopeHost] : []), ...blocks);
      }
    }
    if (merged.length) renderResultContent(nrModeTrendsPayload(savedPayload, parts), savedFilter, merged);
    // Then the whole result: the measurements of both NR Modes, the GAP of Same operator in NSA, the warnings and exports.
    renderResultContent(savedPayload, savedFilter, [...whole, ...(scopeHost ? ['summary-scope'] : [])],
      name => (name === 'summary-scope' ? scopeHost : root.querySelector(`[data-result-pane="${name}"]`)));
    for (const name of split) {
      const pane = root.querySelector(`[data-result-pane="${name}"]`);
      if (pane && tableExports[name]) pane.prepend(tableExports[name]);
    }
  }

  // NSA & SA in the same chart: the Scoring Trends of both NR Modes on one axis of quarters (or periods), where a campaign
  // of NSA and the SA one of the same quarter (2026-Q2 and 2026-Q2-SA) are one point; each operator has an NSA line and
  // a dashed SA line.
  function nrModeQuarter(label) {
    return String(label ?? '').replace(/(^|[_\- ])(NSA|SA)(?=$|[_\- ])/i, '').replace(/[_\- ]+$/, '').trim();
  }

  function nrModeQuarters(...lists) {
    const quarters = [...new Set(lists.flat().map(nrModeQuarter))];
    return typeof globalThis.campaignCompare === 'function' ? quarters.sort((left, right) => globalThis.campaignCompare(left, right) || 0) : quarters;
  }

  // The items of both NR Modes (one per series of each mode), NSA then SA of each operator, on the given quarters.
  function nrModeSeries(nsaItems, saItems, campaignsOf, quarters, pointsKey) {
    const remap = (item, campaigns, mode) => {
      const at = new Map(campaigns.map((campaign, index) => [nrModeQuarter(campaign), index]));
      return {...item, label: `${item.label} ${mode}`, nr_mode: mode, dashed: mode === 'SA',
        [pointsKey]: quarters.map(quarter => (at.has(quarter) ? item[pointsKey]?.[at.get(quarter)] ?? null : null))};
    };
    const series = [];
    const sa = [...saItems];
    for (const item of nsaItems) {
      series.push(remap(item, campaignsOf.NSA, 'NSA'));
      const index = sa.findIndex(other => other.label === item.label);
      if (index >= 0) series.push(remap(sa.splice(index, 1)[0], campaignsOf.SA, 'SA'));
    }
    return [...series, ...sa.map(item => remap(item, campaignsOf.SA, 'SA'))];
  }

  function nrModeTrendsPayload(savedPayload, parts) {
    const active = parts.map(part => activeScoringPayload(part));
    const insights = active.map(part => part?.views?.insights || {});
    const byKey = (items, key) => new Map((Array.isArray(items) ? items : []).map(item => [key(item), item]));
    const trendKey = item => `${item.environment}|${item.title || ''}`;
    const trends = [];
    const nsaTrends = byKey(insights[0].campaign_trends, trendKey), saTrends = byKey(insights[1].campaign_trends, trendKey);
    for (const key of new Set([...nsaTrends.keys(), ...saTrends.keys()])) {
      const nsa = nsaTrends.get(key), sa = saTrends.get(key);
      const quarters = nrModeQuarters(nsa?.campaigns || [], sa?.campaigns || []);
      trends.push({...(nsa || sa), campaigns: quarters,
        series: nrModeSeries(nsa?.series || [], sa?.series || [], {NSA: nsa?.campaigns || [], SA: sa?.campaigns || []}, quarters, 'points'),
        maximum: Math.max(Number(nsa?.maximum) || 0, Number(sa?.maximum) || 0) || (nsa || sa).maximum});
    }
    const summaryKey = item => String(item.environment);
    const summaries = [];
    const nsaSummaries = byKey(insights[0].area_summaries, summaryKey), saSummaries = byKey(insights[1].area_summaries, summaryKey);
    for (const key of new Set([...nsaSummaries.keys(), ...saSummaries.keys()])) {
      const nsa = nsaSummaries.get(key), sa = saSummaries.get(key);
      const quarters = nrModeQuarters(nsa?.campaigns || [], sa?.campaigns || []);
      const campaignsOf = {NSA: nsa?.campaigns || [], SA: sa?.campaigns || []};
      const saAreas = new Map((sa?.areas || []).map(area => [area.label, area]));
      const areas = (nsa?.areas || []).map(area => ({...area,
        rows: nrModeSeries(area.rows || [], saAreas.get(area.label)?.rows || [], campaignsOf, quarters, 'trend')}));
      for (const area of sa?.areas || []) {
        if (!areas.some(other => other.label === area.label)) areas.push({...area, rows: nrModeSeries([], area.rows || [], campaignsOf, quarters, 'trend')});
      }
      // (Each row scores the latest campaign of its NR Mode, with its change from the previous one of that NR Mode.)
      summaries.push({...(nsa || sa), campaigns: quarters, areas, latest_campaign: 'latest campaign',
        previous_campaign: nsa?.previous_campaign || sa?.previous_campaign ? 'previous campaign' : null});
    }
    // The trends replace those of the scoring shown (Best Network or Most Reliable).
    const withTrends = views => ({...(views || {}),
      insights: {...(views?.insights || {}), campaign_trends: trends, area_summaries: summaries}});
    if (effectiveScoring(savedPayload) === 'most_reliable') {
      const reliable = savedPayload.scorings.most_reliable;
      return {...savedPayload, scorings: {...savedPayload.scorings, most_reliable: {...reliable, views: withTrends(reliable.views)}}};
    }
    return {...savedPayload, views: withTrends(savedPayload.views)};
  }

  // The panels of NSA and SA paired by their kind and place (the second Scoring Table of NSA with the second of SA); a
  // panel of SA without one of NSA goes after the SA panel before it.
  function interleaveNrModeBlocks(nsa, sa, pairs = null) {
    const keyOf = seen => block => {
      const name = `${block.tagName}.${block.className}`;
      const count = seen.get(name) || 0;
      seen.set(name, count + 1);
      return `${name}#${count}`;
    };
    const nsaKey = keyOf(new Map());
    const saKey = keyOf(new Map());
    const saByKey = new Map(sa.map(block => [saKey(block), block]));
    const merged = [];
    const placed = new Set();
    for (const block of nsa) {
      merged.push(block);
      const match = saByKey.get(nsaKey(block));
      if (match) {
        merged.push(match);
        placed.add(match);
        pairs?.set(block, match);
      }
    }
    sa.forEach((block, index) => {
      if (placed.has(block)) return;
      const previous = sa.slice(0, index).reverse().find(item => merged.includes(item));
      merged.splice(previous ? merged.indexOf(previous) + 1 : 0, 0, block);
    });
    return merged;
  }

  // The pill of an NR Mode, in the colour of NSA or SA in every tab and theme.
  function nrModeTag(mode) {
    const tag = document.createElement('span');
    tag.className = `scoring-nr-mode-tag scoring-nr-mode-tag-${String(mode).toLowerCase()}`;
    tag.textContent = mode;
    tag.title = mode === 'SA' ? 'Standalone' : 'Non-Standalone';
    return tag;
  }

  function tagNrModeBlock(block, mode) {
    block.classList.add('scoring-nr-mode-block', `scoring-nr-mode-block-${String(mode).toLowerCase()}`);
    (block.querySelector('h4, h3, .scoring-table-section-title') || block).prepend(nrModeTag(mode));
  }

  // Each panel: NSA then SA. The filters of a pair of panels (the operator buttons and the choices whose selection both
  // share) are shown once above them and apply to both; the operators of SA that NSA lacks join its buttons.
  function shareNrModeControls(nsaBlock, saBlock) {
    const selector = '.scoring-loss-controls, .scoring-loss-operators, .scoring-insight-select';
    const controlsOf = (block, within = block) => [...within.querySelectorAll(selector)]
      .filter(element => element.parentElement.closest(selector) === (within === block ? null : within));
    const signature = element => element.textContent.replace(/\s+/g, ' ').trim();
    const share = (control, twins) => {
      const twin = twins.find(other => other.className === control.className && signature(other) === signature(control));
      if (twin) {
        twin.remove();
        return;
      }
      const chips = control.matches('.scoring-loss-operators') && twins.find(other => other.matches('.scoring-loss-operators'));
      if (chips) {
        const shown = new Set([...control.querySelectorAll('button')].map(chip => chip.textContent.trim()));
        const target = [...control.querySelectorAll('.scoring-operator-chips')].at(-1) || control;
        for (const chip of chips.querySelectorAll('button')) if (!shown.has(chip.textContent.trim())) target.append(chip);
        chips.remove();
        return;
      }
      if (control.matches('.scoring-loss-controls')) {
        const box = twins.find(other => other.matches('.scoring-loss-controls'));
        if (!box) return;
        const inner = controlsOf(saBlock, box);
        for (const child of controlsOf(nsaBlock, control)) share(child, inner);
        if (!box.querySelector(selector)) box.remove();
      }
    };
    const controls = controlsOf(nsaBlock);
    if (!controls.length) return null;
    const twins = controlsOf(saBlock);
    const bar = document.createElement('div');
    bar.className = 'scoring-nr-mode-shared-controls';
    bar.append(Object.assign(document.createElement('span'), {className: 'scoring-nr-mode-shared-label', textContent: 'NSA & SA'}));
    for (const control of controls) {
      share(control, twins);
      bar.append(control);
    }
    return bar;
  }

  function renderResultContent(savedPayload, savedFilter, panesToRender,
    paneOf = name => root.querySelector(`[data-result-pane="${name}"]`)) {
    currentResults = savedPayload;
    currentResultsSavedFilterId = savedFilterIdOf(savedFilter || savedPayload.saved_filter || {}) || null;
    const resultFilters = (savedFilter || savedPayload.saved_filter || {}).context_filters;
    resultScopeFilters = resultFilters && typeof resultFilters === 'object' ? resultFilters : {};
    syncResultScoring(savedPayload);
    const payload = activeScoringPayload(savedPayload);
    const shouldRenderPane = name => panesToRender.includes(name);
    const scoringRows = payload.scoring ?? payload.scoring_rows ?? [];
    const gapRows = payload.gap ?? payload.gap_rows ?? [];
    const scoringPane = paneOf('scoring');
    const chartPane = paneOf('charts');
    const gapPane = paneOf('gap');
    // (The parts of NSA vs SA leave the export buttons to their tab.)
    const ownExports = !savedPayload.nr_mode_part;
    const views = payload.views && typeof payload.views === 'object' ? payload.views : {};
    const allScoreTables = normalizeRows(views.score_tables ?? payload.score_tables ?? payload.scoring_views?.score_tables ?? []);
    const allGapTables = normalizeRows(views.gap_tables ?? payload.gap_tables ?? payload.scoring_views?.gap_tables ?? []);
    const allGapSummaryTables = normalizeRows(views.gap_summary_tables ?? payload.gap_summary_tables ?? payload.scoring_views?.gap_summary_tables ?? []);
    const allHierarchyScoreTables = normalizeRows(views.hierarchy_score_tables ?? []);
    const allHierarchyGapTables = normalizeRows(views.hierarchy_gap_tables ?? []);
    const applyCoverageDefault = environmentDefaultSavedFilterId !== currentResultsSavedFilterId;
    const environmentSelection = syncResultEnvironment([...allScoreTables, ...allHierarchyScoreTables], {
      payload, applyCoverageDefault,
    });
    environmentDefaultSavedFilterId = currentResultsSavedFilterId;
    const effectiveEnvironment = environmentSelection.effective;
    const scoreTables = allScoreTables.filter(table => environmentOf(table) === effectiveEnvironment);
    const gapTables = allGapTables.filter(table => environmentOf(table) === effectiveEnvironment);
    const gapSummaryTables = allGapSummaryTables.filter(table => environmentOf(table) === effectiveEnvironment);
    const hierarchyScoreTable = allHierarchyScoreTables.find(table => environmentOf(table) === effectiveEnvironment) || null;
    const hierarchyGapTable = allHierarchyGapTables.find(table => environmentOf(table) === effectiveEnvironment) || null;
    const displayScoreTables = scoreTables.map(tableForSelectedMode);
    const displayGapTables = gapTables.map(tableForSelectedMode);
    const displayGapSummaryTables = gapSummaryTables.map(tableForSelectedMode);
    const displayHierarchyScoreTable = tableForSelectedMode(hierarchyScoreTable);
    const displayHierarchyGapTable = tableForSelectedMode(hierarchyGapTable);
    const thresholdLegend = normalizeRows(views.threshold_legend ?? payload.threshold_legend ?? []);
    const totalsRows = normalizeRows(payload.totals ?? payload.scoring_totals ?? []);
    const detailRows = normalizeRows(scoringRows);
    const hasScoringViews = Array.isArray(views.score_tables) || Array.isArray(payload.score_tables) || Array.isArray(payload.scoring_views?.score_tables);
    const hasGapViews = Array.isArray(views.gap_tables) || Array.isArray(payload.gap_tables) || Array.isArray(payload.scoring_views?.gap_tables)
      || Array.isArray(views.gap_summary_tables) || Array.isArray(payload.gap_summary_tables) || Array.isArray(payload.scoring_views?.gap_summary_tables);
    if (shouldRenderPane('scoring')) {
      if (displayHierarchyScoreTable) {
        renderHierarchyScoringViews(scoringPane, displayHierarchyScoreTable, thresholdLegend);
      } else if (hasScoringViews) {
        renderScoringViews(scoringPane, displayScoreTables, thresholdLegend);
      } else if (totalsRows.length) {
        scoringPane.replaceChildren();
        const summaryHeading = document.createElement('h4');
        summaryHeading.className = 'scoring-table-section-title';
        summaryHeading.textContent = 'Scoring Tables — Summary';
        appendResultScope(summaryHeading);
        const summaryTable = document.createElement('div');
        summaryTable.className = 'scoring-table-section';
        renderTable(summaryTable, totalsRows, 'No scoring summary rows are available.', {hideGapColumns: true});
        scoringPane.append(summaryHeading, summaryTable);
        const detailHeading = document.createElement('h4');
        detailHeading.className = 'scoring-table-section-title';
        detailHeading.textContent = 'Scoring Tables — Breakdown';
        appendResultScope(detailHeading);
        const detailTable = document.createElement('div');
        detailTable.className = 'scoring-table-section';
        renderTable(detailTable, detailRows, 'No KPI detail rows are available.', {hideGapColumns: true});
        scoringPane.append(detailHeading, detailTable);
      } else {
        scoringPane.replaceChildren();
        renderTable(scoringPane, detailRows, 'This Saved Filter has no scoring table rows.', {hideGapColumns: true});
      }
      renderCampaignComparisons(scoringPane, payload, effectiveEnvironment);
      if (tableExports.scoring && ownExports) scoringPane.prepend(tableExports.scoring);
    }
    if (shouldRenderPane('charts')) {
      chartPane.classList.remove('scoring-chart-grid');
      if (hierarchyScoreTable) renderHierarchyCharts(chartPane, hierarchyScoreTable);
      else renderCharts(chartPane, chartRowsForEnvironment(payload.charts ?? [], allScoreTables, effectiveEnvironment), scoreTables);
      renderCategoryAllocation(chartPane, scoreTables, hierarchyScoreTable, allScoreTables);
      renderBestNetworkChart(chartPane, scoreTables, hierarchyScoreTable, allScoreTables);
    }
    if (shouldRenderPane('summary')) renderSummary(paneOf('summary'), payload, effectiveEnvironment);
    if (shouldRenderPane('summary-scope')) renderSummaryScope(paneOf('summary-scope'), payload, effectiveEnvironment);
    if (shouldRenderPane('geographical-areas')) renderGeographicalAreas(paneOf('geographical-areas'), payload, effectiveEnvironment);
    if (shouldRenderPane('trends')) renderTrends(paneOf('trends'), payload, effectiveEnvironment);
    if (shouldRenderPane('points')) {
      renderPointsLost(paneOf('points'), payload, effectiveEnvironment,
        savedFilterIdOf(savedFilter || payload.saved_filter || {}));
    }
    if (shouldRenderPane('gap')) {
      const gapTotals = normalizeRows(payload.gap_totals ?? []);
      if (displayHierarchyGapTable) {
        renderHierarchyGapViews(gapPane, displayHierarchyGapTable, displayHierarchyScoreTable);
      } else if (displayGapSummaryTables.length) {
        renderGapSummaryViews(gapPane, displayGapSummaryTables);
      } else if (hasGapViews) {
        renderGapViews(gapPane, displayGapTables);
      } else if (gapTotals.length) {
        gapPane.replaceChildren();
        for (const [title, rows] of [['GAP Summary', gapTotals], ['KPI GAP Details', normalizeRows(gapRows)]]) {
          const heading = document.createElement('h4');
          heading.className = 'scoring-table-section-title';
          heading.textContent = title;
          appendResultScope(heading);
          const section = document.createElement('div');
          section.className = 'scoring-table-section';
          renderTable(section, rows, 'No comparable GAP rows are available.');
          gapPane.append(heading, section);
        }
      } else {
        renderTable(gapPane, gapRows, 'No GAP rows are available for the selected baseline operator.');
      }
      // The GAP tables, the GAP by part and the KPI GAP Profile are each in their own card.
      const gapTablesCard = document.createElement('section');
      gapTablesCard.className = 'scoring-result-card scoring-gap-tables-card';
      gapTablesCard.append(...gapPane.childNodes);
      if (gapTablesCard.childNodes.length) gapPane.append(gapTablesCard);
      renderGapParts(gapPane, payload, effectiveEnvironment);
      renderKpiGapProfiles(gapPane, payload, effectiveEnvironment);
      if (tableExports.gap && ownExports) gapPane.prepend(tableExports.gap);
    }
    const warnings = payload.warnings ?? savedFilter?.warnings ?? [];
    renderWarnings(scoringCoverageWarnings({...payload, warnings}, savedFilter, effectiveEnvironment));
    // Scaling concerns the Combined scores, not the score of a single environment.
    renderNotices(!effectiveEnvironment || ['all', 'Combined'].includes(effectiveEnvironment) ? payload.notices ?? savedFilter?.notices ?? [] : []);
    setExportLinks(savedFilterIdOf(savedFilter || payload.saved_filter || {}), true);
  }

  // While the selected Saved Filter calculates, the results show an animated progress bar. Each poll updates it in place,
  // so the stripes keep moving instead of starting again.
  function renderCalculating(savedFilter) {
    const progress = Math.round(progressValue(savedFilter));
    const detail = String(valueOf(savedFilter, ['message'], '') || '').trim();
    const update = (element) => {
      element.querySelector('.scoring-calculating-fill').style.width = `${Math.max(6, progress)}%`;
      element.querySelector('.scoring-calculating-bar').setAttribute('aria-valuenow', String(progress));
      element.querySelector('.scoring-calculating-detail').textContent = [`${progress}%`, detail].filter(Boolean).join(' · ');
    };
    const current = resultPanes.map(pane => pane.querySelector(':scope > .scoring-calculating:not(.is-loading)'));
    if (current.length && current.every(Boolean)) {
      current.forEach(update);
      return;
    }
    renderNoResult('');
    for (const pane of resultPanes) {
      const element = document.createElement('div');
      element.className = 'scoring-calculating';
      element.setAttribute('role', 'status');
      element.innerHTML = '<p class="scoring-calculating-title">Calculating Scoring…</p>'
        + '<div class="scoring-calculating-bar" role="progressbar" aria-label="Scoring calculation" aria-valuemin="0" aria-valuemax="100">'
        + '<span class="scoring-calculating-fill"></span></div><p class="scoring-calculating-detail"></p>';
      update(element);
      pane.replaceChildren(element);
    }
  }

  // While the results of a saved Saved Filter load, the results show the same striped bar, moving across its whole width.
  function renderLoadingResults() {
    renderNoResult('');
    for (const pane of resultPanes) {
      const element = document.createElement('div');
      element.className = 'scoring-calculating is-loading';
      element.setAttribute('role', 'status');
      element.innerHTML = '<p class="scoring-calculating-title">Loading Scoring Results…</p>'
        + '<div class="scoring-calculating-bar" role="progressbar" aria-label="Loading scoring results">'
        + '<span class="scoring-calculating-fill" style="width: 100%"></span></div>';
      pane.replaceChildren(element);
    }
  }

  function renderNoResult(text) {
    environmentControl.hidden = false;
    syncResultScoring(null);
    environmentSelect.disabled = true;
    for (const pane of resultPanes) {
      disconnectScoringValueObservers(pane);
      pane.replaceChildren();
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = text;
      pane.append(empty);
    }
    root.querySelector('[data-warning-box]').hidden = true;
    renderNotices([]);
    setExportLinks('', false);
  }

  let pointsLossTimer = 0;

  async function loadSavedFilter(savedFilter, force = false, updateSavedFilterList = true) {
    const id = savedFilterIdOf(savedFilter);
    if (!id) return;
    selectedSavedFilterId = id;
    selectedSavedFilter = savedFilter;
    if (updateSavedFilterList) renderSavedFilters();
    if (!force && resultCache.has(id) && isComplete(savedFilter)) {
      const cached = resultCache.get(id);
      if (currentResultsSavedFilterId !== id || currentResults !== cached) renderResult(cached, savedFilter);
      return;
    }
    if (currentResultsSavedFilterId !== id) {
      currentResults = null;
      currentResultsSavedFilterId = null;
      if (isActive(savedFilter)) renderCalculating(savedFilter);
      else renderLoadingResults();
    }
    try {
      const payload = await requestJson(`${savedFiltersUrl}/${encodeURIComponent(id)}`);
      if (deletedSavedFilterIds.has(id) || selectedSavedFilterId !== id) return;
      const record = payload.saved_filter || payload;
      selectedSavedFilter = record;
      const status = normalizeStatus(record);
      if (isActive(record)) calculatingSavedFilters.set(id, {record, request: ++savedFilterRequests});
      else calculatingSavedFilters.delete(id);
      // A saved result whose CDRs or methodology are gone is shown as it was, saying why.
      if (record.unavailable) setMessage(`${record.unavailable} The saved result is shown.`, 'error');
      if (isComplete(record) || payload.scoring || payload.gap) {
        currentResults = payload;
        resultCache.set(id, payload);
        renderResult(payload, record);
        // A result from the Scoring History is reloaded once its Points Lost Map is ready.
        window.clearTimeout(pointsLossTimer);
        if (payload.points_loss_pending) {
          // The list of Saved Filters (light) is checked until the map is saved; only then are the results loaded
          // and drawn again.
          const loadedAt = record.updated_at;
          const checkPointsLoss = async () => {
            if (selectedSavedFilterId !== id) return;
            try {
              const list = await requestJson(savedFiltersUrl);
              const current = (list.saved_filters || []).find(item => savedFilterIdOf(item) === id);
              if (selectedSavedFilterId !== id) return;
              if (!current || current.updated_at !== loadedAt) {
                resultCache.delete(id);
                loadSavedFilter(selectedSavedFilter, true, false);
                return;
              }
            } catch (_error) {
              // Checked again a moment later.
            }
            pointsLossTimer = window.setTimeout(checkPointsLoss, 5000);
          };
          pointsLossTimer = window.setTimeout(checkPointsLoss, 5000);
        }
      } else if (status === 'failed') {
        currentResults = null;
        currentResultsSavedFilterId = null;
        const error = valueOf(record, ['error', 'error_message', 'last_error'], 'This Saved Filter failed without an error message.');
        renderNoResult(error);
      } else if (isActive(record)) {
        currentResults = null;
        currentResultsSavedFilterId = null;
        renderCalculating(record);
        setExportLinks('', false);
        // Opening filters whose CDRs or methodology changed calculates them again: follow the calculation.
        if (!timer) timer = window.setInterval(refreshSavedFilters, 3500);
      } else {
        currentResults = null;
        currentResultsSavedFilterId = null;
        renderNoResult('Scoring results will appear here when the calculation completes.');
        setExportLinks('', false);
      }
    } catch (error) {
      if (deletedSavedFilterIds.has(id) || selectedSavedFilterId !== id) return;
      currentResults = null;
      currentResultsSavedFilterId = null;
      renderNoResult(error.message || 'The selected filters could not be loaded.');
      setMessage(error.message || 'The selected filters could not be loaded.', 'error');
    }
  }

  async function refreshSavedFilters() {
    if (refreshInFlight) return;
    refreshInFlight = true;
    try {
      const request = ++savedFilterRequests;
      const payload = await requestJson(savedFiltersUrl);
      savedFilters = (Array.isArray(payload) ? payload : (Array.isArray(payload.saved_filters) ? payload.saved_filters : []))
        .filter(savedFilter => !deletedSavedFilterIds.has(savedFilterIdOf(savedFilter)))
        .map(savedFilter => {
          const calculating = calculatingSavedFilters.get(savedFilterIdOf(savedFilter));
          if (!calculating || isActive(savedFilter)) return savedFilter;
          // Requested before the Saved Filter was queued again: it keeps calculating until a later list says it ended.
          if (calculating.request > request) return {...savedFilter, ...calculating.record};
          calculatingSavedFilters.delete(savedFilterIdOf(savedFilter));
          return savedFilter;
        });
      for (const savedFilter of savedFilters) {
        const id = savedFilterIdOf(savedFilter);
        const cached = resultCache.get(id);
        if (cached && (isActive(savedFilter) || cached.saved_filter?.updated_at !== savedFilter.updated_at)) resultCache.delete(id);
      }
      const ordered = sortedSavedFilters(savedFilters);
      const requested = requestedSavedFilterIdPending.value
        ? ordered.find(savedFilter => savedFilterIdOf(savedFilter) === requestedSavedFilterIdPending.value) : null;
      requestedSavedFilterIdPending.value = null;
      const retained = !requested && userSelectedSavedFilter && selectedSavedFilterId
        ? ordered.find(savedFilter => savedFilterIdOf(savedFilter) === selectedSavedFilterId) : null;
      if (requested) reopenScoring();
      // After Close Scoring, none opens on its own.
      selectedSavedFilter = requested || retained || (scoringClosed ? null : ordered.find(isComplete) || ordered[0]) || null;
      selectedSavedFilterId = selectedSavedFilter ? savedFilterIdOf(selectedSavedFilter) : null;
      userSelectedSavedFilter = Boolean(requested || retained);
      renderSavedFilters();
      if (selectedSavedFilter) {
        const hasCached = resultCache.has(savedFilterIdOf(selectedSavedFilter)) && isComplete(selectedSavedFilter);
        if (!hasCached || isActive(selectedSavedFilter)) await loadSavedFilter(selectedSavedFilter, isActive(selectedSavedFilter), false);
        else {
          const id = savedFilterIdOf(selectedSavedFilter);
          const cached = resultCache.get(id);
          if (currentResultsSavedFilterId !== id || currentResults !== cached) renderResult(cached, selectedSavedFilter);
        }
      } else {
        currentResults = null;
        currentResultsSavedFilterId = null;
        renderNoResult('Calculate a scoring or choose Saved Filters to see their results.');
      }
      calculationMatchRefresh = true;
      updateSelection();
      // The opened Saved Filter counts with its latest answer too: a list read before it was queued again must not stop
      // following its calculation.
      const anyActive = savedFilters.some(isActive) || Boolean(selectedSavedFilter && isActive(selectedSavedFilter));
      if (anyActive && !timer) timer = window.setInterval(refreshSavedFilters, 3500);
      if (!anyActive && timer) { window.clearInterval(timer); timer = null; }
    } catch (error) {
      savedFilterList.innerHTML = '';
      const empty = document.createElement('div');
      empty.className = 'scoring-empty';
      empty.textContent = error.message || 'The Saved Filters could not be loaded.';
      savedFilterList.append(empty);
      syncSavedFilterLists();
      setMessage(error.message || 'The Saved Filters could not be loaded.', 'error');
    } finally {
      refreshInFlight = false;
      if (scoringViewScrollRestorePending) restoreScoringViewScroll();
      else persistScoringViewState();
    }
  }

  async function deleteSavedFilter(id) {
    const savedFilter = savedFilters.find(record => savedFilterIdOf(record) === id);
    if (!savedFilter || deletingSavedFilterIds.has(id)) return;
    const copy = `Delete this Saved Filter and its result?${isActive(savedFilter) ? ' Its pending result will be discarded.' : ''} The CDRs and the Scoring History stay.`;
    const accepted = typeof showConfirmDialog === 'function'
      ? await showConfirmDialog(copy, {title: 'Delete Saved Filter', confirmLabel: 'Delete'})
      : window.confirm(copy);
    if (!accepted) return;
    deletingSavedFilterIds.add(id);
    renderSavedFilters();
    try {
      await requestJson(`${savedFiltersUrl}/${encodeURIComponent(id)}`, {method: 'DELETE'});
      deletedSavedFilterIds.add(id);
      resultCache.delete(id);
      savedFilters = savedFilters.filter(record => savedFilterIdOf(record) !== id);
      calculationMatchKey = '';
      if (editingSavedFilter && savedFilterIdOf(editingSavedFilter) === id) stopSavedFilterEdit();
      updateSelection();
      if (selectedSavedFilterId === id) {
        selectedSavedFilterId = null;
        selectedSavedFilter = null;
        currentResults = null;
        currentResultsSavedFilterId = null;
        userSelectedSavedFilter = false;
        renderNoResult('Calculate a scoring or choose Saved Filters to see their results.');
      }
      renderSavedFilters();
      setMessage('Saved Filter and its saved result deleted.', 'success');
      await refreshSavedFilters();
    } catch (error) {
      setMessage(error.message || 'The Saved Filter could not be deleted.', 'error');
    } finally {
      deletingSavedFilterIds.delete(id);
      renderSavedFilters();
    }
  }

  // ``url`` updates an existing Saved Filter instead (its Use newer CDRs button, or Save Changes when it is edited) or
  // saves a copy of one (Save as New Filter, with the name of the copy in ``extra``).
  // Returns whether the Saved Filter was saved.
  async function createSavedFilter(force, {url = savedFiltersUrl, extra = {}} = {}) {
    const datasetIds = selectedDatasetIds();
    if (!datasetIds.length) {
      setMessage('Select one or more CDR datasets first.', 'error');
      return false;
    }
    const missingKinds = datasetKindOrder.filter(kind => !datasetInputs.some(input => input.checked
      && !input.closest('[data-dataset-option]')?.hidden
      && String(input.closest('[data-dataset-option]')?.dataset.datasetKind || '').toLowerCase() === kind));
    if (missingKinds.length) {
      const labels = missingKinds.map(kind => datasetKindLabels[kind]);
      setMessage(`Select at least one dataset from each CDR type: ${labels.join(', ')}.`, 'error');
      return false;
    }
    const baseline = baselineInput.value.trim();
    if (!baseline) {
      setMessage('Enter a baseline operator for the GAP analysis.', 'error');
      baselineInput.focus();
      return false;
    }
    const payload = {...calculationPayload(), force, ...extra};
    // A new scoring always opens on Summary.
    showResultTab('summary');
    syncResultTableControls();
    persistScoringViewState();
    submittingCalculation = true;
    ++calculationMatchRevision;
    window.clearTimeout(calculationMatchTimer);
    calculateButton.disabled = true;
    recalculateButton.disabled = true;
    if (editSaveButton) editSaveButton.disabled = true;
    setMessage(force ? 'Submitting a fresh scoring calculation…' : 'Submitting scoring calculation…');
    try {
      await persistCalculationSelection();
      const body = await requestJson(url, {method: 'POST', body: JSON.stringify(payload)});
      const savedFilter = body.saved_filter || body;
      const id = savedFilterIdOf(savedFilter);
      if (!id) throw new Error('The scoring service did not return the Saved Filter.');
      if (force) recalculatingSavedFilters.add(String(id)); else recalculatingSavedFilters.delete(String(id));
      if (isActive(savedFilter)) {
        selectionStatus = {key: JSON.stringify(calculationPayload()), kind: 'busy',
          text: `${force ? 'Recalculating' : 'Calculating'} the scoring of the selected CDRs and filters…`};
      }
      selectedSavedFilterId = id;
      selectedSavedFilter = savedFilter;
      userSelectedSavedFilter = true;
      showUnmatchedSelection(false);
      reopenScoring();
      if (force) resultCache.delete(id);
      const cached = Boolean(body.cached);
      if (cached && (body.scoring || body.gap)) {
        const result = {saved_filter: savedFilter, scoring: body.scoring || [], gap: body.gap || [], warnings: body.warnings || []};
        resultCache.set(id, result);
      }
      if (body.changed === false) setMessage('The Saved Filter already had this selection: nothing changed.', 'success');
      else if (cached) setMessage('Loaded the previously calculated result.', 'success');
      else if (isActive(savedFilter)) setMessage(selectionStatus.text, 'busy');
      else setMessage('Scoring calculation added to the background queue.', 'success');
      await refreshSavedFilters();
      if (isActive(selectedSavedFilter)) {
        renderSavedFilters();
        if (!timer) timer = window.setInterval(refreshSavedFilters, 3500);
      }
      return true;
    } catch (error) {
      setMessage(error.message || 'The scoring calculation could not be started.', 'error');
      return false;
    } finally {
      submittingCalculation = false;
      calculationMatchKey = '';
      updateSelection();
    }
  }

  datasetInputs.forEach(input => input.addEventListener('change', () => {
    updateSelection();
    scheduleSelectionSave();
  }));
  nrFilter.addEventListener('change', () => {
    // Another NR Mode: its newest campaign with Data, Voice and Speech CDRs, and their CDRs.
    pinnedCdrs = false;
    autoCdrs = {options: autoCdrs.options, incomplete: []};
    applyNrFilter(false);
    setFilterValues('Campaign', []);
    scheduleAutoCdrRefresh({defaultCampaign: true, delay: 0});
  });
  // A Latest campaign choice stands alone: checking one clears the other one and the campaigns, checking a campaign
  // clears it (before the change reaches the panel below).
  const campaignFilterSelect = contextFilterSelects.get('Campaign');
  let campaignChoice = [...(campaignFilterSelect?.selectedOptions || [])].map(option => option.value);
  campaignFilterSelect?.addEventListener('change', () => {
    const chosen = [...campaignFilterSelect.selectedOptions].map(option => option.value).filter(Boolean);
    const presets = chosen.filter(isCampaignPreset), campaigns = chosen.filter(value => !isCampaignPreset(value));
    const addedPreset = presets.find(value => !campaignChoice.includes(value));
    const next = addedPreset ? [addedPreset] : presets.length && campaigns.length ? campaigns : chosen;
    if ([...campaignFilterSelect.options].some(option => option.selected !== next.includes(option.value))) {
      for (const option of campaignFilterSelect.options) option.selected = next.includes(option.value);
      campaignFilterSelect.dispatchEvent(new Event('multiselect:options-updated'));
    }
    campaignChoice = next;
  });
  campaignFilterSelect?.addEventListener('multiselect:options-updated', () => {
    campaignChoice = [...campaignFilterSelect.selectedOptions].map(option => option.value);
  });
  root.addEventListener('change', event => {
    if ([environmentSelect, scoringKindSelect, showKpiValuesToggle, showGapValuesToggle, gapLayoutSelect, nrLayoutSelect, nrChartsSelect].includes(event.target)) {
      if (event.target === environmentSelect) selectedEnvironment = environmentSelect.value;
      if (event.target === nrLayoutSelect) selectedNrLayout = nrLayoutSelect.value === 'grouped' ? 'grouped' : 'interleaved';
      if (event.target === nrChartsSelect) selectedNrCharts = nrChartsSelect.value === 'separate' ? 'separate' : 'same';
      if (event.target === scoringKindSelect) selectedScoring = scoringKindSelect.value === 'most_reliable' ? 'most_reliable' : 'best_network';
      persistScoringViewState();
    }
    if (event.target === scoringProfileSelect) {
      calculationMatchKey = '';
      const profile = scoringProfileById.get(scoringProfileSelect.value);
      if (profile) {
        setMessage(`This calculation will use ${profile.name}.`, 'success');
        scheduleSelectionSave();
      }
      return;
    }
    if (event.target === baselineInput || event.target.matches('[data-aggregation-level], [data-scoring-context-filter]')) {
      if (event.target.matches('[data-scoring-context-filter]') && !restoringSelection) {
        pinnedCdrs = false;
        scheduleAutoCdrRefresh();
      }
      updateSelection();
      scheduleSelectionSave();
      return;
    }
    if (event.target.matches?.('[data-scoring-area-summary] select, [data-scoring-area-time-split], [data-scoring-trend-campaigns]')) {
      syncAreaSummary();
      updateSelection();
      scheduleSelectionSave();
      return;
    }
    if (event.target === themeSelect) {
      setScoringTheme(themeSelect.value);
      return;
    }
    if (event.target === environmentSelect && currentResults) {
      selectedEnvironment = environmentSelect.value;
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    if ((event.target === nrLayoutSelect || event.target === nrChartsSelect) && currentResults) {
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    if (event.target.matches?.('[data-insight-select]') && currentResults) {
      insightSelections.set(event.target.dataset.insightSelect, event.target.value);
      persistScoringViewState();
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    if (event.target === scoringKindSelect && currentResults) {
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    if (event.target === showGapValuesToggle) {
      syncGapValueControls();
      if (currentResults) renderResult(currentResults, selectedSavedFilter, ['scoring']);
      return;
    }
    if (event.target === showKpiValuesToggle && currentResults) {
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    if (event.target === gapLayoutSelect && currentResults) {
      renderResult(currentResults, selectedSavedFilter);
      setExportLinks(currentResultsSavedFilterId, true);
      return;
    }
    const gapSummaryOperator = event.target.closest('[data-gap-summary-operator]');
    if (gapSummaryOperator && currentResults) {
      gapComparisonSelections.set(gapSummaryOperator.dataset.gapSummaryStateKey, gapSummaryOperator.value);
      // The KPI GAP Profile and the Points Lost Map follow the operator chosen here.
      if (gapSummaryOperator.value.startsWith('operator:')) {
        insightSelections.set('gap-insight-operators', JSON.stringify([gapSummaryOperator.value.slice('operator:'.length)]));
        insightSelections.set('gap-insight-operators-offered', JSON.stringify('*'));
        insightSelections.set('gap-insight-follows-comparison', 'true');
      }
      persistScoringViewState();
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    const hierarchyGapOperator = event.target.closest('[data-hierarchy-gap-operator]');
    if (hierarchyGapOperator && currentResults) {
      gapComparisonSelections.set(hierarchyGapOperator.dataset.hierarchyGapStateKey, hierarchyGapOperator.value);
      // The KPI GAP Profile and the Points Lost Map follow the operator chosen here.
      if (hierarchyGapOperator.value.startsWith('operator:')) {
        insightSelections.set('gap-insight-operators', JSON.stringify([hierarchyGapOperator.value.slice('operator:'.length)]));
        insightSelections.set('gap-insight-operators-offered', JSON.stringify('*'));
        insightSelections.set('gap-insight-follows-comparison', 'true');
      }
      persistScoringViewState();
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    const select = event.target.closest('[data-comparison-context]');
    if (!select || !currentResults) return;
    const kind = select.dataset.contextKind;
    if (select.dataset.contextSource === 'chart') {
      const identity = select.selectedOptions[0]?.dataset.contextIdentity;
      if (identity) contextSelections.set(kind, identity);
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    const activeResults = activeScoringPayload(currentResults);
    const views = activeResults.views && typeof activeResults.views === 'object' ? activeResults.views : {};
    const allTables = kind === 'gap'
      ? (views.gap_tables ?? currentResults.gap_tables ?? currentResults.scoring_views?.gap_tables ?? [])
      : kind === 'gap-summary'
        ? (views.gap_summary_tables ?? currentResults.gap_summary_tables ?? currentResults.scoring_views?.gap_summary_tables ?? [])
      : (views.score_tables ?? currentResults.score_tables ?? currentResults.scoring_views?.score_tables ?? []);
    const tables = (Array.isArray(allTables) ? allTables : []).filter(table => environmentOf(table) === currentEffectiveEnvironment);
    const selected = Array.isArray(tables) ? tables[Number(select.value)] : null;
    if (!selected) return;
    contextSelections.set(kind, comparisonIdentity(selected, kind));
    renderResult(currentResults, selectedSavedFilter);
  });
  baselineInput.addEventListener('input', updateSelection);
  calculateButton.addEventListener('click', () => createSavedFilter(false));
  recalculateButton.addEventListener('click', () => createSavedFilter(true));
  closeScoringButton?.addEventListener('click', closeScoring);
  document.addEventListener('click', event => {
    for (const selector of savedFilterSelectors) if (!selector.contains(event.target)) selector.open = false;
  });
  for (const selector of savedFilterSelectors) selector.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    selector.open = false;
    selector.querySelector('summary').focus();
  });
  // Editing a Saved Filter: the Calculation panel, in a dialog, shows its selection with the CDRs of its NR Mode and
  // Campaign until Save Changes gives it the selection of the panel (calculated again) or Cancel Editing (or Escape)
  // gives the panel back its selection before the editing.
  function syncSavedFilterEditing() {
    const editing = Boolean(editingSavedFilter);
    const duplicating = editing && duplicateName !== null;
    if (editBanner) editBanner.hidden = !editing;
    if (editTitle && editing) {
      const id = savedFilterIdOf(editingSavedFilter);
      const named = `${editingSavedFilter.name ? `“${editingSavedFilter.name}” · ` : ''}Filter ID ${id}`;
      editTitle.textContent = duplicating ? `Duplicating Saved Filter ${named}` : `Editing Saved Filter ${named}`;
    }
    if (editText && editing) {
      editText.textContent = duplicating
        ? 'Change the NR Mode, Campaign, filters, Split by, GAP reference, Scoring Trends or methodology of the copy: its CDRs '
          + `follow the NR Mode and Campaign. Save as New Filter calculates it as a new Favourites Filter${duplicateName.trim() ? ` named “${duplicateName.trim()}”` : ''}; `
          + 'the Saved Filter copied stays as it was. Cancel Editing (or Escape) leaves without a copy.'
        : editTextDefault;
    }
    if (editSaveLabel) editSaveLabel.textContent = duplicating ? 'Save as New Filter' : 'Save Changes';
    if (editSaveButton && !duplicating) editSaveButton.disabled = false;
    calculationPanel?.classList.toggle('is-editing-saved-filter', editing);
    calculateButton.hidden = editing;
    recalculateButton.hidden = editing;
    if (closeScoringButton) closeScoringButton.hidden = editing;
    if (editSaveButton) editSaveButton.hidden = !editing;
    if (editCancelButton) editCancelButton.hidden = !editing;
  }

  // ``duplicateName`` edits a copy of the Saved Filter instead, saved as a new one with that name.
  function startSavedFilterEdit(savedFilter, {duplicateName: copyName = null} = {}) {
    if (!editingSavedFilter) selectionBeforeEdit = {selection: calculationSelectionFromControls(), pinned: pinnedCdrs};
    editingSavedFilter = savedFilter;
    duplicateName = copyName;
    for (const selector of savedFilterSelectors) selector.open = false;
    calculationMatchKey = '';
    restoreCalculationSelectionFromSavedFilter(savedFilter, {automaticCdrs: true});
    syncSavedFilterEditing();
    if (editDialog && calculationPanel && !editDialog.open) {
      // The page keeps the height of the panel while it is in the dialog.
      editPanelPlaceholder = document.createElement('div');
      editPanelPlaceholder.style.height = `${calculationPanel.offsetHeight}px`;
      calculationPanel.before(editPanelPlaceholder);
      editDialog.append(calculationPanel);
      editDialog.showModal();
      editDialog.scrollTop = 0;
    }
  }

  function stopSavedFilterEdit({restore = false} = {}) {
    const before = selectionBeforeEdit;
    editingSavedFilter = null;
    duplicateName = null;
    selectionBeforeEdit = null;
    calculationMatchKey = '';
    if (editPanelPlaceholder && calculationPanel) {
      editPanelPlaceholder.replaceWith(calculationPanel);
      editPanelPlaceholder = null;
    }
    if (editDialog?.open) editDialog.close();
    syncSavedFilterEditing();
    if (restore && before) {
      pinnedCdrs = before.pinned;
      keepRestoredContextValues(before.selection?.context_filters);
      applySavedCalculationSelection(before.selection);
      scheduleSelectionSave();
      scheduleAutoCdrRefresh({delay: 0});
    } else {
      updateSelection();
    }
  }

  editSaveButton?.addEventListener('click', async () => {
    const savedFilter = editingSavedFilter;
    if (!savedFilter) return;
    const id = encodeURIComponent(savedFilterIdOf(savedFilter));
    const saved = duplicateName !== null
      ? await createSavedFilter(false, {url: `${savedFiltersUrl}/${id}/duplicate`, extra: {name: duplicateName}})
      : await createSavedFilter(false, {url: `${savedFiltersUrl}/${id}/edit`});
    if (saved && editingSavedFilter === savedFilter) stopSavedFilterEdit();
  });
  editCancelButton?.addEventListener('click', () => stopSavedFilterEdit({restore: true}));
  // Escape closes an open menu of the dialog first, and then cancels the editing.
  let escapeClosedMenu = false;
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && editDialog?.open) {
      escapeClosedMenu = Boolean(editDialog.querySelector('.multiselect-menu:not([hidden])'));
    }
  }, true);
  editDialog?.addEventListener('cancel', event => {
    event.preventDefault();
    if (escapeClosedMenu) {
      // The menus close as with a click outside them.
      escapeClosedMenu = false;
      editDialog.dispatchEvent(new MouseEvent('click', {bubbles: true}));
      return;
    }
    stopSavedFilterEdit({restore: true});
  });

  // The filters of the Saved Filter stay in sight while it is named: a copy of its card, without its name badge.
  function savedFilterCardReference(event, id) {
    const card = event.target.closest('.saved-filter-row')?.querySelector('.saved-filter-item')
      || root.querySelector(`.saved-filter-item[data-saved-filter-id="${CSS.escape(id)}"]`);
    if (!card) return null;
    const reference = document.createElement('div');
    reference.className = 'saved-filter-item saved-filter-reference';
    reference.append(...Array.from(card.children, child => child.cloneNode(true))
      .filter(child => !child.classList?.contains('saved-filter-head') && !child.classList?.contains('saved-filter-name')));
    return reference;
  }

  // The name, pin, duplicate and Use newer CDRs buttons of a Saved Filter, in the lists and in the selected card of
  // the Scoring Results dropdown. Returns whether the click was one of them.
  async function savedFilterAction(event) {
    const pin = event.target.closest('[data-saved-filter-pin]');
    const rename = event.target.closest('[data-saved-filter-rename]');
    const useNewer = event.target.closest('[data-saved-filter-newer]');
    const duplicate = event.target.closest('[data-saved-filter-duplicate]');
    if (pin || rename || useNewer || duplicate) {
      event.preventDefault();
      const id = pin?.dataset.savedFilterPin || rename?.dataset.savedFilterRename || useNewer?.dataset.savedFilterNewer
        || duplicate?.dataset.savedFilterDuplicate;
      const savedFilter = savedFilters.find(record => savedFilterIdOf(record) === id);
      if (!savedFilter) return true;
      if (duplicate) {
        // A copy of its selection opens in the edit dialog, to change it and save it as a new Saved Filter.
        const name = await showTextInputDialog('Name of the copy', {
          reference: savedFilterCardReference(event, id),
          eyebrow: 'Saved Filter', title: 'Duplicate Saved Filter', value: savedFilter.name ? `${savedFilter.name} (copy)` : '',
          placeholder: 'For example 2026-Q3 London', maxLength: 120, confirmLabel: 'Edit Filters of the Copy',
          note: 'The copy opens with the filters of this Saved Filter in a dialog: change them (for example its Campaign) and '
            + 'Save as New Filter saves it as a new Favourites Filter, right after this one, which stays as it is.',
        });
        if (name === null || name === undefined) return true;
        startSavedFilterEdit(savedFilter, {duplicateName: String(name)});
        return true;
      }
      if (useNewer) {
        // The same Saved Filter, updated with the CDRs that replace the older ones and calculated again.
        const replacements = new Map((savedFilter.newer_cdrs || []).map(item => [String(item.id), String(item.replaced_by)]));
        restoreCalculationSelectionFromSavedFilter({
          ...savedFilter,
          dataset_ids: [...new Set((savedFilter.dataset_ids || []).map(value => replacements.get(String(value)) || String(value)))],
        });
        for (const selector of savedFilterSelectors) selector.open = false;
        await createSavedFilter(false, {url: `${savedFiltersUrl}/${encodeURIComponent(id)}/use-newer-cdrs`});
        return true;
      }
      // Edit Filters opens its selection in a dialog to change it (a changed name is saved first).
      let edit = false;
      const changes = pin ? {pinned: !savedFilter.pinned} : await (async () => {
        const answer = await showTextInputDialog('Name', {
          reference: savedFilterCardReference(event, id),
          eyebrow: 'Saved Filter', title: 'Edit Saved Filter', value: savedFilter.name || '',
          placeholder: 'For example 2026-Q3 London', maxLength: 120, confirmLabel: 'Save Name',
          secondaryLabel: 'Edit Filters',
          note: 'The name is shown as a badge on top of its card (empty: its filters only). Edit Filters changes its NR '
            + 'Mode, Campaign, filters, Split by, GAP reference and methodology in a dialog; its CDRs follow the NR Mode and Campaign.',
        });
        if (!answer) return null;
        edit = answer.choice === 'secondary';
        const unchanged = answer.value.trim().replace(/\s+/g, ' ') === (savedFilter.name || '');
        return edit && unchanged ? null : {name: answer.value};
      })();
      if (changes) {
        try {
          await requestJson(`${savedFiltersUrl}/${encodeURIComponent(id)}`, {method: 'PATCH', body: JSON.stringify(changes)});
          await refreshSavedFilters();
        } catch (error) {
          setMessage(error.message || 'The Saved Filter could not be updated.', 'error');
          return true;
        }
      }
      if (edit) startSavedFilterEdit(savedFilters.find(record => savedFilterIdOf(record) === id) || savedFilter);
      return true;
    }
    return false;
  }

  for (const list of savedFilterLists) list.addEventListener('click', async event => {
    if (await savedFilterAction(event)) return;
    const remove = event.target.closest('[data-delete-saved-filter-id]');
    if (remove) {
      deleteSavedFilter(remove.dataset.deleteSavedFilterId);
      return;
    }
    const card = event.target.closest('[data-saved-filter-id]');
    if (card) {
      // A click on the card folds or unfolds the rest of its details.
      const row = card.closest('.saved-filter-row');
      const unfolded = unfoldedSavedFilterIds(list);
      const open = !unfolded.has(card.dataset.savedFilterId);
      if (open) unfolded.add(card.dataset.savedFilterId);
      else unfolded.delete(card.dataset.savedFilterId);
      row?.classList.toggle('is-expanded', open);
      card.setAttribute('aria-expanded', String(open));
      return;
    }
    const button = event.target.closest('[data-saved-filter-use]');
    if (!button) return;
    const savedFilter = savedFilters.find(record => savedFilterIdOf(record) === button.dataset.savedFilterUse);
    if (!savedFilter) return;
    await useSavedFilter(savedFilter, {fromDropdown: savedFilterSelectors.find(selector => selector.contains(button))});
  });

  // Use Filter: the Saved Filter becomes the one of the module, its selection goes to the Calculation panel and its result
  // is loaded. Used from a selector (``fromDropdown``) the page stays there; otherwise it goes to its results. ``source``
  // tells App Events where it was chosen (navigator: the Filter Navigator).
  async function useSavedFilter(savedFilter, {fromDropdown = null, source = ''} = {}) {
    if (editingSavedFilter) stopSavedFilterEdit();
    userSelectedSavedFilter = true;
    selectedSavedFilterId = savedFilterIdOf(savedFilter);
    selectedSavedFilter = savedFilter;
    restoreCalculationSelectionFromSavedFilter(savedFilter);
    showUnmatchedSelection(false);
    reopenScoring();
    // Opening it with Use Filter counts as a use.
    requestJson(`${savedFiltersUrl}/${encodeURIComponent(selectedSavedFilterId)}/use${source ? `?source=${encodeURIComponent(source)}` : ''}`,
      {method: 'POST'})
      .then(() => refreshSavedFilters())
      .catch(() => { /* The count is not essential to open it. */ });
    for (const selector of savedFilterSelectors) selector.open = false;
    // A Saved Filter opened from the Saved Filters panel takes the page to its results at once, and again once they are
    // drawn (they change the height of the page).
    const showResults = () => {
      const resultsPanel = root.querySelector('.scoring-results-panel');
      if (resultsPanel && typeof showSectionAtTop === 'function') showSectionAtTop(resultsPanel);
      else resultsPanel?.scrollIntoView({block: 'start'});
    };
    if (fromDropdown) fromDropdown.querySelector('summary').focus();
    else showResults();
    persistScoringViewState();
    await loadSavedFilter(savedFilter, true);
    if (!fromDropdown && selectedSavedFilterId === savedFilterIdOf(savedFilter)) showResults();
  }

  // The words of a text as the search of the Filter Navigator compares them: in lower case, without accents, split at
  // anything but letters and digits.
  function savedFilterNavigatorWords(text) {
    return String(text ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase()
      .split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  }

  // Whether a word typed finds a word of a Saved Filter: the start of it, but a number of one or two digits is the whole
  // word (2 finds Latest 2 campaigns, not 2026-Q3).
  function savedFilterNavigatorWordMatches(word, typed) {
    return /^\p{N}{1,2}$/u.test(typed) ? word === typed : word.startsWith(typed);
  }

  // Whether the words of a Saved Filter hold every word typed, in any order.
  function savedFilterNavigatorMatches(words, query) {
    return savedFilterNavigatorWords(query).every(typed => words.some(word => savedFilterNavigatorWordMatches(word, typed)));
  }

  // The Favourites Filters the search finds: those with every word typed, where two words typed one after the other stay
  // together when some of them hold them one after the other in one of their texts (latest camp finds Latest campaign,
  // not Latest 2 campaigns); words that no Favourites Filter holds together are found anywhere.
  function savedFilterNavigatorFound(entries, query) {
    const typed = savedFilterNavigatorWords(query);
    let found = entries.filter(entry => savedFilterNavigatorMatches(entry.words, query));
    for (let index = 0; index + 1 < typed.length; index += 1) {
      const together = entry => entry.phrases.some(words => words.some((word, at) => at + 1 < words.length
        && savedFilterNavigatorWordMatches(word, typed[index]) && savedFilterNavigatorWordMatches(words[at + 1], typed[index + 1])));
      if (found.some(together)) found = found.filter(together);
    }
    return found;
  }

  // What the Filter Navigator shows of a Favourites Filter, from its filters (not from its name): its branches (the areas
  // it filters, or Nationwide, then its NR Mode), its leaf (its Campaign: the automatic choice with the campaigns it stood
  // for last time, or its campaigns), the Operator and Vendor it filters, and its other fields, which tell it apart from
  // another one on the same leaf. Its words are those the search looks in.
  function savedFilterNavigatorEntry(savedFilter) {
    const id = savedFilterIdOf(savedFilter);
    const scopes = savedFilterScopes(savedFilter);
    const areas = scopes.filter(scope => ['all', 'region', 'cluster', 'city'].includes(scope.dimension));
    const filtered = scopes.filter(scope => !areas.includes(scope));
    const mode = String(valueOf(savedFilter, ['nr_mode'], '') || '');
    const modeLabel = mode === 'NSA+SA' ? 'NSA vs SA' : (mode || 'All NR Modes');
    const display = values => [...new Set(values.map(value => hierarchyDisplayValue({level: 'Campaign', value})))]
      .sort((left, right) => insightCampaignKey(left) - insightCampaignKey(right) || left.localeCompare(right));
    const campaignFilter = savedSavedFilterValues(savedFilter, 'Campaign');
    const choice = campaignFilter.find(isCampaignPreset);
    const campaigns = choice ? display(Array.isArray(savedFilter?.resolved_campaigns) ? savedFilter.resolved_campaigns : [])
      : display(campaignFilter.length ? campaignFilter : savedFilterCampaigns(savedFilter).filter(value => value !== 'Unspecified'));
    const campaign = choice ? campaignPresetLabels[choice] : (campaigns.join(', ') || 'All Campaigns');
    const filteredValue = dimension => filtered.find(scope => scope.dimension === dimension)?.text;
    const baseline = valueOf(savedFilter, ['baseline_operator'], 'EE');
    const reference = baseline === '@same-operator-nsa' ? 'Same operator in NSA' : baseline;
    const methodology = valueOf(savedFilter, ['scoring_profile_name', 'profile_name'], '') || 'Default';
    const details = [
      ['operator', 'Operator', filteredValue('operator') || 'All Operators'],
      ['vendor', 'Vendor', filteredValue('vendor') || 'All Vendors'],
      ['', 'Split by', savedFilterLevels(savedFilter)],
      ['', 'GAP Reference', reference],
      ['', 'Scoring Methodology', methodology],
      ['', 'Geographical Areas', savedFilterAreaSummaryParts(savedFilter).map(([, label, value]) => `${label}: ${value}`).join(' · ')],
      ['', 'Scoring Trends', `${savedFilterTrendCampaigns(savedFilter)} · Time split: ${savedFilterTimeSplit(savedFilter)}`],
      ['', 'CDRs', savedFilterCdrNames(savedFilter).join(', ') || savedFilterCdrSummary(savedFilter)],
    ];
    const areaKey = areas.map(scope => `${scope.dimension}:${scope.text}`).join('|');
    // Each text apart, to find words typed together; all their words, to find words typed anywhere.
    const phrases = [savedFilter.name, ...areas.map(scope => scope.text), ...filtered.map(scope => scope.text), modeLabel,
      campaign, campaigns.join(' '), reference, methodology, `Filter ID ${id}`].map(savedFilterNavigatorWords);
    return {
      id, name: savedFilter.name || '', status: normalizeStatus(savedFilter), areas, areaKey, mode, modeLabel,
      modeKey: `${areaKey}#${mode}`, campaign, campaigns: choice ? campaigns : [], filtered, details, distinct: [],
      phrases, words: phrases.flat(),
    };
  }

  // The tree of the Filter Navigator from its entries (in the order of the list): each area in the order of its first
  // Favourites Filter, its NR Modes (NSA, SA, NSA vs SA) and their Favourites Filters. Those that would read alike on a
  // leaf get, in ``distinct``, the fields that tell them apart (their Filter ID when nothing does).
  function savedFilterNavigatorTree(entries) {
    const modeOrder = mode => (index => (index < 0 ? 3 : index))(['NSA', 'SA', 'NSA+SA'].indexOf(mode));
    const areas = [];
    for (const entry of entries) {
      let area = areas.find(item => item.key === entry.areaKey);
      if (!area) areas.push(area = {key: entry.areaKey, areas: entry.areas, modes: []});
      let mode = area.modes.find(item => item.mode === entry.mode);
      if (!mode) area.modes.push(mode = {key: entry.modeKey, mode: entry.mode, label: entry.modeLabel, entries: []});
      mode.entries.push(entry);
    }
    for (const area of areas) {
      area.modes.sort((left, right) => modeOrder(left.mode) - modeOrder(right.mode));
      for (const mode of area.modes) {
        const leaves = new Map();
        for (const entry of mode.entries) {
          const key = [entry.campaign, ...entry.campaigns].join('|');
          leaves.set(key, [...(leaves.get(key) || []), entry]);
        }
        for (const alike of leaves.values()) {
          const differing = alike.length < 2 ? [] : alike[0].details.map((_detail, index) => index)
            .filter(index => new Set(alike.map(entry => entry.details[index][2])).size > 1);
          for (const entry of alike) {
            entry.distinct = differing.map(index => entry.details[index]);
            if (alike.length > 1 && !differing.length) entry.distinct = [['', 'Filter ID', entry.id]];
          }
        }
      }
    }
    return areas;
  }

  // A text with the starts of its words that the search found marked.
  function savedFilterNavigatorHighlight(text, query) {
    const value = String(text ?? '');
    const typed = savedFilterNavigatorWords(query);
    if (!typed.length) return [value];
    const nodes = [];
    let last = 0;
    for (const match of value.matchAll(/[\p{L}\p{N}]+/gu)) {
      const word = savedFilterNavigatorWords(match[0])[0] || '';
      const length = Math.max(0, ...typed.filter(token => savedFilterNavigatorWordMatches(word, token)).map(token => token.length));
      if (!length) continue;
      const mark = document.createElement('mark');
      mark.textContent = value.slice(match.index, match.index + length);
      nodes.push(value.slice(last, match.index), mark);
      last = match.index + length;
    }
    nodes.push(value.slice(last));
    return nodes.filter(node => node !== '');
  }

  // A branch of the tree (an area or an NR Mode), with the number of its Favourites Filters, and the group of its children.
  function savedFilterNavigatorBranch(key, level, content, count, open) {
    const item = document.createElement('div');
    item.setAttribute('role', 'treeitem');
    item.setAttribute('aria-level', String(level));
    item.setAttribute('aria-expanded', String(open));
    item.tabIndex = -1;
    item.className = `saved-filter-navigator-branch is-level-${level}`;
    item.dataset.navigatorKey = key;
    const label = document.createElement('div');
    label.className = 'saved-filter-navigator-label';
    const chevron = document.createElement('span');
    chevron.className = 'saved-filter-navigator-chevron';
    chevron.setAttribute('aria-hidden', 'true');
    chevron.textContent = '▶';
    const badge = document.createElement('span');
    badge.className = 'saved-filter-navigator-count';
    badge.textContent = String(count);
    badge.title = `${count} Favourites Filter${count === 1 ? '' : 's'}`;
    label.append(chevron, ...content, badge);
    const group = document.createElement('div');
    group.setAttribute('role', 'group');
    group.className = 'saved-filter-navigator-group';
    group.hidden = !open;
    item.append(label, group);
    return {item, group};
  }

  // A Favourites Filter on its leaf: its Campaign, the campaigns it stands for, what it filters and what tells it apart,
  // its status when it is not calculated, In Use for the one in use, and its name below.
  function savedFilterNavigatorLeaf(entry, query, inUse) {
    const item = document.createElement('div');
    item.setAttribute('role', 'treeitem');
    item.setAttribute('aria-level', '3');
    item.setAttribute('aria-selected', String(inUse));
    item.tabIndex = -1;
    item.className = 'saved-filter-navigator-leaf';
    item.dataset.navigatorKey = `filter:${entry.id}`;
    item.dataset.savedFilterNavigatorUse = entry.id;
    item.title = inUse ? 'This Saved Filter is the one in use' : `Use this Saved Filter: ${entry.name || `Filter ID: ${entry.id}`}`;
    const label = document.createElement('div');
    label.className = 'saved-filter-navigator-label';
    const text = document.createElement('span');
    text.className = 'saved-filter-navigator-leaf-text';
    const main = document.createElement('span');
    main.className = 'saved-filter-navigator-leaf-main';
    const campaign = document.createElement('span');
    campaign.className = 'saved-filter-navigator-campaign';
    campaign.append(...savedFilterNavigatorHighlight(entry.campaign, query));
    main.append(campaign);
    if (entry.campaigns.length) {
      const campaigns = document.createElement('span');
      campaigns.className = 'saved-filter-navigator-campaigns';
      campaigns.append(...savedFilterNavigatorHighlight(entry.campaigns.join(' · '), query));
      main.append(campaigns);
    }
    const chips = [...entry.filtered.map(scope => [scope.dimension, scope.title, scope.text]),
      ...entry.distinct.filter(([dimension]) => !entry.filtered.some(scope => scope.dimension === dimension && dimension))
        .map(([dimension, name, value]) => [dimension, `${name}: ${value}`, dimension ? value : `${name}: ${value}`])];
    for (const [dimension, title, value] of chips) {
      const chip = document.createElement('span');
      chip.className = 'saved-filter-navigator-chip';
      if (dimension) chip.dataset.dimension = dimension;
      chip.title = title;
      chip.append(...savedFilterNavigatorHighlight(value, query));
      main.append(chip);
    }
    if (entry.status !== 'completed') {
      const status = document.createElement('span');
      status.className = 'scoring-status';
      status.dataset.status = entry.status;
      status.textContent = entry.status === 'saved' ? 'not calculated' : entry.status;
      main.append(status);
    }
    if (inUse) {
      const badge = document.createElement('span');
      badge.className = 'saved-filter-navigator-in-use';
      badge.textContent = 'In Use';
      main.append(badge);
    }
    text.append(main);
    if (entry.name) {
      const name = document.createElement('span');
      name.className = 'saved-filter-navigator-name';
      name.append(...savedFilterNavigatorHighlight(entry.name, query));
      text.append(name);
    }
    label.append(text);
    item.append(label);
    return item;
  }

  function renderSavedFilterNavigator() {
    if (!navigatorTree) return;
    const query = navigatorSearch?.value || '';
    const searching = savedFilterNavigatorWords(query).length > 0;
    const entries = sortedSavedFilters(savedFilters).filter(savedFilter => savedFilter.pinned).map(savedFilterNavigatorEntry);
    // What tells two Favourites Filters apart is found among all of them, so it does not change while searching.
    const tree = savedFilterNavigatorTree(entries);
    const found = new Set(savedFilterNavigatorFound(entries, query).map(entry => entry.id));
    const inUseId = selectedSavedFilterId && !selectionUnmatched && !scoringClosed ? selectedSavedFilterId : '';
    const focusedKey = navigatorTree.contains(document.activeElement) ? document.activeElement.dataset?.navigatorKey : '';
    const isOpen = key => (searching ? !navigatorSearchCollapsed.has(key) : navigatorExpanded.has(key));
    const items = [];
    for (const area of tree) {
      const areaCount = area.modes.reduce((total, mode) => total + mode.entries.filter(entry => found.has(entry.id)).length, 0);
      if (!areaCount) continue;
      const areaLabels = area.areas.map(scope => {
        const label = document.createElement('span');
        label.className = 'saved-filter-navigator-area';
        label.dataset.dimension = scope.dimension;
        label.title = scope.title;
        label.append(...savedFilterNavigatorHighlight(scope.text, query));
        return label;
      });
      const areaBranch = savedFilterNavigatorBranch(area.key, 1, areaLabels, areaCount, isOpen(area.key));
      for (const mode of area.modes) {
        const shown = mode.entries.filter(entry => found.has(entry.id));
        if (!shown.length) continue;
        const modeLabel = document.createElement('span');
        modeLabel.className = 'saved-filter-navigator-mode';
        modeLabel.dataset.nrMode = mode.mode === 'NSA+SA' ? 'nsa-vs-sa' : mode.mode.toLowerCase();
        modeLabel.title = `NR Mode: ${mode.label}`;
        if (mode.mode === 'NSA+SA') {
          for (const [part, kind] of [['NSA', 'nsa'], [' vs ', ''], ['SA', 'sa']]) {
            const piece = document.createElement('span');
            if (kind) piece.dataset.nrMode = kind;
            piece.append(...savedFilterNavigatorHighlight(part, query));
            modeLabel.append(piece);
          }
        } else modeLabel.append(...savedFilterNavigatorHighlight(mode.label, query));
        const modeBranch = savedFilterNavigatorBranch(mode.key, 2, [modeLabel], shown.length, isOpen(mode.key));
        modeBranch.group.append(...shown.map(entry => savedFilterNavigatorLeaf(entry, query, entry.id === inUseId)));
        areaBranch.group.append(modeBranch.item);
      }
      items.push(areaBranch.item);
    }
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'saved-filter-navigator-empty';
      empty.textContent = entries.length ? 'No Favourites Filter has every word typed.'
        : 'No Favourites Filters yet: star (☆) a scoring to keep its filters here.';
      items.push(empty);
    }
    navigatorTree.replaceChildren(...items);
    if (navigatorCount) {
      navigatorCount.textContent = searching ? `${found.size} of ${entries.length} Favourites Filters`
        : `${entries.length} Favourites Filter${entries.length === 1 ? '' : 's'}`;
    }
    // The tree is one stop of Tab: on the item focused before, else the one in use, else the first one.
    const visible = visibleNavigatorItems();
    const current = visible.find(item => item.dataset.navigatorKey === focusedKey)
      || visible.find(item => item.getAttribute('aria-selected') === 'true') || visible[0];
    if (current) {
      current.tabIndex = 0;
      if (focusedKey) current.focus();
    }
  }

  function visibleNavigatorItems() {
    return navigatorTree ? [...navigatorTree.querySelectorAll('[role="treeitem"]')]
      .filter(item => !item.parentElement?.closest('[role="group"][hidden]')) : [];
  }

  function focusNavigatorItem(item) {
    for (const other of navigatorTree.querySelectorAll('[role="treeitem"]')) other.tabIndex = -1;
    item.tabIndex = 0;
    item.focus();
    item.querySelector('.saved-filter-navigator-label')?.scrollIntoView({block: 'nearest'});
  }

  function toggleNavigatorBranch(item, open) {
    const key = item.dataset.navigatorKey;
    item.setAttribute('aria-expanded', String(open));
    const group = item.querySelector(':scope > [role="group"]');
    if (group) group.hidden = !open;
    if (savedFilterNavigatorWords(navigatorSearch?.value).length) {
      if (open) navigatorSearchCollapsed.delete(key);
      else navigatorSearchCollapsed.add(key);
    } else if (open) navigatorExpanded.add(key);
    else navigatorExpanded.delete(key);
  }

  function openSavedFilterNavigator(origin = null) {
    if (!navigatorDialog || navigatorDialog.open) return;
    navigatorOrigin = origin;
    for (const selector of savedFilterSelectors) selector.open = false;
    if (navigatorSearch) navigatorSearch.value = '';
    navigatorSearchCollapsed.clear();
    // The branches of the Saved Filter in use open with it.
    const inUse = savedFilters.find(record => record.pinned && savedFilterIdOf(record) === selectedSavedFilterId);
    if (inUse) {
      const entry = savedFilterNavigatorEntry(inUse);
      navigatorExpanded.add(entry.areaKey);
      navigatorExpanded.add(entry.modeKey);
    }
    renderSavedFilterNavigator();
    // With a mouse the search is ready to type in; on a touch screen its keyboard would cover the tree, so the dialog
    // takes the focus (the search is out of reach while it opens, or the dialog would give it the focus).
    const typing = Boolean(window.matchMedia?.('(pointer: fine)').matches);
    if (navigatorSearch && !typing) navigatorSearch.disabled = true;
    navigatorDialog.showModal();
    if (navigatorSearch) navigatorSearch.disabled = false;
    navigatorTree.querySelector('[aria-selected="true"] > .saved-filter-navigator-label')?.scrollIntoView({block: 'center'});
    if (typing) navigatorSearch?.focus();
    else navigatorDialog.focus();
  }

  // Choosing a Favourites Filter in the Filter Navigator uses it, as Use Filter on its card (the one in use only closes it).
  function useNavigatorFilter(id) {
    const savedFilter = savedFilters.find(record => savedFilterIdOf(record) === String(id));
    if (!savedFilter) return;
    const origin = navigatorOrigin;
    navigatorDialog.close();
    if (String(id) === selectedSavedFilterId && !selectionUnmatched && !scoringClosed) return;
    useSavedFilter(savedFilter, {fromDropdown: origin, source: 'navigator'});
  }

  root.addEventListener('click', event => {
    const opener = event.target.closest('[data-saved-filter-navigator-open]');
    if (!opener) return;
    // Inside the selector, the button does not open its list.
    event.preventDefault();
    openSavedFilterNavigator(savedFilterSelectors.find(selector => selector.contains(opener)) || null);
  });
  navigatorDialog?.querySelector('[data-saved-filter-navigator-close]')?.addEventListener('click', () => navigatorDialog.close());
  navigatorSearch?.addEventListener('input', () => {
    navigatorSearchCollapsed.clear();
    renderSavedFilterNavigator();
  });
  navigatorSearch?.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown') {
      const first = visibleNavigatorItems()[0];
      if (!first) return;
      event.preventDefault();
      focusNavigatorItem(first);
    } else if (event.key === 'Enter') {
      // Enter uses the Favourites Filter found when the words typed find only one.
      event.preventDefault();
      const leaves = [...navigatorTree.querySelectorAll('[data-saved-filter-navigator-use]')];
      if (leaves.length === 1) useNavigatorFilter(leaves[0].dataset.savedFilterNavigatorUse);
    } else if (event.key === 'Escape' && navigatorSearch.value) {
      // Escape clears the search first; with nothing typed it closes the Filter Navigator.
      event.preventDefault();
      navigatorSearch.value = '';
      navigatorSearchCollapsed.clear();
      renderSavedFilterNavigator();
    }
  });
  navigatorTree?.addEventListener('click', event => {
    const leaf = event.target.closest('[data-saved-filter-navigator-use]');
    if (leaf) {
      useNavigatorFilter(leaf.dataset.savedFilterNavigatorUse);
      return;
    }
    const item = event.target.closest('.saved-filter-navigator-label')?.parentElement;
    if (!item?.hasAttribute('aria-expanded')) return;
    toggleNavigatorBranch(item, item.getAttribute('aria-expanded') !== 'true');
    focusNavigatorItem(item);
  });
  // The keys of a tree: ↑ ↓ Home End move, → opens a branch (or goes into it), ← closes it (or goes to its parent),
  // Enter or Space opens and closes a branch and uses a Favourites Filter.
  navigatorTree?.addEventListener('keydown', event => {
    const item = event.target.closest?.('[role="treeitem"]');
    if (!item) return;
    const items = visibleNavigatorItems();
    const index = items.indexOf(item);
    const branch = item.hasAttribute('aria-expanded');
    const open = item.getAttribute('aria-expanded') === 'true';
    let next = null;
    if (event.key === 'ArrowDown') next = items[index + 1];
    else if (event.key === 'ArrowUp') {
      if (!index) {
        event.preventDefault();
        navigatorSearch?.focus();
        return;
      }
      next = items[index - 1];
    } else if (event.key === 'Home') next = items[0];
    else if (event.key === 'End') next = items[items.length - 1];
    else if (event.key === 'ArrowRight') {
      if (branch && !open) toggleNavigatorBranch(item, true);
      else if (branch) next = items[index + 1];
    } else if (event.key === 'ArrowLeft') {
      if (branch && open) toggleNavigatorBranch(item, false);
      else next = item.parentElement?.closest('[role="treeitem"]');
    } else if (event.key === 'Enter' || event.key === ' ') {
      if (branch) toggleNavigatorBranch(item, !open);
      else useNavigatorFilter(item.dataset.savedFilterNavigatorUse);
    } else return;
    event.preventDefault();
    if (next) focusNavigatorItem(next);
  });

  root.addEventListener('click', event => {
    // Details folds or unfolds the selected card of every selector, without opening the dropdown.
    const details = event.target.closest('[data-saved-filter-details]');
    if (details) {
      event.preventDefault();
      selectedSavedFilterUnfolded = !selectedSavedFilterUnfolded;
      for (const card of selectedSavedFilterCards) {
        card.classList.toggle('is-folded', !selectedSavedFilterUnfolded);
        card.querySelector('[data-saved-filter-details]')?.setAttribute('aria-expanded', String(selectedSavedFilterUnfolded));
      }
      return;
    }
    // In the selected card of the dropdown, the buttons do not open it.
    if (event.target.closest('summary') && event.target.closest('[data-saved-filter-pin], [data-saved-filter-rename], [data-saved-filter-duplicate], [data-saved-filter-newer]')) {
      savedFilterAction(event);
      return;
    }
    const cdrButton = event.target.closest('[data-saved-filter-cdrs]');
    if (cdrButton) {
      event.preventDefault();
      const savedFilter = savedFilters.find(record => savedFilterIdOf(record) === cdrButton.dataset.savedFilterCdrs);
      if (!savedFilter) return;
      const copy = document.getElementById('info-copy');
      const overlay = document.getElementById('info-overlay');
      const previousWhiteSpace = copy?.style.whiteSpace || '';
      if (copy) copy.style.whiteSpace = 'pre-line';
      // A wider panel: each CDR on one line.
      overlay?.classList.add('info-cdr-list');
      showInfoDialog(savedFilterCdrNames(savedFilter).join('\n') || savedFilterCdrSummary(savedFilter), {
        title: `Saved Filter ${savedFilterIdOf(savedFilter)} — CDRs`,
        onClose: () => {
          if (copy) copy.style.whiteSpace = previousWhiteSpace;
          overlay?.classList.remove('info-cdr-list');
          cdrButton.focus();
        },
      });
      return;
    }
    const insightOperator = event.target.closest('[data-gap-insight-operator]');
    if (insightOperator && currentResults) {
      let chosen = [];
      try { chosen = JSON.parse(insightOperator.dataset.gapInsightOperators || '[]'); } catch (_error) { chosen = []; }
      const operator = insightOperator.dataset.gapInsightOperator;
      chosen = chosen.includes(operator) ? chosen.filter(item => item !== operator) : [...chosen, operator];
      if (!chosen.length) return;
      insightSelections.set('gap-insight-operators', JSON.stringify(chosen));
      insightSelections.set('gap-insight-operators-offered', insightOperator.dataset.gapInsightOffered || 'null');
      // Every other section with operator buttons shows its operators as this one.
      let offered = [];
      try { offered = JSON.parse(insightOperator.dataset.gapInsightOffered || '[]'); } catch (_error) { offered = []; }
      setOperatorChoices(Object.fromEntries((Array.isArray(offered) ? offered : []).map(name => [name, chosen.includes(name)])));
      persistScoringViewState();
      // With one operator, the GAP comparison above follows it.
      const comparison = root.querySelector('[data-result-pane="gap"] [data-hierarchy-gap-operator], [data-result-pane="gap"] [data-gap-summary-operator]');
      const key = comparison?.dataset.hierarchyGapStateKey || comparison?.dataset.gapSummaryStateKey;
      if (chosen.length === 1 && key && [...comparison.options].some(option => option.value === `operator:${chosen[0]}`)) {
        gapComparisonSelections.set(key, `operator:${chosen[0]}`);
        persistScoringViewState();
      }
      // The KPI GAP Profile (GAP Analysis) and the Points Lost Map (Points Lost) share the choice.
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    if (event.target.closest('[data-generate-report]')) {
      event.preventDefault();
      void generateScoringReport();
      return;
    }
    const exportLink = event.target.closest('.scoring-export-actions a, .scoring-table-export a');
    if (exportLink?.getAttribute('aria-disabled') === 'true') {
      event.preventDefault();
      return;
    }
    if (exportLink?.matches('[data-export-ppt]')) {
      event.preventDefault();
      void exportSelectedScoringReport(exportLink);
      return;
    }
    const pick = event.target.closest('[data-insight-pick]');
    if (pick && currentResults) {
      insightSelections.set(pick.dataset.insightPick, pick.dataset.insightPickOperator);
      persistScoringViewState();
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    const chip = event.target.closest('[data-insight-chip]');
    if (chip && currentResults) {
      let chosen = [];
      try { chosen = JSON.parse(chip.dataset.insightChosen || '[]'); } catch (_error) { chosen = []; }
      const operator = chip.dataset.insightChip;
      chosen = chosen.includes(operator) ? chosen.filter(item => item !== operator) : [...chosen, operator];
      if (!chosen.length) return;
      insightSelections.set(chip.dataset.insightChipKey, JSON.stringify(chosen));
      // Every other section with operator buttons shows its operators as this one.
      const offered = [...(chip.closest('.scoring-loss-operators') || chip.parentElement).querySelectorAll('[data-insight-chip]')]
        .map(item => item.dataset.insightChip);
      setOperatorChoices(Object.fromEntries(offered.map(name => [name, chosen.includes(name)])));
      persistScoringViewState();
      renderResult(currentResults, selectedSavedFilter);
      return;
    }
    const tab = event.target.closest('[data-result-tab]');
    if (!tab || !root.contains(tab)) return;
    const name = tab.dataset.resultTab;
    if (activeResultTab === name) return;
    activeResultTab = name;
    syncResultTableControls();
    for (const other of root.querySelectorAll('[data-result-tab]')) {
      const selected = other === tab;
      other.setAttribute('aria-selected', String(selected));
      other.tabIndex = selected ? 0 : -1;
    }
    for (const pane of root.querySelectorAll('[data-result-pane]')) pane.hidden = pane.dataset.resultPane !== name;
    // Chosen while the results are scrolled (their tab bar held at the top), the tab opens at its start.
    if (resultTabsBar) {
      const top = parseFloat(getComputedStyle(resultTabsBar).top) || 0;
      const start = resultTabsBar.parentElement.getBoundingClientRect().top;
      if (start < top) window.scrollBy({top: start - top, behavior: 'auto'});
    }
    persistScoringViewState();
    if (currentResults) renderResult(currentResults, selectedSavedFilter, [name]);
  });
  expandedChartClose?.addEventListener('click', closeExpandedChart);
  // The Scoring Results entries of the Scoring tab menu (#scoring-results-summary, -charts, -tables, -geographical-areas,
  // -trends, -gap or -points-lost; -locations from earlier links) open that
  // results tab and show the results tabs at the top of the page.
  const openResultTabFromHash = () => {
    const name = {'scoring-results-summary': 'summary', 'scoring-results-charts': 'charts', 'scoring-results-tables': 'scoring',
      'scoring-results-geographical-areas': 'geographical-areas', 'scoring-results-locations': 'geographical-areas',
      'scoring-results-trends': 'trends', 'scoring-results-gap': 'gap',
      'scoring-results-points-lost': 'points'}[
      decodeURIComponent(window.location.hash.slice(1))];
    if (!name) return;
    root.querySelector(`[data-result-tab="${name}"]`)?.click();
    // Shown once: a reload then returns to the tab and position being read instead of this one.
    window.history.replaceState(window.history.state, '', `${window.location.pathname}${window.location.search}`);
    window.requestAnimationFrame(() => {
      const panel = root.querySelector('.scoring-result-tabs') || root.querySelector('.scoring-results-panel');
      if (!panel) return;
      // The results are drawn after the page opens: the panel stays at the top while they arrive (see app.js).
      if (typeof showSectionAtTop === 'function') {
        showSectionAtTop(panel);
        keepSectionInView(panel);
      } else panel.scrollIntoView({block: 'start'});
    });
  };
  window.addEventListener('hashchange', openResultTabFromHash);
  openResultTabFromHash();
  // Double-clicking a map (the Points Lost Map and the maps of the routes) or a table of the results opens it larger.
  root.addEventListener('dblclick', event => {
    if (event.target.closest('.scoring-chart-card, .scoring-map-zoom, [data-scoring-chart-overlay]')) return;
    const pane = event.target.closest('[data-result-pane]');
    if (!pane) return;
    const meta = selectedEnvironment ? environmentLabel(selectedEnvironment) : '';
    const map = event.target.closest('.scoring-loss-map-figure');
    if (map?.querySelector('svg')) {
      const operator = map.closest('.scoring-loss-map-card')?.querySelector('.scoring-insight-note strong')?.textContent;
      openExpandedView(map.querySelector('svg'), ['Points Lost Map', operator].filter(Boolean).join(' — '), meta, map, 'Map');
      appendExpandedScope(map.closest('.scoring-insight-section')?.querySelector('h4'));
      return;
    }
    const routeMap = event.target.closest('svg.scoring-stretch-map');
    if (routeMap) {
      const heading = routeMap.closest('.scoring-insight-section')?.querySelector('h4');
      openExpandedView(routeMap, titleWithoutScope(heading) || 'Route map', meta, routeMap, 'Map');
      appendExpandedScope(heading);
      return;
    }
    const table = event.target.closest('table');
    if (!table) return;
    // The title of the section the table belongs to: the nearest heading above it in its tab.
    const heading = table.closest('.scoring-insight-section')?.querySelector('h4')
      || [...pane.querySelectorAll('h3, h4')].filter(item => item.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).at(-1);
    openExpandedView(table, titleWithoutScope(heading) || 'Scoring table', meta, table, 'Table');
    appendExpandedScope(heading);
  });
  chartOverlay?.addEventListener('click', event => {
    if (event.target === chartOverlay) closeExpandedChart();
  });
  document.addEventListener('keydown', event => {
    if (!chartOverlay || chartOverlay.hidden) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closeExpandedChart();
      return;
    }
    if (event.key !== 'Tab') return;
    if (event.shiftKey && document.activeElement === expandedChartClose) {
      event.preventDefault();
      chartDialog.focus();
    } else if (!event.shiftKey && document.activeElement === chartDialog) {
      event.preventDefault();
      expandedChartClose.focus();
    } else if (!event.shiftKey && document.activeElement === expandedChartClose) {
      event.preventDefault();
      chartDialog.focus();
    }
  });
  window.addEventListener('pagehide', flushSelectionSaveOnPageHide);
  syncGapValueControls();
  syncResultTableControls();
  applyNrFilter(false);
  // Closed before the page was reloaded: it stays closed.
  if (scoringClosed) syncResultsShown();
  Promise.all([loadCalculationSelection(), refreshSavedFilters()]).catch(() => {});
})();
